"""灵知统一教学语义与两级编排规则。

课程级先确定学习目的、学科类型和课程教学类型；讲次级再结合本讲内容
确定本讲课型并排列教学块。旧字段只在这里转换，不继续形成平行规则。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "teaching_semantics_v1"

LEARNING_PURPOSES: dict[str, dict[str, Any]] = {
    "systematic": {
        "label": "系统学习",
        "result": "形成完整、可迁移的知识与能力结构",
    },
    "project": {
        "label": "项目实战",
        "result": "完成可展示、可评价的真实成果",
    },
    "exam": {
        "label": "期末冲刺",
        "result": "在限定时间内补齐重点并通过测评验证",
    },
}

SUBJECT_TYPES: dict[str, str] = {
    "auto": "自动判断",
    "general": "通用课程",
    "math_formal": "数学与形式科学",
    "programming_engineering": "编程与工程技术",
    "natural_science": "自然科学",
    "life_medical": "生命科学与医学基础",
    "humanities_social": "人文社科",
    "language_learning": "语言学习",
    "business_career": "商业与职业技能",
}

COURSE_TEACHING_TYPES: dict[str, dict[str, Any]] = {
    "theory": {
        "label": "理论课",
        "organizing_principle": "以概念、原理、推导和解释为主线",
        "lesson_type_mix": {"theory": 55, "theory_practice": 30, "review_assessment": 15},
        "default_arc": ["theory", "theory_practice", "review_assessment"],
        "required_block_roles": ["concept", "reasoning", "example", "checkpoint"],
    },
    "laboratory": {
        "label": "实验课",
        "organizing_principle": "以问题、实验、观察、数据和证据为主线",
        "lesson_type_mix": {"theory": 15, "experiment_inquiry": 65, "review_assessment": 20},
        "default_arc": ["theory", "experiment_inquiry", "review_assessment"],
        "required_block_roles": ["orientation", "activity", "reasoning", "feedback"],
    },
    "practice": {
        "label": "实践课",
        "organizing_principle": "以示范、操作、练习和反馈为主线",
        "lesson_type_mix": {"theory_practice": 25, "practice": 60, "review_assessment": 15},
        "default_arc": ["theory_practice", "practice", "review_assessment"],
        "required_block_roles": ["example", "application", "activity", "feedback"],
    },
    "seminar": {
        "label": "研讨课",
        "organizing_principle": "以问题、材料、案例、讨论和判断为主线",
        "lesson_type_mix": {"theory": 15, "case_discussion": 70, "review_assessment": 15},
        "default_arc": ["theory", "case_discussion", "review_assessment"],
        "required_block_roles": ["orientation", "example", "reasoning", "counterexample", "feedback"],
    },
    "project": {
        "label": "项目课",
        "organizing_principle": "以阶段任务、成果制作、评审和迭代为主线",
        "lesson_type_mix": {"theory_practice": 20, "project_workshop": 65, "review_assessment": 15},
        "default_arc": ["theory_practice", "project_workshop", "review_assessment"],
        "required_block_roles": ["orientation", "application", "activity", "feedback", "transfer"],
    },
    "comprehensive": {
        "label": "综合课",
        "organizing_principle": "根据内容在讲授、练习、实验、研讨和项目之间形成最小充分组合",
        "lesson_type_mix": {
            "theory": 20,
            "theory_practice": 25,
            "practice": 15,
            "case_discussion": 10,
            "experiment_inquiry": 10,
            "project_workshop": 10,
            "review_assessment": 10,
        },
        "default_arc": ["theory", "theory_practice", "practice", "review_assessment"],
        "required_block_roles": ["orientation", "concept", "application", "activity", "feedback"],
    },
}

LESSON_TYPE_LABELS = {
    "theory": "理论讲授",
    "practice": "实践操作",
    "theory_practice": "讲练结合",
    "case_discussion": "案例研讨",
    "experiment_inquiry": "实验探究",
    "project_workshop": "项目工作坊",
    "review_assessment": "复习测评",
}

_LEGACY_COURSE_TYPE_TO_PURPOSE = {
    "systematic": "systematic",
    "project": "project",
    "inquiry": "systematic",
    "exam": "exam",
}

_LEGACY_COMPOSITION_TO_TEACHING_TYPE = {
    "theory_driven": "theory",
    "project_driven": "project",
    "inquiry_driven": "seminar",
    "example_driven": "comprehensive",
    "case_driven": "seminar",
    "practice_driven": "practice",
    "balanced": "comprehensive",
}

_DEFAULT_TEACHING_TYPE_BY_PURPOSE = {
    "systematic": "comprehensive",
    "project": "project",
    "exam": "comprehensive",
}

_BLOCK_ROLE_ORDER: dict[str, tuple[str, ...]] = {
    "theory": ("orientation", "objective", "prerequisite", "concept", "reasoning", "counterexample", "example", "application", "checkpoint", "feedback", "transfer", "remediation"),
    "theory_practice": ("orientation", "objective", "concept", "example", "application", "activity", "feedback", "reasoning", "transfer", "checkpoint", "remediation"),
    "practice": ("orientation", "objective", "example", "application", "activity", "feedback", "transfer", "checkpoint", "remediation"),
    "case_discussion": ("orientation", "objective", "example", "reasoning", "counterexample", "activity", "feedback", "transfer", "checkpoint"),
    "experiment_inquiry": ("orientation", "objective", "concept", "activity", "reasoning", "counterexample", "feedback", "transfer", "checkpoint"),
    "project_workshop": ("orientation", "objective", "application", "activity", "feedback", "reasoning", "transfer", "checkpoint"),
    "review_assessment": ("orientation", "objective", "checkpoint", "feedback", "remediation", "application", "transfer", "concept"),
}


def _value(raw: Any) -> str:
    return str(getattr(raw, "value", raw) or "").strip().lower()


def resolve_learning_purpose(raw: Any = None, *, legacy_course_type: Any = None) -> str:
    explicit = _value(raw)
    if explicit in LEARNING_PURPOSES:
        return explicit
    return _LEGACY_COURSE_TYPE_TO_PURPOSE.get(_value(legacy_course_type), "systematic")


def resolve_course_teaching_type(
    raw: Any = None,
    *,
    learning_purpose: Any = None,
    legacy_course_type: Any = None,
    composition_style: Any = None,
) -> tuple[str, str]:
    explicit = _value(raw)
    if explicit in COURSE_TEACHING_TYPES:
        return explicit, "course_teaching_type"
    if _value(legacy_course_type) == "inquiry":
        return "seminar", "legacy_course_type"
    legacy_style = _value(composition_style)
    if legacy_style in _LEGACY_COMPOSITION_TO_TEACHING_TYPE:
        return _LEGACY_COMPOSITION_TO_TEACHING_TYPE[legacy_style], "composition_style"
    purpose = resolve_learning_purpose(learning_purpose, legacy_course_type=legacy_course_type)
    return _DEFAULT_TEACHING_TYPE_BY_PURPOSE[purpose], "learning_purpose_default"


def compile_course_semantics(
    *,
    learning_purpose: Any = None,
    legacy_course_type: Any = None,
    subject_type: Any = None,
    course_teaching_type: Any = None,
    composition_style: Any = None,
) -> dict[str, Any]:
    purpose = resolve_learning_purpose(
        learning_purpose,
        legacy_course_type=legacy_course_type,
    )
    teaching_type, resolved_from = resolve_course_teaching_type(
        course_teaching_type,
        learning_purpose=purpose,
        legacy_course_type=legacy_course_type,
        composition_style=composition_style,
    )
    subject = _value(subject_type) or "auto"
    if subject not in SUBJECT_TYPES:
        subject = "auto"
    contract = deepcopy(COURSE_TEACHING_TYPES[teaching_type])
    strategies: list[str] = []
    if _value(legacy_course_type) == "inquiry":
        strategies.append("problem_inquiry")
    return {
        "teaching_semantics_version": SCHEMA_VERSION,
        "learning_purpose": purpose,
        "learning_purpose_label": LEARNING_PURPOSES[purpose]["label"],
        "learning_purpose_result": LEARNING_PURPOSES[purpose]["result"],
        "subject_type": subject,
        "subject_type_label": SUBJECT_TYPES[subject],
        "course_teaching_type": teaching_type,
        "course_teaching_type_label": contract["label"],
        "course_teaching_type_resolved_from": resolved_from,
        "course_teaching_type_contract": contract,
        "course_lesson_type_distribution": deepcopy(contract["lesson_type_mix"]),
        "internal_teaching_strategies": strategies,
    }


def lesson_phase(index: int, total: int) -> str:
    if total <= 1:
        return "single"
    ratio = max(0, index) / max(1, total - 1)
    if ratio <= 0.2:
        return "opening"
    if ratio >= 0.8:
        return "closing"
    return "development"


def recommend_lesson_type(
    course_teaching_type: Any,
    *,
    phase: str,
    legacy_candidate: str = "theory",
) -> str:
    teaching_type, _ = resolve_course_teaching_type(course_teaching_type)
    candidate = legacy_candidate if legacy_candidate in LESSON_TYPE_LABELS else "theory"
    if phase == "closing":
        return "review_assessment"
    if teaching_type == "comprehensive":
        return candidate
    if teaching_type == "theory":
        return candidate if candidate in {"theory", "theory_practice", "review_assessment"} else "theory_practice"
    if teaching_type == "laboratory":
        return "theory" if phase == "opening" else "experiment_inquiry"
    if teaching_type == "practice":
        return "theory_practice" if phase == "opening" else "practice"
    if teaching_type == "seminar":
        return "theory" if phase == "opening" else "case_discussion"
    if teaching_type == "project":
        return "theory_practice" if phase == "opening" else "project_workshop"
    return candidate


def order_teaching_blocks(
    blocks: list[dict[str, Any]],
    lesson_type: str,
) -> list[dict[str, Any]]:
    """在每个小节内部按本讲课型排序，保持小节次序与块身份不变。"""
    order = _BLOCK_ROLE_ORDER.get(lesson_type, _BLOCK_ROLE_ORDER["theory"])
    priority = {role: index for index, role in enumerate(order)}
    section_order: dict[str, int] = {}
    for block in blocks:
        section_id = _value(block.get("section_node_id"))
        section_order.setdefault(section_id, len(section_order))
    indexed = list(enumerate(blocks))
    indexed.sort(
        key=lambda pair: (
            section_order.get(_value(pair[1].get("section_node_id")), len(section_order)),
            priority.get(_value(pair[1].get("role")), len(priority)),
            pair[0],
        )
    )
    return [deepcopy(block) for _, block in indexed]


__all__ = [
    "COURSE_TEACHING_TYPES",
    "LEARNING_PURPOSES",
    "LESSON_TYPE_LABELS",
    "SCHEMA_VERSION",
    "SUBJECT_TYPES",
    "compile_course_semantics",
    "lesson_phase",
    "order_teaching_blocks",
    "recommend_lesson_type",
    "resolve_course_teaching_type",
    "resolve_learning_purpose",
]
