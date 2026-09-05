"""Normalize one course section's knowledge structure without repository access."""

from __future__ import annotations

from typing import Any


def normalize_knowledge_structure(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Read historical fields, but never manufacture knowledge from a title."""
    normalized: list[dict[str, Any]] = []
    for topic_index, raw_topic in enumerate(section.get("knowledge_structure") or []):
        if not isinstance(raw_topic, dict):
            continue
        topic_name = str(
            raw_topic.get("concept_group")
            or raw_topic.get("topic")
            or raw_topic.get("name")
            or ""
        ).strip()
        points = [
            point
            for point_index, raw_point in enumerate(raw_topic.get("knowledge_points") or [])
            if (point := _normalize_point(raw_point, point_index))
        ]
        if not topic_name or not points:
            continue
        normalized.append({
            "concept_group": topic_name,
            "topic": topic_name,
            "description": str(raw_topic.get("description") or "").strip(),
            "knowledge_points": points,
            "detail_status": "refined",
            "order": topic_index,
        })

    if normalized:
        section["knowledge_structure"] = normalized
        section["knowledge_structure_status"] = "structured"
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
        section["knowledge_structure"] = []
        section["knowledge_structure_status"] = "needs_enrichment"
        return []
    normalized = [{
        "concept_group": "待知识化内容",
        "topic": "待知识化内容",
        "description": "历史课程只保留了要点名称，尚未形成可发布的原子知识结构。",
        "knowledge_points": [{
            "name": name,
            "statement": "",
            "description": "",
            "knowledge_type": "definition",
            "conditions": [],
            "boundaries": [],
            "counterexamples": [],
            "capability": "",
            "capability_points": [],
            "misconceptions": [],
            "mastery_criteria": [],
            "relations": [],
            "aliases": [],
            "entry_reason": "",
            "prerequisite_names": [],
            "order": index,
        } for index, name in enumerate(names)],
        "detail_status": "outline_only",
        "order": 0,
    }]
    section["knowledge_structure"] = normalized
    section["knowledge_structure_status"] = "needs_enrichment"
    section["key_points"] = names
    return normalized


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
        "knowledge_id": str(raw.get("knowledge_id") or "").strip(),
        "name": name,
        "statement": str(raw.get("statement") or raw.get("description") or "").strip(),
        "description": str(raw.get("description") or raw.get("statement") or "").strip(),
        "knowledge_type": str(raw.get("knowledge_type") or "definition").strip(),
        "conditions": _unique(raw.get("conditions") or []),
        "boundaries": _unique(raw.get("boundaries") or []),
        "counterexamples": _unique(raw.get("counterexamples") or []),
        "content_block_refs": _unique(
            raw.get("content_block_refs") or raw.get("block_refs") or []
        ),
        "capability": str(raw.get("capability") or "").strip(),
        "capability_points": _normalize_standard_points(
            raw.get("capability_points") or raw.get("capabilities") or []
        ),
        "misconceptions": _normalize_standard_points(
            raw.get("mistake_points") or raw.get("misconceptions") or []
        ),
        "mastery_criteria": _normalize_standard_points(raw.get("mastery_criteria") or []),
        "relations": _normalize_relations(raw.get("relations") or []),
        "aliases": _unique([str(item).strip() for item in raw.get("aliases") or []]),
        "entry_reason": str(raw.get("entry_reason") or "").strip(),
        "relation_state": str(raw.get("relation_state") or "").strip(),
        "relation_decision_reason": str(raw.get("relation_decision_reason") or "").strip(),
        "prerequisite_names": _unique(
            [str(item).strip() for item in raw.get("prerequisite_names") or []]
        ),
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
                    "practice_strategy", "source_status", "observable_error_pattern",
                    "confused_with", "discrimination", "observable_performance",
                    "required_independence", "required_transfer", "verification_method",
                    "required_evidence_types", "related_knowledge_names",
                }
            }
            if any(str(item.get(key) or "").strip() for key in ("name", "label", "statement")):
                normalized.append(item)
        elif str(value).strip():
            normalized.append(str(value).strip())
    return normalized


def _normalize_relations(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        values = [values] if values else []
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        target_name = str(value.get("target_name") or "").strip()
        relation_type = str(value.get("relation_type") or "").strip()
        if not target_name or not relation_type:
            continue
        result.append({
            "target_name": target_name,
            "relation_type": relation_type,
            "reason": str(value.get("reason") or "").strip(),
            "conditions": _unique(value.get("conditions") or []),
            "distinction": str(value.get("distinction") or "").strip(),
            "derivation_steps": _unique(value.get("derivation_steps") or []),
            "necessity": str(value.get("necessity") or "").strip(),
            "priority": str(value.get("priority") or "core").strip(),
            "relation_group_id": str(value.get("relation_group_id") or "").strip() or None,
            "group_operator": str(value.get("group_operator") or "").strip() or None,
        })
    return result


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


__all__ = ["normalize_knowledge_structure"]
