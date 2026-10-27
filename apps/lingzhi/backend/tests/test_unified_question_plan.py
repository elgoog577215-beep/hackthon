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
    c['course_knowledge_base']['mastery_criteria'][0]['checkpoints']=c['course_knowledge_base']['mastery_criteria'][0]['checkpoints'][:1]
    c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    slots=[s for n in compile_course_assessment_blueprint(c)['nodes']for s in n['slots']]
    assert slots[0]['input_mode']=='numeric_unit' and slots[0]['validation_mode']=='numeric_unit_validator'


def test_unbound_lecture_tags_do_not_satisfy_unified_quantity():
    from knowledge_criterion_generation import request_plan
    from assessment_blueprint import compile_course_assessment_blueprint
    from assessment_quantity import build_quantity_plan
    c=course();c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='ordinary-one')
    b=compile_course_assessment_blueprint(c)
    old={'items':[{'node_id':'L1','course_knowledge_refs':['K'],'lifecycle_status':'needs_review'}]}
    plan=build_quantity_plan(c,b,previous=old,node_ids=['L1'],count=3,append_only=False,batch_id='batch')
    assert sum(len(rows)for rows in plan['slots'].values())==3


def test_answer_change_invalidates_blind_solver_cache_without_exposing_answer():
    from assessment_orchestrator import _blind_solution_cache_key
    spec={'task':{'rendered_text':'求结果'},'input_contract':{'mode':'numeric_unit'}}
    first={'solution':{'canonical_answer':{'value':0}}};second={'solution':{'canonical_answer':{'value':2}}}
    assert _blind_solution_cache_key(spec,first)!=_blind_solution_cache_key(spec,second)


def test_nonexistent_is_not_a_valid_numeric_zero_placeholder():
    from assessment_solution_protocol import numeric_domain_issue
    slot={'criterion_target':{},'assessment_purpose':'criterion_check','input_mode':'numeric_unit'}
    assert numeric_domain_issue(slot,{'result_status':'nonexistent','answer':{'value':0}})['code']=='ANSWER_DOMAIN_MISMATCH'
    assert numeric_domain_issue(slot,{'result_status':'determinate','answer':{'value':0}})is None


@pytest.mark.asyncio
async def test_single_numeric_checkpoint_keeps_deterministic_grading_without_model():
    from practice_grading import PracticeGrader
    criterion=deepcopy(course()['course_knowledge_base']['mastery_criteria'][0]);criterion['checkpoints']=criterion['checkpoints'][:1]
    question={'_knowledge_criterion':criterion,'question_type':'numeric_response','input_contract':{'mode':'numeric_unit'},
              'validation_mode':'numeric_unit_validator','grading_policy':{'method':'typed_validator'},
              'answer_spec':{'canonical_answer':{'value':1,'unit':'无'},'validator_config':{'unit_aliases':['无']}},
              'validation_policy':{'mastery_eligible':False}}
    grader=object.__new__(PracticeGrader)
    result=await grader.grade(question,{'submitted_answer_payload':{'value':1,'unit':'无'}})
    assert result['passed']is True and result['criterion_results']=={'C':{'A':True}}
    assert result['grading_method']!='knowledge_checkpoint_v2'


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
async def test_ordinary_admission_blocks_missing_baseline_before_job_creation(monkeypatch,tmp_path):
    from routers import question_bank as routes
    from fastapi import HTTPException
    from unittest.mock import AsyncMock
    from question_bank_jobs import QuestionBankRebuildJobRepository
    c=course();c.pop('course_knowledge_base')
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=c))
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',QuestionBankRebuildJobRepository(tmp_path))
    class Executor:
        def submit(self,**kwargs):raise AssertionError('Admission must block before executor')
    monkeypatch.setattr(routes,'question_bank_rebuild_executor',Executor())
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


def test_readiness_and_current_binding_projection_are_separate_from_publication():
    from knowledge_criterion_generation import generation_readiness, plan, seal_binding
    from question_bank_knowledge import binding_view
    c=course();assert generation_readiness(c)['ready']is True
    no=deepcopy(c);no.pop('course_knowledge_base')
    assert generation_readiness(no)['code']=='knowledge_baseline_required'
    target=plan(c,{'C':'CR'},['K'],['L1'],'projection')['targets'][0]
    q={'revision_id':'Q','item_id':'I','prompt':'判断并说明依据','primary_knowledge_ids':['K'],
       'assessment_binding_schema':'atomic_assessment_v1','knowledge_revision_refs':{'K':'KR'},
       'knowledge_baseline_revision':c['course_knowledge_base']['revision_id'],'question_spec':{},'solution_revision_id':'S',
       'criterion_target':target,'lifecycle_status':'needs_review'}
    q['criterion_binding']=seal_binding(q,target,{'passed':True,'solution_consistent':True,'confidence':.95,'reviewer_triggered':True,
        'criterion_alignment':{'checkpoints':{'A':True,'B':True},'conditions_controlled':True,'reason':'题目要求逐项说明'}})
    assert binding_view(c,{'items':[q]})['items'][0]['status']=='bound'
    c['course_knowledge_base']['mastery_criteria'][0]['checkpoints'][0]['pass_condition']='改变判据'
    assert binding_view(c,{'items':[q]})['items'][0]['status']=='stale'


def test_review_anchor_uses_an_exact_public_field_reference():
    from question_measurement_contract import bind_review_anchor
    q={'task':{'rendered_text':'写出余项并注明 β 的范围。'},'stimulus':{'rendered_text':'给定完整数据'}}
    r={'passed':True,'review_witness':{'observation_test':{'public_anchor_ref':'task','public_anchor':r'写出余项并注明 \beta 的范围'}}}
    bound=bind_review_anchor(r,q)
    assert bound['review_witness']['observation_test']['public_anchor']==q['task']['rendered_text']
    r['review_witness']['observation_test']['public_anchor_ref']='invented'
    assert bind_review_anchor(r,q)['passed']is False


def test_measurement_numeric_predictions_are_losslessly_normalized():
    from assessment_measurement_design import attach_measurement_designs
    c={'assessment_slot':{'slot_id':'one'}}
    p={'target_rule':'规则','public_material':'给定数值','ask':'求上界','incorrect_rule':'漏掉阶乘',
       'trace':'代入并核对','correct_prediction':0.125,'incorrect_prediction':0.25}
    result=attach_measurement_designs([c],{'plans':[{'slot_id':'one','plan':p}]})
    assert result[0]['private_measurement_design']['correct_prediction']=='0.125'
