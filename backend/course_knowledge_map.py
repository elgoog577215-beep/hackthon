"""Course-local coverage mapped onto an independent subject knowledge library."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from course_versioning import stable_hash
from subject_knowledge import (
    knowledge_index,
    knowledge_library_slice,
    match_subject_knowledge,
    resolve_subject_library,
    suggest_subject_knowledge,
)


COURSE_MAP_SCHEMA = "course_knowledge_map_v2"


def normalize_knowledge_structure(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize course-local outline concepts without promoting them to formal knowledge."""
    normalized: list[dict[str, Any]] = []
    for topic_index, raw_topic in enumerate(section.get("knowledge_structure") or []):
        if not isinstance(raw_topic, dict):
            continue
        topic_name = str(raw_topic.get("topic") or raw_topic.get("name") or "").strip()
        points = [
            point
            for point_index, raw_point in enumerate(raw_topic.get("knowledge_points") or [])
            if (point := _normalize_point(raw_point, point_index))
        ]
        if not topic_name or not points:
            continue
        normalized.append({
            "topic": topic_name,
            "description": str(raw_topic.get("description") or "").strip(),
            "knowledge_points": points,
            "detail_status": "refined",
            "order": topic_index,
        })

    if normalized:
        section["knowledge_structure"] = normalized
        section["key_points"] = _unique([
            point["name"]
            for topic in normalized
            for point in topic["knowledge_points"]
        ])
        return normalized

    names = _unique([
        str(item).strip()
        for item in section.get("key_points") or []
        if str(item).strip()
    ])
    if not names:
        names = [str(section.get("node_name") or section.get("title") or "本节内容").strip()]
    topic_name = str(section.get("node_name") or section.get("title") or "本节内容").strip()
    normalized = [{
        "topic": topic_name,
        "description": "来自课程大纲的局部表述，尚未完成课程内细化。",
        "knowledge_points": [{
            "name": name,
            "description": "",
            "capability": f"能够解释并在本节任务中应用「{name}」",
            "aliases": [],
            "prerequisite_names": [],
            "order": index,
        } for index, name in enumerate(names)],
        "detail_status": "outline_only",
        "order": 0,
    }]
    section["knowledge_structure"] = normalized
    section["key_points"] = names
    return normalized


def compile_course_knowledge_map(
    course_data: dict[str, Any],
    library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile deterministic course coverage without creating formal knowledge IDs."""
    subject_library = deepcopy(library) if library is not None else resolve_subject_library(course_data)
    formal_nodes = knowledge_index(subject_library)
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
                "suggestions": [] if match else suggest_subject_knowledge(subject_library, entry["local_name"]),
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

    sequence_relations = _course_sequence_relations(course_id, sections)
    knowledge_mappings = [
        mapping for mapping in mappings if mapping.get("mapping_scope") == "knowledge"
    ]
    unresolved = [
        deepcopy(mapping) for mapping in mappings
        if mapping.get("mapping_scope") == "knowledge"
        and mapping.get("match_status") == "unmapped"
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
        "asset_id": stable_hash({"course": course_id, "kind": "course_knowledge_map"}, prefix="ckma_"),
        "course_id": course_id,
        "knowledge_library_id": subject_library.get("library_id"),
        "knowledge_library_version": subject_library.get("version"),
        "knowledge_library_revision_id": subject_library.get("revision_id"),
        "binding_revision_id": (
            (course_data.get("knowledge_library_binding") or {}).get("revision_id")
        ),
        "library_lifecycle_status": subject_library.get(
            "lifecycle_status",
            "accepted" if subject_library.get("status") == "active" else "degraded",
        ),
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
        "status": "active" if formal_nodes else "library_unavailable",
    }
    payload["revision_id"] = _revision_id(payload, "ckmvr_")
    return payload


def project_course_knowledge_map(course_data: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(course_data)
    return compile_course_knowledge_map(projected)


def project_learning_assets_to_knowledge(
    course_data: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return a read-only current projection for legacy or current asset bundles."""
    from course_knowledge_base import (
        bind_course_knowledge_base_to_map,
        build_course_knowledge_library_view,
        compile_course_knowledge_base,
        knowledge_binding_for_section,
    )
    from subject_knowledge import build_knowledge_library_view

    projected_course = deepcopy(course_data)
    projected_assets = deepcopy(assets)
    library = resolve_subject_library(projected_course)
    course_map = compile_course_knowledge_map(projected_course, library)
    formal_ids = set(knowledge_index(library))
    legacy_mapping = _legacy_concept_mapping(projected_assets, library)

    for values in projected_assets.values():
        if not isinstance(values, list):
            continue
        for asset in values:
            if not isinstance(asset, dict):
                continue
            _project_asset_library_refs(
                asset,
                library=library,
                course_map=course_map,
                formal_ids=formal_ids,
                legacy_mapping=legacy_mapping,
            )

    course_knowledge_base = compile_course_knowledge_base(
        projected_course,
        library=library,
        course_map=course_map,
        assets=projected_assets,
    )
    course_map = bind_course_knowledge_base_to_map(course_map, course_knowledge_base)
    course_knowledge_base = compile_course_knowledge_base(
        projected_course,
        library=library,
        course_map=course_map,
        assets=projected_assets,
    )
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
                "course_capability_refs",
                "course_mistake_refs",
                "course_improvement_refs",
            ):
                asset[field] = _unique([
                    ref for binding in bindings for ref in binding.get(field) or []
                ])
            asset["course_knowledge_base_revision_id"] = course_knowledge_base.get("revision_id")

    knowledge_view = build_knowledge_library_view(library, course_map, projected_assets)
    if knowledge_view.get("status") == "unavailable":
        knowledge_view = build_course_knowledge_library_view(
            course_knowledge_base,
            course_map,
            projected_assets,
        )
    projected_assets.pop("knowledge_graph", None)
    projected_assets.pop("subject_knowledge", None)
    projected_assets.pop("teaching_standards", None)
    projected_assets["course_knowledge_base"] = [course_knowledge_base]
    projected_assets["course_knowledge_map"] = [course_map]
    projected_assets["knowledge_library"] = [knowledge_view]
    return projected_assets


