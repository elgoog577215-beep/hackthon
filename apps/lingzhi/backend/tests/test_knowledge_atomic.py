import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts
from course_repository import CourseDocumentConflict
from ai_base import AIProviderRequestError
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from routers.knowledge_first import router

PIPELINE = 'inventory_atomic_v1'


def test_inventory_groups_balance_source_size_without_splitting_or_losing_sources():
    from knowledge_atomic import source_groups
    from unittest.mock import patch
    units = {f'S{i}': {'source_text': 'x' * 1000} for i in range(12)}
    with patch('knowledge_atomic.sources', return_value=units): groups = source_groups({})
    assert [k for group in groups for k in group] == list(units)
    assert len(groups) == 3
    assert all(sum(len(units[k]['source_text']) for k in group) <= 4500 for group in groups)


@pytest.mark.asyncio
async def test_batch_failure_keeps_inflight_success_and_does_not_start_more_work():
    from knowledge_atomic import run_batches
    rows = [{'id': i, 'status': 'pending'} for i in range(4)]
    entered = asyncio.Event()
    started = []
    async def process(index, row):
        started.append(row['id'])
        if row['id'] == 0:
            await entered.wait()
            raise TimeoutError('one failed request')
        entered.set()
        await asyncio.sleep(.02)
        row['status'] = 'completed'
    with pytest.raises(TimeoutError): await run_batches(rows, process, width=2)
    assert started == [0, 1]
    assert rows[1]['status'] == 'completed'
    assert all(r['status'] == 'pending' for r in (rows[0], rows[2], rows[3]))


def test_progress_reserves_undiscovered_work_and_completes_only_after_save():
    from knowledge_atomic import pipeline_progress
    pipeline = {'organize_hierarchy': True, 'inventory_batches': [{'status': 'pending'}], 'batches': []}
    assert pipeline_progress(pipeline) == 0
    pipeline['inventory_batches'][0]['status'] = 'completed'
    assert pipeline_progress(pipeline) == 20
    pipeline['batches'] = [{'status': 'pending'} for _ in range(7)]
    assert pipeline_progress(pipeline) == 20
    for row in pipeline['batches']: row['status'] = 'completed'
    assert pipeline_progress(pipeline) == 85
    pipeline['hierarchy'] = {'status': 'completed'}
    assert pipeline_progress(pipeline) == 95  # Only the final persisted candidate is 100%.


@pytest.mark.asyncio
async def test_preview_keeps_all_frozen_points_reachable_during_subtree_generation(svc, monkeypatch):
    from knowledge_atomic import project_preview
    setup_course(svc, monkeypatch); provider(svc)
    job = start(svc); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    saved['status'] = 'running'
    pipeline = saved['checkpoint']['atomic_pipeline']
    pipeline['hierarchy'] = {'categories': [{'key': 'C1', 'name': '栈', 'scope': '栈操作', 'parent_key': None}],
        'assignments': [], 'tasks': [
            {'key': 'root', 'point_keys': ['K1', 'K2'], 'status': 'completed', 'is_root': True},
            {'key': 'C1', 'point_keys': ['K1', 'K2'], 'status': 'pending'}]}
    before = deepcopy(saved)
    tree = project_preview(saved, 'c-pilot')
    assert tree['generation_preview'] is True
    assert len(tree['knowledge_points']) == 2
    assert all(p['parent_id'] == tree['categories'][0]['id'] for p in tree['knowledge_points'])
    assert tree['atomic_assessment']['ready_for_adoption'] is False
    assert saved == before


