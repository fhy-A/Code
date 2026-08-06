const base = require("@playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");
const { FIXTURE_CONTENT, startIsolatedHost } = require("./isolated-host.cjs");

const { expect } = base;
const MODEL_ID = "h4-e2e-model";

function countOccurrences(text, marker) {
  return String(text).split(marker).length - 1;
}

function summarizeLoopbackRequests(entries) {
  const counts = {};
  for (const entry of entries) {
    const key = `${entry.method} ${entry.path}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

async function attachTextBestEffort(testInfo, name, filePath, payload) {
  try {
    await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    await testInfo.attach(name, { path: filePath, contentType: "application/json" });
  } catch {}
}

async function attachScreenshotBestEffort(testInfo, page, filePath) {
  if (!page) return;
  try {
    await page.screenshot({ path: filePath, fullPage: true });
    await testInfo.attach("failure-screenshot", { path: filePath, contentType: "image/png" });
  } catch {}
}

const test = base.test.extend({
  h4: async ({ browser }, use, testInfo) => {
    const host = await startIsolatedHost();
    let context = null;
    let page = null;
    let useCompleted = false;
    const consoleEntries = [];
    const pageErrors = [];
    const loopbackRequests = [];
    const blockedRequests = [];
    const diagnosticSteps = [];

    try {
      expect(host.ready.environment).toEqual({
        parentSentinelPresent: false,
        sensitiveNames: [],
        homeIsIsolated: true,
      });
      context = await browser.newContext();
      await context.addInitScript(({ syntheticKey, platformToken, modelId }) => {
        class OfflineMarkedRenderer {}
        let markedOptions = {};
        window.marked = {
          Renderer: OfflineMarkedRenderer,
          setOptions(options) {
            markedOptions = options || {};
          },
          parse(source) {
            const text = String(source ?? "");
            return markedOptions.renderer?.paragraph
              ? markedOptions.renderer.paragraph({ text, tokens: [{ text }] })
              : text;
          },
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
        localStorage.setItem("code-permission-profile", "read");
        localStorage.setItem("code-lang", "en");
      }, {
        syntheticKey: host.syntheticKey,
        platformToken: host.platformToken,
        modelId: MODEL_ID,
      });

      await context.route("**/*", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const isLoopback = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
        if (!isLoopback) {
          blockedRequests.push({ method: request.method(), path: url.pathname, reason: "non-loopback" });
          await route.abort("blockedbyclient");
          return;
        }
        loopbackRequests.push({ method: request.method(), path: url.pathname });
        if (url.pathname === "/proxy/models") {
          await route.continue({
            headers: {
              ...request.headers(),
              "x-base-url": host.ready.fakeUrl,
            },
          });
          return;
        }
        await route.continue();
      });

      page = await context.newPage();
      page.on("console", (message) => {
        consoleEntries.push({ type: message.type(), text: host.sanitize(message.text()) });
      });
      page.on("pageerror", (error) => pageErrors.push(host.sanitize(error.stack || error.message)));

      const h4 = {
        page,
        host,
        consoleEntries,
        pageErrors,
        loopbackRequests,
        blockedRequests,
        diagnosticSteps,
        async open(runtime) {
          const target = runtime === "classic"
            ? `${host.ready.codeUrl}/dist/frontend/index.classic.html`
            : `${host.ready.codeUrl}/`;
          diagnosticSteps.push({ step: "navigate", runtime });
          await page.goto(target, { waitUntil: "domcontentloaded" });
          await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", MODEL_ID);
          await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
            element.value = fakeUrl;
          }, host.ready.fakeUrl);
        },
        async proveNonLoopbackBlocked() {
          const result = await page.evaluate(async () => {
            const scheme = ["ht", "tp"].join("");
            const hostParts = ["192", "0", "2", "1"];
            const target = `${scheme}://${hostParts.join(".")}/h4-block-probe`;
            try {
              await fetch(target);
              return "unexpected-success";
            } catch {
              return "blocked";
            }
          });
          expect(result).toBe("blocked");
          expect(blockedRequests.filter((entry) => entry.path === "/h4-block-probe")).toEqual([
            { method: "GET", path: "/h4-block-probe", reason: "non-loopback" },
          ]);
          expect(blockedRequests.every((entry) => entry.reason === "non-loopback")).toBe(true);
          diagnosticSteps.push({ step: "network-policy-probe", result, blockedCount: blockedRequests.length });
        },
        async submit(userMarker) {
          await page.locator("#prompt").fill(userMarker);
          await page.locator("#sendBtn").click();
          await expect(page.locator("#messages article.msg.user").filter({ hasText: userMarker })).toHaveCount(1);
          await expect(page.locator("#activeRunBanner.visible .active-run-line[role='status']")).toBeVisible();
          diagnosticSteps.push({ step: "running-state-observed", userMarker });
          await host.releaseModel();
        },
        async metrics() {
          return host.metrics();
        },
        evidence(label, payload) {
          console.log(`H4_EVIDENCE ${JSON.stringify({ label, ...payload })}`);
        },
      };

      await use(h4);
      useCompleted = true;
    } finally {
      const failed = !useCompleted || Boolean(testInfo.error) || testInfo.status !== testInfo.expectedStatus;
      if (failed) {
        const screenshotPath = path.join(host.artifactsDir, "failure.png");
        const consolePath = path.join(host.artifactsDir, "console.json");
        const diagnosticsPath = path.join(host.artifactsDir, "sanitized-diagnostics.json");
        await attachScreenshotBestEffort(testInfo, page, screenshotPath);
        await attachTextBestEffort(testInfo, "sanitized-console", consolePath, consoleEntries);
        await attachTextBestEffort(testInfo, "sanitized-diagnostics", diagnosticsPath, {
          diagnosticSteps,
          loopbackRequests: summarizeLoopbackRequests(loopbackRequests),
          blockedRequests,
          pageErrors,
        });
      }
      let contextCloseError = null;
      try {
        if (context) await context.close();
      } catch (error) {
        contextCloseError = error;
      }
      const cleanup = await host.stop();
      const repeatedCleanup = await host.stop();
      console.log(`H4_CLEANUP ${JSON.stringify({
        title: testInfo.title,
        portsClosed: cleanup.portsClosed,
        rootRemoved: cleanup.rootRemoved,
        temporaryFiles: cleanup.temporaryFiles,
        childPidRecorded: Number.isInteger(cleanup.childPid),
        childExited: cleanup.childExited,
        activeChildCount: cleanup.activeChildCount,
      })}`);
      expect(repeatedCleanup).toBe(cleanup);
      expect(cleanup.childExited).toBe(true);
      expect(cleanup.activeChildCount).toBe(0);
      expect(cleanup.portsClosed).toEqual([true, true]);
      expect(cleanup.rootRemoved).toBe(true);
      expect(cleanup.cleanupErrors).toEqual([]);
      if (contextCloseError) throw contextCloseError;
    }
  },
});

