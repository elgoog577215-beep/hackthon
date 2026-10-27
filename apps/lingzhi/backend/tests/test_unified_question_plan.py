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
@pytest.mark.parametrize('point_scope',[False,True])
async def test_ordinary_admission_freezes_reviewed_targets_before_executor(monkeypatch,tmp_path,point_scope):
    from routers import question_bank as routes
    from question_bank_jobs import QuestionBankRebuildJobRepository
    from unittest.mock import AsyncMock
    c=course();jobs=QuestionBankRebuildJobRepository(tmp_path);submitted=[]
    if point_scope:
        c['course_knowledge_base']['tree_schema']='knowledge_first_generic_v1'
        c['course_knowledge_base']['knowledge_points'][0]['granularity_status']='candidate'
    class Executor:
        def submit(self,**kwargs):submitted.append(kwargs)
    monkeypatch.setattr(routes,'_question_bank_course',AsyncMock(return_value=c))
    monkeypatch.setattr(routes,'_question_bank_source_material_asset_ids',lambda *_:set())
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',jobs)
    monkeypatch.setattr(routes,'question_bank_rebuild_executor',Executor())
    args={'knowledge_ids':['K'],'knowledge_baseline_revision':c['course_knowledge_base']['revision_id']}if point_scope else {'questions_per_lesson':3}
    response=await routes.rebuild_question_bank('c',routes.QuestionBankRebuildRequest(request_id='ordinary-one',scope='nodes',node_ids=['L1'],**args),x_user_id='teacher')
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
    from question_bank_knowledge import question_binding_projection
    q['lifecycle_status']='rejected'
    assert binding_view(c,{'items':[q]})['counts']['bound']==0
    assert question_binding_projection(c,{'items':[q]},[q])['Q']['knowledge_binding_status']=='bound'
    q['lifecycle_status']='needs_review'
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
    for invalid in [[],{},None]:
        r['review_witness']['observation_test']['public_anchor_ref']=invalid
        assert bind_review_anchor(r,q)['passed']is False


def test_measurement_numeric_predictions_are_losslessly_normalized():
    from assessment_measurement_design import attach_measurement_designs
    c={'assessment_slot':{'slot_id':'one'}}
    p={'target_rule':'规则','public_material':'给定数值','ask':'求上界','incorrect_rule':'漏掉阶乘',
       'trace':'代入并核对','correct_prediction':0.125,'incorrect_prediction':0.25}
    result=attach_measurement_designs([c],{'plans':[{'slot_id':'one','plan':p}]})
    assert result[0]['private_measurement_design']['correct_prediction']=='0.125'


def test_numeric_units_compare_dimensions_not_wording_and_require_finite_numbers():
    from assessment_validators import answers_equivalent
    for unit in ['无量纲','无单位','dimensionless','unitless','1','无']:
        assert answers_equivalent('numeric_unit_validator',2,{'value':2,'unit':unit}),unit
    assert not answers_equivalent('numeric_unit_validator',2,{'value':2,'unit':'m'})
    assert not answers_equivalent('numeric_unit_validator',{'value':0,'unit':'无'},{'value':0,'unit':'个'})
    assert answers_equivalent('numeric_unit_validator',{'value':1,'unit':'m'},{'value':100,'unit':'cm'})
    assert not answers_equivalent('numeric_unit_validator',{'value':float('inf')},{'value':float('inf')})


def test_numeric_disagreement_is_an_untrusted_proposal_until_full_delivery_review():
    from assessment_orchestrator import _apply_independent_validation
    from assessment_solution_protocol import attest_final_solution_review,delivery_hash
    c={'question_spec':{'task':{'rendered_text':'计算15乘8'}},'solution_envelope':{'canonical_answer':12,'validation_mode':'numeric_unit_validator'}}
    independent={'answer':{'value':120,'unit':'无'},'work':[{'title':'乘法','calculation':'15*8=120','explanation':'按给定两数相乘','result':'120'}],
                 'checks':['核对乘积'],'summary':'乘积为120','result_status':'determinate'}
    _apply_independent_validation(c,{'passed':False,'deterministic':True,'validation_mode':'numeric_unit_validator','issue_code':'numeric_or_unit_mismatch'},
                                  independent,resolve_numeric=True)
    assert c['solution_envelope']['author_answer_proposal']==12
    assert c['solution_envelope']['canonical_answer']==independent['answer']
    assert c['solution_validation']['passed']is False
    report=attest_final_solution_review(c,{'passed':False,'solution_consistent':False,'confidence':.99},delivery_hash(c))
    assert report['passed']is False and c['solution_validation']['passed']is False


