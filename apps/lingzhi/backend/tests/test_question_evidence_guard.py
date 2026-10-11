"""Regressions from the frozen first C17 live round, plus negative controls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from assessment_contracts import compile_course_assessment_profile
from assessment_semantics import evaluate_question_semantic_preflight, should_run_semantic_review
from question_evidence_guard import evidence_findings, stamp_evidence_admission, independent_evidence_admitted


def fixture(key):
    root = Path(__file__).resolve().parents[2]
    samples = json.loads((root / 'docs/研究/C17单点出题千问首轮样题-2026-10-11.json').read_text(encoding='utf-8'))
    sample = next(q for q in samples['questions'] if q['key'] == key)
    materials = json.loads((root / 'backend/resources/knowledge_first/c17.json').read_text(encoding='utf-8'))
    point = next(p for b in materials['bundles'].values() for p in b['points'] if p['key'] == key)
    return {'prompt': sample['prompt'], 'options': sample['options'],
            'question_spec': {'stimulus': {'rendered_text': sample['prompt']}, 'task': {}, 'options': sample['options']},
            'solution_envelope': {'canonical_answer':sample['canonical_answer'], 'worked_solution':sample['worked_solution']},
            'assessment_binding_schema':'atomic_assessment_v1', 'primary_knowledge_ids':[sample['knowledge_id']],
            'knowledge_revision_refs':{sample['knowledge_id']:sample['knowledge_revision']},
            'solution_revision_id':'s1',
            'design_brief': {'assessment_binding_schema':'atomic_assessment_v1', 'primary_knowledge':point['statement'],
                             'question_type':'selected_response','language_contract': {'programming_languages':['C'],'language_standard':'C17'}}}


def test_c17_is_structured_language_without_misclassifying_cpp():
    c=compile_course_assessment_profile({'course_name':'C17程序设计'})['notation_and_language']
    assert c['programming_languages']==['C']
    assert c['language_standard']=='C17'
    cpp=compile_course_assessment_profile({'course_name':'C++17程序设计'})['notation_and_language']
    assert 'C' not in cpp['programming_languages']


@pytest.mark.parametrize('key', ['K-T07','K-T08','K-I10','K-F13'])
def test_previous_language_drift_is_rejected(key):
    assert 'COURSE_LANGUAGE_MISMATCH' in {i['code'] for i in evidence_findings(fixture(key))}


@pytest.mark.parametrize('key', ['K-F03','K-F12'])
def test_previous_rule_disclosure_is_not_hidden_by_one_letter_answer(key):
    assert 'ANSWER_RULE_DISCLOSED' in {i['code'] for i in evidence_findings(fixture(key))}


def test_legitimate_code_and_wrong_distractors_are_not_treated_as_answer_disclosure():
    assert evidence_findings(fixture('K-I08')) == []


def test_atomic_choice_requires_semantic_review_even_when_letter_agrees():
    contract=fixture('K-I08')
    contract['solution_validation']={'deterministic':True, 'passed':True}
    assert should_run_semantic_review(contract, {'passed':True})


def test_missing_review_cannot_count_as_independent_evidence():
    contract=fixture('K-I08')
    stamp_evidence_admission(contract, {'passed':True,'solution_consistent':True})
    assert not independent_evidence_admitted(contract)


def test_verified_admission_is_bound_to_exact_question_and_solution_revision():
    contract=fixture('K-I08')
    report={'passed':True,'solution_consistent':True,'reviewer_triggered':True,
            'evidence_checks':dict(language_aligned=True,no_answer_leakage=True,explanation_consistent=True,independently_assessable=True)}
    stamp_evidence_admission(contract, report)
    assert independent_evidence_admitted(contract)
    changed=deepcopy(contract);changed['prompt']+='已知答案是B。'
    assert not independent_evidence_admitted(changed)
    changed=deepcopy(contract);changed['solution_revision_id']='s2'
    assert not independent_evidence_admitted(changed)


def test_disclosed_item_remains_ineligible_even_if_reviewer_says_yes():
    contract=fixture('K-F03')
    stamp_evidence_admission(contract, {'passed':True,'solution_consistent':True,'reviewer_triggered':True,
        'evidence_checks':dict(language_aligned=True,no_answer_leakage=True,explanation_consistent=True,independently_assessable=True)})
    assert not independent_evidence_admitted(contract)
