from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

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
from slide_deck_v6_orchestrator import SLIDE_DECK_V6_BUILD_CONTRACT_VERSION
from jobs.manager import TaskManager


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
    import jobs.manager as task_manager_module

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
    for step in ("outline", "teaching", "content"):
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
async def test_v6_ppt_recovery_requires_a_retryable_failure(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    manager = TaskManager(MemoryStorage(), course_service=None, ws_service=None)
    common = {
        "course_id": "generic-field-course",
        "type": "slide_deck_variant_build",
        "status": "failed",
        "phase": "story",
        "progress": 41,
        "request_snapshot": {"target_schema": "slide_deck_v6"},
    }
    manager.tasks["retryable"] = {
        **common,
        "id": "retryable",
        "slide_build_contract_version": SLIDE_DECK_V6_BUILD_CONTRACT_VERSION,
        "slide_build_progress_v2": {
            "failure": {"retryable": True, "code": "story_ai_batch_timeout"},
        },
    }
    manager.tasks["terminal"] = {
        **common,
        "id": "terminal",
        "slide_build_progress_v2": {
            "failure": {"retryable": False, "code": "template_layout_unavailable"},
        },
    }
    candidate_checkpoints = tmp_path / "slide_deck_v6_candidates" / "checkpoints"
    candidate_checkpoints.mkdir(parents=True)
    progress_checkpoints = tmp_path / "slide_build_progress_v2"
    progress_checkpoints.mkdir(parents=True)
    (candidate_checkpoints / "retryable.json").write_text("{}", encoding="utf-8")
    (progress_checkpoints / "retryable.json").write_text("{}", encoding="utf-8")

    assert manager.describe_task_recovery("retryable")["can_resume"] is True
    assert manager.describe_task_recovery("terminal")["can_resume"] is False

    resumed = await manager.resume_task("retryable")

    assert resumed["status"] == "resumed"
    assert manager.tasks["retryable"]["status"] == "pending"
    assert await manager._task_queue.get() == "retryable"


@pytest.mark.asyncio
async def test_new_v6_task_records_the_current_checkpoint_contract(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    manager = TaskManager(MemoryStorage(), course_service=None, ws_service=None)

    task_id = await manager.create_task(
        "generic-field-course",
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={"target_schema": "slide_deck_v6"},
    )

    assert manager.tasks[task_id]["slide_build_contract_version"] == (
        SLIDE_DECK_V6_BUILD_CONTRACT_VERSION
    )


@pytest.mark.asyncio
async def test_v6_recovery_hides_a_stale_checkpoint_contract(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    manager = TaskManager(MemoryStorage(), course_service=None, ws_service=None)
    task_id = await manager.create_task(
        "generic-field-course",
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={"target_schema": "slide_deck_v6"},
    )
    manager.tasks[task_id].update({
        "status": "failed",
        "phase": "story",
        "slide_build_contract_version": "slide_deck_v6_build_contract_v4",
        "slide_build_progress_v2": {
            "failure": {
                "retryable": True,
                "code": "story_summary_markdown_invalid",
            },
        },
    })
    candidate_checkpoints = tmp_path / "slide_deck_v6_candidates" / "checkpoints"
    candidate_checkpoints.mkdir(parents=True)
    progress_checkpoints = tmp_path / "slide_build_progress_v2"
    progress_checkpoints.mkdir(parents=True)
    (candidate_checkpoints / f"{task_id}.json").write_text(
        json.dumps({
            "schema_version": "slide_deck_v6_checkpoint_v1",
            "build_contract_version": "slide_deck_v6_build_contract_v4",
        }),
        encoding="utf-8",
    )
    (progress_checkpoints / f"{task_id}.json").write_text("{}", encoding="utf-8")

    recovery = manager.describe_task_recovery(task_id)

    assert recovery["can_resume"] is False
    assert recovery["reason_code"] == "checkpoint_contract_stale"
    assert recovery["reason"] == "生成协议已升级，请重新生成当前组合"


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
async def test_service_restart_requeues_teacher_outline_generation(tmp_path, monkeypatch):
    manager, storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    manager.tasks["job-recovery"]["type"] = "teacher_outline_generation"
    manager.tasks["job-recovery"]["phase"] = "outline_generation"

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is True
    task = manager.tasks["job-recovery"]
    assert task["status"] == "pending"
    assert task["type"] == "teacher_outline_generation"
    assert task["restart_recovery_count"] == 1
    assert task["last_recovery_reason"] == "service_restart"
    assert storage.load_course("course-recovery")["generation_status"] == "resuming"
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
async def test_polling_task_summary_does_not_load_workspace_or_copy_heavy_artifacts(
    tmp_path, monkeypatch,
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    task = manager.tasks["job-recovery"]
    task["event_history"] = [{"payload": "x" * 100_000}]
    task["result"] = {"rendered": "y" * 100_000}
    task["last_event"] = {"payload": "z" * 100_000}

    def unexpected_workspace_load(_workspace_id):
        raise AssertionError("polling summary must not load the generation workspace")

    monkeypatch.setattr(workspaces, "load_course", unexpected_workspace_load)

    summary = manager.get_latest_task_by_course("course-recovery")

    assert summary is not None
    assert summary["id"] == "job-recovery"
    assert summary["recovery"]["state"] == "manual_resume"
    assert summary["recovery"]["can_resume"] is True
    assert "event_history" not in summary
    assert "last_event" not in summary
    assert "result" not in summary


@pytest.mark.asyncio
async def test_latest_course_task_can_be_scoped_away_from_slide_builds(
    tmp_path, monkeypatch,
):
    manager, _storage, _workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="completed"
    )
    generation_task = manager.tasks["job-recovery"]
    generation_task["type"] = "course_generation"
    generation_task["updated_at"] = "2026-08-16T10:00:00"
    slide_task = dict(generation_task)
    slide_task.update({
        "id": "job-slide",
        "type": "slide_deck_variant_build",
        "status": "failed",
        "updated_at": "2026-08-16T11:00:00",
    })
    manager.tasks["job-slide"] = slide_task

    assert manager.get_latest_task_by_course("course-recovery")["id"] == "job-slide"
    scoped = manager.get_latest_task_by_course(
        "course-recovery",
        task_type="course_generation",
    )
    assert scoped is not None
    assert scoped["id"] == "job-recovery"
    assert manager.get_latest_task_by_course(
        "course-recovery",
        task_type="course_import",
    ) is None


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
async def test_quality_failure_resumes_as_targeted_asset_repair(tmp_path, monkeypatch):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "progress": 100,
    })
    course = workspaces.load_course("job-recovery")
    asset_blocker = {
        "issue_id": "aqi-rubric",
        "gate": "semantic",
        "severity": "critical",
        "asset_type": "questions",
        "asset_id": "question-L2-1-1",
        "message": "理解检查量规与题目焦点不一致",
    }
    course["asset_quality_report"] = {
        "passed": False,
        "blocking_issues": [asset_blocker],
    }
    course["generation_quality_report"] = {
        "final_status": "quality_failed",
        "publication_allowed": False,
        "blocking_issues": [
            {
                "code": "difficulty:double_spike",
                "severity": "critical",
                "message": "L2-1-2 同时提高新概念负荷和任务复杂度，且支架不足",
                "suggestion": "提高支架强度",
                "node_id": "L2-1-2",
            },
            {
                "code": "asset:aqi-rubric",
                "severity": "critical",
                "message": asset_blocker["message"],
                "suggestion": "复核量规",
                "node_id": asset_blocker["asset_id"],
            },
        ],
    }
    workspaces.save_course("job-recovery", course)
    workspaces.set_status("job-recovery", "quality_failed", result={"quality": "failed"})

    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "quality_blocked"
    assert recovery["can_resume"] is True
    assert recovery["quality_failure"]["blocker_count"] == 2
    assert recovery["quality_failure"]["repair_scopes"] == [
        "difficulty_contract",
        "learning_assets",
    ]
    assert recovery["quality_failure"]["blockers"][1]["target_id"] == "question-L2-1-1"
    resumed = await manager.resume_task("job-recovery")
    assert resumed["status"] == "resumed"
    assert manager.tasks["job-recovery"]["asset_repair_requested"] is True
    assert manager.tasks["job-recovery"]["quality_repair_requested"] is True
    assert manager.tasks["job-recovery"]["phase"] == "quality_repair"
    assert manager._task_queue.qsize() == 1
    assert workspaces.load("job-recovery")["recovery_history"][-1]["reason"] == "quality_gate_repair"


@pytest.mark.asyncio
async def test_repeated_unchanged_quality_failure_disables_blind_resume(tmp_path, monkeypatch):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    course = workspaces.load_course("job-recovery")
    course["generation_quality_report"] = {
        "final_status": "quality_failed",
        "publication_allowed": False,
        "blocking_issues": [{
            "code": "difficulty:double_spike",
            "severity": "critical",
            "message": "L2-1-2 同时提高新概念负荷和任务复杂度，且支架不足",
            "suggestion": "提高支架强度",
            "node_id": "L2-1-2",
        }],
    }
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "publication_allowed": False,
    })

    first = manager.describe_task_recovery("job-recovery")
    manager.tasks["job-recovery"]["quality_failure"] = {
        **first["quality_failure"],
        "repeat_count": 2,
    }
    repeated = manager.describe_task_recovery("job-recovery")

    assert repeated["state"] == "quality_blocked"
    assert repeated["can_resume"] is False
    assert repeated["reason_code"] == "quality_gate_unchanged"
    assert "连续两次" in repeated["reason"]


