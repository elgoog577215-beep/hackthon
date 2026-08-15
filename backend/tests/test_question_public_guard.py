"""G1 可观察动作字段 + G2 公开/私有边界常驻守卫。"""
from __future__ import annotations

import pytest

from question_public_guard import (
    FORBIDDEN_PUBLIC_FIELDS,
    assert_no_answer_leak,
    find_answer_leaks,
    rejected_teacher_patch_fields,
)


# --- G2：常驻守卫 -----------------------------------------------------------


def test_clean_public_question_passes() -> None:
    public = {
        "revision_id": "qbr_1",
        "prompt": "计算内能变化",
        "options": [{"id": "A", "text": "12 kJ"}, {"id": "B", "text": "28 kJ"}],
        "input_contract": {"mode": "choice"},
        "hint_contract": {"levels": [{"level": 1, "text": "先统一符号"}]},
    }
    assert find_answer_leaks(public) == []
    assert_no_answer_leak(public)


@pytest.mark.parametrize("field", sorted(FORBIDDEN_PUBLIC_FIELDS))
def test_every_forbidden_field_is_detected_at_top_level(field) -> None:
    assert find_answer_leaks({field: "x"}) == [field]


def test_blanked_answer_field_is_not_reported_as_a_leak() -> None:
    """V2 投影会把 answer_spec 显式置空以保持键形状稳定。

    把空壳报成泄漏会让守卫天天喊狼来了，真泄漏反而没人看。
    """
    assert find_answer_leaks({"answer_spec": {}}) == []
    assert find_answer_leaks({"canonical_answer": ""}) == []
    assert find_answer_leaks({"hidden_tests": []}) == []
    # 但只要带上内容就必须报
    assert find_answer_leaks({"answer_spec": {"correct_answer": "12"}}) == [
        "answer_spec",
    ]
    assert find_answer_leaks({"canonical_answer": 0}) == ["canonical_answer"]


def test_nested_leak_is_found() -> None:
    """泄漏常发生在嵌套投影里，只查顶层等于没查。"""
    leaked = {
        "formal_task": {
            "prompt": "题干",
            "source_item": {"answer_spec": {"correct_answer": "12"}},
        },
    }
    assert find_answer_leaks(leaked) == [
        "formal_task.source_item.answer_spec",
    ]


def test_leak_inside_a_list_is_found() -> None:
    leaked = {"items": [{"prompt": "甲"}, {"prompt": "乙", "canonical_answer": 12}]}
    assert find_answer_leaks(leaked) == ["items[1].canonical_answer"]


def test_guard_raises_rather_than_returning_false() -> None:
    """答案泄漏不该有"忽略"这个选项。"""
    with pytest.raises(AssertionError, match="leaked private answer fields"):
        assert_no_answer_leak(
            {"answer_spec": {"correct_answer": "12"}},
            context="student payload",
        )


def test_guard_message_names_the_context_and_path() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_no_answer_leak(
            {"task": {"solution_envelope": {"rubric": ["列式"]}}},
            context="practice payload",
        )
    message = str(excinfo.value)
    assert "practice payload" in message
    assert "task.solution_envelope" in message


def test_scan_is_depth_bounded_and_does_not_hang() -> None:
    deep: dict = {"answer_spec": 1}
    for _ in range(50):
        deep = {"nested": deep}
    # 超出扫描深度就不再往下找，但不能崩
    assert find_answer_leaks(deep) == []


def test_real_student_facing_projection_has_no_leak() -> None:
    """拿真实的学生侧投影跑一遍守卫，而不是只测手搓的字典。"""
    from assessment_contracts import project_public_question

    internal_task = {
        "revision_id": "qbr_1",
        "question_id": "q_1",
        "node_id": "L2-1-1",
        "prompt": "计算内能变化",
        "question_type": "short_answer",
        "options": [],
        "concept_ids": ["ckp_1"],
        # 下面这些是私有的，公开投影必须把它们挡在外面
        "answer_spec": {"type": "exact", "correct_answer": "12 kJ"},
        "canonical_answer": "12 kJ",
        "solution_envelope": {"rubric": ["列式", "核对单位"]},
        "hidden_tests": [{"test_id": "t1", "stdin": "", "expected_output": "12"}],
    }
    public = project_public_question(internal_task)

    assert_no_answer_leak(public, context="student-facing question")
    assert public["prompt"] == "计算内能变化"
    assert "12 kJ" not in repr(public)


