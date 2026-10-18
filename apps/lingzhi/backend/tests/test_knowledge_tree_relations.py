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
    return {'point_reviews': {key: '已比较全目录，按命题判断直接教学依赖。' for key in data['focus_keys']},
        'links': [{'source_key': a, 'target_key': b, 'type': 'prerequisite',
                   'necessity': 'recommended', 'context': '比较栈顶操作', 'reason': '先理解元素如何加入栈顶，再比较移除规则。',
                   'conditions': [], 'strength': 'medium', 'derivation_steps': []}], 'gaps': []}


def fake_provider(svc, *, relation_fails=False):
    calls = []; started = asyncio.Event()
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); stage = data['stage']
        if stage == 'extract': value = response()
        elif stage == 'tree_relations':
            started.set()
            if relation_fails: raise TimeoutError('isolated relationship failure')
            value = relation_response(data)
            assert set(value) == {'point_reviews', 'links', 'gaps'}
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


@pytest.mark.parametrize('change', ['unknown', 'missing_review', 'cycle', 'rewrite', 'steps'])
def test_compact_relations_keep_existing_graph_guards(change):
    from knowledge_tree_relations import compile_relations
    points = [{'key': 'P1', 'knowledge_id': 'a', 'revision_id': 'r1', 'name': 'A', 'statement': '冻结命题甲', 'conditions': [], 'lesson_ids': ['l']},
              {'key': 'P2', 'knowledge_id': 'b', 'revision_id': 'r2', 'name': 'B', 'statement': '冻结命题乙', 'conditions': [], 'lesson_ids': ['l']}]
    pipeline = {'catalog': points, 'base_revision': 'frozen', 'baseline_relations': []}
    value = relation_response({'focus_keys': ['P1', 'P2']})
    if change == 'unknown': value['links'][0]['target_key'] = 'foreign'
    if change == 'missing_review': value['point_reviews'].pop('P2')
    if change == 'cycle': value['links'].append({**value['links'][0], 'source_key': 'P2', 'target_key': 'P1'})
    if change == 'rewrite': value['knowledge_points'] = []
    if change == 'steps': value['links'][0]['type'] = 'derives'
    with pytest.raises(CourseDocumentConflict): compile_relations({'course_id': 'c'}, pipeline, ['P1', 'P2'], value, 'l')


@pytest.mark.asyncio
async def test_relation_shards_run_together_and_resume_only_failed_shard(monkeypatch):
    from knowledge_tree_relations import generate
    monkeypatch.setenv('COURSE_KNOWLEDGE_TREE_RELATION_BATCH_SIZE', '2')
    points = [{'knowledge_id': f'k{i}', 'revision_id': f'r{i}', 'name': f'知识{i}', 'statement': f'冻结命题{i}',
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
