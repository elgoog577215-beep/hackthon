from __future__ import annotations

import asyncio
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_repository import CourseDocumentRepository
from dependencies import get_course_document_repository, require_task_manager
from routers import courses as courses_router


class MemoryStorage:
    def __init__(self):
        self.data: dict[str, dict] = {}

    def load_course(self, course_id: str):
        return deepcopy(self.data.get(course_id))

    def save_course(self, course_id: str, value: dict):
        self.data[course_id] = deepcopy(value)


def preview(status: str = "completed_with_warnings") -> dict:
    return {
        "course_id": "course-1",
        "course_name": "人工智能基础十讲",
        "task": {"id": "job-1", "status": status},
        "nodes": [
            {
                "node_id": "lesson-1",
                "parent_node_id": "root",
                "node_name": "第一讲 AI概览",
                "node_level": 1,
                "node_content": "本讲介绍人工智能的定义。",
            },
            {
                "node_id": "knowledge-1",
                "parent_node_id": "lesson-1",
                "node_name": "1.1 AI定义",
                "node_level": 2,
                "node_content": "解释人工智能的基本定义。",
            },
        ],
        "course_plan": {
            "chapters": [
                {
                    "chapter_id": "lesson-1",
                    "title": "第一讲 AI概览",
                    "sections": [
                        {
                            "node_id": "knowledge-1",
                            "title": "1.1 AI定义",
                            "learning_objective": "解释人工智能的基本定义。",
                        }
                    ],
                }
            ]
        },
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v3",
            "status": "completed",
            "revision_id": "tpr_job_1",
            "sections": [
                {
                    "node_id": "knowledge-1",
                    "title": "1.1 AI定义",
                    "learning_objective": "解释人工智能的基本定义。",
                }
            ],
        },
    }


def client_for(status: str = "completed_with_warnings") -> tuple[TestClient, CourseDocumentRepository, MemoryStorage]:
    storage = MemoryStorage()
    repository = CourseDocumentRepository(storage)
    asyncio.run(repository.create_generation_shell(
        "course-1",
        title="人工智能基础十讲",
        job_id="job-1",
    ))

    class FakeTaskManager:
        @staticmethod
        def get_generation_preview(course_id: str):
            assert course_id == "course-1"
            return preview(status)

        @staticmethod
        def get_generation_workspace_course(course_id: str):
            assert course_id == "course-1"
            return preview(status)

    app = FastAPI()
    app.include_router(courses_router.router, prefix="/api")
    app.dependency_overrides[get_course_document_repository] = lambda: repository
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    return TestClient(app), repository, storage


def test_confirms_preview_as_teacher_source_without_student_publication():
    client, repository, storage = client_for()

    response = client.post(
        "/api/courses/course-1/teacher-authoring/confirm-generation-preview",
        json={"confirm": True, "source_task_id": "job-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    document, canonical = repository.load_document("course-1")
    assert canonical is True
    assert [section.section_id for section in document.sections] == ["lesson-1", "knowledge-1"]
    assert document.blocks
    assert storage.data["course-1"]["course_plan"]["chapters"]
    assert response.json()["workbench"]["available"] is True
    assert response.json()["workbench"]["current_plan_revision_id"]
    assert "course_document_publication" not in storage.data["course-1"]


def test_rejects_running_preview_and_keeps_shell_empty():
    client, repository, _storage = client_for("running")

    response = client.post(
        "/api/courses/course-1/teacher-authoring/confirm-generation-preview",
        json={"confirm": True, "source_task_id": "job-1"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "generation_preview_not_terminal"
    document, _canonical = repository.load_document("course-1")
    assert document.sections == []
    assert document.blocks == []
