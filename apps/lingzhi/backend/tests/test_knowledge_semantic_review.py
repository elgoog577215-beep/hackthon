"""Semantic normalization precedes identity; coverage accounts for every outcome."""
from copy import deepcopy
import json
import pytest
from backend.tests.test_knowledge_first import svc


def candidate(statement='独立知识结论', key='P1'):
    return dict(key=key,statement=statement,knowledge_type='rule',conditions=[],symbol_definitions=[],
                teaching_context=[],examples=[],check_intents=['独立应用这一结论'],
                coverage_unit_ids=[key],input_material_keys=['S1'],branch='规则',profile_focus='')


def conclusion(statement='独立知识结论', **patch):
    return dict(statement=statement,knowledge_type='rule',conditions=[],symbol_definitions=[],
                teaching_context=[],examples=[],check='单独说明该结论及其条件',role='relation',**patch)


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


@pytest.mark.parametrize('variant',['metadata_only','unchanged_child'])
def test_refuted_core_cannot_survive_by_changing_examples_or_adding_a_sibling(variant):
    from knowledge_semantic_review import compile_reviews
    original=candidate('被反例推翻的结论')
    rows=[conclusion(original['statement'])]
    if variant=='metadata_only':rows[0]['examples']=['换一个例子']
    else:rows.append(conclusion('另一个正确结论'))
    with pytest.raises(ValueError,match='无效修正'):
        compile_reviews(response(rows,result='refuted'),[original])


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
    assert payload['challenge_scope']==['statement','conditions']
    assert '反例' in prompt and '独立结论' in prompt
    for retired in ['source_literal','source_span','逐字','偶函数','法线','微积分']:
        assert retired not in prompt


def test_conclusions_have_one_role_and_bounded_reasons():
    from knowledge_semantic_review import compile_reviews
    value=response()
    assert compile_reviews(value,[candidate()])['points'][0]['semantic_review']['conclusion_role']=='relation'
    value['reviews']['P1']['conclusions'][0]['role']=['relation','representation']
    with pytest.raises(ValueError):compile_reviews(value,[candidate()])
    value=response();value['reviews']['P1']['reason']='讨论'*500
    with pytest.raises(ValueError,match='reason'):compile_reviews(value,[candidate()])
    value=response();value['reviews']['P1']['conclusions'][0]['role']='rule'
    with pytest.raises(ValueError,match='role.*relation'):
        compile_reviews(value,[candidate()])


def test_review_receives_frozen_domain_context_without_requiring_source_word_matches():
    from knowledge_semantic_review import review_prompt
    context={'course_title':'程序设计','standard':'教学指定版本'}
    p=review_prompt([candidate()],course_context=context)
    assert json.loads(p.split('\nINPUT_JSON:\n')[1])['course_context']==context


def test_explicit_content_retry_reuses_extraction_and_drops_only_dependent_stages():
    from knowledge_registry_pipeline import continued_pipeline
    original={'candidate':{'revision_id':'old'},'atomic_pipeline':{
        'inventory_batches':[{'id':'inventory-1','status':'completed','points':[candidate()]}],
        'identity_job_id':'stable-origin', **{key:{'status':'completed'} for key in (
            'semantic_review','registry','identity_review','names','hierarchy','registry_relations','preview_tree','kc_profiles')}}}
    before=deepcopy(original)
    next_checkpoint=continued_pipeline(original,'content')
    pipeline=next_checkpoint['atomic_pipeline']
    assert pipeline['inventory_batches']==original['atomic_pipeline']['inventory_batches']
    assert pipeline['identity_job_id']=='stable-origin'
    assert all(key not in pipeline for key in ('semantic_review','registry','names','hierarchy','kc_profiles'))
    assert original==before


@pytest.mark.asyncio
async def test_pipeline_reviews_before_identity_and_resumes_without_repeating_finished_review(svc, monkeypatch):
    from types import SimpleNamespace
    from backend.tests.test_knowledge_atomic import setup_course
    from backend.tests.test_knowledge_registry_pipeline import discovery_reply, atomic_reply, truth_reply, completion_reply
    setup_course(svc,monkeypatch)
    calls=[];broken=True
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);stage=payload['stage'];calls.append(stage)
        if stage=='knowledge_discovery':return discovery_reply(payload)
        if stage=='knowledge_atomize':return atomic_reply(payload)
        if stage=='candidate_coverage_review':return completion_reply()
        if stage=='candidate_truth_review':return truth_reply(payload)
        if stage=='candidate_semantic_review':
            p=payload['points'][0]
            return json.dumps({'reviews':{p['key']:{**response()['reviews']['P1'],
                'conclusions':[conclusion('独立结论甲'),conclusion('独立结论乙')]}}})
        if stage=='identity_review':
            assert set(payload['allowed_actions'])=={'keep','match','check','uncertain'}
            return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'独立结论'} for p in payload['candidates']}})
        if stage=='candidate_names':
            return json.dumps({'names':{} if broken else {p['key']:{'name':p['statement'],'meta_question':'解释该结论'} for p in payload['points']}})
        raise AssertionError(stage)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    v=svc.view('c-pilot',source_mode='handouts')
    def start(rid,**extra):
        return svc.start('c-pilot','tree',rid,v['knowledge_revision'],v['document_revision'],source_mode='handouts',
            lesson_id='cpu',pipeline='inventory_atomic_v1',organize_hierarchy=False,include_relations=False,**extra)[0]
    job=start('review-first');await svc.run('c-pilot',job['id'])
    old=deepcopy(svc.authoring.get_job('c-pilot',job['id']))
    assert old['status']=='failed'
    assert calls==['knowledge_discovery','knowledge_atomize','candidate_coverage_review','candidate_semantic_review','candidate_truth_review','identity_review','candidate_names','candidate_names']
    calls.clear();broken=False
    resumed=start('review-resume',resume_job_id=job['id']);await svc.run('c-pilot',resumed['id'])
    out=svc.authoring.get_job('c-pilot',resumed['id'])
    assert out['status']=='completed',out.get('error')
    assert out['generation_contract']=='knowledge_registry_v5'
    assert calls==['candidate_names']
    assert len(out['checkpoint']['candidate']['knowledge_points'])==2
    assert out['checkpoint']['candidate']['knowledge_coverage']['missing_unit_ids']==[]
    assert svc.authoring.get_job('c-pilot',job['id'])==old
