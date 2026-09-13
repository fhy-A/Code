import copy
import json
from pathlib import Path
import pytest
import server as srv
from code_runtime import goal_acceptance, goal_v2_protocol
from test_goal_v2_agentrun import isolated_server, _origin_message, _persist_session, _create_run, _call, _plan, SESSION_ID
from test_goal_closeout import _worker, _tool, _final, _read_args, _ready_last


def source(mid, quote, purpose='input'):
    return {'messageId': mid, 'quote': quote, 'purpose': purpose}


def waiting_run(root, purpose='input', legacy=False, with_data=False, supplied=None):
    text = supplied or ('Later I will provide final input.' if purpose == 'input' else 'Wait for my explicit confirmation.')
    if with_data: text = 'Later I will provide final input. ' + text
    origin = _origin_message('acceptance-first', 'acceptance-origin');origin['content'] = text
    _persist_session(SESSION_ID, [origin])
    run = _create_run('acceptance-first', permission_profile='bypass');run['cwd'] = str(root)
    if legacy: run['goal_acceptance_policy'] = None
    assert _call(run,'goal_create',{'objective':'Implement and test, then verify final supplied values.'},'create')['ok']
    plan = _plan();criterion={'id':'user-input','kind':'user','description':text}
    if not legacy: criterion['sourceReference']=source(origin['id'],text,purpose)
    plan[-1]['acceptanceCriteria'].append(criterion)
    if with_data:
        data_criterion={'id':'data-input','kind':'user','description':'Later I will provide final input.'}
        if not legacy: data_criterion['sourceReference']=source(origin['id'],'Later I will provide final input.')
        plan[-1]['acceptanceCriteria'].append(data_criterion)
    assert _call(run,'goal_set_plan',{'steps':plan},'plan')['ok']
    assert _call(run,'goal_start_step',{'stepId':'step-1'},'start')['ok'];_ready_last(run)
    assert _call(run,'goal_raise_gate',{'gateType':'waiting_user','summary':text},'wait')['ok']
    run['status']='model'
    return run


def followup(root, text, client='acceptance-next', message_id='acceptance-next-origin'):
    existing=srv.read_jsonl(srv.messages_path(SESSION_ID))
    message=_origin_message(client,message_id);message['content']=text
    _persist_session(SESSION_ID,[*existing,message])
    run=_create_run(client,permission_profile='bypass');run['cwd']=str(root)
    run['messages'][-1]['content']=text
    return run