@pytest.mark.asyncio
async def test_repair_policy_upgrade_allows_one_retry_of_legacy_quality_failure(
    tmp_path, monkeypatch
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch, task_status="failed"
    )
    course = workspaces.load_course("job-recovery")
    course["generation_quality_report"] = {
        "final_status": "quality_failed",
        "publication_allowed": False,
        "blocking_issues": [{
            "code": "asset:question_coverage",
            "severity": "critical",
            "message": "questions do not cover L2-1-1",
            "asset_type": "questions",
        }],
    }
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "publication_allowed": False,
        "quality_failure": {
            "fingerprint": TaskManager._quality_failure_summary(course)["fingerprint"],
            "repeat_count": 2,
            "supported": True,
            "repair_scopes": ["learning_assets"],
            "blockers": [],
        },
    })

    recovery = manager.describe_task_recovery("job-recovery")

    assert recovery["state"] == "quality_blocked"
    assert recovery["can_resume"] is True
    assert recovery["reason_code"] == "quality_gate_failed"
    assert recovery["quality_failure"]["repeat_count"] == 1
    assert (
        recovery["quality_failure"]["repair_policy_version"]
        == "quality_repair_v2.2"
    )


def test_quality_failure_summary_includes_source_chain_blockers():
    summary = TaskManager._quality_failure_summary({
        "generation_quality_report": {
            "final_status": "completed_with_warnings",
            "blocking_issues": [],
        },
        "asset_quality_report": {
            "passed": True,
            "blocking_issues": [],
        },
        "generation_source_chain_report": {
            "can_publish": False,
            "issues": [{
                "code": "requirements_revision_mismatch",
                "step": "requirements",
                "message": "requirements no longer matches its confirmed revision",
            }],
        },
    })

    assert summary["blocker_count"] == 1
    assert summary["repair_scopes"] == ["manual_review"]
    assert summary["supported"] is False
    assert summary["blockers"][0]["code"] == "requirements_revision_mismatch"


