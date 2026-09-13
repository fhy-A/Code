import copy
import io
import json
import pytest
import server as srv
from code_runtime import output_budget, reasoning_capabilities as rc, protocol_replay
from code_runtime.model_route_registry import ModelRouteRegistry
from test_goal_v2_agentrun import isolated_server, _persist_session, _origin_message, SESSION_ID


def create(isolated_server, monkeypatch, *, model='deepseek-flash', intent='default', preference=None,
           budget=None, metadata=None, raw=None, request_id='output-fixture'):
    registry = ModelRouteRegistry(isolated_server / 'routes.json')
    catalog = registry.refresh([{'connectionId': 'fixture', 'source': 'manual', 'key': 'synthetic',
        'baseUrl': 'https://fixture.invalid'}], lambda _: [model])
    monkeypatch.setattr(srv, '_model_route_registry', registry)
    monkeypatch.setattr(srv.context_window, '_catalog', {})
    monkeypatch.setattr(srv.context_window, '_output_catalog', {})
    if metadata:
        srv.context_window.normalize_catalog('https://fixture.invalid', [{'id': model, **metadata}], output_scope='fixture')
    route = catalog['routes'][0]
    selection = {'schemaVersion': 2, 'intent': intent, 'modelId': model, 'routeRef': route['routeRef'],
                 'capabilityRevision': route['reasoning']['capabilityRevision']}
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    return srv._create_agent_run(SESSION_ID, {'model': model, 'max_tokens': 0,
        'messages': [{'role': 'user', 'content': 'Perform the approved isolated work.'}], **(raw or {})},
        'https://fixture.invalid', ['synthetic'], ['write_file', 'list_files'], permission_profile='bypass',
        client_request_id=request_id, run_kind='foreground', start_worker=False,
        cwd=str(isolated_server), route_ref=route['routeRef'], catalog_revision=catalog['catalogRevision'],
        reasoning_selection=selection if not raw else None, context_budget_tokens=budget,
        output_preference=preference or {'version': 1, 'mode': 'auto'})


@pytest.mark.parametrize('model,intent,want,parameter', [
    ('deepseek-flash', 'default', 65536, 'max_tokens'), ('deepseek-flash', 'high', 65536, 'max_tokens'),
    ('deepseek-v4-flash-vision-exp', 'default', 65536, 'max_tokens'),
    ('gpt-5.4', 'high', 65536, 'max_completion_tokens'),
    ('unknown-alias', 'default', 16384, 'max_tokens')])
def test_real_admission_resolves_once(isolated_server, monkeypatch, model, intent, want, parameter):
    run = create(isolated_server, monkeypatch, model=model, intent=intent)
    assert run['request'][parameter] == want
    assert run['output_budget']['requestedTokens'] == want
    record = srv._agent_run_record(run)
    monkeypatch.setattr(output_budget, 'resolve', lambda *a, **k: pytest.fail('must not re-resolve on restore'))
    restored = srv._agent_run_from_record(record)
    assert restored['request'] == run['request']
    assert restored['output_budget'] == run['output_budget']


@pytest.mark.parametrize('support,want', [(False, 32768), (True, 65536)])
def test_explicit_server_metadata_support(isolated_server, monkeypatch, support, want):
    run = create(isolated_server, monkeypatch, model='declared-model', metadata={'supports_reasoning': support})
    assert run['request']['max_tokens'] == want


def test_route_non_reasoning_declaration_is_respected(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, metadata={'supports_reasoning': False})
    assert run['request']['max_tokens'] == 32768
    with pytest.raises(rc.ReasoningError, match='output_reasoning_incompatible'):
        create(isolated_server, monkeypatch, metadata={'supports_reasoning': False}, intent='high', request_id='different-input')


def test_context_and_fixed_thinking_reject_without_shrinking(isolated_server, monkeypatch):
    with pytest.raises(rc.ReasoningError, match='output_context_insufficient'):
        create(isolated_server, monkeypatch, budget=32768)
    with pytest.raises(rc.ReasoningError, match='reasoning_budget_insufficient'):
        create(isolated_server, monkeypatch, model='claude-sonnet-4-5', intent='high',
            preference={'version': 1, 'mode': 'manual', 'tokens': 4096})


