"""Bidirectional impact analysis between course knowledge and its downstream artifacts.

The teaching-plan side of this already exists in `teaching_plan_impact`: a plan
edit resolves to a knowledge id, and `KnowledgeReferenceIndex` reverse-looks-up
everything that cites it. This module drives the same index from the other end —
a knowledge revision — and adds the reverse direction, where changed course body
text is checked against the knowledge base for missing coverage.

Deliberate reuse rather than a parallel analyzer: the impact groups, downstream
state machine and failure-preservation rules all come from `teaching_plan_impact`.
A knowledge edit and a plan edit that touch the same block must produce the same
downstream verdict, which cannot be guaranteed by two independent implementations.

Three rules shape the output:

1. Impact comes from explicit bindings and relations, never a model guess. With
   no compiled knowledge base the report degrades to course-wide and says so.
2. A knowledge change that breaks stable identity is `blocked`, not rebuilt.
   Silently regenerating on top of an orphaned reference is how historical
   practice attempts lose their meaning.
3. Nothing here rebuilds or writes. It produces a read-only plan; the course and
   representation pipelines remain the only writers.
"""

from __future__ import annotations

from typing import Any

from course_knowledge_revisions import (
    KnowledgeRevisionEvent,
    changed_knowledge_ids,
    knowledge_revision_event,
)
from teaching_plan_impact import (
    IMPACT_GROUPS,
    KnowledgeReferenceIndex,
)

KNOWLEDGE_IMPACT_SCHEMA = "course_knowledge_impact_report_v1"
KNOWLEDGE_COVERAGE_SCHEMA = "course_knowledge_coverage_check_v1"

# Relation types that propagate a change forward: if the source knowledge moved,
# the target's explanation may no longer hold. `equivalent_to` / `contrasts_with`
# are symmetric, so they propagate both ways.
_FORWARD_RELATION_TYPES = {"prerequisite", "derives", "generalizes", "applies_to"}
_SYMMETRIC_RELATION_TYPES = {"equivalent_to", "contrasts_with"}

# Bounded traversal. A knowledge graph edit whose blast radius reaches this far
# is a course-wide review, not a localized rebuild, and pretending otherwise
# would produce a precise-looking list that is really just "most of the course".
MAX_RELATION_DEPTH = 3


def _text(value: Any) -> str:
    return str(value or "").strip()


def _relation_adjacency(
    knowledge_base: dict[str, Any] | None,
) -> dict[str, list[tuple[str, str]]]:
    """source knowledge id -> [(target id, relation type)] over accepted edges."""
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for relation in (knowledge_base or {}).get("relations") or []:
        if not isinstance(relation, dict):
            continue
        if _text(relation.get("status")) == "rejected":
            continue
        source = _text(relation.get("source_knowledge_id"))
        target = _text(relation.get("target_knowledge_id"))
        relation_type = _text(relation.get("relation_type"))
        if not source or not target:
            continue
        if relation_type in _FORWARD_RELATION_TYPES:
            adjacency.setdefault(source, []).append((target, relation_type))
        elif relation_type in _SYMMETRIC_RELATION_TYPES:
            adjacency.setdefault(source, []).append((target, relation_type))
            adjacency.setdefault(target, []).append((source, relation_type))
    return adjacency


def dependent_knowledge_ids(
    knowledge_base: dict[str, Any] | None,
    seed_ids: list[str],
    *,
    max_depth: int = MAX_RELATION_DEPTH,
) -> dict[str, dict[str, Any]]:
    """Knowledge reachable from `seed_ids` along relations, with depth and path.

    Breadth-first so each id keeps its *shortest* justification: a point two
    hops away should be explained by the two-hop path, not whichever longer
    walk happened to reach it first.
    """
    adjacency = _relation_adjacency(knowledge_base)
    seeds = {_text(item) for item in seed_ids if _text(item)}
    found: dict[str, dict[str, Any]] = {}
    frontier = [(item, 0) for item in sorted(seeds)]

    while frontier:
        current_id, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for target, edge_type in sorted(adjacency.get(current_id, [])):
            if target in seeds or target in found:
                continue
            found[target] = {
                "knowledge_id": target,
                "depth": depth + 1,
                "relation_type": edge_type,
                "via": current_id,
            }
            frontier.append((target, depth + 1))
    return found


