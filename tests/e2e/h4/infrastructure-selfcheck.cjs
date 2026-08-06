const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const {
  classifyPendingCommandOnChildExit,
  getActiveChildCount,
  startIsolatedHost,
} = require("./isolated-host.cjs");

const SENTINEL_NAME = "H4_PARENT_SECRET_SENTINEL";
const INJECTED_FAILURE = "H4_INJECTED_BEFORE_BROWSER";

async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function main() {
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

  try {
    host = await startIsolatedHost();
    environment = host.ready.environment;
    assert.deepEqual(environment, {
      parentSentinelPresent: false,
      sensitiveNames: [],
      homeIsIsolated: true,
    });

    toolBoundary = await host.probeToolBoundary();
    assert.deepEqual(toolBoundary, {
      rejectedAction: true,
      rejectedPath: true,
      allowedRead: true,
      unsafeDelta: 2,
      delegationDelta: 1,
      toolExecutionDelta: 1,
    });

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

  const restartHost = await startIsolatedHost();
  const restartPaths = {
    root: restartHost.root,
    dataDir: restartHost.dataDir,
    projectDir: restartHost.projectDir,
    homeDir: restartHost.homeDir,
  };
  const firstReady = restartHost.ready;
  const transition = await restartHost.restartGeneration();
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

  const failedRestartHost = await startIsolatedHost();
  const failedRestartRoot = failedRestartHost.root;
  let startupFailureObserved = false;
  try {
    await failedRestartHost.restartGeneration({ injectFailureAfterSpawn: true });
  } catch (error) {
    assert.equal(error.message, "H4 injected generation startup failure");
    startupFailureObserved = true;
  }
  assert.equal(startupFailureObserved, true);
  assert.equal(await pathExists(failedRestartRoot), true);
  const failedRestartCleanup = await failedRestartHost.stop();
  assert.equal(failedRestartCleanup.childExited, true);
  assert.deepEqual(failedRestartCleanup.portsClosed, [true, true]);
  assert.equal(failedRestartCleanup.rootRemoved, true);
  assert.deepEqual(failedRestartCleanup.cleanupErrors, []);
  assert.strictEqual(await failedRestartHost.stop(), failedRestartCleanup);
  assert.equal(getActiveChildCount(), 0);

  process.stdout.write(`${JSON.stringify({
    infrastructureSelfCheck: "passed",
    injectedFailureObserved,
    parentSentinelPresent: environment.parentSentinelPresent,
    sensitiveEnvironmentNameCount: environment.sensitiveNames.length,
    homeIsIsolated: environment.homeIsIsolated,
    toolBoundary,
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
      observed: startupFailureObserved,
      finalRootRemoved: failedRestartCleanup.rootRemoved,
      activeChildCount: getActiveChildCount(),
    },
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`H4 infrastructure self-check failed: ${error.message}\n`);
  process.exitCode = 1;
});
