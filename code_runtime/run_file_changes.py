"""Bounded, read-only projection of recorded file operations. No runtime recovery."""
import hashlib
import difflib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

BINDING = 'code-run-review-binding/v1'
RECEIPT = 'code-file-change-receipt/v1'
SCHEMA = 'code-run-file-changes/v1'
RUN_BYTES = 16 * 1024 * 1024
TOTAL_BYTES = 64 * 1024 * 1024
# Conservatively include both bounded source/Session checks in the request quota.
SCOPE_RESERVE = 2 * (1024 * 1024 + 4096)
MEMBERS = 32
OPERATIONS = 512
FILES = 128
SUMMARY_BYTES = 256 * 1024
DIFF_BYTES = 256 * 1024
DIFF_LINES = 5000
DELETE_BYTES = 256 * 1024
DELETE_PRIVATE = '_codeReviewDelete'
DELETE_SCHEMA = 'code-delete-preimage/v1'
DELETE_REASONS = {'binary', 'encoding', 'limit', 'unreadable', 'changed', 'unverifiable', 'not-retained'}
TERMINAL = {'completed', 'failed', 'cancelled'}
READ_TOOLS = {'read_file', 'list_files', 'search_files', 'search_text', 'find_files',
              'get_file_info', 'request_user_input', 'read_skill_resource'}


class ReviewError(ValueError):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def text(value, limit=32768):
    return isinstance(value, str) and 0 < len(value) <= limit and '\0' not in value


def canonical_path(value):
    return (text(value) and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
            and not any(part in {'.', '..'} for part in re.split(r'[\\/]', value)))


def public_value(value):
    """One reserved local-review field never belongs in general tool projections."""
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items() if key != DELETE_PRIVATE}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    return value


def public_messages(messages):
    """Also protect recovery of JSON-serialized tool messages from an older writer."""
    output = public_value(messages)
    for message in output:
        if not isinstance(message, dict) or message.get('role') != 'tool':
            continue
        content = message.get('content')
        if isinstance(content, str) and DELETE_PRIVATE in content:
            try:
                message['content'] = json.dumps(public_value(json.loads(content)), ensure_ascii=False, separators=(',', ':'))
            except (ValueError, TypeError, RecursionError):
                message['content'] = '{"reviewContentOmitted":true}'
    return output


def delete_diff(proof):
    value = proof['text'].removeprefix('\ufeff').replace('\r\r\n', '\n').replace('\r\n', '\n').replace('\r', '\n')
    lines = list(difflib.unified_diff(value.splitlines(), [], fromfile='a/' + proof['canonicalPath'],
                                    tofile='b/' + proof['canonicalPath'], lineterm=''))
    diff = '\n'.join(lines) + ('\n' if lines else '')
    if len(diff.encode()) > DIFF_BYTES or len(lines) > DIFF_LINES:
        raise ValueError('limit')
    return diff


def file_signature(metadata):
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError('changed')
    return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def capture_delete(path, operation_id):
    """One bounded pre-delete read; no backups, persistence, or mutation here."""
    try:
        identity = os.path.normcase(str(path.resolve()))
        before = file_signature(path.lstat())
        if before[2] > DELETE_BYTES:
            return None, None, 'limit'
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = file_signature(os.fstat(stream.fileno()))
            # Windows path stat and handle fstat can expose different ctime semantics.
            # Compare their common identity/size/mtime, and each source's ctime to itself.
            if opened[:4] != before[:4]:
                return None, None, 'changed'
            raw = stream.read(DELETE_BYTES + 1)
            if file_signature(os.fstat(stream.fileno())) != opened:
                return None, None, 'changed'
        if len(raw) > DELETE_BYTES:
            return None, None, 'limit'
        if len(raw) != before[2] or file_signature(path.lstat()) != before or os.path.normcase(str(path.resolve())) != identity:
            return None, None, 'changed'
        if any(byte < 32 and byte not in (9, 10, 13) for byte in raw) or b'\x7f' in raw:
            return None, None, 'binary'
        try:
            content = raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            return None, None, 'encoding'
        proof = {'schema': DELETE_SCHEMA, 'operationId': operation_id, 'canonicalPath': identity,
                 'byteLength': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'text': content}
        delete_diff(proof)  # Reject an over-budget diff before retaining any text.
        return proof, before, None
    except ValueError as exc:
        return None, None, str(exc) if str(exc) in DELETE_REASONS else 'unreadable'
    except Exception:
        return None, None, 'unreadable'


