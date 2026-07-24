"""Deterministic blueprint impact analysis and course revision identities."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable


VERSION_SCHEMA = "course_version_v1"
BLUEPRINT_SCHEMA = "blueprint_revision_v1"

DISPLAY_FIELDS = ("node_name",)
SEMANTIC_FIELDS = (
    "learning_objective",
    "scope_boundary",
    "key_points",
    "knowledge_structure",
    "module_plan",
    "assessment",
    "exercise_plan",
    "examples_plan",
    "misconceptions",
    "learning_path_role",
    "path_reason",
)
DIFFICULTY_FIELDS = ("difficulty_contract",)
GROUNDING_FIELDS = ("grounding_contract",)
DEPENDENCY_FIELDS = ("parent_node_id", "prerequisite_node_ids", "node_level")
GLOBAL_RECOMPILE_FIELDS = (
    "course_type",
    "course_intent",
    "learner_starting_profile",
    "course_purpose",
    "difficulty_profile",
    "subject_pedagogy_profile",
    "course_module_plan",
    "learning_asset_plan",
)


def stable_hash(value: Any, *, prefix: str = "") -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}"


def blueprint_revision_id(course_data: dict[str, Any]) -> str:
    payload = {
        "course_blueprint": course_data.get("course_blueprint") or {},
        "nodes": [_blueprint_node(node) for node in course_data.get("nodes") or []],
        "purpose": course_data.get("course_purpose") or "systematic",
        "course_type": course_data.get("course_type") or "systematic",
        "course_intent": course_data.get("course_intent") or {},
        "learner_starting_profile": (
            course_data.get("learner_starting_profile") or {}
        ),
        "asset_plan": course_data.get("learning_asset_plan") or {},
    }
    return stable_hash(payload, prefix="bp_")


def content_revision_ids(course_data: dict[str, Any]) -> dict[str, str]:
    revisions: dict[str, str] = {}
    for node in course_data.get("nodes") or []:
        node_id = str(node.get("node_id") or "")
        if not node_id:
            continue
        payload = {
            "content": node.get("node_content") or "",
            "grounding_annotations": node.get("grounding_annotations") or [],
            "quality": node.get("generation_quality") or {},
        }
        revisions[node_id] = stable_hash(payload, prefix="content_")
    return revisions


def asset_revision_ids(course_data: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    assets = course_data.get("learning_assets") or {}
    for asset_type, values in assets.items():
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("asset_id") or item.get("question_id") or item.get("criterion_id") or item.get("misconception_id") or item.get("graph_id") or "")
            if not asset_id:
                continue
            result[f"{asset_type}:{asset_id}"] = str(item.get("revision_id") or stable_hash(item, prefix="asset_"))
    return result


def build_version_entry(
    course_data: dict[str, Any],
    *,
    version_id: str,
    sequence: int,
    reason: str,
    operation: str,
    base_version_id: str | None,
    changed_node_ids: Iterable[str] = (),
    status: str = "current",
) -> dict[str, Any]:
    return {
        "schema_version": VERSION_SCHEMA,
        "version_id": version_id,
        "sequence": sequence,
        "course_id": str(course_data.get("course_id") or ""),
        "course_name": str(course_data.get("course_name") or ""),
        "base_version_id": base_version_id,
        "blueprint_revision_id": blueprint_revision_id(course_data),
        "content_revision_ids": content_revision_ids(course_data),
        "asset_revision_ids": asset_revision_ids(course_data),
        "reason": reason,
        "operation": operation,
        "changed_node_ids": sorted({str(item) for item in changed_node_ids if item}),
        "quality_status": _quality_status(course_data),
        "status": status,
        "created_at": datetime.now().isoformat(),
    }


def build_blueprint_draft(course_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": BLUEPRINT_SCHEMA,
        "course_id": course_data.get("course_id"),
        "course_name": course_data.get("course_name"),
        "course_purpose": course_data.get("course_purpose") or "systematic",
        "course_type": course_data.get("course_type") or "systematic",
        "course_intent": deepcopy(course_data.get("course_intent") or {}),
        "learner_starting_profile": deepcopy(
            course_data.get("learner_starting_profile") or {}
        ),
        "course_blueprint": deepcopy(course_data.get("course_blueprint") or {}),
        "nodes": [_blueprint_node(node) for node in course_data.get("nodes") or []],
        "learning_asset_plan": deepcopy(course_data.get("learning_asset_plan") or {}),
        "blueprint_locks": deepcopy(course_data.get("blueprint_locks") or {}),
        "base_blueprint_revision_id": blueprint_revision_id(course_data),
        "updated_at": datetime.now().isoformat(),
    }


def merge_blueprint_draft(course_data: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Build a generation candidate without mutating the active course."""
    candidate = deepcopy(course_data)
    old_nodes = {str(node.get("node_id") or ""): deepcopy(node) for node in course_data.get("nodes") or []}
    merged_nodes: list[dict[str, Any]] = []
    for draft_node in draft.get("nodes") or []:
        node_id = str(draft_node.get("node_id") or "")
        merged = old_nodes.get(node_id, {})
        merged.update(deepcopy(draft_node))
        merged_nodes.append(merged)
    candidate["nodes"] = merged_nodes
    for field in (
        "course_name",
        "course_purpose",
        "course_type",
        "course_intent",
        "learner_starting_profile",
        "course_blueprint",
        "learning_asset_plan",
        "blueprint_locks",
    ):
        if field in draft:
            candidate[field] = deepcopy(draft[field])
    candidate["blueprint_revision_id"] = blueprint_revision_id(candidate)
    return candidate


