from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models import CourseGenerationRequest
from routers import courses


def _request(actor_id: str | None = None):
    return SimpleNamespace(headers={"X-User-Id": actor_id} if actor_id else {})


def test_teacher_library_filters_courses_by_owner(monkeypatch):
    monkeypatch.setattr(courses.storage, "list_courses", lambda: [
        {
            "course_id": "owned",
            "owner_id": "teacher-a",
            "authoring_surface": "teacher",
            "course_status": "draft",
            "is_published": False,
        },
        {
            "course_id": "foreign",
            "owner_id": "teacher-b",
            "authoring_surface": "teacher",
            "course_status": "draft",
            "is_published": False,
        },
    ])

    result = courses._list_teacher_courses(set(), owner_id="teacher-a")

    assert [item["course_id"] for item in result] == ["owned"]


@pytest.mark.asyncio
async def test_teacher_course_creation_rejects_shared_or_missing_identity():
    with pytest.raises(HTTPException) as captured:
        await courses.create_teacher_course(
            courses.TeacherCourseCreateRequest(course_name="身份边界"),
            _request(),
        )

    assert captured.value.status_code == 400
    assert captured.value.detail["code"] == "actor_identity_required"


@pytest.mark.asyncio
async def test_foreign_teacher_cannot_delete_private_course(monkeypatch):
    monkeypatch.setattr(courses, "get_course_or_404", AsyncMock(return_value={
        "course_id": "course-1",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "is_published": False,
    }))
    manager = SimpleNamespace(delete_course=AsyncMock())

    with pytest.raises(HTTPException) as captured:
        await courses.delete_course("course-1", _request("teacher-b"), manager)

    assert captured.value.status_code == 404
    assert captured.value.detail["code"] == "teacher_course_unavailable"
    manager.delete_course.assert_not_awaited()


@pytest.mark.asyncio
async def test_teacher_course_deletion_removes_owned_calendar(monkeypatch):
    monkeypatch.setattr(courses, "get_course_or_404", AsyncMock(return_value={
        "course_id": "course-1",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "is_published": False,
    }))
    delete_calendar = MagicMock(return_value=True)
    monkeypatch.setattr(courses.teaching_calendar_repository, "delete", delete_calendar)
    manager = SimpleNamespace(delete_course=AsyncMock(return_value=2))

    result = await courses.delete_course("course-1", _request("teacher-a"), manager)

    assert result == {
        "status": "success",
        "removed_tasks": 2,
        "calendar_removed": True,
    }
    manager.delete_course.assert_awaited_once_with("course-1")
    delete_calendar.assert_called_once_with("teacher-a", "course-1")


@pytest.mark.asyncio
async def test_targeted_generation_reports_owner_mismatch_without_starting_job(monkeypatch):
    monkeypatch.setattr(courses.storage, "load_course", lambda _course_id: {
        "course_id": "course-1",
        "course_status": "draft",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "generation_job_id": "",
    })
    manager = SimpleNamespace(create_generation_job=AsyncMock())
    request = CourseGenerationRequest(
        subject="身份边界",
        target_course_id="course-1",
        teacher_authoring_mode="lesson_assets_v1",
    )

    with pytest.raises(HTTPException) as captured:
        await courses.create_course_generation_job(
            request,
            _request("teacher-b"),
            manager,
        )

    assert captured.value.status_code == 404
    assert captured.value.detail == {
        "code": "teacher_course_draft_unavailable",
        "message": "课程草稿不存在或不属于当前教师",
    }
    manager.create_generation_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_targeted_generation_persists_same_actor_in_task_snapshot(monkeypatch):
    monkeypatch.setattr(courses.storage, "load_course", lambda _course_id: {
        "course_id": "course-1",
        "course_status": "draft",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "generation_job_id": "",
    })
    manager = SimpleNamespace(create_generation_job=AsyncMock(return_value={
        "job_id": "job-1",
        "course_id": "course-1",
    }))
    request = CourseGenerationRequest(
        subject="身份边界",
        target_course_id="course-1",
        teacher_authoring_mode="lesson_assets_v1",
    )

    result = await courses.create_course_generation_job(
        request,
        _request("teacher-a"),
        manager,
    )

    assert result["job_id"] == "job-1"
    snapshot = manager.create_generation_job.await_args.args[0]
    assert snapshot["_retrieval_actor_id"] == "teacher-a"
