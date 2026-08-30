const assert = require("node:assert/strict");
const { chromium } = require("@playwright/test");
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

async function installDisclosureFixture(page) {
  await page.evaluate((longPath) => {
    document.querySelector(".chat-pane").classList.remove("empty-chat");
    document.getElementById("messageList").innerHTML = `
      <button id="disclosureFocusStart" type="button">focus start</button>
      <section id="traceFixture" class="execution-trace completed" data-execution-trace="fixture">
        <div id="traceSummary" class="execution-trace-summary" role="button" tabindex="0" aria-expanded="false" data-execution-trace-toggle>
          <div class="completed-run-status msg" data-completed-run-status>
            <span class="completed-run-line"><span class="completed-run-label">Thought and execution</span><span class="run-time">1.2s</span></span>
          </div>
          <span id="traceChevron" class="execution-trace-chevron" aria-hidden="true"></span>
        </div>
        <div class="execution-trace-body">
          <article class="msg assistant tool-process execution-trace-persistent">
            <details id="stageFixture" class="tool-process-stage succeeded" data-tool-process-id="fixture-stage">
              <summary id="stageSummary" class="tool-process-stage-summary">
                <span class="tool-process-stage-heading"><strong>Tools</strong><code>src/ui</code></span>
                <span id="stageChevron" class="tool-process-stage-chevron" aria-hidden="true"></span>
              </summary>
              <div class="tool-process-stage-body"><div class="tool-process-list">
                <details id="itemFixture" class="tool-process-item succeeded" data-tool-process-item-key="fixture-short">
                  <summary id="itemSummary">
                    <span class="tool-process-indicator succeeded" aria-hidden="true"></span>
                    <span class="tool-process-row-heading"><strong>Read</strong><code>README.md</code></span>
                    <span class="tool-process-outcome">done</span>
                    <span id="itemChevron" class="tool-process-chevron" aria-hidden="true"></span>
                  </summary>
                  <div class="tool-process-body"><div class="tool-process-detail"><strong>Output</strong><pre>short item</pre></div></div>
                </details>
                <details id="longItemFixture" class="tool-process-item succeeded" data-tool-process-item-key="fixture-long">
                  <summary id="longItemSummary">
                    <span class="tool-process-indicator succeeded" aria-hidden="true"></span>
                    <span class="tool-process-row-heading"><strong>Read</strong><code id="longItemPath">${longPath}</code></span>
                    <span id="longItemOutcome" class="tool-process-outcome">done</span>
                    <span id="longItemChevron" class="tool-process-chevron" aria-hidden="true"></span>
                  </summary>
                  <div class="tool-process-body"><div class="tool-process-detail"><strong>Output</strong><pre>long item</pre></div></div>
                </details>
              </div></div>
            </details>
          </article>
        </div>
      </section>`;
  }, LONG_PATH);
}

async function installFinalStateTransitionOverride(page) {
  await page.addStyleTag({
    content: `
      #traceChevron,
      #stageChevron,
      #itemChevron,
      #longItemChevron {
        transition: none !important;
      }
    `,
  });
  const transitions = await page.evaluate(() => Object.fromEntries(
    ["traceChevron", "stageChevron", "itemChevron", "longItemChevron"].map((id) => [
      id,
      getComputedStyle(document.getElementById(id)).transitionDuration,
    ]),
  ));
  assert.deepEqual(transitions, {
    traceChevron: "0s",
    stageChevron: "0s",
    itemChevron: "0s",
    longItemChevron: "0s",
  });
  return transitions;
}

async function disclosureState(page) {
  return page.evaluate(() => ({
    traceExpanded: document.getElementById("traceFixture").classList.contains("is-expanded"),
    traceAria: document.getElementById("traceSummary").getAttribute("aria-expanded"),
    stageOpen: document.getElementById("stageFixture").open,
    itemOpen: document.getElementById("itemFixture").open,
  }));
}

async function arrowDirection(page, selector) {
  return page.locator(selector).evaluate((element) => {
    const transform = getComputedStyle(element).transform;
    const match = transform.match(/^matrix\(([^)]+)\)$/);
    if (!match) return { transform, direction: "unknown" };
    const values = match[1].split(",").map(Number);
    return { transform, direction: values[1] < 0 ? "right" : "down" };
  });
}

