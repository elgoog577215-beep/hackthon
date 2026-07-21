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
    ) -> None:
        self._controller = controller
        self.model_id = model_id
        self._released = False

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
        self.initial_limit = _env_int("AI_PROVIDER_INITIAL_CONCURRENCY", 2)
        self.max_limit = max(
            self.initial_limit,
            _env_int("AI_PROVIDER_MAX_CONCURRENCY", 4),
        )
        self.successes_to_grow = _env_int(
            "AI_PROVIDER_SUCCESSES_TO_GROW", 3
        )
        self.start_interval_seconds = _env_float(
            "AI_PROVIDER_START_INTERVAL_SECONDS", 0.5
        )
        self.rate_limit_backoff_seconds = _env_float(
            "AI_PROVIDER_RATE_LIMIT_BACKOFF_SECONDS", 2.0,
            minimum=0.1,
        )
        self._condition = asyncio.Condition()
        self._models: dict[str, ModelCapacityState] = {}
        self._provider_limit = self.initial_limit
        self._provider_in_flight = 0
        self._provider_success_streak = 0
        self._next_provider_start = 0.0

    def _state(self, model_id: str) -> ModelCapacityState:
        return self._models.setdefault(
            model_id,
            ModelCapacityState(limit=self.initial_limit),
        )

    async def acquire(
        self,
        model_id: str,
        *,
        on_wait_activity: Callable[[], None] | None = None,
    ) -> CapacityLease:
        while True:
            async with self._condition:
                state = self._state(model_id)
                now = time.monotonic()
                if state.cooldown_until > now:
                    raise ModelCapacityCoolingDown(
                        model_id,
                        state.cooldown_until - now,
                    )
                ready_at = self._next_provider_start
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
                    return CapacityLease(self, model_id)

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
            self._condition.notify_all()

    async def report_success(self, model_id: str) -> None:
        async with self._condition:
            state = self._state(model_id)
            state.succeeded += 1
            state.success_streak += 1
            self._provider_success_streak += 1
            state.cooldown_until = 0.0
            if (
                state.success_streak >= self.successes_to_grow
                and state.limit < self.max_limit
            ):
                state.limit += 1
                state.success_streak = 0
            if (
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
