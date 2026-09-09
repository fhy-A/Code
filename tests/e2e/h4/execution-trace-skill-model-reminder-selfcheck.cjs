const assert = require("node:assert/strict");
const fs = require("node:fs/promises"), os = require("node:os"), path = require("node:path");
const { chromium, expect } = require("@playwright/test");
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

function createAudit() {
  return { initiated: [], fulfilled: [], serverBound: [], blockedWrites: [], blockedExternal: [] };
}

async function installNetworkFence(context, runtime, audit) {
  context.on("request", (request) => {
    const url = new URL(request.url());
    audit.initiated.push({ runtime, method: request.method(), path: url.pathname, hostname: url.hostname });
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const fixture = method === "POST" ? STARTUP_FIXTURES[url.pathname] : null;
    if (fixture) {
      audit.fulfilled.push({ runtime, method, path: url.pathname });
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) });
      return;
    }
    const local = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
    if (!local) {
      audit.blockedExternal.push({ runtime, method, path: url.pathname, hostname: url.hostname });
      await route.abort("blockedbyclient");
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      audit.blockedWrites.push({ runtime, method, path: url.pathname });
      await route.abort("blockedbyclient");
      return;
    }
    audit.serverBound.push({ runtime, method, path: url.pathname });
    await route.continue();
  });
}

