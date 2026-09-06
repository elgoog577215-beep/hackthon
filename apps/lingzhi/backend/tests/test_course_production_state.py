from copy import deepcopy
from types import SimpleNamespace

import pytest

from course_production_state import (
    Availability,
    CourseProductionState,
    DisplayState,
    PreparationState,
    ProductionAction,
    ProductionStage,
    SourceRequirement,
    SourceReviewState,
    SourceState,
    TaskState,
    compile_course_production_state,
    read_course_production_state,
)
from routers import courses, teaching_calendar


def _course(count: int) -> dict:
    return {
        "course_id": "course-1",
        "course_profile": {"planned_lecture_count": count},
        "nodes": [
            {
                "node_id": f"lesson-{index}",
                "node_name": f"第 {index} 讲",
                "node_level": 1,
                "parent_node_id": "root",
            }
            for index in range(1, count + 1)
        ],
    }


def _ready_lesson(index: int) -> dict:
    plan_id = f"plan-{index}"
    script_id = f"script-{index}"
    return {
        "working_revision_id": plan_id,
        "source_state": "current",
        "revisions": [{
            "revision_id": plan_id,
            "generation_source": "model",
            "plan": {
                "schema_version": "course_teaching_plan_v3",
                "sections": [{
                    "node_id": f"section-{index}",
                    "teaching_modules": [{"module_id": f"module-{index}"}],
                }],
            },
        }],
        "working_script_revision_id": script_id,
        "script_revisions": [{
            "revision_id": script_id,
            "source_lesson_plan_revision_id": plan_id,
            "sections": [{
                "section_node_id": f"section-{index}",
                "content": f"第 {index} 讲完整讲义",
                "blocks": [{"block_id": f"block-{index}"}],
            }],
        }],
        "ppt_assets": [{
            "working_representation_id": f"ppt-{index}",
            "source_lesson_plan_revision_id": plan_id,
            "source_script_revision_id": script_id,
            "source_state": "current",
        }],
    }


def test_projection_contract_locks_schema_and_enums():
    result = compile_course_production_state(
        _course(1),
        authoring_state={"course_id": "course-1", "lessons": {}},
    )

    assert result["schema_version"] == "course_production_state_v1"
    assert list(result["stages"]) == ["outline", "lesson_plan", "script", "ppt"]
    assert {item.value for item in DisplayState} == {
        "not_generated", "generating", "available", "failed"
    }
    assert {item.value for item in ProductionStage} == {
        "outline", "lesson_plan", "script", "ppt"
    }
    assert {item.value for item in PreparationState} == {"preparing", "prepared"}
    assert {item.value for item in TaskState} == {
        "idle", "queued", "running", "paused", "waiting_for_input",
        "waiting_for_review", "cancelled", "failed", "completed", "unknown",
    }
    assert {item.value for item in ProductionAction} == {
        "generate", "pause_generation", "cancel_generation",
        "resume_generation", "provide_input", "review_generation",
        "retry_generation", "inspect_failure",
        "regenerate_from_latest_source",
    }
    assert {item.value for item in Availability} == {"missing", "usable", "stale"}
    assert {item.value for item in SourceState} == {"missing", "current", "stale", "mixed"}
    assert {item.value for item in SourceRequirement} == {"required", "optional"}
    assert {item.value for item in SourceReviewState} == {
        "verified", "pending_review", "blocked"
    }
    assert result["source_summary"] == {
        "pending_review_count": 0,
        "required_blocked_count": 0,
        "sources": [],
    }
    assert result["stages"]["outline"]["action_targets"] == {}
    assert result["stages"]["outline"]["has_unconfirmed_draft"] is False
    assert CourseProductionState.model_validate(result).course_id == "course-1"


def test_projection_is_pure_and_does_not_mutate_owner_snapshots():
    course = _course(1)
    authoring = {
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {"lesson-1": _ready_lesson(1)},
    }
    tasks = [{
        "id": "task-1",
        "course_id": "course-1",
        "type": "teacher_lesson_plan_generation",
        "lesson_unit_id": "lesson-1",
        "status": "running",
        "progress": 45,
    }]
    before = deepcopy((course, authoring, tasks))

    compile_course_production_state(course, authoring_state=authoring, tasks=tasks)

    assert (course, authoring, tasks) == before


def test_projection_reads_unconfirmed_draft_through_public_task_manager_boundary():
    class AuthoringRepository:
        @staticmethod
        def view(_course_id):
            return {"course_id": "course-1", "lessons": {}}

    class TaskManagerReader:
        @staticmethod
        def get_tasks_by_course(_course_id):
            return [{
                "id": "outline-completed",
                "course_id": "course-1",
                "type": "teacher_outline_generation",
                "status": "completed",
            }]

        @staticmethod
        def get_blueprint_draft(_course_id):
            return {"draft_revision_id": "draft-1"}

    stage = read_course_production_state(
        _course(1),
        AuthoringRepository(),
        TaskManagerReader(),
    )["stages"]["outline"]

    assert stage["has_unconfirmed_draft"] is True
    assert stage["action_targets"] == {
        "regenerate_from_latest_source": ["outline-completed"],
    }


@pytest.mark.parametrize(
    ("task_manager", "expected_code"),
    [
        (None, "task_state_unavailable"),
        (
            SimpleNamespace(
                get_tasks_by_course=lambda _course_id: (_ for _ in ()).throw(
                    RuntimeError("task index unavailable")
                ),
                get_blueprint_draft=lambda _course_id: None,
            ),
            "task_state_read_failed",
        ),
        (
            SimpleNamespace(
                get_tasks_by_course=lambda _course_id: ["invalid task"],
                get_blueprint_draft=lambda _course_id: None,
            ),
            "task_state_read_failed",
        ),
    ],
)
def test_unreadable_task_owner_fails_closed_across_all_production_stages(
    task_manager,
    expected_code,
):
    repository = SimpleNamespace(
        view=lambda _course_id: {
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        }
    )

    result = read_course_production_state(
        _course(1),
        repository,
        task_manager,
    )

    assert result["stages"]["outline"]["display_state"] == "available"
    for stage_name in ("outline", "lesson_plan", "script", "ppt"):
        stage = result["stages"][stage_name]
        assert stage["task_state"] == "unknown"
        assert stage["allowed_actions"] == ["inspect_failure"]
        assert stage["action_targets"] == {}
        assert expected_code in {item["code"] for item in stage["issues"]}


