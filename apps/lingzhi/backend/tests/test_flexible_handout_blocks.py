"""Open teaching composition uses one request and the existing authoring store."""
import json
from copy import deepcopy

import pytest

from teacher_script import (
    parse_handout_blocks, handout_section_contract, script_contract_for_revision,
    normalize_teacher_script_section, validate_teacher_script_section,
)
from backend.tests.test_teacher_handout_lecture import fixture, new_job


def marker(kind, title, body, **metadata):
    return '<!-- block:' + json.dumps({'type': kind, 'title': title, **metadata}, ensure_ascii=False) + ' -->\n' + body


TEXT = '\n'.join([
    marker('思想实验', '先尝试反推', '假设只能观察末尾元素，怎样组织访问？', key='story'),
    marker('推导', '从操作得到规则', '由末尾插入与删除，得到后进先出的访问顺序。', key='derive'),
    marker('定义', '栈', '栈是一种后进先出的线性结构。', key='define'),
    marker('练习', '操作后的栈顶', '依次压入 1、2，再弹出一次，栈顶是什么？', key='q'),
    marker('解答', '依据访问顺序核对', '栈顶是 1，因为最后压入的 2 先被弹出。', key='a', answer_to='q'),
])


def test_free_order_custom_types_and_answer_identity():
    parsed = parse_handout_blocks(TEXT, 's', identity='job-1', complete=True)
    assert not parsed['error']
    blocks = parsed['blocks']
    assert [b['content_type'] for b in blocks] == ['思想实验', 'derivation', 'definition', 'exercise', 'answer']
    assert blocks[-1]['answer_to'] == blocks[-2]['block_id']
    assert '<!-- block:' not in parsed['content']
    regenerated = parse_handout_blocks(TEXT, 's', identity='job-2', complete=True)
    assert {b['block_id'] for b in blocks}.isdisjoint(b['block_id'] for b in regenerated['blocks'])


@pytest.mark.parametrize('text,error', [
    (marker('解答', '错误引用', '答案', key='a', answer_to='missing'), 'block_answer_reference_invalid'),
    (marker('定义', '空内容', ''), 'block_incomplete'),
    (marker('定义', '未闭合', '```python\nx=1'), 'block_incomplete'),
    (marker('定义', '一', '正文', key='same') + '\n' + marker('定义', '二', '正文', key='same'), 'block_key_duplicate'),
    ('<!-- block:{"type":[]} -->\n正文', 'block_metadata_invalid'),
    ('只有未分类正文', 'block_marker_missing'),
])
def test_invalid_structure_preserves_blocks_without_publishing(text, error):
    assert parse_handout_blocks(text, 's', complete=True)['error'] == error


def test_every_token_prefix_is_safe_and_code_markers_stay_literal():
    source = marker('例题', '协议示例', '```html\n<!-- block:{"type":"假块"} -->\n```\n正文')
    for index in range(len(source) + 1):
        partial = parse_handout_blocks(source[:index], 's')
        assert len(partial['blocks']) <= 1
    parsed = parse_handout_blocks(source, 's', complete=True)
    assert not parsed['error'] and len(parsed['blocks']) == 1
    assert '<!-- block:' in parsed['blocks'][0]['content']


def test_custom_task_can_have_a_custom_response_without_closed_type_list():
    text = marker('思想实验', '假设条件', '假设只能从一端取出元素。', key='task') + '\n' + marker('反思反馈', '检查推理', '沿操作约束核对结论。', key='response', answer_to='task')
    parsed = parse_handout_blocks(text, 's', complete=True)
    assert not parsed['error']
    assert parsed['blocks'][1]['answer_to'] == parsed['blocks'][0]['block_id']


def test_provider_stop_and_scope_control_completion_not_a_model_password():
    from teacher_script import parse_handout_stream
    text = '<!-- section:s -->\n' + TEXT
    assert not parse_handout_stream(text, ['s'])['completed']
    done = parse_handout_stream(text, ['s'], provider_complete=True)
    assert not done['error'] and list(done['completed']) == ['s']
    assert parse_handout_stream(text, ['s', 'missing'], provider_complete=True)['error'] == 'missing_sections'
    assert parse_handout_stream(text + '\n```python\nx =', ['s'], provider_complete=True)['error'] == 'section_incomplete'


def test_reader_projection_keeps_types_and_answer_links():
    from course_document import document_from_legacy_course, course_view_from_document
    blocks = parse_handout_blocks(TEXT, 's', identity='job', complete=True)['blocks']
    course = {'course_id': 'c', 'course_name': '栈', 'nodes': [{'node_id': 's', 'node_level': 2, 'node_name': '栈', 'content_blocks': [
        {'block_id': b['block_id'], 'type': b['role'], 'title': b['title'], 'content': b['content'],
         'metadata': {key: b[key] for key in ('module_id', 'content_type', 'type_label', 'answer_to')}} for b in blocks
    ]}]}
    document = document_from_legacy_course(course)
    assert document.blocks[0].payload['content_type'] == '思想实验'
    assert document.blocks[-1].payload['answer_to'] == blocks[-2]['block_id']
    projected = course_view_from_document(course, document)
    assert projected['nodes'][0]['content_blocks'][0]['metadata']['content_type'] == '思想实验'


