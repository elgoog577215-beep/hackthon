"""本地视频分析 runner。

以编程方式跑通 video-analyze POC 的 **Qwen/vLLM 路径**，直接返回 POC 的 report dict。
等价于 `analyze.py main()` 的 qwen 分支，但去掉了 argparse / dotenv / 结果落盘 /
slides / report.html 等只在 CLI 场景需要的部分。

注意：整条流水线是**阻塞式**的（同步 OpenAI 客户端 + ffmpeg 子进程 + 内部线程池），
调用方必须用 `asyncio.to_thread(run_local_analysis, ...)` 包裹，避免阻塞事件循环。
"""
from __future__ import annotations

import math
import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Optional

_range = range  # 保留内置 range，避免被函数参数 range= 遮蔽

from ._vendor import gemini_steps, local_steps
from ._vendor import qwen_provider as qw
from ._vendor.util import get_logger, hms_to_sec


class AnalysisCancelled(Exception):
    """分析被取消（例如分析过程中视频被删除）。用于与真正的失败区分，调用方据此静默收尾。"""
    pass


# ---------------------------------------------------------------------------
# 无副作用的结果缓存桩：vendored 函数签名要求一个 cache 参数，
# 但服务端按请求执行、不做断点续跑，也不应往容器文件系统落盘。
# ---------------------------------------------------------------------------
class _NoCache:
    hits = 0

    def get(self, dim: str, sig: str) -> None:
        return None

    def put(self, dim: str, sig: str, data: Any) -> None:
        return None

    @staticmethod
    def sig(*parts: Any) -> str:
        return ""


# ---------------------------------------------------------------------------
# 从 analyze.py 搬来的总评辅助（这些函数只存在于 analyze.py，不在任何模块里）
# ---------------------------------------------------------------------------
def _count_leaves(tree: list) -> int:
    n = 0
    for node in tree:
        ch = node.get("children") or []
        n += _count_leaves(ch) if ch else 1
    return n


def _dist(items: list, key: str) -> dict:
    d: dict = {}
    for it in items:
        v = it.get(key)
        if v:
            d[v] = d.get(v, 0) + 1
    return d


def _overview_context(meta, duration, chapters, knowledge, interactions, ideology,
                      fillers, volume, gaps, wuhe) -> dict:
    seg_types: dict = {}
    for ch in chapters:
        for s in ch.get("file_structure", []):
            dur = max(0.0, hms_to_sec(s.get("end_time", 0)) - hms_to_sec(s.get("start_time", 0)))
            seg_types[s.get("type", "其他")] = round(seg_types.get(s.get("type", "其他"), 0) + dur)
    return {
        "course": meta.get("courseName"),
        "duration_sec": round(duration),
        "segment_type_seconds": seg_types,
        "chapter_count": len(chapters),
        "knowledge_point_count": _count_leaves(knowledge),
        "interaction": {
            "count": len(interactions),
            "cognitive_dist": _dist(interactions, "type"),
            "wuhe_dist": (wuhe or {}).get("counts", {}),
            "pure_lecture_spans": (gaps or {}).get("pure_lecture_spans", []),
        },
        "sizheng_count": len(ideology),
        "sizheng_avg_naturalness": round(
            sum((e.get("result", {}) or {}).get("naturalness", 0) for e in ideology) / len(ideology), 2)
        if ideology else None,
        "fillers_top5": [{"term": t["term"], "count": t["count"]} for t in (fillers or {}).get("top5", [])],
        "fillers_redundancy_ratio": (fillers or {}).get("redundancy_ratio"),
        "volume": {k: volume.get(k) for k in ("avg_spl", "max_spl", "min_spl")} if volume else {},
    }


def _collect_terms(knowledge: list, chapters: list) -> list:
    terms: list = []

    def walk(node):
        if node.get("title"):
            terms.append(node["title"])
        for c in node.get("children") or []:
            walk(c)

    for n in knowledge:
        walk(n)
    for ch in chapters:
        for s in ch.get("file_structure", []):
            for kp in s.get("keypoint", []) or []:
                if kp.get("name"):
                    terms.append(kp["name"])
    return terms


# ---------------------------------------------------------------------------
# Map-reduce: 长视频分段并行 LLM → 合并
# ---------------------------------------------------------------------------
_SEGMENT_SEC = 180.0  # 每段 3 分钟——vLLM 6×A800 可充分并行


