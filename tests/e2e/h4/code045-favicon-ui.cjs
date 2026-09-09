const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC','base64');
async function scenario(browser,host,runtime,theme,width,dir){
  const audit=createAudit(),context=await createContext(browser,host,runtime,audit,{width,theme,language:runtime==='bundle'?'zh':'en'}),counts={},requests=[],errors=[];
  let release;const gate=new Promise(resolve=>release=resolve);
  // Expose existing closures only; product logic and rendering remain unchanged.
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch(),source=await response.text();
    const needle=source.match(/function bindExtLinkFavicons\([^)]*\) \{/)?.[0];assert(needle);
    // Playwright aborts URLs ending exactly in /favicon.ico before user routing.
    // The transport-only query keeps this isolated response controllable; the
    // deterministic source test separately verifies the exact production URL.
    const instrumented=source.replace(needle,'window.__faviconUI = {bind:bindExtLinkFavicons, tooltip:bindTooltips, contextMenu:bindLinkContextMenus, cache:_faviconCache, render:renderMessages, state, set:setSessionMessages, run:ensureSessionRun}; '+needle)
      .replace('`${cacheKey}/favicon.ico`','`${cacheKey}/favicon.ico?code045-fixture=1`');
    assert(instrumented.includes('/favicon.ico?code045-fixture=1'));
    await route.fulfill({response,body:instrumented});
  });
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());let name,source;
    if(url.hostname==='www.google.com'&&url.pathname==='/s2/favicons'){
      const origin=new URL(url.searchParams.get('domain'));name=origin.hostname;source='google';
      assert.equal(origin.pathname,'/');assert.equal(origin.search,'');assert.equal(url.searchParams.get('sz'),'32');
    }else if(url.hostname.endsWith('.test')&&url.pathname==='/favicon.ico'){name=url.hostname;source='origin'}
    else return route.fallback();
    assert(['success.test','retry.test','missing.test','badimage.test','network.test'].includes(name));
    const key=name+':'+source;counts[key]=(counts[key]||0)+1;
    requests.push({host:name,source,path:url.pathname,time:Date.now()});await gate;
    if(name==='missing.test'||(source==='google'&&['retry.test','network.test'].includes(name)))return route.abort('failed');
    if(source==='google'&&name==='badimage.test')return route.fulfill({status:200,contentType:'image/png',headers:{'Cache-Control':'no-store'},body:'not an image'});
    return route.fulfill({status:200,contentType:'image/png',headers:{'Cache-Control':'no-store'},body:png});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  const key=`${runtime}-${theme}-${width}`;
  try{
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
    const install=async()=>page.evaluate(()=>{
      const renderer=Code.ui.markdown.createMarkdownFeature().renderer;
      const names=['success.test','retry.test','missing.test','badimage.test','network.test','retry.test'];
      const html=names.map(name=>'<p>'+renderer.link({href:'https://'+name+'/path',text:'https://'+name+'/path'})+'</p>').join('')+'<p><a class="path-file-card" data-path="C:/fixture/readme.txt" title="C:/fixture/readme.txt">readme.txt</a></p>';
      const d=window.__faviconUI;d.state.sessionId='code045-owned-ui';const run=d.run(d.state.sessionId);run.isStreaming=true;run.taskStartTime ||= Date.now();
      window.__faviconRenderSerial=(window.__faviconRenderSerial||0)+1;
      d.set(d.state.sessionId,[{role:'assistant',content:html+'<p>Stream '+window.__faviconRenderSerial+'</p>'}]);d.render();
      window.__retryNode=document.querySelector('a[href="https://retry.test/path"] .link-ext-icon');
      return [...document.querySelectorAll('a.ext-link .link-ext-icon')].map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height}});
    });
    const before=await install(),links=page.locator('a.ext-link');await expect(links).toHaveCount(6);await expect(links.locator('svg')).toHaveCount(6);
    const retry=links.nth(1);await retry.focus();await expect(page.locator('.sb-path-tooltip')).toHaveText('https://retry.test/path');assert.equal(await retry.getAttribute('title'),null);
    await page.screenshot({path:path.join(dir,key+'-before.png')});release();
    await expect(links.nth(0).locator('canvas.ext-favicon')).toHaveCount(1);await expect(retry.locator('canvas.ext-favicon')).toHaveCount(1);await expect(links.nth(4).locator('canvas.ext-favicon')).toHaveCount(1);await expect(links.nth(5).locator('canvas.ext-favicon')).toHaveCount(1);
    await expect(links.nth(2).locator('svg')).toHaveCount(1);await expect(links.nth(3).locator('canvas.ext-favicon')).toHaveCount(1);
    assert.deepEqual(counts,{'success.test:google':1,'retry.test:google':1,'missing.test:google':1,'badimage.test:google':1,'retry.test:origin':1,'missing.test:origin':1,'badimage.test:origin':1,'network.test:google':1,'network.test:origin':1});
    const after=await page.evaluate(()=>({sameNode:window.__retryNode===document.querySelector('a[href="https://retry.test/path"] .link-ext-icon'),geometry:[...document.querySelectorAll('a.ext-link .link-ext-icon')].map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height}}),overflow:document.documentElement.scrollWidth>innerWidth}));
    assert(after.sameNode);assert.deepEqual(after.geometry,before);assert(!after.overflow);
    const beforeRedraw=requests.length;
    for(let step=0;step<20;step++)await install();
    await expect(links.nth(0).locator('canvas.ext-favicon')).toHaveCount(1);
    assert.equal(requests.length,beforeRedraw,'no-store success must not request again during streaming redraw');
    await page.evaluate(()=>{const d=window.__faviconUI;d.run(d.state.sessionId).isStreaming=false;d.render()});
    assert.equal(requests.length,beforeRedraw);
    await page.locator('.path-file-card').hover();await expect(page.locator('.sb-path-tooltip')).toHaveCount(1);await expect(page.locator('.sb-path-tooltip')).toHaveText('C:/fixture/readme.txt');assert.equal(await page.locator('.path-file-card').getAttribute('title'),null);
    await page.evaluate(()=>{
      window.__faviconCopied=[];window.__faviconActivated=[];
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.__faviconCopied.push(value)}}});
      document.querySelector('a.ext-link').addEventListener('click',event=>{event.preventDefault();window.__faviconActivated.push(event.currentTarget.href)});
    });
    await links.nth(0).click({button:'right'});await page.locator('.file-ctx-menu [data-action="copy-link"]').click();
    await expect.poll(()=>page.evaluate(()=>window.__faviconCopied)).toEqual(['https://success.test/path']);
    await links.nth(0).focus();await page.keyboard.press('Enter');assert.deepEqual(await page.evaluate(()=>window.__faviconActivated),['https://success.test/path']);
    assert.equal(await links.nth(0).getAttribute('target'),'_blank');assert.equal(await links.nth(0).getAttribute('rel'),'noopener');
    await page.screenshot({path:path.join(dir,key+'-after.png')});
    // This in-memory fixture has no persisted Session; suppress its unload beacon.
    await page.evaluate(()=>{window.__faviconUI.state.sessionId=''});
    await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await install();await expect(page.locator('a.ext-link').nth(0).locator('canvas.ext-favicon')).toHaveCount(1);
    assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
    assert(requests.every(r=>r.path==='/s2/favicons'||r.path==='/favicon.ico'));
    assert(!audit.initiated.some(r=>r.path==='/api/favicon'));
    return {runtime,theme,width,counts,requests,originFixtureQuery:true,geometry:before,originalNodeRecovered:true,noStoreRedrawRequests:beforeRedraw,streamingRedraws:20,tooltip:true,contextCopy:true,keyboardActivation:true,refresh:true,errors};
  }finally{release();await page.evaluate(()=>{if(window.__faviconUI?.state.sessionId==='code045-owned-ui')window.__faviconUI.state.sessionId=''}).catch(()=>{});await context.close();}
}

