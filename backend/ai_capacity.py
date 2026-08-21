"""Shared adaptive capacity control for real provider requests.

Business stages may create many independent work units, but they all compete for
the same provider/model capacity.  This module queues those units instead of
letting every stage burst into the provider at once.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Callable


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


@dataclass
class ModelCapacityState:
    limit: int
    in_flight: int = 0
    cooldown_until: float = 0.0
    success_streak: int = 0
    started: int = 0
    succeeded: int = 0
    rate_limited: int = 0
    quota_exhausted: int = 0
    transient_failures: int = 0
    queue_wait_seconds_total: float = 0.0
    queue_wait_events: int = 0
    # 慢启动：没见过失败之前，每成功一次就放宽一位；见到第一次失败即退出，
    # 之后回到保守的 AIMD（每 successes_to_grow 次成功才 +1）。
    slow_start: bool = True


class ModelCapacityCoolingDown(RuntimeError):
    """The selected model cooled down while this request was queued.

    Callers should immediately try another configured model instead of making
    every already-queued request wait behind the same failed model.
    """

    def __init__(self, model_id: str, retry_after_seconds: float) -> None:
        self.model_id = model_id
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(
            f"model_capacity_cooling_down:{model_id}:"
            f"{self.retry_after_seconds:.3f}s"
        )


class CapacityLease:
    def __init__(
        self,
        controller: "ProviderCapacityController",
        model_id: str,
        queue_wait_seconds: float = 0.0,
    ) -> None:
        self._controller = controller
        self.model_id = model_id
        # A-1：排队等待时长由队列自己计量。调用方用秒表夹住 acquire() 只能
        # 量到"等了多久"，量不到"为什么等"——是并发位满了，还是 cooldown /
        # 发车间隔在压着。后者是 B-4 要对齐容量时真正要看的数。
        self.queue_wait_seconds = queue_wait_seconds
        self.queue_wait_reason = ""
        self._released = False

    @property
    def queue_wait_ms(self) -> float:
        return self.queue_wait_seconds * 1000.0

    async def __aenter__(self) -> "CapacityLease":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._controller.release(self.model_id)


class ProviderCapacityController:
    """A loop-local, provider-wide AIMD queue.

    It starts conservatively, grows only after consecutive successful streams,
    and contracts immediately when the provider reports rate or quota pressure.
    """

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.initial_limit = _env_int("AI_PROVIDER_INITIAL_CONCURRENCY", 4)
        self.max_limit = max(
            self.initial_limit,
            _env_int("AI_PROVIDER_MAX_CONCURRENCY", 16),
        )
        self.successes_to_grow = _env_int(
            "AI_PROVIDER_SUCCESSES_TO_GROW", 3
        )
        self.start_interval_seconds = _env_float(
            "AI_PROVIDER_START_INTERVAL_SECONDS", 0.1
        )
        self.post_request_interval_seconds = 0.0
        self.wait_during_cooldown = False
        self.rate_limit_backoff_seconds = _env_float(
            "AI_PROVIDER_RATE_LIMIT_BACKOFF_SECONDS", 2.0,
            minimum=0.1,
        )
        self._condition = asyncio.Condition()
        self._models: dict[str, ModelCapacityState] = {}
        self._provider_limit = self.initial_limit
        self._provider_in_flight = 0
        self._provider_success_streak = 0
        self._provider_slow_start = True
        self._next_provider_start = 0.0

    async def configure_last_resort(
        self,
        *,
        max_concurrency: int,
        start_interval_seconds: float,
        post_request_interval_seconds: float,
    ) -> None:
        """Apply a conservative profile to a credential-scoped fallback.

        Last-resort credentials are commonly shared, burst-sensitive pools.
        The profile is monotonic: later callers cannot accidentally loosen a
        controller that another caller has already constrained.
        """
        async with self._condition:
            resolved_limit = max(1, int(max_concurrency))
            self.initial_limit = min(self.initial_limit, resolved_limit)
            self.max_limit = min(self.max_limit, resolved_limit)
            self._provider_limit = min(
                self._provider_limit,
                resolved_limit,
            )
            self.start_interval_seconds = max(
                self.start_interval_seconds,
                max(0.0, float(start_interval_seconds)),
            )
            self.post_request_interval_seconds = max(
                self.post_request_interval_seconds,
                max(0.0, float(post_request_interval_seconds)),
            )
            self.wait_during_cooldown = True
            # 最后兜底的凭据通常是共享的、对突发敏感的池子：慢启动的"每成功
            # 一次就放宽一位"在这里正好是不该做的事，明确关掉。
            self._provider_slow_start = False
            for state in self._models.values():
                state.limit = min(state.limit, resolved_limit)
                state.slow_start = False
            self._condition.notify_all()

    def _state(self, model_id: str) -> ModelCapacityState:
        # 新模型要继承控制器当前的慢启动开关：`configure_last_resort` 之后
        # 才第一次出现的模型，不能又从慢启动开始。
        return self._models.setdefault(
            model_id,
            ModelCapacityState(
                limit=self.initial_limit,
                slow_start=self._provider_slow_start,
            ),
        )

    async def acquire(
        self,
        model_id: str,
        *,
        on_wait_activity: Callable[[], None] | None = None,
    ) -> CapacityLease:
        wait_started = time.monotonic()
        # 只记第一次让出的原因：那是这次请求真正被什么挡住的原因，后续轮次
        # 往往只是被唤醒后重新检查条件。
        wait_reason = ""
        while True:
            async with self._condition:
                state = self._state(model_id)
                now = time.monotonic()
                if (
                    state.cooldown_until > now
                    and not self.wait_during_cooldown
                ):
                    raise ModelCapacityCoolingDown(
                        model_id,
                        state.cooldown_until - now,
                    )
                ready_at = max(
                    self._next_provider_start,
                    state.cooldown_until
                    if self.wait_during_cooldown
                    else 0.0,
                )
                if (
                    state.in_flight < state.limit
                    and self._provider_in_flight < self._provider_limit
                    and now >= ready_at
                ):
                    state.in_flight += 1
                    self._provider_in_flight += 1
                    state.started += 1
                    self._next_provider_start = (
                        now + self.start_interval_seconds
                    )
                    waited = now - wait_started
                    state.queue_wait_seconds_total += waited
                    lease = CapacityLease(self, model_id, waited)
                    lease.queue_wait_reason = wait_reason
                    return lease

                if not wait_reason:
                    if state.in_flight >= state.limit:
                        wait_reason = "model_concurrency"
                    elif self._provider_in_flight >= self._provider_limit:
                        wait_reason = "provider_concurrency"
                    elif (
                        self.wait_during_cooldown
                        and state.cooldown_until > now
                    ):
                        wait_reason = "cooldown"
                    else:
                        wait_reason = "start_interval"
                    state.queue_wait_events += 1

                # A release will notify capacity waiters.  A cooldown/spacing
                # window needs a bounded timer so it can wake without traffic.
                timeout = None
                if now < ready_at:
                    timeout = max(0.01, ready_at - now)
                if on_wait_activity:
                    on_wait_activity()
                    timeout = min(timeout, 5.0) if timeout else 5.0
                try:
                    if timeout is None:
                        await self._condition.wait()
                    else:
                        await asyncio.wait_for(
                            self._condition.wait(), timeout=timeout
                        )
                except asyncio.TimeoutError:
                    pass

    async def release(self, model_id: str) -> None:
        async with self._condition:
            state = self._state(model_id)
            state.in_flight = max(0, state.in_flight - 1)
            self._provider_in_flight = max(
                0,
                self._provider_in_flight - 1,
            )
            self._next_provider_start = max(
                self._next_provider_start,
                time.monotonic() + self.post_request_interval_seconds,
            )
            self._condition.notify_all()

    async def report_success(self, model_id: str) -> None:
        async with self._condition:
            state = self._state(model_id)
            state.succeeded += 1
            state.success_streak += 1
            self._provider_success_streak += 1
            state.cooldown_until = 0.0
            # 生成链路的并行阶段是**短脉冲**：一门 8 课时的课，正文阶段总共
            # 也只有 8 次调用。原来的 AIMD 每 3 次成功才放宽一位，而这 3 次
            # 成功要等调用结束才拿得到——脉冲跑完了限额还没涨起来，
            # 于是"看着是并行，实际只跑出 2~3 路"。实测：8 个并发单元、
            # 单元耗时 0.4 秒，墙钟 1.11 秒（有效并行度 2.87，理想是 8）。
            #
            # 慢启动照搬 TCP 的做法：没见过失败之前每成功一次就放宽一位，
            # 撞到第一次失败立刻退出慢启动并按原来的 AIMD 收缩。
            # 这样脉冲能在头几次成功后就把限额顶上去，而"一失败就退回保守"
            # 的安全性没有变。
            if state.slow_start:
                if state.limit < self.max_limit:
                    state.limit += 1
                state.success_streak = 0
            elif (
                state.success_streak >= self.successes_to_grow
                and state.limit < self.max_limit
            ):
                state.limit += 1
                state.success_streak = 0
            if self._provider_slow_start:
                if self._provider_limit < self.max_limit:
                    self._provider_limit += 1
                self._provider_success_streak = 0
            elif (
                self._provider_success_streak
                >= self.successes_to_grow
                and self._provider_limit < self.max_limit
            ):
                self._provider_limit += 1
                self._provider_success_streak = 0
            self._condition.notify_all()

    async def report_failure(
        self,
        model_id: str,
        *,
        failure_kind: str,
        cooldown_seconds: float = 0.0,
    ) -> None:
        async with self._condition:
            state = self._state(model_id)
            state.success_streak = 0
            self._provider_success_streak = 0
            # 见到第一次失败就退出慢启动：之后只按保守的 AIMD 增长。
            # 这条对所有失败类型都生效，包括 transient——脉冲期间的偶发失败
            # 也说明"再往上顶不安全"。
            state.slow_start = False
            self._provider_slow_start = False
            now = time.monotonic()
            if failure_kind == "quota_exhausted":
                state.quota_exhausted += 1
                state.limit = 1
                self._provider_limit = max(
                    1,
                    math.ceil(self._provider_limit / 2),
                )
                state.cooldown_until = max(
                    state.cooldown_until,
                    now + max(1.0, cooldown_seconds),
                )
            elif failure_kind == "rate_limited":
                state.rate_limited += 1
                state.limit = max(1, math.ceil(state.limit / 2))
                self._provider_limit = max(
                    1,
                    math.ceil(self._provider_limit / 2),
                )
                state.cooldown_until = max(
                    state.cooldown_until,
                    now
                    + max(
                        self.rate_limit_backoff_seconds,
                        cooldown_seconds,
                    ),
                )
            else:
                state.transient_failures += 1
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "start_interval_seconds": self.start_interval_seconds,
            "post_request_interval_seconds": (
                self.post_request_interval_seconds
            ),
            "wait_during_cooldown": self.wait_during_cooldown,
            "limit": self._provider_limit,
            "in_flight": self._provider_in_flight,
            "models": {
                model_id: {
                    "limit": state.limit,
                    "in_flight": state.in_flight,
                    "started": state.started,
                    "succeeded": state.succeeded,
                    "rate_limited": state.rate_limited,
                    "quota_exhausted": state.quota_exhausted,
                    "transient_failures": state.transient_failures,
                    "queue_wait_seconds_total": round(
                        state.queue_wait_seconds_total, 3
                    ),
                    "queue_wait_events": state.queue_wait_events,
                }
                for model_id, state in self._models.items()
            },
        }


_CONTROLLERS: dict[tuple[str, int], ProviderCapacityController] = {}


def get_provider_capacity_controller(
    provider_id: str,
) -> ProviderCapacityController:
    loop = asyncio.get_running_loop()
    key = (provider_id, id(loop))
    controller = _CONTROLLERS.get(key)
    if controller is None:
        controller = ProviderCapacityController(provider_id)
        _CONTROLLERS[key] = controller
    return controller


def reset_provider_capacity_controllers() -> None:
    """Test helper; production code never discards live capacity state."""
    _CONTROLLERS.clear()
