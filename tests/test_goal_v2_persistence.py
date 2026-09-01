from __future__ import annotations

import json
import multiprocessing
import os
import pytest

from code_runtime.goal_runtime import GoalCreationContext, GoalV2Runtime
from code_runtime.goal_v2_protocol import build_event, canonical_json
from code_runtime.goal_v2_store import (
    GOAL_V2_DIRECTORY_NAME,
    GoalV2ConflictError,
    GoalV2CorruptionError,
    GoalV2PersistenceError,
    GoalV2Service,
)


SESSION_A = "session-v2-store-a"
SESSION_B = "session-v2-store-b"


def _context(session_id: str, suffix: str = "a") -> GoalCreationContext:
    return GoalCreationContext(
        session_id=session_id,
        origin_message_id=f"message-{suffix}",
        client_request_id=f"request-{suffix}",
        owner_run_id=f"run-{suffix}",
        permission_profile="read",
        source_kind="autonomous",
    )


def _create(
    runtime: GoalV2Runtime,
    session_id: str,
    *,
    objective: str = "Persist Goal v2 safely",
    key: str = "create-v2",
    suffix: str = "a",
):
    return runtime.create_goal(
        session_id,
        objective,
        context=_context(session_id, suffix),
        expected_revision=0,
        idempotency_key=key,
    )


def _race_create(data_root: str, ready, start, results, suffix: str) -> None:
    try:
        runtime = GoalV2Runtime(data_root)
        ready.put(suffix)
        if not start.wait(10):
            results.put((suffix, "timeout"))
            return
        _create(
            runtime,
            SESSION_A,
            objective=f"Concurrent objective {suffix}",
            key=f"concurrent-{suffix}",
            suffix=suffix,
        )
        results.put((suffix, "accepted"))
    except GoalV2ConflictError:
        results.put((suffix, "conflict"))
    except Exception as exc:  # pragma: no cover - diagnostic transport
        results.put((suffix, f"error:{type(exc).__name__}:{exc}"))


def test_v2_uses_a_dedicated_directory_and_never_reads_legacy_sidecars(tmp_path):
    legacy_goal = tmp_path / "goals" / f"{SESSION_A}.jsonl"
    legacy_workflow = tmp_path / "goal-workflows" / f"{SESSION_A}.jsonl"
    legacy_goal.parent.mkdir(parents=True)
    legacy_workflow.parent.mkdir(parents=True)
    legacy_goal.write_text("legacy Goal v1 bytes\n", encoding="utf-8")
    legacy_workflow.write_text("legacy workflow bytes\n", encoding="utf-8")
    before = (legacy_goal.read_bytes(), legacy_workflow.read_bytes())

    runtime = GoalV2Runtime(tmp_path)
    assert runtime.read(SESSION_A).state.revision == 0
    created = _create(runtime, SESSION_A)

    assert created["revision"] == 1
    assert runtime.service.events_path(SESSION_A).parent.name == GOAL_V2_DIRECTORY_NAME
    assert runtime.service.events_path(SESSION_A).exists()
    assert (legacy_goal.read_bytes(), legacy_workflow.read_bytes()) == before


def test_session_isolation_and_read_only_query_do_not_write(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    assert runtime.read(SESSION_A).state.revision == 0
    assert not (tmp_path / GOAL_V2_DIRECTORY_NAME).exists()

    _create(runtime, SESSION_A)

    assert runtime.read(SESSION_A).state.revision == 1
    assert runtime.read(SESSION_B).state.revision == 0
    assert not runtime.service.events_path(SESSION_B).exists()


def test_partial_tail_recovers_last_complete_event_and_refuses_mutation(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A)
    path = runtime.service.events_path(SESSION_A)
    with path.open("ab") as handle:
        handle.write(b'{"protocolVersion":2')

    read = runtime.read(SESSION_A)
    assert read.health == "degraded"
    assert read.writable is False
    assert read.state.revision == created["revision"] == 1
    with pytest.raises(GoalV2CorruptionError):
        runtime.clear_goal(
            SESSION_A,
            created["goal"]["goalId"],
            reason="must fail closed",
            expected_revision=1,
            idempotency_key="clear-degraded",
        )


@pytest.mark.parametrize(
    "replacement",
    [
        b"not-json\n",
        b'{"protocolVersion":1}\n',
    ],
)
def test_middle_corruption_or_unknown_version_refuses_read_write_continuation(
    tmp_path, replacement,
):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A)
    path = runtime.service.events_path(SESSION_A)
    original = path.read_bytes()
    path.write_bytes(replacement + original)

    read = runtime.read(SESSION_A)
    assert read.health == "corrupted"
    assert read.writable is False
    assert read.state.revision == 0
    with pytest.raises(GoalV2CorruptionError):
        runtime.clear_goal(
            SESSION_A,
            created["goal"]["goalId"],
            reason="must fail closed",
            expected_revision=0,
            idempotency_key="clear-corrupted",
        )


