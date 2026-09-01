const assert = require("node:assert/strict");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const STARTUP_FIXTURES = Object.freeze({
  "/api/image-routes/refresh": Object.freeze({
    version: 1,
    catalogRevision: 0,
    routes: [],
    ok: true,
    changed: false,
    successfulConnections: 0,
    failedConnections: 0,
    failures: [],
  }),
  "/api/code/sync-keys": Object.freeze({ tokens: [], keys: {} }),
});

function createAudit() {
  return { initiated: [], fulfilled: [], serverBound: [], blockedWrites: [], blockedExternal: [] };
}

async function installNetworkFence(context, runtime, audit) {
  context.on("request", (request) => {
    const url = new URL(request.url());
    audit.initiated.push({ runtime, method: request.method(), path: url.pathname, hostname: url.hostname });
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const fixture = method === "POST" ? STARTUP_FIXTURES[url.pathname] : null;
    if (fixture) {
      audit.fulfilled.push({ runtime, method, path: url.pathname });
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) });
      return;
    }
    const local = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
    if (!local) {
      audit.blockedExternal.push({ runtime, method, path: url.pathname, hostname: url.hostname });
      await route.abort("blockedbyclient");
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      audit.blockedWrites.push({ runtime, method, path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    audit.serverBound.push({ runtime, method, path: url.pathname });
    await route.continue();
  });
}

async function createContext(browser, host, runtime, audit) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await installNetworkFence(context, runtime, audit);
  await context.addInitScript(({ platformToken, language, theme }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    localStorage.setItem("code-key-config", "[]");
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken,
      userId: "53",
      username: "skill-model-reminder-selfcheck",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", language);
    localStorage.setItem("code-theme-mode", theme);
    localStorage.removeItem("code-model");
    localStorage.removeItem("code-model-route-ref");
  }, {
    platformToken: host.platformToken,
    language: runtime === "bundle" ? "zh" : "en",
    theme: runtime === "bundle" ? "dark" : "light",
  });
  return context;
}

async function waitForRuntime(page, runtime) {
  await page.waitForFunction((expectedRuntime) => {
    const root = document.documentElement;
    return root.getAttribute("data-frontend-runtime") === expectedRuntime
      && root.getAttribute("data-code-phase-one-shell-ready") === "true"
      && (expectedRuntime !== "bundle" || root.getAttribute("data-code-frontend-ready") === "true");
  }, runtime === "bundle" ? "bundle" : "classic-fallback");
}

async function installTraceProjection(page, runtime) {
  return page.evaluate((runtimeName) => {
    const createMessagesFeature = window.Code?.ui?.messages?.createMessagesFeature;
    if (typeof createMessagesFeature !== "function") throw new Error("messages feature unavailable");
    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
    const names = runtimeName === "bundle" ? ["imagegen"] : ["documents", "pdf"];
    let messages = [
      { role: "user", content: "trace fixture", meta: { activeSkillNames: names } },
      { role: "assistant", content: "inspect", meta: { toolCalls: [{ id: "call-1", function: { name: "read_file", arguments: "{}" } }] } },
      { role: "tool-call", content: "", meta: { action: "read_file", toolCallId: "call-1" } },
      { role: "tool-result", content: "ok", meta: { action: "read_file", toolCallId: "call-1", outcome: "completed", result: { ok: true } } },
      { role: "assistant", content: "done", _responseTime: "2s" },
    ];
    const feature = createMessagesFeature({
      escapeHtml,
      formatCompact: (value) => String(value),
      renderMarkdown: (value) => `<p>${escapeHtml(value)}</p>`,
      t: (key, vars = {}) => key === "executionTraceSkillsAria"
        ? `${runtimeName === "bundle" ? "已启用 Skill" : "Enabled Skills"}: ${vars.names}`
        : key,
      getMessageText: (message) => String(message?.content || ""),
      getBackgroundJob: () => null,
      getMessages: () => messages,
      getSessionId: () => "h4-skill-trace",
      getSelectedModel: () => "fixture-model",
      renderNetworkRecoveryStatus: () => "",
      renderAssistantContent: (value) => `<p>${escapeHtml(value)}</p>`,
      renderBranchFlow: () => "",
      isEditSuggestionMessage: () => false,
      renderEditSuggestion: () => "",
      getToolActionLabel: (action) => action,
    });
    document.querySelector(".chat-pane")?.classList.remove("empty-chat");
    document.getElementById("messageList").innerHTML = feature.projectMessages(messages, { hasActiveRun: false });
    return { names };
  }, runtime);
}

