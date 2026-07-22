import json

import pytest

import task_manager as task_manager_module
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
