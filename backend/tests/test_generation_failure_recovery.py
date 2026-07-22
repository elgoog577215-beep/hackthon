from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from guided_generation import (
    artifact_revision,
    confirm_waiting_step,
    create_guided_workflow,
    mark_waiting,
    step_state,
)
from task_manager import TaskManager, TaskRecoveryConflict


class MemoryStorage:
    def __init__(self) -> None:
        self.courses: dict[str, dict] = {}

    def load_course(self, course_id: str):
        return deepcopy(self.courses.get(course_id))

    async def save_course(self, course_id: str, data: dict) -> None:
        self.courses[course_id] = deepcopy(data)


def _course(*, interrupted_status: str = "generating") -> dict:
    return {
        "course_id": "course-recovery",
        "course_name": "失败恢复课程",
        "course_blueprint": {"nodes": ["L2-1-1", "L2-1-2"]},
        "nodes": [
            {
                "node_id": "L2-1-1",
                "node_level": 2,
                "node_name": "已完成内容",
                "node_content": "这里是已经完成并持久化的课程正文。",
                "generation_status": "completed",
            },
            {
                "node_id": "L2-1-2",
                "node_level": 2,
                "node_name": "中断内容",
                "node_content": "",
                "node_content_draft": "进程中断前已经保存的草稿",
                "generation_status": interrupted_status,
                "error_summary": "provider connection closed",
            },
        ],
    }


async def _workspace_manager(tmp_path, monkeypatch, *, task_status: str = "running"):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    versions = CourseVersionRepository(tmp_path / "versions")
    documents = CourseDocumentRepository(storage)
    course = _course(interrupted_status="error" if task_status == "failed" else "generating")
    job_id = "job-recovery"
    await documents.create_generation_shell(
        course["course_id"],
        title=course["course_name"],
        job_id=job_id,
        metadata=course,
    )
    workspaces.create(job_id, course_id=course["course_id"], course_data=course)
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    manager.save_tasks = lambda: None
    manager.tasks[job_id] = {
        "id": job_id,
        "course_id": course["course_id"],
        "course_name": course["course_name"],
        "type": "course_generation",
        "status": task_status,
        "phase": "content_generation",
        "progress": 55,
        "completed_nodes": 1,
        "total_nodes": 2,
        "current_nodes": ["L2-1-2"],
        "current_node_name": "中断内容",
        "workspace_id": job_id,
        "request_snapshot": {},
        "error": "provider connection closed" if task_status == "failed" else None,
    }
    return manager, storage, workspaces, versions, documents


def _release_workflow(course: dict, request: dict | None = None) -> dict:
    snapshot = request or {}
    workflow = create_guided_workflow(snapshot)
    for step in ("outline", "content"):
        revision = artifact_revision(step, course, request=snapshot)
        mark_waiting(workflow, step, revision=revision)
        confirm_waiting_step(workflow, step, revision=revision)
    mark_waiting(
        workflow,
        "release",
        revision=artifact_revision("release", course, request=snapshot),
    )
    return workflow


@pytest.mark.asyncio
async def test_service_restart_recovers_same_job_and_preserves_checkpoint(tmp_path, monkeypatch):
    manager, storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is True
    assert manager.tasks["job-recovery"]["status"] == "pending"
    assert storage.load_course("course-recovery")["generation_status"] == "resuming"
    recovered = workspaces.load_course("job-recovery")
    assert recovered["nodes"][0]["node_content"].startswith("这里是已经完成")
    assert recovered["nodes"][1]["node_content_draft"] == "进程中断前已经保存的草稿"
    assert recovered["nodes"][1]["generation_status"] == "pending"
    history = workspaces.load("job-recovery")["recovery_history"]
    assert history[-1]["reason"] == "service_restart"
    assert history[-1]["automatic"] is True


@pytest.mark.asyncio
async def test_fresh_active_job_is_not_described_as_recovery(tmp_path, monkeypatch):
    manager, _storage, _workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )

    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "none"
    assert recovery["reason_code"] == "not_needed"
    assert recovery["can_resume"] is False


