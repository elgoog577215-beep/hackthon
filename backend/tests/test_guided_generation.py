from guided_generation import (
    artifact_revision,
    build_source_chain_report,
    confirm_waiting_step,
    create_guided_workflow,
    invalidate_after,
    mark_waiting,
    step_state,
)
import pytest


def _course():
    return {
        "course_id": "course-1",
        "course_name": "线性代数",
        "course_outline_revision_id": "bp-confirmed",
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


def test_six_steps_form_one_confirmed_source_chain():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)

    for step in ("outline", "knowledge", "teaching", "content"):
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
    for step in ("outline", "knowledge", "teaching", "content"):
        revision = artifact_revision(step, course, request=request)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)

    course["nodes"][0]["node_content"] = "未经确认的新正文"
    report = build_source_chain_report(workflow, course, request=request)
    invalidated = invalidate_after(workflow, "outline")

    assert report["can_publish"] is False
    assert any(item["code"] == "content_revision_mismatch" for item in report["issues"])
    assert invalidated == ["knowledge", "teaching", "content", "release"]
    assert step_state(workflow, "knowledge")["status"] == "needs_regeneration"


def test_outline_drift_is_detected_even_when_persisted_revision_id_is_stale():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)
    for step in ("outline", "knowledge", "teaching", "content"):
        revision = artifact_revision(step, course, request=request)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)

    course["nodes"][0]["learning_objective"] = "未经确认的新目标"
    report = build_source_chain_report(workflow, course, request=request)

    assert report["can_publish"] is False
    assert any(item["code"] == "outline_revision_mismatch" for item in report["issues"])


def test_step_cannot_confirm_after_its_upstream_revision_changes():
    request = {"subject": "线性代数", "difficulty": "intermediate"}
    course = _course()
    workflow = create_guided_workflow(request)
    outline_revision = artifact_revision("outline", course, request=request)
    mark_waiting(workflow, "outline", revision=outline_revision)
    confirm_waiting_step(workflow, "outline", revision=outline_revision)

    knowledge_revision = artifact_revision("knowledge", course, request=request)
    mark_waiting(workflow, "knowledge", revision=knowledge_revision)
    step_state(workflow, "outline")["artifact_revision"] = "outline_changed"

    with pytest.raises(ValueError, match="stale upstream"):
        confirm_waiting_step(
            workflow,
            "knowledge",
            revision=knowledge_revision,
        )
