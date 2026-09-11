import inspect
from dataclasses import replace
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import release
from devtools import verification


class TestReleaseNotesAutomation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.releases_dir = Path(self._tmp.name)
        self._releases_patch = mock.patch.object(
            release,
            "RELEASES_DIR",
            self.releases_dir,
        )
        self._releases_patch.start()

    def tearDown(self):
        self._releases_patch.stop()
        self._tmp.cleanup()

    def test_new_release_uses_chinese_template_and_is_blocked(self):
        release_file = release.generate_release_notes(
            "0.5.31",
            "ABC123",
            1024 * 1024,
        )
        content = release_file.read_text(encoding="utf-8")

        self.assertIn("## 打包信息", content)
        self.assertIn("## 下载与校验", content)
        self.assertIn(release.RELEASE_NOTES_PLACEHOLDER, content)
        self.assertIn("Code-v0.5.31.exe", content)
        self.assertIn("ABC123", content)
        self.assertTrue(
            release.validate_release_notes(release_file, "0.5.31"),
        )
        with self.assertRaises(SystemExit):
            release.require_release_notes_ready(release_file, "0.5.31")

    def test_preserves_legacy_body_and_refreshes_generated_metadata(self):
        release_file = self.releases_dir / "v0.5.31.md"
        release_file.write_text(
            """# Code v0.5.30 Release Notes

Date: 2026-07-27

## 更新重点

- 修复发布说明被覆盖的问题。

## Packaging

- stale metadata

## Download / verification

`Code-v0.5.30.exe` / `OLD_SHA`
""",
            encoding="utf-8",
        )

        generated = release.generate_release_notes(
            "0.5.31",
            "NEW_SHA",
            2 * 1024 * 1024,
        )
        content = generated.read_text(encoding="utf-8")

        self.assertIn("## 更新重点", content)
        self.assertIn("修复发布说明被覆盖的问题", content)
        self.assertIn("Code-v0.5.31.exe", content)
        self.assertIn("NEW_SHA", content)
        self.assertIn("2.00 MiB", content)
        self.assertNotIn("stale metadata", content)
        self.assertNotIn("Code-v0.5.30.exe", content)
        self.assertNotIn("OLD_SHA", content)
        self.assertEqual(
            release.validate_release_notes(generated, "0.5.31"),
            [],
        )

    def test_preserves_prepared_body_only_file(self):
        release_file = self.releases_dir / "v0.5.31.md"
        release_file.write_text(
            """## 主要改动

- 自动发布会保留这段预先写好的中文正文。
""",
            encoding="utf-8",
        )

        generated = release.generate_release_notes(
            "0.5.31",
            "READY_SHA",
            4096,
        )
        content = generated.read_text(encoding="utf-8")

        self.assertIn("自动发布会保留这段预先写好的中文正文", content)
        self.assertEqual(content.count("## 主要改动"), 1)
        self.assertEqual(
            release.validate_release_notes(generated, "0.5.31"),
            [],
        )

        regenerated = release.generate_release_notes(
            "0.5.31",
            "REFRESHED_SHA",
            8192,
        )
        refreshed_content = regenerated.read_text(encoding="utf-8")
        self.assertEqual(refreshed_content.count("## 主要改动"), 1)
        self.assertIn("自动发布会保留这段预先写好的中文正文", refreshed_content)
        self.assertIn("REFRESHED_SHA", refreshed_content)
        self.assertNotIn("READY_SHA", refreshed_content)

    def test_placeholder_variants_are_rejected(self):
        variants = (
            "内容待补充",
            "TBD",
            "[TODO] write notes",
            "DRY_RUN_SHA256",
            "适用于 vX.Y.Z",
        )
        for index, placeholder in enumerate(variants):
            with self.subTest(placeholder=placeholder):
                release_file = self.releases_dir / f"v0.5.{40 + index}.md"
                version = f"0.5.{40 + index}"
                release_file.write_text(
                    release._render_release_notes(
                        version,
                        f"## 主要改动\n\n- {placeholder}",
                        "VALID_SHA",
                        1024,
                        "2026-07-28",
                    ),
                    encoding="utf-8",
                )
                self.assertTrue(
                    release.validate_release_notes(release_file, version),
                )

    def test_release_notes_gate_runs_before_git_commit_and_tag(self):
        source = inspect.getsource(release.prepare_release)
        self.assertLess(
            source.index("require_release_notes_ready"),
            source.index("save_credential"),
        )
        self.assertLess(source.index("require_prepare_inputs"), source.index("run_release_quality_checks"))

    def test_release_paths_exclude_generated_pyinstaller_spec(self):
        paths = release._release_paths("1.2.3")
        self.assertEqual(
            paths,
            (
                "VERSION",
                "file_version_info.txt",
                "README.md",
                "docs/releases/v1.2.3.md",
            ),
        )
        self.assertTrue(all(not path.endswith(".spec") for path in paths))

    def test_release_command_diagnostics_are_safe_for_legacy_console_encoding(self):
        raw = tempfile.SpooledTemporaryFile()
        import io

        stream = io.TextIOWrapper(raw, encoding="gbk")
        with mock.patch.object(release.sys, "stdout", stream):
            self.assertIn("\\u2713", release._console_safe("status: \u2713"))

    def test_frontend_release_gate_builds_then_verifies(self):
        successful = (0, "ok", "")
        with mock.patch.object(
            release,
            "run",
            side_effect=[successful, successful, successful],
        ) as run_command:
            release.prepare_frontend_assets(build=True)

        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            [
                ["node", str(release.FRONTEND_BUILD_SCRIPT)],
                ["node", str(release.FRONTEND_BUILD_SCRIPT), "--check"],
                ["node", "--check", str(release.FRONTEND_BUNDLE)],
            ],
        )

    def test_frontend_release_gate_is_read_only_in_dry_run(self):
        successful = (0, "ok", "")
        with mock.patch.object(
            release,
            "run",
            side_effect=[successful, successful],
        ) as run_command:
            release.prepare_frontend_assets(build=False)

        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            [
                ["node", str(release.FRONTEND_BUILD_SCRIPT), "--check"],
                ["node", "--check", str(release.FRONTEND_BUNDLE)],
            ],
        )

    def test_frontend_release_gate_failure_stops_release(self):
        failed = (1, "stale", "hash mismatch")
        with mock.patch.object(release, "run", return_value=failed):
            with self.assertRaises(SystemExit):
                release.prepare_frontend_assets(build=False)

    def test_frontend_release_gate_runs_before_exe_packaging(self):
        source = inspect.getsource(release.prepare_release)
        self.assertLess(
            source.index("run_release_quality_checks"),
            source.index("build_exe"),
        )


