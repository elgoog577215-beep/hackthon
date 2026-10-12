import json
from unittest.mock import AsyncMock

import pytest

from ai_teacher_context import format_ai_teacher_context_prompt
from course_generation.prompts import build_handout_prompt
from teacher_script import handout_structure_closed, parse_handout_blocks
from teaching_diagrams import teaching_diagram_catalog, teaching_diagram_prompt


def test_catalog_is_shared_by_handout_and_both_answer_perspectives():
    catalog = teaching_diagram_catalog()
    assert len(catalog['types']) == 44
    assert len({t['id'] for t in catalog['types']}) == 44
    handout = build_handout_prompt(course_title='Test', lesson={}, requirements='', sections=[{'node_id': 's'}], plan_sections={}, completed_sections=[], partial_text='', contract='handout_lecture_v3')
    for prompt in [handout, format_ai_teacher_context_prompt({'request': {'perspective': 'teacher'}}), format_ai_teacher_context_prompt({'request': {'perspective': 'learner'}})]:
        assert teaching_diagram_prompt() in prompt
        assert '```lingzhi-diagram' in prompt
        assert '不编造数值' in prompt
        assert '隐藏解答' in prompt
        for entry in catalog['types']:
            assert f"- {entry['id']}（" in prompt


def test_original_handout_parser_preserves_diagram_source_and_prose():
    spec = {'schema_version': 'teaching_diagram_v1', 'type': 'bar_chart', 'title': 'A and B', 'summary': 'Same unit', 'source': 'Hypothetical example', 'unit': 'count', 'items': [{'label': 'A', 'value': 2}, {'label': 'B', 'value': 4}]}
    fence = '```lingzhi-diagram\n' + json.dumps(spec, ensure_ascii=False) + '\n```'
    body = 'Explanation\n\n' + fence + '\n\nConclusion'
    parsed = parse_handout_blocks('<!-- block:{"type":"explanation","title":"Read quantities","key":"one"} -->\n' + body, 's', complete=True)
    assert parsed['blocks'][0]['content'] == body
    assert handout_structure_closed(body)
    assert not handout_structure_closed(body.replace('\n```\n', '\n'))


@pytest.mark.asyncio
async def test_companion_answers_use_same_catalog_without_changing_note_or_check_protocol(monkeypatch):
    from ai_service import ai_service
    from routers.study_dialogues import _model

    reply = 'Explanation\n\n```lingzhi-diagram\n{}\n```'
    call = AsyncMock(return_value=json.dumps({'reply': reply, 'draft': 'A plain note.'}))
    monkeypatch.setattr(ai_service, '_call_llm', call)
    result = await _model({'source': 'Hypothetical example', 'message': 'Explain'}, action='discuss', language='en')
    assert result == {'reply': reply, 'draft': 'A plain note.'}
    call.assert_awaited_once()
    instruction = call.call_args.kwargs['system_prompt']
    assert teaching_diagram_prompt() in instruction
    assert 'Keep draft as the required single plain paragraph' in instruction
    assert call.call_args.kwargs['json_mode'] is True
    call.reset_mock()
    call.return_value = json.dumps({'passed': None, 'confidence': 0.1, 'feedback': 'Insufficient evidence'})
    await _model({'student_answer': 'Not sure'}, action='check', language='en')
    assert teaching_diagram_prompt() not in call.call_args.kwargs['system_prompt']
    call.assert_awaited_once()
