const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
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

async function requestJson(baseUrl, pathname, options = {}, allowedStatuses = [200, 201]) {
  const response = await fetch(new URL(pathname, baseUrl), {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!allowedStatuses.includes(response.status)) {
    throw new Error(`Unexpected ${response.status} for ${options.method || "GET"} ${pathname}`);
  }
  return { status: response.status, payload };
}

async function waitUntil(read, predicate, message, timeoutMs = 8_000) {
  const deadline = Date.now() + timeoutMs;
  let latest;
  while (Date.now() < deadline) {
    latest = await read();
    if (predicate(latest)) return latest;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`${message}: ${JSON.stringify(latest)}`);
}

async function seedContract(host) {
  const targetPrimary = path.join(host.root, "target-primary");
  const targetSecondary = path.join(host.root, "target-secondary");
  const longProjectRoot = path.join(host.root, "long-project-root");
  const newProjectRoot = path.join(host.root, "new-project-root");
  const editorPrimary = path.join(host.root, "editor-primary");
  const editorSecondary = path.join(host.root, "editor-secondary");
  const conflictEditorPrimary = path.join(host.root, "conflict-editor-primary");
  const dragBundleTargetRoot = path.join(host.root, "drag-bundle-target");
  const dragClassicTargetRoot = path.join(host.root, "drag-classic-target");
  const dragBundleConflictRoot = path.join(host.root, "drag-bundle-conflict");
  const dragClassicConflictRoot = path.join(host.root, "drag-classic-conflict");
  const duplicateRootA = path.join(host.root, "area-a", "shared-src");
  const duplicateRootB = path.join(host.root, "area-b", "shared-src");
  const conflictRoot = path.join(
    host.root,
    "a-very-long-session-source-folder-name-for-narrow-confirmation-layout",
    "nested-source-folder-that-must-wrap-without-overflow",
  );
  await Promise.all([
    fs.mkdir(targetPrimary),
    fs.mkdir(targetSecondary),
    fs.mkdir(longProjectRoot),
    fs.mkdir(newProjectRoot),
    fs.mkdir(editorPrimary),
    fs.mkdir(editorSecondary),
    fs.mkdir(conflictEditorPrimary),
    fs.mkdir(dragBundleTargetRoot),
    fs.mkdir(dragClassicTargetRoot),
    fs.mkdir(dragBundleConflictRoot),
    fs.mkdir(dragClassicConflictRoot),
    fs.mkdir(duplicateRootA, { recursive: true }),
    fs.mkdir(duplicateRootB, { recursive: true }),
    fs.mkdir(conflictRoot, { recursive: true }),
    fs.mkdir(path.join(host.dataDir, "attachments"), { recursive: true }),
  ]);
  await Promise.all([
    fs.writeFile(path.join(targetPrimary, "target-primary.txt"), "primary\n", "utf8"),
    fs.writeFile(path.join(targetSecondary, "target-secondary.txt"), "secondary\n", "utf8"),
    fs.writeFile(path.join(longProjectRoot, "long-project.txt"), "long\n", "utf8"),
    fs.writeFile(path.join(newProjectRoot, "new-project.txt"), "new\n", "utf8"),
    fs.writeFile(path.join(editorPrimary, "editor-primary.txt"), "primary\n", "utf8"),
    fs.writeFile(path.join(editorSecondary, "editor-secondary.txt"), "secondary\n", "utf8"),
    fs.writeFile(path.join(dragBundleTargetRoot, "bundle-target.txt"), "bundle\n", "utf8"),
    fs.writeFile(path.join(dragClassicTargetRoot, "classic-target.txt"), "classic\n", "utf8"),
  ]);

  const existingProjects = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  let originalProject = existingProjects.find((project) => (
    (project.rootPaths || []).some((root) => path.resolve(root) === path.resolve(host.projectDir))
  ));
  if (!originalProject) {
    originalProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
      method: "POST",
      body: JSON.stringify({
        label: "Original project",
        rootPaths: [host.projectDir],
      }),
    })).payload;
  }
  const targetProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "Target project",
      rootPaths: [targetPrimary, targetSecondary],
    }),
  })).payload;
  originalProject = (await requestJson(
    host.ready.codeUrl,
    `/api/projects/${originalProject.id}/update`,
    {
      method: "POST",
      body: JSON.stringify({
        label: originalProject.label,
        rootPaths: [host.projectDir, targetSecondary, duplicateRootA, duplicateRootB],
        expectedStateToken: originalProject.stateToken,
      }),
    },
  )).payload;
  const longProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "A very long project name that should be clipped in the submenu",
      rootPaths: [longProjectRoot],
    }),
  })).payload;
  const editorProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "Primary editor project",
      rootPaths: [editorPrimary, editorSecondary],
    }),
  })).payload;
  const conflictEditorProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "Primary conflict editor",
      rootPaths: [conflictEditorPrimary, targetPrimary],
    }),
  })).payload;
  const dragBundleTargetProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "Bundle drag target",
      rootPaths: [dragBundleTargetRoot],
    }),
  })).payload;
  const dragClassicTargetProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "Classic drag target",
      rootPaths: [dragClassicTargetRoot],
    }),
  })).payload;

  const createSession = async (
    title,
    runState = {},
    projectId = null,
    cwd = host.projectDir,
  ) => (
    await requestJson(host.ready.codeUrl, "/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        title,
        projectId,
        cwd,
        runState,
      }),
    })
  ).payload;

  const createDragFixture = async (prefix, targetProject, conflictCwd) => {
    const fixture = {
      targetProject,
      current: await createSession(`${prefix} current`, {}, originalProject.id),
      other: await createSession(`${prefix} other`),
      cancel: await createSession(`${prefix} cancel`, {}, longProject.id, longProjectRoot),
      busy: await createSession(`${prefix} busy`, { status: "paused" }),
      waiting: await createSession(`${prefix} waiting`, {
        status: "waiting_user_input",
        userInputRequest: {
          requestId: `${prefix.toLowerCase().replaceAll(" ", "-")}-request`,
          status: "pending",
          questions: [],
        },
      }),
      conflict: await createSession(`${prefix} conflict`, {}, null, conflictCwd),
      archived: await createSession(`${prefix} archived`, {}, originalProject.id),
    };
    await requestJson(
      host.ready.codeUrl,
      `/api/session-archive/${encodeURIComponent(fixture.archived.id)}/archive`,
      { method: "POST" },
    );
    return fixture;
  };
  const dragBundle = await createDragFixture(
    "CODE-071 bundle drag",
    dragBundleTargetProject,
    dragBundleConflictRoot,
  );
  const dragClassic = await createDragFixture(
    "CODE-071 classic drag",
    dragClassicTargetProject,
    dragClassicConflictRoot,
  );

  return {
    targetPrimary,
    targetSecondary,
    longProjectRoot,
    newProjectRoot,
    editorPrimary,
    editorSecondary,
    conflictEditorPrimary,
    dragBundleTargetRoot,
    dragClassicTargetRoot,
    duplicateRootA,
    duplicateRootB,
    conflictRoot,
    originalProject,
    targetProject,
    longProject,
    editorProject,
    conflictEditorProject,
    drag: {
      bundle: dragBundle,
      classic: dragClassic,
    },
    current: await createSession("CODE-071 current", {}, originalProject.id),
    longAssigned: await createSession(
      "CODE-071 long assigned",
      {},
      longProject.id,
      longProjectRoot,
    ),
    other: await createSession("CODE-071 other"),
    busy: await createSession("CODE-071 busy", { status: "paused" }),
    wide: await createSession("CODE-071 wide", {}, null, host.homeDir),
    conflict: await createSession("CODE-071 conflict", {}, null, conflictRoot),
    createAndMove: await createSession("CODE-071 create and move"),
    classic: await createSession("CODE-071 classic", {}, originalProject.id),
    classicLongAssigned: await createSession(
      "CODE-071 classic long assigned",
      {},
      longProject.id,
      longProjectRoot,
    ),
    editorSession: await createSession(
      "CODE-071 primary editor",
      {},
      editorProject.id,
      editorPrimary,
    ),
  };
}

async function createContext(
  browser,
  host,
  seed,
  projectRequests,
  projectPreviews,
  pageErrors,
  currentSessionId,
  themeMode = "light",
) {
  const context = await browser.newContext({
    viewport: { width: 460, height: 800 },
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  context.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "PUT" && /^\/api\/sessions\/[^/]+\/project$/.test(url.pathname)) {
      let body = null;
      try { body = request.postDataJSON(); } catch {}
      projectRequests.push({ path: url.pathname, body });
    }
    if (request.method() === "POST" && /^\/api\/sessions\/[^/]+\/project\/preview$/.test(url.pathname)) {
      let body = null;
      try { body = request.postDataJSON(); } catch {}
      projectPreviews.push({ path: url.pathname, body });
    }
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname === "/api/pick-folder") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ cancelled: false, path: seed.newProjectRoot }),
      });
      return;
    }
    const fixture = request.method() === "POST" ? STARTUP_FIXTURES[url.pathname] : null;
    if (fixture) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
      return;
    }
    if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  await context.addInitScript(({
    platformToken,
    currentSessionId,
    projectDir,
    expandedProjectIds,
    themeMode: initialThemeMode,
  }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    localStorage.setItem("code-key-config", "[]");
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken,
      userId: "71",
      username: "code071-h4",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", "en");
    localStorage.setItem("code-theme-mode", initialThemeMode);
    localStorage.setItem("code-sidebar-width", "190");
    localStorage.setItem("code-recent-folders", JSON.stringify([projectDir]));
    localStorage.setItem("code-expanded-project-sessions", JSON.stringify(
      Object.fromEntries([
        "__unassigned_sessions__",
        ...expandedProjectIds,
      ].map((projectId) => [projectId, true])),
    ));
    localStorage.setItem("code-foreground-view", "session");
    localStorage.setItem("code-last-session", currentSessionId);
  }, {
    platformToken: host.platformToken,
    currentSessionId,
    projectDir: host.projectDir,
    expandedProjectIds: [
      seed.originalProject.id,
      seed.targetProject.id,
      seed.longProject.id,
      seed.editorProject.id,
      seed.conflictEditorProject.id,
      seed.drag.bundle.targetProject.id,
      seed.drag.classic.targetProject.id,
    ],
    themeMode,
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error?.stack || error)));
  return { context, page };
}

async function sessionRecord(host, sessionId) {
  return (await requestJson(
    host.ready.codeUrl,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  )).payload;
}

async function waitForSession(host, sessionId, predicate, message) {
  return waitUntil(
    () => sessionRecord(host, sessionId),
    predicate,
    message,
  );
}

async function waitForRoot(page, expected) {
  await waitUntil(
    () => page.locator("#projectRoot").inputValue(),
    (value) => path.resolve(value) === path.resolve(expected),
    "file tree root did not converge",
  );
}

async function openProjectSubmenu(page, sessionId) {
  const more = page.locator(`.session-more-btn[data-session-id="${sessionId}"]`);
  await more.scrollIntoViewIfNeeded();
  await more.press("Enter");
  const menu = page.locator(".session-more-menu:not(.session-project-submenu)");
  await menu.waitFor({ state: "visible" });
  assert.equal(await menu.getAttribute("role"), "menu");
  assert.equal(await more.getAttribute("aria-expanded"), "true");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  const trigger = menu.locator('[data-action="project"]');
  assert.equal(await trigger.evaluate((element) => element === document.activeElement), true);
  await trigger.press("ArrowRight");
  const submenu = page.locator(".session-project-submenu");
  await submenu.waitFor({ state: "visible" });
  assert.equal(await submenu.getAttribute("role"), "menu");
  assert.equal(await trigger.getAttribute("aria-expanded"), "true");
  return { more, menu, trigger, submenu };
}

