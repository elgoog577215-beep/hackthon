"""Bounded editing of a not-yet-delivered outline, using the formal editor.

The caller owns the task, checkpoints and publication. This module never saves
formal course content and never starts another task.
"""
from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from ai_base import AIProviderRequestError, AIProviderUnavailable
from course_generation.outline import (
    _review_course_requirements,
    outline_detail_field_is_empty,
    review_course_outline_document,
)
from course_outline_adjustments import OutlineAdjustmentError, apply_outline_operations
from course_versioning import stable_hash

POLICY_VERSION = "outline_auto_improvement_v1"
MAX_ROUNDS = 2
HOUR_FIELDS = ("classroom_lecture", "classroom_practice", "online_instruction")
ISSUE_FIELDS = {
    "generic_objectives": {"learning_objective"},
    "overlong_objectives": {"learning_objective"},
    "repeated_objective_template": {"learning_objective"},
    "repeated_assessment_template": {"assessment"},
    "missing_assessments": {"assessment"},
    "missing_scope_boundaries": {"scope_boundary"},
    "missing_application_anchors": {"application_anchors"},
    "missing_learning_tasks": {"learning_tasks"},
    "missing_online_learning_tasks": {"learning_tasks"},
    "missing_extension_resources": {"extension_resources"},
}


