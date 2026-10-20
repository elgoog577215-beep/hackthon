"""Short statements are bound presentation of complete, source-backed facts."""
from copy import deepcopy
import json

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start
from backend.tests.test_knowledge_extraction_repair import point, value
from course_repository import CourseDocumentConflict


CONTRACT = 'knowledge_expression_v1'


def current(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot')
    context = svc._context(raw, 'handouts', 'cpu')
    return raw, {**context, 'expression_contract': CONTRACT}


@pytest.mark.asyncio
@pytest.mark.parametrize('decision', ['keep', 'replace', 'context'])
async def test_review_aligns_names_with_final_points_without_an_extra_model_call(svc, monkeypatch, decision):
    from knowledge_content_review import review_content
    raw, context = current(svc, monkeypatch)
    original = value([point()]); before = deepcopy(original); calls = []
    chosen = [] if decision != 'replace' else [point(), point('出栈', value='移除并返回栈顶元素')]
    names = {'keep': ['入栈把元素加入栈顶'], 'replace': ['入栈把元素加入栈顶', '出栈移除栈顶元素'], 'context': []}[decision]

    async def call(*args):
        head, encoded = args[-2].split('\nINPUT_JSON:\n', 1)
        assert '唯一完整响应格式' in head
        assert '"decision":"keep|replace|context|source_issue"' not in head
        data = json.loads(encoded); calls.append(data)
        assert data['review_contract'] == 'knowledge_content_review_v2'
        assert data['expression_contract'] == CONTRACT
        return json.dumps({'point_reviews': {'S1.1:0': {'decision': decision, 'points': chosen,
            'reason': '冻结来源支持对应规则', 'names': names}}, 'additions': {'S1.1': []},
            'addition_names': {'S1.1': []}, 'source_issues': []})

    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    reviewed = await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], original, record)
    assert original == before and len(calls) == 1
    assert len(reviewed['_content_review_trace']) == len(names)
    assert [trace['expression']['text'] for trace in reviewed['_content_review_trace']] == names
    assert record['expression_contract'] == CONTRACT


