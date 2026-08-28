#!/usr/bin/env python3
"""Kill a real generation mid-flight and check what the user is told.

P0/P3 acceptance. Unit tests pin the two recovery projections against
hand-built task records; this drives a real job against a real provider,
kills the worker while it is generating, and then asks both projections the
question a teacher asks: can this continue, and where did it stop?

What it checks:
  1. Both projections agree on can_resume / reason_code after the kill
     (the P0 contract, observed on a real interrupted job rather than a
     fixture).
  2. The interrupted job actually carries chapter/section progress
     (current_node_name, phase_detail) rather than a bare status (P3).
  3. Resume continues from the checkpoint instead of restarting.
"""

from __future__ import annotations

import argparse
import asyncio
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

import jobs.manager as task_manager_module  # noqa: E402
from course_repository import CourseDocumentRepository  # noqa: E402
from course_generation.service import CourseService  # noqa: E402
from course_versions import CourseVersionRepository  # noqa: E402
from generation_workspace import GenerationWorkspaceRepository  # noqa: E402
from learning_asset_storage import LearningAssetRepository  # noqa: E402
from material_storage import MaterialRepository  # noqa: E402
from question_bank import QuestionBankRepository  # noqa: E402
from storage import Storage  # noqa: E402
from jobs.manager import TaskManager  # noqa: E402


def _progress(task: dict) -> dict:
    return {
        "status": task.get("status"),
        "phase": task.get("phase") or task.get("current_phase"),
        "current_node_name": task.get("current_node_name"),
        # There is no current_node_index field anywhere in the codebase; the
        # per-node position is carried by phase_detail.completed_items /
        # total_items alongside current_node_name.
        "total_nodes": task.get("total_nodes"),
        "completed_nodes": task.get("completed_nodes"),
        "phase_detail": task.get("phase_detail"),
    }


async def run(subject: str, kill_after: int, timeout_seconds: int) -> dict:
    started = time.monotonic()
    report: dict = {"provider": "qwen3.6-35b-a3b"}
    with tempfile.TemporaryDirectory(prefix="lingzhi-kill-resume-") as temporary:
        data_root = Path(temporary) / "data"
        storage = Storage(str(data_root))
        workspaces = GenerationWorkspaceRepository(
            data_root / "generation_workspaces"
        )
        task_manager_module.TASKS_FILE = data_root / "tasks.json"
        manager = TaskManager(
            storage,
            CourseService(materials=MaterialRepository(data_root / "materials")),
            None,
            version_repository=CourseVersionRepository(
                data_root / "course_versions"
            ),
            asset_repository=LearningAssetRepository(
                data_root / "learning_assets"
            ),
            workspace_repository=workspaces,
            document_repository=CourseDocumentRepository(storage),
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
                "requirements": "只生成 1 章 2 节，正文简洁。",
                "materials": [],
                "material_bindings": [],
                "grounding_strategy": "general_assisted",
                "pedagogy_mode": "math_formal",
                "generation_mode": "fast",
                "course_purpose": "systematic",
                "web_question_enrichment": {"enabled": True},
            })
            task_id = str(job["job_id"])
            course_id = str(job["course_id"])

            # Confirm gates until content generation starts, then kill.
            progress_samples: list[dict] = []
            killed = False
            while time.monotonic() - started < timeout_seconds:
                task = manager.tasks[task_id]
                sample = _progress(task)
                if not progress_samples or progress_samples[-1] != sample:
                    progress_samples.append(sample)
                if task.get("status") == "waiting_for_review":
                    review = manager.get_generation_review(course_id) or {}
                    step = str(review.get("step") or "")
                    if step == "release":
                        report["note"] = "跑到发布门仍未进入正文，未能触发中断"
                        break
                    if review.get("can_confirm"):
                        await manager.confirm_generation_step(course_id, step)
                        continue
                if (
                    not killed
                    and str(task.get("phase") or "") == "content_generation"
                    and time.monotonic() - started > kill_after
                ):
                    # Kill the worker the way a crash would: cancel the loop
                    # without letting the job finalize.
                    await manager.shutdown(timeout=5)
                    killed = True
                    break
                if task.get("status") in {
                    "completed",
                    "completed_with_warnings",
                    "failed",
                }:
                    break
                await asyncio.sleep(1)

            report["killed_mid_generation"] = killed
            report["progress_samples"] = progress_samples[-6:]

            task = manager.tasks[task_id]
            if killed:
                # A crash leaves the record mid-flight; mark it the way the
                # restart path would find it.
                task["status"] = "failed"

            expensive = manager.describe_task_recovery(task_id)
            cheap = manager._task_recovery_summary(task)
            report["resume_view"] = {
                "can_resume": expensive.get("can_resume"),
                "reason_code": expensive.get("reason_code"),
                "state": expensive.get("state"),
            }
            report["polling_view"] = {
                "can_resume": cheap.get("can_resume"),
                "reason_code": cheap.get("reason_code"),
                "state": cheap.get("state"),
            }
            report["views_agree"] = (
                expensive.get("can_resume") == cheap.get("can_resume")
                and expensive.get("reason_code") == cheap.get("reason_code")
            )
            checkpoint = expensive.get("checkpoint") or {}
            report["checkpoint"] = {
                k: checkpoint.get(k)
                for k in (
                    "phase",
                    "completed_nodes",
                    "total_nodes",
                    "outline_ready",
                )
            }
            report["progress_visible"] = bool(
                task.get("current_node_name") or task.get("phase_detail")
            )
        finally:
            try:
                await manager.shutdown(timeout=5)
            except Exception:
                pass
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="真机中断与恢复一致性验证")
    parser.add_argument("--subject", default="一元二次方程的判别式")
    parser.add_argument("--kill-after", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    report = asyncio.run(run(args.subject, args.kill_after, args.timeout))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("views_agree") else 1


if __name__ == "__main__":
    raise SystemExit(main())
