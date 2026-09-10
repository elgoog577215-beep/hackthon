"""Regression for 86 completed observations becoming a retry chain of only seven."""
from copy import deepcopy

import pytest

from backend.tests.test_teacher_semantic_scan_recovery import scan_context, response
from course_evolution.scan_recovery import directly_failed_units, historical_scan_results
from course_evolution.semantic_scan import scan_batches
from course_evolution.teacher_planning import create_teacher_course_change_plan


async def history(tmp_path):
    repo, context = scan_context(tmp_path)

    async def older(overview, items, instruction):
        if any(i['unit_id'] == 'u3' for i in items):
            raise ValueError('invalid envelope')
        return response(items, [])

    first = await create_teacher_course_change_plan(
        context=context, user_id='teacher', request_id='older', instruction='Add practice',
        repository=repo, analyzer=older, scan_model_identity='model-v1')
    first.change_sets[-1].status = 'rejected'
    repo.save(first)

    async def newer(overview, items, instruction):
        if any(i['unit_id'] != 'u0' for i in items):
            raise ValueError('invalid envelope')
        return response(items, [])

    state = await create_teacher_course_change_plan(
        context=context, user_id='teacher', request_id='newer', instruction='Add practice',
        repository=repo, analyzer=newer, scan_model_identity='model-v1')
    assert state.change_sets[0].impact_summary['coverage']['scanned_units'] == 3
    assert state.change_sets[-1].impact_summary['coverage']['scanned_units'] == 1
    return repo, context, state


@pytest.mark.asyncio
async def test_retry_recovers_compatible_history_without_reviving_review_authority(tmp_path):
    repo, context, state = await history(tmp_path)
    old, source = state.change_sets
    seen, events = [], []

    async def analyzer(overview, items, instruction):
        seen.extend(i['unit_id'] for i in items)
        return response(items, [])

    async def progress(detail, checkpoint):
        events.append(detail)

    result = await create_teacher_course_change_plan(
        context=context, user_id='teacher', request_id='retry', instruction='Add practice',
        repository=repo, analyzer=analyzer, supersedes_plan_id=source.change_set_id,
        rescan_incomplete_only=True, scan_model_identity='model-v1', on_scan_progress=progress)
    plan = result.change_sets[-1]
    assert set(seen) == {'u3'}
    assert events[0]['retained_units'] == 3
    assert plan.impact_summary['coverage']['scanned_units'] == 4
    assert plan.impact_summary['coverage']['historical_reuse'] == [
        {'plan_id': old.change_set_id, 'unit_ids': ['u1', 'u2']}]
    assert result.change_sets[0].status == 'rejected'
    assert plan.status == 'pending' and not plan.application_receipt
    assert not plan.selected_operation_ids


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['request', 'model', 'base', 'outline', 'scope', 'answers',
                                  'confirmation', 'contract', 'owner', 'course', 'applied', 'content'])
async def test_incompatible_history_is_not_reused(tmp_path, change):
    _, context, state = await history(tmp_path)
    old, source = state.change_sets
    if change == 'request':
        old.request_text = 'Different requirement'
    elif change == 'model':
        old.impact_summary['scan_model_identity'] = 'other-model'
    elif change == 'base':
        old.base_revision_vector = {'other': 'revision'}
    elif change == 'outline':
        old.impact_summary['current_outline'] = []
    elif change == 'scope':
        old.impact_summary['request_asset_types'] = ['ppt']
    elif change == 'answers':
        old.impact_summary['clarification_answer_digest'] = 'different-answers'
    elif change == 'confirmation':
        old.impact_summary['clarification_confirmation'] = {'confirmed_at': 'earlier'}
    elif change == 'contract':
        old.impact_summary['scan_contract'] = 'unknown-contract'
    elif change == 'owner':
        old.user_id = 'other-teacher'
    elif change == 'course':
        old.course_id = 'other-course'
    elif change == 'applied':
        old.status = 'applied'
    elif change == 'content':
        for unit in context.units:
            unit.text += 'changed with unchanged revision label'
    ids, analyses, origins = historical_scan_results(
        plans=state.change_sets, source=source, context=context, model_identity='model-v1',
        excluded_ids={'u0'})
    assert not ids and not analyses and not origins


