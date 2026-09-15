"""CODE-084: isolated source/index transactions and real Agent authorization.

Run with CODE_DATA_DIR set to a disposable root before importing server.
No test reads the user's memory, config, sessions, or index.
"""
import copy
import hashlib
import json
import os
import subprocess
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

if not os.environ.get('CODE_DATA_DIR'):
    raise RuntimeError('Set CODE_DATA_DIR to a disposable profile before memory tests')

import server as srv
from code_runtime.managed_memory import MemoryError, MemoryStore
import test_agent_runtime as runtime_fixture


@pytest.fixture
def isolated():
    runtime_fixture.TestDurableAgentRuntime.setUpClass()
    fixture = runtime_fixture.TestDurableAgentRuntime()
    fixture.setUp()
    forbidden = fixture.data_dir / 'forbidden-global-index.md'
    original_open = Path.open
    def guarded_open(path, *args, **kwargs):
        assert path != forbidden, 'Global MEMORY_INDEX_PATH was accessed'
        return original_open(path, *args, **kwargs)
    try:
        with mock.patch.object(srv, 'MEMORY_INDEX_PATH', forbidden), mock.patch.object(Path, 'open', guarded_open):
            yield fixture
    finally:
        fixture.tearDown()
        runtime_fixture.TestDurableAgentRuntime.tearDownClass()


def save(name='alpha', body='first fact'):
    return srv.execute_save_memory_tool({'name': name, 'description': 'description', 'body': body})


def remove(item, operation='delete-once'):
    return srv.delete_memory(item['name'], expected=item['revision'], expected_scope=item['scope'], operation=operation)


def test_save_replay_repairs_index_without_rewriting_body(isolated):
    first = save()
    path = srv.MEMORY_DIR / 'alpha.md'
    original = path.read_bytes(), path.stat().st_mtime_ns
    (srv.MEMORY_DIR / 'MEMORY.md').write_text('stale', encoding='utf-8')
    assert save()['replayed'] is True
    assert original == (path.read_bytes(), path.stat().st_mtime_ns)
    assert 'alpha.md' in (srv.MEMORY_DIR / 'MEMORY.md').read_text(encoding='utf-8')
    assert first['scope'] == 'project:' + str(isolated.project_dir)


def test_old_bom_frontmatter_and_unknown_metadata_survive_replay(isolated):
    srv.MEMORY_DIR.mkdir(parents=True)
    raw=('\ufeff---\r\nproject: '+str(isolated.project_dir)+'\r\ndescription: description\r\nunknown: keep\r\n---\r\n\r\nfirst fact\r\n').encode('utf-8')
    path=srv.MEMORY_DIR/'alpha.md';path.write_bytes(raw)
    before=path.stat().st_mtime_ns
    assert save()['replayed']
    assert path.read_bytes()==raw and path.stat().st_mtime_ns==before
    assert srv.read_memory('alpha')['meta']['unknown']=='keep'


def test_delete_confirmation_cas_recreation_and_replay(isolated):
    save(); original = srv.read_memory('alpha')
    with pytest.raises(MemoryError, match='confirm'): srv.delete_memory('alpha')
    save(body='changed')
    with pytest.raises(MemoryError) as error: remove(original)
    assert error.value.code == 'memory_conflict'
    latest = srv.read_memory('alpha'); assert remove(latest)['applied']
    assert not srv.load_memory_context(str(isolated.project_dir))['found']
    save(body='recreated')
    replay = remove(latest)
    assert replay['replayed'] is True and replay['ok'] is False and replay['applied'] is False
    assert replay['errorCode'] == 'memory_target_changed'
    assert srv.read_memory('alpha')['body'].strip() == 'recreated'
    with pytest.raises(MemoryError): remove(latest, operation='new-delete')


