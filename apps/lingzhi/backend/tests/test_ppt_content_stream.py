import asyncio
import json
from types import SimpleNamespace

import pytest

from ppt_teaching_planner import invoke_teaching_provider, project_ppt_stream_text
from slide_ai_planning_v6 import build_ai_base_story_planner_v6


def test_partial_provider_json_projects_only_teacher_facing_text():
    assert project_ppt_stream_text('{"title":"导数的定') == '导数的定'
    assert project_ppt_stream_text('') == ''
    assert project_ppt_stream_text('not JSON') == ''
    preview = project_ppt_stream_text(json.dumps({
        'title': '导数定义',
        'page_id': 'internal-page-id',
        'points': [{'heading': '平均变化率', 'text': '从割线逼近切线',
                    'sources': [{'text': 'private-source-text'}]}],
        'notes': '先观察斜率，再讨论极限。',
        'reasoning_content': {'text': 'private-reasoning'},
        'response_contract': {'title': 'private-schema'},
    }, ensure_ascii=False))
    assert preview == '导数定义\n\n平均变化率\n\n从割线逼近切线\n\n先观察斜率，再讨论极限。'


class StreamingProvider:
    calls = []

    def __init__(self, *, provider_profile='ppt'):
        assert provider_profile == 'ppt'

    async def _call_llm(self, prompt, **kwargs):
        request = json.loads(prompt)
        self.calls.append((request, kwargs))
        page_id = request.get('page', {}).get('page_id', 'narrative')
        reset, delta = kwargs.get('on_content_reset'), kwargs.get('on_content_delta')
        if reset:
            await reset()
            await delta('{"title":"old draft')
            await asyncio.sleep(0)
            # The existing provider signals its own retry; no adapter-side request.
            await reset()
        response = json.dumps({'title': page_id, 'notes': '完成正文'}, ensure_ascii=False)
        if delta:
            await delta(response[:10])
            await asyncio.sleep(0)
            await delta(response[10:])
        kwargs['telemetry_sink']({'model_id': 'qwen3.8-27b', 'status': 'completed', 'physical_request_count': 1})
        return response

    _extract_json = staticmethod(json.loads)


@pytest.mark.asyncio
async def test_existing_planner_streams_concurrent_pages_and_retry_resets_without_extra_calls(monkeypatch):
    import slide_ai_planning_v6
    StreamingProvider.calls = []
    monkeypatch.setattr(slide_ai_planning_v6, 'AIBase', StreamingProvider)
    events = []
    async def record(event):
        events.append(event)
    planner = build_ai_base_story_planner_v6(on_content_stream=record)
    results = await asyncio.gather(*(planner({
        'teaching_request': 'fixed_fields', 'page': {'page_id': f'page-{i}'},
    }) for i in range(1, 5)))
    assert len(StreamingProvider.calls) == 4
    assert [result['title'] for result in results] == [f'page-{i}' for i in range(1, 5)]
    assert {event['batch_id'] for event in events} == {f'page-{i}' for i in range(1, 5)}
    for i in range(1, 5):
        page_events = [event for event in events if event['batch_id'] == f'page-{i}']
        assert [event['event'] for event in page_events] == ['reset', 'delta', 'reset', 'delta', 'delta', 'complete']
        assert json.loads(''.join(event['delta'] for event in page_events[3:]))['title'] == f'page-{i}'
    for _, options in StreamingProvider.calls:
        assert options['enable_thinking'] is False
        assert options['retry_count'] == 1 and options['max_attempts'] == 2


@pytest.mark.asyncio
async def test_non_streaming_call_keeps_existing_provider_options():
    provider = StreamingProvider()
    StreamingProvider.calls = []
    result = await invoke_teaching_provider(provider, {'teaching_request': 'narrative'})
    assert result['title'] == 'narrative'
    assert len(provider.calls) == 1
    assert 'on_content_delta' not in provider.calls[0][1]
    assert 'on_content_reset' not in provider.calls[0][1]


@pytest.mark.asyncio
async def test_real_provider_adapter_forwards_tokens_with_one_physical_request(monkeypatch):
    from ai_base import AIBase
    monkeypatch.setenv('AI_API_KEY', 'test-key')
    monkeypatch.setenv('AI_PPT_STORY_MODELS', 'qwen3.8-27b')
    calls, deltas, resets = [], [], []
    class Completions:
        async def create(self, **options):
            calls.append(options)
            async def stream():
                for content, reasoning in [(None, 'private-reasoning'), ('{"title":"导数', None), ('定义"}', None)]:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                        content=content, reasoning_content=reasoning,
                    ), finish_reason=None)])
            return stream()
    provider = AIBase(provider_profile='ppt')
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    provider.smart_models = provider.fast_models = ['qwen3.8-27b']
    provider._working_model_cache.clear()
    provider._model_failure_cache.clear()
    async def delta(text):
        deltas.append(text)
    async def reset():
        resets.append(True)
    result = await invoke_teaching_provider(provider, {'teaching_request': 'fixed_fields'},
        on_content_delta=delta, on_content_reset=reset)
    assert result['title'] == '导数定义'
    assert len(calls) == 1 and calls[0]['stream'] is True
    assert calls[0]['model'] == 'qwen3.8-27b'
    assert resets == [True]
    assert deltas == ['{"title":"导数', '定义"}']
    assert sum(attempt['physical_request_count'] for attempt in result.telemetry) == 1
