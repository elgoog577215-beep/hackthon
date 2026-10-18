from copy import deepcopy

import pytest

from course_repository import CourseDocumentConflict
from knowledge_tree_relations import compile_relations


def pipeline():
    return {'contract': 'knowledge_tree_relations_v3', 'focus_keys': ['P1', 'P2', 'P3'],
        'base_revision': 'frozen', 'baseline_relations': [], 'existing_relations': [],
        'catalog': [
            {'key': 'P1', 'knowledge_id': 'stack', 'revision_id': 's', 'name': '栈的规则', 'statement': '栈遵循后进先出规则。', 'subjects': ['栈'], 'conditions': [], 'lesson_ids': ['l']},
            {'key': 'P2', 'knowledge_id': 'dfs', 'revision_id': 'd', 'name': 'DFS的实现', 'statement': 'DFS使用栈维护待访问节点。', 'subjects': ['DFS'], 'conditions': [], 'lesson_ids': ['l']},
            {'key': 'P3', 'knowledge_id': 'sort', 'revision_id': 'm', 'name': '归并排序', 'statement': '归并排序递归划分并合并有序序列。', 'subjects': ['归并排序'], 'conditions': [], 'lesson_ids': ['l']}]}


def response():
    return {'point_reviews': {'P1': '栈直接用于DFS实现。'}, 'focus_links': {'P1': [
        {'p': 'P2', 'd': 'out', 't': 'applies_to', 'c': '待访问节点管理', 'r': '栈的后进先出用于DFS管理待访问节点。', 'if': [], 'w': 'medium',
         'sn': '栈的规则', 'tn': 'DFS的实现', 'sq': '栈遵循后进先出规则', 'tq': 'DFS使用栈维护待访问节点'}]}, 'gaps': []}


def test_relation_keeps_exact_endpoint_names_and_selected_evidence():
    result = compile_relations({'course_id': 'c'}, pipeline(), ['P1'], response(), 'l')
    assert len(result['relations']) == 1 and not result['semantic_rejections']
    assert [r['quote'] for r in result['relations'][0]['evidence_refs']] == ['栈遵循后进先出规则', 'DFS使用栈维护待访问节点']
    assert result['relations'][0]['evidence_origin'] == 'model_selected_validated_statement_quotes'


@pytest.mark.parametrize('field,value', [('sn', '归并排序'), ('sq', '不存在的原文'), ('tq', '归并排序递归划分')])
def test_wrong_endpoint_or_forged_quotation_is_rejected(field, value):
    value_response = response(); value_response['focus_links']['P1'][0][field] = value
    result = compile_relations({'course_id': 'c'}, pipeline(), ['P1'], value_response, 'l')
    assert result['relations'] == []
    assert result['semantic_rejections'][0]['code'] in {'endpoint_name_mismatch', 'endpoint_quote_mismatch'}
    assert result['semantic_rejections'][0]['link'] == value_response['focus_links']['P1'][0]


def test_unrelated_cross_lesson_edge_is_retained_as_rejected_evidence_not_a_graph_edge():
    value = response(); link = value['focus_links']['P1'][0]
    link.update(p='P3', tn='归并排序', tq='归并排序递归划分并合并有序序列', r='同属算法所以应当先学栈。')
    result = compile_relations({'course_id': 'c'}, pipeline(), ['P1'], value, 'l')
    assert result['relations'] == []
    assert result['semantic_rejections'][0]['code'] == 'missing_direct_reference'
    assert result['semantic_rejections'][0]['link'] == link


def test_reusing_one_generic_reason_for_distinct_pairs_cannot_fill_the_graph():
    value = response(); first = value['focus_links']['P1'][0]
    first['r'] = '分治递归是典型复杂用例'
    other = {**deepcopy(first), 'p': 'P3', 'tn': '归并排序', 'tq': '归并排序递归划分并合并有序序列'}
    value['focus_links']['P1'].append(other)
    p = pipeline(); p['catalog'][2]['statement'] = '归并排序借助栈实现递归划分并合并有序序列。'
    other['tq'] = p['catalog'][2]['statement']
    result = compile_relations({'course_id': 'c'}, p, ['P1'], value, 'l')
    assert result['relations'] == []
    assert [r['code'] for r in result['semantic_rejections']] == ['reused_pair_reason', 'reused_pair_reason']
