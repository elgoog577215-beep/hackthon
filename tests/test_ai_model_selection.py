import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))


class FakeStream:
    def __init__(self, text):
        self.text = text
        self.done = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.done:
            raise StopAsyncIteration
        self.done = True
        delta = SimpleNamespace(content=self.text)
        choice = SimpleNamespace(delta=delta)
        return SimpleNamespace(choices=[choice])


class FakeCompletions:
    def __init__(self):
        self.models = []
        self.extra_bodies = []

    async def create(self, model, **_kwargs):
        self.models.append(model)
        self.extra_bodies.append(_kwargs.get("extra_body"))
        if model == "bad-model":
            raise Exception("has no provider supported")
        return FakeStream("OK")


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class AuthenticationCompletions:
    def __init__(self):
        self.models = []

    async def create(self, model, **_kwargs):
        self.models.append(model)
        raise Exception("Error code: 401 - Authentication failed")


class AuthenticationClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=AuthenticationCompletions())


@pytest.mark.asyncio
async def test_call_llm_falls_back_to_next_available_model(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_CANDIDATES", "bad-model, good-model")

    from ai_base import AIBase

    AIBase._working_model_cache.clear()
    ai = AIBase()
    fake = FakeClient()
    ai.client = fake

    assert await ai._call_llm("只回复 OK", retry_count=1) == "OK"
    assert fake.chat.completions.models == ["bad-model", "good-model"]
    assert fake.chat.completions.extra_bodies[-1] == {"enable_thinking": False}
    assert ai._models_for(use_fast_model=False)[0] == "good-model"


@pytest.mark.asyncio
async def test_call_llm_can_enable_thinking_for_high_value_steps(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_CANDIDATES", "good-model")
    monkeypatch.setenv("AI_ENABLE_THINKING", "true")

    from ai_base import AIBase

    AIBase._working_model_cache.clear()
    ai = AIBase()
    fake = FakeClient()
    ai.client = fake

    assert await ai._call_llm("设计课程大纲", retry_count=1, enable_thinking=True) == "OK"
    assert fake.chat.completions.extra_bodies[-1] == {"enable_thinking": True}


@pytest.mark.asyncio
async def test_authentication_failure_stops_all_retries_and_models(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "invalid-key")
    monkeypatch.setenv("AI_MODEL_CANDIDATES", "first-model, second-model")

    from ai_base import AIBase, AIProviderUnavailable

    AIBase._working_model_cache.clear()
    ai = AIBase()
    fake = AuthenticationClient()
    ai.client = fake

    assert await ai._call_llm("测试", retry_count=3) is None
    assert fake.chat.completions.models == ["first-model"]

    with pytest.raises(AIProviderUnavailable) as exc_info:
        async for _chunk in ai._stream_llm("继续测试"):
            pass
    assert exc_info.value.retryable is False
    assert fake.chat.completions.models == ["first-model"]


def test_clean_response_text_removes_chatty_course_preamble():
    from ai_base import AIBase

    ai = AIBase()
    raw = """```markdown
好的，遵照您的指示，我将为「1.2 向量」撰写详细教学内容。

---

### 写作计划/边界确认
本节将先说明边界。

## 1.2 向量的坐标表示

正式正文。
```"""

    cleaned = ai.clean_response_text(raw)

    assert cleaned.startswith("## 1.2 向量的坐标表示")
    assert "遵照您的指示" not in cleaned
    assert "写作计划" not in cleaned