def build_knowledge_impact_report(
    event: KnowledgeRevisionEvent,
    *,
    course_data: dict[str, Any] | None = None,
    knowledge_base: dict[str, Any] | None = None,
    max_relation_depth: int = MAX_RELATION_DEPTH,
) -> dict[str, Any]:
    """Group the downstream impact of one knowledge revision for review.

    Output shares `teaching_plan_impact.IMPACT_GROUPS` so the same downstream
    state machine consumes both a plan edit and a knowledge edit.
    """
    base = knowledge_base
    if base is None:
        base = (course_data or {}).get("course_knowledge_base")
    index = KnowledgeReferenceIndex(base)
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in IMPACT_GROUPS}
    seen: set[tuple[str, str, str]] = set()

    def _add(group: str, item_type: str, item_id: str, **extra: Any) -> None:
        key = (group, item_type, item_id)
        if key in seen or not item_type or not item_id:
            return
        seen.add(key)
        groups[group].append({"type": item_type, "id": item_id, **extra})

    direct_ids = changed_knowledge_ids(event)

    # An identity violation makes the reverse lookup untrustworthy: references
    # may point at knowledge that no longer exists. Report it and stop, rather
    # than emitting a confident-looking list built on broken anchors.
    for violation in event.identity_violations:
        _add(
            "blocked",
            "knowledge_point",
            violation.entity_id,
            reason=violation.message,
            knowledge_id=violation.entity_id,
            resolution="requires_identity_migration",
            violation_code=violation.code,
        )

    if not index.available:
        # No compiled knowledge base: the honest answer is course-wide.
        _add(
            "blocked",
            "course_knowledge_base",
            _text(event.course_id) or "course",
            reason="课程尚未编译知识库，无法定位受影响的下游产物，需整门课程复核。",
            resolution="course_fallback",
        )
        return {
            "schema_version": KNOWLEDGE_IMPACT_SCHEMA,
            **groups,
            "blocking": True,
            "knowledge_index_available": False,
            "changed_knowledge_ids": direct_ids,
            "dependent_knowledge_ids": [],
            "identity_preserved": event.identity_preserved,
        }

    blocked_ids = {item.entity_id for item in event.identity_violations}

    for knowledge_id in direct_ids:
        if knowledge_id in blocked_ids:
            continue
        display = index.display_name(knowledge_id) or knowledge_id
        targets = index.referencing_targets(knowledge_id)
        for object_type, object_id in targets:
            _add(
                "needs_regeneration",
                object_type,
                object_id,
                reason=f"直接引用了发生变化的知识点「{display}」。",
                knowledge_id=knowledge_id,
                resolution="direct_reference",
            )
        if not targets:
            # A knowledge point nothing cites yet is a real state, not an error:
            # it is safe to change precisely because no artifact depends on it.
            _add(
                "changed",
                "knowledge_point",
                knowledge_id,
                reason=f"知识点「{display}」已变化，但当前没有下游产物引用它。",
                knowledge_id=knowledge_id,
                resolution="no_referencing_object",
            )

    dependents = dependent_knowledge_ids(
        base, direct_ids, max_depth=max_relation_depth,
    )
    for knowledge_id, info in sorted(dependents.items()):
        if knowledge_id in blocked_ids:
            continue
        display = index.display_name(knowledge_id) or knowledge_id
        via_display = index.display_name(info["via"]) or info["via"]
        reason = (
            f"经 {info['relation_type']} 关系依赖已变化的「{via_display}」"
            f"（{info['depth']} 跳），需复核是否仍然成立。"
        )
        for object_type, object_id in index.referencing_targets(knowledge_id):
            _add(
                "stale",
                object_type,
                object_id,
                reason=reason,
                knowledge_id=knowledge_id,
                resolution="relation_dependency",
                relation_depth=info["depth"],
                relation_type=info["relation_type"],
            )

    return {
        "schema_version": KNOWLEDGE_IMPACT_SCHEMA,
        **groups,
        "blocking": bool(groups["blocked"]),
        "knowledge_index_available": True,
        "changed_knowledge_ids": direct_ids,
        "dependent_knowledge_ids": sorted(dependents),
        "identity_preserved": event.identity_preserved,
    }


