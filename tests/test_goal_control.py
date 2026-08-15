import copy
import json
import tempfile
import unittest
from pathlib import Path

from goal_control import GoalConfirmationError, GoalControlError, GoalControlService
from goal_protocol import request_hash
from goal_store import GoalConflictError, GoalCorruptionError, GoalService


STAGE1_V1_EVENT_FIELDS = {
    "protocolVersion", "eventId", "operation", "sessionId", "goalId",
    "revision", "expectedRevision", "idempotencyKey", "requestHash",
    "actor", "createdAt", "snapshot",
}


class TestGoalControlService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "goals"
        self.clock_values = iter(
            f"2026-08-15T12:00:{second:02d}" for second in range(60)
        )
        self.store = GoalService(self.root, clock=lambda: next(self.clock_values))
        self.confirmation_secret = b"goal-control-test-secret-32-bytes"
        self.control = GoalControlService(
            self.store,
            confirmation_secret=self.confirmation_secret,
            clock=lambda: next(self.clock_values),
        )
        self.session_id = "session01"

    def rebuild_services(self):
        self.store = GoalService(self.root, clock=lambda: next(self.clock_values))
        self.control = GoalControlService(
            self.store,
            confirmation_secret=self.confirmation_secret,
            clock=lambda: next(self.clock_values),
        )

    def request(self, **value):
        return self.control.handle(self.session_id, value)

    def create_draft(self, *, key="draft-01", objective="交付一个可验证功能", language="zh"):
        return self.request(
            operation="create_draft",
            expectedRevision=0,
            idempotencyKey=key,
            objective=objective,
            permissionProfile="accept",
            language=language,
        )

    def activate(self):
        draft = self.create_draft()
        return self.request(
            operation="confirm_draft",
            expectedRevision=draft["revision"],
            idempotencyKey="confirm-01",
            goalId=draft["goal"]["goalId"],
        )

    def proposal(self, projection, proposal):
        return self.request(
            operation="propose_change",
            expectedRevision=projection["revision"],
            goalId=projection["goal"]["goalId"],
            proposal=proposal,
        )

    def confirm_proposal(self, projection, proposed, *, key="change-01"):
        return self.request(
            operation="confirm_change",
            expectedRevision=projection["revision"],
            idempotencyKey=key,
            goalId=projection["goal"]["goalId"],
            confirmationToken=proposed["confirmationToken"],
        )

    def test_create_draft_is_bounded_awaiting_confirmation_and_disarmed(self):
        result = self.create_draft()
        goal = result["goal"]
        self.assertEqual(goal["lifecycle"], "awaiting_confirmation")
        self.assertEqual(len(goal["steps"]), 3)
        self.assertEqual({step["status"] for step in goal["steps"]}, {"pending"})
        self.assertIsNone(goal["currentStepId"])
        self.assertEqual(goal["permissionProfile"], "accept")
        self.assertFalse(result["armed"])
        self.assertIsNone(goal["ownerRunId"])

    def test_confirm_draft_activates_first_step_without_runtime_state(self):
        result = self.activate()
        self.assertEqual(result["goal"]["lifecycle"], "active")
        self.assertEqual(result["goal"]["steps"][0]["status"], "in_progress")
        self.assertEqual(result["goal"]["currentStepId"], "step-1")
        self.assertFalse(result["armed"])
        self.assertIsNone(result["goal"]["ownerRunId"])

    def test_control_idempotency_is_stable_across_server_timestamps(self):
        first = self.create_draft(key="stable-draft")
        self.rebuild_services()
        retry = self.create_draft(key="stable-draft")
        self.assertFalse(first["noOp"])
        self.assertTrue(retry["noOp"])
        self.assertEqual(retry["revision"], 1)
        with self.assertRaisesRegex(GoalConflictError, "different payload"):
            self.create_draft(key="stable-draft", objective="不同目标")

        confirmed = self.request(
            operation="confirm_draft",
            expectedRevision=1,
            idempotencyKey="stable-confirm",
            goalId=first["goal"]["goalId"],
        )
        self.rebuild_services()
        confirmed_retry = self.request(
            operation="confirm_draft",
            expectedRevision=1,
            idempotencyKey="stable-confirm",
            goalId=first["goal"]["goalId"],
        )
        self.assertEqual(confirmed["revision"], 2)
        self.assertTrue(confirmed_retry["noOp"])
        repeated_confirm = self.request(
            operation="confirm_draft",
            expectedRevision=confirmed["revision"],
            idempotencyKey="stable-confirm-second-request",
            goalId=first["goal"]["goalId"],
        )
        self.assertEqual(repeated_confirm["revision"], 2)
        self.assertTrue(repeated_confirm["noOp"])

    def test_all_control_events_are_stage1_v1_readable_and_foldable(self):
        active = self.activate()
        paused = self.request(
            operation="pause", expectedRevision=active["revision"],
            idempotencyKey="compat-pause", goalId=active["goal"]["goalId"],
        )
        resumed = self.request(
            operation="resume", expectedRevision=paused["revision"],
            idempotencyKey="compat-resume", goalId=paused["goal"]["goalId"],
        )
        proposed = self.proposal(
            resumed, {"type": "supplement", "text": "兼容回退验收"}
        )
        changed = self.confirm_proposal(resumed, proposed, key="compat-change")
        cancel = self.proposal(changed, {"type": "cancel"})
        cancelled = self.confirm_proposal(changed, cancel, key="compat-cancel")
        clear = self.proposal(cancelled, {"type": "clear"})
        cleared = self.confirm_proposal(cancelled, clear, key="compat-clear")

        events = [
            json.loads(line)
            for line in self.store.events_path(self.session_id).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(events), 7)
        previous_revision = 0
        current_goal = None
        for event in events:
            self.assertEqual(set(event), STAGE1_V1_EVENT_FIELDS)
            self.assertNotIn("idempotencyHash", event)
            self.assertEqual(event["protocolVersion"], 1)
            self.assertEqual(event["expectedRevision"], previous_revision)
            self.assertEqual(event["revision"], previous_revision + 1)
            mutation = {
                "operation": event["operation"],
                "sessionId": event["sessionId"],
                "goalId": event["goalId"],
                "expectedRevision": event["expectedRevision"],
            }
            if event["operation"] == "replace":
                mutation["snapshot"] = event["snapshot"]
                current_goal = event["snapshot"]
            else:
                self.assertIsNone(event["snapshot"])
                self.assertEqual(current_goal["goalId"], event["goalId"])
                current_goal = None
            self.assertEqual(event["requestHash"], request_hash(mutation))
            previous_revision = event["revision"]
        self.assertEqual(previous_revision, cleared["revision"])
        self.assertIsNone(current_goal)

        restored = GoalService(self.root).read(self.session_id)
        self.assertEqual(restored.health, "healthy")
        self.assertTrue(restored.writable)
        self.assertEqual(restored.state.revision, cleared["revision"])
        self.assertIsNone(restored.state.goal)

    def test_unknown_fields_permission_escalation_and_active_replacement_are_rejected(self):
        with self.assertRaisesRegex(GoalControlError, "unknown fields"):
            self.request(
                operation="create_draft",
                expectedRevision=0,
                idempotencyKey="unknown-01",
                objective="目标",
                permissionProfile="read",
                language="zh",
                snapshot={"lifecycle": "active"},
            )
        with self.assertRaisesRegex(GoalControlError, "unsupported"):
            self.request(
                operation="create_draft",
                expectedRevision=0,
                idempotencyKey="escalate-01",
                objective="目标",
                permissionProfile="admin",
                language="zh",
            )
        active = self.activate()
        with self.assertRaisesRegex(GoalConflictError, "at most one"):
            self.request(
                operation="create_draft",
                expectedRevision=active["revision"],
                idempotencyKey="replacement-01",
                objective="静默覆盖",
                permissionProfile="bypass",
                language="zh",
            )

    def test_pause_resume_are_exact_lifecycle_transitions_and_preserve_permission(self):
        active = self.activate()
        paused = self.request(
            operation="pause",
            expectedRevision=active["revision"],
            idempotencyKey="pause-01",
            goalId=active["goal"]["goalId"],
        )
        self.assertEqual(paused["goal"]["lifecycle"], "paused")
        self.assertEqual(paused["goal"]["permissionProfile"], "accept")
        self.rebuild_services()
        repeated_pause = self.request(
            operation="pause",
            expectedRevision=paused["revision"],
            idempotencyKey="pause-02",
            goalId=paused["goal"]["goalId"],
        )
        self.assertEqual(repeated_pause["revision"], paused["revision"])
        self.assertTrue(repeated_pause["noOp"])
        resumed = self.request(
            operation="resume",
            expectedRevision=paused["revision"],
            idempotencyKey="resume-01",
            goalId=paused["goal"]["goalId"],
        )
        self.assertEqual(resumed["goal"]["lifecycle"], "active")
        self.rebuild_services()
        repeated_resume = self.request(
            operation="resume",
            expectedRevision=resumed["revision"],
            idempotencyKey="resume-02",
            goalId=resumed["goal"]["goalId"],
        )
        self.assertEqual(repeated_resume["revision"], resumed["revision"])
        self.assertTrue(repeated_resume["noOp"])

    def test_proposal_is_read_only_and_requires_a_valid_direct_confirmation(self):
        active = self.activate()
        before = self.store.events_path(self.session_id).read_bytes()
        proposed = self.proposal(active, {"type": "supplement", "text": "补充移动端验收"})
        alternative = self.proposal(active, {"type": "supplement", "text": "另一项补充"})
        self.assertTrue(proposed["requiresConfirmation"])
        self.assertEqual(self.store.events_path(self.session_id).read_bytes(), before)

        tampered = proposed["confirmationToken"][:-1] + ("0" if proposed["confirmationToken"][-1] != "0" else "1")
        with self.assertRaises(GoalConfirmationError):
            self.request(
                operation="confirm_change",
                expectedRevision=active["revision"],
                idempotencyKey="tampered-01",
                goalId=active["goal"]["goalId"],
                confirmationToken=tampered,
            )
        self.assertEqual(self.store.events_path(self.session_id).read_bytes(), before)

        changed = self.confirm_proposal(active, proposed)
        self.assertIn("补充移动端验收", changed["goal"]["objective"])
        self.rebuild_services()
        retry = self.confirm_proposal(active, proposed)
        self.assertTrue(retry["noOp"])
        with self.assertRaisesRegex(GoalConflictError, "different payload"):
            self.confirm_proposal(active, alternative)

    def test_cancel_and_clear_each_require_a_separate_confirmation(self):
        active = self.activate()
        cancel = self.proposal(active, {"type": "cancel"})
        self.assertEqual(self.store.read(self.session_id).state.goal["lifecycle"], "active")
        cancelled = self.confirm_proposal(active, cancel, key="cancel-01")
        self.assertEqual(cancelled["goal"]["lifecycle"], "cancelled")

        clear = self.proposal(cancelled, {"type": "clear"})
        cleared = self.confirm_proposal(cancelled, clear, key="clear-01")
        self.assertIsNone(cleared["goal"])
        self.assertEqual(cleared["tombstone"]["goalId"], cancelled["goal"]["goalId"])
        self.rebuild_services()
        retry = self.confirm_proposal(cancelled, clear, key="clear-01")
        self.assertTrue(retry["noOp"])
        with self.assertRaisesRegex(GoalConflictError, "different payload"):
            self.request(
                operation="create_draft",
                expectedRevision=cleared["revision"],
                idempotencyKey="clear-01",
                objective="不同领域请求",
                permissionProfile="read",
                language="zh",
            )

        fresh = self.request(
            operation="create_draft",
            expectedRevision=cleared["revision"],
            idempotencyKey="fresh-goal-01",
            objective="新目标",
            permissionProfile="read",
            language="zh",
        )
        self.assertNotEqual(fresh["goal"]["goalId"], cancelled["goal"]["goalId"])

    def test_structured_revision_preserves_started_steps_and_rejects_completed_rewrite(self):
        active = self.activate()
        steps = [
            {"id": "step-1", "description": active["goal"]["steps"][0]["description"]},
            {"id": "step-2", "description": "执行调整后的实现"},
            {"id": "step-3", "description": "完成调整后的验收"},
            {"id": "step-4", "description": "记录兼容边界"},
        ]
        proposal = self.proposal(active, {"type": "revise", "steps": steps})
        self.assertEqual(proposal["diff"]["steps"]["before"][0]["id"], "step-1")
        self.assertEqual(proposal["diff"]["steps"]["after"][3]["id"], "step-4")
        self.assertTrue(
            proposal["diff"]["steps"]["before"][0]["acceptanceCriteria"]
        )
        revised = self.confirm_proposal(active, proposal, key="revise-01")
        self.assertEqual(len(revised["goal"]["steps"]), 4)
        self.assertEqual(revised["goal"]["currentStepId"], "step-1")

        stored = self.store.read(self.session_id).state.goal
        stored["steps"][0]["status"] = "completed"
        stored["steps"][1]["status"] = "in_progress"
        stored["currentStepId"] = "step-2"
        stored["revision"] = revised["revision"] + 1
        stored["updatedAt"] = "2026-08-15T12:01:00"
        completed = self.store.replace(
            self.session_id,
            stored,
            expected_revision=revised["revision"],
            idempotency_key="advance-test-only",
        )
        bad_steps = [
            {"id": item["id"], "description": item["description"]}
            for item in completed["goal"]["steps"]
        ]
        bad_steps[0] = {"id": "step-1", "description": "改写已完成步骤"}
        proposed = self.proposal(completed, {"type": "revise", "steps": bad_steps})
        with self.assertRaisesRegex(GoalConflictError, "completed step"):
            self.confirm_proposal(completed, proposed, key="rewrite-completed")

    def test_stale_goal_id_and_malformed_proposal_never_write(self):
        active = self.activate()
        path = self.store.events_path(self.session_id)
        before = path.read_bytes()
        with self.assertRaises(GoalConflictError):
            self.request(
                operation="pause",
                expectedRevision=0,
                idempotencyKey="stale-pause",
                goalId=active["goal"]["goalId"],
            )
        with self.assertRaises(GoalConflictError):
            self.request(
                operation="propose_change",
                expectedRevision=active["revision"],
                goalId="goal-wrong",
                proposal={"type": "cancel"},
            )
        with self.assertRaises(GoalControlError):
            self.proposal(active, {"type": "revise", "steps": ["too", "few"]})
        self.assertEqual(path.read_bytes(), before)

    def test_degraded_sidecar_rejects_control_but_preserves_last_projection(self):
        active = self.activate()
        with open(self.store.events_path(self.session_id), "ab") as handle:
            handle.write(b'{"partial"')
        with self.assertRaises(GoalCorruptionError):
            self.request(
                operation="pause",
                expectedRevision=active["revision"],
                idempotencyKey="pause-degraded",
                goalId=active["goal"]["goalId"],
            )
        read_result = self.store.read(self.session_id)
        self.assertEqual(read_result.health, "degraded")
        self.assertEqual(read_result.state.goal["lifecycle"], "active")
        self.assertFalse(read_result.projection()["armed"])

    def test_english_draft_and_invalid_request_shapes(self):
        draft = self.create_draft(objective="Ship a bounded feature", language="en")
        self.assertIn("Confirm the Goal scope", draft["goal"]["steps"][0]["description"])
        with self.assertRaises(GoalControlError):
            self.control.handle(self.session_id, {"operation": "unknown"})
        with self.assertRaises(GoalControlError):
            self.control.handle(self.session_id, [])


if __name__ == "__main__":
    unittest.main()
