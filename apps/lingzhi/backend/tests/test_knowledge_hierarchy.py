from copy import deepcopy

import pytest

from course_repository import CourseDocumentConflict


def leaves():
    return [{'key': 'K1', 'name': '入栈', 'statement': '插入栈顶', 'revision_id': 'r1', 'source_quotes': [{'quote': '原文'}]},
            {'key': 'K2', 'name': '出栈', 'statement': '移除栈顶', 'revision_id': 'r2'}]


def hierarchy():
    return {'categories': [{'key': 'C1', 'name': '栈', 'parent_key': None},
                           {'key': 'C2', 'name': '基本操作', 'parent_key': 'C1'}],
            'assignments': [{'point_key': 'K1', 'category_key': 'C2'}, {'point_key': 'K2', 'category_key': 'C2'}]}


def test_whole_lesson_hierarchy_changes_only_classification():
    from knowledge_hierarchy import compile_hierarchy, apply_hierarchy
    points = leaves(); before = deepcopy(points)
    compiled = compile_hierarchy(hierarchy(), points, 'course', 'lesson')
    categories, organized = apply_hierarchy(compiled, points)
    assert len(categories) == 2 and categories[1]['parent_id'] == categories[0]['id']
    assert organized[0]['parent_id'] == organized[1]['parent_id'] == categories[1]['id']
    assert points == before
    for point, original in zip(organized, before):
        assert {k: v for k, v in point.items() if k not in {'parent_id', 'primary_concept_group_id'}} == original


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'cycle', 'empty', 'rewrite'])
def test_invalid_hierarchy_cannot_drop_duplicate_or_rewrite_frozen_points(change):
    from knowledge_hierarchy import compile_hierarchy
    value = hierarchy()
    if change == 'missing': value['assignments'].pop()
    if change == 'duplicate': value['assignments'].append(value['assignments'][0])
    if change == 'unknown': value['assignments'][0]['category_key'] = 'absent'
    if change == 'cycle': value['categories'][0]['parent_key'] = 'C2'
    if change == 'empty': value['categories'].append({'key': 'C3', 'name': '空分支', 'parent_key': None})
    if change == 'rewrite': value['assignments'][0]['statement'] = '模型改写'
    with pytest.raises(CourseDocumentConflict): compile_hierarchy(value, leaves(), 'course', 'lesson')


def test_independent_branches_can_have_different_depths_beyond_six_levels():
    from knowledge_hierarchy import compile_hierarchy, apply_hierarchy
    points = leaves()
    categories = [{'key': f'C{i}', 'name': f'范围{i}', 'parent_key': f'C{i-1}' if i else None} for i in range(9)]
    value = {'categories': categories, 'assignments': [
        {'point_key': 'K1', 'category_key': 'C1'}, {'point_key': 'K2', 'category_key': 'C8'}]}
    compiled = compile_hierarchy(value, points, 'course', 'lesson')
    result, organized = apply_hierarchy(compiled, points)
    by_id = {c['id']: c for c in result}
    assert [by_id[p['parent_id']]['depth'] for p in organized] == [1, 8]
    assert result[-1]['path_names'] == [f'范围{i}' for i in range(9)]


def test_adaptive_contract_requires_scope_and_all_frozen_points_without_rewriting():
    from knowledge_hierarchy import compile_hierarchy, hierarchy_schema, CONTRACT
    value = hierarchy()
    value.update(response_contract=CONTRACT, point_categories={'K1': 'C2', 'K2': 'C2'})
    value.pop('assignments')
    for c in value['categories']: c['scope'] = '描述本分支组织的知识范围'
    compiled = compile_hierarchy(value, leaves(), 'course', 'lesson')
    assert compiled['schema_version'] == CONTRACT
    assert compiled['categories'][1]['scope'] == '描述本分支组织的知识范围'
    schema = hierarchy_schema(['K1', 'K2'])
    assert schema['properties']['point_categories']['required'] == ['K1', 'K2']
    assert 'scope' in schema['properties']['categories']['items']['required']
    value['categories'][1]['scope'] = ''
    with pytest.raises(CourseDocumentConflict): compile_hierarchy(value, leaves(), 'course', 'lesson')


def test_same_name_ancestor_cannot_create_fake_depth():
    from knowledge_hierarchy import compile_hierarchy
    value = hierarchy(); value['categories'][1]['name'] = value['categories'][0]['name']
    with pytest.raises(CourseDocumentConflict, match='同名'):
        compile_hierarchy(value, leaves(), 'course', 'lesson')
