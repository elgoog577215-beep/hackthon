import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from course_repository import CourseDocumentConflict


def point(subject='入栈', **extra):
    return {'form': 'fact', 'subject': subject, 'property': '操作效果', 'value': '将元素插入栈顶', 'conditions': [], 'attachments': [], **extra}


def value(points):
    return {'response_contract': 'knowledge_extract_v9', 'passages': {'S1.1': {'points': points, 'note': None}}, 'source_issues': []}


def keep_review(payload):
    return {'point_reviews': {key: {'decision': 'keep', 'points': [], 'reason': '隔离夹具保留原点'} for key in payload['points']},
            'additions': {p['key']: [] for p in payload['source_passages']}, 'source_issues': []}


@pytest.mark.asyncio
@pytest.mark.parametrize('subject,tool', [('DFS', '栈'), ('BFS', '队列')])
@pytest.mark.parametrize('preserve', [False, True])
async def test_mechanism_to_definition_repair_must_keep_its_valid_implementation_scope(svc, monkeypatch, subject, tool, preserve):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw=svc.repository.load_raw('c-pilot');context=svc._context(raw,'handouts','cpu')
    scope=f'本讲基于显式{tool}实现'
    source=f'{subject}使用{tool}探索节点，只描述访问顺序与机制。'
    passages=[dict(key='S1.1',source_key='S1',text=source,start=0,end=len(source))]
    for module in ('knowledge_extraction_repair','knowledge_semantic_contract'):
        monkeypatch.setattr(module+'.passage_catalog',lambda *a,**k:deepcopy(passages))
    original=value([dict(form='procedure',subject=subject,goal='搜索节点',steps=['访问当前节点'],
                        completion='处理完节点',conditions=[scope],attachments=[])])
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        if preserve:assert payload['targets']['S1.1:0']['required_conditions']==[scope]
        corrected=dict(form='definition',subject=subject,meaning='一种节点访问策略',constraints=[],conditions=[scope] if preserve else [],attachments=[])
        return json.dumps({'repairs':{'S1.1:0':{'points':[corrected],'handling':'replace','reason':'改为策略定义，保留实现范围'}},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    if preserve:
        corrected=await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})
        assert corrected['passages']['S1.1']['points'][0]['conditions']==[scope]
    else:
        with pytest.raises(CourseDocumentConflict,match='前提|conditions'):
            await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})


def test_small_repair_schema_enforces_the_exact_field_that_failed():
    from jsonschema import Draft202012Validator
    from knowledge_extraction_repair import repair_schema
    targets = {'S1.1:0': {'point': point(property='效果和端点'), 'passage_key': 'S1.1'}}
    validator = Draft202012Validator(repair_schema(targets, {'S1.1': '入栈将元素插入栈顶。出栈移除元素。'}))
    result = {'repairs': {'S1.1:0': {'points': [point()], 'handling': 'replace', 'reason': '修正属性'}}, 'source_issues': []}
    assert validator.is_valid(result)
    result['repairs']['S1.1:0']['points'][0]['property'] = '效果和端点'
    assert not validator.is_valid(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('out_of_scope', [False, True])
async def test_one_scoped_repair_preserves_valid_points_and_original_response(svc, monkeypatch, out_of_scope):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(), point('出栈', property='效果和端点')]); before = deepcopy(original)
    calls = []
    async def call(*args):
        calls.append(args[-1])
        return json.dumps({'repairs': {'S1.1:0' if out_of_scope else 'S1.1:1': {
            'points': [point('出栈', value='移除并返回栈顶元素')], 'handling': 'replace', 'reason': '仅保留一个操作效果属性'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if out_of_scope:
        with pytest.raises(CourseDocumentConflict): await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    else:
        record = {}
        corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, record)
        assert corrected['passages']['S1.1']['points'][0] == original['passages']['S1.1']['points'][0]
        assert record['target_keys'] == ['S1.1:1'] and record['raw_response']
        assert corrected['passages']['S1.1']['points'][1]['property'] == '操作效果'
    assert calls == ['extract_repair'] and original == before


@pytest.mark.asyncio
async def test_unaffected_context_note_is_not_overwritten_by_point_repair(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    passages = [{'key': 'S1.1', 'source_key': 'S1', 'text': '入栈将元素插入栈顶。', 'start': 0, 'end': 10},
                {'key': 'S2.1', 'source_key': 'S2', 'text': '本讲学习目标。', 'start': 0, 'end': 7}]
    monkeypatch.setattr('knowledge_extraction_repair.passage_catalog', lambda *args: deepcopy(passages))
    monkeypatch.setattr('knowledge_semantic_contract.passage_catalog', lambda *args: deepcopy(passages))
    original = value([point(property='效果和端点')])
    note = {'points': [], 'note': {'handling': 'context', 'reason': '仅为教学目标，不是知识命题'}}
    original['passages']['S2.1'] = deepcopy(note)
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:0': {'points': [point()], 'handling': 'replace', 'reason': '只改属性'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1', 'S2'], 1, original, {})
    assert corrected['passages']['S2.1'] == note


@pytest.mark.asyncio
async def test_split_repair_preserves_review_provenance_for_each_new_point(svc, monkeypatch):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(), point('出栈', property='效果和端点')])
    original['_content_review_trace'] = [{'point_review_key': 'A'}, {'point_review_key': 'B'}]
    async def call(*args):
        return json.dumps({'repairs': {'S1.1:1': {'points': [point('出栈', value='移除并返回栈顶元素'),
                point('出栈', property='返回对象', value='栈顶元素')], 'handling': 'replace', 'reason': '分别保留两个检查角度'}}, 'source_issues': []})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, original, {})
    assert [t['point_review_key'] for t in corrected['_content_review_trace']] == ['A', 'B', 'B']
    assert corrected['_content_review_trace'][1]['structural_repair_target'] == 'S1.1:1'


