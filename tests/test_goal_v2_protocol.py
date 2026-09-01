from __future__ import annotations

import pytest

from code_runtime.goal_runtime import GoalCreationContext, GoalV2ContextError, GoalV2Runtime
from code_runtime.goal_v2_protocol import (
    GOAL_V2_PROTOCOL_VERSION,
    GoalV2FoldState,
    GoalV2ProtocolError,
    GoalV2TransitionError,
    apply_event,
    build_event,
)
from code_runtime.goal_v2_store import GoalV2ConflictError, GoalV2Service


SESSION_ID = "session-v2-alpha"
GOAL_ID = "goal-v2-alpha"
RUN_ID = "run-v2-alpha"


def _steps() -> list[dict]:
    return [
        {
            "id": f"step-{index}",
            "description": f"Product step {index}",
            "acceptanceCriteria": [
                {
                    "id": f"criterion-{index}",
                    "description": f"Criterion {index} is satisfied",
                    "kind": "machine",
                }
            ],
        }
        for index in range(1, 4)
    ]


def _evidence(index: int) -> list[dict]:
    return [
        {
            "id": f"evidence-{index}",
            "criterionId": f"criterion-{index}",
            "kind": "machine",
            "summary": f"Criterion {index} passed",
            "sourceRunId": RUN_ID,
            "sourceToolCallId": f"tool-{index}",
            "artifactDigest": "a" * 64,
            "recordedAt": "2026-08-15T12:00:00+08:00",
        }
    ]


def _append(
    state: GoalV2FoldState,
    event_type: str,
    payload: dict,
    *,
    goal_id: str = GOAL_ID,
    key: str | None = None,
) -> dict:
    event = build_event(
        event_id=f"event-{state.revision + 1}",
        event_type=event_type,
        session_id=state.session_id,
        goal_id=goal_id,
        expected_revision=state.revision,
        idempotency_key=key or f"key-{state.revision + 1}",
        actor="test",
        created_at=f"2026-08-15T12:00:{state.revision:02d}+08:00",
        payload=payload,
    )
    apply_event(state, event)
    return event


def _create_payload(source_kind: str = "explicit") -> dict:
    return {
        "objective": "Build a durable long-running Goal",
        "originMessageId": "message-origin-1",
        "clientRequestId": "request-origin-1",
        "ownerRunId": RUN_ID,
        "sourceKind": source_kind,
        "permissionProfile": "read",
    }


@pytest.mark.parametrize("source_kind", ["explicit", "autonomous"])
def test_goal_created_supports_both_sources_before_a_plan(source_kind: str):
    state = GoalV2FoldState(SESSION_ID)

    event = _append(state, "goal_created", _create_payload(source_kind))

    assert event["protocolVersion"] == GOAL_V2_PROTOCOL_VERSION
    assert event["revision"] == 1
    assert state.goal is not None
    assert state.goal["sourceKind"] == source_kind
    assert state.goal["originMessageId"] == "message-origin-1"
    assert state.goal["clientRequestId"] == "request-origin-1"
    assert state.goal["ownerRunId"] == RUN_ID
    assert state.goal["permissionProfile"] == "read"
    assert state.goal["lifecycle"] == "draft"
    assert state.goal["steps"] == []
    assert state.goal["currentStepId"] is None