test("default bundle completes first plain-text send", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("bundle");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "bundle");
  await expect(page.locator("html")).toHaveAttribute("data-code-frontend-ready", "true");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_PLAIN_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_PLAIN_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_PLAIN_USER")).toBe(1);
  expect(countOccurrences(text, "H4_PLAIN_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "plain-text", stream: true, hasToolResult: false },
  ]);
  expect(metrics.toolExecutions).toEqual([]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("bundle-plain", {
    runtime: "bundle",
    ready: true,
    chatRequests: metrics.chatRequests.length,
    toolExecutions: 0,
    dom: { user: 1, final: 1, runningObserved: true },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});

test("default bundle executes one read-only tool without duplicate DOM", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("bundle");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "bundle");
  await expect(page.locator("html")).toHaveAttribute("data-code-frontend-ready", "true");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_TOOL_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_TOOL_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const stage = page.locator("#messages article.msg.assistant.agent-commentary").filter({ hasText: "H4_TOOL_STAGE" });
  const process = page.locator("#messages article.tool-process");
  const result = page.locator("#messages .tool-process-detail pre").filter({ hasText: FIXTURE_CONTENT.trim() });
  await expect(stage).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(process.locator(".tool-process-item")).toHaveCount(1);
  await expect(result).toHaveCount(1);
  const user = page.locator("#messages article.msg.user").filter({ hasText: "H4_TOOL_USER" });
  const ordered = await page.evaluate(({ userMarker, stageMarker, finalMarker }) => {
    const messages = document.querySelector("#messages");
    const find = (selector, marker) => [...messages.querySelectorAll(selector)]
      .find((element) => element.textContent.includes(marker));
    const nodes = [
      find("article.msg.user", userMarker),
      find("article.msg.assistant.agent-commentary", stageMarker),
      messages.querySelector("article.tool-process"),
      find("article.msg.assistant", finalMarker),
    ];
    return nodes.every(Boolean) && nodes.slice(0, -1).every((node, index) => (
      Boolean(node.compareDocumentPosition(nodes[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)
    ));
  }, {
    userMarker: "H4_TOOL_USER",
    stageMarker: "H4_TOOL_STAGE",
    finalMarker: "H4_TOOL_FINAL",
  });
  expect(ordered).toBe(true);
  await expect(user).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_TOOL_STAGE")).toBe(1);
  expect(countOccurrences(text, FIXTURE_CONTENT.trim())).toBe(1);
  expect(countOccurrences(text, "H4_TOOL_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "tool-call", stream: true, hasToolResult: false },
    { scenario: "tool-final", stream: true, hasToolResult: true },
  ]);
  expect(metrics.toolExecutions).toEqual([{ action: "read_file", path: "fixture.txt" }]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("bundle-read-tool", {
    runtime: "bundle",
    ready: true,
    chatRequests: metrics.chatRequests.length,
    toolExecutions: metrics.toolExecutions.length,
    dom: { user: 1, stage: 1, tool: 1, result: 1, final: 1, ordered },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});

test("classic fallback completes one plain-text task", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("classic");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "classic-fallback");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_CLASSIC_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_CLASSIC_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_CLASSIC_USER")).toBe(1);
  expect(countOccurrences(text, "H4_CLASSIC_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "classic-text", stream: true, hasToolResult: false },
  ]);
  expect(metrics.toolExecutions).toEqual([]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("classic-plain", {
    runtime: "classic-fallback",
    chatRequests: metrics.chatRequests.length,
    toolExecutions: 0,
    dom: { user: 1, final: 1, runningObserved: true },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});
