"""Offline v2 Child AgentRun replay and first-difference diagnostics for H3-2B2."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "replay-agent-multi-run-traces.cjs"
SINGLE_RUNNER = ROOT / "scripts" / "replay-agent-traces.cjs"
SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "child-agent-multi-run-trace-suite.json"
SINGLE_SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "trace-suite.json"
EXPECTED_FIXTURE_SUITE_HASH = "0ab4fb75adfd3a0818db55f1e57b02fa5aabdcf9b6c156fd8827dfb98e7255da"
EXPECTED_SUITE_REPLAY_HASH = "764f914012c0bb5c1e635725eac39b3b120374262a20d3b251c8b7645531c618"
EXPECTED_COMPOSITE_HASH = "176f9e3324d213fe6ac5c9a3bc12e78d7b3f6dd004b3124b7a188c36801158a0"
EXPECTED_RUN_HASHES = {
    "P1": "f88a0d3c606050608d2836f38fd2010f47f9a3243ff728b9d886dd40d869d065",
    "C1": "4c1c79fff9cd4cd04ab807bcdc4f572c6bba1c21ebb5091d8f7ca3c50bd5c46d",
    "C2": "472d381a1923b8060fbf3732b599b1ac334d1f89bc04de47b05aa3e06307c6cd",
}
EXPECTED_V1_HASHES = {
    "fixture": "710a3e5677281d3554f33a2b0fa11fd84a52270c6b90e0aa96e9b93da534880a",
    "suite": "095537b72121478d1ef35a143aa6ecd361c0ec557a4fcc9594e3b024e86aabf6",
    "composite": "5bfc185b1f31979e3802b1908d1b908c6f64d4ccc5ca882da158e7b840504e85",
    "F1": "996792e15f8182f3b7c7f04acd862efdb5fd5ba590cca34a20d03ab3708b112a",
    "B1": "2de637407b7156c3d32a94f95fa4e824c0a089c86436f9d78c600fd1340b817a",
    "F2": "2959cee047a402407bd8b8d29cc2b46fa8b00b7b3e2c17abb647cebc967e1d6a",
}
EXPECTED_SINGLE_FIXTURE_HASH = "c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc"
EXPECTED_SINGLE_REPLAY_HASH = "166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2"


def run_runner(*arguments, check=True):
    return subprocess.run(
        ["node", str(RUNNER), "--suite", str(SUITE_PATH), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_default_runner(*arguments):
    return subprocess.run(
        ["node", str(RUNNER), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
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
const suite = runner.loadSuite("./tests/fixtures/harness/child-agent-multi-run-trace-suite.json");
const scenario = JSON.parse(JSON.stringify(suite.scenarios[0]));
{mutation}
try {{
  runner.replayScenario(scenario, {{fixtureVersion: 2, ...({options})}});
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


class HarnessChildMultiRunReplayTests(unittest.TestCase):
    def test_v2_suite_replays_offline_with_independent_counts_and_hashes(self):
        summary = json.loads(run_runner("--json").stdout)
        self.assertEqual(summary["replayVersion"], 1)
        self.assertEqual(summary["multiRunFixtureVersion"], 2)
        self.assertEqual(summary["scenarioCount"], 1)
        self.assertEqual(summary["runCount"], 3)
        self.assertEqual(summary["eventCount"], 21)
        self.assertEqual(summary["scheduleStepCount"], 21)
        self.assertEqual(summary["factMarkerCount"], 0)
        self.assertEqual(summary["checkpointCount"], 6)
        self.assertEqual(summary["checkpointRecoveryCount"], 6)
        self.assertEqual(summary["fixtureSuiteHash"], EXPECTED_FIXTURE_SUITE_HASH)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_SUITE_REPLAY_HASH)

        result = summary["results"][0]
        self.assertEqual(
            result["name"],
            "child-agent-out-of-order-terminal-parent-results",
        )
        self.assertEqual(result["stateHash"], EXPECTED_COMPOSITE_HASH)
        self.assertEqual(result["duplicateStateHash"], EXPECTED_COMPOSITE_HASH)
        self.assertEqual(result["runStateHashes"], EXPECTED_RUN_HASHES)
        self.assertEqual(result["duplicateRunStateHashes"], EXPECTED_RUN_HASHES)
        self.assertEqual(result["orders"]["creation"], ["P1", "C1", "C2"])
        self.assertEqual(result["orders"]["terminal"], ["C2", "C1", "P1"])
        self.assertEqual(result["orders"]["childCreated"], ["T1:C1", "T2:C2"])
        self.assertEqual(result["orders"]["childTerminal"], ["C2", "C1"])
        self.assertEqual(result["orders"]["parentToolResults"], ["T1", "T2"])
        self.assertEqual(result["orders"]["factMarkers"], [])
        self.assertEqual(result["factMarkerChecks"], [])
        for checkpoint in result["checkpoints"]:
            with self.subTest(after_step=checkpoint["afterStep"]):
                self.assertEqual(checkpoint["resumedStateHash"], EXPECTED_COMPOSITE_HASH)
                self.assertEqual(checkpoint["resumedRunStateHashes"], EXPECTED_RUN_HASHES)

    def test_v2_named_listed_and_repeated_replay_are_deterministic(self):
        first = json.loads(run_runner("--json").stdout)
        second = json.loads(run_runner("--json").stdout)
        named = json.loads(run_runner(
            "--scenario",
            "child-agent-out-of-order-terminal-parent-results",
            "--json",
        ).stdout)
        listed = run_runner("--list").stdout.strip().splitlines()
        self.assertEqual(first, second)
        self.assertEqual(named, first)
        self.assertEqual(listed, ["child-agent-out-of-order-terminal-parent-results"])

    def test_default_cli_and_all_v1_hashes_remain_unchanged(self):
        summary = json.loads(run_default_runner("--json").stdout)
        result = summary["results"][0]
        self.assertEqual(summary["multiRunFixtureVersion"], 1)
        self.assertEqual(summary["fixtureSuiteHash"], EXPECTED_V1_HASHES["fixture"])
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_V1_HASHES["suite"])
        self.assertEqual(result["stateHash"], EXPECTED_V1_HASHES["composite"])
        self.assertEqual(
            result["runStateHashes"],
            {key: EXPECTED_V1_HASHES[key] for key in ("F1", "B1", "F2")},
        )

    def test_single_run_baseline_and_hashes_remain_unchanged(self):
        summary = json.loads(run_single_runner("--json").stdout)
        single_suite = json.loads(SINGLE_SUITE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(summary["fixtureCount"], 17)
        self.assertEqual(summary["eventCount"], 124)
        self.assertEqual(summary["checkpointCount"], 25)
        self.assertEqual(summary["checkpointRecoveryCount"], 25)
        self.assertEqual(summary["recoveryCount"], 4)
        self.assertEqual(canonical_hash(single_suite), EXPECTED_SINGLE_FIXTURE_HASH)
        self.assertEqual(summary["suiteReplayHash"], EXPECTED_SINGLE_REPLAY_HASH)

    def test_runner_reuses_production_projection_without_child_business_state_machine(self):
        source = RUNNER.read_text(encoding="utf-8")
        for forbidden in (
            "_start_agent_worker",
            "_execute_agent_delegation_batch",
            "_complete_agent_delegation",
            "childUsageMerged",
            "usageLedger",
            "pumpQueuedSessionMessages",
            "pumpBackgroundDispatcher",
            "appendSessionMessages",
            "renderSessionMessages",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("reduceRunProjectionInput", source)
        self.assertIn("projectRunViewModel", source)

    def test_wrong_parent_run_reports_child_identity_path(self):
        error = mutation_error(run_mutation(
            "scenario.identities.agentRuns.C1.parentAgentRunId = "
            "scenario.identities.agentRuns.C2.agentRunId;"
        ))
        self.assertEqual(error["path"], "$.identities.agentRuns.C1.parentAgentRunId")

    def test_duplicate_and_wrong_parent_tool_relations_have_frozen_paths(self):
        cases = (
            (
                'scenario.identities.agentRuns.C2.parentToolCallId = "T1";',
                "$.identities.agentRuns.C2.parentToolCallId",
            ),
            (
                'scenario.identities.agentRuns.C2.parentToolCallId = "T9";',
                "$.runs.P1.events[2].data.toolCalls[1]",
            ),
        )
        for mutation, expected_path in cases:
            with self.subTest(mutation=mutation):
                error = mutation_error(run_mutation(mutation))
                self.assertEqual(error["path"], expected_path)

    def test_missing_and_miswritten_child_created_events_have_frozen_paths(self):
        cases = (
            (
                'scenario.runs.P1.events[4].type = "model_pending"; '
                "scenario.runs.P1.events[4].data = {round: 1};",
                "$.runs.P1.events",
            ),
            (
                "scenario.runs.P1.events[4].data.childAgentRunId = "
                "scenario.identities.agentRuns.C2.agentRunId;",
                "$.runs.P1.events[4].data.childAgentRunId",
            ),
        )
        for mutation, expected_path in cases:
            with self.subTest(mutation=mutation):
                error = mutation_error(run_mutation(mutation))
                self.assertEqual(error["path"], expected_path)

    def test_wrong_parent_result_child_id_reports_raw_result_path(self):
        error = mutation_error(run_mutation(
            "scenario.runs.P1.events[7].data.result.childAgentRunId = "
            "scenario.identities.agentRuns.C2.agentRunId;"
        ))
        self.assertEqual(
            error["path"],
            "$.runs.P1.events[7].data.result.childAgentRunId",
        )

    def test_child_terminal_order_mutation_reports_child_order_path(self):
        error = mutation_error(run_mutation(
            """
