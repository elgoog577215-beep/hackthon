"""Slow authoring storage must not occupy the HTTP/model event loop."""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from ai_base import AIProviderRequestError
from backend.tests.test_teacher_handout_lecture import fixture, new_job, response, BLOCK
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "disconnect", "publication_failure"])
async def test_handout_repository_work_never_runs_on_event_loop(tmp_path, monkeypatch, outcome):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    event_thread = threading.get_ident()
    calls = []
    for name in ("get_job", "update_job", "update_job_live", "update_job_stream", "save_script_revision"):
        original = getattr(repo, name)

        def recorded(*args, _original=original, _name=name, **changes):
            calls.append((_name, threading.get_ident()))
            if outcome == "publication_failure" and _name == "save_script_revision":
                raise OSError("disk unavailable during publication")
            return _original(*args, **changes)

        monkeypatch.setattr(repo, name, recorded)

    async def generate(**request):
        if outcome == "disconnect":
            text = "<!-- section:L2-1-1 -->\n" + BLOCK + "已完成小节\n<!-- section:L2-1-2 -->\n" + BLOCK + "收到的片段"
            await request["on_content_delta"](text)
            raise AIProviderRequestError("connection lost")
        text = response(["L2-1-1", "L2-1-2"])
        await request["on_scope"](["L2-1-1", "L2-1-2"])
        await request["on_content_reset"]()
        await request["on_content_delta"](text)
        return {"text": text}

    result = await service.run_script_job(**kwargs, job_id=jid, generator=generate)
    assert result["status"] == ("completed" if outcome == "completed" else "failed")
    assert calls
    assert not [name for name, thread in calls if thread == event_thread], "authoring I/O occupied the event loop"
    reloaded = TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", jid)
    assert reloaded["id"] == jid
    assert reloaded["result_sections"] == result["result_sections"]
    if outcome == "disconnect":
        assert "收到的片段" in reloaded["raw_response"]
    if outcome == "publication_failure":
        assert len(reloaded["result_sections"]) == 2