@pytest.mark.asyncio
async def test_inventory_and_atomize_batches_use_bounded_concurrency(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = provider(svc)
    original_factory = svc.provider_factory
    active = 0
    peak = 0

    def factory():
        nonlocal active, peak
        base = original_factory()
        original_call = base._call_llm

        async def concurrent_call(prompt, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.02)
                return await original_call(prompt, **kwargs)
            finally:
                active -= 1

        base._call_llm = concurrent_call
        return base

    svc.provider_factory = factory
    job = start(svc)
    await svc.run('c-pilot', job['id'])
    assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status'] == 'completed'
    assert peak >= 2


@pytest.mark.asyncio
async def test_stream_metadata_does_not_persist_full_history_between_checkpoints(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc)
    job = start(svc)
    persisted = []
    original = svc.authoring.update_job
    def record(cid, jid, **changes):
        persisted.append(changes)
        return original(cid, jid, **changes)
    monkeypatch.setattr(svc.authoring, 'update_job', record)
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    assert len(saved['stage_observations']) == 3
    assert not any('model_telemetry' in changes or 'raw_response' in changes and 'checkpoint' not in changes for changes in persisted)


def setup_course(svc, monkeypatch):
    monkeypatch.setenv('COURSE_KNOWLEDGE_ATOMIC_BATCH_SIZE', '1')
    handouts(svc)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '入栈将元素插入栈顶。出栈移除并返回栈顶元素。'
    svc.authoring._save(state)


def inventory():
    return {'items': [
        {'key': 'I1', 'name': '入栈', 'kind': 'rule', 'claim': '入栈将元素插入栈顶。', 'focus_terms': ['入栈'],
         'sources': [{'key': 'S1', 'quote': '入栈将元素插入栈顶。'}]},
        {'key': 'I2', 'name': '出栈', 'kind': 'rule', 'claim': '出栈移除并返回栈顶元素。', 'focus_terms': ['出栈'],
         'sources': [{'key': 'S1', 'quote': '出栈移除并返回栈顶元素。'}]},
    ], 'source_coverage': [{'source_key': 'S1', 'item_keys': ['I1', 'I2'], 'handling': 'items', 'reason': '分别记录两个独立操作。'}]}


def atomic_answer(items):
    return {'categories': [{'key': 'C1', 'name': '栈操作', 'parent_key': None}],
        'points': [{'key': f'K{i}', 'category_key': 'C1', 'name': item['name'], 'statement': item['claim'],
            'conditions': [], 'meta_question': item['name'] + '执行什么操作？', 'meta_answer': item['claim'],
            'sources': item['sources'], 'inventory_keys': [item['key']], 'independent_claims': [item['claim']]}
            for i, item in enumerate(items, 1)],
        'coverage': [{'inventory_key': item['key'], 'point_keys': [f'K{i}'], 'handling': 'point', 'reason': '独立命题。'} for i, item in enumerate(items, 1)],
        'question_coverage': [{'inventory_key': item['key'], 'point_key': f'K{i}',
            'question_quote': item['name'] + '执行什么操作？', 'answer_quote': item['claim']} for i, item in enumerate(items, 1)], 'gaps': []}


def provider(svc, *, fail_at=None, mutate=None):
    calls = []
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        calls.append(data)
        assert kwargs['max_attempts'] == 1
        if fail_at == len(calls):
            raise TimeoutError('isolated interruption')
        if data['stage'] == 'hierarchy_partition':
            result = {'response_contract': 'knowledge_partition_v1',
                'groups': [{'key': f'G{i}', 'name': p['name'], 'scope': p['statement']} for i,p in enumerate(data['points'])],
                'point_groups': {p['key']: f'G{i}' for i,p in enumerate(data['points'])}, 'stop_reason': '区分插入与删除操作'}
        else:
            result = inventory() if data['stage'] == 'inventory' else atomic_answer(data['items'])
        if mutate:
            mutate(data, result)
        text = json.dumps(result, ensure_ascii=False)
        kwargs['on_content_delta'](text)
        return text
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test-qwen', client=None)
    return calls


def start(svc, request_id='atomic', **extra):
    view = svc.view('c-pilot', source_mode='handouts')
    return svc.start('c-pilot', 'tree', request_id, view['knowledge_revision'], view['document_revision'],
        source_mode='handouts', lesson_id='cpu', pipeline=PIPELINE, **extra)[0]


@pytest.mark.asyncio
async def test_new_generation_organizes_all_batches_without_changing_frozen_leaves(svc, monkeypatch):
    setup_course(svc, monkeypatch); calls = provider(svc)
    job = start(svc, organize_hierarchy=True); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    cp = saved['checkpoint']; candidate = cp['candidate']
    assert [c['stage'] for c in calls] == ['inventory', 'atomize', 'atomize', 'hierarchy_partition']
    assert len(calls[-1]['points']) == 2
    assert cp['atomic_pipeline']['hierarchy']['status'] == 'completed'
    assert len(candidate['categories']) == 2
    assert len(candidate['categories']) == len({p['parent_id'] for p in candidate['knowledge_points']})
    frozen = [p for b in cp['atomic_pipeline']['batches'] for p in b['tree']['knowledge_points']]
    for point, original in zip(candidate['knowledge_points'], frozen):
        for field in ('knowledge_id', 'statement', 'source_quotes', 'meta_question', 'meta_answer'):
            assert point[field] == original[field]
    assert candidate['atomic_assessment']['relation_status'] == 'not_run'


@pytest.mark.asyncio
async def test_existing_candidate_can_reorganize_only_hierarchy_and_preserve_old_job(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc)
    original = start(svc); await svc.run('c-pilot', original['id'])
    before = deepcopy(svc.authoring.load('c-pilot')['jobs'][original['id']]); raw = deepcopy(svc.repository.load_raw('c-pilot'))
    calls = provider(svc)
    new = start(svc, 'organize', resume_job_id=original['id'], retry_batch_id='hierarchy')
    await svc.run('c-pilot', new['id'])
    after = svc.authoring.load('c-pilot')['jobs'][new['id']]
    assert after['status'] == 'completed'
    assert [c['stage'] for c in calls] == ['hierarchy_partition']
    assert after['checkpoint']['atomic_pipeline']['batches'] == before['checkpoint']['atomic_pipeline']['batches']
    assert svc.authoring.load('c-pilot')['jobs'][original['id']] == before
    assert svc.repository.load_raw('c-pilot') == raw
    for point, prior in zip(after['checkpoint']['candidate']['knowledge_points'], before['checkpoint']['candidate']['knowledge_points']):
        assert point['knowledge_id'] == prior['knowledge_id'] and point['revision_id'] == prior['revision_id']


@pytest.mark.asyncio
async def test_failed_hierarchy_continue_reuses_all_completed_atomic_batches(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc, fail_at=4)
    old = start(svc, organize_hierarchy=True); await svc.run('c-pilot', old['id'])
    assert svc.authoring.load('c-pilot')['jobs'][old['id']]['status'] == 'failed'
    calls = provider(svc)
    new = start(svc, 'resume-hierarchy', resume_job_id=old['id'])
    await svc.run('c-pilot', new['id'])
    assert [c['stage'] for c in calls] == ['hierarchy_partition']
    assert svc.authoring.load('c-pilot')['jobs'][new['id']]['status'] == 'completed'


@pytest.mark.asyncio
async def test_replacing_leaf_batch_invalidates_hierarchy_and_preserves_other_batch(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc)
    old = start(svc, organize_hierarchy=True); await svc.run('c-pilot', old['id'])
    prior = svc.authoring.load('c-pilot')['jobs'][old['id']]['checkpoint']['atomic_pipeline']
    calls = provider(svc)
    new = start(svc, 'retry-organized-leaf', resume_job_id=old['id'], retry_batch_id='atoms-2')
    await svc.run('c-pilot', new['id'])
    assert [c['stage'] for c in calls] == ['atomize', 'hierarchy_partition']
    assert svc.authoring.load('c-pilot')['jobs'][new['id']]['checkpoint']['atomic_pipeline']['batches'][0] == prior['batches'][0]


@pytest.mark.asyncio
async def test_inventory_batches_and_questions_are_durable_without_course_writes(svc, monkeypatch):
    setup_course(svc, monkeypatch); before = deepcopy(svc.repository.load_raw('c-pilot')); calls = provider(svc)
    job = start(svc); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    cp = saved['checkpoint']['atomic_pipeline']
    assert len(cp['items']) == 2 and len(cp['batches']) == 2
    assert all(b['status'] == 'completed' for b in cp['batches'])
    candidate = saved['checkpoint']['candidate']
    assert len(candidate['knowledge_points']) == 2
    assert candidate['atomic_assessment']['ready_for_adoption']
    assert candidate['atomic_assessment']['semantics_verified'] is False
    assert [c['stage'] for c in calls] == ['inventory', 'atomize', 'atomize']
    assert svc.repository.load_raw('c-pilot') == before


@pytest.mark.asyncio
async def test_provider_gateway_failure_is_reported_as_model_unavailable(svc, monkeypatch):
    setup_course(svc, monkeypatch)

    async def call(prompt, **kwargs):
        raise AIProviderRequestError('Error code: 502 - Bad Gateway')

    svc.provider_factory = lambda: SimpleNamespace(
        _call_llm=call, model_smart='test-qwen', client=None
    )
    job = start(svc, 'gateway-failure')
    await svc.run('c-pilot', job['id'])

    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'failed'
    assert saved['error']['code'] == 'ModelConnectionUnavailable'
    assert '模型服务' in saved['error']['message']
    assert not saved['checkpoint']['atomic_pipeline']['items']


@pytest.mark.asyncio
async def test_explicit_continue_reuses_inventory_and_completed_batches(svc, monkeypatch):
    setup_course(svc, monkeypatch); calls = provider(svc, fail_at=3)
    job = start(svc); await svc.run('c-pilot', job['id'])
    old = deepcopy(svc.authoring.load('c-pilot')['jobs'][job['id']])
    assert old['status'] == 'failed'
    assert old['checkpoint']['atomic_pipeline']['batches'][0]['status'] == 'completed'
    resumed_calls = provider(svc)
    resumed = start(svc, 'continue', resume_job_id=job['id'])
    await svc.run('c-pilot', resumed['id'])
    assert len(resumed_calls) == 1 and resumed_calls[0]['stage'] == 'atomize'
    assert svc.authoring.load('c-pilot')['jobs'][resumed['id']]['status'] == 'completed'
    assert svc.authoring.load('c-pilot')['jobs'][job['id']] == old
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_multiple_independent_items_in_one_point_block_adoption(svc, monkeypatch):
    setup_course(svc, monkeypatch); monkeypatch.setenv('COURSE_KNOWLEDGE_ATOMIC_BATCH_SIZE', '8')
    def coarse(data, result):
        if data['stage'] != 'atomize': return
        result['points'] = [result['points'][0]]
        result['points'][0]['inventory_keys'] = [i['key'] for i in data['items']]
        for row in result['coverage']: row['point_keys'] = ['K1']
        for row in result['question_coverage']: row['point_key'] = 'K1'
    provider(svc, mutate=coarse); job = start(svc); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    report = saved['checkpoint']['candidate']['atomic_assessment']
    assert not report['ready_for_adoption']
    assert any(i['code'] == 'multiple_independent_items' for i in report['issues'])
    view = svc.view('c-pilot')
    with pytest.raises(CourseDocumentConflict, match='覆盖|细化'):
        svc.adopt('c-pilot', job['id'], '', view['document_revision'])


@pytest.mark.asyncio
async def test_question_that_only_checks_pop_does_not_cover_push(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    def wrong_question(data, result):
        if data['stage'] == 'atomize' and data['items'][0]['name'] == '入栈':
            p = result['points'][0]; p['meta_question'] = '出栈移除什么？'; p['meta_answer'] = '栈顶元素。'
            result['question_coverage'][0].update(question_quote=p['meta_question'], answer_quote=p['meta_answer'])
    provider(svc, mutate=wrong_question); job = start(svc); await svc.run('c-pilot', job['id'])
    report = svc.authoring.load('c-pilot')['jobs'][job['id']]['checkpoint']['candidate']['atomic_assessment']
    assert not report['ready_for_adoption']
    assert any(i['code'] == 'question_focus_missing' for i in report['issues'])


@pytest.mark.asyncio
async def test_retries_only_selected_batch_and_keeps_successful_batch(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc); job = start(svc); await svc.run('c-pilot', job['id'])
    before = svc.authoring.load('c-pilot')['jobs'][job['id']]['checkpoint']['atomic_pipeline']
    calls = provider(svc); new = start(svc, 'retry-one', resume_job_id=job['id'], retry_batch_id=before['batches'][1]['id'])
    await svc.run('c-pilot', new['id'])
    assert len(calls) == 1
    after = svc.authoring.load('c-pilot')['jobs'][new['id']]['checkpoint']['atomic_pipeline']
    assert after['batches'][0]['tree'] == before['batches'][0]['tree']


@pytest.mark.asyncio
async def test_changed_sources_reject_continue_before_any_model_call(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc, fail_at=3); job = start(svc); await svc.run('c-pilot', job['id'])
    state = svc.authoring.load('c-pilot'); state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] += '来源改变。'
    svc.authoring._save(state); calls = provider(svc)
    with pytest.raises(CourseDocumentConflict): start(svc, 'stale', resume_job_id=job['id'])
    assert calls == []


@pytest.mark.asyncio
async def test_status_stays_small_but_version_changes_when_a_batch_finishes(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc); job = start(svc)
    before = svc.status('c-pilot')['result_version']; await svc.run('c-pilot', job['id'])
    after = svc.status('c-pilot')
    assert before != after['result_version'] and len(json.dumps(after).encode()) < 20000
    assert '独立命题' not in json.dumps(after, ensure_ascii=False)


@pytest.mark.asyncio
async def test_public_reader_does_not_receive_private_inventory_or_batch_drafts(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc, fail_at=3); job = start(svc); await svc.run('c-pilot', job['id'])
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'is_published': True})
    app = FastAPI(); app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    response = TestClient(app).get('/api/courses/c-pilot/knowledge-first', headers={'X-User-Id': 'foreign'})
    assert response.status_code == 200 and response.json().get('atomic_runs', []) == []


