"""Validation boundaries retain valid artifacts and repair only diagnosed fields."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_extract import review_response
from backend.tests.test_knowledge_extraction_repair import point, value
from course_repository import CourseDocumentConflict

PROCESSING = 'knowledge_validation_pipeline_v4'


def context_for(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot')
    return raw, {**svc._context(raw, 'handouts', 'cpu'), 'expression_contract': 'knowledge_expression_v1',
                 'content_review_contract': 'knowledge_content_review_v3', 'knowledge_validation_contract': PROCESSING}


async def pending_review(svc, monkeypatch):
    from knowledge_content_review import review_content
    raw, context = context_for(svc, monkeypatch)
    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n')[1]); result = review_response(data)
        result['point_reviews']['S1.1:0']['names'] = ['入栈的操作效果']
        return json.dumps(result)
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}; extracted = value([point()])
    reviewed = await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], extracted, record)
    return raw, context, extracted, reviewed, record


@pytest.mark.asyncio
async def test_semantic_review_is_checkpointed_while_invalid_expression_remains_unpublishable(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    raw, context, extracted, reviewed, record = await pending_review(svc, monkeypatch)
    assert reviewed['passages'] == extracted['passages']
    assert record['status'] == 'completed' and record['reviewed_response'] == reviewed
    assert record['expression_issues'][0]['point_key'] == 'S1.1:0'
    assert record['expression_issues'][0]['field'] == 'name'
    assert reviewed['_content_review_trace'][0]['expression']['status'] == 'pending'
    with pytest.raises(CourseDocumentConflict, match='短陈述') as error:
        compile_extraction(raw, context, ['S1'], 1, reviewed)
    assert error.value.diagnostics[0]['code'] == 'invalid_short_statement'
    assert error.value.diagnostics[0]['point_key'] == 'S1.1:0'


@pytest.mark.asyncio
@pytest.mark.parametrize('illegal_patch', [False, True])
async def test_name_only_error_has_a_name_only_action_and_cannot_change_semantic_slots(svc, monkeypatch, illegal_patch):
    from knowledge_extraction_repair import repair_points
    from knowledge_extract import compile_extraction
    raw, context, _, reviewed, _ = await pending_review(svc, monkeypatch)
    before = deepcopy(reviewed); calls = []
    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n')[1]); calls.append(data)
        target = data['targets']['S1.1:0']
        assert target['correction_plan']['expression_only'] is True
        assert target['correction_plan']['editable_fields'] == []
        assert target['current_name'] == '入栈的操作效果'
        action = {'handling': 'rename', 'reason': '只将标题改为完整陈述'}
        if illegal_patch: action.update(handling='patch', patch={'value': '删除栈顶元素'})
        return json.dumps({'repairs': {'S1.1:0': action}, 'short_statements': {'S1.1:0': ['入栈把元素加入栈顶']}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if illegal_patch:
        with pytest.raises(CourseDocumentConflict): await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, reviewed, {})
    else:
        repaired = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, reviewed, {})
        assert repaired['passages'] == reviewed['passages']
        tree = compile_extraction(raw, context, ['S1'], 1, repaired)['tree']
        assert tree['knowledge_points'][0]['name'] == '入栈把元素加入栈顶'
    assert reviewed == before and len(calls) == 1


def test_expression_diagnostic_does_not_widen_an_existing_semantic_field_restriction():
    from knowledge_correction_plan import correction_plan
    plan = correction_plan(point(), [{'code': 'source_subject', 'message': '主体缺来源'},
                                    {'code': 'invalid_short_statement', 'message': '名称不完整'}])
    assert plan['editable_fields'] == ['conditions', 'subject']
    assert plan['fixed_fields']['value'] == point()['value'] and not plan['expression_only']


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['none', 'source', 'extraction'])
async def test_frozen_valid_review_replays_without_a_model_request_and_is_bound_to_its_inputs(svc, monkeypatch, mutation):
    from knowledge_content_review import review_content
    from knowledge_review_protocol import freeze_review
    from knowledge_compact import passage_catalog
    raw, context, extracted, _, record = await pending_review(svc, monkeypatch)
    frozen = freeze_review(record, extracted, context, ['S1'], origin_job_id='old-job')
    assert frozen and frozen['origin_job_id'] == 'old-job'
    if mutation == 'extraction': extracted['passages']['S1.1']['points'][0]['value'] = '删除栈顶元素'
    if mutation == 'source':
        catalog = passage_catalog({**context, 'knowledge_passage_mode':'source_blocks_v1'}, ['S1'])
        catalog[0]['text'] += '来源已经变化。'
        monkeypatch.setattr('knowledge_compact.passage_catalog', lambda *a, **kw: deepcopy(catalog))
        monkeypatch.setattr('knowledge_content_review.passage_catalog', lambda *a, **kw: deepcopy(catalog))
    async def forbidden(*args): raise AssertionError('Replay must never request another semantic review')
    monkeypatch.setattr('knowledge_atomic.call_stage', forbidden)
    if mutation != 'none':
        with pytest.raises(CourseDocumentConflict, match='冻结核对'):
            await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], extracted, {}, frozen=frozen)
    else:
        replay = {}
        await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], extracted, replay, frozen=frozen)
        assert replay['review_origin_job_id'] == 'old-job'
        assert replay['raw_response'] == record['raw_response']


@pytest.mark.asyncio
async def test_invalid_review_structure_cannot_be_reused_as_an_accepted_artifact(svc, monkeypatch):
    from knowledge_review_protocol import freeze_review
    _, context, extracted, _, record = await pending_review(svc, monkeypatch)
    parsed = json.loads(record['raw_response']); del parsed['addition_names']
    record['raw_response'] = json.dumps(parsed)
    assert freeze_review(record, extracted, context, ['S1'], origin_job_id='old-job') is None


@pytest.mark.asyncio
async def test_explicit_continue_reuses_review_and_upgrades_only_the_incomplete_v3_batch(svc, monkeypatch):
    setup_course(svc, monkeypatch); calls = []; correction_payloads = []; correcting = False
    async def model(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); stage = data['stage']; calls.append(stage)
        if stage == 'extract': return json.dumps(value([point()]))
        if stage == 'content_review':
            out = review_response(data); out['point_reviews']['S1.1:0']['names'] = ['入栈的操作效果']; return json.dumps(out)
        if stage == 'extract_repair':
            correction_payloads.append(deepcopy(data))
            return json.dumps({'repairs': {'S1.1:0': {'handling':'rename','reason':'只修表达'}},
                'short_statements': {'S1.1:0': ['入栈把元素加入栈顶' if correcting else '入栈的操作效果']}, 'source_issues':[]})
        raise AssertionError(stage)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', job['id'])
    failed = svc.authoring.get_job('c-pilot', job['id'])
    assert failed['status'] == 'failed'
    assert calls == ['extract','content_review','extract_repair','extract_repair']
    # Reproduce the already-persisted v3 failure without changing its source.
    cp = deepcopy(failed['checkpoint']); cp['atomic_pipeline']['processing_contract'] = 'knowledge_validation_pipeline_v3'
    svc.authoring.update_job('c-pilot', job['id'], checkpoint=cp)
    original = deepcopy(svc.authoring.get_job('c-pilot', job['id']))
    calls.clear(); correction_payloads.clear(); correcting = True
    resumed = start(svc, 'continue-only-invalid-expression', resume_job_id=job['id'])
    assert resumed['checkpoint']['atomic_pipeline']['processing_contract'] == PROCESSING
    await svc.run('c-pilot', resumed['id']); saved = svc.authoring.get_job('c-pilot', resumed['id'])
    assert saved['status'] == 'completed', saved.get('error')
    assert calls == ['extract_repair']
    assert svc.authoring.get_job('c-pilot', job['id']) == original
    batch = saved['checkpoint']['atomic_pipeline']['inventory_batches'][0]
    assert batch['content_review']['review_origin_job_id'] == job['id']
    assert 'previous_attempt_feedback' not in batch['content_review']
    assert correction_payloads[0]['correction_feedback']['previous_batch_error']
    assert saved['checkpoint']['candidate']['knowledge_points'][0]['name'] == '入栈把元素加入栈顶'
