"""
Tests for server.py pure functions.
Run: python -m unittest tests.test_server -v
   or: python tests/test_server.py
"""
import base64
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server
import launcher


class TestSkillDependencyOperations(unittest.TestCase):
    def setUp(self):
        with server._dependency_operation_lock:
            server._dependency_operations.clear()

    def tearDown(self):
        with server._dependency_operation_lock:
            server._dependency_operations.clear()

    def _plan(self, fingerprint="plan-fingerprint"):
        return {
            "schemaVersion": 1,
            "skill": "demo",
            "capability": "runtime",
            "action": "install",
            "actionable": True,
            "noChanges": False,
            "blockedReasons": [],
            "requirements": [],
            "systemRequirements": [],
            "locations": {"python": r"C:\managed\python", "node": r"C:\managed\node"},
            "authorization": {
                "scope": "managed_runtime",
                "root": r"C:\managed",
                "systemPackageManagers": False,
                "pathChanges": False,
                "globalWrappers": False,
            },
            "steps": [{
                "id": "install-python-packages",
                "type": "python",
                "purpose": "install_packages",
                "displayCommand": "python -m pip install demo",
                "_argv": ["python", "-m", "pip", "install", "demo"],
            }],
            "commandSummaries": ["python -m pip install demo"],
            "fingerprint": fingerprint,
        }

    def test_operation_is_idempotent_tracks_progress_and_hides_argv(self):
        release = threading.Event()

        def execute(plan, *, cancel_event, progress_callback, process_callback, timeout_seconds):
            progress_callback({
                "phase": "install_packages",
                "currentStep": 1,
                "completedSteps": 0,
                "totalSteps": 1,
                "step": server.public_dependency_operation_plan(plan["steps"][0]),
            })
            release.wait(timeout=3)
            return {"ok": True, "completedSteps": 1, "totalSteps": 1}

        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()) as preview,
            mock.patch.object(server, "execute_dependency_operation_plan", side_effect=execute),
            mock.patch.object(server, "get_single_skill_dependency_status", return_value={
                "name": "demo", "status": "ready", "capabilities": [],
            }),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            duplicate = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            self.assertIs(operation, duplicate)
            with self.assertRaisesRegex(ValueError, "already running"):
                server.create_skill_dependency_operation("other", "runtime", "install", "plan-fingerprint")
            preview.assert_called_once_with("demo", "runtime", "install")
            deadline = time.time() + 2
            while operation["status"] == "pending" and time.time() < deadline:
                time.sleep(0.01)
            snapshot = server._dependency_operation_snapshot(operation)
            self.assertEqual(snapshot["status"], "running")
            self.assertEqual(snapshot["currentCommand"], "python -m pip install demo")
            self.assertNotIn("_argv", snapshot["plan"]["steps"][0])
            release.set()
            deadline = time.time() + 2
            while operation["status"] != "completed" and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual(operation["status"], "completed")
        self.assertEqual(operation["progress"], 100)
        self.assertEqual(operation["result"]["dependency"]["status"], "ready")
        dismissed = server.cancel_skill_dependency_operation(operation["id"])
        self.assertTrue(server._dependency_operation_snapshot(dismissed)["dismissed"])
        self.assertIsNone(server.get_skill_dependency_operation(operation["id"]))

    def test_cancellation_reaches_terminal_state_and_is_retryable(self):
        def execute(plan, *, cancel_event, progress_callback, process_callback, timeout_seconds):
            cancel_event.wait(timeout=3)
            return {"ok": False, "cancelled": True, "errorCode": "cancelled"}

        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()),
            mock.patch.object(server, "execute_dependency_operation_plan", side_effect=execute),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            server.cancel_skill_dependency_operation(operation["id"])
            deadline = time.time() + 2
            while operation["status"] != "cancelled" and time.time() < deadline:
                time.sleep(0.01)

        snapshot = server._dependency_operation_snapshot(operation)
        self.assertEqual(snapshot["status"], "cancelled")
        self.assertTrue(snapshot["cancelRequested"])
        self.assertTrue(snapshot["retryable"])

    def test_failed_operation_keeps_safe_recovery_metadata(self):
        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()),
            mock.patch.object(server, "execute_dependency_operation_plan", return_value={
                "ok": False,
                "errorCode": "process_failed",
                "error": "Dependency step failed with exit code 1.",
                "failedStep": {"id": "install-python-packages", "displayCommand": "python -m pip install demo"},
            }),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            deadline = time.time() + 2
            while operation["status"] not in server._DEPENDENCY_OPERATION_TERMINAL and time.time() < deadline:
                time.sleep(0.01)

        snapshot = server._dependency_operation_snapshot(operation)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "process_failed")
        self.assertTrue(snapshot["retryable"])
        self.assertNotIn("stdout", snapshot)
        self.assertNotIn("stderr", snapshot)


class TestUpdaterHelpers(unittest.TestCase):
    def test_remote_version_selects_matching_code_asset(self):
        payload = {
            "tag_name": "v0.5.4",
            "assets": [
                {"name": "helper.exe", "browser_download_url": "https://example.test/helper.exe"},
                {
                    "name": "Code-v0.5.4.exe",
                    "browser_download_url": "https://example.test/Code-v0.5.4.exe",
                },
            ],
        }
        response = mock.Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        with mock.patch.object(server.request, "urlopen", return_value=response):
            version, url = server._read_remote_version()
        self.assertEqual(version, "0.5.4")
        self.assertEqual(url, "https://example.test/Code-v0.5.4.exe")

    def test_valid_windows_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "Code-v1.2.3.exe"
            exe.write_bytes(b"MZ" + (b"\0" * (1024 * 1024)))
            self.assertTrue(server._is_valid_windows_executable(exe))

    def test_rejects_incomplete_or_non_pe_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "Code-v1.2.3.exe.part"
            bad.write_text("<html>download failed</html>", encoding="utf-8")
            self.assertFalse(server._is_valid_windows_executable(bad))

    def test_update_script_keeps_new_version_and_removes_old_ones(self):
        target_dir = Path(r"C:\Code")
        new_exe = target_dir / "Code-v1.2.3.exe"
        partial_exe = target_dir / "Code-v1.2.3.exe.part"
        log_path = target_dir / "update.log"
        bat_path = server._build_update_script(target_dir, new_exe, partial_exe, log_path)
        script = Path(bat_path).read_text(encoding="utf-8")
        # Batch-file updater — uses findstr to match versioned Code-v*.exe processes
        self.assertIn("findstr /i Code-", script)
        self.assertIn("taskkill", script)
        self.assertIn("move /y", script)
        self.assertIn("del /f", script)
        self.assertIn('start "" "', script)
        self.assertIn("--reuse-browser", script)

    def test_update_script_findstr_matches_versioned_process(self):
        """The batch updater must find versioned names like Code-v0.5.24.exe."""
        target_dir = Path(r"C:\Code")
        new_exe = target_dir / "Code-v2.0.0.exe"
        bat_path = server._build_update_script(target_dir, new_exe, None, target_dir / "update.log")
        script = Path(bat_path).read_text(encoding="utf-8")
        # findstr /i Code- catches "Code-v0.5.24.exe", "Code-v1.0.0.exe", etc.
        self.assertIn("findstr /i Code-", script)
        # Must NOT use the old exact-match filter that only caught "Code.exe"
        self.assertNotIn("IMAGENAME eq Code.exe", script)

    def test_check_update_detects_newer_release(self):
        handler = object.__new__(server.CodeHandler)
        download_url = "https://github.com/fhy-A/Code/releases/download/v0.4.11/Code-v0.4.11.exe"
        with mock.patch.object(server, "_read_version_file", return_value="0.4.10"), \
             mock.patch.object(server, "_read_remote_version", return_value=("0.4.11", download_url)):
            result = handler._check_update()
        self.assertTrue(result["updateAvailable"])
        self.assertEqual(result["remoteVersion"], "0.4.11")
        self.assertTrue(result["downloadUrl"].endswith("/v0.4.11/Code-v0.4.11.exe"))

    def test_frontend_waits_for_new_version_before_cache_busting_reload(self):
        settings_js = (
            Path(__file__).resolve().parent.parent / "src" / "features" / "settings.js"
        ).read_text(encoding="utf-8")
        self.assertIn('if (versionInfo.localVersion !== remoteVersion) return;', settings_js)
        self.assertIn('cache: "no-store"', settings_js)
        self.assertIn(
            'refreshed.searchParams.set("updated", `${remoteVersion}-${Date.now()}`)',
            settings_js,
        )
        self.assertIn("global.location.replace(refreshed.toString())", settings_js)


