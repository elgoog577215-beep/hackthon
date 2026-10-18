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


def test_single_pass_requires_explicit_note_for_every_passage(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    value = response(); value.pop('unassigned_passages'); value['passage_notes'] = {}
    with pytest.raises(CourseDocumentConflict, match='完整'): compile_extraction(raw, context, ['S1'], 1, value)
    value['passage_notes'] = {'S1.1': None}
    assert compile_extraction(raw, context, ['S1'], 1, value)['source_coverage'][0]['uncovered_passage_keys'] == []
    value['points'] = []
    assert compile_extraction(raw, context, ['S1'], 1, value)['source_coverage'][0]['uncovered_passage_keys'] == ['S1.1']


def test_passage_keyed_extraction_cannot_silently_omit_source_text(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    points = response()['points']
    for point in points: point.pop('source_passage_keys')
    value = {'response_contract': 'knowledge_extract_v1', 'passages': {'S1.1': {'points': points, 'note': None}}, 'source_issues': []}
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert result['source_coverage'][0]['uncovered_passage_keys'] == []
    value['passages']['S1.1'] = {'points': [], 'note': None}
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, value)


def test_question_parts_bind_exact_frozen_focus_without_rewriting_answer(svc, monkeypatch):
    from knowledge_extract import compile_extraction, extraction_schema
    from jsonschema import validate, ValidationError
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    point = response()['points'][0]
    point.pop('source_passage_keys'); point.pop('question')
    point['question_before'] = ''; point['question_after'] = '执行什么操作？'
    value = {'response_contract': 'knowledge_extract_v1', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    validate(value, extraction_schema(['S1.1']))
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert result['tree']['knowledge_points'][0]['meta_question'] == '入栈执行什么操作？'
    assert result['tree']['knowledge_points'][0]['meta_answer'] == point['claim']
    assert result['report']['ready_for_adoption']
    point['question_after'] = ''
    with pytest.raises(ValidationError): validate(value, extraction_schema(['S1.1']))
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, value)


def test_source_focus_keys_prevent_invented_subjects_without_changing_claims(svc, monkeypatch):
    import json
    from jsonschema import validate, ValidationError
    from knowledge_extract import extraction_prompt, extraction_schema, compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    payload = json.loads(extraction_prompt(raw, context, ['S1']).split('\nINPUT_JSON:\n')[1])
    passage = payload['source_passages'][0]
    options = passage['focus_options']
    assert options and all(term in passage['text'] for term in options.values())
    focus_key = next(k for k, term in options.items() if term == '入栈')
    point = response()['points'][0]
    for key in ('source_passage_keys', 'question', 'focus_term'): point.pop(key)
    point.update(focus_key=focus_key, question_before='', question_after='执行什么操作？')
    value = {'response_contract': 'knowledge_extract_v2', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    schema = extraction_schema(['S1.1'], {'S1.1': options}, contract='knowledge_extract_v2')
    validate(value, schema)
    before = deepcopy(value)
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert result['report']['ready_for_adoption']
    assert result['items'][0]['focus_terms'] == ['入栈']
    assert result['tree']['knowledge_points'][0]['meta_question'] == '入栈执行什么操作？'
    assert result['tree']['knowledge_points'][0]['statement'] == point['claim']
    assert value == before
    point['focus_key'] = 'invented-subject'
    with pytest.raises(ValidationError): validate(value, schema)
    with pytest.raises(CourseDocumentConflict, match='原文对象'):
        compile_extraction(raw, context, ['S1'], 1, value)


def test_source_focus_options_include_real_recursion_objects_and_keep_legacy_prompt(svc, monkeypatch):
    import json
    from knowledge_extract import focus_options, extraction_prompt
    text = '**最大同时存在的栈帧数量（最大递归深度）**。return n * factorial(n - 1)  # 递归调用'
    options = focus_options(text)
    assert {'最大递归深度', '递归调用'} <= set(options.values())
    assert all(term in text for term in options.values())
    assert '最大深度' not in options.values()
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    prompt = extraction_prompt(raw, context, ['S1'], contract='knowledge_extract_v1')
    payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1])
    assert all('focus_options' not in p for p in payload['source_passages'])
    assert '"focus_term"' in prompt


