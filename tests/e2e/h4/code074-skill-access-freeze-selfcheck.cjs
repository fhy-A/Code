const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const MODEL_ID = "h4-e2e-model";
const SKILL = "h4-skill-access";
const BODY = "H4_SKILL_ACCESS_BODY_MUST_APPEAR_ONCE";
const GUIDE = "H4_SKILL_ACCESS_PINNED_GUIDE\n";
const USER = "H4_SKILL_ACCESS_USER";
const FINAL = "H4_SKILL_ACCESS_FINAL";
const CALL_IDS = [
  "h4-skill-access-use",
  "h4-skill-access-read",
  "h4-skill-access-check",
  "h4-skill-access-command",
  "h4-skill-access-nonactive",
];

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

async function waitFor(check, message, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await delay(40);
  }
  throw new Error(message);
}

async function installSkill(host) {
  const directory = path.join(host.dataDir, "skills", SKILL);
  const helper = Buffer.from("print('h4 trusted helper')\n", "utf8");
  await fs.mkdir(path.join(directory, "scripts"), { recursive: true });
  await fs.mkdir(path.join(directory, "references"), { recursive: true });
  await fs.writeFile(path.join(directory, "SKILL.md"), [
    "---",
    `name: ${SKILL}`,
    "description: H4 canonical active access fixture",
    "keywords: h4+skill+access",
    "allowed-tools: use_skill, check_skill_dependencies, read_skill_resource, run_command",
    "---",
    "",
    BODY,
    "Read references/guide.md and use the trusted helper only when required.",
    "",
  ].join("\n"), "utf8");
  await fs.writeFile(path.join(directory, "dependencies.json"), JSON.stringify({
    schemaVersion: 1,
    skill: SKILL,
    capabilities: { inspect: { required: [], optional: [] } },
  }), "utf8");
  await fs.writeFile(path.join(directory, "scripts", "run.py"), helper);
  await fs.writeFile(path.join(directory, "references", "guide.md"), GUIDE, "utf8");
  await fs.writeFile(path.join(directory, "code-resources.json"), JSON.stringify({
    schemaVersion: 1,
    skill: SKILL,
    resources: [{
      id: "run-helper",
      path: "scripts/run.py",
      sha256: sha256(helper),
      kind: "python",
      protocol: "h4-skill-access/v1",
      modelVisible: true,
      arguments: ["<input>"],
    }],
  }), "utf8");
}

async function readTerminalRecord(host, runId) {
  const target = path.join(host.dataDir, "agent-runs", `${runId}.json`);
  return waitFor(async () => {
    try {
      const record = JSON.parse(await fs.readFile(target, "utf8"));
      return ["completed", "failed", "cancelled"].includes(record.status) ? record : null;
    } catch {
      return null;
    }
  }, `AgentRun did not become terminal: ${runId}`);
}

async function createContext(browser, host, runtime) {
  const context = await browser.newContext({
    viewport: { width: 1200, height: 760 },
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await context.addInitScript(({ syntheticKey, platformToken, modelId }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    localStorage.setItem("code-key-config", JSON.stringify([{
      name: "H4 synthetic", key: syntheticKey, enabled: true, source: "manual",
    }]));
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken, userId: "7", username: "h4-user",
    }));
    localStorage.setItem("code-model", modelId);
    localStorage.setItem("code-permission-profile", "bypass");
    localStorage.setItem("code-auto-permission-risk-ack", "v1");
  }, {
    syntheticKey: host.syntheticKey,
    platformToken: host.platformToken,
    modelId: MODEL_ID,
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      await route.abort("blockedbyclient");
    } else if (url.pathname === "/proxy/models") {
      await route.continue({ headers: { ...request.headers(), "x-base-url": host.ready.fakeUrl } });
    } else {
      await route.continue();
    }
  });
  return context;
}

