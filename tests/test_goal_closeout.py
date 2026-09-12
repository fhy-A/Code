from __future__ import annotations

import json
import pytest
import server as srv
from test_goal_v2_agentrun import (
    isolated_server, _active_goal_run, _call, _create_run, _origin_message,
    _persist_session, _model_runtime_stub, SESSION_ID,
)


def _worker(monkeypatch, run, responses):
    payloads = []
    pending = iter(responses)
    monkeypatch.setattr(srv, '_create_model_runtime_run', lambda *args, **kw: (
        payloads.append(args[1]) or _model_runtime_stub('fake-' + str(len(payloads)))
    ))
    def response(*args, **kwargs):
        item = next(pending)
        return {'status': 'completed', 'result': item() if callable(item) else item}
    monkeypatch.setattr(srv, '_agent_wait_for_model', response)
    srv._agent_run_worker(run)
    return payloads


def _final(content='The requested work is complete.'):
    return {'content': content, 'toolCalls': [], 'finishReason': 'stop', 'usage': {}}


@pytest.mark.parametrize('text', ['The requested work is complete.',
                                  'A required acceptance condition is still missing; more work is needed.'])
def test_final_without_goal_disposition_is_not_accepted(isolated_server, monkeypatch, text):
    run = _active_goal_run()
    _worker(monkeypatch, run, [_final(text)] * 4)
    assert run['status'] == 'failed'
    assert run['error_code'] == 'goal_closeout_unresolved'
    goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['lifecycle'] == 'active'
    assert goal['gate']['type'] == 'blocked'


def test_request_has_fresh_goal_ids_and_evidence(isolated_server):
    run = _active_goal_run()
    projection = srv.goal_v2_runtime().read(SESSION_ID).projection()
    payload, _ = srv._agent_model_payload(run)
    text = '\n'.join(str(m.get('content') or '') for m in payload['messages'])
    assert projection['goal']['goalId'] in text
    assert 'criterion-1' in text
    assert 'goal_read' in text


def _tool(name, arguments, call_id='model-call'):
    return {'content': '', 'toolCalls': [{'id': call_id, 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments)}}], 'finishReason': 'tool_calls', 'usage': {}}


def _read_args(run, relation='related', **extra):
    p = srv.goal_v2_runtime().read(run['session_id']).projection()
    return {'goalId': p['goal']['goalId'], 'expectedRevision': p['revision'],
            'relation': relation, 'reason': 'This message ' + relation + ' to the confirmed goal.', **extra}


def _next_run(content='Continue the original task'):
    rid = 'next-request'
    path = srv.messages_path(SESSION_ID)
    messages = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    message = _origin_message(rid, 'next-origin')
    message['content'] = content
    _persist_session(SESSION_ID, [*messages, message])
    run = _create_run(rid)
    run['messages'][-1]['content'] = content
    return run


def _ready_last(run):
    for i in (1, 2):
        if i != 1:
            assert _call(run, 'goal_start_step', {'stepId': f'step-{i}'}, f's{i}')['ok']
        assert _call(run, 'goal_complete_step', {'stepId': f'step-{i}', 'evidence': [{
            'criterionId': f'criterion-{i}', 'kind': 'machine', 'summary': f'Isolated check {i} passed',
        }]}, f'c{i}')['ok']
    assert _call(run, 'goal_start_step', {'stepId': 'step-3'}, 's3')['ok']


@pytest.mark.parametrize('omitted_final', [False, True])
def test_completion_receipt_then_exactly_one_no_tool_final(isolated_server, monkeypatch, omitted_final):
    run = _active_goal_run()
    _ready_last(run)
    responses = ([_final()] if omitted_final else []) + [_tool('goal_complete_step', {
        'stepId': 'step-3', 'evidence': [{'criterionId': 'criterion-3', 'kind': 'machine',
                                      'summary': 'Required isolated verification passed; optional release not authorized.'}],
    }), _final('All required acceptance checks passed. Optional release was not requested.')]
    payloads = _worker(monkeypatch, run, responses)
    assert run['status'] == 'completed'
    assert len(payloads) == (3 if omitted_final else 2)
    assert 'tools' not in payloads[-1]
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'completed'
    assert sum(e['type'] == 'agent_completed' for e in run['events']) <= 1


@pytest.mark.parametrize('relation', ['status', 'unrelated'])
@pytest.mark.parametrize('late', [False, True])
def test_status_and_unrelated_do_not_write_goal(isolated_server, monkeypatch, relation, late):
    _active_goal_run()
    run = _next_run('What is the task status?' if relation == 'status' else 'Translate this sentence.')
    before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    payloads = _worker(monkeypatch, run, ([_final()] if late else []) + [
        _tool('goal_read', _read_args(run, relation)), _final('Requested answer only.'),
    ])
    assert run['status'] == 'completed'
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before
    assert run['goal_closeout']['relation'] == relation
    assert run['goal_closeout']['sourceCallId'] == 'model-call'
    assert len(payloads) == (3 if late else 2)
    with pytest.raises(srv.GoalV2ContextError):
        srv._agent_goal_prepare_operation(run, {'id': 'forbidden-clear',
            'function': {'name': 'goal_clear_gate'}, 'arguments': {}}, {})
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


def test_remaining_work_can_continue_but_cannot_rearm_check(isolated_server, monkeypatch):
    run = _active_goal_run()
    args = _read_args(run, decision='continue', criterionIds=['criterion-1'], nextAction='Run the required isolated check')
    payloads = _worker(monkeypatch, run, [_final('More work remains.'),
        _tool('goal_read', args), _tool('goal_raise_gate', {
            'gateType': 'waiting_user', 'summary': 'criterion-1 needs user observation. Resume after user supplies the observation.',
        }, 'wait'), _final('Waiting for criterion-1 observation.')])
    assert run['status'] == 'completed'
    assert run['goal_closeout']['phase'] == 'resumed'
    assert run['goal_closeout']['checkRound'] == 1
    assert 'tools' not in payloads[-1]
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['gate']['type'] == 'waiting_user'


