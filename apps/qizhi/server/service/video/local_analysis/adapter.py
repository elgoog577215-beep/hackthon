"""把 video-analyze POC 的 report dict 适配为 report-new 消费的 v2 analysis_result。

策略：尽量把 POC 各维度数据回填成超星「中间格式」(teach_db_result / teach_summary /
teach_knowledge / teach_question / teach_wh)，复用 service.video.analysis 下既有的纯计算
提取器（与云端/超星链路完全相同的代码），从而保证产出的子结构与云端逐字段一致，
前端 VideoAnalysisReportNewView 无需任何改动即可渲染。

得分维度（radar/scores/ai_summary）直接取自 POC 的 overall（POC 已用 LLM 产出五维评分与
总评），不再走云端的二次评分，避免重复 LLM 调用。
"""
from __future__ import annotations

from typing import Any

from ..analysis.design import (
    compute_information_density,
    compute_type_distribution,
    flatten_segments,
)
from ..analysis.expression import (
    analyze_language_conciseness,
    analyze_speech_rate,
    extract_volume_analysis,
)
from ..analysis.interaction import (
    analyze_wh_distribution,
    compute_interaction_gaps,
)
from ..analysis.knowledge import extract_knowledge_tree

_RADAR_DIMS = ["教学表达", "教学设计", "知识呈现", "互动质量", "思政融合"]


def _transcript_data_from_poc(report: dict) -> dict:
    """POC 字幕 start_sec/end_sec -> 云端提取器需要的 start/end。"""
    items = []
    for t in report.get("transcript", []) or []:
        items.append({
            "start": float(t.get("start_sec", t.get("start", 0)) or 0),
            "end": float(t.get("end_sec", t.get("end", 0)) or 0),
            "text": t.get("text", "") or "",
        })
    return {"transcript": items}


def _word_cloud_from_poc(report: dict) -> list[dict]:
    """POC wordcloud.frequencies(dict) -> [{word, weight}]（取 TOP50）。"""
    freq = (report.get("wordcloud") or {}).get("frequencies") or {}
    items = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:50]
    return [{"word": w, "weight": c} for w, c in items]


def _intro_concl_from_phase(phase: dict | None, score: int) -> dict:
    """POC PhaseAnalysis(exists/start_time/end_time/content/evaluation) -> 前端期望结构。
    POC 不产出 score，用教学设计维度得分作为代理（仅展示用，不参与计算）。"""
    phase = phase or {}
    exists = bool(phase.get("exists"))
    st = phase.get("start_time", "") or ""
    et = phase.get("end_time", "") or ""
    time_range = f"{st}-{et}" if (exists and (st or et)) else ""
    return {
        "exists": exists,
        "score": score if exists else 0,
        "description": phase.get("content", "") or "",
        "evaluation": phase.get("evaluation", "") or "",
        "time_range": time_range,
        "start_time": st,
        "end_time": et,
    }


def _ideology_from_sizheng(report: dict) -> list[dict]:
    """POC sizheng[{start,end,result:{status,title,content,naturalness}}] -> 前端思政事件。
    naturalness(1-5) 线性放大到 integration_score(0-100)。"""
    events = []
    for e in report.get("sizheng", []) or []:
        r = e.get("result", {}) or {}
        nat = r.get("naturalness", r.get("融入自然度", 0)) or 0
        try:
            score = int(round(float(nat) * 20))
        except (TypeError, ValueError):
            score = 0
        events.append({
            "start": e.get("start", 0),
            "end": e.get("end", 0),
            "title": r.get("title", "") or "",
            "content": r.get("content", "") or "",
            "integration_score": max(0, min(100, score)),
            "integration_evaluation": "",
            "status": r.get("status", 0),
        })
    return events


def _scores_from_overall(overall: dict) -> dict:
    """POC overall.radar[{name,score}] + overall_score -> {维度名: 分, 综合得分: 分}。"""
    radar = overall.get("radar", []) or []
    by_name = {d.get("name"): d.get("score", 0) for d in radar}
    scores = {dim: int(round(float(by_name.get(dim, 0) or 0))) for dim in _RADAR_DIMS}
    overall_score = overall.get("overall_score")
    if overall_score is None:
        overall_score = round(sum(scores.values()) / len(scores)) if scores else 0
    scores["综合得分"] = int(round(float(overall_score)))
    return scores


