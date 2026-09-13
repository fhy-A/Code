import json
import pytest
from code_runtime import context_window, output_budget, output_truncation, protocol_replay
from code_runtime.reasoning_capabilities import ReasoningError


@pytest.mark.parametrize('support,disabled,want', [(True, False, 65536), (True, True, 32768),
                                                (False, False, 32768), (None, False, 16384)])
def test_auto_candidates_preserve_unknown(support, disabled, want):
    value = output_budget.resolve({'version': 1, 'mode': 'auto'}, model_id='fixture', route_ref='r',
        capability={}, reasoning_supported=support, reasoning_disabled=disabled)
    assert value['requestedTokens'] == want
    assert output_budget.restore(value, model_id='fixture', route_ref='r', requested_tokens=want) == value


def test_manual_is_not_raised_and_excess_is_rejected():
    cap = {'modelLimit': 32768, 'routeLimit': 8192}
    manual = {'version': 1, 'mode': 'manual', 'tokens': 1234}
    assert output_budget.resolve(manual, model_id='m', route_ref='r', capability=cap)['requestedTokens'] == 1234
    with pytest.raises(ReasoningError, match='output_budget_exceeds_limit'):
        output_budget.resolve(dict(manual, tokens=9000), model_id='m', route_ref='r', capability=cap)
    assert output_budget.resolve({'version': 1, 'mode': 'auto'}, model_id='m', route_ref='r', capability=cap,
                                 reasoning_supported=True)['requestedTokens'] == 8192


@pytest.mark.parametrize('bad', [0, -1, True, 1.5, '123', 2000001])
def test_manual_requires_bounded_integer(bad):
    with pytest.raises(ReasoningError):
        output_budget.intent({'version': 1, 'mode': 'manual', 'tokens': bad})


def test_output_metadata_has_separate_provenance_and_connection_scope(monkeypatch):
    monkeypatch.setattr(context_window, '_catalog', {})
    monkeypatch.setattr(context_window, '_output_catalog', {})
    context_window.normalize_catalog('https://one.invalid/v1', [{'id': 'same-alias', 'context_length': 128000}])
    assert context_window.output_capability('same-alias', 'https://one.invalid/v1')['routeLimit'] is None
    context_window.normalize_catalog('https://two.invalid/v1', [{'id': 'same-alias', 'max_output_tokens': 7000}])
    assert context_window.output_capability('same-alias', 'https://one.invalid/v1')['routeLimit'] is None
    assert context_window.output_capability('same-alias', 'https://two.invalid/v1')['routeLimit'] == 7000


@pytest.mark.parametrize('arguments', ['{"path":', '{"path":"synthetic.txt","content":"synthetic"}'])
def test_length_with_tools_is_truncation_even_when_json_happens_to_be_valid(arguments):
    response = protocol_replay.Response('deepseek')
    response.feed(json.dumps({'choices': [{'delta': {'reasoning_content': 'synthetic'}, 'finish_reason': 'length'}]}))
    response.feed('[DONE]')
    message = {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call', 'type': 'function',
        'function': {'name': 'write_file', 'arguments': arguments}}]}
    with pytest.raises(output_truncation.OutputTruncated, match='output_truncated_tools'):
        response.complete(message)


@pytest.mark.parametrize('field,bad', [('version', 2), ('version', True), ('modelId', 'other'),
    ('routeRef', 'other'), ('requestedTokens', 8192), ('candidateTokens', 32768),
    ('source', []), ('reasoningSupported', 'yes'), ('routeLimit', True), ('extra', 1)])
def test_budget_restore_rejects_mismatched_or_unknown_snapshot(field, bad):
    value = output_budget.resolve({'version': 1, 'mode': 'auto'}, model_id='m', route_ref='r',
                                  capability={}, reasoning_supported=True)
    value[field] = bad
    with pytest.raises(ReasoningError):
        output_budget.restore(value, model_id='m', route_ref='r', requested_tokens=65536)


@pytest.mark.parametrize('field,bad', [('version', 2), ('version', True), ('kind', []),
    ('code', []), ('finishReason', []), ('requestedTokens', 8192),
    ('completionTokens', -1), ('reasoningTokens', True), ('extra', 1)])
def test_diagnostic_restore_rejects_invalid_counts_or_budget(field, bad):
    value = output_truncation.summary({'finishReason': 'length', 'content': 'partial'}, 4096)
    value[field] = bad
    with pytest.raises(ReasoningError, match='output_diagnostic_invalid'):
        output_truncation.restore(value, 4096)
