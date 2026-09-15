// Isolated real settings -> HTTP -> Markdown/index chain, with no real model.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const { chromium, expect } = require('@playwright/test');
const { startIsolatedHost, getActiveChildCount } = require('./isolated-host.cjs');
const { createContext, createAudit, waitForRuntime } = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function scenario(browser, host, runtime, width, language, dir) {
  const audit = createAudit(), errors = [], context = await createContext(browser, host, runtime, audit, { width, language, preserveLanguage: true });
  await context.route('**/api/memory**', route => {
    assert.equal(new URL(route.request().url()).origin, new URL(host.ready.codeUrl).origin);
    return route.continue();
  });
  await context.route('**/api/tools/save_memory', route => {
    assert.equal(new URL(route.request().url()).origin, new URL(host.ready.codeUrl).origin);
    return route.continue();
  });
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/, async route => {
    const response = await route.fetch(), source = await response.text();
    const needle = 'async function projectAgentEvent(ctx, event, snapshot = null) {';
    assert(source.includes(needle));
    await route.fulfill({ response, body: source.replace(needle,
      'window.__memoryProbe={settings:settingsFeature,memory:skillsMemoryFeature,state,els,setLang,build:buildSystemPromptSnapshot,pause:agentRecoveryPauseError,target:authorizationTarget,complete:projectAgentToolCompleted};' + needle) });
  });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(String(error)));
  try {
    await page.goto(new URL(runtime === 'bundle' ? '/' : '/dist/frontend/index.classic.html', host.ready.codeUrl).href);
    await waitForRuntime(page, runtime); await page.waitForLoadState('networkidle');
    await page.evaluate(() => __memoryProbe.settings.openSettingsPage('memory'));
    const name = `${runtime}-memory`;
    await page.locator('#settingsNewMem').click();
    await page.locator('#settingsMemName').fill(name);
    await page.locator('#settingsMemDesc').fill('fixture description');
    await page.locator('#settingsMemBody').fill('fixture durable fact');
    await page.locator('#settingsSaveMem').click();
    await expect(page.locator(`[data-edit="${name}"]`)).toBeVisible();
    const read = async n => {
      const response = await context.request.get(new URL(`/api/memory?file=${n}`, host.ready.codeUrl).href);
      assert(response.ok()); return response.json();
    };
    const original = await read(name);
    assert(original.revision && original.scope === 'legacy');
    await page.locator(`[data-edit="${name}"]`).click();
    await page.locator('#settingsMemName').fill(`${name}-renamed`);
    await page.locator('#settingsMemBody').fill('renamed latest fact');
    const mutations = [];
    const listener = request => { if (new URL(request.url()).pathname === '/api/memory' && request.method() !== 'GET') mutations.push(request.method()); };
    page.on('request', listener);
    await page.locator('#settingsSaveMem').click();
    await expect(page.locator(`[data-del="${name}-renamed"]`)).toBeVisible();
    page.off('request', listener);
    assert.deepEqual(mutations, ['POST'], 'Rename must not issue a destructive pre-delete');
    const renamed = await read(`${name}-renamed`);
    assert.equal(renamed.body, 'renamed latest fact');
    assert.equal(renamed.scope, original.scope);
    const index = await fs.readFile(path.join(host.dataDir, 'memory', 'MEMORY.md'), 'utf8');
    assert(index.includes(`${name}-renamed.md`) && !index.includes(`](${name}.md)`));

    // Real async feature: old success/failure and project navigation cannot win.
    const cache = await page.evaluate(async () => {
      const p = __memoryProbe, originalFetch = window.fetch, deferred = [];
      window.fetch = (url, init) => String(url).startsWith('/api/memory-context?')
        ? new Promise((resolve, reject) => deferred.push({ resolve, reject })) : originalFetch(url, init);
      const respond = (index, content) => deferred[index].resolve(new Response(JSON.stringify({ found: true, content, count: 1 }), { headers: { 'Content-Type': 'application/json' } }));
      try {
        const first = p.memory.loadMemoryContext(), second = p.memory.loadMemoryContext();
        respond(1, 'new'); await second; respond(0, 'old'); await first;
        if (p.state.memoryContext.content !== 'new') throw Error('Old success won');
        const third = p.memory.loadMemoryContext();
        p.state._foregroundNavigationSeq += 1;
        p.els.projectRoot.value += '/new-project';
        const fourth = p.memory.loadMemoryContext();
        respond(3, 'new project'); await fourth; deferred[2].reject(Error('old failure')); await third;
        if (p.state.memoryContext.content !== 'new project') throw Error('Old project failure won');
        return { sequence: true, project: true };
      } finally { window.fetch = originalFetch; }
    });
    assert(cache.sequence && cache.project);
    await page.reload(); await waitForRuntime(page, runtime);
    const completion = await page.evaluate(async runtime => {
      const p=__memoryProbe, originalFetch=window.fetch;
      const response=await originalFetch('/api/tools/save_memory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'event-'+runtime,description:'event fixture',body:'event-driven current fact'})});
      if(!response.ok) throw Error(await response.text());
      const result=await response.json();
      p.state.sessionId='event-session';
      p.state.memoryContext={found:true,content:'stale cached memory',count:99,project:p.els.projectRoot.value};
      const ctx={sessionId:'event-session',cwd:p.els.projectRoot.value,agentRunId:'event-run',run:{},messages:[{role:'tool-call',meta:{agentRunId:'event-run',toolCallId:'event-call',action:'save_memory'}}]};
      ctx.run._activeCtx=ctx;
      window.fetch=(url,init)=>String(url).startsWith('/api/memory-context?')
        ? new Promise(resolve=>window.__releaseMemoryRead=()=>originalFetch(url,init).then(resolve)) : originalFetch(url,init);
      try {
        p.complete(ctx,{type:'tool_completed',seq:101,data:{name:'save_memory',toolCallId:'event-call',result}});
        if(p.state.memoryContext.content!==null || p.state.memoryContext.count!==0) throw Error('Tool completion retained stale cache');
        if(typeof window.__releaseMemoryRead!=='function') throw Error('Tool completion did not request current memory');
        window.__releaseMemoryRead();
        return {scope:result.memoryScope,path:result.path};
      } finally {window.fetch=originalFetch;}
    },runtime);
    assert(completion.scope.startsWith('project:'));
    await page.waitForFunction(()=>__memoryProbe.state.memoryContext?.content?.includes('event-driven current fact'));
    assert(!(await page.evaluate(()=>__memoryProbe.state.memoryContext.content)).includes('stale cached memory'));
    await page.evaluate(()=>__memoryProbe.settings.openSettingsPage('memory'));

    await page.locator('[data-settings-lang="en"]').click();
    await expect(page.locator('.settings-memory-description')).toHaveText('Manage persistent knowledge. Each model request reads current memory; already sent history is retained.');
    await page.reload(); await waitForRuntime(page, runtime);
    await page.evaluate(() => __memoryProbe.settings.openSettingsPage('memory'));
    await expect(page.locator('.settings-memory-description')).toHaveText('Manage persistent knowledge. Each model request reads current memory; already sent history is retained.');
    await page.locator('[data-settings-lang="zh"]').click();
    await expect(page.locator('.settings-memory-description')).toHaveText('管理跨会话知识。每次模型请求读取最新记忆；已发送的会话历史保留。');
    await page.locator(`[data-del="${name}-renamed"]`).click();
    await expect(page.locator('.key-delete-confirm')).toContainText('legacy');
    for (const selector of ['.key-confirm-yes', '.key-confirm-no']) {
      assert(await page.locator(selector).evaluate(el => { const r=el.getBoundingClientRect(); return r.width >= 40 && r.left >= 0 && r.right <= innerWidth; }));
    }
    await page.screenshot({ path: path.join(dir, `${runtime}-${width}-confirmation.png`) });
    await page.locator('.key-confirm-no').click();
    assert.equal((await read(`${name}-renamed`)).revision, renamed.revision);
    await page.locator(`[data-del="${name}-renamed"]`).click();
    await page.locator('.key-confirm-yes').click();
    await expect(page.locator(`[data-del="${name}-renamed"]`)).toHaveCount(0);
    assert(!(await fs.readFile(path.join(host.dataDir, 'memory', 'MEMORY.md'), 'utf8')).includes(`${name}-renamed.md`));
    const legacy = await page.evaluate(async () => {
      const p = __memoryProbe;
      const prompt = await p.build({ memoryContext: {found:true,content:'NEVER-FREEZE-MEMORY'} });
      if (prompt.prompt.includes('NEVER-FREEZE-MEMORY')) throw Error('Memory leaked into frozen prompt');
      if (!Code.agent.tools.nativeTools.some(t => t.function.name === 'delete_memory')) throw Error('New tool missing from browser registry');
      const error = p.pause({ errorCode: 'memory_context_new_turn_required', recoveryState: { resumable: false } });
      return { text: error.message, recoverable: error.recoverable,
        target: p.target({ path: 'one.md', memoryTarget: { scope: 'global' } }) };
    });
    assert(legacy.text.includes('刷新页面') && legacy.text.includes('服务已更新') && legacy.text.includes('同一会话') && !legacy.recoverable && legacy.target.includes('global'));
    assert.deepEqual(errors, []);
    assert(!audit.serverBound.some(entry => entry.path.startsWith('/api/agent/runs') && entry.method === 'POST'));
    return { runtime, width, create: true, atomicRename: true, cancel: true, delete: true, cache, toolCompletionRefresh: true, languageRoundtrip: true, legacyPause: true };
  } catch (error) {
    await page.screenshot({ path: path.join(dir, `${runtime}-failed.png`) }).catch(() => {});
    await fs.writeFile(path.join(dir, `${runtime}-failed.json`), JSON.stringify({ error: String(error.stack), errors, audit }, null, 2));
    throw error;
  } finally { await context.close(); }
}

(async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'code084-memory-ui-'));
  const host = await startIsolatedHost({ disableRoutingV2: true });
  const result = { dir, cases: [] }; let browser;
  try {
    browser = await chromium.launch({ headless: true });
    for (const [runtime, width, language] of [['bundle', 1280, 'zh'], ['classic', 390, 'en']]) {
      result.cases.push(await scenario(browser, host, runtime, width, language, dir));
      console.log(`${runtime}/${width} passed`);
    }
    result.ok = true;
  } catch (error) { result.error = String(error.stack); result.ok = false; process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    const cleanup = await host.stop();
    result.cleanup = { childExited: cleanup.childExited, portsClosed: cleanup.portsClosed,
      rootRemoved: cleanup.rootRemoved, errors: cleanup.cleanupErrors, activeChildren: getActiveChildCount() };
    if (!cleanup.childExited || !cleanup.rootRemoved || !cleanup.portsClosed.every(Boolean) || cleanup.cleanupErrors.length || getActiveChildCount()) { result.ok = false; process.exitCode = 1; }
    await fs.writeFile(path.join(dir, 'result.json'), JSON.stringify(result, null, 2));
  }
  console.log(JSON.stringify(result));
})().catch(error => { console.error(error); process.exitCode = 1; });
