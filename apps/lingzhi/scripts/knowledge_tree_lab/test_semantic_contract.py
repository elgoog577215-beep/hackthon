from copy import deepcopy
import pytest
from .cross_course_round import COURSES
from .semantic_contract import question_bank, compile_candidate, attach_review, REVIEW_AXES
from .pipeline import digest


def sample():
    c = deepcopy(COURSES[0]); bank = question_bank(c)
    tree = {'points': [{'key': 'P1', 'statement': '赋值不复制'}]}
    doc = {'skills': [{'key':'S1', 'point_keys':['P1'],
        'task': {'probe_keys':['Q1'], 'state_policy':'independent_reset'},
        'criteria':[{'point_key':'P1', 'probe_key':'Q1', 'question_revision':bank['Q1']['revision'],
                     'binding':{'target':'别名', 'required_evidence':'判断是否同对象', 'why_direct':'直接判断身份'}}],
        'mistakes':[{'key':'A', 'point_keys':['P1'], 'probe_key':'Q1', 'wrong_rule':'赋值复制',
                     'prediction':'False', 'derivation':['复制产生新对象','身份不同'], 'limits':'不能单题确诊',
                     'repair_steps':[{'source_ref':'M1','source_quote':'赋值b=a使两个名字指向同一列表，不会复制列表。',
                         'action':'画名字到对象的连线', 'check_key':'Q1', 'scope_limit':'只讨论列表赋值'}]}],
        'discrimination': {'probe_keys':['Q1'], 'distinguishes':'与正确规则预测不同','limits':'非唯一错因'},
        'retest':{'key':'R2','question_revision':bank['R2']['revision'], 'prerequisite_point_keys':[], 'why_transfer':'新输入'},
        'mastery_requirements':['前置知识需另核验']} ]}
    return c,tree,doc


def test_resolution_is_immutable_and_never_semantic_approval():
    c,t,d=sample();before=deepcopy((c,t,d));r=compile_candidate(c,t,d)
    assert (c,t,d)==before
    assert not r['contract']['structural_issues']
    assert r['skills'][0]['criteria'][0]['resolved_check']['answer']=='True'
    assert not r['contract']['ready_for_adoption']


@pytest.mark.parametrize('mutation,code', [
    ('revision','stale_question'), ('answer','answer_rewrite'), ('quote','unsupported_repair_quote'),
    ('reuse','training_uses_transfer_or_unknown'), ('same_text','transfer_reused_as_training'),
    ('missing','criteria_coverage'), ('collision','question_identity_collision')])
def test_known_failure_classes_are_blocked(mutation,code):
    c,t,d=sample();s=d['skills'][0]
    if mutation=='revision': c['probes'][0]['question']='不同题目'
    if mutation=='answer': s['criteria'][0]['pass_evidence']='False'
    if mutation=='quote': s['mistakes'][0]['repair_steps'][0]['source_quote']='材料从未说过的泛化'
    if mutation=='reuse': s['task']['probe_keys']=['R2']
    if mutation=='same_text':
        d['supplemental_probes']=[{'key':'N1',**{k:v for k,v in c['retests'][1].items() if k!='key'},'source_refs':['M1']}]
        s['task']['probe_keys']=['N1']
    if mutation=='missing': s['criteria']=[]
    if mutation=='collision': d['supplemental_probes']=[{'key':'Q1','question':'覆盖原题'}]
    assert code in [v['code'] for v in compile_candidate(c,t,d)['contract']['structural_issues']]


def test_quoted_wrong_action_still_needs_semantic_review():
    c,t,d=sample();d['skills'][0]['mistakes'][0]['repair_steps'][0]['action']='把赋值画成独立复制'
    result=compile_candidate(c,t,d)
    assert not result['contract']['structural_issues']
    assert result['contract']['semantic_status']=='pending_independent_review'
    assert not result['contract']['ready_for_adoption']


def test_review_cannot_survive_content_change_or_missing_semantic_axis():
    c,t,d=sample();candidate=compile_candidate(c,t,d)
    review={'candidate_digest':digest(candidate),'axes':dict.fromkeys(REVIEW_AXES,True),
            'reviewer':'test-only','evidence':['test receipt'],'blockers':[]}
    assert attach_review(candidate,review)['contract']['sample_usable']
    assert not attach_review(candidate,review)['contract']['ready_for_adoption']
    incomplete=deepcopy(review);del incomplete['axes']['prediction']
    with pytest.raises(ValueError,match='incomplete_semantic_review'): attach_review(candidate,incomplete)
    changed=deepcopy(candidate);changed['skills'][0]['mistakes'][0]['prediction']='True'
    with pytest.raises(ValueError,match='stale_semantic_review'): attach_review(changed,review)


def test_one_failed_axis_blocks_usable_even_with_valid_structure():
    c,t,d=sample();candidate=compile_candidate(c,t,d)
    axes=dict.fromkeys(REVIEW_AXES,True);axes['repair']=False
    review={'candidate_digest':digest(candidate),'axes':axes,'reviewer':'test-only','evidence':['bad action']}
    assert not attach_review(candidate,review)['contract']['sample_usable']
