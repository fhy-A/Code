"""Pure Agent event contract and compatibility helpers.

The server may call these pure helpers from an in-memory shadow observer. The
module does not own AgentRun persistence, HTTP snapshots, or frontend
projection.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field


AGENT_EVENT_PROTOCOL_VERSION = 1
AGENT_EVENT_ENVELOPE_FIELDS = frozenset({
    "protocolVersion",
    "seq",
    "type",
    "data",
    "createdAt",
})

AGENT_RUN_ACTIVE_STATES = frozenset({"model", "tools"})
AGENT_RUN_WAITING_STATES = frozenset({
    "waiting_credentials",
    "waiting_user_input",
    "waiting_authorization",
})
AGENT_RUN_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
AGENT_RUN_STATES = (
    AGENT_RUN_ACTIVE_STATES
    | AGENT_RUN_WAITING_STATES
    | AGENT_RUN_TERMINAL_STATES
)


def _event_spec(*payload_fields, required=()):
    return {
        "payloadFields": frozenset(payload_fields),
        "requiredPayloadFields": frozenset(required),
    }


AGENT_EVENT_SPECS = {
    "created": _event_spec(
        "model",
        "allowedTools",
        "maxRounds",
        "contextLimit",
        "permissionProfile",
        "toolBudgets",
        "cwd",
        "workspaceRoots",
        required=("model",),
    ),
    "resumed": _event_spec("status", required=("status",)),
    "waiting_credentials": _event_spec(
        "resumeStatus",
        "reason",
        required=("resumeStatus",),
    ),
    "model_pending": _event_spec("round", required=("round",)),
    "model_started": _event_spec(
        "round",
        "runtimeRunId",
        required=("round", "runtimeRunId"),
    ),
    "model_completed": _event_spec(
        "round",
        "runtimeRunId",
        "content",
        "reasoning",
        "toolCalls",
        "finishReason",
        "usage",
        "completedAt",
        "outcome",
        "forcedFinal",
        required=("round", "runtimeRunId"),
    ),
    "model_recovery": _event_spec(
        "reason",
        "attempt",
        "maxAttempts",
        "runtimeRunId",
        "legacyPendingInput",
        required=("reason", "attempt"),
    ),
    "tool_started": _event_spec(
        "toolCallId",
        "name",
        "arguments",
        "argumentAliases",
        required=("toolCallId", "name", "arguments"),
    ),
    "command_started": _event_spec(
        "toolCallId",
        "command",
        required=("toolCallId", "command"),
    ),
    "tool_completed": _event_spec(
        "toolCallId",
        "name",
        "arguments",
        "argumentAliases",
        "result",
        "outcome",
        "replayed",
        required=("toolCallId", "name", "result", "outcome"),
    ),
    "tool_retry_blocked": _event_spec(
        "toolCallId",
        "name",
        "failureCount",
        required=("toolCallId", "name", "failureCount"),
    ),
    "authorization_required": _event_spec(
        "authorizationId",
        "toolCallId",
        "action",
        "proposalId",
        "path",
        "diff",
        "decision",
        "requestedAt",
        "command",
        "description",
        "childAgentRunId",
        required=("authorizationId", "toolCallId", "action"),
    ),
    "authorization_submitted": _event_spec(
        "authorizationId",
        "toolCallId",
        "decision",
        "childAgentRunId",
        required=("authorizationId", "toolCallId", "decision"),
    ),
    "user_input_required": _event_spec(
        "requestId",
        "toolCallId",
        "title",
        "reason",
        "questions",
        "type",
        required=("requestId", "toolCallId", "questions"),
    ),
    "user_input_submitted": _event_spec(
        "requestId",
        "toolCallId",
        required=("requestId", "toolCallId"),
    ),
    "child_agent_created": _event_spec(
        "toolCallId",
        "childAgentRunId",
        required=("toolCallId", "childAgentRunId"),
    ),
    "context_compaction_started": _event_spec(
        "compactionId",
        "reason",
        "estimatedTokensBefore",
        "contextLimit",
        "threshold",
        "compactedMessageCount",
        "retainedMessageCount",
        required=("compactionId", "reason"),
    ),
    "context_compaction_completed": _event_spec(
        "compactionId",
        "runtimeRunId",
        "reason",
        "summary",
        "estimatedTokensBefore",
        "estimatedTokensAfter",
        "compactedMessageCount",
        "retainedMessageCount",
        "usage",
        "startedAt",
        "completedAt",
        required=("compactionId", "summary"),
    ),
    "context_compaction_failed": _event_spec(
        "compactionId",
        "reason",
        "error",
        "errorCode",
        required=("compactionId", "error"),
    ),
    "completed": _event_spec(),
    "failed": _event_spec("error", "errorCode", required=("error",)),
    "cancelled": _event_spec(),
}

AGENT_RUN_TRANSITIONS = {
    "model": frozenset({
        "model",
        "tools",
        "waiting_user_input",
        "waiting_authorization",
        "waiting_credentials",
        "completed",
        "failed",
        "cancelled",
    }),
    "tools": frozenset({
        "tools",
        "model",
        "waiting_user_input",
        "waiting_authorization",
        "waiting_credentials",
        "completed",
        "failed",
        "cancelled",
    }),
    "waiting_credentials": frozenset({
        "waiting_credentials",
        "model",
        "tools",
        "failed",
        "cancelled",
    }),
    "waiting_user_input": frozenset({
        "waiting_user_input",
        "waiting_credentials",
        "failed",
        "cancelled",
    }),
    "waiting_authorization": frozenset({
        "waiting_authorization",
        "waiting_credentials",
        "failed",
        "cancelled",
    }),
    "completed": frozenset({"completed"}),
    "failed": frozenset({"failed"}),
    "cancelled": frozenset({"cancelled"}),
}

MODEL_ROUND_STATES = frozenset({
    "pending",
    "started",
    "completed",
    "recovery",
    "failed",
    "cancelled",
})
MODEL_ROUND_TRANSITIONS = {
    "pending": frozenset({"pending", "started", "failed", "cancelled"}),
    "started": frozenset({"started", "completed", "failed", "cancelled"}),
    "completed": frozenset({"completed", "pending", "recovery"}),
    "recovery": frozenset({"recovery", "pending", "started", "failed", "cancelled"}),
    "failed": frozenset({"failed"}),
    "cancelled": frozenset({"cancelled"}),
}

TOOL_EXECUTION_STATES = frozenset({
    "running",
    "waiting_user_input",
    "waiting_authorization",
    "applying_edit",
    "authorized",
    "applying_file_mutation",
    "waiting_child",
    "waiting_child_authorization",
    "completed",
    "cancelled",
})
TOOL_EXECUTION_TRANSITIONS = {
    "running": frozenset({
        "running",
        "waiting_user_input",
        "waiting_authorization",
        "waiting_child",
        "completed",
        "cancelled",
    }),
    "waiting_user_input": frozenset({
        "waiting_user_input",
        "completed",
        "cancelled",
    }),
    "waiting_authorization": frozenset({
        "waiting_authorization",
        "authorized",
        "completed",
        "cancelled",
    }),
    "authorized": frozenset({
        "authorized",
        "running",
        "applying_edit",
        "applying_file_mutation",
        "waiting_child",
        "completed",
        "cancelled",
    }),
    "applying_edit": frozenset({"applying_edit", "completed", "cancelled"}),
    "applying_file_mutation": frozenset({
        "applying_file_mutation",
        "completed",
        "cancelled",
    }),
    "waiting_child": frozenset({
        "waiting_child",
        "waiting_child_authorization",
        "completed",
        "cancelled",
    }),
    "waiting_child_authorization": frozenset({
        "waiting_child_authorization",
        "waiting_child",
        "completed",
        "cancelled",
    }),
    "completed": frozenset({"completed"}),
    "cancelled": frozenset({"cancelled"}),
}

TRANSITION_TABLES = {
    "run": AGENT_RUN_TRANSITIONS,
    "model_round": MODEL_ROUND_TRANSITIONS,
    "tool_execution": TOOL_EXECUTION_TRANSITIONS,
}

_SENSITIVE_KEY_NAMES = frozenset({
    "apikey",
    "accesstoken",
    "authorization",
    "cookie",
    "cookies",
    "headers",
    "keys",
    "password",
    "clientsecret",
})
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
)
_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class AgentProtocolError(ValueError):
    """Raised when strict contract validation rejects an event or transition."""


def _diagnostic(code, message, *, path="", severity="warning"):
    result = {"code": code, "severity": severity, "message": message}
    if path:
        result["path"] = path
    return result


def _normalized_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _credential_diagnostics(value, path="$", found=None):
    """Find credential-shaped content without retaining any matched value."""
    if found is None:
        found = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _normalized_key(key) in _SENSITIVE_KEY_NAMES:
                found.setdefault(
                    "credential_bearing_field",
                    _diagnostic(
                        "credential_bearing_field",
                        f"Credential-bearing field is not allowed in Agent events: {child_path}",
                        path=child_path,
                        severity="error",
                    ),
                )
                continue
            _credential_diagnostics(child, child_path, found)
            if len(found) >= 2:
                break
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _credential_diagnostics(child, f"{path}[{index}]", found)
            if len(found) >= 2:
                break
    elif isinstance(value, str):
        for pattern in _SENSITIVE_TEXT_PATTERNS:
            if pattern.search(value):
                found.setdefault(
                    "credential_like_text",
                    _diagnostic(
                        "credential_like_text",
                        f"Credential-like text requires review in Agent events: {path}",
                        path=path,
                        severity="warning",
                    ),
                )
                break
    return list(found.values())


def normalize_agent_event(raw_event, *, strict=False, credential_mode="reject"):
    """Adapt an unversioned/current event to the canonical v1 envelope.

    Unknown event types and unknown fields are preserved or ignored with
    diagnostics so a newer producer cannot crash an older projection. Missing
    required fields fail only in strict test mode. Credential-shaped content
    is rejected by default; the production shadow observer may request a
    sanitized diagnostic so sequence validation can continue without retaining
    the matched value.
    """
    if not isinstance(raw_event, dict):
        raise AgentProtocolError("Agent event must be an object")
    if credential_mode not in {"reject", "diagnose"}:
        raise ValueError("credential_mode must be 'reject' or 'diagnose'")
    credential_diagnostics = _credential_diagnostics(raw_event)
    if credential_diagnostics and (strict or credential_mode == "reject"):
        raise AgentProtocolError(credential_diagnostics[0]["message"])

    diagnostics = list(credential_diagnostics)
    raw_version = raw_event.get("protocolVersion")
    if raw_version is None:
        source_version = 0
        diagnostics.append(_diagnostic(
            "legacy_unversioned_event",
            "Unversioned Agent event was adapted as protocol v0.",
            path="protocolVersion",
            severity="info",
        ))
    elif isinstance(raw_version, int) and raw_version >= 1:
        source_version = raw_version
        if raw_version > AGENT_EVENT_PROTOCOL_VERSION:
            diagnostic = _diagnostic(
                "future_protocol_version",
                f"Protocol v{raw_version} was read using the v1 stable envelope.",
                path="protocolVersion",
            )
            diagnostics.append(diagnostic)
            if strict:
                raise AgentProtocolError(diagnostic["message"])
    else:
        raise AgentProtocolError("protocolVersion must be a positive integer")

    unknown_envelope = sorted(set(raw_event) - AGENT_EVENT_ENVELOPE_FIELDS)
    if unknown_envelope:
        diagnostics.append(_diagnostic(
            "unknown_envelope_fields",
            f"Ignored unknown envelope fields: {', '.join(unknown_envelope)}",
            path="$",
            severity="info",
        ))

    raw_seq = raw_event.get("seq")
    if isinstance(raw_seq, bool) or not isinstance(raw_seq, int) or raw_seq <= 0:
        if strict:
            raise AgentProtocolError("event seq must be a positive integer")
        diagnostics.append(_diagnostic(
            "invalid_event_seq",
            "Invalid event seq was normalized to zero for diagnostics.",
            path="seq",
        ))
        seq = 0
    else:
        seq = raw_seq

    event_type = str(raw_event.get("type") or "").strip()
    if not event_type:
        raise AgentProtocolError("event type must be a non-empty string")
    known_type = event_type in AGENT_EVENT_SPECS
    if not known_type:
        diagnostics.append(_diagnostic(
            "unknown_event_type",
            f"Unknown event type {event_type!r} was preserved and may be ignored by projections.",
            path="type",
        ))

    raw_data = raw_event.get("data")
    if not isinstance(raw_data, dict):
        if strict:
            raise AgentProtocolError("event data must be an object")
        diagnostics.append(_diagnostic(
            "invalid_event_data",
            "Non-object event data was replaced with an empty object.",
            path="data",
        ))
        raw_data = {}
    data = deepcopy(raw_data)

    if known_type:
        spec = AGENT_EVENT_SPECS[event_type]
        missing = sorted(spec["requiredPayloadFields"] - data.keys())
        if missing:
            diagnostic = _diagnostic(
                "missing_payload_fields",
                f"Missing required payload fields: {', '.join(missing)}",
                path="data",
            )
            diagnostics.append(diagnostic)
            if strict:
                raise AgentProtocolError(diagnostic["message"])
        unknown_payload = sorted(data.keys() - spec["payloadFields"])
        if unknown_payload:
            diagnostics.append(_diagnostic(
                "unknown_payload_fields",
                f"Preserved unknown payload fields: {', '.join(unknown_payload)}",
                path="data",
                severity="info",
            ))

    created_at = str(raw_event.get("createdAt") or "")
    if not _ISO_UTC_RE.fullmatch(created_at):
        if strict:
            raise AgentProtocolError("createdAt must be an ISO-8601 UTC timestamp")
        diagnostics.append(_diagnostic(
            "invalid_created_at",
            "Invalid createdAt was preserved for compatibility diagnostics.",
            path="createdAt",
        ))

    return {
        "event": {
            "protocolVersion": AGENT_EVENT_PROTOCOL_VERSION,
            "seq": seq,
            "type": event_type,
            "data": data,
            "createdAt": created_at,
        },
        "sourceProtocolVersion": source_version,
        "knownType": known_type,
        "diagnostics": diagnostics,
    }


def validate_transition(domain, previous, current, *, strict=False):
    """Validate one Run/model-round/tool-execution state transition."""
    table = TRANSITION_TABLES.get(str(domain or ""))
    if table is None:
        raise AgentProtocolError(f"unknown transition domain: {domain!r}")
    if previous not in table:
        raise AgentProtocolError(f"unknown {domain} state: {previous!r}")
    if current not in table:
        raise AgentProtocolError(f"unknown {domain} state: {current!r}")
    valid = current in table[previous]
    diagnostics = []
    if not valid:
        diagnostic = _diagnostic(
            "illegal_state_transition",
            f"Illegal {domain} transition: {previous} -> {current}",
            path=domain,
        )
        diagnostics.append(diagnostic)
        if strict:
            raise AgentProtocolError(diagnostic["message"])
    return {"valid": valid, "diagnostics": diagnostics}


def _event_fingerprint(event):
    payload = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class AgentEventSequenceValidator:
    """Check monotonic ordering and make exact redelivery idempotent."""

    cursor: int = 0
    fingerprints: dict[int, str] = field(default_factory=dict)

    def observe(self, normalized_event, *, strict=False):
        event = (
            normalized_event.get("event")
            if isinstance(normalized_event, dict) and "event" in normalized_event
            else normalized_event
        )
        if not isinstance(event, dict):
            raise AgentProtocolError("normalized event must be an object")
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
            raise AgentProtocolError("normalized event seq must be a positive integer")
        fingerprint = _event_fingerprint(event)
        existing = self.fingerprints.get(seq)
        if existing is not None:
            if existing == fingerprint:
                return {
                    "accepted": False,
                    "duplicate": True,
                    "diagnostics": [_diagnostic(
                        "duplicate_event",
                        f"Event seq {seq} was already accepted with identical content.",
                        path="seq",
                        severity="info",
                    )],
                }
            raise AgentProtocolError(
                f"event seq {seq} was reused with different content"
            )

        diagnostics = []
        if seq <= self.cursor:
            diagnostic = _diagnostic(
                "out_of_order_event",
                f"Event seq {seq} is behind cursor {self.cursor}.",
                path="seq",
            )
            diagnostics.append(diagnostic)
            if strict:
                raise AgentProtocolError(diagnostic["message"])
            return {"accepted": False, "duplicate": False, "diagnostics": diagnostics}
        if seq > self.cursor + 1:
            diagnostic = _diagnostic(
                "event_sequence_gap",
                f"Event seq jumped from {self.cursor} to {seq}.",
                path="seq",
            )
            diagnostics.append(diagnostic)
            if strict:
                raise AgentProtocolError(diagnostic["message"])

        self.fingerprints[seq] = fingerprint
        self.cursor = seq
        return {"accepted": True, "duplicate": False, "diagnostics": diagnostics}


def public_contract_summary():
    """Return a JSON-serializable contract summary for tests and diagnostics."""
    return {
        "protocolVersion": AGENT_EVENT_PROTOCOL_VERSION,
        "envelopeFields": sorted(AGENT_EVENT_ENVELOPE_FIELDS),
        "eventTypes": {
            name: {
                "payloadFields": sorted(spec["payloadFields"]),
                "requiredPayloadFields": sorted(spec["requiredPayloadFields"]),
            }
            for name, spec in sorted(AGENT_EVENT_SPECS.items())
        },
        "transitions": {
            domain: {
                state: sorted(targets)
                for state, targets in sorted(table.items())
            }
            for domain, table in sorted(TRANSITION_TABLES.items())
        },
        "unknownFieldPolicy": "preserve payload, ignore envelope extras, emit diagnostics",
        "credentialPolicy": "reject recursively",
    }