def test_manual_limits_and_explicit_disabled_reasoning(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, preference={'version': 1, 'mode': 'manual', 'tokens': 1234})
    assert run['request']['max_tokens'] == 1234
    old = srv._agent_run_record(run); old.pop('outputBudget')
    assert srv._agent_run_from_record(old)['request']['max_tokens'] == 1234


def test_explicit_disabled_known_reasoning_uses_non_reasoning_candidate(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, raw={'thinking': {'type': 'disabled'}})
    assert run['request']['max_tokens'] == 32768


def test_same_model_route_limit_caps_auto_and_rejects_manual(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, metadata={'max_output_tokens': 8192})
    assert run['request']['max_tokens'] == 8192
    assert run['output_budget']['routeLimitSource'] == 'metadata'
    with pytest.raises(rc.ReasoningError, match='output_budget_exceeds_limit'):
        create(isolated_server, monkeypatch, metadata={'max_output_tokens': 8192}, request_id='second-request',
               preference={'version': 1, 'mode': 'manual', 'tokens': 16384})


def frames(*, calls=None, text='', reasoning='synthetic', finish='length', done=True, tokens=16384, reasoning_tokens=13357):
    delta = {'reasoning_content': reasoning, 'content': text}
    if calls:
        delta['tool_calls'] = calls
    items = [json.dumps({'choices': [{'delta': delta, 'finish_reason': None}]}),
             json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}],
                         'usage': {'completion_tokens': tokens, 'prompt_tokens': 10,
                                   'completion_tokens_details': {'reasoning_tokens': reasoning_tokens}}})]
    if done:
        items.append('[DONE]')
    return ''.join('data: ' + x + '\n\n' for x in items).encode()


class Stream(io.BytesIO):
    status = 200


@pytest.mark.parametrize('kind', ['reasoning', 'text', 'tools_partial', 'tools_valid'])
def test_real_sse_worker_stops_without_retry_or_partial_tool_execution(isolated_server, monkeypatch, kind):
    tokens = 4096 if kind == 'reasoning' else 16384
    run = create(isolated_server, monkeypatch, preference={'version': 1, 'mode': 'manual', 'tokens': tokens})
    calls = None
    if kind.startswith('tools'):
        calls = [{'index': 0, 'id': 'partial', 'type': 'function', 'function': {'name': 'write_file',
            'arguments': '{"path":' if kind == 'tools_partial' else json.dumps({
                'path': str(isolated_server / 'must-not-exist'), 'content': 'forbidden'})}}]
    blob = frames(calls=calls, text='partial answer' if kind == 'text' else '', tokens=tokens,
                  reasoning_tokens=tokens if kind == 'reasoning' else 13357)
    requests = []
    monkeypatch.setattr(srv.request, 'urlopen', lambda request, **kw: (requests.append(request) or Stream(blob)))
    srv._agent_run_worker(run)
    assert run['status'] == 'failed'
    assert run['error_code'] == 'output_truncated_' + ('tools' if calls else kind)
    assert len(requests) == 1
    assert run['tool_executions'] == {}
    assert not (isolated_server / 'must-not-exist').exists()
    assert not run['protocol_replay']['entries']
    assert run['model_checkpoint'] is None
    assert run['output_diagnostic']['completionTokens'] == tokens
    assert run['output_diagnostic']['reasoningTokens'] == (4096 if kind == 'reasoning' else 13357)
    assert run['output_diagnostic']['requestedTokens'] == tokens
    assert run['non_action_count'] == 0
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert restored['output_diagnostic'] == run['output_diagnostic']
    assert restored['request'] == run['request']


