const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
const baseline=process.argv.includes('--baseline');
const baselineRoot=path.join(os.tmpdir(),'code079-r044-baseline');
async function scenario(browser,host,runtime,width,language,dir){
 const audit=createAudit(),errors=[],context=await createContext(browser,host,runtime,audit,{width,language,theme:language==='en'?'dark':'light'});
 await context.route(/\/(?:app\.js|code\.bundle\.js|styles\.css|src\/ui\/messages\.js)$/,async route=>{
  const response=await route.fetch(),url=new URL(route.request().url());
  let source=baseline?await fs.readFile(path.join(baselineRoot,url.pathname.endsWith('/code.bundle.js')?'code.bundle.js':url.pathname.slice(1)),'utf8'):await response.text();
  if(/\/(?:app\.js|code\.bundle\.js)$/.test(url.pathname)){
   const needle='function renderMessages() {';assert(source.includes(needle));
   source=source.replace(needle,`window.__innerProbe={render:renderMessages,state,run:ensureSessionRun}; ${needle}`);
   source=source.replace('  reconcileToolProcessNodes(els.messageList, projectedMessageList);','  window.__innerCapture?.("before-reconcile"); reconcileToolProcessNodes(els.messageList, projectedMessageList); window.__innerCapture?.("after-reconcile");');
   source=source.replace('  const toolProcessReconciliation = reconcileToolProcessNodes(els.messageList, projectedMessageList);','  window.__innerCapture?.("before-reconcile"); const toolProcessReconciliation = reconcileToolProcessNodes(els.messageList, projectedMessageList); window.__innerCapture?.("after-reconcile");');
   source=source.replace('  toolProcessReconciliation.restoreScroll?.();','  toolProcessReconciliation.restoreScroll?.(); window.__innerCapture?.("after-restore");');
   source=source.replace('  toolProcessReconciliation?.restoreScroll?.();','  toolProcessReconciliation?.restoreScroll?.(); window.__innerCapture?.("after-restore");');
   // Keep the actual product reconciliation call intact in both versions.
   source=source.replace('  els.messageList.replaceChildren(...Array.from(projectedMessageList.childNodes));','  els.messageList.replaceChildren(...Array.from(projectedMessageList.childNodes)); window.__innerCapture?.("after-attach");');
  }
  await route.fulfill({response,body:source});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  await page.evaluate(()=>{
   const d=window.__innerProbe,sid='internal-scroll-owned',runId='run-a';d.state.sessionId=sid;
   const longOutput=Array.from({length:50},(_,i)=>`line ${i}: `+'w'.repeat(70)).join('\n');
   const calls=(prefix,count)=>Array.from({length:count},(_,i)=>[
    {role:'tool-call',meta:{agentRunId:runId,toolCallId:`${prefix}${i}`,action:'read_file',tool:{action:'read_file',path:'same-long-directory/'.repeat(9)+'fixture.txt'}}},
    ...(i===0?[]:[{role:'tool-result',content:i===5?longOutput:'read',meta:{agentRunId:runId,toolCallId:`${prefix}${i}`,action:'read_file',result:{ok:i!==1,content:'read'},outcome:i===1?'failed':'succeeded'}}]),
   ]).flat();
   window.__innerMessages=[{role:'user',content:'Review the collected evidence'},...calls('a',36),{role:'assistant',content:'Checking the next group',meta:{publicProcessCommentary:true,agentRunId:runId}},...calls('b',32)];
   d.state.messages=window.__innerMessages;Object.assign(d.run(sid),{agentRunId:runId,isStreaming:true,taskStartTime:Date.now()-6000});d.state._sessionRunStates[sid]={agentRunId:runId,status:'running'};
   window.__innerRender=()=>{d.state.messages=window.__innerMessages;d.state._lastRenderedHtml=null;d.render();};window.__innerRender();
   window.__stages=()=>[...document.querySelectorAll('details.tool-process-stage')];
   window.__item=id=>document.querySelector(`details.tool-process-item[data-tool-call-id="${id}"]`);
   window.__geometry=id=>{
    const item=window.__item(id),summary=item.querySelector(':scope > summary'),r=summary.getBoundingClientRect(),style=getComputedStyle(summary);
    const box=selector=>{const e=summary.querySelector(selector),b=e.getBoundingClientRect();return {x:b.left-r.left,y:b.top-r.top,w:b.width,h:b.height,cx:(b.left+b.right)/2-r.left};};
    return {height:r.height,width:r.width,padding:style.padding,gap:style.gap,dot:box('.tool-process-indicator'),heading:box('.tool-process-row-heading'),outcome:box('.tool-process-outcome'),arrow:box('.tool-process-chevron')};
   };
   window.__result=(id,outcome)=>{
    window.__innerMessages=window.__innerMessages.filter(m=>!(m.role==='tool-result'&&m.meta.toolCallId===id));
    const index=window.__innerMessages.findIndex(m=>m.role==='tool-call'&&m.meta.toolCallId===id);
    if(outcome!=='running')window.__innerMessages.splice(index+1,0,{role:'tool-result',content:'read',meta:{agentRunId:'run-a',toolCallId:id,action:'read_file',outcome,result:{ok:outcome==='succeeded',content:'read'}}});
    window.__innerRender();
   };
   window.__stages().forEach(s=>s.open=true);window.__item('a5').open=true;window.__item('b5').open=true;
   window.__innerLog=[];
   window.__innerCapture=phase=>window.__innerLog.push({phase,points:(window.__pointRefs||[]).map(e=>({top:e.scrollTop,left:e.scrollLeft,connected:e.isConnected}))});
   window.__points=()=>[window.__stages()[0].querySelector('.tool-process-stage-body'),window.__stages()[1].querySelector('.tool-process-stage-body'),window.__item('a5').querySelector('.tool-process-body'),window.__item('b5').querySelector('.tool-process-body')];
   window.__position=mode=>{const points=window.__points();points.forEach((e,i)=>{e.scrollTop=mode==='bottom'?e.scrollHeight:(i+1)*45;});window.__pointRefs=points;return points.map(e=>({top:e.scrollTop,left:e.scrollLeft,max:e.scrollHeight-e.clientHeight}));};
   window.__readPositions=()=>window.__points().map((e,i)=>({top:e.scrollTop,left:e.scrollLeft,max:Math.max(0,e.scrollHeight-e.clientHeight),same:e===window.__pointRefs[i]}));
  });
  const geometry={};for(const outcome of ['pending','running','succeeded','failed','cancelled','completed','interrupted']){
   await page.evaluate(outcome=>window.__result('a0',outcome),outcome);geometry[outcome]=await page.evaluate(()=>window.__geometry('a0'));
  }
  const crossRows=await page.evaluate(()=>({success:window.__geometry('a2'),failed:window.__geometry('a1')}));
  const groupBody=page.locator('details.tool-process-stage').last().locator(':scope > .tool-process-stage-body');
  await groupBody.scrollIntoViewIfNeeded();await groupBody.evaluate(e=>e.scrollTop=40);
  const wheelBox=await groupBody.boundingBox();await page.mouse.move(wheelBox.x+wheelBox.width/2,Math.max(55,wheelBox.y)+20);await page.mouse.wheel(0,100);
  await expect.poll(()=>groupBody.evaluate(e=>e.scrollTop)).toBeGreaterThan(40);
  const wheelPosition=await groupBody.evaluate(e=>e.scrollTop);await page.mouse.move(width/2,795);
  const updates=[];
  for(const mode of ['middle','bottom']){
   const before=await page.evaluate(mode=>window.__position(mode),mode);assert(before.every(e=>e.top>0),'all nested regions really scroll');
   const identities=await page.evaluate(()=>{window.__stageRefs=window.__stages();window.__itemRefs=[window.__item('a5'),window.__item('b5')];return true;});
   await page.evaluate(()=>{window.__innerLog=[];window.__innerMessages.push({role:'tool-call',meta:{agentRunId:'run-a',toolCallId:'new-'+window.__innerMessages.length,action:'read_file',tool:{action:'read_file',path:'new.txt'}}});window.__innerRender();});
   const after=await page.evaluate(()=>window.__readPositions()),timing=await page.evaluate(()=>window.__innerLog);
   const same=await page.evaluate(()=>window.__stages().every((s,i)=>s===window.__stageRefs[i]&&s.open)&&['a5','b5'].every((id,i)=>window.__item(id)===window.__itemRefs[i]&&window.__item(id).open));assert(same);
   updates.push({mode,before,after,timing});
  }
  const folded=await page.evaluate(async()=>{
   const before=window.__position('middle');await new Promise(requestAnimationFrame);
   window.__stages()[0].open=false;window.__innerRender();window.__stages()[0].open=true;await new Promise(requestAnimationFrame);
   return {before,after:window.__readPositions()};
  });
  const parentCompletion=await page.evaluate(()=>{
   const sample=()=>{const stage=window.__stages()[0],body=stage.querySelector('.tool-process-stage-body'),row=window.__item('a2').querySelector('summary').getBoundingClientRect(),r=body.getBoundingClientRect();return {className:stage.className,left:row.left,top:row.top,anchorTop:row.top-r.top,scrollTop:body.scrollTop,margin:getComputedStyle(body).margin,padding:getComputedStyle(body).padding};};
   const before=sample();window.__innerMessages.forEach(m=>{if(m.role==='tool-result'&&m.meta.toolCallId.startsWith('a')){m.meta.outcome='succeeded';m.meta.result.ok=true;}});window.__innerRender();return {before,after:sample()};
  });assert(parentCompletion.after.className.includes('succeeded'));
  // Product pre-wrap normally avoids horizontal overflow. This fixture-only
  // presentation variant supplies genuine nonzero native scrollLeft values;
  // the product reconciliation itself is never modified to manufacture loss.
  await page.addStyleTag({content:'.tool-process-detail pre { white-space:pre; overflow:auto; max-height:80px; }'});
  const detailScroll=await page.evaluate(async()=>{
   const pre=()=>window.__item('a5').querySelectorAll('.tool-process-detail pre')[1];
   let node=pre();node.scrollLeft=140;node.scrollTop=70;await new Promise(requestAnimationFrame);
   const before={left:node.scrollLeft,top:node.scrollTop};window.__innerRender();node=pre();
   return {before,after:{left:node.scrollLeft,top:node.scrollTop}};
  });assert(detailScroll.before.left>0&&detailScroll.before.top>0);
  const shrink=await page.evaluate(()=>{
   const before=window.__position('bottom');
   window.__innerMessages.find(m=>m.role==='tool-result'&&m.meta.toolCallId==='a5').content='short';window.__innerRender();
   const pre=window.__item('a5').querySelectorAll('.tool-process-detail pre')[1];
   return {before,after:window.__readPositions(),pre:{left:pre.scrollLeft,top:pre.scrollTop,maxLeft:pre.scrollWidth-pre.clientWidth,maxTop:pre.scrollHeight-pre.clientHeight}};
  });
  const focused=await page.evaluate(()=>{
   const summary=window.__item('a4').querySelector('summary');summary.focus({preventScroll:true});window.__innerRender();
   return document.activeElement===summary;
  });
  await page.locator('[data-tool-call-id="a4"] > summary').press('Space');assert(await page.locator('[data-tool-call-id="a4"]').evaluate(e=>e.open));
  await page.locator('[data-tool-call-id="a4"] > summary').press('Enter');assert(!(await page.locator('[data-tool-call-id="a4"]').evaluate(e=>e.open)));
  const isolation=await page.evaluate(()=>{
   window.__position('middle');const oldB=window.__points()[1].scrollTop;
   window.__innerMessages.forEach(m=>{if(m.meta?.toolCallId?.startsWith('a'))m.meta.agentRunId='different-run';});window.__innerRender();window.__stages()[0].open=true;
   const changedRun={newTop:window.__points()[0].scrollTop,otherTop:window.__points()[1].scrollTop,oldOtherTop:oldB};
   const d=window.__innerProbe;d.state.sessionId='other-internal-session';Object.assign(d.run(d.state.sessionId),{isStreaming:true,taskStartTime:Date.now()-5000,agentRunId:'different-run'});d.state._sessionRunStates[d.state.sessionId]={agentRunId:'different-run',status:'running'};
   window.__innerRender();window.__stages().forEach(s=>s.open=true);
   return {changedRun,newSessionTops:window.__stages().map(s=>s.querySelector('.tool-process-stage-body').scrollTop)};
  });
  await page.evaluate(()=>{const result=window.__innerMessages.find(m=>m.role==='tool-result'&&m.meta.toolCallId==='a1');result.meta.outcome='failed';result.meta.result.ok=false;window.__innerRender();window.__stages().forEach(s=>s.open=true);});
  await page.locator('details.tool-process-stage').first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}.png`)});
  if(baseline){assert.notEqual(geometry.running.height,geometry.succeeded.height);assert(updates.some(u=>u.after.some((p,i)=>u.before[i].top>0&&p.top===0)),'R043 must reproduce real scroll loss');}
  else{
   for(const [state,g] of Object.entries(geometry))for(const field of ['height','padding','gap'])assert.equal(g[field],geometry.succeeded[field],`${state}/${field}`);
   for(const [state,g] of Object.entries(geometry))for(const part of ['dot','heading','outcome','arrow'])for(const axis of ['x','y','w','h'])assert(Math.abs(g[part][axis]-geometry.succeeded[part][axis])<0.6,`${state}/${part}/${axis}`);
   assert(Math.abs(crossRows.success.dot.cx-crossRows.failed.dot.cx)<0.6);assert(Math.abs(crossRows.success.heading.x-crossRows.failed.heading.x)<0.6);
   for(const update of updates)update.after.forEach((p,i)=>assert(Math.abs(p.top-Math.min(update.before[i].top,p.max))<1,`${update.mode} region ${i} kept scroll`));
   folded.after.forEach((p,i)=>assert(Math.abs(p.top-Math.min(folded.before[i].top,p.max))<1,`reopen region ${i} kept scroll`));
   assert.deepEqual(detailScroll.after,detailScroll.before);assert(focused,'focused summary survives reattachment');
   shrink.after.forEach((p,i)=>assert(Math.abs(p.top-Math.min(shrink.before[i].top,p.max))<1,`shortened region ${i} clamps`));
   assert.equal(shrink.pre.left,0);assert.equal(shrink.pre.top,0);
   assert.equal(isolation.changedRun.newTop,0);assert.equal(isolation.changedRun.otherTop,isolation.changedRun.oldOtherTop);assert(isolation.newSessionTops.every(top=>top===0));
   for(const axis of ['left','top','anchorTop','scrollTop'])assert(Math.abs(parentCompletion.after[axis]-parentCompletion.before[axis])<1,`parent completion ${axis} stable`);
  }
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,width,language,geometry,crossRows,wheelPosition,updates,folded,parentCompletion,detailScroll,shrink,focused,isolation,errors};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${width}-${language}-failed.png`)}).catch(()=>{});await fs.writeFile(path.join(dir,'failure.json'),JSON.stringify({error:String(error.stack),errors,log:await page.evaluate(()=>window.__innerLog).catch(()=>null),positions:await page.evaluate(()=>window.__readPositions()).catch(()=>null)},null,2));throw error;}
 finally{await page.evaluate(()=>{const d=window.__innerProbe;if(d){d.run(d.state.sessionId).isStreaming=false;d.state.sessionId='';}}).catch(()=>{});await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),baseline?'code079-r044-before-':'code079-r044-after-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,baseline,cases:[]};console.log(dir);
 try{browser=await chromium.launch({headless:true});for(const runtime of baseline?['classic']:['bundle','classic'])for(const width of [1280,390])for(const language of ['zh','en']){result.cases.push(await scenario(browser,host,runtime,width,language,dir));console.log(`${runtime}/${width}/${language} passed`);}const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.ok=true;}
 catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const clean=await host.stop();result.cleanup={childExited:clean.childExited,portsClosed:clean.portsClosed,rootRemoved:clean.rootRemoved,errors:clean.cleanupErrors,activeChildren:getActiveChildCount()};if(!clean.childExited||!clean.rootRemoved||!clean.portsClosed.every(Boolean)||clean.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify({dir,ok:result.ok,error:result.error,cleanup:result.cleanup}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
