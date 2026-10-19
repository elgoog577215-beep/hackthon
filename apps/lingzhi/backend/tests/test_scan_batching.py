"""Budget packing must reduce requests without reducing complete scan coverage."""
from copy import deepcopy

import pytest

from ai_base import AIBase
from course_evolution.scan_batching import pack_scan_batches
from course_evolution.scan_prompt import build_scan_prompt, SCAN_SYSTEM_PROMPT, SCAN_INPUT_TOKEN_LIMIT
from course_evolution.semantic_scan import scan_batches


def fragments(count=20):
    return [{'unit_id': f'u{i}', 'title': f'第{i}讲', 'asset_type': 'script',
             'content': '完整课程内容与约束。' * 100, 'part': 1, 'parts': 1,
             'editable_fields': {'markdown': '完整课程内容与约束。' * 100}}
            for i in range(count)]


def test_packing_reduces_calls_with_identical_order_and_text():
    items = fragments()
    original = deepcopy(items)
    optimized = pack_scan_batches(items, overview={}, instruction='补充适用条件')
    legacy = pack_scan_batches(items, overview={}, instruction='补充适用条件', legacy=True)
    assert len(optimized) < len(legacy)
    assert [item for batch in optimized for item in batch] == original
    assert items == original
    for batch in optimized:
        assert len(batch) <= 8
        prompt = build_scan_prompt({}, batch, '补充适用条件')
        assert AIBase.estimate_request_tokens(prompt, SCAN_SYSTEM_PROMPT) <= SCAN_INPUT_TOKEN_LIMIT


def test_large_course_overview_is_included_in_every_batch_budget():
    items = fragments()
    large = {'outline': '课程目标与不可修改的限制。' * 260}
    ordinary = pack_scan_batches(items, overview={}, instruction='检查')
    limited = pack_scan_batches(items, overview=large, instruction='检查')
    assert len(limited) > len(ordinary)
    assert [item for batch in limited for item in batch] == items
    for batch in limited:
        assert AIBase.estimate_request_tokens(build_scan_prompt(large, batch, '检查'), SCAN_SYSTEM_PROMPT) <= SCAN_INPUT_TOKEN_LIMIT


@pytest.mark.asyncio
async def test_live_findings_are_bounded_and_do_not_expose_patch_payloads():
    items = fragments(12)
    items[0]['block_title'] = '画像中的证据与推断'
    events = []
    async def analyze(overview, batch, instruction):
        return {'affected_units': [{'unit_id': item['unit_id'], 'reason': '补充边界。' * 200,
                 'content_patches': [{'before': 'PRIVATE_ORIGINAL', 'after': 'PRIVATE_CANDIDATE'}]} for item in batch]}
    async def progress(detail, checkpoint):
        events.append(deepcopy(detail))
    _, scanned, missing, failures, _ = await scan_batches(
        overview={}, batches=[items[:6], items[6:]], instruction='补充边界',
        revisions={}, analyzer=analyze, on_progress=progress,
    )
    assert len(scanned) == 12 and not missing and not failures
    first = next(event for event in events if event.get('finding_count'))
    assert first['completed_parts'] < first['total_parts']
    assert events[-1]['finding_count'] == 12
    assert len(events[-1]['findings']) == 8
    assert events[-1]['findings'][0]['title'] == '画像中的证据与推断'
    assert all(len(finding['reason']) <= 320 for finding in events[-1]['findings'])
    assert 'PRIVATE_' not in str(events)
