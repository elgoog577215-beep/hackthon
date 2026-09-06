"""Gemini 维度分析：字幕（分块转写）、课堂环节、知识点、互动、思政、总评。

设计要点：
- 调用包裹 `_raw` 有「渐进降级」：若模型不支持 thinking_config / media_resolution
  等可选字段，自动剥离重试，避免因模型版本差异直接失败。
- 结构化输出解析失败时降温 + 纠错提示重试。
- 字幕分块转写：每窗 start/end offset；自动判定时间戳是相对还是绝对；按时间分区去重合并。
"""
from __future__ import annotations

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional, Tuple

from pydantic import TypeAdapter

# google-genai 仅 gemini 后端需要；qwen 路径不会触达任何用到 types 的函数，
# 故缺失时降级为 None，避免在仅装 qwen 依赖的服务端 import 期失败。
try:
    from google.genai import types
except Exception:  # pragma: no cover - 服务端仅走 qwen，不安装 google-genai
    types = None  # type: ignore

from . import schemas
from .cache import ResultCache
from .util import sec_to_hms

PROMPT_VERSION = "2"          # 整段(结构化)维度 prompt/schema 版本
TRANSCRIPT_VERSION = "1"      # 字幕窗口 prompt 版本（与整段维度分开，互不失效）

SYSTEM_INSTRUCTION = (
    "你是一名资深的高校教学督导与课堂教学分析专家，正在分析一节中文大学课堂的录像。"
    "请结合视频画面与音频（教师与学生的讲话）做客观、专业的分析。"
    "所有输出使用简体中文。严格按要求的 JSON 结构输出，不要输出任何多余文字或解释。"
)

TRANSCRIPT_PROMPT = (
    "请对所提供的这一段课堂视频做逐字语音转写（只转写有声的讲话内容，不要描述画面、不要加说明）。"
    "按自然语句/语义切分为若干片段。每个片段给出："
    "start_sec、end_sec（单位：秒，相对于【所提供视频片段】的开头，从 0 开始计），"
    "以及 text（该时段的简体中文逐字稿）。保持时间先后顺序，尽量准确对齐时间。"
)

STRUCTURE_PROMPT = (
    "请分析这节课的课堂教学环节结构，输出 JSON：\n"
    "1) chapters：按时间顺序把课堂划分为若干阶段，每个阶段含 summary（该阶段整体小结）"
    "和 file_structure（该阶段内的环节列表）。每个环节含 start_time/end_time（HH:MM:SS）、"
    "type（环节类型，参考：课程回顾/课程导入/知识讲授/案例分析/课堂提问/课堂活动/小组讨论/"
    "实践演示/布置作业/课堂总结）、sub_type（可空）、content（该环节做了什么）、"
    "keypoint（该环节的关键点列表，每个含 name/start_time/end_time）。\n"
    "2) intro_analysis：课程导入环节的专项分析（exists 是否存在、start_time/end_time、content、evaluation 评价与建议）。\n"
    "3) summary_analysis：课程总结环节的专项分析（字段同上）。\n"
    "时间戳为相对整段视频开头的绝对时间。"
)

KNOWLEDGE_PROMPT = (
    "请抽取这节课的知识点层级结构，最多 3 层，输出顶层知识点数组。"
    "每个节点含 id（如 '1'、'1.1'、'1.1.1'）、title（知识点名称）、"
    "start_time/end_time（HH:MM:SS，相对整段视频开头的绝对时间）、children（子知识点，最深到第 3 层）。"
    "知识点要具体、贴合讲授内容，避免过于笼统。"
)

INTERACTION_PROMPT = (
    "请找出这节课中所有的师生互动/课堂提问事件，输出数组。每条含："
    "text（规范化后的问题表述）、type（认知层次，取值：记忆型/理解型/应用型/分析型/评价型/创造型）、"
    "segment（教师的实际原话）、start_time/end_time（HH:MM:SS 绝对时间）、"
    "wuhe（五何分类，取值：是何/为何/如何/若何/由何）。\n"
    "五何释义：是何=事实与定义类；为何=原因/目的/意义；如何=方法/过程/步骤；"
    "若何=假设/条件/推测（如果…会怎样）；由何=来源/出处/背景由来。"
)

