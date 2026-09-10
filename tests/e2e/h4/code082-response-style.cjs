const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
async function scenario(browser,host,runtime,width,language,dir){
 const audit=createAudit(),errors=[],context=await createContext(browser,host,runtime,audit,{width,language,theme:language==='zh'?'light':'dark'});
 await context.addInitScript(()=>localStorage.setItem('code-temperature','0'));
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch(),source=await response.text(),needle='async function projectAgentEvent(ctx, event, snapshot = null) {';
  assert(source.includes(needle));
  await route.fulfill({response,body:source.replace(needle,`window.__styleProbe={settings:settingsFeature,build:buildModelRequestPayload,context:buildRunContext,recover:buildRecoveredRunContext,resume:resumePersistedSessionRun,resumeAll:resumePersistedRuns,background:createBackgroundServerContext,send:sendMessage,enqueue:enqueueSessionMessage,state,els,set:setSessionMessages,
   enableSyntheticRecovery(){const previous=getApiKeys,base=els.baseUrl.value;getApiKeys=()=>['synthetic-offline'];els.baseUrl.value='http://127.0.0.1';return ()=>{getApiKeys=previous;els.baseUrl.value=base;};},
   failSubmission(){const original=window.fetch;window.fetch=(url,init)=>String(url).endsWith('/api/sessions')&&init?.method==='POST'
    ? new Promise(resolve=>window.__releaseCreate=()=>resolve(new Response(JSON.stringify({error:'synthetic admission failure'}),{status:503,headers:{'Content-Type':'application/json'}}))) : original(url,init);},
   failQueue(){getModelDispatchCredentials=async()=>{throw Error('synthetic route failure');};const original=window.fetch;window.fetch=(url,init)=>String(url).includes('/api/sessions/style-owned')&&init?.method
    ? Promise.resolve(new Response(JSON.stringify({id:'style-owned',revision:1}),{headers:{'Content-Type':'application/json'}})) : original(url,init);},
  }; ${needle}`)});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  await page.evaluate(()=>window.__styleProbe.settings.openSettingsPage('models'));
  const detail=page.locator('#settingsResponseDetail'),tone=page.locator('#settingsResponseTone'),advanced=page.locator('.response-style-advanced');
  await expect(detail).toHaveValue('default');await expect(tone).toHaveValue('default');await expect(advanced).not.toHaveAttribute('open','');
  for(const d of ['default','concise','detailed'])for(const t of ['default','professional','casual']){
   await detail.selectOption(d);await tone.selectOption(t);
   assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('code-response-style'))),{version:1,detail:d,tone:t});
  }
  await advanced.locator('summary').click();await expect(page.locator('#settingsTemperature')).toHaveValue('0');
  assert(await advanced.locator('summary').evaluate(el=>{const expected=document.createElement('span');expected.style.color='var(--muted)';el.appendChild(expected);const ok=getComputedStyle(el).color===getComputedStyle(expected).color;expected.remove();return ok;}));
  await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}.png`)});
  assert(await detail.evaluate(el=>{const r=el.getBoundingClientRect();return r.width>60&&r.right<=innerWidth;}));
  // Simulate only storage failure; the real settings listener must revert UI.
  await page.evaluate(()=>{window.__originalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='code-response-style')throw Error('synthetic quota');return window.__originalSet.call(this,k,v);};});
  await detail.selectOption('concise');await expect(detail).toHaveValue('detailed');
  await expect(page.locator('#settingsResponseStyleStatus')).toHaveText(language==='zh'?'保存失败，回复风格未更改。请重试。':'Could not save. Reply preferences are unchanged. Please retry.');
  await page.evaluate(()=>Storage.prototype.setItem=window.__originalSet);
  await page.reload();await waitForRuntime(page,runtime);await page.evaluate(()=>window.__styleProbe.settings.openSettingsPage('models'));
  await expect(detail).toHaveValue('detailed');await expect(tone).toHaveValue('casual');
  const evidence=await page.evaluate(async()=>{
   const d=window.__styleProbe,p=Code.agent.systemPrompt;const original=p.readResponseStylePreference(localStorage).snapshot;
   const sid='style-owned';d.state.sessions=[{id:sid,cwd:'C:/synthetic'}];d.state.sessionId=sid;d.set(sid,[{role:'user',content:'Explain fixture'}]);
   const ctx=d.context(sid,{model:'fixture',temperature:0,responseStyle:original});ctx.projectContextResolved=true;ctx.isDetachedBackground=true;
   const first=await d.build(ctx,false);
   p.saveResponseStylePreference(localStorage,{detail:'concise',tone:'professional'});
   const again=await d.build(ctx,false);
   if(first.payload.messages[0].content!==again.payload.messages[0].content)throw Error('prompt changed');
   const restored=d.recover({id:sid,messages:d.state.messages,stats:{}},{model:'fixture',temperature:0,responseStyle:original});
   const background=d.background({id:'bg',sessionId:sid,model:'fixture',temperature:0,userText:'independent task',taskPrompt:'independent task',responseStyle:original});
   if(!background.messages[0].content.includes(original.instruction))throw Error('background style missing');
   const legacy=d.recover({id:sid,messages:[],stats:{}},{model:'fixture',temperature:0});if(legacy.responseStyle!==null)throw Error('legacy guessed');
   let unknown=false;try{d.recover({id:sid,messages:[],stats:{}},{responseStyle:{version:9}});}catch(e){unknown=e.code==='response_style_snapshot_invalid';}if(!unknown)throw Error('bad snapshot accepted');
   return {frozenPrompt:first.payload.messages[0].content,temperature:first.payload.temperature,restored:restored.responseStyle,background:true,legacy:true,unknown:true};
  });
  assert.equal(evidence.temperature,0);assert(evidence.frozenPrompt.includes('[Reply preferences]'));
  // Exercise the actual startup and submitted-input recovery entries. Bad snapshots
  // must show a localized alert before projection mutation or any server write.
  const recoveryEntries=[];
  for(const entry of ['startup','submitted-input'])for(const invalid of ['unknown','damaged']){
   const sid=`style-invalid-${entry}-${invalid}`,runId=`synthetic-${entry}-${invalid}`;
   const responseStyle=invalid==='unknown'?{version:9}:{version:2,detail:'concise',tone:'default',instruction:'damaged'};
   const fixture={id:sid,title:sid,cwd:'C:/synthetic',revision:1,messages:[{role:'user',content:'Preserve original task'}],stats:{},runState:{status:entry==='startup'?'running':'waiting-user-input',executionOwner:'server-agent',agentRunId:runId,userInputRequest:{id:'synthetic-question'},responseStyle}};
   await page.route(`**/api/sessions/${sid}`,route=>{assert.equal(route.request().method(),'GET');return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixture)});});
   const retained=await page.evaluate(async({fixture,entry})=>{
    const d=window.__styleProbe,original=JSON.stringify(fixture),before=JSON.stringify(d.state.messages);
    d.state.sessions=[fixture];d.state.sessionId='';const restore=d.enableSyntheticRecovery();
    try{if(entry==='startup')await d.resumeAll();else await d.resume(fixture,{submittedUserInput:{agentRunId:fixture.runState.agentRunId,requestId:'synthetic-question'}});}
    finally{restore();}
    return original===JSON.stringify(fixture)&&before===JSON.stringify(d.state.messages);
   },{fixture,entry});
   assert(retained,'invalid recovery changed original task/projection');
   const expected=language==='zh'?`无法恢复会话“${sid}”：保存的回复风格无法识别。原记录已保留，未使用当前设置替换。`:`Could not restore session “${sid}”: its saved reply preferences are not recognized. The original record is preserved; current settings were not substituted.`;
   await expect(page.getByRole('alert').filter({hasText:expected})).toBeVisible();
   recoveryEntries.push({entry,invalid,visible:true,preserved:true});
  }
  // A failed first submission keeps its pre-await preference on the real pending message.
  const firstFailed=await page.evaluate(async()=>{
   const d=window.__styleProbe,p=Code.agent.systemPrompt;d.state.sessionId='';d.failSubmission();
   const initial=p.readResponseStylePreference(localStorage).snapshot;
   const pending=d.send('Synthetic first task',{model:'fixture',reasoningSelection:null}).catch(()=>false);
   while(!window.__releaseCreate)await new Promise(r=>setTimeout(r,0));
   p.saveResponseStylePreference(localStorage,{detail:'detailed',tone:'casual'});window.__releaseCreate();await pending;
   const message=d.state.messages.findLast(m=>m.meta?.pendingDispatch);
   return {initial,actual:message?.meta?.pendingDispatch?.responseStyle};
  });assert.deepEqual(firstFailed.actual,firstFailed.initial);
  const queueFailed=await page.evaluate(async()=>{
   const d=window.__styleProbe,p=Code.agent.systemPrompt,sid='style-owned';d.state.sessionId=sid;d.failQueue();
   const initial=p.createResponseStyleSnapshot({detail:'concise',tone:'professional'});
   const message={id:'queue-failed',role:'user',_model:'fixture',content:'Synthetic queue task',meta:{queuedDispatch:{id:'queue-failed',status:'failed',responseStyle:initial,reasoningSelection:null}}};
   d.set(sid,[message]);await d.enqueue(sid,message.content,[],{existingMessage:message}).catch(()=>false);
   return {initial,actual:message.meta.queuedDispatch.responseStyle,status:message.meta.queuedDispatch.status};
  });assert.deepEqual(queueFailed.actual,queueFailed.initial);assert.equal(queueFailed.status,'failed');
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,width,language,nineChoices:true,storageFailure:true,reload:true,freeze:true,firstSubmissionFailure:true,background:true,oldAndInvalid:true,recoveryEntries};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-failed.png`)}).catch(()=>{});await fs.writeFile(path.join(dir,`${runtime}-${width}-${language}-failed.json`),JSON.stringify({error:String(error.stack),errors,audit},null,2));throw error;}
 finally{await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code082-r049-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};
 try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const width of [1280,390])for(const language of ['zh','en']){result.cases.push(await scenario(browser,host,runtime,width,language,dir));console.log(`${runtime}/${width}/${language} passed`);}
 const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
 }catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const cleanup=await host.stop();result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
