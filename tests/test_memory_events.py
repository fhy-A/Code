"""Pure frontend cache invalidation and scope fencing; no service import."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_memory_completion_invalidation_and_session_fences():
    script = r'''
const assert=require('node:assert/strict');
global.window={Code:{features:{}}};require('./src/features/skills-memory.js');
const state={sessionId:'current',_foregroundNavigationSeq:1,memoryContext:{found:true,content:'deleted secret',count:2,project:'project-a'}};
const elements={projectRoot:{value:'project-a'}},panel={innerHTML:'',style:{}},requests=[];
const feature=window.Code.features.skillsMemory.createSkillsMemoryFeature({state,elements,
 document:{getElementById:()=>panel},t:(key,args)=>key+JSON.stringify(args||{}),
 apiJson:url=>new Promise(resolve=>requests.push({url,resolve}))});
const ctx={sessionId:'current',cwd:'project-a'}, event=action=>({type:'tool_completed',data:{name:action,result:{ok:true,memoryScope:'project:project-a',content:'untrusted event body'}}});
(async()=>{
 for(const action of ['save_memory','delete_memory','write_file','delete_file','propose_edit']){
  const pending=feature.refreshMemoryAfterToolCompleted(ctx,event(action),true);
  assert.equal(state.memoryContext.content,null);assert.equal(state.memoryContext.count,0);
  assert(!panel.innerHTML.includes('memoryContextCount'));
  const request=requests.at(-1);assert.equal(request.url,'/api/memory-context?project=project-a');
  request.resolve({found:true,content:'current source',count:1});assert(await pending);
  assert.equal(state.memoryContext.content,'current source');assert(panel.innerHTML.includes('memoryContextCount'));
 }
 const count=requests.length,before=JSON.stringify(state.memoryContext);
 for(const other of [{...ctx,sessionId:'old'},{...ctx,cwd:'project-b'},{...ctx,isDetachedBackground:true},{...ctx,isSubAgent:true}]){
  assert.equal(await feature.refreshMemoryAfterToolCompleted(other,event('save_memory'),true),false);
 }
 assert.equal(await feature.refreshMemoryAfterToolCompleted(ctx,event('save_memory'),false),false);
 assert.equal(await feature.refreshMemoryAfterToolCompleted(ctx,{type:'tool_completed',data:{result:{ok:true}}},true),false);
 const foreign=event('write_file');foreign.data.result.memoryScope='project:other';
 assert.equal(await feature.refreshMemoryAfterToolCompleted(ctx,foreign,true),false);
 assert.equal(requests.length,count);assert.equal(JSON.stringify(state.memoryContext),before);
 const first=feature.refreshMemoryAfterToolCompleted(ctx,event('save_memory'),true),firstRequest=requests.at(-1);
 const second=feature.refreshMemoryAfterToolCompleted(ctx,event('delete_memory'),true),secondRequest=requests.at(-1);
 secondRequest.resolve({found:false,content:null,count:0});await second;
 firstRequest.resolve({found:true,content:'old request',count:9});await first;
 assert.equal(state.memoryContext.content,null);assert.equal(state.memoryContext.count,0);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run(['node','-'], input=script, cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
