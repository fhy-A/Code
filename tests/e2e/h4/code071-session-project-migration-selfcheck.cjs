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
  await Promise.all([
    fs.mkdir(targetPrimary),
    fs.mkdir(targetSecondary),
    fs.mkdir(longProjectRoot),
    fs.mkdir(newProjectRoot),
    fs.mkdir(path.join(host.dataDir, "attachments"), { recursive: true }),
  ]);
  await Promise.all([
    fs.writeFile(path.join(targetPrimary, "target-primary.txt"), "primary\n", "utf8"),
    fs.writeFile(path.join(targetSecondary, "target-secondary.txt"), "secondary\n", "utf8"),
    fs.writeFile(path.join(longProjectRoot, "long-project.txt"), "long\n", "utf8"),
    fs.writeFile(path.join(newProjectRoot, "new-project.txt"), "new\n", "utf8"),
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
  const longProject = (await requestJson(host.ready.codeUrl, "/api/projects", {
    method: "POST",
    body: JSON.stringify({
      label: "A very long project name that should be clipped in the submenu",
      rootPaths: [longProjectRoot],
    }),
  })).payload;

  const createSession = async (title, runState = {}, projectId = null) => (
    await requestJson(host.ready.codeUrl, "/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        title,
        projectId,
        cwd: host.projectDir,
        runState,
      }),
    })
  ).payload;

  return {
    targetPrimary,
    targetSecondary,
    longProjectRoot,
    newProjectRoot,
    originalProject,
    targetProject,
    longProject,
    current: await createSession("CODE-071 current", {}, originalProject.id),
    other: await createSession("CODE-071 other"),
    busy: await createSession("CODE-071 busy", { status: "paused" }),
    createAndMove: await createSession("CODE-071 create and move"),
    classic: await createSession("CODE-071 classic", {}, originalProject.id),
  };
}

async function createContext(
  browser,
  host,
  seed,
  projectRequests,
  pageErrors,
  currentSessionId,
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
  await context.addInitScript(({ platformToken, currentSessionId, projectDir }) => {
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
    localStorage.setItem("code-theme-mode", "light");
    localStorage.setItem("code-sidebar-width", "190");
    localStorage.setItem("code-recent-folders", JSON.stringify([projectDir]));
    localStorage.setItem("code-expanded-project-sessions", JSON.stringify({
      __unassigned_sessions__: true,
    }));
    localStorage.setItem("code-foreground-view", "session");
    localStorage.setItem("code-last-session", currentSessionId);
  }, { platformToken: host.platformToken, currentSessionId, projectDir: host.projectDir });
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
  await page.keyboard.press("ArrowRight");
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
    minimumItemHeight: submenuMetrics.maxItemHeightFloor,
  };
}

async function moveToProject(page, host, sessionId, project) {
  const { submenu } = await openProjectSubmenu(page, sessionId);
  const item = submenu.locator(`[data-project-id="${project.id}"]`);
  assert.equal(await item.isDisabled(), false);
  await item.focus();
  await page.keyboard.press("Enter");
  return waitForSession(
    host,
    sessionId,
    (session) => session.projectId === project.id,
    "Session did not move to target project",
  );
}

async function browseHome(page, host) {
  await page.locator("#projectRootShort").click();
  await page.locator("#cwdHomeBtn").click();
  await waitForRoot(page, host.homeDir);
}