@pytest.mark.asyncio
async def test_existing_point_identity_and_semantic_revision_survive_exact_refinement(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc); first = start(svc); await svc.run('c-pilot', first['id'])
    tree = deepcopy(svc.authoring.load('c-pilot')['jobs'][first['id']]['checkpoint']['candidate'])
    point = tree['knowledge_points'][0]; prior_id = point['knowledge_id']; point['knowledge_id'] = point['id'] = 'existing-custom-id'
    for lesson in tree['lessons']: lesson['knowledge_ids'] = ['existing-custom-id' if k == prior_id else k for k in lesson['knowledge_ids']]
    tree['revision_id'] = 'existing-tree'; tree['status'] = 'accepted'
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'course_knowledge_base': tree, 'knowledge_first_history': {'existing-tree': tree}})
    before = deepcopy(svc.repository.load_raw('c-pilot')); provider(svc)
    second = start(svc, 'same-facts'); await svc.run('c-pilot', second['id'])
    candidate = svc.authoring.load('c-pilot')['jobs'][second['id']]['checkpoint']['candidate']
    unchanged = next(p for p in candidate['knowledge_points'] if p['knowledge_id'] == 'existing-custom-id')
    assert unchanged['revision_id'] == point['revision_id']
    assert not candidate['identity_changes']['retired_points']
    assert svc.repository.load_raw('c-pilot') == before