def test_symbol_only_sources_keep_literal_anchors_and_empty_sources_allow_only_explicit_notes():
    from jsonschema import Draft202012Validator
    from knowledge_extract import focus_options, extraction_schema
    assert '2+3=5' in focus_options('2+3=5').values()
    schema = extraction_schema(['S1.1'], {'S1.1': {}})
    Draft202012Validator.check_schema(schema)
    value = {'response_contract': 'knowledge_extract_v3', 'passages': {'S1.1': {
        'points': [], 'note': {'handling': 'context', 'reason': '空白片段无可提取知识'}}}, 'source_issues': []}
    validator = Draft202012Validator(schema)
    assert validator.is_valid(value)
    value['passages']['S1.1']['note'] = None
    assert not validator.is_valid(value)


@pytest.mark.parametrize('goal', [False, True])
def test_complete_questions_remain_model_authored_and_learning_goals_cannot_pass_as_facts(svc, monkeypatch, goal):
    import json
    from jsonschema import validate
    from knowledge_extract import extraction_prompt, extraction_schema, compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    passage = json.loads(extraction_prompt(raw, context, ['S1']).split('\nINPUT_JSON:\n')[1])['source_passages'][0]
    options = passage['focus_options']; key = next(k for k,v in options.items() if v == '入栈')
    point = response()['points'][0]
    for field in ('source_passage_keys', 'focus_term'): point.pop(field)
    point['focus_key'] = key
    if goal: point['claim'] = '能画出入栈的操作示意图，并准确指出元素进出方向。'
    value = {'response_contract': 'knowledge_extract_v3', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    validate(value, extraction_schema(['S1.1'], {'S1.1': options}))
    result = compile_extraction(raw, context, ['S1'], 1, value)
    assert result['tree']['knowledge_points'][0]['meta_question'] == '入栈执行什么操作？'
    assert result['report']['ready_for_adoption'] is not goal
    if goal: assert any(i['code'] == 'nonknowledge_leaf' for i in result['report']['issues'])
    else:
        point['question'] = '出栈执行什么操作？'
        result = compile_extraction(raw, context, ['S1'], 1, value)
        assert result['tree']['knowledge_points'][0]['meta_question'] == point['question']
        assert not result['report']['ready_for_adoption']  # No invented prefix to hide a wrong subject.


@pytest.mark.asyncio
async def test_failed_single_pass_continues_only_missing_source_group(svc, monkeypatch):
    import json
    from types import SimpleNamespace
    from backend.tests.test_knowledge_atomic import start
    setup_course(svc, monkeypatch)
    state = svc.authoring.load('c-pilot')
    blocks = state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks']
    blocks[0]['content'] = '入栈将元素插入栈顶。'
    blocks.append({**deepcopy(blocks[0]), 'block_id': 'pop-block', 'content': '出栈移除并返回栈顶元素。'})
    svc.authoring._save(state)
    monkeypatch.setattr('knowledge_extract.extraction_groups', lambda context: [['S1'], ['S2']])
    fail = True; calls = []
    async def call(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); source = payload['source_passages'][0]['source_key']
        calls.append(source)
        if fail and source == 'S2': raise TimeoutError('isolated request interrupted')
        value = response(); value['points'] = [value['points'][0 if source == 'S1' else 1]]
        value['points'][0]['source_passage_keys'] = [source + '.1']
        return json.dumps(value, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test-qwen', client=None)
    first = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', first['id'])
    original = deepcopy(svc.authoring.load('c-pilot')['jobs'][first['id']])
    assert original['status'] == 'failed'
    assert original['checkpoint']['atomic_pipeline']['inventory_batches'][0]['status'] == 'completed'
    fail = False; calls.clear()
    resumed = start(svc, 'resume-single-pass', resume_job_id=first['id'])
    assert resumed['extraction_mode'] == 'single_pass_v1'
    await svc.run('c-pilot', resumed['id'])
    result = svc.authoring.load('c-pilot')['jobs'][resumed['id']]
    assert calls == ['S2'] and result['status'] == 'completed'
    assert len(result['checkpoint']['candidate']['knowledge_points']) == 2
    assert svc.authoring.load('c-pilot')['jobs'][first['id']] == original


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
            'response_contract': 'knowledge_partition_v1', 'groups': [],
            'point_groups': {p['key']: '__direct__' for p in data['points']}, 'stop_reason': '两个栈操作自然并列'}
        return json.dumps(result, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test-qwen', client=None)
    before = deepcopy(svc.repository.load_raw('c-pilot'))
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True)
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.load('c-pilot')['jobs'][job['id']]
    assert saved['status'] == 'completed'
    assert calls == ['extract', 'hierarchy_partition']
    assert len(saved['checkpoint']['candidate']['knowledge_points']) == 2
    assert saved['checkpoint']['candidate']['atomic_assessment']['ready_for_adoption']
    assert svc.repository.load_raw('c-pilot') == before
