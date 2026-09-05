"""
教学表达二次处理模块。

从超星转写/分析结果中提取并二次加工：
- 音量分析（透传）
- 语速分析（仿照超星 teach_db_result 格式）
- 语言精炼度（口头禅检测）
"""

import re
from typing import Any

from common.utils.logger import get_logger

logger = get_logger(__name__)

# 冗余填充词正则（从左到右优先匹配长模式）
FILLER_PATTERNS = [
    r"那个(?:什么|啥)?",
    r"然后(?:呢)?",
    r"就是(?:说)?",
    r"对吧|是不是|对吗",
    r"这(?:个|些|样)",
    r"那(?:么|样|样的话)?",
    r"嗯+|啊+|哦+|呃+|唉+|哎+|哟+|呢+|吧+|嘛+|啦+|哈+",
    r"其实|本来|反正|不过|但是|所以|于是|接着|后来|最后",
    r"首先|其次|例如|比如|好比|像是|好像",
    r"大概|大约|差不多|基本上|也许|可能|应该",
    r"总的来说|换言之|换句话说|也就是说|说白了|老实说|说实话|坦白说",
    r"一般来讲|一般而言|一般来说|通常情况下|大多数时候",
]
FILLER_REGEX = re.compile("|".join(FILLER_PATTERNS))


def extract_volume_analysis(analyze_data: dict) -> dict:
    """直接提取超星音量分析结果。"""
    db_result = analyze_data.get("teach_db_result", {}).get("data", {})
    if not db_result:
        return {}
    return {
        "total_seconds": db_result.get("total_seconds", 0),
        "total_duration": db_result.get("total_duration", 0.0),
        "avg_spl": db_result.get("avg_spl", 0.0),
        "max_spl": db_result.get("max_spl", 0.0),
        "min_spl": db_result.get("min_spl", 0.0),
        "result": db_result.get("result", []),
    }


def analyze_speech_rate(transcript_data: dict, analyze_data: dict) -> dict:
    """
    计算语速（CPM，字/分钟），输出格式仿照超星 teach_db_result。
    """
    total_windows, total_duration = _get_window_params(transcript_data, analyze_data)
    if total_windows <= 0 or total_duration <= 0:
        return {
            "total_windows": 0,
            "total_duration": 0.0,
            "avg_cpm": 0.0,
            "max_cpm": 0.0,
            "min_cpm": 0.0,
            "result": [],
        }

    window_duration = total_duration / total_windows
    transcript = transcript_data.get("transcript", [])
    window_chars: list[float] = [0.0] * total_windows

    for item in transcript:
        start = float(item.get("start", 0))
        end = float(item.get("end", 0))
        text = item.get("text", "")
        # 以中文字符数衡量内容量
        chars = len(re.findall(r"[一-鿿]", text))

        if chars <= 0:
            continue

        start_win = int(start / window_duration)
        end_win = int(end / window_duration)
        start_win = max(0, min(start_win, total_windows - 1))
        end_win = max(0, min(end_win, total_windows - 1))

        if start_win == end_win:
            window_chars[start_win] += chars
        else:
            total_span = end - start
            if total_span <= 0:
                window_chars[start_win] += chars
                continue
            for w in range(start_win, end_win + 1):
                win_start = max(start, w * window_duration)
                win_end = min(end, (w + 1) * window_duration)
                overlap = max(0, win_end - win_start)
                ratio = overlap / total_span
                window_chars[w] += chars * ratio

    minute_per_window = window_duration / 60.0
    cpms = [
        wc / minute_per_window if minute_per_window > 0 else 0.0
        for wc in window_chars
    ]

    avg_cpm = round(sum(cpms) / len(cpms), 2) if cpms else 0.0
    max_cpm = round(max(cpms), 2) if cpms else 0.0
    min_cpm = round(min(cpms), 2) if cpms else 0.0

    return {
        "total_windows": total_windows,
        "total_duration": round(total_duration, 2),
        "avg_cpm": avg_cpm,
        "max_cpm": max_cpm,
        "min_cpm": min_cpm,
        "result": [round(c, 2) for c in cpms],
    }


def analyze_language_conciseness(transcript_data: dict) -> dict:
    """
    检测冗余填充词（口头禅）频率及占比，返回 TOP5 及典型语句。
    """
    transcript = transcript_data.get("transcript", [])
    full_text = "".join(item.get("text", "") for item in transcript)
    cleaned_text = re.sub(r"\s", "", full_text)

    if not cleaned_text:
        return {
            "filler_word_ratio": 0.0,
            "filler_word_count": 0,
            "total_word_count": 0,
            "top_filler_words": [],
        }

    total_word_count = len(cleaned_text)

    # 统计各填充词出现次数
    term_counts: dict[str, int] = {}
    for m in FILLER_REGEX.finditer(full_text):
        term = m.group()
        term_counts[term] = term_counts.get(term, 0) + 1

    filler_word_count = sum(term_counts.values())
    filler_word_ratio = (
        round(filler_word_count / total_word_count, 4)
        if total_word_count > 0
        else 0.0
    )

    # 取 TOP5
    sorted_terms = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    top_filler_words: list[dict[str, Any]] = []
    for term, count in sorted_terms:
        examples = []
        for item in transcript:
            text = item.get("text", "")
            if term in text:
                examples.append({
                    "start": item["start"],
                    "end": item["end"],
                    "text": text.strip(),
                })
                if len(examples) >= 3:
                    break
        top_filler_words.append({
            "term": term,
            "count": count,
            "examples": examples,
        })

    return {
        "filler_word_ratio": filler_word_ratio,
        "filler_word_count": filler_word_count,
        "total_word_count": total_word_count,
        "top_filler_words": top_filler_words,
    }


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------

def _get_window_params(transcript_data: dict, analyze_data: dict) -> tuple[int, float]:
    """确定语速/密度分析的窗口数和总时长。"""
    db_result = analyze_data.get("teach_db_result", {}).get("data", {})
    total_windows = db_result.get("total_seconds", 0)
    total_duration = db_result.get("total_duration", 0.0)

    if total_windows > 0 and total_duration > 0:
        return total_windows, total_duration

    # fallback：从 transcript 推算
    transcript = transcript_data.get("transcript", [])
    if not transcript:
        return 0, 0.0

    total_duration = float(transcript[-1].get("end", 0))
    # 按 30s 窗口对齐
    total_windows = max(1, int(total_duration / 30))
    return total_windows, total_duration
