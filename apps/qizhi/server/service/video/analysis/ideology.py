"""
思政融合二次处理模块。

从超星分析结果中提取并二次加工：
- 思政事件列表
- 融入自然度大模型评价
"""

import json
from typing import Any

from agents.llm import complete_chat
from common.utils.logger import get_logger

logger = get_logger(__name__)


async def analyze_ideological_events(
    transcript_data: dict,
    analyze_data: dict,
) -> list[dict]:
    """
    提取思政事件，并对每个事件进行融入自然度大模型评价。
    """
    class_education = analyze_data.get("class_education_summary", {})
    summaries = class_education.get("summary", [])

    if not summaries:
        return []

    # 收集所有事件的基本信息
    events = []
    for item in summaries:
        events.append({
            "start": item.get("start", 0),
            "end": item.get("end", 0),
            "title": item.get("result", {}).get("title", ""),
            "content": item.get("result", {}).get("content", ""),
        })

    # 逐个事件进行大模型评价
    results = []
    for event in events:
        event_text = _extract_event_text(transcript_data, event["start"], event["end"])

        try:
            evaluation = await _evaluate_integration(event, event_text)
        except Exception as e:
            logger.exception("思政融入自然度评价失败: %s", e)
            evaluation = {"score": 0, "evaluation": "评价失败"}

        results.append({
            "start": event["start"],
            "end": event["end"],
            "title": event["title"],
            "content": event["content"],
            "integration_score": evaluation.get("score", 0),
            "integration_evaluation": evaluation.get("evaluation", ""),
        })

    return results


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _extract_event_text(
    transcript_data: dict,
    start_sec: float,
    end_sec: float,
    max_chars: int = 2000,
) -> str:
    """从转写结果中截取事件时间段的原文。"""
    transcript = transcript_data.get("transcript", [])
    texts = []
    for item in transcript:
        item_start = float(item.get("start", 0))
        item_end = float(item.get("end", 0))
        if item_end >= start_sec and item_start <= end_sec:
            texts.append(item.get("text", "").strip())
    full = "\n".join(texts)
    if len(full) > max_chars:
        return full[:max_chars] + "\n..."
    return full


async def _evaluate_integration(event: dict, event_text: str) -> dict:
    """调用大模型评价思政融入自然度。"""
    system_prompt = (
        "你是一位资深思政教育专家，擅长评判课程中思政元素的融入质量。"
        "请对提供的思政片段进行专业评价，严格以 JSON 格式返回。"
    )
    user_prompt = (
        f"思政事件：{event['title']}\n"
        f"事件描述：{event['content']}\n\n"
        f"课堂原文片段：\n{event_text}\n\n"
        "请从以下维度评价该思政事件的融入自然度（满分100分），"
        "并以 JSON 格式返回：\n"
        "1. 融入自然度：思政内容是否与专业知识自然融合，不生硬\n"
        "2. 引发共鸣度：是否能有效引发学生情感共鸣和价值认同\n"
        "3. 教育实效度：是否达到润物细无声的育人效果\n\n"
        '{\n  "score": 整数(0-100),\n'
        '  "evaluation": "评价文本（200字以内）"\n}'
    )

    response = await complete_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        enable_thinking=False,
    )

    return _parse_llm_json(response)


def _parse_llm_json(text: str) -> dict:
    """解析模型返回的 JSON，兼容 markdown 代码块。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except Exception:
        return {"score": 0, "evaluation": text[:500] if text else "解析失败"}
