from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from generation_streaming import (
    stream_generation_result,
    structured_generation_stream,
)


def _parse(block: str) -> tuple[str, dict]:
    event = ""
    data = ""
    for line in block.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
    return event, json.loads(data)


@pytest.mark.asyncio
async def test_structured_generation_starts_immediately_then_completes(monkeypatch):
    monkeypatch.setenv("GENERATION_STREAM_HEARTBEAT_SECONDS", "0.05")

    async def operation():
        await asyncio.sleep(0.08)
        return {"candidate_id": "c1"}

    response = stream_generation_result(
        operation,
        stage="candidate",
        started_message="已收到",
        waiting_message="正在生成",
    )
    stream = response.body_iterator
    first = _parse(await stream.__anext__())
    remaining = [_parse(item) async for item in stream]

    assert first[0] == "started"
    assert any(name == "heartbeat" for name, _payload in remaining)
    assert remaining[-1] == (
        "complete",
        {
            "status": "completed",
            "stage": "candidate",
            "delivery_mode": "progress_stream",
            "elapsed_ms": remaining[-1][1]["elapsed_ms"],
            "result": {"candidate_id": "c1"},
        },
    )


@pytest.mark.asyncio
async def test_structured_generation_normalizes_domain_failure():
    async def operation():
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_changed", "message": "正式内容已变化"},
        )

    response = stream_generation_result(
        operation,
        stage="candidate",
        started_message="已收到",
        waiting_message="正在生成",
    )
    events = [_parse(item) async for item in response.body_iterator]

    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "revision_changed"
    assert events[-1][1]["http_status"] == 409


@pytest.mark.asyncio
async def test_stream_decorator_keeps_one_handler_for_json_and_sse():
    calls: list[str] = []

    @structured_generation_stream(
        stage="candidate",
        started_message="已收到",
        waiting_message="正在生成",
    )
    async def handler(request: Request):
        calls.append(str(request.headers.get("accept") or ""))
        return {"candidate_id": "c1"}

    json_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/generate",
        "headers": [],
    })
    assert await handler(json_request) == {"candidate_id": "c1"}

    sse_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/generate",
        "headers": [(b"accept", b"text/event-stream")],
    })
    response = await handler(sse_request)
    events = [_parse(item) async for item in response.body_iterator]

    assert [name for name, _payload in events] == ["started", "complete"]
    assert events[-1][1]["result"] == {"candidate_id": "c1"}
    assert len(calls) == 2