def test_plan_and_progress_are_named_events_with_three_public_statuses():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload("autonomous"))
    _append(state, "plan_set", {"steps": _steps(), "sourceRunId": RUN_ID})

    assert [item["status"] for item in state.goal["steps"]] == [
        "pending",
        "pending",
        "pending",
    ]

    _append(
        state,
        "step_started",
        {"stepId": "step-1", "sourceRunId": RUN_ID},
    )
    assert [item["status"] for item in state.goal["steps"]] == [
        "in_progress",
        "pending",
        "pending",
    ]
    _append(
        state,
        "gate_raised",
        {
            "gateType": "waiting_user",
            "summary": "Need a product choice",
            "sourceRunId": RUN_ID,
        },
    )
    assert state.goal["gate"]["type"] == "waiting_user"
    assert state.goal["steps"][0]["status"] == "in_progress"
    _append(state, "gate_cleared", {"sourceRunId": RUN_ID})
    _append(
        state,
        "step_completed",
        {"stepId": "step-1", "sourceRunId": RUN_ID, "evidence": _evidence(1)},
    )

    _append(
        state,
        "goal_paused",
        {"reason": "User paused", "sourceRunId": RUN_ID},
    )
    assert state.goal["lifecycle"] == "paused"
    _append(state, "goal_resumed", {"sourceRunId": RUN_ID})
    assert state.goal["lifecycle"] == "active"

    for index in (2,):
        _append(
            state,
            "step_started",
            {"stepId": f"step-{index}", "sourceRunId": RUN_ID},
        )
        _append(
            state,
            "step_completed",
            {
                "stepId": f"step-{index}",
                "sourceRunId": RUN_ID,
                "evidence": _evidence(index),
            },
        )
    _append(
        state,
        "step_started",
        {"stepId": "step-3", "sourceRunId": RUN_ID},
    )
    _append(
        state,
        "goal_completed",
        {
            "stepId": "step-3",
            "sourceRunId": RUN_ID,
            "evidence": _evidence(3),
        },
    )
    assert {item["status"] for item in state.goal["steps"]} == {"completed"}
    assert state.goal["lifecycle"] == "completed"
    assert state.goal["permissionProfile"] == "read"


def test_legacy_ready_for_acceptance_history_remains_foldable_and_completable():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload())
    _append(state, "plan_set", {"steps": _steps(), "sourceRunId": RUN_ID})
    for index in range(1, 4):
        _append(
            state,
            "step_started",
            {"stepId": f"step-{index}", "sourceRunId": RUN_ID},
        )
        _append(
            state,
            "step_completed",
            {
                "stepId": f"step-{index}",
                "sourceRunId": RUN_ID,
                "evidence": _evidence(index),
            },
        )
    _append(
        state,
        "goal_ready_for_acceptance",
        {"summary": "Legacy ready record", "sourceRunId": RUN_ID},
    )
    assert state.goal["lifecycle"] == "ready_for_acceptance"

    _append(
        state,
        "goal_completed",
        {"summary": "Compatibility completion", "sourceRunId": RUN_ID},
    )
    assert state.goal["lifecycle"] == "completed"


def test_direct_completion_rejects_gate_nonfinal_and_incomplete_evidence():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload())
    _append(state, "plan_set", {"steps": _steps(), "sourceRunId": RUN_ID})
    _append(
        state,
        "step_started",
        {"stepId": "step-1", "sourceRunId": RUN_ID},
    )
    with pytest.raises(GoalV2TransitionError, match="final planned step"):
        _append(
            state,
            "goal_completed",
            {
                "stepId": "step-1",
                "sourceRunId": RUN_ID,
                "evidence": _evidence(1),
            },
        )

    _append(
        state,
        "gate_raised",
        {
            "gateType": "waiting_user",
            "summary": "User acceptance is still pending",
            "sourceRunId": RUN_ID,
        },
    )
    with pytest.raises(GoalV2TransitionError, match="gated Goal"):
        _append(
            state,
            "goal_completed",
            {
                "stepId": "step-1",
                "sourceRunId": RUN_ID,
                "evidence": _evidence(1),
            },
        )