async function createContext(browser, host, runtime, audit, view = {}) {
  const context = await browser.newContext({
    viewport: { width: view.width || 1280, height: 800 },
    hasTouch: Boolean(view.touch),
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  await installNetworkFence(context, runtime, audit);
  await context.addInitScript(({ platformToken, language, theme }) => {
    class OfflineRenderer {}
    window.marked = {
      Renderer: OfflineRenderer,
      setOptions() {},
      parse(value) { return String(value ?? ""); },
    };
    localStorage.setItem("code-key-config", "[]");
    localStorage.setItem("code-platform-auth", JSON.stringify({
      token: platformToken,
      userId: "53",
      username: "skill-model-reminder-selfcheck",
    }));
    localStorage.setItem("code-permission-profile", "read");
    localStorage.setItem("code-lang", language);
    localStorage.setItem("code-theme-mode", theme);
    localStorage.setItem("code-sidebar-hidden", "1");
    localStorage.removeItem("code-model");
    localStorage.removeItem("code-model-route-ref");
  }, {
    platformToken: host.platformToken,
    language: view.language || (runtime === "bundle" ? "zh" : "en"),
    theme: view.theme || (runtime === "bundle" ? "dark" : "light"),
  });
  if (view.language) await context.addInitScript(() => {
    window.Code = {core: {}, features: {}, services: {}, agent: {}, ui: {}};
    let messagesApi;
    Object.defineProperty(Code.ui, 'messages', {configurable: true, get: () => messagesApi, set(api) {
      messagesApi = {...api, createMessagesFeature(options) {
        window.__toolNameOptions = options;
        const feature = api.createMessagesFeature(options);
        window.__toolNameFeature = feature;
        return feature;
      }, createMessageScrollController(options) {
        const controller=api.createMessageScrollController(options);window.__messageScroller=controller;return controller;
      }};
    }});
    let stateApi;
    Object.defineProperty(Code.core,'state',{configurable:true,get:()=>stateApi,set(api){
      stateApi={...api,createAppState(...args){const state=api.createAppState(...args);window.__traceAppState=state;return state;}};
    }});
    let timelineApi;
    Object.defineProperty(Code.ui,'timeline',{configurable:true,get:()=>timelineApi,set(api){
      timelineApi={...api,createTimelineFeature(options){const feature=api.createTimelineFeature(options);window.__timelineFeature=feature;return feature;}};
    }});
    let i18nApi;
    Object.defineProperty(Code.core, 'i18n', {configurable: true, get: () => i18nApi, set(api) {
      i18nApi = {...api, createI18nRuntime(options) {
        const result = api.createI18nRuntime(options); window.__toolNameLanguage = result.setLang; return result;
      }};
    }});
  });
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

async function installTraceProjection(page, runtime) {
  return page.evaluate((runtimeName) => {
    const createMessagesFeature = window.Code?.ui?.messages?.createMessagesFeature;
    if (typeof createMessagesFeature !== "function") throw new Error("messages feature unavailable");
    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
    const names = runtimeName === "bundle" ? ["imagegen"] : ["documents", "pdf"];
    let messages = [
      { role: "user", content: "trace fixture", meta: { activeSkillNames: names } },
      { role: "assistant", content: "inspect", meta: { toolCalls: [{ id: "call-1", function: { name: "read_file", arguments: "{}" } }] } },
      { role: "tool-call", content: "", meta: { action: "read_file", toolCallId: "call-1" } },
      { role: "tool-result", content: "ok", meta: { action: "read_file", toolCallId: "call-1", outcome: "completed", result: { ok: true } } },
      { role: "assistant", content: "done", _responseTime: "2s" },
    ];
    const feature = createMessagesFeature({
      escapeHtml,
      formatCompact: (value) => String(value),
      renderMarkdown: (value) => `<p>${escapeHtml(value)}</p>`,
      t: (key, vars = {}) => key === "executionTraceSkillsAria"
        ? `${runtimeName === "bundle" ? "已启用 Skill" : "Enabled Skills"}: ${vars.names}`
        : key,
      getMessageText: (message) => String(message?.content || ""),
      getBackgroundJob: () => null,
      getMessages: () => messages,
      getSessionId: () => "h4-skill-trace",
      getSelectedModel: () => "fixture-model",
      renderNetworkRecoveryStatus: () => "",
      renderAssistantContent: (value) => `<p>${escapeHtml(value)}</p>`,
      renderBranchFlow: () => "",
      isEditSuggestionMessage: () => false,
      renderEditSuggestion: () => "",
      getToolActionLabel: (action) => action,
    });
    document.querySelector(".chat-pane")?.classList.remove("empty-chat");
    document.getElementById("messageList").innerHTML = feature.projectMessages(messages, { hasActiveRun: false });
    return { names };
  }, runtime);
}

async function exerciseRuntime(browser, host, runtime, audit) {
  const context = await createContext(browser, host, runtime, audit);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  try {
    const target = runtime === "classic"
      ? new URL("/dist/frontend/index.classic.html", host.ready.codeUrl).href
      : new URL("/", host.ready.codeUrl).href;
    await page.goto(target, { waitUntil: "domcontentloaded" });
    await waitForRuntime(page, runtime);

    const prompt = page.locator("#prompt");
    const sessionCountBefore = await page.locator("#sessionList .session-row").count();
    await prompt.fill("draft must remain");
    const sendButton = page.locator("#sendBtn");
    assert.equal(await sendButton.isEnabled(), true);
    await sendButton.click();
    const expectedReminder = runtime === "bundle"
      ? "未找到可用模型，请检查 API Key"
      : "No available models found. Check your API Key.";
    const toast = page.locator("#toastContainer .toast.warning").filter({ hasText: expectedReminder });
    await toast.waitFor({ state: "visible" });
    assert.equal(await prompt.inputValue(), "draft must remain");
    assert.equal(await page.locator("#sessionList .session-row").count(), sessionCountBefore);

    const projection = await installTraceProjection(page, runtime);
    const summary = page.locator(".execution-trace-summary");
    const chip = page.locator(".execution-trace-skill-chip");
    assert.equal(await chip.count(), 0);
    assert.equal(await page.locator('[data-current-action="use_skill"]').count(), 0);
    const geometry = await page.evaluate(() => {
      const rect = (selector) => {
        const box = document.querySelector(selector).getBoundingClientRect();
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height };
      };
      const status = rect(".completed-run-status");
      const chevron = rect(".execution-trace-chevron");
      return {
        status,
        chevron,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        viewportWidth: innerWidth,
      };
    });
    assert.equal(geometry.status.right <= geometry.chevron.left + 1, true);
    assert.equal(geometry.documentWidth <= geometry.viewportWidth, true);
    assert.equal(geometry.bodyWidth <= geometry.viewportWidth, true);

    await summary.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(".execution-trace").evaluate((element) => element.classList.contains("is-expanded")), true);
    assert.equal(await summary.getAttribute("aria-expanded"), "true");
    await page.keyboard.press("Space");
    assert.equal(await page.locator(".execution-trace").evaluate((element) => element.classList.contains("is-expanded")), false);
    assert.equal(await summary.getAttribute("aria-expanded"), "false");
    assert.deepEqual(pageErrors, []);
    return { runtime, expectedReminder, draftPreserved: true, projection, geometry, keyboardFold: true };
  } finally {
    await page.close();
    await context.close();
  }
}

async function exerciseToolNames(browser, host, evidenceDir, representativeOnly = false) {
  const audit = createAudit(), cases = [];
  for (const runtime of ['bundle', 'classic']) for (const language of ['zh', 'en'])
  for (const theme of ['light', 'dark']) for (const width of [1280, 390]) {
    const representative = (runtime === 'bundle' && language === 'zh' && theme === 'light') || (runtime === 'classic' && language === 'en' && theme === 'dark');
    if (representativeOnly && !representative) continue;
    const context = await createContext(browser, host, runtime, audit, {language, theme, width});
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    try {
      await page.goto(new URL(runtime === 'bundle' ? '/' : '/dist/frontend/index.classic.html', host.ready.codeUrl).href);
      await waitForRuntime(page, runtime); await page.waitForLoadState('networkidle');
      const originals = await page.evaluate(() => {
        const options = window.__toolNameOptions;
        if (!options?.getToolActionLabel) throw new Error('real tool labels unavailable');
        const feature = Code.ui.messages.createMessagesFeature({...options, getSessionId: () => 'tool-name-fixture'});
        const definitions = [
          ['single', ['read_file'], 'succeeded'],
          ['repeat', ['read_file', 'read_file'], 'completed'],
          ['mixed', ['read_file', 'search_files', 'web_fetch'], 'succeeded'],
          ['skills', ['use_skill', 'read_skill_resource', 'check_skill_dependencies'], 'succeeded'],
          ['failed', ['propose_edit', 'write_file'], 'failed'],
          ['running', ['read_file', 'run_command'], 'running'],
          ['unknown', ['legacy_scan', 'constructor', ''], 'completed'],
          ['image-read', ['read_file'], 'succeeded'],
          ['cancelled', ['web_fetch', 'web_fetch'], 'cancelled'],
        ];
        const groups = definitions.map(([name, actions, outcome], groupIndex) => ({name, actions, outcome,
          items: actions.flatMap((action, index) => {
            const id = `${groupIndex}-${index}`, args = action === 'web_fetch' ? {url: 'https://example.test/page'}
              : action === 'run_command' ? {command: 'view_image picture.png; search_web example'}
              : action === 'use_skill' || action === 'read_skill_resource' || action === 'check_skill_dependencies' ? {skill: 'documents', name: 'documents'}
              : {path: name === 'image-read' ? 'picture.png' : 'README.md'};
            const call = {msg: {role: 'tool-call', meta: {action, toolCallId: id, tool: {action, ...args}}}, index: index * 2};
            if (outcome === 'running' && index === actions.length - 1) return [call];
            return [call, {msg: {role: 'tool-result', content: outcome === 'failed' ? 'synthetic failure' : 'synthetic result', meta: {action, toolCallId: id, outcome: outcome === 'running' ? 'succeeded' : outcome}}, index: index * 2 + 1}];
          }),
        }));
        groups.push({name: 'legacy-result', actions: ['web_fetch'], outcome: 'completed', items: [{msg: {role: 'tool-result', content: 'old result', meta: {action: 'web_fetch'}}, index: 0}]});
        const frozen = JSON.stringify(groups);
        window.__renderToolNames = () => {
          document.querySelector('.chat-pane').classList.remove('empty-chat');
          document.getElementById('messageList').innerHTML = groups.map((group, index) => feature.renderToolProcessProjection(group.items, index)).join('');
          if (JSON.stringify(groups) !== frozen) throw new Error('synthetic history mutated');
          return groups.map(group => ({name: group.name, labels: group.actions.map(options.getToolActionLabel)}));
        };
        return window.__renderToolNames();
      });
      const stages = page.locator('.tool-process-stage'); await expect(stages).toHaveCount(10);
      const headings = await stages.locator(':scope > summary strong').allTextContents();
      assert.equal(headings[0], language === 'zh' ? '读取文件' : 'Read File');
      assert.equal(headings[1], `${headings[0]} ×2`);
      assert.equal(headings[2], language === 'zh' ? '读取文件 · 搜索文件 · 抓取网页' : 'Read File · Search Files · Web Fetch');
      assert.equal(headings[3], language === 'zh' ? '加载 Skill · 读取 Skill 资源 · 检查 Skill 依赖' : 'Load Skill · Read Skill Resource · Check Skill Dependencies');
      assert.equal(headings[5], language === 'zh' ? '执行命令' : 'Run Command');
      assert.equal(headings[6], `legacy_scan · constructor · ${language === 'zh' ? '工具过程' : 'Tool activity'}`);
      assert.equal(headings[7], headings[0]);
      assert.equal(headings[8], language === 'zh' ? '抓取网页 ×2' : 'Web Fetch ×2');
      assert.equal(headings[9], language === 'zh' ? '抓取网页' : 'Web Fetch');
      await expect(stages.nth(4)).toHaveClass(/failed/); await expect(stages.nth(5)).toHaveClass(/running/);
      for (let index = 0; index < originals.length; index++) {
        assert.deepEqual(await stages.nth(index).locator('.tool-process-row-heading strong').allTextContents(), originals[index].labels);
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const prefix = `${runtime}-${language}-${theme}-${width}`;
      async function scrollHistoryToTop() {
        const area = page.locator('#messages'), box = await area.boundingBox();
        await page.mouse.move(box.x + box.width - 16, box.y + 16);
        await page.mouse.wheel(0, -10000);
        await expect.poll(() => area.evaluate(el => el.scrollTop)).toBe(0);
      }
      if (representative) {
        await scrollHistoryToTop();
        await page.screenshot({path: path.join(evidenceDir, `${prefix}-names.png`)});
      }
      const mixed = stages.nth(2), mixedSummary = mixed.locator(':scope > summary');
      await mixedSummary.focus(); await page.keyboard.press('Enter'); await expect(mixed).toHaveAttribute('open', '');
      const item = mixed.locator('.tool-process-item').nth(1);
      await item.locator(':scope > summary').click(); await expect(item).toHaveAttribute('open', '');
      await expect(item.locator('.tool-process-body')).toContainText('README.md');
      if (representative) {
        await scrollHistoryToTop();
        await expect(mixedSummary).toBeInViewport({ratio: 1});
        await page.screenshot({path: path.join(evidenceDir, `${prefix}-mixed-expanded.png`)});
      }
      await mixedSummary.focus(); await page.keyboard.press('Space'); await expect(mixed).not.toHaveAttribute('open', '');
      await page.evaluate(next => { window.__toolNameLanguage(next); window.__renderToolNames(); }, language === 'zh' ? 'en' : 'zh');
      await expect(stages.nth(2).locator(':scope > summary strong')).toHaveText(language === 'zh' ? 'Read File · Search Files · Web Fetch' : '读取文件 · 搜索文件 · 抓取网页');
      await page.evaluate(next => { window.__toolNameLanguage(next); window.__renderToolNames(); }, language);
      await expect(stages.nth(2).locator(':scope > summary strong')).toHaveText(headings[2]);
      assert.deepEqual(errors, []);
      cases.push({runtime, language, theme, width, headings, groups: 10, keyboardFold: true, detailClick: true, languageSwitch: true});
    } finally { await context.close(); }
  }
  assert.deepEqual(audit.blockedWrites, []);
  return {cases, blockedWrites: audit.blockedWrites};
}

function fixturePng(width, height) {
  const zlib = require('node:zlib');
  function chunk(type, bytes) {
    const name = Buffer.from(type), input = Buffer.concat([name, bytes]);let crc = 0xffffffff;
    for (const byte of input) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); }
    const size = Buffer.alloc(4), checksum = Buffer.alloc(4);size.writeUInt32BE(bytes.length);checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
    return Buffer.concat([size,input,checksum]);
  }
  const header = Buffer.alloc(13);header.writeUInt32BE(width);header.writeUInt32BE(height,4);header[8]=8;header[9]=2;
  const pixels = Buffer.alloc(height*(width*3+1));
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){const offset=y*(width*3+1)+1+x*3;pixels[offset]=Math.round(x/width*200);pixels[offset+1]=120;pixels[offset+2]=Math.round(y/height*220);}
  return Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',header),chunk('IDAT',zlib.deflateSync(pixels)),chunk('IEND',Buffer.alloc(0))]).toString('base64');
}

