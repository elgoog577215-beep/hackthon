"""Both recovery projections must answer "is this finished?" the same way.

``describe_task_recovery`` loads the workspace and checks the publication
receipt; ``_task_recovery_summary`` is the polling-safe version that avoids
loading course payloads. They are reached through different endpoints
(``_task_view`` vs ``_task_summary_view``), so a disagreement means the task
list and the resume button tell the teacher different things about the same job.
"""

import pytest

import task_manager as task_manager_module
from task_manager import TaskManager


def _manager(tmp_path, monkeypatch) -> TaskManager:
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    return TaskManager(storage=None, course_service=None, ws_service=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, publication_allowed",
    [
        ("completed", True),
        ("completed_with_warnings", True),
        ("completed_with_warnings", False),
        ("failed", True),
        ("paused", True),
        ("conflict", True),
    ],
)
async def test_both_recovery_views_agree_on_completion(
    tmp_path, monkeypatch, status, publication_allowed
):
    """Compare only the completion verdict, which both views must share.

    The two differ legitimately afterwards: the expensive view loads the
    workspace and can report ``checkpoint_not_supported`` for a job that has no
    isolated workspace, while the polling view never loads one. That divergence
    is by design; claiming a job is *finished* when it is not is the bug.
    """
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-1", course_name="课程", enqueue=False)
    task = manager.tasks[task_id]
    task["status"] = status
    task["publication_allowed"] = publication_allowed

    expensive = manager.describe_task_recovery(task_id)
    cheap = manager._task_recovery_summary(task)

    expensive_done = expensive["reason_code"] == "already_published"
    cheap_done = cheap["reason_code"] == "already_published"
    assert expensive_done == cheap_done, (
        f"{status}/{publication_allowed}: "
        f"resume says published={expensive_done}, polling says published={cheap_done}"
    )


@pytest.mark.asyncio
async def test_warning_completion_without_a_receipt_is_not_called_published(
    tmp_path, monkeypatch
):
    """The case the two views used to disagree on.

    A ``completed_with_warnings`` task that was never actually published has no
    publication receipt. Reporting it as ``already_published`` would tell the
    teacher the course is live when it is not.
    """
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-2", course_name="课程", enqueue=False)
    task = manager.tasks[task_id]
    task["status"] = "completed_with_warnings"
    task["publication_allowed"] = True
    # No workspace_id => no publication receipt exists.
    task.pop("workspace_id", None)

    expensive = manager.describe_task_recovery(task_id)
    cheap = manager._task_recovery_summary(task)

    assert (expensive["reason_code"] == "already_published") is False
    assert (cheap["reason_code"] == "already_published") is False
