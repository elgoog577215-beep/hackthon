from copy import deepcopy
import pytest
from backend.tests.test_knowledge_semantic_review import candidate


def certified(key,group=None):
    return {**candidate('等价命题',key),'semantic_review':{'independence_group':group or key}}


def match(target):
    return dict(action='match',target=target,same_claim=True,same_scope=True,same_symbols=True,reason='完整知识等价')


def test_explicit_equivalence_chains_are_resolved_without_moving_existing_identity():
    from knowledge_identity_matching import resolve_matches
    rows=[certified(k) for k in ['A','B','C']]
    old={**candidate(),'key':'E1','knowledge_id':'stored','revision_id':'old-revision','name':'既有名称'}
    before=deepcopy(old)
    result=resolve_matches(rows,[old],{'A':match('B'),'B':match('C'),'C':match('E1')})
    assert len(result['points'])==1
    assert result['points'][0]['knowledge_id']=='stored'
    assert set(result['points'][0]['coverage_unit_ids'])=={'A','B','C'}
    assert old==before


def test_equivalence_cycles_choose_one_stable_candidate_but_siblings_cannot_collapse():
    from knowledge_identity_matching import resolve_matches
    rows=[certified('A'),certified('B')]
    result=resolve_matches(rows,[],{'A':match('B'),'B':match('A')})
    assert len(result['points'])==1 and result['points'][0]['key']=='A'
    rows[1]['semantic_review']['independence_group']='A'
    with pytest.raises(ValueError,match='独立结论'):
        resolve_matches(rows,[],{'A':match('B'),'B':match('A')})


def test_focus_batch_needs_complete_explicit_decisions_and_never_rewrites_facts():
    from knowledge_identity_matching import parse_matches, matching_prompt
    rows=[certified('A'),certified('B')]
    with pytest.raises(ValueError):parse_matches({'decisions':{}},rows[:1],rows,[])
    with pytest.raises(ValueError):parse_matches({'decisions':{'A':match('unknown')}},rows[:1],rows,[])
    bad=match('B');bad['same_scope']=False
    with pytest.raises(ValueError):parse_matches({'decisions':{'A':bad}},rows[:1],rows,[])
    prompt=matching_prompt(rows[:1],rows,[])
    assert 'challenge' not in prompt and 'same_scope' in prompt
