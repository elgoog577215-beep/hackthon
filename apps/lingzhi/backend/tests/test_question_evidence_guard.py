"""Regressions from the frozen first C17 live round, plus negative controls."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from assessment_contracts import compile_course_assessment_profile
from assessment_semantics import should_run_semantic_review
from question_evidence_guard import CHECKS, evidence_findings, independent_evidence_admitted, stamp_evidence_admission


def fixture(key):
    root = Path(__file__).resolve().parents[2]
    samples = json.loads((root / "docs/研究/C17单点出题千问首轮样题-2026-10-11.json").read_text(encoding="utf-8"))
    sample = next(q for q in samples["questions"] if q["key"] == key)
    materials = json.loads((root / "backend/resources/knowledge_first/c17.json").read_text(encoding="utf-8"))
    point = next(p for b in materials["bundles"].values() for p in b["points"] if p["key"] == key)
    return {
        "prompt": sample["prompt"],
        "options": sample["options"],
        "question_spec": {"stimulus": {"rendered_text": sample["prompt"]}, "task": {}, "options": sample["options"]},
        "solution_envelope": {
            "canonical_answer": sample["canonical_answer"],
            "worked_solution": sample["worked_solution"],
        },
        "assessment_binding_schema": "atomic_assessment_v1",
        "primary_knowledge_ids": [sample["knowledge_id"]],
        "knowledge_revision_refs": {sample["knowledge_id"]: sample["knowledge_revision"]},
        "solution_revision_id": "s1",
        "design_brief": {
            "assessment_binding_schema": "atomic_assessment_v1",
            "primary_knowledge": point["statement"],
            "question_type": "selected_response",
            "language_contract": {"programming_languages": ["C"], "language_standard": "C17"},
        },
    }


def test_c17_is_structured_language_without_misclassifying_cpp():
    c = compile_course_assessment_profile({"course_name": "C17程序设计"})["notation_and_language"]
    assert c["programming_languages"] == ["C"]
    assert c["language_standard"] == "C17"
    cpp = compile_course_assessment_profile({"course_name": "C++17程序设计"})["notation_and_language"]
    assert "C" not in cpp["programming_languages"]


@pytest.mark.parametrize("key", ["K-T07", "K-T08", "K-I10", "K-F13"])
def test_previous_language_drift_is_rejected(key):
    assert "COURSE_LANGUAGE_MISMATCH" in {i["code"] for i in evidence_findings(fixture(key))}


@pytest.mark.parametrize("key", ["K-F03", "K-F12"])
def test_previous_rule_disclosure_is_not_hidden_by_one_letter_answer(key):
    assert "ANSWER_RULE_DISCLOSED" in {i["code"] for i in evidence_findings(fixture(key))}


def test_legitimate_code_and_wrong_distractors_are_not_treated_as_answer_disclosure():
    assert evidence_findings(fixture("K-I08")) == []


def test_atomic_choice_requires_semantic_review_even_when_letter_agrees():
    contract = fixture("K-I08")
    contract["solution_validation"] = {"deterministic": True, "passed": True}
    assert should_run_semantic_review(contract, {"passed": True})


def test_missing_review_cannot_count_as_independent_evidence():
    contract = fixture("K-I08")
    stamp_evidence_admission(contract, {"passed": True, "solution_consistent": True})
    assert not independent_evidence_admitted(contract)


def test_verified_admission_is_bound_to_exact_question_and_solution_revision():
    contract = fixture("K-I08")
    report = {
        "passed": True,
        "solution_consistent": True,
        "reviewer_triggered": True,
        "evidence_checks": {key: True for key in CHECKS},
        "review_witness": {
            "option_audit": [{"option_id": o["id"], "meaning": o["text"], "is_correct": o["id"] == "B",
                              "reason": "if控制空语句，后面的赋值在条件真假两种情况下都会执行。"} for o in contract["options"]],
            "observation_test": {"target_statement": contract["design_brief"]["primary_knowledge"],
                "observed_quantity": "n不大于10时是否执行赋值", "public_anchor": "flag = 1",
                "incorrect_rule": "误认为if控制分号后面的赋值", "correct_prediction": "执行赋值",
                "incorrect_prediction": "不执行赋值", "trace": "条件为假仍执行后续独立赋值，错误规则则跳过赋值。"},
            "unsupported_assumptions": [],
        },
    }
    stamp_evidence_admission(contract, report)
    assert independent_evidence_admitted(contract)
    changed = deepcopy(contract)
    changed["prompt"] += "已知答案是B。"
    assert not independent_evidence_admitted(changed)
    changed = deepcopy(contract)
    changed["solution_revision_id"] = "s2"
    assert not independent_evidence_admitted(changed)


def test_disclosed_item_remains_ineligible_even_if_reviewer_says_yes():
    contract = fixture("K-F03")
    stamp_evidence_admission(
        contract,
        {
            "passed": True,
            "solution_consistent": True,
            "reviewer_triggered": True,
            "evidence_checks": dict(
                language_aligned=True,
                no_answer_leakage=True,
                explanation_consistent=True,
                independently_assessable=True,
            ),
        },
    )
    assert not independent_evidence_admitted(contract)


@pytest.mark.asyncio
async def test_old_persisted_allow_flag_cannot_make_disclosed_answer_independent():
    from knowledge_mastery import build_knowledge_profile
    from practice_grading import PracticeGrader

    task = fixture("K-F03")
    kid = task["primary_knowledge_ids"][0]
    task.update(
        input_contract={"mode": "choice"},
        validation_mode="exact_validator",
        grading_policy={"method": "typed_validator"},
        validation_policy={"mastery_eligible": True},
        answer_spec={"canonical_answer": "A", "validation_mode": "exact_validator"},
    )
    result = await PracticeGrader.grade(
        object.__new__(PracticeGrader), task, {"submitted_answer_payload": {"selected_option_id": "A"}}
    )
    assert result["passed"] is True
    assert result["mastery_eligible"] is False
    assert result["evidence_strength"] == "invalid"
    base = {
        "lifecycle_status": "active",
        "revision_id": "baseline",
        "knowledge_points": [
            {
                "knowledge_id": kid,
                "revision_id": task["knowledge_revision_refs"][kid],
                "status": "active",
                "granularity_status": "atomic",
            }
        ],
    }
    attempt = {
        "attempt_id": "a",
        "user_id": "u",
        "course_id": "c",
        "course_version_id": "v",
        "status": "graded",
        "task_revision_id": "q",
        "concept_ids": [kid],
        "knowledge_revision_refs": task["knowledge_revision_refs"],
        "result": result,
    }
    profile = build_knowledge_profile(
        base, course_id="c", course_version_id="v", user_id="u", attempts=[attempt], events=[]
    )
    assert profile["nodes"][0]["mastery"] is None
    assert profile["nodes"][0]["independent_count"] == 0


def test_adopted_standard_overrides_incidental_comparison_language():
    course = {
        "course_name": "程序设计（对比Python）",
        "course_knowledge_base": {"status": "accepted", "sources": {"course_context": {"language_standard": "C17"}}},
    }
    c = compile_course_assessment_profile(course)["notation_and_language"]
    assert c["programming_languages"] == ["C"] and c["language_standard"] == "C17"


def test_question_form_proposition_is_not_an_asserted_rule():
    q = fixture("K-F03")
    q["question_spec"]["stimulus"]["rendered_text"] = (
        "for控制条件在首次评估时即为假，循环体被执行零次，这个说法是否正确？"
    )
    q["prompt"] = q["question_spec"]["stimulus"]["rendered_text"]
    assert not evidence_findings(q)


def test_last_line_task_cannot_admit_multiline_complete_output_as_answer():
    task = fixture("K-I08")
    task["prompt"] = "程序输出A和计数，请选择输出的最后一行（包含换行符）。"
    task["options"] = [{"id": "B", "text": "A:\neval_count=0\n"}, {"id": "C", "text": "A:\neval_count=1\n"}]
    task["question_spec"]["options"] = task["options"]
    assert "RESPONSE_SCOPE_MISMATCH" in {i["code"] for i in evidence_findings(task)}


def test_complete_output_task_allows_multiple_lines():
    task = fixture("K-I08")
    task["prompt"] = "请选择程序的完整输出。"
    task["options"] = [{"id": "B", "text": "A:\neval_count=0\n"}]
    task["question_spec"]["options"] = task["options"]
    assert not evidence_findings(task)