async function pointerPoint(page, locator) {
  const box = await locator.boundingBox();
  assert.ok(box);
  const point = {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
  await page.mouse.move(point.x, point.y);
  return point;
}

async function clickPointerTarget(page, locator) {
  const point = await pointerPoint(page, locator);
  await page.mouse.click(point.x, point.y);
  return point;
}

async function movePointerOutside(page, { click = false } = {}) {
  const viewport = page.viewportSize();
  assert.ok(viewport);
  const point = { x: viewport.width - 6, y: viewport.height - 6 };
  if (click) await page.mouse.click(point.x, point.y);
  else await page.mouse.move(point.x, point.y);
}

async function exerciseProjectMenuAcceptance(page, seed, sessionId) {
  const more = page.locator(`.session-more-btn[data-session-id="${sessionId}"]`);
  await more.scrollIntoViewIfNeeded();
  await more.click();
  let menu = page.locator(".session-more-menu:not(.session-project-submenu)");
  await menu.waitFor({ state: "visible" });
  let trigger = menu.locator('[data-action="project"]');
  const menuBox = await menu.boundingBox();
  assert.ok(menuBox);
  assert.equal(menuBox.width < 168, true);

  // Hover opens a transient submenu. Crossing the short trigger/menu gap
  // keeps it open, while leaving both regions closes it without sticky delay.
  const triggerPoint = await pointerPoint(page, trigger);
  let submenu = page.locator(".session-project-submenu");
  await submenu.waitFor({ state: "visible" });
  const triggerHit = await page.evaluate(({ x, y }) => {
    const hit = document.elementFromPoint(x, y);
    const triggerElement = document.querySelector('[data-action="project"]');
    const submenuElement = document.querySelector(".session-project-submenu");
    return {
      matches: hit?.closest?.('[data-action="project"]') != null,
      hit: hit?.tagName || "",
      trigger: triggerElement?.getBoundingClientRect().toJSON(),
      submenu: submenuElement?.getBoundingClientRect().toJSON(),
      viewport: { width: innerWidth, height: innerHeight },
    };
  }, triggerPoint);
  assert.equal(triggerHit.matches, true, JSON.stringify(triggerHit));
  assert.equal(await submenu.getAttribute("data-locked"), "false");
  assert.equal(
    await submenu.locator(`[data-project-id="${seed.originalProject.id}"]`).count(),
    0,
  );
  assert.equal(
    await submenu.locator(`[data-project-id="${seed.targetProject.id}"]`).count(),
    1,
  );
  assert.equal(await submenu.locator('[data-project-action="remove"]').count(), 1);
  assert.equal(await submenu.locator('[data-project-action="create"]').count(), 0);
  const submenuMetrics = await submenu.evaluate((element) => {
    const style = getComputedStyle(element);
    const longItem = element.querySelector('[data-project-name^="A very long"] span');
    const itemHeights = [...element.querySelectorAll('[role="menuitem"]')]
      .map((item) => item.getBoundingClientRect().height);
    return {
      width: element.getBoundingClientRect().width,
      minWidth: parseFloat(style.minWidth),
      maxItemHeightFloor: Math.min(...itemHeights),
      longItemClipped: Boolean(longItem && longItem.scrollWidth > longItem.clientWidth),
    };
  });
  assert.equal(submenuMetrics.minWidth < 210, true);
  assert.equal(submenuMetrics.width <= 240.5, true);
  assert.equal(submenuMetrics.maxItemHeightFloor >= 30, true);
  assert.equal(submenuMetrics.longItemClipped, true);

  const longItem = submenu.locator(`[data-project-id="${seed.longProject.id}"]`);
  const shortItem = submenu.locator(`[data-project-id="${seed.targetProject.id}"]`);
  assert.equal(await longItem.getAttribute("data-tooltip"), seed.longProject.label);
  assert.equal(await longItem.evaluate((element) => (
    element.classList.contains("session-project-tooltip-target")
  )), true);
  assert.equal(await shortItem.getAttribute("data-tooltip"), null);
  assert.equal(await shortItem.evaluate((element) => (
    element.classList.contains("session-project-tooltip-target")
  )), false);
  const menuBeforeTooltip = await submenu.boundingBox();
  await longItem.hover();
  await page.waitForTimeout(100);
  let tooltip = page.locator(".sb-path-tooltip.session-project-tooltip:not([hidden])");
  assert.equal(await tooltip.count(), 0);
  await tooltip.waitFor({ state: "visible", timeout: 1_000 });
  assert.equal(await tooltip.textContent(), seed.longProject.label);
  const tooltipMetrics = await tooltip.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      pointerEvents: getComputedStyle(element).pointerEvents,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
    };
  });
  assert.equal(tooltipMetrics.width <= 320.5, true, JSON.stringify(tooltipMetrics));
  assert.equal(tooltipMetrics.height > 34, true, JSON.stringify(tooltipMetrics));
  assert.equal(tooltipMetrics.left >= 8, true);
  assert.equal(tooltipMetrics.right <= tooltipMetrics.viewportWidth - 7.5, true);
  assert.equal(tooltipMetrics.top >= 8, true);
  assert.equal(tooltipMetrics.bottom <= tooltipMetrics.viewportHeight - 7.5, true);
  assert.equal(tooltipMetrics.pointerEvents, "none");
  const menuAfterTooltip = await submenu.boundingBox();
  assert.deepEqual(menuAfterTooltip, menuBeforeTooltip);

  // Keyboard focus shows the same non-interactive overlay immediately, then
  // moving focus to another menu item hides it without disturbing the menu.
  await submenu.locator(".session-menu-separator").hover();
  await tooltip.waitFor({ state: "hidden" });
  await longItem.focus();
  tooltip = page.locator(".sb-path-tooltip.session-project-tooltip:not([hidden])");
  await tooltip.waitFor({ state: "visible" });
  await page.keyboard.press("ArrowDown");
  await tooltip.waitFor({ state: "hidden" });
  assert.deepEqual(await submenu.boundingBox(), menuBeforeTooltip);

  await submenu.hover();
  await page.waitForTimeout(120);
  assert.equal(await submenu.count(), 1);
  await movePointerOutside(page);
  await submenu.waitFor({ state: "detached" });
  assert.equal(await menu.count(), 1);

  // Clicking a transient submenu locks it. Pointer exit no longer closes it;
  // a second trigger click toggles it closed.
  await pointerPoint(page, trigger);
  submenu = page.locator(".session-project-submenu");
  await submenu.waitFor({ state: "visible" });
  await clickPointerTarget(page, trigger);
  assert.equal(await submenu.getAttribute("data-locked"), "true");
  await movePointerOutside(page);
  await page.waitForTimeout(120);
  assert.equal(await submenu.count(), 1);
  await clickPointerTarget(page, trigger);
  await submenu.waitFor({ state: "detached" });

  // Outside click and Escape both close a locked submenu and its parent menu.
  await clickPointerTarget(page, trigger);
  submenu = page.locator(".session-project-submenu");
  await submenu.waitFor({ state: "visible" });
  assert.equal(await submenu.getAttribute("data-locked"), "true");
  await movePointerOutside(page, { click: true });
  await menu.waitFor({ state: "detached" });

  await more.click();
  menu = page.locator(".session-more-menu:not(.session-project-submenu)");
  await menu.waitFor({ state: "visible" });
  trigger = menu.locator('[data-action="project"]');
  await clickPointerTarget(page, trigger);
  submenu = page.locator(".session-project-submenu");
  await submenu.waitFor({ state: "visible" });
  await page.keyboard.press("Escape");
  await menu.waitFor({ state: "detached" });
  assert.equal(await more.evaluate((element) => element === document.activeElement), true);

  return {
    hoverOpen: "pass",
    hoverBridge: "pass",
    hoverExit: "pass",
    clickLock: "pass",
    clickToggle: "pass",
    outsideClose: "pass",
    escapeClose: "pass",
    currentProjectHidden: "pass",
    compactRootWidth: Math.round(menuBox.width),
    compactSubmenuMinWidth: submenuMetrics.minWidth,
    longNameEllipsis: "pass",
    longTooltipDelay: "pass",
    shortTooltipAbsent: "pass",
    keyboardTooltip: "pass",
    tooltipWidth: Math.round(tooltipMetrics.width),
    tooltipWrap: "pass",
    tooltipViewportAvoidance: "pass",
    tooltipDoesNotResizeMenu: "pass",
    minimumItemHeight: submenuMetrics.maxItemHeightFloor,
  };
}

async function exerciseLongRemoveTooltip(page, host, seed, sessionId) {
  const { submenu } = await openProjectSubmenu(page, sessionId);
  const remove = submenu.locator('[data-project-action="remove"]');
  const expected = `Remove from "${seed.longProject.label}"`;
  assert.equal(await remove.getAttribute("data-tooltip"), expected);
  assert.equal(await remove.evaluate((element) => (
    element.classList.contains("session-project-tooltip-target")
  )), true);
  const menuBeforeTooltip = await submenu.boundingBox();
  await remove.hover();
  const tooltip = page.locator(".sb-path-tooltip.session-project-tooltip:not([hidden])");
  await tooltip.waitFor({ state: "visible" });
  assert.equal(await tooltip.textContent(), expected);
  const metrics = await tooltip.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
    };
  });
  assert.equal(metrics.width <= 320.5, true, JSON.stringify(metrics));
  assert.equal(metrics.height > 34, true, JSON.stringify(metrics));
  assert.equal(metrics.left >= 8, true);
  assert.equal(metrics.right <= metrics.viewportWidth - 7.5, true);
  assert.equal(metrics.top >= 8, true);
  assert.equal(metrics.bottom <= metrics.viewportHeight - 7.5, true);
  assert.deepEqual(await submenu.boundingBox(), menuBeforeTooltip);
  await remove.focus();
  await page.keyboard.press("Enter");
  const removed = await waitForSession(
    host,
    sessionId,
    (session) => session.projectId == null,
    "long-name Session did not move out of its project",
  );
  assert.equal(path.resolve(removed.cwd), path.resolve(seed.longProjectRoot));
  return {
    longRemoveTooltip: "pass",
    removeStillSucceeds: "pass",
    tooltipWidth: Math.round(metrics.width),
    tooltipWrap: "pass",
    tooltipViewportAvoidance: "pass",
    tooltipDoesNotResizeMenu: "pass",
  };
}

async function selectProjectFromMenu(page, sessionId, project) {
  const { submenu } = await openProjectSubmenu(page, sessionId);
  const item = submenu.locator(`[data-project-id="${project.id}"]`);
  assert.equal(await item.isDisabled(), false);
  await item.focus();
  await page.keyboard.press("Enter");
}

async function openMigrationConfirm(page, sessionId, project) {
  await selectProjectFromMenu(page, sessionId, project);
  const modal = page.locator(".session-project-migration-modal");
  await modal.waitFor({ state: "visible" });
  return modal;
}

async function moveToProject(page, host, sessionId, project) {
  await selectProjectFromMenu(page, sessionId, project);
  assert.equal(await page.locator(".session-project-migration-modal").count(), 0);
  return waitForSession(
    host,
    sessionId,
    (session) => session.projectId === project.id,
    "Session did not move to target project",
  );
}

const SESSION_PROJECT_DRAG_MIME = "application/x-workbar-session-project-move";

function projectDropBlock(page, projectId) {
  return page.locator(
    `.project-block[data-project-id="${projectId}"][data-project-key="${projectId}"]`,
  );
}

function unassignedDropBlock(page) {
  return page.locator(
    '.project-block[data-project-key="__unassigned_sessions__"]',
  );
}

async function sessionDragSource(page, sessionId) {
  const source = page.locator(
    `.session-row[data-session-id="${sessionId}"] .session-main[draggable="true"]`,
  );
  await source.scrollIntoViewIfNeeded();
  await source.waitFor({ state: "visible" });
  return source;
}

async function dragSessionToTargetWithNativeDrag(page, sessionId, target) {
  const source = await sessionDragSource(page, sessionId);
  await target.scrollIntoViewIfNeeded();
  await source.dragTo(target);
}

async function dragSessionToVisibleTargetWithMouse(page, sessionId, target) {
  const source = await sessionDragSource(page, sessionId);
  await target.scrollIntoViewIfNeeded();
  await source.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  assert.ok(sourceBox, `Missing visible native drag source for ${sessionId}`);
  assert.ok(targetBox, `Missing visible native drag target for ${sessionId}`);
  await target.evaluate((element) => { window.__code071NativeDropTarget = element; });
  let pointerDown = false;
  try {
    const startX = sourceBox.x + Math.min(28, sourceBox.width / 3);
    const startY = sourceBox.y + sourceBox.height / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    pointerDown = true;
    await page.mouse.move(startX + 12, startY, { steps: 4 });
    await page.waitForFunction((id) => (
      document.querySelector(
        `.session-row[data-session-id="${CSS.escape(id)}"]`,
      )?.classList.contains("is-session-project-drag-source")
    ), sessionId);
    await page.mouse.move(
      targetBox.x + targetBox.width / 2,
      targetBox.y + targetBox.height / 2,
      { steps: 14 },
    );
    await page.waitForFunction(() => (
      window.__code071NativeDropTarget?.closest(".project-block")?.classList.contains(
        "is-session-project-drop-over",
      )
    ));
  } finally {
    if (pointerDown) await page.mouse.up();
    await page.evaluate(() => { delete window.__code071NativeDropTarget; });
  }
}

async function dragSessionToBlock(page, sessionId, block) {
  await sessionDragSource(page, sessionId);
  await block.scrollIntoViewIfNeeded();
  const selector = await block.evaluate((element) => {
    const projectId = element.dataset.projectId;
    const projectKey = element.dataset.projectKey;
    if (projectId) {
      return `.project-block[data-project-id="${CSS.escape(projectId)}"]`;
    }
    return `.project-block[data-project-key="${CSS.escape(projectKey || "")}"]`;
  });
  await beginSyntheticSessionDrag(page, sessionId);
  return dispatchSyntheticSessionDrop(page, selector);
}