def test_waiting_user_later_related_message_reads_evidence_and_recovers(isolated_server, monkeypatch):
    first = _active_goal_run()
    _ready_last(first)
    assert _call(first, 'goal_raise_gate', {'gateType': 'waiting_user', 'summary': 'criterion-3: confirm required observation'}, 'wait')['ok']
    run = _next_run('The required observation passed; finish the confirmed goal.')
    read = _call(run, 'goal_read', _read_args(run), 'read-new')
    assert read['ok'] and read['goal']['steps'][0]['evidence'][0]['criterionId'] == 'criterion-1'
    assert _call(run, 'goal_clear_gate', {}, 'resume-gate')['ok']
    payloads = _worker(monkeypatch, run, [_tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
        'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Required observation confirmed in this synthetic input',
    }]}), _final()])
    assert run['status'] == 'completed' and len(payloads) == 2
    assert not any(e['name'] in {'goal_start_step', 'goal_set_plan'} for e in run['tool_executions'].values())


@pytest.mark.parametrize('lifecycle', ['paused', 'cancelled', 'gate'])
def test_existing_pause_cancel_gate_not_cleared_by_final(isolated_server, monkeypatch, lifecycle):
    initial = _active_goal_run()
    rt = srv.goal_v2_runtime(); p = rt.read(SESSION_ID).projection()
    common = dict(source_run_id=initial['id'], expected_revision=p['revision'], idempotency_key='user-control')
    if lifecycle == 'paused': rt.pause(SESSION_ID, p['goal']['goalId'], reason='user paused', **common)
    elif lifecycle == 'cancelled': rt.cancel_goal(SESSION_ID, p['goal']['goalId'], reason='user cancelled', **common)
    else: rt.raise_gate(SESSION_ID, p['goal']['goalId'], 'blocked', 'External condition missing', **common)
    before = rt.read(SESSION_ID).projection()
    run = _next_run('Explain current state only.')
    _worker(monkeypatch, run, [_tool('goal_read', _read_args(run, 'status')),
                                _final('Current state explained.')])
    assert run['status'] == 'completed'
    assert rt.read(SESSION_ID).projection() == before


def test_closeout_blocks_business_tools_and_plan_changes(isolated_server, monkeypatch):
    run = _active_goal_run()
    payloads = _worker(monkeypatch, run, [_final(), _tool('write_file', {'path': 'forbidden.txt', 'content': 'no'})])
    assert run['error_code'] == 'goal_closeout_unresolved'
    assert not run['tool_executions'].get('model-call')
    assert {d['function']['name'] for d in payloads[1]['tools']} <= srv.goal_closeout.CHECK_TOOLS
    assert not (isolated_server / 'forbidden.txt').exists()


def test_stale_read_and_stale_completion_do_not_mutate(isolated_server):
    run = _active_goal_run()
    args = _read_args(run)
    srv._agent_model_payload(run)
    rt = srv.goal_v2_runtime(); p = rt.read(SESSION_ID).projection()
    rt.raise_gate(SESSION_ID, p['goal']['goalId'], 'blocked', 'Concurrent gate', source_run_id=run['id'],
                  expected_revision=p['revision'], idempotency_key='concurrent-gate')
    revision = rt.read(SESSION_ID).state.revision
    assert not _call(run, 'goal_read', args, 'stale-read')['ok']
    assert not _call(run, 'goal_complete_step', {'stepId': 'step-1', 'evidence': [{
        'criterionId': 'criterion-1', 'kind': 'machine', 'summary': 'must not apply',
    }]}, 'stale-complete')['ok']
    assert rt.read(SESSION_ID).state.revision == revision


def test_restart_preserves_consumed_check_and_gate_replay(isolated_server, monkeypatch):
    run = _active_goal_run()
    run['rounds'].append({'round': 1, 'content': 'candidate'})
    assert srv._agent_goal_closeout_candidate(run, _final()) == 'continue'
    record = srv._agent_run_record(run)
    rebuilt = srv._agent_run_from_record(record)
    rebuilt['status'] = 'model'
    _worker(monkeypatch, rebuilt, [_final()])
    assert rebuilt['status'] == 'failed'
    assert rebuilt['goal_closeout']['checkRound'] == 1
    revision = srv.goal_v2_runtime().read(SESSION_ID).state.revision
    again = srv._agent_run_from_record(srv._agent_run_record(rebuilt))
    again['status'] = 'model'
    assert srv._agent_goal_before_model(again) is False
    assert srv.goal_v2_runtime().read(SESSION_ID).state.revision == revision


def test_old_run_defaults_and_unknown_control_state_fail_closed(isolated_server):
    run = _active_goal_run()
    old = srv._agent_run_record(run); old.pop('goalCloseout', None)
    restored = srv._agent_run_from_record(old)
    assert restored['goal_closeout_enabled'] is False
    assert srv._agent_goal_closeout_candidate(restored, _final()) == 'none'
    assert 'goalCloseout' not in srv._agent_run_record(restored)
    for field, value in [('version', 2), ('runId', 'wrong'), ('checkRound', 999), ('relation', 'invented')]:
        record = srv._agent_run_record(run)
        record['goalCloseout'][field] = value
        with pytest.raises(ValueError): srv._agent_run_from_record(record)


def test_read_receipt_replay_does_not_reset_spent_budget(isolated_server):
    run = _active_goal_run()
    run['rounds'].append({'round': 1, 'content': 'candidate'})
    srv._agent_goal_closeout_candidate(run, _final())
    args = _read_args(run, decision='continue', criterionIds=['criterion-1'], nextAction='Required check')
    assert _call(run, 'goal_read', args, 'read-once')['ok']
    rebuilt = srv._agent_run_from_record(srv._agent_run_record(run))
    state = dict(rebuilt['goal_closeout'])
    execution = rebuilt['tool_executions']['read-once']
    call = {'id': 'read-once', 'function': {'name': 'goal_read'}, 'arguments': args}
    assert srv._execute_agent_goal_operation(rebuilt, call, execution)['ok']
    assert rebuilt['goal_closeout'] == state


