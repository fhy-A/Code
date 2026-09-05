const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const cp = require("node:child_process");
const readline = require("node:readline");
const net = require("node:net");
const { chromium, expect } = require("@playwright/test");

const repo = path.resolve(__dirname, "../../..");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await delay(60);
  }
  throw new Error(message);
}
async function api(base, route, body) {
  const response = await fetch(new URL(route, base), {
    method: body === undefined ? "GET" : "POST", headers: {"content-type": "application/json"},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(5000),
  });
  assert.ok(response.ok, `${route}: ${response.status}`);
  return response.json();
}
async function closed(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({host: "127.0.0.1", port});
    const finish = (value) => {socket.destroy(); resolve(value);};
    socket.once("connect", () => finish(false));
    socket.once("error", () => finish(true));
    socket.setTimeout(500, () => finish(true));
  });
}

async function exercise(browser, ready, root, language, theme) {
  const audit = {language, theme, requests: [], runs: [], errors: [], blocked: [], abortedRequests:[]};
  const pendingWrites = new Set();
  const context = await browser.newContext({viewport: {width: 1280, height: 850}, serviceWorkers: "block"});
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ready.codeUrl && url.origin !== ready.fakeUrl) {
      audit.blocked.push(url.hostname + url.pathname);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  await context.addInitScript(({model, language, theme}) => {
    class OfflineRenderer {}
    window.marked = {Renderer: OfflineRenderer, setOptions() {}, parse(value) {return String(value || "");}};
    localStorage.setItem("code-key-config", JSON.stringify([{name: "H4 simulated", key: "h4-not-a-real-key", enabled: true, source: "manual"}]));
    localStorage.setItem("code-platform-auth", JSON.stringify({token: "h4-not-a-real-token", userId: "7", username: "h4-simulated"}));
    localStorage.setItem("code-model", model);
    localStorage.setItem("code-permission-profile", "plan");
    localStorage.setItem("code-lang", language);
    localStorage.setItem("code-theme-mode", theme);
    window.__loadingProtocol = "pending";
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (new URL(String(args[0]), location.href).pathname === "/api/browser-heartbeat") {
        response.clone().json().then((value) => {window.__loadingProtocol = value.skillLoadingProtocol || "off";});
      }
      return response;
    };
  }, {model: ready.model, language, theme});
  context.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/agent/runs") audit.requests.push(request.postDataJSON());
    if (request.method() === "PUT") pendingWrites.add(request);
  });
  context.on("requestfinished", (request) => pendingWrites.delete(request));
  context.on("requestfailed", (request) => {
    pendingWrites.delete(request);
    if (new URL(request.url()).origin === ready.codeUrl) audit.abortedRequests.push({method:request.method(), path:new URL(request.url()).pathname, error:request.failure()?.errorText});
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => audit.errors.push(error.message));
  try {
    async function open() {
      await until(() => pendingWrites.size === 0, "session save was still in progress before navigation");
      await page.goto(ready.codeUrl, {waitUntil: "domcontentloaded"});
      await page.waitForFunction(() => document.documentElement.getAttribute("data-code-frontend-ready") === "true");
      await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", ready.model);
      await page.waitForFunction(() => window.__loadingProtocol !== "pending");
      await page.locator("#baseUrl").evaluate((element, url) => {element.value = url;}, ready.fakeUrl);
    }
    async function submit(text) {
      await page.locator("#newChat").click();
      await page.locator("#baseUrl").evaluate((element, url) => {element.value = url;}, ready.fakeUrl);
      const created = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/agent/runs");
      await page.locator("#prompt").fill(text);
      await page.locator("#sendBtn").click();
      const response = await created;
      const body = await response.json();
      assert.equal(response.status(), 201, JSON.stringify(body));
      audit.runs.push(body.agentRunId);
      return body.agentRunId;
    }
    async function record(id) {
      return JSON.parse(await fs.readFile(path.join(root, "profile/agent-runs", `${id}.json`), "utf8"));
    }
    async function finish(id) {
      await until(async () => ["completed", "failed", "cancelled"].includes((await record(id)).status), "Run did not finish");
      const result = await record(id);
      assert.equal(result.status, "completed", JSON.stringify({error:result.error, code:result.errorCode}));
      await page.locator("#messages article.msg.assistant").filter({hasText:"H4_SIMULATED_CHOICE_FINAL"}).last().waitFor({state:"visible"});
      await expect(page.locator("#sendBtn")).not.toHaveClass(/running/);
      await expect(page.locator("[data-active-run-anchor]")).toHaveCount(0);
      await until(() => pendingWrites.size === 0, "terminal session save did not settle");
      return result;
    }
    async function checkTraces(expected, label) {
      await expect(page.locator(".execution-trace-skill-chip")).toHaveCount(0);
      const rows = page.locator(".tool-process-item").filter({has:page.locator(".tool-process-row-heading strong", {hasText:language === "zh" ? "加载 Skill" : "Load Skill"})});
      await expect(rows).toHaveCount(expected.length);
      const observed = await rows.locator(".tool-process-row-heading code").allTextContents();
      assert.deepEqual(observed, expected);
      if (label !== "live") {
        await expect(page.locator("#sendBtn")).not.toHaveClass(/running/);
        await expect(page.locator("[data-active-run-anchor]")).toHaveCount(0);
        await expect(rows.filter({has:page.locator(".tool-process-indicator.running, .tool-process-indicator.pending")})).toHaveCount(0);
        if (!label.includes("failed") && !label.includes("off-restored")) {
          for (let index=0; index<expected.length; index+=1) await expect(rows.nth(index)).toHaveClass(/succeeded|completed/);
        }
      }
      const ids = await rows.evaluateAll((elements) => elements.map((element) => element.dataset.toolCallId));
      assert.equal(new Set(ids).size, ids.length, "duplicate loading operations");
      assert.equal((await page.locator("#messages").innerText()).includes("→ use_skill"), false);
      const collapsed = page.locator(".execution-trace:not(.is-expanded) > .execution-trace-summary");
      if (await collapsed.count()) await collapsed.first().click();
      for (const summary of await page.locator(".tool-process-stage:not([open]) > summary").all()) await summary.click();
      for (const name of expected) {
        const heading = page.locator(".tool-process-stage-heading:visible, .tool-process-row-heading:visible")
          .filter({has:page.locator("strong", {hasText:language === "zh" ? "加载 Skill" : "Load Skill"})})
          .filter({has:page.locator("code", {hasText:name})});
        await expect(heading.first()).toBeVisible();
      }
      await page.screenshot({path:path.join(root, `${language}-${theme}-${label}.png`), fullPage:true});
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    await open();
    assert.equal(await page.evaluate(() => window.__loadingProtocol), "model-driven-v1");
    const mid = await submit("H4_MID: This run uses simulated choices to inspect then load ledger and refine.");
    if (language === "zh") {
      await until(async () => (await api(ready.codeUrl, "/__h4/state")).waiting, "loader did not reach its real operation");
      await checkTraces(["ledger"], "live");
      await expect(page.locator('.tool-process-item[data-tool-call-id="owner"]')).toHaveClass(/running|pending/);
      await api(ready.codeUrl, "/__h4/release", {});
    }
    const done = await finish(mid);
    assert.equal(done.version, 7);
    assert.deepEqual(done.activeSkillNames, ["ledger", "refine"]);
    assert.equal(done.toolExecutions.before.skillLoadCount, 0);
    assert.deepEqual(done.toolExecutions.before.skillExecutionContext.skills, []);
    await checkTraces(["ledger", "refine"], "completed");
    await open();
    await checkTraces(["ledger", "refine"], "refreshed");
    const explicit = await submit("/ledger H4_EXPLICIT: simulated upstream, explicit user selection.");
    const selected = await finish(explicit);
    assert.equal(selected.skillLoading.loads.length, 1);
    assert.equal(selected.skillLoading.loads[0].origin, "explicit");
    assert.equal(selected.messages.some((message) => message.role === "assistant" && message.tool_calls?.some((call) => call.function?.name === "use_skill")), false);
    await checkTraces(["ledger"], "explicit");
    await open();
    await checkTraces(["ledger"], "explicit-refreshed");
    const failed = await submit("H4_FAILURE: simulated unavailable Skill request.");
    const rejected = await finish(failed);
    assert.equal(rejected.toolExecutions.unavailable.result.errorCode, "skill_loading_not_available_in_catalog");
    assert.deepEqual(rejected.activeSkillNames, []);
    await checkTraces(["missing"], "failed-load");
    await expect(page.locator('.tool-process-item[data-tool-call-id="unavailable"]')).toHaveClass(/failed/);
    await open();
    await checkTraces(["missing"], "failed-refreshed");
    await api(ready.codeUrl, "/__h4/off", {});
    await open();
    assert.equal(await page.evaluate(() => window.__loadingProtocol), "off");
    await checkTraces(["missing"], "off-restored-v7");
    const old = await submit("/ledger H4_NONE: simulated legacy run without a load event.");
    const legacy = await finish(old);
    assert.equal(legacy.version, 6);
    assert.deepEqual(legacy.activeSkillNames, ["ledger"]);
    await checkTraces([], "old-no-invented-event");
    await api(ready.codeUrl, "/__h4/on", {});
    await open();
    const none = await submit("H4_NONE: simulated model chooses ordinary conversation without Skill.");
    const empty = await finish(none);
    assert.equal(empty.version, 7);
    assert.deepEqual(empty.skillLoading.loads, []);
    await checkTraces([], "none");
    assert.deepEqual(audit.errors, []);
    assert.ok(audit.requests.slice(0,3).every((request) => request.skillActivationRequest.schemaVersion === 2));
    return {...audit, requests:audit.requests.map((request) => ({version:request.skillActivationRequest.schemaVersion, explicit:request.skillActivationRequest.explicitSkill})), simulatedChoices:true};
  } catch (error) {
    await page.screenshot({path:path.join(root, `${language}-failure.png`), fullPage:true}).catch(() => {});
    await fs.writeFile(path.join(root, `${language}-audit.json`), JSON.stringify(audit, null, 2));
    error.message += `; audit saved in ${root}`;
    throw error;
  } finally {
    await context.close();
  }
}

(async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "code-h4-r084-"));
  const temp = path.join(root, "tmp"); await fs.mkdir(temp);
  const child = cp.spawn("python", ["-B", "-u", path.join(__dirname,"code074_skill_loading_host.py"), root], {
    cwd:repo, windowsHide:true, stdio:["pipe","pipe","pipe"],
    env:{...process.env, CODE_DATA_DIR:path.join(root,"profile"), TEMP:temp, TMP:temp,
         PYTHONUTF8:"0", PYTHONIOENCODING:"utf-8", PYTHONDONTWRITEBYTECODE:"1"},
  });
  const events = []; let stderr = ""; let exited = false; let exitCode = null; let browser;
  const lines = readline.createInterface({input:child.stdout});
  lines.on("line", (line) => {try {events.push(JSON.parse(line));} catch {}});
  child.stderr.on("data", (data) => {stderr += data;});
  child.on("exit", (code) => {exited=true; exitCode=code;});
  child.on("error", (error) => {stderr+=error.message; exited=true;});
  let ready, results, failure;
  console.log(JSON.stringify({root, simulatedChoices:true}));
  try {
    ready = await until(() => events.find((event) => event.type === "ready") || (exited && Promise.reject(new Error(stderr))), "host startup timed out");
    browser = await chromium.launch({headless:true});
    results = [];
    for (const [language,theme] of [["zh","dark"],["en","light"]]) results.push(await exercise(browser, ready, root, language, theme));
  } catch (error) {failure = error;} finally {
    if (browser) await browser.close();
    if (!exited) child.stdin.write(JSON.stringify({command:"shutdown"})+"\n");
    await until(() => exited, "host shutdown timed out", 10000).catch(() => child.kill());
    await until(() => exited, "host process still running", 5000);
    lines.close();
    await fs.writeFile(path.join(root,"host-stderr.txt"), stderr, "utf8");
  }
  const cleanup = {exitCode, stopped:events.find((event) => event.type === "stopped"), portsClosed: ready ? await Promise.all([closed(Number(new URL(ready.codeUrl).port)), closed(Number(new URL(ready.fakeUrl).port))]) : []};
  await fs.writeFile(path.join(root,"result.json"), JSON.stringify({ok:!failure, results, cleanup, error:failure?.stack},null,2));
  assert.equal(exitCode, 0, stderr);
  assert.equal(cleanup.stopped?.workersStopped, true);
  assert.deepEqual(cleanup.portsClosed, [true,true]);
  if (failure) throw failure;
  console.log(JSON.stringify({ok:true, root, results, cleanup}));
})().catch((error) => {console.error(error.stack); process.exitCode=1;});