IDEOLOGY_PROMPT = (
    "请找出这节课中的课程思政融入点（如家国情怀、文化自信、职业伦理、科学精神、"
    "生态环保、社会责任、工匠精神、创新精神、团队协作等），输出数组。每条含："
    "start_time、end_time（HH:MM:SS，取自字幕中最接近的片段时间）、"
    "result.status（融入程度：0=无 1=隐性 2=显性）、result.title（思政点标题）、"
    "result.content（融入的具体描述）、result.naturalness（融入自然度评分 1-5，越自然越高）。"
    "注意通读整节课，思政点可能分布在课程的任何阶段（包括后半段），不要只看开头。"
)

OVERVIEW_PROMPT = (
    "下面给出对一节中文大学课堂的多维分析数据（JSON）。请基于这些数据，对该课堂做总体评价，输出 JSON：\n"
    "summary（AI 总评摘要，约 150-250 字）、"
    "radar（教学表达/教学设计/知识呈现/互动质量/思政融合 五个维度，各含 name、score(0-100)、comment 评语）、"
    "overall_score（综合得分 0-100）、suggestions（面向教师的总体改进建议，3-6 条）、"
    "capability_summary（能力概述：一段 100-200 字的总体能力评价段落，概括教师在各维度的综合表现水平、"
    "突出优势与明显不足，语气客观专业）、"
    "improvement_suggestions（改进建议：3-5 条针对性强、可操作的教学改进建议，"
    "每条 20-50 字，覆盖得分较低的维度，给出具体方法而非笼统建议）。\n"
    "评分要结合数据：教学表达看语速/口头禅/音量稳定度；教学设计看环节完整性与导入总结；"
    "知识呈现看知识点的系统性与层次；互动质量看互动数量/类型分布/最长无互动时长；思政融合看思政点数量与自然度。\n\n"
    "分析数据：\n"
)


# ---------------------------------------------------------------------------
# Runner：封装 client + 模型 + 默认配置 + 用量统计 + 并发
# ---------------------------------------------------------------------------