def _project_asset_library_refs(
    asset: dict[str, Any],
    *,
    library: dict[str, Any],
    course_map: dict[str, Any],
    formal_ids: set[str],
    legacy_mapping: dict[str, str],
    fallback_concept_ids: list[str] | None = None,
) -> None:
    """Project legacy learning assets onto the current library without mutating storage."""
    original = [str(item) for item in asset.get("concept_ids") or [] if item]
    inferred = list(fallback_concept_ids or [])
    if not original:
        section_ids = [str(asset.get("node_id") or ""), *[str(item) for item in asset.get("node_ids") or []]]
        inferred = _unique([
            *inferred,
            *[
                knowledge_id
                for section_id in section_ids
                for knowledge_id in knowledge_ids_for_section(course_map, section_id)
                if section_id
            ],
        ])
    projected = _unique([
        item if item in formal_ids else legacy_mapping.get(item, "")
        for item in (original or inferred)
    ])
    if not projected:
        return

    changed = projected != original
    asset["concept_ids"] = projected
    library_slice = knowledge_library_slice(library, projected)
    for field, collection, id_key in (
        ("skill_unit_ids", "skill_units", "skill_unit_id"),
        ("mistake_point_ids", "mistake_points", "mistake_point_id"),
        ("improvement_point_ids", "improvement_points", "improvement_point_id"),
    ):
        available = _unique([
            str(item.get(id_key) or "") for item in library_slice.get(collection) or []
        ])
        existing = [str(item) for item in asset.get(field) or [] if item]
        valid_existing = [item for item in existing if item in set(available)]
        current = valid_existing or available
        if current != existing:
            changed = True
        asset[field] = current

    legacy_mistake_id = asset.pop("standard_mistake_id", None)
    if legacy_mistake_id and not asset.get("mistake_point_id"):
        mistake_ids = set(asset.get("mistake_point_ids") or [])
        if str(legacy_mistake_id) in mistake_ids:
            asset["mistake_point_id"] = str(legacy_mistake_id)
    if legacy_mistake_id is not None:
        changed = True

    guided_task = asset.get("guided_task")
    if isinstance(guided_task, dict):
        _project_asset_library_refs(
            guided_task,
            library=library,
            course_map=course_map,
            formal_ids=formal_ids,
            legacy_mapping=legacy_mapping,
            fallback_concept_ids=projected,
        )
    if changed:
        asset["knowledge_identity_status"] = "compatibility_projection"


