"""User-source traceability, not an authorization or natural-language classifier."""
import copy
import hashlib
import json
from .goal_v2_protocol import GoalV2ProtocolError, normalize_source_reference

PURPOSES = ('input', 'judgment', 'authorization')


def policy(value):
    if value is None:
        return None
    if type(value) is not int or value != 1:
        raise ValueError('goal_acceptance_policy_invalid')
    return value


def bind(reference, sources):
    raw_fields = {'messageId', 'quote', 'purpose'}
    if not isinstance(reference, dict):
        raise GoalV2ProtocolError('sourceReference must be an object with messageId, quote and purpose')
    missing = raw_fields - set(reference)
    if missing:
        raise GoalV2ProtocolError('sourceReference is missing required fields: ' + ', '.join(sorted(missing)))
    if set(reference) - raw_fields - {'version', 'contentHash'}:
        raise GoalV2ProtocolError('sourceReference has unknown fields; remove fields outside the declared schema')
    if 'version' in reference and (type(reference['version']) is not int or reference['version'] != 1):
        raise GoalV2ProtocolError('sourceReference.version must be integer 1 when provided')
    if 'contentHash' in reference:
        supplied_hash = reference['contentHash']
        if (not isinstance(supplied_hash, str) or len(supplied_hash) != 64
                or any(c not in '0123456789abcdef' for c in supplied_hash)):
            raise GoalV2ProtocolError('sourceReference.contentHash must be a 64-character lowercase SHA-256 when provided')
    message_id, quote, purpose = (reference[k] for k in ('messageId', 'quote', 'purpose'))
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 128 or message_id not in sources:
        raise GoalV2ProtocolError('sourceReference.messageId must identify an eligible user source; use a supplied source ID')
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        raise GoalV2ProtocolError('sourceReference.purpose must be input, judgment or authorization')
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 1000:
        raise GoalV2ProtocolError('sourceReference.quote must contain 1-1000 characters of nonblank source text')
    if quote not in sources[message_id]:
        raise GoalV2ProtocolError('sourceReference.quote is not an exact substring of the selected user source; copy its original wording')
    compiled = {'version': 1, 'messageId': message_id, 'quote': quote, 'purpose': purpose,
                'contentHash': hashlib.sha256(sources[message_id].encode('utf-8')).hexdigest()}
    if 'contentHash' in reference and reference['contentHash'] != compiled['contentHash']:
        raise GoalV2ProtocolError('sourceReference.contentHash does not match the selected source; supply its matching SHA-256')
    return normalize_source_reference(compiled)


def plan(steps, sources, previous=None):
    compiled = copy.deepcopy(steps)
    prior = {(s['id'], c['id']): c for s in previous or [] for c in s.get('acceptanceCriteria') or []}
    if not isinstance(compiled, list):
        raise GoalV2ProtocolError('Goal plan must be an array')
    for step in compiled:
        if not isinstance(step, dict):
            raise GoalV2ProtocolError('Goal plan step must be an object')
        for criterion in step.get('acceptanceCriteria') or []:
            if not isinstance(criterion, dict):
                raise GoalV2ProtocolError('Goal criterion must be an object')
            old = prior.get((step.get('id'), criterion.get('id')))
            if old and all(criterion.get(k) == old.get(k) for k in ('id', 'kind', 'description', 'sourceReference')):
                continue  # preserve unknown legacy and frozen canonical references verbatim
            if criterion.get('kind') == 'user' or 'sourceReference' in criterion:
                criterion['sourceReference'] = bind(criterion.get('sourceReference'), sources)
    # The existing reducer still owns started-step immutability and legal
    # pending-step revision. Provenance must not create another permission regime.
    return compiled


def receipt_sources(run, extra_messages=()):
    """Read existing controller receipts; model/tool prose never creates one."""
    run_id = str(run.get('id') or '')
    receipts = run.get('steer_receipts', run.get('steerReceipts', [])) or []
    wanted = {r.get('messageHash') for r in receipts[-128:] if isinstance(r, dict) and r.get('status') == 'consumed'}
    by_hash = {}
    for message in list(run.get('messages') or [])[-50000:] + list(extra_messages):
        if not wanted:
            break
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        content = message.get('content')
        if not isinstance(content, (str, list)):
            continue
        payload = json.dumps({'role':'user','content':content}, ensure_ascii=False, sort_keys=True, separators=(',',':'))
        if len(payload) > 2 * 1024 * 1024:
            continue
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        if digest not in wanted:
            continue
        text = content if isinstance(content, str) else '\n'.join(p.get('text','') for p in content if isinstance(p,dict) and p.get('type')=='text' and isinstance(p.get('text'),str))
        if text.strip(): by_hash[digest] = text
    found = {}
    for receipt in receipts[-128:]:
        if (isinstance(receipt,dict) and receipt.get('status') == 'consumed'
                and receipt.get('messageHash') in by_hash and receipt.get('steerId')):
            key = 'steer-' + run_id + '-' + str(receipt['steerId'])
            found[key] = by_hash[receipt['messageHash']]
    executions = run.get('tool_executions', run.get('toolExecutions', {})) or {}
    for call_id, execution in list(executions.items())[-50000:]:
        if not isinstance(execution,dict) or execution.get('name') != 'request_user_input' or execution.get('status') != 'completed':
            continue
        result = execution.get('result') or {}
        if (not isinstance(result,dict) or result.get('ok') is not True or result.get('action') != 'request_user_input'
                or result.get('requestId') != 'user-input-' + str(call_id)):
            continue
        for answer in result.get('answers') or []:
            if not isinstance(answer,dict) or answer.get('status') != 'resolved':
                continue
            text = answer.get('text') if answer.get('type') == 'text' else answer.get('answer')
            if not isinstance(text,str) or not text.strip():
                continue
            suffix = hashlib.sha256((str(call_id)+'\0'+str(answer.get('id') or '')).encode()).hexdigest()[:24]
            found['answer-' + run_id + '-' + suffix] = text  # never quote the model-authored question/prompt
    return dict(list(found.items())[-128:])
