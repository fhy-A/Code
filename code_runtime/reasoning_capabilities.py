"""Exact model reasoning contracts; no credentials, network probes or alias guessing."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from urllib.parse import urlsplit
from datetime import datetime, timezone
from .reasoning_catalog import MODELS, PROFILES, SOURCE_COMMIT

REVISION = "reasoning-static-2026-09-09-v1:" + SOURCE_COMMIT
INTENTS = ("default", "low", "medium", "high")
MANAGED_FIELDS = frozenset({
    "reasoning_effort", "reasoning", "thinking", "output_config",
    "enable_thinking", "thinking_budget",
})
# Exact public IDs only. Additional o-models await an exact parameter contract.


class ReasoningError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

    def public_payload(self):
        return {"error": self.code, "errorCode": self.code, "retryable": False}


def transport_profile(base_url):
    """Only the native HTTPS endpoint proves this transport, never a model name."""
    try:
        url = urlsplit(str(base_url or ""))
        native = (url.scheme == "https" and url.hostname == "api.openai.com"
                  and url.port in (None, 443) and not url.username and not url.password
                  and not url.query and not url.fragment
                  and url.path.rstrip("/") in ("", "/v1"))
    except ValueError:
        native = False
    return "openai-chat-native-v1" if native else "unknown"


def reviewed_profile(model_id, base_url, contract):
    model = MODELS.get(model_id)
    if not model:
        return "unknown"
    native = transport_profile(base_url)
    if native == "openai-chat-native-v1" and model["provider"] == "openai":
        return native
    try:
        url = urlsplit(base_url)
        host = {"deepseek": "api.deepseek.com", "anthropic": "api.anthropic.com"}.get(model["provider"])
        if (host and url.scheme == "https" and url.hostname == host and url.port in (None, 443)
                and not url.username and not url.password and not url.query and not url.fragment
                and url.path.rstrip("/") in ("", "/v1")):
            return model["adapter"]
        if (contract and contract["adapterProfile"] == model["adapter"]
                and contract["modelId"] == model_id
                and datetime.fromisoformat(contract["expiresAt"].replace("Z", "+00:00")) > datetime.now(timezone.utc)):
            return model["adapter"]
    except (ValueError, TypeError, KeyError):
        pass
    return "unknown"


def projection(model_id, route_ref="", base_url="", *, enabled=None, contract=None):
    if enabled is None:
        enabled = os.environ.get("CODE_REASONING_V2_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    profile = reviewed_profile(model_id, base_url, contract)
    model = MODELS.get(model_id)
    blocked = model_id == "gpt-6-astra"
    available = list(INTENTS if model and profile != "unknown" else ("default",))
    if blocked or not enabled:
        available = []
    identity = [REVISION, str(model_id), str(route_ref), profile, bool(enabled), contract]
    revision = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
    return {
        "schemaVersion": 2, "capabilityRevision": revision,
        "intents": available, "protocolProfile": profile,
        "candidate": model is not None,
        **({"minimumOutputTokens": {intent: budget + model["answerReserve"] for intent, budget in zip(INTENTS[1:], model["efforts"])}}
           if model and model.get("answerReserve") else {}),
        "evidence": "adapter-tested" if model and profile != "unknown" else "unknown",
        "routeVerified": bool(contract and contract.get("routeVerified") and profile != "unknown"),
        "sourceUrl": model["source"] if model else "",
        "reason": ("reasoning_disabled" if not enabled else
                   "reasoning_protocol_unsupported" if blocked else
                   "reasoning_connection_unverified" if profile == "unknown" else
                   "reasoning_model_unverified" if model is None else ""),
    }


def compile_request(payload, selection, *, model_id, route_ref, base_url, enabled=None, contract=None):
    """Compile once at admission. Existing runs and retries never call this again."""
    if not isinstance(selection, dict) or set(selection) != {
        "schemaVersion", "intent", "modelId", "routeRef", "capabilityRevision",
    } or type(selection.get("schemaVersion")) is not int or selection["schemaVersion"] != 2:
        raise ReasoningError("reasoning_selection_invalid")
    if selection["modelId"] != model_id or selection["routeRef"] != route_ref:
        raise ReasoningError("reasoning_target_mismatch")
    cap = projection(model_id, route_ref, base_url, enabled=enabled, contract=contract)
    if selection["capabilityRevision"] != cap["capabilityRevision"]:
        raise ReasoningError("reasoning_selection_stale")
    intent = selection["intent"]
    if intent not in cap["intents"]:
        raise ReasoningError(cap["reason"] or "reasoning_intent_unsupported")
    extra = payload.get("extra_body")
    google = extra.get("google") if isinstance(extra, dict) else None
    if MANAGED_FIELDS.intersection(payload) or (
        isinstance(google, dict) and "thinking_config" in google
    ):
        raise ReasoningError("reasoning_parameter_conflict")
    result = copy.deepcopy(payload)
    model = MODELS.get(model_id)
    if model and cap["protocolProfile"] != "unknown":
        if intent != "default":
            value = model["efforts"][INTENTS.index(intent) - 1]
            if model["provider"] == "anthropic":
                result["thinking"] = {"type": model["thinking"]}
                if model["thinking"] == "enabled":
                    budget = result.get("max_tokens", 0)
                    if type(budget) is not int or budget < value + model["answerReserve"]:
                        raise ReasoningError("reasoning_budget_insufficient")
                    result["thinking"]["budget_tokens"] = value
                else:
                    result["output_config"] = {"effort": value}
            else:
                result["reasoning_effort"] = value
                if model["provider"] == "deepseek":
                    result["thinking"] = {"type": "enabled"}
        # The exact GPT-5.4 contract forbids sampling with non-none effort.
        # Do not extrapolate Astra/GPT-5.4 restrictions to other model families.
        if ((model_id in {"gpt-5.4", "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"} and intent != "default")
                or model_id in {"o3", "o3-2025-04-16", "o4-mini", "o4-mini-2025-04-16"}
                or (model["provider"] == "anthropic" and (intent != "default" or model.get("sampling") is False))):
            for field in ("temperature", "top_p", "logprobs", "top_logprobs"):
                result.pop(field, None)
            result.pop("top_k", None)
        if model["provider"] == "openai" and "max_tokens" in result:
            if "max_completion_tokens" in result and result["max_completion_tokens"] != result["max_tokens"]:
                raise ReasoningError("reasoning_parameter_conflict")
            result["max_completion_tokens"] = result.pop("max_tokens")
    snapshot = {**copy.deepcopy(selection), "protocolProfile": cap["protocolProfile"],
                "evidence": cap["evidence"], "routeVerified": cap["routeVerified"]}
    if model and model.get("replay") and cap["protocolProfile"] != "unknown":
        snapshot["schemaVersion"] = 3
        snapshot["transportIdentity"] = transport_identity(base_url)
    return result, snapshot


def transport_identity(base_url):
    return hashlib.sha256(str(base_url or "").rstrip("/").removesuffix("/v1").encode()).hexdigest()


def restore_snapshot(value, *, model_id, route_ref):
    """Validate frozen metadata without consulting today's capability catalog."""
    if value is None:
        return None
    fields = {
        "schemaVersion", "intent", "modelId", "routeRef", "capabilityRevision",
        "protocolProfile", "evidence", "routeVerified",
    }
    if isinstance(value, dict) and value.get("schemaVersion") == 3:
        fields.add("transportIdentity")
    if not isinstance(value, dict) or set(value) != fields or type(value.get("schemaVersion")) is not int or value["schemaVersion"] not in (2, 3):
        raise ReasoningError("reasoning_snapshot_invalid")
    if (value["intent"] not in INTENTS or value["modelId"] != model_id
            or value["routeRef"] != route_ref
            or value["protocolProfile"] not in PROFILES | {"unknown"}
            or value["evidence"] not in {"unknown", "adapter-tested"}
            or type(value["routeVerified"]) is not bool
            or not isinstance(value["capabilityRevision"], str)
            or len(value["capabilityRevision"]) != 24):
        raise ReasoningError("reasoning_snapshot_invalid")
    if value["schemaVersion"] == 2 and value["protocolProfile"] not in {"unknown", "openai-chat-native-v1"}:
        raise ReasoningError("reasoning_snapshot_invalid")
    if value["schemaVersion"] == 3 and value["protocolProfile"] in {"unknown", "openai-chat-native-v1"}:
        raise ReasoningError("reasoning_snapshot_invalid")
    if value["schemaVersion"] == 3 and (not isinstance(value["transportIdentity"], str)
            or len(value["transportIdentity"]) != 64
            or MODELS.get(model_id, {}).get("adapter") != value["protocolProfile"]):
        raise ReasoningError("reasoning_snapshot_invalid")
    return copy.deepcopy(value)
