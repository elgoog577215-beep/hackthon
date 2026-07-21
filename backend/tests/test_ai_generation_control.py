import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from course_context import CourseContextManager
from course_pedagogy import PedagogyMode
from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceNotFound, GenerationWorkspaceRepository
from learning_asset_storage import LearningAssetRepository
from material_storage import MaterialRepository
from course_generation_budget import CourseGenerationDeadlineExceeded
from task_manager import DEFAULT_MAX_CONCURRENCY, TaskManager, TaskStateConflict
from websocket_service import WebSocketService


class FakeCourseStorage:
    def __init__(self, course_data):
        self.course_data = course_data
        self.saved_course_id = None
        self.saved_data = None

    def load_course(self, course_id):
        return self.course_data

    async def save_course(self, course_id, data):
        self.saved_course_id = course_id
        self.saved_data = data


class DurableCourseStorage:
    def __init__(self):
        self.courses = {}

    def load_course(self, course_id):
        return self.courses.get(course_id)

    async def save_course(self, course_id, data):
        self.courses[course_id] = data

    def delete_course(self, course_id):
        self.courses.pop(course_id, None)


def _lifecycle_manager(tmp_path, monkeypatch):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = DurableCourseStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        version_repository=CourseVersionRepository(tmp_path / "versions"),
        asset_repository=LearningAssetRepository(tmp_path / "assets"),
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
    )
    return manager, storage, workspaces


async def _durable_generation_manager(tmp_path, monkeypatch, *, status):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = DurableCourseStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    documents = CourseDocumentRepository(storage)
    course = {
        "course_id": "c1",
        "course_name": "恢复测试",
        "course_blueprint": {"nodes": ["n1"]},
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "节点",
            "node_content": "",
            "node_content_draft": "已保存草稿",
            "generation_status": "error" if status == "failed" else "generating",
        }],
    }
    await documents.create_generation_shell(
        "c1", title="恢复测试", job_id="t1", metadata=course
    )
    workspaces.create("t1", course_id="c1", course_data=course)
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    manager.save_tasks = lambda: None
    manager.tasks["t1"] = {
        "id": "t1",
        "course_id": "c1",
        "type": "course_generation",
        "status": status,
        "phase": "content_generation",
        "progress": 55,
        "current_nodes": [{"node_id": "n1"}],
        "current_node_name": "节点",
        "workspace_id": "t1",
    }
    return manager


def test_task_manager_uses_provider_safe_default_concurrency():
    manager = TaskManager(storage=None, course_service=None, ws_service=None)

    assert manager.max_concurrency == DEFAULT_MAX_CONCURRENCY
    assert manager.max_concurrency == 4


@pytest.mark.asyncio
async def test_course_jobs_respect_global_course_concurrency():
    manager = TaskManager(
        storage=None,
        course_service=None,
        ws_service=None,
        max_course_concurrency=2,
    )
    active = 0
    peak = 0

    async def fake_process(_task_id):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    manager._process_task = fake_process
    await asyncio.gather(*(manager._run_job(f"t{index}") for index in range(3)))

    assert peak == 2


@pytest.mark.asyncio
async def test_pause_cancels_active_calls_and_resume_requeues_same_job(tmp_path, monkeypatch):
    manager = await _durable_generation_manager(tmp_path, monkeypatch, status="running")
    job = asyncio.create_task(asyncio.sleep(60))
    node = asyncio.create_task(asyncio.sleep(60))
    manager._running_job_tasks["t1"] = job
    manager._running_node_tasks["t1"] = {"n1": node}

    await manager.pause_task("t1")
    await asyncio.sleep(0)

    assert manager.tasks["t1"]["status"] == "paused"
    assert job.cancelled()
    assert node.cancelled()

    await manager.resume_task("t1")
    assert manager.tasks["t1"]["status"] == "pending"
    assert await manager._task_queue.get() == "t1"


@pytest.mark.asyncio
async def test_pause_rejects_missing_and_terminal_tasks():
    manager = TaskManager(storage=None, course_service=None, ws_service=None)

    with pytest.raises(KeyError):
        await manager.pause_task("missing")

    manager.tasks["done"] = {"id": "done", "status": "completed"}
    with pytest.raises(TaskStateConflict) as exc_info:
        await manager.pause_task("done")
    assert exc_info.value.status == "completed"


def test_find_active_task_never_falls_back_to_terminal_history():
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager.tasks = {}
    manager.tasks["done"] = {
        "id": "done",
        "course_id": "course-1",
        "status": "completed_with_warnings",
        "updated_at": "2026-07-15T00:00:00",
    }

    assert manager._find_active_task("course-1") is None


