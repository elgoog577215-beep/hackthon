"""
个体化生长数据模型（Phase 2：证据判定 + 变更生成服务）
==========================================

对应 docs/requirements/灵知AI课程智能体_开发规格文档.md：
    - §4 "学习证据 MUST 驱动个体化课程演化" Requirement
      （"学生连续要求更详细解释" / "证据门槛判定" Scenario）
    - §4 "课程生成 MUST 具备结构校验与生成后质检" Requirement
      （"生成结果解析失败" / "生成记录可追溯" Scenario）

职责：
    evaluate_evidence_for_node()  证据 -> AdaptationHypothesis 判定（纯函数，无 LLM 调用）
    generate_change_set()         AdaptationHypothesis -> CourseChangeSet（调用 LLM，带受控重试与兜底）

复用既有基础设施：
    - adaptive_models.py 的 Pydantic 模型（不重新定义）
    - ai_base.AIBase 的 LLM 调用层（_call_llm / _extract_json），与 ai_quiz_service.py
      _generate_quiz_with_retry 的"解析失败 -> 把错误回传模型 -> 受控重试"模式保持一致
    - storage.py 的 load_evidence_items / load_change_sets（调用方负责持久化，本文件是纯服务层）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from adaptive_models import (
    AdaptationHypothesis,
    ChangeItem,
    CourseChangeSet,
    EvidenceItem,
)
from ai_base import AIBase

logger = logging.getLogger(__name__)


# =============================================================================
# 证据门槛判定：evaluate_evidence_for_node
# =============================================================================
#
# 规格文档 §4 "证据门槛判定" Scenario 的核心约束：
#   - 单条极强证据（如"这段完全看不懂"）MAY 立即触发，不要求"多次出现"
#   - 多条弱证据 MUST 结合强度、一致性、覆盖范围、时效性、可逆性和误判成本综合判断，
#     不得仅以固定次数作为唯一触发条件
#
# 实现策略：不做"计数 >= N 就触发"的机械判断，而是把 count 作为综合信号之一，
# 与 strength（强度均值/峰值）、type_diversity（证据类型多样性，体现"一致性"侧面：
# 同类型证据反复出现比杂乱证据更能说明问题）、recency（时效性）组合成一个
# 0-1 的综合分数，超过阈值才触发。

# 单条证据强度超过该阈值时，视为"极强单一证据"，可直接触发（不要求达到综合分数门槛）。
SINGLE_EVIDENCE_TRIGGER_THRESHOLD = 0.85

# 综合分数触发门槛（多条弱证据场景）。
COMBINED_SIGNAL_TRIGGER_THRESHOLD = 0.6

# 证据的"时效性"窗口：超过该天数的证据，权重按线性衰减到 0。
RECENCY_WINDOW_DAYS = 14

# 单条弱证据类型（本身可逆性高、误判成本低，需要更多佐证才能触发）。
_WEAK_EVIDENCE_TYPES = {"skip_behavior"}

# 高置信度证据类型（学生显式表达出的强烈信号，误判成本相对低——即便误判，
# 顶多是补充了一段学生已经理解的内容，可逆性高）。
_HIGH_CONFIDENCE_EVIDENCE_TYPES = {"explicit_feedback", "reject_reason"}


def _recency_weight(created_at: datetime, now: Optional[datetime] = None) -> float:
    """计算证据的时效性权重（0-1），越新权重越高，超出窗口衰减为 0。"""
    now = now or datetime.now()
    age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    if age_days >= RECENCY_WINDOW_DAYS:
        return 0.0
    return max(0.0, 1.0 - age_days / RECENCY_WINDOW_DAYS)


def _evidence_created_at(item: EvidenceItem) -> datetime:
    dt = item.created_at
    # created_at 可能是带时区/不带时区的 datetime，统一去掉 tzinfo 便于比较。
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def evaluate_evidence_for_node(
    evidence_items: List[EvidenceItem],
    node_id: str,
    course_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[AdaptationHypothesis]:
    """基于某节点近期的 EvidenceItem，判断是否应生成 AdaptationHypothesis。

    这是一个纯函数：不读写存储、不调用 LLM，只做判定逻辑，便于单元测试。
    调用方（如 API 路由/后台任务）负责先用 storage.load_evidence_items 读取
    该课程的所有证据，过滤出 node_id 匹配的部分，再传入本函数。

    判定逻辑（对应规格文档"证据门槛判定" Scenario）：
        1. 若存在单条 strength >= SINGLE_EVIDENCE_TRIGGER_THRESHOLD 的证据，
           直接触发（不要求多次出现）。
        2. 否则计算多条证据的综合信号分数，综合以下维度：
             - count_signal：证据数量（对数增长，避免"次数越多线性无限加分"）
             - strength_signal：证据强度的加权均值（弱证据类型打折）
             - diversity_signal：证据类型多样性（同类反复出现体现一致性，
               但不同类型证据互相印证同一节点问题时，覆盖范围更广，也应加分；
               这里用"类型数 / 总数"的倒数关系近似覆盖范围与一致性的平衡）
             - recency_signal：证据的时效性加权
           综合分数 >= COMBINED_SIGNAL_TRIGGER_THRESHOLD 时触发。
        3. 均不满足时返回 None（不生成假设，不触发变更）。

    Args:
        evidence_items: 该节点相关的 EvidenceItem 列表（调用方已按 node_id 过滤）。
        node_id: 目标节点 id。
        course_id: 课程 id（写入生成的 AdaptationHypothesis）。
        now: 供测试注入的"当前时间"，默认使用 datetime.now()。

    Returns:
        AdaptationHypothesis，或 None（未达到触发门槛）。
    """
    now = now or datetime.now()
    relevant = [item for item in evidence_items if item.node_id == node_id]
    if not relevant:
        return None

    # --- 规则 1：单条极强证据直接触发 ---
    strongest = max(relevant, key=lambda it: it.strength)
    if strongest.strength >= SINGLE_EVIDENCE_TRIGGER_THRESHOLD or (
        strongest.evidence_type in _HIGH_CONFIDENCE_EVIDENCE_TYPES
        and strongest.strength >= 0.7
    ):
        return AdaptationHypothesis(
            node_id=node_id,
            course_id=course_id,
            hypothesis=(
                f"节点 {node_id} 存在一条高强度证据"
                f"（类型={strongest.evidence_type}, 强度={strongest.strength:.2f}），"
                "判断当前内容对该学生存在明显理解障碍，无需等待多次出现即可触发适配。"
            ),
            supporting_evidence_ids=[strongest.id],
            confidence=min(1.0, strongest.strength + 0.1),
        )

    # --- 规则 2：多条弱证据的综合信号判断 ---
    import math

    count = len(relevant)
    # 数量信号：对数增长，count=1 -> 0, count=2 -> ~0.3, count=5 -> ~0.7（封顶 1.0）
    count_signal = min(1.0, math.log2(count + 1) / 3.0)

    def _effective_strength(item: EvidenceItem) -> float:
        s = item.strength
        if item.evidence_type in _WEAK_EVIDENCE_TYPES:
            s *= 0.6  # 弱证据类型打折：可逆性高、误判成本低，需要更强佐证
        return s

    strength_values = [_effective_strength(it) for it in relevant]
    strength_signal = sum(strength_values) / len(strength_values)

    distinct_types = {it.evidence_type for it in relevant}
    # 多样性/覆盖范围信号：多种证据类型互相印证同一节点问题，比单一类型反复出现更可信；
    # 但同类型反复出现（一致性）也是有效信号，因此两者取加权平均而非互斥。
    diversity_ratio = len(distinct_types) / count
    consistency_ratio = 1.0 - diversity_ratio if count > 1 else 0.0
    coverage_signal = 0.5 * min(1.0, len(distinct_types) / 3.0) + 0.5 * consistency_ratio

    recency_values = [_recency_weight(_evidence_created_at(it), now) for it in relevant]
    recency_signal = sum(recency_values) / len(recency_values)

    combined_score = (
        0.3 * count_signal
        + 0.35 * strength_signal
        + 0.15 * coverage_signal
        + 0.2 * recency_signal
    )

    logger.debug(
        "evaluate_evidence_for_node(node_id=%s): count=%d count_signal=%.2f "
        "strength_signal=%.2f coverage_signal=%.2f recency_signal=%.2f combined=%.2f",
        node_id, count, count_signal, strength_signal, coverage_signal,
        recency_signal, combined_score,
    )

    if combined_score < COMBINED_SIGNAL_TRIGGER_THRESHOLD:
        return None

    type_summary = "、".join(sorted(distinct_types))
    return AdaptationHypothesis(
        node_id=node_id,
        course_id=course_id,
        hypothesis=(
            f"节点 {node_id} 在近期积累了 {count} 条证据（类型：{type_summary}），"
            f"综合强度/覆盖范围/时效性评分为 {combined_score:.2f}，"
            "判断当前推导颗粒度或讲解深度可能不足以支撑该学生的理解。"
        ),
        supporting_evidence_ids=[it.id for it in relevant],
        confidence=min(1.0, combined_score),
    )


# =============================================================================
# CourseChangeSet 生成：generate_change_set
# =============================================================================

_CHANGE_SET_SYSTEM_PROMPT = (
    "你是课程内容适配助手，负责基于学生的学习证据判断，为课程节点生成结构化的"
    "变更建议（CourseChangeSet）。你的输出只能是变更建议，不得直接声称已经修改课程；"
    "变更内容必须紧扣给定的假设与证据，不得编造与证据无关的修改。"
)

_CHANGE_SET_PROMPT_TEMPLATE = """课程 id: {course_id}
目标节点 id: {node_id}
当前节点内容（可能为空）:
---
{node_content}
---

