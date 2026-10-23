"""TeX in display titles must survive the JSON transport's escaping boundary."""
import json

import pytest

from teacher_script import parse_handout_blocks


@pytest.mark.parametrize('formula', [r'\varepsilon', r'\delta', r'\theta', r'\frac{x}{2}', r'\nu + \tau', r'\underbrace{x}_{a}'])
@pytest.mark.parametrize('escaped', [False, True])
def test_raw_and_json_escaped_math_titles_have_identical_meaning(formula, escaped):
    title = '参数 $' + formula + '$'
    metadata = {'type': 'definition', 'title': title, 'key': 'definition'}
    encoded = json.dumps(metadata, ensure_ascii=False)
    if not escaped:
        encoded = encoded.replace('\\\\', '\\')
    result = parse_handout_blocks('<!-- block:' + encoded + ' -->\n正文保持不变。', 'section', complete=True)
    assert not result['error']
    assert result['blocks'][0]['title'] == title
    assert result['blocks'][0]['content'] == '正文保持不变。'


@pytest.mark.parametrize('payload', [
    r'{"type":"definition","title":"$\delta$","key":"bad\id"}',
    r'{"type":"definition","title":"$\delta$","key":"a","key":"b"}',
    r'{"type":"definition","title":"outside \invalid","key":"a"}',
    r'{"type":"definition","title":"$\delta$","key":"a","answer_to":"missing"}',
])
def test_math_transport_normalization_does_not_relax_identity_or_other_json(payload):
    result = parse_handout_blocks('<!-- block:' + payload + ' -->\n正文。', 'section', complete=True)
    assert result['error']
