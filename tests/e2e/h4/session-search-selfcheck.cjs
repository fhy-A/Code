const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium, expect: playwrightExpect } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const expect = playwrightExpect.configure({ timeout: 8_000 });
const CLASSIC_PATH = "/dist/frontend/index.classic.html";

async function requestJson(codeUrl, pathname, { method = "GET", body } = {}) {
  const response = await fetch(new URL(pathname, codeUrl), {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(5_000),
  });
  const text = await response.text();
  return {
    status: response.status,
    body: text ? JSON.parse(text) : null,
  };
}

async function seedSearchFacts(host) {
  const alphaPath = path.join(host.projectDir, "session-search-alpha");
  const betaPath = path.join(host.projectDir, "session-search-beta");
  await Promise.all([
    fs.mkdir(alphaPath, { recursive: true }),
    fs.mkdir(betaPath, { recursive: true }),
  ]);
  const alphaProject = await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: { path: alphaPath, label: "Search Alpha" },
  });
  const betaProject = await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: { path: betaPath, label: "Search Beta" },
  });
  assert.equal(alphaProject.status, 201);
  assert.equal(betaProject.status, 201);

  const sessions = [];
  for (let index = 0; index < 12; index += 1) {
    const project = index % 2 ? betaProject.body : alphaProject.body;
    const cwd = index % 2 ? betaPath : alphaPath;
    const lastMessageTime = new Date(Date.UTC(2026, 7, 25, 8, index, 0)).toISOString();
    const created = await requestJson(host.ready.codeUrl, "/api/sessions", {
      method: "POST",
      body: {
        title: `Search Shared ${index}`,
        projectId: project.id,
        cwd,
        messages: [{ role: "user", content: `Search seed ${index}`, _time: lastMessageTime }],
        runState: { status: "completed" },
      },
    });
    assert.equal(created.status, 201);
    assert.equal(Date.parse(created.body.lastMessageTime), Date.parse(lastMessageTime));
    sessions.push(created.body);
  }

  const archivedCreated = await requestJson(host.ready.codeUrl, "/api/sessions", {
    method: "POST",
    body: {
      title: "Archived Hidden Needle",
      projectId: alphaProject.body.id,
      cwd: alphaPath,
      messages: [{
        role: "user",
        content: "Archived search seed",
        _time: "2026-08-25T09:00:00Z",
      }],
      runState: { status: "completed" },
    },
  });
  assert.equal(archivedCreated.status, 201);
  const archived = await requestJson(
    host.ready.codeUrl,
    `/api/session-archive/${encodeURIComponent(archivedCreated.body.id)}/archive`,
    { method: "POST", body: {} },
  );
  assert.equal(archived.status, 200);

  return Object.freeze({
    sessions,
    archived: archivedCreated.body,
    projectLabels: [alphaProject.body.label, betaProject.body.label],
  });
}

async function readSessionFacts(host, seed) {
  const [active, archived] = await Promise.all([
    requestJson(host.ready.codeUrl, "/api/sessions"),
    requestJson(host.ready.codeUrl, "/api/session-archive"),
  ]);
  assert.equal(active.status, 200);
  assert.equal(archived.status, 200);
  const expectedIds = new Set(seed.sessions.map((session) => session.id));
  return {
    active: active.body.data
      .filter((session) => expectedIds.has(session.id))
      .map((session) => ({
        id: session.id,
        title: session.title,
        projectId: session.projectId,
        lastMessageTime: session.lastMessageTime,
        runState: session.runState || {},
      }))
      .sort((left, right) => left.id.localeCompare(right.id)),
    archived: archived.body.data
      .filter((session) => session.id === seed.archived.id)
      .map((session) => ({
        id: session.id,
        title: session.title,
        projectId: session.projectId,
        archivedAt: session.archivedAt,
      })),
  };
}

function observeRequests(context, evidence) {
  context.on("request", (request) => {
    const url = new URL(request.url());
    evidence.push({ method: request.method(), hostname: url.hostname, path: url.pathname });
  });
}

