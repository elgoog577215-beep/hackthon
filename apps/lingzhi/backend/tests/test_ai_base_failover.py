from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable


@pytest.fixture(autouse=True)
def _select_http_provider(monkeypatch):
    """Keep HTTP failover tests isolated from the local Codex default."""
    monkeypatch.setenv("AI_LOCAL_PROVIDER", "http")


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


class EmptyThenSuccessCompletions:
    def __init__(self, empty_model="model-a"):
        self.empty_model = empty_model
        self.calls = []

    async def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == self.empty_model:
            return FakeStream([])
        return _success_stream()


class AlwaysFailingCompletions:
    def __init__(self, error_factory):
        self.error_factory = error_factory
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs["model"])
        raise self.error_factory()


class SuccessfulCompletions:
    def __init__(self):
        self.calls = []
        self.requests = []

    async def create(self, **kwargs):
        self.calls.append(kwargs["model"])
        self.requests.append(kwargs)
        return _success_stream()


def _make_service(monkeypatch, completions, models=("model-a", "model-b")):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://primary.example.test/v1")
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("MODELSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("MODELSCOPE_MODEL", raising=False)
    monkeypatch.delenv("MODELSCOPE_MODEL_CANDIDATES", raising=False)
    monkeypatch.delenv("MODELSCOPE_MODEL_FAST_CANDIDATES", raising=False)
    service = AIBase()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.smart_models = list(models)
    service.fast_models = list(models)
    service._working_model_cache.clear()
    service._model_failure_cache.clear()
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
async def test_call_llm_cools_down_empty_model_and_fails_over(monkeypatch):
    completions = EmptyThenSuccessCompletions()
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm(
        "hi",
        retry_count=1,
        raise_on_failure=True,
    )

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]
    assert (
        service._primary_provider_scope(),
        "model-a",
    ) in service._model_failure_cache


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
async def test_shared_attempt_budget_prevents_candidate_retry_multiplication(
    monkeypatch,
):
    completions = SequencedCompletions(
        lambda: httpx.ConnectTimeout("connection timed out")
    )
    service = _make_service(monkeypatch, completions)

    with pytest.raises(AIProviderRequestError, match="connection timed out"):
        await service._call_llm(
            "hi",
            retry_count=3,
            max_attempts=1,
            raise_on_failure=True,
        )

    assert completions.calls == ["model-a"]


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
async def test_bounded_assessment_call_circuit_breaks_on_exhausted_quota(
    monkeypatch,
):
    error = RuntimeError("insufficient_quota: account balance exhausted")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)
    service.api_base = "https://quota-circuit.example.test/v1"

    with pytest.raises(AIProviderUnavailable, match="quota_exhausted"):
        await service._call_llm(
            "hi",
            retry_count=1,
            max_attempts=2,
            raise_on_failure=True,
        )

    assert completions.calls == ["model-a"]


@pytest.mark.asyncio
async def test_call_llm_still_fails_over_on_rate_limit_chinese_marker(monkeypatch):
    error = RuntimeError("触发速率限制，请稍后重试")
    completions = SequencedCompletions(lambda: error)
    service = _make_service(monkeypatch, completions)

    result = await service._call_llm("hi", retry_count=1)

    assert result == "ok-answer"
    assert completions.calls == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_quota_failed_model_is_skipped_by_later_calls(monkeypatch):
    completions = SequencedCompletions(
        lambda: _make_status_error(
            429,
            "insufficient_quota: exceeded today's quota",
        )
    )
    service = _make_service(monkeypatch, completions)

    assert await service._call_llm("first", retry_count=1) == "ok-answer"
    service._working_model_cache.clear()
    assert await service._call_llm("second", retry_count=1) == "ok-answer"

    assert completions.calls == ["model-a", "model-b", "model-b"]
    assert (
        service._primary_provider_scope(),
        "model-a",
    ) in service._model_failure_cache


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
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)
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


class TruncatedThenSuccessCompletions:
    """First attempt hits the output ceiling, the retry has room to finish."""

    def __init__(self):
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) == 1:
            return FakeStream([
                SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(
                        reasoning_content="thinking" * 40,
                        content="partial",
                    ),
                    finish_reason="length",
                )]),
            ])
        return _success_stream()