def test_item_rework_keeps_the_selected_target_and_generation_identity(monkeypatch):
    from routers import question_bank as routes
    from knowledge_criterion_generation import request_plan
    from assessment_blueprint import compile_course_assessment_blueprint
    c=course();c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='first')
    slot=compile_course_assessment_blueprint(c)['nodes'][0]['slots'][0]
    class Bank:
        def load_bundle(self,*_):return {'items':[{'revision_id':'Q','assessment_slot':slot,'criterion_target':slot['criterion_target']}]}
    monkeypatch.setattr(routes,'question_bank_repository',Bank())
    p=routes.QuestionBankRebuildRequest(request_id='rework-one',scope='items',node_ids=['L1'],revision_ids=['Q'])
    frozen=routes._admit_generation_plan(c,p,'teacher')
    scoped={**c,'_criterion_generation_plan':frozen}
    after=compile_course_assessment_blueprint(scoped)['nodes'][0]['slots']
    assert len(after)==1 and after[0]['generation_key']==slot['generation_key']
    assert frozen['entrypoint']=='items'


def test_numeric_validator_configuration_has_no_second_expected_answer():
    from assessment_orchestrator import _normalize_candidate_layout
    candidate={'question_spec':{},'solution':{'validation_mode':'numeric_unit_validator','canonical_answer':120,
               'validator_config':{'expected_value':12,'tolerance':.01,'relative_tolerance':0}}}
    normalized,receipt=_normalize_candidate_layout(candidate)
    assert normalized['solution']['canonical_answer']==120
    assert normalized['solution']['validator_config']=={'absolute_tolerance':.01,'relative_tolerance':0}
    assert candidate['solution']['validator_config']['expected_value']==12
    assert receipt


def test_new_fill_prioritizes_uncovered_criteria_instead_of_repeating_first_target():
    from knowledge_criterion_generation import request_plan,seal_binding
    from assessment_blueprint import compile_course_assessment_blueprint
    from assessment_quantity import build_quantity_plan
    c=course();other=deepcopy(c['course_knowledge_base']['mastery_criteria'][0]);other.update(criterion_id='C2',revision_id='CR2')
    c['course_knowledge_base']['mastery_criteria'].append(other)
    c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='fill')
    b=compile_course_assessment_blueprint(c);target=c['_criterion_generation_plan']['targets'][0]
    q={'node_id':'L1','lifecycle_status':'needs_review','prompt':'已生成的题目','question_spec':{},'solution_revision_id':'S'}
    q['criterion_binding']=seal_binding(q,target,{'passed':True,'solution_consistent':True,'confidence':.95,'reviewer_triggered':True,
        'criterion_alignment':{'checkpoints':{'A':True,'B':True},'conditions_controlled':True,'reason':'完整覆盖'}})
    p=build_quantity_plan(c,b,previous={'items':[q]},node_ids=['L1'],count=2,append_only=False,batch_id='fill-batch')
    assert p['slots']['L1'][0]['template_index']==1


def test_ordinary_plan_accepts_a_realistic_catalog_and_rejects_incompatible_formats_before_queue():
    from knowledge_criterion_generation import request_plan,PreparationRequired
    c=course();template=c['course_knowledge_base']['mastery_criteria'][0]
    c['course_knowledge_base']['mastery_criteria']=[{**deepcopy(template),'criterion_id':f'C{i:02}','revision_id':f'CR{i:02}'}for i in range(60)]
    assert len(request_plan(c,node_ids=['L1'],request_id='catalog')['targets'])==60
    c=course();c['course_knowledge_base']['mastery_criteria'][0]['assessment_format']='numeric_response'
    with pytest.raises(PreparationRequired)as error:request_plan(c,node_ids=['L1'],request_id='bad-form')
    assert error.value.code=='criterion_format_mismatch'


@pytest.mark.parametrize('topic_only',[False,True])
def test_lecture_references_resolve_through_real_parent_links_without_rewriting_knowledge(topic_only):
    from knowledge_criterion_generation import request_plan
    c=course();c['nodes'].append({'node_id':'lecture-opaque','node_level':1,'node_name':'任意讲次'})
    c['nodes'][0]['parent_node_id']='lecture-opaque'
    point=c['course_knowledge_base']['knowledge_points'][0];point['section_refs']=['lecture-opaque'];point['topic']='lecture-opaque'
    if topic_only:point['section_refs']=[]
    c['course_knowledge_base']['mastery_criteria'][0]['section_refs']=['lecture-opaque']
    frozen=deepcopy(c['course_knowledge_base'])
    p=request_plan(c,node_ids=['L1'],request_id='real-reference-shape')
    assert p['targets'][0]['node_id']=='L1'
    assert c['course_knowledge_base']==frozen


