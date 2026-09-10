const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),app=fs.readFileSync(path.join(root,'app.js'),'utf8');
function runtime(){
 const sandbox={Code:{agent:{},core:{}},console,structuredClone};sandbox.window=sandbox;
 vm.createContext(sandbox);
 for(const name of ['system-prompt','subagents','model-request'])vm.runInContext(fs.readFileSync(path.join(root,`src/agent/${name}.js`),'utf8'),sandbox);
 return sandbox;
}
const plain=x=>JSON.parse(JSON.stringify(x));
function extract(s,name,next){vm.runInContext(app.slice(app.indexOf(`function ${name}(`),app.indexOf(`function ${next}(`)),s);}
test('nine preferences preserve sampling, tools and complete task contract; default prompt bytes unchanged',()=>{
 const s=runtime(),p=s.Code.agent.systemPrompt,r=s.Code.agent.modelRequest;
 const base={securityLayer:'SAFETY',behaviorInstruction:'ENGINEERING',permissionInstruction:'PERMISSIONS'};
 const original=p.createSystemPromptSnapshot(base).prompt;
 assert.equal(original,'SAFETY\n\nENGINEERING\n\nPERMISSIONS');
 const tools=[{type:'function',function:{name:'read_file',parameters:{type:'object',properties:{path:{type:'string'}}}}}];
 for(const detail of p.RESPONSE_DETAILS)for(const tone of p.RESPONSE_TONES){
  const style=p.createResponseStyleSnapshot({detail,tone});
  assert.deepEqual(plain(p.restoreResponseStyleSnapshot(plain(style))),plain(style));
  const prompt=p.createSystemPromptSnapshot({...base,responseStyleInstruction:style.instruction}).prompt;
  if(detail==='default'&&tone==='default')assert.equal(prompt,original);
  else{assert(prompt.startsWith('SAFETY\n\nENGINEERING\n\n[Reply preferences]'));assert(prompt.endsWith('PERMISSIONS'));assert(style.instruction.includes('Keep the engineering work complete'));}
  const request=r.assembleModelRequestPayload({model:'fixture',systemPrompt:prompt,temperature:0,maxTokens:1234,tools,reasoningSelection:{}});
  assert.equal(request.temperature,0);assert.equal(request.max_tokens,1234);assert.deepEqual(plain(request.tools),tools);
  assert.equal(request.messages[0].content,prompt);assert(!('verbosity' in request));
 }
});
test('local preference failure preserves storage; only an explicit successful save updates it',()=>{
 const p=runtime().Code.agent.systemPrompt;let value=null;const storage={getItem:()=>value,setItem:(_,v)=>{value=v;}};
 assert.equal(p.readResponseStylePreference(storage).snapshot.instruction,'');
 for(const broken of ['{',JSON.stringify({version:9,detail:'concise',tone:'casual'}),JSON.stringify({version:1,detail:null,tone:'casual'})]){
  value=broken;assert.equal(p.readResponseStylePreference(storage).error,'responseStyleLoadFailed');assert.equal(value,broken);
 }
 p.saveResponseStylePreference(storage,{detail:'detailed',tone:'casual'});
 const saved=value;assert.equal(p.readResponseStylePreference(storage).snapshot.tone,'casual');
 assert.throws(()=>p.saveResponseStylePreference({setItem(){throw Error('quota');}},{detail:'concise',tone:'professional'}));assert.equal(value,saved);
});
test('missing legacy snapshot stays missing, malformed and unknown frozen data fail closed',()=>{
 const p=runtime().Code.agent.systemPrompt,good=plain(p.createResponseStyleSnapshot({detail:'concise',tone:'casual'}));
 assert.equal(p.restoreResponseStyleSnapshot(undefined),null);assert.equal(p.restoreResponseStyleSnapshot(null),null);
 for(const bad of [false,0,'',[],{}, {...good,version:99},{...good,instruction:'INJECT'}, {...good,extra:1},{...good,tone:'other'}])assert.throws(()=>p.restoreResponseStyleSnapshot(bad),e=>e.code==='response_style_snapshot_invalid');
});
test('queue and background checkpoints survive JSON/reload without reading current settings; child prompt remains separate',()=>{
 const s=runtime(),p=s.Code.agent.systemPrompt;
 s.restoreResponseStyleSnapshot=p.restoreResponseStyleSnapshot;s.normalizeImageRouteDispatch=()=>null;
 extract(s,'queuedMessageCheckpoint','findQueuedUserMessage');
 const style=plain(p.createResponseStyleSnapshot({detail:'detailed',tone:'casual'}));
 const queued=plain(s.queuedMessageCheckpoint({id:'q',temperature:0,responseStyle:style}));
 assert.deepEqual(queued.responseStyle,style);assert.equal(queued.temperature,0);
 const b=s.Code.agent.subagents;
 const checkpoint=plain(b.buildBackgroundJobCheckpoint({id:'b',responseStyle:style,temperature:0},1));
 assert.deepEqual(plain(b.buildRestoredBackgroundJobData(checkpoint)).responseStyle,style);
 const child=b.createSubAgentContext({parentContext:{responseStyle:style,cwd:'synthetic'},taskPrompt:'inspect'});
 assert(!child.messages[0].content.includes('[Reply preferences]'));
 const legacy=plain(s.queuedMessageCheckpoint({id:'old'}));assert(!('responseStyle' in legacy));
 assert(!('responseStyle' in plain(b.buildBackgroundJobCheckpoint({id:'old'}))));
 assert.throws(()=>s.queuedMessageCheckpoint({id:'bad',responseStyle:false}));
 assert.throws(()=>b.buildBackgroundJobCheckpoint({id:'bad',responseStyle:{version:9}}));
});
test('main prompt cache pins the original instruction across retries and setting changes',async()=>{
 const p=runtime().Code.agent.systemPrompt,owner={};let calls=0;
 const before=p.createResponseStyleSnapshot({detail:'concise',tone:'professional'});
 const captured=await p.getOrCreateSystemPromptSnapshot(owner,()=>{calls++;return p.createSystemPromptSnapshot({securityLayer:'SEC',responseStyleInstruction:before.instruction});});
 const retry=await p.getOrCreateSystemPromptSnapshot(owner,()=>{calls++;return p.createSystemPromptSnapshot({responseStyleInstruction:'wrong'});});
 assert.equal(retry,captured);assert.equal(calls,1);assert(!JSON.stringify(owner).includes('instruction'));
});
test('admitted v1 golden snapshots retain exact original text through queue and background restore',()=>{
 const s=runtime(),p=s.Code.agent.systemPrompt;
 s.restoreResponseStyleSnapshot=p.restoreResponseStyleSnapshot;s.normalizeImageRouteDispatch=()=>null;
 extract(s,'queuedMessageCheckpoint','findQueuedUserMessage');
 const legacy=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/response-style-v1.json'),'utf8'));
 for(const original of legacy){
  assert.deepEqual(plain(p.restoreResponseStyleSnapshot(original)),original);
  const queued=s.queuedMessageCheckpoint({id:'old',responseStyle:original});
  assert.deepEqual(plain(queued.responseStyle),original);
  assert.deepEqual(plain(s.Code.agent.subagents.buildRestoredBackgroundJobData({id:'old',responseStyle:original}).responseStyle),original);
  const early={...original,instruction:original.instruction.replace('Keep the usual cadence of progress reporting and action names.','Use the usual amount of progress reporting and action labels.')};
  assert.deepEqual(plain(p.restoreResponseStyleSnapshot(early)),early);
 }
 const next=p.createResponseStyleSnapshot({detail:'concise',tone:'default'});
 assert.equal(next.version,2);assert(next.instruction.includes('explicitly requests a detailed explanation'));
 assert(!next.instruction.includes('Expand when the user asks for an explanation.'));
});
