"""Formal course-document templates compiled from Lingzhi's canonical data.

The templates in this module are presentation and generation contracts, not a
second source of course truth.  Course profile, outline and lesson-plan values
continue to belong to their existing repositories; this module only maps those
values into the document structure teachers expect when reading or exporting a
syllabus and lesson plan.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


FORMAL_AUTHORING_TEMPLATE_VERSION = "formal_course_authoring_v2"

OUTLINE_DOCUMENT_SECTIONS = (
    "课程基本信息",
    "课程定位与简介",
    "教学目标",
    "课程要求",
    "考核与成绩构成",
    "教学内容与学时安排",
    "参考资料",
)

LESSON_PLAN_DOCUMENT_SECTIONS = (
    "课次基本信息",
    "教学目标",
    "教学重点与难点",
    "教学准备与来源资料",
    "教学过程",
    "课堂检查与评价证据",
    "作业与拓展",
    "教学备注与课后反思",
)

OBJECTIVE_DIMENSIONS = (
    {
        "id": "knowledge_capability",
        "label": "知识与能力",
        "policy": "必须落到可观察、可检查的学习者表现",
    },
    {
        "id": "process_method",
        "label": "过程与方法",
        "policy": "通过学科适配的分析、推导、实验、实作或论证任务体现",
    },
    {
        "id": "transfer_innovation",
        "label": "迁移与创新",
        "policy": "只在课程目标和本讲课型真实需要时生成，不为补齐模板编造空洞目标",
    },
)

_PROFILE_FIELDS = (
    "course_code",
    "course_category",
    "credits",
    "total_hours",
    "target_major",
    "target_grade",
    "course_intro",
    "assessment_method",
    "teaching_goals",
)

_TEACHING_CONTEXT_LABELS = {
    "classroom": "线下课堂",
    "online": "在线教学",
    "blended": "混合式教学",
    "self_study": "自主学习",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _text_list(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    return list(dict.fromkeys(
        text
        for item in values
        if (text := _text(item))
    ))[:limit]


def snapshot_formal_course_profile(profile: Any) -> dict[str, Any]:
    """Freeze only the confirmed baseline fields needed by generation.

    The snapshot belongs to the generation brief and participates in its
    fingerprint.  It never replaces the live ``course_profile``.
    """
    source = profile if isinstance(profile, dict) else {}
    snapshot: dict[str, Any] = {}
    for field in _PROFILE_FIELDS:
        value = deepcopy(source.get(field))
        if isinstance(value, str):
            value = _text(value)
        if value not in (None, "", [], {}):
            snapshot[field] = value
    # ``course_goal`` is a historical alias of ``teaching_goals``. Keep one
    # canonical value so prompts and fingerprints do not carry the same
    # teacher intent twice.
    if "teaching_goals" not in snapshot:
        fallback_goal = _text(source.get("course_goal"))
        if fallback_goal:
            snapshot["teaching_goals"] = fallback_goal
    return snapshot


def attach_formal_course_profile(
    brief: dict[str, Any],
    profile: Any,
) -> dict[str, Any]:
    """Attach the current baseline snapshot to the existing generation brief."""
    snapshot = snapshot_formal_course_profile(profile)
    if snapshot:
        brief["formal_course_profile"] = snapshot
    else:
        brief.pop("formal_course_profile", None)
    return brief


def _teacher_brief(course_data: dict[str, Any]) -> dict[str, Any]:
    direct = course_data.get("teacher_course_brief")
    if isinstance(direct, dict) and direct:
        return direct
    request = course_data.get("generation_request")
    if isinstance(request, dict):
        value = request.get("teacher_course_brief")
        if isinstance(value, dict):
            return value
    brief = course_data.get("course_generation_brief")
    if isinstance(brief, dict):
        value = brief.get("teacher_course_brief")
        if isinstance(value, dict):
            return value
    return {}


def _course_profile(course_data: dict[str, Any]) -> dict[str, Any]:
    current = course_data.get("course_profile")
    if isinstance(current, dict) and current:
        return snapshot_formal_course_profile(current)
    brief = course_data.get("course_generation_brief")
    if isinstance(brief, dict):
        return snapshot_formal_course_profile(
            brief.get("formal_course_profile")
        )
    return {}


def _source_labels(course_data: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    labels: list[str] = []

    def add(value: Any) -> None:
        text = _text(value)
        if text and text not in labels:
            labels.append(text)

    for card in course_data.get("material_cards") or []:
        if not isinstance(card, dict):
            continue
        add(
            card.get("filename")
            or card.get("source_label")
            or card.get("title")
            or card.get("name")
        )
    for item in course_data.get("reference_materials") or []:
        if isinstance(item, dict):
            add(item.get("label") or item.get("title") or item.get("filename"))
        else:
            add(item)
    for item in plan.get("references") or plan.get("reference_materials") or []:
        if isinstance(item, dict):
            add(item.get("label") or item.get("title") or item.get("filename"))
        else:
            add(item)
    return labels[:30]


def compile_formal_course_context(
    course_data: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project canonical course values into the shared formal template."""
    effective_plan = plan if isinstance(plan, dict) else (
        course_data.get("course_outline")
        or course_data.get("course_plan")
        or {}
    )
    effective_plan = effective_plan if isinstance(effective_plan, dict) else {}
    profile = _course_profile(course_data)
    classroom = _teacher_brief(course_data)
    audience = _text(
        profile.get("target_grade")
        or classroom.get("target_audience")
        or course_data.get("target_audience")
    )
    total_hours = (
        profile.get("total_hours")
        if profile.get("total_hours") not in (None, "")
        else classroom.get("total_class_hours")
    )
    teaching_context = _text(classroom.get("teaching_context"))
    lesson_minutes = classroom.get("lesson_duration_minutes")
    class_size = classroom.get("class_size")
    information = {
        "课程代码": _text(profile.get("course_code")),
        "课程类别": _text(profile.get("course_category")),
        "学分": profile.get("credits"),
        "总学时": total_hours,
        "每次课时长": (
            f"{lesson_minutes} 分钟"
            if lesson_minutes not in (None, "")
            else ""
        ),
        "面向专业": _text(profile.get("target_major")),
        "教学对象": audience,
        "班级规模": (
            f"{class_size} 人"
            if class_size not in (None, "")
            else ""
        ),
        "学期": _text(classroom.get("academic_term")),
        "授课方式": _TEACHING_CONTEXT_LABELS.get(
            teaching_context,
            teaching_context,
        ),
    }
    information = {
        key: value for key, value in information.items()
        if value not in (None, "", [], {})
    }
    assessment_methods = _text_list(profile.get("assessment_method"))
    assessment_methods.extend(
        item for item in _text_list(classroom.get("course_assessment_plan"))
        if item not in assessment_methods
    )
    class_profile = _text(classroom.get("class_profile"))
    requirements = [
        item for item in _text_list(classroom.get("additional_requirements"))
        if item not in assessment_methods
        and item != class_profile
        and item != f"学情特点：{class_profile}"
    ]

    return {
        "schema_version": FORMAL_AUTHORING_TEMPLATE_VERSION,
        "course_information": information,
        "course_intro": _text(profile.get("course_intro")),
        "positioning": _text(effective_plan.get("positioning")),
        "student_profile": class_profile,
        "learning_objectives": _text_list(
            effective_plan.get("learning_objectives")
            or profile.get("teaching_goals")
            or profile.get("course_goal")
        ),
        "prerequisites": _text_list(effective_plan.get("prerequisites")),
        "teaching_requirements": list(dict.fromkeys(requirements)),
        "assessment_methods": list(dict.fromkeys(assessment_methods)),
        "references": _source_labels(course_data, effective_plan),
        "outline_document_sections": list(OUTLINE_DOCUMENT_SECTIONS),
        "lesson_plan_document_sections": list(LESSON_PLAN_DOCUMENT_SECTIONS),
        "objective_dimensions": [deepcopy(item) for item in OBJECTIVE_DIMENSIONS],
        "lesson_flow_contract": {
            "required_roles": [
                "进入本讲问题或任务",
                "完成核心教学",
                "安排学习者可观察行动",
                "产生检查或总结证据",
            ],
            "selection_rule": (
                "由教学类型、学科画像、本讲课型和已确认教学块决定具体流程；"
                "不强制所有课次套用相同环节。"
            ),
        },
        "reference_policy": (
            "只列出教师上传、已绑定或已确认的来源；"
            "没有可用来源时保持空缺，不编造书目、案例、数据或链接。"
        ),
    }


