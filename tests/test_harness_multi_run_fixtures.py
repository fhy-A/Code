"""Strict fixture and direct production-function contracts for H3-2B1."""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

import server as server_mod


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "multi-run-trace-suite.schema.json"
SUITE_PATH = FIXTURE_DIR / "multi-run-trace-suite.json"
EXPECTED_FIXTURE_SUITE_HASH = "710a3e5677281d3554f33a2b0fa11fd84a52270c6b90e0aa96e9b93da534880a"


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_node(script):
    return subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


class HarnessMultiRunFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
        cls.scenario = cls.suite["scenarios"][0]

    def test_multi_run_schema_is_strict_versioned_and_accepts_the_suite(self):
        Draft202012Validator.check_schema(self.schema)
        validator = Draft202012Validator(
            self.schema,
            format_checker=FormatChecker(),
        )
        errors = sorted(validator.iter_errors(self.suite), key=lambda error: list(error.path))
        self.assertEqual(errors, [])
        self.assertEqual(self.schema["properties"]["multiRunFixtureVersion"]["const"], 1)
        self.assertEqual(self.suite["multiRunFixtureVersion"], 1)
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["scenario"]["additionalProperties"])

        mutated = json.loads(json.dumps(self.suite))
        mutated["scenarios"][0]["unexpectedBusinessState"] = {}
        paths = [list(error.path) for error in validator.iter_errors(mutated)]
        self.assertIn(["scenarios", 0], paths)

    def test_multi_run_counts_names_and_raw_hash_are_frozen_separately(self):
        scenarios = self.suite["scenarios"]
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(
            [scenario["name"] for scenario in scenarios],
            ["queue-parallel-multi-run-relations"],
        )
        self.assertEqual(len(self.scenario["runs"]), 3)
        self.assertEqual(
            sum(len(run["events"]) for run in self.scenario["runs"].values()),
            12,
        )
        self.assertEqual(len(self.scenario["schedule"]), 15)
        self.assertEqual(
            sum(entry["kind"] == "fact-marker" for entry in self.scenario["schedule"]),
            3,
        )
        self.assertEqual(len(self.scenario["checkpoints"]), 4)
        self.assertEqual(canonical_hash(self.suite), EXPECTED_FIXTURE_SUITE_HASH)

    def test_static_identity_graph_uses_the_production_agent_run_id_function(self):
        identities = self.scenario["identities"]
        session = identities["sessions"]["S1"]
        agent_runs = identities["agentRuns"]

        for run_key, identity in agent_runs.items():
            with self.subTest(run=run_key):
                self.assertEqual(identity["sessionId"], session["sessionId"])
                self.assertEqual(identity["parentAgentRunId"], "")
                self.assertEqual(identity["parentToolCallId"], "")
                self.assertEqual(
                    identity["agentRunId"],
                    server_mod._agent_run_id_for_client_request(
                        identity["sessionId"],
                        identity["clientRequestId"],
                    ),
                )

        queue_item = identities["queueItems"]["Q1"]
        background_job = identities["backgroundJobs"]["J1"]
        self.assertEqual(queue_item["agentRunKey"], "F2")
        self.assertEqual(
            queue_item["clientRequestId"],
            agent_runs[queue_item["agentRunKey"]]["clientRequestId"],
        )
        self.assertEqual(background_job["agentRunKey"], "B1")
        self.assertEqual(background_job["parentForegroundRunKey"], "F1")
        self.assertEqual(
            background_job["clientRequestId"],
            agent_runs[background_job["agentRunKey"]]["clientRequestId"],
        )
        self.assertEqual(agent_runs["B1"]["role"], "background")
        self.assertEqual(agent_runs["B1"]["parentAgentRunId"], "")

    def test_runtime_identities_close_against_their_run_events(self):
        runtimes = self.scenario["identities"]["runtimes"]
        observed = {}
        for run_key, run in self.scenario["runs"].items():
            for event in run["events"]:
                runtime_run_id = event["data"].get("runtimeRunId")
                if runtime_run_id:
                    observed.setdefault(runtime_run_id, set()).add(
                        (run_key, event["data"].get("round"))
                    )

        for runtime in runtimes.values():
            with self.subTest(runtime=runtime["runtimeRunId"]):
                self.assertEqual(
                    observed[runtime["runtimeRunId"]],
                    {(runtime["agentRunKey"], runtime["round"])},
                )

    def test_session_accessors_and_background_helpers_are_direct_contracts_only(self):
        completed = run_node(
            r"""
const suite = require("./tests/fixtures/harness/multi-run-trace-suite.json");
const scenario = suite.scenarios[0];
global.window = {};
require("./src/core/namespace.js");
require("./src/core/state.js");
require("./src/agent/subagents.js");

const stateModule = window.Code.core.state;
const subagents = window.Code.agent.subagents;
const identities = scenario.identities;
const direct = scenario.directContracts;
const session = identities.sessions.S1;
const queueItem = identities.queueItems.Q1;
const backgroundJob = identities.backgroundJobs.J1;
const backgroundRun = identities.agentRuns[backgroundJob.agentRunKey];

const state = stateModule.createAppState({getItem() { return null; }});
state.sessions = [{id: session.sessionId}, {id: "session-fixture-empty"}];
state.sessionId = session.sessionId;
const accessors = stateModule.createSessionStateAccessors(state);
accessors.setQueuedMessageCheckpoints(session.sessionId, [{
  id: queueItem.id,
  clientRequestId: queueItem.clientRequestId,
  status: direct.sessionAccessors.queueStatus,
}]);
accessors.setBackgroundRunCheckpoint(session.sessionId, {
  id: backgroundJob.id,
  clientRequestId: backgroundJob.clientRequestId,
  status: direct.sessionAccessors.backgroundStatus,
  agentRunId: backgroundRun.agentRunId,
  cursor: direct.sessionAccessors.backgroundCursor,
});
const stored = {
  queued: accessors.getQueuedMessageCheckpoints(session.sessionId),
  background: accessors.getBackgroundRunCheckpoints(session.sessionId),
  otherQueued: accessors.getQueuedMessageCheckpoints("session-fixture-empty"),
  otherBackground: accessors.getBackgroundRunCheckpoints("session-fixture-empty"),
};
accessors.removeBackgroundRunCheckpoint(session.sessionId, backgroundJob.id);
const afterExplicitRemove = {
  queued: accessors.getQueuedMessageCheckpoints(session.sessionId),
  background: accessors.getBackgroundRunCheckpoints(session.sessionId),
};

const parsedParallel = subagents.parseParallelCommand(direct.parallelCommand.input);
const checkpoint = subagents.buildBackgroundJobCheckpoint({
  id: backgroundJob.id,
  clientRequestId: backgroundJob.clientRequestId,
  status: direct.sessionAccessors.backgroundStatus,
  agentRunId: backgroundRun.agentRunId,
  cursor: direct.sessionAccessors.backgroundCursor,
  userText: direct.parallelCommand.expectedTask,
  model: direct.backgroundResult.model,
  queuedAt: 1000,
  deadlineAt: 5000,
}, 2000);
const restored = subagents.buildRestoredBackgroundJobData(checkpoint, {
  sessionId: session.sessionId,
});
const resultMessage = subagents.buildBackgroundResultMessage({
  id: backgroundJob.id,
  agentRunId: backgroundRun.agentRunId,
  parentTaskStartedAt: 500,
}, {
  content: direct.backgroundResult.content,
  model: direct.backgroundResult.model,
  timestamp: direct.backgroundResult.timestamp,
  responseTime: direct.backgroundResult.responseTime,
  usage: direct.backgroundResult.usage,
  includeUsage: true,
});
const resultDetection = {
  absent: subagents.hasBackgroundResult([], backgroundJob.id),
  present: subagents.hasBackgroundResult([resultMessage], backgroundJob.id),
};
const mergedUsage = subagents.mergeBackgroundUsageStats(
  direct.usageMerge.current,
  direct.usageMerge.child,
);

process.stdout.write(JSON.stringify({
  stored,
  afterExplicitRemove,
  parsedParallel,
  checkpoint,
  restored,
  resultMessage,
  resultDetection,
  mergedUsage,
}));
"""
        )
        data = json.loads(completed.stdout)
        direct = self.scenario["directContracts"]
        queue_item = self.scenario["identities"]["queueItems"]["Q1"]
        background_job = self.scenario["identities"]["backgroundJobs"]["J1"]
        background_run = self.scenario["identities"]["agentRuns"]["B1"]

        self.assertEqual(data["stored"]["queued"], [{
            "id": queue_item["id"],
            "clientRequestId": queue_item["clientRequestId"],
            "status": direct["sessionAccessors"]["queueStatus"],
        }])
        self.assertEqual(data["stored"]["background"][0]["id"], background_job["id"])
        self.assertEqual(data["stored"]["otherQueued"], [])
        self.assertEqual(data["stored"]["otherBackground"], [])
        self.assertEqual(data["afterExplicitRemove"]["queued"], data["stored"]["queued"])
        self.assertEqual(data["afterExplicitRemove"]["background"], [])

        self.assertEqual(data["parsedParallel"], direct["parallelCommand"]["expectedTask"])
        self.assertEqual(data["checkpoint"]["agentRunId"], background_run["agentRunId"])
        self.assertEqual(
            data["checkpoint"]["cursor"],
            direct["sessionAccessors"]["backgroundCursor"],
        )
        self.assertEqual(data["restored"]["sessionId"], "session-fixture-multi-1")
        self.assertEqual(data["restored"]["status"], "pending")
        self.assertTrue(data["restored"]["restored"])

        self.assertEqual(data["resultMessage"]["meta"]["jobId"], background_job["id"])
        self.assertEqual(
            data["resultMessage"]["meta"]["agentRunId"],
            background_run["agentRunId"],
        )
        self.assertEqual(
            data["resultMessage"]["meta"]["_usage"],
            direct["backgroundResult"]["usage"],
        )
        self.assertEqual(data["resultDetection"], {"absent": False, "present": True})
        self.assertEqual(data["mergedUsage"], direct["usageMerge"]["expected"])

    def test_multi_run_suite_contains_only_synthetic_sanitized_content(self):
        serialized = json.dumps(self.suite, ensure_ascii=False)
        for forbidden in (
            r"(?i)authorization\s*:",
            r"(?i)bearer\s+",
            r"(?i)cookie\s*:",
            r"(?i)sk-[a-z0-9]",
            r"(?i)api[_ -]?key",
            r"[A-Za-z]:\\",
            r"https?://",
        ):
            with self.subTest(pattern=forbidden):
                self.assertIsNone(re.search(forbidden, serialized))
        self.assertIn("Synthetic", serialized)


if __name__ == "__main__":
    unittest.main()
