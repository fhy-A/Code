"""Explicit isolated child suite; never import server during normal collection."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest import mock

import pytest

if not os.environ.get('CODE_DATA_DIR'):
    raise RuntimeError('Disposable CODE_DATA_DIR required before importing server')

import server as srv
import test_session_persistence as fixtures
from code_runtime.project_archive import ArchiveService, BatchError, _previews, _watched


@pytest.fixture
def setup():
    fixture = fixtures.TestSessionArchiveLifecycle()
    fixture.setUp()
    try:
        with mock.patch.object(srv, 'PROJECTS_PATH', fixture.root / 'projects.json'):
            srv._write_projects([{'id':'fixture-project','label':'Fixture', 'rootPaths':[str(fixture.root)]}])
            yield fixture, ArchiveService(srv)
    finally:
        fixture.doCleanups()


def session(f, **kwargs):
    value = f.create_session(**kwargs)
    f.attach_session_to_project(value['id'], 'fixture-project', f.root)
    return value['id']


def confirm(service, preview):
    return service.execute(preview['operationId'], token=preview['confirmationToken'], action=preview['action'])


def test_cancel_is_memory_only_and_target_set_is_fixed(setup):
    f,s = setup
    sid = session(f)
    preview = s.preview('fixture-project')
    assert preview['total'] == 1 and preview['action'] == 'archive'
    s.store.cancel_preview(preview['operationId'], preview['confirmationToken'])
    assert not s.store.root.exists()
    assert srv.session_path(sid).exists()
    preview = s.preview('fixture-project')
    later = session(f)
    assert confirm(s, preview)['items'][0]['state'] == 'archived'
    assert srv.session_path(later).exists()


@pytest.mark.parametrize('change', ['none','new_run','move_back'])
def test_original_run_progress_survives_human_confirmation_delay(setup, change):
    f,s = setup
    sid = session(f, run_state={'status':'running', 'runtimeRunId':'original-browser-round'})
    run = f.create_active_agent_run(sid)
    preview = s.preview('fixture-project')
    stop = threading.Event()
    writes, failures = [], []
    def output():
        try:
            while not stop.wait(0.04):
                with srv._session_lifecycle_lock(sid), srv._json_write_lock:
                    if srv._session_archive_stop_fence_active(sid):
                        continue
                    meta = srv._read_session_meta_strict(srv.session_path(sid))
                    if meta is None:
                        return
                    meta['revision'] = meta.get('revision',0) + 1
                    meta['runState']['modelRound'] = meta['revision']
                    meta['updatedAt'] = str(time.time())
                    srv.write_json(srv.session_path(sid), meta)
                    with srv.messages_path(sid).open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps({'role':'assistant','content':'isolated streaming output'})+'\n')
                    writes.append(meta['revision'])
        except BaseException as exc:
            failures.append(exc)
    worker = threading.Thread(target=output)
    worker.start()
    try:
        time.sleep(1.5)
        if change == 'new_run':
            f.create_active_agent_run(sid)
        elif change == 'move_back':
            with srv._session_lifecycle_lock(sid), srv._agent_run_lock, srv._json_write_lock:
                f.attach_session_to_project(sid, 'other-project', f.root)
                f.attach_session_to_project(sid, 'fixture-project', f.root)
        time.sleep(1.5)  # Real elapsed human confirmation interval, not a mocked clock.
        result = confirm(s, preview)
    finally:
        stop.set(); worker.join(timeout=3)
    assert not worker.is_alive() and not failures
    assert len(writes) >= 30
    assert result['items'][0]['state'] == ('archived' if change == 'none' else 'conflict'), result
    assert srv._get_agent_run(run['id'])['status'] == ('cancelled' if change == 'none' else 'model')


@pytest.mark.parametrize('change', ['new_run','move_back','restore','queued'])
def test_new_work_or_lifecycle_changes_conflict(setup, change):
    f,s = setup
    sid = session(f)
    preview = s.preview('fixture-project')
    if change == 'new_run':
        run = f.create_active_agent_run(sid)
        srv._cancel_agent_run(run['id'])  # Even a new Run that finished cannot hide admission.
    elif change == 'move_back':
        f.attach_session_to_project(sid, 'other-project', f.root)
        f.attach_session_to_project(sid, 'fixture-project', f.root)
    elif change == 'restore':
        srv._mutate_session_archive_state(sid, archived=True)
        srv._mutate_session_archive_state(sid, archived=False)
    else:
        meta = srv._read_session_meta_strict(srv.session_path(sid))
        meta['runState'] = {'queuedMessages':[{'id':'new-message','status':'pending'}]}
        srv.write_json(srv.session_path(sid), meta)
    result = confirm(s, preview)
    assert result['items'][0]['state'] == 'conflict', result
    assert srv.session_path(sid).exists()


def test_response_loss_restart_restore_never_rearchives(setup):
    f,s = setup
    sid = session(f)
    preview = s.preview('fixture-project')
    assert confirm(s, preview)['items'][0]['state'] == 'archived'
    srv._mutate_session_archive_state(sid, archived=False)
    _previews.clear(); _watched.clear()
    restarted = ArchiveService(srv)
    result = restarted.execute(preview['operationId'], resume=True)
    assert result['items'][0]['state'] == 'archived'
    assert srv.session_path(sid).exists()


def test_partial_failure_retry_excludes_success_and_new_sessions(setup):
    f,s = setup
    ids = sorted([session(f), session(f)])
    preview = s.preview('fixture-project')
    original = srv._mutate_session_archive_state
    def fail(sid, **kwargs):
        if sid == ids[1]:
            raise OSError('isolated archive failure')
        return original(sid, **kwargs)
    with mock.patch.object(srv, '_mutate_session_archive_state', side_effect=fail):
        result = confirm(s, preview)
    assert [i['state'] for i in result['items']] == ['archived','archive_failed']
    session(f)
    retry = s.preview('fixture-project', preview['operationId'])
    assert [i['sessionId'] for i in retry['items']] == [ids[1]]
    assert confirm(s, retry)['items'][0]['state'] == 'archived'


def test_stopped_but_archive_failed_is_distinct(setup):
    f,s = setup
    sid = session(f, run_state={'status':'running'})
    run = f.create_active_agent_run(sid)
    preview = s.preview('fixture-project')
    with mock.patch.object(srv, '_mutate_session_archive_state', side_effect=OSError('fixture')):
        result = confirm(s, preview)
    assert result['items'][0]['state'] == 'stopped_archive_failed'
    assert result['items'][0]['result']['workStopped']
    assert srv._get_agent_run(run['id'])['status'] == 'cancelled'


def test_corrupt_record_fails_closed(setup):
    f,s = setup
    sid = session(f)
    preview = s.preview('fixture-project')
    s.store.path(preview['operationId']).parent.mkdir(parents=True)
    s.store.path(preview['operationId']).write_text('{broken',encoding='utf-8')
    with pytest.raises(BatchError): confirm(s, preview)
    assert srv.session_path(sid).exists()


def test_paused_and_unfinished_goal_preserved(setup):
    f,s = setup
    sid = session(f, run_state={'status':'paused'})
    f.create_active_goal(sid)
    preview = s.preview('fixture-project')
    assert preview['action'] == 'archive'
    assert confirm(s, preview)['items'][0]['state'] == 'archived'


def test_real_streaming_agent_round_delayed_confirmation(setup):
    f,s = setup
    sid = session(f)
    deltas = []
    class StreamingModel(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.end_headers()
            try:
                for index in range(240):
                    self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':' fixture chunk'},'finish_reason':None}]})+'\n\n').encode())
                    self.wfile.flush()
                    deltas.append(index)
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    upstream = ThreadingHTTPServer(('127.0.0.1',0), StreamingModel)
    worker = threading.Thread(target=upstream.serve_forever)
    worker.start()
    run = None
    try:
        run = srv._create_agent_run(sid, {'model':'fixture-model','messages':[{'role':'user','content':'Fixture long output'}]},
            'http://127.0.0.1:'+str(upstream.server_port), ['synthetic-fixture'], allowed_tools=[],
            cwd=str(f.root), start_worker=True)
        deadline = time.monotonic()+5
        while len(deltas)<3 and time.monotonic()<deadline: time.sleep(0.03)
        assert len(deltas)>=3, srv._get_agent_run(run['id']).get('status')
        preview = s.preview('fixture-project')
        assert preview['active'] == 1
        initial = len(deltas)
        time.sleep(3)
        assert len(deltas)-initial >= 30
        result = confirm(s, preview)
        assert result['items'][0]['state'] == 'archived', result
        assert srv._get_agent_run(run['id'])['status'] == 'cancelled'
    finally:
        if run and run.get('worker'):
            srv._cancel_agent_run(run['id'])
            run['worker'].join(timeout=10)
            assert not run['worker'].is_alive()
        upstream.shutdown(); upstream.server_close(); worker.join(timeout=3)
        assert not worker.is_alive()


def test_http_duplicate_confirm_and_refresh(setup):
    f,s = setup
    session(f)
    class Handler(srv.CodeHandler):
        def log_message(self,*args): pass
    host=ThreadingHTTPServer(('127.0.0.1',0), Handler)
    worker=threading.Thread(target=host.serve_forever);worker.start()
    def call(action, body):
        with urlopen(Request('http://127.0.0.1:'+str(host.server_port)+'/api/project-session-archive/'+action,
            data=json.dumps(body).encode(), headers={'Content-Type':'application/json'}), timeout=15) as response:
            return json.load(response)
    try:
        preview=call('preview',{'projectId':'fixture-project'})
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:call('confirm',preview),range(2)))
        assert all(value['items'][0]['state']=='archived' for value in results)
        assert call('resume',{'operationId':preview['operationId']})['items'][0]['state']=='archived'
    finally:
        host.shutdown();host.server_close();worker.join(timeout=3)


def test_crash_after_bundle_commit_recovers_receipt_before_restore(setup):
    f,s=setup
    sid=session(f)
    preview=s.preview('fixture-project')
    original=srv._record_project_archive_effect
    class Crash(BaseException): pass
    with mock.patch.object(srv,'_record_project_archive_effect',side_effect=Crash):
        with pytest.raises(Crash):confirm(s,preview)
    assert srv._session_archive_journal_path(sid).exists()
    _previews.clear();_watched.clear()
    srv._mutate_session_archive_state(sid,archived=False)
    assert srv.session_path(sid).exists()
    assert s.execute(preview['operationId'],resume=True)['items'][0]['state']=='archived'
    assert srv.session_path(sid).exists()


def test_new_run_admission_blocked_during_stop(setup):
    f,s=setup
    sid=session(f)
    original_run=f.create_active_agent_run(sid)
    preview=s.preview('fixture-project')
    cancel=srv._cancel_agent_run
    attempts=[]
    def checked(run_id):
        with pytest.raises(srv.SessionLifecycleConflictError):f.create_active_agent_run(sid)
        attempts.append(run_id)
        return cancel(run_id)
    with mock.patch.object(srv,'_cancel_agent_run',side_effect=checked):
        result=confirm(s,preview)
    assert result['items'][0]['state']=='archived'
    assert attempts==[original_run['id']]


def test_missing_generation_or_completion_receipt_fails_closed(setup):
    f,s=setup
    sid=session(f)
    preview=s.preview('fixture-project')
    assert confirm(s,preview)['items'][0]['state']=='archived'
    item=s.store.load(preview['operationId'])['items'][0]
    s.store.effect_path(preview['operationId'],sid).unlink()
    with pytest.raises(BatchError):s.execute(preview['operationId'],resume=True)
    assert not srv.session_path(sid).exists()


def test_restart_stopping_does_not_repeat_ambiguous_cancellation(setup):
    f,s=setup
    sid=session(f)
    f.create_active_agent_run(sid)
    preview=s.preview('fixture-project')
    class Crash(BaseException):pass
    with mock.patch.object(srv,'_stop_session_agent_runs',side_effect=Crash):
        with pytest.raises(Crash):confirm(s,preview)
    _previews.clear();_watched.clear()
    with mock.patch.object(srv,'_stop_session_agent_runs',side_effect=AssertionError('Repeated stop')):
        result=s.execute(preview['operationId'],resume=True)
    assert result['items'][0]['state']=='uncertain'
    assert srv.session_path(sid).exists()


def test_restart_after_stop_before_archive_continues_without_stopping_again(setup):
    f,s=setup
    sid=session(f)
    f.create_active_agent_run(sid)
    preview=s.preview('fixture-project')
    class Crash(BaseException):pass
    with mock.patch.object(srv,'_clear_session_active_work_state',side_effect=Crash):
        with pytest.raises(Crash):confirm(s,preview)
    _previews.clear();_watched.clear()
    with mock.patch.object(srv,'_stop_session_agent_runs',side_effect=AssertionError('Repeated stop')):
        result=s.execute(preview['operationId'],resume=True)
    assert result['items'][0]['state']=='archived'


def test_first_checkpoint_of_frozen_server_run_is_progress(setup):
    f,s=setup
    sid=session(f)
    run=f.create_active_agent_run(sid)
    preview=s.preview('fixture-project')
    meta=srv._read_session_meta_strict(srv.session_path(sid))
    meta['runState']={'status':'running','executionOwner':'server-agent','agentRunId':run['id'],
                      'runtimeRunId':'first-browser-projection','modelRound':1}
    srv.write_json(srv.session_path(sid),meta)
    assert confirm(s,preview)['items'][0]['state']=='archived'


def test_corrupt_generation_blocks_single_delete_before_core_changes(setup):
    f,s=setup
    sid=session(f)
    s.preview('fixture-project')
    s.store.generation(sid,persist=True)
    s.store.generation_path(sid).write_text('{corrupt',encoding='utf-8')
    before=srv.session_path(sid).read_bytes(),srv.messages_path(sid).read_bytes()
    with pytest.raises(srv.SessionDeleteError):
        srv.CodeHandler.delete_session(f.make_handler(),sid)
    assert before==(srv.session_path(sid).read_bytes(),srv.messages_path(sid).read_bytes())
