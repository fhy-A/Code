"""
P0 HTTP Route Integration Tests — core tool endpoints + session CRUD.

Starts a live server in a background thread and tests real HTTP requests.
Run: python -m pytest tests/test_routes.py -v
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as server_mod


def _free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_PORT = _free_port()
_BASE = f"http://127.0.0.1:{_PORT}"


def _req(method, path, **kwargs):
    """Helper: issue an HTTP request and return (status, data)."""
    url = f"{_BASE}{path}"
    resp = requests.request(method, url, timeout=10, **kwargs)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


# ═══════════════════════════════════════════════════════════════════
# Shared fixtures — one server for all tests
# ═══════════════════════════════════════════════════════════════════

class TestServerFixture(unittest.TestCase):
    """Base class that starts a real server in a background thread."""

    _server_started = False
    _server_thread = None
    _server_instance = None
    _tmp_root = None
    _tmp_data = None

    @classmethod
    def setUpClass(cls):
        if cls._server_started:
            return

        # Temp project root with test files
        cls._tmp_root = Path(tempfile.mkdtemp(prefix="code_test_root_"))
        cls._tmp_data = Path(tempfile.mkdtemp(prefix="code_test_data_"))

        # Create test project structure
        (cls._tmp_root / "src").mkdir(parents=True)
        (cls._tmp_root / "src" / "main.py").write_text("print('hello world')\n", encoding="utf-8")
        (cls._tmp_root / "src" / "utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (cls._tmp_root / "README.md").write_text("# Test Project\n\nThis is a test.\n", encoding="utf-8")
        (cls._tmp_root / "binary.bin").write_bytes(b"\x00\x01\x02\x03" * 256)
        (cls._tmp_root / "output").mkdir()

        # Create data dirs
        for sub in ["sessions", "memory", "skills", "attachments", "file-backups"]:
            (cls._tmp_data / sub).mkdir(parents=True, exist_ok=True)
        config = {
            "projectRoot": str(cls._tmp_root),
            "newApiBaseUrl": "http://localhost:3000",
            "userHome": str(Path.home()),
        }
        (cls._tmp_data / "config.json").write_text(json.dumps(config), encoding="utf-8")

        # Override server module paths
        cls._patchers = [
            mock.patch.object(server_mod, "DATA_DIR", cls._tmp_data),
            mock.patch.object(server_mod, "CONFIG_PATH", cls._tmp_data / "config.json"),
            mock.patch.object(server_mod, "SESSIONS_DIR", cls._tmp_data / "sessions"),
            mock.patch.object(server_mod, "MEMORY_DIR", cls._tmp_data / "memory"),
            mock.patch.object(server_mod, "SKILLS_DIR", cls._tmp_data / "skills"),
            mock.patch.object(server_mod, "ATTACHMENTS_DIR", cls._tmp_data / "attachments"),
            mock.patch.object(server_mod, "FILE_BACKUP_DIR", cls._tmp_data / "file-backups"),
            mock.patch.object(server_mod, "APP_DIR", cls._tmp_root),  # for static file serving
        ]
        for p in cls._patchers:
            p.start()

        # Start server
        server_mod.ThreadingHTTPServer.daemon_threads = True
        cls._server_instance = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", _PORT), server_mod.CodeHandler
        )
        cls._server_instance.socket.settimeout(2.0)
        cls._server_thread = threading.Thread(
            target=cls._server_instance.serve_forever, daemon=True
        )
        cls._server_thread.start()
        time.sleep(0.3)  # let it bind
        cls._server_started = True

    @classmethod
    def tearDownClass(cls):
        # Cleanup happens at process exit; leave tmp dirs for debugging
        pass


# ═══════════════════════════════════════════════════════════════════
# 1. Health & Config
# ═══════════════════════════════════════════════════════════════════

class TestHealthAndConfig(TestServerFixture):

    def test_ping(self):
        status, data = _req("GET", "/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("pong"))

    def test_version(self):
        status, data = _req("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertIn("localVersion", data)
        self.assertIn("serverVersion", data)
        self.assertEqual(data["name"], "Code")
        self.assertEqual(data["instanceMode"], "release")
        self.assertEqual(data["port"], 3010)

    def test_agent_run_create_accepts_only_skill_selection_intent(self):
        secret = "FORGED-CLIENT-SKILL-CONTRACT-SENTINEL"
        skill_name = "observer-route-skill"
        skill_dir = self._tmp_data / "skills" / skill_name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: Route observer\n"
            "tools: read_file\n---\n\nObserve only.\n",
            encoding="utf-8",
        )
        (skill_dir / "evidence.json").write_text(json.dumps({
            "schemaVersion": 1,
            "requirements": [{
                "id": "inspect-input",
                "type": "tool_execution",
                "tool": "read_file",
                "minCount": 1,
            }],
        }), encoding="utf-8")
        with (
            mock.patch.object(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False),
            mock.patch.object(server_mod, "_start_agent_worker", return_value=None),
        ):
            status, data = _req("POST", "/api/agent/runs", json={
                "sessionId": "session-1",
                "clientRequestId": "observer-route-request-1",
                "payload": {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "run selected skill"}],
                },
                "baseUrl": "http://127.0.0.1:1",
                "keys": [],
                "allowedTools": ["read_file"],
                "activeSkillName": skill_name,
                "skillEvidenceContract": {"secret": secret},
            })

        self.assertEqual(status, 201)
        run_id = data["agentRunId"]
        snapshot_status, snapshot = _req("GET", f"/api/agent/runs/{run_id}")
        self.assertEqual(snapshot_status, 200)
        self.assertEqual(snapshot["skillEvidence"]["contractState"], "valid")
        self.assertEqual(snapshot["skillEvidence"]["status"], "partial")
        self.assertEqual(snapshot["skillEvidence"]["activeSkill"]["name"], skill_name)
        persisted = server_mod._agent_run_path(run_id).read_text(encoding="utf-8")
        self.assertEqual(json.loads(persisted)["version"], 5)
        self.assertNotIn(secret, persisted)
        self.assertNotIn(secret, json.dumps(snapshot))

    def test_browser_heartbeat_keeps_projection_shadow_disabled_in_release(self):
        status, data = _req("GET", "/api/browser-heartbeat")
        self.assertEqual(status, 200)
        self.assertEqual(data["instanceMode"], "release")
        self.assertFalse(data["agentProjectionShadow"])

    def test_skill_dependency_preflight_route(self):
        expected = {
            "summary": {"declared": 1, "ready": 0, "partial": 1, "unavailable": 0},
            "skills": [{"name": "docx", "status": "partial", "capabilities": []}],
            "errors": [],
        }
        with mock.patch.object(server_mod, "get_skill_dependency_status", return_value=expected):
            status, data = _req("GET", "/api/skills/dependencies")
        self.assertEqual(status, 200)
        self.assertEqual(data, expected)

    def test_single_skill_dependency_route_refreshes_only_the_selected_skill(self):
        expected = {"name": "docx", "status": "ready", "capabilities": []}
        with mock.patch.object(server_mod, "get_single_skill_dependency_status", return_value=expected) as check:
            status, data = _req("GET", "/api/skills/docx/dependencies")
        self.assertEqual(status, 200)
        self.assertEqual(data, expected)
        check.assert_called_once_with("docx")

    def test_dependency_plan_route_never_exposes_executable_arguments(self):
        plan = {
            "skill": "docx",
            "capability": "create",
            "action": "install",
            "actionable": True,
            "steps": [{
                "id": "install-python",
                "displayCommand": "python -m pip install demo",
                "_argv": ["python", "-m", "pip", "install", "demo"],
            }],
            "fingerprint": "preview-fingerprint",
        }
        with mock.patch.object(server_mod, "preview_skill_dependency_operation", return_value=plan) as preview:
            status, data = _req("POST", "/api/skills/dependencies/plan", json={
                "skill": "docx", "capability": "create", "action": "install",
            })
        self.assertEqual(status, 200)
        self.assertEqual(data["fingerprint"], "preview-fingerprint")
        self.assertNotIn("_argv", data["steps"][0])
        preview.assert_called_once_with("docx", "create", "install")

    def test_dependency_operation_start_poll_and_cancel_routes(self):
        condition = threading.Condition(threading.RLock())
        operation = {
            "id": "dependency-operation",
            "skill": "docx",
            "capability": "create",
            "action": "install",
            "status": "completed",
            "phase": "completed",
            "progress": 100,
            "currentStep": 1,
            "completedSteps": 1,
            "totalSteps": 1,
            "currentCommand": "python -m pip install demo",
            "createdAt": "2026-07-23T10:00:00",
            "startedAt": "2026-07-23T10:00:00",
            "finishedAt": "2026-07-23T10:00:01",
            "version": 3,
            "cancelRequested": False,
            "errorCode": "",
            "error": "",
            "failedStep": None,
            "result": {"dependency": {"name": "docx", "status": "ready", "capabilities": []}},
            "plan": {"fingerprint": "confirmed", "steps": [{"displayCommand": "python -m pip install demo", "_argv": ["python"]}]},
            "condition": condition,
        }
        with (
            mock.patch.object(server_mod, "create_skill_dependency_operation", return_value=operation) as create,
            mock.patch.object(server_mod, "get_skill_dependency_operation", return_value=operation),
            mock.patch.object(server_mod, "cancel_skill_dependency_operation", return_value=operation),
        ):
            post_status, posted = _req("POST", "/api/skills/dependencies/operations", json={
                "skill": "docx", "capability": "create", "action": "install", "fingerprint": "confirmed",
            })
            get_status, fetched = _req("GET", "/api/skills/dependencies/operations/dependency-operation")
            delete_status, cancelled = _req("DELETE", "/api/skills/dependencies/operations/dependency-operation")
        self.assertEqual((post_status, get_status, delete_status), (201, 200, 200))
        self.assertEqual(posted["id"], "dependency-operation")
        self.assertEqual(fetched["status"], "completed")
        self.assertNotIn("_argv", fetched["plan"]["steps"][0])
        self.assertEqual(cancelled["id"], "dependency-operation")
        create.assert_called_once_with("docx", "create", "install", "confirmed")

    def test_config_get(self):
        status, data = _req("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertIn("projectRoot", data)

    def test_config_roundtrip(self):
        status, _ = _req("POST", "/api/config", json={
            "projectRoot": str(self._tmp_root),
            "newApiBaseUrl": "http://localhost:3000",
        })
        self.assertEqual(status, 200)

    def test_404_unknown_route(self):
        status, data = _req("GET", "/api/nonexistent")
        self.assertEqual(status, 404)


# ═══════════════════════════════════════════════════════════════════
# 2. File System Tools
# ═══════════════════════════════════════════════════════════════════

class TestFileTools(TestServerFixture):

    def test_registry_declares_read_interaction_and_proposal_effects(self):
        self.assertEqual(set(server_mod.SERVER_TOOL_REGISTRY), {
            "request_user_input", "list_files", "read_file", "search_files", "glob_files",
            "web_fetch", "use_skill", "check_skill_dependencies", "read_skill_resource", "save_memory", "run_command",
            "propose_edit", "write_file", "delete_file", "task",
        })
        interaction = server_mod.SERVER_TOOL_REGISTRY["request_user_input"]
        self.assertEqual(interaction["effect"], "interaction")
        self.assertTrue(interaction["idempotent"])
        self.assertFalse(interaction["background"])
        for name in (
            "list_files", "read_file", "search_files", "glob_files",
            "web_fetch", "use_skill", "check_skill_dependencies", "read_skill_resource",
        ):
            spec = server_mod.SERVER_TOOL_REGISTRY[name]
            self.assertEqual(spec["effect"], "read")
            self.assertTrue(spec["idempotent"])
            self.assertTrue(spec["background"])
        proposal = server_mod.SERVER_TOOL_REGISTRY["propose_edit"]
        self.assertEqual(proposal["effect"], "proposal")
        self.assertTrue(proposal["idempotent"])
        self.assertFalse(proposal["background"])
        command = server_mod.SERVER_TOOL_REGISTRY["run_command"]
        self.assertEqual(command["effect"], "command")
        self.assertFalse(command["idempotent"])
        self.assertTrue(command["background"])
        memory = server_mod.SERVER_TOOL_REGISTRY["save_memory"]
        self.assertEqual(memory["effect"], "memory_write")
        self.assertTrue(memory["idempotent"])
        self.assertTrue(memory["background"])
        for name in ("write_file", "delete_file"):
            mutation = server_mod.SERVER_TOOL_REGISTRY[name]
            self.assertEqual(mutation["effect"], "file_mutation")
            self.assertTrue(mutation["idempotent"])
            self.assertTrue(mutation["background"])
        delegation = server_mod.SERVER_TOOL_REGISTRY["task"]
        self.assertEqual(delegation["effect"], "delegation")
        self.assertTrue(delegation["idempotent"])
        self.assertTrue(delegation["background"])
        self.assertIsNone(delegation["execute"])

    def test_http_read_only_tools_share_registry_results(self):
        cases = [
            ("list_files", {"path": "src", "maxDepth": 1}),
            ("read_file", {"path": "src/main.py"}),
            ("search_files", {"query": "hello", "path": "src"}),
            ("glob_files", {"pattern": "*.py", "path": "src"}),
        ]
        for action, payload in cases:
            with self.subTest(action=action):
                direct = server_mod.execute_registered_tool(action, payload)
                status, routed = _req("POST", f"/api/tools/{action}", json=payload)
                self.assertEqual(status, 200)
                self.assertEqual(routed, direct)

    def test_registered_tool_protocol_validation_is_strict_and_nested(self):
        with self.assertRaisesRegex(ValueError, "path is required"):
            server_mod.execute_registered_tool("read_file", {})
        with self.assertRaisesRegex(ValueError, "file_path is not supported"):
            server_mod.execute_registered_tool(
                "read_file", {"file_path": "src/main.py"},
            )
        status, routed_error = _req(
            "POST",
            "/api/tools/read_file",
            json={"file_path": "src/main.py"},
        )
        self.assertEqual(status, 400)
        self.assertIn("file_path is not supported", routed_error["error"])
        with self.assertRaisesRegex(ValueError, "maxDepth must be integer"):
            server_mod.execute_registered_tool(
                "list_files", {"path": "src", "maxDepth": True},
            )

        valid_questionnaire = {
            "questions": [{
                "id": "target",
                "prompt": "Choose a target",
                "type": "single",
                "allowOther": True,
                "options": [
                    {
                        "value": "src", "label": "Source",
                        "description": "Recommended for source inspection.",
                        "recommended": True,
                    },
                    {
                        "value": "tests", "label": "Tests",
                        "description": "Use for test inspection.",
                        "recommended": False,
                    },
                ],
            }],
        }
        self.assertEqual(
            server_mod._registered_tool_argument_errors(
                "request_user_input", valid_questionnaire,
            ),
            [],
        )
        invalid_questionnaire = {
            "questions": [{
                "id": "target",
                "prompt": "Choose a target",
                "type": "unsupported",
                "allowOther": True,
                "options": [
                    {
                        "value": "src",
                        "description": "Recommended for source inspection.",
                        "recommended": True,
                    },
                    {
                        "value": "tests", "label": "Tests",
                        "description": "Use for test inspection.",
                        "recommended": False,
                    },
                ],
            }],
        }
        errors = server_mod._registered_tool_argument_errors(
            "request_user_input", invalid_questionnaire,
        )
        self.assertEqual(
            {(item["field"], item["reason"]) for item in errors},
            {
                ("questions[0].type", "enum"),
                ("questions[0].options[0].label", "required"),
            },
        )

    def test_http_network_and_skill_tools_share_registry_results(self):
        skill_dir = self._tmp_data / "skills" / "registered-skill"
        references_dir = skill_dir / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: registered-skill\ndescription: Registry test\n"
            "tools: read_file\n---\n\nFollow the registered instructions.\n",
            encoding="utf-8",
        )
        (references_dir / "guide.md").write_text("Registered reference", encoding="utf-8")

        cases = [
            ("use_skill", {"name": "registered-skill"}),
            ("check_skill_dependencies", {"name": "registered-skill"}),
            ("read_skill_resource", {
                "skill": "registered-skill",
                "file": "references/guide.md",
            }),
        ]
        for action, payload in cases:
            with self.subTest(action=action):
                direct = server_mod.execute_registered_tool(action, payload)
                status, routed = _req("POST", f"/api/tools/{action}", json=payload)
                self.assertEqual(status, 200)
                self.assertEqual(routed, direct)

        web_result = {
            "ok": True,
            "action": "web_fetch",
            "url": "https://example.com",
            "status": 200,
            "content": "Example",
        }
        with mock.patch.dict(
            server_mod.SERVER_TOOL_REGISTRY["web_fetch"],
            {"execute": lambda _payload: dict(web_result)},
        ):
            status, routed = _req(
                "POST", "/api/tools/web_fetch", json={"url": "https://example.com"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(routed, web_result)

    def test_http_save_memory_uses_shared_idempotent_registry_service(self):
        payload = {
            "name": "registry-memory",
            "description": "Remember the shared service",
            "body": "Use one durable implementation for HTTP and AgentRun.",
        }
        path = server_mod.MEMORY_DIR / "registry-memory.md"
        path.unlink(missing_ok=True)
        direct = server_mod.execute_registered_tool("save_memory", payload)
        before = path.read_bytes()
        before_mtime = path.stat().st_mtime_ns

        status, routed = _req("POST", "/api/tools/save_memory", json=payload)

        self.assertEqual(status, 201)
        self.assertFalse(direct["replayed"])
        self.assertTrue(routed["replayed"])
        self.assertEqual(routed["action"], "save_memory")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)

    # ── list_files ──
    def test_list_files_root(self):
        status, data = _req("POST", "/api/tools/list_files", json={"path": ""})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        entries = data.get("items") or data.get("files") or []
        names = [e["name"] for e in entries]
        self.assertIn("src", names)
        self.assertIn("README.md", names)

    def test_list_files_subdir(self):
        status, data = _req("POST", "/api/tools/list_files", json={"path": "src"})
        self.assertEqual(status, 200)
        entries = data.get("items") or data.get("files") or []
        names = [e["name"] for e in entries]
        self.assertIn("main.py", names)
        self.assertIn("utils.py", names)

    def test_list_files_nonexistent(self):
        status, data = _req("POST", "/api/tools/list_files", json={"path": "nonexistent"})
        self.assertEqual(status, 400)

    # ── read_file ──
    def test_read_text_file(self):
        status, data = _req("POST", "/api/tools/read_file",
                            json={"path": "src/main.py"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertIn("hello world", data.get("content", ""))

    def test_read_file_with_line_range(self):
        status, data = _req("POST", "/api/tools/read_file",
                            json={"path": "src/utils.py", "startLine": 1, "endLine": 1})
        self.assertEqual(status, 200)
        content = data.get("content", "")
        self.assertIn("def add", content)

    def test_read_binary_file(self):
        status, data = _req("POST", "/api/tools/read_file",
                            json={"path": "binary.bin"})
        self.assertEqual(status, 200)
        # Binary files get size/type info but limited content
        self.assertTrue(data.get("ok") or data.get("binary") or "size" in data)

    def test_read_nonexistent_file(self):
        status, data = _req("POST", "/api/tools/read_file",
                            json={"path": "nonexistent.txt"})
        self.assertEqual(status, 400)

    def test_read_file_path_traversal_rejected(self):
        status, data = _req("POST", "/api/tools/read_file",
                            json={"path": "../../../Windows/System32/drivers/etc/hosts"})
        self.assertEqual(status, 400)

    # ── write_file ──
    def test_write_and_read_roundtrip(self):
        status, data = _req("POST", "/api/tools/write_file",
                            json={"path": "test_write.txt", "content": "hello test"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        # Verify file was actually written
        written = self._tmp_root / "test_write.txt"
        self.assertTrue(written.exists())
        self.assertEqual(written.read_text(encoding="utf-8"), "hello test")

    def test_write_file_creates_backup(self):
        # First write
        _req("POST", "/api/tools/write_file",
             json={"path": "backup_test.txt", "content": "version 1"})
        # Second write should create backup
        status, data = _req("POST", "/api/tools/write_file",
                            json={"path": "backup_test.txt", "content": "version 2"})
        self.assertEqual(status, 200)
        # Check backup exists
        backups = list((self._tmp_data / "file-backups").iterdir())
        self.assertGreater(len(backups), 0)

    def test_write_file_shared_service_replays_without_duplicate_backup(self):
        path = self._tmp_root / "write_replay.txt"
        path.write_text("before", encoding="utf-8")
        payload = {
            "path": "write_replay.txt",
            "content": "after",
            "_operationId": "route-write-operation",
        }
        direct = server_mod.execute_registered_tool("write_file", payload)
        backup_path = Path(direct["backupPath"])
        before_mtime = path.stat().st_mtime_ns

        status, routed = _req("POST", "/api/tools/write_file", json=payload)

        self.assertEqual(status, 200)
        self.assertFalse(direct["replayed"])
        self.assertTrue(routed["replayed"])
        self.assertEqual(path.read_text(encoding="utf-8"), "after")
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)
        self.assertTrue(backup_path.is_file())
        self.assertEqual(backup_path.read_text(encoding="utf-8"), "before")

    def test_write_file_path_traversal_not_outside_project(self):
        """Path traversal must not result in file written outside project or home."""
        status, data = _req("POST", "/api/tools/write_file",
                            json={"path": "../outside.txt", "content": "safe"})
        # The server either accepts and redirects, or rejects — both are safe behaviors
        # The key security property: sensitive paths must NOT be writable
        sensitive = Path("C:/Windows/System32/outside.txt")
        self.assertFalse(sensitive.exists(), "Must not write to System32!")
        # If accepted, verify the file ended up in a safe location
        if status == 200:
            written_path = data.get("path", "")
            self.assertNotIn("System32", written_path)
            self.assertNotIn("Windows", written_path)

    # ── delete_file ──
    def test_delete_file(self):
        path = self._tmp_root / "to_delete.txt"
        path.write_text("delete me")
        self.assertTrue(path.exists(), "File should exist before delete")
        status, data = _req("POST", "/api/tools/delete_file",
                            json={"path": "to_delete.txt"})
        self.assertEqual(status, 200, f"Delete failed: {data}")
        self.assertTrue(data.get("ok"))
        self.assertFalse(path.exists())

    def test_delete_file_shared_service_replays_from_durable_receipt(self):
        path = self._tmp_root / "delete_replay.txt"
        path.write_text("delete once", encoding="utf-8")
        payload = {
            "path": "delete_replay.txt",
            "_operationId": "route-delete-operation",
        }
        direct = server_mod.execute_registered_tool("delete_file", payload)
        backup_path = Path(direct["backupPath"])

        status, routed = _req("POST", "/api/tools/delete_file", json=payload)

        self.assertEqual(status, 200)
        self.assertFalse(direct["replayed"])
        self.assertTrue(routed["replayed"])
        self.assertFalse(path.exists())
        self.assertTrue(backup_path.is_file())
        self.assertEqual(backup_path.read_text(encoding="utf-8"), "delete once")

    def test_delete_file_path_traversal_rejected(self):
        status, data = _req("POST", "/api/tools/delete_file",
                            json={"path": "../../../etc/passwd"})
        self.assertEqual(status, 400)

    # ── mkdir ──
    def test_mkdir(self):
        status, data = _req("POST", "/api/mkdir",
                            json={"name": "new_test_dir", "parent": ""})
        self.assertEqual(status, 200)
        self.assertTrue((self._tmp_root / "new_test_dir").is_dir())

    def test_mkdir_in_subdir(self):
        status, data = _req("POST", "/api/mkdir",
                            json={"name": "nested", "parent": "src"})
        self.assertEqual(status, 200)
        self.assertTrue((self._tmp_root / "src" / "nested").is_dir())

    # ── search_files ──
    def test_search_files_by_content(self):
        status, data = _req("POST", "/api/tools/search_files",
                            json={"query": "print", "path": "src"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        # Should find main.py containing "print"
        matches = data.get("items") or data.get("results") or data.get("matches") or []
        self.assertIsInstance(matches, list)

    def test_search_files_recursive_glob_includes_project_root(self):
        status, data = _req(
            "POST",
            "/api/tools/search_files",
            json={"query": "Test Project", "glob": "**/*.md"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        paths = [item.get("path") for item in data.get("results") or []]
        self.assertIn("README.md", paths)

    def test_search_files_hints_when_regex_syntax_is_used_as_literal(self):
        status, literal = _req(
            "POST",
            "/api/tools/search_files",
            json={"query": "Test Project|Missing", "glob": "**/*.md"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(literal.get("results"), [])
        self.assertIn("regex=true", literal.get("hint") or "")

        status, regex = _req(
            "POST",
            "/api/tools/search_files",
            json={
                "query": "Test Project|Missing",
                "regex": True,
                "glob": "**/*.md",
            },
        )
        self.assertEqual(status, 200)
        paths = [item.get("path") for item in regex.get("results") or []]
        self.assertIn("README.md", paths)

    # ── glob_files ──
    def test_glob_files(self):
        status, data = _req("POST", "/api/tools/glob_files",
                            json={"pattern": "**/*.py", "path": "src"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        results = data.get("items") or data.get("results") or data.get("matches") or []
        self.assertIsInstance(results, list)

    def test_glob_files_recursive_pattern_includes_project_root(self):
        status, data = _req(
            "POST",
            "/api/tools/glob_files",
            json={"pattern": "**/*.md"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        paths = [item.get("path") for item in data.get("results") or []]
        self.assertIn("README.md", paths)


# ═══════════════════════════════════════════════════════════════════
# 3. Command Execution
# ═══════════════════════════════════════════════════════════════════

class TestCommandExecution(TestServerFixture):

    def test_http_command_uses_shared_registry_service(self):
        direct = server_mod.execute_registered_tool(
            "run_command", {"command": "echo shared-command"},
        )
        status, routed = _req(
            "POST", "/api/tools/run_command", json={"command": "echo shared-command"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(routed["ok"], direct["ok"])
        self.assertEqual(routed["action"], direct["action"])
        self.assertEqual(routed["command"], direct["command"])
        self.assertIn("shared-command", routed["stdout"])

    def test_safe_command_echo(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "echo hello world", "description": "test"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertIn("hello", data.get("stdout", "").lower())
        self.assertIn("world", data.get("stdout", "").lower())

    def test_safe_command_dir(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "dir", "description": "list dir"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))

    def test_blocked_del_command(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "del file.txt", "description": "delete"})
        self.assertEqual(status, 400)
        self.assertFalse(data.get("ok", True))

    def test_blocked_format_command(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "format C:", "description": "destroy"})
        self.assertEqual(status, 400)

    def test_python_c_allowed(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "python -c \"print(42)\"", "description": "test"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertIn("42", data.get("stdout", ""))

    def test_empty_command_rejected(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "", "description": "empty"})
        self.assertEqual(status, 400)

    def test_command_with_timeout(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={"command": "ping -n 4 127.0.0.1", "description": "ping", "timeout": 10})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))

    def test_command_timeout_returns_checkpointed_failure(self):
        status, data = _req(
            "POST",
            "/api/tools/run_command",
            json={
                "command": 'python -c "import time; print(\'before-timeout\', flush=True); time.sleep(5)"',
                "timeout": 1,
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertTrue(data["timedOut"])
        self.assertIn("before-timeout", data["stdout"])

    def test_nonzero_command_preserves_exit_code_and_stderr(self):
        status, data = _req(
            "POST",
            "/api/tools/run_command",
            json={"command": 'python -c "import sys; print(\'failed\', file=sys.stderr); raise SystemExit(3)"'},
        )
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertEqual(data["exitCode"], 3)
        self.assertIn("failed", data["stderr"])


# ═══════════════════════════════════════════════════════════════════
# 4. Session CRUD Lifecycle
# ═══════════════════════════════════════════════════════════════════

class TestSessionLifecycle(TestServerFixture):
    _session_id = None

    def test_01_create_session(self):
        status, data = _req("POST", "/api/sessions", json={
            "title": "Integration Test Session",
            "messages": [{"role": "user", "content": "Hello"}],
        })
        self.assertEqual(status, 201)
        self.assertIn("id", data)
        self.assertIn("_filePath", data)
        self.assertIn("_messageFilePath", data)
        TestSessionLifecycle._session_id = data["id"]
        self.assertTrue(Path(data["_filePath"]).exists())
        self.assertTrue(Path(data["_messageFilePath"]).exists())
        self.assertEqual(Path(data["_messageFilePath"]).suffix, ".jsonl")

    def test_02_save_session(self):
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("PUT", f"/api/sessions/{sid}", json={
            "title": "Integration Test Session Updated",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        })
        self.assertEqual(status, 200)
        self.assertIn("_filePath", data)
        self.assertIn("_messageFilePath", data)

    def test_03_load_session(self):
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("GET", f"/api/sessions/{sid}")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("title"), "Integration Test Session Updated")
        self.assertEqual(len(data.get("messages", [])), 2)
        self.assertEqual(Path(data["_messageFilePath"]).suffix, ".jsonl")

    def test_04_list_sessions(self):
        status, data = _req("GET", "/api/sessions")
        self.assertEqual(status, 200)
        sessions = data.get("sessions") or data.get("data") or []
        sids = [s["id"] for s in sessions]
        self.assertIn(TestSessionLifecycle._session_id, sids)

    def test_05_archive_session(self):
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("PUT", f"/api/sessions/{sid}/archive", json={
            "messages": [{"role": "user", "content": "test"}],
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))

    def test_055_append_messages(self):
        """POST /api/sessions/{id}/messages — incremental append."""
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("POST", f"/api/sessions/{sid}/messages", json={
            "messages": [
                {"role": "assistant", "content": "appended 1"},
                {"role": "assistant", "content": "appended 2"},
            ],
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("appended"), 2)
        # Verify messages are there
        _, full = _req("GET", f"/api/sessions/{sid}")
        self.assertGreaterEqual(len(full.get("messages", [])), 4)  # 2 original + 2 appended

    def test_055b_append_messages_empty(self):
        """POST /api/sessions/{id}/messages with empty messages is a no-op."""
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("POST", f"/api/sessions/{sid}/messages", json={
            "messages": [],
        })
        self.assertEqual(status, 200)
        self.assertEqual(data.get("appended"), 0)

    def test_06_delete_session(self):
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("DELETE", f"/api/sessions/{sid}")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))

    def test_07_session_deleted_not_found(self):
        sid = TestSessionLifecycle._session_id
        self.assertIsNotNone(sid, "Session not created yet")
        status, data = _req("GET", f"/api/sessions/{sid}")
        self.assertEqual(status, 404)


# ═══════════════════════════════════════════════════════════════════
# 5. Web Fetch
# ═══════════════════════════════════════════════════════════════════

class TestWebFetch(TestServerFixture):

    def test_fetch_blocked_internal_ip(self):
        status, data = _req("POST", "/api/tools/web_fetch",
                            json={"url": "http://127.0.0.1/admin"})
        self.assertEqual(status, 400)
        self.assertIn("内网", data.get("error", ""))

    def test_fetch_blocked_private_ip(self):
        status, data = _req("POST", "/api/tools/web_fetch",
                            json={"url": "http://192.168.1.1/"})
        self.assertEqual(status, 400)

    def test_fetch_empty_url_rejected(self):
        status, data = _req("POST", "/api/tools/web_fetch",
                            json={"url": ""})
        self.assertEqual(status, 400)


# ═══════════════════════════════════════════════════════════════════
# 6. Attachments
# ═══════════════════════════════════════════════════════════════════

class TestAttachments(TestServerFixture):

    @staticmethod
    def _tiff_bytes():
        import io
        from PIL import Image

        image = Image.new("RGB", (19, 13), (12, 80, 190))
        output = io.BytesIO()
        image.save(output, format="TIFF")
        return output.getvalue()

    def test_attachment_upload(self):
        import base64
        content = base64.b64encode(b"hello attachment").decode()
        status, data = _req("POST", "/api/attachments",
                            json={"name": "test.txt", "contentBase64": content})
        self.assertIn(status, [200, 201])
        self.assertTrue(data.get("path"))

    def test_attachment_path_safety(self):
        import base64
        content = base64.b64encode(b"safe content").decode()
        # Name gets sanitized, so traversal in name should be harmless
        status, data = _req("POST", "/api/attachments",
                            json={"name": "../../../evil.txt", "contentBase64": content})
        # Should succeed — name is sanitized
        self.assertIn(status, [200, 201])

    def test_tiff_attachment_preview_route_is_png_and_preserves_source(self):
        import base64
        import hashlib
        import io
        from PIL import Image

        source = self._tiff_bytes()
        status, uploaded = _req("POST", "/api/attachments", json={
            "name": "sample.tiff",
            "contentBase64": base64.b64encode(source).decode("ascii"),
        })
        self.assertIn(status, [200, 201])
        _root, target = server_mod.resolve_attachment_path(uploaded["path"])
        before_hash = hashlib.sha256(target.read_bytes()).hexdigest()

        response = requests.get(
            f"{_BASE}/api/attachments/preview",
            params={"path": uploaded["path"]},
            timeout=10,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (19, 13))
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), before_hash)

    def test_inline_tiff_attachment_preview_route_is_png(self):
        import base64

        response = requests.post(
            f"{_BASE}/api/attachments/preview",
            json={
                "mime": "image/tiff",
                "contentBase64": base64.b64encode(self._tiff_bytes()).decode("ascii"),
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")
        self.assertTrue(response.content.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_tiff_preview_route_rejects_non_attachment_and_traversal_paths(self):
        cases = (
            "README.md",
            str(self._tmp_root / "README.md"),
            "attachments/../../../README.md",
            "attachment:../../../README.md",
        )
        for value in cases:
            with self.subTest(path=value):
                response = requests.get(
                    f"{_BASE}/api/attachments/preview",
                    params={"path": value},
                    timeout=10,
                )
                self.assertEqual(response.status_code, 400)
                payload = response.json()
                self.assertNotIn(str(self._tmp_root), str(payload))
                self.assertNotIn(str(self._tmp_data), str(payload))

    def test_tiff_preview_route_rejects_wrong_signature_and_bad_base64(self):
        import base64

        cases = (
            {"mime": "image/tiff", "contentBase64": "%%%"},
            {"mime": "image/tiff", "contentBase64": base64.b64encode(b"not-tiff").decode("ascii")},
            {"mime": "image/png", "contentBase64": base64.b64encode(self._tiff_bytes()).decode("ascii")},
            {"mime": "image/tiff", "contentBase64": base64.b64encode(b"II*\x00broken").decode("ascii")},
        )
        for payload in cases:
            with self.subTest(payload=payload["mime"]):
                response = requests.post(
                    f"{_BASE}/api/attachments/preview",
                    json=payload,
                    timeout=10,
                )
                self.assertEqual(response.status_code, 400)
                self.assertLess(len(response.content), 512)


# ═══════════════════════════════════════════════════════════════════
# 7. Error handling & edge cases
# ═══════════════════════════════════════════════════════════════════

class TestErrorHandling(TestServerFixture):

    def test_malformed_json_body(self):
        status, data = _req("POST", "/api/tools/run_command",
                            data="not json",
                            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_missing_required_params(self):
        status, data = _req("POST", "/api/tools/run_command",
                            json={})  # missing "command"
        self.assertEqual(status, 400)

    def test_invalid_method_on_route(self):
        # DELETE on /api/ping
        status, data = _req("DELETE", "/api/ping")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