def test_plan_revision_cannot_rewrite_started_steps_or_origin_identity():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload())
    _append(state, "plan_set", {"steps": _steps(), "sourceRunId": RUN_ID})
    _append(
        state,
        "step_started",
        {"stepId": "step-1", "sourceRunId": RUN_ID},
    )
    origin = {
        key: state.goal[key]
        for key in (
            "originMessageId",
            "clientRequestId",
            "sourceKind",
            "permissionProfile",
        )
    }

    revised = _steps()
    revised[0]["description"] = "Silently replace an active step"
    with pytest.raises(GoalV2TransitionError, match="cannot change description"):
        _append(
            state,
            "plan_revised",
            {"steps": revised, "sourceRunId": RUN_ID},
        )

    with pytest.raises(GoalV2ProtocolError, match="unknown fields"):
        build_event(
            event_id="event-identity-rewrite",
            event_type="plan_revised",
            session_id=SESSION_ID,
            goal_id=GOAL_ID,
            expected_revision=state.revision,
            idempotency_key="key-identity-rewrite",
            actor="test",
            created_at="2026-08-15T12:00:00+08:00",
            payload={
                "objective": "Changed objective",
                "originMessageId": "message-forged",
                "sourceRunId": RUN_ID,
            },
        )
    assert {key: state.goal[key] for key in origin} == origin


def test_invalid_transitions_and_evidence_fail_closed():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload())

    with pytest.raises(GoalV2ProtocolError, match="3-8"):
        _append(
            state,
            "plan_set",
            {"steps": _steps()[:2], "sourceRunId": RUN_ID},
        )
    _append(state, "plan_set", {"steps": _steps(), "sourceRunId": RUN_ID})
    with pytest.raises(GoalV2TransitionError, match="plan order"):
        _append(
            state,
            "step_started",
            {"stepId": "step-2", "sourceRunId": RUN_ID},
        )
    _append(
        state,
        "step_started",
        {"stepId": "step-1", "sourceRunId": RUN_ID},
    )
    bad_evidence = _evidence(1)
    bad_evidence[0]["criterionId"] = "criterion-other"
    with pytest.raises(GoalV2ProtocolError, match="unknown criterion"):
        _append(
            state,
            "step_completed",
            {"stepId": "step-1", "sourceRunId": RUN_ID, "evidence": bad_evidence},
        )
    with pytest.raises(GoalV2TransitionError, match="every step"):
        _append(
            state,
            "goal_ready_for_acceptance",
            {"summary": None, "sourceRunId": RUN_ID},
        )


def test_revision_jump_and_duplicate_persisted_identity_are_rejected():
    state = GoalV2FoldState(SESSION_ID)
    first = _append(state, "goal_created", _create_payload())
    jumped = build_event(
        event_id="event-jump",
        event_type="plan_set",
        session_id=SESSION_ID,
        goal_id=GOAL_ID,
        expected_revision=2,
        idempotency_key="key-jump",
        actor="test",
        created_at="2026-08-15T12:00:02+08:00",
        payload={"steps": _steps(), "sourceRunId": RUN_ID},
    )
    with pytest.raises(GoalV2TransitionError, match="not contiguous"):
        apply_event(state, jumped)

    duplicate_identity = build_event(
        event_id=first["eventId"],
        event_type="plan_set",
        session_id=SESSION_ID,
        goal_id=GOAL_ID,
        expected_revision=1,
        idempotency_key="key-new",
        actor="test",
        created_at="2026-08-15T12:00:01+08:00",
        payload={"steps": _steps(), "sourceRunId": RUN_ID},
    )
    with pytest.raises(GoalV2TransitionError, match="duplicate eventId"):
        apply_event(state, duplicate_identity)


def test_clear_is_a_tombstone_and_historical_goal_ids_never_reuse():
    state = GoalV2FoldState(SESSION_ID)
    _append(state, "goal_created", _create_payload())
    _append(state, "goal_cleared", {"reason": "User cleared it"})

    assert state.goal is None
    assert state.tombstone["goalId"] == GOAL_ID
    assert state.tombstone["originMessageId"] == "message-origin-1"
    with pytest.raises(GoalV2TransitionError, match="cannot be reused"):
        _append(
            state,
            "goal_created",
            _create_payload(),
            goal_id=GOAL_ID,
        )

    next_payload = _create_payload("autonomous")
    next_payload.update(
        {
            "objective": "A new durable objective",
            "originMessageId": "message-origin-2",
            "clientRequestId": "request-origin-2",
            "ownerRunId": "run-v2-beta",
        }
    )
    _append(state, "goal_created", next_payload, goal_id="goal-v2-beta")
    assert state.goal["goalId"] == "goal-v2-beta"
    assert state.tombstone is None