def test_unreadable_authoring_owner_blocks_assets_but_keeps_outline_controls():
    class AuthoringRepository:
        @staticmethod
        def view(_course_id):
            raise RuntimeError("authoring store unavailable")

    task_manager = SimpleNamespace(
        get_tasks_by_course=lambda _course_id: [],
        get_blueprint_draft=lambda _course_id: None,
    )

    result = read_course_production_state(
        _course(1),
        AuthoringRepository(),
        task_manager,
    )

    assert result["stages"]["outline"]["task_state"] == "idle"
    assert result["stages"]["outline"]["allowed_actions"] == []
    for stage_name in ("lesson_plan", "script", "ppt"):
        stage = result["stages"][stage_name]
        assert stage["display_state"] == "failed"
        assert stage["task_state"] == "unknown"
        assert stage["allowed_actions"] == ["inspect_failure"]
        assert stage["action_targets"] == {}
        assert "teacher_asset_state_read_failed" in {
            item["code"] for item in stage["issues"]
        }


def test_unreadable_blueprint_draft_blocks_outline_regeneration_only():
    repository = SimpleNamespace(
        view=lambda _course_id: {
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        }
    )
    task_manager = SimpleNamespace(
        get_tasks_by_course=lambda _course_id: [],
        get_blueprint_draft=lambda _course_id: (_ for _ in ()).throw(
            RuntimeError("version repository unavailable")
        ),
    )

    result = read_course_production_state(
        _course(1),
        repository,
        task_manager,
    )

    outline = result["stages"]["outline"]
    assert outline["display_state"] == "available"
    assert outline["task_state"] == "unknown"
    assert outline["allowed_actions"] == ["inspect_failure"]
    assert outline["action_targets"] == {}
    assert "blueprint_draft_read_failed" in {
        item["code"] for item in outline["issues"]
    }
    for stage_name in ("lesson_plan", "script", "ppt"):
        assert result["stages"][stage_name]["task_state"] == "idle"


def test_ppt_checkpoint_is_read_as_attempt_without_becoming_persisted_state():
    checkpoint = {
        "task_id": "teacher-v6-1",
        "lesson_unit_id": "lesson-1",
        "status": "running",
        "progress": 38,
        "updated_at": "2026-09-04T01:00:00+00:00",
    }
    before = deepcopy(checkpoint)

    result = compile_course_production_state(
        _course(1),
        authoring_state={"course_id": "course-1", "lessons": {}},
        ppt_checkpoints=[checkpoint],
    )

    assert result["lessons"][0]["stages"]["ppt"]["display_state"] == "generating"
    assert result["lessons"][0]["stages"]["ppt"]["allowed_actions"] == [
        "inspect_failure"
    ]
    assert result["lessons"][0]["stages"]["ppt"]["action_targets"] == {}
    assert result["lessons"][0]["stages"]["ppt"]["issues"][0]["code"] == (
        "checkpoint_without_task_owner"
    )
    assert result["stages"]["ppt"]["latest_attempt"]["task_ids"] == ["teacher-v6-1"]
    assert checkpoint == before


def test_latest_retry_attempt_does_not_replace_formal_course_denominator():
    authoring = {
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {
            f"lesson-{index}": _ready_lesson(index)
            for index in range(1, 16)
        },
    }
    tasks = [{
        "id": "retry-lesson-16",
        "parent_job_id": "retry-batch-1",
        "course_id": "course-1",
        "type": "teacher_lesson_plan_generation",
        "lesson_unit_id": "lesson-16",
        "status": "failed",
        "progress": 0,
        "batch_size": 1,
        "error": {"code": "provider_unavailable", "message": "模型暂时不可用", "retryable": True},
        "updated_at": "2026-09-04T01:00:00+00:00",
    }]

    result = compile_course_production_state(
        _course(16),
        authoring_state=authoring,
        tasks=tasks,
    )
    stage = result["stages"]["lesson_plan"]

    assert stage["counts"] == {
        "total": 16,
        "available": 15,
        "generating": 0,
        "failed": 1,
        "stale": 0,
    }
    assert stage["latest_attempt"]["target_count"] == 1
    assert stage["latest_attempt"]["completed"] == 0
    assert stage["latest_attempt"]["failed"] == 1


def test_authoring_jobs_feed_the_projection_without_explicit_task_injection():
    authoring = {
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {
            **{
                f"lesson-{index}": _ready_lesson(index)
                for index in range(1, 16)
            },
            "lesson-16": {
                "working_revision_id": "plan-16",
                "source_state": "current",
                "revisions": _ready_lesson(16)["revisions"],
                "working_script_revision_id": "",
                "script_revisions": [],
            },
        },
        "jobs": {
            "script-retry-16": {
                "id": "script-retry-16",
                "parent_job_id": "script-retry-batch",
                "course_id": "course-1",
                "type": "teacher_lesson_script_generation",
                "lesson_unit_id": "lesson-16",
                "status": "failed",
                "progress": 50,
                "batch_size": 1,
                "checkpoint": {"current_block_id": "block-16-3"},
                "error": {
                    "code": "lesson_script_shard_incomplete",
                    "message": "3 个教学块生成失败，已保留其他成功结果。",
                    "retryable": True,
                },
                "updated_at": "2026-09-05T01:00:00+00:00",
            },
        },
    }

    result = compile_course_production_state(
        _course(16),
        authoring_state=authoring,
    )
    stage = result["stages"]["script"]
    lesson = next(
        item for item in result["lessons"]
        if item["lesson_unit_id"] == "lesson-16"
    )["stages"]["script"]

    assert stage["counts"] == {
        "total": 16,
        "available": 15,
        "generating": 0,
        "failed": 1,
        "stale": 0,
    }
    assert stage["latest_attempt"]["target_count"] == 1
    assert stage["latest_attempt"]["failed"] == 1
    assert lesson["display_state"] == "failed"
    assert lesson["task_state"] == "failed"
    assert lesson["issues"][0]["task_id"] == "script-retry-16"
    assert lesson["issues"][0]["block_id"] == "block-16-3"
    assert lesson["issues"][0]["recovery"]["action"] == "retry_generation"


