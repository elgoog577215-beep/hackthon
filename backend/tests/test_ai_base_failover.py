from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable


class FakeStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _success_stream():
    return FakeStream([
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            reasoning_content=None,
            content="ok-answer",
        ))]),
    ])


def _make_status_error(status_code: int, message: str = "boom") -> Exception:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(message, response=response, body=None)


class SequencedCompletions:
    """First model raises `first_error` on every attempt, second model succeeds."""

    def __init__(self, first_error_factory, failing_model="model-a"):
        self.first_error_factory = first_error_factory
        self.failing_model = failing_model
        self.calls = []

    async def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == self.failing_model:
            raise self.first_error_factory()
        return _success_stream()


def _make_service(monkeypatch, completions, models=("model-a", "model-b")):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    service = AIBase()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.smart_models = list(models)
    service.fast_models = list(models)
    service._working_model_cache.clear()
    service._provider_failure = None
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: httpx.ConnectTimeout("connection timed out"),
        lambda: httpx.ReadTimeout("read timed out"),
        lambda: httpx.ConnectError("connection reset by peer"),
        lambda: openai.APITimeoutError(request=httpx.Request("POST", "https://example.test")),
        lambda: _make_status_error(429, "Error code: 429 - {'error': {'message': 'Too Many Requests'}}"),
        lambda: _make_status_error(500, "Error code: 500 - {'error': {'message': 'Internal Server Error'}}"),
        lambda: _make_status_error(503, "Error code: 503 - {'error': {'message': 'Service Unavailable'}}"),
    ],
    ids=["connect-timeout", "read-timeout", "connect-error", "api-timeout-error", "429", "500", "503"],
)
async def test_call_llm_fails_over_to_next_model_on_transient_errors(monkeypatch, error_factory):
    completions = SequencedCompletions(error_factory)
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=1)

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_429_request_id_containing_403_does_not_disable_provider(monkeypatch):
    completions = SequencedCompletions(
        lambda: _make_status_error(
            429,
            (
                "Error code: 429 - daily quota exceeded; "
                "request_id=df395bfc-855a-403e-9ed9-88807996b5c2"
            ),
        )
    )
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=1)

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]
    assert service._provider_failure is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: httpx.ConnectTimeout("connection timed out"),
        lambda: _make_status_error(429, "Error code: 429 - {'error': {'message': 'Too Many Requests'}}"),
        lambda: _make_status_error(500, "Error code: 500 - {'error': {'message': 'Internal Server Error'}}"),
    ],
    ids=["connect-timeout", "429", "500"],
)
async def test_stream_llm_fails_over_to_next_model_on_transient_errors(monkeypatch, error_factory):
    completions = SequencedCompletions(error_factory)
    service = _make_service(monkeypatch, completions)

    chunks = []
    async for chunk in service._stream_llm("hi"):
        chunks.append(chunk)

    assert "".join(chunks) == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [401, 403],
)
async def test_call_llm_blocks_provider_on_authentication_error_without_trying_next_model(monkeypatch, status_code):
    error = _make_status_error(status_code, f"Error code: {status_code} - forbidden/unauthorized")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=3)

    assert result is None
    assert completions.calls == ["model-a"]
    assert service._provider_failure == "authentication_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [401, 403],
)
async def test_stream_llm_blocks_provider_on_authentication_error_without_trying_next_model(monkeypatch, status_code):
    error = _make_status_error(status_code, f"Error code: {status_code} - forbidden/unauthorized")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)

    with pytest.raises(AIProviderUnavailable):
        async for _ in service._stream_llm("hi"):
            pass

    assert completions.calls == ["model-a"]
    assert service._provider_failure == "authentication_failed"


@pytest.mark.asyncio
async def test_call_llm_still_fails_over_on_legacy_string_markers(monkeypatch):
    """Preserve existing behaviour: vendor-specific text markers still trigger failover."""
    error = RuntimeError("insufficient_quota: account balance exhausted")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=1)

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_call_llm_still_fails_over_on_rate_limit_chinese_marker(monkeypatch):
    error = RuntimeError("触发速率限制，请稍后重试")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=1)

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_call_llm_raise_on_failure_surfaces_error_after_all_candidates(monkeypatch):
    error = _make_status_error(503, "provider unavailable")
    completions = SequencedCompletions(
        lambda: error,
        failing_model="model-a",
    )
    service = _make_service(monkeypatch, completions, models=("model-a",))

    with pytest.raises(AIProviderRequestError, match="provider unavailable"):
        await service._call_llm("hi", retry_count=1, raise_on_failure=True)

    assert completions.calls == ["model-a"]


@pytest.mark.asyncio
async def test_call_llm_strict_mode_reports_missing_provider(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    service = AIBase()

    with pytest.raises(AIProviderUnavailable, match="not_configured"):
        await service._call_llm("hi", raise_on_failure=True)


def test_is_authentication_error_recognizes_403_and_forbidden():
    assert AIBase._is_authentication_error(_make_status_error(403, "forbidden"))
    assert AIBase._is_authentication_error(RuntimeError("403 Forbidden"))
    assert AIBase._is_authentication_error(RuntimeError("Forbidden: no access"))
    assert not AIBase._is_authentication_error(RuntimeError("connection reset"))
    assert not AIBase._is_authentication_error(
        _make_status_error(
            429,
            "quota exceeded; request_id=ac734b8f-4bae-4030-a8c7",
        )
    )


def test_should_try_next_model_recognizes_real_sdk_errors():
    assert AIBase._should_try_next_model(_make_status_error(429, "Too Many Requests"))
    assert AIBase._should_try_next_model(_make_status_error(500, "Internal Server Error"))
    assert AIBase._should_try_next_model(_make_status_error(502, "Bad Gateway"))
    assert AIBase._should_try_next_model(httpx.ConnectTimeout("timed out"))
    assert AIBase._should_try_next_model(
        openai.APITimeoutError(request=httpx.Request("POST", "https://example.test"))
    )
    # Non-retryable client errors should not trigger failover (they are bounded per-request errors).
    assert not AIBase._should_try_next_model(_make_status_error(400, "Bad Request"))


def test_daily_quota_model_is_skipped_after_first_failure(monkeypatch):
    completions = SequencedCompletions(
        lambda: _make_status_error(
            429,
            "You have exceeded today's quota for model-a",
        )
    )
    service = _make_service(monkeypatch, completions)

    service._cooldown_model(
        "model-a",
        _make_status_error(
            429,
            "You have exceeded today's quota for model-a",
        ),
    )

    assert service._models_for(False) == ["model-b"]