async function exerciseImageReads(browser, host, evidenceDir) {
  const audit=createAudit(), cases=[], landscape=fixturePng(160,80), portrait=fixturePng(80,160);
  for(const runtime of ['bundle','classic'])for(const language of ['zh','en'])for(const theme of ['light','dark'])for(const width of [1280,390]){
    const context=await createContext(browser,host,runtime,audit,{language,theme,width}),page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    try{
      const url=new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href;
      async function install(){
        return page.evaluate(({landscape,portrait})=>{
          const feature=window.__toolNameFeature;if(!feature)throw new Error('real bound message feature missing');
          const visual={ok:true,action:'read_file',binary:true,visual:true,mime:'image/png',base64:landscape,path:'same.png',size:512};
          const result=(id,action,value,outcome='succeeded')=>[
            {role:'tool-call',meta:{action,toolCallId:id,tool:action==='run_command'?{action,command:'echo fixture'}:{action,path:value.path||'notes.txt'}}},
            {role:'tool-result',content:'snapshot result',meta:{action,toolCallId:id,result:value,outcome}},
          ];
          const initial=[{role:'user',content:'Image history fixture'},
            ...result('command-before','run_command',{ok:true,content:'before'}),
            ...result('image-a','read_file',visual),
            ...result('command-between','run_command',{ok:true,content:'between'}),
            ...result('image-b','read_file',visual),
            ...result('text-between','read_file',{ok:true,path:'notes.txt',content:'text'}),
            ...result('image-c','read_file',{...visual,path:'portrait.png',base64:portrait}),
            ...result('image-missing','read_file',{...visual,base64:undefined}),
            ...result('image-svg','read_file',{...visual,mime:'image/svg+xml',base64:undefined,svgText:'<svg onload="window.__unsafeSvg=1"><image href="https://image-fixture.invalid/private"/></svg>'}),
            ...result('image-corrupt','read_file',{...visual,base64:btoa('\x89PNG\r\n\x1a\nnot an image')}),
            ...result('image-failed','read_file',{...visual,ok:false,error:'synthetic read failure'},'failed'),
            {role:'assistant',content:'Separate original tool stage.'},
            ...result('image-second-stage','read_file',{...visual,path:'second.png'}),
            {role:'assistant',content:'Fixture complete.',_responseTime:'1s'},
          ];
          const stored=localStorage.getItem('code079-read-image-fixture'),history=stored?JSON.parse(stored):initial;
          localStorage.setItem('code079-read-image-fixture',JSON.stringify(history));
          const snapshot=JSON.stringify(history);
          window.__renderImageReads=()=>{
            const target=document.getElementById('messageList'),projected=document.createElement('div');
            document.querySelector('.chat-pane').classList.remove('empty-chat');
            projected.innerHTML=feature.projectMessages(history,{hasActiveRun:false,expandedExecutionTraces:new Set(['0'])});
            feature.reconcileToolProcessNodes(target,projected);target.replaceChildren(...projected.childNodes);
            if(JSON.stringify(history)!==snapshot)throw new Error('history changed');
          };
          window.__renderImageSequence=sequence=>{
            const items=[...sequence].flatMap((kind,index)=>result(`${kind}-${index}`,kind==='I'?'read_file':'run_command',kind==='I'?{...visual,base64:index?portrait:landscape}:{ok:true,content:'fixture'})).map((msg,index)=>({msg,index}));
            document.getElementById('messageList').innerHTML=feature.renderToolProcessProjection(items,0);
          };
          window.__renderImageReads();return {restored:!!stored,snapshot};
        },{landscape,portrait});
      }
      await page.goto(url);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
      const installed=await install(),groups=page.locator('.tool-image-stage'),first=groups.first();
      const initialArea=page.locator('#messages'),initialBox=await initialArea.boundingBox();
      await page.mouse.move(initialBox.x+initialBox.width-16,initialBox.y+16);await page.mouse.wheel(0,-10000);
      await expect.poll(()=>initialArea.evaluate(el=>el.scrollTop)).toBe(0);
      await expect(groups).toHaveCount(2);
      await expect(first.locator(':scope > summary strong')).toHaveText(language==='zh'?'已查看 6 张图像':'Viewed 6 images');
      await expect(first).toHaveAttribute('open','');
      await expect(first.locator('.tool-image-preview')).toHaveCount(6);
      const preview=first.locator('[data-tool-image-preview]').first(),image=preview.locator('img');
      await expect.poll(()=>image.evaluate(el=>el.naturalWidth)).toBe(160);
      await expect(first.locator('[data-tool-image-preview]:disabled')).toHaveCount(3);
      const ids=await page.locator('.tool-process-item').evaluateAll(items=>items.map(el=>el.dataset.toolCallId));
      assert.equal(ids.length,11);assert.equal(new Set(ids).size,11);
      assert(ids.indexOf('command-before')<ids.indexOf('image-a'));
      assert(ids.indexOf('command-between')<ids.indexOf('text-between'));
      assert(ids.indexOf('text-between')<ids.indexOf('image-failed'));
      const imageIds=await first.locator('.tool-process-item').evaluateAll(items=>items.map(el=>el.dataset.toolCallId));
      assert.deepEqual(imageIds,['image-a','image-b','image-c','image-missing','image-svg','image-corrupt']);
      const sources=await first.locator('img[data-tool-image]').evaluateAll(items=>items.map(el=>el.src));
      assert.equal(sources[0],sources[1]);assert.notEqual(sources[1],sources[2]);
      assert(sources.every(source=>source.startsWith('data:image/png;base64,')));
      assert.equal(await page.evaluate(()=>window.__unsafeSvg),undefined);
      await expect(image).toHaveCSS('object-fit','contain');
      const imageBoxes=await first.locator('img[data-tool-image]').evaluateAll(items=>items.filter(el=>el.naturalWidth>0).map(el=>{const r=el.getBoundingClientRect();return{width:r.width,height:r.height,naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight,fit:getComputedStyle(el).objectFit};}));
      assert.equal(imageBoxes.length,3);assert(imageBoxes.every(r=>r.width<=112&&r.height<=112&&r.fit==='contain'));
      assert.equal(imageBoxes[2].naturalWidth,80);assert.equal(imageBoxes[2].naturalHeight,160);
      const boxes=await first.locator('.tool-image-preview').evaluateAll(items=>items.map(el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}}));
      assert(boxes.every(r=>r.width===112&&r.height===112));if(width===390)assert(boxes[2].y>boxes[0].y);
      const summary=first.locator(':scope > summary');
      const ordinary=page.locator('.tool-process-stage:not(.tool-image-stage)').first();
      assert(await first.evaluate(el=>{
        const article=el.closest('article.tool-process'),ordinary=document.querySelector('.tool-process-stage:not(.tool-image-stage)')?.closest('article.tool-process');
        return article.parentElement===ordinary.parentElement&&!ordinary.contains(article);
      }));
      assert.deepEqual(await page.locator('.tool-process-stage:not(.tool-image-stage) .tool-process-item').evaluateAll(items=>items.map(el=>el.dataset.toolCallId)),['command-before','command-between','text-between','image-failed']);
      await ordinary.locator(':scope > summary').focus();await page.keyboard.press('Enter');await expect(ordinary).toHaveAttribute('open','');
      await expect(first.locator('.tool-image-grid')).toBeVisible();
      await page.keyboard.press('Enter');await expect(ordinary).not.toHaveAttribute('open','');await expect(first.locator('.tool-image-grid')).toBeVisible();
      await summary.focus();await page.keyboard.press('Enter');await expect(first).not.toHaveAttribute('open','');
      await expect(ordinary).not.toHaveAttribute('open','');
      await page.evaluate(()=>window.__renderImageReads());await expect(first).not.toHaveAttribute('open','');
      await summary.focus();await page.keyboard.press('Space');await expect(first).toHaveAttribute('open','');
      await expect.poll(()=>image.evaluate(el=>el.naturalWidth)).toBe(160);
      await preview.focus();await page.keyboard.press('Enter');
      await expect(page.locator('#imageOverlay img')).toHaveAttribute('src',sources[0]);
      await page.keyboard.press('Escape');await expect(page.locator('#imageOverlay')).toHaveCount(0);
      const metadata=first.locator('.tool-image-tools');await metadata.locator(':scope > summary').click();
      await first.locator('.tool-process-item').first().locator(':scope > summary').click();
      await expect(first.locator('.tool-process-item').first().locator('.tool-process-body')).toContainText('read_file');
      await expect(first.locator('.tool-process-item').first().locator('.tool-process-body')).toContainText('same.png');
      await metadata.locator(':scope > summary').click();
      const area=page.locator('#messages'),areaBox=await area.boundingBox();
      await page.mouse.move(areaBox.x+areaBox.width-16,areaBox.y+16);await page.mouse.wheel(0,-10000);
      await expect.poll(()=>area.evaluate(el=>el.scrollTop)).toBe(0);
      const scrollBefore=await area.evaluate(el=>el.scrollTop);
      await image.evaluate(el=>new Promise(resolve=>{const source=el.src;el.removeAttribute('src');el.addEventListener('load',()=>requestAnimationFrame(resolve),{once:true});requestAnimationFrame(()=>{el.src=source;});}));
      assert.equal(await area.evaluate(el=>el.scrollTop),scrollBefore);
      const representative=(runtime==='bundle'&&language==='zh'&&theme==='light')||(runtime==='classic'&&language==='en'&&theme==='dark');
      if(representative)await page.screenshot({path:path.join(evidenceDir,`${runtime}-${language}-${theme}-${width}-image-reads.png`)});
      await page.evaluate(next=>{window.__toolNameLanguage(next);window.__renderImageReads();},language==='zh'?'en':'zh');
      await expect(first.locator(':scope > summary strong')).toHaveText(language==='zh'?'Viewed 6 images':'已查看 6 张图像');
      await page.evaluate(next=>{window.__toolNameLanguage(next);window.__renderImageReads();},language);
      await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
      const restored=await install();assert(restored.restored);assert.equal(restored.snapshot,installed.snapshot);
      await expect(groups).toHaveCount(2);await expect(first.locator('.tool-image-preview')).toHaveCount(6);
      for(const [sequence,expected] of [['IT',[true,false]],['TI',[false,true]],['ITI',[true,false]],['TIT',[false,true]],['II',[true]],['TT',[false]]]){
        await page.evaluate(sequence=>window.__renderImageSequence(sequence),sequence);
        assert.deepEqual(await page.locator('.tool-process-stage').evaluateAll(items=>items.map(el=>el.classList.contains('tool-image-stage'))),expected);
        assert.equal(await page.locator('.tool-process-item').count(),sequence.length);
        if(representative&&['ITI','TIT'].includes(sequence)){
          const box=await area.boundingBox();await page.mouse.move(box.x+box.width-16,box.y+16);await page.mouse.wheel(0,-10000);await expect.poll(()=>area.evaluate(el=>el.scrollTop)).toBe(0);
          await page.screenshot({path:path.join(evidenceDir,`${runtime}-${language}-${theme}-${width}-${sequence==='ITI'?'image-first':'tool-first'}.png`)});
        }
      }
      assert.deepEqual(errors,[]);cases.push({runtime,language,theme,width,groups:2,records:7,orderPatterns:6,duplicateReadKept:true,siblings:true,independentFolds:true,foldRetained:true,preview:true,details:true,delayedLoadStable:true,restored:true});
    }finally{await context.close();}
  }
  assert.deepEqual(audit.blockedWrites,[]);
  assert.equal(audit.initiated.filter(r=>r.path==='/api/file'||r.hostname==='image-fixture.invalid').length,0);
  return {cases,additionalFileReads:0,externalImageRequests:0};
}

