// Bounded synthetic diagnosis through the real application's render callback.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
const {chromium, expect} = require('@playwright/test');
const {startIsolatedHost, getActiveChildCount} = require('./isolated-host.cjs');
const {createAudit, createContext, waitForRuntime} = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

function verifyStableSummaryHeight(cases) {
  let updates=0, frames=0;
  for(const scenario of cases)for(const update of scenario.cases) {
    const label=`${scenario.runtime}/${scenario.width}/${update.mode}/${update.kind}`;
    for(const sample of [update.before,...update.frames]) {
      assert(Number.isFinite(sample.anchorTop), `${label}: missing visible anchor`);
      assert(sample.summaries?.length, `${label}: missing summary geometry`);
      for(const summary of sample.summaries)assert.equal(summary.height,32,`${label}: summary height must stay 32px`);
    }
    for(const sample of update.frames) {
      frames++;
      assert.equal(sample.state.following,update.mode==='following',`${label}: following changed`);
      if(update.mode==='history' || !['image','output'].includes(update.kind)) {
        assert(Math.abs(sample.scrollTop-update.before.scrollTop)<=0.5,`${label}: unexpected scroll displacement`);
        assert(Math.abs(sample.anchorTop-update.before.anchorTop)<=0.5,`${label}: unexpected anchor displacement`);
      }
      if(!['image','output'].includes(update.kind))assert.equal(sample.scrollHeight,update.before.scrollHeight,`${label}: unexpected height change`);
    }
    const last=update.frames.at(-1);
    if(update.mode==='following')assert(Math.abs(last.scrollHeight-last.clientHeight-last.scrollTop)<=0.5,`${label}: must settle at bottom`);
    if(update.kind==='image')assert(last.groups>=2 && last.images.length===1,`${label}: independent image trace missing`);
    if(update.kind==='delayed-image')assert(update.events.some(event=>event.type==='image-load'),`${label}: delayed load missing`);
    updates++;
  }
  return {updates,frames,summaryHeight:32};
}

async function exercise(browser, host, runtime, width, evidenceDir) {
  const audit = createAudit(), context = await createContext(browser, host, runtime, audit, {language:'zh', theme:'light', width});
  await context.addInitScript(() => {
    let api;
    Object.defineProperty(Code.features, 'goal', {configurable:true, get:()=>api, set(value) {
      api = {...value, createGoalFeature(options) {
        window.__diagnosticRender = options.renderMessages;
        return value.createGoalFeature(options);
      }};
    }});
  });
  const page = await context.newPage(), errors = [], cases = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    await page.goto(new URL(runtime === 'bundle' ? '/' : '/dist/frontend/index.classic.html', host.ready.codeUrl).href);
    await waitForRuntime(page, runtime);
    await page.waitForLoadState('networkidle');
    await page.route('**/code077-delayed.png', async route => {
      await new Promise(resolve=>setTimeout(resolve,180));
      await route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC','base64')});
    });
    await page.evaluate(() => {
      const state = window.__traceAppState, scroller = window.__messageScroller;
      if (!state || !scroller || !window.__diagnosticRender) throw Error('actual render wiring missing');
      const area = document.getElementById('messages'), list = document.getElementById('messageList');
      window.__events = []; window.__anchorIndex = 8;
      const record = (type, detail={}) => window.__events.push({time:performance.now(),type,...detail});
      new MutationObserver(records => record('mutation', {count:records.length, childLists:records.filter(r=>r.type==='childList').length}))
        .observe(list, {subtree:true,childList:true,characterData:true});
      area.addEventListener('scroll',()=>record('scroll',{scrollTop:area.scrollTop}));
      list.addEventListener('load',event=>record('image-load',{tag:event.target.tagName}),true);
      window.__sample = label => {
        const target = list.querySelector(`[data-msg-index="${window.__anchorIndex}"]`), rect = target?.getBoundingClientRect();
        return {label,time:performance.now(),scrollTop:area.scrollTop,scrollHeight:area.scrollHeight,clientHeight:area.clientHeight,
          anchorTop:rect?.top,anchorHeight:rect?.height,containerTop:area.getBoundingClientRect().top,
          state:scroller.snapshot(),groups:list.querySelectorAll('.tool-process-stage').length,
          summaries:[...list.querySelectorAll('.tool-process-stage-summary')].map(el=>({height:el.getBoundingClientRect().height,minHeight:getComputedStyle(el).minHeight,padding:getComputedStyle(el).padding,parent:el.parentElement.className})),
          images:[...list.querySelectorAll('img')].map(img=>({complete:img.complete,width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height}))};
      };
      window.__frames = async (label,count=18) => {
        const samples=[window.__sample(label+':sync')];
        for(let i=0;i<count;i++){await new Promise(requestAnimationFrame);samples.push(window.__sample(label+':frame'+i));}
        return samples;
      };
      window.__install = () => {
        const session='code077-synthetic'; state.sessionId=session;
        state.messages=Array.from({length:7},(_,i)=>[
          {role:'user',content:`Synthetic question ${i}`},
          {role:'assistant',content:'Stable historical paragraph. '.repeat(80),_responseTime:'1s'},
        ]).flat();
        state.messages.push({role:'user',content:'Synthetic running task'},
          {role:'tool-call',meta:{action:'read_file',toolCallId:'read-a',tool:{action:'read_file',path:'fixture.txt'}}});
        state._sessionRuns[session]={sessionId:session,isStreaming:true,taskStartTime:Date.now()-9000,taskElapsedBaseMs:9000,taskElapsedResumedAt:Date.now()};
        state._sessionRunStates[session]={}; state._lastRenderedHtml=null;
        window.__diagnosticRender(); scroller.forceToLatest(session);
      };
      window.__change = kind => {
        const run=state._sessionRuns[state.sessionId];
        record('update-start',{kind});
        if(kind==='timer') {run.taskElapsedBaseMs+=1000;}
        if(kind==='tool-complete') state.messages.push({role:'tool-result',content:'Read complete',meta:{action:'read_file',toolCallId:'read-a',outcome:'succeeded',result:{ok:true,content:'Synthetic file'}}});
        if(kind==='tool-next') state.messages.push({role:'tool-call',meta:{action:'run_command',toolCallId:'cmd-a',tool:{action:'run_command',command:'echo synthetic'}}});
        if(kind==='output') state.messages.push({role:'assistant',content:'New synthetic content. '.repeat(30)});
        if(kind==='same-redraw') state._lastRenderedHtml=null;
        if(kind==='delayed-image') {
          const image=list.querySelector('img');if(!image)throw Error('image sample missing');
          image.src='/code077-delayed.png'; record('update-end',{kind});return;
        }
        if(kind==='image') state.messages.push(
          {role:'tool-call',meta:{action:'read_file',toolCallId:'image-a',tool:{action:'read_file',path:'fixture.png'}}},
          {role:'tool-result',content:'Synthetic image',meta:{action:'read_file',toolCallId:'image-a',outcome:'succeeded',result:{ok:true,action:'read_file',binary:true,visual:true,mime:'image/png',path:'fixture.png',base64:'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC'}}});
        window.__diagnosticRender(); record('update-end',{kind});
      };
      window.__install();
    });
    for (const mode of ['following','history']) {
      await page.evaluate(()=>window.__install());
      await expect.poll(()=>page.evaluate(()=>{const s=window.__sample('');return s.scrollHeight-s.clientHeight-s.scrollTop;})).toBe(0);
      if(mode==='history') {
        const box=await page.locator('#messages').boundingBox();
        await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.mouse.wheel(0,-1600);
        await expect.poll(()=>page.evaluate(()=>window.__messageScroller.snapshot().following)).toBe(false);
        await expect.poll(()=>page.evaluate(()=>window.__messageScroller.snapshot().userScrollIntentActive)).toBe(false);
      }
      await page.evaluate(()=>{
        const area=document.getElementById('messages'), top=area.getBoundingClientRect().top;
        const visible=[...area.querySelectorAll('.msg[data-msg-index]')].find(el=>el.getBoundingClientRect().bottom>top+20);
        window.__anchorIndex=Number(visible.dataset.msgIndex);window.__events=[];
      });
      for(const kind of ['timer','timer','tool-complete','tool-next','image','output','same-redraw',...(width===390?['delayed-image']:[])]) {
        const result=await page.evaluate(async kind=>{
          const before=window.__sample('before'); const old=document.querySelector('#messageList .msg');
          window.__change(kind); const sameNode=old===document.querySelector('#messageList .msg');
          const frames=await window.__frames(kind);
          return {kind,before,sameNode,frames,events:window.__events.splice(0)};
        },kind);
        result.mode=mode; cases.push(result);
      }
      await page.screenshot({path:path.join(evidenceDir,`${runtime}-${width}-${mode}.png`)});
    }
    assert.deepEqual(errors,[]); assert.deepEqual(audit.blockedWrites,[]);
    return {runtime,width,cases,errors,audit};
  } finally { await context.close(); }
}

