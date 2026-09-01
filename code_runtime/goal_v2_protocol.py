"""Goal v2 append-only event protocol and deterministic reducer.

Goal v2 intentionally does not read or fold Goal v1 snapshots.  A Goal may be
created from a user message before a plan exists; later named events add the
plan and advance it without replacing the whole trusted state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


GOAL_V2_PROTOCOL_VERSION = 2
GOAL_V2_EVENT_TYPES = frozenset({
    "goal_created",
    "plan_set",
    "plan_revised",
    "step_started",
    "step_completed",
    "gate_raised",
    "gate_cleared",
    "goal_paused",
    "goal_resumed",
    "goal_ready_for_acceptance",
    "goal_completed",
    "goal_cancelled",
    "goal_cleared",
})
GOAL_V2_STEP_STATUSES = frozenset({"pending", "in_progress", "completed"})
GOAL_V2_LIFECYCLES = frozenset({
    "draft",
    "active",
    "paused",
    "ready_for_acceptance",
    "completed",
    "cancelled",
})
GOAL_V2_TERMINAL_LIFECYCLES = frozenset({"completed", "cancelled"})
GOAL_V2_GATE_TYPES = frozenset({"waiting_user", "blocked", "failed"})
GOAL_V2_SOURCE_KINDS = frozenset({"explicit", "autonomous"})
GOAL_V2_PERMISSION_PROFILES = frozenset({"read", "plan", "accept", "bypass"})
GOAL_V2_EVIDENCE_KINDS = frozenset({"machine", "agent", "user"})

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_MAX_OBJECTIVE_LENGTH = 20_000
_MAX_DESCRIPTION_LENGTH = 4_000
_MAX_SUMMARY_LENGTH = 2_000
_MAX_CRITERIA_PER_STEP = 20
_MAX_EVIDENCE_PER_STEP = 100
_EVENT_FIELDS = frozenset({
    "protocolVersion",
    "eventId",
    "type",
    "sessionId",
    "goalId",
    "revision",
    "expectedRevision",
    "idempotencyKey",
    "requestHash",
    "actor",
    "createdAt",
    "payload",
})
_STEP_PLAN_FIELDS = frozenset({"id", "description", "acceptanceCriteria"})
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
_PAYLOAD_FIELDS = {
    "goal_created": frozenset({
        "objective", "originMessageId", "clientRequestId", "ownerRunId",
        "sourceKind", "permissionProfile",
    }),
    "plan_set": frozenset({"steps", "sourceRunId"}),
    "plan_revised": frozenset({"objective", "steps", "sourceRunId"}),
    "step_started": frozenset({"stepId", "sourceRunId"}),
    "step_completed": frozenset({"stepId", "sourceRunId", "evidence"}),
    "gate_raised": frozenset({"gateType", "summary", "sourceRunId"}),
    "gate_cleared": frozenset({"sourceRunId"}),
    "goal_paused": frozenset({"reason", "sourceRunId"}),
    "goal_resumed": frozenset({"sourceRunId"}),
    "goal_ready_for_acceptance": frozenset({"summary", "sourceRunId"}),
    # Legacy ``ready_for_acceptance`` records use ``summary``.  New direct
    # completion records carry the final step evidence so the step and Goal
    # cross the durability boundary in one event/revision.
    "goal_completed": frozenset({
        "summary", "sourceRunId", "stepId", "evidence",
    }),
    "goal_cancelled": frozenset({"reason", "sourceRunId"}),
    "goal_cleared": frozenset({"reason"}),
}


class GoalV2ProtocolError(ValueError):
    """The persisted or proposed Goal v2 value is malformed."""


class GoalV2TransitionError(GoalV2ProtocolError):
    """A valid Goal v2 event is illegal for the current fold state."""


@dataclass
class GoalV2FoldState:
    """Trusted state obtained exclusively by folding Goal v2 events."""

    session_id: str
    revision: int = 0
    goal: dict[str, Any] | None = None
    tombstone: dict[str, Any] | None = None
    last_event_id: str | None = None
    used_goal_ids: set[str] = field(default_factory=set)
    event_ids: set[str] = field(default_factory=set)
    idempotency: dict[str, str] = field(default_factory=dict)
    paused_from: str | None = None

    def projection(self) -> dict[str, Any]:
        return {
            "protocolVersion": GOAL_V2_PROTOCOL_VERSION,
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
        raise GoalV2ProtocolError(f"{label} must be an object")
    return value


def _reject_unknown_fields(
    value: dict[str, Any], allowed: frozenset[str], label: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GoalV2ProtocolError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _require_text(
    value: Any, label: str, *, maximum: int, allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise GoalV2ProtocolError(f"{label} must be a string")
    if not allow_empty and not value.strip():
        raise GoalV2ProtocolError(f"{label} must not be empty")
    if len(value) > maximum:
        raise GoalV2ProtocolError(f"{label} exceeds {maximum} characters")
    return value


def _optional_text(value: Any, label: str, *, maximum: int) -> str | None:
    if value in (None, ""):
        return None
    return _require_text(value, label, maximum=maximum)


def require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=128)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise GoalV2ProtocolError(f"{label} is not a valid identifier")
    return text


def _optional_identifier(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return require_identifier(value, label)


def require_revision(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GoalV2ProtocolError(f"{label} must be an integer >= {minimum}")
    return value


def _normalize_criterion(value: Any, step_id: str) -> dict[str, Any]:
    criterion = _require_dict(value, f"step {step_id} criterion")
    _reject_unknown_fields(criterion, _CRITERION_FIELDS, f"step {step_id} criterion")
    criterion_id = require_identifier(
        criterion.get("id"), f"step {step_id} criterion.id"
    )
    kind = _require_text(
        criterion.get("kind"), f"criterion {criterion_id}.kind", maximum=32
    )
    if kind not in GOAL_V2_EVIDENCE_KINDS:
        raise GoalV2ProtocolError(f"criterion {criterion_id}.kind is unsupported")
    return {
        "id": criterion_id,
        "description": _require_text(
            criterion.get("description"),
            f"criterion {criterion_id}.description",
            maximum=_MAX_DESCRIPTION_LENGTH,
        ),
        "kind": kind,
    }


def normalize_plan_steps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not (3 <= len(value) <= 8):
        raise GoalV2ProtocolError("plan steps must contain 3-8 product-level steps")
    normalized: list[dict[str, Any]] = []
    for raw_step in value:
        step = _require_dict(raw_step, "plan step")
        _reject_unknown_fields(step, _STEP_PLAN_FIELDS, "plan step")
        step_id = require_identifier(step.get("id"), "plan step.id")
        criteria = step.get("acceptanceCriteria")
        if not isinstance(criteria, list) or not (1 <= len(criteria) <= _MAX_CRITERIA_PER_STEP):
            raise GoalV2ProtocolError(
                f"step {step_id}.acceptanceCriteria must contain "
                f"1-{_MAX_CRITERIA_PER_STEP} items"
            )
        normalized_criteria = [_normalize_criterion(item, step_id) for item in criteria]
        criterion_ids = [item["id"] for item in normalized_criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise GoalV2ProtocolError(f"step {step_id} contains duplicate criterion ids")
        normalized.append({
            "id": step_id,
            "description": _require_text(
                step.get("description"),
                f"step {step_id}.description",
                maximum=_MAX_DESCRIPTION_LENGTH,
            ),
            "acceptanceCriteria": normalized_criteria,
        })
    step_ids = [item["id"] for item in normalized]
    if len(set(step_ids)) != len(step_ids):
        raise GoalV2ProtocolError("plan contains duplicate step ids")
    return normalized


def _normalize_evidence(
    value: Any, step_id: str, criterion_ids: set[str],
) -> dict[str, Any]:
    evidence = _require_dict(value, f"step {step_id} evidence")
    _reject_unknown_fields(evidence, _EVIDENCE_FIELDS, f"step {step_id} evidence")
    evidence_id = require_identifier(evidence.get("id"), f"step {step_id} evidence.id")
    criterion_id = require_identifier(
        evidence.get("criterionId"), f"evidence {evidence_id}.criterionId"
    )
    if criterion_id not in criterion_ids:
        raise GoalV2ProtocolError(
            f"evidence {evidence_id} references an unknown criterion"
        )
    kind = _require_text(
        evidence.get("kind"), f"evidence {evidence_id}.kind", maximum=32
    )
    if kind not in GOAL_V2_EVIDENCE_KINDS:
        raise GoalV2ProtocolError(f"evidence {evidence_id}.kind is unsupported")
    digest = evidence.get("artifactDigest")
    if digest not in (None, ""):
        digest = _require_text(
            digest, f"evidence {evidence_id}.artifactDigest", maximum=64
        )
        if not _SHA256_RE.fullmatch(digest):
            raise GoalV2ProtocolError(
                f"evidence {evidence_id}.artifactDigest must be lowercase SHA-256"
            )
    else:
        digest = None
    return {
        "id": evidence_id,
        "criterionId": criterion_id,
        "kind": kind,
        "summary": _require_text(
            evidence.get("summary"),
            f"evidence {evidence_id}.summary",
            maximum=_MAX_SUMMARY_LENGTH,
        ),
        "sourceRunId": _optional_identifier(
            evidence.get("sourceRunId"), f"evidence {evidence_id}.sourceRunId"
        ),
        "sourceToolCallId": _optional_identifier(
            evidence.get("sourceToolCallId"),
            f"evidence {evidence_id}.sourceToolCallId",
        ),
        "artifactDigest": digest,
        "recordedAt": _require_text(
            evidence.get("recordedAt"),
            f"evidence {evidence_id}.recordedAt",
            maximum=64,
        ),
    }


def _normalize_payload(event_type: str, value: Any) -> dict[str, Any]:
    payload = _require_dict(value, f"{event_type} payload")
    _reject_unknown_fields(payload, _PAYLOAD_FIELDS[event_type], f"{event_type} payload")
    source_run_id = lambda: _optional_identifier(
        payload.get("sourceRunId"), f"{event_type} payload.sourceRunId"
    )
    if event_type == "goal_created":
        source_kind = _require_text(
            payload.get("sourceKind"), "goal_created payload.sourceKind", maximum=32
        )
        if source_kind not in GOAL_V2_SOURCE_KINDS:
            raise GoalV2ProtocolError("goal_created payload.sourceKind is unsupported")
        permission = _require_text(
            payload.get("permissionProfile"),
            "goal_created payload.permissionProfile",
            maximum=32,
        )
        if permission not in GOAL_V2_PERMISSION_PROFILES:
            raise GoalV2ProtocolError(
                "goal_created payload.permissionProfile is unsupported"
            )
        return {
            "objective": _require_text(
                payload.get("objective"),
                "goal_created payload.objective",
                maximum=_MAX_OBJECTIVE_LENGTH,
            ),
            "originMessageId": require_identifier(
                payload.get("originMessageId"),
                "goal_created payload.originMessageId",
            ),
            "clientRequestId": require_identifier(
                payload.get("clientRequestId"),
                "goal_created payload.clientRequestId",
            ),
            "ownerRunId": require_identifier(
                payload.get("ownerRunId"),
                "goal_created payload.ownerRunId",
            ),
            "sourceKind": source_kind,
            "permissionProfile": permission,
        }
    if event_type == "plan_set":
        return {
            "steps": normalize_plan_steps(payload.get("steps")),
            "sourceRunId": source_run_id(),
        }
    if event_type == "plan_revised":
        if "objective" not in payload and "steps" not in payload:
            raise GoalV2ProtocolError(
                "plan_revised payload requires objective and/or steps"
            )
        result = {"sourceRunId": source_run_id()}
        if "objective" in payload:
            result["objective"] = _require_text(
                payload.get("objective"),
                "plan_revised payload.objective",
                maximum=_MAX_OBJECTIVE_LENGTH,
            )
        if "steps" in payload:
            result["steps"] = normalize_plan_steps(payload.get("steps"))
        return result
    if event_type in {"step_started", "step_completed"}:
        result = {
            "stepId": require_identifier(
                payload.get("stepId"), f"{event_type} payload.stepId"
            ),
            "sourceRunId": source_run_id(),
        }
        if event_type == "step_completed":
            evidence = payload.get("evidence")
            if not isinstance(evidence, list) or not (1 <= len(evidence) <= _MAX_EVIDENCE_PER_STEP):
                raise GoalV2ProtocolError(
                    f"step_completed payload.evidence must contain "
                    f"1-{_MAX_EVIDENCE_PER_STEP} items"
                )
            # Criterion references are checked against the current step by the reducer.
            result["evidence"] = copy.deepcopy(evidence)
        return result
    if event_type == "gate_raised":
        gate_type = _require_text(
            payload.get("gateType"), "gate_raised payload.gateType", maximum=32
        )
        if gate_type not in GOAL_V2_GATE_TYPES:
            raise GoalV2ProtocolError("gate_raised payload.gateType is unsupported")
        return {
            "gateType": gate_type,
            "summary": _require_text(
                payload.get("summary"),
                "gate_raised payload.summary",
                maximum=_MAX_SUMMARY_LENGTH,
            ),
            "sourceRunId": source_run_id(),
        }
    if event_type in {"gate_cleared", "goal_resumed"}:
        return {"sourceRunId": source_run_id()}
    if event_type == "goal_completed" and (
        "stepId" in payload or "evidence" in payload
    ):
        evidence = payload.get("evidence")
        if not isinstance(evidence, list) or not (1 <= len(evidence) <= _MAX_EVIDENCE_PER_STEP):
            raise GoalV2ProtocolError(
                "goal_completed payload.evidence must contain "
                f"1-{_MAX_EVIDENCE_PER_STEP} items"
            )
        return {
            "stepId": require_identifier(
                payload.get("stepId"), "goal_completed payload.stepId"
            ),
            "sourceRunId": source_run_id(),
            # Criterion references are checked against the final step below.
            "evidence": copy.deepcopy(evidence),
        }
    if event_type in {
        "goal_paused", "goal_ready_for_acceptance", "goal_completed", "goal_cancelled",
    }:
        label = "reason" if event_type in {"goal_paused", "goal_cancelled"} else "summary"
        return {
            label: _optional_text(
                payload.get(label), f"{event_type} payload.{label}", maximum=_MAX_SUMMARY_LENGTH
            ),
            "sourceRunId": source_run_id(),
        }
    if event_type == "goal_cleared":
        return {
            "reason": _optional_text(
                payload.get("reason"), "goal_cleared payload.reason", maximum=_MAX_SUMMARY_LENGTH
            )
        }
    raise GoalV2ProtocolError(f"unsupported Goal v2 event type: {event_type}")


def mutation_payload(
    event_type: str,
    session_id: str,
    goal_id: str,
    expected_revision: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": event_type,
        "sessionId": session_id,
        "goalId": goal_id,
        "expectedRevision": expected_revision,
        "payload": payload,
    }


def build_event(
    *,
    event_id: str,
    event_type: str,
    session_id: str,
    goal_id: str,
    expected_revision: int,
    idempotency_key: str,
    actor: str,
    created_at: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if event_type not in GOAL_V2_EVENT_TYPES:
        raise GoalV2ProtocolError(f"unsupported Goal v2 event type: {event_type}")
    normalized_session_id = require_identifier(session_id, "goal event.sessionId")
    normalized_goal_id = require_identifier(goal_id, "goal event.goalId")
    expected_revision = require_revision(
        expected_revision, "goal event.expectedRevision", allow_zero=True
    )
    normalized_payload = _normalize_payload(event_type, payload)
    desired = mutation_payload(
        event_type,
        normalized_session_id,
        normalized_goal_id,
        expected_revision,
        normalized_payload,
    )
    event = {
        "protocolVersion": GOAL_V2_PROTOCOL_VERSION,
        "eventId": require_identifier(event_id, "goal event.eventId"),
        "type": event_type,
        "sessionId": normalized_session_id,
        "goalId": normalized_goal_id,
        "revision": expected_revision + 1,
        "expectedRevision": expected_revision,
        "idempotencyKey": require_identifier(
            idempotency_key, "goal event.idempotencyKey"
        ),
        "requestHash": request_hash(desired),
        "actor": _require_text(actor, "goal event.actor", maximum=64),
        "createdAt": _require_text(
            created_at, "goal event.createdAt", maximum=64
        ),
        "payload": normalized_payload,
    }
    return event


def validate_event(
    event: Any, *, session_id: str | None = None,
) -> dict[str, Any]:
    value = _require_dict(event, "goal event")
    _reject_unknown_fields(value, _EVENT_FIELDS, "goal event")
    if value.get("protocolVersion") != GOAL_V2_PROTOCOL_VERSION:
        raise GoalV2ProtocolError(
            f"unsupported Goal protocol version: {value.get('protocolVersion')!r}"
        )
    event_type = _require_text(value.get("type"), "goal event.type", maximum=64)
    if event_type not in GOAL_V2_EVENT_TYPES:
        raise GoalV2ProtocolError(f"unsupported Goal v2 event type: {event_type}")
    event_session_id = require_identifier(value.get("sessionId"), "goal event.sessionId")
    if session_id is not None and event_session_id != session_id:
        raise GoalV2ProtocolError("goal event sessionId does not match its sidecar")
    expected_revision = require_revision(
        value.get("expectedRevision"),
        "goal event.expectedRevision",
        allow_zero=True,
    )
    revision = require_revision(value.get("revision"), "goal event.revision")
    if revision != expected_revision + 1:
        raise GoalV2ProtocolError(
            "goal event revision must equal expectedRevision + 1"
        )
    normalized_payload = _normalize_payload(event_type, value.get("payload"))
    digest = _require_text(
        value.get("requestHash"), "goal event.requestHash", maximum=64
    )
    if not _SHA256_RE.fullmatch(digest):
        raise GoalV2ProtocolError(
            "goal event.requestHash must be lowercase SHA-256"
        )
    normalized = {
        "protocolVersion": GOAL_V2_PROTOCOL_VERSION,
        "eventId": require_identifier(value.get("eventId"), "goal event.eventId"),
        "type": event_type,
        "sessionId": event_session_id,
        "goalId": require_identifier(value.get("goalId"), "goal event.goalId"),
        "revision": revision,
        "expectedRevision": expected_revision,
        "idempotencyKey": require_identifier(
            value.get("idempotencyKey"), "goal event.idempotencyKey"
        ),
        "requestHash": digest,
        "actor": _require_text(value.get("actor"), "goal event.actor", maximum=64),
        "createdAt": _require_text(
            value.get("createdAt"), "goal event.createdAt", maximum=64
        ),
        "payload": normalized_payload,
    }
    expected_hash = request_hash(mutation_payload(
        event_type,
        event_session_id,
        normalized["goalId"],
        expected_revision,
        normalized_payload,
    ))
    if digest != expected_hash:
        raise GoalV2ProtocolError(
            "goal event.requestHash does not match its mutation payload"
        )
    return normalized


def _require_current_goal(state: GoalV2FoldState, goal_id: str) -> dict[str, Any]:
    if state.goal is None:
        raise GoalV2TransitionError("Goal v2 event requires a current Goal")
    if state.goal["goalId"] != goal_id:
        raise GoalV2TransitionError("Goal v2 event goalId does not match the current Goal")
    return state.goal


def _require_nonterminal(goal: dict[str, Any]) -> None:
    if goal["lifecycle"] in GOAL_V2_TERMINAL_LIFECYCLES:
        raise GoalV2TransitionError("terminal Goals cannot be changed")


def _materialize_plan_steps(plan_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **copy.deepcopy(step),
            "status": "pending",
            "evidence": [],
        }
        for step in plan_steps
    ]


def _apply_plan_revision(
    goal: dict[str, Any], plan_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    previous = {step["id"]: step for step in goal["steps"]}
    revised: list[dict[str, Any]] = []
    for definition in plan_steps:
        old = previous.get(definition["id"])
        if old is None:
            revised.append({**copy.deepcopy(definition), "status": "pending", "evidence": []})
            continue
        if old["status"] != "pending":
            if old["description"] != definition["description"]:
                raise GoalV2TransitionError(
                    f"started step {old['id']} cannot change description"
                )
            if old["acceptanceCriteria"] != definition["acceptanceCriteria"]:
                raise GoalV2TransitionError(
                    f"started step {old['id']} cannot change acceptance criteria"
                )
        revised.append({
            **copy.deepcopy(definition),
            "status": old["status"],
            "evidence": copy.deepcopy(old["evidence"]),
        })
    revised_ids = {step["id"] for step in revised}
    for old in goal["steps"]:
        if old["status"] != "pending" and old["id"] not in revised_ids:
            raise GoalV2TransitionError(
                f"started step {old['id']} cannot disappear from a revised plan"
            )
    started_before = [
        step["id"] for step in goal["steps"] if step["status"] != "pending"
    ]
    started_after = [
        step["id"] for step in revised if step["status"] != "pending"
    ]
    if started_after != started_before:
        raise GoalV2TransitionError("started steps cannot be reordered")
    return revised


def apply_event(state: GoalV2FoldState, event: Any) -> GoalV2FoldState:
    normalized = validate_event(event, session_id=state.session_id)
    if normalized["revision"] != state.revision + 1:
        raise GoalV2TransitionError("Goal v2 event revision is not contiguous")
    if normalized["expectedRevision"] != state.revision:
        raise GoalV2TransitionError(
            "Goal v2 event expectedRevision does not match fold state"
        )
    if normalized["eventId"] in state.event_ids:
        raise GoalV2TransitionError("duplicate eventId in persisted Goal v2 history")
    key = normalized["idempotencyKey"]
    if key in state.idempotency:
        raise GoalV2TransitionError(
            "duplicate idempotency key in persisted Goal v2 history"
        )

    event_type = normalized["type"]
    goal_id = normalized["goalId"]
    payload = normalized["payload"]
    timestamp = normalized["createdAt"]

    if event_type == "goal_created":
        if goal_id in state.used_goal_ids:
            raise GoalV2TransitionError("historical Goal v2 goalId cannot be reused")
        if state.goal is not None and state.goal["lifecycle"] not in GOAL_V2_TERMINAL_LIFECYCLES:
            raise GoalV2TransitionError("a Session may have at most one active Goal")
        state.goal = {
            "goalId": goal_id,
            "sessionId": state.session_id,
            "revision": normalized["revision"],
            "objective": payload["objective"],
            "originMessageId": payload["originMessageId"],
            "clientRequestId": payload["clientRequestId"],
            "sourceKind": payload["sourceKind"],
            "permissionProfile": payload["permissionProfile"],
            "lifecycle": "draft",
            "steps": [],
            "currentStepId": None,
            "gate": None,
            "ownerRunId": payload["ownerRunId"],
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        state.tombstone = None
        state.paused_from = None
        state.used_goal_ids.add(goal_id)
    elif event_type == "goal_cleared":
        goal = _require_current_goal(state, goal_id)
        state.goal = None
        state.tombstone = {
            "goalId": goal_id,
            "revision": normalized["revision"],
            "eventId": normalized["eventId"],
            "originMessageId": goal["originMessageId"],
            "clearedAt": timestamp,
            "reason": payload["reason"],
        }
        state.paused_from = None
    else:
        goal = _require_current_goal(state, goal_id)
        _require_nonterminal(goal)
        if event_type == "plan_set":
            if goal["steps"]:
                raise GoalV2TransitionError("plan_set requires a Goal without a plan")
            if goal["lifecycle"] != "draft":
                raise GoalV2TransitionError("plan_set requires a draft Goal")
            goal["steps"] = _materialize_plan_steps(payload["steps"])
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "plan_revised":
            if not goal["steps"]:
                raise GoalV2TransitionError("plan_revised requires an existing plan")
            if goal["lifecycle"] == "paused":
                raise GoalV2TransitionError("paused Goals must be resumed before plan revision")
            if "objective" in payload:
                goal["objective"] = payload["objective"]
            if "steps" in payload:
                goal["steps"] = _apply_plan_revision(goal, payload["steps"])
                if goal["lifecycle"] == "ready_for_acceptance" and any(
                    step["status"] != "completed" for step in goal["steps"]
                ):
                    goal["lifecycle"] = "active"
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "step_started":
            if goal["lifecycle"] not in {"draft", "active"}:
                raise GoalV2TransitionError("step_started requires a draft or active Goal")
            if not goal["steps"]:
                raise GoalV2TransitionError("step_started requires an established plan")
            if goal["currentStepId"] is not None:
                raise GoalV2TransitionError("another Goal step is already in progress")
            if goal["gate"] is not None:
                raise GoalV2TransitionError("a gated Goal cannot start another step")
            by_id = {step["id"]: step for step in goal["steps"]}
            step = by_id.get(payload["stepId"])
            if step is None:
                raise GoalV2TransitionError("step_started references an unknown step")
            if step["status"] != "pending":
                raise GoalV2TransitionError("step_started requires a pending step")
            position = goal["steps"].index(step)
            if any(item["status"] != "completed" for item in goal["steps"][:position]):
                raise GoalV2TransitionError("Goal steps must start in plan order")
            step["status"] = "in_progress"
            goal["currentStepId"] = step["id"]
            goal["lifecycle"] = "active"
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "step_completed":
            if goal["lifecycle"] != "active":
                raise GoalV2TransitionError("step_completed requires an active Goal")
            if goal["currentStepId"] != payload["stepId"]:
                raise GoalV2TransitionError("step_completed must target the current step")
            step = next(
                item for item in goal["steps"] if item["id"] == payload["stepId"]
            )
            criterion_ids = {item["id"] for item in step["acceptanceCriteria"]}
            evidence = [
                _normalize_evidence(item, step["id"], criterion_ids)
                for item in payload["evidence"]
            ]
            evidence_ids = [item["id"] for item in evidence]
            if len(set(evidence_ids)) != len(evidence_ids):
                raise GoalV2TransitionError("step_completed contains duplicate evidence ids")
            covered = {item["criterionId"] for item in evidence}
            if covered != criterion_ids:
                raise GoalV2TransitionError(
                    "step_completed requires evidence for every acceptance criterion"
                )
            step["status"] = "completed"
            step["evidence"] = evidence
            goal["currentStepId"] = None
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "gate_raised":
            if goal["gate"] is not None:
                raise GoalV2TransitionError("Goal already has an unresolved gate")
            goal["gate"] = {
                "type": payload["gateType"],
                "summary": payload["summary"],
                "sourceRunId": payload["sourceRunId"],
                "raisedAt": timestamp,
            }
        elif event_type == "gate_cleared":
            if goal["gate"] is None:
                raise GoalV2TransitionError("Goal has no gate to clear")
            goal["gate"] = None
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "goal_paused":
            if goal["lifecycle"] not in {"draft", "active", "ready_for_acceptance"}:
                raise GoalV2TransitionError("goal_paused requires a running Goal lifecycle")
            state.paused_from = goal["lifecycle"]
            goal["lifecycle"] = "paused"
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "goal_resumed":
            if goal["lifecycle"] != "paused" or state.paused_from is None:
                raise GoalV2TransitionError("goal_resumed requires a paused Goal")
            goal["lifecycle"] = state.paused_from
            state.paused_from = None
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "goal_ready_for_acceptance":
            if goal["lifecycle"] not in {"draft", "active"}:
                raise GoalV2TransitionError(
                    "goal_ready_for_acceptance requires a draft or active Goal"
                )
            if not goal["steps"] or any(
                step["status"] != "completed" for step in goal["steps"]
            ):
                raise GoalV2TransitionError(
                    "goal_ready_for_acceptance requires every step to be completed"
                )
            if goal["gate"] is not None:
                raise GoalV2TransitionError(
                    "a gated Goal cannot become ready for acceptance"
                )
            goal["lifecycle"] = "ready_for_acceptance"
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "goal_completed":
            if "stepId" in payload:
                if goal["lifecycle"] != "active":
                    raise GoalV2TransitionError(
                        "direct goal_completed requires an active Goal"
                    )
                if goal["gate"] is not None:
                    raise GoalV2TransitionError(
                        "a gated Goal cannot complete its final step"
                    )
                if goal["currentStepId"] != payload["stepId"]:
                    raise GoalV2TransitionError(
                        "direct goal_completed must target the current step"
                    )
                step = next(
                    item for item in goal["steps"]
                    if item["id"] == payload["stepId"]
                )
                if goal["steps"][-1]["id"] != step["id"] or any(
                    item["status"] != "completed" for item in goal["steps"][:-1]
                ):
                    raise GoalV2TransitionError(
                        "direct goal_completed requires the final planned step"
                    )
                criterion_ids = {
                    item["id"] for item in step["acceptanceCriteria"]
                }
                evidence = [
                    _normalize_evidence(item, step["id"], criterion_ids)
                    for item in payload["evidence"]
                ]
                evidence_ids = [item["id"] for item in evidence]
                if len(set(evidence_ids)) != len(evidence_ids):
                    raise GoalV2TransitionError(
                        "goal_completed contains duplicate evidence ids"
                    )
                covered = {item["criterionId"] for item in evidence}
                if covered != criterion_ids:
                    raise GoalV2TransitionError(
                        "goal_completed requires evidence for every final-step "
                        "acceptance criterion"
                    )
                step["status"] = "completed"
                step["evidence"] = evidence
                goal["currentStepId"] = None
            else:
                # Compatibility-only fold for already persisted v2 records.
                if goal["lifecycle"] != "ready_for_acceptance":
                    raise GoalV2TransitionError(
                        "goal_completed requires a Goal ready for acceptance"
                    )
                if goal["gate"] is not None:
                    raise GoalV2TransitionError(
                        "a gated Goal cannot be completed"
                    )
            goal["lifecycle"] = "completed"
            goal["ownerRunId"] = payload["sourceRunId"]
        elif event_type == "goal_cancelled":
            goal["lifecycle"] = "cancelled"
            goal["ownerRunId"] = payload["sourceRunId"]
            state.paused_from = None
        else:
            raise GoalV2TransitionError(f"unhandled Goal v2 event type: {event_type}")
        goal["revision"] = normalized["revision"]
        goal["updatedAt"] = timestamp

    state.revision = normalized["revision"]
    state.last_event_id = normalized["eventId"]
    state.event_ids.add(normalized["eventId"])
    state.idempotency[key] = normalized["requestHash"]
    return state
