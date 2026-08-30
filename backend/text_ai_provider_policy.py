"""灵知文本大模型提供方边界。

私有端点由环境变量提供，本模块只固化可检查的模型 ID、
端点一致性与禁止外部文本回退规则。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse


EXPECTED_TEXT_MODEL = "qwen3.8-27b"
_FORBIDDEN_TEXT_ENV_KEYS = (
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "MODELSCOPE_MODEL_CANDIDATES",
    "MODELSCOPE_MODEL_FAST_CANDIDATES",
)


class TextAIProviderPolicyError(ValueError):
    """文本模型配置违反灵知的强制提供方边界。"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def normalize_openai_base_url(value: object) -> str:
    """规范化 OpenAI 兼容 base URL，不输出或记录原始地址。"""
    normalized = str(value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise TextAIProviderPolicyError("zju_qwen_base_url_invalid")
    path = parsed.path.rstrip("/")
    if path != "/v1":
        raise TextAIProviderPolicyError("zju_qwen_base_url_must_end_in_v1")
    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port}{path}"


def enforce_text_ai_provider_policy(
    *,
    api_base: object,
    models: Sequence[object],
    environment: Mapping[str, str] | None = None,
) -> None:
    """确保一个文本路由只使用私有 Qwen 端点与指定模型。"""
    values = environment if environment is not None else os.environ
    expected_base = values.get("ZJU_QWEN_BASE_URL", "")
    if not str(expected_base or "").strip():
        raise TextAIProviderPolicyError("zju_qwen_base_url_missing")
    if not str(values.get("ZJU_QWEN_API_KEY", "") or "").strip():
        raise TextAIProviderPolicyError("zju_qwen_api_key_missing")
    local_provider = str(values.get("AI_LOCAL_PROVIDER", "") or "").strip().lower()
    if local_provider not in {"", "http"}:
        raise TextAIProviderPolicyError("external_local_text_provider_forbidden")

    if normalize_openai_base_url(api_base) != normalize_openai_base_url(
        expected_base
    ):
        raise TextAIProviderPolicyError("text_provider_base_url_mismatch")

    normalized_models = [str(item or "").strip() for item in models]
    if not normalized_models or any(
        model != EXPECTED_TEXT_MODEL for model in normalized_models
    ):
        raise TextAIProviderPolicyError("text_provider_model_mismatch")

    if any(
        str(values.get(key, "") or "").strip()
        for key in _FORBIDDEN_TEXT_ENV_KEYS
    ):
        raise TextAIProviderPolicyError("modelscope_text_fallback_forbidden")


__all__ = [
    "EXPECTED_TEXT_MODEL",
    "TextAIProviderPolicyError",
    "enforce_text_ai_provider_policy",
    "normalize_openai_base_url",
]