def test_missing_practice_slots_are_included_in_targeted_repair():
    targets = TaskManager._failed_practice_targets(
        {
            "questions": [{
                "node_id": "L2-1-1",
                "practice_level": "concept_check",
                "quality_status": "passed",
                "quality_report": {"passed": True},
                "practice_contract_revision_id": "pc-ok",
                "input_contract": {"node_id": "L2-1-1"},
            }],
        },
        expected_node_ids=["L2-1-1", "L2-1-2"],
    )

    assert targets == {
        "L2-1-1": ["objective_practice", "mastery_check"],
        "L2-1-2": [
            "concept_check",
            "objective_practice",
            "mastery_check",
        ],
    }


def test_confirmed_outline_revision_mismatch_uses_snapshot_repair_scope():
    summary = TaskManager._quality_failure_summary({
        "course_outline_revision_id": "bp-confirmed",
        "generation_quality_report": {
            "final_status": "completed_with_warnings",
            "blocking_issues": [],
        },
        "asset_quality_report": {
            "passed": True,
            "blocking_issues": [],
        },
        "generation_source_chain_report": {
            "can_publish": False,
            "issues": [{
                "code": "outline_revision_mismatch",
                "step": "outline",
                "message": "outline no longer matches its confirmed revision",
            }],
        },
    })

    assert summary["supported"] is True
    assert summary["repair_scopes"] == ["confirmed_outline_snapshot"]