def test_duplicate_authoring_and_task_manager_snapshots_count_once():
    failed = {
        "id": "script-retry-1",
        "parent_job_id": "script-retry-batch",
        "course_id": "course-1",
        "type": "teacher_lesson_script_generation",
        "lesson_unit_id": "lesson-1",
        "status": "failed",
        "batch_size": 1,
        "error": {"code": "provider_unavailable", "message": "模型暂时不可用"},
        "updated_at": "2026-09-05T01:00:00+00:00",
    }
    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
            "jobs": {failed["id"]: deepcopy(failed)},
        },
        tasks=[deepcopy(failed)],
    )

    assert result["stages"]["script"]["latest_attempt"]["task_ids"] == ["script-retry-1"]
    assert result["stages"]["script"]["latest_attempt"]["failed"] == 1
    assert len(result["stages"]["script"]["issues"]) == 1


def test_non_retryable_failure_never_projects_a_retry_action():
    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {
                "script-failed": {
                    "id": "script-failed",
                    "course_id": "course-1",
                    "type": "teacher_lesson_script_generation",
                    "lesson_unit_id": "lesson-1",
                    "status": "failed",
                    "error": {
                        "code": "lesson_plan_scope_stale",
                        "message": "上游教案已变化。",
                        "retryable": False,
                    },
                },
            },
        },
    )

    issue = result["stages"]["script"]["issues"][0]
    assert issue["recovery"]["action"] == "inspect_failure"


def test_teacher_ppt_v6_authoring_job_is_the_projected_attempt_owner():
    task_id = "tlj-ppt-v6-failed"
    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
            "jobs": {
                task_id: {
                    "schema_version": "teacher_asset_job_v1",
                    "id": task_id,
                    "course_id": "course-1",
                    "lesson_unit_id": "lesson-1",
                    "type": "teacher_lesson_ppt_generation",
                    "asset_type": "ppt",
                    "status": "failed",
                    "request_snapshot": {
                        "lesson_unit_id": "lesson-1",
                        "ppt_manuscript_task_id": "tlj-manuscript-1",
                    },
                    "resume_from_job_id": "tlj-ppt-v6-paused",
                    "error": {
                        "code": "render_quality_gate_failed",
                        "message": "PPT 渲染质量校验失败",
                        "retryable": True,
                    },
                    "updated_at": "2026-09-05T04:00:00+00:00",
                },
            },
        },
    )

    stage = result["stages"]["ppt"]
    lesson = result["lessons"][0]["stages"]["ppt"]
    assert stage["display_state"] == "available"
    assert stage["counts"] == {
        "total": 1,
        "available": 1,
        "generating": 0,
        "failed": 0,
        "stale": 0,
    }
    assert stage["latest_attempt"]["task_ids"] == [task_id]
    assert lesson["task_state"] == "failed"
    assert lesson["issues"][0]["task_id"] == task_id
    assert lesson["issues"][0]["recovery"]["action"] == "retry_generation"


def test_cancelled_attempt_is_not_reported_as_generation_failure():
    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {
                "script-cancelled": {
                    "id": "script-cancelled",
                    "course_id": "course-1",
                    "type": "teacher_lesson_script_generation",
                    "lesson_unit_id": "lesson-1",
                    "status": "cancelled",
                    "updated_at": "2026-09-05T01:00:00+00:00",
                },
            },
        },
    )

    stage = result["stages"]["script"]
    lesson = result["lessons"][0]["stages"]["script"]
    assert stage["display_state"] == "not_generated"
    assert stage["task_state"] == "cancelled"
    assert stage["latest_attempt_failed"] is False
    assert stage["counts"]["failed"] == 0
    assert stage["issues"] == []
    assert lesson["display_state"] == "not_generated"
    assert lesson["task_state"] == "cancelled"


def test_error_attempt_projects_failure_and_honors_explicit_retryability():
    actions = {}
    for retryable in (True, False):
        task_id = f"outline-error-{str(retryable).lower()}"
        stage = compile_course_production_state(
            {"course_id": "course-1"},
            tasks=[{
                "id": task_id,
                "course_id": "course-1",
                "type": "teacher_outline_generation",
                "status": "error",
                "error_detail": {
                    "code": "provider_interrupted",
                    "message": "模型请求中断。",
                    "retryable": retryable,
                },
                "updated_at": "2026-09-05T05:00:00+00:00",
            }],
        )["stages"]["outline"]

        assert stage["display_state"] == "failed"
        assert stage["task_state"] == "failed"
        assert stage["latest_attempt_failed"] is True
        assert stage["latest_attempt"]["task_ids"] == [task_id]
        assert stage["issues"][0]["task_id"] == task_id
        actions[retryable] = stage["issues"][0]["recovery"]["action"]

    assert actions == {True: "retry_generation", False: "inspect_failure"}


def test_legacy_canceled_attempt_projects_cancelled_without_failure():
    task_id = "outline-canceled"
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": task_id,
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "canceled",
            "updated_at": "2026-09-05T05:00:00+00:00",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "not_generated"
    assert stage["task_state"] == "cancelled"
    assert stage["latest_attempt_failed"] is False
    assert stage["latest_attempt"]["task_ids"] == [task_id]
    assert stage["issues"] == []


