from __future__ import annotations

from copy import deepcopy

import pytest

from question_bank import (
    build_question_bank,
    filter_question_bank_items,
    formal_task_from_question_bank_item,
)
from routers.practice import _student_question_payload


def _course(
    *,
    course_id: str,
    mode: str,
    node_name: str,
    objective: str,
    content: str,
    assessment: str,
) -> dict:
    return {
        "course_id": course_id,
        "course_name": node_name,
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
            "node_id": f"{course_id}-node",
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


@pytest.mark.parametrize(
    ("mode", "node_name", "objective", "assessment", "archetype_id"),
    [
        (
            "math_formal",
            "函数极限",
            "根据定义推导并计算函数极限",
            "写出推导、条件与结果检查",
            "symbolic_derivation",
        ),
        (
            "natural_science",
            "热力学第一定律",
            "使用能量守恒计算封闭系统的状态变化",
            "列出已知量、方程、单位和边界检查",
            "numeric_calculation",
        ),
        (
            "programming_engineering",
            "Java 并发调试",
            "定位竞态条件并修复线程安全问题",
            "提交代码、测试和执行证据",
            "code_execution",
        ),
        (
            "humanities_social",
            "工业革命的社会影响",
            "依据两则史料论证社会结构变化",
            "引用史料形成论点、证据和限定",
            "evidence_argument",
        ),
        (
            "language_learning",
            "学术摘要写作",
            "根据研究材料撰写英文摘要",
            "完成摘要并说明语域选择",
            "language_production",
        ),
        (
            "business_career",
            "有限预算下的渠道决策",
            "比较方案并在预算约束下作出决策",
            "提交比较、选择、权衡和风险",
            "constrained_decision",
        ),
    ],
)
def test_question_bank_builds_v2_candidates_for_every_subject_family(
    mode: str,
    node_name: str,
    objective: str,
    assessment: str,
    archetype_id: str,
):
    course = _course(
        course_id=f"course-{mode}",
        mode=mode,
        node_name=node_name,
        objective=objective,
        content=(
            f"本节围绕“{node_name}”给出定义、条件、材料与示例。"
            "学生必须使用题面给定的输入完成任务，并提供可以复核的过程和结果检查。"
        ),
        assessment=assessment,
    )

    bundle = build_question_bank(course)

    assert bundle["assessment_profile"]["schema_version"] == (
        "course_assessment_profile_v1"
    )
    assert bundle["assessment_objectives"][0]["schema_version"] == (
        "assessment_objective_v1"
    )
    generated = [
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    ]
    assert len(generated) == 3
    assert {
        item["question_spec"]["schema_version"]
        for item in generated
    } == {"question_spec_v2"}
    slots = {
        slot["practice_level"]: slot
        for slot in bundle["assessment_blueprint"]["nodes"][0][
            "slots"
        ]
    }
    assert archetype_id in {
        item["archetype_id"]
        for item in generated
    }
    assert len({
        item["input_contract"]["mode"]
        for item in generated
    }) >= 2
    for item in generated:
        slot = slots[item["practice_levels"][0]]
        assert item["archetype_id"] == slot["archetype_id"]
        assert item["question_type"] == slot["question_type"]
        assert item["input_contract"]["mode"] == slot["input_mode"]
        if mode in {
            "programming_engineering",
            "humanities_social",
            "language_learning",
        }:
            assert (
                item["compiled_contract_validation"]["passed"]
                is False
            )
            assert item["lifecycle_status"] == "needs_review"
        else:
            assert (
                item["compiled_contract_validation"]["passed"]
                is True
            )
        if slot["input_mode"] == "choice":
            assert len(item["options"]) >= 2
        else:
            assert item["options"] == []
    assert all(item["generation_status"] for item in generated)
    assert all(
        item["lifecycle_status"] in {"approved", "needs_review"}
        for item in generated
    )


def test_v2_solution_is_stored_privately_and_hydrated_only_for_internal_task():
    course = _course(
        course_id="course-private-solution",
        mode="humanities_social",
        node_name="史料论证",
        objective="依据两则史料形成因果论证",
        content=(
            "材料一：工厂劳动时间显著增加。"
            "材料二：工业城市人口增长且住房压力上升。"
            "回答必须逐条引用材料，并区分相关关系与因果关系。"
        ),
        assessment="形成论点、证据、推理和限定",
    )

    bundle = build_question_bank(course)
    item = next(
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    )
    solution_id = item["solution_revision_id"]

    assert solution_id in bundle["solution_envelopes"]
    assert "canonical_answer" not in repr(item["question_spec"])
    assert "solution_envelope" not in item
    assert "answer_spec" not in item
    assert item["formal_task"]["solution_revision_id"] == solution_id
    assert not item["formal_task"]["answer_spec"]
    internal_task = formal_task_from_question_bank_item({
        **item,
        "_solution_envelope": bundle["solution_envelopes"][
            solution_id
        ],
    })
    assert internal_task["answer_spec"]
    assert item["formal_task"]["hint_contract"]["generator"] == (
        "solution_graph_v1"
    )


def test_question_bank_filters_v2_generation_metadata():
    course = _course(
        course_id="course-filter-v2",
        mode="programming_engineering",
        node_name="代码测试与调试",
        objective="定位程序错误并提交修复",
        content=(
            "给定程序、输入输出契约和三个失败测试。"
            "需要保留接口，修复错误，并补充边界测试与运行记录。"
        ),
        assessment="提交代码、测试和执行轨迹",
    )
    bundle = build_question_bank(course)
    item = next(
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    )

    filtered = filter_question_bank_items(
        bundle,
        archetype_id=item["archetype_id"],
        validation_mode=item["validation_mode"],
        risk_level=item["risk_level"],
        objective_id=item["objective_id"],
        generation_status=item["generation_status"],
    )

    assert filtered
    assert all(
        filtered_item["archetype_id"] == item["archetype_id"]
        for filtered_item in filtered
    )


def test_fallback_questions_without_complete_solution_do_not_auto_publish():
    course = _course(
        course_id="course-programming-diagnostics",
        mode="programming_engineering",
        node_name="内存泄漏检测与诊断方法",
        objective="诊断并修复 Python 内存泄漏",
        content=(
            "给定 tracemalloc 快照、引用链和失败测试。"
            "需要定位泄漏原因、提交修复代码并执行回归测试。"
        ),
        assessment="提交代码、测试和诊断依据",
    )

    bundle = build_question_bank(course)
    practice = [
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    ]

    assert len(practice) == 3
    concept = next(
        item
        for item in practice
        if item["practice_levels"] == ["concept_check"]
    )
    assert all(
        item["review_tier"] == "mandatory_review"
        and item["lifecycle_status"] == "needs_review"
        and item["generation_status"] != "published"
        for item in practice
    )
    assert (
        concept["compiled_contract_validation"]["passed"]
        is False
    )


def test_fallback_open_questions_require_independent_review():
    course = _course(
        course_id="course-family-sample",
        mode="programming_engineering",
        node_name="并发代码测试",
        objective="定位竞态条件并验证修复",
        content=(
            "给定线程安全要求、失败测试和执行轨迹。"
            "需要修复代码并补充边界测试。"
        ),
        assessment="提交代码、测试和执行证据",
    )

    bundle = build_question_bank(course)
    practice = [
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    ]
    assert len(practice) == 3
    assert sum(
        item["review_tier"] == "auto_publish"
        and item["lifecycle_status"] == "approved"
        for item in practice
    ) == 0
    assert sum(
        item["review_tier"] == "mandatory_review"
        and item["lifecycle_status"] == "needs_review"
        for item in practice
    ) == 3
    assert bundle["review_queue"]["sample_count"] == 0
    assert bundle["review_queue"]["sample_items"] == []
    assert bundle["review_policy"][
        "default_publish_after_validation"
    ] is True
    assert bundle["review_policy"]["post_publication_rework"] is True


def test_practice_student_payload_uses_public_allowlist():
    internal = {
        "revision_id": "qr-1",
        "node_id": "node-1",
        "prompt": "完成题目",
        "options": [],
        "question_type": "structured_response",
        "practice_level": "objective_practice",
        "answer_spec": {"canonical_answer": "SECRET"},
        "solution_envelope": {"hidden_tests": ["SECRET"]},
        "solution_revision_id": "sol-secret",
        "question_spec": {"validator_config": "SECRET"},
        "grading_policy": {"reference": "SECRET"},
        "future_private_field": "SECRET",
    }

    public = _student_question_payload(deepcopy(internal))

    assert public == {
        "revision_id": "qr-1",
        "node_id": "node-1",
        "prompt": "完成题目",
        "options": [],
        "question_type": "structured_response",
        "practice_level": "objective_practice",
    }
