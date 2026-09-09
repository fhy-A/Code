const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'../../..'),app=fs.readFileSync(path.join(root,'app.js'),'utf8'),diff=fs.readFileSync(path.join(root,'src/ui/diff.js'),'utf8');
function setup(){
  const state={pendingEdits:{}},context=vm.createContext({window:{Code:{ui:{}}},state,formatToolResult:r=>r.error||JSON.stringify(r),isInternalGoalToolName:()=>false,
    agentEventMeta:(ctx,event,type)=>({agentRunId:ctx.agentRunId,agentEventType:type,agentEventSeq:event.seq}),
    findAgentProjectionMessage:(ctx,type,seq)=>ctx.messages.find(m=>m.meta?.agentEventType===type&&m.meta?.agentEventSeq===seq)});
  vm.runInContext(diff,context);const api=context.window.Code.ui.diff;context.getEditSuggestionInstanceId=api.getEditSuggestionInstanceId;
  for(const name of ['projectServerEditToolCompleted','projectAgentToolCompleted']){
    const a=app.indexOf('function '+name+'('),b=app.indexOf('\nfunction ',a+1);vm.runInContext(app.slice(a,b),context);
  }
  const ctx={agentRunId:'synthetic-run',messages:[]};
  const complete=(result,id='synthetic-call',seq=2)=>{
    if(!ctx.messages.some(m=>m.role==='tool-call'&&m.meta.toolCallId===id))ctx.messages.push({role:'tool-call',content:'synthetic tool',meta:{agentRunId:ctx.agentRunId,toolCallId:id,action:result.action,tool:{action:result.action}}});
    context.projectAgentToolCompleted(ctx,{seq,data:{toolCallId:id,name:result.action,result,outcome:result.ok===false?'failed':'succeeded'}});
    return ctx.messages.filter(m=>m.role==='tool-result').at(-1);
  };
  const feature=api.createDiffFeature({getPendingEdits:()=>state.pendingEdits});
  return {state,ctx,api,complete,render:m=>feature.renderEditSuggestionProjection(m,0)};
}
const outcomes=[];function check(name,fn){try{fn();outcomes.push({name,ok:true})}catch(e){outcomes.push({name,ok:false,error:e.stack})}}
const invalid={ok:false,action:'write_file',errorCode:'invalid_tool_arguments',error:'Unterminated string starting at: line 1 column 41 (char 40)'};
for(const [name,result] of [['parse',invalid],['validation',{...invalid,error:'path is required',fieldErrors:[{path:'path',message:'required'}]}],['io',{ok:false,action:'write_file',error:'access denied'}],['edit',{ok:false,action:'propose_edit',error:'target not found',applied:false}],['read',{ok:false,action:'read_file',error:'not found'}],['rejection_without_proposal',{ok:false,action:'write_file',rejected:true,error:'user declined'}]])check(name+'-failure-without-proposal-stays-in-tool-trace',()=>{
  const h=setup(),m=h.complete(result);assert.equal(m.meta.result.error,result.error);assert.equal(m.meta.outcome,'failed');assert.equal(m.meta.pendingEditId,undefined);assert.equal(m.meta.rejected,undefined);assert.equal(h.api.isEditSuggestionMessage(m),false);assert.equal(h.render(m),'');assert.equal(Object.keys(h.state.pendingEdits).length,0);
  h.complete(result);assert.equal(h.ctx.messages.filter(x=>x.role==='tool-result').length,1);
});
check('historical-fake-pending-is-filtered-without-mutation',()=>{
 const h=setup(),m={role:'tool-result',content:invalid.error,meta:{action:'write_file',serverManaged:true,pendingEditId:'server-edit-old',outcome:'failed',result:invalid,applied:false,rejected:false}};
 const frozen=JSON.stringify(m);assert(!h.api.isEditSuggestionMessage(m));assert.equal(h.render(m),'');assert.equal(JSON.stringify(m),frozen);
});
for(const approved of [false,true])check('real-proposal-failure-'+(approved?'after-approval':'before-approval'),()=>{
 const h=setup(),proposal={role:'tool-result',content:'--- a/example.txt\n+++ b/example.txt\n@@ -1 +1 @@\n-old\n+new',meta:{action:'write_file',path:'example.txt',agentRunId:'synthetic-run',toolCallId:'synthetic-call',pendingEditId:'server-edit-real',authorizationId:'auth-real',serverManaged:true,...(approved?{authorizationDecision:'approved'}:{})}};
 h.ctx.messages.push(proposal);const m=h.complete({ok:false,action:'write_file',error:'write failed',applied:false});assert.equal(m,proposal);assert.equal(m.meta.rejected,false);assert.equal(m.meta.applied,false);
 const html=h.render(m);assert(html.includes('toolProcessFailed'));assert(!html.includes('waitingApproval'));assert(!html.includes('appliedLabel'));assert(!html.includes('rejectedLabel'));assert(html.includes('example.txt'));
});
check('historical-failure-does-not-relabel-as-rejected-or-approved',()=>{
 const h=setup(),m={role:'tool-result',content:'--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b',meta:{action:'write_file',path:'x',serverManaged:true,authorizationId:'auth',pendingEditId:'old',authorizationDecision:'approved',rejected:true,outcome:'failed',result:{...invalid,applied:false}}};
 const snapshot=JSON.stringify(m),html=h.render(m);assert(html.includes('toolProcessFailed'));assert(!html.includes('rejectedLabel'));assert(!html.includes('appliedLabel'));assert.equal(JSON.stringify(m),snapshot);
});
check('successful-write-and-later-success-after-invalid-call',()=>{
 const h=setup();h.complete(invalid);const m=h.complete({ok:true,action:'write_file',path:'example.svg',diff:'--- a/example.svg\n+++ b/example.svg\n@@ -0,0 +1 @@\n+svg'},'second-call',3);
 assert(h.api.isEditSuggestionMessage(m));assert(h.render(m).includes('appliedLabel'));assert.equal(h.ctx.messages.filter(x=>h.api.isEditSuggestionMessage(x)).length,1);
});
check('explicit-user-rejection-remains-rejected',()=>{
 const h=setup();h.ctx.messages.push({role:'tool-result',content:'--- a/example.svg\n+++ b/example.svg\n@@ -1 +1 @@\n-a\n+b',meta:{action:'write_file',path:'example.svg',agentRunId:'synthetic-run',toolCallId:'synthetic-call',pendingEditId:'real',authorizationId:'auth',serverManaged:true,authorizationDecision:'rejected'}});const m=h.complete({ok:false,action:'write_file',path:'example.svg',rejected:true,error:'user declined'});assert(h.api.isEditSuggestionMessage(m));assert(h.render(m).includes('rejectedLabel'));assert(!h.render(m).includes('toolProcessFailed'));
});
check('already-applied-proposal-keeps-applied-fact-on-later-failure',()=>{
 const h=setup(),m={role:'tool-result',content:'--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b',meta:{action:'write_file',path:'x',agentRunId:'synthetic-run',toolCallId:'synthetic-call',serverManaged:true,pendingEditId:'x',applied:true}};h.ctx.messages.push(m);h.complete({ok:false,action:'write_file',error:'follow-up failed'});assert(h.render(m).includes('appliedLabel'));
});
check('genuine-pending-proposal-remains-pending',()=>{
 const h=setup(),m={role:'tool-result',content:'--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b',meta:{action:'write_file',path:'x',serverManaged:true,pendingEditId:'x',authorizationId:'auth'}};assert(h.render(m).includes('waitingApproval'));
});
console.log(JSON.stringify({ok:outcomes.every(x=>x.ok),outcomes},null,2));if(outcomes.some(x=>!x.ok))process.exitCode=1;
