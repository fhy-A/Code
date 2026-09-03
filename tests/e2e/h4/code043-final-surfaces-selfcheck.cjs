const assert = require("node:assert/strict");
const { chromium } = require("@playwright/test");
const { getActiveChildCount, startIsolatedHost } = require("./isolated-host.cjs");

const CLASSIC_PATH = "/dist/frontend/index.classic.html";
const DESKTOP = Object.freeze({ width: 1280, height: 800 });
const NARROW = Object.freeze({ width: 390, height: 720 });
const LONG_COPY = "A deliberately long notification message verifies wrapping without horizontal overflow across the compact viewport and all registered themes.";
const IMAGE_ROUTES_FIXTURE = Object.freeze({
  version: 1,
  catalogRevision: 0,
  routes: [],
  ok: true,
  changed: false,
  successfulConnections: 0,
  failedConnections: 0,
  failures: [],
});

function keySyncFixture() {
  const tokens = [];
  const keys = {};
  for (let index = 1; index <= 18; index += 1) {
    tokens.push({
      id: index,
      name: `synthetic-key-${index}-${"long-name-".repeat(4)}`,
      status: index === 18 ? 2 : 1,
    });
    keys[index] = `sk-h4-code043-final-${String(index).padStart(2, "0")}`;
  }
  return { tokens, keys };
}

function createAudit() {
  return {
    requests: [],
    startupFixtures: [],
    interactiveSyncFixtures: [],
    serverBound: [],
    blockedExternal: [],
    blockedWrites: [],
  };
}

