import asyncio
from copy import deepcopy

import pytest

from knowledge_mastery import freeze_knowledge_refs
from question_bank import QuestionBankRepository, formal_task_from_question_bank_item, refresh_question_bank_bundle
from question_bank_knowledge import bind_questions, binding_view


def course():
    return {'course_id': 'c1', 'owner_id': 'owner', 'nodes': [], 'course_knowledge_base': {
        'revision_id': 'tree1', 'lifecycle_status': 'active',
        'knowledge_points': [
            {'knowledge_id': 'k1', 'revision_id': 'kr1', 'status': 'active', 'granularity_status': 'atomic', 'name': '整数除法', 'statement': '整数除法向零截断', 'section_refs': ['n1']},
            {'knowledge_id': 'k2', 'revision_id': 'kr2', 'status': 'active', 'granularity_status': 'atomic', 'name': '条件判断', 'statement': 'if 执行条件为真的分支', 'section_refs': ['n1']},
            {'knowledge_id': 'group', 'revision_id': 'gr1', 'status': 'active', 'granularity_status': 'compound', 'name': '分类'},
        ],
    }}


def bank():
    return refresh_question_bank_bundle({'course_id': 'c1', 'items': [{
        'item_id': 'q1', 'revision_id': 'r1', 'course_id': 'c1', 'node_id': 'n1',
        'prompt': '计算 -7 / 2 的整数结果。', 'question_type': 'single_choice',
        'options': [{'id': 'A', 'text': '-3'}, {'id': 'B', 'text': '-4'}],
        'answer_spec': {'canonical_answer': 'A'}, 'course_knowledge_refs': ['k1', 'k2'],
        'lifecycle_status': 'approved', 'quality_report': {'passed': True},
    }]})


async def match(items, points):
    assert {p['knowledge_id'] for p in points} == {'k1', 'k2'}
    return [{'revision_id': i['revision_id'], 'knowledge_ids': ['k1'], 'confidence': 0.95,
             'reason': '直接考查整数除法的取整规则', 'evidence': '-7 / 2'} for i in items]


def test_auto_binds_actual_atomic_target_not_all_lecture_points_and_is_idempotent():
    original = bank()
    updated = asyncio.run(bind_questions(course(), original, matcher=match))
    item = updated['items'][0]
    assert original['items'][0]['course_knowledge_refs'] == ['k1', 'k2']
    assert item['course_knowledge_refs'] == ['k1']
    assert item['revision_id'] != 'r1'
    assert item['parent_revision_id'] == 'r1'
    assert item['knowledge_binding']['knowledge_revision_refs'] == {'k1': 'kr1'}
    assert binding_view(course(), updated)['counts']['bound'] == 1
    assert asyncio.run(bind_questions(course(), updated, matcher=None)) == updated


def test_manual_binding_is_validated_and_old_revisions_remain_readable(tmp_path):
    repository = QuestionBankRepository(tmp_path)
    original = repository.save_bundle('c1', bank())
    updated = asyncio.run(bind_questions(course(), original, mode='manual', revision_id='r1', knowledge_ids=['k2']))
    repository.save_bundle('c1', updated)
    assert repository.load_bundle('c1', original['bundle_revision_id']) == original
    assert updated['items'][0]['answer_spec'] == original['items'][0]['answer_spec']
    for ids in (['missing'], ['group'], ['k1', 'k1']):
        with pytest.raises(ValueError):
            asyncio.run(bind_questions(course(), original, mode='manual', revision_id='r1', knowledge_ids=ids))


def test_question_binding_freezes_revisions_and_never_relabels_old_attempts():
    updated = asyncio.run(bind_questions(course(), bank(), matcher=match))
    task = formal_task_from_question_bank_item(updated['items'][0])
    changed = course()
    changed['course_knowledge_base']['knowledge_points'][0]['revision_id'] = 'kr-new'
    assert binding_view(changed, updated)['counts']['stale'] == 1
    assert freeze_knowledge_refs(changed['course_knowledge_base'], task) == {'k1': 'kr1'}
    assert task['concept_ids'] == ['k1']


def test_uncertain_match_remains_pending_and_does_not_feed_section_refs_to_mastery():
    async def uncertain(items, points):
        return [{'revision_id': 'r1', 'knowledge_ids': ['k1'], 'confidence': .5, 'reason': '不确定', 'evidence': '-7 / 2'}]
    updated = asyncio.run(bind_questions(course(), bank(), matcher=uncertain))
    assert binding_view(course(), updated)['counts']['pending'] == 1
    task = formal_task_from_question_bank_item(updated['items'][0])
    assert task['concept_ids'] == []
    assert freeze_knowledge_refs(course()['course_knowledge_base'], task) == {}


def test_no_tree_no_matching_or_mutation():
    assert asyncio.run(bind_questions({'course_id': 'c1'}, bank(), matcher=None)) == bank()
    assert binding_view({'course_id': 'c1'}, bank())['tree_ready'] is False


