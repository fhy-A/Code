const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.resolve(__dirname,'../../../app.js'),'utf8');
const code=source.slice(source.indexOf('const followUpSubmissions ='),source.indexOf('async function cancelQueuedSessionMessage('));
const pump=source.slice(source.indexOf('async function pumpQueuedSessionMessages('),source.indexOf('async function resumePersistedQueuedMessages('));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
const flush=()=>new Promise(setImmediate);
function setup(){
  let messages=[],queue=[],streaming=true,revision=0;
  const log=[],control={profile:'read',credentials:async()=>({routeRef:'',catalogRevision:0}),save:async()=>({id:'s',revision:++revision}),steer:async()=>({result:{steerId:'accepted'}})};
  const state={sessionId:'s',_sessionRuns:{},_queuedMessagePumps:new Set()},run={abortController:new AbortController()};
  const ctx={sessionId:'s',model:'fixture',agentRunId:'parent',run,messages,stats:{}};run._activeCtx=ctx;state._sessionRuns.s=run;
  const sandbox=vm.createContext({console,Promise,Map,Set,Date,Math,structuredClone,queueMicrotask,state,
    els:{toolPreset:{value:'default'},temperature:{value:.2}},t:key=>key,
    getSessionMessages:()=>messages,setSessionMessages:(_id,value)=>{messages=value;ctx.messages=value},getSessionStats:()=>({}),
    getQueuedMessageCheckpoints:()=>queue,setQueuedMessageCheckpoints:(_id,value)=>{queue=value},
    getSessionRunState:()=>({}),setSessionRunState(){},getBackgroundRunCheckpoints:()=>[],
    getSelectedModel:()=> 'fixture',getReasoningSelectionForModel:()=>null,getThinkingLevel:()=> 'auto',
    normalizeImageRouteDispatch:()=>null,getSelectedImageRoute:()=>null,getPermissionProfile:()=>control.profile,
    getEffectiveMaxTokens:()=>1024,getModelContextResolution:()=>({}),queuedMessageCheckpoint:item=>({...item}),
    renderSessionMessages:id=>log.push({type:'render',id,texts:messages.map(m=>m.content)}),
    getModelDispatchCredentials:(...args)=>control.credentials(...args),uploadImagesForStorage:async()=>[],
    saveSessionState:async(...args)=>{log.push({type:'save',id:args[0],messages:JSON.parse(JSON.stringify(args[1]))});return control.save(...args)},
    isSessionStreaming:()=>streaming,ensureSessionRun:()=>run,ownsActiveRunContext:value=>value===ctx,
    agentRuntime:{steerAgentRun:async(id,body)=>{log.push({type:'steer',id,key:body.clientRequestId});return control.steer(id,body)}},
    messageScrollController:null,modelRouteFailureCode:()=>'',updateQueuedMessageItem(){},
    runQueuedSessionMessage:async(_id,item)=>{log.push({type:'dispatch',id:item.id,text:item.userText});queue=queue.filter(q=>q.id!==item.id);return true},
  });
  vm.runInContext(code+pump,sandbox);
  return {api:vm.runInContext('({enqueueSessionMessage,steerSessionMessage,retryFailedFollowUpMessage,recoverUnadmittedFollowUpMessages,submitSessionSteer,resumePendingSessionSteers,pumpQueuedSessionMessages,followUpSubmissions})',sandbox),
    state,ctx,log,control,messages:()=>messages,queue:()=>queue,streaming:value=>{streaming=value},
    restore:saved=>{messages=JSON.parse(JSON.stringify(saved));ctx.messages=messages;run._activeCtx=null}};
}
async function main(){
  const outcomes=[];async function check(name,fn){try{await fn();outcomes.push({name,ok:true})}catch(error){outcomes.push({name,ok:false,error:String(error.stack)})}}
  await check('queue-shows-before-qualification-and-preserves-arrival-order',async()=>{
    const h=setup(),first=deferred();let count=0;h.control.credentials=()=>++count===1?first.promise:Promise.resolve({});
    const a=h.api.enqueueSessionMessage('s','first'),b=h.api.enqueueSessionMessage('s','second');
    assert.deepEqual(h.messages().map(m=>m.content),['first','second']);
    assert.equal(h.log.filter(e=>e.type==='render').length,2);await flush();
    h.streaming(false);await h.api.pumpQueuedSessionMessages('s');assert.equal(h.log.filter(e=>e.type==='dispatch').length,0);
    first.resolve({});await Promise.all([a,b]);await flush();
    assert.deepEqual(h.log.filter(e=>e.type==='dispatch').map(e=>e.text),['first','second']);assert.equal(h.api.followUpSubmissions.size,0);
  });
  await check('queue-save-unconfirmed-never-dispatches-and-retry-keeps-identity',async()=>{
    const h=setup();h.control.save=async()=>({id:'s',revision:1,_sessionRevisionConflict:true});
    await assert.rejects(h.api.enqueueSessionMessage('s','saved later'),/followUpSaveFailed/);
    const id=h.messages()[0].meta.queuedDispatch.id;
    h.streaming(false);await h.api.pumpQueuedSessionMessages('s');assert.equal(h.log.filter(e=>e.type==='dispatch').length,0);
    h.streaming(true);h.control.save=async()=>({id:'s',revision:2});
    await h.api.retryFailedFollowUpMessage('s',h.messages()[0].id);assert.equal(h.messages().length,1);assert.equal(h.queue()[0].id,id);
  });
  await check('qualification-failure-keeps-copyable-message-and-retry-reuses-it',async()=>{
    const h=setup();h.control.credentials=async()=>{throw new Error('no route')};
    await assert.rejects(h.api.enqueueSessionMessage('s','retained'),/no route/);const id=h.messages()[0].id;
    assert.equal(h.messages()[0].content,'retained');assert.equal(h.queue().length,0);
    h.control.credentials=async()=>({});await h.api.retryFailedFollowUpMessage('s',id);assert.equal(h.messages().length,1);assert.equal(h.messages()[0].id,id);
  });
  await check('steer-shows-before-save-and-observer-cannot-overtake-save',async()=>{
    const h=setup(),gate=deferred();h.control.save=()=>gate.promise;
    const sent=h.api.steerSessionMessage('s','instant');await flush();
    assert.equal(h.messages()[0].content,'instant');assert.equal(h.log.filter(e=>e.type==='steer').length,0);
    await h.api.resumePendingSessionSteers(h.ctx);assert.equal(h.log.filter(e=>e.type==='steer').length,0);
    gate.resolve({id:'s',revision:1});await sent;assert.equal(h.log.filter(e=>e.type==='steer').length,1);
  });
  await check('steer-save-failure-and-resume-require-confirmed-save',async()=>{
    const h=setup();h.control.save=async()=>{throw new Error('offline')};
    await assert.rejects(h.api.steerSessionMessage('s','retain steer'),/offline/);const id=h.messages()[0].meta.steerDispatch.clientRequestId;
    await h.api.resumePendingSessionSteers(h.ctx);assert.equal(h.log.filter(e=>e.type==='steer').length,0);
    h.control.save=async()=>({id:'s',revision:1});await h.api.retryFailedFollowUpMessage('s',h.messages()[0].id);assert.equal(h.messages().length,1);
    assert.equal(h.log.find(e=>e.type==='steer').key,id);
  });
  await check('acceptance-failure-retry-uses-same-request-and-concurrent-replay-coalesces',async()=>{
    const h=setup();h.control.steer=async()=>{throw new Error('lost response')};
    await assert.rejects(h.api.steerSessionMessage('s','once'),/lost response/);const id=h.log.find(e=>e.type==='steer').key;
    const gate=deferred();h.control.steer=()=>gate.promise;
    const a=h.api.submitSessionSteer(h.ctx,h.messages()[0]),b=h.api.submitSessionSteer(h.ctx,h.messages()[0]);await flush();
    assert.equal(h.log.filter(e=>e.type==='steer').length,2);gate.resolve({result:{steerId:'same'}});await Promise.all([a,b]);
    assert(h.log.filter(e=>e.type==='steer').every(e=>e.key===id));assert.equal(h.messages().length,1);
  });
  await check('409-converts-same-visible-message-to-queue-once',async()=>{
    const h=setup();h.control.steer=async()=>{const error=new Error('terminal');error.status=409;throw error};
    await h.api.steerSessionMessage('s','next turn');assert.equal(h.messages().length,1);assert.equal(h.queue().length,1);
    assert(!h.messages()[0].meta.steerDispatch);assert.equal(h.queue()[0].userText,'next turn');
  });
  await check('accepted-receipt-save-failure-retry-does-not-send-again',async()=>{
    const h=setup();let count=0;h.control.save=async()=>{if(++count===2)throw new Error('disk full');return {id:'s',revision:1}};
    await assert.rejects(h.api.steerSessionMessage('s','accepted'),/followUpReceiptSaveFailed/);
    assert.equal(h.messages()[0].meta.steerDispatch.status,'accepted');h.control.save=async()=>({id:'s',revision:2});
    await h.api.retryFailedFollowUpMessage('s',h.messages()[0].id);assert.equal(h.log.filter(e=>e.type==='steer').length,1);assert.equal(h.messages().length,1);
    assert(!h.log.filter(e=>e.type==='save').at(-1).messages[0].meta.steerDispatch.failureCode);
  });
  await check('session-switch-does-not-retarget-delayed-acceptance',async()=>{
    const h=setup(),gate=deferred();h.control.save=()=>gate.promise;const sent=h.api.steerSessionMessage('s','origin');await flush();
    h.state.sessionId='other';h.ctx.agentRunId='';gate.resolve({id:'s',revision:1});await sent;
    assert(h.log.filter(e=>e.type==='save'||e.type==='render').every(e=>e.id==='s'));assert.equal(h.log.find(e=>e.type==='steer').id,'parent');
  });
  await check('same-text-new-send-is-distinct-and-does-not-inherit-old-images',async()=>{
    const h=setup();h.control.credentials=async()=>{throw new Error('no route')};
    await assert.rejects(h.api.enqueueSessionMessage('s','same',[{mime:'image/png',base64:'fixture'}]));
    const first=h.messages()[0];h.control.credentials=async()=>({});await h.api.enqueueSessionMessage('s','same',[]);
    assert.equal(h.messages().length,2);assert.notEqual(h.messages()[1].id,first.id);
    assert.equal(h.messages()[1].content,'same');assert(!h.messages()[1]._images);
    await h.api.retryFailedFollowUpMessage('s',first.id);assert.equal(h.messages().length,2);
  });
  await check('refreshed-failed-steer-explicit-retry-keeps-original-request',async()=>{
    const h=setup();h.control.steer=async()=>{throw new Error('offline')};
    await assert.rejects(h.api.steerSessionMessage('s','restore'));
    const snapshot=h.messages(),id=snapshot[0].id,key=snapshot[0].meta.steerDispatch.clientRequestId;
    h.restore(snapshot);h.control.steer=async()=>({result:{steerId:'same'}});
    await h.api.retryFailedFollowUpMessage('s',id);assert.equal(h.messages().length,1);assert.equal(h.log.filter(e=>e.type==='steer').at(-1).key,key);
  });
  await check('refresh-during-qualification-keeps-message-but-never-invents-admission',async()=>{
    const h=setup(),gate=deferred();h.control.credentials=()=>gate.promise;
    const sent=h.api.enqueueSessionMessage('s','interrupted');const saved=JSON.parse(JSON.stringify(h.messages()));
    h.api.recoverUnadmittedFollowUpMessages('s');assert.equal(h.messages()[0].meta.queuedDispatch.status,'pending');
    const restored=setup();restored.restore(saved);restored.api.recoverUnadmittedFollowUpMessages('s');
    assert.equal(restored.queue().length,0);assert.equal(restored.messages()[0].meta.queuedDispatch.status,'failed');
    await restored.api.retryFailedFollowUpMessage('s',saved[0].id);assert.equal(restored.messages().length,1);assert.equal(restored.queue()[0].id,saved[0].meta.queuedDispatch.id);
    gate.resolve({});await sent;
  });
  await check('retry-retains-the-existing-queue-permission-snapshot',async()=>{
    const h=setup();h.control.save=async()=>{throw new Error('offline')};
    await assert.rejects(h.api.enqueueSessionMessage('s','frozen'));
    h.control.profile='bypass';h.control.save=async()=>({id:'s',revision:1});
    await h.api.retryFailedFollowUpMessage('s',h.messages()[0].id);assert.equal(h.queue()[0].permissionProfile,'read');
  });
  for (const failSave of [true,false]) await check(`queue-execution-save-${failSave?'failure-blocks':'confirmation-precedes'}-dispatch`,async()=>{
    const gate=deferred(),events=[],message={role:'user',content:'queued',meta:{}},messages=[message];
    const item={id:'queue-id',clientRequestId:'request-id',userText:'queued',model:'fixture',permissionProfile:'read'};
    const sandbox=vm.createContext({console:{error(){}},structuredClone,Date,
      findQueuedUserMessage:()=>message,updateQueuedMessageItem(){},
      getSessionMessages:()=>messages,getSessionStats:()=>({}),
      saveFollowUpMessages:()=>gate.promise,saveSessionState:async()=>({}),
      sendMessage:async(text,options)=>events.push({type:'dispatch',text,options}),
      preserveFailedFollowUp:()=>events.push({type:'preserved'}),
      appendSessionMessages:(_id,value)=>messages.push(value),t:key=>key,escapeHtml:value=>value,
      finishQueuedSessionMessage:(_id,_queueId,ok)=>events.push({type:'finished',ok}),
    });
    vm.runInContext(source.slice(source.indexOf('async function runQueuedSessionMessage('),source.indexOf('async function pumpQueuedSessionMessages(')),sandbox);
    const running=vm.runInContext('runQueuedSessionMessage',sandbox)('s',item);await flush();
    assert.equal(events.length,0);
    if(failSave)gate.reject(new Error('save offline'));else gate.resolve({id:'s',revision:1});
    assert.equal(await running,!failSave);
    const dispatches=events.filter(e=>e.type==='dispatch');assert.equal(dispatches.length,failSave?0:1);
    if(failSave){assert(events.some(e=>e.type==='preserved'));assert.equal(message.content,'queued');assert.equal(message.meta.detachedFromMain,true)}
    else{assert.equal(dispatches[0].options.clientRequestId,'request-id');assert.equal(dispatches[0].options.existingMessage,message)}
  });
  console.log(JSON.stringify({ok:outcomes.every(o=>o.ok),outcomes},null,2));if(outcomes.some(o=>!o.ok))process.exitCode=1;
}
main().catch(error=>{console.error(error);process.exitCode=1});