def _sections(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [section for chapter in plan.get("chapters") or [] for section in chapter.get("sections") or []]


def _positive(value: Any) -> float:
    try:
        number = float(value or 0)
    except (ValueError, TypeError):
        return 0
    return number if math.isfinite(number) and number > 0 else 0


def _protected(existing: dict[str, Any]) -> dict[str, set[str]]:
    fields = set().union(*ISSUE_FIELDS.values(), {"hour_breakdown"})
    protected = {}
    for node in existing.get("nodes") or []:
        if int(node.get("node_level") or 0) == 2:
            protected[str(node.get("node_id") or "")] = {
                field for field in fields if not outline_detail_field_is_empty(field, node.get(field))
            }
    return protected


def _draft(plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    # Keep original IDs and metadata; the existing editor performs all validation.
    nodes = []
    for index, chapter in enumerate(plan.get("chapters") or [], 1):
        chapter_id = str(chapter.get("node_id") or f"L1-{index}")
        nodes.append({**deepcopy(chapter), "node_id": chapter_id,
                      "node_level": 1, "parent_node_id": "root", "node_name": chapter["title"]})
        nodes[-1].pop("sections", None)
        for section in chapter.get("sections") or []:
            nodes.append({**deepcopy(section), "node_level": 2,
                          "parent_node_id": chapter_id, "node_name": section["title"]})
    return {**deepcopy(context), "authoring_structure_version": "lecture_v1",
            "course_plan": deepcopy(plan), "course_outline": deepcopy(plan), "nodes": nodes}


def _apply(plan: dict[str, Any], context: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    result = apply_outline_operations(_draft(plan, context), operations)
    normalized_nodes = {node["node_id"]: node for node in result["draft"]["nodes"]}
    # The editor canonicalizes display names and projections. Copy only requested
    # normalized fields back, preserving generation/evidence/lecture metadata.
    changed = {op["node_ref"]: set() for op in operations}
    for op in operations:
        changed[op["node_ref"]].update(set(op) - {"op", "node_ref"})
    improved = deepcopy(plan)
    for chapter in improved["chapters"]:
        for section in chapter["sections"]:
            node_id = section["node_id"]
            target = normalized_nodes[result["id_map"][node_id]]
            for field in changed.get(node_id, set()):
                section[field] = deepcopy(target[field])
                chapter[field] = deepcopy(target[field])
                if field == "learning_objective":
                    chapter["learning_focus"] = target[field]
                if field == "hour_breakdown":
                    section["planned_hours"] = chapter["planned_hours"] = target["planned_hours"]
    improved["total_hours"] = round(sum(_positive(s.get("planned_hours")) for s in _sections(improved)), 2)
    return improved


def _hour_operations(plan: dict[str, Any], context: dict[str, Any], protected: dict[str, set[str]]) -> list[dict[str, Any]]:
    requirements = _review_course_requirements(context)
    total = _positive(requirements["total_hours"])
    mode = requirements["teaching_context"]
    # No invented delivery mode or blended split. Preserve an existing blended
    # allocation; if neither side has a basis leave it for the teacher.
    if not total or mode not in {"classroom", "online", "self_study", "blended"}:
        return []
    sections = _sections(plan)
    mutable = [s for s in sections if "hour_breakdown" not in protected.get(s["node_id"], set())]
    fixed = sum(sum(_positive((s.get("hour_breakdown") or {}).get(k)) for k in HOUR_FIELDS)
                for s in sections if s not in mutable)
    remaining = round((total - fixed) * 100)
    if not mutable or remaining < len(mutable):
        return []
    weights = [_positive(s.get("planned_hours")) or
               sum(_positive((s.get("hour_breakdown") or {}).get(k)) for k in HOUR_FIELDS) or 1 for s in mutable]
    amounts = [remaining * w / sum(weights) for w in weights]
    units = [math.floor(v) for v in amounts]
    for index in sorted(range(len(units)), key=lambda i: amounts[i] - units[i], reverse=True)[:remaining - sum(units)]:
        units[index] += 1
    operations = []
    for section, cents in zip(mutable, units):
        current = section.get("hour_breakdown") or {}
        ratios = [_positive(current.get(k)) for k in HOUR_FIELDS]
        if mode == "classroom":
            ratios[2] = 0
            if not sum(ratios):
                ratios[0] = 1
        elif mode in {"online", "self_study"}:
            ratios = [0, 0, 1]
        elif not ratios[2] or not sum(ratios[:2]):
            return []
        raw = [cents * v / sum(ratios) for v in ratios]
        parts = [math.floor(v) for v in raw]
        for index in sorted(range(3), key=lambda i: raw[i] - parts[i], reverse=True)[:cents - sum(parts)]:
            parts[index] += 1
        value = dict(zip(HOUR_FIELDS, [part / 100 for part in parts]))
        if value != current:
            operations.append({"op": "update_node", "node_ref": section["node_id"], "hour_breakdown": value})
    return operations


def _references(plan: dict[str, Any]) -> set[str]:
    return {str(item).strip() for field in ("reference_books", "reference_websites")
            for item in plan.get(field) or [] if str(item).strip()}


def _targets(report: dict[str, Any], plan: dict[str, Any], protected: dict[str, set[str]]) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    targets: dict[str, set[str]] = {}
    issues = []
    for issue in report["issues"]:
        code = issue["code"].split(":")[-1]
        fields = ISSUE_FIELDS.get(code, set())
        if code == "missing_extension_resources" and not _references(plan):
            continue
        selected = []
        for node_id in issue.get("node_ids") or []:
            allowed = fields - protected.get(node_id, set())
            if allowed:
                targets.setdefault(node_id, set()).update(allowed)
                selected.append(node_id)
        if selected:
            issues.append({**issue, "node_ids": selected})
    return targets, issues


def _safe_operations(payload: Any, targets: dict[str, set[str]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list) or not operations or len(operations) > len(targets) * 4:
        raise OutlineAdjustmentError("auto_operations_invalid", "自动优化没有返回有效操作")
    operations = deepcopy(operations)
    for op in operations:
        if not isinstance(op, dict) or op.get("op") != "update_node":
            raise OutlineAdjustmentError("auto_scope_violation", "自动优化试图修改课程结构")
        if not isinstance(op.get("node_ref"), str):
            raise OutlineAdjustmentError("auto_scope_violation", "自动优化缺少有效节点身份")
        allowed = targets.get(op["node_ref"], set())
        if not allowed or set(op) - {"op", "node_ref"} - allowed:
            raise OutlineAdjustmentError("auto_scope_violation", "自动优化超出允许字段")
        if "extension_resources" in op:
            resources = op["extension_resources"]
            if not isinstance(resources, list) or not resources:
                raise OutlineAdjustmentError("auto_source_invalid", "资源为空")
            for item in resources:
                if not isinstance(item, dict) or item.get("source_ref") not in _references(plan):
                    raise OutlineAdjustmentError("auto_source_invalid", "资源缺少已有来源")
                # A label match does not verify an edition or page number. The
                # automatic path may select a source, never invent verification.
                item.update(title=item["source_ref"], edition="", locator="", verification_status="pending")
    return operations


def _issue_units(report: dict[str, Any]) -> set[tuple[str, str]]:
    return {(issue["code"], node) for issue in report["issues"] for node in issue.get("node_ids") or ["course"]}


async def improve_generated_outline(
    *, plan: dict[str, Any], context: dict[str, Any], existing: dict[str, Any],
    saved_state: dict[str, Any], propose: Callable[..., Awaitable[dict[str, Any]]],
    checkpoint: Callable[[dict[str, Any]], Awaitable[None]],
    progress: Callable[[int], Awaitable[None]], timeout_seconds: float = 120,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Improve the unpublished plan; cancellation and persistence errors escape."""
    protected = _protected(existing)
    input_revision = stable_hash({"plan": plan, "requirements": _review_course_requirements(context),
                                  "protected": {k: sorted(v) for k, v in protected.items()},
                                  "policy": POLICY_VERSION}, prefix="outline_auto_")
    state = deepcopy(saved_state) if saved_state.get("input_revision") == input_revision else {
        "policy_version": POLICY_VERSION, "input_revision": input_revision,
        "attempts": 0, "status": "running", "accepted_plan": deepcopy(plan), "errors": [],
    }
    best = deepcopy(state["accepted_plan"])
    report = review_course_outline_document(best, course_context=context)
    state.setdefault("initial_issue_count", len(report["issues"]))
    if state.get("status") != "running":
        return best, report, state
    hours = _hour_operations(best, context, protected)
    if hours:
        try:
            candidate = _apply(best, context, hours)
            candidate_report = review_course_outline_document(candidate, course_context=context)
            if not _issue_units(candidate_report) - _issue_units(report):
                best, report = candidate, candidate_report
                state["hours_corrected"] = True
        except OutlineAdjustmentError as exc:
            state["errors"].append(exc.code)
    state["accepted_plan"] = deepcopy(best)
    await checkpoint(state)
    while state["attempts"] < MAX_ROUNDS:
        targets, issues = _targets(report, best, protected)
        if not targets:
            break
        state["attempts"] += 1
        await checkpoint(state)  # Charge before calling: restart cannot reset the bound.
        await progress(state["attempts"])
        instruction = (
            "在交付前优化新生成的大纲，合并处理以下问题。只允许 update_node，且只修改给定节点的允许字段。"
            "保留每讲实际主题和教师输入；目标必须表达本讲内容对应的可观察成果，不能只换句式或同义词。"
            "无需修改已合格内容。资源只从已有来源选择，缺少版次或定位时保持 pending，不能编造。\n"
            + json.dumps({"issues": issues, "allowed_fields": {k: sorted(v) for k, v in targets.items()}}, ensure_ascii=False)
        )
        try:
            payload = await asyncio.wait_for(propose(draft=_draft(best, context), instruction=instruction), timeout=timeout_seconds)
            operations = _safe_operations(payload, targets, best)
            candidate = _apply(best, context, operations)
            candidate_report = review_course_outline_document(candidate, course_context=context)
            before, after = _issue_units(report), _issue_units(candidate_report)
            new_issues = after - before
            # Selecting a real source may reveal the remaining human verification.
            new_issues = {unit for unit in new_issues if not (
                unit[0] == "outline_editorial:unverified_extension_resources"
                and ("outline_editorial:missing_extension_resources", unit[1]) in before)}
            targeted = {(issue["code"], node) for issue in issues for node in issue["node_ids"]}
            if new_issues or not targeted - after:
                state["errors"].append("auto_no_improvement")
            else:
                best, report = candidate, candidate_report
                state["accepted_plan"] = deepcopy(best)
        except (AIProviderRequestError, AIProviderUnavailable, TimeoutError, OutlineAdjustmentError) as exc:
            state["errors"].append(exc.code if isinstance(exc, OutlineAdjustmentError) else "auto_provider_unavailable")
            state["status"] = "partial"
        await checkpoint(state)
        if state["status"] != "running":
            break
    state["status"] = "partial" if report["issues"] else "completed"
    state["remaining_issue_count"] = len(report["issues"])
    state["remaining_issue_codes"] = [issue["code"] for issue in report["issues"]]
    await checkpoint(state)
    return best, report, state