def test_revision_jump_in_persisted_history_is_corruption(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A)
    path = runtime.service.events_path(SESSION_A)
    jumped = build_event(
        event_id="event-revision-jump",
        event_type="goal_cleared",
        session_id=SESSION_A,
        goal_id=created["goal"]["goalId"],
        expected_revision=3,
        idempotency_key="clear-revision-jump",
        actor="test",
        created_at="2026-08-15T12:00:03+08:00",
        payload={"reason": "jump"},
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(jumped) + "\n")

    read = runtime.read(SESSION_A)
    assert read.health == "corrupted"
    assert read.writable is False
    assert read.state.revision == 1


def test_event_replay_and_tombstone_are_deterministic(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A)
    goal_id = created["goal"]["goalId"]
    cleared = runtime.clear_goal(
        SESSION_A,
        goal_id,
        reason="User cleared the Goal",
        expected_revision=1,
        idempotency_key="clear-v2",
    )

    rebuilt = GoalV2Runtime(tmp_path)
    replayed = rebuilt.read(SESSION_A).projection()
    assert replayed["revision"] == cleared["revision"] == 2
    assert replayed["goal"] is None
    assert replayed["tombstone"]["goalId"] == goal_id
    assert replayed["tombstone"]["originMessageId"] == "message-a"


