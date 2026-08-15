import copy
import json
import multiprocessing
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from goal_protocol import GoalProtocolError, request_hash
from goal_store import (
    GoalConflictError,
    GoalCorruptionError,
    GoalPersistenceError,
    GoalService,
)
from tests.test_goal_protocol import make_snapshot


STAGE1_V1_EVENT_FIELDS = {
    "protocolVersion", "eventId", "operation", "sessionId", "goalId",
    "revision", "expectedRevision", "idempotencyKey", "requestHash",
    "actor", "createdAt", "snapshot",
}


def _process_goal_write(root, session_id, goal_id, result_queue):
    service = GoalService(Path(root))
    try:
        result = service.replace(
            session_id,
            make_snapshot(session_id=session_id, goal_id=goal_id),
            expected_revision=0,
            idempotency_key=f"create-{goal_id}",
        )
        result_queue.put(("ok", result["goal"]["goalId"]))
    except Exception as exc:  # pragma: no cover - asserted in parent process
        result_queue.put((type(exc).__name__, str(exc)))


class TestGoalPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "goals"
        self.service = GoalService(self.root, clock=lambda: "2026-08-15T11:00:00")
        self.session_id = "session01"

    def create_goal(self, *, goal_id="goal-01", key="create-01"):
        return self.service.replace(
            self.session_id,
            make_snapshot(session_id=self.session_id, goal_id=goal_id),
            expected_revision=0,
            idempotency_key=key,
        )

    def test_read_only_projection_does_not_create_storage(self):
        projection = self.service.read(self.session_id).projection()
        self.assertFalse(self.root.exists())
        self.assertFalse(projection["exists"])
        self.assertEqual(projection["revision"], 0)
        self.assertIsNone(projection["goal"])
        self.assertFalse(projection["armed"])

    def test_append_only_event_shape_and_full_snapshot(self):
        result = self.create_goal()
        path = self.service.events_path(self.session_id)
        lines = path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[0])

        self.assertEqual(len(lines), 1)
        self.assertEqual(event["protocolVersion"], 1)
        self.assertEqual(event["operation"], "replace")
        self.assertEqual(event["revision"], 1)
        self.assertEqual(event["expectedRevision"], 0)
        self.assertEqual(event["snapshot"], result["goal"])
        self.assertFalse(result["armed"])

    def test_control_idempotency_uses_only_stage1_v1_event_fields(self):
        snapshot = make_snapshot(session_id=self.session_id)
        domain_request = {
            "controlVersion": 1,
            "operation": "create_draft",
            "sessionId": self.session_id,
            "expectedRevision": 0,
            "body": {"objective": "bounded"},
        }
        self.service.replace(
            self.session_id,
            snapshot,
            expected_revision=0,
            idempotency_key="control-create-01",
            idempotency_payload=domain_request,
            actor="user-control",
        )
        path = self.service.events_path(self.session_id)
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(event), STAGE1_V1_EVENT_FIELDS)
        self.assertNotIn("idempotencyHash", event)
        self.assertLessEqual(len(event["actor"]), 64)
        self.assertTrue(event["actor"].startswith("user-control~"))
        mutation = {
            "operation": "replace",
            "sessionId": self.session_id,
            "goalId": snapshot["goalId"],
            "expectedRevision": 0,
            "snapshot": event["snapshot"],
        }
        self.assertEqual(event["requestHash"], request_hash(mutation))

        restored = GoalService(self.root).read(self.session_id)
        self.assertEqual(restored.health, "healthy")
        self.assertTrue(restored.writable)
        self.assertEqual(
            restored.state.idempotency[event["idempotencyKey"]],
            request_hash(domain_request),
        )

    def test_cas_and_idempotency_same_payload_noop_different_payload_rejected(self):
        snapshot = make_snapshot(session_id=self.session_id)
        first = self.service.replace(
            self.session_id,
            snapshot,
            expected_revision=0,
            idempotency_key="same-key",
        )
        retry = self.service.replace(
            self.session_id,
            snapshot,
            expected_revision=0,
            idempotency_key="same-key",
        )
        self.assertFalse(first["noOp"])
        self.assertTrue(retry["noOp"])
        self.assertEqual(len(self.service.events_path(self.session_id).read_text().splitlines()), 1)

        changed = copy.deepcopy(snapshot)
        changed["objective"] = "A different request under the same key"
        with self.assertRaisesRegex(GoalConflictError, "different payload"):
            self.service.replace(
                self.session_id,
                changed,
                expected_revision=0,
                idempotency_key="same-key",
            )
        with self.assertRaisesRegex(GoalConflictError, "stale"):
            self.service.replace(
                self.session_id,
                make_snapshot(session_id=self.session_id, goal_id="goal-02"),
                expected_revision=0,
                idempotency_key="stale-key",
            )

    def test_threaded_cas_allows_one_writer(self):
        barrier = threading.Barrier(8)
        outcomes = []
        outcome_lock = threading.Lock()

        def writer(index):
            barrier.wait()
            try:
                self.service.replace(
                    self.session_id,
                    make_snapshot(session_id=self.session_id, goal_id=f"goal-{index:02d}"),
                    expected_revision=0,
                    idempotency_key=f"thread-{index:02d}",
                )
                value = "ok"
            except GoalConflictError:
                value = "conflict"
            with outcome_lock:
                outcomes.append(value)

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("conflict"), 7)
        self.assertEqual(self.service.read(self.session_id).state.revision, 1)

    def test_cross_process_lock_and_cas_allow_one_writer(self):
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        processes = [
            context.Process(
                target=_process_goal_write,
                args=(str(self.root), self.session_id, f"goal-process-{index}", queue),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        outcomes = [queue.get(timeout=5)[0] for _ in processes]
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("GoalConflictError"), 1)
        self.assertEqual(self.service.read(self.session_id).state.revision, 1)
        queue.close()
        queue.join_thread()

    def test_fsync_failure_is_reported_and_idempotent_retry_recovers(self):
        snapshot = make_snapshot(session_id=self.session_id)
        with mock.patch("goal_store.os.fsync", side_effect=OSError("durability unavailable")):
            with self.assertRaisesRegex(GoalPersistenceError, "durably append"):
                self.service.replace(
                    self.session_id,
                    snapshot,
                    expected_revision=0,
                    idempotency_key="fsync-retry",
                )
        recovered = self.service.replace(
            self.session_id,
            snapshot,
            expected_revision=0,
            idempotency_key="fsync-retry",
        )
        self.assertTrue(recovered["noOp"])
        self.assertEqual(recovered["revision"], 1)

    def test_partial_tail_recovers_last_trusted_snapshot_and_disarms(self):
        self.create_goal()
        with open(self.service.events_path(self.session_id), "ab") as handle:
            handle.write(b'{"protocolVersion":1,"eventId"')
        result = self.service.read(self.session_id)
        self.assertEqual(result.health, "degraded")
        self.assertFalse(result.writable)
        self.assertEqual(result.state.revision, 1)
        self.assertEqual(result.state.goal["goalId"], "goal-01")
        self.assertFalse(result.projection()["armed"])
        with self.assertRaises(GoalCorruptionError):
            self.service.replace(
                self.session_id,
                make_snapshot(session_id=self.session_id, revision=2),
                expected_revision=1,
                idempotency_key="after-partial",
            )

    def test_middle_corruption_and_unknown_version_refuse_writes(self):
        self.create_goal()
        path = self.service.events_path(self.session_id)
        first_line = path.read_text(encoding="utf-8")
        path.write_text(first_line + "{not-json}\n" + first_line, encoding="utf-8")
        result = self.service.read(self.session_id)
        self.assertEqual(result.health, "corrupted")
        self.assertEqual(result.error["line"], 2)
        self.assertEqual(result.state.revision, 1)
        with self.assertRaises(GoalCorruptionError):
            self.service.clear(
                self.session_id,
                "goal-01",
                expected_revision=1,
                idempotency_key="clear-corrupt",
            )

        event = json.loads(first_line)
        event["protocolVersion"] = 99
        path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        unknown = self.service.read(self.session_id)
        self.assertEqual(unknown.health, "corrupted")
        self.assertEqual(unknown.state.revision, 0)
        self.assertIn("unsupported goal protocol", unknown.error["message"])

    def test_revision_gap_is_corruption(self):
        self.create_goal()
        path = self.service.events_path(self.session_id)
        event = json.loads(path.read_text(encoding="utf-8"))
        event["eventId"] = "gap-event"
        event["revision"] = 3
        event["expectedRevision"] = 2
        event["idempotencyKey"] = "gap-request"
        event["snapshot"]["revision"] = 3
        event["requestHash"] = request_hash({
            "operation": "replace",
            "sessionId": self.session_id,
            "goalId": event["goalId"],
            "expectedRevision": 2,
            "snapshot": event["snapshot"],
        })
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        result = self.service.read(self.session_id)
        self.assertEqual(result.health, "corrupted")
        self.assertEqual(result.state.revision, 1)
        self.assertIn("contiguous", result.error["message"])

    def test_clear_tombstone_preserves_history_and_prevents_id_reuse(self):
        self.create_goal()
        cleared = self.service.clear(
            self.session_id,
            "goal-01",
            expected_revision=1,
            idempotency_key="clear-01",
        )
        self.assertIsNone(cleared["goal"])
        self.assertEqual(cleared["tombstone"]["goalId"], "goal-01")
        self.assertEqual(len(self.service.events_path(self.session_id).read_text().splitlines()), 2)
        clear_retry = self.service.clear(
            self.session_id,
            "goal-01",
            expected_revision=1,
            idempotency_key="clear-01",
        )
        self.assertTrue(clear_retry["noOp"])
        self.assertEqual(clear_retry["revision"], 2)
        with self.assertRaisesRegex(GoalConflictError, "different payload"):
            self.service.clear(
                self.session_id,
                "goal-02",
                expected_revision=1,
                idempotency_key="clear-01",
            )

        with self.assertRaisesRegex(GoalConflictError, "cannot be reused"):
            self.service.replace(
                self.session_id,
                make_snapshot(session_id=self.session_id, goal_id="goal-01", revision=3),
                expected_revision=2,
                idempotency_key="reuse-01",
            )
        new_goal = self.service.replace(
            self.session_id,
            make_snapshot(session_id=self.session_id, goal_id="goal-02", revision=3),
            expected_revision=2,
            idempotency_key="create-02",
        )
        self.assertEqual(new_goal["goal"]["goalId"], "goal-02")

    def test_new_service_instance_is_always_disarmed(self):
        self.create_goal()
        self.assertFalse(GoalService(self.root).read(self.session_id).projection()["armed"])

    def test_archive_and_delete_check_existence_under_mutation_lock(self):
        destination = self.root / "archive" / "goal.jsonl"
        order = []

        @contextmanager
        def observed_lock(_session_id):
            order.append("locked")
            yield

        with mock.patch.object(self.service, "_mutation_lock", observed_lock):
            self.assertIsNone(self.service.archive(self.session_id, destination))
            order.append("archive-returned")
            self.assertFalse(self.service.delete(self.session_id))
            order.append("delete-returned")

        self.assertEqual(
            order,
            ["locked", "archive-returned", "locked", "delete-returned"],
        )

    def test_invalid_step_state_never_reaches_disk(self):
        snapshot = make_snapshot(session_id=self.session_id)
        snapshot["steps"][0]["status"] = "blocked"
        with self.assertRaises(GoalProtocolError):
            self.service.replace(
                self.session_id,
                snapshot,
                expected_revision=0,
                idempotency_key="invalid-state",
            )
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
