"""Isolated two-process harness for generation restart verification."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import time


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import task_manager as task_manager_module
from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from task_manager import TaskManager


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_course(self, course_id: str):
        if not self.path.exists():
            return None
        courses = json.loads(self.path.read_text(encoding="utf-8"))
        return deepcopy(courses.get(course_id))

    async def save_course(self, course_id: str, data: dict) -> None:
        courses = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        courses[course_id] = deepcopy(data)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(courses, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)


def build_manager(root: Path) -> tuple[TaskManager, JsonStorage, GenerationWorkspaceRepository]:
    task_manager_module.TASKS_FILE = root / "tasks.json"
    storage = JsonStorage(root / "courses.json")
    workspaces = GenerationWorkspaceRepository(root / "workspaces")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        version_repository=CourseVersionRepository(root / "versions"),
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
    )
    return manager, storage, workspaces


async def seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manager, storage, workspaces = build_manager(root)
    course = {
        "course_id": "process-course",
        "course_name": "真实进程恢复",
        "course_blueprint": {"nodes": ["node-1", "node-2"]},
        "nodes": [
            {
                "node_id": "node-1",
                "node_level": 2,
                "node_name": "已完成",
                "node_content": "已经完成并落盘的正文",
                "generation_status": "completed",
            },
            {
                "node_id": "node-2",
                "node_level": 2,
                "node_name": "中断节点",
                "node_content": "",
                "node_content_draft": "强制终止前的草稿",
                "generation_status": "generating",
            },
        ],
    }
    documents = CourseDocumentRepository(storage)
    await documents.create_generation_shell(
        course["course_id"], title=course["course_name"], job_id="process-job", metadata=course
    )
    workspaces.create("process-job", course_id=course["course_id"], course_data=course)
    manager.tasks["process-job"] = {
        "id": "process-job",
        "course_id": course["course_id"],
        "course_name": course["course_name"],
        "type": "course_generation",
        "status": "running",
        "phase": "content_generation",
        "progress": 50,
        "completed_nodes": 1,
        "total_nodes": 2,
        "workspace_id": "process-job",
        "current_nodes": ["node-2"],
    }
    manager.save_tasks()
    (root / "seed-ready").write_text("ready", encoding="utf-8")
    time.sleep(60)


async def recover(root: Path) -> None:
    manager, storage, workspaces = build_manager(root)
    should_queue = await manager._reconcile_task_after_restart("process-job")
    payload = {
        "should_queue": should_queue,
        "task": manager.tasks["process-job"],
        "workspace": workspaces.load("process-job"),
        "shell": storage.load_course("process-course"),
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    mode, root_arg = sys.argv[1:3]
    root_path = Path(root_arg)
    asyncio.run(seed(root_path) if mode == "seed" else recover(root_path))
