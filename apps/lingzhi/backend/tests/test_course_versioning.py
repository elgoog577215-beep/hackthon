from __future__ import annotations

from copy import deepcopy

import pytest

from course_versioning import (
    analyze_blueprint_impact,
    build_blueprint_draft,
    outline_adjustment_proposal_id,
)
from course_versions import CourseVersionConflict, CourseVersionRepository


def _course() -> dict:
    return {
        "course_id": "course-1",
        "course_name": "微积分",
        "course_purpose": "systematic",
        "course_blueprint": {"course_title": "微积分", "positioning": "系统学习"},
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_name": "第一章",
                "node_level": 1,
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_name": "极限",
                "node_level": 2,
                "learning_objective": "解释极限",
                "prerequisite_node_ids": [],
                "difficulty_contract": {"target_level": "beginner"},
                "grounding_contract": {"required_evidence_ids": ["ev-1"]},
                "node_content": "旧极限正文",
            },
            {
                "node_id": "L2-1-2",
                "parent_node_id": "L1-1",
                "node_name": "导数",
                "node_level": 2,
                "learning_objective": "计算导数",
                "prerequisite_node_ids": ["L2-1-1"],
                "difficulty_contract": {"target_level": "beginner"},
                "grounding_contract": {"required_evidence_ids": ["ev-2"]},
                "node_content": "旧导数正文",
            },
        ],
        "learning_assets": {
            "questions": [
                {"asset_id": "q-1", "revision_id": "qr-1", "node_id": "L2-1-1"},
            ]
        },
    }


def test_impact_analysis_propagates_semantic_dependency():
    course = _course()
    draft = build_blueprint_draft(course)
    target = next(node for node in draft["nodes"] if node["node_id"] == "L2-1-1")
    target["learning_objective"] = "解释并比较极限"

    report = analyze_blueprint_impact(course, draft)

    assert report["can_confirm"] is True
    assert report["affected_node_ids"] == ["L2-1-1", "L2-1-2"]
    assert "mastery_criteria" in report["asset_impacts"]["L2-1-1"]
    assert "upstream_dependency" in report["node_changes"]["L2-1-2"]


def test_difficulty_change_does_not_invalidate_knowledge_truth():
    course = _course()
    draft = build_blueprint_draft(course)
    target = next(node for node in draft["nodes"] if node["node_id"] == "L2-1-2")
    target["difficulty_contract"] = {"target_level": "advanced"}

    report = analyze_blueprint_impact(course, draft)

    assert report["affected_node_ids"] == ["L2-1-2"]
    assert report["asset_impacts"]["L2-1-2"] == ["checklist", "mastery_criteria", "questions"]


def test_rich_outline_formatting_is_preserved_as_display_only():
    course = _course()
    draft = build_blueprint_draft(course)
    target = next(node for node in draft["nodes"] if node["node_id"] == "L2-1-1")
    target["outline_editor_html"] = {
        "title_html": "<strong>极限</strong>",
        "body_html": "<p>解释<em>极限</em></p>",
    }

    report = analyze_blueprint_impact(course, draft)
    rebuilt = build_blueprint_draft({**course, "nodes": draft["nodes"]})
    rebuilt_target = next(node for node in rebuilt["nodes"] if node["node_id"] == "L2-1-1")

    assert report["display_only_node_ids"] == ["L2-1-1"]
    assert report["affected_node_ids"] == []
    assert rebuilt_target["outline_editor_html"] == target["outline_editor_html"]


def test_lock_conflict_blocks_confirmation():
    course = _course()
    course["blueprint_locks"] = {"L2-1-1": {"planning": True}}
    draft = build_blueprint_draft(course)
    target = next(node for node in draft["nodes"] if node["node_id"] == "L2-1-1")
    target["learning_objective"] = "修改锁定目标"

    report = analyze_blueprint_impact(course, draft)

    assert report["can_confirm"] is False
    assert report["lock_conflicts"][0]["status"] == "locked_conflict"


