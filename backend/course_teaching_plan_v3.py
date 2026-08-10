"""Normalization, validation and deterministic assembly for teaching-plan V3."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_versioning import stable_hash

FORMAL_KNOWLEDGE_RELATION_TYPES = {
    "prerequisite",
    "derives",
    "equivalent_to",
    "contrasts_with",
    "applies_to",
    "generalizes",
}


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(
        text for value in values if (text := str(value or "").strip())
    ))


def _optional_int(value: Any, *, lower: int = 1, upper: int = 240) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper:
        return value
    return None


def _section_execution(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "planned_minutes": _optional_int(raw.get("planned_minutes")),
        "key_difficulties": _unique(list(raw.get("key_difficulties") or [])),
        "teacher_activities": _unique(list(raw.get("teacher_activities") or [])),
        "student_activities": _unique(list(raw.get("student_activities") or [])),
        "resource_refs": _unique(list(raw.get("resource_refs") or [])),
        "in_class_checks": _unique(list(raw.get("in_class_checks") or [])),
        "homework": _unique(list(raw.get("homework") or [])),
        "teaching_notes": _unique(list(raw.get("teaching_notes") or [])),
    }
    return {key: value for key, value in fields.items() if value not in (None, [])}


def _module_execution(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "planned_minutes": _optional_int(raw.get("planned_minutes")),
        "teacher_activity": str(raw.get("teacher_activity") or "").strip(),
        "student_activity": str(raw.get("student_activity") or "").strip(),
    }
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": "blocking"}


def promote_course_teaching_plan_v3(
    payload: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    """Wrap a valid compact/legacy plan in the one official V3 envelope.

    Compact planning already contains the same section knowledge and teaching
    intent as the batched path. The only missing V3 field is a stable revision
    for the embedded whole-course identity decision. Building that revision
    locally keeps small courses at one model call while ensuring every newly
    persisted official plan has the same public schema.
    """
    sections = [
        deepcopy(section)
        for section in payload.get("sections") or []
        if isinstance(section, dict)
    ]
    skeleton_revision_id = str(
        payload.get("skeleton_revision_id") or ""
    ).strip()
    if not skeleton_revision_id:
        identity_contract = {
            "schema_version": "course_teaching_plan_identity_v3",
            "source_outline_revision_id": outline_revision_id,
            "sections": [
                {
                    "node_id": str(section.get("node_id") or ""),
                    "owned_knowledge": [
                        {
                            "name": str(point.get("name") or ""),
                            "statement": str(point.get("statement") or ""),
                            "prerequisite_names": _unique(
                                list(point.get("prerequisite_names") or [])
                            ),
                        }
                        for group in section.get("knowledge_structure") or []
                        if isinstance(group, dict)
                        for point in group.get("knowledge_points") or []
                        if isinstance(point, dict)
                    ],
                    "reused_knowledge_names": _unique(
                        list(section.get("reused_knowledge_names") or [])
                    ),
                    "module_bindings": [
                        {
                            "module_id": str(module.get("module_id") or ""),
                            "knowledge_names": _unique(
                                list(module.get("knowledge_names") or [])
                            ),
                        }
                        for module in section.get("teaching_modules") or []
                        if isinstance(module, dict)
                    ],
                }
                for section in sections
            ],
        }
        skeleton_revision_id = stable_hash(
            identity_contract,
            prefix="teaching_skeleton_",
        )

    upgraded = {
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": (
            str(payload.get("source_outline_revision_id") or "").strip()
            or outline_revision_id
        ),
        "skeleton_revision_id": skeleton_revision_id,
        "sections": sections,
    }
    upgraded["revision_id"] = stable_hash(upgraded, prefix="teaching_")
    return upgraded


# Deterministic shape repair for knowledge-detail entries.
#
# Models reliably produce the right *content* but drift on the *shape*: a bare
# string where an object is required, or a synonym for the canonical key. Those
# drifts are mechanical, so repairing them here removes a whole class of
# correction round-trips.
#
# This repairs shape only. A field whose content is genuinely absent stays
# absent so the validator still rejects the batch — inventing a mastery
# criterion or a repair strategy would pass the quality gate with content no
# teacher wrote.
_CAPABILITY_ALIASES = {
    "observable_behavior": "observable_behavior",
    "behavior": "observable_behavior",
    "observable": "observable_behavior",
    "capability": "observable_behavior",
    "description": "observable_behavior",
}
_MASTERY_ALIASES = {
    "observable_performance": "observable_performance",
    "performance": "observable_performance",
    "observable": "observable_performance",
    "criterion": "observable_performance",
    "standard": "observable_performance",
    "verification_method": "verification_method",
    "verification": "verification_method",
    "method": "verification_method",
    "evidence": "verification_method",
    "how_to_verify": "verification_method",
}
_MISCONCEPTION_ALIASES = {
    "observable_error_pattern": "observable_error_pattern",
    "error_pattern": "observable_error_pattern",
    "error": "observable_error_pattern",
    "mistake": "observable_error_pattern",
    "symptom": "observable_error_pattern",
    "discrimination": "discrimination",
    "discriminator": "discrimination",
    "diagnosis": "discrimination",
    "why": "discrimination",
    "root_cause": "discrimination",
    "repair_strategy": "repair_strategy",
    "repair": "repair_strategy",
    "remediation": "repair_strategy",
    "fix": "repair_strategy",
    "correction": "repair_strategy",
}


def _repair_detail_entry(
    raw: Any,
    *,
    aliases: dict[str, str],
    primary_field: str,
) -> dict[str, Any]:
    """Coerce one capability/criterion/misconception into its canonical shape."""
    if isinstance(raw, str):
        text = raw.strip()
        return {primary_field: text} if text else {}
    if not isinstance(raw, dict):
        return {}
    repaired: dict[str, Any] = deepcopy(raw)
    for key, value in raw.items():
        canonical = aliases.get(str(key).strip().lower())
        if canonical is None:
            continue
        # Never let an alias clobber a canonical field the model already filled.
        if str(repaired.get(canonical) or "").strip():
            continue
        if isinstance(value, str) and value.strip():
            repaired[canonical] = value.strip()
        elif isinstance(value, list):
            joined = "；".join(
                item.strip() for item in value
                if isinstance(item, str) and item.strip()
            )
            if joined:
                repaired[canonical] = joined
    return repaired


def _repair_detail_list(
    values: Any,
    *,
    aliases: dict[str, str],
    primary_field: str,
) -> list[dict[str, Any]]:
    if isinstance(values, (str, dict)):
        values = [values]
    if not isinstance(values, list):
        return []
    repaired = [
        _repair_detail_entry(item, aliases=aliases, primary_field=primary_field)
        for item in values
    ]
    return [item for item in repaired if item]


def normalize_teaching_plan_skeleton_v3(
    payload: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    registry: list[dict[str, Any]] = []
    for raw in payload.get("knowledge_registry") or []:
        if not isinstance(raw, dict):
            continue
        registry.append({
            "knowledge_key": str(raw.get("knowledge_key") or "").strip(),
            "name": str(raw.get("name") or "").strip(),
            "statement": str(raw.get("statement") or "").strip(),
            "owner_node_id": str(raw.get("owner_node_id") or "").strip(),
            "reused_in_node_ids": _unique(list(raw.get("reused_in_node_ids") or [])),
            "prerequisite_keys": _unique(list(raw.get("prerequisite_keys") or [])),
            "module_ids": _unique(list(raw.get("module_ids") or [])),
        })
    sections: list[dict[str, Any]] = []
    for raw in payload.get("sections") or []:
        if not isinstance(raw, dict):
            continue
        sections.append({
            "node_id": str(raw.get("node_id") or "").strip(),
            "owned_knowledge_keys": _unique(list(raw.get("owned_knowledge_keys") or [])),
            "reused_knowledge_keys": _unique(list(raw.get("reused_knowledge_keys") or [])),
        })
    normalized = {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "source_outline_revision_id": outline_revision_id,
        "knowledge_registry": registry,
        "sections": sections,
    }
    normalized["revision_id"] = stable_hash(normalized, prefix="teaching_skeleton_")
    return normalized


def compile_course_knowledge_graph_draft(
    skeleton: dict[str, Any],
) -> dict[str, Any]:
    """Project the reconciled skeleton into an upstream knowledge graph draft.

    Identity and prerequisite direction are frozen before detailed teaching-plan
    batches run. Later batches enrich these nodes without changing their owner,
    reuse positions or prerequisite edges.
    """
    registry = [
        item for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    known_keys = {
        str(item.get("knowledge_key") or "") for item in registry
        if str(item.get("knowledge_key") or "")
    }
    nodes = [{
        "knowledge_key": str(item.get("knowledge_key") or ""),
        "name": str(item.get("name") or ""),
        "statement": str(item.get("statement") or ""),
        "owner_node_id": str(item.get("owner_node_id") or ""),
        "reused_in_node_ids": list(item.get("reused_in_node_ids") or []),
        "module_ids": list(item.get("module_ids") or []),
        "detail_status": "pending_enrichment",
    } for item in registry]
    edges: list[dict[str, Any]] = []
    invalid_prerequisite_keys: list[str] = []
    for item in registry:
        target_key = str(item.get("knowledge_key") or "")
        for prerequisite_key in item.get("prerequisite_keys") or []:
            source_key = str(prerequisite_key or "")
            if source_key not in known_keys or target_key not in known_keys:
                invalid_prerequisite_keys.append(source_key or target_key)
                continue
            edge = {
                "source_knowledge_key": source_key,
                "target_knowledge_key": target_key,
                "relation_type": "prerequisite",
                "direction": "source_before_target",
            }
            edge["edge_id"] = stable_hash(edge, prefix="ckgd_edge_")
            edges.append(edge)
    section_bindings = [{
        "node_id": str(item.get("node_id") or ""),
        "owned_knowledge_keys": list(item.get("owned_knowledge_keys") or []),
        "reused_knowledge_keys": list(item.get("reused_knowledge_keys") or []),
    } for item in skeleton.get("sections") or [] if isinstance(item, dict)]
    incoming = {
        str(edge.get("target_knowledge_key") or "") for edge in edges
    }
    topological_order, cyclic_keys = _knowledge_graph_topology(
        [str(item.get("knowledge_key") or "") for item in registry],
        edges,
    )
    draft = {
        "schema_version": "course_knowledge_graph_draft_v1",
        "source_outline_revision_id": str(
            skeleton.get("source_outline_revision_id") or ""
        ),
        "source_skeleton_revision_id": str(skeleton.get("revision_id") or ""),
        "nodes": nodes,
        "edges": edges,
        "section_bindings": section_bindings,
        "topology": {
            "is_dag": not invalid_prerequisite_keys and not cyclic_keys,
            "topological_order": topological_order,
            "root_knowledge_keys": [
                str(item.get("knowledge_key") or "")
                for item in registry
                if str(item.get("knowledge_key") or "") not in incoming
            ],
        },
        "quality": {
            "identity_count": len(nodes),
            "prerequisite_edge_count": len(edges),
            "section_binding_count": len(section_bindings),
            "invalid_prerequisite_keys": list(dict.fromkeys(invalid_prerequisite_keys)),
            "cyclic_knowledge_keys": cyclic_keys,
        },
        "status": "identity_frozen" if nodes and not invalid_prerequisite_keys and not cyclic_keys else "needs_review",
    }
    draft["revision_id"] = stable_hash(draft, prefix="ckgd_")
    return draft


def restore_teaching_plan_skeleton_from_graph_draft(
    graph_draft: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    """Recover the exact frozen skeleton from its durable graph projection.

    A process interruption can leave the mutable teaching-stage skeleton at a
    partial shard while the already frozen knowledge graph and accepted model
    batches are still intact. The graph projection preserves every identity,
    owner, reuse binding, module binding and prerequisite edge needed to
    reconstruct the skeleton. Only return it when the deterministic revision
    matches the graph's recorded source revision; otherwise callers must
    regenerate instead of guessing identities.
    """
    if not isinstance(graph_draft, dict):
        return {}
    if (
        graph_draft.get("schema_version")
        != "course_knowledge_graph_draft_v1"
        or graph_draft.get("status") not in {
            "identity_frozen",
            "knowledge_frozen",
        }
        or graph_draft.get("source_outline_revision_id")
        != outline_revision_id
    ):
        return {}
    source_revision = str(
        graph_draft.get("source_skeleton_revision_id") or ""
    )
    if not source_revision:
        return {}

    prerequisite_keys: dict[str, list[str]] = {}
    for edge in graph_draft.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if (
            edge.get("relation_type") != "prerequisite"
            or edge.get("direction") != "source_before_target"
        ):
            continue
        source = str(edge.get("source_knowledge_key") or "")
        target = str(edge.get("target_knowledge_key") or "")
        if source and target:
            prerequisite_keys.setdefault(target, []).append(source)

    restored = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [{
            "knowledge_key": str(node.get("knowledge_key") or ""),
            "name": str(node.get("name") or ""),
            "statement": str(node.get("statement") or ""),
            "owner_node_id": str(node.get("owner_node_id") or ""),
            "reused_in_node_ids": list(
                node.get("reused_in_node_ids") or []
            ),
            "prerequisite_keys": prerequisite_keys.get(
                str(node.get("knowledge_key") or ""),
                [],
            ),
            "module_ids": list(node.get("module_ids") or []),
        } for node in graph_draft.get("nodes") or [] if isinstance(node, dict)],
        "sections": [
            binding
            for binding in graph_draft.get("section_bindings") or []
            if isinstance(binding, dict)
        ],
    }, outline_revision_id=outline_revision_id)
    if restored.get("revision_id") != source_revision:
        return {}
    return restored


def _knowledge_graph_topology(
    knowledge_keys: list[str],
    edges: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    ordered_keys = list(dict.fromkeys(key for key in knowledge_keys if key))
    indegree = {key: 0 for key in ordered_keys}
    outgoing: dict[str, list[str]] = {key: [] for key in ordered_keys}
    for edge in edges:
        source = str(edge.get("source_knowledge_key") or "")
        target = str(edge.get("target_knowledge_key") or "")
        if source not in indegree or target not in indegree:
            continue
        outgoing[source].append(target)
        indegree[target] += 1
    queue = [key for key in ordered_keys if indegree[key] == 0]
    result: list[str] = []
    while queue:
        source = queue.pop(0)
        result.append(source)
        for target in outgoing[source]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    cyclic = [key for key in ordered_keys if key not in result]
    return result, cyclic


def validate_teaching_plan_skeleton_v3(
    skeleton: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = [str(item.get("node_id") or "") for item in sections]
    actual_ids = [str(item.get("node_id") or "") for item in skeleton.get("sections") or []]
    allowed_modules = {
        str(section.get("node_id") or ""): {
            str(module.get("module_id") or "")
            for module in section.get("module_plan") or []
            if isinstance(module, dict)
        }
        for section in sections
    }
    issues: list[dict[str, str]] = []
    if actual_ids != expected_ids:
        issues.append(_issue(
            "teaching_skeleton:section_order_mismatch",
            "全课知识职责骨架必须按目录顺序完整覆盖所有小节",
        ))
    registry = [item for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)]
    keys = [str(item.get("knowledge_key") or "") for item in registry]
    names = [str(item.get("name") or "") for item in registry]
    key_set = set(keys)
    if not registry or any(not key for key in keys):
        issues.append(_issue("teaching_skeleton:missing_key", "每个知识点必须有稳定 knowledge_key"))
    if len(keys) != len(key_set):
        issues.append(_issue("teaching_skeleton:duplicate_key", "knowledge_key 在全课必须唯一"))
    if any(not name for name in names) or len(names) != len(set(names)):
        issues.append(_issue("teaching_skeleton:invalid_name", "知识规范名称必须非空且全课唯一"))

    section_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or [] if isinstance(item, dict)
    }
    section_order = {node_id: index for index, node_id in enumerate(expected_ids)}
    registry_order = {key: index for index, key in enumerate(keys)}
    ownership: dict[str, str] = {}
    declared_reuse: dict[str, set[str]] = {}
    for node_id in expected_ids:
        identity = section_by_id.get(node_id) or {}
        owned = list(identity.get("owned_knowledge_keys") or [])
        reused = list(identity.get("reused_knowledge_keys") or [])
        if not owned:
            issues.append(_issue(
                "teaching_skeleton:empty_owner",
                f"小节 {node_id} 至少要首次负责一个原子知识点",
            ))
        if len(owned) > 8:
            issues.append(_issue(
                "teaching_skeleton:owner_budget_exceeded",
                f"小节 {node_id} 首次负责的知识点超过 8 个，无法进入有界详细批次",
            ))
        for key in owned:
            if key not in key_set:
                issues.append(_issue("teaching_skeleton:unknown_owned_key", f"小节 {node_id} 引用了未知知识键 {key}"))
            if key in ownership:
                issues.append(_issue("teaching_skeleton:duplicate_owner", f"知识键 {key} 只能由一个小节首次负责"))
            ownership[key] = node_id
        for key in reused:
            if key not in ownership:
                issues.append(_issue("teaching_skeleton:future_reuse", f"小节 {node_id} 只能复用前序小节已负责的知识键 {key}"))
            declared_reuse.setdefault(key, set()).add(node_id)

    registry_by_key = {str(item.get("knowledge_key") or ""): item for item in registry}
    for key, owner in ownership.items():
        item = registry_by_key.get(key) or {}
        if str(item.get("owner_node_id") or "") != owner:
            issues.append(_issue("teaching_skeleton:owner_mismatch", f"知识键 {key} 的 owner_node_id 与小节职责不一致"))
        if not str(item.get("statement") or "").strip():
            issues.append(_issue("teaching_skeleton:missing_statement", f"知识键 {key} 缺少规范陈述"))
        prerequisite_keys = list(item.get("prerequisite_keys") or [])
        if set(prerequisite_keys) - key_set:
            issues.append(_issue("teaching_skeleton:unknown_prerequisite", f"知识键 {key} 引用了未知前置知识"))
        for prerequisite_key in prerequisite_keys:
            prerequisite_owner = ownership.get(prerequisite_key, "")
            if prerequisite_key not in key_set:
                continue
            if (
                section_order.get(prerequisite_owner, len(expected_ids))
                > section_order.get(owner, -1)
                or (
                    prerequisite_owner == owner
                    and registry_order.get(prerequisite_key, len(keys))
                    >= registry_order.get(key, -1)
                )
            ):
                issues.append(_issue(
                    "teaching_skeleton:future_prerequisite",
                    f"知识键 {key} 只能引用本节更早位置或前序小节的前置知识 {prerequisite_key}",
                ))
        if set(item.get("module_ids") or []) - allowed_modules.get(owner, set()):
            issues.append(_issue("teaching_skeleton:unknown_module", f"知识键 {key} 绑定了本节不允许的课程块"))
        if not item.get("module_ids"):
            issues.append(_issue("teaching_skeleton:missing_module", f"知识键 {key} 至少要绑定一个本节允许的课程块"))
        if set(item.get("reused_in_node_ids") or []) != declared_reuse.get(key, set()):
            issues.append(_issue("teaching_skeleton:reuse_mismatch", f"知识键 {key} 的注册表复用位置与小节职责不一致"))
    if set(ownership) != key_set:
        issues.append(_issue("teaching_skeleton:unowned_key", "知识注册表中的每个键都必须有唯一首次负责小节"))
    return {
        "schema_version": "course_teaching_plan_skeleton_validation_v3",
        "passed": not issues,
        "issues": issues,
        "blocking_issues": issues,
        "actual": {"section_count": len(actual_ids), "knowledge_point_count": len(keys)},
    }


def normalize_teaching_plan_batch_v3(
    payload: dict[str, Any],
    *,
    batch_id: str,
    skeleton_revision_id: str,
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for raw_section in payload.get("sections") or []:
        if not isinstance(raw_section, dict):
            continue
        details = []
        for raw in raw_section.get("knowledge_details") or []:
            if not isinstance(raw, dict):
                continue
            details.append({
                "knowledge_key": str(raw.get("knowledge_key") or "").strip(),
                "concept_group": str(raw.get("concept_group") or "核心机制").strip(),
                "group_description": str(raw.get("group_description") or "").strip(),
                "knowledge_type": str(raw.get("knowledge_type") or "concept").strip(),
                "conditions": _unique(list(raw.get("conditions") or [])),
                "boundaries": _unique(list(raw.get("boundaries") or [])),
                "counterexamples": _unique(list(raw.get("counterexamples") or [])),
                "capability_points": _repair_detail_list(
                    raw.get("capability_points"),
                    aliases=_CAPABILITY_ALIASES,
                    primary_field="observable_behavior",
                ),
                "misconceptions": _repair_detail_list(
                    raw.get("misconceptions"),
                    aliases=_MISCONCEPTION_ALIASES,
                    primary_field="observable_error_pattern",
                ),
                "mastery_criteria": _repair_detail_list(
                    raw.get("mastery_criteria"),
                    aliases=_MASTERY_ALIASES,
                    primary_field="observable_performance",
                ),
                "aliases": _unique(list(raw.get("aliases") or [])),
                "positive_examples": _unique(
                    list(raw.get("positive_examples") or [])
                ),
                "source_refs": _unique(list(raw.get("source_refs") or [])),
                "confidence": str(raw.get("confidence") or "").strip(),
            })
        relations = []
        for raw in raw_section.get("knowledge_relations") or []:
            if isinstance(raw, dict):
                relations.append({
                    **deepcopy(raw),
                    "source_key": str(raw.get("source_key") or "").strip(),
                    "target_key": str(raw.get("target_key") or "").strip(),
                })
        modules = []
        for raw in raw_section.get("teaching_modules") or []:
            if isinstance(raw, dict):
                modules.append({
                    "module_id": str(raw.get("module_id") or "").strip(),
                    "teaching_purpose": str(raw.get("teaching_purpose") or "").strip(),
                    "knowledge_keys": _unique(list(raw.get("knowledge_keys") or [])),
                    "teaching_guidance": str(raw.get("teaching_guidance") or "").strip(),
                    **_module_execution(raw),
                })
        sections.append({
            "node_id": str(raw_section.get("node_id") or "").strip(),
            "knowledge_details": details,
            "knowledge_relations": relations,
            "teaching_modules": modules,
            **_section_execution(raw_section),
        })
    normalized = {
        "schema_version": "course_teaching_plan_batch_v3",
        "batch_id": batch_id,
        "skeleton_revision_id": skeleton_revision_id,
        "sections": sections,
    }
    normalized["revision_id"] = stable_hash(normalized, prefix="teaching_batch_")
    return normalized


def normalize_course_knowledge_batch_v1(
    payload: dict[str, Any],
    *,
    batch_id: str,
    skeleton_revision_id: str,
) -> dict[str, Any]:
    """Normalize the knowledge engineer's output without accepting teaching data."""
    combined = normalize_teaching_plan_batch_v3(
        payload,
        batch_id=batch_id,
        skeleton_revision_id=skeleton_revision_id,
    )
    normalized = {
        "schema_version": "course_knowledge_batch_v1",
        "batch_id": batch_id,
        "skeleton_revision_id": skeleton_revision_id,
        "sections": [
            {
                "node_id": str(section.get("node_id") or ""),
                "knowledge_details": deepcopy(
                    section.get("knowledge_details") or []
                ),
                "knowledge_relations": deepcopy(
                    section.get("knowledge_relations") or []
                ),
            }
            for section in combined.get("sections") or []
            if isinstance(section, dict)
        ],
    }
    normalized["revision_id"] = stable_hash(
        normalized,
        prefix="knowledge_batch_",
    )
    return normalized


