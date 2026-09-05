"""Per-entity knowledge revisions for independent, safe knowledge evolution.

The course knowledge base already computes a content hash per record, but the
course revision vector carries the whole base as one opaque
``course_knowledge_base`` key. That is enough to know *something* changed and
not enough to answer the two questions this module exists for:

1. Which knowledge points, relations and bindings actually moved between two
   knowledge revisions? Without that, every knowledge edit invalidates the whole
   course and the only safe response is regenerating everything.
2. Did a change rewrite a stable knowledge identity or its source binding? Those
   are the anchors historical practice attempts, learning events and downstream
   bindings resolve against, so they may only change through an explicit,
   recorded mapping — never by silent overwrite.

This module is pure analysis over two knowledge-base payloads. It owns no
storage, holds no facts, and never mutates the knowledge base: the course
repository stays the single writer, and the knowledge base stays the single
knowledge truth source. It only makes the existing revision data addressable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from course_versioning import stable_hash

KNOWLEDGE_REVISION_VECTOR_SCHEMA = "course_knowledge_revision_vector_v1"
KNOWLEDGE_REVISION_EVENT_SCHEMA = "course_knowledge_revision_event_v1"

# (collection, id field, revision-vector key prefix). The prefix is part of the
# stored contract: downstream consumers match on it, so renaming one is a
# breaking change, not a cleanup.
ENTITY_SPECS: tuple[tuple[str, str, str], ...] = (
    ("concept_groups", "concept_group_id", "concept_group"),
    ("knowledge_points", "knowledge_id", "point"),
    ("skill_units", "skill_id", "skill"),
    ("misconceptions", "misconception_id", "misconception"),
    ("mastery_criteria", "criterion_id", "criterion"),
    ("relations", "relation_id", "relation"),
    ("bindings", "binding_id", "binding"),
)

# Identity anchors that downstream artifacts and historical learning facts
# resolve against. A knowledge command may retire them through a recorded
# mapping, but may never repoint them in place.
_IDENTITY_ANCHOR_FIELDS = ("knowledge_id", "primary_concept_group_id")
_SOURCE_BINDING_FIELDS = ("source_refs", "section_refs", "objective_refs")

_RETIRED_STATUSES = {"retired", "tombstone", "superseded", "merged", "split"}


class KnowledgeRevisionVector(BaseModel):
    schema_version: Literal["course_knowledge_revision_vector_v1"] = (
        KNOWLEDGE_REVISION_VECTOR_SCHEMA
    )
    course_id: str
    knowledge_base_revision_id: str = ""
    lifecycle_status: str = ""
    revisions: dict[str, str] = Field(default_factory=dict)


class KnowledgeIdentityViolation(BaseModel):
    code: str
    entity_kind: str
    entity_id: str
    message: str


class KnowledgeRevisionEvent(BaseModel):
    schema_version: Literal["course_knowledge_revision_event_v1"] = (
        KNOWLEDGE_REVISION_EVENT_SCHEMA
    )
    event_id: str
    course_id: str
    command_id: str = ""
    operation: str = "update_knowledge"
    previous: KnowledgeRevisionVector
    current: KnowledgeRevisionVector
    changed_source_keys: list[str] = Field(default_factory=list)
    added_source_keys: list[str] = Field(default_factory=list)
    removed_source_keys: list[str] = Field(default_factory=list)
    # Old knowledge_id -> new knowledge_id(s), for split / merge / rename. This
    # is what lets a historical PracticeAttempt keep its original reference and
    # still be explained under the current knowledge base.
    identity_map: dict[str, list[str]] = Field(default_factory=dict)
    identity_violations: list[KnowledgeIdentityViolation] = Field(default_factory=list)
    created_at: str

    @property
    def identity_preserved(self) -> bool:
        return not self.identity_violations


def _text(value: Any) -> str:
    return str(value or "").strip()


def _records(knowledge_base: dict[str, Any] | None, collection: str) -> list[dict[str, Any]]:
    values = (knowledge_base or {}).get(collection)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def _entity_index(
    knowledge_base: dict[str, Any] | None,
    collection: str,
    id_field: str,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in _records(knowledge_base, collection):
        entity_id = _text(item.get(id_field))
        if entity_id:
            index[entity_id] = item
    return index


def _entity_revision(item: dict[str, Any]) -> str:
    """Prefer the stored revision hash; fall back to hashing the record.

    A record with no ``revision_id`` still has to participate in the diff,
    otherwise an edit to it would read as "nothing changed" — the exact
    silent-drift failure this vector is meant to catch.
    """
    revision = _text(item.get("revision_id"))
    if revision:
        return revision
    return stable_hash(
        {key: value for key, value in item.items() if key != "revision_id"},
        prefix="ckdr_",
    )


def knowledge_revision_vector(
    knowledge_base: dict[str, Any] | None,
) -> KnowledgeRevisionVector:
    """Address every knowledge record by a stable revision-vector key."""
    base = knowledge_base if isinstance(knowledge_base, dict) else {}
    revisions: dict[str, str] = {}
    base_revision = _text(base.get("revision_id"))
    if base_revision:
        revisions["course_knowledge_base"] = base_revision

    for collection, id_field, prefix in ENTITY_SPECS:
        for entity_id, item in sorted(_entity_index(base, collection, id_field).items()):
            revisions[f"{prefix}:{entity_id}"] = _entity_revision(item)

    return KnowledgeRevisionVector(
        course_id=_text(base.get("course_id")),
        knowledge_base_revision_id=base_revision,
        lifecycle_status=_text(base.get("lifecycle_status")),
        revisions=revisions,
    )


def _normalize_identity_map(identity_map: dict[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for old_id, new_ids in (identity_map or {}).items():
        key = _text(old_id)
        if not key:
            continue
        values = new_ids if isinstance(new_ids, (list, tuple, set)) else [new_ids]
        resolved = [_text(value) for value in values if _text(value)]
        normalized[key] = sorted(dict.fromkeys(resolved))
    return normalized


def check_knowledge_identity(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
    *,
    identity_map: dict[str, Any] | None = None,
) -> list[KnowledgeIdentityViolation]:
    """Report stable-identity and source-binding rewrites.

    Disappearing without a mapping, and repointing an anchor or source binding
    in place, are the two ways a knowledge edit silently orphans downstream
    references and historical evidence. Both are reported here rather than left
    to be discovered when a reverse lookup returns nothing.
    """
    mapping = _normalize_identity_map(identity_map)
    violations: list[KnowledgeIdentityViolation] = []

    previous_points = _entity_index(previous, "knowledge_points", "knowledge_id")
    current_points = _entity_index(current, "knowledge_points", "knowledge_id")

    for knowledge_id, point in sorted(previous_points.items()):
        if knowledge_id in current_points:
            continue
        targets = mapping.get(knowledge_id)
        if not targets:
            violations.append(KnowledgeIdentityViolation(
                code="knowledge_identity_dropped",
                entity_kind="knowledge_point",
                entity_id=knowledge_id,
                message=(
                    f"知识点「{_text(point.get('name')) or knowledge_id}」被移除，"
                    "但没有旧新 ID 映射；历史作答与下游绑定会失去指向"
                ),
            ))
            continue
        unresolved = [item for item in targets if item not in current_points]
        if unresolved:
            violations.append(KnowledgeIdentityViolation(
                code="knowledge_identity_map_unresolved",
                entity_kind="knowledge_point",
                entity_id=knowledge_id,
                message=(
                    f"知识点 {knowledge_id} 的映射目标不存在于新知识库："
                    f"{'、'.join(unresolved)}"
                ),
            ))

    for knowledge_id, point in sorted(current_points.items()):
        before = previous_points.get(knowledge_id)
        if not before:
            continue
        for field in _IDENTITY_ANCHOR_FIELDS:
            if field == "knowledge_id":
                continue
            if _text(before.get(field)) != _text(point.get(field)):
                violations.append(KnowledgeIdentityViolation(
                    code="knowledge_anchor_rewritten",
                    entity_kind="knowledge_point",
                    entity_id=knowledge_id,
                    message=(
                        f"知识点 {knowledge_id} 的 {field} 被直接改写"
                        f"（{_text(before.get(field))} -> {_text(point.get(field))}），"
                        "稳定身份只能通过映射迁移"
                    ),
                ))
        for field in _SOURCE_BINDING_FIELDS:
            was = [_text(item) for item in before.get(field) or []]
            now = [_text(item) for item in point.get(field) or []]
            dropped = sorted(set(was) - set(now))
            if dropped and _text(point.get("status")) not in _RETIRED_STATUSES:
                violations.append(KnowledgeIdentityViolation(
                    code="knowledge_source_binding_dropped",
                    entity_kind="knowledge_point",
                    entity_id=knowledge_id,
                    message=(
                        f"知识点 {knowledge_id} 的来源绑定 {field} 丢失"
                        f"{'、'.join(dropped)}；来源绑定不得被直接改写"
                    ),
                ))

    return violations


def knowledge_revision_event(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
    *,
    command_id: str = "",
    operation: str = "update_knowledge",
    identity_map: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> KnowledgeRevisionEvent:
    """Diff two knowledge revisions into a durable, per-entity change record."""
    before = knowledge_revision_vector(previous)
    after = knowledge_revision_vector(current)
    course_id = after.course_id or before.course_id
    if before.course_id and after.course_id and before.course_id != after.course_id:
        raise ValueError("Knowledge revision event cannot span multiple courses")

    before_keys = set(before.revisions)
    after_keys = set(after.revisions)
    mapping = _normalize_identity_map(identity_map)
    timestamp = created_at or datetime.now(timezone.utc).isoformat()

    payload = {
        "course_id": course_id,
        "command_id": command_id,
        "operation": operation,
        "previous": before.model_dump(mode="json"),
        "current": after.model_dump(mode="json"),
        "changed_source_keys": sorted(
            key
            for key in before_keys & after_keys
            if before.revisions[key] != after.revisions[key]
        ),
        "added_source_keys": sorted(after_keys - before_keys),
        "removed_source_keys": sorted(before_keys - after_keys),
        "identity_map": mapping,
        "created_at": timestamp,
    }
    violations = check_knowledge_identity(previous, current, identity_map=mapping)
    return KnowledgeRevisionEvent(
        event_id=stable_hash(payload, prefix="ckre_"),
        identity_violations=violations,
        **payload,
    )


def changed_knowledge_ids(event: KnowledgeRevisionEvent) -> list[str]:
    """Knowledge point ids touched by this revision, for reverse lookup."""
    ids: set[str] = set()
    for key in (
        list(event.changed_source_keys)
        + list(event.added_source_keys)
        + list(event.removed_source_keys)
    ):
        prefix, _, entity_id = key.partition(":")
        if prefix == "point" and entity_id:
            ids.add(entity_id)
    ids.update(event.identity_map)
    for targets in event.identity_map.values():
        ids.update(targets)
    return sorted(ids)


def knowledge_revision_snapshot(event: KnowledgeRevisionEvent) -> dict[str, Any]:
    """Stable, readable projection for regression snapshots.

    Deliberately drops timestamps, event ids and full vectors: those drift on
    unrelated edits and would turn a snapshot test into noise that hides real
    impact regressions. Only counts by kind and the affected ids survive.
    """
    def _by_kind(keys: list[str]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for key in keys:
            prefix, _, entity_id = key.partition(":")
            grouped.setdefault(prefix, []).append(entity_id or prefix)
        return {kind: sorted(values) for kind, values in sorted(grouped.items())}

    return {
        "operation": event.operation,
        "changed": _by_kind(event.changed_source_keys),
        "added": _by_kind(event.added_source_keys),
        "removed": _by_kind(event.removed_source_keys),
        "identity_map": {key: list(value) for key, value in sorted(event.identity_map.items())},
        "identity_violations": sorted(item.code for item in event.identity_violations),
    }


__all__ = [
    "ENTITY_SPECS",
    "KNOWLEDGE_REVISION_EVENT_SCHEMA",
    "KNOWLEDGE_REVISION_VECTOR_SCHEMA",
    "KnowledgeIdentityViolation",
    "KnowledgeRevisionEvent",
    "KnowledgeRevisionVector",
    "changed_knowledge_ids",
    "check_knowledge_identity",
    "knowledge_revision_event",
    "knowledge_revision_snapshot",
    "knowledge_revision_vector",
]
