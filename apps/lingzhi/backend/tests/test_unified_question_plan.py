from copy import deepcopy
import pytest
from backend.tests.test_criterion_question_generation import course


def test_ordinary_generation_freezes_the_same_target_contract_as_explicit_generation():
    from knowledge_criterion_generation import request_plan, plan
    c=course()
    ordinary=request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    explicit=plan(c,{'C':'CR'},['K'],['L1'],'ordinary-one')
    assert ordinary['targets']==explicit['targets']
    assert ordinary['criterion_revision_refs']=={'C':'CR'}
    assert ordinary['entrypoint']=='lecture' and ordinary['default_count']==3
    assert c==course()


def test_no_adopted_or_reviewed_targets_never_falls_back_to_lecture_labels():
    from knowledge_criterion_generation import request_plan, PreparationRequired
    c=course();c.pop('course_knowledge_base')
    with pytest.raises(PreparationRequired)as error:request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    assert error.value.code=='knowledge_baseline_required'
    c=course();c['course_knowledge_base']['mastery_criteria'][0]['review_status']='draft'
    with pytest.raises(PreparationRequired)as error:request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    assert error.value.code=='reviewed_criteria_required'


def test_generic_adopted_points_get_exact_slots_without_reclassifying_knowledge():
    from knowledge_criterion_generation import request_plan
    from assessment_blueprint import compile_course_assessment_blueprint
    c=course();point=c['course_knowledge_base']['knowledge_points'][0]
    point['granularity_status']='candidate';c['course_knowledge_base']['tree_schema']='knowledge_first_generic_v1'
    c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    original=deepcopy(c['course_knowledge_base'])
    b=compile_course_assessment_blueprint(c)
    slots=[s for n in b['nodes']for s in n['slots']]
    assert slots and all(s['primary_knowledge_ids']==['K'] and s['criterion_target']['criterion']['criterion_id']=='C'for s in slots)
    assert c['course_knowledge_base']==original


def test_reviewed_response_form_controls_typed_validator():
    from knowledge_criterion_generation import request_plan
    from assessment_blueprint import compile_course_assessment_blueprint
    c=course();c['course_knowledge_base']['mastery_criteria'][0]['assessment_format']='numeric_response'
    c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    slots=[s for n in compile_course_assessment_blueprint(c)['nodes']for s in n['slots']]
    assert slots[0]['input_mode']=='numeric_unit' and slots[0]['validation_mode']=='numeric_unit_validator'


def test_retry_reuses_frozen_semantic_targets_and_rejects_new_revisions():
    from knowledge_criterion_generation import request_plan, PreparationRequired
    c=course();p=request_plan(c,node_ids=['L1'],request_id='original')
    again=request_plan(c,node_ids=['L1'],request_id='retry-one',prior_plan=p)
    assert again==p
    c['course_knowledge_base']['mastery_criteria'][0]['revision_id']='new'
    with pytest.raises(PreparationRequired):request_plan(c,node_ids=['L1'],request_id='retry-one',prior_plan=p)


def test_repair_must_not_transplant_answer_from_a_restored_new_question():
    from assessment_orchestrator import _apply_targeted_repair_candidate
    original={'question_spec':{'stimulus':{'rendered_text':'原题'},'task':{'rendered_text':'求结果'}},
              'solution':{'canonical_answer':{'value':0},'validation_mode':'numeric_unit_validator'}}
    proposed=deepcopy(original);proposed['question_spec']['stimulus']['rendered_text']='另一道题';proposed['solution']['canonical_answer']={'value':2}
    repaired,guard=_apply_targeted_repair_candidate(original,proposed,issue_codes=['VALIDATION_FAILED'])
    assert repaired==original and guard['rejected']is True


def test_failure_preserves_specific_validator_reason():
    from assessment_orchestrator import _apply_independent_validation
    c={'question_spec':{},'solution_envelope':{'canonical_answer':{'value':2},'validation_mode':'numeric_unit_validator'}}
    _apply_independent_validation(c,{'passed':False,'deterministic':True,'validation_mode':'numeric_unit_validator','issue_code':'numeric_or_unit_mismatch'},
                                  {'answer':{'value':1},'work':[],'summary':''})
    assert c['solution_validation']['issues'][0]['code']=='independent_solution_mismatch'
    assert c['solution_validation']['issues'][0]['message']


@pytest.mark.asyncio
async def test_ordinary_admission_blocks_missing_baseline_before_job_creation(monkeypatch):
    from routers import question_bank as routes
    from fastapi import HTTPException
    from unittest.mock import AsyncMock
    c=course();c.pop('course_knowledge_base')
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=c))
    with pytest.raises(HTTPException)as error:
        await routes.rebuild_question_bank('c',routes.QuestionBankRebuildRequest(request_id='ordinary-one',scope='nodes',node_ids=['L1'],questions_per_lesson=3),x_user_id='teacher')
    assert error.value.status_code==409 and error.value.detail['code']=='knowledge_baseline_required'


@pytest.mark.asyncio
async def test_ordinary_admission_freezes_reviewed_targets_before_executor(monkeypatch,tmp_path):
    from routers import question_bank as routes
    from question_bank_jobs import QuestionBankRebuildJobRepository
    from unittest.mock import AsyncMock
    c=course();jobs=QuestionBankRebuildJobRepository(tmp_path);submitted=[]
    class Executor:
        def submit(self,**kwargs):submitted.append(kwargs)
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=c))
    monkeypatch.setattr(routes,'_question_bank_source_material_asset_ids',lambda *_:set())
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',jobs)
    monkeypatch.setattr(routes,'question_bank_rebuild_executor',Executor())
    response=await routes.rebuild_question_bank('c',routes.QuestionBankRebuildRequest(request_id='ordinary-one',scope='nodes',node_ids=['L1'],questions_per_lesson=3),x_user_id='teacher')
    frozen=jobs.load('c',response['job_id'])['criterion_generation_plan']
    assert frozen['criterion_revision_refs']=={'C':'CR'}
    assert submitted[0]['course']['_criterion_generation_plan']==frozen