async function installNetworkFence(context, runtime, audit) {
  let keySyncCalls = 0;
  context.on("request", (request) => {
    const url = new URL(request.url());
    audit.requests.push({ runtime, method: request.method(), hostname: url.hostname, path: url.pathname });
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (method === "POST" && url.pathname === "/api/image-routes/refresh") {
      audit.startupFixtures.push({ runtime, path: url.pathname });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(IMAGE_ROUTES_FIXTURE),
      });
      return;
    }
    if (method === "POST" && url.pathname === "/api/code/sync-keys") {
      keySyncCalls += 1;
      const startup = keySyncCalls === 1;
      (startup ? audit.startupFixtures : audit.interactiveSyncFixtures).push({
        runtime,
        path: url.pathname,
        ordinal: keySyncCalls,
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(startup ? { tokens: [], keys: {} } : keySyncFixture()),
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
    viewport: DESKTOP,
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await installNetworkFence(context, runtime, audit);
  await context.addInitScript(({ platformToken, language }) => {
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
      username: "code043-final-surfaces",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", language);
    localStorage.setItem("code-theme-mode", "light");
    localStorage.removeItem("code-sidebar-hidden");
  }, { platformToken: host.platformToken, language: runtime === "bundle" ? "en" : "zh" });
  return context;
}

async function waitForRuntime(page, runtime) {
  await page.waitForFunction((expectedRuntime) => {
    const root = document.documentElement;
    return root.getAttribute("data-frontend-runtime") === expectedRuntime
      && root.getAttribute("data-code-phase-one-shell-ready") === "true"
      && (expectedRuntime !== "bundle" || root.getAttribute("data-code-frontend-ready") === "true");
  }, runtime === "bundle" ? "bundle" : "classic-fallback");
  await page.waitForFunction(() => document.getElementById("newFolderBtn")?.disabled === false);
}

async function openSettings(page, panel = "models") {
  if (await page.locator("#settingsPage").evaluate((element) => element.classList.contains("hidden"))) {
    await page.locator("#settingsMenuBtn").click();
  }
  await page.locator(`#settingsNav [data-panel="${panel}"]`).click();
  await page.waitForFunction((expectedPanel) => (
    document.querySelector(`.settings-nav-item[data-panel="${expectedPanel}"]`)?.classList.contains("active")
  ), panel);
}

async function selectTheme(page, mode) {
  await openSettings(page, "theme");
  await page.locator(`[data-tp-mode="${mode}"]`).click();
  await page.waitForFunction((expectedMode) => {
    const active = document.querySelector(`[data-tp-mode="${expectedMode}"]`);
    return localStorage.getItem("code-theme-mode") === expectedMode
      && active?.getAttribute("aria-checked") === "true";
  }, mode);
}

async function captureTheme(page, expectedMode) {
  await openSettings(page, "theme");
  await page.locator(`[data-tp-mode="${expectedMode}"]`).focus();
  await page.keyboard.press("Tab");
  const modeFocus = await page.evaluate(() => {
    const element = document.activeElement;
    return {
      active: element?.matches(".tp-mode-btn") === true,
      focusVisible: element.matches(":focus-visible"),
      outlineStyle: getComputedStyle(element).outlineStyle,
      outlineWidth: getComputedStyle(element).outlineWidth,
    };
  });
  await page.locator('[data-tp-mode="system"]').focus();
  await page.keyboard.press("Tab");
  const rowFocus = await page.evaluate(() => {
    const element = document.activeElement;
    return {
      active: element?.matches(".tp-row") === true,
      focusVisible: element.matches(":focus-visible"),
      outlineStyle: getComputedStyle(element).outlineStyle,
      outlineWidth: getComputedStyle(element).outlineWidth,
    };
  });
  const projection = await page.evaluate((selectedMode) => {
    const card = document.querySelector(".theme-settings-panel");
    const modeSwitch = document.querySelector(".tp-mode-switch");
    const selected = document.querySelector(`[data-tp-mode="${selectedMode}"]`);
    const buttonRect = selected.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    return {
      selectedAria: selected.getAttribute("aria-checked"),
      storedMode: localStorage.getItem("code-theme-mode"),
      resolvedDark: document.documentElement.getAttribute("data-theme-mode") === "dark",
      surface: getComputedStyle(card).backgroundColor,
      headingSize: getComputedStyle(document.querySelector(".settings-theme-heading .settings-section-title")).fontSize,
      modeSize: getComputedStyle(selected).fontSize,
      modeHeight: buttonRect.height,
      modeColumns: getComputedStyle(modeSwitch).gridTemplateColumns.split(" ").filter(Boolean).length,
      card: { left: cardRect.left, right: cardRect.right, width: cardRect.width },
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    };
  }, expectedMode);
  assert.deepEqual({ active: modeFocus.active, focusVisible: modeFocus.focusVisible }, { active: true, focusVisible: true });
  assert.notEqual(modeFocus.outlineStyle, "none");
  assert.notEqual(modeFocus.outlineWidth, "0px");
  assert.deepEqual({ active: rowFocus.active, focusVisible: rowFocus.focusVisible }, { active: true, focusVisible: true });
  assert.notEqual(rowFocus.outlineStyle, "none");
  assert.notEqual(rowFocus.outlineWidth, "0px");
  assert.equal(projection.selectedAria, "true");
  assert.equal(projection.storedMode, expectedMode);
  assert.equal(projection.headingSize, "18px");
  assert.equal(projection.modeSize, "14px");
  assert.equal(projection.modeHeight, 40);
  assert.equal(projection.card.left >= 0 && projection.card.right <= projection.viewportWidth + 1, true);
  assert.equal(projection.documentWidth <= projection.viewportWidth, true);
  assert.equal(projection.bodyWidth <= projection.viewportWidth, true);
  return { ...projection, modeFocus, rowFocus };
}

async function verifySystemThemeContract(page) {
  await selectTheme(page, "system");
  const result = await page.evaluate(() => ({
    storedMode: localStorage.getItem("code-theme-mode"),
    groups: [...document.querySelectorAll("[data-tp-variant-group]")].map((element) => element.dataset.tpVariantGroup),
    lightVariant: localStorage.getItem("code-theme-light-variant"),
    darkVariant: localStorage.getItem("code-theme-dark-variant"),
  }));
  assert.equal(result.storedMode, "system");
  assert.deepEqual(result.groups, ["light", "dark"]);
  return result;
}

async function captureToasts(page, phase) {
  await page.evaluate(({ copy, label }) => {
    const { showToast } = window.Code.services.notifications;
    for (const type of ["error", "warning", "success", "info"]) {
      showToast(`${label}: ${copy}`, type, { duration: 15000 });
    }
  }, { copy: LONG_COPY, label: phase });
  await page.waitForFunction(() => document.querySelectorAll("#toastContainer .toast").length === 4);
  const projection = await page.evaluate(() => {
    const container = document.getElementById("toastContainer");
    const containerRect = container.getBoundingClientRect();
    const toasts = [...container.querySelectorAll(".toast")].map((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        role: element.getAttribute("role"),
        live: element.getAttribute("aria-live"),
        atomic: element.getAttribute("aria-atomic"),
        width: rect.width,
        fontSize: style.fontSize,
        lineHeight: style.lineHeight,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
        background: style.backgroundColor,
      };
    });
    return {
      container: { left: containerRect.left, right: containerRect.right, width: containerRect.width },
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      toasts,
    };
  });
  assert.deepEqual(projection.toasts.map((toast) => toast.role), ["alert", "status", "status", "status"]);
  assert.deepEqual(projection.toasts.map((toast) => toast.live), ["assertive", "polite", "polite", "polite"]);
  assert.equal(projection.toasts.every((toast) => toast.atomic === "true"), true);
  assert.equal(projection.toasts.every((toast) => toast.fontSize === "14px"), true);
  assert.equal(projection.toasts.every((toast) => toast.scrollWidth <= toast.clientWidth + 1), true);
  assert.equal(projection.container.left >= 0 && projection.container.right <= projection.viewportWidth + 1, true);
  assert.equal(projection.documentWidth <= projection.viewportWidth, true);
  assert.equal(projection.bodyWidth <= projection.viewportWidth, true);
  await page.evaluate(() => document.querySelectorAll("#toastContainer .toast").forEach((element) => element.remove()));
  return projection;
}

async function exerciseNewFolder(page) {
  if (!(await page.locator("#settingsPage").evaluate((element) => element.classList.contains("hidden")))) {
    await page.locator("#closeSettingsPage").click();
  }
  const opener = page.locator("#newFolderBtn");
  await opener.focus();
  await opener.click();
  await page.waitForFunction(() => !document.getElementById("newFolderModal").classList.contains("hidden"));
  const opened = await page.evaluate(() => {
    const modal = document.getElementById("newFolderModal");
    const dialog = modal.querySelector('[role="dialog"]');
    const cardRect = dialog.getBoundingClientRect();
    const input = document.getElementById("newFolderName");
    const inputRect = input.getBoundingClientRect();
    const createRect = document.getElementById("confirmNewFolder").getBoundingClientRect();
    const labelId = dialog.getAttribute("aria-labelledby");
    return {
      ariaHidden: modal.getAttribute("aria-hidden"),
      ariaModal: dialog.getAttribute("aria-modal"),
      accessibleName: document.getElementById(labelId)?.textContent?.trim() || "",
      closeName: document.getElementById("closeNewFolder").getAttribute("aria-label") || "",
      inputFocused: document.activeElement === input,
      inputHeight: inputRect.height,
      createHeight: createRect.height,
      titleSize: getComputedStyle(document.getElementById(labelId)).fontSize,
      card: { left: cardRect.left, right: cardRect.right, width: cardRect.width },
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
    };
  });
  assert.equal(opened.ariaHidden, "false");
  assert.equal(opened.ariaModal, "true");
  assert.notEqual(opened.accessibleName, "");
  assert.notEqual(opened.closeName, "");
  assert.equal(opened.inputFocused, true);
  assert.equal(opened.inputHeight, 40);
  assert.equal(opened.createHeight, 32);
  assert.equal(opened.titleSize, "18px");
  assert.equal(opened.card.left >= 0 && opened.card.right <= opened.viewportWidth + 1, true);
  assert.equal(opened.documentWidth <= opened.viewportWidth, true);
  await page.keyboard.press("Escape");
  const closed = await page.evaluate(() => ({
    hidden: document.getElementById("newFolderModal").classList.contains("hidden"),
    ariaHidden: document.getElementById("newFolderModal").getAttribute("aria-hidden"),
    focusReturned: document.activeElement === document.getElementById("newFolderBtn"),
  }));
  assert.deepEqual(closed, { hidden: true, ariaHidden: "true", focusReturned: true });
  return { opened, closed };
}

async function openKeySync(page) {
  await openSettings(page, "models");
  await page.locator("#settingsConnectPlatform").focus();
  await page.locator("#settingsConnectPlatform").click();
  await page.waitForFunction(() => document.querySelectorAll("#keySyncOverlay .key-sync-row").length === 18);
  await page.waitForFunction(() => document.activeElement?.classList.contains("key-sync-close"));
}

async function captureKeySync(page) {
  const result = await page.evaluate(() => {
    const overlay = document.getElementById("keySyncOverlay");
    const dialog = overlay.querySelector('[role="dialog"]');
    const list = overlay.querySelector(".key-sync-list");
    const row = overlay.querySelector(".key-sync-row");
    const cardRect = dialog.getBoundingClientRect();
    const labelId = dialog.getAttribute("aria-labelledby");
    return {
      ariaModal: dialog.getAttribute("aria-modal"),
      accessibleName: document.getElementById(labelId)?.textContent?.trim() || "",
      closeName: overlay.querySelector(".key-sync-close").getAttribute("aria-label") || "",
      closeFocused: document.activeElement === overlay.querySelector(".key-sync-close"),
      titleSize: getComputedStyle(document.getElementById(labelId)).fontSize,
      summarySize: getComputedStyle(overlay.querySelector(".key-sync-summary")).fontSize,
      rowAreas: getComputedStyle(row).gridTemplateAreas,
      rowScrollWidth: row.scrollWidth,
      rowClientWidth: row.clientWidth,
      listScrollable: list.scrollHeight > list.clientHeight,
      card: { left: cardRect.left, right: cardRect.right, width: cardRect.width },
      surface: getComputedStyle(dialog).backgroundColor,
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    };
  });
  assert.equal(result.ariaModal, "true");
  assert.notEqual(result.accessibleName, "");
  assert.notEqual(result.closeName, "");
  assert.equal(result.closeFocused, true);
  assert.equal(result.titleSize, "18px");
  assert.equal(result.summarySize, "14px");
  assert.equal(result.rowScrollWidth <= result.rowClientWidth + 1, true);
  assert.equal(result.listScrollable, true);
  assert.equal(result.card.left >= 0 && result.card.right <= result.viewportWidth + 1, true);
  assert.equal(result.documentWidth <= result.viewportWidth, true);
  assert.equal(result.bodyWidth <= result.viewportWidth, true);
  return result;
}

async function closeKeySync(page) {
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.getElementById("keySyncOverlay"));
  const focusReturned = await page.evaluate(() => document.activeElement === document.getElementById("settingsConnectPlatform"));
  assert.equal(focusReturned, true);
  return { focusReturned };
}

async function captureCompactDialog(page) {
  await page.evaluate((copy) => {
    const modal = document.getElementById("compactConfirmModal");
    const body = document.getElementById("compactConfirmBody");
    body.innerHTML = `<p>${copy}</p><div class="compact-stats">
      <div><span>Compress</span><b>48 messages</b></div>
      <div><span>Keep recent</span><b>12 messages</b></div>
      <div><span>Estimated savings</span><b>~18,000 Token</b></div>
    </div>${Array.from({ length: 24 }, (_, index) => `<p class="confirm-note">${index + 1}. ${copy}</p>`).join("")}`;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.getElementById("cancelCompact").focus();
  }, LONG_COPY);
  const result = await page.evaluate(() => {
    const modal = document.getElementById("compactConfirmModal");
    const dialog = modal.querySelector('[role="dialog"]');
    const body = document.getElementById("compactConfirmBody");
    const cardRect = dialog.getBoundingClientRect();
    const labelId = dialog.getAttribute("aria-labelledby");
    return {
      ariaHidden: modal.getAttribute("aria-hidden"),
      ariaModal: dialog.getAttribute("aria-modal"),
      describedBy: dialog.getAttribute("aria-describedby"),
      accessibleName: document.getElementById(labelId)?.textContent?.trim() || "",
      closeName: document.getElementById("cancelCompactX").getAttribute("aria-label") || "",
      cancelFocused: document.activeElement === document.getElementById("cancelCompact"),
      titleSize: getComputedStyle(document.getElementById(labelId)).fontSize,
      bodySize: getComputedStyle(body).fontSize,
      noteSize: getComputedStyle(body.querySelector(".confirm-note")).fontSize,
      buttonHeight: document.getElementById("cancelCompact").getBoundingClientRect().height,
      bodyScrollable: body.scrollHeight > body.clientHeight,
      card: { left: cardRect.left, top: cardRect.top, right: cardRect.right, bottom: cardRect.bottom, width: cardRect.width },
      surface: getComputedStyle(dialog).backgroundColor,
      viewport: { width: innerWidth, height: innerHeight },
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    };
  });
  assert.equal(result.ariaHidden, "false");
  assert.equal(result.ariaModal, "true");
  assert.equal(result.describedBy, "compactConfirmBody");
  assert.notEqual(result.accessibleName, "");
  assert.notEqual(result.closeName, "");
  assert.equal(result.cancelFocused, true);
  assert.equal(result.titleSize, "18px");
  assert.equal(result.bodySize, "14px");
  assert.equal(result.noteSize, "12px");
  assert.equal(result.buttonHeight, 32);
  assert.equal(result.bodyScrollable, true);
  assert.equal(result.card.left >= 0 && result.card.right <= result.viewport.width + 1, true);
  assert.equal(result.card.top >= 0 && result.card.bottom <= result.viewport.height + 1, true);
  assert.equal(result.documentWidth <= result.viewport.width, true);
  assert.equal(result.bodyWidth <= result.viewport.width, true);
  await page.evaluate(() => {
    const modal = document.getElementById("compactConfirmModal");
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.getElementById("compactConfirmBody").innerHTML = "";
  });
  return result;
}

async function exerciseRuntime(browser, host, runtime, audit, scenario) {
  const context = await createContext(browser, host, runtime, audit);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL(CLASSIC_PATH, host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    const sessionsReady = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname === "/api/sessions";
    });
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await sessionsReady;
    await waitForRuntime(page, runtime);

    let evidence;
    if (scenario === "core") {
      await selectTheme(page, "light");
      const lightTheme = await captureTheme(page, "light");
      const systemTheme = await verifySystemThemeContract(page);
      await selectTheme(page, "light");
      const lightToasts = await captureToasts(page, `${runtime}-light`);
      const lightFolder = await exerciseNewFolder(page);
      const lightCompact = await captureCompactDialog(page);

      await page.setViewportSize(NARROW);
      await selectTheme(page, "dark");
      const darkTheme = await captureTheme(page, "dark");
      assert.equal(darkTheme.resolvedDark, true);
      assert.equal(darkTheme.modeColumns, 1);
      assert.notEqual(lightTheme.surface, darkTheme.surface);
      const darkToasts = await captureToasts(page, `${runtime}-dark-narrow`);
      const darkFolder = await exerciseNewFolder(page);
      const darkCompact = await captureCompactDialog(page);
      evidence = {
        themes: { light: lightTheme, system: systemTheme, dark: darkTheme },
        toasts: { light: lightToasts, darkNarrow: darkToasts },
        newFolder: { light: lightFolder, darkNarrow: darkFolder },
        compact: { light: lightCompact, darkNarrow: darkCompact },
      };
    } else {
      await selectTheme(page, "light");
      await openKeySync(page);
      const lightDesktop = await captureKeySync(page);
      await page.setViewportSize(NARROW);
      const lightNarrow = await captureKeySync(page);
      assert.equal(lightNarrow.rowAreas.includes("name actions"), true);
      const lightClose = await closeKeySync(page);

      await selectTheme(page, "dark");
      await openKeySync(page);
      const darkNarrow = await captureKeySync(page);
      assert.equal(darkNarrow.rowAreas.includes("name actions"), true);
      assert.notEqual(lightDesktop.surface, darkNarrow.surface);
      const darkClose = await closeKeySync(page);
      evidence = {
        keySync: { lightDesktop, lightNarrow, darkNarrow, lightClose, darkClose },
      };
    }

    assert.deepEqual(pageErrors, []);
    return {
      runtime,
      scenario,
      language: await page.evaluate(() => document.documentElement.lang),
      viewportMatrix: { desktop: DESKTOP, narrow: NARROW },
      ...evidence,
    };
  } finally {
    await page.close();
    await context.close();
  }
}

