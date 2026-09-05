const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");

const PREFIX = "code-h4-c3-";
const SKILL = "startup-alpha";
const HOST = path.join(__dirname, "code074_skill_startup_host.py");
const ROOT = path.resolve(__dirname, "..", "..", "..");
const activeChildren = new Set();
const activeHosts = new Set();

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function withTimeout(promise, timeout, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeout);
    Promise.resolve(promise).then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error) => { clearTimeout(timer); reject(error); },
    );
  });
}

async function portClosed(port, timeout = 5_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const open = await new Promise((resolve) => {
      const socket = net.createConnection({ host: "127.0.0.1", port });
      const finish = (value) => { socket.destroy(); resolve(value); };
      socket.setTimeout(150, () => finish(false));
      socket.once("connect", () => finish(true));
      socket.once("error", () => finish(false));
    });
    if (!open) return true;
    await delay(40);
  }
  return false;
}

function assertOwnedRoot(root) {
  const resolved = path.resolve(root);
  assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()));
  assert.equal(path.basename(resolved).startsWith(PREFIX), true);
  return resolved;
}

function spawnHost(root, mode, syncFailed = false, delayReady = false) {
  const args = [
    "-u", HOST, root, "serve", mode,
    ...(syncFailed ? ["sync-failed"] : []),
    ...(delayReady ? ["delay-ready"] : []),
  ];
  const child = childProcess.spawn("python", args, {
    cwd: ROOT,
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1",
      NO_PROXY: "127.0.0.1,localhost,::1",
      no_proxy: "127.0.0.1,localhost,::1",
    },
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  activeChildren.add(child);
  const events = [];
  const waiters = [];
  const stderr = [];
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (value) => stderr.push(String(value)));
  const lines = readline.createInterface({ input: child.stdout });
  const deliver = (event) => {
    events.push(event);
    for (let index = waiters.length - 1; index >= 0; index -= 1) {
      if (waiters[index].predicate(event)) {
        const waiter = waiters.splice(index, 1)[0];
        clearTimeout(waiter.timer);
        waiter.resolve(event);
      }
    }
  };
  lines.on("line", (line) => {
    try { deliver(JSON.parse(line)); } catch {}
  });
  const waitFor = (predicate, label, timeout = 15_000) => {
    const found = events.find(predicate);
    if (found) return Promise.resolve(found);
    return new Promise((resolve, reject) => {
      const waiter = { predicate, resolve, reject, timer: null };
      waiter.timer = setTimeout(() => {
        const index = waiters.indexOf(waiter);
        if (index >= 0) waiters.splice(index, 1);
        reject(new Error(`${label}; stderr=${stderr.join("").slice(-1000)}`));
      }, timeout);
      waiters.push(waiter);
    });
  };
  let resolveExit;
  let exited = false;
  let spawnError = null;
  const exit = new Promise((resolve) => { resolveExit = resolve; });
  const rejectWaiters = (error) => {
    while (waiters.length) {
      const waiter = waiters.pop();
      clearTimeout(waiter.timer);
      waiter.reject(error);
    }
  };
  const finishExit = (code, signal) => {
    if (exited) return;
    exited = true;
    activeChildren.delete(child);
    lines.close();
    const error = spawnError || new Error(`host exited (${signal || code})`);
    rejectWaiters(error);
    resolveExit({ code, signal, spawnError, stderr: stderr.join("") });
  };
  child.once("error", (error) => {
    spawnError = error;
    rejectWaiters(error);
    // A failed spawn has no process to reap.  Errors from an existing PID do
    // not prove exit; retain ownership tracking until the exit event arrives.
    if (child.pid == null) finishExit(null, null);
  });
  child.once("exit", (code, signal) => finishExit(code, signal));
  const host = { child, events, waitFor, exit, get exited() { return exited; } };
  activeHosts.add(host);
  exit.finally(() => activeHosts.delete(host));
  return host;
}

async function terminateHost(host) {
  if (!host.exited && host.child.stdin.writable) {
    try { host.child.stdin.write(`${JSON.stringify({ command: "shutdown" })}\n`); } catch {}
  }
  if (!host.exited) {
    try { await withTimeout(host.exit, 2_000, "graceful host exit timed out"); } catch {
      try { host.child.kill(); } catch {}
    }
  }
  const exited = await withTimeout(host.exit, 5_000, "forced host exit timed out");
  const listening = host.events.find((event) => event.type === "listening");
  const portsClosed = listening ? await Promise.all([
    portClosed(listening.codePort), portClosed(listening.fakePort),
  ]) : [];
  return { childExited: host.exited, portsClosed, exited };
}

