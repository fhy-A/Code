const assert = require("node:assert/strict");
const { chromium, expect } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const CLASSIC_PATH = "/dist/frontend/index.classic.html";
const VIEWPORT = Object.freeze({ width: 1280, height: 800 });
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
const LONG_PATH = `src/${"deeply-nested-folder/".repeat(18)}final-result.json`;

function createAudit() {
  return {
    initiated: [],
    startupFulfilled: [],
    serverBound: [],
    blockedExternal: [],
    blockedWrites: [],
  };
}

async function installNetworkFence(context, runtime, audit) {
  context.on("request", (request) => {
    const url = new URL(request.url());
    audit.initiated.push({ runtime, method: request.method(), hostname: url.hostname, path: url.pathname });
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const startup = method === "POST" ? STARTUP_FIXTURES[url.pathname] : null;
    if (startup) {
      audit.startupFulfilled.push({ runtime, method, path: url.pathname, fulfilled: true });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(startup),
      });
      return;
    }
    const local = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
    if (!local) {
      audit.blockedExternal.push({ runtime, method, hostname: url.hostname, path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      audit.blockedWrites.push({ runtime, method, path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    audit.serverBound.push({ runtime, method, hostname: url.hostname, path: url.pathname });
    await route.continue();
  });
}

async function createContext(browser, host, runtime, audit) {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await installNetworkFence(context, runtime, audit);
  await context.addInitScript(({ platformToken }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    localStorage.setItem("code-key-config", "[]");
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken,
      userId: "43",
      username: "code043-compact-disclosures-final-state",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", "en");
    localStorage.setItem("code-theme-mode", "light");
    localStorage.removeItem("code-sidebar-hidden");
  }, { platformToken: host.platformToken });
  await context.addInitScript(() => {
    window.Code = { core: {}, features: {}, services: {}, agent: {}, ui: {} };
    let sessionsApi;
    Object.defineProperty(Code.features, "sessions", {
      configurable: true,
      get: () => sessionsApi,
      set(api) {
        sessionsApi = Object.freeze({ ...api, createSessionNavigation(options) {
          window.__code058 = options;
          return api.createSessionNavigation(options);
        }});
      },
    });
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

// Capture existing navigation callbacks at module registration. Product code and
// bundle/classic scripts are served unchanged; all decision writes are fulfilled.
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

function request(id, source = "main", tool = "write_file", language = "zh") {
  return {
    id, authorizationId: `authorization-${id}`, agentRunId: `run-${id}`,
    sessionId: "code058-fixture", serverAgent: true,
    sourceKey: source, sourceLabel: source === "main" ? (language === "zh" ? "主 Agent" : "Main Agent") : (language === "zh" ? "子 Agent · 检查文件" : "Sub-agent · Inspect files"),
    tool: { action: tool, path: `src/${"long-directory/".repeat(8)}${id}.js`, command: "echo synthetic-command" },
    editId: tool === "write_file" ? `edit-${id}` : "",
    stats: tool === "write_file" ? { additions: 3, removals: 1 } : null,
    selected: true, status: "pending", detachedBackground: source !== "main",
  };
}

async function installItems(page, items, language = "zh", restore = false) {
  await page.evaluate(({ items, language, restore }) => {
    const fixture = window.__code058;
    fixture.state.sessionId = "code058-fixture";
    fixture.state.lang = language;
    fixture.state.messages = [{ role: "user", content: language === "zh" ? "合成授权展示样本" : "Synthetic authorization sample" }];
    fixture.state.authorizationRequests = [];
    fixture.state.authorizationPanelCollapsed = false;
    for (const item of items) {
      const current = restore ? fixture.recovery.restoreAuthorizationRequest(item.sessionId, item) : item;
      // Existing completion callback avoids starting any model continuation.
      current.resolve = () => {};
      if (!restore) fixture.state.authorizationRequests.push(current);
    }
    fixture.view.renderMessages();
  }, { items, language, restore });
}

async function waitIdle(page) {
  await page.waitForFunction(() => !window.__code058.state.authorizationRequests.some(item => item._finishing));
}

async function exercise(browser, host, runtime, audit, evidenceDir) {
  const context = await createContext(browser, host, runtime, audit);
  const submissions = [];
  const fulfilledSessionWrites = [];
  const pageErrors = [];
  let rejectNext = false;
  let releaseDecision = null;
  let decisionGate = null;
  await context.route("**/*", async route => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "POST" && /^\/api\/agent\/runs\/[^/]+\/authorization$/.test(url.pathname)) {
      submissions.push({ path: url.pathname, ...req.postDataJSON() });
      if (decisionGate) await decisionGate;
      if (rejectNext) {
        rejectNext = false;
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "Synthetic retryable failure" }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, result: {} }) });
      }
      return;
    }
    if (["POST", "PUT"].includes(req.method()) && url.pathname === "/api/sessions/code058-fixture") {
      fulfilledSessionWrites.push(url.pathname);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, revision: 1 }) });
      return;
    }
    await route.fallback();
  });
  const page = await context.newPage();
  page.on("pageerror", e => pageErrors.push(String(e)));
  const panel = page.locator("#authorizationPanel");
  const approve = panel.locator('[data-auth-action="approve"]');
  const reject = panel.locator('[data-auth-action="reject-all"]');
  const matrix = [];
  try {
    await page.goto(new URL(runtime === "bundle" ? "/" : CLASSIC_PATH, host.ready.codeUrl).href);
    await waitForRuntime(page, runtime);
    await page.waitForLoadState("networkidle");
    await page.locator("#toggleSidebar").click();
    await expect(page.locator(".pi-shell")).toHaveClass(/sidebar-hidden/);
    for (const language of ["zh", "en"]) for (const width of [1280, 390]) for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width, height: 800 });
      await page.evaluate(mode => Code.core.theme.activateTheme(mode), theme);
      const scenarios = {
        "single-main": [request("one", "main", "write_file", language)],
        "single-sub": [request("child", "sub:one", "run_command", language)],
        "multi-main": [request("one", "main", "write_file", language), request("two", "main", "run_command", language)],
        mixed: [request("one", "main", "write_file", language), request("child", "sub:one", "run_command", language)],
        background: [request("child", "sub:one", "write_file", language), request("child2", "sub:two", "run_command", language)],
      };
      for (const [scenario, items] of Object.entries(scenarios)) {
        await installItems(page, items, language);
        const single = items.length === 1;
        await expect(panel).toBeVisible();
        await expect(approve).toHaveText(single ? (language === "zh" ? "批准" : "Approve") : `${language === "zh" ? "批准所选" : "Approve selected"} (2)`);
        await expect(reject).toHaveText(single ? (language === "zh" ? "拒绝" : "Reject") : language === "zh" ? "全部拒绝" : "Reject all");
        await expect(panel.locator('[data-auth-select]')).toHaveCount(single ? 0 : 2);
        await expect(panel.locator('.authorization-head-copy > span')).toHaveCount(single ? 0 : 1);
        if (single) await expect(panel.locator('input[type="checkbox"]')).toHaveCount(0);
        if (scenario === "single-sub") await expect(panel.locator('.authorization-source')).toHaveText(items[0].sourceLabel);
        if (scenario === "multi-main") await expect(panel.locator('[data-auth-group="main"]')).toHaveCount(1);
        if (scenario === "mixed" || scenario === "background") await expect(panel.locator('.authorization-group')).toHaveCount(2);
        const geometry = await panel.evaluate(el => ({ width: el.getBoundingClientRect().width, viewport: innerWidth, overflow: el.scrollWidth > el.clientWidth }));
        assert.equal(geometry.overflow, false);
        assert(geometry.width <= width);
        assert(geometry.width >= 300, "Narrow sample must use the chat viewport, not the sidebar-compressed pane");
        for (const checkbox of await panel.locator('input[type="checkbox"]').all()) await expect(checkbox).toHaveAccessibleName(/\S/);
        await approve.focus();
        await page.keyboard.press("Shift+Tab");
        await page.keyboard.press("Tab");
        const focus = await approve.evaluate(el => ({ active: document.activeElement === el, outline: getComputedStyle(el).outlineStyle }));
        assert.equal(focus.active, true); assert.notEqual(focus.outline, "none");
        const name = `${runtime}-${language}-${theme}-${width}-${scenario}`;
        if (runtime === "bundle") await panel.screenshot({ path: path.join(evidenceDir, name + ".png") });
        await panel.locator('.authorization-collapse').click();
        await expect(panel.locator('.authorization-collapsed-bar')).toHaveText(single ? (language === "zh" ? "需要确认›" : "Confirmation required›") : new RegExp(language === "zh" ? "2 项操作" : "2 operations"));
        await panel.locator('.authorization-collapsed-bar').focus();
        await page.keyboard.press("Enter");
        await expect(approve).toBeVisible();
        matrix.push({ scenario, language, width, theme, geometry });
      }
    }

    // Current sole request remains actionable even when it was deselected in a batch.
    const sole = { ...request("sole"), selected: false };
    await installItems(page, [sole]);
    await expect(approve).toBeEnabled();
    decisionGate = new Promise(resolve => { releaseDecision = resolve; });
    const before = submissions.length;
    await approve.click();
    await expect(approve).toBeDisabled(); await expect(reject).toBeDisabled();
    await approve.evaluate(el => el.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await page.waitForFunction(() => window.__code058.state.authorizationRequests[0]?._finishing === true);
    releaseDecision(); decisionGate = null;
    await expect(panel).toBeHidden();
    assert.deepEqual(submissions.slice(before).map(x => [x.authorizationId, x.decision]), [[sole.authorizationId, "approved"]]);

    // Multi-item selections remain explicit; resolving one makes the deselected tail the sole item.
    await installItems(page, [request("a"), { ...request("b", "sub:one"), selected: false }]);
    await approve.click(); await waitIdle(page);
    await expect(approve).toHaveText("批准"); await expect(approve).toBeEnabled();
    await reject.click(); await expect(panel).toBeHidden();
    assert.deepEqual(submissions.slice(-2).map(x => [x.authorizationId, x.decision]), [["authorization-a", "approved"], ["authorization-b", "rejected"]]);

    // Existing group and row controls still select exactly the requested batch members.
    await installItems(page, [request("g1"), request("g2")]);
    await panel.locator('[data-auth-group="main"]').uncheck(); await expect(approve).toBeDisabled();
    await panel.locator('[data-auth-select="g2"]').check();
    await expect(approve).toHaveText("批准所选 (1)");
    await approve.click(); await waitIdle(page);
    assert.equal(submissions.at(-1).authorizationId, "authorization-g2");

    // Stale single buttons cannot act on a new request or a newly arrived batch.
    await installItems(page, [request("old")]);
    const startStale = submissions.length;
    await page.evaluate(items => { const button = document.querySelector('[data-auth-action="approve"]'); window.__code058.state.authorizationRequests = items; button.click(); }, [request("replacement")]);
    assert.equal(submissions.length, startStale);
    await page.evaluate(items => { const button = document.querySelector('[data-auth-action="reject-all"]'); window.__code058.state.authorizationRequests = items; button.click(); }, [request("n1"), request("n2")]);
    assert.equal(submissions.length, startStale);
    await expect(approve).toHaveText("批准所选 (2)");
    await page.evaluate(items => { const button = document.querySelector('[data-auth-action="approve"]'); window.__code058.state.authorizationRequests = items; button.click(); }, [request("back-to-one")]);
    assert.equal(submissions.length, startStale);
    await expect(approve).toHaveText("批准");

    await installItems(page, [request("reject-main"), { ...request("reject-sub", "sub:one"), selected: false }]);
    await reject.click(); await expect(panel).toBeHidden();
    assert.deepEqual(submissions.slice(-2).map(x => [x.authorizationId, x.decision]), [["authorization-reject-main", "rejected"], ["authorization-reject-sub", "rejected"]]);

    // Retry uses the same authorization ID; no selection checkbox is needed.
    await installItems(page, [request("retry", "sub:one", "run_command")]);
    rejectNext = true;
    await approve.click();
    await page.waitForFunction(() => window.__code058.state.authorizationRequests[0]?.error === "Synthetic retryable failure");
    await expect(approve).toBeEnabled(); await expect(reject).toBeEnabled();
    await approve.click(); await expect(panel).toBeHidden();
    assert.deepEqual(submissions.slice(-2).map(x => x.authorizationId), ["authorization-retry", "authorization-retry"]);

    // Reload the real runtime, then invoke its existing saved-request recovery callback.
    await page.reload(); await waitForRuntime(page, runtime);
    await page.waitForLoadState("networkidle");
    await installItems(page, [{ ...request("restored"), selected: false }], "zh", true);
    await expect(approve).toBeEnabled(); await expect(panel.locator('[data-auth-select]')).toHaveCount(0);
    await page.evaluate(() => { const {state,recovery} = window.__code058; recovery.restoreAuthorizationRequest(state.sessionId, { ...state.authorizationRequests[0] }); });
    assert.equal(await page.evaluate(() => window.__code058.state.authorizationRequests.length), 1);
    await reject.click(); await expect(panel).toBeHidden();
    assert.equal(submissions.at(-1).authorizationId, "authorization-restored");
    assert.deepEqual(pageErrors, []);
    return { runtime, matrix, submissions, fulfilledSessionWrites, reloadRecovery: true, duplicateGuard: true, staleSingleGuard: true, failureRetry: true };
  } finally {
    if (releaseDecision) releaseDecision();
    await context.close();
  }
}

