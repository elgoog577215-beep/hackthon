"""Equivalence is scoped, bidirectional and reversible; it is not similarity."""
from copy import deepcopy
import json

import pytest

from course_repository import CourseDocumentConflict
from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course, start


def points():
    claims = ['物体的速度保持不变。', '物体可以静止，也可以做匀速直线运动。', '合力为零不意味着物体一定静止。']
    return [{'key': f'K{i}', 'id': f'p{i}', 'knowledge_id': f'p{i}', 'name': claim.rstrip('。'),
             'statement': claim, 'conditions': ['在惯性参考系中', '物体所受合力为零'] if i < 3 else [],
             'source_refs': [f's{i}'], 'source_quotes': [{'evidence_id': f'e{i}', 'quote': claim}],
             'meta_question': f'检查{i}', 'meta_answer': claim, 'section_refs': ['lesson'],
             'atomic_contract': {'form': 'fact', 'semantics_verified': False}}
            for i, claim in enumerate(claims, 1)]


def response():
    return {'groups': [{'canonical_key': 'K1', 'member_keys': ['K1', 'K2'],
                        'relation': 'equivalent', 'forward_reason': '速度恒定时为静止或匀速直线运动。',
                        'reverse_reason': '静止和匀速直线运动的速度均恒定。'}]}


def test_scoped_equivalents_merge_without_rewriting_and_retain_both_source_histories():
    from knowledge_equivalence import validate_groups, apply_equivalences, catalog_signature
    original = points(); before = deepcopy(original)
    record = {'contract': 'knowledge_equivalence_v1', 'status': 'completed',
              'input_signature': catalog_signature(original), 'groups': validate_groups(response(), original)}
    merged, aliases = apply_equivalences(original, record)
    assert original == before and len(merged) == 2
    assert merged[0]['knowledge_id'] == 'p1' and merged[0]['statement'] == before[0]['statement']
    assert merged[0]['conditions'] == before[0]['conditions']
    assert merged[0]['source_quotes'] == before[0]['source_quotes'] + before[1]['source_quotes']
    assert merged[0]['semantic_equivalents'][0]['point'] == before[1]
    assert merged[1] == before[2] and aliases == {'K2': 'K1'}
    assert record['groups'][0]['semantics_verified'] is False
    assert apply_equivalences(original, record) == (merged, aliases)


@pytest.mark.parametrize('change', ['scope', 'one_way', 'unknown', 'overlap', 'missing_member', 'no_reason', 'extra'])
def test_similarity_entailment_scope_changes_and_ambiguous_groups_are_rejected(change):
    from knowledge_equivalence import validate_groups
    rows = points(); value = response(); group = value['groups'][0]
    if change == 'scope': rows[1]['conditions'] = ['在非惯性参考系中']
    elif change == 'one_way': group['relation'] = 'entails'
    elif change == 'unknown': group['member_keys'][1] = 'K99'
    elif change == 'overlap': value['groups'].append(deepcopy(group))
    elif change == 'missing_member': group['canonical_key'] = 'K3'
    elif change == 'no_reason': group['reverse_reason'] = ''
    else: group['replacement_statement'] = '新编结论'
    with pytest.raises(CourseDocumentConflict): validate_groups(value, rows)


def test_equivalence_is_domain_independent_and_does_not_require_matching_names_or_subjects():
    from knowledge_equivalence import validate_groups
    rows = points()[:2]
    rows[0].update(name='栈按后进先出访问', statement='栈按后进先出的顺序访问元素。')
    rows[1].update(name='后入栈的元素先出栈', statement='栈中后加入的元素先被移除。')
    for p in rows: p['conditions'] = []
    assert len(validate_groups(response(), rows)) == 1


def test_modified_claim_source_or_conditions_cannot_reuse_a_previous_merge():
    from knowledge_equivalence import validate_groups, apply_equivalences, catalog_signature
    rows = points()
    record = {'contract': 'knowledge_equivalence_v1', 'status': 'completed',
              'input_signature': catalog_signature(rows), 'groups': validate_groups(response(), rows)}
    for field, value in [('statement', '速度为零'), ('conditions', []), ('source_quotes', [])]:
        changed = deepcopy(rows); changed[0][field] = value
        with pytest.raises(CourseDocumentConflict, match='冻结'): apply_equivalences(changed, record)


