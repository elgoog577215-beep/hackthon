from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from teacher_lesson_authoring import (
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    lesson_plan_ppt_source,
    lesson_scope,
    teacher_lesson_v6_source,
)
from course_presentation_graph import compile_course_presentation_graph
from dependencies import get_teacher_lesson_authoring_repository, require_task_manager
from routers import teacher_lesson_authoring as teacher_lesson_router
from routers import courses as courses_router


def course_data():
    return {
        "course_id": "course-1",
        "nodes": [
            {"node_id": "L1-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一讲"},
            {"node_id": "L2-1-1", "parent_node_id": "L1-1", "node_level": 2, "node_name": "1.1"},
            {"node_id": "L2-1-2", "parent_node_id": "L1-1", "node_level": 2, "node_name": "1.2"},
            {"node_id": "L1-2", "parent_node_id": "root", "node_level": 1, "node_name": "第二讲"},
            {"node_id": "L2-2-1", "parent_node_id": "L1-2", "node_level": 2, "node_name": "2.1"},
        ],
        "course_plan": {
            "chapters": [
                {"node_id": "L1-1", "title": "第一讲", "sections": [{"node_id": "L2-1-1"}, {"node_id": "L2-1-2"}]},
                {"node_id": "L1-2", "title": "第二讲", "sections": [{"node_id": "L2-2-1"}]},
            ]
        },
    }


def test_lesson_scope_keeps_all_sections_inside_one_lesson():
    scoped = lesson_scope(course_data(), "L1-1")
    assert scoped["lesson"]["node_name"] == "第一讲"
    assert [item["node_id"] for item in scoped["sections"]] == ["L2-1-1", "L2-1-2"]
    assert scoped["chapter"]["node_id"] == "L1-1"


def test_repository_keeps_sibling_lesson_assets_independent(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    repository.set_outline("course-1", "outline-v1")
    first = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"sections": [{"node_id": "L2-1-1"}]},
        source_outline_revision_id="outline-v1",
    )
    second = repository.save_plan_revision(
        "course-1",
        "L1-2",
        {"sections": [{"node_id": "L2-2-1"}]},
        source_outline_revision_id="outline-v1",
    )

    assert first["working_revision_id"] != second["working_revision_id"]
    view = repository.view("course-1")
    assert set(view["lessons"]) == {"L1-1", "L1-2"}
    assert len(view["lessons"]["L1-1"]["revisions"]) == 1


def test_valid_fallback_finishes_with_warning_and_remains_editable(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = TeacherLessonAuthoringService(repository)
    job = repository.create_job(
        "course-1",
        "L1-1",
        request_id="request-1",
        source_outline_revision_id="outline-v1",
    )

    async def planner(_course, _lesson_id, on_progress):
        await on_progress("lesson_plan_validation", 70, "正在校验")
        return {
            "plan": {"sections": [{"node_id": "L2-1-1", "teaching_modules": []}]},
            "warnings": [{"code": "model_output_failed_validation"}],
            "generation_source": "deterministic_local_fallback",
            "source_outline_revision_id": "outline-v1",
        }

    completed = asyncio.run(service.run_plan_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        course_data=course_data(),
        planner=planner,
    ))

    assert completed["status"] == "completed_with_warnings"
    lesson = repository.view("course-1")["lessons"]["L1-1"]
    assert lesson["revisions"][0]["status"] == "needs_ai_review"
    assert lesson["revisions"][0]["plan"]["sections"][0]["node_id"] == "L2-1-1"


def test_request_id_is_idempotent(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    first = repository.create_job("course-1", "L1-1", request_id="same")
    second = repository.create_job("course-1", "L1-1", request_id="same")
    assert first["id"] == second["id"]


def test_teacher_only_course_is_hidden_from_student_list(monkeypatch):
    courses = [
        {"course_id": "student-course", "is_published": True},
        {
            "course_id": "teacher-course",
            "generation_job_id": "teacher-job",
            "authoring_surface": "teacher",
        },
    ]
    monkeypatch.setattr(courses_router.storage, "list_courses", lambda: courses)
    monkeypatch.setattr(courses_router.learning_snapshot_repository, "load", lambda *_args: None)
    student = courses_router._list_courses_with_resume("learner", {"teacher-job"})
    teacher = courses_router._list_teacher_courses({"teacher-job"})
    assert [item["course_id"] for item in student] == ["student-course"]
    assert [item["course_id"] for item in teacher] == ["student-course", "teacher-course"]


def test_ai_candidate_acceptance_creates_new_working_revision(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"sections": [{"node_id": "L2-1-1", "learning_objective": "before"}]},
        source_outline_revision_id="outline-v1",
    )
    candidate = repository.save_ai_candidate(
        "course-1",
        "L1-1",
        base_revision_id=lesson["working_revision_id"],
        instruction="优化目标",
        section_node_id="L2-1-1",
        plan={"sections": [{"node_id": "L2-1-1", "learning_objective": "after"}]},
    )
    accepted = repository.resolve_ai_candidate(
        "course-1",
        "L1-1",
        candidate["candidate_id"],
        accept=True,
    )

    assert len(accepted["revisions"]) == 2
    assert accepted["working_revision_id"] != lesson["working_revision_id"]
    assert accepted["revisions"][-1]["plan"]["sections"][0]["learning_objective"] == "after"
    assert accepted["ai_candidates"][0]["status"] == "accepted"


