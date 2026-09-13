import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = r'''
global.window={Code:{ui:{},agent:{}}};
require('./src/agent/model-request.js');
require('./src/ui/diff.js');require('./src/ui/messages.js');
const assert=require('node:assert/strict');
const escapeHtml=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const common={escapeHtml,renderMarkdown:escapeHtml,renderAssistantContent:escapeHtml,t:k=>k,
 getMessageText:m=>String(m?.content||''),getSelectedModel:()=>'',getSessionId:()=> 'fixture',getToolActionLabel:a=>a};
const diff=window.Code.ui.diff.createDiffFeature(common);
const ui=window.Code.ui.messages.createMessagesFeature({...common,isEditSuggestionMessage:window.Code.ui.diff.isEditSuggestionMessage,
 renderEditSuggestion:(m,i)=>diff.renderEditSuggestionProjection(m,i)});
const call=(id,run='run-a')=>({role:'tool-call',content:'',meta:{action:'write_file',toolCallId:id,agentRunId:run,tool:{action:'write_file',path:id+'.txt'}}});
const result=(id,run='run-a',outcome='succeeded')=>({role:'tool-result',content:'```diff\n+synthetic\n```',meta:{
 action:'write_file',toolCallId:id,agentRunId:run,pendingEditId:'edit-'+run+'-'+id,outcome,
 applied:outcome==='succeeded',proposalOnly:outcome==='pending',result:{ok:outcome!=='failed',cancelled:outcome==='cancelled',path:id+'.txt'}}});
const assistant=(ids,run='run-a')=>({role:'assistant',content:'Two approved writes.',meta:{agentRunId:run,
 toolCalls:ids.map(id=>({id,type:'function',function:{name:'write_file',arguments:JSON.stringify({path:id+'.txt',content:'synthetic'})}}))}});
const project=rows=>ui.projectMessages([{role:'user',content:'synthetic task'},...rows],{hasActiveRun:false,runState:{}});
const items=html=>[...html.matchAll(/<details class="tool-process-item ([^"]+)" data-tool-call-id="([^"]+)" data-agent-run-id="([^"]*)"/g)].map(m=>({outcome:m[1],id:m[2],run:m[3]}));
'''


