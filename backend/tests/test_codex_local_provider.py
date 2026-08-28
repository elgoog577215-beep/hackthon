from unittest.mock import AsyncMock

import pytest

from ai_base import AIBase, AIProviderUnavailable
from codex_local_provider import CodexLocalProvider


@pytest.fixture(autouse=True)
def _select_local_codex(monkeypatch):
    monkeypatch.setenv("AI_LOCAL_PROVIDER", "codex")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_call_llm_uses_local_codex_without_http_credentials(monkeypatch):
    monkeypatch.setattr(
        CodexLocalProvider,
        "configured",
        property(lambda self: True),
    )
    call = AsyncMock(return_value='{"ok":true}')
    monkeypatch.setattr(CodexLocalProvider, "call", call)

    service = AIBase()
    result = await service._call_llm(
        "生成课程结构",
        system_prompt="只输出 JSON",
        json_mode=True,
        raise_on_failure=True,
    )

    assert result == '{"ok":true}'
    call.assert_awaited_once()
    assert call.await_args.kwargs["json_mode"] is True


@pytest.mark.asyncio
async def test_stream_llm_yields_local_codex_output(monkeypatch):
    monkeypatch.setattr(
        CodexLocalProvider,
        "configured",
        property(lambda self: True),
    )
    output = "链路生成正文" * 1200
    monkeypatch.setattr(
        CodexLocalProvider,
        "call",
        AsyncMock(return_value=output),
    )

    service = AIBase()
    chunks = [chunk async for chunk in service._stream_llm("生成正文")]

    assert chunks == [output], "整段返回的本地模型不应在事后被切块伪装成 token 流"


@pytest.mark.asyncio
async def test_missing_local_codex_is_a_structured_provider_failure(monkeypatch):
    monkeypatch.setattr(
        CodexLocalProvider,
        "configured",
        property(lambda self: False),
    )

    service = AIBase()
    with pytest.raises(AIProviderUnavailable) as caught:
        await service._call_llm("生成课程", raise_on_failure=True)

    assert caught.value.reason == "local_codex_not_configured"
