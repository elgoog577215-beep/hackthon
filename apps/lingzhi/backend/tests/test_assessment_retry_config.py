"""Assessment stages share one bounded provider policy."""
import pytest
from assessment_generation_policy import resolve_assessment_generation_policy
from assessment_orchestrator import UniversalAssessmentModel


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['generate', 'repair', 'solve', 'review'])
async def test_stage_policy_prevents_nested_provider_retries(monkeypatch, stage):
    monkeypatch.setenv('AI_ASSESSMENT_RETRY_COUNT', '99')
    model = UniversalAssessmentModel()
    calls = []
    async def invoke(prompt, **kwargs):
        calls.append(kwargs)
        return 'response'
    monkeypatch.setattr(model, '_call_llm', invoke)
    policy = resolve_assessment_generation_policy('complete').call_policy(stage)
    assert await model._assessment_llm_call(policy, 'prompt', retry_count=1) == 'response'
    assert len(calls) == 1
    assert calls[0]['max_attempts'] == calls[0]['retry_count'] == 1
