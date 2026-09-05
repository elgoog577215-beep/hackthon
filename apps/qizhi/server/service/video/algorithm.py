import json
import math
from typing import Any


def _safe_json_loads(val: str | list | dict | None) -> list | dict:
    """安全地将可能的 JSON 字符串解析为 Python 对象。"""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    try:
        parsed = json.loads(val)
        return parsed if isinstance(parsed, (list, dict)) else []
    except Exception:
        return []


def _clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """将数值限制在 [min_val, max_val] 范围内。"""
    return max(min_val, min(max_val, value))


def _stdev(values: list[float]) -> float:
    """计算标准差。"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _parse_time(t: str) -> float:
    """将时间字符串解析为秒数。支持 HH:MM:SS 或 MM:SS。"""
    try:
        parts = t.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """合并重叠的时间区间。"""
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# ---------------------------------------------------------------------------
# 雷达图主入口
# ---------------------------------------------------------------------------

def calculate_radar_chart(result: dict[str, Any]) -> dict[str, float]:
    """将超星视频分析结果计算为六维雷达图数据。

    维度定义（基于超星多模态分析数据）：
        1. 课程导入 —— 基于 teach_summary 中导入类环节的结构化数据
        2. 思政融合 —— 基于 class_education_summary 中思政元素的时间分布
        3. 互动质量 —— 基于 teach_wh 五何互动模型的类型覆盖与认知深度
        4. 讲授质量 —— 基于 teach_db_result 声压级数据与讲授环节时长占比
        5. 教学节奏 —— 基于 teach_summary 各环节的时间分布与类型配比
        6. 课堂总结 —— 基于 teach_summary 中总结类环节的结构性数据

    返回字典结构：
    {
        "课程导入": 82.5,
        "思政融合": 76.3,
        "互动质量": 68.0,
        "讲授质量": 85.4,
        "教学节奏": 72.1,
        "课堂总结": 90.0,
    }
    """
    data = result

    # 全局时间参数
    audio_duration = data.get("audio_duration") or 0.0
    audio_duration_minutes = audio_duration / 60.0 if audio_duration else 0.0

    # 预处理：提取 teach_summary 中所有环节
    segments = _extract_segments(data)

    # 各维度独立计算
    intro = _calc_course_introduction(segments, audio_duration)
    ideology = _calc_ideological_integration(data, audio_duration)
    interaction = _calc_interaction_quality(data, audio_duration_minutes)
    teaching = _calc_teaching_quality(data, segments, audio_duration)
    rhythm = _calc_teaching_rhythm(segments, audio_duration, audio_duration_minutes)
    summary = _calc_class_summary(segments, audio_duration)

    return {
        "课程导入": round(intro["score"], 1),
        "思政融合": round(ideology["score"], 1),
        "互动质量": round(interaction["score"], 1),
        "讲授质量": round(teaching["score"], 1),
        "教学节奏": round(rhythm["score"], 1),
        "课堂总结": round(summary["score"], 1),
    }


# ---------------------------------------------------------------------------
# 数据预处理
# ---------------------------------------------------------------------------

def _extract_segments(data: dict[str, Any]) -> list[dict[str, Any]]:
    """从 teach_summary 中展平提取所有教学环节。"""
    teach_summary = _safe_json_loads(data.get("teach_summary"))
    if not isinstance(teach_summary, list):
        return []

    segments = []
    for item in teach_summary:
        if isinstance(item, dict) and isinstance(item.get("file_structure"), list):
            for seg in item["file_structure"]:
                if isinstance(seg, dict):
                    start = _parse_time(seg.get("start_time", "0:0:0"))
                    end = _parse_time(seg.get("end_time", "0:0:0"))
                    seg["_start"] = start
                    seg["_end"] = end
                    seg["_duration"] = max(0.0, end - start)
                    segments.append(seg)
    return segments


# ---------------------------------------------------------------------------
# 维度 1：课程导入
# ---------------------------------------------------------------------------

def _calc_course_introduction(segments: list[dict[str, Any]], audio_duration: float) -> dict[str, Any]:
    """计算「课程导入」维度得分。

    基于 teach_summary 中导入类环节（课程回顾、情境导入）：
    - 环节存在性：是否有导入类环节
    - 导入时长：理想区间为 60–300 秒（1–5 分钟）
    - 类型多样性：同时包含「课程回顾」与「情境导入」得满分
    """
    intro_types = {"课程回顾", "情境导入"}
    intro_segments = [s for s in segments if s.get("type") in intro_types]

    if not intro_segments:
        return {"score": 0.0, "reason": "无导入环节数据"}

    total_duration = sum(s["_duration"] for s in intro_segments)

    # 1. 存在性得分（只要有即得满分）
    existence_score = 100.0

    # 2. 时长得分：60–300 秒为满分区间
    if 60 <= total_duration <= 300:
        duration_score = 100.0
    elif total_duration < 60:
        duration_score = _clamp(total_duration / 60 * 100)
    elif total_duration <= 600:
        duration_score = _clamp(100 - (total_duration - 300) / 300 * 100)
    else:
        duration_score = 0.0

    # 3. 多样性得分：同时有两种类型为满分
    found_types = {s.get("type") for s in intro_segments}
    diversity_score = 100.0 if len(found_types & intro_types) >= 2 else 50.0

    score = existence_score * 0.3 + duration_score * 0.4 + diversity_score * 0.3
    return {
        "score": round(score, 1),
        "total_duration": round(total_duration, 1),
        "found_types": sorted(found_types),
        "existence_score": round(existence_score, 1),
        "duration_score": round(duration_score, 1),
        "diversity_score": round(diversity_score, 1),
    }


# ---------------------------------------------------------------------------
# 维度 2：思政融合
# ---------------------------------------------------------------------------

def _calc_ideological_integration(data: dict[str, Any], audio_duration: float) -> dict[str, Any]:
    """计算「思政融合」维度得分。

    基于 class_education_summary：
    - 思政元素数量：≥5 个为满分
    - 覆盖时长占比：5%–15% 为满分区间，避免喧宾夺主
    - 分布均匀度：基于变异系数（CV）评估时间分布的离散程度
    """
    ces = data.get("class_education_summary") or {}
    if not isinstance(ces, dict):
        ces = {}
    summaries = ces.get("summary", [])
    if not isinstance(summaries, list):
        summaries = []

    if not summaries:
        return {"score": 0.0, "reason": "无思政元素数据"}

    count = len(summaries)

    # 合并重叠区间后计算覆盖时长
    intervals = [
        (item.get("start", 0.0), item.get("end", 0.0))
        for item in summaries
        if isinstance(item, dict)
    ]
    merged = _merge_intervals(intervals)
    covered_duration = sum(end - start for start, end in merged)

    # 1. 数量得分
    count_score = _clamp(count / 5 * 100)

    # 2. 覆盖比例得分：5%–15% 为满分
    ratio = (covered_duration / audio_duration * 100) if audio_duration else 0.0
    if 5 <= ratio <= 15:
        ratio_score = 100.0
    elif ratio < 5:
        ratio_score = _clamp(ratio / 5 * 100)
    else:
        ratio_score = _clamp(100 - (ratio - 15) * 5)

    # 3. 分布均匀度：基于时间间隔的变异系数
    uniformity_score = 100.0
    if len(intervals) >= 2:
        starts = sorted([s for s, _ in intervals])
        gaps = [starts[i] - starts[i - 1] for i in range(1, len(starts))]
        if gaps:
            mean_gap = sum(gaps) / len(gaps)
            if mean_gap > 0:
                cv = _stdev(gaps) / mean_gap
                uniformity_score = _clamp(100 - cv * 30)

    score = count_score * 0.4 + ratio_score * 0.4 + uniformity_score * 0.2
    return {
        "score": round(score, 1),
        "count": count,
        "covered_duration": round(covered_duration, 1),
        "covered_ratio": round(ratio, 2),
        "count_score": round(count_score, 1),
        "ratio_score": round(ratio_score, 1),
        "uniformity_score": round(uniformity_score, 1),
    }


# ---------------------------------------------------------------------------
# 维度 3：互动质量
# ---------------------------------------------------------------------------

def _calc_interaction_quality(data: dict[str, Any], duration_minutes: float) -> dict[str, Any]:
    """计算「互动质量」维度得分。

    基于 teach_wh（五何互动模型）：
    - 类型覆盖度：「是何」「为何」「如何」「若何」「由何」五类全覆盖为满分
    - 互动密度：理想密度为每分钟 3–10 条
    - 认知深度：「如何」「若何」「由何」为高阶互动，占比越高认知深度越深
    """
    teach_wh = _safe_json_loads(data.get("teach_wh"))
    if not isinstance(teach_wh, list) or not teach_wh:
        return {"score": 0.0, "reason": "无五何互动数据"}

    categories = {}
    for item in teach_wh:
        cat = item.get("category", "未知")
        categories[cat] = categories.get(cat, 0) + 1

    total = len(teach_wh)
    known_cats = {"是何", "为何", "如何", "若何", "由何"}
    covered = len(known_cats & set(categories.keys()))

    # 1. 覆盖度得分
    coverage_score = covered / 5 * 100

    # 2. 密度得分：3–10 条/分钟为满分
    density_score = 0.0
    if duration_minutes > 0:
        density = total / duration_minutes
        if 3 <= density <= 10:
            density_score = 100.0
        elif density < 3:
            density_score = _clamp(density / 3 * 100)
        else:
            density_score = _clamp(100 - (density - 10) * 5)

    # 3. 认知深度得分：高阶互动（如何、若何、由何）占比
    high_order = sum(categories.get(c, 0) for c in {"如何", "若何", "由何"})
    depth_ratio = (high_order / total * 100) if total else 0.0
    depth_score = _clamp(depth_ratio * 2)  # 50% 占比即满分

    score = coverage_score * 0.3 + density_score * 0.3 + depth_score * 0.4
    return {
        "score": round(score, 1),
        "total": total,
        "categories": categories,
        "coverage_score": round(coverage_score, 1),
        "density_score": round(density_score, 1),
        "depth_score": round(depth_score, 1),
    }


# ---------------------------------------------------------------------------
# 维度 4：讲授质量
# ---------------------------------------------------------------------------

def _calc_teaching_quality(
    data: dict[str, Any],
    segments: list[dict[str, Any]],
    audio_duration: float,
) -> dict[str, Any]:
    """计算「讲授质量」维度得分。

    基于多模态数据融合：
    - 音量适宜度： teach_db_result 中平均 SPL 50–60 dB 为最佳区间
    - 音量稳定性：SPL 标准差 <3 为满分
    - 讲授时长占比：总时长中讲授环节占 40%–70% 为理想区间
    """
    db_result = data.get("teach_db_result") or {}
    db_data = db_result.get("data") if isinstance(db_result, dict) else {}
    if not isinstance(db_data, dict):
        db_data = {}

    avg_spl = db_data.get("avg_spl")
    spl_values = db_data.get("result")

    # 1. 音量适宜度
    volume_score = 0.0
    stability_score = 0.0
    if isinstance(avg_spl, (int, float)) and isinstance(spl_values, list) and spl_values:
        if 50 <= avg_spl <= 60:
            volume_score = 100.0
        elif avg_spl < 50:
            volume_score = _clamp(avg_spl / 50 * 100)
        else:
            volume_score = _clamp(100 - (avg_spl - 60) * 5)

        std = _stdev([float(v) for v in spl_values if isinstance(v, (int, float))])
        stability_score = _clamp(100 - (std / 15) * 100)

    # 2. 讲授时长占比
    lecture_segments = [s for s in segments if s.get("type") == "讲授"]
    lecture_duration = sum(s["_duration"] for s in lecture_segments)
    lecture_ratio = (lecture_duration / audio_duration * 100) if audio_duration else 0.0

    if 40 <= lecture_ratio <= 70:
        ratio_score = 100.0
    elif lecture_ratio < 40:
        ratio_score = _clamp(lecture_ratio / 40 * 100)
    else:
        ratio_score = _clamp(100 - (lecture_ratio - 70) * 3)

    score = volume_score * 0.3 + stability_score * 0.3 + ratio_score * 0.4
    return {
        "score": round(score, 1),
        "avg_spl": round(avg_spl, 2) if isinstance(avg_spl, (int, float)) else None,
        "lecture_ratio": round(lecture_ratio, 2),
        "volume_score": round(volume_score, 1),
        "stability_score": round(stability_score, 1),
        "ratio_score": round(ratio_score, 1),
    }


# ---------------------------------------------------------------------------
# 维度 5：教学节奏
# ---------------------------------------------------------------------------

def _calc_teaching_rhythm(
    segments: list[dict[str, Any]],
    audio_duration: float,
    duration_minutes: float,
) -> dict[str, Any]:
    """计算「教学节奏」维度得分。

    基于 teach_summary 中各环节的时间分布：
    - 总时长合理性：20–90 分钟为合理区间
    - 环节切换频率：理想 3–8 次/分钟，避免单调或碎片化
    - 类型多样性：覆盖 ≥5 种环节类型为满分
    - 时间配比合理性：讲授 40%–70%、互动 ≥10%、导入总结 ≥10%
    """
    if not segments or audio_duration <= 0:
        return {"score": 0.0, "reason": "无教学环节数据"}

    # 1. 时长得分
    if 20 <= duration_minutes <= 90:
        duration_score = 100.0
    elif duration_minutes < 20:
        duration_score = _clamp(duration_minutes / 20 * 100)
    else:
        duration_score = _clamp(100 - (duration_minutes - 90) * 2)

    # 2. 切换频率：3–8 次/分钟为满分
    switch_count = len(segments) - 1
    switch_freq = switch_count / duration_minutes if duration_minutes > 0 else 0.0
    if 3 <= switch_freq <= 8:
        switch_score = 100.0
    elif switch_freq < 3:
        switch_score = _clamp(switch_freq / 3 * 100)
    else:
        switch_score = _clamp(100 - (switch_freq - 8) * 5)

    # 3. 类型多样性
    found_types = {s.get("type", "") for s in segments}
    type_count = len(found_types - {""})
    diversity_score = _clamp(type_count / 5 * 100)

    # 4. 时间配比合理性
    lecture_dur = sum(s["_duration"] for s in segments if s.get("type") == "讲授")
    interaction_dur = sum(
        s["_duration"]
        for s in segments
        if s.get("type") in {"课堂问答", "学生展示/汇报"}
    )
    intro_summary_dur = sum(
        s["_duration"]
        for s in segments
        if s.get("type") in {"课程回顾", "情境导入", "课程总结", "布置作业/任务"}
    )

    lecture_ratio = lecture_dur / audio_duration * 100
    interaction_ratio = interaction_dur / audio_duration * 100
    intro_summary_ratio = intro_summary_dur / audio_duration * 100

    # 讲授 40%–70% 为满分
    if 40 <= lecture_ratio <= 70:
        lecture_part_score = 100.0
    elif lecture_ratio < 40:
        lecture_part_score = _clamp(lecture_ratio / 40 * 100)
    else:
        lecture_part_score = _clamp(100 - (lecture_ratio - 70) * 3)

    # 互动 ≥10% 为满分
    interaction_part_score = _clamp(interaction_ratio / 10 * 100) if interaction_ratio < 10 else 100.0

    # 导入总结 ≥10% 为满分
    intro_summary_part_score = _clamp(intro_summary_ratio / 10 * 100) if intro_summary_ratio < 10 else 100.0

    balance_score = (lecture_part_score + interaction_part_score + intro_summary_part_score) / 3

    score = duration_score * 0.2 + switch_score * 0.2 + diversity_score * 0.2 + balance_score * 0.4
    return {
        "score": round(score, 1),
        "duration_minutes": round(duration_minutes, 1),
        "switch_freq": round(switch_freq, 2),
        "type_count": type_count,
        "lecture_ratio": round(lecture_ratio, 1),
        "interaction_ratio": round(interaction_ratio, 1),
        "intro_summary_ratio": round(intro_summary_ratio, 1),
        "duration_score": round(duration_score, 1),
        "switch_score": round(switch_score, 1),
        "diversity_score": round(diversity_score, 1),
        "balance_score": round(balance_score, 1),
    }


# ---------------------------------------------------------------------------
# 维度 6：课堂总结
# ---------------------------------------------------------------------------

def _calc_class_summary(segments: list[dict[str, Any]], audio_duration: float) -> dict[str, Any]:
    """计算「课堂总结」维度得分。

    基于 teach_summary 中总结类环节（课程总结、布置作业/任务）：
    - 环节存在性：是否有总结类环节
    - 总结时长：理想区间为 60–300 秒（1–5 分钟）
    - 类型多样性：同时包含「课程总结」与「布置作业/任务」得满分
    - 位置合理性：总结环节发生在课堂最后 15% 时间内得满分
    """
    summary_types = {"课程总结", "布置作业/任务"}
    summary_segments = [s for s in segments if s.get("type") in summary_types]

    if not summary_segments:
        return {"score": 0.0, "reason": "无总结环节数据"}

    total_duration = sum(s["_duration"] for s in summary_segments)

    # 1. 存在性得分
    existence_score = 100.0

    # 2. 时长得分
    if 60 <= total_duration <= 300:
        duration_score = 100.0
    elif total_duration < 60:
        duration_score = _clamp(total_duration / 60 * 100)
    elif total_duration <= 600:
        duration_score = _clamp(100 - (total_duration - 300) / 300 * 100)
    else:
        duration_score = 0.0

    # 3. 多样性得分
    found_types = {s.get("type") for s in summary_segments}
    diversity_score = 100.0 if len(found_types & summary_types) >= 2 else 50.0

    # 4. 位置得分：发生在最后 15% 时间内为满分
    last_threshold = audio_duration * 0.85 if audio_duration else 0.0
    in_end = all(s["_start"] >= last_threshold for s in summary_segments)
    position_score = 100.0 if in_end else 50.0

    score = existence_score * 0.2 + duration_score * 0.3 + diversity_score * 0.2 + position_score * 0.3
    return {
        "score": round(score, 1),
        "total_duration": round(total_duration, 1),
        "found_types": sorted(found_types),
        "in_end": in_end,
        "existence_score": round(existence_score, 1),
        "duration_score": round(duration_score, 1),
        "diversity_score": round(diversity_score, 1),
        "position_score": round(position_score, 1),
    }
