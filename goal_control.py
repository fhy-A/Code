"""Restricted explicit user controls for persisted Session Goals.

This module is the only domain layer allowed to translate browser commands into
Goal snapshots.  It deliberately exposes named operations instead of arbitrary
snapshot replacement, and it never creates or resumes an AgentRun.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any, Callable

from goal_protocol import (
    GOAL_PERMISSION_PROFILES,
    GOAL_TERMINAL_LIFECYCLES,
    canonical_json,
    request_hash,
)
from goal_store import GoalConflictError, GoalCorruptionError, GoalService


GOAL_CONTROL_VERSION = 1
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CONTROL_FIELDS = {
    "create_draft": frozenset({
        "operation", "expectedRevision", "idempotencyKey", "objective",
        "permissionProfile", "language",
    }),
    "confirm_draft": frozenset({
        "operation", "expectedRevision", "idempotencyKey", "goalId",
    }),
    "pause": frozenset({
        "operation", "expectedRevision", "idempotencyKey", "goalId",
    }),
    "resume": frozenset({
        "operation", "expectedRevision", "idempotencyKey", "goalId",
    }),
    "propose_change": frozenset({
        "operation", "expectedRevision", "goalId", "proposal",
    }),
    "confirm_change": frozenset({
        "operation", "expectedRevision", "idempotencyKey", "goalId",
        "confirmationToken",
    }),
}
_PROPOSAL_FIELDS = frozenset({"type", "text", "objective", "steps"})
_STEP_PROPOSAL_FIELDS = frozenset({"id", "description", "acceptanceCriteria"})
_CRITERION_PROPOSAL_FIELDS = frozenset({"description", "kind"})
_PROPOSAL_TYPES = frozenset({"supplement", "revise", "cancel", "clear"})


class GoalControlError(ValueError):
    """A public Goal control request is malformed or not allowed."""


class GoalConfirmationError(GoalControlError):
    """A proposed destructive or structural change was not validly confirmed."""


def _default_clock() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GoalControlError(f"{label} must be an object")
    return value


def _reject_unknown(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GoalControlError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _require_text(value: Any, label: str, *, maximum: int = 20_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoalControlError(f"{label} must be a non-empty string")
    text = value.strip()
    if len(text) > maximum:
        raise GoalControlError(f"{label} exceeds {maximum} characters")
    return text


def _require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=128)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise GoalControlError(f"{label} is not a valid identifier")
    return text


def _require_revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoalControlError("expectedRevision must be an integer >= 0")
    return value


def _criterion_id(step_id: str, index: int, description: str) -> str:
    digest = hashlib.sha256(f"{step_id}:{index}:{description}".encode("utf-8")).hexdigest()[:16]
    return f"criterion-{digest}"


def _default_steps(objective: str, language: str) -> list[dict[str, Any]]:
    if language == "en":
        descriptions = [
            "Confirm the Goal scope and bounded completion criteria",
            f"Execute the work required for: {objective}",
            "Verify the result with evidence and obtain final acceptance",
        ]
        criteria = [
            "The user-visible scope and completion boundary are explicit",
            "The requested outcome is implemented without expanding permissions",
            "Machine evidence is recorded and subjective acceptance remains with the user",
        ]
    else:
        descriptions = [
            "确认 Goal 范围与有界完成条件",
            f"执行目标所需工作：{objective}",
            "用证据验收结果并取得最终确认",
        ]
        criteria = [
            "面向用户的范围与完成边界已明确",
            "在不扩大权限的前提下完成所请求结果",
            "机器证据已记录，主观验收仍由用户确认",
        ]
    kinds = ("user", "agent", "user")
    steps = []
    for index, (description, criterion, kind) in enumerate(
        zip(descriptions, criteria, kinds), start=1
    ):
        step_id = f"step-{index}"
        steps.append({
            "id": step_id,
            "description": description,
            "status": "pending",
            "acceptanceCriteria": [{
                "id": _criterion_id(step_id, 1, criterion),
                "description": criterion,
                "kind": kind,
            }],
            "evidence": [],
        })
    return steps


class GoalControlService:
    """Apply a closed set of user controls through one ``GoalService`` writer."""

    def __init__(
        self,
        goal_service: GoalService,
        *,
        confirmation_secret: bytes,
        clock: Callable[[], str] | None = None,
    ):
        if not isinstance(confirmation_secret, bytes) or len(confirmation_secret) < 16:
            raise ValueError("confirmation_secret must contain at least 16 bytes")
        self.goal_service = goal_service
        self.confirmation_secret = confirmation_secret
        self.clock = clock or _default_clock

    def handle(self, session_id: str, request: Any) -> dict[str, Any]:
        session_id = _require_identifier(session_id, "sessionId")
        value = _require_object(request, "Goal control request")
        operation = _require_text(value.get("operation"), "operation", maximum=32)
        allowed = _CONTROL_FIELDS.get(operation)
        if allowed is None:
            raise GoalControlError(f"unsupported Goal control operation: {operation}")
        _reject_unknown(value, allowed, "Goal control request")
        handlers = {
            "create_draft": self._create_draft,
            "confirm_draft": self._confirm_draft,
            "pause": self._pause,
            "resume": self._resume,
            "propose_change": self._propose_change,
            "confirm_change": self._confirm_change,
        }
        return handlers[operation](session_id, value)

    @staticmethod
    def _idempotency_payload(
        operation: str,
        session_id: str,
        expected_revision: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "controlVersion": GOAL_CONTROL_VERSION,
            "operation": operation,
            "sessionId": session_id,
            "expectedRevision": expected_revision,
            "body": body,
        }

    @staticmethod
    def _idempotent_retry(read_result, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        previous = read_result.state.idempotency.get(key)
        if previous is None:
            return None
        digest = request_hash(payload)
        if previous != digest:
            raise GoalConflictError("idempotency key was already used with a different payload")
        projection = read_result.projection()
        projection.update({"accepted": True, "noOp": True})
        return projection

    @staticmethod
    def _require_writable(read_result) -> None:
        if not read_result.writable:
            raise GoalCorruptionError("Goal sidecar is degraded or corrupted; mutation refused")

    @staticmethod
    def _require_goal(read_result, goal_id: str, expected_revision: int) -> dict[str, Any]:
        if read_result.state.revision != expected_revision:
            raise GoalConflictError(
                f"stale Goal revision: expected {expected_revision}, current {read_result.state.revision}"
            )
        goal = read_result.state.goal
        if goal is None:
            raise GoalConflictError("Session has no current Goal")
        if goal["goalId"] != goal_id:
            raise GoalConflictError("goalId does not match the current Goal")
        return copy.deepcopy(goal)

    def _create_draft(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        expected_revision = _require_revision(value.get("expectedRevision"))
        key = _require_identifier(value.get("idempotencyKey"), "idempotencyKey")
        objective = _require_text(value.get("objective"), "objective", maximum=8_000)
        permission = _require_text(value.get("permissionProfile"), "permissionProfile", maximum=32)
        if permission not in GOAL_PERMISSION_PROFILES:
            raise GoalControlError("permissionProfile is unsupported")
        language = value.get("language", "zh")
        if language not in {"zh", "en"}:
            raise GoalControlError("language must be zh or en")
        body = {"objective": objective, "permissionProfile": permission, "language": language}
        idempotency_payload = self._idempotency_payload(
            "create_draft", session_id, expected_revision, body
        )
        read_result = self.goal_service.read(session_id)
        self._require_writable(read_result)
        retry = self._idempotent_retry(read_result, key, idempotency_payload)
        if retry is not None:
            return retry
        if read_result.state.revision != expected_revision:
            raise GoalConflictError(
                f"stale Goal revision: expected {expected_revision}, current {read_result.state.revision}"
            )
        current = read_result.state.goal
        if current is not None and current["lifecycle"] not in GOAL_TERMINAL_LIFECYCLES:
            raise GoalConflictError("a Session may have at most one active Goal")
        now = self.clock()
        goal_id = "goal-" + hashlib.sha256(f"{session_id}:{key}".encode("utf-8")).hexdigest()[:24]
        snapshot = {
            "goalId": goal_id,
            "sessionId": session_id,
            "revision": expected_revision + 1,
            "objective": objective,
            "lifecycle": "awaiting_confirmation",
            "permissionProfile": permission,
            "steps": _default_steps(objective, language),
            "currentStepId": None,
            "runtimeSignals": [],
            "ownerRunId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        return self.goal_service.replace(
            session_id,
            snapshot,
            expected_revision=expected_revision,
            idempotency_key=key,
            idempotency_payload=idempotency_payload,
            actor="user-control",
        )

    def _simple_transition(
        self,
        operation: str,
        session_id: str,
        value: dict[str, Any],
        *,
        from_lifecycles: set[str],
        to_lifecycle: str,
    ) -> dict[str, Any]:
        expected_revision = _require_revision(value.get("expectedRevision"))
        key = _require_identifier(value.get("idempotencyKey"), "idempotencyKey")
        goal_id = _require_identifier(value.get("goalId"), "goalId")
        body = {"goalId": goal_id}
        idempotency_payload = self._idempotency_payload(
            operation, session_id, expected_revision, body
        )
        read_result = self.goal_service.read(session_id)
        self._require_writable(read_result)
        retry = self._idempotent_retry(read_result, key, idempotency_payload)
        if retry is not None:
            return retry
        snapshot = self._require_goal(read_result, goal_id, expected_revision)
        already_applied_lifecycle = {
            "confirm_draft": "active",
            "pause": "paused",
            "resume": "active",
        }.get(operation)
        if snapshot["lifecycle"] == already_applied_lifecycle:
            projection = read_result.projection()
            projection.update({"accepted": True, "noOp": True})
            return projection
        if snapshot["lifecycle"] not in from_lifecycles:
            allowed = ", ".join(sorted(from_lifecycles))
            raise GoalConflictError(f"{operation} requires Goal lifecycle: {allowed}")
        snapshot["revision"] = expected_revision + 1
        snapshot["lifecycle"] = to_lifecycle
        snapshot["updatedAt"] = self.clock()
        if operation == "confirm_draft":
            first_step = snapshot["steps"][0]
            first_step["status"] = "in_progress"
            snapshot["currentStepId"] = first_step["id"]
        return self.goal_service.replace(
            session_id,
            snapshot,
            expected_revision=expected_revision,
            idempotency_key=key,
            idempotency_payload=idempotency_payload,
            actor="user-control",
        )

    def _confirm_draft(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        return self._simple_transition(
            "confirm_draft",
            session_id,
            value,
            from_lifecycles={"awaiting_confirmation"},
            to_lifecycle="active",
        )

    def _pause(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        return self._simple_transition(
            "pause", session_id, value, from_lifecycles={"active"}, to_lifecycle="paused"
        )

    def _resume(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        return self._simple_transition(
            "resume", session_id, value, from_lifecycles={"paused"}, to_lifecycle="active"
        )

    def _normalize_proposal(self, raw: Any, current: dict[str, Any]) -> dict[str, Any]:
        value = _require_object(raw, "proposal")
        _reject_unknown(value, _PROPOSAL_FIELDS, "proposal")
        proposal_type = _require_text(value.get("type"), "proposal.type", maximum=32)
        if proposal_type not in _PROPOSAL_TYPES:
            raise GoalControlError(f"unsupported proposal type: {proposal_type}")
        if proposal_type in {"cancel", "clear"}:
            if set(value) != {"type"}:
                raise GoalControlError(f"{proposal_type} proposal accepts no additional fields")
            return {"type": proposal_type}
        if proposal_type == "supplement":
            if set(value) != {"type", "text"}:
                raise GoalControlError("supplement proposal requires only text")
            return {"type": "supplement", "text": _require_text(value.get("text"), "proposal.text", maximum=2_000)}

        if not ({"objective", "steps"} & set(value)):
            raise GoalControlError("revise proposal requires objective and/or steps")
        normalized: dict[str, Any] = {"type": "revise"}
        if "objective" in value:
            normalized["objective"] = _require_text(
                value.get("objective"), "proposal.objective", maximum=8_000
            )
        if "steps" in value:
            normalized["steps"] = self._normalize_step_proposals(value.get("steps"), current)
        return normalized

    def _normalize_step_proposals(
        self, raw_steps: Any, current: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_steps, list) or not (3 <= len(raw_steps) <= 8):
            raise GoalControlError("proposal.steps must contain 3-8 items")
        existing_steps = current["steps"]
        existing_by_id = {item["id"]: item for item in existing_steps}
        normalized = []
        used_ids: set[str] = set()
        for index, raw in enumerate(raw_steps):
            if isinstance(raw, str):
                item = {"description": raw}
            else:
                item = _require_object(raw, f"proposal.steps[{index}]")
                _reject_unknown(item, _STEP_PROPOSAL_FIELDS, f"proposal.steps[{index}]")
            fallback = existing_steps[index]["id"] if index < len(existing_steps) else f"step-{index + 1}"
            step_id = _require_identifier(item.get("id", fallback), f"proposal.steps[{index}].id")
            if step_id in used_ids:
                raise GoalControlError("proposal.steps contains duplicate ids")
            used_ids.add(step_id)
            previous = existing_by_id.get(step_id)
            description = _require_text(
                item.get("description", previous["description"] if previous else None),
                f"proposal.steps[{index}].description",
                maximum=2_000,
            )
            if "acceptanceCriteria" in item:
                criteria = self._normalize_criteria(item["acceptanceCriteria"], step_id)
            elif previous:
                criteria = copy.deepcopy(previous["acceptanceCriteria"])
            else:
                default = "该步骤有明确、可核验的完成结果"
                criteria = [{
                    "id": _criterion_id(step_id, 1, default),
                    "description": default,
                    "kind": "agent",
                }]
            normalized.append({
                "id": step_id,
                "description": description,
                "status": previous["status"] if previous else "pending",
                "acceptanceCriteria": criteria,
                "evidence": copy.deepcopy(previous["evidence"]) if previous else [],
            })
        return normalized

    @staticmethod
    def _normalize_criteria(raw: Any, step_id: str) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not (1 <= len(raw) <= 8):
            raise GoalControlError("acceptanceCriteria must contain 1-8 items")
        normalized = []
        for index, candidate in enumerate(raw, start=1):
            if isinstance(candidate, str):
                description = _require_text(candidate, "criterion.description", maximum=1_000)
                kind = "agent"
            else:
                value = _require_object(candidate, "criterion")
                _reject_unknown(value, _CRITERION_PROPOSAL_FIELDS, "criterion")
                description = _require_text(value.get("description"), "criterion.description", maximum=1_000)
                kind = value.get("kind", "agent")
                if kind not in {"machine", "agent", "user"}:
                    raise GoalControlError("criterion.kind must be machine, agent, or user")
            normalized.append({
                "id": _criterion_id(step_id, index, description),
                "description": description,
                "kind": kind,
            })
        return normalized

    def _proposal_diff(self, current: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
        proposal_type = proposal["type"]
        if proposal_type == "supplement":
            return {"type": proposal_type, "supplement": proposal["text"]}
        if proposal_type in {"cancel", "clear"}:
            return {"type": proposal_type, "goalId": current["goalId"]}
        def project_steps(steps):
            return [
                {
                    "id": item["id"],
                    "description": item["description"],
                    "acceptanceCriteria": [
                        {"description": criterion["description"], "kind": criterion["kind"]}
                        for criterion in item["acceptanceCriteria"]
                    ],
                }
                for item in steps
            ]

        return {
            "type": proposal_type,
            "objective": {
                "before": current["objective"],
                "after": proposal.get("objective", current["objective"]),
            },
            "steps": {
                "before": project_steps(current["steps"]),
                "after": project_steps(proposal.get("steps", current["steps"])),
            },
        }

    def _sign_proposal(self, payload: dict[str, Any]) -> str:
        raw = canonical_json(payload).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        signature = hmac.new(self.confirmation_secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _verify_proposal(self, token: Any) -> dict[str, Any]:
        token = _require_text(token, "confirmationToken", maximum=200_000)
        try:
            encoded, signature = token.rsplit(".", 1)
        except ValueError as exc:
            raise GoalConfirmationError("confirmation token is malformed") from exc
        expected = hmac.new(
            self.confirmation_secret, encoded.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise GoalConfirmationError("confirmation token signature is invalid")
        try:
            padding = "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(encoded + padding).decode("utf-8"))
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise GoalConfirmationError("confirmation token payload is invalid") from exc
        if not isinstance(payload, dict) or payload.get("controlVersion") != GOAL_CONTROL_VERSION:
            raise GoalConfirmationError("confirmation token version is unsupported")
        return payload

    def _propose_change(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        expected_revision = _require_revision(value.get("expectedRevision"))
        goal_id = _require_identifier(value.get("goalId"), "goalId")
        read_result = self.goal_service.read(session_id)
        self._require_writable(read_result)
        current = self._require_goal(read_result, goal_id, expected_revision)
        proposal = self._normalize_proposal(value.get("proposal"), current)
        if (
            current["lifecycle"] in GOAL_TERMINAL_LIFECYCLES
            and proposal["type"] != "clear"
        ):
            raise GoalConflictError("terminal Goals cannot be changed")
        payload = {
            "controlVersion": GOAL_CONTROL_VERSION,
            "sessionId": session_id,
            "goalId": goal_id,
            "expectedRevision": expected_revision,
            "proposal": proposal,
        }
        return {
            "accepted": False,
            "requiresConfirmation": True,
            "revision": expected_revision,
            "goalId": goal_id,
            "proposal": proposal,
            "diff": self._proposal_diff(current, proposal),
            "confirmationToken": self._sign_proposal(payload),
        }

    def _apply_proposal(
        self, current: dict[str, Any], proposal: dict[str, Any], revision: int
    ) -> dict[str, Any]:
        snapshot = copy.deepcopy(current)
        snapshot["revision"] = revision
        snapshot["updatedAt"] = self.clock()
        proposal_type = proposal["type"]
        if proposal_type == "supplement":
            snapshot["objective"] = f"{snapshot['objective']}\n\n补充：{proposal['text']}"
        elif proposal_type == "revise":
            if "objective" in proposal:
                snapshot["objective"] = proposal["objective"]
            if "steps" in proposal:
                snapshot["steps"] = copy.deepcopy(proposal["steps"])
                current_ids = [item["id"] for item in snapshot["steps"] if item["status"] == "in_progress"]
                snapshot["currentStepId"] = current_ids[0] if current_ids else None
        elif proposal_type == "cancel":
            snapshot["lifecycle"] = "cancelled"
        return snapshot

    def _confirm_change(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        expected_revision = _require_revision(value.get("expectedRevision"))
        key = _require_identifier(value.get("idempotencyKey"), "idempotencyKey")
        goal_id = _require_identifier(value.get("goalId"), "goalId")
        payload = self._verify_proposal(value.get("confirmationToken"))
        if (
            payload.get("sessionId") != session_id
            or payload.get("goalId") != goal_id
            or payload.get("expectedRevision") != expected_revision
        ):
            raise GoalConfirmationError("confirmation token does not match the current request")
        proposal = payload.get("proposal")
        if not isinstance(proposal, dict):
            raise GoalConfirmationError("confirmation token contains no proposal")
        idempotency_body = {"goalId": goal_id, "proposal": proposal}
        idempotency_payload = self._idempotency_payload(
            "confirm_change", session_id, expected_revision, idempotency_body
        )
        read_result = self.goal_service.read(session_id)
        self._require_writable(read_result)
        retry = self._idempotent_retry(read_result, key, idempotency_payload)
        if retry is not None:
            return retry
        current = self._require_goal(read_result, goal_id, expected_revision)
        if (
            current["lifecycle"] in GOAL_TERMINAL_LIFECYCLES
            and proposal.get("type") != "clear"
        ):
            raise GoalConflictError("terminal Goals cannot be changed")
        normalized = proposal
        if normalized.get("type") not in _PROPOSAL_TYPES:
            raise GoalConfirmationError("confirmation proposal is not canonical")
        if normalized["type"] == "clear":
            return self.goal_service.clear(
                session_id,
                goal_id,
                expected_revision=expected_revision,
                idempotency_key=key,
                idempotency_payload=idempotency_payload,
                actor="user-control",
            )
        snapshot = self._apply_proposal(current, normalized, expected_revision + 1)
        return self.goal_service.replace(
            session_id,
            snapshot,
            expected_revision=expected_revision,
            idempotency_key=key,
            idempotency_payload=idempotency_payload,
            actor="user-control",
        )
