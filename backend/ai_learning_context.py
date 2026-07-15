"""Formal learner-model context used by learner-aware course operations."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from learner_context import DEFAULT_USER_ID
from learner_model import is_model_item_current
from learner_model_service import build_current_learner_model_for_course
from storage import storage


logger = logging.getLogger(__name__)


@dataclass
class AILearningContext:
    user_id: str = DEFAULT_USER_ID
    course_id: str | None = None
    node_id: str | None = None
    node_name: str = ""
    course_context: str = ""
    request_persona: str = ""
    learner_model: dict[str, Any] = field(default_factory=dict)
    teaching_guidance: dict[str, Any] = field(default_factory=dict)
    learner_model_prompt: str = ""
    teaching_guidance_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_prompt(self) -> str:
        return format_ai_learning_context_prompt(self)


def build_ai_learning_context(
    *,
    user_id: str = DEFAULT_USER_ID,
    course_id: str | None = None,
    node_id: str | None = None,
    node_name: str = "",
    question: str = "",
    request_context: str = "",
    request_persona: str = "",
    include_course_context: bool = True,
) -> AILearningContext:
    """Build bounded personalization from the one formal LearnerModel."""
    model = build_current_learner_model_for_course(course_id, user_id=user_id) or {}
    guidance = build_teaching_guidance(model, node_id=node_id, question=question)
    course_context = request_context or ""
    if include_course_context:
        course_context = "\n\n".join(
            part for part in [_load_course_context(course_id, node_id), request_context] if part
        )

    model_prompt = format_learner_model_prompt(model, node_id=node_id)
    guidance_prompt = format_teaching_guidance_prompt(guidance)
    sufficiency = model.get("data_sufficiency") or {}
    return AILearningContext(
        user_id=user_id,
        course_id=course_id,
        node_id=node_id,
        node_name=node_name,
        course_context=course_context,
        request_persona=request_persona.strip(),
        learner_model=model,
        teaching_guidance=guidance,
        learner_model_prompt=model_prompt,
        teaching_guidance_prompt=guidance_prompt,
        metadata={
            "learner_model_revision_id": model.get("model_revision_id"),
            "data_sufficiency": sufficiency.get("level", "none"),
            "personalization_enabled": bool(
                user_id != DEFAULT_USER_ID and sufficiency.get("level") not in {None, "none"}
            ),
            "guidance_reason_codes": guidance.get("reason_codes") or [],
        },
    )


def build_teaching_guidance(
    model: dict[str, Any],
    *,
    node_id: str | None,
    question: str,
) -> dict[str, Any]:
    """Translate model evidence into bounded content-generation guidance."""
    objective = next((
        item for item in model.get("objectives") or []
        if node_id and str(item.get("node_id") or "") == node_id
    ), None) or {}
    support = objective.get("support_need") or {}
    support_confidence = str(support.get("confidence") or "insufficient")
    has_support_need = (
        is_model_item_current(objective)
        and support.get("status") == "needs_support"
        and support_confidence in {"medium", "high"}
    )
    text = str(question or "").lower()
    asks_for_simplification = any(token in text for token in [
        "不懂", "不会", "困惑", "太难", "简化", "简单", "confused", "hard", "simplify",
    ])
    asks_for_example = any(token in text for token in [
        "例子", "举例", "案例", "example",
    ])
    reason_codes: list[str] = []
    if asks_for_simplification:
        reason_codes.append("explicit_simplification_request")
    if asks_for_example:
        reason_codes.append("explicit_example_request")
    if has_support_need:
        reason_codes.append(str(support.get("reason_code") or "formal_support_need"))

    return {
        "model_revision_id": model.get("model_revision_id"),
        "objective_id": objective.get("objective_id"),
        "objective_revision_id": objective.get("objective_revision_id"),
        "data_sufficiency": (model.get("data_sufficiency") or {}).get("level", "none"),
        "needs_simplification": asks_for_simplification or has_support_need,
        "needs_examples": asks_for_example or has_support_need,
        "needs_weakness_practice": has_support_need,
        "recommends_review": has_support_need,
        "needs_clarifying_question": False,
        "reason_codes": reason_codes,
        "evidence_refs": support.get("evidence_refs") or [],
    }


def format_learner_model_prompt(model: dict[str, Any], *, node_id: str | None) -> str:
    if not model:
        return "当前课程没有可用的正式学习者模型，不进行个性化推断。"
    sufficiency = model.get("data_sufficiency") or {}
    objective = next((
        item for item in model.get("objectives") or []
        if node_id and str(item.get("node_id") or "") == node_id
    ), None)
    lines = [
        f"- 模型修订：{model.get('model_revision_id') or '无'}",
        f"- 证据充分度：{sufficiency.get('level', 'none')}",
        f"- 正式证据数：{sufficiency.get('formal_evidence_count', 0)}",
    ]
    if objective:
        current = is_model_item_current(objective)
        support = (objective.get("support_need") or {}) if current else {
            "status": "unknown",
            "confidence": "insufficient",
            "reason_code": "evidence_expired",
        }
        lines.extend([
            f"- 当前目标：{objective.get('statement') or objective.get('node_name') or objective.get('node_id')}",
            f"- 阅读状态：{objective.get('reading_status', 'not_started')}",
            f"- 正式掌握：{objective.get('mastery_status', 'not_checked')}",
            f"- 支持需求：{support.get('status', 'unknown')}；置信度 {support.get('confidence', 'insufficient')}；原因 {support.get('reason_code', 'insufficient_evidence')}",
        ])
        if not current:
            lines.append("- 边界：当前目标的模型证据已过有效期，只能作为历史线索，不能驱动个性化判断。")
    else:
        lines.append("- 当前目标：没有与当前节点匹配的正式目标，不推断薄弱点。")
    if sufficiency.get("level") in {None, "none", "limited"}:
        lines.append("- 边界：证据不足，只能响应用户明确要求，不能推断稳定偏好或能力。")
    return "\n".join(lines)


def format_teaching_guidance_prompt(guidance: dict[str, Any]) -> str:
    effects = []
    if guidance.get("needs_simplification"):
        effects.append("简化解释并减少跳步")
    if guidance.get("needs_examples"):
        effects.append("补充与当前节点直接相关的例子")
    if guidance.get("needs_weakness_practice"):
        effects.append("提供可验证的小练习，但不改课程主线")
    if guidance.get("recommends_review"):
        effects.append("加入简短回顾")
    if not effects:
        effects.append("保持课程契约与当前讲解节奏")
    lines = [f"- {item}" for item in effects]
    reasons = guidance.get("reason_codes") or []
    if reasons:
        lines.append("- 依据代码：" + "；".join(str(item) for item in reasons))
    return "\n".join(lines)


def format_ai_learning_context_prompt(context: AILearningContext | dict[str, Any]) -> str:
    data = context.to_dict() if isinstance(context, AILearningContext) else dict(context)
    explicit_persona = str(data.get("request_persona") or "").strip()
    return f"""## 课程与节点上下文
