from copy import deepcopy
import pytest
from .independent_round import blind, audit_gate, apply_repair, validate, AXES
from .pipeline import digest
from .cross_course_round import COURSES


def sample():
    return {'points':[{'key':'P1','path':['别名'],'name':'别名','statement':'赋值不复制',
      'conditions':['普通列表'],'meta_question':'同对象吗','source_refs':['M1'],'capability':'判断身份','mastery':'检查和迁移均正确',
      'check':{'question':'a=[1];b=a;判断a is b。','answer':'True','origin_key':'Q1'},
      'mistake':{'wrong_rule':'赋值复制','prediction':'False','derivation':['复制产生新对象'],'limits':'非唯一错因'},
      'repair':{'source_ref':'M1','source_quote':'赋值b=a使两个名字指向同一列表，不会复制列表。','action':'画对象图','cannot_infer':'不能推广到浅拷贝'},
      'transfer':{'question':'x=[3];y=x;判断身份并解释','answer':'同一对象','prerequisite_keys':[]}}], 'relations':[],'gaps':[]}


def test_blind_auditor_cannot_read_proposed_correct_answers():
    c=sample();c['gaps']=['先前裁判说答案为42'];c['points'][0]['examples']=['解答为42'];b=blind(c)
    assert 'answer' not in b['points'][0]['check']
    assert 'answer' not in b['points'][0]['transfer']
    assert c['points'][0]['check']['answer']=='True'
    assert b['points'][0]['mistake']['prediction']=='False'
    assert 'gaps' not in b
    assert 'examples' not in b['points'][0]
    assert 'mastery' not in b['points'][0]


def test_incomplete_audit_or_missing_axis_cannot_pass():
    c=sample();r={'key':'P1',**dict.fromkeys(AXES,True),'check_answer':'True',
                 'transfer_answer':'同一对象','actual_target':'身份','evidence':'赋值不复制','issues':[]}
    a={'reviews':[r],'coverage':{'complete':True,'missing':[]},'global_issues':[]}
    assert audit_gate(c,a)['model_review_passed']
    assert not audit_gate(c,a)['ready_for_adoption']
    del r['repair']
    assert not audit_gate(c,a)['model_review_passed']
    a['reviews']=[]
    assert audit_gate(c,a)['failed_keys']==['P1']


def test_scoped_patch_is_atomic_and_rejects_stale_revision():
    c=sample();before=deepcopy(c);p=deepcopy(c['points'][0]);p['check']['answer']='candidate revision'
    patch={'replacements':[p],'new_points':[],'relations':[],'gaps':[]}
    with pytest.raises(ValueError,match='repair_scope'):apply_repair(c,patch,set(),digest(c))
    assert c==before
    with pytest.raises(ValueError,match='stale_candidate'):apply_repair(c,patch,{'P1'},'stale')
    assert apply_repair(c,patch,{'P1'},digest(c))['points'][0]['check']['answer']=='candidate revision'
    assert c==before


@pytest.mark.parametrize('kind',['check','transfer','quote','frozen','duplicate'])
def test_invalid_card_does_not_count_as_checked_knowledge(kind):
    c=sample();p=c['points'][0]
    assert not validate(COURSES[0],c)
    if kind in ('check','transfer'):del p[kind]['answer']
    if kind=='quote':p['repair']['source_quote']='力与质量无关'
    if kind=='frozen':p['check']['question']='换成另一个问题'
    if kind=='duplicate':c['points'].append(deepcopy(p))
    assert validate(COURSES[0],c)