def test_atomic_rename_preserves_metadata_and_collision(isolated):
    srv.write_memory('alpha', {'project': '*', 'created': 'old', 'custom': 'keep'}, 'old body')
    original = srv.read_memory('alpha')
    result = srv.write_memory('beta', {'description': 'new'}, 'new body', original_name='alpha',
                              expected=original['revision'], expected_scope='global', operation='rename')
    assert result['meta']['custom'] == 'keep' and result['meta']['created'] == 'old'
    assert result['scope'] == 'global'
    assert not (srv.MEMORY_DIR / 'alpha.md').exists()
    srv.write_memory('alpha', {}, 'collision')
    collision_raw = srv.read_memory('alpha')['raw']
    with pytest.raises(MemoryError) as error:
        srv.write_memory('alpha', {}, 'changed', original_name='beta', expected=result['revision'])
    assert error.value.code == 'memory_name_conflict'
    assert srv.read_memory('alpha')['raw'] == collision_raw


@pytest.mark.parametrize('crash', [False, True])
def test_failure_and_restart_recovery_keep_source_and_index(isolated, monkeypatch, crash):
    save(); store=srv._memory_store(); original=store.read('alpha')
    original_atomic=MemoryStore._atomic
    class SimulatedCrash(BaseException): pass
    fired=[]
    def fail_index(self,path,raw):
        if path == self.index and b'beta' in raw and not fired:
            fired.append(True)
            raise SimulatedCrash() if crash else OSError('injected index failure')
        return original_atomic(self,path,raw)
    with monkeypatch.context() as patch:
        patch.setattr(MemoryStore,'_atomic',fail_index)
        with pytest.raises(SimulatedCrash if crash else MemoryError):
            store.mutate('rename','alpha',new_name='beta',raw=original['raw'].encode(), expected=original['revision'], operation='rename-fail')
    assert [item['name'] for item in srv._memory_store().list()] == ['alpha']
    assert srv.read_memory('alpha')['raw'] == original['raw']
    assert 'beta' not in (srv.MEMORY_DIR/'MEMORY.md').read_text(encoding='utf-8')
    assert not store.journal.exists()


def test_legacy_frontmatter_visibility_and_concurrent_saves(isolated):
    srv.write_memory('legacy', {}, 'legacy fact')
    srv.write_memory('global', {'project':'*','unknown':'preserved'}, 'global fact')
    srv.write_memory('other', {'project':'other-root'}, 'other fact')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i:save('entry'+str(i),str(i)),range(8)))
    context=srv.load_memory_context(str(isolated.project_dir))
    assert context['count']==10 and 'other fact' not in context['content']
    assert srv.load_memory_context('')['count']==11
    assert len((srv.MEMORY_DIR/'MEMORY.md').read_text(encoding='utf-8').splitlines())==11
    with pytest.raises(MemoryError): save('other')


@pytest.mark.parametrize('name',['MEMORY','memory','../escape','a/b','CON','x.md'])
def test_reserved_and_escaping_names_rejected(isolated,name):
    with pytest.raises(MemoryError): srv.write_memory(name,{},'no')


def test_file_tools_join_store_and_refuse_forged_delete(isolated):
    save(); item=srv.read_memory('alpha'); path=str(srv.MEMORY_DIR/'alpha.md')
    result=srv.execute_write_file_tool({'path':path,'content':item['raw'].replace('first fact','file edit')})
    assert result['memoryScope']==item['scope']
    assert result['ok'] and 'file edit' in srv.load_memory_context(str(isolated.project_dir))['content']
    with pytest.raises(MemoryError): srv.execute_delete_file_tool({'path':path,'confirmed':True})
    with pytest.raises(MemoryError): srv.execute_delete_memory_tool({'name':'alpha','scope':item['scope'],'confirmed':True})
    for path in [srv.MEMORY_DIR/'MEMORY.md',srv.MEMORY_DIR/'.memory-transaction.json']:
        with pytest.raises(MemoryError): srv.execute_write_file_tool({'path':str(path),'content':'bad'})