class TestReadmeVersionMetadata(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.stack = ExitStack()
        self.stack.enter_context(mock.patch.object(release, "ROOT", self.root))
        self.stack.enter_context(
            mock.patch.object(release, "VERSION_FILE", self.root / "VERSION"),
        )
        self.stack.enter_context(
            mock.patch.object(
                release,
                "VERSION_INFO_FILE",
                self.root / "file_version_info.txt",
            ),
        )
        self.stack.enter_context(
            mock.patch.object(release, "README_FILE", self.root / "README.md"),
        )

    def tearDown(self):
        self.stack.close()
        self._tmp.cleanup()

    @staticmethod
    def _badge(url_version, alt_version):
        return (
            '<img src="https://img.shields.io/badge/version-'
            f'{url_version}-2563EB" alt="Version {alt_version}">'
        )

    def _write_readme(self, *, badge=None, exe_name=None):
        parts = [
            badge if badge is not None else self._badge("0.6.6", "0.6.6"),
            '<img src="docs/brand.svg" alt="Unrelated Version 9.9.9">',
        ]
        if exe_name is not None:
            parts.append(f"下载 `{exe_name}`。")
        self.readme = "\n".join(parts) + "\n"
        release.README_FILE.write_text(self.readme, encoding="utf-8")

    def _prepare_consistency_files(self, expected_version):
        release.VERSION_FILE.write_text(expected_version + "\n", encoding="utf-8")
        release.VERSION_INFO_FILE.write_text(
            f"OriginalFilename=Code-v{expected_version}.exe\n",
            encoding="utf-8",
        )

    def test_update_readme_synchronizes_badge_alt_and_exe_idempotently(self):
        self._write_readme(
            badge=self._badge("0.6.6", "0.5.30"),
            exe_name="Code-v0.6.6.exe",
        )

        release.update_readme("0.6.7")
        first = release.README_FILE.read_text(encoding="utf-8")
        release.update_readme("0.6.7")
        second = release.README_FILE.read_text(encoding="utf-8")

        self.assertIn(self._badge("0.6.7", "0.6.7"), first)
        self.assertIn("Code-v0.6.7.exe", first)
        self.assertIn(
            '<img src="docs/brand.svg" alt="Unrelated Version 9.9.9">',
            first,
        )
        self.assertNotIn("Code-v0.6.6.exe", first)
        self.assertEqual(second, first)

    def test_consistency_rejects_missing_or_stale_readme_fields(self):
        cases = {
            "missing-badge-url": (
                '<img src="docs/version.svg" alt="Version {version}">',
                "Code-v{version}.exe",
            ),
            "stale-badge-url": (self._badge("0.5.30", "{version}"), "Code-v{version}.exe"),
            "missing-badge-alt": (
                '<img src="https://img.shields.io/badge/version-{version}-2563EB">',
                "Code-v{version}.exe",
            ),
            "stale-badge-alt": (self._badge("{version}", "0.5.30"), "Code-v{version}.exe"),
            "missing-exe": (self._badge("{version}", "{version}"), None),
            "stale-exe": (self._badge("{version}", "{version}"), "Code-v0.5.30.exe"),
        }

        for dry_run in (True, False):
            expected_version = "0.6.6" if dry_run else "0.6.7"
            self._prepare_consistency_files(expected_version)
            for case_id, (badge_template, exe_template) in cases.items():
                with self.subTest(dry_run=dry_run, case=case_id):
                    badge = badge_template.format(version=expected_version)
                    exe_name = (
                        exe_template.format(version=expected_version)
                        if exe_template is not None
                        else None
                    )
                    self._write_readme(badge=badge, exe_name=exe_name)
                    with self.assertRaises(SystemExit):
                        release.verify_version_consistency(
                            "0.6.7",
                            "0.6.6",
                            dry_run=dry_run,
                        )

    def test_consistency_accepts_complete_readme_metadata(self):
        for dry_run in (True, False):
            expected_version = "0.6.6" if dry_run else "0.6.7"
            with self.subTest(dry_run=dry_run):
                self._prepare_consistency_files(expected_version)
                self._write_readme(
                    badge=self._badge(expected_version, expected_version),
                    exe_name=f"Code-v{expected_version}.exe",
                )
                release.verify_version_consistency(
                    "0.6.7",
                    "0.6.6",
                    dry_run=dry_run,
                )


class TestHarnessReplayReleaseGate(unittest.TestCase):
    @staticmethod
    def _expected_npm_executable():
        return "npm.cmd" if release.os.name == "nt" else "npm"

    def test_pytest_full_uses_shared_1500_second_definition_and_durations(self):
        spec = release.CHECKS["pytest_full"]
        self.assertEqual(spec.timeout, 1500)
        self.assertEqual(spec.command, (release.sys.executable, "-m", "pytest", "tests", "-v", "--tb=short", "--durations=30"))
        manifest_entry = next(
            item
            for item in verification.get_release_definition_manifest()["checks"]
            if item["id"] == "pytest_full"
        )
        self.assertEqual(manifest_entry["command"], spec.command)
        self.assertEqual(manifest_entry["timeout"], 1500)
        self.assertEqual(
            verification.get_release_check_ids(dry_run=False, skip_tests=False),
            ("git_diff_check", "syntax_app", "syntax_agent_runtime", "syntax_server",
             "syntax_launcher", "syntax_build_exe", "frontend_build", "frontend_freshness",
             "frontend_bundle_syntax", "harness_replay", "pytest_full"),
        )
        current_fingerprint = verification.get_release_definition_fingerprint()
        old_command = (release.sys.executable, "-m", "pytest", "tests", "-q", "--durations=30")
        with mock.patch.dict(verification.CHECKS, {"pytest_full": replace(spec, command=old_command)}):
            self.assertNotEqual(verification.get_release_definition_fingerprint(), current_fingerprint)

        with mock.patch.object(
            release,
            "run",
            return_value=(0, "1356 passed", ""),
        ) as run_command, mock.patch.object(release, "ok") as mark_ok:
            release.run_tests()

        run_command.assert_called_once_with(
            list(spec.command),
            description="pytest tests -v --tb=short --durations=30",
            timeout=1500,
        )
        mark_ok.assert_called_once_with("全量测试通过")

    def test_replay_gate_uses_exact_command_and_timeout_then_continues(self):
        with mock.patch.object(
            release,
            "run",
            return_value=(0, "Replay hash: fixture-hash", ""),
        ) as run_command, mock.patch.object(release, "ok") as mark_ok:
            release.run_harness_replay_gate()

        run_command.assert_called_once_with(
            [self._expected_npm_executable(), "run", "verify:harness-replay"],
            description="npm run verify:harness-replay",
            timeout=30,
        )
        mark_ok.assert_called_once_with("Harness replay 门禁通过")

    def test_replay_gate_nonzero_result_exits_with_bounded_diagnostic(self):
        oversized_output = "\n".join(f"diagnostic-{index}" for index in range(500))
        with mock.patch.object(
            release,
            "run",
            return_value=(7, oversized_output, "synthetic stderr marker"),
        ), mock.patch.object(release, "die", side_effect=SystemExit) as stop_release:
            with self.assertRaises(SystemExit):
                release.run_harness_replay_gate()

        message = stop_release.call_args.args[0]
        self.assertIn("退出码 7", message)
        self.assertIn("synthetic stderr marker", message)
        self.assertLessEqual(len(message), 2100)

    def test_replay_gate_timeout_and_start_failure_exit(self):
        failures = (
            subprocess.TimeoutExpired(
                ["npm", "run", "verify:harness-replay"],
                30,
                output="synthetic timeout output",
            ),
            FileNotFoundError("synthetic npm missing"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                release,
                "run",
                side_effect=failure,
            ), mock.patch.object(release, "die", side_effect=SystemExit) as stop_release:
                with self.assertRaises(SystemExit):
                    release.run_harness_replay_gate()
                self.assertLessEqual(len(stop_release.call_args.args[0]), 2100)

    def test_fast_checks_and_replay_precede_full_pytest(self):
        ids = verification.get_release_check_ids(dry_run=False, skip_tests=False)
        self.assertLess(ids.index("git_diff_check"), ids.index("frontend_build"))
        self.assertLess(ids.index("syntax_build_exe"), ids.index("frontend_build"))
        self.assertLess(ids.index("harness_replay"), ids.index("pytest_full"))


    def test_skip_tests_routes_to_prepared_credential_instead_of_trust_skip(self):
        with mock.patch.object(
            release.sys,
            "argv",
            ["release.py", "0.5.99", "--skip-tests", "--no-proxy"],
        ), mock.patch.object(release, "publish_prepared") as publish_prepared, \
                mock.patch.object(release, "run_tests") as run_tests, \
                mock.patch.object(release, "run_harness_replay_gate") as replay_gate, \
                mock.patch.object(release, "run_git_diff_check") as diff_check, \
                mock.patch.object(release, "build_exe") as build_exe:
            release.main()

        publish_prepared.assert_called_once_with("0.5.99", auto_yes=False)
        run_tests.assert_not_called()
        replay_gate.assert_not_called()
        diff_check.assert_not_called()
        build_exe.assert_not_called()

    def test_dry_run_does_not_execute_replay_gate(self):
        calls = []
        with mock.patch.object(release.sys, "argv", ["release.py", "0.5.99", "--dry-run", "--no-proxy"]), \
                mock.patch.object(release, "get_current_version", return_value="0.5.98"), \
                mock.patch.object(release, "verify_version_consistency"), \
                mock.patch.object(release, "run", side_effect=lambda cmd, **kw: (calls.append(tuple(cmd)) or (0, "", ""))), \
                mock.patch.object(release, "git_commit_and_tag") as commit, \
                mock.patch.object(release, "push_to_github") as push, \
                mock.patch.object(release, "create_github_release") as publish:
            release.main()
        expected = verification.get_release_check_ids(dry_run=True, skip_tests=False)
        self.assertEqual(calls, [verification.CHECKS[key].command for key in expected])
        commit.assert_called_once_with("0.5.99", dry_run=True)
        push.assert_called_once_with("0.5.99", dry_run=True)
        self.assertTrue(publish.call_args.kwargs["dry_run"])


    def test_replay_failure_prevents_full_pytest(self):
        with mock.patch.object(release, "run", return_value=(0, "", "")), \
                mock.patch.object(release, "run_harness_replay_gate", side_effect=SystemExit) as replay, \
                mock.patch.object(release, "run_tests") as full:
            with self.assertRaises(SystemExit):
                release.run_release_quality_checks(dry_run=False, skip_tests=False)
        replay.assert_called_once_with()
        full.assert_not_called()



if __name__ == "__main__":
    unittest.main()