def test_model_projection_does_not_silently_drop_ten_criteria_or_completed_evidence(isolated_server):
    run = _active_goal_run(); _ready_last(run)
    p = srv.goal_v2_runtime().read(SESSION_ID).projection()
    p['goal']['steps'][2]['acceptanceCriteria'] = [
        {'id': f'criterion-extra-{i}', 'kind': 'machine', 'description': f'condition {i}'} for i in range(10)]
    projected = srv.goal_closeout.project(p)
    assert len(projected['goal']['steps'][2]['acceptanceCriteria']) == 10
    assert projected['goal']['steps'][0]['evidence'][0]['sourceRunId'] == run['id']
    assert projected['goal']['steps'][2]['omittedCriteria'] == 0
    # Drop all prior tool receipts as compaction would. The next request still gets current authoritative IDs.
    run['messages'] = [{'role': 'system', 'content': 'Original safety'}, {'role': 'user', 'content': 'Continue'}]
    payload, _ = srv._agent_model_payload(run)
    assert payload['messages'][0]['content'] == 'Original safety'
    text = '\n'.join(str(x.get('content') or '') for x in payload['messages'])
    assert p['goal']['goalId'] in text and 'criterion-1' in text and 'sourceToolCallId' in text


def test_large_projection_declares_truncation_and_paged_criteria(isolated_server):
    run = _active_goal_run(); p = srv.goal_v2_runtime().read(SESSION_ID).projection()
    p['goal']['objective'] = '目' * 8000
    for step in p['goal']['steps']:
        step['description'] = '步' * 2000
        step['acceptanceCriteria'] = [{'id': f"{step['id']}-c{i}", 'kind': 'machine',
                                      'description': '条' * 2000} for i in range(20)]
    projected = srv.goal_closeout.project(p)
    assert projected['truncated']
    assert len(json.dumps(projected, ensure_ascii=True, separators=(',', ':'))) <= 24000
    page = srv.goal_closeout.project(p, step_id='step-1', offset=9)
    assert page['goal']['steps'][0]['acceptanceCriteria'][0]['id'] == 'step-1-c9'
    chunks = []
    cursor = 0
    while cursor is not None:
        part = srv.goal_closeout.project(p, step_id='step-1', offset=9, text_offset=cursor)
        criterion = part['goal']['steps'][0]['acceptanceCriteria'][0]
        chunks.append(criterion['description'])
        next_cursor = criterion['descriptionNextOffset']
        assert next_cursor is None or next_cursor > cursor
        cursor = next_cursor
    assert ''.join(chunks) == '条' * 2000
    assert page['goal']['steps'][0]['nextOffset'] == 10


def test_continuation_has_fixed_remaining_bound_no_successor(isolated_server, monkeypatch):
    run = _active_goal_run()
    args = _read_args(run, decision='continue', criterionIds=['criterion-1'], nextAction='Inspect required evidence')
    responses = [_final()] + [_tool('goal_read', args, f'continue-{i}') for i in range(15)]
    payloads = _worker(monkeypatch, run, responses)
    assert len(payloads) == 1 + srv.goal_closeout.CONTINUE_ROUNDS
    assert run['status'] == 'failed' and run['error_code'] == 'goal_closeout_unresolved'
    assert run['goal_closeout']['checkRound'] == 1
    assert not srv._handoff_agent_goal_run(run, reason='must not spawn from closeout')
    goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['gate']['type'] == 'blocked' and 'criterion-1' in goal['gate']['summary']


def test_continuation_preserves_original_tool_budget_and_one_dispatch(isolated_server, monkeypatch):
    run = _active_goal_run()
    dispatched = []
    monkeypatch.setitem(srv.SERVER_TOOL_REGISTRY['list_files'], 'execute', lambda args: (
        dispatched.append(args) or {'ok': True, 'action': 'list_files', 'items': []}))
    payloads = _worker(monkeypatch, run, [_final(), _tool('goal_read', _read_args(run,
        decision='continue', criterionIds=['criterion-1'], nextAction='Inspect allowed workspace once')),
        _tool('list_files', {'path': str(isolated_server)}, 'read-business'),
        _tool('goal_raise_gate', {'gateType': 'waiting_user', 'summary': 'criterion-1 awaits user observation'}, 'wait'),
        _final('Awaiting user observation for criterion-1.')])
    assert len(dispatched) == 1 and run['status'] == 'completed'
    assert len(payloads) == 5
    assert 'goal_revise_plan' not in {t['function']['name'] for t in payloads[1]['tools']}
    assert 'list_files' in {t['function']['name'] for t in payloads[2]['tools']}
    assert 'tools' not in payloads[-1]


