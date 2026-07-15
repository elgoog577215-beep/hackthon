"""Shared presentation domain and transport contracts.

The course document is input-only. Presentation revisions and artifacts live in
their own repository and refer back to an immutable source snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TemplateId = Literal["lingzhi-classroom", "lingzhi-engineering", "lingzhi-academic"]
LayoutId = Literal["L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08", "L09", "L10"]
DeckStatus = Literal[
    "draft", "generating", "editing", "quality_blocked", "ready",
    "exporting", "exported", "failed",
]
SlideStatus = Literal["planned", "generating", "ready", "failed"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(StrictModel):
    course_id: str = Field(min_length=1, max_length=200)
    source_format: Literal["canonical", "legacy_snapshot"]
    version_id: str = Field(min_length=1, max_length=200)
    document_revision: str = Field(min_length=1, max_length=200)
    blueprint_revision_id: str = ""
    asset_bundle_revision_id: str = ""
    source_snapshot_id: str = Field(min_length=1, max_length=200)
    source_snapshot_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PresentationScope(StrictModel):
    type: Literal["chapter", "course"] = "chapter"
    section_ids: list[str] = Field(default_factory=list, max_length=500)


class SlideSourceRefs(StrictModel):
    section_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    block_revision_ids: list[str] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class SlideBlock(StrictModel):
    block_id: str = Field(min_length=1, max_length=200)
    type: Literal["text", "bullets", "code", "quote", "comparison", "exercise", "callout"] = "text"
    title: str = Field(default="", max_length=300)
    content: str = Field(default="", max_length=6000)
    items: list[str] = Field(default_factory=list, max_length=12)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityIssue(StrictModel):
    code: str = Field(min_length=1, max_length=120)
    severity: Literal["info", "warning", "blocking"]
    message: str = Field(min_length=1, max_length=2000)
    target_type: Literal["deck", "slide", "source", "artifact"] = "deck"
    target_id: str = ""
    fix_action: str = Field(default="", max_length=2000)


class SlideQuality(StrictModel):
    issues: list[QualityIssue] = Field(default_factory=list)
    capacity: dict[str, int | float | bool] = Field(default_factory=dict)


class Slide(StrictModel):
    slide_id: str = Field(min_length=1, max_length=200)
    position: int = Field(ge=0)
    layout_id: LayoutId
    status: SlideStatus = "planned"
    title: str = Field(default="", max_length=300)
    subtitle: str = Field(default="", max_length=500)
    key_message: str = Field(default="", max_length=1000)
    blocks: list[SlideBlock] = Field(default_factory=list, max_length=12)
    speaker_notes: str = Field(default="", max_length=10000)
    source_refs: SlideSourceRefs = Field(default_factory=SlideSourceRefs)
    quality: SlideQuality = Field(default_factory=SlideQuality)


class DeckRevision(StrictModel):
    revision_id: str = Field(min_length=1, max_length=200)
    parent_revision_id: str | None = None
    deck_id: str = Field(min_length=1, max_length=200)
    reason: Literal["initial_generation", "chat_patch", "reorder", "restore", "quality_repair"]
    created_at: str = Field(default_factory=utc_now)
    created_by: str = "system"
    source_snapshot_id: str = Field(min_length=1, max_length=200)
    slide_order: list[str] = Field(default_factory=list)
    slides: list[Slide] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_slide_order(self) -> "DeckRevision":
        slide_ids = [slide.slide_id for slide in self.slides]
        if len(slide_ids) != len(set(slide_ids)):
            raise ValueError("slide_id must be unique")
        if self.slide_order != slide_ids:
            raise ValueError("slide_order must exactly match slides order")
        return self


class PresentationDeck(StrictModel):
    schema_version: int = 1
    deck_id: str = Field(min_length=1, max_length=200)
    course_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    source_ref: SourceRef
    scope: PresentationScope
    purpose: Literal["teaching", "self_study"] = "teaching"
    template_id: TemplateId = "lingzhi-classroom"
    status: DeckStatus = "draft"
    active_revision_id: str | None = None
    active_generation_id: str | None = None
    latest_quality_report_id: str | None = None
    latest_artifact_id: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class GenerationWorkingSnapshot(StrictModel):
    generation_id: str
    deck_id: str
    event_seq: int = Field(default=0, ge=0)
    outline_revision: int = Field(default=1, ge=1)
    slide_order: list[str] = Field(default_factory=list)
    slides: list[Slide] = Field(default_factory=list)
    cancelled_slot_ids: list[str] = Field(default_factory=list)
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


EventType = Literal[
    "deck_outline", "slide_upsert", "slide_patch", "progress",
    "quality_report", "generation_complete", "export_ready", "error",
]


class PresentationEvent(StrictModel):
    schema_version: Literal["presentation-event/v1"] = "presentation-event/v1"
    event_type: EventType
    deck_id: str
    generation_id: str
    event_seq: int = Field(ge=1)
    outline_revision: int = Field(ge=1)
    revision_id: str | None = None
    emitted_at: str = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def sse_id(self) -> str:
        return f"{self.generation_id}:{self.event_seq}"


class QualityReport(StrictModel):
    report_id: str
    deck_id: str
    revision_id: str | None = None
    source_snapshot_id: str
    status: Literal["passed", "blocked", "advisory"]
    issues: list[QualityIssue] = Field(default_factory=list)
    checked_at: str = Field(default_factory=utc_now)
    render_measurement: dict[str, Any] = Field(default_factory=dict)


class DeckProposal(StrictModel):
    proposal_id: str
    request_id: str
    deck_id: str
    base_revision_id: str
    scope: Literal["slide", "deck"]
    slide_ids: list[str] = Field(default_factory=list, max_length=50)
    prompt: str = Field(min_length=1, max_length=5000)
    patches: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    status: Literal["proposed", "applied", "cancelled", "stale"] = "proposed"
    created_at: str = Field(default_factory=utc_now)


class ArtifactReceipt(StrictModel):
    artifact_id: str
    deck_id: str
    revision_id: str
    source_snapshot_id: str
    template_id: TemplateId
    template_version: str
    layout_registry_version: str
    html_path: str
    html_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pptx_path: str
    pptx_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    title_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    speaker_notes_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    quality_report_id: str
    created_at: str = Field(default_factory=utc_now)
    stale: bool = False


class CreatePresentationRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    title: str = Field(default="课件草稿", min_length=1, max_length=300)
    scope: PresentationScope
    purpose: Literal["teaching", "self_study"] = "teaching"
    template_id: TemplateId = "lingzhi-classroom"
    page_budget: int = Field(default=8, ge=3, le=30)
    extra_requirements: str = Field(default="", max_length=5000)


class GeneratePresentationRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    expected_revision_id: str | None = None
    page_budget: int = Field(default=8, ge=3, le=30)
    extra_requirements: str = Field(default="", max_length=5000)


class ChatPresentationRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    expected_revision_id: str
    scope: Literal["slide", "deck"] = "slide"
    slide_ids: list[str] = Field(default_factory=list, max_length=50)
    prompt: str = Field(min_length=1, max_length=5000)


class RevisionCommand(StrictModel):
    command_id: str = Field(min_length=8, max_length=200)
    expected_revision_id: str


class FinalizePresentationRequest(RevisionCommand):
    render_measurement: dict[str, Any] = Field(default_factory=dict)


class PreviewMessage(StrictModel):
    version: Literal["presentation-preview/v1"] = "presentation-preview/v1"
    type: Literal["preview:ready", "slide:selected", "render:measured"]
    deck_id: str
    revision_id: str
    revision_checksum: str
    slide_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
