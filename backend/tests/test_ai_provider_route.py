"""A provider switch must be visible beyond the server log.

``ai_base`` fails over from the primary pool to the ModelScope last resort and
logs one warning. That is invisible to the teacher watching a course generate:
the course may be produced entirely by the backup service with no indication.
These tests pin the seam that makes the switch observable in task projections.
"""

import asyncio
from types import SimpleNamespace

import pytest

import ai_provider_route
import task_manager as task_manager_module
from ai_provider_route import (
    ROUTE_FALLBACK,
    ROUTE_PRIMARY,
    provider_route_snapshot,
    record_fallback_switch,
    record_primary_recovered,
    reset_provider_route,
)
from task_manager import TaskManager


@pytest.fixture(autouse=True)
def _clean_route():
    reset_provider_route()
    yield
    reset_provider_route()


def test_default_route_is_primary_and_reports_no_switch():
    snapshot = provider_route_snapshot()
    assert snapshot["route"] == ROUTE_PRIMARY
    assert snapshot["switched_at"] is None
    assert snapshot["switch_count"] == 0


def test_switch_records_endpoint_reason_and_time():
    record_fallback_switch(endpoint="https://api-inference.modelscope.cn/v1")
    snapshot = provider_route_snapshot()

    assert snapshot["route"] == ROUTE_FALLBACK
    assert snapshot["fallback_endpoint"] == "https://api-inference.modelscope.cn/v1"
    assert snapshot["reason_code"] == "primary_pool_exhausted"
    assert snapshot["switched_at"]
    assert snapshot["switch_count"] == 1


def test_recovery_returns_to_primary_and_clears_the_endpoint():
    record_fallback_switch(endpoint="https://backup.test/v1")
    record_primary_recovered()
    snapshot = provider_route_snapshot()

    assert snapshot["route"] == ROUTE_PRIMARY
    assert snapshot["reason_code"] == "primary_recovered"
    assert snapshot["fallback_endpoint"] is None
    # The count is kept so an operator can still see the flap.
    assert snapshot["switch_count"] == 1


def test_repeated_recovery_is_a_no_op_and_does_not_inflate_the_count():
    """Every successful primary call signals recovery; only the first matters."""
    record_fallback_switch(endpoint="https://backup.test/v1")
    record_primary_recovered()
    first = provider_route_snapshot()["switched_at"]
    for _ in range(5):
        record_primary_recovered()

    snapshot = provider_route_snapshot()
    assert snapshot["switched_at"] == first
    assert snapshot["switch_count"] == 1


def test_flapping_is_countable():
    for index in range(3):
        record_fallback_switch(endpoint=f"https://backup{index}.test/v1")
        record_primary_recovered()

    assert provider_route_snapshot()["switch_count"] == 3


def test_snapshot_is_a_copy_so_callers_cannot_corrupt_the_record():
    snapshot = provider_route_snapshot()
    snapshot["route"] = "tampered"
    assert provider_route_snapshot()["route"] == ROUTE_PRIMARY


def test_record_never_stores_a_credential():
    """Only the base URL is kept; keys must not reach a task projection."""
    record_fallback_switch(endpoint="https://api-inference.modelscope.cn/v1")
    values = " ".join(str(v) for v in provider_route_snapshot().values())
    assert "sk-" not in values
    assert "api_key" not in values


@pytest.mark.asyncio
async def test_task_summary_exposes_the_current_route(tmp_path, monkeypatch):
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    task_id = await manager.create_task("c1", course_name="量子力学", enqueue=False)

    assert manager.get_task_summary(task_id)["provider_route"]["route"] == ROUTE_PRIMARY

    record_fallback_switch(endpoint="https://api-inference.modelscope.cn/v1")
    summary = manager.get_task_summary(task_id)

    assert summary["provider_route"]["route"] == ROUTE_FALLBACK
    assert summary["provider_route"]["fallback_endpoint"]


@pytest.mark.asyncio
async def test_concurrent_switches_do_not_lose_counts():
    """One AIBase serves every job, so switches can race."""

    async def switch_and_recover(index: int) -> None:
        await asyncio.sleep(0)
        record_fallback_switch(endpoint=f"https://backup{index}.test/v1")

    await asyncio.gather(*(switch_and_recover(i) for i in range(20)))

    assert provider_route_snapshot()["switch_count"] == 20


@pytest.mark.asyncio
async def test_a_real_failover_marks_the_route_and_a_primary_success_clears_it(
    monkeypatch,
):
    """End-to-end: drive ai_base's own failover, not the recorder alone.

    Reuses the failover suite's harness so this stays honest if that changes.
    """
    # Load the failover suite by path: sibling test modules are not importable
    # by name under this project's pytest layout.
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "_failover_harness",
        Path(__file__).with_name("test_ai_base_failover.py"),
    )
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    service = harness._make_service_with_modelscope_fallback(
        monkeypatch,
        harness.AlwaysFailingCompletions(
            lambda: harness._make_status_error(429, "insufficient_quota")
        ),
        harness.SuccessfulCompletions(),
    )

    assert provider_route_snapshot()["route"] == ROUTE_PRIMARY

    result = await service._call_llm(
        "hi", retry_count=1, json_mode=True, raise_on_failure=True
    )

    assert result == "ok-answer"
    switched = provider_route_snapshot()
    assert switched["route"] == ROUTE_FALLBACK
    assert switched["fallback_endpoint"]

    # The primary answering again is what ends fallback mode. The quota errors
    # above opened two independent cooldowns — the model failure cache and the
    # per-endpoint capacity controller. Both must be cleared, or the primary is
    # never retried and this would assert nothing.
    from ai_capacity import reset_provider_capacity_controllers

    type(service)._model_failure_cache.clear()
    reset_provider_capacity_controllers()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=harness.SuccessfulCompletions())
    )
    await service._call_llm(
        "hi again", retry_count=1, json_mode=True, raise_on_failure=True
    )

    assert provider_route_snapshot()["route"] == ROUTE_PRIMARY
