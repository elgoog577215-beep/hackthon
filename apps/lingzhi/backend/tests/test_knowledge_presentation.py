"""Short navigation labels must never move the referenced knowledge baseline."""
from copy import deepcopy
import json

import pytest

from backend.tests.test_knowledge_first import svc
from course_repository import CourseDocumentConflict


def tree():
    return {'revision_id': 'kb-old', 'tree_schema': 'knowledge_first_generic_v1', 'status': 'accepted',
            'knowledge_points': [{'knowledge_id': 'k1', 'revision_id': 'kr-old',
                'name': '若函数在一点可导且导数非零，法线斜率为导数的负倒数',
                'statement': "若 $f'(a)\\ne0$，法线斜率为 $-1/f'(a)$。",
                'conditions': ['函数在该点可导', '导数非零'], 'knowledge_type': 'rule',
                'granularity_status': 'candidate', 'aliases': ['法线倾斜程度'],
                'kc_skill_profile': {'knowledge_id': 'k1', 'knowledge_revision': 'kr-old'}}]}


def seed(svc):
    svc.storage.update_course_data('c-pilot', lambda raw: {**raw, 'course_knowledge_base': tree()})


def save(svc, **overrides):
    raw = svc.repository.load_raw('c-pilot')
    args = dict(actor='owner', command_id='rename-1', expected_document=raw['course_document_revision'],
                expected_knowledge='kb-old', expected_presentation='', tree_revision='kb-old',
                labels=[{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '法线斜率'}])
    args.update(overrides)
    return svc.update_presentation('c-pilot', **args)


def test_new_generation_names_are_titles_not_full_sentences():
    from knowledge_registry_contract import names_prompt
    prompt = names_prompt([{'key': 'P1', **tree()['knowledge_points'][0]}])
    payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1])
    assert payload['naming_contract'] == 'knowledge_names_v2'
    assert payload['name_style'] == 'short_title'
    assert '不要问句' in prompt and '不要把完整知识陈述搬到名称' in prompt
    assert '不要问句、栏目名或“某某的定义”' not in prompt
    assert payload['points'][0]['statement'] == tree()['knowledge_points'][0]['statement']


def test_presentation_preserves_baseline_point_facts_profiles_and_question_binding(svc):
    from knowledge_presentation import present_tree
    from question_bank_knowledge import binding_view
    from handout_knowledge import knowledge_facts, lesson_fingerprint
    seed(svc)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    result = save(svc)
    after = svc.repository.load_raw('c-pilot')
    assert after['course_knowledge_base'] == before['course_knowledge_base']
    assert after['course_document_revision'] == before['course_document_revision']
    shown = present_tree(after['course_knowledge_base'], after['knowledge_presentation'])
    assert shown['knowledge_points'][0]['display_name'] == '法线斜率'
    assert shown['revision_id'] == 'kb-old'
    assert knowledge_facts(shown['knowledge_points'][0]) == knowledge_facts(tree()['knowledge_points'][0])
    assert lesson_fingerprint(shown, 'L1') == lesson_fingerprint(tree(), 'L1')
    assert shown['knowledge_points'][0]['kc_skill_profile'] == tree()['knowledge_points'][0]['kc_skill_profile']
    question = {'revision_id': 'q1', 'knowledge_binding': {'status': 'bound', 'knowledge_ids': ['k1'],
        'knowledge_revision_refs': {'k1': 'kr-old'}, 'knowledge_baseline_revision': 'kb-old'}}
    assert binding_view({**after, 'course_knowledge_base': shown}, {'items': [question]})['counts']['bound'] == 1
    assert result['presentation_revision'] == after['knowledge_presentation']['revision_id']
    assert save(svc) == result  # a lost HTTP response can be retried


