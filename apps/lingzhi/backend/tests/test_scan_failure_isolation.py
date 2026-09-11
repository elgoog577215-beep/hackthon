"""A failed unit must not turn unattempted neighbours into failed checks."""
from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from course_evolution.semantic_scan import scan_batches


def result(items):
    return {'affected_units': [{'unit_id': i['unit_id']} for i in items]}


async def no_wait(seconds):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize('mixed', [False, True])
async def test_one_bad_unit_is_isolated_and_neighbours_finish(mixed):
    calls, snapshots = [], []
    items = [{'unit_id': 'bad', 'part': 1}, {'unit_id': 'bad', 'part': 2},
             {'unit_id': 'good'}, {'unit_id': 'other'}]
    async def analyze(overview, batch, instruction):
        calls.append(deepcopy(batch))
        if any(i['unit_id'] == 'bad' for i in batch):
            raise AIProviderRequestError('empty_response')
        return result(batch)
    async def report(detail, checkpoint):
        snapshots.append(detail)
    _, checked, missing, failures, _ = await scan_batches(
        overview={}, batches=[items] if mixed else [[i] for i in items], instruction='practice',
        revisions={}, analyzer=analyze, sleep=no_wait, on_progress=report)
    assert checked == {'good', 'other'} and missing == {'bad'}
    assert not snapshots[-1].get('provider_recovery_failed')
    assert snapshots[-1]['failed_parts'] == 1
    assert snapshots[-1]['deferred_parts'] == 1
    assert snapshots[-1]['completed_parts'] == 2
    assert not any(len(c) == 1 and c[0].get('part') == 2 for c in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('cached_success', [False, True])
async def test_only_fresh_provider_success_resets_outage_evidence(cached_success):
    batches = [[{'unit_id': u}] for u in ['bad1', 'bad2', 'healthy', 'bad3', 'last']]
    checkpoint, snapshots, calls = {}, [], []
    async def report(detail, saved):
        checkpoint.update(deepcopy(saved))
        snapshots.append(detail)
    async def initial(overview, items, instruction):
        if items[0]['unit_id'] != 'healthy':
            raise ValueError('invalid result')
        return result(items)
    if cached_success:
        await scan_batches(overview={}, batches=batches, instruction='x', revisions={},
                           analyzer=initial, on_progress=report)
    async def analyze(overview, items, instruction):
        u = items[0]['unit_id']
        calls.append(u)
        if u.startswith('bad'):
            raise AIProviderRequestError('empty_response')
        return result(items)
    _, checked, missing, _, _ = await scan_batches(overview={}, batches=batches, instruction='x',
        revisions={}, analyzer=analyze, checkpoint=deepcopy(checkpoint), on_progress=report, sleep=no_wait)
    assert ('last' not in calls) == cached_success
    assert ('last' in missing) == cached_success
    assert 'healthy' in checked
    assert snapshots[-1].get('provider_recovery_failed', False) == cached_success


@pytest.mark.asyncio
async def test_timeout_recovery_keeps_successful_subfragments_on_next_retry():
    batches = [[{'unit_id': 'long', 'content': 'a' * 1200}], [{'unit_id': 'good'}]]
    checkpoint, snapshots, calls = {}, [], []
    async def report(detail, saved):
        checkpoint.update(deepcopy(saved))
        snapshots.append(detail)
    async def flaky(overview, items, instruction):
        i = items[0]
        if i['unit_id'] == 'long' and i.get('recovery_part') != 1:
            raise TimeoutError('provider timeout')
        return result(items)
    args = dict(overview={}, batches=batches, instruction='x', revisions={}, on_progress=report)
    _, checked, missing, _, _ = await scan_batches(**args, analyzer=flaky)
    assert checked == {'good'} and missing == {'long'}
    assert snapshots[-1]['failed_parts'] == 1 and snapshots[-1]['deferred_parts'] == 1
    async def healthy(overview, items, instruction):
        calls.extend(items)
        return result(items)
    _, checked, missing, _, _ = await scan_batches(**args, analyzer=healthy, checkpoint=deepcopy(checkpoint))
    assert checked == {'long', 'good'} and not missing
    assert [i['recovery_part'] for i in calls] == [2, 3]
    assert snapshots[-1]['completed_parts'] == snapshots[-1]['total_parts'] == 4


@pytest.mark.asyncio
async def test_mixed_batch_timeout_isolates_bad_leaf_and_resumes_only_that_leaf():
    batch = [{'unit_id': u} for u in ['good1', 'bad', 'good2', 'good3']]
    checkpoint, calls = {}, []
    async def report(detail, saved):
        checkpoint.update(deepcopy(saved))
    async def flaky(overview, items, instruction):
        if any(i['unit_id'] == 'bad' for i in items):
            raise TimeoutError('provider timeout')
        return result(items)
    args = dict(overview={}, batches=[batch], instruction='x', revisions={}, on_progress=report)
    _, checked, missing, _, _ = await scan_batches(**args, analyzer=flaky)
    assert checked == {'good1', 'good2', 'good3'} and missing == {'bad'}
    async def healthy(overview, items, instruction):
        calls.extend(i['unit_id'] for i in items)
        return result(items)
    _, checked, missing, _, _ = await scan_batches(**args, analyzer=healthy, checkpoint=deepcopy(checkpoint))
    assert not missing and len(checked) == 4
    assert calls == ['bad']
