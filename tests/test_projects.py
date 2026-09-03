"""Tests for the Codex-style project/session data contract."""

import json
import os
import tempfile
import threading
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
    BUSY_RUN_STATES = {
        "running": {"status": "running"},
        "paused": {"status": "paused"},
        "waiting-user": {
            "status": "waiting_user_input",
            "userInputRequest": {"status": "pending"},
        },
        "waiting-authorization": {
            "status": "waiting_authorization",
            "authorizationRequest": {"status": "pending"},
        },
        "waiting-skill": {
            "status": "waiting_skill_evidence",
            "skillEvidenceRequest": {"status": "pending"},
        },
        "queued": {
            "status": "completed",
            "queuedMessages": [{"status": "pending"}],
        },
        "background": {
            "status": "completed",
            "backgroundRuns": [{"status": "running"}],
        },
    }

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

    def test_shared_secondary_roots_survive_read_write_and_reload(self):
        server.write_json(server.PROJECTS_PATH, [
            {
                "id": "project-1",
                "label": "Alpha",
                "rootPaths": [str(self.project_root), str(self.third_root)],
            },
            {
                "id": "project-2",
                "label": "Beta",
                "rootPaths": [str(self.other_root), str(self.third_root)],
            },
        ])

        projects = server._read_projects()
        server._write_projects(projects)
        reloaded = {project["id"]: project for project in server._read_projects()}

        shared_root = str(self.third_root.resolve())
        self.assertEqual(reloaded["project-1"]["rootPaths"][1], shared_root)
        self.assertEqual(reloaded["project-2"]["rootPaths"][1], shared_root)

    def test_project_storage_rejects_duplicate_primary_roots(self):
        with self.assertRaisesRegex(ValueError, "same primary source folder"):
            server._write_projects([
                {
                    "id": "project-1",
                    "label": "Alpha",
                    "rootPaths": [str(self.project_root)],
                },
                {
                    "id": "project-2",
                    "label": "Beta",
                    "rootPaths": [str(self.project_root), str(self.other_root)],
                },
            ])

    def test_primary_inference_uses_deepest_component_ancestor(self):
        nested_root = self.project_root / "nested"
        nested_leaf = nested_root / "child"
        nested_leaf.mkdir(parents=True)
        server._write_projects([
            {
                "id": "outer-project",
                "label": "Outer",
                "rootPaths": [str(self.project_root)],
            },
            {
                "id": "inner-project",
                "label": "Inner",
                "rootPaths": [str(nested_root)],
            },
        ])

        project = server._find_project_by_path(nested_leaf)
        project_id, cwd = server._import_session_location(nested_leaf)

        self.assertEqual(project["id"], "inner-project")
        self.assertEqual(project_id, "inner-project")
        self.assertEqual(cwd, str(nested_root.resolve()))

    def test_secondary_only_path_never_infers_or_creates_a_project(self):
        server._write_projects([
            {
                "id": "project-1",
                "label": "Alpha",
                "rootPaths": [str(self.project_root), str(self.third_root)],
            },
            {
                "id": "project-2",
                "label": "Beta",
                "rootPaths": [str(self.other_root), str(self.third_root)],
            },
        ])

        project_id, cwd = server._import_session_location(self.third_root)

        self.assertIsNone(server._find_project_by_path(self.third_root))
        self.assertIsNone(project_id)
        self.assertEqual(cwd, str(self.third_root.resolve()))
        self.assertEqual(len(server._read_projects()), 2)

    def test_path_ancestry_is_component_aware_and_uses_host_case_rules(self):
        child = self.project_root / "child"
        prefix_sibling = Path(str(self.project_root) + "-copy") / "child"

        self.assertTrue(server._path_is_same_or_descendant(child, self.project_root))
        self.assertFalse(
            server._path_is_same_or_descendant(prefix_sibling, self.project_root)
        )
        case_and_slash_variant = str(child).swapcase().replace("\\", "/")
        self.assertEqual(
            server._path_is_same_or_descendant(case_and_slash_variant, self.project_root),
            os.name == "nt",
        )

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

    def test_create_allows_another_secondary_as_primary_but_rejects_duplicate_primary(self):
        self.write_project(roots=[self.project_root, self.other_root])
        shared_secondary_handler = self.make_handler({
            "label": "Shared",
            "rootPaths": [str(self.other_root), str(self.third_root)],
        })

        server.CodeHandler.create_project(shared_secondary_handler)

        created = shared_secondary_handler.send_json.call_args.args[0]
        self.assertEqual(shared_secondary_handler.send_json.call_args.args[1], 201)
        self.assertEqual(created["rootPath"], str(self.other_root.resolve()))

        duplicate_primary_handler = self.make_handler({
            "label": "Duplicate",
            "rootPaths": [str(self.project_root), str(self.third_root)],
        })
        server.CodeHandler.create_project(duplicate_primary_handler)

        payload, status = duplicate_primary_handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "project_primary_conflict")

    def test_update_project_migrates_only_sessions_on_removed_roots(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-on-removed-root",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "codex",
            },
        )
        self.write_session(
            "session-on-retained-root",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
            },
        )
        handler = self.make_handler({
            "label": "Moved workspace",
            "rootPaths": [str(self.project_root), str(self.third_root)],
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
            [str(self.project_root.resolve()), str(self.third_root.resolve())],
        )
        self.assertEqual(response["rootPath"], str(self.project_root.resolve()))
        self.assertEqual(session["cwd"], str(self.project_root.resolve()))
        self.assertEqual(session["revision"], 1)
        self.assertEqual(retained_session["cwd"], str(self.project_root.resolve()))
        self.assertEqual(index_entry["cwd"], str(self.project_root.resolve()))
        self.assertEqual(server.load_config()["projectRoot"], str(self.project_root.resolve()))

    def test_assigned_project_owns_session_when_removed_root_is_another_primary(self):
        server._write_projects([
            {
                "id": "project-1",
                "label": "Workspace",
                "rootPaths": [str(self.project_root), str(self.other_root)],
            },
            {
                "id": "project-2",
                "label": "Other",
                "rootPaths": [str(self.other_root)],
            },
        ])
        server.save_config({"projectRoot": str(self.other_root)})
        self.write_session(
            "session-on-shared-root",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "revision": 2,
            },
        )
        handler = self.make_handler({
            "label": "Workspace",
            "rootPaths": [str(self.project_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        session = server.read_json(
            server.session_path("session-on-shared-root"),
            {},
        )
        self.assertEqual(session["projectId"], "project-1")
        self.assertEqual(session["cwd"], str(self.project_root.resolve()))
        self.assertEqual(session["revision"], 3)
        self.assertEqual(
            server.load_config()["projectRoot"],
            str(self.other_root.resolve()),
        )

    def test_update_project_rejects_every_busy_session_that_would_move(self):
        for suffix, run_state in self.BUSY_RUN_STATES.items():
            with self.subTest(suffix=suffix):
                self.write_project(roots=[self.project_root, self.other_root])
                server._write_session_index_payload("")
                self.write_session(
                    "session-busy-root-update",
                    {
                        "projectId": "project-1",
                        "cwd": str(self.other_root),
                        "source": "code",
                        "revision": 3,
                        "runState": run_state,
                    },
                )
                session_path = server.session_path("session-busy-root-update")
                before = {
                    "projects": server.PROJECTS_PATH.read_bytes(),
                    "session": session_path.read_bytes(),
                    "index": server._session_index_path().read_bytes(),
                    "config": server.CONFIG_PATH.read_bytes(),
                }
                handler = self.make_handler({
                    "label": "Blocked update",
                    "rootPaths": [str(self.project_root)],
                })

                server.CodeHandler.update_project(handler, "project-1")

                payload, status = handler.send_json.call_args.args
                self.assertEqual(status, 409)
                self.assertEqual(payload["errorCode"], "project_session_migration_busy")
                self.assertTrue(payload["retryable"])
                self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
                self.assertEqual(session_path.read_bytes(), before["session"])
                self.assertEqual(server._session_index_path().read_bytes(), before["index"])
                self.assertEqual(server.CONFIG_PATH.read_bytes(), before["config"])

    def test_update_project_allows_busy_session_on_a_retained_root(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-busy-retained-root",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 4,
                "runState": {"status": "running"},
            },
        )
        handler = self.make_handler({
            "label": "Retained root",
            "rootPaths": [str(self.project_root), str(self.third_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        stored = server.read_json(server.session_path("session-busy-retained-root"), {})
        self.assertEqual(handler.send_json.call_args.args[0]["label"], "Retained root")
        self.assertEqual(stored["projectId"], "project-1")
        self.assertEqual(stored["cwd"], str(self.project_root.resolve()))
        self.assertEqual(stored["revision"], 4)

    def test_update_project_write_failure_rolls_back_all_location_facts(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-project-update-rollback",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "revision": 2,
                "runState": {"status": "idle"},
            },
        )
        session_path = server.session_path("session-project-update-rollback")
        before = {
            "projects": server.PROJECTS_PATH.read_bytes(),
            "session": session_path.read_bytes(),
            "index": server._session_index_path().read_bytes(),
            "config": server.CONFIG_PATH.read_bytes(),
        }
        handler = self.make_handler({
            "label": "Rollback update",
            "rootPaths": [str(self.project_root)],
        })
        original_write_json = server.write_json

        def fail_session_write(path, payload):
            if Path(path) == session_path:
                raise OSError("synthetic project Session write failure")
            return original_write_json(path, payload)

        with mock.patch.object(server, "write_json", side_effect=fail_session_write):
            server.CodeHandler.update_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "project_session_migration_failed")
        self.assertTrue(payload["retryable"])
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(server._session_index_path().read_bytes(), before["index"])
        self.assertEqual(server.CONFIG_PATH.read_bytes(), before["config"])

    def test_reordering_without_explicit_primary_keeps_primary_and_session_bytes(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-primary-reorder",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
            },
        )
        session_path = server.session_path("session-primary-reorder")
        session_before = session_path.read_bytes()
        index_before = server._session_index_path().read_bytes()
        config_before = server.CONFIG_PATH.read_bytes()
        handler = self.make_handler({
            "label": "Reordered",
            "rootPaths": [str(self.other_root), str(self.project_root)],
        })

        server.CodeHandler.update_project(handler, "project-1")

        self.assertEqual(
            server._find_project("project-1")["rootPaths"],
            [str(self.project_root.resolve()), str(self.other_root.resolve())],
        )
        self.assertEqual(session_path.read_bytes(), session_before)
        self.assertEqual(server._session_index_path().read_bytes(), index_before)
        self.assertEqual(server.CONFIG_PATH.read_bytes(), config_before)

    def test_explicit_primary_switch_keeps_sessions_and_old_primary_as_secondary(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-primary-switch",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 7,
                "runState": {"status": "running"},
            },
        )
        session_path = server.session_path("session-primary-switch")
        before = {
            "session": session_path.read_bytes(),
            "index": server._session_index_path().read_bytes(),
            "config": server.CONFIG_PATH.read_bytes(),
        }
        handler = self.make_handler({
            "label": "Switched",
            "rootPaths": [str(self.other_root), str(self.project_root)],
            "primaryRootPath": str(self.other_root),
        })

        server.CodeHandler.update_project(handler, "project-1")

        self.assertEqual(
            handler.send_json.call_args.args[0]["rootPaths"],
            [str(self.other_root.resolve()), str(self.project_root.resolve())],
        )
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(server._session_index_path().read_bytes(), before["index"])
        self.assertEqual(server.CONFIG_PATH.read_bytes(), before["config"])

    def test_explicit_primary_switch_write_failure_restores_project_and_sessions(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-primary-switch-rollback",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 5,
            },
        )
        session_path = server.session_path("session-primary-switch-rollback")
        before = {
            "projects": server.PROJECTS_PATH.read_bytes(),
            "session": session_path.read_bytes(),
            "index": server._session_index_path().read_bytes(),
            "config": server.CONFIG_PATH.read_bytes(),
        }
        handler = self.make_handler({
            "label": "Failed switch",
            "rootPaths": [str(self.other_root), str(self.project_root)],
            "primaryRootPath": str(self.other_root),
        })
        original_write_json = server.write_json
        failed = False

        def fail_first_project_write(path, payload):
            nonlocal failed
            if Path(path) == server.PROJECTS_PATH and not failed:
                failed = True
                raise OSError("synthetic primary switch write failure")
            return original_write_json(path, payload)

        with mock.patch.object(server, "write_json", side_effect=fail_first_project_write):
            server.CodeHandler.update_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "project_session_migration_failed")
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(server._session_index_path().read_bytes(), before["index"])
        self.assertEqual(server.CONFIG_PATH.read_bytes(), before["config"])

    def test_newly_added_folder_can_become_primary_without_dropping_old_primary(self):
        self.write_project(roots=[self.project_root, self.other_root])
        handler = self.make_handler({
            "label": "Expanded",
            "rootPaths": [
                str(self.third_root),
                str(self.project_root),
                str(self.other_root),
            ],
            "primaryRootPath": str(self.third_root),
        })

        server.CodeHandler.update_project(handler, "project-1")

        self.assertEqual(
            handler.send_json.call_args.args[0]["rootPaths"],
            [
                str(self.third_root.resolve()),
                str(self.project_root.resolve()),
                str(self.other_root.resolve()),
            ],
        )

    def test_primary_switch_cannot_remove_previous_primary_in_same_update(self):
        self.write_project(roots=[self.project_root, self.other_root])
        before = server.PROJECTS_PATH.read_bytes()
        handler = self.make_handler({
            "label": "Bypass",
            "rootPaths": [str(self.other_root)],
            "primaryRootPath": str(self.other_root),
        })

        server.CodeHandler.update_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "project_primary_change_requires_explicit")
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before)

    def test_update_rejects_primary_marker_outside_requested_roots(self):
        self.write_project(roots=[self.project_root, self.other_root])
        before = server.PROJECTS_PATH.read_bytes()
        handler = self.make_handler({
            "label": "Invalid",
            "rootPaths": [str(self.project_root), str(self.other_root)],
            "primaryRootPath": str(self.third_root),
        })

        server.CodeHandler.update_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 400)
        self.assertEqual(payload["errorCode"], "project_primary_invalid")
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before)

    def test_update_allows_primary_and_secondary_roots_as_shared_secondaries(self):
        server._write_projects([
            {
                "id": "project-1",
                "label": "Workspace",
                "rootPaths": [str(self.project_root)],
            },
            {
                "id": "project-2",
                "label": "Other",
                "rootPaths": [str(self.other_root), str(self.third_root)],
            },
        ])
        handler = self.make_handler({
            "label": "Shared",
            "rootPaths": [
                str(self.project_root),
                str(self.other_root),
                str(self.third_root),
            ],
        })

        server.CodeHandler.update_project(handler, "project-1")

        self.assertEqual(handler.send_json.call_args.args[0]["label"], "Shared")
        self.assertEqual(
            server._find_project("project-1")["rootPaths"],
            [
                str(self.project_root.resolve()),
                str(self.other_root.resolve()),
                str(self.third_root.resolve()),
            ],
        )

    def test_update_rejects_another_projects_primary_as_new_primary(self):
        server._write_projects([
            {
                "id": "project-1",
                "label": "Workspace",
                "rootPaths": [str(self.project_root), str(self.third_root)],
            },
            {
                "id": "project-2",
                "label": "Other",
                "rootPaths": [str(self.other_root)],
            },
        ])
        before = server.PROJECTS_PATH.read_bytes()
        handler = self.make_handler({
            "label": "Duplicate",
            "rootPaths": [str(self.other_root), str(self.project_root), str(self.third_root)],
            "primaryRootPath": str(self.other_root),
        })

        server.CodeHandler.update_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "project_primary_conflict")
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before)
        self.assertEqual(handler.send_json.call_args.args[1], 409)
        self.assertEqual(
            server._find_project("project-1")["rootPaths"],
            [str(self.project_root.resolve()), str(self.third_root.resolve())],
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

    def test_unassign_project_ignores_selected_file_tree_root(self):
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
        self.assertEqual(stored["cwd"], str(self.project_root.resolve()))

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
        self.assertEqual(stored["revision"], 1)
        self.assertEqual(entry["source"], "claude-code")
        self.assertNotIn("project", entry)
        self.assertNotIn("group", entry)

    def test_delete_project_rejects_every_busy_attached_session_without_writes(self):
        for suffix, run_state in TestProjectSchema.BUSY_RUN_STATES.items():
            with self.subTest(suffix=suffix):
                self.write_project()
                server._write_session_index_payload("")
                self.write_session(
                    "session-busy-project-delete",
                    {
                        "projectId": "project-1",
                        "cwd": str(self.project_root),
                        "source": "code",
                        "revision": 5,
                        "runState": run_state,
                    },
                )
                session_path = server.session_path("session-busy-project-delete")
                before = {
                    "projects": server.PROJECTS_PATH.read_bytes(),
                    "session": session_path.read_bytes(),
                    "index": server._session_index_path().read_bytes(),
                    "config": server.CONFIG_PATH.read_bytes(),
                }
                handler = self.make_handler()

                server.CodeHandler.delete_project(handler, "project-1")

                payload, status = handler.send_json.call_args.args
                self.assertEqual(status, 409)
                self.assertEqual(payload["errorCode"], "project_session_migration_busy")
                self.assertTrue(payload["retryable"])
                self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
                self.assertEqual(session_path.read_bytes(), before["session"])
                self.assertEqual(server._session_index_path().read_bytes(), before["index"])
                self.assertEqual(server.CONFIG_PATH.read_bytes(), before["config"])

    def test_delete_project_rejects_a_nonterminal_agent_run_without_writes(self):
        self.write_project()
        self.write_session(
            "session-project-delete-agent-busy",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 1,
                "runState": {"status": "idle"},
            },
        )
        run = server._create_agent_run(
            "session-project-delete-agent-busy",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "test"}],
            },
            "https://gateway.example.test",
            [],
            allowed_tools=[],
            start_worker=False,
        )
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))
        session_path = server.session_path("session-project-delete-agent-busy")
        before = {
            "projects": server.PROJECTS_PATH.read_bytes(),
            "session": session_path.read_bytes(),
            "index": server._session_index_path().read_bytes(),
        }
        handler = self.make_handler()

        server.CodeHandler.delete_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "project_session_migration_busy")
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(server._session_index_path().read_bytes(), before["index"])

    def test_delete_project_write_failure_rolls_back_all_location_facts(self):
        self.write_project()
        self.write_session(
            "session-project-delete-rollback",
            {
                "projectId": "project-1",
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 2,
                "runState": {"status": "idle"},
            },
        )
        session_path = server.session_path("session-project-delete-rollback")
        before = {
            "projects": server.PROJECTS_PATH.read_bytes(),
            "session": session_path.read_bytes(),
            "index": server._session_index_path().read_bytes(),
        }
        handler = self.make_handler()

        with mock.patch.object(
            server,
            "_write_projects",
            side_effect=OSError("synthetic project catalog write failure"),
        ):
            server.CodeHandler.delete_project(handler, "project-1")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "project_session_migration_failed")
        self.assertTrue(payload["retryable"])
        self.assertEqual(server.PROJECTS_PATH.read_bytes(), before["projects"])
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(server._session_index_path().read_bytes(), before["index"])

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


