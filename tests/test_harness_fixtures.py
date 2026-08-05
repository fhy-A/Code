"""H0-2 guards for synthetic traces and minimum compatibility fixtures."""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod
from scripts import verify_harness_fixtures as harness_fixtures


ROOT = Path(__file__).resolve().parent.parent
COMPATIBILITY_DIR = ROOT / "tests" / "fixtures" / "harness" / "compatibility"


class HarnessFixtureTests(unittest.TestCase):
    def test_trace_suite_has_all_frozen_scenarios(self):
        summary = harness_fixtures.validate_trace_suite()
        self.assertEqual(summary["fixtureCount"], 17)
        self.assertEqual(summary["eventCount"], 124)
        self.assertEqual(summary["recoveryPointCount"], 4)
        self.assertEqual(
            set(summary["names"]),
            {
                "plain-text-final",
                "single-read-tool",
                "multi-tool-stage",
                "questionnaire-submit",
                "edit-authorization-accept",
                "command-authorization-reject",
                "auto-compaction-success",
                "auto-compaction-failure",
                "cancel-during-model",
                "cancel-during-command",
                "cancel-multi-tool-terminal-closure",
                "command-failure-model-recovery",
                "refresh-before-first-response",
                "refresh-during-tools",
                "server-restart-command-unknown",
                "poll-disconnect-reconnect",
                "model-non-action-recovery",
            },
        )

    def test_trace_schema_and_suite_version_stay_aligned(self):
        schema = json.loads(
            (ROOT / "tests" / "fixtures" / "harness" / "trace-suite.schema.json")
            .read_text(encoding="utf-8")
        )
        suite = harness_fixtures.load_trace_suite()
        self.assertEqual(schema["properties"]["fixtureVersion"]["const"], 1)
        self.assertEqual(suite["fixtureVersion"], 1)
        self.assertEqual(schema["properties"]["source"]["const"], "synthetic")

    def test_h3_2a_raw_fixture_contracts_close_declared_tools(self):
        suite = harness_fixtures.load_trace_suite()
        fixtures = {fixture["name"]: fixture for fixture in suite["fixtures"]}

        cancelled = fixtures["cancel-multi-tool-terminal-closure"]
        cancelled_model_events = [
            event for event in cancelled["events"]
            if event["type"] == "model_completed"
        ]
        self.assertEqual(len(cancelled_model_events), 1)
        declared_ids = [
            tool_call["id"]
            for tool_call in cancelled_model_events[0]["data"]["toolCalls"]
        ]
        completed_events = [
            event for event in cancelled["events"]
            if event["type"] == "tool_completed"
        ]
        completed_ids = [event["data"]["toolCallId"] for event in completed_events]
        self.assertEqual(
            declared_ids,
            ["tool-fixture-cancel-command", "tool-fixture-cancel-read"],
        )
        self.assertEqual(completed_ids, declared_ids)
        self.assertEqual(len(completed_ids), len(set(completed_ids)))

        started_ids = {
            event["data"]["toolCallId"]
            for event in cancelled["events"]
            if event["type"] == "tool_started"
        }
        command_started_ids = {
            event["data"]["toolCallId"]
            for event in cancelled["events"]
            if event["type"] == "command_started"
        }
        self.assertEqual(started_ids, {"tool-fixture-cancel-command"})
        self.assertEqual(command_started_ids, {"tool-fixture-cancel-command"})
        self.assertNotIn("tool-fixture-cancel-read", started_ids)
        self.assertNotIn("tool-fixture-cancel-read", command_started_ids)

        cancelled_results = {
            event["data"]["toolCallId"]: event["data"]["result"]
            for event in completed_events
        }
        self.assertIs(cancelled_results["tool-fixture-cancel-command"]["cancelled"], True)
        self.assertIs(cancelled_results["tool-fixture-cancel-read"]["cancelled"], True)
        self.assertIs(
            cancelled_results["tool-fixture-cancel-read"]["cancelledBeforeStart"],
            True,
        )
        self.assertEqual(
            [
                event["type"]
                for event in cancelled["events"]
                if event["type"] in {"completed", "failed", "cancelled"}
            ],
            ["cancelled"],
        )

        recovered = fixtures["command-failure-model-recovery"]
        recovered_model_events = [
            event for event in recovered["events"]
            if event["type"] == "model_completed"
        ]
        self.assertEqual(len(recovered_model_events), 2)
        failure_declared_ids = [
            tool_call["id"]
            for tool_call in recovered_model_events[0]["data"]["toolCalls"]
        ]
        failure_completed_events = [
            event for event in recovered["events"]
            if event["type"] == "tool_completed"
        ]
        self.assertEqual(failure_declared_ids, ["tool-fixture-command-failure"])
        self.assertEqual(
            [event["data"]["toolCallId"] for event in failure_completed_events],
            failure_declared_ids,
        )
        self.assertEqual(
            [
                event["data"]["toolCallId"]
                for event in recovered["events"]
                if event["type"] == "tool_started"
            ],
            failure_declared_ids,
        )
        self.assertEqual(
            [
                event["data"]["toolCallId"]
                for event in recovered["events"]
                if event["type"] == "command_started"
            ],
            failure_declared_ids,
        )
        failure_result = failure_completed_events[0]["data"]["result"]
        self.assertIs(failure_result["ok"], False)
        self.assertEqual(failure_result["exitCode"], 23)
        self.assertEqual(failure_result["stderr"], "synthetic-command-failure-marker")
        self.assertEqual(recovered_model_events[1]["data"]["toolCalls"], [])
        self.assertEqual(
            recovered_model_events[1]["data"]["content"],
            "Synthetic command failure handled.",
        )
        self.assertEqual(
            [
                event["type"]
                for event in recovered["events"]
                if event["type"] in {"completed", "failed", "cancelled"}
            ],
            ["completed"],
        )

    def test_sanitizer_rejects_credentials_private_paths_and_real_urls(self):
        self.assertEqual(harness_fixtures.scan_sensitive_fixtures(), [])
        probe = {
            "apiKey": "fixture-value",
            "message": "Bearer abcdefghijk",
            "path": "C:\\Users\\Example\\private.txt",
            "url": "https://service.example.com/v1",
        }
        findings = harness_fixtures._scan_value(probe, "probe")
        self.assertGreaterEqual(len(findings), 4)

    def test_trace_walk_hashes_are_deterministic(self):
        suite = harness_fixtures.load_trace_suite()
        expected = {
            100: "e2598557076f9f7c2c4c9a0f7f87af2133290aa7ff5e149490c5165be37927c2",
            1_000: "a7039b29a6a124c7617c8a9484bc7e529f2d37c62bcb5085241cb9467d5d9576",
            10_000: "15e8cc141302275bfae3d344fd616f1c9b2d7e4da40414bd97181ce5dcef6d6c",
        }
        for size, digest in expected.items():
            with self.subTest(size=size):
                self.assertEqual(harness_fixtures.trace_walk_hash(suite, size), digest)
                self.assertEqual(harness_fixtures.trace_walk_hash(suite, size), digest)

    def test_agent_run_v1_v2_v3_v4_minimum_records_restore(self):
        for version in (1, 2, 3, 4):
            fixture = json.loads(
                (COMPATIBILITY_DIR / f"agent-run-v{version}.json")
                .read_text(encoding="utf-8")
            )
            record = fixture["record"]
            expected = fixture["expected"]
            with self.subTest(version=version), mock.patch.object(
                server_mod,
                "_agent_run_workspace",
                return_value=("/workspace/restored", ["/workspace/restored"]),
            ) as workspace_mock:
                restored = server_mod._agent_run_from_record(record)
                self.assertEqual(restored["status"], expected["status"])
                self.assertEqual(restored["resume_status"], expected["resumeStatus"])
                self.assertEqual(restored["context_limit"], expected["contextLimit"])
                self.assertEqual(len(restored["compactions"]), expected["compactionCount"])
                self.assertEqual(
                    len(restored["steer_receipts"]),
                    expected.get("steerReceiptCount", 0),
                )
                self.assertEqual(restored["pending_steers"], [])
                roots_argument = workspace_mock.call_args.args[2]
                if expected["workspaceRootsSource"] == "legacy-fallback":
                    self.assertIsNone(roots_argument)
                else:
                    self.assertEqual(roots_argument, record["workspaceRoots"])

    def test_legacy_jsonl_keeps_valid_history_and_skips_partial_tail(self):
        path = COMPATIBILITY_DIR / "session-legacy-partial.jsonl"
        messages = server_mod.read_jsonl(path)
        self.assertEqual(len(messages), 3)
        self.assertEqual([item["role"] for item in messages], ["user", "assistant", "tool-call"])
        self.assertEqual(messages[0]["content"], "Synthetic legacy question.")

    def test_classic_frontend_manifest_matches_compatibility_entry(self):
        fixture = json.loads(
            (COMPATIBILITY_DIR / "classic-frontend.json").read_text(encoding="utf-8")
        )
        entry_source = (ROOT / fixture["entry"]).read_text(encoding="utf-8")
        imports = re.findall(r'^import "([^"]+)";$', entry_source, flags=re.MULTILINE)
        self.assertEqual(imports, fixture["expectedEntryImports"])
        self.assertEqual(imports[-2:], ["../agent-runtime.js", "../app.js"])
        for relative_path in fixture["requiredBuildOutputs"]:
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_standalone_verifier_passes_without_runtime_or_network(self):
        result = subprocess.run(
            [sys.executable, "scripts/verify_harness_fixtures.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout.strip())
        self.assertEqual(summary["fixtureCount"], 17)
        self.assertEqual(summary["eventCount"], 124)
        self.assertEqual(summary["compatibilityFixtureCount"], 6)


if __name__ == "__main__":
    unittest.main()
