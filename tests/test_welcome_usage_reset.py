import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.window={};require('./src/core/namespace.js');require('./src/core/state.js');
require('./src/features/sessions.js');require('./src/ui/panels.js');
const storageMap=new Map(),storage={getItem:k=>storageMap.get(k)??null,setItem:(k,v)=>storageMap.set(k,String(v)),removeItem:k=>storageMap.delete(k)};
const state=window.Code.core.state.createAppState(storage);
const access=window.Code.core.state.createSessionStateAccessors(state);
const node=()=>({value:'',textContent:'',hidden:false,attrs:{},setAttribute(k,v){this.attrs[k]=String(v)},
 classList:{values:new Set(),add(...xs){xs.forEach(x=>this.values.add(x))},remove(...xs){xs.forEach(x=>this.values.delete(x))},contains(x){return this.values.has(x)},toggle(x,on){on?this.add(x):this.remove(x)}}});
const elements=new Proxy({}, {get:(o,k)=>o[k]??(o[k]=node())});
const oldMessages=[{role:'user',content:'retained task'},{role:'assistant',content:'retained result'}];
const oldStats={input:1000,output:200,cache:500,cost:3,cacheReported:true};
const oldUsage={prompt_tokens:900,completion_tokens:200};
const saved=[];
const panels=window.Code.ui.panels.createPanelsFeature({elements,
 getMessages:()=>state.messages,getStats:()=>state.stats,getSessionId:()=>state.sessionId,
 getSessionLastUsage:access.getSessionLastUsage,getSession:()=>state.sessions.find(s=>s.id===state.sessionId),
 getContextMessages:items=>items,estimateTokens:text=>text.length,getSystemPrompt:()=> 'system prompt',
 getContextLimit:()=>1000,getSelectedModel:()=> 'fixture-model',formatCompact:String,formatNumber:String,t:k=>k});
const app=fs.readFileSync('app.js','utf8');
const context={state,els:elements,saveSessionState:(...args)=>{saved.push(args);return Promise.resolve()},
 cancelAnimationFrame:()=>{},renderMessages:()=>panels.updateStatsPanel(),renderSessions:()=>{},
 updateStatsPanel:()=>panels.updateStatsPanel(),showToast:()=>{},t:k=>k};
vm.createContext(context);
const install=(start,end)=>vm.runInContext(app.slice(app.indexOf(start),app.indexOf(end,app.indexOf(start))),context);
install('function cacheActiveSessionState()', 'function isSessionStreaming(');
install('function clearCurrentSession()', 'function exportMarkdown(');
const navigation=window.Code.features.sessions.createSessionNavigation({state,elements,storage,stateAccessors:access,
 data:{createSession:async body=>({id:'fresh',title:body.title,projectId:body.projectId,messages:[]}),
       getSession:async()=>({id:'old',messages:oldMessages,stats:oldStats,lastUsage:oldUsage})},
 project:{getById:id=>id?{id}:null,getPrimaryPath:()=>'',getCurrentRoot:()=>'',getCurrentProject:()=>null,pathsEqual:(a,b)=>a===b,saveRoot:async()=>{}},
 branch:{syncMetadata:()=>null},
 recovery:{reconcilePersistedUserInputRequest:async()=>{},restoreAuthorizationRequest:()=>{},restoreSkillEvidenceRequest:()=>{}},
 view:{cacheActiveSessionState:context.cacheActiveSessionState,closeTopPanels:()=>{},syncActiveStreamingState:()=>{},
 renderMessages:context.renderMessages,renderSessions:()=>{},updateGroupBadge:()=>{},updateStatsPanel:context.updateStatsPanel,
 updateSendButtonState:()=>{},resetRenderCache:()=>{},refreshSessions:async()=>{},scheduleMessagesScrollToBottom:()=>{},showToast:()=>{}},t:k=>k});
context.invalidateForegroundSessionNavigation=navigation.invalidateForegroundSessionNavigation;
state.sessionId='old';state.sessions=[{id:'old'}];elements.sessionTitle.value='old task';
access.setSessionMessages('old',oldMessages);access.setSessionStats('old',oldStats);access.setSessionLastUsage('old',oldUsage);
const initial=panels.updateStatsPanel();assert.equal(initial.contextTokens,900);assert.equal(elements.statContext.textContent,'90%');
function assertEmptyDisplay(){
 const actual=panels.updateStatsPanel();
 assert.equal(actual.contextTokens,'system prompt'.length);
 assert.equal(actual.input,0);assert.equal(actual.output,0);assert.equal(actual.cacheHit,null);
 assert.equal(elements.statContext.textContent,'1%');assert.equal(elements.statCacheHit.hidden,true);
 assert.equal(elements.tokenCacheHit.textContent,'—');assert.equal(elements.usageStrip.classList.contains('danger'),false);
 const arc=Number(elements.ctxRingFill.attrs['stroke-dasharray'].split(' ')[0]);
 assert.ok(Math.abs(arc-2*Math.PI*5*actual.contextPct/100)<1e-10);
 assert.equal(state.lastUsage,null);assert.equal(access.getSessionLastUsage(),null);
}
'''


def run_node(body):
    result=subprocess.run(['node','-'],input=SETUP+body,cwd=ROOT,text=True,encoding='utf-8',capture_output=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('entry',['new','project','clear'])
def test_new_and_clear_restore_empty_usage_without_losing_old_or_late_usage(entry):
    run_node('const entry='+json.dumps(entry)+r''';
(async()=>{
 if(entry==='clear')context.clearCurrentSession();else navigation.beginNewConversation(entry==='project'?'project-a':null);
 assert.equal(state.sessionId,null);assertEmptyDisplay();
 assert.equal(state.pendingProjectId,entry==='project'?'project-a':null);
 assert.strictEqual(access.getSessionLastUsage('old'),oldUsage);
 assert.strictEqual(access.getSessionStats('old'),oldStats);
 assert.strictEqual(access.getSessionMessages('old'),oldMessages);
 assert.equal(saved.length,1);assert.equal(saved[0][0],'old');assert.strictEqual(saved[0][2],oldStats);
 const lateUsage={prompt_tokens:750,completion_tokens:300};
 const lateStats={input:1400,output:300,cache:700,cost:4,cacheReported:true};
 // A late result is routed through the actual session-keyed accessors.
 access.setSessionLastUsage('old',lateUsage);access.setSessionStats('old',lateStats);
 assertEmptyDisplay();assert.strictEqual(access.getSessionLastUsage('old'),lateUsage);
 await navigation.createSession('fresh task');assert.equal(state.sessionId,'fresh');assertEmptyDisplay();
 await navigation.loadSession('old',{userInitiated:false});
 const restored=panels.updateStatsPanel();
 assert.strictEqual(state.lastUsage,lateUsage);assert.strictEqual(state.stats,lateStats);
 assert.equal(restored.contextTokens,750);assert.equal(restored.cacheHit,0.5);
 assert.equal(elements.statContext.textContent,'75%');assert.equal(elements.statCacheHit.textContent,'50%');
 assert.strictEqual(state.messages,oldMessages);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_no_session_accessor_ignores_stale_mirror_but_retains_session_cache():
    run_node(r'''
state.sessionId=null;state.messages=[];state.stats={input:0,output:0,cache:0};
assert.strictEqual(state.lastUsage,oldUsage);
const stats=panels.updateStatsPanel();
assert.equal(stats.contextTokens,'system prompt'.length);
assert.equal(access.getSessionLastUsage(null),null);
assert.strictEqual(access.getSessionLastUsage('old'),oldUsage);
''')
