from copy import deepcopy
import pytest
from .foundation_round import validate_inventory,validate_atoms,assemble


def sample():
    c={'key':'test','profile':'限定范围','materials':[{'id':'M1','text':'赋值不复制。例子甲。'}]}
    i={'status':'candidate','claims':[{'key':'C1','kind':'rule','claim':'赋值不复制','source_ref':'M1','quote':'赋值不复制。'},
       {'key':'C2','kind':'case','claim':'例子甲','source_ref':'M1','quote':'例子甲。'}]}
    a={'points':[{'key':'P1','name':'赋值','statement':'赋值不复制','conditions':['普通列表'],'boundaries':[],
        'meta_question':'赋值复制吗','meta_answer':'不复制','claim_refs':['C1','C2']}],
       'dispositions':[{'claim_key':'C1','role':'point','point_keys':['P1'],'reason':'规则'},
                       {'claim_key':'C2','role':'example','point_keys':['P1'],'reason':'案例'}],'gaps':[]}
    t={'categories':[{'key':'G1','parent_key':None,'name':'赋值'}],'placements':[{'point_key':'P1','parent_key':'G1'}]}
    return c,i,a,t


def test_classifier_cannot_rewrite_facts_and_program_preserves_provenance():
    c,i,a,t=sample();before=deepcopy((c,i,a,t));result=assemble(c,i,a,t)
    assert (c,i,a,t)==before
    assert result['points'][0]['statement']==a['points'][0]['statement']
    assert result['points'][0]['evidence'][1]['start']==6
    assert result['points'][0]['attachments'][0]['claim']['quote']=='例子甲。'
    assert result['inventory']==i['claims']
    assert not result['ready_for_adoption']
    assert result==assemble(c,i,a,t)
    t['points']=[{'statement':'偷偷改写'}]
    with pytest.raises(ValueError,match='classifier_rewrote_content'):assemble(c,i,a,t)


@pytest.mark.parametrize('kind',['missing','duplicate','cycle','empty','foreign'])
def test_tree_cannot_silently_drop_duplicate_or_orphan_points(kind):
    c,i,a,t=sample()
    if kind=='missing':t['placements']=[]
    if kind=='duplicate':t['placements']*=2
    if kind=='cycle':t['categories'][0]['parent_key']='G1'
    if kind=='empty':t['categories'].append({'key':'G2','parent_key':None,'name':'空'})
    if kind=='foreign':t['placements'][0]['parent_key']='G9'
    with pytest.raises(ValueError):assemble(c,i,a,t)


def test_fake_quote_and_case_as_rule_and_missing_disposition_are_detected():
    c,i,a,t=sample();assert not validate_inventory(c,i);assert not validate_atoms(i,a)
    i['claims'][0]['quote']='赋值会复制。';assert validate_inventory(c,i)
    a['dispositions'][1]['role']='point';assert 'case_as_knowledge' in validate_atoms(i,a)
    a['dispositions'].pop();assert 'inventory_coverage' in validate_atoms(i,a)
