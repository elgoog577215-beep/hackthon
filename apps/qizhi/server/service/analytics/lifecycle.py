import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

from service.analytics.service import record_server_event


T = TypeVar("T")
Recorder = Callable[..., Awaitable[None]]


async def instrument_stream(
    stream: AsyncIterator[T],
    *,
    user_id: str | None,
    feature: str,
    workflow_id: str,
    record: Recorder = record_server_event,
    on_success: Callable[[], Awaitable[None]] | None = None,
) -> AsyncIterator[T]:
    started = time.perf_counter()
    await record(
        event_name="task_started",
        user_id=user_id,
        feature=feature,
        workflow_id=workflow_id,
    )
    try:
        async for item in stream:
            yield item
    except (asyncio.CancelledError, GeneratorExit):
        await record(
            event_name="task_cancelled",
            user_id=user_id,
            feature=feature,
            workflow_id=workflow_id,
            outcome="cancelled",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        raise
    except Exception as exc:
        await record(
            event_name="task_failed",
            user_id=user_id,
            feature=feature,
            workflow_id=workflow_id,
            outcome="failed",
            duration_ms=int((time.perf_counter() - started) * 1000),
            properties={"error_code": type(exc).__name__},
        )
        raise
    else:
        if on_success:
            await on_success()
        await record(
            event_name="task_succeeded",
            user_id=user_id,
            feature=feature,
            workflow_id=workflow_id,
            outcome="success",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

