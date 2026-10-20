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