class TestSessionProjectMigration(ProjectSessionTestCase):
    def test_move_uses_current_primary_root_and_advances_revision(self):
        self.write_project(
            project_id="target-project",
            roots=[self.other_root, self.third_root],
            label="Target",
        )
        self.write_session(
            "session-move-primary",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 7,
                "runState": {"status": "completed"},
            },
        )
        handler = self.make_handler({
            "projectId": "target-project",
            "cwd": str(self.third_root),
            "expectedRevision": 7,
        })

        server.CodeHandler.assign_session_project(handler, "session-move-primary")

        payload = handler.send_json.call_args.args[0]
        stored = server.read_json(server.session_path("session-move-primary"), {})
        entry = server._read_session_index()["session-move-primary"]
        target_root = str(self.other_root.resolve())
        self.assertEqual(stored["projectId"], "target-project")
        self.assertEqual(stored["cwd"], target_root)
        self.assertEqual(stored["revision"], 8)
        self.assertEqual(entry["projectId"], "target-project")
        self.assertEqual(entry["cwd"], target_root)
        self.assertEqual(payload["projectId"], "target-project")
        self.assertEqual(payload["cwd"], target_root)
        self.assertEqual(payload["revision"], 8)
        self.assertEqual(payload["session"]["revision"], 8)

    def test_stale_retry_is_idempotent_only_when_location_already_matches(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-idempotent-move",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "revision": 4,
                "runState": {"status": "idle"},
            },
        )
        retry = self.make_handler({
            "projectId": "project-1",
            "expectedRevision": 3,
        })

        server.CodeHandler.assign_session_project(retry, "session-idempotent-move")

        payload = retry.send_json.call_args.args[0]
        self.assertEqual(payload["revision"], 4)
        self.assertEqual(
            server.read_json(server.session_path("session-idempotent-move"), {})["revision"],
            4,
        )

        conflict = self.make_handler({"projectId": None, "expectedRevision": 3})
        server.CodeHandler.assign_session_project(conflict, "session-idempotent-move")
        conflict_payload, status = conflict.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(conflict_payload["errorCode"], "session_revision_conflict")
        self.assertEqual(conflict_payload["revision"], 4)
        self.assertEqual(conflict_payload["projectId"], "project-1")

    def test_move_revision_fences_a_stale_message_save(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-move-save-fence",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 2,
                "runState": {"status": "idle"},
            },
        )
        move = self.make_handler({
            "projectId": "project-1",
            "expectedRevision": 2,
        })
        server.CodeHandler.assign_session_project(move, "session-move-save-fence")

        stale_save = self.make_handler({
            "title": "Stale tab",
            "messages": [{"role": "user", "content": "stale"}],
            "expectedRevision": 2,
        })
        server.CodeHandler.save_session(stale_save, "session-move-save-fence")

        payload, status = stale_save.send_json.call_args.args
        stored = server.read_json(server.session_path("session-move-save-fence"), {})
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_revision_conflict")
        self.assertEqual(payload["currentRevision"], 3)
        self.assertEqual(stored["projectId"], "project-1")
        self.assertEqual(stored["cwd"], str(self.other_root.resolve()))
        self.assertEqual(server.read_jsonl(server.messages_path("session-move-save-fence")), [])

    def test_move_rejects_every_nonterminal_session_projection(self):
        self.write_project(root=self.other_root)
        cases = {
            "running": {"status": "running"},
            "paused": {"status": "paused"},
            "waiting-user": {
                "status": "waiting_user_input",
                "userInputRequest": {"status": "pending"},
            },
            "waiting-authorization": {
                "status": "waiting_authorization",
                "authorizationRequest": {"status": "pending"},
            },
            "waiting-skill": {
                "status": "waiting_skill_evidence",
                "skillEvidenceRequest": {"status": "pending"},
            },
            "queued": {
                "status": "completed",
                "queuedMessages": [{"status": "pending"}],
            },
            "background": {
                "status": "completed",
                "backgroundRuns": [{"status": "running"}],
            },
        }
        for suffix, run_state in cases.items():
            with self.subTest(suffix=suffix):
                session_id = f"session-busy-{suffix}"
                self.write_session(
                    session_id,
                    {
                        "projectId": None,
                        "cwd": str(self.project_root),
                        "source": "code",
                        "revision": 2,
                        "runState": run_state,
                    },
                )
                handler = self.make_handler({
                    "projectId": "project-1",
                    "expectedRevision": 2,
                })

                server.CodeHandler.assign_session_project(handler, session_id)

                payload, status = handler.send_json.call_args.args
                self.assertEqual(status, 409)
                self.assertEqual(payload["errorCode"], "session_project_migration_busy")
                self.assertTrue(payload["retryable"])
                stored = server.read_json(server.session_path(session_id), {})
                self.assertIsNone(stored["projectId"])
                self.assertEqual(stored["revision"], 2)

        self.write_session(
            "session-busy-same-location",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "revision": 5,
                "runState": {"status": "running"},
            },
        )
        same_location = self.make_handler({
            "projectId": "project-1",
            "expectedRevision": 5,
        })
        server.CodeHandler.assign_session_project(
            same_location,
            "session-busy-same-location",
        )
        payload, status = same_location.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_project_migration_busy")

    def test_move_rejects_a_durable_nonterminal_agent_run(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-agent-busy",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 0,
                "runState": {"status": "idle"},
            },
        )
        run = server._create_agent_run(
            "session-agent-busy",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "test"}],
            },
            "https://gateway.example.test",
            [],
            allowed_tools=[],
            start_worker=False,
        )
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))
        handler = self.make_handler({"projectId": "project-1", "expectedRevision": 0})

        server.CodeHandler.assign_session_project(handler, "session-agent-busy")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "session_project_migration_busy")
        self.assertIsNone(
            server.read_json(server.session_path("session-agent-busy"), {})["projectId"]
        )

    def test_index_failure_rolls_back_session_and_index_together(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-move-rollback",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 3,
                "runState": {"status": "idle"},
            },
        )
        session_path = server.session_path("session-move-rollback")
        index_path = server._session_index_path()
        before = {
            "session": session_path.read_bytes(),
            "index": index_path.read_bytes(),
        }
        handler = self.make_handler({
            "projectId": "project-1",
            "expectedRevision": 3,
        })

        with mock.patch.object(
            server,
            "_write_session_index_from_meta",
            side_effect=OSError("synthetic index failure"),
        ):
            server.CodeHandler.assign_session_project(handler, "session-move-rollback")

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 503)
        self.assertEqual(payload["errorCode"], "session_project_migration_failed")
        self.assertTrue(payload["retryable"])
        self.assertEqual(session_path.read_bytes(), before["session"])
        self.assertEqual(index_path.read_bytes(), before["index"])

    def test_rollback_failure_is_sanitized_and_nonretryable(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-move-recovery-failure",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 1,
                "runState": {"status": "idle"},
            },
        )
        handler = self.make_handler({
            "projectId": "project-1",
            "expectedRevision": 1,
        })
        sentinel = str(self.data_dir / "PRIVATE-SENTINEL")

        with mock.patch.object(
            server,
            "_write_session_index_from_meta",
            side_effect=OSError("synthetic index failure"),
        ), mock.patch.object(
            server,
            "_restore_path_snapshot",
            side_effect=PermissionError(sentinel),
        ):
            server.CodeHandler.assign_session_project(
                handler,
                "session-move-recovery-failure",
            )

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 500)
        self.assertEqual(
            payload["errorCode"],
            "session_project_migration_recovery_failed",
        )
        self.assertFalse(payload["retryable"])
        self.assertNotIn(sentinel, json.dumps(payload))

    def test_agent_run_reloads_workspace_when_move_wins_admission_race(self):
        self.write_project(root=self.other_root)
        self.write_session(
            "session-run-race",
            {
                "projectId": None,
                "cwd": str(self.project_root),
                "source": "code",
                "revision": 0,
                "runState": {"status": "idle"},
            },
        )
        first_resolution_complete = threading.Event()
        release_admission = threading.Event()
        original_workspace = server._agent_run_workspace
        calls = []

        def gated_workspace(*args, **kwargs):
            result = original_workspace(*args, **kwargs)
            calls.append(result)
            if len(calls) == 1:
                first_resolution_complete.set()
                self.assertTrue(release_admission.wait(timeout=5))
            return result

        outcome = {}

        def create_run():
            try:
                outcome["run"] = server._create_agent_run(
                    "session-run-race",
                    {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "test"}],
                    },
                    "https://gateway.example.test",
                    [],
                    allowed_tools=[],
                    start_worker=False,
                )
            except Exception as exc:  # surfaced by the assertions below
                outcome["error"] = exc

        with mock.patch.object(server, "_agent_run_workspace", side_effect=gated_workspace):
            thread = threading.Thread(target=create_run)
            thread.start()
            self.assertTrue(first_resolution_complete.wait(timeout=5))
            handler = self.make_handler({
                "projectId": "project-1",
                "expectedRevision": 0,
            })
            server.CodeHandler.assign_session_project(handler, "session-run-race")
            release_admission.set()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", outcome)
        run = outcome["run"]
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(run["cwd"], str(self.other_root.resolve()))
        self.assertEqual(run["workspace_roots"], [str(self.other_root.resolve())])


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
    def create_run_across_location_mutation(self, session_id, mutate):
        first_resolution_complete = threading.Event()
        release_admission = threading.Event()
        original_workspace = server._agent_run_workspace
        calls = []
        outcome = {}

        def gated_workspace(*args, **kwargs):
            result = original_workspace(*args, **kwargs)
            calls.append(result)
            if len(calls) == 1:
                first_resolution_complete.set()
                self.assertTrue(release_admission.wait(timeout=5))
            return result

        def create_run():
            try:
                outcome["run"] = server._create_agent_run(
                    session_id,
                    {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "test"}],
                    },
                    "https://gateway.example.test",
                    [],
                    allowed_tools=[],
                    start_worker=False,
                )
            except Exception as exc:
                outcome["error"] = exc

        with mock.patch.object(server, "_agent_run_workspace", side_effect=gated_workspace):
            thread = threading.Thread(target=create_run)
            thread.start()
            self.assertTrue(first_resolution_complete.wait(timeout=5))
            mutate()
            release_admission.set()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", outcome)
        self.assertGreaterEqual(len(calls), 2)
        run = outcome["run"]
        self.addCleanup(lambda: server._agent_runs.pop(run["id"], None))
        return run

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

    def test_agent_run_reloads_workspace_when_project_root_update_wins_race(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-project-update-race",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "runState": {"status": "idle"},
            },
        )

        def update_project():
            handler = self.make_handler({
                "label": "Updated",
                "rootPaths": [str(self.project_root), str(self.third_root)],
            })
            server.CodeHandler.update_project(handler, "project-1")

        run = self.create_run_across_location_mutation(
            "session-project-update-race",
            update_project,
        )

        self.assertEqual(run["cwd"], str(self.project_root.resolve()))
        self.assertEqual(
            run["workspace_roots"],
            [str(self.project_root.resolve()), str(self.third_root.resolve())],
        )

    def test_agent_run_reloads_workspace_when_project_delete_wins_race(self):
        self.write_project(roots=[self.project_root, self.other_root])
        self.write_session(
            "session-project-delete-race",
            {
                "projectId": "project-1",
                "cwd": str(self.other_root),
                "source": "code",
                "runState": {"status": "idle"},
            },
        )

        def delete_project():
            handler = self.make_handler()
            server.CodeHandler.delete_project(handler, "project-1")

        run = self.create_run_across_location_mutation(
            "session-project-delete-race",
            delete_project,
        )

        self.assertEqual(run["cwd"], str(self.other_root.resolve()))
        self.assertEqual(run["workspace_roots"], [str(self.other_root.resolve())])


if __name__ == "__main__":
    unittest.main()