@pytest.mark.asyncio
async def test_handout_and_tree_checkpoint_share_store_without_stalling_observers(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    tree = repo.create_job("course-1", "tree", job_type="course_knowledge_tree_generation")
    original_save = repo._save
    loop_thread = threading.get_ident()
    saves = []
    ticks = []
    running = True

    def slow_save(value):
        saves.append(threading.get_ident())
        time.sleep(.06)
        return original_save(value)

    monkeypatch.setattr(repo, "_save", slow_save)

    async def observe():
        while running:
            ticks.append(time.monotonic())
            repo.read_knowledge_observation("course-1", lambda value: value["jobs"])
            await asyncio.sleep(.005)

    async def tree_checkpoint():
        for revision in range(3):
            await asyncio.to_thread(repo.update_job, "course-1", tree["id"], status="running",
                                    checkpoint={"atomic_pipeline": {"revision": revision}})

    async def generate(**request):
        text = response(["L2-1-1", "L2-1-2"])
        await request["on_content_delta"](text)
        return {"text": text}

    observer = asyncio.create_task(observe())
    try:
        result, _ = await asyncio.gather(
            service.run_script_job(**kwargs, job_id=jid, generator=generate), tree_checkpoint())
    finally:
        running = False
        await observer
    assert result["status"] == "completed"
    assert loop_thread not in saves, "one generator still persisted on the shared event loop"
    assert len(ticks) > 10
    assert max(b - a for a, b in zip(ticks, ticks[1:])) < .1
    fresh = TeacherLessonAuthoringRepository(tmp_path)
    assert fresh.get_job("course-1", tree["id"])["checkpoint"]["atomic_pipeline"]["revision"] == 2
    assert fresh.get_job("course-1", jid)["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_waits_for_inflight_save_and_keeps_the_same_durable_job(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    original_save = repo._save
    entered = threading.Event()
    released = threading.Event()
    finished = threading.Event()
    loop_thread = threading.get_ident()

    def slow_save(value):
        if threading.get_ident() != loop_thread and not entered.is_set():
            entered.set()
            assert released.wait(3)
        result = original_save(value)
        finished.set()
        return result

    monkeypatch.setattr(repo, "_save", slow_save)

    async def generate(**request):
        return {"text": response(["L2-1-1", "L2-1-2"])}

    task = asyncio.create_task(service.run_script_job(**kwargs, job_id=jid, generator=generate))
    try:
        for _ in range(100):
            if entered.is_set() or task.done():
                break
            await asyncio.sleep(.005)
        assert entered.is_set(), "no asynchronous durable write was reached"
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done(), "cancel returned while an orphan writer could still commit"
        task.cancel()
        await asyncio.sleep(.01)
        assert not task.done(), "a second cancellation detached the same writer"
    finally:
        released.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert finished.is_set()
    assert TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", jid)["id"] == jid


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_script_admission_and_publication_guards_stay_off_event_loop(tmp_path, monkeypatch, batch):
    from backend.tests.test_teacher_lesson_authoring import single_section_course_data, standard_lesson_plan
    from routers import teacher_lesson_authoring as routes

    repo = TeacherLessonAuthoringRepository(tmp_path)
    source = {**single_section_course_data(), "blueprint_revision_id": "outline-v1"}
    repo.save_plan_revision("course-1", "L1-1", standard_lesson_plan(), source_outline_revision_id="outline-v1")
    loop_thread = threading.get_ident()
    calls = []
    for name in ("view", "create_job", "update_job", "get_job"):
        original = getattr(repo, name)
        def recorded(*args, _name=name, _original=original, **kwargs):
            calls.append((_name, threading.get_ident()))
            return _original(*args, **kwargs)
        monkeypatch.setattr(repo, name, recorded)

    def material_evidence(*args):
        calls.append(("material_evidence", threading.get_ident()))
        return [], []

    monkeypatch.setattr(routes, "_course_material_evidence", material_evidence)
    monkeypatch.setattr(routes, "_capture_generation_source_snapshot", lambda **kwargs: None)
    class Provider:
        async def generate_teacher_handout(self, **kwargs):
            return {"text": response(["L2-1-1"])}

    tm = SimpleNamespace(storage=SimpleNamespace(load_course=lambda _: source), course_service=Provider(),
                         get_generation_workspace_course=lambda _: None, get_generation_preview=lambda _: None)
    request = SimpleNamespace(headers={"X-User-Id": "teacher"})
    if batch:
        result = await routes.generate_all_lesson_scripts("course-1", routes.GenerateAllLessonScriptsRequest(), request, tm, repo)
        jid = result["jobs"][0]["id"]
    else:
        result = await routes.generate_lesson_script("course-1", "L1-1", routes.GenerateLessonScriptRequest(), request, tm, repo)
        jid = result["job"]["id"]
    await asyncio.gather(*list(repo._runtime_jobs["course-1"]))
    assert not [name for name, thread in calls if thread == loop_thread], "admission/source guard blocked HTTP"
    assert TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", jid)["status"] == "completed"


@pytest.mark.asyncio
async def test_script_runner_error_cleanup_is_not_a_synchronous_save(tmp_path, monkeypatch):
    from routers.teacher_lesson_authoring import _run_lesson_plan_job

    repo, _, _ = fixture(tmp_path)
    jid = new_job(repo)
    original = repo.update_job
    threads = []
    def recorded(*args, **kwargs):
        threads.append(threading.get_ident())
        return original(*args, **kwargs)
    monkeypatch.setattr(repo, "update_job", recorded)

    async def broken():
        raise OSError("checkpoint could not be stored")

    await _run_lesson_plan_job(course_id="course-1", job_id=jid, repository=repo, run=broken)
    assert threading.get_ident() not in threads
    assert repo.get_job("course-1", jid)["status"] == "failed"


@pytest.mark.asyncio
async def test_provider_can_finish_receiving_while_checkpoint_disk_is_slow(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    save = repo._save
    receiving = False
    callback_seconds = []

    def slow_save(value):
        if receiving:
            time.sleep(.15)
        return save(value)

    monkeypatch.setattr(repo, "_save", slow_save)
    text = response(["L2-1-1", "L2-1-2"])
    async def generate(**request):
        nonlocal receiving
        receiving = True
        for chunk in [text[:90], text[90:140], text[140:]]:
            began = time.monotonic()
            await request["on_content_delta"](chunk)
            callback_seconds.append(time.monotonic() - began)
            await asyncio.sleep(.005)
        return {"text": text}

    result = await service.run_script_job(**kwargs, job_id=jid, generator=generate)
    assert result["status"] == "completed"
    assert max(callback_seconds) < .08, "provider receive path waited for a durable checkpoint"
    fresh = TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", jid)
    assert fresh["raw_response"] == text
    assert len(fresh["result_sections"]) == 2


@pytest.mark.asyncio
async def test_pause_keeps_received_text_even_if_stream_projection_is_waiting_for_disk(tmp_path, monkeypatch):
    repo, service, kwargs = fixture(tmp_path)
    jid = new_job(repo)
    text = "<!-- section:L2-1-1 -->\n" + BLOCK + "所有收到的文字"
    async def generate(**request):
        await request["on_content_delta"](text)
        # No wait for a projection, parsing pass, or periodic checkpoint.
        await asyncio.to_thread(repo.pause_job, "course-1", jid)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await service.run_script_job(**kwargs, job_id=jid, generator=generate)
    fresh = TeacherLessonAuthoringRepository(tmp_path).get_job("course-1", jid)
    assert fresh["status"] == "paused"
    assert fresh["raw_response"] == text