async function beginSyntheticSessionDrag(page, sessionId) {
  return page.evaluate(({ id, mime }) => {
    const source = document.querySelector(
      `.session-row[data-session-id="${CSS.escape(id)}"] .session-main[draggable]`,
    );
    if (!source) throw new Error(`Missing drag source for ${id}`);
    const dataTransfer = new DataTransfer();
    const event = new DragEvent("dragstart", {
      bubbles: true,
      cancelable: true,
      dataTransfer,
    });
    const dispatched = source.dispatchEvent(event);
    window.__code071SessionDrag = { source, dataTransfer };
    const ghost = document.querySelector(".session-project-drag-ghost");
    return {
      dispatched,
      defaultPrevented: event.defaultPrevented,
      types: Array.from(dataTransfer.types),
      payload: dataTransfer.getData(mime),
      text: dataTransfer.getData("text/plain"),
      html: dataTransfer.getData("text/html"),
      sourceActive: Boolean(source.closest(".session-row")?.classList.contains(
        "is-session-project-drag-source",
      )),
      available: document.querySelectorAll(
        ".project-block.is-session-project-drop-available",
      ).length,
      noop: document.querySelectorAll(
        ".project-block.is-session-project-drop-noop",
      ).length,
      invalid: document.querySelectorAll(
        ".project-block.is-session-project-drop-invalid",
      ).length,
      ghostCount: document.querySelectorAll(".session-project-drag-ghost").length,
      ghostText: ghost?.textContent || "",
      temporary: document.querySelectorAll(".session-project-drop-temporary").length,
    };
  }, { id: sessionId, mime: SESSION_PROJECT_DRAG_MIME });
}

async function exerciseSessionProjectPointerHitMatrix(page, sourceKey, targetKey) {
  return page.evaluate(({ noopKey, moveKey }) => {
    const root = document.querySelector("#sessionList");
    const drag = window.__code071SessionDrag;
    if (!root || !drag?.dataTransfer) throw new Error("Pointer hit matrix unavailable");
    const existingBlocks = Array.from(root.querySelectorAll(".project-block"));
    const savedDisplays = existingBlocks.map((block) => block.style.display);
    existingBlocks.forEach((block) => { block.style.display = "none"; });
    const listRect = root.getBoundingClientRect();
    const baseTop = listRect.top + Math.max(64, Math.min(100, listRect.height / 3));
    const blockHeight = 44;
    const makeBlock = (key, top) => {
      const block = document.createElement("div");
      block.className = "project-block code071-pointer-hit-block";
      block.dataset.projectKey = key;
      block.style.position = "fixed";
      block.style.left = `${listRect.left + 8}px`;
      block.style.top = `${top}px`;
      block.style.width = `${Math.max(24, listRect.width - 16)}px`;
      block.style.height = `${blockHeight}px`;
      block.style.margin = "0";
      block.style.padding = "0";
      root.appendChild(block);
      return block;
    };
    const first = makeBlock(noopKey, baseTop);
    const second = makeBlock(moveKey, baseTop + blockHeight + 16);
    const setTop = (block, top) => { block.style.top = `${top}px`; };
    const dispatch = (clientX, clientY) => {
      const event = new DragEvent("dragover", {
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
        dataTransfer: drag.dataTransfer,
      });
      root.dispatchEvent(event);
      return {
        defaultPrevented: event.defaultPrevented,
        dropEffect: drag.dataTransfer.dropEffect,
        hovered: Array.from(root.querySelectorAll(
          ".project-block.is-session-project-drop-over",
        )).map((block) => block.dataset.projectKey || ""),
      };
    };
    const centerX = listRect.left + listRect.width / 2;
    let result;
    try {
      let firstRect = first.getBoundingClientRect();
      let secondRect = second.getBoundingClientRect();
      const inside = dispatch(centerX, secondRect.top + secondRect.height / 2);
      const snapUpper = dispatch(centerX, firstRect.bottom + 6);
      const snapLower = dispatch(centerX, secondRect.top - 6);
      const tie = dispatch(centerX, firstRect.bottom + 8);

      setTop(second, firstRect.bottom + 20);
      secondRect = second.getBoundingClientRect();
      const beyond = dispatch(centerX, firstRect.bottom + 10);
      const horizontalOutside = dispatch(listRect.left - 1, firstRect.top + 12);

      setTop(first, baseTop);
      setTop(second, baseTop + blockHeight + 16);
      firstRect = first.getBoundingClientRect();
      const stationaryY = firstRect.top + firstRect.height / 2;
      const beforeRectChange = dispatch(centerX, stationaryY);
      setTop(first, baseTop - blockHeight - 40);
      setTop(second, stationaryY - blockHeight / 2);
      const afterRectChange = dispatch(centerX, stationaryY);
      result = {
        inside,
        snapUpper,
        snapLower,
        tie,
        beyond,
        horizontalOutside,
        beforeRectChange,
        afterRectChange,
      };
      dispatch(listRect.left - 1, listRect.top - 1);
    } finally {
      first.remove();
      second.remove();
      existingBlocks.forEach((block, index) => {
        block.style.display = savedDisplays[index];
      });
    }
    return result;
  }, { noopKey: sourceKey, moveKey: targetKey });
}

async function hoverSyntheticSessionProjectTarget(page, selector) {
  return page.evaluate((targetSelector) => {
    const root = document.querySelector("#sessionList");
    const target = document.querySelector(targetSelector);
    const drag = window.__code071SessionDrag;
    if (!root || !target || !drag?.dataTransfer) {
      throw new Error(`Synthetic hover target unavailable: ${targetSelector}`);
    }
    target.scrollIntoView({ block: "center", inline: "nearest" });
    const targetRect = target.getBoundingClientRect();
    const targetStyle = getComputedStyle(target);
    const text = target.querySelector(".project-name, .session-project-drop-temporary-name");
    const background = targetStyle.backgroundColor;
    const boxShadow = targetStyle.boxShadow;
    const textColor = text ? getComputedStyle(text).color : "";
    const clientX = targetRect.left + targetRect.width / 2;
    const clientY = targetRect.top + targetRect.height / 2;
    const dispatch = (type) => {
      const event = new DragEvent(type, {
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
        dataTransfer: drag.dataTransfer,
      });
      root.dispatchEvent(event);
      return event.defaultPrevented;
    };
    dispatch("dragenter");
    const defaultPrevented = dispatch("dragover");
    return {
      defaultPrevented,
      background,
      boxShadow,
      textColor,
      rect: {
        x: targetRect.x,
        y: targetRect.y,
        width: targetRect.width,
        height: targetRect.height,
      },
      hovered: Array.from(root.querySelectorAll(
        ".project-block.is-session-project-drop-over",
      )).map((block) => block.dataset.projectKey || ""),
    };
  }, selector);
}

async function dispatchSyntheticSessionDrop(
  page,
  selector,
  repeat = 1,
  pointerSelector = selector,
) {
  return page.evaluate(({ targetSelector, pointerTargetSelector, dropCount }) => {
    const target = document.querySelector(targetSelector);
    const pointerTarget = document.querySelector(pointerTargetSelector);
    const drag = window.__code071SessionDrag;
    if (!target || !pointerTarget || !drag?.dataTransfer) {
      throw new Error(`Synthetic drag target unavailable: ${targetSelector}`);
    }
    pointerTarget.scrollIntoView({ block: "center", inline: "nearest" });
    const pointerRect = pointerTarget.getBoundingClientRect();
    const clientX = pointerRect.left + pointerRect.width / 2;
    const clientY = pointerRect.top + pointerRect.height / 2;
    const dispatch = (type) => {
      const event = new DragEvent(type, {
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
        dataTransfer: drag.dataTransfer,
      });
      const dispatched = target.dispatchEvent(event);
      return {
        dispatched,
        defaultPrevented: event.defaultPrevented,
      };
    };
    const dragenter = dispatch("dragenter");
    const dragover = dispatch("dragover");
    const hoveredAfterDragover = Array.from(document.querySelectorAll(
      ".project-block.is-session-project-drop-over",
    )).map((block) => block.dataset.projectKey || "");
    const drops = [];
    for (let index = 0; index < dropCount; index += 1) drops.push(dispatch("drop"));
    drag.source?.dispatchEvent(new DragEvent("dragend", {
      bubbles: true,
      cancelable: false,
      dataTransfer: drag.dataTransfer,
    }));
    delete window.__code071SessionDrag;
    return { dragenter, dragover, hoveredAfterDragover, drops };
  }, {
    targetSelector: selector,
    pointerTargetSelector: pointerSelector,
    dropCount: repeat,
  });
}

async function endSyntheticSessionDrag(page) {
  await page.evaluate(() => {
    const drag = window.__code071SessionDrag;
    drag?.source?.dispatchEvent(new DragEvent("dragend", {
      bubbles: true,
      cancelable: false,
      dataTransfer: drag.dataTransfer,
    }));
    delete window.__code071SessionDrag;
  });
}

async function assertSessionDragUiCleared(page, { includePending = true } = {}) {
  await page.waitForFunction((checkPending) => {
    const transientCount = document.querySelectorAll([
      ".is-session-project-drag-source",
      ".is-session-project-drop-available",
      ".is-session-project-drop-noop",
      ".is-session-project-drop-invalid",
      ".is-session-project-drop-over",
      ".session-project-drag-ghost",
      ".session-project-drop-temporary",
    ].join(", ")).length;
    const rootActive = document.querySelector("#sessionList")?.classList.contains(
      "is-session-project-dragging",
    );
    const pendingCount = checkPending
      ? document.querySelectorAll(".is-session-project-migration-pending").length
      : 0;
    return transientCount === 0 && !rootActive && pendingCount === 0;
  }, includePending);
}

function sessionMigrationRequestCounts(sessionId, projectRequests, projectPreviews) {
  const encodedId = encodeURIComponent(sessionId);
  const commitPath = `/api/sessions/${encodedId}/project`;
  const previewPath = `${commitPath}/preview`;
  return {
    commits: projectRequests.filter((request) => request.path === commitPath).length,
    previews: projectPreviews.filter((request) => request.path === previewPath).length,
  };
}

async function browseHome(page, host) {
  await page.locator("#projectRootShort").click();
  await page.locator("#cwdHomeBtn").click();
  await waitForRoot(page, host.homeDir);
}

async function exercisePrimaryEditor(page, host, seed, { currentPrimary, nextPrimary }) {
  const sessionBefore = await sessionRecord(host, seed.editorSession.id);
  const projectBefore = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.editorProject.id);
  assert.match(projectBefore.stateToken, /^[0-9a-f]{64}$/);
  const header = page.locator(
    `.project-header[data-project-id="${seed.editorProject.id}"]`,
  );
  await header.click({ button: "right" });
  const menu = page.locator(".project-context-menu");
  await menu.waitFor({ state: "visible" });
  await menu.locator('[data-action="edit"]').click();

  const modal = page.locator("#projectEditModal");
  await modal.waitFor({ state: "visible" });
  let rows = modal.locator(".project-source-folder-row");
  assert.equal(await rows.count(), 2);
  assert.equal(
    await rows.nth(0).locator(".project-source-folder-name").textContent(),
    path.basename(currentPrimary),
  );
  assert.equal(await rows.nth(0).locator(".project-source-folder-remove").isDisabled(), true);

  await rows.nth(1).locator('[data-project-folder-action="primary"]').click();
  rows = modal.locator(".project-source-folder-row");
  assert.equal(
    await rows.nth(0).locator(".project-source-folder-name").textContent(),
    path.basename(nextPrimary),
  );
  assert.equal(await rows.nth(0).locator(".project-source-folder-remove").isDisabled(), true);
  assert.equal(
    await rows.nth(1).locator(".project-source-folder-name").textContent(),
    path.basename(currentPrimary),
  );
  assert.equal(await rows.nth(1).locator(".project-source-folder-remove").isDisabled(), true);

  const updateRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST"
      && url.pathname === `/api/projects/${seed.editorProject.id}/update`;
  });
  await modal.locator("#saveProjectEdit").click();
  const updateRequest = await updateRequestPromise;
  const updateBody = updateRequest.postDataJSON();
  assert.equal(updateBody.expectedStateToken, projectBefore.stateToken);
  assert.equal(path.resolve(updateBody.primaryRootPath), path.resolve(nextPrimary));
  assert.deepEqual(
    updateBody.rootPaths.map((rootPath) => path.resolve(rootPath)),
    [path.resolve(nextPrimary), path.resolve(currentPrimary)],
  );
  await modal.waitFor({ state: "hidden" });

  const updatedProject = await waitUntil(
    async () => {
      const projects = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
      return projects.find((project) => project.id === seed.editorProject.id);
    },
    (project) => path.resolve(project?.rootPaths?.[0] || "") === path.resolve(nextPrimary),
    "explicit primary switch did not persist",
  );
  const sessionAfter = await sessionRecord(host, seed.editorSession.id);
  for (const key of ["projectId", "cwd", "revision", "updatedAt"]) {
    assert.equal(sessionAfter[key], sessionBefore[key], `Session ${key} changed during primary switch`);
  }
  assert.equal(path.resolve(updatedProject.rootPaths[1]), path.resolve(currentPrimary));
  assert.notEqual(updatedProject.stateToken, projectBefore.stateToken);
  return {
    explicitIntent: "pass",
    stateCas: "pass",
    oldPrimaryRetained: "pass",
    sameUpdateRemovalBlocked: "pass",
    sessionLocationUnchanged: "pass",
  };
}

