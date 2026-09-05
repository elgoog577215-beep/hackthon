"""
视频分析 Agent 工具模块。
"""


async def fetch_transcript_ranges(
    transcript_data: dict,
    ranges: list[dict],
) -> str:
    """
    根据时间段列表批量提取转录文本原文。

    Args:
        transcript_data: 超星转写接口原始返回（含 result.transcript）
        ranges: [{"start": float, "end": float}, ...]

    Returns:
        拼接后的原文文本，每个时间段用分隔线区分
    """
    transcript = transcript_data.get("result", {}).get("transcript", [])
    results: list[str] = []

    for r in ranges:
        start = float(r.get("start", 0))
        end = float(r.get("end", 0))
        texts: list[str] = []
        for item in transcript:
            item_start = float(item.get("start", 0))
            item_end = float(item.get("end", 0))
            if item_end >= start and item_start <= end:
                texts.append(item.get("text", "").strip())
        results.append(f"[{start:.0f}s-{end:.0f}s]\n" + "\n".join(texts))

    return "\n\n---\n\n".join(results)
