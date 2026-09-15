"""R004 child driver: real interpreter exit/restart, never an in-process reset.

This file is invoked only by test_project_archive_process.py. Process A exits
with os._exit at a durable boundary; process B imports server from scratch.
"""
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
assert CASE_ROOT.name.startswith('code072-process-') and PROFILE.name == 'data'
assert len(sys.argv) == 3 and sys.argv[1] in {'seed', 'recover'}
PHASE, CASE = sys.argv[1:]
assert CASE in {'partial', 'stopped', 'bundle'}


def io_guard(event, args):
    if event in {'socket.bind', 'socket.connect'}:
        raise AssertionError('Process recovery fixture must not open listeners or network connections')
    if event in {'open', 'os.listdir', 'os.scandir'} and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        protected = ROOT / 'data'
        if path == protected or protected in path.parents:
            raise AssertionError('Process recovery fixture accessed real product data')


sys.addaudithook(io_guard)
sys.path.insert(0, str(ROOT))
assert 'server' not in sys.modules
import server as srv
from code_runtime.project_archive import ArchiveService, _previews, _watched

assert srv.DATA_DIR.resolve() == PROFILE
assert not _previews and not _watched and not srv._agent_runs
SERVICE = ArchiveService(srv)
HANDOFF = CASE_ROOT / 'handoff.json'


def write_fact(path, value):
    with path.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def file_fact(path):
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes':path.stat().st_size, 'mtimeNs':path.stat().st_mtime_ns}


def core_facts(sid):
    return {'session':file_fact(srv.session_path(sid)), 'messages':file_fact(srv.messages_path(sid))}


def archive_facts(sid, op):
    bundle = srv._session_archive_bundle_path(sid)
    return {name:file_fact(bundle / name) for name in ('session.json','messages.jsonl','manifest.json')} | {
        'effect':file_fact(SERVICE.store.effect_path(op,sid))}


def assert_state(op, expected):
    record = SERVICE.store.load(op, allow_preview=False)
    actual = [item['state'] for item in record['items']]
    assert actual == expected, (actual, expected)
    return record


if PHASE == 'seed':
    project_root = CASE_ROOT / 'project'
    project_root.mkdir()
    srv.write_json(srv.CONFIG_PATH, {'projectRoot':str(project_root)})
    srv._write_projects([{'id':'process-project','label':'Process fixture','rootPaths':[str(project_root)]}])
    ids = []
    for index in range(2 if CASE == 'partial' else 1):
        handler = object.__new__(srv.CodeHandler)
        handler.read_body_json = mock.Mock(return_value={
            'title':f'Process fixture {index}', 'projectId':'process-project', 'cwd':str(project_root),
            'messages':[{'role':'user','content':'Disposable process-boundary fixture'}],
        })
        handler.send_json = mock.Mock()
        srv.CodeHandler.create_session(handler)
        ids.append(handler.send_json.call_args.args[0]['id'])
    ids.sort()
    run = None
    if CASE == 'stopped':
        # A real durable Run admission/cancel path, with no worker/model needed
        # for this persistence boundary. The child cannot open network sockets.
        run = srv._create_agent_run(ids[0], {'model':'fixture','messages':[{'role':'user','content':'fixture'}]},
            'http://127.0.0.1:9', ['synthetic-only'], allowed_tools=[],
            cwd=str(project_root), start_worker=False)
    preview = SERVICE.preview('process-project')
    op = preview['operationId']
    fact = {'case':CASE,'processA':os.getpid(),'operationId':op,'sessionIds':ids,
            'activeCoreBefore':{sid:core_facts(sid) for sid in ids},
            'initialRegistriesEmpty':True,'networkListenersOpened':0,'connectionsOpened':0}

    def crash_at_boundary():
        fact['stateBeforeExit'] = [i['state'] for i in SERVICE.store.load(op,allow_preview=False)['items']]
        write_fact(HANDOFF, fact)
        os._exit(73)  # Deliberately bypass Python cleanup and lose all process memory.

    if CASE == 'partial':
        original = SERVICE.execute_item
        def before_second(value, item):
            if item['target']['id'] == ids[1]:
                assert_state(op,['archived','pending'])
                fact['completedArchiveBefore'] = archive_facts(ids[0],op)
                assert srv.session_path(ids[1]).exists()
                assert not SERVICE.store.effect_path(op,ids[1]).exists()
                crash_at_boundary()
            return original(value,item)
        SERVICE.execute_item = before_second
    elif CASE == 'stopped':
        def after_durable_stop(sid, **kwargs):
            assert_state(op,['stopped'])
            run_path = srv._agent_run_path(run['id'])
            assert json.loads(run_path.read_text(encoding='utf-8'))['status'] == 'cancelled'
            assert not SERVICE.store.effect_path(op,sid).exists()
            fact['runId'] = run['id']
            fact['terminalRunBefore'] = file_fact(run_path)
            crash_at_boundary()
        srv._clear_session_active_work_state = after_durable_stop
    else:
        def after_bundle_before_receipt(journal, manifest):
            assert_state(op,['archiving'])
            sid = ids[0]
            assert srv._read_session_archive_journal(sid)['state'] == 'bundle_committed'
            assert srv._session_archive_bundle_path(sid).exists()
            assert not SERVICE.store.effect_path(op,sid).exists()
            assert not srv.session_path(sid).exists()
            fact['committedArchiveToken'] = manifest['archiveToken']
            fact['journalBeforeExit'] = file_fact(srv._session_archive_journal_path(sid))
            crash_at_boundary()
        srv._record_project_archive_effect = after_bundle_before_receipt
    SERVICE.execute(op, token=preview['confirmationToken'], action=preview['action'])
    raise AssertionError('The intended process crash boundary was not reached')


