const childProcess = require("node:child_process");
const fs = require("node:fs/promises");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");

const TEMP_PREFIX = "code-h4-e2e-";
const FIXTURE_CONTENT = "H4_SYNTHETIC_FILE_CONTENT\n";
const VISUAL_FIXTURE_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC",
  "base64",
);
const COMMAND_TIMEOUT_MS = 5_000;
const EXIT_TIMEOUT_MS = 5_000;
const activeChildren = new Set();

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function withTimeout(promise, timeoutMs, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    Promise.resolve(promise).then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

async function fetchJsonBounded(url, options = {}, timeoutMs = COMMAND_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const payload = await response.json();
    if (!response.ok || payload?.ok !== true) {
      throw new Error(`H4 gate control failed (${response.status})`);
    }
    return payload;
  } finally {
    clearTimeout(timer);
  }
}

function assertOwnedRoot(root) {
  const resolved = path.resolve(root);
  const temporaryBase = path.resolve(os.tmpdir());
  if (path.dirname(resolved) !== temporaryBase || !path.basename(resolved).startsWith(TEMP_PREFIX)) {
    throw new Error(`Refusing to manage non-H4 temporary root: ${resolved}`);
  }
  return resolved;
}

function buildChildEnvironment(homeDir, temporaryDir) {
  const environment = {
    HOME: homeDir,
    USERPROFILE: homeDir,
    TEMP: temporaryDir,
    TMP: temporaryDir,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    NO_PROXY: "127.0.0.1,localhost,::1",
    no_proxy: "127.0.0.1,localhost,::1",
  };
  const pathValue = process.env.Path || process.env.PATH;
  if (pathValue) environment[process.platform === "win32" ? "Path" : "PATH"] = pathValue;
  for (const name of ["PATHEXT", "SystemRoot", "WINDIR", "ComSpec"]) {
    const value = process.env[name] || process.env[name.toUpperCase()];
    if (value) environment[name] = value;
  }
  return environment;
}

async function portAcceptsConnections(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    const finish = (open) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(200, () => finish(false));
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
  });
}

async function waitForPortClosed(port, timeoutMs = EXIT_TIMEOUT_MS) {
  if (!Number.isInteger(port) || port <= 0) return false;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await portAcceptsConnections(port))) return true;
    await delay(50);
  }
  return !(await portAcceptsConnections(port));
}

function childHasExited(child) {
  return !child || child.exitCode !== null || child.signalCode !== null;
}

function classifyPendingCommandOnChildExit({
  command,
  initiatedByStop = false,
  exitCode,
  signalCode = null,
} = {}) {
  const completedByExpectedStopExit = (
    command === "shutdown"
    && initiatedByStop === true
    && exitCode === 0
    && signalCode === null
  );
  return Object.freeze({
    completedByExpectedStopExit,
    outcome: completedByExpectedStopExit ? "complete" : "reject",
  });
}

async function waitForChildExit(child, timeoutMs = EXIT_TIMEOUT_MS) {
  if (childHasExited(child)) return true;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (exited) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.removeListener("exit", onExit);
      child.removeListener("close", onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    const timer = setTimeout(() => finish(childHasExited(child)), timeoutMs);
    child.once("exit", onExit);
    child.once("close", onExit);
  });
}

async function terminateRecordedChild(child) {
  if (childHasExited(child)) return true;
  try {
    child.kill();
  } catch {}
  if (await waitForChildExit(child)) return true;
  try {
    child.kill("SIGKILL");
  } catch {}
  return waitForChildExit(child);
}

async function listRelativeFiles(root) {
  const results = [];
  async function visit(directory) {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(target);
      else results.push(path.relative(root, target).split(path.sep).join("/"));
    }
  }
  await visit(root);
  return results.sort();
}

async function rootIsRemoved(root) {
  try {
    await fs.access(root);
    return false;
  } catch {
    return true;
  }
}

