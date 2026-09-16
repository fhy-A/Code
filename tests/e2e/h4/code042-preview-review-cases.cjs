const assert = require("node:assert/strict");
const path = require("node:path");

module.exports = async function reviewCases(browser, baseUrl) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.route("**/__preview_review_fixture", (route) => route.fulfill({contentType:"text/html",body:`<!doctype html>
      <div id="workbench"><div id="previewTabs"></div><div id="filePreview"></div></div>
      <div id="previewTitle"></div><div id="previewMeta"></div><div id="previewLanguage"></div><div id="previewModeActions"></div>
      <button id="refreshPreview"></button><button id="copyPreview"></button><button id="togglePreview"></button><button id="closePreview"></button><div id="previewResizer"></div>`}));
    await page.goto(baseUrl + "/__preview_review_fixture");
    await page.evaluate(() => { window.Code = {features:{}}; });
    await page.addScriptTag({path:path.resolve(__dirname,"../../..","src/features/preview.js")});
    const result = await page.evaluate(async () => {
      const checks=[];
      const check=(value,label)=>{if(!value)throw new Error(label);checks.push(label);};
      const until=async(test)=>{const end=Date.now()+5000;while(!test()){if(Date.now()>end)throw new Error("fixture deadline");await new Promise(r=>setTimeout(r,0));}};
      const store=new Map(),messages=[],held=[],calls=[];
      const source="a".repeat(32), incarnation="b".repeat(32);
      const state={sessionId:"retry",previewWidth:420};
      let failContexts=1,contextGate=null,delay=false,large=false;
      const storage={getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value)};
      const elements=Object.fromEntries(["workbench","filePreview","previewTitle","previewMeta","previewLanguage","previewModeActions","refreshPreview","copyPreview","togglePreview","closePreview","previewResizer"].map(id=>[id,document.getElementById(id)]));
      const key=()=>`${source}:${state.sessionId}:${incarnation}`;
      const hash=async(value)=>[...new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value)))].map(n=>n.toString(16).padStart(2,"0")).join("");
      const apiJson=async(url,options={})=>{
        calls.push(url);
        if(url==="/api/preview/context"){
          if(failContexts-->0)throw new Error("once");
          const body=JSON.parse(options.body);
          if(contextGate)await contextGate.promise;
          return {dataSourceId:source,sessionId:body.sessionId,sessionInstanceId:body.sessionId?incarnation:body.draftId,draftId:body.draftId,identityInitialized:true};
        }
        const name=new URL(url,location.origin).searchParams.get("path").split("/").pop();
        const data={name,path:name,canonicalAbsolutePath:`/fixture/${name}`,locator:`/fixture/${name}`,fileKey:await hash(name),contentRevision:name,content:large?"x".repeat(3*1024*1024):name,binary:false,size:10};
        if(delay)return new Promise((resolve,reject)=>held.push({resolve:(extra={})=>resolve({...data,...extra}),reject}));
        return data;
      };
      const options={state,elements,storage,apiJson,renderMarkdown:s=>s,showToast:s=>messages.push(s)};
      const create=()=>window.Code.features.preview.createPreviewFeature(options);
      const feature=create();feature.bind();
      check(await feature.restore()===false,"first context failure is reported");
      await feature.loadFile("recovered.txt");
      check(calls.filter(url=>url==="/api/preview/context").length===2 && elements.filePreview.textContent.includes("recovered.txt"),"ordinary click retries failed initialization");
      check(!messages.includes("previewTabsUnavailable") && !messages.includes("previewIdentityRenewed"),"normal first initialization stays quiet");
      feature.beginNavigation();state.sessionId="parallel-init";
      let releaseContext; contextGate={promise:new Promise(r=>releaseContext=r)};
      const count=calls.filter(url=>url==="/api/preview/context").length;
      const first=feature.loadFile("first.txt"),second=feature.loadFile("second.txt");
      check(calls.filter(url=>url==="/api/preview/context").length===count+1,"concurrent initialization is merged");
      releaseContext();contextGate=null;await Promise.all([first,second]);
      check(elements.filePreview.textContent.includes("second.txt"),"merged initialization preserves latest ordinary intent");
      feature.beginNavigation();state.sessionId="late-init";
      let rejectOld;contextGate={promise:new Promise((_,reject)=>rejectOld=reject)};
      const oldInitialization=feature.restore();feature.beginNavigation();contextGate=null;state.sessionId="current-init";
      await feature.restore();await feature.loadFile("current.txt");rejectOld(new Error("late initialization failure"));await oldInitialization;
      check(elements.filePreview.textContent.includes("current.txt"),"late initialization failure cannot clear the new scope");
      feature.close();store.clear();
      const id="1".repeat(32),tab={id,fileKey:"2".repeat(64),path:"/fixture/a.txt",locator:"/fixture/a.txt",name:"a.txt",mode:"source",scroll:0,scale:null,page:0,order:1};
      const valid={tabs:[tab],active:id,reuse:id,mru:[id],paneOpen:true,orderCounter:1};
      const mutations=[
        w=>w.tabs[0]=null,w=>w.tabs[0].id="",w=>w.tabs[0].id='bad"]',w=>w.tabs.push({...tab,fileKey:"3".repeat(64),order:2}),
        w=>w.active="missing",w=>w.reuse="missing",w=>w.mru=["missing"],w=>w.mru=[id,id],w=>w.mru="wrong",
        w=>w.tabs[0].scroll=-1,w=>w.tabs[0].scroll=Infinity,w=>w.tabs[0].scale=6,w=>w.tabs[0].page=0.5,
        w=>w.tabs[0].innerScroll={top:0,left:"bad"},w=>w.tabs[0].mode="unsafe",w=>w.tabs[0].name="x".repeat(4097),
        w=>w.tabs[0].path="x".repeat(32769),w=>w.tabs[0].locator="",w=>w.paneOpen="yes",w=>w.orderCounter=Infinity,
      ];
      for(let index=0;index<mutations.length;index++){
        store.clear();state.sessionId=`invalid-${index}`;
        const workspace=JSON.parse(JSON.stringify(valid));mutations[index](workspace);
        const raw=JSON.stringify({version:1,records:{[key()]:workspace}},null,2);store.set("code-preview-workspaces-v1",raw);
        const candidate=create();await candidate.restore();
        check(document.querySelectorAll("#previewTabs [role=tab]").length===0,`invalid descriptor ${index} restores empty`);
        await candidate.loadFile("usable.txt");
        check(elements.filePreview.textContent.includes("usable.txt") && store.get("code-preview-workspaces-v1")===raw,`invalid descriptor ${index} preserves bytes and remains usable`);
        candidate.close();
      }
      store.clear();state.sessionId="empty-corruption";store.set("code-preview-workspaces-v1","");
      const emptyCorrupt=create();await emptyCorrupt.restore();await emptyCorrupt.loadFile("usable.txt");
      check(store.get("code-preview-workspaces-v1")==="" && elements.filePreview.textContent.includes("usable.txt"),"empty corrupt store is preserved and new opens remain usable");emptyCorrupt.close();
      store.clear();state.sessionId="later-corruption";
      const live=create();await live.restore();await live.loadFile("before.txt");
      const corrupted=JSON.stringify({version:1,records:{[key()]:null}},null,2);store.set("code-preview-workspaces-v1",corrupted);
      await live.restore();check(document.querySelectorAll("#previewTabs [role=tab]").length===0 && store.get("code-preview-workspaces-v1")===corrupted,"later corruption is not overwritten by an in-memory snapshot");live.close();
      store.clear();state.sessionId="old-tabs";
      store.set("code-preview-workspaces-v1",JSON.stringify({version:1,records:{[`${source}:old-tabs:${"c".repeat(32)}`]:valid}}));
      const oldTabs=create();await oldTabs.restore();
      check(messages.includes("previewTabsUnavailable"),"known old tabs get a user-level loss notice");oldTabs.close();
      store.clear();state.sessionId="cache";
      const cache=create();await cache.restore();await cache.loadFile("a.txt",undefined,{newTab:true});await cache.loadFile("b.txt",undefined,{newTab:true});
      const click=name=>[...document.querySelectorAll("#previewTabs [role=tab]")].find(button=>button.textContent===name).click();
      delay=true;click("a.txt");
      check(elements.filePreview.textContent.includes("a.txt") && !elements.filePreview.textContent.includes("noFileOpen"),"cache hit paints the target immediately");
      await until(()=>held.length===1);const heldCount=calls.length;cache.refreshLanguage();
      await new Promise(r=>setTimeout(r,3300));
      check(held.length===1 && calls.length===heldCount,"held validation never overlaps automatic refresh even after language refresh");
      held.shift().resolve({content:"a updated",contentRevision:"a2"});await until(()=>elements.filePreview.textContent.includes("a updated"));
      check(true,"changed content replaces cached content after validation");
      click("b.txt");await until(()=>held.length===1);click("a.txt");await until(()=>held.length===2);
      check(elements.filePreview.textContent.includes("a updated"),"rapid switching shows the target cached data");
      held.shift().reject(new Error("old failure"));held.shift().resolve({content:"a current",contentRevision:"a3"});await until(()=>elements.filePreview.textContent.includes("a current"));
      click("b.txt");await until(()=>held.length===1);held.shift().reject(new Error("current failure"));await until(()=>elements.filePreview.textContent.includes("previewUnavailable"));
      click("a.txt");
      check(elements.filePreview.textContent.includes("previewLoading") && !elements.filePreview.textContent.includes("a current"),"failed validation invalidates cached snapshots");
      await until(()=>held.length===1);held.shift().resolve();await until(()=>elements.filePreview.textContent.includes("a.txt"));delay=false;
      for(let index=0;index<9;index++)await cache.loadFile(`entry-${index}.txt`,undefined,{newTab:true});
      delay=true;click("a.txt");check(elements.filePreview.textContent.includes("previewLoading"),"entry budget evicts least recent data");
      await until(()=>held.length===1);held.shift().resolve();await until(()=>elements.filePreview.textContent.includes("a.txt"));delay=false;
      cache.beginNavigation();state.sessionId="byte-budget";await cache.restore();large=true;
      for(let index=0;index<3;index++)await cache.loadFile(`large-${index}.txt`,undefined,{newTab:true});
      large=false;delay=true;click("large-0.txt");check(elements.filePreview.textContent.includes("previewLoading"),"byte budget evicts data below entry limit");
      await until(()=>held.length===1);cache.beginNavigation();state.sessionId="new-scope";delay=false;await cache.restore();await cache.loadFile("new.txt");held.shift().resolve({content:"late bytes"});
      await new Promise(r=>setTimeout(r,0));check(elements.filePreview.textContent.includes("new.txt") && !elements.filePreview.textContent.includes("late bytes"),"scope change releases cache and rejects late content");cache.close();
      store.clear();state.sessionId="drag";await feature.restore();await feature.loadFile("drag.txt");
      const oldRaf=window.requestAnimationFrame,oldCancel=window.cancelAnimationFrame,frames=new Map(),cancelled=[],captures=new Set();let frameId=0;
      window.requestAnimationFrame=callback=>{frames.set(++frameId,callback);return frameId;};window.cancelAnimationFrame=id=>cancelled.push(id);
      const resizer=elements.previewResizer;
      resizer.setPointerCapture=id=>captures.add(id);resizer.hasPointerCapture=id=>captures.has(id);resizer.releasePointerCapture=id=>captures.delete(id);
      const pointer=(type,x)=>resizer.dispatchEvent(new PointerEvent(type,{pointerId:7,clientX:x,bubbles:true}));
      try{
        for(const action of ["close","navigate"]){
          await feature.restore();await feature.loadFile("drag.txt");const width=state.previewWidth;
          pointer("pointerdown",500);pointer("pointermove",450);const pending=frameId,callback=frames.get(pending);
          check(captures.has(7) && document.body.classList.contains("resizing-preview"),`${action} fixture owns capture before cleanup`);
          if(action==="close")feature.close();else feature.beginNavigation();callback();
          check(cancelled.includes(pending) && !captures.has(7) && !document.body.classList.contains("resizing-preview")
            && !document.documentElement.style.getPropertyValue("--drag-preview-content-width") && state.previewWidth===width,`${action} releases pending RAF capture and temporary styles`);
        }
        await feature.restore();await feature.loadFile("drag.txt");pointer("pointerdown",500);pointer("pointermove",450);frames.get(frameId)();pointer("pointerup",450);
        check(state.previewWidth===470 && store.get("code-preview-width")==="470" && !captures.has(7),"normal resizing still commits its final width");
      }finally{window.requestAnimationFrame=oldRaf;window.cancelAnimationFrame=oldCancel;feature.close();}
      return {checks,invalidVariants:mutations.length,messages,requestCount:calls.length};
    });
    assert(result.checks.length>50);
    return result;
  } finally {await context.close();}
};
