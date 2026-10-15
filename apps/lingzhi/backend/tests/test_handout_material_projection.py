from copy import deepcopy
import json

from course_generation.prompts import build_handout_prompt, handout_source_projection


def test_keeps_every_source_character_locator_and_restriction_without_duplicate_index_text():
    units = [{'evidence_id': f'e{i}', 'asset_id': 'original-pdf',
              'source_text': f'完整第{i}页：定义、条件、边界及推导。\n' * 40,
              'locator': {'page': i + 1, 'section_path': ['方法', '条件']},
              'authority': 'primary', 'usage_policy': 'prefer', 'factual_allowed': True,
              'confidence': 'high', 'summary': '可由原文重建的摘要', 'keywords': ['索引词'],
              'document_id': 'parsed-source', 'block_ids': [f'b{i}'], 'content_hash': f'hash{i}'}
             for i in range(10)]
    lesson = {'lesson_title': '设计思维', 'selected_material_evidence': units}
    original = deepcopy(lesson)
    projected = handout_source_projection(lesson)
    assert lesson == original
    assert len(projected['selected_material_evidence']) == 10
    for old, new in zip(units, projected['selected_material_evidence'], strict=True):
        for key in ('evidence_id', 'asset_id', 'source_text', 'locator', 'authority', 'usage_policy', 'factual_allowed', 'confidence'):
            assert new[key] == old[key]
        assert not {'summary', 'keywords', 'document_id', 'block_ids', 'content_hash'} & new.keys()
    prompt = build_handout_prompt(course_title='课程', lesson=lesson, requirements='',
        sections=[{'node_id': 's'}], plan_sections={}, completed_sections=[], partial_text='', contract='test')
    payload = json.JSONDecoder().raw_decode(prompt.split('\n', 1)[1])[0]
    assert ''.join(u['source_text'] for u in payload['lesson']['selected_material_evidence']) == ''.join(u['source_text'] for u in units)


def test_legacy_or_summary_only_sources_are_not_dropped_or_reinterpreted():
    lesson = {'selected_material_evidence': [{'summary': '唯一可用正文', 'keywords': ['教师自填']},
                                             {'source_text': '', 'summary': '不可丢弃'},
                                             {'text': '旧格式原文', 'summary': '教师说明'}]}
    assert handout_source_projection(lesson) == lesson