class GeminiRunner:
    def __init__(self, client, model: str, logger, *, media_resolution: Optional[str] = "low",
                 temperature: float = 0.3, workers: int = 3, transcript_max_tokens: int = 32768):
        self.client = client
        self.model = model
        self.log = logger
        self.temperature = temperature
        self.workers = max(1, workers)
        self.transcript_max_tokens = transcript_max_tokens
        self.system_instruction = SYSTEM_INSTRUCTION
        self.media_resolution = _media_res_enum(media_resolution)
        self.usage = {"prompt": 0, "candidates": 0, "cached": 0, "calls": 0}

    # ---- 用量 ----
    def _acc(self, resp):
        um = getattr(resp, "usage_metadata", None)
        if um is None:
            return
        self.usage["prompt"] += getattr(um, "prompt_token_count", 0) or 0
        self.usage["candidates"] += getattr(um, "candidates_token_count", 0) or 0
        self.usage["cached"] += getattr(um, "cached_content_token_count", 0) or 0
        self.usage["calls"] += 1

    # ---- 低层调用（带可选字段渐进降级）----
    def _raw(self, contents, *, schema=None, max_output_tokens=None, thinking_budget=None,
             cached_content=None, temperature=None):
        kw: dict = {}
        if schema is not None:
            kw["response_mime_type"] = "application/json"
            kw["response_schema"] = schema
        if temperature is not None:
            kw["temperature"] = temperature
        if max_output_tokens:
            kw["max_output_tokens"] = max_output_tokens
        if cached_content:
            kw["cached_content"] = cached_content
        else:
            kw["system_instruction"] = self.system_instruction
        if self.media_resolution is not None:
            kw["media_resolution"] = self.media_resolution
        if thinking_budget is not None:
            kw["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

        # 配置降级只在「参数错误」时发生；瞬时错误由 _call_with_backoff 退避重试。
        strip_order = ["thinking_config", "media_resolution"]
        attempt = dict(kw)
        last = None
        for _ in range(1 + len(strip_order)):
            try:
                return self._call_with_backoff(contents, attempt)
            except Exception as e:
                last = e
                if _is_bad_request(e):
                    stripped = False
                    for k in strip_order:
                        if k in attempt:
                            self.log.warning(f"模型疑似不支持 {k}，移除后重试：{_short(e)}")
                            attempt.pop(k)
                            stripped = True
                            break
                    if stripped:
                        continue
                raise
        raise last  # type: ignore

    def _call_with_backoff(self, contents, kw, max_tries: int = 5):
        """对 503/429/网络等瞬时错误做指数退避重试（不改配置）。"""
        delay = 4.0
        last = None
        for i in range(max_tries):
            try:
                cfg = types.GenerateContentConfig(**kw)
                resp = self.client.models.generate_content(model=self.model, contents=contents, config=cfg)
                self._acc(resp)
                return resp
            except Exception as e:
                last = e
                if _is_transient(e) and i < max_tries - 1:
                    wait = delay + random.uniform(0, delay / 2)
                    self.log.warning(f"瞬时错误，{wait:.0f}s 后重试（{i+1}/{max_tries}）：{_short(e)}")
                    time.sleep(wait)
                    delay = min(delay * 2, 60.0)
                    continue
                raise
        raise last  # type: ignore

    @staticmethod
    def finish_reason(resp) -> str:
        try:
            fr = resp.candidates[0].finish_reason
        except Exception:
            return ""
        return getattr(fr, "name", str(fr)) if fr else ""

    @staticmethod
    def coerce(resp, schema):
        """把 response 解析成 python 对象（dict 或 list[dict]）。"""
        parsed = getattr(resp, "parsed", None)
        if parsed is not None:
            return _dump(parsed)
        text = getattr(resp, "text", None)
        if not text:
            raise ValueError("响应为空")
        text = _strip_fences(text)
        ta = TypeAdapter(schema)
        return _dump(ta.validate_json(text))

    # ---- 高层（带重试）：用于整段视频的结构化维度 ----
    def run(self, label, contents, schema, *, max_output_tokens=None, thinking_budget=0,
            cached_content=None, retries=2):
        base = list(contents)
        cur = list(contents)
        temp = self.temperature
        last = None
        for attempt in range(retries + 1):
            resp = self._raw(cur, schema=schema, max_output_tokens=max_output_tokens,
                             thinking_budget=thinking_budget, cached_content=cached_content,
                             temperature=temp)
            try:
                data = self.coerce(resp, schema)
                if data is None:
                    raise ValueError("解析结果为空")
                return data
            except Exception as e:
                last = e
                self.log.warning(f"[{label}] 解析失败（第 {attempt+1} 次）：{e}")
                cur = base + [f"上次输出无法解析为要求的 JSON（{e}）。请只输出严格符合 schema 的 JSON。"]
                temp = max(0.0, temp - 0.15)
        raise RuntimeError(f"[{label}] 多次重试仍失败：{last}")

    # ---- 并发 map（保序）----
    def map_parallel(self, fn, items):
        items = list(items)
        if self.workers <= 1 or len(items) <= 1:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(fn, items))


# ---------------------------------------------------------------------------
# 视频 Part 构造
# ---------------------------------------------------------------------------

def video_part(file, start: Optional[float] = None, end: Optional[float] = None,
               fps: Optional[float] = None) -> types.Part:
    vm = None
    if start is not None or end is not None or fps is not None:
        kw = {}
        if start is not None:
            kw["start_offset"] = f"{start:.3f}s"
        if end is not None:
            kw["end_offset"] = f"{end:.3f}s"
        if fps is not None:
            kw["fps"] = fps
        vm = types.VideoMetadata(**kw)
    return types.Part(
        file_data=types.FileData(file_uri=file.uri, mime_type=file.mime_type or "video/mp4"),
        video_metadata=vm,
    )


# ---------------------------------------------------------------------------
# 维度 2：字幕分块转写
# ---------------------------------------------------------------------------

def make_windows(start: float, end: float, window_sec: float, overlap_sec: float):
    step = max(1.0, window_sec - overlap_sec)
    wins, p = [], start
    while p < end - 1e-6:
        w1 = min(p + window_sec, end)
        wins.append((p, w1))
        if w1 >= end - 1e-6:
            break
        p += step
    return wins


