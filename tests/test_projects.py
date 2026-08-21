"""Tests for the Codex-style project/session data contract."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server


class ProjectSessionTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="code-projects-")
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)
        self.sessions_dir = self.data_dir / "sessions"
        self.sessions_dir.mkdir()
        self.project_root = self.data_dir / "workspace"
        self.project_root.mkdir()
        self.other_root = self.data_dir / "other"
        self.other_root.mkdir()
        self.third_root = self.data_dir / "third"
        self.third_root.mkdir()

        self.patchers = [
            mock.patch.object(server, "DATA_DIR", self.data_dir),
            mock.patch.object(server, "SESSIONS_DIR", self.sessions_dir),
            mock.patch.object(server, "PROJECTS_PATH", self.data_dir / "projects.json"),
            mock.patch.object(
                server,
                "PROJECTS_MIGRATION_FLAG",
                self.data_dir / ".codex_projects_migrated",
            ),
            mock.patch.object(
                server,
                "PROJECT_ROOTS_MIGRATION_FLAG",
                self.data_dir / ".codex_project_roots_migrated",
            ),
            mock.patch.object(server, "CONFIG_PATH", self.data_dir / "config.json"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        server.write_json(server.CONFIG_PATH, {"projectRoot": str(self.project_root)})

    def make_handler(self, body=None):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body or {})
        handler.send_json = mock.Mock()
        return handler

    def write_project(
        self,
        project_id="project-1",
        root=None,
        roots=None,
        label="Workspace",
    ):
        project = {
            "id": project_id,
            "label": label,
            "rootPaths": [
                str(path) for path in (roots or [root or self.project_root])
            ],
        }
        server._write_projects([project])
        return server._find_project(project_id)

    def write_session(self, session_id, meta, index_entry=None):
        date_dir = self.sessions_dir / "2026" / "07" / "20"
        date_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": session_id,
            "title": "Session",
            "createdAt": "2026-07-20T10:00:00",
            "updatedAt": "2026-07-20T10:00:00",
            "messageCount": 0,
            **meta,
        }
        server.write_json(date_dir / f"{session_id}.json", payload)
        server.write_jsonl(date_dir / f"{session_id}.jsonl", [])
        if index_entry is not False:
            entry = index_entry or {
                "id": session_id,
                "title": payload["title"],
                "updatedAt": payload["updatedAt"],
                "messageCount": payload["messageCount"],
                "_parentId": payload.get("_parentId"),
                "_branchDepth": payload.get("_branchDepth", 0),
                "projectId": payload.get("projectId"),
                "cwd": payload.get("cwd", ""),
                "source": payload.get("source", "code"),
            }
            with open(server._session_index_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return payload


class TestProjectSchema(ProjectSessionTestCase):
    def test_legacy_records_are_normalized_and_magic_project_is_removed(self):
        server.write_json(server.PROJECTS_PATH, [
            {
                "id": "__unclassified__",
                "name": "Sessions",
                "rootPath": str(self.other_root),
            },
            {
                "id": "legacy-project",
                "name": "Legacy",
                "rootPath": str(self.project_root),
                "createdAt": "2026-07-20T10:00:00",
            },
        ])

        projects = server._read_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], "legacy-project")
        self.assertEqual(projects[0]["label"], "Legacy")
        self.assertEqual(projects[0]["rootPaths"], [str(self.project_root.resolve())])
        self.assertNotIn("path", projects[0])
        self.assertNotIn("name", projects[0])
        self.assertNotIn("rootPath", projects[0])

    def test_project_storage_is_canonical_but_api_keeps_temporary_aliases(self):
        project = self.write_project()
        stored = server.read_json(server.PROJECTS_PATH, [])[0]
        api_record = server._project_api_record(project)

        self.assertEqual(
            set(stored),
            {"id", "label", "rootPaths"},
        )
        self.assertEqual(api_record["rootPaths"], [str(self.project_root.resolve())])
        self.assertEqual(api_record["name"], api_record["label"])
        self.assertEqual(api_record["rootPath"], api_record["path"])

    def test_ensure_project_for_path_is_idempotent(self):
        first = server._ensure_project_for_path(self.project_root)
        second = server._ensure_project_for_path(self.project_root)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(server._read_projects()), 1)

    def test_import_location_creates_project_only_for_existing_cwd(self):
        project_id, cwd = server._import_session_location(self.project_root)
        missing_id, missing_cwd = server._import_session_location(
            self.data_dir / "missing"
        )

        self.assertIsNotNone(project_id)
        self.assertEqual(cwd, str(self.project_root.resolve()))
        self.assertIsNone(missing_id)
        self.assertEqual(missing_cwd, str((self.data_dir / "missing").resolve()))
        self.assertEqual(len(server._read_projects()), 1)

    def test_session_location_accepts_attached_roots_and_rejects_other_folders(self):
        self.write_project(roots=[self.project_root, self.other_root])

        project_id, secondary_cwd = server._session_location(
            "project-1",
            self.other_root,
        )
        self.assertEqual(project_id, "project-1")
        self.assertEqual(secondary_cwd, str(self.other_root.resolve()))

        with self.assertRaisesRegex(ValueError, "source folders"):
            server._session_location("project-1", self.third_root)

        project_id, cwd = server._session_location("project-1", None)
        self.assertEqual(project_id, "project-1")
        self.assertEqual(cwd, str(self.project_root.resolve()))

    def test_create_and_rename_project_accept_new_and_legacy_field_names(self):
        create_handler = self.make_handler({
            "path": str(self.project_root),
            "label": "Code",
        })
        server.CodeHandler.create_project(create_handler)
        created = create_handler.send_json.call_args.args[0]

        self.assertEqual(create_handler.send_json.call_args.args[1], 201)
        self.assertEqual(created["label"], "Code")
        self.assertEqual(created["name"], "Code")
        self.assertEqual(created["path"], str(self.project_root.resolve()))
        self.assertEqual(created["rootPaths"], [str(self.project_root.resolve())])

        rename_handler = self.make_handler({"name": "Renamed"})
        server.CodeHandler.rename_project(rename_handler, created["id"])
        renamed = rename_handler.send_json.call_args.args[0]

        self.assertEqual(renamed["label"], "Renamed")
        self.assertEqual(server._find_project(created["id"])["label"], "Renamed")

    def test_update_project_migrates_only_sessions_on_removed_roots(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-on-removed-root",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "codex",
            },
        )
        self.write_session(
            "session-on-retained-root",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
            },
        )
        handler = self.make_handler({
            "label": "Moved workspace",
            "rootPaths": [str(self.other_root), str(self.third_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        response = handler.send_json.call_args.args[0]
        project = server._find_project("project-1")
        session = server.read_json(
            server.session_path("session-on-removed-root"),
            {},
        )
        retained_session = server.read_json(
            server.session_path("session-on-retained-root"),
            {},
        )
        index_entry = server._read_session_index()["session-on-removed-root"]
        self.assertEqual(project["label"], "Moved workspace")
        self.assertEqual(
            project["rootPaths"],
            [str(self.other_root.resolve()), str(self.third_root.resolve())],
        )
        self.assertEqual(response["rootPath"], str(self.other_root.resolve()))
        self.assertEqual(session["cwd"], str(self.other_root.resolve()))
        self.assertEqual(retained_session["cwd"], str(self.other_root.resolve()))
        self.assertEqual(index_entry["cwd"], str(self.other_root.resolve()))
        self.assertEqual(server.load_config()["projectRoot"], str(self.other_root.resolve()))

    def test_reordering_primary_preserves_session_cwds_and_active_config(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-primary-reorder",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
            },
        )
        handler = self.make_handler({
            "label": "Reordered",
            "rootPaths": [str(self.other_root), str(self.project_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        session = server.read_json(server.session_path("session-primary-reorder"), {})
        self.assertEqual(session["cwd"], str(self.project_root.resolve()))
        self.assertEqual(server.load_config()["projectRoot"], str(self.project_root.resolve()))
        self.assertEqual(
            server._find_project("project-1")["rootPaths"],
            [str(self.other_root.resolve()), str(self.project_root.resolve())],
        )

    def test_update_project_rejects_a_source_folder_used_by_another_project(self):
        server._write_projects([
            {
                "id": "project-1",
                "label": "Workspace",
                "rootPaths": [str(self.project_root)],
            },
            {
                "id": "project-2",
                "label": "Other",
                "rootPaths": [str(self.other_root)],
            },
        ])
        handler = self.make_handler({
            "label": "Duplicate",
            "rootPaths": [str(self.other_root), str(self.third_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        self.assertEqual(handler.send_json.call_args.args[1], 409)
        self.assertEqual(
            server._find_project("project-1")["rootPaths"],
            [str(self.project_root.resolve())],
        )

    def test_project_folder_picker_starts_from_the_project_source_folder(self):
        handler = self.make_handler()
        with mock.patch.object(
            server,
            "open_native_folder_picker",
            return_value=None,
        ) as picker:
            server.CodeHandler.pick_folder(handler, str(self.other_root))

        picker.assert_called_once_with(self.other_root.resolve())
        self.assertEqual(
            handler.send_json.call_args.args[0],
            {"cancelled": True},
        )


class TestSessionContract(ProjectSessionTestCase):
    def test_index_writer_uses_project_id_cwd_and_source_only(self):
        server._write_session_index_entry(
            "session001",
            "Test",
            "2026-07-20T10:00:00",
            2,
            project_id="project-1",
            cwd=self.project_root,
            source="codex",
        )

        entry = server._read_session_index()["session001"]
        self.assertEqual(entry["projectId"], "project-1")
        self.assertEqual(entry["cwd"], str(self.project_root.resolve()))
        self.assertEqual(entry["source"], "codex")
        self.assertFalse(entry["sourceBadgeVisible"])
        self.assertNotIn("project", entry)
        self.assertNotIn("group", entry)

    def test_session_list_does_not_resolve_each_index_entry_with_session_path(self):
        self.write_session("session-fast-a", {"source": "code"})
        self.write_session("session-fast-b", {"source": "code"})
        handler = self.make_handler()

        with mock.patch.object(
            server,
            "session_path",
            side_effect=AssertionError("session list must use one metadata snapshot"),
        ):
            server.CodeHandler.get_sessions(handler)

        listed_ids = {
            item["id"]
            for item in handler.send_json.call_args.args[0]["data"]
        }
        self.assertEqual(listed_ids, {"session-fast-a", "session-fast-b"})

    def test_session_list_snapshot_keeps_flat_legacy_metadata_compatible(self):
        session_id = "legacy-flat-session"
        server.write_json(
            self.sessions_dir / f"{session_id}.json",
            {
                "id": session_id,
                "title": "Legacy flat",
                "createdAt": "2026-07-19T10:00:00",
                "updatedAt": "2026-07-19T10:00:00",
                "messageCount": 0,
                "source": "code",
            },
        )
        server._write_session_index_entry(
            session_id,
            "Legacy flat",
            "2026-07-19T10:00:00",
            0,
            source="code",
        )
        handler = self.make_handler()

        server.CodeHandler.get_sessions(handler)

        listed_ids = {
            item["id"]
            for item in handler.send_json.call_args.args[0]["data"]
        }
        self.assertIn(session_id, listed_ids)

    def test_session_list_backfills_pristine_import_badge_state(self):
        self.write_session(
            "session-imported",
            {
                "source": "claude-code",
                "importState": {
                    "source": "claude-code",
                    "codeModified": False,
                },
            },
        )
        handler = self.make_handler()

        server.CodeHandler.get_sessions(handler)

        response = handler.send_json.call_args.args[0]
        listed = next(
            item for item in response["data"]
            if item["id"] == "session-imported"
        )
        self.assertTrue(listed["sourceBadgeVisible"])
        self.assertTrue(
            server._read_session_index()["session-imported"]["sourceBadgeVisible"]
        )

    def test_first_code_message_hides_import_badge_and_keeps_source(self):
        original_messages = [
            {
                "role": "system",
                "content": "Imported boundary",
                "meta": {"_system": True, "kind": "import-boundary"},
            },
            {"role": "user", "content": "Imported request"},
        ]
        snapshot_hash = server._import_message_snapshot_hash(original_messages)
        self.write_session(
            "session-continued",
            {
                "source": "codex",
                "messageCount": len(original_messages),
                "importState": {
                    "source": "codex",
                    "snapshotSha256": snapshot_hash,
                    "codeModified": False,
                },
            },
            index_entry=False,
        )
        server.write_jsonl(
            server.messages_path("session-continued"),
            original_messages,
        )
        server._write_session_index_entry(
            "session-continued",
            "Session",
            "2026-07-20T10:00:00",
            len(original_messages),
            source="codex",
            source_badge_visible=True,
        )
        continued_messages = [
            *original_messages,
            {"role": "user", "content": "Continue in Code"},
        ]
        handler = self.make_handler({
            "title": "Session",
            "messages": continued_messages,
        })

        server.CodeHandler.save_session(handler, "session-continued")

        response = handler.send_json.call_args.args[0]
        stored = server.read_json(
            server.session_path("session-continued"),
            {},
        )
        index_entry = server._read_session_index()["session-continued"]
        self.assertEqual(response["source"], "codex")
        self.assertFalse(response["sourceBadgeVisible"])
        self.assertTrue(stored["importState"]["codeModified"])
        self.assertFalse(index_entry["sourceBadgeVisible"])

    def test_create_and_save_session_persist_canonical_context(self):
        self.write_project()
        create_handler = self.make_handler({
            "title": "New",
            "projectId": "project-1",
            "messages": [],
        })
        server.CodeHandler.create_session(create_handler)
        created = create_handler.send_json.call_args.args[0]
        session_id = created["id"]
        stored = server.read_json(server.session_path(session_id), {})

        self.assertEqual(stored["projectId"], "project-1")
        self.assertEqual(stored["cwd"], str(self.project_root.resolve()))
        self.assertEqual(stored["source"], "code")
        self.assertNotIn("group", stored)

        save_handler = self.make_handler({"title": "Imported", "group": "Codex"})
        server.CodeHandler.save_session(save_handler, session_id)
        saved = server.read_json(server.session_path(session_id), {})
        index_entry = server._read_session_index()[session_id]

        self.assertEqual(saved["source"], "codex")
        self.assertEqual(save_handler.send_json.call_args.args[0]["group"], "Codex")
        self.assertNotIn("group", saved)
        self.assertNotIn("group", index_entry)

    def test_assign_and_unassign_project_moves_then_preserves_cwd(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session002",
            {"projectId": None, "cwd": str(self.project_root), "source": "code"},
        )

        assign_handler = self.make_handler({"projectId": "project-1"})
        server.CodeHandler.assign_session_project(assign_handler, "session002")
        assigned = server.read_json(server.session_path("session002"), {})
        self.assertEqual(assigned["projectId"], "project-1")
        self.assertEqual(assigned["cwd"], str(self.other_root.resolve()))

        unassign_handler = self.make_handler({"projectId": None})
        server.CodeHandler.assign_session_project(unassign_handler, "session002")
        unassigned = server.read_json(server.session_path("session002"), {})
        self.assertIsNone(unassigned["projectId"])
        self.assertEqual(unassigned["cwd"], str(self.other_root.resolve()))

    def test_unassign_project_can_move_session_to_selected_file_tree_root(self):
        self.write_project()
        self.write_session(
            "session-unassign-cwd",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
            },
        )
        handler = self.make_handler({
            "projectId": None,
            "cwd": str(self.third_root),
        })

        server.CodeHandler.assign_session_project(handler, "session-unassign-cwd")

        stored = server.read_json(server.session_path("session-unassign-cwd"), {})
        self.assertIsNone(stored["projectId"])
        self.assertEqual(stored["cwd"], str(self.third_root.resolve()))

    def test_delete_project_unassigns_sessions_without_losing_cwd(self):
        self.write_project()
        self.write_session(
            "session003",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "claude-code",
            },
        )
        handler = self.make_handler()

        server.CodeHandler.delete_project(handler, "project-1")

        stored = server.read_json(server.session_path("session003"), {})
        entry = server._read_session_index()["session003"]
        self.assertEqual(server._read_projects(), [])
        self.assertIsNone(stored["projectId"])
        self.assertEqual(stored["cwd"], str(self.project_root.resolve()))
        self.assertEqual(entry["source"], "claude-code")
        self.assertNotIn("project", entry)
        self.assertNotIn("group", entry)

    def test_branch_inherits_project_cwd_and_source(self):
        self.write_project()
        self.write_session(
            "session004",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "codex",
                "messageCount": 0,
                "importState": {
                    "source": "codex",
                    "codeModified": False,
                },
            },
        )
        handler = self.make_handler({"title": "Branch"})

        server.CodeHandler.branch_session(handler, "session004")

        child = handler.send_json.call_args.args[0]
        stored = server.read_json(server.session_path(child["id"]), {})
        self.assertEqual(stored["projectId"], "project-1")
        self.assertEqual(stored["cwd"], str(self.project_root.resolve()))
        self.assertEqual(stored["source"], "codex")
        self.assertFalse(child["sourceBadgeVisible"])
        self.assertFalse(
            server._read_session_index()[child["id"]]["sourceBadgeVisible"]
        )
        self.assertTrue(
            server._read_session_index()["session004"]["sourceBadgeVisible"]
        )
        self.assertNotIn("group", stored)


class TestProjectMigration(ProjectSessionTestCase):
    def test_migration_normalizes_legacy_data_and_indexes_unindexed_sessions(self):
        server.write_json(server.PROJECTS_PATH, [
            {
                "id": "project-1",
                "name": "Legacy",
                "rootPath": str(self.project_root),
                "createdAt": "2026-07-20T10:00:00",
            },
            {
                "id": "__unclassified__",
                "name": "Sessions",
                "rootPath": str(self.other_root),
            },
        ])
        self.write_session(
            "session005",
            {"projectId": "project-1", "group": "Codex"},
            index_entry={
                "id": "session005",
                "title": "Indexed",
                "updatedAt": "2026-07-20T10:00:00",
                "messageCount": 0,
                "project": "project-1",
                "group": "Codex",
            },
        )
        self.write_session(
            "session006",
            {"group": "Claude Code"},
            index_entry=False,
        )

        first_result = server._migrate_codex_project_sessions_support()
        second_result = server._migrate_codex_project_sessions_support()

        codex_meta = server.read_json(server.session_path("session005"), {})
        claude_meta = server.read_json(server.session_path("session006"), {})
        index = server._read_session_index()
        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertTrue(server.PROJECTS_MIGRATION_FLAG.exists())
        self.assertEqual([project["id"] for project in server._read_projects()], ["project-1"])
        self.assertEqual(codex_meta["projectId"], "project-1")
        self.assertEqual(codex_meta["cwd"], str(self.project_root.resolve()))
        self.assertEqual(codex_meta["source"], "codex")
        self.assertEqual(claude_meta["source"], "claude-code")
        self.assertEqual(claude_meta["cwd"], str(self.project_root.resolve()))
        self.assertEqual(set(index), {"session005", "session006"})
        for meta in (codex_meta, claude_meta):
            self.assertNotIn("group", meta)
        for entry in index.values():
            self.assertIn("projectId", entry)
            self.assertIn("cwd", entry)
            self.assertIn("source", entry)
            self.assertNotIn("project", entry)
            self.assertNotIn("group", entry)

    def test_multi_folder_migration_persists_root_paths_once(self):
        server.write_json(server.PROJECTS_PATH, [{
            "id": "legacy-project",
            "label": "Legacy",
            "path": str(self.project_root),
        }])

        first_result = server._migrate_project_root_paths()
        second_result = server._migrate_project_root_paths()

        stored = server.read_json(server.PROJECTS_PATH, [])
        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertTrue(server.PROJECT_ROOTS_MIGRATION_FLAG.exists())
        self.assertEqual(stored, [{
            "id": "legacy-project",
            "label": "Legacy",
            "rootPaths": [str(self.project_root.resolve())],
        }])


class TestAgentRunWorkspace(ProjectSessionTestCase):
    def test_agent_run_uses_session_cwd_and_attached_project_roots(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-agent-workspace",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
            },
        )
        run = server._create_agent_run(
            "session-agent-workspace",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "test"}],
            },
            "https://gateway.example.test",
            [],
            allowed_tools=[],
            start_worker=False,
            cwd=str(self.third_root),
        )
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))

        snapshot = server._agent_snapshot(run)
        record = server._agent_run_record(run)
        restored = server._agent_run_from_record(record)

        self.assertEqual(run["cwd"], str(self.other_root.resolve()))
        self.assertEqual(
            run["workspace_roots"],
            [str(self.project_root.resolve()), str(self.other_root.resolve())],
        )
        self.assertEqual(snapshot["cwd"], str(self.other_root.resolve()))
        self.assertEqual(restored["cwd"], str(self.other_root.resolve()))
        self.assertEqual(restored["workspace_roots"], run["workspace_roots"])

    def test_background_tool_resolves_relative_paths_from_captured_session_cwd(self):
        (self.other_root / "secondary-only.txt").write_text("secondary", encoding="utf-8")
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-agent-tool-root",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
            },
        )
        run = server._create_agent_run(
            "session-agent-tool-root",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "list"}],
            },
            "https://gateway.example.test",
            [],
            allowed_tools=["list_files"],
            start_worker=False,
        )
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))
        run["pending_tool_calls"] = server._normalize_agent_tool_calls(
            run,
            [{
                "id": "call-list-secondary",
                "type": "function",
                "function": {"name": "list_files", "arguments": {"path": ""}},
            }],
            1,
        )

        completed = server._execute_agent_pending_tools(run)

        result = run["tool_executions"]["call-list-secondary"]["result"]
        self.assertTrue(completed)
        self.assertIn(
            "secondary-only.txt",
            [item["name"] for item in result["items"]],
        )


if __name__ == "__main__":
    unittest.main()
