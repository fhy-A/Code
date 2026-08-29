const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const {
  classifyPendingCommandOnChildExit,
  getActiveChildCount,
  startIsolatedHost,
} = require("./isolated-host.cjs");

const SENTINEL_NAME = "H4_PARENT_SECRET_SENTINEL";
const INJECTED_FAILURE = "H4_INJECTED_BEFORE_BROWSER";
const THIRD_PARTY_TRANSITION_COMMAND = "transition-propose-edit-third-party";
const THIRD_PARTY_TRANSITION_CONTRACT = Object.freeze({
  command: THIRD_PARTY_TRANSITION_COMMAND,
  path: "h4-propose-edit-fixture.txt",
  expectedBeforeSha256: "f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3",
  byteLength: 28,
  targetSha256: "3ca2970e23df18316faba0c55fde5881e36d215d02499ee36e3e257113ebe931",
});
const ZERO_PRODUCTION_CALLBACKS = Object.freeze({
  registeredDelegations: 0,
  proposalDelegations: 0,
  applyDelegations: 0,
  writes: 0,
  backups: 0,
  toolExecutions: 0,
  runCommandAttempts: 0,
});

async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

function assertAgentRunIndexesReady(ready) {
  assert.deepEqual(ready.agentRunIndexes, {
    nonterminal: {
      state: "ready",
      entries: ready.agentRunIndexes.nonterminal.entries,
      processInitialized: true,
    },
    session: {
      state: "ready",
      entries: ready.agentRunIndexes.session.entries,
      processInitialized: true,
    },
  });
  assert.equal(Number.isInteger(ready.agentRunIndexes.nonterminal.entries), true);
  assert.equal(Number.isInteger(ready.agentRunIndexes.session.entries), true);
}