def delete_capture_current(path, proof, signature):
    try:
        return file_signature(path.lstat()) == signature and os.path.normcase(str(path.resolve())) == proof['canonicalPath']
    except Exception:
        return False


def verified_delete_diff(result, receipt):
    proof = result.get(DELETE_PRIVATE)
    if (not isinstance(proof, dict) or proof.get('schema') != DELETE_SCHEMA
            or receipt.get('deleteEvidenceSchema') != DELETE_SCHEMA
            or proof.get('operationId') != receipt['operationId']
            or proof.get('canonicalPath') != receipt['canonicalPath']
            or digest(proof) != receipt.get('deleteEvidenceSha256')
            or not isinstance(proof.get('text'), str)):
        raise ValueError('unverifiable')
    raw = proof['text'].encode('utf-8')
    if (len(raw) > DELETE_BYTES or type(proof.get('byteLength')) is not int
            or len(raw) != proof['byteLength'] or hashlib.sha256(raw).hexdigest() != proof.get('sha256')
            or any(byte < 32 and byte not in (9, 10, 13) for byte in raw) or b'\x7f' in raw):
        raise ValueError('unverifiable')
    diff = delete_diff(proof)
    if hashlib.sha256(diff.encode()).hexdigest() != receipt.get('diffSha256'):
        raise ValueError('unverifiable')
    return diff


def line_stats(diff):
    """Count a bounded, structurally complete single-file unified diff, not net changes."""
    if not isinstance(diff, str) or len(diff.encode()) > DIFF_BYTES:
        return None
    lines = diff.splitlines()
    if (len(lines) > DIFF_LINES or len(lines) < 3
            or not lines[0].startswith('--- ') or not lines[1].startswith('+++ ')):
        return None
    old = new = added = removed = 0
    hunks = 0
    for line in lines[2:]:
        if line.startswith('@@ '):
            match = re.fullmatch(r'@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?: .*)?', line)
            if old or new or not match:
                return None
            old, new = (int(value) if value is not None else 1 for value in match.groups())
            hunks += 1
        elif line == '\\ No newline at end of file' and hunks:
            continue
        elif hunks and (old or new) and line.startswith('+'):
            added += 1; new -= 1
        elif hunks and (old or new) and line.startswith('-'):
            removed += 1; old -= 1
        elif hunks and (old or new) and line.startswith(' '):
            old -= 1; new -= 1
        else:
            return None
        if old < 0 or new < 0:
            return None
    return {'additions': added, 'deletions': removed} if hunks and old == new == 0 else None


