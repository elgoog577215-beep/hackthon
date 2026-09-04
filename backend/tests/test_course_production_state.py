from copy import deepcopy
from types import SimpleNamespace

import pytest

from course_production_state import (
    Availability,
    CourseProductionState,
    DisplayState,
    PreparationState,
    ProductionStage,
    SourceRequirement,
    SourceReviewState,
    SourceState,
    TaskState,
    compile_course_production_state,
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
        "idle", "queued", "running", "paused", "failed", "completed"
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
        "error": {"code": "script_quality_failed", "message": "讲义质量校验未通过"},
    }
    first = compile_course_production_state(
        _course(1),
        authoring_state={"course_id": "course-1", "lessons": {}},
        tasks=[task],
    )["issues"][0]
    second = compile_course_production_state(
        _course(1),
        authoring_state={"course_id": "course-1", "lessons": {}},
        tasks=[deepcopy(task)],
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
