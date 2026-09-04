import io
import json
import subprocess
import unittest
from dataclasses import replace
from unittest import mock

import release
from devtools import verification
import verify


class TestVerificationProfiles(unittest.TestCase):
    def test_four_profiles_have_stable_exact_mappings(self):
        self.assertEqual(tuple(verification.PROFILE_CHECK_IDS), ("quick", "ui", "runtime", "release"))
        self.assertEqual(
            verification.get_profile_check_ids("quick"),
            ("git_diff_check", *verification.SYNTAX_CHECK_IDS),
        )
        self.assertEqual(
            verification.get_profile_check_ids("ui"),
            (
                "frontend_freshness",
                "frontend_bundle_syntax",
                "pytest_ui",
                "git_diff_check",
                "syntax_app",
            ),
        )
        self.assertEqual(
            verification.get_profile_check_ids("runtime"),
            (
                "frontend_freshness",
                "frontend_bundle_syntax",
                "pytest_full",
                "harness_replay",
                "h4",
                "git_diff_check",
                *verification.SYNTAX_CHECK_IDS,
            ),
        )
        self.assertEqual(
            verification.get_profile_check_ids("release"),
            verification.RELEASE_READ_ONLY_CHECK_IDS,
        )

    def test_h4_is_runtime_only_and_standalone_profiles_never_build(self):
        for profile, checks in verification.PROFILE_CHECK_IDS.items():
            self.assertEqual("h4" in checks, profile == "runtime")
            self.assertNotIn("frontend_build", checks)

    def test_unknown_profile_has_stable_failure_summary(self):
        stream = io.StringIO()
        exit_code = verification.run_profile("unknown", stream=stream)
        self.assertEqual(exit_code, 2)
        self.assertEqual(
            stream.getvalue().splitlines(),
            [
                "VERIFY profile=unknown",
                "ERROR unknown_profile=unknown available=quick,ui,runtime,release",
                "FIRST_FAILURE unknown_profile",
                "RESULT profile=unknown status=failed exit=2",
            ],
        )

    def test_fail_fast_preserves_first_exit_code_and_summary(self):
        calls = []

        def executor(spec):
            calls.append(spec.check_id)
            return subprocess.CompletedProcess(
                spec.command,
                9 if spec.check_id == "syntax_app" else 0,
                stdout="synthetic output" if spec.check_id == "syntax_app" else "",
                stderr="",
            )

        stream = io.StringIO()
        exit_code = verification.run_profile("quick", executor=executor, stream=stream)
        self.assertEqual(exit_code, 9)
        self.assertEqual(tuple(calls), ("git_diff_check", "syntax_app"))
        output = stream.getvalue()
        self.assertIn("FAIL id=syntax_app reason=command exit=9", output)
        self.assertIn("FIRST_FAILURE syntax_app", output)
        self.assertIn("RESULT profile=quick status=failed exit=9", output)
        self.assertNotIn("PASS id=syntax_agent_runtime", output)

    def test_success_summary_lists_executed_and_skipped_items_once(self):
        calls = []

        def executor(spec):
            calls.append(spec.check_id)
            return subprocess.CompletedProcess(spec.command, 0, stdout="", stderr="")

        stream = io.StringIO()
        self.assertEqual(
            verification.run_profile("ui", executor=executor, stream=stream),
            0,
        )
        self.assertEqual(tuple(calls), verification.PROFILE_CHECK_IDS["ui"])
        self.assertEqual(len(calls), len(set(calls)))
        output = stream.getvalue()
        self.assertIn("EXECUTE count=5 items=frontend_freshness", output)
        self.assertIn("SKIP count=", output)
        self.assertIn("FIRST_FAILURE none", output)
        self.assertTrue(output.endswith("RESULT profile=ui status=passed exit=0\n"))

    def test_command_output_is_safe_for_legacy_windows_console_encoding(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="gbk")

        def executor(spec):
            return subprocess.CompletedProcess(
                spec.command,
                9,
                stdout="replacement: \ufffd",
                stderr="",
            )

        self.assertEqual(
            verification.run_profile("quick", executor=executor, stream=stream),
            9,
        )
        stream.flush()
        self.assertIn(b"replacement:", raw.getvalue())

    def test_cli_requires_exactly_one_profile(self):
        with mock.patch("builtins.print") as printer:
            self.assertEqual(verify.main([]), 2)
        printer.assert_called_once_with(
            "Usage: python verify.py doctor|quick|ui|runtime|release"
        )

    def test_cli_routes_doctor_outside_the_four_profiles(self):
        with mock.patch.object(verify, "run_doctor", return_value=0) as doctor:
            self.assertEqual(verify.main(["doctor"]), 0)
        doctor.assert_called_once_with()
        self.assertEqual(
            tuple(verification.PROFILE_CHECK_IDS),
            ("quick", "ui", "runtime", "release"),
        )


