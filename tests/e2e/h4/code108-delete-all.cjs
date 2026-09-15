// Real isolated UI -> HTTP -> all-scope admission and permanent-delete transaction.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const { chromium, expect } = require('@playwright/test');
const { startIsolatedHost, getActiveChildCount } = require('./isolated-host.cjs');
const { createContext, createAudit, waitForRuntime } = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function api(host,url,method='GET',body) {
  const response=await fetch(new URL(url,host.ready.codeUrl),{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();assert(response.ok,JSON.stringify(value));return value;
}

async function scenario(browser,host,runtime,width,language,dir) {
  const projects=[];
  for (const label of ['current','other','historical']) {
    const root=path.join(host.root,runtime+'-'+label);await fs.mkdir(root);
    projects.push(await api(host,'/api/projects','POST',{label,rootPaths:[root]}));
  }
  const make=async(title,pid=projects[0].id,archived=true)=>{
    const record=await api(host,'/api/sessions','POST',{title,projectId:pid,cwd:projects.find(p=>p.id===pid)?.rootPaths[0]||host.projectDir,messages:[{role:'user',content:'Disposable fixture'}]});
    if(archived)await api(host,`/api/session-archive/${record.id}/archive`,'POST',{});
    return record;
  };
  const ids=[];
  for(const pid of [...projects.map(p=>p.id),null])ids.push((await make('hidden',pid)).id);
  const active=await make('keep active',projects[0].id,false);
  await api(host,`/api/projects/${projects[2].id}`,'DELETE');
  const workspace=path.join(projects[0].rootPaths[0],'keep.txt');await fs.writeFile(workspace,'preserve');
  const catalog=await fs.readFile(path.join(host.dataDir,'projects.json'));
  const audit=createAudit(),errors=[],requests=[];
  const context=await createContext(browser,host,runtime,audit,{width,language,theme:'dark',preserveLanguage:true});
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch(),source=await response.text(),needle='function openProjectContextMenu(projectId, anchor = {}) {';
    assert(source.includes(needle));await route.fulfill({response,body:source.replace(needle,'window.__allProbe={settings:settingsFeature};'+needle)});
  });
  let intercept='normal',afterSubmission;
  await context.route(/\/api\/project-archive-delete\//,async route=>{
    const action=new URL(route.request().url()).pathname.split('/').at(-1);
    const body=route.request().postDataJSON();requests.push({action,body});
    assert.equal(new URL(route.request().url()).origin,new URL(host.ready.codeUrl).origin);
    if(action==='confirm-all'&&intercept==='before'){intercept='normal';await route.abort('failed');return;}
    if(action==='confirm-all'&&intercept==='after'){
      intercept='normal';const response=await route.fetch();assert(response.ok());afterSubmission=await response.json();await route.abort('failed');return;
    }
    return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  const open=async()=>{await page.evaluate(()=>__allProbe.settings.openSettingsPage('archives'));await expect(page.locator('.archive-all-delete')).toBeVisible();};
  const reload=async()=>{await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await open();};
  const notice=page.locator('.archive-feedback-card[data-kind="delete"]');
  try {
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
    await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await open();
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(projects[0].id));
    await page.locator('#archivedSessionSearchInput').fill('not found');
    const beforeOps=(await api(host,'/api/project-archive-delete')).data.length;
    const snapshots=[];
    for(const theme of ['light','dark']){
      await page.evaluate(theme=>window.Code.core.theme.activateTheme(theme,'codex','codex'),theme);
      await expect(page.locator('.archive-all-delete')).toHaveText(language==='zh'?'全部删除':'Delete all');
      const bounds=await page.locator('.archive-all-delete').evaluate(el=>{
        const b=el.getBoundingClientRect(),h=el.closest('.settings-section-header').getBoundingClientRect(),t=el.closest('.archived-sessions-panel').querySelector('.archived-session-toolbar').getBoundingClientRect();
        return {button:{right:b.right,bottom:b.bottom,left:b.left},header:{right:h.right,bottom:h.bottom},toolbarTop:t.top,color:getComputedStyle(el).color,border:getComputedStyle(el).borderTopColor};
      });
      assert(Math.abs(bounds.button.right-bounds.header.right)<3&&bounds.button.bottom<=bounds.toolbarTop,JSON.stringify(bounds));
      const rgb=bounds.color.match(/[\d.]+/g).map(Number).map(v=>bounds.color.startsWith('color(')?v*255:v);assert(rgb[0]>rgb[1]+30&&rgb[0]>rgb[2]+15,bounds.color);
      assert.equal(bounds.color,bounds.border);
      await expect(page.locator('#settingsPage')).toHaveCSS('opacity','1');
      await page.screenshot({path:path.join(dir,`${runtime}-${theme}-header.png`)});
      const requestCount=requests.length;
      await page.locator('.archive-all-delete').click();
      await expect(page.locator('.archive-all-delete-modal')).toBeVisible();
      await expect(page.locator('.archive-all-delete-modal h2')).toHaveText(language==='zh'?'删除全部已归档会话？':'Delete all archived sessions?');
      await expect(page.locator('.delete-all-submit')).toHaveText(language==='zh'?'删除':'Delete');
      assert.equal(await page.locator('.archive-all-delete-modal ul, .archive-all-delete-modal details').count(),0);
      assert(!/\d/.test(await page.locator('.archive-all-delete-modal').innerText()));
      assert.equal(requests.length,requestCount,'No pre-confirmation preview or mutation request');
      await expect(page.locator('.archive-all-delete-modal')).toHaveCSS('opacity','1');
      await page.screenshot({path:path.join(dir,`${runtime}-${theme}-confirm.png`)});
      await page.locator('.delete-all-cancel').click();
      assert.equal((await api(host,'/api/project-archive-delete')).data.length,beforeOps);
      snapshots.push({theme,bounds,cancelZeroMutation:true,noPreview:true});
    }
    // The request is lost before the server sees it; the page reload retains its ID.
    intercept='before';await page.locator('.archive-all-delete').click();await page.locator('.delete-all-submit').click();
    await expect(page.locator('.archive-all-delete-modal')).toHaveCount(0);
    await expect(notice).toHaveAttribute('data-state','unknown');
    const original=requests.find(r=>r.action==='confirm-all').body;
    await reload();await expect(notice).toHaveAttribute('data-state','unknown');
    intercept='after';await notice.locator('.feedback-continue').click();
    await expect(notice).toHaveAttribute('data-state','unknown');
    assert(afterSubmission&&afterSubmission.items.every(i=>i.state==='deleted'));
    assert.deepEqual(new Set(afterSubmission.items.map(i=>i.sessionId)),new Set(ids));
    const later=await make('arrived after consent');
    await notice.locator('.feedback-check').click();await expect(notice).toHaveAttribute('data-state','success');
    await expect(notice).toContainText(language==='zh'?'已删除全部已归档会话。':'All archived sessions deleted.');
    const confirmations=requests.filter(r=>r.action==='confirm-all');assert.equal(confirmations.length,2);
    assert(confirmations.every(r=>r.body.operationId===original.operationId&&r.body.confirmationToken===original.confirmationToken));
    const operations=(await api(host,'/api/project-archive-delete')).data;
    assert.equal(operations.length,beforeOps+1);assert.equal(operations[0].operationId,original.operationId);
    await api(host,`/api/sessions/${active.id}`);
    assert.equal(await fs.readFile(workspace,'utf8'),'preserve');assert.deepEqual(await fs.readFile(path.join(host.dataDir,'projects.json')),catalog);
    const allArchives=await api(host,'/api/session-archive');
    assert(JSON.stringify(allArchives).includes(later.id));
    // Each cleanup failure uses the production v3 journal, fact and cleanup receipt.
    const cleanupCases=[];
    for(const kind of ['bundle','journal']){
      const target=await make('cleanup '+kind),healthy=await make('healthy '+kind,null);
      const control=path.join(host.root,'code072-cleanup-control.json');
      await fs.writeFile(control,JSON.stringify({sessionId:target.id,kind}));
      await reload();await page.locator('.archive-all-delete').click();await page.locator('.delete-all-submit').click();
      await expect(notice).toHaveAttribute('data-state','attention');
      await notice.locator('summary').click();
      await expect(notice.locator(`li[data-session-id="${target.id}"]`)).toHaveAttribute('data-state','cleanup_pending');
      const batch=(await api(host,'/api/project-archive-delete')).data[0];
      assert.equal(batch.scope.kind,'all');assert(batch.items.find(i=>i.sessionId===healthy.id).cleanupComplete);
      const events=async()=> (await fs.readFile(path.join(host.root,'code072-cleanup-events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).filter(v=>v.sessionId===target.id&&v.kind==='facts_delete');
      assert.equal((await events()).length,1);
      await reload();await expect(notice.locator('.feedback-continue')).toBeVisible();
      await expect(page.locator('#settingsPage')).toHaveCSS('opacity','1');
      await expect(page.locator('.archived-session-state[role="status"]')).toHaveCount(0);
      await page.screenshot({path:path.join(dir,`${runtime}-${kind}-pending.png`)});
      await fs.writeFile(control,JSON.stringify({sessionId:target.id,kind:'off'}));
      await notice.locator('.feedback-continue').click();await expect(notice).toHaveAttribute('data-state','success');
      assert.equal((await events()).length,1);
      const repeat=await api(host,'/api/project-archive-delete/resume','POST',batch);assert(repeat.items.every(i=>i.cleanupComplete));
      assert.equal((await events()).length,1);cleanupCases.push({kind,factsDeletedOnce:true,reloadResume:true});
    }
    // Language changes use the production language runtime without another request.
    await page.evaluate(language=>window.__toolNameLanguage(language==='zh'?'en':'zh'),language);await open();
    await expect(page.locator('.archive-all-delete')).toHaveText(language==='zh'?'Delete all':'全部删除');
    await page.evaluate(language=>window.__toolNameLanguage(language),language);await open();
    await expect(page.locator('.archive-all-delete')).toHaveText(language==='zh'?'全部删除':'Delete all');
    assert.deepEqual(errors,[]);
    return {runtime,width,language,snapshots,cleanupCases,immediateConfirmation:true,noCountsOrList:true,requestLossBeforeAndAfter:true,sameOperationAcrossReload:true,newArchiveExcluded:true,workspaceAndActivePreserved:true,languageSwitch:true};
  } catch(error){await page.screenshot({path:path.join(dir,runtime+'-failed.png')}).catch(()=>{});await fs.writeFile(path.join(dir,runtime+'-failure.json'),JSON.stringify({error:String(error.stack),errors,audit,requests},null,2));throw error;}
  finally{await context.close();}
}

(async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code108-all-ui-'));
  const host=await startIsolatedHost({disableRoutingV2:true,enableArchiveDeleteCleanupFaults:true});let browser;const result={dir,cases:[]};
  try{browser=await chromium.launch({headless:true});for(const [runtime,width,language] of [['bundle',1280,'zh'],['classic',390,'en']])result.cases.push(await scenario(browser,host,runtime,width,language,dir));result.ok=true;}
  catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
  finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