- node_id: {data.get('node_id') or '未知'}
- 节点名称：{data.get('node_name') or '未知'}
{_clip(data.get('course_context') or '无', 18000)}

## 正式学习者模型
{data.get('learner_model_prompt') or '当前没有可用的正式学习者模型。'}

## 本次教学指导
{data.get('teaching_guidance_prompt') or '保持直接、清晰、可验证的讲解。'}

## 用户本次显式说明
{explicit_persona or '无；不得从历史行为猜测学习风格或人格。'}

## 使用边界
- 课程账本和节点契约优先于个性化推断。
- 阅读不等于掌握；单次失败不等于稳定薄弱点。
- 学习者模型只解释正式证据，不能直接改写课程、事实或下一步动作。"""


def _load_course_context(course_id: str | None, node_id: str | None) -> str:
    if not course_id or not node_id:
        return ""
    try:
        course = storage.load_course(course_id)
    except Exception:
        logger.debug("Could not load course context for AI Learning Context", exc_info=True)
        return ""
    if not course:
        return ""
    nodes = _flatten_nodes(course.get("nodes", []))
    current = next((node for node in nodes if node.get("node_id") == node_id), None)
    if not current:
        return ""
    parts = [f"课程：{course.get('course_name', '')}".strip()]
    if current.get("parent_node_id"):
        parent = next(
            (node for node in nodes if node.get("node_id") == current.get("parent_node_id")),
            None,
        )
        if parent:
            parts.append(f"父章节：{parent.get('node_name', '')}")
    parts.append(f"当前节点：{current.get('node_name', '')}\n{current.get('node_content', '')}")
    index = next((i for i, node in enumerate(nodes) if node.get("node_id") == node_id), -1)
    if index > 0:
        parts.append(f"前序节点：{nodes[index - 1].get('node_name', '')}")
    if index != -1 and index < len(nodes) - 1:
        parts.append(f"后续节点：{nodes[index + 1].get('node_name', '')}")
    return "\n\n".join(part for part in parts if part.strip())


def _flatten_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        result.append(node)
        if node.get("children"):
            result.extend(_flatten_nodes(node["children"]))
    return result


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


__all__ = [
    "AILearningContext",
    "build_ai_learning_context",
    "build_teaching_guidance",
    "format_ai_learning_context_prompt",
    "format_learner_model_prompt",
    "format_teaching_guidance_prompt",
]