class TestDevelopmentDoctor(unittest.TestCase):
    def _which(self, name):
        return {
            "python": "C:/h4/python.exe",
            "node": "C:/node/node.exe",
            verification.NPM: "C:/node/npm.cmd",
        }.get(name)

    def _h4_payload(self, executable="C:/current/python.exe", missing=()):
        return {
            "executable": executable,
            "version": "3.12.10",
            "modules": {
                import_name: package_name not in missing
                for import_name, package_name in verification.DOCTOR_PYTHON_MODULES
            },
        }

    def _node_payload(self, chromium=None):
        chromium = chromium or {
            "id": "chromium_launch",
            "status": "passed",
            "reason": "ready",
            "detail": {
                "contextClosed": True,
                "temporaryRootRemoved": True,
            },
        }
        return {
            "schema": verification.DOCTOR_NODE_SCHEMA,
            "checks": [
                {
                    "id": "esbuild_transform",
                    "status": "passed",
                    "reason": "ready",
                    "detail": {"version": "0.28.1"},
                },
                {
                    "id": "playwright_package",
                    "status": "passed",
                    "reason": "ready",
                    "detail": {"version": "1.62.1"},
                },
                chromium,
            ],
        }

    def _executor(self, h4_payload=None, node_payload=None, node_returncode=0):
        h4_payload = h4_payload or self._h4_payload()
        node_payload = node_payload or self._node_payload()

        def execute(command, _timeout):
            if command[0] == "python":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(h4_payload),
                    stderr="",
                )
            if command[-1] == "--version":
                version = "v24.14.0" if "node.exe" in command[0] else "11.9.0"
                return subprocess.CompletedProcess(command, 0, stdout=version, stderr="")
            if command[-1] == str(verification.DOCTOR_NODE_PROBE):
                return subprocess.CompletedProcess(
                    command,
                    node_returncode,
                    stdout=json.dumps(node_payload),
                    stderr="",
                )
            raise AssertionError(f"unexpected doctor command: {command}")

        return execute

    def test_doctor_aggregates_success_and_preserves_release_definition(self):
        stream = io.StringIO()
        before_ids = verification.get_release_check_ids(dry_run=False, skip_tests=False)
        before_fingerprint = verification.get_release_definition_fingerprint()

        exit_code = verification.run_doctor(
            executor=self._executor(),
            which=self._which,
            module_finder=lambda _name: True,
            stream=stream,
            current_executable="C:/current/python.exe",
            current_version="3.12.10",
        )

        self.assertEqual(exit_code, 0)
        output = stream.getvalue()
        for check_id in (
            "python_current",
            "python_current_modules",
            "python_h4",
            "python_identity",
            "python_h4_modules",
            "node_runtime",
            "npm_runtime",
            *verification.DOCTOR_NODE_CHECK_IDS,
        ):
            self.assertIn(f"CHECK id={check_id} status=passed", output)
        self.assertIn("FIRST_FAILURE none", output)
        self.assertTrue(output.endswith("RESULT doctor status=passed exit=0\n"))
        self.assertEqual(
            verification.get_release_check_ids(dry_run=False, skip_tests=False),
            before_ids,
        )
        self.assertEqual(
            verification.get_release_definition_fingerprint(),
            before_fingerprint,
        )

    def test_doctor_reports_all_missing_modules_and_executables(self):
        stream = io.StringIO()
        exit_code = verification.run_doctor(
            executor=lambda command, timeout: self.fail((command, timeout)),
            which=lambda _name: None,
            module_finder=lambda name: name not in {"requests", "yaml"},
            stream=stream,
            current_executable="C:/current/python.exe",
            current_version="3.12.10",
        )

        self.assertEqual(exit_code, 1)
        output = stream.getvalue()
        self.assertIn(
            'CHECK id=python_current_modules status=failed reason=missing '
            'detail={"missing":["requests","PyYAML"]}',
            output,
        )
        self.assertIn("CHECK id=python_h4 status=failed reason=missing", output)
        self.assertIn("CHECK id=node_runtime status=failed reason=missing", output)
        self.assertIn("CHECK id=npm_runtime status=failed reason=missing", output)
        self.assertIn("CHECK id=esbuild_transform status=failed reason=blocked", output)
        self.assertIn("RESULT doctor status=failed exit=1", output)

    def test_doctor_reports_interpreter_mismatch_as_non_blocking_warning(self):
        stream = io.StringIO()
        exit_code = verification.run_doctor(
            executor=self._executor(
                h4_payload=self._h4_payload(executable="D:/other/python.exe")
            ),
            which=self._which,
            module_finder=lambda _name: True,
            stream=stream,
            current_executable="C:/current/python.exe",
            current_version="3.12.10",
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "CHECK id=python_identity status=warning reason=interpreter_mismatch",
            stream.getvalue(),
        )

    def test_doctor_reports_chromium_launch_failure_and_cleanup_state(self):
        stream = io.StringIO()
        chromium = {
            "id": "chromium_launch",
            "status": "failed",
            "reason": "launch_failed",
            "detail": {
                "code": "EPERM",
                "contextClosed": True,
                "temporaryRootRemoved": True,
            },
        }
        exit_code = verification.run_doctor(
            executor=self._executor(
                node_payload=self._node_payload(chromium),
                node_returncode=1,
            ),
            which=self._which,
            module_finder=lambda _name: True,
            stream=stream,
            current_executable="C:/current/python.exe",
        )

        self.assertEqual(exit_code, 1)
        output = stream.getvalue()
        self.assertIn(
            "CHECK id=chromium_launch status=failed reason=launch_failed",
            output,
        )
        self.assertIn('"temporaryRootRemoved":true', output)

    def test_doctor_reports_node_probe_timeout_without_hiding_other_checks(self):
        stream = io.StringIO()
        base_executor = self._executor()

        def execute(command, timeout):
            if command[-1] == str(verification.DOCTOR_NODE_PROBE):
                raise subprocess.TimeoutExpired(command, timeout)
            return base_executor(command, timeout)

        exit_code = verification.run_doctor(
            executor=execute,
            which=self._which,
            module_finder=lambda _name: True,
            stream=stream,
            current_executable="C:/current/python.exe",
        )

        self.assertEqual(exit_code, 1)
        output = stream.getvalue()
        self.assertIn("CHECK id=node_runtime status=passed", output)
        for check_id in verification.DOCTOR_NODE_CHECK_IDS:
            self.assertIn(
                f"CHECK id={check_id} status=failed reason=timeout",
                output,
            )

    def test_doctor_treats_chromium_cleanup_failure_as_blocking(self):
        stream = io.StringIO()
        chromium = {
            "id": "chromium_launch",
            "status": "failed",
            "reason": "cleanup_failed",
            "detail": {
                "contextClosed": False,
                "temporaryRootRemoved": False,
            },
        }
        exit_code = verification.run_doctor(
            executor=self._executor(
                node_payload=self._node_payload(chromium),
                node_returncode=1,
            ),
            which=self._which,
            module_finder=lambda _name: True,
            stream=stream,
            current_executable="C:/current/python.exe",
        )

        self.assertEqual(exit_code, 1)
        output = stream.getvalue()
        self.assertIn(
            "CHECK id=chromium_launch status=failed reason=cleanup_failed",
            output,
        )
        self.assertIn('"temporaryRootRemoved":false', output)