class TestWorkbarAuthentication(unittest.TestCase):
    def make_handler(self, body):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body)
        handler.send_json = mock.Mock()
        return handler

    def test_validate_code_auth_uses_fixed_workbar_endpoint(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        account_response = mock.MagicMock()
        account_response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "id": 42,
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "group": "default",
                "quota": 123,
                "used_quota": 45,
                "request_count": 67,
            },
        }).encode("utf-8")
        account_response.__enter__.return_value = account_response
        status_response = mock.MagicMock()
        status_response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "quota_per_unit": 500000,
                "quota_display_type": "CNY",
                "usd_exchange_rate": 7.2,
                "custom_currency_symbol": "",
                "custom_currency_exchange_rate": 1,
            },
        }).encode("utf-8")
        status_response.__enter__.return_value = status_response

        with mock.patch.object(server.request, "urlopen", side_effect=[account_response, status_response]) as urlopen:
            handler._handle_validate_code_auth()

        upstream = urlopen.call_args_list[0].args[0]
        self.assertEqual(upstream.full_url, "https://workbar.ai/api/user/self")
        self.assertEqual(upstream.get_header("Authorization"), "test-access-token")
        self.assertEqual(upstream.get_header("New-api-user"), "42")
        self.assertEqual(urlopen.call_args_list[1].args[0].full_url, "https://workbar.ai/api/status")
        handler.send_json.assert_called_once_with({
            "valid": True,
            "account": {
                "userId": "42",
                "username": "alice",
                "displayName": "Alice",
                "email": "alice@example.com",
                "group": "default",
                "quota": 123,
                "usedQuota": 45,
                "requestCount": 67,
                "quotaDisplay": {
                    "quotaPerUnit": 500000,
                    "type": "CNY",
                    "usdExchangeRate": 7.2,
                    "customCurrencySymbol": "",
                    "customCurrencyExchangeRate": 1,
                },
            },
        })

    def test_validate_code_auth_only_returns_allowlisted_account_fields(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        response = mock.MagicMock()
        response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "id": 42,
                "username": "alice",
                "access_token": "must-not-leak",
                "stripe_customer": "cus_private",
                "permissions": {"admin": True},
            },
        }).encode("utf-8")
        response.__enter__.return_value = response

        with mock.patch.object(server.request, "urlopen", side_effect=[response, server.error.URLError("offline")]):
            handler._handle_validate_code_auth()

        result = handler.send_json.call_args.args[0]["account"]
        self.assertEqual(set(result), {
            "userId", "username", "displayName", "email", "group",
            "quota", "usedQuota", "requestCount", "quotaDisplay",
        })
        self.assertNotIn("must-not-leak", json.dumps(result))

    def test_validate_code_auth_rejects_invalid_or_mismatched_account(self):
        for payload in (
            {"success": False, "message": "invalid"},
            {"success": True, "data": {"id": 99, "username": "other"}},
        ):
            with self.subTest(payload=payload):
                handler = self.make_handler({"token": "test-access-token", "userId": "42"})
                response = mock.MagicMock()
                response.read.return_value = json.dumps(payload).encode("utf-8")
                response.__enter__.return_value = response
                with mock.patch.object(server.request, "urlopen", return_value=response):
                    handler._handle_validate_code_auth()
                self.assertEqual(handler.send_json.call_args.args[1], 401)

    def test_validate_code_auth_keeps_outage_separate_from_expiry(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        with mock.patch.object(server.request, "urlopen", side_effect=server.error.URLError("offline")):
            handler._handle_validate_code_auth()
        handler.send_json.assert_called_once_with({"error": "workbar is unavailable"}, 502)

    def test_sync_keys_uses_fixed_workbar_endpoint_and_normalizes_prefix(self):
        handler = self.make_handler({
            "token": "test-access-token",
            "userId": "42",
            "platformUrl": "https://untrusted.example",
        })
        token_response = mock.MagicMock()
        token_response.read.return_value = json.dumps({
            "data": {"items": [
                {"id": 7, "name": "first", "status": 1},
                {"id": 8, "name": "second", "status": 2},
                {"id": 9, "name": "masked", "status": 1},
            ]},
        }).encode("utf-8")
        token_response.__enter__.return_value = token_response
        key_response = mock.MagicMock()
        key_response.read.return_value = json.dumps({
            "data": {"keys": {"7": "full-value", "8": "sk-ready", "9": "sk-***mask"}},
        }).encode("utf-8")
        key_response.__enter__.return_value = key_response

        with mock.patch.object(
            server.request,
            "urlopen",
            side_effect=[token_response, key_response],
        ) as urlopen:
            handler._handle_sync_keys()

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].full_url, "https://workbar.ai/api/token/?p=0&size=100")
        self.assertEqual(requests[1].full_url, "https://workbar.ai/api/token/batch/keys")
        self.assertEqual(requests[1].get_method(), "POST")
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(payload["keys"], {"7": "sk-full-value", "8": "sk-ready"})

    def test_sync_keys_preserves_local_auth_on_workbar_outage(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        with mock.patch.object(server.request, "urlopen", side_effect=server.error.URLError("offline")):
            handler._handle_sync_keys()
        handler.send_json.assert_called_once_with({"error": "workbar is unavailable"}, 502)

    def test_sync_keys_paginates_and_batches_all_platform_keys(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})

        def response(payload):
            result = mock.MagicMock()
            result.read.return_value = json.dumps(payload).encode("utf-8")
            result.__enter__.return_value = result
            return result

        first_page = [{"id": key_id, "name": f"key-{key_id}", "status": 1} for key_id in range(1, 101)]
        second_page = [{"id": 101, "name": "key-101", "status": 1}]
        side_effects = [
            response({"data": {"items": first_page, "total": 101}}),
            response({"data": {"items": second_page, "total": 101}}),
            response({"data": {"keys": {str(key_id): f"value-{key_id}" for key_id in range(1, 101)}}}),
            response({"data": {"keys": {"101": "value-101"}}}),
        ]
        with mock.patch.object(server.request, "urlopen", side_effect=side_effects) as urlopen:
            handler._handle_sync_keys()

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].full_url, "https://workbar.ai/api/token/?p=0&size=100")
        self.assertEqual(requests[1].full_url, "https://workbar.ai/api/token/?p=1&size=100")
        self.assertEqual(json.loads(requests[2].data)["ids"], list(range(1, 101)))
        self.assertEqual(json.loads(requests[3].data)["ids"], [101])
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(len(payload["tokens"]), 101)
        self.assertEqual(payload["keys"]["101"], "sk-value-101")


