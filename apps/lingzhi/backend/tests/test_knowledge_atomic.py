import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts
from course_repository import CourseDocumentConflict
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from routers.knowledge_first import router

PIPELINE = 'inventory_atomic_v1'


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


def test_public_reader_does_not_receive_private_inventory_or_batch_drafts(svc, monkeypatch):
    setup_course(svc, monkeypatch); svc.storage.update_course_data('c-pilot', lambda r: {**r, 'is_published': True})
    app = FastAPI(); app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    response = TestClient(app).get('/api/courses/c-pilot/knowledge-first', headers={'X-User-Id': 'foreign'})
    assert response.status_code == 200 and response.json().get('atomic_runs', []) == []
