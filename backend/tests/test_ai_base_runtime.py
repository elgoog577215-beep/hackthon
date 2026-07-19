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


def _clear_model_environment(monkeypatch):
    for name in (
        "AI_MODEL_CANDIDATES",
        "AI_MODEL",
        "AI_MODEL_FAST_CANDIDATES",
        "AI_MODEL_FAST",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_official_deepseek_base_uses_official_model_defaults(monkeypatch):
    _clear_model_environment(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://api.deepseek.com/v1")

    service = AIBase()

    assert service.smart_models == ["deepseek-v4-pro"]
    assert service.fast_models == ["deepseek-v4-flash"]


def test_modelscope_defaults_use_only_verified_qwen35_pool(monkeypatch):
    _clear_model_environment(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv(
        "AI_API_BASE",
        "https://api-inference.modelscope.cn/v1",
    )

    service = AIBase()

    expected = [
        "Qwen/Qwen3.5-27B",
        "Qwen/Qwen3.5-122B-A10B",
        "Qwen/Qwen3.5-397B-A17B",
    ]
    assert service.smart_models == expected
    assert service.fast_models == expected


def test_explicit_model_configuration_is_not_overridden_for_official_deepseek(monkeypatch):
    _clear_model_environment(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://api.deepseek.com")
    monkeypatch.setenv("AI_MODEL_CANDIDATES", "my-smart-model")
    monkeypatch.setenv("AI_MODEL_FAST", "my-fast-model")

    service = AIBase()

    assert service.smart_models == ["my-smart-model"]
    assert service.fast_models == ["my-fast-model"]


@pytest.mark.asyncio
async def test_global_thinking_switch_overrides_call_site_request(monkeypatch):
    captured = {}

    class CapturingCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                    reasoning_content=None,
                    content="正式答案",
                ))]),
            ])

    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
    monkeypatch.setenv("AI_ENABLE_THINKING", "false")
    service = AIBase()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=CapturingCompletions())
    )
    service.smart_models = ["deepseek-ai/DeepSeek-V4-Pro"]
    service._working_model_cache.clear()

    result = await service._call_llm("test", retry_count=1, enable_thinking=True)

    assert result == "正式答案"
    assert captured["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    assert captured["extra_body"]["enable_thinking"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("thinking_enabled, expected_type", [(True, "enabled"), (False, "disabled")])
async def test_official_deepseek_uses_thinking_body_for_normal_calls(
    monkeypatch, thinking_enabled, expected_type
):
    captured = {}

    class CapturingCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                    reasoning_content=None,
                    content="answer",
                ))]),
            ])

    _clear_model_environment(monkeypatch)
    monkeypatch.delenv("AI_ENABLE_THINKING", raising=False)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AI_THINKING_ENABLED", str(thinking_enabled).lower())
    service = AIBase()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=CapturingCompletions()))

    assert await service._call_llm("test", retry_count=1, enable_thinking=True) == "answer"
    assert captured["extra_body"] == {"thinking": {"type": expected_type}}


@pytest.mark.asyncio
async def test_official_deepseek_uses_thinking_body_for_stream_calls(monkeypatch):
    captured = {}

    class CapturingCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                    reasoning_content=None,
                    content="answer",
                ))]),
            ])

    _clear_model_environment(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://api.deepseek.com")
    service = AIBase()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=CapturingCompletions()))

    assert [chunk async for chunk in service._stream_llm("test", enable_thinking=True)] == ["answer"]
    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_modelscope_and_non_official_deepseek_hosts_keep_modelscope_thinking_body(monkeypatch):
    captured = {}

    class CapturingCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                    reasoning_content=None,
                    content="answer",
                ))]),
            ])

    _clear_model_environment(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_API_BASE", "https://deepseek-proxy.example.com/v1")
    service = AIBase()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=CapturingCompletions()))

    assert await service._call_llm("test", retry_count=1, enable_thinking=True) == "answer"
    assert captured["extra_body"] == {"enable_thinking": True}


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
    service._model_failure_cache.clear()

    yielded = []
    with pytest.raises(AIProviderRequestError, match="connection reset"):
        async for chunk in service._stream_llm("test"):
            yielded.append(chunk)

    assert yielded == []
    assert calls == ["model-a"]
