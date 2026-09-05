"""Lightweight strategy contracts for AI course generation.

The strategy layer does not call an LLM. It only names the generation use case
and turns learner-state / teaching-decision signals into bounded prompt
constraints, so course blueprint generation does not get mixed with
personalized remediation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GENERAL_COURSE_BLUEPRINT = "general_course_blueprint"
PERSONALIZED_NODE_EXPLANATION = "personalized_node_explanation"
WEAKNESS_REMEDIATION_CONTENT = "weakness_remediation_content"


@dataclass(frozen=True)
class CourseGenerationStrategy:
    use_case: str
    label: str
    personalization_scope: str
    include_ai_learning_context: bool
    target_effects: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        effects = self.target_effects or ["保持课程契约清晰、可验证"]
        guardrails = self.guardrails or ["不得突破课程蓝图、节点边界和事实约束"]
        return "\n".join([
            "## 课程生成策略",
            f"- 生成用途：{self.label}",
            f"- 个性化边界：{self.personalization_scope}",
            f"- 是否读取 AI Learning Context：{'是' if self.include_ai_learning_context else '否'}",
            "- 内容倾向：" + "；".join(effects),
            "- 边界要求：" + "；".join(guardrails),
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_case": self.use_case,
            "label": self.label,
            "personalization_scope": self.personalization_scope,
            "include_ai_learning_context": self.include_ai_learning_context,
            "target_effects": list(self.target_effects),
            "guardrails": list(self.guardrails),
        }


def build_course_generation_strategy(
    use_case: str,
    *,
    ai_learning_context: Any = None,
) -> CourseGenerationStrategy:
    """Return the bounded strategy for a course generation use case."""
    if use_case == GENERAL_COURSE_BLUEPRINT:
        return CourseGenerationStrategy(
            use_case=GENERAL_COURSE_BLUEPRINT,
            label="通用课程结构蓝图",
            personalization_scope="面向所有学习者的课程骨架，不使用单个学习者状态改写目录主线。",
            include_ai_learning_context=False,
            target_effects=[
                "章节父子关系清晰",
                "学习目标、范围边界、误区和验收标准可追踪",
                "后续节点正文可按同一蓝图生成",
            ],
            guardrails=[
                "不得根据默认用户的临时状态改变课程结构",
                "不得把复习建议写进课程目录",
            ],
        )

    if use_case == WEAKNESS_REMEDIATION_CONTENT:
        effects = [
            "优先补清晰例子",
            "增加可验证小练习",
            "放慢推理链条",
        ]
        effects.extend(_decision_effects(ai_learning_context))
        return CourseGenerationStrategy(
            use_case=WEAKNESS_REMEDIATION_CONTENT,
            label="薄弱点补充内容",
            personalization_scope="只调整当前节点或内容块的讲法、例子和练习密度，不改课程蓝图。",
            include_ai_learning_context=True,
            target_effects=_dedupe(effects),
            guardrails=[
                "必须服务当前薄弱点或风险",
                "不得把个性化补救内容扩散成全课程结构变更",
                "不得凭空新增课程契约之外的概念",
            ],
        )

    effects = [
        "按学习者状态调整解释速度",
        "保留课程节点契约",
    ]
    effects.extend(_decision_effects(ai_learning_context))
    return CourseGenerationStrategy(
        use_case=PERSONALIZED_NODE_EXPLANATION,
        label="个性化节点解释",
        personalization_scope="在当前节点内部调整讲法，不替换原有笔记、错题、课程蓝图和结构化 blocks。",
        include_ai_learning_context=True,
        target_effects=_dedupe(effects),
        guardrails=[
            "课程账本和节点契约优先于个性化推断",
            "状态与决策只能影响讲法、例子、练习和提醒",
            "不得把系统推断写成确定事实",
        ],
    )


def build_course_generation_strategy_prompt(
    use_case: str,
    *,
    ai_learning_context: Any = None,
) -> str:
    return build_course_generation_strategy(
        use_case,
        ai_learning_context=ai_learning_context,
    ).to_prompt()


def classify_generation_use_case(
    *,
    requirement: str = "",
    block_type: str = "",
    action_type: str = "",
    default: str = PERSONALIZED_NODE_EXPLANATION,
) -> str:
    """Classify local generation requests without scanning old state again."""
    text = " ".join([requirement, block_type, action_type]).lower()
    remediation_keywords = [
        "薄弱",
        "错题",
        "复习",
        "练习",
        "测验",
        "自测",
        "不懂",
        "不会",
        "practice",
        "review",
        "exercise",
        "quiz",
    ]
    if any(keyword in text for keyword in remediation_keywords):
        return WEAKNESS_REMEDIATION_CONTENT
    return default


def _decision_effects(ai_learning_context: Any) -> list[str]:
    if not ai_learning_context:
        return []
    data = ai_learning_context.to_dict() if hasattr(ai_learning_context, "to_dict") else dict(ai_learning_context)
    decision = data.get("teaching_guidance") or {}
    effects = []
    if decision.get("needs_simplification"):
        effects.append("简化解释并减少跳步")
    if decision.get("needs_examples"):
        effects.append("补充贴近当前节点的例子")
    if decision.get("needs_weakness_practice"):
        effects.append("增加针对薄弱点的练习")
    if decision.get("needs_clarifying_question"):
        effects.append("先用小问题校准理解")
    if decision.get("recommends_review"):
        effects.append("加入复习提醒或回顾片段")
    return effects


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result
