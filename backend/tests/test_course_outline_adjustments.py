from __future__ import annotations

from copy import deepcopy

import pytest

from course_outline_adjustments import (
    OutlineAdjustmentError,
    apply_outline_operations,
    describe_outline_diff,
)
from course_versioning import blueprint_draft_revision_id, build_blueprint_draft


def _draft() -> dict:
    return {
        "schema_version": "blueprint_revision_v1",
        "course_id": "course-outline-1",
        "course_name": "Unity 游戏编程",
        "course_type": "systematic",
        "course_purpose": "systematic",
        "difficulty_profile": {"target_level": "beginner"},
        "course_generation_brief": {
            "course_type": "systematic",
            "course_shape_constraints": {
                "chapter_count": 8,
                "section_count": 24,
                "chapter_count_source": "user_explicit",
                "section_count_source": "user_explicit",
            },
            "material_scope": {"mode": "strict", "evidence_ids": ["ev-1"]},
        },
        "blueprint_locks": {},
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "基础",
                "learning_objective": "建立基础认知",
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_level": 2,
                "node_name": "场景与对象",
                "learning_objective": "组织场景对象",
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "L2-1-2",
                "parent_node_id": "L1-1",
                "node_level": 2,
                "node_name": "生命周期",
                "learning_objective": "选择生命周期入口",
                "prerequisite_node_ids": ["L2-1-1"],
            },
            {
                "node_id": "L1-2",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "工程实践",
                "learning_objective": "完成工程实践",
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "L2-2-1",
                "parent_node_id": "L1-2",
                "node_level": 2,
                "node_name": "组件组合",
                "learning_objective": "组合组件",
                "prerequisite_node_ids": ["L2-1-2"],
            },
        ],
    }


def test_atomic_operations_recompile_every_outline_projection_and_remap_ids():
    draft = _draft()
    original_contract = deepcopy(draft["course_generation_brief"])

    result = apply_outline_operations(
        draft,
        [
            {
                "op": "remove_node",
                "node_ref": "L2-2-1",
            },
            {
                "op": "move_node",
                "node_ref": "L2-1-2",
                "parent_ref": "L1-2",
                "after_ref": None,
            },
            {
                "op": "update_node",
                "node_ref": "L2-1-2",
                "node_name": "脚本生命周期与执行时机",
                "learning_objective": "正确选择 Awake、Start 与 Update",
            },
            {
                "op": "add_node",
                "temp_ref": "tmp-component-composition",
                "node_level": 2,
                "parent_ref": "L1-2",
                "after_ref": "L2-1-2",
                "node_name": "组件组合实战",
                "learning_objective": "用组件组合实现角色能力",
                "prerequisite_refs": ["L2-1-2"],
            },
        ],
    )

    adjusted = result["draft"]
    assert [node["node_id"] for node in adjusted["nodes"]] == [
        "L1-1",
        "L2-1-1",
        "L1-2",
        "L2-2-1",
        "L2-2-2",
    ]
    moved, added = adjusted["nodes"][3:]
    assert moved["node_name"] == "2.1 脚本生命周期与执行时机"
    assert moved["parent_node_id"] == "L1-2"
    assert moved["prerequisite_node_ids"] == ["L2-1-1"]
    assert added["prerequisite_node_ids"] == ["L2-2-1"]

    chapters = adjusted["course_plan"]["chapters"]
    assert [chapter["title"] for chapter in chapters] == ["第1章 基础", "第2章 工程实践"]
    assert [section["node_id"] for section in chapters[1]["sections"]] == [
        "L2-2-1",
        "L2-2-2",
    ]
    assert adjusted["course_outline"] == adjusted["course_plan"]
    assert adjusted["course_blueprint"]["sections"] == chapters
    assert adjusted["course_blueprint"]["nodes"] == adjusted["nodes"]

    constraints = adjusted["course_generation_brief"]["course_shape_constraints"]
    assert constraints == {
        "chapter_count": 2,
        "section_count": 3,
        "chapter_count_source": "outline_adjustment",
        "section_count_source": "outline_adjustment",
    }
    assert adjusted["course_shape_constraints"] == constraints
    assert adjusted["course_generation_brief"]["course_type"] == original_contract["course_type"]
    assert adjusted["course_generation_brief"]["material_scope"] == original_contract["material_scope"]
    assert adjusted["difficulty_profile"] == draft["difficulty_profile"]
    assert result["id_map"]["L2-1-2"] == "L2-2-1"
    assert result["id_map"]["tmp-component-composition"] == "L2-2-2"