def test_conflict_attempt_projects_failure_for_inspection_without_resume():
    task_id = "outline-conflict"
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": task_id,
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "conflict",
            "message": "候选大纲基于旧课程版本。",
            "error_detail": {
                "code": "revision_conflict",
                "retryable": True,
            },
            "updated_at": "2026-09-05T05:00:00+00:00",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "failed"
    assert stage["task_state"] == "failed"
    assert stage["latest_attempt_failed"] is True
    assert stage["latest_attempt"]["task_ids"] == [task_id]
    assert stage["issues"][0]["task_id"] == task_id
    assert stage["issues"][0]["code"] == "revision_conflict"
    assert stage["issues"][0]["recovery"]["action"] == "inspect_failure"


@pytest.mark.parametrize(
    ("status", "task_state", "allowed_actions", "action_targets"),
    [
        (
            "active",
            "running",
            ["inspect_failure"],
            {},
        ),
        (
            "queued",
            "queued",
            ["inspect_failure"],
            {},
        ),
        (
            "waiting_for_input",
            "waiting_for_input",
            ["provide_input"],
            {"provide_input": ["outline-waiting_for_input"]},
        ),
        (
            "waiting_for_review",
            "waiting_for_review",
            ["review_generation"],
            {"review_generation": ["outline-waiting_for_review"]},
        ),
    ],
)
def test_legacy_active_queued_and_waiting_states_use_supported_actions_only(
    status,
    task_state,
    allowed_actions,
    action_targets,
):
    task_id = f"outline-{status}"
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": task_id,
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": status,
            "updated_at": "2026-09-05T06:00:00+00:00",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "generating"
    assert stage["task_state"] == task_state
    assert stage["counts"]["generating"] == 1
    assert stage["task_ids"] == [task_id]
    assert stage["allowed_actions"] == allowed_actions
    assert stage["action_targets"] == action_targets


def test_unknown_nonempty_task_state_is_never_collapsed_to_idle():
    task_id = "outline-unknown-owner-state"
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": task_id,
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "provider_half_closed",
            "updated_at": "2026-09-05T06:00:00+00:00",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "failed"
    assert stage["task_state"] == "unknown"
    assert stage["latest_attempt_failed"] is False
    assert stage["task_ids"] == [task_id]
    assert stage["allowed_actions"] == ["inspect_failure"]
    assert stage["issues"][0]["task_id"] == task_id
    assert stage["issues"][0]["code"] == "unknown_task_state"
    assert stage["issues"][0]["recovery"]["action"] == "inspect_failure"


@pytest.mark.parametrize(
    ("recovery", "expected_action"),
    [
        (
            {
                "state": "quality_blocked",
                "can_resume": True,
                "reason_code": "quality_gate_failed",
                "reason": "可按保存的质量现场修复。",
            },
            "retry_generation",
        ),
        (
            {
                "state": "quality_blocked",
                "can_resume": False,
                "reason_code": "quality_gate_unchanged",
                "reason": "重复质量失败，需要人工检查。",
            },
            "inspect_failure",
        ),
    ],
)
def test_quality_blocked_warning_uses_recovery_authority(
    recovery,
    expected_action,
):
    task_id = f"outline-{expected_action}"
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": task_id,
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed_with_warnings",
            "phase": "quality_failed",
            "publication_allowed": False,
            "recovery": recovery,
            "updated_at": "2026-09-05T06:00:00+00:00",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "failed"
    assert stage["task_state"] == "failed"
    assert stage["latest_attempt_failed"] is True
    assert stage["task_ids"] == [task_id]
    assert stage["allowed_actions"] == [expected_action]
    assert stage["issues"][0]["task_id"] == task_id
    assert stage["issues"][0]["code"] == recovery["reason_code"]
    assert stage["issues"][0]["recovery"]["action"] == expected_action


def test_completed_with_warnings_requires_published_nonblocking_evidence():
    published = compile_course_production_state(
        _course(1),
        tasks=[{
            "id": "outline-published-warning",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed_with_warnings",
            "publication_allowed": True,
        }],
    )["stages"]["outline"]
    blocked = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": "outline-quality-report-blocked",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed_with_warnings",
            "quality_report": {
                "final_status": "quality_failed",
                "publication_allowed": False,
            },
        }],
    )["stages"]["outline"]
    unverified = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": "outline-unverified-warning",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed_with_warnings",
        }],
    )["stages"]["outline"]

    assert published["display_state"] == "available"
    assert published["task_state"] == "completed"
    assert published["allowed_actions"] == []
    assert blocked["display_state"] == "failed"
    assert blocked["task_state"] == "failed"
    assert blocked["allowed_actions"] == ["inspect_failure"]
    assert blocked["issues"][0]["code"] == "quality_blocked"
    assert unverified["display_state"] == "failed"
    assert unverified["task_state"] == "failed"
    assert unverified["allowed_actions"] == ["inspect_failure"]


def test_completed_task_without_formal_asset_fails_closed_for_inspection():
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": "outline-completed-without-asset",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "failed"
    assert stage["task_state"] == "completed"
    assert stage["allowed_actions"] == ["inspect_failure"]
    assert stage["issues"][0]["code"] == "completed_without_asset"


@pytest.mark.parametrize("owner", ["task_manager", "ppt_checkpoint"])
def test_paused_non_authoring_snapshot_without_recovery_cannot_resume(owner):
    task = {
        "task_id": "ppt-paused-without-recovery",
        "course_id": "course-1",
        "lesson_unit_id": "lesson-1",
        "status": "paused",
    }
    arguments = (
        {"tasks": [{**task, "type": "teacher_lesson_ppt_generation"}]}
        if owner == "task_manager"
        else {"ppt_checkpoints": [task]}
    )

    lesson = compile_course_production_state(
        _course(1),
        authoring_state={"course_id": "course-1", "lessons": {}},
        **arguments,
    )["lessons"][0]["stages"]["ppt"]

    assert lesson["task_state"] == "paused"
    assert lesson["allowed_actions"] == ["inspect_failure"]