async function clickBlankSpace(page, containerSelector, summarySelector) {
  const point = await page.evaluate(({ containerSelector: container, summarySelector: summary }) => {
    const containerRect = document.querySelector(container).getBoundingClientRect();
    const summaryRect = document.querySelector(summary).getBoundingClientRect();
    const x = containerRect.right - 8;
    const finite = Number.isFinite(x) && Number.isFinite(summaryRect.right);
    if (!finite || x <= summaryRect.right + 4) {
      throw new Error(`No blank hit-test space for ${summary}: ${JSON.stringify({ containerRect, summaryRect })}`);
    }
    return { x, y: summaryRect.top + summaryRect.height / 2 };
  }, { containerSelector, summarySelector });
  await page.mouse.click(point.x, point.y);
  return point;
}

async function captureGeometry(page) {
  return page.evaluate(() => {
    const rect = (selector) => {
      const box = document.querySelector(selector).getBoundingClientRect();
      return { left: box.left, top: box.top, right: box.right, bottom: box.bottom, width: box.width, height: box.height };
    };
    const controls = {
      trace: rect("#traceSummary"),
      stage: rect("#stageSummary"),
      item: rect("#itemSummary"),
    };
    const longPath = document.getElementById("longItemPath");
    const longPathStyle = getComputedStyle(longPath);
    const orderSelectors = [
      "#longItemSummary .tool-process-indicator",
      "#longItemSummary .tool-process-row-heading strong",
      "#longItemPath",
      "#longItemOutcome",
      "#longItemChevron",
    ];
    const order = orderSelectors.map((selector) => ({ selector, ...rect(selector) }));
    const overlaps = [];
    for (let index = 1; index < order.length; index += 1) {
      if (order[index - 1].right > order[index].left + 1) {
        overlaps.push([order[index - 1].selector, order[index].selector]);
      }
    }
    return {
      controls,
      longPath: {
        clientWidth: longPath.clientWidth,
        scrollWidth: longPath.scrollWidth,
        overflow: longPathStyle.overflow,
        textOverflow: longPathStyle.textOverflow,
        whiteSpace: longPathStyle.whiteSpace,
      },
      order,
      overlaps,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      viewportWidth: innerWidth,
    };
  });
}

async function captureFocus(page) {
  await page.evaluate(() => {
    document.querySelectorAll(".is-pointer-focus").forEach((element) => element.classList.remove("is-pointer-focus"));
  });
  await page.locator("#disclosureFocusStart").focus();
  const result = {};
  for (const [name, selector] of [
    ["trace", "#traceSummary"],
    ["stage", "#stageSummary"],
    ["item", "#itemSummary"],
  ]) {
    await page.keyboard.press("Tab");
    result[name] = await page.locator(selector).evaluate((element) => ({
      active: document.activeElement === element,
      outlineStyle: getComputedStyle(element).outlineStyle,
      outlineWidth: getComputedStyle(element).outlineWidth,
    }));
  }
  return result;
}

