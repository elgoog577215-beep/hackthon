"""本地分析（不调用 Gemini）：音量曲线、口头禅、互动间隔、信息密度、词云频次、五何图。"""
from __future__ import annotations

import math
import subprocess
from typing import Any, Dict, List, Optional

import numpy as np

from .util import hms_to_sec, sec_to_hms

# 默认口头禅 / 冗余填充词表（可在 CLI 覆盖）
DEFAULT_FILLERS = [
    "那个", "然后", "就是说", "也就是说", "就是", "这个", "对吧", "是吧", "对不对",
    "那么", "其实", "所以说", "的话", "啊", "嗯", "呃", "呢", "嘛", "好吧", "比如说",
]

WUHE_CATS = ["是何", "为何", "如何", "若何", "由何"]
COG_CATS = ["记忆型", "理解型", "应用型", "分析型", "评价型", "创造型"]


# ---------------------------------------------------------------------------
# A 音量分析（逐桶相对响度 dBFS）
# ---------------------------------------------------------------------------

def analyze_volume(video_path: str, bucket_sec: float = 30.0, spl_offset: float = 0.0,
                   sample_rate: int = 16000, start: Optional[float] = None,
                   end: Optional[float] = None, log=None) -> Dict[str, Any]:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", video_path]
    if start is not None and end is not None:
        cmd += ["-t", f"{max(0.0, end - start):.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg 提取音频失败：" + err.decode("utf-8", "ignore")[:400])

    x = np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768.0
    n = x.size
    spb = max(1, int(bucket_sec * sample_rate))
    nbuckets = int(math.ceil(n / spb)) if n else 0
    result: List[float] = []
    for i in range(nbuckets):
        seg = x[i * spb:(i + 1) * spb]
        if seg.size == 0:
            continue
        rms = float(np.sqrt(np.mean(seg ** 2)))
        raw = 20.0 * math.log10(rms + 1e-9)  # dBFS，恒 ≤ 0
        # 仅对负值（dBFS）加偏移转成正数刻度；已经是正数的值不动（"原本是正的就不调整"）
        db = raw + spl_offset if raw < 0 else raw
        result.append(round(db, 2))
    duration = n / sample_rate if sample_rate else 0.0
    return {
        "total_seconds": len(result),
        "total_duration": round(duration, 2),
        "bucket_sec": bucket_sec,
        "avg_spl": round(float(np.mean(result)), 2) if result else 0.0,
        "max_spl": round(max(result), 2) if result else 0.0,
        "min_spl": round(min(result), 2) if result else 0.0,
        "result": result,
        "note": f"result 为每 {int(bucket_sec)}s 的相对响度 dBFS（非校准 SPL）；如需正数刻度可设 --spl-offset",
    }


# ---------------------------------------------------------------------------
# B 语言精炼度（口头禅频率）
# ---------------------------------------------------------------------------

def analyze_fillers(transcript: List[dict], filler_terms: Optional[List[str]] = None,
                    top_n: int = 5) -> Dict[str, Any]:
    filler_terms = filler_terms or DEFAULT_FILLERS
    full = "".join(s.get("text", "") for s in transcript)
    total_chars = len(full)
    counts = {t: full.count(t) for t in filler_terms}
    counts = {t: c for t, c in counts.items() if c > 0}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    top = []
    for term, count in ranked:
        examples = []
        for s in transcript:
            if term in s.get("text", ""):
                examples.append({
                    "start": s.get("start_sec", s.get("start", 0)),
                    "end": s.get("end_sec", s.get("end", 0)),
                    "text": s.get("text", ""),
                })
                if len(examples) >= 3:
                    break
        top.append({"term": term, "count": count, "examples": examples})

    total_filler = sum(counts.values())
    return {
        "total_chars": total_chars,
        "total_filler": total_filler,
        "redundancy_ratio": round(total_filler / total_chars, 4) if total_chars else 0.0,
        "top5": top,
        "note": "口头禅按子串计数；含包含关系的词（如“就是”/“就是说”）可能重复计。",
    }


# ---------------------------------------------------------------------------
# C 互动间隔分析
# ---------------------------------------------------------------------------

def analyze_gaps(interactions: List[dict], duration: float, max_gap_min: float = 12.0) -> Dict[str, Any]:
    times = sorted(hms_to_sec(i.get("start_time", i.get("start", 0))) for i in interactions)
    max_gap = max_gap_min * 60.0
    points = [0.0] + times + [duration]
    gaps, pure, suggestions = [], [], []
    for a, b in zip(points[:-1], points[1:]):
        g = b - a
        gaps.append({"start": round(a, 1), "end": round(b, 1),
                     "gap_sec": round(g, 1), "gap_min": round(g / 60, 1)})
        if g > max_gap:
            pure.append({"start": sec_to_hms(a), "end": sec_to_hms(b), "duration_min": round(g / 60, 1)})
            t = a + max_gap
            while t < b - 1:
                suggestions.append(sec_to_hms(t))
                t += max_gap
    return {
        "max_gap_min": max_gap_min,
        "interaction_count": len(times),
        "gaps": gaps,
        "pure_lecture_spans": pure,
        "suggested_insertions": suggestions,
    }


