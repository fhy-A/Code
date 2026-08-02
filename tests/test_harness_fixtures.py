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
    def test_trace_suite_has_all_frozen_h0_2_scenarios(self):
        summary = harness_fixtures.validate_trace_suite()
        self.assertEqual(summary["fixtureCount"], 15)
        self.assertEqual(summary["eventCount"], 106)
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
            100: "fb7a6439a77f41fa0e3b2001a611bc8b383e7e2b28f7dd573b22156304631a3c",
            1_000: "989cdffa4b0734d5502280a038dc225f6aabf4e4145bcbd6f9979952c068d6b0",
            10_000: "84205dda88862e7bbfff74077f326547648d8cfba4044c53f358dde51c9887d1",
        }
        for size, digest in expected.items():
            with self.subTest(size=size):
                self.assertEqual(harness_fixtures.trace_walk_hash(suite, size), digest)
                self.assertEqual(harness_fixtures.trace_walk_hash(suite, size), digest)

    def test_agent_run_v1_v2_v3_minimum_records_restore(self):
        for version in (1, 2, 3):
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
        self.assertEqual(summary["fixtureCount"], 15)
        self.assertEqual(summary["compatibilityFixtureCount"], 5)


if __name__ == "__main__":
    unittest.main()
