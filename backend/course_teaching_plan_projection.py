"""User-safe projection for the whole-course teaching plan."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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
        })
    return modules


def _project_chapters(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    plan = course_data.get("course_plan")
    if not isinstance(plan, dict):
        return []
    chapters: list[dict[str, Any]] = []
    for chapter_index, raw_chapter in enumerate(plan.get("chapters") or [], start=1):
        if not isinstance(raw_chapter, dict):
            continue
        sections = [
            item
            for item in raw_chapter.get("sections") or []
            if isinstance(item, dict)
        ]
        chapters.append({
            "chapter_id": _text(
                raw_chapter.get("chapter_id")
                or raw_chapter.get("chapter_number")
                or f"chapter-{chapter_index}"
            ),
            "chapter_number": _text(
                raw_chapter.get("chapter_number") or chapter_index
            ),
            "title": _text(
                raw_chapter.get("title")
                or raw_chapter.get("chapter_title")
                or f"第 {chapter_index} 章"
            ),
            "learning_focus": _text(
                raw_chapter.get("learning_focus")
                or raw_chapter.get("learning_objective")
            ),
            "section_count": len(sections),
            "section_ids": [
                _text(item.get("node_id"))
                for item in sections
                if _text(item.get("node_id"))
            ],
        })
    return chapters


def _project_overall_plan(
    course_data: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = course_data.get("course_plan")
    plan = plan if isinstance(plan, dict) else {}
    request = course_data.get("generation_request")
    request = request if isinstance(request, dict) else {}
    pedagogy = course_data.get("subject_pedagogy_profile")
    pedagogy = pedagogy if isinstance(pedagogy, dict) else {}
    brief = course_data.get("course_generation_brief")
    brief = brief if isinstance(brief, dict) else {}

    knowledge_usage: dict[str, dict[str, Any]] = {}
    assessment_methods: list[str] = []
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
                for criterion in point.get("mastery_criteria") or []:
                    if not isinstance(criterion, dict):
                        continue
                    method = _text(
                        criterion.get("verification_method")
                        or criterion.get("verification")
                        or criterion.get("evidence")
                    )
                    if method and method not in assessment_methods:
                        assessment_methods.append(method)

    return {
        "course_title": _text(
            plan.get("course_title")
            or course_data.get("course_name")
        ),
        "positioning": _text(
            plan.get("positioning")
            or brief.get("goal")
        ),
        "target_audience": _text(
            request.get("target_audience")
            or course_data.get("target_audience")
        ),
        "learning_objectives": _strings(plan.get("learning_objectives")),
        "prerequisites": _strings(plan.get("prerequisites")),
        "teaching_strategy": {
            "primary_mode": _text(pedagogy.get("primary_mode")),
            "secondary_mode": _text(pedagogy.get("secondary_mode")),
            "rationale": _text(pedagogy.get("rationale")),
        },
        "assessment_methods": assessment_methods[:8],
        "chapters": _project_chapters(course_data),
        "knowledge_tags": sorted(
            knowledge_usage.values(),
            key=lambda item: (
                -int(item.get("section_count") or 0),
                _text(item.get("name")),
            ),
        ),
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
    sections = []
    if isinstance(plan, dict):
        for raw in plan.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            sections.append({
                "node_id": str(raw.get("node_id") or ""),
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
            })

    status = str(stage.get("status") or "")
    if not status:
        status = "completed" if sections else "pending"
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
        "overall": _project_overall_plan(
            course_data,
            sections=sections,
        ),
        "sections": sections,
    }
