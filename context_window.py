"""Authoritative context-window resolver for Code AgentRuns (A+B+C2)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
from urllib import parse

from official_model_capabilities import CATALOG_JSON

MIN_TOKENS = 1024
MAX_TOKENS = 2_000_000
UNKNOWN_TOKENS = 128_000
OFFICIAL_CATALOG_SCHEMA = "code-official-model-capabilities/v1"
OFFICIAL_SOURCE_HOSTS = {
    "openai": {"developers.openai.com"},
    "anthropic": {"platform.claude.com"},
    "google": {"ai.google.dev"},
    "xai": {"docs.x.ai"},
    "deepseek": {"api-docs.deepseek.com"},
    "kimi": {"platform.kimi.com"},
    "qwen": {"help.aliyun.com"},
}
METADATA_FIELDS = (
    "context_window", "context_length", "contextWindow",
    "contextWindowTokens", "max_context_tokens", "maxContextTokens",
)
_catalog_lock = threading.RLock()
_catalog: dict[tuple[str, str], dict] = {}
_official_catalog = None
_official_catalog_error = ""


def canonical_model_id(value):
    return str(value or "").strip().removeprefix("models/")


def _catalog_date(value, field):
    try:
        return dt.date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise ValueError(f"official catalog {field} must be an ISO date") from exc


def _catalog_token(value, field, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"official catalog {field} must be an integer")
    if not MIN_TOKENS <= value <= MAX_TOKENS:
        raise ValueError(f"official catalog {field} is out of range")
    return value


def _catalog_id(value, field):
    model_id = str(value or "").strip()
    if (
        not model_id
        or model_id != canonical_model_id(model_id)
        or "/" in model_id
        or ":" in model_id
    ):
        raise ValueError(f"official catalog {field} must be an exact canonical model ID")
    return model_id


def _validate_official_catalog(data):
    if not isinstance(data, dict) or data.get("schema") != OFFICIAL_CATALOG_SCHEMA:
        raise ValueError("official catalog schema is invalid")
    revision = str(data.get("catalogRevision") or "").strip()
    if not revision:
        raise ValueError("official catalog revision is required")
    verified_at = _catalog_date(data.get("verifiedAt"), "verifiedAt")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("official catalog entries must be a non-empty array")

    entries = []
    lookup = {}
    identities = {}
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"official catalog entry {index} must be an object")
        provider = str(raw.get("provider") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", provider):
            raise ValueError(f"official catalog entry {index} provider is invalid")
        model_id = _catalog_id(raw.get("modelId"), f"entry {index} modelId")
        status = str(raw.get("status") or "")
        if status not in {"active", "research_pending"}:
            raise ValueError(f"official catalog entry {index} status is invalid")
        context_tokens = _catalog_token(
            raw.get("contextWindowTokens"),
            f"entry {index} contextWindowTokens",
            nullable=status == "research_pending",
        )
        if status == "active" and context_tokens is None:
            raise ValueError(f"official catalog entry {index} active value is missing")
        if status == "research_pending" and context_tokens is not None:
            raise ValueError(f"official catalog entry {index} pending value must be null")
        max_output_tokens = _catalog_token(
            raw.get("maxOutputTokens"),
            f"entry {index} maxOutputTokens",
            nullable=True,
        )
        source_url = str(raw.get("sourceUrl") or "").strip()
        source = parse.urlsplit(source_url)
        if source.scheme != "https" or not source.hostname or source.username or source.password:
            raise ValueError(f"official catalog entry {index} sourceUrl is invalid")
        if source.hostname.lower() not in OFFICIAL_SOURCE_HOSTS.get(provider, set()):
            raise ValueError(f"official catalog entry {index} source host is invalid")
        as_of = _catalog_date(raw.get("asOf"), f"entry {index} asOf")
        if as_of > verified_at:
            raise ValueError(f"official catalog entry {index} asOf exceeds verifiedAt")
        confidence = str(raw.get("confidence") or "")
        if confidence not in {"official_direct", "official_label_only"}:
            raise ValueError(f"official catalog entry {index} confidence is invalid")
        max_age_days = raw.get("maxAgeDays")
        if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
            raise ValueError(f"official catalog entry {index} maxAgeDays must be an integer")
        if not 1 <= max_age_days <= 365:
            raise ValueError(f"official catalog entry {index} maxAgeDays is out of range")
        conditions = raw.get("conditions")
        if not isinstance(conditions, list) or any(not isinstance(item, str) for item in conditions):
            raise ValueError(f"official catalog entry {index} conditions must be strings")
        alias_ambiguity = str(raw.get("aliasAmbiguity") or "").strip()
        if not alias_ambiguity:
            raise ValueError(f"official catalog entry {index} aliasAmbiguity is required")
        valid_until = raw.get("validUntil")
        if valid_until is not None:
            valid_until = _catalog_date(valid_until, f"entry {index} validUntil")
        official_label = str(raw.get("officialLabel") or "").strip()
        if status == "research_pending" and (
            confidence != "official_label_only" or not official_label
        ):
            raise ValueError(
                f"official catalog entry {index} pending evidence is incomplete"
            )
        if status == "active" and confidence != "official_direct":
            raise ValueError(f"official catalog entry {index} active confidence is invalid")

        aliases = []
        raw_aliases = raw.get("aliases")
        if not isinstance(raw_aliases, list):
            raise ValueError(f"official catalog entry {index} aliases must be an array")
        for alias_index, raw_alias in enumerate(raw_aliases):
            if not isinstance(raw_alias, dict):
                raise ValueError(f"official catalog entry {index} alias {alias_index} is invalid")
            alias_id = _catalog_id(
                raw_alias.get("id"), f"entry {index} alias {alias_index} id",
            )
            moving = raw_alias.get("moving")
            if not isinstance(moving, bool):
                raise ValueError(f"official catalog entry {index} alias {alias_index} moving is invalid")
            alias_max_age = raw_alias.get("maxAgeDays", max_age_days)
            if isinstance(alias_max_age, bool) or not isinstance(alias_max_age, int):
                raise ValueError(f"official catalog entry {index} alias {alias_index} maxAgeDays is invalid")
            if not 1 <= alias_max_age <= max_age_days:
                raise ValueError(f"official catalog entry {index} alias {alias_index} maxAgeDays is out of range")
            aliases.append({
                "id": alias_id,
                "moving": moving,
                "maxAgeDays": alias_max_age,
            })

        entry = {
            "provider": provider,
            "modelId": model_id,
            "aliases": aliases,
            "contextWindowTokens": context_tokens,
            "maxOutputTokens": max_output_tokens,
            "officialLabel": official_label,
            "sourceUrl": source_url,
            "asOf": as_of,
            "confidence": confidence,
            "status": status,
            "maxAgeDays": max_age_days,
            "aliasAmbiguity": alias_ambiguity,
            "conditions": list(conditions),
            "validUntil": valid_until,
        }
        entries.append(entry)
        for identity, alias in [(model_id, None), *((item["id"], item) for item in aliases)]:
            key = identity.lower()
            previous = identities.get(key)
            if previous is not None:
                raise ValueError(
                    f"official catalog duplicate model ID {identity!r} across "
                    f"{previous!r} and {provider!r}"
                )
            identities[key] = provider
            if status == "active":
                lookup[key] = {"entry": entry, "alias": alias}

    return {
        "schema": OFFICIAL_CATALOG_SCHEMA,
        "catalogRevision": revision,
        "verifiedAt": verified_at,
        "entries": tuple(entries),
        "lookup": lookup,
    }


def load_official_catalog(*, data=None):
    if data is None:
        data = json.loads(CATALOG_JSON)
    return _validate_official_catalog(data)


def official_catalog_status():
    return {
        "available": _official_catalog is not None,
        "error": _official_catalog_error,
        "catalogRevision": str((_official_catalog or {}).get("catalogRevision") or ""),
        "entryCount": len((_official_catalog or {}).get("entries") or ()),
    }


def official_resolution(model, *, today=None):
    catalog = _official_catalog
    if not catalog:
        return None
    model_id = canonical_model_id(model)
    match = catalog["lookup"].get(model_id.lower())
    if not match:
        return None
    current_date = today or dt.datetime.now(dt.timezone.utc).date()
    if isinstance(current_date, dt.datetime):
        current_date = current_date.date()
    if not isinstance(current_date, dt.date):
        raise ValueError("official catalog resolution date is invalid")
    entry = match["entry"]
    age_days = max(0, (current_date - entry["asOf"]).days)
    alias = match["alias"]
    if alias and alias["moving"] and age_days > alias["maxAgeDays"]:
        return None
    source = "stale_official" if age_days > entry["maxAgeDays"] else "official"
    return {
        "contextWindowTokens": entry["contextWindowTokens"],
        "contextWindowSource": source,
        "contextWindowHard": False,
        "maxOutputTokens": entry["maxOutputTokens"],
        "officialProvider": entry["provider"],
        "officialCatalogRevision": catalog["catalogRevision"],
        "officialSourceUrl": entry["sourceUrl"],
    }


try:
    _official_catalog = load_official_catalog()
except (json.JSONDecodeError, ValueError) as exc:
    _official_catalog = None
    _official_catalog_error = str(exc)


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


def _candidate_priority(candidate):
    if candidate.get("hard"):
        return 100
    return {
        "official": 40,
        "stale_official": 39,
        "family": 20,
        "unknown": 10,
    }.get(str(candidate.get("contextWindowSource") or ""), 0)


def _merge_catalog_candidate(previous, candidate):
    if not previous:
        return dict(candidate)
    previous_priority = _candidate_priority(previous)
    candidate_priority = _candidate_priority(candidate)
    if candidate_priority != previous_priority:
        return dict(candidate if candidate_priority > previous_priority else previous)
    previous_tokens = int(previous["contextWindowTokens"])
    candidate_tokens = int(candidate["contextWindowTokens"])
    winner = candidate if candidate_tokens < previous_tokens else previous
    merged = dict(winner)
    if previous_tokens != candidate_tokens:
        merged["metadataStatus"] = "conflict"
    return merged


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
            official = official_resolution(model)
            estimate, estimate_source = family_resolution(model)
            if metadata is not None:
                candidate = {
                    "contextWindowTokens": metadata,
                    "contextWindowSource": "metadata",
                    "contextWindowHard": True,
                    "hard": True,
                    "maxOutputTokens": None,
                    "metadataStatus": status,
                }
            elif official:
                candidate = {
                    **official,
                    "hard": False,
                    "metadataStatus": status,
                }
            else:
                candidate = {
                    "contextWindowTokens": estimate,
                    "contextWindowSource": estimate_source,
                    "contextWindowHard": False,
                    "hard": False,
                    "maxOutputTokens": None,
                    "metadataStatus": status,
                }
            key = (cid, model.lower())
            previous = _catalog.get(key)
            merged = _merge_catalog_candidate(previous, candidate)
            entry = {
                "id": model,
                **{key: value for key, value in merged.items() if key != "hard"},
                "connectionId": cid,
            }
            _catalog[key] = {**entry, "hard": bool(entry["contextWindowHard"])}
            output.append({**raw, **entry})
    return output


def resolve(model, base_url, *, budget=None, legacy_hint=None, max_tokens=4096):
    model_id = canonical_model_id(model)
    cid = connection_id(base_url)
    with _catalog_lock:
        catalog = dict(_catalog.get((cid, model_id.lower())) or {})
    official = official_resolution(model_id)
    if official:
        estimated_capability = int(official["contextWindowTokens"])
        estimated_source = str(official["contextWindowSource"])
    else:
        estimated_capability, estimated_source = family_resolution(model_id)
    catalog_hard = bool(catalog.get("hard"))
    catalog_source = str(catalog.get("contextWindowSource") or "")
    if catalog_hard:
        capability = int(catalog["contextWindowTokens"])
        hard = True
        source = catalog_source or "metadata"
        max_output_tokens = catalog.get("maxOutputTokens")
    elif official:
        capability = estimated_capability
        hard = False
        source = estimated_source
        max_output_tokens = official.get("maxOutputTokens")
    else:
        stale_cached_official = catalog_source in {"official", "stale_official"}
        capability = int(
            estimated_capability
            if stale_cached_official
            else (catalog.get("contextWindowTokens") or estimated_capability)
        )
        hard = False
        source = estimated_source if stale_cached_official else (catalog_source or estimated_source)
        max_output_tokens = None if stale_cached_official else catalog.get("maxOutputTokens")
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
        "maxOutputTokens": max_output_tokens,
        "contextBudgetTokens": normalized_budget,
        "contextLimit": final_limit,
        "safetyMarginTokens": safety,
        "availableInputTokens": available,
        "compressionTriggerTokens": min(int(final_limit * 0.90), available),
        "inputBudgetInsufficient": raw_available < 1024,
        "budgetClamped": clamped,
        "budgetAboveEstimate": attempted,
    }
