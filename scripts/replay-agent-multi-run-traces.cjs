#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const singleRunHarness = require("./replay-agent-traces.cjs");

const {
  ReplayAssertionError,
  canonicalHash,
  firstDifference,
} = singleRunHarness;

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_SUITE_PATH = path.join(
  ROOT,
  "tests",
  "fixtures",
  "harness",
  "multi-run-trace-suite.json",
);
const TERMINAL_EVENT_TYPES = new Set(["completed", "failed", "cancelled"]);

function loadProjectionContract() {
  if (!global.window) global.window = {};
  require(path.join(ROOT, "src", "core", "namespace.js"));
  require(path.join(ROOT, "src", "agent", "run-reducer.js"));
  require(path.join(ROOT, "src", "ui", "run-view-model.js"));
  return {
    reducer: global.window.Code.agent.runReducer,
    view: global.window.Code.ui.runViewModel,
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function failScenario(scenario, message, details = {}) {
  throw new ReplayAssertionError(message, {
    scenario: scenario?.name || "<unknown>",
    ...details,
  });
}

function displayValue(value) {
  if (value === undefined) return "<missing>";
  const serialized = JSON.stringify(value);
  if (!serialized || serialized.length <= 240) return value;
  return `${serialized.slice(0, 237)}...`;
}

function failDifference(scenario, message, difference, details = {}) {
  failScenario(scenario, message, {
    ...details,
    path: difference.path,
    expected: displayValue(difference.expected),
    actual: displayValue(difference.actual),
  });
}

function loadSuite(suitePath = DEFAULT_SUITE_PATH) {
  return JSON.parse(fs.readFileSync(path.resolve(suitePath), "utf8"));
}

function normalizeEvent(rawEvent) {
  return { protocolVersion: 1, ...rawEvent };
}

function findRunEvent(scenario, runKey, eventSeq) {
  return scenario.runs[runKey]?.events?.find((event) => event.seq === eventSeq) || null;
}

function validateIdentityGraph(scenario) {
  const identities = scenario.identities || {};
  const sessions = identities.sessions || {};
  const agentRuns = identities.agentRuns || {};
  const runtimes = identities.runtimes || {};
  const queueItems = identities.queueItems || {};
  const backgroundJobs = identities.backgroundJobs || {};
  const runs = scenario.runs || {};
  const runKeys = Object.keys(runs);

  if (runKeys.length < 2) {
    failScenario(scenario, "multi-run scenario requires at least two runs", {
      path: "$.runs",
      expected: "at least two runs",
      actual: runKeys,
    });
  }

  const seenAgentRunIds = new Map();
  for (const [runKey, run] of Object.entries(runs)) {
    if (!agentRuns[runKey]) {
      failScenario(scenario, "run identity reference is missing", {
        path: `$.runs.${runKey}.identityRef`,
        expected: runKey,
        actual: run.identityRef,
      });
    }
    if (run.identityRef !== runKey) {
      failScenario(scenario, "run identity reference differs from its map key", {
        path: `$.runs.${runKey}.identityRef`,
        expected: runKey,
        actual: run.identityRef,
      });
    }
    const identity = agentRuns[runKey];
    const session = sessions[identity.sessionRef];
    if (!session) {
      failScenario(scenario, "agent run references an unknown session", {
        path: `$.identities.agentRuns.${runKey}.sessionRef`,
        expected: Object.keys(sessions),
        actual: identity.sessionRef,
      });
    }
    if (identity.sessionId !== session.sessionId) {
      failScenario(scenario, "agent run session identity is inconsistent", {
        path: `$.identities.agentRuns.${runKey}.sessionId`,
        expected: session.sessionId,
        actual: identity.sessionId,
      });
    }
    if (identity.parentAgentRunId || identity.parentToolCallId) {
      failScenario(scenario, "H3-2B1 agent runs must remain independent root runs", {
        path: `$.identities.agentRuns.${runKey}.parentAgentRunId`,
        expected: "",
        actual: identity.parentAgentRunId,
      });
    }
    if (seenAgentRunIds.has(identity.agentRunId)) {
      failScenario(scenario, "agentRunId must be unique within a scenario", {
        path: `$.identities.agentRuns.${runKey}.agentRunId`,
        expected: `different from ${seenAgentRunIds.get(identity.agentRunId)}`,
        actual: identity.agentRunId,
      });
    }
    seenAgentRunIds.set(identity.agentRunId, runKey);

    const sequences = (run.events || []).map((event) => event.seq);
    const expectedSequences = Array.from({ length: sequences.length }, (_, index) => index + 1);
    const difference = firstDifference(sequences, expectedSequences, `$.runs.${runKey}.events`);
    if (difference) failDifference(scenario, "run event sequence is not contiguous", difference);
  }

  const seenRuntimeIds = new Map();
  for (const [runtimeKey, runtime] of Object.entries(runtimes)) {
    if (!runs[runtime.agentRunKey]) {
      failScenario(scenario, "runtime references an unknown agent run", {
        path: `$.identities.runtimes.${runtimeKey}.agentRunKey`,
        expected: runKeys,
        actual: runtime.agentRunKey,
      });
    }
    if (seenRuntimeIds.has(runtime.runtimeRunId)) {
      failScenario(scenario, "runtimeRunId must be unique within a scenario", {
        path: `$.identities.runtimes.${runtimeKey}.runtimeRunId`,
        expected: `different from ${seenRuntimeIds.get(runtime.runtimeRunId)}`,
        actual: runtime.runtimeRunId,
      });
    }
    seenRuntimeIds.set(runtime.runtimeRunId, runtimeKey);
    const matchingEvent = runs[runtime.agentRunKey].events.find((event) => (
      event.data?.runtimeRunId === runtime.runtimeRunId
      && Number(event.data?.round || 0) === Number(runtime.round)
    ));
    if (!matchingEvent) {
      failScenario(scenario, "runtime identity has no matching run event", {
        path: `$.identities.runtimes.${runtimeKey}.runtimeRunId`,
        expected: "a model event with the same runtimeRunId and round",
        actual: runtime.runtimeRunId,
      });
    }
  }

  for (const [runKey, run] of Object.entries(runs)) {
    for (let eventIndex = 0; eventIndex < run.events.length; eventIndex += 1) {
      const event = run.events[eventIndex];
      const runtimeRunId = String(event.data?.runtimeRunId || "");
      if (!runtimeRunId) continue;
      const runtimeKey = seenRuntimeIds.get(runtimeRunId);
      const runtime = runtimeKey ? runtimes[runtimeKey] : null;
      if (!runtime || runtime.agentRunKey !== runKey) {
        failScenario(scenario, "run event runtime identity is not closed", {
          path: `$.runs.${runKey}.events[${eventIndex}].data.runtimeRunId`,
          expected: `runtime owned by ${runKey}`,
          actual: runtimeRunId,
        });
      }
    }
  }

  for (const [queueKey, item] of Object.entries(queueItems)) {
    const session = sessions[item.sessionRef];
    const linkedRun = agentRuns[item.agentRunKey];
    if (!session || item.sessionId !== session.sessionId) {
      failScenario(scenario, "queue item session identity is inconsistent", {
        path: `$.identities.queueItems.${queueKey}.sessionId`,
        expected: session?.sessionId,
        actual: item.sessionId,
      });
    }
    if (!linkedRun) {
      failScenario(scenario, "queue item references an unknown agent run", {
        path: `$.identities.queueItems.${queueKey}.agentRunKey`,
        expected: runKeys,
        actual: item.agentRunKey,
      });
    }
    if (linkedRun.sessionId !== item.sessionId) {
      failScenario(scenario, "queue item and linked run belong to different sessions", {
        path: `$.identities.queueItems.${queueKey}.agentRunKey`,
        expected: `run in ${item.sessionId}`,
        actual: item.agentRunKey,
      });
    }
    if (linkedRun.clientRequestId !== item.clientRequestId) {
      failScenario(scenario, "queue item client request identity is inconsistent", {
        path: `$.identities.queueItems.${queueKey}.clientRequestId`,
        expected: linkedRun.clientRequestId,
        actual: item.clientRequestId,
      });
    }
  }

  for (const [jobKey, job] of Object.entries(backgroundJobs)) {
    const session = sessions[job.sessionRef];
    const linkedRun = agentRuns[job.agentRunKey];
    const parentRun = agentRuns[job.parentForegroundRunKey];
    if (!session || job.sessionId !== session.sessionId) {
      failScenario(scenario, "background job session identity is inconsistent", {
        path: `$.identities.backgroundJobs.${jobKey}.sessionId`,
        expected: session?.sessionId,
        actual: job.sessionId,
      });
    }
    if (!linkedRun || !parentRun) {
      failScenario(scenario, "background job references an unknown agent run", {
        path: `$.identities.backgroundJobs.${jobKey}.agentRunKey`,
        expected: runKeys,
        actual: job.agentRunKey,
      });
    }
    if (linkedRun.sessionId !== job.sessionId || parentRun.sessionId !== job.sessionId) {
      failScenario(scenario, "background job run relations cross session boundaries", {
        path: `$.identities.backgroundJobs.${jobKey}.sessionId`,
        expected: job.sessionId,
        actual: {
          linkedRun: linkedRun.sessionId,
          parentRun: parentRun.sessionId,
        },
      });
    }
    if (linkedRun.clientRequestId !== job.clientRequestId) {
      failScenario(scenario, "background job client request identity is inconsistent", {
        path: `$.identities.backgroundJobs.${jobKey}.clientRequestId`,
        expected: linkedRun.clientRequestId,
        actual: job.clientRequestId,
      });
    }
    if (linkedRun.parentAgentRunId || linkedRun.parentToolCallId) {
      failScenario(scenario, "explicit parallel run must not be modeled as a child AgentRun", {
        path: `$.identities.agentRuns.${job.agentRunKey}.parentAgentRunId`,
        expected: "",
        actual: linkedRun.parentAgentRunId,
      });
    }
  }
}

function deriveOrders(scenario, throughStep = scenario.schedule.length) {
  const creation = [];
  const terminal = [];
  const factMarkers = [];
  for (const entry of scenario.schedule) {
    if (entry.step > throughStep) break;
    if (entry.kind === "fact-marker") {
      factMarkers.push(`${entry.fact}:${entry.ref}`);
      continue;
    }
    const event = findRunEvent(scenario, entry.runKey, entry.eventSeq);
    if (event?.type === "created") creation.push(entry.runKey);
    if (TERMINAL_EVENT_TYPES.has(event?.type)) terminal.push(entry.runKey);
  }
  return { creation, terminal, factMarkers };
}

function validateSchedule(scenario) {
  const runKeys = Object.keys(scenario.runs);
  const expectedLocalSeq = Object.fromEntries(runKeys.map((runKey) => [runKey, 1]));
  const queueItems = scenario.identities.queueItems;
  const backgroundJobs = scenario.identities.backgroundJobs;

  for (let index = 0; index < scenario.schedule.length; index += 1) {
    const entry = scenario.schedule[index];
    const expectedStep = index + 1;
    if (entry.step !== expectedStep) {
      failScenario(scenario, "schedule steps must be contiguous", {
        path: `$.schedule[${index}].step`,
        expected: expectedStep,
        actual: entry.step,
      });
    }
    if (entry.kind === "fact-marker") {
      const refs = entry.fact === "background-dispatched" ? backgroundJobs : queueItems;
      if (!refs[entry.ref]) {
        failScenario(scenario, "fact marker references an unknown identity", {
          path: `$.schedule[${index}].ref`,
          expected: Object.keys(refs),
          actual: entry.ref,
        });
      }
      continue;
    }
    const run = scenario.runs[entry.runKey];
    if (!run) {
      failScenario(scenario, "schedule references an unknown run", {
        path: `$.schedule[${index}].runKey`,
        expected: runKeys,
        actual: entry.runKey,
      });
    }
    const identity = scenario.identities.agentRuns[entry.runKey];
    if (entry.agentRunId !== identity.agentRunId) {
      failScenario(scenario, "schedule event was delivered to the wrong run", {
        path: `$.schedule[${index}].agentRunId`,
        expected: identity.agentRunId,
        actual: entry.agentRunId,
      });
    }
    const event = findRunEvent(scenario, entry.runKey, entry.eventSeq);
    if (!event) {
      failScenario(scenario, "schedule references an unavailable run event", {
        path: `$.schedule[${index}].eventSeq`,
        expected: run.events.map((candidate) => candidate.seq),
        actual: entry.eventSeq,
      });
    }
    if (entry.eventSeq !== expectedLocalSeq[entry.runKey]) {
      failScenario(scenario, "schedule duplicates or reorders a run event", {
        path: `$.schedule[${index}].eventSeq`,
        expected: expectedLocalSeq[entry.runKey],
        actual: entry.eventSeq,
      });
    }
    expectedLocalSeq[entry.runKey] += 1;
  }

  for (const runKey of runKeys) {
    const expectedAfterFinal = scenario.runs[runKey].events.length + 1;
    if (expectedLocalSeq[runKey] !== expectedAfterFinal) {
      const missingSeq = expectedLocalSeq[runKey];
      failScenario(scenario, "schedule omits a canonical run event", {
        path: `$.runs.${runKey}.events[${missingSeq - 1}].seq`,
        expected: `scheduled event ${runKey}:${missingSeq}`,
        actual: "<missing>",
      });
    }
  }

  const actualOrders = deriveOrders(scenario);
  const difference = firstDifference(actualOrders, scenario.expectedOrders, "$.orders");
  if (difference) failDifference(scenario, "fixed schedule order differs", difference);
}

function validateCheckpoints(scenario) {
  const runKeys = Object.keys(scenario.runs).sort();
  const seenSteps = new Set();
  for (let index = 0; index < scenario.checkpoints.length; index += 1) {
    const checkpoint = scenario.checkpoints[index];
    if (
      checkpoint.afterStep < 1
      || checkpoint.afterStep > scenario.schedule.length
      || seenSteps.has(checkpoint.afterStep)
    ) {
      failScenario(scenario, "checkpoint references an invalid or duplicate schedule step", {
        path: `$.checkpoints[${index}].afterStep`,
        expected: `unique step between 1 and ${scenario.schedule.length}`,
        actual: checkpoint.afterStep,
      });
    }
    seenSteps.add(checkpoint.afterStep);
    for (const field of ["expectedRunCursors", "expectedRunViews"]) {
      const actualKeys = Object.keys(checkpoint[field] || {}).sort();
      const difference = firstDifference(
        actualKeys,
        runKeys,
        `$.checkpoints[${index}].${field}`,
      );
      if (difference) failDifference(scenario, "checkpoint run set differs", difference);
    }
  }
}

function validateScenario(scenario) {
  if (!scenario || typeof scenario !== "object" || !scenario.name) {
    throw new ReplayAssertionError("multi-run scenario requires a name", {
      scenario: "<unknown>",
      path: "$.name",
    });
  }
  validateIdentityGraph(scenario);
  validateSchedule(scenario);
  validateCheckpoints(scenario);
}

function createCompositeState(scenario, contract) {
  const runStates = {};
  const runCursors = {};
  for (const [runKey, run] of Object.entries(scenario.runs)) {
    const state = contract.reducer.createRunProjectionState(run.initialSnapshot);
    runStates[runKey] = state;
    runCursors[runKey] = Number(state.cursor || 0);
  }
  return {
    scheduleCursor: 0,
    identities: deepFreeze(clone(scenario.identities)),
    runStates,
    runCursors,
  };
}

function runStatesHash(state) {
  return canonicalHash({ runStates: state.runStates, runCursors: state.runCursors });
}

function applyScheduleEntry(scenario, state, entry, contract, {
  duplicateDelivery = false,
  collectFactMarkerChecks = null,
} = {}) {
  const identityHashBefore = canonicalHash(state.identities);
  if (entry.kind === "fact-marker") {
    const runHashBefore = runStatesHash(state);
    state.scheduleCursor = entry.step;
    const runHashAfter = runStatesHash(state);
    if (runHashAfter !== runHashBefore) {
      failScenario(scenario, "fact marker changed run projection state", {
        path: `$.schedule[${entry.step - 1}].fact`,
        expected: runHashBefore,
        actual: runHashAfter,
      });
    }
    collectFactMarkerChecks?.push({
      step: entry.step,
      fact: `${entry.fact}:${entry.ref}`,
      runStateHash: runHashAfter,
    });
  } else {
    const event = normalizeEvent(findRunEvent(scenario, entry.runKey, entry.eventSeq));
    state.runStates[entry.runKey] = contract.reducer.reduceRunProjectionInput(
      state.runStates[entry.runKey],
      { kind: "event", event },
    );
    if (duplicateDelivery) {
      state.runStates[entry.runKey] = contract.reducer.reduceRunProjectionInput(
        state.runStates[entry.runKey],
        { kind: "event", event },
      );
    }
    state.runCursors[entry.runKey] = Number(state.runStates[entry.runKey].cursor || 0);
    state.scheduleCursor = entry.step;
  }
  const identityHashAfter = canonicalHash(state.identities);
  if (identityHashAfter !== identityHashBefore) {
    failScenario(scenario, "schedule processing mutated the identity graph", {
      path: "$.identities",
      expected: identityHashBefore,
      actual: identityHashAfter,
    });
  }
  return state;
}

function replayThroughStep(scenario, throughStep, contract, options = {}) {
  const state = createCompositeState(scenario, contract);
  const factMarkerChecks = [];
  for (const entry of scenario.schedule) {
    if (entry.step > throughStep) break;
    applyScheduleEntry(scenario, state, entry, contract, {
      duplicateDelivery: options.duplicateDelivery === true,
      collectFactMarkerChecks: factMarkerChecks,
    });
  }
  return { state, factMarkerChecks };
}

function continueFromStep(scenario, state, afterStep, contract) {
  for (const entry of scenario.schedule) {
    if (entry.step <= afterStep) continue;
    applyScheduleEntry(scenario, state, entry, contract);
  }
  return state;
}

function referenceTimeForCursor(scenario, scheduleCursor) {
  if (!scheduleCursor) return scenario.clock?.origin || null;
  const entry = scenario.schedule[scheduleCursor - 1];
  if (entry.kind === "fact-marker") return entry.observedAt;
  return findRunEvent(scenario, entry.runKey, entry.eventSeq)?.createdAt || null;
}

function projectCompositeState(scenario, state, contract) {
  const referenceTime = referenceTimeForCursor(scenario, state.scheduleCursor);
  const runs = {};
  for (const runKey of Object.keys(scenario.runs).sort()) {
    runs[runKey] = contract.view.projectRunViewModel(state.runStates[runKey], {
      referenceTime,
    });
  }
  return {
    scheduleCursor: Number(state.scheduleCursor || 0),
    identities: state.identities,
    runCursors: { ...state.runCursors },
    runs,
    orders: deriveOrders(scenario, state.scheduleCursor),
  };
}

function checkpointRunView(model) {
  return {
    cursor: model.cursor,
    status: model.status,
    terminalStatus: model.terminalStatus,
    modelRoundCount: model.modelRoundCount,
    timeline: model.timeline.map((item) => item.type),
  };
}

function hashRunViews(projection) {
  return Object.fromEntries(
    Object.entries(projection.runs).map(([runKey, view]) => [runKey, canonicalHash(view)]),
  );
}

function assertCheckpoint(scenario, checkpoint, checkpointIndex, projection) {
  const cursorDifference = firstDifference(
    projection.runCursors,
    checkpoint.expectedRunCursors,
    `$.checkpoints[${checkpointIndex}].expectedRunCursors`,
  );
  if (cursorDifference) {
    failDifference(scenario, "checkpoint run cursors differ", cursorDifference, {
      scheduleStep: checkpoint.afterStep,
    });
  }
  for (const [runKey, expectedView] of Object.entries(checkpoint.expectedRunViews)) {
    const actualView = checkpointRunView(projection.runs[runKey]);
    const difference = firstDifference(
      actualView,
      expectedView,
      `$.checkpoints[${checkpointIndex}].expectedRunViews.${runKey}`,
    );
    if (difference) {
      failDifference(scenario, "checkpoint run View Model differs", difference, {
        scheduleStep: checkpoint.afterStep,
      });
    }
  }
}

function expectedRunCursorsForSchedulePrefix(scenario, scheduleCursor) {
  const expected = Object.fromEntries(
    Object.entries(scenario.runs).map(([runKey, run]) => [
      runKey,
      Number(run.initialSnapshot?.eventCursor || 0),
    ]),
  );
  for (const entry of scenario.schedule) {
    if (entry.step > scheduleCursor) break;
    if (entry.kind === "run-event") expected[entry.runKey] = entry.eventSeq;
  }
  return expected;
}

function assertExactRunKeys(scenario, value, pathPrefix) {
  const expectedKeys = Object.keys(scenario.runs).sort();
  const actualKeys = value && typeof value === "object"
    ? Object.keys(value).sort()
    : [];
  const difference = firstDifference(actualKeys, expectedKeys, pathPrefix);
  if (difference) {
    failDifference(scenario, "restored run key set differs", difference);
  }
}

function restoreCompositeState(scenario, serializedState, pathPrefix = "$") {
  const state = clone(serializedState);
  const identityDifference = firstDifference(
    state.identities,
    scenario.identities,
    `${pathPrefix}.identities`,
  );
  if (identityDifference) {
    failDifference(scenario, "restored identity graph differs", identityDifference);
  }
  state.identities = deepFreeze(state.identities);
  if (
    !Number.isInteger(state.scheduleCursor)
    || state.scheduleCursor < 0
    || state.scheduleCursor > scenario.schedule.length
  ) {
    failScenario(scenario, "restored schedule cursor is invalid", {
      path: `${pathPrefix}.scheduleCursor`,
      expected: `integer between 0 and ${scenario.schedule.length}`,
      actual: state.scheduleCursor,
    });
  }

  assertExactRunKeys(scenario, state.runStates, `${pathPrefix}.runStates`);
  assertExactRunKeys(scenario, state.runCursors, `${pathPrefix}.runCursors`);
  const expectedCursors = expectedRunCursorsForSchedulePrefix(
    scenario,
    state.scheduleCursor,
  );
  for (const runKey of Object.keys(scenario.runs)) {
    const expectedCursor = expectedCursors[runKey];
    const savedCursor = state.runCursors[runKey];
    if (savedCursor !== expectedCursor) {
      failScenario(scenario, "restored run cursor differs from the schedule prefix", {
        path: `${pathPrefix}.runCursors.${runKey}`,
        expected: expectedCursor,
        actual: savedCursor,
      });
    }
    const stateCursor = state.runStates[runKey].cursor;
    if (stateCursor !== expectedCursor) {
      failScenario(scenario, "restored run state differs from the schedule prefix", {
        path: `${pathPrefix}.runStates.${runKey}.cursor`,
        expected: expectedCursor,
        actual: stateCursor,
      });
    }
  }
  return state;
}

function replayScenario(scenario, options = {}) {
  validateScenario(scenario);
  const contract = options.contract || loadProjectionContract();
  const fullStep = scenario.schedule.length;
  const uninterrupted = replayThroughStep(scenario, fullStep, contract);
  const finalProjection = projectCompositeState(scenario, uninterrupted.state, contract);
  const stateHash = canonicalHash(finalProjection);
  if (options.verifyExpectedHash !== false && stateHash !== scenario.expectedCompositeHash) {
    failScenario(scenario, "composite state hash differs", {
      path: "$.expectedCompositeHash",
      expected: scenario.expectedCompositeHash,
      actual: stateHash,
    });
  }

  const duplicated = replayThroughStep(scenario, fullStep, contract, {
    duplicateDelivery: true,
  });
  const duplicateProjection = projectCompositeState(scenario, duplicated.state, contract);
  const duplicateDifference = firstDifference(duplicateProjection, finalProjection, "$.duplicate");
  if (duplicateDifference) {
    failDifference(scenario, "duplicate event delivery changed the composite projection", duplicateDifference);
  }

  const checkpoints = [];
  for (let checkpointIndex = 0; checkpointIndex < scenario.checkpoints.length; checkpointIndex += 1) {
    const checkpoint = scenario.checkpoints[checkpointIndex];
    const prefix = replayThroughStep(scenario, checkpoint.afterStep, contract);
    const checkpointProjection = projectCompositeState(scenario, prefix.state, contract);
    assertCheckpoint(scenario, checkpoint, checkpointIndex, checkpointProjection);

    const serializedState = clone(prefix.state);
    options.resumeStateMutator?.({
      checkpointIndex,
      checkpoint,
      state: serializedState,
    });
    const resumePath = `$.checkpoints[${checkpointIndex}].resume`;
    const restored = restoreCompositeState(scenario, serializedState, resumePath);
    continueFromStep(scenario, restored, restored.scheduleCursor, contract);
    const resumedProjection = projectCompositeState(scenario, restored, contract);
    const resumedDifference = firstDifference(
      resumedProjection,
      finalProjection,
      `$.checkpoints[${checkpointIndex}].resume`,
    );
    if (resumedDifference) {
      failDifference(scenario, "composite checkpoint recovery differs", resumedDifference, {
        scheduleStep: checkpoint.afterStep,
      });
    }
    checkpoints.push({
      afterStep: checkpoint.afterStep,
      runCursors: { ...prefix.state.runCursors },
      checkpointStateHash: canonicalHash(checkpointProjection),
      checkpointRunStateHashes: hashRunViews(checkpointProjection),
      resumedStateHash: canonicalHash(resumedProjection),
      resumedRunStateHashes: hashRunViews(resumedProjection),
    });
  }

  const runStateHashes = hashRunViews(finalProjection);
  const duplicateRunStateHashes = hashRunViews(duplicateProjection);
  return {
    name: scenario.name,
    runCount: Object.keys(scenario.runs).length,
    eventCount: Object.values(scenario.runs)
      .reduce((total, run) => total + run.events.length, 0),
    scheduleStepCount: scenario.schedule.length,
    factMarkerCount: scenario.schedule.filter((entry) => entry.kind === "fact-marker").length,
    checkpointCount: scenario.checkpoints.length,
    checkpointRecoveryCount: checkpoints.length,
    stateHash,
    duplicateStateHash: canonicalHash(duplicateProjection),
    runStateHashes,
    duplicateRunStateHashes,
    orders: finalProjection.orders,
    factMarkerChecks: uninterrupted.factMarkerChecks,
    checkpoints,
  };
}

function selectScenarios(scenarios, names = []) {
  if (!names.length) return scenarios;
  const selected = new Set(names);
  return scenarios.filter((scenario) => selected.has(scenario.name));
}

function runReplaySuite(suite, options = {}) {
  if (
    !suite
    || suite.multiRunFixtureVersion !== 1
    || suite.source !== "synthetic"
    || !Array.isArray(suite.scenarios)
  ) {
    throw new ReplayAssertionError("multi-run suite must use fixture version 1", {
      scenario: "<suite>",
      path: "$.multiRunFixtureVersion",
      expected: 1,
      actual: suite?.multiRunFixtureVersion,
    });
  }
  const selected = selectScenarios(suite.scenarios, options.names || []);
  if (!selected.length) {
    throw new ReplayAssertionError("scenario selection matched no multi-run traces", {
      scenario: "<suite>",
      path: "$.scenarios",
      expected: "at least one selected scenario",
      actual: options.names || [],
    });
  }
  const contract = loadProjectionContract();
  const results = selected.map((scenario) => replayScenario(scenario, {
    contract,
    verifyExpectedHash: options.verifyExpectedHash,
  }));
  return {
    replayVersion: 1,
    multiRunFixtureVersion: suite.multiRunFixtureVersion,
    scenarioCount: results.length,
    runCount: results.reduce((total, result) => total + result.runCount, 0),
    eventCount: results.reduce((total, result) => total + result.eventCount, 0),
    scheduleStepCount: results.reduce((total, result) => total + result.scheduleStepCount, 0),
    factMarkerCount: results.reduce((total, result) => total + result.factMarkerCount, 0),
    checkpointCount: results.reduce((total, result) => total + result.checkpointCount, 0),
    checkpointRecoveryCount: results.reduce(
      (total, result) => total + result.checkpointRecoveryCount,
      0,
    ),
    fixtureSuiteHash: canonicalHash(suite),
    suiteReplayHash: canonicalHash(
      results.map((result) => ({ name: result.name, stateHash: result.stateHash })),
    ),
    results,
  };
}

function parseArguments(argv) {
  const options = { names: [], json: false, list: false, suitePath: DEFAULT_SUITE_PATH };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--json") options.json = true;
    else if (argument === "--list") options.list = true;
    else if (argument === "--scenario") {
      index += 1;
      if (!argv[index]) throw new Error("--scenario requires a value");
      options.names.push(argv[index]);
    } else if (argument === "--suite") {
      index += 1;
      if (!argv[index]) throw new Error("--suite requires a value");
      options.suitePath = path.resolve(argv[index]);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }
  return options;
}

function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArguments(argv);
    const suite = loadSuite(options.suitePath);
    const selected = selectScenarios(suite.scenarios || [], options.names);
    if (options.list) {
      process.stdout.write(`${selected.map((scenario) => scenario.name).join("\n")}\n`);
      return 0;
    }
    const summary = runReplaySuite(suite, options);
    if (options.json) process.stdout.write(`${JSON.stringify(summary)}\n`);
    else {
      process.stdout.write(
        `Replayed ${summary.scenarioCount} multi-run scenario(s), `
        + `${summary.eventCount} events in ${summary.scheduleStepCount} steps, `
        + `${summary.checkpointCount} checkpoints; hash ${summary.suiteReplayHash}\n`,
      );
    }
    return 0;
  } catch (error) {
    const payload = error instanceof ReplayAssertionError
      ? error.toJSON()
      : { name: error.name || "Error", message: error.message || String(error) };
    process.stderr.write(`${JSON.stringify(payload)}\n`);
    return 1;
  }
}

module.exports = {
  DEFAULT_SUITE_PATH,
  deriveOrders,
  loadSuite,
  replayScenario,
  replayThroughStep,
  runReplaySuite,
  selectScenarios,
  validateScenario,
};

if (require.main === module) process.exitCode = main();