@pytest.mark.asyncio
async def test_new_pipeline_runs_equivalence_once_and_resume_keeps_frozen_decision(svc, monkeypatch):
    from backend.tests.test_knowledge_tree_relations import fake_provider
    setup_course(svc, monkeypatch); calls = fake_provider(svc)
    job = start(svc, extraction_mode='single_pass_v1', include_relations=True)
    await svc.run('c-pilot', job['id']); saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    assert [s for s, _ in calls].count('semantic_equivalence') == 1
    assert saved['checkpoint']['atomic_pipeline']['semantic_equivalence']['status'] == 'completed'
    assert saved['checkpoint']['candidate']['semantic_equivalence']['semantics_verified'] is False


@pytest.mark.asyncio
async def test_generic_review_v3_reports_invalid_literal_subject_before_model_request(svc, monkeypatch):
    from knowledge_content_review import review_content
    from backend.tests.test_knowledge_extraction_repair import point, value
    from backend.tests.test_knowledge_extract import review_response
    setup_course(svc, monkeypatch)
    raw = svc.repository.load_raw('c-pilot')
    context = {**svc._context(raw, 'handouts', 'cpu'), 'expression_contract': 'knowledge_expression_v1',
               'content_review_contract': 'knowledge_content_review_v3'}
    original = value([point('入栈操作对象')]); calls = []
    async def call(*args):
        prompt = args[-2]; payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload)
        assert payload['review_contract'] == 'knowledge_content_review_v3'
        assert payload['points']['S1.1:0']['compiler_diagnostics'][0]['code'] == 'source_subject'
        assert len(prompt.split('\nINPUT_JSON:\n')[0]) < 5000
        result = review_response(payload)
        result['point_reviews']['S1.1:0'].update(decision='replace', points=[point()], names=['入栈把元素加入栈顶'])
        return json.dumps(result)
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    output = await review_content(svc, 'c-pilot', 'j', None, raw, context, ['S1'], original, {})
    assert len(calls) == 1 and output['passages']['S1.1']['points'][0]['subject'] == '入栈'


def test_review_envelope_schema_rejects_misnested_or_missing_keys_without_repairing_semantics():
    from knowledge_review_protocol import response_schema
    from jsonschema import validate, ValidationError
    schema = response_schema(['S1.1:0'], ['S1.1'])
    valid = {'point_reviews': {'S1.1:0': {'decision': 'keep', 'points': [], 'names': ['入栈把元素加入栈顶'], 'reason': '原文支持'}},
             'additions': {'S1.1': []}, 'addition_names': {'S1.1': []}, 'source_issues': []}
    validate(valid, schema)
    broken = deepcopy(valid); broken['S1.1:0'] = broken['point_reviews'].pop('S1.1:0')
    with pytest.raises(ValidationError): validate(broken, schema)
    del valid['addition_names']
    with pytest.raises(ValidationError): validate(valid, schema)


@pytest.mark.asyncio
async def test_real_pipeline_merges_ids_and_previews_use_the_merged_catalog(svc, monkeypatch):
    from types import SimpleNamespace
    from backend.tests.test_knowledge_extract import review_response
    from backend.tests.test_knowledge_extraction_repair import point, value
    from knowledge_atomic import project_preview
    setup_course(svc, monkeypatch)
    calls = []
    async def model(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); stage = data['stage']; calls.append(stage)
        if stage == 'extract':
            return json.dumps(value([point('栈', property='取出顺序', value='后进先出'),
                                     point('栈', property='访问顺序', value='后加入的元素先被移除')]))
        if stage == 'content_review':
            assert kwargs.get('json_schema') is not None
            reviewed = review_response(data)
            for row in reviewed['point_reviews'].values(): row['names'] = ['栈按后进先出访问元素']
            return json.dumps(reviewed)
        if stage == 'semantic_equivalence':
            return json.dumps({'point_reviews': {'K1': {'canonical_key': 'K2', 'forward_reason': '后进先出即后加入先移除', 'reverse_reason': '后加入先移除即后进先出'},
                                                'K2': {'canonical_key': 'K2', 'forward_reason': '本组代表', 'reverse_reason': ''}}})
        if stage == 'semantic_equivalence_pairs':
            return json.dumps({'pair_reviews': {key: {'relation': 'restatement', 'forward_reason': '同一访问顺序', 'reverse_reason': '同义转述'} for key in data['pairs']}})
        assert len(data['points']) == 1 and data['points'][0]['key'] == 'K1'
        return json.dumps({'response_contract': 'knowledge_partition_v1', 'groups': [],
                           'point_groups': {'K1': '__direct__'}, 'stop_reason': '同一访问规则'})
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    job = start(svc, extraction_mode='single_pass_v1', organize_hierarchy=True)
    await svc.run('c-pilot', job['id']); saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    candidate = saved['checkpoint']['candidate']; assert len(candidate['knowledge_points']) == 1
    assert len(candidate['knowledge_inventory']) == 2
    assert candidate['knowledge_points'][0]['semantic_equivalents'][0]['point']['knowledge_id'] != candidate['knowledge_points'][0]['knowledge_id']
    assert candidate['semantic_equivalence']['identity_map'][0]['knowledge_id'] == candidate['knowledge_points'][0]['knowledge_id']
    preview_job = deepcopy(saved); preview_job['status'] = 'running'
    preview = project_preview(preview_job, 'c-pilot')
    assert len(preview['knowledge_points']) == 1
    assert preview['knowledge_points'][0]['knowledge_id'] == candidate['knowledge_points'][0]['knowledge_id']


