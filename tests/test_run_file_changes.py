"""Recorded task changes, using disposable files and no live model or server."""
import copy
import hashlib
import json
import os
from pathlib import Path
from unittest import mock

import pytest
from code_runtime import run_file_changes as review

if not os.environ.get('CODE_DATA_DIR'):
    pytest.skip('Server integration requires disposable CODE_DATA_DIR', allow_module_level=True)
import server
from test_skill_model_loading import loading_env as immutable_env

RID = '1' * 32
CHILD = '2' * 32
NEXT = '3' * 32
SCOPE = {'dataSourceId': 'a' * 32, 'sessionId': '1234567890abcdef', 'sessionInstanceId': 'b' * 32}
BINDING = {'schema': review.BINDING, **SCOPE, 'rootRunId': RID,
           'rootClientRequestId': 'request-1', 'originMessageId': 'message-1', 'originRoot': '/project'}


def record(rid=RID):
    return {'version': 7, 'id': rid, 'sessionId': SCOPE['sessionId'], 'runKind': 'foreground',
            'status': 'completed', 'clientRequestId': 'request-1', 'reviewBinding': copy.deepcopy(BINDING),
            'toolExecutions': {}, 'result': {}, 'steerReceipts': []}


def operation(path='/project/file.txt', *, action='write_file', kind='update', diff='--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n'):
    result = {'ok': True, 'action': action, 'diff': diff, 'replayed': False}
    if action == 'apply_edit':
        result.update(applied=True, proposalId='op-1')
    if action == 'delete_file':
        result.pop('diff')
    result['fileChange'] = review.make_receipt(result, path, kind=kind, operation_id='op-1')
    return {'name': 'propose_edit' if action == 'apply_edit' else action,
            'status': 'completed', 'operationId': 'op-1', 'result': result}


@pytest.fixture
def records(tmp_path):
    def put(value):
        (tmp_path / (value['id'] + '.json')).write_text(json.dumps(value), encoding='utf-8')
    root = record(); root['toolExecutions']['call-1'] = operation(); put(root)
    return tmp_path, root, put


def project(path, rid=RID, **kw):
    return review.project(path, rid, SCOPE, lambda: dict(SCOPE), **kw)


def test_read_only_summary_detail_and_revision(records):
    path, root, put = records
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    summary = project(path)
    assert summary['coverage']['complete'] and summary['recordedFileCount'] == 1
    assert 'diff' not in summary['operations'][0]
    assert summary['operations'][0]['lineStats'] == {'additions': 1, 'deletions': 1}
    detail = project(path, operation=summary['operations'][0]['operationKey'], revision=summary['revision'])
    assert '+new' in detail['diff']
    assert before == {p.name: p.read_bytes() for p in path.iterdir()}
    root['status'] = 'failed'; put(root)
    with pytest.raises(review.ReviewError, match='review_changed'):
        project(path, operation=detail['operationKey'], revision=summary['revision'])


@pytest.mark.parametrize('diff, expected', [
    ('--- a/f\n+++ b/f\n@@ -1 +1 @@\n---old\n+++new\n', {'additions': 1, 'deletions': 1}),
    ('--- a/f\r\n+++ b/f\r\n@@ -0,0 +1,2 @@\r\n+a\r\n+b\r\n', {'additions': 2, 'deletions': 0}),
    ('--- a/f\n+++ b/f\n@@ -1 +0,0 @@\n-a\n@@ -4 +3 @@\n-b\n+c\n', {'additions': 1, 'deletions': 2}),
    ('--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n', {'additions': 1, 'deletions': 1}),
    ('--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n', None),
    ('--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+b\n+c\n', None),
    ('+not a unified diff', None),
    ('--- a/f\n+++ b/f\n@@ broken @@\n-a\n+b\n', None),
    pytest.param('--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+' + 'b' * review.DIFF_BYTES, None, id='oversized'),
])
def test_verified_line_stats(diff, expected):
    assert review.line_stats(diff) == expected


def test_deleted_operation_has_unknown_stats(records):
    path, root, put = records
    root['toolExecutions'] = {'delete': operation(action='delete_file', kind='delete')}
    put(root)
    assert project(path)['operations'][-1]['lineStats'] is None


@pytest.mark.parametrize('version', [5, 6, 7])
def test_optional_binding_outer_versions(records, version):
    path, root, put = records; root['version'] = version; put(root)
    assert project(path)['recordedFileCount'] == 1
    root.pop('reviewBinding'); put(root)
    with pytest.raises(review.ReviewError, match='binding_unavailable'):
        project(path)


