"""Course-local knowledge structure compiled from one course blueprint."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_knowledge_map import compile_course_knowledge_map, normalize_knowledge_structure
from course_versioning import stable_hash
from subject_knowledge import knowledge_index, resolve_subject_library


COURSE_KNOWLEDGE_BASE_SCHEMA = "course_knowledge_base_v1"
COURSE_KNOWLEDGE_VIEW_SCHEMA = "knowledge_library_view_v2"


def compile_course_knowledge_base(
    course_data: dict[str, Any],
    *,
    library: dict[str, Any] | None = None,
    course_map: dict[str, Any] | None = None,
    assets: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Compile the course-local knowledge, capability, mistake and improvement tree."""
    course_id = str(course_data.get("course_id") or "")
    subject_library = deepcopy(library) if library is not None else resolve_subject_library(course_data)
    mapped = deepcopy(course_map) if course_map is not None else compile_course_knowledge_map(course_data, subject_library)
    mappings_by_section = _mappings_by_section(mapped)
    sections = [
        node for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    practice_by_section = _practice_refs_by_section(assets or {})

    nodes: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    capabilities: list[dict[str, Any]] = []
    mistakes: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    section_bindings: dict[str, dict[str, list[str]]] = {}
    point_name_to_id: dict[str, str] = {}
    prerequisite_names: dict[str, list[str]] = {}

    for section_order, section in enumerate(sections):
        section_id = str(section.get("node_id") or f"section-{section_order + 1}")
        structures = normalize_knowledge_structure(section)
        objective_refs = _unique([section.get("objective_id")])
        evidence_refs = _section_evidence_refs(section)
        practice_refs = practice_by_section.get(section_id, [])
        binding = {
            "knowledge_node_ids": [],
            "capability_point_ids": [],
            "mistake_point_ids": [],
            "improvement_point_ids": [],
        }
        section_point_order = 0

        for topic_order, topic in enumerate(structures):
            topic_name = str(topic.get("topic") or "").strip()
            if not topic_name:
                continue
            topic_id = _local_id(course_id, section_id, "topic", topic_name, "ckt_")
            topic_mappings = _matching_mappings(mappings_by_section.get(section_id, []), "topic", topic_name)
            topic_node = _knowledge_node(
                node_id=topic_id,
                parent_id=None,
                node_type="topic",
                name=topic_name,
                description=str(topic.get("description") or "").strip(),
                aliases=[],
                section_id=section_id,
                objective_refs=objective_refs,
                evidence_refs=evidence_refs,
                practice_refs=practice_refs,
                mappings=topic_mappings,
                order=(section_order * 100) + topic_order,
                source_status="course_blueprint",
                granularity_status=(
                    "adequate" if topic.get("detail_status") == "refined" else "needs_refinement"
                ),
            )
            nodes.append(topic_node)
            binding["knowledge_node_ids"].append(topic_id)

            points = list(topic.get("knowledge_points") or [])
            for point_order, point in enumerate(points):
                point_name = str(point.get("name") or "").strip()
                if not point_name:
                    continue
                point_id = _local_id(course_id, section_id, "knowledge_point", point_name, "ckp_")
                point_mappings = _matching_mappings(
                    mappings_by_section.get(section_id, []), "knowledge_point", point_name
                )
                point_node = _knowledge_node(
                    node_id=point_id,
                    parent_id=topic_id,
                    node_type="knowledge_point",
                    name=point_name,
                    description=str(point.get("description") or "").strip(),
                    aliases=_unique(point.get("aliases") or []),
                    section_id=section_id,
                    objective_refs=objective_refs,
                    evidence_refs=evidence_refs,
                    practice_refs=practice_refs,
                    mappings=point_mappings,
                    order=point_order,
                    source_status="course_blueprint",
                    granularity_status=_point_granularity_status(point),
                )
                nodes.append(point_node)
                binding["knowledge_node_ids"].append(point_id)
                point_name_to_id[_normalize_name(point_name)] = point_id
                prerequisite_names[point_id] = _unique(point.get("prerequisite_names") or [])
                relations.append(_relation(course_id, topic_id, point_id, "contains"))

                capability_values = _capability_values(point, point_name)
                point_capability_ids: list[str] = []
                for capability_order, capability_value in enumerate(capability_values):
                    capability = _normalize_standard(capability_value, "能力点")
                    capability_id = _local_id(
                        course_id, point_id, "capability", capability["name"], "ckc_"
                    )
                    capability_item = {
                        "capability_point_id": capability_id,
                        "knowledge_node_id": point_id,
                        "name": capability["name"],
                        "description": capability["description"],
                        "observable_behavior": capability["observable_behavior"] or capability["name"],
                        "section_refs": [section_id],
                        "objective_refs": objective_refs,
                        "practice_refs": practice_refs,
                        "source_status": capability["source_status"],
                        "order": capability_order,
                        "status": "active",
                    }
                    capability_item["revision_id"] = _revision_id(capability_item, "ckcr_")
                    capabilities.append(capability_item)
                    point_capability_ids.append(capability_id)
                    binding["capability_point_ids"].append(capability_id)
                    relations.append(_relation(course_id, point_id, capability_id, "develops"))

                primary_capability_id = point_capability_ids[0]
                point_mistakes = _standard_values(point, "mistake_points", "misconceptions")
                point_improvements = _standard_values(point, "improvement_points")
                if section_point_order == 0:
                    point_mistakes = [*point_mistakes, *(section.get("misconceptions") or [])]
                    point_improvements = [*point_improvements, *(section.get("assessment") or [])]

                for mistake_order, mistake_value in enumerate(_dedupe_standards(point_mistakes)):
                    mistake = _normalize_standard(mistake_value, "易错点")
                    mistake_id = _local_id(
                        course_id, primary_capability_id, "mistake", mistake["name"], "ckm_"
                    )
                    item = {
                        "mistake_point_id": mistake_id,
                        "capability_point_id": primary_capability_id,
                        "knowledge_node_id": point_id,
                        "name": mistake["name"],
                        "error_pattern": mistake["description"] or mistake["name"],
                        "repair_strategy": mistake["repair_strategy"],
                        "section_refs": [section_id],
                        "source_status": mistake["source_status"],
                        "order": mistake_order,
                        "status": "active",
                    }
                    item["revision_id"] = _revision_id(item, "ckmr_")
                    mistakes.append(item)
                    binding["mistake_point_ids"].append(mistake_id)
                    relations.append(_relation(course_id, primary_capability_id, mistake_id, "has_mistake"))

                for improvement_order, improvement_value in enumerate(
                    _dedupe_standards(point_improvements)
                ):
                    improvement = _normalize_standard(improvement_value, "提升点")
                    improvement_id = _local_id(
                        course_id,
                        primary_capability_id,
                        "improvement",
                        improvement["name"],
                        "cki_",
                    )
                    item = {
                        "improvement_point_id": improvement_id,
                        "capability_point_id": primary_capability_id,
                        "knowledge_node_id": point_id,
                        "name": improvement["name"],
                        "learning_goal": improvement["description"] or improvement["name"],
                        "practice_strategy": improvement["practice_strategy"],
                        "section_refs": [section_id],
                        "source_status": improvement["source_status"],
                        "order": improvement_order,
                        "status": "active",
                    }
                    item["revision_id"] = _revision_id(item, "ckir_")
                    improvements.append(item)
                    binding["improvement_point_ids"].append(improvement_id)
                    relations.append(_relation(course_id, primary_capability_id, improvement_id, "has_improvement"))
                section_point_order += 1

        section_bindings[section_id] = {
            key: _unique(values) for key, values in binding.items()
        }
        section["course_knowledge_refs"] = section_bindings[section_id]["knowledge_node_ids"]
        section["course_capability_refs"] = section_bindings[section_id]["capability_point_ids"]

    for point_id, names in prerequisite_names.items():
        for name in names:
            prerequisite_id = point_name_to_id.get(_normalize_name(name))
            if prerequisite_id and prerequisite_id != point_id:
                relations.append(_relation(course_id, prerequisite_id, point_id, "prerequisite"))

    payload = {
        "schema_version": COURSE_KNOWLEDGE_BASE_SCHEMA,
        "knowledge_base_id": stable_hash({"course": course_id, "kind": "knowledge_base"}, prefix="ckb_"),
        "course_id": course_id,
        "subject_code": str(subject_library.get("subject_id") or "course_local"),
        "formal_library_id": subject_library.get("library_id"),
        "formal_library_revision_id": subject_library.get("revision_id"),
        "root_node_ids": [
            str(node["node_id"]) for node in nodes if not node.get("parent_id")
        ],
        "nodes": nodes,
        "relations": _dedupe_relations(relations),
        "capability_points": capabilities,
        "mistake_points": mistakes,
        "improvement_points": improvements,
        "section_bindings": section_bindings,
        "generation_source_refs": _unique([
            course_data.get("blueprint_revision_id"),
            (course_data.get("course_blueprint") or {}).get("revision_id"),
            mapped.get("revision_id"),
        ]),
        "mapping_revision_id": mapped.get("revision_id"),
        "status": "active",
    }
    payload["revision_id"] = _revision_id(payload, "ckbr_")
    quality = validate_course_knowledge_base(
        payload,
        course_data=course_data,
        library=subject_library,
    )
    payload["quality_status"] = "failed" if quality["critical_count"] else (
        "completed_with_warnings" if quality["issues"] else "passed"
    )
    payload["quality_report"] = quality
    return payload


def validate_course_knowledge_base(
    knowledge_base: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
    library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if knowledge_base.get("schema_version") != COURSE_KNOWLEDGE_BASE_SCHEMA:
        issues.append(_issue("structure", "critical", "课程知识库格式不正确"))

    nodes = list(knowledge_base.get("nodes") or [])
    node_ids = [str(item.get("node_id") or "") for item in nodes]
    if not nodes:
        issues.append(_issue("coverage", "critical", "课程知识库没有可教学知识节点"))
    if not all(node_ids) or len(node_ids) != len(set(node_ids)):
        issues.append(_issue("structure", "critical", "课程知识节点 ID 必须非空且唯一"))
    node_id_set = set(node_ids)
    formal_ids = set(knowledge_index(library or {}))

    for node in nodes:
        node_id = str(node.get("node_id") or "")
        parent_id = str(node.get("parent_id") or "")
        if parent_id and parent_id not in node_id_set:
            issues.append(_issue("structure", "critical", f"知识节点 {node_id} 的父节点不存在"))
        invalid_formal = set(node.get("formal_knowledge_refs") or []) - formal_ids
        if invalid_formal:
            issues.append(_issue(
                "structure", "critical", f"知识节点 {node_id} 引用了不存在的正式知识"
            ))
        if node.get("node_type") == "knowledge_point":
            if not str(node.get("description") or "").strip():
                issues.append(_issue("granularity", "major", f"知识点「{node.get('name')}」缺少边界说明"))
            if not node.get("section_refs"):
                issues.append(_issue("coverage", "critical", f"知识点「{node.get('name')}」没有课程位置"))

    capability_ids = {
        str(item.get("capability_point_id") or "")
        for item in knowledge_base.get("capability_points") or []
    }
    capability_knowledge = {
        str(item.get("knowledge_node_id") or "")
        for item in knowledge_base.get("capability_points") or []
    }
    for node in nodes:
        if node.get("node_type") == "knowledge_point" and node.get("node_id") not in capability_knowledge:
            issues.append(_issue("standards", "critical", f"知识点「{node.get('name')}」没有能力点"))

    for collection, id_key in (
        (knowledge_base.get("mistake_points") or [], "mistake_point_id"),
        (knowledge_base.get("improvement_points") or [], "improvement_point_id"),
    ):
        ids = [str(item.get(id_key) or "") for item in collection]
        if not all(ids) or len(ids) != len(set(ids)):
            issues.append(_issue("structure", "critical", f"{id_key} 必须非空且唯一"))
        for item in collection:
            if str(item.get("capability_point_id") or "") not in capability_ids:
                issues.append(_issue("structure", "critical", f"{id_key} 没有合法能力点父级"))

    section_ids = {
        str(node.get("node_id") or "")
        for node in (course_data or {}).get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    }
    bound_sections = {
        section_id
        for section_id, refs in (knowledge_base.get("section_bindings") or {}).items()
        if (refs or {}).get("knowledge_node_ids")
    }
    if section_ids - bound_sections:
        issues.append(_issue(
            "coverage", "critical", f"课程知识库未覆盖小节：{sorted(section_ids - bound_sections)}"
        ))

    cycle = _find_prerequisite_cycle(knowledge_base.get("relations") or [])
    if cycle:
        issues.append(_issue("structure", "critical", f"课程知识前置关系存在循环：{' -> '.join(cycle)}"))

    critical_count = sum(item["severity"] == "critical" for item in issues)
    major_count = sum(item["severity"] == "major" for item in issues)
    return {
        "schema_version": "course_knowledge_quality_v1",
        "passed": critical_count == 0,
        "strict_passed": not issues,
        "critical_count": critical_count,
        "major_count": major_count,
        "issues": issues,
        "coverage": {
            "section_count": len(section_ids),
            "covered_section_count": len(section_ids & bound_sections),
            "knowledge_node_count": len(nodes),
            "knowledge_point_count": sum(item.get("node_type") == "knowledge_point" for item in nodes),
            "capability_point_count": len(knowledge_base.get("capability_points") or []),
            "mistake_point_count": len(knowledge_base.get("mistake_points") or []),
            "improvement_point_count": len(knowledge_base.get("improvement_points") or []),
        },
    }


def knowledge_binding_for_section(
    knowledge_base: dict[str, Any], section_id: str
) -> dict[str, list[str]]:
    binding = (knowledge_base.get("section_bindings") or {}).get(section_id) or {}
    return {
        "course_knowledge_refs": _unique(binding.get("knowledge_node_ids") or []),
        "course_capability_refs": _unique(binding.get("capability_point_ids") or []),
        "course_mistake_refs": _unique(binding.get("mistake_point_ids") or []),
        "course_improvement_refs": _unique(binding.get("improvement_point_ids") or []),
    }


def bind_course_knowledge_base_to_map(
    course_map: dict[str, Any],
    knowledge_base: dict[str, Any],
) -> dict[str, Any]:
    """Attach course-local knowledge identities to the existing coverage map."""
    enriched = deepcopy(course_map)
    nodes = list(knowledge_base.get("nodes") or [])
    nodes_by_mapping: dict[str, list[str]] = {}
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        for mapping_id in node.get("mapping_refs") or []:
            nodes_by_mapping.setdefault(str(mapping_id), []).append(node_id)
    for mapping in enriched.get("mappings") or []:
        mapping_id = str(mapping.get("mapping_id") or "")
        mapping["course_knowledge_node_ids"] = _unique(nodes_by_mapping.get(mapping_id, []))
        mapping["revision_id"] = _revision_id(mapping, "ckmr_")
    enriched["section_course_knowledge_ids"] = {
        section_id: _unique((binding or {}).get("knowledge_node_ids") or [])
        for section_id, binding in (knowledge_base.get("section_bindings") or {}).items()
    }
    coverage = dict(enriched.get("coverage") or {})
    coverage.update({
        "course_local_node_count": len(nodes),
        "course_local_knowledge_point_count": sum(
            item.get("node_type") == "knowledge_point" for item in nodes
        ),
        "course_local_coverage_status": (
            "covered" if enriched.get("section_course_knowledge_ids") else "missing"
        ),
    })
    enriched["coverage"] = coverage
    enriched["unresolved_candidates"] = [
        deepcopy(mapping) for mapping in enriched.get("mappings") or []
        if mapping.get("match_status") == "unmapped"
    ]
    enriched["revision_id"] = _revision_id(enriched, "ckmvr_")
    return enriched


def course_knowledge_base_prompt_context(
    knowledge_base: dict[str, Any], section_id: str
) -> str:
    binding = knowledge_binding_for_section(knowledge_base, section_id)
    knowledge_ids = set(binding["course_knowledge_refs"])
    capability_ids = set(binding["course_capability_refs"])
    knowledge = [
        item for item in knowledge_base.get("nodes") or []
        if item.get("node_id") in knowledge_ids and item.get("node_type") == "knowledge_point"
    ]
    capabilities = [
        item for item in knowledge_base.get("capability_points") or []
        if item.get("capability_point_id") in capability_ids
    ]
    mistakes = [
        item for item in knowledge_base.get("mistake_points") or []
        if item.get("mistake_point_id") in set(binding["course_mistake_refs"])
    ]
    improvements = [
        item for item in knowledge_base.get("improvement_points") or []
        if item.get("improvement_point_id") in set(binding["course_improvement_refs"])
    ]
    if not knowledge:
        return "当前小节尚未形成课程知识契约，必须先补齐可解释、可练习、可诊断的细知识点。"
    rows = ["本节正文、例子、练习和反馈必须围绕以下同一组教学坐标："]
    for item in knowledge:
        rows.append(f"- 知识点：{item.get('name')}；边界：{item.get('description') or '待补充'}")
        for capability in capabilities:
            if capability.get("knowledge_node_id") == item.get("node_id"):
                rows.append(f"  - 能力点：{capability.get('observable_behavior') or capability.get('name')}")
                for mistake in mistakes:
                    if mistake.get("capability_point_id") == capability.get("capability_point_id"):
                        rows.append(f"    - 易错点：{mistake.get('error_pattern') or mistake.get('name')}")
                for improvement in improvements:
                    if improvement.get("capability_point_id") == capability.get("capability_point_id"):
                        rows.append(f"    - 提升点：{improvement.get('learning_goal') or improvement.get('name')}")
    return "\n".join(rows)


def build_course_knowledge_library_view(
    knowledge_base: dict[str, Any],
    course_map: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Project a course-local knowledge base into the existing student read model."""
    bindings: dict[str, dict[str, set[str]]] = {}

    def binding(node_id: str) -> dict[str, set[str]]:
        return bindings.setdefault(node_id, {
            "section_ids": set(),
            "block_ids": set(),
            "objective_ids": set(),
            "question_ids": set(),
            "criterion_ids": set(),
            "misconception_ids": set(),
            "skill_unit_ids": set(),
            "mistake_point_ids": set(),
            "improvement_ids": set(),
        })

    for node in knowledge_base.get("nodes") or []:
        node_id = str(node.get("node_id") or "")
        entry = binding(node_id)
        entry["section_ids"].update(node.get("section_refs") or [])
        entry["block_ids"].update(node.get("course_block_refs") or [])
        entry["objective_ids"].update(node.get("objective_refs") or [])
    for capability in knowledge_base.get("capability_points") or []:
        binding(str(capability.get("knowledge_node_id") or ""))["skill_unit_ids"].add(
            str(capability.get("capability_point_id") or "")
        )
    for mistake in knowledge_base.get("mistake_points") or []:
        binding(str(mistake.get("knowledge_node_id") or ""))["mistake_point_ids"].add(
            str(mistake.get("mistake_point_id") or "")
        )
    for improvement in knowledge_base.get("improvement_points") or []:
        binding(str(improvement.get("knowledge_node_id") or ""))["improvement_ids"].add(
            str(improvement.get("improvement_point_id") or "")
        )
    for asset_type, id_key, binding_key in (
        ("questions", "question_id", "question_ids"),
        ("mastery_criteria", "criterion_id", "criterion_ids"),
        ("misconceptions", "misconception_id", "misconception_ids"),
    ):
        for asset in assets.get(asset_type) or []:
            asset_id = str(asset.get(id_key) or asset.get("asset_id") or "")
            for node_id in asset.get("course_knowledge_refs") or []:
                if node_id and asset_id:
                    binding(str(node_id))[binding_key].add(asset_id)

    source_nodes = list(knowledge_base.get("nodes") or [])
    by_id = {str(item.get("node_id") or ""): item for item in source_nodes}
    view_nodes = []
    for node in source_nodes:
        node_id = str(node.get("node_id") or "")
        path_ids, path_names = _local_path(by_id, node_id)
        entry = binding(node_id)
        projected = {
            "knowledge_id": node_id,
            "code": node_id,
            "parent_id": node.get("parent_id"),
            "node_type": node.get("node_type"),
            "name": node.get("name"),
            "description": node.get("description"),
            "depth": len(path_ids) - 1,
            "sort_order": int(node.get("order") or 0),
            "path_ids": path_ids,
            "path_names": path_names,
            "aliases": deepcopy(node.get("aliases") or []),
            "learning_actions": [],
            "typical_problems": [],
            "source_status": "course_local",
            "status": node.get("status", "active"),
            "revision_id": node.get("revision_id"),
            "formal_knowledge_refs": deepcopy(node.get("formal_knowledge_refs") or []),
            "identity_scope": "course_local",
        }
        for key, values in entry.items():
            projected[key] = sorted(value for value in values if value)
        projected["covered_by_course"] = bool(projected["section_ids"])
        view_nodes.append(projected)

    skill_units = [{
        "skill_unit_id": item.get("capability_point_id"),
        "name": item.get("name"),
        "learning_goal": item.get("description") or item.get("observable_behavior"),
        "observable_behaviors": [item.get("observable_behavior")],
        "primary_knowledge_id": item.get("knowledge_node_id"),
        "knowledge_ids": [item.get("knowledge_node_id")],
        "source_status": "course_local",
    } for item in knowledge_base.get("capability_points") or []]
    mistake_points = [{
        "mistake_point_id": item.get("mistake_point_id"),
        "skill_unit_id": item.get("capability_point_id"),
        "name": item.get("name"),
        "error_pattern": item.get("error_pattern"),
        "repair_strategy": item.get("repair_strategy"),
        "knowledge_ids": [item.get("knowledge_node_id")],
        "source_status": "course_local",
    } for item in knowledge_base.get("mistake_points") or []]
    improvement_points = [{
        "improvement_point_id": item.get("improvement_point_id"),
        "skill_unit_id": item.get("capability_point_id"),
        "name": item.get("name"),
        "learning_goal": item.get("learning_goal"),
        "practice_strategy": item.get("practice_strategy"),
        "knowledge_ids": [item.get("knowledge_node_id")],
        "source_status": "course_local",
    } for item in knowledge_base.get("improvement_points") or []]
    relations = [{
        "relation_id": item.get("relation_id"),
        "source_knowledge_id": item.get("source_id"),
        "target_knowledge_id": item.get("target_id"),
        "relation_type": item.get("relation_type"),
        "reason": item.get("reason", ""),
        "source_status": "course_local",
        "status": "accepted",
        "revision_id": item.get("revision_id"),
    } for item in knowledge_base.get("relations") or [] if item.get("source_id") in by_id and item.get("target_id") in by_id]
    payload = {
        "schema_version": COURSE_KNOWLEDGE_VIEW_SCHEMA,
        "library_id": knowledge_base.get("knowledge_base_id"),
        "subject_id": knowledge_base.get("subject_code") or "course_local",
        "library_version": knowledge_base.get("revision_id"),
        "root_node_id": next(iter(knowledge_base.get("root_node_ids") or []), ""),
        "nodes": view_nodes,
        "relations": relations,
        "skill_units": skill_units,
        "mistake_points": mistake_points,
        "improvement_points": improvement_points,
        "skill_relations": [],
        "usage_policy": {
            "ai_must_judge_independently": True,
            "allowed_fit": ["hit", "partial", "miss"],
            "may_invent_formal_ids": False,
            "personal_state_can_modify_library": False,
        },
        "course_map_revision_id": course_map.get("revision_id"),
        "course_knowledge_base_revision_id": knowledge_base.get("revision_id"),
        "coverage": {
            **deepcopy(course_map.get("coverage") or {}),
            "course_local_knowledge_count": len(view_nodes),
            "course_local_capability_count": len(skill_units),
            "status": "course_local",
        },
        "unresolved_mappings": deepcopy(course_map.get("unresolved_candidates") or []),
        "identity_scope": "course_local",
        "status": "active" if view_nodes else "unavailable",
    }
    payload["asset_id"] = stable_hash({
        "knowledge_base": knowledge_base.get("revision_id"),
        "course_map": course_map.get("revision_id"),
    }, prefix="ckv_")
    payload["revision_id"] = _revision_id(payload, "ckvr_")
    return payload


def _knowledge_node(
    *,
    node_id: str,
    parent_id: str | None,
    node_type: str,
    name: str,
    description: str,
    aliases: list[str],
    section_id: str,
    objective_refs: list[str],
    evidence_refs: list[str],
    practice_refs: list[str],
    mappings: list[dict[str, Any]],
    order: int,
    source_status: str,
    granularity_status: str,
) -> dict[str, Any]:
    formal_refs = _unique([
        ref for mapping in mappings for ref in mapping.get("knowledge_ids") or []
    ])
    block_refs = _unique([
        ref for mapping in mappings for ref in mapping.get("block_ids") or []
    ])
    item = {
        "node_id": node_id,
        "parent_id": parent_id,
        "node_type": node_type,
        "name": name,
        "description": description,
        "aliases": aliases,
        "granularity_status": granularity_status,
        "formal_knowledge_ref": next(iter(formal_refs), None),
        "formal_knowledge_refs": formal_refs,
        "mapping_refs": _unique([mapping.get("mapping_id") for mapping in mappings]),
        "source_refs": evidence_refs,
        "course_block_refs": block_refs,
        "section_refs": [section_id],
        "objective_refs": objective_refs,
        "practice_refs": practice_refs,
        "prerequisite_refs": [],
        "relation_refs": [],
        "source_status": source_status,
        "order": order,
        "status": "active",
    }
    item["revision_id"] = _revision_id(item, "cknr_")
    return item


def _mappings_by_section(course_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for mapping in course_map.get("mappings") or []:
        result.setdefault(str(mapping.get("section_id") or ""), []).append(mapping)
    return result


def _matching_mappings(
    mappings: list[dict[str, Any]], local_kind: str, name: str
) -> list[dict[str, Any]]:
    normalized = _normalize_name(name)
    return [
        mapping for mapping in mappings
        if mapping.get("local_kind") == local_kind
        and _normalize_name(mapping.get("local_name")) == normalized
    ]


def _capability_values(point: dict[str, Any], point_name: str) -> list[Any]:
    values = point.get("capability_points") or point.get("capabilities") or []
    if not isinstance(values, list):
        values = [values]
    if not values and point.get("capability"):
        values = [point.get("capability")]
    return values or [f"能够解释并在新情境中应用「{point_name}」"]


def _standard_values(point: dict[str, Any], *keys: str) -> list[Any]:
    result: list[Any] = []
    for key in keys:
        values = point.get(key) or []
        result.extend(values if isinstance(values, list) else [values])
    return result


def _normalize_standard(value: Any, fallback_label: str) -> dict[str, str]:
    if isinstance(value, dict):
        name = str(value.get("name") or value.get("label") or value.get("statement") or "").strip()
        return {
            "name": name or fallback_label,
            "description": str(value.get("description") or value.get("learning_goal") or "").strip(),
            "observable_behavior": str(value.get("observable_behavior") or value.get("capability") or "").strip(),
            "repair_strategy": str(value.get("repair_strategy") or "回到成立条件、关键步骤和反例进行对照检查").strip(),
            "practice_strategy": str(value.get("practice_strategy") or "换用新情境独立完成等价任务并说明依据").strip(),
            "source_status": str(value.get("source_status") or "course_blueprint"),
        }
    name = str(value or "").strip() or fallback_label
    return {
        "name": name,
        "description": "",
        "observable_behavior": name,
        "repair_strategy": "回到成立条件、关键步骤和反例进行对照检查",
        "practice_strategy": "换用新情境独立完成等价任务并说明依据",
        "source_status": "course_blueprint",
    }


def _point_granularity_status(point: dict[str, Any]) -> str:
    if not str(point.get("description") or "").strip():
        return "needs_refinement"
    if not _capability_values(point, str(point.get("name") or "")):
        return "needs_refinement"
    return "adequate"


def _practice_refs_by_section(
    assets: dict[str, list[dict[str, Any]]]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for asset_type in ("questions", "mastery_criteria", "misconceptions", "diagnostic_templates", "validation_questions"):
        for item in assets.get(asset_type) or []:
            asset_id = str(
                item.get("question_id")
                or item.get("criterion_id")
                or item.get("misconception_id")
                or item.get("asset_id")
                or item.get("revision_id")
                or ""
            )
            section_ids = _unique([item.get("node_id"), *(item.get("node_ids") or [])])
            for section_id in section_ids:
                if asset_id:
                    result.setdefault(section_id, []).append(asset_id)
    return {section_id: _unique(values) for section_id, values in result.items()}


def _section_evidence_refs(section: dict[str, Any]) -> list[str]:
    contract = section.get("grounding_contract") or {}
    return _unique([
        *(section.get("evidence_refs") or []),
        *(contract.get("required_evidence_ids") or []),
        *(contract.get("optional_evidence_ids") or []),
    ])


def _relation(
    course_id: str, source_id: str, target_id: str, relation_type: str
) -> dict[str, Any]:
    item = {
        "relation_id": stable_hash({
            "course": course_id,
            "source": source_id,
            "target": target_id,
            "type": relation_type,
        }, prefix="ckrel_"),
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "source_status": "course_blueprint",
        "status": "active",
    }
    item["revision_id"] = _revision_id(item, "ckrelr_")
    return item


def _dedupe_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relation in relations:
        relation_id = str(relation.get("relation_id") or "")
        if relation_id and relation_id not in seen:
            seen.add(relation_id)
            result.append(relation)
    return result


def _dedupe_standards(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_standard(value, "")
        key = _normalize_name(normalized["name"])
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _find_prerequisite_cycle(relations: list[dict[str, Any]]) -> list[str]:
    graph: dict[str, list[str]] = {}
    for relation in relations:
        if relation.get("relation_type") == "prerequisite":
            graph.setdefault(str(relation.get("source_id") or ""), []).append(
                str(relation.get("target_id") or "")
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


def _local_path(
    by_id: dict[str, dict[str, Any]], node_id: str
) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    names: list[str] = []
    current = by_id.get(node_id)
    while current:
        ids.append(str(current.get("node_id") or ""))
        names.append(str(current.get("name") or ""))
        current = by_id.get(str(current.get("parent_id") or ""))
    return list(reversed(ids)), list(reversed(names))


def _local_id(course_id: str, parent: str, kind: str, name: str, prefix: str) -> str:
    return stable_hash({
        "course": course_id,
        "parent": parent,
        "kind": kind,
        "name": _normalize_name(name),
    }, prefix=prefix)


def _normalize_name(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _revision_id(item: dict[str, Any], prefix: str) -> str:
    return stable_hash({key: value for key, value in item.items() if key != "revision_id"}, prefix=prefix)


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _issue(gate: str, severity: str, message: str) -> dict[str, str]:
    return {"gate": gate, "severity": severity, "message": message}


__all__ = [
    "COURSE_KNOWLEDGE_BASE_SCHEMA",
    "bind_course_knowledge_base_to_map",
    "build_course_knowledge_library_view",
    "compile_course_knowledge_base",
    "course_knowledge_base_prompt_context",
    "knowledge_binding_for_section",
    "validate_course_knowledge_base",
]
