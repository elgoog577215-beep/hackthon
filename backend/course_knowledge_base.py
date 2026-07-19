"""Course-owned atomic knowledge, relation, and teaching-binding model."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from content_blocks import set_node_content_blocks
from course_knowledge_map import normalize_knowledge_structure
from course_versioning import stable_hash

COURSE_KNOWLEDGE_BASE_SCHEMA = "course_knowledge_base_v2"
COURSE_KNOWLEDGE_VIEW_SCHEMA = "knowledge_library_view_v3"

RELATION_TYPES = {
    "prerequisite",
    "derives",
    "equivalent_to",
    "contrasts_with",
    "applies_to",
    "generalizes",
}
SYMMETRIC_RELATION_TYPES = {"equivalent_to", "contrasts_with"}
KNOWLEDGE_TYPES = {
    "definition",
    "principle",
    "rule",
    "method",
    "condition",
    "representation",
    "procedure",
}
TEACHING_ROLES = {
    "introduces",
    "explains",
    "demonstrates",
    "reinforces",
    "practices",
    "assesses",
    "remediates",
    "extends",
}


def compile_course_knowledge_base(
    course_data: dict[str, Any],
    *,
    library: dict[str, Any] | None = None,
    course_map: dict[str, Any] | None = None,
    assets: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Compile one course's knowledge blueprint into the v2 product contract."""
    # Kept in the signature for persisted callers, but intentionally ignored:
    # knowledge identity never crosses a course boundary, and the compatibility
    # map is a downstream projection rather than an input to the knowledge base.
    del library, course_map
    for section in _sections(course_data):
        if (
            not section.get("content_blocks")
            and str(section.get("node_content") or "").strip()
        ):
            set_node_content_blocks(section, str(section.get("node_content") or ""))
    existing = course_data.get("course_knowledge_base")
    if isinstance(existing, dict):
        apply_persisted_course_knowledge_base(course_data, existing)
    course_id = str(course_data.get("course_id") or "")
    sections = _sections(course_data)
    section_by_id = {str(item.get("node_id") or ""): item for item in sections}
    practice_by_section = _practice_refs_by_section(assets or {})

    concept_groups: list[dict[str, Any]] = []
    knowledge_points: list[dict[str, Any]] = []
    skill_units: list[dict[str, Any]] = []
    misconceptions: list[dict[str, Any]] = []
    mastery_criteria: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    relation_candidates: list[dict[str, Any]] = []
    invalid_relation_candidates: list[dict[str, Any]] = []
    unresolved_relation_candidates: list[dict[str, Any]] = []
    unresolved_reuse_candidates: list[dict[str, Any]] = []

    point_by_name: dict[str, dict[str, Any]] = {}
    section_point_ids: dict[str, list[str]] = {}
    group_point_ids: dict[str, list[str]] = {}

    for section_order, section in enumerate(sections):
        section_id = str(section.get("node_id") or f"section-{section_order + 1}")
        section_name = _section_title(section)
        chapter_id = str(section.get("parent_node_id") or "")
        objective_refs = _unique([section.get("objective_id")])
        source_refs = _section_evidence_refs(section)
        practice_refs = practice_by_section.get(section_id, [])
        structures = normalize_knowledge_structure(section)
        section_ids: list[str] = []

        for group_order, raw_group in enumerate(structures):
            group_name = str(
                raw_group.get("concept_group")
                or raw_group.get("topic")
                or ""
            ).strip()
            if not group_name:
                continue
            group_id = _local_id(course_id, section_id, "concept_group", group_name, "ckg_")
            group = {
                "concept_group_id": group_id,
                "course_id": course_id,
                "name": group_name,
                "description": str(raw_group.get("description") or "").strip(),
                "primary_section_ref": section_id,
                "primary_chapter_ref": chapter_id,
                "section_name": section_name,
                "order": (section_order * 100) + group_order,
                "source_refs": source_refs,
                "status": "active",
            }
            group["revision_id"] = _revision_id(group, "ckgr_")
            concept_groups.append(group)
            group_point_ids[group_id] = []

            for point_order, raw_point in enumerate(raw_group.get("knowledge_points") or []):
                name = str(raw_point.get("name") or "").strip()
                statement = str(
                    raw_point.get("statement")
                    or raw_point.get("description")
                    or ""
                ).strip()
                if not name or not statement:
                    continue
                normalized_name = _normalize_name(name)
                existing = point_by_name.get(normalized_name)
                if existing:
                    point_id = str(existing["knowledge_id"])
                    existing["section_refs"] = _unique([*existing["section_refs"], section_id])
                    existing["objective_refs"] = _unique([*existing["objective_refs"], *objective_refs])
                    existing["source_refs"] = _unique([*existing["source_refs"], *source_refs])
                    existing["practice_refs"] = _unique([*existing["practice_refs"], *practice_refs])
                    existing["revision_id"] = _revision_id(existing, "ckpr_")
                    section_ids.append(point_id)
                    _append_binding(
                        bindings,
                        course_id=course_id,
                        knowledge_ids=[point_id],
                        skill_ids=_skills_for_point(skill_units, point_id),
                        target_type="section",
                        target_id=section_id,
                        teaching_role="reinforces",
                        importance="supporting",
                        source_refs=source_refs,
                        binding_method="explicit_reuse",
                    )
                    continue

                point_id = _local_id(course_id, group_id, "knowledge_point", name, "ckp_")
                knowledge_type = str(raw_point.get("knowledge_type") or "definition")
                if knowledge_type not in KNOWLEDGE_TYPES:
                    knowledge_type = "definition"
                point = {
                    "knowledge_id": point_id,
                    "course_id": course_id,
                    "primary_concept_group_id": group_id,
                    "knowledge_type": knowledge_type,
                    "name": name,
                    "statement": statement,
                    "conditions": _unique(raw_point.get("conditions") or []),
                    "boundaries": _unique(raw_point.get("boundaries") or []),
                    "counterexamples": _unique(raw_point.get("counterexamples") or []),
                    "aliases": _unique(raw_point.get("aliases") or []),
                    "entry_reason": str(raw_point.get("entry_reason") or "").strip(),
                    "source_refs": source_refs,
                    "section_refs": [section_id],
                    "objective_refs": objective_refs,
                    "course_block_refs": [],
                    "declared_block_refs": _unique(raw_point.get("content_block_refs") or []),
                    "practice_refs": practice_refs,
                    "reference_suggestions": [],
                    "granularity_status": "atomic" if _point_has_required_content(raw_point) else "needs_review",
                    "order": point_order,
                    "status": "active",
                }
                point["revision_id"] = _revision_id(point, "ckpr_")
                knowledge_points.append(point)
                point_by_name[normalized_name] = point
                group_point_ids[group_id].append(point_id)
                section_ids.append(point_id)

                point_skills = _compile_skills(course_id, point, raw_point, section_id, source_refs)
                skill_units.extend(point_skills)
                point_skill_ids = [str(item["skill_id"]) for item in point_skills]
                misconceptions.extend(
                    _compile_misconceptions(
                        course_id,
                        point,
                        raw_point,
                        point_skill_ids,
                        section_id,
                        source_refs,
                    )
                )
                mastery_criteria.extend(
                    _compile_mastery_criteria(
                        course_id,
                        point,
                        raw_point,
                        point_skill_ids,
                        section_id,
                        source_refs,
                    )
                )
                _append_binding(
                    bindings,
                    course_id=course_id,
                    knowledge_ids=[point_id],
                    skill_ids=point_skill_ids,
                    target_type="section",
                    target_id=section_id,
                    teaching_role="introduces",
                    importance="primary",
                    source_refs=source_refs,
                    binding_method="knowledge_blueprint",
                )
                for prerequisite_name in raw_point.get("prerequisite_names") or []:
                    relation_candidates.append({
                        "source_name": str(prerequisite_name),
                        "target_name": name,
                        "relation_type": "prerequisite",
                        "reason": f"{prerequisite_name} 是独立学习 {name} 所需的前置知识",
                        "necessity": "required",
                        "priority": "core",
                    })
                for relation in raw_point.get("relations") or []:
                    relation_candidates.append({
                        **deepcopy(relation),
                        "source_name": name,
                    })

        for reused_name in _unique(section.get("reused_knowledge_names") or []):
            existing = point_by_name.get(_normalize_name(reused_name))
            if not existing:
                unresolved_reuse_candidates.append({
                    "section_id": section_id,
                    "knowledge_name": reused_name,
                })
                continue
            point_id = str(existing["knowledge_id"])
            existing["section_refs"] = _unique([*existing["section_refs"], section_id])
            existing["objective_refs"] = _unique([*existing["objective_refs"], *objective_refs])
            existing["source_refs"] = _unique([*existing["source_refs"], *source_refs])
            existing["practice_refs"] = _unique([*existing["practice_refs"], *practice_refs])
            existing["revision_id"] = _revision_id(existing, "ckpr_")
            section_ids.append(point_id)
            _append_binding(
                bindings,
                course_id=course_id,
                knowledge_ids=[point_id],
                skill_ids=_skills_for_point(skill_units, point_id),
                target_type="section",
                target_id=section_id,
                teaching_role="reinforces",
                importance="supporting",
                source_refs=source_refs,
                binding_method="explicit_knowledge_reuse",
            )

        section_point_ids[section_id] = _unique(section_ids)

    point_by_id = {
        str(item.get("knowledge_id") or ""): item
        for item in knowledge_points
        if str(item.get("knowledge_id") or "")
    }
    relation_decisions = _compile_relation_decisions(
        course_data,
        point_by_id,
    )
    for decision in relation_decisions:
        point = point_by_id.get(str(decision.get("knowledge_id") or ""))
        if not point:
            continue
        point["relation_state"] = decision.get("decision")
        point["relation_decision_reason"] = decision.get("reason")
        if decision.get("decision") == "course_entry":
            point["entry_reason"] = str(decision.get("reason") or "").strip()
        point["revision_id"] = _revision_id(point, "ckpr_")

    relation_candidates.extend(
        item for item in course_data.get("knowledge_relations") or []
        if isinstance(item, dict)
    )
    relations = _compile_relations(
        course_id,
        relation_candidates,
        point_by_name,
        point_by_id,
        invalid_relation_candidates,
        unresolved_relation_candidates,
    )

    _compile_course_object_bindings(
        course_id,
        sections,
        section_point_ids,
        knowledge_points,
        skill_units,
        mastery_criteria,
        bindings,
        assets or {},
    )
    _backfill_point_block_refs(knowledge_points, bindings)
    valid_block_ids = {
        str(block.get("block_id") or block.get("content_block_id") or "")
        for section in sections
        for block in section.get("content_blocks") or []
        if str(block.get("block_id") or block.get("content_block_id") or "")
    }
    invalid_block_ref_candidates = [
        {"knowledge_id": point.get("knowledge_id"), "block_id": block_id}
        for point in knowledge_points
        for block_id in point.get("declared_block_refs") or []
        if block_id not in valid_block_ids
    ]

    payload: dict[str, Any] = {
        "schema_version": COURSE_KNOWLEDGE_BASE_SCHEMA,
        "knowledge_base_id": stable_hash(
            {"course": course_id, "kind": "course_knowledge_base_v2"},
            prefix="ckb_",
        ),
        "course_id": course_id,
        "concept_groups": concept_groups,
        "knowledge_points": knowledge_points,
        "skill_units": skill_units,
        "misconceptions": misconceptions,
        "mastery_criteria": mastery_criteria,
        "relation_plan_schema_version": (
            course_data.get("knowledge_relation_schema_version")
            or (course_data.get("course_plan") or {}).get(
                "knowledge_relation_schema_version"
            )
        ),
        "relation_decisions": relation_decisions,
        "relations": _dedupe_relations(relations),
        "bindings": _dedupe_bindings(bindings),
        "source_refs": _unique([
            course_data.get("blueprint_revision_id"),
            (course_data.get("course_blueprint") or {}).get("revision_id"),
        ]),
        "reference_catalog": {
            "library_id": None,
            "revision_id": None,
            "role": "disabled_cross_course_reference",
            "required": False,
        },
        "generation_audit": {
            "invalid_relation_candidates": invalid_relation_candidates,
            "unresolved_relation_candidates": unresolved_relation_candidates,
            "unresolved_reuse_candidates": unresolved_reuse_candidates,
            "invalid_block_ref_candidates": invalid_block_ref_candidates,
            "title_fallback_used": False,
            "legacy_outline_sections": [
                section_id
                for section_id, section in section_by_id.items()
                if section.get("knowledge_structure_status") == "needs_enrichment"
            ],
        },
        "lifecycle_status": "candidate",
        "created_from": "course_blueprint",
        "source_course_fingerprint": course_knowledge_source_fingerprint(course_data),
    }
    _attach_compatibility_projection(payload, section_point_ids, group_point_ids)
    payload["revision_id"] = _revision_id(payload, "ckbr_")
    quality = validate_course_knowledge_base(payload, course_data=course_data, library={})
    payload["quality_report"] = quality
    # ``active`` means the knowledge base is structurally usable by the course.
    # Non-blocking quality suggestions stay visible in the report but no longer
    # downgrade the whole course or stop content generation.
    payload["lifecycle_status"] = "active" if quality["passed"] else "degraded"
    payload["status"] = payload["lifecycle_status"]
    if quality["passed"]:
        for relation in payload["relations"]:
            relation["status"] = "accepted"
            relation["revision_id"] = _revision_id(relation, "ckrelr_")
    payload["revision_id"] = _revision_id(payload, "ckbr_")
    return payload


