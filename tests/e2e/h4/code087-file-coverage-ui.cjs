const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function scenario(browser,host,runtime,language,width,dir){
 const theme=language==='zh'?'light':'dark',audit=createAudit(),errors=[];
 const context=await createContext(browser,host,runtime,audit,{width,theme,language});
 await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
  const response=await route.fetch(),source=await response.text(),needle='function projectAgentToolCompleted(ctx, event) {';
  assert(source.includes(needle));
  await route.fulfill({response,body:source.replace(needle,'window.__coverageProbe={complete:projectAgentToolCompleted,render:renderMessages,set:setSessionMessages,state,run:ensureSessionRun}; '+needle)});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
 try{
  await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
  await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
  const installed=await page.evaluate(()=>{
   const d=window.__coverageProbe;d.state.sessionId='coverage-owned-ui';d.run(d.state.sessionId).isStreaming=false;
   const ctx={agentRunId:'coverage-synthetic-run',sessionId:d.state.sessionId,messages:[{role:'user',content:'检查目录与搜索反馈'}]};
   const coverage=(status,reasons={},scope={requestedPath:'.',rootFallback:false})=>({status,reasons,scope,samples:[],samplesTruncated:false});
   const cases=[
    ['complete',{ok:true,action:'search_files',query:'NEEDLE',count:0,results:[],coverage:coverage('complete')}],
    ['partial-empty',{ok:true,action:'search_files',query:'NEEDLE',count:0,results:[],coverage:coverage('partial',{file_unreadable:2})}],
    ['unknown-sizes',{ok:true,action:'list_files',path:'.',count:25,items:Array.from({length:25},(_,i)=>({type:'file',path:`unknown-${i}.txt`,size:0,sizeAvailable:false})),coverage:coverage('partial',{metadata_unavailable:25})}],
    ['root-failed',{ok:false,action:'glob_files',pattern:'*.txt',count:0,results:[],error:'Target is not accessible for this operation.',coverage:coverage('failed',{directory_unavailable:1})}],
    ['fallback',{ok:true,action:'glob_files',pattern:'*.txt',count:1,results:[{type:'file',path:'outside.txt',size:10}],coverage:coverage('partial',{directory_unavailable:1},{requestedPath:'sub',rootFallback:true,fallbackPath:'.'})}],
    ['legacy',{ok:true,action:'search_files',query:'NEEDLE',count:0,results:[]}],
   ];
   let seq=0;
   for(const [id,result] of cases){
    ctx.messages.push({role:'tool-call',content:'',meta:{agentRunId:ctx.agentRunId,action:result.action,toolCallId:id,tool:{action:result.action}}});
    const event={seq:++seq,data:{toolCallId:id,name:result.action,outcome:result.ok===false?'failed':'succeeded',result}};
    d.complete(ctx,event);d.complete(ctx,event);
   }
   window.__coverageSnapshot=JSON.stringify(ctx.messages);d.set(d.state.sessionId,JSON.parse(window.__coverageSnapshot));d.render();
   return {resultCount:ctx.messages.filter(message=>message.role==='tool-result').length};
  });
  assert.equal(installed.resultCount,6);
  const verify=async()=>{
   for(const stage of await page.locator('details.tool-process-stage').all())if(await stage.getAttribute('open')===null)await stage.locator(':scope > summary').click();
   for(const item of await page.locator('details.tool-process-item').all())if(await item.getAttribute('open')===null)await item.locator(':scope > summary').click();
   const body=id=>page.locator(`.tool-process-item[data-tool-call-id="${id}"] .tool-process-body`);
   for(const id of ['complete','partial-empty','unknown-sizes','root-failed','fallback','legacy'])await expect(page.locator(`.tool-process-item[data-tool-call-id="${id}"]`)).toHaveCount(1);
   await expect(body('complete')).toContainText(language==='zh'?'本次筛选范围内未找到匹配项':'No matches within the requested filters and scope');
   await expect(body('partial-empty')).toContainText(language==='zh'?'已检查部分未找到匹配项':'No matches in the inspected portion');
   const sizes=await body('unknown-sizes').innerText(),unknown=language==='zh'?'大小未知':'Size unknown';
   assert.equal(sizes.split(unknown).length-1,25);assert(!/\b0\s*(?:B|bytes)\b/.test(sizes));
   await expect(body('root-failed')).toContainText(language==='zh'?'目标整体不可访问':'The target is not accessible');
   if(language==='zh')await expect(body('root-failed')).not.toContainText('Target is not accessible for this operation');
   await expect(body('fallback')).toContainText(language==='zh'?'已回查根目录（原范围：sub）':'Also searched the root (requested scope: sub)');
   await expect(body('fallback')).toContainText('outside.txt');
   await expect(body('legacy')).toContainText(language==='zh'?'没有找到匹配项':'No matches');
   await expect(body('legacy')).not.toContainText(language==='zh'?'已检查本次筛选范围':'Checked the requested filters and scope');
   await expect(page.locator('.tool-process-item[data-tool-call-id="root-failed"]')).toHaveClass(/failed/);
   await expect(page.locator('.tool-process-item[data-tool-call-id="partial-empty"]')).not.toHaveClass(/failed/);
   await expect(page.locator('.edit-suggestion')).toHaveCount(0);
  };
  await verify();
  await page.evaluate(()=>{const d=window.__coverageProbe;d.set(d.state.sessionId,JSON.parse(window.__coverageSnapshot));d.render();});
  await verify();
  assert.equal(await page.evaluate(()=>JSON.stringify(window.__coverageProbe.state.messages)===window.__coverageSnapshot),true);
  await page.locator('.tool-process-item[data-tool-call-id="fallback"]').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(dir,`${runtime}-${language}-${width}.png`)});
  assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
  return {runtime,language,width,theme,results:6,unknownSizes:25,duplicateEventsSafe:true,historyUnchanged:true,errors};
 }catch(error){await page.screenshot({path:path.join(dir,`${runtime}-${language}-${width}-failed.png`)}).catch(()=>{});await fs.writeFile(path.join(dir,`${runtime}-${language}-${width}-failed.json`),JSON.stringify({error:String(error.stack),errors,blockedWrites:audit.blockedWrites,body:await page.locator('body').innerText()},null,2));throw error;}
 finally{await page.evaluate(()=>{if(window.__coverageProbe?.state.sessionId==='coverage-owned-ui')window.__coverageProbe.state.sessionId='';}).catch(()=>{});await context.close();}
}

async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code087-r036-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir,cases:[]};
 try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const language of ['zh','en'])for(const width of [1280,390]){result.cases.push(await scenario(browser,host,runtime,language,width,dir));console.log(`${runtime} ${language} ${width} passed`);}
  const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
 }catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const cleanup=await host.stop();result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
 console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
