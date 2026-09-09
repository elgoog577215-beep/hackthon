"""Whole-course scans must survive model envelope failures without losing work."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_teacher_change_durable import fixture
from course_evolution.teacher_planning import TeacherCourseChangeUnit, create_teacher_course_change_plan
from course_generation.service import CourseService


def response(candidates, patches=None):
    return {
        "signal_kind": "semantic",
        "affected_units": [{"unit_id": c["unit_id"], "content_patches": patches} for c in candidates],
        "structure": {"required": False},
    }


def scan_context(tmp_path, *, long=False):
    _, _, repo, context = fixture(tmp_path)
    context.units = [TeacherCourseChangeUnit(
        unit_id=f"u{i}", asset_type="lesson_plan", unit_type="lesson_plan_section",
        title=f"Lecture {i}", text="a" * (16000 if long else 3900), source_revision="r1",
    ) for i in range(1 if long else 4)]
    return repo, context


@pytest.mark.asyncio
async def test_repeated_unit_with_null_patches_does_not_abort_analysis(tmp_path):
    repo, context = scan_context(tmp_path, long=True)
    async def analyze(overview, candidates, instruction):
        return response(candidates)
    state = await create_teacher_course_change_plan(
        context=context, user_id="teacher", request_id="null", instruction="Add practice",
        repository=repo, analyzer=analyze,
    )
    assert state.change_sets[-1].impact_summary["coverage"]["scanned_units"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [{"affected_units": 1}, {"affected_units": {}}, {},
    {"affected_units": [{"unit_id": "not-in-this-batch"}]}])
async def test_invalid_envelope_blocks_only_its_scan_instead_of_crashing_or_passing(tmp_path, malformed):
    repo, context = scan_context(tmp_path)
    async def analyze(*args):
        return deepcopy(malformed)
    state = await create_teacher_course_change_plan(
        context=context, user_id="teacher", request_id="bad", instruction="Add practice",
        repository=repo, analyzer=analyze,
    )
    plan = state.change_sets[-1]
    assert plan.teacher_change_planning.status == "blocked"
    assert plan.impact_summary["coverage"]["scanned_units"] == 0
    assert plan.impact_summary["coverage"]["failed_batches"]


@pytest.mark.asyncio
async def test_resume_reuses_successful_parts_and_invalidates_changed_input(tmp_path):
    repo, context = scan_context(tmp_path)
    checkpoint, events, calls = {}, [], []
    async def progress(detail, saved):
        checkpoint.clear()
        checkpoint.update(deepcopy(saved))
        events.append(deepcopy(detail))
    async def flaky(overview, candidates, instruction):
        calls.append([c["unit_id"] for c in candidates])
        if any(c["unit_id"] == "u3" for c in candidates):
            raise TimeoutError("provider timeout")
        return response(candidates, [])
    state = await create_teacher_course_change_plan(
        context=context, user_id="teacher", request_id="first", instruction="Add practice",
        repository=repo, analyzer=flaky, scan_checkpoint={}, on_scan_progress=progress,
    )
    plan = state.change_sets[-1]
    assert plan.teacher_change_planning.status == "blocked"
    assert checkpoint["results"]
    calls.clear()
    async def healthy(overview, candidates, instruction):
        calls.extend(c["unit_id"] for c in candidates)
        return response(candidates, [])
    result = await create_teacher_course_change_plan(
        context=context, user_id="teacher", request_id="resume", instruction="Add practice",
        repository=repo, analyzer=healthy, supersedes_plan_id=plan.change_set_id,
        scan_checkpoint=deepcopy(checkpoint), on_scan_progress=progress,
    )
    assert calls == ["u3"]
    assert result.change_sets[-1].impact_summary["coverage"]["scanned_units"] == 4
    assert events[-1]["completed_parts"] == events[-1]["total_parts"]
    assert events[-1]["reused_parts"] == 3
    for change in ("instruction", "revision", "content"):
        calls.clear()
        updated = context.model_copy(deep=True)
        if change == "revision":
            updated.base_revision_vector["teacher_outline"] = "new-revision"
        if change == "content":
            updated.units[0].text += "changed"
        await create_teacher_course_change_plan(
            context=updated, user_id="teacher", request_id=change,
            instruction="Different goal" if change == "instruction" else "Add practice",
            repository=repo, analyzer=healthy, scan_checkpoint=deepcopy(checkpoint),
        )
        assert set(calls) == {"u0", "u1", "u2", "u3"}


@pytest.mark.asyncio
async def test_provider_error_is_not_replaced_by_missing_json():
    async def llm(*args, **kwargs):
        if kwargs.get("raise_on_failure"):
            raise TimeoutError("provider timeout")
        return None
    service = SimpleNamespace(_call_llm=llm, _extract_json=lambda value: None)
    with pytest.raises(TimeoutError, match="provider timeout"):
        await CourseService.analyze_teacher_course_change(service, {}, [], "Add practice")


@pytest.mark.asyncio
async def test_job_keeps_private_checkpoint_on_failure_and_uses_it_on_retry(tmp_path, monkeypatch):
    from backend.tests.test_task_manager_runtime_durability import build_manager
    from course_evolution.jobs import enqueue_analysis, run_analysis
    manager = build_manager(tmp_path, monkeypatch)
    saved = {"signature": "fixture", "results": {"batch": {"affected_units": []}}}
    async def fail_after_checkpoint(**kwargs):
        await kwargs["on_scan_progress"](
            {"completed_parts": 1, "total_parts": 2, "reused_parts": 0, "failed_parts": 0}, saved,
        )
        raise RuntimeError("failure after scan")
    task = await enqueue_analysis(manager=manager, user_id="teacher", course_id="course-1",
        request_id="first-job", instruction="Add practice")
    await run_analysis(manager, task["id"], service=SimpleNamespace(create_teacher_plan=fail_after_checkpoint))
    assert manager.tasks[task["id"]]["analysis_checkpoint"] == saved
    assert "analysis_checkpoint" not in manager.get_task_summary(task["id"])
    assert manager._tasks_for_persistence()[task["id"]]["analysis_checkpoint"] == saved
    assert manager.tasks[task["id"]]["phase_detail"]["scan"]["completed_parts"] == 1
    async def capture(**kwargs):
        assert kwargs["scan_checkpoint"] == saved
        return SimpleNamespace(change_sets=[SimpleNamespace(
            impact_summary={"request_id": "retry-job"}, change_set_id="recovered-plan")])
    retry = await enqueue_analysis(manager=manager, user_id="teacher", course_id="course-1",
        request_id="retry-job", instruction="Add practice")
    await run_analysis(manager, retry["id"], service=SimpleNamespace(create_teacher_plan=capture))
    assert manager.get_task_summary(retry["id"])["status"] == "completed"