@pytest.mark.parametrize('change', [lambda r: r['reviewBinding'].update(schema='future'),
    lambda r: r['reviewBinding'].update(sessionInstanceId='c'*32),
    lambda r: r['reviewBinding'].update(dataSourceId='c'*32),
    lambda r: r.update(sessionId='another'), lambda r: r.update(version=99)])
def test_unknown_or_cross_scope_fails_closed(records, change):
    path, root, put = records; change(root); put(root)
    with pytest.raises(review.ReviewError): project(path)


def test_bidirectional_child_continuation_and_independent_request(records):
    path, root, put = records
    child = record(CHILD); child.update(runKind='child', parentAgentRunId=RID, parentToolCallId='task-1')
    child['toolExecutions']['child-write'] = operation(action='apply_edit')
    root['toolExecutions']['task-1'] = {'name': 'task', 'childAgentRunId': CHILD}
    continuation = record(NEXT); continuation['clientRequestId'] = 'next-request'
    continuation['continuation'] = {'parentRunId': RID, 'rootRunId': RID, 'rootClientRequestId': 'request-1', 'index': 1}
    root['result']['continuation'] = {'agentRunId': NEXT, 'clientRequestId': 'next-request'}
    root['steerReceipts'] = [{'status':'consumed'}, {'status':'queued'}]
    for r in (root, child, continuation): put(r)
    summary = project(path, CHILD)
    assert summary['coverage']['complete'] and summary['steerCount'] == 1
    assert summary['recordedFileCount'] == 1 and len(summary['operations']) == 2
    assert len({op['groupKey'] for op in summary['operations']}) == 2
    child['parentToolCallId'] = 'forged'; put(child)
    assert not project(path)['coverage']['complete']
    with pytest.raises(review.ReviewError, match='unassociated'): project(path, CHILD)
    root['toolExecutions']['task-1']['childAgentRunId'] = RID; put(root)
    assert 'relationship_cycle' in project(path)['coverage']['reasons']


@pytest.mark.parametrize('modify,reason', [
    (lambda e: e['result'].update(replayed=True), 'replay_without_fresh_receipt'),
    (lambda e: e['result'].pop('replayed'), 'unconfirmed_effect'),
    (lambda e: e.update(status='cancelled', result={'ok':False,'cancelled':True}), 'unconfirmed_effect'),
    (lambda e: e['result'].pop('fileChange'), 'missing_file_receipt'),
    (lambda e: e['result']['fileChange'].update(fileKey='0'*64), 'missing_file_receipt'),
    (lambda e: e['result']['fileChange'].update(canonicalPath='relative.txt',fileKey=review.digest('relative.txt')), 'missing_file_receipt'),
    (lambda e: e['result']['fileChange'].update(entityKind='directory'), 'missing_file_receipt'),
    (lambda e: e.update(operationId='other'), 'operation_identity_conflict'),
    (lambda e: e['result'].update(diff='tampered'), 'diff_unavailable'),
    (lambda e: e.update(name='run_command'), 'uncovered_tool'),
    (lambda e: e.update(name='create_ppt_master_deck'), 'uncovered_tool')])
def test_coverage_gaps_never_become_no_change(records, modify, reason):
    path, root, put = records; modify(root['toolExecutions']['call-1']); put(root)
    value=project(path); assert reason in value['coverage']['reasons']; assert value['recordedFileCount']==0


@pytest.mark.parametrize('action,kind,body', [('apply_edit','update','diff'), ('write_file','create','no-line-diff'), ('delete_file','delete','not-retained')])
def test_actual_apply_empty_line_diff_and_delete(records, action, kind, body):
    path, root, put = records
    root['toolExecutions']['call-1'] = operation(action=action,kind=kind,diff='' if action=='write_file' else '+line');put(root)
    summary=project(path); assert summary['operations'][0]['bodyState']==body
    assert summary['recordedFileCount']==1
    root['toolExecutions']['duplicate']=copy.deepcopy(root['toolExecutions']['call-1']);put(root)
    assert len(project(path)['operations'])==1


def test_directory_is_not_a_file(records):
    path, root, put = records
    item=operation(action='delete_file',kind='delete');item['result']['fileChange']['entityKind']='directory'
    root['toolExecutions']={'call-1':item};put(root)
    summary=project(path);assert summary['recordedFileCount']==0 and len(summary['operations'])==1


def test_detached_background_request_is_its_own_root(records):
    path,root,put=records;root['runKind']='background';put(root)
    assert project(path)['rootRunId']==RID and project(path)['recordedFileCount']==1


