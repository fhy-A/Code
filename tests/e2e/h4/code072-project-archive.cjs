// Real UI -> isolated HTTP -> archive transactions. No live profile/model.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const { chromium, expect } = require('@playwright/test');
const { startIsolatedHost, getActiveChildCount } = require('./isolated-host.cjs');
const { createContext, createAudit, waitForRuntime } = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function api(host, route, method='GET', body) {
  const response = await fetch(new URL(route,host.ready.codeUrl), {method, headers:{'Content-Type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();
  assert(response.ok, `${method} ${route}: ${response.status} ${JSON.stringify(value)}`);
  return value;
}

async function scenario(browser, host, runtime, width, language, dir) {
  const projectRoot=path.join(host.root,'batch-'+runtime);await fs.mkdir(projectRoot);
  const project=await api(host,'/api/projects','POST',{label:'Duplicate label',rootPaths:[projectRoot]});
  const otherRoot=path.join(host.root,'other-'+runtime);await fs.mkdir(otherRoot);
  const other=await api(host,'/api/projects','POST',{label:'Duplicate label',rootPaths:[otherRoot]});
  const make=(title,projectId,runState={})=>api(host,'/api/sessions','POST',{title,projectId,cwd:projectId===project.id?projectRoot:otherRoot,runState,messages:[{role:'user',content:'fixture'}]});
  const first=await make(runtime+' needle',project.id);
  const second=await make(runtime+' active',project.id,{status:'running'});
  const unrelated=await make(runtime+' unrelated',other.id);
  const old=await make(runtime+' historical',other.id);
  await api(host,`/api/session-archive/${old.id}/archive`,'POST',{});
  const unassigned=await make(runtime+' unassigned',null);
  await api(host,`/api/session-archive/${unassigned.id}/archive`,'POST',{});
  const deletedRoot=path.join(host.root,'deleted-'+runtime);await fs.mkdir(deletedRoot);
  const deleted=await api(host,'/api/projects','POST',{label:'Deleted fixture',rootPaths:[deletedRoot]});
  const historical=await api(host,'/api/sessions','POST',{title:runtime+' deleted project',projectId:deleted.id,cwd:deletedRoot,messages:[]});
  await api(host,`/api/session-archive/${historical.id}/archive`,'POST',{});
  await api(host,`/api/projects/${deleted.id}`,'DELETE');
  const audit=createAudit(), errors=[];
  const context=await createContext(browser,host,runtime,audit,{width,language,preserveLanguage:true});
  // Keep the shared read-only fence intact. Only these fixture archive actions
  // may reach this host, and no other origin is permitted by this exception.
  await context.route(/\/api\/(?:project-session-archive(?:\/|\?)|session-archive\/)/, route=>{
    assert.equal(new URL(route.request().url()).origin,new URL(host.ready.codeUrl).origin);
    return route.continue();
  });
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch(), source=await response.text();
    const needle='function openProjectContextMenu(projectId, anchor = {}) {';
    assert(source.includes(needle));
    await route.fulfill({response,body:source.replace(needle,
      'window.__batchProbe={menu:openProjectContextMenu,settings:settingsFeature,state,setLang,reconcile:reconcileProjectArchiveNavigation};'+needle)});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  const open=async()=>{
    await page.evaluate(pid=>__batchProbe.menu(pid,{x:20,y:20}),project.id);
    await page.locator('[data-action="archive-all"]').click();
    await expect(page.locator('.batch-submit')).toBeEnabled();
  };
  try {
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
    await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
    // Cold settings load must populate filters when the async list arrives.
    await page.evaluate(()=>__batchProbe.settings.openSettingsPage('archives'));
    await expect(page.locator('#archivedProjectFilter option')).toHaveCount(runtime==='bundle'?4:6);
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(deleted.id));
    await expect(page.locator('.archived-session-row')).toHaveCount(1);
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(''));
    await expect(page.locator(`.archived-session-row[data-session-id="${unassigned.id}"]`)).toBeVisible();
    await open();
    await expect(page.locator('.batch-items li')).toHaveCount(2);
    const before=(await api(host,'/api/sessions')).data.map(v=>v.id).sort();
    await page.locator('.batch-cancel').click();
    assert.deepEqual((await api(host,'/api/sessions')).data.map(v=>v.id).sort(),before);
    await open();
    await page.screenshot({path:path.join(dir,runtime+'-confirm.png')});
    const bounds=await page.locator('.project-archive-card').evaluate(el=>{const b=el.getBoundingClientRect();return {left:b.left,right:b.right,width:innerWidth,overflow:el.scrollWidth>el.clientWidth+1};});
    assert(bounds.left>=0&&bounds.right<=bounds.width+1&&!bounds.overflow,JSON.stringify(bounds));
    // Lose the response after the authority-changing POST actually completes.
    const lose=async route=>{await route.fetch();await route.abort('failed');};
    await page.route('**/api/project-session-archive/confirm',lose,{times:1});
    await page.locator('.batch-submit').click();
    await expect(page.locator('.batch-body [role="alert"]')).toBeVisible();
    await expect(page.locator('.batch-submit')).toBeEnabled();
    await page.evaluate(sid=>{__batchProbe.state.sessionId=sid;},unrelated.id);
    await page.route('**/api/sessions',async route=>{
      const response=await route.fetch();await route.fulfill({response,json:{data:[]}});
    },{times:1});
    await page.locator('.batch-read').click();
    await expect(page.locator('.batch-submit')).toBeDisabled();
    await expect(page.locator('.batch-body [role="alert"]')).toHaveCount(0);
    assert.equal(await page.evaluate(()=>__batchProbe.state.sessionId),unrelated.id,'An unrelated current Session missing from the list must stay selected');
    const records=(await api(host,'/api/project-session-archive?projectId='+encodeURIComponent(project.id))).data;
    assert.equal(records.length,1);assert(records[0].items.every(i=>i.state==='archived'));
    assert((await api(host,'/api/sessions')).data.some(v=>v.id===unrelated.id));
    await page.locator('.batch-cancel').click();
    await page.evaluate(()=>__batchProbe.settings.openSettingsPage('archives'));
    await expect(page.locator('#archivedProjectFilter')).toBeVisible();
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(project.id));
    await expect(page.locator('.archived-session-row')).toHaveCount(2);
    await page.locator('#archivedSessionSearchInput').fill('needle');
    await expect(page.locator('.archived-session-row')).toHaveCount(1);
    await expect(page.locator(`.archived-session-row[data-session-id="${first.id}"]`)).toBeVisible();
    await page.screenshot({path:path.join(dir,runtime+'-filter.png')});
    // Single restore remains available and an old completed batch cannot undo it.
    await page.locator('.archived-session-restore').click();
    await expect(page.locator(`.archived-session-row[data-session-id="${first.id}"]`)).toHaveCount(0);
    const replay=await api(host,'/api/project-session-archive/resume','POST',{operationId:records[0].operationId});
    assert(replay.items.every(i=>i.state==='archived'));
    assert((await api(host,'/api/sessions')).data.some(v=>v.id===first.id));
    const preserved=await page.evaluate(async({sid,batch,pid})=>{
      __batchProbe.state.sessionId=sid;__batchProbe.state.sessions=[];
      const navigated=await __batchProbe.reconcile(batch,pid);
      return !navigated&&__batchProbe.state.sessionId===sid;
    },{sid:first.id,batch:records[0],pid:project.id});
    assert(preserved,'A restored current Session must remain selected');
    // Removing the last row for a selected project resets both select and list.
    await page.locator('#archivedSessionSearchInput').fill('');
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(other.id));
    await page.locator(`.archived-session-row[data-session-id="${old.id}"] .archived-session-restore`).click();
    await expect(page.locator('#archivedProjectFilter')).toHaveValue('');
    await expect(page.locator(`.archived-session-row[data-session-id="${second.id}"]`)).toBeVisible();
    await page.reload();await waitForRuntime(page,runtime);
    await open();await page.locator('.batch-history summary').click();
    await page.locator('.batch-history-item').first().click();
    await expect(page.locator('.batch-submit')).toBeDisabled();
    await page.locator('.batch-cancel').click();
    assert.deepEqual(errors,[]);
    return {runtime,width,language,cancel:true,lostResponseRead:true,fixedProject:true,searchAndIdFilter:true,singleRestore:true,reloadHistory:true,coldFilter:true,deletedAndUnassigned:true,missingOptionReset:true,unrelatedAndRestoredNavigation:true,bounds};
  } catch(error) {
    await page.screenshot({path:path.join(dir,runtime+'-failed.png')}).catch(()=>{});
    await fs.writeFile(path.join(dir,runtime+'-failure.json'),JSON.stringify({error:String(error.stack),errors,audit},null,2));
    throw error;
  } finally {await context.close();}
}

(async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code072-ui-'));
  const host=await startIsolatedHost({disableRoutingV2:true});
  let browser;const result={dir,cases:[]};
  try {
    browser=await chromium.launch({headless:true});
    for(const [runtime,width,language] of [['bundle',1280,'zh'],['classic',390,'en']]) {
      result.cases.push(await scenario(browser,host,runtime,width,language,dir));
      console.log(runtime+' passed');
    }
    result.ok=true;
  } catch(error){result.error=String(error.stack);result.ok=false;process.exitCode=1;}
  finally {
    if(browser)await browser.close();
    const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};
    if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}
    await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));
  }
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
