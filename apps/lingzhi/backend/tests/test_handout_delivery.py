"""Handout scheduling, interruption durability and explicit downstream delivery."""
import asyncio
from types import SimpleNamespace

import pytest

from ai_base import AIBase
from ai_capacity import ProviderCapacityController, get_provider_capacity_controller, provider_request_schedule, reset_provider_capacity_controllers
from routers import teacher_lesson_authoring as routes
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringService
from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan


@pytest.mark.asyncio
async def test_queue_is_fair_across_users_and_courses_and_orders_lectures(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    capacity = ProviderCapacityController("isolated")
    held = await capacity.acquire("m")
    order = []
    async def request(actor, course, lecture, block=0):
        with provider_request_schedule(actor=actor, course=course, lecture=lecture, block=block):
            async with await capacity.acquire("m"):
                order.append((actor, course, lecture, block))
    inputs = [("a", "one", 3), ("a", "one", 1, 2), ("a", "one", 1, 1),
              ("a", "two", 1), ("a", "two", 2), ("b", "three", 1), ("c", "four", 1)]
    tasks = [asyncio.create_task(request(*args)) for args in inputs]
    cancelled = asyncio.create_task(request("cancelled", "gone", 0))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    await held.release()
    await asyncio.wait_for(asyncio.gather(*tasks), 1)
    assert {actor for actor, *_ in order[:3]} == {"a", "b", "c"}
    assert [(l, b) for a, c, l, b in order if c == "one"] == [(1, 1), (1, 2), (3, 0)]
    courses = [c for a, c, *_ in order if a == "a"]
    assert courses[:4] in (["one", "two", "one", "two"], ["two", "one", "two", "one"])
    assert courses[-1] == "one"
    assert capacity.snapshot()["queued"] == capacity.snapshot()["in_flight"] == 0


@pytest.mark.asyncio
async def test_adaptive_capacity_reduces_on_slow_streams_and_timeout(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "4")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "8")
    capacity = ProviderCapacityController("isolated")
    await capacity.report_success("m", duration_seconds=4, output_characters=1000, first_token_seconds=1)
    assert capacity.snapshot()["limit"] == 5
    for _ in range(2):
        await capacity.report_success("m", duration_seconds=20, output_characters=1000, first_token_seconds=1)
    assert capacity.snapshot()["limit"] == 4
    assert capacity.snapshot()["models"]["m"]["latency_reductions"] == 1
    await capacity.report_failure("m", failure_kind="transient")
    assert capacity.snapshot()["limit"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_real_request_deadline_excludes_queue_and_retains_partial_stream(monkeypatch, disconnect):
    monkeypatch.setenv("AI_API_KEY", "isolated-test-key")
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    ai = AIBase()
    monkeypatch.setattr(ai, "_models_for", lambda *args: ["isolated-model"])
    async def no_spacing():
        pass
    monkeypatch.setattr(ai, "_wait_for_request_slot", no_spacing)
    received, calls, closed = [], [], []
    class Stream:
        def __aiter__(self):
            return self.content()
        async def content(self):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="已收到的正文" * 30), finish_reason=None)])
            if disconnect:
                await asyncio.Event().wait()
        async def close(self):
            closed.append(True)
    async def create(**kwargs):
        calls.append(kwargs)
        return Stream()
    ai.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    capacity = get_provider_capacity_controller(ai._primary_provider_scope())
    held = await capacity.acquire("isolated-model")
    task = asyncio.create_task(ai._call_llm("test", retry_count=1, max_attempts=1,
        request_timeout_seconds=.025, raise_on_failure=True, on_content_delta=received.append))
    await asyncio.sleep(.06)  # Exceeds the active request deadline while queued.
    assert not calls and not task.done()
    await held.release()
    if disconnect:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task, 1)
    else:
        assert await asyncio.wait_for(task, 1) == "已收到的正文" * 30
    assert received == ["已收到的正文" * 30]
    assert len(calls) == len(closed) == 1
    assert capacity.snapshot()["in_flight"] == capacity.snapshot()["queued"] == 0


@pytest.mark.asyncio
async def test_live_queue_heartbeat_persists_fragments_and_prevents_false_expiry(tmp_path, monkeypatch):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    job = repo.create_job("course", "L1", job_type="teacher_lesson_script_generation")
    repo.update_job("course", job["id"], restart_whole=False)
    repo.update_job_stream("course", job["id"], phase="queued", progress=5, message="等待资源",
                           batch_id="shard:block", event="delta", delta="尚未完成的正文", block_id="block")
    monkeypatch.setattr(routes, "_TEACHER_JOB_HEARTBEAT_SECONDS", .005)
    gate = asyncio.Event()
    task = asyncio.create_task(routes._run_lesson_plan_job(course_id="course", job_id=job["id"], repository=repo, run=gate.wait), name=job["id"])
    repo.track_runtime_job("course", task)
    await asyncio.sleep(.03)
    assert repo.expire_stale_job("course", job["id"], stale_after_seconds=1)["status"] == "pending"
    reloaded = TeacherLessonAuthoringRepository(tmp_path).get_job("course", job["id"])
    assert reloaded["streamed_block_content"] == {"block": "尚未完成的正文"}
    gate.set()
    await task
    await routes.recover_teacher_generation_jobs(SimpleNamespace(), TeacherLessonAuthoringRepository(tmp_path))
    interrupted = TeacherLessonAuthoringRepository(tmp_path).get_job("course", job["id"])
    assert interrupted["status"] == "failed"
    assert interrupted["streamed_block_content"] == {"block": "尚未完成的正文"}


@pytest.mark.asyncio
async def test_duplicate_route_reuses_frozen_job_and_interruption_retains_text(tmp_path, monkeypatch):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    source = {**single_section_course_data(), "blueprint_revision_id": "outline-v1"}
    repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1")
    gate = asyncio.Event()
    calls = []
    class Service:
        async def generate_teacher_script_section(self, **kwargs):
            calls.append(kwargs)
            await kwargs["on_content_delta"]("没有换行的真实片段")
            await gate.wait()
            raise asyncio.TimeoutError("provider disconnected")
    tm = SimpleNamespace(storage=SimpleNamespace(load_course=lambda _: source), course_service=Service(),
                         get_generation_workspace_course=lambda _: None, get_generation_preview=lambda _: None)
    request = SimpleNamespace(headers={"X-User-Id": "teacher"})
    monkeypatch.setattr(routes, "_course_material_evidence", lambda *args: ([], []))
    first = await routes.generate_lesson_script("course-1", "L1-1", routes.GenerateLessonScriptRequest(request_id="one", requirements="原输入"), request, tm, repo)
    second = await routes.generate_lesson_script("course-1", "L1-1", routes.GenerateLessonScriptRequest(request_id="two", requirements="另一输入"), request, tm, repo)
    assert first["job"]["id"] == second["job"]["id"]
    assert second["job"]["requirements"] == "原输入"
    gate.set()
    tasks = list(repo._runtime_jobs["course-1"])
    await asyncio.gather(*tasks)
    saved = TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", first["job"]["id"])
    assert saved["status"] == "failed"
    assert len(calls) == 1
    assert list(saved["streamed_block_content"].values()) == ["没有换行的真实片段"]
    assert not saved.get("auto_recovery")
    assert not repo.lesson("course-1", "L1-1")["working_script_revision_id"]