async function listOwnedH4Roots() {
  const entries = await fs.readdir(os.tmpdir(), { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("code-h4-e2e-"))
    .map((entry) => entry.name)
    .sort();
}

async function requestJson(codeUrl, pathname, {
  method = "GET",
  body,
} = {}) {
  const headers = {};
  let encodedBody;
  if (body !== undefined) {
    headers["content-type"] = "application/json";
    encodedBody = JSON.stringify(body);
  }
  const response = await fetch(new URL(pathname, codeUrl), {
    method,
    headers,
    body: encodedBody,
    signal: AbortSignal.timeout(5_000),
  });
  const text = await response.text();
  return {
    status: response.status,
    body: text ? JSON.parse(text) : null,
  };
}

async function runArchiveDeleteRestartEquivalentEvidence() {
  const host = await startIsolatedHost();
  let cleanup;
  try {
    assertAgentRunIndexesReady(host.ready);
    const targetCreated = await requestJson(host.ready.codeUrl, "/api/sessions", {
      method: "POST",
      body: {
        title: "H4 equivalent archive target",
        messages: [{ role: "user", content: "H4_EQUIVALENT_TARGET" }],
        runState: { status: "completed" },
      },
    });
    const unrelatedCreated = await requestJson(host.ready.codeUrl, "/api/sessions", {
      method: "POST",
      body: {
        title: "H4 equivalent unrelated Session",
        messages: [{ role: "user", content: "H4_EQUIVALENT_UNRELATED" }],
        runState: { status: "completed" },
      },
    });
    assert.equal(targetCreated.status, 201);
    assert.equal(unrelatedCreated.status, 201);
    const targetSessionId = String(targetCreated.body.id || "");
    const unrelatedSessionId = String(unrelatedCreated.body.id || "");
    assert.match(targetSessionId, /^[a-f0-9]{16}$/);
    assert.match(unrelatedSessionId, /^[a-f0-9]{16}$/);

    const targetSeed = await host.command("seed-session-archive-sidecars", {
      sessionId: targetSessionId,
    });
    const unrelatedSeed = await host.command("seed-session-archive-sidecars", {
      sessionId: unrelatedSessionId,
    });
    assert.equal(targetSeed.ok, true);
    assert.equal(unrelatedSeed.ok, true);
    const targetRunId = targetSeed.archiveFixture.agentRunId;
    const unrelatedRunId = unrelatedSeed.archiveFixture.agentRunId;

    const archived = await requestJson(
      host.ready.codeUrl,
      `/api/session-archive/${targetSessionId}/archive`,
      { method: "POST" },
    );
    assert.equal(archived.status, 200);
    assert.equal(archived.body.status, "archived");

    const transition = await host.restartGeneration();
    assert.equal(transition.generationNumber, 2);
    assertAgentRunIndexesReady(transition.currentReady);
    assert.equal(transition.currentReady.agentRunIndexes.session.entries >= 2, true);

    const listed = await requestJson(host.ready.codeUrl, "/api/session-archive");
    assert.equal(listed.status, 200);
    const targetArchive = listed.body.data.find((item) => item.id === targetSessionId);
    assert.match(String(targetArchive?.archiveToken || ""), /^[a-f0-9]{32}$/);

    const resetReads = await host.command("session-archive-run-read-evidence", {
      runIds: [targetRunId, unrelatedRunId],
      reset: true,
    });
    assert.deepEqual(resetReads.runReads, {
      [targetRunId]: 0,
      [unrelatedRunId]: 0,
    });

    const deletePath = `/api/session-archive/${targetSessionId}`
      + `?archiveToken=${targetArchive.archiveToken}`;
    const deleted = await requestJson(host.ready.codeUrl, deletePath, {
      method: "DELETE",
    });
    assert.equal(deleted.status, 200);
    assert.deepEqual(deleted.body, { ok: true });

    const targetEvidence = (await host.command(
      "session-archive-fixture-evidence",
      { sessionId: targetSessionId },
    )).archiveEvidence;
    assert.deepEqual(targetEvidence, {
      sessionId: targetSessionId,
      activeMeta: false,
      activeMessages: false,
      archiveBundle: false,
      archiveManifest: false,
      archiveSession: false,
      archiveMessages: false,
      goal: false,
      asset: false,
      agentRun: false,
    });
    const unrelatedEvidence = (await host.command(
      "session-archive-fixture-evidence",
      { sessionId: unrelatedSessionId },
    )).archiveEvidence;
    assert.deepEqual(unrelatedEvidence, {
      sessionId: unrelatedSessionId,
      activeMeta: true,
      activeMessages: true,
      archiveBundle: false,
      archiveManifest: false,
      archiveSession: false,
      archiveMessages: false,
      goal: true,
      asset: true,
      agentRun: true,
    });
    const readsAfterDelete = await host.command("session-archive-run-read-evidence", {
      runIds: [targetRunId, unrelatedRunId],
    });
    assert.deepEqual(readsAfterDelete.runReads, {
      [targetRunId]: 1,
      [unrelatedRunId]: 0,
    });

    const repeated = await requestJson(host.ready.codeUrl, deletePath, {
      method: "DELETE",
    });
    assert.equal(repeated.status, 410);
    assert.equal(repeated.body.errorCode, "session_deleted");
    const readsAfterRepeatedDelete = await host.command(
      "session-archive-run-read-evidence",
      { runIds: [targetRunId, unrelatedRunId] },
    );
    assert.deepEqual(readsAfterRepeatedDelete.runReads, readsAfterDelete.runReads);
    assert.deepEqual((await host.command(
      "session-archive-fixture-evidence",
      { sessionId: unrelatedSessionId },
    )).archiveEvidence, unrelatedEvidence);

    return {
      firstDeleteStatus: deleted.status,
      repeatedDeleteStatus: repeated.status,
      targetFactsRemoved: true,
      unrelatedRunReads: readsAfterDelete.runReads[unrelatedRunId],
      unrelatedFactsPreserved: true,
      processFreshRestartReady: true,
    };
  } finally {
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
  }
}

async function assertControlStdoutIsolationSourceContract() {
  const pythonHostPath = path.join(__dirname, "isolated_host.py");
  const productionServerPath = path.resolve(__dirname, "../../../server.py");
  const [pythonHostSource, productionServerSource] = await Promise.all([
    fs.readFile(pythonHostPath, "utf8"),
    fs.readFile(productionServerPath, "utf8"),
  ]);
  assert.match(
    pythonHostSource,
    /class H4CodeHandler\(code_server\.CodeHandler\):\s+def log_message\(self, _format: str, \*_args\) -> None:\s+return/,
  );
  assert.match(
    pythonHostSource,
    /code_server\.ThreadingHTTPServer\(\("127\.0\.0\.1", 0\), H4CodeHandler\)/,
  );
  assert.match(
    pythonHostSource,
    /agent_run_indexes = prepare_agent_run_indexes_before_listener\(\)\s+code_httpd = code_server\.ThreadingHTTPServer/,
  );
  assert.doesNotMatch(
    pythonHostSource,
    /code_server\.CodeHandler\.log_message\s*=/,
  );
  assert.match(
    productionServerSource,
    /class CodeHandler\(BaseHTTPRequestHandler\):[\s\S]*?def log_message\(self, fmt, \*args\):\s+print\(/,
  );
  return {
    h4UsesSilentSubclass: true,
    productionHandlerNotMonkeyPatched: true,
  };
}

async function runControlStdoutIsolationPressure(host) {
  const requestCount = 8;
  const controlCount = 8;
  const requestSummary = [];
  let controlPendingCount = 0;
  const requestPromises = Array.from({ length: requestCount }, async (_, index) => {
    const method = "GET";
    const pathname = "/api/ping";
    const url = new URL(pathname, host.ready.codeUrl);
    url.searchParams.set("h4_stdout_probe", String(index));
    const response = await fetch(url, {
      method,
      signal: AbortSignal.timeout(5_000),
    });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { pong: true });
    requestSummary.push({ method, path: pathname });
    return true;
  });
  const controlPromises = Array.from({ length: controlCount }, async () => {
    controlPendingCount += 1;
    try {
      const metrics = await host.metrics();
      assert.ok(metrics);
      assert.ok(Array.isArray(metrics.production?.agentRuns));
      assert.ok(Array.isArray(metrics.production?.runtimeRuns));
      return true;
    } finally {
      controlPendingCount -= 1;
    }
  });
  const settled = await Promise.all([...requestPromises, ...controlPromises]);
  assert.equal(settled.length, requestCount + controlCount);
  assert.equal(settled.every(Boolean), true);
  assert.equal(controlPendingCount, 0);
  assert.equal(requestSummary.length, requestCount);
  assert.deepEqual(
    [...new Set(requestSummary.map(({ method, path: requestPath }) => `${method} ${requestPath}`))],
    ["GET /api/ping"],
  );
  return {
    requestCount,
    controlCount,
    requestSummary,
    allPromisesSettled: true,
    controlPendingCount,
  };
}

function productionCallbackCounts(metrics) {
  return {
    registeredDelegations: Number(metrics.productionToolDelegations || 0),
    proposalDelegations: Number(metrics.productionEditProposalDelegations || 0),
    applyDelegations: Number(metrics.productionEditApplyDelegations || 0),
    writes: Number(metrics.productionEditWrites || 0),
    backups: Number(metrics.productionEditBackups || 0),
    toolExecutions: (metrics.toolExecutions || []).length,
    runCommandAttempts: (metrics.runCommandAttempts || []).length,
  };
}

function callbackDelta(before, after) {
  return Object.fromEntries(Object.keys(ZERO_PRODUCTION_CALLBACKS).map((key) => (
    [key, Number(after[key] || 0) - Number(before[key] || 0)]
  )));
}

async function exerciseThirdPartyTransitionPrecondition(host) {
  const initialState = {
    state: "initial",
    exists: true,
    initialHashMatches: true,
    targetHashMatches: false,
    thirdPartyHashMatches: false,
  };
  const metricsBefore = await host.metrics();
  const callbacksBefore = productionCallbackCounts(metricsBefore);
  const response = await host.command(THIRD_PARTY_TRANSITION_COMMAND);
  assert.equal(response.ok, false);
  assert.deepEqual(response.transition, {
    accepted: false,
    reason: "proposal-precondition-not-ready",
    commandKeysExact: true,
    attempt: 1,
    path: THIRD_PARTY_TRANSITION_CONTRACT.path,
    fileBefore: initialState,
    fileAfter: initialState,
    fixedBytes: {
      byteLength: THIRD_PARTY_TRANSITION_CONTRACT.byteLength,
      sha256: THIRD_PARTY_TRANSITION_CONTRACT.targetSha256,
      hashMatches: false,
    },
    projectTreeUnchanged: true,
    projectTreeChangedOnlyAtFixedPath: false,
    homeTreeUnchanged: true,
    artifactsTreeUnchanged: true,
    backupCountBefore: 0,
    backupCountAfter: 0,
    productionCallbacks: ZERO_PRODUCTION_CALLBACKS,
  });
  const metricsAfter = await host.metrics();
  assert.deepEqual(
    callbackDelta(callbacksBefore, productionCallbackCounts(metricsAfter)),
    ZERO_PRODUCTION_CALLBACKS,
  );
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionAttempts
      - metricsBefore.proposeEditThirdPartyTransitionAttempts,
    1,
  );
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionWrites
      - metricsBefore.proposeEditThirdPartyTransitionWrites,
    0,
  );
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionRejections
      - metricsBefore.proposeEditThirdPartyTransitionRejections,
    1,
  );
  assert.deepEqual(
    metricsAfter.proposeEditThirdPartyTransitionTimeline.slice(
      metricsBefore.proposeEditThirdPartyTransitionTimeline.length,
    ),
    [response.transition],
  );
  return response.transition;
}