def test_targeted_editorial_operation_can_update_scope_and_assessment():
    result = apply_outline_operations(
        _draft(),
        [{
            "op": "update_node",
            "node_ref": "L2-1-2",
            "scope_boundary": "只比较 Awake、Start 与 Update 的触发时机，不展开协程调度",
            "assessment": [
                "为三个给定初始化场景选择回调入口，并逐项说明选择依据",
            ],
        }],
    )

    node = next(
        item for item in result["draft"]["nodes"]
        if item["node_id"] == "L2-1-2"
    )
    assert node["scope_boundary"].startswith("只比较")
    assert node["assessment"] == [
        "为三个给定初始化场景选择回调入口，并逐项说明选择依据",
    ]
    updated = result["draft"]["course_plan"]["chapters"][0]["sections"][1]
    assert updated["assessment"] == node["assessment"]


def test_formal_outline_adjustment_updates_course_and_lecture_contract_fields():
    draft = _draft()
    draft["authoring_structure_version"] = "lecture_v1"
    draft["course_generation_brief"]["course_shape_constraints"] = {
        "teacher_lecture_mode": True,
        "chapter_count": 2,
        "section_count": 2,
    }
    draft["nodes"] = [
        draft["nodes"][0],
        draft["nodes"][1],
        draft["nodes"][3],
        draft["nodes"][4],
    ]
    draft["nodes"][3]["prerequisite_node_ids"] = ["L2-1-1"]
    draft["course_plan"] = {
        "formal_syllabus_contract_version": "formal_syllabus_v2",
        "authoring_structure_version": "lecture_v1",
        "reference_books": ["《Unity 开发实践》，第2版"],
    }

    result = apply_outline_operations(
        draft,
        [
            {
                "op": "update_course_plan",
                "course_intro_zh": "本课程从场景对象出发，完成可验证的交互原型。",
                "course_intro_en": "This course builds a verifiable interactive prototype from scene objects.",
                "learning_objectives": ["掌握场景、对象与组件的组织方法"],
                "education_objectives": ["具备依据测试证据承担工程责任的意识"],
                "measurable_outcomes": ["能完成原型并提交验证记录"],
                "assessment_plan": [
                    {
                        "item": "讲次作品",
                        "category": "formative",
                        "weight_percent": 60,
                        "criteria": "按功能完整性与验证记录评分",
                        "outcome_numbers": [1],
                    },
                    {
                        "item": "综合原型",
                        "category": "summative",
                        "weight_percent": 40,
                        "criteria": "按可用性和可解释性评分",
                        "outcome_numbers": [1],
                    },
                ],
            },
            {
                "op": "update_node",
                "node_ref": "L2-1-1",
                "content_summary": "识别场景、对象与组件之间的关系。",
                "application_anchors": ["角色移动原型"],
                "extension_resources": [
                    {
                        "resource_type": "book",
                        "title": "Unity 开发实践",
                        "edition": "第2版",
                        "locator": "第3章，45–68页",
                        "source_ref": "《Unity 开发实践》，第2版",
                        "verification_status": "verified",
                    }
                ],
                "learning_tasks": [
                    {
                        "mode": "offline",
                        "stage": "after_class",
                        "task": "完成角色移动原型",
                        "evidence": "可运行工程与测试记录",
                        "estimated_hours": 1,
                    }
                ],
                "education_objective_refs": ["育人目标1"],
                "ideology_implementation": "用失败测试记录讨论工程责任。",
                "external_mentor": {
                    "name": "李工",
                    "organization": "某游戏工作室",
                    "role": "原型评审",
                },
                "hour_breakdown": {
                    "classroom_lecture": 1,
                    "classroom_practice": 1,
                    "online_instruction": 0,
                },
            },
        ],
    )

    plan = result["draft"]["course_plan"]
    lecture = plan["chapters"][0]["sections"][0]
    assert plan["course_intro_en"].startswith("This course")
    assert [item["weight_percent"] for item in plan["assessment_plan"]] == [60, 40]
    assert lecture["application_anchors"] == ["角色移动原型"]
    assert lecture["extension_resources"][0]["verification_status"] == "verified"
    assert lecture["external_mentor"]["role"] == "原型评审"
    assert lecture["hour_breakdown"] == {
        "classroom_lecture": 1.0,
        "classroom_practice": 1.0,
        "online_instruction": 0.0,
    }
    assert lecture["planned_hours"] == 2.0
    diff = describe_outline_diff(draft, result["draft"], result["id_map"])
    assert {item["field"] for item in diff["course_updated"]} >= {
        "course_intro_zh",
        "course_intro_en",
        "learning_objectives",
        "education_objectives",
        "measurable_outcomes",
        "assessment_plan",
    }


