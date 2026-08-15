import copy
import unittest

from goal_protocol import (
    GOAL_PROTOCOL_VERSION,
    GoalFoldState,
    GoalProtocolError,
    GoalTransitionError,
    apply_event,
    normalize_snapshot,
    request_hash,
)


def make_snapshot(
    session_id="session01",
    goal_id="goal-01",
    revision=1,
    *,
    lifecycle="active",
    statuses=None,
):
    statuses = statuses or ["in_progress", "pending", "pending"]
    steps = []
    for index, status in enumerate(statuses, start=1):
        step_id = f"step-{index}"
        steps.append({
            "id": step_id,
            "description": f"Product step {index}",
            "status": status,
            "acceptanceCriteria": [{
                "id": f"criterion-{index}",
                "description": f"Evidence for step {index}",
                "kind": "machine" if index != 3 else "user",
            }],
            "evidence": [],
        })
    current = next((step["id"] for step in steps if step["status"] == "in_progress"), None)
    return {
        "goalId": goal_id,
        "sessionId": session_id,
        "revision": revision,
        "objective": "Implement a durable, testable Goal fact layer",
        "lifecycle": lifecycle,
        "permissionProfile": "accept",
        "steps": steps,
        "currentStepId": current,
        "runtimeSignals": [],
        "ownerRunId": "run-owner-01",
        "createdAt": "2026-08-15T10:00:00",
        "updatedAt": f"2026-08-15T10:00:{revision:02d}",
    }


def make_event(snapshot, *, expected_revision=0, operation="replace", key="request-01"):
    revision = expected_revision + 1
    mutation = {
        "operation": operation,
        "sessionId": snapshot["sessionId"],
        "goalId": snapshot["goalId"],
        "expectedRevision": expected_revision,
    }
    if operation == "replace":
        mutation["snapshot"] = snapshot
    return {
        "protocolVersion": GOAL_PROTOCOL_VERSION,
        "eventId": f"event-{revision}",
        "operation": operation,
        "sessionId": snapshot["sessionId"],
        "goalId": snapshot["goalId"],
        "revision": revision,
        "expectedRevision": expected_revision,
        "idempotencyKey": key,
        "requestHash": request_hash(mutation),
        "actor": "server",
        "createdAt": f"2026-08-15T10:01:{revision:02d}",
        "snapshot": snapshot if operation == "replace" else None,
    }


