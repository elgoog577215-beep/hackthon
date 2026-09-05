"""
互动质量二次处理模块。

从超星分析结果中提取并二次加工：
- 互动事件时序
- 互动间隔（纯讲授段）
- 五何互动分布及典型案例
"""

from typing import Any

from common.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 公共函数
# ---------------------------------------------------------------------------


def extract_interaction_events(analyze_data: dict) -> dict[str, Any]:
    """提取互动事件及统计信息。"""
    teach_question = analyze_data.get("teach_question", {})

    events = []
    for q in teach_question.get("questions", []):
        events.append({
            "text": q.get("text", ""),
            "type": q.get("type", ""),
            "segment": q.get("segment", ""),
            "start_time": q.get("start_time", ""),
            "end_time": q.get("end_time", ""),
        })

    stats = {}
    for t, data in teach_question.get("statistics", {}).items():
        stats[t] = data.get("count", 0)

    return {
        "interaction_events": events,
        "type_statistics": stats,
    }


def compute_interaction_gaps(
    analyze_data: dict,
    transcript_data: dict,
) -> list[dict]:
    """
    计算互动间隔，标注超过12分钟无互动的纯讲授段。
    每个纯讲授段内部包含建议插入互动的时间点。
    """
    teach_question = analyze_data.get("teach_question", {})
    questions = teach_question.get("questions", [])

    # 课程总时长
    transcript = transcript_data.get("transcript", [])
    total_duration = float(transcript[-1].get("end", 0)) if transcript else 0.0

    if not questions:
        return []

    # 按时间排序
    sorted_q = sorted(
        questions,
        key=lambda x: _time_to_seconds(x.get("start_time", "00:00:00")),
    )

    gaps: list[dict[str, Any]] = []

    # 1. 课程开始到第一个互动
    first_start = _time_to_seconds(sorted_q[0].get("start_time", "00:00:00"))
    if first_start > 720:
        gaps.append(_build_gap(0.0, first_start))

    # 2. 相邻互动之间
    for i in range(1, len(sorted_q)):
        prev_end = _time_to_seconds(sorted_q[i - 1].get("end_time", "00:00:00"))
        curr_start = _time_to_seconds(sorted_q[i].get("start_time", "00:00:00"))
        gap = curr_start - prev_end
        if gap > 720:
            gaps.append(_build_gap(prev_end, curr_start))

    # 3. 最后一个互动到课程结束
    last_end = _time_to_seconds(sorted_q[-1].get("end_time", "00:00:00"))
    if total_duration > 0 and (total_duration - last_end) > 720:
        gaps.append(_build_gap(last_end, total_duration))

    return gaps


def analyze_wh_distribution(analyze_data: dict) -> dict[str, Any]:
    """分析五何互动分布及典型案例。"""
    teach_wh = analyze_data.get("teach_wh", [])

    stats: dict[str, dict[str, Any]] = {}

    for item in teach_wh:
        category = item.get("category", "其他")
        if category not in stats:
            stats[category] = {"count": 0, "ratio": 0.0, "examples": []}

        stats[category]["count"] += 1

        # 每个类别最多收集 3 条示例
        if len(stats[category]["examples"]) < 3:
            stats[category]["examples"].append({
                "start": item.get("start", ""),
                "end": item.get("end", ""),
                "text": item.get("text", "").strip(),
            })

    total = len(teach_wh)
    for category in stats:
        stats[category]["ratio"] = (
            round(stats[category]["count"] / total, 4) if total > 0 else 0.0
        )

    return stats


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _time_to_seconds(t: str) -> float:
    """将时间字符串转换为秒数，支持 HH:MM:SS / MM:SS / 纯秒数。"""
    if not t:
        return 0.0
    t = str(t).strip()
    try:
        return float(t)
    except ValueError:
        pass
    parts = t.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0.0


def _seconds_to_time(s: float) -> str:
    """秒数转换为 HH:MM:SS 或 MM:SS。"""
    hours = int(s // 3600)
    minutes = int((s % 3600) // 60)
    seconds = int(s % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _build_gap(start: float, end: float) -> dict[str, Any]:
    """构建一个纯讲授段 gap 结构（含建议）。"""
    gap = end - start
    suggestion_time = (start + end) / 2
    minutes = int(gap // 60)
    secs = int(gap % 60)
    return {
        "start": _seconds_to_time(start),
        "end": _seconds_to_time(end),
        "duration_seconds": int(gap),
        "label": "纯讲授段",
        "suggestion": {
            "time": _seconds_to_time(suggestion_time),
            "reason": (
                f"距上次互动已超12分钟（{minutes}分{secs}秒），"
                "建议在此插入互动以活跃课堂"
            ),
        },
    }