# ---------------------------------------------------------------------------
# D 信息密度曲线
# ---------------------------------------------------------------------------

def _flatten_leaf_starts(tree: List[dict]) -> List[float]:
    leaves = []

    def walk(node):
        children = node.get("children") or []
        if children:
            for c in children:
                walk(c)
        else:
            leaves.append(hms_to_sec(node.get("start_time", 0)))

    for n in tree:
        walk(n)
    return leaves


def analyze_density(knowledge_tree: List[dict], transcript: List[dict], duration: float,
                    bucket_sec: float = 60.0, weights=(0.6, 0.4)) -> Dict[str, Any]:
    nb = max(1, int(math.ceil(duration / bucket_sec)))
    kp = [0] * nb
    chars = [0] * nb
    for t in _flatten_leaf_starts(knowledge_tree):
        kp[min(nb - 1, int(t // bucket_sec))] += 1
    for s in transcript:
        st = s.get("start_sec", s.get("start", 0))
        chars[min(nb - 1, int(float(st) // bucket_sec))] += len(s.get("text", ""))

    def norm(arr):
        mx = max(arr) if arr else 0
        return [(v / mx) if mx > 0 else 0.0 for v in arr]

    nk, nc = norm(kp), norm(chars)
    w1, w2 = weights
    buckets = []
    for i in range(nb):
        buckets.append({
            "t_start": round(i * bucket_sec, 1),
            "t_end": round(min((i + 1) * bucket_sec, duration), 1),
            "density": round(w1 * nk[i] + w2 * nc[i], 4),
            "knowledge_points": kp[i],
            "chars": chars[i],
        })
    return {"bucket_sec": bucket_sec, "weights": {"knowledge": w1, "speech": w2}, "buckets": buckets}


# ---------------------------------------------------------------------------
# E 词云频次
# ---------------------------------------------------------------------------

_STOP = set("的 了 和 与 及 在 是 中 对 这 那 我们 你们 一个 一种 进行 以及 等 之 其 也 都 "
            "就 还 要 把 被 让 给 从 到 上 下 它 他 她 有 会 能 可以 这个 那个 什么".split())


def build_wordcloud(phrases: List[str], render: bool = False, font: Optional[str] = None,
                    out_path: Optional[str] = None, top: int = 120, log=None) -> Dict[str, Any]:
    use_jieba = False
    try:
        import jieba  # noqa
        use_jieba = True
    except Exception:
        pass

    freq: Dict[str, int] = {}
    for ph in phrases:
        ph = (ph or "").strip()
        if not ph:
            continue
        if use_jieba:
            import jieba
            toks = [w for w in jieba.cut(ph) if len(w) >= 2 and w not in _STOP]
            if not toks:
                toks = [ph]
        else:
            toks = [ph]
        for w in toks:
            freq[w] = freq.get(w, 0) + 1

    items = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:top]
    frequencies = {k: v for k, v in items}

    image_path = None
    if render and frequencies:
        image_path = _render_wordcloud(frequencies, font, out_path, log)
    return {"frequencies": frequencies, "image_path": image_path,
            "engine": "jieba" if use_jieba else "phrase"}


def _render_wordcloud(frequencies, font, out_path, log):
    try:
        from wordcloud import WordCloud
    except Exception as e:
        if log:
            log.warning(f"[wordcloud] 未安装 wordcloud，跳过 PNG 渲染：{e}")
        return None
    font = font or _default_cjk_font()
    if not font:
        if log:
            log.warning("[wordcloud] 未找到中文字体，跳过 PNG 渲染")
        return None
    try:
        wc = WordCloud(font_path=font, width=1200, height=700, background_color="white",
                       prefer_horizontal=0.9, collocations=False)
        wc.generate_from_frequencies(frequencies)
        wc.to_file(out_path)
        return out_path
    except Exception as e:
        if log:
            log.warning(f"[wordcloud] 渲染失败：{e}")
        return None


def _default_cjk_font():
    import os
    for p in [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# F 五何互动交流图
# ---------------------------------------------------------------------------

def build_wuhe(interactions: List[dict]) -> Dict[str, Any]:
    counts = {c: 0 for c in WUHE_CATS}
    cog_counts = {c: 0 for c in COG_CATS}
    cross: Dict[tuple, int] = {}
    for it in interactions:
        w = it.get("wuhe")
        t = it.get("type")
        if w in counts:
            counts[w] += 1
        if t in cog_counts:
            cog_counts[t] += 1
        if w in counts and t in cog_counts:
            cross[(w, t)] = cross.get((w, t), 0) + 1

    present_w = [c for c in WUHE_CATS if counts[c] > 0]
    present_c = [c for c in COG_CATS if cog_counts[c] > 0]
    nodes = [{"name": "互动"}] + [{"name": c} for c in present_w] + [{"name": c} for c in present_c]
    links = [{"source": "互动", "target": c, "value": counts[c]} for c in present_w]
    for (w, t), v in cross.items():
        links.append({"source": w, "target": t, "value": v})

    return {"total": len(interactions), "counts": counts, "cognitive_counts": cog_counts,
            "nodes": nodes, "links": links}
