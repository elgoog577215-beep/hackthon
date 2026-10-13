import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts, answer
from course_repository import CourseDocumentConflict


def one_lesson_response(lid, name=None):
    data = answer(); index = 0 if lid == 'cpu' else 1
    data['points'] = [data['points'][index]]
    data['points'][0]['sources'] = [{'key': 'S1'}]
    if name: data['points'][0]['name'] = name
    data['lessons'] = [data['lessons'][index]]
    data['cross_alignment'] = [{'knowledge_key': p['key'], 'reason': '独立新命题', 'relation_reason': '已比较讲内与其他讲命题；只保留有依据的关系。', 'links': []} for p in data['points']]
    return data


@pytest.mark.parametrize('kind', ['teacher_lesson_script_generation', 'teacher_lesson_plan_generation', 'course_knowledge_tree_generation'])
def test_other_lecture_generation_does_not_block_selected_tree(svc, kind):
    handouts(svc)
    other = svc.authoring.create_job('c-pilot', 'tree' if kind == 'course_knowledge_tree_generation' else 'memory',
        job_type=kind, request_id='other', source_outline_revision_id='outline')
    svc.authoring.update_job('c-pilot', other['id'], status='running', knowledge_lesson_id='memory' if kind == 'course_knowledge_tree_generation' else '')
    view = svc.view('c-pilot', source_mode='handouts')
    job, created = svc.start('c-pilot', 'tree', 'cpu-new', view['knowledge_revision'], view['document_revision'], source_mode='handouts', lesson_id='cpu')
    assert created and job['knowledge_lesson_id'] == 'cpu'
    assert svc.authoring.get_job('c-pilot', other['id'])['status'] == 'running'


