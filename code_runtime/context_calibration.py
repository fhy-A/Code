"""Strict context-error evidence and key-scoped calibration storage.

The module deliberately has no dependency on AgentRun or HTTP state.  Raw API
keys and base URLs are accepted only long enough to derive irreversible scope
identifiers; neither value is returned by the public helpers or written to the
runtime data file.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from . import context_window


SCHEMA = "code-context-calibration/v1"
KEY_FINGERPRINT_DOMAIN = "code-context-key/v1\0"
SCOPE_DOMAIN = "code-context-calibration-scope/v1\0"
EXPLICIT_TTL = dt.timedelta(days=30)
HEURISTIC_TTL = dt.timedelta(days=7)
MAX_OBSERVATIONS_PER_SCOPE = 8
MAX_SCOPES = 4096
CALIBRATION_LADDER = (
    2_000_000,
    1_050_000,
    1_000_000,
    400_000,
    256_000,
    200_000,
    128_000,
    64_000,
    32_000,
    16_000,
)
CONTEXT_HTTP_STATUSES = frozenset({400, 413, 422})
CONTEXT_ERROR_CODES = frozenset({
    "context_length_exceeded",
    "context_window_exceeded",
    "max_context_length_exceeded",
    "maximum_context_length_exceeded",
})
STRUCTURED_MAXIMUM_FIELDS = (
    "max_context_tokens",
    "maximum_context_tokens",
    "context_window",
    "context_length",
    "maxContextTokens",
    "maximumContextTokens",
    "contextWindowTokens",
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_PHRASES = (
    re.compile(r"\bcontext[_ -]length[_ -]exceeded\b", re.IGNORECASE),
    re.compile(r"\bcontext[_ -]window[_ -]exceeded\b", re.IGNORECASE),
    re.compile(r"\b(?:maximum|max)\s+context\s+(?:length|window)\b", re.IGNORECASE),
    re.compile(r"\bcontext\s+(?:length|window)\s+(?:was\s+)?exceeded\b", re.IGNORECASE),
    re.compile(r"\bprompt\s+is\s+too\s+long\s+for\s+(?:this\s+)?(?:model|context\s+window)\b", re.IGNORECASE),
    re.compile(r"\brequest\s+has\s+too\s+many\s+tokens\s+for\s+(?:the\s+)?context\s+window\b", re.IGNORECASE),
)
_MAXIMUM_PATTERNS = (
    re.compile(
        r"\b(?:maximum|max)\s+context\s+(?:length|window)"
        r"(?:\s+(?:is|of|=|:))?\s*([1-9][0-9,]{3,9})\s*tokens?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcontext\s+(?:length|window)\s+(?:has\s+)?(?:a\s+)?"
        r"(?:maximum|max|limit)(?:\s+(?:is|of|=|:))?\s*"
        r"([1-9][0-9,]{3,9})\s*tokens?\b",
        re.IGNORECASE,
    ),
)
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


class CalibrationStorageUnavailable(RuntimeError):
    """Raised when a mutation cannot safely use the calibration store."""


@dataclass(frozen=True)
class CalibrationReadResult:
    storage_status: str
    document: dict | None
    error: str = ""

    @property
    def available(self) -> bool:
        return self.storage_status in {"missing", "ok"}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _as_utc(value: dt.datetime) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_iso(value, field: str) -> dt.datetime:
    text = str(value or "")
    if not text.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp") from exc
    return _as_utc(parsed)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def key_fingerprint(raw_key) -> str:
    key = str(raw_key or "")
    if not key:
        raise ValueError("key is required")
    return _sha256(KEY_FINGERPRINT_DOMAIN + key)


def calibration_scope(base_url, raw_key, model) -> dict:
    connection_id = context_window.connection_id(base_url)
    fingerprint = key_fingerprint(raw_key)
    model_id = context_window.canonical_model_id(model).strip().lower()
    if not model_id or len(model_id) > 256:
        raise ValueError("model is required and must not exceed 256 characters")
    scope_id = _sha256(
        SCOPE_DOMAIN + connection_id + "\0" + fingerprint + "\0" + model_id
    )
    return normalize_calibration_scope({
        "scopeId": scope_id,
        "connectionId": connection_id,
        "keyFingerprint": fingerprint,
        "modelId": model_id,
    })


def normalize_calibration_scope(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    allowed = {"scopeId", "connectionId", "keyFingerprint", "modelId"}
    if set(value) - allowed:
        return None
    scope_id = str(value.get("scopeId") or "")
    connection_id = str(value.get("connectionId") or "")
    fingerprint = str(value.get("keyFingerprint") or "")
    model_id = str(value.get("modelId") or "")
    if (
        not _HEX_64.fullmatch(scope_id)
        or not _HEX_64.fullmatch(connection_id)
        or not _HEX_64.fullmatch(fingerprint)
        or not model_id
        or len(model_id) > 256
        or scope_id != _sha256(
            SCOPE_DOMAIN + connection_id + "\0" + fingerprint + "\0" + model_id
        )
    ):
        return None
    return {
        "scopeId": scope_id,
        "connectionId": connection_id,
        "keyFingerprint": fingerprint,
        "modelId": model_id,
    }


def _structured_error(payload) -> dict:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("error")
    return nested if isinstance(nested, dict) else payload


def _structured_codes(payload, explicit_code="") -> set[str]:
    values = {str(explicit_code or "").strip().lower()}
    if isinstance(payload, dict):
        for source in (payload, _structured_error(payload)):
            for field in ("code", "type"):
                values.add(str(source.get(field) or "").strip().lower())
    values.discard("")
    return values


def _bounded_token(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        token = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9,]*", value.strip()):
        token = int(value.replace(",", ""))
    else:
        return None
    if context_window.MIN_TOKENS <= token <= context_window.MAX_TOKENS:
        return token
    return None


def _explicit_maximum_candidates(payload, message) -> list[int]:
    candidates = []
    structured = _structured_error(payload)
    for field in STRUCTURED_MAXIMUM_FIELDS:
        token = _bounded_token(structured.get(field))
        if token is not None:
            candidates.append(token)
    text = str(message or "")
    for pattern in _MAXIMUM_PATTERNS:
        for match in pattern.finditer(text):
            token = _bounded_token(match.group(1))
            if token is not None:
                candidates.append(token)
    return candidates


def classify_context_failure(status=0, *, payload=None, code="", message="") -> dict:
    """Return strict, sanitized learning evidence for a context-length failure."""
    numeric_status = int(status or 0)
    codes = _structured_codes(payload, code)
    text = str(message or "")
    matched = (
        numeric_status in CONTEXT_HTTP_STATUSES
        and (
            bool(codes & CONTEXT_ERROR_CODES)
            or any(pattern.search(text) for pattern in _CONTEXT_PHRASES)
        )
    )
    if not matched:
        return {
            "matched": False,
            "errorCode": "",
            "evidenceKind": "",
            "explicitMaximumTokens": None,
            "numericConflict": False,
        }
    candidates = _explicit_maximum_candidates(payload, text)
    unique = sorted(set(candidates))
    explicit = unique[0] if len(unique) == 1 else None
    return {
        "matched": True,
        "errorCode": "context_window_exceeded",
        "evidenceKind": "explicit_max" if explicit is not None else "heuristic",
        "explicitMaximumTokens": explicit,
        "numericConflict": len(unique) > 1,
    }


def context_failure_attribution(scope, status, classification) -> dict | None:
    """Build the only credential-free context-failure record persisted by D1."""
    if not isinstance(scope, dict) or not isinstance(classification, dict):
        return None
    if not classification.get("matched"):
        return None
    value = {
        "scopeId": str(scope.get("scopeId") or ""),
        "connectionId": str(scope.get("connectionId") or ""),
        "keyFingerprint": str(scope.get("keyFingerprint") or ""),
        "modelId": str(scope.get("modelId") or ""),
        "upstreamStatus": int(status or 0),
        "errorCode": "context_window_exceeded",
        "evidenceKind": str(classification.get("evidenceKind") or "heuristic"),
        "explicitMaximumTokens": classification.get("explicitMaximumTokens"),
        "numericConflict": bool(classification.get("numericConflict")),
    }
    return normalize_context_failure_attribution(value)


def calibration_candidate(current_limit, *, explicit_maximum=None, max_tokens=4096) -> dict | None:
    """Choose one strictly lower, input-viable D-lite recovery cap."""
    current = _bounded_token(current_limit)
    if current is None:
        return None
    explicit = _bounded_token(explicit_maximum)
    if explicit is not None and explicit < current:
        candidate = explicit
        evidence_kind = "explicit_max"
    else:
        candidate = next((value for value in CALIBRATION_LADDER if value < current), None)
        evidence_kind = "heuristic"
    if candidate is None:
        return None
    if isinstance(max_tokens, bool):
        return None
    try:
        maximum_output = int(max_tokens or 0)
    except (TypeError, ValueError):
        return None
    if maximum_output < 0 or maximum_output > context_window.MAX_TOKENS:
        return None
    safety = max(4096, int(candidate * 0.05))
    raw_available = candidate - maximum_output - safety
    if raw_available < 1024:
        return None
    return {
        "capTokens": candidate,
        "evidenceKind": evidence_kind,
        "safetyMarginTokens": safety,
        "availableInputTokens": raw_available,
        "compressionTriggerTokens": min(int(candidate * 0.90), raw_available),
    }


def calibration_observation_id(scope_id, agent_run_id, round_number, cap_tokens, evidence_kind) -> str:
    if not _HEX_64.fullmatch(str(scope_id or "")):
        raise ValueError("scopeId is invalid")
    run_id = str(agent_run_id or "")
    if not run_id or len(run_id) > 128:
        raise ValueError("agentRunId is invalid")
    try:
        round_value = int(round_number)
    except (TypeError, ValueError) as exc:
        raise ValueError("round is invalid") from exc
    cap = _bounded_token(cap_tokens)
    kind = str(evidence_kind or "")
    if round_value < 1 or cap is None or kind not in {"explicit_max", "heuristic"}:
        raise ValueError("calibration observation facts are invalid")
    return _sha256(
        "code-context-calibration-observation/v1\0"
        + str(scope_id) + "\0" + run_id + "\0" + str(round_value)
        + "\0" + str(cap) + "\0" + kind
    )


def calibration_expiry(evidence_kind, verified_at) -> str:
    kind = str(evidence_kind or "")
    ttl = {"explicit_max": EXPLICIT_TTL, "heuristic": HEURISTIC_TTL}.get(kind)
    if ttl is None:
        raise ValueError("evidenceKind is invalid")
    return _iso(_as_utc(verified_at) + ttl)


def normalize_context_failure_attribution(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        "scopeId", "connectionId", "keyFingerprint", "modelId",
        "upstreamStatus", "errorCode", "evidenceKind",
        "explicitMaximumTokens", "numericConflict",
    }
    if set(value) - allowed:
        return None
    scope = normalize_calibration_scope({
        field: value.get(field)
        for field in ("scopeId", "connectionId", "keyFingerprint", "modelId")
    })
    if not scope:
        return None
    try:
        status = int(value.get("upstreamStatus") or 0)
    except (TypeError, ValueError):
        return None
    if status not in CONTEXT_HTTP_STATUSES:
        return None
    evidence_kind = str(value.get("evidenceKind") or "")
    if evidence_kind not in {"explicit_max", "heuristic"}:
        return None
    explicit = value.get("explicitMaximumTokens")
    if explicit is not None:
        explicit = _bounded_token(explicit)
        if explicit is None:
            return None
    if evidence_kind == "explicit_max" and explicit is None:
        return None
    if evidence_kind == "heuristic" and explicit is not None:
        return None
    return {
        **scope,
        "upstreamStatus": status,
        "errorCode": "context_window_exceeded",
        "evidenceKind": evidence_kind,
        "explicitMaximumTokens": explicit,
        "numericConflict": bool(value.get("numericConflict")),
    }


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_file(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0, os.SEEK_END)
        if file_obj.tell() == 0:
            file_obj.write(b"\0")
            file_obj.flush()
            os.fsync(file_obj.fileno())
        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)


def _unlock_file(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _empty_document(now: dt.datetime) -> dict:
    return {
        "schema": SCHEMA,
        "revision": 0,
        "updatedAt": _iso(now),
        "scopes": {},
    }


def _require_fields(value: dict, allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{field} contains unknown fields: {', '.join(unknown)}")


def _validate_document(value) -> dict:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("calibration schema is invalid")
    _require_fields(value, {"schema", "revision", "updatedAt", "scopes"}, "document")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("calibration revision is invalid")
    _parse_iso(value.get("updatedAt"), "updatedAt")
    raw_scopes = value.get("scopes")
    if not isinstance(raw_scopes, dict) or len(raw_scopes) > MAX_SCOPES:
        raise ValueError("calibration scopes are invalid")
    scopes = {}
    for scope_id, raw_scope in raw_scopes.items():
        if not _HEX_64.fullmatch(str(scope_id or "")) or not isinstance(raw_scope, dict):
            raise ValueError("calibration scope identity is invalid")
        _require_fields(
            raw_scope,
            {"scopeId", "connectionId", "keyFingerprint", "modelId", "observations"},
            "scope",
        )
        if str(raw_scope.get("scopeId") or "") != scope_id:
            raise ValueError("calibration scope identity is inconsistent")
        connection_id = str(raw_scope.get("connectionId") or "")
        fingerprint = str(raw_scope.get("keyFingerprint") or "")
        model_id = str(raw_scope.get("modelId") or "")
        expected_scope = _sha256(
            SCOPE_DOMAIN + connection_id + "\0" + fingerprint + "\0" + model_id
        )
        if (
            not _HEX_64.fullmatch(connection_id)
            or not _HEX_64.fullmatch(fingerprint)
            or expected_scope != scope_id
            or not model_id
            or len(model_id) > 256
        ):
            raise ValueError("calibration scope binding is invalid")
        raw_observations = raw_scope.get("observations")
        if not isinstance(raw_observations, list) or len(raw_observations) > MAX_OBSERVATIONS_PER_SCOPE:
            raise ValueError("calibration observations are invalid")
        observations = []
        seen = set()
        for raw_observation in raw_observations:
            if not isinstance(raw_observation, dict):
                raise ValueError("calibration observation is invalid")
            _require_fields(
                raw_observation,
                {"observationId", "capTokens", "evidenceKind", "verifiedAt", "expiresAt"},
                "observation",
            )
            observation_id = str(raw_observation.get("observationId") or "")
            if not _HEX_64.fullmatch(observation_id) or observation_id in seen:
                raise ValueError("calibration observation identity is invalid")
            seen.add(observation_id)
            cap_tokens = _bounded_token(raw_observation.get("capTokens"))
            if cap_tokens is None:
                raise ValueError("calibration cap is invalid")
            evidence_kind = str(raw_observation.get("evidenceKind") or "")
            ttl = {"explicit_max": EXPLICIT_TTL, "heuristic": HEURISTIC_TTL}.get(evidence_kind)
            if ttl is None:
                raise ValueError("calibration evidence kind is invalid")
            verified_at = _parse_iso(raw_observation.get("verifiedAt"), "verifiedAt")
            expires_at = _parse_iso(raw_observation.get("expiresAt"), "expiresAt")
            if expires_at - verified_at != ttl:
                raise ValueError("calibration TTL is invalid")
            observations.append({
                "observationId": observation_id,
                "capTokens": cap_tokens,
                "evidenceKind": evidence_kind,
                "verifiedAt": _iso(verified_at),
                "expiresAt": _iso(expires_at),
            })
        scopes[scope_id] = {
            "scopeId": scope_id,
            "connectionId": connection_id,
            "keyFingerprint": fingerprint,
            "modelId": model_id,
            "observations": observations,
        }
    return {
        "schema": SCHEMA,
        "revision": revision,
        "updatedAt": str(value["updatedAt"]),
        "scopes": scopes,
    }


class ContextCalibrationStore:
    def __init__(self, data_dir, *, clock=None):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "context-calibrations.json"
        self.lock_path = self.data_dir / "context-calibrations.lock"
        self.clock = clock or _utc_now

    def _now(self) -> dt.datetime:
        return _as_utc(self.clock())

    def read(self) -> CalibrationReadResult:
        try:
            payload = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return CalibrationReadResult("missing", _empty_document(self._now()))
        except OSError as exc:
            return CalibrationReadResult("corrupted", None, str(exc)[:240])
        try:
            return CalibrationReadResult("ok", _validate_document(json.loads(payload)))
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return CalibrationReadResult("corrupted", None, str(exc)[:240])

    @contextmanager
    def _mutation_lock(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        local_lock = _thread_lock(self.lock_path)
        with local_lock:
            with open(self.lock_path, "a+b") as lock_file:
                _lock_file(lock_file)
                try:
                    yield
                finally:
                    _unlock_file(lock_file)

    def _atomic_write(self, document: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            try:
                directory_fd = os.open(self.data_dir, os.O_RDONLY)
            except OSError:
                directory_fd = -1
            if directory_fd >= 0:
                try:
                    os.fsync(directory_fd)
                except OSError:
                    pass
                finally:
                    os.close(directory_fd)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def resolve(self, scope_id, *, now=None) -> dict:
        read_result = self.read()
        if not read_result.available:
            return {
                "storageStatus": read_result.storage_status,
                "capTokens": None,
                "observationCount": 0,
            }
        current = _as_utc(now) if now is not None else self._now()
        scope = (read_result.document.get("scopes") or {}).get(str(scope_id or ""))
        active = [] if not scope else [
            observation
            for observation in scope.get("observations") or []
            if _parse_iso(observation["expiresAt"], "expiresAt") > current
        ]
        winner = min(
            active,
            key=lambda item: (
                item["capTokens"],
                -_parse_iso(item["expiresAt"], "expiresAt").timestamp(),
            ),
            default=None,
        )
        return {
            "storageStatus": read_result.storage_status,
            "capTokens": winner["capTokens"] if winner else None,
            "evidenceKind": winner["evidenceKind"] if winner else "",
            "expiresAt": winner["expiresAt"] if winner else "",
            "observationCount": len(active),
        }

    def record_success(
        self,
        scope,
        *,
        cap_tokens,
        evidence_kind,
        observation_id,
        now=None,
    ) -> dict:
        normalized_scope = _validate_document({
            "schema": SCHEMA,
            "revision": 0,
            "updatedAt": _iso(self._now()),
            "scopes": {
                str(scope.get("scopeId") or ""): {
                    **dict(scope),
                    "observations": [],
                },
            },
        })["scopes"]
        scope_id, scope_record = next(iter(normalized_scope.items()))
        cap = _bounded_token(cap_tokens)
        if cap is None:
            raise ValueError("capTokens is invalid")
        kind = str(evidence_kind or "")
        ttl = {"explicit_max": EXPLICIT_TTL, "heuristic": HEURISTIC_TTL}.get(kind)
        if ttl is None:
            raise ValueError("evidenceKind is invalid")
        observation_id = str(observation_id or "")
        if not _HEX_64.fullmatch(observation_id):
            raise ValueError("observationId is invalid")
        verified_at = _as_utc(now) if now is not None else self._now()
        observation = {
            "observationId": observation_id,
            "capTokens": cap,
            "evidenceKind": kind,
            "verifiedAt": _iso(verified_at),
            "expiresAt": _iso(verified_at + ttl),
        }
        with self._mutation_lock():
            read_result = self.read()
            if not read_result.available:
                raise CalibrationStorageUnavailable("storage_unavailable")
            document = read_result.document
            existing_scope = (document.get("scopes") or {}).get(scope_id)
            if existing_scope and any(
                existing_scope[field] != scope_record[field]
                for field in ("connectionId", "keyFingerprint", "modelId")
            ):
                raise CalibrationStorageUnavailable("scope binding conflict")
            target = dict(existing_scope or scope_record)
            observations = list(target.get("observations") or [])
            existing = next((item for item in observations if item["observationId"] == observation_id), None)
            if existing is not None:
                if (
                    existing["capTokens"] != observation["capTokens"]
                    or existing["evidenceKind"] != observation["evidenceKind"]
                ):
                    raise CalibrationStorageUnavailable("observation identity conflict")
                return dict(existing)
            observations.append(observation)
            current = verified_at
            observations = [
                item for item in observations
                if _parse_iso(item["expiresAt"], "expiresAt") > current
            ]
            if len(observations) > MAX_OBSERVATIONS_PER_SCOPE:
                minimum = min(observations, key=lambda item: item["capTokens"])
                newest = sorted(
                    observations,
                    key=lambda item: item["verifiedAt"],
                    reverse=True,
                )
                observations = [minimum] + [
                    item for item in newest
                    if item["observationId"] != minimum["observationId"]
                ][:MAX_OBSERVATIONS_PER_SCOPE - 1]
            target["observations"] = observations
            document["scopes"][scope_id] = target
            document["revision"] = int(document.get("revision") or 0) + 1
            document["updatedAt"] = _iso(verified_at)
            validated = _validate_document(document)
            try:
                self._atomic_write(validated)
            except OSError as exc:
                raise CalibrationStorageUnavailable("storage_unavailable") from exc
        return dict(observation)

    def reset(self, scope_id=None, *, now=None) -> bool:
        with self._mutation_lock():
            read_result = self.read()
            if not read_result.available:
                raise CalibrationStorageUnavailable("storage_unavailable")
            document = read_result.document
            scopes = document["scopes"]
            if scope_id is None:
                changed = bool(scopes)
                scopes.clear()
            else:
                changed = scopes.pop(str(scope_id), None) is not None
            if not changed:
                return False
            timestamp = _as_utc(now) if now is not None else self._now()
            document["revision"] = int(document.get("revision") or 0) + 1
            document["updatedAt"] = _iso(timestamp)
            try:
                self._atomic_write(_validate_document(document))
            except OSError as exc:
                raise CalibrationStorageUnavailable("storage_unavailable") from exc
            return True
