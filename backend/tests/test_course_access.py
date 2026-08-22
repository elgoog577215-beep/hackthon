from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_access import (
    CourseOwnershipMiddleware,
    course_id_from_api_path,
    teacher_course_access_denial,
)


def test_course_id_parser_covers_shared_and_teacher_routes():
    assert course_id_from_api_path("/api/courses/course-1/lesson-authoring") == "course-1"
    assert course_id_from_api_path("/api/teacher/courses/course-2/generation-preview") == "course-2"
    assert course_id_from_api_path("/api/teacher/courses") == ""
    assert course_id_from_api_path("/api/course-generation/generate") == ""


def test_unpublished_teacher_course_is_visible_only_to_owner():
    course = {
        "course_id": "course-1",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "course_status": "draft",
    }

    assert teacher_course_access_denial(course, "teacher-a") is None
    assert teacher_course_access_denial(course, "teacher-b") == {
        "code": "teacher_course_unavailable",
        "message": "课程不存在或不属于当前教师",
    }
    assert teacher_course_access_denial(course, None) is not None


def test_published_or_shared_courses_remain_readable():
    published = {
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "course_document_publication": {"published_at": "2026-08-23T00:00:00Z"},
    }
    shared = {"authoring_surface": "shared", "owner_id": "teacher-a"}

    assert teacher_course_access_denial(published, "learner-b") is None
    assert teacher_course_access_denial(published, "learner-b", method="DELETE") is not None
    assert teacher_course_access_denial(shared, "learner-b", method="DELETE") is None


def test_middleware_guards_every_course_subrouter_without_blocking_public_reads():
    course = {
        "course_id": "course-1",
        "authoring_surface": "teacher",
        "owner_id": "teacher-a",
        "course_status": "draft",
    }
    storage = type("Storage", (), {"load_course": lambda _self, _course_id: course})()
    app = FastAPI()
    app.add_middleware(CourseOwnershipMiddleware, course_storage=storage)

    @app.get("/api/courses/{course_id}/lesson-authoring")
    def read_lesson_authoring(course_id: str):
        return {"course_id": course_id}

    @app.post("/api/courses/{course_id}/lesson-authoring")
    def write_lesson_authoring(course_id: str):
        return {"course_id": course_id}

    client = TestClient(app)
    denied = client.get(
        "/api/courses/course-1/lesson-authoring",
        headers={"X-User-Id": "teacher-b"},
    )
    owned = client.get(
        "/api/courses/course-1/lesson-authoring",
        headers={"X-User-Id": "teacher-a"},
    )
    course["course_document_publication"] = {"published_at": "2026-08-23"}
    public_read = client.get(
        "/api/courses/course-1/lesson-authoring",
        headers={"X-User-Id": "learner-b"},
    )
    public_write = client.post(
        "/api/courses/course-1/lesson-authoring",
        headers={"X-User-Id": "learner-b"},
    )

    assert denied.status_code == 404
    assert owned.status_code == 200
    assert public_read.status_code == 200
    assert public_write.status_code == 404
