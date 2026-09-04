import asyncio
from types import SimpleNamespace

import pytest

from routers import courses
from routers import teacher_lesson_authoring as lesson_router
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


def test_course_preparation_status_requires_every_current_complete_asset():
    course = {
        "course_id": "course-1",
        "generation_request": {"teacher_course_brief": {"section_count": 99}},
    }
    lessons = {
        "lesson-1": {
            "working_revision_id": "plan-1",
            "source_state": "current",
            "revisions": [{
                "revision_id": "plan-1",
                "generation_source": "model",
                "plan": {"schema_version": "course_teaching_plan_v3", "sections": [{
                    "node_id": "section-1",
                    "teaching_modules": [{"module_id": "concept"}],
                }]},
            }],
            "working_script_revision_id": "handout-1",
            "script_revisions": [{
                "revision_id": "handout-1",
                "source_lesson_plan_revision_id": "plan-1",
                "sections": [{
                    "section_node_id": "section-1",
                    "content": "第一讲完整讲义",
                    "blocks": [{"block_id": "script-block-1"}],
                }],
            }],
            "ppt_assets": [{
                "working_representation_id": "ppt-1",
                "source_lesson_plan_revision_id": "plan-1",
                "source_script_revision_id": "handout-1",
                "source_state": "current",
            }],
        },
        "lesson-2": {
            "working_revision_id": "plan-2",
            "source_state": "current",
            "revisions": [{
                "revision_id": "plan-2",
                "generation_source": "model",
                "plan": {"schema_version": "course_teaching_plan_v3", "sections": [{
                    "node_id": "section-2",
                    "teaching_modules": [{"module_id": "application"}],
                }]},
            }],
            "working_script_revision_id": "handout-2",
            "script_revisions": [{
                "revision_id": "handout-2",
                "source_lesson_plan_revision_id": "plan-2",
                "sections": [{
                    "section_node_id": "section-2",
                    "content": "第二讲完整讲义",
                    "blocks": [{"block_id": "script-block-2"}],
                }],
            }],
            "ppt_assets": [{
                "working_representation_id": "ppt-2",
                "source_lesson_plan_revision_id": "plan-2",
                "source_script_revision_id": "handout-2",
                "source_state": "current",
            }],
        },
    }
    repository = SimpleNamespace(view=lambda _course_id: {
        "outline_revision_id": "outline-1",
        "lessons": lessons,
    })

    result = courses._teacher_preparation_projection(course, repository)

    assert result["preparation_state"] == "prepared"
    assert result["preparation_summary"] == {
        "planned_lessons": 2,
        "outline_ready": True,
        "ready_lesson_plans": 2,
        "ready_handouts": 2,
        "ready_ppts": 2,
    }

    lessons["lesson-2"]["script_revisions"][0]["source_lesson_plan_revision_id"] = "plan-old"
    assert courses._teacher_preparation_projection(course, repository)["preparation_state"] == "preparing"


def test_course_preparation_projects_the_latest_active_lesson_batch():
    repository = SimpleNamespace(view=lambda _course_id: {
        "outline_revision_id": "outline-1",
        "lessons": {},
        "jobs": {
            "old": {
                "id": "old",
                "type": "teacher_lesson_plan_generation",
                "status": "completed",
                "updated_at": "2026-09-01T09:00:00+00:00",
            },
            "lesson-1": {
                "id": "lesson-1",
                "parent_job_id": "batch-1",
                "type": "teacher_lesson_plan_generation",
                "lesson_unit_id": "lecture-1",
                "status": "completed",
                "progress": 100,
                "batch_position": 1,
                "batch_size": 3,
                "updated_at": "2026-09-02T09:00:00+00:00",
            },
            "lesson-2": {
                "id": "lesson-2",
                "parent_job_id": "batch-1",
                "type": "teacher_lesson_plan_generation",
                "lesson_unit_id": "lecture-2",
                "status": "running",
                "progress": 50,
                "message": "正在生成第 2 讲教案",
                "batch_position": 2,
                "batch_size": 3,
                "updated_at": "2026-09-02T09:01:00+00:00",
            },
            "lesson-3": {
                "id": "lesson-3",
                "parent_job_id": "batch-1",
                "type": "teacher_lesson_plan_generation",
                "lesson_unit_id": "lecture-3",
                "status": "pending",
                "progress": 0,
                "batch_position": 3,
                "batch_size": 3,
                "updated_at": "2026-09-02T09:00:30+00:00",
            },
        },
    })

    result = courses._teacher_preparation_projection(
        {"course_id": "course-1"},
        repository,
    )["preparation_summary"]["current_production"]

    assert result == {
        "target": "lesson_plan",
        "status": "running",
        "completed": 1,
        "total": 3,
        "failed": 0,
        "progress": 50,
        "current_lesson_ids": ["lecture-2", "lecture-3"],
        "message": "正在生成第 2 讲教案",
        "updated_at": "2026-09-02T09:01:00+00:00",
    }


