"""Canonical course document models and deterministic legacy projection."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from content_blocks import blocks_to_markdown, content_fingerprint, normalize_blocks


COURSE_DOCUMENT_SCHEMA = "course_document_v1"

BlockKind = Literal[
    "rich_text",
    "formula",
    "code",
    "image",
    "audio",
    "video",
    "diagram",
    "table",
    "callout",
    "source_excerpt",
    "practice_ref",
    "code_lab",
    "reflection",
    "project",
    "mastery_check",
    "review_checkpoint",
    "remediation_slot",
    "graph_embed",
]

BlockRole = Literal[
    "orientation",
    "prerequisite",
    "concept",
    "reasoning",
    "example",
    "counterexample",
    "application",
    "misconception",
    "checkpoint",
    "remediation",
    "summary",
    "transfer",
]

_KINDS = {
    "rich_text", "formula", "code", "image", "audio", "video", "diagram",
    "table", "callout", "source_excerpt", "practice_ref", "code_lab",
    "reflection", "project", "mastery_check", "review_checkpoint",
    "remediation_slot", "graph_embed",
}

_ROLES = {
    "orientation", "prerequisite", "concept", "reasoning", "example",
    "counterexample", "application", "misconception", "checkpoint",
    "remediation", "summary", "transfer",
}

_LEGACY_NODE_FIELDS = {
    "node_id", "parent_node_id", "node_name", "node_level", "node_content",
    "content_blocks", "children",
}


class CourseSection(BaseModel):
    section_id: str
    parent_section_id: str | None = None
    title: str
    position: int = Field(ge=0)
    level: int = Field(default=1, ge=1)
    learning_objective: str = ""
    objective_id: str = ""
    objective_revision_id: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class CourseBlock(BaseModel):
    block_id: str
    section_id: str
    parent_group_id: str | None = None
    position: int = Field(ge=0)
    kind: BlockKind = "rich_text"
    role: BlockRole = "concept"
    payload: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[str] = Field(default_factory=list)
    objective_refs: list[str] = Field(default_factory=list)
    concept_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    visibility_rule: dict[str, Any] = Field(default_factory=dict)
    internal_revision: str = ""
    status: Literal["draft", "final", "retired"] = "final"


class CourseDocument(BaseModel):
    schema_version: Literal["course_document_v1"] = COURSE_DOCUMENT_SCHEMA
    course_id: str
    title: str
    document_revision: str = ""
    sections: list[CourseSection] = Field(default_factory=list)
    blocks: list[CourseBlock] = Field(default_factory=list)


def stable_hash(value: Any, *, prefix: str) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{prefix}{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def legacy_source_checksum(course_data: dict[str, Any]) -> str:
    source = {
        "course_id": course_data.get("course_id"),
        "course_name": course_data.get("course_name"),
        "nodes": course_data.get("nodes") or [],
    }
    return stable_hash(source, prefix="legacy_")


def refresh_block_revision(block: CourseBlock | dict[str, Any]) -> CourseBlock:
    item = block if isinstance(block, CourseBlock) else CourseBlock.model_validate(block)
    payload = item.model_dump(mode="json", exclude={"internal_revision"})
    item.internal_revision = stable_hash(payload, prefix="cbr_")
    return item


def refresh_document_revision(document: CourseDocument | dict[str, Any]) -> CourseDocument:
    item = document if isinstance(document, CourseDocument) else CourseDocument.model_validate(document)
    item.blocks = [refresh_block_revision(block) for block in item.blocks]
    payload = item.model_dump(mode="json", exclude={"document_revision"})
    item.document_revision = stable_hash(payload, prefix="cdr_")
    return item


def document_from_legacy_course(course_data: dict[str, Any]) -> CourseDocument:
    sections: list[CourseSection] = []
    blocks: list[CourseBlock] = []
    nodes = list(_walk_legacy_nodes(course_data.get("nodes") or []))

    for index, node in enumerate(nodes):
        section_id = str(node.get("node_id") or f"section-{index + 1}")
        parent_id = str(node.get("parent_node_id") or "")
        attributes = {
            key: deepcopy(value)
            for key, value in node.items()
            if key not in _LEGACY_NODE_FIELDS
        }
        objective_id = str(node.get("objective_id") or "")
        sections.append(CourseSection(
            section_id=section_id,
            parent_section_id=None if parent_id in {"", "root", "None"} else parent_id,
            title=str(node.get("node_name") or "未命名章节"),
            position=index,
            level=max(1, int(node.get("node_level") or 1)),
            learning_objective=str(node.get("learning_objective") or ""),
            objective_id=objective_id,
            objective_revision_id=str(node.get("objective_revision_id") or ""),
            attributes=attributes,
        ))

        legacy_blocks = normalize_blocks(
            section_id,
            node.get("content_blocks"),
            str(node.get("node_content") or ""),
        )
        for block_index, legacy_block in enumerate(legacy_blocks):
            metadata = legacy_block.get("metadata") if isinstance(legacy_block.get("metadata"), dict) else {}
            kind = str(metadata.get("kind") or "rich_text")
            if kind not in _KINDS:
                kind = "rich_text"
            role = str(metadata.get("role") or _legacy_role(legacy_block))
            if role not in _ROLES:
                role = "concept"
            block = CourseBlock(
                block_id=str(legacy_block.get("block_id") or f"{section_id}-block-{block_index + 1}"),
                section_id=section_id,
                parent_group_id=legacy_block.get("parent_block_id"),
                position=block_index,
                kind=kind,
                role=role,
                payload={
                    "title": str(legacy_block.get("title") or ""),
                    "markdown": str(legacy_block.get("content") or ""),
                    "summary": str(legacy_block.get("summary") or ""),
                    "knowledge_binding_status": metadata.get("knowledge_binding_status"),
                },
                asset_refs=_unique_refs(metadata.get("asset_refs")),
                objective_refs=_unique_refs(
                    metadata.get("objective_refs"),
                    [objective_id] if objective_id else [],
                ),
                concept_refs=_unique_refs(metadata.get("concept_refs")),
                evidence_refs=_unique_refs(metadata.get("evidence_refs")),
                status="draft" if legacy_block.get("status") == "draft" else "final",
            )
            blocks.append(refresh_block_revision(block))

    return refresh_document_revision(CourseDocument(
        course_id=str(course_data.get("course_id") or ""),
        title=str(course_data.get("course_name") or "未命名课程"),
        sections=sections,
        blocks=blocks,
    ))


def document_from_generation_draft(course_data: dict[str, Any]) -> CourseDocument:
    """Compile the task-local generation shape into the canonical course document."""
    document = document_from_legacy_course(course_data)
    nodes = {
        str(node.get("node_id") or ""): node
        for node in _walk_legacy_nodes(course_data.get("nodes") or [])
        if node.get("node_id")
    }
    for block in document.blocks:
        node = nodes.get(block.section_id) or {}
        objective_id = str(node.get("objective_id") or "")
        if objective_id and objective_id not in block.objective_refs:
            block.objective_refs.append(objective_id)
        block.evidence_refs = _unique_refs(
            node.get("evidence_refs"),
            (node.get("grounding_contract") or {}).get("required_evidence_ids"),
            [
                item.get("evidence_id") or item.get("evidence_ref")
                for item in node.get("grounding_annotations") or []
                if isinstance(item, dict)
            ],
        )
        block.asset_refs = _unique_refs(
            node.get("asset_refs"),
            node.get("media_asset_refs"),
        )
        if block.payload.get("knowledge_binding_status") not in {"matched", "unmatched"}:
            block.concept_refs = _unique_refs(node.get("concept_refs"))
    return refresh_document_revision(document)


def course_view_from_document(
    course_data: dict[str, Any],
    document: CourseDocument | dict[str, Any],
) -> dict[str, Any]:
    doc = document if isinstance(document, CourseDocument) else CourseDocument.model_validate(document)
    view = deepcopy(course_data)
    view["course_schema_version"] = COURSE_DOCUMENT_SCHEMA
    view["course_document_revision"] = doc.document_revision
    view["course_document_authoritative"] = True
    view["nodes"] = []

    blocks_by_section: dict[str, list[CourseBlock]] = {}
    for block in sorted(doc.blocks, key=lambda item: (item.section_id, item.position)):
        blocks_by_section.setdefault(block.section_id, []).append(block)

    for section in sorted(doc.sections, key=lambda item: item.position):
        legacy_blocks = [_legacy_block(block) for block in blocks_by_section.get(section.section_id, [])]
        node = deepcopy(section.attributes)
        node.update({
            "node_id": section.section_id,
            "parent_node_id": section.parent_section_id or "root",
            "node_name": section.title,
            "node_level": section.level,
            "node_content": blocks_to_markdown(legacy_blocks),
            "content_blocks": legacy_blocks,
            "learning_objective": section.learning_objective,
            "objective_id": section.objective_id,
            "objective_revision_id": section.objective_revision_id,
        })
        view["nodes"].append(node)
    return view


def _legacy_block(block: CourseBlock) -> dict[str, Any]:
    title = str(block.payload.get("title") or "")
    content = str(block.payload.get("markdown") or block.payload.get("text") or "")
    legacy_type = block.role if block.role in {
        "concept", "reasoning", "example", "application", "summary"
    } else {
        "orientation": "intro",
        "checkpoint": "exercise",
        "misconception": "summary",
    }.get(block.role, "custom")
    return {
        "block_id": block.block_id,
        "parent_block_id": block.parent_group_id,
        "type": legacy_type,
        "title": title,
        "content": content,
        "summary": str(block.payload.get("summary") or ""),
        "order": block.position,
        "status": "draft" if block.status == "draft" else "final",
        "metadata": {
            "kind": block.kind,
            "role": block.role,
            "asset_refs": list(block.asset_refs),
            "objective_refs": list(block.objective_refs),
            "concept_refs": list(block.concept_refs),
            "evidence_refs": list(block.evidence_refs),
            "knowledge_binding_status": block.payload.get("knowledge_binding_status"),
        },
        "content_fingerprint": content_fingerprint(content),
        "block_revision_id": block.internal_revision,
    }


def _legacy_role(block: dict[str, Any]) -> str:
    old_type = str(block.get("type") or "concept")
    title = str(block.get("title") or "").lower()
    if old_type == "intro":
        return "orientation"
    if old_type == "exercise":
        return "example" if any(word in title for word in ("例题", "推演", "示例")) else "checkpoint"
    if old_type == "summary":
        return "misconception" if any(word in title for word in ("错误", "误区")) else "summary"
    if old_type in {"concept", "reasoning", "example", "application"}:
        return old_type
    return "concept"


def _walk_legacy_nodes(nodes: list[dict[str, Any]]):
    seen: set[str] = set()

    def visit(node: dict[str, Any]):
        node_id = str(node.get("node_id") or "")
        if node_id and node_id in seen:
            return
        if node_id:
            seen.add(node_id)
        yield node
        for child in node.get("children") or []:
            if isinstance(child, dict):
                yield from visit(child)

    for item in nodes:
        if isinstance(item, dict):
            yield from visit(item)


def _unique_refs(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else []
        for item in items:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
    return result
