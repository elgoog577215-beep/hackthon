#!/usr/bin/env python3
"""Run one real generation job against isolated temporary persistence."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import task_manager as task_manager_module  # noqa: E402
from course_repository import CourseDocumentRepository  # noqa: E402
from course_service import CourseService  # noqa: E402
from course_versions import CourseVersionRepository  # noqa: E402
from generation_workspace import GenerationWorkspaceRepository  # noqa: E402
from learning_asset_storage import LearningAssetRepository  # noqa: E402
from material_storage import MaterialRepository  # noqa: E402
from storage import Storage  # noqa: E402
from task_manager import TaskManager  # noqa: E402


TERMINAL_STATUSES = {"completed", "completed_with_warnings", "failed", "conflict"}


async def run_smoke(subject: str, timeout_seconds: int) -> dict[str, object]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lingzhi-generation-smoke-") as temporary:
        root = Path(temporary)
        data_root = root / "data"
        storage = Storage(str(data_root))
        workspaces = GenerationWorkspaceRepository(data_root / "generation_workspaces")
        versions = CourseVersionRepository(data_root / "course_versions")
        assets = LearningAssetRepository(data_root / "learning_assets")
        documents = CourseDocumentRepository(storage)
        service = CourseService(materials=MaterialRepository(data_root / "materials"))
        task_manager_module.TASKS_FILE = data_root / "tasks.json"
        manager = TaskManager(
            storage,
            service,
            None,
            version_repository=versions,
            asset_repository=assets,
            workspace_repository=workspaces,
            document_repository=documents,
        )
        await manager.start()
        try:
            job = await manager.create_generation_job({
                "subject": subject,
                "target_audience": "大学生",
                "difficulty": "beginner",
                "style": "academic",
                "requirements": (
                    "这是发布链路验收课程。只生成 1 章 1 节，聚焦一个最小完整概念；"
                    "正文简洁，但必须包含定义、一个例子、一个误区和一个可验收任务。"
                ),
                "materials": [],
                "material_bindings": [],
                "grounding_strategy": "general_assisted",
                "pedagogy_mode": "math_formal",
                "generation_mode": "fast",
                "course_purpose": "systematic",
            })
            task_id = str(job["job_id"])
            course_id = str(job["course_id"])
            while time.monotonic() - started < timeout_seconds:
                task = manager.tasks[task_id]
                if task.get("status") in TERMINAL_STATUSES:
                    break
                await asyncio.sleep(1)
            else:
                raise TimeoutError(f"课程生成超时：{timeout_seconds} 秒")

            task = manager.tasks[task_id]
            raw = storage.load_course(course_id)
            workspace = workspaces.load(task_id)
            envelope = documents.document_envelope(course_id)
            document = envelope["document"]
            failures: list[str] = []
            if task.get("status") != "completed":
                failures.append(f"任务状态为 {task.get('status')}")
            if raw.get("course_schema_version") != "course_document_v1":
                failures.append("正式课程不是 course_document_v1")
            if "nodes" in raw:
                failures.append("正式课程仍持久化了旧 nodes")
            if raw.get("generation_status") != "passed":
                failures.append("课程未通过最终质量门")
            if workspace.get("status") != "published":
                failures.append("生成工作区未标记为 published")
            if not document.get("sections") or not document.get("blocks"):
                failures.append("发布后的课程文档为空")
            if manager.get_generation_workspace_course(course_id) is not None:
                failures.append("已发布工作区仍覆盖正式课程读取")
            if failures:
                raise RuntimeError("；".join(failures))

            return {
                "status": "passed",
                "course_id": course_id,
                "task_id": task_id,
                "course_name": envelope.get("course_name"),
                "document_revision": document.get("document_revision"),
                "section_count": len(document.get("sections") or []),
                "block_count": len(document.get("blocks") or []),
                "workspace_status": workspace.get("status"),
                "generation_status": raw.get("generation_status"),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            await manager.shutdown(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证首次课程生成的统一发布链路")
    parser.add_argument("--subject", default="一元一次方程的移项原理")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    try:
        result = asyncio.run(run_smoke(args.subject, args.timeout))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
