from copy import deepcopy

import pytest
from pydantic import ValidationError

from routers.question_bank import QuestionBankRebuildRequest
from assessment_blueprint import compile_course_assessment_blueprint
from knowledge_assessment import assessment_binding, slot_keys_by_node
from question_bank_jobs import QuestionBankRebuildJobRepository


def course():
    return {'course_id':'quantity-course','course_name':'Python basics', 'nodes':[
        {'node_id':'lecture-1','node_level':1,'node_name':'第一讲'},
        {'node_id':'part-a','node_level':2,'parent_node_id':'lecture-1','node_name':'循环','learning_objective':'分析循环执行次数','node_content':'for and while loops'},
        {'node_id':'part-b','node_level':2,'parent_node_id':'lecture-1','node_name':'列表','learning_objective':'追踪列表状态','node_content':'list append and pop'},
        {'node_id':'lecture-2','node_level':1,'node_name':'第二讲'},
        {'node_id':'part-c','node_level':2,'parent_node_id':'lecture-2','node_name':'函数','learning_objective':'分析参数传递','node_content':'function arguments'},
    ]}


def test_request_keeps_quantity_and_append_and_forces_preservation():
    request=QuestionBankRebuildRequest(scope='nodes', node_ids=['part-a'], mode='full', questions_per_lesson=5, append_only=True)
    assert request.questions_per_lesson==5 and request.append_only
    assert request.mode=='incremental'


@pytest.mark.parametrize('count',[0,21,True,2.5])
def test_invalid_quantity_is_rejected(count):
    with pytest.raises(ValidationError):
        QuestionBankRebuildRequest(questions_per_lesson=count)


def test_append_requires_count_and_cannot_rebuild_an_existing_item():
    with pytest.raises(ValidationError):
        QuestionBankRebuildRequest(append_only=True)
    with pytest.raises(ValidationError):
        QuestionBankRebuildRequest(scope='items',revision_ids=['revision'],questions_per_lesson=2,append_only=True)


def test_quantity_is_per_lecture_and_keys_are_independent_of_old_slots():
    from assessment_quantity import build_quantity_plan
    c=course(); original=deepcopy(c)
    blueprint=compile_course_assessment_blueprint(c)
    plan=build_quantity_plan(c,blueprint,previous=None,node_ids=['part-a','part-b','part-c'],count=5,append_only=True,batch_id='batch-1')
    c['_assessment_quantity_plan']=plan
    expanded=compile_course_assessment_blueprint(c)
    keys=slot_keys_by_node(expanded)
    assert len(keys['part-a'])+len(keys['part-b'])==5
    assert len(keys['part-c'])==5
    assert len(set(k for v in keys.values() for k in v))==10
    assert not set(keys['part-a']) & {'concept_check','objective_practice','mastery_check'}
    assert original==course()
    for node in expanded['nodes']:
        for slot in node['slots']:
            assert assessment_binding(slot)['generation_key']==slot['generation_key']
    other=build_quantity_plan(original,blueprint,previous=None,node_ids=['part-a','part-b','part-c'],count=5,append_only=True,batch_id='batch-2')
    assert set(plan['slots']['part-a'][i]['generation_key'] for i in range(3)).isdisjoint(s['generation_key'] for s in other['slots']['part-a'])


def test_fill_counts_existing_questions_across_all_parts_of_a_lecture():
    from assessment_quantity import build_quantity_plan
    c=course(); bp=compile_course_assessment_blueprint(c)
    previous={'items':[{'node_id':'part-a','lifecycle_status':'approved'},{'node_id':'part-b','lifecycle_status':'needs_review'}]}
    plan=build_quantity_plan(c,bp,previous=previous,node_ids=['part-a','part-b'],count=5,append_only=False,batch_id='fill')
    assert sum(len(v) for v in plan['slots'].values())==3
    assert not plan['slots'].get('part-c')


def test_adopted_reference_tree_with_candidate_points_keeps_lecture_generation_targets():
    c=course()
    c['course_knowledge_base']={'tree_schema':'knowledge_first_generic_v1','status':'accepted','revision_id':'kb-ref',
        'knowledge_points':[{'knowledge_id':'candidate','granularity_status':'candidate','section_refs':['lecture-1'],
                             'statement':'循环会重复执行代码','meta_question':'循环何时终止？','source_refs':['handout-1']}]}
    before=deepcopy(c['course_knowledge_base'])
    blueprint=compile_course_assessment_blueprint(c)
    assert len(blueprint['nodes'][0]['slots'])==3
    assert c['course_knowledge_base']==before


def test_no_planned_targets_cannot_report_success_for_append():
    from assessment_quantity import build_quantity_plan
    with pytest.raises(ValueError,match='targets_unavailable'):
        build_quantity_plan(course(),{'nodes':[{'node_id':'part-a','slots':[]}]},previous=None,
                            node_ids=['part-a'],count=2,append_only=True,batch_id='empty')


def test_job_count_and_operation_are_frozen_and_change_idempotency(tmp_path):
    repo=QuestionBankRebuildJobRepository(tmp_path)
    args=dict(course_id='c',request_id='same-id',scope='course',node_ids=[],mode='incremental',actor_id='teacher')
    first,_=repo.create_job(**args,questions_per_lesson=2,append_only=True)
    same,created=repo.create_job(**args,questions_per_lesson=2,append_only=True)
    second,_=repo.create_job(**args,questions_per_lesson=3,append_only=True)
    assert not created and same['job_id']==first['job_id']
    assert second['job_id']!=first['job_id']
    assert first['questions_per_lesson']==2 and first['append_only']
    assert repo.freeze_quantity_plan(first['job_id'],{'slots':{'a':[]}})=={'slots':{'a':[]}}
    assert repo.freeze_quantity_plan(first['job_id'],{'slots':{'b':[]}})=={'slots':{'a':[]}}