async function start(root, mode, syncFailed = false, options = {}) {
  const host = spawnHost(root, mode, syncFailed, options.delayReady === true);
  try {
    if (options.delayReady === true) {
      await host.waitFor(
        (event) => event.type === "listening",
        `${mode} delayed host never reached the controlled listener boundary`,
        15_000,
      );
    }
    const first = await host.waitFor(
      (event) => ["ready", "startup-error", "owner-error"].includes(event.type),
      `${mode} host did not publish a startup result`,
      options.timeout || 15_000,
    );
    host.first = first;
    return host;
  } catch (error) {
    error.cleanup = await terminateHost(host);
    throw error;
  }
}

async function stop(host) {
  try {
    host.child.stdin.write(`${JSON.stringify({ command: "shutdown" })}\n`);
    const stopped = await host.waitFor(
      (event) => event.type === "stopped", "host did not stop", 8_000,
    );
    const cleanup = await terminateHost(host);
    assert.equal(cleanup.exited.code, 0, cleanup.exited.stderr);
    assert.deepEqual(stopped.portsClosed, [true, true]);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
  } catch (error) {
    error.cleanup = await terminateHost(host);
    throw error;
  }
}

async function prepare(root) {
  const child = childProcess.spawn("python", ["-u", HOST, root, "prepare"], {
    cwd: ROOT, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", PYTHONUTF8: "1" },
  });
  activeChildren.add(child);
  child.once("close", () => activeChildren.delete(child));
  child.once("error", () => {
    if (child.pid == null) activeChildren.delete(child);
  });
  let output = "";
  let error = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (value) => { output += value; });
  child.stderr.on("data", (value) => { error += value; });
  const code = await withTimeout(new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (value) => resolve(value));
  }), 15_000, "fixture preparation timed out").catch((error) => {
    try { child.kill(); } catch {}
    throw error;
  });
  activeChildren.delete(child);
  assert.equal(code, 0, error);
  assert.equal(JSON.parse(output.trim()).ok, true);
}

