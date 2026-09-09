const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
const {chromium, expect} = require('@playwright/test');
const {startIsolatedHost, getActiveChildCount} = require('./isolated-host.cjs');
const models = ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-v4-flash-vision-exp'];
const intents = ['default', 'low', 'medium', 'high'];

async function main() {
  const evidenceDir = await fs.mkdtemp(path.join(os.tmpdir(), 'code083-static-routing-'));
  const host = await startIsolatedHost();
  const cases = [], errors = [];
  let browser, success = false;
  try {
    await host.command('enable-static-reasoning');
    await host.releaseModel();
    browser = await chromium.launch({headless:true});
    for (const runtime of ['bundle', 'classic']) {
      const context = await browser.newContext({viewport:{width:1280,height:850},serviceWorkers:'block'});
      try {
        await context.addInitScript(({key,token,runtime})=>{
          class Renderer{};window.marked={Renderer,setOptions(){},parse:v=>String(v??'')};
          localStorage.setItem('code-key-config',JSON.stringify([{name:'Synthetic static',key,source:'manual',enabled:true}]));
          localStorage.setItem('code-platform-auth',JSON.stringify({token,userId:'7',username:'synthetic-static'}));
          localStorage.setItem('code-reasoning-v2',JSON.stringify({schemaVersion:2,intent:'default'}));
          localStorage.setItem('code-lang',runtime==='bundle'?'zh':'en');
          localStorage.setItem('code-theme-mode',runtime==='bundle'?'light':'dark');
        },{key:host.syntheticKey,token:host.platformToken,runtime});
        await context.route('**/*',async route=>{
          const req=route.request(),url=new URL(req.url());
          if(!['127.0.0.1','localhost','::1'].includes(url.hostname))return route.abort();
          // Only configure the synthetic connection destination. All catalog
          // responses, capability projections, UI and requests are production.
          if(req.method()==='POST' && ['/api/model-routes/refresh','/api/agent/runs'].includes(url.pathname)) {
            const body=req.postDataJSON();body.baseUrl=host.ready.fakeUrl;
            return route.continue({postData:JSON.stringify(body)});
          }
          if(url.pathname==='/proxy/models')return route.continue({headers:{...req.headers(),'x-base-url':host.ready.fakeUrl}});
          return route.continue();
        });
        const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
        await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);
        await page.waitForFunction(()=>document.documentElement.getAttribute('data-code-phase-one-shell-ready')==='true');
        await page.locator('#baseUrl').evaluate((el,url)=>{el.value=url;},host.ready.fakeUrl);
        await expect.poll(async()=>{
          const response=await page.request.get(host.ready.codeUrl+'/api/model-routes');
          const body=await response.json();return body.routes?.filter(r=>r.modelId==='deepseek-v4-pro').length||0;
        },{timeout:15000}).toBeGreaterThan(0);
        await page.waitForLoadState('networkidle');
        const catalog=await (await page.request.get(host.ready.codeUrl+'/api/model-routes')).json();
        for(const route of catalog.routes.filter(r=>models.includes(r.modelId))) {
          assert.deepEqual(route.reasoning.intents,intents);
          assert.equal(route.reasoning.routeVerified,false);
        }
        const trigger=page.locator('#modelPillBtn'),menu=page.locator('#modelReasoningDropdown');
        for(const model of models) for(const intent of intents) {
          if(!(await menu.isVisible()))await trigger.click();
          if(await menu.getAttribute('data-pane')!=='root')await page.locator('#modelPickerBack').click();
          await page.locator('[data-picker-pane=model]').click();
          await page.locator(`#modelPillDropdown [data-model="${model}"]`).first().click();
          if(!(await menu.isVisible()))await trigger.click();
          if(await menu.getAttribute('data-pane')!=='effort')await page.locator('#thinkingPillBtn').click();
          const option=page.locator(`#thinkingPillDropdown [data-value=${intent}]`);
          await expect(option).toBeEnabled();await option.click();
          const marker=`H4_STATIC_SEND_${runtime}_${model}_${intent}`;
          const createdPromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/agent/runs'&&r.request().method()==='POST');
          await page.locator('#prompt').fill(marker);await page.locator('#sendBtn').click();
          const response=await createdPromise,created=await response.json();
          assert.equal(response.status(),201,JSON.stringify(created));
          await expect.poll(async()=>{
            const snapshot=await (await page.request.get(host.ready.codeUrl+'/api/agent/runs/'+created.agentRunId)).json();
            return snapshot.status;
          },{timeout:15000}).toBe('completed');
          await expect(page.locator('#sendBtn')).not.toHaveClass(/running/);
          const metrics=await host.metrics();
          const requests=metrics.chatRequests.filter(r=>r.scenario==='static-reasoning' && r.payload.messages.some(m=>m.content===marker));
          assert.equal(requests.length,1);
          const wire=requests[0].payload;assert.equal(wire.model,model);
          if(intent==='default') {assert.equal(wire.thinking,undefined);assert.equal(wire.reasoning_effort,undefined);}
          else {assert.deepEqual(wire.thinking,{type:'enabled'});assert.equal(wire.reasoning_effort,{low:'low',medium:'high',high:'max'}[intent]);}
          assert.equal(wire.reasoningSelection,undefined);
          cases.push({runtime,model,intent,routeVerified:false,completed:true});
        }
        await trigger.click();await page.locator('#thinkingPillBtn').click();
        await menu.screenshot({path:path.join(evidenceDir,runtime+'.png')});
      } finally {await context.close();}
    }
    const metrics=await host.metrics();assert.equal(metrics.toolExecutions.length,0);assert.deepEqual(errors,[]);
    const registry=JSON.parse(await fs.readFile(path.join(host.dataDir,'model-route-registry.json'),'utf8'));
    assert.equal(Object.keys(registry.reasoningContracts||{}).length,0);
    success=true;
  } finally {
    if(browser)await browser.close();
    const cleanup=await host.stop();assert(cleanup.childExited&&cleanup.rootRemoved);assert.deepEqual(cleanup.portsClosed,[true,true]);assert.equal(getActiveChildCount(),0);
    await fs.writeFile(path.join(evidenceDir,'result.json'),JSON.stringify({ok:success,cases,errors,cleanup},null,2));
  }
  console.log(JSON.stringify({ok:true,cases:cases.length,evidenceDir}));
}
main().catch(error=>{console.error(error);process.exitCode=1});