def test_memory_edit_proposal_keeps_resolved_target_and_repairs_replay_index(isolated):
    save(); path=srv.MEMORY_DIR/'alpha.md'; original=srv.read_memory('alpha')
    proposal=srv.execute_propose_edit_tool({'path':str(path),'newContent':original['raw'].replace('first fact','proposal fact')})
    result=srv.execute_apply_edit_proposal(proposal)
    assert result['memoryScope']==original['scope']
    assert result['ok'] and srv.read_memory('alpha')['body']=='proposal fact'
    before=path.stat().st_mtime_ns
    (srv.MEMORY_DIR/'MEMORY.md').write_text('stale',encoding='utf-8')
    replay=srv.execute_apply_edit_proposal(proposal)
    assert replay['replayed'] and replay['memoryScope']==original['scope']
    assert path.stat().st_mtime_ns==before and 'alpha.md' in (srv.MEMORY_DIR/'MEMORY.md').read_text(encoding='utf-8')


def test_recovery_refuses_external_replacement(isolated,monkeypatch):
    save(); original=srv.read_memory('alpha'); atomic=MemoryStore._atomic
    class Crash(BaseException): pass
    def interrupted(self,path,raw):
        if path==self.index and b'beta' in raw: raise Crash()
        return atomic(self,path,raw)
    with monkeypatch.context() as patch:
        patch.setattr(MemoryStore,'_atomic',interrupted)
        with pytest.raises(Crash):
            srv._memory_store().mutate('rename','alpha',new_name='beta',raw=original['raw'].encode(),expected=original['revision'])
    external=b'external replacement'
    (srv.MEMORY_DIR/'alpha.md').write_bytes(external)
    with pytest.raises(MemoryError) as error: srv.list_memories()
    assert error.value.code=='memory_recovery_conflict'
    assert (srv.MEMORY_DIR/'alpha.md').read_bytes()==external
    assert srv._memory_store().journal.exists()


def test_hardlink_rejected_before_index_or_source_write(isolated):
    save(); outside=isolated.data_dir/'outside.md'; outside.write_text('protected',encoding='utf-8')
    (srv.MEMORY_DIR/'linked.md').hardlink_to(outside)
    with pytest.raises(MemoryError): srv.execute_write_file_tool({'path':str(srv.MEMORY_DIR/'linked.md'),'content':'bad'})
    assert outside.read_text(encoding='utf-8')=='protected'


def new_run(isolated, tool='delete_memory', profile='bypass', memory_version=1, system='system'):
    return srv._create_agent_run('memory-session', {'model':'fixture-model', 'messages':[
        {'role':'system','content':system}, {'role':'user','content':'fixture task'}],
        'tools':[srv._SERVER_TOOL_DEFINITIONS[tool]]}, isolated.base_url,['fixture-key'],
        [tool],permission_profile=profile,start_worker=False,cwd=str(isolated.project_dir),
        memory_context_version=memory_version, run_kind='foreground', client_request_id=uuid.uuid4().hex)


@pytest.mark.parametrize('tool',['delete_memory','delete_file'])
@pytest.mark.parametrize('profile',['accept','bypass'])
def test_controller_requires_real_approval_and_survives_restore(isolated,tool,profile):
    save(); item=srv.read_memory('alpha'); run=new_run(isolated,tool,profile)
    args={'name':'alpha','scope':item['scope']} if tool=='delete_memory' else {'path':str(srv.MEMORY_DIR/'alpha.md')}
    call={'id':'delete-call','function':{'name':tool,'arguments':json.dumps(args)},'arguments':args,
          'fingerprint':hashlib.sha256((tool+'\0'+json.dumps(args)).encode()).hexdigest()}
    run['messages'].append({'role':'assistant','content':None,'tool_calls':[{'id':call['id'],'type':'function','function':call['function']}]})
    run['pending_tool_calls']=[call];run['status']='tools'
    assert srv._execute_agent_pending_tools(run) is False
    assert run['status']=='waiting_authorization' and srv.read_memory('alpha')
    pending=run['pending_authorization']; assert pending['memoryTarget']['revision']==item['revision']
    pending_restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert pending_restored['pending_authorization']['memoryTarget'] == pending['memoryTarget']
    with pytest.raises(MemoryError): srv._submit_agent_authorization(run, '', 'approved')
    srv._submit_agent_authorization(run,pending['authorizationId'],'approved')
    assert run['tool_executions']['delete-call']['memoryTarget']==pending['memoryTarget']
    # Persisted execution contract remains bound to the exact approved version.
    record=srv._agent_run_record(run)
    restored=srv._agent_run_from_record(record)
    restored['status']='tools'
    assert srv._execute_agent_pending_tools(restored) is True
    completed=next(event for event in reversed(restored['events']) if event['type']=='tool_completed')
    assert completed['data']['result']['memoryScope']==item['scope']
    assert not (srv.MEMORY_DIR/'alpha.md').exists()
    assert not hasattr(srv._agent_workspace_context,'memory_authorization')


