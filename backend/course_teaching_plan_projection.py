"""User-safe projection for the whole-course teaching plan."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_teaching_guidance import compile_overall_teaching_guidance


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def _normalized_knowledge_name(value: Any) -> str:
    return "".join(_text(value).lower().split())


def _knowledge_id_index(course_data: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    knowledge_base = course_data.get("course_knowledge_base")
    if not isinstance(knowledge_base, dict):
        return index
    for raw_point in knowledge_base.get("knowledge_points") or []:
        if not isinstance(raw_point, dict):
            continue
        knowledge_id = _text(raw_point.get("knowledge_id"))
        names = [
            raw_point.get("name"),
            *(raw_point.get("aliases") or []),
        ]
        if not knowledge_id:
            continue
        for name in names:
            normalized = _normalized_knowledge_name(name)
            if normalized:
                index.setdefault(normalized, knowledge_id)
    return index


def _project_knowledge_structure(
    value: Any,
    *,
    knowledge_ids: dict[str, str],
) -> list[dict[str, Any]]:
    groups = []
    for raw_group in value if isinstance(value, list) else []:
        if not isinstance(raw_group, dict):
            continue
        points = []
        for raw_point in raw_group.get("knowledge_points") or []:
            if not isinstance(raw_point, dict):
                continue
            name = str(raw_point.get("name") or "").strip()
            if not name:
                continue
            knowledge_id = (
                str(raw_point.get("knowledge_id") or "").strip()
                or knowledge_ids.get(_normalized_knowledge_name(name), "")
            )
            points.append({
                "knowledge_id": knowledge_id,
                "knowledge_status": (
                    "bound" if knowledge_id else "awaiting_compilation"
                ),
                "name": name,
                "statement": str(
                    raw_point.get("statement") or ""
                ).strip(),
                "description": str(
                    raw_point.get("description") or ""
                ).strip(),
                "knowledge_type": str(
                    raw_point.get("knowledge_type") or ""
                ).strip(),
                "conditions": _strings(raw_point.get("conditions")),
                "boundaries": _strings(raw_point.get("boundaries")),
                "counterexamples": _strings(
                    raw_point.get("counterexamples")
                ),
                "capability": str(
                    raw_point.get("capability") or ""
                ).strip(),
                "capability_points": deepcopy(
                    raw_point.get("capability_points") or []
                ),
                "misconceptions": deepcopy(
                    raw_point.get("misconceptions") or []
                ),
                "mastery_criteria": deepcopy(
                    raw_point.get("mastery_criteria") or []
                ),
                "aliases": _strings(raw_point.get("aliases")),
                "prerequisite_names": _strings(
                    raw_point.get("prerequisite_names")
                ),
            })
        if not points:
            continue
        groups.append({
            "concept_group": str(
                raw_group.get("concept_group")
                or raw_group.get("topic")
                or ""
            ).strip(),
            "description": str(
                raw_group.get("description") or ""
            ).strip(),
            "knowledge_points": points,
        })
    return groups


def _project_knowledge_relations(value: Any) -> list[dict[str, Any]]:
    relations = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        relations.append({
            "source_name": str(raw.get("source_name") or "").strip(),
            "target_name": str(raw.get("target_name") or "").strip(),
            "relation_type": str(
                raw.get("relation_type") or ""
            ).strip(),
            "reason": str(raw.get("reason") or "").strip(),
            "conditions": _strings(raw.get("conditions")),
            "distinction": str(
                raw.get("distinction") or ""
            ).strip(),
            "derivation_steps": _strings(
                raw.get("derivation_steps")
            ),
            "necessity": str(raw.get("necessity") or "").strip(),
            "priority": str(raw.get("priority") or "").strip(),
        })
    return relations


def _project_teaching_modules(value: Any) -> list[dict[str, Any]]:
    modules = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        modules.append({
            "module_id": str(raw.get("module_id") or "").strip(),
            "teaching_purpose": str(
                raw.get("teaching_purpose") or ""
            ).strip(),
            "knowledge_names": _strings(
                raw.get("knowledge_names")
            ),
            "teaching_guidance": str(
                raw.get("teaching_guidance") or ""
            ).strip(),
            "planned_minutes": raw.get("planned_minutes") if isinstance(raw.get("planned_minutes"), int) else None,
            "teacher_activity": str(raw.get("teacher_activity") or "").strip(),
            "student_activity": str(raw.get("student_activity") or "").strip(),
        })
    return modules


def _project_overall_plan(
    course_data: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    overall = compile_overall_teaching_guidance(course_data)
    raw_course_plan = course_data.get("course_plan")
    raw_course_plan = (
        raw_course_plan
        if isinstance(raw_course_plan, dict)
        else {}
    )
    knowledge_usage: dict[str, dict[str, Any]] = {}
    for section in sections:
        seen_in_section: set[str] = set()
        for group in section.get("knowledge_structure") or []:
            for point in group.get("knowledge_points") or []:
                name = _text(point.get("name"))
                if not name:
                    continue
                normalized = _normalized_knowledge_name(name)
                entry = knowledge_usage.setdefault(normalized, {
                    "knowledge_id": _text(point.get("knowledge_id")),
                    "name": name,
                    "section_count": 0,
                })
                if not entry["knowledge_id"]:
                    entry["knowledge_id"] = _text(point.get("knowledge_id"))
                if normalized not in seen_in_section:
                    entry["section_count"] += 1
                    seen_in_section.add(normalized)
    return {
        **overall,
        "pedagogy_quality_contract": deepcopy(
            raw_course_plan.get(
                "pedagogy_quality_contract"
            )
            or {}
        ),
        "knowledge_tags": sorted(
            knowledge_usage.values(),
            key=lambda item: (
                -int(item.get("section_count") or 0),
                _text(item.get("name")),
            ),
        ),
    }


def _compile_formal_readiness(
    course_data: dict[str, Any],
    *,
    overall: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check whether the deterministic teacher document is deliverable."""
    issues: list[dict[str, Any]] = []

    def add(
        code: str,
        field: str,
        message: str,
        *,
        node_id: str = "",
        severity: str = "critical",
    ) -> None:
        issues.append({
            "code": code,
            "severity": severity,
            "scope": "section" if node_id else "course",
            "node_id": node_id,
            "field": field,
            "message": message,
        })

    for field, message in (
        ("course_title", "缺少正式教案名称"),
        ("positioning", "缺少课程定位"),
        ("target_audience", "缺少教学对象"),
    ):
        if not _text(overall.get(field)):
            add(f"formal_plan_missing_{field}", field, message)
    if not overall.get("learning_objectives"):
        add(
            "formal_plan_missing_objectives",
            "learning_objectives",
            "缺少可检查的总体教学目标",
        )

    classroom = overall.get("classroom") or {}
    for field, message in (
        ("total_class_hours", "缺少总课时"),
        ("lesson_duration_minutes", "缺少单课时时长"),
        ("teaching_context", "缺少授课场景"),
        ("class_profile", "缺少班级学情说明"),
    ):
        if not classroom.get(field):
            add(f"formal_plan_missing_{field}", field, message)
    if not classroom.get("teaching_preparation"):
        add(
            "formal_plan_missing_preparation",
            "teaching_preparation",
            "缺少课前准备",
            severity="major",
        )
    if not (
        overall.get("assessment_methods")
        or classroom.get("course_assessment_plan")
    ):
        add(
            "formal_plan_missing_assessment",
            "assessment_methods",
            "缺少课程评价安排",
        )

    course_plan = course_data.get("course_plan") or {}
    expected_ids = [
        _text(section.get("node_id"))
        for chapter in course_plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict) and _text(section.get("node_id"))
    ]
    actual_ids = {_text(section.get("node_id")) for section in sections}
    for node_id in expected_ids:
        if node_id not in actual_ids:
            add(
                "formal_plan_missing_section",
                "sections",
                "目录中的课时尚未进入正式教案",
                node_id=node_id,
            )
    if not sections:
        add(
            "formal_plan_empty_process",
            "sections",
            "缺少分课时教学过程",
        )

    for section in sections:
        node_id = _text(section.get("node_id"))
        planned = section.get("planned_minutes")
        if not isinstance(planned, int) or planned <= 0:
            add(
                "formal_plan_missing_lesson_duration",
                "planned_minutes",
                "课时缺少有效时长",
                node_id=node_id,
            )
        if not section.get("key_points"):
            add(
                "formal_plan_missing_key_points",
                "key_points",
                "课时缺少教学重点",
                node_id=node_id,
            )
        if not section.get("key_difficulties"):
            add(
                "formal_plan_missing_difficulties",
                "key_difficulties",
                "课时缺少教学难点",
                node_id=node_id,
            )
        if not section.get("in_class_checks"):
            add(
                "formal_plan_missing_checks",
                "in_class_checks",
                "课时缺少课堂评价证据",
                node_id=node_id,
            )
        if not section.get("homework"):
            add(
                "formal_plan_missing_homework",
                "homework",
                "课时缺少课后任务",
                node_id=node_id,
                severity="major",
            )
        modules = section.get("teaching_modules") or []
        if not modules:
            add(
                "formal_plan_missing_process_modules",
                "teaching_modules",
                "课时缺少可执行的教学环节",
                node_id=node_id,
            )
            continue
        module_minutes = 0
        module_minutes_complete = True
        for module in modules:
            minutes = module.get("planned_minutes")
            if not isinstance(minutes, int) or minutes <= 0:
                module_minutes_complete = False
            else:
                module_minutes += minutes
            if not _text(module.get("teacher_activity")):
                add(
                    "formal_plan_missing_teacher_activity",
                    "teaching_modules.teacher_activity",
                    "教学环节缺少教师活动",
                    node_id=node_id,
                )
            if not _text(module.get("student_activity")):
                add(
                    "formal_plan_missing_student_activity",
                    "teaching_modules.student_activity",
                    "教学环节缺少学生活动",
                    node_id=node_id,
                )
        if not module_minutes_complete:
            add(
                "formal_plan_missing_module_minutes",
                "teaching_modules.planned_minutes",
                "教学环节缺少时长",
                node_id=node_id,
            )
        elif isinstance(planned, int) and planned > 0 and module_minutes != planned:
            add(
                "formal_plan_duration_mismatch",
                "teaching_modules.planned_minutes",
                f"教学环节合计 {module_minutes} 分钟，与课时 {planned} 分钟不一致",
                node_id=node_id,
            )

    critical_count = sum(
        item["severity"] == "critical" for item in issues
    )
    major_count = sum(item["severity"] == "major" for item in issues)
    return {
        "schema_version": "formal_lesson_plan_readiness_v1",
        "status": "ready" if critical_count == 0 else "needs_completion",
        "ready_for_print": critical_count == 0,
        "critical_count": critical_count,
        "major_count": major_count,
        "issue_count": len(issues),
        "expected_section_count": len(expected_ids),
        "covered_section_count": len(set(expected_ids) & actual_ids),
        "issues": issues,
    }


