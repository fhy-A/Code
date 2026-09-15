"""Fixed all-project consent, ownership, old protocol and failure counterexamples."""
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
assert Path(os.environ['CODE_DATA_DIR']).parent.name.startswith('code108-all-cases-')


def guard(event, args):
    if event in {'open', 'os.listdir', 'os.scandir'} and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        assert path != ROOT/'data' and ROOT/'data' not in path.parents, 'Real data access forbidden'


sys.addaudithook(guard)
from project_archive_delete_cases import setup, make, state, confirm, GROUP
import server as srv
from code_runtime.project_archive import BatchError
from code_runtime.project_archive_delete import DeleteService

ALL = {'kind': 'all'}
ACTION = 'permanent_delete_all'


def intent():
    return uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex


def admit(service):
    op, token = intent()
    with mock.patch.object(service, 'execute_item'):
        result = service.confirm_all(op, ALL, ACTION, token, service.store.identity)
    return op, token, result


def test_all_groups_preserve_active_workspace_projects_and_shared_upload(setup):
    f, s = setup
    ids = [make(f, pid) for pid in ('delete-project', 'other-project', 'historical', None)]
    active = make(f, archived=False)
    sentinel = f.root/'workspace.txt'; sentinel.write_bytes(b'keep')
    shared = f.root/'attachments'; shared.mkdir(); (shared/'keep.bin').write_bytes(b'shared')
    catalog = srv.PROJECTS_PATH.read_bytes()
    op, token = intent(); result = s.confirm_all(op, ALL, ACTION, token, s.store.identity)
    assert {i['sessionId'] for i in result['items']} == set(ids)
    assert all(i['state'] == 'deleted' and i['cleanupComplete'] for i in result['items'])
    assert srv.session_path(active).exists() and sentinel.read_bytes() == b'keep'
    assert (shared/'keep.bin').read_bytes() == b'shared' and srv.PROJECTS_PATH.read_bytes() == catalog
    assert s.store.load(op)['schema'] == 'code-project-archive-delete/v2'
    with mock.patch.object(srv.CodeHandler, 'delete_session', side_effect=AssertionError('replay')):
        assert s.confirm_all(op, ALL, ACTION, token, s.store.identity) == result


@pytest.mark.parametrize('scope,action', [(None,ACTION), ({},ACTION), (GROUP,ACTION), (ALL,'permanent_delete'), ({'kind':'all','projectId':''},ACTION)])
def test_explicit_scope_and_action_required(setup, scope, action):
    f, s = setup; sid = make(f); op, token = intent()
    with pytest.raises(BatchError): s.confirm_all(op, scope, action, token, s.store.identity)
    assert not s.store.path(op).exists() and srv._session_archive_bundle_path(sid).exists()


def test_group_and_all_tokens_cannot_be_interchanged(setup):
    f, s = setup; sid = make(f); preview = s.preview(GROUP)
    op, token, _ = admit(s)
    for call in [lambda: s.confirm_all(preview['operationId'],ALL,ACTION,preview['confirmationToken'], s.store.identity),
                 lambda: s.execute(op,GROUP,'permanent_delete',token=token),
                 lambda: s.confirm_all(op,ALL,ACTION,preview['confirmationToken'], s.store.identity),
                 lambda: s.execute(preview['operationId'],ALL,ACTION,token=token),
                 lambda: s.preview(ALL)]:
        with pytest.raises(BatchError): call()
    s.store.cancel_preview(preview['operationId'],preview['confirmationToken'])
    assert srv._session_archive_bundle_path(sid).exists()


def test_new_archive_and_rearchived_same_id_excluded_even_on_retry(setup):
    f, s = setup; original = make(f); stable = make(f,'other-project')
    op, token, _ = admit(s)
    srv._mutate_session_archive_state(original,archived=False)
    srv._mutate_session_archive_state(original,archived=True)
    before = (srv._session_archive_bundle_path(original)/'manifest.json').read_bytes()
    later = make(f,None)
    result = s.confirm_all(op,ALL,ACTION,token, s.store.identity)
    assert state(result,original) == 'conflict' and state(result,stable) == 'deleted'
    assert later not in {i['sessionId'] for i in result['items']}
    assert s.execute(op,ALL,ACTION,resume=True) == result
    assert (srv._session_archive_bundle_path(original)/'manifest.json').read_bytes() == before
    assert srv._session_archive_bundle_path(later).exists()


def test_interrupted_capture_never_enumerates_again(setup):
    f, s = setup; original = make(f); op, token = intent()
    with mock.patch.object(s,'capture_all',side_effect=SystemExit('crash after reservation')):
        with pytest.raises(SystemExit): s.confirm_all(op,ALL,ACTION,token, s.store.identity)
    later = make(f)
    fresh = DeleteService(srv)
    with mock.patch.object(fresh,'capture_all',side_effect=AssertionError('recapture')):
        result = fresh.confirm_all(op,ALL,ACTION,token, fresh.store.identity)
    assert result['captureState'] == 'capturing' and result['items'] == []
    assert all(srv._session_archive_bundle_path(sid).exists() for sid in [original,later])