@pytest.mark.asyncio
async def test_outline_failure_restarts_stage_without_claiming_content_checkpoint(
    tmp_path,
    monkeypatch,
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path,
        monkeypatch,
        task_status="failed",
    )
    workspaces.save_course("job-recovery", {
        "course_id": "course-recovery",
        "course_name": "失败恢复课程",
        "course_generation_brief": {"subject": "失败恢复课程"},
        "subject_pedagogy_profile": {"primary_mode": "general"},
        "material_cards": [],
        "nodes": [],
    })
    manager.tasks["job-recovery"].update({
        "phase": "outline_validation",
        "progress": 34,
        "completed_nodes": 0,
        "total_nodes": 0,
    })

    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "manual_resume"
    assert recovery["can_resume"] is True
    assert recovery["reason_code"] == "stage_restart_available"
    assert recovery["checkpoint"]["requirements_ready"] is True
    assert recovery["checkpoint"]["outline_ready"] is False
    assert recovery["checkpoint"]["completed_nodes"] == 0
    assert recovery["checkpoint"]["total_nodes"] == 0
    assert "重新生成课程目录" in recovery["reason"]
    assert "正文" not in recovery["reason"]


@pytest.mark.asyncio
async def test_reconciled_active_job_is_described_as_auto_resuming(tmp_path, monkeypatch):
    manager, _storage, _workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )

    assert await manager._reconcile_task_after_restart("job-recovery") is True
    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "auto_resuming"
    assert recovery["reason_code"] == "job_recovering"
    assert recovery["checkpoint"]["completed_nodes"] == 1


@pytest.mark.asyncio
async def test_manual_resume_is_idempotent_and_requeues_once(tmp_path, monkeypatch):
    manager, storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    workspaces.set_status("job-recovery", "failed", result={"error": "provider unavailable"})

    first = await manager.resume_task("job-recovery")
    second = await manager.resume_task("job-recovery")

    assert first["status"] == "resumed"
    assert second["status"] == "already_active"
    assert manager._task_queue.qsize() == 1
    assert manager.tasks["job-recovery"]["recovery_count"] == 1
    assert storage.load_course("course-recovery")["generation_status"] == "resuming"
    recovered = workspaces.load_course("job-recovery")["nodes"][1]
    assert recovered["node_content_draft"] == "进程中断前已经保存的草稿"
    assert recovered["generation_status"] == "pending"
    assert workspaces.load("job-recovery")["result"]["error"] == "provider unavailable"


@pytest.mark.asyncio
async def test_concurrent_manual_resume_claims_checkpoint_once(tmp_path, monkeypatch):
    manager, _storage, workspaces, _versions, documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    workspaces.set_status("job-recovery", "failed")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_update = documents.update_generation_state

    async def slow_update(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original_update(*args, **kwargs)

    documents.update_generation_state = slow_update
    first = asyncio.create_task(manager.resume_task("job-recovery"))
    await entered.wait()
    second = await manager.resume_task("job-recovery")

    assert second["status"] == "already_active"
    assert manager._task_queue.empty()

    release.set()
    assert (await first)["status"] == "resumed"
    assert manager._task_queue.qsize() == 1
    assert len(workspaces.load("job-recovery")["recovery_history"]) == 1


@pytest.mark.asyncio
async def test_restart_recognizes_publication_receipt_without_duplicate_execution(tmp_path, monkeypatch):
    manager, storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    raw = storage.load_course("course-recovery")
    raw["generation_status"] = "passed"
    raw["course_operation_log"] = [{
        "command_id": "publish-generation:job-recovery",
        "receipt": {"document_revision": "cdr_published"},
    }]
    await storage.save_course("course-recovery", raw)

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is False
    task = manager.tasks["job-recovery"]
    assert task["status"] == "completed"
    assert task["progress"] == 100
    assert task["course_version_id"] == "cdr_published"
    assert not workspaces.load("job-recovery").get("recovery_history")


@pytest.mark.asyncio
async def test_quality_failure_is_not_exposed_as_runtime_retry(tmp_path, monkeypatch):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "progress": 100,
    })
    workspaces.set_status("job-recovery", "quality_failed", result={"quality": "failed"})

    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "quality_blocked"
    assert recovery["can_resume"] is False
    with pytest.raises(TaskRecoveryConflict):
        await manager.resume_task("job-recovery")
    assert manager._task_queue.empty()