@pytest.mark.parametrize('budget,value,expected', [('DIFF_BYTES',8,'review_diff_limit'),('DIFF_LINES',1,'review_diff_limit'),
    ('OPERATIONS',0,'review_operation_limit'),('FILES',0,'review_file_limit'),('SUMMARY_BYTES',256,'review_summary_limit')])
def test_projection_budgets_are_explicit(records, monkeypatch, budget, value, expected):
    path, _, _ = records;monkeypatch.setattr(review,budget,value)
    assert expected in project(path)['coverage']['reasons']


@pytest.mark.parametrize('budget', ['RUN_BYTES', 'TOTAL_BYTES'])
def test_read_budget_includes_verification(records, monkeypatch, budget):
    path, _, _ = records;size=(path/(RID+'.json')).stat().st_size
    monkeypatch.setattr(review,budget,size if budget=='TOTAL_BYTES' else size-1)
    with pytest.raises(review.ReviewError, match='read_limit'): project(path)


def test_change_during_read_and_missing_details(records):
    path, root, put = records
    def scope():
        return dict(SCOPE)
    original=review.Reader.verify
    def changed(reader):
        root['status']='cancelled';put(root);original(reader)
    with mock.patch.object(review.Reader,'verify',changed), pytest.raises(review.ReviewError,match='changed'):
        review.project(path,RID,SCOPE,scope)
    summary=project(path)
    with pytest.raises(review.ReviewError,match='missing_operation'):
        project(path,operation='0'*64,revision=summary['revision'])


@pytest.fixture
def integration(tmp_path, monkeypatch):
    data, project_dir = tmp_path/'data', tmp_path/'project';project_dir.mkdir()
    monkeypatch.setattr(server,'DATA_DIR',data);monkeypatch.setattr(server,'SESSIONS_DIR',data/'sessions')
    monkeypatch.setattr(server,'FILE_BACKUP_DIR',data/'backups')
    monkeypatch.setattr(server,'_effective_agent_project_root',lambda:str(project_dir))
    server.write_json(server.session_path(SCOPE['sessionId']),{'id':SCOPE['sessionId'],'createdAt':'2026-09-16T00:00:00'})
    return data,project_dir


def test_real_receipts_admission_and_pure_read(integration):
    data, path=integration
    value=server._new_run_review_binding(SCOPE['sessionId'],RID,'request-1','foreground',str(path),'msg','',None)
    assert value['schema']==review.BINDING
    target=path/'a.txt'
    result=server.execute_write_file_tool({'path':str(target),'content':'hello\n','_operationId':'op-1'})
    assert result['fileChange']['canonicalPath']==os.path.normcase(str(target.resolve()))
    root=record();root['reviewBinding']=value;root['toolExecutions']={'call-1':{'name':'write_file','status':'completed','operationId':'op-1','result':result}}
    server.write_json(data/'agent-runs'/(RID+'.json'),root)
    before={str(p):p.read_bytes() for p in data.rglob('*') if p.is_file()}
    scope=server._read_review_scope(SCOPE['sessionId'])
    with mock.patch.object(server,'_get_agent_run',side_effect=AssertionError('recovery forbidden')),mock.patch.object(server,'write_json',side_effect=AssertionError('write forbidden')):
        summary=review.project(data/'agent-runs',RID,scope,lambda:server._read_review_scope(SCOPE['sessionId']))
    assert summary['recordedFileCount']==1
    assert before=={str(p):p.read_bytes() for p in data.rglob('*') if p.is_file()}


def test_receipt_failure_does_not_fail_write_and_replay_is_not_new(integration):
    _,path=integration;target=path/'a.txt'
    with mock.patch.object(review,'make_receipt',side_effect=OSError('capture failed')):
        result=server.execute_write_file_tool({'path':str(target),'content':'hello','_operationId':'op'})
    assert result['ok'] and result['fileChangeUnavailable'] and target.read_text()=='hello'
    repeated=server.execute_write_file_tool({'path':str(target),'content':'hello','_operationId':'op'})
    assert repeated['replayed'] and 'fileChange' not in repeated


def test_delete_race_has_no_fresh_receipt(integration):
    _,path=integration;target=path/'a.txt';target.write_text('hello')
    original=Path.unlink
    def raced(p,*args,**kwargs):
        if p==target:
            original(p);raise FileNotFoundError()
        return original(p,*args,**kwargs)
    with mock.patch.object(Path,'unlink',raced):
        result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert result['ok'] and result['fileChangeUnavailable'] and 'fileChange' not in result


