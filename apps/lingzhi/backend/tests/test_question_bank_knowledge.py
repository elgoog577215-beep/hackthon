import asyncio
from copy import deepcopy

import pytest

from question_bank import QuestionBankRepository, formal_task_from_question_bank_item, refresh_question_bank_bundle
from knowledge_mastery import freeze_knowledge_refs
from question_bank_knowledge import binding_view, bind_questions


def course():
    return {'course_id': 'c1', 'owner_id': 'owner', 'nodes': [], 'course_knowledge_base': {
        'revision_id': 'tree1', 'lifecycle_status': 'active',
        'knowledge_points': [
            {'knowledge_id': 'k1', 'revision_id': 'kr1', 'status': 'active', 'granularity_status': 'atomic', 'name': '整数除法', 'statement': '整数除法向零截断', 'section_refs': ['n1']},
            {'knowledge_id': 'k2', 'revision_id': 'kr2', 'status': 'active', 'granularity_status': 'atomic', 'name': '条件判断', 'statement': 'if 执行条件为真的分支', 'section_refs': ['n1']},
            {'knowledge_id': 'group', 'revision_id': 'gr1', 'status': 'active', 'granularity_status': 'compound', 'name': '分类'},
        ],
    }}


def bank():
    return refresh_question_bank_bundle({'course_id': 'c1', 'items': [{
        'item_id': 'q1', 'revision_id': 'r1', 'course_id': 'c1', 'node_id': 'n1',
        'prompt': '计算 -7 / 2 的整数结果。', 'question_type': 'single_choice',
        'options': [{'id': 'A', 'text': '-3'}, {'id': 'B', 'text': '-4'}],
        'answer_spec': {'canonical_answer': 'A'}, 'course_knowledge_refs': ['k1', 'k2'],
        'lifecycle_status': 'approved', 'quality_report': {'passed': True},
    }]})


async def match(items, points):
    assert {p['knowledge_id'] for p in points} == {'k1', 'k2'}
    return [{'revision_id': i['revision_id'], 'knowledge_ids': ['k1'], 'confidence': 0.95,
             'reason': '直接考查整数除法的取整规则', 'evidence': '-7 / 2'} for i in items]


def test_auto_binds_actual_atomic_target_not_all_lecture_points_and_is_idempotent():
    original = bank()
    updated = asyncio.run(bind_questions(course(), original, matcher=match))
    item = updated['items'][0]
    assert original['items'][0]['course_knowledge_refs'] == ['k1', 'k2']
    assert item['course_knowledge_refs'] == ['k1']
    assert item['revision_id'] != 'r1'
    assert item['parent_revision_id'] == 'r1'
    assert item['knowledge_binding']['knowledge_revision_refs'] == {'k1': 'kr1'}
    assert binding_view(course(), updated)['counts']['bound'] == 1
    assert asyncio.run(bind_questions(course(), updated, matcher=None)) == updated


def test_manual_binding_is_validated_and_old_revisions_remain_readable(tmp_path):
    repository = QuestionBankRepository(tmp_path)
    original = repository.save_bundle('c1', bank())
    updated = asyncio.run(bind_questions(course(), original, mode='manual', revision_id='r1', knowledge_ids=['k2']))
    repository.save_bundle('c1', updated)
    assert repository.load_bundle('c1', original['bundle_revision_id']) == original
    assert updated['items'][0]['answer_spec'] == original['items'][0]['answer_spec']
    for ids in (['missing'], ['group'], ['k1', 'k1']):
        with pytest.raises(ValueError):
            asyncio.run(bind_questions(course(), original, mode='manual', revision_id='r1', knowledge_ids=ids))


def test_question_binding_freezes_revisions_and_never_relabels_old_attempts():
    updated = asyncio.run(bind_questions(course(), bank(), matcher=match))
    task = formal_task_from_question_bank_item(updated['items'][0])
    changed = course()
    changed['course_knowledge_base']['knowledge_points'][0]['revision_id'] = 'kr-new'
    assert binding_view(changed, updated)['counts']['stale'] == 1
    assert freeze_knowledge_refs(changed['course_knowledge_base'], task) == {'k1': 'kr1'}
    assert task['concept_ids'] == ['k1']


def test_uncertain_match_remains_pending_and_does_not_feed_section_refs_to_mastery():
    async def uncertain(items, points):
        return [{'revision_id': 'r1', 'knowledge_ids': ['k1'], 'confidence': .5, 'reason': '不确定', 'evidence': '-7 / 2'}]
    updated = asyncio.run(bind_questions(course(), bank(), matcher=uncertain))
    assert binding_view(course(), updated)['counts']['pending'] == 1
    task = formal_task_from_question_bank_item(updated['items'][0])
    assert task['concept_ids'] == []
    assert freeze_knowledge_refs(course()['course_knowledge_base'], task) == {}


def test_no_tree_no_matching_or_mutation():
    assert asyncio.run(bind_questions({'course_id': 'c1'}, bank(), matcher=None)) == bank()
    assert binding_view({'course_id': 'c1'}, bank())['tree_ready'] is False


def test_generated_exact_binding_does_not_call_model():
    bundle = bank()
    bundle['items'][0].update(assessment_binding_schema='atomic_assessment_v1',
        primary_knowledge_ids=['k1'], course_knowledge_refs=['k1'],
        knowledge_revision_refs={'k1': 'kr1'}, knowledge_baseline_revision='tree1')
    assert binding_view(course(), bundle)['counts']['bound'] == 1
    assert asyncio.run(bind_questions(course(), bundle, matcher=None)) == bundle


def test_foreign_ids_or_missing_model_rows_fail_without_partial_write():
    for rows in ([], [{'revision_id': 'r1', 'knowledge_ids': ['foreign'], 'confidence': .99, 'reason': 'x', 'evidence': '-7 / 2'}]):
        async def bad(items, points):
            return rows
        original = bank()
        before = deepcopy(original)
        with pytest.raises(ValueError):
            asyncio.run(bind_questions(course(), original, matcher=bad))
        assert original == before
