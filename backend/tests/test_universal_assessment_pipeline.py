from __future__ import annotations

from copy import deepcopy

import pytest

from assessment_contracts import (
    ASSESSMENT_ARCHETYPES,
    compile_assessment_objectives,
    compile_course_assessment_profile,
    project_public_question,
    select_assessment_archetype,
)
from assessment_generation import generate_universal_question_contract
from assessment_validators import validate_solution_envelope


def _course(
    *,
    mode: str,
    course_name: str,
    node_name: str,
    objective: str,
    content: str,
    assessment: str,
) -> dict:
    return {
        "course_id": f"universal-{mode}",
        "course_name": course_name,
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": mode,
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": node_name,
            "node_content": content,
            "learning_objective": objective,
            "key_points": [node_name],
            "assessment": [assessment],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


def test_course_assessment_profile_exposes_all_ten_archetypes_and_version():
    course = _course(
        mode="humanities_social",
        course_name="世界史",
        node_name="工业革命的社会影响",
        objective="依据史料解释工业革命造成的社会结构变化",
        content="材料一记录工厂劳动时间，材料二描述城市人口增长。",
        assessment="引用材料形成因果论证",
    )

    profile = compile_course_assessment_profile(course)

    assert profile["schema_version"] == "course_assessment_profile_v1"
    assert profile["profile_revision_id"].startswith("cap_")
    assert profile["course_id"] == course["course_id"]
    assert profile["discipline"]["family"] == "humanities_social"
    assert profile["classification"]["confidence"] >= 0.8
    assert set(profile["allowed_archetype_ids"]) == set(
        ASSESSMENT_ARCHETYPES
    )
    assert profile["source_policy"]["priority"] == [
        "teacher_question_bank",
        "course_materials",
        "trusted_web_reference",
        "general_model_knowledge",
    ]


def test_title_only_objective_is_low_confidence_and_requires_review():
    course = _course(
        mode="programming_engineering",
        course_name="C++ 程序设计",
        node_name="函数模板",
        objective="理解并应用函数模板",
        content="",
        assessment="编写并测试函数模板",
    )
    profile = compile_course_assessment_profile(course)

    objectives = compile_assessment_objectives(course, profile)

    assert len(objectives) == 1
    assert objectives[0]["schema_version"] == "assessment_objective_v1"
    assert objectives[0]["source_sufficiency"] == "insufficient"
    assert objectives[0]["confidence"] == "low"
    assert objectives[0]["risk_level"] == "teacher_review"
    assert objectives[0]["generation_status"] == "candidate_only"


@pytest.mark.parametrize(
    ("mode", "node_name", "objective", "assessment", "expected"),
    [
        (
            "math_formal",
            "函数极限",
            "推导并计算给定函数的极限",
            "写出形式化推导",
            "symbolic_derivation",
        ),
        (
            "natural_science",
            "实验变量控制",
            "设计实验检验温度对反应速率的影响",
            "给出自变量、因变量和控制变量",
            "controlled_experiment",
        ),
        (
            "programming_engineering",
            "空指针调试",
            "定位并修复程序中的空指针错误",
            "提交代码、测试和调试依据",
            "code_execution",
        ),
        (
            "humanities_social",
            "史料中的改革影响",
            "依据两则史料论证改革影响",
            "引用证据形成论点",
            "evidence_argument",
        ),
        (
            "language_learning",
            "商务邮件写作",
            "在给定情境中撰写英文邮件",
            "完成得体表达并说明语气选择",
            "language_production",
        ),
        (
            "business_career",
            "有限预算下的渠道选择",
            "比较方案并在预算约束下决策",
            "给出选择、权衡和风险",
            "constrained_decision",
        ),
    ],
)
def test_structured_archetype_selection_crosses_subject_boundaries(
    mode: str,
    node_name: str,
    objective: str,
    assessment: str,
    expected: str,
):
    course = _course(
        mode=mode,
        course_name=node_name,
        node_name=node_name,
        objective=objective,
        content=(
            f"本节围绕“{node_name}”给出定义、条件、示例与反例，"
            "学生必须使用材料中的约束完成任务并核对结论。"
        ),
        assessment=assessment,
    )
    profile = compile_course_assessment_profile(course)
    compiled = compile_assessment_objectives(course, profile)[0]

    archetype = select_assessment_archetype(compiled, profile)

    assert archetype["archetype_id"] == expected
    assert archetype["required_stimulus_fields"]
    assert archetype["eligible_validation_modes"]
    assert archetype["selection_confidence"] >= 0.7


def test_universal_contract_separates_public_spec_from_private_solution():
    course = _course(
        mode="humanities_social",
        course_name="世界史",
        node_name="工业革命的社会影响",
        objective="依据材料解释工业革命造成的社会结构变化",
        content=(
            "材料一：工厂工人的平均劳动时间显著增加。"
            "材料二：工业城市人口快速增长，住房与卫生压力上升。"
        ),
        assessment="引用两则材料形成因果论证",
    )
    profile = compile_course_assessment_profile(course)
    objective = compile_assessment_objectives(course, profile)[0]

    contract = generate_universal_question_contract(
        course,
        course["nodes"][0],
        profile=profile,
        objective=objective,
        practice_level="objective_practice",
        variant_index=0,
    )

    spec = contract["question_spec"]
    solution = contract["solution_envelope"]
    serialized_spec = repr(spec)
    assert spec["schema_version"] == "question_spec_v2"
    assert spec["archetype_id"] == "evidence_argument"
    assert spec["solution_revision_id"] == solution["solution_revision_id"]
    assert "canonical_answer" not in serialized_spec
    assert "hidden_tests" not in serialized_spec
    assert solution["schema_version"] == "solution_envelope_v1"
    assert solution["rubric"]
    assert solution["solution_graph"]["steps"]
    assert contract["prompt"] != course["nodes"][0]["learning_objective"]
    assert "材料一" in contract["prompt"]


def test_solution_disagreement_requires_review_and_blocks_auto_publish():
    question_spec = {
        "schema_version": "question_spec_v2",
        "archetype_id": "numeric_calculation",
        "response_contract": {"format": "numeric_with_unit"},
        "risk_contract": {"risk_level": "low"},
        "solution_revision_id": "sol-example",
    }
    envelope = {
        "schema_version": "solution_envelope_v1",
        "solution_revision_id": "sol-example",
        "validation_mode": "numeric_unit_validator",
        "canonical_answer": {"value": 10.0, "unit": "J"},
        "validator_config": {"absolute_tolerance": 0.01},
        "rubric": ["数值正确", "单位正确"],
        "solution_graph": {"steps": ["代入数据", "核对单位"]},
    }

    report = validate_solution_envelope(
        question_spec,
        envelope,
        independent_solution={"value": 12.0, "unit": "J"},
    )

    assert report["schema_version"] == "solution_validation_report_v1"
    assert report["passed"] is False
    assert report["status"] == "needs_review"
    assert report["auto_publish_eligible"] is False
    assert "independent_solution_mismatch" in {
        issue["code"] for issue in report["issues"]
    }


def test_student_question_projection_is_allowlist_based():
    internal = {
        "revision_id": "qr-secret",
        "node_id": "node-1",
        "prompt": "完成题目",
        "options": [],
        "question_type": "worked_solution",
        "difficulty_contract": {"target_level": "intermediate"},
        "practice_level": "objective_practice",
        "answer_spec": {"canonical_answer": "SECRET"},
        "solution_envelope": {"hidden_tests": ["SECRET TEST"]},
        "hidden_tests": ["DO NOT LEAK"],
        "question_spec": {"private_validator_config": "SECRET CONFIG"},
        "grading_policy": {"reference_answer": "SECRET"},
        "unexpected_internal_field": "SECRET",
    }

    public = project_public_question(deepcopy(internal))

    assert public == {
        "revision_id": "qr-secret",
        "node_id": "node-1",
        "prompt": "完成题目",
        "options": [],
        "question_type": "worked_solution",
        "difficulty_contract": {"target_level": "intermediate"},
        "practice_level": "objective_practice",
    }

