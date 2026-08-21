"""Authoritative context-window resolver for Code AgentRuns (A+B only)."""

from __future__ import annotations

import hashlib
import re
import threading
from urllib import parse

MIN_TOKENS = 1024
MAX_TOKENS = 2_000_000
UNKNOWN_TOKENS = 128_000
METADATA_FIELDS = (
    "context_window", "context_length", "contextWindow",
    "contextWindowTokens", "max_context_tokens", "maxContextTokens",
)
_catalog_lock = threading.RLock()
_catalog: dict[tuple[str, str], dict] = {}


def canonical_model_id(value):
    return str(value or "").strip().removeprefix("models/")


def canonical_base_url(value):
    raw = str(value or "").strip().rstrip("/")
    parsed = parse.urlsplit(raw)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("baseUrl must not contain credentials")
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        raise ValueError("baseUrl must be an absolute http or https URL")
    port = parsed.port
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    authority = host if port is None else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return parse.urlunsplit((scheme, authority, path, "", ""))


def connection_id(base_url):
    value = canonical_base_url(base_url)
    return hashlib.sha256(f"code-connection/v1\0{value}".encode()).hexdigest()


def family_resolution(model):
    normalized = canonical_model_id(model).lower().replace("_", "-")
    match = re.search(r"claude.*?(\d+)[.-](\d+)", normalized)
    if match:
        major, minor = map(int, match.groups())
        return (
            1_000_000 if major >= 5 or (major == 4 and minor >= 6) else 200_000,
            "family",
        )
    if re.search(r"claude|opus|sonnet|haiku", normalized): return 200_000, "family"
    if re.search(r"gpt-4\.1|gpt-5[.-][2-9]", normalized): return 1_000_000, "family"
    if re.search(r"gpt|o1|o3|o4|openai", normalized): return 128_000, "family"
    if re.search(r"deepseek.*v4", normalized): return 1_000_000, "family"
    if "deepseek" in normalized: return 128_000, "family"
    if "gemini" in normalized: return 1_000_000, "family"
    return UNKNOWN_TOKENS, "unknown"


def family_limit(model):
    return family_resolution(model)[0]


def normalize_metadata(item):
    values = []
    for field in METADATA_FIELDS:
        value = item.get(field) if isinstance(item, dict) else None
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if MIN_TOKENS <= value <= MAX_TOKENS:
            values.append(value)
    if not values:
        return None, "missing"
    return min(values), "conflict" if len(set(values)) > 1 else "valid"


def normalize_catalog(base_url, items):
    cid = connection_id(base_url)
    output = []
    with _catalog_lock:
        for raw in items if isinstance(items, list) else []:
            model = canonical_model_id(raw.get("id") if isinstance(raw, dict) else "")
            if not model:
                continue
            metadata, status = normalize_metadata(raw)
            estimate, estimate_source = family_resolution(model)
            candidate = metadata if metadata is not None else estimate
            candidate_hard = metadata is not None
            candidate_source = "metadata" if candidate_hard else estimate_source
            key = (cid, model.lower())
            previous = _catalog.get(key)
            if previous:
                previous_tokens = previous["contextWindowTokens"]
                if previous_tokens < candidate:
                    candidate = previous_tokens
                    candidate_hard = previous["hard"]
                    candidate_source = previous["contextWindowSource"]
                elif previous_tokens == candidate and previous["hard"]:
                    candidate_hard = True
                    candidate_source = "metadata"
                if previous_tokens != (metadata if metadata is not None else estimate):
                    status = "conflict"
            entry = {
                "id": model,
                "contextWindowTokens": candidate,
                "contextWindowSource": candidate_source,
                "contextWindowHard": candidate_hard,
                "metadataStatus": status,
                "connectionId": cid,
            }
            _catalog[key] = {**entry, "hard": entry["contextWindowHard"]}
            output.append({**raw, **entry})
    return output


def resolve(model, base_url, *, budget=None, legacy_hint=None, max_tokens=4096):
    model_id = canonical_model_id(model)
    cid = connection_id(base_url)
    with _catalog_lock:
        catalog = dict(_catalog.get((cid, model_id.lower())) or {})
    estimated_capability, estimated_source = family_resolution(model_id)
    capability = int(catalog.get("contextWindowTokens") or estimated_capability)
    hard = bool(catalog.get("hard"))
    source = str(catalog.get("contextWindowSource") or estimated_source)
    normalized_budget = None
    if budget not in (None, "", "auto"):
        if isinstance(budget, bool) or not isinstance(budget, int):
            raise ValueError("contextBudgetTokens must be an integer or auto")
        if not MIN_TOKENS <= budget <= MAX_TOKENS:
            raise ValueError("contextBudgetTokens is out of range")
        normalized_budget = budget
    final_limit = capability if normalized_budget is None else normalized_budget
    clamped = False
    attempted = False
    if hard and final_limit > capability:
        final_limit, clamped = capability, True
    elif not hard and final_limit > capability:
        attempted = True
    if legacy_hint not in (None, ""):
        if isinstance(legacy_hint, bool) or not isinstance(legacy_hint, int):
            raise ValueError("contextLimit must be an integer")
        if not MIN_TOKENS <= legacy_hint <= MAX_TOKENS:
            raise ValueError("contextLimit is out of range")
        final_limit = min(final_limit, legacy_hint)
    if isinstance(max_tokens, bool):
        raise ValueError("max_tokens must be a non-negative integer")
    try:
        max_output = int(max_tokens or 0)
    except (TypeError, ValueError):
        raise ValueError("max_tokens must be a non-negative integer")
    if max_output < 0 or max_output > MAX_TOKENS:
        raise ValueError("max_tokens must be a non-negative integer")
    safety = max(4096, int(final_limit * 0.05))
    raw_available = final_limit - max_output - safety
    available = max(1024, raw_available)
    return {
        "connectionId": cid,
        "contextWindowTokens": capability,
        "contextWindowSource": source,
        "contextWindowHard": hard,
        "contextBudgetTokens": normalized_budget,
        "contextLimit": final_limit,
        "safetyMarginTokens": safety,
        "availableInputTokens": available,
        "compressionTriggerTokens": min(int(final_limit * 0.90), available),
        "inputBudgetInsufficient": raw_available < 1024,
        "budgetClamped": clamped,
        "budgetAboveEstimate": attempted,
    }