# --- G2：教师题面修订不得改答案 ---------------------------------------------


def test_teacher_patch_rejects_answer_fields() -> None:
    assert rejected_teacher_patch_fields(
        {"prompt": "新题干", "answer_spec": {}},
    ) == ["answer_spec"]
    assert rejected_teacher_patch_fields(
        {"correct_answer": "12", "canonical_answer": "12"},
    ) == ["canonical_answer", "correct_answer"]


def test_teacher_patch_allows_wording_only_changes() -> None:
    assert rejected_teacher_patch_fields(
        {"prompt": "新题干", "explanation": "新解析", "options": []},
    ) == []


def test_revise_rejects_answer_spec_on_legacy_items_too() -> None:
    """此前只在 V2 题上拒绝，旧题可经题面修订接口改标准答案——这里堵住。"""
    from question_bank import revise_question_bank_item

    legacy_bundle = {
        "schema_version": "question_bank_bundle_v1",
        "course_id": "c1",
        "bundle_revision_id": "qbb_1",
        "items": [{
            "item_id": "qbi_1",
            "revision_id": "qbr_1",
            "prompt": "旧题",
            "options": [],
            "answer_spec": {"type": "exact", "correct_answer": "12"},
            # 注意：没有 question_spec_v2，走的是旧题路径
            "lifecycle_status": "approved",
            "quality_report": {"passed": True},
        }],
        "solution_envelopes": {},
    }
    with pytest.raises(ValueError, match="must not change answers"):
        revise_question_bank_item(
            legacy_bundle,
            "qbr_1",
            patch={"answer_spec": {"correct_answer": "SECRET"}},
            editor_id="teacher-1",
        )


# --- G1：可观察动作进入质量门 -----------------------------------------------


def _contract(**overrides):
    contract = {
        "prompt": "题干",
        "question_spec": {"input_contract": {"mode": "short_text"}},
        "solution_envelope": {},
        "assessment_intent": {},
    }
    contract.update(overrides)
    return contract


def test_observable_action_from_assessment_intent() -> None:
    from assessment_quality import _has_observable_action

    assert _has_observable_action(_contract(
        assessment_intent={"observable_actions": ["写出 ΔU=Q-W 并代入数值"]},
    )) is True


def test_observable_action_from_bound_skill_behaviour() -> None:
    from assessment_quality import _has_observable_action

    assert _has_observable_action(_contract(
        assessment_intent={
            "target_skills": [
                {"id": "cks_1", "observable_behavior": "能列式并核对单位"},
            ],
        },
    )) is True


def test_observable_action_from_rubric_or_result_checks() -> None:
    from assessment_quality import _has_observable_action

    assert _has_observable_action(_contract(
        solution_envelope={"rubric": ["列出已知量", "代入公式"]},
    )) is True
    assert _has_observable_action(_contract(
        solution_envelope={"result_checks": ["回代满足 ΔU+W=Q"]},
    )) is True


def test_question_without_any_observable_action_fails_the_gate() -> None:
    """题干说"请分析"不等于说清了要观察什么行为。"""
    from assessment_quality import _has_observable_action

    assert _has_observable_action(_contract(
        prompt="请分析下面的现象并谈谈你的理解。",
    )) is False


def test_empty_strings_do_not_count_as_observable_actions() -> None:
    from assessment_quality import _has_observable_action

    assert _has_observable_action(_contract(
        assessment_intent={"observable_actions": ["", "   "]},
        solution_envelope={"rubric": [""]},
    )) is False


def test_quality_gate_reports_the_missing_observable_action_code() -> None:
    """G1 要求这条进质量门，不能只是有个 helper。"""
    from pathlib import Path

    import assessment_quality

    source = Path(assessment_quality.__file__).read_text(encoding="utf-8")
    # 硬门里要有这一项，且它要有对应的 issue code——只加一个 helper 不算做完
    assert '"observable_action": _has_observable_action(contract)' in source
    assert "OBSERVABLE_ACTION_MISSING" in source