def _split_transcript(transcript, segment_sec=_SEGMENT_SEC):
    """按时间把 transcript 切成若干段，每段 ~segment_sec 秒。"""
    if not transcript:
        return [transcript]
    end_sec = transcript[-1].get("end_sec", 0)
    if end_sec <= segment_sec * 1.5:
        return [transcript]
    segments = []
    seg_start = 0.0
    while seg_start < end_sec:
        seg_end = seg_start + segment_sec
        seg = [
            s for s in transcript
            if s.get("end_sec", s.get("start_sec", 0)) > seg_start
            and s.get("start_sec", 0) < seg_end
        ]
        if seg:
            segments.append(seg)
        seg_start = seg_end
    return segments


def _merge_structure(results):
    chapters, intro, summary = [], {}, {}
    for i, r in enumerate(results):
        if not r or not isinstance(r, dict):
            continue
        chapters.extend(r.get("chapters", []))
        if i == 0:
            intro = r.get("intro_analysis", {})
        if i == len(results) - 1:
            summary = r.get("summary_analysis", {})
    return {"chapters": chapters, "intro_analysis": intro, "summary_analysis": summary}


def _merge_knowledge(results):
    merged = []
    for seg in results:
        if isinstance(seg, list):
            merged.extend(seg)
    idx = 0
    for node in merged:
        if not isinstance(node, dict):
            continue
        idx += 1
        node["id"] = str(idx)
        for j, ch in enumerate(node.get("children") or []):
            if isinstance(ch, dict):
                ch["id"] = f"{idx}.{j + 1}"
                for k, gc in enumerate(ch.get("children") or []):
                    if isinstance(gc, dict):
                        gc["id"] = f"{idx}.{j + 1}.{k + 1}"
    return merged


def _merge_flat(results):
    merged = []
    for seg in results:
        if isinstance(seg, list):
            merged.extend(seg)
    return merged


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def _safe(name: str, fn, errors: dict, default, log):
    """执行单个维度分析，失败时记录到 errors 并返回默认值（不让整体崩溃）。"""
    try:
        log.info("[local-analysis] %s ...", name)
        return fn()
    except Exception as e:  # noqa: BLE001 - 单维度失败可降级
        log.error("[local-analysis] %s 失败：%s", name, e)
        errors[name] = str(e)
        return default


def _probe_text_service(client, model: str, base_url: str, log) -> None:
    """对文本服务做一次轻量连通性探测；不可用时快速失败（抛普通异常，
    不用 vendored 的 qwen_connectivity_check —— 它会 raise SystemExit，
    在 worker 线程里会异常退出）。"""
    try:
        client.chat.completions.create(
            model=model,
            max_tokens=8,
            messages=[{"role": "user", "content": '只输出 json：{"ok":true}'}],
            response_format={"type": "json_object"},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        log.info("[local-analysis] 文本服务连通正常（%s, %s）", base_url, model)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"本地分析文本服务不可用（model={model}, base_url={base_url}）：{e}"
        ) from e


