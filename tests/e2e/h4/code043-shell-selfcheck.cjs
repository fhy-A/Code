const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const CLASSIC_PATH = "/dist/frontend/index.classic.html";
const DESKTOP_VIEWPORT = Object.freeze({ width: 1280, height: 800 });
const ICON_SELECTORS = Object.freeze([
  "#newChat", "#projectCreateBtn", "#goUp", "#newFolderBtn", "#refreshFiles",
  "#settingsMenuBtn", "#toggleSidebar", "#attachFile", "#togglePreview",
  ".cwd-icon", ".explorer-arrow",
]);
const CLICK_TARGET_IDS = Object.freeze([
  "sessionSearchBtn", "newChat", "projectCreateBtn", "goUp", "newFolderBtn",
  "refreshFiles", "settingsMenuBtn", "toggleSidebar", "attachFile", "togglePreview",
]);
const STARTUP_FIXTURE_RESPONSES = Object.freeze({
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

function observeRequests(
  context,
  runtime,
  requests,
  serverBoundRequests,
  interceptedStartupRequests,
  blockedExternalRequests,
) {
  context.on("request", (request) => {
    const url = new URL(request.url());
    requests.push({ runtime, method: request.method(), hostname: url.hostname, path: url.pathname });
  });
  return context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const fixture = method === "POST" ? STARTUP_FIXTURE_RESPONSES[url.pathname] : null;
    if (fixture) {
      interceptedStartupRequests.push({
        runtime,
        method,
        path: url.pathname,
        fulfilled: true,
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
      return;
    }
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      blockedExternalRequests.push({
        runtime,
        method,
        hostname: url.hostname,
        path: url.pathname,
      });
      await route.abort("blockedbyclient");
      return;
    }
    serverBoundRequests.push({ runtime, method, hostname: url.hostname, path: url.pathname });
    await route.continue();
  });
}

async function createContext(
  browser,
  host,
  runtime,
  language,
  requests,
  serverBoundRequests,
  interceptedStartupRequests,
  blockedExternalRequests,
) {
  const context = await browser.newContext({
    viewport: DESKTOP_VIEWPORT,
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await observeRequests(
    context,
    runtime,
    requests,
    serverBoundRequests,
    interceptedStartupRequests,
    blockedExternalRequests,
  );
  await context.addInitScript(({ platformToken, language: initialLanguage }) => {
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
      username: "code043-shell",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", initialLanguage);
    localStorage.setItem("code-theme-mode", "light");
    localStorage.removeItem("code-sidebar-hidden");
  }, { platformToken: host.platformToken, language });
  return context;
}

async function waitForShellReadiness(page, runtime, expectedLabel) {
  await page.waitForFunction(({ expectedRuntime, expectedText }) => {
    const root = document.documentElement;
    const runtimeReady = root.getAttribute("data-frontend-runtime") === expectedRuntime;
    const phaseReady = root.getAttribute("data-code-phase-one-shell-ready") === "true";
    const bundleReady = expectedRuntime !== "bundle"
      || root.getAttribute("data-code-frontend-ready") === "true";
    const labelReady = document.querySelector("#newChat [data-ui-label]")?.textContent === expectedText;
    return runtimeReady && phaseReady && bundleReady && labelReady;
  }, {
    expectedRuntime: runtime === "bundle" ? "bundle" : "classic-fallback",
    expectedText: expectedLabel,
  });
}

async function exerciseRuntime({
  browser,
  host,
  runtime,
  language,
  requests,
  serverBoundRequests,
  interceptedStartupRequests,
  blockedExternalRequests,
}) {
  const context = await createContext(
    browser,
    host,
    runtime,
    language,
    requests,
    serverBoundRequests,
    interceptedStartupRequests,
    blockedExternalRequests,
  );
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL(CLASSIC_PATH, host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await waitForShellReadiness(page, runtime, language === "en" ? "New Session" : "新建会话");

    const desktop = await page.evaluate(({ iconSelectors, targetIds, expectedLanguage }) => {
      const shell = document.querySelector("#piShell");
      const style = getComputedStyle(shell);
      const icons = iconSelectors.map((selector) => ({
        selector,
        svgCount: document.querySelectorAll(`${selector} svg.ui-icon`).length,
      }));
      const targets = targetIds.map((id) => {
        const element = document.getElementById(id);
        const rect = element.getBoundingClientRect();
        return {
          id,
          width: rect.width,
          height: rect.height,
          ariaLabel: element.getAttribute("aria-label") || "",
          title: element.getAttribute("title") || "",
        };
      });
      return {
        viewport: { width: innerWidth, height: innerHeight },
        language: document.documentElement.lang,
        expectedLanguage,
        phaseReady: document.documentElement.getAttribute("data-code-phase-one-shell-ready"),
        frontendReady: document.documentElement.getAttribute("data-code-frontend-ready"),
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        tokens: {
          caption: style.getPropertyValue("--shell-type-caption").trim(),
          control: style.getPropertyValue("--shell-control-sm").trim(),
          radius: style.getPropertyValue("--shell-radius-md").trim(),
        },
        labels: {
          newChat: document.querySelector("#newChat [data-ui-label]")?.textContent || "",
          settings: document.querySelector("#settingsMenuBtn [data-ui-label]")?.textContent || "",
          preview: document.querySelector("#togglePreview [data-ui-label]")?.textContent || "",
        },
        icons,
        targets,
      };
    }, { iconSelectors: ICON_SELECTORS, targetIds: CLICK_TARGET_IDS, expectedLanguage: language });
    assert.deepEqual(desktop.viewport, DESKTOP_VIEWPORT);
    assert.equal(desktop.phaseReady, "true");
    assert.equal(runtime === "bundle" ? desktop.frontendReady : null, runtime === "bundle" ? "true" : null);
    assert.equal(desktop.documentWidth <= DESKTOP_VIEWPORT.width, true);
    assert.equal(desktop.bodyWidth <= DESKTOP_VIEWPORT.width, true);
    assert.deepEqual(desktop.tokens, { caption: "11px", control: "28px", radius: "10px" });
    assert.equal(desktop.icons.every((icon) => icon.svgCount === 1), true);
    assert.equal(desktop.targets.every((target) => target.width >= 28 && target.height >= 28), true);
    assert.deepEqual(desktop.labels, language === "en"
      ? { newChat: "New Session", settings: "Settings", preview: "Preview" }
      : { newChat: "新建会话", settings: "设置", preview: "预览" });

    const themeProjection = await page.evaluate(() => {
      const root = document.documentElement;
      const body = document.body;
      const read = () => ({
        sidebar: getComputedStyle(document.querySelector(".pi-sidebar")).backgroundColor,
        toolbar: getComputedStyle(document.querySelector(".toolbar")).backgroundColor,
        composer: getComputedStyle(document.querySelector(".composer")).backgroundColor,
        selected: getComputedStyle(document.querySelector("#piShell"))
          .getPropertyValue("--shell-state-selected").trim(),
      });
      body.classList.remove("theme-dark");
      root.dataset.themeMode = "light";
      const light = read();
      body.classList.add("theme-dark");
      root.dataset.themeMode = "dark";
      const dark = read();
      body.classList.remove("theme-dark");
      root.dataset.themeMode = "light";
      return { light, dark };
    });
    assert.notEqual(themeProjection.light.sidebar, themeProjection.dark.sidebar);
    assert.notEqual(themeProjection.light.toolbar, themeProjection.dark.toolbar);
    assert.notEqual(themeProjection.light.composer, themeProjection.dark.composer);
    assert.notEqual(themeProjection.light.selected, "");
    assert.notEqual(themeProjection.dark.selected, "");

    await page.locator("#sessionSearchBtn").focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.locator("#newChat").evaluate((element) => document.activeElement === element), true);
    const focusProjection = await page.locator("#newChat").evaluate((element) => ({
      boxShadow: getComputedStyle(element).boxShadow,
      outlineStyle: getComputedStyle(element).outlineStyle,
    }));
    assert.equal(focusProjection.boxShadow !== "none" || focusProjection.outlineStyle !== "none", true);

    await page.setViewportSize(DESKTOP_VIEWPORT);
    const restored = await page.evaluate(() => ({
      viewport: { width: innerWidth, height: innerHeight },
      sidebarHidden: document.querySelector("#piShell").classList.contains("sidebar-hidden"),
      themeDark: document.body.classList.contains("theme-dark"),
      phaseReady: document.documentElement.getAttribute("data-code-phase-one-shell-ready"),
    }));
    assert.deepEqual(restored, {
      viewport: DESKTOP_VIEWPORT,
      sidebarHidden: false,
      themeDark: false,
      phaseReady: "true",
    });
    assert.deepEqual(pageErrors, []);
    return {
      runtime,
      language,
      desktop,
      themeProjection,
      focusProjection,
      restored,
    };
  } finally {
    await page.close();
    await context.close();
  }
}

function assertStartupInterceptionContract(
  requests,
  serverBoundRequests,
  interceptedStartupRequests,
) {
  const summary = {};
  const paths = Object.keys(STARTUP_FIXTURE_RESPONSES);
  for (const runtime of ["bundle", "classic"]) {
    summary[runtime] = {};
    for (const pathname of paths) {
      const initiated = requests.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      const intercepted = interceptedStartupRequests.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      const reachedServer = serverBoundRequests.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      assert.equal(initiated.length, 1);
      assert.deepEqual(intercepted, [{
        runtime,
        method: "POST",
        path: pathname,
        fulfilled: true,
      }]);
      assert.deepEqual(reachedServer, []);
      summary[runtime][pathname] = {
        initiated: 1,
        intercepted: 1,
        fulfilled: 1,
        serverReceived: 0,
      };
    }
  }
  assert.equal(interceptedStartupRequests.length, 4);
  return summary;
}

function assertZeroBusinessSideEffects(before, after, serverBoundRequests) {
  const productWrites = serverBoundRequests.filter(({ method }) => (
    !["GET", "HEAD", "OPTIONS"].includes(method)
  ));
  assert.deepEqual(productWrites, []);
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
    productWriteRequests: 0,
  };
}

async function controlledImageRegistryState(host) {
  const registryPath = path.join(host.dataDir, "image-route-registry.json");
  try {
    const stat = await fs.stat(registryPath);
    return { exists: true, size: stat.size, modifiedMs: stat.mtimeMs };
  } catch (error) {
    if (error?.code === "ENOENT") return { exists: false };
    throw error;
  }
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true });
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    const metricsBefore = await host.metrics();
    const imageRegistryBefore = await controlledImageRegistryState(host);
    assert.deepEqual(imageRegistryBefore, { exists: false });
    const requests = [];
    const serverBoundRequests = [];
    const interceptedStartupRequests = [];
    const blockedExternalRequests = [];
    browser = await chromium.launch({ headless: true });
    const bundle = await exerciseRuntime({
      browser,
      host,
      runtime: "bundle",
      language: "en",
      requests,
      serverBoundRequests,
      interceptedStartupRequests,
      blockedExternalRequests,
    });
    const classic = await exerciseRuntime({
      browser,
      host,
      runtime: "classic",
      language: "zh",
      requests,
      serverBoundRequests,
      interceptedStartupRequests,
      blockedExternalRequests,
    });
    const metricsAfter = await host.metrics();
    const imageRegistryAfter = await controlledImageRegistryState(host);
    assert.deepEqual(imageRegistryAfter, imageRegistryBefore);
    const startupInterceptions = assertStartupInterceptionContract(
      requests,
      serverBoundRequests,
      interceptedStartupRequests,
    );
    const sideEffects = assertZeroBusinessSideEffects(
      metricsBefore,
      metricsAfter,
      serverBoundRequests,
    );
    const platformSyncBefore = metricsBefore.fakeRequests.filter(
      (entry) => entry.kind === "platform-sync",
    ).length;
    const platformSyncAfter = metricsAfter.fakeRequests.filter(
      (entry) => entry.kind === "platform-sync",
    ).length;
    assert.equal(platformSyncAfter - platformSyncBefore, 0);
    assert.equal(blockedExternalRequests.every((request) => request.method === "GET"), true);
    result = {
      ok: true,
      command: "code043-shell-selfcheck",
      realRuntimeLoads: { bundle: 1, classic: 1 },
      runtimes: [bundle, classic],
      startupInterceptions,
      serverReceiptEvidence: {
        interceptedEndpointsReceived: 0,
        imageRegistryBefore,
        imageRegistryAfter,
        platformSyncRequests: 0,
      },
      sideEffects,
      blockedExternalStaticRequests: blockedExternalRequests.length,
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
    activeChildCount: cleanup.activeChildCount,
    cleanupErrors: cleanup.cleanupErrors,
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
