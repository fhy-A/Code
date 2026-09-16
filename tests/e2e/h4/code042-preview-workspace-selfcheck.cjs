const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { chromium, expect } = require("@playwright/test");
const { startIsolatedHost, getActiveChildCount } = require("./isolated-host.cjs");

async function main() {
  const evidence = await fs.mkdtemp(path.join(os.tmpdir(), "code042-preview-evidence-"));
  console.log(`EVIDENCE ${evidence}`);
  const host = await startIsolatedHost({disableRoutingV2:true});
  const checks = [], errors = [], network = [], transitions = [], routeErrors = [], routeRequests = [];
  let stateContract = null, reviewContract = null;
  let browser, context, cleanup, activePage;
  const api = async (url, body) => {
    const response = await fetch(host.ready.codeUrl + url, body ? {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    } : {});
    assert(response.ok, `${response.status}: ${url}`);
    return response.json();
  };
  try {
    for (const [name, text] of Object.entries({ "a.txt": "ALPHA\n".repeat(100), "b.md": "# BRAVO",
      "c.csv": "Name,Value\nCharlie,3", "d.txt": "DELTA", "long-same-filename-for-narrow-preview-tab-01.txt": "LONG" })) {
      await fs.writeFile(path.join(host.projectDir, name), text);
    }
    const stream = "BT /F1 16 Tf 30 200 Td (Preview PDF) Tj ET";
    const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];
    let pdf = "%PDF-1.4\n"; const offsets = [0];
    objects.forEach((object,index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index+1} 0 obj\n${object}\nendobj\n`; });
    const xref = Buffer.byteLength(pdf);
    pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((offset)=>String(offset).padStart(10,"0")+" 00000 n \n").join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
    await fs.writeFile(path.join(host.projectDir, "sample.pdf"), pdf);
    await fs.writeFile(path.join(host.projectDir, "sample.bin"), Buffer.from([0,1,2,0]));
    const a = await api("/api/sessions", { title: "Preview A", cwd: host.projectDir });
    const b = await api("/api/sessions", { title: "Preview B", cwd: host.projectDir });
    browser = await chromium.launch({ headless: true });
    for (const runtime of ["bundle", "classic"]) {
      context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: "block" });
      const routingState={closing:false,previewGate:null};
      const pendingRoutes=new Set();
      await context.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        const requestEvidence={runtime,handler:"context-dispatcher",url:route.request().url(),method:route.request().method(),stage:routingState.closing?"teardown":"active",outcome:"pending"};
        routeRequests.push(requestEvidence);
        const gate=routingState.previewGate;
        const task=(async()=>{
        try {
        if(url.pathname==="/api/preview/file" && gate)await gate(url);
        if (!["127.0.0.1", "localhost", "::1"].includes(url.hostname)) return await route.abort();
        if (process.env.CODE042_TRACE === "1" && (url.pathname.endsWith("/src/features/preview.js") || url.pathname.endsWith("/code.bundle.js"))) {
          const response = await route.fetch(); let source = await response.text();
          const start = source.indexOf("function registerPreviewFeature");
          const end = source.indexOf("features.preview = Object.freeze", start);
          if (start >= 0 && end > start) {
            let part = source.slice(start,end);
            for (const name of ["beginNavigation", "clearRenderer", "restore", "loadFile"]) {
              const pattern = new RegExp(`(function ${name}\\d*\\([^\\n]*\\) \{)`);
              part = part.replace(pattern, `$1 window.__previewTransitions.push({event:"${name}",epoch,requestSeq,scope:scope?.sessionId||null,stack:new Error().stack});`);
            }
            source = source.slice(0,start)+part+source.slice(end);
          }
          return await route.fulfill({response,body:source});
        }
        if (url.pathname === "/api/image-routes/refresh") return await route.fulfill({ json: { version: 1, routes: [], ok: true } });
        if (url.pathname === "/api/code/sync-keys") return await route.fulfill({ json: { tokens: [], keys: {} } });
        return await route.continue();
        } catch(error) {
          requestEvidence.outcome="failed";
          routeErrors.push({...requestEvidence,closing:routingState.closing,message:String(error),failure:route.request().failure()});
        } finally {if(requestEvidence.outcome==="pending")requestEvidence.outcome="handled";}
        })();
        pendingRoutes.add(task);try {await task;}finally{pendingRoutes.delete(task);}
      });
      await context.addInitScript(({ id, token }) => {
        window.marked = { Renderer: class {}, setOptions() {}, parse: (text) => String(text) };
        if (!sessionStorage.getItem("code042-seeded")) {
          localStorage.setItem("code-key-config", "[]");
          localStorage.setItem("code-platform-auth", JSON.stringify({ token, userId: "42", username: "fixture" }));
          localStorage.setItem("code-lang", "en");
          localStorage.setItem("code-foreground-view", "session");
          localStorage.setItem("code-last-session", id);
          localStorage.setItem("code-expanded-project-sessions", JSON.stringify({ __unassigned_sessions__: true }));
          sessionStorage.setItem("code042-seeded", "1");
        }
      }, { id: a.id, token: host.platformToken });
      const page = await context.newPage(); activePage = page;
      await page.addInitScript(() => {
        window.__previewEvents = []; window.__previewTransitions = [];
        for (const type of ["click", "auxclick", "mousedown", "mouseup", "dblclick"])
          document.addEventListener(type, (e) => { if (e.target.closest(".file-item")) window.__previewEvents.push({type,button:e.button,detail:e.detail,path:e.target.closest(".file-item").dataset.path}); }, true);
      });
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (url.pathname.startsWith("/api/preview/") || url.pathname === "/api/config")
          network.push({kind:"request",time:Date.now(),url:request.url(),method:request.method(),body:request.method()==="POST" ? request.postData() : null});
      });
      page.on("response", async (response) => {
        const url = new URL(response.url());
        if (url.pathname.startsWith("/api/preview/")) network.push({kind:"response",time:Date.now(),url:response.url(),status:response.status(),body:await response.text().catch(()=>"")});
      });
      page.on("pageerror", (error) => errors.push(String(error.stack || error)));
      await page.goto(host.ready.codeUrl + (runtime === "classic" ? "/dist/frontend/index.classic.html" : "/"));
      const file = (name) => page.locator(`.file-item[data-path="${name}"]`);
      const tabs = () => page.locator("#previewTabs [role=tab]");
      const current = () => page.locator("#previewTabs [aria-selected=true]");
      await file("a.txt").waitFor();
      await page.waitForFunction(() => document.querySelector("#sessionTitle")?.value === "Preview A");
      await file("a.txt").click();
      await expect(tabs()).toHaveCount(1);
      await expect(page.locator("#filePreview")).toContainText("ALPHA");
      await file("b.md").dblclick();
      await expect(tabs()).toHaveCount(2);
      await expect(tabs().nth(0)).toHaveText("a.txt");
      await expect(current()).toHaveText("b.md");
      await file("c.csv").click({ modifiers: ["Control"] });
      await expect(tabs()).toHaveCount(3);
      await file("d.txt").click();
      await expect(tabs()).toHaveCount(3);
      await expect(tabs().nth(0)).toHaveText("d.txt");
      await file("b.md").click({ button: "middle" });
      await expect(tabs()).toHaveCount(3);
      await expect(current()).toHaveText("b.md");
      checks.push(`${runtime}: single/double/ctrl/middle/dedupe/reuse`);
      await page.locator(".preview-tab.active .preview-tab-close").click();
      await expect(current()).toHaveText("d.txt");
      checks.push(`${runtime}: MRU close`);
      await page.locator(`.session-main[data-session-id="${b.id}"]`).click();
      await expect(tabs()).toHaveCount(0);
      await expect(page.locator("#filePreview")).not.toContainText("DELTA");
      await file("a.txt").click();
      await expect(tabs()).toHaveCount(1);
      await page.waitForTimeout(310);
      await page.locator(`.session-main[data-session-id="${a.id}"]`).click();
      await expect(tabs()).toHaveCount(2);
      await expect(current()).toHaveText("d.txt");
      checks.push(`${runtime}: same-project session isolation/restore`);
      transitions.push({runtime,stage:"before-reload",events:await page.evaluate(() => window.__previewTransitions)});
      await page.reload();
      await expect(tabs()).toHaveCount(2);
      await expect(current()).toHaveText("d.txt");
      await expect(page.locator("#filePreview")).toContainText("DELTA"); // Reload clears the body cache; both targets must be visited before the cache case.
      checks.push(`${runtime}: refresh restore`);
      await tabs().filter({hasText:"c.csv"}).click();
      await expect(page.locator("#filePreview")).toContainText("Charlie");
      let releaseCacheGate;
      const cacheGate = new Promise(resolve => {releaseCacheGate=resolve;});
      routingState.previewGate=async url=>{
        if(url.searchParams.get("raw")!=="1" && /[\\/](d\.txt|c\.csv)$/.test(url.searchParams.get("path")||""))await cacheGate;
      };
      try {
        for(const name of ["d.txt","c.csv","d.txt","c.csv","d.txt"]) {
          const immediate=await page.evaluate(name=>{
            [...document.querySelectorAll("#previewTabs [role=tab]")].find(tab=>tab.textContent===name).click();
            return document.querySelector("#filePreview").textContent;
          },name);
          assert(immediate.includes(name==="d.txt"?"DELTA":"Charlie"), `cache must paint ${name} synchronously: ${immediate}`);
          assert(!immediate.includes("No file open"));
        }
        await page.screenshot({path:path.join(evidence,`${runtime}-cached-switch.png`)});
      } finally {routingState.previewGate=null;releaseCacheGate();await Promise.all([...pendingRoutes]);}
      assert.deepEqual(routeErrors,[]);
      checks.push(`${runtime}: repeated cached switch with delayed validation`);
      let releaseMedia;
      const mediaGate=new Promise(resolve=>releaseMedia=resolve);let rawRequests=0;
      routingState.previewGate=async url=>{
        if(url.searchParams.get("raw")==="1" && (url.searchParams.get("path")||"").endsWith("parallel-visual-a.png")){rawRequests++;await mediaGate;}
      };
      try {
        await file("parallel-visual-a.png").click({ modifiers: ["Control"] });
        await page.locator("#filePreview img").waitFor({state:"attached"});
        await expect(page.locator("#previewStatus")).toContainText("Loading preview");
        await page.waitForTimeout(3200); // A real refresh interval elapses while raw bytes remain held.
        assert.equal(rawRequests,1);
        assert.equal(await page.locator("#filePreview img").evaluate(image=>image.naturalWidth),0);
        await page.screenshot({path:path.join(evidence,`${runtime}-media-loading.png`)});
      }finally{routingState.previewGate=null;releaseMedia();await Promise.all([...pendingRoutes]);}
      assert.deepEqual(routeErrors,[]);
      await expect.poll(()=>page.locator("#filePreview img").evaluate(image=>image.complete&&image.naturalWidth>0)).toBe(true);
      await expect(page.locator("#previewStatus")).not.toContainText("Loading preview");
      checks.push(`${runtime}: media loading survives metadata refresh without duplicate raw requests`);
      assert.match(await page.locator("#filePreview img").getAttribute("src"), /api\/preview\/file/);
      checks.push(`${runtime}: bound raw image`);
      await file("sample.pdf").click({ modifiers: ["Control"] });
      await expect(page.locator("#filePreview iframe")).toBeVisible();
      assert.match(await page.locator("#filePreview iframe").getAttribute("src"), /api\/preview\/file/);
      await file("sample.bin").click({ modifiers: ["Control"] });
      await expect(page.locator("#filePreview")).toContainText("Binary");
      await file("c.csv").click();
      await expect(page.locator("#filePreview table")).toBeVisible();
      await page.locator("#previewModeActions button").filter({hasText:"Source"}).click();
      await expect(page.locator("#filePreview")).toHaveClass(/code-preview/);
      await file("d.txt").click();
      await file("c.csv").click();
      await expect(page.locator("#filePreview")).toHaveClass(/code-preview/);
      checks.push(`${runtime}: PDF/binary/table mode restoration`);
      await file("long-same-filename-for-narrow-preview-tab-01.txt").click({ modifiers: ["Control"] });
      for (const [width, language, dark] of [[1280, "en", false], [1280, "zh", true], [390, "en", true], [390, "zh", false]]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(({ language, dark }) => {
          document.querySelector(`.theme-opt[data-theme="${dark ? "dark" : "light"}"]`)?.click();
          document.querySelector(`[data-settings-lang="${language}"]`)?.click();
        }, { language, dark });
        await expect(page.locator("#previewTabs [aria-selected=true]")).toHaveText("long-same-filename-for-narrow-preview-tab-01.txt");
        // Resize/redraw preserves manual strip position; explicit activation reveals the tab.
        await page.locator("#previewTabs [aria-selected=true]").click();
        await page.screenshot({ path: path.join(evidence, `${runtime}-${width}-${language}-${dark ? "dark" : "light"}.png`) });
        const layout = await page.evaluate(() => {
          const bar = document.querySelector("#previewTabs").getBoundingClientRect();
          const active = document.querySelector(".preview-tab.active").getBoundingClientRect();
          const close = document.querySelector(".preview-tab.active .preview-tab-close").getBoundingClientRect();
          return {activeVisible:active.left>=bar.left-1 && active.right<=bar.right+1,
            closeVisible:close.left>=0 && close.right<=innerWidth && close.width>0};
        });
        assert.deepEqual(layout, {activeVisible:true,closeVisible:true});
      }
      await page.setViewportSize({ width: 1280, height: 900 });
      await current().focus();
      await current().press("Home");
      await expect(current()).toHaveText("d.txt");
      checks.push(`${runtime}: keyboard and four visual variants`);
      for(const action of ["close","navigate"]) {
        if(action==="navigate") await page.locator("#togglePreview").click();
        const rect=await page.locator("#previewResizer").boundingBox();
        assert(rect);
        await page.mouse.move(rect.x+rect.width/2,rect.y+100);await page.mouse.down();
        await page.evaluate(()=>{
          window.__originalPreviewRaf=requestAnimationFrame;
          window.__originalPreviewCancel=cancelAnimationFrame;
          window.__pendingPreviewRaf=[];
          window.requestAnimationFrame=cb=>{window.__pendingPreviewRaf.push(cb);return window.__pendingPreviewRaf.length;};
          window.cancelAnimationFrame=()=>{};
        });
        try {
          await page.mouse.move(rect.x-25,rect.y+100);
          const released=await page.evaluate(({action,target})=>{
            const resizer=document.querySelector("#previewResizer"),width=document.documentElement.style.getPropertyValue("--preview-width");
            const owned=resizer.hasPointerCapture(1);
            if(action==="close")document.querySelector("#togglePreview").click();
            else document.querySelector(`.session-main[data-session-id="${target}"]`).click();
            window.__pendingPreviewRaf.forEach(cb=>cb());
            return {owned,released:!resizer.hasPointerCapture(1),classCleared:!document.body.classList.contains("resizing-preview"),
              stylesCleared:!document.documentElement.style.getPropertyValue("--drag-preview-content-width")&&!document.documentElement.style.getPropertyValue("--drag-message-list-width"),
              widthStable:document.documentElement.style.getPropertyValue("--preview-width")===width};
          },{action,target:b.id});
          assert.deepEqual(released,{owned:true,released:true,classCleared:true,stylesCleared:true,widthStable:true});
        } finally {
          await page.evaluate(()=>{window.requestAnimationFrame=window.__originalPreviewRaf;window.cancelAnimationFrame=window.__originalPreviewCancel;});
          await page.mouse.up();
        }
        checks.push(`${runtime}: native pointer and held RAF released on ${action}`);
      }
      transitions.push({runtime,events:await page.evaluate(() => window.__previewTransitions)});
      routingState.closing=true;
      await context.close(); context = null;
    }
    stateContract = await require("./code042-preview-state-cases.cjs")(browser, host.ready.codeUrl);
    reviewContract = await require("./code042-preview-review-cases.cjs")(browser, host.ready.codeUrl);
    assert.deepEqual(errors, []);
    assert.deepEqual(routeErrors,[]);
  } catch (error) {
    if (activePage && !activePage.isClosed()) {
      await activePage.screenshot({ path: path.join(evidence, "failure.png") });
      await fs.writeFile(path.join(evidence, "events.json"), JSON.stringify(await activePage.evaluate(() => window.__previewEvents)));
    }
    throw error;
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    cleanup = await host.stop();
    await fs.writeFile(path.join(evidence, "result.json"), JSON.stringify({ checks, stateContract, reviewContract, errors, routeErrors, routeRequests, network, transitions, cleanup }, null, 2));
    assert.deepEqual(routeErrors,[]);
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
  }
  console.log(JSON.stringify({ ok: true, checks, evidence }));
}
main().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