def test_outline_review_findings_do_not_block_lesson_plan_entry():
    source = {
        "outline_framework_only": False,
        "generation_status": "outline_completed",
        "course_outline_quality_report": {
            "passed": False,
            "blockers": [{"code": "outline_editorial:hour_total_mismatch"}],
        },
        "generation_stage_artifacts": {
            "outline": {
                "strategy": "teacher_framework_then_lecture_tasks",
                "status": "completed",
            }
        },
        "nodes": [{"node_id": "L1-1", "node_name": "第一讲"}],
    }

    assert lesson_router._has_teaching_structure(source) is True
    assert lesson_router._has_teaching_structure({
        **source,
        "outline_framework_only": True,
        "generation_status": "outline_framework_ready",
    }) is False


def test_pause_keeps_checkpoint_and_marks_job_resumable(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path / "lesson-authoring")
    job = repository.create_job(
        "course-1",
        "lesson-1",
        request_id="request-1",
        source_outline_revision_id="outline-1",
    )
    repository.update_job(
        "course-1",
        job["id"],
        status="running",
        result_sections=[{"section_node_id": "section-1", "content": "已完成"}],
        completed_blocks=1,
        current_block_id="block-2",
    )

    paused = repository.pause_job("course-1", job["id"])

    assert paused["status"] == "paused"
    assert paused["pause_requested"] is True
    assert paused["retryable"] is True
    assert paused["checkpoint"]["completed_blocks"] == 1
    assert paused["checkpoint"]["result_sections"][0]["content"] == "已完成"


