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


def test_one_relation_property_is_not_mistaken_for_two_independent_attributes():
    from knowledge_semantic_contract import quality_point, build_point
    point = {'form': 'fact', 'subject': 'DFS', 'property': '压入顺序与访问顺序关系',
             'value': '相反', 'conditions': [], 'attachments': []}
    compiled, audit = quality_point(point, 'DFS使用栈时，压入顺序与访问顺序相反。')
    assert audit['property_kind'] == 'single_relation'
    assert compiled['question'] == 'DFS的压入顺序与访问顺序关系是什么？'
    with pytest.raises(CourseDocumentConflict): build_point(point, ['DFS'])  # Frozen older contracts.
    point.update(property='时间和空间关系', value='O(n)和O(1)')
    with pytest.raises(CourseDocumentConflict): quality_point(point, 'DFS的时间和空间代价分别给出。')
    comparison = {'form': 'comparison', 'left_subject': 'DFS', 'right_subject': 'BFS',
        'property': '操作顺序与访问顺序关系', 'left_value': '栈的压入顺序与访问顺序相反（LIFO）',
        'right_value': '队列的入队顺序与访问顺序一致（FIFO）', 'conditions': [], 'attachments': []}
    _, audit = quality_point(comparison, 'DFS与BFS的顺序关系分别陈述。')
    assert audit['property_kind'] == 'single_relation'


def test_named_api_cost_is_not_a_specific_execution_trace():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'fact', 'subject': 'Python列表', 'property': 'pop(0)效率',
             'value': '效率低', 'conditions': [], 'attachments': []}
    compiled, audit = quality_point(point, 'Python列表pop(0)效率低，实际用deque。')
    assert 'pop(0)' in compiled['question'] and audit['property_kind'] == 'named_operation_cost'
    point.update(subject='栈', property='Push(5)后状态', value='[5]')
    with pytest.raises(CourseDocumentConflict): quality_point(point, '栈执行Push(5)后状态是[5]。')


def test_piecewise_function_definition_cannot_be_split_into_unqualified_facts():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'fact', 'subject': 'fib', 'property': '递归定义',
             'value': 'if n <= 1: return n; return fib(n-1) + fib(n-2)', 'conditions': [], 'attachments': []}
    with pytest.raises(CourseDocumentConflict, match='联合定义'):
        quality_point(point, 'fib的定义如下：if n <= 1: return n; return fib(n-1) + fib(n-2)')


@pytest.mark.parametrize('subject,property,value,conditions,match', [
    ('循环', '性能优势', '在内存占用和执行速度上通常优于递归', [], '独立量'),
    ('循环', '内存占用', '恒定', [], '调用帧'),
    ('DFS', '错误实现后果', '若用队列实现，搜索顺序变为广度优先', [], '前提'),
    ('系统栈深度', '范围', '10^3至10^4', ['取决于语言和配置'], '环境'),
    ('递归', '执行机制', '系统栈帧的压入与弹出', [], '实现'),
    ('DFS', '依赖数据结构', '栈', [], '实现'),
    ('栈', '物理存储基础', '必须建立在已有的线性表物理存储之上', [], '物理'),
    ('factorial', '最大栈深度', 'n', [], '符号'),
])
def test_known_source_overstatements_cannot_pass_as_unqualified_facts(subject, property, value, conditions, match):
    from knowledge_semantic_contract import quality_point
    point = {'form': 'fact', 'subject': subject, 'property': property, 'value': value, 'conditions': conditions, 'attachments': []}
    with pytest.raises(CourseDocumentConflict, match=match): quality_point(point, subject+'：'+value)


def test_partial_search_mechanism_is_not_a_complete_executable_method():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'procedure', 'subject': 'DFS', 'goal': '深度优先搜索',
        'steps': ['访问当前节点，将子节点压入栈', '弹出栈顶节点'], 'completion': '所有节点被访问', 'conditions': [], 'attachments': []}
    with pytest.raises(CourseDocumentConflict, match='机制'):
        quality_point(point, 'DFS的机制：访问当前节点，将子节点压入栈。弹出栈顶节点。')


def test_a_valid_parenthesis_string_can_contain_the_closing_opening_substring():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'definition', 'subject': '匹配条件', 'meaning': '顺序正确，即不能出现 `)(`',
             'constraints': [], 'conditions': ['字符串仅包含圆括号'], 'attachments': []}
    with pytest.raises(CourseDocumentConflict, match='前缀'):
        quality_point(point, '括号匹配条件为顺序正确，即不能出现 `)(`。算法使用栈。')


def test_one_correction_receives_all_missing_symbol_and_model_assumptions():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'fact', 'subject': '递归深度', 'property': '栈中数量', 'value': '栈中同时存在 d 个栈帧', 'conditions': [], 'attachments': []}
    with pytest.raises(CourseDocumentConflict) as error:
        quality_point(point, '递归深度为d时，栈中有d个栈帧。')
    assert '符号' in str(error.value) and '调用栈' in str(error.value)


def test_explicit_implementation_scope_is_accepted_but_cannot_cross_algorithms():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'fact', 'subject': 'DFS', 'property': '数据结构作用', 'value': '维护当前路径',
        'conditions': ['使用栈实现'], 'attachments': []}
    assert quality_point(point, 'DFS用栈维护当前路径。')[0]['conditions'] == ['使用栈实现']
    point.update(subject='BFS', value='队列', conditions=['此处展示显式栈实现以体现LIFO'])
    with pytest.raises(CourseDocumentConflict, match='串用'):
        quality_point(point, 'BFS当前用队列实现，DFS当前用显式栈实现。')


def test_access_mechanism_and_its_cost_do_not_hide_in_one_non_cost_question():
    from knowledge_semantic_contract import quality_point
    point = {'form': 'comparison', 'left_subject': '栈', 'right_subject': '队列', 'property': '访问方式',
        'left_value': '需连续出栈，O(n)', 'right_value': '需出队，O(n)',
        'conditions': ['n表示容器中的元素数量，比较最坏情况'], 'attachments': []}
    with pytest.raises(CourseDocumentConflict, match='复杂度'):
        quality_point(point, '栈和队列访问非首元素均需逐个取出，最坏代价O(n)。')
    point['property'] = '访问时间复杂度'
    assert quality_point(point, '栈和队列访问非首元素均需逐个取出，最坏代价O(n)。')[1]['form'] == 'comparison'


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
    assert recorded[0]['json_mode'] is True and 'json_schema' not in recorded[0]