@pytest.mark.asyncio
async def test_standard_supply_uses_the_same_lecture_reference_resolution(monkeypatch):
    from routers import question_bank as routes,practice
    from unittest.mock import AsyncMock
    c=course();c['nodes'].append({'node_id':'lecture-opaque','node_level':1,'node_name':'父讲次'})
    c['nodes'][0]['parent_node_id']='lecture-opaque';c['course_knowledge_base']['knowledge_points'][0]['section_refs']=['lecture-opaque']
    monkeypatch.setattr(routes,'_owned_binding_course',AsyncMock(return_value=c))
    monkeypatch.setattr(practice,'_questions',lambda *args,**kwargs:[])
    monkeypatch.setattr(routes,'load_active_question_bank',lambda *args,**kwargs:{'items':[]})
    class Jobs:
        def latest_for_course(self,*_):return None
        def active_for_course(self,*_):return None
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',Jobs())
    result=await routes.get_criterion_question_supply('c',knowledge_id='K',knowledge_revision='KR',criterion_id='C',criterion_revision='CR',x_user_id='teacher')
    assert result['can_generate']is True and result['node_id']=='L1'


@pytest.mark.asyncio
async def test_failed_unified_job_is_restored_after_reopening_without_starting_generation(monkeypatch,tmp_path):
    from routers import question_bank as routes
    from question_bank_jobs import QuestionBankRebuildJobRepository
    from unittest.mock import AsyncMock
    jobs=QuestionBankRebuildJobRepository(tmp_path)
    j,_=jobs.create_job('c',request_id='failed-job',scope='nodes',node_ids=['L1'],mode='incremental',actor_id='teacher')
    jobs.fail(j['job_id'],code='test_failure',message='保留具体失败原因',retryable=True)
    monkeypatch.setattr(routes,'_settle_rebuild_from_previous_worker',lambda j:j)
    monkeypatch.setattr(routes,'get_course_or_404',AsyncMock(return_value=course()))
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',jobs)
    result=await routes.get_active_question_bank_rebuild('c',x_user_id='teacher')
    assert result['job_id']==j['job_id'] and result['status']=='failed'


def test_standard_failure_resume_keeps_its_original_plan_instead_of_replanning_the_lecture(monkeypatch,tmp_path):
    from routers import question_bank as routes
    from question_bank_jobs import QuestionBankRebuildJobRepository
    c=course();jobs=QuestionBankRebuildJobRepository(tmp_path)
    monkeypatch.setattr(routes,'question_bank_rebuild_job_repository',jobs)
    original=routes.QuestionBankRebuildRequest(request_id='parent-std',scope='nodes',node_ids=['L1'],
        knowledge_ids=['K'],knowledge_baseline_revision=c['course_knowledge_base']['revision_id'],criterion_revision_refs={'C':'CR'})
    frozen=routes._admit_generation_plan(c,original,'teacher')
    parent,_=jobs.create_job('c',request_id='parent-std',scope='nodes',node_ids=['L1'],mode='incremental',actor_id='teacher',
        knowledge_ids=['K'],knowledge_baseline_revision=c['course_knowledge_base']['revision_id'],criterion_revision_refs={'C':'CR'},criterion_generation_plan=frozen)
    jobs.fail(parent['job_id'],code='test',message='未完成',retryable=True)
    retry=routes.QuestionBankRebuildRequest(request_id='child-std',scope='nodes',node_ids=['L1'],resume_job_id=parent['job_id'])
    resumed=routes._admit_generation_plan(c,retry,'teacher')
    assert resumed==frozen and resumed['entrypoint']=='standard'
    assert retry.criterion_revision_refs=={'C':'CR'}


def test_numeric_slot_has_consistent_type_semantics_and_does_not_require_a_dimensionless_unit():
    from knowledge_criterion_generation import request_plan
    from assessment_blueprint import compile_course_assessment_blueprint
    from assessment_contracts import compile_course_assessment_profile
    from question_type_semantics import semantics_for_question_type
    c=course();criterion=c['course_knowledge_base']['mastery_criteria'][0]
    criterion['assessment_format']='numeric_response';criterion['checkpoints']=criterion['checkpoints'][:1]
    c['_criterion_generation_plan']=request_plan(c,node_ids=['L1'],request_id='typed-consistent')
    profile=compile_course_assessment_profile(c);profile['notation_and_language']['requires_units']=False
    slot=compile_course_assessment_blueprint(c,profile=profile)['nodes'][0]['slots'][0]
    assert slot['question_type_semantics_id']==semantics_for_question_type('numeric_response')['registry_id']
    assert slot['response_format']=='numeric_unit'
    assert next(f for f in slot['input_contract']['fields']if f['field_id']=='unit')['required']is False
