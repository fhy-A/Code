"""Fixed-scope permanent archive deletion, separate from archive permissions."""
import hmac
import json
import re
import time
import uuid

from .project_archive import BatchError, BatchStore, ArchiveService, digest, identifier, session_id, _guard, _previews


STATES = {'pending','deleting','cleanup_pending','deleted','conflict','failed','uncertain'}
RETRYABLE = {'conflict','failed'}


def scope(value, *, allow_all=False):
    if allow_all and value == {'kind':'all'}:
        return dict(value)
    if not isinstance(value, dict):
        raise BatchError('archive_delete_invalid_scope', 'An explicit archive group is required.', 400)
    if value == {'kind':'unassigned'}:
        return dict(value)
    if (set(value) != {'kind','projectId'} or value['kind'] not in {'project','deleted-project'}
            or not isinstance(value['projectId'], str) or not value['projectId'].strip()
            or value['projectId'] != value['projectId'].strip() or len(value['projectId']) > 256):
        raise BatchError('archive_delete_invalid_scope', 'An explicit archive group is required.', 400)
    return dict(value)


class DeleteStore(BatchStore):
    def validate(self, value):
        keys = {'schema','dataRoot','operationId','scope','scopeVersion','createdAt','confirmedAt',
                'action','confirmationHash','retryOf','items'}
        all_scope = isinstance(value, dict) and value.get('schema') == 'code-project-archive-delete/v2'
        if all_scope:
            keys |= {'captureState','captureError'}
        if (not isinstance(value, dict) or set(value) != keys
                or value['schema'] not in {'code-project-archive-delete/v1','code-project-archive-delete/v2'} or value['dataRoot'] != self.identity
                or value['action'] != ('permanent_delete_all' if all_scope else 'permanent_delete') or not isinstance(value['items'], list)
                or type(value['createdAt']) not in (float,int) or not 0 < value['createdAt'] < float('inf')
                or (value['confirmedAt'] is not None and (type(value['confirmedAt']) not in (float,int)
                    or not value['createdAt'] <= value['confirmedAt'] < float('inf')))):
            raise BatchError('archive_delete_invalid_state', 'Delete batch state is invalid.')
        scope(value['scope'],allow_all=all_scope); identifier(value['operationId'])
        if all_scope and (value['scope'] != {'kind':'all'} or value['retryOf'] is not None
                or value['captureState'] not in {'capturing','ready','failed'} or not isinstance(value['captureError'],str)
                or value['confirmedAt'] is None or (value['captureState'] != 'ready' and value['items'])
                or value['scopeVersion'] != digest({'kind':'all'})):
            raise BatchError('archive_delete_invalid_state', 'All-archive admission is invalid.')
        if value['retryOf'] is not None:
            identifier(value['retryOf'])
        for key in ('scopeVersion','confirmationHash'):
            if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}',value[key]):
                raise BatchError('archive_delete_invalid_state', 'Delete batch fingerprint is invalid.')
        seen = set()
        for item in value['items']:
            if (not isinstance(item,dict) or set(item) != {'target','state','result'} or item['state'] not in STATES
                    or (item['result'] is not None and (not isinstance(item['result'],dict)
                        or set(item['result']) != {'errorCode'} or not isinstance(item['result']['errorCode'],str)))
                    or (value['confirmedAt'] is None and (item['state'] != 'pending' or item['result'] is not None))):
                raise BatchError('archive_delete_invalid_state', 'Delete item state is invalid.')
            target = item['target']
            if (not isinstance(target,dict) or set(target) != ({'id','archiveToken','version','scope','scopeVersion'} if all_scope else {'id','archiveToken','version'})
                    or not isinstance(target['version'],str) or not re.fullmatch('[0-9a-f]{64}',target['version'])):
                raise BatchError('archive_delete_invalid_state', 'Delete target is invalid.')
            if all_scope:
                scope(target['scope'])
                if not isinstance(target['scopeVersion'],str) or not re.fullmatch('[0-9a-f]{64}',target['scopeVersion']):
                    raise BatchError('archive_delete_invalid_state', 'All-archive target scope is invalid.')
            sid = session_id(target['id']); identifier(target['archiveToken'])
            if sid in seen:
                raise BatchError('archive_delete_invalid_state', 'Duplicate delete target.')
            seen.add(sid)
        return value

    def preview(self, group, version, targets, *, retry_of=None):
        op, token = uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
        value = {'schema':'code-project-archive-delete/v1','dataRoot':self.identity,'operationId':op,
                 'scope':scope(group),'scopeVersion':version,'createdAt':time.time(),'confirmedAt':None,
                 'action':'permanent_delete','confirmationHash':digest(token),'retryOf':retry_of,
                 'items':[{'target':target,'state':'pending','result':None} for target in targets]}
        self.validate(value)
        with _guard:
            for key in [key for key,val in _previews.items() if time.time()-val['createdAt'] > 600]:
                _previews.pop(key,None)
            _previews[(self.identity,op)] = value
        return json.loads(json.dumps(value)), token

    def binding(self, op, sid, token):
        value = self.load(op,allow_preview=False)
        item = next((i for i in value['items'] if i['target']['id'] == sid),None)
        if value['confirmedAt'] is None or not item or item['target']['archiveToken'] != token:
            raise BatchError('archive_delete_invalid_state', 'Delete journal is not bound to this confirmation.')
        return value, item

    def record_effect(self, op, sid, token, deleted_at):
        self.binding(op,sid,token)
        fact = {'schema':'code-project-archive-delete-effect/v1','action':'permanent_delete',
                'operationId':op,'sessionId':sid,'archiveToken':token,'deletedAt':deleted_at}
        path = self.effect_path(op,sid)
        if path.exists():
            existing = self.read_json(path)
            if any(existing.get(key) != value for key,value in fact.items() if key != 'deletedAt'):
                raise BatchError('archive_delete_invalid_state', 'Delete completion receipt conflicts.')
            self.effect(*self.binding(op,sid,token))
        else:
            self.atomic(path,fact)

    def effect(self, value, item):
        path = self.effect_path(value['operationId'],item['target']['id'])
        if not path.exists():
            return None
        fact = self.read_json(path)
        if (set(fact) != {'schema','action','operationId','sessionId','archiveToken','deletedAt'}
                or fact['schema'] != 'code-project-archive-delete-effect/v1' or fact['action'] != 'permanent_delete'
                or fact['operationId'] != value['operationId'] or fact['sessionId'] != item['target']['id']
                or fact['archiveToken'] != item['target']['archiveToken']
                or not isinstance(fact['deletedAt'],str) or not fact['deletedAt']):
            raise BatchError('archive_delete_invalid_state', 'Delete completion receipt is invalid.')
        return fact

    def list(self, group=None):
        if group is not None:
            group = scope(group,allow_all=True)
        directory = self.owned(self.root/'operations')
        records = [self.load(p.stem,allow_preview=False) for p in directory.glob('*.json')] if directory.exists() else []
        return sorted((v for v in records if group is None or v['scope'] == group),key=lambda v:v['createdAt'],reverse=True)

    def cleanup_path(self, op, sid):
        return self.owned(self.root/'cleanup'/identifier(op)/(session_id(sid)+'.json'))

    def record_cleanup(self, op, sid, token, transaction_id):
        value, item = self.binding(op,sid,token)
        if not self.effect(value,item):
            raise BatchError('archive_delete_invalid_state', 'Archive cleanup has no committed deletion receipt.')
        fact = {'schema':'code-project-archive-delete-cleanup/v1','operationId':op,
                'sessionId':sid,'archiveToken':token,'transactionId':identifier(transaction_id)}
        path = self.cleanup_path(op,sid)
        if path.exists():
            if self.read_json(path) != fact:
                raise BatchError('archive_delete_invalid_state', 'Archive cleanup receipt conflicts.')
        else:
            self.atomic(path,fact)

    def cleanup(self, value, item):
        path = self.cleanup_path(value['operationId'],item['target']['id'])
        if not path.exists():
            return None
        fact = self.read_json(path)
        if (set(fact) != {'schema','operationId','sessionId','archiveToken','transactionId'}
                or fact['schema'] != 'code-project-archive-delete-cleanup/v1'
                or fact['operationId'] != value['operationId'] or fact['sessionId'] != item['target']['id']
                or fact['archiveToken'] != item['target']['archiveToken']):
            raise BatchError('archive_delete_invalid_state', 'Archive cleanup receipt is invalid.')
        identifier(fact['transactionId'])
        return fact


