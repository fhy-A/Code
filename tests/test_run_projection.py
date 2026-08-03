import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REDUCER_SOURCE = (ROOT / "src" / "agent" / "run-reducer.js").read_text(encoding="utf-8")
VIEW_MODEL_SOURCE = (ROOT / "src" / "ui" / "run-view-model.js").read_text(encoding="utf-8")
SHADOW_SOURCE = (ROOT / "src" / "agent" / "run-projection-shadow.js").read_text(encoding="utf-8")


def run_node(script):
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


class RunProjectionContractTests(unittest.TestCase):
    def test_observed_model_round_keeps_started_background_round_ahead_of_snapshot(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const shadow = window.Code.agent.runProjectionShadow;
process.stdout.write(JSON.stringify({
  firstStarted: shadow.resolveObservedModelRoundCount(0, 1),
  secondStarted: shadow.resolveObservedModelRoundCount(1, 2),
  completedSnapshot: shadow.resolveObservedModelRoundCount(2, 2),
  replayedSnapshotAhead: shadow.resolveObservedModelRoundCount(3, 2),
}));
""")
        self.assertEqual(data["firstStarted"], 1)
        self.assertEqual(data["secondStarted"], 2)
        self.assertEqual(data["completedSnapshot"], 2)
        self.assertEqual(data["replayedSnapshotAhead"], 3)

    def test_modules_are_pure_and_export_the_frozen_h2_contract(self):
        for forbidden in ("fetch(", "document.", "localStorage", "sessionStorage", "Date.now"):
            self.assertNotIn(forbidden, REDUCER_SOURCE)
            self.assertNotIn(forbidden, VIEW_MODEL_SOURCE)
            self.assertNotIn(forbidden, SHADOW_SOURCE)

        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const reducer = window.Code.agent.runReducer;
const view = window.Code.ui.runViewModel;
const shadow = window.Code.agent.runProjectionShadow;
process.stdout.write(JSON.stringify({
  reducerVersion: reducer.RUN_PROJECTION_SCHEMA_VERSION,
  viewVersion: view.RUN_VIEW_MODEL_SCHEMA_VERSION,
  statusCount: reducer.RUN_STATUSES.length,
  eventTypes: reducer.KNOWN_EVENT_TYPES,
  fields: view.RUN_PROJECTION_COMPARISON_FIELDS,
  reducerFrozen: Object.isFrozen(reducer),
  viewFrozen: Object.isFrozen(view),
  shadowVersion: shadow.RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
  shadowLimit: shadow.DEFAULT_MAX_DIAGNOSTICS,
  shadowFrozen: Object.isFrozen(shadow),
}));
""")
        self.assertEqual(data["reducerVersion"], 1)
        self.assertEqual(data["viewVersion"], 1)
        self.assertEqual(data["statusCount"], 8)
        self.assertEqual(len(data["eventTypes"]), 24)
        self.assertEqual(
            data["fields"],
            [
                "status",
                "terminalStatus",
                "modelRoundCount",
                "toolCount",
                "pendingKind",
                "elapsedMs",
                "timeline",
            ],
        )
        self.assertTrue(data["reducerFrozen"])
        self.assertTrue(data["viewFrozen"])
        self.assertEqual(data["shadowVersion"], 1)
        self.assertEqual(data["shadowLimit"], 64)
        self.assertTrue(data["shadowFrozen"])

    def test_shadow_observer_matches_a_complete_event_and_snapshot_trace(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const shadowApi = window.Code.agent.runProjectionShadow;
const initialSnapshot = {
  status: "model",
  eventCursor: 0,
  createdAt: "2030-01-01T00:00:00Z",
  updatedAt: "2030-01-01T00:00:00Z",
  elapsedObservedAt: "2030-01-01T00:00:00Z",
  elapsedMs: 0,
};
const events = [
  {protocolVersion: 1, seq: 1, type: "model_started", data: {round: 1, runtimeRunId: "round-1"}, createdAt: "2030-01-01T00:00:01Z"},
  {protocolVersion: 1, seq: 2, type: "tool_started", data: {toolCallId: "tool-1", name: "read_file"}, createdAt: "2030-01-01T00:00:02Z"},
  {protocolVersion: 1, seq: 3, type: "tool_completed", data: {toolCallId: "tool-1", name: "read_file", outcome: "succeeded"}, createdAt: "2030-01-01T00:00:03Z"},
  {protocolVersion: 1, seq: 4, type: "completed", data: {}, createdAt: "2030-01-01T00:00:04Z"},
];
const observer = shadowApi.createRunProjectionShadow({initialSnapshot});
const legacy = shadowApi.createLegacyProjectionObservation();
for (const event of events) {
  shadowApi.observeProjectionEvent(observer, event);
  shadowApi.observeLegacyProjectionEvent(legacy, event);
}
const snapshot = {
  status: "completed",
  round: 1,
  toolExecutions: [{toolCallId: "tool-1", name: "read_file", status: "completed", outcome: "succeeded"}],
  createdAt: "2030-01-01T00:00:00Z",
  updatedAt: "2030-01-01T00:00:04Z",
  completedAt: "2030-01-01T00:00:04Z",
  elapsedObservedAt: "2030-01-01T00:00:04Z",
  elapsedMs: 4000,
};
shadowApi.observeProjectionSnapshot(observer, snapshot);
const legacyFacts = shadowApi.snapshotLegacyProjectionObservation(legacy);
const equal = shadowApi.compareProjectionShadow(observer, {
  status: "completed",
  terminalStatus: "completed",
  modelRoundCount: legacyFacts.modelRoundCount,
  toolCount: legacyFacts.toolCount,
  pendingKind: "",
  elapsedMs: 4000,
  timeline: legacyFacts.timeline,
}, {referenceTime: "2030-01-01T00:00:04Z"});
process.stdout.write(JSON.stringify({equal, legacyFacts, summary: shadowApi.snapshotRunProjectionShadow(observer)}));
""")
        self.assertTrue(data["equal"])
        self.assertEqual(data["summary"]["eventsObserved"], 4)
        self.assertEqual(data["summary"]["snapshotsObserved"], 1)
        self.assertEqual(data["summary"]["comparisons"], 1)
        self.assertEqual(data["summary"]["mismatches"], 0)
        self.assertEqual(data["summary"]["diagnostics"], [])
        self.assertEqual(data["legacyFacts"]["modelRoundCount"], 1)
        self.assertEqual(data["legacyFacts"]["toolCount"], 1)
        self.assertEqual(
            data["legacyFacts"]["timeline"],
            [
                {"seq": 1, "type": "model_started", "category": "model", "status": "running", "refId": "round-1"},
                {"seq": 2, "type": "tool_started", "category": "tool", "status": "running", "refId": "tool-1"},
                {"seq": 3, "type": "tool_completed", "category": "tool", "status": "completed", "refId": "tool-1"},
                {"seq": 4, "type": "completed", "category": "terminal", "status": "completed", "refId": ""},
            ],
        )

    def test_authorization_resume_model_pending_does_not_start_the_next_round(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const reducer = window.Code.agent.runReducer;
const view = window.Code.ui.runViewModel;
const shadowApi = window.Code.agent.runProjectionShadow;
const initialSnapshot = {
  status: "model",
  eventCursor: 0,
  round: 0,
  createdAt: "2030-01-01T00:00:00Z",
  updatedAt: "2030-01-01T00:00:00Z",
  elapsedObservedAt: "2030-01-01T00:00:00Z",
  elapsedMs: 0,
};
const events = [
  {protocolVersion: 1, seq: 1, type: "model_started", data: {round: 1, runtimeRunId: "runtime-auth-1"}, createdAt: "2030-01-01T00:00:01Z"},
  {protocolVersion: 1, seq: 2, type: "model_completed", data: {round: 1, runtimeRunId: "runtime-auth-1", toolCalls: [{id: "tool-command-1", name: "run_command"}], outcome: "tool_calls"}, createdAt: "2030-01-01T00:00:02Z"},
  {protocolVersion: 1, seq: 3, type: "tool_started", data: {toolCallId: "tool-command-1", name: "run_command"}, createdAt: "2030-01-01T00:00:03Z"},
  {protocolVersion: 1, seq: 4, type: "authorization_required", data: {authorizationId: "auth-command-1", toolCallId: "tool-command-1", action: "run_command"}, createdAt: "2030-01-01T00:00:04Z"},
  {protocolVersion: 1, seq: 5, type: "authorization_submitted", data: {authorizationId: "auth-command-1", toolCallId: "tool-command-1", decision: "approved"}, createdAt: "2030-01-01T00:00:05Z"},
  {protocolVersion: 1, seq: 6, type: "waiting_credentials", data: {resumeStatus: "tools", reason: "authorization_submitted"}, createdAt: "2030-01-01T00:00:06Z"},
  {protocolVersion: 1, seq: 7, type: "resumed", data: {status: "tools"}, createdAt: "2030-01-01T00:00:07Z"},
  {protocolVersion: 1, seq: 8, type: "command_started", data: {toolCallId: "tool-command-1"}, createdAt: "2030-01-01T00:00:08Z"},
  {protocolVersion: 1, seq: 9, type: "tool_completed", data: {toolCallId: "tool-command-1", name: "run_command", outcome: "succeeded"}, createdAt: "2030-01-01T00:00:09Z"},
  {protocolVersion: 1, seq: 10, type: "model_pending", data: {round: 2}, createdAt: "2030-01-01T00:00:10Z"},
];
let state = reducer.createRunProjectionState(initialSnapshot);
const observer = shadowApi.createRunProjectionShadow({initialSnapshot});
const legacy = shadowApi.createLegacyProjectionObservation();
for (const event of events) {
  state = reducer.reduceRunProjectionEvent(state, event);
  shadowApi.observeProjectionEvent(observer, event);
  shadowApi.observeLegacyProjectionEvent(legacy, event);
}
const pendingModel = view.projectRunViewModel(state);
const pendingSnapshot = {
  status: "model",
  eventCursor: 10,
  round: 1,
  toolExecutions: [{toolCallId: "tool-command-1", name: "run_command", status: "completed", outcome: "succeeded"}],
  createdAt: "2030-01-01T00:00:00Z",
  updatedAt: "2030-01-01T00:00:10Z",
  elapsedObservedAt: "2030-01-01T00:00:10Z",
  elapsedMs: 10000,
};
shadowApi.observeProjectionSnapshot(observer, pendingSnapshot);
const pendingLegacy = shadowApi.snapshotLegacyProjectionObservation(legacy);
const pendingEqual = shadowApi.compareProjectionShadow(observer, {
  status: "model",
  terminalStatus: "",
  modelRoundCount: 1,
  toolCount: pendingLegacy.toolCount,
  pendingKind: "",
  elapsedMs: 10000,
  timeline: pendingLegacy.timeline,
}, {referenceTime: "2030-01-01T00:00:10Z"});
const startedEvent = {protocolVersion: 1, seq: 11, type: "model_started", data: {round: 2, runtimeRunId: "runtime-auth-2"}, createdAt: "2030-01-01T00:00:11Z"};
state = reducer.reduceRunProjectionEvent(state, startedEvent);
shadowApi.observeProjectionEvent(observer, startedEvent);
shadowApi.observeLegacyProjectionEvent(legacy, startedEvent);
const startedModel = view.projectRunViewModel(state);
const startedLegacy = shadowApi.snapshotLegacyProjectionObservation(legacy);
const startedEqual = shadowApi.compareProjectionShadow(observer, {
  status: "model",
  terminalStatus: "",
  modelRoundCount: 2,
  toolCount: startedLegacy.toolCount,
  pendingKind: "",
  elapsedMs: 11000,
  timeline: startedLegacy.timeline,
}, {referenceTime: "2030-01-01T00:00:11Z"});
process.stdout.write(JSON.stringify({
  pendingEqual,
  startedEqual,
  pendingModel,
  pendingLegacy,
  startedModel,
  summary: shadowApi.snapshotRunProjectionShadow(observer),
}));
""")
        self.assertTrue(data["pendingEqual"])
        self.assertTrue(data["startedEqual"])
        self.assertEqual(data["pendingModel"]["status"], "model")
        self.assertEqual(data["pendingModel"]["modelRoundCount"], 1)
        self.assertEqual(data["pendingLegacy"]["modelRoundCount"], 1)
        self.assertEqual(data["startedModel"]["modelRoundCount"], 2)
        self.assertEqual(data["summary"]["mismatches"], 0)
        self.assertEqual(data["summary"]["observerErrors"], 0)

    def test_shadow_diagnostics_are_bounded_sanitized_and_fail_open(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const shadowApi = window.Code.agent.runProjectionShadow;
const secret = "sk-secret-must-never-be-recorded";
const observer = shadowApi.createRunProjectionShadow({maxDiagnostics: 3});
const cappedObserver = shadowApi.createRunProjectionShadow({maxDiagnostics: 1000});
const observed = shadowApi.observeProjectionEvent(observer, {
  protocolVersion: 1,
  seq: 1,
  type: "tool_started",
  data: {toolCallId: "tool-1", name: "run_command", arguments: {apiKey: secret}},
  createdAt: "2030-01-01T00:00:01Z",
});
const invalidObserved = shadowApi.observeProjectionEvent(observer, {data: {result: secret}});
for (let index = 0; index < 5; index += 1) {
  shadowApi.compareProjectionShadow(observer, {
    status: "completed",
    terminalStatus: "completed",
    modelRoundCount: 99,
    toolCount: 99,
    pendingKind: "authorization",
    elapsedMs: 999999,
    timeline: [],
  }, {referenceTime: "2030-01-01T00:00:02Z"});
}
const summary = shadowApi.snapshotRunProjectionShadow(observer);
process.stdout.write(JSON.stringify({
  observed,
  invalidObserved,
  summary,
  secret,
  cappedLimit: cappedObserver.maxDiagnostics,
}));
""")
        self.assertTrue(data["observed"])
        self.assertFalse(data["invalidObserved"])
        self.assertEqual(data["cappedLimit"], 64)
        summary = data["summary"]
        self.assertEqual(summary["observerErrors"], 1)
        self.assertEqual(len(summary["diagnostics"]), 3)
        self.assertGreater(summary["diagnosticsDropped"], 0)
        self.assertGreater(summary["diagnosticCounts"]["projection_mismatch"], 3)
        self.assertEqual(
            set(summary["diagnostics"][0]),
            {"code", "field", "cursor", "status"},
        )
        serialized_summary = json.dumps(summary)
        self.assertNotIn(data["secret"], serialized_summary)
        self.assertNotIn("arguments", serialized_summary)
        self.assertNotIn("result", serialized_summary)

    def test_shadow_report_is_bounded_copied_and_whitelist_sanitized(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
require("./src/agent/run-projection-shadow.js");
const api = window.Code.agent.runProjectionShadow;
const secret = "sk-secret-must-never-be-exported";
const summaries = [
  {
    schemaVersion: 1,
    cursor: 3,
    status: "completed",
    eventsObserved: 3,
    snapshotsObserved: 1,
    comparisons: 4,
    mismatches: 0,
    observerErrors: 0,
    diagnosticCounts: {},
    diagnostics: [],
    diagnosticsDropped: 0,
    runKind: "foreground",
  },
  {
    schemaVersion: 1,
    cursor: 7,
    status: secret,
    eventsObserved: 7,
    snapshotsObserved: 2,
    comparisons: 9,
    mismatches: 2,
    observerErrors: 1,
    diagnosticCounts: {[secret]: 5, projection_mismatch: 2},
    diagnostics: [{
      code: secret,
      field: secret,
      cursor: 6,
      status: secret,
      arguments: secret,
    }],
    diagnosticsDropped: 4,
    runKind: secret,
    runId: secret,
    sessionId: secret,
  },
];
const enabled = api.createProjectionShadowReport(summaries, {enabled: true, maxSummaries: 1});
enabled.summaries[0].cursor = 999;
const copied = api.createProjectionShadowReport(summaries, {enabled: true, maxSummaries: 1});
const disabled = api.createProjectionShadowReport(summaries, {enabled: false});
process.stdout.write(JSON.stringify({
  maxSummaries: api.DEFAULT_MAX_SUMMARIES,
  enabled,
  copied,
  disabled,
  secret,
}));
""")
        self.assertEqual(data["maxSummaries"], 32)
        self.assertTrue(data["enabled"]["enabled"])
        self.assertEqual(data["enabled"]["summaryLimit"], 1)
        self.assertEqual(data["enabled"]["summaryCount"], 1)
        self.assertEqual(
            data["enabled"]["runKindCounts"],
            {"foreground": 1, "background": 0},
        )
        self.assertEqual(data["enabled"]["totals"]["eventsObserved"], 7)
        self.assertEqual(data["enabled"]["totals"]["mismatches"], 2)
        self.assertEqual(data["enabled"]["diagnosticCounts"]["projection_mismatch"], 2)
        self.assertEqual(
            data["enabled"]["diagnosticCounts"]["projection_shadow_error"],
            5,
        )
        self.assertEqual(data["copied"]["summaries"][0]["cursor"], 7)
        self.assertEqual(data["copied"]["summaries"][0]["status"], "")
        self.assertEqual(data["copied"]["summaries"][0]["runKind"], "foreground")
        self.assertFalse(data["disabled"]["enabled"])
        self.assertEqual(data["disabled"]["summaryCount"], 0)
        self.assertEqual(data["disabled"]["summaries"], [])
        serialized = json.dumps(data["enabled"])
        self.assertNotIn(data["secret"], serialized)
        self.assertNotIn("arguments", serialized)
        self.assertNotIn("runId", serialized)
        self.assertNotIn("sessionId", serialized)

    def test_all_h0_traces_replay_to_their_frozen_checkpoints(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
const suite = require("./tests/fixtures/harness/trace-suite.json");
const reducer = window.Code.agent.runReducer;
const view = window.Code.ui.runViewModel;
const results = [];
for (const fixture of suite.fixtures) {
  let state = reducer.createRunProjectionState(fixture.initialSnapshot);
  const checkpoints = new Map(fixture.checkpoints.map((item) => [item.afterSeq, item]));
  const observed = [];
  for (const rawEvent of fixture.events) {
    const event = {protocolVersion: 1, ...rawEvent};
    state = reducer.reduceRunProjectionInput(state, {kind: "event", event});
    const checkpoint = checkpoints.get(event.seq);
    if (checkpoint) {
      const model = view.projectRunViewModel(state);
      observed.push({
        afterSeq: event.seq,
        status: model.status,
        timeline: model.timeline.map((item) => item.type),
      });
    }
  }
  const model = view.projectRunViewModel(state);
  results.push({
    name: fixture.name,
    observed,
    expected: fixture.checkpoints,
    terminal: model.terminalStatus,
    expectedTerminal: fixture.expectedTerminal.status,
    toolCount: model.toolCount,
    diagnostics: model.diagnostics,
  });
}
process.stdout.write(JSON.stringify(results));
""")
        for fixture in data:
            with self.subTest(fixture=fixture["name"]):
                self.assertEqual(fixture["terminal"], fixture["expectedTerminal"])
                self.assertEqual(fixture["diagnostics"], [])
                self.assertEqual(len(fixture["observed"]), len(fixture["expected"]))
                for observed, expected in zip(fixture["observed"], fixture["expected"]):
                    self.assertEqual(observed["afterSeq"], expected["afterSeq"])
                    self.assertEqual(observed["status"], expected["expectedState"]["status"])
                    self.assertEqual(observed["timeline"], expected["expectedTimeline"])

        by_name = {item["name"]: item for item in data}
        self.assertEqual(by_name["single-read-tool"]["toolCount"], 1)
        self.assertEqual(by_name["multi-tool-stage"]["toolCount"], 2)

    def test_reducer_is_immutable_idempotent_and_checkpoint_serializable(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
const suite = require("./tests/fixtures/harness/trace-suite.json");
const fixture = suite.fixtures.find((item) => item.name === "refresh-during-tools");
const reducer = window.Code.agent.runReducer;
const view = window.Code.ui.runViewModel;
const events = fixture.events.map((event) => ({protocolVersion: 1, ...event}));
let original = reducer.createRunProjectionState(fixture.initialSnapshot);
const originalJson = JSON.stringify(original);
const first = reducer.reduceRunProjectionEvent(original, events[0]);
const duplicate = reducer.reduceRunProjectionEvent(first, events[0]);
let uninterrupted = first;
for (const event of events.slice(1)) uninterrupted = reducer.reduceRunProjectionEvent(uninterrupted, event);
let restored = JSON.parse(JSON.stringify(first));
for (const event of events.slice(1)) restored = reducer.reduceRunProjectionEvent(restored, event);
process.stdout.write(JSON.stringify({
  originalUnchanged: JSON.stringify(original) === originalJson,
  newState: first !== original,
  duplicateIdentity: duplicate === first,
  uninterrupted: view.createRunProjectionComparison(view.projectRunViewModel(uninterrupted)),
  restored: view.createRunProjectionComparison(view.projectRunViewModel(restored)),
}));
""")
        self.assertTrue(data["originalUnchanged"])
        self.assertTrue(data["newState"])
        self.assertTrue(data["duplicateIdentity"])
        self.assertEqual(data["uninterrupted"], data["restored"])

    def test_snapshot_pending_timing_unknown_events_and_terminal_guard_are_explicit(self):
        data = run_node(r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/run-reducer.js");
require("./src/ui/run-view-model.js");
const reducer = window.Code.agent.runReducer;
const view = window.Code.ui.runViewModel;
let state = reducer.createRunProjectionState({
  status: "waiting_authorization",
  round: 2,
  toolExecutions: [{toolCallId: "tool-1", name: "run_command", status: "running"}],
  pendingAuthorization: {authorizationId: "auth-1", toolCallId: "tool-1", action: "run_command"},
  createdAt: "2030-01-01T00:00:00Z",
  updatedAt: "2030-01-01T00:00:05Z",
  elapsedObservedAt: "2030-01-01T00:00:05Z",
  elapsedMs: 5000,
});
const waiting = view.projectRunViewModel(state, {referenceTime: "2030-01-01T00:00:08Z"});
state = reducer.applyRunProjectionSnapshot(state, {
  status: "tools",
  round: 2,
  updatedAt: "2030-01-01T00:00:06Z",
  elapsedObservedAt: "2030-01-01T00:00:06Z",
  elapsedMs: 6000,
});
state = reducer.reduceRunProjectionEvent(state, {
  protocolVersion: 1,
  seq: 3,
  type: "future_projection_event",
  data: {secretLookingBody: "must-not-enter-view-model"},
  createdAt: "2030-01-01T00:00:09Z",
});
state = reducer.reduceRunProjectionEvent(state, {
  protocolVersion: 1,
  seq: 4,
  type: "completed",
  data: {},
  createdAt: "2030-01-01T00:00:10Z",
});
const completed = view.projectRunViewModel(state);
state = reducer.reduceRunProjectionEvent(state, {
  protocolVersion: 1,
  seq: 5,
  type: "model_started",
  data: {round: 3, runtimeRunId: "late-runtime"},
  createdAt: "2030-01-01T00:00:11Z",
});
const guarded = view.projectRunViewModel(state);
process.stdout.write(JSON.stringify({waiting, completed, guarded}));
""")
        self.assertEqual(data["waiting"]["pendingKind"], "authorization")
        self.assertEqual(data["waiting"]["toolCount"], 1)
        self.assertEqual(data["waiting"]["modelRoundCount"], 2)
        self.assertEqual(data["waiting"]["elapsedMs"], 8000)
        self.assertEqual(data["completed"]["status"], "completed")
        self.assertEqual(data["completed"]["pendingKind"], "")
        self.assertEqual(data["completed"]["elapsedMs"], 10000)
        self.assertEqual(
            data["completed"]["diagnostics"],
            ["event_sequence_gap", "unknown_event_type"],
        )
        self.assertNotIn("must-not-enter-view-model", json.dumps(data))
        self.assertEqual(data["guarded"]["status"], "completed")
        self.assertIn("illegal_terminal_transition", data["guarded"]["diagnostics"])


if __name__ == "__main__":
    unittest.main()