async function exercise(page, host, seed, projectRequests) {
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

  const movedCurrent = await moveToProject(page, host, seed.current.id, seed.targetProject);
  assert.equal(path.resolve(movedCurrent.cwd), path.resolve(seed.targetPrimary));
  await waitForRoot(page, seed.targetPrimary);
  assert.deepEqual(Object.keys(projectRequests[0].body).sort(), ["expectedRevision", "projectId"]);

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
  assert.equal(path.resolve(removed.cwd), path.resolve(seed.targetPrimary));
  await waitForRoot(page, seed.targetPrimary);

  await browseHome(page, host);
  await page.locator("#projectRootShort").click();
  const recentTargetClicked = await page.evaluate((targetPath) => {
    const target = [...document.querySelectorAll(".cwd-recent-item")]
      .find((item) => item.dataset.path === targetPath);
    target?.click();
    return Boolean(target);
  }, seed.targetPrimary);
  assert.equal(recentTargetClicked, true);
  await waitForRoot(page, seed.targetPrimary);
  const browsedBack = await sessionRecord(host, seed.current.id);
  assert.equal(browsedBack.projectId, null);
  assert.equal(path.resolve(browsedBack.cwd), path.resolve(seed.targetPrimary));

  await browseHome(page, host);
  const rootBeforeOtherMove = await page.locator("#projectRoot").inputValue();
  const movedOther = await moveToProject(page, host, seed.other.id, seed.targetProject);
  assert.equal(path.resolve(movedOther.cwd), path.resolve(seed.targetPrimary));
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
  const newlyMoved = await waitForSession(
    host,
    seed.createAndMove.id,
    (session) => session.projectId && path.resolve(session.cwd) === path.resolve(seed.newProjectRoot),
    "new project and move did not complete",
  );
  const projects = (await requestJson(host.ready.codeUrl, "/api/projects")).payload.data;
  const createdProject = projects.find((project) => project.id === newlyMoved.projectId);
  assert.ok(createdProject);
  assert.equal(path.resolve(createdProject.rootPaths[0]), path.resolve(seed.newProjectRoot));
  assert.equal(path.resolve(await page.locator("#projectRoot").inputValue()), path.resolve(rootBeforeOtherMove));

  return {
    bundle: "pass",
    menuAcceptance,
    menuKeyboard: "pass",
    narrowSidebar: "pass",
    browsingDoesNotMigrate: "pass",
    assignedBrowsingRoundTrip: "pass",
    unassignedCwdIndependent: "pass",
    assignedCreateActionHidden: "pass",
    currentTreeFollowsAuthoritativeCwd: "pass",
    moveOutPreservesCwd: "pass",
    browsingBackDoesNotReattach: "pass",
    otherSessionKeepsCurrentTree: "pass",
    busySessionRejected: "pass",
    newProjectAndMove: "pass",
    projectRequestCount: projectRequests.length,
    projectRequestBodiesExcludeCwd: projectRequests.every(
      (request) => !Object.prototype.hasOwnProperty.call(request.body || {}, "cwd"),
    ),
  };
}

async function exerciseClassic(page, host, seed, projectRequests) {
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
  await browseHome(page, host);
  const browsed = await sessionRecord(host, seed.classic.id);
  assert.equal(browsed.projectId, seed.originalProject.id);
  assert.equal(path.resolve(browsed.cwd), path.resolve(host.projectDir));
  assert.equal(projectRequests.length, requestCountBeforeBrowse);
  const moved = await moveToProject(page, host, seed.classic.id, seed.targetProject);
  assert.equal(path.resolve(moved.cwd), path.resolve(seed.targetPrimary));
  await waitForRoot(page, seed.targetPrimary);
  return {
    directClassic: "pass",
    menuAcceptance,
    browsingDoesNotMigrate: "pass",
    menuKeyboard: "pass",
    currentTreeFollowsAuthoritativeCwd: "pass",
  };
}

async function main() {
  const host = await startIsolatedHost({ disableRoutingV2: true });
  let browser = null;
  let context = null;
  let page = null;
  let cleanup = null;
  const projectRequests = [];
  const pageErrors = [];
  let contract = null;
  try {
    const seed = await seedContract(host);
    browser = await chromium.launch({ headless: true });
    ({ context, page } = await createContext(
      browser,
      host,
      seed,
      projectRequests,
      pageErrors,
      seed.current.id,
    ));
    const bundle = await exercise(page, host, seed, projectRequests);
    await page.close();
    page = null;
    await context.close();
    context = null;
    ({ context, page } = await createContext(
      browser,
      host,
      seed,
      projectRequests,
      pageErrors,
      seed.classic.id,
    ));
    const classic = await exerciseClassic(page, host, seed, projectRequests);
    contract = { bundle, classic };
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
