"""PPT 生成用的同步 LLM Runner（OpenAI 兼容 / 自建 vLLM Qwen）。

复用 video-analyze 的两段式生成思路：JSON 模式 + pydantic 校验 + 重试 + 线程池并发，
对外接口为 .run(label, contents, schema, ...) 与 .map_parallel(fn, items)，与 video-analyze
的 QwenRunner 接口兼容，因此 slides.py 的大纲/填充流水线可直接复用。

端点与密钥默认沿用 agents.llm 中已配置的自建 vLLM（与教案/大纲生成同一套 Qwen），
也可在构造时显式传入 client / model 以便脱离 DB 依赖做离线测试。
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, List, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

from common.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 轻量工具（从 video-analyze 的 gemini_steps 内联过来，避免引入视频分析相关依赖）
# ---------------------------------------------------------------------------

def _strip_fences(txt: str) -> str:
    s = (txt or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _short(e: Any, n: int = 160) -> str:
    return str(e)[:n]


def _is_transient(e: Any) -> bool:
    msg = str(e).lower()
    keys = ("timeout", "timed out", "connection", "reset", "429", "rate limit",
            "502", "503", "504", "overloaded", "temporarily")
    return any(k in msg for k in keys)


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    return obj


def _schema_hint(schema: Any) -> str:
    origin = get_origin(schema)
    if origin in (list, List):
        inner = get_args(schema)[0]
        js = json.dumps(inner.model_json_schema(), ensure_ascii=False)
        return ('请输出一个 JSON 对象，形如 {"items": [ ... ]}，其中 items 是数组，'
                "数组每个元素必须符合以下 JSON Schema：\n" + js)
    js = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return "请输出一个 JSON 对象，必须符合以下 JSON Schema：\n" + js


def _parse_validate(txt: str, schema: Any) -> Any:
    obj = json.loads(_strip_fences(txt))
    origin = get_origin(schema)
    if origin in (list, List):
        if isinstance(obj, dict):
            for k in ("items", "data", "list", "result", "results"):
                if isinstance(obj.get(k), list):
                    obj = obj[k]
                    break
            else:
                arrs = [v for v in obj.values() if isinstance(v, list)]
                if len(arrs) == 1:
                    obj = arrs[0]
    return _dump(TypeAdapter(schema).validate_python(obj))


# ---------------------------------------------------------------------------
# 同步 Runner（与 video-analyze QwenRunner 接口兼容）
# ---------------------------------------------------------------------------

class LlmRunner:
    def __init__(self, client, model: str, *, temperature: float = 0.4,
                 workers: int = 4, enable_thinking: bool = False, log=None):
        self.client = client
        self.model = model
        self.log = log or logger
        self.temperature = temperature
        self.workers = max(1, workers)
        self.enable_thinking = enable_thinking
        self.usage = {"prompt": 0, "candidates": 0, "calls": 0}

    def run(self, label: str, contents: List[str], schema: Any, *,
            max_output_tokens: int | None = None, retries: int = 2) -> Any:
        prompt = "\n".join(c for c in contents if isinstance(c, str))
        hint = _schema_hint(schema)
        system = ("你是一名资深大学教师兼课程 PPT 设计专家。"
                  "请只输出 JSON，不要任何多余文字、解释或 markdown 代码块。")
        user = prompt + "\n\n" + hint
        temp = self.temperature
        last = None
        for attempt in range(retries + 1):
            txt = self._chat(system, user, max_output_tokens, temp)
            try:
                return _parse_validate(txt, schema)
            except Exception as e:
                last = e
                self.log.warning(f"[{label}] JSON 解析/校验失败（第 {attempt + 1} 次）：{_short(e)}")
                user = (prompt + "\n\n" + hint +
                        f"\n\n上次输出无法解析或不符合结构（{_short(e)}）。请严格只输出符合上述结构的 JSON。")
                temp = max(0.0, temp - 0.15)
        raise RuntimeError(f"[{label}] 多次重试仍失败：{last}")

    def _chat(self, system: str, user: str, max_tokens: int | None, temp: float,
              max_tries: int = 5) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        delay = 4.0
        last = None
        for i in range(max_tries):
            try:
                r = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=temp,
                    response_format={"type": "json_object"},
                    # vLLM：思考开关走 chat_template_kwargs（顶层 enable_thinking 无效）
                    extra_body={"chat_template_kwargs": {"enable_thinking": self.enable_thinking}},
                    max_tokens=max_tokens or None,
                )
                u = getattr(r, "usage", None)
                if u:
                    self.usage["prompt"] += getattr(u, "prompt_tokens", 0) or 0
                    self.usage["candidates"] += getattr(u, "completion_tokens", 0) or 0
                self.usage["calls"] += 1
                # content 可能为 None（内容过滤/思考路由），统一成 "" 让上层报错
                return r.choices[0].message.content or ""
            except Exception as e:
                last = e
                if _is_transient(e) and i < max_tries - 1:
                    self.log.warning(f"瞬时错误，{delay:.0f}s 后重试（{i + 1}/{max_tries}）：{_short(e)}")
                    time.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                raise
        raise last  # type: ignore[misc]

    def map_parallel(self, fn: Callable, items) -> list:
        items = list(items)
        if self.workers <= 1 or len(items) <= 1:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(fn, items))


# ---------------------------------------------------------------------------
# 默认 Runner 工厂：复用 agents.llm 已配置的自建 vLLM（与教案/大纲同一端点）
# ---------------------------------------------------------------------------

_model_cache: dict[str, str] = {}


def _resolve_model(client) -> str:
    if "id" in _model_cache:
        return _model_cache["id"]
    try:
        models = client.models.list()
        if models.data:
            _model_cache["id"] = models.data[0].id
            return _model_cache["id"]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ppt] 获取 vLLM 模型列表失败，回退默认模型：{_short(e)}")
    from common.config import settings
    _model_cache["id"] = settings.LOCAL_ANALYSIS_MODEL
    return _model_cache["id"]


def make_default_runner(*, workers: int = 4, temperature: float = 0.4) -> LlmRunner:
    """构造默认 Runner：端点/密钥沿用 agents.llm 中已配置的自建 vLLM Qwen。"""
    from openai import OpenAI

    from agents.llm import VLLM_API_KEY, client as _async_client
    from common.config import settings

    base_url = str(getattr(_async_client, "base_url", "") or "").rstrip("/") \
        or settings.LOCAL_ANALYSIS_TEXT_BASE_URL
    sync_client = OpenAI(api_key=VLLM_API_KEY or "EMPTY", base_url=base_url, timeout=180)
    model = _resolve_model(sync_client)
    return LlmRunner(sync_client, model, workers=workers, temperature=temperature)
