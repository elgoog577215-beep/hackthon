from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_base import AIBase, AIProviderRequestError


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


class FakeCompletions:
    async def create(self, **_kwargs):
        return FakeStream([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                reasoning_content="内部思考不应进入运行输出",
                content=None,
            ))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                reasoning_content=None,
                content="正式答案",
            ))]),
        ])


@pytest.mark.asyncio
async def test_call_llm_does_not_print_reasoning_content(monkeypatch, capsys, caplog):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    service = AIBase()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    service.smart_models = ["test-model"]
    service.fast_models = ["test-model"]
    service._working_model_cache.clear()

    result = await service._call_llm("test", retry_count=1, enable_thinking=True)

    captured = capsys.readouterr()
    assert result == "正式答案"
    assert captured.out == ""
    assert "内部思考不应进入运行输出" not in caplog.text


def test_provider_client_disables_hidden_retries_and_bounds_timeouts(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("AI_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr("ai_base.AsyncOpenAI", fake_client)

    AIBase()

    assert captured["max_retries"] == 0
    assert captured["timeout"].read == 45
    assert captured["timeout"].connect == 7


@pytest.mark.asyncio
async def test_stream_failure_raises_typed_error_without_fake_content(monkeypatch):
    calls = []

    class FailingCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs["model"])
            raise RuntimeError("connection reset")

    monkeypatch.setenv("AI_API_KEY", "test-key")
    service = AIBase()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions())
    )
    service.smart_models = ["model-a", "model-b"]
    service._working_model_cache.clear()

    yielded = []
    with pytest.raises(AIProviderRequestError, match="connection reset"):
        async for chunk in service._stream_llm("test"):
            yielded.append(chunk)

    assert yielded == []
    assert calls == ["model-a"]