def test_prior_success_is_retained_and_not_replayed_on_truncation(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch)
    target = isolated_server / 'approved.txt'
    call = {'index': 0, 'id': 'approved', 'type': 'function', 'function': {'name': 'write_file',
        'arguments': json.dumps({'path': str(target), 'content': 'approved once'})}}
    pending = iter([frames(calls=[call], finish='tool_calls'), frames()])
    requests = []
    monkeypatch.setattr(srv.request, 'urlopen', lambda request, **kw: (requests.append(request) or Stream(next(pending))))
    srv._agent_run_worker(run)
    assert target.read_text() == 'approved once'
    assert len(requests) == 2 and len(run['tool_executions']) == 1
    assert run['tool_executions']['approved']['result']['ok']
    assert len(run['protocol_replay']['entries']) == 1
    assert run['error_code'] == 'output_truncated_reasoning'
    restored = srv._agent_run_from_record(srv._agent_run_record(run))
    assert restored['tool_executions'] == run['tool_executions']


def test_cancel_has_priority_over_length(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch)
    class CancelStream(Stream):
        def readline(self, *args):
            run['cancel_event'].set()
            return super().readline(*args)
    monkeypatch.setattr(srv.request, 'urlopen', lambda *a, **k: CancelStream(frames()))
    srv._agent_run_worker(run)
    assert run['status'] == 'cancelled'
    assert not run['output_diagnostic'] and not run['tool_executions']


def test_truncation_preserves_goal_and_last_valid_native_boundary(isolated_server, monkeypatch):
    from test_goal_v2_agentrun import _active_goal_run, _call
    initial = _active_goal_run()
    assert _call(initial, 'goal_complete_step', {'stepId': 'step-1', 'evidence': [{
        'criterionId': 'criterion-1', 'kind': 'machine', 'summary': 'synthetic completed check'}]}, 'done-step')['ok']
    assert _call(initial, 'goal_start_step', {'stepId': 'step-2'}, 'next-step')['ok']
    before = srv.goal_v2_runtime().read(SESSION_ID).projection()
    run = create(isolated_server, monkeypatch)
    monkeypatch.setattr(srv.request, 'urlopen', lambda *a, **kw: Stream(frames()))
    srv._agent_run_worker(run)
    assert run['error_code'] == 'output_truncated_reasoning'
    assert srv.goal_v2_runtime().read(SESSION_ID).projection() == before
    assert not run['protocol_replay']['entries']


@pytest.mark.parametrize('missing', ['done', 'finish', 'reasoning'])
def test_non_length_protocol_failures_keep_strict_error(isolated_server, monkeypatch, missing):
    run = create(isolated_server, monkeypatch)
    blob = frames(done=missing != 'done', finish=None if missing == 'finish' else 'tool_calls')
    if missing == 'reasoning':
        blob = blob.replace(b'"reasoning_content": "synthetic", ', b'')
    monkeypatch.setattr(srv.request, 'urlopen', lambda *a, **kw: Stream(blob))
    srv._agent_run_worker(run)
    assert run['status'] == ('waiting_recovery' if missing == 'done' else 'failed')
    assert run['error_code'] not in srv.output_truncation.CODES
    assert not run['tool_executions']


def test_compaction_truncation_has_actual_budget_and_no_business_request(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, model='unknown-alias')
    run['messages'] = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'synthetic history ' * 100}
                       for i in range(30)]
    before = copy.deepcopy(run['messages'])
    monkeypatch.setattr(srv, '_agent_should_auto_compact', lambda *a, **kw: True)
    requests = []
    monkeypatch.setattr(srv.request, 'urlopen', lambda request, **kw: (requests.append(request) or Stream(frames(tokens=1600))))
    srv._agent_run_worker(run)
    assert run['status'] == 'failed' and run['error_code'] == 'output_truncated_reasoning'
    assert len(requests) == 1 and not run['tool_executions']
    assert run['messages'] == before
    assert run['output_diagnostic']['kind'] == 'compaction'
    assert run['output_diagnostic']['requestedTokens'] == 1600
    assert run['output_budget']['requestedTokens'] == 16384
    assert srv._agent_run_from_record(srv._agent_run_record(run))['output_diagnostic'] == run['output_diagnostic']


def test_new_compaction_respects_manual_cap_and_fixed_reasoning(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, model='claude-sonnet-4-5', intent='high')
    payload = srv._agent_compaction_payload(run, {'compactedMessages': []})
    assert payload['max_tokens'] == 5120
    assert payload['thinking']['budget_tokens'] == 4096
    # Legacy in-flight runs keep their existing compaction contract too.
    legacy = {**run, 'output_budget': None}
    assert srv._agent_compaction_payload(legacy, {'compactedMessages': []})['max_tokens'] == 1600


