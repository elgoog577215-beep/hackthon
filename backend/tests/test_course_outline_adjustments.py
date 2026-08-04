from __future__ import annotations

from copy import deepcopy

import pytest

from course_outline_adjustments import (
    OutlineAdjustmentError,
    apply_outline_operations,
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
    assert moved["node_name"] == "脚本生命周期与执行时机"
    assert moved["parent_node_id"] == "L1-2"
    assert moved["prerequisite_node_ids"] == ["L2-1-1"]
    assert added["prerequisite_node_ids"] == ["L2-2-1"]

    chapters = adjusted["course_plan"]["chapters"]
    assert [chapter["title"] for chapter in chapters] == ["基础", "工程实践"]
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
