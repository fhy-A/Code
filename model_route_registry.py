"""Secret-free durable identities for model routes.

The registry deliberately separates the durable catalog from the runtime
credential table.  API keys are accepted only while refreshing/rehydrating the
registry and are never serialized by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import threading
from typing import Callable, Iterable


CATALOG_SCHEMA = "code-model-route-registry/v1"
ROUTE_REF_PREFIX = "mr1_"
MAX_ROUTES = 10000


class ModelRouteError(ValueError):
    """Stable, secret-free routing failure surfaced by the local API."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = str(code)
        self.retryable = bool(retryable)

    def public_payload(self) -> dict:
        return {
            "error": str(self),
            "errorCode": self.code,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class ResolvedRoute:
    route_ref: str
    catalog_revision: int
    connection_id: str
    source: str
    group: str
    model_id: str
    label: str
    base_url: str
    key: str


def _clean_text(value, limit: int = 240) -> str:
    return str(value or "").strip().replace("\x00", "")[:limit]


def _clean_models(values: Iterable[object]) -> list[str]:
    result = []
    seen = set()
    for value in values or []:
        model = _clean_text(value, 240)
        if model.startswith("models/"):
            model = model[len("models/"):]
        if not model or model in seen:
            continue
        seen.add(model)
        result.append(model)
    return sorted(result)


class ModelRouteRegistry:
    """Thread-safe route catalog with an in-memory-only credential table."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._refresh_condition = threading.Condition(threading.Lock())
        self._refreshing = False
        self._refresh_fingerprint = ""
        self._refresh_generation = 0
        self._last_refresh_generation = 0
        self._last_refresh_result: dict | None = None
        self._credentials: dict[str, str] = {}
        self._base_urls: dict[str, str] = {}
        self._catalog = self._load_catalog()

    def _new_catalog(self) -> dict:
        return {
            "schema": CATALOG_SCHEMA,
            "salt": secrets.token_hex(32),
            "catalogRevision": 0,
            "routes": [],
        }

    def _load_catalog(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return self._new_catalog()
        if not isinstance(payload, dict) or payload.get("schema") != CATALOG_SCHEMA:
            return self._new_catalog()
        salt = _clean_text(payload.get("salt"), 128)
        revision = payload.get("catalogRevision")
        routes = payload.get("routes")
        if (
            len(salt) < 32
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 0
            or not isinstance(routes, list)
        ):
            return self._new_catalog()
        normalized = []
        for raw in routes[:MAX_ROUTES]:
            route = self._normalize_public_route(raw)
            if route:
                normalized.append(route)
        return {
            "schema": CATALOG_SCHEMA,
            "salt": salt,
            "catalogRevision": revision,
            "routes": sorted(normalized, key=self._route_sort_key),
        }

    def _write_catalog(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            self._catalog,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _route_sort_key(route: dict) -> tuple:
        return (
            str(route.get("label") or ""),
            str(route.get("connectionId") or ""),
            str(route.get("modelId") or ""),
        )

    @staticmethod
    def _normalize_public_route(raw) -> dict | None:
        if not isinstance(raw, dict):
            return None
        route_ref = _clean_text(raw.get("routeRef"), 160)
        connection_id = _clean_text(raw.get("connectionId"), 160)
        model_id = _clean_text(raw.get("modelId"), 240)
        source = _clean_text(raw.get("source"), 32)
        if (
            not route_ref.startswith(ROUTE_REF_PREFIX)
            or not connection_id
            or not model_id
            or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,31}", source)
        ):
            return None
        return {
            "routeRef": route_ref,
            "connectionId": connection_id,
            "source": source,
            "group": _clean_text(raw.get("group"), 120) or "default",
            "modelId": model_id,
            "label": _clean_text(raw.get("label"), 160),
            "baseUrlId": _clean_text(raw.get("baseUrlId"), 96),
            "enabled": raw.get("enabled") is not False,
        }

    def _digest(self, namespace: str, *parts: object) -> str:
        key = bytes.fromhex(self._catalog["salt"])
        message = "\x00".join([namespace, *[str(part or "") for part in parts]])
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def workbar_connection_id(self, base_url: str, user_id: str, token_id: str) -> str:
        return "wc1_" + self._digest(
            "workbar-connection-v1", _clean_text(base_url), _clean_text(user_id), _clean_text(token_id),
        )[:32]

    def base_url_id(self, base_url: str) -> str:
        return "bu1_" + self._digest("model-route-base-url-v1", _clean_text(base_url))[:24]

    def _route_ref(self, connection_id: str, model_id: str) -> str:
        return ROUTE_REF_PREFIX + self._digest(
            "model-route-ref-v1", connection_id, model_id,
        )

    def snapshot(self) -> dict:
        with self._lock:
            routes = []
            for route in self._catalog["routes"]:
                routes.append({
                    "routeRef": route["routeRef"],
                    "connectionId": route["connectionId"],
                    "source": route["source"],
                    "modelId": route["modelId"],
                    "label": route["label"],
                    "enabled": route.get("enabled") is not False,
                    "credentialsAvailable": bool(
                        route.get("enabled") and self._credentials.get(route["routeRef"])
                    ),
                })
            return {
                "version": 1,
                "catalogRevision": int(self._catalog["catalogRevision"]),
                "routes": routes,
            }

    @staticmethod
    def _refresh_identity(connections: Iterable[dict]) -> str:
        identities = []
        for raw in connections or []:
            if not isinstance(raw, dict):
                continue
            key_digest = hashlib.sha256(
                str(raw.get("key") or "").encode("utf-8")
            ).hexdigest()
            identities.append({
                "connectionId": _clean_text(raw.get("connectionId"), 160),
                "source": _clean_text(raw.get("source"), 32),
                "baseUrl": _clean_text(raw.get("baseUrl"), 2048),
                "keyDigest": key_digest,
                "enabled": raw.get("enabled") is not False,
                "group": _clean_text(raw.get("group"), 120),
                "label": _clean_text(raw.get("label"), 160),
                "modelLimitsEnabled": raw.get("modelLimitsEnabled") is True,
                "modelLimits": _clean_models(raw.get("modelLimits") or []),
            })
        serialized = json.dumps(
            sorted(identities, key=lambda item: (
                item["connectionId"], item["source"], item["label"],
            )),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def refresh(
        self,
        connections: Iterable[dict],
        fetch_models: Callable[[dict], Iterable[object]],
    ) -> dict:
        """Replace runtime credentials and update the secret-free catalog.

        Failed enabled connections retain their prior public routes but lose
        runtime credentials. This keeps selection explainable while ensuring a
        stale route cannot be used.
        """
        connection_list = list(connections or [])[:1000]
        fingerprint = self._refresh_identity(connection_list)
        with self._refresh_condition:
            while self._refreshing:
                if self._refresh_fingerprint == fingerprint:
                    generation = self._refresh_generation
                    self._refresh_condition.wait_for(lambda: (
                        not self._refreshing
                        or self._refresh_generation != generation
                    ))
                    if (
                        self._last_refresh_generation == generation
                        and self._last_refresh_result is not None
                    ):
                        return json.loads(json.dumps(self._last_refresh_result))
                    continue
                self._refresh_condition.wait()
            self._refreshing = True
            self._refresh_fingerprint = fingerprint
            self._refresh_generation += 1
            generation = self._refresh_generation

        result = None
        try:
            result = self._refresh_connections(connection_list, fetch_models)
            return result
        finally:
            with self._refresh_condition:
                self._refreshing = False
                self._refresh_fingerprint = ""
                self._last_refresh_generation = generation
                self._last_refresh_result = (
                    json.loads(json.dumps(result)) if result is not None else None
                )
                self._refresh_condition.notify_all()

    def _refresh_connections(
        self,
        connection_list: list[dict],
        fetch_models: Callable[[dict], Iterable[object]],
    ) -> dict:
        with self._lock:
            previous_by_connection: dict[str, list[dict]] = {}
            for route in self._catalog["routes"]:
                previous_by_connection.setdefault(route["connectionId"], []).append(dict(route))

        next_routes: list[dict] = []
        next_credentials: dict[str, str] = {}
        failures = []
        successful_connections = 0
        seen_connections = set()

        for raw in connection_list:
            if not isinstance(raw, dict):
                continue
            connection_id = _clean_text(raw.get("connectionId"), 160)
            source = _clean_text(raw.get("source"), 32)
            base_url = _clean_text(raw.get("baseUrl"), 2048)
            if (
                not connection_id
                or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,31}", source)
                or not base_url
            ):
                continue
            if connection_id in seen_connections:
                continue
            seen_connections.add(connection_id)
            enabled = raw.get("enabled") is not False
            key = _clean_text(raw.get("key"), 8192)
            group = _clean_text(raw.get("group"), 120) or "default"
            label = _clean_text(raw.get("label"), 160)
            base_url_id = self.base_url_id(base_url)
            prior = previous_by_connection.get(connection_id, [])

            if not enabled:
                next_routes.extend([{**route, "enabled": False} for route in prior])
                continue
            if not key:
                next_routes.extend(prior)
                failures.append({"connectionId": connection_id, "code": "route_credentials_unavailable"})
                continue
            try:
                models = _clean_models(fetch_models({**raw, "baseUrl": base_url, "key": key}))
            except Exception:
                next_routes.extend(prior)
                failures.append({"connectionId": connection_id, "code": "route_catalog_unavailable"})
                continue

            successful_connections += 1
            if raw.get("modelLimitsEnabled") is True:
                allowed = set(_clean_models(raw.get("modelLimits") or []))
                models = [model for model in models if model in allowed]
            for model_id in models:
                route_ref = self._route_ref(connection_id, model_id)
                route = {
                    "routeRef": route_ref,
                    "connectionId": connection_id,
                    "source": source,
                    "group": group,
                    "modelId": model_id,
                    "label": label,
                    "baseUrlId": base_url_id,
                    "enabled": True,
                }
                next_routes.append(route)
                next_credentials[route_ref] = key

        unique = {}
        for route in next_routes:
            normalized = self._normalize_public_route(route)
            if normalized:
                unique[normalized["routeRef"]] = normalized
        normalized_routes = sorted(unique.values(), key=self._route_sort_key)[:MAX_ROUTES]
        with self._lock:
            previous_routes = self._catalog["routes"]
            changed = normalized_routes != previous_routes
            if changed:
                self._catalog["catalogRevision"] = int(self._catalog["catalogRevision"]) + 1
            self._catalog["routes"] = normalized_routes
            self._credentials = {
                route_ref: key for route_ref, key in next_credentials.items()
                if route_ref in unique
            }
            self._base_urls = {
                _clean_text(item.get("connectionId"), 160): _clean_text(item.get("baseUrl"), 2048)
                for item in connection_list if isinstance(item, dict)
            }
            self._write_catalog()
            snapshot = self.snapshot()
            snapshot.update({
                "ok": successful_connections > 0 or not seen_connections,
                "changed": changed,
                "successfulConnections": successful_connections,
                "failedConnections": len(failures),
                "failures": failures,
            })
            return snapshot

    def resolve(
        self,
        route_ref: str,
        catalog_revision: int,
        model_id: str,
    ) -> ResolvedRoute:
        normalized_ref = _clean_text(route_ref, 160)
        normalized_model = _clean_text(model_id, 240)
        with self._lock:
            revision = int(self._catalog["catalogRevision"])
            if not self._catalog["routes"]:
                raise ModelRouteError(
                    "route_catalog_unavailable",
                    "Model route catalog is unavailable. Refresh connections and try again.",
                    retryable=True,
                )
            if (
                isinstance(catalog_revision, bool)
                or not isinstance(catalog_revision, int)
                or catalog_revision != revision
            ):
                raise ModelRouteError(
                    "route_stale",
                    "The selected model route is stale. Refresh routes and select it again.",
                    retryable=True,
                )
            route = next(
                (item for item in self._catalog["routes"] if item["routeRef"] == normalized_ref),
                None,
            )
            if not route:
                raise ModelRouteError("route_not_found", "The selected model route no longer exists.")
            if route["modelId"] != normalized_model:
                raise ModelRouteError(
                    "route_model_mismatch",
                    "The selected model does not match the model route.",
                )
            if route.get("enabled") is False:
                raise ModelRouteError("route_disabled", "The selected model route is disabled.")
            key = self._credentials.get(normalized_ref)
            if not key:
                raise ModelRouteError(
                    "route_credentials_unavailable",
                    "Credentials for the selected route are not available. Refresh connections and try again.",
                    retryable=True,
                )
            return ResolvedRoute(
                route_ref=normalized_ref,
                catalog_revision=revision,
                connection_id=route["connectionId"],
                source=route["source"],
                group=route["group"],
                model_id=route["modelId"],
                label=route["label"],
                base_url=self._base_urls.get(route["connectionId"], ""),
                key=key,
            )

    def bind_runtime_base_urls(self, connections: Iterable[dict]) -> None:
        """Attach non-durable base URLs to matching public routes in memory."""
        with self._lock:
            by_connection = {
                _clean_text(item.get("connectionId"), 160): _clean_text(item.get("baseUrl"), 2048)
                for item in connections or [] if isinstance(item, dict)
            }
            self._base_urls = by_connection