@pytest.mark.asyncio
@pytest.mark.parametrize('preserve', [False, True])
async def test_property_only_repair_preserves_valid_original_conditions(svc, monkeypatch, preserve):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(property='效果和端点', conditions=['栈未满'])])
    async def call(*args):
        payload = json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        if preserve: assert payload['targets']['S1.1:0']['required_conditions'] == ['栈未满']
        return json.dumps({'repairs': {'S1.1:0': {'points': [point(conditions=['栈未满'] if preserve else [])],
            'handling':'replace','reason':'只修正属性字段'}}, 'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    if preserve:
        await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})
    else:
        with pytest.raises(CourseDocumentConflict, match='前提'):
            await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})


@pytest.mark.asyncio
@pytest.mark.parametrize('preserve', [False, True])
async def test_subject_only_repair_cannot_change_the_original_answer(svc, monkeypatch, preserve):
    from knowledge_extraction_repair import repair_points
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot'); context = svc._context(raw, 'handouts', 'cpu')
    original = value([point(subject='入栈方法', conditions=['栈未满'])])
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        if preserve: assert payload['targets']['S1.1:0']['fixed_fields']['value']=='将元素插入栈顶'
        return json.dumps({'repairs':{'S1.1:0':{'points':[point(value='将元素插入栈顶' if preserve else '删除整个栈',conditions=['栈未满'])],
            'handling':'replace','reason':'只修正主体'}},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    if preserve:
        await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})
    else:
        with pytest.raises(CourseDocumentConflict,match='主体'):
            await repair_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{})


@pytest.mark.asyncio
async def test_new_task_cannot_bypass_content_review_by_returning_an_old_contract(svc, monkeypatch):
    from backend.tests.test_knowledge_extract import response
    setup_course(svc, monkeypatch)
    calls = []
    async def model(prompt, **kwargs): calls.append(prompt); return json.dumps(response())
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed' and len(calls) == 1
    assert '合同' in saved['error']['message']