async function exerciseTraceArrows(browser, host, evidenceDir) {
  const audit=createAudit(),cases=[],png=fixturePng(160,80);
  for(const runtime of ['bundle','classic'])for(const touch of [false,true]){
    const language=runtime==='bundle'?'zh':'en',theme=runtime==='bundle'?'light':'dark',width=touch?390:1280;
    const context=await createContext(browser,host,runtime,audit,{language,theme,width,touch}),page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    try{
      await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
      await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
      await page.evaluate(png=>{
        const feature=window.__toolNameFeature,records=[];
        for(const [index,action] of ['run_command','run_command','read_file'].entries()){
          records.push({role:'tool-call',meta:{action,toolCallId:String(index),tool:action==='read_file'?{action,path:'snapshot.png'}:{action,command:'echo fixture'}}});
          records.push({role:'tool-result',content:'fixture',meta:{action,toolCallId:String(index),outcome:'succeeded',result:action==='read_file'?{ok:true,binary:true,visual:true,mime:'image/png',base64:png,path:'snapshot.png'}:{ok:true}}});
        }
        document.querySelector('.chat-pane').classList.remove('empty-chat');
        document.getElementById('messageList').innerHTML=feature.renderToolProcessProjection(records.map((msg,index)=>({msg,index})),0);
      },png);
      assert.equal(await page.evaluate(()=>matchMedia('(hover: none)').matches),touch);
      const ordinary=page.locator('.tool-process-stage:not(.tool-image-stage)'),images=page.locator('.tool-image-stage');
      await expect(images).toHaveAttribute('open','');
      const states=[];
      async function neutral(){await page.locator('#prompt').click();await page.mouse.move(width-8,8);}
      for(const [kind,stage,other] of [['ordinary',ordinary,images],['images',images,ordinary]]){
        const summary=stage.locator(':scope > summary'),arrow=summary.locator('.tool-process-stage-chevron');
        async function capture(name){await arrow.evaluate(el=>Promise.all(el.getAnimations().map(animation=>animation.finished)));await page.screenshot({path:path.join(evidenceDir,name)});}
        if(await stage.getAttribute('open')!==null){await neutral();await expect(arrow).toHaveCSS('opacity','1');await summary.click();}
        await neutral();await expect(arrow).toHaveCSS('opacity',touch?'1':'0');
        const box=await summary.boundingBox(),arrowBox=await arrow.evaluate(el=>({width:el.offsetWidth,left:el.offsetLeft})),otherOpen=await other.getAttribute('open');
        await capture(`${runtime}-${touch?'touch':'mouse'}-${kind}-closed.png`);
        if(!touch){
          await summary.hover();await expect(arrow).toHaveCSS('opacity','1');
          assert.equal((await summary.boundingBox()).width,box.width);assert.deepEqual(await arrow.evaluate(el=>({width:el.offsetWidth,left:el.offsetLeft})),arrowBox);
          if(runtime==='bundle')await capture(`${runtime}-${kind}-hover.png`);
          await neutral();await expect(arrow).toHaveCSS('opacity','0');
        }
        await summary.focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');await expect(summary).toBeFocused();
        await expect(arrow).toHaveCSS('opacity','1');
        if(runtime==='bundle'&&!touch)await capture(`${runtime}-${kind}-focus.png`);
        if(touch)await summary.tap({position:{x:2,y:10}});else await summary.click({position:{x:2,y:10}});
        await expect(stage).toHaveAttribute('open','');await neutral();await expect(arrow).toHaveCSS('opacity','1');
        assert.equal(await other.getAttribute('open'),otherOpen);assert.equal((await summary.boundingBox()).width,box.width);
        for(const child of await stage.locator('.tool-process-chevron').all())await expect(child).toHaveCSS('opacity','1');
        await capture(`${runtime}-${touch?'touch':'mouse'}-${kind}-open.png`);
        await summary.focus();await page.keyboard.press('Enter');await expect(stage).not.toHaveAttribute('open','');
        await neutral();await expect(arrow).toHaveCSS('opacity',touch?'1':'0');assert.equal(await other.getAttribute('open'),otherOpen);
        states.push({kind,defaultHidden:!touch,hover:!touch,keyboardFocus:true,openVisible:true,reclosed:true,width:box.width,arrowWidth:arrowBox.width,independent:true,wholeRowClick:true});
      }
      assert.deepEqual(errors,[]);cases.push({runtime,language,theme,width,touch,states});
    }finally{await context.close();}
  }
  assert.deepEqual(audit.blockedWrites,[]);return {cases};
}

