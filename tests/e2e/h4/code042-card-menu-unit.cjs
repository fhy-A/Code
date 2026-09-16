// Production delegated handler; no model, DOM mutation, OS open or clipboard.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
global.window={Code:{features:{}}};require('../../../src/features/files.js');
const {isAbsoluteFilePath}=window.Code.features.files;
const source=fs.readFileSync(path.join(__dirname,'../../../app.js'),'utf8');
const start=source.indexOf('els.messageList.addEventListener("contextmenu", event => {');
const handlerSource=source.slice(start,source.indexOf('\nasync function loadTaskReview(',start));
assert(start>0);
let passed=0;
function fixture(filePath='C:\\工作 区\\报告.txt'){
 const rid='a'.repeat(32),key='b'.repeat(64),ref={rootRunId:rid},owner={meta:{recordedChangeReview:ref}};
 const op={entityKind:'file',fileKey:key,path:filePath,kind:'delete'};
 const summary={sessionId:'session-a',rootRunId:rid,revision:'r1',operations:[op]};
 const state={sessionId:'session-a',_foregroundNavigationSeq:3},rows=[owner],summaries=new WeakMap([[ref,{summary}]]);
 const row={dataset:{recordedReview:rid,reviewFile:key},textContent:'FAKE.txt',title:'C:/untrusted/path'};
 let handler,prevented=false,menu=null,closed=0;
 vm.runInNewContext(handlerSource,{state,isAbsoluteFilePath,recordedChangeSummaries:summaries,
  getSessionMessages:()=>rows,els:{messageList:{contains:element=>element===row,addEventListener:(type,fn)=>{assert.equal(type,'contextmenu');handler=fn;}}},
  filesFeature:{closeFileContextMenu:()=>closed++,showFileContextMenu:(...args)=>menu=args}});
 return {state,rows,ref,owner,summary,op,summaries,row,fire:()=>{menu=null;handler({target:{closest:()=>row},clientX:30,clientY:40,preventDefault:()=>prevented=true});return menu;},get prevented(){return prevented;},get closed(){return closed;}};
}
for(const p of ['C:\\工作 区\\报告.txt','D:/with spaces/notes.txt','\\\\server\\share\\图.md','/tmp/space here/文.txt']){
 const f=fixture(p),menu=f.fire();assert.equal(menu[2],p);assert.equal(menu[3],'file');assert.equal(menu[4].returnFocus,f.row);assert(menu[4].isCurrent());assert(f.prevented&&f.closed);passed++;
}
for(const p of ['relative.txt','C:drive-relative.txt','https://example.test/a','',null,'C:/bad\0name']){
 assert.equal(fixture(p).fire(),null);passed++;
}
for(const change of [f=>f.summaries.delete(f.ref),f=>f.summary.sessionId='other',f=>f.summary.rootRunId='other',f=>f.row.dataset.reviewFile='missing',f=>f.op.entityKind='directory']){
 const f=fixture();change(f);assert.equal(f.fire(),null);passed++;
}
for(const change of [f=>f.state.sessionId='other',f=>f.state._foregroundNavigationSeq++,f=>f.rows.push({meta:{recordedChangeReview:{rootRunId:f.ref.rootRunId}}}),f=>f.owner.meta.recordedChangeReview={...f.ref},f=>f.summaries.set(f.ref,{summary:{...f.summary}}),f=>f.summary.revision='r2',f=>f.summary.sessionId='other',f=>f.summary.rootRunId='other',f=>f.summary.operations=null,f=>f.op.path='C:/replaced.txt',f=>f.summary.operations=[{...f.op}]]){
 const f=fixture(),menu=f.fire();change(f);assert.equal(menu[4].isCurrent(),false);passed++;
}
const cold=fixture();cold.owner.meta.recordedChangeReview={...cold.ref,path:'C:/imported.txt',operations:[cold.op]};assert.equal(cold.fire(),null);passed++;
console.log(JSON.stringify({passed,productionHandler:true,externalOperations:0}));
