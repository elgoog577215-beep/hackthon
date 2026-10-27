from copy import deepcopy
import pytest
from backend.tests.test_knowledge_check_flow import fixture


def course():
    c,criterion,task=fixture();c['owner_id']='teacher'
    c['nodes']=[{'node_id':'L1','node_level':2,'node_name':'变化','node_content':'两个量的变化及其判断依据'}]
    point=c['course_knowledge_base']['knowledge_points'][0]
    point.update(status='active',granularity_status='atomic',meta_question='分别判断两个量并说明依据',source_refs=['S1'])
    c['course_knowledge_base']['sources']=[{'source_id':'S1','text':'两个量的变化及其判断依据'}]
    return c


def test_plan_is_exact_current_and_batch_scoped():
    from knowledge_criterion_generation import plan,validate_plan
    c=course();p=plan(c,{'C':'CR'},['K'],['L1'],'request-one')
    assert p['criterion_revision_refs']=={'C':'CR'}
    assert p['targets'][0]['criterion']['checkpoints'][0]['checkpoint_id']=='A'
    assert p['batch_id']!=plan(c,{'C':'CR'},['K'],['L1'],'request-two')['batch_id']
    for patch in [{'revision_id':'old'},{'readiness':'needs_core_review'},{'review_status':'draft'}]:
        stale=deepcopy(c);stale['course_knowledge_base']['mastery_criteria'][0].update(patch)
        with pytest.raises(ValueError):validate_plan(stale,p)
    with pytest.raises(ValueError):plan(c,{'C':'CR'},['unknown'],['L1'],'request-one')
    with pytest.raises(ValueError):plan(c,{'C':'CR'},['K'],['other'],'request-one')


def test_existing_slots_are_untouched_without_a_criterion_request():
    from knowledge_criterion_generation import decorate_slots,plan
    c=course();slots=[{'slot_id':'old','generation_key':'old','primary_knowledge_ids':['K'],
        'target_objective':{'objective':'知识目标'},'practice_level':'concept_check','input_mode':'choice'}]
    assert decorate_slots(slots,c)==slots
    c['_criterion_generation_plan']=plan(c,{'C':'CR'},['K'],['L1'],'request-one')
    out=decorate_slots(slots,c)
    assert len(out)==1 and out[0]['question_form']=='short_answer' and out[0]['input_mode']=='rich_text'
    assert out[0]['criterion_target']['criterion']['revision_id']=='CR'
    assert out[0]['generation_key']!='old' and slots[0]['input_mode']=='choice'


def test_blueprint_preserves_short_answer_form_and_frozen_criterion():
    from knowledge_criterion_generation import plan
    from assessment_blueprint import compile_course_assessment_blueprint
    c=course();c['assessment_variant_count']=1
    c['_criterion_generation_plan']=plan(c,{'C':'CR'},['K'],['L1'],'request-one')
    b=compile_course_assessment_blueprint(c)
    slots=[s for n in b['nodes']for s in n['slots']]
    assert len(slots)==1 and slots[0]['question_form']=='short_answer'
    assert slots[0]['criterion_target']['criterion']['criterion_id']=='C'


def test_alignment_must_cover_every_checkpoint_before_binding():
    from knowledge_criterion_generation import enforce_alignment,seal_binding,valid_binding,plan
    c=course();target=plan(c,{'C':'CR'},['K'],['L1'],'request-one')['targets'][0]
    slot={'criterion_target':target}
    bad=enforce_alignment({'passed':True,'confidence':.99,'solution_consistent':True,'issues':[]},slot)
    assert bad['passed']is False and bad['issues'][0]['code']=='CRITERION_ALIGNMENT_INCOMPLETE'
    report={'passed':True,'confidence':.95,'solution_consistent':True,'reviewer_triggered':True,
        'criterion_alignment':{'checkpoints':{'A':True,'B':True},'conditions_controlled':True,'reason':'任务要求分别判断并说明依据'},'issues':[]}
    q={'prompt':'判断变化并说明理由','question_spec':{'task':{'rendered_text':'判断变化并说明理由'}},'solution_revision_id':'S',
        'primary_knowledge_ids':['K'],'concept_ids':['K'],'knowledge_revision_refs':{'K':'KR'}}
    binding=seal_binding(q,target,report)
    assert valid_binding({**q,'criterion_binding':binding},target['criterion'])
    edited=deepcopy(q);edited['question_spec']['task']['rendered_text']='另一任务'
    assert not valid_binding({**edited,'criterion_binding':binding},target['criterion'])
    stale=deepcopy(target['criterion']);stale['checkpoints'][0]['pass_condition']='新判据'
    assert not valid_binding({**q,'criterion_binding':binding},stale)