def test_outline_proposal_id_survives_javascript_number_round_trip():
    preview_operations = [{
        "op": "update_node",
        "node_ref": "L1-1",
        "hour_breakdown": {
            "classroom_lecture": 1.0,
            "classroom_practice": 1.5,
            "online_instruction": 0.0,
        },
    }]
    browser_operations = [{
        "op": "update_node",
        "node_ref": "L1-1",
        "hour_breakdown": {
            "classroom_lecture": 1,
            "classroom_practice": 1.5,
            "online_instruction": 0,
        },
    }]

    assert outline_adjustment_proposal_id("draft-1", preview_operations) == (
        outline_adjustment_proposal_id("draft-1", browser_operations)
    )


def test_repository_versions_compare_and_restore(tmp_path):
    repository = CourseVersionRepository(tmp_path)
    course = _course()
    first = repository.ensure_initial_version("course-1", course)
    assert first["version_id"] == "cv1"

    updated = deepcopy(course)
    updated["nodes"][1]["node_content"] = "新极限正文"
    second = repository.create_version(
        "course-1",
        updated,
        reason="更新极限",
        operation="regenerate",
        base_version_id="cv1",
        changed_node_ids=["L2-1-1"],
    )
    assert second["version_id"] == "cv2"

    diff = repository.compare_versions("course-1", "cv1", "cv2")
    assert diff["summary"]["modified_nodes"] == 1
    assert diff["modified_nodes"][0]["content_changed"] is True

    restored, entry = repository.restore_version("course-1", "cv1")
    assert entry["version_id"] == "cv3"
    assert restored["nodes"][1]["node_content"] == "旧极限正文"
    assert repository.current_version_id("course-1") == "cv3"


def test_outline_draft_history_preserves_saved_versions_and_restores_as_new_event(tmp_path):
    repository = CourseVersionRepository(tmp_path)
    first = build_blueprint_draft(_course())
    repository.save_draft("course-1", first, actor="teacher-1")

    second = deepcopy(first)
    second["nodes"][1]["node_name"] = "极限与连续"
    from course_versioning import blueprint_draft_revision_id
    second["draft_revision_id"] = blueprint_draft_revision_id(second)
    repository.save_draft("course-1", second, actor="teacher-1")

    history = repository.list_draft_versions("course-1")
    assert len(history) == 2
    first_entry = next(
        item for item in history if item["draft_revision_id"] == first["draft_revision_id"]
    )
    restored = repository.restore_draft_version(
        "course-1",
        first_entry["history_entry_id"],
        expected_draft_revision_id=second["draft_revision_id"],
        expected_base_blueprint_revision_id=first["base_blueprint_revision_id"],
        actor="teacher-1",
    )

    assert restored["nodes"][1]["node_name"] == "极限"
    restored_history = repository.list_draft_versions("course-1")
    assert len(restored_history) == 3
    assert restored_history[0]["operation"] == "restore"
    assert restored_history[0]["restored_from_history_entry_id"] == first_entry["history_entry_id"]


def test_candidate_base_version_conflict_preserves_candidate(tmp_path):
    repository = CourseVersionRepository(tmp_path)
    course = _course()
    repository.ensure_initial_version("course-1", course)
    candidate = repository.create_candidate(
        "course-1",
        deepcopy(course),
        base_version_id="cv1",
        impact_report={"affected_node_ids": ["L2-1-1"]},
    )
    repository.create_version(
        "course-1",
        deepcopy(course),
        reason="并发版本",
        operation="regenerate",
        base_version_id="cv1",
    )

    with pytest.raises(CourseVersionConflict):
        repository.promote_candidate("course-1", candidate["candidate_id"], reason="冲突候选")

    saved = repository.load_candidate("course-1", candidate["candidate_id"])
    assert saved["status"] == "base_version_conflict"
