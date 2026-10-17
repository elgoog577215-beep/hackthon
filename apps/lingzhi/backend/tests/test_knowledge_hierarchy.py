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


@pytest.mark.parametrize('change', ['unknown', 'missing', 'empty', 'same_name'])
def test_partition_requires_strictly_smaller_meaningful_subsets(change):
    from knowledge_hierarchy import compile_partition
    task = {'name': '栈', 'path': ['栈']}
    value = {'response_contract': 'knowledge_partition_v1', 'groups': [{'key': 'G1', 'name': '插入', 'scope': '插入操作'}],
             'point_groups': {'K1': 'G1', 'K2': '__direct__'}, 'stop_reason': '插入单独归组'}
    if change == 'unknown': value['point_groups']['K1'] = 'unknown'
    if change == 'missing': value['point_groups'].pop('K2')
    if change == 'empty': value['point_groups']['K1'] = '__direct__'
    if change == 'same_name': value['groups'][0]['name'] = '栈'
    with pytest.raises(CourseDocumentConflict): compile_partition(value, task, ['K1', 'K2'])


def test_single_child_is_promoted_without_inventing_another_layer_or_losing_points():
    from knowledge_hierarchy import compile_partition
    response = {'response_contract': 'knowledge_partition_v1',
        'groups': [{'key': 'G1', 'name': '访问规则', 'scope': '同一组访问规则'}],
        'point_groups': {'K1': 'G1', 'K2': 'G1'}, 'stop_reason': '同一具体范围'}
    result = compile_partition(response, {'path': ['访问机制']}, ['K1', 'K2'])
    assert result['groups'] == [] and result['direct_keys'] == ['K1', 'K2']
    assert result['normalizations'] == ['single_child_promoted']


@pytest.mark.asyncio
async def test_sibling_branches_are_partitioned_concurrently(monkeypatch):
    import asyncio
    import json
    from knowledge_hierarchy import organize

    points = [{'key': f'K{i}', 'name': f'点{i}', 'statement': f'冻结命题{i}'} for i in range(1, 5)]
    pipeline = {}
    active = 0
    peak = 0

    async def request(svc, cid, jid, provider, prompt, stage):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        active -= 1
        keys = [p['key'] for p in payload['points']]
        if payload['is_root']:
            return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [
                {'key': 'G1', 'name': '机制', 'scope': '机制'}, {'key': 'G2', 'name': '应用', 'scope': '应用'}],
                'point_groups': {key: 'G1' if key in {'K1', 'K2'} else 'G2' for key in keys},
                'stop_reason': '机制与应用分离'})
        return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [],
            'point_groups': {key: '__direct__' for key in keys}, 'stop_reason': '同一范围内直接并列'})

    monkeypatch.setattr('knowledge_atomic.call_stage', request)
    args = (None, 'c', 'j', None, {'course_id': 'c'},
            {'scope_lesson_id': 'l', 'handout_lessons': [{'title': '课题'}]}, pipeline, points)
    await organize(*args, lambda **extra: None, lambda: None)
    assert peak >= 2


@pytest.mark.asyncio
async def test_recursive_partition_keeps_completed_branches_on_resume(monkeypatch):
    import json
    from knowledge_hierarchy import organize, CONTRACT
    points = [{'key': f'K{i}', 'name': f'点{i}', 'statement': f'冻结命题{i}'} for i in range(1, 5)]
    pipeline = {}; saved = []; calls = []
    async def request(svc, cid, jid, provider, prompt, stage):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data)
        keys = [p['key'] for p in data['points']]
        if len(calls) == 2: raise TimeoutError('interrupted branch')
        if data['is_root']:
            return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [
                {'key': 'G1', 'name': '机制', 'scope': '定义与执行机制'}, {'key': 'G2', 'name': '复杂度', 'scope': '算法复杂度'}],
                'point_groups': {k: 'G1' if k != 'K4' else 'G2' for k in keys}, 'stop_reason': '机制和复杂度分离'})
        if len(keys) == 3:
            return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [
                {'key': 'G1', 'name': '执行过程', 'scope': '执行过程的操作'}],
                'point_groups': {k: '__direct__' if k == 'K1' else 'G1' for k in keys}, 'stop_reason': '定义直接归属，操作继续分组'})
        return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [],
            'point_groups': {k: '__direct__' for k in keys}, 'stop_reason': '同一执行过程的原子规则，适合直接并列'})
    monkeypatch.setattr('knowledge_atomic.call_stage', request)
    args = (None, 'c', 'j', None, {'course_id': 'c'}, {'scope_lesson_id': 'l', 'handout_lessons': [{'title': '课题'}]}, pipeline, points)
    def save(**extra): saved.append(deepcopy(pipeline))
    with pytest.raises(TimeoutError): await organize(*args, save, lambda: None)
    completed_root = deepcopy(pipeline['hierarchy']['tasks'][0])
    result = await organize(*args, save, lambda: None)
    assert sum(call['is_root'] for call in calls) == 1
    assert pipeline['hierarchy']['tasks'][0] == completed_root
    assert pipeline['hierarchy']['status'] == 'completed' and result['schema_version'] == CONTRACT
    parents = {a['point_key']: a['category_key'] for a in result['assignments']}
    assert parents['K1'] != parents['K2'] and parents['K2'] == parents['K3']
    assert len(parents) == 4 and saved