def test_invalid_inventory_preserves_reservation_and_deletes_nothing(setup):
    f, s = setup; sid = make(f); op, token = intent()
    with mock.patch.object(s,'snapshot',side_effect=BatchError('archive_delete_target_changed','conflict')):
        result = s.confirm_all(op,ALL,ACTION,token, s.store.identity)
    assert result['captureState'] == 'failed' and result['captureError'] == 'archive_delete_target_changed'
    with mock.patch.object(s,'capture_all',side_effect=AssertionError('recapture')):
        assert s.confirm_all(op,ALL,ACTION,token, s.store.identity) == result
    assert srv._session_archive_bundle_path(sid).exists()


def test_partial_failure_resume_uses_same_targets_and_keeps_receipts(setup):
    f, s = setup; first = make(f); second = make(f,None); op, token, _ = admit(s)
    original = srv.CodeHandler.delete_archived_session
    def fail(handler,sid,*args,**kwargs):
        if sid == second: raise PermissionError('fixture denied')
        return original(handler,sid,*args,**kwargs)
    with mock.patch.object(srv.CodeHandler,'delete_archived_session',fail):
        result = s.confirm_all(op,ALL,ACTION,token, s.store.identity)
    assert state(result,first) == 'deleted' and state(result,second) == 'failed'
    effect = s.store.effect_path(op,first).read_bytes(); later = make(f)
    result = s.execute(op,ALL,ACTION,resume=True)
    assert all(i['state'] == 'deleted' for i in result['items'])
    assert s.store.effect_path(op,first).read_bytes() == effect and srv._session_archive_bundle_path(later).exists()


def test_simultaneous_group_and_all_have_one_fact_owner(setup):
    f, s = setup; sid = make(f); foreign = make(f,'other-project'); preview = s.preview(GROUP)
    op, token, _ = admit(s)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(s.confirm_all,op,ALL,ACTION,token,s.store.identity)
        b = pool.submit(confirm,s,preview)
        results = [a.result(),b.result()]
    assert sum(state(r,sid) == 'deleted' for r in results) == 1
    assert state(results[0],foreign) == 'deleted'
    assert sum(s.store.effect_path(v,sid).exists() for v in [op,preview['operationId']]) == 1


def test_duplicate_concurrent_all_requests_use_one_operation(setup):
    f, s = setup; sid = make(f); op, token = intent()
    def request(_):
        try: return s.confirm_all(op,ALL,ACTION,token,s.store.identity)
        except BatchError as exc:
            assert exc.code == 'project_archive_busy' and exc.status == 503
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, range(2)))
    assert any(r is not None and state(r,sid) == 'deleted' for r in results)
    for r in results:
        if r is None: r = s.confirm_all(op,ALL,ACTION,token,s.store.identity)
        assert state(r,sid) == 'deleted'
    assert [v['operationId'] for v in s.store.list(ALL)] == [op]


def test_old_reader_refuses_v2_but_old_group_remains_compatible(setup):
    f, s = setup; make(f); group = s.preview(GROUP)
    s.store.confirm(group['operationId'],group['confirmationToken'],'permanent_delete')
    op, token, _ = admit(s)
    source = (ROOT/'tests/fixtures/archive_delete_v1_reader.py').read_text(encoding='utf-8')
    namespace = {'__name__':'legacy_delete'}
    exec(compile(source,'legacy_delete.py','exec'),namespace)
    old = namespace['LegacyDeleteStore'](s.store.root)
    assert old.load(group['operationId'])['scope'] == GROUP
    before = s.store.path(op).read_bytes()
    with pytest.raises(BatchError): old.load(op)
    with pytest.raises(BatchError): old.list()
    assert s.store.path(op).read_bytes() == before
    assert s.store.load(group['operationId'])['schema'] == 'code-project-archive-delete/v1'
    corrupt = s.store.load(op); corrupt['schema']='code-project-archive-delete/v999'
    s.store.atomic(s.store.path(op),corrupt)
    with pytest.raises(BatchError): s.execute(op,ALL,ACTION,resume=True)


@pytest.mark.parametrize('context', [None, '', 'f'*64])
def test_wrong_data_root_cannot_authorize_new_all_operation(setup, context):
    f, s = setup; sid = make(f); op, token = intent()
    with pytest.raises(BatchError): s.confirm_all(op,ALL,ACTION,token,context)
    assert not s.store.path(op).exists() and srv._session_archive_bundle_path(sid).exists()


def test_empty_all_confirmation_is_complete_without_deletion(setup):
    f, s = setup; op, token = intent()
    with mock.patch.object(srv.CodeHandler,'delete_archived_session',side_effect=AssertionError('empty delete')):
        result = s.confirm_all(op,ALL,ACTION,token,s.store.identity)
        assert result['captureState'] == 'ready' and result['confirmed'] and result['items'] == []
        assert s.execute(op,ALL,ACTION,resume=True) == result
