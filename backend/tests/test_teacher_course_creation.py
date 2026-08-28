from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers import courses
from course_repository import CourseDocumentRepository
from storage import Storage


@pytest.mark.asyncio
async def test_create_teacher_course_persists_baseline_without_starting_generation(monkeypatch):
    repository = SimpleNamespace(create_teacher_draft=AsyncMock())
    package_repository = SimpleNamespace(
        create_package=MagicMock(return_value={"package_id": "tcs-course-1"}),
        load_owned=MagicMock(),
        register_material_reference=MagicMock(),
    )
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)
    monkeypatch.setattr(courses, "teacher_course_space_repository", package_repository)
    monkeypatch.setattr(courses.uuid, "uuid4", lambda: "course-1")

    body = courses.TeacherCourseCreateRequest.model_validate({
        "course_name": "设计思维",
        "academic_year": "2026-2027",
        "term": "秋冬",
        "course_code": "DES101",
        "course_goal": "完成可验证的创新方案",
        "default_location": "西1-205",
        "target_grade": "本科生",
        "course_category": "通识必修课",
        "target_major": "工业设计",
        "credits": 2.0,
        "total_hours": 32,
        "assessment_method": "过程考核 + 课程项目",
        "course_intro": "从真实问题出发学习设计思维。",
        "teaching_goals": "能够完成问题定义、创意与验证。",
        "generation_request": {
            "subject": "设计思维",
            "target_audience": "大学生",
            "production_mode": "automatic",
            "course_type": "systematic",
            "difficulty": "intermediate",
            "course_intent": {
                "schema_version": "course_intent_v1",
                "type": "systematic",
                "learning_goal": "完成可验证的创新方案",
            },
            "teacher_course_brief": {
                "schema_version": "teacher_course_brief_v1",
                "academic_term": "2026-2027 秋冬",
                "target_audience": "大学生",
                "total_class_hours": 32,
                "lesson_duration_minutes": 45,
                "section_count": 16,
            },
        },
    })

    result = await courses.create_teacher_course(
        body,
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
    )

    assert result["course_id"] == "course-1"
    repository.create_teacher_draft.assert_awaited_once()
    metadata = repository.create_teacher_draft.await_args.kwargs["metadata"]
    assert metadata["generation_request"]["subject"] == "设计思维"
    assert metadata["generation_request"]["production_mode"] == "automatic"
    assert metadata["generation_request"]["teacher_course_brief"]["section_count"] == 16
    assert metadata["course_profile"] == {
        "course_code": "DES101",
        "course_goal": "完成可验证的创新方案",
        "default_location": "西1-205",
        "target_grade": "本科生",
        "course_category": "通识必修课",
        "target_major": "工业设计",
        "credits": 2.0,
        "total_hours": 32,
        "assessment_method": "过程考核 + 课程项目",
        "course_intro": "从真实问题出发学习设计思维。",
        "teaching_goals": "能够完成问题定义、创意与验证。",
    }
    package_repository.create_package.assert_called_once()


@pytest.mark.asyncio
async def test_empty_teacher_course_stays_draft_in_teacher_list_and_hidden_from_learners(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / "data"))
    repository = CourseDocumentRepository(test_storage)
    package_repository = SimpleNamespace(
        create_package=MagicMock(return_value={"package_id": "tcs-course-2"}),
        load_owned=MagicMock(),
        register_material_reference=MagicMock(),
    )
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)
    monkeypatch.setattr(courses, "teacher_course_space_repository", package_repository)
    monkeypatch.setattr(courses, "storage", test_storage)
    monkeypatch.setattr(courses.uuid, "uuid4", lambda: "course-2")

    result = await courses.create_teacher_course(
        courses.TeacherCourseCreateRequest(course_name="空白课程"),
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
    )

    teacher_course = next(
        item for item in courses._list_teacher_courses(set(), owner_id="teacher-a")
        if item["course_id"] == result["course_id"]
    )
    assert teacher_course["course_status"] == "draft"
    assert teacher_course["authoring_surface"] == "teacher"
    assert teacher_course["is_published"] is False
    assert teacher_course["generation_job_id"] is None
    assert teacher_course["updated_at"]
    assert courses._list_courses_with_resume("learner-a", set()) == []


@pytest.mark.asyncio
async def test_teacher_course_creation_persists_only_current_classifications(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / "data"))
    repository = CourseDocumentRepository(test_storage)
    package_repository = SimpleNamespace(
        create_package=MagicMock(return_value={"package_id": "tcs-course-3"}),
        load_owned=MagicMock(),
        register_material_reference=MagicMock(),
    )
    monkeypatch.setattr(courses, "get_course_document_repository", lambda: repository)
    monkeypatch.setattr(courses, "teacher_course_space_repository", package_repository)
    monkeypatch.setattr(courses, "storage", test_storage)
    monkeypatch.setattr(courses.uuid, "uuid4", lambda: "course-3")

    await courses.create_teacher_course(
        courses.TeacherCourseCreateRequest.model_validate({
            "course_name": "微积分",
            "generation_request": {
                "subject": "微积分",
                "learning_purpose": "systematic",
                "course_teaching_type": "theory",
                "course_type": "systematic",
                "course_purpose": "systematic",
                "composition_style": "theory_driven",
            },
        }),
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
    )

    persisted = repository.load_course_view("course-3")["generation_request"]
    assert persisted["learning_purpose"] == "systematic"
    assert persisted["course_teaching_type"] == "theory"
    assert "course_type" not in persisted
    assert "course_purpose" not in persisted
    assert "composition_style" not in persisted