def course_knowledge_source_fingerprint(course_data: dict[str, Any]) -> str:
    """Hash course semantics while excluding the knowledge projection itself."""
    sections = []
    for section in _sections(course_data):
        blocks = list(section.get("content_blocks") or [])
        canonical_content = str(section.get("node_content") or "").strip()
        if not canonical_content:
            canonical_content = "\n\n".join(
                str(block.get("content") or block.get("markdown") or "").strip()
                for block in blocks
                if str(block.get("content") or block.get("markdown") or "").strip()
            )
        sections.append({
            "section_id": str(section.get("node_id") or ""),
            "parent_node_id": str(section.get("parent_node_id") or ""),
            "path_order": int(section.get("node_order") or section.get("order") or 0),
            "title": _section_title(section),
            "learning_objective": str(section.get("learning_objective") or ""),
            "assessment": _unique(section.get("assessment") or []),
            "scope_boundary": str(section.get("scope_boundary") or ""),
            "content": canonical_content,
        })
    return stable_hash(
        {"course_id": str(course_data.get("course_id") or ""), "sections": sections},
        prefix="cksrc_",
    )


def apply_persisted_course_knowledge_base(
    course_data: dict[str, Any],
    knowledge_base: dict[str, Any],
) -> bool:
    """Hydrate the course projection from an active CKB when content is unchanged."""
    if (
        knowledge_base.get("schema_version") != COURSE_KNOWLEDGE_BASE_SCHEMA
        or knowledge_base.get("lifecycle_status") != "active"
        or knowledge_base.get("source_course_fingerprint")
        != course_knowledge_source_fingerprint(course_data)
    ):
        return False

    sections_by_id = {
        str(section.get("node_id") or ""): section
        for section in _sections(course_data)
    }
    for section in sections_by_id.values():
        section["reused_knowledge_names"] = []
    points_by_id = {
        str(point.get("knowledge_id") or ""): point
        for point in knowledge_base.get("knowledge_points") or []
    }
    point_names = {
        point_id: str(point.get("name") or "")
        for point_id, point in points_by_id.items()
    }
    skills_by_point: dict[str, list[dict[str, Any]]] = {}
    for item in knowledge_base.get("skill_units") or []:
        skills_by_point.setdefault(str(item.get("primary_knowledge_id") or ""), []).append(item)
    mistakes_by_point: dict[str, list[dict[str, Any]]] = {}
    for item in knowledge_base.get("misconceptions") or []:
        mistakes_by_point.setdefault(str(item.get("primary_knowledge_id") or ""), []).append(item)
    criteria_by_point: dict[str, list[dict[str, Any]]] = {}
    for item in knowledge_base.get("mastery_criteria") or []:
        for point_id in item.get("knowledge_ids") or []:
            criteria_by_point.setdefault(str(point_id), []).append(item)
    relations_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in knowledge_base.get("relations") or []:
        relations_by_source.setdefault(str(item.get("source_knowledge_id") or ""), []).append(item)

    hydrated_sections: set[str] = set()
    for group in sorted(knowledge_base.get("concept_groups") or [], key=lambda item: int(item.get("order") or 0)):
        section_id = str(group.get("primary_section_ref") or "")
        section = sections_by_id.get(section_id)
        if not section:
            continue
        raw_group = {
            "concept_group": str(group.get("name") or ""),
            "topic": str(group.get("name") or ""),
            "description": str(group.get("description") or ""),
            "knowledge_points": [],
        }
        points = [
            point for point in knowledge_base.get("knowledge_points") or []
            if str(point.get("primary_concept_group_id") or "")
            == str(group.get("concept_group_id") or "")
        ]
        for point in sorted(points, key=lambda item: int(item.get("order") or 0)):
            point_id = str(point.get("knowledge_id") or "")
            raw_group["knowledge_points"].append({
                "name": str(point.get("name") or ""),
                "statement": str(point.get("statement") or ""),
                "description": str(point.get("statement") or ""),
                "knowledge_type": str(point.get("knowledge_type") or "definition"),
                "conditions": deepcopy(point.get("conditions") or []),
                "boundaries": deepcopy(point.get("boundaries") or []),
                "counterexamples": deepcopy(point.get("counterexamples") or []),
                "aliases": deepcopy(point.get("aliases") or []),
                "entry_reason": str(point.get("entry_reason") or ""),
                "content_block_refs": deepcopy(point.get("course_block_refs") or []),
                "capability_points": [{
                    "name": str(item.get("name") or ""),
                    "observable_behavior": str(item.get("observable_behavior") or ""),
                    "required_evidence_types": deepcopy(item.get("required_evidence_types") or []),
                } for item in skills_by_point.get(point_id, [])],
                "misconceptions": [{
                    "name": str(item.get("name") or ""),
                    "observable_error_pattern": str(item.get("observable_error_pattern") or ""),
                    "confused_with": str(item.get("confused_with") or ""),
                    "discrimination": str(item.get("discrimination") or ""),
                    "repair_strategy": str(item.get("repair_strategy") or ""),
                } for item in mistakes_by_point.get(point_id, [])],
                "mastery_criteria": [{
                    "name": str(item.get("name") or ""),
                    "observable_performance": str(item.get("observable_performance") or ""),
                    "required_independence": str(item.get("required_independence") or "independent"),
                    "required_transfer": str(item.get("required_transfer") or "variation"),
                    "verification_method": str(item.get("verification_method") or ""),
                    "required_evidence_types": deepcopy(item.get("required_evidence_types") or []),
                } for item in criteria_by_point.get(point_id, [])],
                "relations": [{
                    "target_name": point_names.get(str(item.get("target_knowledge_id") or ""), ""),
                    "relation_type": str(item.get("relation_type") or ""),
                    "reason": str(item.get("reason") or ""),
                    "conditions": deepcopy(item.get("conditions") or []),
                    "distinction": str(item.get("distinction") or ""),
                    "derivation_steps": deepcopy(item.get("derivation_steps") or []),
                    "relation_group_id": item.get("relation_group_id"),
                    "group_operator": item.get("group_operator"),
                    "necessity": item.get("necessity"),
                    "priority": item.get("priority"),
                } for item in relations_by_source.get(point_id, [])],
            })
        if not raw_group["knowledge_points"]:
            continue
        if section_id not in hydrated_sections:
            section["knowledge_structure"] = []
            hydrated_sections.add(section_id)
        section["knowledge_structure"].append(raw_group)

    primary_section_by_point = {
        str(point.get("knowledge_id") or ""): str(
            next(
                (
                    group.get("primary_section_ref")
                    for group in knowledge_base.get("concept_groups") or []
                    if str(group.get("concept_group_id") or "")
                    == str(point.get("primary_concept_group_id") or "")
                ),
                "",
            )
        )
        for point in knowledge_base.get("knowledge_points") or []
    }
    for point in knowledge_base.get("knowledge_points") or []:
        point_id = str(point.get("knowledge_id") or "")
        primary_section_id = primary_section_by_point.get(point_id, "")
        for raw_section_id in point.get("section_refs") or []:
            section_id = str(raw_section_id)
            section = sections_by_id.get(section_id)
            if not section or section_id == primary_section_id:
                continue
            section["reused_knowledge_names"] = _unique([
                *section.get("reused_knowledge_names", []),
                point.get("name"),
            ])

    for section_id in hydrated_sections:
        section = sections_by_id[section_id]
        section["knowledge_structure_status"] = "structured"
        section["key_points"] = [
            str(point.get("name") or "")
            for group in section.get("knowledge_structure") or []
            for point in group.get("knowledge_points") or []
        ]
    return bool(hydrated_sections)


