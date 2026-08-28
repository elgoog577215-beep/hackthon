"""Shared transport helpers for bounded, non-durable generation calls.

Long-running course, lesson, question-bank and slide jobs keep their existing
durable task owners.  This module only gives short structured generation calls
the same immediate start, heartbeat, terminal result and cancellation shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse


logger = logging.getLogger(__name__)


def encode_sse(event: str, payload: dict[str, Any]) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def wants_generation_stream(request: Request) -> bool:
    return "text/event-stream" in str(request.headers.get("Accept") or "").lower()


def _heartbeat_seconds() -> float:
    try:
        configured = float(os.getenv("GENERATION_STREAM_HEARTBEAT_SECONDS", "2"))
    except ValueError:
        configured = 2.0
    return max(0.05, min(configured, 15.0))


def _public_failure(error: BaseException) -> dict[str, Any]:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            code = str(detail.get("code") or "generation_failed")
            message = str(detail.get("message") or code)
            extra = {
                key: value
                for key, value in detail.items()
                if key not in {"code", "message"}
            }
        else:
            code = "generation_failed"
            message = str(detail or code)
            extra = {}
        return {
            "code": code,
            "message": message,
            "http_status": error.status_code,
            **extra,
        }
    logger.exception("Structured generation stream failed")
    return {
        "code": "generation_failed",
        "message": "AI 生成暂时不可用，请稍后重试。",
        "http_status": 500,
    }


def stream_generation_result(
    operation: Callable[[], Awaitable[Any]],
    *,
    stage: str,
    started_message: str,
    waiting_message: str,
) -> StreamingResponse:
    """Stream progress for a short structured call and publish one final result.

    Partial JSON is deliberately never exposed: callers receive progress while
    the model works, then one validated domain result.  Durable jobs must not be
    wrapped here because disconnecting this response cancels the operation.
    """

    async def event_stream():
        started_at = time.perf_counter()
        yield encode_sse(
            "started",
            {
                "status": "running",
                "stage": stage,
                "message": started_message,
                "delivery_mode": "progress_stream",
                "elapsed_ms": 0,
            },
        )
        task = asyncio.create_task(operation())
        interval = _heartbeat_seconds()
        try:
            while True:
                done, _pending = await asyncio.wait({task}, timeout=interval)
                if done:
                    break
                yield encode_sse(
                    "heartbeat",
                    {
                        "status": "running",
                        "stage": stage,
                        "message": waiting_message,
                        "delivery_mode": "progress_stream",
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                    },
                )
            try:
                result = jsonable_encoder(task.result())
            except Exception as error:  # noqa: BLE001 - normalized for the stream
                yield encode_sse(
                    "error",
                    {
                        "status": "failed",
                        "stage": stage,
                        "delivery_mode": "progress_stream",
                        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                        **_public_failure(error),
                    },
                )
                return
            yield encode_sse(
                "complete",
                {
                    "status": "completed",
                    "stage": stage,
                    "delivery_mode": "progress_stream",
                    "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                    "result": result,
                },
            )
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def structured_generation_stream(
    *,
    stage: str,
    started_message: str,
    waiting_message: str,
):
    """Add SSE progress to an existing FastAPI generation handler.

    The handler, validation and domain write path remain the sole implementation.
    Existing JSON callers are unchanged; callers asking for SSE receive the
    same operation behind a progress stream and one validated final payload.
    """

    def decorate(handler):
        @wraps(handler)
        async def wrapped(*args, **kwargs):
            request = next(
                (
                    value
                    for value in (*args, *kwargs.values())
                    if isinstance(value, Request)
                ),
                None,
            )
            if request is None or not wants_generation_stream(request):
                return await handler(*args, **kwargs)

            async def operation():
                return await handler(*args, **kwargs)

            return stream_generation_result(
                operation,
                stage=stage,
                started_message=started_message,
                waiting_message=waiting_message,
            )

        return wrapped

    return decorate


async def iter_with_heartbeats(
    source: AsyncIterator[str],
    *,
    interval_seconds: float | None = None,
) -> AsyncIterator[str | None]:
    """Relay real chunks and yield ``None`` while a provider is silent.

    A heartbeat is transport feedback, not generated text.  This distinction
    matters for buffered local providers: the UI stays responsive without
    pretending that a completed answer was token-streamed.
    """

    interval = interval_seconds or _heartbeat_seconds()
    iterator = source.__aiter__()
    pending = asyncio.create_task(anext(iterator))
    try:
        while True:
            done, _pending = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            yield item
            pending = asyncio.create_task(anext(iterator))
    finally:
        if not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        close = getattr(iterator, "aclose", None)
        if callable(close):
            await close()


__all__ = [
    "encode_sse",
    "iter_with_heartbeats",
    "stream_generation_result",
    "structured_generation_stream",
    "wants_generation_stream",
]
