"""Durable fixed-target project archive batches; no Session or workspace I/O.

The server supplies lifecycle-locked snapshots and performs the actual work.
Previews are memory-only: cancel/restart before confirmation has no disk effect.
Effects are immutable completion facts, separate from mutable batch progress.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid


class BatchError(ValueError):
    def __init__(self, code, message, status=409):
        self.code, self.status = code, status
        super().__init__(message)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise BatchError('project_archive_invalid_id', 'Invalid batch identity.', 400)
    return value


def session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', value):
        raise BatchError('project_archive_invalid_state', 'Invalid Session identity.')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


_mutexes = {}
_guard = threading.Lock()
_previews = {}
_watched = {}
ITEM_STATES = frozenset({'pending', 'stopping', 'stopped', 'archiving', 'archived',
    'conflict', 'stop_failed', 'stopped_archive_failed', 'archive_failed', 'uncertain'})
RETRYABLE = frozenset({'conflict', 'stop_failed', 'stopped_archive_failed', 'archive_failed'})


class BatchStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.identity = digest(os.path.normcase(str(self.root)))

    def generation_path(self, sid):
        return self.owned(self.root / 'generations' / (session_id(sid) + '.json'))

    def generation(self, sid, *, watch=False, persist=False):
        key = (self.identity, sid)
        with _guard:
            path = self.generation_path(sid)
            if path.exists():
                fact = self.read_json(path)
                if set(fact) != {'sessionId', 'generation'} or fact['sessionId'] != sid:
                    raise BatchError('project_archive_invalid_state', 'Lifecycle identity is invalid.')
                value = identifier(fact['generation'])
            else:
                value = _watched.get(key)
                if value is None and (watch or persist):
                    value = uuid.uuid4().hex
            if watch or persist:
                _watched[key] = value
            if persist:
                self.atomic(path, {'sessionId':sid, 'generation':value})
            return value

    def bump(self, sid):
        # Call before the lifecycle mutation, while holding its existing lock.
        # An unconfirmed preview never creates durable files.
        key = (self.identity, sid)
        with _guard:
            path = self.generation_path(sid)
            durable = path.exists()
            if not durable and key not in _watched:
                return
            value = uuid.uuid4().hex
            if durable:
                fact = self.read_json(path)  # Corruption must not be overwritten.
                if set(fact) != {'sessionId','generation'} or fact['sessionId'] != sid:
                    raise BatchError('project_archive_invalid_state', 'Lifecycle identity is invalid.')
                identifier(fact['generation'])
                self.atomic(path, {'sessionId':sid, 'generation':value})
            _watched[key] = value

    @staticmethod
    def plain(path):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise BatchError('project_archive_invalid_state', 'Batch state cannot follow links.')
        if path.is_file() and path.stat().st_nlink > 1:
            raise BatchError('project_archive_invalid_state', 'Batch state cannot use linked files.')
        return path

    def owned(self, path):
        if self.root not in path.parents and path != self.root:
            raise BatchError('project_archive_invalid_state', 'Batch path escaped its data root.')
        for parent in (path, *path.parents):
            self.plain(parent)
        return path

    def path(self, operation_id):
        return self.owned(self.root / 'operations' / (identifier(operation_id) + '.json'))

    def atomic(self, path, value):
        self.owned(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
        data = {**value, 'digest': digest(value)}
        try:
            with temporary.open('xb') as stream:
                stream.write(json.dumps(data, ensure_ascii=False, sort_keys=True).encode())
                stream.flush()
                os.fsync(stream.fileno())
            self.owned(path)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def read_json(self, path):
        self.owned(path)
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            checksum = value.pop('digest')
            if not hmac.compare_digest(checksum, digest(value)):
                raise ValueError('checksum')
            return value
        except Exception as exc:
            raise BatchError('project_archive_invalid_state', 'Batch state is damaged; no operation was started.') from exc

    @contextlib.contextmanager
    def locked(self, project_id):
        key = (self.identity, str(project_id))
        with _guard:
            lock = _mutexes.setdefault(key, threading.RLock())
        if not lock.acquire(timeout=1):
            raise BatchError('project_archive_busy', 'Another batch for this project is running.', 503)
        try:
            # The application already owns its data root across processes.
            # This lock serializes independent HTTP requests in that owner.
            yield
        finally:
            lock.release()

    def preview(self, project_id, project_version, targets, *, retry_of=None):
        operation_id, token = uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
        items = []
        for target in targets:
            items.append({'target': target, 'state': 'pending', 'result': None,
                          'archiveToken': digest([operation_id, target['id']])[:32]})
        value = {'schema': 'code-project-session-archive/v1', 'dataRoot': self.identity,
                 'operationId': operation_id, 'projectId': project_id,
                 'projectVersion': project_version, 'createdAt': time.time(),
                 'confirmedAt': None, 'action': 'stop_and_archive' if any(t['active'] for t in targets) else 'archive',
                 'confirmationHash': digest(token), 'retryOf': retry_of, 'items': items}
        self.validate(value)
        with _guard:
            expired = [key for key, val in _previews.items() if time.time() - val['createdAt'] > 600]
            for key in expired:
                _previews.pop(key, None)
            _previews[(self.identity, operation_id)] = value
        return json.loads(json.dumps(value)), token

    def validate(self, value):
        expected = {'schema','dataRoot','operationId','projectId','projectVersion','createdAt',
                    'confirmedAt','action','confirmationHash','retryOf','items'}
        if (not isinstance(value, dict) or set(value) != expected
                or value['schema'] != 'code-project-session-archive/v1' or value['dataRoot'] != self.identity
                or value['action'] not in {'archive','stop_and_archive'}
                or not isinstance(value['projectId'], str) or not value['projectId']
                or not isinstance(value['items'], list)
                or type(value['createdAt']) not in (int, float)
                or not 0 < value['createdAt'] < float('inf')
                or (value['confirmedAt'] is not None and (type(value['confirmedAt']) not in (int, float)
                    or not value['createdAt'] <= value['confirmedAt'] < float('inf')))):
            raise BatchError('project_archive_invalid_state', 'Batch contract is invalid.')
        identifier(value['operationId'])
        if value['retryOf'] is not None:
            identifier(value['retryOf'])
        for key in ['projectVersion', 'confirmationHash']:
            if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key]):
                raise BatchError('project_archive_invalid_state', 'Batch fingerprint is invalid.')
        seen = set()
        for item in value['items']:
            if (not isinstance(item, dict) or set(item) != {'target','state','result','archiveToken'}
                    or item['state'] not in ITEM_STATES
                    or (item['result'] is not None and (not isinstance(item['result'], dict)
                        or set(item['result']) != {'errorCode','workStopped'}
                        or not isinstance(item['result']['errorCode'], str)
                        or type(item['result']['workStopped']) is not bool))
                    or (value['confirmedAt'] is None and (item['state'] != 'pending' or item['result'] is not None))):
                raise BatchError('project_archive_invalid_state', 'Batch item is invalid.')
            target = item['target']
            if (not isinstance(target, dict) or set(target) != {'id','version','runIds','active','generation','projectionRunId'}
                    or not isinstance(target['runIds'], list) or type(target['active']) is not bool
                    or not isinstance(target['projectionRunId'], str) or len(target['projectionRunId']) > 128
                    or not isinstance(target['version'], str) or not re.fullmatch('[0-9a-f]{64}', target['version'])):
                raise BatchError('project_archive_invalid_state', 'Batch target is invalid.')
            sid = session_id(target['id'])
            identifier(target['generation'])
            if sid in seen:
                raise BatchError('project_archive_invalid_state', 'Duplicate batch target.')
            seen.add(sid)
            if target['runIds'] != sorted(set(target['runIds'])):
                raise BatchError('project_archive_invalid_state', 'Invalid frozen work set.')
            for run_id in target['runIds']:
                identifier(run_id)
            if item['archiveToken'] != digest([value['operationId'], sid])[:32]:
                raise BatchError('project_archive_invalid_state', 'Archive receipt identity changed.')
        return value

    def load(self, operation_id, *, allow_preview=True):
        path = self.path(operation_id)
        if path.exists():
            value = self.validate(self.read_json(path))
            if value['operationId'] != operation_id or value['confirmedAt'] is None:
                raise BatchError('project_archive_invalid_state', 'Durable batch identity is invalid.')
            return value
        with _guard:
            value = _previews.get((self.identity, operation_id)) if allow_preview else None
        if value is None or time.time() - value['createdAt'] > 600:
            raise BatchError('project_archive_not_found', 'The preview expired or this batch is unavailable. Refresh the project preview.', 404)
        return self.validate(json.loads(json.dumps(value)))

    def save(self, value):
        self.validate(value)
        if value['confirmedAt'] is None:
            raise BatchError('project_archive_unconfirmed', 'A preview cannot be executed.')
        self.atomic(self.path(value['operationId']), value)

    def confirm(self, operation_id, token, action):
        value = self.load(operation_id)
        if not isinstance(token, str) or not hmac.compare_digest(value['confirmationHash'], digest(token)) or action != value['action']:
            raise BatchError('project_archive_confirmation_invalid', 'Confirmation does not match this fixed project/action preview.')
        if value['confirmedAt'] is None:
            value['confirmedAt'] = time.time()
            self.save(value)
        return value

    def cancel_preview(self, operation_id, token):
        value = self.load(operation_id)
        if value['confirmedAt'] is not None or not hmac.compare_digest(value['confirmationHash'], digest(token)):
            raise BatchError('project_archive_confirmation_invalid', 'This preview cannot be cancelled.')
        with _guard:
            _previews.pop((self.identity, operation_id), None)

    def effect_path(self, operation_id, sid):
        return self.owned(self.root / 'effects' / identifier(operation_id) / (session_id(sid) + '.json'))

    def record_effect(self, operation_id, sid, archive_token, archived_at):
        value = self.load(operation_id, allow_preview=False)
        item = next((i for i in value['items'] if i['target']['id'] == sid), None)
        if not item or item['archiveToken'] != archive_token or value['confirmedAt'] is None:
            raise BatchError('project_archive_invalid_state', 'Archive completion does not belong to this confirmed batch.')
        fact = {'schema':'code-project-archive-effect/v1','operationId':operation_id,
                'sessionId':sid,'archiveToken':archive_token,'archivedAt':archived_at}
        path = self.effect_path(operation_id, sid)
        if path.exists():
            if self.read_json(path) != fact:
                raise BatchError('project_archive_invalid_state', 'Archive completion receipt conflicts.')
        else:
            self.atomic(path, fact)

    def effect(self, value, item):
        path = self.effect_path(value['operationId'], item['target']['id'])
        if not path.exists():
            return None
        fact = self.read_json(path)
        if (set(fact) != {'schema','operationId','sessionId','archiveToken','archivedAt'}
                or fact['schema'] != 'code-project-archive-effect/v1'
                or fact['operationId'] != value['operationId']
                or fact['sessionId'] != item['target']['id'] or fact['archiveToken'] != item['archiveToken']):
            raise BatchError('project_archive_invalid_state', 'Archive completion receipt is invalid.')
        return fact

    def list(self, project_id):
        directory = self.owned(self.root / 'operations')
        if not directory.exists():
            return []
        records = [self.load(p.stem, allow_preview=False) for p in directory.glob('*.json')]
        return sorted((r for r in records if project_id is None or r['projectId'] == project_id), key=lambda r:r['createdAt'], reverse=True)


def work_identities(meta):
    """Admission identities only: timestamps, output, usage and status can advance."""
    run = meta.get('runState') or {}
    if not isinstance(run, dict):
        raise BatchError('project_archive_invalid_state', 'Session work state is invalid.')
    identities = set()
    # Server Run admissions have their own locked generation hook. Their first
    # browser checkpoint may arrive after preview and is still the original Run.
    # Browser-owned rounds have no such admission path, so freeze their identity.
    if not run.get('agentRunId') and run.get('executionOwner') != 'server-agent':
        for key in ('runId', 'requestId', 'runtimeRunId', 'clientRequestId', 'queueItemId'):
            if run.get(key):
                identities.add(digest([key, run[key]]))
    for key in ('queuedMessages', 'backgroundRuns'):
        values = run.get(key) or []
        if not isinstance(values, list):
            raise BatchError('project_archive_invalid_state', 'Session work list is invalid.')
        for item in values:
            if not isinstance(item, dict):
                raise BatchError('project_archive_invalid_state', 'Session work item is invalid.')
            identity = {k:v for k,v in item.items() if k in ('id','runId','requestId','content','text','createdAt')}
            identities.add(digest([key, identity]))
    return identities


class ArchiveService:
    def __init__(self, runtime):
        self.r = runtime
        self.store = BatchStore(runtime.SESSIONS_DIR.parent / 'project-session-archive')

    def note_meta_write(self, path, meta):
        path = Path(path).absolute()
        if path.suffix != '.json' or self.r.SESSIONS_DIR.absolute() not in path.parents:
            return
        sid = path.stem
        if self.store.generation(sid) is None:
            return
        old = self.r._read_session_meta_strict(path)
        run_state = meta.get('runState') or {}
        if not isinstance(run_state, dict):
            raise BatchError('project_archive_invalid_state', 'Session work state is invalid.')
        server_owned = bool(run_state.get('agentRunId') or run_state.get('executionOwner') == 'server-agent')
        if (old is None or self.location(old) != self.location(meta)
                or work_identities(meta) - work_identities(old)
                or (not server_owned and not self.r._session_run_state_has_nonterminal_work(old, allow_quiescent_paused=True)
                    and self.r._session_run_state_has_nonterminal_work(meta, allow_quiescent_paused=True)
                    and not work_identities(meta))):
            self.store.bump(sid)

    @staticmethod
    def location(meta):
        return [meta.get('projectId') or meta.get('project') or '', meta.get('cwd') or '', meta.get('createdAt') or '']

    def project_version(self, project_id):
        # _read_projects is a tolerant listing API. Verify the authoritative input
        # first so a partial/corrupt catalog cannot authorize destructive work.
        raw = json.loads(self.r.PROJECTS_PATH.read_text(encoding='utf-8-sig'))
        records = raw.get('projects', raw.get('items')) if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            raise BatchError('project_archive_invalid_state', 'Project catalog is invalid.')
        projects = self.r._read_projects()
        if len(projects) != len(records):
            raise BatchError('project_archive_invalid_state', 'Project catalog is incomplete.')
        project = next((p for p in projects if p['id'] == project_id), None)
        if project is None:
            raise BatchError('project_archive_project_conflict', 'Project no longer exists.')
        return digest(project)

    @contextlib.contextmanager
    def target_lock(self, sid):
        r = self.r
        with r._session_archive_bounded_lock(r._session_lifecycle_lock(sid)):
            with r._session_archive_bounded_lock(r._agent_run_lock):
                with r._session_archive_bounded_lock(r._json_write_lock):
                    yield

    def snapshot(self, sid, project_id, *, watch=False):
        r = self.r
        if r._session_archive_journal_path(sid).exists() or r._session_archive_bundle_path(sid).exists():
            raise BatchError('project_archive_target_conflict', 'Session archive location changed.')
        meta = r._read_session_meta_strict(r.session_path(sid))
        if not meta or meta.get('id') != sid or self.location(meta)[0] != project_id:
            raise BatchError('project_archive_target_conflict', 'Session identity or project changed.')
        if not r.messages_path(sid).is_file():
            raise BatchError('project_archive_invalid_state', 'Session messages are unavailable.')
        runs = list(r._session_nonterminal_agent_run_ids(sid))
        work_identities(meta)  # Reject malformed work rather than treating it as idle.
        projection_run = str((meta.get('runState') or {}).get('agentRunId') or '')
        generation = self.store.generation(sid, watch=watch)
        return {'id':sid, 'generation':generation,
                'version':digest(self.location(meta)), 'runIds':runs, 'projectionRunId':projection_run,
                'active':bool(runs or r._session_run_state_has_nonterminal_work(meta, allow_quiescent_paused=True))}

    def check(self, value, item):
        if self.project_version(value['projectId']) != value['projectVersion']:
            raise BatchError('project_archive_project_conflict', 'Project changed after preview.')
        target = item['target']
        if value['confirmedAt'] is not None and not self.store.generation_path(target['id']).is_file():
            raise BatchError('project_archive_invalid_state', 'Confirmed lifecycle identity is missing.')
        current = self.snapshot(target['id'], value['projectId'])
        if (current['version'] != target['version'] or current['generation'] != target['generation']
                or set(current['runIds']) - set(target['runIds'])
                or (current['projectionRunId'] and current['projectionRunId'] != target['projectionRunId']
                    and current['projectionRunId'] not in target['runIds'])
                or (not target['active'] and current['active'])):
            raise BatchError('project_archive_target_conflict', 'New work or lifecycle changes require a fresh preview.')
        return current

    def prepare_indexes(self):
        self.r._ensure_agent_run_nonterminal_index_ready(wait=True)

    def preview(self, project_id, retry_of=None):
        self.prepare_indexes()
        with self.store.locked(project_id):
            with self.r._json_write_lock:
                version = self.project_version(project_id)
                candidates = {}
                def scan_error(exc):
                    raise exc
                for directory, dirs, files in os.walk(self.r.SESSIONS_DIR, onerror=scan_error, followlinks=False):
                    base = Path(directory)
                    for name in dirs:
                        self.store.plain(base / name)
                    depth = len(base.relative_to(self.r.SESSIONS_DIR).parts)
                    for name in files:
                        if depth not in (0, 3) or not name.endswith('.json'):
                            continue
                        path = self.store.plain(base / name)
                        meta = self.r._read_session_meta_strict(path)
                        sid = session_id(path.stem)
                        if not meta or meta.get('id') != sid or sid in candidates:
                            raise BatchError('project_archive_invalid_state', 'Session inventory is ambiguous.')
                        candidates[sid] = self.location(meta)[0]
                ids = sorted(sid for sid,pid in candidates.items() if pid == project_id)
            if retry_of:
                previous = self.store.load(retry_of, allow_preview=False)
                if previous['projectId'] != project_id:
                    raise BatchError('project_archive_confirmation_invalid', 'Retry belongs to another project.')
                failed = {i['target']['id'] for i in previous['items'] if i['state'] in RETRYABLE and not self.store.effect(previous, i)}
                ids = [sid for sid in ids if sid in failed]
            targets = []
            for sid in ids:
                with self.target_lock(sid):
                    targets.append(self.snapshot(sid, project_id, watch=True))
            value, token = self.store.preview(project_id, version, targets, retry_of=retry_of)
            return {**self.public(value), 'confirmationToken':token}

    def describe(self, result):
        """Read-only display labels; never add names to durable authorization."""
        value = self.store.load(result['operationId'])
        project = next((p for p in self.r._read_projects() if p['id'] == result['projectId']), None)
        items = []
        for item in result['items']:
            title, available = '', False
            try:
                sid = item['sessionId']
                path = self.r.session_path(sid)
                if not path.exists():
                    path = self.r._session_archive_bundle_path(sid) / 'session.json'
                meta = self.r._read_session_meta_strict(self.store.plain(path))
                if meta and meta.get('id') == sid:
                    title, available = str(meta.get('title') or ''), True
            except (OSError, ValueError):
                pass
            items.append({**item, 'title':title, 'titleAvailable':available})
        return {**result, 'items':items, 'projectName':str((project or {}).get('label') or ''),
                'retryOf':value['retryOf']}

    def public(self, value):
        items = []
        for item in value['items']:
            effect = self.store.effect(value, item) if value['confirmedAt'] is not None else None
            if item['state'] == 'archived' and effect is None:
                raise BatchError('project_archive_invalid_state', 'An archived result has lost its completion receipt.')
            items.append({'sessionId':item['target']['id'], 'active':item['target']['active'],
                          'state':'archived' if effect else item['state'], 'result':item['result']})
        return {'operationId':value['operationId'], 'projectId':value['projectId'],
                'action':value['action'], 'confirmed':value['confirmedAt'] is not None,
                'items':items, 'total':len(items), 'active':sum(i['active'] for i in items),
                'retryable':any(i['state'] in RETRYABLE for i in items)}

    def execute(self, operation_id, *, token=None, action=None, resume=False):
        initial = self.store.load(operation_id, allow_preview=not resume)
        self.prepare_indexes()
        with self.store.locked(initial['projectId']):
            value = self.store.load(operation_id, allow_preview=not resume)
            if value['confirmedAt'] is None:
                if resume:
                    raise BatchError('project_archive_unconfirmed', 'This batch has not been confirmed.')
                if action != value['action'] or not isinstance(token, str) or not hmac.compare_digest(digest(token), value['confirmationHash']):
                    raise BatchError('project_archive_confirmation_invalid', 'Confirmation changed.')
                for item in value['items']:
                    with self.target_lock(item['target']['id']):
                        self.store.generation(item['target']['id'], persist=True)
                value = self.store.confirm(operation_id, token, action)
            elif not resume:
                self.store.confirm(operation_id, token, action)
            self.public(value)  # Validate every existing completion fact before new effects.
            for item in value['items']:
                if item['state'] in RETRYABLE or item['state'] in {'uncertain', 'archived'}:
                    continue
                self.execute_item(value, item)
            return self.public(value)

    def execute_item(self, value, item):
        r, sid = self.r, item['target']['id']
        stopped = item['state'] in {'stopped','archiving'} and value['action'] == 'stop_and_archive' and item['target']['active']
        try:
            with r._session_archive_stop_fence(sid):
                with self.target_lock(sid):
                    # This may finish an already committed archive, but never
                    # infer success from absence or from someone else's bundle.
                    r._recover_session_archive_transaction(sid)
                    if self.store.effect(value, item):
                        item['state'] = 'archived'
                        self.store.save(value)
                        return
                    if item['state'] == 'archiving':
                        raise BatchError('project_archive_effect_missing', 'Previous archive has no completion receipt.')
                    current = self.check(value, item)
                    if item['state'] == 'stopping':
                        # A response/process loss must never repeat an ambiguous
                        # cancellation. Only all-terminal frozen work may advance.
                        if current['runIds']:
                            item['state'] = 'uncertain'
                            item['result'] = {'errorCode':'project_archive_stop_uncertain', 'workStopped':False}
                            self.store.save(value)
                            return
                        stopped = True
                    elif current['active']:
                        item['state'] = 'stopping'
                        self.store.save(value)
                if current['active'] and not stopped:
                    r._stop_session_agent_runs(sid)
                    stopped = True
                with self.target_lock(sid):
                    self.check(value, item)
                    if stopped:
                        item['state'] = 'stopped'
                        self.store.save(value)
                        r._clear_session_active_work_state(sid, force=True)
                    item['state'] = 'archiving'
                    self.store.save(value)
                    r._mutate_session_archive_state(sid, archived=True, stop_fence_owned=True,
                        batch_operation_id=value['operationId'], batch_archive_token=item['archiveToken'])
                    if not self.store.effect(value, item):
                        raise BatchError('project_archive_effect_missing', 'Archive completion receipt is unavailable.')
                    item['state'] = 'archived'
                    item['result'] = {'errorCode':'', 'workStopped':stopped}
                    self.store.save(value)
        except Exception as exc:
            # Corrupt durable state is a batch-level fail-closed condition.
            if isinstance(exc, BatchError) and exc.code == 'project_archive_invalid_state':
                raise
            if self.store.effect(value, item):
                item['state'] = 'archived'
                item['result'] = {'errorCode':'', 'workStopped':stopped}
                self.store.save(value)
                return
            code = getattr(exc, 'code', getattr(exc, 'error_code', 'project_archive_failed'))
            item['state'] = ('stopped_archive_failed' if stopped else
                             'stop_failed' if item['state'] == 'stopping' else
                             'conflict' if isinstance(exc, BatchError) and 'conflict' in code else 'archive_failed')
            item['result'] = {'errorCode':str(code), 'workStopped':stopped}
            self.store.save(value)