def validate_course_knowledge_base(
    knowledge_base: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
    library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply hard structural, semantic, relation, and binding gates."""
    del library  # Optional reference catalogs never participate in product validity.
    issues: list[dict[str, Any]] = []
    if knowledge_base.get("schema_version") != COURSE_KNOWLEDGE_BASE_SCHEMA:
        issues.append(_issue("invalid_schema", "structure", "critical", "课程知识库格式不是 v2"))

    groups = list(knowledge_base.get("concept_groups") or [])
    points = list(knowledge_base.get("knowledge_points") or [])
    skills = list(knowledge_base.get("skill_units") or [])
    mistakes = list(knowledge_base.get("misconceptions") or [])
    criteria = list(knowledge_base.get("mastery_criteria") or [])
    relation_decisions = list(
        knowledge_base.get("relation_decisions") or []
    )
    relations = list(knowledge_base.get("relations") or [])
    bindings = list(knowledge_base.get("bindings") or [])

    if not groups and not points:
        issues.append(_issue(
            "knowledge_blueprint_missing",
            "structure",
            "critical",
            "知识库缺少有效的概念组和知识点，请重新生成",
        ))

    _validate_unique_ids(groups, "concept_group_id", "概念组", issues)
    _validate_unique_ids(points, "knowledge_id", "知识点", issues)
    _validate_unique_ids(skills, "skill_id", "能力点", issues)
    _validate_unique_ids(mistakes, "misconception_id", "易错点", issues, allow_empty=True)
    _validate_unique_ids(criteria, "criterion_id", "掌握标准", issues)
    _validate_unique_ids(relations, "relation_id", "知识关系", issues)
    _validate_unique_ids(bindings, "binding_id", "教学绑定", issues)

    group_ids = {str(item.get("concept_group_id") or "") for item in groups}
    point_ids = {str(item.get("knowledge_id") or "") for item in points}
    section_titles = {
        str(item.get("node_id") or ""): _normalize_outline_name(_section_title(item))
        for item in _sections(course_data or {})
    }

    for group in groups:
        group_id = str(group.get("concept_group_id") or "")
        section_id = str(group.get("primary_section_ref") or "")
        if not section_id:
            issues.append(_issue("group_missing_section", "structure", "critical", f"概念组 {group_id} 没有主要小节"))
        if _normalize_outline_name(group.get("name")) == section_titles.get(section_id):
            issues.append(_issue("group_mirrors_section", "semantic", "major", f"概念组「{group.get('name')}」复制了小节标题，建议在确认时优化名称"))
        owned = [item for item in points if item.get("primary_concept_group_id") == group_id]
        if len(owned) < 2:
            issues.append(_issue("group_too_small", "granularity", "major", f"概念组「{group.get('name')}」少于两个原子知识点"))

    normalized_names: set[str] = set()
    for point in points:
        point_id = str(point.get("knowledge_id") or "")
        name = str(point.get("name") or "").strip()
        normalized_name = _normalize_name(name)
        if normalized_name in normalized_names:
            issues.append(_issue("duplicate_point_identity", "semantic", "critical", f"知识点「{name}」存在重复身份"))
        normalized_names.add(normalized_name)
        if str(point.get("primary_concept_group_id") or "") not in group_ids:
            issues.append(_issue("point_missing_group", "structure", "critical", f"知识点「{name}」没有合法概念组"))
        if not str(point.get("statement") or "").strip():
            issues.append(_issue("point_missing_statement", "granularity", "critical", f"知识点「{name}」只有名称，没有知识陈述"))
        if point.get("knowledge_type") not in KNOWLEDGE_TYPES:
            issues.append(_issue("invalid_knowledge_type", "semantic", "critical", f"知识点「{name}」的类型不合法"))
        if not point.get("conditions") and not point.get("boundaries"):
            issues.append(_issue("point_missing_boundary", "granularity", "major", f"知识点「{name}」没有条件或边界"))
        if not point.get("section_refs"):
            issues.append(_issue("point_missing_path", "coverage", "critical", f"知识点「{name}」没有课程路径"))
        if any(_normalize_outline_name(name) == section_titles.get(section_id) for section_id in point.get("section_refs") or []):
            issues.append(_issue("point_mirrors_section", "semantic", "major", f"知识点「{name}」复制了小节标题，建议在确认时优化名称"))
        if point.get("granularity_status") != "atomic":
            issues.append(_issue("point_not_atomic", "granularity", "major", f"知识点「{name}」的细化信息不完整"))

    skills_by_point: dict[str, list[dict[str, Any]]] = {}
    for skill in skills:
        point_id = str(skill.get("primary_knowledge_id") or "")
        skills_by_point.setdefault(point_id, []).append(skill)
        if point_id not in point_ids:
            issues.append(_issue("skill_missing_point", "structure", "critical", f"能力点「{skill.get('name')}」没有合法知识点"))
        behavior = str(skill.get("observable_behavior") or "").strip()
        if not behavior or _is_unobservable_behavior(behavior):
            issues.append(_issue("skill_not_observable", "standards", "critical", f"能力点「{skill.get('name')}」不是可观察行为"))
    for point in points:
        if not skills_by_point.get(str(point.get("knowledge_id") or "")):
            issues.append(_issue("point_missing_skill", "standards", "major", f"知识点「{point.get('name')}」没有能力点"))

    criteria_by_point: dict[str, list[dict[str, Any]]] = {}
    for criterion in criteria:
        knowledge_ids = _unique(criterion.get("knowledge_ids") or [])
        for point_id in knowledge_ids:
            criteria_by_point.setdefault(point_id, []).append(criterion)
        if not knowledge_ids or set(knowledge_ids) - point_ids:
            issues.append(_issue("criterion_missing_point", "structure", "critical", f"掌握标准「{criterion.get('name')}」引用了无效知识点"))
        if not str(criterion.get("observable_performance") or "").strip():
            issues.append(_issue("criterion_not_observable", "standards", "critical", f"掌握标准「{criterion.get('name')}」不可验证"))
        if not str(criterion.get("verification_method") or "").strip():
            issues.append(_issue("criterion_missing_verification", "standards", "critical", f"掌握标准「{criterion.get('name')}」没有验证方式"))
    for point in points:
        if not criteria_by_point.get(str(point.get("knowledge_id") or "")):
            issues.append(_issue("point_missing_mastery", "standards", "major", f"知识点「{point.get('name')}」没有掌握标准"))

    for mistake in mistakes:
        if str(mistake.get("primary_knowledge_id") or "") not in point_ids:
            issues.append(_issue("misconception_missing_point", "structure", "critical", f"易错点「{mistake.get('name')}」没有合法知识点"))
        required = ("observable_error_pattern", "discrimination", "repair_strategy")
        if any(not str(mistake.get(field) or "").strip() for field in required):
            issues.append(_issue("misconception_is_template", "standards", "critical", f"易错点「{mistake.get('name')}」缺少错误表现、辨别或修复方法"))

    inbound: set[str] = set()
    relation_signatures: set[tuple[str, str, str]] = set()
    for relation in relations:
        source = str(relation.get("source_knowledge_id") or "")
        target = str(relation.get("target_knowledge_id") or "")
        relation_type = str(relation.get("relation_type") or "")
        if source not in point_ids or target not in point_ids or source == target:
            issues.append(_issue("invalid_relation_endpoint", "relations", "critical", "知识关系存在无效端点或自环"))
            continue
        if relation_type not in RELATION_TYPES:
            issues.append(_issue("invalid_relation_type", "relations", "critical", f"不允许关系类型 {relation_type}"))
        if not str(relation.get("reason") or "").strip():
            issues.append(_issue("relation_missing_reason", "relations", "critical", "知识关系缺少具体理由"))
        if relation_type == "contrasts_with" and not str(relation.get("distinction") or "").strip():
            issues.append(_issue("contrast_missing_distinction", "relations", "critical", "对比关系缺少判别维度"))
        if relation_type == "derives" and not relation.get("derivation_steps"):
            issues.append(_issue("derivation_missing_steps", "relations", "critical", "推导关系缺少关键步骤"))
        signature = (source, target, relation_type)
        if signature in relation_signatures:
            issues.append(_issue("duplicate_relation", "relations", "critical", "知识关系语义签名重复"))
        relation_signatures.add(signature)
        inbound.add(target)
        if relation_type in SYMMETRIC_RELATION_TYPES:
            inbound.add(source)
    if knowledge_base.get("relation_plan_schema_version"):
        decision_ids: set[str] = set()
        for decision in relation_decisions:
            knowledge_id = str(decision.get("knowledge_id") or "")
            if (
                knowledge_id not in point_ids
                or knowledge_id in decision_ids
                or decision.get("decision")
                not in {"connected", "course_entry"}
                or not str(decision.get("reason") or "").strip()
            ):
                issues.append(_issue(
                    "invalid_relation_decision",
                    "relations",
                    "critical",
                    "知识关系规划决定存在无效 ID、重复项或缺失理由",
                ))
                continue
            decision_ids.add(knowledge_id)
            if (
                decision.get("decision") == "connected"
                and knowledge_id not in inbound
            ):
                issues.append(_issue(
                    "connected_point_missing_relation",
                    "relations",
                    "critical",
                    f"知识点 {knowledge_id} 被标记为已连接，但没有正式关系入边",
                ))
        if decision_ids != point_ids:
            issues.append(_issue(
                "incomplete_relation_decisions",
                "relations",
                "critical",
                "全课关系规划没有逐一处理所有知识点",
            ))
    for relation_type in ("prerequisite", "generalizes"):
        cycle = _find_relation_cycle(relations, relation_type)
        if cycle:
            issues.append(_issue(f"{relation_type}_cycle", "relations", "major", f"{relation_type} 关系存在循环，建议后续优化：{' -> '.join(cycle)}"))
    for point in points:
        point_id = str(point.get("knowledge_id") or "")
        if point_id not in inbound and not str(point.get("entry_reason") or "").strip():
            issues.append(_issue("point_missing_inbound_or_entry", "relations", "major", f"知识点「{point.get('name')}」尚未说明为何从这里开始学习"))

    if (knowledge_base.get("generation_audit") or {}).get("invalid_relation_candidates"):
        issues.append(_issue("invalid_relation_candidates", "relations", "major", "已忽略六类白名单之外的知识关系候选"))
    if (knowledge_base.get("generation_audit") or {}).get("unresolved_relation_candidates"):
        issues.append(_issue("unresolved_relation_endpoints", "relations", "major", "已忽略端点无法解析的知识关系候选"))
    if (knowledge_base.get("generation_audit") or {}).get("unresolved_reuse_candidates"):
        issues.append(_issue("unresolved_knowledge_reuse", "bindings", "major", "部分复用知识尚未在当前课程中定义，已保留为优化建议"))
    if (knowledge_base.get("generation_audit") or {}).get("invalid_block_ref_candidates"):
        issues.append(_issue("invalid_declared_block_refs", "bindings", "major", "已忽略当前课程中不存在的正文块引用"))

    section_ids = {str(item.get("node_id") or "") for item in _sections(course_data or {})}
    bound_sections = {
        str(binding.get("target_id") or "")
        for binding in bindings
        if binding.get("target_type") == "section" and binding.get("knowledge_ids")
    }
    missing_section_count = len(section_ids - bound_sections)
    if missing_section_count:
        issues.append(_issue(
            "missing_section_bindings",
            "bindings",
            "critical",
            f"还有 {missing_section_count} 个课程小节尚未建立知识映射",
        ))
    for binding in bindings:
        if set(_unique(binding.get("knowledge_ids") or [])) - point_ids:
            issues.append(_issue("binding_missing_point", "bindings", "critical", "教学绑定引用了不存在的知识点"))
        if binding.get("teaching_role") not in TEACHING_ROLES:
            issues.append(_issue("invalid_teaching_role", "bindings", "critical", "教学绑定缺少合法教学作用"))
        if binding.get("binding_method") == "primary_point_fallback" and len(
            _unique(binding.get("candidate_knowledge_ids") or [])
        ) > 1:
            issues.append(_issue("imprecise_block_binding", "bindings", "major", f"内容块 {binding.get('target_id')} 尚未精确绑定"))

    critical_count = sum(item["severity"] == "critical" for item in issues)
    major_count = sum(item["severity"] == "major" for item in issues)
    relation_covered = len(inbound) / len(points) if points else 0.0
    return {
        "schema_version": "course_knowledge_quality_v2",
        "passed": critical_count == 0,
        "strict_passed": not issues,
        "score": max(0, 100 - 15 * critical_count - 5 * major_count),
        "critical_count": critical_count,
        "major_count": major_count,
        "issues": issues,
        "blocking_issues": [item for item in issues if item["severity"] == "critical"],
        "coverage": {
            "section_count": len(section_ids),
            "covered_section_count": len(section_ids & bound_sections),
            "concept_group_count": len(groups),
            "knowledge_point_count": len(points),
            "skill_unit_count": len(skills),
            "misconception_count": len(mistakes),
            "mastery_criterion_count": len(criteria),
            "relation_count": len(relations),
            "relation_decision_count": len(relation_decisions),
            "relation_coverage": round(relation_covered, 4),
            "binding_count": len(bindings),
        },
        "metrics": {
            "mapped_ratio": round(len(section_ids & bound_sections) / len(section_ids), 4) if section_ids else 0.0,
            "relation_coverage": round(relation_covered, 4),
            "atomic_ratio": round(sum(item.get("granularity_status") == "atomic" for item in points) / len(points), 4) if points else 0.0,
        },
    }


def knowledge_binding_for_section(
    knowledge_base: dict[str, Any],
    section_id: str,
) -> dict[str, list[str]]:
    relevant = [
        item for item in knowledge_base.get("bindings") or []
        if item.get("target_type") == "section"
        and str(item.get("target_id") or "") == section_id
    ]
    knowledge_ids = _unique([
        knowledge_id
        for item in relevant
        for knowledge_id in item.get("knowledge_ids") or []
    ])
    skill_ids = _unique([
        skill_id
        for item in relevant
        for skill_id in item.get("skill_ids") or []
    ])
    misconception_ids = _unique([
        str(item.get("misconception_id") or "")
        for item in knowledge_base.get("misconceptions") or []
        if item.get("primary_knowledge_id") in knowledge_ids
    ])
    mastery_ids = _unique([
        str(item.get("criterion_id") or "")
        for item in knowledge_base.get("mastery_criteria") or []
        if set(item.get("knowledge_ids") or []) & set(knowledge_ids)
    ])
    return {
        "course_knowledge_refs": knowledge_ids,
        "course_skill_refs": skill_ids,
        "course_misconception_refs": misconception_ids,
        "course_mastery_refs": mastery_ids,
        # Temporary read aliases for consumers that are migrated in a later slice.
        "course_capability_refs": skill_ids,
        "course_mistake_refs": misconception_ids,
        "course_improvement_refs": [],
    }


def bind_course_knowledge_base_to_map(
    course_map: dict[str, Any],
    knowledge_base: dict[str, Any],
) -> dict[str, Any]:
    """Project course-owned IDs and precise bindings onto the compatibility map."""
    enriched = deepcopy(course_map)
    section_ids = {
        section_id: knowledge_binding_for_section(knowledge_base, section_id)["course_knowledge_refs"]
        for section_id in {
            str(item.get("target_id") or "")
            for item in knowledge_base.get("bindings") or []
            if item.get("target_type") == "section"
        }
    }
    enriched["section_course_knowledge_ids"] = section_ids
    enriched["section_knowledge_ids"] = deepcopy(section_ids)
    enriched["knowledge_bindings"] = deepcopy(knowledge_base.get("bindings") or [])
    points_by_id = {
        str(item.get("knowledge_id") or ""): item
        for item in knowledge_base.get("knowledge_points") or []
    }
    for mapping in enriched.get("mappings") or []:
        section_id = str(mapping.get("section_id") or "")
        available_ids = section_ids.get(section_id, [])
        exact_ids = [
            point_id
            for point_id in available_ids
            if point_id in points_by_id
            and _normalize_name(points_by_id[point_id].get("name"))
            == _normalize_name(mapping.get("local_name"))
        ]
        bound_ids = exact_ids or available_ids
        mapping["course_knowledge_node_ids"] = bound_ids
        mapping["anchor_knowledge_id"] = bound_ids[0] if bound_ids else None
        mapping["knowledge_ids"] = list(bound_ids)
        mapping["match_status"] = "course_local" if bound_ids else "awaiting_course_binding"
        mapping["confidence"] = 1.0 if exact_ids else 0.8 if bound_ids else 0.0
        mapping["suggestions"] = []
        mapping["revision_id"] = _revision_id(mapping, "ckmr_")
    coverage = dict(enriched.get("coverage") or {})
    knowledge_mappings = [
        item for item in enriched.get("mappings") or []
        if item.get("mapping_scope") == "knowledge"
    ]
    mapped = [item for item in knowledge_mappings if item.get("knowledge_ids")]
    coverage.update({
        "mapped_count": len(mapped),
        "unmapped_count": len(knowledge_mappings) - len(mapped),
        "formal_knowledge_count": len(points_by_id),
        "formal_knowledge_ids": list(points_by_id),
        "mapped_ratio": round(len(mapped) / len(knowledge_mappings), 4) if knowledge_mappings else 0.0,
        "status": "mapped" if knowledge_mappings and len(mapped) == len(knowledge_mappings) else "partial",
        "course_local_node_count": len(knowledge_base.get("knowledge_points") or []),
        "course_local_knowledge_point_count": len(knowledge_base.get("knowledge_points") or []),
        "course_local_coverage_status": "covered" if section_ids and all(section_ids.values()) else "missing",
        "binding_count": len(knowledge_base.get("bindings") or []),
    })
    enriched["coverage"] = coverage
    enriched["unresolved_candidates"] = [
        deepcopy(item) for item in knowledge_mappings if not item.get("knowledge_ids")
    ]
    enriched["knowledge_library_id"] = knowledge_base.get("knowledge_base_id")
    enriched["knowledge_library_version"] = knowledge_base.get("revision_id")
    enriched["knowledge_library_revision_id"] = knowledge_base.get("revision_id")
    enriched["binding_revision_id"] = knowledge_base.get("revision_id")
    enriched["library_lifecycle_status"] = knowledge_base.get("lifecycle_status", "degraded")
    enriched["status"] = "active"
    enriched["revision_id"] = _revision_id(enriched, "ckmvr_")
    return enriched


def course_knowledge_base_prompt_context(
    knowledge_base: dict[str, Any],
    section_id: str,
) -> str:
    binding = knowledge_binding_for_section(knowledge_base, section_id)
    point_ids = set(binding["course_knowledge_refs"])
    points = [
        item for item in knowledge_base.get("knowledge_points") or []
        if item.get("knowledge_id") in point_ids
    ]
    if not points:
        return "当前小节尚未形成课程知识契约，禁止用小节标题伪造知识点。"
    skills = list(knowledge_base.get("skill_units") or [])
    mistakes = list(knowledge_base.get("misconceptions") or [])
    criteria = list(knowledge_base.get("mastery_criteria") or [])
    relation_rows = [
        item for item in knowledge_base.get("relations") or []
        if item.get("source_knowledge_id") in point_ids or item.get("target_knowledge_id") in point_ids
    ]
    names = {str(item.get("knowledge_id")): str(item.get("name")) for item in knowledge_base.get("knowledge_points") or []}
    rows = ["本节必须围绕以下课程内知识能力包生成正文、课件、练习和反馈："]
    for point in points:
        point_id = str(point.get("knowledge_id") or "")
        rows.append(f"- 知识点：{point.get('name')}；命题：{point.get('statement')}")
        rows.append(f"  - 条件/边界：{'；'.join([*point.get('conditions', []), *point.get('boundaries', [])])}")
        for skill in skills:
            if skill.get("primary_knowledge_id") == point_id:
                rows.append(f"  - 能力点：{skill.get('observable_behavior')}")
        for mistake in mistakes:
            if mistake.get("primary_knowledge_id") == point_id:
                rows.append(f"  - 易错点：{mistake.get('observable_error_pattern')}；辨别：{mistake.get('discrimination')}")
        for criterion in criteria:
            if point_id in (criterion.get("knowledge_ids") or []):
                rows.append(f"  - 掌握标准：{criterion.get('observable_performance')}")
    if relation_rows:
        rows.append("本节相关知识关系：")
        for relation in relation_rows[:12]:
            rows.append(
                f"- {names.get(str(relation.get('source_knowledge_id')), '')} "
                f"--{relation.get('relation_type')}--> "
                f"{names.get(str(relation.get('target_knowledge_id')), '')}：{relation.get('reason')}"
            )
    return "\n".join(rows)


def build_course_knowledge_library_view(
    knowledge_base: dict[str, Any],
    course_map: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project course path + knowledge packages into the student read model."""
    course_data = course_data or {}
    bindings_by_point: dict[str, dict[str, set[str]]] = {}

    def binding(point_id: str) -> dict[str, set[str]]:
        return bindings_by_point.setdefault(point_id, {
            "section_ids": set(),
            "block_ids": set(),
            "objective_ids": set(),
            "question_ids": set(),
            "criterion_ids": set(),
            "misconception_ids": set(),
            "skill_unit_ids": set(),
            "mistake_point_ids": set(),
            "mastery_criterion_ids": set(),
            "improvement_ids": set(),
        })

    target_keys = {
        "section": "section_ids",
        "course_block": "block_ids",
        "objective": "objective_ids",
        "question": "question_ids",
        "criterion": "criterion_ids",
    }
    for item in knowledge_base.get("bindings") or []:
        target_key = target_keys.get(str(item.get("target_type") or ""))
        for point_id in item.get("knowledge_ids") or []:
            if target_key and item.get("target_id"):
                binding(str(point_id))[target_key].add(str(item["target_id"]))
            binding(str(point_id))["skill_unit_ids"].update(item.get("skill_ids") or [])
    for item in knowledge_base.get("misconceptions") or []:
        point_id = str(item.get("primary_knowledge_id") or "")
        binding(point_id)["mistake_point_ids"].add(str(item.get("misconception_id") or ""))
    for item in knowledge_base.get("mastery_criteria") or []:
        for point_id in item.get("knowledge_ids") or []:
            binding(str(point_id))["mastery_criterion_ids"].add(str(item.get("criterion_id") or ""))
    for asset_type, id_key, target_key in (
        ("questions", "question_id", "question_ids"),
        ("mastery_criteria", "criterion_id", "criterion_ids"),
        ("misconceptions", "misconception_id", "misconception_ids"),
    ):
        for asset in assets.get(asset_type) or []:
            asset_id = str(asset.get(id_key) or asset.get("asset_id") or "")
            for point_id in asset.get("course_knowledge_refs") or []:
                if point_id and asset_id:
                    binding(str(point_id))[target_key].add(asset_id)

    sections = _sections(course_data)
    chapters = [
        item for item in course_data.get("nodes") or []
        if int(item.get("node_level") or 1) == 1
    ]
    course_root_id = f"course-path:{knowledge_base.get('course_id') or 'course'}"
    view_nodes: list[dict[str, Any]] = [
        _view_path_node(
            course_root_id,
            None,
            "course",
            str(course_data.get("course_name") or "本课程"),
            0,
            [],
        )
    ]
    chapter_view_ids: dict[str, str] = {}
    section_view_ids: dict[str, str] = {}
    for order, chapter in enumerate(chapters):
        chapter_id = str(chapter.get("node_id") or "")
        view_id = f"course-path:chapter:{chapter_id}"
        chapter_view_ids[chapter_id] = view_id
        view_nodes.append(_view_path_node(
            view_id,
            course_root_id,
            "chapter",
            _section_title(chapter),
            order,
            [chapter_id],
        ))
    for order, section in enumerate(sections):
        section_id = str(section.get("node_id") or "")
        view_id = f"course-path:section:{section_id}"
        section_view_ids[section_id] = view_id
        parent = chapter_view_ids.get(str(section.get("parent_node_id") or ""), course_root_id)
        view_nodes.append(_view_path_node(
            view_id,
            parent,
            "section",
            _section_title(section),
            order,
            [section_id],
        ))

    group_by_id = {
        str(item.get("concept_group_id") or ""): item
        for item in knowledge_base.get("concept_groups") or []
    }
    for group in knowledge_base.get("concept_groups") or []:
        group_id = str(group.get("concept_group_id") or "")
        parent_id = section_view_ids.get(str(group.get("primary_section_ref") or ""), course_root_id)
        path_ids, path_names = _view_path(view_nodes, parent_id)
        view_nodes.append({
            "knowledge_id": group_id,
            "code": group_id,
            "parent_id": parent_id,
            "node_type": "concept_group",
            "name": group.get("name"),
            "description": group.get("description"),
            "depth": len(path_ids),
            "sort_order": int(group.get("order") or 0),
            "path_ids": [*path_ids, group_id],
            "path_names": [*path_names, str(group.get("name") or "")],
            "aliases": [],
            "learning_actions": [],
            "typical_problems": [],
            "section_ids": [str(group.get("primary_section_ref") or "")],
            "block_ids": [],
            "objective_ids": [],
            "criterion_ids": [],
            "question_ids": [],
            "misconception_ids": [],
            "skill_unit_ids": [],
            "mistake_point_ids": [],
            "mastery_criterion_ids": [],
            "improvement_ids": [],
            "covered_by_course": True,
            "source_status": "course_source",
            "status": group.get("status", "active"),
            "revision_id": group.get("revision_id"),
        })

    skills_by_point: dict[str, list[str]] = {}
    skill_behaviors: dict[str, list[str]] = {}
    for skill in knowledge_base.get("skill_units") or []:
        point_id = str(skill.get("primary_knowledge_id") or "")
        skills_by_point.setdefault(point_id, []).append(str(skill.get("skill_id") or ""))
        skill_behaviors.setdefault(point_id, []).append(str(skill.get("observable_behavior") or ""))
    for point in knowledge_base.get("knowledge_points") or []:
        point_id = str(point.get("knowledge_id") or "")
        parent_id = str(point.get("primary_concept_group_id") or "")
        path_ids, path_names = _view_path(view_nodes, parent_id)
        entry = binding(point_id)
        projected = {
            "knowledge_id": point_id,
            "code": point_id,
            "parent_id": parent_id if parent_id in group_by_id else course_root_id,
            "node_type": "knowledge_point",
            "name": point.get("name"),
            "description": point.get("statement"),
            "statement": point.get("statement"),
            "conditions": deepcopy(point.get("conditions") or []),
            "boundaries": deepcopy(point.get("boundaries") or []),
            "counterexamples": deepcopy(point.get("counterexamples") or []),
            "depth": len(path_ids),
            "sort_order": int(point.get("order") or 0),
            "path_ids": [*path_ids, point_id],
            "path_names": [*path_names, str(point.get("name") or "")],
            "aliases": deepcopy(point.get("aliases") or []),
            "learning_actions": _unique(skill_behaviors.get(point_id, [])),
            "typical_problems": [],
            "source_status": "course_source",
            "status": point.get("status", "active"),
            "revision_id": point.get("revision_id"),
            "identity_scope": "course_local",
            "granularity_status": point.get("granularity_status"),
        }
        for key, values in entry.items():
            projected[key] = sorted(value for value in values if value)
        projected["skill_unit_ids"] = _unique([
            *projected.get("skill_unit_ids", []),
            *skills_by_point.get(point_id, []),
        ])
        projected["covered_by_course"] = bool(projected["section_ids"])
        view_nodes.append(projected)

    relation_view = [{
        "relation_id": item.get("relation_id"),
        "source_knowledge_id": item.get("source_knowledge_id"),
        "target_knowledge_id": item.get("target_knowledge_id"),
        "relation_type": item.get("relation_type"),
        "reason": item.get("reason", ""),
        "conditions": deepcopy(item.get("conditions") or []),
        "distinction": item.get("distinction"),
        "derivation_steps": deepcopy(item.get("derivation_steps") or []),
        "source_status": item.get("source_type", "course_source"),
        "status": item.get("status", "accepted"),
        "revision_id": item.get("revision_id"),
    } for item in knowledge_base.get("relations") or []]
    skill_view = [{
        "skill_unit_id": item.get("skill_id"),
        "name": item.get("name"),
        "learning_goal": item.get("observable_behavior"),
        "observable_behaviors": [item.get("observable_behavior")],
        "primary_knowledge_id": item.get("primary_knowledge_id"),
        "knowledge_ids": _unique([item.get("primary_knowledge_id"), *(item.get("supporting_knowledge_ids") or [])]),
        "source_status": "course_source",
    } for item in knowledge_base.get("skill_units") or []]
    mistake_view = [{
        "mistake_point_id": item.get("misconception_id"),
        "skill_unit_id": next(iter(item.get("skill_ids") or []), ""),
        "name": item.get("name"),
        "error_pattern": item.get("observable_error_pattern"),
        "discrimination": item.get("discrimination"),
        "repair_strategy": item.get("repair_strategy"),
        "knowledge_ids": _unique([item.get("primary_knowledge_id"), *(item.get("related_knowledge_ids") or [])]),
        "source_status": "course_source",
    } for item in knowledge_base.get("misconceptions") or []]

    quality = deepcopy(knowledge_base.get("quality_report") or {})
    public_quality = _public_quality_summary(quality)
    publishable = knowledge_base.get("lifecycle_status") == "active"
    lifecycle = "accepted" if publishable else "degraded"
    published_nodes = view_nodes if publishable else []
    published_relations = relation_view if publishable else []
    published_skills = skill_view if publishable else []
    published_mistakes = mistake_view if publishable else []
    published_mastery = deepcopy(knowledge_base.get("mastery_criteria") or []) if publishable else []
    published_point_count = len(knowledge_base.get("knowledge_points") or []) if publishable else 0
    payload = {
        "schema_version": COURSE_KNOWLEDGE_VIEW_SCHEMA,
        "library_id": knowledge_base.get("knowledge_base_id"),
        "subject_id": knowledge_base.get("course_id") or "course_local",
        "library_version": knowledge_base.get("revision_id"),
        "root_node_id": course_root_id,
        "nodes": published_nodes,
        "relations": published_relations,
        "skill_units": published_skills,
        "mistake_points": published_mistakes,
        "mastery_criteria": published_mastery,
        "improvement_points": [],
        "skill_relations": [],
        "usage_policy": {
            "ai_must_judge_independently": True,
            "allowed_fit": ["hit", "partial", "miss"],
            "may_invent_formal_ids": False,
            "personal_state_can_modify_library": False,
            "identity_scope": "course_only",
        },
        "course_map_revision_id": course_map.get("revision_id"),
        "course_knowledge_base_revision_id": knowledge_base.get("revision_id"),
        "binding_revision_id": knowledge_base.get("revision_id"),
        "coverage": {
            "formal_knowledge_count": 0,
            "mapped_count": published_point_count,
            "unmapped_count": 0,
            "mapped_ratio": 1.0 if published_point_count else 0.0,
            "status": "course_local",
            "course_local_knowledge_count": published_point_count,
            "binding_count": len(knowledge_base.get("bindings") or []),
        },
        "unresolved_mappings": [],
        "identity_scope": "course_local",
        "status": "active" if publishable and published_nodes else "unavailable",
        "lifecycle_status": lifecycle,
        "origin": "course_and_domain_generated",
        "quality_report": public_quality,
        "generation_audit": deepcopy(knowledge_base.get("generation_audit") or {}),
        "source_summary": {"course_source": published_point_count},
    }
    payload["asset_id"] = stable_hash(
        {"knowledge_base": knowledge_base.get("revision_id"), "course_map": course_map.get("revision_id")},
        prefix="ckv_",
    )
    payload["revision_id"] = _revision_id(payload, "ckvr_")
    return payload


def _public_quality_summary(quality: dict[str, Any]) -> dict[str, Any]:
    """Keep governance diagnostics out of the student knowledge read model."""
    issues = list(quality.get("issues") or [])
    blocking = list(quality.get("blocking_issues") or [])
    return {
        "schema_version": quality.get("schema_version"),
        "passed": bool(quality.get("passed")),
        "strict_passed": bool(quality.get("strict_passed")),
        "score": quality.get("score"),
        "critical_count": int(quality.get("critical_count") or len(blocking)),
        "major_count": int(quality.get("major_count") or 0),
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking),
        "metrics": deepcopy(quality.get("metrics") or {}),
        "coverage": deepcopy(quality.get("coverage") or {}),
        # Preserve the read-model shape without exposing internal rule messages.
        "issues": [],
        "blocking_issues": [],
    }


