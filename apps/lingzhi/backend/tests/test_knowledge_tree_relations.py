import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_extract import response
from course_repository import CourseDocumentConflict


def relation_response(data):
    a, b = data['focus_keys'][:2]
    if data.get('relation_contract') == 'knowledge_tree_relations_v3':
        source, target = data['catalog'][a], data['catalog'][b]
        return {'point_reviews': {key: '已核对两端对象和直接引用。' for key in data['focus_keys']},
            'focus_links': {key: ([{'p': b, 'd': 'out', 't': 'prerequisite', 'n': 'recommended',
                'c': '理解后续操作', 'r': f"{target['name']}明确引用{source['name']}。", 'if': [], 'w': 'medium',
                'sn': source['name'], 'tn': target['name'], 'sq': source['claim'], 'tq': target['claim']}] if key == a else [])
                for key in data['focus_keys']}, 'gaps': []}
    return {'point_reviews': {key: '已比较全目录，按命题判断直接教学依赖。' for key in data['focus_keys']},
        'focus_links': {key: ([{'other_key': b, 'direction': 'outgoing', 'type': 'prerequisite',
                   'necessity': 'recommended', 'context': '比较栈顶操作', 'reason': '先理解元素如何加入栈顶，再比较移除规则。',
                   'conditions': [], 'strength': 'medium', 'derivation_steps': []}] if key == a else [])
            for key in data['focus_keys']}, 'gaps': []}