def test_generated_exact_binding_does_not_call_model():
    bundle = bank()
    bundle['items'][0].update(assessment_binding_schema='atomic_assessment_v1',
        primary_knowledge_ids=['k1'], course_knowledge_refs=['k1'],
        knowledge_revision_refs={'k1': 'kr1'}, knowledge_baseline_revision='tree1')
    assert binding_view(course(), bundle)['counts']['bound'] == 1
    assert asyncio.run(bind_questions(course(), bundle, matcher=None)) == bundle


def test_foreign_ids_or_missing_model_rows_fail_without_partial_write():
    for rows in ([], [{'revision_id': 'r1', 'knowledge_ids': ['foreign'], 'confidence': .99, 'reason': 'x', 'evidence': '-7 / 2'}]):
        async def bad(items, points):
            return rows
        original = bank()
        before = deepcopy(original)
        with pytest.raises(ValueError):
            asyncio.run(bind_questions(course(), original, matcher=bad))
        assert original == before


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import question_bank_knowledge as domain
    from question_bank_jobs import QuestionBankRebuildJobRepository
    from routers import question_bank as routes

    current = course()
    repository = QuestionBankRepository(tmp_path / 'banks')
    original = repository.save_bundle('c1', bank())
    async def get_course(course_id):
        assert course_id == 'c1'
        return deepcopy(current)
    monkeypatch.setattr(routes, 'get_course_or_404', get_course)
    monkeypatch.setattr(routes, 'question_bank_repository', repository)
    monkeypatch.setattr(routes, 'question_bank_rebuild_job_repository', QuestionBankRebuildJobRepository(tmp_path / 'jobs'))
    monkeypatch.setattr(routes, '_require_bundle', lambda _: repository.load_bundle('c1'))
    monkeypatch.setattr(domain, 'match_questions', match)
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    with TestClient(app) as client:
        yield client, current, repository, original


def request_body(original, **extras):
    return {'mode': 'auto', 'expected_bundle_revision_id': original['bundle_revision_id'],
            'knowledge_baseline_revision': 'tree1', **extras}


def test_api_owner_auto_bind_and_read_is_side_effect_free(api):
    client, current, repository, original = api
    headers = {'X-User-Id': 'owner'}
    path = '/api/courses/c1/question-bank/knowledge-bindings'
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert repository.load_bundle('c1') == original
    response = client.post(path, headers=headers, json=request_body(original))
    assert response.status_code == 200, response.text
    assert response.json()['counts']['bound'] == 1
    assert repository.load_bundle('c1', original['bundle_revision_id']) == original


@pytest.mark.parametrize('surface', ['teacher', 'student'])
def test_api_rejects_nonowner_even_for_published_course(api, surface):
    client, current, repository, original = api
    current.update(authoring_surface=surface, is_published=True)
    path = '/api/courses/c1/question-bank/knowledge-bindings'
    assert client.get(path, headers={'X-User-Id': 'stranger'}).status_code == 404
    assert client.post(path, headers={'X-User-Id': 'stranger'}, json=request_body(original)).status_code == 404
    assert repository.load_bundle('c1') == original


def test_api_detects_tree_update_during_model_call(api, monkeypatch):
    import question_bank_knowledge as domain
    client, current, repository, original = api
    async def concurrent(items, points):
        current['course_knowledge_base']['revision_id'] = 'tree2'
        return await match(items, points)
    monkeypatch.setattr(domain, 'match_questions', concurrent)
    response = client.post('/api/courses/c1/question-bank/knowledge-bindings', headers={'X-User-Id': 'owner'}, json=request_body(original))
    assert response.status_code == 409
    assert repository.load_bundle('c1') == original


def test_api_detects_bank_update_during_model_call(api, monkeypatch):
    import question_bank_knowledge as domain
    client, current, repository, original = api
    async def concurrent(items, points):
        updated = deepcopy(original)
        updated['items'][0]['prompt'] = '教师刚刚编辑过的题目'
        repository.save_bundle('c1', updated)
        return await match(items, points)
    monkeypatch.setattr(domain, 'match_questions', concurrent)
    response = client.post('/api/courses/c1/question-bank/knowledge-bindings', headers={'X-User-Id': 'owner'}, json=request_body(original))
    assert response.status_code == 409
    assert repository.load_bundle('c1')['items'][0]['prompt'] == '教师刚刚编辑过的题目'


def test_api_provider_failure_keeps_original_and_hides_internal_details(api, monkeypatch):
    import question_bank_knowledge as domain
    client, current, repository, original = api
    async def failed(*_args):
        raise RuntimeError('private provider address')
    monkeypatch.setattr(domain, 'match_questions', failed)
    response = client.post('/api/courses/c1/question-bank/knowledge-bindings', headers={'X-User-Id': 'owner'}, json=request_body(original))
    assert response.status_code == 503
    assert 'private provider' not in response.text
    assert repository.load_bundle('c1') == original


def test_api_refuses_binding_during_generation(api, monkeypatch):
    from routers import question_bank as routes
    client, current, repository, original = api
    monkeypatch.setattr(routes.question_bank_rebuild_job_repository, 'active_for_course', lambda _: {'job_id': 'active'})
    response = client.post('/api/courses/c1/question-bank/knowledge-bindings', headers={'X-User-Id': 'owner'}, json=request_body(original))
    assert response.status_code == 409
    assert repository.load_bundle('c1') == original


