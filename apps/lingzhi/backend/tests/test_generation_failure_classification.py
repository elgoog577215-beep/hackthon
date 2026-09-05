"""The generation worker's catch-all must publish a stable, explainable failure.

Before this, ``_run_job`` stored ``str(exc)`` as the user-facing reason, so a
provider rate limit and a corrupt workspace were indistinguishable to the
teacher. These tests drive the real worker rather than the classifier alone.
"""

import asyncio

import pytest

import jobs.manager as task_manager_module
from ai_base import AIProviderRequestError, AIProviderUnavailable
from generation_workspace import GenerationWorkspaceNotFound
from jobs.manager import TaskManager


def _manager(tmp_path, monkeypatch) -> TaskManager:
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    return manager


async def _run_failing_job(manager: TaskManager, task_id: str, exc: Exception) -> dict:
    async def boom(_task_id):
        raise exc

    manager._process_task = boom
    await manager._run_job(task_id)
    return manager.tasks[task_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc, expected_code, expected_retryable",
    [
        (
            AIProviderRequestError("Error code: 429 limit_burst_rate reached"),
            "provider_rate_limited",
            True,
        ),
        (AIProviderUnavailable("authentication_failed"), "provider_auth_failed", False),
        (GenerationWorkspaceNotFound("job-x"), "workspace_missing", False),
        (RuntimeError("something unmapped"), "generation_failed", True),
    ],
)
async def test_worker_failure_publishes_a_stable_code(
    tmp_path, monkeypatch, exc, expected_code, expected_retryable
):
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task(
        "course-1", course_name="量子力学", enqueue=False
    )

    task = await _run_failing_job(manager, task_id, exc)

    assert task["status"] == "failed"
    assert task["error_code"] == expected_code
    assert task["error_detail"]["code"] == expected_code
    assert task["error_detail"]["retryable"] is expected_retryable
    assert task["error_detail"]["translation_key"] == (
        f"taskObservability.errors.{expected_code}"
    )


@pytest.mark.asyncio
async def test_raw_provider_text_stays_technical_and_is_length_bounded(
    tmp_path, monkeypatch
):
    """Model IDs and payload sizes must not become the headline message."""
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-2", course_name="课程", enqueue=False)
    leaky = AIProviderRequestError(
        "payload 210000 tokens > budget for model Qwen/Qwen3.5-397B-A17B " + "x" * 900
    )

    task = await _run_failing_job(manager, task_id, leaky)

    assert len(task["error"]) == 500
    # The backend emits a code, not prose; the frontend resolves the sentence.
    assert not task["error_user_message"]
    assert task["error_code"] != ""


@pytest.mark.asyncio
async def test_the_projection_carries_the_code_to_the_client(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-3", course_name="课程", enqueue=False)

    await _run_failing_job(manager, task_id, AIProviderUnavailable("not_configured"))
    summary = manager.get_task_summary(task_id)

    assert summary["error_code"] == "provider_auth_failed"


@pytest.mark.asyncio
async def test_user_cancellation_is_never_reported_as_a_generation_failure(
    tmp_path, monkeypatch
):
    """Pausing races the worker; the pause must survive, not become an error."""
    manager = _manager(tmp_path, monkeypatch)
    task_id = await manager.create_task("course-4", course_name="课程", enqueue=False)
    manager.tasks[task_id]["status"] = "paused"

    task = await _run_failing_job(manager, task_id, RuntimeError("cancelled mid-flight"))

    assert task["status"] == "paused"
    assert not task.get("error_code")