def node(body):
    r = subprocess.run(['node', '-'], input=SETUP + body, cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_two_real_edit_cards_do_not_duplicate_the_second_execution():
    node(r'''
const rows=[assistant(['first','second']),call('first'),result('first'),call('second'),result('second')];
const before=JSON.stringify(rows);
for(const source of [rows,JSON.parse(before)]) {
 const rendered=items(project(source));
 assert.deepEqual(rendered,[{outcome:'succeeded',id:'first',run:'run-a'},{outcome:'succeeded',id:'second',run:'run-a'}]);
}
assert.equal(JSON.stringify(rows),before);
''')


def test_terminal_result_precedes_duplicates_but_never_another_run_or_real_pending():
    node(r'''
for(const terminal of ['succeeded','failed','cancelled']) {
 const rows=[assistant(['same']),call('same'),result('same','run-a','pending'),{role:'assistant',content:'boundary'},
  call('same'),result('same','run-a',terminal),result('same','run-a','pending'),
  assistant(['same'],'run-b'),call('same','run-b')];
 const rendered=items(project(rows));
 assert.deepEqual(rendered,[{outcome:terminal,id:'same',run:'run-a'},{outcome:'running',id:'same',run:'run-b'}]);
}
assert.deepEqual(items(project([assistant(['pending']),call('pending'),result('pending','run-a','pending')])),[{outcome:'pending',id:'pending',run:'run-a'}]);
''')


def test_internal_goal_read_and_blank_history_are_hidden_but_wait_explanation_remains():
    node(r'''
const internal={role:'assistant',content:'→ goal_read',meta:{agentRunId:'run-a',toolCalls:[{id:'g',function:{name:'goal_read',arguments:'{}'}}]}};
const rows=[internal,{role:'tool-call',content:'control',meta:{action:'goal_read',toolCallId:'g',agentRunId:'run-a'}},
 {role:'tool-result',content:'private control payload',meta:{action:'goal_read',toolCallId:'g',agentRunId:'run-a',result:{ok:true}}},
 {role:'assistant',content:' ',meta:{agentRunId:'run-a'}},
 {...internal,content:'Please provide the remaining required input.',meta:{...internal.meta,publicProcessCommentary:true}},
 {role:'assistant',content:'The requested explanation remains visible.'}];
const html=project(rows);
assert.ok(!html.includes('goal_read'));assert.ok(!html.includes('private control payload'));
assert.ok(html.includes('Please provide the remaining required input.'));assert.ok(html.includes('The requested explanation remains visible.'));
assert.equal(items(html).length,0);
assert.equal(ui.renderFinalAssistantProjection(rows[3],3),'');
''')


def test_bare_markup_after_progress_is_readable_failure_but_quotes_stay_text():
    node(r'''
const block='<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="goal_read"></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>';
const progress='The isolated comparison finished.\n\n';
const modelRequest=window.Code.agent.modelRequest;
const rows=[{role:'assistant',content:progress+block,meta:{agentRunId:'run-a'}}];
const snapshot=JSON.stringify(rows),html=project(rows);
assert.ok(html.includes('The isolated comparison finished.'));assert.ok(html.includes('toolMarkupNotExecuted'));
assert.ok(!html.includes('DSML'));assert.equal(modelRequest.mapMessageForApi(rows[0]),null);assert.equal(JSON.stringify(rows),snapshot);
for(const text of ['```xml\n'+block+'\n```','> '+block,'    '+block,'The token '+block+' is a quoted example.']) {
 assert.equal(modelRequest.isUnexecutedToolMarkup(text),false);
 assert.equal(modelRequest.mapMessageForApi({role:'assistant',content:text}).content,text);
 assert.ok(project([{role:'assistant',content:text}]).includes('DSML'));
}
assert.equal(modelRequest.mapMessageForApi({role:'user',content:progress+block}).content,progress+block);
''')


def test_incremental_projection_and_runless_legacy_turns_remain_distinct():
    node(r'''
const rows=[assistant(['first','second']),call('first'),result('first'),call('second'),result('second')];
for(let n=1;n<=rows.length;n++) {
 const snapshot=rows.slice(0,n),before=JSON.stringify(snapshot);
 const html=ui.projectMessages([{role:'user',content:'task'},...snapshot],{hasActiveRun:true,runState:{runId:'run-a',status:'tools'}});
 const actual=items(html);
 assert.equal(actual.filter(x=>x.id==='second').length,1);
 assert.equal(actual.find(x=>x.id==='second').outcome,n===rows.length?'succeeded':n<4?'pending':'running');
 assert.equal(JSON.stringify(snapshot),before);
}
const legacy=[call('shared',''),result('shared',''),{role:'user',content:'a later task'},call('shared','')];
assert.deepEqual(items(project(legacy)).map(x=>[x.id,x.outcome]),[['shared','succeeded'],['shared','running']]);
''')


def test_live_model_completed_diagnostic_cannot_reenter_native_history():
    node(r'''
{
const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('function projectAgentModelCompleted('),end=source.indexOf('function findAgentCompactionProjection(',start);
const assistant={role:'assistant',content:'unexecuted streamed body',streaming:true,meta:{protocolRef:{id:'invalid'},protocolContent:'invalid',toolCalls:[{id:'invalid'}]}};
const ctx={messages:[assistant],run:{},sessionId:'s'};
const context={findAgentAssistantByRuntime:()=>assistant,markModelResponseStarted:()=>{},
 isInternalGoalToolName:()=>false,agentEventMeta:()=>({}),setSessionLastUsage:()=>{},updateUsage:()=>{},
 toolProgressSummary:()=>'',getSelectedModel:()=>'',Date,t:k=>k};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
context.projectAgentModelCompleted(ctx,{data:{runtimeRunId:'r',outcome:'tool_protocol_error',content:'Valid progress.',toolCalls:[],usage:{}}});
assert.equal(assistant.content,'Valid progress.\n\ntoolMarkupNotExecuted');assert.equal(assistant.meta.skipApi,true);
assert.equal(assistant.meta.toolCalls.length,0);assert.equal(assistant.meta.protocolRef,undefined);
assert.equal(assistant.meta.protocolContent,undefined);assert.equal(assistant.meta.protocolDisplayContent,undefined);
assert.equal(window.Code.agent.modelRequest.mapMessageForApi(assistant),null);
}
''')
