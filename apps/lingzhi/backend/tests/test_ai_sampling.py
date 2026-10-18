import pytest

from backend.tests.test_ai_base_failover import SuccessfulCompletions, _make_service


@pytest.mark.asyncio
async def test_explicit_sampling_is_forwarded_without_changing_other_calls(monkeypatch):
    completions = SuccessfulCompletions(); provider = _make_service(monkeypatch, completions, models=('model-a',))
    assert await provider._call_llm('extract', temperature=0, max_attempts=1) == 'ok-answer'
    assert completions.requests[0]['temperature'] == 0
    assert await provider._call_llm('normal', max_attempts=1) == 'ok-answer'
    assert 'temperature' not in completions.requests[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 3, True, '0'])
async def test_invalid_sampling_is_rejected_before_network(monkeypatch, value):
    completions = SuccessfulCompletions(); provider = _make_service(monkeypatch, completions, models=('model-a',))
    with pytest.raises(ValueError): await provider._call_llm('extract', temperature=value)
    assert not completions.requests
