"""
教学设计二次处理模块。

从超星分析结果中提取并二次加工：
- 课堂环节扁平化时序标注
- 各环节占比
- 信息密度曲线
"""

import re
from typing import Any

from common.utils.logger import get_logger

logger = get_logger(__name__)

# 环节类型 -> 信息密度权重
TYPE_WEIGHT_MAP = {
    "讲授新课": 1.0,
    "知识讲解": 1.0,
    "新课讲授": 1.0,
    "互动问答": 0.9,
    "提问": 0.9,
    "课堂互动": 0.9,
    "课程回顾": 0.7,
    "复习回顾": 0.7,
    "导入新课": 0.8,
    "总结归纳": 0.75,
    "布置作业/任务": 0.5,
    "作业布置": 0.5,
    "纠错反馈": 0.6,
    "反馈评价": 0.6,
}


def flatten_segments(analyze_data: dict) -> list[dict]:
    """
    将超星 teach_summary 嵌套结构扁平化为一维时序数组。
    """
    teach_summary = analyze_data.get("teach_summary", [])
    segments: list[dict[str, Any]] = []

    for block in teach_summary:
        for fs in block.get("file_structure", []):
            keypoints = fs.get("keypoint", [])
            first_kp = keypoints[0] if keypoints else {}
            segments.append({
                "start_time": fs.get("start_time", ""),
                "end_time": fs.get("end_time", ""),
                "type": fs.get("type", "") or "其他",
                "sub_type": fs.get("sub_type", ""),
                "content": fs.get("content", ""),
                "keypoint_name": first_kp.get("name", ""),
                "keypoint_start": first_kp.get("start_time", ""),
                "keypoint_end": first_kp.get("end_time", ""),
            })

    return segments


def compute_type_distribution(segments: list[dict]) -> list[dict]:
    """统计各环节类型的时长占比。"""
    stats: dict[str, dict[str, Any]] = {}
    total_duration = 0.0

    for seg in segments:
        seg_type = seg.get("type") or "其他"
        start = _time_to_seconds(seg["start_time"])
        end = _time_to_seconds(seg["end_time"])
        duration = max(0.0, end - start)

        if seg_type not in stats:
            stats[seg_type] = {"count": 0, "duration_seconds": 0.0}
        stats[seg_type]["count"] += 1
        stats[seg_type]["duration_seconds"] += duration
        total_duration += duration

    result = []
    for seg_type, data in stats.items():
        result.append({
            "type": seg_type,
            "count": data["count"],
            "duration_seconds": round(data["duration_seconds"], 2),
            "ratio": (
                round(data["duration_seconds"] / total_duration, 4)
                if total_duration > 0
                else 0.0
            ),
        })

    result.sort(key=lambda x: x["duration_seconds"], reverse=True)
    return result


def compute_information_density(
    transcript_data: dict,
    segments: list[dict],
    analyze_data: dict,
) -> dict:
    """
    计算信息密度曲线，窗口粒度与超星音量数据保持一致（约 30s）。

    密度 = normalize(语速 CPM) * 0.6 + 环节类型权重 * 0.4
    """
    total_windows, total_duration = _get_window_params(transcript_data, analyze_data)
    if total_windows <= 0 or total_duration <= 0:
        return {
            "window_size_seconds": 30,
            "total_windows": 0,
            "avg_density": 0.0,
            "max_density": 0.0,
            "min_density": 0.0,
            "result": [],
        }

    window_duration = total_duration / total_windows
    transcript = transcript_data.get("transcript", [])
    window_chars: list[float] = [0.0] * total_windows

    # 1. 统计每窗口中文字符数
    for item in transcript:
        start = float(item.get("start", 0))
        end = float(item.get("end", 0))
        text = item.get("text", "")
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
                overlap = max(0.0, win_end - win_start)
                ratio = overlap / total_span
                window_chars[w] += chars * ratio

    # 2. 语速因子（CPM 归一化）
    minute_per_window = window_duration / 60.0
    cpms = [
        wc / minute_per_window if minute_per_window > 0 else 0.0
        for wc in window_chars
    ]
    min_cpm = min(cpms) if cpms else 0.0
    max_cpm = max(cpms) if cpms else 0.0
    if max_cpm > min_cpm:
        speed_factors = [(c - min_cpm) / (max_cpm - min_cpm) for c in cpms]
    else:
        speed_factors = [0.5] * total_windows

    # 3. 环节类型权重（按覆盖时长加权）
    type_weight_accumulators: list[list[tuple[float, float]]] = [
        [] for _ in range(total_windows)
    ]

    for seg in segments:
        seg_type = seg.get("type", "")
        weight = TYPE_WEIGHT_MAP.get(seg_type, 0.6)
        seg_start = _time_to_seconds(seg["start_time"])
        seg_end = _time_to_seconds(seg["end_time"])

        start_win = int(seg_start / window_duration)
        end_win = int(seg_end / window_duration)
        start_win = max(0, min(start_win, total_windows - 1))
        end_win = max(0, min(end_win, total_windows - 1))

        for w in range(start_win, end_win + 1):
            win_start = w * window_duration
            win_end = (w + 1) * window_duration
            overlap = max(0.0, min(seg_end, win_end) - max(seg_start, win_start))
            if overlap > 0:
                type_weight_accumulators[w].append((weight, overlap))

    type_weights: list[float] = []
    for acc in type_weight_accumulators:
        if not acc:
            type_weights.append(0.6)
        else:
            total_overlap = sum(o for _, o in acc)
            weighted_sum = sum(w * o for w, o in acc)
            type_weights.append(
                weighted_sum / total_overlap if total_overlap > 0 else 0.6
            )

    # 4. 综合密度
    densities = [
        round(speed_factors[w] * 0.6 + type_weights[w] * 0.4, 4)
        for w in range(total_windows)
    ]

    avg_density = round(sum(densities) / len(densities), 4) if densities else 0.0
    max_density = round(max(densities), 4) if densities else 0.0
    min_density = round(min(densities), 4) if densities else 0.0

    return {
        "window_size_seconds": round(window_duration, 2),
        "total_windows": total_windows,
        "avg_density": avg_density,
        "max_density": max_density,
        "min_density": min_density,
        "result": densities,
    }


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


def _get_window_params(transcript_data: dict, analyze_data: dict) -> tuple[int, float]:
    """确定分析的窗口数和总时长。"""
    db_result = analyze_data.get("teach_db_result", {}).get("data", {})
    total_windows = db_result.get("total_seconds", 0)
    total_duration = db_result.get("total_duration", 0.0)

    if total_windows > 0 and total_duration > 0:
        return total_windows, total_duration

    transcript = transcript_data.get("transcript", [])
    if not transcript:
        return 0, 0.0

    total_duration = float(transcript[-1].get("end", 0))
    total_windows = max(1, int(total_duration / 30))
    return total_windows, total_duration
