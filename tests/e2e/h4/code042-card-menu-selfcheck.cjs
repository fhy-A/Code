const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
async function scenario(browser,host,fixture,runtime,width,language,dir){
 const audit=createAudit(),errors=[],actions=[],previews=[],reads=[],context=await createContext(browser,host,runtime,audit,{width,language,theme:language==='zh'?'light':'dark'});
 await context.route('**/api/config',route=>{if(route.request().method()!=='POST')return route.fallback();assert.equal(route.request().postDataJSON().projectRoot,host.projectDir);return route.fulfill({json:fixture.config});});
 await context.addInitScript(({sid})=>{localStorage.setItem('code-last-session',sid);localStorage.setItem('code-foreground-view','session');window.__menuCopies=[];Object.defineProperty(navigator.clipboard,'writeText',{configurable:true,value:async text=>window.__menuCopies.push(text)});}, {sid:fixture.sid});
 await context.route('**/api/preview/context',route=>route.fulfill({json:fixture.binding}));
 await context.route('**/api/agent/runs/*/file-changes**',route=>{reads.push(new URL(route.request().url()).pathname);return route.fulfill({json:fixture.summary});});
 await context.route('**/api/open-file',route=>{const body=route.request().postDataJSON();actions.push(body);return body.reveal?route.fulfill({json:{ok:true,degraded:true}}):route.fulfill({status:404,json:{error:'fixture missing file'}});});
 await context.route('**/api/preview/file?**',route=>{previews.push(new URL(route.request().url()).searchParams.get('path'));return route.fulfill({status:404,json:{error:'fixture missing file'}});});
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch();let source=await response.text();assert(source.includes('filesFeature.bind();'));
  source=source.replace('filesFeature.bind();','filesFeature.bind(); window.__menuHarness={state,filesFeature,recordedChangeSummaries,getSessionMessages,render:renderMessages};');
  assert(source.includes('  openFile: loadFile,'));source=source.replace('  openFile: loadFile,','  openFile: (...args)=>{window.__menuPreviewArgs=args;return loadFile(...args);},');
  await route.fulfill({response,body:source});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await expect(page.locator('[data-review-load]')).toHaveCount(1);
  await page.evaluate(({rid,key})=>{const button=document.createElement('button');button.className='recorded-change-file';button.dataset.recordedReview=rid;button.dataset.reviewFile=key;button.textContent='Forged cold path';button.title='C:/untrusted';document.querySelector('[data-review-card]').appendChild(button);button.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}));button.remove();},{rid:fixture.rid,key:fixture.summary.operations[0].fileKey});
  await expect(page.locator('.file-ctx-menu')).toHaveCount(0);assert.equal(reads.length,0);
  await page.locator('[data-review-load]').click();await expect(page.locator('.recorded-change-file')).toHaveCount(3);
  const row=page.locator('.recorded-change-file').first(),menu=page.locator('.file-ctx-menu');
  const show=async(index=0)=>{await page.locator('.recorded-change-file').nth(index).click({button:'right'});await expect(menu).toBeVisible();};
  await show();assert.equal(reads.length,1,'right click does not inspect historical diff');assert.equal(actions.length,0);assert.equal(previews.length,0);
  await expect(menu.locator('.file-ctx-name')).toHaveText('报告 one.txt');assert.deepEqual(await menu.locator('button').evaluateAll(nodes=>nodes.map(n=>n.dataset.action)),['preview-new','open','copy-path','reveal']);
  await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(row).toBeFocused();
  for(let i=0;i<3;i++){await show(i);await menu.locator('[data-action="copy-path"]').click();}
  assert.deepEqual(await page.evaluate(()=>window.__menuCopies),fixture.summary.operations.map(op=>op.path));
  await show();await menu.locator('[data-action="open"]').click();await expect.poll(()=>actions.length).toBe(1);assert.deepEqual(actions[0],{path:fixture.summary.operations[0].path});
  await expect(page.locator('.toast').last()).toContainText(language==='zh'?'打开失败':'Open failed');
  await show();await menu.locator('[data-action="reveal"]').click();await expect.poll(()=>actions.length).toBe(2);assert.deepEqual(actions[1],{path:fixture.summary.operations[0].path,reveal:true});
  await expect(page.locator('.toast').last()).toContainText(language==='zh'?'未能完成选择':'selection or foreground');
  await show();await menu.locator('[data-action="preview-new"]').click();await expect.poll(()=>previews.length).toBe(1);assert.equal(previews[0],fixture.summary.operations[0].path);
  assert.deepEqual(await page.evaluate(()=>window.__menuPreviewArgs),[fixture.summary.operations[0].path,undefined,{newTab:true}]);
  await expect(page.locator('#filePreview')).toContainText(fixture.summary.operations[0].path);
  // Close preview before menu screenshots; no OS process or real path was opened.
  await page.locator('#closePreview').click();
  const stale=[];
  for(const mode of ['session','navigation','owner','reference','summary']){
   await show();const before={actions:actions.length,previews:previews.length,copies:await page.evaluate(()=>window.__menuCopies.length)};
   await page.evaluate(mode=>{const h=window.__menuHarness,sid=h.state.sessionId,list=h.getSessionMessages(sid),owner=list.findLast(m=>m.meta?.recordedChangeReview),ref=owner.meta.recordedChangeReview,entry=h.recordedChangeSummaries.get(ref);window.__restoreMenuOwner=()=>{h.state.sessionId=sid;owner.meta.recordedChangeReview=ref;h.recordedChangeSummaries.set(ref,entry);if(mode==='owner')list.pop();};if(mode==='session')h.state.sessionId='different-session';if(mode==='navigation')h.state._foregroundNavigationSeq=(h.state._foregroundNavigationSeq||0)+1;if(mode==='owner')list.push({role:'assistant',meta:{recordedChangeReview:{...ref}}});if(mode==='reference')owner.meta.recordedChangeReview={...ref};if(mode==='summary')h.recordedChangeSummaries.set(ref,{summary:{...entry.summary}});},mode);
   await menu.locator('[data-action="open"]').click();await page.evaluate(()=>window.__restoreMenuOwner());assert.equal(actions.length,before.actions);assert.equal(previews.length,before.previews);assert.equal(await page.evaluate(()=>window.__menuCopies.length),before.copies);stale.push(mode);
  }
  await show();await page.keyboard.press('ArrowDown');await expect(menu.locator('[data-action="open"]')).toBeFocused();await page.keyboard.press('End');await expect(menu.locator('[data-action="reveal"]')).toBeFocused();await page.keyboard.press('Escape');
  await show();await page.mouse.click(width/2,55);await expect(menu).toHaveCount(0);
  await expect(page.locator('.toast')).toHaveCount(0,{timeout:10000});
  await show();await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-menu.png`)});await page.keyboard.press('Escape');
  const boxes=[];
  for(const corner of ['bottom-right','top-left']){
   await row.evaluate((element,corner)=>element.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:corner==='bottom-right'?innerWidth-1:0,clientY:corner==='bottom-right'?innerHeight-1:0})),corner);
   const b=await menu.boundingBox();assert(b.x>=0&&b.y>=0&&b.x+b.width<=width&&b.y+b.height<=800);boxes.push(b);
   await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-${corner}.png`)});await page.keyboard.press('Escape');
  }
  // Original tree event handler reaches the same API and retains relative copy semantics.
  await page.evaluate(()=>{const h=window.__menuHarness;h.state._noProject=false;h.state._fileItems=[{name:'tree file.txt',path:'tree file.txt',type:'file',size:1}];h.filesFeature.renderFileTree();});
  const tree=page.locator('#fileTree [data-path="tree file.txt"]').first();await tree.evaluate(el=>el.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:100,clientY:100})));
  await expect(menu).toBeVisible();await menu.locator('[data-action="copy-path"]').click();const copiedTree=await page.evaluate(()=>window.__menuCopies.at(-1));assert.equal(copiedTree,host.projectDir.replaceAll('\\','/')+'/tree file.txt');
  for(const action of ['open','reveal','preview-new']){
   await tree.evaluate(el=>el.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:100,clientY:100})));
   await menu.locator(`[data-action="${action}"]`).click();
   if(action==='preview-new'){await expect.poll(()=>previews.length).toBe(2);assert.equal(previews.at(-1),'tree file.txt');await page.locator('#closePreview').click();}
   else {assert.deepEqual(actions.at(-1),action==='reveal'?{path:'tree file.txt',reveal:true}:{path:'tree file.txt'});}
  }
  // Left click still dispatches historical review, independently of the menu.
  const beforeLeft=reads.length;await row.click();await expect.poll(()=>reads.length).toBeGreaterThan(beforeLeft);await expect(menu).toHaveCount(0);
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,width,language,actions,previews,copies:await page.evaluate(()=>window.__menuCopies),stale,boxes,copiedTree,errors};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-failed.png`)}).catch(()=>{});throw error;}
 finally{await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code042-card-menu-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};console.log(dir);
 const api=async(url,body,method='POST')=>{const r=await fetch(host.ready.codeUrl+url,body?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});assert(r.ok);return r.json();};
 try{
  const session=await api('/api/sessions',{title:'Card menu fixture',cwd:host.projectDir}),binding=await api('/api/preview/context',{sessionId:session.id}),config=await api('/api/config'),rid='d'.repeat(32);
  const paths=['C:\\项目 空间\\报告 one.txt','/tmp/menu fixture/文档.txt','\\\\fixture-server\\share\\missing.txt'];
  const summary={...binding,sessionId:session.id,rootRunId:rid,originRoot:'C:\\项目 空间',revision:'fixture-revision',recordedFileCount:3,coverage:{complete:true},operations:paths.map((p,i)=>({fileKey:String(i+1).repeat(64),operationKey:'op-'+i,groupKey:'group-'+i,runId:rid,entityKind:'file',kind:i===0?'delete':'update',path:p,lineStats:{additions:1,deletions:1}}))};
  const current=await api('/api/sessions/'+session.id);await api('/api/sessions/'+session.id,{title:'Card menu fixture',expectedRevision:current.revision,messages:[{role:'user',content:'Review recorded changes'},{role:'assistant',content:'Changes recorded.',meta:{recordedChangeReview:{rootRunId:rid,recordedFileCount:3,incomplete:false,path:'C:/untrusted'}}}]},'PUT');
  browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const [width,language] of [[1280,'zh'],[390,'en']]){result.cases.push(await scenario(browser,host,{sid:session.id,rid,binding,summary,config},runtime,width,language,dir));console.log(`${runtime}/${width}/${language} passed`);}
  const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.ok=true;
 }catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
