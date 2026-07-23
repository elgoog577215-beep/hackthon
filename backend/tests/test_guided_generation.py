import pytest

from guided_generation import (
    artifact_revision,
    build_source_chain_report,
    confirm_waiting_step,
    create_guided_workflow,
    invalidate_after,
    mark_waiting,
    migrate_guided_workflow,
    step_state,
)


def _course():
    return {
        "course_id": "course-1",
        "course_name": "线性代数",
        "course_outline_revision_id": "bp-confirmed",
        "course_teaching_plan": {
            "revision_id": "teaching-confirmed",
        },
        "course_knowledge_base": {
            "revision_id": "kb-confirmed",
            "lifecycle_status": "active",
        },
        "learning_asset_plan": {"enabled": {"questions": True}},
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量空间",
            "learning_objective": "判断子空间",
            "module_plan": {"teaching_method": "定义—反例—判断"},
            "node_content": "向量空间正文",
            "grounding_annotations": [],
        }],
        "course_knowledge_map": {
            "course_knowledge_base_revision_id": "kb-confirmed",
        },
    }


def test_staged_steps_form_one_confirmed_source_chain():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)

    for step in ("outline", "teaching", "content"):
        revision = artifact_revision(step, course, request=request)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)

    report = build_source_chain_report(workflow, course, request=request)

    assert report["can_publish"] is True
    assert all(item["passed"] for item in report["checks"])


def test_content_drift_blocks_release_and_upstream_change_invalidates_downstream():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)
    for step in ("outline", "teaching", "content"):
        revision = artifact_revision(step, course, request=request)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)

    course["nodes"][0]["node_content"] = "未经确认的新正文"
    report = build_source_chain_report(workflow, course, request=request)
    invalidated = invalidate_after(workflow, "outline")

    assert report["can_publish"] is False
    assert any(item["code"] == "content_revision_mismatch" for item in report["issues"])
    assert invalidated == ["teaching", "content", "release"]
    assert step_state(workflow, "content")["status"] == "needs_regeneration"


def test_outline_drift_is_detected_even_when_persisted_revision_id_is_stale():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)
    for step in ("outline", "teaching", "content"):
        revision = artifact_revision(step, course, request=request)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)

    course["nodes"][0]["learning_objective"] = "未经确认的新目标"
    report = build_source_chain_report(workflow, course, request=request)

    assert report["can_publish"] is False
    assert any(item["code"] == "outline_revision_mismatch" for item in report["issues"])


def test_outline_revision_ignores_downstream_enrichment_but_not_outline_edits():
    course = _course()
    course["course_outline"] = {
        "course_title": "线性代数",
        "positioning": "从向量空间进入线性结构",
        "learning_objectives": ["判断一个集合是否构成子空间"],
        "prerequisites": ["集合与运算"],
        "chapters": [{
            "chapter_number": 1,
            "title": "向量空间",
            "learning_focus": "判断封闭性",
            "sections": [{
                "section_number": "1.1",
                "node_id": "n1",
                "title": "向量空间",
                "learning_objective": "判断子空间",
                "scope_boundary": "只讨论线性封闭性",
                "assessment": ["完成一次子空间判断"],
                "prerequisite_node_ids": [],
            }],
        }],
    }
    confirmed_revision = artifact_revision("outline", course)

    course["course_outline"]["knowledge_relations"] = [{
        "source": "向量空间",
        "target": "子空间",
    }]
    section = course["course_outline"]["chapters"][0]["sections"][0]
    section.update({
        "key_points": ["加法封闭", "数乘封闭"],
        "knowledge_structure": [{"concept_group": "封闭性"}],
        "module_plan": [{"module_id": "core_explanation"}],
        "difficulty_contract": {"target_level": "intermediate"},
    })
    course["nodes"][0].update({
        "knowledge_structure": [{"concept_group": "封闭性"}],
        "difficulty_contract": {"target_level": "intermediate"},
    })

    assert artifact_revision("outline", course) == confirmed_revision

    course["nodes"][0]["learning_objective"] = "判断并证明子空间"
    assert artifact_revision("outline", course) != confirmed_revision


def test_step_cannot_confirm_after_its_upstream_revision_changes():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)
    outline_revision = artifact_revision("outline", course, request=request)
    mark_waiting(workflow, "outline", revision=outline_revision)
    confirm_waiting_step(workflow, "outline", revision=outline_revision)

    teaching_revision = artifact_revision("teaching", course, request=request)
    mark_waiting(workflow, "teaching", revision=teaching_revision)
    confirm_waiting_step(workflow, "teaching", revision=teaching_revision)

    content_revision = artifact_revision("content", course, request=request)
    mark_waiting(workflow, "content", revision=content_revision)
    step_state(workflow, "outline")["artifact_revision"] = "outline_changed"

    with pytest.raises(ValueError, match="stale upstream"):
        confirm_waiting_step(
            workflow,
            "content",
            revision=content_revision,
        )


def test_v1_teaching_review_is_preserved_as_explicit_confirmation():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    workflow = {
        "schema_version": "guided_course_generation_v1",
        "current_step": "teaching",
        "review_step": "teaching",
        "steps": [
            {
                "number": 1,
                "key": "requirements",
                "status": "confirmed",
                "artifact_revision": "req-old",
            },
            {
                "number": 2,
                "key": "outline",
                "status": "confirmed",
                "artifact_revision": "outline-old",
            },
            {
                "number": 3,
                "key": "knowledge",
                "status": "confirmed",
                "artifact_revision": "knowledge-old",
            },
            {
                "number": 4,
                "key": "teaching",
                "status": "waiting_for_confirmation",
                "artifact_revision": "teaching-old",
            },
            {"number": 5, "key": "content", "status": "locked"},
            {"number": 6, "key": "release", "status": "locked"},
        ],
    }

    migrated = migrate_guided_workflow(workflow, request=request)

    assert migrated["schema_version"] == "guided_course_generation_v3"
    assert [item["key"] for item in migrated["steps"]] == [
        "requirements",
        "outline",
        "teaching",
        "content",
        "release",
    ]
    assert migrated["review_step"] == "teaching"
    assert migrated["current_step"] == "teaching"
    assert step_state(migrated, "teaching")["status"] == "waiting_for_confirmation"
