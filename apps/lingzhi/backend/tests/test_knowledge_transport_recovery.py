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
@pytest.mark.parametrize('persistent', [False, True])
async def test_saved_nine_relation_shards_stay_frozen_and_only_seven_eight_recover(svc, monkeypatch, persistent):
    setup_course(svc, monkeypatch); fake_provider(svc)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    # Exercise the frozen historical relation fixture explicitly, not a new registry task.
    svc.authoring.update_job('c-pilot',job['id'],generation_contract='legacy_validation')
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
        if persistent or len(calls) <= 2: raise AIProviderRequestError('Connection error.')
        return await base._call_llm(prompt, **kwargs)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=interrupted, model_smart='test-qwen', client=None)
    await svc.run('c-pilot', job['id']); saved = svc.authoring.get_job('c-pilot', job['id'])
    if persistent:
        assert saved['status'] == 'failed' and calls == ['tree_relations'] * 6
        assert saved['error']['stage'] == saved['pipeline_stage'] == 'tree_relations'
        assert saved['error']['batch_id'] in {'tree-relations-7', 'tree-relations-8'}
        assert saved['error']['transport_attempts'] == 3
        assert saved['error']['recovery_action'] == 'continue_missing_batches'
    else:
        assert saved['status'] == 'completed' and calls == ['tree_relations'] * 4
    actual = saved['checkpoint']['atomic_pipeline']
    assert {k: actual[k] for k in protected} == protected
    assert [b for b in actual['relations']['batches'] if b['id'] not in {'tree-relations-7', 'tree-relations-8'}] == completed
    assert {v['batch_id'] for v in saved['stage_observations']} == {'tree-relations-7', 'tree-relations-8'}
    assert svc.repository.load_raw('c-pilot') == baseline
    assert len(svc.authoring.load('c-pilot')['jobs']) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('message', ['Error code: 401 - invalid key', 'Error code: 429 - quota exhausted', 'empty_response'])
async def test_non_connection_provider_failures_are_not_retried(svc, monkeypatch, message):
    from knowledge_atomic import call_stage
    setup_course(svc, monkeypatch); job=start(svc);calls=[]
    async def model(*args, **kwargs): calls.append(1);raise AIProviderRequestError(message)
    with pytest.raises(AIProviderRequestError):
        await call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=model),'输入','content_review')
    assert calls==[1]


@pytest.mark.asyncio
async def test_source_change_during_backoff_prevents_the_next_request(svc, monkeypatch):
    from knowledge_atomic import call_stage
    from knowledge_transport import model_scope
    from course_repository import CourseDocumentConflict
    setup_course(svc, monkeypatch);job=start(svc);calls=[];changed=False
    async def pause(_seconds):
        nonlocal changed
        changed=True
    def guard():
        if changed: raise CourseDocumentConflict('来源已变化')
    async def model(*args,**kwargs):calls.append(1);raise AIProviderRequestError('Connection error.')
    monkeypatch.setattr('knowledge_transport.retry_pause',pause)
    with model_scope(validate_source=guard), pytest.raises(CourseDocumentConflict,match='来源'):
        await call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=model),'输入','content_review')
    assert calls==[1]


@pytest.mark.asyncio
async def test_parallel_requests_share_a_job_retry_budget(svc, monkeypatch):
    import asyncio
    from knowledge_atomic import call_stage
    from knowledge_transport import model_scope
    setup_course(svc, monkeypatch);job=start(svc);calls=[];budget={'used':5,'active':{}}
    async def pause(_seconds):await asyncio.sleep(0)
    async def model(*args,**kwargs):calls.append(1);raise AIProviderRequestError('Connection error.')
    monkeypatch.setattr('knowledge_transport.retry_pause',pause)
    with model_scope(retry_budget=budget):
        result=await asyncio.gather(*(call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=model),'输入','content_review') for _ in range(2)),return_exceptions=True)
    assert all(isinstance(e,AIProviderRequestError) for e in result)
    assert len(calls)==3 and budget['used']==6 and budget['active']=={}


def test_light_status_keeps_recovery_fields_without_bodies():
    from knowledge_generation_status import job_status
    result=job_status({'id':'j','status':'running','transport_retry_active_count':1,'transport_retry_stage':'tree_relations',
        'failed_stage':'tree_relations','partial_text':'PRIVATE'},'2026-10-19T00:00:00+00:00')
    assert result['transport_retry_stage']==result['failed_stage']=='tree_relations'
    assert result['transport_retry_active_count']==1 and 'partial_text' not in result


def test_local_persistence_error_cannot_inherit_network_retry_from_exception_context():
    from knowledge_transport import transient_connection
    error=PermissionError('cannot save checkpoint');error.__context__=ConnectionError('connection reset')
    assert not transient_connection(error)


@pytest.mark.asyncio
async def test_cancellation_during_backoff_prevents_the_next_request(svc, monkeypatch):
    from knowledge_atomic import call_stage
    from course_repository import CourseDocumentConflict
    setup_course(svc,monkeypatch);job=start(svc);calls=[]
    async def pause(_seconds):svc.authoring.update_job('c-pilot',job['id'],status='cancelled',phase='cancelled')
    async def model(*args,**kwargs):calls.append(1);raise AIProviderRequestError('Connection error.')
    monkeypatch.setattr('knowledge_transport.retry_pause',pause)
    with pytest.raises(CourseDocumentConflict):
        await call_stage(svc,'c-pilot',job['id'],SimpleNamespace(_call_llm=model),'输入','content_review')
    assert calls==[1] and svc.authoring.get_job('c-pilot',job['id'])['status']=='cancelled'


@pytest.mark.asyncio
async def test_authentication_cause_is_not_mislabeled_as_a_retryable_connection(svc, monkeypatch):
    setup_course(svc,monkeypatch);calls=[]
    async def model(*args,**kwargs):
        calls.append(1);cause=RuntimeError('unauthorized');cause.status_code=401
        raise AIProviderRequestError('Connection error.') from cause
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test-qwen',client=None)
    job=start(svc);await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert calls==[1] and saved['error']['code']!='ModelConnectionUnavailable'


@pytest.mark.asyncio
async def test_relation_validation_failure_keeps_its_stage_when_hierarchy_finishes_later(svc, monkeypatch):
    import asyncio
    from course_repository import CourseDocumentConflict
    setup_course(svc,monkeypatch);fake_provider(svc);base=svc.provider_factory()
    async def model(prompt,**kwargs):
        if json.loads(prompt.split('\nINPUT_JSON:\n')[1])['stage'].startswith('hierarchy'):await asyncio.sleep(.05)
        return await base._call_llm(prompt,**kwargs)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test-qwen',client=None)
    def reject(*args,**kwargs):raise CourseDocumentConflict('关系语义未通过')
    monkeypatch.setattr('knowledge_tree_relations.compile_relations',reject)
    job=start(svc,extraction_mode='single_pass_v1',organize_hierarchy=True,include_relations=True)
    svc.authoring.update_job('c-pilot',job['id'],generation_contract='legacy_validation')
    await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='failed' and saved['error']['stage']==saved['pipeline_stage']=='tree_relations'