@pytest.mark.asyncio
async def test_generate_all_lesson_plans_returns_parent_and_independent_queue_metadata(monkeypatch):
    source = {"course_id": "course-1"}
    projected_lessons = [
        {
            "lesson_unit_id": "lesson-1",
            "title": "第一讲",
            "arrangement": {"confirmed": True, "blocks": [{"block_id": "b1"}]},
            "plan": {"can_generate": True},
        },
        {
            "lesson_unit_id": "lesson-2",
            "title": "第二讲",
            "arrangement": {"confirmed": True, "blocks": [{"block_id": "b2"}]},
            "plan": {"can_generate": True},
        },
    ]
    monkeypatch.setattr(lesson_router, "_source_course", lambda _tm, _course_id: source)
    monkeypatch.setattr(lesson_router, "_canonical_outline_revision", lambda _source: "outline-1")
    monkeypatch.setattr(lesson_router, "_lesson_projection", lambda _source, _repository: projected_lessons)
    monkeypatch.setattr(lesson_router, "validate_lesson_arrangement", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        lesson_router,
        "_lesson_plan_material_scope",
        lambda _course_id, _actor, lesson_id: {
            "source_package_id": f"package-{lesson_id}",
            "source_asset_id": f"source-{lesson_id}",
            "material_asset_ids": [f"material-{lesson_id}"],
        },
    )

    requested_children = []

    async def fake_generate(course_id, lesson_id, body, request, tm, repository):
        requested_children.append((lesson_id, body))
        return {"job": {
            "id": f"job-{lesson_id}",
            "lesson_unit_id": lesson_id,
            "type": "teacher_lesson_plan_generation",
            "status": "running",
            "progress": 0,
        }}

    monkeypatch.setattr(lesson_router, "generate_lesson_plan", fake_generate)

    class Repository:
        def view(self, _course_id):
            return {"jobs": {}}

        def current_arrangement(self, _course_id, _lesson_unit_id):
            return {}

        def update_job(self, course_id, job_id, **changes):
            return {
                "id": job_id,
                "course_id": course_id,
                "lesson_unit_id": job_id.removeprefix("job-"),
                "type": "teacher_lesson_plan_generation",
                "status": "running",
                **changes,
            }

    result = await lesson_router.generate_all_lesson_plans(
        "course-1",
        lesson_router.GenerateAllLessonPlansRequest(requirements="统一使用案例导入"),
        SimpleNamespace(headers={"X-User-Id": "teacher-1"}),
        SimpleNamespace(),
        Repository(),
    )

    assert result["parent_job"]["started"] == 2
    assert result["parent_job"]["child_job_ids"] == ["job-lesson-1", "job-lesson-2"]
    assert {job["batch_position"] for job in result["jobs"]} == {1, 2}
    assert len({job["parent_job_id"] for job in result["jobs"]}) == 1
    assert [body.batch_position for _, body in requested_children] == [1, 2]
    assert {body.batch_size for _, body in requested_children} == {2}
    assert len({body.batch_parent_job_id for _, body in requested_children}) == 1
    assert [body.source_asset_id for _, body in requested_children] == [
        "source-lesson-1",
        "source-lesson-2",
    ]
    assert [body.material_asset_ids for _, body in requested_children] == [
        ["material-lesson-1"],
        ["material-lesson-2"],
    ]


@pytest.mark.asyncio
async def test_lesson_plan_batch_resumes_only_paused_and_failed_lessons(monkeypatch):
    lessons = [
        {
            "lesson_unit_id": f"lesson-{index}",
            "title": f"第 {index} 讲",
            "sections": [{"section_node_id": f"section-{index}"}],
            "arrangement": {"confirmed": True, "blocks": [{"block_id": f"b-{index}"}]},
            "plan": {"ready": index <= 10, "can_generate": True},
        }
        for index in range(1, 13)
    ]
    prior_jobs = {
        "paused-job": {
            "id": "paused-job",
            "lesson_unit_id": "lesson-11",
            "type": "teacher_lesson_plan_generation",
            "status": "paused",
        },
        "failed-job": {
            "id": "failed-job",
            "lesson_unit_id": "lesson-12",
            "type": "teacher_lesson_plan_generation",
            "status": "failed",
        },
    }
    monkeypatch.setattr(lesson_router, "_source_course", lambda *_args: {"course_id": "course-1"})
    monkeypatch.setattr(lesson_router, "_canonical_outline_revision", lambda _source: "outline-1")
    monkeypatch.setattr(lesson_router, "_lesson_projection", lambda *_args: lessons)
    monkeypatch.setattr(lesson_router, "validate_lesson_arrangement", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        lesson_router,
        "_lesson_plan_material_scope",
        lambda *_args: {"source_package_id": "", "source_asset_id": "", "material_asset_ids": []},
    )
    requested_children = []

    async def fake_generate(course_id, lesson_id, body, *_args):
        requested_children.append((lesson_id, body))
        return {"job": {"id": f"new-{lesson_id}", "lesson_unit_id": lesson_id, "status": "pending"}}

    monkeypatch.setattr(lesson_router, "generate_lesson_plan", fake_generate)

    class Repository:
        def view(self, _course_id):
            return {"jobs": prior_jobs}

        def current_arrangement(self, _course_id, lesson_unit_id):
            return lessons[int(lesson_unit_id.split("-")[-1]) - 1]["arrangement"]

        def update_job(self, _course_id, job_id, **changes):
            lesson_id = job_id.removeprefix("new-")
            return {"id": job_id, "lesson_unit_id": lesson_id, "status": "pending", **changes}

    result = await lesson_router.generate_all_lesson_plans(
        "course-1",
        lesson_router.GenerateAllLessonPlansRequest(request_id="resume-plans"),
        SimpleNamespace(headers={"X-User-Id": "teacher-1"}),
        SimpleNamespace(),
        Repository(),
    )

    assert [lesson_id for lesson_id, _body in requested_children] == ["lesson-11", "lesson-12"]
    assert [body.resume_job_id for _lesson_id, body in requested_children] == [
        "paused-job",
        "failed-job",
    ]
    assert {body.batch_size for _lesson_id, body in requested_children} == {2}
    assert result["parent_job"]["started"] == 2
    assert result["parent_job"]["skipped_lesson_ids"] == [
        f"lesson-{index}" for index in range(1, 11)
    ]


