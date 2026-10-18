from copy import deepcopy
import pytest

from backend.tests.test_knowledge_extraction_repair import value, point


@pytest.mark.parametrize('ban', ['不能出现 `)(`', '不能出现“)(”'])
@pytest.mark.parametrize('form', ['definition', 'fact'])
def test_proven_false_source_clause_is_quarantined_without_editing_other_knowledge(ban, form):
    from knowledge_source_rules import quarantine_source_errors
    invalid = {'form': 'definition', 'subject': '匹配条件', 'meaning': '顺序正确，即'+ban,
               'constraints': ['字符串仅包含圆括号'], 'conditions': [], 'attachments': []}
    if form == 'fact': invalid = {'form': 'fact', 'subject': '匹配条件', 'property': '规则', 'value': '顺序正确，即'+ban, 'conditions': ['字符串仅包含圆括号'], 'attachments': []}
    original = value([invalid, point()]); original['_content_review_trace'] = [{'point_review_key': 'bad'}, {'point_review_key': 'good'}]
    before = deepcopy(original)
    source = {'S1.1': {'text': '判断字符串中的圆括号是否匹配。匹配条件：顺序正确，即不能出现 `)(`。入栈处理左括号。'}}
    filtered, records = quarantine_source_errors(original, source)
    assert filtered['passages']['S1.1']['points'] == [original['passages']['S1.1']['points'][1]]
    assert filtered['_content_review_trace'] == [{'point_review_key': 'good'}]
    assert records[0]['counterexample'] == '()()' and records[0]['prefix_balances'] == [1, 0, 1, 0]
    assert filtered['source_issues'] and original == before


def test_hallucinated_ban_cannot_be_relabelled_as_a_source_error():
    from knowledge_source_rules import quarantine_source_errors
    invalid = {'form': 'definition', 'subject': '匹配条件', 'meaning': '不能出现 `)(`', 'constraints': [], 'conditions': [], 'attachments': []}
    original = value([invalid])
    filtered, records = quarantine_source_errors(original, {'S1.1': {'text': '圆括号字符串按前缀余额和总余额判断。'}})
    assert filtered == original and records == []


def test_component_to_system_explanation_stays_context_without_blaming_the_source():
    from knowledge_source_rules import contextualize_component_explanations
    original = value([point('popleft()', property='保证特性', value='保证先入队先处理'),
                      point('popleft()', property='操作效果', value='从左端弹出元素')])
    original['_content_review_trace'] = [{'point_review_key':'global'}, {'point_review_key':'primitive'}]
    source = {'S1.1': {'source_key':'S1','text':'queue = deque([root]); node=queue.popleft(); queue.append(child)'}}
    before = deepcopy(original); filtered, records = contextualize_component_explanations(original, source)
    assert filtered['passages']['S1.1']['points'] == [original['passages']['S1.1']['points'][1]]
    assert filtered['_content_review_trace'] == [{'point_review_key':'primitive'}]
    assert filtered['source_issues'] == [] and records[0]['origin'] == 'model_scope_loss'
    assert records[0]['fifo_counterexample']['observed'] == 'B'
    assert original == before