def batch(*pairs):
    return {'content':'','toolCalls':[{'id':'control-'+str(i),'type':'function',
        'function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate(pairs)],'finishReason':'tool_calls','usage':{}}


def evidence(mid, quote, purpose='input'):
    return [{'criterionId':'criterion-3','kind':'machine','summary':'The isolated equality check succeeded.'},
            {'criterionId':'user-input','kind':'user','summary':'The required user input is now supplied.',
             'sourceReference':source(mid,quote,purpose)}]


def test_objective_comparison_closes_original_goal_without_completion_reminder(isolated_server,monkeypatch):
    first=waiting_run(isolated_server);original=srv.goal_v2_runtime().read(SESSION_ID).state.goal['goalId']
    text="Input Alpha and alpha; expected ['alpha']. Run, compare, and report the result."
    run=followup(isolated_server,text)
    command='python -B -c "actual=sorted(set(v.casefold() for v in [\'Alpha\',\'alpha\'])); expected=[\'alpha\']; print(actual==expected)"'
    def complete():
        result=run['tool_executions']['comparison']['result']
        assert result['ok'] and 'True' in (result.get('stdout') or result.get('output') or '')
        return batch(('goal_clear_gate',{}),('goal_complete_step',{'stepId':'step-3','evidence':evidence('acceptance-next-origin',text)}))
    payloads=_worker(monkeypatch,run,[_tool('run_command',{'command':command},'comparison'),_final('The comparison matched.'),
        lambda:_tool('goal_read',_read_args(run),'read-current'),complete,_final('The computed result matches the supplied expected value.')])
    assert run['status']=='completed',run.get('error')
    goal=srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['goalId']==original and goal['lifecycle']=='completed' and goal['gate'] is None
    assert len(payloads)==5 and sum(e.get('name')=='run_command' for e in run['tool_executions'].values())==1
    restored=srv._agent_run_from_record(srv._agent_run_record(run));assert restored['goal_acceptance_policy']==1
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['steps'][-1]['evidence'][-1]['sourceReference']['messageId']=='acceptance-next-origin'


@pytest.mark.parametrize('purpose',['input','judgment','authorization'])
def test_real_missing_input_or_explicit_user_gate_stays_waiting(isolated_server,monkeypatch,purpose):
    run=waiting_run(isolated_server,purpose)
    before=srv.goal_v2_runtime().read(SESSION_ID).projection()
    _worker(monkeypatch,run,[lambda:_tool('goal_read',_read_args(run,decision='wait',criterionIds=['user-input'],nextAction='Wait for the required user response.'),'read-wait'),_final('Waiting for the required user response.')])
    assert run['status']=='completed' and srv.goal_v2_runtime().read(SESSION_ID).projection()==before


def test_unrelated_question_neither_creates_nor_closes_goal(isolated_server,monkeypatch):
    waiting_run(isolated_server,'judgment');before=srv.goal_v2_runtime().read(SESSION_ID).projection()
    run=followup(isolated_server,'Explain a separate language feature; leave the pending acceptance alone.')
    _worker(monkeypatch,run,[lambda:_tool('goal_read',_read_args(run,'unrelated'),'unrelated'),_final('Here is the requested explanation.')])
    assert run['status']=='completed' and srv.goal_v2_runtime().read(SESSION_ID).projection()==before


def test_requirement_quote_is_not_itself_later_user_acceptance(isolated_server):
    run=waiting_run(isolated_server,'judgment')
    assert _call(run,'goal_clear_gate',{},'clear')['ok']
    result=_call(run,'goal_complete_step',{'stepId':'step-3','evidence':evidence('acceptance-origin','Wait for my explicit confirmation.','judgment')},'false-acceptance')
    assert not result['ok'] and srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle']=='active'


def test_old_unknown_user_condition_is_not_downgraded_or_auto_accepted(isolated_server):
    waiting_run(isolated_server,legacy=True);before=srv.goal_v2_runtime().read(SESSION_ID).projection()
    run=followup(isolated_server,'The machine output matched; report it.')
    plan=copy.deepcopy(before['goal']['steps'])
    for step in plan:
        step.pop('status',None);step.pop('evidence',None)
        if step['id']=='step-3': step['acceptanceCriteria']=[c for c in step['acceptanceCriteria'] if c['kind']!='user']
    result = _call(run,'goal_revise_plan',{'steps':plan},'downgrade')
    assert not result['ok'] and 'started step step-3 cannot change acceptance criteria' in str(result)
    assert srv.goal_v2_runtime().read(SESSION_ID).projection()==before


@pytest.mark.parametrize('bad',[None,{}, {'messageId':'fabricated','quote':'real','purpose':'input'},
    {'messageId':'user','quote':'invented','purpose':'input'},{'messageId':'user','quote':'real','purpose':'comparison'}])
def test_source_claim_without_matching_user_text_is_rejected(bad):
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):goal_acceptance.bind(bad,{'user':'real user input'})


def test_optional_policy_and_reference_recovery_are_strict(isolated_server):
    run=waiting_run(isolated_server);record=srv._agent_run_record(run)
    record.pop('goalAcceptancePolicy');assert srv._agent_run_from_record(record)['goal_acceptance_policy'] is None
    for bad in [True,2,'1',{}]:
        with pytest.raises(ValueError):srv._agent_run_from_record({**record,'goalAcceptancePolicy':bad})
    reference=goal_acceptance.bind(source('user','real'),{'user':'real user input'})
    assert goal_v2_protocol.normalize_source_reference(reference)==reference
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):goal_v2_protocol.normalize_source_reference({**reference,'version':2})


@pytest.mark.parametrize('legacy',[False,True])
def test_three_runs_can_reuse_middle_input_and_later_confirm_started_goal(isolated_server,monkeypatch,legacy):
    first=waiting_run(isolated_server,'judgment',legacy=legacy,with_data=True)
    before=srv.goal_v2_runtime().read(SESSION_ID).projection();original=before['goal']['goalId']
    supplied="Samples Alpha and alpha; expected ['alpha']. Run the check; I will confirm later."
    middle=followup(isolated_server,supplied,'middle-request','middle-user')
    command='python -B -c "actual=sorted(set(v.casefold() for v in [\'Alpha\',\'alpha\'])); print(actual==[\'alpha\'])"'
    _worker(monkeypatch,middle,[_tool('run_command',{'command':command},'middle-check'),
        lambda:_tool('goal_read',_read_args(middle,decision='wait',criterionIds=['user-input'],nextAction='Wait for the explicitly requested confirmation.'),'middle-wait'),_final('The check matched; awaiting the requested confirmation.')])
    assert middle['status']=='completed' and 'True' in (middle['tool_executions']['middle-check']['result'].get('stdout') or '')
    assert srv.goal_v2_runtime().read(SESSION_ID).projection()==before
    confirmation='I confirm the computed result meets my acceptance condition. Continue.'
    last=followup(isolated_server,confirmation,'last-request','last-user')
    sources=srv._agent_goal_user_sources(last,before['goal'])
    assert sources['middle-user']==supplied and sources['last-user']==confirmation
    final_evidence=evidence('last-user',confirmation,'judgment') + [{'criterionId':'data-input','kind':'user',
        'summary':'The input supplied in the middle Run was used.', 'sourceReference':source('middle-user',supplied)}]
    _worker(monkeypatch,last,[lambda:_tool('goal_read',_read_args(last),'last-read'),
        batch(('goal_clear_gate',{}),('goal_complete_step',{'stepId':'step-3','evidence':final_evidence})),_final('The original goal is complete.')])
    assert last['status']=='completed',last.get('error')
    goal=srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['goalId']==original and goal['lifecycle']=='completed'
    assert goal['steps'][-1]['acceptanceCriteria']==before['goal']['steps'][-1]['acceptanceCriteria']
    by_id={e['criterionId']:e for e in goal['steps'][-1]['evidence']}
    assert by_id['data-input']['sourceReference']['messageId']=='middle-user'
    assert by_id['user-input']['sourceReference']['messageId']=='last-user'


def test_source_window_excludes_system_assistant_future_and_duplicate_ids(isolated_server):
    waiting_run(isolated_server)
    original=srv.read_jsonl(srv.messages_path(SESSION_ID))
    middle=_origin_message('middle','middle');middle['content']='Real middle input.'
    system=_origin_message('system','system');system['meta']['_system']=True
    assistant=_origin_message('assistant','assistant');assistant['role']='assistant'
    _persist_session(SESSION_ID,original+[middle,system,assistant])
    run=followup(isolated_server,'Current real user message.','current','current')
    future=_origin_message('future','future');future['content']='Not yet consumed by this Run.'
    _persist_session(SESSION_ID,srv.read_jsonl(srv.messages_path(SESSION_ID))+[future,dict(middle,role='tool-result')])
    sources=srv._agent_goal_user_sources(run,srv.goal_v2_runtime().read(SESSION_ID).state.goal)
    assert set(sources)=={'acceptance-origin','current'}
    page=srv._agent_goal_source_view(run,srv.goal_v2_runtime().read(SESSION_ID).state.goal,offset=0)
    assert page['total']==2 and page['historyBoundaryKnown'] and page['scannedBytes']<=64*1024*1024


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('large', [False, True])
def test_pending_revision_preserves_unchanged_old_or_canonical_user_condition(isolated_server, legacy, large):
    origin = _origin_message('revision', 'revision-origin'); origin['content'] = '😀'*1000 if large else 'Ask me for final acceptance.'
    _persist_session(SESSION_ID, [origin]); run = _create_run('revision')
    run['goal_acceptance_policy'] = None if legacy else 1
    assert _call(run, 'goal_create', {'objective': 'Three stages with explicit acceptance.'}, 'create')['ok']
    plan = _plan()
    if large:
        for step in plan:
            step['description'] = '😀'*1800
            step['acceptanceCriteria'][0]['description'] = '😀'*1800
    criterion = {'id': 'approval', 'kind': 'user', 'description': origin['content']}
    if not legacy: criterion['sourceReference'] = source(origin['id'], origin['content'], 'judgment')
    plan[0]['acceptanceCriteria'].append(criterion)
    assert _call(run, 'goal_set_plan', {'steps': plan}, 'plan')['ok']
    started = _call(run, 'goal_start_step', {'stepId': 'step-1'}, 'start')
    assert started['ok']
    run['goal_acceptance_policy'] = 1
    # Assemble solely from actual goal_read responses, including all text cursors.
    read_count = 0
    def read(**extra):
        nonlocal read_count
        read_count += 1
        result = _call(run, 'goal_read', {'goalId':started['goal']['goalId'], 'expectedRevision':started['revision'],
            'relation':'related','reason':'Preserve current conditions and revise a pending stage.', **extra}, 'page-'+str(read_count))
        assert result['ok'] and len(json.dumps(result,ensure_ascii=True,separators=(',',':'))) <= 24000
        return result
    summary = read()
    revised = []
    for summary_step in summary['goal']['steps']:
        sid = summary_step['id']; page = read(stepId=sid,offset=0)['goal']['steps'][0]
        step = {'id':sid,'description':page['description'],'acceptanceCriteria':[]}
        cursor = page['descriptionNextOffset']
        while cursor is not None:
            next_page = read(stepId=sid,offset=0,textOffset=cursor)['goal']['steps'][0]
            step['description'] += next_page['description']; cursor = next_page['descriptionNextOffset']
        for index in range(page['criteriaTotal']):
            c = read(stepId=sid,offset=index)['goal']['steps'][0]['acceptanceCriteria'][0]
            criterion = {k:v for k,v in c.items() if k not in ('descriptionOffset','descriptionNextOffset')}
            cursor = c['descriptionNextOffset']
            while cursor is not None:
                next_c = read(stepId=sid,offset=index,textOffset=cursor)['goal']['steps'][0]['acceptanceCriteria'][0]
                criterion['description'] += next_c['description']; cursor = next_c['descriptionNextOffset']
            step['acceptanceCriteria'].append(criterion)
        revised.append(step)
    assert revised[0]['description'] == plan[0]['description']
    frozen_condition = copy.deepcopy(revised[0]['acceptanceCriteria'][-1])
    if not legacy:
        assert frozen_condition['sourceReference']['quote'] == origin['content']
        assert frozen_condition['sourceReference']['version'] == 1
    revised[1]['description'] = 'Refine the still pending second stage.'
    result = _call(run, 'goal_revise_plan', {'steps': revised}, 'revise')
    assert result['ok'], result
    assert result['goal']['steps'][0]['acceptanceCriteria'][-1] == frozen_condition
    assert result['goal']['steps'][1]['description'] == revised[1]['description']


def test_already_provided_input_can_use_original_source(isolated_server):
    text = "Use input Alpha and alpha; expected ['alpha']."
    run = waiting_run(isolated_server, supplied=text)
    assert _call(run,'goal_clear_gate',{},'clear')['ok']
    # This tests source timing only: input is not a future judgment/permission.
    result = _call(run,'goal_complete_step', {'stepId':'step-3', 'evidence':
        evidence('acceptance-origin',text)}, 'same-input')
    assert result['ok']


def test_consumed_steer_is_citable_after_restore_and_context_compaction(isolated_server):
    run = waiting_run(isolated_server, 'judgment'); goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    text = 'I confirm the computed result satisfies my acceptance condition.'
    receipt = srv._submit_agent_steer(run, text, 'real-steer')
    assert not goal_acceptance.receipt_sources(run)
    srv._consume_agent_steers(run)
    sources = srv._agent_goal_user_sources(run, goal)
    mid = next(k for k,v in sources.items() if v == text)
    assert mid.endswith(receipt['steerId'])
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert goal_acceptance.receipt_sources(restored)[mid] == text
    restored['messages'] = [{'role':'system', 'content':'Compacted context.'}]
    assert not goal_acceptance.receipt_sources(restored)
    # The persisted Session supplies bytes, while the consumed receipt proves origin.
    msg = _origin_message('steer-ui', 'steer-ui'); msg['content'] = text
    _persist_session(SESSION_ID, srv.read_jsonl(srv.messages_path(SESSION_ID)) + [msg])
    assert srv._agent_goal_user_sources(restored, goal)[mid] == text
    bad = copy.deepcopy(srv._agent_run_record(run)); bad['steerReceipts'][0]['messageHash'] = '0'*64
    assert not goal_acceptance.receipt_sources(bad)


def ask(run, monkeypatch):
    run['tools'].append(srv._SERVER_TOOL_DEFINITIONS['request_user_input'])
    _worker(monkeypatch, run, [_tool('request_user_input', {'questions':[
        {'id':'acceptance','type':'single','prompt':'Provide the required acceptance response.','required':True,
         'allowOther':True,'options':[
             {'value':'accept','label':'Accepted','description':'The reviewed result meets the requirement.','recommended':True},
             {'value':'revise','label':'Needs revision','description':'The requirement remains unmet.','recommended':False}]}]}, 'ask-acceptance')])
    assert run['status'] == 'waiting_user_input', run.get('error')


def test_actual_question_reply_invalidates_wait_and_closes_same_goal(isolated_server, monkeypatch):
    run = waiting_run(isolated_server, 'judgment'); goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    ask(run, monkeypatch)
    before = srv._agent_goal_input_key(run)
    assert not goal_acceptance.receipt_sources(run)
    text = 'I explicitly confirm this result meets my acceptance.'
    srv._submit_agent_input(run, [{'id':'acceptance','status':'resolved','other':text}])
    assert srv._agent_goal_input_key(run) != before
    sources = srv._agent_goal_user_sources(run, goal)
    mid = next(k for k,v in sources.items() if v == text)
    assert 'Provide the required acceptance response.' not in sources.values()
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert goal_acceptance.receipt_sources(restored)[mid] == text
    monkeypatch.setattr(srv, '_start_agent_worker', lambda *a, **k: None)
    srv._resume_agent_run(restored, ['synthetic'])
    _worker(monkeypatch, restored, [lambda:_tool('goal_read',_read_args(restored),'answer-read'),
        batch(('goal_clear_gate',{}), ('goal_complete_step', {'stepId':'step-3','evidence':evidence(mid,text,'judgment')})),
        _final('The original goal is complete.')])
    assert restored['status'] == 'completed', restored.get('error')
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'completed'


def test_previous_run_controller_reply_is_available_to_later_run(isolated_server, monkeypatch):
    run = waiting_run(isolated_server, 'judgment'); ask(run, monkeypatch)
    text = 'I approve the result after reviewing it.'
    srv._submit_agent_input(run, [{'id':'acceptance','status':'resolved','other':text}])
    rows = srv.read_jsonl(srv.messages_path(SESSION_ID))
    rows.append({'id':'receipt-row','role':'assistant','content':'Question answered.', 'meta':{'agentRunId':run['id']}})
    _persist_session(SESSION_ID, rows)
    later = followup(isolated_server, 'Continue from my previous answer.')
    goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    sources = srv._agent_goal_user_sources(later, goal)
    assert text in sources.values()
    record = srv._agent_run_record(run); record['sessionId'] = 'different-session'
    srv.write_json(srv._agent_run_path(run['id']), record)
    assert text not in srv._agent_goal_user_sources(later, goal).values()


def test_canonical_reference_rejects_changed_hash():
    ref = goal_acceptance.bind(source('actual', 'Actual user input.'), {'actual':'Actual user input.'})
    assert goal_acceptance.bind(ref, {'actual':'Actual user input.'}) == ref
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):
        goal_acceptance.bind(ref, {'actual':'Actual user input. Added words.'})
    padded = ' '*1000 + 'x'
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):
        goal_acceptance.bind(source('actual',padded), {'actual':padded})
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):
        goal_v2_protocol.normalize_source_reference({**ref,'quote':padded})