@pytest.mark.asyncio
async def test_delete_running_initial_job_cleans_shell_workspace_and_runtime(
    tmp_path, monkeypatch
):
    manager, storage, workspaces = _lifecycle_manager(tmp_path, monkeypatch)
    job = await manager.create_generation_job({"subject": "生命周期测试"})
    task_id = job["task_id"]
    course_id = job["course_id"]
    running = asyncio.create_task(asyncio.sleep(60))
    manager._running_job_tasks[task_id] = running

    await manager.delete_task(task_id)

    assert running.cancelled()
    assert task_id not in manager.tasks
    assert storage.load_course(course_id) is None
    with pytest.raises(GenerationWorkspaceNotFound):
        workspaces.load(task_id)


@pytest.mark.asyncio
async def test_delete_task_preserves_already_published_course(tmp_path, monkeypatch):
    manager, storage, workspaces = _lifecycle_manager(tmp_path, monkeypatch)
    job = await manager.create_generation_job({"subject": "已发布课程"})
    task_id = job["task_id"]
    course_id = job["course_id"]
    published = storage.load_course(course_id)
    published["generation_status"] = "completed_with_warnings"
    published["course_document_publication"] = {"job_id": task_id}
    await storage.save_course(course_id, published)

    await manager.delete_task(task_id)

    assert storage.load_course(course_id)["course_document_publication"]["job_id"] == task_id
    assert task_id not in manager.tasks
    with pytest.raises(GenerationWorkspaceNotFound):
        workspaces.load(task_id)


@pytest.mark.asyncio
async def test_delete_course_cascades_running_job_before_formal_course(
    tmp_path, monkeypatch
):
    manager, storage, workspaces = _lifecycle_manager(tmp_path, monkeypatch)
    job = await manager.create_generation_job({"subject": "级联删除测试"})
    task_id = job["task_id"]
    course_id = job["course_id"]
    running = asyncio.create_task(asyncio.sleep(60))
    manager._running_job_tasks[task_id] = running

    removed = await manager.delete_course(course_id)

    assert removed == 1
    assert running.cancelled()
    assert storage.load_course(course_id) is None
    assert task_id not in manager.tasks
    with pytest.raises(GenerationWorkspaceNotFound):
        workspaces.load(task_id)


@pytest.mark.asyncio
async def test_generation_creation_failure_rolls_back_shell_and_workspace(
    tmp_path, monkeypatch
):
    manager, storage, workspaces = _lifecycle_manager(tmp_path, monkeypatch)
    manager.create_task = AsyncMock(side_effect=OSError("tasks persistence failed"))

    with pytest.raises(OSError, match="tasks persistence failed"):
        await manager.create_generation_job({"subject": "补偿事务测试"})

    assert storage.courses == {}
    assert list(workspaces.root_dir.glob("*.json")) == []


@pytest.mark.asyncio
async def test_generation_creation_is_idempotent_for_same_request_id(
    tmp_path, monkeypatch
):
    manager, storage, workspaces = _lifecycle_manager(tmp_path, monkeypatch)
    request = {"request_id": "request-course-0001", "subject": "幂等课程"}

    first, second = await asyncio.gather(
        manager.create_generation_job(request),
        manager.create_generation_job(request),
    )

    assert first["task_id"] == second["task_id"]
    assert first["course_id"] == second["course_id"]
    assert second["deduplicated"] is True
    assert len(manager.tasks) == 1
    assert len(storage.courses) == 1
    assert len(list(workspaces.root_dir.glob("*.json"))) == 1


@pytest.mark.asyncio
async def test_failed_job_can_resume_same_course_after_provider_recovery(tmp_path, monkeypatch):
    manager = await _durable_generation_manager(tmp_path, monkeypatch, status="failed")
    manager.tasks["t1"]["error"] = "provider unavailable"
    manager.tasks["t1"]["progress"] = 100
    manager._node_retries["t1"] = {"n1": 3}

    await manager.resume_task("t1")

    task = manager.tasks["t1"]
    assert task["status"] == "pending"
    assert task["phase"] == "content_generation"
    assert task["progress"] == 50
    assert task["error"] is None
    assert manager._node_retries["t1"] == {}
    assert await manager._task_queue.get() == "t1"


