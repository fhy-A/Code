#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_SUITE_PATH = path.join(
  ROOT,
  "tests",
  "fixtures",
  "harness",
  "trace-suite.json",
);

class ReplayAssertionError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "ReplayAssertionError";
    this.details = details;
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      ...this.details,
    };
  }
}

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

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .filter((key) => value[key] !== undefined)
        .map((key) => [key, canonicalValue(value[key])]),
    );
  }
  return value;
}

function canonicalHash(value) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(canonicalValue(value)))
    .digest("hex");
}

function displayValue(value) {
  if (value === undefined) return "<missing>";
  const serialized = JSON.stringify(value);
  if (serialized.length <= 240) return value;
  return `${serialized.slice(0, 237)}...`;
}

function firstDifference(actual, expected, currentPath = "$") {
  if (Object.is(actual, expected)) return null;
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      return { path: currentPath, expected, actual };
    }
    const length = Math.max(actual.length, expected.length);
    for (let index = 0; index < length; index += 1) {
      if (index >= expected.length || index >= actual.length) {
        return {
          path: `${currentPath}[${index}]`,
          expected: expected[index],
          actual: actual[index],
        };
      }
      const difference = firstDifference(
        actual[index],
        expected[index],
        `${currentPath}[${index}]`,
      );
      if (difference) return difference;
    }
    return null;
  }
  if (expected && typeof expected === "object") {
    if (!actual || typeof actual !== "object" || Array.isArray(actual)) {
      return { path: currentPath, expected, actual };
    }
    for (const key of Object.keys(expected).sort()) {
      const difference = firstDifference(
        actual[key],
        expected[key],
        `${currentPath}.${key}`,
      );
      if (difference) return difference;
    }
    return null;
  }
  return { path: currentPath, expected, actual };
}

function failFixture(fixture, message, details = {}) {
  throw new ReplayAssertionError(`${fixture.name}: ${message}`, {
    fixture: fixture.name,
    ...details,
    expected: displayValue(details.expected),
    actual: displayValue(details.actual),
  });
}

function normalizeEvent(rawEvent) {
  return { protocolVersion: 1, ...rawEvent };
}

function projectState(state, referenceTime, contract) {
  return contract.view.projectRunViewModel(
    state,
    referenceTime ? { referenceTime } : {},
  );
}

function replayEvents(fixture, events, contract, { stopAfterSeq = null } = {}) {
  let state = contract.reducer.createRunProjectionState(fixture.initialSnapshot);
  const statesByCursor = new Map([[Number(state.cursor || 0), state]]);
  const viewsByCursor = new Map();
  let previousSeq = Number(state.cursor || 0);
  const expectedDiagnostics = Array.isArray(fixture.expectedDiagnostics)
    ? fixture.expectedDiagnostics
    : [];

  for (let index = 0; index < events.length; index += 1) {
    const rawEvent = events[index];
    const expectedSeq = previousSeq + 1;
    if (!rawEvent || rawEvent.seq !== expectedSeq) {
      failFixture(fixture, "event sequence is missing or out of order", {
        eventSeq: rawEvent?.seq ?? null,
        path: `$.events[${index}].seq`,
        expected: expectedSeq,
        actual: rawEvent?.seq,
      });
    }
    const event = normalizeEvent(rawEvent);
    state = contract.reducer.reduceRunProjectionInput(state, { kind: "event", event });
    const model = projectState(state, event.createdAt, contract);
    if (!contract.reducer.RUN_STATUSES.includes(model.status)) {
      failFixture(fixture, "projection produced an invalid status", {
        eventSeq: event.seq,
        path: "$.status",
        expected: contract.reducer.RUN_STATUSES,
        actual: model.status,
      });
    }
    const unexpectedDiagnostic = model.diagnostics.find(
      (diagnostic) => !expectedDiagnostics.includes(diagnostic),
    );
    if (unexpectedDiagnostic) {
      failFixture(fixture, "projection produced an unexpected diagnostic", {
        eventSeq: event.seq,
        path: `$.diagnostics[${model.diagnostics.indexOf(unexpectedDiagnostic)}]`,
        expected: expectedDiagnostics,
        actual: model.diagnostics,
      });
    }
    previousSeq = event.seq;
    statesByCursor.set(event.seq, state);
    viewsByCursor.set(event.seq, model);
    if (stopAfterSeq === event.seq) break;
  }
  return { state, statesByCursor, viewsByCursor };
}

function assertCheckpoint(fixture, checkpoint, model) {
  const stateDifference = firstDifference(
    model,
    checkpoint.expectedState || {},
    "$",
  );
  if (stateDifference) {
    failFixture(fixture, "checkpoint state differs", {
      eventSeq: checkpoint.afterSeq,
      path: stateDifference.path,
      expected: stateDifference.expected,
      actual: stateDifference.actual,
    });
  }
  const actualTimeline = model.timeline.map((item) => item.type);
  const timelineDifference = firstDifference(
    actualTimeline,
    checkpoint.expectedTimeline || [],
    "$.timeline",
  );
  if (timelineDifference) {
    failFixture(fixture, "checkpoint timeline differs", {
      eventSeq: checkpoint.afterSeq,
      path: timelineDifference.path,
      expected: timelineDifference.expected,
      actual: timelineDifference.actual,
    });
  }
}