function sanitizeText(value, secrets, root) {
  let text = String(value ?? "");
  for (const secret of secrets) {
    if (secret) text = text.split(secret).join("[redacted]");
  }
  if (root) text = text.split(root).join("<temporary-root>");
  return text.slice(0, 2_000);
}

async function createOwnedWorkspace() {
  const root = assertOwnedRoot(await fs.mkdtemp(path.join(os.tmpdir(), TEMP_PREFIX)));
  const dataDir = path.join(root, "data");
  const projectDir = path.join(root, "project");
  const artifactsDir = path.join(root, "artifacts");
  const homeDir = path.join(root, "home");
  const temporaryDir = path.join(root, "tmp");
  const syntheticKey = ["h4", "synthetic", "credential"].join("-");
  const platformToken = ["h4", "platform", "session"].join("-");

  try {
    await Promise.all([
      fs.mkdir(dataDir, { recursive: true }),
      fs.mkdir(projectDir, { recursive: true }),
      fs.mkdir(artifactsDir, { recursive: true }),
      fs.mkdir(homeDir, { recursive: true }),
      fs.mkdir(temporaryDir, { recursive: true }),
    ]);
    await Promise.all([
      fs.writeFile(path.join(projectDir, "fixture.txt"), FIXTURE_CONTENT, "utf8"),
      fs.writeFile(path.join(projectDir, "parallel-visual-a.png"), VISUAL_FIXTURE_PNG),
      fs.writeFile(path.join(projectDir, "parallel-visual-b.png"), VISUAL_FIXTURE_PNG),
    ]);
  } catch (error) {
    assertOwnedRoot(root);
    await fs.rm(root, { recursive: true, force: true });
    throw error;
  }

  return Object.freeze({
    root,
    dataDir,
    projectDir,
    artifactsDir,
    homeDir,
    temporaryDir,
    syntheticKey,
    platformToken,
  });
}