async function configureContext(browser, host, requests, blockedRequests) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  observeRequests(context, requests);
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      blockedRequests.push({ method: route.request().method(), path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
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
      userId: "7",
      username: "h4-user",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", "en");
  }, { platformToken: host.platformToken });
  return context;
}

async function assertRuntimeEntry(page, runtime) {
  const expected = runtime === "bundle" ? "bundle" : "classic-fallback";
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", expected);
  if (runtime === "classic") {
    assert.equal(new URL(page.url()).pathname, CLASSIC_PATH);
    assert.equal(await page.locator("html").getAttribute("data-code-frontend-ready"), null);
  }
}

async function exerciseSearchRuntime({ browser, host, seed, runtime, requests, blockedRequests }) {
  const context = await configureContext(browser, host, requests, blockedRequests);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL(CLASSIC_PATH, host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    const sessionCatalogResponse = page.waitForResponse((response) => {
      const request = response.request();
      const url = new URL(response.url());
      return request.method() === "GET"
        && url.pathname === "/api/sessions"
        && response.status() === 200;
    }, { timeout: 8_000 });
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await assertRuntimeEntry(page, runtime);
    const sessionCatalog = await (await sessionCatalogResponse).json();
    const catalogIds = (Array.isArray(sessionCatalog?.data) ? sessionCatalog.data : [])
      .map((session) => String(session?.id || ""))
      .filter(Boolean);
    assert.equal(catalogIds.length, 12);
    assert.deepEqual(new Set(catalogIds), new Set(seed.sessions.map((session) => session.id)));
    await expect(page.locator("#platformAuthGate")).toHaveCount(0);

    const trigger = page.locator("#sessionSearchBtn");
    const modal = page.locator("#sessionSearchModal");
    const dialog = page.locator("#sessionSearchModal .session-search-dialog");
    const input = page.locator("#sessionSearchInput");
    const close = page.locator("#sessionSearchClose");
    const rows = page.locator("#sessionSearchResults .session-search-result");
    await expect(trigger).toBeVisible();

    await trigger.click();
    await expect(modal).toBeVisible();
    await expect(input).toBeFocused();
    await expect(rows).toHaveCount(10);
    await expect(rows.locator(".session-search-result-title")).toHaveText(
      seed.sessions.slice(2).reverse().map((session) => session.title),
    );
    await expect(rows.locator(".session-search-status")).toHaveText(Array(10).fill("Idle"));
    assert.deepEqual(
      new Set(await rows.locator(".session-search-result-project").allTextContents()),
      new Set(seed.projectLabels),
    );

    await input.fill("shared");
    await expect(rows).toHaveCount(12);
    await input.fill(seed.sessions[10].id.slice(0, 8).toUpperCase());
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText(seed.sessions[10].title);
    await input.fill(seed.sessions[10].id.toUpperCase());
    await expect(rows).toHaveCount(1);
    await input.fill("sEaRcH sHaReD 3");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("Search Shared 3");
    await input.fill("Archived Hidden Needle");
    await expect(rows).toHaveCount(0);
    await expect(page.locator("#sessionSearchResults"))
      .toContainText("No matching unarchived sessions");
    await input.fill("does-not-exist");
    await expect(rows).toHaveCount(0);
    await input.fill("");
    await expect(rows).toHaveCount(10);

    await input.press("Shift+Tab");
    await expect(close).toBeFocused();
    await close.press("Shift+Tab");
    await expect(rows.last()).toBeFocused();
    await rows.last().press("Tab");
    await expect(close).toBeFocused();
    await close.press("Tab");
    await expect(input).toBeFocused();
    await input.press("ArrowDown");
    await expect(rows.first()).toBeFocused();
    await rows.first().press("ArrowDown");
    await expect(rows.nth(1)).toBeFocused();
    await rows.nth(1).press("ArrowUp");
    await expect(rows.first()).toBeFocused();
    await rows.first().press("ArrowUp");
    await expect(input).toBeFocused();

    const navigationTarget = runtime === "bundle" ? seed.sessions[11] : seed.sessions[10];
    await input.fill(navigationTarget.title);
    await expect(rows).toHaveCount(1);
    const navigationResponse = page.waitForResponse((response) => {
      const request = response.request();
      const url = new URL(response.url());
      return request.method() === "GET"
        && url.pathname === `/api/sessions/${navigationTarget.id}`
        && response.status() === 200;
    }, { timeout: 8_000 });
    if (runtime === "bundle") await input.press("Enter");
    else await rows.first().click();
    await navigationResponse;
    await expect(modal).toBeHidden();
    await expect(page.locator(
      `#sessionList .session-row.active[data-session-id="${navigationTarget.id}"]`,
    )).toHaveCount(1);
    await expect(page.locator("#sessionTitle")).toHaveValue(navigationTarget.title);

    await trigger.click();
    await input.fill("");
    await input.press("ArrowDown");
    await expect(rows.first()).toBeFocused();
    await rows.first().press("ArrowUp");
    await expect(input).toBeFocused();
    await input.press("Escape");
    await expect(modal).toBeHidden();
    await expect(trigger).toBeFocused();

    await trigger.click();
    await input.press("Escape");
    await expect(modal).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await close.click();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await modal.click({ position: { x: 3, y: 3 } });
    await expect(modal).toBeHidden();
    await expect(trigger).toBeFocused();

    await page.setViewportSize({ width: 390, height: 844 });
    await trigger.click();
    const narrow = await dialog.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const results = document.querySelector("#sessionSearchResults");
      return {
        left: bounds.left,
        right: bounds.right,
        viewport: window.innerWidth,
        horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
        bodyOverflow: getComputedStyle(document.body).overflow,
        resultsOverflowY: getComputedStyle(results).overflowY,
      };
    });
    assert.equal(narrow.left >= 0, true);
    assert.equal(narrow.right <= narrow.viewport, true);
    assert.equal(narrow.horizontalOverflow, false);
    assert.match(narrow.bodyOverflow, /hidden/);
    assert.equal(narrow.resultsOverflowY, "auto");
    await input.press("Escape");
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.locator("#settingsMenuBtn").click();
    await page.locator('#settingsNav [data-panel="archives"]').click();
    const archivedInput = page.locator("#archivedSessionSearchInput");
    const archivedRows = page.locator(".archived-session-row");
    await expect(archivedInput).toBeVisible();
    await expect(archivedRows).toHaveCount(1);
    await expect(archivedRows.first()).toContainText(seed.archived.title);
    await expect(archivedRows.first()).toContainText("Search Alpha");
    await expect(archivedRows.first().locator(".archived-session-restore")).toHaveCount(1);
    await expect(archivedRows.first().locator(".archived-session-delete")).toHaveCount(1);
    await archivedInput.fill("Search Shared");
    await expect(archivedRows).toHaveCount(0);
    await expect(page.locator(".archived-sessions-content"))
      .toContainText("No matching archived sessions");
    await archivedInput.fill("hidden needle");
    await expect(archivedRows).toHaveCount(1);
    await archivedInput.fill(seed.archived.id.slice(0, 8).toUpperCase());
    await expect(archivedRows).toHaveCount(1);
    await archivedInput.fill(seed.archived.id.toUpperCase());
    await expect(archivedRows).toHaveCount(1);
    await archivedInput.fill("");
    await expect(page.locator(".archived-session-group h4")).toHaveText(["Search Alpha"]);

    await page.locator('[data-settings-lang="zh"]').click();
    await expect(archivedInput).toHaveAttribute("placeholder", "搜索归档标题或会话 ID…");
    await expect(trigger).toHaveAttribute("title", "搜索会话");
    await page.locator('[data-settings-lang="en"]').click();
    await expect(archivedInput)
      .toHaveAttribute("placeholder", "Search archived titles or session IDs…");
    await expect(trigger).toHaveAttribute("title", "Search sessions");
    await page.locator("#closeSettingsPage").click();

    await trigger.click();
    await expect(input).toHaveAttribute("placeholder", "Search titles or session IDs…");
    await expect(page.locator("#sessionSearchTitle")).toHaveText("Search unarchived sessions");
    await input.press("Escape");
    assert.deepEqual(pageErrors, []);

    return {
      runtime,
      authoritativeSessionCatalogCount: catalogIds.length,
      recentCount: 10,
      queryCount: 12,
      activeProjects: seed.projectLabels,
      archivedExcluded: true,
      archivedActionsPresent: true,
      navigation: runtime === "bundle" ? "enter" : "click",
      closePaths: ["escape", "backdrop", "button"],
      focusLoop: true,
      narrow,
      languages: ["en", "zh"],
      pageErrors: 0,
    };
  } finally {
    await page.close();
    await context.close();
  }
}

