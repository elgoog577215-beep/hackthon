"""
视频分析并行调度器。

将五个维度的分析任务按依赖关系编排为并行波次 + 串行收尾。
"""

import asyncio

from agents.video_analyzer import analyze_introduction, analyze_conclusion
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

logger = get_logger(__name__)


async def analyze_video_parallel(transcript_data: dict, analyze_data: dict) -> dict:
    """
    并行调度视频五维度分析。

    并行波次 1（7 个任务同时跑）：
    - 教学表达（纯计算）
    - 教学设计基础（纯计算）
    - 知识呈现基础（纯计算）
    - 互动质量（纯计算）
    - 导入分析（LLM）
    - 总结分析（LLM）
    - 思政融合评判（LLM）

    串行波次 2（依赖波次 1）：
    - 知识呈现评分（LLM，依赖知识树）
    - 各维度评分（纯计算）
    - AI 总评（LLM，依赖所有结果）
    """
    # 先同步计算 segments（导入/总结需要）
    segments = flatten_segments(analyze_data)

    # ---- 第一波：最大并行 ----
    expression_coro = _run_expression(transcript_data, analyze_data)
    design_base_coro = _run_design_base(transcript_data, analyze_data)
    knowledge_base_coro = _run_knowledge_base(transcript_data, analyze_data)
    interaction_coro = _run_interaction(analyze_data, transcript_data)
    intro_coro = _run_intro(segments, transcript_data)
    conclusion_coro = _run_conclusion(segments, transcript_data)
    ideology_coro = _run_ideology(transcript_data, analyze_data)

    (
        expression_result,
        design_base_result,
        knowledge_base_result,
        interaction_result,
    ) = await asyncio.gather(
        expression_coro,
        design_base_coro,
        knowledge_base_coro,
        interaction_coro,
        return_exceptions=True,
    )

    intro_result, conclusion_result, ideology_result = await asyncio.gather(
        intro_coro,
        conclusion_coro,
        ideology_coro,
        return_exceptions=True,
    )

    # ---- 第二波：5 个维度评分并行 ----
    expression_data = _unwrap(expression_result, {})
    design_data = _unwrap(design_base_result, {})
    interaction_data = _unwrap(interaction_result, {})
    intro_analysis = _unwrap(intro_result, {})
    conclusion_analysis = _unwrap(conclusion_result, {})
    ideology_events = _unwrap(ideology_result, [])

    score_tasks = [
        asyncio.create_task(
            _score_expression(expression_data)
        ),
        asyncio.create_task(
            _score_design(design_data, intro_analysis, conclusion_analysis)
        ),
        asyncio.create_task(
            _score_knowledge(knowledge_base_result, transcript_data)
        ),
        asyncio.create_task(
            _score_interaction(interaction_data, expression_data)
        ),
        asyncio.create_task(
            _score_ideology(ideology_events)
        ),
    ]
    score_results = await asyncio.gather(*score_tasks, return_exceptions=True)

    s_expression = _unwrap_score(score_results[0], "教学表达评分")
    s_design = _unwrap_score(score_results[1], "教学设计评分")
    s_knowledge = _unwrap_score(score_results[2], "知识呈现评分")
    s_interaction = _unwrap_score(score_results[3], "互动质量评分")
    s_ideology = _unwrap_score(score_results[4], "思政融合评分")

    scores = {
        "教学表达": s_expression,
        "教学设计": s_design,
        "知识呈现": s_knowledge,
        "互动质量": s_interaction,
        "思政融合": s_ideology,
    }
    scores["综合得分"] = round(sum(scores.values()) / len(scores))
    radar_data = build_radar_data(scores)

    # ---- 第三波：AI 总评（LLM）----
    all_data = {
        "teaching_expression": {
            "volume_analysis": expression_data.get("volume", {}),
            "speech_rate_analysis": expression_data.get("speech_rate", {}),
            "language_conciseness": expression_data.get("conciseness", {}),
        },
        "teaching_design": {
            "segments": design_data.get("segments", []),
            "type_distribution": design_data.get("type_distribution", []),
            "information_density": design_data.get("density", {}),
            "introduction_analysis": intro_analysis,
            "conclusion_analysis": conclusion_analysis,
        },
        "knowledge_presentation": {
            "knowledge_tree": _unwrap(knowledge_base_result, {}).get(
                "knowledge_tree", []
            ),
            "word_cloud": _unwrap(knowledge_base_result, {}).get("word_cloud", []),
        },
        "interaction_quality": {
            "interaction_events": interaction_data.get("events", []),
            "type_statistics": interaction_data.get("type_statistics", {}),
            "interaction_gaps": interaction_data.get("gaps", []),
            "wh_distribution": interaction_data.get("wh", {}),
        },
        "ideological_integration": {
            "ideological_events": ideology_events,
        },
    }

    ai_summary = await generate_ai_summary(scores, all_data)

    return {
        **all_data,
        "radar_data": radar_data,
        "ai_summary": ai_summary,
    }