def test_wording_edit_requires_binding_confirmation_again():
    from question_bank import revise_question_bank_item
    updated = asyncio.run(bind_questions(course(), bank(), matcher=match))
    item = updated['items'][0]
    edited = revise_question_bank_item(updated, item['revision_id'], patch={'prompt': '判断 if 条件为假时是否执行分支。'}, editor_id='owner')
    assert binding_view(course(), edited)['counts']['unbound'] == 1
    assert formal_task_from_question_bank_item(edited['items'][0])['concept_ids'] == []


def test_new_association_prepares_refs_but_does_not_certify_independent_mastery():
    from practice_grading import PracticeGrader
    updated = asyncio.run(bind_questions(course(), bank(), matcher=match))
    task = formal_task_from_question_bank_item(updated['items'][0])
    task['grading_policy'] = {'method': 'choice'}
    result = asyncio.run(PracticeGrader.__new__(PracticeGrader).grade(task, {'answer_payload': {'selected_option_id': 'A'}}))
    assert result['mastery_eligible'] is False
    assert result['evidence_exclusion_reason'] == 'knowledge_binding_requires_measurement_review'


@pytest.mark.parametrize('failed', [False, True])
def test_provider_is_bounded_and_closed_even_on_failure(monkeypatch, failed):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import ai_base
    from question_bank_knowledge import match_questions

    call = AsyncMock(return_value=json.dumps({'bindings': []}), side_effect=RuntimeError('offline') if failed else None)
    close = AsyncMock()
    monkeypatch.setattr(ai_base, 'AIBase', lambda: SimpleNamespace(_call_llm=call, client=SimpleNamespace(close=close)))
    if failed:
        with pytest.raises(RuntimeError):
            asyncio.run(match_questions(bank()['items'], course()['course_knowledge_base']['knowledge_points']))
    else:
        assert asyncio.run(match_questions(bank()['items'], course()['course_knowledge_base']['knowledge_points'])) == []
    assert call.call_args.kwargs['max_attempts'] == 1
    assert call.call_args.kwargs['request_timeout_seconds'] == 45
    close.assert_awaited_once()


def test_pending_retry_is_explicit_and_scoped():
    async def uncertain(items, points):
        return [{'revision_id': i['revision_id'], 'knowledge_ids': [], 'confidence': 0} for i in items]
    pending = asyncio.run(bind_questions(course(), bank(), matcher=uncertain))
    assert asyncio.run(bind_questions(course(), pending, matcher=match)) == pending
    revision = pending['items'][0]['revision_id']
    fixed = asyncio.run(bind_questions(course(), pending, matcher=match, retry_pending=True, revision_ids=[revision]))
    assert binding_view(course(), fixed)['counts']['bound'] == 1
    with pytest.raises(ValueError):
        asyncio.run(bind_questions(course(), fixed, matcher=match, revision_ids=['r1']))


def test_retargeting_generated_atomic_question_requires_new_review():
    original = bank()
    original['items'][0].update(assessment_binding_schema='atomic_assessment_v1',
        primary_knowledge_ids=['k1'], course_knowledge_refs=['k1'], knowledge_revision_refs={'k1': 'kr1'}, knowledge_baseline_revision='tree1')
    updated = asyncio.run(bind_questions(course(), original, mode='manual', revision_id='r1', knowledge_ids=['k2']))
    assert updated['items'][0]['lifecycle_status'] == 'needs_review'
    assert updated['items'][0]['primary_knowledge_ids'] == ['k2']


def test_auto_out_of_tree_lecture_stays_pending_without_provider_call():
    current = course()
    current['nodes'] = [{'node_id': 'n1'}, {'node_id': 'n2'}]
    original = bank()
    original['items'][0]['node_id'] = 'n2'
    async def unexpected(*args):
        pytest.fail('Questions outside the adopted knowledge scope must not call the provider')
    updated = asyncio.run(bind_questions(current, original, matcher=unexpected))
    assert binding_view(current, updated)['counts']['pending'] == 1


def test_auto_scopes_legacy_child_node_to_its_lecture_atoms():
    current = course()
    current['nodes'] = [{'node_id': 'lecture'}, {'node_id': 'n1', 'parent_node_id': 'lecture'}, {'node_id': 'other'}]
    current['course_knowledge_base']['knowledge_points'][0]['section_refs'] = ['lecture']
    current['course_knowledge_base']['knowledge_points'][1]['section_refs'] = ['other']
    async def scoped(items, points):
        assert [p['knowledge_id'] for p in points] == ['k1']
        return [{'revision_id': 'r1', 'knowledge_ids': ['k1'], 'confidence': .95, 'reason': '直接检查整除', 'evidence': '-7 / 2'}]
    updated = asyncio.run(bind_questions(current, bank(), matcher=scoped))
    assert binding_view(current, updated)['counts']['bound'] == 1
