"""
评分算法与雷达图数据生成模块。

基于各维度分析结果，计算 5 维得分、综合得分及 AI 总评。
"""

from agents.llm import complete_chat
from common.utils.logger import get_logger

logger = get_logger(__name__)

# 教学设计理想环节类型
_IDEAL_DESIGN_TYPES = {
    "讲授", "案例拓展/题目讲解", "课堂问答", "情境导入", "示范演示",
}

# 互动质量理想类型（teach_question 6 种 + 五何 5 种）
_IDEAL_INTERACTION_TYPES = {
    "创新型", "评价型", "分析型", "应用型", "理解型", "记忆型",
    "是何", "为何", "如何", "若何", "由何",
}


def calculate_expression_score(speech_rate: dict, conciseness: dict) -> int:
    """
    教学表达得分。

    S_speed = 1 - (偏离正常区间累计时长 / 总时长)
    S_conciseness = 1 - (冗余填充词字数 / 总字数)
    S_expression = 0.5 * S_speed + 0.5 * S_conciseness
    """
    total_duration = speech_rate.get("total_duration", 0.0)
    result = speech_rate.get("result", [])

    # 语速偏离正常区间（120~260 CPM）的累计时长
    window_duration = total_duration / len(result) if result else 0
    deviate_duration = 0.0
    for cpm in result:
        if cpm < 120 or cpm > 260:
            deviate_duration += window_duration

    s_speed = 1.0 - (deviate_duration / total_duration) if total_duration > 0 else 0.0
    s_speed = max(0.0, min(1.0, s_speed))

    # 语言精炼度
    filler_count = conciseness.get("filler_word_count", 0)
    total_word_count = conciseness.get("total_word_count", 1)
    s_conciseness = 1.0 - (filler_count / total_word_count) if total_word_count > 0 else 0.0
    s_conciseness = max(0.0, min(1.0, s_conciseness))

    score = (0.5 * s_speed + 0.5 * s_conciseness) * 100
    return round(score)


def calculate_design_score(
    type_distribution: list[dict],
    intro_analysis: dict,
    conclusion_analysis: dict,
) -> int:
    """
    教学设计得分。

    环节丰富度 = 实际覆盖类型数 / 理想类型数(5)
    S_design = 0.3 * 环节丰富度 + 0.35 * 导入质量 + 0.35 * 总结质量
    """
    actual_types = {d.get("type", "") for d in type_distribution}
    coverage = len(actual_types & _IDEAL_DESIGN_TYPES) / len(_IDEAL_DESIGN_TYPES)

    intro_score = (intro_analysis.get("score", 0) or 0) / 100.0
    conclusion_score = (conclusion_analysis.get("score", 0) or 0) / 100.0

    score = 0.3 * coverage + 0.35 * intro_score + 0.35 * conclusion_score
    return round(score * 100)


async def evaluate_knowledge_presentation(
    knowledge_tree: list[dict],
    transcript_data: dict,
) -> int:
    """
    知识呈现得分（需大模型评判）。

    返回 0-100 的整数得分。
    """
    if not knowledge_tree:
        return 0

    # 压缩知识树为简要描述
    tree_summary = _summarize_knowledge_tree(knowledge_tree)

    system_prompt = (
        "你是一位资深教育学专家，擅长评判课堂教学中知识呈现的质量。"
        "请根据提供的知识树结构，从两个维度进行评分（每项满分50分），"
        "并以 JSON 格式返回。"
    )
    user_prompt = (
        "【知识层级树结构】\n"
        f"{tree_summary}\n\n"
        "请从以下维度评分：\n"
        "1. 知识结构合理性（满分50）：层级是否分明、衔接是否紧密、逻辑递进是否合理\n"
        "2. 要素覆盖完整性（满分50）：定义、要点、案例等核心要素是否覆盖全面\n\n"
        '{\n  "structure_score": 整数(0-50),\n'
        '  "coverage_score": 整数(0-50)\n}'
    )

    try:
        response = await complete_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            enable_thinking=False,
        )
        data = _parse_json(response)
        total = data.get("structure_score", 0) + data.get("coverage_score", 0)
        return min(100, max(0, total))
    except Exception as e:
        logger.exception("知识呈现大模型评判失败: %s", e)
        return 0


