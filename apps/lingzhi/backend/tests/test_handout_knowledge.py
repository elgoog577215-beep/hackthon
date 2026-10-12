"""The ordinary handout pipeline can supply a tree without uploaded files."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_generic_knowledge_first import response, source
from course_repository import CourseDocumentConflict


def handouts(svc):
    state = svc.authoring.load('c-pilot')
    state['lessons'] = {lid: {'lesson_unit_id': lid, 'title': title,
        'working_script_revision_id': 'r-' + lid, 'script_revisions': [{
            'revision_id': 'r-' + lid, 'sections': [{'section_node_id': lid,
            'blocks': [{'block_id': 'b-' + lid, 'content': content, 'status': 'completed'}]}]}]}
        for lid, title, content in [('cpu', '处理器', 'CPU执行指令。'), ('memory', '存储器', '主存保存正在使用的数据。')]}
    svc.authoring._save(state)


def answer():
    value = response()
    value['points'][1]['sources'][0]['key'] = 'S2'
    value['lessons'][0]['key'] = 'cpu'
    value['lessons'][1]['key'] = 'memory'
    return value


@pytest.mark.asyncio
async def test_no_upload_extracts_from_existing_handouts_without_rewriting_them(svc, monkeypatch):
    monkeypatch.setattr('knowledge_first.material', lambda: pytest.fail('C17 seed was accessed'))
    handouts(svc)
    before = deepcopy(svc.authoring.load('c-pilot')['lessons'])
    document = deepcopy(svc.repository.load_raw('c-pilot')['course_document'])
    async def call(prompt, **kwargs):
        assert 'CPU执行指令。' in prompt and '主存保存正在使用的数据。' in prompt
        assert kwargs['max_attempts'] == 1
        return json.dumps(answer(), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    v = svc.view('c-pilot', source_mode='handouts')
    assert v['source_mode'] == 'handouts' and v['can_generate_tree']
    job, _ = svc.start('c-pilot', 'tree', 'derived', '', v['document_revision'], source_mode='handouts')
    await svc.run('c-pilot', job['id'])
    assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status'] == 'completed'
    svc.adopt('c-pilot', job['id'], '', v['document_revision'])
    raw = svc.repository.load_raw('c-pilot')
    tree = raw['course_knowledge_base']
    assert tree['source_mode'] == 'handouts'
    assert tree['knowledge_points'][0]['section_refs'] == ['cpu']
    assert tree['knowledge_points'][0]['source_quotes'][0]['handout_ref']['script_revision_id'] == 'r-cpu'
    assert raw['course_document'] == document
    assert svc.authoring.load('c-pilot')['lessons'] == before


def test_without_handouts_gives_next_step_and_blocks_model(svc):
    v = svc.view('c-pilot', source_mode='handouts')
    assert not v['can_generate_tree']
    with pytest.raises(CourseDocumentConflict, match='讲义'):
        svc.start('c-pilot', 'tree', 'empty', '', v['document_revision'], source_mode='handouts')


@pytest.mark.asyncio
async def test_handout_changes_invalidate_candidate_adoption(svc):
    handouts(svc)
    async def call(*args, **kwargs): return json.dumps(answer(), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    v = svc.view('c-pilot', source_mode='handouts')
    job, _ = svc.start('c-pilot', 'tree', 'stale', '', v['document_revision'], source_mode='handouts')
    await svc.run('c-pilot', job['id'])
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] += '正文已修改。'
    svc.authoring._save(state)
    with pytest.raises(CourseDocumentConflict, match='变化'):
        svc.adopt('c-pilot', job['id'], '', v['document_revision'])


def test_recursive_categories_preserve_point_identity_and_reject_cycles(svc):
    from generic_knowledge import compile_tree
    from knowledge_first import course_generation_context
    source(svc); svc.initialize('c-pilot', svc.view('c-pilot')['document_revision'])
    raw = svc.repository.load_raw('c-pilot'); context = course_generation_context(raw)
    shallow = compile_tree(raw, context, response())
    deep = response()
    deep['categories'] += [{'key': 'C3', 'name': '部件职责', 'parent_key': 'C2'},
                           {'key': 'C4', 'name': '执行职责', 'parent_key': 'C3'}]
    deep['points'][0]['category_key'] = 'C4'
    tree = compile_tree(raw, context, deep)
    assert tree['knowledge_points'][0]['knowledge_id'] == shallow['knowledge_points'][0]['knowledge_id']
    deep['categories'][0]['parent_key'] = 'C4'
    with pytest.raises(CourseDocumentConflict, match='环'):
        compile_tree(raw, context, deep)
