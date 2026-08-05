"""Offline multi-run replay and first-difference diagnostics for H3-2B1."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "replay-agent-multi-run-traces.cjs"
SINGLE_RUNNER = ROOT / "scripts" / "replay-agent-traces.cjs"
SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "multi-run-trace-suite.json"
SINGLE_SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "trace-suite.json"
EXPECTED_COMPOSITE_HASH = "5bfc185b1f31979e3802b1908d1b908c6f64d4ccc5ca882da158e7b840504e85"
EXPECTED_FIXTURE_SUITE_HASH = "710a3e5677281d3554f33a2b0fa11fd84a52270c6b90e0aa96e9b93da534880a"
EXPECTED_SUITE_REPLAY_HASH = "095537b72121478d1ef35a143aa6ecd361c0ec557a4fcc9594e3b024e86aabf6"
EXPECTED_SINGLE_FIXTURE_HASH = "c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc"
EXPECTED_SINGLE_REPLAY_HASH = "166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2"


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
        ["node", str(RUNNER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def run_single_runner(*arguments):
    return subprocess.run(
        ["node", str(SINGLE_RUNNER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def run_mutation(mutation, options="{}"):
    script = f"""
const runner = require("./scripts/replay-agent-multi-run-traces.cjs");
const suite = runner.loadSuite();
const scenario = JSON.parse(JSON.stringify(suite.scenarios[0]));
{mutation}
try {{
  runner.replayScenario(scenario, {options});
}} catch (error) {{
  process.stderr.write(JSON.stringify(error.toJSON ? error.toJSON() : {{
    name: error.name,
    message: error.message,
  }}) + "\\n");
  process.exitCode = 1;
}}
"""
    return subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def mutation_error(completed):
    if completed.returncode == 0:
        raise AssertionError("mutation unexpectedly passed")
    return json.loads(completed.stderr.strip().splitlines()[-1])


class HarnessMultiRunReplayTests(unittest.TestCase):
    def test_full_multi_run_suite_replays_offline_with_separate_counts_and_hashes(self):
        summary = json.loads(run_runner("--json").stdout)
        self.assertEqual(summary["replayVersion"], 1)
        self.assertEqual(summary["multiRunFixtureVersion"], 1)
        self.assertEqual(summary["scenarioCount"], 1)
        self.assertEqual(summary["runCount"], 3)
        self.assertEqual(summary["eventCount"], 12)
        self.assertEqual(summary["scheduleStepCount"], 15)
        self.assertEqual(summary["factMarkerCount"], 3)
        self.assertEqual(summary["checkpointCount"], 4)
        self.assertEqual(summary["checkpointRecoveryCount"], 4)
        self.assertEqual(summary["fixtureSuiteHash"], EXPECTED_FIXTURE_SUITE_HASH)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_SUITE_REPLAY_HASH)

        result = summary["results"][0]
        self.assertEqual(result["name"], "queue-parallel-multi-run-relations")
        self.assertEqual(result["stateHash"], EXPECTED_COMPOSITE_HASH)
        self.assertEqual(result["duplicateStateHash"], EXPECTED_COMPOSITE_HASH)
        self.assertEqual(result["duplicateRunStateHashes"], result["runStateHashes"])
        self.assertEqual(result["orders"]["creation"], ["F1", "B1", "F2"])
        self.assertEqual(result["orders"]["terminal"], ["F1", "F2", "B1"])
        self.assertEqual(
            result["orders"]["factMarkers"],
            ["queue-submitted:Q1", "background-dispatched:J1", "queue-run-linked:Q1"],
        )
        self.assertEqual(len(result["factMarkerChecks"]), 3)
        self.assertEqual(
            result["factMarkerChecks"][0]["runStateHash"],
            result["factMarkerChecks"][1]["runStateHash"],
        )
        for checkpoint in result["checkpoints"]:
            with self.subTest(after_step=checkpoint["afterStep"]):
                self.assertEqual(checkpoint["resumedStateHash"], EXPECTED_COMPOSITE_HASH)
                self.assertEqual(
                    checkpoint["resumedRunStateHashes"],
                    result["runStateHashes"],
                )

    def test_repeated_and_named_replay_are_deterministic(self):
        first = json.loads(run_runner("--json").stdout)
        second = json.loads(run_runner("--json").stdout)
        named = json.loads(
            run_runner(
                "--scenario",
                "queue-parallel-multi-run-relations",
                "--json",
            ).stdout
        )
        listed = run_runner("--list").stdout.strip().splitlines()
        self.assertEqual(first, second)
        self.assertEqual(named, first)
        self.assertEqual(listed, ["queue-parallel-multi-run-relations"])

    def test_existing_single_run_baseline_and_hashes_remain_unchanged(self):
        summary = json.loads(run_single_runner("--json").stdout)
        single_suite = json.loads(SINGLE_SUITE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(summary["fixtureCount"], 17)
        self.assertEqual(summary["eventCount"], 124)
        self.assertEqual(summary["checkpointCount"], 25)
        self.assertEqual(summary["checkpointRecoveryCount"], 25)
        self.assertEqual(summary["recoveryCount"], 4)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_SINGLE_REPLAY_HASH)
        self.assertEqual(canonical_hash(single_suite), EXPECTED_SINGLE_FIXTURE_HASH)

    def test_runner_has_no_queue_background_ui_or_usage_business_state_machine(self):
        source = RUNNER.read_text(encoding="utf-8")
        for forbidden in (
            "pumpQueuedSessionMessages",
            "pumpBackgroundDispatcher",
            "runQueuedSessionMessage",
            "runBackgroundSubAgentJob",
            "finishQueuedSessionMessage",
            "mergeBackgroundUsage",
            "appendSessionMessages",
            "renderSessionMessages",
            "buildBackgroundResultMessage",
            "mergeBackgroundUsageStats",
            "createSessionStateAccessors",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("reduceRunProjectionInput", source)
        self.assertIn("projectRunViewModel", source)

    def test_wrong_run_delivery_reports_agent_run_identity_path(self):
        error = mutation_error(run_mutation(
            'scenario.schedule.find((entry) => entry.step === 7).runKey = "B1";'
        ))
        self.assertEqual(error["path"], "$.schedule[6].agentRunId")

    def test_invalid_schedule_reference_reports_event_path(self):
        error = mutation_error(run_mutation(
            "scenario.schedule[0].eventSeq = 99;"
        ))
        self.assertEqual(error["path"], "$.schedule[0].eventSeq")

    def test_identity_conflict_reports_second_agent_run_path(self):
        error = mutation_error(run_mutation(
            "scenario.identities.agentRuns.B1.agentRunId = "
            "scenario.identities.agentRuns.F1.agentRunId;"
        ))
        self.assertEqual(error["path"], "$.identities.agentRuns.B1.agentRunId")

    def test_cross_session_run_reports_session_path(self):
        error = mutation_error(run_mutation(
            'scenario.identities.agentRuns.B1.sessionId = "session-fixture-other";'
        ))
        self.assertEqual(error["path"], "$.identities.agentRuns.B1.sessionId")

    def test_creation_order_mutation_reports_first_order_difference(self):
        error = mutation_error(run_mutation(
            """
