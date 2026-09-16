// Actual production projection and reconciliation, synthetic in-memory messages.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
async function scenario(browser,host,runtime,width,language,dir){
 const audit=createAudit(),errors=[],context=await createContext(browser,host,runtime,audit,{width,language,theme:language==='en'?'dark':'light'});
 // Preview startup binding is outside this in-memory trace fixture.
 await context.route('**/api/preview/context',route=>{const body=route.request().postDataJSON();return route.fulfill({json:{dataSourceId:'trace-fixture',sessionId:body.sessionId,sessionInstanceId:'trace-fixture',draftId:body.draftId,contextRevision:'fixture',serverInstanceId:'fixture'}});});
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch(),source=await response.text(),needle='function renderMessages() {';assert(source.includes(needle));
  await route.fulfill({response,body:source.replace(needle,`window.__trace={render:renderMessages,state,run:ensureSessionRun}; ${needle}`)});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  await page.evaluate(()=>{
   const d=window.__trace,sid='image-trace-owned',runId='trace-run';d.state.sessionId=sid;
   window.__visual={ok:true,action:'read_file',binary:true,visual:true,mime:'image/png',base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF9sAAAAASUVORK5CYII=',path:'fixture.png'};
   window.__record=(id,image=false,pending=false,run=runId)=>[{role:'tool-call',meta:{agentRunId:run,toolCallId:id,action:image?'read_file':'run_command',tool:{action:image?'read_file':'run_command',path:image?'fixture.png':undefined,command:'inspect '+id}}},...(pending?[]:[{role:'tool-result',content:Array.from({length:65},(_,i)=>`line ${i} `+'x'.repeat(60)).join('\n'),meta:{agentRunId:run,toolCallId:id,action:image?'read_file':'run_command',outcome:'succeeded',result:image?window.__visual:{ok:true}}}])];
   window.__messages=[{role:'user',content:'Inspect images between tool calls'},...window.__record('lead'),...window.__record('image',true,true),...window.__record('tail')];
   Object.assign(d.run(sid),{agentRunId:runId,isStreaming:true,taskStartTime:Date.now()});d.state._sessionRunStates[sid]={agentRunId:runId,status:'running'};
   window.__render=()=>{d.state.messages=window.__messages;d.state._lastRenderedHtml=null;d.render();};
   window.__item=id=>document.querySelector(`details.tool-process-item[data-tool-call-id="${id}"]`);
   window.__order=()=>[...document.querySelectorAll('details.tool-process-item')].map(e=>e.dataset.toolCallId);
   window.__groups=()=>[...document.querySelectorAll('details.tool-process-stage')];window.__render();
  });
  const pending=await page.evaluate(()=>{const g=window.__groups();g[0].open=true;const item=window.__item('tail');item.open=true;window.__tail=item;window.__lead=window.__item('lead');item.querySelector('.tool-process-body').scrollTop=80;return {order:window.__order(),groups:g.length,top:item.querySelector('.tool-process-body').scrollTop};});
  assert.equal(pending.groups,1);assert(pending.top>0);
  const split=await page.evaluate(()=>{window.__messages.splice(4,0,window.__record('image',true)[1]);window.__render();const item=window.__item('tail');return {order:window.__order(),kinds:window.__groups().map(e=>e.classList.contains('tool-image-stage')),same:item===window.__tail,open:item.open,top:item.querySelector('.tool-process-body').scrollTop};});
  assert.deepEqual(split.order,['lead','image','tail']);assert.deepEqual(split.kinds,[false,true,false]);assert(split.same&&split.open,'split keeps later item node and expansion');
  await page.evaluate(()=>window.__groups()[2].open=true);
  await expect.poll(()=>page.evaluate(()=>window.__item('tail').querySelector('.tool-process-body').scrollTop)).toBe(pending.top);
  const append=await page.evaluate(()=>{window.__groups()[0].open=false;window.__messages.push(...window.__record('next'),...window.__record('last-image',true));window.__render();return {order:window.__order(),ids:window.__groups().map(e=>e.dataset.toolProcessId),firstOpen:window.__groups()[0].open,tailOpen:window.__groups()[2].open,same:window.__item('tail')===window.__tail};});
  assert.deepEqual(append.order,['lead','image','tail','next','last-image']);assert.equal(new Set(append.ids).size,4);assert(!append.firstOpen&&append.tailOpen&&append.same);
  const preview=page.locator('[data-tool-image-preview]').first();await preview.click();await expect(page.locator('#imageOverlay')).toBeVisible();await page.keyboard.press('Escape');
  await page.evaluate(()=>{window.__item('tail').open=false;document.querySelector('#messages').scrollTop=0;});
  await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-live.png`),fullPage:true});
  const history=await page.evaluate(()=>{const d=window.__trace;d.run(d.state.sessionId).isStreaming=false;d.state._sessionRunStates[d.state.sessionId].status='completed';window.__messages=JSON.parse(JSON.stringify(window.__messages));document.querySelector('#messageList').replaceChildren();window.__render();return {order:window.__order(),kinds:window.__groups().map(e=>e.classList.contains('tool-image-stage'))};});
  assert.deepEqual(history.order,append.order);assert.deepEqual(history.kinds,[false,true,false,true]);
  await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-history.png`),fullPage:true});
  const leadingImage=await page.evaluate(()=>{
   const d=window.__trace;d.run(d.state.sessionId).isStreaming=true;d.state._sessionRunStates[d.state.sessionId].status='running';
   window.__messages=[{role:'user',content:'Leading pending image'},window.__record('first',true,true)[0],...window.__record('between'),...window.__record('final',true)];window.__render();window.__groups()[0].open=true;
   const item=window.__item('between');item.open=true;item.querySelector('.tool-process-body').scrollTop=75;
   window.__messages.splice(2,0,window.__record('first',true)[1]);window.__render();
   return {order:window.__order(),kinds:window.__groups().map(s=>s.classList.contains('tool-image-stage')),same:window.__item('between')===item,open:item.open,groupOpen:window.__groups()[1].open,top:item.querySelector('.tool-process-body').scrollTop};
  });assert.deepEqual(leadingImage.order,['first','between','final']);assert.deepEqual(leadingImage.kinds,[true,false,true]);assert(leadingImage.same&&leadingImage.open&&leadingImage.groupOpen);assert.equal(leadingImage.top,75);
  const isolation=await page.evaluate(()=>{
   const d=window.__trace;d.run(d.state.sessionId).isStreaming=true;d.state._sessionRunStates[d.state.sessionId].status='running';
   window.__messages=[{role:'user',content:'Independent segment scroll'},...Array.from({length:18},(_,i)=>window.__record('a'+i)).flat(),...window.__record('image-a',true),...Array.from({length:18},(_,i)=>window.__record('b'+i)).flat(),...window.__record('image-b',true)];window.__render();
   const stages=window.__groups();stages.forEach(s=>s.open=true);stages[1].open=false;
   const bodies=[stages[0],stages[2]].map(s=>s.querySelector('.tool-process-stage-body'));bodies.forEach((b,i)=>b.scrollTop=60+i*50);const before=bodies.map(b=>b.scrollTop);
   window.__messages.push(...window.__record('image-c',true));window.__render();
   const after=[window.__groups()[0],window.__groups()[2]].map(s=>s.querySelector('.tool-process-stage-body').scrollTop);
   const independent=!window.__groups()[1].open&&window.__groups()[3].open;
   const item=window.__item('b3');item.open=true;
   window.__messages=window.__messages.map(m=>m.meta?{...m,meta:{...m.meta,agentRunId:'different-run'}}:m);d.run(d.state.sessionId).agentRunId='different-run';d.state._sessionRunStates[d.state.sessionId].agentRunId='different-run';window.__render();
   const differentRun=window.__item('b3')!==item&&!window.__item('b3').open;
   const previous=window.__item('b3');previous.open=true;d.state.sessionId='different-session';Object.assign(d.run(d.state.sessionId),{agentRunId:'different-run',isStreaming:true});d.state._sessionRunStates[d.state.sessionId]={agentRunId:'different-run',status:'running'};window.__render();
   const differentSession=window.__item('b3')!==previous&&!window.__item('b3').open;
   return {before,after,independent,differentRun,differentSession};
  });assert(isolation.before.every(n=>n>0));assert.deepEqual(isolation.after,isolation.before);assert(isolation.independent&&isolation.differentRun&&isolation.differentSession);
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);return {runtime,width,language,pending,split,append,history,leadingImage,isolation,errors};
 }catch(e){await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-failed.png`)}).catch(()=>{});throw e;}
 finally{await page.evaluate(()=>{const d=window.__trace;if(d){d.run(d.state.sessionId).isStreaming=false;d.state.sessionId='';}}).catch(()=>{});await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code109-image-trace-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};console.log(dir);
 try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const [width,language] of [[1280,'zh'],[390,'en']]){result.cases.push(await scenario(browser,host,runtime,width,language,dir));console.log(`${runtime}/${width}/${language} passed`);}const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.ok=true;}
 catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
