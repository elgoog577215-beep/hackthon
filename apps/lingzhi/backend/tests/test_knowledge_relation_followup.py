import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_candidate_relations import candidate
from backend.tests.test_knowledge_relation_generation import provider, start, model_response


@pytest.mark.asyncio
async def test_completed_tree_automatically_runs_one_independent_relation_job(svc, monkeypatch):
    source, tree = candidate(svc, monkeypatch)
    svc.authoring.update_job('c-pilot', source['id'], auto_relations=True)
    calls = provider(svc)
    async def forbidden(*args):
        pytest.fail('Completed knowledge must never be regenerated')
    monkeypatch.setattr('knowledge_atomic.run_atomic', forbidden)
    await svc.run('c-pilot', source['id'])
    await svc.run('c-pilot', source['id'])
    jobs = list(svc.authoring.load('c-pilot')['jobs'].values())
    related = [j for j in jobs if j.get('relation_source_job_id') == source['id']]
    assert len(related) == 1 and related[0]['status'] == 'completed'
    saved = svc.authoring.get_job('c-pilot', source['id'])
    assert saved['status'] == 'completed' and saved['checkpoint']['candidate'] == tree
    assert saved['relation_followup']['job_id'] == related[0]['id']
    assert len(calls) == 2 and all(c['stage'] == 'relations' for c in calls)
    duplicate = start(svc, 'manual-double-click', relation_source_job_id=source['id'])
    assert duplicate['id'] == related[0]['id']


@pytest.mark.asyncio
async def test_tree_is_persisted_before_followup_and_failure_does_not_fail_tree(svc, monkeypatch):
    source, tree = candidate(svc, monkeypatch)
    svc.authoring.update_job('c-pilot', source['id'], status='pending', checkpoint={}, auto_relations=True)
    async def extract(service, cid, jid):
        service.authoring.update_job(cid, jid, status='completed', progress=100, checkpoint={'candidate':tree})
    monkeypatch.setattr('knowledge_atomic.run_atomic', extract)
    async def disconnected(*args, **kwargs):
        assert svc.authoring.get_job('c-pilot', source['id'])['checkpoint']['candidate'] == tree
        raise ValueError('invalid model response')
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=disconnected, model_smart='test', client=None)
    await svc.run('c-pilot', source['id'])
    saved = svc.authoring.get_job('c-pilot', source['id'])
    assert saved['status'] == 'completed' and saved['progress'] == 100
    child = svc.authoring.get_job('c-pilot', saved['relation_followup']['job_id'])
    assert child['status'] == 'failed'
    assert svc.view('c-pilot', source_mode='handouts')['candidate']['revision_id'] == tree['revision_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_status', ['failed', 'cancelled', 'paused'])
async def test_incomplete_tree_never_starts_followup(svc, monkeypatch, failure_status):
    source, _ = candidate(svc, monkeypatch)
    svc.authoring.update_job('c-pilot', source['id'], status='pending', checkpoint={}, auto_relations=True)
    async def extract(service, cid, jid):
        service.authoring.update_job(cid, jid, status=failure_status)
    monkeypatch.setattr('knowledge_atomic.run_atomic', extract)
    await svc.run('c-pilot', source['id'])
    assert len(svc.authoring.load('c-pilot')['jobs']) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('persistent', [False, True])
async def test_network_recovery_is_bounded_and_never_repeats_completed_batches(svc, monkeypatch, persistent):
    source, tree = candidate(svc, monkeypatch)
    before = deepcopy(source)
    calls = []
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data['focus_keys'])
        if len(calls) == 2 or persistent and len(calls) > 2:
            raise httpx.ConnectError('isolated disconnect')
        result = json.dumps(model_response(data), ensure_ascii=False)
        kwargs['on_content_delta'](result)
        return result
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    job = start(svc, relation_source_job_id=source['id'])
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == ('failed' if persistent else 'completed')
    assert len(calls) == (4 if persistent else 3)
    assert calls.count(calls[0]) == 1 and calls[1:] == [calls[1]] * (len(calls)-1)
    assert svc.authoring.get_job('c-pilot', source['id']) == before
    if persistent:
        assert saved['error']['code'] == 'RelationConnectionUnavailable'
        assert saved['completed_batches'] == 1
        replay = provider(svc)
        resumed = start(svc, 'resume', resume_job_id=job['id'])
        await svc.run('c-pilot', resumed['id'])
        assert len(replay) == 1
        assert svc.authoring.get_job('c-pilot', resumed['id'])['status'] == 'completed'


@pytest.mark.asyncio
async def test_new_candidate_does_not_display_previous_relation_run(svc, monkeypatch):
    source, _ = candidate(svc, monkeypatch); provider(svc)
    job = start(svc, relation_source_job_id=source['id']); await svc.run('c-pilot', job['id'])
    newer = svc.authoring.create_job('c-pilot','tree',job_type=source['type'],request_id='new-source')
    svc.authoring.update_job('c-pilot',newer['id'],**{k:deepcopy(v) for k,v in source.items()
        if k not in {'id','course_id','request_id','created_at','updated_at'}})
    assert svc.view('c-pilot',source_mode='handouts')['relation_runs'] == []

