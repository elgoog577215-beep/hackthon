"""Qwen provider（自建 vLLM，OpenAI 兼容）：
- 文本分析：通过 OpenAI 兼容接口调用 vLLM 上的 Qwen 文本模型（JSON 模式 + pydantic 校验 + 重试），
  接口与 GeminiRunner.run 兼容，故整段分析(环节/知识点/互动/思政/总评)无需改动即可复用。
- 字幕：Qwen3-ASR 只给文本不给时间戳且单段 ≤5min，故用 ffmpeg 按时间切块、逐块 ASR
  （走 vLLM 的 OpenAI /v1/audio/transcriptions 接口），再按句切分、在已知块区间内按字数比例分配时间戳。

默认指向自建 vLLM：
- 文本：http://127.0.0.1:30964/v1     模型 qwen3.6-35b-a3b
- ASR ：http://127.0.0.1:30219/v1     模型 qwen3-asr-1.7b
可用 .env 的 VLLM_TEXT_BASE_URL / VLLM_ASR_BASE_URL / VLLM_API_KEY 或对应 CLI 参数覆盖。
vLLM 默认无需鉴权，api_key 传 "EMPTY" 即可；如服务端开了 --api-key 再填实际值。
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional, get_args, get_origin

from openai import OpenAI
from pydantic import TypeAdapter

from .cache import ResultCache
from .gemini_steps import _dump, _is_transient, _short, _strip_fences

# 自建 vLLM 默认地址（OpenAI 兼容）
VLLM_TEXT_URL = os.getenv("VLLM_TEXT_ENDPOINT", "http://127.0.0.1:30938/v1")
VLLM_ASR_URL = os.getenv("VLLM_ASR_ENDPOINT", "http://127.0.0.1:30026/v1")

# 兼容保留：阿里云百炼 DashScope 地址，可用 --qwen-base-url 显式切回
BASE_CN = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BASE_INTL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def make_qwen_client(api_key: str, base_url: str):
    return OpenAI(api_key=api_key or "EMPTY", base_url=base_url, timeout=180)


def make_qwen_clients(api_key: str, base_urls: str) -> list:
    """逗号分隔的多 URL → 多 OpenAI client，用于多实例负载均衡。"""
    urls = [u.strip() for u in base_urls.split(",") if u.strip()]
    return [make_qwen_client(api_key, u) for u in urls]


def qwen_connectivity_check(client, model: str, log):
    log.info(f"[check] 校验 vLLM 文本服务与模型 {model}（{client.base_url}）...")
    try:
        client.chat.completions.create(
            model=model, max_tokens=16,
            messages=[{"role": "user", "content": '只输出 json：{"ok":true}'}],
            response_format={"type": "json_object"},
            # vLLM 用 chat_template_kwargs 控制是否思考（顶层 enable_thinking 会被忽略）
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        log.info("[check] 连通正常")
    except Exception as e:
        raise SystemExit(
            f"无法连接文本服务或模型不可用（model={model}，base_url={client.base_url}）。\n  原因：{e}\n"
            f"  请确认 vLLM 已在该地址提供该模型，或用 --model / --qwen-base-url / "
            f".env 的 VLLM_TEXT_BASE_URL 调整。"
        )


# ---------------------------------------------------------------------------
# 文本 Runner（与 GeminiRunner 接口兼容）
# ---------------------------------------------------------------------------

class QwenRunner:
    def __init__(self, client, model: str, logger, *, temperature: float = 0.3,
                 workers: int = 3, enable_thinking: bool = False):
        if isinstance(client, list):
            self._clients = client
        else:
            self._clients = [client]
        self.client = self._clients[0]
        self.model = model
        self.log = logger
        self.temperature = temperature
        self.workers = max(1, workers)
        self.enable_thinking = enable_thinking
        self.usage = {"prompt": 0, "candidates": 0, "cached": 0, "calls": 0}

    def _pick_client(self):
        if len(self._clients) == 1:
            return self._clients[0]
        return random.choice(self._clients)

    def run(self, label, contents, schema, *, max_output_tokens=None, thinking_budget=0,
            cached_content=None, retries=2):
        prompt = "\n".join(c for c in contents if isinstance(c, str))
        hint = _schema_hint(schema)
        system = "你是一名资深的高校教学督导与课堂分析专家。请只输出 JSON，不要任何多余文字、解释或 markdown 代码块。"
        user = prompt + "\n\n" + hint
        temp = self.temperature
        last = None
        for attempt in range(retries + 1):
            txt = self._chat(system, user, max_output_tokens, temp)
            try:
                return _parse_validate(txt, schema)
            except Exception as e:
                last = e
                self.log.warning(f"[{label}] JSON 解析/校验失败（第 {attempt+1} 次）：{_short(e)}")
                user = (prompt + "\n\n" + hint +
                        f"\n\n上次输出无法解析或不符合结构（{_short(e)}）。请严格只输出符合上述结构的 JSON。")
                temp = max(0.0, temp - 0.15)
        raise RuntimeError(f"[{label}] 多次重试仍失败：{last}")

    def _chat(self, system, user, max_tokens, temp, max_tries: int = 5):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        delay = 1.0
        last = None
        for i in range(max_tries):
            try:
                c = self._pick_client()
                r = c.chat.completions.create(
                    model=self.model, messages=messages, temperature=temp,
                    response_format={"type": "json_object"},
                    extra_body={"chat_template_kwargs": {"enable_thinking": self.enable_thinking}},
                    max_tokens=max_tokens or None,
                )
                u = getattr(r, "usage", None)
                if u:
                    self.usage["prompt"] += getattr(u, "prompt_tokens", 0) or 0
                    self.usage["candidates"] += getattr(u, "completion_tokens", 0) or 0
                self.usage["calls"] += 1
                return r.choices[0].message.content or ""
            except Exception as e:
                last = e
                if _is_transient(e) and i < max_tries - 1:
                    wait = delay + random.uniform(0, delay * 0.5)
                    self.log.warning(f"瞬时错误，{wait:.1f}s 后重试（{i+1}/{max_tries}）：{_short(e)}")
                    time.sleep(wait)
                    delay = min(delay * 2, 8.0)
                    continue
                raise
        raise last  # type: ignore

    def map_parallel(self, fn, items):
        items = list(items)
        if self.workers <= 1 or len(items) <= 1:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(fn, items))


def _schema_hint(schema) -> str:
    origin = get_origin(schema)
    if origin in (list, List):
        inner = get_args(schema)[0]
        js = json.dumps(inner.model_json_schema(), ensure_ascii=False)
        return ('请输出一个 JSON 对象，形如 {"items": [ ... ]}，其中 items 是数组，'
                "数组每个元素必须符合以下 JSON Schema：\n" + js)
    js = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return "请输出一个 JSON 对象，必须符合以下 JSON Schema：\n" + js


def _parse_validate(txt: str, schema):
    obj = json.loads(_strip_fences(txt))
    origin = get_origin(schema)
    if origin in (list, List):
        if isinstance(obj, dict):
            for k in ("items", "data", "list", "result", "results"):
                if isinstance(obj.get(k), list):
                    obj = obj[k]
                    break
            else:
                # 对象里只有一个数组值时取之
                arrs = [v for v in obj.values() if isinstance(v, list)]
                if len(arrs) == 1:
                    obj = arrs[0]
    return _dump(TypeAdapter(schema).validate_python(obj))


# ---------------------------------------------------------------------------
# ASR 字幕
# ---------------------------------------------------------------------------

def _is_timeout_err(e: Exception) -> bool:
    """识别"超时"类异常（openai.APITimeoutError / httpx 读超时等），用名字+消息兜底。"""
    name = type(e).__name__.lower()
    return "timeout" in name or "timed out" in str(e).lower()


def make_asr_caller(base_url: str, api_key: str, model: str, log):
    """返回 asr(video_path, start, dur) -> 文本。

    base_url 支持逗号分隔的多 URL，实现多 vLLM 实例负载均衡。
    """
    urls = [u.strip() for u in base_url.split(",") if u.strip()]
    clients = [OpenAI(api_key=api_key or "EMPTY", base_url=u, timeout=60) for u in urls]

    def asr(video_path: str, start: float, dur: float, max_tries: int = 5) -> str:
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="_asr_")
        os.close(fd)
        dur_sec = max(1.0, float(dur))
        # 输出上限（宽松）：约 30 token/秒，远超正常语速（中文约 5 字/秒），仅用于截断
        # "跑飞/复读"的失控生成；正常字幕远到不了这个量、不会被截。
        max_out = max(1024, int(dur_sec * 30))
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", video_path,
                 "-t", f"{dur:.3f}", "-ac", "1", "-ar", "16000", wav],
                check=True,
            )
            delay = 1.0
            last = None
            for i in range(max_tries):
                try:
                    c = random.choice(clients)
                    with open(wav, "rb") as f:
                        resp = c.audio.transcriptions.create(
                            model=model, file=f, language="zh", response_format="json",
                            extra_body={"max_completion_tokens": max_out},
                        )
                    text = (getattr(resp, "text", "") or "").strip()
                    if len(text) > dur_sec * 20:
                        log.warning(f"[asr] 块 {start:.0f}-{start + dur:.0f}s 输出异常({len(text)} 字)，疑似跑飞复读，丢弃")
                        return ""
                    return text
                except Exception as e:
                    last = e
                    timed_out = _is_timeout_err(e)
                    if _is_transient(e) and not timed_out and i < max_tries - 1:
                        wait = delay + random.uniform(0, delay * 0.5)
                        log.warning(f"[asr] 瞬时错误，{wait:.1f}s 后重试：{_short(e)}")
                        time.sleep(wait)
                        delay = min(delay * 2, 8.0)
                        continue
                    if timed_out:
                        log.warning(f"[asr] 转写超时（疑似跑飞），跳过该块不重试：{_short(e)}")
                    raise RuntimeError(f"ASR 失败：{_short(e)}")
            raise RuntimeError(f"ASR 重试耗尽：{_short(last)}")
        finally:
            if os.path.exists(wav):
                os.remove(wav)

    return asr


_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")


def _split_sentences_with_time(text: str, c0: float, c1: float) -> List[dict]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    if not parts:
        return []
    total = sum(len(p) for p in parts)
    span = max(0.1, c1 - c0)
    segs = []
    t = c0
    for p in parts:
        a1 = min(c1, t + len(p) / total * span)
        segs.append({"start_sec": round(t, 2), "end_sec": round(max(t + 0.1, a1), 2), "text": p})
        t = a1
    return segs


def qwen_transcribe(asr, video_path: str, *, range_start: float, range_end: float,
                    chunk_sec: float, model: str, result_cache: ResultCache, workers: int, log,
                    cancel_check=None):
    bounds = []
    s = range_start
    while s < range_end - 1e-6:
        bounds.append((s, min(s + chunk_sec, range_end)))
        s += chunk_sec
    log.info(f"[transcript] ASR 共 {len(bounds)} 个音频块（每块 {chunk_sec:.0f}s）")

    def do(idx: int):
        if cancel_check is not None:
            cancel_check()  # 取消信号（如视频被删）：抛出后中止整个转写
        c0, c1 = bounds[idx]
        dim = f"asr_w{int(c0)}_{int(c1)}"
        sig = ResultCache.sig("asr", model, round(c0, 1), round(c1, 1))
        cached = result_cache.get(dim, sig)
        if cached is not None:
            return cached
        try:
            text = asr(video_path, c0, c1 - c0)
        except Exception as e:
            log.error(f"[transcript] 块 {c0:.0f}-{c1:.0f}s ASR 失败：{_short(e)}")
            text = ""
        result_cache.put(dim, sig, text)
        return text

    items = list(range(len(bounds)))
    if workers > 1 and len(items) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            texts = list(ex.map(do, items))
    else:
        texts = [do(i) for i in items]

    segs = []
    for (c0, c1), text in zip(bounds, texts):
        segs += _split_sentences_with_time(text, c0, c1)
    log.info(f"[transcript] ASR 合并得到 {len(segs)} 个字幕片段")
    return segs