def fake_provider(svc, *, relation_fails=False):
    calls = []; started = asyncio.Event()
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); stage = data['stage']
        if stage == 'extract':
            value = response()
            value['points'][1]['claim'] = '出栈从入栈后的栈中移除并返回栈顶元素。'
        elif stage == 'tree_relations':
            started.set()
            if relation_fails: raise TimeoutError('isolated relationship failure')
            value = relation_response(data)
            assert set(value) == {'point_reviews', 'focus_links', 'gaps'}
        else:
            # Relation generation must start while classification is in flight.
            await asyncio.wait_for(started.wait(), timeout=1)
            value = {'response_contract': 'knowledge_partition_v1', 'groups': [],
                     'point_groups': {p['key']: '__direct__' for p in data['points']}, 'stop_reason': '两个栈操作自然并列'}
        calls.append((stage, value))
        return json.dumps(value, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test-qwen', client=None)
    return calls


@pytest.mark.asyncio
async def test_one_generation_includes_relations_without_prior_adoption_and_adopts_once(svc, monkeypatch):
    setup_course(svc, monkeypatch); before = deepcopy(svc.repository.load_raw('c-pilot'))
    calls = fake_provider(svc)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    await svc.run('c-pilot', job['id']); saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', (saved.get('error'), calls, saved.get('raw_response'))
    candidate = saved['checkpoint']['candidate']
    assert {stage for stage, _ in calls} == {'extract', 'hierarchy_partition', 'tree_relations'}
    assert len(candidate['relations']) == 1
    assert candidate['atomic_assessment']['relation_status'] == 'completed'
    assert candidate['relation_assessment']['mode'] == 'with_tree'
    assert svc.repository.load_raw('c-pilot') == before
    with pytest.raises(CourseDocumentConflict):
        svc.adopt('c-pilot', job['id'], '', before['course_document_revision'])
    svc.adopt('c-pilot', job['id'], '', before['course_document_revision'], confirm_relations=True)
    current = svc.repository.load_raw('c-pilot')['course_knowledge_base']
    assert current['status'] == 'accepted' and current['relations'][0]['review_status'] == 'accepted'
    assert len(current['knowledge_points']) == 2


@pytest.mark.asyncio
async def test_relation_failure_retains_points_and_hierarchy_and_resume_calls_only_relations(svc, monkeypatch):
    setup_course(svc, monkeypatch); fake_provider(svc, relation_fails=True)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    await svc.run('c-pilot', job['id']); original = svc.authoring.get_job('c-pilot', job['id'])
    assert original['status'] == 'failed'
    assert original['checkpoint']['atomic_pipeline']['hierarchy']['status'] == 'completed'
    calls = fake_provider(svc)
    resumed = start(svc, 'continue-relations', resume_job_id=job['id'])
    assert resumed['include_relations']
    await svc.run('c-pilot', resumed['id'])
    assert svc.authoring.get_job('c-pilot', resumed['id'])['status'] == 'completed'
    assert [stage for stage, _ in calls] == ['tree_relations']
    assert svc.authoring.get_job('c-pilot', job['id']) == original


@pytest.mark.parametrize('change', ['unknown', 'missing_review', 'rewrite', 'steps'])
def test_compact_relations_keep_existing_graph_guards(change):
    from knowledge_tree_relations import compile_relations
    points = [{'key': 'P1', 'knowledge_id': 'a', 'revision_id': 'r1', 'name': 'A', 'statement': '冻结命题甲', 'conditions': [], 'lesson_ids': ['l']},
              {'key': 'P2', 'knowledge_id': 'b', 'revision_id': 'r2', 'name': 'B', 'statement': '冻结命题乙', 'conditions': [], 'lesson_ids': ['l']}]
    pipeline = {'catalog': points, 'base_revision': 'frozen', 'baseline_relations': []}
    value = relation_response({'focus_keys': ['P1', 'P2']})
    if change == 'unknown': value['focus_links']['P1'][0]['other_key'] = 'foreign'
    if change == 'missing_review': value['point_reviews'].pop('P2')
    if change == 'rewrite': value['knowledge_points'] = []
    if change == 'steps': value['focus_links']['P1'][0]['type'] = 'derives'
    with pytest.raises(CourseDocumentConflict): compile_relations({'course_id': 'c'}, pipeline, ['P1', 'P2'], value, 'l')


def test_relation_links_are_nested_under_their_focus_to_prevent_cross_batch_edges():
    from knowledge_tree_relations import compile_relations
    points = [{'key': f'P{i}', 'knowledge_id': chr(96+i), 'revision_id': f'r{i}', 'name': f'知识{i}',
               'statement': f'冻结命题{i}', 'conditions': [], 'lesson_ids': ['l']} for i in range(1, 4)]
    pipeline = {'catalog': points, 'base_revision': 'frozen', 'baseline_relations': []}
    value = relation_response({'focus_keys': ['P1', 'P2']})
    value['focus_links']['P1'][0]['source_key'] = 'P2'
    value['focus_links']['P1'][0]['target_key'] = 'P3'
    with pytest.raises(CourseDocumentConflict, match='当前焦点'):
        compile_relations({'course_id': 'c'}, pipeline, ['P1', 'P2'], value, 'l')


def test_relation_assembly_keeps_acyclic_edges_and_reports_cycle_conflicts():
    from knowledge_tree_relations import retain_acyclic_relations
    points = [{'key': f'P{i}', 'knowledge_id': f'k{i}'} for i in range(1, 4)]
    first = {'id': 'r1', 'source_id': 'k1', 'target_id': 'k2', 'type': 'prerequisite'}
    second = {'id': 'r2', 'source_id': 'k2', 'target_id': 'k1', 'type': 'prerequisite'}
    application = {'id': 'r3', 'source_id': 'k2', 'target_id': 'k3', 'type': 'applies_to'}
    kept, gaps = retain_acyclic_relations(points, [], [first, second, application])
    assert [edge['id'] for edge in kept] == ['r1', 'r3']
    assert len(gaps) == 1 and '环' in gaps[0] and 'r2' in gaps[0]


@pytest.mark.asyncio
async def test_relation_shards_run_together_and_resume_only_failed_shard(monkeypatch):
    from knowledge_tree_relations import generate
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_RELATION_BATCH_SIZE', '2')
    points = [{'knowledge_id': f'k{i}', 'revision_id': f'r{i}', 'name': f'知识{i}', 'statement': f'知识{i}建立在知识{i-1}的基础上。',
               'conditions': [], 'section_refs': ['l']} for i in range(4)]
    tree = {'knowledge_points': points, 'relations': [], 'revision_id': 'frozen'}
    pipeline = {}; failed = True; calls = []; entered = asyncio.Event()
    async def call(svc, cid, jid, provider, prompt, stage):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data['focus_keys'])
        if data['focus_keys'][0] == 'P1':
            await asyncio.wait_for(entered.wait(), timeout=1)
        else:
            entered.set()
            if failed: raise TimeoutError('isolated shard failure')
        return json.dumps(relation_response(data), ensure_ascii=False)
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    args = (None, 'c', 'j', None, {'course_id': 'c'}, {'scope_lesson_id': 'l'}, pipeline, tree, lambda **kw: None, lambda: None)
    with pytest.raises(TimeoutError): await generate(*args)
    assert pipeline['relations']['batches'][0]['status'] == 'completed'
    failed = False; calls.clear()
    result = await generate(*args)
    assert calls == [['P3', 'P4']]
    assert len(result['relations']) == 2 and len(result['decisions']) == 4


def compact_pipeline():
    return {'catalog': [{'key': f'P{i}', 'knowledge_id': f'k{i}', 'revision_id': f'r{i}',
        'name': f'知识{i}', 'statement': f'冻结完整命题{i}', 'conditions': ['完整条件'],
        'lesson_ids': ['other' if i == 1 else 'l']} for i in range(1, 5)],
        'focus_keys': ['P2', 'P3', 'P4'], 'existing_relations': [], 'baseline_relations': [], 'base_revision': 'frozen'}


