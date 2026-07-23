"""Deterministic teaching guidance shared by teacher views and generation prompts."""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []

    def item_text(item: Any) -> str:
        if isinstance(item, dict):
            for key in (
                "verification_method",
                "observable_performance",
                "criterion",
                "evidence",
                "description",
                "name",
            ):
                text = _text(item.get(key))
                if text:
                    return text
            return ""
        return _text(item)

    return list(dict.fromkeys(
        text
        for item in value
        if (text := item_text(item))
    ))[:limit]


def _records(value: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in value if isinstance(item, dict)
    ] if isinstance(value, list) else []


def _course_plan(
    course_data: dict[str, Any],
    plan: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(plan, dict):
        return plan
    value = course_data.get("course_plan")
    return value if isinstance(value, dict) else {}


def _assessment_methods(
    course_data: dict[str, Any],
    plan: dict[str, Any],
) -> list[str]:
    methods: list[str] = []

    def add(value: Any) -> None:
        text = _text(value)
        if text and text not in methods:
            methods.append(text)

    for chapter in _records(plan.get("chapters")):
        for section in _records(chapter.get("sections")):
            for item in section.get("assessment") or []:
                if isinstance(item, dict):
                    add(
                        item.get("verification_method")
                        or item.get("observable_performance")
                        or item.get("criterion")
                    )
                else:
                    add(item)

    teaching_plan = course_data.get("course_teaching_plan")
    if isinstance(teaching_plan, dict):
        for section in _records(teaching_plan.get("sections")):
            for group in _records(section.get("knowledge_structure")):
                for point in _records(group.get("knowledge_points")):
                    for criterion in _records(point.get("mastery_criteria")):
                        add(
                            criterion.get("verification_method")
                            or criterion.get("verification")
                            or criterion.get("observable_performance")
                        )
    return methods[:8]


def _chapters(plan: dict[str, Any]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(
        _records(plan.get("chapters")),
        start=1,
    ):
        sections = _records(chapter.get("sections"))
        chapter_number = _text(chapter.get("chapter_number") or index)
        chapters.append({
            "chapter_id": _text(
                chapter.get("chapter_id")
                or chapter.get("chapter_number")
                or f"chapter-{index}"
            ),
            "chapter_number": chapter_number,
            "title": _text(
                chapter.get("title")
                or chapter.get("chapter_title")
                or f"第 {chapter_number} 章"
            ),
            "learning_focus": _text(
                chapter.get("learning_focus")
                or chapter.get("learning_objective")
            ),
            "section_count": len(sections),
            "section_ids": [
                _text(section.get("node_id"))
                for section in sections
                if _text(section.get("node_id"))
            ],
        })
    return chapters


def compile_overall_teaching_guidance(
    course_data: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile the teacher-visible whole-course intent without another model call."""
    plan = _course_plan(course_data, plan)
    request = course_data.get("generation_request")
    request = request if isinstance(request, dict) else {}
    pedagogy = course_data.get("subject_pedagogy_profile")
    pedagogy = pedagogy if isinstance(pedagogy, dict) else {}
    brief = course_data.get("course_generation_brief")
    brief = brief if isinstance(brief, dict) else {}
    positioning = _text(
        plan.get("positioning")
        or brief.get("goal")
    )
    rationale = _text(pedagogy.get("rationale"))

    return {
        "course_title": _text(
            plan.get("course_title")
            or course_data.get("course_name")
        ),
        "positioning": positioning,
        "target_audience": _text(
            request.get("target_audience")
            or course_data.get("target_audience")
        ),
        "learning_objectives": _strings(
            plan.get("learning_objectives"),
            limit=8,
        ),
        "prerequisites": _strings(plan.get("prerequisites"), limit=8),
        "teaching_strategy": {
            "primary_mode": _text(pedagogy.get("primary_mode")),
            "secondary_mode": _text(pedagogy.get("secondary_mode")),
            "rationale": rationale,
        },
        "teaching_throughline": rationale or positioning,
        "assessment_methods": _assessment_methods(course_data, plan),
        "chapters": _chapters(plan),
    }


def compile_section_teaching_guidance(
    course_data: dict[str, Any],
    node: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Locate one section inside the whole-course progression."""
    plan = _course_plan(course_data, plan)
    node_id = _text(node.get("node_id"))
    ordered: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for chapter in _records(plan.get("chapters")):
        for section in _records(chapter.get("sections")):
            ordered.append((chapter, section))

    current_index = next((
        index
        for index, (_chapter, section) in enumerate(ordered)
        if _text(section.get("node_id")) == node_id
    ), -1)
    current_chapter: dict[str, Any] = {}
    current_section: dict[str, Any] = {}
    if current_index >= 0:
        current_chapter, current_section = ordered[current_index]

    def section_summary(index: int) -> str:
        if index < 0 or index >= len(ordered):
            return ""
        _chapter, section = ordered[index]
        title = _text(
            section.get("title")
            or section.get("node_name")
        )
        objective = _text(section.get("learning_objective"))
        return "：".join(item for item in (title, objective) if item)

    return {
        "node_id": node_id,
        "chapter_title": _text(
            current_chapter.get("title")
            or current_chapter.get("chapter_title")
        ),
        "chapter_learning_focus": _text(
            current_chapter.get("learning_focus")
            or current_chapter.get("learning_objective")
        ),
        "section_title": _text(
            current_section.get("title")
            or node.get("node_name")
        ),
        "section_objective": _text(
            current_section.get("learning_objective")
            or node.get("learning_objective")
        ),
        "scope_boundary": _text(
            current_section.get("scope_boundary")
            or node.get("scope_boundary")
        ),
        "assessment": _strings(
            current_section.get("assessment")
            or node.get("assessment"),
            limit=6,
        ),
        "handoff_from": section_summary(current_index - 1),
        "handoff_to": section_summary(current_index + 1),
    }


def format_generation_teaching_guidance(
    course_data: dict[str, Any],
    node: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    compact: bool = False,
) -> str:
    """Format the same teacher intent as a bounded generation instruction."""
    overall = compile_overall_teaching_guidance(course_data, plan=plan)
    section = compile_section_teaching_guidance(
        course_data,
        node,
        plan=plan,
    )
    objectives = overall["learning_objectives"][:3 if compact else 6]
    assessments = (
        section["assessment"]
        or overall["assessment_methods"]
    )[:3 if compact else 6]
    lines = [
        f"- 课程定位：{overall['positioning'] or '按已确认课程目标推进'}",
        f"- 总体成果：{'；'.join(objectives) or '完成当前课程的可观察学习成果'}",
        f"- 教学对象：{overall['target_audience'] or '按课程需求确定'}",
        f"- 学习起点：{'；'.join(overall['prerequisites']) or '无额外前置要求'}",
        f"- 教学主线：{overall['teaching_throughline'] or '从理解进入应用，并用可检查任务闭环'}",
        f"- 当前章节责任：{section['chapter_learning_focus'] or section['chapter_title'] or '推进当前阶段目标'}",
        f"- 本节责任：{section['section_objective'] or '完成当前小节目标'}",
        f"- 评价证据：{'；'.join(assessments) or '使用与本节目标一致的可检查任务'}",
    ]
    if not compact:
        lines.extend([
            f"- 从哪里来：{section['handoff_from'] or '课程起点'}",
            f"- 到哪里去：{section['handoff_to'] or '完成本阶段学习'}",
            f"- 范围边界：{section['scope_boundary'] or '只完成当前小节责任，不提前替代后续教学'}",
        ])
    return "\n".join(lines)


__all__ = [
    "compile_overall_teaching_guidance",
    "compile_section_teaching_guidance",
    "format_generation_teaching_guidance",
]