def transcribe(runner: GeminiRunner, file, *, range_start: float, range_end: float,
               window_sec: float, overlap_sec: float, fps: float, offset_mode: str,
               result_cache: ResultCache, log) -> List[dict]:
    windows = make_windows(range_start, range_end, window_sec, overlap_sec)
    log.info(f"[transcript] 共 {len(windows)} 个窗口（窗口 {window_sec:.0f}s / 重叠 {overlap_sec:.0f}s）")

    def do(idx: int):
        w0, w1 = windows[idx]
        dim = f"transcript_w{int(w0)}_{int(w1)}"
        sig = ResultCache.sig("transcript", runner.model, TRANSCRIPT_VERSION, round(fps, 3),
                              round(w0, 1), round(w1, 1))
        cached = result_cache.get(dim, sig)
        if cached is not None:
            return cached
        segs, trunc = _call_window(runner, file, w0, w1, fps, log)
        if trunc:
            log.warning(f"[transcript] 窗口 {w0:.0f}-{w1:.0f}s 输出被截断，结果可能不全；可减小 --window-sec 重试")
        result_cache.put(dim, sig, segs)
        return segs

    raws = runner.map_parallel(do, range(len(windows)))
    merged = _merge_windows(windows, raws, offset_mode, overlap_sec, range_start, range_end, log)
    log.info(f"[transcript] 合并得到 {len(merged)} 个字幕片段（placement={offset_mode}）")
    return merged


def _call_window(runner: GeminiRunner, file, w0: float, w1: float, fps: float, log) -> Tuple[List[dict], bool]:
    part = video_part(file, w0, w1, fps)
    resp = runner._raw([part, TRANSCRIPT_PROMPT], schema=list[schemas.TranscriptSegment],
                       max_output_tokens=runner.transcript_max_tokens, thinking_budget=0, temperature=0.2)
    trunc = runner.finish_reason(resp) == "MAX_TOKENS"
    try:
        segs = runner.coerce(resp, list[schemas.TranscriptSegment])
    except Exception as e:
        log.warning(f"[transcript] 窗口 {w0:.0f}-{w1:.0f}s 解析失败：{e}")
        segs = []
    return segs, trunc


def _place_segments(w0: float, w1: float, segs, mode: str):
    """把一个窗口内的原始片段映射到真实时间区间 [w0, w1]。

    实测：Gemini 对「裁剪片段」给出的时间戳极不可靠——同一视频不同窗口可能是相对(0起)、
    绝对(偏移)、甚至超出视频长度的漂移值。但窗口内片段的**先后顺序**是可靠的，且我们已知
    每个窗口覆盖的真实区间 [w0,w1]。故默认(auto)忽略其绝对数值，按窗口内 min/max 线性
    归一化到 [w0,w1]（相当于用模型的相对节奏 + 已知窗口边界）。
    """
    rows = []
    for s in segs:
        try:
            st, en = float(s["start_sec"]), float(s["end_sec"])
        except Exception:
            continue
        txt = str(s.get("text", "")).strip()
        if txt:
            rows.append((st, en, txt))
    if not rows:
        return []
    rows.sort(key=lambda r: r[0])
    wlen = max(1e-6, w1 - w0)

    if mode == "relative":
        return [(w0 + a, w0 + max(a + 0.1, b), t) for a, b, t in rows]
    if mode == "absolute":
        return [(a, max(a + 0.1, b), t) for a, b, t in rows]

    # auto：线性归一化到 [w0, w1]
    raw0 = min(r[0] for r in rows)
    raw_end = max(r[1] for r in rows)
    span = raw_end - raw0
    out = []
    if 1e-6 < span <= wlen * 6:  # span 合理 → 用比例映射
        factor = wlen / span
        for a, b, t in rows:
            a0 = w0 + (a - raw0) * factor
            a1 = w0 + (b - raw0) * factor
            out.append((a0, a1, t))
    else:  # span 异常（全为 0 或离谱） → 按序号均匀分布
        n = len(rows)
        step = wlen / n
        for idx, (_, _, t) in enumerate(rows):
            a0 = w0 + idx * step
            out.append((a0, a0 + step, t))
    return [(min(max(a0, w0), w1), min(max(a1, a0 + 0.1), w1), t) for a0, a1, t in out]


def _merge_windows(windows, raws, mode, overlap_sec, range_start, range_end, log) -> List[dict]:
    last = len(windows) - 1
    merged = []
    for i, ((w0, w1), segs) in enumerate(zip(windows, raws)):
        placed = _place_segments(w0, w1, segs, mode)
        low = range_start if i == 0 else w0 + overlap_sec / 2
        high = (range_end + 1e9) if i == last else w1 - overlap_sec / 2
        kept = 0
        for a0, a1, text in placed:
            mid = (a0 + a1) / 2
            if low - 1e-6 <= mid < high:
                merged.append({
                    "start_sec": round(max(range_start, a0), 2),
                    "end_sec": round(min(range_end, a1), 2),
                    "text": text,
                })
                kept += 1
        log.debug(f"[transcript] 窗口 {w0:.0f}-{w1:.0f}: 原始 {len(segs)} → 保留 {kept}")
    merged.sort(key=lambda x: x["start_sec"])
    return merged