def test_request_and_job_identity_freeze_criterion_selection(tmp_path):
    from routers.question_bank import QuestionBankRebuildRequest
    from question_bank_jobs import QuestionBankRebuildJobRepository
    args=dict(request_id='request-one',scope='nodes',node_ids=['L1'],knowledge_ids=['K'],knowledge_baseline_revision='kb',criterion_revision_refs={'C':'CR'})
    payload=QuestionBankRebuildRequest(**args)
    assert payload.criterion_revision_refs=={'C':'CR'}
    jobs=QuestionBankRebuildJobRepository(tmp_path)
    first,_=jobs.create_job('c',mode='incremental',actor_id='teacher',**args)
    other,_=jobs.create_job('c',mode='incremental',actor_id='teacher',**{**args,'criterion_revision_refs':{'D':'DR'}})
    assert first['job_id']!=other['job_id']
    assert jobs.load('c',first['job_id'])['criterion_revision_refs']=={'C':'CR'}


def test_existing_reviewer_receives_and_preserves_checkpoint_alignment():
    from assessment_orchestrator import _normalize_semantic_report,_batch_evaluation_prompt
    from knowledge_criterion_generation import plan
    c=course();target=plan(c,{'C':'CR'},['K'],['L1'],'request-one')['targets'][0]
    alignment={'checkpoints':{'A':True,'B':True},'conditions_controlled':True,'reason':'任务同时要求两个表现'}
    assert _normalize_semantic_report({'criterion_alignment':alignment})['criterion_alignment']==alignment
    text=_batch_evaluation_prompt([{'slot_id':'slot','slot':{'criterion_target':target},'question_spec':{},'objective':{}}])
    assert 'criterion_alignment'in text and 'checkpoints'in text


def test_generated_reviewed_binding_is_consumed_without_editing_the_knowledge_base():
    from knowledge_criterion_generation import plan,seal_binding
    from knowledge_check_flow import task_criterion
    c=course();criterion=c['course_knowledge_base']['mastery_criteria'][0];criterion['assessment_bindings']=[]
    target=plan(c,{'C':'CR'},['K'],['L1'],'request-one')['targets'][0]
    q={'prompt':'分别判断并说明依据','question_spec':{'task':{'rendered_text':'分别判断并说明依据'}},'solution_revision_id':'S',
        'primary_knowledge_ids':['K'],'concept_ids':['K'],'knowledge_revision_refs':{'K':'KR'},'question_type':'short_answer',
        'revision_id':'new-task','review_status':'approved','quality_status':'passed'}
    report={'passed':True,'confidence':.95,'solution_consistent':True,'reviewer_triggered':True,
        'criterion_alignment':{'checkpoints':{'A':True,'B':True},'conditions_controlled':True,'reason':'逐项覆盖'},'issues':[]}
    q['criterion_binding']=seal_binding(q,target,report)
    assert task_criterion(c,q)['criterion_id']=='C'
    assert criterion['assessment_bindings']==[]
    q['prompt']='改动后的另一个问题'
    assert task_criterion(c,q)is None


@pytest.mark.asyncio
async def test_stale_criterion_stops_publication_before_any_bundle_write(monkeypatch):
    from knowledge_criterion_generation import plan
    from routers import question_bank as routes
    from unittest.mock import AsyncMock
    c=course();c['_criterion_generation_plan']=plan(c,{'C':'CR'},['K'],['L1'],'request-one')
    stale=deepcopy(c);stale['course_knowledge_base']['mastery_criteria'][0]['revision_id']='new'
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=stale))
    def forbidden(*a,**k):raise AssertionError('stale criterion reached publication')
    monkeypatch.setattr(routes,'_course_with_rebuilt_assets',forbidden)
    with pytest.raises(ValueError,match='标准'):
        await routes._publish_rebuilt_course('c',c,{}, {},request_id='r',previous_question_bank_revision_id=None,previous_asset_revision_id=None)


def test_supply_is_owner_only_and_generation_scope_is_not_a_student_write(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from routers import question_bank as routes,practice
    c=course();monkeypatch.setattr(routes,'get_course_or_404',AsyncMock(return_value=c))
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=c))
    monkeypatch.setattr(routes,'load_active_question_bank',lambda *a,**k:None)
    monkeypatch.setattr(practice,'_questions',lambda *a,**k:[])
    monkeypatch.setattr(routes.question_bank_rebuild_job_repository,'latest_for_course',lambda *a:None)
    app=FastAPI();app.include_router(routes.router,prefix='/api');client=TestClient(app)
    url='/api/courses/c/question-bank/criterion-supply'
    params={'knowledge_id':'K','knowledge_revision':'KR','criterion_id':'C','criterion_revision':'CR'}
    result=client.get(url,params=params,headers={'X-User-Id':'teacher'})
    assert result.status_code==200 and result.json()['can_generate']is True
    assert result.json()['available_count']==0
    assert client.get(url,params=params,headers={'X-User-Id':'student'}).status_code==404
    c['course_knowledge_base']['mastery_criteria'][0]['readiness']='needs_core_review'
    assert client.get(url,params=params,headers={'X-User-Id':'teacher'}).status_code==409
