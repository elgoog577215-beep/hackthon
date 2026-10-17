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


def test_named_concept_does_not_inherit_incidental_operation_names():
    from knowledge_evidence import enrich_point
    point = {'knowledge_id': 'lifo', 'revision_id': 'unchanged', 'name': '栈的LIFO存取规则',
        'statement': '最后进入栈的元素最先离开。', 'source_quotes': [{'evidence_id': 'e',
            'quote': '**栈（Stack）**采用**后进先出（Last In, First Out, LIFO）**。**入栈（Push）**插入元素。'}]}
    result = enrich_point(point)
    assert 'LIFO' in result['aliases'] and 'Stack' in result['aliases']
    assert 'Push' not in result['aliases']


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


def test_terminology_and_extraction_labels_do_not_change_semantic_identity(svc):
    source(svc)
    from knowledge_first import course_generation_context
    raw = svc.repository.load_raw('c-pilot'); ctx = course_generation_context(raw)
    original = compile_tree(raw, ctx, response())['knowledge_points'][0]
    payload = response()
    payload['points'][0].update(extraction_method='summary', terms=[{
        'name': 'CPU', 'english_name': 'CPU', 'source_key': 'S1', 'quote': 'CPU执行指令。'}])
    updated = compile_tree(raw, ctx, payload)['knowledge_points'][0]
    assert updated['knowledge_id'] == original['knowledge_id']
    assert updated['revision_id'] == original['revision_id']
    assert updated['extraction_method'] == 'summary'
    assert 'CPU' in updated['aliases']


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


def test_source_can_locate_an_owner_candidate_without_adopting_it(svc):
    tree = saved_source(svc)
    candidate = deepcopy(tree); candidate['revision_id'] = 'candidate-version'
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation', request_id='candidate')
    svc.authoring.update_job('c-pilot', job['id'], status='completed', checkpoint={'candidate': candidate})
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'candidate-version', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert data['available'] and data['content'] == QUOTE
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']['revision_id'] == 'tree-old'


def test_source_can_locate_a_retained_historical_tree(svc):
    saved_source(svc)
    def change_baseline(raw):
        raw['course_knowledge_base']['revision_id'] = 'tree-new'
        return raw
    svc.storage.update_course_data('c-pilot', change_baseline)
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert data['available'] and data['handout_ref']['script_revision_id'] == 'old'


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


def test_mismatched_source_block_is_not_presented_as_the_original(svc):
    saved_source(svc)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '被改变的内容'
    svc.authoring._save(state)
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert not data['available'] and data['reason'] == 'source_quote_mismatch'
    assert data['quote'] == QUOTE and data['content'] == ''


def test_material_source_uses_frozen_passage_with_its_page_locator(svc):
    saved_source(svc)
    def material_point(raw):
        quote = raw['course_knowledge_base']['knowledge_points'][0]['source_quotes'][0]
        quote.pop('handout_ref'); quote.update(source_kind='provided_material', locator={'page': 7})
        return raw
    svc.storage.update_course_data('c-pilot', material_point)
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation', request_id='snapshot')
    svc.authoring.update_job('c-pilot', job['id'], status='failed', request_snapshot={'knowledge_generation_context': {
        'evidence_package': {'units': [{'evidence_id': 'ev-old', 'source_text': '资料上下文：' + QUOTE}]}}})
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert data['available'] and data['source_kind'] == 'provided_material'
    assert data['locator']['page'] == 7
    assert data['content'].startswith('资料上下文：')


def split_handout_source(svc):
    from material_evidence import _split_source
    tree = saved_source(svc)
    source = tree['knowledge_points'][0]['source_quotes'][0]
    content = ('背景说明。\n    ' * 200) + QUOTE
    quote = _split_source(content)[0]
    assert quote not in content
    def bind(raw):
        raw['course_knowledge_base']['knowledge_points'][0]['source_quotes'][0]['quote'] = quote
        return raw
    svc.storage.update_course_data('c-pilot', bind)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = content
    svc.authoring._save(state)
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation', request_id='split-snapshot')
    svc.authoring.update_job('c-pilot', job['id'], status='completed', request_snapshot={'knowledge_generation_context': {
        'handout_source_refs': {'hs-test': source['handout_ref']},
        'evidence_package': {'units': [{'evidence_id': 'ev-old', 'block_ids': ['hs-test'], 'source_text': quote}]}}})
    return content, quote, job['id']


def test_frozen_split_quote_can_open_same_original_block_without_claiming_exact_offsets(svc):
    content, quote, _ = split_handout_source(svc)
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert data['available'] and data['content'] == content and data['quote'] == quote
    assert data['quote_match'] == 'frozen_split_passage' and 'quote_start' not in data


@pytest.mark.parametrize('change', ['text', 'reference'])
def test_split_quote_never_hides_changed_content_or_unbound_block(svc, change):
    _, _, job_id = split_handout_source(svc)
    state = svc.authoring.load('c-pilot')
    if change == 'text':
        state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '内容已改变'
    else:
        state['jobs'][job_id]['request_snapshot']['knowledge_generation_context']['handout_source_refs']['hs-test']['block_id'] = 'other-block'
    svc.authoring._save(state)
    data = client_for(svc).get('/api/courses/c-pilot/knowledge-first/source', headers={'X-User-Id': 'owner'},
        params={'tree_revision': 'tree-old', 'knowledge_id': 'keep-id', 'evidence_id': 'ev-old'}).json()
    assert not data['available'] and data['reason'] == 'source_quote_mismatch' and data['content'] == ''


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
