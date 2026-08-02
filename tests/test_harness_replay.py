import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "replay-agent-traces.cjs"


def run_runner(*arguments, check=True):
    return subprocess.run(
        ["node", str(RUNNER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def run_node(script, check=True):
    return subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


class HarnessReplayRunnerTests(unittest.TestCase):
    def test_full_suite_replays_all_frozen_traces_offline(self):
        completed = run_runner("--json")
        summary = json.loads(completed.stdout)

        self.assertEqual(summary["replayVersion"], 1)
        self.assertEqual(summary["fixtureVersion"], 1)
        self.assertEqual(summary["fixtureCount"], 15)
        self.assertEqual(summary["eventCount"], 106)
        self.assertEqual(summary["checkpointCount"], 17)
        self.assertEqual(summary["checkpointRecoveryCount"], 17)
        self.assertEqual(summary["recoveryCount"], 4)
        self.assertEqual(len(summary["suiteReplayHash"]), 64)
        self.assertEqual(
            {result["name"] for result in summary["results"]},
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
        for result in summary["results"]:
            with self.subTest(fixture=result["name"]):
                self.assertEqual(result["stateHash"], result["duplicateStateHash"])
                for checkpoint in result["checkpoints"]:
                    self.assertEqual(checkpoint["resumedStateHash"], result["stateHash"])
                for recovery in result["recoveries"]:
                    self.assertEqual(recovery["stateHash"], result["stateHash"])

    def test_repeated_replay_and_named_or_tagged_subsets_are_deterministic(self):
        first = json.loads(run_runner("--json").stdout)
        second = json.loads(run_runner("--json").stdout)
        self.assertEqual(first["suiteReplayHash"], second["suiteReplayHash"])
        self.assertEqual(first["results"], second["results"])

        named = json.loads(
            run_runner("--fixture", "refresh-during-tools", "--json").stdout,
        )
        self.assertEqual(named["fixtureCount"], 1)
        self.assertEqual(named["results"][0]["name"], "refresh-during-tools")
        self.assertEqual(named["recoveryCount"], 1)

        tagged = json.loads(run_runner("--tag", "authorization", "--json").stdout)
        self.assertEqual(tagged["fixtureCount"], 2)
        self.assertEqual(
            [result["name"] for result in tagged["results"]],
            ["edit-authorization-accept", "command-authorization-reject"],
        )

    def test_missing_event_fails_at_the_first_sequence_path(self):
        completed = run_node(
            r"""
const runner = require("./scripts/replay-agent-traces.cjs");
const suite = runner.loadSuite();
const fixture = suite.fixtures.find((item) => item.name === "multi-tool-stage");
fixture.events = fixture.events.filter((event) => event.seq !== 4);
try {
  runner.runReplaySuite({fixtureVersion: 1, fixtures: [fixture]});
  process.exitCode = 2;
} catch (error) {
  process.stdout.write(JSON.stringify(error.toJSON()));
}
""",
        )
        error = json.loads(completed.stdout)
        self.assertEqual(error["name"], "ReplayAssertionError")
        self.assertEqual(error["fixture"], "multi-tool-stage")
        self.assertEqual(error["eventSeq"], 5)
        self.assertEqual(error["path"], "$.events[3].seq")
        self.assertEqual(error["expected"], 4)
        self.assertEqual(error["actual"], 5)

    def test_out_of_order_event_fails_before_projection_can_hide_it(self):
        completed = run_node(
            r"""
const runner = require("./scripts/replay-agent-traces.cjs");
const suite = runner.loadSuite();
const fixture = suite.fixtures.find((item) => item.name === "single-read-tool");
[fixture.events[1], fixture.events[2]] = [fixture.events[2], fixture.events[1]];
try {
  runner.runReplaySuite({fixtureVersion: 1, fixtures: [fixture]});
  process.exitCode = 2;
} catch (error) {
  process.stdout.write(JSON.stringify(error.toJSON()));
}
""",
        )
        error = json.loads(completed.stdout)
        self.assertEqual(error["name"], "ReplayAssertionError")
        self.assertEqual(error["fixture"], "single-read-tool")
        self.assertEqual(error["eventSeq"], 3)
        self.assertEqual(error["path"], "$.events[1].seq")
        self.assertEqual(error["expected"], 2)
        self.assertEqual(error["actual"], 3)

    def test_checkpoint_mismatch_reports_the_first_projection_path(self):
        completed = run_node(
            r"""
const runner = require("./scripts/replay-agent-traces.cjs");
const suite = runner.loadSuite();
const fixture = suite.fixtures.find((item) => item.name === "questionnaire-submit");
fixture.checkpoints[0].expectedState.status = "tools";
try {
  runner.runReplaySuite({fixtureVersion: 1, fixtures: [fixture]});
  process.exitCode = 2;
} catch (error) {
  process.stdout.write(JSON.stringify(error.toJSON()));
}
""",
        )
        error = json.loads(completed.stdout)
        self.assertEqual(error["name"], "ReplayAssertionError")
        self.assertEqual(error["fixture"], "questionnaire-submit")
        self.assertEqual(error["eventSeq"], 3)
        self.assertEqual(error["path"], "$.status")
        self.assertEqual(error["expected"], "tools")
        self.assertEqual(error["actual"], "waiting_user_input")

    def test_unknown_selection_is_a_clear_cli_failure(self):
        completed = run_runner(
            "--fixture",
            "missing-fixture",
            "--json",
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        error = json.loads(completed.stderr)
        self.assertEqual(error["name"], "ReplayAssertionError")
        self.assertEqual(error["fixture"], "<suite>")
        self.assertEqual(error["path"], "$.fixtures")


if __name__ == "__main__":
    unittest.main()