def propose_kb_linkage_from_block_change(
    course_data: dict[str, Any],
    block_id: str,
    *,
    repository: Any,
    request_id: str,
    library: dict[str, Any] | None = None,
    course_map: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Content -> knowledge-base linkage.

    Call this right after a course block's content change has been durably
    applied - i.e. from the two call sites that represent "a block's content
    just became the new canonical text": `BlockRegenerationService.apply_candidate`
    (backend/block_regeneration.py) and `change_proposals.apply_item`
    (backend/change_proposals.py). Both are wired in from the routers
    (backend/routers/block_regeneration.py, backend/routers/change_proposals.py)
    rather than from those two service modules themselves, so this feature does
    not require touching either of them.

    Uses the same keyword/term matching `compile_course_knowledge_map` already
    performs (`_bind_section_blocks` / `_term_matches`) to find which formal
    knowledge nodes are already bound to `block_id`. For each match, emits one
    pending `source="kb_link"`, `target_kind="kg_node"` change-proposal item
    suggesting the linked knowledge node definition be reviewed. This function
    NEVER edits the knowledge library - it only produces a pending proposal via
    `change_proposals.create_proposal`; an operator (or a future knowledge-edit
    command) must still apply it.
    """
    from change_proposals import create_proposal

    subject_library = library if library is not None else resolve_subject_library(course_data)
    resolved_map = course_map if course_map is not None else compile_course_knowledge_map(
        deepcopy(course_data), subject_library
    )
    formal_nodes = knowledge_index(subject_library)

    target_block = _find_course_block(course_data, block_id)
    if target_block is None:
        return None

    candidate_mappings = [
        mapping for mapping in resolved_map.get("mappings") or []
        if block_id in (mapping.get("block_ids") or [])
        and mapping.get("match_status") not in (None, "unmapped")
        and mapping.get("anchor_knowledge_id")
    ]
    if not candidate_mappings:
        return None

    block_text = f"{target_block.get('title') or ''} {target_block.get('content') or ''}".strip()
    items: list[dict[str, Any]] = []
    kg_target_ids: list[str] = []
    for mapping in candidate_mappings:
        node_id = str(mapping["anchor_knowledge_id"])
        node = formal_nodes.get(node_id)
        if not node or node_id in kg_target_ids:
            continue
        kg_target_ids.append(node_id)
        items.append({
            "block_id": node_id,
            "target_kind": "kg_node",
            "before": {
                "knowledge_id": node_id,
                "name": node.get("name"),
                "description": node.get("description"),
                "aliases": node.get("aliases"),
            },
            "after": {
                "note": "课程正文已变更，建议核对该知识节点定义是否需要同步更新。",
                "source_block_id": block_id,
                "source_block_text_excerpt": block_text[:200],
            },
            "reason": (
                f"课程正文块 {block_id} 的内容变更已被接受，其关联的知识节点"
                f"「{node.get('name')}」（{node_id}）可能需要同步复核。"
                "注意：本条目的目标是知识库节点，不是课程正文块。"
            ),
        })
    if not items:
        return None

    return create_proposal(
        repository,
        str(course_data.get("course_id") or ""),
        request_id=request_id,
        scope="block",
        target_block_ids=kg_target_ids,
        items=items,
        source="kb_link",
        generation_meta={
            "linkage_direction": "content_to_kb",
            "trigger_block_id": block_id,
        },
    )


def _find_course_block(course_data: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    for node in course_data.get("nodes") or []:
        for block in node.get("content_blocks") or []:
            if str(block.get("block_id") or "") == block_id:
                return block
    return None


def knowledge_ids_for_section(course_map: dict[str, Any], section_id: str) -> list[str]:
    return _unique(list((course_map.get("section_knowledge_ids") or {}).get(section_id) or []))


def knowledge_names_for_section(
    course_map: dict[str, Any],
    section_id: str,
    library: dict[str, Any] | None = None,
) -> list[str]:
    formal = knowledge_index(library or {})
    names = [
        str(formal[knowledge_id].get("name") or "")
        for knowledge_id in knowledge_ids_for_section(course_map, section_id)
        if knowledge_id in formal
    ]
    if names:
        return _unique(names)
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
    subject_library = library or resolve_subject_library(course_data)
    formal_ids = set(knowledge_index(subject_library))
    mappings = list(course_map.get("mappings") or [])
    mapping_ids = [str(item.get("mapping_id") or "") for item in mappings]
    if not all(mapping_ids) or len(mapping_ids) != len(set(mapping_ids)):
        issues.append(_map_issue("structure", "critical", "课程知识映射 ID 必须非空且唯一"))
    for mapping in mappings:
        refs = {
            str(item) for item in [mapping.get("anchor_knowledge_id"), *(mapping.get("knowledge_ids") or [])]
            if item
        }
        invalid = refs - formal_ids
        if invalid:
            issues.append(_map_issue("structure", "critical", f"映射引用不存在的正式知识：{sorted(invalid)}"))
        if mapping.get("match_status") == "unmapped" and refs:
            issues.append(_map_issue("semantic", "critical", "待归一映射不得携带正式知识 ID"))
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
    for values in (assets or {}).values():
        if not isinstance(values, list):
            continue
        for asset in values:
            if not isinstance(asset, dict):
                continue
            invalid = set(str(item) for item in asset.get("concept_ids") or []) - formal_ids
            if invalid:
                issues.append(_map_issue("structure", "critical", f"学习资产引用不存在的正式知识：{sorted(invalid)}"))
    for section in course_data.get("nodes") or []:
        for block in section.get("content_blocks") or []:
            refs = ((block.get("metadata") or {}).get("concept_refs") or [])
            invalid = set(str(item) for item in refs) - formal_ids
            if invalid:
                issues.append(_map_issue("structure", "critical", f"正文块引用不存在的正式知识：{sorted(invalid)}"))
    course_knowledge_base = next(iter((assets or {}).get("course_knowledge_base") or []), None)
    if course_knowledge_base:
        local_ids = {
            str(item.get("node_id") or "")
            for item in course_knowledge_base.get("nodes") or []
        }
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


def _legacy_concept_mapping(
    assets: dict[str, list[dict[str, Any]]],
    library: dict[str, Any],
) -> dict[str, str]:
    legacy_graph = next(iter(assets.get("knowledge_graph") or []), {})
    mapping: dict[str, str] = {}
    for concept in legacy_graph.get("concepts") or []:
        match = match_subject_knowledge(library, concept.get("label"))
        if concept.get("concept_id") and match:
            mapping[str(concept["concept_id"])] = str(match["anchor_knowledge_id"])
    for node in legacy_graph.get("nodes") or []:
        match = match_subject_knowledge(library, node.get("name"))
        if node.get("knowledge_id") and match:
            mapping[str(node["knowledge_id"])] = str(match["anchor_knowledge_id"])
    return mapping


def _normalize_point(raw_point: Any, order: int) -> dict[str, Any] | None:
    if isinstance(raw_point, str):
        name = raw_point.strip()
        raw: dict[str, Any] = {}
    elif isinstance(raw_point, dict):
        raw = raw_point
        name = str(raw.get("name") or raw.get("knowledge_point") or "").strip()
    else:
        return None
    if not name:
        return None
    return {
        "name": name,
        "description": str(raw.get("description") or "").strip(),
        "capability": str(raw.get("capability") or f"能够解释并应用「{name}」").strip(),
        "capability_points": _normalize_standard_points(
            raw.get("capability_points") or raw.get("capabilities") or []
        ),
        "mistake_points": _normalize_standard_points(
            raw.get("mistake_points") or raw.get("misconceptions") or []
        ),
        "improvement_points": _normalize_standard_points(
            raw.get("improvement_points") or []
        ),
        "aliases": _unique([str(item).strip() for item in raw.get("aliases") or []]),
        "prerequisite_names": _unique([str(item).strip() for item in raw.get("prerequisite_names") or []]),
        "order": order,
    }


def _normalize_standard_points(values: Any) -> list[Any]:
    if not isinstance(values, list):
        values = [values] if values else []
    normalized: list[Any] = []
    for value in values:
        if isinstance(value, dict):
            item = {
                key: current
                for key, current in value.items()
                if key in {
                    "name", "label", "statement", "description", "learning_goal",
                    "observable_behavior", "capability", "repair_strategy",
                    "practice_strategy", "source_status",
                }
            }
            if any(str(item.get(key) or "").strip() for key in ("name", "label", "statement")):
                normalized.append(item)
        elif str(value).strip():
            normalized.append(str(value).strip())
    return normalized


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
    "knowledge_ids_for_section",
    "knowledge_names_for_section",
    "normalize_knowledge_structure",
    "project_course_knowledge_map",
    "propose_kb_linkage_from_block_change",
    "project_learning_assets_to_knowledge",
    "validate_course_knowledge_map",
]
