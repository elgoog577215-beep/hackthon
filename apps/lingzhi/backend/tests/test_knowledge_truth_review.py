from copy import deepcopy
import json
import pytest
from backend.tests.test_knowledge_semantic_review import candidate


def record(verdict='valid',point=None):
    return {'audits':{'P1':{'verdict':verdict,'reason':'核对命题真值','test_case':'检查满足全部条件的边界实例','point':point}}}


def test_truth_only_review_keeps_identity_and_accepts_a_scoped_core_correction():
    from knowledge_truth_review import compile_audits, truth_prompt
    from knowledge_registry_contract import FIELDS
    old=candidate('错误的全称命题');before=deepcopy(old)
    corrected={k:deepcopy(old[k]) for k in FIELDS};corrected['statement']='补足必要范围后的正确命题'
    result=compile_audits(record('corrected',corrected),[old])
    assert result['points'][0]['key']=='P1'
    assert result['points'][0]['statement']==corrected['statement']
    assert old==before
    prompt=truth_prompt([old],{'course_title':'课程'})
    assert 'examples' not in json.loads(prompt.split('\nINPUT_JSON:\n')[1])['points'][0]
    assert '粒度' in prompt


def test_ineffective_truth_repair_and_silent_rewrites_are_rejected():
    from knowledge_truth_review import compile_audits
    from knowledge_registry_contract import FIELDS
    old=candidate();facts={k:old[k] for k in FIELDS}
    with pytest.raises(ValueError):compile_audits(record('corrected',facts),[old])
    with pytest.raises(ValueError):compile_audits(record('valid',facts),[old])
    with pytest.raises(ValueError):compile_audits({'audits':{}},[old])
    pending=compile_audits(record('uncertain'),[old])
    assert pending['issues'][0]['severity']=='blocking'
    assert pending['points'][0]['statement']==old['statement']