def test_confirmed_outline_snapshot_restore_preserves_content_and_exact_revision():
    confirmed = {
        "course_id": "course-recovery",
        "course_name": "Unity 实战",
        "course_outline": {
            "course_title": "Unity 实战",
            "chapters": [{
                "chapter_number": 1,
                "title": "第1章 开发环境",
                "learning_focus": "",
                "sections": [{
                    "section_number": "1.1",
                    "node_id": "L2-1-1",
                    "title": "1.1 初始化项目",
                    "learning_objective": "完成项目初始化",
                    "scope_boundary": "只覆盖工程初始化",
                    "assessment": ["项目可以运行"],
                    "prerequisite_node_ids": [],
                }],
            }],
        },
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_name": "第1章 开发环境",
                "node_level": 1,
                "learning_objective": "",
                "prerequisite_node_ids": [],
                "scope_boundary": "",
                "assessment": [],
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_name": "1.1 初始化项目",
                "node_level": 2,
                "learning_objective": "完成项目初始化",
                "prerequisite_node_ids": [],
                "scope_boundary": "只覆盖工程初始化",
                "assessment": ["项目可以运行"],
            },
        ],
    }
    expected_revision = artifact_revision("outline", confirmed, request={})
    drifted = deepcopy(confirmed)
    drifted["course_outline"]["chapters"][0]["learning_focus"] = "第1章 开发环境"
    drifted["course_outline"]["chapters"][0]["sections"][0]["title"] = "初始化项目"
    drifted["nodes"][0]["node_name"] = "第1章 第1章 开发环境"
    drifted["nodes"][1]["node_content"] = "已经生成且必须保留的正文"

    restored = TaskManager._restore_confirmed_outline_identity(
        drifted,
        confirmed,
        expected_revision=expected_revision,
        request={},
    )

    assert artifact_revision("outline", restored, request={}) == expected_revision
    assert restored["nodes"][1]["node_content"] == "已经生成且必须保留的正文"
    assert restored["nodes"][0]["node_name"] == "第1章 开发环境"


@pytest.mark.asyncio
async def test_restart_replaces_stale_source_chain_publication_decision_before_completion(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    course = workspaces.load_course("job-recovery")
    course.update({
        "asset_quality_report": {"passed": True, "blocking_issues": []},
        "generation_quality_report": {
            "final_status": "completed_with_warnings",
            "publication_allowed": False,
            "blocking_issues": [],
            "source_chain_passed": False,
        },
    })
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
    })
    fresh_report = {
        "final_status": "completed_with_warnings",
        "publication_allowed": True,
        "blocking_issues": [],
        "warnings": [],
    }
    monkeypatch.setattr(
        task_manager_module,
        "build_final_course_quality_report",
        lambda _course, job_id=None: {**fresh_report, "job_id": job_id},
    )
    captured: dict = {}

    async def capture_complete(task_id: str, course_data: dict) -> None:
        captured["task_id"] = task_id
        captured["quality_report"] = deepcopy(
            course_data.get("generation_quality_report") or {}
        )

    monkeypatch.setattr(manager, "_complete_task", capture_complete)

    should_queue = await manager._reconcile_task_after_restart("job-recovery")

    assert should_queue is False
    assert captured["task_id"] == "job-recovery"
    assert captured["quality_report"]["publication_allowed"] is True
    assert captured["quality_report"].get("source_chain_passed") is not False


