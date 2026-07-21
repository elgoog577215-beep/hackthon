import asyncio

import pytest

from ai_capacity import (
    ModelCapacityCoolingDown,
    get_provider_capacity_controller,
    reset_provider_capacity_controllers,
)


@pytest.mark.asyncio
async def test_provider_capacity_is_shared_and_queues_instead_of_rejecting(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    first = get_provider_capacity_controller("provider-test")
    second = get_provider_capacity_controller("provider-test")
    assert first is second

    lease = await first.acquire("model-a")
    waiting = asyncio.create_task(second.acquire("model-a"))
    await asyncio.sleep(0)
    assert waiting.done() is False

    await lease.release()
    second_lease = await asyncio.wait_for(waiting, timeout=0.2)
    await second_lease.release()
    assert first.snapshot()["models"]["model-a"]["started"] == 2


@pytest.mark.asyncio
async def test_provider_total_capacity_is_shared_across_different_models(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-cross-model")

    first = await controller.acquire("model-a")
    waiting = asyncio.create_task(controller.acquire("model-b"))
    await asyncio.sleep(0)
    assert waiting.done() is False

    await first.release()
    second = await asyncio.wait_for(waiting, timeout=0.2)
    await second.release()
    snapshot = controller.snapshot()
    assert snapshot["limit"] == 1
    assert snapshot["in_flight"] == 0


@pytest.mark.asyncio
async def test_rate_limit_contracts_capacity_and_successes_recover_it(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("AI_PROVIDER_SUCCESSES_TO_GROW", "2")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-aimd")

    await controller.report_success("model-a")
    await controller.report_success("model-a")
    assert controller.snapshot()["models"]["model-a"]["limit"] == 3

    await controller.report_failure(
        "model-a",
        failure_kind="rate_limited",
        cooldown_seconds=0,
    )
    state = controller.snapshot()["models"]["model-a"]
    assert state["limit"] == 2
    assert state["rate_limited"] == 1


@pytest.mark.asyncio
async def test_capacity_wait_emits_activity_while_queued(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-activity")
    lease = await controller.acquire("model-a")
    events: list[str] = []

    waiting = asyncio.create_task(
        controller.acquire(
            "model-a",
            on_wait_activity=lambda: events.append("waiting"),
        )
    )
    await asyncio.sleep(0.02)
    assert events
    await lease.release()
    queued_lease = await asyncio.wait_for(waiting, timeout=0.2)
    await queued_lease.release()


@pytest.mark.asyncio
async def test_queued_request_leaves_model_when_concurrent_call_opens_circuit(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-cooldown-race")
    lease = await controller.acquire("model-a")
    waiting = asyncio.create_task(controller.acquire("model-a"))
    await asyncio.sleep(0)

    await controller.report_failure(
        "model-a",
        failure_kind="rate_limited",
        cooldown_seconds=60,
    )
    await lease.release()

    with pytest.raises(ModelCapacityCoolingDown):
        await asyncio.wait_for(waiting, timeout=0.2)