async function exerciseProjectEditorConflict(page, host, seed) {
  const projectBefore = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.editorProject.id);
  const sessionBefore = await sessionRecord(host, seed.editorSession.id);
  const header = page.locator(
    `.project-header[data-project-id="${seed.editorProject.id}"]`,
  );
  await header.click({ button: "right" });
  const menu = page.locator(".project-context-menu");
  await menu.waitFor({ state: "visible" });
  await menu.locator('[data-action="edit"]').click();

  const modal = page.locator("#projectEditModal");
  await modal.waitFor({ state: "visible" });
  const concurrentLabel = "Primary editor project refreshed";
  const renamed = (await requestJson(
    host.ready.codeUrl,
    `/api/projects/${seed.editorProject.id}/rename`,
    {
      method: "POST",
      body: JSON.stringify({ label: concurrentLabel }),
    },
  )).payload;
  assert.notEqual(renamed.stateToken, projectBefore.stateToken);

  let rows = modal.locator(".project-source-folder-row");
  await rows.nth(1).locator('[data-project-folder-action="primary"]').click();
  const conflictResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname === `/api/projects/${seed.editorProject.id}/update`;
  });
  const conflictRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST"
      && url.pathname === `/api/projects/${seed.editorProject.id}/update`;
  });
  await modal.locator("#saveProjectEdit").click();
  const [conflictRequest, conflictResponse] = await Promise.all([
    conflictRequestPromise,
    conflictResponsePromise,
  ]);
  assert.equal(conflictResponse.status(), 409);
  assert.equal(
    (await conflictResponse.json()).errorCode,
    "project_state_conflict",
  );
  assert.equal(
    conflictRequest.postDataJSON().expectedStateToken,
    projectBefore.stateToken,
  );

  await waitUntil(
    () => modal.locator("#projectEditName").inputValue(),
    (value) => value === concurrentLabel,
    "stale project editor did not load the authoritative label",
  );
  rows = modal.locator(".project-source-folder-row");
  assert.equal(
    await rows.nth(0).locator(".project-source-folder-name").textContent(),
    path.basename(seed.editorSecondary),
  );
  assert.equal(await rows.nth(1).locator(".project-source-folder-remove").isDisabled(), false);
  const conflictToast = page.locator(".toast.error").filter({
    hasText: "This project changed elsewhere. The latest state is loaded; review it and try again",
  });
  await conflictToast.waitFor({ state: "visible" });

  const projectAfter = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.editorProject.id);
  assert.equal(path.resolve(projectAfter.rootPaths[0]), path.resolve(seed.editorSecondary));
  assert.equal(projectAfter.label, concurrentLabel);
  assert.equal(projectAfter.stateToken, renamed.stateToken);
  const sessionAfter = await sessionRecord(host, seed.editorSession.id);
  for (const key of ["projectId", "cwd", "revision", "updatedAt"]) {
    assert.equal(sessionAfter[key], sessionBefore[key], `Session ${key} changed on CAS conflict`);
  }
  await modal.locator("#cancelProjectEdit").click();
  await modal.waitFor({ state: "hidden" });
  return {
    staleRejected: "pass",
    authoritativeStateReloaded: "pass",
    noAutomaticRetry: "pass",
    sessionLocationUnchanged: "pass",
  };
}

async function exerciseCreatePrimaryConflict(page, host, seed) {
  const projectsBefore = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  const pickerPattern = "**/api/pick-folder*";
  const pickerHandler = async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ cancelled: false, path: seed.targetPrimary }),
    });
  };
  await page.route(pickerPattern, pickerHandler);
  try {
    await page.locator("#projectCreateBtn").click();
    const toast = page.locator("#toastContainer .toast.error").filter({
      hasText: seed.targetPrimary,
    });
    await toast.waitFor({ state: "visible" });
    const text = await toast.textContent();
    assert.equal(text.includes(seed.targetPrimary), true);
    assert.equal(text.includes(seed.targetProject.label), true);
  } finally {
    await page.unroute(pickerPattern, pickerHandler);
  }
  const projectsAfter = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  assert.deepEqual(projectsAfter, projectsBefore);
  return { exactFolder: "pass", occupyingProject: "pass", zeroWrite: "pass" };
}

async function exerciseEditPrimaryConflict(page, host, seed) {
  const projectBefore = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.conflictEditorProject.id);
  const header = page.locator(
    `.project-header[data-project-id="${seed.conflictEditorProject.id}"]`,
  );
  await header.scrollIntoViewIfNeeded();
  await header.click({ button: "right" });
  const menu = page.locator(".project-context-menu");
  await menu.waitFor({ state: "visible" });
  await menu.locator('[data-action="edit"]').click();
  const modal = page.locator("#projectEditModal");
  await modal.waitFor({ state: "visible" });
  const rows = modal.locator(".project-source-folder-row");
  assert.equal(await rows.count(), 2);
  await rows.nth(1).locator('[data-project-folder-action="primary"]').click();
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname === `/api/projects/${seed.conflictEditorProject.id}/update`;
  });
  await modal.locator("#saveProjectEdit").click();
  const response = await responsePromise;
  assert.equal(response.status(), 409);
  const payload = await response.json();
  assert.equal(payload.errorCode, "project_primary_conflict");
  assert.equal(payload.conflictRootPath, seed.targetPrimary);
  assert.deepEqual(payload.conflictingProject, {
    id: seed.targetProject.id,
    label: seed.targetProject.label,
  });
  const toast = page.locator("#toastContainer .toast.error").filter({
    hasText: seed.targetPrimary,
  }).last();
  await toast.waitFor({ state: "visible" });
  const text = await toast.textContent();
  assert.equal(text.includes(seed.targetPrimary), true);
  assert.equal(text.includes(seed.targetProject.label), true);
  const projectAfter = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.conflictEditorProject.id);
  assert.equal(projectAfter.stateToken, projectBefore.stateToken);
  await modal.locator("#cancelProjectEdit").click();
  await modal.waitFor({ state: "hidden" });
  return { exactFolder: "pass", occupyingProject: "pass", zeroWrite: "pass" };
}

async function exerciseMigrationConfirmation(
  page,
  host,
  seed,
  projectRequests,
  projectPreviews,
) {
  const sessionBefore = await sessionRecord(host, seed.current.id);
  const projectsBefore = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  const sourceBefore = projectsBefore.find((project) => project.id === seed.originalProject.id);
  const targetBefore = projectsBefore.find((project) => project.id === seed.targetProject.id);
  const putCountBefore = projectRequests.length;
  const previewCountBefore = projectPreviews.length;
  let layout = null;

  for (const action of ["cancel", "escape", "close"]) {
    const modal = await openMigrationConfirm(
      page,
      seed.current.id,
      seed.targetProject,
    );
    const cancel = modal.locator(".session-project-migration-cancel");
    assert.equal(await cancel.evaluate((element) => element === document.activeElement), true);
    if (!layout) {
      assert.equal(await modal.getAttribute("class"), "settings-modal session-project-migration-modal");
      const modalText = await modal.textContent();
      assert.match(modalText, /Add folders to "Target project"\?/);
      assert.match(modalText, /Every Session in "Target project" will gain access/);
      for (const removedText of [
        "Already covered by the target",
        "Working directory after the move",
        "remains unchanged",
        "No files on disk",
      ]) assert.equal(modalText.includes(removedText), false);
      assert.equal(
        await modal.locator(".session-project-migration-confirm").textContent(),
        "Continue",
      );
      const folders = modal.locator(".session-project-migration-folder");
      assert.equal(await folders.count(), 3);
      assert.deepEqual(
        await folders.locator(".session-project-migration-folder-name").allTextContents(),
        [path.basename(host.projectDir), "shared-src", "shared-src"],
      );
      assert.deepEqual(
        await folders.locator(".session-project-migration-folder-context").allTextContents(),
        [path.dirname(seed.duplicateRootA), path.dirname(seed.duplicateRootB)],
      );
      const folderDetails = await folders.evaluateAll((items) => items.map((item) => ({
        title: item.getAttribute("title"),
        ariaLabel: item.getAttribute("aria-label"),
      })));
      for (const expectedPath of [host.projectDir, seed.duplicateRootA, seed.duplicateRootB]) {
        const detail = folderDetails.find((item) => item.title === expectedPath);
        assert.ok(detail);
        assert.equal(detail.ariaLabel.includes(expectedPath), true);
      }
      layout = await modal.locator(".session-project-migration-card").evaluate((card) => {
        const rect = card.getBoundingClientRect();
        const folderNodes = [...card.querySelectorAll(".session-project-migration-folder")];
        return {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          viewportWidth: innerWidth,
          viewportHeight: innerHeight,
          pathsFit: folderNodes.every((node) => node.scrollWidth <= node.clientWidth + 1),
        };
      });
      assert.equal(layout.left >= 9.5, true, JSON.stringify(layout));
      assert.equal(layout.right <= layout.viewportWidth - 9.5, true, JSON.stringify(layout));
      assert.equal(layout.top >= 9.5, true, JSON.stringify(layout));
      assert.equal(layout.bottom <= layout.viewportHeight - 9.5, true, JSON.stringify(layout));
      assert.equal(layout.pathsFit, true, JSON.stringify(layout));
    }
    if (action === "cancel") await cancel.click();
    if (action === "escape") await page.keyboard.press("Escape");
    if (action === "close") await modal.locator(".session-project-migration-close").click();
    await modal.waitFor({ state: "detached" });
    const more = page.locator(`.session-more-btn[data-session-id="${seed.current.id}"]`);
    assert.equal(await more.evaluate((element) => element === document.activeElement), true);
    const unchanged = await sessionRecord(host, seed.current.id);
    assert.equal(unchanged.projectId, sessionBefore.projectId);
    assert.equal(unchanged.revision, sessionBefore.revision);
    assert.equal(path.resolve(unchanged.cwd), path.resolve(sessionBefore.cwd));
    assert.equal(projectRequests.length, putCountBefore);
  }

  const modal = await openMigrationConfirm(page, seed.current.id, seed.targetProject);
  await modal.locator(".session-project-migration-confirm").click();
  await modal.waitFor({ state: "detached" });
  const moved = await waitForSession(
    host,
    seed.current.id,
    (session) => session.projectId === seed.targetProject.id,
    "confirmed Session migration did not commit",
  );
  assert.equal(path.resolve(moved.cwd), path.resolve(host.projectDir));
  assert.equal(moved.revision, sessionBefore.revision + 1);
  await waitForRoot(page, host.projectDir);
  assert.equal(projectRequests.length, putCountBefore + 1);
  assert.equal(projectPreviews.length, previewCountBefore + 4);
  const commitBody = projectRequests.at(-1).body;
  assert.deepEqual(Object.keys(commitBody).sort(), ["expectedRevision", "planToken", "projectId"]);
  assert.match(commitBody.planToken, /^v1\.[A-Za-z0-9_-]+\.[0-9a-f]{64}$/);
  assert.equal(Object.prototype.hasOwnProperty.call(commitBody, "rootsToAdd"), false);

  const projectsAfter = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  const sourceAfter = projectsAfter.find((project) => project.id === seed.originalProject.id);
  const targetAfter = projectsAfter.find((project) => project.id === seed.targetProject.id);
  assert.deepEqual(sourceAfter.rootPaths, sourceBefore.rootPaths);
  assert.equal(sourceAfter.stateToken, sourceBefore.stateToken);
  assert.equal(path.resolve(targetAfter.rootPaths[0]), path.resolve(targetBefore.rootPaths[0]));
  assert.deepEqual(
    targetAfter.rootPaths.map((root) => path.resolve(root)),
    [
      path.resolve(seed.targetPrimary),
      path.resolve(seed.targetSecondary),
      path.resolve(host.projectDir),
      path.resolve(seed.duplicateRootA),
      path.resolve(seed.duplicateRootB),
    ],
  );
  return {
    cancelZeroWrite: "pass",
    escapeZeroWrite: "pass",
    closeZeroWrite: "pass",
    focusDefault: "pass",
    compactSharedAccessCopy: "pass",
    duplicateFoldersDistinguished: "pass",
    sourceRetained: "pass",
    targetPrimaryRetained: "pass",
    serverTokenOnly: "pass",
    finalCwdExactRoot: "pass",
    narrowLayout: "pass",
    longPathWrap: "pass",
    layout,
  };
}

