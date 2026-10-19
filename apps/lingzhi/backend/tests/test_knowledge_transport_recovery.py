import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ai_base import AIProviderRequestError
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_tree_relations import fake_provider


@pytest.mark.asyncio
async def test_zero_output_connection_failures_retry_the_identical_request_in_one_job(svc, monkeypatch):
    from knowledge_atomic import call_stage
    setup_course(svc, monkeypatch); job = start(svc); calls = []
    async def model(prompt, **kwargs):
        calls.append((prompt, kwargs['max_attempts']))
        if len(calls) < 3: raise AIProviderRequestError('Connection error.')
        return '{"ok":true}'
    result = await call_stage(svc, 'c-pilot', job['id'], SimpleNamespace(_call_llm=model), '冻结请求', 'content_review')
    assert result == '{"ok":true}' and calls == [('冻结请求', 1)] * 3
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert [v['status'] for v in saved['stage_observations']] == ['failed', 'failed', 'completed']
    assert [v['transport_attempt'] for v in saved['stage_observations']] == [1, 2, 3]
    assert len(svc.authoring.load('c-pilot')['jobs']) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('partial', [False, True])
async def test_retries_are_bounded_and_never_repeat_partial_output(svc, monkeypatch, partial):
    from knowledge_atomic import call_stage
    setup_course(svc, monkeypatch); job = start(svc); calls = []
    async def model(prompt, **kwargs):
        calls.append(1)
        if partial: kwargs['on_content_delta']('{"partial":')
        raise AIProviderRequestError('Connection error.')
    with pytest.raises(AIProviderRequestError):
        await call_stage(svc, 'c-pilot', job['id'], SimpleNamespace(_call_llm=model), '冻结请求', 'content_review')
    assert len(calls) == (1 if partial else 3)
    assert svc.authoring.get_job('c-pilot', job['id'])['partial_text'] == ('{"partial":' if partial else '')


@pytest.mark.asyncio
async def test_saved_nine_relation_shards_stay_frozen_and_only_seven_eight_recover(svc, monkeypatch):
    setup_course(svc, monkeypatch); fake_provider(svc)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    await svc.run('c-pilot', job['id']); original = svc.authoring.get_job('c-pilot', job['id'])
    assert original['status'] == 'completed'
    pipeline = deepcopy(original['checkpoint']['atomic_pipeline'])
    exemplar = pipeline['relations']['batches'][0]
    rows = [{**deepcopy(exemplar), 'id': f'tree-relations-{i}', 'checkpoint_marker': i} for i in range(1, 12)]
    for i in (6, 7):
        rows[i]['status'] = 'pending'; rows[i].pop('result', None); rows[i].pop('raw_response', None)
    pipeline['relations'].update(status='pending', batches=rows)
    completed = deepcopy([b for b in rows if b['status'] == 'completed'])
    protected = deepcopy({k: pipeline[k] for k in ('items', 'inventory_batches', 'batches', 'hierarchy')})
    baseline = deepcopy(svc.repository.load_raw('c-pilot'))
    restored = deepcopy(original); restored.update(id='isolated-interrupted-job', status='pending', phase='preparing',
        checkpoint={'atomic_pipeline': pipeline}, error=None, stage_observations=[], model_telemetry=[], model_call_count=0)
    state = svc.authoring.load('c-pilot'); state['jobs'] = {restored['id']: restored}; svc.authoring._save(state)
    job = restored
    fake_provider(svc); base = svc.provider_factory(); calls = []
    async def interrupted(prompt, **kwargs):
        stage = json.loads(prompt.split('\nINPUT_JSON:\n')[1])['stage']; calls.append(stage)
        if len(calls) <= 2: raise AIProviderRequestError('Connection error.')
        return await base._call_llm(prompt, **kwargs)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=interrupted, model_smart='test-qwen', client=None)
    await svc.run('c-pilot', job['id']); saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed' and calls == ['tree_relations'] * 4
    actual = saved['checkpoint']['atomic_pipeline']
    assert {k: actual[k] for k in protected} == protected
    assert [b for b in actual['relations']['batches'] if b['id'] not in {'tree-relations-7', 'tree-relations-8'}] == completed
    assert {v['batch_id'] for v in saved['stage_observations']} == {'tree-relations-7', 'tree-relations-8'}
    assert svc.repository.load_raw('c-pilot') == baseline
    assert len(svc.authoring.load('c-pilot')['jobs']) == 1
