"""Independent image-route, upstream, and generated-asset foundations.

This module deliberately does not import the chat ModelRouteRegistry. Image
credentials and base URLs exist only in memory; durable catalogs and assets use
opaque identities and secret-free metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import threading
import time
from typing import Iterable
from urllib import error, parse, request

from PIL import Image, UnidentifiedImageError


IMAGE_ROUTE_CATALOG_SCHEMA = "code-image-route-registry/v1"
IMAGE_ROUTE_REF_PREFIX = "ir1_"
GENERATED_ASSET_SCHEMA = "code-generated-asset/v1"
GENERATED_ASSET_ID_PREFIX = "ga1_"

MAX_IMAGE_ROUTES = 5000
MAX_IMAGE_MODELS_PER_CONNECTION = 100
MAX_IMAGE_COUNT = 4
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_TOTAL_BYTES = MAX_IMAGE_COUNT * MAX_IMAGE_BYTES
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_RESPONSE_BYTES = 112 * 1024 * 1024
MAX_IMAGE_REDIRECTS = 3
IMAGE_TIMEOUT_SECONDS = 60

ALLOWED_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
IMAGE_FORMAT_MIMES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
ALLOWED_IMAGE_SIZES = frozenset({
    "auto", "256x256", "512x512", "1024x1024", "1024x1536", "1536x1024",
})
ALLOWED_IMAGE_QUALITIES = frozenset({
    "auto", "standard", "hd", "low", "medium", "high",
})
ALLOWED_IMAGE_OUTPUT_FORMATS = frozenset({"png", "jpeg", "webp"})
IMAGE_OUTPUT_FORMAT_MIMES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


class ImageRuntimeError(RuntimeError):
    """Stable secret-free error for image routes, assets, or upstream work."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int = 400,
        outcome_unknown: bool = False,
    ):
        super().__init__(str(message))
        self.code = str(code)
        self.retryable = bool(retryable)
        self.http_status = int(http_status)
        self.outcome_unknown = bool(outcome_unknown)

    def public_payload(self) -> dict:
        payload = {
            "error": str(self),
            "errorCode": self.code,
            "retryable": self.retryable,
        }
        if self.outcome_unknown:
            payload.update({"outcomeUnknown": True, "notReplayed": True})
        return payload

    def tool_result(self) -> dict:
        return {"ok": False, "action": "generate_image", **self.public_payload()}


@dataclass(frozen=True)
class ResolvedImageRoute:
    route_ref: str
    catalog_revision: int
    connection_id: str
    label: str
    model_id: str
    supports_generation: bool
    supports_edit: bool
    base_url: str
    key: str

    def public_identity(self) -> dict:
        return {
            "routeRef": self.route_ref,
            "catalogRevision": self.catalog_revision,
            "connectionId": self.connection_id,
            "label": self.label,
            "modelId": self.model_id,
            "supportsGeneration": self.supports_generation,
        }


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    sha256: str

    @property
    def byte_length(self) -> int:
        return len(self.data)


def _clean_text(value, limit: int = 240) -> str:
    return str(value or "").strip().replace("\x00", "")[:limit]


def _normalized_base_url(value) -> str:
    raw = _clean_text(value, 2048).rstrip("/")
    try:
        parsed = parse.urlsplit(raw)
    except ValueError as exc:
        raise ImageRuntimeError("image_route_invalid", "Image connection URL is invalid.") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ImageRuntimeError("image_route_invalid", "Image connection URL is invalid.")
    return parse.urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _normalize_model_entries(values: Iterable[object]) -> list[dict]:
    result = {}
    for raw in list(values or [])[:MAX_IMAGE_MODELS_PER_CONNECTION]:
        if isinstance(raw, str):
            model_id = _clean_text(raw, 240)
        elif isinstance(raw, dict):
            model_id = _clean_text(raw.get("id") or raw.get("modelId"), 240)
        else:
            continue
        if not model_id:
            continue
        result[model_id] = {
            "modelId": model_id,
            "supportsGeneration": True,
        }
    return [result[key] for key in sorted(result)]