class TestGoalProtocol(unittest.TestCase):
    def test_versioned_event_shape_and_first_fold(self):
        snapshot = make_snapshot()
        event = make_event(snapshot)
        state = apply_event(GoalFoldState("session01"), event)

        self.assertEqual(event["protocolVersion"], 1)
        self.assertEqual(state.revision, 1)
        self.assertEqual(state.goal, normalize_snapshot(snapshot, session_id="session01", revision=1))
        self.assertEqual(state.projection()["goal"]["steps"][0]["status"], "in_progress")

    def test_public_steps_allow_only_three_states(self):
        for invalid in ("blocked", "failed", "waiting_user", "retry"):
            snapshot = make_snapshot()
            snapshot["steps"][0]["status"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(GoalProtocolError):
                normalize_snapshot(snapshot, session_id="session01", revision=1)

    def test_runtime_signals_remain_separate_from_step_status(self):
        snapshot = make_snapshot()
        snapshot["runtimeSignals"] = [{
            "type": "waiting_user",
            "summary": "Awaiting a subjective UI PASS",
            "sourceRunId": "run-owner-01",
            "recordedAt": "2026-08-15T10:02:00",
        }]
        normalized = normalize_snapshot(snapshot, session_id="session01", revision=1)
        self.assertEqual(normalized["runtimeSignals"][0]["type"], "waiting_user")
        self.assertEqual(normalized["steps"][0]["status"], "in_progress")

    def test_requires_three_to_eight_steps_and_at_most_one_in_progress(self):
        for count in (2, 9):
            snapshot = make_snapshot(statuses=["pending"] * count, lifecycle="draft")
            with self.subTest(count=count), self.assertRaises(GoalProtocolError):
                normalize_snapshot(snapshot, session_id="session01", revision=1)

        snapshot = make_snapshot(statuses=["in_progress", "in_progress", "pending"])
        with self.assertRaisesRegex(GoalProtocolError, "at most one"):
            normalize_snapshot(snapshot, session_id="session01", revision=1)

    def test_current_step_and_lifecycle_are_consistent(self):
        draft = make_snapshot(lifecycle="draft", statuses=["pending"] * 3)
        self.assertIsNone(normalize_snapshot(draft, session_id="session01", revision=1)["currentStepId"])

        invalid_active = make_snapshot(lifecycle="active", statuses=["pending"] * 3)
        with self.assertRaisesRegex(GoalProtocolError, "exactly one"):
            normalize_snapshot(invalid_active, session_id="session01", revision=1)

        completed = make_snapshot(lifecycle="completed", statuses=["completed"] * 3)
        self.assertEqual(
            normalize_snapshot(completed, session_id="session01", revision=1)["lifecycle"],
            "completed",
        )

    def test_snapshot_rejects_raw_tool_output_and_unknown_fields(self):
        snapshot = make_snapshot()
        snapshot["steps"][0]["evidence"] = [{
            "id": "evidence-1",
            "criterionId": "criterion-1",
            "kind": "machine",
            "summary": "pytest passed",
            "sourceRunId": "run-owner-01",
            "sourceToolCallId": "tool-call-01",
            "artifactDigest": "a" * 64,
            "recordedAt": "2026-08-15T10:03:00",
            "stdout": "unbounded raw output",
        }]
        with self.assertRaisesRegex(GoalProtocolError, "unknown fields"):
            normalize_snapshot(snapshot, session_id="session01", revision=1)

    def test_revision_must_be_contiguous(self):
        state = apply_event(GoalFoldState("session01"), make_event(make_snapshot()))
        snapshot = make_snapshot(revision=3)
        event = make_event(snapshot, expected_revision=2, key="request-gap")
        with self.assertRaisesRegex(GoalTransitionError, "contiguous"):
            apply_event(state, event)

    def test_session_may_not_replace_a_nonterminal_goal(self):
        state = apply_event(GoalFoldState("session01"), make_event(make_snapshot()))
        replacement = make_snapshot(goal_id="goal-02", revision=2)
        with self.assertRaisesRegex(GoalTransitionError, "at most one active"):
            apply_event(state, make_event(replacement, expected_revision=1, key="request-02"))

    def test_completed_steps_cannot_disappear_or_move_backwards(self):
        first = make_snapshot(statuses=["completed", "in_progress", "pending"])
        state = apply_event(GoalFoldState("session01"), make_event(first))

        backwards = make_snapshot(revision=2, statuses=["pending", "in_progress", "pending"])
        with self.assertRaisesRegex(GoalTransitionError, "backwards"):
            apply_event(state, make_event(backwards, expected_revision=1, key="request-02"))

        missing = make_snapshot(revision=2, statuses=["completed", "in_progress", "pending"])
        missing["steps"] = missing["steps"][1:]
        missing["steps"].append({
            "id": "step-4",
            "description": "Replacement pending step",
            "status": "pending",
            "acceptanceCriteria": [{
                "id": "criterion-4",
                "description": "Evidence for step 4",
                "kind": "machine",
            }],
            "evidence": [],
        })
        missing["currentStepId"] = "step-2"
        with self.assertRaisesRegex(GoalTransitionError, "cannot disappear"):
            apply_event(state, make_event(missing, expected_revision=1, key="request-03"))

    def test_permission_profile_is_immutable_within_a_goal(self):
        state = apply_event(GoalFoldState("session01"), make_event(make_snapshot()))
        changed = make_snapshot(revision=2)
        changed["permissionProfile"] = "bypass"
        with self.assertRaisesRegex(GoalTransitionError, "permissionProfile"):
            apply_event(state, make_event(changed, expected_revision=1, key="request-02"))

    def test_event_rejects_unknown_protocol_version(self):
        event = make_event(make_snapshot())
        event["protocolVersion"] = 2
        with self.assertRaisesRegex(GoalProtocolError, "unsupported goal protocol"):
            apply_event(GoalFoldState("session01"), event)


if __name__ == "__main__":
    unittest.main()
