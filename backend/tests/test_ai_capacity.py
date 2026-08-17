import asyncio
import time

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


@pytest.mark.asyncio
async def test_last_resort_profile_serializes_and_spaces_after_completion(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "4")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-last-resort")

    await controller.configure_last_resort(
        max_concurrency=1,
        start_interval_seconds=0,
        post_request_interval_seconds=0.04,
    )
    first = await controller.acquire("model-a")
    waiting = asyncio.create_task(controller.acquire("model-b"))
    await asyncio.sleep(0)
    assert waiting.done() is False

    await first.release()
    await asyncio.sleep(0.01)
    assert waiting.done() is False

    second = await asyncio.wait_for(waiting, timeout=0.2)
    await second.release()
    snapshot = controller.snapshot()
    assert snapshot["limit"] == 1
    assert snapshot["post_request_interval_seconds"] == 0.04


@pytest.mark.asyncio
async def test_last_resort_waiter_survives_shared_rate_limit_cooldown(
    monkeypatch,
):
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AI_PROVIDER_RATE_LIMIT_BACKOFF_SECONDS", "0.1")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("last-resort-cooldown")
    await controller.configure_last_resort(
        max_concurrency=1,
        start_interval_seconds=0,
        post_request_interval_seconds=0,
    )

    first = await controller.acquire("model-a")
    waiting = asyncio.create_task(controller.acquire("model-a"))
    await asyncio.sleep(0)
    await controller.report_failure(
        "model-a",
        failure_kind="rate_limited",
        cooldown_seconds=0.04,
    )
    await first.release()

    await asyncio.sleep(0.02)
    assert waiting.done() is False
    second = await asyncio.wait_for(waiting, timeout=0.3)
    await second.release()


@pytest.mark.asyncio
async def test_slow_start_grows_on_every_success_until_first_failure(
    monkeypatch,
):
    """慢启动：没见过失败之前每成功一次就放宽一位。

    生成链路的并行阶段是短脉冲（一门 8 课时的课，正文阶段总共只有 8 次
    调用）。原来每 3 次成功才 +1，脉冲跑完限额还没涨起来，下一个阶段仍然
    从低限额开始——"看着并行，实际只跑出 2~3 路"。
    """
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("AI_PROVIDER_SUCCESSES_TO_GROW", "3")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-slow-start")

    # 一次成功就应该 +1（旧行为要 3 次）
    await controller.report_success("model-a")
    assert controller.snapshot()["models"]["model-a"]["limit"] == 3
    await controller.report_success("model-a")
    assert controller.snapshot()["models"]["model-a"]["limit"] == 4


@pytest.mark.asyncio
async def test_first_failure_exits_slow_start_and_restores_conservative_aimd(
    monkeypatch,
):
    """撞到第一次失败就退出慢启动，之后回到"每 N 次成功才 +1"。

    这是慢启动的安全边界：放宽得快，但一见到压力就退回保守。
    """
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("AI_PROVIDER_SUCCESSES_TO_GROW", "3")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-exit-slow-start")

    await controller.report_success("model-a")  # 慢启动 -> 3
    await controller.report_failure(
        "model-a", failure_kind="rate_limited", cooldown_seconds=0
    )
    contracted = controller.snapshot()["models"]["model-a"]["limit"]

    # 退出慢启动后：连着 2 次成功不应该再涨（阈值是 3）
    await controller.report_success("model-a")
    await controller.report_success("model-a")
    assert controller.snapshot()["models"]["model-a"]["limit"] == contracted
    # 第 3 次才 +1
    await controller.report_success("model-a")
    assert (
        controller.snapshot()["models"]["model-a"]["limit"] == contracted + 1
    )


@pytest.mark.asyncio
async def test_last_resort_profile_disables_slow_start(monkeypatch):
    """共享的兜底凭据池对突发敏感，慢启动必须关掉——包括之后才出现的模型。"""
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "2")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("AI_PROVIDER_SUCCESSES_TO_GROW", "3")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-last-resort")
    await controller.configure_last_resort(
        max_concurrency=2,
        start_interval_seconds=0.0,
        post_request_interval_seconds=0.0,
    )

    # 配置之后才第一次出现的模型，也不能从慢启动开始
    await controller.report_success("model-new")
    await controller.report_success("model-new")
    limit = controller.snapshot()["models"]["model-new"]["limit"]
    assert limit == 2, f"兜底凭据不应被慢启动放宽，实际 limit={limit}"


@pytest.mark.asyncio
async def test_slow_start_halves_wall_clock_of_a_later_parallel_phase(
    monkeypatch,
):
    """端到端效果：慢启动让**第二个**并行阶段的墙钟减半。

    冷启动那一波受 initial_limit 约束，慢启动帮不上；它的价值在于让后续
    阶段不必从低限额重新爬。这条用例把这个区别钉住，避免把收益说过头。
    """
    monkeypatch.setenv("AI_PROVIDER_INITIAL_CONCURRENCY", "4")
    monkeypatch.setenv("AI_PROVIDER_MAX_CONCURRENCY", "16")
    monkeypatch.setenv("AI_PROVIDER_SUCCESSES_TO_GROW", "3")
    monkeypatch.setenv("AI_PROVIDER_START_INTERVAL_SECONDS", "0")
    reset_provider_capacity_controllers()
    controller = get_provider_capacity_controller("provider-phase")

    async def run_phase(units: int, duration: float) -> float:
        async def one() -> None:
            lease = await controller.acquire("model-a")
            await asyncio.sleep(duration)
            await lease.release()
            await controller.report_success("model-a")

        started = time.perf_counter()
        await asyncio.gather(*[one() for _ in range(units)])
        return time.perf_counter() - started

    unit = 0.05
    await run_phase(8, unit)            # 第一个阶段：受 initial_limit=4 约束
    second = await run_phase(8, unit)   # 第二个阶段：限额已被慢启动顶上去

    # 限额已 >= 8，第二个阶段应当一波跑完（约 1 个 unit，而不是 2 个）
    assert second < unit * 1.8, f"第二阶段仍未一波跑完：{second:.3f}s"