async function exerciseRuntime(browser, host, runtime, audit) {
  const context = await createContext(browser, host, runtime, audit);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await waitForRuntime(page, runtime);

    const prompt = page.locator("#prompt");
    const sessionCountBefore = await page.locator("#sessionList .session-row").count();
    await prompt.fill("draft must remain");
    const sendButton = page.locator("#sendBtn");
    assert.equal(await sendButton.isEnabled(), true);
    await sendButton.click();
    const expectedReminder = runtime === "bundle"
      ? "未找到可用模型，请检查 API Key"
      : "No available models found. Check your API Key.";
    const toast = page.locator("#toastContainer .toast.warning").filter({ hasText: expectedReminder });
    await toast.waitFor({ state: "visible" });
    assert.equal(await prompt.inputValue(), "draft must remain");
    assert.equal(await page.locator("#sessionList .session-row").count(), sessionCountBefore);

    const projection = await installTraceProjection(page, runtime);
    const summary = page.locator(".execution-trace-summary");
    const chip = page.locator(".execution-trace-skill-chip");
    const expectedChip = `Skill · ${projection.names[0]}${projection.names.length > 1 ? ` +${projection.names.length - 1}` : ""}`;
    assert.equal(await chip.textContent(), expectedChip);
    const accessible = await chip.getAttribute("aria-label");
    for (const name of projection.names) assert.equal(accessible.includes(name), true);
    const geometry = await page.evaluate(() => {
      const rect = (selector) => {
        const box = document.querySelector(selector).getBoundingClientRect();
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height };
      };
      const status = rect(".completed-run-status");
      const skill = rect(".execution-trace-skill-chip");
      const chevron = rect(".execution-trace-chevron");
      const style = getComputedStyle(document.querySelector(".execution-trace-skill-chip"));
      return {
        status,
        skill,
        chevron,
        overflow: style.overflow,
        textOverflow: style.textOverflow,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        viewportWidth: innerWidth,
      };
    });
    assert.equal(geometry.status.right <= geometry.skill.left + 1, true);
    assert.equal(geometry.skill.right <= geometry.chevron.left + 1, true);
    assert.equal(geometry.skill.height >= 20, true);
    assert.equal(geometry.overflow, "hidden");
    assert.equal(geometry.textOverflow, "ellipsis");
    assert.equal(geometry.documentWidth <= geometry.viewportWidth, true);
    assert.equal(geometry.bodyWidth <= geometry.viewportWidth, true);

    await summary.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(".execution-trace").evaluate((element) => element.classList.contains("is-expanded")), true);
    assert.equal(await summary.getAttribute("aria-expanded"), "true");
    await page.keyboard.press("Space");
    assert.equal(await page.locator(".execution-trace").evaluate((element) => element.classList.contains("is-expanded")), false);
    assert.equal(await summary.getAttribute("aria-expanded"), "false");
    assert.deepEqual(pageErrors, []);
    return { runtime, expectedReminder, draftPreserved: true, projection, geometry, keyboardFold: true };
  } finally {
    await page.close();
    await context.close();
  }
}

function startupIsolation(audit) {
  const result = {};
  for (const runtime of ["bundle", "classic"]) {
    result[runtime] = {};
    for (const pathname of Object.keys(STARTUP_FIXTURES)) {
      const initiated = audit.initiated.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      const fulfilled = audit.fulfilled.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      const serverReceived = audit.serverBound.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      assert.equal(initiated.length, 1);
      assert.equal(fulfilled.length, 1);
      assert.deepEqual(serverReceived, []);
      result[runtime][pathname] = { initiated: 1, fulfilled: 1, serverReceived: 0 };
    }
  }
  return result;
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true });
  const audit = createAudit();
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    const before = await host.metrics();
    browser = await chromium.launch({ headless: true });
    const bundle = await exerciseRuntime(browser, host, "bundle", audit);
    const classic = await exerciseRuntime(browser, host, "classic", audit);
    const after = await host.metrics();
    assert.deepEqual(audit.blockedWrites, []);
    assert.equal(after.chatRequests.length - before.chatRequests.length, 0);
    assert.equal(after.toolExecutions.length - before.toolExecutions.length, 0);
    assert.equal(after.modelRouteRequests.length - before.modelRouteRequests.length, 0);
    assert.equal(after.production.agentRuns.length - before.production.agentRuns.length, 0);
    assert.equal(after.production.runtimeRuns.length - before.production.runtimeRuns.length, 0);
    result = {
      ok: true,
      command: "execution-trace-skill-model-reminder-selfcheck",
      runtimes: [bundle, classic],
      startupIsolation: startupIsolation(audit),
      sideEffects: { agentRuns: 0, runtimeRuns: 0, chat: 0, tools: 0, modelRoutes: 0, writes: 0 },
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
