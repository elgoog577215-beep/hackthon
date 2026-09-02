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


FORMAL_AUTHORING_TEMPLATE_VERSION = "formal_course_authoring_v5"

OUTLINE_DOCUMENT_SECTIONS = (
    "课程介绍",
    "教学目标",
    "课程要求",
    "教学内容及教学安排",
    "参考资料",
    "课程教学网站",
)

LESSON_PLAN_DOCUMENT_SECTIONS = (
    "本讲基本信息",
    "教学目标",
    "教学重点与难点",
    "本讲教学设计",
    "教学资料与活动记录",
)

OBJECTIVE_DIMENSIONS = (
    {
        "id": "knowledge",
        "label": "知识目标",
        "policy": "说明本讲需要理解、掌握或辨析的知识内容",
    },
    {
        "id": "ability",
        "label": "能力目标",
        "policy": "说明学生能够完成的分析、推导、实验、表达、设计或应用任务",
    },
    {
        "id": "education",
        "label": "育人目标",
        "policy": "只在课程内容确有价值判断、责任或规范要求时填写，不为补齐模板编造套话",
    },
)

OUTLINE_OBJECTIVE_DIMENSIONS = (
    {"id": "learning", "label": "学习目标", "policy": "说清学生要掌握的知识与能力"},
    {"id": "education", "label": "育人目标", "policy": "结合真实课程内容表达价值判断与责任，不空泛套话"},
    {"id": "measurable", "label": "可测量结果", "policy": "使用可观察行为、作品或评价证据说明达成标准"},
)

LESSON_FLOW_SECTIONS = (
    "课前准备（按需）",
    "课堂教学过程",
    "课程总结",
    "作业与拓展",
    "拓展阅读",
    "教学活动照片（教师课后补充）",
)