AI 适配假设: {hypothesis}
假设置信度: {confidence:.2f}
补充说明: {extra_instruction}

请基于以上假设生成一个 JSON 对象，描述对该节点及其相关节点的变更建议。
严格按以下 JSON Schema 输出，不要输出任何解释文字，不要用 markdown 代码块包装：

{{
  "scope": "block" | "section" | "sections" | "chapters" | "book",
  "scope_node_ids": ["受影响的节点 id 列表，至少包含 {node_id}"],
  "change_items": [
    {{
      "target_node_id": "节点 id",
      "operation": "add" | "modify" | "replace" | "delete" | "move" | "difficulty_adjust",
      "before": "变更前内容摘要，若是新增可为 null",
      "after": "变更后内容摘要或新增内容",
      "reason": "该条变更的具体理由，需要引用假设中的判断"
    }}
  ]
}}

要求：
1. change_items 至少包含 1 条，且必须包含对 {node_id} 本身的补充说明；
2. 若假设涉及"预防性补充"（如后续章节可能受影响），可以追加对其他节点的 change_item；
3. after 字段不得为空字符串（新增/修改类操作必须给出具体内容摘要）。
"""

_MAX_GENERATION_ATTEMPTS = 2


class _ChangeSetGenerator(AIBase):
    """内部辅助类：只用于复用 AIBase 的 _call_llm / _extract_json，不对外暴露。"""
    pass


_generator = _ChangeSetGenerator()


def _prompt_template_id() -> str:
    return "adaptation_service.change_set.v1"


async def generate_change_set(
    hypothesis: AdaptationHypothesis,
    node_content: str = "",
    extra_instruction: Optional[str] = None,
    use_fast_model: bool = False,
) -> Optional[CourseChangeSet]:
    """基于 AdaptationHypothesis 调用 LLM 生成 CourseChangeSet。

    对应规格文档"生成结果解析失败" Scenario：
        - 模型输出未通过 Schema 校验时，MUST 把校验错误回传模型进行受控重试；
        - 重试仍失败时 MUST 触发兜底：单个 change_item 校验失败时该条被跳过而不
          拖垮整个 change_set；若最终一条 change_item 都没有，则返回 None，
          由调用方决定如何向用户提示"该部分未成功生成"。

    Args:
        hypothesis: 待生成变更的 AdaptationHypothesis。
        node_content: 目标节点当前内容（用于 prompt 上下文，可为空）。
        extra_instruction: 学生"重新生成"时补充的意见，会被拼入 prompt。
        use_fast_model: 是否使用快速模型（默认使用智能模型，因为涉及内容生成）。

    Returns:
        CourseChangeSet，或 None（生成彻底失败）。
    """
    if not hypothesis.course_id:
        logger.warning("generate_change_set: hypothesis.course_id 为空，仍继续生成但无法归档课程范围")

    prompt = _CHANGE_SET_PROMPT_TEMPLATE.format(
        course_id=hypothesis.course_id or "",
        node_id=hypothesis.node_id,
        node_content=node_content or "（当前节点暂无正文）",
        hypothesis=hypothesis.hypothesis,
        confidence=hypothesis.confidence,
        extra_instruction=extra_instruction or "（无）",
    )

    last_raw_response: Optional[str] = None
    last_error: Optional[str] = None
    model_id = _generator.model_fast if use_fast_model else _generator.model_smart

    for attempt in range(_MAX_GENERATION_ATTEMPTS):
        if attempt == 0:
            current_prompt = prompt
        else:
            # 受控重试：把上一次的校验错误回传模型，要求修正（规格文档 MUST 项）。
            current_prompt = f"""{prompt}

