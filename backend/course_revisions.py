"""Deterministic revision vectors and durable course revision events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from course_document import CourseDocument, stable_hash

COURSE_REVISION_EVENT_SCHEMA = "course_revision_event_v1"
COURSE_REVISION_VECTOR_SCHEMA = "course_revision_vector_v1"


class CourseRevisionVector(BaseModel):
    schema_version: Literal["course_revision_vector_v1"] = COURSE_REVISION_VECTOR_SCHEMA
    course_id: str
    revisions: dict[str, str] = Field(default_factory=dict)


class CourseRevisionEvent(BaseModel):
    schema_version: Literal["course_revision_event_v1"] = COURSE_REVISION_EVENT_SCHEMA
    event_id: str
    course_id: str
    command_id: str = ""
    operation: str = "update_document"
    previous: CourseRevisionVector
    current: CourseRevisionVector
    changed_source_keys: list[str] = Field(default_factory=list)
    added_source_keys: list[str] = Field(default_factory=list)
    removed_source_keys: list[str] = Field(default_factory=list)
    affected_block_ids: list[str] = Field(default_factory=list)
    created_at: str


def revision_vector_for_document(
    document: CourseDocument | dict[str, Any],
) -> CourseRevisionVector:
    item = document if isinstance(document, CourseDocument) else CourseDocument.model_validate(document)
    revisions: dict[str, str] = {"course_document": item.document_revision}
    blocks_by_section: dict[str, list[dict[str, Any]]] = {}

    for block in sorted(item.blocks, key=lambda value: (value.section_id, value.position, value.block_id)):
        revisions[f"block:{block.block_id}"] = block.internal_revision
        blocks_by_section.setdefault(block.section_id, []).append({
            "block_id": block.block_id,
            "position": block.position,
            "revision": block.internal_revision,
            "status": block.status,
        })

    for section in sorted(item.sections, key=lambda value: (value.position, value.section_id)):
        section_payload = {
            "section": section.model_dump(mode="json"),
            "blocks": blocks_by_section.get(section.section_id, []),
        }
        revisions[f"section:{section.section_id}"] = stable_hash(
            section_payload,
            prefix="csr_",
        )
        if section.objective_id:
            objective_revision = section.objective_revision_id or stable_hash(
                {
                    "objective_id": section.objective_id,
                    "learning_objective": section.learning_objective,
                    "section_id": section.section_id,
                },
                prefix="cor_",
            )
            revisions[f"objective:{section.objective_id}"] = objective_revision

    return CourseRevisionVector(course_id=item.course_id, revisions=revisions)


def revision_event_for_documents(
    previous: CourseDocument | dict[str, Any],
    current: CourseDocument | dict[str, Any],
    *,
    command_id: str = "",
    operation: str = "update_document",
    affected_block_ids: list[str] | None = None,
    created_at: str | None = None,
) -> CourseRevisionEvent:
    before = revision_vector_for_document(previous)
    after = revision_vector_for_document(current)
    if before.course_id != after.course_id:
        raise ValueError("Course revision event cannot span multiple courses")

    before_keys = set(before.revisions)
    after_keys = set(after.revisions)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(
        key
        for key in before_keys & after_keys
        if before.revisions[key] != after.revisions[key]
    )
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    event_payload = {
        "course_id": after.course_id,
        "command_id": command_id,
        "operation": operation,
        "previous": before.model_dump(mode="json"),
        "current": after.model_dump(mode="json"),
        "changed_source_keys": changed,
        "added_source_keys": added,
        "removed_source_keys": removed,
        "affected_block_ids": sorted({str(value) for value in affected_block_ids or [] if value}),
        "created_at": timestamp,
    }
    return CourseRevisionEvent(
        event_id=stable_hash(event_payload, prefix="cre_"),
        **event_payload,
    )