class TestTrayRestart(unittest.TestCase):
    def test_source_restart_closes_server_and_relaunches_server_script(self):
        server_ref = mock.Mock()
        icon = mock.Mock()
        with mock.patch.object(server.subprocess, "Popen") as popen:
            server._restart_code_process(server_ref, icon)

        powershell = popen.call_args.args[0]
        self.assertEqual(powershell[:3], [
            "powershell", "-NoProfile", "-NonInteractive",
        ])
        encoded = powershell[powershell.index("-EncodedCommand") + 1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        self.assertIn(f"Wait-Process -Id {os.getpid()}", script)
        self.assertIn(str((server.APP_DIR / "server.py").resolve()), script)
        server_ref.shutdown.assert_called_once_with()
        server_ref.server_close.assert_called_once_with()
        icon.stop.assert_called_once_with()

    def test_tray_menu_exposes_restart_action(self):
        source = Path(server.__file__).read_text(encoding="utf-8")
        self.assertIn('pystray.MenuItem("Restart Code", on_restart)', source)

    def test_restart_cancels_waiter_if_current_server_cannot_stop(self):
        server_ref = mock.Mock()
        server_ref.shutdown.side_effect = RuntimeError("cannot stop")
        icon = mock.Mock()
        waiter = mock.Mock()
        with mock.patch.object(server.subprocess, "Popen", return_value=waiter):
            with self.assertRaisesRegex(RuntimeError, "cannot stop"):
                server._restart_code_process(server_ref, icon)
        waiter.terminate.assert_called_once_with()
        icon.stop.assert_not_called()


class TestSanitizeFilename(unittest.TestCase):
    def test_normal_name(self):
        self.assertEqual(server.sanitize_filename("hello.txt"), "hello.txt")

    def test_strips_path_separators(self):
        # Path().name extracts only the last component
        result = server.sanitize_filename(r"foo\bar/baz.txt")
        self.assertEqual(result, "baz.txt")

    def test_replaces_angle_brackets(self):
        self.assertEqual(server.sanitize_filename("<evil>.txt"), "_evil_.txt")

    def test_replaces_colon(self):
        # Path().name strips the drive letter prefix (C:)
        self.assertEqual(server.sanitize_filename("C:file.txt"), "file.txt")

    def test_replaces_quote_and_pipe(self):
        self.assertEqual(server.sanitize_filename('a"b|c.txt'), "a_b_c.txt")

    def test_replaces_question_mark(self):
        self.assertEqual(server.sanitize_filename("what?.txt"), "what_.txt")

    def test_replaces_asterisk(self):
        self.assertEqual(server.sanitize_filename("*.txt"), "_.txt")

    def test_truncates_long_name(self):
        long_name = "x" * 200 + ".txt"
        result = server.sanitize_filename(long_name)
        self.assertEqual(len(result), 120)
        # Truncation at 120 chars cuts the extension; only verify length

    def test_empty_returns_attachment(self):
        self.assertEqual(server.sanitize_filename(""), "attachment")

    def test_none_returns_attachment(self):
        self.assertEqual(server.sanitize_filename(None), "attachment")

    def test_whitespace_only(self):
        self.assertEqual(server.sanitize_filename("   "), "attachment")


class TestSafeMemoryName(unittest.TestCase):
    def test_valid_simple(self):
        self.assertEqual(server.safe_memory_name("my-config_v2"), "my-config_v2")

    def test_valid_only_letters(self):
        self.assertEqual(server.safe_memory_name("abcdef"), "abcdef")

    def test_valid_max_length(self):
        self.assertEqual(server.safe_memory_name("a" * 64), "a" * 64)

    def test_invalid_empty(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("")

    def test_invalid_none(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name(None)

    def test_invalid_too_long(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("a" * 65)

    def test_invalid_special_chars(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("hello world")

    def test_invalid_dot(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("file.md")


class TestSafeSessionId(unittest.TestCase):
    def test_valid_min_length(self):
        self.assertEqual(server.safe_session_id("abcd1234"), "abcd1234")

    def test_valid_long(self):
        self.assertEqual(server.safe_session_id("a" * 64), "a" * 64)

    def test_invalid_too_short(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("abc")

    def test_invalid_empty(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("")

    def test_invalid_none(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id(None)

    def test_invalid_special_chars(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("session@id!")

    def test_invalid_too_long(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("a" * 65)


class TestIsProbablyText(unittest.TestCase):
    def test_plain_text(self):
        self.assertTrue(server.is_probably_text(b"hello world"))

    def test_json_bytes(self):
        self.assertTrue(server.is_probably_text(b'{"key": "value"}'))

    def test_utf8_encoded(self):
        self.assertTrue(server.is_probably_text("你好世界".encode("utf-8")))

    def test_binary_null_early(self):
        self.assertFalse(server.is_probably_text(b"foo\x00bar"))

    def test_binary_null_at_4095(self):
        data = b"A" * 4095 + b"\x00"
        self.assertFalse(server.is_probably_text(data))

    def test_binary_null_at_4097(self):
        data = b"A" * 4097 + b"\x00"
        self.assertTrue(server.is_probably_text(data))

    def test_empty_bytes(self):
        self.assertTrue(server.is_probably_text(b""))


class TestIsSafeCommand(unittest.TestCase):
    def test_dir_is_safe(self):
        ok, _ = server.is_safe_command("dir")
        self.assertTrue(ok)

    def test_dir_with_path(self):
        ok, _ = server.is_safe_command("dir C:\\Users")
        self.assertTrue(ok)

    def test_git_status(self):
        ok, _ = server.is_safe_command("git status")
        self.assertTrue(ok)

    def test_git_log(self):
        ok, _ = server.is_safe_command("git log --oneline")
        self.assertTrue(ok)

    def test_docker_compose_ps(self):
        ok, _ = server.is_safe_command("docker compose ps")
        self.assertTrue(ok)

    def test_python_m_pytest(self):
        ok, _ = server.is_safe_command("python -m pytest tests/ -v")
        self.assertTrue(ok)

    def test_npm_test(self):
        ok, _ = server.is_safe_command("npm test")
        self.assertTrue(ok)

    def test_empty_is_unsafe(self):
        ok, msg = server.is_safe_command("")
        self.assertFalse(ok)
        self.assertIn("不能为空", msg)

    def test_del_is_blocked(self):
        ok, _ = server.is_safe_command("del file.txt")
        self.assertFalse(ok)

    def test_rm_is_blocked(self):
        ok, _ = server.is_safe_command("rm file.txt")
        self.assertFalse(ok)

    # ── Updated: pipe now allowed ──
    def test_pipe_is_allowed(self):
        ok, _ = server.is_safe_command("dir | findstr test")
        self.assertTrue(ok)

    def test_pipe_git_log(self):
        ok, _ = server.is_safe_command("git log --oneline | head -5")
        self.assertTrue(ok)

    # ── Updated: redirect now allowed ──
    def test_redirect_is_allowed(self):
        ok, _ = server.is_safe_command("dir > output.txt")
        self.assertTrue(ok)

    def test_append_redirect_allowed(self):
        ok, _ = server.is_safe_command("echo line >> log.txt")
        self.assertTrue(ok)

    # ── Semicolon: still blocks when combined with dangerous cmd ──
    def test_semicolon_with_del_still_blocked(self):
        ok, _ = server.is_safe_command("dir; del file.txt")
        self.assertFalse(ok)

    def test_semicolon_in_python_allowed(self):
        ok, _ = server.is_safe_command("python -c \"x=1; y=2; print(x+y)\"")
        self.assertTrue(ok)

    def test_semicolon_in_python_import_allowed(self):
        ok, _ = server.is_safe_command("python -c \"from docx import Document; print('ok')\"")
        self.assertTrue(ok)

    # ── Updated: python -c now allowed ──
    def test_python_c_is_allowed(self):
        ok, _ = server.is_safe_command("python -c 'print(1)'")
        self.assertTrue(ok)

    def test_python_c_multiline_allowed(self):
        ok, _ = server.is_safe_command("python -c \"for i in range(3):\\n print(i)\"")
        self.assertTrue(ok)

    # ── Updated: node -e now allowed ──
    def test_node_e_is_allowed(self):
        ok, _ = server.is_safe_command("node -e 'console.log(1)'")
        self.assertTrue(ok)

    # ── New: file write/create commands allowed ──
    def test_mkdir_allowed(self):
        ok, _ = server.is_safe_command("mkdir newdir")
        self.assertTrue(ok)

    def test_set_content_allowed(self):
        ok, _ = server.is_safe_command("set-content test.txt 'hello'")
        self.assertTrue(ok)

    def test_copy_item_allowed(self):
        ok, _ = server.is_safe_command("copy-item a.txt b.txt")
        self.assertTrue(ok)

    def test_move_item_allowed(self):
        ok, _ = server.is_safe_command("move-item a.txt b.txt")
        self.assertTrue(ok)

    def test_out_file_allowed(self):
        ok, _ = server.is_safe_command("out-file -FilePath out.txt")
        self.assertTrue(ok)

    def test_pip_install_allowed(self):
        ok, _ = server.is_safe_command("pip install requests")
        self.assertTrue(ok)

    def test_dependency_installs_are_classified_by_runtime_ownership(self):
        managed_cases = (
            "pip install requests",
            "python -m pip install requests",
            "python -m venv data/runtime/python",
            "npm install --prefix data/runtime/node lodash",
        )
        for command in managed_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "managed")
                self.assertTrue(server.command_requires_dependency_authorization(command))
        system_cases = (
            "winget install Poppler.Poppler",
            "choco install pandoc",
            "sudo apt-get install libreoffice",
            "python -c \"import subprocess; subprocess.run(['winget', 'install', 'Pandoc.Pandoc'])\"",
        )
        for command in system_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "system")
                self.assertFalse(server.command_requires_dependency_authorization(command))
        environment_cases = (
            '$old = [Environment]::GetEnvironmentVariable("Path", "User"); '
            '[Environment]::SetEnvironmentVariable("Path", "$old;C:\\Pandoc", "User")',
            '$p = "$env:APPDATA\\npm\\pandoc.cmd"; Set-Content -Path $p -Value "@echo off"',
            'setx PATH "%PATH%;C:\\Pandoc"',
        )
        for command in environment_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "environment")
                self.assertFalse(server.command_requires_dependency_authorization(command))
        self.assertFalse(server.command_requires_dependency_authorization("python -m pytest -q"))
        self.assertFalse(server.command_requires_dependency_authorization("npm test"))

    def test_dependency_install_classifier_reads_project_local_wrapper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "install_deps.py"
            script.write_text(
                "import subprocess\nsubprocess.run(['winget', 'install', 'Pandoc.Pandoc'])\n",
                encoding="utf-8",
            )
            kind = server.dependency_install_command_kind(
                "python install_deps.py",
                project_root=root,
            )

        self.assertEqual(kind, "system")

    def test_run_command_blocks_system_package_manager_install(self):
        with mock.patch.object(server.subprocess, "Popen") as popen_mock:
            result = server.execute_run_command_tool({
                "command": "winget install Pandoc.Pandoc",
                "timeout": 300,
            })

        popen_mock.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["userCooperationRequired"])
        self.assertEqual(result["dependencyInstallKind"], "system")

    def test_run_command_blocks_persistent_dependency_environment_changes(self):
        command = (
            '$p = "$env:APPDATA\\npm\\pdftoppm.cmd"; '
            'Set-Content -Path $p -Value "@echo off"'
        )
        with mock.patch.object(server.subprocess, "Popen") as popen_mock:
            result = server.execute_run_command_tool({"command": command})

        popen_mock.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["userCooperationRequired"])
        self.assertEqual(result["dependencyInstallKind"], "environment")
        self.assertIn("Do not modify PATH", result["error"])

    def test_repeated_command_guard_blocks_the_third_identical_attempt(self):
        run = {
            "tool_executions": {
                "one": {"name": "run_command", "command": "python -m pytest -q"},
                "two": {"name": "run_command", "command": "  PYTHON   -m pytest -q  "},
                "current": {"name": "run_command", "command": "python -m pytest -q"},
            },
        }
        count = server._agent_repeated_command_count(
            run,
            "python -m pytest -q",
            exclude_call_id="current",
        )
        self.assertEqual(count, 2)

    # ── New: expanded whitelist checks ──
    def test_curl_allowed(self):
        ok, _ = server.is_safe_command("curl https://example.com")
        self.assertTrue(ok)

    def test_cat_allowed(self):
        ok, _ = server.is_safe_command("cat file.txt")
        self.assertTrue(ok)

    def test_grep_allowed(self):
        ok, _ = server.is_safe_command("grep pattern file.txt")
        self.assertTrue(ok)

    def test_find_allowed(self):
        ok, _ = server.is_safe_command("find . -name '*.py'")
        self.assertTrue(ok)

    def test_wc_allowed(self):
        ok, _ = server.is_safe_command("wc -l file.txt")
        self.assertTrue(ok)

    def test_head_allowed(self):
        ok, _ = server.is_safe_command("head -10 file.txt")
        self.assertTrue(ok)

    def test_tail_allowed(self):
        ok, _ = server.is_safe_command("tail -20 file.txt")
        self.assertTrue(ok)

    def test_tasklist_allowed(self):
        ok, _ = server.is_safe_command("tasklist")
        self.assertTrue(ok)

    def test_netstat_allowed(self):
        ok, _ = server.is_safe_command("netstat -an")
        self.assertTrue(ok)

    def test_ipconfig_allowed(self):
        ok, _ = server.is_safe_command("ipconfig")
        self.assertTrue(ok)

    def test_ping_allowed(self):
        ok, _ = server.is_safe_command("ping localhost")
        self.assertTrue(ok)

    def test_git_branch_allowed(self):
        ok, _ = server.is_safe_command("git branch -a")
        self.assertTrue(ok)

    def test_git_stash_allowed(self):
        ok, _ = server.is_safe_command("git stash list")
        self.assertTrue(ok)

    def test_git_blame_allowed(self):
        ok, _ = server.is_safe_command("git blame server.py")
        self.assertTrue(ok)

    def test_docker_ps_allowed(self):
        ok, _ = server.is_safe_command("docker ps")
        self.assertTrue(ok)

    def test_get_process_allowed(self):
        ok, _ = server.is_safe_command("get-process")
        self.assertTrue(ok)

    def test_cargo_allowed(self):
        ok, _ = server.is_safe_command("cargo build")
        self.assertTrue(ok)

    def test_go_allowed(self):
        ok, _ = server.is_safe_command("go build ./...")
        self.assertTrue(ok)

    def test_tar_create_allowed(self):
        ok, _ = server.is_safe_command("tar -czf archive.tar.gz dir/")
        self.assertTrue(ok)

    # ── Deletion still blocked ──
    def test_del_is_blocked(self):
        ok, _ = server.is_safe_command("del file.txt")
        self.assertFalse(ok)

    def test_rm_is_blocked(self):
        ok, _ = server.is_safe_command("rm file.txt")
        self.assertFalse(ok)

    def test_rmdir_is_blocked(self):
        ok, _ = server.is_safe_command("rmdir somedir")
        self.assertFalse(ok)

    def test_remove_item_is_blocked(self):
        ok, _ = server.is_safe_command("remove-item file.txt")
        self.assertFalse(ok)

    def test_del_force_is_blocked(self):
        ok, _ = server.is_safe_command("del /f /s C:\\important.txt")
        self.assertFalse(ok)

    # ── System destruction still blocked ──
    def test_format_is_blocked(self):
        ok, _ = server.is_safe_command("format C:")
        self.assertFalse(ok)

    def test_shutdown_is_blocked(self):
        ok, _ = server.is_safe_command("shutdown /s")
        self.assertFalse(ok)

    def test_reg_is_blocked(self):
        ok, _ = server.is_safe_command("reg delete HKLM\\something")
        self.assertFalse(ok)

    def test_net_user_is_blocked(self):
        ok, _ = server.is_safe_command("net user admin password")
        self.assertFalse(ok)

    def test_net_start_is_blocked(self):
        ok, _ = server.is_safe_command("net start wuauserv")
        self.assertFalse(ok)

    def test_sc_is_blocked(self):
        ok, _ = server.is_safe_command("sc stop service")
        self.assertFalse(ok)

    def test_stop_process_is_blocked(self):
        ok, _ = server.is_safe_command("stop-process -Name chrome")
        self.assertFalse(ok)

    # ── Command chaining / escape still blocked ──
    def test_ampersand_chaining_blocked(self):
        ok, _ = server.is_safe_command("dir & del file.txt")
        self.assertFalse(ok)

    def test_backtick_escape_blocked(self):
        ok, _ = server.is_safe_command("dir `; del file.txt")
        self.assertFalse(ok)

    # ── Still unknown / edge cases ──
    def test_empty_is_unsafe(self):
        ok, msg = server.is_safe_command("")
        self.assertFalse(ok)
        self.assertIn("不能为空", msg)

    def test_unknown_prefix_is_unsafe(self):
        ok, _ = server.is_safe_command("sudo rm -rf /")
        self.assertFalse(ok)

    def test_findstr_is_safe(self):
        ok, _ = server.is_safe_command("findstr /n test server.py")
        self.assertTrue(ok)

    def test_get_childitem_is_safe(self):
        ok, _ = server.is_safe_command("Get-ChildItem . -Recurse")
        self.assertTrue(ok)

    def test_npx_is_safe(self):
        ok, _ = server.is_safe_command("npx jest")
        self.assertTrue(ok)


class TestParseMemoryFrontmatter(unittest.TestCase):
    def test_with_frontmatter(self):
        text = "---\nname: test-memory\ndescription: A test\n---\n\nThis is the body."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"name": "test-memory", "description": "A test"})
        self.assertEqual(body, "This is the body.")

    def test_no_frontmatter(self):
        text = "Just a plain body without frontmatter."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_empty_frontmatter(self):
        # Adjacent --- with nothing between doesn't match the regex
        text = "---\n---\n\nBody here."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_frontmatter_no_trailing_newline(self):
        text = "---\nkey: value\n---\nBody"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"key": "value"})
        self.assertEqual(body, "Body")

    def test_frontmatter_multiline_body(self):
        text = "---\ntitle: Multi\n---\n\nLine 1\nLine 2\n\nLine 3"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"title": "Multi"})
        self.assertIn("Line 1", body)
        self.assertIn("Line 3", body)

    def test_looks_like_frontmatter_but_not_at_start(self):
        text = "Some text\n---\nkey: value\n---\nBody"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)