async function main() {
  const evidenceIndex=process.argv.indexOf('--check-evidence');
  if(evidenceIndex!==-1) {
    const saved=JSON.parse(await fs.readFile(process.argv[evidenceIndex+1],'utf8'));
    console.log(JSON.stringify(verifyStableSummaryHeight(saved.cases)));return;
  }
  const width=process.argv.includes('--compact')?390:1280;
  const verifyHeight=process.argv.includes('--verify-height');
  const widths=process.argv.includes('--all-widths')?[1280,390]:[width];
  const evidenceDir=await fs.mkdtemp(path.join(os.tmpdir(),verifyHeight?'code077-height-regression-':`code077-round${width===390?2:1}-`));
  const host=await startIsolatedHost({disableRoutingV2:true}); let browser, result={evidenceDir,width,cases:[]};
  try {
    const before=await host.metrics(); browser=await chromium.launch({headless:true});
    for(const sampleWidth of widths)for(const runtime of ['bundle','classic'])result.cases.push(await exercise(browser,host,runtime,sampleWidth,evidenceDir));
    const after=await host.metrics();
    for(const key of ['chatRequests','toolExecutions','modelRouteRequests'])assert.equal(after[key].length-before[key].length,0);
    for(const key of ['agentRuns','runtimeRuns'])assert.equal(after.production[key].length-before.production[key].length,0);
    result.sideEffects={chat:0,tools:0,modelRoutes:0,agentRuns:0,runtimeRuns:0,writes:0};
    if(verifyHeight)result.heightRegression=verifyStableSummaryHeight(result.cases);
    result.ok=true;
  } catch(error) {result.ok=false;result.error=String(error.stack);process.exitCode=1;}
  finally {
    if(browser)await browser.close();const cleanup=await host.stop();
    result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};
    if(!cleanup.childExited || !cleanup.portsClosed.every(Boolean) || !cleanup.rootRemoved || cleanup.cleanupErrors.length || getActiveChildCount()) {
      result.ok=false; result.cleanupFailed=true; process.exitCode=1;
    }
    await fs.writeFile(path.join(evidenceDir,'result.json'),JSON.stringify(result,null,2));
  }
  console.log(JSON.stringify({ok:result.ok,evidenceDir,error:result.error,cleanup:result.cleanup}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
