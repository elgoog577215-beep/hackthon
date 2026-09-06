from copy import deepcopy
from types import SimpleNamespace

import pytest

from course_generation.outline import review_course_outline_document
from course_production_state import read_course_production_state
from teacher_outline_source import read_teacher_outline_source


def source(count=3):
    return {
        "course_id": "course-1",
        "authoring_surface": "teacher",
        "outline_generation_status": "completed",
        "generation_status": "teacher_outline_ready",
        "course_knowledge_scope_contract": {"revision_id": "outline-current"},
        "course_plan": {"chapters": [
            {"node_id": f"lesson-{i}", "sections": [{"node_id": f"section-{i}"}]}
            for i in range(count)
        ]},
        "nodes": [
            node
            for i in range(count)
            for node in (
                {"node_id": f"lesson-{i}", "node_level": 1, "parent_node_id": "root"},
                {"node_id": f"section-{i}", "node_level": 2, "parent_node_id": f"lesson-{i}"},
            )
        ],
    }


def reader(workspace, lessons=None, status="completed"):
    tm = SimpleNamespace(
        get_generation_workspace_course_for_task=lambda _id, **kw: deepcopy(workspace),
        get_tasks_by_course=lambda _id: [
            {"id": "outline-task", "course_id": "course-1", "type": "teacher_outline_generation", "status": status}
        ],
        get_blueprint_draft=lambda _id: None,
    )
    repository = SimpleNamespace(view=lambda _id: {"lessons": deepcopy(lessons or {})})
    return tm, repository


def test_completed_workspace_and_empty_course_shell_share_status_and_generation_source():
    shell = {"course_id": "course-1", "authoring_surface": "teacher", "course_profile": {"planned_lecture_count": 16}}
    workspace = source(16)
    before = deepcopy((shell, workspace))
    tm, repo = reader(workspace)
    for _ in range(2):  # Refresh is a pure read, with the same revision and actions.
        content = read_teacher_outline_source(shell, tm)
        state = read_course_production_state(shell, repo, tm)
        assert content["nodes"] == workspace["nodes"]
        assert content["course_knowledge_scope_contract"]["revision_id"] == "outline-current"
        assert state["stages"]["outline"]["availability"] == "usable"
        assert state["stages"]["outline"]["display_state"] == "available"
        assert state["stages"]["lesson_plan"]["allowed_actions"] == ["generate"]
        assert state["stages"]["lesson_plan"]["counts"]["total"] == 16
        assert state["stages"]["script"]["allowed_actions"] == []
    assert (shell, workspace) == before


@pytest.mark.parametrize(
    "patch",
    [{"outline_framework_only": True}, {"generation_status": "outline_detail_generation"}, {"course_id": "other"}],
)
def test_incomplete_or_foreign_workspace_never_grants_generation(patch):
    workspace = {**source(), **patch}
    tm, repo = reader(workspace)
    state = read_course_production_state({"course_id": "course-1"}, repo, tm)
    assert state["stages"]["outline"]["availability"] == "missing"
    assert state["stages"]["lesson_plan"]["allowed_actions"] == []


def test_last_usable_outline_survives_a_failed_attempt():
    tm, repo = reader(source(), status="failed")
    state = read_course_production_state({"course_id": "course-1"}, repo, tm)
    assert state["stages"]["outline"]["display_state"] == "available"
    assert state["stages"]["outline"]["latest_attempt_failed"] is True
    assert state["stages"]["lesson_plan"]["allowed_actions"] == ["generate"]


@pytest.mark.parametrize("status", ["waiting_for_input", "running", "paused", "failed", "cancelled"])
def test_incomplete_course_shell_with_nodes_and_old_assets_never_unlocks_downstream(status):
    shell = {**source(), "outline_framework_only": True}
    old_assets = {"lesson-0": {"working_revision_id": "old-plan", "revisions": []}}
    tm, repo = reader(shell, old_assets, status=status)
    before = deepcopy(shell)
    state = read_course_production_state(shell, repo, tm)
    assert state["stages"]["outline"]["availability"] == "missing"
    assert state["stages"]["outline"]["display_state"] != "available"
    for stage in ("lesson_plan", "script", "ppt"):
        assert not set(state["stages"][stage]["allowed_actions"]) & {
            "generate", "retry_generation", "resume_generation", "regenerate_from_latest_source",
        }
        assert all("generate" not in lesson["stages"][stage]["allowed_actions"] for lesson in state["lessons"])
    assert shell == before
    # The same directory becomes actionable once its complete source is saved.
    tm, repo = reader(source(), old_assets)
    ready = read_course_production_state(source(), repo, tm)
    assert ready["stages"]["outline"]["availability"] == "usable"
    assert "generate" in ready["stages"]["lesson_plan"]["allowed_actions"]


def test_partial_plan_cannot_use_a_complete_navigation_directory():
    shell = source()
    shell["course_plan"]["chapters"].pop()
    tm, repo = reader(shell)
    state = read_course_production_state(shell, repo, tm)
    assert state["stages"]["outline"]["availability"] == "missing"
    assert "generate" not in state["stages"]["lesson_plan"]["allowed_actions"]