def calculate_interaction_score(
    interaction_data: dict,
    gaps: list[dict],
    total_duration: float,
) -> int:
    """
    互动质量得分。

    互动丰富度 = 实际覆盖类型数 / 理想类型数(11)
    互动间隔合理性 = 1 - (超过12分钟累计时长 / 总时长)
    S_interaction = 0.5 * 丰富度 + 0.5 * 间隔合理性
    """
    # 实际覆盖的互动类型
    actual_types: set[str] = set()
    stats = interaction_data.get("type_statistics", {})
    actual_types.update(k for k, v in stats.items() if v > 0)

    # 五何类型
    wh = interaction_data.get("wh_distribution", {})
    actual_types.update(k for k, v in wh.items() if v.get("count", 0) > 0)

    richness = len(actual_types & _IDEAL_INTERACTION_TYPES) / len(_IDEAL_INTERACTION_TYPES)

    # 超过12分钟的累计时长
    gap_duration = sum(g.get("duration_seconds", 0) for g in gaps)
    gap_ratio = gap_duration / total_duration if total_duration > 0 else 0.0
    gap_reasonableness = max(0.0, 1.0 - gap_ratio)

    score = 0.5 * richness + 0.5 * gap_reasonableness
    return round(score * 100)


def calculate_ideology_score(events: list[dict]) -> int:
    """
    思政融合得分。

    思政存在性 = 1 if 有事件 else 0
    融入自然度 = 平均 integration_score / 100
    S_ideology = 存在性 * 融入自然度
    """
    if not events:
        return 0

    existence = 1.0
    avg_naturalness = sum(
        e.get("integration_score", 0) for e in events
    ) / len(events) / 100.0

    score = existence * avg_naturalness
    return round(score * 100)


async def generate_ai_summary(scores: dict[str, int], all_data: dict) -> dict:
    """
    基于五维得分及各维度分析结果，调用大模型生成 AI 总评摘要与建议。

    返回 {"summary": str, "suggestions": list[str]}
    """
    system_prompt = (
        "你是一位资深教学督导专家，擅长对课堂教学进行综合评价并提出改进建议。"
        "请基于提供的五维得分和简要分析数据，生成：\n"
        "1. 一段 300 字左右的总评摘要（summary）\n"
        "2. 3-5 条具体、可落地的改进建议（suggestions，每条建议是一个字符串）\n\n"
        "必须以 JSON 格式返回，不要输出 Markdown 代码块标记或其他解释性内容：\n"
        '{\n  "summary": "总评摘要...",\n  "suggestions": ["建议1...", "建议2...", "建议3..."]\n}'
    )

    summary_lines = [
        f"【五维得分】",
        f"教学表达：{scores.get('教学表达', 0)} 分",
        f"教学设计：{scores.get('教学设计', 0)} 分",
        f"知识呈现：{scores.get('知识呈现', 0)} 分",
        f"互动质量：{scores.get('互动质量', 0)} 分",
        f"思政融合：{scores.get('思政融合', 0)} 分",
        f"综合得分：{scores.get('综合得分', 0)} 分",
        "",
        "【关键数据摘要】",
    ]

    # 加入各维度关键摘要（控制长度）
    te = all_data.get("teaching_expression", {})
    conciseness = te.get("language_conciseness", {})
    summary_lines.append(
        f"- 语言精炼度：冗余填充词占比 {conciseness.get('filler_word_ratio', 0):.2%}"
    )

    td = all_data.get("teaching_design", {})
    type_dist = td.get("type_distribution", [])
    summary_lines.append(f"- 课堂环节：{len(type_dist)} 种类型")

    iq = all_data.get("interaction_quality", {})
    gaps = iq.get("interaction_gaps", [])
    summary_lines.append(f"- 纯讲授段：{len(gaps)} 段")

    ii = all_data.get("ideological_integration", {})
    events = ii.get("ideological_events", [])
    summary_lines.append(f"- 思政事件：{len(events)} 个")

    user_prompt = "\n".join(summary_lines)

    try:
        response = await complete_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            enable_thinking=False,
        )
        data = _parse_json(response.strip())
        return {
            "summary": data.get("summary", ""),
            "suggestions": data.get("suggestions", []),
        }
    except Exception as e:
        logger.exception("AI 总评生成失败: %s", e)
        return {
            "summary": "AI 总评生成失败，请稍后重试。",
            "suggestions": [],
        }


def build_radar_data(scores: dict[str, int]) -> list[dict]:
    """
    构建雷达图数据，前端可直接使用。
    """
    return [
        {"dimension": k, "score": v}
        for k, v in scores.items()
    ]


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _summarize_knowledge_tree(tree: list[dict], depth: int = 0) -> str:
    """将知识树压缩为文本摘要（控制 token 长度）。"""
    lines = []
    indent = "  " * depth
    for node in tree:
        title = node.get("title", "")
        start = node.get("start_time", "")
        end = node.get("end_time", "")
        lines.append(f"{indent}- {title} ({start}-{end})")
        children = node.get("children", [])
        if children:
            lines.append(_summarize_knowledge_tree(children, depth + 1))
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    """简单 JSON 解析，兼容 markdown 代码块。"""
    import json

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
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
