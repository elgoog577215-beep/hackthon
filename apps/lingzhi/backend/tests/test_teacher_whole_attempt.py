"""Lesson retries keep each job independent and preserve atomic publication."""
import asyncio

import pytest

from backend.tests.test_teacher_lesson_authoring import standard_lesson_plan
from routers.teacher_lesson_authoring import _run_lesson_plan_job
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


def make_job(repo, lesson, *, batch="", size=1):
    job = repo.create_job("course-1", lesson, source_outline_revision_id="outline-v1")
    return repo.update_job("course-1", job["id"], restart_whole=True, parent_job_id=batch, batch_size=size)


def stage(repo, job, content="new"):
    plan = standard_lesson_plan()
    plan["generation_note"] = content
    repo.update_job("course-1", job["id"], status="running")
    result = repo.save_plan_revision("course-1", job["lesson_unit_id"], plan,
                                    source_outline_revision_id="outline-v1", active_job_id=job["id"])
    repo.update_job("course-1", job["id"], status="completed", result_revision_id=result["working_revision_id"])


def test_batch_retries_only_failed_child_and_publishes_each_lesson(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    jobs = [make_job(repo, lesson, batch="batch-1", size=2) for lesson in ["L1-1", "L1-2"]]
    calls = [0, 0]
    release_failed_child = asyncio.Event()

    async def run_one(index):
        calls[index] += 1
        current = repo.get_job("course-1", jobs[index]["id"])
        assert current.get("checkpoint") == {}
        assert not current.get("staged_lesson")
        if index == 1 and calls[index] == 1:
            await release_failed_child.wait()
            raise TimeoutError("provider timeout")
        stage(repo, jobs[index], f"attempt-{calls[index]}")

    async def execute():
        tasks = [
            asyncio.create_task(_run_lesson_plan_job(
                course_id="course-1",
                job_id=job["id"],
                repository=repo,
                run=lambda i=index: run_one(i),
            ))
            for index, job in enumerate(jobs)
        ]
        while repo.get_job("course-1", jobs[0]["id"])["status"] != "completed":
            await asyncio.sleep(0.01)
        assert repo.get_job("course-1", jobs[1]["id"])["status"] == "pending"
        assert repo.lesson("course-1", "L1-1")["working_revision_id"]
        assert not repo.lesson("course-1", "L1-2")["working_revision_id"]
        release_failed_child.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    asyncio.run(execute())
    assert calls == [1, 2]
    for index, job in enumerate(jobs):
        asset = repo.lesson("course-1", job["lesson_unit_id"])
        assert len(asset["revisions"]) == 1
        assert asset["revisions"][0]["plan"]["generation_note"] == f"attempt-{index + 1}"
        assert repo.get_job("course-1", job["id"])["status"] == "completed"


def test_staged_result_survives_reload_but_is_not_formal(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    old = repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1")
    job = make_job(repo, "L1-1")
    stage(repo, job)
    reloaded = TeacherLessonAuthoringRepository(tmp_path)
    assert reloaded.lesson("course-1", "L1-1") == old
    assert reloaded.get_job("course-1", job["id"])["phase"] == "result_ready"
    assert reloaded.publish_generation_attempt("course-1", [job["id"]])
    assert reloaded.lesson("course-1", "L1-1")["working_revision_id"] != old["working_revision_id"]


def test_pause_affects_only_selected_lesson(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    jobs = [make_job(repo, lesson, batch="batch-1", size=2) for lesson in ["L1-1", "L1-2"]]
    for job in jobs:
        stage(repo, job)
    repo.pause_job("course-1", jobs[0]["id"])
    paused = repo.get_job("course-1", jobs[0]["id"])
    sibling = repo.get_job("course-1", jobs[1]["id"])
    assert paused["status"] == "paused"
    assert paused["checkpoint"] == {}
    assert not paused.get("staged_lesson")
    assert sibling["status"] == "running"
    assert sibling["phase"] == "result_ready"
    assert repo.publish_generation_attempt("course-1", [jobs[1]["id"]])
    assert repo.get_job("course-1", jobs[1]["id"])["status"] == "completed"


def test_concurrent_edit_is_not_overwritten(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = make_job(repo, "L1-1")
    stage(repo, job)
    edited = repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1", actor="teacher")
    with pytest.raises(Exception, match="生成依据已变化"):
        repo.publish_generation_attempt("course-1", [job["id"]])
    assert repo.lesson("course-1", "L1-1") == edited


def test_retry_reset_is_once_per_attempt(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = make_job(repo, "L1-1")
    assert repo.reset_generation_attempt("course-1", [job["id"]], 0)
    assert not repo.reset_generation_attempt("course-1", [job["id"]], 0)
    assert repo.get_job("course-1", job["id"])["attempt_number"] == 1


def test_edit_during_model_call_is_not_overwritten(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = make_job(repo, "L1-1")
    edited = repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1", actor="teacher")
    stage(repo, job)
    with pytest.raises(Exception, match="生成依据已变化"):
        repo.publish_generation_attempt("course-1", [job["id"]])
    assert repo.lesson("course-1", "L1-1") == edited


def test_recovered_attempt_keeps_retry_due_and_count(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    old = make_job(repo, "L1-1")
    repo.update_job("course-1", old["id"], attempt_number=4, next_retry_at="2099-01-01T00:00:00+00:00")
    repo.pause_job("course-1", old["id"])
    new = repo.create_job("course-1", "L1-1")
    new = repo.update_job("course-1", new["id"], restart_whole=True, resume_from_job_id=old["id"])
    assert new["attempt_number"] == 5
    assert new["next_retry_at"] == "2099-01-01T00:00:00+00:00"
    assert new["checkpoint"] == {}


def test_cancel_affects_only_selected_lesson(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    jobs = [make_job(repo, x, batch="b", size=2) for x in ["L1-1", "L1-2"]]
    for job in jobs:
        stage(repo, job)
    repo.cancel_job("course-1", jobs[0]["id"])
    cancelled = repo.get_job("course-1", jobs[0]["id"])
    sibling = repo.get_job("course-1", jobs[1]["id"])
    assert cancelled["status"] == "cancelled"
    assert not cancelled.get("staged_lesson")
    assert sibling["status"] == "running"
    assert sibling["phase"] == "result_ready"
    assert repo.publish_generation_attempt("course-1", [jobs[1]["id"]])
    assert repo.get_job("course-1", jobs[1]["id"])["status"] == "completed"


def test_ppt_retry_uses_new_execution_and_same_confirmed_manuscript(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from routers import teacher_lesson_authoring as routes
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = make_job(repo, "L1-1")
    seen = []
    confirmed = object()
    async def build(**kw):
        seen.append(kw)
        if len(seen) == 1:
            raise TimeoutError("provider timeout")
        return {"status": "completed"}
    async def no_wait(_):
        pass
    monkeypatch.setattr(routes.asyncio, "sleep", no_wait)
    candidates = SimpleNamespace(clone_checkpoint=lambda *_: None)
    result = asyncio.run(routes._build_teacher_ppt_attempt(repository=repo, course_id="course-1", task_id=job["id"],
        orchestrator=SimpleNamespace(build=build, candidates=candidates), confirmed_manuscript=confirmed,
        source_revision_provider=lambda: "outline-v1"))
    assert result["status"] == "completed"
    assert seen[0]["task_id"] != seen[1]["task_id"]
    assert all(item["confirmed_manuscript"] is confirmed for item in seen)
