"""Stage two service/HTTP tests inside a disposable data-root child process."""
import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest import mock
from pathlib import Path

import pytest

if not os.environ.get('CODE_DATA_DIR'):
    raise RuntimeError('Disposable CODE_DATA_DIR required')
import server as srv
import test_session_persistence as fixtures
from code_runtime.project_archive import BatchError, ArchiveService
from code_runtime.project_archive_delete import DeleteService

GROUP = {'kind':'project','projectId':'delete-project'}


@pytest.fixture
def setup():
    fixture = fixtures.TestSessionArchiveLifecycle();fixture.setUp()
    try:
        with mock.patch.object(srv,'PROJECTS_PATH',fixture.root/'projects.json'), mock.patch.object(srv,'CONFIG_PATH',fixture.root/'config.json'):
            other = fixture.root/'other';other.mkdir()
            srv.write_json(srv.CONFIG_PATH,{'projectRoot':str(fixture.root)})
            srv._write_projects([{'id':'delete-project','label':'Same name','rootPaths':[str(fixture.root)]},
                                 {'id':'other-project','label':'Same name','rootPaths':[str(other)]}])
            yield fixture,DeleteService(srv)
    finally:
        fixture.doCleanups()


def make(f, pid='delete-project', *, archived=True):
    record=f.create_session(title='Delete fixture')
    f.attach_session_to_project(record['id'],pid,f.root)
    if archived:srv._mutate_session_archive_state(record['id'],archived=True)
    return record['id']


def confirm(service, preview, **overrides):
    params={'group':preview['scope'],'action':preview['action'],'token':preview['confirmationToken']}
    params.update(overrides)
    return service.execute(preview['operationId'],**params)


def state(result, sid):
    return next(i['state'] for i in result['items'] if i['sessionId']==sid)


def test_exact_group_preserves_unarchived_other_project_workspace_and_shared_upload(setup):
    f,s=setup
    target=make(f);other=make(f,'other-project');active=make(f,archived=False)
    sentinel=f.root/'workspace.txt';sentinel.write_bytes(b'workspace')
    uploads=f.root/'attachments';uploads.mkdir();shared=uploads/'shared.png';shared.write_bytes(b'shared attachment')
    projects=srv.PROJECTS_PATH.read_bytes();config=srv.CONFIG_PATH.read_bytes()
    owned_asset=f.create_asset_sidecar(target,'d');other_asset=f.create_asset_sidecar(other,'e')
    others=srv._session_archive_bundle_path(other)/'session.json';other_bytes=others.read_bytes()
    result=confirm(s,s.preview(GROUP))
    assert state(result,target)=='deleted'
    assert not srv._session_archive_bundle_path(target).exists()
    assert srv.session_path(active).exists() and others.read_bytes()==other_bytes
    assert sentinel.read_bytes()==b'workspace' and shared.read_bytes()==b'shared attachment'
    assert not owned_asset.exists() and other_asset.exists()
    assert srv.PROJECTS_PATH.read_bytes()==projects and srv.CONFIG_PATH.read_bytes()==config


@pytest.mark.parametrize('wrong', ['token','scope','action','archive_confirmation','another_batch'])
def test_wrong_confirmation_cannot_delete(setup,wrong):
    f,s=setup;sid=make(f);preview=s.preview(GROUP)
    if wrong=='token':params={'token':'wrong'}
    elif wrong=='scope':params={'group':{'kind':'project','projectId':'other-project'}}
    elif wrong=='action':params={'action':'archive'}
    elif wrong=='another_batch':params={'token':s.preview(GROUP)['confirmationToken']}
    else:
        make(f,archived=False)
        params={'token':ArchiveService(srv).preview('delete-project')['confirmationToken']}
    before=(srv._session_archive_bundle_path(sid)/'session.json').read_bytes()
    with pytest.raises(BatchError):confirm(s,preview,**params)
    assert (srv._session_archive_bundle_path(sid)/'session.json').read_bytes()==before
    assert not s.store.root.exists()


