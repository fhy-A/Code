"""Reasoning preference, payload, queue and transport contracts in actual JS."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def test_public_round_reference_and_budget_validation():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const window={Code:{agent:{}}};vm.runInNewContext(fs.readFileSync('src/agent/model-request.js','utf8'),{window});
const api=window.Code.agent.modelRequest;
const m={role:'assistant',content:'Checking files',meta:{protocolRef:'round-ref',protocolContent:'',protocolDisplayContent:'Checking files',toolCalls:[{id:'c',function:{name:'list_files',arguments:'{}'}}]}};
const wire=api.mapMessageForApi(m);assert.equal(wire.content,'');assert.equal(wire._protocolRef,'round-ref');
m.content='edited';assert.equal(api.mapMessageForApi(m)._protocolRef,undefined);assert.equal(api.mapMessageForApi(m).content,'edited');
const route={modelId:'claude-sonnet-4-5',routeRef:'r',reasoning:{schemaVersion:2,capabilityRevision:'rev',intents:['default','low','medium','high'],minimumOutputTokens:{low:2048,medium:3072,high:5120}}};
assert.throws(()=>api.snapshotReasoningSelection({mode:'v2',intent:'high'},route,4096),/reasoning_budget_insufficient/);
assert.equal(api.snapshotReasoningSelection({mode:'v2',intent:'high'},route,8192).intent,'high');
'''
    result = subprocess.run(["node", "-"], input=script, cwd=ROOT, text=True, capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_picker_without_model_never_projects_saved_effort_or_legacy_status():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const element=()=>({textContent:'',hidden:false,attributes:{},setAttribute(k,v){this.attributes[k]=v},classList:{selected:false,toggle(k,v){this.selected=v},contains(){return this.selected}}});
const ids=Object.fromEntries(['modelReasoningDropdown','modelReasoningLabel','modelReasoningSeparator','modelPickerCurrent','reasoningPickerStatus'].map(id=>[id,element()]));
const options=['default','low','medium','high'].map(value=>({...element(),dataset:{value}}));
const els={thinkingPillLabel:element(),modelPillBtn:element(),thinkingPillDropdown:{...element(),querySelectorAll:()=>options},modelPillDropdown:{querySelectorAll:()=>[]}};
let model='',cap={schemaVersion:2,intents:['default','low','medium','high']};
const sandbox={document:{getElementById:id=>ids[id]},els,getSelectedModel:()=>model,selectedModelRoute:()=>({reasoning:cap}),t:x=>x};
const app=fs.readFileSync('app.js','utf8'),start=app.indexOf('function reasoningIntentLabel('),end=app.indexOf('function closeModelPicker(',start);
vm.runInNewContext(app.slice(start,end),sandbox);
for(const preference of [...['auto','off','high','max','broken'].map(value=>({mode:'legacy',value})),...['default','low','medium','high'].map(intent=>({mode:'v2',intent})),{mode:'invalid'}]){
 const before=JSON.stringify(preference);sandbox.reasoningPreference=preference;model='';sandbox.updateReasoningPicker();
 assert.equal(els.modelPillBtn.attributes['aria-label'],'selectModel');
 assert.equal(ids.modelReasoningLabel.textContent,'');assert(ids.modelReasoningLabel.hidden);assert(ids.modelReasoningSeparator.hidden);
 assert.equal(els.thinkingPillLabel.textContent,'reasoningSelectModelFirst');assert.equal(ids.reasoningPickerStatus.textContent,'reasoningSelectModelFirst');
 assert(options.every(o=>o.disabled&&o.attributes['aria-checked']==='false'));
 model='gpt-5.5';sandbox.updateReasoningPicker();assert(!ids.modelReasoningLabel.hidden);assert(!ids.modelReasoningSeparator.hidden);
 assert.equal(JSON.stringify(preference),before);
 model='';sandbox.updateReasoningPicker();assert.equal(els.thinkingPillLabel.textContent,'reasoningSelectModelFirst');assert.equal(JSON.stringify(preference),before);
}
model='gpt-5.5';cap=undefined;sandbox.reasoningPreference={mode:'v2',intent:'high'};sandbox.updateReasoningPicker();
assert.equal(els.thinkingPillLabel.textContent,'reasoningPending');assert.equal(ids.reasoningPickerStatus.textContent,'reasoningSelectRequired');
console.log('ok');
'''
    result = subprocess.run(["node", "-"], input=script, cwd=ROOT, text=True,
                            capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_enqueue_freezes_intent_before_async_route_resolution():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('app.js','utf8');let resume;const gate=new Promise(r=>resume=r);
let intent='high',thinking='off',captured;const messages=[];
const sandbox={structuredClone,Date,Math,t:x=>x,
 getSelectedModel:()=> 'gpt-5.5',getReasoningSelectionForModel:()=>({schemaVersion:2,intent,routeRef:'mr1_a'}),
 getThinkingLevel:()=>thinking,getModelDispatchCredentials:async()=>{await gate;return{routeRef:'mr1_a',catalogRevision:1}},
 normalizeImageRouteDispatch:()=>null,getSelectedImageRoute:()=>null,getPermissionProfile:()=> 'read',
 els:{toolPreset:{value:'default'},temperature:{value:'0.2'}},getEffectiveMaxTokens:()=>4096,getModelContextResolution:()=>({}),
 uploadImagesForStorage:async()=>[],queuedMessageCheckpoint:x=>structuredClone(x),getQueuedMessageCheckpoints:()=>[],
 setQueuedMessageCheckpoints:(_,items)=>captured=items[0],getSessionMessages:()=>messages,setSessionMessages:()=>{},
 saveSessionState:async()=>{},getSessionStats:()=>({}),renderSessionMessages:()=>{},isSessionStreaming:()=>true};
const start=app.indexOf('async function enqueueSessionMessage('),end=app.indexOf('function followUpMessageText(',start);
vm.runInNewContext(app.slice(start,end)+';globalThis.enqueue=enqueueSessionMessage;',sandbox);
(async()=>{
 const pending=sandbox.enqueue('s','queued fixture');intent='low';thinking='max';resume();await pending;
 assert.equal(captured.reasoningSelection.intent,'high');assert.equal(captured.thinkingLevel,'off');
 assert.equal(messages[0].meta.queuedDispatch.reasoningSelection.intent,'high');
 await sandbox.enqueue('s','retry',{length:0},{existingMessage:messages[0]});
 assert.equal(captured.reasoningSelection.intent,'high');assert.equal(captured.thinkingLevel,'off');
 await sandbox.enqueue('s','old',{length:0},{existingMessage:{role:'user',content:'old',_model:'gpt-5.5'}});
 assert.equal(captured.reasoningSelection,null);
 console.log('ok');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-"], input=script, cwd=ROOT, text=True,
                            capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_preferences_payloads_and_frozen_queues():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const sandbox={window:{Code:{agent:{}}},structuredClone};
vm.runInNewContext(fs.readFileSync('src/agent/model-request.js','utf8'),sandbox);
vm.runInNewContext(fs.readFileSync('src/agent/subagents.js','utf8'),sandbox);
const api=sandbox.window.Code.agent.modelRequest;
const copy=x=>JSON.parse(JSON.stringify(x));
const route={modelId:'gpt-5.5',routeRef:'mr1_a',reasoning:{schemaVersion:2,capabilityRevision:'revision-a',intents:['default','low','medium','high']}};
const unknown={...route,routeRef:'mr1_b',reasoning:{...route.reasoning,intents:['default']}};
for(const value of ['auto','off','high','max']){
 const preference=api.initialReasoningPreference({rawLegacy:value});
 assert.deepEqual(copy(preference),{mode:'legacy',value});
 assert.equal(api.snapshotReasoningSelection(preference,route),null);
 const old=api.assembleModelRequestPayload({model:'o3',thinkingLevel:value});
 assert.equal(old.reasoning_effort,{auto:'low',high:'medium',max:'high'}[value]);
 for(const intent of ['default','low','medium','high']){
  const next=api.initialReasoningPreference({rawLegacy:value,rawV2:JSON.stringify({schemaVersion:2,intent})});
  const selection=api.snapshotReasoningSelection(next,route);
  const wire=api.assembleModelRequestPayload({model:'claude-sonnet-4-5',thinkingLevel:value,reasoningSelection:selection});
  assert.equal(wire.thinking,undefined);assert.equal(wire.reasoning_effort,undefined);assert.equal(wire.reasoningSelection,undefined);
 }
}
assert.deepEqual(copy(api.initialReasoningPreference({hasLegacyInstall:true})),{mode:'legacy',value:'auto'});
assert.deepEqual(copy(api.initialReasoningPreference()),{mode:'v2',intent:'default'});
for(const rawV2 of ['bad','null','{}','{"schemaVersion":3,"intent":"low"}'])assert.equal(api.initialReasoningPreference({rawV2}).mode,'invalid');
for(const rawLegacy of ['','broken'])assert.throws(()=>api.snapshotReasoningSelection(api.initialReasoningPreference({rawLegacy}),route));
assert.throws(()=>api.snapshotReasoningSelection({mode:'v2',intent:'high'},unknown));
assert.throws(()=>api.snapshotReasoningSelection({mode:'v2',intent:'default'},{...route,reasoning:undefined}));
assert.throws(()=>api.snapshotReasoningSelection({mode:'v2',intent:'default'},{...route,reasoning:{...route.reasoning,intents:[],reason:'reasoning_protocol_unsupported'}}));
const selected=api.snapshotReasoningSelection({mode:'v2',intent:'high'},route);
const app=fs.readFileSync('app.js','utf8');
const start=app.indexOf('function queuedMessageCheckpoint('),end=app.indexOf('function findQueuedUserMessage(',start);
vm.runInNewContext(app.slice(start,end)+';globalThis.queue=queuedMessageCheckpoint;',Object.assign(sandbox,{normalizeImageRouteDispatch:()=>null}));
const queued=sandbox.queue({id:'q',model:'gpt-5.5',thinkingLevel:'auto',reasoningSelection:selected});
selected.intent='low';assert.equal(queued.reasoningSelection.intent,'high');
assert.equal(queued.thinkingLevel,'auto');assert.equal(sandbox.queue({id:'old'}).reasoningSelection,null);
const restored=JSON.parse(JSON.stringify(queued));assert.equal(restored.reasoningSelection.intent,'high');
const child=sandbox.window.Code.agent.subagents.createSubAgentContext({parentContext:{reasoningSelection:restored.reasoningSelection},taskPrompt:'fixture'});
assert.equal(child.reasoningSelection.intent,'high');
let background;
Object.assign(sandbox,{AbortController,findBackgroundUserMessage:()=>null,getSessionStats:()=>({}),
 setBackgroundRunCheckpoint:(_,value)=>background=value,
 buildBackgroundJobCheckpoint:sandbox.window.Code.agent.subagents.buildBackgroundJobCheckpoint,
 createSubContext:(parentContext,taskPrompt)=>sandbox.window.Code.agent.subagents.createSubAgentContext({parentContext,taskPrompt}),
 backgroundJobElapsedMs:()=>0});
for(const [from,to] of [['function syncBackgroundJobCheckpoint(','async function persistBackgroundJob('],
 ['function createBackgroundServerContext(','async function runBackgroundSubAgentJob(']]){
 const at=app.indexOf(from);vm.runInNewContext(app.slice(at,app.indexOf(to,at)),sandbox);
}
const job={id:'bg',sessionId:'s',status:'pending',model:'gpt-5.5',thinkingLevel:'off',userText:'fixture',taskPrompt:'fixture',reasoningSelection:restored.reasoningSelection};
sandbox.syncBackgroundJobCheckpoint(job);job.reasoningSelection.intent='low';assert.equal(background.reasoningSelection.intent,'high');
const context=sandbox.createBackgroundServerContext({...job,reasoningSelection:background.reasoningSelection});
assert.equal(context.reasoningSelection.intent,'high');assert.equal(context.thinkingLevel,'off');
background.reasoningSelection.intent='medium';assert.equal(context.reasoningSelection.intent,'high');
assert.equal(sandbox.createBackgroundServerContext({...job,reasoningSelection:undefined}).reasoningSelection,null);
console.log(JSON.stringify({ok:true,legacyCases:4,v2Combinations:16,queueFrozen:true,childInherited:true}));
'''
    result = subprocess.run(["node", "-"], input=script, cwd=ROOT, text=True,
                            capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"]


def test_reasoning_metadata_stays_outside_wire_payload():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const calls=[];const window={Code:{agent:{},services:{}}};
const fetch=async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({agentRunId:'fixture'})}};
vm.runInNewContext(fs.readFileSync('agent-runtime.js','utf8'),{window,fetch,AbortController,setTimeout,clearTimeout,ReadableStream,TextEncoder,TextDecoder});
(async()=>{
 const payload={model:'gpt-5.5',messages:[]},selection={schemaVersion:2,intent:'high'};
 await window.Code.agent.runtime.createAgentRun({sessionId:'s',payload,routeRef:'mr1_a',catalogRevision:1,reasoningSelection:selection});
 assert.equal(calls[0].body.reasoningSelection.intent,'high');assert.equal(calls[0].body.payload.reasoningSelection,undefined);
 await window.Code.agent.runtime.createAgentRun({sessionId:'s',payload,routeRef:'mr1_a'});assert.equal(calls[1].body.reasoningSelection,undefined);
 console.log(JSON.stringify({ok:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(["node", "-"], input=script, cwd=ROOT, text=True,
                            capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"]