@pytest.mark.parametrize('cancelled', [False, True])
def test_question_choice_and_cancellation_use_only_actual_controller_result(isolated_server, monkeypatch, cancelled):
    run = waiting_run(isolated_server, 'judgment'); ask(run, monkeypatch)
    before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    reply = {'id':'acceptance','status':'canceled' if cancelled else 'resolved','values':[] if cancelled else ['accept']}
    srv._submit_agent_input(run, [reply])
    sources = goal_acceptance.receipt_sources(run)
    assert list(sources.values()) == ([] if cancelled else ['Accepted'])
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert goal_acceptance.receipt_sources(restored) == sources
    forged = copy.deepcopy(srv._agent_run_record(run))
    forged['toolExecutions']['ask-acceptance']['result']['requestId'] = 'different-request'
    assert not goal_acceptance.receipt_sources(forged)


def test_restored_pre_policy_tool_snapshot_keeps_bounded_closeout_without_new_parameters(isolated_server, monkeypatch):
    from test_goal_v2_agentrun import _active_goal_run
    run = _active_goal_run(); _ready_last(run)
    legacy = json.loads((Path(__file__).parent/'fixtures/goal-legacy-tools.json').read_text(encoding='utf-8'))
    record = srv._agent_run_record(run); record.pop('goalAcceptancePolicy')
    record['tools'] = [legacy['tools'].get(t['function']['name'],t) for t in record['tools']]
    restored = srv._agent_run_from_record(record)
    assert restored['goal_closeout_enabled'] and restored['goal_acceptance_policy'] is None
    monkeypatch.setattr(srv, '_start_agent_worker', lambda *a, **k: None)
    srv._resume_agent_run(restored, ['synthetic'])
    requests = _worker(monkeypatch, restored, [_final('Work is checked.'),
        _tool('goal_complete_step', {'stepId':'step-3','evidence':[{'criterionId':'criterion-3','kind':'machine','summary':'Existing isolated check passed.'}]}, 'legacy-complete'),
        _final('The existing Goal is complete.')])
    assert restored['status'] == 'completed', restored.get('error')
    assert len(requests) == 3 and 'tools' not in requests[-1]
    assert 'One bounded Goal closeout check' in json.dumps(requests[1]['messages'])
    for request in requests:
        prompts='\n'.join(str(m.get('content') or '') for m in request['messages'] if m.get('role')=='system')
        assert 'sourceReference' not in prompts and 'userSource' not in prompts
        for definition in request.get('tools',[]):
            name=definition['function']['name']
            if name.startswith('goal_'): assert definition == legacy['tools'][name]
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle']=='completed'


def test_new_policy_request_includes_only_callable_source_contract(isolated_server):
    run=waiting_run(isolated_server)
    payload,_=srv._agent_model_payload(run)
    prompts='\n'.join(str(m.get('content') or '') for m in payload['messages'] if m.get('role')=='system')
    assert 'sourceReference' in prompts and 'userSourceReferences' in prompts
    schemas={t['function']['name']:t['function']['parameters'] for t in payload['tools']}
    assert 'userSourceOffset' in schemas['goal_read']['properties']