def run_id(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ReviewError('review_invalid_run', 400)
    return value


def binding(value):
    if not isinstance(value, dict) or value.get('schema') != BINDING:
        raise ReviewError('review_binding_unavailable')
    for key in ('dataSourceId', 'sessionInstanceId', 'rootRunId'):
        run_id(value.get(key))
    if (not text(value.get('sessionId'), 128)
            or not text(value.get('rootClientRequestId'), 200)
            or not isinstance(value.get('originMessageId'), str)
            or len(value['originMessageId']) > 200
            or not text(value.get('originRoot'))):
        raise ReviewError('review_binding_unavailable')
    return {key: value[key] for key in ('schema', 'dataSourceId', 'sessionId',
            'sessionInstanceId', 'rootRunId', 'rootClientRequestId', 'originMessageId', 'originRoot')}


def make_receipt(result, canonical_path, *, kind, operation_id, directory=False):
    """Called only after a fresh mutation. Failure is handled by the caller."""
    if not text(canonical_path) or not text(operation_id, 256):
        raise ReviewError('review_receipt_unavailable')
    diff = result.get('diff')
    receipt = {'schema': RECEIPT, 'canonicalPath': canonical_path,
            'fileKey': digest(canonical_path), 'kind': kind,
            'entityKind': 'directory' if directory else 'file',
            'operationId': operation_id, 'diffSemantics': 'normalized-lines',
            'diffSha256': hashlib.sha256(diff.encode()).hexdigest() if isinstance(diff, str) else None,
            'bodyState': 'not-retained' if kind == 'delete' else 'diff' if diff else 'no-line-diff'}
    if kind == 'delete' and not directory:
        proof = result.get(DELETE_PRIVATE)
        if proof is not None:
            diff = delete_diff(proof)
            receipt.update(deleteEvidenceSchema=DELETE_SCHEMA, deleteEvidenceSha256=digest(proof),
                           diffSha256=hashlib.sha256(diff.encode()).hexdigest(), bodyState='diff' if diff else 'no-line-diff')
            verified_delete_diff(result, receipt)
        else:
            reason = result.get('deleteReviewReason')
            receipt['bodyReason'] = reason if reason in DELETE_REASONS else 'not-retained'
    return receipt


class Reader:
    def __init__(self, directory, *, reserve=0):
        self.directory = Path(directory)
        self.used = reserve
        self.records = {}
        self.raw_hashes = {}

    def raw(self, rid):
        path = self.directory / (run_id(rid) + '.json')
        try:
            if path.is_symlink():
                raise ReviewError('review_record_unavailable')
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ReviewError('review_record_unavailable')
            size = metadata.st_size
            if size > RUN_BYTES or self.used + size > TOTAL_BYTES:
                raise ReviewError('review_read_limit', 413)
            with path.open('rb') as stream:
                data = stream.read(min(RUN_BYTES, TOTAL_BYTES - self.used) + 1)
            self.used += len(data)
            if len(data) > RUN_BYTES or self.used > TOTAL_BYTES:
                raise ReviewError('review_read_limit', 413)
            return data
        except FileNotFoundError:
            raise ReviewError('review_missing_run', 404) from None
        except OSError:
            raise ReviewError('review_record_unavailable') from None

    def get(self, rid):
        if rid in self.records:
            return self.records[rid]
        if len(self.records) >= MEMBERS:
            raise ReviewError('review_member_limit', 413)
        data = self.raw(rid)
        try:
            record = json.loads(data)
        except (ValueError, UnicodeError):
            raise ReviewError('review_record_invalid') from None
        if (not isinstance(record, dict) or record.get('id') != rid
                or type(record.get('version')) is not int or record['version'] not in (5, 6, 7)
                or not isinstance(record.get('toolExecutions', {}), dict)):
            raise ReviewError('review_record_invalid')
        self.records[rid] = record
        self.raw_hashes[rid] = hashlib.sha256(data).hexdigest()
        return record

    def verify(self):
        for rid, expected in self.raw_hashes.items():
            if hashlib.sha256(self.raw(rid)).hexdigest() != expected:
                raise ReviewError('review_changed')


def project(directory, requested_id, expected_scope, read_scope, *, operation=None, revision=None):
    try:
        return _project(directory, requested_id, expected_scope, read_scope, operation=operation, revision=revision)
    except (TypeError, AttributeError, UnicodeError, RecursionError):
        raise ReviewError('review_record_invalid') from None


def _project(directory, requested_id, expected_scope, read_scope, *, operation=None, revision=None):
    """read_scope must only inspect source, active Session and lifecycle fences."""
    scope = read_scope()
    if any(scope.get(k) != expected_scope.get(k) for k in ('dataSourceId', 'sessionId', 'sessionInstanceId')):
        raise ReviewError('review_scope_changed')
    reader = Reader(directory, reserve=SCOPE_RESERVE)
    requested = reader.get(run_id(requested_id))
    root_binding = binding(requested.get('reviewBinding'))
    if any(root_binding[k] != scope.get(k) for k in ('dataSourceId', 'sessionId', 'sessionInstanceId')):
        raise ReviewError('review_scope_changed')
    root_id = root_binding['rootRunId']
    root = reader.get(root_id)
    if (root.get('parentAgentRunId') or root.get('continuation')
            or root.get('runKind') not in {'foreground', 'background'}
            or root.get('clientRequestId') != root_binding['rootClientRequestId']):
        raise ReviewError('review_root_unavailable')
    reasons, accepted, queue = set(), {}, [(root_id, None)]
    while queue:
        rid, edge = queue.pop(0)
        if rid in accepted:
            reasons.add('relationship_cycle'); continue
        try:
            record = reader.get(rid)
            candidate = binding(record.get('reviewBinding'))
            if (candidate != root_binding or record.get('sessionId') != scope['sessionId']):
                raise ReviewError('review_relationship_invalid')
            if edge:
                kind, parent, call_id = edge
                if kind == 'child':
                    if (record.get('parentAgentRunId') != parent['id']
                            or record.get('parentToolCallId') != call_id
                            or record.get('runKind') != 'child' or parent.get('runKind') == 'child'):
                        raise ReviewError('review_relationship_invalid')
                else:
                    cont = record.get('continuation') or {}
                    parent_cont = parent.get('continuation') or {}
                    if (record.get('parentAgentRunId') or record.get('runKind') != 'foreground'
                            or cont.get('parentRunId') != parent['id'] or cont.get('rootRunId') != root_id
                            or cont.get('rootClientRequestId') != root_binding['rootClientRequestId']
                            or type(cont.get('index')) is not int
                            or cont['index'] != parent_cont.get('index', 0) + 1
                            or (parent.get('result') or {}).get('continuation', {}).get('clientRequestId') != record.get('clientRequestId')):
                        raise ReviewError('review_relationship_invalid')
            accepted[rid] = record
            for edge_index, (call_id, execution) in enumerate(record.get('toolExecutions', {}).items()):
                if edge_index >= OPERATIONS:
                    reasons.add('review_operation_limit'); break
                if not isinstance(execution, dict):
                    reasons.add('invalid_execution'); continue
                child = execution.get('childAgentRunId')
                if child:
                    if execution.get('name') != 'task':
                        reasons.add('relationship_invalid'); continue
                    if len(queue) >= MEMBERS:
                        reasons.add('review_member_limit'); break
                    queue.append((child, ('child', record, call_id)))
            successor = (record.get('result') or {}).get('continuation')
            if successor:
                if isinstance(successor, dict) and record.get('runKind') != 'child' and len(queue) < MEMBERS:
                    queue.append((successor.get('agentRunId'), ('continuation', record, None)))
                else:
                    reasons.add('relationship_invalid')
        except (ReviewError, TypeError, AttributeError) as exc:
            if rid == root_id:
                raise ReviewError('review_root_unavailable') from None
            reasons.add(exc.code if isinstance(exc, ReviewError) else 'relationship_invalid')
    if requested_id not in accepted:
        raise ReviewError('review_unassociated_run', 404)
    operations, bodies, file_keys, receipt_ids = [], {}, set(), {}
    scanned = 0
    terminal = all(r.get('status') in TERMINAL for r in accepted.values())
    if not terminal:
        reasons.add('running_members')
    steer_count = 0
    for rid, record in accepted.items():
        steers = record.get('steerReceipts', [])
        steer_count += sum(isinstance(s, dict) and s.get('status') == 'consumed' for s in steers) if isinstance(steers, list) else 0
        for call_id, execution in record.get('toolExecutions', {}).items():
            scanned += 1
            if scanned > OPERATIONS:
                reasons.add('review_operation_limit'); break
            if not text(call_id, 256) or not isinstance(execution, dict):
                reasons.add('invalid_execution'); continue
            name = execution.get('name')
            result = execution.get('result')
            if not isinstance(result, dict):
                result = {}
            action = result.get('action')
            if name == 'task':
                if not execution.get('childAgentRunId'):
                    reasons.add('missing_child')
                continue
            if name in READ_TOOLS or (isinstance(name, str) and name.startswith('goal_')):
                continue
            if name not in {'write_file', 'delete_file', 'propose_edit', 'apply_edit'}:
                reasons.add('uncovered_tool'); continue
            if result.get('rejected') or result.get('proposalOnly') or result.get('cancelledBeforeStart'):
                continue
            if execution.get('status') == 'waiting_authorization':
                continue
            if result.get('replayed') or execution.get('replayedFromCheckpoint'):
                reasons.add('replay_without_fresh_receipt'); continue
            if (execution.get('status') != 'completed' or result.get('ok') is not True or result.get('replayed') is not False
                    or action not in {'write_file', 'apply_edit', 'delete_file'}
                    or (action == 'apply_edit' and result.get('applied') is not True)):
                reasons.add('unconfirmed_effect'); continue
            receipt = result.get('fileChange')
            if (not isinstance(receipt, dict) or receipt.get('schema') != RECEIPT
                    or not canonical_path(receipt.get('canonicalPath')) or receipt.get('fileKey') != digest(receipt['canonicalPath'])
                    or receipt.get('kind') not in {'create', 'update', 'delete'}
                    or receipt.get('entityKind') not in {'file', 'directory'}
                    or (receipt.get('entityKind') == 'directory' and receipt.get('kind') != 'delete')
                    or not text(receipt.get('operationId'), 256)
                    or receipt.get('diffSemantics') != 'normalized-lines'
                    or (action == 'delete_file') != (receipt['kind'] == 'delete')):
                reasons.add('missing_file_receipt'); continue
            op_id = receipt['operationId']
            expected_op = result.get('proposalId') if action == 'apply_edit' else execution.get('operationId')
            if op_id != expected_op:
                reasons.add('operation_identity_conflict'); continue
            dedupe_key = (rid, op_id)
            proof = digest([receipt, action, result.get('diff'), result.get(DELETE_PRIVATE)])
            if dedupe_key in receipt_ids:
                if receipt_ids[dedupe_key] != proof:
                    reasons.add('operation_identity_conflict')
                continue
            receipt_ids[dedupe_key] = proof
            diff = result.get('diff')
            if (receipt['kind'] != 'delete' and
                    (not isinstance(diff, str) or hashlib.sha256(diff.encode()).hexdigest() != receipt.get('diffSha256'))):
                reasons.add('diff_unavailable'); continue
            body_state = 'not-retained' if receipt['kind'] == 'delete' else 'diff' if diff else 'no-line-diff'
            body_reason = receipt.get('bodyReason') if receipt.get('bodyReason') in DELETE_REASONS else 'not-retained'
            delete_verified = False
            if receipt['kind'] == 'delete' and receipt.get('deleteEvidenceSchema') is not None:
                try:
                    if receipt['entityKind'] != 'file':
                        raise ValueError('unverifiable')
                    diff = verified_delete_diff(result, receipt)
                    body_state = 'diff' if diff else 'no-line-diff'
                    delete_verified = True
                except (ValueError, TypeError, KeyError, UnicodeError):
                    diff = None; body_state = 'not-retained'; body_reason = 'unverifiable'
                    reasons.add('delete_evidence_unavailable')
            if isinstance(diff, str) and (len(diff.encode()) > DIFF_BYTES or len(diff.splitlines()) > DIFF_LINES):
                body_state = 'limit'; reasons.add('review_diff_limit')
            if receipt['entityKind'] == 'file' and receipt['fileKey'] not in file_keys:
                if len(file_keys) >= FILES:
                    reasons.add('review_file_limit'); continue
                file_keys.add(receipt['fileKey'])
            key = digest([scope, rid, call_id])
            item = {'operationKey': key, 'runId': rid, 'toolCallId': call_id,
                    'groupKey': digest([root_id, rid, receipt['fileKey']]),
                    'fileKey': receipt['fileKey'], 'path': receipt['canonicalPath'],
                    'kind': receipt['kind'], 'entityKind': receipt['entityKind'],
                    'bodyState': body_state, 'diffSemantics': 'normalized-lines',
                    'lineStats': line_stats(diff) if body_state == 'diff' else {'additions': 0, 'deletions': 0} if delete_verified else None}
            if receipt['kind'] == 'delete' and not delete_verified:
                item['bodyReason'] = body_reason
            operations.append(item)
            bodies[key] = diff if body_state == 'diff' else ''
    payload = {'schema': SCHEMA, **scope, 'rootRunId': root_id,
               'rootClientRequestId': root_binding['rootClientRequestId'],
               'originRoot': root_binding['originRoot'], 'terminal': terminal,
               'steerCount': steer_count, 'recordedFileCount': len(file_keys),
               'operations': operations, 'coverage': {'complete': not reasons, 'reasons': sorted(reasons)}}
    if len(json.dumps(payload, ensure_ascii=False).encode()) > SUMMARY_BYTES - 128:
        reasons.add('review_summary_limit')
        payload['operations'] = []; payload['recordedFileCount'] = 0
        payload['coverage'] = {'complete': False, 'reasons': sorted(reasons)}
        bodies = {}
    payload['revision'] = digest([payload, reader.raw_hashes])
    reader.verify()
    if read_scope() != scope:
        raise ReviewError('review_scope_changed')
    if operation is not None:
        if revision != payload['revision']:
            raise ReviewError('review_changed')
        item = next((x for x in payload['operations'] if x['operationKey'] == operation), None)
        if item is None:
            raise ReviewError('review_missing_operation', 404)
        return {'schema': SCHEMA, 'revision': payload['revision'], **item, 'diff': bodies[operation]}
    return payload