def _compile_skills(
    course_id: str,
    point: dict[str, Any],
    raw_point: dict[str, Any],
    section_id: str,
    source_refs: list[str],
) -> list[dict[str, Any]]:
    values = raw_point.get("capability_points") or []
    if not values and raw_point.get("capability"):
        values = [{
            "name": str(raw_point.get("capability")),
            "observable_behavior": str(raw_point.get("capability")),
        }]
    result = []
    for order, value in enumerate(values if isinstance(values, list) else [values]):
        standard = _standard(value)
        name = standard["name"]
        if not name or not standard["observable_behavior"]:
            continue
        item = {
            "skill_id": _local_id(course_id, str(point["knowledge_id"]), "skill", name, "cks_"),
            "course_id": course_id,
            "name": name,
            "observable_behavior": standard["observable_behavior"],
            "primary_knowledge_id": point["knowledge_id"],
            "supporting_knowledge_ids": [],
            "required_evidence_types": _unique(standard.get("required_evidence_types") or []),
            "section_refs": [section_id],
            "source_refs": source_refs,
            "order": order,
            "status": "active",
        }
        item["revision_id"] = _revision_id(item, "cksr_")
        result.append(item)
    return result


def _compile_misconceptions(
    course_id: str,
    point: dict[str, Any],
    raw_point: dict[str, Any],
    point_skill_ids: list[str],
    section_id: str,
    source_refs: list[str],
) -> list[dict[str, Any]]:
    result = []
    for order, value in enumerate(raw_point.get("misconceptions") or []):
        standard = _standard(value)
        if (
            not standard["name"]
            or not (standard["observable_error_pattern"] or standard["description"])
            or not standard["discrimination"]
            or not standard["repair_strategy"]
        ):
            continue
        item = {
            "misconception_id": _local_id(course_id, str(point["knowledge_id"]), "misconception", standard["name"], "ckm_"),
            "course_id": course_id,
            "name": standard["name"],
            "observable_error_pattern": standard["observable_error_pattern"] or standard["description"],
            "confused_with": standard["confused_with"],
            "discrimination": standard["discrimination"],
            "repair_strategy": standard["repair_strategy"],
            "primary_knowledge_id": point["knowledge_id"],
            "related_knowledge_ids": [],
            "skill_ids": point_skill_ids,
            "section_refs": [section_id],
            "source_refs": source_refs,
            "order": order,
            "status": "active",
        }
        item["revision_id"] = _revision_id(item, "ckmr_")
        result.append(item)
    return result


