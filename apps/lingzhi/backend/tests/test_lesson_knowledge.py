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
    return data


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
        await svc.run('c-pilot', job['id'])
        assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status'] == 'completed'
        svc.adopt('c-pilot', job['id'], v['knowledge_revision'], v['document_revision'])
        saved.append(deepcopy(svc.repository.load_raw('c-pilot')['course_knowledge_base']))
    assert '主存保存正在使用的数据。' not in prompts[0]
    assert 'CPU执行指令。' not in prompts[1]
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
async def test_next_lesson_references_existing_ids_and_can_reuse_without_duplicating(svc):
    handouts(svc)
    calls = []
    async def call(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1: return json.dumps(one_lesson_response('cpu'), ensure_ascii=False)
        assert 'existing_knowledge' in prompt and 'E1' in prompt and 'CPU执行指令。' in prompt
        value = one_lesson_response('memory')
        value['points'].append({'key': 'K1', 'reuse_key': 'E1', 'category_key': 'C2', 'sources': [{'key': 'S1'}]})
        value['lessons'][0]['knowledge_keys'].append('K1')
        value['relations'] = [{'source_key': 'E1', 'target_key': 'K2', 'type': 'prerequisite', 'reason': '处理器使用主存中的数据', 'conditions': []}]
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
    assert tree['relations'][0]['source_id'] == original['knowledge_id']
    assert tree['relations'][0]['cross_lesson'] is True
