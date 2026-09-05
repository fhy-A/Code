const assert = require("node:assert/strict");
const cp = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const net = require("node:net");
const readline = require("node:readline");
const { chromium } = require("@playwright/test");

const repo = path.resolve(__dirname, "../../..");
const hostFile = path.join(__dirname, "code074_skill_startup_host.py");
const prefix = "code-h4-d2-";
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function bounded(promise, ms, label) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(label)), ms); })]); }
  finally { clearTimeout(timer); }
}
function launch(root, args) {
  const child = cp.spawn("python", ["-B", "-u", hostFile, root, ...args], {
    cwd: repo, windowsHide: true, stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, CODE_DATA_DIR: path.join(root, "profile"), TEMP: path.join(root, "temp"), TMP: path.join(root, "temp"), PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1" },
  });
  const events = [], errors = [];
  const lines = readline.createInterface({ input: child.stdout });
  lines.on("line", (line) => { try { events.push(JSON.parse(line)); } catch { errors.push(line); } });
  child.stderr.on("data", (data) => errors.push(String(data)));
  const exit = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => { lines.close(); resolve({ code, signal }); });
  });
  return { child, events, errors, exit };
}
async function ready(host) {
  return bounded((async () => {
    while (!host.events.some((item) => item.type === "ready")) {
      if (host.child.exitCode !== null) throw new Error(host.errors.join("\n"));
      await delay(30);
    }
    return host.events.find((item) => item.type === "ready");
  })(), 15_000, "host readiness timeout");
}
async function assertClosed(port) {
  const open = await new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.setTimeout(300);
    const done = (value) => { socket.destroy(); resolve(value); };
    socket.once("connect", () => done(true)); socket.once("error", () => done(false)); socket.once("timeout", () => done(false));
  });
  assert.equal(open, false, "fixture port remained open");
}