def test_section_only_adjustment_preserves_chapter_learning_focus() -> None:
    draft = _draft()
    chapter = draft["nodes"][0]
    chapter.pop("learning_objective")
    chapter["learning_focus"] = "建立场景、对象与脚本生命周期之间的完整关系"

    adjusted = apply_outline_operations(
        draft,
        [{
            "op": "update_node",
            "node_ref": "L2-1-2",
            "learning_objective": "根据执行时机选择正确的生命周期入口",
        }],
    )["draft"]

    compiled_chapter = adjusted["course_outline"]["chapters"][0]
    assert compiled_chapter["learning_focus"] == chapter["learning_focus"]
    assert compiled_chapter["learning_objective"] == chapter["learning_focus"]


def test_recompile_replaces_stale_numeric_prefixes_in_every_projection():
    draft = _draft()
    draft["nodes"][0]["node_name"] = "第7章 基础"
    draft["nodes"][1]["node_name"] = "7.4 场景与对象"
    draft["nodes"][2]["node_name"] = "1.2 生命周期"
    draft["nodes"][3]["node_name"] = "第3章 工程实践"
    draft["nodes"][4]["node_name"] = "3.8 组件组合"

    adjusted = apply_outline_operations(
        draft,
        [
            {
                "op": "move_node",
                "node_ref": "L2-1-2",
                "parent_ref": "L1-2",
                "after_ref": None,
            }
        ],
    )["draft"]

    expected_names = [
        "第1章 基础",
        "1.1 场景与对象",
        "第2章 工程实践",
        "2.1 生命周期",
        "2.2 组件组合",
    ]
    assert [node["node_name"] for node in adjusted["nodes"]] == expected_names
    assert [chapter["title"] for chapter in adjusted["course_plan"]["chapters"]] == [
        "第1章 基础",
        "第2章 工程实践",
    ]
    assert [
        section["title"]
        for chapter in adjusted["course_outline"]["chapters"]
        for section in chapter["sections"]
    ] == ["1.1 场景与对象", "2.1 生命周期", "2.2 组件组合"]
    assert adjusted["course_blueprint"]["nodes"] == adjusted["nodes"]


def test_lecture_outline_adjustment_preserves_one_visible_level():
    draft = _draft()
    draft["authoring_structure_version"] = "lecture_v1"
    draft["course_generation_brief"]["course_shape_constraints"] = {
        "teacher_lecture_mode": True,
        "chapter_count": 2,
        "section_count": 2,
    }
    draft["nodes"] = [
        draft["nodes"][0],
        draft["nodes"][1],
        draft["nodes"][3],
        draft["nodes"][4],
    ]
    draft["nodes"][0]["node_name"] = "第1章 基础"
    draft["nodes"][1]["node_name"] = "1.1 场景与对象"
    draft["nodes"][2]["node_name"] = "第2章 工程实践"
    draft["nodes"][3]["node_name"] = "2.1 组件组合"
    draft["nodes"][3]["prerequisite_node_ids"] = ["L2-1-1"]

    adjusted = apply_outline_operations(
        draft,
        [{
            "op": "update_node",
            "node_ref": "L1-1",
            "node_name": "场景、对象与基本机制",
        }],
    )["draft"]

    assert adjusted["authoring_structure_version"] == "lecture_v1"
    assert [node["node_name"] for node in adjusted["nodes"]] == [
        "第1讲 场景、对象与基本机制",
        "场景与对象",
        "第2讲 工程实践",
        "组件组合",
    ]
    assert [chapter["title"] for chapter in adjusted["course_plan"]["chapters"]] == [
        "第1讲 场景、对象与基本机制",
        "第2讲 工程实践",
    ]
    assert [
        section["section_number"]
        for chapter in adjusted["course_plan"]["chapters"]
        for section in chapter["sections"]
    ] == ["1", "2"]
    assert adjusted["course_generation_brief"]["course_shape_constraints"]["teacher_lecture_mode"] is True