def test_paused_authoring_job_without_recovery_uses_repository_lifecycle():
    lesson = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {
                "script-paused": {
                    "id": "script-paused",
                    "course_id": "course-1",
                    "type": "teacher_lesson_script_generation",
                    "lesson_unit_id": "lesson-1",
                    "status": "paused",
                },
            },
        },
    )["lessons"][0]["stages"]["script"]

    assert lesson["allowed_actions"] == [
        "resume_generation",
        "cancel_generation",
    ]


@pytest.mark.parametrize(
    ("status", "expected_display"),
    [
        ("queued", "generating"),
        ("running", "generating"),
        ("waiting_for_input", "generating"),
        ("waiting_for_review", "generating"),
        ("paused", "generating"),
        ("failed", "failed"),
        ("provider_half_closed", "failed"),
    ],
)
def test_anonymous_actionable_task_has_no_write_actions(status, expected_display):
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": status,
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == expected_display
    assert stage["counts"]["generating"] == (expected_display == "generating")
    assert stage["task_ids"] == []
    assert stage["allowed_actions"] == ["inspect_failure"]
    assert stage["issues"][0]["code"] == "missing_task_id"


@pytest.mark.parametrize(
    ("task_type", "stage_name"),
    [
        ("teacher_lesson_plan_generation", "lesson_plan"),
        ("teacher_lesson_script_generation", "script"),
        ("teacher_lesson_ppt_generation", "ppt"),
    ],
)
def test_anonymous_unscoped_teacher_asset_task_remains_visible(
    task_type,
    stage_name,
):
    stage = compile_course_production_state(
        _course(1),
        tasks=[{
            "course_id": "course-1",
            "type": task_type,
            "status": "running",
        }],
    )["stages"][stage_name]

    assert stage["display_state"] == "generating"
    assert stage["task_state"] == "running"
    assert stage["task_ids"] == []
    assert stage["allowed_actions"] == ["inspect_failure"]
    assert stage["action_targets"] == {}
    assert [item["code"] for item in stage["issues"]] == ["missing_task_id"]


def test_mixed_batch_action_targets_do_not_expand_retry_scope():
    jobs = [
        {
            "id": "retryable-job",
            "parent_job_id": "mixed-batch",
            "course_id": "course-1",
            "type": "teacher_lesson_script_generation",
            "lesson_unit_id": "lesson-1",
            "status": "failed",
            "error": {"retryable": True},
            "updated_at": "2026-09-05T08:00:00+00:00",
        },
        {
            "id": "unknown-job",
            "parent_job_id": "mixed-batch",
            "course_id": "course-1",
            "type": "teacher_lesson_script_generation",
            "lesson_unit_id": "lesson-2",
            "status": "provider_half_closed",
            "updated_at": "2026-09-05T08:00:00+00:00",
        },
    ]
    stage = compile_course_production_state(
        _course(2),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {item["id"]: item for item in jobs},
        },
    )["stages"]["script"]

    assert stage["task_ids"] == ["retryable-job", "unknown-job"]
    assert stage["allowed_actions"] == ["retry_generation", "inspect_failure"]
    assert stage["action_targets"] == {
        "retry_generation": ["retryable-job"],
    }


def test_formal_owner_wins_newer_checkpoint_with_same_task_id():
    task_id = "teacher-ppt-running"
    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {
                task_id: {
                    "id": task_id,
                    "course_id": "course-1",
                    "type": "teacher_lesson_ppt_generation",
                    "lesson_unit_id": "lesson-1",
                    "status": "running",
                    "updated_at": "2026-09-05T08:00:00+00:00",
                },
            },
        },
        ppt_checkpoints=[{
            "task_id": task_id,
            "lesson_unit_id": "lesson-1",
            "status": "failed",
            "updated_at": "2026-09-05T09:00:00+00:00",
        }],
    )

    lesson = result["lessons"][0]["stages"]["ppt"]
    assert lesson["task_state"] == "running"
    assert lesson["allowed_actions"] == [
        "pause_generation",
        "cancel_generation",
    ]
    assert lesson["action_targets"] == {
        "pause_generation": [task_id],
        "cancel_generation": [task_id],
    }


@pytest.mark.parametrize(
    ("owner_input", "expected_code"),
    [
        (
            {"tasks": [{
                "id": "wrong-owner",
                "course_id": "course-1",
                "type": "teacher_lesson_script_generation",
                "lesson_unit_id": "lesson-1",
                "status": "running",
            }]},
            "task_command_owner_mismatch",
        ),
        (
            {"authoring_state": {
                "course_id": "course-1",
                "lessons": {},
                "jobs": {"waiting-teacher-job": {
                    "id": "waiting-teacher-job",
                    "course_id": "course-1",
                    "type": "teacher_lesson_script_generation",
                    "lesson_unit_id": "lesson-1",
                    "status": "waiting_for_input",
                }},
            }},
            "task_status_has_no_command_owner",
        ),
    ],
)
def test_owner_or_type_without_matching_command_cannot_authorize_writes(
    owner_input,
    expected_code,
):
    lesson = compile_course_production_state(
        _course(1),
        **owner_input,
    )["lessons"][0]["stages"]["script"]

    assert lesson["allowed_actions"] == ["inspect_failure"]
    assert lesson["action_targets"] == {}
    assert expected_code in {item["code"] for item in lesson["issues"]}