def compile_outline_prompt_contract(
    *,
    subject: str,
    audience: str,
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Build the formal-outline constraints consumed by the outline planner."""
    context = compile_formal_course_context({
        "course_name": subject,
        "target_audience": audience,
        "course_generation_brief": brief,
    })
    return {
        "schema_version": context["schema_version"],
        "confirmed_course_information": context["course_information"],
        "course_intro": context["course_intro"],
        "student_profile": context["student_profile"],
        "teaching_requirements": context["teaching_requirements"],
        "assessment_methods": context["assessment_methods"],
        "required_document_sections": context["outline_document_sections"],
        "objective_dimensions": context["objective_dimensions"],
        "reference_policy": context["reference_policy"],
        "integration_rules": [
            "确认的课程信息是只读输入，不得改写、换算或猜测缺失值",
            "当前模型只规划课程定位、目标和目录，正式文书由结构化真源确定性投影",
            "教学目标应为章节学习路径提供依据，不把正式大纲栏目复制到章节标题中",
        ],
    }


def project_lesson_objective_dimensions(
    section: dict[str, Any],
) -> dict[str, list[str]]:
    """Group existing lesson fields without creating another objective truth."""
    knowledge_capability = _text_list(
        section.get("learning_objective") or section.get("objective")
    )
    process_method: list[str] = []
    transfer_innovation: list[str] = []

    for group in section.get("knowledge_structure") or []:
        if not isinstance(group, dict):
            continue
        for knowledge in group.get("knowledge_points") or []:
            if not isinstance(knowledge, dict):
                continue
            for capability in knowledge.get("capability_points") or []:
                if not isinstance(capability, dict):
                    continue
                for item in _text_list(
                    capability.get("observable_behavior")
                    or capability.get("name")
                ):
                    if item not in knowledge_capability:
                        knowledge_capability.append(item)
            for criterion in knowledge.get("mastery_criteria") or []:
                if not isinstance(criterion, dict):
                    continue
                if str(criterion.get("required_transfer") or "") not in {
                    "variation",
                    "novel",
                }:
                    continue
                for item in _text_list(
                    criterion.get("observable_performance")
                    or criterion.get("name")
                ):
                    if item not in transfer_innovation:
                        transfer_innovation.append(item)

    process_candidates = _text_list(section.get("student_activities"))
    for module in section.get("teaching_modules") or []:
        if not isinstance(module, dict):
            continue
        process_candidates.extend(_text_list(module.get("student_activity")))
    for item in process_candidates:
        if item not in process_method:
            process_method.append(item)

    transfer_signals = ("迁移", "变式", "应用", "设计", "探究", "创新", "综合", "真实")
    for item in _text_list(section.get("homework")):
        if any(signal in item for signal in transfer_signals):
            if item not in transfer_innovation:
                transfer_innovation.append(item)

    return {
        label: values[:8]
        for label, values in (
            ("知识与能力", knowledge_capability),
            ("过程与方法", process_method),
            ("迁移与创新", transfer_innovation),
        )
        if values
    }


__all__ = [
    "FORMAL_AUTHORING_TEMPLATE_VERSION",
    "LESSON_PLAN_DOCUMENT_SECTIONS",
    "OBJECTIVE_DIMENSIONS",
    "OUTLINE_DOCUMENT_SECTIONS",
    "attach_formal_course_profile",
    "compile_formal_course_context",
    "compile_outline_prompt_contract",
    "project_lesson_objective_dimensions",
    "snapshot_formal_course_profile",
]