@pytest.mark.asyncio
async def test_legacy_history_requires_exact_base_and_unit_revisions(tmp_path):
    _, context, state = await history(tmp_path)
    old, source = state.change_sets
    old.impact_summary.pop('scan_contract')
    old.impact_summary['coverage'].pop('source_fingerprints')
    context.units[1].source_revision = 'changed'
    ids, _, _ = historical_scan_results(plans=state.change_sets, source=source, context=context,
                                       model_identity='model-v1', excluded_ids={'u0'})
    assert ids == {'u2'}
    context.base_revision_vector['course'] = 'changed'
    assert not historical_scan_results(plans=state.change_sets, source=source, context=context,
                                      model_identity='model-v1', excluded_ids={'u0'})[0]


@pytest.mark.asyncio
async def test_retry_checks_untouched_work_before_previous_failure_and_keeps_batch_cache():
    saved, calls = {}, []
    batches = [[{'unit_id': uid, 'content': uid}] for uid in ['bad', 'cached', 'untouched']]

    async def report(detail, checkpoint):
        saved.update(deepcopy(checkpoint))

    async def first(overview, items, instruction):
        if items[0]['unit_id'] != 'cached':
            raise ValueError('invalid envelope')
        return response(items)

    args = dict(overview={}, batches=batches, instruction='practice', revisions={})
    await scan_batches(**args, analyzer=first, on_progress=report)

    async def retry(overview, items, instruction):
        calls.append(items[0]['unit_id'])
        if items[0]['unit_id'] == 'bad':
            raise ValueError('still invalid')
        return response(items)

    result = await scan_batches(**args, analyzer=retry, checkpoint=saved,
                                deprioritized_unit_ids={'bad'})
    assert calls[0] == 'untouched' and set(calls[1:]) == {'bad'}
    assert result[1] == {'cached', 'untouched'} and result[2] == {'bad'}


def test_deferred_siblings_are_not_treated_as_direct_failures():
    from types import SimpleNamespace
    plan = SimpleNamespace(impact_summary={'coverage': {'failed_batches': [
        {'unit_ids': ['bad', 'untouched'], 'deferred_parts': 20},
        {'unit_ids': ['bad2', 'bad3', 'untouched2'], 'deferred_parts': 10,
         'failed_unit_ids': ['bad2', 'bad3']},
    ]}})
    assert directly_failed_units(plan) == {'bad', 'bad2', 'bad3'}


@pytest.mark.asyncio
async def test_legacy_outline_without_node_revision_uses_exact_tree_but_not_other_unversioned_sources(tmp_path):
    from course_evolution.teacher_planning import _outline_units
    repo, context = scan_context(tmp_path)
    context.units = [_outline_units(context.outline)[0], context.units[0]]
    for unit in context.units:
        unit.source_revision = ''

    async def healthy(overview, items, instruction):
        return response(items, [])

    first = await create_teacher_course_change_plan(
        context=context, user_id='teacher', request_id='outline-old', instruction='Add practice',
        repository=repo, analyzer=healthy, scan_model_identity='model-v1')
    old = first.change_sets[0]
    old.impact_summary.pop('scan_contract')
    old.impact_summary['coverage'].pop('source_fingerprints')
    old.status = 'rejected'
    repo.save(first)

    async def failed(*args):
        raise ValueError('invalid envelope')

    state = await create_teacher_course_change_plan(
        context=context, user_id='teacher', request_id='outline-new', instruction='Add practice',
        repository=repo, analyzer=failed, scan_model_identity='model-v1')
    source = state.change_sets[-1]
    args = dict(plans=state.change_sets, source=source, context=context,
                model_identity='model-v1', excluded_ids=set())
    ids, _, _ = historical_scan_results(**args)
    assert ids == {context.units[0].unit_id}
    context.outline[0]['learning_objective'] = 'New learning objective'
    assert not historical_scan_results(**args)[0]