@pytest.mark.asyncio
async def test_generation_job_migrates_inline_material_without_persisting_content(tmp_path, monkeypatch):
    import task_manager as task_manager_module

    tasks_file = tmp_path / "tasks.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tasks_file)

    class Storage:
        def __init__(self):
            self.courses = {}

        def load_course(self, course_id):
            return self.courses.get(course_id, {})

        async def save_course(self, course_id, data):
            self.courses[course_id] = data

    class CourseService:
        def __init__(self):
            self._material_repository = MaterialRepository(tmp_path / "materials")

    storage = Storage()
    manager = TaskManager(
        storage,
        CourseService(),
        None,
        workspace_repository=GenerationWorkspaceRepository(tmp_path / "workspaces"),
        document_repository=CourseDocumentRepository(storage),
    )
    job = await manager.create_generation_job({
        "subject": "Calculus",
        "materials": [{
            "filename": "notes.md",
            "content": "# Derivative\nA derivative is an instantaneous rate of change.",
            "usage": "content_source",
            "importance": "core",
        }],
    })

    task = manager.tasks[job["task_id"]]
    snapshot = task["request_snapshot"]
    assert snapshot["materials"] == []
    assert snapshot["material_bindings"][0]["asset_id"].startswith("mat-")
    assert "instantaneous rate of change" not in json.dumps(snapshot)
    assert tasks_file.exists()


@pytest.mark.asyncio
async def test_progress_update_shows_active_node_work():
    ws = AsyncMock()
    manager = TaskManager(storage=None, course_service=None, ws_service=ws)
    manager.tasks["t1"] = {
        "course_id": "c1",
        "status": "running",
        "progress": 25,
        "current_node_name": "1.2 发展历程",
        "current_nodes": [{
            "node_id": "L2-1-2",
            "node_name": "1.2 发展历程",
            "generated_chars": 128,
        }],
        "completed_nodes": 1,
        "total_nodes": 4,
    }

    await manager._push_progress("t1")

    payload = ws.push_progress_update.await_args.args[1]
    assert payload["progress"] > 25
    assert payload["bytes_generated"] == 128
    assert payload["current_nodes"][0]["generated_chars"] == 128


@pytest.mark.asyncio
async def test_task_completed_payload_carries_final_progress():
    ws = AsyncMock()
    course_data = {
        "course_id": "c1",
        "course_name": "测试课程",
        "nodes": [
            {"node_level": 1, "generation_status": "completed"},
            {
                "node_level": 2,
                "generation_status": "completed",
                "node_content": "x" * 700,
            },
        ],
    }
    manager = TaskManager(
        storage=FakeCourseStorage(course_data),
        course_service=None,
        ws_service=ws,
    )
    manager.save_tasks = lambda: None
    manager.tasks["t1"] = {
        "course_id": "c1",
        "status": "running",
        "progress": 90,
        "completed_nodes": 0,
        "total_nodes": 0,
        "current_nodes": [],
    }

    await manager._complete_task("t1", course_data)

    payload = ws.push_task_completed.await_args.args[1]
    assert payload["progress"] == 100
    assert payload["completed_nodes"] == 2
    assert payload["total_nodes"] == 2


def test_course_context_ledger_includes_blueprint_contract():
    plan = {
        "course_title": "机器学习入门",
        "learning_objectives": ["理解监督学习"],
        "prerequisites": ["线性代数"],
        "chapters": [{
            "chapter_number": 1,
            "title": "基础",
            "learning_focus": "建立基本概念",
            "sections": [{
                "section_number": "1.1",
                "title": "监督学习",
                "key_points": ["训练数据"],
                "learning_objective": "能解释监督学习任务",
                "prerequisite_node_ids": [],
                "misconceptions": ["监督学习不是人工监督每一步"],
                "assessment": ["能判断分类与回归"],
                "scope_boundary": "不展开深度学习模型",
            }],
        }],
    }

    manager = CourseContextManager()
    context = manager.create_from_plan(
        "c1", plan, PedagogyMode.PROGRAMMING_ENGINEERING
    )
    ledger = context.get_ledger_context("L2-1-1")

    assert "课程上下文账本" in ledger
    assert "能解释监督学习任务" in ledger
    assert "监督学习不是人工监督每一步" in ledger
    assert "不展开深度学习模型" in ledger


@pytest.mark.asyncio
async def test_schedule_nodes_treats_prerequisites_as_learning_order_only():
    started = []
    both_started = asyncio.Event()
    manager = TaskManager(storage=None, course_service=None, ws_service=None, max_concurrency=2)

    async def fake_process(_task_id, node):
        started.append(node["node_id"])
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.2)
        node["generation_status"] = "completed"

    manager._process_node = fake_process
    manager._is_content_complete = lambda _node: False

    await manager._schedule_nodes("t1", [
        {"node_id": "L2-1-2", "node_level": 2, "prerequisite_node_ids": ["L2-1-1"]},
        {"node_id": "L2-1-1", "node_level": 2},
    ])

    assert started == ["L2-1-2", "L2-1-1"]