async function exerciseTimelineNavigation(browser,host,evidenceDir,expectBlocked=false){
  const audit=createAudit(),cases=[];
  for(const runtime of expectBlocked?['bundle']:['bundle','classic'])for(const running of expectBlocked?[false]:[false,true]){
    const context=await createContext(browser,host,runtime,audit,{language:runtime==='bundle'?'zh':'en',theme:runtime==='bundle'?'light':'dark',width:1280}),page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    try{
      await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
      await page.evaluate(running=>{
        const state=window.__traceAppState,scroller=window.__messageScroller,feature=window.__toolNameFeature,timeline=window.__timelineFeature;
        if(!state||!scroller||!feature||!timeline)throw new Error('actual application wiring unavailable');
        window.__timelineInstall=(session,active)=>{
          state.sessionId=session;state.messages=Array.from({length:6},(_,index)=>[
            {role:'user',content:`${session} message ${index}`},
            {role:'assistant',content:('Synthetic answer paragraph for stable scroll geometry. ').repeat(65),_responseTime:'1s'},
          ]).flat();
          document.querySelector('.chat-pane').classList.remove('empty-chat');
          scroller.setSession(session);scroller.setRunning(active,session);
          window.__timelineRedraw=()=>{
            document.getElementById('messageList').innerHTML=feature.projectMessages(state.messages,{hasActiveRun:active});
            timeline.renderTimeline();scroller.onContentChanged(state.sessionId);
          };
          window.__timelineRedraw();scroller.forceToLatest(session);
        };
        window.__timelinePosition=(index=0)=>{
          const area=document.getElementById('messages'),target=area.querySelector(`[data-msg-index="${index}"]`);
          return{scrollTop:area.scrollTop,scrollHeight:area.scrollHeight,clientHeight:area.clientHeight,targetTop:target?.getBoundingClientRect().top,containerTop:area.getBoundingClientRect().top,state:scroller.snapshot()};
        };
        window.__timelineInstall('timeline-fixture',running);window.__timelineClicks=0;window.__nativeJumps=[];
        document.getElementById('chatTimeline').addEventListener('click',()=>window.__timelineClicks++,true);
        const native=Element.prototype.scrollIntoView;
        Element.prototype.scrollIntoView=function(options){if(this.matches('.msg.user'))window.__nativeJumps.push({index:this.dataset.msgIndex,options});return native.call(this,options);};
      },running);
      const marker=page.locator('#chatTimeline .tl-marker[data-index="0"]');await expect(marker).toBeVisible();
      await expect.poll(()=>page.evaluate(()=>{const p=window.__timelinePosition();return p.scrollHeight-p.clientHeight-p.scrollTop;})).toBe(0);
      const before=await page.evaluate(()=>window.__timelinePosition());assert(before.scrollTop>500);
      await marker.click();
      const frames=await page.evaluate(async()=>{const frames=[];for(let index=0;index<45;index++){await new Promise(requestAnimationFrame);frames.push(window.__timelinePosition());}return frames;});
      const last=frames[frames.length-1],clicks=await page.evaluate(()=>window.__timelineClicks),nativeJumps=await page.evaluate(()=>window.__nativeJumps);
      assert.equal(clicks,1);
      if(expectBlocked){assert(Math.abs(last.scrollTop-before.scrollTop)<=2);assert(last.targetTop<last.containerTop-100);assert.equal(nativeJumps.length,1);assert(last.state.following);}
      else{assert(last.targetTop>=last.containerTop-2);assert(last.targetTop<last.containerTop+50);assert(!last.state.following);}
      const checks={};
      if(!expectBlocked){
        assert.equal(nativeJumps.length,0);
        await page.evaluate(()=>{window.__traceAppState.messages.at(-1).content+=' More streamed output.'.repeat(40);window.__timelineRedraw();});
        await expect.poll(()=>page.evaluate(()=>window.__timelinePosition().scrollTop)).toBe(last.scrollTop);
        await page.evaluate(png=>new Promise(resolve=>{
          const image=document.createElement('img');image.width=160;image.height=80;image.setAttribute('data-message-scroll-on-load','');
          document.querySelector('#messages [data-msg-index="0"]').appendChild(image);
          image.addEventListener('load',()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)),{once:true});
          requestAnimationFrame(()=>{image.src=`data:image/png;base64,${png}`;});
        }),fixturePng(160,80));
        assert.equal((await page.evaluate(()=>window.__timelinePosition())).scrollTop,last.scrollTop);checks.redrawAndImageLoad=true;
        async function latest(){await page.locator('#scrollToBottomBtn').click();await expect.poll(()=>page.evaluate(()=>{const p=window.__timelinePosition();return p.scrollHeight-p.clientHeight-p.scrollTop;})).toBe(0);assert(await page.evaluate(()=>window.__messageScroller.snapshot().following));}
        await latest();
        for(const [index,key] of [[2,'Enter'],[4,'Space']]){
          const node=page.locator(`#chatTimeline .tl-marker[data-index="${index}"]`);await node.focus();await page.keyboard.press(key);
          await expect.poll(()=>page.evaluate(index=>{const p=window.__timelinePosition(index);return Math.abs(p.targetTop-p.containerTop);},index)).toBeLessThanOrEqual(2);
          assert.equal(await page.evaluate(()=>window.__messageScroller.snapshot().following),false);await latest();
        }
        checks.keyboard=true;checks.latest=true;
        await page.locator('#chatTimeline .tl-marker[data-index="2"]').click();
        await expect.poll(()=>page.evaluate(()=>window.__messageScroller.snapshot().following)).toBe(false);
        await marker.click();await expect.poll(()=>page.evaluate(()=>{const p=window.__timelinePosition();return Math.abs(p.targetTop-p.containerTop);})).toBeLessThanOrEqual(2);
        checks.readingModeJump=true;
        const missingBefore=await page.evaluate(async()=>{document.querySelector('#messages [data-msg-index="2"]').remove();await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);return window.__timelinePosition();});
        await page.locator('#chatTimeline .tl-marker[data-index="2"]').click();
        const missingAfter=await page.evaluate(()=>window.__timelinePosition());assert.equal(missingAfter.scrollTop,missingBefore.scrollTop);assert.deepEqual(missingAfter.state,missingBefore.state);checks.missingTarget=true;
        await page.evaluate(()=>window.__timelineInstall('timeline-second',false));
        await expect.poll(()=>page.evaluate(()=>{const p=window.__timelinePosition();return p.scrollHeight-p.clientHeight-p.scrollTop;})).toBe(0);
        await marker.click();await expect.poll(()=>page.evaluate(()=>{const p=window.__timelinePosition();return Math.abs(p.targetTop-p.containerTop);})).toBeLessThanOrEqual(2);
        assert.equal(await page.evaluate(()=>window.__messageScroller.snapshot().sessionId),'timeline-second');checks.sessionSwitch=true;
      }
      await page.screenshot({path:path.join(evidenceDir,`${runtime}-${running?'running':'completed'}-timeline.png`)});
      assert.deepEqual(errors,[]);cases.push({runtime,running,before,after:last,frames,clicks,nativeJumps,blocked:expectBlocked,checks});
    }finally{await context.close();}
  }
  assert.deepEqual(audit.blockedWrites,[]);return{cases};
}