@pytest.mark.asyncio
async def test_truncated_output_retries_with_more_headroom(monkeypatch):
    completions = TruncatedThenSuccessCompletions()
    service = _make_service(monkeypatch, completions, models=("model-a",))

    result = await service._call_llm(
        "prompt",
        "system",
        retry_count=2,
        max_tokens=4096,
        reject_truncated=True,
        raise_on_failure=True,
    )

    assert result == "ok-answer"
    assert len(completions.requests) == 2
    # The retry must not repeat the same ceiling, or it just truncates again.
    assert completions.requests[0]["max_tokens"] == 4096
    assert completions.requests[1]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_truncated_output_without_retry_budget_still_raises(monkeypatch):
    completions = TruncatedThenSuccessCompletions()
    service = _make_service(monkeypatch, completions, models=("model-a",))

    with pytest.raises(AIProviderRequestError):
        await service._call_llm(
            "prompt",
            "system",
            retry_count=1,
            max_tokens=4096,
            reject_truncated=True,
            raise_on_failure=True,
        )

    assert len(completions.requests) == 1


class JsonModeRejectingCompletions:
    """First call rejects response_format with 400, then succeeds without it."""

    def __init__(self):
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if "response_format" in kwargs:
            raise _make_status_error(400, "response_format is not supported")
        return _success_stream()


@pytest.mark.asyncio
async def test_json_mode_rejection_is_cached_per_provider_model(monkeypatch):
    AIBase._json_mode_unsupported.clear()
    completions = JsonModeRejectingCompletions()
    service = _make_service(monkeypatch, completions, models=("model-a",))

    first = await service._call_llm(
        "prompt", "system", retry_count=1, json_mode=True,
        raise_on_failure=True,
    )
    assert first == "ok-answer"
    # 探测一次：带 response_format 被拒，然后去掉重发。
    assert len(completions.requests) == 2
    assert "response_format" in completions.requests[0]
    assert "response_format" not in completions.requests[1]

    second = await service._call_llm(
        "prompt", "system", retry_count=1, json_mode=True,
        raise_on_failure=True,
    )
    assert second == "ok-answer"
    # 第二次不该再浪费一次 400 往返。
    assert len(completions.requests) == 3
    assert "response_format" not in completions.requests[2]
    AIBase._json_mode_unsupported.clear()


@pytest.mark.asyncio
async def test_single_transient_failure_does_not_open_the_circuit(monkeypatch):
    """一次瞬时错误不该让全进程停摆。

    _model_failure_cache 是类属性：熔断一开，进程内所有并发槽位同时失效。
    对限流/配额耗尽这是对的，但一次网络抖动就熔断 30 秒代价过高。
    """
    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()
    service = _make_service(
        monkeypatch, SuccessfulCompletions(), models=("model-a",)
    )
    timeout = openai.APITimeoutError(
        request=httpx.Request("POST", "https://example.test")
    )

    service._cool_down_model("model-a", timeout)
    assert service._models_for(False) == ["model-a"]  # 仍可用
    service._cool_down_model("model-a", timeout)
    assert service._models_for(False) == ["model-a"]
    # 连续第 3 次才熔断。
    service._cool_down_model("model-a", timeout)
    assert service._models_for(False) == []

    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()


@pytest.mark.asyncio
async def test_rate_limit_opens_the_circuit_immediately(monkeypatch):
    """限流/配额仍必须立刻熔断——放宽这个会打爆上游。"""
    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()
    service = _make_service(
        monkeypatch, SuccessfulCompletions(), models=("model-a",)
    )

    service._cool_down_model("model-a", _make_status_error(429, "rate limit"))
    assert service._models_for(False) == []

    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()


@pytest.mark.asyncio
async def test_success_clears_a_partial_transient_streak(monkeypatch):
    """成功一次就应清零累计，避免互不相关的抖动攒成熔断。"""
    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()
    completions = SuccessfulCompletions()
    service = _make_service(monkeypatch, completions, models=("model-a",))
    timeout = openai.APITimeoutError(
        request=httpx.Request("POST", "https://example.test")
    )

    service._cool_down_model("model-a", timeout)
    service._cool_down_model("model-a", timeout)
    await service._call_llm("p", "s", retry_count=1, raise_on_failure=True)
    # 成功清零后，再来两次瞬时错误仍不该熔断。
    service._cool_down_model("model-a", timeout)
    service._cool_down_model("model-a", timeout)
    assert service._models_for(False) == ["model-a"]

    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()