@pytest.mark.asyncio
async def test_default_relation_batches_use_eight_points_and_resume_frozen_batches(monkeypatch):
    from knowledge_tree_relations import generate
    monkeypatch.delenv('COURSE_KNOWLEDGE_TREE_RELATION_BATCH_SIZE', raising=False)
    points = [{'knowledge_id': f'k{i}', 'revision_id': f'r{i}', 'name': f'知识{i}',
               'statement': f'冻结命题{i}', 'conditions': [], 'section_refs': ['l']} for i in range(17)]
    tree = {'knowledge_points': points, 'relations': [], 'revision_id': 'frozen'}
    pipeline = {}; calls = []
    async def call(svc, cid, jid, provider, prompt, stage):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data['focus_keys'])
        return json.dumps({'point_reviews': {k: '无直接关系' for k in data['focus_keys']},
                           'focus_links': {k: [] for k in data['focus_keys']}, 'gaps': []}, ensure_ascii=False)
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    args = (None, 'c', 'j', None, {'course_id': 'c'}, {'scope_lesson_id': 'l'}, pipeline, tree, lambda **kw: None, lambda: None)
    await generate(*args)
    assert sorted(map(len, calls)) == [1, 8, 8]
    frozen = deepcopy(pipeline)
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_RELATION_BATCH_SIZE', '2')
    calls.clear(); await generate(*args)
    assert calls == [] and pipeline == frozen


def test_compact_prompt_retains_full_cross_lesson_catalog_without_duplicate_fields():
    from knowledge_tree_relations import prompt_for
    pipeline = compact_pipeline()
    data = json.loads(prompt_for({'course_name': '课'}, pipeline, ['P2'], 'l').split('\nINPUT_JSON:\n')[1])
    assert data['local_keys'] == ['P2', 'P3', 'P4']
    assert data['catalog'] == {p['key']: [p['name'], p['statement'], p['conditions'], p['lesson_ids']] for p in pipeline['catalog']}
    assert data['catalog']['P1'][-1] == ['other']


def test_compact_schema_assigns_every_local_pair_once_and_keeps_cross_lesson_pairs():
    from knowledge_tree_relations import response_schema, owned_targets
    from jsonschema import Draft202012Validator
    keys, local = ['P1', 'P2', 'P3', 'P4'], ['P2', 'P3', 'P4']
    pairs = [(focus, target) for focus in local for target in owned_targets(keys, local, focus)]
    assert len(pairs) == 6 and len({frozenset(pair) for pair in pairs}) == 6
    assert all((focus, 'P1') in pairs for focus in local)
    schema = response_schema(keys, ['P3'], local)
    Draft202012Validator.check_schema(schema)
    edge = {'p': 'P4', 'd': 'in', 't': 'derives', 'c': '场景', 'r': '依据', 'if': [], 'w': 'medium', 's': ['第一步', '第二步']}
    value = {'point_reviews': {'P3': '已比较'}, 'focus_links': {'P3': [edge]}, 'gaps': []}
    validator = Draft202012Validator(schema)
    assert validator.is_valid(value)
    edge['p'] = 'P2'
    assert not validator.is_valid(value)
    edge['p'] = 'P3'
    assert not validator.is_valid(value)
    edge['p'] = 'P1'; edge['s'] = ['只有一步']
    assert not validator.is_valid(value)


def test_compact_relations_expand_direction_conditions_and_derivation_without_losing_evidence():
    from knowledge_tree_relations import compile_relations
    pipeline = compact_pipeline()
    value = {'point_reviews': {'P2': '已比较跨讲及本讲目录'}, 'focus_links': {'P2': [
        {'p': 'P1', 'd': 'in', 't': 'derives', 'c': '公式推导', 'r': '前提推出结论',
         'if': ['额外条件'], 'w': 'strong', 's': ['代入定义', '求出极限']}]}, 'gaps': []}
    result = compile_relations({'course_id': 'c'}, pipeline, ['P2'], value, 'l')
    edge = result['relations'][0]
    assert (edge['source_id'], edge['target_id'], edge['type']) == ('k1', 'k2', 'derives')
    assert edge['derivation_steps'] == ['代入定义', '求出极限']
    assert edge['conditions'] == ['额外条件'] and edge['strength_level'] == 'strong'
    assert [e['quote'] for e in edge['evidence_refs']] == ['冻结完整命题1', '冻结完整命题2']
    value['focus_links']['P2'][0]['p'] = 'P2'
    with pytest.raises(CourseDocumentConflict, match='排序靠前'):
        compile_relations({'course_id': 'c'}, pipeline, ['P2'], value, 'l')
