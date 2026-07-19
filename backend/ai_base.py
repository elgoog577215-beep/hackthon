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

import os
import re
import json
import logging
import sys
import asyncio
import httpx
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    AuthenticationError,
    PermissionDeniedError,
)
from typing import List, Dict, Optional

# 添加项目根目录到系统路径以导入共享配置
project_root = Path(__file__).parent.parent
# 加载环境变量（必须在读取环境变量之前调用）
load_dotenv(project_root / ".env")
sys.path.insert(0, str(project_root))
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle

# ============================================================================
# 配置与常量
# ============================================================================

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API密钥存在性检查（不记录密钥内容）
_api_key_present = bool(os.getenv("AI_API_KEY"))
if _api_key_present:
    logger.info("AI_API_KEY loaded successfully")
else:
    logger.error("AI_API_KEY not found in environment variables")

DEFAULT_SMART_MODELS = [
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-ai/DeepSeek-V4-Flash",
    "deepseek-ai/DeepSeek-V3.2",
    "ZhipuAI/GLM-5.2",
    "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "Qwen/Qwen3-Next-80B-A3B-Instruct",
    "Qwen/Qwen3-32B",
]

DEFAULT_FAST_MODELS = [
    "deepseek-ai/DeepSeek-V4-Flash",
    "deepseek-ai/DeepSeek-V3.2",
    "ZhipuAI/GLM-4.7-Flash",
    "Qwen/Qwen3-Next-80B-A3B-Instruct",
    "Qwen/Qwen3-32B",
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

    def __init__(self):
        # 通过环境变量配置 API 密钥
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
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
        
        if self.api_key:
            request_timeout = max(1.0, float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "180")))
            connect_timeout = max(1.0, float(os.getenv("AI_CONNECT_TIMEOUT_SECONDS", "10")))
            self.client = AsyncOpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
                timeout=httpx.Timeout(request_timeout, connect=connect_timeout),
                max_retries=0,
            )
        else:
            self.client = None
            logger.warning("AI_API_KEY not found. AI features will be disabled.")

    @staticmethod
    def _is_official_deepseek_base(api_base: str) -> bool:
        return urlparse(api_base).hostname == "api.deepseek.com"

    def _thinking_extra_body(self, enable_thinking: bool) -> Dict:
        thinking_enabled = enable_thinking and self.thinking_enabled
        if self._is_official_deepseek_base(self.api_base):
            return {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}}
        return {"enable_thinking": thinking_enabled}

    def _model_cache_key(self, use_fast_model: bool):
        models = self.fast_models if use_fast_model else self.smart_models
        return (self.api_base, "fast" if use_fast_model else "smart", tuple(models))

    def _models_for(self, use_fast_model: bool) -> List[str]:
        models = self.fast_models if use_fast_model else self.smart_models
        cached = self._working_model_cache.get(self._model_cache_key(use_fast_model))
        if cached in models:
            return [cached] + [model for model in models if model != cached]
        return models

    def _remember_model(self, use_fast_model: bool, model_id: str) -> None:
        self._working_model_cache[self._model_cache_key(use_fast_model)] = model_id

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
        if status_code in (401, 403):
            return True

        message = str(error).lower()
        return any(marker in message for marker in (
            "401",
            "403",
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
                    return json.loads(_fix_invalid_escapes(raw))
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
                    return json.loads(_fix_invalid_escapes(raw))
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
                        return json.loads(_fix_invalid_escapes(json_str))
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
        text = re.sub(r'\\\[(.*?)\\\]', r'\n$\n\1\n$\n', text, flags=re.DOTALL)
        
        # 2. 转换行内公式标记
        text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
        
        # 3. 确保复杂环境被 $ 包裹
        envs = r"matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|align|align\*|equation|equation\*|cases|gather|gather\*|alignat|alignat\*"
        pattern = fr'(\$\$)?\s*(\\begin{{({envs})}}.*?\\end{{\3}})\s*(\$\$)?'
        
        def fix_latex_block(match):
            content = match.group(2)
            return f"\n$\n{content.strip()}\n$\n"

        text = re.sub(pattern, fix_latex_block, text, flags=re.DOTALL)
        
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
    
    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        use_fast_model: bool = False,
        retry_count: int = 3,
        enable_thinking: bool = False,
        max_tokens: int | None = None,
        raise_on_failure: bool = False,
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
            raise_on_failure: 失败时是否抛出统一的提供方异常，而不是返回 None

        Returns:
            LLM 完整响应文本，失败返回 None
        """
        if not self.api_key:
            if raise_on_failure:
                raise AIProviderUnavailable("not_configured")
            return None
        if self._provider_failure:
            if raise_on_failure:
                raise AIProviderUnavailable(self._provider_failure)
            return None

        last_error: Exception | None = None
        for model_id in self._models_for(use_fast_model):
            for attempt in range(retry_count):
                try:
                    extra_body = self._thinking_extra_body(enable_thinking)

                    response = await self.client.chat.completions.create(
                        model=model_id,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        stream=True,
                        max_tokens=max_tokens or self.max_tokens,
                        extra_body=extra_body
                    )

                    # 聚合流式响应
                    full_content = ""
                    reasoning_chars = 0
                    truncated = False
                    async for chunk in response:
                        if chunk.choices:
                            # 思考内容不属于课程产物，只记录长度用于调试。
                            if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                                reasoning = chunk.choices[0].delta.reasoning_content
                                if reasoning:
                                    reasoning_chars += len(reasoning)

                            delta = chunk.choices[0].delta
                            if delta.content:
                                full_content += delta.content
                            if getattr(chunk.choices[0], "finish_reason", None) == "length":
                                truncated = True

                    if truncated:
                        logger.warning(
                            f"AI response truncated by max_tokens={max_tokens or self.max_tokens} "
                            f"(Model: {model_id}, Attempt {attempt+1}/{retry_count}, "
                            f"chars={len(full_content)}) - downstream JSON/structure parsing "
                            "will likely fail on this output."
                        )

                    if not full_content:
                        logger.warning(f"Empty response from AI (Model: {model_id}, Attempt {attempt+1}/{retry_count})")
                        if attempt < retry_count - 1:
                            await asyncio.sleep(1)
                            continue
                        break

                    self._remember_model(use_fast_model, model_id)
                    logger.debug(
                        "AI reasoning received (Model: %s, chars=%d)",
                        model_id,
                        reasoning_chars,
                    )
                    logger.info(f"AI Response Complete (Model: {model_id})")
                    return full_content

                except Exception as e:
                    last_error = e
                    logger.error(f"AI API Call Error (Model: {model_id}, Attempt {attempt+1}/{retry_count}): {e}")
                    if self._is_authentication_error(e):
                        self._block_provider("authentication_failed")
                        if raise_on_failure:
                            raise AIProviderUnavailable("authentication_failed") from e
                        return None
                    if self._should_try_next_model(e):
                        break
                    if attempt < retry_count - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        break

        if raise_on_failure:
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
    ):
        """
        流式 LLM 调用 - 生成器函数

        以流式方式调用LLM，逐块返回生成的内容，
        适用于实时显示长文本生成过程。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            use_fast_model: 是否使用快速模型
            enable_thinking: 是否为高价值环节启用模型思考能力

        Yields:
            生成的文本块
        """
        if not self.api_key:
            raise AIProviderUnavailable("not_configured")
        if self._provider_failure:
            raise AIProviderUnavailable(self._provider_failure)

        last_error: Exception | None = None
        for model_id in self._models_for(use_fast_model):
            yielded = False
            try:
                extra_body = self._thinking_extra_body(enable_thinking)

                response = await self.client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    stream=True,
                    extra_body=extra_body
                )

                async for chunk in response:
                    if chunk.choices:
                        # 处理推理内容（用于日志/调试）
                        if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                            reasoning = chunk.choices[0].delta.reasoning_content
                            if reasoning:
                                # 可以记录思考过程或暂时忽略
                                pass

                        delta = chunk.choices[0].delta
                        if delta.content:
                            yielded = True
                            yield delta.content
                if yielded:
                    self._remember_model(use_fast_model, model_id)
                    return
                last_error = AIProviderRequestError(f"Model {model_id} returned an empty stream")
            except Exception as e:
                logger.error(f"Stream Error (Model: {model_id}): {e}")
                if self._is_authentication_error(e):
                    self._block_provider("authentication_failed")
                    raise AIProviderUnavailable("authentication_failed") from e
                last_error = e
                if yielded or not self._should_try_next_model(e):
                    raise AIProviderRequestError(str(e)) from e
        if isinstance(last_error, AIProviderRequestError):
            raise last_error
        if last_error is not None:
            raise AIProviderRequestError(str(last_error)) from last_error
        raise AIProviderRequestError("No available AI model")