def test_unconfirmed_outline_draft_binds_regeneration_to_real_task_id():
    stage = compile_course_production_state(
        _course(1),
        tasks=[{
            "id": "outline-completed",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "completed",
        }],
        blueprint_draft={"draft_revision_id": "draft-1"},
    )["stages"]["outline"]

    assert stage["has_unconfirmed_draft"] is True
    assert stage["allowed_actions"] == ["regenerate_from_latest_source"]
    assert stage["action_targets"] == {
        "regenerate_from_latest_source": ["outline-completed"],
    }


def test_unconfirmed_outline_draft_without_task_id_fails_closed():
    stage = compile_course_production_state(
        _course(1),
        blueprint_draft={"draft_revision_id": "draft-1"},
    )["stages"]["outline"]

    assert stage["has_unconfirmed_draft"] is True
    assert stage["allowed_actions"] == ["inspect_failure"]
    assert stage["action_targets"] == {}
    assert stage["issues"][0]["code"] == "outline_draft_missing_task_id"


@pytest.mark.parametrize(
    ("recovery", "expected_action"),
    [
        (
            {
                "state": "manual_resume",
                "can_resume": True,
                "reason_code": "checkpoint_available",
            },
            "retry_generation",
        ),
        (
            {
                "state": "unavailable",
                "can_resume": False,
                "reason_code": "workspace_missing",
            },
            "inspect_failure",
        ),
    ],
)
def test_task_manager_recovery_overrides_checkpoint_and_retry_flags(
    recovery,
    expected_action,
):
    stage = compile_course_production_state(
        {"course_id": "course-1"},
        tasks=[{
            "id": "outline-recovery-owner",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "failed",
            "workspace_id": "ghost-workspace",
            "retryable": expected_action == "inspect_failure",
            "recovery": recovery,
        }],
    )["stages"]["outline"]

    assert stage["allowed_actions"] == [expected_action]
    assert stage["issues"][0]["recovery"]["action"] == expected_action


@pytest.mark.parametrize(
    ("retryable", "expected_action"),
    [
        (True, "retry_generation"),
        (False, "inspect_failure"),
        (None, "inspect_failure"),
    ],
)
def test_teacher_asset_job_without_recovery_requires_explicit_retryability(
    retryable,
    expected_action,
):
    error = {"code": "teacher_asset_failed", "message": "生成失败。"}
    if retryable is not None:
        error["retryable"] = retryable
    authoring = {
        "course_id": "course-1",
        "lessons": {},
        "jobs": {
            "teacher-asset-failed": {
                "schema_version": "teacher_asset_job_v1",
                "id": "teacher-asset-failed",
                "course_id": "course-1",
                "type": "teacher_lesson_script_generation",
                "lesson_unit_id": "lesson-1",
                "status": "failed",
                "checkpoint": {"current_block_id": "ghost-block"},
                "error": error,
            },
        },
    }

    lesson = compile_course_production_state(
        _course(1),
        authoring_state=authoring,
    )["lessons"][0]["stages"]["script"]

    assert lesson["task_ids"] == ["teacher-asset-failed"]
    assert lesson["allowed_actions"] == [expected_action]
    assert lesson["issues"][0]["task_id"] == "teacher-asset-failed"


@pytest.mark.parametrize(
    ("task", "expected_code"),
    [
        (
            {
                "status": "provider_half_closed",
            },
            "unknown_task_state",
        ),
        (
            {
                "status": "completed_with_warnings",
                "phase": "quality_failed",
                "publication_allowed": False,
                "recovery": {
                    "state": "quality_blocked",
                    "can_resume": False,
                    "reason_code": "quality_gate_unchanged",
                },
            },
            "quality_gate_unchanged",
        ),
    ],
)
def test_last_good_keeps_available_while_problem_and_inspection_remain_visible(
    task,
    expected_code,
):
    lesson = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        },
        tasks=[{
            "id": "plan-problem",
            "course_id": "course-1",
            "type": "teacher_lesson_plan_generation",
            "lesson_unit_id": "lesson-1",
            **task,
        }],
    )["lessons"][0]["stages"]["lesson_plan"]

    assert lesson["display_state"] == "available"
    assert lesson["task_ids"] == ["plan-problem"]
    assert lesson["allowed_actions"] == ["inspect_failure"]
    assert lesson["issues"][0]["code"] == expected_code


def test_last_good_remains_available_when_latest_regeneration_fails():
    task = {
        "id": "retry-lesson-1",
        "course_id": "course-1",
        "type": "teacher_lesson_plan_generation",
        "lesson_unit_id": "lesson-1",
        "status": "failed",
        "error": {"code": "provider_unavailable", "message": "模型暂时不可用"},
        "updated_at": "2026-09-04T01:00:00+00:00",
    }

    result = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "outline_revision_id": "outline-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        },
        tasks=[task],
    )
    lesson_state = result["lessons"][0]["stages"]["lesson_plan"]
    stage_state = result["stages"]["lesson_plan"]

    assert lesson_state["display_state"] == "available"
    assert lesson_state["availability"] == "usable"
    assert lesson_state["latest_attempt_failed"] is True
    assert stage_state["display_state"] == "available"
    assert stage_state["latest_attempt_failed"] is True
    assert lesson_state["issues"][0]["code"] == "provider_unavailable"


def test_issue_identity_is_stable_and_recovery_is_never_automatic():
    task = {
        "id": "retry-lesson-1",
        "course_id": "course-1",
        "type": "teacher_lesson_script_generation",
        "lesson_unit_id": "lesson-1",
        "status": "failed",
        "checkpoint": {"current_block_id": "block-2"},
        "error": {
            "code": "script_quality_failed",
            "message": "讲义质量校验未通过",
            "retryable": True,
        },
    }
    first = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {task["id"]: task},
        },
    )["issues"][0]
    second = compile_course_production_state(
        _course(1),
        authoring_state={
            "course_id": "course-1",
            "lessons": {},
            "jobs": {task["id"]: deepcopy(task)},
        },
    )["issues"][0]

    assert first == second
    assert first["stage"] == "script"
    assert first["lesson_unit_id"] == "lesson-1"
    assert first["block_id"] == "block-2"
    assert first["task_id"] == "retry-lesson-1"
    assert first["recovery"] == {
        "action": "retry_generation",
        "automatic": False,
        "requires_confirmation": True,
    }


