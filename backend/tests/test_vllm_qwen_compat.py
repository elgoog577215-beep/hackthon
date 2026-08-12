"""自部署 vLLM(千问) 兼容性：thinking 开关与 reasoning 字段名。

三条实测症状驱动这些用例：
1. 顶层 enable_thinking 被 vLLM 静默忽略，必须走 chat_template_kwargs；
2. 流式增量字段名是 reasoning，不是 reasoning_content；
3. thinking 吃光 max_tokens 时 content 为 null，表现为空响应+截断+熔断。
"""

from types import SimpleNamespace

import pytest

from ai_base import AIBase


def _service(monkeypatch, base="http://qwen.internal.test/v1"):
    monkeypatch.setenv("AI_API_KEY", "EMPTY")
    monkeypatch.setenv("AI_API_BASE", base)
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)
    return AIBase()


def test_thinking_switch_is_sent_in_both_shapes(monkeypatch):
    """必须带 chat_template_kwargs，同时保留扁平写法兼容其他 provider。"""
    service = _service(monkeypatch)

    body = service._thinking_extra_body(False)

    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["enable_thinking"] is False

    enabled = service._thinking_extra_body(True)
    assert enabled["chat_template_kwargs"] == {"enable_thinking": True}


def test_official_deepseek_shape_is_untouched(monkeypatch):
    """DeepSeek 分支不能被这次兼容改动影响。"""
    service = _service(monkeypatch, base="https://api.deepseek.com/v1")

    body = service._thinking_extra_body(False)

    assert body == {"thinking": {"type": "disabled"}}
    assert "chat_template_kwargs" not in body


@pytest.mark.parametrize("field_name", ["reasoning", "reasoning_content"])
def test_both_reasoning_field_names_are_read(field_name):
    """vLLM 用 reasoning，DeepSeek 系用 reasoning_content，两个都要认。"""
    delta = SimpleNamespace(**{field_name: "思考中"})

    assert AIBase._delta_reasoning(delta) == "思考中"

    message = SimpleNamespace(**{field_name: "思考中"})
    assert AIBase._message_reasoning(message) == "思考中"


def test_absent_reasoning_is_empty_not_error():
    assert AIBase._delta_reasoning(SimpleNamespace()) == ""
    assert AIBase._delta_reasoning(SimpleNamespace(reasoning=None)) == ""


@pytest.mark.asyncio
async def test_thinking_starved_response_is_named_not_reported_as_empty(
    monkeypatch,
):
    """thinking 吃光预算时，报错必须说清原因，而不是伪装成 provider 空响应。

    报成 empty_response 会走瞬时失败路径并计入熔断，把"配置问题"伪装成
    "provider 挂了"，这正是排查了好几轮的那个症状。
    """
    from ai_base import AIProviderRequestError

    class ReasoningOnlyStream:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class Completions:
        async def create(self, **_kwargs):
            return ReasoningOnlyStream([
                SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(reasoning="想了很久" * 50, content=None),
                    finish_reason=None,
                )]),
            ])

    service = _service(monkeypatch)
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    service.smart_models = ["qwen-test"]
    service.fast_models = ["qwen-test"]
    service._working_model_cache.clear()
    service._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()

    with pytest.raises(AIProviderRequestError) as excinfo:
        await service._call_llm(
            "prompt", "system", retry_count=1, raise_on_failure=True
        )

    message = str(excinfo.value)
    assert "thinking_consumed_budget" in message
    assert "reasoning_chars=" in message
    AIBase._model_failure_cache.clear()
    AIBase._model_transient_failures.clear()