class DeleteService:
    def __init__(self, runtime):
        self.r = runtime
        self.store = DeleteStore(runtime.SESSIONS_DIR.parent/'project-archive-delete')
        self.locks = ArchiveService(runtime)

    def scope_version(self, group):
        group = scope(group)
        raw = json.loads(self.r.PROJECTS_PATH.read_text(encoding='utf-8-sig')) if self.r.PROJECTS_PATH.exists() else []
        records = raw.get('projects',raw.get('items')) if isinstance(raw,dict) else raw
        projects = self.r._read_projects()
        if not isinstance(records,list) or len(records) != len(projects):
            raise BatchError('archive_delete_invalid_state', 'Project catalog is incomplete.')
        project = next((p for p in projects if p['id'] == group.get('projectId')),None)
        if (group['kind'] == 'project' and project is None) or (group['kind'] == 'deleted-project' and project is not None):
            raise BatchError('archive_delete_scope_changed', 'The project identity changed; inspect the current archive group.')
        return digest([group,project if group['kind'] == 'project' else None])

    def snapshot(self, sid, group):
        r = self.r
        if r._session_archive_journal_path(sid).exists():
            raise BatchError('archive_delete_unsettled', 'This archive has an unsettled transaction; inspect it first.')
        manifest = r._read_session_archive_manifest(sid)
        if manifest is None:
            raise BatchError('archive_delete_target_changed', 'The archived Session is no longer present.')
        active, messages = r._session_archive_original_paths(sid,manifest['original'])
        if active.exists() or messages.exists():
            raise BatchError('archive_delete_target_changed', 'The Session is no longer exclusively archived.')
        bundle = r._session_archive_bundle_path(sid)
        self.store.plain(bundle)
        meta = r._read_session_meta_strict(bundle/'session.json')
        pid = str(meta.get('projectId') or '').strip()
        expected = '' if group['kind'] == 'unassigned' else group['projectId']
        if pid != expected:
            raise BatchError('archive_delete_target_changed', 'The archive belongs to a different group.')
        return {'id':sid,'archiveToken':manifest['archiveToken'],'version':digest(manifest)}

    def preview(self, group, retry_of=None):
        group = scope(group)
        with self.store.locked(digest(group)):
            with self.r._json_write_lock:
                version = self.scope_version(group)
                bundles = self.r._session_archive_owned_bundle_paths()
            allowed = None
            if retry_of:
                previous = self.store.load(retry_of,allow_preview=False)
                if previous['scope'] != group:
                    raise BatchError('archive_delete_confirmation_invalid', 'Retry belongs to a different archive group.')
                allowed = {i['target']['id'] for i in previous['items'] if i['state'] in RETRYABLE and not self.store.effect(previous,i)}
            targets = []
            for bundle in sorted(bundles,key=lambda p:p.name):
                sid = session_id(bundle.name)
                if allowed is not None and sid not in allowed:
                    continue
                with self.locks.target_lock(sid):
                    meta = self.r._read_session_meta_strict(bundle/'session.json')
                    if not meta or meta.get('id') != sid:
                        raise BatchError('archive_delete_invalid_state', 'Archive inventory is invalid.')
                    if str(meta.get('projectId') or '').strip() != ('' if group['kind'] == 'unassigned' else group['projectId']):
                        continue
                    targets.append(self.snapshot(sid,group))
            value, token = self.store.preview(group,version,targets,retry_of=retry_of)
            return {**self.public(value),'confirmationToken':token}

    def confirm_all(self, op, group, action, token, data_root):
        # Only this explicit endpoint can create an all-project authorization.
        if group != {'kind':'all'} or action != 'permanent_delete_all' or data_root != self.store.identity:
            raise BatchError('archive_delete_confirmation_invalid', 'Explicit all-archive confirmation required.', 400)
        identifier(op)
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{64}',token):
            raise BatchError('archive_delete_confirmation_invalid', 'Invalid all-archive confirmation.', 400)
        with self.store.locked(digest(group)):
            if not self.store.path(op).exists():
                with _guard:
                    if (self.store.identity,op) in _previews:
                        raise BatchError('archive_delete_confirmation_invalid', 'This identity belongs to an existing group preview.')
                now = time.time()
                value = {'schema':'code-project-archive-delete/v2','dataRoot':self.store.identity,
                         'operationId':op,'scope':group,'scopeVersion':digest(group),'createdAt':now,
                         'confirmedAt':now,'action':action,'confirmationHash':digest(token),'retryOf':None,
                         'captureState':'capturing','captureError':'','items':[]}
                # Reserve the ID durably BEFORE enumeration. An interrupted capture
                # can never silently take a later inventory under the old consent.
                self.store.save(value)
                try:
                    value['items'] = self.capture_all()
                    value['captureState'] = 'ready'
                except Exception as exc:
                    value['items'] = []
                    value['captureState'] = 'failed'
                    value['captureError'] = str(getattr(exc,'code','archive_delete_capture_failed'))
                self.store.save(value)
            return self.execute(op,group,action,token=token)

    def capture_all(self):
        # All lifecycle writers take agent/json locks before committing archives.
        # Do not acquire per-Session locks underneath them (lock-order inversion).
        r = self.r
        with r._session_archive_bounded_lock(r._agent_run_lock):
            with r._session_archive_bounded_lock(r._json_write_lock):
                projects = {p['id'] for p in r._read_projects()}
                self.scope_version({'kind':'unassigned'})  # Strict catalog validation.
                items = []
                for bundle in sorted(r._session_archive_owned_bundle_paths(),key=lambda p:p.name):
                    sid = session_id(bundle.name)
                    meta = r._read_session_meta_strict(bundle/'session.json')
                    if not meta or meta.get('id') != sid:
                        raise BatchError('archive_delete_invalid_state', 'Archive inventory is invalid.')
                    pid = str(meta.get('projectId') or '').strip()
                    group = ({'kind':'project' if pid in projects else 'deleted-project','projectId':pid}
                             if pid else {'kind':'unassigned'})
                    target = {**self.snapshot(sid,group),'scope':group,'scopeVersion':self.scope_version(group)}
                    items.append({'target':target,'state':'pending','result':None})
                return items

    def target_scope(self, value, item):
        target = item['target']
        if value['scope'] == {'kind':'all'}:
            return target['scope'], target['scopeVersion']
        return value['scope'], value['scopeVersion']

    def cleanup_complete(self, value, item):
        receipt = self.store.cleanup(value,item)
        if not receipt:
            return False
        journal = self.r._read_session_archive_journal(item['target']['id'])
        return journal is None or journal['transactionId'] != receipt['transactionId']

    def finish_cleanup(self, value, item):
        if self.cleanup_complete(value,item):
            return
        target = item['target']
        journal = self.r._read_session_archive_journal(target['id'])
        receipt = self.store.cleanup(value,item)
        if (not journal or journal.get('schema') != 'code-session-archive-transaction/v3'
                or journal.get('batchOperationId') != value['operationId']
                or journal.get('archiveToken') != target['archiveToken'] or journal.get('state') != 'facts_deleted'
                or (receipt and receipt['transactionId'] != journal['transactionId'])):
            raise BatchError('archive_delete_cleanup_conflict', 'The original cleanup transaction cannot be proven; preserve current objects.')
        if self.r._session_archive_bundle_path(target['id']).exists():
            manifest = self.r._read_session_archive_manifest(target['id'])
            if not manifest or manifest['archiveToken'] != target['archiveToken'] or digest(manifest) != target['version']:
                raise BatchError('archive_delete_cleanup_conflict', 'The archive copy belongs to a different incarnation; preserve it.')
        # facts_deleted recovery is cleanup-only; it never calls delete_session.
        self.r._recover_session_archive_transaction(target['id'])
        if not self.cleanup_complete(value,item):
            raise BatchError('archive_delete_cleanup_pending', 'The archive copy or original transaction still needs cleanup.')

    def public(self, value):
        items = []
        for item in value['items']:
            fact = self.store.effect(value,item) if value['confirmedAt'] is not None else None
            if item['state'] == 'deleted' and not fact:
                raise BatchError('archive_delete_invalid_state', 'A completed delete has lost its receipt.')
            complete = bool(fact and self.cleanup_complete(value,item))
            projected = ('deleted' if complete else 'cleanup_pending') if fact else item['state']
            result = {'errorCode':''} if complete else item['result']
            if fact and not complete and not (result or {}).get('errorCode'):
                result = {'errorCode':'archive_delete_cleanup_pending'}
            items.append({'sessionId':item['target']['id'],'state':projected,'result':result,
                          'factsDeleted':bool(fact),'cleanupComplete':complete})
        return {**({'captureState':value['captureState'],'captureError':value['captureError']} if value['scope'] == {'kind':'all'} else {}),
                'operationId':value['operationId'],'scope':value['scope'],'action':value['action'],
                'confirmed':value['confirmedAt'] is not None,'total':len(items),'items':items,'retryOf':value['retryOf'],
                'retryable':any(i['state'] in RETRYABLE for i in items)}

    def execute(self, op, group, action, *, token=None, resume=False):
        group = scope(group,allow_all=True)
        value = self.store.load(op,allow_preview=not resume)
        expected_action = 'permanent_delete_all' if group == {'kind':'all'} else 'permanent_delete'
        if value['scope'] != group or action != expected_action:
            raise BatchError('archive_delete_confirmation_invalid', 'Scope/action does not match this delete confirmation.')
        self.r._ensure_agent_run_session_index_ready(wait=True)
        with self.store.locked(digest(group)):
            value = self.store.load(op,allow_preview=not resume)
            if not resume:
                value = self.store.confirm(op,token,action)
            if value['confirmedAt'] is None:
                raise BatchError('archive_delete_confirmation_invalid', 'Delete batch has not been confirmed.')
            self.public(value)
            if group == {'kind':'all'} and value['captureState'] != 'ready':
                return self.public(value)
            for item in value['items']:
                if (item['state'] not in ({'pending','deleting','cleanup_pending'} | (RETRYABLE if group == {'kind':'all'} else set()))
                        and not (self.store.effect(value,item) and not self.cleanup_complete(value,item))):
                    continue
                self.execute_item(value,item)
            return self.public(value)

    def execute_item(self, value, item):
        r, target = self.r, item['target']
        sid = target['id']
        try:
            with self.locks.target_lock(sid):
                if self.store.effect(value,item):
                    self.finish_cleanup(value,item)
                    item['state'] = 'deleted';item['result'] = {'errorCode':''};self.store.save(value)
                    return
                journal = r._read_session_archive_journal(sid)
                if journal is not None:
                    if (journal.get('schema') != 'code-session-archive-transaction/v3'
                            or journal.get('batchOperationId') != value['operationId'] or journal.get('archiveToken') != target['archiveToken']):
                        raise BatchError('archive_delete_unsettled', 'Another transaction owns this archive; inspect its result.')
                    r._recover_session_archive_transaction(sid)
                    if not self.store.effect(value,item):
                        raise BatchError('archive_delete_unsettled', 'Delete recovery has no completion proof.')
                else:
                    if item['state'] == 'deleting':
                        raise BatchError('archive_delete_unsettled', 'An interrupted delete has no transaction or receipt; inspect it first.')
                    group, version = self.target_scope(value,item)
                    expected = {k:target[k] for k in ('id','archiveToken','version')}
                    if self.scope_version(group) != version or self.snapshot(sid,group) != expected:
                        raise BatchError('archive_delete_target_changed', 'Archive incarnation or project changed after preview.')
                    item['state'] = 'deleting';self.store.save(value)
                    result = {}
                    handler = object.__new__(r.CodeHandler)
                    handler.send_json = lambda payload,status=200:result.update(payload=payload,status=status)
                    r.CodeHandler.delete_archived_session(handler,sid,target['archiveToken'],batch_operation_id=value['operationId'])
                    if not self.store.effect(value,item):
                        if r._session_archive_journal_path(sid).exists():
                            raise BatchError('archive_delete_unsettled', 'Delete transaction needs recovery; inspect the existing batch.')
                        raise BatchError(str(result.get('payload',{}).get('errorCode') or 'archive_delete_failed'), 'Delete did not complete.')
                if not self.cleanup_complete(value,item):
                    raise BatchError('archive_delete_cleanup_pending', 'Committed deletion still needs archive/transaction cleanup.')
                item['state'] = 'deleted';item['result'] = {'errorCode':''};self.store.save(value)
        except Exception as exc:
            if isinstance(exc,BatchError) and exc.code in {'archive_delete_invalid_state','project_archive_invalid_state'}:
                raise
            if self.store.effect(value,item):
                if self.cleanup_complete(value,item):
                    item['state'] = 'deleted';item['result'] = {'errorCode':''}
                else:
                    item['state'] = 'cleanup_pending'
                    code = getattr(exc,'code',getattr(exc,'error_code','archive_delete_cleanup_failed'))
                    item['result'] = {'errorCode':str(code)}
            else:
                code = getattr(exc,'code',getattr(exc,'error_code','archive_delete_failed'))
                item['state'] = ('uncertain' if code in {'archive_delete_unsettled','archive_delete_recovery_conflict','session_archive_recovery_failed','session_delete_recovery_failed'}
                                 else 'conflict' if code in {'archive_delete_scope_changed','archive_delete_target_changed','session_archive_token_mismatch'} else 'failed')
                item['result'] = {'errorCode':str(code)}
            self.store.save(value)
