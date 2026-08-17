"""
AI 基础服务模块 - LLM 调用层

提供与大语言模型交互的基础能力：
- AsyncOpenAI 客户端初始化与模型配置
- 通用 LLM 调用（含重试、流式聚合）
- 流式 LLM 调用（生成器）
- JSON 提取、Mermaid/LaTeX 语法修复等工具方法
- JSON 解析、章节编号提取等辅助方法

所有 AI 子服务均继承此基类。
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from ai_capacity import (
    ModelCapacityCoolingDown,
    get_provider_capacity_controller,
)
from ai_provider_route import (
    record_fallback_switch,
    record_primary_recovered,
)
from generation_telemetry import record_call as _record_generation_call
from generation_telemetry import telemetry_enabled as _generation_telemetry_on

# 添加项目根目录到系统路径以导入共享配置
project_root = Path(__file__).parent.parent
# 加载环境变量（必须在读取环境变量之前调用）
load_dotenv(project_root / ".env")
sys.path.insert(0, str(project_root))

# ============================================================================
# 配置与常量
# ============================================================================

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API密钥存在性检查（不记录密钥内容）
_api_key_present = bool(os.getenv("AI_API_KEY"))
_modelscope_fallback_key_present = bool(os.getenv("MODELSCOPE_API_KEY"))
if _api_key_present:
    logger.info("AI_API_KEY loaded successfully")
elif _modelscope_fallback_key_present:
    logger.info("Primary AI key is absent; ModelScope fallback is configured")
else:
    logger.error("No AI provider credentials found in environment variables")

DEFAULT_SMART_MODELS = [
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-122B-A10B",
    "Qwen/Qwen3.5-397B-A17B",
]

DEFAULT_FAST_MODELS = [
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-122B-A10B",
    "Qwen/Qwen3.5-397B-A17B",
]


class AIProviderUnavailable(RuntimeError):
    """Provider-wide failure that cannot be repaired by retrying another model."""

    retryable = False

    def __init__(self, reason: str = "provider_unavailable"):
        self.reason = reason
        super().__init__(f"AI provider unavailable: {reason}")


class AIProviderRequestError(RuntimeError):
    """A bounded provider request failed and may be retried by the caller."""

    retryable = True


class AIRequestBudgetExceeded(AIProviderRequestError):
    """The final request payload is too large to send safely."""

    retryable = False


class AIResponseTruncated(AIProviderRequestError):
    """The provider reached the explicit output limit."""

    retryable = True


def _env_int_min1(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(1, default)


def _parse_model_list(value: Optional[str]) -> List[str]:
    return [item.strip() for item in (value or "").replace("\n", ",").split(",") if item.strip()]


# ============================================================================
# AI 基础服务类
# ============================================================================

class AIBase:
    """
    AI 模型交互的基础抽象层。
    支持根据任务复杂性在不同模型之间切换。
    所有 AI 子服务均继承此类。
    """
    _working_model_cache = {}
    _model_failure_cache: dict[tuple[str, str], float] = {}
    # (hostname, model_id) pairs that rejected response_format with a 400.
    _json_mode_unsupported: set[tuple[str, str]] = set()
    _stream_usage_unsupported: set[tuple[str, str]] = set()
    # Consecutive transient failures per (provider, model); reset on success.
    _model_transient_failures: dict[tuple[str, str], int] = {}

    def __init__(self, *, provider_profile: str | None = None) -> None:
        # PPT planning can use an isolated provider without changing course
        # generation, assessments, or the AI teacher.  The dedicated route is
        # fail-closed when only half of the endpoint/key pair is configured so
        # a deployment can never look switched while silently using another
        # provider.
        self.provider_profile = str(provider_profile or "").strip()
        shared_api_key = os.getenv("AI_API_KEY")
        shared_api_base = os.getenv(
            "AI_API_BASE",
            "https://api-inference.modelscope.cn/v1",
        )
        ppt_api_key = os.getenv("AI_PPT_API_KEY")
        ppt_api_base = os.getenv("AI_PPT_API_BASE")
        if self.provider_profile == "ppt" and bool(ppt_api_key) != bool(ppt_api_base):
            raise AIProviderUnavailable("ppt_provider_configuration_incomplete")
        if self.provider_profile == "ppt" and ppt_api_key and ppt_api_base:
            self.api_key = ppt_api_key
            self.api_base = ppt_api_base
        else:
            self.api_key = shared_api_key
            self.api_base = shared_api_base
        self.modelscope_fallback_api_key = os.getenv("MODELSCOPE_API_KEY")
        self.modelscope_fallback_api_base = os.getenv(
            "MODELSCOPE_BASE_URL",
            "https://api-inference.modelscope.cn/v1",
        ).rstrip("/")
        self.modelscope_fallback_models = (
            _parse_model_list(os.getenv("MODELSCOPE_MODEL"))
            or ["Qwen/Qwen3.5-35B-A3B"]
        )
        smart_models = (
            _parse_model_list(os.getenv("AI_MODEL_CANDIDATES"))
            or _parse_model_list(os.getenv("AI_MODEL"))
        )
        fast_models = (
            _parse_model_list(os.getenv("AI_MODEL_FAST_CANDIDATES"))
            or _parse_model_list(os.getenv("AI_MODEL_FAST"))
        )
        if self._is_official_deepseek_base(self.api_base):
            self.smart_models = smart_models or ["deepseek-v4-pro"]
            self.fast_models = fast_models or ["deepseek-v4-flash"]
        else:
            self.smart_models = smart_models or DEFAULT_SMART_MODELS
            self.fast_models = fast_models or DEFAULT_FAST_MODELS
        self.model_smart = self.smart_models[0]
        self.model_fast = self.fast_models[0]
        self.role_models = {
            role: models
            for role, models in {
                "assessment_generator": _parse_model_list(
                    os.getenv("AI_ASSESSMENT_GENERATOR_MODELS")
                ),
                "assessment_solver": _parse_model_list(
                    os.getenv("AI_ASSESSMENT_SOLVER_MODELS")
                ),
                "assessment_reviewer": _parse_model_list(
                    os.getenv("AI_ASSESSMENT_REVIEWER_MODELS")
                ),
                "ppt_story": _parse_model_list(
                    os.getenv("AI_PPT_STORY_MODELS")
                ),
                "ppt_visual": _parse_model_list(
                    os.getenv("AI_PPT_VISUAL_MODELS")
                ),
            }.items()
            if models
        }
        # No max_tokens was ever passed to the provider before this, so every
        # call silently fell back to the provider's own default completion
        # length (commonly ~4096 tokens). Long structured-JSON outputs (e.g.
        # the natural_science pedagogy mode's blueprint, which nests
        # capability_points/mistake_points per chapter) routinely exceed that,
        # get cut off mid-string, and fail JSON parsing in a way that looks
        # like a content-quality bug rather than a truncation bug.
        self.max_tokens = int(os.getenv("AI_MAX_TOKENS", "8192"))
        self.thinking_enabled = os.getenv(
            "AI_THINKING_ENABLED",
            os.getenv("AI_ENABLE_THINKING", "true"),
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._provider_failure: str | None = None
        self._modelscope_fallback_failure: str | None = None
        self._request_spacing_lock = asyncio.Lock()
        self._last_request_started = 0.0
        self._minimum_request_interval = max(
            0.0,
            float(
                os.getenv(
                    "AI_MIN_REQUEST_INTERVAL_SECONDS",
                    "0",
                )
            ),
        )
        self._last_resort_max_concurrency = max(
            1,
            int(os.getenv("AI_LAST_RESORT_MAX_CONCURRENCY", "1")),
        )
        self._last_resort_start_interval_seconds = max(
            0.0,
            float(
                os.getenv(
                    "AI_LAST_RESORT_START_INTERVAL_SECONDS",
                    "5",
                )
            ),
        )
        self._last_resort_post_request_interval_seconds = max(
            0.0,
            float(
                os.getenv(
                    "AI_LAST_RESORT_POST_REQUEST_INTERVAL_SECONDS",
                    "15",
                )
            ),
        )
        self._last_resort_rate_limit_retries = max(
            0,
            int(os.getenv("AI_LAST_RESORT_RATE_LIMIT_RETRIES", "2")),
        )
        
        request_timeout = max(1.0, float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "180")))
        connect_timeout = max(1.0, float(os.getenv("AI_CONNECT_TIMEOUT_SECONDS", "10")))
        client_timeout = httpx.Timeout(request_timeout, connect=connect_timeout)
        if self.api_key:
            self.client = AsyncOpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
                timeout=client_timeout,
                max_retries=0,
            )
        else:
            self.client = None
            logger.warning(
                "Primary AI_API_KEY is not configured; primary route disabled"
            )

        if self.modelscope_fallback_api_key:
            self.modelscope_fallback_client = AsyncOpenAI(
                base_url=self.modelscope_fallback_api_base,
                api_key=self.modelscope_fallback_api_key,
                timeout=client_timeout,
                max_retries=0,
            )
            logger.info("ModelScope last-resort provider configured")
        else:
            self.modelscope_fallback_client = None

    @staticmethod
    def _is_official_deepseek_base(api_base: str) -> bool:
        return urlparse(api_base).hostname == "api.deepseek.com"

    def _thinking_extra_body(
        self,
        enable_thinking: bool,
        api_base: str | None = None,
    ) -> Dict:
        """Build the provider-specific switch for reasoning output.

        Three shapes are in play:

        * official DeepSeek wants a nested ``thinking`` object;
        * vLLM (e.g. a self-hosted Qwen) only honours the flag when it is
          nested under ``chat_template_kwargs`` -- a top-level
          ``enable_thinking`` is accepted and then silently ignored, so
          thinking stays on, ``message.content`` comes back null and the
          whole response looks empty and truncated;
        * other OpenAI-compatible providers use the flat form.

        The flat form is kept alongside the nested one so providers that only
        understand it keep working.
        """
        thinking_enabled = enable_thinking and self.thinking_enabled
        if self._is_official_deepseek_base(api_base or self.api_base):
            return {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}}
        return {
            "enable_thinking": thinking_enabled,
            "chat_template_kwargs": {"enable_thinking": thinking_enabled},
        }

    @staticmethod
    def _delta_reasoning(delta: Any) -> str:
        """Read one streaming delta's reasoning text.

        vLLM names the field ``reasoning`` while DeepSeek-style providers use
        ``reasoning_content``.  Reading only one of them makes a provider look
        like it is streaming nothing.
        """
        for field in ("reasoning_content", "reasoning"):
            value = getattr(delta, field, None)
            if value:
                return str(value)
        return ""

    @staticmethod
    def _message_reasoning(message: Any) -> str:
        """Read a non-streaming message's reasoning text (same two names)."""
        for field in ("reasoning_content", "reasoning"):
            value = getattr(message, field, None)
            if value:
                return str(value)
        return ""

    def _supports_json_response_format(
        self,
        api_base: str | None = None,
        model_id: str | None = None,
    ) -> bool:
        hostname = (urlparse(api_base or self.api_base).hostname or "").casefold()
        if hostname in {
            "api-inference.modelscope.cn",
            "api.modelscope.cn",
        }:
            return False
        return (
            hostname,
            str(model_id or ""),
        ) not in AIBase._json_mode_unsupported

    @classmethod
    def _remember_json_mode_unsupported(
        cls,
        api_base: str | None,
        model_id: str | None,
    ) -> None:
        """Cache one provider's 400 on ``response_format`` for later calls."""
        hostname = (urlparse(api_base or "").hostname or "").casefold()
        cls._json_mode_unsupported.add((hostname, str(model_id or "")))

    @staticmethod
    def _chunk_usage(chunk: Any) -> tuple[int, int] | None:
        """Return ``(input_tokens, output_tokens)`` from a stream chunk.

        Providers that honour ``stream_options.include_usage`` emit a final
        chunk carrying real token counts.  Real counts are worth reaching for:
        the local estimator is deliberately conservative, so a duplicate-context
        bill computed from estimates would be systematically off.
        """
        usage = getattr(chunk, "usage", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if prompt_tokens is None and completion_tokens is None:
            return None
        return (int(prompt_tokens or 0), int(completion_tokens or 0))

    def _supports_stream_usage(self, model_id: str | None = None) -> bool:
        return (
            (urlparse(self.api_base).hostname or "").casefold(),
            str(model_id or ""),
        ) not in AIBase._stream_usage_unsupported

    @classmethod
    def _remember_stream_usage_unsupported(
        cls,
        api_base: str | None,
        model_id: str | None,
    ) -> None:
        """Cache one provider's rejection of ``stream_options``.

        Without the memo a provider that 400s on the option would pay a wasted
        round trip on every instrumented call.
        """
        hostname = (urlparse(api_base or "").hostname or "").casefold()
        cls._stream_usage_unsupported.add((hostname, str(model_id or "")))

    @staticmethod
    def _uses_model_scoped_quota(api_base: str) -> bool:
        hostname = (urlparse(api_base).hostname or "").casefold()
        return hostname in {
            "api-inference.modelscope.cn",
            "api.modelscope.cn",
        }

    async def _wait_for_request_slot(self) -> None:
        if self._minimum_request_interval <= 0:
            return
        async with self._request_spacing_lock:
            now = time.monotonic()
            remaining = (
                self._minimum_request_interval
                - (now - self._last_request_started)
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_started = time.monotonic()

    def _configured_models_for(
        self,
        use_fast_model: bool,
        model_role: str | None = None,
    ) -> List[str]:
        role_models = self.role_models.get(str(model_role or ""))
        if role_models:
            return list(role_models)
        models = list(
            self.fast_models
            if use_fast_model
            else self.smart_models
        )
        if (
            model_role == "assessment_solver"
            and len(models) > 1
        ):
            return [*models[1:], models[0]]
        return models

    def _model_cache_key(
        self,
        use_fast_model: bool,
        model_role: str | None = None,
    ):
        models = self._configured_models_for(
            use_fast_model,
            model_role,
        )
        return (
            self._primary_provider_scope(),
            str(model_role or (
                "fast" if use_fast_model else "smart"
            )),
            tuple(models),
        )

    def _models_for(
        self,
        use_fast_model: bool,
        model_role: str | None = None,
    ) -> List[str]:
        models = self._configured_models_for(
            use_fast_model,
            model_role,
        )
        cached = self._working_model_cache.get(
            self._model_cache_key(
                use_fast_model,
                model_role,
            )
        )
        ordered = (
            [cached] + [model for model in models if model != cached]
            if cached in models
            else list(models)
        )
        now = time.monotonic()
        provider_scope = self._primary_provider_scope()
        available = [
            model
            for model in ordered
            if self._model_failure_cache.get((provider_scope, model), 0) <= now
        ]
        for model in ordered:
            failure_key = (provider_scope, model)
            if self._model_failure_cache.get(failure_key, 0) <= now:
                self._model_failure_cache.pop(failure_key, None)
        return available

    def _remember_model(
        self,
        use_fast_model: bool,
        model_id: str,
        model_role: str | None = None,
    ) -> None:
        self._working_model_cache[
            self._model_cache_key(
                use_fast_model,
                model_role,
            )
        ] = model_id
        provider_scope = self._primary_provider_scope()
        self._model_failure_cache.pop((provider_scope, model_id), None)
        # A success means the model is healthy again: drop any partial
        # transient streak so unrelated blips never accumulate into a trip.
        self._model_transient_failures.pop((provider_scope, model_id), None)

    @staticmethod
    def _credential_scoped_provider_id(
        api_base: str,
        api_key: str | None,
    ) -> str:
        """Separate capacity state by endpoint and credential without leaking keys."""

        credential_digest = hashlib.sha256(
            str(api_key or "anonymous").encode("utf-8")
        ).hexdigest()[:16]
        return f"{str(api_base or '').rstrip('/')}#credential-{credential_digest}"

    def _primary_provider_scope(self) -> str:
        return self._credential_scoped_provider_id(
            self.api_base,
            self.api_key,
        )

    def _fallback_provider_scope(self) -> str:
        return self._credential_scoped_provider_id(
            self.modelscope_fallback_api_base,
            self.modelscope_fallback_api_key,
        )

    @staticmethod
    def estimate_request_tokens(prompt: str, system_prompt: str) -> int:
        """Return a conservative provider-independent mixed-language estimate.

        A flat ``chars / 4`` estimate is unsafe for Chinese: one CJK character
        is commonly close to one token, while ASCII prose is usually several
        characters per token. Keep the approximation deliberately conservative
        so the local gate rejects an oversized request before provider-specific
        tokenization can matter.
        """
        text = prompt + system_prompt
        ascii_chars = sum(character.isascii() for character in text)
        non_ascii_chars = len(text) - ascii_chars
        return max(
            1,
            math.ceil(
                ascii_chars / 3.2
                + non_ascii_chars * 1.2
            ),
        )

    @classmethod
    def validate_request_budget(
        cls,
        prompt: str,
        system_prompt: str,
        max_input_tokens: int | None,
        max_input_chars: int | None = None,
    ) -> int:
        request_chars = len(prompt) + len(system_prompt)
        estimated_tokens = cls.estimate_request_tokens(prompt, system_prompt)
        if (
            (
                max_input_chars is not None
                and request_chars > max_input_chars
            )
            or (
                max_input_tokens is not None
                and estimated_tokens > max_input_tokens
            )
        ):
            raise AIRequestBudgetExceeded(
                "模型请求输入超过硬预算："
                f"estimated={estimated_tokens} tokens，"
                f"token_limit={max_input_tokens}，"
                f"chars={request_chars}，"
                f"char_limit={max_input_chars}"
            )
        return estimated_tokens

    @staticmethod
    def _model_failure_cooldown_seconds(error: Exception) -> float:
        """Choose a bounded cooldown from the failure's operational meaning."""
        status_code = AIBase._error_status_code(error)
        message = str(error).lower()
        quota_exhausted = any(marker in message for marker in (
            "insufficient_quota",
            "insufficient balance",
            "exceeded today's quota",
            "exceeded your current quota",
            "额度",
        ))
        if quota_exhausted:
            return max(
                1.0,
                float(
                    os.getenv(
                        "AI_MODEL_QUOTA_COOLDOWN_SECONDS",
                        "3600",
                    )
                ),
            )
        if status_code == 429 or any(marker in message for marker in (
            "limit_burst_rate",
            "rate limit",
            "速率限制",
        )):
            return max(
                1.0,
                float(
                    os.getenv(
                        "AI_MODEL_RATE_LIMIT_COOLDOWN_SECONDS",
                        "120",
                    )
                ),
            )
        return max(
            1.0,
            float(
                os.getenv(
                    "AI_MODEL_TRANSIENT_COOLDOWN_SECONDS",
                    "30",
                )
            ),
        )

    def _cool_down_model(
        self,
        model_id: str,
        error: Exception,
        provider_scope: str | None = None,
    ) -> None:
        """Open the circuit for one provider/model pair.

        The cache is a class attribute, so opening the circuit stops every
        concurrent slot in the process at once.  That is the right response to
        rate limiting or an exhausted quota, but far too blunt for a single
        transient error: one timeout would otherwise idle the whole run for
        the full cooldown.  Transient failures therefore have to repeat
        consecutively before the circuit opens, while a success clears the
        streak.
        """
        cooldown = self._model_failure_cooldown_seconds(error)
        resolved_scope = provider_scope or self._primary_provider_scope()
        failure_key = (resolved_scope, model_id)
        if self._capacity_failure_kind(error) == "transient":
            threshold = _env_int_min1(
                "AI_MODEL_TRANSIENT_FAILURES_TO_OPEN", 3
            )
            streak = self._model_transient_failures.get(failure_key, 0) + 1
            self._model_transient_failures[failure_key] = streak
            if streak < threshold:
                logger.warning(
                    "AI model transient failure %d/%d (Model: %s); "
                    "circuit stays closed",
                    streak,
                    threshold,
                    model_id,
                )
                return
        self._model_transient_failures.pop(failure_key, None)
        self._model_failure_cache[failure_key] = (
            time.monotonic() + cooldown
        )
        logger.warning(
            "AI model circuit opened (Model: %s, cooldown=%ss)",
            model_id,
            int(cooldown),
        )

    def _cooldown_model(
        self,
        model_id: str,
        error: Exception,
        provider_scope: str | None = None,
    ) -> None:
        """Backward-compatible spelling for callers using the older helper."""
        self._cool_down_model(model_id, error, provider_scope)

    def _modelscope_fallback_models_for(self) -> list[str]:
        now = time.monotonic()
        provider_scope = self._fallback_provider_scope()
        available = [
            model
            for model in self.modelscope_fallback_models
            if self._model_failure_cache.get(
                (provider_scope, model),
                0,
            ) <= now
        ]
        for model in self.modelscope_fallback_models:
            failure_key = (provider_scope, model)
            if self._model_failure_cache.get(failure_key, 0) <= now:
                self._model_failure_cache.pop(failure_key, None)
        return available

    def _modelscope_fallback_available(self) -> bool:
        return bool(
            self.modelscope_fallback_api_key
            and self.modelscope_fallback_client
            and not self._modelscope_fallback_failure
            and self._modelscope_fallback_models_for()
        )

    @staticmethod
    def _capacity_failure_kind(error: Exception) -> str:
        message = str(error).lower()
        if any(marker in message for marker in (
            "insufficient_quota",
            "insufficient balance",
            "exceeded today's quota",
            "exceeded your current quota",
            "额度",
        )):
            return "quota_exhausted"
        if AIBase._error_status_code(error) == 429 or any(
            marker in message
            for marker in ("limit_burst_rate", "rate limit", "速率限制")
        ):
            return "rate_limited"
        return "transient"

    def provider_capacity_snapshot(self) -> dict:
        return get_provider_capacity_controller(
            self._primary_provider_scope()
        ).snapshot()

    @staticmethod
    def _error_status_code(error: Exception) -> Optional[int]:
        """尽量从异常对象中提取 HTTP 状态码（httpx/openai SDK 常见属性）。"""
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(error, "response", None)
        if response is not None:
            resp_status = getattr(response, "status_code", None)
            if isinstance(resp_status, int):
                return resp_status
        return None

    @staticmethod
    def _is_authentication_error(error: Exception) -> bool:
        if isinstance(error, (AuthenticationError, PermissionDeniedError)):
            return True

        status_code = AIBase._error_status_code(error)
        if status_code is not None:
            return status_code in (401, 403)

        message = str(error).lower()
        has_auth_status = bool(
            re.search(r"(?<!\d)(?:401|403)(?!\d)", message)
        )
        return has_auth_status or any(marker in message for marker in (
            "authentication failed",
            "authentication_failed",
            "invalid api key",
            "invalid_api_key",
            "unauthorized",
            "forbidden",
            "permission denied",
            "permission_denied",
        ))

    def _block_provider(self, reason: str) -> None:
        self._provider_failure = reason
        logger.error("AI provider disabled for current process: %s", reason)

    @staticmethod
    def _should_try_next_model(error: Exception) -> bool:
        # 1. 优先根据真实异常类型判断（不依赖供应商特定的文案）。
        if isinstance(error, (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)):
            return True

        # httpx 原生超时/连接类异常（可能未被 openai SDK 包装）。
        if isinstance(error, (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.NetworkError,
        )):
            return True

        # 2. 根据 HTTP 状态码判断：429 与 5xx 均应触发换模型。
        status_code = AIBase._error_status_code(error)
        if status_code == 429 or (status_code is not None and 500 <= status_code < 600):
            return True

        # 3. 根据异常类型名兜底（覆盖未直接 import 的 SDK/版本特定异常类型）。
        type_name = type(error).__name__
        if any(marker in type_name for marker in (
            "Timeout",
            "Connection",
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
            "ServiceUnavailable",
        )):
            return True

        # 4. 兜底：对供应商特定的错误文案做子串匹配（保留原有行为，避免破坏既有场景）。
        message = str(error).lower()
        return any(marker in message for marker in (
            "has no provider supported",
            "insufficient_quota",
            "insufficient balance",
            "limit_burst_rate",
            "rate limit",
            "速率限制",
        ))

    # ============================================================================
    # 辅助工具方法
    # ============================================================================

    def _extract_chapter_number(self, node_name: str) -> str:
        """
        从节点名称中提取章节编号
        
        Args:
            node_name: 节点名称，如"第三章 热力学定律"
            
        Returns:
            章节编号，如"3"
        """
        chinese_nums = {
            "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"
        }
        
        patterns = [
            r"第([一二三四五六七八九十]+)章",
            r"第(\d+)章",
            r"^(\d+)\.",
            r"^(\d+) "
        ]
        
        for pattern in patterns:
            match = re.search(pattern, node_name)
            if match:
                result = match.group(1)
                if result in chinese_nums:
                    return chinese_nums[result]
                return result
        
        return "1"

    def _extract_used_cases(self, existing_content: str) -> List[str]:
        """
        从已有内容中提取已使用的案例
        
        Args:
            existing_content: 已生成的课程内容
            
        Returns:
            已使用的案例列表
        """
        used_cases = []
        
        case_patterns = [
            r"案例[：:]\s*([^\n]+)",
            r"例如[：:，]?\s*([^\n]+)",
            r"实例[：:]\s*([^\n]+)",
            r"应用场景[：:]\s*([^\n]+)",
        ]
        
        for pattern in case_patterns:
            matches = re.findall(pattern, existing_content)
            used_cases.extend(matches)
        
        return list(set(used_cases))[:10]

    # ============================================================================
    # 内容解析工具方法
    # ============================================================================
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        从 LLM 响应中稳健地提取 JSON。
        
        提取策略（按优先级）：
        1. 直接解析完整响应
        2. 从 markdown JSON 代码块提取
        3. 从任意代码块提取
        4. 从文本中查找 JSON 对象边界
        
        Args:
            text: LLM 原始响应文本
            
        Returns:
            解析后的字典，失败返回 None
        """
        logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        # 策略1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                # Some OpenAI-compatible providers ignore JSON mode and
                # emit literal newlines inside fenced-code strings. They
                # are invalid under strict JSON but still unambiguous.
                return json.loads(text, strict=False)
            except json.JSONDecodeError:
                pass

        # 辅助函数：修复 LLM 输出中的非法反斜杠转义（如 LaTeX \alpha, \beta 等）
        def _fix_invalid_escapes(s: str) -> str:
            # JSON 合法转义: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
            # 其他 \x 都是非法的，替换为 \\x
            return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)

        # 策略2: 从 markdown JSON 代码块提取
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                try:
                    return json.loads(
                        _fix_invalid_escapes(raw),
                        strict=False,
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Markdown JSON decode error after fix: {e}")

        # 策略3: 从任意代码块提取
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            raw = code_match.group(1)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                try:
                    return json.loads(
                        _fix_invalid_escapes(raw),
                        strict=False,
                    )
                except json.JSONDecodeError:
                    pass

        # 策略4: 从文本边界提取（支持对象和数组）
        for open_char, close_char in [('{', '}'), ('[', ']')]:
            try:
                start_idx = text.find(open_char)
                end_idx = text.rfind(close_char)
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = text[start_idx:end_idx+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        return json.loads(
                            _fix_invalid_escapes(json_str),
                            strict=False,
                        )
            except json.JSONDecodeError:
                continue

        # 策略5: json-repair 兜底——修复字符串内未转义引号、缺逗号、尾逗号等
        # 模型高频语法损伤（真实案例：question_analysis 输出在字符串值里携带
        # 未转义引号，前四种策略全部失败并导致整课生成失败）。
        try:
            from json_repair import repair_json

            candidate = text
            fence_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if fence_match:
                candidate = fence_match.group(1)
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, (dict, list)) and repaired:
                logger.warning(
                    "JSON extracted via json-repair fallback (chars=%d)",
                    len(candidate),
                )
                return repaired
        except Exception as repair_error:  # pragma: no cover - defensive
            logger.warning(f"json-repair fallback failed: {repair_error}")

        # 所有策略失败
        logger.warning(f"Failed to extract JSON from: {text[:500]}...")

        return None

    @staticmethod
    def _extract_json_array_entries(
        text: str,
        key: str,
    ) -> list[Dict]:
        """Recover complete array entries from a truncated JSON envelope."""
        text = re.sub(
            r'\\(?!["\\/bfnrtu])',
            r'\\\\',
            text,
        )
        marker = f'"{key}"'
        marker_index = text.find(marker)
        if marker_index < 0:
            return []
        array_index = text.find("[", marker_index + len(marker))
        if array_index < 0:
            return []
        decoder = json.JSONDecoder(strict=False)
        entries: list[Dict] = []
        cursor = array_index + 1
        while cursor < len(text):
            while (
                cursor < len(text)
                and text[cursor] in " \t\r\n,"
            ):
                cursor += 1
            if cursor >= len(text) or text[cursor] == "]":
                break
            object_index = text.find("{", cursor)
            if object_index < 0:
                break
            try:
                value, cursor = decoder.raw_decode(
                    text,
                    object_index,
                )
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                entries.append(value)
        return entries

    def _clean_mermaid_syntax(self, text: str) -> str:
        """
        修复 Mermaid 图表语法错误。
        
        主要修复：
        - 节点标签引号转义
        - 特殊字符处理
        - 不同图表类型的适配
        
        Args:
            text: 包含 Mermaid 图表的文本
            
        Returns:
            修复后的文本
        """
        pattern = r'```mermaid(.*?)```'
        
        def fix_mermaid_block(match):
            content = match.group(1)
            
            # 检测图表类型
            clean_lines = [line.strip() for line in content.split('\n') 
                           if line.strip() and not line.strip().startswith('%%')]
            
            if not clean_lines:
                return f'```mermaid{content}```'
                
            first_word = clean_lines[0].split(' ')[0]
            
            # 仅对流程图应用节点标签修复
            # 其他图表类型（序列图、类图等）的括号有特殊含义
            if first_word not in ['graph', 'flowchart']:
                return f'```mermaid{content}```'

            def safe_quote(text):
                """确保文本被双引号包裹，内部引号转义。"""
                text = text.strip()
                inner = text
                # 转义现有双引号
                inner = inner.replace('"', '\\"')
                return f'"{inner}"'

            # 修复各种节点形状的标签
            # 1. 方括号: [Text] -> ["Text"]
            content = re.sub(r'(?<!\[)\[(?![\[])([^\[\]]+?)(?<!\])\](?!\])', 
                             lambda m: f'[{safe_quote(m.group(1))}]', 
                             content)
            
            # 2. 圆括号: (Text) -> ("Text")
            content = re.sub(r'(?<!\()(\()(?![(\[])([^()]+?)(?<!\))(\))(?![\)])', 
                             lambda m: f'({safe_quote(m.group(2))})', 
                             content)
            
            # 3. 花括号: {Text} -> {"Text"}
            content = re.sub(r'(?<!\{)\{(?![{!])([^{}]+?)(?<!\})\}(?!\})', 
                             lambda m: f'{{{safe_quote(m.group(1))}}}', 
                             content)
            
            # 4. 双花括号: {{Text}} -> {{"Text"}}
            content = re.sub(r'\{\{([^{}]+?)\}\}', 
                             lambda m: f'{{{{{safe_quote(m.group(1))}}}}}', 
                             content)
            
            # 5. 双圆括号: ((Text)) -> (("Text"))
            content = re.sub(r'\(\(([^()]+?)\)\)', 
                             lambda m: f'(({safe_quote(m.group(1))}))', 
                             content)
            
            return f'```mermaid{content}```'

        return re.sub(pattern, fix_mermaid_block, text, flags=re.DOTALL)

    def _clean_latex_syntax(self, text: str) -> str:
        """
        修复和规范化 LaTeX 语法。
        
        转换规则：
        1. \\[ ... \\] -> $ ... $ (块级公式)
        2. \\( ... \\) -> $ ... $ (行内公式)
        3. 复杂环境自动包裹在 $ 中
        4. 清理多余空行
        
        Args:
            text: 包含 LaTeX 的文本
            
        Returns:
            规范化后的文本
        """
        # 1. 转换块级公式标记
        text = re.sub(r'\\\[(.*?)\\\]', r'\n$$\n\1\n$$\n', text, flags=re.DOTALL)
        
        # 2. 转换行内公式标记
        text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
        
        # 3. 确保复杂环境被 $$ 包裹
        envs = r"matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|align|align\*|equation|equation\*|cases|gather|gather\*|alignat|alignat\*"
        # Display environments must use display delimiters. Consume legacy
        # dollar runs around the environment so malformed nested shells do not
        # survive into persisted course content.
        pattern = fr'(?:\$+)?\s*(\\begin{{({envs})}}.*?\\end{{\2}})\s*(?:\$+)?'
        
        def fix_latex_block(match):
            content = match.group(1)
            return f"\n$$\n{content.strip()}\n$$\n"

        text = re.sub(pattern, fix_latex_block, text, flags=re.DOTALL)

        # Remove the obsolete single-dollar shell only when it directly wraps
        # a normalized display block. Standalone inline `$...$` formulas are
        # left untouched.
        text = re.sub(
            r'(?m)^[ \t]*\$[ \t]*\n(?=(?:[ \t]*\n)*[ \t]*\$\$[ \t]*\n)',
            '',
            text,
        )
        text = re.sub(
            r'(?m)(?<=\n\$\$)\n(?:[ \t]*\n)*[ \t]*\$[ \t]*(?=\n|$)',
            '\n',
            text,
        )
        
        # 4. 清理多余空行（最多保留2个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def clean_response_text(self, text: str) -> str:
        """
        清理 LLM 响应文本。
        
        处理流程：
        1. 去除 markdown 代码块包装
        2. 修复 LaTeX 语法
        3. 修复 Mermaid 语法
        
        Args:
            text: 原始响应文本
            
        Returns:
            清理后的文本
        """
        clean_text = text.strip()
        
        # 去除 ```markdown 包装
        if clean_text.startswith("```markdown") and clean_text.endswith("```"):
            clean_text = clean_text[11:-3].strip()

        clean_text = self._strip_response_preamble(clean_text)
            
        # 修复 LaTeX
        clean_text = self._clean_latex_syntax(clean_text)
        
        # 修复 Mermaid
        clean_text = self._clean_mermaid_syntax(clean_text)
        
        return clean_text

    @staticmethod
    def _strip_response_preamble(text: str) -> str:
        if not text:
            return ""

        heading = re.search(r"(?m)^#{1,6}\s+", text)
        if heading:
            prefix = text[:heading.start()].strip()
            if len(prefix) <= 1200 and re.search(
                r"(好的|当然|遵照|我将|我们来|我们开始|撰写|写作计划|边界确认|以下是|下面是)",
                prefix,
            ):
                text = text[heading.start():].lstrip()

        text = re.sub(
            r"^#{1,6}\s*(?:写作计划|边界确认|写作计划/边界确认)[^\n]*\n.*?(?:\n\s*(?:---|\*\*\*)\s*\n+|\n+(?=#{1,6}\s))",
            "",
            text,
            count=1,
            flags=re.DOTALL,
        ).lstrip()
        return text

    # ============================================================================
    # 核心 LLM 调用方法
    # ============================================================================
    
    async def _call_modelscope_fallback(
        self,
        prompt: str,
        system_prompt: str,
        retry_count: int,
        enable_thinking: bool,
        max_tokens: int | None,
        max_attempts: int | None,
        reject_truncated: bool,
        raise_on_failure: bool,
        json_mode: bool,
        model_role: str | None,
        on_stream_activity: Callable[[], None] | None,
        telemetry_sink: Callable[[dict], None] | None,
    ) -> str | None:
        if not self._modelscope_fallback_available():
            if raise_on_failure:
                raise AIProviderUnavailable(
                    self._modelscope_fallback_failure
                    or "modelscope_fallback_unavailable"
                )
            return None

        logger.warning(
            "Primary AI provider exhausted; switching to ModelScope fallback"
        )
        record_fallback_switch(endpoint=self.modelscope_fallback_api_base)
        last_error: Exception | None = None
        attempts = 0
        capacity = get_provider_capacity_controller(
            self._fallback_provider_scope()
        )
        await capacity.configure_last_resort(
            max_concurrency=self._last_resort_max_concurrency,
            start_interval_seconds=(
                self._last_resort_start_interval_seconds
            ),
            post_request_interval_seconds=(
                self._last_resort_post_request_interval_seconds
            ),
        )
        for model_id in self._modelscope_fallback_models_for():
            if max_attempts is not None and attempts >= max_attempts:
                break
            rate_limit_retries_left = self._last_resort_rate_limit_retries
            attempt = 0
            while attempt < retry_count + self._last_resort_rate_limit_retries:
                if max_attempts is not None and attempts >= max_attempts:
                    break
                attempts += 1
                attempt += 1
                attempt_started = time.perf_counter()
                queue_wait_ms = 0
                queue_wait_reason = ""
                physical_request_count = 0
                estimated_input_tokens = self.estimate_request_tokens(
                    prompt,
                    system_prompt,
                )

                def emit_telemetry(
                    *,
                    status: str,
                    output: str = "",
                    error: Exception | None = None,
                ) -> None:
                    if telemetry_sink is None:
                        return
                    try:
                        telemetry_sink({
                            "model_id": model_id,
                            "model_role": model_role or "",
                            "provider_attempt": attempts,
                            "physical_request_count": physical_request_count,
                            "status": status,
                            "error_code": type(error).__name__ if error else "",
                            "queue_wait_ms": queue_wait_ms,
                            "duration_ms": int(round(
                                (time.perf_counter() - attempt_started) * 1000
                            )),
                            "estimated_input_tokens": estimated_input_tokens,
                            "estimated_output_tokens": (
                                self.estimate_request_tokens(output, "")
                                if output
                                else 0
                            ),
                            "provider_route": "modelscope_fallback",
                        })
                    except Exception:
                        logger.debug(
                            "Fallback telemetry sink failed",
                            exc_info=True,
                        )

                try:
                    request_options = {
                        "model": model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": True,
                        "max_tokens": max_tokens or self.max_tokens,
                        "extra_body": self._thinking_extra_body(
                            enable_thinking,
                            self.modelscope_fallback_api_base,
                        ),
                    }
                    if json_mode and self._supports_json_response_format(
                        self.modelscope_fallback_api_base,
                        model_id=model_id,
                    ):
                        request_options["response_format"] = {
                            "type": "json_object"
                        }

                    queue_started = time.perf_counter()
                    lease = await capacity.acquire(
                        model_id,
                        on_wait_activity=on_stream_activity,
                    )
                    # 优先用队列自己量的等待时长；取不到再退回本地秒表。
                    lease_wait_ms = getattr(lease, "queue_wait_ms", None)
                    queue_wait_ms = int(round(
                        lease_wait_ms
                        if lease_wait_ms is not None
                        else (time.perf_counter() - queue_started) * 1000
                    ))
                    queue_wait_reason = getattr(
                        lease, "queue_wait_reason", ""
                    )
                    try:
                        try:
                            await self._wait_for_request_slot()
                            physical_request_count += 1
                            response = await (
                                self.modelscope_fallback_client
                                .chat.completions.create(**request_options)
                            )
                        except Exception as format_error:
                            if not (
                                json_mode
                                and self._error_status_code(format_error) == 400
                            ):
                                raise
                            request_options.pop("response_format", None)
                            await self._wait_for_request_slot()
                            physical_request_count += 1
                            response = await (
                                self.modelscope_fallback_client
                                .chat.completions.create(**request_options)
                            )

                        full_content = ""
                        truncated = False
                        async for chunk in response:
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            reasoning = self._delta_reasoning(delta)
                            if reasoning and on_stream_activity:
                                on_stream_activity()
                            if delta.content:
                                full_content += delta.content
                                if on_stream_activity:
                                    on_stream_activity()
                            if getattr(
                                chunk.choices[0],
                                "finish_reason",
                                None,
                            ) == "length":
                                truncated = True
                    finally:
                        await lease.release()

                    if truncated and reject_truncated:
                        raise AIResponseTruncated(
                            "ModelScope fallback output reached max_tokens="
                            f"{max_tokens or self.max_tokens}"
                        )
                    if not full_content:
                        empty_error = AIProviderRequestError(
                            f"empty_response:{model_id}"
                        )
                        last_error = empty_error
                        emit_telemetry(
                            status="empty_response",
                            error=empty_error,
                        )
                        await capacity.report_failure(
                            model_id,
                            failure_kind="transient",
                        )
                        self._cool_down_model(
                            model_id,
                            empty_error,
                            self._fallback_provider_scope(),
                        )
                        break

                    await capacity.report_success(model_id)
                    emit_telemetry(status="completed", output=full_content)
                    logger.info(
                        "ModelScope fallback response complete (Model: %s)",
                        model_id,
                    )
                    return full_content
                except Exception as error:
                    last_error = error
                    emit_telemetry(status="failed", error=error)
                    logger.error(
                        "ModelScope fallback error (Model: %s, Attempt %s/%s): %s",
                        model_id,
                        attempt,
                        retry_count + self._last_resort_rate_limit_retries,
                        error,
                    )
                    if isinstance(error, ModelCapacityCoolingDown):
                        break
                    if self._is_authentication_error(error):
                        self._modelscope_fallback_failure = (
                            "authentication_failed"
                        )
                        break
                    if self._should_try_next_model(error):
                        failure_kind = self._capacity_failure_kind(error)
                        cooldown_seconds = (
                            self._model_failure_cooldown_seconds(error)
                        )
                        await capacity.report_failure(
                            model_id,
                            failure_kind=failure_kind,
                            cooldown_seconds=cooldown_seconds,
                        )
                        # The shared last-resort capacity controller is
                        # configured to queue during a rate-limit cooldown.
                        # Mirroring that temporary cooldown into the
                        # process-wide model circuit makes concurrent callers
                        # conclude that no fallback exists and surface the
                        # primary provider's quota error instead of waiting.
                        # Persistent quota/transient failures still use the
                        # circuit so another configured fallback model can be
                        # selected immediately.
                        if failure_kind != "rate_limited":
                            self._cool_down_model(
                                model_id,
                                error,
                                self._fallback_provider_scope(),
                            )
                        if (
                            failure_kind == "rate_limited"
                            and rate_limit_retries_left > 0
                            and (
                                max_attempts is None
                                or attempts < max_attempts
                            )
                        ):
                            rate_limit_retries_left -= 1
                            wait_seconds = max(
                                cooldown_seconds,
                                capacity.rate_limit_backoff_seconds,
                            )
                            await self._wait_with_activity(
                                wait_seconds,
                                on_stream_activity,
                            )
                            self._modelscope_fallback_models_for()
                            continue
                        break
                    if attempt < retry_count:
                        await asyncio.sleep(2 ** (attempt - 1))
                    else:
                        break
            if self._modelscope_fallback_failure:
                break

        if raise_on_failure:
            if self._modelscope_fallback_failure:
                raise AIProviderUnavailable(
                    self._modelscope_fallback_failure
                ) from last_error
            if last_error is not None:
                raise AIProviderRequestError(str(last_error)) from last_error
            raise AIProviderRequestError("ModelScope fallback has no available model")
        return None

    @staticmethod
    async def _wait_with_activity(
        seconds: float,
        on_activity: Callable[[], None] | None,
    ) -> None:
        """Wait in heartbeat-sized slices so callers remain observable."""
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            if on_activity:
                on_activity()
            interval = min(5.0, remaining)
            await asyncio.sleep(interval)
            remaining -= interval

    async def _stream_modelscope_fallback(
        self,
        prompt: str,
        system_prompt: str,
        enable_thinking: bool,
        max_tokens: int | None,
        max_attempts: int | None,
        on_stream_activity: Callable[[], None] | None,
    ) -> AsyncIterator[str]:
        if not self._modelscope_fallback_available():
            raise AIProviderUnavailable(
                self._modelscope_fallback_failure
                or "modelscope_fallback_unavailable"
            )

        logger.warning(
            "Primary AI provider exhausted; switching stream to ModelScope fallback"
        )
        record_fallback_switch(endpoint=self.modelscope_fallback_api_base)
        last_error: Exception | None = None
        attempts = 0
        capacity = get_provider_capacity_controller(
            self._fallback_provider_scope()
        )
        await capacity.configure_last_resort(
            max_concurrency=self._last_resort_max_concurrency,
            start_interval_seconds=(
                self._last_resort_start_interval_seconds
            ),
            post_request_interval_seconds=(
                self._last_resort_post_request_interval_seconds
            ),
        )
        for model_id in self._modelscope_fallback_models_for():
            if max_attempts is not None and attempts >= max_attempts:
                break
            attempts += 1
            yielded = False
            try:
                lease = await capacity.acquire(
                    model_id,
                    on_wait_activity=on_stream_activity,
                )
                try:
                    await self._wait_for_request_slot()
                    response = await (
                        self.modelscope_fallback_client
                        .chat.completions.create(
                            model=model_id,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            stream=True,
                            max_tokens=max_tokens or self.max_tokens,
                            extra_body=self._thinking_extra_body(
                                enable_thinking,
                                self.modelscope_fallback_api_base,
                            ),
                        )
                    )
                    truncated = False
                    async for chunk in response:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        reasoning = self._delta_reasoning(delta)
                        if reasoning and on_stream_activity:
                            on_stream_activity()
                        if delta.content:
                            yielded = True
                            if on_stream_activity:
                                on_stream_activity()
                            yield delta.content
                        if getattr(
                            chunk.choices[0],
                            "finish_reason",
                            None,
                        ) == "length":
                            truncated = True
                finally:
                    await lease.release()
                if truncated:
                    raise AIResponseTruncated(
                        "ModelScope fallback stream reached max_tokens="
                        f"{max_tokens or self.max_tokens}"
                    )
                if yielded:
                    await capacity.report_success(model_id)
                    return
                last_error = AIProviderRequestError(
                    f"Model {model_id} returned an empty stream"
                )
            except Exception as error:
                last_error = error
                logger.error(
                    "ModelScope fallback stream error (Model: %s): %s",
                    model_id,
                    error,
                )
                if isinstance(error, ModelCapacityCoolingDown):
                    continue
                if self._is_authentication_error(error):
                    self._modelscope_fallback_failure = (
                        "authentication_failed"
                    )
                    break
                should_try_next = self._should_try_next_model(error)
                if should_try_next:
                    failure_kind = self._capacity_failure_kind(error)
                    await capacity.report_failure(
                        model_id,
                        failure_kind=failure_kind,
                        cooldown_seconds=(
                            self._model_failure_cooldown_seconds(error)
                        ),
                    )
                    if failure_kind != "rate_limited":
                        self._cool_down_model(
                            model_id,
                            error,
                            self._fallback_provider_scope(),
                        )
                if yielded or not should_try_next:
                    if isinstance(error, AIProviderRequestError):
                        raise
                    raise AIProviderRequestError(str(error)) from error

        if self._modelscope_fallback_failure:
            raise AIProviderUnavailable(
                self._modelscope_fallback_failure
            ) from last_error
        if isinstance(last_error, AIProviderRequestError):
            raise last_error
        if last_error is not None:
            raise AIProviderRequestError(str(last_error)) from last_error
        raise AIProviderRequestError("ModelScope fallback has no available model")

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        use_fast_model: bool = False,
        retry_count: int = 3,
        enable_thinking: bool = False,
        max_tokens: int | None = None,
        max_input_tokens: int | None = None,
        max_input_chars: int | None = None,
        max_attempts: int | None = None,
        reject_truncated: bool = False,
        raise_on_failure: bool = False,
        json_mode: bool = False,
        model_role: str | None = None,
        on_stream_activity: Callable[[], None] | None = None,
        telemetry_sink: Callable[[dict], None] | None = None,
    ) -> Optional[str]:
        """
        通用 LLM 调用函数。
        
        特性：
        - 支持模型路由（智能模型 vs 快速模型）
        - 支持流式响应
        - 自动处理推理内容日志
        - 包含重试机制
        
        Args:
            prompt: 用户输入提示
            system_prompt: 系统指令
            use_fast_model: 是否使用轻量/快速模型
            retry_count: 最大重试次数
            enable_thinking: 是否为高价值环节启用模型思考能力
            max_tokens: 单次调用允许的最大输出 token 数，默认取
                `self.max_tokens`（环境变量 AI_MAX_TOKENS，默认 8192）。
                输出型任务（如课程蓝图 JSON）应显式传入更大的值。
            max_input_tokens: 最终 system + user prompt 的硬输入预算。
            max_input_chars: 最终请求的独立字符数硬上限。
            max_attempts: 跨候选模型共享的提供方总尝试次数。
            reject_truncated: 输出达到 max_tokens 时是否直接报告截断。
            raise_on_failure: 失败时是否抛出统一的提供方异常，而不是返回 None

        Returns:
            LLM 完整响应文本，失败返回 None
        """
        self.validate_request_budget(
            prompt,
            system_prompt,
            max_input_tokens,
            max_input_chars,
        )
        if not self.api_key and not self.modelscope_fallback_api_key:
            if raise_on_failure:
                raise AIProviderUnavailable("not_configured")
            return None
        if (
            self._provider_failure
            and not self._modelscope_fallback_available()
        ):
            if raise_on_failure:
                raise AIProviderUnavailable(self._provider_failure)
            return None

        last_error: Exception | None = None
        attempts = 0
        # A truncated answer is not a transient network blip: retrying at the
        # same ceiling usually truncates again.  Reasoning models spend this
        # same budget on hidden thinking tokens, so the retry only pays off
        # with real headroom.
        requested_max_tokens = max_tokens or self.max_tokens
        effective_max_tokens = requested_max_tokens
        truncation_headroom_ceiling = max(
            self.max_tokens,
            requested_max_tokens * 2,
        )
        primary_models = (
            self._models_for(use_fast_model, model_role)
            if self.api_key and not self._provider_failure
            else []
        )
        fallback_eligible = not primary_models
        for model_id in primary_models:
            if max_attempts is not None and attempts >= max_attempts:
                break
            for attempt in range(retry_count):
                if max_attempts is not None and attempts >= max_attempts:
                    break
                attempts += 1
                attempt_started = time.perf_counter()
                queue_wait_ms = 0
                queue_wait_reason = ""
                physical_request_count = 0
                real_usage: tuple[int, int] | None = None
                first_token_at: float | None = None
                estimated_input_tokens = self.estimate_request_tokens(
                    prompt,
                    system_prompt,
                )

                def emit_generation_record(
                    *,
                    status: str,
                    output: str = "",
                    error: Exception | None = None,
                ) -> None:
                    """A-1 全链路账单：请求统一出口的唯一打点。"""
                    if not _generation_telemetry_on():
                        return
                    _record_generation_call(
                        model_id=model_id,
                        model_role=model_role or "",
                        status=status,
                        stream=False,
                        attempt=attempts,
                        queue_wait_ms=queue_wait_ms,
                        duration_ms=(
                            (time.perf_counter() - attempt_started) * 1000
                        ),
                        ttfb_ms=(
                            None
                            if first_token_at is None
                            else (first_token_at - attempt_started) * 1000
                        ),
                        prompt=prompt,
                        system_prompt=system_prompt,
                        output_text=output,
                        input_tokens=(
                            real_usage[0] if real_usage else None
                        ),
                        output_tokens=(
                            real_usage[1] if real_usage else None
                        ),
                        tokens_source="provider" if real_usage else "estimate",
                        retry_reason=(
                            type(error).__name__ if error else ""
                        ),
                        error_code=str(error)[:200] if error else "",
                        physical_request_count=physical_request_count,
                        provider_scope=self._primary_provider_scope(),
                        extra={"queue_wait_reason": queue_wait_reason},
                    )

                def emit_telemetry(
                    *,
                    status: str,
                    output: str = "",
                    error: Exception | None = None,
                ) -> None:
                    # 账单打点与既有 sink 走同一批出口，避免漏记某条分支。
                    emit_generation_record(
                        status=status,
                        output=output,
                        error=error,
                    )
                    if telemetry_sink is None:
                        return
                    try:
                        telemetry_sink({
                            "model_id": model_id,
                            "model_role": model_role or "",
                            "provider_attempt": attempts,
                            "physical_request_count": (
                                physical_request_count
                            ),
                            "status": status,
                            "error_code": (
                                type(error).__name__ if error else ""
                            ),
                            "queue_wait_ms": queue_wait_ms,
                            "duration_ms": int(round(
                                (time.perf_counter() - attempt_started)
                                * 1000
                            )),
                            "estimated_input_tokens": (
                                estimated_input_tokens
                            ),
                            "estimated_output_tokens": (
                                self.estimate_request_tokens(output, "")
                                if output
                                else 0
                            ),
                        })
                    except Exception:
                        logger.debug(
                            "Assessment telemetry sink failed",
                            exc_info=True,
                        )
                try:
                    extra_body = self._thinking_extra_body(enable_thinking)
                    capacity = get_provider_capacity_controller(
                        self._primary_provider_scope()
                    )

                    request_options = {
                        "model": model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": True,
                        "max_tokens": effective_max_tokens,
                        "extra_body": extra_body,
                    }
                    if json_mode and self._supports_json_response_format(
                        model_id=model_id
                    ):
                        request_options["response_format"] = {
                            "type": "json_object"
                        }
                    # 真实 token 数只有 provider 给得出；估算值会系统性偏差，
                    # 直接影响"重复上下文占多少 token"这一验收项。
                    if (
                        _generation_telemetry_on()
                        and self._supports_stream_usage(model_id)
                    ):
                        request_options["stream_options"] = {
                            "include_usage": True
                        }
                    queue_started = time.perf_counter()
                    lease = await capacity.acquire(
                        model_id,
                        on_wait_activity=on_stream_activity,
                    )
                    # 优先用队列自己量的等待时长；取不到再退回本地秒表。
                    lease_wait_ms = getattr(lease, "queue_wait_ms", None)
                    queue_wait_ms = int(round(
                        lease_wait_ms
                        if lease_wait_ms is not None
                        else (time.perf_counter() - queue_started) * 1000
                    ))
                    queue_wait_reason = getattr(
                        lease, "queue_wait_reason", ""
                    )
                    try:
                        try:
                            await self._wait_for_request_slot()
                            physical_request_count += 1
                            response = await self.client.chat.completions.create(
                                **request_options
                            )
                        except Exception as format_error:
                            status_400 = (
                                self._error_status_code(format_error) == 400
                            )
                            # 埋点绝不能把一次本来能成功的请求变成失败：
                            # provider 拒绝 stream_options 时退掉该选项重试，
                            # 并记住，后续调用不再白跑一次 400。
                            if (
                                status_400
                                and "stream_options" in request_options
                            ):
                                self._remember_stream_usage_unsupported(
                                    self.api_base,
                                    model_id,
                                )
                                request_options.pop("stream_options", None)
                                await self._wait_for_request_slot()
                                physical_request_count += 1
                                response = (
                                    await self.client.chat.completions.create(
                                        **request_options
                                    )
                                )
                            elif not (json_mode and status_400):
                                raise
                            else:
                                # Remember the rejection: without this every
                                # later call pays the same wasted 400 round
                                # trip.
                                self._remember_json_mode_unsupported(
                                    self.api_base,
                                    model_id,
                                )
                                request_options.pop("response_format", None)
                                await self._wait_for_request_slot()
                                physical_request_count += 1
                                response = (
                                    await self.client.chat.completions.create(
                                        **request_options
                                    )
                                )

                        # 聚合流式响应；内容和推理分片都表示调用仍活跃。
                        full_content = ""
                        reasoning_chars = 0
                        truncated = False
                        async for chunk in response:
                            usage_pair = self._chunk_usage(chunk)
                            if usage_pair is not None:
                                real_usage = usage_pair
                            if chunk.choices:
                                reasoning = self._delta_reasoning(
                                    chunk.choices[0].delta
                                )
                                if reasoning:
                                    reasoning_chars += len(reasoning)
                                    if on_stream_activity:
                                        on_stream_activity()

                                delta = chunk.choices[0].delta
                                if delta.content:
                                    if first_token_at is None:
                                        first_token_at = time.perf_counter()
                                    full_content += delta.content
                                    if on_stream_activity:
                                        on_stream_activity()
                                if getattr(chunk.choices[0], "finish_reason", None) == "length":
                                    truncated = True
                    finally:
                        await lease.release()

                    if truncated:
                        logger.warning(
                            f"AI response truncated by max_tokens={effective_max_tokens} "
                            f"(Model: {model_id}, Attempt {attempt+1}/{retry_count}, "
                            f"chars={len(full_content)}) - downstream JSON/structure parsing "
                            "will likely fail on this output."
                        )
                        if reject_truncated:
                            if effective_max_tokens < truncation_headroom_ceiling:
                                effective_max_tokens = min(
                                    truncation_headroom_ceiling,
                                    effective_max_tokens * 2,
                                )
                                logger.info(
                                    "Raising max_tokens to %d before retrying "
                                    "the truncated request (Model: %s)",
                                    effective_max_tokens,
                                    model_id,
                                )
                            raise AIResponseTruncated(
                                "模型输出达到硬上限："
                                f"max_tokens={effective_max_tokens}，"
                                f"chars={len(full_content)}"
                            )

                    if not full_content:
                        fallback_eligible = True
                        # An empty answer with a large reasoning trace is not a
                        # dead provider: thinking consumed the whole
                        # max_tokens budget and left nothing for the answer.
                        # Reported as a plain empty_response it looks like a
                        # provider outage (and trips the breaker), so name it.
                        thinking_starved = reasoning_chars > 0
                        emit_telemetry(
                            status=(
                                "thinking_consumed_budget"
                                if thinking_starved
                                else "empty_response"
                            )
                        )
                        empty_error = AIProviderRequestError(
                            (
                                "thinking_consumed_budget:"
                                f"{model_id}:reasoning_chars={reasoning_chars}"
                                f":max_tokens={effective_max_tokens}"
                            )
                            if thinking_starved
                            else f"empty_response:{model_id}"
                        )
                        last_error = empty_error
                        if thinking_starved:
                            logger.warning(
                                "Model returned only reasoning and no answer "
                                "(Model: %s, reasoning_chars=%d, "
                                "max_tokens=%d): thinking used the whole "
                                "output budget; disable thinking for this "
                                "call or raise AI_MAX_TOKENS.",
                                model_id,
                                reasoning_chars,
                                effective_max_tokens,
                            )
                        else:
                            logger.warning(
                                "Empty response from AI "
                                f"(Model: {model_id}, "
                                f"Attempt {attempt+1}/{retry_count})"
                            )
                        if attempt < retry_count - 1:
                            await asyncio.sleep(1)
                            continue
                        await capacity.report_failure(
                            model_id,
                            failure_kind="transient",
                        )
                        self._cool_down_model(model_id, empty_error)
                        break

                    self._remember_model(
                        use_fast_model,
                        model_id,
                        model_role,
                    )
                    await capacity.report_success(model_id)
                    # A successful primary call is the recovery signal: no
                    # separate health probe is needed to leave fallback mode.
                    record_primary_recovered()
                    logger.debug(
                        "AI reasoning received (Model: %s, chars=%d)",
                        model_id,
                        reasoning_chars,
                    )
                    logger.info(f"AI Response Complete (Model: {model_id})")
                    emit_telemetry(
                        status="completed",
                        output=full_content,
                    )
                    return full_content

                except Exception as e:
                    emit_telemetry(status="failed", error=e)
                    last_error = e
                    logger.error(f"AI API Call Error (Model: {model_id}, Attempt {attempt+1}/{retry_count}): {e}")
                    if isinstance(e, ModelCapacityCoolingDown):
                        fallback_eligible = True
                        break
                    if self._is_authentication_error(e):
                        self._block_provider("authentication_failed")
                        fallback_eligible = True
                        break
                    if (
                        max_attempts is not None
                        and self._capacity_failure_kind(e)
                        == "quota_exhausted"
                    ):
                        capacity = get_provider_capacity_controller(
                            self._primary_provider_scope()
                        )
                        await capacity.report_failure(
                            model_id,
                            failure_kind="quota_exhausted",
                            cooldown_seconds=(
                                self._model_failure_cooldown_seconds(e)
                            ),
                        )
                        self._cool_down_model(model_id, e)
                        fallback_eligible = True
                        if not self._uses_model_scoped_quota(self.api_base):
                            self._block_provider("quota_exhausted")
                        break
                    if self._should_try_next_model(e):
                        fallback_eligible = True
                        capacity = get_provider_capacity_controller(
                            self._primary_provider_scope()
                        )
                        await capacity.report_failure(
                            model_id,
                            failure_kind=self._capacity_failure_kind(e),
                            cooldown_seconds=self._model_failure_cooldown_seconds(e),
                        )
                        self._cool_down_model(model_id, e)
                        break
                    if attempt < retry_count - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        break

            if self._provider_failure:
                break

        if fallback_eligible and self._modelscope_fallback_available():
            return await self._call_modelscope_fallback(
                prompt=prompt,
                system_prompt=system_prompt,
                retry_count=retry_count,
                enable_thinking=enable_thinking,
                max_tokens=max_tokens,
                max_attempts=max_attempts,
                reject_truncated=reject_truncated,
                raise_on_failure=raise_on_failure,
                json_mode=json_mode,
                model_role=model_role,
                on_stream_activity=on_stream_activity,
                telemetry_sink=telemetry_sink,
            )

        if raise_on_failure:
            if self._provider_failure:
                raise AIProviderUnavailable(
                    self._provider_failure
                ) from last_error
            if last_error is not None:
                raise AIProviderRequestError(str(last_error)) from last_error
            raise AIProviderRequestError("empty_response")
        return None

    async def _stream_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        use_fast_model: bool = False,
        enable_thinking: bool = False,
        max_tokens: int | None = None,
        max_input_tokens: int | None = None,
        max_input_chars: int | None = None,
        max_attempts: int | None = None,
        on_stream_activity: Callable[[], None] | None = None,
    ) -> AsyncIterator[str]:
        """
        流式 LLM 调用 - 生成器函数

        以流式方式调用LLM，逐块返回生成的内容，
        适用于实时显示长文本生成过程。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            use_fast_model: 是否使用快速模型
            enable_thinking: 是否为高价值环节启用模型思考能力
            max_tokens: 当前流式产物允许的最大输出 token。
            max_input_tokens: 最终 system + user prompt 的硬输入预算。
            max_input_chars: 最终请求的独立字符数硬上限。
            max_attempts: 跨候选模型共享的提供方总尝试次数。

        Yields:
            生成的文本块
        """
        self.validate_request_budget(
            prompt,
            system_prompt,
            max_input_tokens,
            max_input_chars,
        )
        if not self.api_key and not self.modelscope_fallback_api_key:
            raise AIProviderUnavailable("not_configured")
        if (
            self._provider_failure
            and not self._modelscope_fallback_available()
        ):
            raise AIProviderUnavailable(self._provider_failure)

        last_error: Exception | None = None
        attempts = 0
        primary_models = (
            self._models_for(use_fast_model)
            if self.api_key and not self._provider_failure
            else []
        )
        fallback_eligible = not primary_models
        for model_id in primary_models:
            if max_attempts is not None and attempts >= max_attempts:
                break
            attempts += 1
            yielded = False
            # 非流式路径已有"截断后加大预算重试"，流式没有：一次截断就以空
            # 正文收场，是正文阶段的单点故障，在 reasoning 模型上尤其常见
            # （thinking 吃光输出预算）。
            stream_max_tokens = max_tokens or self.max_tokens
            truncation_ceiling = max(self.max_tokens, stream_max_tokens * 2)
            # A-1：流式路径此前完全没有埋点，而正文生成正走这条路。少了它
            # 账单会漏掉最耗时的阶段。
            stream_started = time.perf_counter()
            stream_queue_wait_ms = 0.0
            stream_wait_reason = ""
            stream_first_token_at: float | None = None
            stream_output_chars = 0
            stream_usage: tuple[int, int] | None = None
            stream_requests = 0

            def emit_stream_record(
                *,
                status: str,
                error: Exception | None = None,
            ) -> None:
                if not _generation_telemetry_on():
                    return
                _record_generation_call(
                    model_id=model_id,
                    model_role="",
                    status=status,
                    stream=True,
                    attempt=attempts,
                    queue_wait_ms=stream_queue_wait_ms,
                    duration_ms=(
                        (time.perf_counter() - stream_started) * 1000
                    ),
                    ttfb_ms=(
                        None
                        if stream_first_token_at is None
                        else (stream_first_token_at - stream_started) * 1000
                    ),
                    prompt=prompt,
                    system_prompt=system_prompt,
                    input_tokens=stream_usage[0] if stream_usage else None,
                    output_tokens=stream_usage[1] if stream_usage else None,
                    tokens_source="provider" if stream_usage else "estimate",
                    retry_reason=type(error).__name__ if error else "",
                    error_code=str(error)[:200] if error else "",
                    physical_request_count=stream_requests,
                    provider_scope=self._primary_provider_scope(),
                    extra={
                        "output_chars": stream_output_chars,
                        "queue_wait_reason": stream_wait_reason,
                    },
                )

            try:
                while True:
                    extra_body = self._thinking_extra_body(enable_thinking)
                    capacity = get_provider_capacity_controller(
                        self._primary_provider_scope()
                    )
                    queue_started = time.perf_counter()
                    lease = await capacity.acquire(
                        model_id,
                        on_wait_activity=on_stream_activity,
                    )
                    lease_wait_ms = getattr(lease, "queue_wait_ms", None)
                    stream_queue_wait_ms += (
                        lease_wait_ms
                        if lease_wait_ms is not None
                        else (time.perf_counter() - queue_started) * 1000
                    )
                    stream_wait_reason = getattr(
                        lease, "queue_wait_reason", ""
                    ) or stream_wait_reason
                    try:
                        await self._wait_for_request_slot()
                        request_options = {
                            "model": model_id,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": True,
                            "max_tokens": stream_max_tokens,
                            "extra_body": extra_body,
                        }
                        if (
                            _generation_telemetry_on()
                            and self._supports_stream_usage(model_id)
                        ):
                            request_options["stream_options"] = {
                                "include_usage": True
                            }
                        stream_requests += 1
                        try:
                            response = (
                                await self.client.chat.completions.create(
                                    **request_options
                                )
                            )
                        except Exception as stream_option_error:
                            # 同 _call_llm：埋点选项被拒时退掉重试，不能因为
                            # 打点把正文生成打挂。
                            if not (
                                "stream_options" in request_options
                                and self._error_status_code(
                                    stream_option_error
                                ) == 400
                            ):
                                raise
                            self._remember_stream_usage_unsupported(
                                self.api_base,
                                model_id,
                            )
                            request_options.pop("stream_options", None)
                            await self._wait_for_request_slot()
                            stream_requests += 1
                            response = (
                                await self.client.chat.completions.create(
                                    **request_options
                                )
                            )

                        truncated = False
                        async for chunk in response:
                            usage_pair = self._chunk_usage(chunk)
                            if usage_pair is not None:
                                stream_usage = usage_pair
                            if chunk.choices:
                                reasoning = self._delta_reasoning(
                                    chunk.choices[0].delta
                                )
                                if reasoning and on_stream_activity:
                                    on_stream_activity()

                                delta = chunk.choices[0].delta
                                if delta.content:
                                    if stream_first_token_at is None:
                                        stream_first_token_at = (
                                            time.perf_counter()
                                        )
                                    stream_output_chars += len(delta.content)
                                    yielded = True
                                    if on_stream_activity:
                                        on_stream_activity()
                                    yield delta.content
                                if getattr(chunk.choices[0], "finish_reason", None) == "length":
                                    truncated = True
                    finally:
                        await lease.release()
                    if (
                        truncated
                        and not yielded
                        and stream_max_tokens < truncation_ceiling
                    ):
                        # 尚未向调用方吐出任何内容，重发不会产生重复正文。
                        stream_max_tokens = min(
                            truncation_ceiling,
                            stream_max_tokens * 2,
                        )
                        logger.info(
                            "Stream truncated with no content; retrying "
                            "(Model: %s, max_tokens=%d)",
                            model_id,
                            stream_max_tokens,
                        )
                        continue
                    break
                if truncated:
                    emit_stream_record(status="truncated")
                    raise AIResponseTruncated(
                        "模型流式输出达到硬上限："
                        f"max_tokens={stream_max_tokens}"
                    )
                if yielded:
                    self._remember_model(use_fast_model, model_id)
                    await capacity.report_success(model_id)
                    record_primary_recovered()
                    emit_stream_record(status="completed")
                    return
                emit_stream_record(status="empty_response")
                last_error = AIProviderRequestError(f"Model {model_id} returned an empty stream")
            except Exception as e:
                emit_stream_record(status="failed", error=e)
                logger.error(f"Stream Error (Model: {model_id}): {e}")
                if isinstance(e, ModelCapacityCoolingDown):
                    last_error = e
                    fallback_eligible = True
                    continue
                if self._is_authentication_error(e):
                    self._block_provider("authentication_failed")
                    last_error = e
                    fallback_eligible = True
                    break
                last_error = e
                should_try_next = self._should_try_next_model(e)
                if should_try_next:
                    fallback_eligible = True
                    capacity = get_provider_capacity_controller(
                        self._primary_provider_scope()
                    )
                    await capacity.report_failure(
                        model_id,
                        failure_kind=self._capacity_failure_kind(e),
                        cooldown_seconds=self._model_failure_cooldown_seconds(e),
                    )
                    self._cool_down_model(model_id, e)
                if yielded or not should_try_next:
                    if isinstance(e, AIProviderRequestError):
                        raise
                    raise AIProviderRequestError(str(e)) from e
            if not yielded and isinstance(
                last_error,
                AIProviderRequestError,
            ):
                fallback_eligible = True
            if self._provider_failure:
                break

        if fallback_eligible and self._modelscope_fallback_available():
            async for chunk in self._stream_modelscope_fallback(
                prompt=prompt,
                system_prompt=system_prompt,
                enable_thinking=enable_thinking,
                max_tokens=max_tokens,
                max_attempts=max_attempts,
                on_stream_activity=on_stream_activity,
            ):
                yield chunk
            return
        if self._provider_failure:
            raise AIProviderUnavailable(
                self._provider_failure
            ) from last_error
        if isinstance(last_error, AIProviderRequestError):
            raise last_error
        if last_error is not None:
            raise AIProviderRequestError(str(last_error)) from last_error
        raise AIProviderRequestError("No available AI model")
