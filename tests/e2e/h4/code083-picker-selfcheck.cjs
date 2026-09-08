const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const cap=(intents,reason='')=>({schemaVersion:2,capabilityRevision:'synthetic-capability-0001',intents,reason,routeVerified:false,evidence:'adapter-tested'});
const routes=[
 {routeRef:'mr1_synthetic_gpt',connectionId:'manual_synthetic_a',modelId:'gpt-5.5',label:'Synthetic A',reasoning:cap(['default','low','medium','high'])},
 {routeRef:'mr1_synthetic_other',connectionId:'manual_synthetic_b',modelId:'gpt-5.5',label:'Synthetic B',reasoning:cap(['default'],'reasoning_connection_unverified')},
 {routeRef:'mr1_synthetic_astra',connectionId:'manual_synthetic_b',modelId:'gpt-6-astra',label:'Synthetic B',reasoning:cap([],'reasoning_protocol_unsupported')},
 {routeRef:'mr1_synthetic_long',connectionId:'manual_synthetic_b',modelId:'Synthetic-Model-With-A-Long-Name-2026-09-08',label:'Synthetic B',reasoning:cap(['default'],'reasoning_model_unverified')},
].map(r=>({...r,source:'manual',enabled:true,credentialsAvailable:true}));
async function main(){
 const evidenceDir=await fs.mkdtemp(path.join(os.tmpdir(),'code083-picker-'));
 const host=await startIsolatedHost();let browser,result;const cases=[],blockedWrites=[],errors=[];
 try{
  const before=await host.metrics();browser=await chromium.launch({headless:true});
  for(const runtime of ['bundle','classic'])for(const language of ['zh','en'])for(const theme of ['light','dark'])for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:850},serviceWorkers:'block',colorScheme:theme});
   try{
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),method=request.method();
      if(url.pathname==='/api/model-routes'||url.pathname==='/api/model-routes/refresh')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,routingV2:true,catalogRevision:1,routes,ok:true})});
      if(url.pathname==='/api/image-routes/refresh')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,catalogRevision:0,routes:[],ok:true,failures:[]})});
      if(url.pathname==='/api/code/sync-keys')return route.fulfill({status:200,contentType:'application/json',body:'{"tokens":[],"keys":{}}'});
      if(!['127.0.0.1','localhost','::1'].includes(url.hostname))return route.abort();
      if(!['GET','HEAD','OPTIONS'].includes(method)){blockedWrites.push({path:url.pathname,method});return route.abort()}
      return route.continue();
    });
    const initialPreference=width===390?'v2':'legacy';
    await context.addInitScript(({language,theme,token,initialPreference})=>{
      class Renderer{};window.marked={Renderer,setOptions(){},parse:v=>String(v??'')};
      localStorage.setItem('code-key-config',JSON.stringify([
        {key:'sk-synthetic-picker-a',name:'Synthetic A',source:'manual',connectionId:'manual_synthetic_a',enabled:true},
        {key:'sk-synthetic-picker-b',name:'Synthetic B',source:'manual',connectionId:'manual_synthetic_b',enabled:true},
      ]));localStorage.setItem('code-thinking','off');
      if(initialPreference==='v2')localStorage.setItem('code-reasoning-v2',JSON.stringify({schemaVersion:2,intent:'high'}));
      localStorage.setItem('code-model','gpt-5.5');localStorage.setItem('code-model-route-ref','mr1_synthetic_gpt');localStorage.setItem('code-model-route-revision','1');
      localStorage.setItem('code-lang',language);localStorage.setItem('code-theme-mode',theme);localStorage.setItem('code-sidebar-hidden','1');
      localStorage.setItem('code-platform-auth',JSON.stringify({token,userId:'43',username:'synthetic-picker'}));
    },{language,theme,token:host.platformToken,initialPreference});
    await context.addInitScript(()=>{
      window.Code={core:{},features:{},services:{},agent:{},ui:{}};
      let i18nApi;Object.defineProperty(Code.core,'i18n',{configurable:true,get:()=>i18nApi,set(api){i18nApi=Object.freeze({...api,createI18nRuntime(options){const runtime=api.createI18nRuntime(options);window.__code083Lang=runtime.setLang;return runtime}})}});
      let sessionsApi;Object.defineProperty(Code.features,'sessions',{configurable:true,get:()=>sessionsApi,set(api){sessionsApi=Object.freeze({...api,createSessionNavigation(options){window.__code083=options;return api.createSessionNavigation(options)}})}});
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
    await page.waitForFunction(()=>document.documentElement.getAttribute('data-code-phase-one-shell-ready')==='true');
    const trigger=page.locator('#modelPillBtn'),menu=page.locator('#modelReasoningDropdown');
    await page.waitForFunction(()=>document.querySelectorAll('#modelPillDropdown [data-route-ref]').length===4);
    await page.waitForLoadState('networkidle');
    await expect(trigger).toHaveText(language==='zh'?'选择模型':'Select model',{useInnerText:true});
    await expect(trigger).toHaveAttribute('aria-label',language==='zh'?'选择模型':'Select model');
    await trigger.click();await expect(page.locator('#thinkingPillLabel')).toHaveText(language==='zh'?'请先选择模型':'Select a model first');
    await page.locator('#thinkingPillBtn').click();await expect(page.locator('#reasoningPickerStatus')).toHaveText(language==='zh'?'请先选择模型':'Select a model first');
    await expect(page.locator('#thinkingPillDropdown button:disabled')).toHaveCount(4);
    await menu.screenshot({path:path.join(evidenceDir,`${runtime}-${language}-${theme}-${width}-unselected.png`)});
    await page.keyboard.press('Escape');await page.keyboard.press('Escape');
    // Two connections intentionally expose the same model; startup cannot pick one by name.
    await trigger.click();await page.locator('[data-picker-pane=model]').click();
    await page.locator('[data-route-ref=mr1_synthetic_gpt]').click();
    await expect(trigger).toContainText('gpt-5.5');await trigger.click();
    await expect(page.locator('#modelPickerRoot')).toBeVisible();
    await expect(page.locator('#thinkingPillLabel')).toHaveText(initialPreference==='legacy'?(language==='zh'?'旧设置待切换':'Legacy setting'):(language==='zh'?'高':'High'));
    await page.locator('#thinkingPillBtn').click();await expect(page.locator('#thinkingPillDropdown [data-value]')).toHaveCount(4);
    await expect(page.locator('#thinkingPillDropdown [data-value=off]')).toHaveCount(0);
    await page.locator('#thinkingPillDropdown [data-value=high]').click();await expect(menu).toBeHidden();
    assert.equal(await page.evaluate(()=>localStorage.getItem('code-thinking')),'off');
    assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('code-reasoning-v2')).intent),'high');
    await trigger.click();await page.locator('[data-picker-pane=model]').click();
    await page.locator('[data-route-ref=mr1_synthetic_other]').click();await expect(menu).toHaveAttribute('data-pane','effort');
    await expect(page.locator('#thinkingPillDropdown [data-value=high]')).toBeDisabled();await expect(page.locator('#thinkingPillDropdown .selected')).toHaveCount(0);
    await page.keyboard.press('Escape');await expect(page.locator('#modelPickerRoot')).toBeVisible();await page.keyboard.press('Escape');await expect(menu).toBeHidden();await expect(trigger).toBeFocused();
    await trigger.click();await page.locator('[data-picker-pane=model]').click();await page.locator('[data-route-ref=mr1_synthetic_gpt]').click();await expect(menu).toBeHidden();
    await trigger.click();await page.locator('#thinkingPillBtn').click();
    await page.keyboard.press('Home');await expect(page.locator('#modelPickerBack')).toBeFocused();
    await page.keyboard.press('ArrowDown');await expect(page.locator('#thinkingPillDropdown [data-value=default]')).toBeFocused();
    await page.keyboard.press('End');await expect(page.locator('#thinkingPillDropdown [data-value=high]')).toBeFocused();
    await page.evaluate(next=>window.__code083Lang(next),language==='zh'?'en':'zh');
    await expect(page.locator('#thinkingPillDropdown [data-value=default]')).toHaveText(language==='zh'?'Default':'默认');
    await page.evaluate(next=>window.__code083Lang(next),language);
    const geometry=await menu.evaluate(el=>{const box=el.getBoundingClientRect(),dot=getComputedStyle(el.querySelector('.selected'),'::after');return{width:box.width,contained:box.left>=0&&box.right<=innerWidth&&box.top>=0&&box.bottom<=innerHeight,dotWidth:dot.width,dotHeight:dot.height}});
    assert.equal(geometry.width,168);assert(geometry.contained);assert.equal(geometry.dotWidth,'8px');
    await menu.screenshot({path:path.join(evidenceDir,`${runtime}-${language}-${theme}-${width}-effort.png`)});
    await page.locator('#modelPickerBack').click();await page.locator('[data-picker-pane=model]').click();
    const modelGeometry=await menu.boundingBox(),composer=await page.locator('#chatForm').boundingBox();assert(modelGeometry.width<=420);assert(modelGeometry.x>=composer.x-1);await menu.screenshot({path:path.join(evidenceDir,`${runtime}-${language}-${theme}-${width}-models.png`)});
    await page.locator('[data-route-ref=mr1_synthetic_astra]').click();await expect(page.locator('#thinkingPillDropdown button:disabled')).toHaveCount(4);
    await page.locator('#modelPickerBack').click();await page.locator('[data-picker-pane=model]').click();await page.locator('[data-route-ref=mr1_synthetic_gpt]').click();
    await page.reload();await page.waitForFunction(()=>document.documentElement.getAttribute('data-code-phase-one-shell-ready')==='true');
    await page.waitForFunction(()=>document.querySelectorAll('#modelPillDropdown [data-route-ref]').length===4);
    await page.waitForLoadState('networkidle');
    await expect(trigger).toHaveText(language==='zh'?'选择模型':'Select model',{useInnerText:true});
    await trigger.click();await page.locator('[data-picker-pane=model]').click();await page.locator('[data-route-ref=mr1_synthetic_gpt]').click();
    await expect(trigger).toContainText(language==='zh'?'高':'High');
    assert.equal(await page.evaluate(()=>localStorage.getItem('code-thinking')),'off');
    cases.push({runtime,language,theme,width,initialPreference,unselectedGuidance:true,geometry,modelGeometry,legacyOptIn:initialPreference==='legacy',unknownPreservesIntent:true,astraBlocked:true,reload:true,keyboard:true,liveLanguage:true});
   }finally{await context.close()}
  }
  const after=await host.metrics();assert.equal(after.chatRequests.length-before.chatRequests.length,0);assert.equal(after.toolExecutions.length-before.toolExecutions.length,0);assert.deepEqual(blockedWrites,[]);assert.deepEqual(errors,[]);result={ok:true,cases,evidenceDir};
 }finally{
  if(browser)await browser.close();const cleanup=await host.stop();assert(cleanup.childExited&&cleanup.rootRemoved);assert.deepEqual(cleanup.portsClosed,[true,true]);assert.equal(getActiveChildCount(),0);
  await fs.writeFile(path.join(evidenceDir,'result.json'),JSON.stringify({...result,ok:!!result?.ok,cleanup,blockedWrites,errors},null,2));
 }
 console.log(JSON.stringify({ok:true,cases:cases.length,evidenceDir}));
}
main().catch(e=>{console.error(e);process.exitCode=1});
