const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const SCHEMA = "code-development-doctor-node/v1";
const TEMP_PREFIX = "code-doctor-chromium-";
const ESBUILD_TIMEOUT_MS = 8_000;
const CHROMIUM_LAUNCH_TIMEOUT_MS = 10_000;
const CHROMIUM_ACTION_TIMEOUT_MS = 5_000;

function withTimeout(promise, timeoutMs, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const error = new Error(`${label} timed out after ${timeoutMs}ms`);
      error.code = "DOCTOR_TIMEOUT";
      reject(error);
    }, timeoutMs);
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

function compactError(error) {
  const message = String(error?.message || error || "unknown error")
    .split(/\r?\n/, 1)[0]
    .slice(0, 300);
  return {
    name: String(error?.name || "Error"),
    code: String(error?.code || ""),
    message,
  };
}

function classifyError(error, fallback = "execution_failed") {
  const code = String(error?.code || "");
  const message = String(error?.message || error || "");
  if (code === "DOCTOR_TIMEOUT" || /timed out/i.test(message)) return "timeout";
  if (code === "MODULE_NOT_FOUND") return "missing";
  if (code === "ENOENT" || /executable doesn't exist/i.test(message)) return "missing";
  if (code === "EPERM" || code === "EACCES" || /spawn (EPERM|EACCES)/i.test(message)) {
    return "launch_failed";
  }
  return fallback;
}

function assertOwnedTemporaryRoot(root) {
  const resolved = path.resolve(root);
  const temporaryBase = path.resolve(os.tmpdir());
  if (path.dirname(resolved) !== temporaryBase || !path.basename(resolved).startsWith(TEMP_PREFIX)) {
    throw new Error(`Refusing to manage non-doctor temporary root: ${resolved}`);
  }
  return resolved;
}

async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function probeEsbuild() {
  let esbuild = null;
  try {
    esbuild = require("esbuild");
    const result = await withTimeout(
      esbuild.transform("const doctorValue = 1;", {
        loader: "js",
        format: "esm",
        target: "es2020",
      }),
      ESBUILD_TIMEOUT_MS,
      "esbuild transform",
    );
    if (!String(result?.code || "").includes("doctorValue")) {
      throw new Error("esbuild transform returned unexpected output");
    }
    return {
      id: "esbuild_transform",
      status: "passed",
      reason: "ready",
      detail: { version: String(esbuild.version || "unknown") },
    };
  } catch (error) {
    return {
      id: "esbuild_transform",
      status: "failed",
      reason: classifyError(error),
      detail: compactError(error),
    };
  } finally {
    try {
      esbuild?.stop?.();
    } catch {}
  }
}

async function probePlaywrightAndChromium() {
  let playwright;
  let chromium;
  let packageVersion = "unknown";
  try {
    const packageEntry = require.resolve("@playwright/test");
    playwright = require("@playwright/test");
    chromium = playwright.chromium;
    const packageData = JSON.parse(
      await fs.readFile(path.join(path.dirname(packageEntry), "package.json"), "utf8"),
    );
    packageVersion = String(packageData.version || "unknown");
    if (!chromium || typeof chromium.launchPersistentContext !== "function") {
      throw new Error("@playwright/test does not expose Chromium");
    }
  } catch (error) {
    return [
      {
        id: "playwright_package",
        status: "failed",
        reason: classifyError(error, "load_failed"),
        detail: compactError(error),
      },
      {
        id: "chromium_launch",
        status: "failed",
        reason: "blocked",
        detail: { cleanup: "not_started" },
      },
    ];
  }

  const playwrightCheck = {
    id: "playwright_package",
    status: "passed",
    reason: "ready",
    detail: { version: packageVersion },
  };
  const executable = chromium.executablePath();
  if (!(await pathExists(executable))) {
    return [
      playwrightCheck,
      {
        id: "chromium_launch",
        status: "failed",
        reason: "missing",
        detail: { cleanup: "not_started", executable },
      },
    ];
  }

  const temporaryRoot = assertOwnedTemporaryRoot(
    await fs.mkdtemp(path.join(os.tmpdir(), TEMP_PREFIX)),
  );
  let context = null;
  let contextClosed = false;
  let rootRemoved = false;
  let launchDetail = null;
  let failure = null;

  try {
    context = await chromium.launchPersistentContext(temporaryRoot, {
      headless: true,
      timeout: CHROMIUM_LAUNCH_TIMEOUT_MS,
      acceptDownloads: false,
      serviceWorkers: "block",
      args: [
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
      ],
    });
    const page = await withTimeout(context.newPage(), CHROMIUM_ACTION_TIMEOUT_MS, "Chromium page creation");
    await withTimeout(
      page.setContent("<!doctype html><title>Code doctor</title><p>ready</p>"),
      CHROMIUM_ACTION_TIMEOUT_MS,
      "Chromium local page",
    );
    launchDetail = {
      browserVersion: String(context.browser()?.version() || "unknown"),
      executable,
    };
  } catch (error) {
    failure = error;
  } finally {
    if (context) {
      try {
        await withTimeout(context.close(), CHROMIUM_ACTION_TIMEOUT_MS, "Chromium close");
        contextClosed = true;
      } catch (error) {
        failure = failure || error;
      }
    }
    try {
      assertOwnedTemporaryRoot(temporaryRoot);
      await fs.rm(temporaryRoot, {
        recursive: true,
        force: true,
        maxRetries: 3,
        retryDelay: 100,
      });
      rootRemoved = !(await pathExists(temporaryRoot));
    } catch (error) {
      failure = failure || error;
    }
  }

  const cleanup = {
    contextClosed: context ? contextClosed : true,
    temporaryRootRemoved: rootRemoved,
  };
  if (failure || !cleanup.contextClosed || !cleanup.temporaryRootRemoved) {
    const reason = (
      !cleanup.contextClosed || !cleanup.temporaryRootRemoved
        ? "cleanup_failed"
        : classifyError(failure, "launch_failed")
    );
    return [
      playwrightCheck,
      {
        id: "chromium_launch",
        status: "failed",
        reason,
        detail: { ...compactError(failure), ...cleanup, executable },
      },
    ];
  }

  return [
    playwrightCheck,
    {
      id: "chromium_launch",
      status: "passed",
      reason: "ready",
      detail: { ...launchDetail, ...cleanup },
    },
  ];
}

async function main() {
  const checks = [];
  checks.push(await probeEsbuild());
  checks.push(...await probePlaywrightAndChromium());
  const failed = checks.some((check) => check.status === "failed");
  process.stdout.write(`${JSON.stringify({
    schema: SCHEMA,
    nodeExecutable: process.execPath,
    nodeVersion: process.version,
    checks,
  })}\n`);
  process.exitCode = failed ? 1 : 0;
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({
    schema: SCHEMA,
    fatal: compactError(error),
    checks: [],
  })}\n`);
  process.exitCode = 1;
});