class TestBuildMemoryFile(unittest.TestCase):
    def test_basic(self):
        result = server.build_memory_file(
            {"name": "test", "description": "A test memory"},
            "This is the body content."
        )
        expected = (
            "---\n"
            "name: test\n"
            "description: A test memory\n"
            "---\n"
            "\n"
            "This is the body content."
        )
        self.assertEqual(result, expected)

    def test_empty_meta(self):
        result = server.build_memory_file({}, "body")
        self.assertEqual(result, "---\n---\n\nbody")

    def test_empty_body(self):
        result = server.build_memory_file({"key": "val"}, "")
        self.assertEqual(result, "---\nkey: val\n---\n\n")

    def test_roundtrip(self):
        meta = {"name": "rt", "description": "roundtrip test", "type": "note"}
        body = "Line 1\nLine 2"
        built = server.build_memory_file(meta, body)
        parsed_meta, parsed_body = server.parse_memory_frontmatter(built)
        self.assertEqual(parsed_meta, meta)
        self.assertEqual(parsed_body, body)


class TestMakeUnifiedDiff(unittest.TestCase):
    def test_no_change(self):
        diff = server.make_unified_diff("abc", "abc", "file.txt")
        self.assertEqual(diff, "")

    def test_add_line(self):
        diff = server.make_unified_diff("line1\n", "line1\nline2\n", "test.txt")
        self.assertIn("+++ b/test.txt", diff)
        self.assertIn("+line2", diff)

    def test_remove_line(self):
        diff = server.make_unified_diff("line1\nline2\n", "line1\n", "test.txt")
        self.assertIn("--- a/test.txt", diff)
        self.assertIn("-line2", diff)

    def test_modify_line(self):
        diff = server.make_unified_diff("old\n", "new\n", "test.txt")
        self.assertIn("-old", diff)
        self.assertIn("+new", diff)

    def test_ignores_line_ending_style(self):
        diff = server.make_unified_diff("line1\r\nline2\r\n", "line1\nline2\n", "test.txt")
        self.assertEqual(diff, "")

    def test_ignores_final_newline_only(self):
        diff = server.make_unified_diff("line1", "line1\n", "test.txt")
        self.assertEqual(diff, "")

    def test_normalizes_accidentally_doubled_windows_newlines(self):
        source = "line1\r\r\nline2\r\r\n"
        self.assertEqual(server.normalize_text_newlines(source), "line1\nline2\n")

    def test_fuzzy_edit_remains_actionable_after_newline_normalization(self):
        old = server.normalize_text_newlines(
            'def greet(name):\r\r\n    return "Hello " + name\r\r\n\r\r\n'
            'def farewell(name):\r\r\n    return "Goodbye " + name\r\r\n'
        )
        old_fragment = 'def greet(name):\n    return "Hello " + name\n\ndef farewell(name):\n    return "Goodbye " + name'
        new_fragment = 'def greet(name):\n    return f"Hello {name}"\n\ndef farewell(name):\n    return f"Goodbye {name}"'
        found = server.CodeHandler._fuzzy_find(None, old, old_fragment)
        self.assertEqual(found, old_fragment)
        updated = old.replace(found, new_fragment, 1)
        diff = server.make_unified_diff(old, updated, "test_utils.py")
        self.assertIn('+    return f"Hello {name}"', diff)
        self.assertIn('+    return f"Goodbye {name}"', diff)