@pytest.mark.asyncio
async def test_completed_equivalence_reuses_frozen_result_and_failure_stays_visible(monkeypatch):
    from knowledge_equivalence import review_equivalence
    rows = points(); calls = []; saves = []; state = {}
    async def call(*args):
        calls.append(1)
        return json.dumps({'point_reviews': {p['key']: {'canonical_key': 'K1' if p['key'] == 'K2' else p['key'],
            'forward_reason': '同义' if p['key'] == 'K2' else '独立检查目标', 'reverse_reason': '反向同义' if p['key'] == 'K2' else ''} for p in rows}})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    await review_equivalence(None, 'c', 'j', None, rows, state, lambda **kw: saves.append(kw), lambda: None)
    before = deepcopy(state)
    await review_equivalence(None, 'c', 'j', None, rows, state, lambda **kw: saves.append(kw), lambda: None)
    assert calls == [1] and state == before
    async def invalid(*args): return '{"groups":[{"canonical_key":"K99"}]}'
    monkeypatch.setattr('knowledge_atomic.call_stage', invalid)
    state = {}
    with pytest.raises(CourseDocumentConflict):
        await review_equivalence(None, 'c', 'j', None, rows, state, lambda **kw: None, lambda: None)
    assert state['semantic_equivalence']['status'] == 'failed'
    assert 'K99' in state['semantic_equivalence']['raw_response']


def test_equivalence_partition_requires_every_point_and_no_transitive_representatives():
    from knowledge_equivalence import compile_reviews
    rows = points()
    value = {'point_reviews': {p['key']: {'canonical_key': p['key'], 'forward_reason': '独立目标', 'reverse_reason': ''} for p in rows}}
    assert compile_reviews(value, rows) == []
    del value['point_reviews']['K2']
    with pytest.raises(CourseDocumentConflict): compile_reviews(value, rows)


def test_concrete_numeric_program_instance_is_not_a_general_rule_but_symbolic_rules_remain_valid():
    from knowledge_semantic_contract import quality_point
    from backend.tests.test_knowledge_extraction_repair import point
    instance = point('double r=5/2', property='结果', value='2.0')
    source = '例：double r=5/2得到2.0。'
    with pytest.raises(CourseDocumentConflict, match='具体算例'):
        quality_point(instance, source, general_knowledge=True)
    symbolic = point('幂函数', property='求导公式', value='(x^2)′=2x')
    quality_point(symbolic, '幂函数的求导公式为(x^2)′=2x。', general_knowledge=True)


@pytest.mark.asyncio
async def test_complete_case_description_is_compared_as_a_restatement_not_a_concrete_example(monkeypatch):
    from knowledge_equivalence import review_equivalence
    async def call(*args):
        assert '穷尽' in args[-2] and '单个' in args[-2]
        return json.dumps({'point_reviews': {p['key']: {'canonical_key': p['key'], 'forward_reason': '独立检查目标', 'reverse_reason': ''} for p in points()}})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    await review_equivalence(None, 'c', 'j', None, points(), {}, lambda **kw: None, lambda: None)


def test_schema_cannot_declare_both_independence_and_reverse_equivalence():
    from knowledge_equivalence import response_schema
    from jsonschema import validate, ValidationError
    schema = response_schema(['K1', 'K2'])
    value = {'point_reviews': {'K1': {'canonical_key': 'K1', 'forward_reason': '代表', 'reverse_reason': ''},
                              'K2': {'canonical_key': 'K2', 'forward_reason': '同义', 'reverse_reason': '和K1等价'}}}
    with pytest.raises(ValidationError): validate(value, schema)
    value['point_reviews']['K2']['canonical_key'] = 'K1'
    validate(value, schema)