_PROFILE_FIELDS = (
    "english_name",
    "course_code",
    "course_category",
    "credits",
    "weekly_hours",
    "total_hours",
    "prerequisite_courses",
    "target_major",
    "target_grade",
    "weekday",
    "periods",
    "course_period_minutes",
    "active_week_start",
    "active_week_end",
    "week_range_mode",
    "schedule_slots",
    "planned_lecture_count",
    "default_location",
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
        "课程英文名称": _text(profile.get("english_name")),
        "课程代码": _text(profile.get("course_code")),
        "课程类别": _text(profile.get("course_category")),
        "学分": profile.get("credits"),
        "周学时": profile.get("weekly_hours"),
        "总学时": total_hours,
        "每课时时长": (
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
        "上课星期": _text(profile.get("weekday")),
        "上课节次": _text(profile.get("periods")),
        "上课地点": _text(profile.get("default_location")),
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
        "course_intro_zh": _text(effective_plan.get("course_intro_zh") or profile.get("course_intro")),
        "course_intro_en": _text(effective_plan.get("course_intro_en")),
        "positioning": _text(effective_plan.get("positioning")),
        "student_profile": class_profile,
        "learning_objectives": _text_list(
            effective_plan.get("learning_objectives")
            or profile.get("teaching_goals")
            or profile.get("course_goal")
        ),
        "education_objectives": _text_list(
            effective_plan.get("education_objectives")
            or effective_plan.get("育人目标")
        ),
        "measurable_outcomes": _text_list(
            effective_plan.get("measurable_outcomes")
            or effective_plan.get("measurable_objectives")
            or effective_plan.get("可测量成果")
        ),
        "prerequisites": _text_list(effective_plan.get("prerequisites") or profile.get("prerequisite_courses")),
        "teaching_methods": _text_list(
            effective_plan.get("teaching_methods")
            or effective_plan.get("teaching_method")
        ) or _text_list(
            _TEACHING_CONTEXT_LABELS.get(teaching_context, teaching_context)
        ),
        "teaching_requirements": list(dict.fromkeys(requirements)),
        "assessment_methods": list(dict.fromkeys(assessment_methods)),
        "references": _source_labels(course_data, effective_plan),
        "reference_books": _text_list(effective_plan.get("reference_books")),
        "reference_websites": _text_list(effective_plan.get("reference_websites")),
        "course_website": _text(effective_plan.get("course_website")),
        "ideology_cases": deepcopy(effective_plan.get("ideology_cases") or []),
        "outline_document_sections": list(OUTLINE_DOCUMENT_SECTIONS),
        "outline_objective_dimensions": [deepcopy(item) for item in OUTLINE_OBJECTIVE_DIMENSIONS],
        "lesson_plan_document_sections": list(LESSON_PLAN_DOCUMENT_SECTIONS),
        "objective_dimensions": [deepcopy(item) for item in OBJECTIVE_DIMENSIONS],
        "lesson_flow_contract": {
            "required_roles": list(LESSON_FLOW_SECTIONS),
            "classroom_block_fields": [
                "时长", "本块目标与内容", "教师活动", "学生活动", "课堂产出",
                "达成检查", "反馈与调整", "与前后块的衔接", "讲义与PPT对应关系",
            ],
            "discipline_patterns": {
                "math_formal": ["问题引入", "定义建立", "推导或证明", "例题与变式", "应用与检查"],
                "language_learning": ["语境输入", "理解与辨析", "语言操练", "真实表达", "反馈与修正"],
                "natural_science": ["现象或问题", "假设与方法", "实验或证据", "解释", "误差与边界"],
                "programming_engineering": ["任务与约束", "方案设计", "实现", "测试与调试", "复盘与迁移"],
            },
            "selection_rule": (
                "正式外壳保持稳定，课堂教学过程中的教学块按学科、本讲目标和课型动态选择；"
                "案例、讨论、实践不是所有课程的固定顺序。活动照片只能由教师课后补充，AI 必须保持空白。"
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
        "objective_dimensions": context["outline_objective_dimensions"],
        "schedule_contract": (
            "教学内容只按第1讲至第N讲平铺，不使用章、小节或1.1式编号；"
            "每讲用一段适中篇幅说明实际教学内容，并可附周次、目标、重难点、活动、作业与学时"
        ),
        "ideology_case_contract": "思政案例必须对应具体讲次、课程内容、育人目标和实施方式",
        "reference_policy": context["reference_policy"],
        "integration_rules": [
            "确认的课程信息是只读输入，不得改写、换算或猜测缺失值",
            "当前模型按老师模板规划课程介绍、教学目标、课程要求、讲次安排、参考资料与课程网站",
            "教学目标应为讲次学习路径提供依据，不把正式大纲栏目复制到讲次标题中",
            "讲次是教学安排中唯一的课程内容层级，不得在讲次下再生成小节目录",
        ],
    }


def project_lesson_objective_dimensions(
    section: dict[str, Any],
) -> dict[str, list[str]]:
    """Group existing lesson fields without creating another objective truth."""
    knowledge_objectives = _text_list(
        section.get("knowledge_objectives")
        or section.get("knowledge_objective")
        or section.get("learning_objective")
        or section.get("objective")
    )
    ability = _text_list(
        section.get("ability_objectives") or section.get("ability_objective")
    )
    education = _text_list(
        section.get("education_objectives")
        or section.get("education_objective")
        or section.get("education_goal")
        or section.get("ideology_goal")
    )

    # 已有正式目标时直接沿用。原子能力点属于知识与评价明细，再全部拼回
    # “教学目标”会形成十几个分号相连的系统报告，而不是真实教案语言。
    has_explicit_ability = bool(ability)
    for group in section.get("knowledge_structure") or []:
        if not isinstance(group, dict):
            continue
        for knowledge_point in group.get("knowledge_points") or []:
            if not isinstance(knowledge_point, dict):
                continue
            capabilities = (
                []
                if has_explicit_ability
                else knowledge_point.get("capability_points") or []
            )
            for capability in capabilities:
                if not isinstance(capability, dict):
                    continue
                for item in _text_list(
                    capability.get("observable_behavior")
                    or capability.get("name")
                ):
                    if item not in ability:
                        ability.append(item)

    process_candidates = _text_list(section.get("student_activities"))
    for module in section.get("teaching_modules") or []:
        if not isinstance(module, dict):
            continue
        process_candidates.extend(_text_list(module.get("student_activity")))
    for item in process_candidates:
        if item not in ability:
            ability.append(item)

    return {
        label: values[:3]
        for label, values in (
            ("知识目标", knowledge_objectives),
            ("能力目标", ability),
            ("育人目标", education),
        )
    }


__all__ = [
    "FORMAL_AUTHORING_TEMPLATE_VERSION",
    "LESSON_FLOW_SECTIONS",
    "LESSON_PLAN_DOCUMENT_SECTIONS",
    "OBJECTIVE_DIMENSIONS",
    "OUTLINE_OBJECTIVE_DIMENSIONS",
    "OUTLINE_DOCUMENT_SECTIONS",
    "attach_formal_course_profile",
    "compile_formal_course_context",
    "compile_outline_prompt_contract",
    "project_lesson_objective_dimensions",
    "snapshot_formal_course_profile",
]
