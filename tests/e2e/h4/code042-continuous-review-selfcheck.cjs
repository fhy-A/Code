const assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {chromium}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
async function contract(browser,baseUrl){
 const context=await browser.newContext(),page=await context.newPage();
 try{
  await page.route('**/__continuous_review',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><link rel="stylesheet" href="/styles.css"><div id="workbench" style="height:700px;width:760px"><aside class="preview-pane" style="display:block;width:600px"><header class="preview-head"><div id="previewTabs"></div><div id="previewModeActions"></div><button id="refreshPreview"></button><button id="copyPreview"></button></header><div id="filePreview" style="height:450px;overflow:auto"></div></aside></div><button id="togglePreview"></button><div id="previewResizer"></div>`}));
  await page.goto(baseUrl+'/__continuous_review');await page.evaluate(()=>window.Code={features:{},ui:{},core:{}});
  for(const file of ['src/core/i18n.js','src/ui/diff.js','src/features/preview.js'])await page.addScriptTag({path:path.resolve(__dirname,'../../..',file)});
  return await page.evaluate(async()=>{
   const checks=[],calls=[],held=[],store=new Map(),messages=[],copies=[];let mode='normal',active=0,peak=0,copyResolve=null,fileResolve=null;
   const check=(value,label)=>{if(!value)throw new Error(label);checks.push(label);};
   const until=async(test)=>{const end=Date.now()+5000;while(!test()){if(Date.now()>end)throw new Error('fixture deadline');await new Promise(r=>setTimeout(r,0));}};
   const state={sessionId:'session-a',previewWidth:600},source='a'.repeat(32),incarnation='b'.repeat(32),ids=['1'.repeat(32),'2'.repeat(32),'3'.repeat(32)];
   const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
   const t=(key,args)=>Code.core.i18n.translate(key,args,'en');
   const elements=Object.fromEntries(['workbench','filePreview','previewModeActions','refreshPreview','copyPreview','togglePreview','previewResizer'].map(id=>[id,document.getElementById(id)]));
   const summary=id=>({rootRunId:id,dataSourceId:source,sessionId:state.sessionId,sessionInstanceId:incarnation,revision:'r1',originRoot:'/fixture',coverage:{complete:id!==ids[0]},recordedFileCount:10,operations:Array.from({length:10},(_,index)=>({operationKey:'op-'+index,fileKey:'file-'+(index===9?0:index),path:'/fixture/folder'+index+'/same.txt',kind:index===2?'delete':'update',entityKind:'file',lineStats:index===2?null:{additions:1,deletions:1}}))});
   const detail=key=>({operationKey:key,kind:key==='op-2'?'delete':'update',bodyState:key==='op-2'?'not-retained':'diff',diff:mode==='large'?'@@ -0,0 +1 @@\n'+ '+'.padEnd(250000,'X'):mode==='lines'?'@@ -0,0 +1,4999 @@\n'+Array(4999).fill('+line').join('\n'):'--- a/sample.txt\n+++ b/sample.txt\n@@ -1,80 +1,80 @@\n'+Array(80).fill('-before\n+after <script>safe()</script>'+ ' long source'.repeat(35)).join('\n')});
   const apiJson=async(url,options={})=>{
    calls.push(url);
    if(url==='/api/preview/context')return {dataSourceId:source,sessionId:state.sessionId,sessionInstanceId:incarnation,contextRevision:'context',serverInstanceId:'process'};
    const u=new URL(url,location.origin);
    if(u.pathname==='/api/preview/file'){const p=u.searchParams.get('path'),digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(p)),fileKey=[...new Uint8Array(digest)].map(n=>n.toString(16).padStart(2,'0')).join('');if(mode==='held-file')await new Promise(resolve=>fileResolve=resolve);if(p.includes('folder2/'))throw new Error('missing');return {fileKey,canonicalAbsolutePath:p,locator:p,path:p,name:p.split('/').at(-1),contentRevision:'r1',content:'FILE '+p,size:20,binary:false};}
    const match=u.pathname.match(/\/runs\/([^/]+)\/file-changes(?:\/(.+))?$/);if(!match)throw new Error('unexpected '+url);
    if(!match[2])return summary(match[1]);
    active++;peak=Math.max(peak,active);let counted=true;const done=()=>{if(counted){active--;counted=false;}};options.signal?.addEventListener('abort',done,{once:true});
    if(mode==='held')return new Promise(resolve=>held.push({signal:options.signal,resolve:value=>{done();resolve(value);}}));
    await new Promise(resolve=>setTimeout(resolve,1));done();return detail(match[2]);
   };
   const feature=Code.features.preview.createPreviewFeature({state,elements,t,escapeHtml,apiJson,renderMarkdown:escapeHtml,renderDiff:Code.ui.diff.createDiffFeature({escapeHtml,t}).renderDiff,copyText:path=>{copies.push(path);return mode==='held-copy'?new Promise(resolve=>copyResolve=resolve):Promise.resolve(true);},showToast:message=>messages.push(message),isAbsoluteFilePath:path=>path.startsWith('/'),storage:{getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value)}});
   feature.bind();await feature.restore();
   await feature.loadFile('/fixture/one/same.txt',undefined,{newTab:true});await feature.loadFile('/fixture/two/same.txt',undefined,{newTab:true});
   const tabNames=()=>[...document.querySelectorAll('[data-preview-tab]')].map(e=>e.textContent);
   check(tabNames().includes('same.txt · one')&&tabNames().includes('same.txt · two'),'same file names include parent and full path titles');
   await feature.loadFile('/alternate/one/same.txt',undefined,{newTab:true});
   check(tabNames().includes('same.txt · fixture/one')&&tabNames().includes('same.txt · alternate/one'),'equal parent names use the shortest distinct parent suffix');
   document.querySelectorAll('.preview-tab-close')[2].click();await until(()=>elements.filePreview.textContent.includes('/fixture/two/same.txt'));
   const fileTabs=[...document.querySelectorAll('[data-preview-tab]')].map(e=>e.dataset.previewTab);
   const clickTab=id=>document.querySelector(`[data-preview-tab="${id}"]`).click();
   const button=index=>document.querySelector(`[data-review-operation="op-${index}"]`);
   const expanded=()=>document.querySelectorAll('.review-operation[aria-expanded=true]').length;
   await feature.openReview(ids[0]);
   check(expanded()===1&&button(0).getAttribute('aria-expanded')==='true','whole review expands first operation only');
   check((document.querySelector('.review-task-total').textContent.match(/\*/g)||[]).length===1&&document.querySelector('.review-task-total').hasAttribute('aria-describedby'),'mixed unknown and incomplete coverage use one accessible uncertainty marker');
   check(calls.filter(url=>url.includes('/file-changes/')).length===1,'collapsed operations are not prefetched');
   check(!calls.some(url=>url.includes(ids[1])||url.includes(ids[2])),'other rounds remain unread and no historical enumeration is needed');
   check([...document.querySelectorAll('[data-review-entry]')].every((e,index)=>e.dataset.reviewEntry==='op-'+index),'operation order is unchanged');
   check(!document.querySelector('[data-review-task]'),'single-round review contains no historical task picker');
   const pane=document.querySelector('.preview-pane');pane.style.width='250px';
   check([...document.querySelectorAll('.review-operation-row')].every(row=>{const box=row.getBoundingClientRect(),name=row.querySelector('.review-operation').getBoundingClientRect(),stats=row.querySelector('.review-operation-stats').getBoundingClientRect();return stats.left-name.right<=8&&[...row.querySelectorAll('.review-operation-stats,.review-row-action')].every(el=>{const r=el.getBoundingClientRect();return r.left>=box.left&&r.right<=box.right+1;});}),'250px rows truncate paths before statistics and all three actions; counts stay beside the name');
   pane.style.width='600px';
   const action=(index,name)=>document.querySelector(`[data-review-entry="op-${index}"] [data-review-action="${name}"]`);
   button(0).textContent='forged/display/path';action(0,'copy').click();await until(()=>copies.length===1);
   check(copies[0]==='/fixture/folder0/same.txt'&&expanded()===1,'copy uses canonical summary path and never toggles the row');
   action(0,'toggle').focus();action(0,'toggle').click();check(expanded()===0&&document.activeElement.dataset.reviewAction==='toggle','action toggle preserves keyboard focus and toggles exactly once');action(0,'toggle').click();await until(()=>document.querySelector('.diff-block'));
   const diffScroll=()=>document.querySelector('[data-review-entry="op-0"] .diff-lines');
   diffScroll().scrollLeft=180;check(diffScroll().scrollLeft===180,'long source line uses the actual horizontal diff scroller');
   button(1).click();await until(()=>document.querySelectorAll('.diff-block').length===2);button(2).click();await until(()=>document.querySelectorAll('.review-detail').length===3&&document.querySelector('[data-review-entry="op-2"]').textContent.includes('not retained'));
   check(expanded()===3&&document.querySelectorAll('#filePreview script').length===0,'multiple expansions preserve escaped diff and unknown deletion');
   check(diffScroll().scrollLeft===180,'expanding other operations preserves existing horizontal reading position');
   elements.filePreview.scrollTop=240;const scroll=elements.filePreview.scrollTop,before=calls.filter(url=>url.includes('/file-changes')).length;
   clickTab(fileTabs[0]);await until(()=>elements.filePreview.textContent.includes('FILE'));clickTab('review');
   check(elements.filePreview.scrollTop===scroll&&expanded()===3,'file/review return keeps scroll and expanded state synchronously');
   check(diffScroll().scrollLeft===180,'file/review return preserves horizontal reading position');
   check(calls.filter(url=>url.includes('/file-changes')).length===before,'returning to cached review causes no refetch');
   button(1).click();check(expanded()===2,'collapse releases one detail without replacing other expansions');
   await feature.openReview(ids[0],{fileKey:'file-0'});await until(()=>button(9).getAttribute('aria-expanded')==='true');check(elements.filePreview.scrollTop>scroll,'file card locates and expands last recorded operation');
   mode='held';button(3).click();await until(()=>held.length===1);const pending=held.shift();clickTab(fileTabs[1]);check(pending.signal.aborted,'leaving review aborts active detail');pending.resolve({bodyState:'diff',diff:'+LATE INVALID'});await until(()=>elements.filePreview.textContent.includes('FILE'));check(!elements.filePreview.textContent.includes('LATE INVALID'),'late detail cannot replace file renderer');
   mode='normal';clickTab('review');await until(()=>document.querySelector('[data-review-entry="op-3"] .diff-block'));
   for(let i=0;i<9;i++){if(button(i).getAttribute('aria-expanded')!=='true')button(i).click();}
   await until(()=>active===0);check(expanded()===8&&messages.some(m=>m.includes('limit')),'ninth expansion is refused without evicting existing entries');check(peak===1,'detail requests use a single active queue');
   await feature.openReview(ids[0],{fileKey:'file-8'});await until(()=>document.querySelector('[data-review-entry="op-8"] .diff-block'));
   check(expanded()===8&&messages.some(m=>m.includes('collapsed')),'file card still expands its target at the count limit with explicit collapse feedback');
   // Closing a background file cannot steal the active review.
   const inactive=document.querySelector(`[data-preview-tab="${fileTabs[0]}"]`).closest('.preview-tab');inactive.querySelector('.preview-tab-close').click();check(document.querySelector('[data-preview-tab=review]').getAttribute('aria-selected')==='true','closing background file keeps review active');
   clickTab(fileTabs[1]);await until(()=>elements.filePreview.textContent.includes('FILE'));document.querySelector(`[data-preview-tab="${fileTabs[1]}"]`).closest('.preview-tab').querySelector('.preview-tab-close').click();
   check(document.querySelector('[data-preview-tab=review]').getAttribute('aria-selected')==='true'&&document.querySelectorAll('[data-preview-tab]').length===1,'closing active file follows mixed-view MRU back to review');
   document.querySelector('.preview-tab-close').click();check(!elements.workbench.classList.contains('preview-open')&&!document.querySelector('[data-preview-tab=review]'),'review tab closes independently and closes an otherwise empty pane');
   mode='large';await feature.openReview(ids[1]);button(1).click();button(3).click();await until(()=>active===0&&document.querySelector('[data-review-entry="op-3"]').textContent.includes('limit'));check(document.querySelectorAll('.diff-block').length===2,'response budget refuses extra large body without retaining it');
   await feature.openReview(ids[1],{fileKey:'file-3'});await until(()=>document.querySelector('[data-review-entry="op-3"] .diff-block'));check(document.querySelectorAll('.diff-block').length===2,'file card makes room for its target within the same response budget');
   mode='lines';await feature.openReview(ids[2]);button(1).click();button(3).click();await until(()=>active===0&&document.querySelector('[data-review-entry="op-3"]').textContent.includes('limit'));check(document.querySelectorAll('.diff-line').length===9998,'rendered review line budget remains bounded');
   mode='held';button(4).click();await until(()=>held.length===1);const hidden=held.shift(),beforeHide=calls.length;window.dispatchEvent(new PageTransitionEvent('pagehide'));check(hidden.signal.aborted,'pagehide aborts detail');hidden.resolve({bodyState:'diff',diff:'+HIDDEN LATE'});await new Promise(r=>setTimeout(r,10));check(calls.length===beforeHide&&!elements.filePreview.textContent.includes('HIDDEN LATE'),'pagehide does not restart the aborted queue');
   mode='held';button(5).click();await until(()=>held.length===1);const old=held.shift();feature.beginNavigation();state.sessionId='session-b';await feature.restore();check(old.signal.aborted,'Session change aborts remaining detail');old.resolve({bodyState:'diff',diff:'+WRONG SESSION'});await new Promise(r=>setTimeout(r,10));check(!elements.filePreview.textContent.includes('WRONG SESSION')&&!document.querySelector('[data-preview-tab=review]'),'Session change removes review and rejects late result');
   check([...store.values()].filter(value=>value.startsWith('{')).every(value=>!value.includes('operationKey')&&!value.includes('"review"')),'review and its bodies never enter the existing persisted schema');
   mode='normal';await feature.openReview(ids[0]);action(1,'open').click();await until(()=>elements.filePreview.textContent.includes('FILE /fixture/folder1/same.txt'));
   check(document.querySelectorAll('[data-preview-tab]').length===2,'review open uses live-file new-tab route');
   clickTab('review');action(2,'open').click();await until(()=>messages.at(-1)?.includes('unavailable'));
   check(document.querySelectorAll('[data-preview-tab]').length===2,'missing deleted file fails without reconstructing or adding a tab');
   clickTab('review');mode='held-copy';action(0,'copy').click();await until(()=>copyResolve);const messageCount=messages.length;await feature.openReview(ids[1]);copyResolve(true);await new Promise(r=>setTimeout(r,0));
   check(messages.length===messageCount&&elements.filePreview.dataset.reviewView===ids[1],'late copy completion has no feedback in another round');
   mode='held-file';action(4,'open').click();await until(()=>fileResolve);await feature.openReview(ids[2]);fileResolve();await new Promise(r=>setTimeout(r,10));
   check(document.querySelectorAll('[data-preview-tab]').length===2&&elements.filePreview.dataset.reviewView===ids[2],'late open result cannot add a tab or replace another review round');
   feature.close();return {checks,peak,requests:calls.length,expandedLimit:8,byteBudget:1048576,lineBudget:10000};
  });
 }finally{await context.close();}
}
async function main(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code042-continuous-review-')),host=await startIsolatedHost({disableRoutingV2:true});let browser;const result={dir};console.log(dir);
 try{browser=await chromium.launch({headless:true});result.contract=await contract(browser,host.ready.codeUrl);result.ok=true;}catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