const original = scenario.schedule.map((entry) => ({...entry}));
const order = [4, 0, 1, 2, 3, 5];
for (let index = 0; index < order.length; index += 1) {
  scenario.schedule[index] = {...original[order[index]], step: index + 1};
}
"""
        ))
        self.assertEqual(error["path"], "$.orders.creation[0]")

    def test_terminal_order_mutation_reports_first_order_difference(self):
        error = mutation_error(run_mutation(
            """
const original = scenario.schedule.map((entry) => ({...entry}));
const order = [13, 14, 11, 12];
for (let offset = 0; offset < order.length; offset += 1) {
  scenario.schedule[11 + offset] = {...original[order[offset]], step: 12 + offset};
}
"""
        ))
        self.assertEqual(error["path"], "$.orders.terminal[1]")

    def test_composite_recovery_mutation_reports_resumed_run_path(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 2) state.runStates.F2.status = "failed";
  }
}""",
        ))
        self.assertEqual(error["path"], "$.checkpoints[2].resume.runs.F2.status")

    def test_composite_recovery_rejects_regressed_schedule_cursor(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 0) state.scheduleCursor -= 1;
  }
}""",
        ))
        self.assertEqual(
            error["path"],
            "$.checkpoints[0].resume.runCursors.B1",
        )

    def test_composite_recovery_rejects_advanced_schedule_cursor(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 0) state.scheduleCursor += 1;
  }
}""",
        ))
        self.assertEqual(
            error["path"],
            "$.checkpoints[0].resume.runCursors.F1",
        )

    def test_composite_recovery_rejects_out_of_range_schedule_cursor(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 0) state.scheduleCursor = scenario.schedule.length + 1;
  }
}""",
        ))
        self.assertEqual(
            error["path"],
            "$.checkpoints[0].resume.scheduleCursor",
        )

    def test_composite_recovery_requires_exact_run_keys_and_state_cursors(self):
        cases = (
            (
                "delete state.runStates.F2;",
                "$.checkpoints[0].resume.runStates[2]",
            ),
                (
                    "state.runCursors.EXTRA = 0;",
                    "$.checkpoints[0].resume.runCursors[1]",
                ),
            (
                "state.runStates.B1.cursor -= 1;",
                "$.checkpoints[0].resume.runStates.B1.cursor",
            ),
        )
        for mutation, expected_path in cases:
            with self.subTest(mutation=mutation):
                error = mutation_error(run_mutation(
                    "",
                    """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 0) MUTATION
  }
}""".replace("MUTATION", mutation),
                ))
                self.assertEqual(error["path"], expected_path)

    def test_duplicate_schedule_event_reports_first_duplicate_path(self):
        error = mutation_error(run_mutation(
            """
const duplicate = {...scenario.schedule[6]};
scenario.schedule.splice(7, 0, duplicate);
scenario.schedule.forEach((entry, index) => { entry.step = index + 1; });
"""
        ))
        self.assertEqual(error["path"], "$.schedule[7].eventSeq")


if __name__ == "__main__":
    unittest.main()
