// Real render/event projection, isolated host, synthetic events only. Session
// checkpoint I/O is stubbed in the served fixture; backend persistence is
// covered independently by test_action_status.py.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function scenario(browser,host,runtime,width,language,dir){
 const audit=createAudit(),errors=[],context=await createContext(browser,host,runtime,audit,{width,language,theme:language==='zh'?'light':'dark'});
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch(),source=await response.text(),needle='async function projectAgentEvent(ctx, event, snapshot = null) {';
  assert(source.includes(needle));
  await route.fulfill({response,body:source.replace(needle,`window.__statusProbe={project:projectAgentEvent,render:renderMessages,patch:patchStreamingAssistantMessage,set:setSessionMessages,state,run:ensureSessionRun}; persistRunCheckpoint=async()=>true; ${needle}`)});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 await page.route('**/api/sessions/action-status-owned/generated-assets/**',route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF9sAAAAASUVORK5CYII=','base64')}));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
  await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  await page.evaluate(()=>{
   const d=window.__statusProbe,sid='action-status-owned';d.state.sessionId=sid;
   const messages=Array.from({length:6},(_,i)=>[{role:'user',content:`Earlier question ${i}`},{role:'assistant',content:'Historical context paragraph. '.repeat(45),_responseTime:'1s'}]).flat();
   messages.push({role:'user',content:'Inspect the current document'});
   const run=d.run(sid);Object.assign(run,{agentRunId:'status-run',isStreaming:true,taskStartTime:Date.now()-9000,taskElapsedBaseMs:9000,taskElapsedResumedAt:Date.now()});
   d.state._sessionRunStates[sid]={agentRunId:'status-run',status:'running',executionOwner:'server-agent'};
   const ctx={sessionId:sid,agentRunId:'status-run',messages,run,model:'fixture',agentEventCursor:0,responseUsage:{input:0,output:0,cache:0}};
   run._activeCtx=ctx;ctx._actionStatus=Code.agent.tools.createActionStatusObserver(sid,ctx.agentRunId,true);
   let seq=0;const snap={agentRunId:ctx.agentRunId,sessionId:sid,status:'tools',permissionProfile:'accept',events:[]};ctx._actionStatus.observe(snap);
   window.__statusContext=ctx;window.__statusSnapshot=snap;
   window.__statusEvent=async(type,data={})=>{await d.project(ctx,{seq:++seq,type,data,createdAt:new Date().toISOString()},snap);};
   window.__name=async(id,text,name='read_file',content='')=>window.__statusEvent('model_completed',{runtimeRunId:`model-${id}`,toolCalls:[{id,function:{name,arguments:JSON.stringify({path:'fixture.txt',_actionStatus:text})}}],content});
   window.__start=async(id,name='read_file')=>window.__statusEvent('tool_started',{toolCallId:id,name,arguments:{path:'fixture.txt'}});
   window.__finish=async(id,result={ok:true,content:'checked'},name='read_file')=>window.__statusEvent('tool_completed',{toolCallId:id,name,result,outcome:result.ok===false?'failed':'succeeded'});
   d.set(sid,messages);d.render();
  });
  const line=page.locator('[data-action-status-run]');
  await page.evaluate(()=>window.__name('a','核对文档结构，定位排版差异'));await expect(line).toHaveCount(0);
  await page.evaluate(()=>window.__start('a'));await expect(line).toHaveText('核对文档结构，定位排版差异');
  const geometry=await line.evaluate(el=>{
   window.__statusNode=el;const heading=document.querySelector('.tool-process-stage-heading'),a=el.getBoundingClientRect(),b=heading.getBoundingClientRect(),s=getComputedStyle(el),h=getComputedStyle(heading);
   return {left:el.firstElementChild.getBoundingClientRect().left,headingLeft:b.left,font:s.fontSize,headingFont:h.fontSize,line:s.lineHeight,headingLine:h.lineHeight,height:a.height,whiteSpace:s.whiteSpace,overflow:s.textOverflow};
  });
  assert.equal(geometry.font,geometry.headingFont);assert.equal(geometry.line,geometry.headingLine);assert(Math.abs(geometry.left-geometry.headingLeft)<1,'title left alignment');assert.equal(geometry.height,32);
  await page.evaluate(()=>window.__finish('a',{ok:false,error:'synthetic failure'}));await expect(line).toHaveCount(1);
  await page.evaluate(()=>window.__name('placeholder',null,'read_file','Preparing to call 2 tools'));await expect(line).toHaveText('核对文档结构，定位排版差异');
  await page.evaluate(async()=>{await window.__name('b','对照图像内容，检查布局');await window.__start('b');});
  assert(await line.evaluate(el=>el===window.__statusNode),'same footer node');
  await page.evaluate(()=>window.__finish('b',{ok:true,binary:true,visual:true,mime:'image/png',base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF9sAAAAASUVORK5CYII='}));
  await expect(page.locator('.tool-image-stage')).toHaveCount(1);
  await page.mouse.move(width/2,795);
  const idleStyle=await line.evaluate(el=>{
   const idle=document.querySelector('.tool-image-stage > summary strong'),a=getComputedStyle(el),b=getComputedStyle(idle);
   return {color:a.color,idleColor:b.color,weight:a.fontWeight,idleWeight:b.fontWeight,animation:a.animationName};
  });
  assert.equal(idleStyle.color,idleStyle.idleColor);assert.equal(idleStyle.weight,idleStyle.idleWeight);assert.equal(idleStyle.animation,'none');
  await page.evaluate(async()=>{await window.__name('c','检查修改建议，确认目标','propose_edit');await window.__start('c','propose_edit');await window.__finish('c',{ok:true,path:'fixture.txt',diff:'@@\n-old\n+new',proposalOnly:true,proposalId:'fixture'},'propose_edit');});
  await line.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-status.png`)});
  await page.evaluate(async()=>{
   window.__statusSnapshot.permissionProfile='bypass';await window.__name('image','绘制示意图，说明页面结构','generate_image');await window.__start('image','generate_image');
   await window.__finish('image',{ok:true,assets:[{assetId:'ga1_'+'a'.repeat(32),mimeType:'image/png',width:1,height:1,byteLength:68}]},'generate_image');window.__statusSnapshot.permissionProfile='accept';
  });
  await expect(page.locator('[data-generated-image-gallery]')).toHaveCount(1);
  // The ordinary read action's label remains until a genuine text boundary.
  await expect(line).toHaveCount(1);assert(await line.evaluate(el=>[...document.querySelectorAll('.tool-process,.edit-suggestion,[data-generated-image-gallery]')].every(x=>x.getBoundingClientRect().bottom<=el.getBoundingClientRect().top+1)));
  await line.scrollIntoViewIfNeeded();
  const before=await line.evaluate(el=>({text:el.textContent,html:el.outerHTML}));await line.hover();await line.click();assert.deepEqual(await line.evaluate(el=>({text:el.textContent,html:el.outerHTML})),before);
  assert.equal(await line.evaluate(el=>getComputedStyle(el).color),idleStyle.color);
  assert.equal(await line.locator('button,a,summary,[title],[tabindex],svg').count(),0);assert.equal(await line.getAttribute('title'),null);
  await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}.png`)});
  // Replacement, including markup-looking plain text, preserves node and
  // scroll position while the reader is inspecting earlier content.
  await page.locator('#messages').hover();await page.mouse.wheel(0,-850);await page.waitForTimeout(120);
  const scrollBefore=await page.locator('#messages').evaluate(el=>el.scrollTop);
  await page.evaluate(async()=>{await window.__name('long','<b>**Checking**</b> '+ 'x'.repeat(56));await window.__start('long');});
  await page.waitForTimeout(80);assert(Math.abs(await page.locator('#messages').evaluate(el=>el.scrollTop)-scrollBefore)<2);
  await expect(line).toContainText('<b>**Checking**</b>');assert.equal(await line.locator('b').count(),0);
  if(width===390)assert(await line.locator('span').evaluate(el=>el.scrollWidth>el.clientWidth),'narrow overflow uses ellipsis');
  await page.evaluate(()=>window.__messageScroller.forceToLatest(window.__statusContext.sessionId));
  await page.evaluate(async()=>{await window.__name('follow','继续核对结果，确认版面一致');await window.__start('follow');});
  await expect.poll(()=>page.locator('#messages').evaluate(el=>Math.abs(el.scrollHeight-el.clientHeight-el.scrollTop))).toBeLessThan(2);
  await page.evaluate(()=>{const d=window.__statusProbe,ctx=window.__statusContext;ctx.messages.push({role:'assistant',content:'New stage explanation',streaming:true,_streamProjection:'pending',meta:{agentRunId:ctx.agentRunId,agentRuntimeRunId:'model-follow'}});d.patch(ctx.sessionId,ctx.messages.length-1);});
  await expect(line).toHaveCount(0);
  await page.evaluate(async()=>{window.__statusContext.messages.at(-1).streaming=false;await window.__name('wait','Inspecting next step');await window.__start('wait');});await expect(line).toHaveCount(1);
  for(const status of ['waiting_authorization','waiting_user_input','waiting_credentials','waiting_recovery','waiting_skill_evidence','failed','cancelled','completed']){
   await page.evaluate(status=>{const ctx=window.__statusContext;ctx._actionStatus.observe({...window.__statusSnapshot,status});window.__statusProbe.render();},status);await expect(line).toHaveCount(0);
   await page.evaluate(()=>{window.__statusContext._actionStatus.observe(window.__statusSnapshot);window.__statusProbe.render();});await expect(line).toHaveCount(0);
  }
  await page.evaluate(async()=>{
   const ctx=window.__statusContext,d=window.__statusProbe;ctx.agentRunId='new-status-run';ctx.run.agentRunId=ctx.agentRunId;
   window.__statusSnapshot.agentRunId=ctx.agentRunId;d.state._sessionRunStates[ctx.sessionId].agentRunId=ctx.agentRunId;
   ctx._actionStatus=Code.agent.tools.createActionStatusObserver(ctx.sessionId,ctx.agentRunId,true);ctx._actionStatus.observe(window.__statusSnapshot);
   await window.__name('fresh','Freshly checking context');await window.__start('fresh');
  });await expect(line).toHaveCount(1);
  await page.evaluate(()=>{const d=window.__statusProbe;d.state.sessionId='another-session';d.set('another-session',[{role:'user',content:'Other task'}]);d.render();d.state.sessionId=window.__statusContext.sessionId;d.set(d.state.sessionId,window.__statusContext.messages);d.render();});await expect(line).toHaveCount(0);
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,width,language,geometry,idleStyle,defaultProfile:'accept',sameNode:true,scrollPreserved:true,waitingAndTerminalHidden:true,errors};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-failed.png`)}).catch(()=>{});await fs.writeFile(path.join(dir,`${runtime}-${width}-${language}-failed.json`),JSON.stringify({error:String(error.stack),errors,blocked:audit.blockedWrites,body:await page.locator('body').innerText()},null,2));throw error;}
 finally{await page.evaluate(()=>{const d=window.__statusProbe;if(d){const ctx=window.__statusContext;if(ctx){ctx.run.isStreaming=false;ctx.run._activeCtx=null;}d.state.sessionId='';}}).catch(()=>{});await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code079-r043-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};
 try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const width of [1280,390])for(const language of ['zh','en']){result.cases.push(await scenario(browser,host,runtime,width,language,dir));console.log(`${runtime}/${width}/${language} passed`);}
  const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
 }catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const cleanup=await host.stop();result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
 console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
