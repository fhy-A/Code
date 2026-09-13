import copy
import hashlib
import json

import pytest
import server as srv
from code_runtime import goal_acceptance, goal_v2_protocol
from test_goal_acceptance import waiting_run, followup, evidence, batch
from test_goal_v2_agentrun import isolated_server, _call, SESSION_ID
from test_goal_closeout import _worker, _tool, _final, _read_args

TEXT = 'I reviewed the result and confirm acceptance. PRIVATE_SOURCE_SUFFIX'
QUOTE = 'I reviewed the result and confirm acceptance.'
RAW = {'messageId': 'actual-user', 'quote': QUOTE, 'purpose': 'judgment'}
DIGEST = hashlib.sha256(TEXT.encode()).hexdigest()


@pytest.mark.parametrize('extra', [{}, {'version':1}, {'contentHash':DIGEST}, {'version':1,'contentHash':DIGEST}])
def test_schema_optional_combinations_bind_to_identical_canonical_reference(extra):
    value = {**RAW, **extra}; before = copy.deepcopy(value)
    assert not srv._tool_schema_errors(value, srv._GOAL_SOURCE_REFERENCE_SCHEMA)
    result = goal_acceptance.bind(value, {'actual-user':TEXT})
    assert result == {**RAW, 'version':1, 'contentHash':DIGEST}
    assert value == before
    assert goal_v2_protocol.normalize_source_reference(result) == result


@pytest.mark.parametrize('value,field', [
    (None,'sourceReference'), ([], 'sourceReference'), ({},'messageId'),
    ({k:v for k,v in RAW.items() if k!='quote'},'quote'),
    ({k:v for k,v in RAW.items() if k!='purpose'},'purpose'),
    ({**RAW,'unknown':'DO_NOT_ECHO_THIS_VALUE'},'unknown fields'),
    ({**RAW,'version':True},'version'), ({**RAW,'version':0},'version'),
    ({**RAW,'version':2},'version'), ({**RAW,'version':'1'},'version'), ({**RAW,'version':1.0},'version'),
    ({**RAW,'version':None},'version'),
    ({**RAW,'contentHash':None},'contentHash'), ({**RAW,'contentHash':'x'},'contentHash'),
    ({**RAW,'contentHash':DIGEST.upper()},'contentHash'), ({**RAW,'contentHash':{}},'contentHash'),
    ({**RAW,'contentHash':'0'*64},'contentHash'),
    ({**RAW,'version':1,'contentHash':'0'*64},'contentHash'),
    ({**RAW,'purpose':'comparison'},'purpose'), ({**RAW,'purpose':[]},'purpose'),
    ({**RAW,'messageId':'unavailable'},'messageId'), ({**RAW,'messageId':[]},'messageId'),
    ({**RAW,'quote':'Wrong quote'},'quote'), ({**RAW,'quote':''},'quote'),
    ({**RAW,'quote':' '*10},'quote'), ({**RAW,'quote':'x'*1001},'quote'),
])
def test_errors_identify_field_without_echoing_private_source(value, field):
    before = copy.deepcopy(value)
    with pytest.raises(goal_v2_protocol.GoalV2ProtocolError) as caught:
        goal_acceptance.bind(value, {'actual-user':TEXT})
    message = str(caught.value)
    assert field in message and len(message) < 240
    assert TEXT not in message and QUOTE not in message and 'DO_NOT_ECHO_THIS_VALUE' not in message
    assert value == before
    if field in ('version','contentHash','unknown fields'):
        assert 'quote' not in message and 'goal_read' not in message


@pytest.mark.parametrize('value,schema_valid', [
    (RAW,True), ({**RAW,'version':1},True), ({**RAW,'contentHash':DIGEST},True),
    ({**RAW,'version':1,'contentHash':DIGEST},True),
    ({**RAW,'version':2},False), ({**RAW,'version':True},False),
    ({**RAW,'unexpected':'value'},False), ({'messageId':'actual-user','purpose':'judgment'},False),
])
def test_schema_shape_and_runtime_acceptance_agree(value, schema_valid):
    assert (not srv._tool_schema_errors(value,srv._GOAL_SOURCE_REFERENCE_SCHEMA)) == schema_valid
    if schema_valid:
        goal_acceptance.bind(value,{'actual-user':TEXT})
    else:
        with pytest.raises(goal_v2_protocol.GoalV2ProtocolError):
            goal_acceptance.bind(value,{'actual-user':TEXT})


def test_first_four_field_tool_attempt_completes_the_same_old_goal(isolated_server, monkeypatch):
    waiting_run(isolated_server, 'judgment', legacy=True)
    original = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    run = followup(isolated_server, QUOTE)
    final_evidence = evidence('acceptance-next-origin', QUOTE, 'judgment')
    final_evidence[-1]['sourceReference']['version'] = 1
    requests = _worker(monkeypatch, run, [
        lambda:_tool('goal_read',_read_args(run),'inspect'),
        batch(('goal_clear_gate',{}),('goal_complete_step',{'stepId':'step-3','evidence':final_evidence})),
        _final('The original Goal is complete.')])
    completed = run['tool_executions']['control-1']['result']
    assert completed['ok'], completed.get('error')
    assert run['status']=='completed', run.get('error')
    assert len(requests)==3
    assert [e['name'] for e in run['tool_executions'].values()].count('goal_complete_step')==1
    goal = srv.goal_v2_runtime().read(SESSION_ID).state.goal
    assert goal['goalId']==original['goalId'] and goal['lifecycle']=='completed'
    assert goal['steps'][-1]['acceptanceCriteria']==original['steps'][-1]['acceptanceCriteria']
    canonical = goal['steps'][-1]['evidence'][-1]['sourceReference']
    assert canonical == {**final_evidence[-1]['sourceReference'], 'contentHash':hashlib.sha256(QUOTE.encode()).hexdigest()}
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert restored['tool_executions']['control-1']['result']==completed


@pytest.mark.parametrize('extra,field', [({'version':2},'version'), ({'contentHash':'0'*64},'contentHash')])
def test_tool_failure_points_to_metadata_without_requesting_correct_quote_again(isolated_server, extra, field):
    waiting_run(isolated_server,'judgment',legacy=True)
    run=followup(isolated_server,QUOTE)
    assert _call(run,'goal_clear_gate',{},'clear')['ok']
    before=srv.goal_v2_runtime().read(SESSION_ID).projection()
    items=evidence('acceptance-next-origin',QUOTE,'judgment')
    items[-1]['sourceReference'].update(extra)
    result=_call(run,'goal_complete_step',{'stepId':'step-3','evidence':items},'bad-metadata')
    assert not result['ok'] and field in result['error']
    assert 'quote' not in result['error'] and 'goal_read' not in result['error'] and QUOTE not in result['error']
    assert srv.goal_v2_runtime().read(SESSION_ID).projection()==before