class TestNowIso(unittest.TestCase):
    def test_returns_string(self):
        self.assertIsInstance(server.now_iso(), str)

    def test_valid_iso_format(self):
        result = server.now_iso()
        self.assertIsNotNone(
            re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", result),
            f"Expected ISO 8601 format, got: {result}"
        )


class TestToProjectRelative(unittest.TestCase):
    def test_posix_path(self):
        root = Path("/home/user/project")
        target = Path("/home/user/project/sub/dir/file.py")
        result = server.to_project_relative(root, target)
        self.assertEqual(result, "sub/dir/file.py")

    def test_same_directory(self):
        root = Path("/project")
        target = Path("/project")
        result = server.to_project_relative(root, target)
        self.assertEqual(result, ".")


# ─── 2026-07-07: security / performance regression tests ───

class TestSubprocessKwargs(unittest.TestCase):
    """Verify DETACHED_PROCESS is no longer used (breaks stdout capture)."""
    def test_no_detached_process_flag(self):
        kwargs = server._hidden_subprocess_kwargs()
        if not kwargs:  # non-Windows
            self.assertTrue(True)
            return
        flags = kwargs["creationflags"]
        DETACHED = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        self.assertEqual(flags, CREATE_NO_WINDOW,
                         f"DETACHED_PROCESS flag present! Got 0x{flags:08x}, expected 0x{CREATE_NO_WINDOW:08x}")
        self.assertFalse(flags & DETACHED,
                         f"DETACHED_PROCESS must not be set, got 0x{flags:08x}")


class TestSkipDirs(unittest.TestCase):
    """Verify expanded SKIP_DIRS covers common large directories."""
    def test_appdata_skipped(self):
        self.assertIn("AppData", server.SKIP_DIRS)

    def test_vscode_skipped(self):
        self.assertIn(".vscode", server.SKIP_DIRS)

    def test_node_modules_skipped(self):
        self.assertIn("node_modules", server.SKIP_DIRS)

    def test_one_drive_skipped(self):
        self.assertIn("OneDrive", server.SKIP_DIRS)

    def test_cookies_skipped(self):
        self.assertIn("Cookies", server.SKIP_DIRS)

    def test_npm_skipped(self):
        self.assertIn(".npm", server.SKIP_DIRS)

    def test_min_size(self):
        self.assertGreater(len(server.SKIP_DIRS), 50,
                           f"SKIP_DIRS only has {len(server.SKIP_DIRS)} entries, expected 50+")


class TestDeniedRuntimePattern(unittest.TestCase):
    """Verify DENIED_RUNTIME_PATTERN is disabled (python -c / node -e allowed)."""
    def test_denied_runtime_removed(self):
        self.assertFalse(hasattr(server, "DENIED_RUNTIME_PATTERN"),
                         "DENIED_RUNTIME_PATTERN should not exist — python -c / node -e must be allowed")


class TestDeniedCommandPattern(unittest.TestCase):
    """Verify DENIED_COMMAND_PATTERN correctly blocks/allows."""
    def test_does_not_block_semicolon_alone(self):
        # `;` should NOT be in the character class; only `&` and backtick
        self.assertFalse(server.DENIED_COMMAND_PATTERN.search("python -c a=1 print a"),  # no ;/&/` in this
                         "DENIED pattern should not match safe Python")

    def test_does_not_block_pipe(self):
        self.assertIsNone(server.DENIED_COMMAND_PATTERN.search("dir | findstr x"))

    def test_blocks_del(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("del file.txt"))

    def test_blocks_ampersand(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("dir & del"))

    def test_blocks_backtick(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("dir `; del"))


class TestSafeCommandPrefixes(unittest.TestCase):
    """Verify whitelist has expected entries."""
    def test_python_c_in_prefixes(self):
        self.assertIn("python -c ", server.SAFE_COMMAND_PREFIXES)

    def test_pip_in_prefixes(self):
        self.assertIn("pip ", server.SAFE_COMMAND_PREFIXES)

    def test_curl_in_prefixes(self):
        self.assertIn("curl ", server.SAFE_COMMAND_PREFIXES)

    def test_cat_in_prefixes(self):
        self.assertIn("cat ", server.SAFE_COMMAND_PREFIXES)

    def test_mkdir_in_prefixes(self):
        self.assertIn("mkdir ", server.SAFE_COMMAND_PREFIXES)

    def test_set_content_in_prefixes(self):
        self.assertIn("set-content ", server.SAFE_COMMAND_PREFIXES)

    def test_min_count(self):
        self.assertGreater(len(server.SAFE_COMMAND_PREFIXES), 100,
                           f"Only {len(server.SAFE_COMMAND_PREFIXES)} prefixes, expected 100+")


class TestLauncherInstall(unittest.TestCase):
    """Tests for launcher.py install and shortcut logic."""

    def test_get_code_home(self):
        result = launcher.get_code_home()
        self.assertEqual(result, Path.home() / ".code")

    def test_ensure_installed_noop_in_dev(self):
        """ensure_installed is a no-op when sys.frozen is False (dev mode)."""
        self.assertFalse(getattr(sys, "frozen", False),
                         "Test must run in dev mode for this assertion")
        # Should return immediately without raising
        launcher.ensure_installed()

    def test_create_desktop_shortcut_ps_script(self):
        """The PowerShell script embeds the correct target path."""
        exe = Path(r"C:\Users\Test\.code\Code-v9.9.9.exe")
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch("launcher._append_log"):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "ok"
            ok = launcher.create_desktop_shortcut(exe)
        self.assertTrue(ok)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "powershell")
        ps_script = args[4]
        self.assertIn(str(exe).replace("'", "''"), ps_script)
        self.assertIn("Code.lnk", ps_script)
        self.assertIn("WScript.Shell", ps_script)

    def test_create_desktop_shortcut_logs_on_failure(self):
        """Non-zero exit code or missing 'ok' result is logged."""
        exe = Path(r"C:\Users\Test\.code\Code-v9.9.9.exe")
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch("launcher._append_log") as mock_log:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "error"
            ok = launcher.create_desktop_shortcut(exe)
        self.assertFalse(ok)
        # Verify _append_log was called with an error message
        self.assertTrue(mock_log.called)
        log_call_msg = mock_log.call_args[0][1]
        self.assertIn("Shortcut creation failed", log_call_msg)