def test_outline_hour_findings_remain_available_and_are_projected_for_review():
    course = {
        **_course(1),
        "course_outline_quality_report": {
            "status": "review_suggested",
            "blocking_issues": [],
            "issues": [
                {
                    "code": "outline_editorial:missing_hour_breakdown",
                    "message": "本讲尚未分配学时。",
                    "category": "hours",
                    "node_ids": ["lesson-1"],
                    "blocking": False,
                },
                {
                    "code": "outline_editorial:hour_total_mismatch",
                    "message": "各讲学时合计与课程总学时不一致。",
                    "category": "hours",
                    "blocking": False,
                },
            ],
        },
    }

    stage = compile_course_production_state(course)["stages"]["outline"]

    assert stage["display_state"] == "available"
    assert stage["availability"] == "usable"
    assert stage["update_required"] is True
    assert stage["blocking_issues"] == []
    assert {item["code"] for item in stage["review_issues"]} == {
        "outline_editorial:missing_hour_breakdown",
        "outline_editorial:hour_total_mismatch",
    }
    assert stage["review_issues"][0]["recovery"]["automatic"] is False


def test_legacy_hour_blocker_is_downgraded_to_non_blocking_review():
    course = {
        **_course(1),
        "course_outline_quality_report": {
            "passed": False,
            "blockers": [{
                "code": "outline_editorial:hour_total_mismatch",
                "message": "旧报告误把学时差异写进阻断列表。",
            }],
        },
    }

    stage = compile_course_production_state(course)["stages"]["outline"]

    assert stage["display_state"] == "available"
    assert stage["blocking_issues"] == []
    assert [item["code"] for item in stage["review_issues"]] == [
        "outline_editorial:hour_total_mismatch"
    ]


def test_legacy_detail_zero_hour_blocker_is_also_non_blocking():
    course = {
        **_course(1),
        "course_outline_quality_report": {
            "blockers": [{
                "code": "teacher_outline_detail:missing_hour_breakdown",
                "message": "旧明细校验把零学时写进阻断列表。",
            }],
        },
    }

    stage = compile_course_production_state(course)["stages"]["outline"]

    assert stage["display_state"] == "available"
    assert stage["blocking_issues"] == []
    assert [item["code"] for item in stage["review_issues"]] == [
        "teacher_outline_detail:missing_hour_breakdown"
    ]


def test_outline_structure_blocker_fails_only_without_last_good_outline():
    course = {
        "course_id": "course-1",
        "course_outline_quality_report": {
            "blocking_issues": [{
                "code": "outline_structure:missing_lesson_units",
                "message": "大纲没有可用讲次。",
                "blocking": True,
            }],
        },
    }

    stage = compile_course_production_state(
        course,
        authoring_state={"course_id": "course-1", "outline_revision_id": "outline-empty"},
    )["stages"]["outline"]

    assert stage["display_state"] == "failed"
    assert stage["availability"] == "missing"
    assert [item["code"] for item in stage["blocking_issues"]] == [
        "outline_structure:missing_lesson_units"
    ]
    assert stage["review_issues"] == []
    assert stage["allowed_actions"] == ["inspect_failure"]


def test_blocker_keeps_only_safe_active_controls_and_inspection():
    stage = compile_course_production_state(
        {
            "course_id": "course-1",
            "course_outline_quality_report": {
                "blocking_issues": [{
                    "code": "outline_structure:missing_lesson_units",
                    "message": "大纲没有可用讲次。",
                }],
            },
        },
        tasks=[{
            "id": "outline-running-behind-blocker",
            "course_id": "course-1",
            "type": "teacher_outline_generation",
            "status": "running",
        }],
    )["stages"]["outline"]

    assert stage["display_state"] == "generating"
    assert stage["allowed_actions"] == [
        "pause_generation",
        "cancel_generation",
        "inspect_failure",
    ]


def test_optional_ai_recommendation_pending_review_never_blocks_usable_plan():
    course = {
        **_course(1),
        "material_bindings": [{
            "asset_id": "source-ai-1",
            "source_label": "AI 推荐参考资料",
            "authority": "secondary",
            "usage_policy": "optional",
            "source_metadata": {
                "origin": "ai_recommendation",
                "teacher_confirmed": False,
                "private_excerpt": "不得进入投影的资料正文",
            },
        }],
        "material_assets": [{
            "asset_id": "source-ai-1",
            "filename": "reference.pdf",
            "status": "parsed",
        }],
    }
    result = compile_course_production_state(
        course,
        authoring_state={
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        },
    )
    stage = result["stages"]["lesson_plan"]
    summary = result["source_summary"]

    assert stage["display_state"] == "available"
    assert stage["blocking_issues"] == []
    assert summary["pending_review_count"] == 1
    assert summary["required_blocked_count"] == 0
    assert summary["sources"] == [{
        "source_id": "source-ai-1",
        "label": "AI 推荐参考资料",
        "requirement": "optional",
        "state": "pending_review",
        "code": "optional_source_pending_review",
        "summary": "可选来源尚待核对，不影响现有内容使用。",
    }]
    assert "private_excerpt" not in str(summary)
    assert "不得进入投影的资料正文" not in str(summary)