@pytest.mark.asyncio
async def test_extraction_repair_is_bounded_to_one_request_and_preserves_failure(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = []; options = []; feedbacks = []
    async def model(prompt, **kwargs):
        options.append(kwargs)
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'content_review':
            feedbacks.append(payload.get('previous_attempt_feedback'))
            return json.dumps(keep_review(payload))
        if payload['stage'] == 'extract': return json.dumps(value([point(property='效果和端点')]))
        return json.dumps({'repairs': {'S1.1:0': {'points': [point(property='仍然和无效')], 'handling': 'replace', 'reason': '修复失败'}}, 'source_issues': []})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1')
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'failed' and calls == ['extract', 'content_review', 'extract_repair']
    batch = saved['checkpoint']['atomic_pipeline']['inventory_batches'][0]
    assert batch['raw_response'] and batch['repair']['raw_response']
    assert batch['repair']['status'] == 'failed'
    assert 'json_schema' not in options[-1]  # Validate the small contract locally too.
    original = deepcopy(saved)
    resumed = start(svc, 'new-isolated-attempt', resume_job_id=job['id'])
    copied = resumed['checkpoint']['atomic_pipeline']['inventory_batches'][0]
    assert all(field not in copied for field in ('repair', 'content_review', 'validation_error', 'raw_response'))
    assert copied['retry_feedback']['previous_batch_error']['message']
    assert copied['retry_feedback']['failed_correction_response']
    assert svc.authoring.get_job('c-pilot', job['id']) == original
    await svc.run('c-pilot', resumed['id'])
    assert calls == ['extract', 'content_review', 'extract_repair', 'content_review', 'extract_repair']
    assert feedbacks == [None, copied['retry_feedback']]
    assert svc.authoring.get_job('c-pilot', job['id']) == original


@pytest.mark.asyncio
async def test_ambiguous_repeated_question_is_repaired_without_rewriting_other_points(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    state = svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] += '栈的判空检查栈是否为空。队列的判空检查队列是否为空。'
    svc.authoring._save(state)
    calls = []
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'content_review': return json.dumps(keep_review(payload))
        if payload['stage'] == 'extract':
            return json.dumps(value([point('判空', property='检查对象', value='栈是否为空'), point('判空', property='检查对象', value='队列是否为空')]))
        return json.dumps({'repairs': {f'S1.1:{i}': {'points': [point(subject, property='判空检查对象', value=subject+'是否为空')],
                    'handling': 'replace', 'reason': '明确操作所属结构'} for i, subject in enumerate(['栈', '队列'])}, 'source_issues': []})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert calls == ['extract', 'content_review', 'extract_repair'] and saved['status'] == 'completed'
    points = saved['checkpoint']['candidate']['knowledge_points']
    assert len({p['meta_question'] for p in points}) == 2


@pytest.mark.asyncio
async def test_exact_duplicate_claims_keep_one_identity_and_all_inventory_pointers(svc, monkeypatch):
    from backend.tests.test_knowledge_atomic import provider
    from knowledge_atomic import assemble
    setup_course(svc, monkeypatch); provider(svc)
    job = start(svc); await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    pipeline = deepcopy(saved['checkpoint']['atomic_pipeline'])
    pipeline['prompt_contract'] = 'knowledge_extract_v9'
    copied = deepcopy(pipeline['batches'][0]); copied['id'] = 'duplicate-batch'
    copied['tree']['knowledge_points'][0]['inventory_keys'] = ['another-inventory-pointer']
    pipeline['batches'].append(copied)
    before = deepcopy(pipeline)
    result = assemble(svc.repository.load_raw('c-pilot'), saved['request_snapshot']['knowledge_generation_context'], pipeline)
    assert len(result['knowledge_points']) == 2
    assert len(result['atomic_assessment']['exact_duplicate_consolidations']) == 1
    assert 'another-inventory-pointer' in result['knowledge_points'][0]['inventory_keys']
    assert pipeline == before
    assert result['atomic_assessment']['content_review']['missing_batches'] == 1
    assert result['atomic_assessment']['ready_for_adoption'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('review_fails', [False, True])
async def test_new_candidate_revision_reuses_extraction_and_never_bypasses_review(svc, monkeypatch, review_fails):
    setup_course(svc, monkeypatch); calls = []; revising = False
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'extract': return json.dumps(value([point()]))
        if payload['stage'] == 'content_review':
            result = keep_review(payload)
            if revising and review_fails: result['point_reviews'] = {}
            return json.dumps(result)
        raise AssertionError('Old leaf generation must not bypass the v9 review contract')
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    original = start(svc, extraction_mode='single_pass_v1'); await svc.run('c-pilot', original['id'])
    before = svc.authoring.get_job('c-pilot', original['id']); assert before['status'] == 'completed'
    calls.clear(); revising = True
    revised = start(svc, 'explicit-revision', resume_job_id=original['id'], retry_batch_id='all_atoms')
    references = revised['checkpoint']['atomic_pipeline']['review_reference_catalog']
    assert references[0]['knowledge_id'] == before['checkpoint']['candidate']['knowledge_points'][0]['knowledge_id']
    assert references[0]['meta_question'] == before['checkpoint']['candidate']['knowledge_points'][0]['meta_question']
    await svc.run('c-pilot', revised['id']); saved = svc.authoring.get_job('c-pilot', revised['id'])
    assert calls == ['content_review']
    assert saved['status'] == ('failed' if review_fails else 'completed')
    assert svc.authoring.get_job('c-pilot', original['id']) == before
