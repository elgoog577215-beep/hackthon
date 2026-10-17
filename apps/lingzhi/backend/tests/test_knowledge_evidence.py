import json
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts, answer
from backend.tests.test_generic_knowledge_first import response, source
from course_repository import CourseDocumentConflict
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from generic_knowledge import compile_tree
from handout_knowledge import handout_context
from routers.knowledge_first import router


QUOTE = '**潜在函数（Potential Function, PF）**也称**势函数（Potential Function）**，将状态映射到实数。另有队列（Queue）。'


def saved_source(svc):
    state = svc.authoring.load('c-pilot')
    state['lessons'] = {'cpu': {'lesson_unit_id': 'cpu', 'title': '处理器', 'working_script_revision_id': 'new',
        'script_revisions': [
            {'revision_id': 'old', 'sections': [{'section_node_id': 'sec', 'blocks': [{'block_id': 'block', 'content': QUOTE}]}]},
            {'revision_id': 'new', 'sections': [{'section_node_id': 'sec', 'blocks': [{'block_id': 'block', 'content': '已经更新的新讲义。'}]}]},
        ]}}
    svc.authoring._save(state)
    point = {'knowledge_id': 'keep-id', 'revision_id': 'keep-revision', 'key': 'K1', 'name': '势函数定义',
        'statement': '势函数将状态映射到实数。', 'conditions': [], 'parent_id': 'c', 'section_refs': ['cpu'],
        'aliases': ['原有手工别名'], 'source_refs': ['ev-old'], 'source_quotes': [
            {'evidence_id': 'ev-old', 'quote': QUOTE, 'source_kind': 'canonical_handout_block',
             'handout_ref': {'lesson_id': 'cpu', 'script_revision_id': 'old', 'section_id': 'sec', 'block_id': 'block'},
             'locator': {'section_path': ['cpu']}}]}
    tree = {'revision_id': 'tree-old', 'source_mode': 'handouts', 'categories': [{'id': 'c', 'name': '分析方法', 'parent_id': None}],
        'knowledge_points': [point], 'relations': [], 'lessons': [{'topic': 'cpu', 'title': '处理器'}]}
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'course_knowledge_base': tree, 'knowledge_first_history': {'tree-old': tree}})
    return tree


def client_for(svc):
    app = FastAPI(); app.include_router(router, prefix='/api')
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    return TestClient(app)


def test_legacy_read_projects_source_terms_without_changing_identity_or_files(svc):
    saved_source(svc)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    stored = svc.authoring._path('c-pilot').read_bytes()
    view = svc.view('c-pilot', source_mode='handouts')
    point = view['tree']['knowledge_points'][0]
    assert point['knowledge_id'] == 'keep-id' and point['revision_id'] == 'keep-revision'
    assert point['terms'][0]['english_name'] == 'Potential Function'
    assert {'PF', '潜在函数', '原有手工别名'} <= set(point['aliases'])
    assert 'Queue' not in point['aliases']
    assert point['terms'][0]['evidence_refs'][0]['evidence_id'] == 'ev-old'
    assert svc.repository.load_raw('c-pilot') == before
    assert svc.authoring._path('c-pilot').read_bytes() == stored


def test_exact_excerpt_is_checked_and_legacy_source_keys_still_work(svc):
    handouts(svc)
    raw = svc.repository.load_raw('c-pilot'); ctx = handout_context(raw, svc.authoring.load('c-pilot'))
    old = compile_tree(raw, ctx, answer())
    payload = answer(); payload['points'][0]['sources'][0]['quote'] = 'CPU执行指令'
    new = compile_tree(raw, ctx, payload)
    a = old['knowledge_points'][0]; b = new['knowledge_points'][0]
    assert a['knowledge_id'] == b['knowledge_id']
    assert b['source_quotes'][0]['quote'] == 'CPU执行指令'
    assert b['source_quotes'][0]['quote_scope'] == 'exact_excerpt'
    assert a['source_quotes'][0]['quote_scope'] == 'source_passage'
    payload['points'][0]['sources'][0]['quote'] = '主存保存数据，CPU不执行指令'
    with pytest.raises(CourseDocumentConflict, match='引文'):
        compile_tree(raw, ctx, payload)


def test_unsupported_english_is_a_candidate_and_does_not_become_a_search_alias(svc):
    source(svc)
    from knowledge_first import course_generation_context
    raw = svc.repository.load_raw('c-pilot'); ctx = course_generation_context(raw)
    payload = response()
    payload['points'][0]['terms'] = [{'name': 'CPU作用', 'english_name': 'Invented Processing Device',
        'source_key': 'S1', 'quote': 'CPU执行指令。', 'aliases': ['虚构译名']}]
    point = compile_tree(raw, ctx, payload)['knowledge_points'][0]
    assert 'Invented Processing Device' not in point['aliases']
    assert point['term_candidates'][0]['english_name'] == 'Invented Processing Device'
    assert point['term_candidates'][0]['status'] == 'source_unconfirmed'


def test_source_endpoint_locates_frozen_handout_instead_of_current_version(svc):
    saved_source(svc)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    client = client_for(svc)
    result = client.get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'})
    assert result.status_code == 200
    data = result.json()
    assert data['available'] is True and data['content'] == QUOTE
    assert data['handout_ref']['script_revision_id'] == 'old'
    assert data['source_kind'] == 'generated_handout'
    assert data['quote_start'] == 0
    assert svc.repository.load_raw('c-pilot') == before


def test_missing_old_revision_retains_quote_snapshot_and_never_uses_new_text(svc):
    saved_source(svc)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'].pop(0); svc.authoring._save(state)
    result = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'})
    assert result.status_code == 200
    data = result.json()
    assert data['available'] is False and data['reason'] == 'source_revision_missing'
    assert data['quote'] == QUOTE
    assert '已经更新的新讲义' not in json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize('field,value', [('tree_revision', 'foreign'), ('knowledge_id', 'foreign'), ('evidence_id', 'foreign')])
def test_source_endpoint_rejects_unbound_identifiers(svc, field, value):
    saved_source(svc)
    query = {'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old', field: value}
    assert client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', params=query,
        headers={'X-User-Id': 'owner'}).status_code == 404


def test_public_readers_cannot_fetch_private_source_versions(svc):
    saved_source(svc)
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'is_published': True})
    client = client_for(svc)
    query = {'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}
    assert client.get('/api/courses/c-pilot/knowledge-first/source', params=query, headers={'X-User-Id': 'foreign'}).status_code == 404
