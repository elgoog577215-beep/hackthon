from copy import deepcopy

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course
from course_repository import CourseDocumentConflict


def response():
    return {'response_contract': 'knowledge_extract_v1', 'points': [
        {'name': '入栈', 'kind': 'rule', 'claim': '入栈将元素插入栈顶。', 'focus_term': '入栈',
         'conditions': [], 'question': '入栈执行什么操作？', 'source_passage_keys': ['S1.1'], 'attachments': []},
        {'name': '出栈', 'kind': 'rule', 'claim': '出栈移除并返回栈顶元素。', 'focus_term': '出栈',
         'conditions': [], 'question': '出栈执行什么操作？', 'source_passage_keys': ['S1.1'], 'attachments': []}],
        'unassigned_passages': [], 'source_issues': []}


def test_single_pass_compiles_existing_coverage_and_question_guards(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    value = response(); before = deepcopy(value)
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert len(result['tree']['knowledge_points']) == len(result['items']) == 2
    assert result['report']['ready_for_adoption'] is True
    assert result['source_coverage'][0]['uncovered_passage_keys'] == []
    assert all(p['meta_answer'] == p['statement'] for p in result['tree']['knowledge_points'])
    assert value == before
    value['points'][0]['question'] = '出栈执行什么操作？'
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert not result['report']['ready_for_adoption']
    assert any(i['code'] == 'question_focus_missing' for i in result['report']['issues'])


def test_single_pass_rejects_unknown_sources(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    value = response(); value['points'][0]['source_passage_keys'] = ['S99.1']
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, value)


@pytest.mark.asyncio
async def test_single_pass_job_calls_extraction_and_whole_hierarchy_only(svc, monkeypatch):
    import json
    from types import SimpleNamespace
    from backend.tests.test_knowledge_atomic import start
    from knowledge_hierarchy import CONTRACT
    setup_course(svc, monkeypatch); calls = []
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data['stage'])
        result = response() if data['stage'] == 'extract' else {
            'response_contract': CONTRACT, 'categories': [{'key': 'C1', 'name': '栈操作', 'scope': '入栈和出栈', 'parent_key': None}],
            'point_categories': {p['key']: 'C1' for p in data['points']}}
        return json.dumps(result, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test-qwen', client=None)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True)
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    assert calls == ['extract', 'hierarchy']
    assert len(saved['checkpoint']['candidate']['knowledge_points']) == 2
    assert saved['checkpoint']['candidate']['atomic_assessment']['ready_for_adoption']
    assert svc.repository.load_raw('c-pilot') == before
