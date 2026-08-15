import json
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import server
from goal_store import GoalService
from tests.test_goal_protocol import make_snapshot


class TestSessionPersistence(unittest.TestCase):
    def test_write_json_is_atomic_under_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.json"
            errors = []

            def writer(index):
                try:
                    server.write_json(target, {"id": "session", "writer": index, "messages": [index] * 20})
                except Exception as exc:  # pragma: no cover - assertion reports details
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["id"], "session")
            self.assertEqual(len(data["messages"]), 20)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    # ── JSONL-specific tests ──────────────────────────────────────

    def test_write_jsonl_atomic(self):
        """write_jsonl is atomic (temp+replace) — no corruption under concurrent writers."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.jsonl"
            errors = []

            def writer(index):
                try:
                    msgs = [{"role": "user", "content": f"msg-{index}-{i}"} for i in range(20)]
                    server.write_jsonl(target, msgs)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            msgs = server.read_jsonl(target)
            self.assertEqual(len(msgs), 20, "Should have exactly 20 messages (one writer wins)")
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_append_jsonl_concurrent(self):
        """append_jsonl: concurrent appends should preserve all messages."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.jsonl"
            errors = []

            def appender(prefix, count):
                try:
                    msgs = [{"role": "user", "content": f"{prefix}-{i}"} for i in range(count)]
                    server.append_jsonl(target, msgs)
                except Exception as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=appender, args=(f"t{t}", 10))
                for t in range(5)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            msgs = server.read_jsonl(target)
            self.assertEqual(len(msgs), 50, "5 threads x 10 messages = 50")

    def test_read_jsonl_corrupted_last_line(self):
        """read_jsonl skips a corrupted/partial last line (simulated crash)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "crash.jsonl"
            target.write_text(
                '{"role":"user","content":"msg1"}\n'
                '{"role":"assistant","content":"msg2"}\n'
                '{"role":"assistant","conte',  # incomplete — power loss mid-write
                encoding="utf-8",
            )
            msgs = server.read_jsonl(target)
            self.assertEqual(len(msgs), 2, "Should recover first 2 intact lines, skip partial")

    def test_read_jsonl_empty_and_missing(self):
        """read_jsonl returns [] for missing or empty file."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(server.read_jsonl(Path(tmp) / "nope.jsonl"), [])
            empty = Path(tmp) / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            self.assertEqual(server.read_jsonl(empty), [])

    def test_read_jsonl_skips_blank_lines(self):
        """read_jsonl skips blank lines between messages."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "blanks.jsonl"
            target.write_text(
                '{"role":"user","content":"a"}\n'
                '\n'
                '{"role":"assistant","content":"b"}\n'
                '\n\n',
                encoding="utf-8",
            )
            msgs = server.read_jsonl(target)
            self.assertEqual(len(msgs), 2)

    def test_count_jsonl_lines(self):
        """count_jsonl_lines returns correct count without parsing JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "count.jsonl"
            self.assertEqual(server.count_jsonl_lines(target), 0)
            for i in range(100):
                server.append_jsonl(target, [{"role": "user", "content": str(i)}])
            self.assertEqual(server.count_jsonl_lines(target), 100)

    def test_read_last_jsonl_line(self):
        """read_last_jsonl_line returns the last message's parsed JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "last.jsonl"
            self.assertIsNone(server.read_last_jsonl_line(target))
            server.write_jsonl(target, [
                {"role": "user", "content": "first", "_time": "2026-01-01T00:00:00"},
                {"role": "assistant", "content": "last", "_time": "2026-07-15T12:00:00"},
            ])
            last = server.read_last_jsonl_line(target)
            self.assertEqual(last["content"], "last")
            self.assertEqual(last["_time"], "2026-07-15T12:00:00")

    def test_messages_path(self):
        """messages_path returns the correct .jsonl path."""
        p = server.messages_path("abc123def456")
        self.assertTrue(p.name.endswith(".jsonl"))
        self.assertIn("abc123def456", str(p))


class TestGoalSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.sessions_dir = self.root / "sessions"
        self.goals_dir = self.root / "goals"
        self.patch_sessions = mock.patch.object(server, "SESSIONS_DIR", self.sessions_dir)
        self.patch_goals = mock.patch.object(server, "GOALS_DIR", self.goals_dir)
        self.patch_sessions.start()
        self.patch_goals.start()
        self.addCleanup(self.patch_sessions.stop)
        self.addCleanup(self.patch_goals.stop)

    @staticmethod
    def make_handler(body=None):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body or {})
        handler.send_json = mock.Mock()
        return handler

    def create_session(self, messages=None):
        handler = self.make_handler({"title": "Goal lifecycle", "messages": messages or []})
        server.CodeHandler.create_session(handler)
        return handler.send_json.call_args.args[0]

    def create_goal(self, session_id):
        return GoalService(self.goals_dir).replace(
            session_id,
            make_snapshot(session_id=session_id),
            expected_revision=0,
            idempotency_key="create-session-goal",
        )

    def test_goal_sidecar_never_changes_session_messages(self):
        session = self.create_session([{"role": "user", "content": "hello"}])
        message_file = server.messages_path(session["id"])
        before = hashlib.sha256(message_file.read_bytes()).hexdigest()
        self.create_goal(session["id"])
        after = hashlib.sha256(message_file.read_bytes()).hexdigest()
        self.assertEqual(after, before)
        self.assertEqual(server.read_jsonl(message_file), [{"role": "user", "content": "hello"}])

    def test_goal_query_is_read_only_and_missing_session_is_404(self):
        session = self.create_session()
        handler = self.make_handler()
        server.CodeHandler.get_session_goal(handler, session["id"])
        response = handler.send_json.call_args.args[0]["data"]
        self.assertEqual(response["revision"], 0)
        self.assertFalse(response["exists"])
        self.assertFalse(self.goals_dir.exists())

        missing = self.make_handler()
        server.CodeHandler.get_session_goal(missing, "missing01")
        self.assertEqual(missing.send_json.call_args.args[1], 404)
        self.assertFalse(self.goals_dir.exists())

    def test_corrupt_goal_sidecar_does_not_break_session_read(self):
        messages = [{"role": "user", "content": "session remains readable"}]
        session = self.create_session(messages)
        self.create_goal(session["id"])
        with open(GoalService(self.goals_dir).events_path(session["id"]), "a", encoding="utf-8") as handle:
            handle.write("{corrupt-middle}\n")

        handler = self.make_handler()
        server.CodeHandler.get_session(handler, session["id"])
        response = handler.send_json.call_args.args[0]
        self.assertEqual(response["messages"], messages)
        goal = GoalService(self.goals_dir).read(session["id"])
        self.assertEqual(goal.health, "corrupted")
        self.assertFalse(goal.writable)

    def test_delete_session_removes_goal_sidecar(self):
        session = self.create_session()
        self.create_goal(session["id"])
        goal_path = GoalService(self.goals_dir).events_path(session["id"])
        self.assertTrue(goal_path.exists())

        handler = self.make_handler()
        server.CodeHandler.delete_session(handler, session["id"])
        self.assertFalse(goal_path.exists())
        self.assertFalse(server.session_path(session["id"]).exists())

    def test_archive_copies_goal_sidecar_without_changing_source(self):
        messages = [{"role": "user", "content": "archive me"}]
        session = self.create_session(messages)
        self.create_goal(session["id"])
        source = GoalService(self.goals_dir).events_path(session["id"])
        source_bytes = source.read_bytes()

        handler = self.make_handler({"messages": messages})
        server.CodeHandler.archive_session(handler, session["id"])
        archives = list((self.sessions_dir / "archive").glob(f"{session['id']}_*.goal.jsonl"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), source_bytes)
        self.assertEqual(source.read_bytes(), source_bytes)

    def test_branch_copies_messages_but_not_goal(self):
        messages = [{"role": "user", "content": "branch me"}]
        parent = self.create_session(messages)
        self.create_goal(parent["id"])
        handler = self.make_handler({"title": "Child"})
        server.CodeHandler.branch_session(handler, parent["id"])
        child = handler.send_json.call_args.args[0]

        self.assertEqual(child["messages"], messages)
        child_goal = GoalService(self.goals_dir).read(child["id"]).projection()
        self.assertFalse(child_goal["exists"])
        self.assertIsNone(child_goal["goal"])

    def test_import_snapshot_does_not_copy_existing_goal(self):
        parent = self.create_session()
        self.create_goal(parent["id"])
        source = self.root / "foreign.jsonl"
        source.write_text('{"type":"example"}\n', encoding="utf-8")
        source_info = server._import_source_state(source, include_hash=True)
        imported = server._persist_import_snapshot(
            source="codex",
            source_path=source,
            source_info=source_info,
            source_session_id="foreign-session",
            requested_session_id="imported01",
            force_requested_id=True,
            title="Imported",
            created_at="2026-08-15T12:00:00",
            messages=[{"role": "user", "content": "imported"}],
            stats={},
            last_usage={},
            resolved_project_id=None,
            resolved_cwd="",
        )
        self.assertEqual(imported["id"], "imported01")
        imported_goal = GoalService(self.goals_dir).read("imported01").projection()
        self.assertFalse(imported_goal["exists"])
        self.assertEqual(
            GoalService(self.goals_dir).read(parent["id"]).projection()["goal"]["goalId"],
            "goal-01",
        )


if __name__ == "__main__":
    unittest.main()