function resumeFromCursor(fixture, cursor, events, contract) {
  const prefix = events.filter((event) => event.seq <= cursor);
  const suffix = events.filter((event) => event.seq > cursor);
  const prefixReplay = replayEvents(fixture, prefix, contract);
  let state = JSON.parse(JSON.stringify(prefixReplay.state));
  for (const rawEvent of suffix) {
    state = contract.reducer.reduceRunProjectionInput(state, {
      kind: "event",
      event: normalizeEvent(rawEvent),
    });
  }
  return projectState(state, events.at(-1)?.createdAt, contract);
}

function replayWithDuplicateDelivery(fixture, events, contract) {
  let state = contract.reducer.createRunProjectionState(fixture.initialSnapshot);
  for (const rawEvent of events) {
    const event = normalizeEvent(rawEvent);
    state = contract.reducer.reduceRunProjectionInput(state, { kind: "event", event });
    state = contract.reducer.reduceRunProjectionInput(state, { kind: "event", event });
  }
  return projectState(state, events.at(-1)?.createdAt, contract);
}

function replayFixture(fixture, { contract = loadProjectionContract() } = {}) {
  if (!fixture || typeof fixture !== "object" || !fixture.name) {
    throw new ReplayAssertionError("trace fixture requires a name", {
      fixture: "<unknown>",
      path: "$.name",
    });
  }
  const events = Array.isArray(fixture.events) ? fixture.events : [];
  if (!events.length) {
    failFixture(fixture, "events must not be empty", {
      path: "$.events",
      expected: "non-empty array",
      actual: fixture.events,
    });
  }

  const uninterrupted = replayEvents(fixture, events, contract);
  const finalModel = projectState(
    uninterrupted.state,
    events.at(-1)?.createdAt,
    contract,
  );
  const checkpointResults = [];
  for (const checkpoint of fixture.checkpoints || []) {
    const model = uninterrupted.viewsByCursor.get(checkpoint.afterSeq);
    if (!model) {
      failFixture(fixture, "checkpoint references an unavailable event", {
        eventSeq: checkpoint.afterSeq,
        path: "$.checkpoints.afterSeq",
        expected: "an event cursor produced by this trace",
        actual: checkpoint.afterSeq,
      });
    }
    assertCheckpoint(fixture, checkpoint, model);
    const resumedModel = resumeFromCursor(
      fixture,
      Number(checkpoint.afterSeq || 0),
      events,
      contract,
    );
    const resumedDifference = firstDifference(resumedModel, finalModel);
    if (resumedDifference) {
      failFixture(fixture, "checkpoint recovery changed the final projection", {
        eventSeq: checkpoint.afterSeq,
        path: resumedDifference.path,
        expected: resumedDifference.expected,
        actual: resumedDifference.actual,
      });
    }
    checkpointResults.push({
      afterSeq: checkpoint.afterSeq,
      stateHash: canonicalHash(model),
      resumedStateHash: canonicalHash(resumedModel),
    });
  }

  const expectedTerminal = fixture.expectedTerminal || {};
  if (finalModel.terminalStatus !== expectedTerminal.status) {
    failFixture(fixture, "terminal status differs", {
      eventSeq: events.at(-1)?.seq,
      path: "$.terminalStatus",
      expected: expectedTerminal.status,
      actual: finalModel.terminalStatus,
    });
  }
  if (events.at(-1)?.type !== expectedTerminal.eventType) {
    failFixture(fixture, "terminal event differs", {
      eventSeq: events.at(-1)?.seq,
      path: "$.timeline[-1].type",
      expected: expectedTerminal.eventType,
      actual: events.at(-1)?.type,
    });
  }

  const stateHash = canonicalHash(finalModel);
  const duplicateModel = replayWithDuplicateDelivery(fixture, events, contract);
  const duplicateDifference = firstDifference(duplicateModel, finalModel);
  if (duplicateDifference) {
    failFixture(fixture, "duplicate delivery changed the final projection", {
      eventSeq: events.at(-1)?.seq,
      path: duplicateDifference.path,
      expected: duplicateDifference.expected,
      actual: duplicateDifference.actual,
    });
  }

  const recoveryResults = [];
  for (const recovery of fixture.recoveryPoints || []) {
    const recoveredModel = resumeFromCursor(
      fixture,
      Number(recovery.cursor || 0),
      events,
      contract,
    );
    const recoveryDifference = firstDifference(recoveredModel, finalModel);
    if (recoveryDifference) {
      failFixture(fixture, `${recovery.kind} recovery changed the final projection`, {
        eventSeq: recovery.afterSeq,
        path: recoveryDifference.path,
        expected: recoveryDifference.expected,
        actual: recoveryDifference.actual,
      });
    }
    recoveryResults.push({
      kind: recovery.kind,
      afterSeq: recovery.afterSeq,
      cursor: recovery.cursor,
      stateHash: canonicalHash(recoveredModel),
    });
  }

  return {
    name: fixture.name,
    tags: [...(fixture.tags || [])],
    eventCount: events.length,
    checkpointCount: checkpointResults.length,
    recoveryCount: recoveryResults.length,
    terminalStatus: finalModel.terminalStatus,
    stateHash,
    duplicateStateHash: canonicalHash(duplicateModel),
    checkpoints: checkpointResults,
    recoveries: recoveryResults,
  };
}