def test_crash_after_fallback_gate_commit_replays_no_second_event(isolated_server, monkeypatch):
    run = _active_goal_run(); run['rounds'].append({'round': 1, 'content': 'candidate'})
    srv._agent_goal_closeout_candidate(run, _final())
    original = srv.GoalV2Runtime.raise_gate
    def crash(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise SystemExit('simulated process loss after event commit')
    monkeypatch.setattr(srv.GoalV2Runtime, 'raise_gate', crash)
    with pytest.raises(SystemExit):
        srv._agent_goal_closeout_candidate(run, _final())
    saved = json.loads(srv._agent_run_path(run['id']).read_text(encoding='utf-8'))
    assert saved['goalCloseout']['phase'] == 'stopping'
    revision = srv.goal_v2_runtime().read(SESSION_ID).state.revision
    monkeypatch.setattr(srv.GoalV2Runtime, 'raise_gate', original)
    rebuilt = srv._agent_run_from_record(saved); rebuilt['status'] = 'model'
    assert srv._agent_goal_before_model(rebuilt) is False
    assert srv.goal_v2_runtime().read(SESSION_ID).state.revision == revision
    assert rebuilt['goal_closeout']['phase'] == 'stopped'


def test_corrupt_goal_does_not_accept_final_or_clear_previous_state(isolated_server, monkeypatch):
    run = _active_goal_run()
    monkeypatch.setattr(srv, '_agent_goal_projection', lambda run: {'health': 'corrupt', 'goal': None, 'revision': 0})
    assert srv._agent_goal_closeout_candidate(run, _final()) == 'done'
    assert run['error_code'] == 'goal_closeout_unresolved'
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['gate'] is None


def test_cancel_while_checking_never_raises_gate(isolated_server, monkeypatch):
    run = _active_goal_run(); before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    srv._agent_goal_closeout_candidate(run, _final())
    monkeypatch.setattr(srv, '_create_model_runtime_run', lambda *a, **k: _model_runtime_stub('cancelled'))
    def cancel(*args, **kwargs):
        run['cancel_event'].set()
        return {'status': 'cancelled'}
    monkeypatch.setattr(srv, '_agent_wait_for_model', cancel)
    srv._agent_run_worker(run)
    assert run['status'] == 'cancelled'
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


@pytest.mark.parametrize('kind,depth,parent', [('child', 1, 'parent-run'), ('background', 0, '')])
def test_goal_read_does_not_grant_child_or_background_authority(isolated_server, kind, depth, parent):
    _active_goal_run()
    rid = 'not-foreground'; _persist_session(SESSION_ID, [_origin_message(rid)])
    run = _create_run(rid, run_kind=kind, agent_depth=depth, parent_run_id=parent)
    assert 'goal_read' not in {x['function']['name'] for x in run['tools']}
    assert srv._agent_goal_closeout_candidate(run, _final()) == 'none'
    with pytest.raises(srv.GoalV2ContextError):
        srv._agent_goal_read(run, {'arguments': _read_args(run)}, {})
    assert 'goal_read' not in srv.SERVER_TOOL_REGISTRY


def test_final_goal_step_waits_for_real_skill_completion_evaluation(isolated_server, monkeypatch):
    from test_skill_completion import _plan as skill_plan, _lifecycle, _outcome, _SPECS
    run = _active_goal_run(); _ready_last(run)
    plan = skill_plan()
    evaluation = srv.skill_completion.evaluate(plan, _outcome(_lifecycle()), _SPECS)
    assert evaluation['status'] == 'recoverable'
    monkeypatch.setattr(srv, '_agent_skill_completion_evaluate', lambda run: (plan, evaluation))
    result = _call(run, 'goal_complete_step', {'stepId': 'step-3', 'evidence': [{
        'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'must not bypass Skill evidence',
    }]}, 'too-early')
    assert not result['ok']
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'active'


def test_consumed_skill_repair_cannot_open_second_goal_repair(isolated_server, monkeypatch):
    from test_skill_completion import _plan as skill_plan, _lifecycle, _outcome, _SPECS
    run = _active_goal_run()
    plan = skill_plan(); evaluation = srv.skill_completion.evaluate(plan, _outcome(_lifecycle()), _SPECS)
    plan = srv.skill_completion.begin_continuation(plan, evaluation, run['id'], 0, 'candidate')
    plan = srv.skill_completion.advance(plan, 'finalizing')
    monkeypatch.setattr(srv, '_agent_skill_completion_evaluate', lambda run: (plan, {'status': 'satisfied'}))
    assert srv._agent_skill_completion_finish(run, True, candidate=_final()) == 'done'
    assert run['goal_closeout']['phase'] == 'stopped'
    assert run['goal_closeout']['checkRound'] == 0
    assert run['error_code'] == 'goal_closeout_unresolved'


def test_frontend_real_formatter_retains_ids_evidence_and_declares_truncation(isolated_server):
    import subprocess
    from pathlib import Path
    run = _active_goal_run(); _ready_last(run)
    p = srv.goal_v2_runtime().read(SESSION_ID).projection()
    p['goal']['steps'][2]['acceptanceCriteria'] = [
        {'id': f'c{i}', 'kind': 'machine', 'description': 'check'} for i in range(10)]
    script = '''global.window = global; global.Code = {features: {}};
require('./src/features/skills-memory.js');
const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(Code.features.skillsMemory.formatGoalModelProjection(data));'''
    value = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                           input=json.dumps(p), text=True, capture_output=True, check=True, encoding='utf-8')
    formatted = json.loads(value.stdout.split('GOAL_CONTEXT_JSON=', 1)[1])
    assert formatted['goalId'] == p['goal']['goalId']
    assert len(formatted['steps'][2]['acceptanceCriteria']) == 10
    assert formatted['steps'][2]['acceptanceCriteria'][9]['id'] == 'c9'
    assert formatted['steps'][0]['evidence'][0]['criterionId'] == 'criterion-1'
    assert formatted['read']['tool'] == 'goal_read'


def test_relationship_declaration_is_frozen_until_new_input(isolated_server):
    _active_goal_run(); run = _next_run('Only explain current status.')
    assert _call(run, 'goal_read', _read_args(run, 'status'), 'status-read')['ok']
    assert not _call(run, 'goal_read', _read_args(run, 'related'), 'switch-relation')['ok']
    assert run['goal_closeout']['relation'] == 'status'
    # An explicit new steer is a new auditable input, not an automatic reclassification.
    run['steer_receipts'] = [{'id': 'new-input', 'content': 'Now continue the actual work.'}]
    srv._agent_model_payload(run)
    assert _call(run, 'goal_read', _read_args(run, 'related'), 'related-read')['ok']


def test_no_tool_final_is_enforced_even_if_model_returns_a_tool(isolated_server, monkeypatch):
    run = _active_goal_run(); _ready_last(run)
    dispatched = []
    monkeypatch.setitem(srv.SERVER_TOOL_REGISTRY['write_file'], 'execute', lambda args: dispatched.append(args))
    payloads = _worker(monkeypatch, run, [
        _tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
            'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Required check passed',
        }]}, 'finish'), _tool('write_file', {'path': str(isolated_server / 'must-not-write'), 'content': 'bad'}, 'bad-final'),
    ])
    assert 'tools' not in payloads[-1]
    assert dispatched == []
    assert run['status'] == 'failed'
    assert run['error_code'] == 'goal_final_response_tool_call'
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'completed'


