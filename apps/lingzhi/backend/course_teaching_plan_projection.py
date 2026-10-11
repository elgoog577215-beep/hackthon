"""User-safe projection for the whole-course teaching plan."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_lesson_dossier import (
    build_lesson_dossier,
    build_lesson_dossier_consistency,
)
from teaching_design import compile_overall_teaching_guidance


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
                if normalized in index and index[normalized] != knowledge_id:
                    index[normalized] = ""
                else:
                    index.setdefault(normalized, knowledge_id)
    return index


def overlay_lesson_plan_sections(
    course_data: dict[str, Any], sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine current lesson plans for reading without writing either owner."""
    raw_plan = course_data.get("course_teaching_plan")
    plan = deepcopy(raw_plan) if isinstance(raw_plan, dict) else {}
    existing = (
        plan.get("sections")
        or (course_data.get("teaching_plan") or {}).get("sections")
        or []
    )
    by_id = {
        _text(section.get("node_id")): deepcopy(section)
        for section in existing if isinstance(section, dict) and section.get("node_id")
    }
    for section in sections:
        by_id[_text(section["node_id"])] = deepcopy(section)
    node_order = [_text(node.get("node_id")) for node in course_data.get("nodes") or []]
    ordered_ids = [node_id for node_id in node_order if node_id in by_id]
    ordered_ids.extend(node_id for node_id in by_id if node_id not in ordered_ids)
    plan["sections"] = [by_id[node_id] for node_id in ordered_ids]
    return plan


