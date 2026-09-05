"""
视频分析结果二次处理总入口。

用法：
    from service.video.analysis import process_chaoxing_analysis
    result = await process_chaoxing_analysis(transcript_data, analyze_data)
"""

from common.utils.logger import get_logger
from .expression import (
    extract_volume_analysis,
    analyze_speech_rate,
    analyze_language_conciseness,
)
from .design import (
    flatten_segments,
    compute_type_distribution,
    compute_information_density,
)
from .knowledge import extract_knowledge_tree, generate_word_cloud
from .interaction import (
    extract_interaction_events,
    compute_interaction_gaps,
    analyze_wh_distribution,
)
from .ideology import analyze_ideological_events
from .scoring import (
    calculate_expression_score,
    calculate_design_score,
    evaluate_knowledge_presentation,
    calculate_interaction_score,
    calculate_ideology_score,
    generate_ai_summary,
    build_radar_data,
)
from agents.video_analyzer import analyze_introduction, analyze_conclusion

logger = get_logger(__name__)


async def process_chaoxing_analysis(
    transcript_data: dict,
    analyze_data: dict,
) -> dict:
    """
    接收超星转写和分析结果，进行二次处理并返回聚合 JSON。

    Args:
        transcript_data: 超星转写接口原始返回（含 result.transcript）
        analyze_data: 超星分析接口原始返回（已 normalize）

    Returns:
        {
            "teaching_expression": {...},
            "teaching_design": {...},
            "knowledge_presentation": {...},
            "interaction_quality": {...},
            "ideological_integration": {...},
            "scores": {...},
            "radar_data": [...],
            "ai_summary": str,
        }
    """
    # ---- 教学表达 ----
    try:
        volume = extract_volume_analysis(analyze_data)
        speech_rate = analyze_speech_rate(transcript_data, analyze_data)
        conciseness = analyze_language_conciseness(transcript_data)
    except Exception as e:
        logger.exception("教学表达分析失败: %s", e)
        volume = {}
        speech_rate = {}
        conciseness = {}

    # ---- 教学设计 ----
    try:
        segments = flatten_segments(analyze_data)
        type_distribution = compute_type_distribution(segments)
        density = compute_information_density(transcript_data, segments, analyze_data)
    except Exception as e:
        logger.exception("教学设计基础分析失败: %s", e)
        segments = []
        type_distribution = []
        density = {}

    # ---- 导入/总结大模型评判 ----
    intro_analysis = {}
    conclusion_analysis = {}
    try:
        if segments:
            intro_analysis = await analyze_introduction(segments, transcript_data)
            conclusion_analysis = await analyze_conclusion(segments, transcript_data)
    except Exception as e:
        logger.exception("导入/总结大模型评判失败: %s", e)

    # ---- 知识呈现 ----
    try:
        knowledge_tree = extract_knowledge_tree(analyze_data)
        word_cloud = generate_word_cloud(transcript_data, analyze_data)
    except Exception as e:
        logger.exception("知识呈现分析失败: %s", e)
        knowledge_tree = []
        word_cloud = []

    # ---- 互动质量 ----
    try:
        interaction = extract_interaction_events(analyze_data)
        gaps = compute_interaction_gaps(analyze_data, transcript_data)
        wh = analyze_wh_distribution(analyze_data)
    except Exception as e:
        logger.exception("互动质量分析失败: %s", e)
        interaction = {"interaction_events": [], "type_statistics": {}}
        gaps = []
        wh = {}

    # ---- 思政融合 ----
    ideological_events = []
    try:
        ideological_events = await analyze_ideological_events(transcript_data, analyze_data)
    except Exception as e:
        logger.exception("思政融合分析失败: %s", e)

    # ---- 评分 ----
    total_duration = speech_rate.get("total_duration", 0.0)

    s_expression = calculate_expression_score(speech_rate, conciseness)
    s_design = calculate_design_score(type_distribution, intro_analysis, conclusion_analysis)
    s_knowledge = await evaluate_knowledge_presentation(knowledge_tree, transcript_data)
    s_interaction = calculate_interaction_score(
        {"type_statistics": interaction.get("type_statistics", {}), "wh_distribution": wh},
        gaps,
        total_duration,
    )
    s_ideology = calculate_ideology_score(ideological_events)

    scores = {
        "expression": s_expression,
        "design": s_design,
        "knowledge": s_knowledge,
        "interaction": s_interaction,
        "ideology": s_ideology,
        "overall": round((s_expression + s_design + s_knowledge + s_interaction + s_ideology) / 5),
    }

    radar_data = build_radar_data(scores)

    # ---- AI 总评 ----
    all_data = {
        "teaching_expression": {
            "volume_analysis": volume,
            "speech_rate_analysis": speech_rate,
            "language_conciseness": conciseness,
        },
        "teaching_design": {
            "segments": segments,
            "type_distribution": type_distribution,
            "information_density": density,
            "introduction_analysis": intro_analysis,
            "conclusion_analysis": conclusion_analysis,
        },
        "knowledge_presentation": {
            "knowledge_tree": knowledge_tree,
            "word_cloud": word_cloud,
        },
        "interaction_quality": {
            "interaction_events": interaction.get("interaction_events", []),
            "type_statistics": interaction.get("type_statistics", {}),
            "interaction_gaps": gaps,
            "wh_distribution": wh,
        },
        "ideological_integration": {
            "ideological_events": ideological_events,
        },
    }

    ai_summary = await generate_ai_summary(scores, all_data)

    return {
        **all_data,
        "scores": scores,
        "radar_data": radar_data,
        "ai_summary": ai_summary,
    }