def _compile_mastery_criteria(
    course_id: str,
    point: dict[str, Any],
    raw_point: dict[str, Any],
    point_skill_ids: list[str],
    section_id: str,
    source_refs: list[str],
) -> list[dict[str, Any]]:
    result = []
    for order, value in enumerate(raw_point.get("mastery_criteria") or []):
        standard = _standard(value)
        name = standard["name"] or standard["observable_performance"]
        if (
            not name
            or not standard["observable_performance"]
            or not standard["verification_method"]
        ):
            continue
        item = {
            "criterion_id": _local_id(course_id, str(point["knowledge_id"]), "mastery", name, "ckmc_"),
            "course_id": course_id,
            "name": name,
            "observable_performance": standard["observable_performance"],
            "knowledge_ids": [point["knowledge_id"]],
            "skill_ids": point_skill_ids,
            "required_independence": standard["required_independence"] or "independent",
            "required_transfer": standard["required_transfer"] or "variation",
            "verification_method": standard["verification_method"],
            "required_evidence_types": _unique(standard.get("required_evidence_types") or []),
            "section_refs": [section_id],
            "source_refs": source_refs,
            "order": order,
            "status": "active",
        }
        item["revision_id"] = _revision_id(item, "ckmcr_")
        result.append(item)
    return result


