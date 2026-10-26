"""One frozen knowledge body, resumable additive enrichment, original owner."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course
from backend.tests.test_knowledge_core import row, transport_review
from course_repository import CourseDocumentConflict


def start(svc, request_id, **extra):
    view=svc.view('c-pilot',source_mode='handouts')
    return svc.start('c-pilot','tree',request_id,view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',**extra)[0]


def model_reply(payload):
    stage=payload['stage']
    if stage=='candidate_core_extract':
        return {'points':[row(),row('出栈','出栈移除并返回栈顶元素。')],'context_note':''}
    if stage=='candidate_core_review':return transport_review(payload['points'],payload['coverage_materials'])
    if stage=='candidate_core_identity_catalog':return {'identities':{p['key']:p['key'] for p in payload['points']}}
    if stage=='candidate_relations':return {'reviews':{k:'没有需要强连的关系'for k in payload['focus_keys']},'edges':[]}
    if stage=='kc_profiles':
        return {'profiles':{p['key']:{k:'针对这一完整知识的教学说明' for k in
            ['description','assessment_focus','assessment_format','common_mistakes','difficulty_cues']} for p in payload['profiles']}}
    raise AssertionError('Unexpected separate/legacy generation: '+stage)


def provider(svc,calls,override=None):
    async def model(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(payload)
        value=await override(payload) if override else model_reply(payload)
        return json.dumps(value,ensure_ascii=False)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)


async def seed(svc,monkeypatch):
    setup_course(svc,monkeypatch);calls=[];provider(svc,calls)
    job=start(svc,'seed-core',generation_mode='core_v1')
    await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    return saved


def body(tree):
    return {**{k:deepcopy(tree.get(k)) for k in ['categories','concept_groups','knowledge_coverage','lessons']},
        'knowledge_points':[{k:deepcopy(v) for k,v in p.items() if k!='kc_skill_profile'} for p in tree['knowledge_points']]}


@pytest.mark.asyncio
async def test_full_reuses_completed_body_and_only_enriches_frozen_points(svc,monkeypatch):
    original=await seed(svc,monkeypatch);before=deepcopy(svc.repository.load_raw('c-pilot'));calls=[];provider(svc,calls)
    job=start(svc,'enrich-existing',generation_mode='full_v1',base_job_id=original['id'])
    await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    tree=saved['checkpoint']['candidate']
    assert body(tree)==body(original['checkpoint']['candidate'])
    assert {p['stage'] for p in calls}=={'candidate_relations','kc_profiles'}
    assert tree['core_reuse']['origin_job_id']==original['id']
    assert tree['kc_profile_summary']['profile_count']==2
    assert all(p['kc_skill_profile']['knowledge_revision']==p['revision_id']for p in tree['knowledge_points'])
    assert svc.authoring.get_job('c-pilot',original['id'])==original
    assert svc.repository.load_raw('c-pilot')==before


@pytest.mark.asyncio
async def test_fresh_full_uses_the_same_core_pipeline_and_never_legacy_discovery(svc,monkeypatch):
    setup_course(svc,monkeypatch);calls=[];provider(svc,calls)
    job=start(svc,'fresh-full',generation_mode='full_v1')
    await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='completed',saved.get('error')
    assert [p['stage']for p in calls[:3]]==['candidate_core_extract','candidate_core_review','candidate_core_identity_catalog']
    assert {p['stage']for p in calls[3:]}=={'candidate_relations','kc_profiles'}


@pytest.mark.asyncio
async def test_completed_enrichment_is_reused_without_any_model_request(svc,monkeypatch):
    await seed(svc,monkeypatch);calls=[];provider(svc,calls)
    job=start(svc,'first-full',generation_mode='full_v1');await svc.run('c-pilot',job['id'])
    first=svc.authoring.get_job('c-pilot',job['id']);assert first['status']=='completed',first.get('error')
    calls.clear();repeat=start(svc,'repeat-full',generation_mode='full_v1')
    await svc.run('c-pilot',repeat['id']);saved=svc.authoring.get_job('c-pilot',repeat['id'])
    assert saved['status']=='completed',saved.get('error')
    assert not calls
    assert saved['checkpoint']['candidate']['knowledge_points']==first['checkpoint']['candidate']['knowledge_points']


@pytest.mark.asyncio
async def test_partial_enrichment_resume_keeps_success_and_does_not_rebuild_core(svc,monkeypatch):
    original=await seed(svc,monkeypatch);profile_done=asyncio.Event();calls=[]
    async def first(payload):
        if payload['stage']=='candidate_relations':
            await asyncio.wait_for(profile_done.wait(),2)
            raise ValueError('invalid relation response')
        assert payload['stage']=='kc_profiles'
        profile_done.set();return model_reply(payload)
    provider(svc,calls,first);job=start(svc,'partial-full',generation_mode='full_v1')
    await svc.run('c-pilot',job['id']);failed=svc.authoring.get_job('c-pilot',job['id'])
    assert failed['status']=='failed'
    assert body(failed['checkpoint']['atomic_pipeline']['core_tree'])==body(original['checkpoint']['candidate'])
    calls.clear();provider(svc,calls)
    resumed=start(svc,'resume-full',resume_job_id=job['id'])
    await svc.run('c-pilot',resumed['id']);saved=svc.authoring.get_job('c-pilot',resumed['id'])
    assert saved['status']=='completed',saved.get('error')
    assert [p['stage']for p in calls]==['candidate_relations']


@pytest.mark.asyncio
async def test_changed_material_and_incomplete_body_cannot_be_reused(svc,monkeypatch):
    original=await seed(svc,monkeypatch)
    saved=svc.authoring.load('c-pilot')
    saved['jobs'][original['id']]['checkpoint']['candidate']['atomic_assessment']['ready_for_adoption']=False
    svc.authoring._save(saved)
    with pytest.raises(CourseDocumentConflict):start(svc,'bad-body',generation_mode='full_v1',base_job_id=original['id'])
    saved['jobs'][original['id']]=deepcopy(original)
    saved['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content']+=' 新增一条独立知识。'
    svc.authoring._save(saved)
    with pytest.raises(CourseDocumentConflict):start(svc,'stale-body',generation_mode='full_v1',base_job_id=original['id'])


@pytest.mark.asyncio
async def test_adopted_current_body_can_be_enriched_without_regeneration(svc,monkeypatch):
    original=await seed(svc,monkeypatch);view=svc.view('c-pilot',source_mode='handouts')
    svc.adopt('c-pilot',original['id'],view['knowledge_revision'],view['document_revision'])
    accepted=deepcopy(svc.repository.load_raw('c-pilot')['course_knowledge_base']);calls=[];provider(svc,calls)
    job=start(svc,'enrich-adopted',generation_mode='full_v1');await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id']);assert saved['status']=='completed',saved.get('error')
    assert body(saved['checkpoint']['candidate'])==body(accepted)
    assert {p['stage']for p in calls}=={'candidate_relations','kc_profiles'}


@pytest.mark.asyncio
async def test_legacy_completed_relations_are_reused_and_only_missing_profiles_are_generated(svc,monkeypatch):
    original=await seed(svc,monkeypatch);state=svc.authoring.load('c-pilot');job=state['jobs'][original['id']]
    tree=job['checkpoint']['candidate'];keys=[p['key']for p in tree['knowledge_points']]
    job.update(generation_contract='knowledge_registry_v5',include_relations=True)
    job.pop('execution_contract',None);job.pop('generation_mode',None)
    job['checkpoint']['atomic_pipeline']['registry_relations']={'status':'completed','batches':[{'status':'completed','focus_keys':keys,'result':[]}]}
    tree['atomic_assessment']['relation_status']='completed'
    tree['relation_assessment']={'ready_for_adoption':True,'checked_points':len(keys),'mode':'with_tree','proposed_ids':[]}
    svc.authoring._save(state);calls=[];provider(svc,calls)
    new=start(svc,'reuse-historical-full',generation_mode='full_v1',base_job_id=original['id'])
    await svc.run('c-pilot',new['id']);saved=svc.authoring.get_job('c-pilot',new['id'])
    assert saved['status']=='completed',saved.get('error')
    assert [p['stage']for p in calls]==['kc_profiles']


@pytest.mark.asyncio
async def test_explicit_coverage_requirements_are_not_silently_discarded(svc,monkeypatch):
    setup_course(svc,monkeypatch);calls=[]
    async def model(payload):
        if payload['stage']=='candidate_required_coverage':
            return {'coverage':{u['key']:{'status':'missing','knowledge_ids':[],'reason':'现有知识没有承载这条独立结论'}for u in payload['units']}}
        return model_reply(payload)
    provider(svc,calls,model)
    required=[{'statement':'队列从队尾加入新元素。','branch':'队列','knowledge_type':'rule','profile_focus':'','check_intent':'说明入队位置'}]
    new=start(svc,'required-coverage',generation_mode='full_v1',coverage_units=required)
    await svc.run('c-pilot',new['id']);saved=svc.authoring.get_job('c-pilot',new['id'])
    assert saved['status']=='failed'
    assert 'candidate_required_coverage'in [p['stage']for p in calls]
    assert 'candidate_relations'not in [p['stage']for p in calls]
    assert saved['checkpoint']['atomic_pipeline']['required_coverage']['result']['missing_unit_ids']