const original = scenario.schedule.map((entry) => ({...entry}));
const order = [13, 14, 11, 12];
for (let offset = 0; offset < order.length; offset += 1) {
  scenario.schedule[11 + offset] = {...original[order[offset]], step: 12 + offset};
}
"""
        ))
        self.assertEqual(error["path"], "$.orders.childTerminal[0]")

    def test_parent_result_before_all_children_terminal_reports_schedule_path(self):
        error = mutation_error(run_mutation(
            """
const original = scenario.schedule.map((entry) => ({...entry}));
const order = [15, 13, 14];
for (let offset = 0; offset < order.length; offset += 1) {
  scenario.schedule[13 + offset] = {...original[order[offset]], step: 14 + offset};
}
"""
        ))
        self.assertEqual(error["path"], "$.schedule[13].eventSeq")

    def test_parent_result_order_mutation_reports_parent_order_path(self):
        error = mutation_error(run_mutation(
            """
const first = scenario.runs.P1.events[7];
const second = scenario.runs.P1.events[8];
scenario.runs.P1.events[7] = {...second, seq: 8};
scenario.runs.P1.events[8] = {...first, seq: 9};
"""
        ))
        self.assertEqual(error["path"], "$.orders.parentToolResults[0]")

    def test_duplicate_schedule_event_reports_first_duplicate_path(self):
        error = mutation_error(run_mutation(
            """