@pytest.mark.parametrize(
    ("source_fact", "expected_code", "expected_action"),
    [
        ({"status": "failed"}, "required_source_parse_failed", "replace_or_reupload_source"),
        ({"binding_state": "conflict"}, "required_source_binding_conflict", "resolve_source_binding"),
        ({"validity_state": "expired"}, "required_source_stale", "refresh_required_source"),
    ],
)
def test_required_source_failures_return_stable_blocker_and_recovery(
    source_fact,
    expected_code,
    expected_action,
):
    course = {
        **_course(1),
        "material_bindings": [{
            "asset_id": "source-primary-1",
            "source_label": "课程指定教材",
            "authority": "primary",
            "usage_policy": "must_use",
            **source_fact,
        }],
    }

    result = compile_course_production_state(course)
    stage = result["stages"]["lesson_plan"]
    blocker = stage["blocking_issues"][0]

    assert stage["display_state"] == "failed"
    assert result["preparation_state"] == "preparing"
    assert result["source_summary"]["required_blocked_count"] == 1
    assert result["source_summary"]["pending_review_count"] == 0
    assert blocker["source_id"] == "source-primary-1"
    assert blocker["code"] == expected_code
    assert blocker["recovery"]["action"] == expected_action
    assert blocker["recovery"]["automatic"] is False
    assert stage["allowed_actions"] == ["inspect_failure"]


def test_required_source_blocker_preserves_last_good_plan():
    course = {
        **_course(1),
        "material_bindings": [{
            "asset_id": "source-primary-1",
            "authority": "primary",
            "usage_policy": "must_use",
            "validity_state": "stale",
        }],
    }

    result = compile_course_production_state(
        course,
        authoring_state={
            "course_id": "course-1",
            "lessons": {"lesson-1": _ready_lesson(1)},
        },
    )
    stage = result["stages"]["lesson_plan"]

    assert stage["display_state"] == "available"
    assert stage["availability"] == "usable"
    assert stage["update_required"] is True
    assert result["preparation_state"] == "preparing"


class _ReadOnlyRepository:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.read_count = 0

    def view(self, _course_id: str) -> dict:
        self.read_count += 1
        return deepcopy(self.state)


class _ReadOnlyTaskManager:
    def __init__(self, tasks: list[dict]) -> None:
        self.tasks = {
            str(item["id"]): deepcopy(item)
            for item in tasks
        }
        self.read_count = 0

    def get_tasks_by_course(self, course_id: str) -> list[dict]:
        self.read_count += 1
        return [
            deepcopy(item) for item in self.tasks.values()
            if item.get("course_id") == course_id
        ]


def test_teacher_course_list_returns_new_projection_with_legacy_fields_without_writes(monkeypatch):
    course = {
        **_course(1),
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "is_published": True,
    }
    authoring = {
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {"lesson-1": _ready_lesson(1)},
    }
    repository = _ReadOnlyRepository(authoring)
    manager = _ReadOnlyTaskManager([])
    before = deepcopy((course, authoring, manager.tasks))
    monkeypatch.setattr(courses.storage, "list_courses", lambda: [deepcopy(course)])
    monkeypatch.setattr(courses.teaching_calendar_repository, "list_sessions", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(courses, "get_teacher_lesson_authoring_repository", lambda: repository)

    result = courses._teacher_course_library_projection(
        "teacher-a",
        set(),
        manager,
    )[0]

    assert result["preparation_state"] == "prepared"
    assert result["preparation_summary"]["ready_handouts"] == 1
    assert result["course_production_state"]["schema_version"] == "course_production_state_v1"
    assert result["course_production_state"]["preparation_state"] == "prepared"
    assert (course, authoring, manager.tasks) == before


@pytest.mark.asyncio
async def test_single_teacher_course_returns_new_projection_and_preserves_course_payload(monkeypatch):
    course = {
        **_course(1),
        "course_name": "设计思维",
        "authoring_surface": "teacher",
        "is_published": True,
    }
    authoring = {
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {"lesson-1": _ready_lesson(1)},
    }
    repository = _ReadOnlyRepository(authoring)
    manager = _ReadOnlyTaskManager([])

    async def get_course(_course_id: str) -> dict:
        return deepcopy(course)

    monkeypatch.setattr(courses, "get_course_or_404", get_course)
    monkeypatch.setattr(courses, "get_teacher_lesson_authoring_repository", lambda: repository)
    monkeypatch.setattr(courses, "get_task_manager_optional", lambda: manager)

    result = await courses.get_course("course-1", SimpleNamespace(headers={}))

    assert result["course_name"] == "设计思维"
    assert result["preparation_summary"]["planned_lessons"] == 1
    assert result["course_production_state"]["stages"]["ppt"]["counts"]["available"] == 1


@pytest.mark.asyncio
async def test_teaching_calendar_get_adds_same_projection_without_changing_saved_calendar(monkeypatch):
    course = {**_course(1), "course_name": "设计思维"}
    saved_calendar = {
        "course_id": "course-1",
        "course_title": "设计思维",
        "revision": 3,
        "sessions": [{"session_id": "session-1", "lesson_unit_id": "lesson-1"}],
    }
    repository = _ReadOnlyRepository({
        "course_id": "course-1",
        "outline_revision_id": "outline-1",
        "lessons": {"lesson-1": _ready_lesson(1)},
    })
    manager = _ReadOnlyTaskManager([])

    async def get_course(_course_id: str) -> dict:
        return deepcopy(course)

    class CalendarRepository:
        def load(self, *_args) -> dict:
            return deepcopy(saved_calendar)

    monkeypatch.setattr(teaching_calendar, "get_course_or_404", get_course)
    monkeypatch.setattr(teaching_calendar, "teaching_calendar_repository", CalendarRepository())
    monkeypatch.setattr(teaching_calendar, "get_teacher_lesson_authoring_repository", lambda: repository)
    monkeypatch.setattr(teaching_calendar, "get_task_manager_optional", lambda: manager)

    result = await teaching_calendar.get_teaching_calendar(
        "course-1",
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
    )

    assert result["revision"] == 3
    assert result["sessions"] == saved_calendar["sessions"]
    assert result["course_production_state"]["stages"]["script"]["counts"]["available"] == 1
    assert saved_calendar["revision"] == 3
