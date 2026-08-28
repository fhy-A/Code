import json
import hashlib
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import server
from goal_runtime import GoalCreationContext, GoalV2Runtime


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


class TestSessionIndexConversationTime(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sessions_dir = Path(self.temp_dir.name) / "sessions"
        self.patch_sessions = mock.patch.object(
            server,
            "SESSIONS_DIR",
            self.sessions_dir,
        )
        self.patch_location = mock.patch.object(
            server,
            "_session_location",
            return_value=(None, ""),
        )
        self.patch_sessions.start()
        self.patch_location.start()
        self.addCleanup(self.patch_sessions.stop)
        self.addCleanup(self.patch_location.stop)

    @staticmethod
    def make_handler(body=None):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body or {})
        handler.send_json = mock.Mock()
        return handler

    def write_flat_session(self, meta, messages=None):
        sid = meta["id"]
        server.write_json(self.sessions_dir / f"{sid}.json", meta)
        server.write_jsonl(
            self.sessions_dir / f"{sid}.jsonl",
            messages or [],
        )

    def write_raw_index(self, entries):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        server._session_index_path().write_text(
            "".join(
                json.dumps(entry, ensure_ascii=False) + "\n"
                for entry in entries
            ),
            encoding="utf-8",
        )

    def test_get_sessions_backfills_missing_time_once_and_sorts_stably(self):
        self.write_flat_session({
            "id": "legacy01",
            "title": "Legacy",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-23T15:00:00Z",
            "lastMessageTime": "2026-08-20T10:00:00Z",
            "messageCount": 2,
        })
        self.write_flat_session({
            "id": "protected02",
            "title": "Protected",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-20T11:00:00Z",
            "lastMessageTime": "2026-08-20T09:00:00Z",
            "messageCount": 2,
        })
        self.write_flat_session({
            "id": "tiealpha",
            "title": "Tie alpha",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-20T12:00:00Z",
            "messageCount": 1,
        })
        self.write_flat_session({
            "id": "tiebeta0",
            "title": "Tie beta",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-20T12:00:00Z",
            "messageCount": 1,
        })
        self.write_flat_session({
            "id": "invalid03",
            "title": "Invalid timestamp",
            "createdAt": "2026-08-20T07:00:00Z",
            "updatedAt": "2026-08-20T09:00:00Z",
            "lastMessageTime": "2026-08-20T08:00:00Z",
            "messageCount": 1,
        })
        base_entry = {
            "messageCount": 1,
            "source": "code",
            "sourceBadgeVisible": False,
            "interactionState": "",
        }
        self.write_raw_index([
            {
                **base_entry,
                "id": "legacy01",
                "title": "Legacy",
                "updatedAt": "2026-08-23T15:00:00Z",
            },
            {
                **base_entry,
                "id": "protected02",
                "title": "Protected",
                "updatedAt": "2026-08-20T11:00:00Z",
                "lastMessageTime": "2026-08-20T13:00:00Z",
            },
            {
                **base_entry,
                "id": "tiealpha",
                "title": "Tie alpha",
                "updatedAt": "2026-08-20T12:00:00Z",
                "lastMessageTime": "2026-08-20T12:00:00Z",
            },
            {
                **base_entry,
                "id": "tiebeta0",
                "title": "Tie beta",
                "updatedAt": "2026-08-20T12:00:00Z",
                "lastMessageTime": "2026-08-20T12:00:00Z",
            },
            {
                **base_entry,
                "id": "invalid03",
                "title": "Invalid timestamp",
                "updatedAt": "2026-08-20T09:00:00Z",
                "lastMessageTime": "not-a-time",
            },
        ])

        with mock.patch.object(server, "read_json", wraps=server.read_json) as read_meta:
            first = self.make_handler()
            server.CodeHandler.get_sessions(first)
            first_data = first.send_json.call_args.args[0]["data"]
            first_reads = read_meta.call_count

            second = self.make_handler()
            server.CodeHandler.get_sessions(second)
            second_data = second.send_json.call_args.args[0]["data"]

        self.assertEqual(first_reads, 1)
        self.assertEqual(read_meta.call_count, first_reads)
        self.assertEqual(
            [item["id"] for item in first_data],
            ["protected02", "tiealpha", "tiebeta0", "legacy01", "invalid03"],
        )
        self.assertEqual(second_data, first_data)
        response = {item["id"]: item for item in first_data}
        self.assertEqual(response["legacy01"]["lastMessageTime"], "2026-08-20T10:00:00Z")
        self.assertEqual(response["protected02"]["lastMessageTime"], "2026-08-20T13:00:00Z")
        self.assertEqual(response["invalid03"]["lastMessageTime"], "2026-08-20T09:00:00Z")
        index = server._read_session_index()
        self.assertEqual(index["legacy01"]["lastMessageTime"], "2026-08-20T10:00:00Z")
        self.assertEqual(index["protected02"]["lastMessageTime"], "2026-08-20T13:00:00Z")
        self.assertEqual(index["invalid03"]["lastMessageTime"], "not-a-time")

    def test_interaction_state_derivation_is_whitelisted_and_request_authoritative(self):
        secret = "SESSION-INTERACTION-SECRET-SENTINEL"
        cases = [
            ({"runState": {"userInputRequest": {
                "status": "pending", "prompt": secret,
            }}}, "waiting_user_input"),
            ({"runState": {"authorizationRequest": {
                "status": "pending", "reason": secret,
            }}}, "waiting_authorization"),
            ({"runState": {"skillEvidenceRequest": {
                "status": "pending", "gateId": secret,
            }}}, "waiting_skill_evidence"),
            ({"runState": {"skillEvidenceRequest": {
                "status": "resolved", "gateId": secret,
            }}}, ""),
            ({"runState": {"status": "waiting-skill-evidence"}}, ""),
            ({"runState": {}, "interactionState": "waiting_authorization"}, ""),
        ]
        for session, expected in cases:
            with self.subTest(expected=expected, session=session):
                self.assertEqual(server._session_interaction_state(session), expected)

    def test_interaction_state_create_save_clear_and_secret_free_summary(self):
        secret = "SESSION-INTERACTION-SECRET-SENTINEL"
        create = self.make_handler({
            "title": "Interaction state",
            "messages": [],
            "interactionState": "waiting_authorization",
            "runState": {
                "userInputRequest": {
                    "status": "pending",
                    "prompt": secret,
                },
            },
        })
        server.CodeHandler.create_session(create)
        session_id = create.send_json.call_args.args[0]["id"]

        expected_states = [
            "waiting_user_input",
            "waiting_authorization",
            "waiting_skill_evidence",
            "",
        ]
        run_states = [
            {"userInputRequest": {"status": "pending", "prompt": secret}},
            {"authorizationRequest": {"status": "pending", "reason": secret}},
            {"skillEvidenceRequest": {"status": "pending", "gateId": secret}},
            {},
        ]
        observed = []
        for run_state, expected in zip(run_states, expected_states):
            save = self.make_handler({
                "runState": run_state,
                "interactionState": "waiting_authorization",
            })
            server.CodeHandler.save_session(save, session_id)
            index_entry = server._read_session_index()[session_id]
            self.assertEqual(index_entry["interactionState"], expected)
            observed.append(index_entry["interactionState"])
            serialized_index = server._session_index_path().read_text(encoding="utf-8")
            self.assertNotIn(secret, serialized_index)

            listed = self.make_handler()
            server.CodeHandler.get_sessions(listed)
            summary = next(
                item
                for item in listed.send_json.call_args.args[0]["data"]
                if item["id"] == session_id
            )
            self.assertEqual(summary["interactionState"], expected)
            self.assertEqual(summary["runState"], {})
            self.assertNotIn(secret, json.dumps(summary))

        self.assertEqual(observed, expected_states)

    def test_legacy_interaction_state_backfills_once_and_metadata_writes_preserve_it(self):
        secret = "SESSION-INTERACTION-SECRET-SENTINEL"
        self.write_flat_session({
            "id": "legacy-interaction",
            "title": "Legacy interaction",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-20T10:00:00Z",
            "lastMessageTime": "2026-08-20T09:00:00Z",
            "messageCount": 1,
            "runState": {
                "skillEvidenceRequest": {
                    "status": "pending",
                    "gateId": secret,
                },
            },
        })
        self.write_raw_index([{
            "id": "legacy-interaction",
            "title": "Legacy interaction",
            "updatedAt": "2026-08-20T10:00:00Z",
            "lastMessageTime": "2026-08-20T09:00:00Z",
            "messageCount": 1,
            "source": "code",
            "sourceBadgeVisible": False,
        }])

        with mock.patch.object(server, "read_json", wraps=server.read_json) as read_meta:
            first = self.make_handler()
            server.CodeHandler.get_sessions(first)
            first_reads = read_meta.call_count
            second = self.make_handler()
            server.CodeHandler.get_sessions(second)

        self.assertEqual(first_reads, 1)
        self.assertEqual(read_meta.call_count, first_reads)
        index_entry = server._read_session_index()["legacy-interaction"]
        self.assertEqual(index_entry["interactionState"], "waiting_skill_evidence")
        self.assertNotIn(secret, json.dumps(index_entry))
        first_summary = first.send_json.call_args.args[0]["data"][0]
        second_summary = second.send_json.call_args.args[0]["data"][0]
        self.assertEqual(first_summary, second_summary)
        self.assertEqual(first_summary["interactionState"], "waiting_skill_evidence")

        server._write_session_index_entry(
            "legacy-interaction",
            "Metadata-only rename",
            "2026-08-20T11:00:00Z",
            1,
        )
        preserved = server._read_session_index()["legacy-interaction"]
        self.assertEqual(preserved["interactionState"], "waiting_skill_evidence")
        self.assertNotIn(secret, json.dumps(preserved))

    def test_legacy_shanghai_timestamps_round_trip_as_canonical_utc(self):
        shanghai = server.dt.timezone(server.dt.timedelta(hours=8))
        with mock.patch.object(server, "_session_local_timezone", return_value=shanghai):
            record = server._session_api_record({
                "id": "timezone01",
                "createdAt": "2026-08-22T13:37:00",
                "updatedAt": "2026-08-22T13:37:00+08:00",
                "lastMessageTime": "2026-08-22T05:37:00Z",
                "messageCount": 1,
            })
            self.assertEqual(record["createdAt"], "2026-08-22T05:37:00Z")
            self.assertEqual(record["updatedAt"], "2026-08-22T05:37:00Z")
            self.assertEqual(record["lastMessageTime"], "2026-08-22T05:37:00Z")
            self.assertEqual(
                server._last_msg_time([{
                    "role": "user",
                    "content": "legacy local",
                    "_time": "2026-08-22T13:37:00",
                }]),
                "2026-08-22T05:37:00Z",
            )

            self.write_flat_session({
                "id": "timezone01",
                "title": "Timezone",
                "createdAt": "2026-08-22T13:37:00",
                "updatedAt": "2026-08-22T13:37:00",
                "lastMessageTime": "2026-08-22T13:37:00",
                "messageCount": 1,
            })
            self.write_raw_index([{
                "id": "timezone01",
                "title": "Timezone",
                "updatedAt": "2026-08-22T13:37:00",
                "lastMessageTime": "2026-08-22T13:37:00",
                "messageCount": 1,
                "source": "code",
                "sourceBadgeVisible": False,
            }])
            first = self.make_handler()
            second = self.make_handler()
            server.CodeHandler.get_sessions(first)
            server.CodeHandler.get_sessions(second)

        first_record = first.send_json.call_args.args[0]["data"][0]
        second_record = second.send_json.call_args.args[0]["data"][0]
        self.assertEqual(first_record, second_record)
        self.assertEqual(first_record["lastMessageTime"], "2026-08-22T05:37:00Z")
        self.assertEqual(first_record["updatedAt"], "2026-08-22T05:37:00Z")
        self.assertEqual(
            server._read_session_index()["timezone01"]["lastMessageTime"],
            "2026-08-22T13:37:00",
        )

    def test_message_writes_advance_time_while_metadata_writes_preserve_it(self):
        first_time = "2026-08-20T10:00:00Z"
        next_time = "2026-08-20T11:00:00Z"
        create = self.make_handler({
            "title": "Conversation time",
            "messages": [{
                "role": "user",
                "content": "first",
                "_time": first_time,
            }],
        })
        server.CodeHandler.create_session(create)
        created = create.send_json.call_args.args[0]
        session_id = created["id"]
        self.assertRegex(created["createdAt"], r"Z$")
        self.assertRegex(created["updatedAt"], r"Z$")
        persisted_created = server.read_json(server.session_path(session_id), {})["createdAt"]
        self.assertRegex(persisted_created, r"(?:Z|[+-]\d{2}:\d{2})$")
        self.assertEqual(
            server._read_session_index()[session_id]["lastMessageTime"],
            first_time,
        )

        metadata_only = self.make_handler({"title": "Renamed only"})
        server.CodeHandler.save_session(metadata_only, session_id)
        after_metadata = server._read_session_index()[session_id]
        self.assertEqual(after_metadata["title"], "Renamed only")
        self.assertEqual(after_metadata["lastMessageTime"], first_time)

        append = self.make_handler({
            "messages": [{
                "role": "assistant",
                "content": "continued",
                "_time": next_time,
            }],
        })
        server.CodeHandler.append_messages(append, session_id)
        self.assertEqual(
            server._read_session_index()[session_id]["lastMessageTime"],
            next_time,
        )

        internals = self.make_handler({
            "messages": [
                {
                    "role": "tool-result",
                    "content": "internal tool result",
                    "_time": "2026-08-20T11:30:00Z",
                },
                {
                    "role": "assistant",
                    "content": "internal checkpoint",
                    "_time": "2026-08-20T11:31:00Z",
                    "meta": {"kind": "auto-context-compaction"},
                },
            ],
        })
        server.CodeHandler.append_messages(internals, session_id)
        self.assertEqual(
            server._read_session_index()[session_id]["lastMessageTime"],
            next_time,
        )

        server._write_session_index_entry(
            session_id,
            "Metadata-only index update",
            "2026-08-23T15:00:00Z",
            2,
        )
        self.assertEqual(
            server._read_session_index()[session_id]["lastMessageTime"],
            next_time,
        )

        branch = self.make_handler({"title": "Conversation branch"})
        server.CodeHandler.branch_session(branch, session_id)
        child = branch.send_json.call_args.args[0]
        index = server._read_session_index()
        self.assertEqual(index[session_id]["lastMessageTime"], next_time)
        self.assertEqual(index[child["id"]]["lastMessageTime"], next_time)

    def test_empty_session_and_import_use_deterministic_source_times(self):
        empty_handler = self.make_handler({"title": "Empty", "messages": []})
        server.CodeHandler.create_session(empty_handler)
        empty = empty_handler.send_json.call_args.args[0]
        empty_index = server._read_session_index()[empty["id"]]
        self.assertEqual(empty_index["lastMessageTime"], "")

        listed = self.make_handler()
        server.CodeHandler.get_sessions(listed)
        listed_empty = next(
            item
            for item in listed.send_json.call_args.args[0]["data"]
            if item["id"] == empty["id"]
        )
        self.assertEqual(listed_empty["lastMessageTime"], empty["updatedAt"])

        source = Path(self.temp_dir.name) / "foreign.jsonl"
        source.write_text('{"source":"foreign"}\n', encoding="utf-8")
        imported = server._persist_import_snapshot(
            source="codex",
            source_path=source,
            source_info=server._import_source_state(source, include_hash=True),
            source_session_id="foreign-session",
            requested_session_id="imported01",
            force_requested_id=True,
            title="Imported",
            created_at="2026-08-19T08:00:00",
            messages=[
                {"role": "system", "content": "boundary"},
                {"role": "user", "content": "first", "_time": "2026-08-19T09:00:00Z"},
                {"role": "assistant", "content": "last", "_time": "2026-08-19T10:00:00Z"},
            ],
            stats={},
            last_usage={},
            resolved_project_id=None,
            resolved_cwd="",
        )
        self.assertEqual(imported["lastMessageTime"], "2026-08-19T10:00:00Z")
        self.assertEqual(
            server._read_session_index()["imported01"]["lastMessageTime"],
            "2026-08-19T10:00:00Z",
        )

    def test_lazy_backfill_and_concurrent_append_share_one_index_lock(self):
        self.write_flat_session({
            "id": "legacy04",
            "title": "Legacy",
            "createdAt": "2026-08-20T08:00:00Z",
            "updatedAt": "2026-08-20T10:00:00Z",
            "lastMessageTime": "2026-08-20T09:00:00Z",
            "messageCount": 1,
            "runState": {
                "authorizationRequest": {
                    "status": "pending",
                    "reason": "CONCURRENT-INTERACTION-SECRET",
                },
            },
        })
        self.write_raw_index([{
            "id": "legacy04",
            "title": "Legacy",
            "updatedAt": "2026-08-20T10:00:00Z",
            "messageCount": 1,
            "source": "code",
            "sourceBadgeVisible": False,
        }])
        reader_entered = threading.Event()
        release_reader = threading.Event()
        writer_started = threading.Event()
        writer_done = threading.Event()
        errors = []
        original_read_json = server.read_json

        def blocked_read_json(path, default=None):
            if Path(path).name == "legacy04.json":
                reader_entered.set()
                if not release_reader.wait(timeout=5):
                    raise TimeoutError("test reader gate timed out")
            return original_read_json(path, default)

        handler = self.make_handler()

        def reader():
            try:
                server.CodeHandler.get_sessions(handler)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        def writer():
            try:
                writer_started.set()
                server._write_session_index_entry(
                    "newwrite05",
                    "Concurrent writer",
                    "2026-08-20T11:00:00Z",
                    1,
                    last_message_time="2026-08-20T11:00:00Z",
                    interaction_state="waiting_user_input",
                )
                writer_done.set()
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        with mock.patch.object(server, "read_json", side_effect=blocked_read_json):
            read_thread = threading.Thread(target=reader)
            write_thread = threading.Thread(target=writer)
            read_thread.start()
            self.assertTrue(reader_entered.wait(timeout=5))
            write_thread.start()
            self.assertTrue(writer_started.wait(timeout=5))
            self.assertFalse(writer_done.is_set())
            release_reader.set()
            read_thread.join(timeout=5)
            write_thread.join(timeout=5)

        self.assertFalse(read_thread.is_alive())
        self.assertFalse(write_thread.is_alive())
        self.assertEqual(errors, [])
        index = server._read_session_index()
        self.assertEqual(set(index), {"legacy04", "newwrite05"})
        self.assertEqual(index["legacy04"]["lastMessageTime"], "2026-08-20T09:00:00Z")
        self.assertEqual(index["newwrite05"]["lastMessageTime"], "2026-08-20T11:00:00Z")
        self.assertEqual(index["legacy04"]["interactionState"], "waiting_authorization")
        self.assertEqual(index["newwrite05"]["interactionState"], "waiting_user_input")
        self.assertNotIn("CONCURRENT-INTERACTION-SECRET", json.dumps(index))


class TestGoalSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.sessions_dir = self.root / "sessions"
        self.goals_dir = self.root / "goals-v2"
        self.patch_sessions = mock.patch.object(server, "SESSIONS_DIR", self.sessions_dir)
        self.patch_data = mock.patch.object(server, "DATA_DIR", self.root)
        self.patch_sessions.start()
        self.patch_data.start()
        self.addCleanup(self.patch_sessions.stop)
        self.addCleanup(self.patch_data.stop)

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
        return GoalV2Runtime(self.root).create_goal(
            session_id,
            "Verify Session-scoped Goal v2 lifecycle",
            context=GoalCreationContext(
                session_id=session_id,
                origin_message_id="message-goal-origin",
                client_request_id="request-goal-origin",
                owner_run_id="run-goal-origin",
                permission_profile="read",
                source_kind="explicit",
            ),
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
        server.CodeHandler.get_session_goal_v2(handler, session["id"])
        response = handler.send_json.call_args.args[0]["data"]
        self.assertEqual(response["revision"], 0)
        self.assertFalse(response["exists"])
        self.assertFalse(self.goals_dir.exists())

        missing = self.make_handler()
        server.CodeHandler.get_session_goal_v2(missing, "missing01")
        self.assertEqual(missing.send_json.call_args.args[1], 404)
        self.assertFalse(self.goals_dir.exists())

    def test_goal_control_route_binds_existing_session_and_persists_confirmed_origin(self):
        origin = {
            "id": "message-explicit-route",
            "role": "user",
            "content": "/goal Verify explicit v2 route",
            "meta": {"goalOrigin": {
                "messageId": "message-explicit-route",
                "clientRequestId": "request-explicit-route",
            }},
        }
        session = self.create_session([origin])
        message_file = server.messages_path(session["id"])
        before_runs = set(server._agent_runs)
        handler = self.make_handler({
            "operation": "explicit_create",
            "expectedRevision": 0,
            "idempotencyKey": "route-explicit-v2-01",
            "objective": "Verify explicit v2 route",
            "messageId": "message-explicit-route",
            "clientRequestId": "request-explicit-route",
            "permissionProfile": "read",
        })
        server.CodeHandler.control_session_goal_v2(handler, session["id"])
        response = handler.send_json.call_args.args[0]["data"]
        self.assertEqual(response["goal"]["lifecycle"], "draft")
        self.assertEqual(response["goal"]["sourceKind"], "explicit")
        stored = server.read_jsonl(message_file)
        self.assertTrue(stored[0]["meta"]["goalOrigin"]["confirmed"])
        self.assertEqual(stored[0]["meta"]["goalOrigin"]["goalId"], response["goal"]["goalId"])
        self.assertEqual(set(server._agent_runs), before_runs)

        missing = self.make_handler({
            "operation": "explicit_create",
            "expectedRevision": 0,
            "idempotencyKey": "missing-explicit-v2-01",
            "objective": "Do not create an orphan Goal",
            "messageId": "message-explicit-route",
            "clientRequestId": "request-explicit-route",
            "permissionProfile": "read",
        })
        server.CodeHandler.control_session_goal_v2(missing, "missing01")
        self.assertEqual(missing.send_json.call_args.args[1], 404)
        self.assertFalse(GoalV2Runtime(self.root).service.events_path("missing01").exists())

    def test_goal_message_metadata_projects_only_explicit_origin(self):
        message = {
            "id": "message-autonomous",
            "role": "user",
            "content": "ordinary complex task",
            "meta": {"goalOrigin": {
                "messageId": "message-autonomous",
                "clientRequestId": "request-autonomous",
                "goalId": "goal-autonomous",
                "sourceKind": "autonomous",
                "confirmedRevision": 2,
                "confirmed": True,
            }},
        }
        projection = {
            "exists": True,
            "health": "healthy",
            "revision": 2,
            "goal": {
                "goalId": "goal-autonomous",
                "originMessageId": "message-autonomous",
                "clientRequestId": "request-autonomous",
                "sourceKind": "autonomous",
            },
        }
        merged = server._merge_goal_v2_message_metadata(
            "session-autonomous",
            [message],
            projection=projection,
            existing_messages=[message],
        )
        self.assertEqual(merged[0]["meta"]["goalOrigin"], {
            "messageId": "message-autonomous",
            "clientRequestId": "request-autonomous",
        })
        self.assertIsNone(server._goal_v2_confirmed_origin(projection))

    def test_explicit_completion_metadata_binds_unique_final_public_message(self):
        projection = {
            "exists": True,
            "health": "healthy",
            "revision": 8,
            "goal": {
                "goalId": "goal-completed",
                "sourceKind": "explicit",
                "lifecycle": "completed",
                "ownerRunId": "run-completed",
                "createdAt": "2026-08-15T10:00:00Z",
                "updatedAt": "2026-08-15T10:03:07Z",
            },
        }
        messages = [
            {"role": "assistant", "content": "Earlier round", "meta": {
                "agentRunId": "run-completed",
            }},
            {"role": "assistant", "content": "Final public answer", "meta": {
                "agentRunId": "run-completed",
                "_agentRunTerminal": True,
            }},
        ]
        run = {
            "session_id": "session-completed",
            "status": "completed",
        }
        with mock.patch.object(server, "_get_agent_run", return_value=run):
            merged = server._merge_goal_v2_message_metadata(
                "session-completed",
                messages,
                projection=projection,
                existing_messages=[],
            )
        self.assertNotIn("goalCompletion", merged[0].get("meta", {}))
        self.assertEqual(merged[1]["meta"]["goalCompletion"], {
            "goalId": "goal-completed",
            "sourceKind": "explicit",
            "sourceRunId": "run-completed",
            "createdAt": "2026-08-15T10:00:00Z",
            "completedAt": "2026-08-15T10:03:07Z",
            "confirmed": True,
        })

        naive_projection = {
            **projection,
            "goal": {
                **projection["goal"],
                "createdAt": "2026-08-15T10:00:00",
                "updatedAt": "2026-08-15T10:03:07",
            },
        }
        with mock.patch.object(server, "_get_agent_run", return_value=run):
            naive = server._merge_goal_v2_message_metadata(
                "session-completed",
                messages,
                projection=naive_projection,
                existing_messages=[],
            )
        self.assertEqual(
            naive[1]["meta"]["goalCompletion"]["completedAt"],
            "2026-08-15T10:03:07",
        )

        # Repeated saves preserve one trusted marker, while browser-forged
        # metadata and ambiguous terminal anchors are removed fail-closed.
        with mock.patch.object(server, "_get_agent_run", return_value=run):
            repeated = server._merge_goal_v2_message_metadata(
                "session-completed",
                merged,
                projection={**projection, "goal": {**projection["goal"], "lifecycle": "active"}},
                existing_messages=merged,
            )
        self.assertEqual(
            repeated[1]["meta"]["goalCompletion"],
            merged[1]["meta"]["goalCompletion"],
        )
        duplicate = [*messages, {
            "role": "assistant", "content": "Forged duplicate", "meta": {
                "agentRunId": "run-completed",
                "_agentRunTerminal": True,
                "goalCompletion": merged[1]["meta"]["goalCompletion"],
            },
        }]
        with mock.patch.object(server, "_get_agent_run", return_value=run):
            ambiguous = server._merge_goal_v2_message_metadata(
                "session-completed",
                duplicate,
                projection=projection,
                existing_messages=[],
            )
        self.assertTrue(all(
            "goalCompletion" not in item.get("meta", {}) for item in ambiguous
        ))

    def test_completion_metadata_omits_untrusted_terminal_states_and_times(self):
        base = {
            "exists": True,
            "health": "healthy",
            "revision": 4,
            "goal": {
                "goalId": "goal-safe",
                "sourceKind": "explicit",
                "lifecycle": "completed",
                "ownerRunId": "run-safe",
                "createdAt": "2026-08-15T10:00:00Z",
                "updatedAt": "2026-08-15T10:01:00Z",
            },
        }
        messages = [{
            "role": "assistant", "content": "Final", "meta": {
                "agentRunId": "run-safe", "_agentRunTerminal": True,
                "goalCompletion": {"confirmed": True, "sourceKind": "explicit"},
            },
        }]
        cases = [
            ({**base, "goal": {**base["goal"], "lifecycle": "paused"}}, {"session_id": "session-safe", "status": "completed"}),
            ({**base, "goal": {**base["goal"], "sourceKind": "autonomous"}}, {"session_id": "session-safe", "status": "completed"}),
            ({**base, "goal": {**base["goal"], "updatedAt": "2026-08-15T09:59:59Z"}}, {"session_id": "session-safe", "status": "completed"}),
            ({**base, "goal": {**base["goal"], "updatedAt": "2026-08-15T10:01:00"}}, {"session_id": "session-safe", "status": "completed"}),
            (base, {"session_id": "session-safe", "status": "failed"}),
            (base, {"session_id": "another-session", "status": "completed"}),
        ]
        for projection, run in cases:
            with self.subTest(goal=projection["goal"], run=run):
                with mock.patch.object(server, "_get_agent_run", return_value=run):
                    merged = server._merge_goal_v2_message_metadata(
                        "session-safe",
                        messages,
                        projection=projection,
                        existing_messages=[],
                    )
                self.assertNotIn("goalCompletion", merged[0].get("meta", {}))

    def test_goal_control_route_maps_invalid_conflict_and_corruption_without_session_damage(self):
        origin = {
            "id": "message-route-errors",
            "role": "user",
            "content": "/goal Route errors",
            "meta": {"goalOrigin": {
                "messageId": "message-route-errors",
                "clientRequestId": "request-route-errors",
            }},
        }
        session = self.create_session([origin])
        invalid = self.make_handler({"operation": "explicit_create", "snapshot": {}})
        server.CodeHandler.control_session_goal_v2(invalid, session["id"])
        self.assertEqual(invalid.send_json.call_args.args[1], 400)

        valid_body = {
            "operation": "explicit_create",
            "expectedRevision": 0,
            "idempotencyKey": "route-errors-02",
            "objective": "Test Goal v2 route conflicts",
            "messageId": "message-route-errors",
            "clientRequestId": "request-route-errors",
            "permissionProfile": "accept",
        }
        create = self.make_handler(valid_body)
        server.CodeHandler.control_session_goal_v2(create, session["id"])

        conflict = self.make_handler({**valid_body, "objective": "Different objective"})
        server.CodeHandler.control_session_goal_v2(conflict, session["id"])
        self.assertEqual(conflict.send_json.call_args.args[1], 409)

        with open(GoalV2Runtime(self.root).service.events_path(session["id"]), "ab") as handle:
            handle.write(b'{"partial"')
        degraded = self.make_handler(valid_body)
        server.CodeHandler.control_session_goal_v2(degraded, session["id"])
        self.assertEqual(degraded.send_json.call_args.args[1], 409)
        self.assertTrue(server.session_path(session["id"]).exists())

    def test_corrupt_goal_sidecar_does_not_break_session_read(self):
        messages = [{"role": "user", "content": "session remains readable"}]
        session = self.create_session(messages)
        self.create_goal(session["id"])
        with open(GoalV2Runtime(self.root).service.events_path(session["id"]), "a", encoding="utf-8") as handle:
            handle.write("{corrupt-middle}\n")

        handler = self.make_handler()
        server.CodeHandler.get_session(handler, session["id"])
        response = handler.send_json.call_args.args[0]
        self.assertEqual(response["messages"], messages)
        goal = GoalV2Runtime(self.root).read(session["id"])
        self.assertEqual(goal.health, "corrupted")
        self.assertFalse(goal.writable)

    def test_delete_session_removes_goal_sidecar(self):
        session = self.create_session()
        self.create_goal(session["id"])
        goal_path = GoalV2Runtime(self.root).service.events_path(session["id"])
        self.assertTrue(goal_path.exists())

        handler = self.make_handler()
        server.CodeHandler.delete_session(handler, session["id"])
        self.assertFalse(goal_path.exists())
        self.assertFalse(server.session_path(session["id"]).exists())

    def test_archive_copies_goal_sidecar_without_changing_source(self):
        messages = [{"role": "user", "content": "archive me"}]
        session = self.create_session(messages)
        self.create_goal(session["id"])
        source = GoalV2Runtime(self.root).service.events_path(session["id"])
        source_bytes = source.read_bytes()

        handler = self.make_handler({"messages": messages})
        server.CodeHandler.archive_session(handler, session["id"])
        archives = list((self.sessions_dir / "archive").glob(f"{session['id']}_*.goal-v2.jsonl"))
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
        child_goal = GoalV2Runtime(self.root).read(child["id"]).projection()
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
        imported_goal = GoalV2Runtime(self.root).read("imported01").projection()
        self.assertFalse(imported_goal["exists"])
        self.assertEqual(
            GoalV2Runtime(self.root).read(parent["id"]).projection()["goal"]["sourceKind"],
            "explicit",
        )


class TestSessionDeleteConsistency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.sessions_dir = self.root / "sessions"
        self.assets = server.GeneratedAssetRepository(self.root / "generated-assets")
        self.patch_sessions = mock.patch.object(server, "SESSIONS_DIR", self.sessions_dir)
        self.patch_data = mock.patch.object(server, "DATA_DIR", self.root)
        self.patch_assets = mock.patch.object(
            server,
            "_generated_asset_repository",
            self.assets,
        )
        self.patch_sessions.start()
        self.patch_data.start()
        self.patch_assets.start()
        self.addCleanup(self.patch_sessions.stop)
        self.addCleanup(self.patch_data.stop)
        self.addCleanup(self.patch_assets.stop)

    @staticmethod
    def make_handler(body=None, *, path=""):
        handler = object.__new__(server.CodeHandler)
        handler.path = path
        handler.read_body_json = mock.Mock(return_value=body or {})
        handler.send_json = mock.Mock()
        return handler

    def create_session(self, messages=None):
        handler = self.make_handler({
            "title": "Delete consistency",
            "messages": messages or [{"role": "user", "content": "keep consistent"}],
        })
        server.CodeHandler.create_session(handler)
        return handler.send_json.call_args.args[0]

    def create_goal(self, session_id):
        return GoalV2Runtime(self.root).create_goal(
            session_id,
            "Keep Session deletion consistent",
            context=GoalCreationContext(
                session_id=session_id,
                origin_message_id="message-delete-consistency",
                client_request_id="request-delete-consistency",
                owner_run_id="run-delete-consistency",
                permission_profile="read",
                source_kind="explicit",
            ),
            expected_revision=0,
            idempotency_key="create-delete-consistency-goal",
        )

    def create_asset(self, session_id, marker="a"):
        asset_id = "ga1_" + (str(marker)[:1] * 43)
        asset_dir = self.assets.root / asset_id
        asset_dir.mkdir(parents=True)
        (asset_dir / "content.png").write_bytes(b"not-read-by-delete")
        (asset_dir / "meta.json").write_text(json.dumps({
            "schema": "code-generated-asset/v1",
            "assetId": asset_id,
            "operationId": f"operation-delete-consistency-{marker}",
            "sessionId": session_id,
            "agentRunId": "run-delete-consistency",
            "toolCallId": "call-delete-consistency",
            "index": 0,
            "sha256": "0" * 64,
            "mimeType": "image/png",
            "width": 1,
            "height": 1,
            "byteLength": 18,
            "createdAt": "2026-08-28T00:00:00Z",
            "fileName": "content.png",
        }), encoding="utf-8")
        return asset_dir

    @unittest.skipUnless(os.name == "nt", "Windows file sharing semantics")
    def test_delete_file_lock_is_sanitized_and_rolls_back_all_session_state(self):
        session = self.create_session()
        session_id = session["id"]
        session_path = server.session_path(session_id)
        message_path = server.messages_path(session_id)
        goal_path = GoalV2Runtime(self.root).service.events_path(session_id)
        asset_dir = self.create_asset(session_id)
        self.create_goal(session_id)
        index_before = server._session_index_path().read_bytes()

        handler = self.make_handler(path=f"/api/sessions/{session_id}")
        with session_path.open("rb"):
            server.CodeHandler.do_DELETE(handler)

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload, {
            "error": "Session deletion could not be completed safely.",
            "errorCode": "session_delete_failed",
            "retryable": True,
        })
        self.assertTrue(session_path.exists())
        self.assertTrue(message_path.exists())
        self.assertTrue(goal_path.exists())
        self.assertTrue(asset_dir.exists())
        self.assertEqual(server._session_index_path().read_bytes(), index_before)

    def test_delete_snapshot_preparation_failure_is_sanitized_and_changes_nothing(self):
        session = self.create_session()
        session_id = session["id"]
        session_path = server.session_path(session_id)
        message_path = server.messages_path(session_id)
        self.create_goal(session_id)
        goal_path = GoalV2Runtime(self.root).service.events_path(session_id)
        asset_dir = self.create_asset(session_id)
        index_path = server._session_index_path()
        before = {
            "session": session_path.read_bytes(),
            "messages": message_path.read_bytes(),
            "index": index_path.read_bytes(),
            "goal": goal_path.read_bytes(),
            "assets": {
                path.relative_to(asset_dir).as_posix(): path.read_bytes()
                for path in asset_dir.rglob("*")
                if path.is_file()
            },
        }
        sentinel = str(self.root / "PREPARATION-SECRET-SENTINEL")
        original_snapshot = server._path_snapshot

        def fail_session_snapshot(path):
            if Path(path) == session_path:
                raise PermissionError(13, sentinel, str(session_path))
            return original_snapshot(path)

        handler = self.make_handler(path=f"/api/sessions/{session_id}")
        with mock.patch.object(server, "_path_snapshot", side_effect=fail_session_snapshot):
            server.CodeHandler.do_DELETE(handler)

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload, {
            "error": "Session deletion could not be completed safely.",
            "errorCode": "session_delete_failed",
            "retryable": True,
        })
        serialized = json.dumps(payload)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("PREPARATION-SECRET-SENTINEL", serialized)
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(message_path.read_bytes(), before["messages"])
        self.assertEqual(index_path.read_bytes(), before["index"])
        self.assertEqual(goal_path.read_bytes(), before["goal"])
        self.assertEqual({
            path.relative_to(asset_dir).as_posix(): path.read_bytes()
            for path in asset_dir.rglob("*")
            if path.is_file()
        }, before["assets"])

    def test_delete_removes_session_goal_owned_assets_and_index_idempotently(self):
        first = self.create_session()
        second = self.create_session()
        first_goal = GoalV2Runtime(self.root).service.events_path(first["id"])
        second_goal = GoalV2Runtime(self.root).service.events_path(second["id"])
        self.create_goal(first["id"])
        self.create_goal(second["id"])
        first_assets = [
            self.create_asset(first["id"], "a"),
            self.create_asset(first["id"], "b"),
        ]
        second_asset = self.create_asset(second["id"], "c")

        delete = self.make_handler()
        server.CodeHandler.delete_session(delete, first["id"])
        self.assertEqual(delete.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(server.session_path(first["id"]).exists())
        self.assertFalse(server.messages_path(first["id"]).exists())
        self.assertFalse(first_goal.exists())
        self.assertTrue(all(not path.exists() for path in first_assets))
        self.assertNotIn(first["id"], server._read_session_index())

        self.assertTrue(server.session_path(second["id"]).exists())
        self.assertTrue(server.messages_path(second["id"]).exists())
        self.assertTrue(second_goal.exists())
        self.assertTrue(second_asset.exists())
        self.assertIn(second["id"], server._read_session_index())

        repeated = self.make_handler()
        server.CodeHandler.delete_session(repeated, first["id"])
        self.assertEqual(repeated.send_json.call_args.args[0], {"ok": True})
        restarted_assets = server.GeneratedAssetRepository(self.assets.root)
        self.assertEqual(restarted_assets.snapshot_session_assets(first["id"]), [])
        self.assertFalse(GoalV2Runtime(self.root).read(first["id"]).exists)

    def test_index_failure_rolls_back_session_goal_assets_and_index(self):
        session = self.create_session()
        session_id = session["id"]
        session_path = server.session_path(session_id)
        message_path = server.messages_path(session_id)
        self.create_goal(session_id)
        goal_path = GoalV2Runtime(self.root).service.events_path(session_id)
        asset_dir = self.create_asset(session_id)
        index_before = server._session_index_path().read_bytes()

        handler = self.make_handler(path=f"/api/sessions/{session_id}")
        with mock.patch.object(
            server,
            "_remove_session_index_entry",
            side_effect=PermissionError(13, "Permission denied", "session-index.jsonl"),
        ):
            server.CodeHandler.do_DELETE(handler)

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_delete_failed")
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertTrue(session_path.exists())
        self.assertTrue(message_path.exists())
        self.assertTrue(goal_path.exists())
        self.assertTrue(asset_dir.exists())
        self.assertEqual(server._session_index_path().read_bytes(), index_before)

    def test_goal_failure_rolls_back_session_assets_and_index(self):
        session = self.create_session()
        session_id = session["id"]
        session_path = server.session_path(session_id)
        message_path = server.messages_path(session_id)
        self.create_goal(session_id)
        goal_path = GoalV2Runtime(self.root).service.events_path(session_id)
        asset_dir = self.create_asset(session_id)
        index_before = server._session_index_path().read_bytes()

        handler = self.make_handler(path=f"/api/sessions/{session_id}")
        with mock.patch(
            "goal_v2_store.GoalV2Service.delete_sidecar",
            side_effect=PermissionError(13, "Permission denied", "goal-sidecar.jsonl"),
        ):
            server.CodeHandler.do_DELETE(handler)

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_delete_failed")
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertTrue(session_path.exists())
        self.assertTrue(message_path.exists())
        self.assertTrue(goal_path.exists())
        self.assertTrue(asset_dir.exists())
        self.assertEqual(server._session_index_path().read_bytes(), index_before)

    def test_stale_save_after_delete_is_rejected_without_resurrection(self):
        session = self.create_session()
        session_id = session["id"]
        deleted = self.make_handler()
        server.CodeHandler.delete_session(deleted, session_id)

        stale = self.make_handler({
            "title": "stale save",
            "messages": [{"role": "user", "content": "must not return"}],
            "expectedRevision": session.get("revision", 0),
        })
        server.CodeHandler.save_session(stale, session_id)

        payload, status = stale.send_json.call_args.args
        self.assertEqual(status, 410)
        self.assertEqual(payload["errorCode"], "session_deleted")
        self.assertFalse(server.session_path(session_id).exists())
        self.assertFalse(server.messages_path(session_id).exists())
        self.assertNotIn(session_id, server._read_session_index())

    def test_concurrent_save_completes_before_delete_and_cannot_revive_session(self):
        session = self.create_session()
        session_id = session["id"]
        save_entered = threading.Event()
        release_save = threading.Event()
        original_write_jsonl = server.write_jsonl
        errors = []

        def blocked_write(path, messages):
            if Path(path) == server.messages_path(session_id):
                save_entered.set()
                if not release_save.wait(5):
                    raise AssertionError("save release was not signalled")
            return original_write_jsonl(path, messages)

        save = self.make_handler({
            "title": "concurrent save",
            "messages": [{"role": "user", "content": "saved before delete"}],
            "expectedRevision": session.get("revision", 0),
        })
        deleted = self.make_handler()

        def run_save():
            try:
                server.CodeHandler.save_session(save, session_id)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        def run_delete():
            try:
                server.CodeHandler.delete_session(deleted, session_id)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        with mock.patch.object(server, "write_jsonl", side_effect=blocked_write):
            save_thread = threading.Thread(target=run_save)
            delete_thread = threading.Thread(target=run_delete)
            save_thread.start()
            self.assertTrue(save_entered.wait(5))
            delete_thread.start()
            release_save.set()
            save_thread.join(timeout=5)
            delete_thread.join(timeout=5)

        self.assertFalse(save_thread.is_alive())
        self.assertFalse(delete_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(save.send_json.call_args.args[0]["revision"], 1)
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(server.session_path(session_id).exists())
        self.assertFalse(server.messages_path(session_id).exists())
        self.assertNotIn(session_id, server._read_session_index())

if __name__ == "__main__":
    unittest.main()