async function startIsolatedGeneration(
  workspace,
  {
    injectFailureAfterSpawn = false,
    injectIndexBuildFailure = false,
    disableRoutingV2 = false,
  } = {},
) {
  const {
    root,
    dataDir,
    projectDir,
    artifactsDir,
    homeDir,
    temporaryDir,
    syntheticKey,
    platformToken,
  } = workspace;
  assertOwnedRoot(root);
  let child = null;
  let lines = null;
  let host = null;

  try {
    const scriptPath = path.join(__dirname, "isolated_host.py");
    child = childProcess.spawn("python", ["-u", scriptPath, root], {
      cwd: path.resolve(__dirname, "..", "..", ".."),
      env: {
        ...buildChildEnvironment(homeDir, temporaryDir),
        ...(injectIndexBuildFailure
          ? { CODE_H4_INJECT_AGENT_INDEX_BUILD_FAILURE: "1" }
          : {}),
        ...(disableRoutingV2 ? { CODE_ROUTING_V2: "0" } : {}),
      },
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    activeChildren.add(child);
    if (injectFailureAfterSpawn) {
      throw new Error("H4 injected generation startup failure");
    }

    const stderr = [];
    const pending = new Map();
    let nextId = 1;
    let readyResolve;
    let readyReject;
    const readyPromise = new Promise((resolve, reject) => {
      readyResolve = resolve;
      readyReject = reject;
    });

    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => stderr.push(String(chunk)));
    lines = readline.createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      let payload;
      try {
        payload = JSON.parse(line);
      } catch {
        return;
      }
      if (payload.type === "ready") {
        readyResolve(payload);
        return;
      }
      if (payload.type === "response" && pending.has(payload.id)) {
        pending.get(payload.id).finish(null, payload);
      }
    });

    const rejectPending = (error) => {
      for (const handler of pending.values()) handler.finish(error);
      pending.clear();
    };
    child.once("error", (error) => {
      readyReject(error);
      rejectPending(error);
    });
    const onChildExit = (code, signalCode) => {
      activeChildren.delete(child);
      const exitDescription = signalCode === null ? String(code) : `signal ${signalCode}`;
      const error = new Error(`H4 isolated host exited (${exitDescription})`);
      if (!host?.ready) readyReject(error);
      for (const handler of [...pending.values()]) {
        const classification = classifyPendingCommandOnChildExit({
          command: handler.command,
          initiatedByStop: handler.initiatedByStop,
          exitCode: code,
          signalCode,
        });
        if (classification.completedByExpectedStopExit) {
          handler.finish(null, {
            type: "response",
            id: handler.id,
            ok: true,
            completedBy: "expected-stop-exit",
          });
        } else {
          handler.finish(error);
        }
      }
    };
    child.once("exit", onChildExit);

    let stopPromise = null;
    const sendCommand = (
      command,
      details = {},
      timeoutMs = COMMAND_TIMEOUT_MS,
      { initiatedByStop = false } = {},
    ) => {
      if (childHasExited(child) || !child.stdin.writable) {
        throw new Error(`H4 host command unavailable: ${command}`);
      }
      const id = nextId;
      nextId += 1;
      return new Promise((resolve, reject) => {
        let settled = false;
        const finish = (error, response) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          pending.delete(id);
          if (error) reject(error);
          else resolve(response);
        };
        const timer = setTimeout(() => {
          finish(new Error(`H4 host command timed out: ${command}`));
        }, timeoutMs);
        pending.set(id, {
          id,
          command,
          initiatedByStop,
          finish,
        });
        child.stdin.write(`${JSON.stringify({ id, command, ...details })}\n`, (error) => {
          if (error) finish(error);
        });
      });
    };
    host = {
      root,
      dataDir,
      projectDir,
      artifactsDir,
      childPid: child.pid,
      syntheticKey,
      platformToken,
      ready: null,
      stderr,
      async command(command, details = {}, timeoutMs = COMMAND_TIMEOUT_MS) {
        return sendCommand(command, details, timeoutMs);
      },
      async metrics() {
        const response = await this.command("metrics");
        return response.metrics;
      },
      async refreshGateStatus() {
        const response = await fetchJsonBounded(`${this.ready.fakeUrl}/__h4/refresh-gates`);
        return response.gates || {};
      },
      async releaseModel() {
        const response = await this.command("release-model");
        if (response.ok !== true) throw new Error("H4 model gate release failed");
      },
      async armModelCatalogGate() {
        const response = await this.command("arm-model-catalog");
        if (response.ok !== true || response.gate?.armed !== true) {
          throw new Error("H4 model catalog gate arm failed");
        }
        return response.gate;
      },
      async waitModelCatalogGate() {
        const response = await this.command("wait-model-catalog", {}, 6_000);
        if (response.ok !== true || response.gate?.reached !== true) {
          throw new Error("H4 model catalog gate was not reached");
        }
        return response.gate;
      },
      async releaseModelCatalogGate() {
        const response = await this.command("release-model-catalog");
        if (response.ok !== true || response.gate?.released !== true) {
          throw new Error("H4 model catalog gate release failed");
        }
        return response.gate;
      },
      async waitRefreshGate(gate, timeoutMs = 5_000) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
          const gates = await this.refreshGateStatus();
          if (gates?.[gate]?.reached) return gates;
        }
        throw new Error(`H4 refresh gate was not reached: ${gate}`);
      },
      async releaseRefreshGate(gate) {
        const response = await fetchJsonBounded(
          `${this.ready.fakeUrl}/__h4/refresh-gates/${encodeURIComponent(gate)}`,
          { method: "POST" },
        );
        if (!response.gates?.[gate]?.released) {
          throw new Error(`H4 refresh gate release failed: ${gate}`);
        }
        return response.gates;
      },
      async releaseAllRefreshGates() {
        const response = await fetchJsonBounded(
          `${this.ready.fakeUrl}/__h4/refresh-gates/release-all`,
          { method: "POST" },
        );
        const gates = Object.values(response.gates || {});
        if (gates.length === 0 || gates.some((state) => !state.released)) {
          throw new Error("H4 refresh gate release-all failed");
        }
        return response.gates;
      },
      async probeToolBoundary() {
        const response = await this.command("probe-tool-boundary");
        if (response.ok !== true) throw new Error("H4 tool boundary probe failed");
        return response.contract;
      },
      sanitize(value) {
        return sanitizeText(value, [syntheticKey, platformToken], root);
      },
      async stop() {
        if (stopPromise) return stopPromise;
        stopPromise = (async () => {
          let metrics = null;
          const cleanupErrors = [];
          try {
            metrics = await this.metrics();
          } catch (error) {
            cleanupErrors.push(error);
          }
          if (!childHasExited(child)) {
            try {
              await sendCommand(
                "shutdown",
                {},
                COMMAND_TIMEOUT_MS,
                { initiatedByStop: true },
              );
            } catch (error) {
              cleanupErrors.push(error);
            }
          }
          try {
            child.stdin.end();
          } catch (error) {
            cleanupErrors.push(error);
          }

          let childExited = await waitForChildExit(child);
          if (!childExited) childExited = await terminateRecordedChild(child);
          if (childExited) activeChildren.delete(child);
          try {
            lines.close();
          } catch (error) {
            cleanupErrors.push(error);
          }

          const portsClosed = this.ready
            ? await Promise.all([
              waitForPortClosed(this.ready.codePort),
              waitForPortClosed(this.ready.fakePort),
            ])
            : [false, false];
          let temporaryFiles = [];
          try {
            temporaryFiles = await listRelativeFiles(root);
          } catch (error) {
            cleanupErrors.push(error);
          }
          const sanitizedStderr = this.sanitize(stderr.join(""));
          const rootRemoved = await rootIsRemoved(root);
          return {
            metrics,
            portsClosed,
            temporaryFiles,
            rootRemoved,
            rootRetained: !rootRemoved,
            sanitizedStderr,
            cleanupErrors: cleanupErrors.map((error) => this.sanitize(error?.message || error)),
            childPid: child.pid,
            childExited,
            activeChildCount: activeChildren.size,
          };
        })();
        return stopPromise;
      },
    };

    host.ready = await withTimeout(
      readyPromise,
      10_000,
      "H4 isolated host readiness timeout",
    );
    return host;
  } catch (error) {
    if (lines) lines.close();
    const childExited = child ? await terminateRecordedChild(child) : true;
    if (childExited && child) activeChildren.delete(child);
    if (!childExited) {
      throw new Error(`H4 generation readiness cleanup failed (childExited=${childExited})`, {
        cause: error,
      });
    }
    throw error;
  }
}