async function exerciseMigrationBlock(page, host, seed, projectRequests, projectPreviews) {
  const sessionBefore = await sessionRecord(host, seed.wide.id);
  const putCountBefore = projectRequests.length;
  const previewCountBefore = projectPreviews.length;
  await selectProjectFromMenu(page, seed.wide.id, seed.targetProject);
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "too broad",
  }).waitFor({ state: "visible" });
  assert.equal(await page.locator(".session-project-migration-modal").count(), 0);
  await page.waitForTimeout(150);
  assert.equal(projectRequests.length, putCountBefore);
  assert.equal(projectPreviews.length, previewCountBefore + 1);
  const sessionAfter = await sessionRecord(host, seed.wide.id);
  assert.equal(sessionAfter.projectId, sessionBefore.projectId);
  assert.equal(sessionAfter.revision, sessionBefore.revision);
  assert.equal(path.resolve(sessionAfter.cwd), path.resolve(sessionBefore.cwd));
  return { blockedBeforeConfirm: "pass", zeroWrite: "pass", noAutomaticRetry: "pass" };
}

async function exerciseMigrationConflict(page, host, seed, projectRequests, projectPreviews) {
  const sessionBefore = await sessionRecord(host, seed.conflict.id);
  const putCountBefore = projectRequests.length;
  const previewCountBefore = projectPreviews.length;
  await page.setViewportSize({ width: 390, height: 720 });
  const modal = await openMigrationConfirm(page, seed.conflict.id, seed.targetProject);
  const longFolder = modal.locator(".session-project-migration-folder");
  assert.equal(await longFolder.count(), 1);
  assert.equal(
    await longFolder.locator(".session-project-migration-folder-name").textContent(),
    path.basename(seed.conflictRoot),
  );
  assert.equal(await longFolder.getAttribute("title"), seed.conflictRoot);
  const narrowLayout = await modal.locator(".session-project-migration-card").evaluate((card) => {
    const rect = card.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      folderOverflow: card.querySelector(".session-project-migration-folder").scrollWidth
        > card.querySelector(".session-project-migration-folder").clientWidth + 1,
    };
  });
  assert.equal(narrowLayout.left >= 9.5, true, JSON.stringify(narrowLayout));
  assert.equal(narrowLayout.right <= narrowLayout.viewportWidth - 9.5, true, JSON.stringify(narrowLayout));
  assert.equal(narrowLayout.top >= 9.5, true, JSON.stringify(narrowLayout));
  assert.equal(narrowLayout.bottom <= narrowLayout.viewportHeight - 9.5, true, JSON.stringify(narrowLayout));
  assert.equal(narrowLayout.horizontalOverflow, false);
  assert.equal(narrowLayout.folderOverflow, false);
  const renamed = (await requestJson(
    host.ready.codeUrl,
    `/api/projects/${seed.targetProject.id}/rename`,
    {
      method: "POST",
      body: JSON.stringify({ label: "Target changed" }),
    },
  )).payload;
  await modal.locator(".session-project-migration-confirm").click();
  await modal.waitFor({ state: "detached" });
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "changed in another window",
  }).waitFor({ state: "visible" });
  await page.waitForTimeout(250);
  assert.equal(projectRequests.length, putCountBefore + 1);
  assert.equal(projectPreviews.length, previewCountBefore + 1);
  const sessionAfter = await sessionRecord(host, seed.conflict.id);
  assert.equal(sessionAfter.projectId, sessionBefore.projectId);
  assert.equal(sessionAfter.revision, sessionBefore.revision);
  assert.equal(path.resolve(sessionAfter.cwd), path.resolve(sessionBefore.cwd));
  const targetAfter = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === seed.targetProject.id);
  assert.equal(targetAfter.stateToken, renamed.stateToken);
  assert.equal(
    targetAfter.rootPaths.some((root) => path.resolve(root) === path.resolve(seed.conflictRoot)),
    false,
  );
  await page.setViewportSize({ width: 1280, height: 800 });
  return {
    staleRejected: "pass",
    zeroPartialWrite: "pass",
    noAutomaticRetry: "pass",
    longFolderName: "pass",
    narrowLayout: "pass",
  };
}

