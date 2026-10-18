import asyncio,json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course,start
from course_repository import CourseDocumentConflict


def test_literal_controls_and_invalid_escapes_can_be_normalized_without_changing_text():
    from knowledge_compact import parse_complete_json
    raw='{"value":"a'+chr(9)+'b","formula":"'+chr(92)+'Phi(s)"}'
    value=parse_complete_json(raw)
    assert value['value']=='a'+chr(9)+'b' and value['formula']==chr(92)+'Phi(s)'
    assert 'literal_controls_escaped' in value['_format_normalizations']


def test_incomplete_or_duplicate_key_json_is_never_repaired():
    from knowledge_compact import parse_complete_json
    with pytest.raises(json.JSONDecodeError):parse_complete_json('{"items":[')
    with pytest.raises(CourseDocumentConflict):parse_complete_json('{"items":[],"items":[1]}')


@pytest.mark.asyncio
async def test_silent_model_is_stopped_without_another_request_and_partial_output_is_retained(svc,monkeypatch):
    import knowledge_atomic
    setup_course(svc,monkeypatch);before=deepcopy(svc.repository.load_raw('c-pilot'));clock={'now':0.};calls=[]
    monkeypatch.setattr(knowledge_atomic.time,'perf_counter',lambda:clock['now'])
    async def stalled(prompt,**kwargs):
        calls.append(kwargs);kwargs['on_content_delta']('{"partial":');clock['now']=100.
        await asyncio.Event().wait()
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=stalled,model_smart='test-qwen',client=None)
    job=start(svc);await asyncio.wait_for(svc.run('c-pilot',job['id']),timeout=4)
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='failed' and saved['partial_text']=='{"partial":'
    assert len(calls)==1 and calls[0]['max_attempts']==1
    assert svc.repository.load_raw('c-pilot')==before


@pytest.mark.asyncio
@pytest.mark.parametrize('prefix', ['', '{"partial":'])
async def test_whitespace_stream_does_not_reset_meaningful_content_timeout(svc, monkeypatch, prefix):
    import knowledge_atomic
    setup_course(svc, monkeypatch)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    clock = {'now': 0.}
    calls = []
    whitespace = '\n \t' * 500
    monkeypatch.setattr(knowledge_atomic.time, 'perf_counter', lambda: clock['now'])

    async def stalled(prompt, **kwargs):
        calls.append(kwargs)
        if prefix:
            kwargs['on_content_delta'](prefix)
        clock['now'] = 100.
        kwargs['on_content_delta'](whitespace)
        await asyncio.Event().wait()

    svc.provider_factory = lambda: SimpleNamespace(_call_llm=stalled, model_smart='test-qwen', client=None)
    job = start(svc)
    await asyncio.wait_for(svc.run('c-pilot', job['id']), timeout=4)
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed'
    assert saved['error']['code'] == 'KnowledgeModelIdleTimeout'
    assert saved['partial_text'] == prefix + whitespace
    assert len(calls) == 1
    assert saved['stage_observations'][0]['last_content_seconds'] == 0
    assert (saved['last_content_at'] is not None) == bool(prefix)
    assert svc.repository.load_raw('c-pilot') == before