async function startIsolatedHost(initialGenerationOptions = {}) {
  const workspace = await createOwnedWorkspace();
  let currentGeneration = null;
  let finalStopPromise = null;
  let generationNumber = 0;

  const startGeneration = async (options = {}) => {
    generationNumber += 1;
    return startIsolatedGeneration(workspace, options);
  };

  try {
    currentGeneration = await startGeneration(initialGenerationOptions);
  } catch (error) {
    assertOwnedRoot(workspace.root);
    await fs.rm(workspace.root, { recursive: true, force: true });
    throw error;
  }

  const managed = {
    ...workspace,
    get ready() {
      return currentGeneration?.ready || null;
    },
    get stderr() {
      return currentGeneration?.stderr || [];
    },
    get generationNumber() {
      return generationNumber;
    },
    get childPid() {
      return currentGeneration?.childPid || null;
    },
    async command(command, details = {}, timeoutMs = COMMAND_TIMEOUT_MS) {
      if (!currentGeneration) throw new Error("H4 generation is not running");
      return currentGeneration.command(command, details, timeoutMs);
    },
    async metrics() {
      if (!currentGeneration) throw new Error("H4 generation is not running");
      return currentGeneration.metrics();
    },
    async refreshGateStatus() {
      return currentGeneration.refreshGateStatus();
    },
    async releaseModel() {
      return currentGeneration.releaseModel();
    },
    async armModelCatalogGate() {
      return currentGeneration.armModelCatalogGate();
    },
    async waitModelCatalogGate() {
      return currentGeneration.waitModelCatalogGate();
    },
    async releaseModelCatalogGate() {
      return currentGeneration.releaseModelCatalogGate();
    },
    async waitRefreshGate(gate, timeoutMs = 5_000) {
      return currentGeneration.waitRefreshGate(gate, timeoutMs);
    },
    async releaseRefreshGate(gate) {
      return currentGeneration.releaseRefreshGate(gate);
    },
    async releaseAllRefreshGates() {
      return currentGeneration.releaseAllRefreshGates();
    },
    async probeToolBoundary() {
      return currentGeneration.probeToolBoundary();
    },
    sanitize(value) {
      return sanitizeText(
        value,
        [workspace.syntheticKey, workspace.platformToken],
        workspace.root,
      );
    },
    async restartGeneration(options = {}) {
      if (finalStopPromise) throw new Error("H4 host is already stopping");
      if (!currentGeneration) throw new Error("H4 generation is not running");
      const previous = currentGeneration;
      const previousReady = previous.ready;
      const previousCleanup = await previous.stop();
      if (
        previousCleanup.childExited !== true
        || previousCleanup.portsClosed.some((closed) => closed !== true)
        || previousCleanup.rootRetained !== true
        || previousCleanup.cleanupErrors.length > 0
      ) {
        throw new Error("H4 previous generation did not close cleanly before restart");
      }
      currentGeneration = null;
      const next = await startGeneration(options);
      currentGeneration = next;
      return Object.freeze({
        previousPid: previousCleanup.childPid,
        currentPid: next.childPid,
        previousReady,
        currentReady: next.ready,
        previousCleanup,
        generationNumber,
      });
    },
    async stop() {
      if (finalStopPromise) return finalStopPromise;
      finalStopPromise = (async () => {
        let generationCleanup = null;
        const cleanupErrors = [];
        if (currentGeneration) {
          try {
            generationCleanup = await currentGeneration.stop();
          } catch (error) {
            cleanupErrors.push(error);
          }
          currentGeneration = null;
        }
        if (!generationCleanup) {
          generationCleanup = {
            metrics: null,
            portsClosed: [true, true],
            temporaryFiles: [],
            rootRemoved: false,
            rootRetained: true,
            sanitizedStderr: "",
            cleanupErrors: [],
            childPid: null,
            childExited: true,
            activeChildCount: activeChildren.size,
          };
        }
        cleanupErrors.push(...generationCleanup.cleanupErrors);
        let temporaryFiles = generationCleanup.temporaryFiles;
        try {
          temporaryFiles = await listRelativeFiles(workspace.root);
        } catch (error) {
          cleanupErrors.push(error);
        }
        if (generationCleanup.childExited) {
          try {
            assertOwnedRoot(workspace.root);
            await fs.rm(workspace.root, { recursive: true, force: true });
          } catch (error) {
            cleanupErrors.push(error);
          }
        }
        const rootRemoved = await rootIsRemoved(workspace.root);
        return {
          ...generationCleanup,
          temporaryFiles,
          rootRemoved,
          rootRetained: !rootRemoved,
          cleanupErrors: cleanupErrors.map((error) => managed.sanitize(error?.message || error)),
          activeChildCount: activeChildren.size,
        };
      })();
      return finalStopPromise;
    },
  };
  return managed;
}

function getActiveChildCount() {
  return activeChildren.size;
}

process.once("exit", () => {
  for (const child of activeChildren) {
    try {
      child.kill();
    } catch {}
  }
});

module.exports = {
  FIXTURE_CONTENT,
  classifyPendingCommandOnChildExit,
  getActiveChildCount,
  startIsolatedHost,
};