def knowledge_impact_for_revision(
    previous_knowledge_base: dict[str, Any] | None,
    current_knowledge_base: dict[str, Any] | None,
    *,
    course_data: dict[str, Any] | None = None,
    command_id: str = "",
    operation: str = "update_knowledge",
    identity_map: dict[str, Any] | None = None,
    max_relation_depth: int = MAX_RELATION_DEPTH,
) -> tuple[KnowledgeRevisionEvent, dict[str, Any]]:
    """Convenience path: diff two knowledge revisions and group their impact."""
    event = knowledge_revision_event(
        previous_knowledge_base,
        current_knowledge_base,
        command_id=command_id,
        operation=operation,
        identity_map=identity_map,
    )
    report = build_knowledge_impact_report(
        event,
        course_data=course_data,
        knowledge_base=current_knowledge_base,
        max_relation_depth=max_relation_depth,
    )
    return event, report


def knowledge_coverage_check(
    course_data: dict[str, Any] | None,
    *,
    changed_block_ids: list[str],
    knowledge_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reverse direction: does changed body text still have knowledge coverage?

    A block whose content changed but which no binding cites is the concrete
    shape of "正文新增了独立知识内容": the course now teaches something the
    knowledge base does not know about. This reports the gap so a knowledge
    maintenance candidate can be raised; it never writes knowledge itself.
    """
    base = knowledge_base
    if base is None:
        base = (course_data or {}).get("course_knowledge_base")
    index = KnowledgeReferenceIndex(base)

    bound_block_ids: set[str] = set()
    for binding in (base or {}).get("bindings") or []:
        if not isinstance(binding, dict) or _text(binding.get("status")) == "retired":
            continue
        if _text(binding.get("target_type")) == "course_block":
            bound_block_ids.add(_text(binding.get("target_id")))

    blocks_by_id: dict[str, dict[str, Any]] = {}
    document = (course_data or {}).get("course_document")
    if isinstance(document, dict):
        for block in document.get("blocks") or []:
            if isinstance(block, dict) and _text(block.get("block_id")):
                blocks_by_id[_text(block.get("block_id"))] = block

    covered: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for block_id in sorted({_text(item) for item in changed_block_ids if _text(item)}):
        block = blocks_by_id.get(block_id)
        row = {
            "block_id": block_id,
            "section_id": _text((block or {}).get("section_id")),
        }
        if block is None:
            gaps.append({
                **row,
                "gap": "block_not_in_document",
                "reason": "变更的正文块不在当前正式课程文档中，无法判断知识覆盖。",
            })
        elif block_id in bound_block_ids:
            covered.append(row)
        else:
            gaps.append({
                **row,
                "gap": "block_without_knowledge_binding",
                "reason": "该正文块没有任何知识绑定，可能新增了知识库尚未收录的内容。",
            })

    return {
        "schema_version": KNOWLEDGE_COVERAGE_SCHEMA,
        "knowledge_index_available": index.available,
        "covered": covered,
        "gaps": gaps,
        # A gap is a review prompt for the knowledge maintainer, never an
        # automatic knowledge write: AI may only propose through the whitelist
        # commands with explicit user confirmation.
        "requires_knowledge_review": bool(gaps),
    }


def knowledge_impact_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection for regression snapshots.

    Only "哪些对象进入哪一组" survives. Reasons, revisions and timestamps drift
    on unrelated edits; putting them in a snapshot manufactures false failures
    that hide the impact-surface regressions the snapshot exists to catch.
    """
    return {
        "blocking": bool(report.get("blocking")),
        "knowledge_index_available": bool(report.get("knowledge_index_available")),
        "identity_preserved": bool(report.get("identity_preserved")),
        "groups": {
            group: sorted(
                f"{_text(item.get('type'))}:{_text(item.get('id'))}"
                for item in report.get(group) or []
                if isinstance(item, dict)
            )
            for group in IMPACT_GROUPS
            if report.get(group)
        },
    }


__all__ = [
    "KNOWLEDGE_COVERAGE_SCHEMA",
    "KNOWLEDGE_IMPACT_SCHEMA",
    "MAX_RELATION_DEPTH",
    "build_knowledge_impact_report",
    "dependent_knowledge_ids",
    "knowledge_coverage_check",
    "knowledge_impact_for_revision",
    "knowledge_impact_snapshot",
]
