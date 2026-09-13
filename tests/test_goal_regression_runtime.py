import json
import subprocess
from pathlib import Path
import pytest
import server as srv
from code_runtime import tool_markup
from test_goal_v2_agentrun import isolated_server, _active_goal_run, _origin_message, _persist_session, _create_run, _call, _plan, SESSION_ID
from test_goal_closeout import _worker, _final

DSML = '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="goal_read"><｜｜DSML｜｜ parameter name="decision" string="true">wait</｜｜DSML｜｜ parameter></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>'


@pytest.mark.parametrize('prefix', ['', 'The isolated comparison is complete; checking the Goal now.\n\n'])
def test_plain_tool_markup_is_failed_without_execution_or_valid_history(isolated_server, monkeypatch, prefix):
    run = _active_goal_run()
    before = list(run['messages'])
    goal = srv.goal_v2_runtime().read(run['session_id']).projection()
    requests = _worker(monkeypatch, run, [_final(prefix + DSML)] * 4)
    assert run['status'] == 'failed' and run['error_code'] == 'tool_protocol_error'
    assert len(requests) == 1
    assert run['messages'] == before
    assert srv.goal_v2_runtime().read(run['session_id']).projection() == goal
    assert not any('DSML' in str(r.get('content', '')) for r in run['rounds'])
    assert run['rounds'][-1]['content'] == prefix.strip()
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert restored['result'] == run['result'] and restored['messages'] == before


def test_python_and_javascript_markup_contexts_agree():
    cases = [DSML, 'Progress.\n\n' + DSML, 'Progress.\r\n\r\n  ' + DSML + '\r\nNext explanation.',
             '```xml\n'+DSML+'\n```', '~~~\n'+DSML+'\n~~~', '> '+DSML,
             '    '+DSML, '\t'+DSML, '\u00a0'+DSML, 'Inline '+DSML+' example.',
             'A normal explanation mentioning DSML and goal_read.',
             '```\n'+DSML+'\n```\n\n'+DSML, DSML+'\n\n'+DSML]
    script = "global.window={Code:{agent:{}}};require('./src/agent/model-request.js');const api=window.Code.agent.modelRequest;const values=" + json.dumps(cases) + ";console.log(JSON.stringify(values.map(v=>[api.isUnexecutedToolMarkup(v),api.replaceUnexecutedToolMarkup(v).trim()])));"
    r = subprocess.run(['node','-'], input=script, cwd=Path(__file__).resolve().parents[1], text=True, encoding='utf-8', capture_output=True, check=True)
    assert json.loads(r.stdout) == [[tool_markup.is_unexecuted(x),tool_markup.public_text(x)] for x in cases]
    assert [tool_markup.is_unexecuted(x) for x in cases] == [True,True,True,False,False,False,False,False,False,False,False,True,True]


def test_new_plan_cannot_invent_an_unsourced_user_confirmation(isolated_server):
    origin = _origin_message('source-fixture', 'source-origin')
    origin['content'] = 'Implement and test. I will later provide the final input; run it and compare with my expected result.'
    _persist_session(SESSION_ID, [origin])
    run = _create_run('source-fixture', permission_profile='bypass')
    assert _call(run, 'goal_create', {'objective': 'Implement, test, then compare the supplied input.'}, 'create')['ok']
    plan = _plan()
    plan[-1]['acceptanceCriteria'][0].update(kind='user', description='The user must confirm the computed result matches.')
    response = _call(run, 'goal_set_plan', {'steps': plan}, 'unsourced-plan')
    assert response['ok'] is False
    assert srv.goal_v2_runtime().read(SESSION_ID).state.goal['lifecycle'] == 'draft'


@pytest.mark.parametrize('mode', ['normal', 'missing_done', 'missing_finish', 'cancel', 'length', 'compaction'])
def test_real_sse_dsml_does_not_bypass_existing_protocol_boundaries(isolated_server, monkeypatch, mode):
    from test_output_budget_runtime import create, frames, Stream
    run = create(isolated_server, monkeypatch, model='unknown-alias' if mode == 'compaction' else 'deepseek-flash')
    if mode == 'compaction':
        run['messages'] = [{'role':'user' if i % 2 == 0 else 'assistant','content':'synthetic history '*100} for i in range(30)]
        monkeypatch.setattr(srv, '_agent_should_auto_compact', lambda *a, **k: True)
    before = json.loads(json.dumps(run['messages']))
    blob = frames(text='Progress.\n\n'+DSML, finish=None if mode == 'missing_finish' else ('length' if mode == 'length' else 'stop'), done=mode!='missing_done')
    requests = []
    class CancelStream(Stream):
        def readline(self, *args):
            run['cancel_event'].set()
            return super().readline(*args)
    monkeypatch.setattr(srv.request, 'urlopen', lambda request, **kw: (requests.append(request) or (CancelStream if mode == 'cancel' else Stream)(blob)))
    srv._agent_run_worker(run)
    assert len(requests) == 1 and not run['tool_executions'] and not (run.get('protocol_replay') or {}).get('entries')
    assert run['messages'] == before
    if mode in ('normal', 'compaction'):
        assert run['status'] == 'failed' and run['error_code'] == 'tool_protocol_error'
    elif mode == 'cancel': assert run['status'] == 'cancelled'
    elif mode == 'length': assert run['error_code'] == 'output_truncated_text'
    else: assert run['error_code'] != 'tool_protocol_error'
    assert not any('DSML' in str(r.get('content','')) for r in run['rounds'])