@pytest.mark.asyncio
async def test_lesson_script_batch_resumes_only_paused_and_failed_lessons(monkeypatch):
    lessons = [
        {
            "lesson_unit_id": f"lesson-{index}",
            "script": {"ready": index <= 10, "can_generate": True},
        }
        for index in range(1, 13)
    ]
    prior_jobs = {
        "paused-script": {
            "id": "paused-script",
            "lesson_unit_id": "lesson-11",
            "type": "teacher_lesson_script_generation",
            "status": "paused",
        },
        "failed-script": {
            "id": "failed-script",
            "lesson_unit_id": "lesson-12",
            "type": "teacher_lesson_script_generation",
            "status": "failed",
        },
    }
    monkeypatch.setattr(lesson_router, "_source_course", lambda *_args: {"course_id": "course-1"})
    monkeypatch.setattr(lesson_router, "_lesson_projection", lambda *_args: lessons)
    monkeypatch.setattr(
        lesson_router,
        "_current_plan_revision",
        lambda _repository, _course_id, lesson_id: ({}, {"revision_id": f"plan-{lesson_id}"}),
    )
    monkeypatch.setattr(
        lesson_router,
        "_lesson_script_material_scope",
        lambda *_args: {"material_asset_ids": []},
    )
    requested_children = []

    async def fake_generate(course_id, lesson_id, body, *_args):
        requested_children.append((lesson_id, body))
        return {"job": {"id": f"new-{lesson_id}", "lesson_unit_id": lesson_id, "status": "pending"}}

    monkeypatch.setattr(lesson_router, "generate_lesson_script", fake_generate)

    class Repository:
        def view(self, _course_id):
            return {"jobs": prior_jobs}

    result = await lesson_router.generate_all_lesson_scripts(
        "course-1",
        lesson_router.GenerateAllLessonScriptsRequest(request_id="resume-scripts"),
        SimpleNamespace(headers={"X-User-Id": "teacher-1"}),
        SimpleNamespace(),
        Repository(),
    )

    assert [lesson_id for lesson_id, _body in requested_children] == ["lesson-11", "lesson-12"]
    assert [body.resume_job_id for _lesson_id, body in requested_children] == [
        "paused-script",
        "failed-script",
    ]
    assert {body.batch_size for _lesson_id, body in requested_children} == {2}
    assert result["parent_job"]["started"] == 2
    assert result["skipped_lesson_ids"] == [f"lesson-{index}" for index in range(1, 11)]


@pytest.mark.asyncio
async def test_lesson_plan_batch_allows_independent_model_jobs_to_overlap():
    class Repository:
        def get_job(self, _course_id, job_id):
            return {"id": job_id, "status": "pending"}

    active = 0
    peak_active = 0
    order = []
    both_started = asyncio.Event()

    def runner(label):
        async def run():
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            order.append(f"start:{label}")
            if active == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            order.append(f"end:{label}")
            active -= 1
        return run

    await lesson_router.asyncio.gather(
        lesson_router._run_lesson_plan_job(
            course_id="course-1",
            job_id="job-1",
            repository=Repository(),
            run=runner("lesson-1"),
        ),
        lesson_router._run_lesson_plan_job(
            course_id="course-1",
            job_id="job-2",
            repository=Repository(),
            run=runner("lesson-2"),
        ),
    )

    assert peak_active == 2
    assert set(order[:2]) == {"start:lesson-1", "start:lesson-2"}