function assertZeroSideEffects(before, after, requests) {
  const forbiddenRequests = requests.filter(({ method, path: requestPath }) => (
    requestPath === "/api/model-routes/refresh"
    || requestPath === "/proxy/chat"
    || requestPath.startsWith("/api/tools/")
    || requestPath.startsWith("/api/agent/runs")
    || requestPath.startsWith("/api/runtime/runs")
    || requestPath === "/v1/models"
    || (method === "POST" && requestPath.startsWith("/api/agent/"))
  ));
  assert.deepEqual(forbiddenRequests, []);
  assert.equal(after.chatRequests.length - before.chatRequests.length, 0);
  assert.equal(after.toolExecutions.length - before.toolExecutions.length, 0);
  assert.equal(after.modelRouteRequests.length - before.modelRouteRequests.length, 0);
  assert.equal(after.production.agentRuns.length - before.production.agentRuns.length, 0);
  assert.equal(after.production.runtimeRuns.length - before.production.runtimeRuns.length, 0);
  assert.equal(after.fakeRequests.filter((entry) => ["models", "chat"].includes(entry.kind)).length, 0);
  return {
    agentRunRequests: 0,
    runtimeRequests: 0,
    chatRequests: 0,
    toolRequests: 0,
    modelCatalogRequests: 0,
    modelRouteRefreshRequests: 0,
  };
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true });
  let browser = null;
  let cleanup = null;
  try {
    assert.equal(host.ready.agentRunIndexes.nonterminal.state, "ready");
    assert.equal(host.ready.agentRunIndexes.session.state, "ready");
    const seed = await seedSearchFacts(host);
    const factsBefore = await readSessionFacts(host, seed);
    const metricsBefore = await host.metrics();
    const requests = [];
    const blockedRequests = [];
    browser = await chromium.launch({ headless: true });
    const runtimes = [];
    for (const runtime of ["bundle", "classic"]) {
      runtimes.push(await exerciseSearchRuntime({
        browser,
        host,
        seed,
        runtime,
        requests,
        blockedRequests,
      }));
      assert.deepEqual(await readSessionFacts(host, seed), factsBefore);
    }
    const metricsAfter = await host.metrics();
    const sideEffects = assertZeroSideEffects(metricsBefore, metricsAfter, requests);
    assert.equal(blockedRequests.every((request) => request.method === "GET"), true);
    process.stdout.write(`${JSON.stringify({
      ok: true,
      command: "session-search-selfcheck",
      realRuntimeLoads: { bundle: 1, classic: 1 },
      runtimes,
      sideEffects,
      sessionFactsUnchanged: true,
      blockedExternalStaticRequests: blockedRequests.length,
    })}\n`);
  } finally {
    if (browser) await browser.close();
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
  }
}

main().catch((error) => {
  process.stderr.write(`${String(error?.stack || error)}\n`);
  process.exitCode = 1;
});
