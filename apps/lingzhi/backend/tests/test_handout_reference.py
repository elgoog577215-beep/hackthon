import json

from handout_reference import parse_reference_ranges, reference_writing_guide
from teacher_script import parse_handout_blocks, normalize_teacher_script_section, script_contract_for_revision


def tagged(body, kind='definition', title='条件概率'):
    return '<!-- reference:' + json.dumps({'kind': kind, 'title': title}, ensure_ascii=False) + ' -->\n' + body + '\n<!-- reference:end -->'


def test_shared_stream_marks_several_statements_without_a_second_body():
    first = r'当 $P(B)>0$ 时，$$P(A|B)=\frac{P(A\cap B)}{P(B)}$$'
    second = '输入必须为非空序列。\n\n1. 求和。\n2. 除以元素数量。'
    text = '<!-- block:{"type":"explanation","title":"概率与计算"} -->\n引入🙂。\n' + tagged(first) + '\n完整推导。\n' + tagged(second, 'method', '平均值算法')
    parsed = parse_handout_blocks(text, 's', complete=True)
    assert not parsed['error']
    block = parsed['blocks'][0]
    assert '<!-- reference:' not in block['content']
    assert block['content'].count(first) == 1
    assert '完整推导' in block['content']
    assert len(block['references']) == 2
    for ref in block['references']:
        assert block['content'][ref['start']:ref['end']] == ref['content']
    contract = script_contract_for_revision({'node_id': 's', 'node_name': '概率'}, {}, {})
    saved = normalize_teacher_script_section({'section_node_id': 's', 'title': '概率', 'blocks': [block]}, contract)
    assert saved['blocks'][0]['references'] == block['references']
    assert saved['blocks'][0]['reference_schema_version'] == 'handout_reference_v1'


def test_partial_and_invalid_metadata_preserve_readable_prose():
    unfinished = parse_reference_ranges('引入。\n<!-- reference:{"kind":"theorem","title":"定理"} -->\n正文仍在。')
    assert unfinished['content'] == '引入。\n\n正文仍在。'
    assert unfinished['references'] == []
    assert unfinished['reference_issues'] == ['unfinished_range']
    invalid = parse_reference_ranges('<!-- reference:{broken} -->\n完整内容。\n<!-- reference:end -->')
    assert invalid['content'] == '完整内容。'
    assert invalid['references'] == []
    assert 'invalid_metadata' in invalid['reference_issues']


def test_fences_answers_and_nested_ranges_do_not_become_references():
    literal = '```html\n' + tagged('这是代码中的示例标记。') + '\n```'
    result = parse_reference_ranges(literal)
    assert result['content'] == literal and result['references'] == []
    folded = parse_reference_ranges('<details>\n' + tagged('隐藏答案。') + '\n</details>')
    assert folded['references'] == [] and '隐藏答案。' in folded['content']
    nested = parse_reference_ranges(tagged('首段。\n' + tagged('嵌套。') + '\n尾段。'))
    assert not nested['references']
    assert all(word in nested['content'] for word in ['首段', '嵌套', '尾段'])


def test_generation_guide_selects_existing_text_with_conditions_instead_of_summaries():
    guide = reference_writing_guide()
    assert '条件' in guide and '同一范围' in guide
    assert '<!-- reference:end -->' in guide
    assert '不另输出速览摘要' in guide