@pytest.mark.asyncio
async def test_blocked_release_settles_quality_failed_instead_of_dead_review(
    tmp_path,
    monkeypatch,
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path,
        monkeypatch,
    )
    course = workspaces.load_course("job-recovery")
    course.update({
        "course_knowledge_base": {
            "revision_id": "ckb_release",
            "lifecycle_status": "active",
        },
        "course_knowledge_map": {
            "course_knowledge_base_revision_id": "ckb_release",
        },
        "learning_asset_bundle_revision_id": "lab_release",
        "asset_quality_report": {
            "passed": False,
            "blocking_issues": [{
                "code": "questions:input_contract_missing",
                "severity": "critical",
                "message": "题目缺少正式练习契约",
            }],
        },
        "generation_quality_report": {
            "final_status": "completed_with_warnings",
            "publication_allowed": False,
            "blocking_issues": [],
        },
        "generation_stage_artifacts": {
            "content_candidate": {"status": "completed"},
        },
    })
    workflow = _release_workflow(course)
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "running",
        "phase": "finalizing",
        "guided_workflow": workflow,
    })

    await manager._complete_task("job-recovery", course)

    task = manager.tasks["job-recovery"]
    assert task["status"] == "completed_with_warnings"
    assert task["phase"] == "quality_failed"
    assert task["guided_workflow"]["review_step"] is None
    assert step_state(task["guided_workflow"], "release")["status"] == (
        "needs_regeneration"
    )
    assert workspaces.load("job-recovery")["status"] == "quality_failed"


@pytest.mark.asyncio
async def test_restart_rechecks_dead_release_and_restores_confirmable_gate(
    tmp_path,
    monkeypatch,
):
    import task_manager as task_manager_module

    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path,
        monkeypatch,
    )
    course = workspaces.load_course("job-recovery")
    course.update({
        "course_knowledge_base": {
            "revision_id": "ckb_release",
            "lifecycle_status": "active",
        },
        "course_knowledge_map": {
            "course_knowledge_base_revision_id": "ckb_release",
        },
        "asset_quality_report": {
            "passed": True,
            "blocking_issues": [],
        },
        "generation_quality_report": {
            "final_status": "completed_with_warnings",
            "publication_allowed": False,
            "blocking_issues": [{
                "code": "legacy_stale_gate",
                "severity": "critical",
            }],
        },
    })
    workflow = _release_workflow(course)
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "waiting_for_review",
        "phase": "release_ready",
        "guided_workflow": workflow,
    })
    monkeypatch.setattr(
        task_manager_module,
        "build_final_course_quality_report",
        lambda _course, job_id=None: {
            "job_id": job_id,
            "final_status": "passed",
            "publication_allowed": True,
            "blocking_issues": [],
            "warnings": [],
        },
    )

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is False
    task = manager.tasks["job-recovery"]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "release"
    review = manager.get_generation_review("course-recovery")
    assert review["step"] == "release"
    assert review["can_confirm"] is True
    assert review["artifact"]["publication_allowed"] is True
    assert review["artifact"]["source_chain"]["can_publish"] is True


