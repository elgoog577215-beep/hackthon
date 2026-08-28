"""Course-local knowledge coverage and compatibility projection."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from course_versioning import stable_hash
from knowledge_structure import normalize_knowledge_structure

COURSE_MAP_SCHEMA = "course_knowledge_map_v2"


def compile_course_knowledge_map(
    course_data: dict[str, Any],
    library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile deterministic coverage for one course only.

    ``library`` is retained as a read-compatible argument for older callers, but
    deliberately ignored. A course can never acquire identity from another
    course or from a shared subject catalog.
    """
    del library
    course_id = str(course_data.get("course_id") or "")
    sections = [
        node for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    mappings: list[dict[str, Any]] = []
    section_knowledge_ids: dict[str, list[str]] = {}
    section_mapping_ids: dict[str, list[str]] = {}

    for section_order, section in enumerate(sections):
        section_id = str(section.get("node_id") or f"section-{section_order + 1}")
        structures = normalize_knowledge_structure(section)
        section_mappings: list[dict[str, Any]] = []
        local_entries = _local_entries(structures)
        for local_order, entry in enumerate(local_entries):
            mapping_scope = _mapping_scope(section, entry)
            mapping_id = stable_hash({
                "course": course_id,
                "section": section_id,
                "kind": entry["local_kind"],
                "topic": entry["local_topic"],
                "name": entry["local_name"],
            }, prefix="ckm_")
            mapping = {
                "mapping_id": mapping_id,
                "section_id": section_id,
                "local_kind": entry["local_kind"],
                "local_topic": entry["local_topic"],
                "local_name": entry["local_name"],
                "local_description": entry["local_description"],
                "local_capability": entry["local_capability"],
                "anchor_knowledge_id": None,
                "knowledge_ids": [],
                "match_status": "awaiting_course_binding",
                "mapping_scope": mapping_scope,
                "confidence": 0.0,
                "suggestions": [],
                "block_ids": [],
                "objective_ids": _unique([str(section.get("objective_id") or "")]),
                "evidence_ids": _section_evidence_ids(section),
                "source_status": "material_supported" if _section_evidence_ids(section) else "course_structure",
                "detail_status": entry["detail_status"],
                "order": local_order,
            }
            mapping["revision_id"] = _revision_id(mapping, "ckmr_")
            mappings.append(mapping)
            section_mappings.append(mapping)

        _bind_section_blocks(section, section_mappings, {})
        formal_ids: list[str] = []
        mapping_ids = [str(mapping["mapping_id"]) for mapping in section_mappings]
        section_knowledge_ids[section_id] = formal_ids
        section_mapping_ids[section_id] = mapping_ids
        section["concept_refs"] = formal_ids
        section["knowledge_refs"] = formal_ids
        section["knowledge_mapping_refs"] = mapping_ids

    sequence_relations = _course_sequence_relations(course_id, sections)
    knowledge_mappings = [
        mapping for mapping in mappings if mapping.get("mapping_scope") == "knowledge"
    ]
    unresolved = [
        deepcopy(mapping) for mapping in mappings
        if mapping.get("mapping_scope") == "knowledge"
        and mapping.get("match_status") == "awaiting_course_binding"
    ]
    mapped = [
        mapping
        for mapping in knowledge_mappings
        if mapping.get("match_status") == "course_local"
    ]
    formal_ids = _unique([
        knowledge_id
        for mapping in mapped
        for knowledge_id in mapping.get("knowledge_ids") or []
    ])
    payload = {
        "schema_version": COURSE_MAP_SCHEMA,
        "asset_id": stable_hash({"course": course_id, "kind": "course_knowledge_map"}, prefix="ckma_"),
        "course_id": course_id,
        "knowledge_library_id": None,
        "knowledge_library_version": None,
        "knowledge_library_revision_id": None,
        "binding_revision_id": None,
        "library_lifecycle_status": "course_local",
        "mappings": mappings,
        "section_knowledge_ids": section_knowledge_ids,
        "section_mapping_ids": section_mapping_ids,
        "sequence_relations": sequence_relations,
        "coverage": {
            "mapping_count": len(knowledge_mappings),
            "excluded_pedagogical_count": len(mappings) - len(knowledge_mappings),
            "mapped_count": len(mapped),
            "unmapped_count": len(unresolved),
            "formal_knowledge_count": len(formal_ids),
            "formal_knowledge_ids": formal_ids,
            "mapped_ratio": (
                round(len(mapped) / len(knowledge_mappings), 4)
                if knowledge_mappings
                else 0.0
            ),
            "status": (
                "mapped"
                if knowledge_mappings and not unresolved
                else "partial"
                if mapped
                else "unmapped"
            ),
        },
        "unresolved_candidates": unresolved,
        "status": "awaiting_course_binding",
    }
    payload["revision_id"] = _revision_id(payload, "ckmvr_")
    return payload


def compile_legacy_subject_course_map(
    course_data: dict[str, Any],
    library: dict[str, Any],
) -> dict[str, Any]:
    """Compile the retired subject-library mapping for explicit migration only.

    Production callers must use :func:`compile_course_knowledge_map`. This
    adapter exists so historical subject packages can still be inspected and
    copied into a course without restoring a hidden runtime dependency.
    """
    from subject_knowledge import (
        knowledge_index,
        match_subject_knowledge,
        suggest_subject_knowledge,
    )

    if not isinstance(library, dict) or not library.get("nodes"):
        raise ValueError("显式历史迁移必须提供可解析的旧学科知识包")
    subject_library = deepcopy(library)
    formal_nodes = knowledge_index(subject_library)
    course_id = str(course_data.get("course_id") or "")
    sections = [
        node
        for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    mappings: list[dict[str, Any]] = []
    section_knowledge_ids: dict[str, list[str]] = {}
    section_mapping_ids: dict[str, list[str]] = {}

    for section_order, section in enumerate(sections):
        section_id = str(section.get("node_id") or f"section-{section_order + 1}")
        structures = normalize_knowledge_structure(section)
        section_mappings: list[dict[str, Any]] = []
        local_entries = _local_entries(structures)
        if not local_entries:
            section_name = str(
                section.get("node_name") or section.get("title") or ""
            ).strip()
            explicit_match = match_subject_knowledge(subject_library, section_name)
            if explicit_match and explicit_match.get("match_status") in {
                "exact_name",
                "exact_alias",
            }:
                local_entries = [{
                    "local_kind": "concept",
                    "local_topic": section_name,
                    "local_name": section_name,
                    "local_description": "",
                    "local_capability": "",
                    "detail_status": "subject_alias_bridge",
                }]
        for local_order, entry in enumerate(local_entries):
            mapping_scope = _mapping_scope(section, entry)
            match = match_subject_knowledge(subject_library, entry["local_name"])
            mapping_id = stable_hash({
                "course": course_id,
                "section": section_id,
                "kind": entry["local_kind"],
                "topic": entry["local_topic"],
                "name": entry["local_name"],
            }, prefix="ckm_")
            mapping = {
                "mapping_id": mapping_id,
                "section_id": section_id,
                "local_kind": entry["local_kind"],
                "local_topic": entry["local_topic"],
                "local_name": entry["local_name"],
                "local_description": entry["local_description"],
                "local_capability": entry["local_capability"],
                "anchor_knowledge_id": (match or {}).get("anchor_knowledge_id"),
                "knowledge_ids": list((match or {}).get("knowledge_ids") or []),
                "match_status": (match or {}).get("match_status", "unmapped"),
                "mapping_scope": mapping_scope,
                "confidence": float((match or {}).get("confidence") or 0.0),
                "suggestions": (
                    []
                    if match
                    else suggest_subject_knowledge(
                        subject_library,
                        entry["local_name"],
                    )
                ),
                "block_ids": [],
                "objective_ids": _unique([str(section.get("objective_id") or "")]),
                "evidence_ids": _section_evidence_ids(section),
                "source_status": (
                    "material_supported"
                    if _section_evidence_ids(section)
                    else "course_structure"
                ),
                "detail_status": entry["detail_status"],
                "order": local_order,
            }
            mapping["revision_id"] = _revision_id(mapping, "ckmr_")
            mappings.append(mapping)
            section_mappings.append(mapping)

        _bind_section_blocks(section, section_mappings, formal_nodes)
        formal_ids = _unique([
            knowledge_id
            for mapping in section_mappings
            for knowledge_id in mapping.get("knowledge_ids") or []
            if knowledge_id in formal_nodes
        ])
        mapping_ids = [str(mapping["mapping_id"]) for mapping in section_mappings]
        section_knowledge_ids[section_id] = formal_ids
        section_mapping_ids[section_id] = mapping_ids
        section["concept_refs"] = formal_ids
        section["knowledge_refs"] = formal_ids
        section["knowledge_mapping_refs"] = mapping_ids

    knowledge_mappings = [
        mapping
        for mapping in mappings
        if mapping.get("mapping_scope") == "knowledge"
    ]
    unresolved = [
        deepcopy(mapping)
        for mapping in knowledge_mappings
        if mapping.get("match_status") == "unmapped"
    ]
    mapped = [
        mapping
        for mapping in knowledge_mappings
        if mapping.get("match_status") != "unmapped"
    ]
    formal_ids = _unique([
        knowledge_id
        for mapping in mapped
        for knowledge_id in mapping.get("knowledge_ids") or []
    ])
    payload = {
        "schema_version": COURSE_MAP_SCHEMA,
        "asset_id": stable_hash(
            {"course": course_id, "kind": "legacy_subject_course_map"},
            prefix="ckma_",
        ),
        "course_id": course_id,
        "knowledge_library_id": subject_library.get("library_id"),
        "knowledge_library_version": subject_library.get("version"),
        "knowledge_library_revision_id": subject_library.get("revision_id"),
        "binding_revision_id": (
            (course_data.get("knowledge_library_binding") or {}).get("revision_id")
        ),
        "library_lifecycle_status": subject_library.get(
            "lifecycle_status",
            "accepted"
            if subject_library.get("status") == "active"
            else "degraded",
        ),
        "mappings": mappings,
        "section_knowledge_ids": section_knowledge_ids,
        "section_mapping_ids": section_mapping_ids,
        "sequence_relations": _course_sequence_relations(course_id, sections),
        "coverage": {
            "mapping_count": len(knowledge_mappings),
            "excluded_pedagogical_count": len(mappings) - len(knowledge_mappings),
            "mapped_count": len(mapped),
            "unmapped_count": len(unresolved),
            "formal_knowledge_count": len(formal_ids),
            "formal_knowledge_ids": formal_ids,
            "mapped_ratio": (
                round(len(mapped) / len(knowledge_mappings), 4)
                if knowledge_mappings
                else 0.0
            ),
            "status": (
                "mapped"
                if knowledge_mappings and not unresolved
                else "partial"
                if mapped
                else "unmapped"
            ),
        },
        "unresolved_candidates": unresolved,
        "status": "legacy_migration_only",
        "identity_scope": "retired_subject_reference",
    }
    payload["revision_id"] = _revision_id(payload, "ckmvr_")
    return payload


def project_course_knowledge_map(course_data: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(course_data)
    course_map = compile_course_knowledge_map(projected)
    from course_knowledge_base import (
        bind_course_knowledge_base_to_map,
        compile_course_knowledge_base,
    )

    knowledge_base = compile_course_knowledge_base(
        projected,
        assets=projected.get("learning_assets") or {},
    )
    if knowledge_base.get("lifecycle_status") != "active":
        return course_map
    return bind_course_knowledge_base_to_map(course_map, knowledge_base)


def project_learning_assets_to_knowledge(
    course_data: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return a read-only, course-local projection for legacy asset bundles."""
    from course_knowledge_base import (
        bind_course_knowledge_base_to_map,
        build_course_knowledge_library_view,
        compile_course_knowledge_base,
        knowledge_binding_for_section,
    )

    projected_course = deepcopy(course_data)
    projected_assets = deepcopy(assets)
    course_map = compile_course_knowledge_map(projected_course)
    course_knowledge_base = compile_course_knowledge_base(
        projected_course,
        course_map=course_map,
        assets=projected_assets,
    )
    course_map = bind_course_knowledge_base_to_map(course_map, course_knowledge_base)
    for asset_type, values in projected_assets.items():
        if asset_type in {"knowledge_library", "course_knowledge_base", "course_knowledge_map"}:
            continue
        if not isinstance(values, list):
            continue
        for asset in values:
            if not isinstance(asset, dict):
                continue
            section_ids = _unique([
                asset.get("node_id"),
                *(asset.get("node_ids") or []),
            ])
            bindings = [
                knowledge_binding_for_section(course_knowledge_base, section_id)
                for section_id in section_ids
            ]
            for field in (
                "course_knowledge_refs",
                "course_skill_refs",
                "course_misconception_refs",
                "course_mastery_refs",
            ):
                explicit = _unique(list(asset.get(field) or []))
                asset[field] = explicit or _unique([
                    ref for binding in bindings for ref in binding.get(field) or []
                ])
            asset["course_capability_refs"] = list(asset["course_skill_refs"])
            asset["course_mistake_refs"] = list(asset["course_misconception_refs"])
            asset["course_improvement_refs"] = []
            asset["course_knowledge_base_revision_id"] = course_knowledge_base.get("revision_id")

    knowledge_view = build_course_knowledge_library_view(
        course_knowledge_base,
        course_map,
        projected_assets,
        projected_course,
    )
    projected_assets.pop("knowledge_graph", None)
    projected_assets.pop("subject_knowledge", None)
    projected_assets.pop("teaching_standards", None)
    projected_assets["course_knowledge_base"] = [course_knowledge_base]
    projected_assets["course_knowledge_map"] = [course_map]
    projected_assets["knowledge_library"] = [knowledge_view]
    return projected_assets


def knowledge_ids_for_section(course_map: dict[str, Any], section_id: str) -> list[str]:
    return _unique(list((course_map.get("section_knowledge_ids") or {}).get(section_id) or []))


def knowledge_names_for_section(
    course_map: dict[str, Any],
    section_id: str,
    library: dict[str, Any] | None = None,
) -> list[str]:
    del library
    return _unique([
        str(mapping.get("local_name") or "")
        for mapping in course_map.get("mappings") or []
        if str(mapping.get("section_id") or "") == section_id
        and mapping.get("local_kind") == "knowledge_point"
    ])


def validate_course_knowledge_map(
    course_map: dict[str, Any],
    course_data: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]] | None = None,
    library: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if course_map.get("schema_version") != COURSE_MAP_SCHEMA:
        return [_map_issue("structure", "critical", "课程知识映射格式不正确")]
    del library
    course_knowledge_base = next(iter((assets or {}).get("course_knowledge_base") or []), None)
    local_ids = {
        str(item.get("knowledge_id") or "")
        for item in (course_knowledge_base or {}).get("knowledge_points") or []
    }
    mappings = list(course_map.get("mappings") or [])
    mapping_ids = [str(item.get("mapping_id") or "") for item in mappings]
    if not all(mapping_ids) or len(mapping_ids) != len(set(mapping_ids)):
        issues.append(_map_issue("structure", "critical", "课程知识映射 ID 必须非空且唯一"))
    for mapping in mappings:
        refs = {
            str(item) for item in [mapping.get("anchor_knowledge_id"), *(mapping.get("knowledge_ids") or [])]
            if item
        }
        invalid = refs - local_ids
        if invalid:
            issues.append(_map_issue("structure", "critical", f"映射引用不存在的本课程知识：{sorted(invalid)}"))
        if mapping.get("match_status") == "awaiting_course_binding" and refs:
            issues.append(_map_issue("semantic", "critical", "待绑定映射不得携带课程知识 ID"))
    section_ids = {
        str(node.get("node_id") or "") for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    }
    mapped_sections = {str(item.get("section_id") or "") for item in mappings}
    if section_ids - mapped_sections:
        issues.append(_map_issue("coverage", "critical", f"课程知识映射未覆盖小节：{sorted(section_ids - mapped_sections)}"))
    if course_map.get("unresolved_candidates"):
        issues.append(_map_issue(
            "coverage",
            "major",
            f"仍有 {len(course_map.get('unresolved_candidates') or [])} 个课程局部知识待归一",
        ))
    valid_asset_knowledge_ids = local_ids
    for values in (assets or {}).values():
        if not isinstance(values, list):
            continue
        for asset in values:
            if not isinstance(asset, dict):
                continue
            invalid = set(str(item) for item in asset.get("concept_ids") or []) - valid_asset_knowledge_ids
            if invalid:
                issues.append(_map_issue("structure", "critical", f"学习资产引用不存在的正式知识或课程知识：{sorted(invalid)}"))
    for section in course_data.get("nodes") or []:
        for block in section.get("content_blocks") or []:
            refs = ((block.get("metadata") or {}).get("concept_refs") or [])
            invalid = set(str(item) for item in refs) - valid_asset_knowledge_ids
            if invalid:
                issues.append(_map_issue("structure", "critical", f"正文块引用不存在的知识条目：{sorted(invalid)}"))
    if course_knowledge_base:
        for mapping in mappings:
            invalid_local = {
                str(item) for item in mapping.get("course_knowledge_node_ids") or []
            } - local_ids
            if invalid_local:
                issues.append(_map_issue(
                    "structure",
                    "critical",
                    f"课程知识映射引用不存在的课程局部知识：{sorted(invalid_local)}",
                ))
        missing_local_sections = section_ids - {
            section_id
            for section_id, refs in (course_map.get("section_course_knowledge_ids") or {}).items()
            if refs
        }
        if missing_local_sections:
            issues.append(_map_issue(
                "coverage",
                "critical",
                f"课程知识映射未连接课程局部知识：{sorted(missing_local_sections)}",
            ))
    return _dedupe_issues(issues)


def _local_entries(structures: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for topic in structures:
        topic_name = str(topic.get("topic") or "")
        detail_status = str(topic.get("detail_status") or "outline_only")
        if detail_status == "refined":
            entries.append({
                "local_kind": "topic",
                "local_topic": topic_name,
                "local_name": topic_name,
                "local_description": str(topic.get("description") or ""),
                "local_capability": "",
                "detail_status": detail_status,
            })
        for point in topic.get("knowledge_points") or []:
            entries.append({
                "local_kind": "knowledge_point",
                "local_topic": topic_name,
                "local_name": str(point.get("name") or ""),
                "local_description": str(point.get("description") or ""),
                "local_capability": str(point.get("capability") or ""),
                "detail_status": detail_status,
            })
    return entries


def _mapping_scope(section: dict[str, Any], entry: dict[str, str]) -> str:
    """Exclude instructional scaffolding from formal knowledge coverage metrics."""
    section_name = _normalize_text(section.get("node_name") or section.get("title"))
    local_name = _normalize_text(entry.get("local_name"))
    pedagogical_section = any(
        marker in section_name
        for marker in (
            "前置知识诊断",
            "诊断测试",
            "项目设计",
            "项目实现",
            "章节总结",
            "课程总结",
        )
    )
    if entry.get("local_kind") == "topic" and (
        pedagogical_section
        or any(
            marker in local_name
            for marker in ("诊断评估", "系统设计", "项目实现", "章节总结")
        )
    ):
        return "pedagogical"
    if local_name in {
        "需求定义",
        "架构选择",
        "核心实现",
        "测试验证",
        "项目复盘",
        "学习总结",
    }:
        return "pedagogical"
    return "knowledge"


def _bind_section_blocks(
    section: dict[str, Any],
    mappings: list[dict[str, Any]],
    formal_nodes: dict[str, dict[str, Any]],
) -> None:
    for block in section.get("content_blocks") or []:
        metadata = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
        searchable = _normalize_text(
            f"{block.get('title') or ''} {block.get('content') or ''} {block.get('summary') or ''}"
        )
        formal_matches: list[str] = []
        mapping_matches: list[str] = []
        for mapping in mappings:
            terms = [mapping.get("local_name"), mapping.get("local_topic")]
            anchor = formal_nodes.get(str(mapping.get("anchor_knowledge_id") or ""))
            if anchor:
                terms.extend([anchor.get("name"), *(anchor.get("aliases") or [])])
            if not any(_term_matches(term, searchable) for term in terms):
                continue
            mapping_matches.append(str(mapping["mapping_id"]))
            formal_matches.extend(str(item) for item in mapping.get("knowledge_ids") or [])
            block_id = str(block.get("block_id") or "")
            mapping["block_ids"] = _unique([*(mapping.get("block_ids") or []), block_id])
            mapping["revision_id"] = _revision_id(mapping, "ckmr_")
        metadata["concept_refs"] = _unique(formal_matches)
        metadata["knowledge_mapping_refs"] = _unique(mapping_matches)
        metadata["knowledge_binding_status"] = "matched" if formal_matches else "unmapped"
        block["metadata"] = metadata


def _course_sequence_relations(course_id: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_ids = {str(section.get("node_id") or "") for section in sections}
    relations = []
    for section in sections:
        target = str(section.get("node_id") or "")
        for source in section.get("prerequisite_node_ids") or []:
            source_id = str(source)
            if source_id not in section_ids or not target:
                continue
            relation = {
                "relation_id": stable_hash({"course": course_id, "source": source_id, "target": target}, prefix="csr_"),
                "source_section_id": source_id,
                "target_section_id": target,
                "relation_type": "course_prerequisite",
                "source_status": "course_structure",
            }
            relation["revision_id"] = _revision_id(relation, "csrr_")
            relations.append(relation)
    return relations


def _section_evidence_ids(section: dict[str, Any]) -> list[str]:
    contract = section.get("grounding_contract") or {}
    return _unique([
        *[str(item) for item in section.get("evidence_refs") or []],
        *[str(item) for item in contract.get("required_evidence_ids") or []],
        *[str(item) for item in contract.get("optional_evidence_ids") or []],
    ])


def _normalize_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _term_matches(term: Any, searchable: str) -> bool:
    normalized = _normalize_text(term)
    return len(normalized) >= 2 and normalized in searchable


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _revision_id(item: dict[str, Any], prefix: str) -> str:
    return stable_hash({key: value for key, value in item.items() if key != "revision_id"}, prefix=prefix)


def _map_issue(gate: str, severity: str, message: str) -> dict[str, str]:
    return {"gate": gate, "severity": severity, "message": message}


def _dedupe_issues(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for issue in issues:
        key = (issue["gate"], issue["severity"], issue["message"])
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


__all__ = [
    "COURSE_MAP_SCHEMA",
    "compile_course_knowledge_map",
    "compile_legacy_subject_course_map",
    "knowledge_ids_for_section",
    "knowledge_names_for_section",
    "normalize_knowledge_structure",
    "project_course_knowledge_map",
    "project_learning_assets_to_knowledge",
    "validate_course_knowledge_map",
]