async function exerciseThirdPartyTransitionBoundary(host) {
  assert.deepEqual(host.ready.proposeEditThirdPartyTransition, THIRD_PARTY_TRANSITION_CONTRACT);
  const initialState = {
    state: "initial",
    exists: true,
    initialHashMatches: true,
    targetHashMatches: false,
    thirdPartyHashMatches: false,
  };
  const thirdPartyState = {
    state: "third-party",
    exists: true,
    initialHashMatches: false,
    targetHashMatches: false,
    thirdPartyHashMatches: true,
  };
  const fixedBytesBefore = {
    byteLength: THIRD_PARTY_TRANSITION_CONTRACT.byteLength,
    sha256: THIRD_PARTY_TRANSITION_CONTRACT.targetSha256,
    hashMatches: false,
  };
  const fixedBytesAfter = { ...fixedBytesBefore, hashMatches: true };
  const metricsBefore = await host.metrics();
  const callbacksBefore = productionCallbackCounts(metricsBefore);

  const invalidDetails = [
    { path: THIRD_PARTY_TRANSITION_CONTRACT.path },
    { path: "../outside" },
    { path: "C:\\H4_SYNTHETIC_ABSOLUTE\\fixture.txt" },
    { body: "H4_UNTRUSTED_THIRD_PARTY_BYTES" },
    { targetSha256: "0".repeat(64) },
    { expectedBeforeSha256: THIRD_PARTY_TRANSITION_CONTRACT.expectedBeforeSha256 },
    { byteLength: THIRD_PARTY_TRANSITION_CONTRACT.byteLength },
  ];
  const invalid = [];
  const firstAttempt = Number(metricsBefore.proposeEditThirdPartyTransitionAttempts || 0) + 1;
  for (const [index, details] of invalidDetails.entries()) {
    const response = await host.command(THIRD_PARTY_TRANSITION_COMMAND, details);
    assert.equal(response.ok, false);
    assert.deepEqual(response.transition, {
      accepted: false,
      reason: "payload-not-allowed",
      commandKeysExact: false,
      attempt: firstAttempt + index,
      path: THIRD_PARTY_TRANSITION_CONTRACT.path,
      fileBefore: initialState,
      fileAfter: initialState,
      fixedBytes: fixedBytesBefore,
      projectTreeUnchanged: true,
      projectTreeChangedOnlyAtFixedPath: false,
      homeTreeUnchanged: true,
      artifactsTreeUnchanged: true,
      backupCountBefore: 0,
      backupCountAfter: 0,
      productionCallbacks: ZERO_PRODUCTION_CALLBACKS,
    });
    invalid.push(response.transition);
  }

  const accepted = await host.command(THIRD_PARTY_TRANSITION_COMMAND);
  assert.equal(accepted.ok, true);
  assert.deepEqual(accepted.transition, {
    accepted: true,
    reason: "",
    commandKeysExact: true,
    attempt: firstAttempt + invalid.length,
    path: THIRD_PARTY_TRANSITION_CONTRACT.path,
    fileBefore: initialState,
    fileAfter: thirdPartyState,
    fixedBytes: fixedBytesAfter,
    projectTreeUnchanged: false,
    projectTreeChangedOnlyAtFixedPath: true,
    homeTreeUnchanged: true,
    artifactsTreeUnchanged: true,
    backupCountBefore: 0,
    backupCountAfter: 0,
    productionCallbacks: ZERO_PRODUCTION_CALLBACKS,
  });

  const repeated = await host.command(THIRD_PARTY_TRANSITION_COMMAND);
  assert.equal(repeated.ok, false);
  assert.deepEqual(repeated.transition, {
    accepted: false,
    reason: "already-transitioned",
    commandKeysExact: true,
    attempt: firstAttempt + invalid.length + 1,
    path: THIRD_PARTY_TRANSITION_CONTRACT.path,
    fileBefore: thirdPartyState,
    fileAfter: thirdPartyState,
    fixedBytes: fixedBytesAfter,
    projectTreeUnchanged: true,
    projectTreeChangedOnlyAtFixedPath: false,
    homeTreeUnchanged: true,
    artifactsTreeUnchanged: true,
    backupCountBefore: 0,
    backupCountAfter: 0,
    productionCallbacks: ZERO_PRODUCTION_CALLBACKS,
  });

  const metricsAfter = await host.metrics();
  const callbacksAfter = productionCallbackCounts(metricsAfter);
  assert.deepEqual(callbackDelta(callbacksBefore, callbacksAfter), ZERO_PRODUCTION_CALLBACKS);
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionAttempts
      - metricsBefore.proposeEditThirdPartyTransitionAttempts,
    invalid.length + 2,
  );
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionWrites
      - metricsBefore.proposeEditThirdPartyTransitionWrites,
    1,
  );
  assert.equal(
    metricsAfter.proposeEditThirdPartyTransitionRejections
      - metricsBefore.proposeEditThirdPartyTransitionRejections,
    invalid.length + 1,
  );
  assert.deepEqual(
    metricsAfter.proposeEditThirdPartyTransitionTimeline.slice(
      metricsBefore.proposeEditThirdPartyTransitionTimeline.length,
    ),
    [...invalid, accepted.transition, repeated.transition],
  );
  assert.equal(
    metricsAfter.productionEditConflictObservations
      - metricsBefore.productionEditConflictObservations,
    0,
  );
  assert.deepEqual(
    metricsAfter.proposeEditConflictTimeline.slice(
      metricsBefore.proposeEditConflictTimeline.length,
    ),
    [],
  );
  return {
    contract: THIRD_PARTY_TRANSITION_CONTRACT,
    invalid,
    accepted: accepted.transition,
    repeated: repeated.transition,
    counters: {
      attempts: invalid.length + 2,
      writes: 1,
      rejections: invalid.length + 1,
    },
    productionCallbacks: callbackDelta(callbacksBefore, callbacksAfter),
  };
}