def test_lecture_outline_rejects_a_second_internal_unit():
    draft = _draft()
    draft["authoring_structure_version"] = "lecture_v1"
    draft["nodes"] = draft["nodes"][:3]

    with pytest.raises(OutlineAdjustmentError) as error:
        apply_outline_operations(
            draft,
            [{
                "op": "update_node",
                "node_ref": "L2-1-1",
                "learning_objective": "识别场景对象",
            }],
        )

    assert error.value.code == "lecture_has_nested_units"


def test_same_chapter_release_and_delivery_duplicate_is_blocked():
    draft = _draft()
    draft["nodes"].extend(
        [
            {
                "node_id": "L2-2-2",
                "parent_node_id": "L1-2",
                "node_level": 2,
                "node_name": "6.4 完整游戏循环优化与发布流程",
                "learning_objective": (
                    "整合项目各模块，优化用户体验，配置多平台构建设置，"
                    "执行系统化调试并完成最终交付物生成"
                ),
                "prerequisite_node_ids": ["L2-2-1"],
            },
            {
                "node_id": "L2-2-3",
                "parent_node_id": "L1-2",
                "node_level": 2,
                "node_name": "6.2 工程打包、调试验证与交付",
                "learning_objective": (
                    "配置 Unity 构建设置，执行多平台打包，并通过系统化调试流程"
                    "消除致命 Bug，最终生成可独立运行的交付物"
                ),
                "prerequisite_node_ids": ["L2-2-2"],
            },
        ]
    )

    with pytest.raises(OutlineAdjustmentError) as error:
        apply_outline_operations(
            draft,
            [
                {
                    "op": "update_node",
                    "node_ref": "L2-2-1",
                    "learning_objective": "组合组件并衔接完整游戏循环",
                }
            ],
        )

    assert error.value.code == "semantic_duplicate_sections"
    assert error.value.details["node_refs"] == ["L2-2-2", "L2-2-3"]


def test_remove_non_empty_chapter_never_cascades_implicitly():
    with pytest.raises(OutlineAdjustmentError) as error:
        apply_outline_operations(
            _draft(),
            [{"op": "remove_node", "node_ref": "L1-1"}],
        )

    assert error.value.code == "chapter_not_empty"


def test_deleted_dependency_is_a_blocker_instead_of_being_silently_dropped():
    with pytest.raises(OutlineAdjustmentError) as error:
        apply_outline_operations(
            _draft(),
            [{"op": "remove_node", "node_ref": "L2-1-1"}],
        )

    assert error.value.code == "dependency_target_missing"


@pytest.mark.parametrize(
    ("operations", "code"),
    [
        (
            [
                {
                    "op": "update_node",
                    "node_ref": "L2-1-1",
                    "prerequisite_refs": ["L2-1-2"],
                },
                {
                    "op": "update_node",
                    "node_ref": "L2-1-2",
                    "prerequisite_refs": [],
                },
            ],
            "dependency_points_forward",
        ),
        (
            [
                {
                    "op": "update_node",
                    "node_ref": "L2-1-1",
                    "prerequisite_refs": ["L2-1-2"],
                },
                {
                    "op": "update_node",
                    "node_ref": "L2-1-2",
                    "prerequisite_refs": ["L2-1-1"],
                },
            ],
            "dependency_cycle",
        ),
        (
            [
                {
                    "op": "move_node",
                    "node_ref": "L2-1-1",
                    "parent_ref": "L1-2",
                    "after_ref": "L2-2-1",
                },
                {
                    "op": "move_node",
                    "node_ref": "L2-1-2",
                    "parent_ref": "L1-2",
                    "after_ref": "L2-1-1",
                },
            ],
            "chapter_empty",
        ),
    ],
)
def test_invalid_dependency_or_shape_blocks_the_whole_proposal(operations, code):
    with pytest.raises(OutlineAdjustmentError) as error:
        apply_outline_operations(_draft(), operations)

    assert error.value.code == code


def test_draft_revision_is_stable_and_excludes_transient_reports_and_timestamps():
    draft = build_blueprint_draft(_draft())
    revision = blueprint_draft_revision_id(draft)
    changed = deepcopy(draft)
    changed["updated_at"] = "2099-01-01T00:00:00"
    changed["impact_report"] = {"can_confirm": False, "warnings": ["transient"]}

    assert revision.startswith("draft_")
    assert blueprint_draft_revision_id(changed) == revision

    changed["nodes"][1]["node_name"] = "重命名后的场景对象"
    assert blueprint_draft_revision_id(changed) != revision