def test_edit_contract_preserves_custom_types_identity_and_relations():
    blocks = parse_handout_blocks(TEXT, 's', identity='job', complete=True)['blocks']
    section = {'section_node_id': 's', 'title': '栈', 'blocks': blocks}
    contract = script_contract_for_revision({'node_id': 's'}, {}, section)
    edited = deepcopy(section)
    edited['blocks'][0]['content'] = '换一个假设情境，保持同一个内容对象。'
    normalized = normalize_teacher_script_section(edited, contract)
    assert validate_teacher_script_section(normalized, contract)['passed']
    assert normalized['blocks'][0]['content_type'] == '思想实验'
    assert normalized['blocks'][0]['block_id'] == blocks[0]['block_id']
    assert normalized['blocks'][-1]['answer_to'] == blocks[-1]['answer_to']
    whole_edit = normalize_teacher_script_section({**section, 'blocks': [], 'content': normalized['content']}, contract)
    assert validate_teacher_script_section(whole_edit, contract)['passed']
    assert whole_edit['blocks'][0]['content_type'] == '思想实验'


@pytest.mark.asyncio
async def test_one_call_persists_all_types_and_streams_without_protocol(tmp_path):
    repo, service, kwargs = fixture(tmp_path)
    calls = []

    async def generate(**request):
        calls.append(request)
        text = '\n'.join(f'<!-- section:{s["node_id"]} -->\n{TEXT}' for s in request['outline_sections'])
        await request['on_content_delta'](text)
        return {'text': text}

    result = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert result['status'] == 'completed', result.get('error')
    assert len(calls) == 1
    assert len(result['result_sections']) == 2
    assert all(len(s['blocks']) == 5 for s in result['result_sections'])
    assert len(result['block_metadata']) == 10
    assert not any('<!-- block:' in text for text in result['streamed_block_content'].values())
    saved = repo.lesson('course-1', 'L1-1')['script_revisions'][-1]['sections']
    assert saved[0]['blocks'][0]['content_type'] == '思想实验'
    assert saved[0]['blocks'][-1]['answer_to'] == saved[0]['blocks'][-2]['block_id']


def test_knowledge_refs_cannot_invent_plan_identities():
    block = parse_handout_blocks(marker('定义', '栈', '正文', knowledge=['编造知识']), 's', complete=True)['blocks']
    contract = handout_section_contract({'node_id': 's'}, {})
    report = validate_teacher_script_section({'section_node_id': 's', 'blocks': block}, contract)
    assert 'teacher_script:knowledge_scope' in {issue['code'] for issue in report['blocking_issues']}


def test_continuation_draft_does_not_duplicate_completed_prose_or_drop_code():
    from course_generation.prompts import build_handout_prompt
    old = '<!-- section:a -->\n已完成内容唯一出现\n<!-- section:b -->\n未完成内容\n```html\n<!-- section:a -->\n代码里的同形标记\n```'
    prompt = build_handout_prompt(
        course_title='测试', lesson={}, requirements='', contract='test',
        sections=[{'node_id': 'b'}], plan_sections={}, partial_text=old,
        completed_sections=[{'section_node_id': 'a', 'content': '已完成内容唯一出现'}],
    )
    payload = json.JSONDecoder().raw_decode(prompt.split('\n', 1)[1])[0]
    assert payload['incomplete_draft'].startswith('<!-- section:b -->')
    assert '代码里的同形标记' in payload['incomplete_draft']
    assert prompt.count('已完成内容唯一出现') == 1


def test_bad_metadata_after_valid_block_keeps_unassigned_prose_and_code():
    text = marker('定义', '已解析', '有效正文', key='good') + '\n' + '\n'.join([
        '<!-- block:{"type":"例题","title":"未转义"引号""} -->',
        '已收到但无法归属的正文',
        '```html', '<!-- block:literal -->', '```',
        marker('总结', '后续总结', '仍应保留的结尾'),
    ])
    parsed = parse_handout_blocks(text, 's', complete=True)
    assert parsed['error'] == 'block_metadata_invalid'
    assert len(parsed['blocks']) == 1
    assert '有效正文' not in parsed['unassigned_fragment']
    assert '已收到但无法归属的正文' in parsed['unassigned_fragment']
    assert '仍应保留的结尾' in parsed['unassigned_fragment']
    assert '<!-- block:literal -->' in parsed['unassigned_fragment']
    assert '未转义' not in parsed['unassigned_fragment']


@pytest.mark.asyncio
async def test_failed_second_block_remains_visible_in_original_job(tmp_path):
    repo, service, kwargs = fixture(tmp_path)
    async def generate(**request):
        return {'text': '<!-- section:L2-1-1 -->\n' + marker('定义', '栈', '有效正文')
                + '\n<!-- block:invalid -->\n错误标记之后的真实内容'}
    result = await service.run_script_job(**kwargs, job_id=new_job(repo), generator=generate)
    assert result['status'] == 'failed'
    assert '错误标记之后的真实内容' in result['unassigned_fragment']
    assert not repo.lesson('course-1', 'L1-1')['script_revisions']
