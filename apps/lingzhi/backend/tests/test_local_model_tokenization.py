from dataclasses import replace
import json

import httpx
import pytest

from ai_base import AIBase, AIRequestBudgetExceeded
from course_generation.service import CourseService
from course_generation_budget import CourseGenerationBudgetExceeded
from local_model_tokenization import MeasuredChatInput, measure_local_chat_input, prompt_digest


@pytest.mark.asyncio
async def test_counts_full_chat_template_on_the_configured_loopback_model(monkeypatch):
    monkeypatch.setenv('AI_LOCAL_PROVIDER', 'http')
    calls = []
    client = httpx.AsyncClient

    def respond(request):
        calls.append((str(request.url), json.loads(request.content)))
        if request.url.path == '/apply-template':
            return httpx.Response(200, json={'prompt': '<system>来源<user>完整正文<assistant>'})
        return httpx.Response(200, json={'tokens': [1, 2, 3, 4, 5]})

    monkeypatch.setattr('local_model_tokenization.httpx.AsyncClient',
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    result = await measure_local_chat_input('http://127.0.0.1:8012/v1', '', '完整正文', '来源')
    assert result == MeasuredChatInput(5, prompt_digest('完整正文', '来源'))
    assert calls[0][1]['messages'][1]['content'] == '完整正文'
    assert calls[1][1]['content'] == '<system>来源<user>完整正文<assistant>'
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [{'tokens': []}, {'tokens': [True]}, {'tokens': [-1]}, {'other': 'invalid'}])
async def test_unavailable_or_malformed_tokenizer_keeps_conservative_gate(monkeypatch, payload):
    monkeypatch.setenv('AI_LOCAL_PROVIDER', 'http')
    client = httpx.AsyncClient
    def respond(request):
        return httpx.Response(200, json={'prompt': '完整文本'} if request.url.path == '/apply-template' else payload)
    monkeypatch.setattr('local_model_tokenization.httpx.AsyncClient',
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    assert await measure_local_chat_input('http://localhost:8012/v1', '', '正文', '来源') is None


@pytest.mark.asyncio
async def test_never_probes_remote_provider_or_another_route(monkeypatch):
    monkeypatch.setenv('AI_LOCAL_PROVIDER', 'http')
    def unexpected(**kwargs):
        raise AssertionError('No request should be made to a remote provider.')
    monkeypatch.setattr('local_model_tokenization.httpx.AsyncClient', unexpected)
    assert await measure_local_chat_input('https://approved.example/v1', 'private', '正文', '来源') is None
    monkeypatch.setenv('AI_LOCAL_PROVIDER', 'other')
    assert await measure_local_chat_input('http://127.0.0.1:8012/v1', '', '正文', '来源') is None


def test_measured_receipt_is_bound_to_full_text_and_still_enforces_both_limits():
    prompt = '设计思维' * 100
    receipt = MeasuredChatInput(40, prompt_digest(prompt, 'system'))
    assert AIBase.validate_request_budget(prompt, 'system', 50, 1000, receipt) == 40
    with pytest.raises(AIRequestBudgetExceeded):
        AIBase.validate_request_budget(prompt, 'system', 30, 1000, receipt)
    with pytest.raises(AIRequestBudgetExceeded):
        AIBase.validate_request_budget(prompt, 'system', 50, 10, receipt)
    with pytest.raises(ValueError):
        AIBase.validate_request_budget(prompt + 'new', 'system', 50, 1000, receipt)


@pytest.mark.asyncio
async def test_handout_uses_real_capacity_without_shortening_source_or_output(monkeypatch):
    service = CourseService()
    service._generation_budget = replace(service._generation_budget, context_window_tokens=32768,
        teacher_handout_max_output_tokens=8192)
    monkeypatch.setattr(service, 'estimate_request_tokens', lambda *args: 30000)
    source = '用户提供的原文与完整边界。' * 500
    measured = []
    async def count(base, key, prompt, system):
        assert source in prompt
        measured.append(prompt)
        return MeasuredChatInput(16000, prompt_digest(prompt, system))
    monkeypatch.setattr('course_generation.service.measure_local_chat_input', count)
    calls = []
    async def model(prompt, system, **kwargs):
        calls.append(kwargs)
        assert source in prompt
        return '<!-- section:s -->\n<!-- block:{"type":"explanation","title":"教材正文"} -->\n完整解释。'
    monkeypatch.setattr(service, '_call_llm', model)
    await service.generate_teacher_handout(course_id='c', outline_sections=[{'node_id': 's'}],
        plan_sections={}, lesson_context={'source': source})
    assert len(calls) == len(measured) == 1
    assert calls[0]['max_tokens'] == 8192
    assert calls[0]['measured_input'].tokens == 16000
    async def full(*args):
        return None
    monkeypatch.setattr('course_generation.service.measure_local_chat_input', full)
    with pytest.raises(CourseGenerationBudgetExceeded):
        await service.generate_teacher_handout(course_id='c', outline_sections=[{'node_id': 's'}],
            plan_sections={}, lesson_context={'source': source})
    assert len(calls) == 1
