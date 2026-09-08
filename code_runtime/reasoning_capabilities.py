"""Exact model reasoning contracts; no credentials, network probes or alias guessing."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from urllib.parse import urlsplit

REVISION = "reasoning-a-2026-09-08-v1"
INTENTS = ("default", "low", "medium", "high")
MANAGED_FIELDS = frozenset({
    "reasoning_effort", "reasoning", "thinking", "output_config",
    "enable_thinking", "thinking_budget",
})
# Exact public IDs only. Additional o-models await an exact parameter contract.
MODELS = {
    "gpt-5.4": {"default": "none"},
    "gpt-5.5": {"default": "medium"},
    "gpt-5.6-sol": {"default": "medium"},
    "gpt-5.6-terra": {"default": "medium"},
    "gpt-5.6-luna": {"default": "medium"},
}


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


def projection(model_id, route_ref="", base_url="", *, enabled=None):
    if enabled is None:
        enabled = os.environ.get("CODE_REASONING_V2_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    profile = transport_profile(base_url)
    model = MODELS.get(model_id)
    blocked = model_id == "gpt-6-astra"
    available = list(INTENTS if model and profile != "unknown" else ("default",))
    if blocked or not enabled:
        available = []
    identity = [REVISION, str(model_id), str(route_ref), profile, bool(enabled)]
    revision = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
    return {
        "schemaVersion": 2, "capabilityRevision": revision,
        "intents": available, "protocolProfile": profile,
        "candidate": model is not None,
        "evidence": "adapter-tested" if model and profile != "unknown" else "unknown",
        "routeVerified": False,
        "sourceUrl": f"https://developers.openai.com/api/docs/models/{model_id}" if model else "",
        "reason": ("reasoning_disabled" if not enabled else
                   "reasoning_protocol_unsupported" if blocked else
                   "reasoning_connection_unverified" if profile == "unknown" else
                   "reasoning_model_unverified" if model is None else ""),
    }


def compile_request(payload, selection, *, model_id, route_ref, base_url, enabled=None):
    """Compile once at admission. Existing runs and retries never call this again."""
    if not isinstance(selection, dict) or set(selection) != {
        "schemaVersion", "intent", "modelId", "routeRef", "capabilityRevision",
    } or type(selection.get("schemaVersion")) is not int or selection["schemaVersion"] != 2:
        raise ReasoningError("reasoning_selection_invalid")
    if selection["modelId"] != model_id or selection["routeRef"] != route_ref:
        raise ReasoningError("reasoning_target_mismatch")
    cap = projection(model_id, route_ref, base_url, enabled=enabled)
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
            result["reasoning_effort"] = intent
        # The exact GPT-5.4 contract forbids sampling with non-none effort.
        # Do not extrapolate Astra/GPT-5.4 restrictions to other model families.
        if model_id == "gpt-5.4" and intent != "default":
            for field in ("temperature", "top_p", "logprobs", "top_logprobs"):
                result.pop(field, None)
        if "max_tokens" in result:
            if "max_completion_tokens" in result and result["max_completion_tokens"] != result["max_tokens"]:
                raise ReasoningError("reasoning_parameter_conflict")
            result["max_completion_tokens"] = result.pop("max_tokens")
    snapshot = {**copy.deepcopy(selection), "protocolProfile": cap["protocolProfile"],
                "evidence": cap["evidence"], "routeVerified": False}
    return result, snapshot


def restore_snapshot(value, *, model_id, route_ref):
    """Validate frozen metadata without consulting today's capability catalog."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "intent", "modelId", "routeRef", "capabilityRevision",
        "protocolProfile", "evidence", "routeVerified",
    } or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 2:
        raise ReasoningError("reasoning_snapshot_invalid")
    if (value["intent"] not in INTENTS or value["modelId"] != model_id
            or value["routeRef"] != route_ref
            or value["protocolProfile"] not in {"unknown", "openai-chat-native-v1"}
            or value["evidence"] not in {"unknown", "adapter-tested"}
            or value["routeVerified"] is not False
            or not isinstance(value["capabilityRevision"], str)
            or len(value["capabilityRevision"]) != 24):
        raise ReasoningError("reasoning_snapshot_invalid")
    return copy.deepcopy(value)