async function exerciseSessionProjectDrag(
  page,
  host,
  seed,
  fixture,
  projectRequests,
  projectPreviews,
  entryMode,
  options = {},
) {
  const visualOnly = Boolean(options.visualOnly);
  await page.setViewportSize({ width: 1280, height: 800 });
  const targetProject = fixture.targetProject;
  const targetSelector = `.project-block[data-project-id="${targetProject.id}"]`;
  const originalSelector = `.project-block[data-project-id="${seed.originalProject.id}"]`;
  const unassignedSelector = '.project-block[data-project-key="__unassigned_sessions__"]';
  const currentMain = page.locator(
    `.session-main[data-session-id="${fixture.current.id}"]`,
  );
  await currentMain.scrollIntoViewIfNeeded();
  await currentMain.click();
  await waitUntil(
    () => page.locator("#sessionTitle").inputValue(),
    (value) => value === fixture.current.title,
    `${entryMode} drag current Session did not load`,
  );
  await waitForRoot(page, host.projectDir);

  assert.equal(
    await page.locator(".session-project-drag-handle").count(),
    0,
  );
  assert.equal(
    await page.locator(
      `.session-row[data-session-id="${fixture.archived.id}"] .session-main[draggable]`,
    ).count(),
    0,
  );
  const actionAttributes = await page.locator(
    `.session-row[data-session-id="${fixture.current.id}"]`,
  ).evaluate((row) => ({
    main: row.querySelector(".session-main")?.getAttribute("draggable"),
    more: row.querySelector(".session-more-btn")?.getAttribute("draggable"),
    title: row.querySelector(".session-title-text")?.getAttribute("draggable"),
    handleCount: row.querySelectorAll(".session-project-drag-handle").length,
  }));
  assert.deepEqual(actionAttributes, {
    main: "true",
    more: null,
    title: null,
    handleCount: 0,
  });

  const requestCountBeforeVisual = projectRequests.length;
  const previewCountBeforeVisual = projectPreviews.length;
  const expansionBefore = await page.locator(".project-toggle").evaluateAll((toggles) => (
    toggles.map((toggle) => ({
      key: toggle.closest(".project-header")?.dataset.projectKey,
      expanded: toggle.getAttribute("aria-expanded"),
    }))
  ));
  const visualDrag = await beginSyntheticSessionDrag(page, fixture.current.id);
  assert.equal(visualDrag.dispatched, true);
  assert.equal(visualDrag.defaultPrevented, false);
  assert.deepEqual(visualDrag.types, [SESSION_PROJECT_DRAG_MIME]);
  assert.equal(visualDrag.payload, "workbar-session-project-move");
  assert.equal(visualDrag.text, "");
  assert.equal(visualDrag.html, "");
  assert.equal(visualDrag.sourceActive, true);
  assert.equal(visualDrag.available > 0, true);
  assert.equal(visualDrag.noop > 0, true);
  assert.equal(visualDrag.ghostCount, 1);
  assert.equal(visualDrag.ghostText, fixture.current.title);
  const visualState = await page.evaluate(({
    targetId,
    sourceId,
    longProjectId,
    expectedDark,
  }) => {
    const target = document.querySelector(
      `.project-block[data-project-id="${CSS.escape(targetId)}"]`,
    );
    const sourceRow = window.__code071SessionDrag?.source?.closest(".session-row")
      || document.querySelector(".session-row.is-session-project-drag-source");
    const source = sourceRow?.closest(".project-block") || document.querySelector(
      `.project-block[data-project-id="${CSS.escape(sourceId)}"]`,
    );
    const longName = document.querySelector(
      `.project-header[data-project-id="${CSS.escape(longProjectId)}"] .project-name`,
    );
    const ghost = document.querySelector(".session-project-drag-ghost");
    const list = document.querySelector("#sessionList");
    const elements = { target, source, sourceRow, ghost, list };
    const missing = Object.entries(elements)
      .filter(([, element]) => !(element instanceof Element))
      .map(([name]) => name);
    if (missing.length) return { missing, expectedDark };
    for (const element of [target, source, sourceRow]) {
      element.getAnimations().forEach((animation) => animation.finish());
    }
    const targetStyle = getComputedStyle(target);
    const sourceStyle = getComputedStyle(source);
    const sourceRowStyle = getComputedStyle(sourceRow);
    const ghostStyle = getComputedStyle(ghost);
    const sourceRect = source.getBoundingClientRect();
    const sourceRowRect = sourceRow.getBoundingClientRect();
    return {
      missing,
      targetAvailable: target.classList.contains("is-session-project-drop-available"),
      sourceNoop: source.classList.contains("is-session-project-drop-noop"),
      targetShadow: targetStyle.boxShadow,
      targetBackground: targetStyle.backgroundColor,
      sourceOpacity: sourceStyle.opacity,
      sourceRowOpacity: sourceRowStyle.opacity,
      ghostWidth: ghost.getBoundingClientRect().width,
      ghostWhiteSpace: ghostStyle.whiteSpace,
      ghostTextOverflow: ghostStyle.textOverflow,
      handleCount: document.querySelectorAll(".session-project-drag-handle").length,
      sourceBlockContainsRow: sourceRect.top <= sourceRowRect.top
        && sourceRect.bottom >= sourceRowRect.bottom,
      longNameClipped: Boolean(longName && longName.scrollWidth > longName.clientWidth),
      horizontalOverflow: list.scrollWidth > list.clientWidth + 1,
      dark: document.documentElement.getAttribute("data-theme-mode") === "dark",
      expectedDark,
    };
  }, {
    targetId: targetProject.id,
    sourceId: seed.originalProject.id,
    longProjectId: seed.longProject.id,
    expectedDark: entryMode === "classic",
  });
  assert.deepEqual(visualState.missing, [], JSON.stringify(visualState));
  assert.equal(visualState.targetAvailable, true, JSON.stringify(visualState));
  assert.equal(visualState.sourceNoop, true, JSON.stringify(visualState));
  assert.notEqual(visualState.targetShadow, "none");
  assert.notEqual(visualState.targetBackground, "rgba(0, 0, 0, 0)");
  assert.equal(Number(visualState.sourceOpacity) < 1, true);
  assert.equal(Number(visualState.sourceRowOpacity) < 1, true);
  assert.equal(visualState.ghostWidth <= 260.5, true);
  assert.equal(visualState.ghostWhiteSpace, "nowrap");
  assert.equal(visualState.ghostTextOverflow, "ellipsis");
  assert.equal(visualState.handleCount, 0);
  assert.equal(visualState.sourceBlockContainsRow, true);
  assert.equal(visualState.longNameClipped, true, JSON.stringify(visualState));
  assert.equal(visualState.horizontalOverflow, false, JSON.stringify(visualState));
  assert.equal(visualState.dark, visualState.expectedDark);

  const targetHoverStart = await hoverSyntheticSessionProjectTarget(page, targetSelector);
  assert.equal(targetHoverStart.defaultPrevented, true);
  assert.deepEqual(targetHoverStart.hovered, [targetProject.id]);
  assert.match(targetHoverStart.boxShadow, /0px 0px 0px 1px inset/);
  const targetHoverVisual = await page.locator(targetSelector).evaluate((block) => {
    block.getAnimations().forEach((animation) => animation.finish());
    const blockRect = block.getBoundingClientRect();
    const headerRect = block.querySelector(".project-header")?.getBoundingClientRect();
    const childrenRect = block.querySelector(".project-children")?.getBoundingClientRect();
    const text = block.querySelector(".project-name");
    const style = getComputedStyle(block);
    const list = document.querySelector("#sessionList");
    return {
      hovered: block.classList.contains("is-session-project-drop-over"),
      background: style.backgroundColor,
      boxShadow: style.boxShadow,
      textColor: text ? getComputedStyle(text).color : "",
      rect: {
        x: blockRect.x,
        y: blockRect.y,
        width: blockRect.width,
        height: blockRect.height,
      },
      containsWholeBlock: Boolean(
        headerRect
        && childrenRect
        && blockRect.top <= headerRect.top
        && blockRect.bottom >= childrenRect.bottom
        && blockRect.left <= headerRect.left
        && blockRect.right >= headerRect.right
      ),
      horizontalOverflow: Boolean(list && list.scrollWidth > list.clientWidth + 1),
    };
  });
  assert.equal(targetHoverVisual.hovered, true);
  assert.notEqual(targetHoverVisual.background, targetHoverStart.background);
  assert.notEqual(targetHoverVisual.boxShadow, targetHoverStart.boxShadow);
  assert.match(targetHoverVisual.boxShadow, /0px 0px 0px 2px inset/);
  assert.equal(targetHoverVisual.textColor, targetHoverStart.textColor);
  assert.equal(targetHoverVisual.containsWholeBlock, true);
  assert.equal(targetHoverVisual.horizontalOverflow, false);
  for (const dimension of ["x", "y", "width", "height"]) {
    assert.equal(
      Math.abs(targetHoverVisual.rect[dimension] - targetHoverStart.rect[dimension]) < 0.1,
      true,
      JSON.stringify({ dimension, targetHoverStart, targetHoverVisual }),
    );
  }

  const noopHoverStart = await hoverSyntheticSessionProjectTarget(page, originalSelector);
  const noopHoverVisual = await page.locator(originalSelector).evaluate((block) => {
    block.getAnimations().forEach((animation) => animation.finish());
    const text = block.querySelector(".project-name");
    const style = getComputedStyle(block);
    return {
      hovered: block.classList.contains("is-session-project-drop-over"),
      background: style.backgroundColor,
      boxShadow: style.boxShadow,
      textColor: text ? getComputedStyle(text).color : "",
    };
  });
  assert.equal(noopHoverVisual.hovered, true);
  assert.match(noopHoverVisual.boxShadow, /0px 0px 0px 1px inset/);
  assert.notEqual(noopHoverVisual.background, targetHoverVisual.background);
  assert.notEqual(noopHoverVisual.boxShadow, targetHoverVisual.boxShadow);
  assert.equal(noopHoverVisual.textColor, noopHoverStart.textColor);
  Object.assign(visualState, {
    targetAvailableBackground: targetHoverStart.background,
    targetAvailableShadow: targetHoverStart.boxShadow,
    targetHoverBackground: targetHoverVisual.background,
    targetHoverShadow: targetHoverVisual.boxShadow,
    targetHighlightRectStable: true,
    noopHoverBackground: noopHoverVisual.background,
    noopHoverShadow: noopHoverVisual.boxShadow,
  });
  const pointerHitMatrix = await exerciseSessionProjectPointerHitMatrix(
    page,
    seed.originalProject.id,
    targetProject.id,
  );
  assert.deepEqual(pointerHitMatrix.inside.hovered, [targetProject.id]);
  assert.equal(pointerHitMatrix.inside.defaultPrevented, true);
  assert.deepEqual(pointerHitMatrix.snapUpper.hovered, [seed.originalProject.id]);
  assert.deepEqual(pointerHitMatrix.snapLower.hovered, [targetProject.id]);
  assert.deepEqual(pointerHitMatrix.tie.hovered, [seed.originalProject.id]);
  assert.deepEqual(pointerHitMatrix.beyond.hovered, []);
  assert.equal(pointerHitMatrix.beyond.defaultPrevented, false);
  assert.equal(pointerHitMatrix.beyond.dropEffect, "none");
  assert.deepEqual(pointerHitMatrix.horizontalOutside.hovered, []);
  assert.equal(pointerHitMatrix.horizontalOutside.defaultPrevented, false);
  assert.deepEqual(pointerHitMatrix.beforeRectChange.hovered, [seed.originalProject.id]);
  assert.deepEqual(pointerHitMatrix.afterRectChange.hovered, [targetProject.id]);
  const expansionDuring = await page.locator(".project-toggle").evaluateAll((toggles) => (
    toggles.map((toggle) => ({
      key: toggle.closest(".project-header")?.dataset.projectKey,
      expanded: toggle.getAttribute("aria-expanded"),
    }))
  ));
  assert.deepEqual(expansionDuring, expansionBefore);

  if (visualOnly) {
    await page.keyboard.press("Escape");
    await endSyntheticSessionDrag(page);
    await assertSessionDragUiCleared(page);
    assert.equal(projectRequests.length, requestCountBeforeVisual);
    assert.equal(projectPreviews.length, previewCountBeforeVisual);
    return {
      entryMode,
      twoLevelTargetHighlight: "pass",
      fullBlockHighlightWithoutLayoutShift: "pass",
      neutralNoopHighlight: "pass",
      pointerHotspotTolerance: "pass",
      noHorizontalOverflow: "pass",
      theme: visualState.dark ? "dark" : "light",
      visualState,
    };
  }

  const readSessionListScroll = () => page.locator("#sessionList").evaluate((list) => ({
    top: list.scrollTop,
    maximum: Math.max(0, list.scrollHeight - list.clientHeight),
  }));
  const dispatchListEdgeDragOver = (edge) => page.evaluate((targetEdge) => {
    const list = document.querySelector("#sessionList");
    const drag = window.__code071SessionDrag;
    if (!list || !drag?.dataTransfer) throw new Error("Synthetic edge drag unavailable");
    const rect = list.getBoundingClientRect();
    const clientX = rect.left + Math.min(80, rect.width / 2);
    const clientY = targetEdge === "top" ? rect.top + 2 : rect.bottom - 2;
    const target = document.elementFromPoint(clientX, clientY) || list;
    const event = new DragEvent("dragover", {
      bubbles: true,
      cancelable: true,
      clientX,
      clientY,
      dataTransfer: drag.dataTransfer,
    });
    target.dispatchEvent(event);
    return { defaultPrevented: event.defaultPrevented, target: target.className || target.id };
  }, edge);
  const scrollContract = await page.locator("#sessionList").evaluate((list) => {
    list.scrollTop = 0;
    return {
      top: list.scrollTop,
      maximum: Math.max(0, list.scrollHeight - list.clientHeight),
      bodyTop: document.scrollingElement?.scrollTop || 0,
    };
  });
  assert.equal(scrollContract.maximum > 36, true, JSON.stringify(scrollContract));
  await dispatchListEdgeDragOver("bottom");
  await waitUntil(
    readSessionListScroll,
    (value) => value.top >= Math.min(24, value.maximum),
    `${entryMode} Session list did not continuously auto-scroll down`,
  );
  await page.locator("#sessionList").evaluate((list) => {
    list.scrollTop = Math.max(0, list.scrollHeight - list.clientHeight - 3);
  });
  await dispatchListEdgeDragOver("bottom");
  const bottomBound = await waitUntil(
    readSessionListScroll,
    (value) => Math.abs(value.maximum - value.top) <= 1,
    `${entryMode} Session list did not stop at the bottom bound`,
  );
  await page.waitForTimeout(100);
  assert.deepEqual(await readSessionListScroll(), bottomBound);
  await dispatchListEdgeDragOver("top");
  await waitUntil(
    readSessionListScroll,
    (value) => value.top <= Math.max(0, value.maximum - 24),
    `${entryMode} Session list did not continuously auto-scroll up`,
  );
  const topBound = await waitUntil(
    readSessionListScroll,
    (value) => value.top <= 1,
    `${entryMode} Session list did not stop at the top bound`,
  );
  assert.equal(topBound.maximum, scrollContract.maximum);
  assert.equal(
    await page.evaluate(() => document.scrollingElement?.scrollTop || 0),
    scrollContract.bodyTop,
  );
  await page.keyboard.press("Escape");
  await endSyntheticSessionDrag(page);
  await assertSessionDragUiCleared(page);
  const stoppedScroll = await readSessionListScroll();
  await page.waitForTimeout(100);
  assert.deepEqual(await readSessionListScroll(), stoppedScroll);
  assert.equal(projectRequests.length, requestCountBeforeVisual);
  assert.equal(projectPreviews.length, previewCountBeforeVisual);

  await page.evaluate(() => {
    const block = document.createElement("div");
    block.className = "project-block code071-stale-project";
    block.dataset.projectKey = "stale-project";
    block.dataset.projectId = "stale-project";
    block.innerHTML = '<div class="project-header"><span>Stale project</span></div>';
    document.querySelector("#sessionList")?.appendChild(block);
  });
  await beginSyntheticSessionDrag(page, fixture.current.id);
  assert.equal(
    await page.locator(".code071-stale-project").evaluate((block) => (
      block.classList.contains("is-session-project-drop-invalid")
      && !block.classList.contains("is-session-project-drop-available")
    )),
    true,
  );
  const staleDrop = await dispatchSyntheticSessionDrop(
    page,
    ".code071-stale-project .project-header",
  );
  assert.equal(staleDrop.drops[0].defaultPrevented, false);
  await assertSessionDragUiCleared(page);
  await page.locator(".code071-stale-project").evaluate((block) => block.remove());
  assert.equal(projectRequests.length, requestCountBeforeVisual);
  assert.equal(projectPreviews.length, previewCountBeforeVisual);

  await beginSyntheticSessionDrag(page, fixture.current.id);
  await page.evaluate(() => {
    const drag = window.__code071SessionDrag;
    document.body.dispatchEvent(new DragEvent("drop", {
      bubbles: true,
      cancelable: true,
      dataTransfer: drag.dataTransfer,
    }));
  });
  await endSyntheticSessionDrag(page);
  await assertSessionDragUiCleared(page);
  assert.equal(projectRequests.length, requestCountBeforeVisual);
  assert.equal(projectPreviews.length, previewCountBeforeVisual);

  const successToastsBeforeNoop = await page.locator("#toastContainer .toast.success").count();
  const sameBefore = sessionMigrationRequestCounts(
    fixture.current.id,
    projectRequests,
    projectPreviews,
  );
  await beginSyntheticSessionDrag(page, fixture.current.id);
  const sameDrop = await dispatchSyntheticSessionDrop(
    page,
    targetSelector,
    1,
    originalSelector,
  );
  assert.equal(sameDrop.dragover.defaultPrevented, true);
  assert.deepEqual(sameDrop.hoveredAfterDragover, [seed.originalProject.id]);
  assert.equal(sameDrop.drops[0].defaultPrevented, true);
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.current.id, projectRequests, projectPreviews),
    sameBefore,
  );
  assert.equal(
    await page.locator("#toastContainer .toast.success").count(),
    successToastsBeforeNoop,
  );

  const nativeChildNoopBefore = sessionMigrationRequestCounts(
    fixture.current.id,
    projectRequests,
    projectPreviews,
  );
  const childSessionRow = page.locator(
    `.project-block[data-project-id="${seed.originalProject.id}"] ` +
    `.session-row[data-session-id="${fixture.current.id}"]`,
  );
  assert.equal(await childSessionRow.count(), 1);
  await dragSessionToVisibleTargetWithMouse(
    page,
    fixture.current.id,
    childSessionRow,
  );
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.current.id, projectRequests, projectPreviews),
    nativeChildNoopBefore,
  );

  const cancelBefore = sessionMigrationRequestCounts(
    fixture.cancel.id,
    projectRequests,
    projectPreviews,
  );
  // The second native path crosses projects and lands on visible whitespace.
  // Keeping this as the sole locator.dragTo path avoids Chromium's unstable
  // second dragTo sequence while the child-row path above uses real mouse steps.
  await dragSessionToTargetWithNativeDrag(
    page,
    fixture.cancel.id,
    projectDropBlock(page, targetProject.id).locator(".project-empty-sessions"),
  );
  let modal = page.locator(".session-project-migration-modal");
  await modal.waitFor({ state: "visible" });
  await assertSessionDragUiCleared(page, { includePending: false });
  assert.equal(
    await page.locator(
      `.session-row[data-session-id="${fixture.cancel.id}"]`,
    ).evaluate((row) => row.classList.contains("is-session-project-migration-pending")),
    true,
  );
  const pendingRetry = await beginSyntheticSessionDrag(page, fixture.cancel.id);
  assert.equal(pendingRetry.defaultPrevented, true);
  assert.deepEqual(pendingRetry.types, []);
  assert.equal(pendingRetry.available, 0);
  await endSyntheticSessionDrag(page);
  await modal.locator(".session-project-migration-cancel").click();
  await modal.waitFor({ state: "detached" });
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.cancel.id, projectRequests, projectPreviews),
    { commits: cancelBefore.commits, previews: cancelBefore.previews + 1 },
  );
  const cancelAfter = await sessionRecord(host, fixture.cancel.id);
  assert.equal(cancelAfter.projectId, seed.longProject.id);

  const currentBefore = sessionMigrationRequestCounts(
    fixture.current.id,
    projectRequests,
    projectPreviews,
  );
  await dragSessionToBlock(
    page,
    fixture.current.id,
    projectDropBlock(page, targetProject.id),
  );
  modal = page.locator(".session-project-migration-modal");
  await modal.waitFor({ state: "visible" });
  await modal.locator(".session-project-migration-confirm").click();
  await modal.waitFor({ state: "detached" });
  const movedCurrent = await waitForSession(
    host,
    fixture.current.id,
    (session) => session.projectId === targetProject.id,
    `${entryMode} drag current Session did not commit`,
  );
  assert.equal(path.resolve(movedCurrent.cwd), path.resolve(host.projectDir));
  await waitForRoot(page, host.projectDir);
  await assertSessionDragUiCleared(page);
  const restoredCurrentSource = page.locator(
    `.session-row[data-session-id="${fixture.current.id}"] .session-main`,
  );
  assert.equal(await restoredCurrentSource.count(), 1);
  assert.equal(await restoredCurrentSource.getAttribute("draggable"), "true");
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.current.id, projectRequests, projectPreviews),
    { commits: currentBefore.commits + 1, previews: currentBefore.previews + 1 },
  );

  const targetNoopBefore = sessionMigrationRequestCounts(
    fixture.current.id,
    projectRequests,
    projectPreviews,
  );
  await beginSyntheticSessionDrag(page, fixture.current.id);
  await dispatchSyntheticSessionDrop(page, targetSelector);
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.current.id, projectRequests, projectPreviews),
    targetNoopBefore,
  );

  const rootBeforeOtherMove = await page.locator("#projectRoot").inputValue();
  const otherMoveBefore = sessionMigrationRequestCounts(
    fixture.other.id,
    projectRequests,
    projectPreviews,
  );
  await dragSessionToBlock(
    page,
    fixture.other.id,
    projectDropBlock(page, targetProject.id),
  );
  assert.equal(await page.locator(".session-project-migration-modal").count(), 0);
  await waitForSession(
    host,
    fixture.other.id,
    (session) => session.projectId === targetProject.id,
    `${entryMode} non-current drag did not commit`,
  );
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.other.id, projectRequests, projectPreviews),
    { commits: otherMoveBefore.commits + 1, previews: otherMoveBefore.previews + 1 },
  );
  assert.equal(
    path.resolve(await page.locator("#projectRoot").inputValue()),
    path.resolve(rootBeforeOtherMove),
  );

  await dragSessionToBlock(page, fixture.other.id, unassignedDropBlock(page));
  await waitForSession(
    host,
    fixture.other.id,
    (session) => session.projectId == null,
    `${entryMode} drag to unassigned did not commit`,
  );
  await assertSessionDragUiCleared(page);
  assert.equal(
    path.resolve(await page.locator("#projectRoot").inputValue()),
    path.resolve(rootBeforeOtherMove),
  );

  const failedPreviewPath = `/api/sessions/${encodeURIComponent(fixture.other.id)}/project/preview`;
  const failedPreviewPattern = `**${failedPreviewPath}`;
  let previewAborted = false;
  const abortPreview = async (route) => {
    previewAborted = true;
    await route.abort("failed");
  };
  const networkBefore = sessionMigrationRequestCounts(
    fixture.other.id,
    projectRequests,
    projectPreviews,
  );
  await page.route(failedPreviewPattern, abortPreview, { times: 1 });
  await dragSessionToBlock(
    page,
    fixture.other.id,
    projectDropBlock(page, targetProject.id),
  );
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "could not be moved",
  }).last().waitFor({ state: "visible" });
  await page.unroute(failedPreviewPattern, abortPreview);
  await assertSessionDragUiCleared(page);
  assert.equal(previewAborted, true);
  const networkAfter = sessionMigrationRequestCounts(
    fixture.other.id,
    projectRequests,
    projectPreviews,
  );
  assert.equal(networkAfter.commits, networkBefore.commits);
  assert.equal(networkAfter.previews, networkBefore.previews + 1);
  assert.equal((await sessionRecord(host, fixture.other.id)).projectId, null);

  const duplicateBefore = sessionMigrationRequestCounts(
    fixture.other.id,
    projectRequests,
    projectPreviews,
  );
  await beginSyntheticSessionDrag(page, fixture.other.id);
  const duplicateDrop = await dispatchSyntheticSessionDrop(page, targetSelector, 2);
  assert.equal(duplicateDrop.drops[0].defaultPrevented, true);
  await waitForSession(
    host,
    fixture.other.id,
    (session) => session.projectId === targetProject.id,
    `${entryMode} duplicate drop did not finish`,
  );
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.other.id, projectRequests, projectPreviews),
    { commits: duplicateBefore.commits + 1, previews: duplicateBefore.previews + 1 },
  );

  await page.locator(".project-block.unassigned-project").evaluate((block) => block.remove());
  const temporaryBefore = sessionMigrationRequestCounts(
    fixture.current.id,
    projectRequests,
    projectPreviews,
  );
  const temporaryDrag = await beginSyntheticSessionDrag(page, fixture.current.id);
  assert.equal(temporaryDrag.temporary, 1);
  const temporary = page.locator(".session-project-drop-temporary");
  assert.equal(await temporary.count(), 1);
  assert.equal((await temporary.textContent()).includes("Drop here to remove from project"), true);
  assert.equal(
    await temporary.evaluate((block) => (
      block.classList.contains("is-session-project-drop-available")
    )),
    true,
  );
  await temporary.scrollIntoViewIfNeeded();
  await dispatchSyntheticSessionDrop(
    page,
    ".session-project-drop-temporary .project-header",
  );
  await waitForSession(
    host,
    fixture.current.id,
    (session) => session.projectId == null,
    `${entryMode} temporary unassigned drop did not commit`,
  );
  await waitForRoot(page, host.projectDir);
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.current.id, projectRequests, projectPreviews),
    { commits: temporaryBefore.commits + 1, previews: temporaryBefore.previews + 1 },
  );

  for (const blockedSession of [fixture.busy, fixture.waiting]) {
    const blockedBefore = sessionMigrationRequestCounts(
      blockedSession.id,
      projectRequests,
      projectPreviews,
    );
    await dragSessionToBlock(
      page,
      blockedSession.id,
      projectDropBlock(page, targetProject.id),
    );
    await page.locator("#toastContainer .toast.error").filter({
      hasText: "still has running or waiting work",
    }).last().waitFor({ state: "visible" });
    await assertSessionDragUiCleared(page);
    assert.deepEqual(
      sessionMigrationRequestCounts(blockedSession.id, projectRequests, projectPreviews),
      { commits: blockedBefore.commits, previews: blockedBefore.previews + 1 },
    );
    assert.equal((await sessionRecord(host, blockedSession.id)).projectId, null);
  }

  const broadBefore = sessionMigrationRequestCounts(
    seed.wide.id,
    projectRequests,
    projectPreviews,
  );
  await dragSessionToBlock(
    page,
    seed.wide.id,
    projectDropBlock(page, targetProject.id),
  );
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "too broad",
  }).last().waitFor({ state: "visible" });
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(seed.wide.id, projectRequests, projectPreviews),
    { commits: broadBefore.commits, previews: broadBefore.previews + 1 },
  );

  const conflictBeforeRecord = await sessionRecord(host, fixture.conflict.id);
  const conflictBefore = sessionMigrationRequestCounts(
    fixture.conflict.id,
    projectRequests,
    projectPreviews,
  );
  await dragSessionToBlock(
    page,
    fixture.conflict.id,
    projectDropBlock(page, targetProject.id),
  );
  modal = page.locator(".session-project-migration-modal");
  await modal.waitFor({ state: "visible" });
  await requestJson(
    host.ready.codeUrl,
    `/api/projects/${targetProject.id}/rename`,
    {
      method: "POST",
      body: JSON.stringify({ label: `${entryMode} drag target refreshed` }),
    },
  );
  await modal.locator(".session-project-migration-confirm").click();
  await modal.waitFor({ state: "detached" });
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "changed in another window",
  }).last().waitFor({ state: "visible" });
  await assertSessionDragUiCleared(page);
  assert.deepEqual(
    sessionMigrationRequestCounts(fixture.conflict.id, projectRequests, projectPreviews),
    { commits: conflictBefore.commits + 1, previews: conflictBefore.previews + 1 },
  );
  const conflictAfterRecord = await sessionRecord(host, fixture.conflict.id);
  assert.equal(conflictAfterRecord.projectId, conflictBeforeRecord.projectId);
  assert.equal(conflictAfterRecord.revision, conflictBeforeRecord.revision);
  assert.equal(path.resolve(conflictAfterRecord.cwd), path.resolve(conflictBeforeRecord.cwd));
  const targetAfterConflict = (
    await requestJson(host.ready.codeUrl, "/api/projects")
  ).payload.data.find((project) => project.id === targetProject.id);
  assert.equal(
    targetAfterConflict.rootPaths.some(
      (rootPath) => path.resolve(rootPath) === path.resolve(conflictBeforeRecord.cwd),
    ),
    false,
  );

  const rerenderBeforeRequests = projectRequests.length;
  const rerenderBeforePreviews = projectPreviews.length;
  await beginSyntheticSessionDrag(page, fixture.cancel.id);
  await page.locator(
    `.project-header[data-project-id="${seed.longProject.id}"] .project-toggle`,
  ).click();
  await endSyntheticSessionDrag(page);
  await assertSessionDragUiCleared(page);
  assert.equal(projectRequests.length, rerenderBeforeRequests);
  assert.equal(projectPreviews.length, rerenderBeforePreviews);

  const searchBeforeRequests = projectRequests.length;
  const searchBeforePreviews = projectPreviews.length;
  await beginSyntheticSessionDrag(page, fixture.current.id);
  await page.locator("#sessionSearchBtn").click();
  await page.locator("#sessionSearchModal").waitFor({ state: "visible" });
  assert.equal(await page.locator(".session-search-result[draggable]").count(), 0);
  await page.keyboard.press("Escape");
  await endSyntheticSessionDrag(page);
  await page.locator("#sessionSearchModal").waitFor({ state: "hidden" });
  await assertSessionDragUiCleared(page);
  assert.equal(projectRequests.length, searchBeforeRequests);
  assert.equal(projectPreviews.length, searchBeforePreviews);


  return {
    entryMode,
    fixedOpaquePayload: "pass",
    sensitivePayloadAbsent: "pass",
    wholeRowDragSource: "pass",
    childSessionRowDropTarget: "pass",
    visibleBlockWhitespaceDropTarget: "pass",
    pointerHotspotTolerance: "pass",
    stableGapTieBreak: "pass",
    pointerOverridesEventTarget: "pass",
    scrollRectRecalculation: "pass",
    twoLevelTargetHighlight: "pass",
    fullBlockHighlightWithoutLayoutShift: "pass",
    neutralNoopHighlight: "pass",
    boundedSessionListAutoScroll: "pass",
    realtimeDragPreview: "pass",
    ordinaryClick: "pass",
    sameProjectNoop: "pass",
    authoritativeProjectTarget: "pass",
    staleProjectRejected: "pass",
    projectToProject: "pass",
    unassignedToProject: "pass",
    projectToUnassigned: "pass",
    temporaryUnassignedTarget: "pass",
    confirmCancelZeroCommit: "pass",
    duplicateDropSingleChain: "pass",
    busyRejected: "pass",
    waitingRejected: "pass",
    archivedNotDraggable: "pass",
    broadRootRejected: "pass",
    stalePlanRejected: "pass",
    networkFailureRecovered: "pass",
    currentTreeUpdated: "pass",
    nonCurrentTreeUnchanged: "pass",
    escapeCleanup: "pass",
    externalDropCleanup: "pass",
    rerenderCleanup: "pass",
    searchCleanup: "pass",
    noAutoCollapse: "pass",
    narrowSidebar: "pass",
    longProjectName: "pass",
    theme: visualState.dark ? "dark" : "light",
    visualState,
  };
}

