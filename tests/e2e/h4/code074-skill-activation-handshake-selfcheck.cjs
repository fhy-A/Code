const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const MODEL_ID = "h4-e2e-model";
const SKILL_NAME = "h4-canonical";
const SKILL_BODY = "H4_CANONICAL_SKILL_BODY";
const USER_MARKER = "H4_PLAIN_USER";
const FINAL_MARKER = "H4_PLAIN_FINAL";
const SKILL_MARKER = "[[CODE_SKILL_ACTIVATION_CANONICAL_V1]]";
const DELEGATION_BEGIN = "[[CODE_TASK_DELEGATION_CANONICAL_V1_BEGIN]]";
const DELEGATION_END = "[[CODE_TASK_DELEGATION_CANONICAL_V1_END]]";

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function count(value, marker) {
  return String(value || "").split(marker).length - 1;
}

async function waitFor(check, message, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await delay(40);
  }
  throw new Error(message);
}

async function installSkillFixture(host) {
  const directory = path.join(host.dataDir, "skills", SKILL_NAME);
  await fs.mkdir(directory, { recursive: true });
  await fs.writeFile(path.join(directory, "SKILL.md"), [
    "---",
    `name: ${SKILL_NAME}`,
    "description: H4 canonical activation handshake fixture",
    "keywords: h4+canonical+activation",
    "tools: read_file",
    "---",
    "",
    SKILL_BODY,
    "",
  ].join("\n"), "utf8");
}

function activeSkillNamesFromMessages(messages) {
  for (const message of messages || []) {
    if (message?.role === "user" && Array.isArray(message?.meta?.activeSkillNames)) {
      return [...message.meta.activeSkillNames];
    }
  }
  return [];
}

async function readRunRecord(host, agentRunId) {
  assert.match(agentRunId, /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);
  const target = path.join(host.dataDir, "agent-runs", `${agentRunId}.json`);
  return waitFor(async () => {
    try {
      const record = JSON.parse(await fs.readFile(target, "utf8"));
      return ["completed", "failed", "cancelled"].includes(record.status) ? record : null;
    } catch {
      return null;
    }
  }, `AgentRun record did not become terminal: ${agentRunId}`);
}

function createAudit(runtime) {
  return {
    runtime,
    sequence: 0,
    agentRequests: [],
    agentResponses: [],
    sessionWrites: [],
    fullSkillReads: [],
    network: [],
    blockedExternal: [],
    pageErrors: [],
  };
}

async function createContext(browser, host, runtime, audit) {
  const context = await browser.newContext({
    viewport: { width: 1200, height: 760 },
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await context.addInitScript(({ syntheticKey, platformToken, modelId, language }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    window.__h4SkillHeartbeats = [];
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      const input = args[0];
      const rawUrl = input instanceof Request ? input.url : String(input || "");
      if (new URL(rawUrl, location.href).pathname === "/api/browser-heartbeat") {
        response.clone().json().then((body) => {
          window.__h4SkillHeartbeats.push(String(body?.skillActivationProtocol || ""));
        }).catch(() => {});
      }
      return response;
    };
    localStorage.setItem("code-key-config", JSON.stringify([{
      name: "H4 synthetic",
      key: syntheticKey,
      enabled: true,
      source: "manual",
    }]));
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken,
      userId: "7",
      username: "h4-user",
    }));
    localStorage.setItem("code-model", modelId);
    localStorage.setItem("code-permission-profile", "plan");
    localStorage.setItem("code-lang", language);
  }, {
    syntheticKey: host.syntheticKey,
    platformToken: host.platformToken,
    modelId: MODEL_ID,
    language: runtime === "bundle" ? "zh" : "en",
  });

  context.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/proxy/")) {
      audit.network.push({ phase: "request", method: request.method(), path: url.pathname });
    }
    if (request.method() === "GET" && url.pathname === `/api/skills/${SKILL_NAME}`) {
      audit.fullSkillReads.push({ sequence: ++audit.sequence });
      return;
    }
    if (request.method() === "POST" && url.pathname === "/api/agent/runs") {
      audit.agentRequests.push({
        sequence: ++audit.sequence,
        body: request.postDataJSON(),
      });
      return;
    }
    if (request.method() === "PUT" && /^\/api\/sessions\/[^/]+$/.test(url.pathname)) {
      const body = request.postDataJSON();
      audit.sessionWrites.push({
        sequence: ++audit.sequence,
        runState: body?.runState || {},
        activeSkillNames: activeSkillNamesFromMessages(body?.messages),
      });
    }
  });
  context.on("response", (response) => {
    const request = response.request();
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/proxy/")) {
      const entry = { phase: "response", method: request.method(), path: url.pathname, status: response.status() };
      audit.network.push(entry);
      if (url.pathname === "/api/model-routes/refresh") {
        response.json().then((body) => { entry.body = body; }).catch(() => {});
      }
    }
    if (request.method() !== "POST" || url.pathname !== "/api/agent/runs") return;
    const sequence = ++audit.sequence;
    response.json().then((body) => {
      audit.agentResponses.push({ sequence, status: response.status(), body });
    }).catch((error) => {
      audit.pageErrors.push(`AgentRun response parse failed: ${error.message}`);
    });
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      audit.blockedExternal.push({ method: request.method(), hostname: url.hostname, path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    if (url.pathname === "/proxy/models") {
      await route.continue({
        headers: { ...request.headers(), "x-base-url": host.ready.fakeUrl },
      });
      return;
    }
    await route.continue();
  });
  return context;
}