@pytest.mark.parametrize('bad', [None,{},'',{'kind':'project','projectId':''},{'kind':'unassigned','projectId':''},{'kind':'all'}])
def test_scope_cannot_mean_all_projects(setup,bad):
    f,s=setup;sid=make(f)
    with pytest.raises(BatchError):s.preview(bad)
    assert srv._session_archive_bundle_path(sid).exists()


def test_unassigned_and_historical_deleted_project_are_separate(setup):
    f,s=setup
    unassigned=make(f,None);historical=make(f,'gone-project');other=make(f)
    preview=s.preview({'kind':'unassigned'})
    assert [i['sessionId'] for i in preview['items']]==[unassigned]
    assert state(confirm(s,preview),unassigned)=='deleted'
    preview=s.preview({'kind':'deleted-project','projectId':'gone-project'})
    assert [i['sessionId'] for i in preview['items']]==[historical]
    assert state(confirm(s,preview),historical)=='deleted'
    assert srv._session_archive_bundle_path(other).exists()


def test_cancel_and_later_archive_not_in_fixed_target_list(setup):
    f,s=setup;sid=make(f)
    preview=s.preview(GROUP);s.store.cancel_preview(preview['operationId'],preview['confirmationToken'])
    assert not s.store.root.exists()
    preview=s.preview(GROUP);later=make(f)
    assert state(confirm(s,preview),sid)=='deleted'
    assert srv._session_archive_bundle_path(later).exists()


@pytest.mark.parametrize('change',['restore','rearchive','project_rename','historical_recreated','move'])
def test_archive_incarnation_and_scope_changes_conflict(setup,change):
    f,s=setup
    pid='gone-project' if change=='historical_recreated' else 'delete-project'
    group={'kind':'deleted-project','projectId':pid} if change=='historical_recreated' else GROUP
    sid=make(f,pid);preview=s.preview(group)
    if change in {'restore','rearchive','move'}:
        srv._mutate_session_archive_state(sid,archived=False)
        if change=='move':f.attach_session_to_project(sid,'other-project',f.root)
        if change!='restore':srv._mutate_session_archive_state(sid,archived=True)
    else:
        projects=srv._read_projects()
        if change=='project_rename':projects[0]['label']='Changed name'
        else:
            root=f.root/'revived';root.mkdir()
            projects.append({'id':pid,'label':'New identity','rootPaths':[str(root)]})
        srv._write_projects(projects)
    result=confirm(s,preview)
    assert state(result,sid)=='conflict',result
    assert srv.session_path(sid).exists() or srv._session_archive_bundle_path(sid).exists()


def test_partial_failure_retry_uses_only_old_failed_ids(setup):
    f,s=setup;ids=sorted([make(f),make(f)]);preview=s.preview(GROUP)
    original=srv.CodeHandler.delete_session
    def fail(self,sid,**kwargs):
        if sid==ids[1]:raise srv.SessionDeleteError()
        return original(self,sid,**kwargs)
    with mock.patch.object(srv.CodeHandler,'delete_session',fail):result=confirm(s,preview)
    assert [i['state'] for i in result['items']]==['deleted','failed'],result
    later=make(f)
    retry=s.preview(GROUP,preview['operationId'])
    assert [i['sessionId'] for i in retry['items']]==[ids[1]]
    assert state(confirm(s,retry),ids[1])=='deleted'
    assert srv._session_archive_bundle_path(later).exists()


def test_old_batch_does_not_delete_rebuilt_same_id(setup):
    f,s=setup;sid=make(f);preview=s.preview(GROUP)
    assert state(confirm(s,preview),sid)=='deleted'
    srv._mark_session_created(sid)
    srv.write_json(srv.session_path(sid),{'id':sid,'projectId':'delete-project','cwd':str(f.root),'title':'new incarnation'})
    srv.write_jsonl(srv.messages_path(sid),[{'role':'user','content':'new object'}])
    srv._mutate_session_archive_state(sid,archived=True)
    before=(srv._session_archive_bundle_path(sid)/'manifest.json').read_bytes()
    assert state(s.execute(preview['operationId'],GROUP,'permanent_delete',resume=True),sid)=='deleted'
    assert (srv._session_archive_bundle_path(sid)/'manifest.json').read_bytes()==before