def project_course_teaching_plan(course_data: dict[str, Any]) -> dict[str, Any]:
    """Expose teaching intent without prompts, hidden reasoning, or diagnostics."""
    plan = course_data.get("course_teaching_plan")
    stage = (
        (course_data.get("generation_stage_artifacts") or {})
        .get("course_teaching_plan")
        or {}
    )
    knowledge_ids = _knowledge_id_index(course_data)
    course_plan = course_data.get("course_plan")
    course_plan = course_plan if isinstance(course_plan, dict) else {}
    outline_sections = {
        _text(section.get("node_id")): section
        for chapter in course_plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict) and _text(section.get("node_id"))
    }
    sections = []
    if isinstance(plan, dict):
        for raw in plan.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("node_id") or "")
            outline_section = outline_sections.get(node_id) or {}
            sections.append({
                "node_id": node_id,
                "lesson_archetype": deepcopy(
                    outline_section.get("lesson_archetype") or {}
                ),
                "knowledge_structure": _project_knowledge_structure(
                    raw.get("knowledge_structure"),
                    knowledge_ids=knowledge_ids,
                ),
                "key_points": _strings(raw.get("key_points")),
                "reused_knowledge_names": _strings(
                    raw.get("reused_knowledge_names")
                ),
                "knowledge_relations": _project_knowledge_relations(
                    raw.get("knowledge_relations")
                ),
                "teaching_modules": _project_teaching_modules(
                    raw.get("teaching_modules")
                ),
                "planned_minutes": raw.get("planned_minutes") if isinstance(raw.get("planned_minutes"), int) else None,
                "key_difficulties": _strings(raw.get("key_difficulties")),
                "teacher_activities": _strings(raw.get("teacher_activities")),
                "student_activities": _strings(raw.get("student_activities")),
                "resource_refs": _strings(raw.get("resource_refs")),
                "in_class_checks": _strings(raw.get("in_class_checks")),
                "homework": _strings(raw.get("homework")),
                "teaching_notes": _strings(raw.get("teaching_notes")),
            })

    status = str(stage.get("status") or "")
    if not status:
        status = "completed" if sections else "pending"
    overall = _project_overall_plan(
        course_data,
        sections=sections,
    )
    return {
        "schema_version": "course_teaching_plan_projection_v1",
        "status": status,
        "revision_id": str(
            (plan or {}).get("revision_id")
            if isinstance(plan, dict)
            else ""
        ),
        "strategy": str(stage.get("strategy") or "single_whole_course_call"),
        "section_count": int(stage.get("section_count") or len(sections)),
        "knowledge_point_count": int(
            stage.get("knowledge_point_count") or 0
        ),
        "teaching_module_count": int(
            stage.get("teaching_module_count") or 0
        ),
        "overall": overall,
        "formal_readiness": _compile_formal_readiness(
            course_data,
            overall=overall,
            sections=sections,
        ),
        "sections": sections,
    }