# ---------------------------------------------------------------------------
# 第一波并行子任务
# ---------------------------------------------------------------------------


async def _run_expression(transcript_data: dict, analyze_data: dict) -> dict:
    """教学表达分析（纯计算）"""
    volume = extract_volume_analysis(analyze_data)
    speech_rate = analyze_speech_rate(transcript_data, analyze_data)
    conciseness = analyze_language_conciseness(transcript_data)
    return {"volume": volume, "speech_rate": speech_rate, "conciseness": conciseness}


async def _run_design_base(transcript_data: dict, analyze_data: dict) -> dict:
    """教学设计基础分析（纯计算）"""
    segments = flatten_segments(analyze_data)
    type_distribution = compute_type_distribution(segments)
    density = compute_information_density(transcript_data, segments, analyze_data)
    return {
        "segments": segments,
        "type_distribution": type_distribution,
        "density": density,
    }


async def _run_knowledge_base(transcript_data: dict, analyze_data: dict) -> dict:
    """知识呈现基础分析（纯计算）"""
    knowledge_tree = extract_knowledge_tree(analyze_data)
    word_cloud = generate_word_cloud(transcript_data, analyze_data)
    return {"knowledge_tree": knowledge_tree, "word_cloud": word_cloud}


async def _run_interaction(analyze_data: dict, transcript_data: dict) -> dict:
    """互动质量分析（纯计算）"""
    events = extract_interaction_events(analyze_data)
    gaps = compute_interaction_gaps(analyze_data, transcript_data)
    wh = analyze_wh_distribution(analyze_data)
    return {
        "events": events.get("interaction_events", []),
        "type_statistics": events.get("type_statistics", {}),
        "gaps": gaps,
        "wh": wh,
    }


async def _run_intro(segments: list, transcript_data: dict) -> dict:
    """导入分析（LLM）"""
    if not segments:
        return {}
    return await analyze_introduction(segments, transcript_data)


async def _run_conclusion(segments: list, transcript_data: dict) -> dict:
    """总结分析（LLM）"""
    if not segments:
        return {}
    return await analyze_conclusion(segments, transcript_data)


async def _run_ideology(transcript_data: dict, analyze_data: dict) -> list:
    """思政融合评判（LLM）"""
    return await analyze_ideological_events(transcript_data, analyze_data)


# ---------------------------------------------------------------------------
# 第二波并行评分子任务
# ---------------------------------------------------------------------------


async def _score_expression(expression_data: dict) -> int:
    """教学表达评分（纯计算）"""
    return calculate_expression_score(
        expression_data.get("speech_rate", {}),
        expression_data.get("conciseness", {}),
    )


async def _score_design(
    design_data: dict, intro: dict, conclusion: dict
) -> int:
    """教学设计评分（纯计算）"""
    return calculate_design_score(
        design_data.get("type_distribution", []),
        intro,
        conclusion,
    )


async def _score_knowledge(
    knowledge_base_result, transcript_data: dict
) -> int:
    """知识呈现评分（LLM）"""
    kt = _unwrap(knowledge_base_result, {}).get("knowledge_tree", [])
    if not kt:
        return 0
    return await evaluate_knowledge_presentation(kt, transcript_data)


async def _score_interaction(
    interaction_data: dict, expression_data: dict
) -> int:
    """互动质量评分（纯计算）"""
    total_duration = expression_data.get("speech_rate", {}).get(
        "total_duration", 0.0
    )
    return calculate_interaction_score(
        {
            "type_statistics": interaction_data.get("type_statistics", {}),
            "wh_distribution": interaction_data.get("wh", {}),
        },
        interaction_data.get("gaps", []),
        total_duration,
    )


async def _score_ideology(ideology_events: list) -> int:
    """思政融合评分（纯计算）"""
    return calculate_ideology_score(ideology_events)


# ---------------------------------------------------------------------------
# 私有辅助
# ---------------------------------------------------------------------------


def _unwrap(result, default):
    """解包 gather 结果，异常时返回默认值。"""
    if isinstance(result, Exception):
        return default
    return result


def _unwrap_score(result, label: str) -> int:
    """解包评分任务结果，异常时返回 0 并记录。"""
    if isinstance(result, Exception):
        logger.error("%s 失败，使用 0 分", label)
        return 0
    return result
