import json

import pytest

import task_manager as task_manager_module
from assessment_generation_policy import (
    ASSESSMENT_GENERATION_POLICY_VERSION,
)
from task_manager import TaskManager


def test_legacy_release_history_moves_to_persistent_data(tmp_path, monkeypatch):
    legacy = tmp_path / "release" / "tasks.json"
    durable = tmp_path / "state" / "generation_jobs.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "job-1": {
                "id": "job-1",
                "course_id": "course-1",
                "type": "course_generation",
                "status": "completed",
            },
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(task_manager_module, "DEFAULT_TASKS_FILE", durable)
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    monkeypatch.setattr(task_manager_module, "LEGACY_TASKS_FILE", legacy)

    manager = TaskManager(storage=None, course_service=None, ws_service=None)

    assert manager.tasks["job-1"]["course_id"] == "course-1"
    assert json.loads(durable.read_text(encoding="utf-8"))["job-1"]["status"] == "completed"


def test_task_manager_history_survives_restart(tmp_path, monkeypatch):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    first = TaskManager(
        storage=None,
        course_service=None,
        ws_service=None,
    )
    first.tasks["job-1"] = {
        "id": "job-1",
        "course_id": "course-1",
        "type": "course_generation",
        "status": "waiting_for_review",
    }
    first.save_tasks(strict=True)

    restarted = TaskManager(
        storage=None,
        course_service=None,
        ws_service=None,
    )

    assert restarted.tasks["job-1"]["status"] == "waiting_for_review"
    assert restarted.tasks["job-1"]["course_id"] == "course-1"