@pytest.mark.parametrize('override', [
    {'actor': 'other'}, {'expected_document': 'stale'}, {'expected_knowledge': 'stale'},
    {'expected_presentation': 'stale'}, {'tree_revision': 'missing'},
    {'labels': [{'knowledge_id': 'unknown', 'knowledge_revision': 'kr-old', 'name': '名字'}]},
    {'labels': [{'knowledge_id': 'k1', 'knowledge_revision': 'stale', 'name': '名字'}]},
    {'labels': [{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '  '}]},
    {'labels': [{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '名字', 'statement': '改正文'}]},
    {'labels': [{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '甲'},
                {'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '乙'}]},
    {'labels': []},
])
def test_invalid_or_stale_presentation_writes_nothing(svc, override):
    seed(svc)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    with pytest.raises(CourseDocumentConflict):
        save(svc, **override)
    assert svc.repository.load_raw('c-pilot') == before


def test_candidates_are_decorated_without_rewriting_the_saved_job(svc):
    seed(svc)
    candidate = tree(); candidate.update(revision_id='candidate', status='candidate')
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation', request_id='candidate')
    svc.authoring.update_job('c-pilot', job['id'], status='completed', checkpoint={'candidate': candidate})
    before = deepcopy(svc.authoring.load('c-pilot'))
    save(svc, tree_revision='candidate')
    view = svc.view('c-pilot', source_mode='handouts')
    assert view['candidate']['knowledge_points'][0]['display_name'] == '法线斜率'
    assert view['tree']['knowledge_points'][0]['display_name'] == '法线斜率'
    assert svc.authoring.load('c-pilot') == before
    # Semantic edits cannot inherit a label proposed for another revision.
    from knowledge_presentation import present_tree
    candidate['knowledge_points'][0]['revision_id'] = 'new-meaning'
    assert 'display_name' not in present_tree(candidate, svc.repository.load_raw('c-pilot')['knowledge_presentation'])['knowledge_points'][0]


def test_active_course_and_reused_command_conflicts_are_protected(svc):
    seed(svc)
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation', request_id='active')
    with pytest.raises(CourseDocumentConflict, match='任务'):
        save(svc)
    svc.authoring.update_job('c-pilot', job['id'], status='cancelled')
    save(svc)
    with pytest.raises(CourseDocumentConflict, match='标识'):
        save(svc, labels=[{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '另一个名字'}])


def test_second_label_edit_is_versioned_and_retains_search_aliases(svc):
    from knowledge_presentation import present_tree
    seed(svc)
    first = save(svc)
    second = save(svc, command_id='rename-2', expected_presentation=first['presentation_revision'],
                  labels=[{'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '非零导数处的法线斜率'}])
    assert first['presentation_revision'] != second['presentation_revision']
    shown = present_tree(tree(), svc.repository.load_raw('c-pilot')['knowledge_presentation'])
    assert shown['knowledge_points'][0]['display_aliases'] == ['法线斜率']
    assert tree()['knowledge_points'][0]['aliases'] == ['法线倾斜程度']


def test_api_owner_boundary_and_strict_payload(svc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
    from routers.knowledge_first import router
    seed(svc)
    app = FastAPI(); app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    body = dict(command_id='api-1', document_revision=svc.repository.load_raw('c-pilot')['course_document_revision'],
                knowledge_revision='kb-old', tree_revision='kb-old', labels=[{
                    'knowledge_id': 'k1', 'knowledge_revision': 'kr-old', 'name': '法线斜率'}])
    with TestClient(app) as client:
        url = '/api/courses/c-pilot/knowledge-first/presentation'
        assert client.post(url, json=body, headers={'X-User-Id': 'other'}).status_code == 404
        assert client.post(url, json={**body, 'statement': '改正文'}, headers={'X-User-Id': 'owner'}).status_code == 422
        assert client.post(url, json=body, headers={'X-User-Id': 'owner'}).status_code == 200
        assert client.post(url, json={**body, 'command_id': 'api-2'}, headers={'X-User-Id': 'owner'}).status_code == 409


def test_title_changes_invalidate_observation_but_not_semantic_baseline(svc):
    seed(svc)
    svc.storage.update_course_data('c-pilot', lambda raw: {**raw, 'authoring_surface': 'student'})
    before = svc.status('c-pilot')
    save(svc)
    after = svc.status('c-pilot')
    assert before['result_version'] != after['result_version']
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']['revision_id'] == 'kb-old'