def test_literal_source_subject_must_not_end_at_an_unfinished_predicate():
    from knowledge_semantic_contract import quality_point
    from backend.tests.test_knowledge_extraction_repair import point
    with pytest.raises(CourseDocumentConflict, match='残缺谓语'):
        quality_point(point('元素插入到', value='栈顶'), '入栈将元素插入到栈顶。', general_knowledge=True)
    quality_point(point('类型转换', value='在赋值时发生'), '类型转换在赋值时发生。', general_knowledge=True)


@pytest.mark.asyncio
async def test_pair_confirmation_finds_missed_restatements_and_rejects_derived_equivalence(monkeypatch):
    from knowledge_equivalence_pairs import confirm_pairs
    rows = points()[:2]
    for p in rows: p['atomic_contract']['subjects'] = ['物体']
    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        assert len(data['pairs']) == 1
        return json.dumps({'pair_reviews': {'E1': {'relation': relation, 'forward_reason': '正向依据', 'reverse_reason': '反向依据'}}})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    for relation in ['restatement', 'derived_equivalence', 'different', 'uncertain']:
        record = {}
        groups = await confirm_pairs(None, 'c', 'j', None, rows, [], record, lambda **kw: None, lambda: None)
        assert len(groups) == (1 if relation == 'restatement' else 0)
        assert record['pair_batches'][0]['status'] == 'completed'


@pytest.mark.asyncio
async def test_pair_work_is_bounded_and_nontransitive_votes_do_not_merge_through_a_third_point(monkeypatch):
    from knowledge_equivalence_pairs import confirm_pairs
    rows = points()
    for p in rows: p['conditions'] = []; p['atomic_contract']['subjects'] = ['共同对象']
    batches = []
    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n')[1]); batches.append(len(data['pairs']))
        return json.dumps({'pair_reviews': {key: {'relation': 'different' if len(rows) > 3 or {item['a']['key'], item['b']['key']} == {'K1', 'K3'} else 'restatement',
            'forward_reason': '逐对依据', 'reverse_reason': '逐对反向依据'} for key, item in data['pairs'].items()}})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    record = {}
    assert await confirm_pairs(None, 'c', 'j', None, rows, [], record, lambda **kw: None, lambda: None) == []
    assert record['nontransitive_group_count'] == 1
    rows = [{**deepcopy(rows[0]), 'key': f'K{i}'} for i in range(1, 14)]; batches.clear(); record = {}
    assert await confirm_pairs(None, 'c', 'j', None, rows, [], record, lambda **kw: None, lambda: None) == []
    assert batches == [16, 16, 16, 16] and record['unreviewed_pair_count'] == 14


@pytest.mark.asyncio
async def test_discovery_cycles_are_only_pair_proposals_and_cannot_merge_complementary_cases(monkeypatch):
    from knowledge_equivalence import review_equivalence
    rows = points()[:2]; state = {'semantic_equivalence_contract': 'knowledge_equivalence_v3'}
    async def call(*args):
        data = json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        if data['stage'] == 'semantic_equivalence':
            return json.dumps({'point_reviews': {'K1': {'canonical_key': 'K2', 'forward_reason': '候选', 'reverse_reason': '候选'},
                                                'K2': {'canonical_key': 'K1', 'forward_reason': '候选', 'reverse_reason': '候选'}}})
        return json.dumps({'pair_reviews': {key: {'relation': 'different', 'forward_reason': '互补情况不等价', 'reverse_reason': '各自只有一部分情况'} for key in data['pairs']}})
    monkeypatch.setattr('knowledge_atomic.call_stage', call)
    await review_equivalence(None, 'c', 'j', None, rows, state, lambda **kw: None, lambda: None)
    assert state['semantic_equivalence']['status'] == 'completed'
    assert state['semantic_equivalence']['groups'] == []
    assert state['semantic_equivalence']['proposed_edges']


@pytest.mark.asyncio
async def test_opposite_boolean_targets_stay_separate_even_if_a_model_calls_them_equivalent(monkeypatch):
    from knowledge_equivalence_pairs import confirm_pairs
    from knowledge_equivalence import validate_groups
    rows = points()[:2]
    for p, truth in zip(rows, ['假', '真']):
        p['atomic_contract'].update(subjects=['整数值'], property=f'作条件判断为{truth}的条件')
    async def forbidden(*args): raise AssertionError('明确相反的检查目标不应交给模型合并')
    monkeypatch.setattr('knowledge_atomic.call_stage', forbidden)
    record = {'proposed_edges': [['K1', 'K2']]}
    assert await confirm_pairs(None, 'c', 'j', None, rows, [], record, lambda **kw: None, lambda: None) == []
    assert record['rejected_complementary_targets'] == [['K1', 'K2']]
    with pytest.raises(CourseDocumentConflict, match='互补'):
        validate_groups(response(), rows)
