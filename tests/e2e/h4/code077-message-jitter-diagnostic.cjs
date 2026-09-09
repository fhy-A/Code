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

function verifyHorizontalGeometry(cases) {
  let comparisons=0;
  const near=(a,b,label)=>assert(Math.abs(a-b)<=0.5,label);
  for(const scenario of cases)for(const update of scenario.cases) {
    const before=update.before.summaries[0].parts,after=update.frames.at(-1).summaries[0].parts;
    const label=`${scenario.runtime}/${scenario.width}/${update.mode}/${update.kind}`;
    if(update.kind==='tool-complete') {
      for(const selector of ['strong','code','.tool-process-stage-chevron']) {
        assert.equal(before[selector].text,after[selector].text,`${label}: same-content precondition`);
        near(before[selector].left,after[selector].left,`${label}/${selector}: left moved`);
        near(before[selector].width,after[selector].width,`${label}/${selector}: width moved`);comparisons++;
      }
    }
    if(update.kind==='tool-next') {
      near(before.strong.left,after.strong.left,`${label}: title left moved`);
      for(const p of [before,after])near(p.code.left-p.strong.left-p.strong.width,6,`${label}: heading gap`);
      // A different tool/path may legitimately change the arrow's absolute left.
      const gap=p=>p['.tool-process-stage-chevron'].left-p.code.left-p.code.width;
      near(gap(before),gap(after),`${label}: arrow gap changed`);comparisons+=3;
    }
    if(['output','same-redraw','delayed-image'].includes(update.kind)) {
      const imageBefore=update.before.summaries.find(s=>s.parts['.tool-image-icon']);
      const imageAfter=update.frames.at(-1).summaries.find(s=>s.parts['.tool-image-icon']);
      assert(imageBefore && imageAfter,`${label}: image icon missing`);
      near(imageBefore.parts['.tool-image-icon'].left,imageAfter.parts['.tool-image-icon'].left,`${label}: image icon moved`);comparisons++;
    }
  }
  return {comparisons};
}

async function exercise(browser, host, runtime, width, evidenceDir) {
  const traceLayout=process.argv.includes('--trace-layout');
  const expectBefore=process.argv.includes('--expect-before');
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
          summaries:[...list.querySelectorAll('.tool-process-stage-summary')].map(el=>({height:el.getBoundingClientRect().height,minHeight:getComputedStyle(el).minHeight,padding:getComputedStyle(el).padding,parent:el.parentElement.className,
            parts:Object.fromEntries(['strong','code','.tool-process-stage-chevron','.tool-image-icon'].map(selector=>{const part=el.querySelector(selector),r=part?.getBoundingClientRect();return[selector,part?{left:r.left,width:r.width,text:part.textContent}:null];}))})),
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
    let traceControls=null;
    if(traceLayout) {
      await page.evaluate(()=>window.__messageScroller.navigateToMessage(window.__traceAppState.sessionId,14));
      const active=page.locator('.execution-trace.active').last(), summary=active.locator(':scope > .execution-trace-summary');
      const expanded=()=>active.evaluate(el=>el.classList.contains('is-expanded'));
      const semantics=await summary.evaluate(el=>({role:el.getAttribute('role'),tabindex:el.getAttribute('tabindex'),toggle:el.hasAttribute('data-execution-trace-toggle'),arrow:!!el.querySelector('.execution-trace-chevron'),cursor:getComputedStyle(el).cursor}));
      await summary.click(); const afterClick=await expanded();
      await page.evaluate(()=>window.__diagnosticRender()); const afterRedraw=await expanded();
      if(!await expanded())await summary.click();
      const keyboard={};
      for(const key of ['Enter',' ']) {
        if(await summary.getAttribute('tabindex')!==null){await summary.focus();await page.keyboard.press(key===' '?'Space':key);}
        else await summary.dispatchEvent('keydown',{key,bubbles:true});
        keyboard[key]=await expanded(); if(!await expanded())await summary.click();
      }
      await active.evaluate(el=>el.classList.remove('is-expanded'));
      await page.evaluate(()=>{window.__traceAppState._lastRenderedHtml=null;window.__diagnosticRender();});
      const staleCollapseRepaired=await expanded();
      if(!await expanded())await summary.click();
      const internal={};
      for(const [name,selector] of [['tool','details.tool-process-stage:not(.tool-image-stage)'],['image','details.tool-image-stage']]) {
        const group=active.locator(selector).first(),toggle=group.locator(':scope > summary');
        const before=await group.evaluate(el=>el.open);await toggle.click();
        const after=await group.evaluate(el=>el.open);await page.evaluate(()=>window.__diagnosticRender());
        const redrawn=await group.evaluate(el=>el.open);internal[name]={before,after,redrawn};
        assert.equal(after,!before);assert.equal(redrawn,after);
      }
      await page.screenshot({path:path.join(evidenceDir,`${runtime}-${width}-active-controls.png`)});
      await page.evaluate(()=>{
        const state=window.__traceAppState;state._sessionRuns[state.sessionId].isStreaming=false;
        state.messages.at(-1)._responseTime='1s';window.__diagnosticRender();
      });
      const complete=page.locator('.execution-trace.completed[data-execution-trace="14"]'),toggle=complete.locator(':scope > .execution-trace-summary');
      await expect(toggle).toHaveAttribute('role','button');await expect(toggle).toHaveAttribute('tabindex','0');
      const ended=await complete.evaluate(el=>el.classList.contains('is-expanded'));
      await toggle.click();const clicked=await complete.evaluate(el=>el.classList.contains('is-expanded'));
      await toggle.focus();await page.keyboard.press('Space');const keyed=await complete.evaluate(el=>el.classList.contains('is-expanded'));
      assert.equal(clicked,!ended);assert.equal(keyed,ended);
      traceControls={semantics,afterClick,afterRedraw,keyboard,staleCollapseRepaired,internal,completed:{ended,clicked,keyed}};
      await fs.writeFile(path.join(evidenceDir,`${runtime}-${width}-controls.json`),JSON.stringify(traceControls,null,2));
      if(!expectBefore) {
        assert.deepEqual(semantics,{role:null,tabindex:null,toggle:false,arrow:false,cursor:'default'});
        assert(afterClick && afterRedraw && Object.values(keyboard).every(Boolean) && staleCollapseRepaired);
      }
    }
    assert.deepEqual(errors,[]); assert.deepEqual(audit.blockedWrites,[]);
    return {runtime,width,cases,traceControls,errors,audit};
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
    if(process.argv.includes('--trace-layout')&&!process.argv.includes('--expect-before'))result.horizontalRegression=verifyHorizontalGeometry(result.cases);
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