def map_report_to_v2(report: dict) -> dict:
    """POC report dict -> VideoAnalysisResult(v2) dict。"""
    overall = report.get("overall", {}) or {}
    transcript_data = _transcript_data_from_poc(report)
    # 用 POC 音量(total_seconds=分桶数, total_duration=秒)回填 teach_db_result，
    # 让语速/信息密度的时间窗口与音量分桶保持一致。
    analyze_for_windows = {"teach_db_result": {"data": report.get("volume", {}) or {}}}

    # ---- 教学表达 ----
    volume_analysis = extract_volume_analysis(analyze_for_windows)
    speech_rate_analysis = analyze_speech_rate(transcript_data, analyze_for_windows)
    language_conciseness = analyze_language_conciseness(transcript_data)

    # ---- 教学设计 ----
    segments = flatten_segments({"teach_summary": report.get("segments", []) or []})
    type_distribution = compute_type_distribution(segments)
    information_density = compute_information_density(
        transcript_data, segments, analyze_for_windows
    )

    scores = _scores_from_overall(overall)
    design_score = scores.get("教学设计", 0)
    structure_extra = report.get("structure_extra", {}) or {}
    introduction_analysis = _intro_concl_from_phase(
        structure_extra.get("intro_analysis"), design_score
    )
    conclusion_analysis = _intro_concl_from_phase(
        structure_extra.get("summary_analysis"), design_score
    )

    # ---- 知识呈现 ----
    knowledge_tree = extract_knowledge_tree(
        {"teach_knowledge": [{"file_structure": report.get("knowledge", []) or []}]}
    )
    word_cloud = _word_cloud_from_poc(report)

    # ---- 互动质量 ----
    interactions = report.get("interactions", []) or []
    interaction_events = [
        {
            "text": i.get("text", "") or "",
            "type": i.get("type", "") or "",
            "segment": i.get("segment", "") or "",
            "start_time": i.get("start_time", "") or "",
            "end_time": i.get("end_time", "") or "",
        }
        for i in interactions
    ]
    cognitive_counts = (report.get("wuhe") or {}).get("cognitive_counts", {}) or {}
    type_statistics = {k: v for k, v in cognitive_counts.items() if v}
    interaction_gaps = compute_interaction_gaps(
        {"teach_question": {"questions": interactions}}, transcript_data
    )
    teach_wh = [
        {
            "category": i.get("wuhe", ""),
            "start": i.get("start_time", ""),
            "end": i.get("end_time", ""),
            "text": i.get("text", ""),
        }
        for i in interactions
        if i.get("wuhe")
    ]
    wh_distribution = analyze_wh_distribution({"teach_wh": teach_wh})

    # ---- 思政融合 ----
    ideological_events = _ideology_from_sizheng(report)

    # ---- 雷达 / 总评 ----
    radar_data = [{"dimension": k, "score": v} for k, v in scores.items()]
    ai_summary = {
        "summary": overall.get("summary", "") or "",
        "suggestions": overall.get("suggestions", []) or [],
    }

    # ---- 能力概述 & 改进建议（与文档分析对齐） ----
    capability_summary = overall.get("capability_summary", "") or ""
    improvement_suggestions = overall.get("improvement_suggestions", []) or []

    return {
        "teaching_expression": {
            "volume_analysis": volume_analysis,
            "speech_rate_analysis": speech_rate_analysis,
            "language_conciseness": language_conciseness,
        },
        "teaching_design": {
            "segments": segments,
            "type_distribution": type_distribution,
            "information_density": information_density,
            "introduction_analysis": introduction_analysis,
            "conclusion_analysis": conclusion_analysis,
        },
        "knowledge_presentation": {
            "knowledge_tree": knowledge_tree,
            "word_cloud": word_cloud,
        },
        "interaction_quality": {
            "interaction_events": interaction_events,
            "type_statistics": type_statistics,
            "interaction_gaps": interaction_gaps,
            "wh_distribution": wh_distribution,
        },
        "ideological_integration": {
            "ideological_events": ideological_events,
        },
        "scores": scores,
        "radar_data": radar_data,
        "ai_summary": ai_summary,
        "capability_summary": capability_summary,
        "improvement_suggestions": improvement_suggestions,
        # 附带 POC 元信息（含失败维度），便于排查；前端忽略未知键。
        "_local_analysis_meta": report.get("meta", {}),
    }
