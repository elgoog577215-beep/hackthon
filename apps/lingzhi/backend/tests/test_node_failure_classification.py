"""A failed section must explain itself with a stable code, not a raw string.

``_run_job`` already classifies whole-task failures. Per-node failures were left
storing ``str(exc)[:200]``, so a single section that failed on a provider timeout
reached the teacher as unexplained technical text — and the failure list in the
production stage inherited it.
"""

from unittest.mock import AsyncMock

import pytest

import jobs.manager as task_manager_module
from ai_base import (
    AIProviderRequestError,
    AIProviderUnavailable,
    AIRequestBudgetExceeded,
)
from jobs.manager import NodeStatus, TaskManager


class _FailingCourseService:
    """Every node generation attempt raises the configured exception."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def generate_node_content_stream(self, **_kwargs):
        self.calls += 1
        raise self.exc


class _CourseStorage:
    def __init__(self, course: dict) -> None:
        self.course = course

    def load_course(self, _course_id: str) -> dict:
        return self.course

    async def save_course(self, _course_id: str, course: dict) -> None:
        self.course = course


def _course() -> dict:
    return {
        "course_id": "c1",
        "course_name": "量子力学",
        "nodes": [
            {
                "node_id": "L2-1-1",
                "node_name": "波函数",
                "node_level": 2,
                "generation_status": "pending",
            }
        ],
    }


async def _fail_one_node(tmp_path, monkeypatch, exc: Exception, ws=None):
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    storage = _CourseStorage(_course())
    manager = TaskManager(
        storage=storage,
        course_service=_FailingCourseService(exc),
        ws_service=ws,
        max_concurrency=1,
    )
    # Keep the test fast: no backoff sleeps, single attempt.
    manager._content_max_retries = 0
    # ``_process_node`` returns immediately unless the worker loop is live.
    manager._running = True
    task_id = await manager.create_task("c1", course_name="量子力学", enqueue=False)
    manager.tasks[task_id]["status"] = "running"

    await manager._process_node(task_id, _course()["nodes"][0])
    node = storage.course["nodes"][0]
    return manager, task_id, node


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc, expected_code, expected_retryable",
    [
        (
            AIProviderRequestError("Error code: 429 limit_burst_rate reached"),
            "provider_rate_limited",
            True,
        ),
        (
            AIProviderRequestError("insufficient_quota for this organization"),
            "provider_quota_exhausted",
            False,
        ),
        (AIProviderUnavailable("authentication_failed"), "provider_auth_failed", False),
        (RuntimeError("something unmapped"), "generation_failed", True),
    ],
)
async def test_failed_node_records_a_stable_code(
    tmp_path, monkeypatch, exc, expected_code, expected_retryable
):
    _manager, _task_id, node = await _fail_one_node(tmp_path, monkeypatch, exc)

    assert node["generation_status"] == NodeStatus.ERROR.value
    assert node["error_code"] == expected_code
    assert node["error_retryable"] is expected_retryable


@pytest.mark.asyncio
async def test_failed_node_keeps_the_raw_reason_only_as_technical_detail(
    tmp_path, monkeypatch
):
    leaky = AIRequestBudgetExceeded(
        "payload 210000 tokens > budget for model Qwen/Qwen3.5-397B " + "x" * 400
    )
    _manager, _task_id, node = await _fail_one_node(tmp_path, monkeypatch, leaky)

    # The raw text stays available for the collapsible technical area, bounded,
    # but it is no longer the only thing describing the failure.
    assert node["error_summary"]
    assert len(node["error_summary"]) <= 200
    assert node["error_code"] == "generation_budget_exceeded"


@pytest.mark.asyncio
async def test_node_error_event_carries_the_code_to_the_client(tmp_path, monkeypatch):
    ws = AsyncMock()
    await _fail_one_node(
        tmp_path,
        monkeypatch,
        AIProviderUnavailable("not_configured"),
        ws=ws,
    )

    payload = ws.push_error.await_args.args[1]
    assert payload["error_code"] == "provider_auth_failed"
    assert payload["retryable"] is False
    assert payload["node_id"] == "L2-1-1"


@pytest.mark.asyncio
async def test_failure_report_reuses_the_node_code_instead_of_raw_text(
    tmp_path, monkeypatch
):
    """The report the production stage renders must carry the code too."""
    manager, task_id, node = await _fail_one_node(
        tmp_path, monkeypatch, AIProviderRequestError("429 rate limit")
    )

    report_node = manager._failed_node_report_entry(task_id, node)

    assert report_node["error_code"] == "provider_rate_limited"
    assert report_node["retryable"] is True
    assert report_node["node_name"] == "波函数"