def test_gate_disposition_cannot_reopen_business_dispatch(isolated_server, monkeypatch):
    run = _active_goal_run()
    dispatched = []
    monkeypatch.setitem(srv.SERVER_TOOL_REGISTRY['write_file'], 'execute', lambda args: dispatched.append(args))
    _worker(monkeypatch, run, [_final(),
        _tool('goal_read', _read_args(run, decision='continue', criterionIds=['criterion-1'], nextAction='Inspect required evidence')),
        _tool('goal_raise_gate', {'gateType': 'waiting_user', 'summary': 'Wait for criterion-1 observation'}, 'wait'),
        _tool('write_file', {'path': str(isolated_server / 'must-not-write'), 'content': 'bad'}, 'bad-gate-final')])
    assert dispatched == [] and run['status'] == 'failed'
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['gate']['type'] == 'waiting_user'


def test_maximum_unicode_descriptions_have_forward_only_read_cursors(isolated_server):
    import copy
    run = _active_goal_run(); p = srv.goal_v2_runtime().read(SESSION_ID).projection()
    p['goal']['objective'] = '🧭' * 20000
    original = p['goal']['steps'][0]
    p['goal']['steps'] = []
    for i in range(8):
        step = copy.deepcopy(original); step.update(id=f'step-{i}', description='🧭' * 4000,
            status='active' if i == 0 else 'pending', acceptanceCriteria=[{
                'id': f'criterion-{i}-{j}', 'kind': 'machine', 'description': '🧭' * 4000,
            } for j in range(20)])
        p['goal']['steps'].append(step)
    p['goal']['currentStepId'] = 'step-0'
    overview = srv.goal_closeout.project(p)
    assert overview['truncated']
    assert len(json.dumps(overview, ensure_ascii=True, separators=(',', ':'))) <= 22000
    parts, cursor = [], 0
    while cursor is not None:
        page = srv.goal_closeout.project(p, step_id='step-0', offset=19, text_offset=cursor)
        item = page['goal']['steps'][0]['acceptanceCriteria'][0]
        assert len(json.dumps(page, ensure_ascii=True, separators=(',', ':'))) <= 22000
        parts.append(item['description']); next_cursor = item['descriptionNextOffset']
        assert next_cursor is None or next_cursor > cursor
        cursor = next_cursor
    assert ''.join(parts) == '🧭' * 4000


@pytest.mark.parametrize('cancel_steer', [False, True])
def test_real_skill_evidence_satisfied_then_goal_check_is_not_reconsumed(isolated_server, monkeypatch, cancel_steer):
    from code_runtime.skill_activation import SKILL_PROMPT_MARKER
    initial = _active_goal_run(); _ready_last(initial)
    skills = isolated_server / 'skills'; skill = skills / 'completion-probe'; skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: completion-probe\ndescription: isolated completion\nallowed-tools: list_files\n---\nFixture.', encoding='utf-8')
    (skill / 'evidence.json').write_text(json.dumps({'schemaVersion': 2, 'requirements': [{
        'id': 'inspect', 'type': 'tool_execution', 'tool': 'list_files', 'minCount': 1,
    }], 'enforcement': {'schemaVersion': 2, 'mode': 'owner_completion_once', 'activationKinds': ['explicit']}}), encoding='utf-8')
    monkeypatch.setattr(srv, 'SKILLS_DIR', skills)
    monkeypatch.setattr(srv, '_SKILL_ACTIVATION_ENABLED', True)
    monkeypatch.setattr(srv, '_SKILL_IMMUTABLE_ADMISSION_ENABLED', False)
    monkeypatch.setattr(srv, '_SKILL_COMPLETION_ENFORCEMENT_ENABLED', True)
    rid = 'skill-goal-related'; message = _origin_message(rid, 'skill-goal-origin')
    _persist_session(SESSION_ID, [message])
    run = srv._create_agent_run(SESSION_ID, {'model': 'fake-model', 'messages': [
        {'role': 'system', 'content': 'safety\n\n' + SKILL_PROMPT_MARKER},
        {'role': 'user', 'content': 'Verify and finish the original Goal'},
    ]}, 'http://127.0.0.1:1', [], allowed_tools={'schemaVersion': 1, 'names': ['list_files']},
        permission_profile='bypass', start_worker=False, client_request_id=rid, run_kind='foreground',
        cwd=str(isolated_server), skill_activation_request={'schemaVersion': 1, 'explicitSkill': 'completion-probe', 'disabledNames': []})
    assert _call(run, 'goal_read', _read_args(run), 'bind-related')['ok']
    assert run['skill_completion_enforcement']['phase'] == 'armed'
    responses = [_tool('list_files', {'path': str(isolated_server)}, 'inspect'),
        _final('Skill evidence satisfied; omitted Goal closeout')]
    if cancel_steer:
        def new_input():
            srv._submit_agent_steer(run, 'Cancel this Goal now; keep the existing inspection result.', 'skill-cancel')
            return _final('Old candidate must not consume the new input.')
        responses += [new_input, _tool('goal_cancel', {'reason': 'User explicitly cancelled the Goal'}, 'cancel-goal'),
                      _final('The Goal is cancelled; the inspection result is retained.')]
    else:
        responses += [
        _tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
            'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Required isolated inspection succeeded',
        }]}, 'complete-goal'), _final('Goal and Skill complete.')]
    payloads = _worker(monkeypatch, run, responses)
    assert run['status'] == 'completed'
    assert len(payloads) == (5 if cancel_steer else 4)
    assert run['skill_completion_enforcement']['phase'] == 'passed'
    assert run['goal_closeout']['checkRound'] == 2
    assert 'tools' not in payloads[-1]
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == ('cancelled' if cancel_steer else 'completed')
    assert sum(e['name'] == 'list_files' for e in run['tool_executions'].values()) == 1


