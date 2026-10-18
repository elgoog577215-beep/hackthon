from copy import deepcopy

from backend.tests.test_knowledge_extraction_repair import value, point


def test_proven_false_source_clause_is_quarantined_without_editing_other_knowledge():
    from knowledge_source_rules import quarantine_source_errors
    invalid = {'form': 'definition', 'subject': '匹配条件', 'meaning': '顺序正确，即不能出现 `)(`',
               'constraints': ['字符串仅包含圆括号'], 'conditions': [], 'attachments': []}
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
