const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const MODEL_ID = "h4-e2e-model";
const SKILL_NAME = "h4-completion";
const USER_MARKER = "H4_SKILL_COMPLETION_USER";
const CANDIDATE = "H4_SKILL_COMPLETION_CANDIDATE";
const FINAL = "H4_SKILL_COMPLETION_FINAL";

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitFor(check, message, timeoutMs = 12_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await delay(40);
  }
  throw new Error(message);
}

async function installSkill(host) {
  const directory = path.join(host.dataDir, "skills", SKILL_NAME);
  await fs.mkdir(directory, { recursive: true });
  await fs.writeFile(path.join(directory, "SKILL.md"), [
    "---",
    `name: ${SKILL_NAME}`,
    "description: H4 owner completion fixture",
    "tools: read_file",
    "---",
    "",
    "Use owner evidence before completion.",
  ].join("\n"), "utf8");
  await fs.writeFile(path.join(directory, "evidence.json"), JSON.stringify({
    schemaVersion: 2,
    requirements: [{
      id: "inspect-fixture",
      type: "tool_execution",
      tool: "read_file",
      minCount: 1,
    }],
    enforcement: {
      schemaVersion: 2,
      mode: "owner_completion_once",
      activationKinds: ["automatic", "explicit"],
    },
  }), "utf8");
}

async function readTerminalRecord(host, runId) {
  assert.match(runId, /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);
  const target = path.join(host.dataDir, "agent-runs", `${runId}.json`);
  return waitFor(async () => {
    try {
      const record = JSON.parse(await fs.readFile(target, "utf8"));
      return ["completed", "failed", "cancelled"].includes(record.status) ? record : null;
    } catch {
      return null;
    }
  }, `Skill completion AgentRun did not finish: ${runId}`);
}

async function exercise(browser, host, runtime) {
  const before = (await host.metrics()).chatRequests.length;
  const context = await browser.newContext({ viewport: { width: 1200, height: 760 } });
  await context.addInitScript(({ key, token, model }) => {
    class OfflineRenderer {}
    window.marked = { Renderer: OfflineRenderer, setOptions() {}, parse: String };
    window.__h4CompletionProtocol = "";
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      const raw = args[0] instanceof Request ? args[0].url : String(args[0] || "");
      if (new URL(raw, location.href).pathname === "/api/browser-heartbeat") {
        response.clone().json().then((body) => {
          window.__h4CompletionProtocol = String(body?.skillActivationProtocol || "");
        }).catch(() => {});
      }
      return response;
    };
    localStorage.setItem("code-key-config", JSON.stringify([{
      name: "H4 completion", key, enabled: true, source: "manual",
    }]));
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token, userId: "7", username: "h4-user",
    }));
    localStorage.setItem("code-model", model);
    localStorage.setItem("code-permission-profile", "plan");
  }, { key: host.syntheticKey, token: host.platformToken, model: MODEL_ID });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      await route.abort("blockedbyclient");
      return;
    }
    if (url.pathname === "/proxy/models") {
      await route.continue({
        headers: { ...route.request().headers(), "x-base-url": host.ready.fakeUrl },
      });
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  const pageErrors = [];
  let createResponse = null;
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("response", async (response) => {
    if (response.request().method() === "POST"
        && new URL(response.url()).pathname === "/api/agent/runs") {
      createResponse = { status: response.status(), body: await response.json() };
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
    await page.locator("#baseUrl").evaluate((element, value) => { element.value = value; }, host.ready.fakeUrl);
    await waitFor(
      () => page.evaluate(() => window.__h4CompletionProtocol === "canonical-v1"),
      `${runtime} canonical Skill capability was not observed`,
    );
    await page.locator("#prompt").fill(`/${SKILL_NAME} ${USER_MARKER}`);
    await page.locator("#sendBtn").click();
    await waitFor(() => createResponse, `${runtime} AgentRun create response was not observed`);
    assert.equal(createResponse.status, 201);
    await host.releaseModel();
    await page.locator("#messages article.msg.assistant").filter({ hasText: FINAL })
      .waitFor({ state: "visible", timeout: 15_000 });

    const runId = String(createResponse.body?.agentRunId || "");
    const record = await readTerminalRecord(host, runId);
    assert.equal(record.status, "completed");
    assert.equal(record.result.content, FINAL);
    assert.equal(record.skillCompletionEnforcement.phase, "passed");
    assert.equal(record.skillOutcome.aggregateState, "satisfied");
    assert.equal(record.rounds.length, 3);
    assert.equal(record.rounds[0].content, CANDIDATE);
    assert.deepEqual(Object.keys(record.toolExecutions), ["h4-skill-completion-read"]);
    assert.equal(Object.hasOwn(createResponse.body, "skillCompletionEnforcement"), false);
    assert.deepEqual(pageErrors, []);

    const chats = (await host.metrics()).chatRequests.slice(before);
    assert.deepEqual(chats.map((item) => item.scenario), [
      "skill-completion-candidate",
      "skill-completion-call",
      "skill-completion-final",
    ]);
    assert.deepEqual(chats[1].skillCompletion.tools, ["read_file"]);
    assert.equal(chats[1].skillCompletion.continuing, true);
    assert.deepEqual(chats[2].skillCompletion.tools, []);
    assert.equal(chats[2].skillCompletion.finalizing, true);
    return { runtime, runId, rounds: record.rounds.length, terminalStatus: record.status };
  } finally {
    await page.close();
    await context.close();
  }
}

async function main() {
  const host = await startIsolatedHost({
    disableRoutingV2: true,
    enableSkillActivation: true,
    enableSkillCompletion: true,
  });
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    await installSkill(host);
    browser = await chromium.launch({ headless: true });
    const runs = [];
    for (const runtime of ["bundle", "classic"]) {
      runs.push(await exercise(browser, host, runtime));
    }
    result = { ok: true, command: "code074-skill-completion-selfcheck", runs };
  } finally {
    if (browser) await browser.close();
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
  }
  result.cleanup = { rootRemoved: cleanup.rootRemoved, activeChildCount: getActiveChildCount() };
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