@pytest.mark.parametrize('spent', [0, 2, 3])
@pytest.mark.parametrize('restore', [False, True])
def test_r002_explicit_cancel_steer_survives_exhausted_closeout(isolated_server, monkeypatch, spent, restore):
    run = _active_goal_run()
    run['rounds'].append({'round': 1, 'content': 'old candidate'})
    srv._agent_goal_closeout_candidate(run, _final())
    run['rounds'].extend({'round': n + 2} for n in range(spent))
    run['status'] = 'model'
    receipt = srv._submit_agent_steer(run, 'Cancel this Goal now; do not continue the work.', 'cancel-input')
    if restore:
        run = srv._agent_run_from_record(srv._agent_run_record(run))
        run['status'] = 'model'
    payloads = _worker(monkeypatch, run, [_tool('goal_cancel', {'reason': 'User explicitly cancelled this Goal.'}),
                                        _final('The Goal is cancelled.')])
    goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['lifecycle'] == 'cancelled'
    assert goal['gate'] is None
    assert run['status'] == 'completed'
    assert len(payloads) == 2
    assert 'Cancel this Goal now' in json.dumps(payloads[0]['messages'])
    assert run['goal_closeout']['checkRound'] == 1
    assert run['steer_receipts'][0]['steerId'] == receipt['steerId']
    assert run['steer_receipts'][0]['status'] == 'consumed'
    assert srv._submit_agent_steer(run, 'Cancel this Goal now; do not continue the work.', 'cancel-input')['duplicate']
    assert {e['name'] for e in run['tool_executions'].values()} <= {
        'goal_create', 'goal_set_plan', 'goal_start_step', 'goal_cancel'}


def test_r002_old_wait_gate_cannot_hide_new_related_missing_disposition(isolated_server, monkeypatch):
    first = _active_goal_run(); _ready_last(first)
    assert _call(first, 'goal_raise_gate', {'gateType': 'waiting_user',
        'summary': 'criterion-3 requires user observation'}, 'old-wait')['ok']
    before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    run = _next_run('The required acceptance observation passed; finish the Goal.')
    assert _call(run, 'goal_read', _read_args(run), 'related-read')['ok']
    payloads = _worker(monkeypatch, run, [_final('All requested work is done.')] * 3)
    assert len(payloads) == 2  # first omission arms check; second cannot silently succeed
    assert run['status'] == 'failed' and run['error_code'] == 'goal_closeout_unresolved'
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


@pytest.mark.parametrize('when', ['checking', 'exhausted', 'gate_final'])
def test_r002_cancel_arriving_with_old_final_is_seen_by_next_request(isolated_server, monkeypatch, when):
    run = _active_goal_run()
    responses = [_final('Prior candidate')]
    if when == 'exhausted':
        responses.append(_tool('goal_read', _read_args(run)))
    if when == 'gate_final':
        responses.append(_tool('goal_raise_gate', {'gateType': 'waiting_user',
            'summary': 'criterion-1: user must confirm the result'}, 'current-wait'))
    def steer_with_old_final():
        srv._submit_agent_steer(run, 'Cancel this Goal now.', 'late-cancel')
        return _final('Old final that must not answer the new cancellation.')
    responses.extend([steer_with_old_final, _tool('goal_cancel', {'reason': 'User cancelled in latest steer'}, 'cancel'),
                      _final('The Goal is cancelled as requested.')])
    payloads = _worker(monkeypatch, run, responses)
    assert run['status'] == 'completed'
    assert len(payloads) == len(responses)
    assert 'Cancel this Goal now.' in json.dumps(payloads[-2]['messages'])
    assert 'goal_cancel' in {t['function']['name'] for t in payloads[-2]['tools']}
    if when == 'gate_final':
        assert 'tools' not in payloads[-3]
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'cancelled'
    remaining_gate = srv.goal_v2_runtime().read(SESSION_ID).state.goal['gate']
    # The original cancel reducer retains an existing gate for audit; no new gate is raised.
    assert remaining_gate is None if when != 'gate_final' else remaining_gate['type'] == 'waiting_user'
    assert 'Old final' not in run['result']['content']
    assert run['goal_closeout']['checkRound'] == 1
    assert sum(e['type'] == 'steer_consumed' for e in run['events']) == 1
    assert not any(e['name'] in {'write_file', 'run_command'} for e in run['tool_executions'].values())


def _old_waiting_goal():
    first = _active_goal_run(); _ready_last(first)
    assert _call(first, 'goal_raise_gate', {'gateType': 'waiting_user',
        'summary': 'criterion-3: awaiting user observation'}, 'old-wait')['ok']
    return srv.goal_v2_runtime().read(SESSION_ID).projection()


@pytest.mark.parametrize('relation', ['status', 'unrelated'])
def test_r002_old_wait_status_or_unrelated_has_no_goal_writes(isolated_server, monkeypatch, relation):
    before = _old_waiting_goal()
    run = _next_run('What is the status?' if relation == 'status' else 'Translate this sentence.')
    payloads = _worker(monkeypatch, run, [_tool('goal_read', _read_args(run, relation)), _final('Requested answer.')])
    assert run['status'] == 'completed' and len(payloads) == 2
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


@pytest.mark.parametrize('late', [False, True])
def test_r002_current_wait_confirmation_is_auditable_without_duplicate_gate(isolated_server, monkeypatch, late):
    before = _old_waiting_goal()
    run = _next_run('The observation is not available yet; keep waiting for it.')
    args = _read_args(run, decision='wait', criterionIds=['criterion-3'],
                      nextAction='Waiting for the user observation; resume when the user confirms criterion-3.')
    payloads = _worker(monkeypatch, run, ([_final('Still waiting.')] if late else []) + [
        _tool('goal_read', args, 'wait-read'), _final('Waiting for the required observation.')])
    assert run['status'] == 'completed' and len(payloads) == 2 + late
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before
    mark = run['goal_closeout']['gateDisposition']
    assert mark == {'inputKey': run['goal_closeout']['inputKey'], 'revision': before['revision'],
                    'sourceCallId': 'wait-read'}
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    state = dict(restored['goal_closeout'])
    assert srv._execute_agent_goal_operation(restored, {'id': 'wait-read', 'arguments': args,
        'function': {'name': 'goal_read'}}, restored['tool_executions']['wait-read'])['ok']
    assert restored['goal_closeout'] == state
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


