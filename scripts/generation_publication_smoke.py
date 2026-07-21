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
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import task_manager as task_manager_module  # noqa: E402
from course_repository import CourseDocumentRepository  # noqa: E402
from course_service import CourseService  # noqa: E402
from course_versions import CourseVersionRepository  # noqa: E402
from generation_workspace import GenerationWorkspaceRepository  # noqa: E402
from learning_asset_storage import LearningAssetRepository  # noqa: E402
from material_storage import MaterialRepository  # noqa: E402
from question_bank import QuestionBankRepository  # noqa: E402
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
            question_bank_repository_override=QuestionBankRepository(
                data_root / "question_banks"
            ),
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
            confirmed_steps: list[str] = []
            step_ready_seconds: dict[str, float] = {}
            while time.monotonic() - started < timeout_seconds:
                task = manager.tasks[task_id]
                if task.get("status") == "waiting_for_review":
                    review = manager.get_generation_review(course_id)
                    if not review:
                        raise RuntimeError("任务等待确认，但没有可读取的审阅产物")
                    step = str(review.get("step") or "")
                    if step not in {"outline", "release"}:
                        raise RuntimeError(f"烟测遇到非四步链路节点：{step or 'unknown'}")
                    if not review.get("can_confirm"):
                        artifact = review.get("artifact") or {}
                        blocking = artifact.get("blocking_issues") or []
                        raise RuntimeError(
                            f"{step} 无法确认："
                            + json.dumps(
                                {
                                    "quality_status": artifact.get(
                                        "quality_status"
                                    ),
                                    "publication_allowed": artifact.get(
                                        "publication_allowed"
                                    ),
                                    "source_chain_can_publish": (
                                        artifact.get("source_chain") or {}
                                    ).get("can_publish"),
                                    "blocking_issues": blocking[:6],
                                    "asset_quality_passed": artifact.get(
                                        "asset_quality_passed"
                                    ),
                                    "question_review": artifact.get(
                                        "question_review"
                                    ),
                                    "source_chain_issues": (
                                        artifact.get("source_chain") or {}
                                    ).get("issues", [])[:6],
                                },
                                ensure_ascii=False,
                            )
                        )
                    step_ready_seconds[step] = round(
                        time.monotonic() - started,
                        2,
                    )
                    await manager.confirm_generation_step(course_id, step)
                    confirmed_steps.append(step)
                    continue
                if task.get("status") in TERMINAL_STATUSES:
                    break
                await asyncio.sleep(1)
            else:
                raise TimeoutError(f"课程生成超时：{timeout_seconds} 秒")

            task = manager.tasks[task_id]
            raw = storage.load_course(course_id)
            workspace = workspaces.load(task_id)
            generated = workspace.get("course_data") or {}
            stage_artifacts = generated.get("generation_stage_artifacts") or {}
            teaching_stage = stage_artifacts.get("course_teaching_plan") or {}
            knowledge_base = generated.get("course_knowledge_base") or {}
            quality_report = generated.get(
                "generation_quality_report"
            ) or {}
            asset_quality = generated.get("asset_quality_report") or {}
            source_chain = generated.get(
                "generation_source_chain_report"
            ) or {}
            envelope = documents.document_envelope(course_id)
            document = envelope["document"]
            node_durations = [
                round(float(entry.duration_ms or 0) / 1000, 2)
                for entry in manager._get_task_log(task_id)
                if entry.event == "complete" and entry.duration_ms
            ]
            failures: list[str] = []
            if task.get("status") not in {
                "completed",
                "completed_with_warnings",
            }:
                failures.append(f"任务状态为 {task.get('status')}")
            if raw.get("course_schema_version") != "course_document_v1":
                failures.append("正式课程不是 course_document_v1")
            if "nodes" in raw:
                failures.append("正式课程仍持久化了旧 nodes")
            if raw.get("generation_status") not in {
                "passed",
                "completed_with_warnings",
            }:
                failures.append("课程未通过最终质量门")
            if not task.get("publication_allowed"):
                failures.append("任务未通过确定性发布门")
            if quality_report.get("blocking_issues"):
                failures.append("课程仍有阻断性质量问题")
            if not asset_quality.get("passed"):
                failures.append("学习资产合同未通过")
            if not source_chain.get("can_publish"):
                failures.append("确认后的同源链未通过")
            if workspace.get("status") != "published":
                failures.append("生成工作区未标记为 published")
            if not document.get("sections") or not document.get("blocks"):
                failures.append("发布后的课程文档为空")
            if manager.get_generation_workspace_course(course_id) is not None:
                failures.append("已发布工作区仍覆盖正式课程读取")
            if confirmed_steps != ["outline", "release"]:
                failures.append(
                    f"两个人工确认门顺序异常：{confirmed_steps}"
                )
            if int(teaching_stage.get("model_call_count") or 0) not in {1, 2}:
                failures.append("全课教案没有使用一次调用或一次定向纠正完成")
            if "course_knowledge_index" in stage_artifacts:
                failures.append("新链路仍生成了独立知识索引阶段")
            if "course_graph" in stage_artifacts:
                failures.append("新链路仍生成了独立关系图阶段")
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
                "knowledge_point_count": len(
                    knowledge_base.get("knowledge_points") or []
                ),
                "knowledge_relation_count": len(
                    knowledge_base.get("relations") or []
                ),
                "teaching_plan_model_calls": int(
                    teaching_stage.get("model_call_count") or 0
                ),
                "teaching_plan_duration_seconds": round(
                    float(teaching_stage.get("duration_ms") or 0) / 1000,
                    2,
                ),
                "content_node_durations_seconds": node_durations,
                "knowledge_index_model_calls": 0,
                "course_graph_model_calls": 0,
                "confirmed_steps": confirmed_steps,
                "step_ready_seconds": step_ready_seconds,
                "workspace_status": workspace.get("status"),
                "task_status": task.get("status"),
                "quality_status": quality_report.get("final_status"),
                "quality_blocking_issue_count": len(
                    quality_report.get("blocking_issues") or []
                ),
                "asset_quality_passed": bool(
                    asset_quality.get("passed")
                ),
                "source_chain_passed": bool(
                    source_chain.get("can_publish")
                ),
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