function selectFixtures(fixtures, { names = [], tags = [] } = {}) {
  const nameSet = new Set(names);
  const tagSet = new Set(tags);
  return fixtures.filter((fixture) => {
    const matchesName = !nameSet.size || nameSet.has(fixture.name);
    const fixtureTags = new Set(fixture.tags || []);
    const matchesTag = !tagSet.size || [...tagSet].every((tag) => fixtureTags.has(tag));
    return matchesName && matchesTag;
  });
}

function runReplaySuite(suite, options = {}) {
  if (!suite || suite.fixtureVersion !== 1 || !Array.isArray(suite.fixtures)) {
    throw new ReplayAssertionError("trace suite must use fixtureVersion 1", {
      fixture: "<suite>",
      path: "$.fixtureVersion",
      expected: 1,
      actual: suite?.fixtureVersion,
    });
  }
  const selected = selectFixtures(suite.fixtures, options);
  if (!selected.length) {
    throw new ReplayAssertionError("fixture selection matched no traces", {
      fixture: "<suite>",
      path: "$.fixtures",
      expected: "at least one selected fixture",
      actual: { names: options.names || [], tags: options.tags || [] },
    });
  }
  const contract = loadProjectionContract();
  const results = selected.map((fixture) => replayFixture(fixture, { contract }));
  return {
    replayVersion: 1,
    fixtureVersion: suite.fixtureVersion,
    fixtureCount: results.length,
    eventCount: results.reduce((total, result) => total + result.eventCount, 0),
    checkpointCount: results.reduce((total, result) => total + result.checkpointCount, 0),
    checkpointRecoveryCount: results.reduce(
      (total, result) => total + result.checkpointCount,
      0,
    ),
    recoveryCount: results.reduce((total, result) => total + result.recoveryCount, 0),
    suiteReplayHash: canonicalHash(
      results.map((result) => ({ name: result.name, stateHash: result.stateHash })),
    ),
    results,
  };
}

function loadSuite(suitePath = DEFAULT_SUITE_PATH) {
  return JSON.parse(fs.readFileSync(path.resolve(suitePath), "utf8"));
}

function parseArguments(argv) {
  const options = { names: [], tags: [], json: false, list: false, suitePath: DEFAULT_SUITE_PATH };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--fixture") options.names.push(argv[++index] || "");
    else if (argument === "--tag") options.tags.push(argv[++index] || "");
    else if (argument === "--suite") options.suitePath = argv[++index] || "";
    else if (argument === "--json") options.json = true;
    else if (argument === "--list") options.list = true;
    else if (argument === "--help" || argument === "-h") options.help = true;
    else throw new ReplayAssertionError(`unknown argument: ${argument}`, { fixture: "<cli>", path: "$" });
  }
  return options;
}

function printHelp() {
  process.stdout.write([
    "Usage: node scripts/replay-agent-traces.cjs [options]",
    "",
    "Options:",
    "  --fixture <name>  replay one named trace (repeatable)",
    "  --tag <tag>       require a fixture tag (repeatable)",
    "  --suite <path>    use another trace suite",
    "  --list            list matching fixture names",
    "  --json            emit machine-readable JSON",
    "  -h, --help        show this help",
    "",
  ].join("\n"));
}

function main(argv = process.argv.slice(2)) {
  try {
    const options = parseArguments(argv);
    if (options.help) {
      printHelp();
      return 0;
    }
    const suite = loadSuite(options.suitePath);
    if (options.list) {
      const selected = selectFixtures(suite.fixtures || [], options);
      process.stdout.write(`${selected.map((fixture) => fixture.name).join("\n")}\n`);
      return selected.length ? 0 : 1;
    }
    const summary = runReplaySuite(suite, options);
    if (options.json) {
      process.stdout.write(`${JSON.stringify(summary)}\n`);
    } else {
      process.stdout.write(
        `Harness replay passed: ${summary.fixtureCount} fixtures, `
        + `${summary.eventCount} events, ${summary.checkpointCount} checkpoints, `
        + `${summary.checkpointRecoveryCount} checkpoint recoveries, `
        + `${summary.recoveryCount} explicit recoveries\n`,
      );
      process.stdout.write(`Replay hash: ${summary.suiteReplayHash}\n`);
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
  ReplayAssertionError,
  canonicalHash,
  firstDifference,
  loadSuite,
  replayFixture,
  runReplaySuite,
  selectFixtures,
};

if (require.main === module) process.exitCode = main();
