"""E-1 断点续跑：恢复后已完成小节的模型调用次数必须为 0。

不靠肉眼判断——每个节点的模型调用都被计数，断言直接打在计数上。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from task_manager import TaskManager


CONTENT = "这是一节已经完成并持久化的课程正文。" * 20


class MemoryStorage:
    def __init__(self) -> None:
        self.courses: dict[str, dict] = {}

    def load_course(self, course_id: str):
        return deepcopy(self.courses.get(course_id))

    async def save_course(self, course_id: str, data: dict) -> None:
        self.courses[course_id] = deepcopy(data)


class CountingCourseService:
    """A stand-in that records one model call per section it is asked to write."""

    def __init__(self) -> None:
        self.calls_per_node: dict[str, int] = {}

    async def generate_node_content_stream(
        self,
        *,
        course_id: str,
        node: dict,
        config,
        on_chunk,
        on_activity=None,
        course_data=None,
        existing_draft: str = "",
    ) -> str:
        node_id = str(node.get("node_id") or "")
        self.calls_per_node[node_id] = self.calls_per_node.get(node_id, 0) + 1
        # Mirror what the real service records, so the stage-level tally under
        # test is fed the same way production feeds it.
        runtime = dict(node.get("generation_runtime") or {})
        runtime["model_call_count"] = int(runtime.get("model_call_count") or 0) + 1
        node["generation_runtime"] = runtime
        await on_chunk(CONTENT)
        return CONTENT


def _interrupted_course() -> dict:
    """Three sections: two finished before the interruption, one never started."""
    return {
        "course_id": "course-resume",
        "course_name": "断点续跑课程",
        "course_blueprint": {"nodes": ["L2-1-1", "L2-1-2", "L2-1-3"]},
        "nodes": [
            {
                "node_id": "L2-1-1",
                "node_level": 2,
                "node_name": "已完成小节一",
                "node_content": CONTENT,
                "generation_status": "completed",
            },
            {
                "node_id": "L2-1-2",
                "node_level": 2,
                "node_name": "已完成小节二",
                "node_content": CONTENT,
                "generation_status": "completed",
            },
            {
                "node_id": "L2-1-3",
                "node_level": 2,
                "node_name": "中断时未开始的小节",
                "node_content": "",
                "generation_status": "pending",
            },
        ],
    }


async def _manager(tmp_path, monkeypatch):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    versions = CourseVersionRepository(tmp_path / "versions")
    documents = CourseDocumentRepository(storage)
    course = _interrupted_course()
    job_id = "job-resume"
    await documents.create_generation_shell(
        course["course_id"],
        title=course["course_name"],
        job_id=job_id,
        metadata=course,
    )
    workspaces.create(job_id, course_id=course["course_id"], course_data=course)
    service = CountingCourseService()
    manager = TaskManager(
        storage,
        course_service=service,
        ws_service=None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    manager.save_tasks = lambda: None
    # _process_node returns early unless the manager is marked running.
    manager._running = True
    manager.tasks[job_id] = {
        "id": job_id,
        "course_id": course["course_id"],
        "course_name": course["course_name"],
        "type": "course_generation",
        "status": "running",
        "phase": "content_generation",
        "progress": 55,
        "completed_nodes": 2,
        "total_nodes": 3,
        "current_nodes": [],
        "workspace_id": job_id,
        "request_snapshot": {},
    }
    return manager, service, workspaces, job_id


@pytest.mark.asyncio
async def test_resume_never_recalls_the_model_for_a_completed_section(
    tmp_path, monkeypatch,
):
    manager, service, workspaces, job_id = await _manager(tmp_path, monkeypatch)
    course = workspaces.load_course(job_id)
    nodes = [n for n in course["nodes"] if n.get("node_level") == 2]

    await manager._schedule_nodes(job_id, nodes)

    # 已完成的两节：模型调用次数必须为 0。
    assert service.calls_per_node.get("L2-1-1", 0) == 0
    assert service.calls_per_node.get("L2-1-2", 0) == 0
    # 未完成的那一节仍然要被生成，否则"跳过"就变成了"漏做"。
    assert service.calls_per_node.get("L2-1-3", 0) == 1


@pytest.mark.asyncio
async def test_completed_section_content_survives_the_resume(tmp_path, monkeypatch):
    """跳过不能靠丢弃内容来实现——已完成正文必须原样保留。"""
    manager, _service, workspaces, job_id = await _manager(tmp_path, monkeypatch)
    course = workspaces.load_course(job_id)
    nodes = [n for n in course["nodes"] if n.get("node_level") == 2]

    await manager._schedule_nodes(job_id, nodes)

    resumed = manager._load_task_course(job_id) or {}
    by_id = {n["node_id"]: n for n in resumed.get("nodes") or []}
    assert by_id["L2-1-1"]["node_content"] == CONTENT
    assert by_id["L2-1-2"]["node_content"] == CONTENT


@pytest.mark.asyncio
async def test_real_resume_path_leaves_completed_sections_untouched(
    tmp_path, monkeypatch,
):
    """走真实恢复入口 _reset_interrupted_task_nodes，而不是直接调度。"""
    manager, service, workspaces, job_id = await _manager(tmp_path, monkeypatch)
    course = manager._load_task_course(job_id) or {}
    # 模拟中断瞬间：第三节正在生成，且已落了一段草稿。
    for node in course["nodes"]:
        if node["node_id"] == "L2-1-3":
            node["generation_status"] = "generating"
            node["node_content_draft"] = "中断前已经流式保存的草稿开头。"
    await manager._save_task_course(job_id, course)

    await manager._reset_interrupted_task_nodes(job_id, include_errors=True)

    reset = manager._load_task_course(job_id) or {}
    by_id = {n["node_id"]: n for n in reset.get("nodes") or []}
    # 已完成的两节不得被打回 pending。
    assert by_id["L2-1-1"]["generation_status"] == "completed"
    assert by_id["L2-1-2"]["generation_status"] == "completed"
    # 被中断的那节要回到 pending 以便重跑。
    assert by_id["L2-1-3"]["generation_status"] == "pending"

    l2 = [n for n in reset["nodes"] if n.get("node_level") == 2]
    await manager._schedule_nodes(job_id, l2)

    assert service.calls_per_node.get("L2-1-1", 0) == 0
    assert service.calls_per_node.get("L2-1-2", 0) == 0
    assert service.calls_per_node.get("L2-1-3", 0) == 1


@pytest.mark.asyncio
async def test_completed_sections_carry_a_zero_call_ledger_after_resume(
    tmp_path, monkeypatch,
):
    """验收要靠账单，不靠肉眼：已完成小节的 model_call_count 增量必须是 0。"""
    manager, _service, _workspaces, job_id = await _manager(tmp_path, monkeypatch)
    course = manager._load_task_course(job_id) or {}
    # 中断前，两节已完成的正文各自花过一次调用。
    for node in course["nodes"]:
        if node["generation_status"] == "completed":
            node["generation_runtime"] = {"model_call_count": 1}
    await manager._save_task_course(job_id, course)

    before = {
        n["node_id"]: int(
            (n.get("generation_runtime") or {}).get("model_call_count") or 0
        )
        for n in course["nodes"]
    }

    l2 = [
        n
        for n in (manager._load_task_course(job_id) or {})["nodes"]
        if n.get("node_level") == 2
    ]
    await manager._schedule_nodes(job_id, l2)

    after_course = manager._load_task_course(job_id) or {}
    after = {
        n["node_id"]: int(
            (n.get("generation_runtime") or {}).get("model_call_count") or 0
        )
        for n in after_course["nodes"]
    }

    # 恢复这一轮，已完成小节的调用增量必须为 0。
    assert after["L2-1-1"] - before["L2-1-1"] == 0
    assert after["L2-1-2"] - before["L2-1-2"] == 0
    # 未完成的那节确实花了一次调用。
    assert after["L2-1-3"] - before.get("L2-1-3", 0) == 1