def test_run_binding_roundtrip_repeat_and_old_writer_loss(integration):
    _,path=integration
    run=server._create_agent_run(SCOPE['sessionId'],{'model':'test-model','messages':[{'role':'user','content':'fixture'}]},
        'http://127.0.0.1:9',[],allowed_tools=[],start_worker=False,client_request_id='review-roundtrip',
        run_kind='foreground',cwd=str(path))
    try:
        original=copy.deepcopy(run['review_binding']);assert original['schema']==review.BINDING
        saved=server._agent_run_record(run)
        restored=server._agent_run_from_record(saved,immutable_skill_reader=None)
        assert server._agent_run_record(restored)['reviewBinding']==original
        duplicate=server._create_agent_run(SCOPE['sessionId'],{'model':'test-model','messages':[{'role':'user','content':'fixture'}]},
            'http://127.0.0.1:9',[],allowed_tools=[],start_worker=False,client_request_id='review-roundtrip',
            run_kind='foreground',cwd=str(path))
        assert duplicate is run and duplicate['review_binding']==original
        saved['reviewBinding']={'schema':'future','unknown':['keep']}
        restored=server._agent_run_from_record(saved,immutable_skill_reader=None)
        assert server._agent_run_record(restored)['reviewBinding']==saved['reviewBinding']
        assert server._public_run_review_binding(restored) is None
        # The previous writer reconstructed only known Run keys; simulate that exact loss boundary.
        restored.pop('review_binding')
        assert 'reviewBinding' not in server._agent_run_record(restored)
    finally:
        server._agent_runs.pop(run['id'],None)


def test_member_limit_and_missing_child_are_explicit(records, monkeypatch):
    path,root,put=records
    for index,rid in enumerate([CHILD,NEXT]):
        child=record(rid);child.update(runKind='child',parentAgentRunId=RID,parentToolCallId=f'task-{index}')
        root['toolExecutions'][f'task-{index}']={'name':'task','childAgentRunId':rid};put(child)
    put(root);monkeypatch.setattr(review,'MEMBERS',2)
    assert 'review_member_limit' in project(path)['coverage']['reasons']


def test_malformed_record_and_missing_record(records):
    path,root,put=records
    root['toolExecutions']['call-1']['name']={};put(root)
    with pytest.raises(review.ReviewError,match='record_invalid'):project(path)
    (path/(RID+'.json')).write_text('{',encoding='utf-8')
    with pytest.raises(review.ReviewError,match='record_invalid'):project(path)
    (path/(RID+'.json')).unlink()
    with pytest.raises(review.ReviewError,match='missing_run'):project(path)


def test_nonregular_run_record_is_never_opened(records):
    from types import SimpleNamespace
    import stat
    path,_,_=records
    with mock.patch.object(Path,'stat',return_value=SimpleNamespace(st_mode=stat.S_IFIFO,st_size=0)),mock.patch.object(Path,'open',side_effect=AssertionError('must not open')):
        with pytest.raises(review.ReviewError,match='record_unavailable'):project(path)


def test_session_archive_restore_and_failed_delete_preserve_run_fields():
    from test_session_persistence import TestSessionArchiveLifecycle
    fixture=TestSessionArchiveLifecycle();fixture.setUp();run=None
    try:
        created=fixture.create_session();sid=created['id']
        server._preview_context({'sessionId':sid},initialize=True)
        with mock.patch.object(server,'_session_location',return_value=(None,str(fixture.root))):
            run=server._create_agent_run(sid,{'model':'test-model','messages':[{'role':'user','content':'fixture'}]},
            'http://127.0.0.1:9',[],allowed_tools=[],start_worker=False,client_request_id='review-lifecycle',
            run_kind='foreground',cwd=str(fixture.temp_dir.name) if hasattr(fixture,'temp_dir') else str(server.DATA_DIR))
        run['status']='completed';server._persist_agent_run(run)
        run_path=server._agent_run_path(run['id']);before=run_path.read_bytes()
        assert json.loads(before)['reviewBinding']['schema']==review.BINDING
        scope=server._read_review_scope(sid)
        fixture.archive(sid)
        with pytest.raises(review.ReviewError,match='scope_unavailable'):server._read_review_scope(sid)
        fixture.unarchive(sid)
        assert server._read_review_scope(sid)==scope and run_path.read_bytes()==before
        handler=fixture.make_handler()
        with mock.patch.object(server,'_remove_session_index_entry',side_effect=OSError('rollback fixture')):
            with pytest.raises(server.SessionDeleteError):handler.delete_session(sid,delete_terminal_agent_runs=True)
        assert run_path.read_bytes()==before and server._read_review_scope(sid)==scope
        handler.delete_session(sid,delete_terminal_agent_runs=True)
        assert not run_path.exists()
        with pytest.raises(review.ReviewError,match='scope_unavailable'):server._read_review_scope(sid)
    finally:
        if run:server._agent_runs.pop(run['id'],None)
        fixture.doCleanups()