def test_changed_after_approval_is_not_deleted(isolated):
    save(); item=srv.read_memory('alpha'); run=new_run(isolated)
    args={'name':'alpha','scope':item['scope']}
    call={'id':'delete-changed','function':{'name':'delete_memory','arguments':json.dumps(args)},
          'arguments':args,'fingerprint':'frozen-call'}
    run['messages'].append({'role':'assistant','content':None,'tool_calls':[{'id':call['id'],'type':'function','function':call['function']}]})
    run['pending_tool_calls']=[call];run['status']='tools'
    assert not srv._execute_agent_pending_tools(run)
    pending=run['pending_authorization']
    srv._submit_agent_authorization(run,pending['authorizationId'],'approved')
    save(body='changed after confirmation')
    run['status']='tools';srv._execute_agent_pending_tools(run)
    result=run['tool_executions']['delete-changed']['result']
    assert result['ok'] is False and result['errorCode']=='memory_conflict'
    assert srv.read_memory('alpha')['body']=='changed after confirmation'


@pytest.mark.parametrize('kind',['background','child'])
def test_delete_not_available_without_interactive_owner(isolated,kind):
    save(); item=srv.read_memory('alpha'); run=new_run(isolated);run['run_kind']=kind
    with pytest.raises(MemoryError):
        srv._memory_delete_preview(run,{'function':{'name':'delete_memory'},'arguments':{'name':'alpha','scope':item['scope']}})
    # The memory rule does not alter ordinary child file authorization.
    assert srv._memory_delete_preview(run,{'function':{'name':'delete_file'},'arguments':{'path':str(isolated.project_dir/'README.md')}}) is None


def test_save_receipt_survives_retry_and_detects_later_edit(isolated):
    args={'name':'alpha','description':'stable','body':'saved','_operationId':'stable-save'}
    assert srv.execute_save_memory_tool(args)['ok']
    assert srv.execute_save_memory_tool(args)['replayed']
    save(body='user edit')
    result=srv.execute_save_memory_tool(args)
    assert result['ok'] is False and result['errorCode']=='memory_target_changed'
    assert srv.read_memory('alpha')['body']=='user edit'


def test_creation_cas_does_not_overwrite_concurrent_new_target(isolated):
    save(); store=srv._memory_store()
    with pytest.raises(MemoryError): store.mutate('write','alpha',raw=b'bad',expected='')
    assert srv.read_memory('alpha')['body']=='first fact'


def test_source_symlink_escape_is_rejected(isolated):
    save(); outside=isolated.data_dir/'outside.md';outside.write_text('protected',encoding='utf-8')
    try: (srv.MEMORY_DIR/'escape.md').symlink_to(outside)
    except OSError as exc: pytest.skip(f'Host does not permit symlink creation: {exc.winerror}')
    with pytest.raises(MemoryError): srv.execute_write_file_tool({'path':str(srv.MEMORY_DIR/'escape.md'),'content':'bad'})
    assert outside.read_text(encoding='utf-8')=='protected'


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction boundary')
def test_junction_escape_is_rejected(isolated):
    srv.MEMORY_DIR.mkdir(parents=True)
    outside=isolated.data_dir/'outside';outside.mkdir()
    target=outside/'target.md';target.write_text('protected',encoding='utf-8')
    junction=srv.MEMORY_DIR/'linked'
    created=subprocess.run(['cmd','/d','/c','mklink','/J',str(junction),str(outside)],capture_output=True)
    assert created.returncode == 0, created.stderr
    try:
        assert junction.is_junction() and junction.resolve()==outside.resolve()
        with pytest.raises(MemoryError): srv.execute_write_file_tool({'path':str(junction/'target.md'),'content':'bad'})
        assert target.read_text(encoding='utf-8')=='protected'
    finally:
        assert junction.parent.resolve()==srv.MEMORY_DIR.resolve()
        os.rmdir(junction)  # Remove only the verified owned junction, never its target.