def _compile_relation_decisions(
    course_data: dict[str, Any],
    point_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_decisions = (
        course_data.get("knowledge_relation_decisions")
        or (course_data.get("course_plan") or {}).get(
            "knowledge_relation_decisions"
        )
        or []
    )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            continue
        knowledge_id = str(raw.get("knowledge_id") or "").strip()
        decision = str(raw.get("decision") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if (
            knowledge_id not in point_by_id
            or knowledge_id in seen
            or decision not in {"connected", "course_entry"}
            or not reason
        ):
            continue
        seen.add(knowledge_id)
        item = {
            "knowledge_id": knowledge_id,
            "decision": decision,
            "reason": reason,
        }
        item["revision_id"] = _revision_id(item, "ckrdr_")
        result.append(item)
    return result


def _compile_relations(
    course_id: str,
    candidates: list[dict[str, Any]],
    point_by_name: dict[str, dict[str, Any]],
    point_by_id: dict[str, dict[str, Any]],
    invalid: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aliases = {
        "application": "applies_to",
        "confusable": "contrasts_with",
        "equivalent": "equivalent_to",
        "generalization": "generalizes",
    }
    result = []
    for candidate in candidates:
        source_id_candidate = str(
            candidate.get("source_knowledge_id") or ""
        ).strip()
        target_id_candidate = str(
            candidate.get("target_knowledge_id") or ""
        ).strip()
        source_name = str(candidate.get("source_name") or "").strip()
        target_name = str(candidate.get("target_name") or "").strip()
        relation_type = aliases.get(
            str(candidate.get("relation_type") or "").strip(),
            str(candidate.get("relation_type") or "").strip(),
        )
        if relation_type not in RELATION_TYPES:
            invalid.append({**deepcopy(candidate), "rejection_reason": "invalid_relation_type"})
            continue
        if not str(candidate.get("reason") or "").strip():
            invalid.append({**deepcopy(candidate), "rejection_reason": "missing_reason"})
            continue
        if relation_type == "derives" and not candidate.get("derivation_steps"):
            invalid.append({**deepcopy(candidate), "rejection_reason": "missing_derivation_steps"})
            continue
        if relation_type == "contrasts_with" and not str(candidate.get("distinction") or "").strip():
            invalid.append({**deepcopy(candidate), "rejection_reason": "missing_distinction"})
            continue
        if source_id_candidate or target_id_candidate:
            source = point_by_id.get(source_id_candidate)
            target = point_by_id.get(target_id_candidate)
        else:
            source = point_by_name.get(_normalize_name(source_name))
            target = point_by_name.get(_normalize_name(target_name))
        if not source or not target or source is target:
            unresolved.append(deepcopy(candidate))
            continue
        source_id = str(source["knowledge_id"])
        target_id = str(target["knowledge_id"])
        if relation_type in SYMMETRIC_RELATION_TYPES and source_id > target_id:
            source_id, target_id = target_id, source_id
        item = {
            "relation_id": stable_hash(
                {"course": course_id, "source": source_id, "target": target_id, "type": relation_type},
                prefix="ckrel_",
            ),
            "course_id": course_id,
            "source_knowledge_id": source_id,
            "target_knowledge_id": target_id,
            "relation_type": relation_type,
            "relation_group_id": candidate.get("relation_group_id"),
            "group_operator": candidate.get("group_operator"),
            "necessity": str(candidate.get("necessity") or ("required" if relation_type == "prerequisite" else "helpful")),
            "priority": str(candidate.get("priority") or "core"),
            "conditions": _unique(candidate.get("conditions") or []),
            "reason": str(candidate.get("reason") or "").strip(),
            "distinction": str(candidate.get("distinction") or "").strip(),
            "derivation_steps": _unique(candidate.get("derivation_steps") or []),
            "source_refs": _unique(candidate.get("source_refs") or []),
            "source_type": str(candidate.get("source_type") or "model_generated"),
            "confidence": float(candidate.get("confidence") or 0.8),
            "status": "candidate",
        }
        item["revision_id"] = _revision_id(item, "ckrelr_")
        result.append(item)
    return result


def _compile_course_object_bindings(
    course_id: str,
    sections: list[dict[str, Any]],
    section_point_ids: dict[str, list[str]],
    points: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    assets: dict[str, list[dict[str, Any]]],
) -> None:
    by_id = {str(item.get("knowledge_id") or ""): item for item in points}
    for section in sections:
        section_id = str(section.get("node_id") or "")
        candidate_ids = section_point_ids.get(section_id, [])
        if not candidate_ids:
            continue
        objective_id = str(section.get("objective_id") or "")
        if objective_id:
            _append_binding(
                bindings,
                course_id=course_id,
                knowledge_ids=candidate_ids,
                skill_ids=_skill_ids_for_points(skills, candidate_ids),
                target_type="objective",
                target_id=objective_id,
                teaching_role="assesses",
                importance="primary",
                source_refs=_section_evidence_refs(section),
                binding_method="objective_contract",
            )
        for block in section.get("content_blocks") or []:
            block_id = str(block.get("block_id") or block.get("content_block_id") or "")
            if not block_id:
                continue
            explicit = [
                point_id for point_id in candidate_ids
                if block_id in (by_id.get(point_id) or {}).get("declared_block_refs", [])
            ]
            searchable = _normalize_search_text(
                f"{block.get('title') or ''} {block.get('content') or ''} {block.get('summary') or ''}"
            )
            semantic_matches = [
                point_id for point_id in candidate_ids
                if _point_matches_text(by_id.get(point_id) or {}, searchable)
            ]
            matched = explicit or semantic_matches
            method = "knowledge_blueprint_anchor" if explicit else "semantic_name_match"
            if not matched:
                continue
            _append_binding(
                bindings,
                course_id=course_id,
                knowledge_ids=matched,
                skill_ids=_skill_ids_for_points(skills, matched),
                target_type="course_block",
                target_id=block_id,
                teaching_role=_block_teaching_role(block),
                importance="primary" if method == "semantic_name_match" else "supporting",
                source_refs=_section_evidence_refs(section),
                binding_method=method,
                candidate_knowledge_ids=candidate_ids,
            )
    valid_point_ids = set(by_id)
    for asset_type, target_type, teaching_role in (
        ("questions", "question", "practices"),
        ("mastery_criteria", "criterion", "assesses"),
        ("misconceptions", "criterion", "remediates"),
    ):
        for asset in assets.get(asset_type) or []:
            target_id = str(
                asset.get("question_id")
                or asset.get("criterion_id")
                or asset.get("misconception_id")
                or asset.get("asset_id")
                or ""
            )
            explicit = [
                str(item) for item in asset.get("course_knowledge_refs") or []
                if str(item) in valid_point_ids
            ]
            section_ids = _unique([asset.get("node_id"), *(asset.get("node_ids") or [])])
            candidates = _unique([
                point_id for section_id in section_ids
                for point_id in section_point_ids.get(section_id, [])
            ])
            selected = explicit or candidates
            if not target_id or not selected:
                continue
            _append_binding(
                bindings,
                course_id=course_id,
                knowledge_ids=selected,
                skill_ids=_skill_ids_for_points(skills, selected),
                target_type=target_type,
                target_id=target_id,
                teaching_role=teaching_role,
                importance="primary",
                source_refs=_unique(asset.get("evidence_ids") or []),
                binding_method="explicit_asset_binding" if explicit else "legacy_section_fallback",
                candidate_knowledge_ids=candidates,
            )
    for criterion in criteria:
        _append_binding(
            bindings,
            course_id=course_id,
            knowledge_ids=_unique(criterion.get("knowledge_ids") or []),
            skill_ids=_unique(criterion.get("skill_ids") or []),
            target_type="criterion",
            target_id=str(criterion.get("criterion_id") or ""),
            teaching_role="assesses",
            importance="primary",
            source_refs=_unique(criterion.get("source_refs") or []),
            binding_method="mastery_contract",
        )


def _append_binding(
    bindings: list[dict[str, Any]],
    *,
    course_id: str,
    knowledge_ids: list[str],
    skill_ids: list[str],
    target_type: str,
    target_id: str,
    teaching_role: str,
    importance: str,
    source_refs: list[str],
    binding_method: str,
    candidate_knowledge_ids: list[str] | None = None,
) -> None:
    if not target_id or not knowledge_ids:
        return
    item = {
        "binding_id": stable_hash({
            "course": course_id,
            "target_type": target_type,
            "target_id": target_id,
            "knowledge_ids": sorted(_unique(knowledge_ids)),
            "role": teaching_role,
        }, prefix="ckbind_"),
        "course_id": course_id,
        "knowledge_ids": _unique(knowledge_ids),
        "skill_ids": _unique(skill_ids),
        "target_type": target_type,
        "target_id": target_id,
        "teaching_role": teaching_role,
        "importance": importance,
        "anchor": None,
        "source_refs": _unique(source_refs),
        "binding_method": binding_method,
        "candidate_knowledge_ids": _unique(candidate_knowledge_ids or []),
        "status": "active",
    }
    item["revision_id"] = _revision_id(item, "ckbindr_")
    bindings.append(item)


def _attach_compatibility_projection(
    payload: dict[str, Any],
    section_point_ids: dict[str, list[str]],
    group_point_ids: dict[str, list[str]],
) -> None:
    """Expose temporary v1 read aliases while all consumers move to v2 fields."""
    group_nodes = [{
        "node_id": item.get("concept_group_id"),
        "parent_id": None,
        "node_type": "concept_group",
        "name": item.get("name"),
        "description": item.get("description"),
        "section_refs": [item.get("primary_section_ref")],
        "order": item.get("order"),
        "revision_id": item.get("revision_id"),
        "status": item.get("status"),
    } for item in payload.get("concept_groups") or []]
    point_nodes = [{
        "node_id": item.get("knowledge_id"),
        "parent_id": item.get("primary_concept_group_id"),
        "node_type": "knowledge_point",
        "name": item.get("name"),
        "description": item.get("statement"),
        "statement": item.get("statement"),
        "conditions": item.get("conditions"),
        "boundaries": item.get("boundaries"),
        "aliases": item.get("aliases"),
        "section_refs": item.get("section_refs"),
        "course_block_refs": item.get("course_block_refs"),
        "objective_refs": item.get("objective_refs"),
        "practice_refs": item.get("practice_refs"),
        "granularity_status": item.get("granularity_status"),
        "order": item.get("order"),
        "revision_id": item.get("revision_id"),
        "status": item.get("status"),
    } for item in payload.get("knowledge_points") or []]
    payload["nodes"] = [*group_nodes, *point_nodes]
    payload["root_node_ids"] = [str(item.get("concept_group_id")) for item in payload.get("concept_groups") or []]
    payload["capability_points"] = [{
        **deepcopy(item),
        "capability_point_id": item.get("skill_id"),
        "knowledge_node_id": item.get("primary_knowledge_id"),
    } for item in payload.get("skill_units") or []]
    payload["mistake_points"] = [{
        **deepcopy(item),
        "mistake_point_id": item.get("misconception_id"),
        "knowledge_node_id": item.get("primary_knowledge_id"),
        "capability_point_id": next(iter(item.get("skill_ids") or []), ""),
        "error_pattern": item.get("observable_error_pattern"),
    } for item in payload.get("misconceptions") or []]
    payload["improvement_points"] = []
    payload["section_bindings"] = {
        section_id: {
            "knowledge_node_ids": point_ids,
            "capability_point_ids": _skill_ids_for_points(payload.get("skill_units") or [], point_ids),
            "mistake_point_ids": [
                str(item.get("misconception_id") or "")
                for item in payload.get("misconceptions") or []
                if item.get("primary_knowledge_id") in point_ids
            ],
            "mastery_criterion_ids": [
                str(item.get("criterion_id") or "")
                for item in payload.get("mastery_criteria") or []
                if set(item.get("knowledge_ids") or []) & set(point_ids)
            ],
            "improvement_point_ids": [],
        }
        for section_id, point_ids in section_point_ids.items()
    }
    payload["compatibility_projection_version"] = "course_knowledge_base_v1_read_aliases"
    payload["group_point_ids"] = deepcopy(group_point_ids)


def _backfill_point_block_refs(points: list[dict[str, Any]], bindings: list[dict[str, Any]]) -> None:
    by_point: dict[str, list[str]] = {}
    for item in bindings:
        if item.get("target_type") != "course_block":
            continue
        for point_id in item.get("knowledge_ids") or []:
            by_point.setdefault(str(point_id), []).append(str(item.get("target_id") or ""))
    for point in points:
        point["course_block_refs"] = _unique(by_point.get(str(point.get("knowledge_id") or ""), []))
        point["revision_id"] = _revision_id(point, "ckpr_")


def _point_has_required_content(point: dict[str, Any]) -> bool:
    statement = str(point.get("statement") or point.get("description") or "").strip()
    boundary = bool(point.get("conditions") or point.get("boundaries"))
    skills = point.get("capability_points") or point.get("capabilities") or point.get("capability")
    mastery = point.get("mastery_criteria") or []
    return bool(statement and boundary and skills and mastery)


def _standard(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {"name": str(value or "")}
    return {
        "name": str(raw.get("name") or raw.get("label") or raw.get("statement") or "").strip(),
        "description": str(raw.get("description") or raw.get("learning_goal") or "").strip(),
        "observable_behavior": str(raw.get("observable_behavior") or raw.get("capability") or "").strip(),
        "observable_error_pattern": str(raw.get("observable_error_pattern") or raw.get("error_pattern") or "").strip(),
        "confused_with": str(raw.get("confused_with") or "").strip(),
        "discrimination": str(raw.get("discrimination") or "").strip(),
        "repair_strategy": str(raw.get("repair_strategy") or "").strip(),
        "observable_performance": str(raw.get("observable_performance") or "").strip(),
        "required_independence": str(raw.get("required_independence") or "").strip(),
        "required_transfer": str(raw.get("required_transfer") or "").strip(),
        "verification_method": str(raw.get("verification_method") or "").strip(),
        "required_evidence_types": _unique(raw.get("required_evidence_types") or []),
    }


def _sections(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in course_data.get("nodes") or []
        if int(item.get("node_level") or 1) == 2
    ]


def _section_title(section: dict[str, Any]) -> str:
    return str(section.get("node_name") or section.get("title") or "").strip()


def _practice_refs_by_section(assets: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for asset_type in ("questions", "mastery_criteria", "misconceptions", "diagnostic_templates", "validation_questions"):
        for item in assets.get(asset_type) or []:
            asset_id = str(
                item.get("question_id")
                or item.get("criterion_id")
                or item.get("misconception_id")
                or item.get("asset_id")
                or ""
            )
            for section_id in _unique([item.get("node_id"), *(item.get("node_ids") or [])]):
                if asset_id:
                    result.setdefault(section_id, []).append(asset_id)
    return {key: _unique(value) for key, value in result.items()}


def _section_evidence_refs(section: dict[str, Any]) -> list[str]:
    contract = section.get("grounding_contract") or {}
    return _unique([
        *(section.get("evidence_refs") or []),
        *(contract.get("required_evidence_ids") or []),
        *(contract.get("optional_evidence_ids") or []),
    ])


def _skills_for_point(skills: list[dict[str, Any]], point_id: str) -> list[str]:
    return [
        str(item.get("skill_id") or "")
        for item in skills
        if item.get("primary_knowledge_id") == point_id
    ]


def _skill_ids_for_points(skills: list[dict[str, Any]], point_ids: list[str]) -> list[str]:
    selected = set(point_ids)
    return _unique([
        item.get("skill_id") or item.get("capability_point_id")
        for item in skills
        if (item.get("primary_knowledge_id") or item.get("knowledge_node_id")) in selected
    ])


def _block_teaching_role(block: dict[str, Any]) -> str:
    role = str(block.get("role") or block.get("block_role") or "").lower()
    if any(item in role for item in ("practice", "exercise", "task")):
        return "practices"
    if any(item in role for item in ("check", "assess", "feedback")):
        return "assesses"
    if any(item in role for item in ("example", "demo")):
        return "demonstrates"
    if any(item in role for item in ("remed", "repair")):
        return "remediates"
    return "explains"


def _point_matches_text(point: dict[str, Any], searchable: str) -> bool:
    terms = [point.get("name"), *(point.get("aliases") or [])]
    return any(
        (normalized := _normalize_search_text(term)) and len(normalized) >= 2 and normalized in searchable
        for term in terms
    )


def _view_path_node(
    knowledge_id: str,
    parent_id: str | None,
    node_type: str,
    name: str,
    order: int,
    section_ids: list[str],
) -> dict[str, Any]:
    return {
        "knowledge_id": knowledge_id,
        "code": knowledge_id,
        "parent_id": parent_id,
        "node_type": node_type,
        "name": name,
        "description": "课程学习路径",
        "depth": 0,
        "sort_order": order,
        "path_ids": [knowledge_id],
        "path_names": [name],
        "aliases": [],
        "learning_actions": [],
        "typical_problems": [],
        "section_ids": section_ids,
        "block_ids": [],
        "objective_ids": [],
        "criterion_ids": [],
        "question_ids": [],
        "misconception_ids": [],
        "skill_unit_ids": [],
        "mistake_point_ids": [],
        "mastery_criterion_ids": [],
        "improvement_ids": [],
        "covered_by_course": True,
        "source_status": "course_path",
        "status": "active",
        "revision_id": stable_hash({"id": knowledge_id, "name": name}, prefix="ckpathr_"),
    }


def _view_path(nodes: list[dict[str, Any]], node_id: str) -> tuple[list[str], list[str]]:
    by_id = {str(item.get("knowledge_id") or ""): item for item in nodes}
    ids: list[str] = []
    names: list[str] = []
    current = by_id.get(node_id)
    seen: set[str] = set()
    while current and str(current.get("knowledge_id") or "") not in seen:
        current_id = str(current.get("knowledge_id") or "")
        seen.add(current_id)
        ids.append(current_id)
        names.append(str(current.get("name") or ""))
        current = by_id.get(str(current.get("parent_id") or ""))
    return list(reversed(ids)), list(reversed(names))


def _validate_unique_ids(
    items: list[dict[str, Any]],
    key: str,
    label: str,
    issues: list[dict[str, Any]],
    *,
    allow_empty: bool = True,
) -> None:
    ids = [str(item.get(key) or "") for item in items]
    if (not ids and not allow_empty) or (ids and (not all(ids) or len(ids) != len(set(ids)))):
        issues.append(_issue(f"invalid_{key}", "structure", "critical", f"{label} ID 必须非空且唯一"))


def _is_unobservable_behavior(value: str) -> bool:
    normalized = _normalize_name(value)
    return normalized in {"理解", "掌握", "熟悉", "了解"} or normalized.startswith("理解某")


def _find_relation_cycle(relations: list[dict[str, Any]], relation_type: str) -> list[str]:
    graph: dict[str, list[str]] = {}
    for item in relations:
        if item.get("relation_type") == relation_type:
            graph.setdefault(str(item.get("source_knowledge_id") or ""), []).append(
                str(item.get("target_knowledge_id") or "")
            )
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node_id: str) -> list[str]:
        if node_id in visiting:
            start = path.index(node_id) if node_id in path else 0
            return [*path[start:], node_id]
        if node_id in visited:
            return []
        visiting.add(node_id)
        path.append(node_id)
        for target_id in graph.get(node_id, []):
            cycle = visit(target_id)
            if cycle:
                return cycle
        path.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return []

    for node_id in list(graph):
        cycle = visit(node_id)
        if cycle:
            return cycle
    return []


def _dedupe_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in relations:
        relation_id = str(item.get("relation_id") or "")
        if relation_id and relation_id not in seen:
            seen.add(relation_id)
            result.append(item)
    return result


def _dedupe_bindings(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in bindings:
        binding_id = str(item.get("binding_id") or "")
        if binding_id and binding_id not in seen:
            seen.add(binding_id)
            result.append(item)
    return result


def _local_id(course_id: str, parent: str, kind: str, name: str, prefix: str) -> str:
    return stable_hash(
        {"course": course_id, "parent": parent, "kind": kind, "name": _normalize_name(name)},
        prefix=prefix,
    )


def _normalize_outline_name(value: Any) -> str:
    text = re.sub(r"^第?\s*\d+\s*[章节课]?[.、:\-]?\s*", "", str(value or "").strip())
    text = re.sub(r"^\d+(?:\.\d+)*\s*", "", text)
    return _normalize_name(text)


def _normalize_search_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _normalize_name(value: Any) -> str:
    return _normalize_search_text(value)


def _revision_id(item: dict[str, Any], prefix: str) -> str:
    return stable_hash(
        {key: value for key, value in item.items() if key not in {"revision_id", "quality_report"}},
        prefix=prefix,
    )


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _issue(code: str, gate: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "gate": gate, "severity": severity, "message": message}


__all__ = [
    "apply_persisted_course_knowledge_base",
    "COURSE_KNOWLEDGE_BASE_SCHEMA",
    "COURSE_KNOWLEDGE_VIEW_SCHEMA",
    "RELATION_TYPES",
    "bind_course_knowledge_base_to_map",
    "build_course_knowledge_library_view",
    "compile_course_knowledge_base",
    "course_knowledge_source_fingerprint",
    "course_knowledge_base_prompt_context",
    "knowledge_binding_for_section",
    "validate_course_knowledge_base",
]