def test_write_then_cancel_retains_effect_but_reports_missing_receipt(integration):
    data,path=integration
    run=server._create_agent_run(SCOPE['sessionId'],{'model':'test-model','messages':[{'role':'user','content':'fixture'}],
        'tools':[server._SERVER_TOOL_DEFINITIONS['write_file']]},'http://127.0.0.1:9',[],
        allowed_tools=['write_file'],permission_profile='bypass',start_worker=False,client_request_id='review-cancel',run_kind='foreground',cwd=str(path))
    try:
        run['messages'].append({'role':'assistant','content':'','tool_calls':[]})
        run['pending_tool_calls']=server._normalize_agent_tool_calls(run,[{'id':'cancel-write','function':{'name':'write_file','arguments':{'path':'cancelled.txt','content':'written'}}}],1)
        run['status']='tools'
        original=server.execute_registered_tool
        def execute(*args,**kwargs):
            result=original(*args,**kwargs);run['cancel_event'].set();return result
        with mock.patch.object(server,'execute_registered_tool',execute):
            assert server._execute_agent_pending_tools(run) is False
        assert (path/'cancelled.txt').read_text()=='written'
        run['status']='cancelled';server._persist_agent_run(run)
        scope=server._read_review_scope(SCOPE['sessionId'])
        value=review.project(data/'agent-runs',run['id'],scope,lambda:server._read_review_scope(SCOPE['sessionId']))
        assert not value['coverage']['complete'] and value['recordedFileCount']==0
    finally:server._agent_runs.pop(run['id'],None)


@pytest.mark.parametrize('version',[6,7])
def test_immutable_outer_versions_preserve_optional_review_fields(immutable_env,monkeypatch,version):
    from test_skill_model_loading import make_run,call
    if version==7:
        run=make_run(immutable_env)
    else:
        from tests.test_skill_runtime_v2_agentrun import _run
        monkeypatch.setattr(server,'_SKILL_MODEL_LOADING_ENABLED',False)
        run=_run(immutable_env[-1],explicit='ledger')
    run['review_binding']=copy.deepcopy(BINDING)
    saved=server._agent_run_record(run)
    assert saved['version']==version
    restored=server._agent_run_from_record(saved,immutable_skill_reader=immutable_env[-1])
    assert server._agent_run_record(restored)['reviewBinding']==BINDING
    saved['reviewBinding']={'schema':'unknown-optional-review','payload':{'keep':True}}
    restored=server._agent_run_from_record(saved,immutable_skill_reader=immutable_env[-1])
    assert server._agent_run_record(restored)['reviewBinding']==saved['reviewBinding']


def delete_projection(tmp_path, result):
    directory=tmp_path/'review-runs';directory.mkdir(exist_ok=True)
    root=record();root['toolExecutions']={'delete':{'name':'delete_file','status':'completed','operationId':'delete-op','result':result}}
    (directory/(RID+'.json')).write_text(json.dumps(root),encoding='utf-8')
    summary=project(directory)
    detail=project(directory,operation=summary['operations'][0]['operationKey'],revision=summary['revision'])
    return summary,detail


@pytest.mark.parametrize('raw,count', [(b'',0),(b'hello',1),(b'hello\n',1),('中文\n第二行'.encode(),2),(b'\xef\xbb\xbfhello\r\nworld\r\n',2),(b'one\r\r\ntwo\rthree',3),(b'+++text\n---text',2)])
def test_delete_capture_text_variants(integration,tmp_path,raw,count):
    _,path=integration;target=path/'delete.txt';target.write_bytes(raw)
    result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert result['ok'] and not target.exists() and review.DELETE_PRIVATE in result
    assert result[review.DELETE_PRIVATE]['byteLength']==len(raw)
    _,detail=delete_projection(tmp_path,result)
    assert detail['lineStats']=={'additions':0,'deletions':count}
    assert detail['bodyState']==('diff' if count else 'no-line-diff')
    assert review.DELETE_PRIVATE not in detail


