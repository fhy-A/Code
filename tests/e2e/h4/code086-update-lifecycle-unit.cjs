// Deterministic UI timings against the actual settings feature; no HTTP/processes.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const deferred = () => { let resolve, reject; const promise = new Promise((a,b)=>{resolve=a;reject=b}); return {promise,resolve,reject}; };
const flush = () => new Promise(setImmediate);

function harness({job={status:'idle'}, remoteVersion='2.0.0', prepare=async()=>{}}={}) {
  const elements={}, timers=new Map(), calls=[], pauses=[], versions=[], navigations=[];
  let now=0, nextTimer=0;
  class Element {
    constructor(id){this.id=id;this.listeners={};this.style={};this.dataset={};this.classes=new Set();this.children=[];
      this.classList={add:(...v)=>v.forEach(x=>this.classes.add(x)),remove:(...v)=>v.forEach(x=>this.classes.delete(x)),contains:x=>this.classes.has(x),toggle:(x,on)=>on?this.classes.add(x):this.classes.delete(x)};}
    set innerHTML(html){for(const id of this.children)delete elements[id];this.children=[];this.html=html;
      for(const match of html.matchAll(/id="([^"]+)"/g)){elements[match[1]]=new Element(match[1]);this.children.push(match[1]);}}
    get innerHTML(){return this.html||'';}
    addEventListener(name,callback){this.listeners[name]=callback;}
    querySelectorAll(){return [];}
    querySelector(){return null;}
    click(){return this.listeners.click?.({target:this,currentTarget:this});}
  }
  for(const id of ['settingsDetail','settingsPage','closeSettingsPage'])elements[id]=new Element(id);
  const document={body:new Element('body'),getElementById:id=>elements[id]||null,querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){}};
  const timer=(callback,ms,interval)=>{const id=++nextTimer;timers.set(id,{callback,at:now+ms,interval:interval?ms:0});return id};
  const window={Code:{core:{},features:{},services:{},ui:{}},URL,URLSearchParams,
    location:{href:'http://fixture.test/',search:'',replace:url=>navigations.push(url)},
    localStorage:{getItem:()=>null,setItem(){},removeItem(){}},matchMedia:()=>({matches:false,addEventListener(){}}),addEventListener(){},
    setTimeout:(cb,ms)=>timer(cb,ms,false),clearTimeout:id=>timers.delete(id),
    setInterval:(cb,ms)=>timer(cb,ms,true),clearInterval:id=>timers.delete(id),
    AbortController,fetch:async()=>{const held=deferred();versions.push(held);return held.promise;}};
  const sandbox=vm.createContext({window,console,URL,URLSearchParams,Promise,Date:class extends Date{static now(){return now}},setTimeout:window.setTimeout});
  for(const file of ['src/core/namespace.js','src/core/platform.js','src/features/settings.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),sandbox);
  const state={appVersion:'1.0.0'};
  const feature=window.Code.features.settings.createSettingsFeature({state,elements:{},document,storage:window.localStorage,t:key=>key,
    prepareUpdate:prepare,onUpdatePause:value=>{state._updateStopping=value;pauses.push(value)},fetch:window.fetch,
    apiJson:async(url,options={})=>{
      calls.push({url,body:options.body?JSON.parse(options.body):null});
      if(url==='/api/version')return {localVersion:'1.0.0'};
      if(url.startsWith('/api/download-progress'))return {...job};
      if(url==='/api/check-update')return {updateAvailable:true,remoteVersion,isFrozen:true,assetName:`Code-v${remoteVersion}.exe`,assetSize:10};
      if(url==='/api/download-update'){job={jobId:'new-job',version:remoteVersion,status:'completed',progress:100};return {...job};}
      if(url==='/api/restart')return {ok:true};
      throw new Error(url);
    }});
  feature.bind();
  return {calls,pauses,state,versions,navigations,elements,timers,
    async open(){feature.openSettingsPage('update');await flush();},
    async close(){elements.closeSettingsPage.click();await flush();},
    async click(id){assert(elements[id],`missing ${id}`);const result=elements[id].click();await flush();return {result};},
    async tick(ms){const target=now+ms;let count=0;
      while(true){const next=[...timers].filter(([,t])=>t.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;
        if(++count>1000)throw new Error('timer loop');const [id,t]=next;now=t.at;if(t.interval)t.at+=t.interval;else timers.delete(id);t.callback();await flush();}
      now=target;await flush();},
    count(url){return calls.filter(item=>item.url===url).length;},
  };
}

async function run(){
  const outcomes=[];
  async function check(name,fn){try{await fn();outcomes.push({name,ok:true});}catch(error){outcomes.push({name,ok:false,error:String(error.stack)});}}
  for(const mode of ['returned-conflict','real-save-conflict','superseded-snapshot','missing-receipt']){
    await check(`preparation-refuses-${mode}-and-retains-pending-save`,async()=>{
      const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
      const realSave=source.slice(source.indexOf('async function saveSessionState('),source.indexOf('async function saveCurrentSession('));
      const realPrepare=source.slice(source.indexOf('async function prepareCurrentPageForUpdate('),source.indexOf('function cancelSessionRun('));
      const conflict={id:'session',revision:2,_sessionRevisionConflict:true}, confirmed={id:'session',revision:3};
      const state={_updatePendingSessionSaves:new Set(['session']),_sessionRuns:{},_sessionMsgs:{},_backgroundDispatcher:{jobs:[],activeCount:0},sessions:[{id:'session',title:'fixture'}]};
      let failed=true,writes=0;
      const sandbox=vm.createContext({state,Set,Date,Promise,console,
        restoreSupersededSessionProjection:()=>failed&&mode==='superseded-snapshot'?confirmed:null,
        getSessionMessages:()=>[],getSessionStats:()=>({}),getSessionRunState:()=>({}),getSessionLastUsage:()=>null,isSessionStreaming:()=>false,
        apiJson:async()=>({ok:true}),buildSessionSavePayload:()=>({}),t:k=>k,
        persistSessionPayload:async()=>{writes++;return failed?(mode==='missing-receipt'?undefined:conflict):confirmed},
        retireSessionMessageProjection(){},rememberAuthoritativeSessionSnapshot(){},syncTrustedGoalMessageMetadata:()=>false,
        syncSessionSourceBadgeState(){},syncPersistedSessionActivity(){}});
      vm.runInContext(realSave+realPrepare,sandbox);
      if(mode==='returned-conflict')sandbox.saveSessionState=async()=>failed?conflict:confirmed;
      await assert.rejects(sandbox.prepareCurrentPageForUpdate(),/update_save_unconfirmed/);
      assert(state._updatePendingSessionSaves.has('session'));
      if(mode==='superseded-snapshot')assert.equal(writes,0);
      failed=false;await sandbox.prepareCurrentPageForUpdate();
      assert.equal(state._updatePendingSessionSaves.size,0);
    });
  }
  await check('close-and-reopen-retains-pause-until-preparation-settles',async()=>{
    const held=deferred();let preparations=0;
    const h=harness({prepare:()=>{preparations++;return held.promise}});
    await h.open();await h.click('updateCheckBtn');await h.click('updateDlBtn');
    assert.equal(h.state._updateStopping,true);
    await h.close();await h.open();assert.equal(h.state._updateStopping,true);
    await h.click('updateCheckBtn');await h.click('updateDlBtn');assert.equal(preparations,1);
    await h.close();held.resolve();await flush();assert.equal(h.state._updateStopping,false);
    assert.equal(h.count('/api/download-update'),0);assert.equal(h.count('/api/restart'),0);
  });
  await check('timeout-retry-shares-pending-preparation-and-releases-after-rejection',async()=>{
    const held=deferred();let preparations=0;
    const h=harness({prepare:()=>{preparations++;return held.promise}});
    await h.open();await h.click('updateCheckBtn');await h.click('updateDlBtn');await h.tick(60001);
    assert.match(h.elements.updateStatus.innerHTML,/updateStopFailed/);assert.equal(h.state._updateStopping,true);
    await h.click('updateRetryBtn');assert.equal(preparations,1);held.reject(new Error('save failed'));await flush();
    assert.equal(h.state._updateStopping,false);assert.equal(h.count('/api/download-update'),0);
  });
  await check('late-success-after-timeout-releases-pause-without-auto-install',async()=>{
    const held=deferred(),h=harness({prepare:()=>held.promise});
    await h.open();await h.click('updateCheckBtn');await h.click('updateDlBtn');await h.tick(60001);
    assert.equal(h.state._updateStopping,true);held.resolve();await flush();
    assert.equal(h.state._updateStopping,false);assert.equal(h.count('/api/download-update'),0);
    await h.close();
  });
  await check('completed-job-has-no-live-progress-poll-during-held-preparation',async()=>{
    const held=deferred(),h=harness({job:{jobId:'completed-job',version:'2.0.0',status:'completed'},prepare:()=>held.promise});
    await h.open();await h.click('updateRestartBtn');
    assert.equal([...h.timers.values()].filter(timer=>timer.interval===500).length,0);
    await h.tick(1000);assert.equal(h.count('/api/restart'),0);
    held.resolve();await flush();assert.equal(h.count('/api/restart'),1);await h.close();
  });
  await check('installed-v1-can-update-to-v2-with-new-job',async()=>{
    const h=harness({job:{jobId:'old-job',version:'1.0.0',status:'installed'}});
    await h.open();await h.click('updateCheckBtn2');await h.click('updateDlBtn');
    assert.equal(h.count('/api/restart'),1);
    assert.deepEqual(h.calls.find(c=>c.url==='/api/restart').body,{jobId:'new-job'});
    await h.close();
  });
  await check('late-target-version-after-total-timeout-does-not-navigate',async()=>{
    const h=harness({job:{jobId:'pending',version:'2.0.0',status:'installing'}});
    await h.open();await h.tick(91000);assert.equal(h.versions.length,1);
    assert.match(h.elements.updateStatus.innerHTML,/updateRestartUnconfirmed/);
    h.versions[0].resolve({json:async()=>({localVersion:'2.0.0'})});await flush();
    assert.equal(h.navigations.length,0);await h.close();
  });
  await check('new-version-check-invalidates-prior-response',async()=>{
    const h=harness({job:{jobId:'pending',version:'2.0.0',status:'installing'}});
    await h.open();await h.tick(91000);await h.click('updateRecheckBtn');await h.tick(800);
    assert.equal(h.versions.length,2);
    h.versions[0].resolve({json:async()=>({localVersion:'2.0.0'})});await flush();assert.equal(h.navigations.length,0);
    h.versions[1].resolve({json:async()=>({localVersion:'2.0.0'})});await flush();assert.equal(h.navigations.length,1);
    await h.close();
  });
  console.log(JSON.stringify({ok:outcomes.every(item=>item.ok),outcomes},null,2));
  if(outcomes.some(item=>!item.ok))process.exitCode=1;
}
run().catch(error=>{console.error(error);process.exitCode=1});
