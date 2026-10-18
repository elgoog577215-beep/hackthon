import json
from copy import deepcopy

import pytest
from jsonschema import validate

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_tree_relations import fake_provider
from course_repository import CourseDocumentConflict


def response(point):
    return {'response_contract': 'knowledge_extract_v9', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}


def test_new_form_uses_only_its_own_fields_and_keeps_operation_question(svc, monkeypatch):
    from knowledge_extract import compile_extraction, extraction_schema
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    point = {'form': 'fact', 'subject': '入栈', 'property': '操作效果', 'value': '将元素插入栈顶', 'conditions': [], 'attachments': []}
    value = response(point)
    validate(value, extraction_schema(['S1.1'], {'S1.1': ['入栈']}, contract='knowledge_extract_v9'))
    result = compile_extraction(raw, context, ['S1'], 1, value)
    compiled = result['tree']['knowledge_points'][0]
    assert compiled['meta_question'] == '入栈的操作效果是什么？'
    assert compiled['atomic_contract']['schema_version'] == 'knowledge_extract_v9'
    assert value == response(point)
    invalid = deepcopy(value); invalid['passages']['S1.1']['points'][0]['other_subject'] = '出栈'
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, invalid)


def test_new_extraction_does_not_cut_a_method_or_code_block_at_600_chars(monkeypatch):
    from knowledge_extract import extraction_prompt
    content = '**完整方法**\n' + '操作说明。' * 130 + '\n```python\ndef scan(s):\n    return bool(s)\n```'
    monkeypatch.setattr('knowledge_compact.sources', lambda context: {'S1': {'source_text': content}})
    prompt = extraction_prompt({'course_name': '示例'}, {'scope_lesson_id': 'L1'}, ['S1'], contract='knowledge_extract_v9')
    payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1])
    assert len(payload['source_passages']) == 1
    passage = payload['source_passages'][0]
    assert passage['text'] == content and passage['end'] == len(content)


def test_literal_subject_is_bound_to_source_instead_of_incomplete_token_hints(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    monkeypatch.setattr('knowledge_semantic_contract.subject_options', lambda *a, **k: ['入栈', '出栈'])
    point = {'form': 'fact', 'subject': '栈顶元素', 'property': '返回时机', 'value': '出栈时', 'conditions': [], 'attachments': []}
    result = compile_extraction(raw, context, ['S1'], 1, response(point))
    assert result['tree']['knowledge_points'][0]['meta_question'] == '栈顶元素的返回时机是什么？'
    point['subject'] = '虚构元素'
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, response(point))


@pytest.mark.asyncio
async def test_knowledge_requests_pin_sampling_but_keep_single_attempt(svc, monkeypatch):
    setup_course(svc, monkeypatch); calls = fake_provider(svc)
    original_factory = svc.provider_factory
    recorded = []
    def factory():
        p = original_factory(); original = p._call_llm
        async def call(*args, **kwargs):
            recorded.append(kwargs)
            return await original(*args, **kwargs)
        p._call_llm = call
        return p
    svc.provider_factory = factory
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True, include_relations=True)
    await svc.run('c-pilot', job['id'])
    assert recorded
    assert all(k.get('temperature') == 0 and k['max_attempts'] == 1 for k in recorded)
