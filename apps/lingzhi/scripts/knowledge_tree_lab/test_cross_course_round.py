from copy import deepcopy
import pytest
from .cross_course_round import COURSES, parse, validate_tree, validate_teaching

TREE={'status':'candidate','categories':[{'key':'G1','parent_key':None,'name':'分类'}],
      'points':[{'key':'P1','parent_key':'G1','statement':'原命题','meta_question':'原问题','meta_answer':'原答案','source_refs':['M1']}], 'relations':[]}


@pytest.mark.parametrize('kind',['foreign_source','cycle','foreign_parent','duplicate_point','strength'])
def test_tree_contract_rejects_invalid_sources_and_links(kind):
    tree=deepcopy(TREE)
    if kind=='foreign_source':tree['points'][0]['source_refs']=['UNKNOWN']
    if kind=='cycle':tree['categories'][0]['parent_key']='G1'
    if kind=='foreign_parent':tree['points'][0]['parent_key']='G9'
    if kind=='duplicate_point':tree['points'].append(deepcopy(tree['points'][0]))
    if kind=='strength':
        tree['points'].append({**deepcopy(tree['points'][0]),'key':'P2'})
        tree['relations']=[{'from':'P1','to':'P2','type':'prerequisite','strength':'strong'}]
    assert validate_tree(COURSES[0],tree)


def test_missing_assessment_reference_is_not_counted_as_coverage_success():
    doc={'skills':[{'point_keys':['P1'],'observable_behavior':'画图','task':{'prompt':'具体任务','expected_evidence':'图'},
        'criteria':[{'point_key':'P1','probe_key':None,'pass_evidence':'证据'}],
        'mistakes':[{'point_keys':['P1'],'probe_key':'Q1','wrong_rule':'错规则','observable_error':'错表现','prediction':'错答','reason':'规则推导','repair_steps':['画图','核对']}],
        'discrimination':{'probe_keys':['Q1']},'retest_key':'R1','mastery_requirements':['达标']} ]}
    assert 'criterion_ref' in validate_teaching(COURSES[0],TREE,doc)


def test_format_fence_does_not_rewrite_content():
    assert parse('```json\n{"a":1}\n```')=={'a':1}


def test_history_requires_rubric_not_unique_answer_matching():
    history=next(c for c in COURSES if c['key']=='history')
    assert all(q['evidence_type']=='rubric' for q in history['probes']+history['retests'])
    assert '虚构' in history['materials'][-1]['text']