async function exercise(page, host, seed, projectRequests, projectPreviews) {
  await page.goto(new URL("/", host.ready.codeUrl).href, { waitUntil: "domcontentloaded" });
  await page.waitForFunction((sessionId) => (
    document.documentElement.getAttribute("data-code-frontend-ready") === "true"
    && document.querySelector(`.session-more-btn[data-session-id="${sessionId}"]`)
  ), seed.current.id);
  await waitUntil(
    () => page.locator("#sessionTitle").inputValue(),
    (value) => value === seed.current.title,
    "current Session did not load",
  );
  await page.waitForLoadState("networkidle");

  const menuAcceptance = await exerciseProjectMenuAcceptance(
    page,
    seed,
    seed.current.id,
  );
  let longRemoveTooltip = null;

  // Narrow-sidebar keyboard contract: nested menu stays in the viewport,
  // ArrowLeft returns to its trigger, then Escape returns to the row button.
  const narrow = await openProjectSubmenu(page, seed.current.id);
  assert.equal(
    await narrow.submenu.locator('[data-project-action="create"]').count(),
    0,
  );
  const narrowBox = await narrow.submenu.boundingBox();
  assert.ok(narrowBox);
  assert.equal(narrowBox.x >= 8, true);
  assert.equal(narrowBox.x + narrowBox.width <= 452.5, true);
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.locator(".session-project-submenu").count(), 0);
  assert.equal(await narrow.trigger.evaluate((element) => element === document.activeElement), true);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".session-more-menu").count(), 0);
  assert.equal(await narrow.more.evaluate((element) => element === document.activeElement), true);
  assert.equal(projectRequests.length, 0);

  await page.setViewportSize({ width: 1280, height: 800 });
  await browseHome(page, host);
  const browsed = await sessionRecord(host, seed.current.id);
  assert.equal(browsed.projectId, seed.originalProject.id);
  assert.equal(path.resolve(browsed.cwd), path.resolve(host.projectDir));
  const unassignedWhileBrowsing = await sessionRecord(host, seed.other.id);
  assert.equal(unassignedWhileBrowsing.projectId, null);
  assert.equal(path.resolve(unassignedWhileBrowsing.cwd), path.resolve(host.projectDir));
  assert.equal(projectRequests.length, 0);

  await page.locator("#projectRootShort").click();
  const originalRootClicked = await page.evaluate((targetPath) => {
    const target = [...document.querySelectorAll(".cwd-recent-item")]
      .find((item) => item.dataset.path === targetPath);
    target?.click();
    return Boolean(target);
  }, host.projectDir);
  assert.equal(originalRootClicked, true);
  await waitForRoot(page, host.projectDir);
  const browsedBackBeforeMove = await sessionRecord(host, seed.current.id);
  assert.equal(browsedBackBeforeMove.projectId, seed.originalProject.id);
  assert.equal(path.resolve(browsedBackBeforeMove.cwd), path.resolve(host.projectDir));
  assert.equal(projectRequests.length, 0);

  const migrationConfirmation = await exerciseMigrationConfirmation(
    page,
    host,
    seed,
    projectRequests,
    projectPreviews,
  );
  const movedCurrent = await sessionRecord(host, seed.current.id);
  assert.equal(path.resolve(movedCurrent.cwd), path.resolve(host.projectDir));
  await waitForRoot(page, host.projectDir);

  const currentMenu = await openProjectSubmenu(page, seed.current.id);
  const currentItem = currentMenu.submenu.locator(
    `[data-project-id="${seed.targetProject.id}"]`,
  );
  assert.equal(await currentItem.count(), 0);
  assert.equal(
    await currentMenu.submenu.locator('[data-project-action="create"]').count(),
    0,
  );
  const remove = currentMenu.submenu.locator('[data-project-action="remove"]');
  assert.equal(await remove.count(), 1);
  await remove.focus();
  await page.keyboard.press("Enter");
  const removed = await waitForSession(
    host,
    seed.current.id,
    (session) => session.projectId == null,
    "Session did not move out of its project",
  );
  assert.equal(path.resolve(removed.cwd), path.resolve(host.projectDir));
  await waitForRoot(page, host.projectDir);
  longRemoveTooltip = await exerciseLongRemoveTooltip(
    page,
    host,
    seed,
    seed.longAssigned.id,
  );

  await browseHome(page, host);
  await page.locator("#projectRootShort").click();
  const recentTargetClicked = await page.evaluate((targetPath) => {
    const target = [...document.querySelectorAll(".cwd-recent-item")]
      .find((item) => item.dataset.path === targetPath);
    target?.click();
    return Boolean(target);
  }, host.projectDir);
  assert.equal(recentTargetClicked, true);
  await waitForRoot(page, host.projectDir);
  const browsedBack = await sessionRecord(host, seed.current.id);
  assert.equal(browsedBack.projectId, null);
  assert.equal(path.resolve(browsedBack.cwd), path.resolve(host.projectDir));

  await browseHome(page, host);
  const rootBeforeOtherMove = await page.locator("#projectRoot").inputValue();
  const movedOther = await moveToProject(page, host, seed.other.id, seed.targetProject);
  assert.equal(path.resolve(movedOther.cwd), path.resolve(host.projectDir));
  assert.equal(path.resolve(await page.locator("#projectRoot").inputValue()), path.resolve(rootBeforeOtherMove));

  const busyMenu = await openProjectSubmenu(page, seed.busy.id);
  const busyTarget = busyMenu.submenu.locator(
    `[data-project-id="${seed.targetProject.id}"]`,
  );
  await busyTarget.focus();
  await page.keyboard.press("Enter");
  await page.locator("#toastContainer .toast.error").filter({
    hasText: "still has running or waiting work",
  }).waitFor({ state: "visible" });
  const busy = await sessionRecord(host, seed.busy.id);
  assert.equal(busy.projectId, null);
  assert.equal(path.resolve(busy.cwd), path.resolve(host.projectDir));
  assert.equal(path.resolve(await page.locator("#projectRoot").inputValue()), path.resolve(rootBeforeOtherMove));

  const migrationBlock = await exerciseMigrationBlock(
    page,
    host,
    seed,
    projectRequests,
    projectPreviews,
  );
  const createPrimaryConflict = await exerciseCreatePrimaryConflict(page, host, seed);
  const editPrimaryConflict = await exerciseEditPrimaryConflict(page, host, seed);
  const migrationConflict = await exerciseMigrationConflict(
    page,
    host,
    seed,
    projectRequests,
    projectPreviews,
  );

  const createMenu = await openProjectSubmenu(page, seed.createAndMove.id);
  assert.equal(
    await createMenu.submenu.locator(`[data-project-id="${seed.originalProject.id}"]`).count(),
    1,
  );
  assert.equal(
    await createMenu.submenu.locator(`[data-project-id="${seed.targetProject.id}"]`).count(),
    1,
  );
  assert.equal(
    await createMenu.submenu.locator(`[data-project-id="${seed.longProject.id}"]`).count(),
    1,
  );
  const create = createMenu.submenu.locator('[data-project-action="create"]');
  assert.equal(await create.count(), 1);
  await create.focus();
  await page.keyboard.press("Enter");
  const createMigrationModal = page.locator(".session-project-migration-modal");
  await createMigrationModal.waitFor({ state: "visible" });
  await createMigrationModal.locator(".session-project-migration-confirm").click();
  const newlyMoved = await waitForSession(
    host,
    seed.createAndMove.id,
    (session) => session.projectId && path.resolve(session.cwd) === path.resolve(host.projectDir),
    "new project and move did not complete",
  );
  const projects = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  const createdProject = projects.find((project) => project.id === newlyMoved.projectId);
  assert.ok(createdProject);
  assert.equal(path.resolve(createdProject.rootPaths[0]), path.resolve(seed.newProjectRoot));
  assert.equal(path.resolve(createdProject.rootPaths[1]), path.resolve(host.projectDir));
  assert.equal(path.resolve(await page.locator("#projectRoot").inputValue()), path.resolve(rootBeforeOtherMove));

  return {
    bundle: "pass",
    menuAcceptance,
    longRemoveTooltip,
    menuKeyboard: "pass",
    narrowSidebar: "pass",
    browsingDoesNotMigrate: "pass",
    assignedBrowsingRoundTrip: "pass",
    unassignedCwdIndependent: "pass",
    assignedCreateActionHidden: "pass",
    currentTreeFollowsAuthoritativeCwd: "pass",
    migrationConfirmation,
    migrationBlock,
    createPrimaryConflict,
    editPrimaryConflict,
    migrationConflict,
    moveOutPreservesCwd: "pass",
    browsingBackDoesNotReattach: "pass",
    otherSessionKeepsCurrentTree: "pass",
    busySessionRejected: "pass",
    newProjectAndMove: "pass",
    projectRequestCount: projectRequests.length,
    projectRequestBodiesExcludeCwd: projectRequests.every(
      (request) => !Object.prototype.hasOwnProperty.call(request.body || {}, "cwd"),
    ),
    projectRequestsExcludeClientRoots: [...projectRequests, ...projectPreviews].every(
      (request) => !Object.prototype.hasOwnProperty.call(request.body || {}, "rootsToAdd"),
    ),
    previewRequestCount: projectPreviews.length,
  };
}