def normalize_teaching_execution_batch_v1(
    payload: dict[str, Any],
    *,
    batch_id: str,
    skeleton_revision_id: str,
    knowledge_revision_id: str,
) -> dict[str, Any]:
    """Normalize teaching execution while discarding any attempted knowledge edits."""
    combined = normalize_teaching_plan_batch_v3(
        payload,
        batch_id=batch_id,
        skeleton_revision_id=skeleton_revision_id,
    )
    normalized = {
        "schema_version": "teaching_execution_batch_v1",
        "batch_id": batch_id,
        "skeleton_revision_id": skeleton_revision_id,
        "knowledge_revision_id": knowledge_revision_id,
        "sections": [
            {
                "node_id": str(section.get("node_id") or ""),
                "teaching_modules": deepcopy(
                    section.get("teaching_modules") or []
                ),
                **_section_execution(section),
            }
            for section in combined.get("sections") or []
            if isinstance(section, dict)
        ],
    }
    normalized["revision_id"] = stable_hash(
        normalized,
        prefix="teaching_execution_batch_",
    )
    return normalized


def validate_teaching_plan_batch_v3(
    batch: dict[str, Any],
    *,
    batch_spec: dict[str, Any],
    skeleton: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = list(batch_spec.get("section_ids") or [])
    actual_ids = [str(item.get("node_id") or "") for item in batch.get("sections") or []]
    issues: list[dict[str, str]] = []
    if actual_ids != expected_ids:
        issues.append(_issue("teaching_batch:section_mismatch", f"批次 {batch.get('batch_id')} 必须精确覆盖指定小节"))
    identity_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or [] if isinstance(item, dict)
    }
    section_by_id = {str(item.get("node_id") or ""): item for item in sections}
    section_order = {
        str(item.get("node_id") or ""): index
        for index, item in enumerate(sections)
    }
    owner_by_key = {
        str(item.get("knowledge_key") or ""): str(item.get("owner_node_id") or "")
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    }
    registry_keys = {
        str(item.get("knowledge_key") or "")
        for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)
    }
    actual_by_id = {str(item.get("node_id") or ""): item for item in batch.get("sections") or [] if isinstance(item, dict)}
    for node_id in expected_ids:
        identity = identity_by_id.get(node_id) or {}
        expected_keys = list(identity.get("owned_knowledge_keys") or [])
        actual = actual_by_id.get(node_id) or {}
        detail_keys = [str(item.get("knowledge_key") or "") for item in actual.get("knowledge_details") or []]
        if detail_keys != expected_keys:
            issues.append(_issue("teaching_batch:knowledge_key_mismatch", f"小节 {node_id} 必须逐个展开骨架冻结的知识键"))
        allowed_keys = set(expected_keys) | set(identity.get("reused_knowledge_keys") or [])
        available_relation_keys = {
            key
            for key, owner_node_id in owner_by_key.items()
            if section_order.get(owner_node_id, len(sections))
            <= section_order.get(node_id, -1)
        }
        allowed_modules = {
            str(item.get("module_id") or "")
            for item in (section_by_id.get(node_id) or {}).get("module_plan") or []
            if isinstance(item, dict)
        }
        for detail in actual.get("knowledge_details") or []:
            key = str(detail.get("knowledge_key") or "")
            if not detail.get("capability_points") or not detail.get("mastery_criteria"):
                issues.append(_issue("teaching_batch:unobservable_mastery", f"知识键 {key} 必须有可观察能力与掌握标准"))
            if not detail.get("misconceptions"):
                issues.append(_issue("teaching_batch:missing_misconception", f"知识键 {key} 必须包含至少一个可信易错点"))
            for capability in detail.get("capability_points") or []:
                if not isinstance(capability, dict) or not str(
                    capability.get("observable_behavior") or ""
                ).strip():
                    issues.append(_issue("teaching_batch:empty_capability", f"知识键 {key} 的能力必须给出可观察行为"))
            for criterion in detail.get("mastery_criteria") or []:
                if (
                    not isinstance(criterion, dict)
                    or not str(criterion.get("observable_performance") or "").strip()
                    or not str(criterion.get("verification_method") or "").strip()
                ):
                    issues.append(_issue("teaching_batch:empty_mastery", f"知识键 {key} 的掌握标准必须可观察、可验证"))
            for misconception in detail.get("misconceptions") or []:
                if (
                    not isinstance(misconception, dict)
                    or not str(misconception.get("observable_error_pattern") or "").strip()
                    or not str(misconception.get("discrimination") or "").strip()
                    or not str(misconception.get("repair_strategy") or "").strip()
                ):
                    issues.append(_issue("teaching_batch:invalid_misconception", f"知识键 {key} 的易错点必须包含错误表现、判别与修复策略"))
        for relation in actual.get("knowledge_relations") or []:
            if relation.get("source_key") not in registry_keys or relation.get("target_key") not in registry_keys:
                issues.append(_issue("teaching_batch:unknown_relation_endpoint", f"小节 {node_id} 的知识关系引用了未知知识键"))
            elif (
                relation.get("source_key") not in available_relation_keys
                or relation.get("target_key") not in available_relation_keys
            ):
                issues.append(_issue("teaching_batch:future_relation_endpoint", f"小节 {node_id} 的知识关系引用了未来批次保留的知识键"))
            elif not ({relation.get("source_key"), relation.get("target_key")} & set(expected_keys)):
                issues.append(_issue("teaching_batch:unrelated_relation", f"小节 {node_id} 只能返回至少连接一个本节新知识的关系"))
            relation_type = str(relation.get("relation_type") or "")
            if relation_type not in FORMAL_KNOWLEDGE_RELATION_TYPES:
                issues.append(_issue(
                    "teaching_batch:invalid_relation_type",
                    f"小节 {node_id} 的知识关系类型 {relation_type or '空'} 不在六类正式关系中",
                ))
            if not str(relation.get("reason") or "").strip():
                issues.append(_issue(
                    "teaching_batch:relation_missing_reason",
                    f"小节 {node_id} 的知识关系缺少具体语义理由",
                ))
            if relation_type == "derives" and not relation.get("derivation_steps"):
                issues.append(_issue(
                    "teaching_batch:derivation_missing_steps",
                    f"小节 {node_id} 的推导关系缺少关键步骤",
                ))
            if relation_type == "contrasts_with" and not str(
                relation.get("distinction") or ""
            ).strip():
                issues.append(_issue(
                    "teaching_batch:contrast_missing_distinction",
                    f"小节 {node_id} 的对比关系缺少判别维度",
                ))
        for module in actual.get("teaching_modules") or []:
            if module.get("module_id") not in allowed_modules:
                issues.append(_issue("teaching_batch:unknown_module", f"小节 {node_id} 返回了不允许的课程块"))
            if set(module.get("knowledge_keys") or []) - allowed_keys:
                issues.append(_issue("teaching_batch:unknown_module_knowledge", f"小节 {node_id} 的课程块越过了冻结知识边界"))
    return {
        "schema_version": "course_teaching_plan_batch_validation_v3",
        "passed": not issues,
        "issues": issues,
        "blocking_issues": issues,
        "actual": {"section_count": len(actual_ids)},
    }


