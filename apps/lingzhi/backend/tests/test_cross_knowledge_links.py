from knowledge_relations import relation_index
import pytest
from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts, answer
from backend.tests.test_lesson_knowledge import one_lesson_response
from handout_knowledge import handout_context, merge_lesson_tree
from generic_knowledge import compile_tree, tree_prompt
from course_repository import CourseDocumentConflict


def test_non_reusable_new_point_still_links_to_old_rule_and_materializes_both_pointers(svc):
    from copy import deepcopy
    handouts(svc);raw=svc.repository.load_raw('c-pilot');state=svc.authoring.load('c-pilot')
    raw['course_knowledge_base']=compile_tree(raw,handout_context(raw,state),answer())
    context=handout_context(raw,state,'memory')
    response=one_lesson_response('memory');response['relations']=[]
    response['cross_alignment']=[{'knowledge_key':'K2','reason':'这是新命题，不能复用旧点',
        'relation_reason':'虽然不可复用，但主存数据供处理器使用，存在应用关系',
        'links':[{'other_key':'E1','direction':'incoming','type':'applies_to','reason':'处理器读取主存中的数据','conditions':['指令执行']}]}]
    before=deepcopy(response)
    result=merge_lesson_tree(raw['course_knowledge_base'],compile_tree(raw,context,response),'memory')
    assert len(result['relations'])==1
    edge=result['relations'][0]
    assert edge['cross_lesson'] is True
    assert result['relation_index'][edge['source_id']]['outgoing']==[edge['id']]
    assert result['relation_index'][edge['target_id']]['incoming']==[edge['id']]
    assert response==before


def test_no_reuse_explanation_cannot_substitute_for_relation_assessment(svc):
    handouts(svc);raw=svc.repository.load_raw('c-pilot');state=svc.authoring.load('c-pilot')
    context=handout_context(raw,state,'memory')
    response=one_lesson_response('memory')
    response['cross_alignment']=[{'knowledge_key':'K2','reason':'无复用'}]
    with pytest.raises(CourseDocumentConflict,match='关系'):
        compile_tree(raw,context,response)


def test_same_relation_reported_from_both_ends_is_one_edge(svc):
    handouts(svc);raw=svc.repository.load_raw('c-pilot');state=svc.authoring.load('c-pilot')
    context=handout_context(raw,state)
    context['cross_lesson_alignment_contract']='per_point_relations_v3'
    response=answer();response['relations']=[]
    response['cross_alignment']=[{'knowledge_key':key,'reason':'独立命题','relation_reason':'处理器读取主存数据',
        'links':[{'other_key':other,'direction':direction,'type':'applies_to','reason':'处理器读取主存数据','conditions':[]}]}
        for key,other,direction in [('K1','K2','outgoing'),('K2','K1','incoming')]]
    result=compile_tree(raw,context,response)
    assert len(result['relations'])==1
    edge=result['relations'][0]
    assert result['relation_index'][edge['source_id']]['outgoing']==[edge['id']]
    assert result['relation_index'][edge['target_id']]['incoming']==[edge['id']]
    response['cross_alignment'][1]['links'][0]['conditions']=['另一适用范围']
    variant=compile_tree(raw,context,response)
    assert len(variant['relations'])==2  # Different conditions are distinct claims.


def test_directed_relation_has_two_lookup_pointers_without_reversing_its_meaning():
    tree = {'knowledge_points': [{'knowledge_id': 'old'}, {'knowledge_id': 'new'}],
            'relations': [{'id': 'edge', 'source_id': 'old', 'target_id': 'new', 'type': 'prerequisite'}]}
    assert relation_index(tree) == {'old': {'incoming': [], 'outgoing': ['edge']},
                                   'new': {'incoming': ['edge'], 'outgoing': []}}
    tree['knowledge_points'] = [{'knowledge_id': 'old'}]
    assert relation_index(tree) == {'old': {'incoming': [], 'outgoing': []}}


def test_every_new_point_requires_alignment_and_merging_updates_the_old_end(svc):
    handouts(svc)
    raw = svc.repository.load_raw('c-pilot'); state = svc.authoring.load('c-pilot')
    old = compile_tree(raw, handout_context(raw, state), answer())
    raw['course_knowledge_base'] = old
    context = handout_context(raw, state, 'memory')
    assert len(context['reference_knowledge']) == 1
    assert {l['lesson_id'] for l in context['reference_lessons']} == {'cpu'}
    assert '全课程跨讲对齐' in tree_prompt(raw, context)
    response = one_lesson_response('memory')
    response.pop('cross_alignment')
    with pytest.raises(CourseDocumentConflict, match='知识关系'):
        compile_tree(raw, context, response)
    response['cross_alignment'] = [{'knowledge_key': 'K2', 'reason': '独立命题', 'relation_reason': '对比已有处理器与主存知识，处理器使用主存数据', 'links': []}]
    response['relations'] = [{'source_key': 'E1', 'target_key': 'K2', 'type': 'applies_to', 'reason': '读取主存数据', 'conditions': []}]
    result = merge_lesson_tree(old, compile_tree(raw, context, response), 'memory')
    edge = result['relations'][0]
    assert result['relation_index'][edge['source_id']]['outgoing'] == [edge['id']]
    assert result['relation_index'][edge['target_id']]['incoming'] == [edge['id']]
    before = next(p for p in old['knowledge_points'] if p['knowledge_id'] == edge['source_id'])
    assert next(p for p in result['knowledge_points'] if p['knowledge_id'] == edge['source_id']) == before
    response['relations'] = []
    replacement = merge_lesson_tree(result, compile_tree(raw, context, response), 'memory')
    assert replacement['relation_index'][edge['source_id']]['outgoing'] == []
    assert replacement['relation_index'][edge['target_id']]['incoming'] == []
    assert result['relation_index'][edge['source_id']]['outgoing'] == [edge['id']]  # Historical result remains intact.


def test_regeneration_excludes_its_old_points_categories_and_edges_from_model_input(svc):
    from generic_knowledge import tree_model_prompt
    from copy import deepcopy
    handouts(svc)
    raw=svc.repository.load_raw('c-pilot'); state=svc.authoring.load('c-pilot')
    old=compile_tree(raw,handout_context(raw,state),answer())
    own=next(p for p in old['knowledge_points'] if p['section_refs']==['cpu'])
    own.update(name='本讲旧点不应参考',statement='旧版错误命题不可进入模型',meta_answer='旧版答案不可进入模型')
    old['categories'].append({'id':'old-only','name':'本讲旧分类不可进入模型','parent_id':None})
    own['parent_id']='old-only'
    old['relations']=[{'source_id':own['knowledge_id'],'target_id':old['knowledge_points'][1]['knowledge_id'],'type':'applies_to','reason':'本讲旧关系不可进入模型'}]
    raw['course_knowledge_base']=old;before=deepcopy(raw)
    context=handout_context(raw,state,'cpu');prompt=tree_model_prompt(raw,context)
    for marker in ['本讲旧点不应参考','旧版错误命题不可进入模型','旧版答案不可进入模型','本讲旧分类不可进入模型','本讲旧关系不可进入模型']:
        assert marker not in prompt
    assert 'CPU执行指令。' in prompt  # Current saved handout is still the source.
    assert '主存保存正在使用的数据。' in prompt  # Other lecture knowledge remains available.
    assert context['reference_relations']==[]
    assert raw==before
