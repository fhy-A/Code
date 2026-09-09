// Two bounded diagnostic rounds. Product bytes stay unchanged; only the served
// classic app gets function timing wrappers. Agent acceptances are synthetic.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const measuredFunctions=['sendMessage','enqueueSessionMessage','steerSessionMessage','submitSessionSteer','saveSessionState','getModelDispatchCredentials','resolveAtImages','waitForPendingImageAttachments','uploadImagesForStorage','projectOptimisticFirstMessage','renderSessionMessages'];
const markerPattern=/D081_[A-Za-z0-9_]*?_[0-9]+/g;

async function scenario(browser,host,spec,evidenceDir){
  const audit=createAudit(),context=await createContext(browser,host,'classic',audit,{width:1280,language:spec.language||'zh',theme:'light'});
  let page,active=false,agentSequence=0,saveFailures=0,acceptFailures=0;const agents={},network=[],errors=[];
  await context.addInitScript(({key})=>{
    localStorage.setItem('code-key-config',JSON.stringify([{name:'diagnostic synthetic',key,enabled:true,source:'manual'}]));
    localStorage.setItem('code-model','h4-e2e-model');
    window.__d={events:[],busy:0,enabled:false,record(type,data={}){if(this.enabled)this.events.push({t:performance.now(),type,...data});},
      wrap(name,original,args,self){
        const markers=[...JSON.stringify(args.slice(0,name==='saveSessionState'?2:1),(_key,value)=>value instanceof AbortController?undefined:value).matchAll(/D081_[A-Za-z0-9_]*?_[0-9]+/g)].map(m=>m[0]);
        // Do not inspect run/context objects, which can be circular or contain credentials.
        this.record(name+'.start',{markers:[...new Set(markers)]});this.busy++;
        const finish=()=>{this.busy--;this.record(name+'.end',{markers:[...new Set(markers)]});};
        try{const result=original.apply(self,args);if(result?.then)return result.then(value=>{finish();return value},error=>{finish();throw error});finish();return result;}catch(error){finish();throw error;}
      }};
    const fetchOriginal=window.fetch;
    window.fetch=async function(url,options={}){
      const pathname=new URL(typeof url==='string'?url:url.url,location.href).pathname;
      const kind=options.method==='PUT'&&/^\/api\/sessions\/[^/]+$/.test(pathname)?'save':pathname.endsWith('/steer')?'steer':options.method==='POST'&&pathname==='/api/agent/runs'?'agent':'';
      const markers=[...new Set(String(options.body||'').match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[])];
      if(kind)window.__d.record('fetch.'+kind+'.sent',{markers});
      const result=await fetchOriginal.apply(this,arguments);
      if(kind)window.__d.record('fetch.'+kind+'.received',{markers,status:result.status});
      return result;
    };
    const value=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');
    Object.defineProperty(HTMLTextAreaElement.prototype,'value',{...value,set(next){
      if(this.id==='prompt'&&next===''&&this.value)window.__d.record('input.cleared',{markers:this.value.match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[]});
      return value.set.call(this,next);
    }});
    document.addEventListener('submit',event=>{if(event.target.id==='chatForm')window.__d.record('submit',{markers:document.getElementById('prompt').value.match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[]})},true);
    document.addEventListener('keydown',event=>{if(event.target.id==='prompt'&&event.key==='Enter')window.__d.record('input.enter',{markers:event.target.value.match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[]})},true);
    document.addEventListener('click',event=>{if(event.target.closest('#sendBtn'))window.__d.record('input.click',{markers:document.getElementById('prompt').value.match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[]})},true);
    document.addEventListener('DOMContentLoaded',()=>{
      const seen=new Set(),frames=new Set();
      new MutationObserver(()=>{
        if(!window.__d.enabled)return;
        for(const el of document.querySelectorAll('#messages article.msg.user'))for(const marker of el.textContent.match(/D081_[A-Za-z0-9_]*?_[0-9]+/g)||[]){
          if(!seen.has(marker)){seen.add(marker);window.__d.record('dom.user',{markers:[marker]});}
          if(!frames.has(marker)){frames.add(marker);requestAnimationFrame(()=>{const box=el.getBoundingClientRect();window.__d.record('frame.user',{markers:[marker],visible:box.width>0&&box.height>0});});}
        }
      }).observe(document.getElementById('messages'),{childList:true,subtree:true,characterData:true});
    });
  },{key:host.syntheticKey});
  await context.route('**/app.js',async route=>{
    const response=await route.fetch();let source=await response.text();
    for(const name of measuredFunctions){
      // Only text/Session-id/message arguments are copied into timing metadata.
      const credentialDelay=name==='getModelDispatchCredentials'?Number(spec.credentialDelay||0):0;
      source+=`\n{const original=${name};${name}=function(...args){const brief=${JSON.stringify(['steerSessionMessage','enqueueSessionMessage'].includes(name))}?[args[1]]:${JSON.stringify(name==='submitSessionSteer')}?[args[1]?.content]:${JSON.stringify(name==='getModelDispatchCredentials')}?[]:args;const invoke=()=>original.apply(this,args);return window.__d.wrap(${JSON.stringify(name)},${credentialDelay}&&window.__d.enabled?async()=>{await new Promise(resolve=>setTimeout(resolve,${credentialDelay}));return invoke();}:invoke,brief,this);};}\n`;
    }
    await route.fulfill({response,body:source});
  });
  await context.route('**/proxy/models*',route=>route.continue({headers:{...route.request().headers(),'x-base-url':host.ready.fakeUrl}}));
  const mark=async(type,details)=>{if(page&&!page.isClosed())try{await page.evaluate(({type,details})=>window.__d?.record(type,details),{type,details});}catch(error){if(!/context was destroyed|closed/i.test(String(error)))throw error;}};
  await context.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),method=request.method();
    if(method==='POST'&&url.pathname==='/api/config'){
      assert.equal(url.origin,new URL(host.ready.codeUrl).origin);
      const body=request.postDataJSON();assert.deepEqual(Object.keys(body),['projectRoot']);assert.equal(path.resolve(body.projectRoot),path.resolve(host.projectDir));
      await route.fulfill({response:await route.fetch()});return;
    }
    const sessionWrite=['PUT','POST'].includes(method)&&/^\/api\/sessions\/[^/]+$/.test(url.pathname);
    const sessionCreate=method==='POST'&&url.pathname==='/api/sessions';
    if(sessionWrite||sessionCreate){
      assert.equal(url.origin,new URL(host.ready.codeUrl).origin);
      const body=request.postDataJSON(),markers=[...new Set(JSON.stringify(body.messages||[]).match(markerPattern)||[])];
      if(active)await mark('http.save.sent',{markers});
      if(active&&sessionWrite&&markers.length&&spec.saveDelay)await delay(spec.saveDelay);
      if(active&&sessionWrite&&markers.length&&spec.failSave&&saveFailures++===0){await route.fulfill({status:500,json:{error:'controlled save failure'}});return;}
      const response=await route.fetch();if(active)await mark('http.save.accepted',{markers,status:response.status()});
      await route.fulfill({response});return;
    }
    if(url.pathname.startsWith('/api/agent/runs')){
      const body=method==='POST'?request.postDataJSON():{};
      const markers=[...new Set(JSON.stringify(body.message||body.payload?.messages||[]).match(markerPattern)||[])];
      if(method==='POST'&&(url.pathname==='/api/agent/runs'||url.pathname.endsWith('/steer'))){
        await mark(url.pathname.endsWith('/steer')?'http.steer.sent':'http.agent.sent',{markers});
        if(active&&spec.acceptDelay)await delay(spec.acceptDelay);
        network.push({path:url.pathname,markers,clientRequestId:body.clientRequestId});
        if(url.pathname.endsWith('/steer')&&((spec.failAccept&&acceptFailures++===0)||spec.steer409)){
          await route.fulfill({status:spec.steer409?409:500,json:{error:'controlled acceptance failure'}});return;
        }
        await mark(url.pathname.endsWith('/steer')?'http.steer.accepted':'http.agent.accepted',{markers,synthetic:true});
        if(url.pathname.endsWith('/steer')){await route.fulfill({json:{ok:true,result:{steerId:'synthetic-steer-'+network.length}}});return;}
        const id='diagnostic-'+(++agentSequence);agents[id]={agentRunId:id,sessionId:body.sessionId,status:'completed',events:[],nextCursor:0,result:{content:'synthetic acceptance only'},usage:{},toolExecutions:[],rounds:[]};
        await route.fulfill({json:agents[id]});return;
      }
      const id=url.pathname.split('/')[4];await route.fulfill({json:agents[id]||{agentRunId:id,status:'cancelled',events:[],result:{}}});return;
    }
    await route.fallback();
  });
  try{
    page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
    await page.goto(host.ready.codeUrl+'/dist/frontend/index.classic.html');await waitForRuntime(page,'classic');await page.waitForLoadState('networkidle');
    await expect(page.locator('#modelPillBtn')).toHaveAttribute('data-model','h4-e2e-model');
    await page.locator('#baseUrl').evaluate((el,url)=>el.value=url,host.ready.fakeUrl);
    await page.evaluate(async mode=>{
      await createSession('追加诊断隔离历史');
      const messages=[{role:'user',content:'此前的问题',_time:new Date().toISOString()},{role:'assistant',content:'此前已完成的回答',_time:new Date().toISOString()}];
      setSessionMessages(state.sessionId,messages);state.messages=messages;renderSessionMessages(state.sessionId);
      await saveSessionState(state.sessionId,messages,getSessionStats(state.sessionId),undefined,{persistMessages:true});
      if(mode!=='ordinary'){
        const ctx=buildRunContext(state.sessionId);ctx.agentRunId='synthetic-active';ctx.run.agentRunId=ctx.agentRunId;ctx.run.abortController=new AbortController();claimActiveRunContext(ctx);
        setStreaming(true,state.sessionId);localStorage.setItem('code-follow-up-behavior',mode);
      }
    },spec.mode);
    active=true;await page.evaluate(()=>{window.__d.events=[];window.__d.enabled=true});
    const markers=Array.from({length:spec.rapid?3:1},(_,i)=>`D081_${spec.name}_${i+1}`);
    for(const marker of markers){await page.locator('#prompt').fill(marker);if(spec.input==='enter')await page.locator('#prompt').press('Enter');else await page.locator('#sendBtn').click();}
    for(const marker of markers)await expect(page.locator('#messages article.msg.user').filter({hasText:marker})).toHaveCount(1);
    await page.waitForFunction(()=>window.__d.busy===0,{},{timeout:12000});await page.waitForTimeout(80);
    if(spec.retry){
      const originalId=await page.evaluate(marker=>getSessionMessages(state.sessionId).find(m=>m.content===marker)?.id,markers[0]);
      await expect(page.locator('#messages')).toContainText('controlled');
      if(spec.failSave)assert.equal(network.length,0);
      await page.screenshot({path:path.join(evidenceDir,spec.name+'-failure.png'),animations:'disabled'});
      if(spec.language==='en'){
        await page.evaluate(()=>{setLang('zh');applyI18n()});await expect(page.locator('[data-follow-up-retry]')).toHaveText('重试');
        await page.evaluate(()=>{setLang('en');applyI18n()});await expect(page.locator('[data-follow-up-retry]')).toHaveText('Retry');
      }
      await page.locator('[data-follow-up-retry]').click();
      await page.waitForFunction(()=>window.__d.busy===0,{},{timeout:12000});
      assert.equal(await page.evaluate(marker=>getSessionMessages(state.sessionId).find(m=>m.content===marker)?.id,markers[0]),originalId);
    }
    if(spec.sameTextNew){
      const firstId=await page.evaluate(marker=>getSessionMessages(state.sessionId).find(m=>m.content===marker)?.id,markers[0]);
      await page.locator('#prompt').fill(markers[0]);await page.locator('#prompt').press('Enter');
      await page.waitForFunction(()=>window.__d.busy===0,{},{timeout:12000});
      const ids=await page.evaluate(marker=>getSessionMessages(state.sessionId).filter(m=>m.content===marker).map(m=>m.id),markers[0]);
      assert.equal(ids.length,2);assert.equal(ids[0],firstId);assert.notEqual(ids[1],firstId);
    }
    const captured=await page.evaluate(()=>({events:window.__d.events,messages:getSessionMessages(state.sessionId).filter(m=>m.role==='user').map(m=>m.content),sessionId:state.sessionId}));
    const projected=captured.messages.filter(text=>typeof text==='string'&&text.startsWith('D081_'));
    const expectedMessages=spec.sameTextNew?[...markers,...markers]:markers;
    assert.deepEqual(projected,expectedMessages);assert.equal(new Set(network.map(item=>item.clientRequestId)).size,spec.mode==='queue'?0:markers.length);
    assert.equal(network.length,spec.mode==='queue'?0:markers.length+(spec.failAccept?1:0));
    const persisted=await page.request.get(host.ready.codeUrl+'/api/sessions/'+captured.sessionId).then(r=>r.json());
    assert.deepEqual(persisted.messages.filter(m=>m.role==='user'&&String(m.content).startsWith('D081_')).map(m=>m.content),expectedMessages);
    const timings=markers.map(marker=>{
      const events=captured.events.filter(event=>event.markers?.includes(marker)),start=events.find(event=>event.type==='input.'+spec.input)?.t;
      const first=type=>{const event=events.find(event=>event.type===type);return event?+(event.t-start).toFixed(2):null};
      return {marker,clearMs:first('input.cleared'),domMs:first('dom.user'),frameMs:first('frame.user'),saveFetchMs:first('fetch.save.sent'),saveSentMs:first('http.save.sent'),saveAcceptedMs:first('http.save.accepted'),agentFetchMs:first('fetch.agent.sent'),agentSentMs:first('http.agent.sent'),agentAcceptedMs:first('http.agent.accepted'),steerFetchMs:first('fetch.steer.sent'),steerSentMs:first('http.steer.sent'),steerAcceptedMs:first('http.steer.accepted')};
    });
    if(spec.verifyImmediate){
      assert(timings.every(item=>Number.isFinite(item.frameMs)&&item.frameMs>=0&&item.frameMs<200),JSON.stringify(timings));
      for(const marker of markers){
        const bubble=page.locator('#messages article.msg.user').filter({hasText:marker});
        assert(!/提交中|待提交|已接受|submitting|processing/i.test((await bubble.allInnerTexts()).join('')));
        assert.equal(await bubble.locator('.background-dispatch-status').count(),0);
      }
    }
    if(spec.refresh){
      const before=network.length;await page.reload();await waitForRuntime(page,'classic');await page.waitForLoadState('networkidle');
      for(const marker of markers)await expect(page.locator('#messages article.msg.user').filter({hasText:marker})).toHaveCount(1);
      await page.waitForFunction(()=>!state.isStreaming,{},{timeout:12000});
      assert(network.length<=before+markers.length,'refresh must not replay a queued message twice');
    }
    assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
    return {spec,timings,events:captured.events,network,orderedOnce:true,errors};
  }finally{active=false;await context.close();}
}