@pytest.mark.parametrize('raw,reason', [pytest.param(b'x'*(review.DELETE_BYTES+1),'limit',id='size'),pytest.param(b'x\n'*review.DIFF_LINES,'limit',id='lines'),(b'\0abc','binary'),(b'\xffabc','encoding')])
def test_delete_capture_unavailable_keeps_success(integration,tmp_path,raw,reason):
    _,path=integration;target=path/'delete.txt';target.write_bytes(raw)
    result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert result['ok'] and not target.exists() and review.DELETE_PRIVATE not in result
    _,detail=delete_projection(tmp_path,result)
    assert detail['bodyReason']==reason and detail['lineStats'] is None


def test_delete_capture_bounded_read_and_changed_identity(tmp_path):
    target=tmp_path/'x';target.write_bytes(b'old');target.write_bytes(b'abc')
    original=os.fdopen;reads=[]
    class Stream:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):return self
        def __exit__(self,*args):self.stream.close()
        def fileno(self):return self.stream.fileno()
        def read(self,n):reads.append(n);return self.stream.read(n)
    with mock.patch.object(os,'fdopen',lambda fd,*a,**k:Stream(original(fd,*a,**k))):
        proof,signature,reason=review.capture_delete(target,'op')
    assert reads==[review.DELETE_BYTES+1] and reason is None
    target.write_bytes(b'other');assert not review.delete_capture_current(target,proof,signature)


@pytest.mark.parametrize('version',[6,7])
def test_delete_private_evidence_roundtrip_immutable_versions(immutable_env,version):
    from test_skill_model_loading import make_run,call
    secret='DELETE_PRIVATE_VERSION_'+str(version);target=immutable_env[2]/'deletable.txt';target.write_text(secret)
    if version==7:run=make_run(immutable_env,tools=['delete_file'])
    else:
        from tests.test_skill_runtime_v2_agentrun import _run
        run=_run(immutable_env[-1],explicit='',permission='bypass',tools=['delete_file'])
    try:
        result=execute_call(run,'delete_file',{'path':str(target)},'call-1');assert review.DELETE_PRIVATE in result
        saved=server._agent_run_record(run);assert saved['version']==version
        restored=server._agent_run_from_record(saved,immutable_skill_reader=immutable_env[-1])
        assert restored['tool_executions']['call-1']['result'][review.DELETE_PRIVATE]==result[review.DELETE_PRIVATE]
        assert secret not in json.dumps(server._agent_snapshot(restored))+json.dumps(server._agent_model_payload(restored))
    finally:server._agent_runs.pop(run['id'],None)


def test_delete_then_cancel_does_not_publish_unpersisted_proof(integration):
    data,path=integration;target=path/'secret.txt';target.write_text('PRIVATE_CANCELLED_DELETE')
    run=new_delete_run(integration,'delete-cancel');original=server.execute_registered_tool
    def execute(*args,**kwargs):
        result=original(*args,**kwargs);run['cancel_event'].set();return result
    try:
        with mock.patch.object(server,'execute_registered_tool',execute):execute_call(run,'delete_file',{'path':'secret.txt'},'delete-cancel')
        assert not target.exists()
        run['status']='cancelled';server._persist_agent_run(run)
        saved=server._agent_run_record(run);assert review.DELETE_PRIVATE not in json.dumps(saved)
        scope=server._read_review_scope(SCOPE['sessionId']);summary=review.project(data/'agent-runs',run['id'],scope,lambda:scope)
        assert not summary['coverage']['complete'] and summary['recordedFileCount']==0
    finally:server._agent_runs.pop(run['id'],None)


def test_process_exit_after_delete_before_result_does_not_invent_evidence(tmp_path):
    import subprocess
    import sys
    data=tmp_path/'crash-data';workspace=tmp_path/'crash-project';workspace.mkdir()
    target=workspace/'lost.txt';target.write_text('PRIVATE_CRASH_DELETE')
    output=tmp_path/'run-id.txt'
    script=r'''
import os,sys
from pathlib import Path
import server
sid='1234567890abcdef'
server.write_json(server.session_path(sid),{'id':sid,'createdAt':'2026-09-16T00:00:00','cwd':sys.argv[1]})
run=server._create_agent_run(sid,{'model':'fixture','messages':[{'role':'user','content':'fixture'}]},'http://127.0.0.1:9',[],allowed_tools=[],permission_profile='bypass',start_worker=False,client_request_id='crash-delete',run_kind='foreground',cwd=sys.argv[1])
run['tool_executions']['delete']={'name':'delete_file','status':'applying_file_mutation','operationId':'delete-op','arguments':'{}'}
run['status']='tools';server._persist_agent_run(run)
Path(sys.argv[2]).write_text(run['id'])
result=server.execute_delete_file_tool({'path':str(Path(sys.argv[1])/'lost.txt'),'_operationId':'delete-op'})
assert result['ok'] and '_codeReviewDelete' in result
os._exit(73)
'''
    env={**os.environ,'CODE_DATA_DIR':str(data),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}
    child=subprocess.run([sys.executable,'-B','-c',script,str(workspace),str(output)],cwd=Path(server.__file__).parent,env=env,capture_output=True,text=True,timeout=20)
    assert child.returncode==73,child.stderr
    assert not target.exists()
    rid=output.read_text();raw=(data/'agent-runs'/(rid+'.json')).read_text(encoding='utf-8');saved=json.loads(raw)
    assert review.DELETE_PRIVATE not in raw and 'PRIVATE_CRASH_DELETE' not in raw
    scope={key:saved['reviewBinding'][key] for key in SCOPE}
    summary=review.project(data/'agent-runs',rid,scope,lambda:scope)
    assert not summary['coverage']['complete'] and summary['recordedFileCount']==0


