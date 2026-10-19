"""Regression for the L4 duplicate and correction-boundary failures."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_extraction_repair import point, value, keep_review
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


@pytest.mark.asyncio
async def test_field_patch_never_reserializes_or_changes_frozen_math(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(subject='入栈方法', value='a+b-1', conditions=['a表示长度', 'b表示长度'])])
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:0': {'handling': 'patch', 'patch': {'subject': '入栈'}, 'reason': '只选择来源主体'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    result = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    actual = result['passages']['S1.1']['points'][0]
    assert actual == {**original['passages']['S1.1']['points'][0], 'subject': '入栈'}


@pytest.mark.asyncio
async def test_append_conditions_preserves_frozen_scope_without_model_retyping(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(property='时间复杂度', value='O(n)', conditions=['本讲  特定实现'])])
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:0': {'handling': 'patch',
            'patch': {'append_conditions': ['n表示栈中元素数']}, 'reason': '只新增定义'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    result = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    assert result['passages']['S1.1']['points'][0]['conditions'] == ['本讲  特定实现', 'n表示栈中元素数']


@pytest.mark.asyncio
async def test_explicit_equivalence_merges_wording_variants_without_losing_attachments(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    from knowledge_extract import compile_extraction
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(value='插入栈顶'), point(value='将元素插入栈顶',
        attachments=[{'name': '示例', 'kind': 'example', 'claim': '将元素放入栈顶'}])])
    async def call(*args):
        payload = json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        assert payload['duplicate_question_groups'] == [['S1.1:0', 'S1.1:1']]
        return json.dumps({'repairs': {
            'S1.1:0': {'handling': 'replace', 'points': [deepcopy(original['passages']['S1.1']['points'][0])], 'reason': '规范命题'},
            'S1.1:1': {'handling': 'merge', 'merge_into': 'S1.1:0', 'reason': '两者均表示元素插入栈顶，来源支持等价'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, record)
    result = compile_extraction(raw, context, ['S1'], 1, corrected)
    assert result['report']['ready_for_adoption']
    assert len(result['tree']['knowledge_points']) == 1
    assert len(result['tree']['knowledge_points'][0]['inventory_attachments']) == 1


@pytest.mark.asyncio
async def test_equivalence_cannot_merge_unrelated_questions(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(subject='入栈方法'), point(subject='出栈方法')])
    async def call(*args):
        return json.dumps({'repairs': {
            'S1.1:0': {'handling': 'merge', 'merge_into': 'S1.1:1', 'reason': '越界合并'},
            'S1.1:1': {'handling': 'patch', 'patch': {'subject': '出栈'}, 'reason': '修正主体'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    with pytest.raises(CourseDocumentConflict):
        await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})


@pytest.mark.asyncio
async def test_cross_batch_wording_collision_is_reconciled_before_classification(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    state = svc.authoring.load('c-pilot')
    blocks = state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks']
    blocks.append({**deepcopy(blocks[0]), 'block_id': 'another-source'})
    svc.authoring._save(state)
    monkeypatch.setattr('knowledge_extract.extraction_groups', lambda context: [['S1'], ['S2']])
    calls = []
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'content_review': return json.dumps(keep_review(payload))
        if payload['stage'] == 'extract':
            k = payload['source_passages'][0]['key']
            return json.dumps({'response_contract': 'knowledge_extract_v9', 'passages': {k: {'points': [
                point(value='插入栈顶' if k == 'S1.1' else '将元素插入栈顶')], 'note': None}}, 'source_issues': []})
        assert payload['stage'] == 'extract_repair'
        return json.dumps({'repairs': {
            'S1.1:0': {'handling': 'replace', 'points': [point(value='插入栈顶')], 'reason': '规范命题'},
            'S2.1:0': {'handling': 'merge', 'merge_into': 'S1.1:0', 'reason': '同一插入操作的同义总结'}}, 'source_issues': []})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test', client=None)
    job = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed'
    assert calls.count('extract_repair') == 1
    candidate = saved['checkpoint']['candidate']
    assert candidate['atomic_assessment']['ready_for_adoption']
    assert len(candidate['knowledge_points']) == 1
    assert len(candidate['knowledge_points'][0]['source_quotes']) == 2
    assert saved['checkpoint']['atomic_pipeline']['reconciliation']['status'] == 'completed'


def test_complexity_notation_is_not_an_execution_trace():
    from knowledge_semantic_contract import quality_point
    compiled, _ = quality_point(point(subject='入栈', property='O(1)成立前提', value='容量充足'), '入栈在容量充足时为O(1)。')
    assert compiled['claim'] == '入栈的O(1)成立前提为容量充足。'


@pytest.mark.asyncio
async def test_invalid_correction_is_completed_inside_one_bounded_transaction(svc, monkeypatch):
    from knowledge_extraction_repair import correct_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(property='时间复杂度', value='O(n)', conditions=['本讲实现'])]); calls = []
    async def call(*args):
        payload = json.loads(args[-2].split('\nINPUT_JSON:\n')[1]); calls.append(payload)
        correction = {'append_conditions': ['n表示元素数']} if len(calls) == 2 else {'subject': '入栈'}
        return json.dumps({'repairs': {'S1.1:0': {'handling': 'patch', 'patch': correction, 'reason': '定点修正'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    result, _ = await correct_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, record,
        compile_result=lambda corrected: corrected, validate_source=lambda: None, max_attempts=2)
    assert len(calls) == 2 and calls[1]['correction_feedback']['diagnostic']
    assert len(record['attempts']) == 2 and record['attempts'][0]['status'] == 'failed'
    assert result['passages']['S1.1']['points'][0]['conditions'] == ['本讲实现', 'n表示元素数']


@pytest.mark.asyncio
@pytest.mark.parametrize('issue_recorded', [False, True])
async def test_unsupported_source_has_an_explicit_auditable_abstention(svc, monkeypatch, issue_recorded):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(subject='材料中不存在的结构')])
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:0': {'handling': 'source_issue', 'points': [], 'reason': '当前块未提供该结构结论，不能替换为另一个结构'}},
            'source_issues': [{'passage_key': 'S1.1', 'kind': 'suspected_error', 'detail': '候选知识与绑定来源不符'}] if issue_recorded else []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if not issue_recorded:
        with pytest.raises(CourseDocumentConflict):
            await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    else:
        record = {}; result = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, record)
        assert result['passages']['S1.1']['points'] == []
        assert result['source_issues'][0]['detail']
        assert record['decisions'][0]['action'] == 'source_issue'


@pytest.mark.asyncio
async def test_transport_error_during_correction_is_preserved_without_retry(svc, monkeypatch):
    from knowledge_extraction_repair import correct_points
    from knowledge_atomic import KnowledgeModelDegenerateOutput
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu'); calls = []
    async def call(*args):
        calls.append(1); raise KnowledgeModelDegenerateOutput('真实空白退化故障')
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    with pytest.raises(KnowledgeModelDegenerateOutput):
        await correct_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1,
            value([point(subject='不存在')]), record, compile_result=lambda v: v, validate_source=lambda: None, max_attempts=2)
    assert calls == [1]
    assert record['attempts'][0]['validation_error']['code'] == 'KnowledgeModelDegenerateOutput'
