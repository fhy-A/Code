"""Direct session metadata vs archive backups under SESSIONS_DIR.

The goal-v2 sidecar dependency is replaced by a recording stub, so the archive
chain here proves the handler/backup call boundary only; it is not a real
sidecar persistence acceptance test.

Regression coverage for the archive-before-compaction path: the project
archive hook must only treat files that sit directly in SESSIONS_DIR as
session metadata, and must keep rejecting invalid direct identities instead
of swallowing the error.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod
from code_runtime import project_archive


class _Adapter:
    """Minimal stand-in for the handler; the real archive_session chain runs."""

    def __init__(self, body):
        self._body = body
        self.responses = []

    def read_body_json(self):
        return self._body

    def send_json(self, payload, status=200):
        self.responses.append({"status": status, "payload": payload})


class _SidecarStub:
    def __init__(self):
        self.calls = []

    def archive_sidecar(self, session_id, path):
        self.calls.append((session_id, str(path)))
        Path(path).write_text("", encoding="utf-8")


class _GoalRuntimeStub:
    def __init__(self):
        self.service = _SidecarStub()


class NoteMetaWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="code0613-meta-")
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "data"
        self.sessions = self.data_dir / "sessions"
        self.sessions.mkdir(parents=True)
        (self.sessions / "archive").mkdir()
        self.sid = "session-h3-2d2-synthetic"
        self.sidecar = _GoalRuntimeStub()
        self.patches = [
            mock.patch.object(server_mod, "DATA_DIR", self.data_dir),
            mock.patch.object(server_mod, "SESSIONS_DIR", self.sessions),
            mock.patch.object(server_mod, "now_iso", return_value="2026-09-17T00:00:00+00:00"),
            mock.patch.object(server_mod, "goal_v2_runtime", return_value=self.sidecar),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def _service(self):
        return server_mod._project_archive_service()

    def test_archive_backup_chain_writes_json_and_jsonl_without_identity_error(self):
        messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}]
        server_mod.write_jsonl(server_mod.messages_path(self.sid), messages)
        adapter = _Adapter({"messages": messages})
        server_mod.CodeHandler.archive_session(adapter, self.sid)
        self.assertEqual(len(adapter.responses), 1, adapter.responses)
        response = adapter.responses[0]
        self.assertEqual(response["status"], 200, response)
        self.assertTrue(response["payload"]["ok"], response)
        archive_path = Path(response["payload"]["path"])
        self.assertEqual(archive_path.parent, self.sessions / "archive")
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["id"], self.sid)
        self.assertEqual(payload["messageCount"], 2)
        jsonl = archive_path.with_suffix(".jsonl")
        self.assertTrue(jsonl.is_file(), "raw JSONL backup must be written")
        jsonl_messages = [
            json.loads(line)
            for line in jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(jsonl_messages, messages, "JSONL backup must carry the same messages as the JSON backup")
        # The goal-v2 sidecar is a stub: this only proves the call boundary and the
        # expected path are reached, not real sidecar persistence.
        self.assertEqual(len(self.sidecar.service.calls), 1)
        self.assertEqual(self.sidecar.service.calls[0][0], self.sid)

    def test_archive_subdirectory_file_is_not_treated_as_session_metadata(self):
        path = self.sessions / "archive" / (self.sid + "_2026-09-17T00-00-00.000000.json")
        path.write_text(json.dumps({"id": self.sid}), encoding="utf-8")
        service = self._service()
        service.store.generation(self.sid, watch=True, persist=True)
        before = service.store.generation(self.sid)
        with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
            service.note_meta_write(path, {"id": self.sid})
        self.assertEqual(bump.call_count, 0, "archive backups must not touch session generations")
        self.assertEqual(service.store.generation(self.sid), before)

    def test_nested_archive_backup_is_not_treated_as_session_metadata(self):
        # Depth alone accepts a four-part path, so the archive subtree is
        # excluded by name: this path would otherwise reach session_id() and,
        # with a location change, bump the generation.
        path = self.sessions / "archive" / "2026" / "09" / (self.sid + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"id": self.sid, "projectId": "p-archive-old"}), encoding="utf-8")
        service = self._service()
        service.store.generation(self.sid, watch=True, persist=True)
        before = service.store.generation(self.sid)
        with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
            service.note_meta_write(path, {"id": self.sid, "projectId": "p-archive-new"})
        self.assertEqual(bump.call_count, 0, "a four-deep archive backup must not touch generations")
        self.assertEqual(service.store.generation(self.sid), before)


    def test_direct_session_metadata_still_reaches_the_generation_bump(self):
        path = self.sessions / (self.sid + ".json")
        path.write_text(json.dumps({"id": self.sid, "projectId": "old-project"}), encoding="utf-8")
        service = self._service()
        service.store.generation(self.sid, watch=True, persist=True)
        with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
            service.note_meta_write(path, {"id": self.sid, "projectId": "new-project"})
        self.assertEqual(bump.call_count, 1, "a real metadata location change must bump the generation")

    def test_invalid_direct_identity_is_still_rejected(self):
        path = self.sessions / "not.a.session.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(project_archive.BatchError) as caught:
            self._service().note_meta_write(path, {"id": "not.a.session"})
        self.assertEqual(caught.exception.code, "project_archive_invalid_state")

    def test_hierarchical_metadata_from_production_layout_bumps_the_generation(self):
        path = Path(server_mod.session_path(self.sid))
        parts = path.relative_to(self.sessions).parts
        self.assertIn(len(parts), (1, 4), path)
        hier = Path(server_mod.session_path(self.sid))
        self.assertEqual(len(hier.relative_to(self.sessions).parts), 4, hier)
        hier.parent.mkdir(parents=True, exist_ok=True)
        service = self._service()
        before = service.store.generation(self.sid, watch=True, persist=True)
        with mock.patch.object(server_mod, "_project_archive_service", return_value=service):
            with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
                server_mod.write_json(hier, {"id": self.sid, "projectId": "p-hier"})
        self.assertEqual(bump.call_count, 1, "hierarchical session metadata must reach the generation hook")
        self.assertNotEqual(service.store.generation(self.sid), before)

    def test_project_move_back_sequence_always_registers_generation_changes(self):
        hier = Path(server_mod.session_path(self.sid))
        hier.parent.mkdir(parents=True, exist_ok=True)
        service = self._service()
        seen = set()
        with mock.patch.object(server_mod, "_project_archive_service", return_value=service):
            for project in ("p-a", "p-b", "p-a"):
                before = service.store.generation(self.sid, watch=True, persist=True)
                with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
                    server_mod.write_json(hier, {"id": self.sid, "projectId": project})
                self.assertEqual(bump.call_count, 1, project)
                after = service.store.generation(self.sid)
                self.assertNotEqual(after, before, project)
                seen.add(after)
        self.assertEqual(len(seen), 3, "each move must register a generation so the conflict check fires")

    def test_flat_legacy_metadata_still_bumps_the_generation(self):
        path = self.sessions / (self.sid + ".json")
        path.write_text(json.dumps({"id": self.sid, "projectId": "p-flat-old"}), encoding="utf-8")
        service = self._service()
        service.store.generation(self.sid, watch=True, persist=True)
        with mock.patch.object(service.store, "bump", wraps=service.store.bump) as bump:
            service.note_meta_write(path, {"id": self.sid, "projectId": "p-flat-new"})
        self.assertEqual(bump.call_count, 1, "flat legacy metadata must keep working")

    def test_files_outside_sessions_dir_are_ignored(self):
        path = self.data_dir / "elsewhere.json"
        path.write_text("{}", encoding="utf-8")
        self._service().note_meta_write(path, {"id": self.sid})


if __name__ == "__main__":
    unittest.main()