def _project_knowledge_structure(
    value: Any,
    *,
    knowledge_ids: dict[str, str],
    knowledge_names: dict[str, str],
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
                "revision_id": _text(raw_point.get("revision_id")),
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
                "relations": _project_knowledge_relations([
                    {**relation, "source_name": name, "source_knowledge_id": knowledge_id}
                    for relation in raw_point.get("relations") or []
                    if isinstance(relation, dict)
                ], knowledge_names=knowledge_names),
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


def _project_knowledge_relations(
    value: Any, *, knowledge_names: dict[str, str],
) -> list[dict[str, Any]]:
    relations = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        relations.append({
            "source_name": (
                _text(raw.get("source_name"))
                or knowledge_names.get(_text(raw.get("source_knowledge_id")), "")
            ),
            "target_name": (
                _text(raw.get("target_name"))
                or knowledge_names.get(_text(raw.get("target_knowledge_id")), "")
            ),
            "source_knowledge_id": _text(raw.get("source_knowledge_id")),
            "target_knowledge_id": _text(raw.get("target_knowledge_id")),
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
            "source_refs": deepcopy(raw.get("source_refs") or []),
            "relation_group_id": str(raw.get("relation_group_id") or ""),
            "group_operator": str(raw.get("group_operator") or ""),
        })
    return relations


def _project_teaching_modules(
    value: Any,
    *,
    module_plan: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """投影教学环节。

    `label` 与 `block_role` 来自小节冻结的 `module_plan`，不是模型自由发挥的标题。
    生成结果只带 `module_id` 时，页面上就只剩一串英文 id；把模板里的稳定栏目名一起
    带出来，各节的环节名称才会一致。
    """
    planned = module_plan or {}
    modules = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        module_id = str(raw.get("module_id") or "").strip()
        spec = planned.get(module_id) or {}
        modules.append({
            "module_id": module_id,
            "label": str(spec.get("label") or "").strip(),
            "block_role": str(spec.get("block_role") or "").strip(),
            "required": bool(spec.get("required")),
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


def project_course_teaching_plan(course_data: dict[str, Any]) -> dict[str, Any]:
    """Expose teaching intent without prompts, hidden reasoning, or diagnostics."""
    plan = course_data.get("course_teaching_plan")
    plan = plan if isinstance(plan, dict) else {}
    stage = (
        (course_data.get("generation_stage_artifacts") or {})
        .get("course_teaching_plan")
        or {}
    )
    knowledge_ids = _knowledge_id_index(course_data)
    knowledge_base = course_data.get("course_knowledge_base") or {}
    knowledge_base = knowledge_base if isinstance(knowledge_base, dict) else {}
    points = [point for section in (plan or {}).get("sections") or []
              if isinstance(section, dict)
              for group in section.get("knowledge_structure") or []
              if isinstance(group, dict)
              for point in group.get("knowledge_points") or []]
    knowledge_names = {
        _text(point.get("knowledge_id")): _text(point.get("name"))
        for point in [*(knowledge_base.get("knowledge_points") or []), *points]
        if isinstance(point, dict) and point.get("knowledge_id") and point.get("name")
    }
    global_relations = _project_knowledge_relations([
        *((plan or {}).get("knowledge_relations") or []),
        *(knowledge_base.get("relations") or []),
    ], knowledge_names=knowledge_names)
    course_plan = course_data.get("course_plan")
    course_plan = course_plan if isinstance(course_plan, dict) else {}
    outline_sections = {}
    for chapter in course_plan.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_title = _text(chapter.get("title"))
        for section in chapter.get("sections") or []:
            if isinstance(section, dict) and _text(section.get("node_id")):
                outline_sections[_text(section.get("node_id"))] = (
                    section,
                    chapter_title,
                )
    sections = []
    if isinstance(plan, dict):
        for raw in plan.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("node_id") or "")
            outline_section, chapter_title = outline_sections.get(node_id, ({}, ""))
            module_plan = [
                item for item in outline_section.get("module_plan") or []
                if isinstance(item, dict)
            ]
            structure = _project_knowledge_structure(
                raw.get("knowledge_structure"), knowledge_ids=knowledge_ids,
                knowledge_names=knowledge_names,
            )
            section_names = {
                point["name"] for group in structure for point in group["knowledge_points"]
            } | set(_strings(raw.get("reused_knowledge_names")))
            relations = _project_knowledge_relations(
                raw.get("knowledge_relations"), knowledge_names=knowledge_names,
            )
            # These edges already exist in the frozen course graph. Membership
            # only chooses which section displays them; it never infers an edge.
            for relation in global_relations:
                relevant = relation["source_name"] in section_names or relation["target_name"] in section_names
                if relevant and relation not in relations:
                    relations.append(deepcopy(relation))
            sections.append({
                "node_id": node_id,
                "lesson_archetype": deepcopy(
                    outline_section.get("lesson_archetype") or {}
                ),
                "knowledge_structure": structure,
                "key_points": _strings(raw.get("key_points")),
                "reused_knowledge_names": _strings(
                    raw.get("reused_knowledge_names")
                ),
                "knowledge_relations": relations,
                "teaching_modules": _project_teaching_modules(
                    raw.get("teaching_modules"),
                    module_plan={
                        module_id: item
                        for item in module_plan
                        if (module_id := _text(item.get("module_id")))
                    },
                ),
                "planned_minutes": raw.get("planned_minutes") if isinstance(raw.get("planned_minutes"), int) else None,
                "key_difficulties": _strings(raw.get("key_difficulties")),
                "teacher_activities": _strings(raw.get("teacher_activities")),
                "student_activities": _strings(raw.get("student_activities")),
                "resource_refs": _strings(raw.get("resource_refs")),
                "in_class_checks": _strings(raw.get("in_class_checks")),
                "homework": _strings(raw.get("homework")),
                "teaching_notes": _strings(raw.get("teaching_notes")),
                # 呈现层单独持有的编译上下文，只在下面构造 dossier 时使用。
                "_outline": (outline_section, chapter_title, module_plan),
            })

    overall = _project_overall_plan(course_data, sections=sections)
    lesson_minutes = (overall.get("classroom") or {}).get(
        "lesson_duration_minutes"
    )
    lesson_minutes = (
        lesson_minutes
        if isinstance(lesson_minutes, int) and not isinstance(lesson_minutes, bool)
        else None
    )
    minutes_basis = "course_default"
    if not lesson_minutes:
        # 教师没填统一课时长度时，用课程自己已声明的小节时长中位数兜底。
        # 不这样做，只有个别小节有时序、其余小节整栏空白——恰恰是要消除的颗粒度
        # 波动。取中位数而不是凭空定 45 分钟：数字来自这门课自己，且标明来源。
        declared = sorted(
            minutes
            for section in sections
            if isinstance(minutes := section.get("planned_minutes"), int)
            and not isinstance(minutes, bool)
            and minutes > 0
        )
        if declared:
            lesson_minutes = declared[len(declared) // 2]
            minutes_basis = "course_median"
    for index, section in enumerate(sections):
        outline_section, chapter_title, module_plan = section.pop("_outline")
        section["dossier"] = build_lesson_dossier(
            section,
            sequence=index + 1,
            node_title=_text(outline_section.get("title")),
            chapter_title=chapter_title,
            learning_objective=_text(outline_section.get("learning_objective")),
            lesson_archetype=section.get("lesson_archetype"),
            module_plan=module_plan,
            course_lesson_minutes=lesson_minutes,
            course_minutes_basis=minutes_basis,
        )

    from handout_knowledge_projection import project_handout_knowledge
    sections = project_handout_knowledge(course_data, sections)
    status = str(stage.get("status") or "")
    if not status:
        status = "completed" if sections else "pending"
    return {
        "schema_version": "course_teaching_plan_projection_v1",
        "status": status,
        "revision_id": _text(plan.get("revision_id")),
        "strategy": str(stage.get("strategy") or "single_whole_course_call"),
        "section_count": int(stage.get("section_count") or len(sections)),
        "knowledge_point_count": int(
            stage.get("knowledge_point_count") or 0
        ),
        "teaching_module_count": int(
            stage.get("teaching_module_count") or 0
        ),
        "overall": overall,
        "dossier_consistency": build_lesson_dossier_consistency([
            section["dossier"] for section in sections if "dossier" in section
        ]),
        "sections": sections,
    }