function assertRun(record, host) {
  assert.equal(record.version, 5);
  assert.deepEqual(record.activeSkillNames, [SKILL]);
  assert.equal(record.skillLifecycle.access.schemaVersion, 2);
  assert.equal(record.skillLifecycle.access.resourceBindings.length, 1);
  assert.deepEqual(record.skillLifecycle.access.resourceBindings[0], {
    kind: "text",
    skill: SKILL,
    file: "references/guide.md",
    contentHash: `sha256:${sha256(Buffer.from(GUIDE, "utf8"))}`,
  });
  assert.equal(record.skillLifecycle.activation.selected[0].resources.source, "custom");
  assert.equal(JSON.stringify(record.skillLifecycle).includes(host.root), false);
  assert.deepEqual(record.skillRuntimeBindings.bindings.map((binding) => ({
    skill: binding.skill,
    capability: binding.capability,
    checkedStatus: binding.checkedStatus,
  })), [{ skill: SKILL, capability: "inspect", checkedStatus: "ready" }]);

  const executions = record.toolExecutions || {};
  assert.deepEqual(Object.keys(executions), CALL_IDS);
  const use = executions[CALL_IDS[0]].result;
  assert.deepEqual(Object.keys(use).sort(), [
    "action", "alreadyActive", "dependencies", "name", "ok", "runtimeBinding",
    "runtimeResources",
  ]);
  assert.equal(use.ok, true);
  assert.equal(use.runtimeResources.source, "custom");
  assert.equal(use.dependencies.installGuidance.selectedCapability, "inspect");
  assert.equal(Object.hasOwn(use, "body"), false);
  const read = executions[CALL_IDS[1]].result;
  assert.equal(read.content, GUIDE);
  assert.equal(read.file, "references/guide.md");
  const check = executions[CALL_IDS[2]].result;
  assert.equal(check.ok, true);
  assert.equal(check.installGuidance.selectedCapability, "inspect");
  assert.equal(check.runtimeBinding.established, true);
  const command = executions[CALL_IDS[3]].result;
  assert.equal(command.ok, true);
  assert.equal(command.stdout, "H4_SKILL_RUNTIME_PREFLIGHT_OK");
  assert.deepEqual(command.runtime.skills, [{ skill: SKILL, capability: "inspect" }]);
  const rejected = executions[CALL_IDS[4]].result;
  assert.equal(rejected.ok, false);
  assert.equal(rejected.errorCode, "skill_lifecycle_skill_not_active");
  assert.equal(JSON.stringify(rejected).includes("Available"), false);
  const system = String(record.messages?.[0]?.content || "");
  assert.equal(system.split(BODY).length - 1, 1);
}

async function exercise(browser, host, runtime) {
  const context = await createContext(browser, host, runtime);
  const page = await context.newPage();
  const responses = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("response", (response) => {
    const request = response.request();
    if (request.method() === "POST" && new URL(response.url()).pathname === "/api/agent/runs") {
      response.json().then((body) => responses.push({ status: response.status(), body })).catch(() => {});
    }
  });
  try {
    const target = runtime === "classic"
      ? new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await page.waitForFunction((expected) => (
      document.documentElement.getAttribute("data-frontend-runtime") === expected
    ), runtime === "bundle" ? "bundle" : "classic-fallback");
    await page.locator("#modelPillBtn").waitFor({ state: "visible" });
    await waitFor(
      () => page.locator("#modelPillBtn").getAttribute("data-model").then((value) => value === MODEL_ID),
      `${runtime} model catalog was not ready`,
    );
    await page.locator("#baseUrl").evaluate((element, fakeUrl) => { element.value = fakeUrl; }, host.ready.fakeUrl);
    await page.locator("#prompt").fill(`/${SKILL} ${USER}`);
    await page.locator("#sendBtn").click();
    await waitFor(() => responses.length === 1, `${runtime} AgentRun create was not observed`);
    assert.equal(responses[0].status, 201);
    await host.releaseModel();
    await page.locator("#messages article.msg.assistant").filter({ hasText: FINAL })
      .waitFor({ state: "visible", timeout: 20_000 });
    const record = await readTerminalRecord(host, String(responses[0].body.agentRunId || ""));
    assertRun(record, host);
    assert.deepEqual(pageErrors, []);
    return { runtime, status: record.status, tools: Object.keys(record.toolExecutions || {}).length };
  } finally {
    await page.close();
    await context.close();
  }
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true, enableSkillActivation: true });
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    await installSkill(host);
    const directResponse = await fetch(new URL("/api/tools/use_skill", host.ready.codeUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: SKILL }),
    });
    const direct = await directResponse.json();
    assert.equal(directResponse.status, 200, JSON.stringify(direct));
    assert.equal(direct.ok, true);
    assert.equal(direct.body.includes(BODY), true);
    assert.equal(direct.runtimeResources.source, "custom");

    browser = await chromium.launch({ headless: true });
    const runtimes = [];
    for (const runtime of ["bundle", "classic"]) {
      runtimes.push(await exercise(browser, host, runtime));
    }
    result = {
      ok: true,
      command: "code074-skill-access-freeze-selfcheck",
      directLegacyBody: true,
      runtimes,
    };
  } finally {
    if (browser) await browser.close();
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
  }
  result.cleanup = {
    childExited: cleanup.childExited,
    portsClosed: cleanup.portsClosed,
    rootRemoved: cleanup.rootRemoved,
    activeChildCount: getActiveChildCount(),
  };
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
