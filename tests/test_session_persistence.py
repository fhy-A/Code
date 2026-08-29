import json
import hashlib
import http.client
import os
import shutil
import tempfile
import threading
import time
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


class TestSessionArchiveLifecycle(unittest.TestCase):
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
        self.patch_location = mock.patch.object(
            server,
            "_session_location",
            return_value=(None, ""),
        )
        self.patch_sessions.start()
        self.patch_data.start()
        self.patch_assets.start()
        self.patch_location.start()
        self.addCleanup(self.patch_sessions.stop)
        self.addCleanup(self.patch_data.stop)
        self.addCleanup(self.patch_assets.stop)
        self.addCleanup(self.patch_location.stop)
        with server._agent_run_lock:
            self.saved_agent_runs = dict(server._agent_runs)
            server._agent_runs.clear()
        server._rebuild_agent_run_nonterminal_index(force=True)
        if hasattr(server, "_rebuild_agent_run_session_index"):
            server._rebuild_agent_run_session_index(force=True)
        self.addCleanup(self.restore_agent_runs)

    def restore_agent_runs(self):
        with server._agent_run_lock:
            server._agent_runs.clear()
            server._agent_runs.update(self.saved_agent_runs)

    @staticmethod
    def make_handler(body=None, *, path=""):
        handler = object.__new__(server.CodeHandler)
        handler.path = path
        handler.read_body_json = mock.Mock(return_value=body or {})
        handler.send_json = mock.Mock()
        handler.send_error = mock.Mock()
        return handler

    def create_session(self, *, title="Archive lifecycle", run_state=None, messages=None):
        handler = self.make_handler({
            "title": title,
            "messages": messages or [{
                "role": "user",
                "content": "archive fixture",
                "_time": "2026-08-28T12:00:00Z",
            }],
            "runState": run_state or {},
        })
        server.CodeHandler.create_session(handler)
        return handler.send_json.call_args.args[0]

    def archive(self, session_id):
        handler = self.make_handler()
        server.CodeHandler.archive_session_lifecycle(handler, session_id)
        return handler

    def unarchive(self, session_id):
        handler = self.make_handler()
        server.CodeHandler.unarchive_session_lifecycle(handler, session_id)
        return handler

    def archive_summary(self):
        handler = self.make_handler()
        server.CodeHandler.get_archived_sessions(handler)
        return handler.send_json.call_args.args[0]["data"]

    def create_asset_sidecar(self, session_id, marker="a"):
        asset_id = "ga1_" + (str(marker)[:1] * 43)
        asset_dir = self.assets.root / asset_id
        asset_dir.mkdir(parents=True)
        content = b"archive-lifecycle-asset"
        (asset_dir / "content.png").write_bytes(content)
        (asset_dir / "meta.json").write_text(json.dumps({
            "schema": "code-generated-asset/v1",
            "assetId": asset_id,
            "operationId": f"archive-lifecycle-{marker}",
            "sessionId": session_id,
            "agentRunId": "run-archive-lifecycle",
            "toolCallId": "call-archive-lifecycle",
            "index": 0,
            "sha256": hashlib.sha256(content).hexdigest(),
            "mimeType": "image/png",
            "width": 1,
            "height": 1,
            "byteLength": len(content),
            "createdAt": "2026-08-28T12:00:00Z",
            "fileName": "content.png",
        }), encoding="utf-8")
        return asset_dir

    def create_terminal_goal(self, session_id):
        runtime = GoalV2Runtime(self.root)
        created = runtime.create_goal(
            session_id,
            "Archived terminal Goal",
            context=GoalCreationContext(
                session_id=session_id,
                origin_message_id="message-archive-terminal",
                client_request_id="request-archive-terminal",
                owner_run_id="run-archive-terminal",
                permission_profile="read",
                source_kind="explicit",
            ),
            expected_revision=0,
            idempotency_key=f"create-terminal-{session_id}",
        )
        goal = created["goal"]
        runtime.cancel_goal(
            session_id,
            goal["goalId"],
            reason="terminal fixture",
            source_run_id="run-archive-terminal",
            expected_revision=created["revision"],
            idempotency_key=f"cancel-terminal-{session_id}",
        )
        return runtime.service.events_path(session_id)

    def create_terminal_agent_run(self, session_id, marker="a"):
        run_id = hashlib.sha256(
            f"archive-terminal-run\0{session_id}\0{marker}".encode("utf-8")
        ).hexdigest()[:32]
        run = {
            "version": 5,
            "id": run_id,
            "sessionId": session_id,
            "session_id": session_id,
            "status": "completed",
        }
        path = self.root / "agent-runs" / f"{run_id}.json"
        index_added = server._agent_run_session_index_register(run_id, session_id)
        try:
            server.write_json(path, run)
            with server._agent_run_lock:
                server._agent_runs[run_id] = dict(run)
        except Exception:
            if index_added:
                server._agent_run_session_index_unregister_run(run_id)
            raise
        return run_id, path

    def test_preexisting_unowned_archive_directory_is_ignored_without_mutation(self):
        active = self.create_session(title="Legacy backup compatibility")
        legacy = self.root / "session-archive" / "latency-test-20260731-040804"
        legacy.mkdir(parents=True)
        sentinel = legacy / "opaque-backup.bin"
        sentinel.write_bytes(b"PRE-CODE009-LEGACY-BACKUP-SENTINEL")
        metadata_before = {
            "bytes": sentinel.read_bytes(),
            "mtime": sentinel.stat().st_mtime_ns,
            "entries": sorted(path.name for path in legacy.iterdir()),
        }

        active_handler = self.make_handler()
        server.CodeHandler.get_sessions(active_handler)
        archive_handler = self.make_handler()
        server.CodeHandler.get_archived_sessions(archive_handler)

        self.assertEqual(active_handler.send_json.call_args.args[0]["data"][0]["id"], active["id"])
        self.assertEqual(archive_handler.send_json.call_args.args[0], {"data": []})
        self.assertEqual(active_handler.send_json.call_args.args[1:] or (200,), (200,))
        self.assertEqual(archive_handler.send_json.call_args.args[1:] or (200,), (200,))
        self.assertEqual(sentinel.read_bytes(), metadata_before["bytes"])
        self.assertEqual(sentinel.stat().st_mtime_ns, metadata_before["mtime"])
        self.assertEqual(sorted(path.name for path in legacy.iterdir()), metadata_before["entries"])

    def test_new_archives_use_owned_versioned_namespace(self):
        session = self.create_session(title="Managed namespace")
        archived = self.archive(session["id"])
        self.assertEqual(archived.send_json.call_args.args[0]["status"], "archived")
        bundle = server._session_archive_bundle_path(session["id"])
        self.assertEqual(
            bundle.parent,
            self.root / "session-archive" / server._SESSION_ARCHIVE_NAMESPACE_NAME,
        )
        self.assertTrue(bundle.is_dir())
        self.assertEqual(
            server.read_json(server._session_archive_managed_marker_path(), {}),
            {"schema": server._SESSION_ARCHIVE_NAMESPACE_SCHEMA},
        )
        self.assertFalse((self.root / "session-archive" / session["id"]).exists())

    def test_valid_root_v1_bundle_restores_rearchives_and_deletes_after_restart(self):
        session = self.create_session(title="Root v1 compatibility")
        session_id = session["id"]
        goal_path = self.create_terminal_goal(session_id)
        asset_path = self.create_asset_sidecar(session_id, "r")
        _, run_path = self.create_terminal_agent_run(session_id, "r")
        first = self.archive(session_id).send_json.call_args.args[0]
        managed_bundle = server._session_archive_bundle_path(session_id)
        root_bundle = self.root / "session-archive" / session_id
        shutil.move(str(managed_bundle), str(root_bundle))

        server._recover_all_session_archive_transactions()
        self.assertEqual(server._session_archive_bundle_path(session_id), root_bundle)
        summaries = self.archive_summary()
        self.assertEqual([item["id"] for item in summaries], [session_id])
        self.assertEqual(summaries[0]["archiveToken"], first["archiveToken"])

        restored = self.unarchive(session_id)
        self.assertEqual(restored.send_json.call_args.args[0], {"ok": True, "status": "active"})
        self.assertFalse(root_bundle.exists())
        self.assertTrue(server.session_path(session_id).exists())
        self.assertTrue(server.messages_path(session_id).exists())
        self.assertTrue(goal_path.exists())
        self.assertTrue(asset_path.exists())
        self.assertTrue(run_path.exists())

        second = self.archive(session_id).send_json.call_args.args[0]
        self.assertNotEqual(second["archiveToken"], first["archiveToken"])
        self.assertEqual(
            server._session_archive_bundle_path(session_id).parent,
            server._session_archive_managed_root(),
        )
        server._recover_all_session_archive_transactions()
        deleted = self.make_handler()
        server.CodeHandler.delete_archived_session(
            deleted,
            session_id,
            second["archiveToken"],
        )
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(server._session_archive_bundle_path(session_id).exists())
        self.assertFalse(goal_path.exists())
        self.assertFalse(asset_path.exists())
        self.assertFalse(run_path.exists())

    def test_owned_namespace_corruption_fails_closed_but_unmarked_peer_is_ignored(self):
        active = self.create_session(title="Owned corruption")
        server._ensure_session_archive_managed_root()
        corrupt_id = "ownedcorrupt01"
        corrupt = server._session_archive_managed_bundle_path(corrupt_id)
        corrupt.mkdir()
        (corrupt / "session.json").write_text("{}", encoding="utf-8")
        unowned = self.root / "session-archive" / "external-backup"
        unowned.mkdir()
        (unowned / "manifest.backup").write_bytes(b"opaque")

        handler = self.make_handler()
        server.CodeHandler.get_sessions(handler)
        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(payload["errorCode"], "session_archive_recovery_failed")
        self.assertTrue(server.session_path(active["id"]).exists())
        self.assertEqual((unowned / "manifest.backup").read_bytes(), b"opaque")

    def test_tampered_root_manifest_is_owned_and_fails_closed(self):
        corrupt_id = "rootcorrupt01"
        corrupt = self.root / "session-archive" / corrupt_id
        corrupt.mkdir(parents=True)
        (corrupt / "manifest.json").write_text('{"schema":"unexpected"}', encoding="utf-8")
        handler = self.make_handler()
        server.CodeHandler.get_archived_sessions(handler)
        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(payload["errorCode"], "session_archive_recovery_failed")
        self.assertTrue((corrupt / "manifest.json").exists())

    def test_root_and_managed_v1_for_same_session_fail_closed(self):
        session = self.create_session(title="Duplicate namespace")
        session_id = session["id"]
        self.archive(session_id)
        managed = server._session_archive_bundle_path(session_id)
        root_bundle = self.root / "session-archive" / session_id
        shutil.copytree(managed, root_bundle)

        active_handler = self.make_handler()
        server.CodeHandler.get_sessions(active_handler)
        payload, status = active_handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_archive_location_conflict")
        archive_handler = self.make_handler()
        server.CodeHandler.get_archived_sessions(archive_handler)
        payload, status = archive_handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_archive_location_conflict")

    def test_root_v1_journal_and_staging_recovery_remain_compatible(self):
        session = self.create_session(title="Root transaction compatibility")
        session_id = session["id"]
        self.archive(session_id)
        managed_bundle = server._session_archive_bundle_path(session_id)
        root_bundle = self.root / "session-archive" / session_id
        shutil.move(str(managed_bundle), str(root_bundle))
        transaction_id = "e" * 32
        legacy_journal = server._session_archive_legacy_journal_path(session_id)
        server.write_json(legacy_journal, {
            "schema": "code-session-archive-transaction/v1",
            "sessionId": session_id,
            "action": "archive",
            "state": "bundle_committed",
            "transactionId": transaction_id,
        })
        orphan_id = "legacystaging01"
        legacy_staging = server._session_archive_legacy_staging_path(
            orphan_id,
            transaction_id,
        )
        legacy_staging.mkdir(parents=True)
        (legacy_staging / "opaque.tmp").write_bytes(b"owned-old-staging")

        server._recover_all_session_archive_transactions()

        self.assertFalse(legacy_journal.exists())
        self.assertTrue(root_bundle.exists())
        self.assertFalse(legacy_staging.exists())
        self.assertEqual(self.archive_summary()[0]["id"], session_id)

    def test_archive_unarchive_lists_are_idempotent_secret_free_and_non_destructive(self):
        secret = "ARCHIVE-SECRET-SENTINEL"
        archived = self.create_session(
            title="Archived fixture",
            run_state={"status": "completed", "secret": secret},
        )
        active = self.create_session(title="Active fixture")
        active_meta_path = server.session_path(archived["id"])
        active_messages_path = server.messages_path(archived["id"])
        meta_before = active_meta_path.read_bytes()
        messages_before = active_messages_path.read_bytes()
        goal_path = self.create_terminal_goal(archived["id"])
        goal_before = goal_path.read_bytes()
        asset_dir = self.create_asset_sidecar(archived["id"])
        asset_before = {
            path.name: path.read_bytes()
            for path in asset_dir.iterdir()
            if path.is_file()
        }

        first = self.archive(archived["id"])
        payload = first.send_json.call_args.args[0]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "archived")
        self.assertRegex(payload["archiveToken"], r"^[0-9a-f]{32}$")
        self.assertTrue(payload["archivedAt"].endswith("Z"))
        token = payload["archiveToken"]
        archived_at = payload["archivedAt"]
        bundle = server._session_archive_bundle_path(archived["id"])
        self.assertFalse(active_meta_path.exists())
        self.assertFalse(active_messages_path.exists())
        self.assertEqual((bundle / "session.json").read_bytes(), meta_before)
        self.assertEqual((bundle / "messages.jsonl").read_bytes(), messages_before)
        manifest_after_first = (bundle / "manifest.json").read_bytes()
        index_after_first = server._session_index_path().read_bytes()

        repeated = self.archive(archived["id"])
        repeated_payload = repeated.send_json.call_args.args[0]
        self.assertEqual(repeated_payload["archiveToken"], token)
        self.assertEqual(repeated_payload["archivedAt"], archived_at)
        self.assertEqual((bundle / "manifest.json").read_bytes(), manifest_after_first)
        self.assertEqual(server._session_index_path().read_bytes(), index_after_first)

        active_list = self.make_handler()
        server.CodeHandler.get_sessions(active_list)
        active_ids = [item["id"] for item in active_list.send_json.call_args.args[0]["data"]]
        self.assertEqual(active_ids, [active["id"]])

        summaries = self.archive_summary()
        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(set(summary), {
            "id", "title", "projectId", "source", "createdAt", "updatedAt",
            "lastMessageTime", "archivedAt", "archiveToken",
        })
        self.assertEqual(summary["id"], archived["id"])
        self.assertEqual(summary["archiveToken"], token)
        self.assertNotIn(secret, json.dumps(summary))
        self.assertNotIn("runState", summary)
        self.assertNotIn("messages", summary)
        self.assertNotIn("cwd", summary)
        self.assertEqual((bundle / "messages.jsonl").read_bytes(), messages_before)
        self.assertEqual(goal_path.read_bytes(), goal_before)
        self.assertEqual({
            path.name: path.read_bytes()
            for path in asset_dir.iterdir()
            if path.is_file()
        }, asset_before)

        restored = self.unarchive(archived["id"])
        self.assertEqual(restored.send_json.call_args.args[0], {
            "ok": True,
            "status": "active",
        })
        self.assertEqual(active_meta_path.read_bytes(), meta_before)
        self.assertEqual(active_messages_path.read_bytes(), messages_before)
        self.assertFalse(bundle.exists())
        meta_after_restore = server.session_path(archived["id"]).read_bytes()
        index_after_restore = server._session_index_path().read_bytes()
        repeated_restore = self.unarchive(archived["id"])
        self.assertEqual(repeated_restore.send_json.call_args.args[0], {
            "ok": True,
            "status": "active",
        })
        self.assertEqual(server.session_path(archived["id"]).read_bytes(), meta_after_restore)
        self.assertEqual(server._session_index_path().read_bytes(), index_after_restore)
        self.assertEqual(self.archive_summary(), [])

    def test_manifest_paths_identity_and_integrity_fail_closed(self):
        session = self.create_session(title="Manifest binding")
        other = self.create_session(title="Manifest sibling")
        self.archive(session["id"])
        bundle = server._session_archive_bundle_path(session["id"])
        manifest_path = bundle / "manifest.json"
        original_manifest = manifest_path.read_bytes()
        sibling_before = server.session_path(other["id"]).read_bytes()
        sentinel = "MANIFEST-PATH-SECRET"
        tamper_cases = (
            ("other-session", lambda manifest: manifest["original"].__setitem__(
                "session", server._session_archive_relative_path(server.session_path(other["id"]))
            )),
            ("staging-traversal", lambda manifest: manifest["original"].__setitem__(
                "messages", f"sessions/../session-archive/{sentinel}.jsonl"
            )),
            ("wrong-identity", lambda manifest: manifest.__setitem__("sessionId", other["id"])),
        )
        for label, mutate in tamper_cases:
            with self.subTest(label=label):
                manifest = json.loads(original_manifest)
                mutate(manifest)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                failed = self.unarchive(session["id"])
                payload, status = failed.send_json.call_args.args
                self.assertEqual(status, 500)
                self.assertEqual(payload["errorCode"], "session_archive_recovery_failed")
                self.assertNotIn(sentinel, json.dumps(payload))
                self.assertEqual(server.session_path(other["id"]).read_bytes(), sibling_before)
                self.assertFalse(server.session_path(session["id"]).exists())
                manifest_path.write_bytes(original_manifest)

        archived_messages_path = bundle / "messages.jsonl"
        archived_messages_before = archived_messages_path.read_bytes()
        archived_messages_path.write_bytes(b"CORRUPT-ARCHIVE-CONTENT")
        failed = self.unarchive(session["id"])
        self.assertEqual(failed.send_json.call_args.args[1], 500)
        self.assertEqual(
            failed.send_json.call_args.args[0]["errorCode"],
            "session_archive_recovery_failed",
        )
        self.assertFalse(server.session_path(session["id"]).exists())
        archived_messages_path.write_bytes(archived_messages_before)

        archived_meta_path = bundle / "session.json"
        archived_meta_before = archived_meta_path.read_bytes()
        wrong_meta = json.loads(archived_meta_before)
        wrong_meta["id"] = other["id"]
        archived_meta_path.write_text(json.dumps(wrong_meta), encoding="utf-8")
        manifest = json.loads(original_manifest)
        meta_bytes = archived_meta_path.read_bytes()
        manifest["files"]["session.json"] = server._session_archive_file_fact(
            meta_bytes,
            mtime_ns=manifest["files"]["session.json"]["mtimeNs"],
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        failed = self.unarchive(session["id"])
        self.assertEqual(failed.send_json.call_args.args[1], 500)
        self.assertEqual(
            failed.send_json.call_args.args[0]["errorCode"],
            "session_archive_recovery_failed",
        )
        self.assertEqual(server.session_path(other["id"]).read_bytes(), sibling_before)

    def test_journal_identity_state_and_staging_are_strictly_bounded(self):
        session = self.create_session(title="Journal binding")
        session_id = session["id"]
        active_before = server.session_path(session_id).read_bytes()
        journal_path = server._session_archive_journal_path(session_id)
        transaction_id = "a" * 32
        staging = server._session_archive_staging_path(session_id, transaction_id)
        staging.mkdir(parents=True)
        (staging / "sentinel.txt").write_text("bounded", encoding="utf-8")
        sibling = server._session_archive_root() / "sibling-archive"
        sibling.mkdir(parents=True)
        (sibling / "keep.txt").write_text("keep", encoding="utf-8")

        invalid_journals = (
            {"schema": "code-session-archive-transaction/v1", "sessionId": session_id,
             "action": "archive", "state": "prepared", "transactionId": "../sibling-archive"},
            {"schema": "code-session-archive-transaction/v1", "sessionId": "z" * 16,
             "action": "archive", "state": "prepared", "transactionId": transaction_id},
            {"schema": "code-session-archive-transaction/v1", "sessionId": session_id,
             "action": "archive", "state": "unknown", "transactionId": transaction_id},
        )
        for journal in invalid_journals:
            with self.subTest(journal=journal):
                server.write_json(journal_path, journal)
                with self.assertRaises(server.SessionArchiveMutationError) as raised:
                    server._recover_session_archive_transaction(session_id)
                self.assertTrue(raised.exception.recovery_failed)
                self.assertTrue(staging.exists())
                self.assertTrue((sibling / "keep.txt").exists())
                self.assertEqual(server.session_path(session_id).read_bytes(), active_before)
        journal_path.unlink()

    def test_legacy_flat_metadata_with_dated_messages_archives_and_restores(self):
        session_id = "legacyflat01"
        flat_meta = self.sessions_dir / f"{session_id}.json"
        meta = {
            "id": session_id,
            "title": "Legacy flat",
            "messageCount": 1,
            "runState": {},
        }
        server.write_json(flat_meta, meta)
        dated_messages = server.messages_path(session_id)
        server.write_jsonl(dated_messages, [{"role": "user", "content": "legacy"}])
        server._write_session_index_from_meta(meta)
        meta_before = flat_meta.read_bytes()
        messages_before = dated_messages.read_bytes()

        archived = self.archive(session_id)
        self.assertEqual(archived.send_json.call_args.args[0]["status"], "archived")
        self.assertFalse(flat_meta.exists())
        self.assertFalse(dated_messages.exists())
        with server._agent_run_lock:
            server._agent_runs.clear()
        self.assertEqual(self.archive_summary()[0]["id"], session_id)
        restored = self.unarchive(session_id)
        self.assertEqual(restored.send_json.call_args.args[0]["status"], "active")
        self.assertEqual(flat_meta.read_bytes(), meta_before)
        self.assertEqual(dated_messages.read_bytes(), messages_before)
        self.assertEqual(server.messages_path(session_id), dated_messages)
        token = self.archive(session_id).send_json.call_args.args[0]["archiveToken"]
        deleted = self.make_handler()
        server.CodeHandler.delete_archived_session(deleted, session_id, token)
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(flat_meta.exists())
        self.assertFalse(dated_messages.exists())

    def test_legacy_index_without_lifecycle_fields_and_restart_projection_are_safe(self):
        legacy_active = self.create_session(title="Legacy active")
        recovered_archive = self.create_session(title="Recovered archive")

        index = server._read_session_index()
        for entry in index.values():
            entry.pop("archivedAt", None)
            entry.pop("archiveToken", None)
        entries = list(index.values())
        server._write_session_index_payload("\n".join(
            json.dumps(entry, ensure_ascii=False) for entry in entries
        ) + "\n")

        listed = self.make_handler()
        server.CodeHandler.get_sessions(listed)
        self.assertEqual(
            {item["id"] for item in listed.send_json.call_args.args[0]["data"]},
            {legacy_active["id"], recovered_archive["id"]},
        )
        rebuilt_index = server._read_session_index()
        self.assertNotIn("archivedAt", rebuilt_index[legacy_active["id"]])
        self.assertNotIn("archiveToken", rebuilt_index[legacy_active["id"]])
        self.assertNotIn("archiveToken", rebuilt_index[recovered_archive["id"]])

        recovered_token = self.archive(recovered_archive["id"]).send_json.call_args.args[0]["archiveToken"]

        # A process restart has no in-memory archive dependency.
        with server._agent_run_lock:
            server._agent_runs.clear()
        summaries = self.archive_summary()
        self.assertEqual([item["id"] for item in summaries], [recovered_archive["id"]])
        self.assertEqual(summaries[0]["archiveToken"], recovered_token)

    def test_archive_state_survives_session_writers_import_and_index_rebuild(self):
        session = self.create_session(
            title="Preserved archive",
            messages=[{"role": "user", "content": "imported"}],
        )
        session_id = session["id"]
        archive_payload = self.archive(session_id).send_json.call_args.args[0]
        bundle = server._session_archive_bundle_path(session_id)
        bundle_before = {
            path.name: path.read_bytes()
            for path in bundle.iterdir()
            if path.is_file()
        }

        saved = self.make_handler({
            "title": "Renamed while archived",
            "runState": {"status": "completed"},
        })
        server.CodeHandler.save_session(saved, session_id)
        appended = self.make_handler({
            "messages": [{"role": "assistant", "content": "preserved"}],
        })
        server.CodeHandler.append_messages(appended, session_id)
        with mock.patch.object(server, "_session_location", return_value=("project-archive", "")):
            assigned = self.make_handler({"projectId": "project-archive"})
            server.CodeHandler.assign_session_project(assigned, session_id)
        branched = self.make_handler({"title": "Branch from archived"})
        server.CodeHandler.branch_session(branched, session_id)
        for handler in (saved, appended, assigned, branched):
            payload, status = handler.send_json.call_args.args
            self.assertEqual(status, 409)
            self.assertEqual(payload["errorCode"], "session_archived")

        source_path = self.root / "import-source.jsonl"
        source_path.write_text('{"type":"message"}\n', encoding="utf-8")
        with self.assertRaises(server.SessionLifecycleConflictError) as raised:
            server._persist_import_snapshot(
                source="codex",
                source_path=source_path,
                source_session_id="source-archive-lifecycle",
                requested_session_id=session_id,
                force_requested_id=True,
                title="Imported archive",
                created_at="2026-08-28T12:00:00Z",
                messages=[],
                stats={},
                last_usage={},
                resolved_project_id="project-archive",
                resolved_cwd="",
            )
        self.assertEqual(raised.exception.error_code, "session_archived")
        self.assertEqual({
            path.name: path.read_bytes()
            for path in bundle.iterdir()
            if path.is_file()
        }, bundle_before)

        server._session_index_path().unlink()
        server._rebuild_index_if_needed()
        self.assertNotIn(session_id, server._read_session_index())
        listed = self.archive_summary()
        self.assertEqual([item["id"] for item in listed], [session_id])

    def test_archived_session_all_active_read_write_and_goal_entrypoints_fail_closed(self):
        session = self.create_session(title="Archived API guards")
        session_id = session["id"]
        self.archive(session_id)
        bundle = server._session_archive_bundle_path(session_id)
        before = {
            path.name: path.read_bytes()
            for path in bundle.iterdir()
            if path.is_file()
        }
        handlers = []

        opened = self.make_handler()
        server.CodeHandler.get_session(opened, session_id)
        handlers.append(opened)
        goal_read = self.make_handler()
        server.CodeHandler.get_session_goal_v2(goal_read, session_id)
        handlers.append(goal_read)
        goal_control = self.make_handler({"action": "cancel"})
        server.CodeHandler.control_session_goal_v2(goal_control, session_id)
        handlers.append(goal_control)
        saved = self.make_handler({"title": "blocked"})
        server.CodeHandler.save_session(saved, session_id)
        handlers.append(saved)
        appended = self.make_handler({"messages": [{"role": "user", "content": "blocked"}]})
        server.CodeHandler.append_messages(appended, session_id)
        handlers.append(appended)
        assigned = self.make_handler({"projectId": "blocked"})
        server.CodeHandler.assign_session_project(assigned, session_id)
        handlers.append(assigned)
        branched = self.make_handler({"title": "blocked"})
        server.CodeHandler.branch_session(branched, session_id)
        handlers.append(branched)

        for handler in handlers:
            payload, status = handler.send_json.call_args.args
            self.assertEqual(status, 409)
            self.assertEqual(payload["errorCode"], "session_archived")
        self.assertEqual({
            path.name: path.read_bytes()
            for path in bundle.iterdir()
            if path.is_file()
        }, before)

    def test_archive_restore_leave_branch_goal_asset_and_message_facts_unchanged(self):
        parent = self.create_session(title="Archive tree")
        child_handler = self.make_handler({"title": "Archive child"})
        server.CodeHandler.branch_session(child_handler, parent["id"])
        child = child_handler.send_json.call_args.args[0]
        goal_path = self.create_terminal_goal(parent["id"])
        asset_dir = self.create_asset_sidecar(parent["id"], "t")
        _, run_path = self.create_terminal_agent_run(parent["id"], "t")
        parent_messages = server.messages_path(parent["id"])
        child_meta = server.session_path(child["id"])
        child_messages = server.messages_path(child["id"])
        before = {
            "parentMessages": parent_messages.read_bytes(),
            "childMeta": child_meta.read_bytes(),
            "childMessages": child_messages.read_bytes(),
            "goal": goal_path.read_bytes(),
            "agentRun": run_path.read_bytes(),
            "assets": {
                path.name: path.read_bytes()
                for path in asset_dir.iterdir()
                if path.is_file()
            },
            "branches": server.read_json(server.session_path(parent["id"]), {})["_branches"],
        }

        self.archive(parent["id"])
        self.unarchive(parent["id"])

        self.assertEqual(parent_messages.read_bytes(), before["parentMessages"])
        self.assertEqual(child_meta.read_bytes(), before["childMeta"])
        self.assertEqual(child_messages.read_bytes(), before["childMessages"])
        self.assertEqual(goal_path.read_bytes(), before["goal"])
        self.assertEqual(run_path.read_bytes(), before["agentRun"])
        self.assertEqual({
            path.name: path.read_bytes()
            for path in asset_dir.iterdir()
            if path.is_file()
        }, before["assets"])
        self.assertEqual(
            server.read_json(server.session_path(parent["id"]), {})["_branches"],
            before["branches"],
        )

    def test_archive_rejects_nonterminal_session_goal_and_agent_run_facts(self):
        run_state_cases = [
            {"status": "running"},
            {"status": "waiting-network"},
            {"queuedMessages": [{"id": "queued-1", "status": "pending"}]},
            {"backgroundRuns": [{"id": "background-1", "status": "waiting-recovery"}]},
            {"authorizationRequest": {"status": "pending", "reason": "secret"}},
        ]
        for index, run_state in enumerate(run_state_cases):
            with self.subTest(run_state=run_state):
                session = self.create_session(
                    title=f"Nonterminal {index}",
                    run_state=run_state,
                )
                before_meta = server.session_path(session["id"]).read_bytes()
                before_index = server._session_index_path().read_bytes()
                rejected = self.archive(session["id"])
                payload, status = rejected.send_json.call_args.args
                self.assertEqual(status, 409)
                self.assertEqual(payload["errorCode"], "session_archive_not_terminal")
                self.assertEqual(server.session_path(session["id"]).read_bytes(), before_meta)
                self.assertEqual(server._session_index_path().read_bytes(), before_index)

        goal_session = self.create_session(title="Active Goal")
        GoalV2Runtime(self.root).create_goal(
            goal_session["id"],
            "Archive must wait for Goal completion",
            context=GoalCreationContext(
                session_id=goal_session["id"],
                origin_message_id="message-archive-lifecycle",
                client_request_id="request-archive-lifecycle",
                owner_run_id="run-archive-lifecycle",
                permission_profile="read",
                source_kind="explicit",
            ),
            expected_revision=0,
            idempotency_key="create-archive-lifecycle-goal",
        )
        rejected_goal = self.archive(goal_session["id"])
        self.assertEqual(rejected_goal.send_json.call_args.args[1], 409)
        self.assertEqual(
            rejected_goal.send_json.call_args.args[0]["errorCode"],
            "session_archive_not_terminal",
        )

        run_session = self.create_session(title="Persisted AgentRun")
        runs_dir = self.root / "agent-runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        server.write_json(runs_dir / ("a" * 32 + ".json"), {
            "version": 5,
            "id": "a" * 32,
            "sessionId": run_session["id"],
            "status": "waiting_recovery",
        })
        server._agent_run_nonterminal_index_register("a" * 32, run_session["id"])
        rejected_run = self.archive(run_session["id"])
        self.assertEqual(rejected_run.send_json.call_args.args[1], 409)
        self.assertEqual(
            rejected_run.send_json.call_args.args[0]["errorCode"],
            "session_archive_not_terminal",
        )

    def test_archive_eligibility_does_not_read_unrelated_agent_run_history(self):
        target = self.create_session(title="Indexed archive target")
        runs_dir = self.root / "agent-runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        for index in range(1001):
            run_id = f"{index:032x}"
            server.write_json(runs_dir / f"{run_id}.json", {
                "version": 5,
                "id": run_id,
                "sessionId": "unrelated-session",
                "status": "completed",
            })
        rebuild = getattr(server, "_rebuild_agent_run_nonterminal_index", None)
        if callable(rebuild):
            rebuild()

        original_read_text = Path.read_text
        unrelated_reads = []

        def tracked_read_text(path, *args, **kwargs):
            resolved = Path(path)
            if resolved.parent == runs_dir and resolved.suffix == ".json":
                unrelated_reads.append(resolved.name)
            return original_read_text(path, *args, **kwargs)

        started = time.monotonic()
        with mock.patch.object(Path, "read_text", tracked_read_text):
            archived = self.archive(target["id"])
        elapsed = time.monotonic() - started

        self.assertEqual(archived.send_json.call_args.args[0]["status"], "archived")
        self.assertEqual(unrelated_reads, [])
        self.assertLess(elapsed, 1.0)

    def test_agent_run_index_legacy_build_is_secret_free_and_idempotent(self):
        runs_dir = self.root / "agent-runs"
        secret = "AGENT-INDEX-SECRET-SENTINEL"
        nonterminal_id = "b" * 32
        terminal_id = "c" * 32
        server.write_json(runs_dir / f"{nonterminal_id}.json", {
            "version": 5,
            "id": nonterminal_id,
            "sessionId": "legacy-index-session",
            "status": "waiting_authorization",
            "messages": [{"role": "user", "content": secret}],
            "request": {"url": f"https://example.invalid/?token={secret}"},
        })
        server.write_json(runs_dir / f"{terminal_id}.json", {
            "version": 5,
            "id": terminal_id,
            "sessionId": "terminal-index-session",
            "status": "completed",
            "result": {"secret": secret},
        })
        shutil.rmtree(server._agent_run_nonterminal_index_dir())

        first = server._rebuild_agent_run_nonterminal_index(force=False)
        first_bytes = server._agent_run_nonterminal_index_path().read_bytes()
        second = server._rebuild_agent_run_nonterminal_index(force=False)

        self.assertEqual(first["entries"], {nonterminal_id: "legacy-index-session"})
        self.assertEqual(second["entries"], first["entries"])
        self.assertEqual(server._agent_run_nonterminal_index_path().read_bytes(), first_bytes)
        self.assertNotIn(secret.encode("utf-8"), first_bytes)
        self.assertEqual(
            set(json.loads(first_bytes)["entries"][0]),
            {"runId", "sessionId"},
        )

    def test_agent_run_index_unavailable_is_safe_and_rebuild_recovers(self):
        session = self.create_session(title="Index recovery")
        index_path = server._agent_run_nonterminal_index_path()
        shutil.rmtree(index_path.parent)
        with mock.patch.object(
            server, "_start_agent_run_nonterminal_index_build", return_value=None,
        ):
            missing = self.archive(session["id"])
        payload, status = missing.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_archive_index_unavailable")

        index_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel = "CORRUPT-INDEX-SECRET-SENTINEL"
        index_path.write_text('{"schema":"wrong","secret":"' + sentinel + '"}', encoding="utf-8")
        with mock.patch.object(
            server, "_start_agent_run_nonterminal_index_build", return_value=None,
        ):
            corrupt = self.archive(session["id"])
        payload, status = corrupt.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_archive_index_unavailable")
        self.assertNotIn(sentinel, json.dumps(payload))

        server._rebuild_agent_run_nonterminal_index(force=True)
        recovered = self.archive(session["id"])
        self.assertEqual(recovered.send_json.call_args.args[0]["status"], "archived")

    def test_agent_run_index_crash_windows_never_replay_or_underblock(self):
        missing_session = self.create_session(title="Prepared index fact")
        missing_run_id = "d" * 32
        server._agent_run_nonterminal_index_register(
            missing_run_id, missing_session["id"],
        )
        with mock.patch.object(
            server, "_start_agent_run_nonterminal_index_build", return_value=None,
        ):
            missing_record = self.archive(missing_session["id"])
        payload, status = missing_record.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_archive_index_unavailable")
        self.assertTrue(server.session_path(missing_session["id"]).exists())

        terminal_session = self.create_session(title="Terminal before index clear")
        terminal_run_id = "e" * 32
        server._rebuild_agent_run_nonterminal_index(force=True)
        server._agent_run_nonterminal_index_register(
            terminal_run_id, terminal_session["id"],
        )
        server.write_json(server._agent_run_path(terminal_run_id), {
            "version": 5,
            "id": terminal_run_id,
            "sessionId": terminal_session["id"],
            "status": "failed",
        })
        archived = self.archive(terminal_session["id"])
        self.assertEqual(archived.send_json.call_args.args[0]["status"], "archived")
        self.assertNotIn(
            terminal_run_id,
            server._read_agent_run_nonterminal_index()["entries"],
        )

    def test_process_freshness_rebuild_catches_legacy_writer_after_ready_index(self):
        session = self.create_session(title="Rollback writer compatibility")
        run_id = "f" * 32
        run_path = server._agent_run_path(run_id)
        server.write_json(run_path, {
            "version": 5,
            "id": run_id,
            "sessionId": session["id"],
            "status": "waiting_recovery",
        })
        key = str(server._agent_run_nonterminal_index_path().resolve(strict=False))
        with server._agent_run_index_builds_lock:
            server._agent_run_index_initialized_roots.discard(key)
        started = threading.Event()
        release = threading.Event()
        original_read_text = Path.read_text

        def gated_read_text(path, *args, **kwargs):
            if Path(path) == run_path:
                started.set()
                release.wait(timeout=5)
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", gated_read_text):
            worker = server._start_agent_run_nonterminal_index_build()
            self.assertIsNotNone(worker)
            self.assertTrue(started.wait(timeout=2))
            blocked = self.archive(session["id"])
            payload, status = blocked.send_json.call_args.args
            self.assertEqual(status, 503)
            self.assertEqual(payload["errorCode"], "session_archive_index_unavailable")
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        rejected = self.archive(session["id"])
        payload, status = rejected.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_archive_not_terminal")

    def test_agent_run_index_concurrent_register_preserves_all_entries(self):
        session_a = self.create_session(title="Concurrent register A")
        session_b = self.create_session(title="Concurrent register B")
        barrier = threading.Barrier(3)
        errors = []

        def register(run_id, session_id):
            try:
                barrier.wait(timeout=2)
                server._agent_run_nonterminal_index_register(run_id, session_id)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=register, args=("1" * 32, session_a["id"])),
            threading.Thread(target=register, args=("2" * 32, session_b["id"])),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(server._read_agent_run_nonterminal_index()["entries"], {
            "1" * 32: session_a["id"],
            "2" * 32: session_b["id"],
        })

    def test_agent_run_session_index_legacy_build_is_secret_free_and_idempotent(self):
        runs_dir = self.root / "agent-runs"
        secret = "AGENT-RUN-SESSION-INDEX-SECRET-SENTINEL"
        records = {
            "3" * 32: ("legacy-session-index-a", "waiting_recovery"),
            "4" * 32: ("legacy-session-index-b", "completed"),
        }
        for run_id, (session_id, status) in records.items():
            server.write_json(runs_dir / f"{run_id}.json", {
                "version": 5,
                "id": run_id,
                "sessionId": session_id,
                "status": status,
                "messages": [{"role": "user", "content": secret}],
                "request": {"url": f"https://example.invalid/?token={secret}"},
                "result": {"path": f"C:/secret/{secret}"},
            })
        shutil.rmtree(server._agent_run_session_index_dir())

        first = server._rebuild_agent_run_session_index(force=False)
        first_bytes = server._agent_run_session_index_path().read_bytes()
        second = server._rebuild_agent_run_session_index(force=False)

        expected = {run_id: session_id for run_id, (session_id, _status) in records.items()}
        self.assertEqual(first["entries"], expected)
        self.assertEqual(second["entries"], expected)
        self.assertEqual(server._agent_run_session_index_path().read_bytes(), first_bytes)
        self.assertNotIn(secret.encode("utf-8"), first_bytes)
        self.assertTrue(all(
            set(item) == {"runId", "sessionId"}
            for item in json.loads(first_bytes)["entries"]
        ))

    def test_agent_run_session_index_unavailable_or_stale_delete_fails_closed(self):
        session = self.create_session(title="Session index fail closed")
        run_id, run_path = self.create_terminal_agent_run(session["id"], "fail-closed")
        archived = self.archive(session["id"]).send_json.call_args.args[0]
        index_path = server._agent_run_session_index_path()
        secret = "SESSION-INDEX-FAILURE-SECRET-SENTINEL"

        def mutate(case):
            if case == "missing":
                index_path.unlink(missing_ok=True)
            elif case == "building":
                server._write_agent_run_session_index_building()
            elif case == "corrupt":
                index_path.write_text(
                    '{"schema":"wrong","secret":"' + secret + '"}',
                    encoding="utf-8",
                )
            elif case == "stale":
                server._write_agent_run_session_index({})
            elif case == "conflict":
                server._write_agent_run_session_index({run_id: "other-session"})
            else:
                raise AssertionError(case)

        for case in ("missing", "building", "corrupt", "stale", "conflict"):
            with self.subTest(case=case):
                server._rebuild_agent_run_session_index(force=True)
                mutate(case)
                with mock.patch.object(
                    server, "_start_agent_run_session_index_build", return_value=None,
                ):
                    rejected = self.make_handler()
                    server.CodeHandler.delete_archived_session(
                        rejected,
                        session["id"],
                        archived["archiveToken"],
                    )
                payload, status = rejected.send_json.call_args.args
                self.assertEqual(status, 503)
                self.assertEqual(
                    payload["errorCode"],
                    "session_delete_failed"
                    if case in {"stale", "conflict"}
                    else "session_archive_failed",
                )
                self.assertNotIn(secret, json.dumps(payload))
                self.assertTrue(server._session_archive_bundle_path(session["id"]).exists())
                self.assertFalse(server.session_path(session["id"]).exists())
                self.assertFalse(server.messages_path(session["id"]).exists())
                self.assertTrue(run_path.exists())

        server._rebuild_agent_run_session_index(force=True)
        deleted = self.make_handler()
        server.CodeHandler.delete_archived_session(
            deleted,
            session["id"],
            archived["archiveToken"],
        )
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(run_path.exists())

    def test_agent_run_session_index_process_rebuild_catches_legacy_terminal_run(self):
        session = self.create_session(title="Legacy writer process rebuild")
        run_id = "5" * 32
        run_path = server._agent_run_path(run_id)
        server.write_json(run_path, {
            "version": 5,
            "id": run_id,
            "sessionId": session["id"],
            "status": "completed",
        })
        archived = self.archive(session["id"]).send_json.call_args.args[0]
        key = str(server._agent_run_session_index_path().resolve(strict=False))
        with server._agent_run_index_builds_lock:
            server._agent_run_index_initialized_roots.discard(key)
        started = threading.Event()
        release = threading.Event()
        original_read_text = Path.read_text

        def gated_read_text(path, *args, **kwargs):
            if Path(path) == run_path:
                started.set()
                release.wait(timeout=5)
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", gated_read_text):
            worker = server._start_agent_run_session_index_build()
            self.assertIsNotNone(worker)
            self.assertTrue(started.wait(timeout=2))
            blocked = self.make_handler()
            server.CodeHandler.delete_archived_session(
                blocked,
                session["id"],
                archived["archiveToken"],
            )
            payload, status = blocked.send_json.call_args.args
            self.assertEqual(status, 503)
            self.assertEqual(payload["errorCode"], "session_archive_failed")
            self.assertTrue(run_path.exists())
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())

        deleted = self.make_handler()
        server.CodeHandler.delete_archived_session(
            deleted,
            session["id"],
            archived["archiveToken"],
        )
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(run_path.exists())

    def test_permanent_delete_and_late_agent_run_persist_are_race_safe(self):
        session = self.create_session(title="Delete/persist race")
        session_id = session["id"]
        run = server._create_agent_run(
            session_id,
            {
                "model": "fixture-model",
                "messages": [{"role": "user", "content": "terminal before delete"}],
            },
            "http://127.0.0.1:9",
            ["synthetic-key"],
            allowed_tools=[],
            start_worker=False,
        )
        self.assertTrue(server._finish_agent_run(run, "completed"))
        run_path = server._agent_run_path(run["id"])
        archived = self.archive(session_id).send_json.call_args.args[0]
        delete_entered = threading.Event()
        release_delete = threading.Event()
        persist_started = threading.Event()
        create_started = threading.Event()
        delete_errors = []
        persist_errors = []
        create_errors = []
        original_restore = server._restore_session_archive_file

        def gated_restore(*args, **kwargs):
            if not delete_entered.is_set():
                delete_entered.set()
                if not release_delete.wait(timeout=5):
                    raise AssertionError("delete release was not signalled")
            return original_restore(*args, **kwargs)

        deleted = self.make_handler()

        def run_delete():
            try:
                server.CodeHandler.delete_archived_session(
                    deleted,
                    session_id,
                    archived["archiveToken"],
                )
            except Exception as exc:
                delete_errors.append(exc)

        def run_persist():
            persist_started.set()
            try:
                server._persist_agent_run(run)
            except Exception as exc:
                persist_errors.append(exc)

        def run_create():
            create_started.set()
            try:
                server._create_agent_run(
                    session_id,
                    {
                        "model": "fixture-model",
                        "messages": [{"role": "user", "content": "must lose delete race"}],
                    },
                    "http://127.0.0.1:9",
                    ["synthetic-key"],
                    allowed_tools=[],
                    start_worker=False,
                )
            except Exception as exc:
                create_errors.append(exc)

        with mock.patch.object(
            server,
            "_restore_session_archive_file",
            side_effect=gated_restore,
        ):
            delete_thread = threading.Thread(target=run_delete)
            persist_thread = threading.Thread(target=run_persist)
            create_thread = threading.Thread(target=run_create)
            delete_thread.start()
            self.assertTrue(delete_entered.wait(timeout=2))
            persist_thread.start()
            create_thread.start()
            self.assertTrue(persist_started.wait(timeout=2))
            self.assertTrue(create_started.wait(timeout=2))
            release_delete.set()
            delete_thread.join(timeout=5)
            persist_thread.join(timeout=5)
            create_thread.join(timeout=5)

        self.assertFalse(delete_thread.is_alive())
        self.assertFalse(persist_thread.is_alive())
        self.assertFalse(create_thread.is_alive())
        self.assertEqual(delete_errors, [])
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertEqual(len(persist_errors), 1)
        self.assertIsInstance(persist_errors[0], server.AgentRunIndexError)
        self.assertEqual(len(create_errors), 1)
        self.assertIsInstance(create_errors[0], server.SessionLifecycleConflictError)
        self.assertEqual(create_errors[0].error_code, "session_deleted")
        self.assertFalse(run_path.exists())
        self.assertEqual(list(server._agent_runs_dir().glob("*.json")), [])
        self.assertNotIn(
            run["id"],
            server._read_agent_run_session_index()["entries"],
        )

    def test_agent_run_session_index_concurrent_register_preserves_all_entries(self):
        barrier = threading.Barrier(3)
        errors = []

        def register(run_id, session_id):
            try:
                barrier.wait(timeout=2)
                server._agent_run_session_index_register(run_id, session_id)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=register, args=("6" * 32, "session-index-a")),
            threading.Thread(target=register, args=("7" * 32, "session-index-b")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(server._read_agent_run_session_index()["entries"], {
            "6" * 32: "session-index-a",
            "7" * 32: "session-index-b",
        })

    def test_agent_run_index_unregister_schedules_rebuild_outside_shared_index_lock(self):
        def assert_index_lock_available():
            acquired = threading.Event()

            def probe():
                if server._agent_run_index_lock.acquire(timeout=0.5):
                    try:
                        acquired.set()
                    finally:
                        server._agent_run_index_lock.release()

            thread = threading.Thread(target=probe)
            thread.start()
            thread.join(timeout=1)
            self.assertTrue(acquired.is_set())

        cases = (
            (
                server._agent_run_nonterminal_index_unregister,
                "_read_agent_run_nonterminal_index",
                "_start_agent_run_nonterminal_index_build",
            ),
            (
                server._agent_run_session_index_unregister_run,
                "_read_agent_run_session_index",
                "_start_agent_run_session_index_build",
            ),
        )
        for unregister, read_name, start_name in cases:
            with self.subTest(unregister=unregister.__name__), mock.patch.object(
                server,
                read_name,
                side_effect=server.AgentRunIndexError("synthetic unavailable"),
            ), mock.patch.object(
                server,
                start_name,
                side_effect=assert_index_lock_available,
            ):
                self.assertFalse(unregister("8" * 32))

    def test_archive_only_delete_requires_current_token_and_keeps_siblings_safe(self):
        first = self.create_session(title="Delete archived")
        second = self.create_session(title="Keep sibling")
        child_handler = self.make_handler({"title": "Reparent after archive delete"})
        server.CodeHandler.branch_session(child_handler, first["id"])
        child_id = child_handler.send_json.call_args.args[0]["id"]
        first_goal = self.create_terminal_goal(first["id"])
        second_goal = self.create_terminal_goal(second["id"])
        first_run_id, first_run_path = self.create_terminal_agent_run(first["id"], "d")
        second_run_id, second_run_path = self.create_terminal_agent_run(second["id"], "e")
        first_run_before = first_run_path.read_bytes()
        first_token = self.archive(first["id"]).send_json.call_args.args[0]["archiveToken"]
        second_token = self.archive(second["id"]).send_json.call_args.args[0]["archiveToken"]
        self.assertEqual(first_run_path.read_bytes(), first_run_before)
        first_asset = self.create_asset_sidecar(first["id"], "d")
        second_asset = self.create_asset_sidecar(second["id"], "e")

        wrong = self.make_handler()
        server.CodeHandler.delete_archived_session(wrong, first["id"], "0" * 32)
        wrong_payload, wrong_status = wrong.send_json.call_args.args
        self.assertEqual(wrong_status, 409)
        self.assertEqual(wrong_payload["errorCode"], "session_archive_token_mismatch")
        self.assertTrue(server._session_archive_bundle_path(first["id"]).exists())
        self.assertTrue(first_asset.exists())

        self.unarchive(first["id"])
        replacement_token = self.archive(first["id"]).send_json.call_args.args[0]["archiveToken"]
        self.assertNotEqual(replacement_token, first_token)
        stale = self.make_handler()
        server.CodeHandler.delete_archived_session(stale, first["id"], first_token)
        stale_payload, stale_status = stale.send_json.call_args.args
        self.assertEqual(stale_status, 409)
        self.assertEqual(stale_payload["errorCode"], "session_archive_token_mismatch")

        deleted = self.make_handler()
        server.CodeHandler.delete_archived_session(deleted, first["id"], replacement_token)
        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(server.session_path(first["id"]).exists())
        self.assertFalse(server.messages_path(first["id"]).exists())
        self.assertFalse(first_asset.exists())
        self.assertFalse(first_goal.exists())
        self.assertFalse(first_run_path.exists())
        self.assertNotIn(first_run_id, server._agent_runs)
        self.assertNotIn(first["id"], server._read_session_index())
        self.assertTrue(server._session_archive_bundle_path(second["id"]).exists())
        self.assertTrue(second_asset.exists())
        self.assertTrue(second_goal.exists())
        self.assertTrue(second_run_path.exists())
        self.assertIn(second_run_id, server._agent_runs)
        child_meta = server.read_json(server.session_path(child_id), {})
        self.assertNotIn("_parentId", child_meta)
        self.assertEqual(child_meta["_branchDepth"], 0)
        self.assertEqual(self.archive_summary()[0]["archiveToken"], second_token)

        repeated = self.make_handler()
        server.CodeHandler.delete_archived_session(repeated, first["id"], replacement_token)
        repeated_payload, repeated_status = repeated.send_json.call_args.args
        self.assertEqual(repeated_status, 410)
        self.assertEqual(repeated_payload["errorCode"], "session_deleted")
        with self.assertRaises(server.SessionLifecycleConflictError) as raised:
            server._create_agent_run(
                first["id"],
                {"model": "fixture-model", "messages": [{
                    "role": "user",
                    "content": "must stay deleted",
                }]},
                "http://127.0.0.1:9",
                ["synthetic-key"],
                start_worker=False,
            )
        self.assertEqual(raised.exception.error_code, "session_deleted")

    def test_archive_only_delete_reads_only_target_agent_runs_from_ready_index(self):
        session = self.create_session(title="Indexed permanent delete")
        target_run_id, target_run_path = self.create_terminal_agent_run(
            session["id"], "d",
        )
        unrelated_dir = self.root / "agent-runs"
        for index in range(1001):
            run_id = f"{index + 1:032x}"
            server.write_json(unrelated_dir / f"{run_id}.json", {
                "version": 5,
                "id": run_id,
                "sessionId": f"unrelated-{index:04d}",
                "status": "completed",
            })
        server._rebuild_agent_run_session_index(force=True)
        archived = self.archive(session["id"]).send_json.call_args.args[0]

        original_read = server._read_session_meta_strict
        observed_run_reads = []

        def tracked_read(path):
            candidate = Path(path)
            if candidate.parent == unrelated_dir and candidate.suffix == ".json":
                observed_run_reads.append(candidate.stem)
            return original_read(path)

        deleted = self.make_handler()
        with mock.patch.object(server, "_read_session_meta_strict", tracked_read):
            server.CodeHandler.delete_archived_session(
                deleted,
                session["id"],
                archived["archiveToken"],
            )

        self.assertEqual(deleted.send_json.call_args.args[0], {"ok": True})
        self.assertEqual(observed_run_reads, [target_run_id])
        self.assertFalse(target_run_path.exists())

    def test_archive_only_delete_failure_keeps_archived_state_recoverable(self):
        session = self.create_session(title="Delete rollback remains archived")
        token = self.archive(session["id"]).send_json.call_args.args[0]["archiveToken"]
        asset = self.create_asset_sidecar(session["id"], "r")
        meta_path = server.session_path(session["id"])
        messages_path = server.messages_path(session["id"])
        index_path = server._session_index_path()
        bundle = server._session_archive_bundle_path(session["id"])
        before = {
            "bundle": {
                path.name: path.read_bytes()
                for path in bundle.iterdir()
                if path.is_file()
            },
            "index": index_path.read_bytes(),
        }
        handler = self.make_handler()
        original_remove_index = server._remove_session_index_entry
        remove_calls = 0

        def fail_first_remove(session_id):
            nonlocal remove_calls
            remove_calls += 1
            if remove_calls == 1:
                raise PermissionError(13, "ARCHIVE-DELETE-SECRET", str(index_path))
            return original_remove_index(session_id)

        with mock.patch.object(
            server,
            "_remove_session_index_entry",
            side_effect=fail_first_remove,
        ):
            server.CodeHandler.delete_archived_session(handler, session["id"], token)
        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_delete_failed")
        self.assertNotIn("ARCHIVE-DELETE-SECRET", json.dumps(payload))
        self.assertFalse(meta_path.exists())
        self.assertFalse(messages_path.exists())
        self.assertEqual({
            path.name: path.read_bytes()
            for path in bundle.iterdir()
            if path.is_file()
        }, before["bundle"])
        self.assertEqual(index_path.read_bytes(), before["index"])
        self.assertTrue(asset.exists())
        self.assertEqual(self.archive_summary()[0]["archiveToken"], token)
        retried = self.make_handler()
        server.CodeHandler.delete_archived_session(retried, session["id"], token)
        self.assertEqual(retried.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(meta_path.exists())
        self.assertFalse(asset.exists())

    def test_concurrent_save_finishes_before_archive_and_state_is_not_lost(self):
        session = self.create_session(title="Concurrent archive")
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
            "title": "Saved before archive",
            "messages": [{"role": "user", "content": "saved"}],
            "expectedRevision": 0,
        })
        archived = self.make_handler()

        def run_save():
            try:
                server.CodeHandler.save_session(save, session_id)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        def run_archive():
            try:
                server.CodeHandler.archive_session_lifecycle(archived, session_id)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        with mock.patch.object(server, "write_jsonl", side_effect=blocked_write):
            save_thread = threading.Thread(target=run_save)
            archive_thread = threading.Thread(target=run_archive)
            save_thread.start()
            self.assertTrue(save_entered.wait(5))
            archive_thread.start()
            release_save.set()
            save_thread.join(timeout=5)
            archive_thread.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertFalse(save_thread.is_alive())
        self.assertFalse(archive_thread.is_alive())
        self.assertEqual(save.send_json.call_args.args[0]["revision"], 1)
        archive_payload = archived.send_json.call_args.args[0]
        self.assertEqual(archive_payload["status"], "archived")
        meta = server.read_json(
            server._session_archive_bundle_path(session_id) / "session.json",
            {},
        )
        self.assertEqual(meta["title"], "Saved before archive")
        self.assertNotIn(session_id, server._read_session_index())
        self.assertEqual(
            server._read_session_archive_manifest(session_id)["archiveToken"],
            archive_payload["archiveToken"],
        )

    def test_lifecycle_http_routes_are_distinct_from_compaction_archive(self):
        session = self.create_session(title="Lifecycle routes")
        archive_handler = self.make_handler(
            path=f"/api/session-archive/{session['id']}/archive",
        )
        server.CodeHandler.do_POST(archive_handler)
        archive_payload = archive_handler.send_json.call_args.args[0]
        self.assertEqual(archive_payload["status"], "archived")

        list_handler = self.make_handler(path="/api/session-archive")
        server.CodeHandler.do_GET(list_handler)
        self.assertEqual(
            [item["id"] for item in list_handler.send_json.call_args.args[0]["data"]],
            [session["id"]],
        )

        restore_handler = self.make_handler(
            path=f"/api/session-archive/{session['id']}/restore",
        )
        server.CodeHandler.do_POST(restore_handler)
        self.assertEqual(
            restore_handler.send_json.call_args.args[0],
            {"ok": True, "status": "active"},
        )
        token = self.archive(session["id"]).send_json.call_args.args[0]["archiveToken"]
        delete_handler = self.make_handler(
            path=f"/api/session-archive/{session['id']}?archiveToken={token}",
        )
        server.CodeHandler.do_DELETE(delete_handler)
        self.assertEqual(delete_handler.send_json.call_args.args[0], {"ok": True})

        # The established full-history compaction endpoint keeps its method/path.
        compact = self.make_handler({"messages": [{"role": "user", "content": "history"}]})
        compact.path = f"/api/sessions/{'b' * 16}/archive"
        with mock.patch.object(server.CodeHandler, "archive_session") as archive_copy:
            server.CodeHandler.do_PUT(compact)
        archive_copy.assert_called_once_with("b" * 16)

        # Legacy active-Session DELETE keeps its established method/path.
        legacy = self.create_session(title="Legacy delete route")
        legacy_delete = self.make_handler(path=f"/api/sessions/{legacy['id']}")
        server.CodeHandler.do_DELETE(legacy_delete)
        self.assertEqual(legacy_delete.send_json.call_args.args[0], {"ok": True})
        self.assertFalse(server.session_path(legacy["id"]).exists())

    def test_archived_session_rejects_new_agent_run_before_creation(self):
        session = self.create_session(title="No new AgentRun")
        self.archive(session["id"])
        runs_before = list((self.root / "agent-runs").glob("*.json"))
        with self.assertRaises(server.SessionLifecycleConflictError) as raised:
            server._create_agent_run(
                session["id"],
                {"model": "fixture-model", "messages": [{
                    "role": "user",
                    "content": "must not run",
                }]},
                "http://127.0.0.1:9",
                ["synthetic-key"],
                start_worker=False,
            )
        self.assertEqual(raised.exception.error_code, "session_archived")
        self.assertEqual(list((self.root / "agent-runs").glob("*.json")), runs_before)

    def test_active_and_archive_dual_location_fails_closed_everywhere(self):
        session = self.create_session(title="Dual location conflict")
        session_id = session["id"]
        self.archive(session_id)
        bundle = server._session_archive_bundle_path(session_id)
        manifest = server._read_session_archive_manifest(session_id)
        active_meta, active_messages = server._session_archive_original_paths(
            session_id,
            manifest["original"],
        )
        server._restore_path_snapshot(active_meta, (bundle / "session.json").read_bytes())
        server._restore_path_snapshot(active_messages, (bundle / "messages.jsonl").read_bytes())

        active_list = self.make_handler()
        server.CodeHandler.get_sessions(active_list)
        archived_list = self.make_handler()
        server.CodeHandler.get_archived_sessions(archived_list)
        opened = self.make_handler()
        server.CodeHandler.get_session(opened, session_id)
        saved = self.make_handler({"title": "must not save"})
        server.CodeHandler.save_session(saved, session_id)
        for handler in (active_list, archived_list, opened, saved):
            payload, status = handler.send_json.call_args.args
            self.assertEqual(status, 409)
            self.assertEqual(payload["errorCode"], "session_archive_location_conflict")
        self.assertTrue(active_meta.exists())
        self.assertTrue(active_messages.exists())
        self.assertTrue(bundle.exists())

    def test_archive_windows_lock_failure_is_durable_and_restart_recovers_forward(self):
        session = self.create_session(title="Windows lock recovery")
        session_id = session["id"]
        active_meta = server.session_path(session_id)
        active_messages = server.messages_path(session_id)
        original_unlink = Path.unlink
        sentinel = "WINDOWS-LOCK-ARCHIVE-SECRET"

        def locked_unlink(path, *args, **kwargs):
            if Path(path) == active_meta:
                raise PermissionError(32, sentinel, str(path))
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", new=locked_unlink):
            failed = self.archive(session_id)
        payload, status = failed.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(payload["errorCode"], "session_archive_recovery_failed")
        self.assertNotIn(sentinel, json.dumps(payload))
        self.assertTrue(active_meta.exists())
        self.assertTrue(active_messages.exists())
        self.assertTrue(server._session_archive_bundle_path(session_id).exists())
        self.assertTrue(server._session_archive_journal_path(session_id).exists())

        # A new process/list request can deterministically finish the admitted move.
        server._recover_all_session_archive_transactions()
        self.assertFalse(active_meta.exists())
        self.assertFalse(active_messages.exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertEqual(self.archive_summary()[0]["id"], session_id)

    def test_archive_preparation_failure_is_sanitized_and_byte_preserving(self):
        session = self.create_session(title="Archive preparation failure")
        session_id = session["id"]
        active_meta = server.session_path(session_id)
        active_messages = server.messages_path(session_id)
        index_path = server._session_index_path()
        before = {
            "meta": active_meta.read_bytes(),
            "messages": active_messages.read_bytes(),
            "index": index_path.read_bytes(),
        }
        original_write_json = server.write_json
        sentinel = "ARCHIVE-PREPARE-PATH-SECRET"

        def fail_manifest(path, payload):
            if Path(path).name == "manifest.json":
                raise PermissionError(13, sentinel, str(path))
            return original_write_json(path, payload)

        with mock.patch.object(server, "write_json", side_effect=fail_manifest):
            failed = self.archive(session_id)
        payload, status = failed.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_archive_failed")
        self.assertNotIn(sentinel, json.dumps(payload))
        self.assertEqual(active_meta.read_bytes(), before["meta"])
        self.assertEqual(active_messages.read_bytes(), before["messages"])
        self.assertEqual(index_path.read_bytes(), before["index"])
        self.assertFalse(server._session_archive_bundle_path(session_id).exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        staging_root = server._session_archive_root() / ".staging"
        self.assertEqual(list(staging_root.iterdir()) if staging_root.exists() else [], [])

    def test_archive_index_commit_failure_is_forward_recovered_without_dual_authority(self):
        session = self.create_session(title="Archive index commit failure")
        session_id = session["id"]
        original_remove = server._remove_session_index_entry
        calls = 0

        def fail_once(target_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise PermissionError(13, "ARCHIVE-INDEX-SECRET", "hidden")
            return original_remove(target_id)

        with mock.patch.object(
            server,
            "_remove_session_index_entry",
            side_effect=fail_once,
        ):
            failed = self.archive(session_id)
        payload, status = failed.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_archive_failed")
        self.assertNotIn("ARCHIVE-INDEX-SECRET", json.dumps(payload))
        self.assertFalse(server.session_path(session_id).exists())
        self.assertFalse(server.messages_path(session_id).exists())
        self.assertTrue(server._session_archive_bundle_path(session_id).exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertNotIn(session_id, server._read_session_index())

    def test_restore_commit_crash_recovers_to_unique_active_location(self):
        session = self.create_session(title="Restore crash recovery")
        session_id = session["id"]
        active_meta = server.session_path(session_id)
        active_messages = server.messages_path(session_id)
        meta_before = active_meta.read_bytes()
        messages_before = active_messages.read_bytes()
        self.archive(session_id)
        bundle = server._session_archive_bundle_path(session_id)
        original_remove = server._remove_owned_archive_tree

        def fail_bundle_remove(path):
            if Path(path).resolve(strict=False) == bundle.resolve(strict=False):
                raise PermissionError(32, "RESTORE-LOCK-SECRET", str(path))
            return original_remove(path)

        with mock.patch.object(
            server,
            "_remove_owned_archive_tree",
            side_effect=fail_bundle_remove,
        ):
            failed = self.unarchive(session_id)
        payload, status = failed.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(payload["errorCode"], "session_archive_recovery_failed")
        self.assertNotIn("RESTORE-LOCK-SECRET", json.dumps(payload))
        self.assertTrue(active_meta.exists())
        self.assertTrue(active_messages.exists())
        self.assertTrue(bundle.exists())
        self.assertTrue(server._session_archive_journal_path(session_id).exists())

        server._recover_all_session_archive_transactions()
        self.assertEqual(active_meta.read_bytes(), meta_before)
        self.assertEqual(active_messages.read_bytes(), messages_before)
        self.assertFalse(bundle.exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertIn(session_id, server._read_session_index())

    def test_restore_active_committed_without_bundle_finishes_journal_only(self):
        session = self.create_session(title="Restore commit window")
        session_id = session["id"]
        self.archive(session_id)
        bundle = server._session_archive_bundle_path(session_id)
        manifest = server._read_session_archive_manifest(session_id)
        active_meta, active_messages = server._session_archive_original_paths(
            session_id,
            manifest["original"],
        )
        transaction_id = "c" * 32
        server._restore_session_archive_file(
            active_meta,
            bundle / "session.json",
            manifest["files"]["session.json"],
        )
        server._restore_session_archive_file(
            active_messages,
            bundle / "messages.jsonl",
            manifest["files"]["messages.jsonl"],
        )
        server._write_session_archive_journal(session_id, {
            "action": "restore",
            "state": "active_committed",
            "transactionId": transaction_id,
        })
        server._remove_owned_archive_tree(bundle)

        server._recover_all_session_archive_transactions()
        self.assertTrue(active_meta.exists())
        self.assertTrue(active_messages.exists())
        self.assertFalse(bundle.exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertIn(session_id, server._read_session_index())

    def test_delete_prepared_crash_recovers_full_owned_fact_deletion(self):
        session = self.create_session(title="Delete crash recovery")
        session_id = session["id"]
        goal_path = self.create_terminal_goal(session_id)
        asset_path = self.create_asset_sidecar(session_id, "x")
        run_id, run_path = self.create_terminal_agent_run(session_id, "x")
        token = self.archive(session_id).send_json.call_args.args[0]["archiveToken"]
        transaction_id = "b" * 32
        server._write_session_archive_journal(session_id, {
            "action": "delete",
            "state": "prepared",
            "transactionId": transaction_id,
        })

        # Simulate a process restart before active core restoration.
        with server._agent_run_lock:
            server._agent_runs.clear()
        server._recover_all_session_archive_transactions()
        self.assertFalse(server._session_archive_bundle_path(session_id).exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertFalse(goal_path.exists())
        self.assertFalse(asset_path.exists())
        self.assertFalse(run_path.exists())
        self.assertNotIn(run_id, server._agent_runs)
        repeated = self.make_handler()
        server.CodeHandler.delete_archived_session(repeated, session_id, token)
        self.assertEqual(repeated.send_json.call_args.args[1], 410)
        self.assertEqual(repeated.send_json.call_args.args[0]["errorCode"], "session_deleted")

    def test_delete_facts_committed_without_bundle_finishes_journal_only(self):
        session = self.create_session(title="Delete commit window")
        session_id = session["id"]
        token = self.archive(session_id).send_json.call_args.args[0]["archiveToken"]
        bundle = server._session_archive_bundle_path(session_id)
        manifest = server._read_session_archive_manifest(session_id)
        active_meta, active_messages = server._session_archive_original_paths(
            session_id,
            manifest["original"],
        )
        transaction_id = "d" * 32
        server._restore_session_archive_file(
            active_meta,
            bundle / "session.json",
            manifest["files"]["session.json"],
        )
        server._restore_session_archive_file(
            active_messages,
            bundle / "messages.jsonl",
            manifest["files"]["messages.jsonl"],
        )
        server.CodeHandler.delete_session(
            self.make_handler(),
            session_id,
            send_response=False,
            delete_terminal_agent_runs=True,
            session_core_path=active_meta,
            messages_core_path=active_messages,
        )
        server._write_session_archive_journal(session_id, {
            "action": "delete",
            "state": "facts_deleted",
            "transactionId": transaction_id,
        })
        server._remove_owned_archive_tree(bundle)

        server._recover_all_session_archive_transactions()
        self.assertFalse(active_meta.exists())
        self.assertFalse(active_messages.exists())
        self.assertFalse(bundle.exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        repeated = self.make_handler()
        server.CodeHandler.delete_archived_session(repeated, session_id, token)
        self.assertEqual(repeated.send_json.call_args.args[1], 410)

    def test_delete_recovery_failure_preserves_journal_until_forward_recovery(self):
        session = self.create_session(title="Delete recovery failure")
        session_id = session["id"]
        goal_path = self.create_terminal_goal(session_id)
        asset_path = self.create_asset_sidecar(session_id, "q")
        _, run_path = self.create_terminal_agent_run(session_id, "q")
        token = self.archive(session_id).send_json.call_args.args[0]["archiveToken"]
        bundle = server._session_archive_bundle_path(session_id)
        original_remove_index = server._remove_session_index_entry

        with mock.patch.object(
            server,
            "_remove_session_index_entry",
            side_effect=PermissionError(32, "DELETE-RECOVERY-SECRET", "hidden"),
        ):
            failed = self.make_handler()
            server.CodeHandler.delete_archived_session(failed, session_id, token)
        payload, status = failed.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(payload["errorCode"], "session_delete_recovery_failed")
        self.assertNotIn("DELETE-RECOVERY-SECRET", json.dumps(payload))
        self.assertTrue(bundle.exists())
        self.assertTrue(server._session_archive_journal_path(session_id).exists())
        self.assertTrue(goal_path.exists())
        self.assertTrue(asset_path.exists())
        self.assertTrue(run_path.exists())

        # Once the external lock/failure clears, the durable journal completes
        # the already-authorized deletion rather than presenting a false archive.
        self.assertIsNotNone(original_remove_index)
        server._recover_all_session_archive_transactions()
        self.assertFalse(bundle.exists())
        self.assertFalse(server._session_archive_journal_path(session_id).exists())
        self.assertFalse(goal_path.exists())
        self.assertFalse(asset_path.exists())
        self.assertFalse(run_path.exists())

    def test_import_archive_race_cannot_recreate_active_core(self):
        session = self.create_session(title="Import/archive race")
        session_id = session["id"]
        source_path = self.root / "import-race.jsonl"
        source_path.write_text('{"type":"message"}\n', encoding="utf-8")
        replace_entered = threading.Event()
        release_replace = threading.Event()
        original_replace = server.os.replace
        archive_errors = []
        import_errors = []

        def blocked_replace(source, target):
            if Path(target) == server._session_archive_bundle_path(session_id):
                replace_entered.set()
                if not release_replace.wait(5):
                    raise AssertionError("archive replace release was not signalled")
            return original_replace(source, target)

        def run_archive():
            try:
                self.archive(session_id)
            except Exception as exc:  # pragma: no cover
                archive_errors.append(exc)

        def run_import():
            try:
                server._persist_import_snapshot(
                    source="codex",
                    source_path=source_path,
                    source_session_id="source-import-race",
                    requested_session_id=session_id,
                    force_requested_id=True,
                    title="Imported race",
                    created_at="2026-08-28T12:00:00Z",
                    messages=[{"role": "user", "content": "import race"}],
                    stats={},
                    last_usage={},
                    resolved_project_id=None,
                    resolved_cwd="",
                )
            except Exception as exc:
                import_errors.append(exc)

        with mock.patch.object(server.os, "replace", side_effect=blocked_replace):
            archive_thread = threading.Thread(target=run_archive)
            import_thread = threading.Thread(target=run_import)
            archive_thread.start()
            self.assertTrue(replace_entered.wait(5))
            import_thread.start()
            release_replace.set()
            archive_thread.join(5)
            import_thread.join(5)
        self.assertEqual(archive_errors, [])
        self.assertEqual(len(import_errors), 1)
        self.assertIsInstance(import_errors[0], server.SessionLifecycleConflictError)
        self.assertEqual(import_errors[0].error_code, "session_archived")
        self.assertFalse(server.session_path(session_id).exists())
        self.assertFalse(server.messages_path(session_id).exists())
        self.assertTrue(server._session_archive_bundle_path(session_id).exists())
        self.assertNotIn(session_id, server._read_session_index())

    def test_archive_and_new_agent_run_admission_are_race_safe(self):
        session = self.create_session(title="Archive admission race")
        session_id = session["id"]
        archive_write_entered = threading.Event()
        release_archive_write = threading.Event()
        archive_errors = []
        create_errors = []
        original_replace = server.os.replace

        def blocked_archive_replace(source, target):
            if Path(target) == server._session_archive_bundle_path(session_id):
                archive_write_entered.set()
                if not release_archive_write.wait(5):
                    raise AssertionError("archive write release was not signalled")
            return original_replace(source, target)

        archived = self.make_handler()

        def run_archive():
            try:
                server.CodeHandler.archive_session_lifecycle(archived, session_id)
            except Exception as exc:  # pragma: no cover - assertion reports details
                archive_errors.append(exc)

        def run_create():
            try:
                server._create_agent_run(
                    session_id,
                    {"model": "fixture-model", "messages": [{
                        "role": "user",
                        "content": "must lose archive admission race",
                    }]},
                    "http://127.0.0.1:9",
                    ["synthetic-key"],
                    start_worker=False,
                )
            except Exception as exc:
                create_errors.append(exc)

        with mock.patch.object(server.os, "replace", side_effect=blocked_archive_replace):
            archive_thread = threading.Thread(target=run_archive)
            create_thread = threading.Thread(target=run_create)
            archive_thread.start()
            self.assertTrue(archive_write_entered.wait(5))
            create_thread.start()
            release_archive_write.set()
            archive_thread.join(timeout=5)
            create_thread.join(timeout=5)

        self.assertFalse(archive_thread.is_alive())
        self.assertFalse(create_thread.is_alive())
        self.assertEqual(archive_errors, [])
        self.assertEqual(archived.send_json.call_args.args[0]["status"], "archived")
        self.assertEqual(len(create_errors), 1)
        self.assertIsInstance(create_errors[0], server.SessionLifecycleConflictError)
        self.assertEqual(create_errors[0].error_code, "session_archived")
        self.assertEqual(list((self.root / "agent-runs").glob("*.json")), [])


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

    def start_http_server(self):
        server.ThreadingHTTPServer.daemon_threads = True
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.CodeHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def cleanup():
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        self.addCleanup(cleanup)
        return http.client.HTTPConnection(
            "127.0.0.1",
            httpd.server_address[1],
            timeout=5,
        )

    @staticmethod
    def http_json(connection, method, path, body=None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {}
        if payload is not None:
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            }
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8"))

    def test_stale_put_consumes_body_before_asset_get_on_same_connection(self):
        connection = self.start_http_server()
        self.addCleanup(connection.close)
        status, created = self.http_json(connection, "POST", "/api/sessions", {
            "title": "keep-alive stale PUT",
            "messages": [],
        })
        self.assertEqual(status, 201)
        session_id = created["id"]
        self.assertEqual(
            self.http_json(connection, "DELETE", f"/api/sessions/{session_id}"),
            (200, {"ok": True}),
        )

        stale_body = {
            "title": "must stay deleted",
            "messages": [{"role": "user", "content": "stale body sentinel"}],
            "expectedRevision": 0,
        }
        status, payload = self.http_json(
            connection,
            "PUT",
            f"/api/sessions/{session_id}",
            stale_body,
        )
        self.assertEqual(status, 410)
        self.assertEqual(payload["errorCode"], "session_deleted")

        asset_id = "ga1_" + ("z" * 43)
        status, payload = self.http_json(
            connection,
            "GET",
            f"/api/sessions/{session_id}/generated-assets/{asset_id}",
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["errorCode"], "generated_asset_not_found")

    def test_early_messages_post_consumes_body_before_next_same_connection_request(self):
        for state in ("deleted", "missing"):
            with self.subTest(state=state):
                connection = self.start_http_server()
                self.addCleanup(connection.close)
                if state == "deleted":
                    status, created = self.http_json(
                        connection,
                        "POST",
                        "/api/sessions",
                        {"title": "deleted messages", "messages": []},
                    )
                    self.assertEqual(status, 201)
                    session_id = created["id"]
                    self.assertEqual(
                        self.http_json(
                            connection,
                            "DELETE",
                            f"/api/sessions/{session_id}",
                        ),
                        (200, {"ok": True}),
                    )
                    expected_status = 410
                    expected_code = "session_deleted"
                else:
                    session_id = "missingmessages01"
                    expected_status = 404
                    expected_code = "session_not_found"

                status, payload = self.http_json(
                    connection,
                    "POST",
                    f"/api/sessions/{session_id}/messages",
                    {"messages": [{"role": "assistant", "content": "stale"}]},
                )
                self.assertEqual(status, expected_status)
                self.assertEqual(payload["errorCode"], expected_code)
                status, payload = self.http_json(connection, "GET", "/api/sessions")
                self.assertEqual(status, 200)
                self.assertIn("data", payload)

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
        stale.read_body_json.assert_called_once_with()
        self.assertEqual(status, 410)
        self.assertEqual(payload["errorCode"], "session_deleted")
        self.assertFalse(server.session_path(session_id).exists())
        self.assertFalse(server.messages_path(session_id).exists())
        self.assertNotIn(session_id, server._read_session_index())

    def test_missing_messages_test_double_consumes_body_exactly_once(self):
        handler = self.make_handler({
            "messages": [{"role": "assistant", "content": "discard once"}],
        })
        server.CodeHandler.append_messages(handler, "missingmessages02")

        handler.read_body_json.assert_called_once_with()
        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 404)
        self.assertEqual(payload["errorCode"], "session_not_found")

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