async function waitForRuntime(page, runtime, audit) {
  await page.waitForFunction((expectedRuntime) => {
    const root = document.documentElement;
    return root.getAttribute("data-frontend-runtime") === expectedRuntime
      && root.getAttribute("data-code-phase-one-shell-ready") === "true"
      && (expectedRuntime !== "bundle" || root.getAttribute("data-code-frontend-ready") === "true");
  }, runtime === "bundle" ? "bundle" : "classic-fallback");
  await page.locator("#modelPillBtn").waitFor({ state: "visible" });
  try {
    await waitFor(
      async () => (await page.locator("#modelPillBtn").getAttribute("data-model")) === MODEL_ID,
      `${runtime} model catalog was not ready`,
    );
  } catch (error) {
    error.message += `; network=${JSON.stringify(audit.network)}`;
    throw error;
  }
}

function assertCanonicalRequest(request) {
  const body = request.body;
  assert.deepEqual(Object.keys(body.skillActivationRequest).sort(), [
    "disabledNames", "explicitSkill", "schemaVersion",
  ]);
  assert.deepEqual(body.skillActivationRequest, {
    schemaVersion: 1,
    explicitSkill: SKILL_NAME,
    disabledNames: [],
  });
  assert.deepEqual(Object.keys(body.allowedTools).sort(), ["names", "schemaVersion"]);
  assert.equal(body.allowedTools.schemaVersion, 1);
  assert.equal(body.allowedTools.names.includes("read_file"), true);
  assert.equal(body.allowedTools.names.includes("task"), true);
  assert.equal(Object.hasOwn(body, "activeSkillName"), false);
  assert.equal(Object.hasOwn(body, "activeSkillNames"), false);
  const system = String(body.payload?.messages?.[0]?.content || "");
  assert.equal(count(system, SKILL_MARKER), 1);
  assert.equal(count(system, DELEGATION_BEGIN), 1);
  assert.equal(count(system, DELEGATION_END), 1);
  assert.equal(system.includes(SKILL_BODY), false);
}

function assertConsumedRun(record) {
  assert.deepEqual(record.activeSkillNames, [SKILL_NAME]);
  const system = String(record.messages?.[0]?.content || "");
  assert.equal(count(system, SKILL_MARKER), 0);
  assert.equal(count(system, DELEGATION_BEGIN), 0);
  assert.equal(count(system, DELEGATION_END), 0);
  assert.equal(count(system, SKILL_BODY), 1);
  const tools = (record.tools || []).map((tool) => String(tool?.function?.name || ""));
  assert.equal(tools.includes("read_file"), true);
  assert.equal(tools.includes("task"), false);
}

function assertLegacyRequest(request) {
  const body = request.body;
  assert.equal(Object.hasOwn(body, "skillActivationRequest"), false);
  assert.equal(Array.isArray(body.allowedTools), true);
  assert.deepEqual(body.activeSkillNames, [SKILL_NAME]);
  assert.equal(body.activeSkillName, SKILL_NAME);
  const system = String(body.payload?.messages?.[0]?.content || "");
  assert.equal(count(system, SKILL_MARKER), 0);
  assert.equal(count(system, DELEGATION_BEGIN), 0);
  assert.equal(count(system, DELEGATION_END), 0);
  assert.equal(count(system, SKILL_BODY), 1);
}