def test_management_http_conflicts_and_rename_replay(isolated):
    host=ThreadingHTTPServer(('127.0.0.1',0),srv.CodeHandler)
    worker=threading.Thread(target=host.serve_forever,daemon=True);worker.start()
    base='http://127.0.0.1:'+str(host.server_address[1])
    import requests
    try:
        response=requests.post(base+'/api/memory',json={'name':'http-memory','meta':{'project':'*','custom':'keep'},'body':'old'},timeout=3)
        assert response.status_code==201
        item=response.json()
        denied=requests.delete(base+'/api/memory',params={'file':item['name']},timeout=3)
        assert denied.status_code==409 and denied.json()['errorCode']=='memory_confirmation_required'
        update={'name':'http-renamed','originalName':item['name'],'revision':item['revision'],
                'scope':item['scope'],'meta':item['meta'],'body':'new','operationId':'http-rename'}
        result=requests.post(base+'/api/memory',json=update,timeout=3)
        assert result.status_code==201 and result.json()['meta']['custom']=='keep'
        replay=requests.post(base+'/api/memory',json=update,timeout=3)
        assert replay.status_code==201 and replay.json()['replayed']
        stale=requests.delete(base+'/api/memory',params={'file':'http-renamed','revision':item['revision'],'scope':item['scope']},timeout=3)
        assert stale.status_code==409 and stale.json()['errorCode']=='memory_conflict'
        assert requests.get(base+'/api/memory-context',params={'project':''},timeout=3).json()['found']
    finally:
        host.shutdown();host.server_close();worker.join(timeout=3)
        assert not worker.is_alive()


def test_actual_model_tool_model_chain_reloads_memory(isolated):
    save(); run=new_run(isolated,tool='save_memory')
    args={'name':'alpha','description':'description','body':'next request fact'}
    fixture=runtime_fixture._AgentUpstream
    fixture.scripted_rounds=[[
        {'choices':[{'delta':{'tool_calls':[{'index':0,'id':'save-new','type':'function',
            'function':{'name':'save_memory','arguments':json.dumps(args)}}]},'finish_reason':'tool_calls'}]},
    ],[{'choices':[{'delta':{'content':'fixture completed'},'finish_reason':'stop'}]}]]
    srv._agent_run_worker(run)
    assert run['status']=='completed'
    assert len(fixture.payloads)==2
    assert 'first fact' in json.dumps(fixture.payloads[0])
    assert 'next request fact' in json.dumps(fixture.payloads[1])
    assert 'first fact' not in json.dumps(fixture.payloads[1])
    assert 'Current persistent memory' not in json.dumps(run['messages'])
    completed=next(event for event in run['events'] if event['type']=='tool_completed')
    assert completed['data']['result']['memoryScope']=='project:'+str(isolated.project_dir)


def test_visible_targets_supply_scope_without_guessing(isolated):
    save()
    srv.write_memory('shared',{'project':'*'},'shared')
    srv.write_memory('old',{'description':'legacy'},'old')
    srv.write_memory('hidden',{'project':'another-project'},'not visible')
    context=srv.load_memory_context(str(isolated.project_dir))
    assert {item['name'] for item in context['targets']}=={'alpha','shared','old'}
    run=new_run(isolated)
    for target in context['targets']:
        assert json.dumps(target,ensure_ascii=False) in context['content']
        preview=srv._memory_delete_preview(run,{'function':{'name':'delete_memory'},'arguments':target})
        assert preview['name']==target['name'] and preview['scope']==target['scope']
    assert 'another-project' not in context['content'] and 'hidden' not in context['content']