def test_orphan_assets_do_not_prove_that_an_outline_exists():
    tm, repo = reader(None, {"lesson-0": {"working_revision_id": "old-plan"}})
    state = read_course_production_state({"course_id": "course-1"}, repo, tm)
    assert state["stages"]["outline"]["availability"] == "missing"
    assert "generate" not in state["stages"]["lesson_plan"]["allowed_actions"]


@pytest.mark.parametrize("status", ["running", "paused", "failed"])
def test_incomplete_outline_blocks_old_batch_recovery_but_keeps_stop_controls(status):
    shell = {**source(), "outline_framework_only": True}
    tm, _ = reader(shell, status="running")
    job = {
        "id": "old-job", "course_id": "course-1", "lesson_unit_id": "lesson-0",
        "type": "teacher_lesson_plan_generation", "parent_job_id": "old-batch",
        "status": status, "error": {"retryable": True},
    }
    repo = SimpleNamespace(view=lambda _id: {"lessons": {}, "jobs": {"old-job": job}})
    state = read_course_production_state(shell, repo, tm)
    for asset in (state["stages"]["lesson_plan"], state["lessons"][0]["stages"]["lesson_plan"]):
        assert not {"generate", "retry_generation", "resume_generation"} & set(asset["allowed_actions"])
        assert not {"retry_generation", "resume_generation"} & set(asset["action_targets"])
        if status in {"running", "paused"}:
            assert "cancel_generation" in asset["allowed_actions"]
            assert asset["action_targets"]["cancel_generation"] == ["old-job"]


def test_outline_source_read_failure_preserves_content_and_disables_new_generation():
    workspace = source()
    tm, repo = reader(workspace)

    def unavailable(*args, **kwargs):
        raise OSError("workspace unavailable")

    tm.get_generation_workspace_course_for_task = unavailable
    state = read_course_production_state(workspace, repo, tm)
    assert any(issue["code"] == "outline_source_read_failed" for issue in state["issues"])
    assert "generate" not in state["stages"]["lesson_plan"]["allowed_actions"]
    assert workspace == source()


@pytest.mark.parametrize(
    "stale,section_id,allowed",
    [(False, "section-0", True), (True, "section-0", False), (False, "wrong-section", False)],
)
def test_script_generation_uses_current_plan_and_exact_outline_scope(stale, section_id, allowed):
    plan = {
        "working_revision_id": "plan-1",
        "source_state": "stale" if stale else "current",
        "revisions": [
            {
                "revision_id": "plan-1",
                "plan": {
                    "schema_version": "course_teaching_plan_v3",
                    "sections": [
                        {"node_id": section_id, "teaching_modules": [{"module_id": "block-1"}]},
                    ],
                },
            }
        ],
    }
    tm, repo = reader(source(), {"lesson-0": plan})
    state = read_course_production_state({"course_id": "course-1"}, repo, tm)
    assert ("generate" in state["stages"]["script"]["allowed_actions"]) is allowed
    assert ("generate" in state["lessons"][0]["stages"]["script"]["allowed_actions"]) is allowed
    assert all("generate" not in lesson["stages"]["script"]["allowed_actions"] for lesson in state["lessons"][1:])


def review_plan():
    return {
        "authoring_structure_version": "lecture_v1",
        "formal_syllabus_contract_version": "formal_syllabus_v2",
        "chapters": [
            {
                "sections": [
                    {
                        "node_id": f"section-{i}",
                        "title": f"主题{i}",
                        "learning_objective": f"比较主题{i}的两种解法并说明理由",
                        "extension_resources": [],
                        "hour_breakdown": {"classroom_lecture": 0},
                    }
                ]
            }
            for i in range(3)
        ],
    }


def test_review_explains_template_evidence_resource_action_and_hour_causality():
    plan = review_plan()
    plan["chapters"][0]["sections"][0]["extension_resources"] = [
        {"resource_type": "book", "title": "参考书", "source_ref": "参考书", "verification_status": "pending"}
    ]
    report = review_course_outline_document(plan, course_context={"teacher_course_brief": {"total_class_hours": 3}})
    issues = {i["code"].split(":")[-1]: i for i in report["issues"]}
    repeated = issues["repeated_objective_template"]
    assert "可能" in repeated["message"]
    assert len(repeated["evidence"]["examples"]) == 3
    assert issues["missing_extension_resources"]["repair_mode"] == "manual"
    missing = issues["unverified_extension_resources"]["evidence"]["resources"][0]["missing_fields"]
    assert set(missing) == {"verification_record", "reference_match", "edition", "locator"}
    assert issues["missing_hour_breakdown"]["evidence"] == {"actual_hours": 0, "expected_hours": 3}
    assert "hour_total_mismatch" not in issues
    assert report["non_blocking"] and report["passed"]
    assert not any(issue["blocking"] for issue in report["issues"])
    plan["reference_books"] = ["参考书"]
    report = review_course_outline_document(plan)
    assert next(i for i in report["issues"] if i["code"].endswith("missing_extension_resources"))["repair_mode"] == "ai"


def test_old_review_is_recomputed_without_mutating_saved_outline():
    workspace = {**source(), "course_plan": review_plan(), "course_outline_quality_report": {"rule_version": "old"}}
    before = deepcopy(workspace)
    tm, _ = reader(workspace)
    current = read_teacher_outline_source({"course_id": "course-1"}, tm)
    assert current["course_outline_quality_report"]["rule_version"] == "course_outline_editorial_v8"
    assert workspace == before
