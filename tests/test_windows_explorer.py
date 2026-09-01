"""Deterministic tests for Windows Explorer selection and foreground handling."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server
from code_runtime import windows_explorer


class _Shell:
    def __init__(self, *, fail_select=None, fail_open=None):
        self.selected = []
        self.opened = []
        self.fail_select = fail_select
        self.fail_open = fail_open

    def select_file(self, path):
        self.selected.append(Path(path))
        if self.fail_select:
            raise RuntimeError(self.fail_select)

    def open_folder(self, path):
        self.opened.append(Path(path))
        if self.fail_open:
            raise RuntimeError(self.fail_open)


class _Provider:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0
        self.timeouts = []

    def list_windows(self, timeout=None):
        self.timeouts.append(timeout)
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        value = self.snapshots[index]
        if isinstance(value, Exception):
            raise value
        return value


class _WindowApi:
    def __init__(self, *, iconic=False, foreground_results=(True,), fail_pulse=False,
                 fail_cleanup=False):
        self.iconic = iconic
        self.foreground_results = list(foreground_results)
        self.fail_pulse = fail_pulse
        self.fail_cleanup = fail_cleanup
        self.foreground = 0
        self.events = []

    def is_iconic(self, hwnd):
        self.events.append(("is_iconic", hwnd))
        return self.iconic

    def restore(self, hwnd):
        self.events.append(("restore", hwnd))

    def set_foreground(self, hwnd):
        self.events.append(("foreground", hwnd))
        if self.fail_pulse and any(event[0] == "topmost_on" for event in self.events):
            raise RuntimeError("foreground boom")
        result = self.foreground_results.pop(0) if self.foreground_results else False
        if result:
            self.foreground = hwnd
        return result

    def get_foreground(self):
        self.events.append(("get_foreground", self.foreground))
        return self.foreground

    def set_topmost(self, hwnd, enabled):
        self.events.append(("topmost_on" if enabled else "topmost_off", hwnd))
        if not enabled and self.fail_cleanup:
            raise RuntimeError("cleanup boom")


class _Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class TestWindowsExplorerPureContracts(unittest.TestCase):
    def test_windows_path_identity_preserves_unicode_spaces_and_long_paths(self):
        self.assertEqual(
            windows_explorer.normalize_windows_path(r"\\?\C:\Users\Admin\中文 空格\..\文件.txt"),
            r"c:\users\admin\文件.txt",
        )
        self.assertEqual(
            windows_explorer.normalize_windows_path(r"C:/Users/Admin/한글/파일.txt"),
            r"c:\users\admin\한글\파일.txt",
        )
        long_tail = "\\".join(["segment"] * 50)
        self.assertGreater(len(windows_explorer.normalize_windows_path(f"C:\\{long_tail}")), 260)

    def test_nearest_existing_directory_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            existing = root / "已有 空格"
            existing.mkdir()
            missing = existing / "深层" / "目标.txt"
            self.assertEqual(
                windows_explorer.nearest_existing_directory(missing, root),
                existing,
            )
            self.assertEqual(
                windows_explorer.nearest_existing_directory(existing, root),
                existing,
            )
            with self.assertRaises(windows_explorer.ExplorerIntegrationError):
                windows_explorer.nearest_existing_directory(root.parent / "outside.txt", root)

    def test_exact_window_match_rejects_wrong_and_ambiguous_explorer_windows(self):
        target = r"C:\Work\中文 项目"
        windows = [
            {"hwnd": 10, "path": r"C:\Other"},
            {"hwnd": 20, "path": r"c:/work/中文 项目"},
        ]
        self.assertEqual(windows_explorer.exact_explorer_window(windows, target), (20, "unique"))
        windows.append({"hwnd": 30, "path": target})
        self.assertEqual(
            windows_explorer.exact_explorer_window(windows, target),
            (None, "ambiguous"),
        )
        self.assertEqual(
            windows_explorer.exact_explorer_window([{"hwnd": 10, "path": r"C:\Other"}], target),
            (None, "not_found"),
        )

    def test_shell_windows_provider_uses_path_not_title_and_bounds_failures(self):
        completed = subprocess.CompletedProcess(
            ["powershell"], 0, stdout='[{"hwnd":101,"path":"C:\\\\项目"}]', stderr="",
        )
        runner = mock.Mock(return_value=completed)
        provider = windows_explorer.ShellWindowsProvider(runner=runner)
        self.assertEqual(provider.list_windows(), [{"hwnd": 101, "path": r"C:\项目"}])
        command = runner.call_args.args[0]
        self.assertIn("Document.Folder.Self.Path", command[-1])
        self.assertIn("[Console]::OutputEncoding = $utf8", command[-1])
        self.assertIn("[Console]::OpenStandardOutput()", command[-1])
        self.assertIn("$utf8.GetBytes([string]$json)", command[-1])
        self.assertEqual(runner.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(runner.call_args.kwargs["errors"], "strict")
        self.assertNotIn("LocationName", command[-1])
        self.assertNotIn("AppActivate", command[-1])
        failing = windows_explorer.ShellWindowsProvider(
            runner=mock.Mock(side_effect=RuntimeError("secret upstream detail")),
        )
        with self.assertRaisesRegex(
            windows_explorer.ExplorerIntegrationError,
            "Explorer window enumeration failed",
        ) as caught:
            failing.list_windows()
        self.assertNotIn("secret", str(caught.exception))

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is unavailable")
    def test_powershell_utf8_wrapper_round_trips_unicode_without_local_code_page(self):
        script = windows_explorer._powershell_utf8_json_script(r"""