async function api(base, target, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(new URL(target, base), {
      ...options,
      signal: controller.signal,
      headers: { "content-type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json();
    return { status: response.status, body };
  } finally {
    clearTimeout(timer);
  }
}

async function waitRun(base, runId, expected, timeout = 15_000) {
  const deadline = Date.now() + timeout;
  let latest = null;
  while (Date.now() < deadline) {
    const result = await api(base, `/api/agent/runs/${runId}`);
    assert.equal(result.status, 200);
    latest = result.body;
    if (expected.includes(latest.status)) return latest;
    await delay(40);
  }
  throw new Error(`run ${runId} stayed ${latest?.status}; expected ${expected.join(",")}`);
}

async function createRun(ready, { immutable, message, requestId }) {
  const body = {
    sessionId: "",
    clientRequestId: requestId,
    payload: {
      model: "h4-startup-model",
      messages: [
        ...(immutable ? [{ role: "system", content: "[[CODE_SKILL_ACTIVATION_CANONICAL_V1]]" }] : []),
        { role: "user", content: message },
      ],
    },
    baseUrl: ready.fakeUrl,
    keys: ["h4-startup-key"],
    allowedTools: immutable
      ? { schemaVersion: 1, names: ["read_file", "write_file"] }
      : ["read_file", "write_file"],
    permissionProfile: "accept",
    runKind: "foreground",
    maxRounds: 3,
    ...(immutable ? {
      skillActivationRequest: {
        schemaVersion: 1, explicitSkill: SKILL, disabledNames: [],
      },
    } : { activeSkillName: "", activeSkillNames: [] }),
  };
  const created = await api(ready.codeUrl, "/api/agent/runs", {
    method: "POST", body: JSON.stringify(body),
  });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  return created.body.agentRunId;
}

async function storeHash(root) {
  const store = path.join(root, "profile", "skill-store-v1");
  const hash = crypto.createHash("sha256");
  async function visit(directory) {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      const target = path.join(directory, entry.name);
      const relative = path.relative(store, target).split(path.sep).join("/");
      hash.update(relative).update("\0");
      if (entry.isDirectory()) await visit(target);
      else hash.update(await fs.readFile(target));
    }
  }
  await visit(store);
  return hash.digest("hex");
}

async function record(root, runId) {
  return JSON.parse(await fs.readFile(
    path.join(root, "profile", "agent-runs", `${runId}.json`), "utf8",
  ));
}

async function main() {
  const root = assertOwnedRoot(await fs.mkdtemp(path.join(os.tmpdir(), PREFIX)));
  const evidence = { generations: [], failures: [] };
  try {
    await prepare(root);
    let injectedCleanup = null;
    try {
      await start(root, "off", false, { delayReady: true, timeout: 100 });
      assert.fail("controlled ready timeout did not fire");
    } catch (error) {
      injectedCleanup = error.cleanup;
    }
    assert.equal(injectedCleanup.childExited, true);
    assert.deepEqual(injectedCleanup.portsClosed, [true, true]);
    assert.equal(activeChildren.size, 0);
    const afterInjectedFailure = await start(root, "off");
    assert.equal(afterInjectedFailure.first.type, "ready");
    assert.equal(afterInjectedFailure.first.startup.status, "disabled");
    await stop(afterInjectedFailure);
    evidence.failures.push({
      mode: "controlled-ready-timeout", childExited: true, portsClosed: [true, true],
    });

    const first = await start(root, "on");
    assert.equal(first.first.type, "ready");
    assert.deepEqual(first.first.startup, {
      status: "ready", admissionEnabled: true, readerReady: true, errorCode: "",
    });
    const heartbeat = await api(first.first.codeUrl, "/api/browser-heartbeat");
    assert.equal(heartbeat.body.skillActivationProtocol, "canonical-v1");
    const pendingId = await createRun(first.first, {
      immutable: true, message: "hold-v6 generation one", requestId: "h4-c3-pending",
    });
    await waitRun(first.first.codeUrl, pendingId, ["waiting_authorization"]);
    const pendingRecord = await record(root, pendingId);
    assert.equal(pendingRecord.version, 6);
    const identity = pendingRecord.skillLifecycle.activation.selected[0];
    const initialStoreHash = await storeHash(root);

    const concurrent = await start(root, "off");
    assert.equal(concurrent.first.type, "owner-error");
    assert.equal(concurrent.first.code, "data_dir_owner_busy");
    assert.equal(concurrent.first.listenerPublished, false);
    assert.equal((await withTimeout(
      concurrent.exit, 5_000, "owner-busy host exit timed out",
    )).code, 3);
    await stop(first);
    evidence.generations.push({ mode: "on", version: 6, status: "waiting_authorization" });

    const second = await start(root, "off", true);
    assert.equal(second.first.type, "ready");
    assert.equal(second.first.startup.readerReady, true);
    assert.equal(second.first.startup.admissionEnabled, false);
    assert.equal((await api(second.first.codeUrl, "/api/browser-heartbeat")).body.skillActivationProtocol, undefined);
    const restored = await waitRun(second.first.codeUrl, pendingId, ["waiting_authorization"]);
    const authorizationId = restored.pendingAuthorization.authorizationId;
    const rejected = await api(second.first.codeUrl, `/api/agent/runs/${pendingId}/authorization`, {
      method: "POST",
      body: JSON.stringify({ authorizationId, decision: "rejected" }),
    });
    assert.equal(rejected.status, 200, JSON.stringify(rejected.body));
    const resumed = await api(second.first.codeUrl, `/api/agent/runs/${pendingId}/resume`, {
      method: "POST",
      body: JSON.stringify({ keys: ["h4-startup-key"], baseUrl: second.first.fakeUrl }),
    });
    assert.equal(resumed.status, 200, JSON.stringify(resumed.body));
    await waitRun(second.first.codeUrl, pendingId, ["completed"]);
    const legacyId = await createRun(second.first, {
      immutable: false, message: "legacy generation two", requestId: "h4-c3-legacy",
    });
    await waitRun(second.first.codeUrl, legacyId, ["completed"]);
    assert.equal((await record(root, legacyId)).version, 5);
    assert.equal(await storeHash(root), initialStoreHash);
    await stop(second);
    evidence.generations.push({ mode: "off", restoredV6: true, newVersion: 5 });

    const third = await start(root, "on", true);
    assert.equal(third.first.type, "ready");
    assert.equal(third.first.store.dataRootId, first.first.store.dataRootId);
    assert.equal(third.first.store.registryHash, first.first.store.registryHash);
    assert.equal(third.first.store.receiptCount, 1);
    const finalId = await createRun(third.first, {
      immutable: true, message: "generation three", requestId: "h4-c3-final",
    });
    await waitRun(third.first.codeUrl, finalId, ["completed"]);
    const finalRecord = await record(root, finalId);
    assert.equal(finalRecord.version, 6);
    assert.equal(finalRecord.skillLifecycle.activation.selected[0].revisionId, identity.revisionId);
    const oldClientId = await createRun(third.first, {
      immutable: false, message: "old client while immutable enabled", requestId: "h4-c3-old-client",
    });
    await waitRun(third.first.codeUrl, oldClientId, ["completed"]);
    assert.equal((await record(root, oldClientId)).version, 5);
    const cancelId = await createRun(third.first, {
      immutable: true, message: "hold-v6 cancel after corruption", requestId: "h4-c3-cancel",
    });
    const recoverId = await createRun(third.first, {
      immutable: true, message: "hold-v6 recover after corruption", requestId: "h4-c3-recover",
    });
    await waitRun(third.first.codeUrl, cancelId, ["waiting_authorization"]);
    await waitRun(third.first.codeUrl, recoverId, ["waiting_authorization"]);
    await stop(third);
    evidence.generations.push({ mode: "on", newVersion: 6, sameRevision: true });

    const digest = identity.revisionId.replace(/^sha256:/, "");
    const objectSkill = path.join(
      root, "profile", "skill-store-v1", "objects", "sha256", digest.slice(0, 2),
      digest, "content", "SKILL.md",
    );
    const original = await fs.readFile(objectSkill);
    await fs.writeFile(objectSkill, Buffer.concat([original, Buffer.from("corrupt")]));
    const blocked = await start(root, "on");
    assert.equal(blocked.first.type, "startup-error");
    assert.equal(blocked.first.listenerPublished, false);
    assert.equal((await withTimeout(
      blocked.exit, 5_000, "startup-error host exit timed out",
    )).code, 2);
    evidence.failures.push({ mode: "on", code: blocked.first.code, listenerPublished: false });

    const degraded = await start(root, "off");
    assert.equal(degraded.first.type, "ready");
    assert.equal(degraded.first.startup.status, "unavailable");
    assert.equal(degraded.first.startup.readerReady, false);
    await waitRun(degraded.first.codeUrl, cancelId, ["waiting_recovery"]);
    await waitRun(degraded.first.codeUrl, recoverId, ["waiting_recovery"]);
    const degradedLegacy = await createRun(degraded.first, {
      immutable: false, message: "legacy while immutable unavailable", requestId: "h4-c3-degraded-legacy",
    });
    await waitRun(degraded.first.codeUrl, degradedLegacy, ["completed"]);
    assert.equal((await record(root, degradedLegacy)).version, 5);
    await fs.writeFile(objectSkill, original);
    assert.equal((await waitRun(degraded.first.codeUrl, recoverId, ["waiting_recovery"])).status, "waiting_recovery");
    const cancelled = await api(degraded.first.codeUrl, `/api/agent/runs/${cancelId}`, { method: "DELETE" });
    assert.equal(cancelled.status, 200);
    assert.equal((await waitRun(degraded.first.codeUrl, cancelId, ["cancelled"])).status, "cancelled");
    assert.equal("skillRecovery" in await record(root, cancelId), false);
    await stop(degraded);

    const recovered = await start(root, "off", true);
    assert.equal(recovered.first.startup.readerReady, true);
    await waitRun(recovered.first.codeUrl, recoverId, ["waiting_authorization"]);
    const finalCancel = await api(recovered.first.codeUrl, `/api/agent/runs/${recoverId}`, { method: "DELETE" });
    assert.equal(finalCancel.status, 200);
    await waitRun(recovered.first.codeUrl, recoverId, ["cancelled"]);
    assert.equal(await storeHash(root), initialStoreHash);
    await stop(recovered);
    evidence.failures.push({ mode: "off", legacyAvailable: true, restartRequired: true, cancelReaderFree: true });

    console.log(JSON.stringify({ ok: true, command: "code074-skill-runtime-startup-selfcheck", ...evidence }));
  } finally {
    assertOwnedRoot(root);
    for (const host of [...activeHosts]) {
      await terminateHost(host);
    }
    for (const child of [...activeChildren]) {
      if (child.exitCode === null && child.signalCode === null) {
        try { child.kill(); } catch {}
        await withTimeout(new Promise((resolve) => child.once("exit", resolve)), 5_000,
          "owned fixture child did not exit");
      }
      activeChildren.delete(child);
    }
    assert.equal(activeHosts.size, 0, "owned fixture hosts remain active");
    assert.equal(activeChildren.size, 0, "owned fixture children remain active");
    await fs.rm(root, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
