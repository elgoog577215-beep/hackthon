"""Regression for the L4 duplicate and correction-boundary failures."""
from copy import deepcopy
import json

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course
from backend.tests.test_knowledge_extraction_repair import point, value
from course_repository import CourseDocumentConflict


@pytest.mark.parametrize('different_conditions', [False, True])
def test_within_batch_duplicates_consolidate_before_identity_validation(svc, monkeypatch, different_conditions):
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    first = point(); second = point(conditions=['栈未满'] if different_conditions else [],
        attachments=[{'name': '插入说明', 'kind': 'example', 'claim': '将元素放到栈顶'}])
    response = value([first, second]); response['_content_review_trace'] = [{'origin': 'A'}, {'origin': 'B'}]
    before = deepcopy(response)
    result = compile_extraction(raw, context, ['S1'], 3, response)
    points = result['tree']['knowledge_points']
    assert len(points) == (2 if different_conditions else 1)
    assert result['report']['ready_for_adoption']
    assert response == before
    if not different_conditions:
        assert points[0]['inventory_keys'] == ['I3_P1', 'I3_P2', 'I3_P2A1']
        assert len(points[0]['inventory_attachments']) == 1
        assert points[0]['content_review']['equivalent_reviews'] == [{'origin': 'A'}, {'origin': 'B'}]
        assert len(result['report']['atomicity_checks']) == 2
        assert {tuple(row['point_keys']) for row in result['report']['coverage']} == {('K1',)}


@pytest.mark.asyncio
@pytest.mark.parametrize('mutate', [False, True])
async def test_quantity_only_repair_has_one_shared_immutable_plan(svc, monkeypatch, mutate):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(property='时间复杂度', value='O(n)', conditions=['本讲实现'])])
    async def call(*args):
        payload = json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        target = payload['targets']['S1.1:0']
        assert target['correction_plan']['editable_fields'] == ['conditions']
        assert target['correction_plan']['required_symbols'] == ['n']
        corrected = deepcopy(original['passages']['S1.1']['points'][0])
        corrected['conditions'].append('n表示栈中元素的数量')
        if mutate: corrected['property'] = '最好、平均、最坏时间复杂度'
        return json.dumps({'repairs': {'S1.1:0': {'points': [corrected], 'handling': 'replace', 'reason': '定义输入规模'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if mutate:
        with pytest.raises(CourseDocumentConflict):
            await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    else:
        result = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
        assert result['passages']['S1.1']['points'][0]['property'] == '时间复杂度'


@pytest.mark.asyncio
async def test_data_errors_finish_independent_batches_once_but_never_claim_success():
    from knowledge_atomic import run_batches, KnowledgeBatchValidationError
    rows = [{'status': 'pending'} for _ in range(5)]; started = []
    async def process(index, row):
        started.append(index)
        if index in {1, 3}: raise KnowledgeBatchValidationError(f'inventory-{index}', '质量未通过')
        row['status'] = 'completed'
    with pytest.raises(KnowledgeBatchValidationError) as failed:
        await run_batches(rows, process, width=2)
    assert sorted(started) == [1, 2, 3, 4, 5]
    assert [e['batch_id'] for e in failed.value.failures] == ['inventory-1', 'inventory-3']
    assert [r['status'] for r in rows] == ['pending', 'completed', 'pending', 'completed', 'completed']
