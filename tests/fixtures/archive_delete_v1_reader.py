"""Frozen v1 group reader for CODE-108 downgrade compatibility checks.

Copied scope/validate/list from cd9c7a02b4db925112e084c5103bb7b253b5d5ed.
Only reading is supported; no writes, effects or execution are copied.
"""
import re
from code_runtime.project_archive import BatchError, BatchStore, identifier, session_id
STATES = {'pending','deleting','cleanup_pending','deleted','conflict','failed','uncertain'}

def scope(value):
    if not isinstance(value, dict):
        raise BatchError('archive_delete_invalid_scope', 'An explicit archive group is required.', 400)
    if value == {'kind':'unassigned'}:
        return dict(value)
    if (set(value) != {'kind','projectId'} or value['kind'] not in {'project','deleted-project'}
            or not isinstance(value['projectId'], str) or not value['projectId'].strip()
            or value['projectId'] != value['projectId'].strip() or len(value['projectId']) > 256):
        raise BatchError('archive_delete_invalid_scope', 'An explicit archive group is required.', 400)
    return dict(value)


class LegacyDeleteStore(BatchStore):
    def validate(self, value):
        keys = {'schema','dataRoot','operationId','scope','scopeVersion','createdAt','confirmedAt',
                'action','confirmationHash','retryOf','items'}
        if (not isinstance(value, dict) or set(value) != keys
                or value['schema'] != 'code-project-archive-delete/v1' or value['dataRoot'] != self.identity
                or value['action'] != 'permanent_delete' or not isinstance(value['items'], list)
                or type(value['createdAt']) not in (float,int) or not 0 < value['createdAt'] < float('inf')
                or (value['confirmedAt'] is not None and (type(value['confirmedAt']) not in (float,int)
                    or not value['createdAt'] <= value['confirmedAt'] < float('inf')))):
            raise BatchError('archive_delete_invalid_state', 'Delete batch state is invalid.')
        scope(value['scope']); identifier(value['operationId'])
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
            if (not isinstance(target,dict) or set(target) != {'id','archiveToken','version'}
                    or not isinstance(target['version'],str) or not re.fullmatch('[0-9a-f]{64}',target['version'])):
                raise BatchError('archive_delete_invalid_state', 'Delete target is invalid.')
            sid = session_id(target['id']); identifier(target['archiveToken'])
            if sid in seen:
                raise BatchError('archive_delete_invalid_state', 'Duplicate delete target.')
            seen.add(sid)
        return value

    def list(self, group=None):
        if group is not None:
            group = scope(group)
        directory = self.owned(self.root/'operations')
        records = [self.load(p.stem,allow_preview=False) for p in directory.glob('*.json')] if directory.exists() else []
        return sorted((v for v in records if group is None or v['scope'] == group),key=lambda v:v['createdAt'],reverse=True)
