const assert = require("node:assert/strict");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const SENTINEL_NAME = "H4_PARENT_SECRET_SENTINEL";
const INJECTED_FAILURE = "H4_INJECTED_BEFORE_BROWSER";

async function main() {
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

  process.stdout.write(`${JSON.stringify({
    infrastructureSelfCheck: "passed",
    injectedFailureObserved,
    parentSentinelPresent: environment.parentSentinelPresent,
    sensitiveEnvironmentNameCount: environment.sensitiveNames.length,
    homeIsIsolated: environment.homeIsIsolated,
    toolBoundary,
    childExited: cleanup.childExited,
    activeChildCount: cleanup.activeChildCount,
    portsClosed: cleanup.portsClosed,
    rootRemoved: cleanup.rootRemoved,
    stopIdempotent: true,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`H4 infrastructure self-check failed: ${error.message}\n`);
  process.exitCode = 1;
});
