from copy import deepcopy
import json
import pytest
from backend.tests.test_knowledge_semantic_review import candidate


def record(verdict='valid',point=None):
    return {'audits':{'P1':{'verdict':verdict,'reason':'核对命题真值','test_case':'检查满足全部条件的边界实例','point':point}}}


def test_truth_only_review_keeps_identity_and_accepts_a_scoped_core_correction():
    from knowledge_truth_review import compile_audits, truth_prompt
    from knowledge_truth_review import CORE_FIELDS
    old=candidate('错误的全称命题');before=deepcopy(old)
    corrected={k:deepcopy(old[k]) for k in CORE_FIELDS};corrected['statement']='补足必要范围后的正确命题'
    result=compile_audits(record('corrected',corrected),[old])
    assert result['points'][0]['key']=='P1'
    assert result['points'][0]['statement']==corrected['statement']
    assert old==before
    prompt=truth_prompt([old],{'course_title':'课程'})
    assert 'examples' not in json.loads(prompt.split('\nINPUT_JSON:\n')[1])['points'][0]
    assert '粒度' in prompt


def test_ineffective_truth_repair_and_silent_rewrites_are_rejected():
    from knowledge_truth_review import compile_audits
    from knowledge_truth_review import CORE_FIELDS
    old=candidate();facts={k:old[k] for k in CORE_FIELDS}
    with pytest.raises(ValueError):compile_audits(record('corrected',facts),[old])
    with pytest.raises(ValueError):compile_audits(record('valid',facts),[old])
    with pytest.raises(ValueError):compile_audits({'audits':{}},[old])
    pending=compile_audits(record('uncertain'),[old])
    assert pending['issues'][0]['severity']=='blocking'
    assert pending['points'][0]['statement']==old['statement']



def test_truth_correction_accepts_only_core_and_keeps_all_other_fields_frozen():
    from knowledge_truth_review import compile_audits, truth_prompt
    old=candidate('错误结论');old.update(teaching_context=['原教学场景'],examples=['原例子'],custom_attachment={'keep':True})
    before=deepcopy(old)
    core={'statement':'修正结论','conditions':['适用前提'],'symbol_definitions':['x 表示输入']}
    result=compile_audits(record('corrected',core),[old])['points'][0]
    assert {k:result[k] for k in core}==core
    assert all(result[k]==v for k,v in before.items() if k not in core)
    assert old==before
    for extra in ['teaching_context','examples','knowledge_type','name']:
        with pytest.raises(ValueError):compile_audits(record('corrected',{**core,extra:'不允许改'}),[old])
    prompt=truth_prompt([old],{})
    assert 'knowledge_truth_review_v2' in prompt
    assert 'point含statement,knowledge_type' not in prompt