def test_goal_terminal_run_removed_and_stage_one_receipt_survives(setup):
    f,s=setup;sid=make(f,archived=False)
    f.create_active_goal(sid)
    run=f.create_active_agent_run(sid);srv._cancel_agent_run(run['id'])
    first=ArchiveService(srv);p=first.preview('delete-project')
    first.execute(p['operationId'],token=p['confirmationToken'],action=p['action'])
    goal=srv.goal_v2_runtime().service.events_path(sid);assert goal.exists()
    assert state(confirm(s,s.preview(GROUP)),sid)=='deleted'
    assert not goal.exists() and not srv._agent_run_path(run['id']).exists()
    assert first.execute(p['operationId'],resume=True)['items'][0]['state']=='archived'


def test_http_parallel_confirm_and_read_result(setup):
    f,s=setup;sid=make(f)
    class Handler(srv.CodeHandler):
        def log_message(self,*args):pass
    host=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=host.serve_forever);worker.start()
    def call(action,body):
        request=Request(f'http://127.0.0.1:{host.server_port}/api/project-archive-delete/{action}',
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=15) as response:return json.load(response)
        except HTTPError as exc:
            payload=json.load(exc)
            assert exc.code==503 and payload.get('errorCode') in {'project_archive_busy','session_archive_busy'},payload
            return {'busy':True,'errorCode':payload['errorCode']}
    try:
        preview=call('preview',{'scope':GROUP})
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:call('confirm',preview),range(2)))
        assert any(not result.get('busy') and state(result,sid)=='deleted' for result in results)
        for result in results:
            if result.get('busy'):
                # The existing one-second bounded lock may reject a concurrent
                # request while fsync is slow. Retry the same confirmed identity.
                assert state(call('confirm',preview),sid)=='deleted'
            else:assert state(result,sid)=='deleted'
        with urlopen(f'http://127.0.0.1:{host.server_port}/api/project-archive-delete') as response:
            assert json.load(response)['data'][0]['items'][0]['state']=='deleted'
    finally:
        host.shutdown();host.server_close();worker.join(timeout=3)
        assert not worker.is_alive()


def test_delete_and_restore_race_has_one_authoritative_winner(setup):
    f,s=setup;sid=make(f);preview=s.preview(GROUP)
    entered=threading.Event();release=threading.Event();restore_started=threading.Event()
    original=srv._project_archive_delete_prepare_core
    def gated(journal,manifest):
        entered.set();assert release.wait(3)
        return original(journal,manifest)
    def restore():
        restore_started.set()
        try:return srv._mutate_session_archive_state(sid,archived=False)
        except srv.SessionLifecycleConflictError as exc:return {'errorCode':exc.error_code}
    from concurrent.futures import ThreadPoolExecutor
    with mock.patch.object(srv,'_project_archive_delete_prepare_core',gated), ThreadPoolExecutor(max_workers=2) as pool:
        deleting=pool.submit(confirm,s,preview);assert entered.wait(3)
        restoring=pool.submit(restore);assert restore_started.wait(3);release.set()
        assert state(deleting.result(timeout=10),sid)=='deleted'
        assert restoring.result(timeout=10)['errorCode'] in {'session_deleted','session_not_found','session_archive_busy'}
    assert not srv.session_path(sid).exists() and not srv._session_archive_bundle_path(sid).exists()


def test_foreign_restore_transaction_is_not_recovered_by_delete_batch(setup):
    f,s=setup;sid=make(f);preview=s.preview(GROUP)
    import uuid
    srv._write_session_archive_journal(sid,{'action':'restore','state':'prepared','transactionId':uuid.uuid4().hex})
    before=srv._session_archive_journal_path(sid).read_bytes()
    result=confirm(s,preview)
    assert state(result,sid)=='uncertain'
    assert srv._session_archive_journal_path(sid).read_bytes()==before
    assert not srv.session_path(sid).exists() and srv._session_archive_bundle_path(sid).exists()


