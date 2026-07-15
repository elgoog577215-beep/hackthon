"""资料驱动课程生成 V3 的稳定数据契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MaterialStatus = Literal[
    "uploaded",
    "pending",
    "parsing",
    "parsed",
    "degraded",
    "failed",
    "metadata_only",
]
MaterialPurpose = Literal[
    "content_source",
    "style_reference",
    "question_source",
    "supplement",
    "weak_context",
]
MaterialPriority = Literal["core", "supporting", "weak"]
MaterialAuthority = Literal["primary", "secondary", "context_only"]
MaterialUsagePolicy = Literal["must_use", "prefer", "optional", "style_only"]


class MaterialAsset(BaseModel):
    asset_id: str
    filename: str
    extension: str
    mime_type: str
    detected_mime: str
    size_bytes: int = Field(ge=0)
    sha256: str
    status: MaterialStatus = "uploaded"
    source_name: str
    upload_batch_id: str = ""
    bound_course_ids: list[str] = Field(default_factory=list)
    parser_name: str = ""
    parser_version: str = ""
    parse_options_hash: str = ""
    parse_quality: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    warnings: list[str] = Field(default_factory=list)
    uploaded_at: str
    updated_at: str


class MaterialBinding(BaseModel):
    asset_id: str
    purpose: MaterialPurpose = "content_source"
    priority: MaterialPriority = "core"
    authority: MaterialAuthority = "primary"
    usage_policy: MaterialUsagePolicy = "prefer"
    user_description: str = Field(default="", max_length=2000)
    source_label: str = Field(default="", max_length=200)


class DocumentLocator(BaseModel):
    page: int | None = None
    slide: int | None = None
    section_path: list[str] = Field(default_factory=list)
    bbox: dict[str, float] | None = None


class DocumentBlock(BaseModel):
    block_id: str
    kind: Literal[
        "title",
        "heading",
        "paragraph",
        "list_item",
        "table",
        "formula",
        "code",
        "picture",
        "question",
        "other",
    ] = "paragraph"
    text: str = ""
    order: int = Field(ge=0)
    parent_block_id: str | None = None
    locator: DocumentLocator = Field(default_factory=DocumentLocator)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    document_id: str
    asset_id: str
    schema_version: str = "parsed_document_v1"
    source_sha256: str
    parse_status: Literal["parsed", "degraded", "failed", "metadata_only"]
    parser_name: str
    parser_version: str
    parse_options_hash: str
    blocks: list[DocumentBlock] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str = ""
    created_at: str


class EvidenceUnit(BaseModel):
    evidence_id: str
    asset_id: str
    document_id: str
    kind: Literal[
        "definition",
        "claim",
        "procedure",
        "example",
        "question",
        "formula",
        "table",
        "style_sample",
        "context",
    ]
    source_text: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    block_ids: list[str]
    locator: DocumentLocator
    content_hash: str
    purpose: MaterialPurpose
    priority: MaterialPriority
    authority: MaterialAuthority
    usage_policy: MaterialUsagePolicy
    factual_allowed: bool = True
    confidence: Literal["high", "medium", "low"] = "high"


class EvidenceConflict(BaseModel):
    conflict_id: str
    topic: str
    evidence_ids: list[str]
    resolution: Literal["authority_selected", "preserve_multiple", "unresolved"]
    selected_evidence_id: str | None = None
    message: str


class CoverageGap(BaseModel):
    gap_id: str
    objective: str
    reason: str
    strategy: Literal["general_knowledge", "background_only", "blocked"]


class NodeGroundingContract(BaseModel):
    contract_version: str = "node_grounding_v1"
    required_evidence_ids: list[str] = Field(default_factory=list)
    optional_evidence_ids: list[str] = Field(default_factory=list)
    question_evidence_ids: list[str] = Field(default_factory=list)
    style_asset_ids: list[str] = Field(default_factory=list)
    allow_general_knowledge: bool = True
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class EvidenceCoveragePlan(BaseModel):
    plan_version: str = "evidence_coverage_v1"
    strategy: Literal["strict_grounded", "material_first", "general_assisted"] = "material_first"
    evidence_count: int = 0
    asset_coverage: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    gaps: list[CoverageGap] = Field(default_factory=list)
    node_contracts: dict[str, NodeGroundingContract] = Field(default_factory=dict)


__all__ = [
    "CoverageGap",
    "DocumentBlock",
    "DocumentLocator",
    "EvidenceConflict",
    "EvidenceCoveragePlan",
    "EvidenceUnit",
    "MaterialAsset",
    "MaterialAuthority",
    "MaterialBinding",
    "MaterialPriority",
    "MaterialPurpose",
    "MaterialStatus",
    "MaterialUsagePolicy",
    "NodeGroundingContract",
    "ParsedDocument",
]
