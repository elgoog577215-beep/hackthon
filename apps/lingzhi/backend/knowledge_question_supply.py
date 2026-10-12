"""Read-only question supply and exact selection of existing blueprint slots.

Generation, review, storage and grading remain owned by the existing assessment
pipeline. This module never generates questions or grants review approval.
"""
from collections import Counter
from copy import deepcopy


def current_question_assets(course: dict, assets: dict, bank: dict | None) -> dict:
    """Keep knowledge-tree practice links aligned with the current bank checks."""
    if bank is None:
        return assets
    from knowledge_practice import adopted_knowledge_checks
    from question_bank import FINAL_ASSESSMENT_ROLES, approved_formal_tasks

    tasks = approved_formal_tasks(bank)
    result = deepcopy(assets)
    result["questions"] = [
        *[q for q in tasks if q.get("assessment_role") not in FINAL_ASSESSMENT_ROLES],
        *adopted_knowledge_checks(course),
    ]
    result["final_assessment"] = [q for q in tasks if q.get("assessment_role") in FINAL_ASSESSMENT_ROLES]
    return result


def select_knowledge_slots(blueprint: dict, knowledge_ids: list[str], node_ids: list[str]) -> dict[str, list[str]]:
    requested = set(knowledge_ids)
    selected = {}
    found = set()
    for node in blueprint.get("nodes") or []:
        node_id = str(node.get("node_id") or "")
        if node_id not in node_ids:
            continue
        keys = []
        for slot in node.get("slots") or []:
            primary = slot.get("primary_knowledge_ids") or []
            if len(primary) == 1 and primary[0] in requested and slot.get("generation_key"):
                found.add(primary[0])
                keys.append(slot["generation_key"])
        if keys:
            selected[node_id] = keys
    if not requested or found != requested or set(selected) != set(node_ids):
        raise ValueError("Selected knowledge points have no eligible slots in the requested lectures")
    return selected


def knowledge_question_supply(base: dict, tasks: list[dict], items: list[dict]) -> list[dict]:
    """Count only exact current bindings; never return answers or private reviews."""
    rows = []
    for point in base.get("knowledge_points") or []:
        kid, revision = point.get("knowledge_id"), point.get("revision_id")
        if not kid or not revision:
            continue

        def matches(question):
            return question.get("primary_knowledge_ids") == [kid] and (question.get("knowledge_revision_refs") or {}).get(kid) == revision

        # Bank projections and learning assets can contain the same revision.
        available = {q.get("revision_id") or q.get("task_revision_id"): q for q in tasks if matches(q)}
        available.pop(None, None)
        sources = Counter(
            "authored" if q.get("origin") == "adopted_authored_check" else
            "generated" if q.get("source_type") in {"generated", "variant"} else
            "imported" if q.get("source_type") == "imported" else "other"
            for q in available.values()
        )
        available_bank_ids = {q.get("question_bank_item_revision_id") or q.get("revision_id") for q in available.values()}
        pending = {q.get("revision_id") for q in items if matches(q) and (
            q.get("lifecycle_status") in {"candidate", "needs_review"}
            or (q.get("lifecycle_status") == "approved" and q.get("revision_id") not in available_bank_ids)
        )}
        pending.discard(None)
        rows.append({
            "knowledge_id": kid, "revision_id": revision,
            "available_count": len(available), "pending_count": len(pending),
            "sources": dict(sources),
        })
    return rows
