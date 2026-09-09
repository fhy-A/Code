const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
async function scenario(browser,host,runtime,theme,width,dir){
 const language=runtime==='bundle'?'zh':'en',audit=createAudit(),context=await createContext(browser,host,runtime,audit,{width,theme,language}),errors=[];
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch(),source=await response.text(),needle='function projectAgentToolCompleted(ctx, event) {';assert(source.includes(needle));
  await route.fulfill({response,body:source.replace(needle,'window.__code087={complete:projectAgentToolCompleted,render:renderMessages,set:setSessionMessages,state,run:ensureSessionRun}; '+needle)});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
 const install=async historical=>page.evaluate(historical=>{
  const d=window.__code087;d.state.sessionId='code087-owned-ui';d.run(d.state.sessionId).isStreaming=false;
  const ctx={agentRunId:'code087-synthetic-run',sessionId:d.state.sessionId,messages:[{role:'user',content:'检查文件工具失败显示'}]};
  let seq=0;
  const finish=(id,result,proposal)=>{
   ctx.messages.push({role:'tool-call',content:'',meta:{agentRunId:ctx.agentRunId,action:result.action,toolCallId:id,tool:{action:result.action}}});
   if(proposal)ctx.messages.push({role:'tool-result',content:'--- a/'+proposal.path+'\n+++ b/'+proposal.path+'\n@@ -1 +1 @@\n-old\n+new',meta:{action:result.action,path:proposal.path,agentRunId:ctx.agentRunId,toolCallId:id,pendingEditId:'real-'+id,authorizationId:'auth-'+id,authorizationDecision:'approved',serverManaged:true,...proposal}});
   const event={seq:++seq,data:{toolCallId:id,name:result.action,outcome:result.ok===false?'failed':'succeeded',result}};
   d.complete(ctx,event);d.complete(ctx,event);
  };
  finish('parse-failed',{ok:false,action:'write_file',errorCode:'invalid_tool_arguments',error:'Unterminated string starting at: line 1 column 41 (char 40)'});
  finish('validation-failed',{ok:false,action:'write_file',errorCode:'invalid_tool_arguments',error:'path is required'});
  finish('io-failed',{ok:false,action:'write_file',error:'Access denied'});
  finish('proposal-failed',{ok:false,action:'write_file',error:'File changed before writing',applied:false},{path:'proposal.txt'});
  finish('write-success',{ok:true,action:'write_file',path:'created.svg',diff:'--- /dev/null\n+++ b/created.svg\n@@ -0,0 +1 @@\n+svg'});
  finish('user-rejected',{ok:false,action:'write_file',path:'declined.txt',error:'User declined',rejected:true},{path:'declined.txt',authorizationDecision:'rejected'});
  finish('rejection-without-proposal',{ok:false,action:'write_file',error:'User declined without a proposal',rejected:true});
  if(historical){for(const m of ctx.messages)if(m.role==='tool-result'&&['parse-failed','validation-failed','io-failed','rejection-without-proposal'].includes(m.meta.toolCallId))Object.assign(m.meta,{pendingEditId:'old-'+m.meta.toolCallId,serverManaged:true,applied:false,rejected:false});}
  window.__code087Snapshot=JSON.stringify(ctx.messages);d.set(d.state.sessionId,JSON.parse(window.__code087Snapshot));d.render();
  return {messages:ctx.messages.length,resultCount:ctx.messages.filter(m=>m.role==='tool-result').length};
 },historical);
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  const verify=async()=>{
   await expect(page.locator('.edit-suggestion')).toHaveCount(3);
   for(const id of ['parse-failed','validation-failed','io-failed']){
    const item=page.locator(`.tool-process-item[data-tool-call-id="${id}"]`);await expect(item).toHaveCount(1);await expect(item).toHaveClass(/failed/);
   }
   for(const stage of await page.locator('details.tool-process-stage').all())if(await stage.getAttribute('open')===null)await stage.locator(':scope > summary').click();
   const error=page.locator('.tool-process-item[data-tool-call-id="parse-failed"]');if(await error.getAttribute('open')===null)await error.locator('summary').click();
   await expect(error.locator('.tool-process-body')).toBeVisible();await expect(error.locator('.tool-process-body')).toContainText('Unterminated string');
   const cards=page.locator('.edit-suggestion');assert(!(await cards.allTextContents()).some(text=>/未命名文件|Untitled file/.test(text)));
   const statuses=await cards.locator('.tool-edit-status').allTextContents();
   assert.deepEqual(statuses,language==='zh'?['失败','已应用','已拒绝']:['Failed','Applied','Rejected']);
   assert.equal(await cards.locator('.apply-edit-btn').count(),0);assert(!(await cards.allTextContents()).some(text=>text.includes('+1 lines')));assert.equal(await page.locator('.tool-edit-status').filter({hasText:/等待批准|Waiting for approval/}).count(),0);
  };
  const live=await install(false);assert.equal(live.resultCount,7);await verify();
  const historical=await install(true);assert.equal(historical.resultCount,7);await verify();
  assert.equal(await page.evaluate(()=>JSON.stringify(window.__code087.state.messages)===window.__code087Snapshot),true);
  await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}.png`)});
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,theme,width,language,live,historical,editCards:3,failedCalls:4,errorVisible:true,duplicateEventSafe:true,historyUnchanged:true,errors};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}-failed.png`)}).catch(()=>{});await fs.writeFile(path.join(dir,`${runtime}-${theme}-${width}-failed.json`),JSON.stringify({error:String(error.stack),errors,blockedWrites:audit.blockedWrites,body:await page.locator('body').innerText()},null,2));throw error;
 }finally{await page.evaluate(()=>{if(window.__code087?.state.sessionId==='code087-owned-ui')window.__code087.state.sessionId=''}).catch(()=>{});await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code087-r027-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};
 try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const theme of ['light','dark'])for(const width of [1280,390]){result.cases.push(await scenario(browser,host,runtime,theme,width,dir));console.log(`${runtime} ${theme} ${width} passed`)}
 const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
 }catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;
 }finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
 console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1});