async function exerciseRuntime(browser, host, runtime, audit) {
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
    await installDisclosureFixture(page);
    const transitionOverride = await installFinalStateTransitionOverride(page);

    const initial = await disclosureState(page);
    assert.deepEqual(initial, {
      traceExpanded: false,
      traceAria: "false",
      stageOpen: false,
      itemOpen: false,
    });
    assert.equal((await arrowDirection(page, "#traceChevron")).direction, "right");
    assert.equal((await arrowDirection(page, "#stageChevron")).direction, "right");

    const blankSpaceClicks = [];
    blankSpaceClicks.push(await clickBlankSpace(page, "#traceFixture", "#traceSummary"));
    assert.deepEqual(await disclosureState(page), initial);
    await page.locator("#traceSummary").click();
    assert.equal((await disclosureState(page)).traceExpanded, true);
    assert.equal((await disclosureState(page)).traceAria, "true");
    assert.equal((await arrowDirection(page, "#traceChevron")).direction, "down");

    blankSpaceClicks.push(await clickBlankSpace(page, "#stageFixture", "#stageSummary"));
    assert.equal((await disclosureState(page)).stageOpen, false);
    await page.locator("#stageSummary").click();
    assert.equal((await disclosureState(page)).stageOpen, true);
    assert.equal((await arrowDirection(page, "#stageChevron")).direction, "down");

    blankSpaceClicks.push(await clickBlankSpace(page, "#itemFixture", "#itemSummary"));
    assert.equal((await disclosureState(page)).itemOpen, false);
    await page.locator("#itemSummary").click();
    assert.equal((await disclosureState(page)).itemOpen, true);
    assert.equal((await arrowDirection(page, "#itemChevron")).direction, "down");

    const geometry = await captureGeometry(page);
    for (const control of Object.values(geometry.controls)) {
      assert.equal(control.height >= 28 && control.height <= 36, true);
    }
    assert.equal(geometry.longPath.scrollWidth > geometry.longPath.clientWidth, true);
    assert.deepEqual(
      {
        overflow: geometry.longPath.overflow,
        textOverflow: geometry.longPath.textOverflow,
        whiteSpace: geometry.longPath.whiteSpace,
      },
      { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
    );
    assert.deepEqual(geometry.overlaps, []);
    assert.equal(geometry.documentWidth <= geometry.viewportWidth, true);
    assert.equal(geometry.bodyWidth <= geometry.viewportWidth, true);

    const focus = await captureFocus(page);
    for (const state of Object.values(focus)) {
      assert.equal(state.active, true);
      assert.notEqual(state.outlineStyle, "none");
      assert.notEqual(state.outlineWidth, "0px");
    }

    await page.locator("#traceSummary").focus();
    await page.keyboard.press("Space");
    assert.deepEqual(
      { expanded: (await disclosureState(page)).traceExpanded, aria: (await disclosureState(page)).traceAria },
      { expanded: false, aria: "false" },
    );
    await page.keyboard.press("Enter");
    assert.deepEqual(
      { expanded: (await disclosureState(page)).traceExpanded, aria: (await disclosureState(page)).traceAria },
      { expanded: true, aria: "true" },
    );
    await page.locator("#stageSummary").focus();
    await page.keyboard.press("Space");
    assert.equal((await disclosureState(page)).stageOpen, false);
    await page.keyboard.press("Space");
    assert.equal((await disclosureState(page)).stageOpen, true);
    await page.locator("#itemSummary").focus();
    await page.keyboard.press("Enter");
    assert.equal((await disclosureState(page)).itemOpen, false);
    await page.keyboard.press("Enter");
    assert.equal((await disclosureState(page)).itemOpen, true);

    const light = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.evaluate(() => document.body.classList.add("theme-dark"));
    const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    assert.notEqual(light, dark);
    assert.equal((await arrowDirection(page, "#traceChevron")).direction, "down");
    assert.equal((await arrowDirection(page, "#stageChevron")).direction, "down");
    assert.equal((await arrowDirection(page, "#itemChevron")).direction, "down");
    assert.deepEqual(pageErrors, []);

    return {
      runtime,
      transitionOverride,
      initial,
      blankSpaceClicks,
      geometry,
      focus,
      keyboard: await disclosureState(page),
      themes: { light, dark },
    };
  } finally {
    await page.close();
    await context.close();
  }
}

function summarizeStartupIsolation(audit) {
  const summary = {};
  for (const runtime of ["bundle", "classic"]) {
    summary[runtime] = {};
    for (const pathname of Object.keys(STARTUP_FIXTURES)) {
      const initiated = audit.initiated.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      const fulfilled = audit.startupFulfilled.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      const serverReceived = audit.serverBound.filter((entry) => (
        entry.runtime === runtime && entry.method === "POST" && entry.path === pathname
      ));
      assert.equal(initiated.length, 1);
      assert.equal(fulfilled.length, 1);
      assert.deepEqual(serverReceived, []);
      summary[runtime][pathname] = { initiated: 1, fulfilled: 1, serverReceived: 0 };
    }
  }
  return summary;
}

function assertZeroSideEffects(before, after, audit) {
  assert.deepEqual(audit.blockedWrites, []);
  assert.equal(audit.blockedExternal.every((entry) => entry.method === "GET"), true);
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
    result = {
      ok: true,
      command: "code043-compact-disclosures-final-state-selfcheck",
      realRuntimeLoads: { bundle: 1, classic: 1 },
      runtimes: [bundle, classic],
      startupIsolation: summarizeStartupIsolation(audit),
      sideEffects: assertZeroSideEffects(before, after, audit),
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