def test_legacy_producer_reload_then_new_foreground_run(isolated):
    legacy='=== 长期记忆（跨会话保留） ===\nold inline memory'
    old=new_run(isolated,memory_version=None,system=legacy)
    history=copy.deepcopy(old['messages'])
    srv._agent_run_worker(old)
    assert old['status']=='waiting_recovery' and 'reload the page' in old['error']
    # Another send from the still-old producer must not evade the gate.
    again=new_run(isolated,memory_version=None,system=legacy)
    with mock.patch.object(srv,'_create_model_runtime_run') as outbound:
        srv._agent_run_worker(again)
    outbound.assert_not_called()
    assert again['status']=='waiting_recovery'
    fresh=new_run(isolated)
    runtime_fixture._AgentUpstream.scripted_rounds=[[{'choices':[{'delta':{'content':'fresh frontend continued'},'finish_reason':'stop'}]}]]
    srv._agent_run_worker(fresh)
    assert fresh['session_id']==old['session_id'] and fresh['status']=='completed'
    assert old['status']=='waiting_recovery' and old['messages']==history


def test_request_memory_is_fresh_and_never_rewrites_history(isolated):
    save(); run=new_run(isolated); history=copy.deepcopy(run['messages'])
    first,_=srv._agent_model_payload(run)
    save(body='latest fact');second,_=srv._agent_model_payload(run)
    assert 'first fact' in json.dumps(first,ensure_ascii=False)
    assert 'latest fact' in json.dumps(second,ensure_ascii=False) and 'first fact' not in json.dumps(second)
    remove(srv.read_memory('alpha'));third,_=srv._agent_model_payload(run)
    assert 'Current persistent memory' not in json.dumps(third)
    assert run['messages']==history and 'first fact' in json.dumps(first)


def test_legacy_run_pauses_without_outbound_and_new_turn_works(isolated):
    legacy='system\n=== 长期记忆（跨会话保留） ===\nold fact\nother instructions'
    run=new_run(isolated,memory_version=None,system=legacy);history=copy.deepcopy(run['messages'])
    with mock.patch.object(srv,'_create_model_runtime_run') as outbound:
        srv._agent_run_worker(run)
    outbound.assert_not_called()
    assert run['status']=='waiting_recovery' and run['messages']==history
    restored=srv._agent_run_from_record(srv._agent_run_record(run))
    assert restored['recovery_state']['resumable'] is False
    with pytest.raises(MemoryError): srv._resume_agent_run(restored,['fixture-key'])
    fresh=new_run(isolated)
    assert fresh['run_kind']=='foreground' and fresh['id']!=run['id']
    assert fresh['session_id']==run['session_id'] and srv._agent_memory_send_gate(fresh)
    plain_legacy=new_run(isolated,memory_version=None)
    assert srv._agent_memory_send_gate(plain_legacy)
    # The versioned producer owns segmentation. Quoted legacy markers in a
    # new system/project instruction are not inferred to be old memory.
    modern=new_run(isolated,system='Discuss the marker === 长期记忆（跨会话保留） === as text')
    assert srv._agent_memory_send_gate(modern)


def test_legacy_gate_does_not_repeat_completed_tools(isolated):
    run=new_run(isolated,tool='save_memory',memory_version=None,system='=== 长期记忆（跨会话保留） ===\nold fact')
    args={'name':'alpha','description':'done','body':'already saved'}
    function={'name':'save_memory','arguments':json.dumps(args)}
    result={'ok':True,'action':'save_memory','name':'alpha'}
    run['messages'] += [{'role':'assistant','content':None,'tool_calls':[{'id':'done-call','type':'function','function':function}]},
                        {'role':'tool','tool_call_id':'done-call','content':json.dumps(result)}]
    run['pending_tool_calls']=[{'id':'done-call','function':function,'arguments':args,'fingerprint':'completed-call'}]
    run['tool_executions']={'done-call':{'name':'save_memory','arguments':args,'fingerprint':'completed-call',
        'status':'completed','result':result,'outcome':'succeeded'}}
    run['status']='tools';history=copy.deepcopy(run['messages'])
    with mock.patch.object(srv,'execute_registered_tool') as tool, mock.patch.object(srv,'_create_model_runtime_run') as outbound:
        srv._agent_run_worker(run)
    tool.assert_not_called();outbound.assert_not_called()
    assert run['status']=='waiting_recovery' and run['messages']==history