class TestSharedReleaseDefinition(unittest.TestCase):
    def test_release_definition_fingerprint_is_stable_and_excludes_h4(self):
        manifest = verification.get_release_definition_manifest()
        self.assertEqual(
            [item["id"] for item in manifest["checks"]],
            list(verification.get_release_check_ids(dry_run=False, skip_tests=False)),
        )
        self.assertNotIn("h4", [item["id"] for item in manifest["checks"]])
        first = verification.get_release_definition_fingerprint()
        self.assertEqual(first, verification.get_release_definition_fingerprint())

        original = verification.CHECKS["pytest_full"]
        with mock.patch.dict(
            verification.CHECKS,
            {"pytest_full": replace(original, timeout=original.timeout + 1)},
        ):
            self.assertNotEqual(first, verification.get_release_definition_fingerprint())

    def test_formal_release_order_matches_historical_gate_order(self):
        self.assertEqual(
            verification.get_release_check_ids(dry_run=False, skip_tests=False),
            (
                "frontend_build",
                "frontend_freshness",
                "frontend_bundle_syntax",
                "pytest_full",
                "harness_replay",
                "git_diff_check",
                *verification.SYNTAX_CHECK_IDS,
            ),
        )

    def test_dry_run_and_skip_tests_keep_historical_subsets(self):
        syntax = verification.SYNTAX_CHECK_IDS
        self.assertEqual(
            verification.get_release_check_ids(dry_run=True, skip_tests=False),
            ("frontend_freshness", "frontend_bundle_syntax", *syntax),
        )
        self.assertEqual(
            verification.get_release_check_ids(dry_run=False, skip_tests=True),
            (
                "frontend_build",
                "frontend_freshness",
                "frontend_bundle_syntax",
                *syntax,
            ),
        )
        self.assertEqual(
            verification.get_release_check_ids(dry_run=True, skip_tests=True),
            ("frontend_freshness", "frontend_bundle_syntax", *syntax),
        )

    def test_release_runner_executes_shared_definition_once_in_order(self):
        calls = []
        with mock.patch.object(
            release,
            "prepare_frontend_assets",
            side_effect=lambda **kwargs: calls.extend(
                (
                    "frontend_build",
                    "frontend_freshness",
                    "frontend_bundle_syntax",
                )
                if kwargs["build"]
                else ("frontend_freshness", "frontend_bundle_syntax")
            ),
        ), mock.patch.object(release, "run_tests", side_effect=lambda: calls.append("pytest_full")), \
                mock.patch.object(
                    release,
                    "run_harness_replay_gate",
                    side_effect=lambda: calls.append("harness_replay"),
                ), mock.patch.object(
                    release,
                    "run_git_diff_check",
                    side_effect=lambda: calls.append("git_diff_check"),
                ), mock.patch.object(
                    release,
                    "run_syntax_checks",
                    side_effect=lambda: calls.extend(verification.SYNTAX_CHECK_IDS),
                ):
            release.run_release_quality_checks(dry_run=False, skip_tests=False)

        expected = verification.get_release_check_ids(dry_run=False, skip_tests=False)
        self.assertEqual(tuple(calls), expected)
        self.assertEqual(len(calls), len(set(calls)))

    def test_release_runner_propagates_first_failure(self):
        with mock.patch.object(release, "prepare_frontend_assets"), mock.patch.object(
            release,
            "run_tests",
            side_effect=SystemExit(3),
        ), mock.patch.object(release, "run_harness_replay_gate") as replay_gate:
            with self.assertRaises(SystemExit):
                release.run_release_quality_checks(dry_run=False, skip_tests=False)
        replay_gate.assert_not_called()

    def test_shared_timeouts_preserve_release_contract(self):
        self.assertEqual(verification.CHECKS["frontend_build"].timeout, 120)
        self.assertEqual(verification.CHECKS["frontend_freshness"].timeout, 120)
        self.assertEqual(verification.CHECKS["frontend_bundle_syntax"].timeout, 120)
        self.assertEqual(verification.CHECKS["pytest_full"].timeout, 1080)
        self.assertEqual(verification.CHECKS["harness_replay"].timeout, 30)
        for check_id in ("git_diff_check", *verification.SYNTAX_CHECK_IDS):
            self.assertEqual(verification.CHECKS[check_id].timeout, 300)


if __name__ == "__main__":
    unittest.main()
