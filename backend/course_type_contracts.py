"""Deterministic course-type routing and generation contracts.

Course type controls how a course is organized. Subject pedagogy still controls
how the content is taught, while the learner starting profile controls where an
individual path expands, compresses, or remains provisional.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COURSE_TYPE_SYSTEMATIC = "systematic"
COURSE_TYPE_PROJECT = "project"
COURSE_TYPE_INQUIRY = "inquiry"
COURSE_TYPE_EXAM = "exam"

COURSE_TYPES = {
    COURSE_TYPE_SYSTEMATIC,
    COURSE_TYPE_PROJECT,
    COURSE_TYPE_INQUIRY,
    COURSE_TYPE_EXAM,
}
ENABLED_COURSE_TYPES = {
    COURSE_TYPE_SYSTEMATIC,
    COURSE_TYPE_PROJECT,
}


class CourseTypeNotEnabled(ValueError):
    def __init__(self, course_type: str) -> None:
        self.course_type = course_type
        self.code = "course_type_not_enabled"
        super().__init__(f"课程类型尚未开放：{course_type}")


def ensure_course_type_enabled(course_type: str) -> None:
    if course_type not in ENABLED_COURSE_TYPES:
        raise CourseTypeNotEnabled(course_type)


COURSE_TYPE_CONTRACTS: dict[str, dict[str, Any]] = {
    COURSE_TYPE_SYSTEMATIC: {
        "label": "系统学习",
        "organizing_question": "学习者要系统掌握哪个知识领域？",
        "planning_sequence": ["知识地图", "先修关系", "基础到进阶", "综合应用"],
        "outline_requirements": [
            "覆盖目标领域的必要知识结构",
            "按先修关系从基础推进到综合应用",
            "不得只围绕零散问题或单一项目罗列内容",
        ],
        "completion_evidence": "学习者能够解释、迁移并综合应用核心知识",
    },
    COURSE_TYPE_PROJECT: {
        "label": "项目实战",
        "organizing_question": "学习者要完成什么项目，以及为了完成它需要补齐什么？",
        "planning_sequence": ["项目目标", "交付物", "项目里程碑", "能力缺口", "学习与验证"],
        "outline_requirements": [
            "章节围绕可检查的项目里程碑组织，而不是写成普通学科目录",
            "把学习者已有经验、重点补充和待验证内容显式映射到学习路径",
            "每个阶段必须同时包含必要知识、实践动作和可检查产出",
            "最终路径必须能够完成约定交付物",
        ],
        "completion_evidence": "学习者完成约定交付物，并能说明关键决策与验证依据",
    },
    COURSE_TYPE_INQUIRY: {
        "label": "问题探究",
        "organizing_question": "学习者要回答什么核心问题？",
        "planning_sequence": ["界定问题", "拆解子问题", "组织证据", "检验解释", "形成结论"],
        "outline_requirements": [
            "目录由核心问题和子问题推进，不得伪装成带问号的普通章节目录",
            "区分已有认识、待验证假设、证据需求和阶段性结论",
            "最终形成有证据边界的回答或判断",
        ],
        "completion_evidence": "学习者形成可追溯证据、能说明边界的结论",
    },
    COURSE_TYPE_EXAM: {
        "label": "考试冲刺",
        "organizing_question": "在限定时间内，哪些考纲能力最需要优先补齐？",
        "planning_sequence": ["考试范围", "当前准备度", "薄弱点", "复习优先级", "模拟验证"],
        "outline_requirements": [
            "按考纲覆盖、剩余时间和薄弱程度确定优先级",
            "每个阶段包含复习目标、典型任务和检查方式",
            "不得为了形式完整平均分配学习时间",
        ],
        "completion_evidence": "学习者通过分阶段检查与模拟任务达到目标准备度",
    },
}


_LEGACY_PURPOSE_TO_TYPE = {
    "systematic": COURSE_TYPE_SYSTEMATIC,
    "exam_sprint": COURSE_TYPE_EXAM,
    "material_organization": COURSE_TYPE_SYSTEMATIC,
    "personalized_remedial": COURSE_TYPE_SYSTEMATIC,
}

_LEGACY_COMPOSITION_TO_TYPE = {
    "project_driven": COURSE_TYPE_PROJECT,
    "inquiry_driven": COURSE_TYPE_INQUIRY,
}

_TYPE_TO_PURPOSE = {
    COURSE_TYPE_SYSTEMATIC: "systematic",
    COURSE_TYPE_PROJECT: "systematic",
    COURSE_TYPE_INQUIRY: "systematic",
    COURSE_TYPE_EXAM: "exam_sprint",
}

_TYPE_TO_COMPOSITION = {
    COURSE_TYPE_SYSTEMATIC: "balanced",
    COURSE_TYPE_PROJECT: "project_driven",
    COURSE_TYPE_INQUIRY: "inquiry_driven",
    COURSE_TYPE_EXAM: "example_driven",
}


def resolve_course_type(
    course_type: Any = None,
    *,
    course_purpose: Any = None,
    composition_style: Any = None,
) -> tuple[str, str]:
    """Resolve the new type without breaking old requests.

    The explicit new field always wins. Legacy purpose is stronger than legacy
    composition because it historically represented a user-selected goal.
    """
    explicit = _string_value(course_type)
    if explicit in COURSE_TYPES:
        return explicit, "course_type"
    legacy_purpose = _string_value(course_purpose)
    if legacy_purpose in _LEGACY_PURPOSE_TO_TYPE and legacy_purpose != "systematic":
        return _LEGACY_PURPOSE_TO_TYPE[legacy_purpose], "course_purpose"
    legacy_style = _string_value(composition_style)
    if legacy_style in _LEGACY_COMPOSITION_TO_TYPE:
        return _LEGACY_COMPOSITION_TO_TYPE[legacy_style], "composition_style"
    if legacy_purpose == "systematic":
        return COURSE_TYPE_SYSTEMATIC, "course_purpose"
    return COURSE_TYPE_SYSTEMATIC, "default"


def compatible_course_purpose(course_type: str, course_purpose: Any = None) -> str:
    legacy = _string_value(course_purpose)
    if legacy in _LEGACY_PURPOSE_TO_TYPE:
        return legacy
    return _TYPE_TO_PURPOSE.get(course_type, "systematic")


def course_purpose_for_type(course_type: str) -> str:
    return _TYPE_TO_PURPOSE.get(course_type, "systematic")


def default_composition_style(course_type: str) -> str:
    return _TYPE_TO_COMPOSITION.get(course_type, "balanced")


def compile_course_type_brief(
    *,
    course_type: Any,
    course_intent: Any,
    learner_starting_profile: Any,
    topic: str,
    requirements: str = "",
    learner_profile_summary: str = "",
    course_purpose: Any = None,
    composition_style: Any = None,
) -> dict[str, Any]:
    """Compile type-specific request data into the brief used by the LLM chain."""
    resolved_type, resolved_from = resolve_course_type(
        course_type,
        course_purpose=course_purpose,
        composition_style=composition_style,
    )
    intent = _model_dict(course_intent)
    intent["type"] = resolved_type
    intent = _fill_intent_defaults(resolved_type, intent, topic, requirements)
    starting_profile = _compile_starting_profile(
        learner_starting_profile,
        course_type=resolved_type,
        course_intent=intent,
        learner_profile_summary=learner_profile_summary,
    )
    contract = deepcopy(COURSE_TYPE_CONTRACTS[resolved_type])
    return {
        "course_type": resolved_type,
        "course_type_label": contract["label"],
        "course_type_resolved_from": resolved_from,
        "course_type_contract": contract,
        "course_intent": intent,
        "learner_starting_profile": starting_profile,
        "personalization_rationale": _personalization_rationale(
            resolved_type,
            intent,
            starting_profile,
        ),
    }


def apply_course_type_brief(
    brief: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    brief.update(compile_course_type_brief(**kwargs))
    contract = brief["course_type_contract"]
    hard_constraints = list(brief.get("hard_constraints") or [])
    for item in contract.get("outline_requirements") or []:
        if item not in hard_constraints:
            hard_constraints.append(item)
    brief["hard_constraints"] = hard_constraints
    expected_deliverable = str(
        (brief.get("course_intent") or {}).get("expected_deliverable") or ""
    ).strip()
    if expected_deliverable:
        deliverables = list(brief.get("expected_deliverables") or [])
        if expected_deliverable not in deliverables:
            deliverables.insert(0, expected_deliverable)
        brief["expected_deliverables"] = deliverables
    return brief


def _fill_intent_defaults(
    course_type: str,
    intent: dict[str, Any],
    topic: str,
    requirements: str,
) -> dict[str, Any]:
    result = deepcopy(intent)
    result["schema_version"] = "course_intent_v1"
    if course_type == COURSE_TYPE_PROJECT:
        if not str(result.get("project_goal") or "").strip():
            result["project_goal"] = topic
        if not str(result.get("expected_deliverable") or "").strip():
            result["expected_deliverable"] = "完成可展示、可检查的项目成果"
        result.setdefault("prior_experience", "")
        result.setdefault("current_uncertainty", "")
        result.setdefault("project_constraints", requirements)
    elif course_type == COURSE_TYPE_INQUIRY:
        if not str(result.get("core_question") or "").strip():
            result["core_question"] = topic
        result.setdefault("existing_understanding", "")
        result.setdefault("evidence_scope", "")
        result.setdefault("desired_output", "形成有证据边界的回答")
    elif course_type == COURSE_TYPE_EXAM:
        if not str(result.get("exam_name") or "").strip():
            result["exam_name"] = topic
        result.setdefault("exam_date", "")
        result.setdefault("exam_scope", requirements)
        result.setdefault("current_preparation", "")
    else:
        if not str(result.get("learning_goal") or "").strip():
            result["learning_goal"] = topic
        result.setdefault("desired_outcome", requirements)
        result.setdefault("existing_foundation", "")
    return result


def _compile_starting_profile(
    raw_profile: Any,
    *,
    course_type: str,
    course_intent: dict[str, Any],
    learner_profile_summary: str,
) -> dict[str, Any]:
    profile = _model_dict(raw_profile)
    strengths = _string_list(profile.get("self_reported_strengths"))
    focus_areas = _string_list(profile.get("focus_areas"))
    needs_validation = _string_list(profile.get("needs_validation"))
    if course_type == COURSE_TYPE_PROJECT:
        prior = str(course_intent.get("prior_experience") or "").strip()
        uncertainty = str(course_intent.get("current_uncertainty") or "").strip()
        if prior and prior not in strengths:
            strengths.append(prior)
        if uncertainty and uncertainty not in focus_areas:
            focus_areas.append(uncertainty)
        for item in strengths:
            marker = f"待在项目任务中验证：{item}"
            if marker not in needs_validation:
                needs_validation.append(marker)
    summary = str(profile.get("summary") or learner_profile_summary or "").strip()
    evidence_basis = str(profile.get("evidence_basis") or "self_reported").strip()
    if evidence_basis not in {"self_reported", "interview", "observed", "mixed"}:
        evidence_basis = "self_reported"
    if course_type == COURSE_TYPE_PROJECT:
        has_starting_evidence = bool(strengths or focus_areas)
    else:
        has_starting_evidence = bool(strengths or focus_areas or summary)
    default_status = "tentative" if has_starting_evidence else "insufficient"
    status = str(profile.get("status") or default_status).strip()
    if status not in {"insufficient", "tentative", "confirmed"}:
        status = default_status
    if evidence_basis == "self_reported" and status == "confirmed":
        status = "tentative"
    return {
        "summary": summary,
        "self_reported_strengths": strengths,
        "focus_areas": focus_areas,
        "needs_validation": needs_validation,
        "evidence_basis": evidence_basis,
        "status": status,
    }


def _personalization_rationale(
    course_type: str,
    intent: dict[str, Any],
    profile: dict[str, Any],
) -> list[str]:
    result = [
        "学习起点仅作为暂定规划依据，未经学习行为验证的自述不得写成已掌握事实。"
    ]
    if course_type == COURSE_TYPE_PROJECT:
        if profile.get("status") == "insufficient":
            result.append(
                "起点信息不足；不得压缩任何内容，未证实能力必须标为 verify_in_project。"
            )
        if profile.get("self_reported_strengths"):
            result.append(
                "自述已有经验只能暂定压缩，对应能力必须标为 verify_in_project 并保留验证节点。"
            )
        if profile.get("focus_areas"):
            result.append("当前不确定项需要展开为重点知识、实践动作和检查产出。")
        result.append(
            f"所有个性化调整必须服务项目交付物：{intent.get('expected_deliverable')}"
        )
    return result


def _model_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    if not isinstance(value, dict):
        return {}
    return {key: deepcopy(item) for key, item in value.items() if item is not None}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:20]


def _string_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


__all__ = [
    "COURSE_TYPES",
    "COURSE_TYPE_CONTRACTS",
    "ENABLED_COURSE_TYPES",
    "CourseTypeNotEnabled",
    "apply_course_type_brief",
    "compatible_course_purpose",
    "compile_course_type_brief",
    "course_purpose_for_type",
    "default_composition_style",
    "ensure_course_type_enabled",
    "resolve_course_type",
]
