"""Deterministic, course-native teaching graph for slide-deck V6.

This compiler operates on canonical course blocks and teaching dependencies. It
does not know presentation character budgets; those belong to final page
allocation after story planning.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseBlock, CourseDocument, stable_hash


ArtifactKind = Literal[
    "code",
    "formula",
    "table",
    "diagram",
    "image",
    "data",
    "experiment",
    "source_excerpt",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoursePresentationUnitV1(_StrictModel):
    teaching_unit_id: str
    section_id: str
    source_ordinal: int = Field(ge=0)
    primary_block_ids: list[str] = Field(min_length=1)
    supporting_block_ids: list[str] = Field(default_factory=list)
    teaching_intent: str
    artifact_kinds: list[ArtifactKind] = Field(default_factory=list)
    prerequisite_unit_ids: list[str] = Field(default_factory=list)
    dependent_unit_ids: list[str] = Field(default_factory=list)
    source_text: str


class CoursePresentationGraphV1(_StrictModel):
    schema_version: Literal["course_presentation_graph_v1"] = (
        "course_presentation_graph_v1"
    )
    course_id: str
    source_document_revision: str
    graph_digest: str
    units: list[CoursePresentationUnitV1] = Field(default_factory=list)
    formal_block_ids: list[str] = Field(default_factory=list)
    primary_block_coverage: float = Field(ge=0, le=1)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


_ANCHOR_ROLES = {"orientation", "prerequisite", "objective", "concept"}
_ARTIFACT_KIND_BY_BLOCK_KIND: dict[str, ArtifactKind] = {
    "code": "code",
    "code_lab": "code",
    "formula": "formula",
    "table": "table",
    "diagram": "diagram",
    "graph_embed": "diagram",
    "image": "image",
    "source_excerpt": "source_excerpt",
}
_CODE_FENCE_RE = re.compile(r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n.+?```", re.S)
_DISPLAY_FORMULA_RE = re.compile(r"\$\$.+?\$\$|\\\[.+?\\\]", re.S)
_MARKDOWN_TABLE_RE = re.compile(r"(?m)^\s*\|.+\|\s*\n\s*\|\s*:?-{3,}")


def block_source_text(block: CourseBlock) -> str:
    payload = block.payload or {}
    return str(
        payload.get("markdown")
        or payload.get("text")
        or payload.get("content")
        or payload.get("summary")
        or ""
    ).strip()


def _artifact_kinds(block: CourseBlock) -> list[ArtifactKind]:
    kinds: list[ArtifactKind] = []
    explicit = _ARTIFACT_KIND_BY_BLOCK_KIND.get(block.kind)
    if explicit:
        kinds.append(explicit)
    text = block_source_text(block)
    if block.kind == "rich_text":
        if _CODE_FENCE_RE.search(text):
            kinds.append("code")
        if _DISPLAY_FORMULA_RE.search(text):
            kinds.append("formula")
        if _MARKDOWN_TABLE_RE.search(text):
            kinds.append("table")
    payload_kind = str((block.payload or {}).get("artifact_kind") or "").strip()
    if payload_kind in ArtifactKind.__args__:  # type: ignore[attr-defined]
        kinds.append(payload_kind)  # type: ignore[arg-type]
    return list(dict.fromkeys(kinds))


def block_artifact_kinds(block: CourseBlock) -> list[ArtifactKind]:
    """Return source-backed characteristic artifacts for one canonical block."""

    return _artifact_kinds(block)


def _teaching_intent(blocks: list[CourseBlock]) -> str:
    roles = [block.role for block in blocks]
    artifacts = {kind for block in blocks for kind in _artifact_kinds(block)}
    if artifacts:
        return "artifact_explanation"
    if any(role in {"activity", "checkpoint", "feedback"} for role in roles):
        return "practice_feedback"
    if any(role in {"misconception", "remediation", "counterexample"} for role in roles):
        return "misconception_repair"
    if any(role in {"reasoning"} for role in roles):
        return "mechanism"
    if any(role in {"example", "application", "transfer"} for role in roles):
        return "worked_example"
    if any(role == "summary" for role in roles):
        return "recap"
    return "concept_explanation"


def _ordered_formal_blocks(document: CourseDocument) -> list[CourseBlock]:
    section_order = {
        section.section_id: (section.position, section.level, index)
        for index, section in enumerate(document.sections)
    }
    unknown_base = len(section_order)
    return sorted(
        (block for block in document.blocks if block.status == "final"),
        key=lambda block: (
            section_order.get(block.section_id, (unknown_base, 99, unknown_base)),
            block.position,
            block.block_id,
        ),
    )


def _partition_section(blocks: list[CourseBlock]) -> list[list[CourseBlock]]:
    groups: list[list[CourseBlock]] = []
    current: list[CourseBlock] = []
    current_group_id: str | None = None
    for block in blocks:
        starts_new_anchor = (
            bool(current)
            and block.role in _ANCHOR_ROLES
            and any(item.role in _ANCHOR_ROLES for item in current)
            and not (
                block.parent_group_id
                and current_group_id
                and block.parent_group_id == current_group_id
            )
        )
        if starts_new_anchor:
            groups.append(current)
            current = []
            current_group_id = None
        current.append(block)
        current_group_id = current_group_id or block.parent_group_id
    if current:
        groups.append(current)
    return groups


def compile_course_presentation_graph(
    document: CourseDocument,
    *,
    teaching_plan: dict[str, Any] | None = None,
) -> CoursePresentationGraphV1:
    """Compile complete source-ordered teaching units without text pagination."""

    ordered = _ordered_formal_blocks(document)
    by_section: dict[str, list[CourseBlock]] = defaultdict(list)
    section_sequence: list[str] = []
    for block in ordered:
        if block.section_id not in by_section:
            section_sequence.append(block.section_id)
        by_section[block.section_id].append(block)

    units: list[CoursePresentationUnitV1] = []
    previous_unit_id = ""
    for section_id in section_sequence:
        for blocks in _partition_section(by_section[section_id]):
            ordinal = len(units)
            block_ids = [block.block_id for block in blocks]
            unit_id = stable_hash(
                {
                    "revision": document.document_revision,
                    "section_id": section_id,
                    "block_ids": block_ids,
                    "ordinal": ordinal,
                },
                prefix="cpu_",
            )
            unit = CoursePresentationUnitV1(
                teaching_unit_id=unit_id,
                section_id=section_id,
                source_ordinal=ordinal,
                primary_block_ids=block_ids,
                teaching_intent=_teaching_intent(blocks),
                artifact_kinds=list(
                    dict.fromkeys(
                        kind for block in blocks for kind in _artifact_kinds(block)
                    )
                ),
                prerequisite_unit_ids=[previous_unit_id] if previous_unit_id else [],
                source_text="\n\n".join(
                    text for block in blocks if (text := block_source_text(block))
                ),
            )
            if units:
                units[-1].dependent_unit_ids.append(unit_id)
            units.append(unit)
            previous_unit_id = unit_id

    formal_ids = [block.block_id for block in ordered]
    owned_ids = [block_id for unit in units for block_id in unit.primary_block_ids]
    unique_owned = set(owned_ids)
    diagnostics: list[dict[str, Any]] = []
    if len(owned_ids) != len(unique_owned):
        diagnostics.append({"code": "duplicate_primary_block_owner"})
    missing = [block_id for block_id in formal_ids if block_id not in unique_owned]
    if missing:
        diagnostics.append({"code": "formal_blocks_missing", "block_ids": missing})
    coverage = 1.0 if not formal_ids else len(unique_owned.intersection(formal_ids)) / len(formal_ids)
    graph_payload = {
        "course_id": document.course_id,
        "revision": document.document_revision,
        "teaching_plan": teaching_plan or {},
        "units": [unit.model_dump(mode="json") for unit in units],
    }
    return CoursePresentationGraphV1(
        course_id=document.course_id,
        source_document_revision=document.document_revision,
        graph_digest=stable_hash(graph_payload, prefix="cpgraph_"),
        units=units,
        formal_block_ids=formal_ids,
        primary_block_coverage=coverage,
        diagnostics=diagnostics,
    )


__all__ = [
    "ArtifactKind",
    "CoursePresentationGraphV1",
    "CoursePresentationUnitV1",
    "block_artifact_kinds",
    "block_source_text",
    "compile_course_presentation_graph",
]