def test_manual_small_compaction_is_never_raised(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch, preference={'version': 1, 'mode': 'manual', 'tokens': 1234})
    assert srv._agent_compaction_payload(run, {'compactedMessages': []})['max_tokens'] == 1234


@pytest.mark.parametrize('signature', [True, False])
def test_claude_max_tokens_does_not_relax_signature_validation(isolated_server, monkeypatch, signature):
    from tests.test_reasoning_protocol import claude_frames
    run = create(isolated_server, monkeypatch, model='claude-sonnet-4-5', intent='high')
    events = claude_frames(content='', tool=True)
    for event in events:
        if event.get('type') == 'message_delta':
            event['delta']['stop_reason'] = 'max_tokens'
        if event.get('delta', {}).get('partial_json') == '"."}':
            event['delta']['partial_json'] = ''  # a real incomplete tool argument block
    if not signature:
        events = [e for e in events if e.get('delta', {}).get('type') != 'signature_delta']
    blob = ''.join('data: ' + json.dumps(e) + '\n\n' for e in events).encode()
    monkeypatch.setattr(srv.request, 'urlopen', lambda *a, **kw: Stream(blob))
    srv._agent_run_worker(run)
    assert run['status'] == 'failed'
    assert run['error_code'] == ('output_truncated_tools' if signature else 'reasoning_replay_invalid')
    assert not run['tool_executions'] and not run['protocol_replay']['entries']


def test_length_rejects_entire_two_tool_batch(isolated_server, monkeypatch):
    run = create(isolated_server, monkeypatch)
    calls = [{'index': i, 'id': f'call-{i}', 'type': 'function', 'function': {'name': 'write_file',
        'arguments': json.dumps({'path': str(isolated_server / f'forbidden-{i}'), 'content': 'synthetic'})
                     if i == 0 else '{"path":'}} for i in range(2)]
    monkeypatch.setattr(srv.request, 'urlopen', lambda *a, **kw: Stream(frames(calls=calls)))
    srv._agent_run_worker(run)
    assert run['error_code'] == 'output_truncated_tools'
    assert run['tool_executions'] == {} and not (isolated_server / 'forbidden-0').exists()


def test_real_route_model_fetch_keeps_same_url_connections_separate(isolated_server, monkeypatch):
    registry = ModelRouteRegistry(isolated_server / 'exact-route-caps.json')
    monkeypatch.setattr(srv, '_model_route_registry', registry)
    monkeypatch.setattr(srv.context_window, '_catalog', {})
    monkeypatch.setattr(srv.context_window, '_output_catalog', {})
    def response(request, **kwargs):
        cap = 7000 if request.get_header('Authorization') == 'Bearer synthetic-a' else 12000
        return Stream(json.dumps({'data': [{'id': 'deepseek-flash', 'max_output_tokens': cap}]}).encode())
    monkeypatch.setattr(srv.request, 'urlopen', response)
    catalog = registry.refresh([
        {'connectionId': ' fixture-a ', 'source': 'manual', 'key': 'synthetic-a', 'baseUrl': 'https://same.invalid'},
        {'connectionId': 'fixture-b', 'source': 'manual', 'key': 'synthetic-b', 'baseUrl': 'https://same.invalid'},
    ], srv._fetch_models_for_route_connection)
    actual = {}
    for route in catalog['routes']:
        payload, budget = srv._agent_resolve_output({'model': 'deepseek-flash', 'max_tokens': 0},
            {'version': 1, 'mode': 'auto'}, 'https://same.invalid', route['routeRef'], catalog['catalogRevision'], None)
        actual[route['connectionId']] = payload['max_tokens']
        assert budget['routeLimitSource'] == 'metadata'
    assert actual == {'fixture-a': 7000, 'fixture-b': 12000}
    assert srv.context_window.output_capability('deepseek-flash', 'https://same.invalid')['routeLimit'] is None