function startupIsolation(audit) {
  const result = {};
  for (const runtime of ["bundle", "classic"]) {
    result[runtime] = {};
    for (const pathname of Object.keys(STARTUP_FIXTURES)) {
      const initiated = audit.initiated.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      const fulfilled = audit.fulfilled.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      const serverReceived = audit.serverBound.filter((item) => item.runtime === runtime && item.method === "POST" && item.path === pathname);
      assert.equal(initiated.length, 1);
      assert.equal(fulfilled.length, 1);
      assert.deepEqual(serverReceived, []);
      result[runtime][pathname] = { initiated: 1, fulfilled: 1, serverReceived: 0 };
    }
  }
  return result;
}

async function main() {
  const toolNamesOnly = process.argv.includes('--tool-names-only');
  const imageReadsOnly = process.argv.includes('--image-reads-only');
  const traceArrowsOnly = process.argv.includes('--trace-arrows-only');
  const timelineOnly = process.argv.includes('--timeline-only');
  const evidenceDir = await fs.mkdtemp(path.join(os.tmpdir(), 'code079-tool-names-'));
  const host = await startIsolatedHost({ disableRoutingV2: true });
  const audit = createAudit();
  let browser = null;
  let cleanup = null;
  let result = null;
  try {
    const before = await host.metrics();
    browser = await chromium.launch({ headless: true });
    const runtimes = [];
    if (!toolNamesOnly && !imageReadsOnly && !traceArrowsOnly && !timelineOnly) {
      runtimes.push(await exerciseRuntime(browser, host, 'bundle', audit));
      runtimes.push(await exerciseRuntime(browser, host, 'classic', audit));
    }
    const toolNames = imageReadsOnly || traceArrowsOnly || timelineOnly ? null : await exerciseToolNames(browser, host, evidenceDir, toolNamesOnly);
    const imageReads = toolNamesOnly || traceArrowsOnly || timelineOnly ? null : await exerciseImageReads(browser, host, evidenceDir);
    const traceArrows = toolNamesOnly || imageReadsOnly || timelineOnly ? null : await exerciseTraceArrows(browser, host, evidenceDir);
    const timelineNavigation = timelineOnly ? await exerciseTimelineNavigation(browser,host,evidenceDir,process.argv.includes('--expect-timeline-blocked')) : null;
    const after = await host.metrics();
    assert.deepEqual(audit.blockedWrites, []);
    assert.equal(after.chatRequests.length - before.chatRequests.length, 0);
    assert.equal(after.toolExecutions.length - before.toolExecutions.length, 0);
    assert.equal(after.modelRouteRequests.length - before.modelRouteRequests.length, 0);
    assert.equal(after.production.agentRuns.length - before.production.agentRuns.length, 0);
    assert.equal(after.production.runtimeRuns.length - before.production.runtimeRuns.length, 0);
    result = {
      ok: true,
      command: "execution-trace-skill-model-reminder-selfcheck",
      runtimes,
      toolNames,
      imageReads,
      traceArrows,
      timelineNavigation,
      evidenceDir,
      startupIsolation: toolNamesOnly || imageReadsOnly || traceArrowsOnly || timelineOnly ? {} : startupIsolation(audit),
      sideEffects: { agentRuns: 0, runtimeRuns: 0, chat: 0, tools: 0, modelRoutes: 0, writes: 0 },
    };
  } finally {
    if (browser) await browser.close();
    cleanup = await host.stop();
    assert.equal(cleanup.childExited, true);
    assert.deepEqual(cleanup.portsClosed, [true, true]);
    assert.equal(cleanup.rootRemoved, true);
    assert.deepEqual(cleanup.cleanupErrors, []);
    assert.equal(getActiveChildCount(), 0);
    if (!result) await fs.writeFile(path.join(evidenceDir, 'result.json'), JSON.stringify({ok: false, cleanup}, null, 2));
  }
  result.cleanup = {
    childExited: cleanup.childExited,
    portsClosed: cleanup.portsClosed,
    rootRemoved: cleanup.rootRemoved,
    activeChildCount: getActiveChildCount(),
  };
  await fs.writeFile(path.join(evidenceDir, 'result.json'), JSON.stringify(result, null, 2));
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
