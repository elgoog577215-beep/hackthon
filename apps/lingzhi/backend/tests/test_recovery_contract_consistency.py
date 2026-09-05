"""Both recovery projections must answer "is this finished?" the same way.

``describe_task_recovery`` loads the workspace and checks the publication
receipt; ``_task_recovery_summary`` is the polling-safe version that avoids
loading course payloads. They are reached through different endpoints
(``_task_view`` vs ``_task_summary_view``), so a disagreement means the task
list and the resume button tell the teacher different things about the same job.
"""

import pytest

import jobs.manager as task_manager_module
from storage import Storage
from jobs.manager import TaskManager


def _manager(tmp_path, monkeypatch) -> TaskManager:
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    return TaskManager(storage=None, course_service=None, ws_service=None)


def _manager_with_storage(tmp_path, monkeypatch) -> TaskManager:
    """A manager backed by real storage.

    Resumability cases set a ``workspace_id``, and the publication-receipt
    lookup that runs on that path reads through the course repository, so the
    ``storage=None`` manager above cannot exercise them.
    """
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    return TaskManager(
        storage=Storage(str(tmp_path / "data")),
        course_service=None,
        ws_service=None,
    )


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

    Resumability is pinned separately below; see
    ``test_both_views_agree_when_the_workspace_is_gone``.
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["failed", "paused", "error", "completed_with_warnings"]
)
async def test_both_views_agree_when_the_workspace_is_gone(
    tmp_path, monkeypatch, status
):
    """The disagreement a teacher actually hits: resume offered, then refused.

    The polling summary used to infer a usable checkpoint from the presence of
    a ``workspace_id`` on the task record. ``describe_task_recovery`` loaded the
    workspace and answered ``workspace_missing``. A job whose workspace had been
    deleted therefore appeared resumable in the task list and refused on click,
    which reads as the button being broken.
    """
    manager = _manager_with_storage(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-3", course_name="课程", enqueue=False)
    task = manager.tasks[task_id]
    task["status"] = status
    task["publication_allowed"] = True
    # Recorded, but never created on disk — the state left behind when a
    # workspace is cleaned up while the task record survives.
    task["workspace_id"] = "workspace-that-was-deleted"

    expensive = manager.describe_task_recovery(task_id)
    cheap = manager._task_recovery_summary(task)

    assert expensive["can_resume"] == cheap["can_resume"], (
        f"{status}: resume says can_resume={expensive['can_resume']}, "
        f"polling says {cheap['can_resume']}"
    )
    assert expensive["reason_code"] == cheap["reason_code"]
    assert cheap["can_resume"] is False
    assert cheap["reason_code"] == "workspace_missing"


@pytest.mark.asyncio
async def test_a_live_workspace_is_still_offered_for_resume(
    tmp_path, monkeypatch
):
    """The fix must not disarm resume for jobs that can genuinely continue."""
    manager = _manager_with_storage(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-4", course_name="课程", enqueue=False)
    task = manager.tasks[task_id]
    task["status"] = "failed"
    task["publication_allowed"] = True
    workspace_id = f"workspace-{task_id}"
    manager._generation_workspace_repository.create(
        workspace_id,
        course_id="course-4",
        course_data={"course_id": "course-4", "nodes": []},
    )
    task["workspace_id"] = workspace_id

    cheap = manager._task_recovery_summary(task)
    expensive = manager.describe_task_recovery(task_id)

    assert cheap["can_resume"] is True
    assert cheap["reason_code"] != "workspace_missing"
    assert expensive["can_resume"] == cheap["can_resume"]


@pytest.mark.asyncio
async def test_v6_task_list_reports_the_same_saved_checkpoint_as_resume_endpoint(
    tmp_path,
    monkeypatch,
):
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task(
        "course-v6",
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={"target_schema": "slide_deck_v6"},
    )
    task = manager.tasks[task_id]
    failure = {
        "stage": "story",
        "code": "story_summary_markdown_invalid",
        "message": "Summary still contains Markdown",
        "retryable": True,
        "chapter_id": "chapter-4",
        "page_id": "page-3",
        "batch_id": "story-12",
    }
    task.update({
        "status": "failed",
        "phase": "story",
        "error_detail": failure,
        "slide_build_progress_v2": {"failure": failure},
    })
    checkpoint_path = (
        manager._storage_data_dir
        / "slide_deck_v6_candidates"
        / "checkpoints"
        / f"{task_id}.json"
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text("{}", encoding="utf-8")
    progress_path = (
        manager._storage_data_dir / "slide_build_progress_v2" / f"{task_id}.json"
    )
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text("{}", encoding="utf-8")

    expensive = manager.describe_task_recovery(task_id)
    cheap = manager._task_recovery_summary(task)

    assert expensive["reason_code"] == "checkpoint_available"
    assert expensive["can_resume"] is True
    assert cheap["reason_code"] == expensive["reason_code"]
    assert cheap["can_resume"] is expensive["can_resume"]