def test_lesson_ppt_binds_exact_plan_revision_and_becomes_stale(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"lesson_title": "第一讲", "sections": [{"node_id": "L2-1-1", "title": "1.1"}]},
        source_outline_revision_id="outline-v1",
    )
    source_revision = lesson["working_revision_id"]
    source = lesson_plan_ppt_source(
        lesson["revisions"][-1]["plan"],
        lesson_unit_id="L1-1",
        source_revision_id=source_revision,
    )
    assert source["source_lesson_plan_revision_id"] == source_revision
    asset = repository.save_ppt_revision(
        "course-1",
        "L1-1",
        {"title": "第一讲", "slides": [{"slide_id": "slide-1", "title": "封面", "body": []}]},
        source_lesson_plan_revision_id=source_revision,
    )
    assert asset["source_state"] == "current"
    assert asset["revisions"][0]["source_lesson_plan_revision_id"] == source_revision

    repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"lesson_title": "第一讲 v2", "sections": [{"node_id": "L2-1-1", "title": "1.1"}]},
        source_outline_revision_id="outline-v1",
        actor="teacher",
    )
    stale = repository.lesson("course-1", "L1-1")["ppt_assets"][0]
    assert stale["source_state"] == "stale"
    assert stale["revisions"][0]["deck"]["slides"][0]["title"] == "封面"


def test_teacher_lesson_v6_source_is_synthetic_and_covers_only_one_lesson():
    source = course_data()
    source_before = str(source)
    revision = {
        "revision_id": "plan-v1",
        "plan": {
            "revision_id": "plan-v1",
            "sections": [
                {
                    "node_id": "L2-1-1",
                    "learning_objective": "理解第一节",
                    "key_points": ["概念一"],
                    "teaching_modules": [{
                        "module_id": "core_explanation",
                        "teaching_purpose": "讲清概念一",
                        "knowledge_names": ["概念一"],
                    }],
                },
                {
                    "node_id": "L2-1-2",
                    "learning_objective": "理解第二节",
                    "key_points": ["概念二"],
                    "teaching_modules": [{
                        "module_id": "learner_action",
                        "teaching_purpose": "完成概念二练习",
                        "knowledge_names": ["概念二"],
                    }],
                },
            ],
        },
    }
    document, view, synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id="L1-1",
        plan_revision=revision,
    )
    graph = compile_course_presentation_graph(
        document,
        teaching_plan=view["course_teaching_plan"],
    )
    assert synthetic_id.startswith("teacher-lesson-")
    assert synthetic_id != source["course_id"]
    assert {section.section_id for section in document.sections} == {"L1-1", "L2-1-1", "L2-1-2"}
    assert {block.section_id for block in document.blocks} == {"L2-1-1", "L2-1-2"}
    assert graph.primary_block_coverage == 1.0
    assert graph.diagnostics == []
    assert str(source) == source_before


def test_ppt_ai_candidate_acceptance_creates_new_deck_revision(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"sections": [{"node_id": "L2-1-1"}]},
        source_outline_revision_id="outline-v1",
    )
    asset = repository.save_ppt_revision(
        "course-1",
        "L1-1",
        {"title": "第一讲", "slides": [{"slide_id": "slide-1", "title": "before", "body": []}]},
        source_lesson_plan_revision_id=lesson["working_revision_id"],
    )
    candidate = repository.save_ppt_ai_candidate(
        "course-1",
        "L1-1",
        asset_id=asset["asset_id"],
        base_revision_id=asset["working_revision_id"],
        instruction="优化封面",
        slide_indexes=[0],
        deck={"title": "第一讲", "slides": [{"slide_id": "slide-1", "title": "after", "body": []}]},
    )
    accepted = repository.resolve_ppt_ai_candidate(
        "course-1",
        "L1-1",
        candidate["candidate_id"],
        accept=True,
    )
    assert len(accepted["revisions"]) == 2
    assert accepted["revisions"][-1]["deck"]["slides"][0]["title"] == "after"


def test_teacher_lesson_api_generates_only_requested_lesson(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)

    class FakeCourseService:
        calls = []

        async def prepare_teacher_lesson_plan(self, *, course_data, lesson_unit_id, on_phase):
            self.calls.append(lesson_unit_id)
            await on_phase("lesson_plan_batch", 60, "生成中")
            scope = lesson_scope(course_data, lesson_unit_id)
            return {
                "plan": {
                    "sections": [
                        {"node_id": item["node_id"], "teaching_modules": []}
                        for item in scope["sections"]
                    ]
                },
                "warnings": [],
                "source_outline_revision_id": "outline-v1",
                "generation_source": "model",
            }

    class FakeTaskManager:
        storage = None
        course_service = FakeCourseService()

        @staticmethod
        def get_generation_workspace_course(course_id):
            assert course_id == "course-1"
            return {**course_data(), "blueprint_revision_id": "outline-v1"}

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository

    with TestClient(app) as client:
        view = client.get("/api/teacher/courses/course-1/lesson-authoring")
        assert view.status_code == 200
        assert [item["lesson_unit_id"] for item in view.json()["lessons"]] == ["L1-1", "L1-2"]

        response = client.post(
            "/api/teacher/courses/course-1/lessons/L1-2/plan/generate",
            json={"request_id": "lesson-two"},
        )
        assert response.status_code == 202
        job_id = response.json()["job"]["id"]
        for _ in range(50):
            job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{job_id}").json()["job"]
            if job["status"] in {"completed", "completed_with_warnings", "failed"}:
                break
            time.sleep(0.01)

    assert job["status"] == "completed"
    assert FakeTaskManager.course_service.calls == ["L1-2"]
    assets = repository.view("course-1")["lessons"]
    assert set(assets) == {"L1-2"}
    assert assets["L1-2"]["revisions"][0]["plan"]["sections"] == [
        {"node_id": "L2-2-1", "teaching_modules": []}
    ]