@pytest.mark.asyncio
async def test_restart_preserves_healthy_release_review_without_reconciliation(
    tmp_path,
    monkeypatch,
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path,
        monkeypatch,
    )
    course = workspaces.load_course("job-recovery")
    course.update({
        "course_knowledge_base": {
            "revision_id": "ckb_release",
            "lifecycle_status": "active",
        },
        "course_knowledge_map": {
            "course_knowledge_base_revision_id": "ckb_release",
        },
        "asset_quality_report": {"passed": True, "blocking_issues": []},
        "generation_quality_report": {
            "final_status": "passed",
            "publication_allowed": True,
            "blocking_issues": [],
        },
    })
    workflow = _release_workflow(course)
    course["generation_source_chain_report"] = {
        "can_publish": True,
        "issues": [],
        "sentinel": "preserve-me",
    }
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "waiting_for_review",
        "phase": "release_ready",
        "guided_workflow": workflow,
    })

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is False
    task = manager.tasks["job-recovery"]
    assert task["status"] == "waiting_for_review"
    assert "release_gate_reconciled_at" not in task
    saved = workspaces.load_course("job-recovery")
    assert saved["generation_source_chain_report"]["sentinel"] == "preserve-me"


@pytest.mark.asyncio
async def test_restart_does_not_mutate_workspace_when_course_shell_is_missing(tmp_path, monkeypatch):
    manager, storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    workspaces.set_status("job-recovery", "failed", result={"error": "interrupted"})
    storage.courses.clear()

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is False
    assert manager.tasks["job-recovery"]["status"] == "failed"
    assert manager.tasks["job-recovery"]["phase"] == "recovery_unavailable"
    workspace = workspaces.load("job-recovery")
    assert workspace["status"] == "failed"
    assert not workspace.get("recovery_history")
    assert workspace["course_data"]["nodes"][1]["generation_status"] == "generating"


@pytest.mark.asyncio
async def test_candidate_generation_job_recovers_without_new_workspace(tmp_path, monkeypatch):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    versions = CourseVersionRepository(tmp_path / "versions")
    candidate = versions.create_candidate(
        "course-candidate",
        {
            **_course(),
            "course_id": "course-candidate",
        },
        base_version_id="version-base",
        impact_report={"affected_node_ids": ["L2-1-2"]},
    )
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        version_repository=versions,
        workspace_repository=GenerationWorkspaceRepository(tmp_path / "workspaces"),
        document_repository=CourseDocumentRepository(storage),
    )
    manager.save_tasks = lambda: None
    manager.tasks["job-candidate"] = {
        "id": "job-candidate",
        "course_id": "course-candidate",
        "type": "course_generation",
        "operation": "regenerate",
        "candidate_id": candidate["candidate_id"],
        "status": "running",
        "phase": "content_generation",
        "progress": 50,
        "completed_nodes": 1,
        "total_nodes": 2,
    }

    should_queue = await manager._reconcile_task_after_restart("job-candidate")

    assert should_queue is True
    assert manager.tasks["job-candidate"]["status"] == "pending"
    restored = versions.load_candidate("course-candidate", candidate["candidate_id"])
    interrupted = restored["course_data"]["nodes"][1]
    assert interrupted["generation_status"] == "pending"
    assert interrupted["node_content_draft"] == "进程中断前已经保存的草稿"


def test_real_process_kill_and_restart_recovers_persisted_checkpoint(tmp_path):
    harness = Path(__file__).with_name("recovery_process_harness.py")
    process = subprocess.Popen(
        [sys.executable, str(harness), "seed", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while not (tmp_path / "seed-ready").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not (tmp_path / "seed-ready").exists():
            process.kill()
            _stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"recovery seed process did not become ready: {stderr}")
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    recovered = subprocess.run(
        [sys.executable, str(harness), "recover", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(recovered.stdout.strip().splitlines()[-1])

    assert payload["should_queue"] is True
    assert payload["task"]["status"] == "pending"
    assert payload["task"]["restart_recovery_count"] == 1
    assert payload["shell"]["generation_status"] == "resuming"
    assert payload["workspace"]["recovery_history"][-1]["automatic"] is True
    interrupted = payload["workspace"]["course_data"]["nodes"][1]
    assert interrupted["generation_status"] == "pending"
    assert interrupted["node_content_draft"] == "强制终止前的草稿"
