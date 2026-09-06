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
    """兜底凭据在共享限流冷却期内：排队者要等完冷却再拿到锁，不能被踢出。

    这条用例要守住的是两件事，都与墙钟无关：

    1. `wait_during_cooldown=True` 时，已经在排队的请求**不能**收到
       `ModelCapacityCoolingDown`——那是"立刻换下一个模型"的信号，
       对共享兜底凭据是错的（换了也还是同一个池子）。
    2. 冷却结束后它**必须真的拿到**锁，不能永久卡死。

    以前这里靠墙钟断言"睡 20ms 后还没完成"，来证明"它确实等了"。
    但 8 核跑满时那个 `sleep(0.02)` 可能实际睡上百毫秒，冷却
    （100ms）早就过完了，于是假失败——实测：额外调度延迟一超过约 80ms
    必然翻车。而随机红的用例最终会被习惯性忽略，真失败也跟着被忽略。

    现在改成断言**控制器自己的时钟**：冷却窗口尚未结束时排队者不得完成。
    这个判据不依赖测试进程被调度得多快——它问的是"以控制器记录的
    cooldown_until 为准，此刻是否还在冷却期内"，而不是"墙上过了多少毫秒"。
    """
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

    # 断言①：只要控制器的冷却窗口还没走完，排队者就不该完成。
    # 用控制器记录的 cooldown_until 判断，而不是"墙上过了多久"。
    state = controller._models["model-a"]
    if time.monotonic() < state.cooldown_until:
        assert waiting.done() is False, (
            "冷却窗口内排队者就完成了——说明它没有等冷却"
        )

    # 断言②：冷却结束后必须真的拿到锁。超时给到 30 秒纯粹是"别挂死"的
    # 兜底，不是性能断言——它比冷却窗口(0.1s)大两个数量级，
    # 任何负载下都不会误判，真卡死时仍然会红。
    second = await asyncio.wait_for(waiting, timeout=30)

    # 断言③：它确实是"等出来"的，而不是绕过了冷却——等待时长必须不短于
    # 冷却窗口。这是本用例的核心，且不依赖测试进程被调度得多快。
    #
    # 注意不要断言 `queue_wait_reason == "cooldown"`：排队者入队时第一个
    # 挡住它的是 `model_concurrency`（那会儿 first 还没释放），而
    # `queue_wait_reason` 按设计只记**第一次**让出的原因
    # （`ai_capacity.py` 的 `if not wait_reason`）。冷却是它等待期间遇到的
    # 第二个原因，不会覆盖掉第一个。
    assert second.queue_wait_reason == "model_concurrency"
    assert second.queue_wait_seconds >= 0.04, (
        f"只等了 {second.queue_wait_seconds:.3f}s，短于冷却窗口 0.04s——"
        "说明它绕过了冷却"
    )
    await second.release()

    # 断言④：全程没有抛 ModelCapacityCoolingDown（抛了上面就 raise 了）。
    # 共享兜底凭据下"换个模型重试"没有意义，必须是等待语义。
    assert controller.wait_during_cooldown is True


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
