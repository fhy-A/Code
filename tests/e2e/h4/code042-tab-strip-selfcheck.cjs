const assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code042-tab-strip-')),host=await startIsolatedHost({disableRoutingV2:true});console.log(dir);
 let browser,context,page;const result={dir,cases:[],errors:[]};
 const touchOnly=process.argv.includes('--touch-only');
 const api=async(url,body,method='POST')=>{const r=await fetch(host.ready.codeUrl+url,body?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});assert(r.ok,await r.clone().text());return r.json();};
 try{
  const names=['short.py','notes.md','a-very-long-file-name-with-many-components.archive.tar.gz','中文很长的类型声明文件测试.d.ts','README','.env','src/one/settings.json','src/two/settings.json',...Array.from({length:12},(_,i)=>`source-component-${i+1}.test.js`)];
  const paths=names.map(name=>path.join(host.projectDir,name));
  for(const [i,p] of paths.entries()){await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,`fixture ${i}\n`);}
  const a=await api('/api/sessions',{title:'Tab strip A',cwd:host.projectDir}),b=await api('/api/sessions',{title:'Tab strip B',cwd:host.projectDir});
  const binding=await api('/api/preview/context',{sessionId:a.id}),id='4'.repeat(32),canonical=paths[0].toLowerCase(),diff='--- a/short.py\n+++ b/short.py\n@@ -1 +1 @@\n-before\n+after\n';
  const record={version:7,id,sessionId:a.id,status:'completed',runKind:'foreground',clientRequestId:'tabs',reviewBinding:{schema:'code-run-review-binding/v1',dataSourceId:binding.dataSourceId,sessionId:a.id,sessionInstanceId:binding.sessionInstanceId,rootRunId:id,rootClientRequestId:'tabs',originMessageId:'tabs-message',originRoot:host.projectDir},toolExecutions:{call:{name:'write_file',status:'completed',operationId:'op',result:{ok:true,action:'write_file',replayed:false,diff,fileChange:{schema:'code-file-change-receipt/v1',canonicalPath:canonical,fileKey:sha(JSON.stringify(canonical)),kind:'update',entityKind:'file',operationId:'op',diffSemantics:'normalized-lines',diffSha256:sha(diff),bodyState:'diff'}}}},result:{},steerReceipts:[]};
  await fs.mkdir(path.join(host.dataDir,'agent-runs'),{recursive:true});await fs.writeFile(path.join(host.dataDir,'agent-runs',id+'.json'),JSON.stringify(record));
  const saved=await api('/api/sessions/'+a.id);await api('/api/sessions/'+a.id,{title:'Tab strip A',expectedRevision:saved.revision,messages:[{role:'user',content:'Tab fixture',meta:{recordedChangeReview:{rootRunId:id}}},{role:'assistant',content:'Complete',meta:{agentRunId:id,_agentRunTerminal:true}}]},'PUT');
  const summaryResponse=await fetch(host.ready.codeUrl+`/api/agent/runs/${id}/file-changes?`+new URLSearchParams({dataSourceId:binding.dataSourceId,sessionId:a.id,sessionInstanceId:binding.sessionInstanceId}));
  result.fixtureSummary={status:summaryResponse.status,body:await summaryResponse.json()};assert(summaryResponse.ok,JSON.stringify(result.fixtureSummary));assert.equal(result.fixtureSummary.body.operations.length,1);
  browser=await chromium.launch({headless:true});
  for(const runtime of touchOnly?['bundle']:['bundle','classic']){
   context=await browser.newContext({viewport:{width:touchOnly?390:1600,height:1000},hasTouch:touchOnly,isMobile:touchOnly,serviceWorkers:'block'});const checks=[],reads=[];
   await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(!['127.0.0.1','localhost','::1'].includes(url.hostname))return route.abort();
    if(url.pathname==='/api/image-routes/refresh')return route.fulfill({json:{version:1,routes:[],ok:true}});
    if(url.pathname==='/api/code/sync-keys')return route.fulfill({json:{tokens:[],keys:{}}});
    if(url.pathname==='/api/preview/file')reads.push(url.searchParams.get('path'));
    if(url.pathname.endsWith('/app.js')||url.pathname.endsWith('/code.bundle.js')){
     const response=await route.fetch(),source=await response.text();assert(source.includes('previewFeature.bind();'));
     return route.fulfill({response,body:source.replace('previewFeature.bind();','previewFeature.bind(); window.__tabStripHarness={feature:previewFeature};')});
    }
    return route.continue();
   });
   await context.addInitScript(({sid,token})=>{window.marked={Renderer:class{},setOptions(){},parse:text=>String(text)};localStorage.setItem('code-key-config','[]');localStorage.setItem('code-platform-auth',JSON.stringify({token,userId:'42',username:'fixture'}));if(!sessionStorage.getItem('tabs-seeded')){localStorage.setItem('code-lang','en');localStorage.setItem('code-last-session',sid);sessionStorage.setItem('tabs-seeded','1');}localStorage.setItem('code-foreground-view','session');localStorage.setItem('code-expanded-project-sessions',JSON.stringify({__unassigned_sessions__:true}));},{sid:a.id,token:host.platformToken});
   page=await context.newPage();page.on('pageerror',error=>result.errors.push(String(error)));
   await page.goto(host.ready.codeUrl+(runtime==='classic'?'/dist/frontend/index.classic.html':'/'));await page.waitForLoadState('networkidle');
   const tabs=page.locator('[data-preview-tab]'),toggle=page.locator('#previewTabListToggle'),menu=page.locator('#previewTabListMenu'),active=page.locator('[data-preview-tab][aria-selected=true]');
   const resize=async width=>{await page.evaluate(width=>window.__tabStripHarness.feature.applyPreviewWidth(width,false),width);await expect.poll(async()=>Math.round((await page.locator('#previewPane').boundingBox()).width)).toBe(width);};
   const shot=async suffix=>{await page.mouse.move(500,20);await page.screenshot({animations:'disabled',path:path.join(dir,`${runtime}-${suffix}.png`)});};
   const layout=()=>page.evaluate(()=>{const strip=document.querySelector('#previewTabs'),items=[...strip.children],bounds=strip.getBoundingClientRect(),current=strip.querySelector('.active')?.getBoundingClientRect();return {width:document.querySelector('#previewPane').getBoundingClientRect().width,rowCount:new Set(items.map(e=>Math.round(e.getBoundingClientRect().top))).size,widths:items.map(e=>e.getBoundingClientRect().width),closeFits:items.every(e=>{const p=e.getBoundingClientRect(),c=e.querySelector('.preview-tab-close').getBoundingClientRect();return c.width>=28&&c.left>=p.left&&c.right<=p.right+1;}),activeVisible:!current||current.left>=bounds.left-1&&current.right<=bounds.right+1,scroll:strip.scrollLeft,menuInPane:(()=>{const m=document.querySelector('#previewTabListMenu').getBoundingClientRect(),p=document.querySelector('#previewPane').getBoundingClientRect();return m.left>=p.left&&m.right<=p.right+1&&m.bottom<=innerHeight;})()};});
   if(touchOnly){
    assert(await page.evaluate(()=>matchMedia('(pointer:coarse)').matches));await page.locator('.file-item[data-path="short.py"]').tap();await expect(tabs).toHaveCount(1);
    await page.evaluate(async paths=>{for(const p of paths)await window.__tabStripHarness.feature.loadFile(p,undefined,{newTab:true});},paths.slice(1,5));await expect(tabs).toHaveCount(5);await expect(toggle).toBeVisible();
    const closeBox=await page.locator('.preview-tab.active .preview-tab-close').boundingBox();assert(closeBox.width>=28&&closeBox.height>=36);assert.equal(Math.round((await layout()).width),390);
    await toggle.tap();await expect(menu).toBeVisible();assert((await layout()).menuInPane);await shot('touch-390-menu');const target=await menu.locator('button').first().getAttribute('data-preview-menu-tab');await menu.locator('button').first().tap();await expect(active).toHaveAttribute('data-preview-tab',target);await expect(tabs).toHaveCount(5);assert((await layout()).activeVisible);
    await page.locator('.preview-tab.active .preview-tab-close').tap();await expect(tabs).toHaveCount(4);await expect(page.locator(`[data-preview-tab="${target}"]`)).toHaveCount(0);await expect(page.locator('.workbench')).toHaveClass(/preview-open/);await shot('touch-390-close-own-tab');
    checks.push('390px coarse-pointer touch: native tap opens list, selects existing tab and closes only that tab; fixed close target is at least 28x36px');result.cases.push({runtime:'bundle-touch',checks,requests:reads.length});await context.close();context=null;continue;
   }
   await page.locator('.file-item[data-path="short.py"]').click();await expect(tabs).toHaveCount(1);await expect(page.locator('#filePreview')).toContainText('fixture 0');await resize(720);await expect(toggle).toBeHidden();assert((await layout()).widths[0]<=236);await shot('one-tab-720-en-light');
   await page.locator('.file-item[data-path="notes.md"]').click({modifiers:['Control']});await expect(tabs).toHaveCount(2);await resize(250);await expect(toggle).toBeVisible();await expect(page.locator('#previewNewTab')).toBeVisible();assert((await layout()).closeFits);await shot('two-tabs-250-en-light');
   checks.push('1/2 actual file gestures; short tabs do not fill wide panel; at 250px fixed plus and close buttons retain space and overflow exposes the list');
   // Populate the remaining descriptors through the production explicit-open route and real isolated API.
   await page.evaluate(async paths=>{for(const p of paths)await window.__tabStripHarness.feature.loadFile(p,undefined,{newTab:true});},paths.slice(2,12));
   await expect(tabs).toHaveCount(12);await resize(460);await expect(toggle).toBeVisible();assert.equal((await layout()).rowCount,1);
   const inactive=page.locator('.preview-tab:not(.active)').last(),passiveColor=await inactive.evaluate(el=>getComputedStyle(el).backgroundColor),activeColor=await active.locator('..').evaluate(el=>getComputedStyle(el).backgroundColor);assert.notEqual(passiveColor,activeColor);
   await inactive.hover();await expect.poll(()=>inactive.evaluate(el=>getComputedStyle(el).backgroundColor)).not.toBe(passiveColor);
   await page.screenshot({animations:'disabled',path:path.join(dir,`${runtime}-dozen-460-en-light-hover.png`)});
   await page.keyboard.press('Tab');await inactive.locator('.preview-tab-close').focus();assert(await inactive.locator('.preview-tab-close').evaluate(el=>el.matches(':focus-visible')&&getComputedStyle(el).outlineStyle==='solid'));
   await page.screenshot({animations:'disabled',path:path.join(dir,`${runtime}-dozen-460-en-light-inactive-focus.png`)});
   await toggle.click();await page.keyboard.press('Home');const beforeAppend=await page.evaluate(()=>document.activeElement.dataset.previewMenuTab);
   await page.evaluate(p=>window.__tabStripHarness.feature.loadFile(p,undefined,{newTab:true}),paths[12]);await expect(menu.locator('button')).toHaveCount(13);await expect(menu.locator(`[data-preview-menu-tab="${beforeAppend}"]`)).toBeFocused();await page.keyboard.press('Escape');
   checks.push('dozen-tab layout has distinct active/hover/keyboard-focus states; an explicit async tab append preserves the open menu focus');
   await page.evaluate(async paths=>{for(const p of paths)await window.__tabStripHarness.feature.loadFile(p,undefined,{newTab:true});},paths.slice(13));
   await expect(tabs).toHaveCount(20);await page.locator('[data-recorded-review]').first().click();await expect(tabs).toHaveCount(21);await expect(page.locator('.review-detail')).toContainText('after');
   const ids=await tabs.evaluateAll(nodes=>nodes.map(n=>n.dataset.previewTab));
   await page.evaluate(()=>window.__tabStripHarness.feature.stopAutoRefresh());
   for(const width of [250,390,460,720]){
    await resize(width);await expect(toggle).toBeVisible();await active.click();
    const geometry=await layout();assert.equal(geometry.rowCount,1);assert(geometry.closeFits&&geometry.activeVisible);assert(geometry.widths.every(w=>w>=88&&w<=236));
    const before=reads.length;await toggle.click();await expect(menu.locator('[role=menuitemradio]')).toHaveCount(21);assert((await layout()).menuInPane);await page.waitForTimeout(40);assert.equal(reads.length,before);
    assert.equal(await menu.locator('[aria-checked=true]').count(),1);await expect(menu).toContainText('a-very-long-file-name-with-many-components.archive.tar.gz');await expect(menu).toContainText('中文很长的类型声明文件测试.d.ts');
    if(width===250||width===460)await shot(`many-${width}-en-light-menu`);
    if(width===460){await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowDown');await shot('many-460-en-light-menu-long-names');}
    await page.keyboard.press('Escape');await expect(toggle).toBeFocused();await expect(menu).toBeHidden();
   }
   checks.push('20 files plus review remain one row at real 250/390/460/720px; list stays fixed/in bounds and does not fetch background bodies');
   for(const [index,extension] of [[2,'.tar.gz'],[3,'.d.ts'],[6,'.json'],[7,'.json']]){
    await toggle.click();await menu.locator(`[data-preview-menu-tab="${ids[index]}"]`).click();await expect(active).toHaveAttribute('data-preview-tab',ids[index]);
    await expect(active.locator('.preview-tab-extension')).toHaveText(extension);assert((await layout()).activeVisible);await expect(active).toHaveAttribute('title',paths[index]);
    assert(await active.locator('.preview-tab-extension').evaluate(el=>el.scrollWidth<=el.clientWidth),`extension must be fully visible: ${extension}`);
    if(index===6||index===7)assert(await active.locator('.preview-tab-parent').evaluate(el=>el.scrollWidth<=el.clientWidth),'short distinguishing parent must be fully visible');
    if(index===2){await expect(page.locator('#filePreview')).not.toHaveClass(/\bloading\b/);await shot('long-compound-extension-visible');}
   }
   await expect(tabs.nth(4).locator('.preview-tab-extension')).toHaveCount(0);await expect(tabs.nth(5).locator('.preview-tab-extension')).toHaveCount(0);
   await expect(tabs.nth(6)).toContainText(' · one');await expect(tabs.nth(7)).toContainText(' · two');
   await expect(tabs.nth(6)).toHaveAttribute('aria-label',paths[6]);
   checks.push('long Chinese/compound extensions remain separate and visible; no-extension/dotfiles and same-name parent labels/full-path accessibility preserved');
   await page.evaluate(()=>window.__tabStripHarness.feature.stopAutoRefresh());let before=reads.length;
   await toggle.focus();await page.keyboard.press('ArrowDown');await expect(menu.locator('button').first()).toBeFocused();await page.keyboard.press('End');await expect(menu.locator('button').last()).toBeFocused();await page.keyboard.press('Home');await expect(menu.locator('button').first()).toBeFocused();assert.equal(reads.length,before);
   await page.keyboard.press('Escape');await expect(toggle).toBeFocused();await toggle.click();await page.locator('#prompt').click();await expect(menu).toBeHidden();await expect(page.locator('#prompt')).toBeFocused();
   checks.push('list arrow/Home/End keys navigate without activation; Escape returns focus and outside click dismisses');
   await toggle.click();await menu.locator(`[data-preview-menu-tab="review"]`).click();await expect(active).toHaveAttribute('data-preview-tab','review');
   await page.locator('#previewTabs').evaluate(el=>{el.scrollLeft=600;});const left=await page.locator('#previewTabs').evaluate(el=>el.scrollLeft);
   await page.locator('[data-review-action=toggle]').first().click();await expect.poll(()=>page.locator('#previewTabs').evaluate(el=>el.scrollLeft)).toBe(left);
   await toggle.click();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');
   const menuFocus=await page.evaluate(()=>{window.__stableMenuButton=document.activeElement;return document.activeElement.dataset.previewMenuTab;});const menuTop=await menu.evaluate(el=>el.scrollTop);
   before=reads.length;await page.evaluate(async()=>{await Promise.resolve();window.__tabStripHarness.feature.refreshLanguage();});assert.equal(reads.length,before);assert(await page.evaluate(()=>document.activeElement===window.__stableMenuButton));assert.equal(await menu.evaluate(el=>el.scrollTop),menuTop);assert.equal(await page.locator('#previewTabs').evaluate(el=>el.scrollLeft),left);
   await resize(390);await expect(menu.locator(`[data-preview-menu-tab="${menuFocus}"]`)).toBeFocused();assert((await layout()).menuInPane);assert.equal(await page.locator('#previewTabs').evaluate(el=>el.scrollLeft),left);
   checks.push('review expansion and asynchronous production redraw preserve manual strip offset and exact menu focus/scroll; resize retains both');
   await page.keyboard.press('Escape');await page.locator('#previewTabs').hover();await page.mouse.wheel(0,220);await expect.poll(()=>page.locator('#previewTabs').evaluate(el=>el.scrollLeft)).toBeGreaterThan(left);
   await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="dark"]').click());
   await toggle.click();await expect(toggle).toHaveAttribute('aria-label','标签列表');await expect(menu.locator('button').last()).toContainText('审查');await shot('many-390-zh-dark-menu');await page.keyboard.press('Escape');
   await page.setViewportSize({width:390,height:900});await expect.poll(async()=>Math.round((await page.locator('#previewPane').boundingBox()).width)).toBe(390);await active.click();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');await expect(active).toBeFocused();assert(await active.evaluate(el=>el.matches(':focus-visible')));await shot('viewport-390-zh-dark-focus');
   await page.setViewportSize({width:1600,height:1000});await resize(460);await page.evaluate(()=>document.documentElement.style.zoom='1.25');await toggle.click();assert((await layout()).menuInPane);await shot('125-percent-css-zoom');await page.keyboard.press('Escape');await page.evaluate(()=>document.documentElement.style.zoom='');
   checks.push('native strip wheel, Chinese dark labels, narrow viewport, focus ring and 125% CSS zoom remain usable; zoom restored');
   await toggle.click();await menu.locator(`[data-preview-menu-tab="${ids[0]}"]`).click();await expect(active).toHaveAttribute('data-preview-tab',ids[0]);await expect(tabs).toHaveCount(21);assert((await layout()).activeVisible);
   await page.locator('.preview-tab.active .preview-tab-close').click();await expect(active).toHaveAttribute('data-preview-tab','review');await expect(tabs).toHaveCount(20);
   checks.push('explicit list selection reuses existing tab, reveals it and preserves mixed file/review MRU on close');
   await toggle.click();await menu.locator(`[data-preview-menu-tab="${ids[1]}"]`).evaluate(el=>window.__staleMenuButton=el);
   await page.evaluate(id=>window.__tabStripHarness.feature.closeTab(id),ids[1]);await expect(menu).toBeHidden();before=reads.length;await page.evaluate(()=>window.__staleMenuButton.click());await page.waitForTimeout(30);assert.equal(reads.length,before);await expect(tabs).toHaveCount(19);
   await toggle.click();await menu.locator('button').first().evaluate(el=>window.__staleMenuButton=el);await page.locator('#togglePreview').click();await expect(menu).toBeHidden();await page.evaluate(()=>window.__staleMenuButton.click());await expect(page.locator('.workbench')).not.toHaveClass(/preview-open/);
   await page.locator('#togglePreview').click();await toggle.click();await menu.locator('button').first().evaluate(el=>window.__staleMenuButton=el);await page.locator(`.session-main[data-session-id="${b.id}"]`).click();await expect(tabs).toHaveCount(0);await expect(menu).toBeHidden();before=reads.length;await page.evaluate(()=>window.__staleMenuButton.click());await page.waitForTimeout(30);assert.equal(reads.length,before);await expect(tabs).toHaveCount(0);
   checks.push('deleted target, collapsed pane and Session change invalidate detached menu actions without stale navigation/read');
   await page.waitForTimeout(350);await page.locator(`.session-main[data-session-id="${a.id}"]`).click();await expect(tabs).toHaveCount(18);await expect(page.locator('[data-preview-tab=review]')).toHaveCount(0);
   await page.evaluate(()=>document.querySelector('[data-settings-lang="en"]').click());await expect(toggle).toHaveAttribute('aria-label','Tab list');await page.reload();await expect(tabs).toHaveCount(18);await expect(toggle).toHaveAttribute('aria-label','Tab list');await toggle.click();await expect(menu).toHaveAttribute('aria-label','Open tabs');await shot('restored-english-list');await page.keyboard.press('Escape');
   await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());await expect(toggle).toHaveAttribute('aria-label','标签列表');await expect(page.locator('#closePreview')).toHaveCount(0);
   checks.push('Session return/reload restores existing file descriptors only; new list labels switch immediately, persist English through reload and return to Chinese');
   await page.locator('#previewNewTab').click();const blankA=await active.getAttribute('data-preview-tab');await page.locator('#previewNewTab').click();const blankB=await active.getAttribute('data-preview-tab');await expect(tabs).toHaveCount(20);await page.locator('[data-recorded-review]').first().click();await expect(tabs).toHaveCount(21);await expect(active).toHaveAttribute('data-preview-tab','review');await page.locator('#previewNewTab').click();await expect(tabs).toHaveCount(21);await expect(active).toHaveAttribute('data-preview-tab','review');
   await page.locator(`[data-preview-tab="${blankB}"]`).click();await expect(page.locator('[data-picker-query]')).toBeVisible();await page.locator('.preview-tab.active .preview-tab-close').click();await expect(active).toHaveAttribute('data-preview-tab','review');await page.locator('.preview-tab.active .preview-tab-close').click();await expect(active).toHaveAttribute('data-preview-tab',blankA);await expect(page.locator('[data-picker-query]')).toBeVisible();
   checks.push('18 files plus 2 blanks share 20 slots with one extra review; plus at cap preserves review; blank close returns review and review close follows mixed MRU to remaining blank');
   result.cases.push({runtime,checks,requests:reads.length});await context.close();context=null;
  }
  assert.deepEqual(result.errors,[]);result.ok=true;
 }catch(error){result.ok=false;result.error=String(error.stack);if(page&&!page.isClosed())await page.screenshot({path:path.join(dir,'failure.png')}).catch(()=>{});process.exitCode=1;}
 finally{if(context)await context.close();if(browser)await browser.close();const cleanup=await host.stop();result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