@pytest.mark.asyncio
async def test_generation_job_normalizes_legacy_assessment_profiles(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    manager = TaskManager(storage=None, course_service=None, ws_service=None)

    task_id = await manager.create_task(
        "course-fast",
        request_snapshot={"assessment_generation_profile": "fast"},
        enqueue=False,
    )
    assert manager.tasks[task_id]["assessment_generation_profile"] == "adaptive"
    assert manager.tasks[task_id]["request_snapshot"][
        "assessment_generation_profile"
    ] == "adaptive"
    assert manager.tasks[task_id][
        "assessment_generation_policy_version"
    ] == ASSESSMENT_GENERATION_POLICY_VERSION

    manager.tasks["legacy"] = {
        "id": "legacy",
        "course_id": "course-legacy",
        "type": "course_generation",
        "status": "completed",
    }
    manager.save_tasks(strict=True)
    restarted = TaskManager(storage=None, course_service=None, ws_service=None)

    assert restarted.tasks["legacy"]["assessment_generation_profile"] == (
        "adaptive"
    )


@pytest.mark.asyncio
async def test_failed_slide_task_summary_exposes_quality_blockers(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    task_id = "slide-quality-failure"
    manager.tasks[task_id] = {
        "id": task_id,
        "course_id": "course-1",
        "type": "slide_deck_variant_build",
        "status": "running",
        "phase": "build_blocked",
        "progress": 100,
        "error": "slide_deck_variant_quality_gate_failed",
        "event_history": [],
    }
    await manager._record_representation_event(task_id, {
        "event": "build_blocked",
        "quality": {
            "passed": False,
            "score": 80,
            "blockers": [
                {
                    "severity": "critical",
                    "code": "body_density_overflow",
                    "page_id": "slide:v4:leftover:0001",
                },
            ],
            "warnings": [],
        },
    })
    manager.tasks[task_id]["status"] = "failed"
    manager.save_tasks(strict=True)
    restarted = TaskManager(storage=None, course_service=None, ws_service=None)

    summary = restarted.get_task_summary(task_id)

    assert summary is not None
    assert summary["quality"]["passed"] is False
    assert summary["quality"]["blockers"] == [
        {
            "severity": "critical",
            "code": "body_density_overflow",
            "page_id": "slide:v4:leftover:0001",
        },
    ]
    assert "last_event" not in summary


def test_terminal_job_persistence_omits_large_recovery_payloads(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager.tasks["job-complete"] = {
        "id": "job-complete",
        "course_id": "course-1",
        "type": "course_generation",
        "status": "completed",
        "updated_at": "2026-07-31T12:00:00",
        "result": {"content": "x" * 100_000},
        "event_history": [{"payload": "x" * 100_000}],
        "node_drafts": {"node-1": "x" * 100_000},
        "request_snapshot": {"source": "x" * 100_000},
    }

    manager.save_tasks(strict=True)

    persisted = json.loads(durable.read_text(encoding="utf-8"))
    terminal = persisted["job-complete"]
    assert terminal["course_id"] == "course-1"
    assert terminal["status"] == "completed"
    assert "result" not in terminal
    assert "event_history" not in terminal
    assert "node_drafts" not in terminal
    assert "request_snapshot" not in terminal
    assert manager.tasks["job-complete"]["result"]["content"]


def test_job_persistence_keeps_active_recovery_and_bounds_terminal_history(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    monkeypatch.setattr(
        task_manager_module,
        "MAX_TERMINAL_TASK_HISTORY",
        2,
        raising=False,
    )
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager.tasks = {
        "job-old": {
            "id": "job-old",
            "status": "completed",
            "updated_at": "2026-07-31T09:00:00",
        },
        "job-middle": {
            "id": "job-middle",
            "status": "failed",
            "updated_at": "2026-07-31T10:00:00",
        },
        "job-new": {
            "id": "job-new",
            "status": "cancelled",
            "updated_at": "2026-07-31T11:00:00",
        },
        "job-running": {
            "id": "job-running",
            "status": "running",
            "updated_at": "2026-07-31T08:00:00",
            "request_snapshot": {"topic": "热力学"},
            "node_drafts": {"node-1": "checkpoint"},
        },
    }

    manager.save_tasks(strict=True)

    persisted = json.loads(durable.read_text(encoding="utf-8"))
    assert set(persisted) == {"job-middle", "job-new", "job-running"}
    assert persisted["job-running"]["request_snapshot"] == {"topic": "热力学"}
    assert persisted["job-running"]["node_drafts"] == {"node-1": "checkpoint"}


def test_oversized_job_index_is_archived_before_json_hydration(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    durable.parent.mkdir(parents=True)
    original = json.dumps({
        "job-oversized": {
            "id": "job-oversized",
            "status": "completed",
            "result": "x" * 500,
        },
    })
    durable.write_text(original, encoding="utf-8")
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    monkeypatch.setattr(
        task_manager_module,
        "MAX_TASK_INDEX_BYTES",
        128,
        raising=False,
    )

    manager = TaskManager(storage=None, course_service=None, ws_service=None)

    archives = list(durable.parent.glob("generation_jobs.oversized-*.json"))
    assert manager.tasks == {}
    assert not durable.exists()
    assert len(archives) == 1
    assert archives[0].read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_outline_growth_never_regresses_when_parallel_updates_arrive_out_of_order(
    tmp_path,
    monkeypatch,
):
    durable = tmp_path / "data" / "generation_jobs.json"
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", durable)
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager.tasks["job-growth"] = {
        "id": "job-growth",
        "status": "running",
        "phase": "outline_generation",
        "current_phase": "outline_generation",
        "phase_detail": {
            "outline_growth": {
                "completed_sections": 4,
                "active_batch_id": "chapter-2",
                "active_chapter_number": 2,
                "chapters": [{"chapter_number": 1, "sections": [1, 2, 3, 4]}],
            },
        },
    }

    await manager._update_phase(
        "job-growth",
        "outline_generation",
        35,
        "旧批次稍后返回",
        phase_detail={
            "outline_growth": {
                "completed_sections": 2,
                "active_batch_id": "chapter-3",
                "active_chapter_number": 3,
                "chapters": [{"chapter_number": 1, "sections": [1, 2]}],
            },
        },
    )

    growth = manager.tasks["job-growth"]["phase_detail"]["outline_growth"]
    assert growth["completed_sections"] == 4
    assert growth["chapters"][0]["sections"] == [1, 2, 3, 4]
    assert growth["active_batch_id"] == "chapter-3"
    assert growth["active_chapter_number"] == 3

    await manager._update_phase(
        "job-growth",
        "outline_generation",
        36,
        "提供方心跳",
        phase_detail={"provider_unit": "outline_batch"},
    )

    heartbeat_growth = manager.tasks["job-growth"]["phase_detail"]["outline_growth"]
    assert heartbeat_growth["completed_sections"] == 4
