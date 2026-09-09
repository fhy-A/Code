// Real bundle/classic UI; updater requests are synthetic and never reach an installer.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
const {chromium, expect} = require('@playwright/test');
const {startIsolatedHost, getActiveChildCount} = require('./isolated-host.cjs');
const {createContext, createAudit, waitForRuntime} = require('./execution-trace-skill-model-reminder-selfcheck.cjs');

async function exercise(browser, host, runtime, width, evidenceDir) {
  const audit=createAudit(), context=await createContext(browser,host,runtime,audit,{width,language:width===390?'en':'zh',theme:'light',preserveLanguage:true});
  await context.addInitScript(()=>{
    let api;
    Object.defineProperty(Code.features,'settings',{configurable:true,get:()=>api,set(value){
      api={...value,createSettingsFeature(options){
        const prepare=options.prepareUpdate;
        options.prepareUpdate=()=>window.__updateFailPrepare?Promise.reject(new Error('save failed')):prepare?.();
        const feature=value.createSettingsFeature(options);window.__updateSettings=feature;window.__updateOptions=options;return feature;
      }};
    }});
  });
  let job={status:'idle'}, installed=false, failStop=false, failInstall=false, unknownInstall=false, frozen=true;
  let heldStop=null;
  const calls={stop:0,download:0,restart:0,progress:[],external:[]}, errors=[],checks=[];
  const version='0.99.1', initialVersion='0.6.6';
  await context.route('**/api/{version,check-update,download-progress,download-update,update-stop,restart}*',async route=>{
    const url=new URL(route.request().url()), method=route.request().method();let result,status=200;
    if(url.pathname==='/api/version')result={localVersion:installed?version:initialVersion};
    else if(url.pathname==='/api/check-update')result={updateAvailable:true,remoteVersion:version,isFrozen:frozen,assetName:`Code-v${version}.exe`,assetSize:100};
    else if(url.pathname==='/api/download-progress'){calls.progress.push(url.search);result=job;}
    else if(url.pathname==='/api/update-stop'){assert.equal(method,'POST');calls.stop++;if(heldStop)await heldStop;status=failStop?409:200;result=failStop?{errorCode:'update_stop_failed'}:{ok:true};}
    else if(url.pathname==='/api/download-update'){
      calls.download++;const body=route.request().postDataJSON();assert.equal(body.version,version);
      job={jobId:'update-fixture',version,status:'downloading',stage:'downloading',progress:30};result={ok:true,...job};
    } else {
      calls.restart++;assert.equal(route.request().postDataJSON().jobId,'update-fixture');
      if(unknownInstall){await route.abort('failed');return;}
      if(failInstall){status=500;result={errorCode:'install_launch_failed'};}
      else {installed=true;job={...job,status:'installed'};result={ok:true,status:'installing',jobId:'update-fixture',version};}
    }
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
  const target=new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href;
  async function open(){await page.evaluate(()=>window.__updateSettings.openSettingsPage('update'));await expect(page.locator('#updateStatus')).toBeVisible();}
  async function load(){await page.goto(target);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await open();}
  async function close(){await page.locator('#closeSettingsPage').click();}
  async function available(){await expect(page.locator('#updateCheckBtn')).toBeVisible();await page.locator('#updateCheckBtn').click();await expect(page.locator('#updateDlBtn')).toBeVisible();}
  async function reset(){await close();job={status:'idle'};installed=false;failStop=false;failInstall=false;unknownInstall=false;await open();}
  try {
    if(process.argv.includes('--lifecycle-only')){
      job={jobId:'previous-install',version:initialVersion,status:'installed'};
      await load();let releaseStop;heldStop=new Promise(resolve=>{releaseStop=resolve});
      await page.locator('#updateCheckBtn2').click();await page.locator('#updateDlBtn').click();
      await expect.poll(()=>calls.stop).toBe(1);await close();await open();
      assert.equal(await page.evaluate(()=>window.__updateOptions.state._updateStopping),true);
      await page.locator('#updateCheckBtn2').click();await page.locator('#updateDlBtn').click();
      assert.equal(calls.stop,1);await close();releaseStop();heldStop=null;
      await expect.poll(()=>page.evaluate(()=>window.__updateOptions.state._updateStopping)).toBe(false);
      assert.equal(calls.download,0);assert.equal(calls.restart,0);checks.push('close-reopen-keeps-real-page-paused-until-prepare-settles');

      await page.clock.install();await open();heldStop=new Promise(resolve=>{releaseStop=resolve});
      await page.locator('#updateCheckBtn2').click();await page.locator('#updateDlBtn').click();
      await expect.poll(()=>calls.stop).toBe(2);await page.clock.fastForward(61000);
      await expect(page.locator('#updateStatus [data-i18n="updateStopFailed"]')).toBeVisible();
      assert.equal(await page.evaluate(()=>window.__updateOptions.state._updateStopping),true);
      await page.locator('#updateRetryBtn').click();assert.equal(calls.stop,2);
      releaseStop();heldStop=null;await expect.poll(()=>calls.download).toBe(1);
      assert.equal(calls.restart,0);checks.push('timeout-retry-shares-real-page-preparation');
      job={...job,status:'completed',stage:'completed'};await expect.poll(()=>calls.restart).toBe(1);await page.waitForURL(/updated=/);
      await waitForRuntime(page,runtime);await open();
      await expect(page.locator('#updateStatus [data-i18n="upToDate"]')).toBeVisible();
      checks.push('installed-previous-version-to-new-job-single-click');
      assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
      return {runtime,width,calls,checks,errors};
    }
    await load();await available();
    await page.evaluate(()=>{const button=document.getElementById('updateDlBtn');button.click();button.click();});
    await expect.poll(()=>calls.download).toBe(1);assert.equal(calls.stop,1);
    job={...job,stage:'verifying',progress:100};
    await expect(page.locator('#updateStatus [data-i18n="updateVerifying"]')).toBeVisible();
    job={...job,status:'completed',stage:'completed'};
    await expect.poll(()=>calls.restart).toBe(1);await page.waitForURL(/updated=/);
    await waitForRuntime(page,runtime);await open();await expect(page.locator('#updateStatus [data-i18n="upToDate"]')).toBeVisible();
    assert(calls.progress.some(query=>query==='?id=update-fixture'));checks.push('single-click-double-click-fixed-job');
    await page.screenshot({path:path.join(evidenceDir,`${runtime}-${width}-installed.png`),animations:'disabled'});

    await reset();await available();await page.locator('#updateDlBtn').click();await expect.poll(()=>calls.download).toBe(2);
    await close();job={...job,status:'completed',stage:'completed'};await open();
    await expect(page.locator('#updateRestartBtn')).toBeVisible();assert.equal(calls.restart,1);checks.push('close-reopen-does-not-install');
    await page.reload();await waitForRuntime(page,runtime);await open();
    await expect(page.locator('#updateRestartBtn')).toBeVisible();assert.equal(calls.restart,1);checks.push('refresh-does-not-install');
    const observer=await context.newPage();await observer.goto(target);await waitForRuntime(observer,runtime);
    await observer.evaluate(()=>window.__updateSettings.openSettingsPage('update'));
    await expect(observer.locator('#updateRestartBtn')).toBeVisible();assert.equal(calls.restart,1);
    await observer.close();checks.push('second-tab-completed-job-needs-explicit-click');

    failInstall=true;await page.locator('#updateRestartBtn').click();await expect.poll(()=>calls.restart).toBe(2);
    await expect(page.locator('#updateStatus [data-i18n="updateErrorInstall"]')).toBeVisible();
    assert.equal(calls.download,2);await expect(page.locator('#updateRestartBtn')).toBeVisible();checks.push('verified-job-retry-keeps-file');
    failInstall=false;unknownInstall=true;await page.locator('#updateRestartBtn').click();await expect.poll(()=>calls.restart).toBe(3);
    await page.clock.install();await page.clock.fastForward(91000);
    await expect(page.locator('#updateStatus [data-i18n="updateRestartUnconfirmed"]')).toBeVisible();
    await expect(page.locator('#updateRecheckBtn')).toBeVisible();checks.push('transport-unknown-bounded-wait');
    for(const action of await page.locator('#updateActions > *').all()){
      const fits=await action.evaluate(el=>{const a=el.getBoundingClientRect(),p=el.parentElement.getBoundingClientRect();return a.right<=p.right+1&&a.left>=p.left-1&&el.scrollWidth<=el.clientWidth+1&&el.scrollHeight<=el.clientHeight+1});
      assert(fits,'update actions must stay readable at the viewport width');
    }
    await page.screenshot({path:path.join(evidenceDir,`${runtime}-${width}-timeout.png`),animations:'disabled'});
    await page.locator('#updateRecheckBtn').click();assert.equal(calls.restart,3);checks.push('recheck-does-not-restart');
    await close();await page.clock.resume();

    job={status:'idle'};unknownInstall=false;failStop=true;await open();await available();await page.locator('#updateDlBtn').click();
    await expect(page.locator('#updateStatus [data-i18n="updateStopFailed"]')).toBeVisible();
    assert.equal(calls.download,2);assert.equal(calls.restart,3);checks.push('stop-failure-no-download-or-install');

    await reset();await page.evaluate(()=>{window.__updateFailPrepare=true});await available();await page.locator('#updateDlBtn').click();
    await expect(page.locator('#updateStatus [data-i18n="updateStopFailed"]')).toBeVisible();
    assert.equal(calls.download,2);assert.equal(calls.restart,3);checks.push('page-save-failure-no-download-or-install');
    await page.evaluate(()=>{window.__updateFailPrepare=false});

    await reset();let releaseStop;heldStop=new Promise(resolve=>{releaseStop=resolve});const beforeStop=calls.stop;
    await available();await page.locator('#updateDlBtn').click();await expect.poll(()=>calls.stop).toBe(beforeStop+1);
    await close();releaseStop();heldStop=null;await page.waitForLoadState('networkidle');await open();
    await expect(page.locator('#updateCheckBtn')).toBeVisible();assert.equal(calls.download,2);assert.equal(calls.restart,3);
    checks.push('close-during-stop-invalidates-late-download-intent');

    await reset();await available();await page.locator('#updateDlBtn').click();await expect.poll(()=>calls.download).toBe(3);
    job={...job,jobId:'unrelated-job',version:'0.99.2',status:'completed'};
    await expect(page.locator('#updateStatus [data-i18n="updateErrorMetadata"]')).toBeVisible();
    assert.equal(calls.restart,3);checks.push('unrelated-job-cannot-auto-install');

    await reset();frozen=false;await page.locator('#updateCheckBtn').click();
    await expect(page.locator('#updateActions a')).toBeVisible();assert.equal(await page.locator('#updateDlBtn').count(),0);checks.push('source-mode-manual-download');
    await page.evaluate(()=>{window.__updateOptions.setLang('en');window.__updateOptions.applyI18n();});
    await expect(page.locator('[data-i18n="openDownloadPage"]')).toHaveText('Open download page');
    await page.reload();await waitForRuntime(page,runtime);await open();
    await page.locator('#updateCheckBtn').click();
    await expect(page.locator('[data-i18n="openDownloadPage"]')).toHaveText('Open download page');
    await page.evaluate(()=>{window.__updateOptions.setLang('zh');window.__updateOptions.applyI18n();});
    await expect(page.locator('[data-i18n="openDownloadPage"]')).toHaveText('打开下载页面');
    checks.push('language-switch-and-reload');
    assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
    return {runtime,width,calls,checks,errors};
  } finally {await context.close();}
}

async function main(){
  const evidenceDir=await fs.mkdtemp(path.join(os.tmpdir(),'code086-ui-')),host=await startIsolatedHost({disableRoutingV2:true});
  let browser,result={evidenceDir,cases:[]};
  try{
    const before=await host.metrics();browser=await chromium.launch({headless:true});
    const views=process.argv.includes('--lifecycle-only')?[['bundle',1280]]:[['bundle',1280],['classic',390]];
    for(const [runtime,width] of views)result.cases.push(await exercise(browser,host,runtime,width,evidenceDir));
    const after=await host.metrics();
    for(const key of ['chatRequests','toolExecutions','modelRouteRequests'])assert.equal(after[key].length-before[key].length,0);
    for(const key of ['agentRuns','runtimeRuns'])assert.equal(after.production[key].length-before.production[key].length,0);
    result.sideEffects={chat:0,tools:0,modelRoutes:0,agentRuns:0,runtimeRuns:0,realUpdateRequests:0};result.ok=true;
  }catch(error){result.ok=false;result.error=String(error.stack);process.exitCode=1;}
  finally{
    if(browser)await browser.close();const cleanup=await host.stop();
    result.cleanup={childExited:cleanup.childExited,portsClosed:cleanup.portsClosed,rootRemoved:cleanup.rootRemoved,errors:cleanup.cleanupErrors,activeChildren:getActiveChildCount()};
    if(!cleanup.childExited||!cleanup.rootRemoved||!cleanup.portsClosed.every(Boolean)||cleanup.cleanupErrors.length||getActiveChildCount())process.exitCode=1;
    await fs.writeFile(path.join(evidenceDir,'result.json'),JSON.stringify(result,null,2));
  }
  console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
