import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from course_repository import CourseDocumentConflict


def point(subject='入栈', **extra):
    return {'form': 'fact', 'subject': subject, 'property': '操作效果', 'value': '将元素插入栈顶', 'conditions': [], 'attachments': [], **extra}


def value(points):
    return {'response_contract': 'knowledge_extract_v9', 'passages': {'S1.1': {'points': points, 'note': None}}, 'source_issues': []}


def test_small_repair_schema_enforces_the_exact_field_that_failed():
    from jsonschema import Draft202012Validator
    from knowledge_extraction_repair import repair_schema
    targets = {'S1.1:0': {'point': point(property='效果和端点'), 'passage_key': 'S1.1'}}
    validator = Draft202012Validator(repair_schema(targets, {'S1.1': '入栈将元素插入栈顶。出栈移除元素。'}))
    result = {'repairs': {'S1.1:0': {'points': [point()], 'handling': 'replace', 'reason': '修正属性'}}, 'source_issues': []}
    assert validator.is_valid(result)
    result['repairs']['S1.1:0']['points'][0]['property'] = '效果和端点'
    assert not validator.is_valid(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('out_of_scope', [False, True])
async def test_one_scoped_repair_preserves_valid_points_and_original_response(svc, monkeypatch, out_of_scope):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(), point('出栈', property='效果和端点')]); before = deepcopy(original)
    calls = []
    async def call(*args):
        calls.append(args[-1])
        return json.dumps({'repairs': {'S1.1:0' if out_of_scope else 'S1.1:1': {
            'points': [point('出栈', value='移除并返回栈顶元素')], 'handling': 'replace', 'reason': '仅保留一个操作效果属性'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if out_of_scope:
        with pytest.raises(CourseDocumentConflict): await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    else:
        record = {}
        corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, record)
        assert corrected['passages']['S1.1']['points'][0] == original['passages']['S1.1']['points'][0]
        assert record['target_keys'] == ['S1.1:1'] and record['raw_response']
        assert corrected['passages']['S1.1']['points'][1]['property'] == '操作效果'
    assert calls == ['extract_repair'] and original == before


@pytest.mark.asyncio
async def test_unaffected_context_note_is_not_overwritten_by_point_repair(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    passages = [{'key': 'S1.1', 'source_key': 'S1', 'text': '入栈将元素插入栈顶。', 'start': 0, 'end': 10},
                {'key': 'S2.1', 'source_key': 'S2', 'text': '本讲学习目标。', 'start': 0, 'end': 7}]
    monkeypatch.setattr('knowledge_extraction_repair.passage_catalog', lambda *args: deepcopy(passages))
    monkeypatch.setattr('knowledge_semantic_contract.passage_catalog', lambda *args: deepcopy(passages))
    original = value([point(property='效果和端点')])
    note = {'points': [], 'note': {'handling': 'context', 'reason': '仅为教学目标，不是知识命题'}}
    original['passages']['S2.1'] = deepcopy(note)
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:0': {'points': [point()], 'handling': 'replace', 'reason': '只改属性'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1', 'S2'], 1, original, {})
    assert corrected['passages']['S2.1'] == note


@pytest.mark.asyncio
async def test_extraction_repair_is_bounded_to_one_request_and_preserves_failure(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = []; options = []
    async def model(prompt, **kwargs):
        options.append(kwargs)
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'extract': return json.dumps(value([point(property='效果和端点')]))
        return json.dumps({'repairs': {'S1.1:0': {'points': [point(property='仍然和无效')], 'handling': 'replace', 'reason': '修复失败'}}, 'source_issues': []})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1')
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed' and calls == ['extract', 'extract_repair']
    batch = saved['checkpoint']['atomic_pipeline']['inventory_batches'][0]
    assert batch['raw_response'] and batch['repair']['raw_response']
    assert batch['repair']['status'] == 'failed'
    assert 'json_schema' not in options[1]  # Validate the small contract locally too.


@pytest.mark.asyncio
async def test_ambiguous_repeated_question_is_repaired_without_rewriting_other_points(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] += '栈的判空检查栈是否为空。队列的判空检查队列是否为空。'
    svc.authoring._save(state)
    calls = []
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'extract':
            return json.dumps(value([point('判空', property='检查对象', value='栈是否为空'), point('判空', property='检查对象', value='队列是否为空')]))
        return json.dumps({'repairs': {f'S1.1:{i}': {'points': [point(subject, property='判空检查对象', value=subject+'是否为空')],
                    'handling': 'replace', 'reason': '明确操作所属结构'} for i, subject in enumerate(['栈', '队列'])}, 'source_issues': []})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert calls == ['extract', 'extract_repair'] and saved['status'] == 'completed'
    points = saved['checkpoint']['candidate']['knowledge_points']
    assert len({p['meta_question'] for p in points}) == 2


@pytest.mark.asyncio
async def test_exact_duplicate_claims_keep_one_identity_and_all_inventory_pointers(svc, monkeypatch):
    from backend.tests.test_knowledge_atomic import provider
    from knowledge_atomic import assemble
    setup_course(svc, monkeypatch); provider(svc)
    job = start(svc); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    pipeline = deepcopy(saved['checkpoint']['atomic_pipeline'])
    pipeline['prompt_contract'] = 'knowledge_extract_v9'
    copied = deepcopy(pipeline['batches'][0]); copied['id'] = 'duplicate-batch'
    copied['tree']['knowledge_points'][0]['inventory_keys'] = ['another-inventory-pointer']
    pipeline['batches'].append(copied)
    before = deepcopy(pipeline)
    result = assemble(svc.repository.load_raw('c-pilot'), saved['request_snapshot']['knowledge_generation_context'], pipeline)
    assert len(result['knowledge_points']) == 2
    assert len(result['atomic_assessment']['exact_duplicate_consolidations']) == 1
    assert 'another-inventory-pointer' in result['knowledge_points'][0]['inventory_keys']
    assert pipeline == before
