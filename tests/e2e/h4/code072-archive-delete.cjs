// Stage two: isolated real group UI -> HTTP -> durable permanent deletion.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const { chromium, expect } = require('@playwright/test');
const { startIsolatedHost, getActiveChildCount } = require('./isolated-host.cjs');
const { createContext, createAudit, waitForRuntime } = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function api(host,url,method='GET',body) {
  const response = await fetch(new URL(url,host.ready.codeUrl),{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();assert(response.ok,`${method} ${url}: ${response.status} ${JSON.stringify(value)}`);return value;
}

async function scenario(browser,host,runtime,width,language,dir) {
  const projects=[];
  for(const name of ['target','other','gone']) {
    const root=path.join(host.root,runtime+'-'+name);await fs.mkdir(root);
    projects.push(await api(host,'/api/projects','POST',{label:'Same project name',rootPaths:[root]}));
  }
  const [project,other,gone]=projects;
  const make=async(title,pid=project.id,archived=true)=>{
    const selected=projects.find(p=>p.id===pid);
    const value=await api(host,'/api/sessions','POST',{title,projectId:pid,cwd:selected?.rootPaths[0]||host.projectDir,messages:[{role:'user',content:'Disposable delete fixture'}]});
    if(archived)await api(host,`/api/session-archive/${value.id}/archive`,'POST',{});
    return value;
  };
  const first=await make(runtime+' needle'),second=await make(runtime+' hidden');
  const active=await make(runtime+' active',project.id,false),foreign=await make(runtime+' foreign',other.id);
  const unassigned=await make(runtime+' unassigned',null),historical=await make(runtime+' historical',gone.id);
  await api(host,`/api/projects/${gone.id}`,'DELETE');
  const workspace=path.join(project.rootPaths[0],'keep.txt');await fs.writeFile(workspace,'Keep workspace');
  const projectBytes=await fs.readFile(path.join(host.dataDir,'projects.json'));
  const audit=createAudit(),errors=[];
  const context=await createContext(browser,host,runtime,audit,{width,language,preserveLanguage:true});
  await context.route(/\/api\/(?:project-archive-delete(?:\/|\?|$)|session-archive\/)/,route=>{
    assert.equal(new URL(route.request().url()).origin,new URL(host.ready.codeUrl).origin);
    return route.continue();
  });
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch(),source=await response.text(),needle='function openProjectContextMenu(projectId, anchor = {}) {';
    assert(source.includes(needle));await route.fulfill({response,body:source.replace(needle,'window.__deleteProbe={settings:settingsFeature,state,feedback:archiveFeedbackEntries,covered:archiveFeedbackCovered,store:archiveFeedbackStore};'+needle)});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
  const openGroup=async pid=>{
    const key=pid===null?{kind:'unassigned'}:{kind:pid===gone.id?'deleted-project':'project',projectId:pid};
    const selector='.archive-group-delete[data-scope='+JSON.stringify(JSON.stringify(key))+']';
    await page.locator(selector).click();await expect(page.locator('.delete-batch-submit')).toBeEnabled();
  };
  const openSettings=async()=>{
    await page.evaluate(()=>__deleteProbe.settings.openSettingsPage('archives'));
    await expect(page.locator('#archivedSessionSearchInput')).toBeVisible();
  };
  try {
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
    await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await openSettings();
    const labels=await page.locator('#archivedProjectFilter option').allTextContents();
    for(const id of [project.id,other.id,gone.id])assert(labels.every(label=>!label.includes(id)));
    const toolbar=await page.locator('.archived-session-toolbar').evaluate(el=>{
      const search=el.querySelector('.archived-session-search-field').getBoundingClientRect(),filter=el.querySelector('.archived-project-filter-field').getBoundingClientRect();
      return {search:{left:search.left,top:search.top,width:search.width},filter:{left:filter.left,top:filter.top,width:filter.width},overflow:el.scrollWidth>el.clientWidth+1};
    });assert(!toolbar.overflow);
    if(width>600)assert(Math.abs(toolbar.search.top-toolbar.filter.top)<3&&toolbar.search.left<toolbar.filter.left&&toolbar.search.width>toolbar.filter.width);
    else assert(toolbar.filter.top>toolbar.search.top);
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(project.id));
    await page.locator('#archivedSessionSearchInput').fill('needle');
    await expect(page.locator('.archived-session-row')).toHaveCount(1);
    await expect(page.locator('.archived-group-count')).toHaveText(language==='zh'?'（匹配 1 / 共 2）':'(1 matching / 2 total)');
    await openGroup(project.id);
    await expect(page.locator('.archive-delete-items li')).toHaveCount(2);
    await expect(page.locator('.archive-delete-items')).not.toBeVisible();
    await expect(page.locator('.archive-delete-search-note')).toContainText(language==='zh'?'搜索结果之外':'outside the search');
    await expect(page.locator('.archive-delete-scope')).toContainText(project.label);
    assert(!(await page.locator('.delete-batch-body').innerText()).includes(project.id));
    await expect(page.locator('.delete-batch-body')).toContainText(language==='zh'?'不可恢复':'cannot be undone');
    const before=(await api(host,'/api/session-archive')).data.map(v=>v.id).sort();
    await page.locator('.delete-batch-cancel').click();
    assert.deepEqual((await api(host,'/api/session-archive')).data.map(v=>v.id).sort(),before);
    await openGroup(project.id);
    await expect(page.locator('.archive-group-delete-modal')).toHaveCSS('opacity','1');
    await page.screenshot({path:path.join(dir,runtime+'-confirm.png')});
    const bounds=await page.locator('.archive-group-delete-modal .modal-card').evaluate(el=>{const b=el.getBoundingClientRect();return {left:b.left,right:b.right,width:innerWidth,overflow:el.scrollWidth>el.clientWidth+1};});
    assert(bounds.left>=0&&bounds.right<=bounds.width+1&&!bounds.overflow);
    await page.route('**/api/project-archive-delete/confirm',async route=>{await route.fetch();await route.abort('failed');},{times:1});
    await page.locator('.delete-batch-submit').click();await expect(page.locator('.archive-group-delete-modal')).toHaveCount(0);
    const notice=page.locator('.archive-feedback-card[data-kind="delete"]:not(.is-success)');
    await expect(notice.locator('.feedback-check')).toBeVisible();
    await expect(notice).toContainText(language==='zh'?'暂时无法确认':'not confirmed');
    await notice.locator('.feedback-check').click();await expect(notice).toHaveCount(0);
    const result=(await api(host,'/api/project-archive-delete')).data.find(v=>v.scope.projectId===project.id);
    assert.equal(result.total,2);assert(result.items.every(i=>i.state==='deleted'));
    await page.screenshot({path:path.join(dir,runtime+'-result.png')});
    assert((await api(host,'/api/sessions')).data.some(v=>v.id===active.id));
    assert((await api(host,'/api/session-archive')).data.some(v=>v.id===foreign.id));
    assert.equal(await fs.readFile(workspace,'utf8'),'Keep workspace');
    assert.deepEqual(await fs.readFile(path.join(host.dataDir,'projects.json')),projectBytes);
    // Search does not control the authoritative group set; retry does not add new archives.
    await page.locator('#archivedSessionSearchInput').fill('');
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(other.id));
    await openGroup(other.id);
    await expect(page.locator('.archive-delete-search-note')).toHaveCount(0);
    await api(host,`/api/session-archive/${foreign.id}/restore`,'POST',{});
    await page.route('**/api/sessions',route=>route.abort('failed'),{times:1});
    await page.locator('.delete-batch-submit').click();
    await expect(notice.locator('.feedback-retry')).toBeVisible();
    await expect(notice.locator('.feedback-refresh')).toBeVisible();
    await notice.locator('summary').click();
    await expect(notice).toContainText(language==='zh'?'已变化':'changed');
    await api(host,`/api/session-archive/${foreign.id}/archive`,'POST',{});
    const later=await make(runtime+' later archive',other.id);
    await notice.locator('.feedback-retry').click();
    await expect(page.locator('.archive-delete-items li')).toHaveCount(1);
    await page.locator('.delete-batch-cancel').click();await expect(notice).toBeVisible();
    await notice.locator('.feedback-retry').click();
    await page.locator('.delete-batch-submit').click();await expect(notice).toHaveCount(0);
    assert((await api(host,'/api/session-archive')).data.some(v=>v.id===later.id));
    await page.locator('#archivedProjectFilter').selectOption('');
    await expect(page.locator('.archived-session-group[data-project-id="__unassigned__"] .archived-group-count')).toHaveText(language==='zh'?'（1）':'(2)');
    await expect(page.locator(`.archived-session-group[data-project-id="${gone.id}"] .archived-group-count`)).toHaveText(language==='zh'?'（1）':'(1)');
    await expect(page.locator(`.archived-session-group[data-project-id="${other.id}"] .archived-group-count`)).toHaveText(language==='zh'?'（1）':'(1)');
    await openGroup(null);await expect(page.locator('.archive-delete-scope')).toHaveText(language==='zh'?'未归属项目':'No project');
    await page.locator('.delete-batch-cancel').click();
    await openGroup(gone.id);await expect(page.locator('.archive-delete-scope')).toContainText(language==='zh'?'原项目已移除':'Former project');
    await page.locator('.delete-batch-cancel').click();
    // Keep the old single delete UI working alongside the new group action.
    await page.locator(`.archived-session-row[data-session-id="${historical.id}"] .archived-session-delete`).click();
    await page.locator('#confirmDeleteSession').click();
    await expect(page.locator(`.archived-session-row[data-session-id="${historical.id}"]`)).toHaveCount(0);
    await page.reload();await waitForRuntime(page,runtime);await openSettings();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.archive-delete-history,.archive-delete-history-item')).toHaveCount(0);
    await expect(notice).toHaveCount(0);
    const cleanupCases=[];
    for(const kind of ['bundle','journal']) {
      const root=path.join(host.root,runtime+'-cleanup-'+kind);await fs.mkdir(root);
      const cleanupProject=await api(host,'/api/projects','POST',{label:'Cleanup '+kind,rootPaths:[root]});
      projects.push(cleanupProject);
      const target=await make(runtime+' cleanup '+kind,cleanupProject.id);
      const healthy=await make(runtime+' healthy '+kind,cleanupProject.id);
      const findBundle=async directory=>{
        for(const entry of await fs.readdir(directory,{withFileTypes:true})) {
          if(!entry.isDirectory())continue;
          const child=path.join(directory,entry.name);
          if(entry.name===target.id)return child;
          const found=await findBundle(child);if(found)return found;
        }
      };
      const bundle=await findBundle(path.join(host.dataDir,'session-archive'));assert(bundle);
      const journal=path.join(path.dirname(bundle),'.transactions',target.id+'.json');
      const exists=async name=>fs.access(name).then(()=>true,()=>false);
      const control=path.join(host.root,'code072-cleanup-control.json');
      await fs.writeFile(control,JSON.stringify({sessionId:target.id,kind}));
      await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await openSettings();
      await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(cleanupProject.id));
      await openGroup(cleanupProject.id);await page.locator('.delete-batch-submit').click();
      await expect(notice.locator('.feedback-continue')).toBeVisible();
      await notice.locator('summary').click();
      const targetRow=notice.locator(`li[data-session-id="${target.id}"]`);
      await expect(targetRow).toHaveAttribute('data-state','cleanup_pending');
      await expect(targetRow).toContainText(language==='zh'?'归档清理未完成':'Archive cleanup pending');
      await expect(notice).toContainText(language==='zh'?'已完成 1 个':'Completed: 1');
      await expect(notice.locator('.feedback-continue')).toHaveText(language==='zh'?'继续清理旧归档':'Resume archive cleanup');
      const batch=(await api(host,'/api/project-archive-delete')).data.find(v=>v.scope.projectId===cleanupProject.id);
      const item=batch.items.find(v=>v.sessionId===target.id);
      assert(item.factsDeleted&&!item.cleanupComplete&&item.result.errorCode);
      assert.equal(await exists(bundle),kind==='bundle');assert(await exists(journal));
      await notice.locator('.feedback-check').click();await expect(targetRow).toHaveAttribute('data-state','cleanup_pending');
      await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await openSettings();
      await expect(notice.locator('.feedback-continue')).toBeVisible();await notice.locator('summary').click();
      await expect(targetRow).toHaveAttribute('data-state','cleanup_pending');
      const feedbackText=await notice.innerText();assert(!feedbackText.includes(batch.operationId)&&!feedbackText.includes(target.id));
      await expect(page.locator('#settingsPage')).toHaveCSS('opacity','1');
      await page.screenshot({path:path.join(dir,runtime+'-'+kind+'-cleanup-pending.png')});
      const events=async()=> (await fs.readFile(path.join(host.root,'code072-cleanup-events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse).filter(v=>v.sessionId===target.id);
      assert.equal((await events()).filter(v=>v.kind==='facts_delete').length,1);
      await fs.writeFile(control,JSON.stringify({sessionId:target.id,kind:'off'}));
      await notice.locator('.feedback-continue').click();await expect(notice).toHaveCount(0);
      await expect(page.locator('.archive-group-delete-modal')).toHaveCount(0);
      assert(!await exists(bundle)&&!await exists(journal));
      const after=await events();
      for(const event of ['facts_delete','bundle_removed','journal_removed'])assert.equal(after.filter(v=>v.kind===event).length,1,event);
      const repeated=await api(host,'/api/project-archive-delete/resume','POST',{operationId:batch.operationId,scope:batch.scope,action:'permanent_delete'});
      assert(repeated.items.every(v=>v.state==='deleted'&&v.cleanupComplete));
      assert.deepEqual(await events(),after);
      cleanupCases.push({kind,partialBatchVisible:true,readPreservesPending:true,cleanupOnlyResume:true,factsDeletedOnce:true,copyAndJournalRemoved:true});
    }
    const largeRoot=path.join(host.root,'delete-large-'+runtime);await fs.mkdir(largeRoot);
    const large=await api(host,'/api/projects','POST',{label:'Large delete preview',rootPaths:[largeRoot]});projects.push(large);
    for(let i=0;i<24;i++)await make('Long archive title '+i+' '+('Long text '.repeat(25)),large.id);
    await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await openSettings();
    await page.locator('#archivedProjectFilter').selectOption(JSON.stringify(large.id));await openGroup(large.id);
    await expect(page.locator('.archive-delete-search-note')).toHaveCount(0);
    await expect(page.locator('.archive-delete-items')).not.toBeVisible();await page.locator('.batch-target-list > summary').click();
    await expect(page.locator('.archive-delete-items li')).toHaveCount(24);
    const largeBounds=await page.locator('.archive-delete-items').evaluate(el=>({height:el.clientHeight,scroll:el.scrollHeight,overflow:el.scrollWidth>el.clientWidth+1}));
    assert(largeBounds.height<=201&&largeBounds.scroll>largeBounds.height&&!largeBounds.overflow,JSON.stringify(largeBounds));
    await expect(page.locator('.archive-group-delete-modal')).toHaveCSS('opacity','1');const footerBounds=await page.locator('.project-archive-card .confirm-actions').evaluate(el=>({bottom:el.getBoundingClientRect().bottom,height:innerHeight}));assert(footerBounds.bottom<=footerBounds.height-8);
    const panelStyle=await page.locator('.batch-list-panel').first().evaluate(el=>({border:parseFloat(getComputedStyle(el).borderTopWidth),background:getComputedStyle(el).backgroundColor,card:getComputedStyle(el.closest('.project-archive-card')).backgroundColor}));assert(panelStyle.border>=1&&panelStyle.background!==panelStyle.card);
    await page.screenshot({path:path.join(dir,runtime+'-large-lists.png')});
    await page.locator('.delete-batch-cancel').click();
    const association=await page.evaluate(()=>{
      const old=__deleteProbe.store('delete',{operationId:'ui-parent',scope:{kind:'unassigned'},confirmed:true,total:2,items:[{sessionId:'a',state:'failed'},{sessionId:'b',state:'cleanup_pending'}]});
      const child=__deleteProbe.store('delete',{operationId:'ui-child',scope:{kind:'unassigned'},retryOf:'ui-parent',confirmed:false,total:1,items:[{sessionId:'a',state:'pending'}]});
      const preview=[...__deleteProbe.covered(old)];child.value.confirmed=true;child.value.items[0].state='failed';const failure=[...__deleteProbe.covered(old)];
      child.unknown=true;child.value.items[0].state='deleted';const unknown=[...__deleteProbe.covered(old)];child.unknown=false;const success=[...__deleteProbe.covered(old)];
      __deleteProbe.feedback.delete('delete:ui-parent');__deleteProbe.feedback.delete('delete:ui-child');return {preview,failure,unknown,success};
    });assert.deepEqual(association,{preview:[],failure:[],unknown:[],success:['a']});
    assert.deepEqual(errors,[]);
    return {runtime,width,language,searchDoesNotLimitScope:true,cancel:true,lostResponseDirectRead:true,
      conflictAndFreshRetry:true,newArchiveExcludedFromRetry:true,unassignedAndHistorical:true,singleDelete:true,
      noCompletedHistory:true,unfinishedReload:true,completionCloses:true,collapsedList:true,largeListScroll:true,toolbarResponsive:true,activeProjectWorkspacePreserved:true,bounds,cleanupCases};
  } catch(error) {
    await page.screenshot({path:path.join(dir,runtime+'-failed.png')}).catch(()=>{});
    await fs.writeFile(path.join(dir,runtime+'-failure.json'),JSON.stringify({error:String(error.stack),errors,audit},null,2));
    throw error;
  } finally {await context.close();}
}

(async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code072-delete-ui-'));
  const host=await startIsolatedHost({disableRoutingV2:true,enableArchiveDeleteCleanupFaults:true});let browser;const result={dir,cases:[]};
  try {
    browser=await chromium.launch({headless:true});
    for(const [runtime,width,language] of [['bundle',1280,'zh'],['classic',390,'en']]) {
      result.cases.push(await scenario(browser,host,runtime,width,language,dir));console.log(runtime+' passed');
    }
    result.ok=true;
  } catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
  finally {
    if(browser)await browser.close();const c=await host.stop();
    result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};
    if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}
    await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));
  }
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