@pytest.mark.asyncio
async def test_release_review_deduplicates_wrapped_asset_and_quality_blockers(
    tmp_path, monkeypatch,
):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    course = workspaces.load_course("job-recovery")
    asset_blocker = {
        "issue_id": "aqi-rubric",
        "gate": "semantic",
        "severity": "critical",
        "asset_type": "questions",
        "asset_id": "question-L2-1-1",
        "message": "理解检查量规与题目焦点不一致",
    }
    course["asset_quality_report"] = {
        "passed": False,
        "blocking_issues": [asset_blocker],
    }
    course["generation_quality_report"] = {
        "final_status": "quality_failed",
        "publication_allowed": False,
        "blocking_issues": [
            {
                "code": "difficulty:double_spike",
                "severity": "critical",
                "message": "L2-1-2 同时提高新概念负荷和任务复杂度，且支架不足",
                "node_id": "L2-1-2",
            },
            {
                "code": "difficulty:double_spike",
                "severity": "critical",
                "message": "L2-1-2 同时提高新概念负荷和任务复杂度，且支架不足",
                "node_id": "L2-1-2",
            },
            {
                "code": "asset:aqi-rubric",
                "severity": "critical",
                "message": asset_blocker["message"],
                "node_id": asset_blocker["asset_id"],
            },
        ],
    }
    workspaces.save_course("job-recovery", course)
    workflow = _release_workflow(course)
    manager._mark_release_gate_blocked(workflow)
    manager.tasks["job-recovery"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "guided_workflow": workflow,
    })

    review = manager.get_generation_review("course-recovery")

    assert review is not None
    assert len(review["artifact"]["blocking_issues"]) == 2


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
    import jobs.manager as task_manager_module

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
    import jobs.manager as task_manager_module

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
        [sys.executable, "-X", "utf8", str(harness), "seed", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
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
        [sys.executable, "-X", "utf8", str(harness), "recover", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
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


# --- D-1b：覆盖度判定必须出现在大纲确认页 ---------------------------------


def _outline_review_workflow(course: dict) -> dict:
    """把工作流停在 outline 复核步，等待用户确认。"""
    snapshot = {}
    workflow = create_guided_workflow(snapshot)
    revision = artifact_revision("outline", course, request=snapshot)
    mark_waiting(workflow, "outline", revision=revision)
    return workflow


async def _outline_review(tmp_path, monkeypatch, *, verdict):
    manager, _storage, workspaces, _versions, _documents = await _workspace_manager(
        tmp_path, monkeypatch
    )
    course = workspaces.load_course("job-recovery")
    course["course_name"] = "微积分核心概览课"
    course["course_plan"] = {
        "positioning": "在 8 课时内掌握微积分的核心推理链条",
        "learning_objectives": ["能够计算导数与定积分"],
    }
    stage = course.setdefault("generation_stage_artifacts", {}).setdefault(
        "outline", {}
    )
    if verdict is not None:
        stage["course_coverage_verdict"] = verdict
    workspaces.save_course("job-recovery", course)
    manager.tasks["job-recovery"].update({
        "status": "waiting_for_review",
        "phase": "outline_ready",
        "guided_workflow": _outline_review_workflow(course),
    })
    return manager.get_generation_review("course-recovery")


_CALCULUS_VERDICT = {
    "schema_version": "course_coverage_verdict_v1",
    "subject": "微积分",
    "status": "partial",
    "scale": "micro",
    "scale_label": "微型课",
    "class_hours": 8,
    "may_claim_complete_subject": False,
    "coverage_promise": "只覆盖一个可检查的核心切面，不承担学科完整覆盖",
    "required_positioning": "微积分核心概览课",
    "covered_topics": ["函数、极限与连续", "导数定义与求导法则"],
    "uncovered_topics": [
        "隐函数求导与相关变化率",
        "中值定理",
        "洛必达法则与未定式",
        "微分方程入门",
    ],
    "advisories": ["建议一：压缩为核心课", "建议二：增加课时"],
}


@pytest.mark.asyncio
async def test_outline_review_page_shows_the_coverage_verdict(tmp_path, monkeypatch):
    """用户在确认目录时就能看到覆盖度判断和不覆盖清单。"""
    review = await _outline_review(tmp_path, monkeypatch, verdict=_CALCULUS_VERDICT)

    assert review is not None
    coverage = review["artifact"]["course_coverage"]
    assert coverage["available"] is True
    assert coverage["status"] == "partial"
    assert coverage["scale_label"] == "微型课"
    assert coverage["may_claim_complete_subject"] is False
    assert coverage["class_hours"] == 8
    assert coverage["uncovered_count"] == 4
    assert "中值定理" in coverage["uncovered_topics"]
    assert "函数、极限与连续" in coverage["covered_topics"]
    assert coverage["required_positioning"] == "微积分核心概览课"


@pytest.mark.asyncio
async def test_outline_review_without_a_verdict_is_not_reported_as_complete(
    tmp_path, monkeypatch,
):
    """D-1 之前生成的老课程没有判定——必须报 unknown，不能默认为完整。"""
    review = await _outline_review(tmp_path, monkeypatch, verdict=None)

    assert review is not None
    coverage = review["artifact"]["course_coverage"]
    assert coverage["available"] is False
    assert coverage["status"] == "unknown"
    assert coverage.get("may_claim_complete_subject") is not True


def test_outline_gate_message_names_the_uncovered_count():
    """确认门上的提示必须点出规格与不覆盖数量，不能只说"N 节已就绪"。"""
    message = TaskManager._outline_review_message({
        "available": True,
        "may_claim_complete_subject": False,
        "scale_label": "微型课",
        "uncovered_count": 4,
    })

    assert "微型课" in message
    assert "4" in message


def test_outline_gate_message_stays_plain_for_a_full_term_course():
    """完整学期课不应被这条提示打扰。"""
    message = TaskManager._outline_review_message({
        "available": True,
        "may_claim_complete_subject": True,
        "scale_label": "完整学期课",
        "uncovered_count": 0,
    })

    assert message == "课程目录等待确认；确认后将规划全课小节教案并生成正文"


# --- 大纲确认文案的两个维度必须正交（与 main 0fe4108d 合并后的语义） ---------
#
# 一、视角：教师大纲 vs 学习者课程，决定"确认之后会发生什么"；
# 二、覆盖度：D-1 的规格判定，决定"这门课能不能覆盖这个学科"。
# 二者互不覆盖——尤其覆盖度不能因为是教师大纲就被丢掉，那正是诚实性门的意义。


def test_teacher_outline_message_still_carries_the_coverage_verdict():
    """教师大纲也要看到覆盖度结论——不能因为换了视角就把诚实性门丢掉。"""
    message = TaskManager._outline_review_message(
        {
            "available": True,
            "may_claim_complete_subject": False,
            "scale_label": "微型课",
            "uncovered_count": 5,
        },
        is_teacher_outline=True,
    )

    # 覆盖度维度
    assert "微型课" in message
    assert "5" in message
    # 视角维度：教师大纲的下一步是按讲生成教案，不是生成正文
    assert "按讲生成教案" in message
    assert "生成正文" not in message


def test_learner_course_message_keeps_its_own_next_step():
    """学习者课程的下一步文案不得被教师视角串味。"""
    message = TaskManager._outline_review_message(
        {
            "available": True,
            "may_claim_complete_subject": False,
            "scale_label": "微型课",
            "uncovered_count": 5,
        },
        is_teacher_outline=False,
    )

    assert "微型课" in message
    assert "将规划全课小节教案并生成正文" in message
    assert "按讲生成教案" not in message


def test_teacher_outline_without_coverage_verdict_uses_plain_teacher_wording():
    """完整学期课/无判定时，教师大纲用自己的朴素文案，不掺覆盖度。"""
    plain = TaskManager._outline_review_message(
        {"available": True, "may_claim_complete_subject": True,
         "scale_label": "完整学期课", "uncovered_count": 0},
        is_teacher_outline=True,
    )
    unknown = TaskManager._outline_review_message(
        {"available": False, "status": "unknown"},
        is_teacher_outline=True,
    )

    assert plain == "课程大纲等待确认；确认后可按讲生成教案"
    assert unknown == "课程大纲等待确认；确认后可按讲生成教案"


def test_two_dimensions_are_independent():
    """正交性：换视角只改下一步那半句，覆盖度那半句逐字不变。"""
    coverage = {
        "available": True,
        "may_claim_complete_subject": False,
        "scale_label": "单元课",
        "uncovered_count": 3,
    }
    learner = TaskManager._outline_review_message(coverage, is_teacher_outline=False)
    teacher = TaskManager._outline_review_message(coverage, is_teacher_outline=True)

    verdict = "本次为单元课，有 3 个核心主题不覆盖"
    assert learner.startswith(verdict)
    assert teacher.startswith(verdict)
    # 两者只在"下一步"那半句上不同
    assert learner[len(verdict):] != teacher[len(verdict):]