async function exercise(browser, host, runtime, canonical) {
  const audit = createAudit(runtime);
  const context = await createContext(browser, host, runtime, audit);
  const page = await context.newPage();
  page.on("pageerror", (error) => audit.pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await waitForRuntime(page, runtime, audit);
    await waitFor(() => audit.network.some((entry) => (
      entry.phase === "response"
      && entry.path === "/api/skills"
      && entry.status === 200
    )), `${runtime} Skill catalog was not loaded`);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
      element.value = fakeUrl;
    }, host.ready.fakeUrl);
    await waitFor(
      () => page.evaluate(() => window.__h4SkillHeartbeats.length > 0),
      `${runtime} heartbeat was not observed`,
    );
    const heartbeat = await page.evaluate(() => window.__h4SkillHeartbeats.at(-1));
    assert.equal(heartbeat, canonical ? "canonical-v1" : "");

    const submitBoundary = audit.sequence;
    await page.locator("#prompt").fill(`/${SKILL_NAME} ${USER_MARKER}`);
    await page.locator("#sendBtn").click();
    await waitFor(() => audit.agentRequests.length === 1, `${runtime} AgentRun create was not observed`);
    await waitFor(() => audit.agentResponses.length === 1, `${runtime} AgentRun response was not observed`);
    await host.releaseModel();
    await page.locator("#messages article.msg.assistant").filter({ hasText: FINAL_MARKER })
      .waitFor({ state: "visible", timeout: 15_000 });

    assert.equal(audit.agentRequests.length, 1);
    assert.equal(audit.agentResponses.length, 1);
    assert.equal(audit.agentResponses[0].status, 201);
    const agentRunId = String(audit.agentResponses[0].body?.agentRunId || "");
    const record = await readRunRecord(host, agentRunId);
    if (canonical) {
      assertCanonicalRequest(audit.agentRequests[0]);
      assert.deepEqual(audit.agentResponses[0].body.activeSkillNames, [SKILL_NAME]);
      assert.equal(audit.fullSkillReads.filter((item) => item.sequence > submitBoundary).length, 0);
      assertConsumedRun(record);
      const firstRunCheckpoint = audit.sessionWrites.find((entry) => (
        String(entry.runState?.status || "") === "running"
      ));
      assert.ok(firstRunCheckpoint, "canonical running checkpoint was not persisted");
      assert.equal(firstRunCheckpoint.sequence > audit.agentResponses[0].sequence, true);
      assert.equal(firstRunCheckpoint.runState.agentRunId, agentRunId);
      assert.deepEqual(firstRunCheckpoint.activeSkillNames, [SKILL_NAME]);
    } else {
      assertLegacyRequest(audit.agentRequests[0]);
      assert.equal(Object.hasOwn(audit.agentResponses[0].body, "activeSkillNames"), false);
      assert.equal(audit.fullSkillReads.filter((item) => item.sequence > submitBoundary).length, 1);
      assert.deepEqual(record.activeSkillNames, [SKILL_NAME]);
    }
    const expectedStaticPaths = new Set([
      "/npm/katex@0.16.11/dist/katex.min.css",
      "/npm/katex@0.16.11/dist/katex.min.js",
      "/npm/marked/marked.min.js",
    ]);
    assert.equal(audit.blockedExternal.every((entry) => (
      entry.hostname === "cdn.jsdelivr.net" && expectedStaticPaths.has(entry.path)
    )), true);
    assert.deepEqual(audit.pageErrors, []);
    return {
      runtime,
      protocol: canonical ? "canonical-v1" : "legacy",
      createPosts: audit.agentRequests.length,
      fullSkillReads: audit.fullSkillReads.filter((item) => item.sequence > submitBoundary).length,
      activeSkillNames: record.activeSkillNames || [],
      terminalStatus: record.status,
      blockedStaticAssets: audit.blockedExternal.length,
    };
  } finally {
    await page.close();
    await context.close();
  }
}

async function main() {
  const host = await startIsolatedHost({
    disableRoutingV2: true,
    enableSkillActivation: true,
  });
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    await installSkillFixture(host);
    const skillCatalogResponse = await fetch(new URL("/api/skills?brief=1", host.ready.codeUrl));
    const skillCatalog = await skillCatalogResponse.json();
    assert.equal(
      (skillCatalog.data || []).some((skill) => skill?.name === SKILL_NAME),
      true,
      `H4 Skill fixture is unavailable: ${JSON.stringify(skillCatalog)}`,
    );
    browser = await chromium.launch({ headless: true });
    const canonical = [];
    for (const runtime of ["bundle", "classic"]) {
      canonical.push(await exercise(browser, host, runtime, true));
    }
    const restart = await host.restartGeneration({
      disableRoutingV2: true,
      enableSkillActivation: false,
    });
    assert.equal(restart.previousCleanup.childExited, true);
    assert.deepEqual(restart.previousCleanup.portsClosed, [true, true]);
    const legacy = [];
    for (const runtime of ["bundle", "classic"]) {
      legacy.push(await exercise(browser, host, runtime, false));
    }
    result = {
      ok: true,
      command: "code074-skill-activation-handshake-selfcheck",
      canonical,
      legacy,
      generations: 2,
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
