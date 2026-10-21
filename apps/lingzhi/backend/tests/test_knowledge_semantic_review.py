"""Semantic normalization precedes identity; coverage accounts for every outcome."""
from copy import deepcopy
import json
import pytest


def candidate(statement='独立知识结论', key='P1'):
    return dict(key=key,statement=statement,knowledge_type='rule',conditions=[],symbol_definitions=[],
                teaching_context=[],examples=[],check_intents=['独立应用这一结论'],
                coverage_unit_ids=[key],input_material_keys=['S1'],branch='规则',profile_focus='')


def conclusion(statement='独立知识结论', **patch):
    return dict(statement=statement,knowledge_type='rule',conditions=[],symbol_definitions=[],
                teaching_context=[],examples=[],check='单独说明该结论及其条件',**patch)


def response(points=None, disposition='knowledge', result='consistent'):
    return {'reviews': {'P1': {'disposition':disposition,'reason':'逐条核对独立结论',
        'challenge':{'case':'检验边界情形或反例','result':result,'explanation':'比较前提与结论'},
        'conclusions': [conclusion()] if points is None else points}}}


def test_review_splits_independent_results_and_tracks_the_frozen_obligation():
    from knowledge_semantic_review import compile_reviews
    original=candidate('对象的定义、数量关系和表示方程')
    before=deepcopy(original)
    output=compile_reviews(response([conclusion('对象定义'),conclusion('数量关系'),conclusion('表示方程')]),[original])
    assert len(output['points'])==3
    assert len({p['key'] for p in output['points']})==3
    assert all(p['coverage_unit_ids']==['P1'] for p in output['points'])
    assert all(p['semantic_review']['independence_group']=='P1' for p in output['points'])
    assert original==before


def test_refuted_claim_must_be_changed_and_original_is_retained():
    from knowledge_semantic_review import compile_reviews
    original=candidate('整数除法总能得到精确的有理数')
    bad=response([conclusion(original['statement'])],result='refuted')
    with pytest.raises(ValueError,match='无效修正'):
        compile_reviews(bad,[original])
    good=response([conclusion('C17整数除法的商向零截断')],result='refuted')
    fixed=compile_reviews(good,[original])
    assert fixed['points'][0]['statement']=='C17整数除法的商向零截断'
    assert fixed['reviews'][0]['original']==original


def test_uncertainty_is_blocking_and_cannot_be_certified_by_empty_checks():
    from knowledge_semantic_review import compile_reviews
    original=candidate()
    with pytest.raises(ValueError):compile_reviews(response(result='inconclusive'),[original])
    result=compile_reviews(response([],disposition='uncertain',result='inconclusive'),[original])
    assert result['points'][0]['statement']==original['statement']
    assert result['issues'][0]['severity']=='blocking'
    bad=response();bad['reviews']['P1']['challenge']['case']=' '
    with pytest.raises(ValueError):compile_reviews(bad,[original])
    with pytest.raises(ValueError):compile_reviews({'reviews':{}},[original])


def test_examples_get_explicit_disposition_without_fake_leaves_or_silent_loss():
    from knowledge_semantic_review import compile_reviews
    from knowledge_coverage import coverage_report
    original=candidate('将给定数值代入后得到答案12')
    compiled=compile_reviews(response([],disposition='example'),[original])
    assert not compiled['points']
    report=coverage_report([{'key':'P1'},{'key':'P2'}],[candidate(key='P2')],compiled['resolutions'])
    assert report['missing_unit_ids']==[]
    assert report['covered_unit_count']==1 and report['accounted_unit_count']==2
    assert report['non_knowledge_unit_count']==1
    assert report['unit_dispositions']['P1']['disposition']=='example'
    assert coverage_report([{'key':'P1'}],[])['missing_unit_ids']==['P1']
    with pytest.raises(ValueError):coverage_report([{'key':'P2'}],[],compiled['resolutions'])
    bad=deepcopy(compiled['resolutions']);bad[0]['disposition']='knowledge'
    with pytest.raises(ValueError):coverage_report([{'key':'P1'}],[],bad)


def test_identity_cannot_rewrite_or_recombine_reviewed_siblings():
    from knowledge_semantic_review import compile_reviews
    from knowledge_registry_identity import apply_decisions
    normalized=compile_reviews(response([conclusion('独立规则甲'),conclusion('独立规则乙')]),[candidate()])['points']
    left,right=normalized
    decisions={p['key']:{'action':'keep','reason':'独立'} for p in normalized}
    rewritten=deepcopy(decisions);rewritten[left['key']]={'action':'replace','reason':'再改写','points':[]}
    with pytest.raises(ValueError,match='身份阶段'):
        apply_decisions(normalized,[],rewritten)
    decisions[right['key']]={'action':'match','target':left['key'],'same_claim':True,'same_scope':True,'same_symbols':True,'reason':'同一主题'}
    with pytest.raises(ValueError,match='独立结论'):
        apply_decisions(normalized,[],decisions)


def test_review_contract_is_subject_independent_and_contains_no_source_gate():
    from knowledge_semantic_review import review_prompt
    prompt=review_prompt([candidate('普遍命题')])
    payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
    assert payload['stage']=='candidate_semantic_review'
    assert '反例' in prompt and '独立结论' in prompt
    for retired in ['source_literal','source_span','逐字','偶函数','法线','微积分']:
        assert retired not in prompt