@pytest.mark.parametrize('scope', ['cpu', 'whole-course'])
def test_same_lecture_and_course_wide_jobs_still_block_and_are_visible(svc, scope):
    handouts(svc)
    blocker = svc.authoring.create_job('c-pilot', scope, job_type='teacher_lesson_script_generation', request_id='blocker')
    svc.authoring.update_job('c-pilot', blocker['id'], status='running', progress=35)
    view = svc.view('c-pilot', source_mode='handouts')
    with pytest.raises(CourseDocumentConflict):
        svc.start('c-pilot', 'tree', 'blocked', view['knowledge_revision'], view['document_revision'], source_mode='handouts', lesson_id='cpu')
    assert view['active_jobs'][0]['id'] == blocker['id']
    option = next(l for l in view['lesson_options'] if l['lesson_id'] == 'cpu')
    assert option['blocking_job_ids'] == [blocker['id']]
    svc.authoring.update_job('c-pilot', blocker['id'], status='failed')
    view = svc.view('c-pilot', source_mode='handouts')
    assert view['active_jobs'] == []
    assert next(l for l in view['lesson_options'] if l['lesson_id'] == 'cpu')['blocking_job_ids'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('changed_lesson', ['cpu', 'memory'])
async def test_parallel_handout_completion_only_invalidates_its_own_tree(svc, changed_lesson):
    handouts(svc)
    async def call(*args, **kwargs):
        state = svc.authoring.load('c-pilot')
        state['lessons'][changed_lesson]['script_revisions'][0]['sections'][0]['blocks'][0]['content'] += ' 已更新。'
        svc.authoring._save(state)
        return json.dumps(one_lesson_response('cpu'), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    view = svc.view('c-pilot', source_mode='handouts')
    job, _ = svc.start('c-pilot', 'tree', 'source-race', view['knowledge_revision'], view['document_revision'], source_mode='handouts', lesson_id='cpu')
    await svc.run('c-pilot', job['id'])
    result = svc.authoring.get_job('c-pilot', job['id'])
    assert result['status'] == ('failed' if changed_lesson == 'cpu' else 'completed')


def test_same_lesson_duplicate_request_reuses_the_job(svc):
    handouts(svc)
    view = svc.view('c-pilot', source_mode='handouts')
    args = ('c-pilot', 'tree', 'same-request', view['knowledge_revision'], view['document_revision'])
    first, created = svc.start(*args, source_mode='handouts', lesson_id='cpu')
    second, repeated = svc.start(*args, source_mode='handouts', lesson_id='cpu')
    assert created and not repeated and first['id'] == second['id']
    with pytest.raises(CourseDocumentConflict):
        svc.start('c-pilot', 'tree', 'another-request', view['knowledge_revision'], view['document_revision'], source_mode='handouts', lesson_id='cpu')


def test_published_course_reader_cannot_see_owner_blocking_jobs(svc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
    from routers.knowledge_first import router
    handouts(svc)
    svc.storage.update_course_data('c-pilot', lambda raw: {**raw, 'is_published': True})
    blocker = svc.authoring.create_job('c-pilot', 'cpu', job_type='teacher_lesson_script_generation', request_id='private')
    svc.authoring.update_job('c-pilot', blocker['id'], status='running')
    app = FastAPI()
    app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    with TestClient(app) as client:
        response = client.get('/api/courses/c-pilot/knowledge-first?source_mode=handouts', headers={'X-User-Id': 'reader'})
    assert response.status_code == 200
    assert response.json()['active_jobs'] == response.json()['blocking_job_ids'] == response.json()['jobs'] == []
    assert not response.json()['can_edit']


@pytest.mark.asyncio
async def test_single_lesson_generation_is_scoped_and_preserves_other_lesson_and_history(svc):
    handouts(svc)
    prompts = []
    async def call(prompt, **kwargs):
        prompts.append(prompt)
        return json.dumps(one_lesson_response('cpu' if len(prompts) in [1, 3] else 'memory', 'CPU新名称' if len(prompts) == 3 else None), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    saved = []
    for i, lid in enumerate(['cpu', 'memory', 'cpu']):
        v = svc.view('c-pilot', source_mode='handouts')
        job, _ = svc.start('c-pilot', 'tree', str(i), v['knowledge_revision'], v['document_revision'], source_mode='handouts', lesson_id=lid)
        assert job['knowledge_lesson_id'] == lid
        assert [l['lesson_id'] for l in job['request_snapshot']['knowledge_generation_context']['handout_lessons']] == [lid]
        await svc.run('c-pilot', job['id'])
        assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status'] == 'completed'
        svc.adopt('c-pilot', job['id'], v['knowledge_revision'], v['document_revision'])
        saved.append(deepcopy(svc.repository.load_raw('c-pilot')['course_knowledge_base']))
    assert '主存保存正在使用的数据。' not in prompts[0]
    assert 'CPU执行指令。' in prompts[1]  # Prior knowledge is reference context, not another handout input.
    before = next(p for p in saved[1]['knowledge_points'] if 'memory' in p['section_refs'])
    after = next(p for p in saved[2]['knowledge_points'] if 'memory' in p['section_refs'])
    assert before == after
    assert next(p for p in saved[2]['knowledge_points'] if 'cpu' in p['section_refs'])['name'] == 'CPU新名称'
    history = svc.repository.load_raw('c-pilot')['knowledge_first_history']
    assert history[saved[1]['revision_id']] == saved[1]
    view = svc.view('c-pilot', source_mode='handouts')
    assert {c['lesson_id'] for c in view['candidates']} == {'cpu', 'memory'}


def test_unknown_or_empty_lesson_cannot_fall_back_to_whole_course(svc):
    handouts(svc); v = svc.view('c-pilot', source_mode='handouts')
    with pytest.raises(CourseDocumentConflict, match='讲义'):
        svc.start('c-pilot', 'tree', 'bad', '', v['document_revision'], source_mode='handouts', lesson_id='foreign')
    assert not svc.authoring.load('c-pilot')['jobs']


def test_selected_context_does_not_depend_on_other_handout_content(svc):
    from handout_knowledge import handout_context
    handouts(svc); raw = svc.repository.load_raw('c-pilot'); state = svc.authoring.load('c-pilot')
    before = handout_context(raw, state, lesson_id='cpu')
    state['lessons']['memory']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '其他讲更新'
    after = handout_context(raw, state, lesson_id='cpu')
    assert before['revision_id'] == after['revision_id']
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '本讲更新'
    assert before['revision_id'] != handout_context(raw, state, lesson_id='cpu')['revision_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('reference_key', ['E1', 'K1'])
async def test_next_lesson_references_existing_ids_and_can_reuse_without_duplicating(svc, reference_key):
    handouts(svc)
    calls = []
    async def call(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1: return json.dumps(one_lesson_response('cpu'), ensure_ascii=False)
        assert 'existing_knowledge' in prompt and 'E1' in prompt and 'CPU执行指令。' in prompt
        value = one_lesson_response('memory')
        value['points'].append({'key': 'K1', 'reuse_key': 'E1', 'category_key': 'C2', 'sources': [{'key': 'S1'}]})
        value['cross_alignment'].append({'knowledge_key': 'K1', 'reason': '复用处理器命题', 'relation_reason': '处理器使用主存数据', 'links': []})
        value['lessons'][0]['knowledge_keys'].append('K1')
        value['relations'] = [{'source_key': reference_key, 'target_key': 'K2', 'type': 'prerequisite', 'reason': '处理器使用主存中的数据', 'conditions': []}]
        return json.dumps(value, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    for lid in ['cpu', 'memory']:
        v = svc.view('c-pilot', source_mode='handouts')
        job, _ = svc.start('c-pilot', 'tree', lid, v['knowledge_revision'], v['document_revision'], source_mode='handouts', lesson_id=lid)
        await svc.run('c-pilot', job['id'])
        assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status'] == 'completed'
        svc.adopt('c-pilot', job['id'], v['knowledge_revision'], v['document_revision'])
        if lid == 'cpu': original = deepcopy(svc.view('c-pilot')['tree']['knowledge_points'][0])
    tree = svc.view('c-pilot')['tree']
    assert len(tree['knowledge_points']) == 2
    reused = next(p for p in tree['knowledge_points'] if p['knowledge_id'] == original['knowledge_id'])
    assert set(reused['section_refs']) == {'cpu', 'memory'}
    assert reused['statement'] == original['statement']
    assert reused['revision_id'] == original['revision_id']
    assert tree['relations'][0]['source_id'] == original['knowledge_id']
    assert tree['relations'][0]['cross_lesson'] is True


def test_cross_lecture_cycle_is_rejected_after_merging_existing_edges(svc):
    from handout_knowledge import handout_context, merge_lesson_tree
    from generic_knowledge import compile_tree
    handouts(svc); raw = svc.repository.load_raw('c-pilot')
    old = compile_tree(raw, handout_context(raw, svc.authoring.load('c-pilot')), answer())
    a, b = [p['knowledge_id'] for p in old['knowledge_points']]
    old['relations'] = [{'id': 'old', 'type': 'prerequisite', 'source_id': a, 'target_id': b}]
    one = deepcopy(old); one['knowledge_points'] = [one['knowledge_points'][0]]
    one['relations'] = [{'id': 'new', 'type': 'prerequisite', 'source_id': b, 'target_id': a}]
    one['lessons'] = [one['lessons'][0]]
    with pytest.raises(CourseDocumentConflict, match='环'):
        merge_lesson_tree(old, one, 'cpu')


def test_unknown_reference_and_rewriting_existing_definition_are_rejected(svc):
    from handout_knowledge import handout_context
    from generic_knowledge import compile_tree
    handouts(svc); raw = svc.repository.load_raw('c-pilot'); state = svc.authoring.load('c-pilot')
    raw['course_knowledge_base'] = compile_tree(raw, handout_context(raw, state), answer())
    context = handout_context(raw, state, lesson_id='cpu')
    one = one_lesson_response('cpu'); one['relations'] = [{'source_key': 'E999', 'target_key': 'K1', 'type': 'prerequisite', 'reason': '未知端点'}]
    with pytest.raises(CourseDocumentConflict): compile_tree(raw, context, one)
    one = one_lesson_response('cpu'); one['points'][0]['reuse_key'] = 'E1'; one['points'][0]['statement'] = '把旧知识改成新定义'
    with pytest.raises(CourseDocumentConflict, match='未知'): compile_tree(raw, context, one)
    one['points'][0]['reuse_key'] = 'E2'
    with pytest.raises(CourseDocumentConflict, match='不能改写'): compile_tree(raw, context, one)


def test_untouched_material_based_points_remain_readable_in_mixed_preview(svc):
    from handout_knowledge import handout_context, visible_handout_tree
    from generic_knowledge import compile_tree
    handouts(svc); raw = svc.repository.load_raw('c-pilot')
    tree = compile_tree(raw, handout_context(raw, svc.authoring.load('c-pilot')), answer())
    point = tree['knowledge_points'][1]
    for quote in point['source_quotes']: quote.pop('handout_ref')
    point['verification_status'] = 'source_quote_checked_semantics_pending'
    block = {'block_id': 'visible', 'payload': {'knowledge_refs': [{'knowledge_id': point['knowledge_id'], 'revision_id': point['revision_id']}]}}
    view = visible_handout_tree(tree, {'blocks': [block]}, {})
    assert [p['knowledge_id'] for p in view['knowledge_points']] == [point['knowledge_id']]


@pytest.mark.asyncio
async def test_independent_lecture_candidates_can_be_adopted_in_sequence(svc):
    handouts(svc)
    replies = iter(['cpu', 'memory'])
    async def call(*args, **kwargs): return json.dumps(one_lesson_response(next(replies)), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    jobs = []
    for lid in ['cpu', 'memory']:
        v = svc.view('c-pilot', source_mode='handouts')
        job, _ = svc.start('c-pilot', 'tree', lid, v['knowledge_revision'], v['document_revision'], source_mode='handouts', lesson_id=lid)
        await svc.run('c-pilot', job['id']); jobs.append(job)
    for job in jobs:
        v = svc.view('c-pilot', source_mode='handouts')
        svc.adopt('c-pilot', job['id'], v['knowledge_revision'], v['document_revision'])
    v = svc.view('c-pilot', source_mode='handouts')
    assert {l['topic'] for l in v['tree']['lessons']} == {'cpu', 'memory'}
    assert len(v['tree']['knowledge_points']) == 2
    assert all(c['adopted'] for c in v['candidates'])
    revision = v['knowledge_revision']
    svc.adopt('c-pilot', jobs[0]['id'], revision, v['document_revision'])
    assert svc.view('c-pilot')['knowledge_revision'] == revision


@pytest.mark.asyncio
@pytest.mark.parametrize('changed_lesson', ['cpu', 'memory'])
async def test_changed_local_or_cross_lecture_definition_blocks_adoption(svc, changed_lesson):
    from generic_knowledge import compile_tree
    from handout_knowledge import handout_context
    handouts(svc); raw = svc.repository.load_raw('c-pilot')
    baseline = compile_tree(raw, handout_context(raw, svc.authoring.load('c-pilot')), answer())
    baseline['status'] = 'accepted'
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'course_knowledge_base': baseline, 'knowledge_first_history': {baseline['revision_id']: deepcopy(baseline)}})
    reply = one_lesson_response('cpu')
    reply['relations'] = [{'source_key': 'E2', 'target_key': 'K1', 'type': 'applies_to', 'reason': '处理器读取主存', 'conditions': []}]
    async def call(*args, **kwargs): return json.dumps(reply, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    v = svc.view('c-pilot')
    job, _ = svc.start('c-pilot', 'tree', 'changing', v['knowledge_revision'], v['document_revision'], source_mode='handouts', lesson_id='cpu')
    await svc.run('c-pilot', job['id'])
    changed = deepcopy(baseline); changed['revision_id'] = 'changed'
    next(p for p in changed['knowledge_points'] if changed_lesson in p['section_refs'])['statement'] = '新的知识定义'
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'course_knowledge_base': changed})
    with pytest.raises(CourseDocumentConflict, match='更新|变化'):
        svc.adopt('c-pilot', job['id'], 'changed', v['document_revision'])