def analyze_blueprint_impact(
    course_data: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    old_nodes = {str(node.get("node_id") or ""): node for node in course_data.get("nodes") or []}
    new_nodes = {str(node.get("node_id") or ""): node for node in draft.get("nodes") or []}
    old_ids = {node_id for node_id in old_nodes if node_id}
    new_ids = {node_id for node_id in new_nodes if node_id}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    direct: dict[str, set[str]] = {}
    display_only: set[str] = set()

    global_changes = [
        field
        for field in GLOBAL_RECOMPILE_FIELDS
        if field in draft and _field_value(course_data, field) != _field_value(draft, field)
    ]
    if global_changes:
        for node_id, node in new_nodes.items():
            if int(node.get("node_level") or 1) == 2:
                direct.setdefault(node_id, set()).add("global_contract")

    for node_id in sorted(old_ids & new_ids):
        old = old_nodes[node_id]
        new = new_nodes[node_id]
        changed_categories: set[str] = set()
        if _changed(old, new, DISPLAY_FIELDS):
            changed_categories.add("display")
        if _changed(old, new, SEMANTIC_FIELDS):
            changed_categories.add("semantic")
        if _changed(old, new, DIFFICULTY_FIELDS):
            changed_categories.add("difficulty")
        if _changed(old, new, GROUNDING_FIELDS):
            changed_categories.add("grounding")
        if _changed(old, new, DEPENDENCY_FIELDS):
            changed_categories.add("dependency")
        if changed_categories:
            if changed_categories == {"display"}:
                display_only.add(node_id)
            else:
                direct[node_id] = changed_categories

    for node_id in added:
        direct[node_id] = {"structure", "semantic"}
    for node_id in removed:
        direct[node_id] = {"structure", "dependency"}

    affected = set(direct)
    reverse_dependencies = _reverse_dependencies(new_nodes)
    queue = [node_id for node_id, categories in direct.items() if categories & {"semantic", "dependency", "structure", "grounding", "global_contract"}]
    while queue:
        source = queue.pop(0)
        for dependent in reverse_dependencies.get(source, set()):
            if dependent not in affected:
                affected.add(dependent)
                direct.setdefault(dependent, set()).add("upstream_dependency")
                queue.append(dependent)

    locks = draft.get("blueprint_locks") or course_data.get("blueprint_locks") or {}
    conflicts: list[dict[str, Any]] = []
    for node_id in sorted(affected | set(removed)):
        node_locks = locks.get(node_id) or {}
        categories = direct.get(node_id, set())
        if node_locks.get("planning") and categories & {"semantic", "dependency", "structure", "global_contract"}:
            conflicts.append(_lock_conflict(node_id, "planning", categories))
        if node_locks.get("content") and categories - {"display"}:
            conflicts.append(_lock_conflict(node_id, "content", categories))
        if node_locks.get("assets") and categories & {"semantic", "difficulty", "grounding", "dependency", "structure", "global_contract", "upstream_dependency"}:
            conflicts.append(_lock_conflict(node_id, "assets", categories))

    asset_impacts = {
        node_id: _asset_types_for_categories(categories)
        for node_id, categories in sorted(direct.items())
        if categories - {"display"}
    }
    unchanged = sorted(new_ids - affected - display_only)
    return {
        "schema_version": "impact_analysis_v1",
        "base_blueprint_revision_id": blueprint_revision_id(course_data),
        "draft_blueprint_revision_id": blueprint_revision_id(merge_blueprint_draft(course_data, draft)),
        "global_changes": global_changes,
        "added_node_ids": added,
        "removed_node_ids": removed,
        "display_only_node_ids": sorted(display_only),
        "affected_node_ids": sorted(affected),
        "unchanged_node_ids": unchanged,
        "node_changes": {node_id: sorted(categories) for node_id, categories in sorted(direct.items())},
        "asset_impacts": asset_impacts,
        "lock_conflicts": conflicts,
        "can_confirm": not conflicts,
        "summary": {
            "affected_nodes": len(affected),
            "unchanged_nodes": len(unchanged),
            "display_only_nodes": len(display_only),
            "asset_updates": sum(len(items) for items in asset_impacts.values()),
            "lock_conflicts": len(conflicts),
        },
    }


def compare_course_snapshots(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_nodes = {str(node.get("node_id") or ""): node for node in left.get("nodes") or []}
    right_nodes = {str(node.get("node_id") or ""): node for node in right.get("nodes") or []}
    left_ids, right_ids = set(left_nodes), set(right_nodes)
    modified: list[dict[str, Any]] = []
    for node_id in sorted(left_ids & right_ids):
        lnode, rnode = left_nodes[node_id], right_nodes[node_id]
        fields = [
            field
            for field in (*DISPLAY_FIELDS, *SEMANTIC_FIELDS, *DIFFICULTY_FIELDS, *GROUNDING_FIELDS, *DEPENDENCY_FIELDS, "node_content")
            if _field_value(lnode, field) != _field_value(rnode, field)
        ]
        if fields:
            modified.append({
                "node_id": node_id,
                "node_name": rnode.get("node_name") or lnode.get("node_name") or node_id,
                "changed_fields": fields,
                "content_changed": "node_content" in fields,
            })
    left_assets = asset_revision_ids(left)
    right_assets = asset_revision_ids(right)
    asset_keys = set(left_assets) | set(right_assets)
    changed_assets = sorted(key for key in asset_keys if left_assets.get(key) != right_assets.get(key))
    return {
        "schema_version": "course_version_diff_v1",
        "course_name_changed": left.get("course_name") != right.get("course_name"),
        "blueprint_changed": blueprint_revision_id(left) != blueprint_revision_id(right),
        "added_node_ids": sorted(right_ids - left_ids),
        "removed_node_ids": sorted(left_ids - right_ids),
        "modified_nodes": modified,
        "changed_asset_keys": changed_assets,
        "summary": {
            "added_nodes": len(right_ids - left_ids),
            "removed_nodes": len(left_ids - right_ids),
            "modified_nodes": len(modified),
            "changed_assets": len(changed_assets),
        },
    }


def _blueprint_node(node: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "node_id",
        "parent_node_id",
        "node_name",
        "node_level",
        "node_type",
        *SEMANTIC_FIELDS,
        *DIFFICULTY_FIELDS,
        *GROUNDING_FIELDS,
        "prerequisite_node_ids",
        "generation_status",
        "lock_state",
    )
    return {field: deepcopy(node.get(field)) for field in fields if field in node}


def _field_value(data: dict[str, Any], field: str) -> Any:
    if field in {"course_purpose", "course_type"}:
        return data.get(field) or "systematic"
    if field in {
        "course_intent",
        "learner_starting_profile",
        "difficulty_profile",
        "subject_pedagogy_profile",
        "learning_asset_plan",
    }:
        return data.get(field) or {}
    if field == "course_module_plan":
        return data.get(field) or []
    return data.get(field)


def _changed(left: dict[str, Any], right: dict[str, Any], fields: Iterable[str]) -> bool:
    return any(_field_value(left, field) != _field_value(right, field) for field in fields)


def _reverse_dependencies(nodes: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for node_id, node in nodes.items():
        dependencies = list(node.get("prerequisite_node_ids") or [])
        parent_id = str(node.get("parent_node_id") or "")
        if parent_id:
            dependencies.append(parent_id)
        for dependency in dependencies:
            dep = str(dependency or "")
            if dep:
                result.setdefault(dep, set()).add(node_id)
    return result


def _asset_types_for_categories(categories: set[str]) -> list[str]:
    knowledge_assets = ("knowledge_library", "course_knowledge_map")
    if "global_contract" in categories or "structure" in categories:
        return ["questions", *knowledge_assets, "mastery_criteria", "misconceptions", "overview", "checklist"]
    result: set[str] = set()
    if categories & {"semantic", "upstream_dependency"}:
        result.update(("questions", *knowledge_assets, "mastery_criteria", "misconceptions", "overview", "checklist"))
    if "difficulty" in categories:
        result.update(("questions", "mastery_criteria", "checklist"))
    if "grounding" in categories:
        result.update(("questions", "course_knowledge_map", "knowledge_library", "misconceptions"))
    if "dependency" in categories:
        result.update(("course_knowledge_map", "knowledge_library", "questions", "overview", "checklist"))
    return sorted(result)


def _lock_conflict(node_id: str, lock_type: str, categories: set[str]) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "lock_type": lock_type,
        "status": "locked_conflict",
        "categories": sorted(categories),
        "message": f"节点 {node_id} 的 {lock_type} 锁定与当前修改冲突",
    }


def _quality_status(course_data: dict[str, Any]) -> str:
    report = course_data.get("generation_quality_report") or {}
    return str(report.get("final_status") or course_data.get("generation_status") or "unknown")


__all__ = [
    "BLUEPRINT_SCHEMA",
    "VERSION_SCHEMA",
    "analyze_blueprint_impact",
    "asset_revision_ids",
    "blueprint_revision_id",
    "build_blueprint_draft",
    "build_version_entry",
    "compare_course_snapshots",
    "content_revision_ids",
    "merge_blueprint_draft",
    "stable_hash",
]