def test_r002_omitted_wait_resolution_can_clear_and_complete_in_worker(isolated_server, monkeypatch):
    _old_waiting_goal()
    run = _next_run('The required observation passed. Finish this Goal.')
    assert _call(run, 'goal_read', _read_args(run), 'read-related')['ok']
    payloads = _worker(monkeypatch, run, [_final('Forgot to settle the inherited gate.'),
        _tool('goal_clear_gate', {}, 'clear'), _tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
            'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Required observation passed in isolated input',
        }]}, 'complete'), _final('The Goal is complete.')])
    assert run['status'] == 'completed' and len(payloads) == 4
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'completed'
    assert 'tools' not in payloads[-1]
    assert sum(bool(r.get('goalFinalResponse')) for r in run['rounds']) == 1
    assert {e['name'] for e in run['tool_executions'].values()} == {'goal_read', 'goal_clear_gate', 'goal_complete_step'}


def test_r002_successful_mutation_cannot_redeclare_status_or_unrelated(isolated_server):
    run = _active_goal_run()
    assert _call(run, 'goal_read', _read_args(run), 'related-after-mutation')['ok']
    before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    for relation in ('status', 'unrelated'):
        assert not _call(run, 'goal_read', _read_args(run, relation), 'reclassify-' + relation)['ok']
    assert run['goal_closeout']['relation'] == 'related'
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before


class _CloseoutCrash(BaseException):
    pass


def _crash():
    raise _CloseoutCrash()


@pytest.mark.parametrize('stage', ['armed', 'wait', 'cleared', 'completed'])
def test_r002_wait_resolution_worker_restart_preserves_budget_and_events(isolated_server, monkeypatch, stage):
    before = _old_waiting_goal()
    run = _next_run('The acceptance observation passed; finish the Goal.')
    assert _call(run, 'goal_read', _read_args(run), 'related')['ok']
    wait_args = _read_args(run, decision='wait', criterionIds=['criterion-3'],
        nextAction='Waiting for user to supply the remaining observation; resume after that observation.')
    complete = _tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
        'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Isolated required observation passed',
    }]}, 'complete')
    prefix = [_final('Old final omitted the disposition.')]
    tail = [_tool('goal_clear_gate', {}, 'clear'), complete, _final('Goal complete.')]
    if stage == 'wait':
        prefix.append(_tool('goal_read', wait_args, 'wait-read'))
        tail = [_final('Waiting for user observation.')]
    elif stage in {'cleared', 'completed'}:
        prefix.append(tail.pop(0))
        if stage == 'completed':
            prefix.append(tail.pop(0))
    with pytest.raises(_CloseoutCrash):
        _worker(monkeypatch, run, [*prefix, _crash])
    # Recover the actual persisted record from the worker boundary, not an invented state.
    saved = json.loads(srv._agent_run_path(run['id']).read_text(encoding='utf-8'))
    restored = srv._agent_run_from_record(saved)
    restored['status'] = 'model'
    mark = dict(restored['goal_closeout'])
    if stage == 'wait':
        assert srv._execute_agent_goal_operation(restored, {'id': 'wait-read', 'arguments': wait_args,
            'function': {'name': 'goal_read'}}, restored['tool_executions']['wait-read'])['ok']
        assert restored['goal_closeout'] == mark
    payloads = _worker(monkeypatch, restored, tail)
    assert restored['status'] == 'completed'
    assert restored['goal_closeout']['checkRound'] == mark['checkRound'] == 1
    after = srv.goal_v2_runtime().read(SESSION_ID).projection()
    if stage == 'wait':
        assert after == before
    else:
        assert after['goal']['lifecycle'] == 'completed'
        assert after['revision'] == before['revision'] + 2  # clear + atomic step evidence/completion
        assert 'tools' not in payloads[-1]
        assert sum(bool(r.get('goalFinalResponse')) for r in restored['rounds']) == 1


def test_r002_consumed_new_input_restore_has_one_control_window_only(isolated_server, monkeypatch):
    run = _active_goal_run()
    run['rounds'].append({'round': 1})
    srv._agent_goal_closeout_candidate(run, _final())
    run['rounds'].extend([{'round': 2}, {'round': 3}]); run['status'] = 'model'
    srv._submit_agent_steer(run, 'Inspect current requirements before deciding.', 'input-once')
    def read_current():
        return _tool('goal_read', _read_args(run), 'new-read')
    with pytest.raises(_CloseoutCrash):
        _worker(monkeypatch, run, [read_current, _crash])
    saved = json.loads(srv._agent_run_path(run['id']).read_text(encoding='utf-8'))
    restored = srv._agent_run_from_record(saved); restored['status'] = 'model'
    assert restored['goal_closeout']['inputRound'] == 3
    assert srv._submit_agent_steer(restored, 'Inspect current requirements before deciding.', 'input-once')['duplicate']
    payloads = _worker(monkeypatch, restored, [lambda: _tool('goal_read', _read_args(restored), 'read-again')])
    assert len(payloads) == 1
    assert restored['status'] == 'failed' and restored['error_code'] == 'goal_closeout_unresolved'
    assert restored['goal_closeout']['checkRound'] == 1
    assert restored['goal_closeout']['inputRound'] == 3


def test_r002_wait_confirmation_does_not_survive_revision_or_input_change(isolated_server):
    _old_waiting_goal()
    run = _next_run('Still waiting for the user observation.')
    args = _read_args(run, decision='wait', criterionIds=['criterion-3'], nextAction='Wait for user; resume after observation.')
    assert _call(run, 'goal_read', args, 'wait')['ok']
    projection = srv.goal_v2_runtime().read(SESSION_ID).projection()
    assert srv._agent_goal_disposition_confirmed(run, run['goal_closeout'], projection)
    changed = dict(projection, revision=projection['revision'] + 1)
    assert not srv._agent_goal_disposition_confirmed(run, run['goal_closeout'], changed)
    run['status'] = 'model'
    srv._submit_agent_steer(run, 'The observation passed now; finish.', 'new-acceptance')
    srv._consume_agent_steers(run)
    srv._agent_goal_state(run, projection)
    assert run['goal_closeout']['gateDisposition'] is None
    assert not srv._agent_goal_disposition_confirmed(run, run['goal_closeout'], projection)


