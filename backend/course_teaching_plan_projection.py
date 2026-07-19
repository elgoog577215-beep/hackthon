"""User-safe projection for the whole-course teaching plan."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def _project_knowledge_structure(value: Any) -> list[dict[str, Any]]:
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
            points.append({
                "knowledge_id": str(
                    raw_point.get("knowledge_id") or ""
                ).strip(),
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


def project_course_teaching_plan(course_data: dict[str, Any]) -> dict[str, Any]:
    """Expose teaching intent without prompts, hidden reasoning, or diagnostics."""
    plan = course_data.get("course_teaching_plan")
    stage = (
        (course_data.get("generation_stage_artifacts") or {})
        .get("course_teaching_plan")
        or {}
    )
    sections = []
    if isinstance(plan, dict):
        for raw in plan.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            sections.append({
                "node_id": str(raw.get("node_id") or ""),
                "knowledge_structure": _project_knowledge_structure(
                    raw.get("knowledge_structure")
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
        "sections": sections,
    }