async function streamingScenario(browser,host,runtime,theme,width,dir,baseline){
  const audit=createAudit(),context=await createContext(browser,host,runtime,audit,{width,theme,language:'zh'});
  const requests=[],errors=[],failed=[],gates=new Map();
  for(const name of ['quick.test','slow.test']){let release;const promise=new Promise(r=>release=r);gates.set(name,{promise,release})}
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch();let source=await response.text();
    const needle=source.match(/function bindExtLinkFavicons\([^)]*\) \{/)?.[0];assert(needle);
    source=source.replace(needle,'window.__faviconUI={bind:bindExtLinkFavicons,cache:_faviconCache,render:renderMessages,state,set:setSessionMessages,get:getSessionMessages,run:ensureSessionRun,update:updateAssistantMessage,patches:[],scheduled:0,fullRenders:0}; '+needle)
      .replace('`${cacheKey}/favicon.ico`','`${cacheKey}/favicon.ico?code045-fixture=1`')
      .replace('function renderMessages() {','function renderMessages() { if(window.__faviconUI)window.__faviconUI.fullRenders++;')
      .replace('function scheduleStreamingAssistantPatch(sessionId, index) {','function scheduleStreamingAssistantPatch(sessionId, index) { window.__faviconUI.scheduled++;');
    const start=source.indexOf('function patchStreamingAssistantMessage('),end=source.indexOf('function scheduleStreamingAssistantPatch(',start);
    const block=source.slice(start,end),endNeedle='  messageScrollController?.onContentChanged(sessionId);';assert(block.includes(endNeedle));
    source=source.slice(0,start)+block.replace(endNeedle,`  window.__faviconUI.patches.push({streaming:msg.streaming,canvases:outputNode?.querySelectorAll('canvas.ext-favicon').length,slots:outputNode?.querySelectorAll('.link-ext-icon').length,fullRenders:window.__faviconUI.fullRenders});\n${endNeedle}`)+source.slice(end);
    await route.fulfill({response,body:source});
  });
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());let name,kind;
    if(url.hostname==='www.google.com'&&url.pathname==='/s2/favicons'){name=new URL(url.searchParams.get('domain')).hostname;kind='google'}
    else if(url.hostname.endsWith('.test')&&url.pathname==='/favicon.ico'){name=url.hostname;kind='origin'}
    else return route.fallback();
    assert(['quick.test','slow.test','late.test','failed.test'].includes(name));requests.push({name,kind,time:Date.now()});
    if(gates.has(name))await gates.get(name).promise;
    if(name==='failed.test')return route.abort('failed');
    return route.fulfill({status:200,contentType:'image/png',headers:{'Cache-Control':'no-store'},body:png});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));page.on('requestfailed',r=>{if(r.url().includes('s2/favicons')||r.url().includes('/favicon.ico'))failed.push(r.url())});
  // Shared offline harness parses HTML verbatim. Use the actual Markdown link
  // renderer for frozen paragraph/table tokens; do not claim marked parsing coverage.
  let prefix;

  const geometry=()=>page.evaluate(()=>[...document.querySelectorAll('a.ext-link')].map(link=>{
    const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};
    const slot=link.querySelector('.link-ext-icon'),node=slot.firstElementChild,parent=link.closest('td,p');
    const text=[...link.childNodes].find(n=>n.nodeType===Node.TEXT_NODE);const range=document.createRange();range.selectNodeContents(text);
    return {href:link.getAttribute('href'),kind:parent.tagName,outer:rect(slot),inner:rect(node),text:rect(range),relativeText:{x:rect(range).x-rect(parent).x,y:rect(range).y-rect(parent).y},relativeOuter:{x:rect(slot).x-rect(parent).x,y:rect(slot).y-rect(parent).y},lineHeight:getComputedStyle(parent).lineHeight,parentHeight:parent.getBoundingClientRect().height};
  }));
  const stableGeometry=async()=>{
    let previous='',stable=0,value;
    for(let frame=0;frame<120;frame++){
      await page.evaluate(()=>new Promise(requestAnimationFrame));value=await geometry();const next=JSON.stringify(value);
      stable=next===previous?stable+1:0;if(stable>=5)return value;previous=next;
    }
    throw new Error('Icon/text geometry did not settle');
  };
  const update=async content=>{
    const prior=await page.evaluate(content=>{const d=window.__faviconUI,n=d.patches.length;d.update(0,content,true,d.state.sessionId);return n},content);
    await expect.poll(()=>page.evaluate(()=>window.__faviconUI.patches.length)).toBeGreaterThan(prior);
  };
  const result={runtime,theme,width,baseline,requests,failed};
  try{
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
    prefix=await page.evaluate(()=>{const renderer=Code.ui.markdown.createMarkdownFeature().renderer;
      const link=(name,text,suffix='path')=>renderer.link({href:'https://'+name+'/'+suffix,text});
      return '<p>段落 '+link('quick.test','快图')+' 与 '+link('slow.test','慢图')+' 尾文。</p><table><thead><tr><th>类型</th><th>链接</th></tr></thead><tbody><tr><td>一</td><td>'+link('quick.test','快图','other')+'</td></tr><tr><td>二</td><td>'+link('slow.test','慢图','other')+'</td></tr></tbody></table>';
    });
    await page.evaluate(()=>{const d=window.__faviconUI;d.state.sessionId='code045-stream-owned';d.run(d.state.sessionId).isStreaming=true;d.set(d.state.sessionId,[{role:'assistant',content:'准备输出。',streaming:true,_streamProjection:'answer'}]);d.render()});
    await expect(page.locator('[data-stream-part="answer"]')).toHaveCount(1);
    await update(prefix+'持续输出 0');await expect(page.locator('a.ext-link')).toHaveCount(4);
    const initialRenders=await page.evaluate(()=>window.__faviconUI.fullRenders);
    if(baseline){
      for(let i=1;i<=6;i++)await update(prefix+'持续输出 '+i);
      assert.equal(requests.length,0);assert.equal(await page.locator('canvas.ext-favicon').count(),0);
      result.incrementalBeforeControl={updates:7,requests:0,globeCount:4,stillStreaming:await page.evaluate(()=>window.__faviconUI.get(window.__faviconUI.state.sessionId)[0].streaming)};
    }else await expect.poll(()=>requests.length).toBe(2);
    await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}-stream-before.png`)});result.before=await stableGeometry();
    if(baseline){await page.evaluate(()=>window.__faviconUI.bind());await expect.poll(()=>requests.length).toBe(2)}
    gates.get('quick.test').release();await expect(page.locator('canvas.ext-favicon')).toHaveCount(2);
    result.quickLoaded=await stableGeometry();
    // The text is unchanged across these observations; only the icon loaded.
    for(let i=0;i<result.before.length;i++){
      if(!baseline){
        assert.deepEqual(result.quickLoaded[i].outer,result.before[i].outer);
        assert.deepEqual(result.quickLoaded[i].text,result.before[i].text);
        assert.equal(result.quickLoaded[i].parentHeight,result.before[i].parentHeight);
        assert.equal(result.quickLoaded[i].lineHeight,result.before[i].lineHeight);
      }
      assert.equal(result.before[i].outer.width,20);assert.equal(result.before[i].outer.height,20);
      assert.equal(result.before[i].inner.width,baseline?12:16);assert.equal(result.before[i].inner.height,baseline?12:16);
      if(i%2===0){assert.equal(result.quickLoaded[i].inner.width,16);assert.equal(result.quickLoaded[i].inner.height,16)}
    }
    if(!baseline){
      for(let i=1;i<=8;i++)await update(prefix+'持续输出 '+i);
      assert.equal(requests.length,2);assert.equal(failed.length,0);
      const snapshots=await page.evaluate(()=>window.__faviconUI.patches.slice(-8));assert(snapshots.every(x=>x.streaming&&x.canvases===2&&x.slots===4));
      result.cachedSynchronousPatches=snapshots;
      assert.equal(await page.evaluate(()=>window.__faviconUI.fullRenders),initialRenders);
      gates.get('slow.test').release();await expect(page.locator('canvas.ext-favicon')).toHaveCount(4);
      const expanded=prefix+await page.evaluate(()=>{const renderer=Code.ui.markdown.createMarkdownFeature().renderer;return '<p>新增 '+renderer.link({href:'https://late.test/x',text:'后到'})+' 和 '+renderer.link({href:'https://failed.test/x',text:'失败'})+'。</p><p>持续输出 9</p>'});
      await update(expanded);await expect(page.locator('canvas.ext-favicon')).toHaveCount(5);await expect.poll(()=>requests.length).toBe(5);
      assert.equal(requests.filter(x=>x.name==='slow.test').length,1);assert.equal(requests.filter(x=>x.name==='quick.test').length,1);
      await expect(page.locator('a[href="https://failed.test/x"] svg')).toHaveCount(1);
      for(let i=10;i<14;i++)await update(expanded+' '+i);
      assert.equal(requests.length,5);assert.equal(await page.evaluate(()=>window.__faviconUI.get(window.__faviconUI.state.sessionId)[0].streaming),true);
      result.visibleBeforeEnd=await page.evaluate(()=>({streaming:window.__faviconUI.get(window.__faviconUI.state.sessionId)[0].streaming,canvases:document.querySelectorAll('canvas.ext-favicon').length,slots:document.querySelectorAll('.link-ext-icon').length}));
      await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}-stream-after.png`)});
      await page.evaluate(content=>{const d=window.__faviconUI;d.run(d.state.sessionId).isStreaming=false;d.update(0,content,false,d.state.sessionId)},expanded+' 13');
      await expect(page.locator('[data-streaming-message="true"]')).toHaveCount(0);await expect(page.locator('canvas.ext-favicon')).toHaveCount(5);assert.equal(requests.length,5);
      result.finalGeometry=await geometry();assert(result.finalGeometry.every(x=>x.inner.width===16&&x.inner.height===16&&x.outer.width===20&&x.outer.height===20));
    }else{gates.get('slow.test').release();await expect(page.locator('canvas.ext-favicon')).toHaveCount(4);await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}-stream-after.png`)});}
    result.trace=await page.evaluate(()=>({scheduled:window.__faviconUI.scheduled,patches:window.__faviconUI.patches,fullRenders:window.__faviconUI.fullRenders}));
    assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);result.errors=errors;result.ok=true;
    return result;
  }catch(error){
    await fs.writeFile(path.join(dir,`${runtime}-${theme}-${width}-failure.json`),JSON.stringify({measurements:result,error:String(error.stack),errors,requests,state:await page.evaluate(()=>({messages:window.__faviconUI?.get(window.__faviconUI.state.sessionId),trace:window.__faviconUI?.patches,html:document.querySelector('[data-stream-part="answer"]')?.innerHTML,marked:typeof marked})).catch(()=>null)},null,2));
    await page.screenshot({path:path.join(dir,`${runtime}-${theme}-${width}-failure.png`)}).catch(()=>{});throw error;
  }finally{for(const g of gates.values())g.release();await page.evaluate(()=>{if(window.__faviconUI?.state.sessionId==='code045-stream-owned')window.__faviconUI.state.sessionId=''}).catch(()=>{});await context.close();}
}

async function main(){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),process.argv.includes('--streaming')?'code045-r025-ui-':'code045-r023-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser,result={dir,cases:[]};
  try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const theme of ['light','dark'])for(const width of [1280,390]){
    if(process.argv.includes("--quick") && !((runtime==="bundle"&&theme==="dark"&&width===390)||(runtime==="classic"&&theme==="light"&&width===1280)))continue;
    result.cases.push(await (process.argv.includes('--streaming')?streamingScenario(browser,host,runtime,theme,width,dir,process.argv.includes('--baseline')):scenario(browser,host,runtime,theme,width,dir)));console.log(`${runtime} ${theme} ${width} passed`);
  }const m=await host.metrics();assert.equal(m.chatRequests.length,0);assert.equal(m.toolExecutions.length,0);assert.equal(m.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
  }catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;}
  finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
  console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1});