def test_cross_process_lock_and_cas_allow_only_one_competing_writer(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    results = context.Queue()
    start = context.Event()
    processes = [
        context.Process(
            target=_race_create,
            args=(str(tmp_path), ready, start, results, suffix),
        )
        for suffix in ("a", "b")
    ]
    for process in processes:
        process.start()
    assert {ready.get(timeout=15), ready.get(timeout=15)} == {"a", "b"}
    start.set()
    outcomes = {results.get(timeout=20), results.get(timeout=20)}
    for process in processes:
        process.join(20)
        assert process.exitcode == 0

    assert sorted(outcome for _, outcome in outcomes) == ["accepted", "conflict"]
    read = GoalV2Runtime(tmp_path).read(SESSION_A)
    assert read.health == "healthy"
    assert read.state.revision == 1
    assert len(runtime_lines := read.state.event_ids) == 1
    assert runtime_lines


def test_fsync_failure_is_reported_and_retry_recovers_by_persisted_idempotency(
    tmp_path, monkeypatch,
):
    service = GoalV2Service(
        tmp_path, clock=lambda: "2026-08-15T12:00:00+08:00"
    )
    runtime = GoalV2Runtime(tmp_path, service=service)
    real_fsync = os.fsync

    def fail_fsync(_fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(GoalV2PersistenceError, match="simulated fsync failure"):
        _create(runtime, SESSION_A)
    monkeypatch.setattr(os, "fsync", real_fsync)

    # The append may be visible despite the durability error.  A retry must
    # therefore fold the event and return the persisted idempotent result,
    # never append a second revision.
    recovered = _create(GoalV2Runtime(tmp_path), SESSION_A)
    assert recovered["revision"] == 1
    assert recovered["noOp"] is True
    assert len(
        GoalV2Service(tmp_path).events_path(SESSION_A).read_text(
            encoding="utf-8"
        ).splitlines()
    ) == 1


def test_final_step_completion_recovers_as_one_persisted_terminal_event(
    tmp_path, monkeypatch,
):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A, objective="Complete directly")
    goal_id = created["goal"]["goalId"]
    steps = [
        {
            "id": f"step-{index}",
            "description": f"Stage {index}",
            "acceptanceCriteria": [{
                "id": f"criterion-{index}",
                "description": f"Stage {index} passes",
                "kind": "machine",
            }],
        }
        for index in range(1, 4)
    ]
    planned = runtime.set_plan(
        SESSION_A, goal_id, steps,
        source_run_id="run-final",
        expected_revision=1,
        idempotency_key="plan-final",
    )

    def evidence(index: int) -> list[dict]:
        return [{
            "id": f"evidence-{index}",
            "criterionId": f"criterion-{index}",
            "kind": "machine",
            "summary": f"Stage {index} passed",
            "sourceRunId": "run-final",
            "sourceToolCallId": f"tool-{index}",
            "recordedAt": "2026-08-16T12:00:00+08:00",
        }]

    revision = planned["revision"]
    for index in (1, 2):
        started = runtime.start_step(
            SESSION_A, goal_id, f"step-{index}",
            source_run_id="run-final",
            expected_revision=revision,
            idempotency_key=f"start-{index}",
        )
        completed = runtime.complete_step(
            SESSION_A, goal_id, f"step-{index}", evidence(index),
            source_run_id="run-final",
            expected_revision=started["revision"],
            idempotency_key=f"complete-{index}",
        )
        revision = completed["revision"]
        assert completed["goal"]["lifecycle"] == "active"
    started = runtime.start_step(
        SESSION_A, goal_id, "step-3",
        source_run_id="run-final",
        expected_revision=revision,
        idempotency_key="start-3",
    )

    real_fsync = os.fsync
    monkeypatch.setattr(
        os, "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("final fsync failed")),
    )
    with pytest.raises(GoalV2PersistenceError, match="final fsync failed"):
        runtime.complete_step(
            SESSION_A, goal_id, "step-3", evidence(3),
            source_run_id="run-final",
            expected_revision=started["revision"],
            idempotency_key="complete-3",
        )
    monkeypatch.setattr(os, "fsync", real_fsync)

    recovered = GoalV2Runtime(tmp_path).complete_step(
        SESSION_A, goal_id, "step-3", evidence(3),
        source_run_id="run-final",
        expected_revision=started["revision"],
        idempotency_key="complete-3",
    )
    assert recovered["noOp"] is True
    assert recovered["revision"] == 8
    assert recovered["goal"]["lifecycle"] == "completed"
    assert recovered["goal"]["steps"][-1]["status"] == "completed"
    events = [
        json.loads(line)
        for line in runtime.service.events_path(SESSION_A).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [event["type"] for event in events][-1] == "goal_completed"
    assert "goal_ready_for_acceptance" not in {
        event["type"] for event in events
    }


def test_same_key_with_different_mutation_conflicts_without_appending(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    created = _create(runtime, SESSION_A, objective="Original objective")
    path = runtime.service.events_path(SESSION_A)
    before = path.read_bytes()

    with pytest.raises(GoalV2ConflictError, match="different payload"):
        runtime.service.append(
            SESSION_A,
            created["goal"]["goalId"],
            "goal_created",
            {
                "objective": "Different objective",
                "originMessageId": "message-a",
                "clientRequestId": "request-a",
                "ownerRunId": "run-a",
                "sourceKind": "autonomous",
                "permissionProfile": "read",
            },
            expected_revision=0,
            idempotency_key="create-v2",
        )
    assert path.read_bytes() == before


def test_persisted_lines_are_strict_v2_events(tmp_path):
    runtime = GoalV2Runtime(tmp_path)
    _create(runtime, SESSION_A)
    event = json.loads(
        runtime.service.events_path(SESSION_A).read_text(encoding="utf-8")
    )

    assert event["protocolVersion"] == 2
    assert event["type"] == "goal_created"
    assert set(event["payload"]) == {
        "objective",
        "originMessageId",
        "clientRequestId",
        "ownerRunId",
        "sourceKind",
        "permissionProfile",
    }
    assert canonical_json(event).startswith('{"actor"')