@pytest.mark.parametrize('damage',['operation','effect'])
def test_damaged_batch_evidence_never_authorizes_more_deletion(setup,damage):
    f,s=setup;sid=make(f);preview=s.preview(GROUP)
    if damage=='operation':
        s.store.confirm(preview['operationId'],preview['confirmationToken'],'permanent_delete')
        s.store.path(preview['operationId']).write_text('{damaged',encoding='utf-8')
        with pytest.raises(BatchError):confirm(s,preview)
        assert srv._session_archive_bundle_path(sid).exists()
    else:
        assert state(confirm(s,preview),sid)=='deleted'
        s.store.effect_path(preview['operationId'],sid).write_text('{damaged',encoding='utf-8')
        with pytest.raises(BatchError):s.execute(preview['operationId'],GROUP,'permanent_delete',resume=True)


@pytest.mark.parametrize('failure',['bundle','journal'])
def test_cleanup_pending_is_not_reported_as_deleted(setup,failure):
    f,s=setup;ids=sorted([make(f),make(f)]);sid=ids[0]
    bundle=srv._session_archive_bundle_path(sid);journal=srv._session_archive_journal_path(sid)
    remove_tree=srv._remove_owned_archive_tree;unlink=Path.unlink
    attempts=[]
    def locked_bundle(path):
        if path==bundle:
            attempts.append('bundle');raise PermissionError('fixture archive copy is locked')
        return remove_tree(path)
    def locked_journal(path,*args,**kwargs):
        if path==journal:
            attempts.append('journal');raise PermissionError('fixture journal is locked')
        return unlink(path,*args,**kwargs)
    class Handler(srv.CodeHandler):
        def log_message(self,*args):pass
    host=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=host.serve_forever);worker.start()
    def call(action=None,body=None):
        url=f'http://127.0.0.1:{host.server_port}/api/project-archive-delete'+('/'+action if action else '')
        request=Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=20) as response:return json.load(response)
    try:
        preview=call('preview',{'scope':GROUP})
        original_delete=srv.CodeHandler.delete_session
        with mock.patch.object(srv.CodeHandler,'delete_session',wraps=original_delete) as delete:
            fault=mock.patch.object(srv,'_remove_owned_archive_tree',side_effect=locked_bundle) if failure=='bundle' else mock.patch.object(Path,'unlink',locked_journal)
            with fault:
                result=call('confirm',preview)
                assert state(result,sid)=='cleanup_pending',result
                assert state(result,ids[1])=='deleted'
                item=next(i for i in result['items'] if i['sessionId']==sid)
                assert item['factsDeleted'] and not item['cleanupComplete'] and item['result']['errorCode']
                assert journal.exists() and bundle.exists()==(failure=='bundle')
                history=call()['data'][0]
                assert state(history,sid)=='cleanup_pending'
                # A stale progress record from the pre-fix candidate is not a
                # substitute for actual copy/journal cleanup evidence.
                stale=s.store.load(preview['operationId'])
                stale['items'][0]['state']='deleted';stale['items'][0]['result']={'errorCode':''}
                s.store.save(stale)
                assert state(call()['data'][0],sid)=='cleanup_pending'
                before=delete.call_count
                assert before==2
                again=call('resume',{'operationId':preview['operationId'],'scope':GROUP,'action':'permanent_delete'})
                assert state(again,sid)=='cleanup_pending' and delete.call_count==before
            assert attempts
            # Once the filesystem fault is gone, the same batch may only clean
            # its original copy/journal. Fact deletion never runs again.
            result=call('resume',{'operationId':preview['operationId'],'scope':GROUP,'action':'permanent_delete'})
            assert all(i['state']=='deleted' and i['cleanupComplete'] for i in result['items'])
            assert delete.call_count==before and not journal.exists() and not bundle.exists()
            proof=s.store.cleanup(s.store.load(preview['operationId']),s.store.load(preview['operationId'])['items'][0])
            assert proof
            assert call('resume',{'operationId':preview['operationId'],'scope':GROUP,'action':'permanent_delete'})==result
            assert delete.call_count==before
    finally:
        host.shutdown();host.server_close();worker.join(timeout=3)
        assert not worker.is_alive()
