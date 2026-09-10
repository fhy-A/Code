const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const sandbox = {window: {Code: {agent: {modelRequest: {}}, ui: {}}}};
vm.createContext(sandbox);
for (const file of ['src/agent/tools.js', 'src/ui/messages.js']) vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox);
const api = sandbox.window.Code.agent.tools;
const snapshot = (extra = {}) => ({sessionId:'session', agentRunId:'run', status:'tools', permissionProfile:'accept', events:[], ...extra});
const call = (id, text, name='read_file') => ({id, function:{name, arguments:JSON.stringify({path:'.', _actionStatus:text})}});
const completed = (seq, calls, content='') => ({seq, type:'model_completed', data:{runtimeRunId:`model-${seq}`, toolCalls:calls, content}});
const start = (seq, id, type='tool_started', name='read_file') => ({seq,type,data:{toolCallId:id,name}});
function fresh() { const value=api.createActionStatusObserver('session','run',true);value.observe(snapshot());return value; }

test('optional schema and strict display validation, independent of execution arguments',()=>{
 for(const item of api.nativeTools){const schema=item.function.parameters;assert.equal('_actionStatus' in schema.properties,item.function.name!=='request_user_input');assert(!schema.required?.includes('_actionStatus'));}
 for(const bad of [null,{},[],0,'',' ','a\nb','a\tb','a\rb','x'.repeat(81),'\u202eabc','\ud800'])assert.equal(api.validActionStatus(bad),'');
 assert.equal(api.validActionStatus('🙂'.repeat(80)),'🙂'.repeat(80));
 assert.equal(api.validActionStatus('  <b>**plain**</b>  '),'<b>**plain**</b>');
 const raw=call('one','Checking context');const before=JSON.stringify(raw);
 assert(!('_actionStatus' in api.normalizeNativeToolCall(raw)));assert.equal(JSON.stringify(raw),before);
});
test('one stage retains through completion, failures, and empty model work; ordered starts replace',()=>{
 const o=fresh();o.event(completed(1,[call('a','Inspecting inputs'),call('b','Checking totals')]),snapshot());assert.equal(o.view(),'');
 o.event(start(2,'a'),snapshot());assert.equal(o.view(),'Inspecting inputs');
 o.event({seq:3,type:'tool_completed',data:{toolCallId:'a',result:{ok:false}}},snapshot());assert.equal(o.view(),'Inspecting inputs');
 o.event(start(4,'b'),snapshot());assert.equal(o.view(),'Checking totals');
 o.event({seq:5,type:'model_started',data:{runtimeRunId:'next'}},snapshot({status:'model'}));assert.equal(o.view(),'Checking totals');
 o.event(completed(6,[call('c',null)]),snapshot());o.event(start(7,'c'),snapshot());assert.equal(o.view(),'Checking totals');
 o.event(completed(8,[call('d','New stage')],'Now checking layout'),snapshot());assert.equal(o.view(),'');
 o.event(start(9,'d'),snapshot());assert.equal(o.view(),'New stage');
 o.boundary('old-runtime');assert.equal(o.view(),'New stage');o.boundary('model-8');assert.equal(o.view(),'');
});
test('default permissions and plan proposals; command waits for authoritative command_started',()=>{
 const o=fresh();o.event(completed(1,[call('c','Checking output','run_command')]),snapshot());
 o.event(start(2,'c'),snapshot());assert.equal(o.view(),'');o.event(start(3,'c','command_started'),snapshot());assert.equal(o.view(),'Checking output');
 for(const name of ['read_file','search_files','list_files','glob_files','web_fetch','use_skill','task']){
  const x=fresh();x.event(completed(1,[call('x','Inspecting context',name)]),snapshot());x.event(start(2,'x','tool_started',name),snapshot());assert.equal(x.view(),'Inspecting context',name);
 }
 for(const permissionProfile of ['accept','plan','bypass']){
  const x=fresh();x.event(completed(1,[call('p','Preparing changes','propose_edit')]),snapshot({permissionProfile}));x.event(start(2,'p','tool_started','propose_edit'),snapshot({permissionProfile}));assert.equal(Boolean(x.view()),permissionProfile!=='accept');
 }
 const x=fresh();x.event(completed(1,[call('w','Applying chosen changes','write_file')]),snapshot());
 x.event(start(2,'w','tool_started','write_file'),snapshot({toolExecutions:[{toolCallId:'w',authorizationDecision:'approved',status:'applying_file_mutation'}]}));assert.equal(x.view(),'Applying chosen changes');
});
for(const status of ['waiting_authorization','waiting_user_input','waiting_credentials','waiting_recovery','waiting_skill_evidence','completed','cancelled','failed'])test(`${status} clears all names; old calls never revive`,()=>{
 const o=fresh();o.event(completed(1,[call('a','Inspecting inputs'),call('b','Stale next')]),snapshot());o.event(start(2,'a'),snapshot());
 o.observe(snapshot({status}));assert.equal(o.view(),'');o.observe(snapshot());o.event(start(3,'b'),snapshot());assert.equal(o.view(),'');
 o.event(completed(4,[call('c','Fresh action')]),snapshot());o.event(start(5,'c'),snapshot());assert.equal(o.view(),['completed','cancelled','failed'].includes(status)?'':'Fresh action');
});
test('reload/reconnect/CAS reset consumes snapshot watermark, ignores replay and out-of-order',()=>{
 for(const initial of [false,true]){
  const o=api.createActionStatusObserver('session','run',initial);if(initial)o.reset();
  const replay=[completed(10,[call('old','Old name')]),start(11,'old')];o.observe(snapshot({events:replay}));
  for(const event of replay)o.event(event,snapshot());assert.equal(o.view(),'');
  o.event(completed(12,[call('new','Fresh name')]),snapshot());o.event(start(13,'new'),snapshot());assert.equal(o.view(),'Fresh name');
  o.event(completed(10,[call('old','Stale')],'old text'),snapshot());assert.equal(o.view(),'Fresh name');
  o.event(completed(14,[call('replayed','Result replay')]),snapshot());o.event({seq:15,type:'tool_completed',data:{toolCallId:'replayed',replayed:true}},snapshot());assert.equal(o.view(),'Fresh name');
  o.reset();o.event(completed(16,[call('stale','During reconnect')]),snapshot({events:[completed(16,[])]}));assert.equal(o.view(),'');
 }
});
test('foreign session/Run/Child and internal/interaction tools cannot name foreground',()=>{
 for(const extra of [{sessionId:'other'},{agentRunId:'child'}]){const o=fresh();o.event(completed(1,[call('x','Wrong owner')]),snapshot(extra));o.event(start(2,'x'),snapshot());assert.equal(o.view(),'');}
 for(const name of ['request_user_input','goal_set_plan','made_up']){const o=fresh();o.event(completed(1,[call('x','Not an action',name)]),snapshot());o.event(start(2,'x'),snapshot());assert.equal(o.view(),'');}
});
test('compaction and model recovery do not revive names',()=>{
 for(const type of ['context_compaction_started','context_compaction_completed','context_compaction_failed','model_recovery']){
  const o=fresh();o.event(completed(1,[call('a','Inspecting inputs'),call('b','Stale next')]),snapshot());o.event(start(2,'a'),snapshot());o.event({seq:3,type,data:{}},snapshot());o.event(start(4,'b'),snapshot());assert.equal(o.view(),'');
 }
});
test('unadvertised old-Run field, mismatched tool names and invalid sequence never display',()=>{
 const o=fresh();o.event(completed(1,[call('a','Unknown old field')]),snapshot());
 o.event({seq:2,type:'tool_started',data:{toolCallId:'a',name:'read_file',arguments:{path:'.',_actionStatus:'Unknown old field'}}},snapshot());assert.equal(o.view(),'');
 o.event(completed(3,[call('b','Wrong tool')]),snapshot());o.event(start(4,'b','tool_started','write_file'),snapshot());assert.equal(o.view(),'');
 o.event(completed(NaN,[call('bad','Invalid sequence')]),snapshot());o.event(start(5,'bad'),snapshot());assert.equal(o.view(),'');
});
test('real message projection renders escaped independent single footer only for active Run',()=>{
 const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
 const feature=sandbox.window.Code.ui.messages.createMessagesFeature({escapeHtml,getSessionId:()=> 'session'});
 const messages=[{role:'user',content:'Inspect'},{role:'assistant',content:'',meta:{agentRunId:'run',toolCalls:[call('a','Hidden parameter')]}},{role:'tool-call',meta:{agentRunId:'run',toolCallId:'a',action:'read_file',tool:{action:'read_file',path:'.'}}}];
 const before=JSON.stringify(messages), projection={hasActiveRun:true,runState:{agentRunId:'run',status:'running'},actionStatus:'<b>**Checking**</b>'};
 const html=feature.projectMessages(messages,projection);assert.equal((html.match(/data-action-status-run=/g)||[]).length,1);
 assert(html.includes('&lt;b&gt;**Checking**&lt;/b&gt;'));assert(html.lastIndexOf('data-action-status-run')>html.lastIndexOf('tool-process-stage'));
 const line=html.slice(html.indexOf('<div class="msg assistant action-status"'));assert(!/title=|button|tabindex|summary|chevron/.test(line));
 assert(!feature.projectMessages(messages,{...projection,hasActiveRun:false}).includes('data-action-status-run'));
 assert.equal(JSON.stringify(messages),before);assert(!html.includes('Hidden parameter'));
});