$value = [ordered]@{ hwnd = 101; path = 'C:\项目 空格\한글' }
$json = ConvertTo-Json -InputObject $value -Compress
""")
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=False,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            json.loads(completed.stdout.decode("utf-8", "strict")),
            {"hwnd": 101, "path": r"C:\项目 空格\한글"},
        )

    def test_source_uses_approved_shell_and_window_apis_only(self):
        source = Path(windows_explorer.__file__).read_text(encoding="utf-8")
        for required in (
            "SHOpenFolderAndSelectItems", "Document.Folder.Self.Path",
            "CoInitializeEx", "SetForegroundWindow", "SW_RESTORE",
            "HWND_TOPMOST", "HWND_NOTOPMOST",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "AppActivate", "SwitchToThisWindow", "AttachThreadInput",
            "SendInput", "keybd_event", "Alt+Tab",
        ):
            self.assertNotIn(forbidden, source)


class TestExplorerActivation(unittest.TestCase):
    def test_minimized_exact_window_restores_and_activates_without_pulse(self):
        api = _WindowApi(iconic=True, foreground_results=(True,))
        result = windows_explorer.activate_exact_window(101, api)
        self.assertEqual(result, {
            "foreground": "foreground", "restored": True, "topmostPulse": False,
        })
        self.assertIn(("restore", 101), api.events)
        self.assertNotIn(("topmost_on", 101), api.events)

    def test_rejected_foreground_uses_one_strict_topmost_pair(self):
        api = _WindowApi(foreground_results=(False, True))
        result = windows_explorer.activate_exact_window(202, api)
        self.assertEqual(result["foreground"], "topmost-pulse")
        self.assertTrue(result["topmostPulse"])
        self.assertEqual(
            [event for event in api.events if event[0].startswith("topmost")],
            [("topmost_on", 202), ("topmost_off", 202)],
        )

    def test_pulse_exception_still_removes_topmost(self):
        api = _WindowApi(foreground_results=(False,), fail_pulse=True)
        result = windows_explorer.activate_exact_window(303, api)
        self.assertEqual(result["foreground"], "not-confirmed")
        self.assertEqual(
            [event for event in api.events if event[0].startswith("topmost")],
            [("topmost_on", 303), ("topmost_off", 303)],
        )

    def test_topmost_cleanup_failure_is_fail_closed(self):
        api = _WindowApi(foreground_results=(False, True), fail_cleanup=True)
        with self.assertRaisesRegex(
            windows_explorer.ExplorerIntegrationError,
            "topmost cleanup failed",
        ):
            windows_explorer.activate_exact_window(404, api)
        self.assertEqual(api.events[-1], ("topmost_off", 404))


class TestWindowsExplorerController(unittest.TestCase):
    def _controller(self, shell, windows, api, **kwargs):
        return windows_explorer.WindowsExplorerController(
            shell_api=shell,
            window_provider=_Provider(windows),
            window_api=api,
            timeout=kwargs.pop("timeout", 0),
            **kwargs,
        )

    def test_file_selection_targets_parent_and_exact_hwnd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "中文 空格.txt"
            target.write_text("ok", encoding="utf-8")
            shell = _Shell()
            api = _WindowApi(foreground_results=(True,))
            controller = self._controller(
                shell, [[{"hwnd": 11, "path": str(root)}]], api,
            )
            result = controller.open(target, select_file=True, allowed_root=root)
            self.assertEqual(shell.selected, [target])
            self.assertEqual(shell.opened, [])
            self.assertEqual(result["action"], "select_file")
            self.assertTrue(result["selected"])
            self.assertFalse(result["degraded"])

    def test_directory_open_targets_directory_itself(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / "目录 空格"
            folder.mkdir()
            shell = _Shell()
            controller = self._controller(
                shell, [[{"hwnd": 12, "path": str(folder)}]], _WindowApi(),
            )
            result = controller.open(folder, select_file=False, allowed_root=root)
            self.assertEqual(shell.opened, [folder])
            self.assertEqual(result["action"], "open_folder")
            self.assertFalse(result["selected"])

    def test_missing_target_opens_nearest_parent_and_reports_degraded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / "exists"
            parent.mkdir()
            missing = parent / "missing" / "file.txt"
            shell = _Shell()
            controller = self._controller(
                shell, [[{"hwnd": 13, "path": str(parent)}]], _WindowApi(),
            )
            result = controller.open(missing, select_file=True, allowed_root=root)
            self.assertEqual(shell.opened, [parent])
            self.assertEqual(shell.selected, [])
            self.assertTrue(result["degraded"])
            self.assertEqual(result["degradedReasons"], ["target_missing"])

    def test_ambiguous_windows_are_never_activated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "file.txt"
            target.write_text("ok", encoding="utf-8")
            api = _WindowApi()
            controller = self._controller(
                _Shell(),
                [[{"hwnd": 14, "path": str(root)}, {"hwnd": 15, "path": str(root)}]],
                api,
            )
            result = controller.open(target, select_file=True, allowed_root=root)
            self.assertEqual(result["foreground"], "ambiguous")
            self.assertIn("window_match_ambiguous", result["degradedReasons"])
            self.assertEqual(api.events, [])

    def test_window_poll_timeout_is_bounded_and_does_not_activate_wrong_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "file.txt"
            target.write_text("ok", encoding="utf-8")
            clock = _Clock()
            api = _WindowApi()
            provider = _Provider([[{"hwnd": 16, "path": str(root / "other")}]])
            controller = windows_explorer.WindowsExplorerController(
                shell_api=_Shell(),
                window_provider=provider,
                window_api=api,
                timeout=0.2,
                poll_interval=0.05,
                clock=clock,
                sleeper=clock.sleep,
            )
            result = controller.open(target, select_file=True, allowed_root=root)
            self.assertEqual(result["foreground"], "window-not-found")
            self.assertGreaterEqual(sum(clock.sleeps), 0.2)
            self.assertTrue(all(0 <= timeout <= 0.2 for timeout in provider.timeouts))
            self.assertEqual(api.events, [])

    def test_shell_exceptions_are_bounded_and_do_not_leak_detail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "secret.txt"
            target.write_text("ok", encoding="utf-8")
            controller = self._controller(
                _Shell(fail_select="sensitive raw shell failure"), [[]], _WindowApi(),
            )
            with self.assertRaisesRegex(
                windows_explorer.ExplorerIntegrationError,
                "Explorer file selection failed",
            ) as caught:
                controller.open(target, select_file=True, allowed_root=root)
            self.assertNotIn("sensitive", str(caught.exception))


class TestServerOpenFileActions(unittest.TestCase):
    def test_windows_reveal_directory_default_and_explicit_explorer_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            file_path = root / "file.txt"
            file_path.write_text("ok", encoding="utf-8")
            folder = root / "folder"
            folder.mkdir()
            explorer = mock.Mock(return_value={"ok": True, "action": "select_file"})
            startfile = mock.Mock()
            with mock.patch("server.resolve_project_path", side_effect=[
                (root, file_path), (root, folder), (root, file_path),
            ]):
                reveal = server.perform_open_file_action(
                    {"path": "file.txt", "reveal": True},
                    platform_name="nt", explorer_open=explorer, startfile=startfile,
                )
                directory = server.perform_open_file_action(
                    {"path": "folder", "explorer": True},
                    platform_name="nt", explorer_open=explorer, startfile=startfile,
                )
                default_file = server.perform_open_file_action(
                    {"path": "file.txt"},
                    platform_name="nt", explorer_open=explorer, startfile=startfile,
                )
            self.assertEqual(reveal["action"], "select_file")
            self.assertEqual(explorer.call_args_list, [
                mock.call(file_path, select_file=True, allowed_root=root),
                mock.call(folder, select_file=False, allowed_root=root),
            ])
            startfile.assert_called_once_with(str(file_path))
            self.assertEqual(default_file["action"], "default")

    def test_existing_directory_without_new_flag_keeps_folder_open_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / "folder"
            folder.mkdir()
            explorer = mock.Mock(return_value={"ok": True, "action": "open_folder"})
            with mock.patch("server.resolve_project_path", return_value=(root, folder)):
                result = server.perform_open_file_action(
                    {"path": "folder"}, platform_name="nt", explorer_open=explorer,
                )
            self.assertEqual(result["action"], "open_folder")
            explorer.assert_called_once_with(folder, select_file=False, allowed_root=root)

    def test_non_windows_reveal_keeps_parent_startfile_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "file.txt"
            startfile = mock.Mock()
            with mock.patch("server.resolve_project_path", return_value=(root, target)):
                result = server.perform_open_file_action(
                    {"path": "file.txt", "reveal": True},
                    platform_name="posix", startfile=startfile,
                )
            startfile.assert_called_once_with(str(root))
            self.assertEqual(result["action"], "reveal")

    def test_terminal_requires_directory_and_uses_literal_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / "含 ' 引号"
            folder.mkdir()
            popen = mock.Mock()
            with mock.patch("server.resolve_project_path", return_value=(root, folder)):
                result = server.perform_open_file_action(
                    {"path": "folder", "terminal": True}, popen=popen,
                )
            self.assertEqual(result["action"], "terminal")
            command = popen.call_args.args[0]
            self.assertEqual(command[-1], str(folder))
            self.assertIn("-LiteralPath $args[0]", command[3])
            self.assertEqual(popen.call_args.kwargs["cwd"], str(folder))

    def test_missing_path_and_non_directory_terminal_fail_before_side_effect(self):
        with self.assertRaisesRegex(ValueError, "Missing path"):
            server.perform_open_file_action({}, startfile=mock.Mock())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            file_path = root / "file.txt"
            file_path.write_text("ok", encoding="utf-8")
            popen = mock.Mock()
            with mock.patch("server.resolve_project_path", return_value=(root, file_path)):
                with self.assertRaisesRegex(ValueError, "existing directory"):
                    server.perform_open_file_action(
                        {"path": "file.txt", "terminal": True}, popen=popen,
                    )
            popen.assert_not_called()

    def test_handler_returns_degraded_payload_and_bounds_errors(self):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value={"path": "missing", "reveal": True})
        handler.send_json = mock.Mock()
        result = {
            "ok": True,
            "action": "open_folder",
            "selected": False,
            "degraded": True,
            "degradedReasons": ["target_missing"],
            "foreground": "window-not-found",
            "restored": False,
            "topmostPulse": False,
        }
        with mock.patch("server.perform_open_file_action", return_value=result):
            server.CodeHandler._handle_open_file(handler)
        handler.send_json.assert_called_once_with(result)


if __name__ == "__main__":
    unittest.main()
