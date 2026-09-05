from fastapi import FastAPI
from fastapi.testclient import TestClient

from dependencies import get_course_document_repository, require_task_manager
from routers import tasks as tasks_router


class FakeTaskManager:
    def __init__(self):
        self.tasks = {
            "task-1": {
                "id": "task-1",
                "course_id": "course-1",
                "owner_id": "teacher-1",
                "status": "completed",
                "updated_at": "2026-08-28T00:00:00Z",
            }
        }

    def get_latest_task_by_course(self, course_id: str, task_type=None):
        return next(
            (
                task
                for task in self.tasks.values()
                if task["course_id"] == course_id
            ),
            None,
        )


class FakeCourseRepository:
    @staticmethod
    def load_raw(course_id: str):
        return {
            "course_id": course_id,
            "authoring_surface": "teacher",
            "owner_id": "teacher-1",
            "course_document_publication": {
                "published_at": "2026-08-28T00:00:00Z",
            },
        }


def test_published_course_hides_teacher_task_from_learner_without_failing_page():
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = FakeTaskManager
    app.dependency_overrides[get_course_document_repository] = FakeCourseRepository

    with TestClient(app) as client:
        learner = client.get(
            "/api/courses/course-1/task",
            headers={"X-User-Id": "learner-1"},
        )
        teacher = client.get(
            "/api/courses/course-1/task",
            headers={"X-User-Id": "teacher-1"},
        )

    assert learner.status_code == 200
    assert learner.json() == {"status": "none"}
    assert teacher.status_code == 200
    assert teacher.json()["id"] == "task-1"