@pytest.mark.asyncio
async def test_replacing_coarse_point_requires_confirmation_and_preserves_history_refs(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    old = {'revision_id': 'old-tree', 'source_mode': 'handouts', 'status': 'accepted', 'categories': [], 'concept_groups': [],
        'knowledge_points': [{'id': 'old-coarse', 'knowledge_id': 'old-coarse', 'revision_id': 'old-point-rev', 'name': '栈操作',
            'statement': '入栈插入元素；出栈移除元素。', 'conditions': [], 'section_refs': ['cpu'], 'source_quotes': []}],
        'relations': [], 'sources': [], 'lessons': [{'topic': 'cpu', 'title': '栈', 'knowledge_ids': ['old-coarse']}], 'source_handouts': []}
    refs = {'question-old': {'knowledge_id': 'old-coarse', 'knowledge_revision_id': 'old-point-rev', 'baseline_revision': 'old-tree'}}
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'course_knowledge_base': old, 'historical_question_refs': refs})
    provider(svc); job = start(svc); await svc.run('c-pilot', job['id'])
    view = svc.view('c-pilot')
    with pytest.raises(CourseDocumentConflict, match='身份'):
        svc.adopt('c-pilot', job['id'], 'old-tree', view['document_revision'])
    svc.adopt('c-pilot', job['id'], 'old-tree', view['document_revision'], confirm_identity_changes=True)
    raw = svc.repository.load_raw('c-pilot')
    assert raw['historical_question_refs'] == refs
    assert raw['knowledge_first_history']['old-tree']['knowledge_points'][0]['knowledge_id'] == 'old-coarse'
    assert raw['knowledge_first_history']['old-tree']['knowledge_points'][0]['revision_id'] == 'old-point-rev'
    assert all(p['knowledge_id'] != 'old-coarse' for p in raw['course_knowledge_base']['knowledge_points'])