async function main() {
  const stdoutIsolationSource = await assertControlStdoutIsolationSourceContract();
  const expectedStopExit = classifyPendingCommandOnChildExit({
    command: "shutdown",
    initiatedByStop: true,
    exitCode: 0,
    signalCode: null,
  });
  assert.deepEqual(expectedStopExit, {
    completedByExpectedStopExit: true,
    outcome: "complete",
  });
  for (const abnormalExit of [
    { exitCode: 1, signalCode: null },
    { exitCode: null, signalCode: "SIGTERM" },
  ]) {
    assert.equal(classifyPendingCommandOnChildExit({
      command: "shutdown",
      initiatedByStop: true,
      ...abnormalExit,
    }).outcome, "reject");
  }
  assert.equal(classifyPendingCommandOnChildExit({
    command: "metrics",
    initiatedByStop: true,
    exitCode: 0,
    signalCode: null,
  }).outcome, "reject");
  assert.equal(classifyPendingCommandOnChildExit({
    command: "shutdown",
    initiatedByStop: false,
    exitCode: 0,
    signalCode: null,
  }).outcome, "reject");

  const previousSentinel = process.env[SENTINEL_NAME];
  process.env[SENTINEL_NAME] = ["synthetic", "parent", "only"].join("-");
  let host = null;
  let cleanup = null;
  let injectedFailureObserved = false;
  let environment = null;
  let toolBoundary = null;
  let proposeEditFixture = null;
  let proposeEditThirdPartyTransition = null;
  let thirdPartyTransitionPrecondition = null;
  let thirdPartyTransitionBoundary = null;
  let thirdPartyFixturePath = null;
  let controlStdoutIsolation = null;

  try {
    host = await startIsolatedHost();
    assertAgentRunIndexesReady(host.ready);
    environment = host.ready.environment;
    proposeEditFixture = host.ready.proposeEditFixture;
    proposeEditThirdPartyTransition = host.ready.proposeEditThirdPartyTransition;
    assert.deepEqual(environment, {
      parentSentinelPresent: false,
      sensitiveNames: [],
      homeIsIsolated: true,
    });
    assert.deepEqual(
      proposeEditThirdPartyTransition,
      THIRD_PARTY_TRANSITION_CONTRACT,
    );
    thirdPartyTransitionPrecondition = await exerciseThirdPartyTransitionPrecondition(host);

    toolBoundary = await host.probeToolBoundary();
    assert.deepEqual(toolBoundary, {
      rejectedAction: true,
      rejectedPath: true,
      allowedRead: true,
      unsafeDelta: 2,
      delegationDelta: 1,
      toolExecutionDelta: 1,
      registryMutationActions: {
        rejectedWrite: true,
        rejectedDelete: true,
        unsafeDelta: 2,
        delegationDelta: 0,
        toolExecutionDelta: 0,
      },
      proposeEdit: {
        rejectedPathEscape: true,
        rejectedKeys: true,
        rejectedBytes: true,
        rejectedApplyAction: true,
        rejectedApplyPathEscape: true,
        rejectedApplyKeys: true,
        rejectedApplyBytes: true,
        allowedProposal: true,
        proposalApplied: false,
        initialFilePreserved: true,
        backupCountUnchanged: true,
        unsafeDelta: 7,
        delegationDelta: 1,
        toolExecutionDelta: 1,
        proposalDelegationDelta: 1,
        applyDelegationDelta: 0,
        writeDelta: 0,
        backupDelta: 0,
        proposalTimelineDelta: 1,
        applyTimelineDelta: 0,
        writeTimelineDelta: 0,
        backupTimelineDelta: 0,
      },
      runCommand: {
        rejectedRunCommand: true,
        attemptDelta: 1,
        unsafeDelta: 1,
        entryIsRejectStub: true,
        capturedOriginalCallable: true,
        stubReferencesOriginal: false,
        outputCallbackDelta: 0,
        processCallbackDelta: 0,
        projectTreeUnchanged: true,
        homeTreeUnchanged: true,
        artifactsTreeUnchanged: true,
        allTreesUnchanged: true,
      },
    });
    assert.deepEqual(proposeEditFixture, {
      path: "h4-propose-edit-fixture.txt",
      initialSha256: "f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3",
      targetSha256: "26ed22af144d40ac7a02a4a6087bbfa8bcb2024782e90fdac3ed6cb2abbbf3ef",
    });
    thirdPartyTransitionBoundary = await exerciseThirdPartyTransitionBoundary(host);
    thirdPartyFixturePath = path.join(
      host.projectDir,
      THIRD_PARTY_TRANSITION_CONTRACT.path,
    );
    assert.equal(await pathExists(thirdPartyFixturePath), true);

    controlStdoutIsolation = await runControlStdoutIsolationPressure(host);

    throw new Error(INJECTED_FAILURE);
  } catch (error) {
    assert.equal(error.message, INJECTED_FAILURE);
    injectedFailureObserved = true;
  } finally {
    try {
      if (host) cleanup = await host.stop();
    } finally {
      if (previousSentinel === undefined) delete process.env[SENTINEL_NAME];
      else process.env[SENTINEL_NAME] = previousSentinel;
    }
  }

  assert.equal(injectedFailureObserved, true);
  assert.ok(cleanup);
  assert.equal(cleanup.childExited, true);
  assert.equal(cleanup.activeChildCount, 0);
  assert.equal(getActiveChildCount(), 0);
  assert.deepEqual(cleanup.portsClosed, [true, true]);
  assert.equal(cleanup.rootRemoved, true);
  assert.deepEqual(cleanup.cleanupErrors, []);
  assert.strictEqual(await host.stop(), cleanup);
  assert.equal(await pathExists(thirdPartyFixturePath), false);

  const restartHost = await startIsolatedHost();
  const restartPaths = {
    root: restartHost.root,
    dataDir: restartHost.dataDir,
    projectDir: restartHost.projectDir,
    homeDir: restartHost.homeDir,
  };
  const firstReady = restartHost.ready;
  assertAgentRunIndexesReady(firstReady);
  const transition = await restartHost.restartGeneration();
  assertAgentRunIndexesReady(transition.currentReady);
  assert.notEqual(transition.previousPid, transition.currentPid);
  assert.equal(transition.previousPid > 0, true);
  assert.equal(transition.currentPid > 0, true);
  assert.equal(transition.generationNumber, 2);
  assert.deepEqual(transition.previousCleanup.portsClosed, [true, true]);
  assert.equal(transition.previousCleanup.childExited, true);
  assert.equal(transition.previousCleanup.rootRetained, true);
  assert.equal(transition.previousCleanup.rootRemoved, false);
  assert.deepEqual(transition.previousCleanup.cleanupErrors, []);
  assert.equal(await pathExists(restartPaths.root), true);
  assert.equal(restartHost.root, restartPaths.root);
  assert.equal(restartHost.dataDir, restartPaths.dataDir);
  assert.equal(restartHost.projectDir, restartPaths.projectDir);
  assert.equal(restartHost.homeDir, restartPaths.homeDir);
  for (const target of Object.values(restartPaths).slice(1)) {
    assert.equal(path.dirname(target) === restartPaths.root || target.startsWith(`${restartPaths.root}${path.sep}`), true);
    assert.equal(await pathExists(target), true);
  }
  assert.equal(firstReady.codePort > 0 && transition.currentReady.codePort > 0, true);
  assert.equal(firstReady.fakePort > 0 && transition.currentReady.fakePort > 0, true);
  assert.deepEqual(restartHost.ready.environment, {
    parentSentinelPresent: false,
    sensitiveNames: [],
    homeIsIsolated: true,
  });
  const restartCleanup = await restartHost.stop();
  assert.equal(restartCleanup.childExited, true);
  assert.deepEqual(restartCleanup.portsClosed, [true, true]);
  assert.equal(restartCleanup.rootRemoved, true);
  assert.equal(restartCleanup.rootRetained, false);
  assert.deepEqual(restartCleanup.cleanupErrors, []);
  assert.strictEqual(await restartHost.stop(), restartCleanup);

  const rootsBeforeIndexFailure = await listOwnedH4Roots();
  let initialIndexFailureObserved = false;
  try {
    await startIsolatedHost({ injectIndexBuildFailure: true });
  } catch (error) {
    assert.match(error.message, /^H4 isolated host exited \(/);
    initialIndexFailureObserved = true;
  }
  assert.equal(initialIndexFailureObserved, true);
  assert.deepEqual(await listOwnedH4Roots(), rootsBeforeIndexFailure);
  assert.equal(getActiveChildCount(), 0);

  const failedRestartHost = await startIsolatedHost();
  const failedRestartRoot = failedRestartHost.root;
  const failedRestartReady = failedRestartHost.ready;
  assertAgentRunIndexesReady(failedRestartReady);
  let startupFailureObserved = false;
  try {
    await failedRestartHost.restartGeneration({ injectIndexBuildFailure: true });
  } catch (error) {
    assert.match(error.message, /^H4 isolated host exited \(/);
    startupFailureObserved = true;
  }
  assert.equal(startupFailureObserved, true);
  assert.equal(await pathExists(failedRestartRoot), true);
  assert.equal(getActiveChildCount(), 0);
  assert.equal(failedRestartHost.ready, null);
  assert.equal(failedRestartHost.generationNumber, 2);
  assert.equal(failedRestartReady.codePort > 0, true);
  assert.equal(await pathExists(failedRestartRoot), true);
  const failedRestartCleanup = await failedRestartHost.stop();
  assert.equal(failedRestartCleanup.childExited, true);
  assert.deepEqual(failedRestartCleanup.portsClosed, [true, true]);
  assert.equal(failedRestartCleanup.rootRemoved, true);
  assert.deepEqual(failedRestartCleanup.cleanupErrors, []);
  assert.strictEqual(await failedRestartHost.stop(), failedRestartCleanup);
  assert.equal(getActiveChildCount(), 0);

  const archiveDeleteEquivalent = await runArchiveDeleteRestartEquivalentEvidence();
  assert.equal(getActiveChildCount(), 0);

  process.stdout.write(`${JSON.stringify({
    infrastructureSelfCheck: "passed",
    injectedFailureObserved,
    parentSentinelPresent: environment.parentSentinelPresent,
    sensitiveEnvironmentNameCount: environment.sensitiveNames.length,
    homeIsIsolated: environment.homeIsIsolated,
    toolBoundary,
    proposeEditFixture,
    proposeEditThirdPartyTransition,
    thirdPartyTransitionPrecondition,
    thirdPartyTransitionBoundary,
    controlStdoutIsolation: {
      ...stdoutIsolationSource,
      requestCount: controlStdoutIsolation.requestCount,
      controlCount: controlStdoutIsolation.controlCount,
      requestSummary: controlStdoutIsolation.requestSummary,
      allPromisesSettled: controlStdoutIsolation.allPromisesSettled,
      cleanupPendingCount: controlStdoutIsolation.controlPendingCount,
    },
    childExitClassification: {
      expectedStopExit: expectedStopExit.outcome,
      abnormalShutdownExit: "reject",
      pendingNonShutdown: "reject",
      shutdownOutsideStop: "reject",
    },
    childExited: cleanup.childExited,
    activeChildCount: cleanup.activeChildCount,
    portsClosed: cleanup.portsClosed,
    rootRemoved: cleanup.rootRemoved,
    stopIdempotent: true,
    crossProcessLifecycle: {
      distinctPids: transition.previousPid !== transition.currentPid,
      firstGenerationPortsClosedBeforeSecondReady: transition.previousCleanup.portsClosed,
      rootRetainedBetweenGenerations: transition.previousCleanup.rootRetained,
      sameOwnedPaths: true,
      finalRootRemoved: restartCleanup.rootRemoved,
      finalStopIdempotent: true,
    },
    restartStartupFailure: {
      initialObserved: initialIndexFailureObserved,
      observed: startupFailureObserved,
      listenerCreated: false,
      finalRootRemoved: failedRestartCleanup.rootRemoved,
      activeChildCount: getActiveChildCount(),
    },
    archiveDeleteRestartEquivalent: archiveDeleteEquivalent,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`H4 infrastructure self-check failed: ${error.message}\n`);
  process.exitCode = 1;
});