def test_r002_optional_metadata_old_defaults_and_corruption_are_bounded(isolated_server):
    run = _active_goal_run()
    old = srv._agent_run_record(run)
    old['goalCloseout'].pop('inputRound'); old['goalCloseout'].pop('gateDisposition')
    restored = srv._agent_run_from_record(old)
    assert not srv._agent_goal_input_window(restored, restored['goal_closeout'])
    assert restored['goal_closeout'].get('gateDisposition') is None
    for field, invalid in [('inputRound', True), ('inputRound', 999), ('gateDisposition', {'revision': 1})]:
        broken = json.loads(json.dumps(old)); broken['goalCloseout'][field] = invalid
        with pytest.raises(ValueError):
            srv._agent_run_from_record(broken)


def test_r002_new_input_after_completion_receipt_is_not_answered_by_old_final(isolated_server, monkeypatch):
    run = _active_goal_run(); _ready_last(run)
    def new_question():
        srv._submit_agent_steer(run, 'Explain the retained acceptance evidence.', 'after-complete')
        return _final('Old completion final.')
    payloads = _worker(monkeypatch, run, [_final('Initial candidate'),
        _tool('goal_complete_step', {'stepId': 'step-3', 'evidence': [{
            'criterionId': 'criterion-3', 'kind': 'machine', 'summary': 'Passed isolated observation',
        }]}, 'complete'), new_question,
        lambda: _tool('goal_read', _read_args(run, 'status'), 'new-status'),
        _final('The retained evidence covers all three confirmed criteria.')])
    assert run['status'] == 'completed' and len(payloads) == 5
    assert 'tools' not in payloads[2]
    assert 'goal_read' in {t['function']['name'] for t in payloads[3]['tools']}
    assert 'Explain the retained acceptance evidence.' in json.dumps(payloads[3]['messages'])
    assert 'retained evidence covers' in run['result']['content']
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'completed'


def test_r002_exhausted_check_new_input_cannot_reopen_business_work(isolated_server, monkeypatch):
    run = _active_goal_run()
    run['rounds'].append({'round': 1}); srv._agent_goal_closeout_candidate(run, _final())
    run['rounds'].extend([{'round': 2}, {'round': 3}]); run['status'] = 'model'
    srv._submit_agent_steer(run, 'Continue with the required check.', 'no-renewal')
    args = _read_args(run, decision='continue', criterionIds=['criterion-1'], nextAction='Perform required check')
    dispatched = []
    monkeypatch.setitem(srv.SERVER_TOOL_REGISTRY['list_files'], 'execute', lambda args: dispatched.append(args))
    payloads = _worker(monkeypatch, run, [_tool('goal_read', args, 'continue'),
        _tool('list_files', {'path': str(isolated_server)}, 'business')])
    assert run['status'] == 'failed' and dispatched == []
    assert not run['tool_executions']['continue']['result']['ok']
    assert run['goal_closeout']['checkRound'] == 1
    assert all({t['function']['name'] for t in p.get('tools', [])} <= srv.goal_closeout.CHECK_TOOLS for p in payloads)


def test_r002_cancel_commit_crash_replays_original_cas_without_extra_event(isolated_server, monkeypatch):
    run = _active_goal_run()
    run['rounds'].append({'round': 1}); srv._agent_goal_closeout_candidate(run, _final())
    run['status'] = 'model'
    srv._submit_agent_steer(run, 'Cancel this Goal now.', 'crash-cancel-input')
    runtime = srv.goal_v2_runtime()
    original = type(runtime).cancel_goal
    def crash_after_commit(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise _CloseoutCrash()
    with monkeypatch.context() as scoped:
        scoped.setattr(type(runtime), 'cancel_goal', crash_after_commit)
        with pytest.raises(_CloseoutCrash):
            _worker(scoped, run, [_tool('goal_cancel', {'reason': 'Explicit user cancellation'}, 'cancel')])
    committed = runtime.read(SESSION_ID).projection()
    assert committed['goal']['lifecycle'] == 'cancelled'
    saved = json.loads(srv._agent_run_path(run['id']).read_text(encoding='utf-8'))
    restored = srv._agent_run_from_record(saved)
    assert restored['pending_tool_calls']
    payloads = _worker(monkeypatch, restored, [_final('The Goal is cancelled.')])
    assert restored['status'] == 'completed' and len(payloads) == 1
    assert runtime.read(SESSION_ID).projection() == committed
    assert restored['tool_executions']['cancel']['result']['ok']


def test_r002_wait_read_receipt_crash_finishes_pending_call_once(isolated_server, monkeypatch):
    before = _old_waiting_goal()
    run = _next_run('The observation is still unavailable; keep waiting.')
    args = _read_args(run, decision='wait', criterionIds=['criterion-3'],
        nextAction='Waiting for user observation; resume when it becomes available.')
    persist = srv._persist_agent_run
    def crash_after_receipt(candidate):
        persist(candidate)
        if candidate['tool_executions'].get('wait', {}).get('goalReadReceipt'):
            raise _CloseoutCrash()
    with monkeypatch.context() as scoped:
        scoped.setattr(srv, '_persist_agent_run', crash_after_receipt)
        with pytest.raises(_CloseoutCrash):
            _worker(scoped, run, [_final('Waiting, but omitted confirmation.'), _tool('goal_read', args, 'wait')])
    saved = json.loads(srv._agent_run_path(run['id']).read_text(encoding='utf-8'))
    restored = srv._agent_run_from_record(saved)
    assert restored['pending_tool_calls']
    mark = dict(restored['goal_closeout'])
    _worker(monkeypatch, restored, [_final('Still waiting for user observation.')])
    assert restored['status'] == 'completed'
    assert restored['goal_closeout'] == mark
    assert restored['tool_executions']['wait']['result']['ok']
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before
