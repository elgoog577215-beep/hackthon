from copy import deepcopy

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_relation_generation import seed, provider, start
from knowledge_first import TREE_JOB, knowledge_revision
from course_repository import CourseDocumentConflict


def candidate(svc,monkeypatch,blocked=True):
    tree=seed(svc,monkeypatch);raw=svc.repository.load_raw('c-pilot');context=svc._context(raw,'handouts','cpu')
    tree.update(status='candidate',revision_id='candidate-v1',atomic_assessment={'ready_for_adoption':not blocked,
        'issues':[{'code':'source_focus_pending','severity':'blocking'}] if blocked else []})
    job=svc.authoring.create_job('c-pilot','tree',job_type=TREE_JOB,request_id='source-tree')
    job=svc.authoring.update_job('c-pilot',job['id'],status='completed',phase='completed',progress=100,
        actor=raw['owner_id'],source_mode='handouts',knowledge_lesson_id='cpu',knowledge_pipeline='inventory_atomic_v1',
        source_document_revision=raw.get('course_document_revision'),source_knowledge_revision=knowledge_revision(raw),
        source_context_revision=context['revision_id'],request_snapshot={'knowledge_generation_context':context},checkpoint={'candidate':tree})
    return job,tree


@pytest.mark.asyncio
async def test_relations_on_pending_candidate_preserve_content_and_quality_gate(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch);before=deepcopy(svc.repository.load_raw('c-pilot'));calls=provider(svc)
    job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='completed'
    result=saved['checkpoint']['candidate']
    for field in ('knowledge_points','categories','atomic_assessment','sources','lessons'):
        assert result.get(field)==tree.get(field)
    assert result['relation_assessment']['source_job_id']==source['id']
    assert all(c['stage']=='relations' for c in calls)
    assert svc.authoring.get_job('c-pilot',source['id'])==source
    view=svc.view('c-pilot',source_mode='handouts')
    with pytest.raises(CourseDocumentConflict,match='阻塞'):
        svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'],confirm_relations=True)
    assert svc.repository.load_raw('c-pilot')==before


@pytest.mark.asyncio
async def test_bad_relation_is_kept_for_review_without_failing_completed_knowledge(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch)
    def corrupt(data,result):
        if result['decisions'][0]['links']:result['decisions'][0]['links'][0]['evidence'][0]['quote']='not in source'
    provider(svc,mutate=corrupt);job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='completed'
    result=saved['checkpoint']['candidate'];assert result['relation_assessment']['issues']
    assert result['knowledge_points']==tree['knowledge_points'] and result['atomic_assessment']==tree['atomic_assessment']


@pytest.mark.asyncio
async def test_model_disconnect_only_fails_relation_task_and_keeps_source_candidate(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch);provider(svc,fail_at=1)
    job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    assert svc.authoring.get_job('c-pilot',job['id'])['status']=='failed'
    assert svc.authoring.get_job('c-pilot',source['id'])==source
    assert svc.view('c-pilot',source_mode='handouts')['candidate']['revision_id']==tree['revision_id']


@pytest.mark.parametrize('field,value',[('actor','foreign'),('status','failed'),('knowledge_lesson_id','memory'),('source_document_revision','stale')])
def test_foreign_stale_incomplete_or_other_lesson_candidate_is_rejected(svc,monkeypatch,field,value):
    source,_=candidate(svc,monkeypatch)
    state=svc.authoring.load('c-pilot');state['jobs'][source['id']][field]=value;svc.authoring._save(state)
    with pytest.raises(CourseDocumentConflict):start(svc,relation_source_job_id=source['id'])


@pytest.mark.asyncio
async def test_source_change_during_relation_request_prevents_candidate_save(svc,monkeypatch):
    source,_=candidate(svc,monkeypatch)
    def mutate(data,result):
        state=svc.authoring.load('c-pilot');state['jobs'][source['id']]['checkpoint']['candidate']['revision_id']='changed';svc.authoring._save(state)
    provider(svc,mutate=mutate);job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='failed' and not saved['checkpoint'].get('candidate')


@pytest.mark.asyncio
async def test_candidate_relations_adoption_requires_original_quality_confirmations(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch,blocked=False)
    state=svc.authoring.load('c-pilot');state['jobs'][source['id']]['checkpoint']['candidate']['atomic_assessment']['issues']=[{'severity':'review','code':'compound_review'}];svc.authoring._save(state)
    provider(svc);job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    view=svc.view('c-pilot',source_mode='handouts')
    with pytest.raises(CourseDocumentConflict,match='复合'):
        svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'],confirm_relations=True)
    svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'],
        confirm_relations=True,confirm_atomic_review=True)
    adopted=svc.repository.load_raw('c-pilot')['course_knowledge_base']
    assert adopted['knowledge_points']==tree['knowledge_points']
    assert adopted['status']=='accepted'


@pytest.mark.asyncio
async def test_missing_relation_review_saves_a_blocked_candidate_instead_of_losing_knowledge(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch)
    provider(svc,mutate=lambda data,result:result.update(decisions=[]))
    job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='completed'
    result=saved['checkpoint']['candidate']
    assert result['knowledge_points']==tree['knowledge_points']
    assert result['relation_assessment']['ready_for_adoption'] is False
    assert all(i['severity']=='blocking' for i in result['relation_assessment']['issues'])


@pytest.mark.asyncio
async def test_cycle_suggestion_is_quarantined_without_dropping_unrelated_links(svc,monkeypatch):
    source,tree=candidate(svc,monkeypatch)
    a,b=tree['knowledge_points'][:2]
    edge={'id':'existing-edge','source_id':a['knowledge_id'],'target_id':b['knowledge_id'],'type':'prerequisite','context':'original','conditions':[]}
    state=svc.authoring.load('c-pilot');state['jobs'][source['id']]['checkpoint']['candidate']['relations']=[edge];svc.authoring._save(state)
    provider(svc);job=start(svc,relation_source_job_id=source['id']);await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='completed'
    result=saved['checkpoint']['candidate']
    assert edge in result['relations'] and any(e['type']=='applies_to' for e in result['relations'])
    assert any('环' in i['message'] for i in result['relation_assessment']['issues'])
