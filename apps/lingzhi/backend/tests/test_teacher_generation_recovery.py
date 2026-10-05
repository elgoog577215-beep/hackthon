"""Teacher delivery: internal recovery, usable drafts and hard boundaries."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from ai_base import AIProviderUnavailable
from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan
from course_generation.service import CourseService
from teacher_lesson_authoring import (
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    generation_failure,
    validate_teacher_lesson_plan,
)
from teacher_script import (
    SCRIPT_PIPELINE_VERSION,
    upgrade_script_quality_report,
)


@pytest.mark.parametrize("failure", [TimeoutError(), ValueError("JSON parse failed"), None])
def test_plan_recovers_in_original_job_and_publishes_once(tmp_path, failure):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    job = repo.create_job("course-1", "L1-1", request_id="recover", source_outline_revision_id="outline-v1")
    calls = []

    async def planner(course, lesson_id, on_progress):
        current = repo.get_job("course-1", job["id"])
        calls.append(current)
        assert current["status"] == "running" and current["error"] is None
        if len(calls) == 1:
            repo.update_job("course-1", job["id"], checkpoint={"saved_batch": "batch-1"})
            if failure is not None:
                raise failure
            return {"plan": {}}
        assert current["checkpoint"] == {"saved_batch": "batch-1"}
        return {"plan": standard_lesson_plan(), "generation_source": "model"}

    result = asyncio.run(TeacherLessonAuthoringService(repo).run_plan_job(
        course_id="course-1", lesson_unit_id="L1-1", job_id=job["id"],
        course_data=single_section_course_data(), planner=planner,
    ))
    assert result["status"] == "failed" and len(calls) == 1
    resumed, changed = repo.resume_lesson_generation("course-1", job["id"], input_fingerprint="")
    assert changed and resumed["id"] == job["id"]
    result = asyncio.run(TeacherLessonAuthoringService(repo).run_plan_job(
        course_id="course-1", lesson_unit_id="L1-1", job_id=job["id"],
        course_data=single_section_course_data(), planner=planner,
    ))
    assert result["status"] == "completed", result
    assert len(calls) == 2
    assert not result.get("auto_recovery")
    assert len(repo.view("course-1")["jobs"]) == 1
    assert len(repo.lesson("course-1", "L1-1")["revisions"]) == 1


@pytest.mark.parametrize("mode", ["exhausted", "unavailable", "conflict"])
def test_plan_failure_is_bounded_and_preserves_previous_revision(tmp_path, mode):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline("course-1", "outline-v1")
    old = repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1")
    job = repo.create_job("course-1", "L1-1", request_id="failing", source_outline_revision_id="outline-v1")
    calls = []

    async def planner(*_):
        calls.append(True)
        if mode == "unavailable":
            raise AIProviderUnavailable("credentials missing")
        if mode == "conflict":
            repo.set_outline("course-1", "outline-v2")
        raise TimeoutError("request timeout")

    result = asyncio.run(TeacherLessonAuthoringService(repo).run_plan_job(
        course_id="course-1", lesson_unit_id="L1-1", job_id=job["id"],
        course_data=single_section_course_data(), planner=planner,
    ))
    assert result["status"] == "failed"
    assert len(calls) == 1
    assert repo.lesson("course-1", "L1-1")["working_revision_id"] == old["working_revision_id"]
    if mode != "exhausted":
        assert not result["error"]["retryable"]


@pytest.mark.parametrize("status", ["paused", "cancelled"])
def test_stopping_task_during_recovery_never_restarts_it(tmp_path, status):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = repo.create_job("course-1", "L1-1", request_id="stop")
    calls = []

    async def planner(*_):
        calls.append(True)
        repo.update_job("course-1", job["id"], status=status)
        raise TimeoutError("request timeout")

    result = asyncio.run(TeacherLessonAuthoringService(repo).run_plan_job(
        course_id="course-1", lesson_unit_id="L1-1", job_id=job["id"],
        course_data=single_section_course_data(), planner=planner,
    ))
    assert result["status"] == status
    assert len(calls) == 1
    assert not repo.lesson("course-1", "L1-1")["working_revision_id"]






def test_auxiliary_plan_fields_are_advice_while_missing_teaching_content_blocks():
    plan = standard_lesson_plan()
    plan["formal_field_policy_version"] = "teacher_lesson_formal_fields_v1"
    plan["sections"][0]["teaching_notes"] = []
    report = validate_teacher_lesson_plan(plan)
    assert report["schema_version"] == "teacher_lesson_plan_quality_v2"
    assert report["passed"]
    assert {i["code"] for i in report["review_issues"]} >= {"lesson_plan:recommended_reading", "lesson_plan:teaching_notes"}
    plan["sections"][0]["teaching_modules"] = []
    assert not validate_teacher_lesson_plan(plan)["passed"]


@pytest.mark.parametrize("version", ["v8", "v9", "v10"])
def test_old_reports_reclassify_advice_without_erasing_real_failure(version):
    report = {"schema_version": f"teacher_script_quality_{version}", "pipeline_version": SCRIPT_PIPELINE_VERSION,
              "passed": False, "publication_eligible": False, "blocking_issues": [
                  {"code": "teacher_script:lesson_too_shallow"}, {"code": "teacher_script:block_empty"},
              ]}
    before = deepcopy(report)
    current = upgrade_script_quality_report(report)
    assert report == before
    assert current["schema_version"] == "teacher_script_quality_v12"
    assert not current["passed"]
    assert [i["code"] for i in current["blocking_issues"]] == ["teacher_script:block_empty"]
    assert current["review_issues"] == []


def test_old_speech_requirements_are_retired_without_hiding_content_failure():
    report = {
        "schema_version": "teacher_script_quality_v10",
        "pipeline_version": SCRIPT_PIPELINE_VERSION,
        "passed": False,
        "publication_eligible": False,
        "blocking_issues": [
            {"code": "teacher_script:not_directly_teachable"},
            {"code": "teacher_script:unclosed_math_delimiter"},
        ],
        "review_issues": [{"code": "teacher_script:missing_transition"}],
    }
    before = deepcopy(report)
    current = upgrade_script_quality_report(report)
    assert report == before
    assert current["passed"]
    assert current["publication_eligible"]
    assert current["blocking_issues"] == []
    assert current["review_issues"] == []