def test_delete_capture_errors_and_final_change_do_not_flip_delete(integration,tmp_path):
    _,path=integration
    for n,patcher in enumerate([mock.patch.object(review,'capture_delete',side_effect=OSError('read failed')),mock.patch.object(review,'delete_capture_current',return_value=False)]):
        target=path/f'x{n}';target.write_text('hello')
        with patcher:result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
        assert result['ok'] and not target.exists() and review.DELETE_PRIVATE not in result
        _,detail=delete_projection(tmp_path,result)
        assert detail['lineStats'] is None and detail['bodyReason'] in {'changed','unreadable'}


def test_delete_auxiliary_receipt_failure_discards_private_body(integration):
    _,path=integration;target=path/'x';target.write_text('private')
    with mock.patch.object(review,'make_receipt',side_effect=ValueError('broken')):
        result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert result['ok'] and result['fileChangeUnavailable'] and not target.exists()
    assert review.DELETE_PRIVATE not in result


def test_directory_and_managed_memory_do_not_capture_body(integration,monkeypatch):
    _,path=integration;directory=path/'empty';directory.mkdir()
    with mock.patch.object(review,'capture_delete',side_effect=AssertionError('excluded')):
        result=server.execute_delete_file_tool({'path':str(directory),'_operationId':'directory-op'})
        assert result['isDirectory'] and review.DELETE_PRIVATE not in result
        target=path/'managed';target.write_text('private memory')
        monkeypatch.setattr(server,'_managed_memory_file',lambda _: 'memory')
        monkeypatch.setattr(server._agent_workspace_context,'memory_authorization',{'name':'memory','scope':{}},raising=False)
        with mock.patch.object(server,'execute_delete_memory_tool',return_value={'ok':True}):
            result=server.execute_delete_file_tool({'path':str(target),'_operationId':'memory-op'})
        assert review.DELETE_PRIVATE not in result


def test_delete_failure_prewritten_receipt_and_replay_never_invent_body(integration):
    _,path=integration;target=path/'x';target.write_text('secret')
    with mock.patch.object(Path,'unlink',side_effect=PermissionError('blocked')):
        with pytest.raises(PermissionError):server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert target.exists()
    assert server._read_delete_receipt('delete-op',server.to_project_relative(path,target))
    target.unlink()  # external loss after prewritten idempotency receipt, not this tool's effect
    replay=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert replay['replayed'] and review.DELETE_PRIVATE not in replay and 'fileChange' not in replay


@pytest.mark.parametrize('field', ['text','sha256','byteLength','operationId','canonicalPath','schema'])
def test_delete_tampering_preserves_fact_but_rejects_body(integration,tmp_path,field):
    _,path=integration;target=path/'x';target.write_text('secret')
    result=server.execute_delete_file_tool({'path':str(target),'_operationId':'delete-op'})
    assert review.DELETE_PRIVATE in result, review.public_value(result)
    result[review.DELETE_PRIVATE][field]='tampered'
    summary,detail=delete_projection(tmp_path,result)
    assert summary['recordedFileCount']==1 and not summary['coverage']['complete']
    assert detail['kind']=='delete' and detail['bodyReason']=='unverifiable' and detail['lineStats'] is None and not detail['diff']


def new_delete_run(integration,request_id):
    _,path=integration;names=['write_file','propose_edit','delete_file']
    return server._create_agent_run(SCOPE['sessionId'],{'model':'test-model','messages':[{'role':'user','content':'fixture'}],
        'tools':[server._SERVER_TOOL_DEFINITIONS[name] for name in names]},'http://127.0.0.1:9',[],
        allowed_tools=names,permission_profile='bypass',start_worker=False,client_request_id=request_id,run_kind='foreground',cwd=str(path))