def run_local_analysis(
    video_path: str,
    *,
    range: Optional[tuple[float, float]] = None,
    text_base_url: str,
    asr_base_url: str,
    model: str = "qwen3.6-35b-a3b",
    asr_model: str = "qwen3-asr-1.7b",
    api_key: str = "EMPTY",
    course_name: str = "",
    sub_title: str = "",
    url: str = "",
    workers: int = 3,
    bucket_sec: float = 30.0,
    density_bucket_sec: float = 60.0,
    max_gap_min: float = 12.0,
    asr_chunk_sec: float = 60.0,
    log=None,
) -> dict:
    """对本地视频文件跑完整的本地分析流水线，返回 POC 的 report dict。

    Args:
        video_path: 视频文件绝对路径。
        range: 可选 (start_sec, end_sec)，仅分析该时间段（用于 2 分钟联调短片段）。
        text_base_url / asr_base_url: 自建 vLLM 的文本 / ASR OpenAI 兼容地址。
        model / asr_model: 文本模型 / ASR 模型名。
    Returns:
        report dict，键与 analyze.py 落盘的 report.json 一致。
    """
    log = log or get_logger(False)

    if not os.path.exists(video_path):
        raise RuntimeError(f"视频文件不存在：{video_path}")

    duration_full = local_steps_probe_duration(video_path)
    rstart = range[0] if range else 0.0
    rend = min(range[1], duration_full) if range else duration_full
    log.info(
        "[local-analysis] 视频=%s 总时长=%.1fs 分析区间=%.1f-%.1fs provider=qwen 模型=%s",
        os.path.basename(video_path), duration_full, rstart, rend, model,
    )

    # ---- provider: 文本 runner + ASR（支持逗号分隔的多实例 URL）----
    text_urls = [u.strip() for u in text_base_url.split(",") if u.strip()]
    clients = [qw.make_qwen_client(api_key, u) for u in text_urls]
    _probe_text_service(clients[0], model, text_urls[0], log)
    runner = qw.QwenRunner(clients, model, log, workers=workers, enable_thinking=False)
    asr = qw.make_asr_caller(asr_base_url, api_key, asr_model, log)
    rcache = _NoCache()
    errors: dict = {}

    def _cancel_check() -> None:
        if not os.path.exists(video_path):
            raise AnalysisCancelled(f"视频文件已删除，取消分析：{video_path}")

    _STRUCT_DEFAULT = {"chapters": [], "intro_analysis": {}, "summary_analysis": {}}
    _DIMS = [
        ("structure", gemini_steps.analyze_structure, _STRUCT_DEFAULT),
        ("knowledge", gemini_steps.analyze_knowledge, []),
        ("interactions", gemini_steps.analyze_interactions, []),
        ("ideology", gemini_steps.analyze_ideology, []),
    ]

    # ---- 计算分段边界（ASR chunk 级 + LLM segment 级）----
    duration = rend - rstart
    n_seg = max(1, math.ceil(duration / _SEGMENT_SEC)) if duration > _SEGMENT_SEC * 1.5 else 1
    seg_bounds = []
    for si in _range(n_seg):
        s = rstart + si * _SEGMENT_SEC
        e = min(rstart + (si + 1) * _SEGMENT_SEC, rend)
        seg_bounds.append((s, e))

    # 全局线程池：ASR workers + LLM 并发(4 per seg) + 音量 1
    pool = ThreadPoolExecutor(max_workers=max(workers, n_seg * 4) + 1)

    # ---- 音量：独立于 ASR/LLM，立即启动 ----
    f_volume: Future = pool.submit(
        _safe, "volume",
        lambda: local_steps.analyze_volume(
            video_path, bucket_sec=bucket_sec, spl_offset=90.0,
            start=(rstart if range else None), end=(rend if range else None), log=log,
        ),
        errors, {}, log,
    )

    # ---- 流式流水线：ASR 按段完成 → 立即投喂 LLM ----
    # 预分配固定大小列表，按索引写入以保证线程安全和顺序
    seg_futures: dict[str, list[Future | None]] = {d[0]: [None] * n_seg for d in _DIMS}
    all_transcript: list[list] = [[] for _ in _range(n_seg)]

    def _asr_segment(si: int) -> list:
        """对第 si 段做 ASR 并返回该段字幕列表。"""
        s, e = seg_bounds[si]
        seg_transcript = qw.qwen_transcribe(
            asr, video_path, range_start=s, range_end=e,
            chunk_sec=asr_chunk_sec, model=asr_model,
            result_cache=rcache, workers=workers, log=log,
            cancel_check=_cancel_check,
        )
        return seg_transcript or []

    def _asr_then_llm(si: int) -> None:
        """ASR 第 si 段，完成后立即提交该段的 4 维度 LLM。"""
        seg_t = _asr_segment(si)
        all_transcript[si] = seg_t
        if not seg_t:
            for dim_name, _, dim_default in _DIMS:
                f: Future = Future()
                f.set_result(dim_default)
                seg_futures[dim_name][si] = f
            return
        _cancel_check()
        for dim_name, dim_fn, dim_default in _DIMS:
            f = pool.submit(
                _safe, f"{dim_name}[{si}]",
                lambda _fn=dim_fn, _t=seg_t: _fn(runner, transcript=_t),
                errors, dim_default, log,
            )
            seg_futures[dim_name][si] = f

    if n_seg > 1:
        log.info("[local-analysis] 流式流水线: %d 段 × 4 维度, ASR→LLM 重叠执行", n_seg)
        asr_futs = [pool.submit(_asr_then_llm, si) for si in _range(n_seg)]
        for f in asr_futs:
            f.result()
    else:
        log.info("[local-analysis] 短视频单段: ASR → 4 维度并行 LLM")
        seg_t = _asr_segment(0)
        all_transcript[0] = seg_t
        if not seg_t:
            pool.shutdown(wait=False)
            raise RuntimeError("ASR 未产出任何字幕，无法进行后续分析（请检查 ASR 服务与视频音轨）")
        _cancel_check()
        for dim_name, dim_fn, dim_default in _DIMS:
            f = pool.submit(
                _safe, dim_name,
                lambda _fn=dim_fn, _t=seg_t: _fn(runner, transcript=_t),
                errors, dim_default, log,
            )
            seg_futures[dim_name][0] = f

    # ---- 收集结果 ----
    transcript = [s for seg in all_transcript for s in seg]
    if not transcript:
        pool.shutdown(wait=False)
        raise RuntimeError("ASR 未产出任何字幕，无法进行后续分析（请检查 ASR 服务与视频音轨）")

    if n_seg > 1:
        structure = _merge_structure([f.result() for f in seg_futures["structure"]])
        knowledge = _merge_knowledge([f.result() for f in seg_futures["knowledge"]])
        interactions = _merge_flat([f.result() for f in seg_futures["interactions"]])
        ideology = _merge_flat([f.result() for f in seg_futures["ideology"]])
    else:
        structure = seg_futures["structure"][0].result() or _STRUCT_DEFAULT
        knowledge = seg_futures["knowledge"][0].result() or []
        interactions = seg_futures["interactions"][0].result() or []
        ideology = seg_futures["ideology"][0].result() or []

    volume = f_volume.result()
    pool.shutdown(wait=False)

    chapters = structure.get("chapters", [])

    # ---- 其余本地分析 ----
    fillers = _safe("fillers", lambda: local_steps.analyze_fillers(transcript), errors, {}, log)
    gaps = _safe("gaps", lambda: local_steps.analyze_gaps(interactions, rend, max_gap_min), errors, {}, log)
    density = _safe("density", lambda: local_steps.analyze_density(knowledge, transcript, rend, density_bucket_sec), errors, {}, log)
    wuhe = _safe("wuhe", lambda: local_steps.build_wuhe(interactions), errors, {}, log)
    phrases = _collect_terms(knowledge, chapters)
    wordcloud = _safe("wordcloud", lambda: local_steps.build_wordcloud(phrases, render=False), errors, {}, log)

    # ---- 总评（依赖前面所有结果）----
    meta = {"courseName": course_name, "subTitle": sub_title, "url": url}
    ctx = _overview_context(meta, rend, chapters, knowledge, interactions, ideology,
                            fillers, volume, gaps, wuhe)
    overview = _safe("overview", lambda: gemini_steps.analyze_overview(runner, ctx), errors, {}, log)

    # ---- 思政：补 result.融入自然度 中文键，并把时间归一到秒 ----
    sizheng = []
    for e in ideology:
        r = dict(e.get("result", {}))
        if "naturalness" in r:
            r["融入自然度"] = r["naturalness"]
        sizheng.append({
            "start": round(hms_to_sec(e.get("start_time", e.get("start", 0))), 1),
            "end": round(hms_to_sec(e.get("end_time", e.get("end", 0))), 1),
            "result": r,
        })

    # ---- 组装 report（键与 analyze.py 落盘的 report.json 一致）----
    overall = dict(overview)
    overall.update({"courseName": meta["courseName"], "subTitle": meta["subTitle"], "url": meta["url"]})
    report = {
        "meta": {
            **meta,
            "video": os.path.basename(video_path),
            "duration": round(rend, 2),
            "provider": "qwen",
            "model": model,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "range": list(range) if range else None,
            "tokens": runner.usage,
            "errors": errors,
        },
        "overall": overall,
        "transcript": transcript,
        "volume": volume,
        "fillers": fillers,
        "segments": chapters,
        "structure_extra": {
            "intro_analysis": structure.get("intro_analysis", {}),
            "summary_analysis": structure.get("summary_analysis", {}),
        },
        "knowledge": knowledge,
        "interactions": interactions,
        "sizheng": sizheng,
        "density": density,
        "wordcloud": wordcloud,
        "gaps": gaps,
        "wuhe": wuhe,
    }
    log.info("[local-analysis] 完成：综合得分=%s，失败维度=%s",
             overall.get("overall_score"), list(errors.keys()) or "无")
    return report


def local_steps_probe_duration(video_path: str) -> float:
    """探测视频时长（封装 vendored util.probe_duration，便于单测替换）。"""
    from ._vendor.util import probe_duration
    return probe_duration(video_path)
