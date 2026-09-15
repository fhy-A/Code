"""Fresh-process delete recovery and R002 replacement-file counterexamples."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path(os.environ['CODE_DATA_DIR']).resolve()
CASE_ROOT = PROFILE.parent
assert CASE_ROOT.parent == Path(tempfile.gettempdir()).resolve()
assert CASE_ROOT.name.startswith('code072-delete-process-') and PROFILE.name == 'data'
PHASE, CASE = sys.argv[1:]
ALL_SCOPE = os.environ.get('CODE108_ALL_SCOPE') == '1'
assert PHASE in {'seed','recover'}
assert (ALL_SCOPE and CASE == 'capture') or CASE in {'partial','facts_deleted','effect','prepared','core_restored'} or CASE.startswith(('prepared_','core_restored_','cleanup_'))
GROUP = {'kind':'all'} if ALL_SCOPE else {'kind':'project','projectId':'process-project'}
ACTION = 'permanent_delete_all' if ALL_SCOPE else 'permanent_delete'


def guard(event,args):
    if event in {'socket.bind','socket.connect'}:
        raise AssertionError('Delete recovery fixture forbids network/listener access')
    if event in {'open','os.listdir','os.scandir'} and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        if path == ROOT/'data' or ROOT/'data' in path.parents:
            raise AssertionError('Delete recovery fixture accessed real data')


sys.addaudithook(guard)
sys.path.insert(0,str(ROOT))
assert 'server' not in sys.modules
import server as srv
from code_runtime.project_archive import _previews, _watched
from code_runtime.project_archive_delete import DeleteService
assert srv.DATA_DIR.resolve() == PROFILE and not _previews and not _watched and not srv._agent_runs
srv._ensure_agent_run_nonterminal_index_ready(wait=True)
srv._ensure_agent_run_session_index_ready(wait=True)
SERVICE = DeleteService(srv)
HANDOFF = CASE_ROOT/'handoff.json'


def write(path,value):
    with path.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())


def file_fact(path):
    if not path.exists():return None
    info = path.stat()
    return {'hash':hashlib.sha256(path.read_bytes()).hexdigest(),'size':info.st_size,
            'mtime':info.st_mtime_ns,'ctime':info.st_ctime_ns,'inode':info.st_ino}


def core(sid):
    return {'session':file_fact(srv.session_path(sid)),'messages':file_fact(srv.messages_path(sid))}


if PHASE == 'seed':
    project = CASE_ROOT/'project';project.mkdir()
    srv.write_json(srv.CONFIG_PATH,{'projectRoot':str(project)})
    srv._write_projects([{'id':'process-project','label':'Process fixture','rootPaths':[str(project)]}])
    ids = []
    for index in range(2 if CASE == 'partial' else 1):
        handler = object.__new__(srv.CodeHandler)
        handler.read_body_json = mock.Mock(return_value={'title':f'Delete fixture {index}','projectId':'process-project',
            'cwd':str(project),'messages':[{'role':'user','content':'original archived content'}]})
        handler.send_json = mock.Mock();srv.CodeHandler.create_session(handler)
        sid = handler.send_json.call_args.args[0]['id'];ids.append(sid)
        srv._mutate_session_archive_state(sid,archived=True)
    ids.sort()
    if ALL_SCOPE:
        import uuid
        preview = {'operationId':uuid.uuid4().hex,'confirmationToken':uuid.uuid4().hex+uuid.uuid4().hex}
    else:
        preview = SERVICE.preview(GROUP)
    op = preview['operationId']
    def confirm_operation():
        if ALL_SCOPE:
            return SERVICE.confirm_all(op,GROUP,ACTION,preview['confirmationToken'],SERVICE.store.identity)
        return SERVICE.execute(op,GROUP,ACTION,token=preview['confirmationToken'])
    evidence = {'case':CASE,'processA':os.getpid(),'operationId':op,'sessionIds':ids,
                'freshRegistriesA':True,'networkListenersOpened':0,'connectionsOpened':0,'allScope':ALL_SCOPE,'confirmationToken':preview['confirmationToken']}
    def crash():
        value = SERVICE.store.load(op,allow_preview=False)
        evidence['statesAtExit'] = [i['state'] for i in value['items']]
        journal = srv._read_session_archive_journal(ids[-1])
        evidence['journalAtExit'] = journal
        write(HANDOFF,evidence)
        os._exit(73)
    if CASE == 'capture':
        SERVICE.capture_all = crash
    elif CASE == 'partial':
        original = SERVICE.execute_item
        def before_second(value,item):
            if item['target']['id'] == ids[1]:
                evidence['firstEffect'] = file_fact(SERVICE.store.effect_path(op,ids[0]))
                assert [i['state'] for i in SERVICE.store.load(op)['items']] == ['deleted','pending']
                crash()
            return original(value,item)
        SERVICE.execute_item = before_second
    elif CASE in {'facts_deleted','effect'}:
        original = srv._record_project_archive_delete_effect
        def receipt_boundary(journal):
            assert journal['state'] == 'facts_deleted'
            assert not srv.session_path(ids[0]).exists() and not srv.messages_path(ids[0]).exists()
            if CASE == 'effect':original(journal)
            assert SERVICE.store.effect_path(op,ids[0]).exists() == (CASE == 'effect')
            crash()
        srv._record_project_archive_delete_effect = receipt_boundary
    elif CASE.startswith('cleanup_'):
        original_tree, original_unlink = srv._remove_owned_archive_tree, Path.unlink
        def cleanup_tree(path):
            if path == srv._session_archive_bundle_path(ids[0]) and CASE in {'cleanup_bundle','cleanup_replaced'}:
                raise PermissionError('Deterministic original bundle cleanup failure')
            return original_tree(path)
        def cleanup_unlink(path,*args,**kwargs):
            if path == srv._session_archive_journal_path(ids[0]):
                if CASE == 'cleanup_journal':
                    raise PermissionError('Deterministic original journal cleanup failure')
                if CASE == 'cleanup_journal_unlinked':
                    original_unlink(path,*args,**kwargs)
                    assert SERVICE.store.cleanup_path(op,ids[0]).exists()
                    crash()
            return original_unlink(path,*args,**kwargs)
        srv._remove_owned_archive_tree, Path.unlink = cleanup_tree, cleanup_unlink
        result = confirm_operation()
        assert result['items'][0]['state'] == 'cleanup_pending',result
        assert result['items'][0]['factsDeleted'] and not result['items'][0]['cleanupComplete']
        assert result['items'][0]['result']['errorCode']
        evidence['pendingResultA'] = result
        crash()
    else:
        boundary = 'core_restored' if CASE.startswith('core_restored') else 'prepared'
        original = srv._write_session_archive_journal
        def journal_boundary(sid,payload):
            journal = original(sid,payload)
            if journal['action'] == 'delete' and journal['state'] == boundary:crash()
            return journal
        srv._write_session_archive_journal = journal_boundary
    confirm_operation()
    raise AssertionError('Expected abrupt exit was not reached')


evidence = json.loads(HANDOFF.read_text(encoding='utf-8'))
assert evidence['processA'] != os.getpid()
op, ids = evidence['operationId'], evidence['sessionIds']
sid = ids[-1]
if CASE == 'capture':
    original = SERVICE.capture_all
    def recapture():raise AssertionError('Old confirmation attempted a new inventory')
    SERVICE.capture_all = recapture
    result = SERVICE.confirm_all(op,GROUP,ACTION,evidence['confirmationToken'],SERVICE.store.identity)
    assert result['captureState'] == 'capturing' and result['items'] == []
    assert all(srv._session_archive_bundle_path(i).exists() for i in ids)
    evidence.update(processB=os.getpid(),freshRegistriesB=True,realProcessRestart=True,passed=True,
                    interruptedCapturePreserved=True)
    write(CASE_ROOT/'result.json',evidence)
    print(json.dumps(evidence,ensure_ascii=False))
    sys.exit(0)
negative = not CASE.startswith('cleanup_') and CASE not in {'partial','facts_deleted','effect','prepared','core_restored'}
cleanup_calls = []
if CASE.startswith('cleanup_'):
    original_tree, original_unlink = srv._remove_owned_archive_tree, Path.unlink
    def cleanup_tree(path):
        if path == srv._session_archive_bundle_path(sid):cleanup_calls.append('bundle')
        return original_tree(path)
    def cleanup_unlink(path,*args,**kwargs):
        if path == srv._session_archive_journal_path(sid):cleanup_calls.append('journal')
        return original_unlink(path,*args,**kwargs)
    srv._remove_owned_archive_tree, Path.unlink = cleanup_tree, cleanup_unlink
if CASE == 'cleanup_replaced':
    import uuid
    manifest_path = srv._session_archive_bundle_path(sid)/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['archiveToken'] = uuid.uuid4().hex
    write(manifest_path,manifest)
    replacement_before = file_fact(manifest_path)
    journal_before = file_fact(srv._session_archive_journal_path(sid))
if negative:
    # Independently rebuild/change a core file after process A has exited.
    # Copying bytes+mtime still produces a different file identity.
    field = 'session' if CASE.endswith('session') else 'messages'
    path = srv.session_path(sid) if field == 'session' else srv.messages_path(sid)
    source = srv._session_archive_bundle_path(sid)/('session.json' if field == 'session' else 'messages.jsonl')
    if '_rebuild_' in CASE:
        payload = source.read_bytes()
        mtime = evidence['journalAtExit'].get('activeFiles',{}).get(field,{}).get('mtimeNs',source.stat().st_mtime_ns)
        path.unlink(missing_ok=True);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
        os.utime(path,ns=(mtime,mtime))
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'{"id":"new-object","content":"DO NOT OVERWRITE OR DELETE"}\n')
    before = core(sid)
    journal_before = file_fact(srv._session_archive_journal_path(sid))
calls = []
original = srv.CodeHandler.delete_session
def delete(self,target,**kwargs):
    calls.append(target)
    if negative or CASE in {'facts_deleted','effect'} or CASE.startswith('cleanup_'):
        raise AssertionError('Recovery repeated deletion or touched a replacement object')
    return original(self,target,**kwargs)
srv.CodeHandler.delete_session = delete
result = SERVICE.execute(op,GROUP,ACTION,resume=True)
if CASE == 'cleanup_replaced':
    assert result['items'][0]['state'] == 'cleanup_pending',result
    assert result['items'][0]['result']['errorCode'] == 'archive_delete_cleanup_conflict',result
    assert calls == [] and cleanup_calls == []
    assert file_fact(manifest_path) == replacement_before
    assert file_fact(srv._session_archive_journal_path(sid)) == journal_before
    evidence['replacementArchivePreserved'] = True
elif negative:
    assert result['items'][-1]['state'] == 'uncertain',result
    assert result['items'][-1]['result']['errorCode'] == 'archive_delete_recovery_conflict',result
    assert calls == [] and core(sid) == before
    assert file_fact(srv._session_archive_journal_path(sid)) == journal_before
    assert not SERVICE.store.effect_path(op,sid).exists()
    evidence['replacementCorePreserved'] = before
else:
    assert all(i['state'] == 'deleted' for i in result['items']),result
    assert all(not srv._session_archive_journal_path(i).exists() for i in ids)
    assert all(not srv._session_archive_bundle_path(i).exists() for i in ids)
    assert calls == ([ids[-1]] if CASE in {'partial','prepared','core_restored'} else []),calls
    if CASE.startswith('cleanup_'):
        expected = ['bundle','journal'] if CASE == 'cleanup_bundle' else ['journal'] if CASE == 'cleanup_journal' else []
        assert cleanup_calls == expected,cleanup_calls
        evidence['cleanupCallsB'] = list(cleanup_calls)
    if CASE == 'partial':assert file_fact(SERVICE.store.effect_path(op,ids[0])) == evidence['firstEffect']
    # A later object with the same ID must survive old confirmation/reload.
    srv._mark_session_created(sid)
    srv.write_json(srv.session_path(sid),{'id':sid,'title':'Rebuilt after delete','projectId':'process-project','cwd':str(CASE_ROOT/'project')})
    srv.write_jsonl(srv.messages_path(sid),[{'role':'user','content':'new incarnation'}])
    srv._mutate_session_archive_state(sid,archived=True)
    new_archive = file_fact(srv._session_archive_bundle_path(sid)/'manifest.json')
    before_calls = list(calls)
    assert all(i['state'] == 'deleted' for i in SERVICE.execute(op,GROUP,ACTION,resume=True)['items'])
    assert calls == before_calls and file_fact(srv._session_archive_bundle_path(sid)/'manifest.json') == new_archive
    evidence['rebuiltArchivePreserved'] = True
evidence.update(processB=os.getpid(),freshRegistriesB=True,realProcessRestart=True,deleteCallsB=calls,passed=True)
write(CASE_ROOT/'result.json',evidence)
print(json.dumps(evidence,ensure_ascii=False))