class TestCodexImport(unittest.TestCase):
    """Tests for Codex session import (list, parse, convert, import)."""

    def _make_codex_jsonl(self, messages, session_id="019f91af-test-session",
                          created_at="2026-07-24T10:00:00Z"):
        """Build a Codex-format JSONL string from simplified message tuples.

        Each tuple: (role, text)  e.g. ("user", "hello")
        """
        lines = []
        # session_meta
        lines.append(json.dumps({
            "type": "session_meta",
            "timestamp": created_at,
            "payload": {"session_id": session_id, "timestamp": created_at,
                        "cwd": "/home/test", "originator": "codex-tui",
                        "cli_version": "0.145.0", "source": "cli",
                        "thread_source": "user", "model_provider": "custom",
                        "history_mode": "legacy"}
        }))
        # messages
        for role, text in messages:
            lines.append(json.dumps({
                "type": "response_item",
                "timestamp": created_at,
                "payload": {"type": "message", "role": role,
                            "content": [{"type": "input_text", "text": text}]}
            }))
        return "\n".join(lines) + "\n"

    def test_list_codex_sessions_detects_valid_file(self):
        """A valid Codex JSONL appears in the session list."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl = codex_dir / "test-session.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "帮我写一个 Python 脚本"),
                ("assistant", "好的，这是脚本..."),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR",
                                   Path(td)):
                sessions = server.list_codex_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        self.assertIn("Python 脚本", sessions[0]["title"])
        self.assertGreater(sessions[0]["messageCount"], 0)  # estimated from file size
        self.assertEqual(sessions[0]["sourceId"], "test-session")
        self.assertEqual(sessions[0]["source"], "codex")
        self.assertEqual(
            sessions[0]["cwd"],
            server._normalize_local_path("/home/test"),
        )
        self.assertTrue(sessions[0]["sourcePath"].endswith(".jsonl"))

    def test_list_codex_sessions_search_by_filename(self):
        """Query parameter filters by filename."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl_a = codex_dir / "project-alpha.jsonl"
            jsonl_a.write_text(self._make_codex_jsonl([
                ("user", "Alpha project task"),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            jsonl_b = codex_dir / "project-beta.jsonl"
            jsonl_b.write_text(self._make_codex_jsonl([
                ("user", "Beta project task"),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                all_sessions = server.list_codex_sessions()
                alpha_only = server.list_codex_sessions(query="alpha")
        self.assertEqual(len(all_sessions), 2)
        self.assertEqual(len(alpha_only), 1)
        self.assertIn("Alpha", alpha_only[0]["title"])

    def test_list_codex_sessions_empty_dir(self):
        """Empty or non-existent directory returns empty list."""
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(server, "CODEX_SESSIONS_DIR",
                                   Path(td) / "nonexistent"):
                sessions = server.list_codex_sessions()
        self.assertEqual(sessions, [])

    def test_read_codex_session_meta_extracts_title_and_count(self):
        """_read_codex_session_meta returns title and estimated count."""
        with tempfile.TemporaryDirectory() as td:
            jsonl = Path(td) / "test.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "项目交接测试"),
                ("assistant", "收到，开始处理"),
                ("user", "第二步"),
                ("assistant", "好的"),
            ]), encoding="utf-8")
            meta = server._read_codex_session_meta(jsonl)
        self.assertEqual(meta["title"], "项目交接测试")
        self.assertGreater(meta["message_count"], 0)  # estimated from file size
        self.assertEqual(meta["cwd"], server._normalize_local_path("/home/test"))

    def test_codex_user_wrapper_sanitizer_retains_only_actual_request(self):
        ambient = (
            '<in-app-browser-context source="ambient-ui-state">\n'
            "# In app browser:\n- Current URL: http://127.0.0.1:3010/\n"
            "</in-app-browser-context>\n\n"
            "## My request for Codex:\nContinue the import task"
        )
        self.assertEqual(
            server._sanitize_codex_user_text(ambient),
            "Continue the import task",
        )
        injected_only = (
            "<recommended_plugins>\n- Example\n</recommended_plugins>"
            "# AGENTS.md instructions for C:\\workspace\n"
            "<INSTRUCTIONS>\nRules\n</INSTRUCTIONS>"
            "<environment_context>\n<cwd>C:\\workspace</cwd>\n</environment_context>"
        )
        self.assertEqual(server._sanitize_codex_user_text(injected_only), "")
        self.assertEqual(
            server._sanitize_codex_user_text(
                "<environment_context>\n<cwd>C:\\workspace</cwd>\n"
                "</environment_context>"
            ),
            "",
        )
        self.assertEqual(
            server._sanitize_codex_user_text("<turn_aborted>Stopped</turn_aborted>"),
            "",
        )
        self.assertEqual(
            server._sanitize_codex_user_text(
                "<command-name>/login</command-name>"
                "<command-message>login</command-message>"
                "<command-args></command-args>"
            ),
            "/login",
        )

    def test_read_codex_title_uses_request_inside_ambient_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "wrapped.jsonl"
            source.write_text(self._make_codex_jsonl([
                (
                    "user",
                    '<in-app-browser-context source="ambient-ui-state">\n'
                    "browser state\n</in-app-browser-context>\n"
                    "## My request for Codex:\nActual imported title",
                ),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            self.assertEqual(
                server._read_codex_title(source),
                "Actual imported title",
            )
            self.assertEqual(
                server._read_codex_session_meta(source)["title"],
                "Actual imported title",
            )

    def test_import_codex_session_creates_code_files(self):
        """Import creates .jsonl, .json, and updates index."""
        with tempfile.TemporaryDirectory() as td:
            codex_file = Path(td) / "codex-session.jsonl"
            codex_file.write_text(self._make_codex_jsonl([
                ("user", "这是第一条消息"),
                ("assistant", "这是回复"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "code-sessions"
            sessions_dir.mkdir()
            idx = sessions_dir / "index.jsonl"
            idx.write_text("", encoding="utf-8")
            # import now uses created_at from messages (2026-07-24) for date_dir
            date_dir = sessions_dir / "2026" / "07" / "24"
            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_codex_session(str(codex_file))

            self.assertEqual(meta["title"], "这是第一条消息")
            self.assertEqual(meta["messageCount"], 2)
            self.assertEqual(meta["source"], "codex")
            self.assertEqual(meta["cwd"], server._normalize_local_path("/home/test"))
            self.assertIsNone(meta["projectId"])
            self.assertTrue(meta["id"])

            jsonl_files = list(date_dir.glob("*.jsonl"))
            json_files = list(date_dir.glob("*.json"))
            self.assertEqual(len(jsonl_files), 1)
            self.assertEqual(len(json_files), 1)

            msgs = server.read_jsonl(jsonl_files[0])
            self.assertEqual(len(msgs), 3)
            self.assertEqual(msgs[0]["role"], "system")
            self.assertEqual(msgs[0]["meta"]["kind"], "import-boundary")
            self.assertTrue(msgs[0]["meta"]["_system"])
            self.assertEqual(msgs[1]["role"], "user")
            self.assertEqual(msgs[1]["content"], "这是第一条消息")
            stored = server.read_json(json_files[0], {})
            self.assertNotIn("group", stored)
            index_entry = {
                item["id"]: item
                for item in (
                    json.loads(line)
                    for line in idx.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            }[meta["id"]]
            self.assertEqual(index_entry["source"], "codex")
            self.assertNotIn("group", index_entry)
            self.assertNotIn("project", index_entry)

    def test_reimport_unchanged_codex_session_is_idempotent(self):
        """An unchanged source is a no-op and does not duplicate the index."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            index_path = sessions_dir / "index.jsonl"
            index_path.write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                index_after_first = index_path.read_text(encoding="utf-8")
                second = server.import_codex_session(str(source))

            self.assertEqual(first["importAction"], "created")
            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(
                index_path.read_text(encoding="utf-8"),
                index_after_first,
            )
            stored_meta = server.read_json(
                next(sessions_dir.rglob(f"{first['id']}.json")),
                {},
            )
            self.assertEqual(stored_meta["importState"]["source"], "codex")
            self.assertEqual(len(stored_meta["importState"]["sourceSha256"]), 64)
            self.assertFalse(stored_meta["importState"]["codeModified"])
            self.assertEqual(
                len(list(sessions_dir.rglob(f"{first['id']}.json"))),
                1,
            )

    def test_reimport_updated_pristine_codex_session_refreshes_in_place(self):
        """A source update replaces a pristine imported snapshot in place."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "Source follow-up"),
                    ("assistant", "Updated source response"),
                ]), encoding="utf-8")
                second = server.import_codex_session(str(source))

            self.assertEqual(second["importAction"], "updated")
            self.assertEqual(second["id"], first["id"])
            stored = server.read_jsonl(
                next(sessions_dir.rglob(f"{first['id']}.jsonl"))
            )
            self.assertIn(
                "Source follow-up",
                [item.get("content") for item in stored],
            )
            self.assertEqual(
                len(list(sessions_dir.rglob(f"{first['id']}.json"))),
                1,
            )

    def test_reimport_touched_codex_source_refreshes_locator_only(self):
        """Metadata-only source changes settle after one authoritative recheck."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "codex"
            codex_dir.mkdir()
            source = codex_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(server, "CODEX_SESSIONS_DIR", codex_dir):
                first = server.import_codex_session(str(source))
                source_stat = source.stat()
                os.utime(
                    source,
                    ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns + 1_000_000),
                )
                touched = server.list_codex_sessions()[0]
                second = server.import_codex_session(str(source))
                settled = server.list_codex_sessions()[0]

            self.assertEqual(touched["importStatus"], "update-available")
            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(settled["importStatus"], "imported")
            self.assertFalse(settled["canImport"])

    def test_reimport_moved_codex_source_matches_stable_source_session_id(self):
        """Moving a source file does not create a second imported session."""
        with tempfile.TemporaryDirectory() as td:
            first_dir = Path(td) / "first"
            second_dir = Path(td) / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            source = first_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                moved = second_dir / source.name
                source.rename(moved)
                second = server.import_codex_session(str(moved))

            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(
                second["importState"]["sourcePathKey"],
                server._path_identity(moved),
            )
            self.assertEqual(
                len(list(sessions_dir.rglob("codex-*.json"))),
                1,
            )

    def test_reimport_updated_continued_codex_session_creates_one_snapshot(self):
        """A source update never overwrites messages added later in Code."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            index_path = sessions_dir / "index.jsonl"
            index_path.write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                root_messages_path = next(
                    sessions_dir.rglob(f"{first['id']}.jsonl")
                )
                root_messages = server.read_jsonl(root_messages_path)
                root_messages.extend([
                    {"role": "user", "content": "Continued in Code"},
                    {"role": "assistant", "content": "Code-side response"},
                ])
                server.write_jsonl(root_messages_path, root_messages)

                unchanged = server.import_codex_session(str(source))
                self.assertEqual(unchanged["importAction"], "continued")

                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "New source turn"),
                    ("assistant", "New source response"),
                ]), encoding="utf-8")
                snapshot = server.import_codex_session(str(source))
                index_after_snapshot = index_path.read_text(encoding="utf-8")
                repeated = server.import_codex_session(str(source))

            self.assertEqual(snapshot["importAction"], "snapshot-created")
            self.assertNotEqual(snapshot["id"], first["id"])
            self.assertEqual(snapshot["importRootSessionId"], first["id"])
            self.assertEqual(
                snapshot["importState"]["previousSessionId"],
                first["id"],
            )
            self.assertEqual(repeated["importAction"], "unchanged")
            self.assertEqual(repeated["id"], snapshot["id"])
            self.assertEqual(
                index_path.read_text(encoding="utf-8"),
                index_after_snapshot,
            )

            preserved_root = server.read_jsonl(root_messages_path)
            self.assertIn(
                "Continued in Code",
                [item.get("content") for item in preserved_root],
            )
            snapshot_messages = server.read_jsonl(
                next(sessions_dir.rglob(f"{snapshot['id']}.jsonl"))
            )
            snapshot_contents = [item.get("content") for item in snapshot_messages]
            self.assertIn("New source turn", snapshot_contents)
            self.assertNotIn("Continued in Code", snapshot_contents)

    def test_codex_import_listing_reports_repeated_import_state(self):
        """The picker distinguishes imported, continued, and conflict states."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "codex"
            codex_dir.mkdir()
            source = codex_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(server, "CODEX_SESSIONS_DIR", codex_dir):
                before = server.list_codex_sessions()[0]
                imported = server.import_codex_session(str(source))
                after = server.list_codex_sessions()[0]

                meta_path = next(sessions_dir.rglob(f"{imported['id']}.json"))
                messages_path = meta_path.with_suffix(".jsonl")
                messages = server.read_jsonl(messages_path)
                messages.append({"role": "user", "content": "Continued in Code"})
                server.write_jsonl(messages_path, messages)
                meta = server.read_json(meta_path, {})
                server._refresh_import_divergence(meta, messages)
                server.write_json(meta_path, meta)
                continued = server.list_codex_sessions()[0]

                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "New source turn"),
                    ("assistant", "New source response"),
                ]), encoding="utf-8")
                conflict = server.list_codex_sessions()[0]

            self.assertEqual(before["importStatus"], "available")
            self.assertTrue(before["canImport"])
            self.assertEqual(after["importStatus"], "imported")
            self.assertFalse(after["canImport"])
            self.assertEqual(continued["importStatus"], "continued")
            self.assertFalse(continued["canImport"])
            self.assertEqual(conflict["importStatus"], "update-conflict")
            self.assertTrue(conflict["canImport"])

    def test_import_codex_preserves_safe_history_and_usage(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-complex.jsonl"
            timestamp = "2026-07-24T10:00:00.123Z"
            image_data = "aGVsbG8="
            large_output = "HEAD-" + ("x" * 14000) + "-TAIL"
            records = [
                {
                    "type": "session_meta",
                    "timestamp": timestamp,
                    "payload": {"cwd": "/home/test/codex"},
                },
                {
                    "type": "turn_context",
                    "timestamp": timestamp,
                    "payload": {"model": "gpt-test"},
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Inspect this image"},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{image_data}",
                            },
                        ],
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {"type": "agent_reasoning", "text": "Check the file first."},
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "Use a safe read."}],
                        "encrypted_content": "must-not-be-imported",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "function_call",
                        "name": "read_file",
                        "arguments": '{"path":"example.txt"}',
                        "call_id": "call-1",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": large_output,
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Inspection complete."}],
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 101,
                                "cached_input_tokens": 11,
                                "output_tokens": 20,
                            },
                            "last_token_usage": {
                                "input_tokens": 12,
                                "cached_input_tokens": 3,
                                "output_tokens": 4,
                            },
                        },
                    },
                },
            ]
            source.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_codex_session(str(source))
                # Re-importing the same source replaces the deterministic target.
                server.import_codex_session(str(source))

            stored_path = next(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            messages = server.read_jsonl(stored_path)
            boundaries = [
                item for item in messages
                if item.get("meta", {}).get("kind") == "import-boundary"
            ]
            self.assertEqual(len(boundaries), 1)
            self.assertIn("migrated from Codex", boundaries[0]["content"])
            self.assertIn(
                "using only the tools that Code currently makes available",
                boundaries[0]["content"],
            )

            user = next(item for item in messages if item.get("role") == "user")
            self.assertEqual(server._import_message_text(user), "Inspect this image")
            self.assertEqual(user["_model"], "gpt-test")
            self.assertEqual(user["_time"], timestamp)
            self.assertEqual(user["_images"][0]["base64"], image_data)
            self.assertEqual(user["content"][1]["type"], "image_url")

            call = next(item for item in messages if item.get("role") == "tool-call")
            result = next(item for item in messages if item.get("role") == "tool-result")
            for trace in (call, result):
                self.assertTrue(trace["meta"]["skipApi"])
                self.assertTrue(trace["meta"]["imported"])
                self.assertFalse(trace["meta"]["native"])
                self.assertFalse(trace["meta"]["replayable"])
                self.assertEqual(trace["meta"]["toolCallId"], "call-1")
            self.assertEqual(call["meta"]["action"], "read_file")
            self.assertTrue(result["meta"]["importedPayloadTruncated"])
            self.assertEqual(result["meta"]["importedOriginalChars"], len(large_output))
            self.assertEqual(len(result["meta"]["importedSha256"]), 64)
            self.assertIn("HEAD-", result["content"])
            self.assertIn("-TAIL", result["content"])
            self.assertNotIn("must-not-be-imported", json.dumps(messages))

            assistant = next(
                item for item in messages if item.get("role") == "assistant"
            )
            self.assertIn("Check the file first.", assistant["thought"])
            self.assertIn("Use a safe read.", assistant["thought"])
            self.assertEqual(
                assistant["meta"]["_usage"],
                {"input": 12, "output": 4, "cache": 3},
            )
            self.assertEqual(
                meta["stats"],
                {"input": 101, "output": 20, "cache": 11},
            )
            self.assertEqual(meta["lastUsage"], {"input": 12, "output": 4, "cache": 3})
            self.assertEqual(meta["messageCount"], len(messages) - 1)

    def test_import_codex_session_rejects_nonexistent_file(self):
        with self.assertRaises(ValueError):
            server.import_codex_session("/nonexistent/path.jsonl")

    def test_import_codex_session_rejects_empty(self):
        """A file with no valid messages raises ValueError."""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty.jsonl"
            empty.write_text(
                '{"type":"session_meta","payload":{"session_id":"x"}}\n',
                encoding="utf-8")
            with self.assertRaises(ValueError):
                server.import_codex_session(str(empty))

    def test_generate_import_id_is_stable(self):
        """Same path produces same import ID."""
        id1 = server._generate_codex_import_id(
            Path("C:/Users/Admin/.codex/sessions/2026/07/24/test.jsonl"))
        id2 = server._generate_codex_import_id(
            Path("C:/Users/Admin/.codex/sessions/2026/07/24/test.jsonl"))
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("codex-"))

    def test_list_codex_sessions_includes_small_files(self):
        """Even small Codex session files appear (count estimated from file size)."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl = codex_dir / "small.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "hi"),
                ("assistant", "hello"),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_codex_sessions()
        self.assertEqual(len(sessions), 1)

    # ── Claude Code import tests ──

    def _make_claude_jsonl(self, messages):
        """Build a Claude Code-format JSONL from (role, text) tuples."""
        lines = []
        for role, text in messages:
            content = text if role == "user" else [{"type": "text", "text": text}]
            lines.append(json.dumps({
                "type": role,
                "message": {"role": role, "content": content},
                "timestamp": "2026-07-24T10:00:00.000Z",
                "sessionId": "test-claude-session",
                "cwd": "/home/test/project",
            }))
        return "\n".join(lines) + "\n"

    def test_list_claude_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "my-project"
            proj.mkdir(parents=True)
            jsonl = proj / "abc123.jsonl"
            jsonl.write_text(self._make_claude_jsonl([
                ("user", "帮我优化数据库查询"),
                ("assistant", "好的，先看看现有代码"),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CLAUDE_PROJECTS_DIR", Path(td)):
                sessions = server.list_claude_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["title"], "帮我优化数据库查询")
        self.assertEqual(sessions[0]["messageCount"], 2)
        self.assertEqual(sessions[0]["project"], "my-project")
        self.assertEqual(sessions[0]["source"], "claude-code")
        self.assertEqual(
            sessions[0]["cwd"],
            server._normalize_local_path("/home/test/project"),
        )
        self.assertTrue(sessions[0]["id"].startswith("claude-"))

    def test_list_claude_sessions_excludes_sidechain_agent_files(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "my-project"
            project.mkdir(parents=True)
            main = project / "main-session.jsonl"
            main.write_text(self._make_claude_jsonl([
                ("user", "Main session"),
                ("assistant", "Main reply"),
            ]), encoding="utf-8")
            sidechain = project / "agent-worker.jsonl"
            sidechain.write_text(
                json.dumps({
                    "type": "user",
                    "isSidechain": True,
                    "agentId": "worker",
                    "message": {"role": "user", "content": "Worker task"},
                    "timestamp": "2026-07-24T10:00:00.000Z",
                }) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(server, "CLAUDE_PROJECTS_DIR", Path(td)):
                sessions = server.list_claude_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["sourceId"], "main-session")

    def test_import_claude_session(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl = Path(td) / "session.jsonl"
            jsonl.write_text(self._make_claude_jsonl([
                ("user", "Claude 导入测试"),
                ("assistant", "收到，这是回复"),
                ("user", "继续第二步"),
                ("assistant", "好的"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "code-sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")
            date_dir = sessions_dir / "2026" / "07" / "24"
            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_claude_session(str(jsonl))
            self.assertEqual(meta["title"], "Claude 导入测试")
            self.assertEqual(meta["messageCount"], 4)
            self.assertEqual(meta["source"], "claude-code")
            self.assertEqual(
                meta["cwd"],
                server._normalize_local_path("/home/test/project"),
            )
            self.assertIsNone(meta["projectId"])
            # Find the created jsonl file (may be in any subdirectory)
            created = list(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            self.assertEqual(len(created), 1,
                            f"Expected 1 jsonl for {meta['id']}, found {len(created)} in {list(sessions_dir.rglob('*'))}")
            stored_files = list(sessions_dir.rglob(f"{meta['id']}.json"))
            self.assertEqual(len(stored_files), 1)
            stored = server.read_json(stored_files[0], {})
            self.assertNotIn("group", stored)
            index_entry = {
                item["id"]: item
                for item in (
                    json.loads(line)
                    for line in (sessions_dir / "index.jsonl").read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line.strip()
                )
            }[meta["id"]]
            self.assertEqual(index_entry["source"], "claude-code")

    def test_reimport_claude_session_uses_shared_idempotent_flow(self):
        """Claude imports expose the same unchanged and update states as Codex."""
        with tempfile.TemporaryDirectory() as td:
            claude_dir = Path(td) / "claude" / "project"
            claude_dir.mkdir(parents=True)
            source = claude_dir / "session.jsonl"
            source.write_text(self._make_claude_jsonl([
                ("user", "Initial Claude request"),
                ("assistant", "Initial Claude response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(
                     server,
                     "CLAUDE_PROJECTS_DIR",
                     claude_dir.parent,
                 ):
                first = server.import_claude_session(str(source))
                unchanged = server.import_claude_session(str(source))
                imported_row = server.list_claude_sessions()[0]
                source.write_text(self._make_claude_jsonl([
                    ("user", "Initial Claude request"),
                    ("assistant", "Initial Claude response"),
                    ("user", "New Claude turn"),
                    ("assistant", "New Claude response"),
                ]), encoding="utf-8")
                update_row = server.list_claude_sessions()[0]
                updated = server.import_claude_session(str(source))
                settled_row = server.list_claude_sessions()[0]

            self.assertEqual(first["importAction"], "created")
            self.assertEqual(unchanged["importAction"], "unchanged")
            self.assertEqual(unchanged["id"], first["id"])
            self.assertEqual(imported_row["importStatus"], "imported")
            self.assertFalse(imported_row["canImport"])
            self.assertEqual(update_row["importStatus"], "update-available")
            self.assertTrue(update_row["canImport"])
            self.assertEqual(updated["importAction"], "updated")
            self.assertEqual(updated["id"], first["id"])
            self.assertEqual(settled_row["importStatus"], "imported")

    def test_import_claude_preserves_main_trace_images_and_usage(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "claude-complex.jsonl"
            timestamp = "2026-07-24T10:00:00.000Z"
            records = [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "<system-reminder>foreign rules</system-reminder>"
                                    "Claude image task"
                                ),
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": "aW1hZ2U=",
                                },
                            },
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [
                            {"type": "thinking", "thinking": "Read the request."},
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [
                            {"type": "thinking", "thinking": "Inspect safely."},
                            {"type": "text", "text": "I will inspect it."},
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Read",
                                "input": {"file_path": "example.txt"},
                            },
                        ],
                        "usage": {
                            "input_tokens": 12,
                            "output_tokens": 5,
                            "cache_read_input_tokens": 3,
                        },
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "file contents",
                                "is_error": False,
                            },
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "user",
                    "isSidechain": True,
                    "message": {"role": "user", "content": "sidechain must be skipped"},
                    "timestamp": timestamp,
                },
                {
                    "type": "user",
                    "isMeta": True,
                    "message": {"role": "user", "content": "meta must be skipped"},
                    "timestamp": timestamp,
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [{"type": "text", "text": "Done."}],
                        "usage": {"input_tokens": 4, "output_tokens": 2},
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
            ]
            source.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_claude_session(str(source))

            messages = server.read_jsonl(
                next(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            )
            boundary = messages[0]
            self.assertEqual(boundary["meta"]["kind"], "import-boundary")
            self.assertEqual(boundary["meta"]["importSource"], "claude-code")
            self.assertIn("migrated from Claude Code", boundary["content"])
            serialized = json.dumps(messages)
            self.assertNotIn("foreign rules", serialized)
            self.assertNotIn("sidechain must be skipped", serialized)
            self.assertNotIn("meta must be skipped", serialized)

            user = next(item for item in messages if item.get("role") == "user")
            self.assertEqual(server._import_message_text(user), "Claude image task")
            self.assertEqual(user["_images"][0]["base64"], "aW1hZ2U=")
            assistant = next(
                item for item in messages
                if item.get("role") == "assistant" and item.get("thought")
            )
            self.assertEqual(
                assistant["thought"],
                "Read the request.\n\nInspect safely.",
            )
            self.assertEqual(
                assistant["meta"]["_usage"],
                {"input": 12, "output": 5, "cache": 3},
            )
            call = next(item for item in messages if item.get("role") == "tool-call")
            result = next(item for item in messages if item.get("role") == "tool-result")
            self.assertEqual(call["meta"]["action"], "Read")
            self.assertEqual(result["meta"]["action"], "Read")
            self.assertEqual(call["meta"]["toolCallId"], result["meta"]["toolCallId"])
            self.assertTrue(call["meta"]["skipApi"])
            self.assertTrue(result["meta"]["skipApi"])
            self.assertIn('"is_error": false', result["content"])
            self.assertEqual(meta["stats"], {"input": 16, "output": 7, "cache": 3})
            self.assertEqual(meta["lastUsage"], {"input": 4, "output": 2, "cache": 0})
            self.assertEqual(meta["messageCount"], len(messages) - 1)

    def test_unified_list_api(self):
        """list_importable_sessions dispatches correctly."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            (codex_dir / "test.jsonl").write_text(self._make_codex_jsonl([
                ("user", "测试"), ("assistant", "好的")
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_importable_sessions("codex")
            self.assertGreaterEqual(len(sessions), 1)
        # Unknown source
        with self.assertRaises(ValueError):
            server.list_importable_sessions("unknown-source")


if __name__ == "__main__":
    unittest.main()
