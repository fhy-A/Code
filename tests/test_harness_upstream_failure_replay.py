"""Offline H3-2C1 replay and first-difference diagnostics."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "replay-agent-traces.cjs"
SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "upstream-failure-recovery-trace-suite.json"
DEFAULT_SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "trace-suite.json"
EXPECTED_FIXTURE_SUITE_HASH = "3278b2cfed32b5d06d8c0e0b4c07f84b065b3c0f41803d13bbbe211c8879a6c1"
EXPECTED_SUITE_REPLAY_HASH = "caa4f57850729a6d9452030418f914b42061fae0c64e410e839d892d38b97177"
EXPECTED_STATE_HASHES = {
    "upstream-401-config-terminal": "4ee23358e8e2263316e27fbfd2d55ab703dcb555f40b5412fe0a0899157d049e",
    "upstream-429-transient-terminal": "5f76190e174310644acca65d82ece61d5334a5039ed45af6d2aa003e42db4088",
    "upstream-502-transient-terminal": "2c924318f4433e84503fe3b4ff744075f9590dd87b9bb59c65aaecc1ca05bc9e",
    "model-first-response-timeout-terminal": "9920c097c0a31748b5b48a30eccd78b402a7add99b3928de77c85cc728569293",
    "model-empty-output-recovery-current": "186644bcc433bd0fe9e16fc965ef7a9dfdc45cd4b7b6b9fff1fc5f8b15f1c0c5",
    "model-reasoning-only-recovery-current": "29257088abe58ed97c3e9d4c9b337815556e38db4b6f0fc83e1007f4eb686456",
}
EXPECTED_DEFAULT_FIXTURE_HASH = "c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc"
EXPECTED_DEFAULT_REPLAY_HASH = "166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2"


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_runner(*arguments, check=True):
    return subprocess.run(
        ["node", str(RUNNER), "--suite", str(SUITE_PATH), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def run_default_runner(*arguments):
    return subprocess.run(
        ["node", str(RUNNER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def run_mutation(fixture_name, mutation):
    script = f"""
const runner = require("./scripts/replay-agent-traces.cjs");
const suite = runner.loadSuite("./tests/fixtures/harness/upstream-failure-recovery-trace-suite.json");
const fixture = suite.fixtures.find((item) => item.name === {json.dumps(fixture_name)});
{mutation}
try {{
  runner.runReplaySuite({{fixtureVersion: 1, fixtures: [fixture]}});
  process.exitCode = 2;
}} catch (error) {{
  process.stdout.write(JSON.stringify(error.toJSON ? error.toJSON() : {{
    name: error.name,
    message: error.message,
  }}));
}}
"""
    return subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def mutation_error(fixture_name, mutation):
    completed = run_mutation(fixture_name, mutation)
    if not completed.stdout:
        raise AssertionError(f"mutation emitted no diagnostic: {completed.stderr}")
    return json.loads(completed.stdout)


class HarnessUpstreamFailureReplayTests(unittest.TestCase):
    def test_independent_suite_replays_with_frozen_counts_and_hashes(self):
        summary = json.loads(run_runner("--json").stdout)
        self.assertEqual(summary["replayVersion"], 1)
        self.assertEqual(summary["fixtureVersion"], 1)
        self.assertEqual(summary["fixtureCount"], 6)
        self.assertEqual(summary["eventCount"], 26)
        self.assertEqual(summary["checkpointCount"], 16)
        self.assertEqual(summary["checkpointRecoveryCount"], 16)
        self.assertEqual(summary["recoveryCount"], 0)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_SUITE_REPLAY_HASH)
        self.assertEqual(
            canonical_hash(json.loads(SUITE_PATH.read_text(encoding="utf-8"))),
            EXPECTED_FIXTURE_SUITE_HASH,
        )

        self.assertEqual(
            {result["name"]: result["stateHash"] for result in summary["results"]},
            EXPECTED_STATE_HASHES,
        )
        for result in summary["results"]:
            with self.subTest(fixture=result["name"]):
                self.assertEqual(result["stateHash"], result["duplicateStateHash"])
                for checkpoint in result["checkpoints"]:
                    self.assertEqual(checkpoint["resumedStateHash"], result["stateHash"])

    def test_named_tagged_and_repeated_replay_are_deterministic(self):
        first = json.loads(run_runner("--json").stdout)
        second = json.loads(run_runner("--json").stdout)
        self.assertEqual(first, second)

        named = json.loads(
            run_runner("--fixture", "model-empty-output-recovery-current", "--json").stdout,
        )
        self.assertEqual(named["fixtureCount"], 1)
        self.assertEqual(named["eventCount"], 7)
        self.assertEqual(named["checkpointRecoveryCount"], 4)

        tagged = json.loads(run_runner("--tag", "transient", "--json").stdout)
        self.assertEqual(
            [result["name"] for result in tagged["results"]],
            [
                "upstream-429-transient-terminal",
                "upstream-502-transient-terminal",
                "model-first-response-timeout-terminal",
            ],
        )

    def test_default_single_run_baseline_and_historical_fixture_are_unchanged(self):
        summary = json.loads(run_default_runner("--json").stdout)
        suite = json.loads(DEFAULT_SUITE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(summary["fixtureCount"], 17)
        self.assertEqual(summary["eventCount"], 124)
        self.assertEqual(summary["checkpointCount"], 25)
        self.assertEqual(summary["checkpointRecoveryCount"], 25)
        self.assertEqual(summary["recoveryCount"], 4)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_DEFAULT_REPLAY_HASH)
        self.assertEqual(canonical_hash(suite), EXPECTED_DEFAULT_FIXTURE_HASH)

        historical = next(
            item for item in suite["fixtures"] if item["name"] == "model-non-action-recovery"
        )
        self.assertEqual(
            [event["type"] for event in historical["events"]],
            [
                "created",
                "model_started",
                "model_completed",
                "model_recovery",
                "model_pending",
                "model_started",
                "model_completed",
                "completed",
            ],
        )
        self.assertEqual(historical["events"][6]["data"]["outcome"], "content")

    def test_missing_and_out_of_order_recovery_have_frozen_sequence_paths(self):
        cases = (
            (
                "fixture.events.splice(3, 1);",
                "$.events[3].seq",
            ),
            (
                "[fixture.events[3], fixture.events[4]] = [fixture.events[4], fixture.events[3]];",
                "$.events[3].seq",
            ),
        )
        for mutation, expected_path in cases:
            with self.subTest(mutation=mutation):
                error = mutation_error("model-empty-output-recovery-current", mutation)
                self.assertEqual(error["path"], expected_path)

    def test_wrong_non_action_outcome_reports_model_round_path(self):
        error = mutation_error(
            "model-reasoning-only-recovery-current",
            'fixture.events[2].data.outcome = "completed";',
        )
        self.assertEqual(error["path"], "$.modelRounds[0].outcome")

    def test_duplicate_recovery_event_reports_first_duplicate_sequence_path(self):
        error = mutation_error(
            "model-empty-output-recovery-current",
            "fixture.events.splice(4, 0, JSON.parse(JSON.stringify(fixture.events[3])));",
        )
        self.assertEqual(error["path"], "$.events[4].seq")

    def test_deleted_failure_terminal_reports_terminal_status_path(self):
        error = mutation_error(
            "upstream-429-transient-terminal",
            "fixture.events.pop();",
        )
        self.assertEqual(error["path"], "$.checkpoints.afterSeq")


if __name__ == "__main__":
    unittest.main()