def _context(source_kind: str = "autonomous", **overrides) -> GoalCreationContext:
    values = {
        "session_id": SESSION_ID,
        "origin_message_id": "message-runtime-1",
        "client_request_id": "request-runtime-1",
        "owner_run_id": "run-runtime-1",
        "permission_profile": "accept",
        "source_kind": source_kind,
    }
    values.update(overrides)
    return GoalCreationContext(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_top_level_foreground": False},
        {"is_child": True},
        {"is_detached": True},
        {"is_parallel": True},
        {"is_background": True},
        {"session_id": "session-v2-other"},
    ],
)
def test_autonomous_creation_rejects_non_foreground_or_cross_session_context(
    tmp_path, overrides,
):
    runtime = GoalV2Runtime(tmp_path)

    with pytest.raises(GoalV2ContextError):
        runtime.create_goal(
            SESSION_ID,
            "Autonomous durable objective",
            context=_context(**overrides),
            expected_revision=0,
            idempotency_key="create-autonomous",
        )
    assert runtime.read(SESSION_ID).state.revision == 0


@pytest.mark.parametrize("source_kind", ["explicit", "autonomous"])
def test_server_context_binds_creation_identity_without_permission_escalation(
    tmp_path, source_kind,
):
    runtime = GoalV2Runtime(tmp_path)
    context = _context(source_kind, permission_profile="read")

    result = runtime.create_goal(
        SESSION_ID,
        "Shared explicit/autonomous event contract",
        context=context,
        expected_revision=0,
        idempotency_key=f"create-{source_kind}",
    )

    goal = result["goal"]
    assert goal["sourceKind"] == source_kind
    assert goal["originMessageId"] == context.origin_message_id
    assert goal["clientRequestId"] == context.client_request_id
    assert goal["ownerRunId"] == context.owner_run_id
    assert goal["permissionProfile"] == "read"
    assert goal["steps"] == []


def test_same_objective_reuses_current_goal_and_different_objective_conflicts(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    context = _context()
    first = runtime.create_goal(
        SESSION_ID,
        "One durable objective",
        context=context,
        expected_revision=0,
        idempotency_key="create-first",
    )
    reused = runtime.create_goal(
        SESSION_ID,
        " One durable objective ",
        context=context,
        expected_revision=first["revision"],
        idempotency_key="create-second-same-objective",
    )

    assert reused["noOp"] is True
    assert reused["reused"] is True
    assert reused["revision"] == 1
    with pytest.raises(GoalV2ConflictError, match="different nonterminal"):
        runtime.create_goal(
            SESSION_ID,
            "A different objective",
            context=context,
            expected_revision=1,
            idempotency_key="create-different",
        )
    assert runtime.read(SESSION_ID).state.revision == 1


def test_rebuilt_services_preserve_idempotency_and_detect_different_payload(tmp_path):
    clock = lambda: "2026-08-15T12:00:00+08:00"
    first = GoalV2Runtime(tmp_path, service=GoalV2Service(tmp_path, clock=clock))
    context = _context("explicit")
    accepted = first.create_goal(
        SESSION_ID,
        "Restart-safe creation",
        context=context,
        expected_revision=0,
        idempotency_key="restart-safe-key",
    )

    rebuilt = GoalV2Runtime(tmp_path, service=GoalV2Service(tmp_path, clock=clock))
    same = rebuilt.create_goal(
        SESSION_ID,
        "Restart-safe creation",
        context=context,
        expected_revision=0,
        idempotency_key="restart-safe-key",
    )
    assert accepted["revision"] == same["revision"] == 1
    assert same["noOp"] is True

    with pytest.raises(GoalV2ConflictError, match="different payload"):
        rebuilt.service.append(
            SESSION_ID,
            accepted["goal"]["goalId"],
            "goal_created",
            {
                **_create_payload("explicit"),
                "objective": "Conflicting restart payload",
            },
            expected_revision=0,
            idempotency_key="restart-safe-key",
        )
