import json

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
