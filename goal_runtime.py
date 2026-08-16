"""Named, server-owned domain operations for Goal v2.

This module deliberately exposes no HTTP route or model tool.  A later wiring
stage will construct :class:`GoalCreationContext` from the authoritative
foreground AgentRun rather than accepting provenance fields from model input.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goal_v2_protocol import (
    GOAL_V2_SOURCE_KINDS,
    build_event,
    canonical_json,
    require_identifier,
)
from goal_v2_store import GoalV2ConflictError, GoalV2Service


class GoalV2ContextError(ValueError):
    """The supplied server runtime context cannot own a Goal creation."""


@dataclass(frozen=True)
class GoalCreationContext:
    session_id: str
    origin_message_id: str
    client_request_id: str
    owner_run_id: str
    permission_profile: str
    source_kind: str
    is_top_level_foreground: bool = True
    is_child: bool = False
    is_detached: bool = False
    is_parallel: bool = False
    is_background: bool = False


class GoalV2Runtime:
    """Restricted named operations over the Goal v2 event service."""

    def __init__(self, data_root: Path | str, *, service: GoalV2Service | None = None):
        self.service = service or GoalV2Service(data_root)

    @staticmethod
    def _goal_id(session_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(canonical_json({
            "sessionId": session_id,
            "idempotencyKey": idempotency_key,
        }).encode("utf-8")).hexdigest()[:24]
        return f"goal-{digest}"

    @staticmethod
    def _validate_creation_context(
        session_id: str, context: GoalCreationContext,
    ) -> None:
        if session_id != context.session_id:
            raise GoalV2ContextError(
                "Goal creation context belongs to another Session"
            )
        if context.source_kind not in GOAL_V2_SOURCE_KINDS:
            raise GoalV2ContextError("Goal creation sourceKind is unsupported")
        if (
            not context.is_top_level_foreground
            or context.is_child
            or context.is_detached
            or context.is_parallel
            or context.is_background
        ):
            raise GoalV2ContextError(
                "only a top-level ordinary foreground AgentRun may create a Goal"
            )
        require_identifier(context.origin_message_id, "origin_message_id")
        require_identifier(context.client_request_id, "client_request_id")
        require_identifier(context.owner_run_id, "owner_run_id")

    def read(self, session_id: str):
        return self.service.read(session_id)

    def create_goal(
        self,
        session_id: str,
        objective: str,
        *,
        context: GoalCreationContext,
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._validate_creation_context(session_id, context)
        current = self.service.read(session_id)
        if not current.writable:
            # Let the service produce the canonical corruption failure.
            goal_id = self._goal_id(session_id, idempotency_key)
        else:
            goal = current.state.goal
            if goal is not None and goal["lifecycle"] not in {"completed", "cancelled"}:
                if goal["objective"].strip() == str(objective or "").strip():
                    projection = current.projection()
                    projection.update({
                        "accepted": True,
                        "noOp": True,
                        "reused": True,
                    })
                    return projection
                raise GoalV2ConflictError(
                    "the Session already has a different nonterminal Goal"
                )
            goal_id = self._goal_id(session_id, idempotency_key)
        return self.service.append(
            session_id,
            goal_id,
            "goal_created",
            {
                "objective": objective,
                "originMessageId": context.origin_message_id,
                "clientRequestId": context.client_request_id,
                "ownerRunId": context.owner_run_id,
                "sourceKind": context.source_kind,
                "permissionProfile": context.permission_profile,
            },
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent" if context.source_kind == "autonomous" else "user-command",
        )

    def set_plan(
        self, session_id: str, goal_id: str, steps: list[dict[str, Any]], *,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "plan_set",
            {"steps": steps, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def revise_plan(
        self, session_id: str, goal_id: str, *, source_run_id: str,
        expected_revision: int, idempotency_key: str,
        objective: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"sourceRunId": source_run_id}
        if objective is not None:
            payload["objective"] = objective
        if steps is not None:
            payload["steps"] = steps
        return self.service.append(
            session_id, goal_id, "plan_revised", payload,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def start_step(
        self, session_id: str, goal_id: str, step_id: str, *,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "step_started",
            {"stepId": step_id, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def complete_step(
        self, session_id: str, goal_id: str, step_id: str,
        evidence: list[dict[str, Any]], *, source_run_id: str,
        expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "stepId": step_id,
            "sourceRunId": source_run_id,
            "evidence": evidence,
        }
        current = self.service.read(session_id)

        # A persisted retry must choose the same event shape even after the
        # first call advanced or completed the Goal.  Compare the two closed
        # candidates against the stored request hash before inspecting state.
        previous_hash = current.state.idempotency.get(idempotency_key)
        if previous_hash is not None:
            for event_type in ("step_completed", "goal_completed"):
                candidate = build_event(
                    event_id="candidate",
                    event_type=event_type,
                    session_id=session_id,
                    goal_id=goal_id,
                    expected_revision=expected_revision,
                    idempotency_key=idempotency_key,
                    actor="foreground-agent",
                    created_at="1970-01-01T00:00:00",
                    payload=payload,
                )
                if candidate["requestHash"] == previous_hash:
                    return self.service.append(
                        session_id, goal_id, event_type, payload,
                        expected_revision=expected_revision,
                        idempotency_key=idempotency_key,
                        actor="foreground-agent",
                    )
            raise GoalV2ConflictError(
                "idempotency key was already used with a different payload"
            )

        if not current.writable:
            # Preserve the store's canonical fail-closed corruption response.
            return self.service.append(
                session_id, goal_id, "step_completed", payload,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                actor="foreground-agent",
            )
        if current.state.revision != expected_revision:
            raise GoalV2ConflictError(
                f"stale Goal v2 revision: expected {expected_revision}, "
                f"current {current.state.revision}"
            )
        goal = current.state.goal
        if not isinstance(goal, dict) or goal.get("goalId") != goal_id:
            raise GoalV2ConflictError("Goal operation requires the current Goal")
        if goal.get("lifecycle") != "active":
            raise GoalV2ConflictError(
                "goal_complete_step requires an active Goal"
            )
        if goal.get("currentStepId") != step_id:
            raise GoalV2ConflictError(
                "goal_complete_step must target the current step"
            )
        if goal.get("gate") is not None:
            raise GoalV2ConflictError(
                "a gated Goal step cannot be completed"
            )
        step = next(
            (item for item in goal.get("steps") or [] if item.get("id") == step_id),
            None,
        )
        if step is None:
            raise GoalV2ConflictError("goal_complete_step references an unknown step")
        criteria = {
            item["id"]: item for item in step.get("acceptanceCriteria") or []
        }
        evidence_by_criterion = {
            item.get("criterionId"): item for item in evidence
            if isinstance(item, dict)
        }
        if set(evidence_by_criterion) != set(criteria):
            raise GoalV2ConflictError(
                "goal_complete_step requires evidence for every acceptance criterion"
            )
        for criterion_id, criterion in criteria.items():
            if evidence_by_criterion[criterion_id].get("kind") != criterion.get("kind"):
                raise GoalV2ConflictError(
                    "goal_complete_step evidence kind must match its acceptance criterion"
                )

        is_final = bool(goal.get("steps")) and goal["steps"][-1]["id"] == step_id
        event_type = "goal_completed" if is_final else "step_completed"
        return self.service.append(
            session_id, goal_id, event_type, payload,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def raise_gate(
        self, session_id: str, goal_id: str, gate_type: str, summary: str, *,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "gate_raised",
            {
                "gateType": gate_type,
                "summary": summary,
                "sourceRunId": source_run_id,
            },
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def clear_gate(
        self, session_id: str, goal_id: str, *, source_run_id: str,
        expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "gate_cleared",
            {"sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def pause(
        self, session_id: str, goal_id: str, *, reason: str | None,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_paused",
            {"reason": reason, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def resume(
        self, session_id: str, goal_id: str, *, source_run_id: str,
        expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_resumed",
            {"sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def ready_for_acceptance(
        self, session_id: str, goal_id: str, *, summary: str | None,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_ready_for_acceptance",
            {"summary": summary, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def complete_goal(
        self, session_id: str, goal_id: str, *, summary: str | None,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_completed",
            {"summary": summary, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def cancel_goal(
        self, session_id: str, goal_id: str, *, reason: str | None,
        source_run_id: str, expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_cancelled",
            {"reason": reason, "sourceRunId": source_run_id},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="foreground-agent",
        )

    def clear_goal(
        self, session_id: str, goal_id: str, *, reason: str | None,
        expected_revision: int, idempotency_key: str,
    ) -> dict[str, Any]:
        return self.service.append(
            session_id, goal_id, "goal_cleared", {"reason": reason},
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor="user-control",
        )