const duplicate = {...scenario.schedule[12]};
scenario.schedule.splice(13, 0, duplicate);
scenario.schedule.forEach((entry, index) => { entry.step = index + 1; });
"""
        ))
        self.assertEqual(error["path"], "$.schedule[13].eventSeq")

    def test_v2_composite_recovery_state_pollution_reports_resumed_run_path(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 3) state.runStates.P1.status = "failed";
  }
}""",
        ))
        self.assertEqual(
            error["path"],
            "$.checkpoints[3].resume.runs.P1.diagnostics[0]",
        )

    def test_v2_composite_recovery_cursor_pollution_has_frozen_paths(self):
        cases = (
            (
                "state.scheduleCursor -= 1;",
                "$.checkpoints[3].resume.runCursors.C1",
            ),
            (
                "state.scheduleCursor += 1;",
                "$.checkpoints[3].resume.runCursors.P1",
            ),
            (
                "state.scheduleCursor = scenario.schedule.length + 1;",
                "$.checkpoints[3].resume.scheduleCursor",
            ),
        )
        for mutation, expected_path in cases:
            with self.subTest(mutation=mutation):
                error = mutation_error(run_mutation(
                    "",
                    """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 3) MUTATION
  }
}""".replace("MUTATION", mutation),
                ))
                self.assertEqual(error["path"], expected_path)

    def test_v2_composite_recovery_requires_exact_run_keys(self):
        error = mutation_error(run_mutation(
            "",
            """{
  resumeStateMutator({checkpointIndex, state}) {
    if (checkpointIndex === 3) state.runCursors.EXTRA = 0;
  }
}""",
        ))
        self.assertEqual(error["path"], "$.checkpoints[3].resume.runCursors[2]")


if __name__ == "__main__":
    unittest.main()