@pytest.mark.asyncio
async def test_content_stage_has_no_fixed_wall_clock_deadline():
    manager = TaskManager(
        storage=None,
        course_service=None,
        ws_service=None,
        max_concurrency=2,
    )
    completed = []

    async def fake_process(_task_id, node):
        await asyncio.sleep(0.03)
        completed.append(node["node_id"])

    manager._process_node = fake_process
    manager._is_content_complete = lambda _node: False

    settled = await manager._schedule_nodes(
        "t1",
        [
            {"node_id": "L2-1-1", "node_level": 2},
            {"node_id": "L2-1-2", "node_level": 2},
        ],
    )

    assert settled is True
    assert completed == ["L2-1-1", "L2-1-2"]
    assert not hasattr(manager, "_content_stage_timeout_seconds")


@pytest.mark.asyncio
async def test_content_stream_keeps_running_while_chunks_continue():
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager._content_inactivity_timeout_seconds = 0.02
    activity = asyncio.Event()

    async def progressing_stream():
        for _ in range(4):
            await asyncio.sleep(0.012)
            activity.set()
        return "持续生成完成"

    result = await manager._await_content_progress(
        "持续输出小节",
        progressing_stream(),
        activity,
    )

    assert result == "持续生成完成"


@pytest.mark.asyncio
async def test_content_stream_stops_after_real_inactivity():
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager._content_inactivity_timeout_seconds = 0.01
    activity = asyncio.Event()
    cancelled = asyncio.Event()

    async def stalled_stream():
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "不会到达"

    with pytest.raises(CourseGenerationDeadlineExceeded, match="没有新内容"):
        await manager._await_content_progress(
            "卡住的小节",
            stalled_stream(),
            activity,
        )

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_websocket_node_finalized_message(monkeypatch):
    sent = []
    service = WebSocketService()

    async def fake_send(_course_id, message):
        sent.append(message)

    monkeypatch.setattr(service, "_send_to_subscribers", fake_send)

    await service.push_node_finalized("c1", {
        "task_id": "t1",
        "node_id": "L2-1-1",
        "node_content": "final",
    })

    assert sent[0]["type"] == "node_finalized"
    assert sent[0]["payload"]["node_content"] == "final"


@pytest.mark.asyncio
async def test_save_generated_node_content_marks_node_completed():
    storage = FakeCourseStorage({
        "nodes": [{
            "node_id": "L2-1-1",
            "node_content": "",
            "generation_status": "generating",
            "generated_chars": 0,
            "error_summary": "old error",
        }]
    })
    manager = TaskManager(storage=storage, course_service=None, ws_service=None)
    manager.tasks["t1"] = {"id": "t1", "course_id": "c1", "status": "running"}

    data = await manager._save_generated_node_content(
        "t1",
        "c1",
        "L2-1-1",
        "final content",
        13,
    )

    node = data["nodes"][0]
    assert storage.saved_course_id == "c1"
    assert node["node_content"] == "## 正文\n\nfinal content"
    assert len(node["content_blocks"]) == 1
    assert node["content_blocks"][0]["block_revision_id"].startswith("cbr_")
    assert node["generation_status"] == "completed"
    assert node["generated_chars"] == 13
    assert node["error_summary"] is None


@pytest.mark.asyncio
async def test_publish_node_completion_keeps_websocket_payloads():
    ws = AsyncMock()
    manager = TaskManager(storage=None, course_service=None, ws_service=ws)

    await manager._publish_node_completion(
        "c1",
        "t1",
        {"node_id": "L2-1-1", "node_name": "1.1 导数定义"},
        "final content",
        13,
        content_blocks=[{"block_id": "L2-1-1-1-intro", "block_revision_id": "cbr_1"}],
    )

    finalized_payload = ws.push_node_finalized.await_args.args[1]
    completed_payload = ws.push_node_completed.await_args.args[1]
    assert finalized_payload["phase"] == "final"
    assert finalized_payload["node_content"] == "final content"
    assert completed_payload == {
        "task_id": "t1",
        "node_id": "L2-1-1",
        "node_name": "1.1 导数定义",
        "node_content": "final content",
        "content_blocks": [{"block_id": "L2-1-1-1-intro", "block_revision_id": "cbr_1"}],
        "generated_chars": 13,
    }


@pytest.mark.asyncio
async def test_qa_event_stream_splits_metadata():
    from ai_qa_service import AIQAService

    service = AIQAService()

    async def fake_stream(*_args, **_kwargs):
        yield "答案"
        yield "\n---METADATA---\n"
        yield '{"node_id":"n1","quote":"q","anno_summary":"s"}'

    service.answer_question_stream = fake_stream

    events = [
        event async for event in service.answer_question_events(
            "q", "ctx", [], "", "", "c1", "n1", "", None, False
        )
    ]

    assert any("event: answer" in event and "答案" in event for event in events)
    assert any("event: metadata" in event and '"node_id": "n1"' in event for event in events)