async function main() {
  const evidenceDir = await fs.mkdtemp(path.join(os.tmpdir(), "code058-display-"));
  const host = await startIsolatedHost({ disableRoutingV2: true });
  const audit = createAudit();
  let browser;
  let result;
  try {
    const before = await host.metrics();
    browser = await chromium.launch({ headless: true });
    const runtimes = [];
    for (const runtime of ["bundle", "classic"]) runtimes.push(await exercise(browser, host, runtime, audit, evidenceDir));
    const after = await host.metrics();
    assert.equal(after.chatRequests.length - before.chatRequests.length, 0);
    assert.equal(after.toolExecutions.length - before.toolExecutions.length, 0);
    assert.equal(after.production.agentRuns.length - before.production.agentRuns.length, 0);
    assert.equal(after.production.runtimeRuns.length - before.production.runtimeRuns.length, 0);
    assert.equal(after.modelRouteRequests.length - before.modelRouteRequests.length, 0);
    assert.deepEqual(audit.blockedWrites, []);
    result = { ok: true, evidenceDir, runtimes, syntheticDecisionsOnly: true, realToolExecutions: 0, realAgentRuns: 0 };
  } finally {
    if (browser) await browser.close();
    const cleanup = await host.stop();
    assert.equal(cleanup.childExited, true); assert.deepEqual(cleanup.portsClosed, [true,true]);
    assert.equal(cleanup.rootRemoved, true); assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
    if (result) result.cleanup = { childExited: cleanup.childExited, portsClosed: cleanup.portsClosed, rootRemoved: cleanup.rootRemoved, activeChildCount: cleanup.activeChildCount, cleanupErrors: cleanup.cleanupErrors };
    await fs.writeFile(path.join(evidenceDir, "result.json"), JSON.stringify(result || {ok:false,audit}, null, 2));
  }
  const screenshots = (await fs.readdir(evidenceDir)).filter(x => x.endsWith('.png'));
  await fs.writeFile(path.join(evidenceDir, 'index.html'), `<!doctype html><meta charset="utf-8"><title>CODE-058 授权展示验收</title><style>body{font:15px system-ui;margin:24px;background:#eee}select{padding:8px}img{display:block;margin-top:20px;max-width:100%;border:1px solid #aaa}</style><h1>单项与批量授权展示</h1><p>真实 bundle 渲染的合成样本：单主、单子、多主、混合、后台；中英文、深浅主题、窄宽布局。测试审批请求全部由夹具响应，无真实工具副作用。</p><select id="choice" onchange="document.getElementById('preview').src=this.value">${screenshots.map(x=>`<option>${x}</option>`).join('')}</select><img id="preview" src="${screenshots[0]}">`);
  process.stdout.write(JSON.stringify({ok:true,evidenceDir,cases:result.runtimes.reduce((n,x)=>n+x.matrix.length,0),submissions:result.runtimes.map(x=>x.submissions.length),cleanup:result.cleanup})+'\n');
}
main().catch(e=>{console.error(e);process.exitCode=1;});

