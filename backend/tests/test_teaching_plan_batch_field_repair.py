"""Deterministic shape repair for teaching-plan batch knowledge details.

The repair layer exists to remove a class of AI correction round-trips caused
by shape drift alone. These tests pin the boundary it must not cross: shape is
repaired, missing content is never invented.
"""

from __future__ import annotations

from course_teaching_plan_v3 import normalize_teaching_plan_batch_v3


def _detail(**overrides) -> dict:
    detail = {
        "knowledge_key": "matrix.multiply",
        "knowledge_type": "procedure",
    }
    detail.update(overrides)
    return detail


def _normalize(detail: dict) -> dict:
    batch = normalize_teaching_plan_batch_v3(
        {"sections": [{"node_id": "L2-1-1", "knowledge_details": [detail]}]},
        batch_id="TP-B01",
        skeleton_revision_id="skeleton_test",
    )
    return batch["sections"][0]["knowledge_details"][0]


def test_bare_strings_become_canonical_objects():
    normalized = _normalize(_detail(
        capability_points=["能按定义计算两个矩阵的乘积"],
        mastery_criteria=["能独立算对三阶矩阵乘法"],
        misconceptions=["把矩阵乘法当成逐元素相乘"],
    ))

    assert normalized["capability_points"] == [
        {"observable_behavior": "能按定义计算两个矩阵的乘积"},
    ]
    assert normalized["mastery_criteria"] == [
        {"observable_performance": "能独立算对三阶矩阵乘法"},
    ]
    assert normalized["misconceptions"] == [
        {"observable_error_pattern": "把矩阵乘法当成逐元素相乘"},
    ]


def test_synonym_keys_map_to_canonical_fields():
    normalized = _normalize(_detail(
        capability_points=[{"behavior": "能判断两个矩阵是否可乘"}],
        mastery_criteria=[{"criterion": "给出维度即可判断", "evidence": "课堂小测三题全对"}],
        misconceptions=[{
            "error": "忽略维度匹配就直接相乘",
            "why": "把矩阵当成数字处理",
            "fix": "先写出维度再动笔",
        }],
    ))

    assert normalized["capability_points"][0]["observable_behavior"] == (
        "能判断两个矩阵是否可乘"
    )
    criterion = normalized["mastery_criteria"][0]
    assert criterion["observable_performance"] == "给出维度即可判断"
    assert criterion["verification_method"] == "课堂小测三题全对"
    misconception = normalized["misconceptions"][0]
    assert misconception["observable_error_pattern"] == "忽略维度匹配就直接相乘"
    assert misconception["discrimination"] == "把矩阵当成数字处理"
    assert misconception["repair_strategy"] == "先写出维度再动笔"


def test_canonical_field_wins_over_synonym():
    normalized = _normalize(_detail(
        misconceptions=[{
            "observable_error_pattern": "权威表述",
            "error": "同义键表述",
            "discrimination": "d",
            "repair_strategy": "r",
        }],
    ))

    assert normalized["misconceptions"][0]["observable_error_pattern"] == "权威表述"


def test_list_valued_field_is_joined_not_dropped():
    normalized = _normalize(_detail(
        misconceptions=[{
            "error_pattern": "维度写反",
            "discrimination": "d",
            "remediation": ["先标注维度", "再逐行核对"],
        }],
    ))

    assert normalized["misconceptions"][0]["repair_strategy"] == "先标注维度；再逐行核对"


def test_single_object_is_accepted_where_a_list_is_expected():
    normalized = _normalize(_detail(
        capability_points={"observable_behavior": "能计算乘积"},
    ))

    assert normalized["capability_points"] == [
        {"observable_behavior": "能计算乘积"},
    ]


def test_missing_content_is_never_invented():
    """A genuinely absent repair strategy must stay absent.

    Filling it deterministically would pass the quality gate with a mastery
    standard no teacher authored, which is worse than failing the batch.
    """
    normalized = _normalize(_detail(
        misconceptions=[{"error": "把矩阵乘法当成逐元素相乘"}],
        mastery_criteria=[{"criterion": "能算对"}],
    ))

    misconception = normalized["misconceptions"][0]
    assert misconception["observable_error_pattern"] == "把矩阵乘法当成逐元素相乘"
    assert not str(misconception.get("discrimination") or "").strip()
    assert not str(misconception.get("repair_strategy") or "").strip()
    assert not str(
        normalized["mastery_criteria"][0].get("verification_method") or ""
    ).strip()


def test_empty_and_malformed_entries_are_dropped():
    normalized = _normalize(_detail(
        capability_points=["", "   ", None, 42, {"unrelated_key": "x"}],
    ))

    assert normalized["capability_points"] == [{"unrelated_key": "x"}]


def test_repair_is_deterministic_across_runs():
    detail = _detail(
        capability_points=["能计算乘积"],
        mastery_criteria=[{"criterion": "能算对", "method": "小测"}],
        misconceptions=[{"error": "e", "why": "w", "fix": "f"}],
    )

    first = normalize_teaching_plan_batch_v3(
        {"sections": [{"node_id": "L2-1-1", "knowledge_details": [detail]}]},
        batch_id="TP-B01",
        skeleton_revision_id="skeleton_test",
    )
    second = normalize_teaching_plan_batch_v3(
        {"sections": [{"node_id": "L2-1-1", "knowledge_details": [detail]}]},
        batch_id="TP-B01",
        skeleton_revision_id="skeleton_test",
    )

    assert first["revision_id"] == second["revision_id"]
    assert first == second