class ImageRouteRegistry:
    """Thread-safe secret-free image catalog with in-memory credentials."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._credentials: dict[str, str] = {}
        self._base_urls: dict[str, str] = {}
        self._catalog = self._load_catalog()

    def _new_catalog(self) -> dict:
        return {
            "schema": IMAGE_ROUTE_CATALOG_SCHEMA,
            "salt": secrets.token_hex(32),
            "catalogRevision": 0,
            "routes": [],
        }

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
        if (
            not re.fullmatch(r"ir1_[a-f0-9]{64}", route_ref)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", connection_id)
            or not model_id
        ):
            return None
        return {
            "routeRef": route_ref,
            "connectionId": connection_id,
            "label": _clean_text(raw.get("label"), 160),
            "modelId": model_id,
            "supportsGeneration": raw.get("supportsGeneration") is not False,
            "enabled": raw.get("enabled") is not False,
        }

    def _load_catalog(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return self._new_catalog()
        if not isinstance(payload, dict) or payload.get("schema") != IMAGE_ROUTE_CATALOG_SCHEMA:
            return self._new_catalog()
        salt = _clean_text(payload.get("salt"), 128)
        revision = payload.get("catalogRevision")
        routes = payload.get("routes")
        if (
            not re.fullmatch(r"[a-f0-9]{64}", salt)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 0
            or not isinstance(routes, list)
        ):
            return self._new_catalog()
        normalized = []
        for raw in routes[:MAX_IMAGE_ROUTES]:
            route = self._normalize_public_route(raw)
            if route:
                normalized.append(route)
        return {
            "schema": IMAGE_ROUTE_CATALOG_SCHEMA,
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

    def _digest(self, namespace: str, *parts: object) -> str:
        key = bytes.fromhex(self._catalog["salt"])
        message = "\x00".join([namespace, *[str(part or "") for part in parts]])
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def _route_ref(self, connection_id: str, model_id: str) -> str:
        return IMAGE_ROUTE_REF_PREFIX + self._digest(
            "image-route-ref-v1", connection_id, model_id,
        )

    def snapshot(self) -> dict:
        with self._lock:
            routes = []
            for route in self._catalog["routes"]:
                routes.append({
                    "routeRef": route["routeRef"],
                    "connectionId": route["connectionId"],
                    "label": route["label"],
                    "modelId": route["modelId"],
                    "supportsGeneration": route.get("supportsGeneration") is not False,
                    "enabled": route.get("enabled") is not False,
                    "credentialsAvailable": bool(
                        route.get("enabled") is not False
                        and self._credentials.get(route["routeRef"])
                        and self._base_urls.get(route["routeRef"])
                    ),
                })
            return {
                "version": 1,
                "catalogRevision": int(self._catalog["catalogRevision"]),
                "routes": routes,
            }

    def refresh(self, connections: Iterable[dict]) -> dict:
        connection_list = list(connections or [])[:1000]
        with self._lock:
            previous_by_connection: dict[str, list[dict]] = {}
            for route in self._catalog["routes"]:
                previous_by_connection.setdefault(route["connectionId"], []).append(dict(route))

            next_routes = []
            next_credentials = {}
            next_base_urls = {}
            failures = []
            seen = set()
            successful_connections = 0

            for raw in connection_list:
                if not isinstance(raw, dict):
                    continue
                connection_id = _clean_text(raw.get("connectionId"), 160)
                label = _clean_text(raw.get("name") or raw.get("label"), 160)
                if (
                    not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", connection_id)
                    or not label
                    or connection_id in seen
                ):
                    continue
                seen.add(connection_id)
                prior = previous_by_connection.get(connection_id, [])
                if raw.get("enabled") is False:
                    next_routes.extend([{**route, "enabled": False} for route in prior])
                    continue
                try:
                    base_url = _normalized_base_url(raw.get("baseUrl"))
                except ImageRuntimeError:
                    next_routes.extend(prior)
                    failures.append({"connectionId": connection_id, "code": "image_route_invalid"})
                    continue
                key = _clean_text(raw.get("key"), 8192)
                models = _normalize_model_entries(raw.get("models") or raw.get("imageModels") or [])
                if not key:
                    next_routes.extend(prior)
                    failures.append({
                        "connectionId": connection_id,
                        "code": "image_route_credentials_unavailable",
                    })
                    continue
                if not models:
                    next_routes.extend(prior)
                    failures.append({"connectionId": connection_id, "code": "image_route_models_missing"})
                    continue
                successful_connections += 1
                for model in models:
                    route_ref = self._route_ref(connection_id, model["modelId"])
                    route = {
                        "routeRef": route_ref,
                        "connectionId": connection_id,
                        "label": label,
                        "modelId": model["modelId"],
                        "supportsGeneration": True,
                        "enabled": True,
                    }
                    next_routes.append(route)
                    next_credentials[route_ref] = key
                    next_base_urls[route_ref] = base_url

            unique = {}
            for route in next_routes:
                normalized = self._normalize_public_route(route)
                if normalized:
                    unique[normalized["routeRef"]] = normalized
            normalized_routes = sorted(unique.values(), key=self._route_sort_key)[:MAX_IMAGE_ROUTES]
            changed = normalized_routes != self._catalog["routes"]
            if changed:
                self._catalog["catalogRevision"] = int(self._catalog["catalogRevision"]) + 1
            self._catalog["routes"] = normalized_routes
            self._credentials = {
                ref: value for ref, value in next_credentials.items() if ref in unique
            }
            self._base_urls = {
                ref: value for ref, value in next_base_urls.items() if ref in unique
            }
            self._write_catalog()
            snapshot = self.snapshot()
            snapshot.update({
                "ok": successful_connections > 0 or not seen,
                "changed": changed,
                "successfulConnections": successful_connections,
                "failedConnections": len(failures),
                "failures": failures,
            })
            return snapshot

    def resolve(self, route_ref: str, catalog_revision: int, model_id: str) -> ResolvedImageRoute:
        normalized_ref = _clean_text(route_ref, 160)
        normalized_model = _clean_text(model_id, 240)
        with self._lock:
            revision = int(self._catalog["catalogRevision"])
            if not self._catalog["routes"]:
                raise ImageRuntimeError(
                    "image_route_catalog_unavailable",
                    "Image route catalog is unavailable.",
                    retryable=True,
                    http_status=503,
                )
            if (
                isinstance(catalog_revision, bool)
                or not isinstance(catalog_revision, int)
                or catalog_revision != revision
            ):
                raise ImageRuntimeError(
                    "image_route_stale",
                    "The selected image route is stale.",
                    retryable=True,
                    http_status=409,
                )
            route = next(
                (item for item in self._catalog["routes"] if item["routeRef"] == normalized_ref),
                None,
            )
            if not route:
                raise ImageRuntimeError("image_route_not_found", "The selected image route no longer exists.", http_status=409)
            if route["modelId"] != normalized_model:
                raise ImageRuntimeError("image_route_model_mismatch", "The image model does not match the selected route.", http_status=409)
            if route.get("enabled") is False:
                raise ImageRuntimeError("image_route_disabled", "The selected image route is disabled.", http_status=409)
            key = self._credentials.get(normalized_ref)
            base_url = self._base_urls.get(normalized_ref)
            if not key or not base_url:
                raise ImageRuntimeError(
                    "image_route_credentials_unavailable",
                    "Credentials for the selected image route are unavailable.",
                    retryable=True,
                    http_status=503,
                )
            return ResolvedImageRoute(
                route_ref=normalized_ref,
                catalog_revision=revision,
                connection_id=route["connectionId"],
                label=route["label"],
                model_id=route["modelId"],
                supports_generation=route.get("supportsGeneration") is not False,
                # Legacy supportsEdit values are intentionally ignored. A
                # single owned reference always attempts the edits endpoint.
                supports_edit=True,
                base_url=base_url,
                key=key,
            )


def normalize_generate_request(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ImageRuntimeError("image_request_invalid", "Image arguments must be an object.")
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt or len(prompt) > 8000:
        raise ImageRuntimeError("image_prompt_invalid", "Image prompt must contain 1 to 8000 characters.")
    count = payload.get("count", 1)
    if isinstance(count, bool):
        raise ImageRuntimeError("image_count_invalid", "Image count must be between 1 and 4.")
    try:
        count = int(count)
    except (TypeError, ValueError) as exc:
        raise ImageRuntimeError("image_count_invalid", "Image count must be between 1 and 4.") from exc
    if count < 1 or count > MAX_IMAGE_COUNT:
        raise ImageRuntimeError("image_count_invalid", "Image count must be between 1 and 4.")
    size = str(payload.get("size") or "auto").strip().lower()
    quality = str(payload.get("quality") or "auto").strip().lower()
    output_format = str(payload.get("outputFormat") or "png").strip().lower()
    if size not in ALLOWED_IMAGE_SIZES:
        raise ImageRuntimeError("image_size_invalid", "Image size is not supported.")
    if quality not in ALLOWED_IMAGE_QUALITIES:
        raise ImageRuntimeError("image_quality_invalid", "Image quality is not supported.")
    if output_format not in ALLOWED_IMAGE_OUTPUT_FORMATS:
        raise ImageRuntimeError("image_format_invalid", "Image output format is not supported.")
    reference = payload.get("reference")
    if reference is not None:
        if not isinstance(reference, dict):
            raise ImageRuntimeError("image_reference_invalid", "Image reference identity is invalid.")
        reference_type = str(reference.get("type") or "").strip()
        reference_id = str(reference.get("id") or "").strip()
        if reference_type not in {"attachment", "generated_asset"} or not reference_id or len(reference_id) > 512:
            raise ImageRuntimeError("image_reference_invalid", "Image reference identity is invalid.")
        reference = {"type": reference_type, "id": reference_id}
    return {
        "prompt": prompt,
        "count": count,
        "size": size,
        "quality": quality,
        "outputFormat": output_format,
        "reference": reference,
    }


def _magic_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ImageRuntimeError("image_response_invalid", "Generated image signature is not supported.")


def validate_image_bytes(data: bytes, declared_mime: str = "") -> ValidatedImage:
    payload = bytes(data or b"")
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ImageRuntimeError("image_response_too_large", "Generated image exceeds the per-image size limit.")
    detected_mime = _magic_mime(payload)
    declared = str(declared_mime or "").split(";", 1)[0].strip().lower()
    if declared and declared not in ALLOWED_IMAGE_MIMES:
        raise ImageRuntimeError("image_response_mime_invalid", "Generated image MIME is not supported.")
    if declared and declared != detected_mime:
        raise ImageRuntimeError("image_response_mime_mismatch", "Generated image MIME does not match its bytes.")
    try:
        with Image.open(io.BytesIO(payload)) as candidate:
            format_mime = IMAGE_FORMAT_MIMES.get(str(candidate.format or "").upper())
            width, height = candidate.size
            candidate.verify()
        if format_mime != detected_mime:
            raise ImageRuntimeError("image_response_mime_mismatch", "Generated image format does not match its bytes.")
        if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
            raise ImageRuntimeError("image_response_pixels_invalid", "Generated image dimensions exceed the pixel limit.")
        with Image.open(io.BytesIO(payload)) as decoded:
            decoded.load()
    except ImageRuntimeError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageRuntimeError("image_response_pixels_invalid", "Generated image dimensions exceed the pixel limit.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageRuntimeError("image_response_corrupt", "Generated image is damaged or incomplete.") from exc
    return ValidatedImage(
        data=payload,
        mime_type=detected_mime,
        extension=IMAGE_EXTENSIONS[detected_mime],
        width=int(width),
        height=int(height),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _public_addresses(host: str, port: int, resolver=socket.getaddrinfo):
    try:
        records = resolver(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    except (OSError, socket.gaierror) as exc:
        raise ImageRuntimeError("image_download_dns_failed", "Generated image host could not be resolved.", retryable=True, http_status=502) from exc
    validated = []
    seen = set()
    for family, socktype, proto, canonname, sockaddr in records or ():
        if family not in {socket.AF_INET, socket.AF_INET6} or not sockaddr:
            raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image URL was blocked by the public-address policy.")
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image URL was blocked by the public-address policy.") from exc
        if (
            not address.is_global
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image URL was blocked by the public-address policy.")
        key = (family, address.compressed, int(port))
        if key in seen:
            continue
        seen.add(key)
        validated.append((family, socktype or socket.SOCK_STREAM, proto or socket.IPPROTO_TCP, canonname, sockaddr))
    if not validated:
        raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image URL was blocked by the public-address policy.")
    return tuple(validated)


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, addresses, *, timeout, use_tls, socket_factory=socket.socket, tls_context_factory=ssl.create_default_context):
        super().__init__(host, port=port, timeout=timeout)
        self._addresses = tuple(addresses)
        self._use_tls = bool(use_tls)
        self._socket_factory = socket_factory
        self._tls_context_factory = tls_context_factory

    def connect(self):
        last_error = None
        for family, socktype, proto, _canonname, sockaddr in self._addresses:
            raw_socket = None
            try:
                raw_socket = self._socket_factory(family, socktype, proto)
                raw_socket.settimeout(self.timeout)
                raw_socket.connect(sockaddr)
                peer_ip = ipaddress.ip_address(str(raw_socket.getpeername()[0]).split("%", 1)[0])
                expected_ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
                if peer_ip != expected_ip:
                    raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image connection peer changed.")
                if self._use_tls:
                    context = self._tls_context_factory()
                    raw_socket = context.wrap_socket(raw_socket, server_hostname=self.host)
                self.sock = raw_socket
                return
            except Exception as exc:
                last_error = exc
                if raw_socket is not None:
                    try:
                        raw_socket.close()
                    except OSError:
                        pass
        if isinstance(last_error, ImageRuntimeError):
            raise last_error
        raise ImageRuntimeError("image_download_failed", "Generated image download failed.", retryable=True, http_status=502) from last_error


def _default_public_connection_factory(*, scheme, host, port, addresses, timeout):
    return _PinnedConnection(
        host,
        port,
        addresses,
        timeout=timeout,
        use_tls=scheme == "https",
    )


class PublicImageDownloader:
    """Redirect-aware downloader pinned to prevalidated public DNS answers."""

    def __init__(self, *, resolver=socket.getaddrinfo, connection_factory=None, clock=time.monotonic):
        self._resolver = resolver
        self._connection_factory = connection_factory or _default_public_connection_factory
        self._clock = clock

    @staticmethod
    def _parsed_url(url: str):
        if not isinstance(url, str) or not url or any(ord(ch) < 32 for ch in url):
            raise ImageRuntimeError("image_download_url_invalid", "Generated image URL is invalid.")
        try:
            parsed = parse.urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise ImageRuntimeError("image_download_url_invalid", "Generated image URL is invalid.") from exc
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise ImageRuntimeError("image_download_url_invalid", "Generated image URL is invalid.")
        if parsed.username is not None or parsed.password is not None:
            raise ImageRuntimeError("image_download_url_invalid", "Credentialed image URLs are not allowed.")
        default_port = 443 if scheme == "https" else 80
        if port not in {None, default_port}:
            raise ImageRuntimeError("image_download_url_invalid", "Non-default image URL ports are not allowed.")
        host = parsed.hostname.rstrip(".").lower()
        if not host or host == "localhost" or host.endswith(".local"):
            raise ImageRuntimeError("image_download_ssrf_blocked", "Generated image URL was blocked by the public-address policy.")
        path = parsed.path or "/"
        if not path.startswith("/") or "\\" in path:
            raise ImageRuntimeError("image_download_url_invalid", "Generated image URL path is invalid.")
        target = parse.urlunsplit(("", "", path, parsed.query, ""))
        normalized = parse.urlunsplit((scheme, host, path, parsed.query, ""))
        return scheme, host, default_port, target, normalized

    def fetch(self, url: str, *, timeout: float = IMAGE_TIMEOUT_SECONDS) -> ValidatedImage:
        deadline = self._clock() + max(0.05, min(float(timeout), IMAGE_TIMEOUT_SECONDS))
        current_url = url
        previous_scheme = None
        visited = set()
        for redirect_count in range(MAX_IMAGE_REDIRECTS + 1):
            scheme, host, port, target, normalized = self._parsed_url(current_url)
            if previous_scheme == "https" and scheme != "https":
                raise ImageRuntimeError("image_download_redirect_blocked", "Generated image redirect was blocked.")
            previous_scheme = scheme
            if normalized in visited:
                raise ImageRuntimeError("image_download_redirect_blocked", "Generated image redirect loop was blocked.")
            visited.add(normalized)
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise ImageRuntimeError("image_download_timeout", "Generated image download timed out.", retryable=True, http_status=504)
            addresses = _public_addresses(host, port, self._resolver)
            connection = self._connection_factory(
                scheme=scheme,
                host=host,
                port=port,
                addresses=addresses,
                timeout=min(5.0, remaining),
            )
            response = None
            try:
                connection.putrequest("GET", target, skip_host=True, skip_accept_encoding=True)
                connection.putheader("Host", host)
                connection.putheader("Accept", "image/png,image/jpeg,image/webp")
                connection.putheader("User-Agent", "Code-Image-Asset/1")
                connection.putheader("Connection", "close")
                connection.endheaders()
                response = connection.getresponse()
                status = int(response.status)
                if status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location or redirect_count >= MAX_IMAGE_REDIRECTS:
                        raise ImageRuntimeError("image_download_redirect_blocked", "Generated image redirect limit was exceeded.")
                    current_url = parse.urljoin(normalized, location)
                    continue
                if status < 200 or status >= 300:
                    raise ImageRuntimeError(
                        "image_download_failed",
                        "Generated image download failed.",
                        retryable=status in {408, 425, 429} or status >= 500,
                        http_status=502,
                    )
                declared_length = response.getheader("Content-Length")
                if declared_length is not None:
                    try:
                        declared_length = int(declared_length)
                    except (TypeError, ValueError) as exc:
                        raise ImageRuntimeError("image_response_invalid", "Generated image response length is invalid.") from exc
                    if declared_length < 1 or declared_length > MAX_IMAGE_BYTES:
                        raise ImageRuntimeError("image_response_too_large", "Generated image exceeds the per-image size limit.")
                chunks = []
                total = 0
                while True:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise ImageRuntimeError("image_download_timeout", "Generated image download timed out.", retryable=True, http_status=504)
                    active_socket = getattr(connection, "sock", None)
                    if active_socket is not None:
                        active_socket.settimeout(min(5.0, remaining))
                    chunk = response.read(min(64 * 1024, MAX_IMAGE_BYTES + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ImageRuntimeError("image_response_too_large", "Generated image exceeds the per-image size limit.")
                if declared_length is not None and total != declared_length:
                    raise ImageRuntimeError("image_response_invalid", "Generated image response was incomplete.")
                content_type = response.getheader("Content-Type") or ""
                if not content_type:
                    raise ImageRuntimeError(
                        "image_response_mime_invalid",
                        "Generated image response did not declare an image MIME.",
                    )
                return validate_image_bytes(b"".join(chunks), content_type)
            except ImageRuntimeError:
                raise
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                raise ImageRuntimeError("image_download_failed", "Generated image download failed.", retryable=True, http_status=502) from exc
            finally:
                if response is not None:
                    try:
                        response.close()
                    except OSError:
                        pass
                try:
                    connection.close()
                except OSError:
                    pass
        raise ImageRuntimeError("image_download_redirect_blocked", "Generated image redirect limit was exceeded.")


def build_edit_multipart(fields: dict, image: ValidatedImage) -> tuple[bytes, str]:
    boundary = "code-image-" + secrets.token_hex(16)
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode("ascii"),
        b'Content-Disposition: form-data; name="image"; filename="reference.',
        image.extension.encode("ascii"),
        b'"\r\n',
        f"Content-Type: {image.mime_type}\r\n\r\n".encode("ascii"),
        image.data,
        b"\r\n",
        f"--{boundary}--\r\n".encode("ascii"),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class ImageUpstreamClient:
    """Bounded OpenAI-compatible generations/edits client."""

    def __init__(self, *, urlopen=request.urlopen, downloader=None, clock=time.monotonic):
        self._urlopen = urlopen
        self._downloader = downloader or PublicImageDownloader()
        self._clock = clock

    @staticmethod
    def _endpoint_url(base_url: str, endpoint: str) -> str:
        base = str(base_url or "").rstrip("/")
        suffix = str(endpoint or "").lstrip("/")
        if base.lower().endswith("/v1") and suffix.lower().startswith("v1/"):
            suffix = suffix[3:]
        return f"{base}/{suffix}"

    @staticmethod
    def _read_bounded(response, limit: int) -> bytes:
        declared = response.headers.get("Content-Length") if response.headers else None
        if declared is not None:
            try:
                declared = int(declared)
            except (TypeError, ValueError) as exc:
                raise ImageRuntimeError("image_response_invalid", "Image API response length is invalid.") from exc
            if declared < 0 or declared > limit:
                raise ImageRuntimeError("image_response_too_large", "Image API response exceeds the total size limit.")
        chunks = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise ImageRuntimeError("image_response_too_large", "Image API response exceeds the total size limit.")
        if declared is not None and total != declared:
            raise ImageRuntimeError("image_response_invalid", "Image API response was incomplete.")
        return b"".join(chunks)

    @staticmethod
    def _http_error(status: int, *, reference_edit: bool = False) -> ImageRuntimeError:
        if status in {401, 403}:
            return ImageRuntimeError("image_credentials_rejected", "Image connection credentials were rejected.", http_status=502)
        if reference_edit and status in {404, 405, 501}:
            return ImageRuntimeError(
                "image_edit_unsupported",
                "Image service does not support reference editing.",
                http_status=502,
                outcome_unknown=True,
            )
        if status == 429:
            return ImageRuntimeError("image_rate_limited", "Image service rate limit was reached.", retryable=True, http_status=429)
        if status in {408, 504}:
            return ImageRuntimeError("image_upstream_timeout", "Image service timed out after dispatch.", retryable=True, http_status=504, outcome_unknown=True)
        return ImageRuntimeError(
            "image_upstream_http_error",
            "Image service rejected the request.",
            retryable=status >= 500,
            http_status=502,
            outcome_unknown=status >= 500,
        )

    def _decode_images(self, raw: bytes, normalized_request: dict, *, deadline: float) -> list[ValidatedImage]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ImageRuntimeError("image_response_invalid", "Image service returned invalid JSON.") from exc
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != normalized_request["count"]:
            raise ImageRuntimeError("image_response_count_invalid", "Image service returned an unexpected image count.")
        expected_mime = IMAGE_OUTPUT_FORMAT_MIMES[normalized_request["outputFormat"]]
        expected_size = None
        if normalized_request["size"] != "auto":
            width, height = normalized_request["size"].split("x", 1)
            expected_size = int(width), int(height)
        images = []
        total = 0
        for item in items:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise ImageRuntimeError(
                    "image_upstream_timeout",
                    "Image service response processing timed out after dispatch.",
                    retryable=True,
                    http_status=504,
                )
            if not isinstance(item, dict):
                raise ImageRuntimeError("image_response_invalid", "Image service returned an invalid image item.")
            encoded = item.get("b64_json")
            if isinstance(encoded, str) and encoded:
                if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 16:
                    raise ImageRuntimeError("image_response_too_large", "Generated image exceeds the per-image size limit.")
                try:
                    image = validate_image_bytes(base64.b64decode(encoded, validate=True))
                except (ValueError, binascii.Error) as exc:
                    raise ImageRuntimeError("image_response_base64_invalid", "Generated image base64 is invalid.") from exc
            elif isinstance(item.get("url"), str) and item.get("url"):
                image = self._downloader.fetch(item["url"], timeout=remaining)
            else:
                raise ImageRuntimeError("image_response_invalid", "Image service returned no supported image payload.")
            if image.mime_type != expected_mime:
                raise ImageRuntimeError(
                    "image_response_format_mismatch",
                    "Generated image format did not match the requested output format.",
                )
            if expected_size is not None and (image.width, image.height) != expected_size:
                raise ImageRuntimeError(
                    "image_response_size_mismatch",
                    "Generated image dimensions did not match the requested size.",
                )
            total += image.byte_length
            if total > MAX_IMAGE_TOTAL_BYTES:
                raise ImageRuntimeError("image_response_too_large", "Generated image set exceeds the total size limit.")
            images.append(image)
        return images

    def generate(
        self,
        route: ResolvedImageRoute,
        normalized_request: dict,
        operation_id: str,
        *,
        reference_image: ValidatedImage | None = None,
        cancel_event=None,
        timeout: int = IMAGE_TIMEOUT_SECONDS,
    ) -> list[ValidatedImage]:
        if cancel_event is not None and cancel_event.is_set():
            raise ImageRuntimeError("image_cancelled", "Image generation was cancelled before dispatch.")
        bounded_timeout = max(1, min(int(timeout), IMAGE_TIMEOUT_SECONDS))
        deadline = self._clock() + bounded_timeout
        endpoint = "/v1/images/edits" if reference_image is not None else "/v1/images/generations"
        target = self._endpoint_url(route.base_url, endpoint)
        fields = {
            "model": route.model_id,
            "prompt": normalized_request["prompt"],
            "size": normalized_request["size"],
            "quality": normalized_request["quality"],
            "n": normalized_request["count"],
            "response_format": "b64_json",
            "output_format": normalized_request["outputFormat"],
        }
        if reference_image is None:
            body = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        else:
            body, content_type = build_edit_multipart(fields, reference_image)
        upstream_request = request.Request(
            target,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {route.key}",
                "Content-Type": content_type,
                "Accept": "application/json",
                "Idempotency-Key": operation_id,
                "User-Agent": "Code-Image-Runtime/1",
            },
        )
        response = None
        try:
            response = self._urlopen(upstream_request, timeout=bounded_timeout)
            status = int(getattr(response, "status", 200) or 200)
            if status < 200 or status >= 300:
                raise self._http_error(status, reference_edit=reference_image is not None)
            try:
                raw = self._read_bounded(response, MAX_IMAGE_RESPONSE_BYTES)
            except ImageRuntimeError as exc:
                raise ImageRuntimeError(
                    exc.code,
                    str(exc),
                    retryable=exc.retryable,
                    http_status=exc.http_status,
                    outcome_unknown=True,
                ) from None
        except ImageRuntimeError:
            raise
        except error.HTTPError as exc:
            raise self._http_error(
                int(exc.code),
                reference_edit=reference_image is not None,
            ) from None
        except (TimeoutError, socket.timeout) as exc:
            raise ImageRuntimeError("image_upstream_timeout", "Image service timed out after dispatch.", retryable=True, http_status=504, outcome_unknown=True) from exc
        except (error.URLError, OSError, http.client.HTTPException) as exc:
            raise ImageRuntimeError("image_upstream_network_error", "Image service connection failed after dispatch.", retryable=True, http_status=502, outcome_unknown=True) from exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
        if cancel_event is not None and cancel_event.is_set():
            raise ImageRuntimeError("image_cancelled", "Image generation was cancelled after dispatch.", outcome_unknown=True)
        try:
            return self._decode_images(
                raw,
                normalized_request,
                deadline=deadline,
            )
        except ImageRuntimeError as exc:
            if exc.outcome_unknown:
                raise
            raise ImageRuntimeError(
                exc.code,
                str(exc),
                retryable=exc.retryable,
                http_status=exc.http_status,
                outcome_unknown=True,
            ) from None


class GeneratedAssetRepository:
    """Single-host asset store with opaque IDs and Session ownership."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.RLock()

    @staticmethod
    def _valid_asset_id(asset_id: str) -> bool:
        return bool(re.fullmatch(r"ga1_[A-Za-z0-9_-]{32,96}", str(asset_id or "")))

    def _asset_dir(self, asset_id: str) -> Path:
        if not self._valid_asset_id(asset_id):
            raise ImageRuntimeError("generated_asset_not_found", "Generated asset was not found.", http_status=404)
        target = (self.root / asset_id).resolve()
        root = self.root.resolve()
        if root not in target.parents:
            raise ImageRuntimeError("generated_asset_not_found", "Generated asset was not found.", http_status=404)
        return target

    def _read_meta_dir(self, asset_dir: Path) -> dict | None:
        try:
            payload = json.loads((asset_dir / "meta.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != GENERATED_ASSET_SCHEMA:
            return None
        if payload.get("assetId") != asset_dir.name or not self._valid_asset_id(asset_dir.name):
            return None
        if not re.fullmatch(r"content\.(?:png|jpg|webp)", str(payload.get("fileName") or "")):
            return None
        return payload

    def _all_operation_assets(self, operation_id: str, session_id: str, agent_run_id: str, tool_call_id: str) -> list[dict]:
        if not self.root.exists():
            return []
        matches = []
        for candidate in self.root.iterdir():
            if not candidate.is_dir() or not self._valid_asset_id(candidate.name):
                continue
            meta = self._read_meta_dir(candidate)
            if not meta:
                continue
            if (
                meta.get("operationId") == operation_id
                and meta.get("sessionId") == session_id
                and meta.get("agentRunId") == agent_run_id
                and meta.get("toolCallId") == tool_call_id
            ):
                matches.append(meta)
        return sorted(matches, key=lambda item: int(item.get("index") or 0))

    @staticmethod
    def public_asset(meta: dict) -> dict:
        return {
            "assetId": str(meta.get("assetId") or ""),
            "url": f"/api/sessions/{meta.get('sessionId')}/generated-assets/{meta.get('assetId')}",
            "mimeType": str(meta.get("mimeType") or ""),
            "width": int(meta.get("width") or 0),
            "height": int(meta.get("height") or 0),
            "byteLength": int(meta.get("byteLength") or 0),
            "sha256": str(meta.get("sha256") or ""),
        }

    def find_operation_result(self, operation_id: str, session_id: str, agent_run_id: str, tool_call_id: str, expected_count: int) -> dict | None:
        with self._lock:
            try:
                matches = self._all_operation_assets(
                    operation_id, session_id, agent_run_id, tool_call_id,
                )
            except OSError as exc:
                raise ImageRuntimeError(
                    "generated_asset_store_unavailable",
                    "Generated asset storage is unavailable.",
                    retryable=True,
                    http_status=503,
                ) from exc
            if not matches:
                return None
            expected = int(expected_count)
            indices = [int(item.get("index") or 0) for item in matches]
            if len(matches) != expected or indices != list(range(expected)):
                raise ImageRuntimeError(
                    "image_operation_partial",
                    "A prior image operation left partial durable assets and was not replayed.",
                    outcome_unknown=True,
                )
            return {
                "ok": True,
                "action": "generate_image",
                "count": len(matches),
                "assets": [self.public_asset(meta) for meta in matches],
                "replayed": True,
            }

    def save_operation(
        self,
        operation_id: str,
        session_id: str,
        agent_run_id: str,
        tool_call_id: str,
        images: list[ValidatedImage],
        *,
        created_at: str,
    ) -> dict:
        with self._lock:
            existing = self.find_operation_result(
                operation_id, session_id, agent_run_id, tool_call_id, len(images),
            )
            if existing:
                return existing
            self.root.mkdir(parents=True, exist_ok=True)
            metas = []
            for index, image in enumerate(images):
                asset_id = GENERATED_ASSET_ID_PREFIX + secrets.token_urlsafe(32).rstrip("=")
                final_dir = self._asset_dir(asset_id)
                temp_dir = self.root / (".tmp-" + secrets.token_hex(16))
                temp_dir.mkdir(parents=False, exist_ok=False)
                file_name = f"content.{image.extension}"
                meta = {
                    "schema": GENERATED_ASSET_SCHEMA,
                    "assetId": asset_id,
                    "operationId": operation_id,
                    "sessionId": session_id,
                    "agentRunId": agent_run_id,
                    "toolCallId": tool_call_id,
                    "index": index,
                    "sha256": image.sha256,
                    "mimeType": image.mime_type,
                    "width": image.width,
                    "height": image.height,
                    "byteLength": image.byte_length,
                    "createdAt": created_at,
                    "fileName": file_name,
                }
                try:
                    (temp_dir / file_name).write_bytes(image.data)
                    (temp_dir / "meta.json").write_text(
                        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    temp_dir.replace(final_dir)
                except Exception:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    raise
                metas.append(meta)
            return {
                "ok": True,
                "action": "generate_image",
                "count": len(metas),
                "assets": [self.public_asset(meta) for meta in metas],
            }

    def read(self, session_id: str, asset_id: str) -> tuple[bytes, dict]:
        with self._lock:
            asset_dir = self._asset_dir(asset_id)
            meta = self._read_meta_dir(asset_dir)
            if not meta:
                raise ImageRuntimeError("generated_asset_not_found", "Generated asset was not found.", http_status=404)
            if str(meta.get("sessionId") or "") != str(session_id or ""):
                raise ImageRuntimeError("generated_asset_forbidden", "Generated asset does not belong to this Session.", http_status=403)
            file_path = (asset_dir / str(meta["fileName"])).resolve()
            if asset_dir.resolve() not in file_path.parents or not file_path.is_file():
                raise ImageRuntimeError("generated_asset_not_found", "Generated asset was not found.", http_status=404)
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                raise ImageRuntimeError(
                    "generated_asset_store_unavailable",
                    "Generated asset storage is unavailable.",
                    retryable=True,
                    http_status=503,
                ) from exc
            if len(data) != int(meta.get("byteLength") or -1) or hashlib.sha256(data).hexdigest() != meta.get("sha256"):
                raise ImageRuntimeError("generated_asset_corrupt", "Generated asset integrity check failed.", http_status=409)
            validated = validate_image_bytes(data, str(meta.get("mimeType") or ""))
            if validated.width != int(meta.get("width") or 0) or validated.height != int(meta.get("height") or 0):
                raise ImageRuntimeError("generated_asset_corrupt", "Generated asset metadata does not match its bytes.", http_status=409)
            return data, meta

    def delete_session_assets(self, session_id: str) -> int:
        normalized_session = str(session_id or "")
        if not normalized_session or not self.root.exists():
            return 0
        removed = 0
        try:
            with self._lock:
                for candidate in list(self.root.iterdir()):
                    if not candidate.is_dir() or not self._valid_asset_id(candidate.name):
                        continue
                    meta = self._read_meta_dir(candidate)
                    if not meta or str(meta.get("sessionId") or "") != normalized_session:
                        continue
                    target = candidate.resolve()
                    root = self.root.resolve()
                    if root not in target.parents:
                        raise ImageRuntimeError("generated_asset_cleanup_failed", "Generated asset cleanup target was rejected.")
                    shutil.rmtree(target)
                    removed += 1
        except ImageRuntimeError:
            raise
        except OSError as exc:
            raise ImageRuntimeError(
                "generated_asset_cleanup_failed",
                "Generated asset cleanup could not be completed.",
                retryable=True,
                http_status=503,
            ) from exc
        return removed
