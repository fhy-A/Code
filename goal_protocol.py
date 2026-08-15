"""Versioned Goal fact protocol and strict deterministic reducer.

This module is deliberately independent from HTTP, Session messages, AgentRun,
and frontend state.  It validates complete Goal snapshots and folds append-only
events into one trusted projection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


GOAL_PROTOCOL_VERSION = 1
GOAL_EVENT_OPERATIONS = frozenset({"replace", "clear"})
GOAL_STEP_STATUSES = frozenset({"pending", "in_progress", "completed"})
GOAL_LIFECYCLES = frozenset({
    "draft",
    "awaiting_confirmation",
    "active",
    "paused",
    "ready_for_acceptance",
    "completed",
    "cancelled",
})
GOAL_TERMINAL_LIFECYCLES = frozenset({"completed", "cancelled"})
GOAL_RUNTIME_SIGNALS = frozenset({"waiting_user", "blocked", "failed", "retry"})
GOAL_PERMISSION_PROFILES = frozenset({"read", "plan", "accept", "bypass"})
GOAL_EVIDENCE_KINDS = frozenset({"machine", "agent", "user"})

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_MAX_OBJECTIVE_LENGTH = 20_000
_MAX_DESCRIPTION_LENGTH = 4_000
_MAX_SUMMARY_LENGTH = 2_000
_MAX_CRITERIA_PER_STEP = 20
_MAX_EVIDENCE_PER_STEP = 100
_SNAPSHOT_FIELDS = frozenset({
    "goalId",
    "sessionId",
    "revision",
    "objective",
    "lifecycle",
    "permissionProfile",
    "steps",
    "currentStepId",
    "runtimeSignals",
    "ownerRunId",
    "createdAt",
    "updatedAt",
})
_STEP_FIELDS = frozenset({
    "id",
    "description",
    "status",
    "acceptanceCriteria",
    "evidence",
})
_CRITERION_FIELDS = frozenset({"id", "description", "kind"})
_EVIDENCE_FIELDS = frozenset({
    "id",
    "criterionId",
    "kind",
    "summary",
    "sourceRunId",
    "sourceToolCallId",
    "artifactDigest",
    "recordedAt",
})
_SIGNAL_FIELDS = frozenset({"type", "summary", "sourceRunId", "recordedAt"})
_EVENT_FIELDS = frozenset({
    "protocolVersion",
    "eventId",
    "operation",
    "sessionId",
    "goalId",
    "revision",
    "expectedRevision",
    "idempotencyKey",
    "requestHash",
    "actor",
    "createdAt",
    "snapshot",
})


class GoalProtocolError(ValueError):
    """The persisted or proposed Goal value violates protocol v1."""


class GoalTransitionError(GoalProtocolError):
    """A valid snapshot attempts an illegal deterministic transition."""


@dataclass
class GoalFoldState:
    """Internal trusted fold state; callers should expose ``projection()``."""

    session_id: str
    revision: int = 0
    goal: dict[str, Any] | None = None
    tombstone: dict[str, Any] | None = None
    last_event_id: str | None = None
    used_goal_ids: set[str] = field(default_factory=set)
    event_ids: set[str] = field(default_factory=set)
    idempotency: dict[str, str] = field(default_factory=dict)

    def projection(self) -> dict[str, Any]:
        return {
            "protocolVersion": GOAL_PROTOCOL_VERSION,
            "sessionId": self.session_id,
            "revision": self.revision,
            "goal": copy.deepcopy(self.goal),
            "tombstone": copy.deepcopy(self.tombstone),
            "lastEventId": self.last_event_id,
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GoalProtocolError(f"{label} must be an object")
    return value


def _reject_unknown_fields(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GoalProtocolError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _require_string(value: Any, label: str, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise GoalProtocolError(f"{label} must be a string")
    if not allow_empty and not value.strip():
        raise GoalProtocolError(f"{label} must not be empty")
    if len(value) > maximum:
        raise GoalProtocolError(f"{label} exceeds {maximum} characters")
    return value


def _require_identifier(value: Any, label: str) -> str:
    text = _require_string(value, label, maximum=128)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise GoalProtocolError(f"{label} is not a valid identifier")
    return text


def _optional_identifier(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return _require_identifier(value, label)


def _require_positive_revision(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GoalProtocolError(f"{label} must be an integer >= {minimum}")
    return value


def _normalize_criterion(value: Any, step_id: str) -> dict[str, Any]:
    criterion = _require_dict(value, f"step {step_id} criterion")
    _reject_unknown_fields(criterion, _CRITERION_FIELDS, f"step {step_id} criterion")
    criterion_id = _require_identifier(criterion.get("id"), f"step {step_id} criterion.id")
    kind = _require_string(criterion.get("kind"), f"criterion {criterion_id}.kind", maximum=32)
    if kind not in GOAL_EVIDENCE_KINDS:
        raise GoalProtocolError(f"criterion {criterion_id}.kind is unsupported")
    return {
        "id": criterion_id,
        "description": _require_string(
            criterion.get("description"),
            f"criterion {criterion_id}.description",
            maximum=_MAX_DESCRIPTION_LENGTH,
        ),
        "kind": kind,
    }


def _normalize_evidence(value: Any, step_id: str, criterion_ids: set[str]) -> dict[str, Any]:
    evidence = _require_dict(value, f"step {step_id} evidence")
    _reject_unknown_fields(evidence, _EVIDENCE_FIELDS, f"step {step_id} evidence")
    evidence_id = _require_identifier(evidence.get("id"), f"step {step_id} evidence.id")
    criterion_id = _require_identifier(
        evidence.get("criterionId"), f"evidence {evidence_id}.criterionId"
    )
    if criterion_id not in criterion_ids:
        raise GoalProtocolError(f"evidence {evidence_id} references an unknown criterion")
    kind = _require_string(evidence.get("kind"), f"evidence {evidence_id}.kind", maximum=32)
    if kind not in GOAL_EVIDENCE_KINDS:
        raise GoalProtocolError(f"evidence {evidence_id}.kind is unsupported")
    normalized = {
        "id": evidence_id,
        "criterionId": criterion_id,
        "kind": kind,
        "summary": _require_string(
            evidence.get("summary"),
            f"evidence {evidence_id}.summary",
            maximum=_MAX_SUMMARY_LENGTH,
        ),
        "sourceRunId": _optional_identifier(
            evidence.get("sourceRunId"), f"evidence {evidence_id}.sourceRunId"
        ),
        "sourceToolCallId": _optional_identifier(
            evidence.get("sourceToolCallId"), f"evidence {evidence_id}.sourceToolCallId"
        ),
        "artifactDigest": None,
        "recordedAt": _require_string(
            evidence.get("recordedAt"),
            f"evidence {evidence_id}.recordedAt",
            maximum=64,
        ),
    }
    digest = evidence.get("artifactDigest")
    if digest not in (None, ""):
        digest = _require_string(digest, f"evidence {evidence_id}.artifactDigest", maximum=64)
        if not _SHA256_RE.fullmatch(digest):
            raise GoalProtocolError(f"evidence {evidence_id}.artifactDigest must be lowercase SHA-256")
        normalized["artifactDigest"] = digest
    return normalized


def _normalize_step(value: Any) -> dict[str, Any]:
    step = _require_dict(value, "goal step")
    _reject_unknown_fields(step, _STEP_FIELDS, "goal step")
    step_id = _require_identifier(step.get("id"), "goal step.id")
    status = _require_string(step.get("status"), f"step {step_id}.status", maximum=32)
    if status not in GOAL_STEP_STATUSES:
        raise GoalProtocolError(f"step {step_id}.status must be pending, in_progress, or completed")
    criteria = step.get("acceptanceCriteria")
    if not isinstance(criteria, list) or not (1 <= len(criteria) <= _MAX_CRITERIA_PER_STEP):
        raise GoalProtocolError(
            f"step {step_id}.acceptanceCriteria must contain 1-{_MAX_CRITERIA_PER_STEP} items"
        )
    normalized_criteria = [_normalize_criterion(item, step_id) for item in criteria]
    criterion_ids = [item["id"] for item in normalized_criteria]
    if len(set(criterion_ids)) != len(criterion_ids):
        raise GoalProtocolError(f"step {step_id} contains duplicate criterion ids")
    raw_evidence = step.get("evidence", [])
    if not isinstance(raw_evidence, list) or len(raw_evidence) > _MAX_EVIDENCE_PER_STEP:
        raise GoalProtocolError(
            f"step {step_id}.evidence must contain at most {_MAX_EVIDENCE_PER_STEP} items"
        )
    normalized_evidence = [
        _normalize_evidence(item, step_id, set(criterion_ids)) for item in raw_evidence
    ]
    evidence_ids = [item["id"] for item in normalized_evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise GoalProtocolError(f"step {step_id} contains duplicate evidence ids")
    return {
        "id": step_id,
        "description": _require_string(
            step.get("description"), f"step {step_id}.description", maximum=_MAX_DESCRIPTION_LENGTH
        ),
        "status": status,
        "acceptanceCriteria": normalized_criteria,
        "evidence": normalized_evidence,
    }


def _normalize_signal(value: Any) -> dict[str, Any]:
    signal = _require_dict(value, "runtime signal")
    _reject_unknown_fields(signal, _SIGNAL_FIELDS, "runtime signal")
    signal_type = _require_string(signal.get("type"), "runtime signal.type", maximum=32)
    if signal_type not in GOAL_RUNTIME_SIGNALS:
        raise GoalProtocolError(f"unsupported runtime signal: {signal_type}")
    return {
        "type": signal_type,
        "summary": _require_string(
            signal.get("summary"), "runtime signal.summary", maximum=_MAX_SUMMARY_LENGTH
        ),
        "sourceRunId": _optional_identifier(signal.get("sourceRunId"), "runtime signal.sourceRunId"),
        "recordedAt": _require_string(
            signal.get("recordedAt"), "runtime signal.recordedAt", maximum=64
        ),
    }


def normalize_snapshot(snapshot: Any, *, session_id: str, revision: int) -> dict[str, Any]:
    value = _require_dict(snapshot, "goal snapshot")
    _reject_unknown_fields(value, _SNAPSHOT_FIELDS, "goal snapshot")
    normalized_session_id = _require_identifier(value.get("sessionId"), "goal snapshot.sessionId")
    if normalized_session_id != session_id:
        raise GoalProtocolError("goal snapshot sessionId does not match its event")
    snapshot_revision = _require_positive_revision(value.get("revision"), "goal snapshot.revision")
    if snapshot_revision != revision:
        raise GoalProtocolError("goal snapshot revision does not match its event")
    lifecycle = _require_string(value.get("lifecycle"), "goal snapshot.lifecycle", maximum=32)
    if lifecycle not in GOAL_LIFECYCLES:
        raise GoalProtocolError(f"unsupported goal lifecycle: {lifecycle}")
    permission_profile = _require_string(
        value.get("permissionProfile"), "goal snapshot.permissionProfile", maximum=32
    )
    if permission_profile not in GOAL_PERMISSION_PROFILES:
        raise GoalProtocolError("goal snapshot.permissionProfile is unsupported")
    steps = value.get("steps")
    if not isinstance(steps, list) or not (3 <= len(steps) <= 8):
        raise GoalProtocolError("goal snapshot.steps must contain 3-8 product-level steps")
    normalized_steps = [_normalize_step(item) for item in steps]
    step_ids = [item["id"] for item in normalized_steps]
    if len(set(step_ids)) != len(step_ids):
        raise GoalProtocolError("goal snapshot contains duplicate step ids")
    in_progress = [item["id"] for item in normalized_steps if item["status"] == "in_progress"]
    if len(in_progress) > 1:
        raise GoalProtocolError("goal snapshot may contain at most one in_progress step")
    current_step_id = _optional_identifier(value.get("currentStepId"), "goal snapshot.currentStepId")
    expected_current = in_progress[0] if in_progress else None
    if current_step_id != expected_current:
        raise GoalProtocolError("goal snapshot.currentStepId must identify the in_progress step")
    if lifecycle in {"draft", "awaiting_confirmation"} and in_progress:
        raise GoalProtocolError(f"{lifecycle} goals cannot expose an in_progress step")
    if lifecycle in {"active", "paused", "ready_for_acceptance"} and len(in_progress) != 1:
        raise GoalProtocolError(f"{lifecycle} goals must expose exactly one in_progress step")
    if lifecycle == "completed":
        if any(item["status"] != "completed" for item in normalized_steps):
            raise GoalProtocolError("completed goals require every step to be completed")
        if current_step_id is not None:
            raise GoalProtocolError("completed goals cannot have a current step")
    raw_signals = value.get("runtimeSignals", [])
    if not isinstance(raw_signals, list) or len(raw_signals) > 20:
        raise GoalProtocolError("goal snapshot.runtimeSignals must contain at most 20 items")
    normalized = {
        "goalId": _require_identifier(value.get("goalId"), "goal snapshot.goalId"),
        "sessionId": normalized_session_id,
        "revision": snapshot_revision,
        "objective": _require_string(
            value.get("objective"), "goal snapshot.objective", maximum=_MAX_OBJECTIVE_LENGTH
        ),
        "lifecycle": lifecycle,
        "permissionProfile": permission_profile,
        "steps": normalized_steps,
        "currentStepId": current_step_id,
        "runtimeSignals": [_normalize_signal(item) for item in raw_signals],
        "ownerRunId": _optional_identifier(value.get("ownerRunId"), "goal snapshot.ownerRunId"),
        "createdAt": _require_string(value.get("createdAt"), "goal snapshot.createdAt", maximum=64),
        "updatedAt": _require_string(value.get("updatedAt"), "goal snapshot.updatedAt", maximum=64),
    }
    return normalized


def validate_event(event: Any, *, session_id: str | None = None) -> dict[str, Any]:
    value = _require_dict(event, "goal event")
    _reject_unknown_fields(value, _EVENT_FIELDS, "goal event")
    version = value.get("protocolVersion")
    if version != GOAL_PROTOCOL_VERSION:
        raise GoalProtocolError(f"unsupported goal protocol version: {version!r}")
    operation = _require_string(value.get("operation"), "goal event.operation", maximum=16)
    if operation not in GOAL_EVENT_OPERATIONS:
        raise GoalProtocolError(f"unsupported goal event operation: {operation}")
    event_session_id = _require_identifier(value.get("sessionId"), "goal event.sessionId")
    if session_id is not None and event_session_id != session_id:
        raise GoalProtocolError("goal event sessionId does not match its sidecar")
    revision = _require_positive_revision(value.get("revision"), "goal event.revision")
    expected_revision = _require_positive_revision(
        value.get("expectedRevision"), "goal event.expectedRevision", allow_zero=True
    )
    if revision != expected_revision + 1:
        raise GoalProtocolError("goal event revision must equal expectedRevision + 1")
    digest = _require_string(value.get("requestHash"), "goal event.requestHash", maximum=64)
    if not _SHA256_RE.fullmatch(digest):
        raise GoalProtocolError("goal event.requestHash must be lowercase SHA-256")
    normalized = {
        "protocolVersion": GOAL_PROTOCOL_VERSION,
        "eventId": _require_identifier(value.get("eventId"), "goal event.eventId"),
        "operation": operation,
        "sessionId": event_session_id,
        "goalId": _require_identifier(value.get("goalId"), "goal event.goalId"),
        "revision": revision,
        "expectedRevision": expected_revision,
        "idempotencyKey": _require_identifier(
            value.get("idempotencyKey"), "goal event.idempotencyKey"
        ),
        "requestHash": digest,
        "actor": _require_string(value.get("actor"), "goal event.actor", maximum=64),
        "createdAt": _require_string(value.get("createdAt"), "goal event.createdAt", maximum=64),
        "snapshot": None,
    }
    if operation == "replace":
        normalized["snapshot"] = normalize_snapshot(
            value.get("snapshot"), session_id=event_session_id, revision=revision
        )
        if normalized["snapshot"]["goalId"] != normalized["goalId"]:
            raise GoalProtocolError("goal event goalId does not match its snapshot")
    elif value.get("snapshot") is not None:
        raise GoalProtocolError("clear events must use a null snapshot")
    expected_hash = request_hash({
        "operation": operation,
        "sessionId": event_session_id,
        "goalId": normalized["goalId"],
        "expectedRevision": expected_revision,
        "snapshot": normalized["snapshot"],
    } if operation == "replace" else {
        "operation": operation,
        "sessionId": event_session_id,
        "goalId": normalized["goalId"],
        "expectedRevision": expected_revision,
    })
    if normalized["requestHash"] != expected_hash:
        raise GoalProtocolError("goal event.requestHash does not match its mutation payload")
    return normalized


def _step_transition(previous: dict[str, Any], current: dict[str, Any]) -> None:
    progress = {"pending": 0, "in_progress": 1, "completed": 2}
    if progress[current["status"]] < progress[previous["status"]]:
        raise GoalTransitionError(f"step {previous['id']} cannot move backwards")
    if previous["status"] == "completed":
        if current["description"] != previous["description"]:
            raise GoalTransitionError(f"completed step {previous['id']} cannot change description")
        if current["acceptanceCriteria"] != previous["acceptanceCriteria"]:
            raise GoalTransitionError(f"completed step {previous['id']} cannot change acceptance criteria")


def _validate_snapshot_transition(previous: dict[str, Any], current: dict[str, Any]) -> None:
    if previous["lifecycle"] in GOAL_TERMINAL_LIFECYCLES:
        raise GoalTransitionError("terminal goals cannot be rewritten")
    allowed_lifecycles = {
        "draft": {"draft", "awaiting_confirmation", "active", "cancelled"},
        "awaiting_confirmation": {
            "draft", "awaiting_confirmation", "active", "paused", "cancelled"
        },
        "active": {"active", "paused", "ready_for_acceptance", "completed", "cancelled"},
        "paused": {"paused", "active", "cancelled"},
        "ready_for_acceptance": {
            "ready_for_acceptance", "active", "completed", "cancelled"
        },
    }
    if current["lifecycle"] not in allowed_lifecycles.get(previous["lifecycle"], set()):
        raise GoalTransitionError(
            f"illegal goal lifecycle transition: {previous['lifecycle']} -> {current['lifecycle']}"
        )
    if current["createdAt"] != previous["createdAt"]:
        raise GoalTransitionError("goal createdAt is immutable")
    if current["permissionProfile"] != previous["permissionProfile"]:
        raise GoalTransitionError("goal permissionProfile is immutable")
    previous_steps = {item["id"]: item for item in previous["steps"]}
    current_steps = {item["id"]: item for item in current["steps"]}
    for step_id, old_step in previous_steps.items():
        new_step = current_steps.get(step_id)
        if new_step is None:
            if old_step["status"] != "pending":
                raise GoalTransitionError(f"started step {step_id} cannot disappear")
            continue
        _step_transition(old_step, new_step)


def apply_event(state: GoalFoldState, event: Any) -> GoalFoldState:
    normalized = validate_event(event, session_id=state.session_id)
    if normalized["revision"] != state.revision + 1:
        raise GoalTransitionError("goal event revision is not contiguous")
    if normalized["expectedRevision"] != state.revision:
        raise GoalTransitionError("goal event expectedRevision does not match fold state")
    key = normalized["idempotencyKey"]
    if normalized["eventId"] in state.event_ids:
        raise GoalTransitionError("duplicate eventId in persisted Goal history")
    if key in state.idempotency:
        raise GoalTransitionError("duplicate idempotency key in persisted Goal history")
    goal_id = normalized["goalId"]
    if normalized["operation"] == "clear":
        if state.goal is None:
            raise GoalTransitionError("cannot clear a Session without a current Goal")
        if state.goal["goalId"] != goal_id:
            raise GoalTransitionError("clear event goalId does not match the current Goal")
        state.goal = None
        state.tombstone = {
            "goalId": goal_id,
            "revision": normalized["revision"],
            "eventId": normalized["eventId"],
            "clearedAt": normalized["createdAt"],
        }
    else:
        snapshot = normalized["snapshot"]
        if state.goal is None:
            if goal_id in state.used_goal_ids:
                raise GoalTransitionError("cleared or historical goalId cannot be reused")
        elif state.goal["goalId"] == goal_id:
            _validate_snapshot_transition(state.goal, snapshot)
        else:
            if state.goal["lifecycle"] not in GOAL_TERMINAL_LIFECYCLES:
                raise GoalTransitionError("a Session may have at most one active Goal")
            if goal_id in state.used_goal_ids:
                raise GoalTransitionError("historical goalId cannot be reused")
        state.goal = copy.deepcopy(snapshot)
        state.tombstone = None
        state.used_goal_ids.add(goal_id)
    state.revision = normalized["revision"]
    state.last_event_id = normalized["eventId"]
    state.event_ids.add(normalized["eventId"])
    state.idempotency[key] = normalized["requestHash"]
    return state
