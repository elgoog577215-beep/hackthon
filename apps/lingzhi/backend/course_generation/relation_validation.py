"""Teaching-plan relation validation and cross-batch diagnosis."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)

def _issue_dict(code: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": "critical", "message": message}


def diagnose_cross_batch_relation_cycles(
    *,
    skeleton: dict[str, Any],
    batches: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    relation_type: str = "prerequisite",
) -> list[dict[str, Any]]:
    """Report relation cycles that only exist once skeleton and batches merge.

    Detection only -- this never removes an edge. Which edge to drop changes the
    course's knowledge structure, so it is a product decision, not a mechanical
    repair. The report carries what that decision needs: every edge on the cycle,
    the layer that declared it, the sections owning each endpoint, the batch a
    batch-declared edge came from, and whether the edge agrees with section order.

    This has to run after assembly because neither input contains a cycle on its
    own: the skeleton's ``prerequisite_keys`` form one arc and a batch's
    ``knowledge_relations`` form the other. No single-layer validator can see it.
    """
    registry = {
        str(item.get("knowledge_key") or ""): item
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    }
    if not registry:
        return []
    section_order = {
        str(item.get("node_id") or ""): index
        for index, item in enumerate(sections)
    }
    owner_of = {
        key: str(item.get("owner_node_id") or "")
        for key, item in registry.items()
    }

    # edge -> list of provenance records, so an edge declared by both layers is
    # reported as such rather than silently attributed to one of them.
    edges: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def add_edge(source: str, target: str, origin: dict[str, Any]) -> None:
        if not source or not target or source not in registry or target not in registry:
            return
        edges.setdefault((source, target), []).append(origin)

    for key, item in registry.items():
        for prerequisite_key in item.get("prerequisite_keys") or []:
            add_edge(str(prerequisite_key), key, {"layer": "skeleton"})
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        batch_id = str(batch.get("batch_id") or "")
        for section in batch.get("sections") or []:
            if not isinstance(section, dict):
                continue
            node_id = str(section.get("node_id") or "")
            for relation in section.get("knowledge_relations") or []:
                if not isinstance(relation, dict):
                    continue
                if str(relation.get("relation_type") or "") != relation_type:
                    continue
                add_edge(
                    str(relation.get("source_key") or ""),
                    str(relation.get("target_key") or ""),
                    {"layer": "batch", "batch_id": batch_id, "declared_in": node_id},
                )

    graph: dict[str, list[str]] = {}
    for source, target in edges:
        graph.setdefault(source, []).append(target)

    cycles = _find_all_relation_cycles(graph)
    if not cycles:
        return []

    reports: list[dict[str, Any]] = []
    for cycle in cycles:
        cycle_edges: list[dict[str, Any]] = []
        for index in range(len(cycle) - 1):
            source, target = cycle[index], cycle[index + 1]
            source_owner = owner_of.get(source, "")
            target_owner = owner_of.get(target, "")
            source_position = section_order.get(source_owner)
            target_position = section_order.get(target_owner)
            # A prerequisite must be taught before what depends on it. An edge
            # pointing backwards contradicts the frozen section order and is the
            # shape seen in the first real occurrence (a batch declaring an
            # earlier section's knowledge as depending on a later one).
            agrees_with_order = (
                source_position is not None
                and target_position is not None
                and source_position <= target_position
            )
            cycle_edges.append({
                "source_key": source,
                "source_name": str((registry.get(source) or {}).get("name") or source),
                "source_section": source_owner,
                "target_key": target,
                "target_name": str((registry.get(target) or {}).get("name") or target),
                "target_section": target_owner,
                "declared_by": deepcopy(edges.get((source, target)) or []),
                "agrees_with_section_order": agrees_with_order,
            })
        contradicting = [
            item for item in cycle_edges
            if not item["agrees_with_section_order"]
        ]
        reports.append({
            "schema_version": "cross_batch_relation_cycle_v1",
            "relation_type": relation_type,
            "cycle_keys": list(cycle),
            "cycle_names": [
                str((registry.get(key) or {}).get("name") or key) for key in cycle
            ],
            "edges": cycle_edges,
            "batch_ids": sorted({
                str(origin.get("batch_id") or "")
                for item in cycle_edges
                for origin in item["declared_by"]
                if origin.get("layer") == "batch" and origin.get("batch_id")
            }),
            "layers": sorted({
                str(origin.get("layer") or "")
                for item in cycle_edges
                for origin in item["declared_by"]
            }),
            "order_contradicting_edge_count": len(contradicting),
            # Recorded, not acted on: an edge contradicting section order is the
            # mechanically-identifiable culprit, while a cycle whose edges all
            # agree with order needs a human to decide what the course means.
            "verdict": (
                "order_contradiction"
                if contradicting
                else "all_edges_plausible"
            ),
        })
    return reports


def _find_all_relation_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Return each distinct cycle once, as a closed node path."""
    colors: dict[str, int] = {}
    path: list[str] = []
    seen: set[frozenset[str]] = set()
    found: list[list[str]] = []

    def visit(node: str) -> None:
        colors[node] = 1
        path.append(node)
        for neighbour in graph.get(node, []):
            if colors.get(neighbour) == 1:
                cycle = path[path.index(neighbour):] + [neighbour]
                signature = frozenset(cycle)
                if signature not in seen:
                    seen.add(signature)
                    found.append(cycle)
            elif colors.get(neighbour) is None:
                visit(neighbour)
        colors[node] = 2
        path.pop()

    for node in list(graph):
        if colors.get(node) is None:
            visit(node)
    return found


def _record_relation_cycle_diagnosis(
    teaching_stage: dict[str, Any],
    *,
    skeleton: dict[str, Any],
    batches: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the cross-batch cycle report to the stage without blocking on it.

    Deliberately non-blocking: the knowledge-base compiler already fails a course
    whose prerequisites form a cycle, so a second hard gate here would add no
    protection. What is missing is the *diagnosis* -- by compile time the batches
    that declared the offending edges are long frozen, so the report has to be
    produced here, where the declaring batch is still identifiable.
    """
    try:
        reports = diagnose_cross_batch_relation_cycles(
            skeleton=skeleton,
            batches=batches,
            sections=sections,
        )
    except Exception:  # noqa: BLE001 - diagnosis must never break generation
        logger.exception("Cross-batch relation cycle diagnosis failed")
        return []
    if reports:
        teaching_stage["relation_cycle_diagnosis"] = deepcopy(reports)
        for report in reports:
            logger.warning(
                "Cross-batch %s cycle detected: %s (layers=%s batches=%s verdict=%s)",
                report.get("relation_type"),
                " -> ".join(report.get("cycle_names") or []),
                report.get("layers"),
                report.get("batch_ids"),
                report.get("verdict"),
            )
    else:
        teaching_stage.pop("relation_cycle_diagnosis", None)
    return reports


def _coherence_repair_suggestion(issue: dict[str, Any]) -> str:
    if issue.get("code") == "coherence:incorrect_next_section_handoff":
        return (
            "删除或改正错误的下一节预告，使它与全课总编契约中的实际后续小节一致；"
            "本节已经完成的知识不得再声称属于下一节"
        )
    return (
        "保留与前置章节的一两句承接，删除或重写重复讲解，"
        "把篇幅用于当前小节独有的知识、例子、任务与验收"
    )

__all__ = [
    "diagnose_cross_batch_relation_cycles",
]
