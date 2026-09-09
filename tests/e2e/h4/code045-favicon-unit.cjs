const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const app=fs.readFileSync(path.resolve(__dirname,'../../../app.js'),'utf8');
const source=app.slice(app.indexOf('const _FAVICON_GOOGLE_TIMEOUT_MS'),app.indexOf('// Right-click menus for links in final answers'));
const flush=async()=>{for(let i=0;i<4;i++)await new Promise(setImmediate)};
function setup(){
  const calls=[],timers=new Map(),listeners={},slots=[];let serial=0,observer,now=Date.now();
  const context=vm.createContext({URL,Date:class extends Date{static now(){return now}},Map,Set,Promise,Number,encodeURIComponent,
    Image:class{constructor(){this.naturalWidth=32;this.naturalHeight=32}set src(url){this.assignedUrl=url;this._src=url;calls.push(this)}get src(){return this._src}removeAttribute(){this._src='';this.removed=true}settle(type='load'){this['on'+type]?.()}},
    MutationObserver:class{constructor(fn){observer=fn}observe(){}disconnect(){listeners.disconnected=true}},
    document:{body:{},getElementById:()=>({}),querySelectorAll:()=>slots.filter(s=>s.isConnected),createElement:tag=>{
      assert.equal(tag,'canvas');const canvas={style:{},setAttribute(){},getContext:()=>({drawImage:img=>{canvas.drawnFrom=img}})};return canvas;
    }},
    window:{setTimeout:(fn,ms)=>{const id=++serial;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),addEventListener:(type,fn)=>listeners[type]=fn}});
  vm.runInContext(source,context);const api=vm.runInContext('({bindExtLinkFavicons,_normalizeFaviconOrigin,_faviconCache,_pruneFaviconConsumers,get active(){return _faviconActiveLoads}})',context);
  const slot=(href='https://one.test/path')=>{const item={isConnected:true,dataset:{},children:['glyph'],closest:()=>({getAttribute:()=>href}),replaceChildren(node){this.children=[node]}};slots.push(item);return item};
  const tick=ms=>{now+=ms;for(const [id,t] of [...timers])if(t.ms===ms){timers.delete(id);t.fn()}};
  return {advance:ms=>{now+=ms},api,calls,timers,listeners,slot,tick,remove:()=>observer([{removedNodes:[{}]}])};
}
const outcomes=[];
async function check(group,name,fn){if(process.argv[2]&&process.argv[2]!==group)return;try{await fn();outcomes.push({name,ok:true})}catch(e){outcomes.push({name,ok:false,error:e.stack})}}
async function main(){
 await check('binding','unsafe-static-inputs-make-no-external-image-request',async()=>{
  const h=setup();const bad=['http://127.0.0.1','http://127.1','http://2130706433','http://0x7f000001','http://0177.0.0.1','https://192.168.1.2','https://8.8.8.8','http://[::1]','http://[::ffff:127.0.0.1]','http://localhost','http://a.localhost','http://LOCALHOST.','https://printer','https://work.local','https://one.test:444','http://one.test:443','https://user:secret@one.test/a','https://@one.test','file:///tmp/icon','data:image/png,hello','//one.test','https://bad_host.test','https://-bad.test','https://one.test\\secret','https://one.test/\nsecret'];
  for(const value of bad){assert.equal(h.api._normalizeFaviconOrigin(value),'',value);h.slot(value)}h.api.bindExtLinkFavicons();assert.equal(h.calls.length,0);assert.equal(h.api._faviconCache.size,0);
 });
 await check('binding','canonical-origin-only-idna-default-ports-and-private-path-removal',async()=>{
  const h=setup();assert.equal(h.api._normalizeFaviconOrigin('https://例子.测试/path?q=private#secret'),'https://xn--fsqu00a.xn--0zwm56d');assert.equal(h.api._normalizeFaviconOrigin('HTTP://WWW.Example.COM.:80/a'),'http://www.example.com');
  h.slot('https://Example.COM:443/private?secret=never-send#fragment');h.slot('https://example.com/other');h.api.bindExtLinkFavicons();assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].assignedUrl,'https://www.google.com/s2/favicons?domain=https%3A%2F%2Fexample.com&sz=32');assert.equal(h.calls[0].referrerPolicy,'no-referrer');assert.equal(h.calls[0].crossOrigin,undefined);
  h.calls[0].settle('error');await flush();assert.equal(h.calls[1].assignedUrl,'https://example.com/favicon.ico');h.calls[1].settle();await flush();
 });
 await check('binding','shared-google-success-keeps-original-glyph-until-load',async()=>{
  const h=setup(),a=h.slot(),b=h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,1);assert.equal(a.children[0],'glyph');
  h.calls[0].settle();await flush();assert.equal(h.calls.length,1);assert.equal(a.children[0].className,'ext-favicon');assert.equal(b.children[0].className,'ext-favicon');assert.equal([...h.api._faviconCache.values()][0].attempts,1);assert.equal(h.api.active,0);
 });
 await check('binding','google-error-falls-back-to-exact-origin-once',async()=>{
  const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();h.calls[0].settle('error');await flush();assert.equal(h.calls[1].assignedUrl,'https://one.test/favicon.ico');assert.equal(a.children[0],'glyph');h.calls[1].settle();await flush();assert.equal(a.children[0].drawnFrom,h.calls[1]);assert.equal(h.calls.length,2);assert.equal(h.timers.size,0);
 });
 await check('binding','dual-failure-caches-negative-and-redraw-does-not-retry',async()=>{
  const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();h.calls[0].settle('error');await flush();h.calls[1].settle('error');await flush();a.isConnected=false;h.slot();h.api.bindExtLinkFavicons();h.advance(30000);h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,2);assert.equal(h.timers.size,0);assert.equal(a.children[0],'glyph');
 });
 await check('binding','four-plus-three-second-timeouts-stop-and-ignore-late-success',async()=>{
  const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();const late=h.calls[0].onload;h.tick(4000);await flush();late();assert.equal(a.children[0],'glyph');h.tick(3000);await flush();assert.equal(h.calls.length,2);assert(h.calls.every(x=>x.removed));assert.equal(h.api.active,0);assert.equal(h.timers.size,0);
 });
 await check('binding','one-pixel-falls-back-but-sixteen-pixel-is-not-classified-as-placeholder',async()=>{
  const h=setup();h.slot();h.api.bindExtLinkFavicons();h.calls[0].naturalWidth=1;h.calls[0].settle();await flush();assert.equal(h.calls.length,2);h.calls[1].settle();await flush();
  const good=setup();good.slot();good.api.bindExtLinkFavicons();good.calls[0].naturalWidth=16;good.calls[0].naturalHeight=16;good.calls[0].settle();await flush();assert.equal(good.calls.length,1);
 });
 await check('queue','four-slot-fifo-holds-one-slot-for-bounded-origin-fallback',async()=>{
  const h=setup();for(let i=0;i<9;i++)h.slot(`https://host${i}.test`);h.api.bindExtLinkFavicons();assert.equal(h.calls.length,4);h.calls[0].settle('error');await flush();assert.equal(h.calls.length,5);assert.equal(h.calls[4].assignedUrl,'https://host0.test/favicon.ico');assert.equal(h.api.active,4);
  h.calls[4].settle();await flush();for(let i=1;i<h.calls.length;i++){if(i===4)continue;h.calls[i].settle();await flush();assert(h.api.active<=4)}
  const google=h.calls.filter(c=>c.assignedUrl.includes('google.com/s2'));assert.deepEqual(google.map(c=>new URL(c.assignedUrl).searchParams.get('domain')),Array.from({length:9},(_,i)=>`https://host${i}.test`));assert.equal(h.api.active,0);
 });
 await check('queue','synchronous-redraw-registers-new-consumers-without-cancelling',async()=>{
  const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();a.isConnected=false;const b=h.slot();h.api.bindExtLinkFavicons();h.remove();assert.equal(h.calls.length,1);assert(!h.calls[0].removed);h.calls[0].settle();await flush();assert.equal(a.children[0],'glyph');assert.equal(b.children[0].drawnFrom,h.calls[0]);
 });
 await check('queue','scoped-incremental-binding-registers-before-pruning-and-paints-cache-synchronously',async()=>{
  const h=setup(),old=h.slot(),unrelated=h.slot('https://unrelated.test');let scans=0;
  const root={querySelectorAll:selector=>{assert.equal(selector,'a.ext-link .link-ext-icon');scans++;return [old]}};
  h.api.bindExtLinkFavicons(root);assert.equal(scans,1);assert.equal(h.calls.length,1);assert.equal(unrelated.dataset.bound,undefined);
  old.isConnected=false;const fresh=h.slot();root.querySelectorAll=()=>[fresh];h.api.bindExtLinkFavicons(root);h.remove();
  assert.equal(h.calls.length,1);assert(!h.calls[0].removed);h.calls[0].settle();await flush();
  fresh.isConnected=false;const cached=h.slot();root.querySelectorAll=()=>[cached];h.api.bindExtLinkFavicons(root);
  assert.equal(cached.children[0].drawnFrom,h.calls[0]);assert.equal(h.calls.length,1);assert.equal(unrelated.dataset.bound,undefined);
 });
 await check('queue','cancelled-origin-can-resubscribe-and-old-load-cannot-replace-it',async()=>{
  const h=setup(),a=h.slot();h.api.bindExtLinkFavicons();const late=h.calls[0].onload;a.isConnected=false;h.remove();await flush();assert(h.calls[0].removed);const b=h.slot();h.api.bindExtLinkFavicons();late();await flush();assert.equal(b.children[0],'glyph');assert.equal(h.calls.length,2);h.calls[1].settle();await flush();assert.equal(b.children[0].drawnFrom,h.calls[1]);assert.equal(h.api.active,0);
 });
 await check('queue','decoded-resource-repaint-never-creates-new-images-or-reads-pixels',async()=>{
  const h=setup();h.slot();h.api.bindExtLinkFavicons();h.calls[0].settle();await flush();
  for(let i=0;i<20;i++){const slot=h.slot();h.api.bindExtLinkFavicons();assert.equal(slot.children[0].drawnFrom,h.calls[0]);assert.equal(slot.children[0].style.animation,'none')}
  assert.equal(h.calls.length,1);assert.equal(h.timers.size,0);assert(!source.includes('getImageData'));assert(!source.includes('toDataURL'));assert(!source.includes('toBlob'));
 });
 await check('queue','bounded-lru-negative-expiry-and-positive-expiry',async()=>{
  const h=setup();for(let i=0;i<129;i++){const a=h.slot(`https://host${i}.test`);h.api.bindExtLinkFavicons();h.calls.at(-1).settle();await flush();a.isConnected=false}assert.equal(h.api._faviconCache.size,128);
  h.advance(6*60*60*1000+1);h.slot('https://host128.test');h.api.bindExtLinkFavicons();assert.equal(h.calls.length,130);h.calls.at(-1).settle();await flush();
  const f=setup();f.slot();f.api.bindExtLinkFavicons();f.calls[0].settle('error');await flush();f.calls[1].settle('error');await flush();f.advance(300001);f.slot();f.api.bindExtLinkFavicons();assert.equal(f.calls.length,3);f.calls[2].settle();await flush();
 });
 await check('queue','pagehide-preserves-bfcache-and-final-leave-releases-all-pending-images',async()=>{
  const h=setup();h.slot();h.api.bindExtLinkFavicons();h.listeners.pagehide({persisted:true});assert.equal(h.timers.size,1);h.listeners.pagehide({persisted:false});await flush();assert.equal(h.timers.size,0);assert.equal(h.api._faviconCache.size,0);assert.equal(h.api.active,0);assert(h.calls[0].removed);assert(h.listeners.disconnected);h.slot();h.api.bindExtLinkFavicons();assert.equal(h.calls.length,1);
 });
 console.log(JSON.stringify({ok:outcomes.every(o=>o.ok),outcomes},null,2));if(outcomes.some(o=>!o.ok))process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1});