async function main(){
  const round=Number(process.argv[2]||1);assert([1,2,3].includes(round));
  const evidenceDir=await fs.mkdtemp(path.join(os.tmpdir(),`code081-round${round}-`));
  const host=await startIsolatedHost({disableRoutingV2:true});let browser,result={round,evidenceDir,cases:[]};
  try{
    browser=await chromium.launch({headless:true});
    const specs=round===3?[
      {name:'r014_steer_click',mode:'steer',input:'click',saveDelay:800,verifyImmediate:true},
      {name:'r014_steer_retry',mode:'steer',input:'enter',failAccept:true,retry:true,saveDelay:800,verifyImmediate:true,language:'en'},
      {name:'r014_queue_qualification',mode:'queue',input:'click',credentialDelay:800,rapid:true,verifyImmediate:true},
      {name:'r014_queue_save_retry',mode:'queue',input:'enter',saveDelay:800,failSave:true,retry:true,refresh:true,verifyImmediate:true},
      {name:'r014_steer_409',mode:'steer',input:'click',acceptDelay:800,steer409:true,verifyImmediate:true},
      {name:'r014_same_text_new',mode:'queue',input:'enter',failSave:true,sameTextNew:true,verifyImmediate:true},
    ]:round===1?['ordinary','steer','queue'].flatMap(mode=>['click','enter'].map(input=>({name:`r1_${mode}_${input}`,mode,input}))).concat([{name:'r1_queue_rapid',mode:'queue',input:'enter',rapid:true}]):[
      {name:'r2_ordinary_save',mode:'ordinary',input:'click',saveDelay:800},
      {name:'r2_steer_save',mode:'steer',input:'enter',saveDelay:800},
      {name:'r2_queue_save',mode:'queue',input:'click',saveDelay:800},
      {name:'r2_steer_accept',mode:'steer',input:'click',acceptDelay:800},
      {name:'r2_queue_rapid_save',mode:'queue',input:'enter',saveDelay:800,rapid:true},
    ];
    for(const spec of specs.filter(item=>!process.argv.some(arg=>arg.startsWith('--case='))||process.argv.includes('--case='+item.name))){result.cases.push(await scenario(browser,host,spec,evidenceDir));console.log(JSON.stringify({finished:spec.name}));}
    const metrics=await host.metrics();assert.equal(metrics.chatRequests.length,0);assert.equal(metrics.toolExecutions.length,0);assert.equal(metrics.production.agentRuns.length,0);
    result.effects={modelRequests:0,tools:0,realAgentRuns:0};result.ok=true;
  }catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
  finally{if(browser)await browser.close();const cleanup=await host.stop();result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};
    if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}
    await fs.writeFile(path.join(evidenceDir,'result.json'),JSON.stringify(result,null,2));}
  console.log(JSON.stringify({round,ok:result.ok,evidenceDir,error:result.error,cases:result.cases.map(c=>({spec:c.spec,timings:c.timings})),cleanup:result.cleanup}));
}
main().catch(error=>{console.error(error);process.exitCode=1});
