"""Terminal output diagnostics contain counts only, never reasoning/tool bodies."""
from .reasoning_capabilities import ReasoningError

FINISH_REASONS = {'length', 'max_tokens'}
CODES = {'output_truncated_reasoning', 'output_truncated_text', 'output_truncated_tools'}


def _counts(result):
    usage = result.get('usage') if isinstance(result.get('usage'), dict) else {}
    details = usage.get('completion_tokens_details')
    return usage, details if isinstance(details, dict) else {}


def classify(result):
    if not isinstance(result.get('finishReason'), str) or result['finishReason'] not in FINISH_REASONS:
        return ''
    if result.get('toolCalls') or result.get('tool_calls'):
        return 'output_truncated_tools'
    usage, details = _counts(result)
    reasoning = details.get('reasoning_tokens')
    reasoning = reasoning if type(reasoning) is int and reasoning > 0 else 0
    if not str(result.get('content') or '').strip() and (result.get('reasoning') or reasoning):
        return 'output_truncated_reasoning'
    return 'output_truncated_text'


def summary(result, budget, kind='model'):
    usage, details = _counts(result)
    def count(value):
        return value if type(value) is int and value >= 0 else None
    return {'version': 1, 'kind': kind, 'code': classify(result), 'finishReason': result.get('finishReason'),
            'requestedTokens': budget, 'promptTokens': count(usage.get('prompt_tokens')),
            'completionTokens': count(usage.get('completion_tokens')),
            'reasoningTokens': count(details.get('reasoning_tokens'))}


class OutputTruncated(ReasoningError):
    pass


def restore(value, budget):
    if value is None:
        return None
    fields = {'version', 'kind', 'code', 'finishReason', 'requestedTokens', 'promptTokens', 'completionTokens', 'reasoningTokens'}
    if (not isinstance(value, dict) or set(value) != fields or type(value['version']) is not int
            or value['version'] != 1 or not isinstance(value['code'], str) or value['code'] not in CODES
            or not isinstance(value['finishReason'], str) or value['finishReason'] not in FINISH_REASONS
            or value['kind'] not in ('model', 'compaction') or type(value['requestedTokens']) is not int
            or (value['kind'] == 'model' and value['requestedTokens'] != budget)
            or (value['kind'] == 'compaction' and not 1 <= value['requestedTokens'] <= max(1600, budget))
            or any(value[k] is not None and (type(value[k]) is not int or value[k] < 0)
                   for k in ('promptTokens', 'completionTokens', 'reasoningTokens'))):
        raise ReasoningError('output_diagnostic_invalid')
    return dict(value)
