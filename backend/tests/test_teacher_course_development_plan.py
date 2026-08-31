from types import SimpleNamespace

import pytest

from routers import courses
from routers import teacher_lesson_authoring as lesson_router
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


def test_course_preparation_status_requires_every_confirmed_asset():
    course = {
        "course_id": "course-1",
        "generation_request": {"teacher_course_brief": {"section_count": 99}},
    }
    lessons = {
        "lesson-1": {
            "confirmed_revision_id": "plan-1",
            "script_confirmation": {
                "confirmed_revision_id": "handout-1",
                "source_state": "current",
            },
            "ppt_assets": [{
                "ppt_manuscript_status": "confirmed",
                "source_state": "current",
            }],
        },
        "lesson-2": {
            "confirmed_revision_id": "plan-2",
            "script_confirmation": {
                "confirmed_revision_id": "handout-2",
                "source_state": "current",
            },
            "ppt_assets": [{
                "confirmed_at": "2026-08-30T00:00:00Z",
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
        "outline_confirmed": True,
        "confirmed_lesson_plans": 2,
        "confirmed_handouts": 2,
        "confirmed_ppts": 2,
    }

    lessons["lesson-2"]["script_confirmation"]["source_state"] = "stale"
    assert courses._teacher_preparation_projection(course, repository)["preparation_state"] == "preparing"


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
async def test_generate_all_lesson_plans_returns_parent_and_serial_queue_metadata(monkeypatch):
    source = {"course_id": "course-1"}
    projected_lessons = [
        {
            "lesson_unit_id": "lesson-1",
            "title": "第一讲",
            "arrangement": {"confirmed": True, "blocks": [{"block_id": "b1"}]},
            "plan": {},
        },
        {
            "lesson_unit_id": "lesson-2",
            "title": "第二讲",
            "arrangement": {"confirmed": True, "blocks": [{"block_id": "b2"}]},
            "plan": {},
        },
    ]
    monkeypatch.setattr(lesson_router, "_source_course", lambda _tm, _course_id: source)
    monkeypatch.setattr(lesson_router, "_canonical_outline_revision", lambda _source: "outline-1")
    monkeypatch.setattr(lesson_router, "_lesson_projection", lambda _source, _repository: projected_lessons)

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


@pytest.mark.asyncio
async def test_lesson_plan_batch_runs_one_model_job_at_a_time():
    class Repository:
        def get_job(self, _course_id, job_id):
            return {"id": job_id, "status": "pending"}

    active = 0
    peak_active = 0
    order = []

    def runner(label):
        async def run():
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            order.append(f"start:{label}")
            await lesson_router.asyncio.sleep(0)
            order.append(f"end:{label}")
            active -= 1
        return run

    await lesson_router.asyncio.gather(
        lesson_router._run_lesson_plan_serially(
            course_id="course-1",
            job_id="job-1",
            repository=Repository(),
            run=runner("lesson-1"),
        ),
        lesson_router._run_lesson_plan_serially(
            course_id="course-1",
            job_id="job-2",
            repository=Repository(),
            run=runner("lesson-2"),
        ),
    )

    assert peak_active == 1
    assert order == ["start:lesson-1", "end:lesson-1", "start:lesson-2", "end:lesson-2"]