@pytest.mark.asyncio
async def test_completed_batches_change_observation_version_before_task_finishes(svc, monkeypatch):
    setup_course(svc, monkeypatch); versions = []
    original = svc.authoring.update_job
    def observe(cid, jid, **changes):
        saved = original(cid, jid, **changes)
        if changes.get('completed_batches') in {1, 2}:
            versions.append(svc.status(cid)['result_version'])
        return saved
    monkeypatch.setattr(svc.authoring, 'update_job', observe)
    provider(svc); job = start(svc); await svc.run('c-pilot', job['id'])
    assert len(versions) == 2 and versions[0] != versions[1]


def test_task_and_source_checks_do_not_copy_all_historical_jobs(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    job = start(svc)
    raw = svc.repository.load_raw('c-pilot')
    expected = svc._context(raw, 'handouts', 'cpu')
    monkeypatch.setattr(svc.authoring, 'load', lambda *_: pytest.fail('copied entire authoring history'))
    assert svc._active('c-pilot', job['id'])['id'] == job['id']
    assert svc._context(raw, 'handouts', 'cpu') == expected


@pytest.mark.asyncio
async def test_refinement_may_not_drop_inventory_conditions(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    def conditioned(data, result):
        if data['stage'] == 'inventory': result['items'][0]['conditions'] = ['栈未满']
    provider(svc, mutate=conditioned); job = start(svc); await svc.run('c-pilot', job['id'])
    report = svc.authoring.load('c-pilot')['jobs'][job['id']]['checkpoint']['candidate']['atomic_assessment']
    assert not report['ready_for_adoption']
    assert any(i['code'] == 'condition_coverage_missing' for i in report['issues'])


@pytest.mark.asyncio
async def test_partial_batch_response_cannot_bypass_atomic_checks_via_legacy_recheck(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc, fail_at=3); job = start(svc); await svc.run('c-pilot', job['id'])
    view = svc.view('c-pilot', source_mode='handouts')
    assert not next(j for j in view['jobs'] if j['id'] == job['id'])['recheck_available']
    with pytest.raises(CourseDocumentConflict, match='分批'):
        svc.recheck('c-pilot', job['id'], 'bypass', view['document_revision'], view['knowledge_revision'])


@pytest.mark.asyncio
async def test_adopted_private_inventory_is_not_exposed_to_published_readers(svc, monkeypatch):
    setup_course(svc, monkeypatch); provider(svc); job = start(svc); await svc.run('c-pilot', job['id'])
    view = svc.view('c-pilot', source_mode='handouts')
    svc.adopt('c-pilot', job['id'], '', view['document_revision'])
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'is_published': True})
    app = FastAPI(); app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    result = TestClient(app).get('/api/courses/c-pilot/knowledge-first', headers={'X-User-Id': 'foreign'}).json()
    assert 'knowledge_inventory' not in result['tree']
    assert 'inventory_source_coverage' not in result['tree']
    assert 'identity_changes' not in result['tree']


def test_background_source_group_can_have_no_independent_inventory_items(svc, monkeypatch):
    from knowledge_atomic import compile_inventory
    setup_course(svc, monkeypatch)
    context = svc._context(svc.repository.load_raw('c-pilot'), 'handouts', 'cpu')
    result = {'items': [], 'source_coverage': [{'source_key':'S1', 'item_keys':[], 'handling':'context', 'reason':'课程背景，非独立命题'}]}
    items, coverage = compile_inventory(result, context, ['S1'], 1)
    assert items == [] and coverage[0]['handling'] == 'context'


@pytest.mark.asyncio
async def test_correct_answer_cannot_hide_a_question_about_another_operation(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    def wrong_question(data, result):
        if data['stage'] == 'atomize' and data['items'][0]['name'] == '入栈':
            result['points'][0]['meta_question'] = '出栈执行什么操作？'
            result['question_coverage'][0]['question_quote'] = '出栈执行什么操作？'
    provider(svc, mutate=wrong_question); job = start(svc); await svc.run('c-pilot', job['id'])
    report = svc.authoring.load('c-pilot')['jobs'][job['id']]['checkpoint']['candidate']['atomic_assessment']
    assert any(i['code'] == 'question_focus_missing' for i in report['issues'])