def test_compiler_changes_only_name_and_keeps_full_fact_conditions_sources_and_identity(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    from knowledge_expression import bind_name
    from knowledge_compact import passage_catalog
    raw, context = current(svc, monkeypatch)
    response = value([point()]); before = deepcopy(response)
    passage = passage_catalog({**context, 'knowledge_passage_mode': 'source_blocks_v1'}, ['S1'])[0]
    legacy = compile_extraction(raw, {k: v for k, v in context.items() if k != 'expression_contract'}, ['S1'], 1, response)
    response['_expression_contract'] = CONTRACT
    response['_content_review_trace'] = [{'expression': bind_name('入栈把元素加入栈顶', point(), passage['text'])}]
    result = compile_extraction(raw, context, ['S1'], 1, response)
    actual, old = result['tree']['knowledge_points'][0], legacy['tree']['knowledge_points'][0]
    assert actual['name'] == '入栈把元素加入栈顶'
    assert actual['knowledge_id'] == old['knowledge_id']
    for field in ('statement', 'conditions', 'meta_question', 'meta_answer', 'source_quotes', 'source_refs'):
        assert actual[field] == old[field], field
    assert actual['atomic_contract']['expression']['contract'] == CONTRACT
    assert result['report']['ready_for_adoption']
    assert before['passages'] == response['passages']


@pytest.mark.parametrize('label', ['', '入栈是什么？', '如何入栈', '入栈的操作效果', '甲' * 201])
def test_invalid_short_names_are_not_silently_accepted(label):
    from knowledge_expression import bind_name
    with pytest.raises(CourseDocumentConflict):
        bind_name(label, point(), '入栈将元素插入栈顶。')


@pytest.mark.parametrize('mutation', ['claim', 'conditions', 'source'])
def test_name_binding_is_invalidated_when_semantics_or_source_change(mutation):
    from knowledge_expression import bind_name, bound_name
    raw = point(); source = '入栈将元素插入栈顶。'
    expression = bind_name('入栈把元素加入栈顶', raw, source)
    if mutation == 'claim': raw['value'] = '移除栈顶'
    elif mutation == 'conditions': raw['conditions'] = ['只在非满栈时']
    else: source += '新的来源版本。'
    with pytest.raises(CourseDocumentConflict, match='短陈述'):
        bound_name(expression, raw, source)


def test_new_context_cannot_compile_without_names_but_legacy_contract_still_works(svc, monkeypatch):
    from knowledge_extract import compile_extraction
    raw, context = current(svc, monkeypatch)
    response = value([point()])
    with pytest.raises(CourseDocumentConflict, match='短陈述'):
        compile_extraction(raw, context, ['S1'], 1, response)
    legacy = {key: val for key, val in context.items() if key != 'expression_contract'}
    assert compile_extraction(raw, legacy, ['S1'], 1, response)['tree']['knowledge_points'][0]['name'] == '入栈的操作效果'


@pytest.mark.asyncio
async def test_new_job_freezes_expression_contract(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    from backend.tests.test_knowledge_tree_relations import fake_provider
    fake_provider(svc)
    job = start(svc, extraction_mode='single_pass_v1')
    await svc.run('c-pilot', job['id'])
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    assert saved['checkpoint']['atomic_pipeline']['expression_contract'] == CONTRACT
    assert saved['checkpoint']['candidate']['expression_contract'] == CONTRACT
    assert saved['checkpoint']['candidate']['atomic_assessment']['content_review']['contract'] == 'knowledge_content_review_v3'
    assert all('expression' in p['atomic_contract'] for p in saved['checkpoint']['candidate']['knowledge_points'])


@pytest.mark.asyncio
async def test_limited_semantic_repair_rebinds_name_to_the_final_corrected_point(svc, monkeypatch):
    from knowledge_expression import bind_name
    from knowledge_compact import passage_catalog
    from knowledge_extraction_repair import repair_points
    from knowledge_extract import compile_extraction
    raw, context = current(svc, monkeypatch)
    source = passage_catalog({**context, 'knowledge_passage_mode': 'source_blocks_v1'}, ['S1'])[0]['text']
    invalid = point('虚构入栈')
    response = value([invalid]); response['_expression_contract'] = CONTRACT
    response['_content_review_trace'] = [{'expression': bind_name('入栈把元素加入栈顶', invalid, source)}]

    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n', 1)[1])
        assert data['expression_contract'] == CONTRACT
        return json.dumps({'repairs': {'S1.1:0': {'handling': 'patch', 'patch': {'subject': '入栈'},
            'reason': '主体须逐字来自原文'}}, 'short_statements': {'S1.1:0': ['入栈把元素加入栈顶']}, 'source_issues': []})

    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    corrected = await repair_points(svc, 'c-pilot', 'j', None, raw, context, ['S1'], 1, response, {})
    assert corrected['_content_review_trace'][0]['expression'] != response['_content_review_trace'][0]['expression']
    compiled = compile_extraction(raw, context, ['S1'], 1, corrected)
    assert compiled['tree']['knowledge_points'][0]['name'] == '入栈把元素加入栈顶'


def test_unsupported_contract_and_missing_name_rows_are_explicit_errors():
    from knowledge_expression import check_contract, named_traces
    with pytest.raises(CourseDocumentConflict): check_contract('future-expression')
    with pytest.raises(CourseDocumentConflict): named_traces([], [point()], '入栈将元素插入栈顶。', {})


def test_literal_joint_notation_is_not_split_by_punctuation_in_new_contract():
    from knowledge_semantic_contract import quality_point
    source = 'C17中，if/else分支根据条件选择执行其中一个分支。'
    rule = point('if/else分支', property='执行逻辑', value='根据条件选择执行其中一个分支', conditions=['C17'])
    with pytest.raises(CourseDocumentConflict, match='独立操作'):
        quality_point(rule, source)  # Preserve the frozen old contract.
    compiled, audit = quality_point(rule, source, allow_literal_slash=True)
    assert 'if/else分支' in compiled['claim']
    assert audit['subject_notation_review'] == ['if/else分支']
    assert audit['semantics_verified'] is False


def test_complete_symbolic_formula_is_used_without_a_verbose_word_mnemonic():
    from knowledge_expression import bind_name, bound_name
    rule = point('乘积求导', property='求导公式', value='(uv)′=u′v+uv′', conditions=['u和v在当前点可导'])
    source = '乘积求导公式为(uv)′=u′v+uv′，u和v在当前点可导。'
    expression = bind_name('乘积求导为前导后乘加前乘后导', rule, source)
    assert bound_name(expression, rule, source) == rule['value']
    assert expression['text'] == '乘积求导为前导后乘加前乘后导'  # Original model wording stays auditable.
