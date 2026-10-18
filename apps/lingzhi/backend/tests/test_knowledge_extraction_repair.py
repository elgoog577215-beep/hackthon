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
async def test_extraction_repair_is_bounded_to_one_request_and_preserves_failure(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = []
    async def model(prompt, **kwargs):
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