# ---------------------------------------------------------------------------
# 维度 3-6：整段视频的结构化分析
# ---------------------------------------------------------------------------

def _transcript_text(transcript, max_chars: int = 80000) -> str:
    lines = [f"[{sec_to_hms(s.get('start_sec', 0))}] {s.get('text', '')}" for s in transcript]
    txt = "\n".join(lines)
    return txt[:max_chars]


def _grounded(prompt: str, transcript) -> str:
    return (prompt + "\n\n下面是这节课【带时间戳的完整字幕】（格式 [时:分:秒] 文本）。"
            "请严格依据字幕的内容与时间戳进行分析：所有 start_time/end_time 必须取自最接近的字幕片段时间；"
            "务必通读到字幕结尾、覆盖整节课（约 "
            + (sec_to_hms(transcript[-1].get("end_sec", 0)) if transcript else "00:00:00")
            + "），不要只分析开头部分。\n\n===== 字幕开始 =====\n"
            + _transcript_text(transcript) + "\n===== 字幕结束 =====")


def _holistic(runner, label, prompt, schema, transcript, media, *, thinking_budget=0,
              max_output_tokens=16384, cached_content=None):
    """优先用字幕文本做分析（时间戳可靠、全程覆盖、更省）；无字幕时退回视频输入。"""
    if transcript:
        return runner.run(label, [_grounded(prompt, transcript)], schema,
                          thinking_budget=thinking_budget, max_output_tokens=max_output_tokens)
    contents = [prompt] if cached_content else [media, prompt]
    return runner.run(label, contents, schema, thinking_budget=thinking_budget,
                      cached_content=cached_content, max_output_tokens=max_output_tokens)


def analyze_structure(runner, transcript=None, media=None, cached_content=None):
    return _holistic(runner, "structure", STRUCTURE_PROMPT, schemas.StructureResult,
                     transcript, media, thinking_budget=0, max_output_tokens=32768,
                     cached_content=cached_content)


def analyze_knowledge(runner, transcript=None, media=None, cached_content=None):
    return _holistic(runner, "knowledge", KNOWLEDGE_PROMPT, list[schemas.KnowledgeL1],
                     transcript, media, thinking_budget=0, max_output_tokens=16384,
                     cached_content=cached_content)


def analyze_interactions(runner, transcript=None, media=None, cached_content=None):
    return _holistic(runner, "interactions", INTERACTION_PROMPT, list[schemas.InteractionEvent],
                     transcript, media, thinking_budget=0, max_output_tokens=16384,
                     cached_content=cached_content)


def analyze_ideology(runner, transcript=None, media=None, cached_content=None):
    return _holistic(runner, "ideology", IDEOLOGY_PROMPT, list[schemas.IdeologyEvent],
                     transcript, media, thinking_budget=2048, max_output_tokens=8192,
                     cached_content=cached_content)


def analyze_overview(runner, context: dict):
    prompt = OVERVIEW_PROMPT + json.dumps(context, ensure_ascii=False, indent=2)
    return runner.run("overview", [prompt], schemas.OverviewResult,
                      thinking_budget=1024, max_output_tokens=4096)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _short(e) -> str:
    return str(e).replace("\n", " ")[:160]


_TRANSIENT = ("503", "429", "500", "unavailable", "resource_exhausted", "internal error",
              "deadline", "timeout", "timed out", "connection", "disconnected", "reset by peer",
              "temporarily", "high demand", "try again", "overloaded")


def _is_transient(e) -> bool:
    s = str(e).lower()
    return any(k in s for k in _TRANSIENT)


def _is_bad_request(e) -> bool:
    s = str(e).lower()
    return ("400" in s or "invalid_argument" in s or "unknown field" in s
            or "unknown name" in s or "not supported" in s or "is not allowed" in s)


def _media_res_enum(name: Optional[str]):
    if not name or name == "default":
        return None
    m = {
        "low": types.MediaResolution.MEDIA_RESOLUTION_LOW,
        "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        "high": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    }
    return m.get(name.lower())


def _dump(obj):
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