fact = json.loads(HANDOFF.read_text(encoding='utf-8'))
assert fact['case'] == CASE and fact['processA'] != os.getpid()
op, ids = fact['operationId'], fact['sessionIds']
assert_state(op, fact['stateBeforeExit'])
calls = []
mutate = srv._mutate_session_archive_state


def tracked_mutation(sid, **kwargs):
    calls.append({'sessionId':sid,'archived':kwargs['archived']})
    return mutate(sid,**kwargs)


def forbidden_stop(*args, **kwargs):
    raise AssertionError('A new interpreter repeated an already completed stop')


srv._mutate_session_archive_state = tracked_mutation
srv._stop_session_agent_runs = forbidden_stop
srv._cancel_agent_run = forbidden_stop
if CASE == 'partial':
    assert archive_facts(ids[0],op) == fact['completedArchiveBefore']
    result = SERVICE.execute(op,resume=True)
    assert calls == [{'sessionId':ids[1],'archived':True}], calls
    assert archive_facts(ids[0],op) == fact['completedArchiveBefore']
elif CASE == 'stopped':
    run_path = srv._agent_run_path(fact['runId'])
    assert json.loads(run_path.read_text(encoding='utf-8'))['status'] == 'cancelled'
    result = SERVICE.execute(op,resume=True)
    assert calls == [{'sessionId':ids[0],'archived':True}], calls
    assert file_fact(run_path) == fact['terminalRunBefore'], 'The persisted terminal Run was rewritten'
else:
    sid = ids[0]
    with SERVICE.target_lock(sid):
        srv._recover_session_archive_transaction(sid)
    record = SERVICE.store.load(op,allow_preview=False)
    effect = SERVICE.store.effect(record,record['items'][0])
    assert effect and effect['archiveToken'] == fact['committedArchiveToken']
    assert not srv._session_archive_journal_path(sid).exists()
    srv._mutate_session_archive_state(sid,archived=False)
    restored = core_facts(sid)
    assert restored == fact['activeCoreBefore'][sid], 'Restored bytes/mtime changed'
    proof = file_fact(SERVICE.store.effect_path(op,sid))
    result = SERVICE.execute(op,resume=True)
    assert calls == [{'sessionId':sid,'archived':False}], calls
    assert core_facts(sid) == restored
    assert file_fact(SERVICE.store.effect_path(op,sid)) == proof

assert all(item['state'] == 'archived' for item in result['items'])
before_replay = list(calls)
assert SERVICE.execute(op,resume=True)['items'] == result['items']
assert calls == before_replay, 'Repeated resume replayed a completed effect'
assert all(not srv._session_archive_journal_path(sid).exists() for sid in ids)
if CASE == 'bundle':
    assert core_facts(ids[0]) == fact['activeCoreBefore'][ids[0]]
evidence = {**fact,'processB':os.getpid(),'newInterpreter':True,'freshRegistriesBeforeRecovery':True,
            'mutationCallsInB':calls,'completedReplayHadNoMutations':True,'passed':True}
write_fact(CASE_ROOT / 'result.json',evidence)
print(json.dumps(evidence,ensure_ascii=False))
