"""Teacher delivery: internal recovery, usable drafts and hard boundaries."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from ai_base import AIProviderUnavailable
from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan
from course_generation.service import CourseService
from teacher_lesson_authoring import (
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    _quality_improves,
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
    assert result["status"] == "completed", result
    assert len(calls) == 2
    assert result["auto_recovery"]["lesson_plan"]["retries"] == 1
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
    assert len(calls) == (3 if mode == "exhausted" else 1)
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


@pytest.mark.parametrize("first_result", ["timeout", "empty"])
def test_script_retries_failed_unit_without_regenerating_successful_sibling(tmp_path, first_result):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    plan = standard_lesson_plan()
    plan["sections"][0]["teaching_modules"].append({"module_id": "summary", "planned_minutes": 2})
    lesson = repo.save_plan_revision("course-1", "L1-1", plan, source_outline_revision_id="outline-v1")
    outline = {"node_id": "L2-1-1", "node_name": "函数", "module_plan": [
        {"module_id": "core_explanation", "label": "概念"}, {"module_id": "summary", "label": "总结"},
    ]}
    job = repo.create_job("course-1", "L1-1", job_type="teacher_lesson_script_generation", request_id="script")
    counts = {}

    async def generator(_outline, _plan, module, _context):
        key = module["module_id"]
        counts[key] = counts.get(key, 0) + 1
        assert repo.get_job("course-1", job["id"])["status"] == "running"
        if key == "summary" and counts[key] == 1:
            if first_result == "empty":
                return ""
            raise TimeoutError("model timeout")
        return "请看函数定义：每个输入对应唯一输出。用两个输入检查对应关系，再说明它与一般关系的区别。"

    result = asyncio.run(TeacherLessonAuthoringService(repo).run_script_job(
        course_id="course-1", lesson_unit_id="L1-1", job_id=job["id"],
        source_plan_revision_id=lesson["working_revision_id"], outline_sections=[outline],
        plan_sections={"L2-1-1": plan["sections"][0]}, generator=generator,
    ))
    assert result["status"] == "completed", result
    assert counts == {"core_explanation": 1, "summary": 2}
    assert result["completed_blocks"] == 2
    assert len(repo.view("course-1")["jobs"]) == 1


def test_retry_budget_is_atomic_and_survives_repository_reload(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = repo.create_job("course-1", "L1-1", request_id="budget")
    error = generation_failure(TimeoutError(), "request_timeout")
    def reserve(unit):
        return repo.reserve_generation_retry("course-1", job["id"], unit, error)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(reserve, ["a", "b", "c", "d"])) == [1] * 4
    repo = TeacherLessonAuthoringRepository(tmp_path)
    assert set(repo.get_job("course-1", job["id"])["auto_recovery"]) == {"a", "b", "c", "d"}
    assert reserve("a") == 2
    assert reserve("a") == 0


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


@pytest.mark.parametrize("version", ["v8", "v9"])
def test_old_reports_reclassify_advice_without_erasing_real_failure(version):
    report = {"schema_version": f"teacher_script_quality_{version}", "pipeline_version": SCRIPT_PIPELINE_VERSION,
              "passed": False, "publication_eligible": False, "blocking_issues": [
                  {"code": "teacher_script:lesson_too_shallow"}, {"code": "teacher_script:block_empty"},
              ]}
    before = deepcopy(report)
    current = upgrade_script_quality_report(report)
    assert report == before
    assert current["schema_version"] == "teacher_script_quality_v10"
    assert not current["passed"]
    assert [i["code"] for i in current["blocking_issues"]] == ["teacher_script:block_empty"]
    assert current["review_issues"] == [{"code": "teacher_script:lesson_too_shallow"}]


def test_quality_improvement_prioritizes_real_failure_over_new_advice():
    assert _quality_improves({"blocking_issues": [], "review_issues": [{"code": "style"}]},
                             {"blocking_issues": [{"code": "empty"}]})
    assert not _quality_improves({"blocking_issues": [{"code": "empty"}]},
                                 {"review_issues": [{"code": "style"}]})


def test_optional_script_optimization_timeout_keeps_usable_draft(monkeypatch):
    service = CourseService()
    calls = []
    async def model(*_, **__):
        calls.append(True)
        if len(calls) > 1:
            raise TimeoutError("optional optimization timeout")
        return "## 概念\n\n" + "函数为每个输入指定唯一输出，对应关系满足单值条件。" * 8
    monkeypatch.setattr(service, "_call_llm", model)
    result = asyncio.run(service.generate_teacher_script_section(
        course_id="isolated-test", outline_section={"node_id": "s", "module_plan": [{"module_id": "core_explanation", "label": "概念"}]},
        current_plan_section={"node_id": "s", "teaching_modules": [{"module_id": "core_explanation"}]},
    ))
    assert result["quality_report"]["passed"]
    assert result["quality_report"]["review_issues"]
    assert len(calls) == 2
