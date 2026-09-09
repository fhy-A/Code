const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const app=fs.readFileSync(path.resolve(__dirname,'../../../app.js'),'utf8');
const source=app.slice(app.indexOf('const _FAVICON_RETRY_DELAY_MS'),app.indexOf('// Right-click menus for links in final answers'));
const flush=async()=>{for(let i=0;i<5;i++)await new Promise(setImmediate)};
function setup(ignoreAbort=false){
  const calls=[],timers=new Map(),revoked=[],created=[],listeners={},slots=[];let serial=0,observer,decode='load',now=Date.now();
  const fakeURL=class extends URL{static createObjectURL(){const url='blob:fixture/'+(++serial);created.push(url);return url}static revokeObjectURL(url){revoked.push(url)}};
  const response=(status=200,retry='1')=>({ok:status===200,status,headers:{get:()=>retry},body:{cancel:async()=>{}},blob:async()=>new Blob(['valid fixture'],{type:'image/png'})});
  const context=vm.createContext({URL:fakeURL,AbortController,Blob,Date:class extends Date{static now(){return now}},Map,Set,Promise,Number,encodeURIComponent,
    fetch:(url,options)=>new Promise((resolve,reject)=>{calls.push({url,options,resolve,reject});if(!ignoreAbort)options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})}),
    MutationObserver:class{constructor(fn){observer=fn}observe(){}disconnect(){listeners.disconnected=true}},
    document:{body:{},getElementById:()=>({}),querySelectorAll:()=>slots.filter(s=>s.isConnected),createElement:()=>{
      const handlers={};return {naturalWidth:16,naturalHeight:16,addEventListener:(type,fn)=>handlers[type]=fn,
        set src(url){this._src=url;queueMicrotask(()=>{const type=decode;this['on'+type]?.();handlers[type]?.()})},get src(){return this._src}};
    }},window:{setTimeout:(fn,ms)=>{const id=++serial;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),addEventListener:(type,fn)=>listeners[type]=fn}});
  vm.runInContext(source,context);const api=vm.runInContext('({bindExtLinkFavicons,_faviconCache,_pruneFaviconConsumers,get active(){return _faviconActiveLoads}})',context);
  const slot=(host='one.test')=>{const item={isConnected:true,dataset:{},children:['glyph'],closest:()=>({getAttribute:()=>`https://${host}/path`}),replaceChildren(node){this.children=[node]}};slots.push(item);return item};
  const tick=ms=>{for(const [id,t] of [...timers])if(t.ms===ms){timers.delete(id);t.fn()}};
  return {advance:ms=>{now+=ms},api,calls,timers,revoked,created,listeners,slot,response,tick,remove:()=>observer([{removedNodes:[{}]}]),decode:value=>decode=value};
}
const outcomes=[];
async function check(group,name,fn){if(process.argv[2]&&process.argv[2]!==group)return;try{await fn();outcomes.push({name,ok:true})}catch(e){outcomes.push({name,ok:false,error:e.stack})}}
async function main(){
  await check('binding','same-origin-shared-success-keeps-glyph-until-decoded',async()=>{
    const h=setup(),a=h.slot(),b=h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,1);assert.equal(a.children[0],'glyph');
    assert.equal(h.calls[0].url,'/api/favicon?scheme=https&host=one.test');assert.equal(h.calls[0].options.referrerPolicy,'no-referrer');assert.equal(h.calls[0].options.redirect,'error');
    h.calls[0].resolve(h.response());await flush();assert.equal(a.children[0].className,'ext-favicon');assert.equal(b.children[0].className,'ext-favicon');assert.equal(h.api.active,0);
  });
  await check('binding','503-retry-after-restores-original-node-once',async()=>{
    const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();h.calls[0].resolve(h.response(503,'2'));await flush();assert.equal(a.children[0],'glyph');
    assert([...h.timers.values()].some(t=>t.ms===2000));h.tick(2000);h.calls[1].resolve(h.response());await flush();assert.equal(a.children[0].className,'ext-favicon');assert.equal(h.calls.length,2);
  });
  await check('binding','stable-status-and-decode-failure-never-retry',async()=>{
    for(const status of [400,403,404,200]){const h=setup(),a=h.slot();if(status===200)h.decode('error');h.api.bindExtLinkFavicons();h.calls[0].resolve(h.response(status));await flush();
      assert.equal(a.children[0],'glyph');assert.equal(h.timers.size,0);h.slot();h.api.bindExtLinkFavicons();await flush();assert.equal(h.calls.length,1);assert.equal(h.created.length,h.revoked.length);}
  });
  await check('binding','network-failure-two-attempts-no-third-after-redraw',async()=>{
    const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();h.calls[0].reject(new TypeError('network'));await flush();h.tick(1000);h.calls[1].reject(new TypeError('network'));await flush();
    a.isConnected=false;h.slot();h.api.bindExtLinkFavicons();h.tick(30000);await flush();assert.equal(h.calls.length,2);assert.equal(h.timers.size,0);
  });
  await check('binding','retry-after-above-budget-stops-without-early-request',async()=>{
    for(const header of ['11','120',new Date(Date.now()+60000).toUTCString()]){
      const h=setup();h.slot();h.api.bindExtLinkFavicons();h.calls[0].resolve(h.response(503,header));await flush();
      assert.equal(h.timers.size,0);assert.equal(h.calls.length,1);assert.equal([...h.api._faviconCache.values()][0].status,'failed');
    }
  });
  await check('binding','hanging-request-times-out-with-one-bounded-retry',async()=>{
    const h=setup();h.slot();h.api.bindExtLinkFavicons();h.tick(10000);await flush();h.tick(1000);h.tick(10000);await flush();assert.equal(h.calls.length,2);assert.equal(h.api.active,0);assert.equal(h.timers.size,0);
  });
  await check('queue','four-slot-fifo-retry-goes-to-tail',async()=>{
    const h=setup();for(let i=0;i<9;i++)h.slot(`host${i}.test`);h.api.bindExtLinkFavicons();assert.equal(h.calls.length,4);
    h.calls[0].resolve(h.response(503));await flush();assert.equal(h.calls.length,5);h.tick(1000);
    for(let i=1;i<10;i++){assert(h.api.active<=4);h.calls[i].resolve(h.response());await flush();}
    assert.deepEqual(h.calls.map(c=>new URL(c.url,'https://local').searchParams.get('host')),[...Array.from({length:9},(_,i)=>`host${i}.test`),'host0.test']);assert.equal(h.api.active,0);
  });
  await check('queue','redraw-retains-budget-and-replacement-consumer',async()=>{
    const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();h.calls[0].resolve(h.response(503));await flush();a.isConnected=false;const b=h.slot();h.api.bindExtLinkFavicons();h.remove();h.tick(1000);
    h.calls[1].resolve(h.response());await flush();assert.equal(a.children[0],'glyph');assert.equal(b.children[0].className,'ext-favicon');assert.equal(h.calls.length,2);
  });
  await check('queue','removed-consumers-abort-and-ignore-late-response',async()=>{
    const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();a.isConnected=false;h.remove();h.calls[0].resolve(h.response());await flush();assert(h.calls[0].options.signal.aborted);assert.equal(a.children[0],'glyph');assert.equal(h.api.active,0);
    h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,2);h.calls[1].resolve(h.response());await flush();
  });
  await check('queue','late-response-after-cancel-cannot-replace-a-new-cycle',async()=>{
    const h=setup(true),a=h.slot();h.api.bindExtLinkFavicons();a.isConnected=false;h.remove();
    const b=h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,2);
    h.calls[0].resolve(h.response());await flush();assert.equal(b.children[0],'glyph');assert.equal(h.created.length,0);
    h.calls[1].resolve(h.response());await flush();assert.equal(b.children[0].className,'ext-favicon');assert.equal(a.children[0],'glyph');assert.equal(h.api.active,0);
  });
  await check('queue','success-lru-revokes-assets-terminal-budgets-stay-bounded',async()=>{
    const h=setup();for(let i=0;i<130;i++){const a=h.slot(`success${i}.test`);h.api.bindExtLinkFavicons();h.calls.at(-1).resolve(h.response());await flush();a.isConnected=false;}
    assert.equal(h.api._faviconCache.size,128);assert.equal(h.revoked.length,2);
    h.listeners.pagehide({persisted:false});await flush();assert.equal(h.revoked.length,130);assert.equal(h.api._faviconCache.size,0);assert(h.listeners.disconnected);
    const f=setup();for(let i=0;i<129;i++){f.slot(`failed${i}.test`);f.api.bindExtLinkFavicons();f.calls.at(-1).resolve(f.response(404));await flush();}
    assert.equal(f.calls.length,129);assert.equal(f.api._faviconCache.size,128);f.slot('failed128.test');f.api.bindExtLinkFavicons();assert.equal(f.calls.length,129);
    f.advance(300001);f.slot('failed128.test');f.api.bindExtLinkFavicons();assert.equal(f.calls.length,130);f.calls[129].resolve(f.response());await flush();
  });
  await check('queue','pagehide-preserves-bfcache-then-disposes-on-final-leave',async()=>{
    const h=setup();h.slot();h.api.bindExtLinkFavicons();h.calls[0].resolve(h.response(503));await flush();h.listeners.pagehide({persisted:true});assert.equal(h.timers.size,1);
    h.listeners.pagehide({persisted:false});assert.equal(h.timers.size,0);h.tick(1000);assert.equal(h.calls.length,1);
  });
  console.log(JSON.stringify({ok:outcomes.every(o=>o.ok),outcomes},null,2));if(outcomes.some(o=>!o.ok))process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1});
