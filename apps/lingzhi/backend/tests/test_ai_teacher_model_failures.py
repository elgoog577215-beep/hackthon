"""A failed AI-teacher answer must say which kind of failure it was.

`ai_base` already classifies provider failures (auth, rate limit, quota,
timeout, truncation, budget) and fails over across configured models. The AI
teacher threw that classification away: `AIQAService.answer_question_stream`
collapsed everything into a bare `RuntimeError`, and the `/ask_events` handler
reported one hard-coded `model_unavailable` code. A teacher could not tell a
temporary rate limit (retry works) from a missing API key (retrying never
works) from an answer that was cut off mid-sentence (the partial text is real
but incomplete).

These tests pin the classification down to a stable code that survives the SSE
boundary, reusing the existing `ai_base` exceptions rather than inventing a
second taxonomy.
"""

from __future__ import annotations

import json

import pytest

from ai_base import (
    AIProviderRequestError,
    AIProviderUnavailable,
    AIRequestBudgetExceeded,
    AIResponseTruncated,
)
from ai_qa_service import AIQAService, AITeacherModelFailure, classify_model_failure
from ai_capacity import ModelCapacityCoolingDown


def _package() -> dict:
    return {"conversation": {"recent_messages": []}}


async def _drain(service: AIQAService):
    chunks = []
    async for chunk in service.answer_question_stream("解释变量", context_package=_package()):
        chunks.append(chunk)
    return chunks


def _failing_service(error: Exception) -> AIQAService:
    service = AIQAService()

    async def stream(*_args, **_kwargs):
        raise error
        yield ""  # pragma: no cover - makes this an async generator

    service._stream_llm = stream
    return service


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_retryable"),
    [
        (AIProviderUnavailable("not_configured"), "model_not_configured", False),
        (AIProviderUnavailable("authentication_failed"), "model_auth_failed", False),
        (AIRequestBudgetExceeded("prompt too large"), "model_request_too_large", False),
        (AIResponseTruncated("hit max_tokens"), "model_response_truncated", True),
        (ModelCapacityCoolingDown("model-a", 12.0), "model_rate_limited", True),
        (AIProviderRequestError("Request timed out."), "model_timeout", True),
        (AIProviderRequestError("Error code: 429 rate limit"), "model_rate_limited", True),
        (AIProviderRequestError("insufficient_quota for this key"), "model_quota_exhausted", False),
        (AIProviderRequestError("something else broke"), "model_unavailable", True),
    ],
)
def test_classify_model_failure_maps_provider_errors_to_stable_codes(
    error: Exception,
    expected_code: str,
    expected_retryable: bool,
):
    failure = classify_model_failure(error)

    assert failure.code == expected_code
    assert failure.retryable is expected_retryable
    # Every classified failure carries teacher-facing Chinese copy for the audit
    # trail; the client localizes from `code`, not from this string.
    assert failure.message


@pytest.mark.asyncio
async def test_answer_stream_raises_a_classified_failure_instead_of_bare_runtime_error():
    service = _failing_service(AIProviderRequestError("Request timed out."))

    with pytest.raises(AITeacherModelFailure) as excinfo:
        await _drain(service)

    assert excinfo.value.code == "model_timeout"
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_unparseable_provider_error_chunk_is_still_classified():
    """The provider sometimes streams its error as ordinary text."""
    service = AIQAService()

    async def stream(*_args, **_kwargs):
        yield "\n[Error: provider authentication failed]"

    service._stream_llm = stream

    with pytest.raises(AITeacherModelFailure) as excinfo:
        await _drain(service)

    assert excinfo.value.code == "model_auth_failed"
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_unconfigured_service_marker_is_classified_as_not_configured():
    service = AIQAService()

    async def stream(*_args, **_kwargs):
        yield "AI Service not configured."

    service._stream_llm = stream

    with pytest.raises(AITeacherModelFailure) as excinfo:
        await _drain(service)

    assert excinfo.value.code == "model_not_configured"
    assert excinfo.value.retryable is False


@pytest.mark.asyncio
async def test_failure_after_partial_output_keeps_the_text_already_shown():
    """A mid-stream failure must not silently drop what the learner already read."""
    service = AIQAService()

    async def stream(*_args, **_kwargs):
        yield "变量名通过绑定"
        raise AIResponseTruncated("hit max_tokens")

    service._stream_llm = stream
    seen: list[str] = []

    with pytest.raises(AITeacherModelFailure) as excinfo:
        async for chunk in service.answer_question_stream("解释变量", context_package=_package()):
            seen.append(chunk)

    assert "".join(seen) == "变量名通过绑定"
    assert excinfo.value.code == "model_response_truncated"
    assert excinfo.value.partial_text == "变量名通过绑定"


@pytest.mark.asyncio
async def test_answer_events_emits_a_classified_error_block_and_keeps_partial_answer():
    """`answer_question_events` is the SSE contract; the code must reach the wire."""
    service = AIQAService()

    async def stream(*_args, **_kwargs):
        yield "变量名通过绑定指向"
        raise AIProviderRequestError("Error code: 429 rate limit")

    service._stream_llm = stream
    blocks = [
        block
        async for block in service.answer_question_events(
            "解释变量",
            context_package=_package(),
        )
    ]

    events = _parse_sse("".join(blocks))
    answered = "".join(
        payload.get("chunk", "")
        for name, payload in events
        if name == "answer"
    )
    assert answered == "变量名通过绑定指向"

    error_events = [payload for name, payload in events if name == "error"]
    assert len(error_events) == 1
    assert error_events[0]["code"] == "model_rate_limited"
    assert error_events[0]["retryable"] is True
    assert error_events[0]["message"]
    # A failed answer has no trustworthy final answer or metadata block.
    assert not [name for name, _ in events if name == "final_answer"]


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name = ""
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if not name or not data_lines:
            continue
        try:
            parsed.append((name, json.loads("\n".join(data_lines))))
        except json.JSONDecodeError:
            continue
    return parsed
