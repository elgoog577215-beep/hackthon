from copy import deepcopy

import pytest
from jsonschema import validate, Draft202012Validator

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course
from course_repository import CourseDocumentConflict


def fact(**extra):
    return {'form': 'fact', 'subject': '入栈', 'property': '操作端点', 'value': '栈顶',
            'conditions': [], 'attachments': [], **extra}


def result(svc, monkeypatch, point):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    value = {'response_contract': 'knowledge_extract_v6', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    return compile_extraction(raw, context, ['S1'], 1, value), value


def test_single_property_assembles_subject_question_without_putting_answer_in_question(svc, monkeypatch):
    output, _ = result(svc, monkeypatch, fact())
    point = output['tree']['knowledge_points'][0]
    assert point['statement'] == '入栈的操作端点为栈顶。'
    assert point['meta_question'] == '入栈的操作端点是什么？'
    assert '栈顶' not in point['meta_question']
    assert point['atomic_contract']['form'] == 'fact'
    assert output['report']['ready_for_adoption']


@pytest.mark.parametrize('point', [fact(property='操作端点和复杂度'), fact(value='插入栈顶；出栈移除栈顶'), fact(subject='虚构对象')])
def test_independent_claims_or_invented_subjects_are_not_silently_approved(svc, monkeypatch, point):
    with pytest.raises(CourseDocumentConflict): result(svc, monkeypatch, point)


def test_joint_definition_is_one_complete_target_and_keeps_all_constraints(svc, monkeypatch):
    point = {'form': 'definition', 'subject': '入栈', 'meaning': '把元素加入栈中的操作',
             'constraints': ['仅在栈顶插入', '不从栈底插入'], 'conditions': [], 'attachments': []}
    output, value = result(svc, monkeypatch, point)
    compiled = output['tree']['knowledge_points'][0]
    assert '栈底' in compiled['statement'] and '全部限定条件' in compiled['meta_question']
    assert not any(i['code'] == 'compound_review' for i in output['report']['issues'])
    assert output['report']['atomicity_checks'][0]['form'] == 'definition'
    assert value['passages']['S1.1']['points'][0] == point


def test_single_dimension_comparison_checks_both_subjects_and_does_not_drop_an_answer(svc, monkeypatch):
    point = {'form': 'comparison', 'left_subject': '入栈', 'right_subject': '出栈', 'property': '操作效果',
             'left_value': '将元素插入栈顶', 'right_value': '移除并返回栈顶元素', 'conditions': [], 'attachments': []}
    output, _ = result(svc, monkeypatch, point)
    compiled = output['tree']['knowledge_points'][0]
    assert all(s in compiled['meta_question'] for s in ('入栈', '出栈', '操作效果'))
    assert '插入' in compiled['statement'] and '返回' in compiled['statement']
    assert not any(i['code'] == 'compound_review' for i in output['report']['issues'])


def test_complete_method_question_covers_steps_and_termination(svc, monkeypatch):
    point = {'form': 'procedure', 'subject': '入栈', 'goal': '加入一个元素',
             'steps': ['检查容量', '将元素放入栈顶', '更新栈顶指针'], 'completion': '新元素成为栈顶', 'conditions': [], 'attachments': []}
    output, _ = result(svc, monkeypatch, point)
    compiled = output['tree']['knowledge_points'][0]
    assert '完整步骤' in compiled['meta_question'] and '结束判据' in compiled['meta_question']
    assert all(step in compiled['statement'] for step in point['steps'])
    assert not any(i['code'] == 'compound_review' for i in output['report']['issues'])


def test_structured_contract_schema_keeps_old_contract_frozen(svc, monkeypatch):
    import json
    from knowledge_extract import extraction_prompt, extraction_schema
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    payload = json.loads(extraction_prompt(raw, context, ['S1']).split('\nINPUT_JSON:\n')[1])
    passage = payload['source_passages'][0]
    schema = extraction_schema(['S1.1'], {'S1.1': passage['focus_options']})
    validate({'response_contract': 'knowledge_extract_v6', 'passages': {'S1.1': {'points': [fact()], 'note': None}}, 'source_issues': []},
             extraction_schema(['S1.1'], {'S1.1': passage['focus_options']}, contract='knowledge_extract_v6'))
    old = json.loads(extraction_prompt(raw, context, ['S1'], contract='knowledge_extract_v5').split('\nINPUT_JSON:\n')[1])
    assert old['extraction_contract'] == 'knowledge_extract_v5'


def test_decoder_enforces_the_same_single_attribute_boundary_as_the_compiler():
    from knowledge_semantic_contract import point_variants
    validator = Draft202012Validator(point_variants(['入栈']))
    assert validator.is_valid(fact())
    assert not validator.is_valid(fact(property='操作端点和复杂度'))
    assert not validator.is_valid(fact(value='插入栈顶；出栈移除栈顶'))


def test_uniform_wire_form_preserves_single_target_semantics_without_union_branch_repetition(svc, monkeypatch):
    import json
    from knowledge_extract import extraction_prompt, extraction_schema, compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    passage = json.loads(extraction_prompt(raw, context, ['S1']).split('\nINPUT_JSON:\n')[1])['source_passages'][0]
    point = {'form': 'fact', 'subjects': ['入栈'], 'target': '操作端点', 'values': ['栈顶'], 'details': [], 'conditions': [], 'attachments': []}
    value = {'response_contract': 'knowledge_extract_v7', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    validate(value, extraction_schema(['S1.1'], {'S1.1': passage['focus_options']}, contract='knowledge_extract_v7'))
    compiled = compile_extraction(raw, context, ['S1'], 1, value)
    assert compiled['tree']['knowledge_points'][0]['meta_question'] == '入栈的操作端点是什么？'
    point['values'].append('另一个无关结论')
    with pytest.raises(CourseDocumentConflict): compile_extraction(raw, context, ['S1'], 1, value)


@pytest.mark.parametrize('form,target,value,other_subject,other_value,details', [
    ('fact', '保存内容', '函数参数、局部变量、返回地址', '', '', []),
    ('definition', '', '将元素加入栈中的操作', '', '', ['仅在栈顶插入']),
    ('comparison', '操作效果', '插入元素', '出栈', '移除元素', []),
    ('procedure', '加入元素', '新元素成为栈顶', '', '', ['放入元素', '更新指针']),
])
def test_scalar_slots_preserve_enumerations_and_form_specific_fields(svc, monkeypatch, form, target, value, other_subject, other_value, details):
    import json
    from knowledge_extract import extraction_prompt, extraction_schema, compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    passage = json.loads(extraction_prompt(raw, context, ['S1']).split('\nINPUT_JSON:\n')[1])['source_passages'][0]
    point = {'form': form, 'subject': '入栈', 'target': target, 'value': value,
             'other_subject': other_subject, 'other_value': other_value, 'details': details, 'conditions': [], 'attachments': []}
    response = {'response_contract': 'knowledge_extract_v8', 'passages': {'S1.1': {'points': [point], 'note': None}}, 'source_issues': []}
    validate(response, extraction_schema(['S1.1'], {'S1.1': passage['focus_options']}))
    result = compile_extraction(raw, context, ['S1'], 1, response)
    assert result['report']['ready_for_adoption']
    assert result['tree']['knowledge_points'][0]['atomic_contract']['form'] == form
    assert value in result['tree']['knowledge_points'][0]['statement']


def test_core_question_keeps_the_same_assumptions_as_its_answer():
    from knowledge_semantic_contract import build_point
    point, _ = build_point(fact(conditions=['栈未满']), ['入栈'])
    assert '栈未满' in point['question']
    assert point['conditions'] == ['栈未满']


@pytest.mark.parametrize('point,options', [
    (fact(subject='栈状态', property='Push(5)后', value='[5]'), ['栈状态']),
    (fact(subject='栈必须为空', property='条件', value='空'), ['栈必须为空']),
])
def test_concrete_execution_states_and_predicate_subjects_cannot_become_general_facts(point, options):
    from knowledge_semantic_contract import build_point
    with pytest.raises(CourseDocumentConflict): build_point(point, options)


def test_method_question_uses_its_named_tool_or_algorithm_naturally():
    from knowledge_semantic_contract import build_point
    point = {'form': 'procedure', 'subject': '栈', 'goal': '判断圆括号是否匹配', 'steps': ['扫描字符', '维护栈'],
             'completion': '没有提前失败且栈为空', 'conditions': [], 'attachments': []}
    compiled, _ = build_point(point, ['栈'])
    assert compiled['question'].startswith('如何运用栈判断圆括号是否匹配？')