function assertNetworkContract(before, after, audit, interactiveSyncCount) {
  assert.deepEqual(audit.blockedWrites, []);
  assert.equal(audit.blockedExternal.every((entry) => entry.method === "GET"), true);
  for (const runtime of ["bundle", "classic"]) {
    assert.equal(audit.startupFixtures.filter((entry) => entry.runtime === runtime && entry.path === "/api/image-routes/refresh").length, 1);
    assert.equal(audit.startupFixtures.filter((entry) => entry.runtime === runtime && entry.path === "/api/code/sync-keys").length, 1);
    assert.equal(audit.interactiveSyncFixtures.filter((entry) => entry.runtime === runtime && entry.path === "/api/code/sync-keys").length, interactiveSyncCount);
  }
  assert.equal(after.chatRequests.length - before.chatRequests.length, 0);
  assert.equal(after.toolExecutions.length - before.toolExecutions.length, 0);
  assert.equal(after.modelRouteRequests.length - before.modelRouteRequests.length, 0);
  assert.equal(after.production.agentRuns.length - before.production.agentRuns.length, 0);
  assert.equal(after.production.runtimeRuns.length - before.production.runtimeRuns.length, 0);
  assert.equal(after.fakeRequests.filter((entry) => ["models", "chat", "platform-sync"].includes(entry.kind)).length, 0);
  return {
    chatRequests: 0,
    toolRequests: 0,
    modelCatalogRequests: 0,
    platformSyncServerRequests: 0,
    productWriteRequests: 0,
  };
}

async function main() {
  const scenario = String(process.argv[2] || "");
  assert.equal(["core", "key-sync"].includes(scenario), true);
  const surfaces = scenario === "core"
    ? ["theme-picker", "toast-stack", "new-folder", "compact-confirm"]
    : ["key-sync"];
  const host = await startIsolatedHost({ disableRoutingV2: true });
  const audit = createAudit();
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    const before = await host.metrics();
    browser = await chromium.launch({ headless: true });
    const bundle = await exerciseRuntime(browser, host, "bundle", audit, scenario);
    const classic = await exerciseRuntime(browser, host, "classic", audit, scenario);
    const after = await host.metrics();
    result = {
      ok: true,
      command: `code043-final-${scenario}-selfcheck-v3`,
      realRuntimeLoads: { bundle: 1, classic: 1 },
      matrix: {
        themes: ["light", "dark"],
        viewports: ["desktop", "390px"],
        surfaces,
      },
      runtimes: [bundle, classic],
      network: assertNetworkContract(before, after, audit, scenario === "key-sync" ? 2 : 0),
      blockedExternalStaticRequests: audit.blockedExternal.length,
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
