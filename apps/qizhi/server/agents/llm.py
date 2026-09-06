import os
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from infra.db import User

# 自建 vLLM 的凭据由运行环境提供。
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")

client = AsyncOpenAI(
    base_url=os.getenv("VLLM_TEXT_ENDPOINT", "http://127.0.0.1:30938/v1").split(",")[0].strip(),
    api_key=VLLM_API_KEY,
)

NON_THINKING_SAMPLING = dict(
    temperature=0.7,
    top_p=0.80,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": False},
    },
)

THINKING_SAMPLING = dict(
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": True},
    },
)


def _actor_system_prefix(actor: User | None) -> str:
    """把调用者身份注入 system prompt 前缀。即便后端 vLLM 不识别 metadata，
    模型也能看到这段 [CALLER ...] 显式标记，按身份产出受限响应。"""
    if actor is None:
        return ""
    return (
        f"[CALLER name={actor.name or ''} "
        f"zju_id={actor.zju_id or ''} "
        f"role={actor.role or 'student'}]\n\n"
    )


def _actor_metadata(actor: User | None) -> dict | None:
    """请求体级 metadata，vLLM 0.6+ 会回写到访问日志便于审计。"""
    if actor is None:
        return None
    return {
        "actor_id": actor.id,
        "actor_role": actor.role or "",
        "actor_zju_id": actor.zju_id or "",
    }


def _build_sampling(enable_thinking: bool, actor: User | None) -> dict:
    """基于全局 SAMPLING 模板复制一份，按需注入 actor metadata。
    必须深拷贝 extra_body，否则多个请求并发会互相污染。"""
    base = THINKING_SAMPLING if enable_thinking else NON_THINKING_SAMPLING
    sampling = {**base, "extra_body": {**base["extra_body"]}}
    meta = _actor_metadata(actor)
    if meta is not None:
        sampling["extra_body"]["metadata"] = meta
    return sampling


async def stream_chat(
    system_prompt: str = "",
    user_prompt: str = "",
    *,
    history: list[dict[str, str]] | None = None,
    enable_thinking: bool = False,
    actor: User | None = None,
) -> AsyncIterator[str]:
    """流式对话：构造 system + history + user 消息，流式返回模型输出。

    `actor` 透传调用者身份：会把 [CALLER ...] 注入到 system prompt 前缀，
    并把 actor metadata 注入到 vLLM 请求体（便于后端审计）。
    """
    model = await _get_model()
    messages = [{"role": "system", "content": _actor_system_prefix(actor) + system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    sampling = _build_sampling(enable_thinking, actor)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        **sampling,
    )
    async for chunk in response:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            yield content


async def complete_chat(
    system_prompt: str = "",
    user_prompt: str = "",
    *,
    history: list[dict[str, str]] | None = None,
    enable_thinking: bool = False,
    actor: User | None = None,
) -> str:
    """非流式对话：构造 system + history + user 消息，返回完整模型输出。"""
    model = await _get_model()
    messages = [{"role": "system", "content": _actor_system_prefix(actor) + system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    sampling = _build_sampling(enable_thinking, actor)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        **sampling,
    )
    return response.choices[0].message.content or ""


async def _get_model() -> str:
    """使用部署指定的模型，不根据服务端列表顺序切换模型。"""
    if not VLLM_API_KEY:
        raise RuntimeError("请配置 VLLM_API_KEY 后再调用教学模型")
    return os.getenv("VLLM_MODEL", "qwen3.8-27b")