async function exerciseClassic(page, host, seed, projectRequests, projectPreviews) {
  const requestCountBeforeBrowse = projectRequests.length;
  await page.goto(
    new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href,
    { waitUntil: "domcontentloaded" },
  );
  await page.waitForFunction((sessionId) => (
    document.documentElement.getAttribute("data-frontend-runtime") === "classic-fallback"
    && document.querySelector(`.session-more-btn[data-session-id="${sessionId}"]`)
  ), seed.classic.id);
  await waitUntil(
    () => page.locator("#sessionTitle").inputValue(),
    (value) => value === seed.classic.title,
    "classic Session did not load",
  );
  await page.waitForLoadState("networkidle");
  const menuAcceptance = await exerciseProjectMenuAcceptance(
    page,
    seed,
    seed.classic.id,
  );
  let longRemoveTooltip = null;
  await browseHome(page, host);
  const browsed = await sessionRecord(host, seed.classic.id);
  assert.equal(browsed.projectId, seed.originalProject.id);
  assert.equal(path.resolve(browsed.cwd), path.resolve(host.projectDir));
  assert.equal(projectRequests.length, requestCountBeforeBrowse);
  const moved = await moveToProject(page, host, seed.classic.id, seed.targetProject);
  assert.equal(path.resolve(moved.cwd), path.resolve(host.projectDir));
  await waitForRoot(page, host.projectDir);
  longRemoveTooltip = await exerciseLongRemoveTooltip(
    page,
    host,
    seed,
    seed.classicLongAssigned.id,
  );
  return {
    directClassic: "pass",
    menuAcceptance,
    longRemoveTooltip,
    browsingDoesNotMigrate: "pass",
    menuKeyboard: "pass",
    currentTreeFollowsAuthoritativeCwd: "pass",
    previewPipeline: projectPreviews.length > 0 ? "pass" : "fail",
  };
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true });
  let browser = null;
  let context = null;
  let page = null;
  let cleanup = null;
  const projectRequests = [];
  const projectPreviews = [];
  const pageErrors = [];
  let contract = null;
  try {
    const seed = await seedContract(host);
    browser = await chromium.launch({ headless: true });
    const visualOnly = process.env.CODE071_H4_VISUAL_ONLY === "1";
    if (visualOnly) {
      ({ context, page } = await createContext(
        browser,
        host,
        seed,
        projectRequests,
        projectPreviews,
        pageErrors,
        seed.drag.bundle.current.id,
      ));
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(new URL("/", host.ready.codeUrl).href, {
        waitUntil: "domcontentloaded",
      });
      await page.waitForFunction((sessionId) => (
        document.documentElement.getAttribute("data-code-frontend-ready") === "true"
        && document.querySelector(`.session-main[data-session-id="${sessionId}"]`)
      ), seed.drag.bundle.current.id);
      const bundleVisual = await exerciseSessionProjectDrag(
        page,
        host,
        seed,
        seed.drag.bundle,
        projectRequests,
        projectPreviews,
        "bundle",
        { visualOnly: true },
      );
      await page.close();
      page = null;
      await context.close();
      context = null;
      ({ context, page } = await createContext(
        browser,
        host,
        seed,
        projectRequests,
        projectPreviews,
        pageErrors,
        seed.drag.classic.current.id,
        "dark",
      ));
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(
        new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href,
        { waitUntil: "domcontentloaded" },
      );
      await page.waitForFunction((sessionId) => (
        document.documentElement.getAttribute("data-frontend-runtime") === "classic-fallback"
        && document.querySelector(`.session-main[data-session-id="${sessionId}"]`)
      ), seed.drag.classic.current.id);
      const classicVisual = await exerciseSessionProjectDrag(
        page,
        host,
        seed,
        seed.drag.classic,
        projectRequests,
        projectPreviews,
        "classic",
        { visualOnly: true },
      );
      contract = {
        visualHighlight: {
          bundle: bundleVisual,
          classic: classicVisual,
        },
      };
    } else {
    ({ context, page } = await createContext(
      browser,
      host,
      seed,
      projectRequests,
      projectPreviews,
      pageErrors,
      seed.current.id,
    ));
    const bundle = await exercise(page, host, seed, projectRequests, projectPreviews);
    const sessionDragBundle = await exerciseSessionProjectDrag(
      page,
      host,
      seed,
      seed.drag.bundle,
      projectRequests,
      projectPreviews,
      "bundle",
    );
    const primaryEditorBundle = await exercisePrimaryEditor(page, host, seed, {
      currentPrimary: seed.editorPrimary,
      nextPrimary: seed.editorSecondary,
    });
    const primaryEditorConflict = await exerciseProjectEditorConflict(page, host, seed);
    await page.close();
    page = null;
    await context.close();
    context = null;
    ({ context, page } = await createContext(
      browser,
      host,
      seed,
      projectRequests,
      projectPreviews,
      pageErrors,
      seed.classic.id,
      "dark",
    ));
    const classic = await exerciseClassic(
      page,
      host,
      seed,
      projectRequests,
      projectPreviews,
    );
    const sessionDragClassic = await exerciseSessionProjectDrag(
      page,
      host,
      seed,
      seed.drag.classic,
      projectRequests,
      projectPreviews,
      "classic",
    );
    const primaryEditorClassic = await exercisePrimaryEditor(page, host, seed, {
      currentPrimary: seed.editorSecondary,
      nextPrimary: seed.editorPrimary,
    });
    contract = {
      bundle,
      classic,
      sessionDrag: {
        bundle: sessionDragBundle,
        classic: sessionDragClassic,
      },
      primaryEditor: {
        bundle: primaryEditorBundle,
        classic: primaryEditorClassic,
      },
      primaryEditorConflict,
    };
    }
    assert.deepEqual(pageErrors, []);
  } finally {
    if (page && !page.isClosed()) await page.close();
    if (context) await context.close();
    if (browser) await browser.close();
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, [], JSON.stringify({
      cleanupErrors: cleanup.cleanupErrors,
      stderr: cleanup.sanitizedStderr,
      temporaryFiles: cleanup.temporaryFiles,
    }));
    assert.equal(getActiveChildCount(), 0);
  }
  process.stdout.write(`${JSON.stringify({
    ok: true,
    command: "code071-session-project-migration-selfcheck",
    contract,
    pageErrors: pageErrors.length,
    cleanup: {
      childExited: cleanup.childExited,
      portsClosed: cleanup.portsClosed,
      rootRemoved: cleanup.rootRemoved,
      activeChildCount: cleanup.activeChildCount,
      cleanupErrors: cleanup.cleanupErrors,
    },
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