def execute_call(run,name,arguments,call_id):
    calls=server._normalize_agent_tool_calls(run,[{'id':call_id,'function':{'name':name,'arguments':arguments}}],1)
    run['messages'].append({'role':'assistant','content':'','tool_calls':server._agent_assistant_tool_calls(calls)})
    run['pending_tool_calls']=calls;run['status']='tools'
    server._execute_agent_pending_tools(run)
    return run['tool_executions'][call_id]['result']


def test_real_write_apply_delete_run_chain_totals(integration):
    data,path=integration;run=new_delete_run(integration,'delete-chain')
    try:
        assert execute_call(run,'write_file',{'path':'notes.md','content':'one\ntwo\nthree\n'},'write-notes')['ok']
        assert execute_call(run,'propose_edit',{'path':'notes.md','newContent':'ONE\nTWO\nthree\n'},'edit-notes')['applied']
        assert execute_call(run,'write_file',{'path':'temporary.txt','content':'temporary\n'},'write-temp')['ok']
        result=execute_call(run,'delete_file',{'path':'temporary.txt'},'delete-temp');assert review.DELETE_PRIVATE in result,review.public_value(result)
        run['status']='completed';server._persist_agent_run(run)
        scope=server._read_review_scope(SCOPE['sessionId']);value=review.project(data/'agent-runs',run['id'],scope,lambda:server._read_review_scope(SCOPE['sessionId']))
        assert value['coverage']['complete'] and value['recordedFileCount']==2
        assert sum(op['lineStats']['additions'] for op in value['operations'])==6
        assert sum(op['lineStats']['deletions'] for op in value['operations'])==3
        deleted=next(op for op in value['operations'] if op['kind']=='delete')
        detail=review.project(data/'agent-runs',run['id'],scope,lambda:scope,operation=deleted['operationKey'],revision=value['revision'])
        assert '-temporary' in detail['diff'] and deleted['lineStats']=={'additions':0,'deletions':1}
    finally:server._agent_runs.pop(run['id'],None)


def test_private_delete_body_only_in_run_result_across_projection_and_restore(integration):
    data,path=integration;secret='PRIVATE_DELETE_ONLY_928af'
    (path/'secret.txt').write_text(secret)
    run=new_delete_run(integration,'delete-private')
    try:
        result=execute_call(run,'delete_file',{'path':'secret.txt'},'delete-secret')
        assert secret in result[review.DELETE_PRIVATE]['text']
        assert secret not in json.dumps(server._agent_snapshot(run))
        assert secret not in server._agent_tool_message_content(result)
        assert secret not in json.dumps(server._agent_model_payload(run))
        saved=server._agent_run_record(run)
        assert saved['version']==5 and secret in json.dumps(saved['toolExecutions'])
        assert secret not in json.dumps(saved['messages'])+json.dumps(saved['events'])
        # Recovery of a legacy writer's accidental structured/JSON tool projection is filtered too.
        saved['events'].append({'seq':999,'type':'tool_completed','data':{'result':result},'createdAt':server.now_iso()})
        saved['messages'][-1]['content']=json.dumps(result)
        restored=server._agent_run_from_record(saved,immutable_skill_reader=None)
        assert secret in restored['tool_executions']['delete-secret']['result'][review.DELETE_PRIVATE]['text']
        assert secret not in json.dumps(server._agent_snapshot(restored))+json.dumps(server._agent_model_payload(restored))
        restored['events']=[];restored['status']='tools';restored['pending_tool_calls']=[{'id':'delete-secret','function':{'name':'delete_file'}}]
        with restored['condition']:server._close_agent_tools_for_cancel_locked(restored)
        assert any(event['type']=='tool_completed' for event in restored['events'])
        assert secret not in json.dumps(restored['events'])
        resaved=server._agent_run_record(restored);assert secret not in json.dumps(resaved['events'])+json.dumps(resaved['messages'])
        # General tool HTTP handler must not return the private field.
        from types import SimpleNamespace
        output=[];handler=SimpleNamespace(read_body_json=lambda:{'path':'ignored'},send_json=lambda value:output.append(value))
        with mock.patch.object(server,'execute_registered_tool',return_value=result):server.CodeHandler.tool_delete_file(handler)
        assert secret not in json.dumps(output) and review.DELETE_PRIVATE not in output[0]
    finally:server._agent_runs.pop(run['id'],None)
