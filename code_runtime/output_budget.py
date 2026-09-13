"""Admission-only output intent resolution; never reinterpret a restored Run."""
from __future__ import annotations

import copy
from .reasoning_capabilities import ReasoningError

MAX_TOKENS = 2_000_000


def intent(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ReasoningError('output_preference_invalid')
    mode = value.get('mode')
    fields = {'version', 'mode'} | ({'tokens'} if mode == 'manual' else set())
    if not isinstance(mode, str) or mode not in {'auto', 'manual'} or set(value) != fields:
        raise ReasoningError('output_preference_invalid')
    if mode == 'manual' and (type(value['tokens']) is not int or not 1 <= value['tokens'] <= MAX_TOKENS):
        raise ReasoningError('output_preference_invalid')
    return copy.deepcopy(value)


def resolve(value, *, model_id, route_ref, capability, reasoning_supported=None, reasoning_disabled=False):
    preference = intent(value)
    if reasoning_supported is not None and type(reasoning_supported) is not bool:
        raise ReasoningError('output_capability_invalid')
    # These are coding-request candidates, not model hard maxima or measured optima.
    if reasoning_supported is None:
        candidate, source = 16384, 'unknown_conservative'
    elif reasoning_supported and not reasoning_disabled:
        candidate, source = 65536, 'reasoning_candidate'
    else:
        candidate, source = 32768, 'non_reasoning_candidate'
    limits = [capability.get(k) for k in ('modelLimit', 'routeLimit') if capability.get(k) is not None]
    if any(type(n) is not int or not 1 <= n <= MAX_TOKENS for n in limits):
        raise ReasoningError('output_capability_invalid')
    maximum = min(limits) if limits else None
    if preference['mode'] == 'manual':
        requested, source = preference['tokens'], 'user_override'
        if maximum is not None and requested > maximum:
            raise ReasoningError('output_budget_exceeds_limit')
    else:
        requested = min(candidate, maximum) if maximum is not None else candidate
    return {'version': 1, 'modelId': model_id, 'routeRef': route_ref, 'intent': preference,
            'candidateTokens': candidate, 'requestedTokens': requested, 'source': source,
            'modelLimit': capability.get('modelLimit'), 'routeLimit': capability.get('routeLimit'),
            'modelLimitSource': capability.get('modelLimitSource', 'unknown'),
            'routeLimitSource': capability.get('routeLimitSource', 'unknown'),
            'reasoningSupported': reasoning_supported, 'reasoningDisabled': bool(reasoning_disabled)}


def restore(value, *, model_id, route_ref, requested_tokens):
    if value is None:
        return None
    fields = {'version', 'modelId', 'routeRef', 'intent', 'candidateTokens', 'requestedTokens', 'source',
              'modelLimit', 'routeLimit', 'modelLimitSource', 'routeLimitSource',
              'reasoningSupported', 'reasoningDisabled'}
    if (not isinstance(value, dict) or set(value) != fields or type(value.get('version')) is not int
            or value['version'] != 1 or value['modelId'] != model_id or value['routeRef'] != route_ref
            or type(value['requestedTokens']) is not int or value['requestedTokens'] != requested_tokens
            or not 1 <= value['requestedTokens'] <= MAX_TOKENS
            or type(value['candidateTokens']) is not int or value['candidateTokens'] not in {16384, 32768, 65536}
            or not isinstance(value['source'], str) or value['source'] not in {'unknown_conservative', 'reasoning_candidate', 'non_reasoning_candidate', 'user_override'}
            or (value['reasoningSupported'] is not None and type(value['reasoningSupported']) is not bool)
            or type(value['reasoningDisabled']) is not bool):
        raise ReasoningError('output_budget_snapshot_invalid')
    preference = intent(value['intent'])
    for key in ('modelLimit', 'routeLimit'):
        limit = value[key]
        if limit is not None and (type(limit) is not int or not value['requestedTokens'] <= limit <= MAX_TOKENS):
            raise ReasoningError('output_budget_snapshot_invalid')
    if value['modelLimitSource'] not in ('official', 'unknown') or value['routeLimitSource'] not in ('metadata', 'unknown'):
        raise ReasoningError('output_budget_snapshot_invalid')
    if preference['mode'] == 'manual' and (preference['tokens'] != requested_tokens or value['source'] != 'user_override'):
        raise ReasoningError('output_budget_snapshot_invalid')
    if preference['mode'] == 'auto':
        expected_candidate = (16384 if value['reasoningSupported'] is None else
                              65536 if value['reasoningSupported'] and not value['reasoningDisabled'] else 32768)
        expected_source = {16384: 'unknown_conservative', 65536: 'reasoning_candidate', 32768: 'non_reasoning_candidate'}[expected_candidate]
        expected_tokens = min([expected_candidate] + [value[k] for k in ('modelLimit', 'routeLimit') if value[k] is not None])
        if (value['candidateTokens'] != expected_candidate or value['requestedTokens'] != expected_tokens
                or value['source'] != expected_source):
            raise ReasoningError('output_budget_snapshot_invalid')
    return copy.deepcopy(value)