你上一次的输出未通过 JSON Schema 校验，错误信息：
{last_error}

上一次的原始输出（供参考，请修正而不是完全重写无关内容）：
{(last_raw_response or "")[:1500]}

请重新输出严格符合 Schema 的 JSON，不要包含任何解释文字或 markdown 代码块标记。
"""

        response = await _generator._call_llm(
            current_prompt, _CHANGE_SET_SYSTEM_PROMPT, use_fast_model=use_fast_model
        )
        if not response:
            last_error = "LLM 未返回任何内容（可能是 API 未配置或调用失败）"
            continue

        last_raw_response = response
        parsed = _generator._extract_json(response)
        if not parsed or not isinstance(parsed, dict):
            last_error = "无法从响应中提取合法 JSON 对象"
            continue

        change_set, error = _build_change_set_from_parsed(
            parsed, hypothesis, model_id=model_id, extra_instruction=extra_instruction
        )
        if change_set is not None:
            return change_set
        last_error = error

    logger.warning(
        "generate_change_set: 生成失败，已达最大重试次数 %d，最后错误：%s",
        _MAX_GENERATION_ATTEMPTS, last_error,
    )
    return None


def _build_change_set_from_parsed(
    parsed: Dict[str, Any],
    hypothesis: AdaptationHypothesis,
    model_id: str,
    extra_instruction: Optional[str],
) -> tuple[Optional[CourseChangeSet], Optional[str]]:
    """把模型输出的 dict 转换为 CourseChangeSet，做粒度化兜底：
    单条 change_item 校验失败时跳过该条并记录，而不是让整个 change_set 生成失败
    （对应"重试仍失败时 MUST 触发对应粒度的兜底"）。

    Returns:
        (CourseChangeSet | None, 错误信息 | None)
    """
    scope = parsed.get("scope")
    raw_items = parsed.get("change_items")
    if scope not in ("block", "section", "sections", "chapters", "book"):
        return None, f"scope 字段非法或缺失: {scope!r}"
    if not isinstance(raw_items, list) or not raw_items:
        return None, "change_items 字段缺失或为空数组"

    valid_items: List[ChangeItem] = []
    skipped: List[str] = []
    for idx, raw_item in enumerate(raw_items):
        try:
            item = ChangeItem(
                target_node_id=raw_item.get("target_node_id"),
                operation=raw_item.get("operation"),
                before=raw_item.get("before"),
                after=raw_item.get("after"),
                reason=raw_item.get("reason", ""),
            )
            if not item.after:
                raise ValueError("after 字段为空")
            valid_items.append(item)
        except (ValidationError, ValueError, TypeError) as e:
            skipped.append(f"change_items[{idx}] 校验失败已跳过: {e}")
            logger.warning("generate_change_set: %s", skipped[-1])

    if not valid_items:
        detail = "; ".join(skipped) if skipped else "change_items 均无效"
        return None, f"所有 change_items 均未通过校验（{detail}）"

    scope_node_ids = parsed.get("scope_node_ids")
    if not isinstance(scope_node_ids, list) or not scope_node_ids:
        # 兜底：至少包含所有 change_item 涉及的节点
        scope_node_ids = sorted({item.target_node_id for item in valid_items})

    generation_meta: Dict[str, Any] = {
        "model_id": model_id,
        "prompt_template": _prompt_template_id(),
        "params": {
            "extra_instruction": extra_instruction,
            "hypothesis_confidence": hypothesis.confidence,
        },
        "generated_at": datetime.now().isoformat(),
    }
    if skipped:
        generation_meta["skipped_change_items"] = skipped

    change_set = CourseChangeSet(
        course_id=hypothesis.course_id or "",
        scope=scope,
        scope_node_ids=scope_node_ids,
        change_items=valid_items,
        source_hypothesis_id=hypothesis.id,
        status="pending",
        generation_meta=generation_meta,
    )
    return change_set, None