async function main() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
  await fs.mkdir(path.join(root, "temp"));
  let host, browser, addresses, passed = false;
  const evidence = [];
  try {
    const prepare = launch(root, ["prepare"]);
    assert.equal((await bounded(prepare.exit, 10_000, "prepare timeout")).code, 0);
    for (const relative of ["app.js", "agent-runtime.js", "index.html", "styles.css", "VERSION", "src", "dist/frontend", "assets"]) {
      await fs.cp(path.join(repo, relative), path.join(root, "app", relative), { recursive: true });
    }
    host = launch(root, ["serve", "on", "ui"]);
    addresses = await ready(host);
    const url = addresses.codeUrl;
    const getSnapshot = () => fetch(`${url}/api/skill-management/v1`).then((response) => response.json());
    browser = await chromium.launch({ headless: true });
    for (const mode of ["bundle", "classic"]) {
      const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
      const errors = [], requests = [];
      await context.addInitScript((mode) => {
        // Same offline Markdown fixture used by the existing CODE-074 H4.
        // This suite verifies settings/transactions, not Markdown rendering.
        window.marked = { Renderer: class {}, setOptions() {}, parse: String };
        localStorage.setItem("code-platform-auth", JSON.stringify({ token: "h4-d2-synthetic-token", userId: "7", username: "h4-user" }));
        localStorage.setItem("code-lang", mode === "bundle" ? "zh" : "en");
        localStorage.setItem("code-theme-mode", mode === "bundle" ? "dark" : "light");
        localStorage.setItem("code-theme", mode === "bundle" ? "dark" : "light");
      }, mode);
      await context.route("**/*", (route) => new URL(route.request().url()).origin === url ? route.continue() : route.abort());
      const page = await context.newPage();
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => { if (request.url().startsWith(url + "/api/skill-management")) requests.push({ method: request.method(), path: new URL(request.url()).pathname }); });
      try {
        await page.goto(url + (mode === "bundle" ? "/" : "/dist/frontend/index.classic.html"));
        await page.waitForFunction(() => document.documentElement.getAttribute("data-code-phase-one-shell-ready") === "true");
        await page.locator("#settingsMenuBtn").click();
        await page.locator('#settingsNav [data-panel="skills"]').click();
        await page.locator("#settingsSkillsSidebar [data-installation]").first().waitFor();
        if ((await getSnapshot()).mode === "immutable-v1") {
          page.once("dialog", (dialog) => dialog.accept());
          await page.locator("#managedConvert").click();
          await page.locator("#managedImport").waitFor();
        }
        const snapshot = await getSnapshot();
        const bundled = snapshot.installations.find((item) => item.kind === "bundled");
        await page.locator(`[data-installation="${bundled.installationId}"]`).click();
        await page.locator("#managedEdit").click();
        await page.locator("#skillEditorModal:not(.hidden)").waitFor();
        await page.waitForFunction(() => document.activeElement?.id === "skillEditBody");
        const focus = await page.locator("#skillEditBody").evaluate((element) => ({
          id: document.activeElement?.id, inert: element.closest("[inert]")?.id,
          disabled: element.disabled, display: getComputedStyle(element).display,
          modalDisplay: getComputedStyle(document.querySelector("#skillEditorModal")).display,
        }));
        assert.equal(focus.id, "skillEditBody", JSON.stringify(focus));
        const original = await page.locator("#skillEditBody").inputValue();
        const edited = original.replace("name: startup-alpha", `name: d2-${mode}`).replace("---\n\n", "license: synthetic\nmetadata:\n  untouched: yes\n---\n\n") + `\nD2_${mode}_body\n`;
        await page.locator("#skillEditBody").fill(edited);
        page.once("dialog", (dialog) => dialog.accept());
        await page.locator("#saveSkillEdit").click();
        await page.locator("#skillEditorModal").waitFor({ state: "hidden" });
        let local = (await getSnapshot()).installations.find((item) => item.displayName === `d2-${mode}`);
        assert.equal(local.kind, "local");
        await page.locator(`[data-installation="${local.installationId}"]`).click();
        await page.locator("#managedToggle").click();
        await page.waitForFunction(() => document.querySelector("#managedToggle")?.textContent.match(/启用|Enable/));
        assert.equal((await getSnapshot()).installations.find((item) => item.installationId === local.installationId).enabled, false);
        await page.locator("#managedRemove").click();
        await page.waitForFunction(() => document.querySelector("#managedRemove")?.textContent.match(/恢复|Restore/));
        await page.locator("#managedRemove").click();
        await page.waitForFunction(() => document.querySelector("#managedRemove")?.textContent.match(/卸载|uninstall/));
        // A dirty editor retains its original CAS and content across an external update.
        await page.locator("#managedEdit").click();
        await page.locator("#skillEditBody").fill(edited + "\nUNSAVED_DRAFT");
        const current = await getSnapshot();
        const preview = await fetch(`${url}/api/skill-management/v1/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ protocol: "skill-management/v1", base: current.registry, kind: "set-enabled", installationId: local.installationId, enabled: true }) }).then((response) => response.json());
        const response = await fetch(`${url}/api/skill-management/v1/operations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ protocol: "skill-management/v1", base: preview.base, request: preview.request, operationKey: `external-${mode}` }) });
        assert.equal(response.status, 200);
        await page.locator("#saveSkillEdit").click();
        await page.waitForFunction(() => !document.querySelector("#saveSkillEdit")?.disabled);
        assert.equal(await page.locator("#skillEditBody").inputValue(), edited + "\nUNSAVED_DRAFT");
        assert.equal(await page.locator("#skillEditorModal").isVisible(), true);
        page.once("dialog", (dialog) => dialog.accept());
        await page.locator("#cancelSkillEdit").click();
        await page.locator("#skillEditorModal").waitFor({ state: "hidden" });
        const otherLanguage = mode === "bundle" ? "en" : "zh";
        await page.locator(`[data-settings-lang="${otherLanguage}"]`).click();
        await page.waitForFunction((text) => document.querySelector("#managedEdit")?.textContent === text,
          otherLanguage === "en" ? "Edit" : "编辑");
        await page.locator(`[data-settings-lang="${mode === "bundle" ? "zh" : "en"}"]`).click();
        await page.waitForFunction((installationId) => {
          const selected = document.querySelector("#settingsSkillsSidebar [aria-current=true]");
          const detail = document.querySelector("#settingsSkillsDetail");
          return selected?.dataset.installation === installationId
            && detail?.dataset.renderedInstallation === installationId;
        }, local.installationId);
        assert.equal(await page.locator("#settingsSkillsDetail .skill-detail-name").textContent(), `d2-${mode}`);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.locator("#managedEdit").waitFor({ state: "visible" });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
        assert.equal(overflow, false);
        const actionsOverlap = await page.evaluate(() => {
          const end = Math.max(...[...document.querySelectorAll("#settingsManagedActions button")].map((item) => item.getBoundingClientRect().bottom));
          return end > document.querySelector("#settingsSkillsSidebar").getBoundingClientRect().top + 1;
        });
        assert.equal(actionsOverlap, false, "management controls overlap the installation list");
        await page.screenshot({ path: path.join(root, `d2-${mode}-390.png`), fullPage: true });
        assert.deepEqual(errors, []);
        evidence.push({ mode, language: mode === "bundle" ? "zh" : "en", viewport: 390, requests: requests.length, draftCAS: true, optionalPageErrors: errors });
      } catch (error) {
        console.error(JSON.stringify({ mode, pageErrors: errors, requests }));
        await page.screenshot({ path: path.join(root, `failure-${mode}.png`), fullPage: true });
        throw error;
      } finally { await context.close(); }
    }
    passed = true;
    console.log(JSON.stringify({ status: "passed", evidence, screenshotRoot: root }));
  } finally {
    if (browser) await browser.close();
    if (host) {
      host.child.stdin.write(JSON.stringify({ command: "shutdown" }) + "\n");
      const result = await bounded(host.exit, 10_000, "fixture host did not exit; root retained");
      assert.equal(result.code, 0);
      if (addresses) {
        await assertClosed(new URL(addresses.codeUrl).port);
        await assertClosed(new URL(addresses.fakeUrl).port);
      }
    }
    // Retain screenshots and synthetic data for visual QA; never touch old roots.
    console.log(JSON.stringify({ cleanup: "browser/context/host/ports closed", root, passed }));
  }
}
main().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