def validate_course_knowledge_batch_v1(
    batch: dict[str, Any],
    *,
    batch_spec: dict[str, Any],
    skeleton: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate knowledge semantics and keep prerequisite identity immutable."""
    compatibility = {
        **batch,
        "schema_version": "course_teaching_plan_batch_v3",
    }
    base = validate_teaching_plan_batch_v3(
        compatibility,
        batch_spec=batch_spec,
        skeleton=skeleton,
        sections=sections,
    )
    issues = list(base.get("blocking_issues") or [])
    expected_ids = set(batch_spec.get("section_ids") or [])
    registry = [
        item
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    expected_prerequisites = {
        (str(prerequisite_key), str(item.get("knowledge_key") or ""))
        for item in registry
        if str(item.get("owner_node_id") or "") in expected_ids
        for prerequisite_key in item.get("prerequisite_keys") or []
    }
    actual_prerequisites = {
        (
            str(relation.get("source_key") or ""),
            str(relation.get("target_key") or ""),
        )
        for section in batch.get("sections") or []
        if isinstance(section, dict)
        for relation in section.get("knowledge_relations") or []
        if isinstance(relation, dict)
        and relation.get("relation_type") == "prerequisite"
    }
    for source, target in sorted(
        actual_prerequisites - expected_prerequisites
    ):
        issues.append(_issue(
            "knowledge_batch:changed_prerequisite",
            f"知识批次不得新增或改写冻结前置关系 {source} -> {target}",
        ))
    for source, target in sorted(
        expected_prerequisites - actual_prerequisites
    ):
        issues.append(_issue(
            "knowledge_batch:missing_prerequisite_semantics",
            f"冻结前置关系 {source} -> {target} 必须补充具体语义理由",
        ))
    section_by_id = {
        str(item.get("node_id") or ""): item
        for item in sections
        if isinstance(item, dict)
    }
    for section in batch.get("sections") or []:
        if not isinstance(section, dict):
            continue
        node_id = str(section.get("node_id") or "")
        allowed_source_refs = {
            str(item.get("evidence_id") or "")
            for item in (section_by_id.get(node_id) or {}).get(
                "evidence_hints"
            ) or []
            if isinstance(item, dict)
            and str(item.get("evidence_id") or "")
        }
        for detail in section.get("knowledge_details") or []:
            if not isinstance(detail, dict):
                continue
            key = str(detail.get("knowledge_key") or "")
            source_refs = set(detail.get("source_refs") or [])
            if source_refs - allowed_source_refs:
                issues.append(_issue(
                    "knowledge_batch:unapproved_source_ref",
                    f"知识键 {key} 引用了未准入的资料标识",
                ))
            confidence = str(detail.get("confidence") or "")
            if confidence not in {"high", "medium", "low"}:
                issues.append(_issue(
                    "knowledge_batch:invalid_confidence",
                    f"知识键 {key} 必须声明 high、medium 或 low 置信度",
                ))
            if not source_refs and confidence == "high":
                issues.append(_issue(
                    "knowledge_batch:ungrounded_high_confidence",
                    f"知识键 {key} 无准入来源时不得声明高置信",
                ))
        for relation in section.get("knowledge_relations") or []:
            if not isinstance(relation, dict):
                continue
            if set(relation.get("source_refs") or []) - allowed_source_refs:
                issues.append(_issue(
                    "knowledge_batch:unapproved_relation_source_ref",
                    f"小节 {node_id} 的知识关系引用了未准入资料标识",
                ))
    return {
        "schema_version": "course_knowledge_batch_validation_v1",
        "passed": not issues,
        "issues": issues,
        "blocking_issues": issues,
        "actual": deepcopy(base.get("actual") or {}),
    }


def validate_teaching_execution_batch_v1(
    batch: dict[str, Any],
    *,
    batch_spec: dict[str, Any],
    skeleton: dict[str, Any],
    sections: list[dict[str, Any]],
    knowledge_revision_id: str,
) -> dict[str, Any]:
    """Validate a lesson-plan batch against the frozen knowledge contract."""
    issues: list[dict[str, str]] = []
    expected_ids = [str(item) for item in batch_spec.get("section_ids") or []]
    actual_sections = [
        item
        for item in batch.get("sections") or []
        if isinstance(item, dict)
    ]
    actual_ids = [str(item.get("node_id") or "") for item in actual_sections]
    if actual_ids != expected_ids:
        issues.append(_issue(
            "teaching_execution:section_mismatch",
            f"批次 {batch.get('batch_id')} 必须按顺序精确覆盖指定小节",
        ))
    if str(batch.get("knowledge_revision_id") or "") != knowledge_revision_id:
        issues.append(_issue(
            "teaching_execution:knowledge_revision_mismatch",
            "教案批次必须绑定当前冻结知识修订",
        ))

    identity_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or []
        if isinstance(item, dict)
    }
    section_by_id = {
        str(item.get("node_id") or ""): item
        for item in sections
        if isinstance(item, dict)
    }
    actual_by_id = {
        str(item.get("node_id") or ""): item for item in actual_sections
    }
    for node_id in expected_ids:
        identity = identity_by_id.get(node_id) or {}
        allowed_keys = set(identity.get("owned_knowledge_keys") or []) | set(
            identity.get("reused_knowledge_keys") or []
        )
        required_owned_keys = set(identity.get("owned_knowledge_keys") or [])
        section = section_by_id.get(node_id) or {}
        expected_module_ids = [
            str(item.get("module_id") or "")
            for item in section.get("module_plan") or []
            if isinstance(item, dict) and str(item.get("module_id") or "")
        ]
        actual = actual_by_id.get(node_id) or {}
        modules = [
            item
            for item in actual.get("teaching_modules") or []
            if isinstance(item, dict)
        ]
        actual_module_ids = [
            str(item.get("module_id") or "") for item in modules
        ]
        if actual_module_ids != expected_module_ids:
            issues.append(_issue(
                "teaching_execution:module_coverage_mismatch",
                f"小节 {node_id} 必须按顺序精确覆盖已选课程块",
            ))
        covered_keys: set[str] = set()
        for module in modules:
            module_id = str(module.get("module_id") or "")
            module_keys = set(module.get("knowledge_keys") or [])
            covered_keys.update(module_keys)
            if not module_keys or module_keys - allowed_keys:
                issues.append(_issue(
                    "teaching_execution:invalid_module_knowledge",
                    f"小节 {node_id} 的课程块 {module_id} 必须仅绑定本节冻结知识",
                ))
            for field, label in (
                ("teaching_purpose", "教学目的"),
                ("teaching_guidance", "具体讲法"),
                ("teacher_activity", "教师动作"),
                ("student_activity", "学生动作"),
            ):
                if not str(module.get(field) or "").strip():
                    issues.append(_issue(
                        "teaching_execution:empty_module_field",
                        f"小节 {node_id} 的课程块 {module_id} 缺少{label}",
                    ))
        if required_owned_keys - covered_keys:
            issues.append(_issue(
                "teaching_execution:uncovered_owned_knowledge",
                f"小节 {node_id} 存在未落入任一课程块的首次负责知识",
            ))
        for field, label in (
            ("key_difficulties", "重点难点"),
            ("teacher_activities", "教师活动"),
            ("student_activities", "学生活动"),
            ("in_class_checks", "课堂检查"),
            ("homework", "作业或迁移任务"),
        ):
            if not actual.get(field):
                issues.append(_issue(
                    "teaching_execution:missing_section_execution",
                    f"小节 {node_id} 缺少{label}",
                ))
    return {
        "schema_version": "teaching_execution_batch_validation_v1",
        "passed": not issues,
        "issues": issues,
        "blocking_issues": issues,
        "actual": {"section_count": len(actual_ids)},
    }


def compile_frozen_course_knowledge_graph(
    *,
    skeleton: dict[str, Any],
    knowledge_batches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Freeze enriched knowledge before any teaching execution is generated."""
    identity = compile_course_knowledge_graph_draft(skeleton)
    issues: list[dict[str, str]] = []
    if identity.get("status") != "identity_frozen":
        issues.append(_issue(
            "knowledge_freeze:identity_not_frozen",
            "知识身份与前置 DAG 未通过冻结",
        ))
    details_by_key: dict[str, dict[str, Any]] = {}
    returned_relations: list[dict[str, Any]] = []
    for batch in knowledge_batches:
        for section in batch.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for detail in section.get("knowledge_details") or []:
                if not isinstance(detail, dict):
                    continue
                key = str(detail.get("knowledge_key") or "")
                if key in details_by_key:
                    issues.append(_issue(
                        "knowledge_freeze:duplicate_detail",
                        f"知识键 {key} 被多个批次重复展开",
                    ))
                details_by_key[key] = deepcopy(detail)
            returned_relations.extend(
                deepcopy(relation)
                for relation in section.get("knowledge_relations") or []
                if isinstance(relation, dict)
            )

    registry = [
        item
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    registry_keys = {
        str(item.get("knowledge_key") or "") for item in registry
    }
    nodes: list[dict[str, Any]] = []
    for canonical in registry:
        key = str(canonical.get("knowledge_key") or "")
        detail = details_by_key.get(key)
        if detail is None:
            issues.append(_issue(
                "knowledge_freeze:missing_detail",
                f"知识键 {key} 尚未完成语义、能力与掌握标准展开",
            ))
            detail = {}
        nodes.append({
            **deepcopy(canonical),
            **deepcopy(detail),
            "knowledge_key": key,
            "name": str(canonical.get("name") or ""),
            "statement": str(canonical.get("statement") or ""),
            "owner_node_id": str(canonical.get("owner_node_id") or ""),
            "reused_in_node_ids": list(
                canonical.get("reused_in_node_ids") or []
            ),
            "prerequisite_keys": list(
                canonical.get("prerequisite_keys") or []
            ),
            "module_ids": list(canonical.get("module_ids") or []),
            "detail_status": "frozen" if detail else "missing",
        })
    unknown_detail_keys = set(details_by_key) - registry_keys
    for key in sorted(unknown_detail_keys):
        issues.append(_issue(
            "knowledge_freeze:unknown_detail",
            f"知识批次返回了未冻结的知识键 {key}",
        ))

    edges: list[dict[str, Any]] = []
    edge_signatures: set[tuple[str, str, str]] = set()
    for relation in returned_relations:
        source = str(relation.get("source_key") or "")
        target = str(relation.get("target_key") or "")
        relation_type = str(relation.get("relation_type") or "")
        signature = (source, target, relation_type)
        if source not in registry_keys or target not in registry_keys:
            issues.append(_issue(
                "knowledge_freeze:unknown_relation_endpoint",
                f"知识关系 {source} -> {target} 引用了未知知识键",
            ))
            continue
        if relation_type not in FORMAL_KNOWLEDGE_RELATION_TYPES:
            issues.append(_issue(
                "knowledge_freeze:invalid_relation_type",
                f"知识关系类型 {relation_type or '空'} 不在正式六类关系中",
            ))
            continue
        if signature in edge_signatures:
            continue
        edge_signatures.add(signature)
        edge = {
            **deepcopy(relation),
            "source_knowledge_key": source,
            "target_knowledge_key": target,
        }
        if relation_type == "prerequisite":
            edge["direction"] = "source_before_target"
        edge.pop("source_key", None)
        edge.pop("target_key", None)
        edge["edge_id"] = stable_hash(edge, prefix="ckgf_edge_")
        edges.append(edge)

    expected_prerequisites = {
        (str(prerequisite), str(item.get("knowledge_key") or ""))
        for item in registry
        for prerequisite in item.get("prerequisite_keys") or []
    }
    actual_prerequisites = {
        (
            str(edge.get("source_knowledge_key") or ""),
            str(edge.get("target_knowledge_key") or ""),
        )
        for edge in edges
        if edge.get("relation_type") == "prerequisite"
    }
    if actual_prerequisites != expected_prerequisites:
        issues.append(_issue(
            "knowledge_freeze:prerequisite_identity_mismatch",
            "知识详情批次不得改变骨架冻结的前置 DAG",
        ))
    prerequisite_edges = [
        edge for edge in edges if edge.get("relation_type") == "prerequisite"
    ]
    topological_order, cyclic_keys = _knowledge_graph_topology(
        [str(item.get("knowledge_key") or "") for item in registry],
        prerequisite_edges,
    )
    if cyclic_keys:
        issues.append(_issue(
            "knowledge_freeze:prerequisite_cycle",
            f"前置关系存在循环：{' -> '.join(cyclic_keys)}",
        ))
    frozen = {
        "schema_version": "course_knowledge_graph_draft_v1",
        "source_outline_revision_id": str(
            skeleton.get("source_outline_revision_id") or ""
        ),
        "source_skeleton_revision_id": str(skeleton.get("revision_id") or ""),
        "nodes": nodes,
        "edges": edges,
        "section_bindings": deepcopy(identity.get("section_bindings") or []),
        "topology": {
            "is_dag": not cyclic_keys,
            "topological_order": topological_order,
            "root_knowledge_keys": [
                key for key in topological_order
                if key not in {
                    target for _source, target in expected_prerequisites
                }
            ],
        },
        "quality": {
            "knowledge_point_count": len(nodes),
            "relation_count": len(edges),
            "formal_relation_types_used": sorted({
                str(edge.get("relation_type") or "") for edge in edges
            }),
            "issues": deepcopy(issues),
            "blocking_issue_count": len(issues),
        },
        "status": "knowledge_frozen" if nodes and not issues else "needs_review",
    }
    frozen["revision_id"] = stable_hash(frozen, prefix="ckgf_")
    return frozen


def merge_knowledge_and_teaching_batches(
    *,
    knowledge_batches: list[dict[str, Any]],
    teaching_batches: list[dict[str, Any]],
    skeleton_revision_id: str,
) -> list[dict[str, Any]]:
    """Create the legacy assembly shape after both independent stages pass."""
    knowledge_by_node = {
        str(section.get("node_id") or ""): section
        for batch in knowledge_batches
        for section in batch.get("sections") or []
        if isinstance(section, dict)
    }
    merged: list[dict[str, Any]] = []
    for teaching_batch in teaching_batches:
        sections: list[dict[str, Any]] = []
        for teaching in teaching_batch.get("sections") or []:
            if not isinstance(teaching, dict):
                continue
            node_id = str(teaching.get("node_id") or "")
            knowledge = knowledge_by_node.get(node_id) or {}
            sections.append({
                "node_id": node_id,
                "knowledge_details": deepcopy(
                    knowledge.get("knowledge_details") or []
                ),
                "knowledge_relations": deepcopy(
                    knowledge.get("knowledge_relations") or []
                ),
                "teaching_modules": deepcopy(
                    teaching.get("teaching_modules") or []
                ),
                **_section_execution(teaching),
            })
        batch_id = str(teaching_batch.get("batch_id") or "")
        payload = {
            "schema_version": "course_teaching_plan_batch_v3",
            "batch_id": batch_id,
            "skeleton_revision_id": skeleton_revision_id,
            "sections": sections,
        }
        payload["revision_id"] = stable_hash(
            payload,
            prefix="teaching_batch_",
        )
        merged.append(payload)
    return merged


def assemble_course_teaching_plan_v3(
    *,
    skeleton: dict[str, Any],
    batches: list[dict[str, Any]],
    outline_revision_id: str,
) -> dict[str, Any]:
    """Assemble one official plan independent of batch completion order."""
    registry = {
        str(item.get("knowledge_key") or ""): item
        for item in skeleton.get("knowledge_registry") or [] if isinstance(item, dict)
    }
    details_by_id = {
        str(item.get("node_id") or ""): item
        for batch in batches
        for item in batch.get("sections") or []
        if isinstance(item, dict)
    }
    planned_sections: list[dict[str, Any]] = []
    for identity in skeleton.get("sections") or []:
        node_id = str(identity.get("node_id") or "")
        expanded = details_by_id.get(node_id) or {}
        groups: list[dict[str, Any]] = []
        group_by_name: dict[str, dict[str, Any]] = {}
        for detail in expanded.get("knowledge_details") or []:
            key = str(detail.get("knowledge_key") or "")
            canonical = registry.get(key) or {}
            group_name = str(detail.get("concept_group") or "核心机制")
            group = group_by_name.get(group_name)
            if group is None:
                group = {
                    "concept_group": group_name,
                    "description": str(detail.get("group_description") or ""),
                    "knowledge_points": [],
                }
                groups.append(group)
                group_by_name[group_name] = group
            group["knowledge_points"].append({
                "name": str(canonical.get("name") or key),
                "statement": str(canonical.get("statement") or ""),
                "knowledge_type": str(detail.get("knowledge_type") or "concept"),
                "conditions": list(detail.get("conditions") or []),
                "boundaries": list(detail.get("boundaries") or []),
                "counterexamples": list(detail.get("counterexamples") or []),
                "entry_reason": (
                    "这是本课程的知识入口。"
                    if not canonical.get("prerequisite_keys") else ""
                ),
                "prerequisite_names": [
                    str((registry.get(item) or {}).get("name") or item)
                    for item in canonical.get("prerequisite_keys") or []
                ],
                "capability_points": deepcopy(detail.get("capability_points") or []),
                "misconceptions": deepcopy(detail.get("misconceptions") or []),
                "mastery_criteria": deepcopy(detail.get("mastery_criteria") or []),
                "aliases": list(detail.get("aliases") or []),
                "positive_examples": list(
                    detail.get("positive_examples") or []
                ),
                "source_refs": list(detail.get("source_refs") or []),
                "confidence": str(detail.get("confidence") or ""),
            })
        relations = []
        for relation in expanded.get("knowledge_relations") or []:
            source = registry.get(str(relation.get("source_key") or "")) or {}
            target = registry.get(str(relation.get("target_key") or "")) or {}
            relations.append({
                **deepcopy(relation),
                "source_name": str(source.get("name") or ""),
                "target_name": str(target.get("name") or ""),
            })
            relations[-1].pop("source_key", None)
            relations[-1].pop("target_key", None)
        modules = []
        for module in expanded.get("teaching_modules") or []:
            modules.append({
                "module_id": str(module.get("module_id") or ""),
                "teaching_purpose": str(module.get("teaching_purpose") or ""),
                "knowledge_names": [
                    str((registry.get(item) or {}).get("name") or item)
                    for item in module.get("knowledge_keys") or []
                ],
                "teaching_guidance": str(module.get("teaching_guidance") or ""),
                **_module_execution(module),
            })
        planned_sections.append({
            "node_id": node_id,
            "knowledge_structure": groups,
            "key_points": [
                str((registry.get(key) or {}).get("name") or key)
                for key in identity.get("owned_knowledge_keys") or []
            ],
            "reused_knowledge_names": [
                str((registry.get(key) or {}).get("name") or key)
                for key in identity.get("reused_knowledge_keys") or []
            ],
            "knowledge_relations": relations,
            "teaching_modules": modules,
            **_section_execution(expanded),
        })
    assembled = {
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": outline_revision_id,
        "skeleton_revision_id": skeleton.get("revision_id"),
        "sections": planned_sections,
    }
    assembled["revision_id"] = stable_hash(
        {
            "schema_version": assembled["schema_version"],
            "source_outline_revision_id": outline_revision_id,
            "skeleton_revision_id": skeleton.get("revision_id"),
            "sections": planned_sections,
        },
        prefix="teaching_",
    )
    return assembled
