"""Course-faithful contracts and publication gates for slide-deck V6."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from course_document import CourseBlock, CourseDocument, refresh_document_revision, stable_hash
from course_presentation_graph import (
    CoursePresentationGraphV1,
    CoursePresentationUnitV1,
    block_artifact_kinds,
    block_presentation_text,
    block_source_text,
    page_artifact_kinds,
    page_teaching_intent,
)
from slide_layout_geometry import (
    capacity_profile_items_fit,
    capacity_profile_text_fits,
    diagram_node_layout_metrics,
    semantic_break_positions,
)
from template_layout_contract import TemplateLayoutPackContractV1

V6Status = Literal["v6_ready", "v6_needs_manual_edit", "v6_failed"]
SLIDE_DECK_V6_COMPILER_VERSION = "slide_deck_v6_compiler_v9"

V6_STAGE_CONTRACTS: dict[str, str] = {
    "source": "Freeze canonical source blocks, revisions, and artifact identities.",
    "story": "Normalize and validate deterministic globally unique page identities.",
    "visual": "Bind exactly one source-scoped visual decision to every story page.",
    "template": "Materialize complete source into declared capacity-safe continuations.",
    "quality": "Reject visible source loss, duplication, truncation, or unsupported claims.",
    "render": "Render the validated shared Web/PPTX contract without semantic changes.",
    "publish": "Publish only the finalized candidate whose frozen dependencies still match.",
    "recovery": "Resume only checkpoints compatible with the current build contract.",
}

V6_FAILURE_ROOT_CAUSE_BY_CODE: dict[str, str] = {
    "story_page_id_missing": "page_identity",
    "story_duplicate_page_id": "page_identity",
    "visual_page_coverage_incomplete": "visual_page_mapping",
    "visual_page_duplicate": "visual_page_mapping",
    "visual_page_duplicate_conflict": "visual_page_mapping",
    "visual_page_unknown": "visual_page_mapping",
    "visual_source_binding_mismatch": "visual_page_mapping",
    "visual_layout_binding_mismatch": "visual_page_mapping",
    "template_required_slot_unfilled": "source_slot_binding",
    "template_source_slot_coverage_incomplete": "source_slot_binding",
    "template_source_semantic_fidelity_incomplete": "source_slot_binding",
    "template_slot_capacity_exceeded": "pagination_capacity",
    "template_continuation_contract_invalid": "pagination_contract",
    "template_layout_unavailable": "pagination_contract",
    "continuation_title_unavailable": "source_slot_binding",
    "pagination_expansion_excessive": "pagination_capacity",
    "duplicate_final_page_title": "source_fidelity",
    "source_artifact_visible_fidelity_incomplete": "source_fidelity",
    "source_prose_visible_fidelity_incomplete": "source_fidelity",
    "ordered_step_visible_fidelity_incomplete": "source_fidelity",
    "v6_recovery_contract_mismatch": "checkpoint_contract",
}


def classify_v6_failure(stage: str, code: str) -> dict[str, str]:
    """Return the owning stage and stable root-cause family for diagnostics."""

    owner_stage = stage if stage in V6_STAGE_CONTRACTS else "quality"
    root_cause = V6_FAILURE_ROOT_CAUSE_BY_CODE.get(
        code,
        "checkpoint_contract"
        if "recovery" in code or "checkpoint" in code
        else f"{owner_stage}_contract",
    )
    return {
        "owner_stage": owner_stage,
        "root_cause": root_cause,
        "stage_contract": V6_STAGE_CONTRACTS[owner_stage],
    }


@dataclass(frozen=True)
class _SafePageMaterialization:
    layout: Any
    source_blocks: list[CourseBlock]


@dataclass(frozen=True)
class _LayoutSourceAssignments:
    """One deterministic, source-backed assignment shared by every stage."""

    artifact_slots: dict[str, list[CourseBlock]]
    text_slots: dict[str, list[CourseBlock]]
    unassigned_blocks: list[CourseBlock]
    missing_required_slot_ids: list[str]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class V6Failure(_StrictModel):
    stage: str
    code: str
    message: str
    retryable: bool = False
    chapter_id: str = ""
    page_id: str = ""
    batch_id: str = ""


class V6BuildError(ValueError):
    def __init__(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        retryable: bool = False,
        chapter_id: str = "",
        page_id: str = "",
        batch_id: str = "",
        node_id: str = "",
    ) -> None:
        self.node_id = node_id
        self.failure = V6Failure(
            stage=stage,
            code=code,
            message=message,
            retryable=retryable,
            chapter_id=chapter_id,
            page_id=page_id,
            batch_id=batch_id,
        )
        super().__init__(f"{code}: {message}")


class PptSourceContractV2(_StrictModel):
    schema_version: Literal["ppt_source_contract_v2"] = "ppt_source_contract_v2"
    course_id: str
    course_document_revision: str
    active_block_ids: list[str]
    active_block_digest: str
    teaching_plan_revision: str
    teaching_plan_digest: str
    knowledge_revision: str
    knowledge_digest: str
    coherence_revision: str
    coherence_digest: str
    template_id: str
    template_version: str
    template_digest: str
    story_policy_version: str = "slide_story_plan_v3"
    visual_policy_version: str = "slide_visual_plan_v2"
    locale: str
    source_digest: str


class SlideStoryPageV3(_StrictModel):
    page_id: str
    teaching_unit_id: str
    template_layout_id: str
    title: str = Field(max_length=90)
    summary: str = Field(default="", max_length=700)
    source_block_ids: list[str] = Field(min_length=1)
    page_ordinal: int = Field(ge=0)


class SlideStoryBatchV3(_StrictModel):
    batch_id: str
    chapter_id: str
    provider: str
    model: str
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    validation_status: Literal["passed", "failed"]
    failure_category: str = ""
    pages: list[SlideStoryPageV3] = Field(default_factory=list)


class AIProviderAttemptDiagnosticV1(_StrictModel):
    provider: str
    model: str
    attempt: int = Field(ge=1)
    status: str
    duration_ms: int = Field(default=0, ge=0)
    queue_wait_ms: int = Field(default=0, ge=0)
    physical_request_count: int = Field(default=1, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tokens_source: Literal["provider", "estimate", "unknown"] = "unknown"
    failure_kind: str = ""
    error_code: str = ""


class AIBatchDiagnosticV1(_StrictModel):
    schema_version: Literal["ai_batch_diagnostic_v1"] = "ai_batch_diagnostic_v1"
    kind: Literal["story", "visual"]
    batch_id: str
    chapter_id: str
    provider: str
    model: str
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    retry_count: int = Field(ge=0)
    physical_request_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tokens_source: Literal["provider", "estimate", "mixed", "unknown"] = "unknown"
    validation_status: Literal["passed", "failed", "degraded"]
    failure_category: str = ""
    attempt_records: list[AIProviderAttemptDiagnosticV1] = Field(default_factory=list)


class SlideStoryPlanV3(_StrictModel):
    schema_version: Literal["slide_story_plan_v3"] = "slide_story_plan_v3"
    source_document_revision: str
    template_digest: str
    batches: list[SlideStoryBatchV3] = Field(min_length=1)

    @computed_field
    @property
    def pages(self) -> list[SlideStoryPageV3]:
        return [page for batch in self.batches for page in batch.pages]


VisualDecisionKind = Literal[
    "text_native",
    "code",
    "formula",
    "table",
    "data",
    "diagram",
    "image",
    "experiment",
    "source_excerpt",
]


class SlideVisualDecisionV2(_StrictModel):
    page_id: str
    decision: VisualDecisionKind
    source_block_ids: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    source_asset_ids: list[str] = Field(default_factory=list)
    visual_payload: dict[str, Any] = Field(default_factory=dict)
    resolved_template_layout_id: str
    provider: str = ""
    model: str = ""
    duration_ms: int = Field(default=0, ge=0)
    attempts: int = Field(default=1, ge=1)
    degraded: bool = False
    degradation_reason: str = ""

    @model_validator(mode="after")
    def require_source_binding(self) -> SlideVisualDecisionV2:
        if not self.source_block_ids and not self.source_section_ids:
            raise ValueError("visual_source_binding_missing")
        return self


class SlideVisualPlanV2(_StrictModel):
    schema_version: Literal["slide_visual_plan_v2"] = "slide_visual_plan_v2"
    source_document_revision: str
    template_digest: str
    decisions: list[SlideVisualDecisionV2] = Field(min_length=1)


class SourceNoteBlockV2(_StrictModel):
    block_id: str
    block_revision: str
    full_text: str
    source_kind: str
    source_payload: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[str] = Field(default_factory=list)


class SlideSpeakerNotesV2(_StrictModel):
    schema_version: Literal["slide_speaker_notes_v2"] = "slide_speaker_notes_v2"
    source_document_revision: str
    teaching_unit_id: str
    source_blocks: list[SourceNoteBlockV2] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_source_binding(self) -> SlideSpeakerNotesV2:
        if not self.source_blocks and not self.source_section_ids:
            raise ValueError("speaker_note_source_binding_missing")
        return self


class SlideRegionV6(_StrictModel):
    region_id: str
    slot_id: str
    content_kind: str
    content: str
    source_block_ids: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    source_asset_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_source_binding(self) -> SlideRegionV6:
        if not self.source_block_ids and not self.source_section_ids:
            raise ValueError("region_source_binding_missing")
        return self


class SlidePageV6(_StrictModel):
    schema_version: Literal["slide_page_v6"] = "slide_page_v6"
    page_id: str
    page_ordinal: int = Field(ge=0)
    teaching_unit_id: str
    title: str
    title_max_lines: int = Field(default=1, ge=1, le=3)
    resolved_layout: str
    web_renderer_adapter: str
    pptx_renderer_adapter: str
    regions: list[SlideRegionV6] = Field(min_length=1)
    source_block_ids: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    artifact_kinds: list[str] = Field(default_factory=list)
    visual_decision: SlideVisualDecisionV2
    speaker_notes: SlideSpeakerNotesV2
    continuation_of_page_id: str = ""
    continuation_index: int = Field(default=1, ge=1)
    continuation_count: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def require_source_binding(self) -> SlidePageV6:
        if not self.source_block_ids and not self.source_section_ids:
            raise ValueError("page_source_binding_missing")
        return self


class SlideDeckV6Quality(_StrictModel):
    formal_block_visible_coverage: float = Field(ge=0, le=1)
    full_text_note_binding: float = Field(ge=0, le=1)
    source_artifact_visible_fidelity: float = Field(default=1.0, ge=0, le=1)
    source_prose_visible_fidelity: float = Field(default=1.0, ge=0, le=1)
    ordered_step_visible_fidelity: float = Field(default=1.0, ge=0, le=1)
    generated_ellipsis_free: bool = True
    source_order_preserved: bool
    template_contract_passed: bool
    subject_artifacts_passed: bool
    web_pptx_contract_shared: bool
    story_page_count: int = Field(default=0, ge=0)
    final_page_count: int = Field(default=0, ge=0)
    pagination_expansion_ratio: float = Field(default=1.0, ge=0)
    max_story_page_expansion: int = Field(default=1, ge=0)
    pagination_page_upper_bound: int = Field(default=0, ge=0)
    pagination_within_dynamic_bound: bool = True
    average_visible_chars_per_page: float = Field(default=0.0, ge=0)
    max_visible_chars_per_page: int = Field(default=0, ge=0)
    visible_to_speaker_notes_ratio: float = Field(default=0.0, ge=0)
    teacher_cue_free_page_ratio: float = Field(default=1.0, ge=0, le=1)
    distinct_page_title_ratio: float = Field(default=1.0, ge=0, le=1)
    render_review: dict[str, Any] = Field(default_factory=dict)
    blockers: list[V6Failure] = Field(default_factory=list)
    passed: bool = True

    @model_validator(mode="after")
    def derive_passed(self) -> SlideDeckV6Quality:
        self.passed = bool(
            self.formal_block_visible_coverage == 1.0
            and self.full_text_note_binding == 1.0
            and self.source_artifact_visible_fidelity == 1.0
            and self.source_prose_visible_fidelity == 1.0
            and self.ordered_step_visible_fidelity == 1.0
            and self.generated_ellipsis_free
            and self.source_order_preserved
            and self.template_contract_passed
            and self.subject_artifacts_passed
            and self.web_pptx_contract_shared
            and self.pagination_within_dynamic_bound
            and not self.blockers
        )
        return self


class SlideDeckV6(_StrictModel):
    schema_version: Literal["slide_deck_v6"] = "slide_deck_v6"
    course_id: str
    title: str
    theme: str
    source_document_revision: str
    template_id: str
    template_version: str
    template_digest: str
    template_theme_overrides: dict[str, str] = Field(default_factory=dict)
    status: V6Status
    pages: list[SlidePageV6] = Field(min_length=1)
    quality: SlideDeckV6Quality


PptManuscriptPageType = Literal[
    "cover",
    "agenda",
    "concept",
    "reasoning",
    "example",
    "practice",
    "comparison",
    "code",
    "formula",
    "table",
    "data",
    "diagram",
    "summary",
    "content",
]


class PptManuscriptPageV1(_StrictModel):
    """一页可审阅的 PPT 文书：拥有台上可见内容，不拥有新知识。"""

    page_id: str
    page_number: int = Field(ge=1)
    teaching_unit_id: str
    course_block_types: list[str] = Field(default_factory=list)
    page_type: PptManuscriptPageType
    title: str
    visible_copy: list[str] = Field(default_factory=list)
    layout_id: str
    composition_notes: str
    visual_kind: VisualDecisionKind
    source_script_block_ids: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    speaker_note_source_block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_source_binding(self) -> PptManuscriptPageV1:
        if not self.source_script_block_ids and not self.source_section_ids:
            raise ValueError("ppt_manuscript_source_binding_missing")
        return self


class PptManuscriptV1(_StrictModel):
    """讲稿与模板渲染之间的唯一逐页内容合同。"""

    schema_version: Literal["ppt_manuscript_v1"] = "ppt_manuscript_v1"
    manuscript_revision: str
    source_document_revision: str
    source_lesson_plan_revision_id: str = ""
    source_script_revision_id: str = ""
    template_id: str
    template_version: str
    template_digest: str
    page_count: int = Field(ge=1)
    pages: list[PptManuscriptPageV1] = Field(min_length=1)
    quality_status: Literal["passed"] = "passed"


def _ppt_manuscript_page_type(page: SlidePageV6) -> PptManuscriptPageType:
    layout = page.resolved_layout.casefold()
    roles = {
        note.source_kind.casefold()
        for note in page.speaker_notes.source_blocks
        if note.source_kind
    }
    visual = page.visual_decision.decision
    if "cover" in layout:
        return "cover"
    if "agenda" in layout:
        return "agenda"
    if visual in {"code", "formula", "table", "data", "diagram"}:
        return visual
    if "comparison" in layout or "compare" in layout or "counterexample" in roles:
        return "comparison"
    if roles.intersection({"summary", "transfer"}) or "recap" in layout:
        return "summary"
    if roles.intersection({"activity", "checkpoint", "feedback", "remediation"}):
        return "practice"
    if roles.intersection({"example", "application"}):
        return "example"
    if "reasoning" in roles:
        return "reasoning"
    if "concept" in roles:
        return "concept"
    return "content"


def compile_ppt_manuscript_v1(
    deck: SlideDeckV6,
    *,
    source_lesson_plan_revision_id: str = "",
    source_script_revision_id: str = "",
) -> PptManuscriptV1:
    """把已通过内容门的页面规格固化为 PPT 文书。

    此投影只整理已绑定的讲稿内容、页型、版式和构图决策，
    不会在渲染前再生成、摘要或改写知识。
    """

    pages: list[PptManuscriptPageV1] = []
    for page in sorted(deck.pages, key=lambda item: item.page_ordinal):
        visible_copy = list(dict.fromkeys(
            region.content.strip()
            for region in page.regions
            if region.content_kind != "notes" and region.content.strip()
        ))
        course_block_types = list(dict.fromkeys(
            note.source_kind
            for note in page.speaker_notes.source_blocks
            if note.source_kind
        ))
        region_order = [
            region.slot_id
            for region in page.regions
            if region.content_kind != "notes"
        ]
        pages.append(PptManuscriptPageV1(
            page_id=page.page_id,
            page_number=page.page_ordinal + 1,
            teaching_unit_id=page.teaching_unit_id,
            course_block_types=course_block_types,
            page_type=_ppt_manuscript_page_type(page),
            title=page.title,
            visible_copy=visible_copy,
            layout_id=page.resolved_layout,
            composition_notes=(
                f"使用 {page.resolved_layout} 版式，"
                f"按 {' → '.join(region_order) or '默认区域'} 排列，"
                f"视觉类型为 {page.visual_decision.decision}。"
            ),
            visual_kind=page.visual_decision.decision,
            source_script_block_ids=list(page.source_block_ids),
            source_section_ids=list(page.source_section_ids),
            speaker_note_source_block_ids=[
                note.block_id for note in page.speaker_notes.source_blocks
            ],
        ))
    payload = {
        "source_document_revision": deck.source_document_revision,
        "source_lesson_plan_revision_id": source_lesson_plan_revision_id,
        "source_script_revision_id": source_script_revision_id,
        "template_id": deck.template_id,
        "template_version": deck.template_version,
        "template_digest": deck.template_digest,
        "page_count": len(pages),
        "pages": [page.model_dump(mode="json") for page in pages],
        "quality_status": "passed",
    }
    return PptManuscriptV1(
        manuscript_revision=stable_hash(payload, prefix="pptman_"),
        **payload,
    )


def _formal_blocks(document: CourseDocument) -> list[CourseBlock]:
    section_order = {section.section_id: index for index, section in enumerate(sorted(document.sections, key=lambda item: (item.position, item.level)))}
    return sorted(
        (block for block in document.blocks if block.status == "final"),
        key=lambda block: (section_order.get(block.section_id, len(section_order)), block.position, block.block_id),
    )


def compile_shadow_chapter_document(
    document: CourseDocument,
    chapter_id: str,
) -> CourseDocument:
    """Freeze one selected section subtree without mutating the online course."""

    known_sections = {section.section_id for section in document.sections}
    if chapter_id not in known_sections:
        raise V6BuildError(
            stage="source",
            code="shadow_chapter_not_found",
            message="The requested shadow chapter is not present in the frozen course",
            chapter_id=chapter_id,
        )
    selected = {chapter_id}
    changed = True
    while changed:
        before = len(selected)
        selected.update(
            section.section_id
            for section in document.sections
            if section.parent_section_id in selected
        )
        changed = len(selected) != before
    payload = document.model_dump(mode="json")
    payload["document_revision"] = ""
    payload["sections"] = [
        section.model_dump(mode="json")
        for section in document.sections
        if section.section_id in selected
    ]
    payload["blocks"] = [
        block.model_dump(mode="json")
        for block in document.blocks
        if block.section_id in selected
    ]
    return refresh_document_revision(CourseDocument.model_validate(payload))


def compile_ppt_source_contract_v2(
    document: CourseDocument,
    *,
    teaching_plan: dict[str, Any],
    knowledge_snapshot: dict[str, Any],
    coherence_contract: dict[str, Any],
    template_contract: TemplateLayoutPackContractV1,
    locale: str,
) -> PptSourceContractV2:
    blocks = _formal_blocks(document)
    block_payload = [block.model_dump(mode="json") for block in blocks]
    teaching_plan_revision = str(
        teaching_plan.get("revision_id")
        or teaching_plan.get("revision")
        or teaching_plan.get("version")
        or ""
    )
    knowledge_revision = str(
        knowledge_snapshot.get("revision_id")
        or knowledge_snapshot.get("revision")
        or knowledge_snapshot.get("version")
        or ""
    )
    coherence_revision = str(
        coherence_contract.get("revision_id")
        or coherence_contract.get("revision")
        or coherence_contract.get("version")
        or ""
    )
    values = {
        "course_id": document.course_id,
        "document_revision": document.document_revision,
        "blocks": block_payload,
        "teaching_plan": teaching_plan,
        "knowledge": knowledge_snapshot,
        "coherence": coherence_contract,
        "template_digest": template_contract.template_digest,
        "locale": locale,
    }
    return PptSourceContractV2(
        course_id=document.course_id,
        course_document_revision=document.document_revision,
        active_block_ids=[block.block_id for block in blocks],
        active_block_digest=stable_hash(block_payload, prefix="blocks_"),
        teaching_plan_revision=teaching_plan_revision,
        teaching_plan_digest=stable_hash(teaching_plan, prefix="plan_"),
        knowledge_revision=knowledge_revision,
        knowledge_digest=stable_hash(knowledge_snapshot, prefix="knowledge_"),
        coherence_revision=coherence_revision,
        coherence_digest=stable_hash(coherence_contract, prefix="coherence_"),
        template_id=template_contract.template_id,
        template_version=template_contract.template_version,
        template_digest=template_contract.template_digest,
        locale=locale,
        source_digest=stable_hash(values, prefix="pptsrc_"),
    )


def build_signature_v6(
    *,
    document: CourseDocument,
    course_data: dict[str, Any],
    mode: str,
    theme: str,
    template_contract: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    """Build the cache identity from the same frozen inputs consumed by V6."""

    source = compile_ppt_source_contract_v2(
        document,
        teaching_plan=dict(course_data.get("course_teaching_plan") or {}),
        knowledge_snapshot=dict(course_data.get("course_knowledge_base") or {}),
        coherence_contract=dict(course_data.get("course_coherence_contract") or {}),
        template_contract=template_contract,
        locale=str(course_data.get("language") or course_data.get("locale") or "zh-CN"),
    )
    fields = {
        "source_digest": source.source_digest,
        "course_document_revision": source.course_document_revision,
        "template_id": source.template_id,
        "template_version": source.template_version,
        "template_digest": source.template_digest,
        "story_policy_version": source.story_policy_version,
        "visual_policy_version": source.visual_policy_version,
        "mode": mode,
        "theme": theme,
        "compiler_version": SLIDE_DECK_V6_COMPILER_VERSION,
    }
    return {**fields, "signature": stable_hash(fields, prefix="slidebuildv6_")}


_PROTECTED_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
_PROTECTED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.]{2,}\b")
_CJK_SPAN_RE = re.compile(r"[\u3400-\u9fff]{2,}")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_GENERIC_GROUNDING_TERMS = {
    "一个", "可以", "需要", "必须", "通过", "采用", "使用", "完成",
    "进行", "形成", "当前", "相关", "内容", "方法", "过程", "结果",
    "the", "and", "for", "with", "from", "into", "then", "before", "after",
    "this", "that", "these", "those", "using", "use", "used", "through",
}


def _protected_tokens(text: str) -> set[str]:
    return {
        *(match.group(0).lower() for match in _PROTECTED_NUMBER_RE.finditer(text)),
        *(
            variant
            for match in _PROTECTED_IDENTIFIER_RE.finditer(text)
            for variant in _identifier_token_variants(match.group(0))
        ),
    }


def _identifier_token_variants(value: str) -> set[str]:
    """Keep dotted identifiers strict while accepting a source-backed prefix.

    Course prose commonly introduces a file or qualified symbol such as
    ``FieldAuditRunner.py`` or ``System.Collections.Generic`` and later refers
    to ``FieldAuditRunner`` or ``System.Collections``. Those are not new facts;
    they are exact prefixes of the frozen identifier. Suffixes and unrelated
    identifiers remain unsupported.
    """

    normalized = str(value or "").casefold()
    variants = {normalized}
    parts = normalized.split(".")
    for index in range(1, len(parts)):
        prefix = ".".join(parts[:index])
        if _PROTECTED_IDENTIFIER_RE.fullmatch(prefix):
            variants.add(prefix)
    return variants


def _title_protected_tokens(text: str) -> set[str]:
    """Keep exact-match protection for identifiers, without treating prose as code."""

    protected = {
        match.group(0).lower()
        for match in _PROTECTED_NUMBER_RE.finditer(text)
    }
    for match in _PROTECTED_IDENTIFIER_RE.finditer(text):
        token = match.group(0)
        if (
            any(character.isdigit() for character in token)
            or any(character in "_." for character in token)
            or (token.isupper() and len(token) > 1)
            or any(character.isupper() for character in token[1:])
        ):
            protected.update(_identifier_token_variants(token))
    return protected


def _grounding_terms(text: str) -> set[str]:
    terms = {
        match.group(0).casefold()
        for match in _LATIN_WORD_RE.finditer(text)
    }
    for match in _CJK_SPAN_RE.finditer(text):
        span = match.group(0)
        terms.update(
            span[index:index + 2]
            for index in range(max(0, len(span) - 1))
        )
    return {term for term in terms if term not in _GENERIC_GROUNDING_TERMS}


def _semantic_grounding_ratio(claim: str, source: str) -> float:
    claim_terms = _grounding_terms(claim)
    if not claim_terms:
        return 1.0
    return len(claim_terms.intersection(_grounding_terms(source))) / len(claim_terms)


_DANGLING_TITLE_END_RE = re.compile(
    r"(?:[：:；;，,、/\\]|[（(《〈【\[]|"
    r"(?:与|和|及|或|以及|并|并且|同时|为|对|从|向|到|的)|"
    r"\b(?:and|or|to|of|with|versus|vs\.?)\b)\s*$",
    re.IGNORECASE,
)


def _title_is_incomplete(value: str) -> bool:
    title = " ".join(str(value or "").split()).strip()
    return bool(title and _DANGLING_TITLE_END_RE.search(title))


def _title_semantic_source_text(value: str) -> str:
    """Remove structural heading labels while retaining their specific subject."""

    lines: list[str] = []
    for raw_line in str(value or "").splitlines():
        clean = _visible_prose_text(raw_line).strip()
        if not clean:
            continue
        structural_heading = bool(
            re.match(r"^\s*#{1,6}\s+", raw_line)
            or re.fullmatch(r"\s*(?:\*\*|__).*?(?:\*\*|__)\s*", raw_line)
        )
        if structural_heading:
            parts = re.split(r"[：:]", clean, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                clean = parts[1].strip()
        lines.append(clean)
    return "\n".join(lines)


def _unit_source_text_for_blocks(
    unit: CoursePresentationUnitV1,
    block_ids: set[str] | list[str],
) -> str:
    selected_ids = [str(block_id) for block_id in block_ids]
    texts = [
        str(unit.primary_block_texts.get(block_id) or "").strip()
        for block_id in selected_ids
        if str(unit.primary_block_texts.get(block_id) or "").strip()
    ]
    # A lesson/chapter opening is allowed to use its formal section title. The
    # title belongs to the frozen course source even though it is not duplicated
    # inside the objective block text.
    if unit.section_title and any(
        unit.primary_block_roles.get(block_id) == "objective"
        for block_id in selected_ids
    ):
        texts.insert(0, unit.section_title)
    return "\n\n".join(texts) or unit.source_text


def _unit_map(graph: CoursePresentationGraphV1) -> dict[str, CoursePresentationUnitV1]:
    return {unit.teaching_unit_id: unit for unit in graph.units}


def graph_page_source_blocks(
    unit: CoursePresentationUnitV1,
    source_block_ids: list[str],
) -> list[CourseBlock]:
    """Rehydrate the frozen block facts needed by the template allocator."""

    result: list[CourseBlock] = []
    for index, block_id in enumerate(source_block_ids):
        source_text = unit.primary_block_texts.get(block_id, "")
        presentation_text = unit.primary_block_presentation_texts.get(
            block_id,
            source_text,
        )
        payload: dict[str, Any] = {
            "text": source_text,
            "_v6_artifact_kinds": unit.primary_block_artifacts.get(
                block_id,
                [],
            ),
        }
        if presentation_text != source_text:
            payload["slide_visible_text"] = presentation_text
        result.append(CourseBlock(
            block_id=block_id,
            section_id=unit.section_id,
            position=index,
            kind=unit.primary_block_kinds.get(block_id, "rich_text"),
            role=unit.primary_block_roles.get(block_id, "concept"),
            payload=payload,
            asset_refs=list(unit.primary_block_asset_refs.get(block_id, [])),
        ))
    return result


def validate_slide_story_plan_v3(
    plan: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> None:
    if plan.source_document_revision != graph.source_document_revision:
        raise V6BuildError(stage="story", code="story_source_revision_mismatch", message="Story source revision differs from the frozen graph")
    if plan.template_digest != template.template_digest:
        raise V6BuildError(stage="story", code="story_template_revision_mismatch", message="Story template digest differs from the frozen template")
    failed = next((batch for batch in plan.batches if batch.validation_status != "passed"), None)
    if failed:
        raise V6BuildError(
            stage="story",
            code=failed.failure_category or "story_ai_batch_failed",
            message="A required story AI batch failed validation",
            retryable=True,
            chapter_id=failed.chapter_id,
            batch_id=failed.batch_id,
        )
    units = _unit_map(graph)
    known_blocks = set(graph.formal_block_ids)
    observed_blocks: list[str] = []
    previous_unit_ordinal = -1
    page_count_by_unit: Counter[str] = Counter()
    title_owners: dict[str, str] = {}
    page_id_owners: set[str] = set()
    for page in sorted(plan.pages, key=lambda item: item.page_ordinal):
        if not page.page_id.strip():
            raise V6BuildError(
                stage="story",
                code="story_page_id_missing",
                message="Every V6 page requires a stable identity",
            )
        if page.page_id in page_id_owners:
            raise V6BuildError(
                stage="story",
                code="story_duplicate_page_id",
                message="Every V6 page identity must be globally unique",
                page_id=page.page_id,
            )
        page_id_owners.add(page.page_id)
        unit = units.get(page.teaching_unit_id)
        if unit is None:
            raise V6BuildError(stage="story", code="story_unknown_teaching_unit", message="Story references an unknown teaching unit", page_id=page.page_id)
        unknown = [block_id for block_id in page.source_block_ids if block_id not in known_blocks]
        if unknown:
            raise V6BuildError(stage="story", code="story_unknown_source_id", message=f"Unknown source block IDs: {', '.join(unknown)}", page_id=page.page_id)
        if any(block_id not in unit.primary_block_ids for block_id in page.source_block_ids):
            raise V6BuildError(stage="story", code="story_cross_unit_source", message="A page references source owned by another teaching unit", page_id=page.page_id)
        layout = template.get_layout(page.template_layout_id)
        if layout is None:
            raise V6BuildError(stage="template", code="template_layout_unavailable", message=f"Unknown V6 template layout: {page.template_layout_id}", page_id=page.page_id)
        page_intent = page_teaching_intent(unit, page.source_block_ids)
        required_artifacts = page_artifact_kinds(unit, page.source_block_ids)
        if page_intent not in layout.teaching_intents:
            raise V6BuildError(stage="template", code="template_layout_intent_mismatch", message="Template layout does not support the teaching intent", page_id=page.page_id)
        if required_artifacts and not required_artifacts.issubset(
            set(layout.artifact_kinds)
        ):
            raise V6BuildError(
                stage="template",
                code="template_layout_artifact_mismatch",
                message="Template layout does not express the page's source artifact",
                page_id=page.page_id,
            )
        required_slot_kinds = source_required_slot_kinds(
            graph_page_source_blocks(unit, page.source_block_ids)
        )
        if not _layout_supports_required_slot_kinds(
            layout,
            required_slot_kinds,
        ):
            raise V6BuildError(
                stage="template",
                code="template_layout_semantic_slot_mismatch",
                message=(
                    "Template layout cannot preserve a required source semantic "
                    "structure"
                ),
                page_id=page.page_id,
            )
        title_slot = next(
            (slot for slot in layout.slots if slot.slot_kind == "title"),
            None,
        )
        if not page.title.strip():
            raise V6BuildError(
                stage="story",
                code="story_title_missing",
                message="Every V6 page requires a visible source-grounded title",
                page_id=page.page_id,
            )
        if title_slot and not _title_fits_slot(page.title, title_slot):
            raise V6BuildError(
                stage="story",
                code="story_title_capacity_exceeded",
                message="Story title exceeds the selected template title capacity",
                page_id=page.page_id,
            )
        if _title_is_incomplete(page.title):
            raise V6BuildError(
                stage="story",
                code="story_title_incomplete",
                message="Visible page title ends with an incomplete connector or delimiter",
                page_id=page.page_id,
            )
        summary_body_slots = [
            slot for slot in layout.slots if slot.slot_kind == "body"
        ]
        if page.summary and (
            _presentation_summary_text(page.summary) != page.summary.strip()
            or _looks_like_markdown_table(page.summary)
        ):
            raise V6BuildError(
                stage="story",
                code="story_summary_markdown_invalid",
                message="Story summary must be presentation-ready text without Markdown",
                page_id=page.page_id,
            )
        if page.summary and len(summary_body_slots) == 1:
            summary_slot = summary_body_slots[0]
            summary_capacity = int(summary_slot.max_chars or 0)
            if summary_capacity and len(page.summary) > summary_capacity:
                raise V6BuildError(
                    stage="story",
                    code="story_summary_capacity_exceeded",
                    message="Story summary exceeds the selected template support slot",
                    page_id=page.page_id,
                )
            source_length = len(_presentation_summary_text(
                _unit_source_text_for_blocks(unit, page.source_block_ids)
            ))
            summary_min_chars = min(
                int(getattr(summary_slot, "min_chars", 0) or 0),
                source_length,
            )
            if summary_min_chars and len(_presentation_summary_text(page.summary)) < summary_min_chars:
                raise V6BuildError(
                    stage="story",
                    code="story_page_underfilled",
                    message=(
                        "Story summary underfills the selected template body despite "
                        "sufficient frozen source content"
                    ),
                    page_id=page.page_id,
                )
        validate_story_template_text_slots(
            page_id=page.page_id,
            template=template,
            layout=layout,
            source_blocks=graph_page_source_blocks(unit, page.source_block_ids),
            story_summary=page.summary,
        )
        if unit.source_ordinal < previous_unit_ordinal:
            raise V6BuildError(stage="story", code="story_dependency_order_invalid", message="Story reverses course teaching-unit order", page_id=page.page_id)
        previous_unit_ordinal = unit.source_ordinal
        page_count_by_unit[unit.teaching_unit_id] += 1
        normalized_title = re.sub(r"\s+", "", page.title).casefold()
        if normalized_title in title_owners:
            raise V6BuildError(
                stage="story",
                code="duplicate_slide_title",
                message="Each V6 page must have a distinct teaching title",
                page_id=page.page_id,
            )
        title_owners[normalized_title] = page.page_id
        page_source_text = _unit_source_text_for_blocks(
            unit,
            page.source_block_ids,
        )
        if not _ellipsis_maps_to_frozen_source(page.title, page_source_text):
            raise V6BuildError(
                stage="story",
                code="story_unsupported_title",
                message=(
                    "A title ellipsis is not traceable to the same frozen-source "
                    "context"
                ),
                page_id=page.page_id,
            )
        unsupported_title_tokens = (
            _title_protected_tokens(page.title)
            - _title_protected_tokens(page_source_text)
        )
        if unsupported_title_tokens or _semantic_grounding_ratio(page.title, page_source_text) < 0.12:
            raise V6BuildError(
                stage="story",
                code="story_unsupported_title",
                message="Visible page title is not traceable to its frozen source unit",
                page_id=page.page_id,
            )
        if _semantic_grounding_ratio(
            page.title,
            _title_semantic_source_text(page_source_text),
        ) < 0.25:
            raise V6BuildError(
                stage="story",
                code="story_title_lacks_specificity",
                message=(
                    "Visible page title repeats a structural label instead of the "
                    "bound page's teaching subject"
                ),
                page_id=page.page_id,
            )
        unsupported = _protected_tokens(page.summary) - _protected_tokens(unit.source_text)
        if unsupported:
            raise V6BuildError(stage="story", code="story_unsupported_fact", message=f"Unsupported factual tokens: {', '.join(sorted(unsupported))}", page_id=page.page_id)
        if not _ellipsis_maps_to_frozen_source(page.summary, page_source_text):
            raise V6BuildError(
                stage="story",
                code="story_unsupported_fact",
                message=(
                    "A summary ellipsis is not traceable to the same frozen-source "
                    "context"
                ),
                page_id=page.page_id,
            )
        if page.summary and _semantic_grounding_ratio(page.summary, unit.source_text) < 0.12:
            raise V6BuildError(
                stage="story",
                code="story_unsupported_semantic_claim",
                message="Story summary has insufficient lexical grounding in its frozen source unit",
                page_id=page.page_id,
            )
        observed_blocks.extend(page.source_block_ids)
    for unit in graph.units:
        maximum_pages = story_page_count_range(unit, template)[1]
        if page_count_by_unit[unit.teaching_unit_id] > maximum_pages:
            failed_page = next(
                page
                for page in reversed(sorted(
                    plan.pages,
                    key=lambda item: item.page_ordinal,
                ))
                if page.teaching_unit_id == unit.teaching_unit_id
            )
            raise V6BuildError(
                stage="story",
                code="teaching_unit_page_limit_exceeded",
                message=(
                    "A teaching unit exceeds its template-safe page budget "
                    f"of {maximum_pages}"
                ),
                page_id=failed_page.page_id,
            )
    missing = [block_id for block_id in graph.formal_block_ids if block_id not in observed_blocks]
    if missing:
        raise V6BuildError(stage="story", code="story_course_block_coverage_incomplete", message=f"Story omitted formal blocks: {', '.join(missing)}")
    duplicates = [block_id for block_id, count in Counter(observed_blocks).items() if count > 1]
    if duplicates:
        raise V6BuildError(stage="story", code="story_duplicate_primary_block", message=f"Story gives multiple primary pages to blocks: {', '.join(duplicates)}")


_REQUIRED_VISUAL_DECISION: dict[str, set[str]] = {
    "code": {"code"},
    "formula": {"formula"},
    "table": {"table", "data"},
    "data": {"data", "table"},
    "experiment": {"experiment", "image", "data"},
    "source_excerpt": {"source_excerpt", "image"},
}


def validate_slide_visual_plan_v2(
    plan: SlideVisualPlanV2,
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> Literal["v6_ready", "v6_needs_manual_edit"]:
    if plan.source_document_revision != graph.source_document_revision or plan.template_digest != template.template_digest:
        raise V6BuildError(stage="visual", code="visual_source_contract_mismatch", message="Visual plan does not match the frozen source/template")
    story_pages = {page.page_id: page for page in story.pages}
    decision_page_ids = [decision.page_id for decision in plan.decisions]
    unknown_page_ids = [
        page_id for page_id in decision_page_ids if page_id not in story_pages
    ]
    if unknown_page_ids:
        raise V6BuildError(
            stage="visual",
            code="visual_page_unknown",
            message="Visual plan contains a decision outside the frozen Story scope",
            page_id=unknown_page_ids[0],
        )
    duplicate_page_ids = [
        page_id
        for page_id, count in Counter(decision_page_ids).items()
        if count > 1
    ]
    if duplicate_page_ids:
        raise V6BuildError(
            stage="visual",
            code="visual_page_duplicate",
            message="Visual plan must contain exactly one decision per Story page",
            page_id=duplicate_page_ids[0],
        )
    decisions = {decision.page_id: decision for decision in plan.decisions}
    missing_page_ids = [
        page.page_id for page in story.pages if page.page_id not in decisions
    ]
    if missing_page_ids:
        raise V6BuildError(
            stage="visual",
            code="visual_page_coverage_incomplete",
            message="Visual plan is missing a decision for a frozen Story page",
            page_id=missing_page_ids[0],
        )
    units = _unit_map(graph)
    degraded = False
    for page_id, page in story_pages.items():
        decision = decisions[page_id]
        unit = units[page.teaching_unit_id]
        if set(decision.source_block_ids) != set(page.source_block_ids):
            raise V6BuildError(
                stage="visual",
                code="visual_source_binding_mismatch",
                message="Visual decision must bind exactly the story page source blocks",
                page_id=page_id,
            )
        layout = template.get_layout(decision.resolved_template_layout_id)
        if layout is None:
            raise V6BuildError(stage="visual", code="template_layout_unavailable", message="Visual plan selected an unknown template layout", page_id=page_id)
        source_blocks = graph_page_source_blocks(
            unit,
            page.source_block_ids,
        )
        validate_layout_source_satisfiability(
            page_id=page_id,
            template=template,
            layout=layout,
            source_blocks=source_blocks,
            story_summary=page.summary,
        )
        story_layout = template.get_layout(page.template_layout_id)
        safe_degraded_rebind = bool(
            story_layout is not None
            and decision.degraded
            and decision.decision == "text_native"
            and layout.layout_slug
            in set(story_layout.safe_continuation_layout_slugs)
            and page_teaching_intent(unit, page.source_block_ids)
            in layout.teaching_intents
            and not any(
                slot.required
                and slot.slot_kind in {"code", "formula", "table", "visual"}
                for slot in layout.slots
            )
            and not page_artifact_kinds(unit, page.source_block_ids)
            and _layout_supports_required_slot_kinds(
                layout,
                source_required_slot_kinds(
                    graph_page_source_blocks(unit, page.source_block_ids)
                ),
            )
        )
        if (
            decision.resolved_template_layout_id != page.template_layout_id
            and not safe_degraded_rebind
        ):
            raise V6BuildError(
                stage="visual",
                code="visual_layout_binding_mismatch",
                message=(
                    "Visual decision must retain the story page template layout "
                    "unless an optional visual safely degrades to an approved prose continuation"
                ),
                page_id=page_id,
            )
        unknown_assets = set(decision.source_asset_ids) - set(unit.source_asset_refs)
        if unknown_assets:
            raise V6BuildError(
                stage="visual",
                code="visual_unknown_source_asset",
                message="Visual plan references an asset outside the frozen teaching unit",
                page_id=page_id,
            )
        if decision.decision in {"image", "experiment"} and not decision.source_asset_ids:
            raise V6BuildError(
                stage="visual",
                code="visual_source_asset_missing",
                message="Image and experiment visuals require a frozen source asset reference",
                page_id=page_id,
            )
        if decision.decision == "diagram":
            nodes = decision.visual_payload.get("nodes") or []
            edges = decision.visual_payload.get("edges") or []
            if not isinstance(nodes, list) or not isinstance(edges, list) or len(nodes) < 2 or not edges:
                raise V6BuildError(
                    stage="visual",
                    code="visual_diagram_payload_missing",
                    message="A diagram decision requires at least two source-bound nodes and one edge",
                    page_id=page_id,
                )
            if len(nodes) > 6 or len(edges) > 10:
                raise V6BuildError(
                    stage="visual",
                    code="visual_diagram_capacity_exceeded",
                    message="Diagram nodes or edges exceed the template-safe capacity",
                    page_id=page_id,
                )
            node_ids = {str(node.get("node_id") or "") for node in nodes if isinstance(node, dict)}
            if "" in node_ids or len(node_ids) != len(nodes):
                raise V6BuildError(
                    stage="visual",
                    code="visual_diagram_node_invalid",
                    message="Diagram node IDs must be non-empty and unique",
                    page_id=page_id,
                )
            if layout.layout_slug == "evidence-diagram":
                diagram_metrics = diagram_node_layout_metrics(
                    [str(node.get("label") or "").strip() for node in nodes],
                    direction=str(
                        decision.visual_payload.get("direction") or "vertical"
                    ),
                )
                if not diagram_metrics["fits"]:
                    raise V6BuildError(
                        stage="visual",
                        code="visual_diagram_capacity_exceeded",
                        message=(
                            "Complete diagram labels exceed the published node geometry"
                        ),
                        page_id=page_id,
                    )
            for node in nodes:
                if not isinstance(node, dict):
                    raise V6BuildError(stage="visual", code="visual_diagram_node_invalid", message="Diagram node must be an object", page_id=page_id)
                label = str(node.get("label") or "").strip()
                node_sources = set(node.get("source_block_ids") or [])
                if not label or not node_sources or not node_sources.issubset(set(page.source_block_ids)):
                    raise V6BuildError(stage="visual", code="visual_diagram_node_unbound", message="Every diagram node needs a page source binding", page_id=page_id)
                node_source_text = _unit_source_text_for_blocks(unit, node_sources)
                if (
                    _title_protected_tokens(label) - _protected_tokens(node_source_text)
                    or _semantic_grounding_ratio(label, node_source_text) < 0.12
                    or not _ellipsis_maps_to_frozen_source(label, node_source_text)
                ):
                    raise V6BuildError(
                        stage="visual",
                        code="visual_diagram_label_unsupported",
                        message="Diagram node label is not grounded in its bound source blocks",
                        page_id=page_id,
                        node_id=str(node.get("node_id") or ""),
                    )
            if any(
                not isinstance(edge, dict)
                or str(edge.get("source") or "") not in node_ids
                or str(edge.get("target") or "") not in node_ids
                for edge in edges
            ):
                raise V6BuildError(
                    stage="visual",
                    code="visual_diagram_edge_invalid",
                    message="Diagram edges must connect declared source-bound nodes",
                    page_id=page_id,
                )
        for artifact in page_artifact_kinds(unit, page.source_block_ids):
            allowed = _REQUIRED_VISUAL_DECISION.get(artifact)
            if allowed and decision.decision not in allowed:
                raise V6BuildError(
                    stage="visual",
                    code="required_subject_representation_missing",
                    message=f"Required {artifact} representation was replaced by {decision.decision}",
                    page_id=page_id,
                )
        requires_artifact_slot = any(
            slot.required and slot.slot_kind in {"code", "formula", "table", "visual"}
            for slot in layout.slots
        )
        if (
            requires_artifact_slot
            and layout.artifact_kinds
            and decision.decision not in set(layout.artifact_kinds)
        ):
            raise V6BuildError(stage="visual", code="visual_layout_artifact_mismatch", message="Visual decision does not match the template artifact contract", page_id=page_id)
        if decision.degraded:
            if not decision.degradation_reason:
                raise V6BuildError(stage="visual", code="visual_degradation_reason_missing", message="A degraded page must explain the degradation", page_id=page_id)
            degraded = True
    return "v6_needs_manual_edit" if degraded else "v6_ready"


def _complete_sentence_excerpt(text: str, capacity: int) -> str:
    normalized = " ".join(text.split())
    if capacity <= 0:
        return ""
    if len(normalized) <= capacity:
        return normalized
    numbered_marker = "\u0000V6_NUMBER_DOT\u0000"
    protected = re.sub(
        r"(^|\s)(\d{1,2})\.\s+",
        lambda match: f"{match.group(1)}{match.group(2)}{numbered_marker} ",
        normalized,
    )
    sentences = [
        sentence.replace(numbered_marker, ".")
        for sentence in re.split(
            r"(?<=[。！？])\s*|(?<=[.!?])(?=\s|$)\s*",
            protected,
        )
    ]
    result = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{result}{sentence}" if not result else f"{result} {sentence}"
        if len(candidate) > capacity:
            break
        result = candidate
    if result:
        return result
    if capacity == 1:
        return normalized[:1]
    excerpt_end = min(len(normalized), capacity - 1)
    protected_spans = [
        match.span()
        for pattern in (_PROTECTED_NUMBER_RE, _PROTECTED_IDENTIFIER_RE)
        for match in pattern.finditer(normalized)
    ]
    containing_span = next(
        (
            (start, end)
            for start, end in protected_spans
            if start < excerpt_end < end
        ),
        None,
    )
    if containing_span is not None:
        excerpt_end = containing_span[0]
    excerpt = normalized[:excerpt_end].rstrip("，。！？,;: ")
    for opening, closing in (("(", ")"), ("（", "）"), ("[", "]"), ("【", "】"), ("{", "}")):
        if excerpt.rfind(opening) > excerpt.rfind(closing):
            excerpt = excerpt[:excerpt.rfind(opening)].rstrip("，。！？,;: ")
    return f"{excerpt}…"


def _semantic_prose_excerpt(text: str, capacity: int) -> str:
    """Keep source paragraph/list boundaries while selecting a safe excerpt."""

    visible = _visible_prose_text(text)
    groups = [
        "\n".join(line.rstrip() for line in group.splitlines()).strip()
        for group in re.split(r"\n\s*\n", visible)
        if group.strip()
    ]
    if not groups or capacity <= 0:
        return ""
    complete = "\n\n".join(groups)
    if len(complete) <= capacity:
        return complete
    selected: list[str] = []
    for group in groups:
        candidate = "\n\n".join([*selected, group])
        if len(candidate) > capacity:
            break
        selected.append(group)
    if selected:
        return "\n\n".join(selected)
    return _complete_sentence_excerpt(groups[0], capacity)


def _visible_prose_text(value: str) -> str:
    """Compile source Markdown into audience-facing text without changing facts."""

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?m)^\s*(?:`{3,}|~{3,})[^\n]*$",
        "",
        text,
    )
    text = re.sub(r"!\[([^]]*)]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?<!\\)(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\\)(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*_]\s*){3,}$", "", text)

    compiled_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            stripped.count("|") >= 2
            and re.fullmatch(r"\|?[|:\-\s]+\|?", stripped)
            and "-" in stripped
        ):
            continue
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            cells = [
                cell.strip().replace(r"\|", "|")
                for cell in re.split(r"(?<!\\)\|", stripped.strip("|"))
                if cell.strip()
            ]
            compiled_lines.append(" ".join(cells))
            continue
        compiled_lines.append(line)
    text = "\n".join(compiled_lines)
    # Strip presentation HTML, not arbitrary angle-bracketed identifiers.
    # Treating every XML-looking token as markup corrupts source expressions
    # such as List<Action<CollisionListener>> and templated C++ types.
    audience_html_tags = (
        "a|article|aside|b|blockquote|body|br|caption|code|dd|div|dl|dt|em|"
        "figcaption|figure|footer|h[1-6]|head|header|hr|html|i|img|li|main|"
        "mark|ol|p|pre|section|small|span|strong|sub|sup|table|tbody|td|tfoot|"
        "th|thead|tr|u|ul"
    )
    text = re.sub(
        rf"</?(?:{audience_html_tags})(?:\s[^<>]*)?/?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.replace(r"\*", "*").replace(r"\_", "_").strip()


def _presentation_summary_text(value: str) -> str:
    """Compile source markup into one presentation-ready summary contract."""

    text = _visible_prose_text(value)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"(?m)^\s*[-+*]\s+(?:\[[ xX]\]\s+)?", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    return text.strip()


def _canonical_visible_semantic_text(value: str) -> str:
    """Normalize visible prose for exact source-containment decisions."""

    text = _presentation_summary_text(value)
    text = re.sub(r"(?m)^\s*(?:>\s*)+", "", text)
    text = text.replace("*", "")
    return re.sub(r"\s+", "", text)


def _looks_like_markdown_table(value: str) -> bool:
    """Return true when prose is actually a Markdown table serialization."""

    table_lines = [
        line.strip()
        for line in str(value or "").splitlines()
        if line.strip().startswith("|")
        and line.strip().endswith("|")
        and line.count("|") >= 3
    ]
    if len(table_lines) < 2:
        return False
    return any(
        re.fullmatch(r"[|:\-\s]+", line) and "-" in line
        for line in table_lines
    )


def _display_excerpt(value: str, display_units: int) -> str:
    """Return a source-only excerpt bounded by rendered-width units."""

    clean = " ".join(_visible_prose_text(value).split())
    if display_units <= 0 or _display_width_units(clean) <= display_units:
        return clean
    preferred = ""
    for segment in re.split(r"(?<=[。！？.!?；;])\s*", clean):
        candidate = segment if not preferred else f"{preferred} {segment}"
        if _display_width_units(candidate) > display_units:
            break
        preferred = candidate
    if preferred:
        return preferred
    budget = max(1, display_units - 2)
    result = ""
    for character in clean:
        if _display_width_units(result + character) > budget:
            break
        result += character
    next_character = clean[len(result):len(result) + 1]
    if (
        result
        and next_character
        and result[-1].isascii()
        and result[-1].isalnum()
        and next_character.isascii()
        and next_character.isalnum()
    ):
        word_boundary = result.rfind(" ")
        if word_boundary >= max(4, len(result) // 2):
            result = result[:word_boundary]
    return f"{result.rstrip('，。！？,;: ')}…" if result else "…"


def _slot_artifact_kind(slot_kind: str) -> str:
    return {
        "code": "code",
        "formula": "formula",
        "table": "table",
        "visual": "visual",
    }.get(slot_kind, "")


def _block_matches_slot(block: CourseBlock, slot_kind: str) -> bool:
    artifact = _slot_artifact_kind(slot_kind)
    kinds = set(block_artifact_kinds(block))
    if artifact == "visual":
        return bool(
            kinds.intersection(
                {"diagram", "image", "data", "experiment", "source_excerpt"}
            )
        )
    return bool(artifact and artifact in kinds)


def _code_candidates(text: str) -> list[str]:
    fenced: list[str] = []
    for match in re.finditer(
        r"```(?:[A-Za-z0-9_+.#-]+)?[^\S\r\n]*\r?\n(.*?)```",
        text,
        re.DOTALL,
    ):
        value = match.group(1)
        # Remove only the structural newline immediately before the closing
        # fence. Additional trailing newlines belong to the source code and
        # must survive pagination as blank lines.
        if value.endswith("\r\n"):
            value = value[:-2]
        elif value.endswith(("\r", "\n")):
            value = value[:-1]
        if value.strip("\r\n"):
            fenced.append(value)
    return fenced or [text.strip("\r\n")]


def _code_language(text: str, block: CourseBlock) -> str:
    """Return a source-declared language, then a conservative generic inference."""

    fence = re.search(
        r"```([A-Za-z0-9_+.#-]+)?[^\S\r\n]*\r?\n",
        str(text or ""),
    )
    declared = str(
        (fence.group(1) if fence else "")
        or (block.payload or {}).get("code_language")
        or (block.payload or {}).get("language")
        or ""
    ).strip().casefold()
    aliases = {
        "cs": "csharp",
        "c#": "csharp",
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sh": "bash",
        "shell": "bash",
    }
    if declared:
        return aliases.get(declared, declared)
    source = max(_code_candidates(text), key=len)
    if re.search(r"\b(?:MonoBehaviour|Debug\.Log|SerializeField|GameObject)\b", source):
        return "csharp"
    if re.search(r"(?m)^\s*(?:async\s+)?def\s+\w+\s*\(", source):
        return "python"
    if re.search(r"\b(?:const|let|function)\s+\w+|=>", source):
        return "javascript"
    if re.search(r"(?im)^\s*(?:select|insert|update|delete|create\s+table)\b", source):
        return "sql"
    return ""


def _code_chunk_blocks(
    block: CourseBlock,
    chunks: list[str],
    *,
    language: str,
) -> list[CourseBlock]:
    """Attach source-line identity without changing the code carried by a chunk."""

    result: list[CourseBlock] = []
    start_line = 1
    chunk_count = len(chunks)
    for chunk_index, chunk in enumerate(chunks, start=1):
        source_line_count = len(chunk.split("\n"))
        payload_metadata = {
            "_v6_code_chunk_content": chunk,
            "_v6_code_language": language,
            "_v6_code_start_line": start_line,
            "_v6_code_end_line": start_line + source_line_count - 1,
            "_v6_code_chunk_index": chunk_index,
            "_v6_code_chunk_count": chunk_count,
            "_v6_artifact_only": True,
        }
        result.append(_block_with_source_excerpt(
            block,
            (
                f"```{language}\n{chunk}\n```"
                if block.kind != "code"
                else chunk
            ),
            artifact_kind="code",
            payload_metadata=payload_metadata,
        ))
        start_line += source_line_count
    return result


def _prose_source_text(block: CourseBlock) -> str:
    text = block_presentation_text(block)
    without_code = re.sub(
        r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n.*?```",
        "",
        text,
        flags=re.DOTALL,
    )
    prose_lines = [
        line
        for line in without_code.splitlines()
        if not re.match(r"^\s*\|.*\|\s*$", line)
        and not re.match(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$", line)
    ]
    prose = _visible_prose_text("\n".join(prose_lines))
    if prose == text.strip() and block.kind in {"code", "formula", "table"}:
        return ""
    return prose


def _artifact_free_prose_text(block: CourseBlock) -> str:
    """Return only the prose companion of a source-backed artifact block.

    Inline math remains ordinary teaching prose.  Only display formulae that
    the graph classifies as formula artifacts are removed here so that their
    source expression is rendered once in the formula slot, not duplicated in
    a prose continuation.
    """

    prose = _prose_source_text(block)
    if not prose or "formula" not in set(block_artifact_kinds(block)):
        return prose
    without_display_formula = re.sub(
        r"\$\$.+?\$\$|\\\[.+?\\\]",
        "",
        prose,
        flags=re.DOTALL,
    )
    return _visible_prose_text(without_display_formula)


def _code_display_line_cost(line: str, line_width: int) -> int:
    width = max(1, line_width)
    return max(1, (_display_width_units(line.expandtabs(4)) + width - 1) // width)


def _code_structure_text(
    line: str,
    *,
    in_block_comment: bool,
) -> tuple[str, bool]:
    """Return code characters that can affect brace structure."""

    structural: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(line):
        character = line[index]
        next_character = line[index + 1:index + 2]
        if in_block_comment:
            if character == "*" and next_character == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            index += 1
            continue
        if character in {'"', "'", "`"}:
            quote = character
            index += 1
            continue
        if character == "/" and next_character == "*":
            in_block_comment = True
            index += 2
            continue
        if (character == "/" and next_character == "/") or (
            character == "-" and next_character == "-"
        ):
            break
        if character == "#" and not "".join(structural).strip():
            break
        structural.append(character)
        index += 1
    return "".join(structural), in_block_comment


def _balanced_code_spans(lines: list[str]) -> list[list[str]]:
    """Find complete source brace blocks, preferring executable inner units."""

    stack: list[tuple[int, bool]] = []
    spans: list[list[str]] = []
    in_block_comment = False
    for index, line in enumerate(lines):
        structural_line, in_block_comment = _code_structure_text(
            line,
            in_block_comment=in_block_comment,
        )
        for character_index, character in enumerate(structural_line):
            if character == "{":
                stack.append((index, bool(structural_line[:character_index].strip())))
            elif character == "}" and stack:
                start, has_inline_signature = stack.pop()
                signature = start
                if not has_inline_signature:
                    line_index = next(
                        (
                            candidate
                            for candidate in range(start - 1, -1, -1)
                            if lines[candidate].strip()
                        ),
                        None,
                    )
                    if line_index is not None:
                        signature = line_index
                spans.append(lines[signature:index + 1])
    return spans


def _safe_code_excerpt(
    candidate: str,
    *,
    max_chars: int,
    max_lines: int,
) -> str:
    lines = candidate.splitlines()
    line_budget = max_lines or max(1, len(lines))
    char_budget = max_chars or max(1, len(candidate))
    line_width = max(24, char_budget // max(1, line_budget))

    def fits(candidate_lines: list[str]) -> bool:
        return bool(
            candidate_lines
            and len("\n".join(candidate_lines)) <= char_budget
            and sum(
                _code_display_line_cost(line, line_width)
                for line in candidate_lines
            ) <= line_budget
        )

    if fits(lines):
        return candidate.strip("\n")

    complete_spans = [span for span in _balanced_code_spans(lines) if fits(span)]
    if complete_spans:
        selected = max(
            complete_spans,
            key=lambda span: (
                sum(bool(line.strip()) for line in span),
                len("\n".join(span)),
            ),
        )
        return "\n".join(selected).strip("\n")

    selected: list[str] = []
    for line in lines:
        if not fits([*selected, line]):
            break
        selected.append(line)
    while selected and (
        not selected[-1].strip()
        or selected[-1].lstrip().startswith(("//", "#", "--"))
    ):
        selected.pop()
    return "\n".join(selected).strip("\n")


def _bounded_code_content(
    blocks: list[CourseBlock],
    *,
    max_chars: int,
    max_lines: int,
) -> str:
    """Return complete source code or require template-safe pagination."""

    if not blocks:
        return ""
    capacity = max_chars or 1600
    line_capacity = max_lines or 24
    complete_blocks: list[str] = []
    for block in blocks:
        payload = block.payload or {}
        candidate = (
            str(payload["_v6_code_chunk_content"])
            if "_v6_code_chunk_content" in payload
            else max(_code_candidates(block_source_text(block)), key=len)
        )
        if candidate:
            complete_blocks.append(candidate)
    content = "\n\n".join(complete_blocks)
    line_width = max(24, capacity // max(1, line_capacity))
    rendered_line_cost = sum(
        _code_display_line_cost(line, line_width)
        for line in content.split("\n")
    )
    if len(content) > capacity or rendered_line_cost > line_capacity:
        raise ValueError("template_slot_capacity_exceeded")
    return content


def _formula_candidates(text: str) -> list[str]:
    displayed = [
        match.group(0).strip()
        for match in re.finditer(r"\$\$.+?\$\$|\\\[.+?\\\]", text, re.DOTALL)
        if match.group(0).strip()
    ]
    if displayed:
        return displayed
    inline = [
        match.group(0).strip()
        for match in re.finditer(
            r"(?<!\\)\$(?!\$).+?(?<!\\)\$(?!\$)",
            text,
            re.DOTALL,
        )
        if match.group(0).strip()
    ]
    return list(dict.fromkeys(inline)) or [text.strip()]


def _bounded_formula_content(
    blocks: list[CourseBlock],
    *,
    max_chars: int,
) -> str:
    """Keep formula slots atomic when source blocks also contain instructions."""

    candidates = [
        candidate
        for block in blocks
        for candidate in _formula_candidates(block_source_text(block))
        if candidate
    ]
    if not candidates:
        return ""
    content = "\n\n".join(candidates)
    if max_chars and len(content) > max_chars:
        raise ValueError("template_slot_capacity_exceeded")
    return content


_ORDERED_STEP_PATTERN = re.compile(
    r"^\s*(?:(?:\d+)[.)、．]|[一二三四五六七八九十百]+[、.．)]|(?:step|步骤)\s*\d+\s*[:：.、-]?)\s*(.+?)\s*$",
    flags=re.IGNORECASE,
)
_NESTED_STEP_DETAIL_PATTERN = re.compile(r"^\s+[-*+]\s+(.+?)\s*$")


def _ordered_step_groups(value: str) -> list[tuple[str, list[str]]]:
    """Parse explicit source order without flattening detail boundaries."""

    steps: list[tuple[str, list[str]]] = []
    for line in str(value or "").splitlines():
        step_match = _ORDERED_STEP_PATTERN.match(line)
        if step_match:
            heading = _visible_prose_text(step_match.group(1)).strip()
            if heading:
                steps.append((heading, []))
            continue
        detail_match = _NESTED_STEP_DETAIL_PATTERN.match(line)
        if steps and detail_match:
            detail = _visible_prose_text(detail_match.group(1)).strip()
            if detail:
                steps[-1][1].append(detail)
    return steps


def _ordered_step_items(value: str) -> list[str]:
    """Preserve explicit source order while folding details into their parent step."""

    steps = _ordered_step_groups(value)

    if steps:
        result: list[str] = []
        for heading, details in steps:
            clean_heading = heading.rstrip(" :：")
            if not details:
                result.append(clean_heading)
                continue
            cjk = bool(re.search(r"[\u3400-\u9fff]", clean_heading))
            detail_separator = "；" if cjk else "; "
            relation_separator = "：" if cjk else ": "
            result.append(
                f"{clean_heading}{relation_separator}{detail_separator.join(details)}"
            )
        return result

    return [
        _visible_prose_text(re.sub(r"^\s*[-*+]\s+", "", line)).strip()
        for line in str(value or "").splitlines()
        if re.match(r"^\s*[-*+]\s+", line)
        and _visible_prose_text(re.sub(r"^\s*[-*+]\s+", "", line)).strip()
    ]


def _complete_ordered_step_item(
    heading: str,
    details: list[str],
) -> str:
    """Render one complete ordered source step without clipping its details."""

    clean_heading = heading.rstrip(" :：")
    if not details:
        return clean_heading
    cjk = bool(re.search(r"[\u3400-\u9fff]", clean_heading))
    detail_separator = "；" if cjk else "; "
    relation_separator = "：" if cjk else ": "
    def normalize_detail(value: str) -> str:
        return value.rstrip(" .。！？!?;；:：")

    def terminal_punctuation(value: str) -> str:
        clean = value.rstrip()
        return clean[-1] if clean and clean[-1] in ".。！？!?" else ""

    selected: list[str] = []
    selected_terminal = ""
    for detail in details:
        normalized_detail = normalize_detail(detail)
        if not normalized_detail:
            continue
        candidate_terminal = terminal_punctuation(detail)
        selected.append(normalized_detail)
        selected_terminal = candidate_terminal
    if selected:
        return (
            f"{clean_heading}{relation_separator}"
            f"{detail_separator.join(selected)}"
            f"{selected_terminal}"
        ).rstrip(" ;；:：")
    return clean_heading


def _canonical_step_sequence_text(value: str) -> str:
    """Normalize presentation-only separators while retaining factual tokens."""

    text = _presentation_summary_text(value)
    text = re.sub(r"(?m)^\s*(?:>\s*)+", "", text)
    text = re.sub(r"(?im)^\s*\[[ x]\]\s*", "", text)
    text = text.replace("*", "")
    # A template may render a source semicolon as a full stop (or omit the
    # separator around a nested detail).  Decimal points remain significant.
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", "", text)
    text = re.sub(r"[，,。；;：:！？!?、]", "", text)
    return re.sub(r"\s+", "", text).casefold()


def _ordered_step_sequence_visible(source: str, visible: str) -> bool:
    """Verify every ordered heading/detail atom is visible in source order."""

    groups = _ordered_step_groups(source)
    if len(groups) < 2:
        return True
    actual = _canonical_step_sequence_text(visible)
    cursor = 0
    for heading, details in groups:
        for atom in [heading, *details]:
            expected = _canonical_step_sequence_text(atom)
            if not expected:
                continue
            found_at = actual.find(expected, cursor)
            if found_at < 0:
                return False
            cursor = found_at + len(expected)
    return True


_STEP_LEAD_CRITICAL_FACT_RE = re.compile(
    r"(?:\b(?:admin(?:istrator)?|only|must|required|warning|caution|"
    r"prerequisite|backup|irreversible|failure|failed|unless|before)\b|"
    r"仅|只有|管理员|必须|务必|警告|注意|前提|备份|不可逆|失败|条件)",
    flags=re.IGNORECASE,
)
_STEP_LEAD_SCAFFOLD_RE = re.compile(
    r"^(?:"
    r"(?:please\s+)?(?:follow|complete|perform|carry\s+out|run|execute)\s+"
    r"(?:the\s+|these\s+)?[a-z\s-]{0,40}(?:steps?|operations?|tasks?|procedure|workflow)"
    r"(?:\s+in\s+(?:source\s+)?order)?"
    r"|(?:please\s+)?complete\s+[a-z\s-]{1,40}\s+in\s+(?:source\s+)?order"
    r"|procedure\s+record"
    r"|[a-z][a-z\s-]{0,36}\s+task"
    r"|(?:请)?(?:按|按照)(?:以下|下列|上述)(?:步骤|流程)(?:操作|执行)?"
    r"|(?:请)?(?:完成|执行|进行|遵循)(?:以下|下列|上述)"
    r"(?:步骤|操作|任务|流程)(?:以完成(?:本节)?(?:实践|任务|操作|流程))?"
    r"|依次(?:完成|执行)(?:以下|下列|上述)?(?:步骤|操作|任务|流程)"
    r")[.。:：]?$",
    flags=re.IGNORECASE,
)


def _ordered_step_lead_is_scaffolding(value: str) -> bool:
    """Recognize only narrow, fact-free directions that introduce steps."""

    normalized = _presentation_summary_text(value).strip()
    if not normalized or _STEP_LEAD_CRITICAL_FACT_RE.search(normalized):
        return False
    return _STEP_LEAD_SCAFFOLD_RE.fullmatch(normalized) is not None


def _ordered_step_projection_is_semantically_closed(source: str) -> bool:
    """Return whether ordered steps contain every post-intro prose line.

    Only a narrowly recognized, fact-free lead before the first explicit step
    is presentation scaffolding; the ordered headings and their indented
    details carry the teaching facts.  Any prerequisite/warning, top-level
    bullet, acceptance condition, or trailing paragraph is independent source
    meaning and cannot disappear into a steps-only template.
    """

    seen_step = False
    for line in str(source or "").splitlines():
        if _ORDERED_STEP_PATTERN.match(line):
            seen_step = True
            continue
        if seen_step and _NESTED_STEP_DETAIL_PATTERN.match(line):
            continue
        if not line.strip():
            continue
        if not seen_step and _ordered_step_lead_is_scaffolding(line):
            continue
        return False
    return seen_step


def _first_incomplete_visible_prose_block(
    source_blocks: list[CourseBlock],
    regions: list[SlideRegionV6],
) -> str:
    """Return the first block whose complete prose is absent from text regions.

    Template satisfiability must prove semantic content, not merely attach a
    block ID to some visible region.  Structured layouts are allowed to change
    Markdown markers and presentation punctuation, but every source token must
    remain visible in source order across declared continuations.
    """

    for block in source_blocks:
        if block.kind in {"image", "diagram", "graph_embed", "audio", "video"}:
            # These blocks are rendered by their native media/visual adapter;
            # their payload text is metadata rather than a prose companion.
            continue
        source_prose = _artifact_free_prose_text(block)
        expected = _canonical_step_sequence_text(source_prose)
        if not expected:
            continue
        visible = "\n".join(
            region.content
            for region in regions
            if region.content_kind in {"body", "items", "steps"}
            and block.block_id in region.source_block_ids
        )
        if (
            _ordered_step_groups(source_prose)
            and _ordered_step_projection_is_semantically_closed(source_prose)
            and _ordered_step_sequence_visible(source_prose, visible)
        ):
            continue
        actual = _canonical_step_sequence_text(visible)
        if expected not in actual:
            return block.block_id
    return ""


def source_required_slot_kinds(source_blocks: list[CourseBlock]) -> set[str]:
    """Return slots required by the learner-visible presentation projection."""

    sequence_roles = {"activity", "checkpoint", "orientation"}
    if any(
        block.role in sequence_roles
        and len(_ordered_step_items(block_presentation_text(block))) >= 2
        for block in source_blocks
    ):
        return {"steps"}
    return set()


def _layout_supports_required_slot_kinds(
    layout: Any,
    required_slot_kinds: set[str],
) -> bool:
    """Return whether a layout preserves each required semantic structure.

    A body slot is the lossless fallback for structured prose: it retains the
    source's ordered markers and context even when a card/step projection
    cannot do so.  The later shared fidelity predicate still proves that the
    complete source is visible, so this does not turn body into a bypass.
    """

    available = {slot.slot_kind for slot in layout.slots}
    supported = set(available)
    if "body" in available:
        supported.add("steps")
    return required_slot_kinds.issubset(supported)


def _layout_semantic_fallback_cost(
    layout: Any,
    source_blocks: list[CourseBlock],
) -> int:
    """Prefer native semantic slots over a verified lossless body fallback."""

    required = source_required_slot_kinds(source_blocks)
    available = {slot.slot_kind for slot in layout.slots}
    if required.issubset(available):
        return 0
    return 1 if _layout_supports_required_slot_kinds(layout, required) else 2


def _bounded_slot_content(
    blocks: list[CourseBlock],
    *,
    slot_kind: str,
    max_chars: int,
    max_items: int,
    max_lines: int,
    max_rows: int,
    supports_single_row_detail: bool = False,
    capacity_profile: str = "",
) -> str:
    if slot_kind == "code":
        return _bounded_code_content(
            blocks,
            max_chars=max_chars,
            max_lines=max_lines,
        )
    if slot_kind == "formula":
        return _bounded_formula_content(blocks, max_chars=max_chars)
    texts = []
    for block in blocks:
        text = (
            _prose_source_text(block)
            if slot_kind not in {"formula", "table", "visual"}
            else block_source_text(block)
        )
        if text:
            texts.append(text)
    if not texts:
        return ""
    capacity = max_chars or 520
    if slot_kind == "table":
        content = _normalize_markdown_table("\n".join(texts))
        lines = content.splitlines()
        _headers, rows = _table_components(content)
        oversized = bool(
            (max_rows and len(lines) > max_rows + 2)
            or len(content) > capacity
        )
        if oversized and not (supports_single_row_detail and len(rows) == 1):
            raise ValueError("template_slot_capacity_exceeded")
        return content.rstrip()
    if slot_kind == "steps":
        ordered_groups = [
            group
            for text in texts
            for group in _ordered_step_groups(text)
        ]
        fallback_steps = (
            []
            if ordered_groups
            else [_visible_prose_text(text).strip() for text in texts if text.strip()]
        )
        step_count = len(ordered_groups) or len(fallback_steps)
        item_limit = max_items or step_count
        if step_count > item_limit:
            raise ValueError("template_slot_capacity_exceeded")
        complete_items = (
            [
                _complete_ordered_step_item(heading, details)
                for heading, details in ordered_groups
            ]
            if ordered_groups
            else [
                _visible_prose_text(step).strip()
                for step in fallback_steps
            ]
        )
        if not capacity_profile_items_fit(capacity_profile, complete_items):
            raise ValueError("template_slot_capacity_exceeded")
        content = "\n".join(complete_items).rstrip()
        if len(content) > capacity or (
            max_lines and _prose_wrapped_line_cost(content) > max_lines
        ):
            raise ValueError("template_slot_capacity_exceeded")
        return content
    if slot_kind == "items":
        items_by_block: list[list[str]] = []
        for text in texts:
            candidates = [
                _visible_prose_text(re.sub(
                    r"^\s*(?:#{1,6}\s+|[-*+] |\d+[.)]\s*)",
                    "",
                    line,
                )).strip()
                for line in text.splitlines()
                if line.strip()
            ]
            items_by_block.append(candidates or [text])
        complete_items = [
            item
            for items in items_by_block
            for item in items
            if item
        ]
        item_limit = max_items or len(complete_items)
        if len(complete_items) > item_limit:
            raise ValueError("template_slot_capacity_exceeded")
        if not capacity_profile_items_fit(capacity_profile, complete_items):
            raise ValueError("template_slot_capacity_exceeded")
        content = "\n".join(complete_items).rstrip()
        if len(content) > capacity:
            raise ValueError("template_slot_capacity_exceeded")
        return content
    if slot_kind == "body":
        content = "\n\n".join(texts).rstrip()
        if len(content) > capacity or (
            max_lines and _prose_wrapped_line_cost(content) > max_lines
        ) or (
            capacity_profile
            and not capacity_profile_text_fits(capacity_profile, content)
        ):
            raise ValueError("template_slot_capacity_exceeded")
        return content
    if len(texts) == 1:
        return _semantic_prose_excerpt(texts[0], capacity)
    separator_cost = 2 * (len(texts) - 1)
    per_block_capacity = max(24, (capacity - separator_cost) // len(texts))
    excerpts = [
        _semantic_prose_excerpt(text, per_block_capacity)
        for text in texts
    ]
    content = "\n\n".join(excerpts)
    if len(content) > capacity:
        raise ValueError("template_slot_capacity_exceeded")
    return content


def _block_with_source_excerpt(
    block: CourseBlock,
    content: str,
    *,
    artifact_kind: str = "",
    payload_metadata: dict[str, Any] | None = None,
) -> CourseBlock:
    payload = dict(block.payload or {})
    key = next(
        (
            candidate
            for candidate in (
                "markdown",
                "text",
                "content",
                "code",
                "formula",
                "table",
                "summary",
            )
            if candidate in payload
        ),
        "text",
    )
    payload[key] = content
    if not artifact_kind and "slide_visible_text" in payload:
        payload["slide_visible_text"] = content
    if artifact_kind:
        payload["artifact_kind"] = artifact_kind
    if payload_metadata:
        payload.update(payload_metadata)
    return block.model_copy(update={"payload": payload}, deep=True)


def _block_with_prose_excerpt(block: CourseBlock, content: str) -> CourseBlock:
    """Create a prose-only view without retaining the source artifact kind."""

    return block.model_copy(
        update={
            "kind": "rich_text",
            "payload": {"markdown": content},
        },
        deep=True,
    )


def _pack_lines(
    lines: list[str],
    *,
    max_lines: int,
    max_chars: int,
    prefix_lines: list[str] | None = None,
) -> list[str]:
    prefix = list(prefix_lines or [])
    prefix_chars = len("\n".join(prefix))
    allowed_lines = max_lines or max(1, len(lines))
    if prefix and allowed_lines <= len(prefix):
        raise ValueError("template_slot_capacity_exceeded")
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate = [*prefix, *current, line]
        candidate_text = "\n".join(candidate)
        exceeds_lines = len(candidate) > allowed_lines
        exceeds_chars = bool(max_chars and len(candidate_text) > max_chars)
        if current and (exceeds_lines or exceeds_chars):
            chunks.append("\n".join([*prefix, *current]))
            current = [line]
            candidate_text = "\n".join([*prefix, line])
        else:
            current.append(line)
        if len([*prefix, *current]) > allowed_lines or (
            max_chars and len("\n".join([*prefix, *current])) > max_chars
        ):
            raise ValueError("template_slot_capacity_exceeded")
    if current:
        chunks.append("\n".join([*prefix, *current]))
    elif prefix and prefix_chars <= max_chars:
        chunks.append("\n".join(prefix))
    return chunks


def _pack_formulae(
    formulae: list[str],
    *,
    max_chars: int,
    max_lines: int,
) -> list[str]:
    """Pack atomic formulae against the renderer's multiline formula frame.

    The renderer displays formulae separated by one blank line, so character
    capacity alone can place many short symbols into a frame that only has
    room for a few visible lines.  Count both formula lines and separators.
    """

    def rendered_line_count(values: list[str]) -> int:
        formula_lines = sum(
            max(1, len(str(value or "").splitlines())) for value in values
        )
        return formula_lines + max(0, len(values) - 1)

    chunks: list[str] = []
    current: list[str] = []
    for formula in formulae:
        candidate = "\n\n".join([*current, formula])
        exceeds_chars = bool(max_chars and len(candidate) > max_chars)
        exceeds_lines = bool(
            max_lines and rendered_line_count([*current, formula]) > max_lines
        )
        if current and (exceeds_chars or exceeds_lines):
            chunks.append("\n\n".join(current))
            current = [formula]
            continue
        if (max_chars and len(candidate) > max_chars) or (
            max_lines and rendered_line_count([formula]) > max_lines
        ):
            raise ValueError("template_slot_capacity_exceeded")
        current.append(formula)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _pack_code_lines(
    lines: list[str],
    *,
    max_lines: int,
    max_chars: int,
) -> list[str]:
    """Pack every code line at stable structural boundaries when possible."""

    allowed_lines = max_lines or max(1, len(lines))
    capacity = max_chars or max(1, len("\n".join(lines)))
    line_width = max(24, capacity // max(1, allowed_lines))

    def exceeds(candidate: list[str]) -> bool:
        return bool(
            len("\n".join(candidate)) > capacity
            or sum(
                _code_display_line_cost(line, line_width)
                for line in candidate
            ) > allowed_lines
        )

    for line in lines:
        if exceeds([line]):
            raise ValueError("template_slot_capacity_exceeded")

    minimum_chunk_cost = max(2, min(4, ceil(allowed_lines / 4)))
    minimum_chunk_chars = min(
        48,
        max(24, (max_chars or len("\n".join(lines))) // 12),
    )

    def nonblank_before(index: int) -> str:
        for candidate in reversed(lines[:index]):
            if candidate.strip():
                return candidate.strip()
        return ""

    def nonblank_after(index: int) -> str:
        for candidate in lines[index:]:
            if candidate.strip():
                return candidate.strip()
        return ""

    def method_declaration(value: str) -> bool:
        if not re.search(r"\)\s*(?:where\b.*)?$", value):
            return False
        return not re.match(
            r"^(?:if|for|foreach|while|switch|catch|using|lock)\b",
            value,
        )

    def boundary_cost(index: int) -> tuple[int, int]:
        if index >= len(lines):
            return 0, 0
        left = nonblank_before(index)
        right = nonblank_after(index)
        adjacent_declarations = bool(
            re.search(r"\)\s*;\s*$", left)
            and re.search(r"\)\s*;\s*$", right)
        )
        hard_break = bool(
            left.endswith("{")
            or method_declaration(left)
            or adjacent_declarations
            or right in {"{", "}"}
            or re.match(r"^(?:else|catch|finally)\b", right)
        )
        if not lines[index - 1].strip():
            semantic_rank = 0
        elif left in {"}", "};"}:
            semantic_rank = 1
        elif left.endswith(";"):
            semantic_rank = 2
        else:
            semantic_rank = 3
        return int(hard_break), semantic_rank

    # Dynamic programming rejects sparse fragments first, then selects the safest
    # structural boundaries before minimizing the page count. A method longer
    # than one page still splits deterministically at the least harmful statement
    # boundary instead of failing or dropping it.
    best: dict[int, tuple[tuple[int, int, int, int, int], list[int]]] = {
        len(lines): ((0, 0, 0, 0, 0), [])
    }
    for start in range(len(lines) - 1, -1, -1):
        candidates: list[tuple[tuple[int, int, int, int, int], list[int]]] = []
        for end in range(start + 1, len(lines) + 1):
            chunk_lines = lines[start:end]
            if exceeds(chunk_lines):
                break
            continuation = best.get(end)
            if continuation is None:
                continue
            chunk_cost = sum(
                _code_display_line_cost(line, line_width)
                for line in chunk_lines
            )
            chunk_chars = len(re.sub(r"\s+", "", "".join(chunk_lines)))
            sparse = int(
                chunk_cost < minimum_chunk_cost
                or chunk_chars < minimum_chunk_chars
            )
            hard_break, semantic_rank = boundary_cost(end)
            following, following_breaks = continuation
            score = (
                sparse + following[0],
                hard_break + following[1],
                1 + following[2],
                semantic_rank + following[3],
                (allowed_lines - chunk_cost) ** 2 + following[4],
            )
            candidates.append((score, [end, *following_breaks]))
        if not candidates:
            raise ValueError("template_slot_capacity_exceeded")
        best[start] = min(candidates, key=lambda candidate: candidate[0])

    boundaries = best[0][1]
    chunks: list[str] = []
    start = 0
    for end in boundaries:
        chunks.append("\n".join(lines[start:end]))
        start = end
    return chunks


def _split_artifact_block(
    block: CourseBlock,
    *,
    slot_kind: str,
    max_chars: int,
    max_lines: int,
    max_rows: int,
) -> list[CourseBlock]:
    content = block_source_text(block)
    if slot_kind == "code":
        code = max(_code_candidates(content), key=len)
        chunks = _pack_code_lines(
            code.splitlines(),
            max_lines=max_lines,
            max_chars=max_chars,
        )
    elif slot_kind == "table":
        lines = content.splitlines()
        header: list[str] = []
        rows = lines
        if len(lines) >= 2 and re.match(r"^\s*\|.*\|\s*$", lines[0]) and re.match(
            r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$",
            lines[1],
        ):
            header = lines[:2]
            rows = lines[2:]
        chunks = _pack_lines(
            rows,
            max_lines=(max_rows or max(1, len(rows))) + len(header),
            max_chars=max_chars,
            prefix_lines=header,
        )
    elif slot_kind == "formula":
        formulae = _formula_candidates(content)
        chunks = _pack_formulae(
            formulae,
            max_chars=max_chars,
            max_lines=max_lines,
        )
    else:
        return [block]
    if slot_kind == "code":
        return _code_chunk_blocks(
            block,
            chunks,
            language=_code_language(content, block),
        )
    return [
        _block_with_source_excerpt(
            block,
            chunk,
            artifact_kind=slot_kind,
            payload_metadata={"_v6_artifact_only": True},
        )
        for chunk in chunks
    ]


def _split_code_block_for_layout_variants(
    block: CourseBlock,
    *,
    slot: Any,
    split_first_page: bool,
) -> list[CourseBlock]:
    """Use the narrow split capacity once, then the declared full-width capacity."""

    continuation_chars = int(
        getattr(slot, "continuation_max_chars", 0) or slot.max_chars
    )
    continuation_lines = int(
        getattr(slot, "continuation_max_lines", 0) or slot.max_lines
    )
    if not split_first_page or (
        continuation_chars == slot.max_chars
        and continuation_lines == slot.max_lines
    ):
        return _split_artifact_block(
            block,
            slot_kind="code",
            max_chars=continuation_chars,
            max_lines=continuation_lines,
            max_rows=slot.max_rows,
        )

    code = max(_code_candidates(block_source_text(block)), key=len)
    lines = code.splitlines()
    split_chunks = _pack_code_lines(
        lines,
        max_lines=slot.max_lines,
        max_chars=slot.max_chars,
    )
    first_chunk = split_chunks[0]
    # ``splitlines()`` discards a terminal blank source line. Count the exact
    # newline-separated records so the continuation neither duplicates nor
    # drops the blank separator represented at the page boundary.
    consumed_lines = len(first_chunk.split("\n"))
    remaining_lines = lines[consumed_lines:]
    chunks = [first_chunk]
    if remaining_lines:
        chunks.extend(_pack_code_lines(
            remaining_lines,
            max_lines=continuation_lines,
            max_chars=continuation_chars,
        ))
    return _code_chunk_blocks(
        block,
        chunks,
        language=_code_language(block_source_text(block), block),
    )


def _semantic_prose_groups(value: str) -> list[str]:
    """Return complete visible paragraphs, splitting only at sentence boundaries."""

    return [
        "\n".join(line.rstrip() for line in group.splitlines()).strip()
        for group in re.split(r"\n\s*\n", _visible_prose_text(value))
        if group.strip()
    ]


def _pack_complete_text_items(
    items: list[str],
    *,
    max_chars: int,
    max_items: int = 0,
    max_lines: int = 0,
    separator: str = "\n",
    items_fit: Callable[[list[str]], bool] | None = None,
) -> list[list[str]]:
    """Pack complete semantic items without generating excerpts or ellipses."""

    capacity = max_chars or max(1, len(separator.join(items)))
    item_limit = max_items or max(1, len(items))
    chunks: list[list[str]] = []
    current: list[str] = []
    for item in items:
        candidate = [*current, item]
        candidate_text = separator.join(candidate)
        if current and (
            len(candidate) > item_limit
            or len(candidate_text) > capacity
            or (items_fit is not None and not items_fit(candidate))
            or (
                max_lines
                and _prose_wrapped_line_cost(candidate_text) > max_lines
            )
        ):
            chunks.append(current)
            current = [item]
        else:
            current = candidate
        current_text = separator.join(current)
        if (
            len(current) > item_limit
            or len(current_text) > capacity
            or (items_fit is not None and not items_fit(current))
            or (
                max_lines
                and _prose_wrapped_line_cost(current_text) > max_lines
            )
        ):
            raise ValueError("template_slot_capacity_exceeded")
    if current:
        chunks.append(current)
    return chunks


_PROSE_LINE_WIDTH_UNITS = 44


def _prose_wrapped_line_cost(value: str) -> int:
    """Estimate readable 16pt lines for the shared two-column body adapter."""

    return sum(
        max(
            1,
            ceil(_display_width_units(line) / _PROSE_LINE_WIDTH_UNITS),
        )
        for line in str(value or "").splitlines()
    )


def _prose_fits_slot(
    value: str,
    *,
    max_chars: int,
    max_lines: int,
    capacity_profile: str = "",
) -> bool:
    return bool(
        value
        and (not max_chars or len(value) <= max_chars)
        and (not max_lines or _prose_wrapped_line_cost(value) <= max_lines)
        and (
            not capacity_profile
            or capacity_profile_text_fits(capacity_profile, value)
        )
    )


def _pack_complete_prose_groups(
    groups: list[str],
    *,
    max_chars: int,
    max_lines: int,
    capacity_profile: str = "",
) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for group in groups:
        candidate = [*current, group]
        if current and not _prose_fits_slot(
            "\n\n".join(candidate),
            max_chars=max_chars,
            max_lines=max_lines,
            capacity_profile=capacity_profile,
        ):
            chunks.append(current)
            current = [group]
        else:
            current = candidate
        if not _prose_fits_slot(
            "\n\n".join(current),
            max_chars=max_chars,
            max_lines=max_lines,
            capacity_profile=capacity_profile,
        ):
            raise ValueError("template_slot_capacity_exceeded")
    if current:
        chunks.append(current)
    return chunks


def _split_oversized_prose_group(
    value: str,
    *,
    max_chars: int,
    max_lines: int = 0,
    capacity_profile: str = "",
) -> list[str]:
    """Split one oversized sentence losslessly when it cannot fit on one page."""

    text = str(value or "").strip()
    if not text or _prose_fits_slot(
        text,
        max_chars=max_chars,
        max_lines=max_lines,
        capacity_profile=capacity_profile,
    ):
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while not _prose_fits_slot(
        remaining,
        max_chars=max_chars,
        max_lines=max_lines,
        capacity_profile=capacity_profile,
    ):
        window_limit = min(len(remaining), max_chars or len(remaining))
        fitting_boundaries = [
            (position, rank)
            for position, rank in semantic_break_positions(
                remaining[:window_limit]
            )
            if _prose_fits_slot(
                remaining[:position],
                max_chars=max_chars,
                max_lines=max_lines,
                capacity_profile=capacity_profile,
            )
        ]
        window_end = 0
        if fitting_boundaries:
            furthest_position = max(position for position, _ in fitting_boundaries)
            useful_floor = max(2, ceil(furthest_position * 0.55))
            useful_boundaries = [
                candidate
                for candidate in fitting_boundaries
                if candidate[0] >= useful_floor
            ]
            window_end = min(
                useful_boundaries,
                key=lambda candidate: (candidate[1], -candidate[0]),
            )[0]
        if not window_end:
            # A genuinely unbroken token has no semantic boundary. Locate the
            # largest renderable prefix without the previous character-by-
            # character quadratic scan; no source text is removed. Search
            # each renderer font-size band independently because a dynamic
            # font threshold makes the combined predicate non-monotonic.
            for band_low, band_high in (
                (181, window_limit),
                (171, min(180, window_limit)),
                (91, min(170, window_limit)),
                (1, min(90, window_limit)),
            ):
                if band_low > band_high:
                    continue
                low = band_low
                high = band_high
                band_best = 0
                while low <= high:
                    midpoint = (low + high) // 2
                    if _prose_fits_slot(
                        remaining[:midpoint],
                        max_chars=max_chars,
                        max_lines=max_lines,
                        capacity_profile=capacity_profile,
                    ):
                        band_best = midpoint
                        low = midpoint + 1
                    else:
                        high = midpoint - 1
                if band_best:
                    window_end = band_best
                    break
        if window_end <= 1:
            raise ValueError("template_slot_capacity_exceeded")
        split_at = window_end
        chunk = remaining[:split_at].strip()
        if not chunk or not _prose_fits_slot(
            chunk,
            max_chars=max_chars,
            max_lines=max_lines,
            capacity_profile=capacity_profile,
        ):
            split_at = window_end
            chunk = remaining[:split_at].strip()
        chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _rebalance_prose_continuations(
    chunks: list[str],
    *,
    max_chars: int,
    max_lines: int,
    capacity_profile: str = "",
) -> list[str]:
    """Avoid sparse continuation pages by redistributing adjacent source text."""

    balanced = [chunk.strip() for chunk in chunks if chunk.strip()]
    if len(balanced) < 2:
        return balanced
    minimum_useful_chars = max(
        30,
        min(120, (max_chars or max(map(len, balanced))) // 5),
    )
    maximum_attempts = max(1, len(balanced) * 2)
    for _ in range(maximum_attempts):
        sparse_index = next(
            (
                index
                for index, chunk in enumerate(balanced)
                if len(chunk) < minimum_useful_chars
            ),
            None,
        )
        if sparse_index is None:
            break
        neighbor_index = (
            1
            if sparse_index == 0
            else sparse_index - 1
        )
        pair_start = min(sparse_index, neighbor_index)
        left_original, right_original = balanced[pair_start: pair_start + 2]
        preserves_semantic_boundary = bool(
            re.search(r"[。！？.!?；;]\s*$", left_original)
            or len(left_original) <= 60
            or re.match(
                r"^(?:[-*+>]\s+|#{1,6}\s+|\d+[.)、]\s*)",
                right_original,
            )
        )
        if preserves_semantic_boundary:
            separator = "\n\n"
        elif re.search(r"(?:[-*+>]|#{1,6}|\d+[.)、])\s*$", left_original):
            # A previous capacity split may land immediately after a Markdown
            # marker. Restore the structural space without promoting that
            # artificial boundary to a paragraph-level split candidate.
            separator = " "
        else:
            separator = ""
        combined = f"{left_original}{separator}{right_original}"
        if _prose_fits_slot(
            combined,
            max_chars=max_chars,
            max_lines=max_lines,
            capacity_profile=capacity_profile,
        ):
            balanced[pair_start: pair_start + 2] = [combined]
            continue
        candidates: list[tuple[tuple[int, int, int, int], str, str]] = []
        for position, semantic_rank in semantic_break_positions(combined):
            left = combined[:position].strip()
            right = combined[position:].strip()
            if not _prose_fits_slot(
                left,
                max_chars=max_chars,
                max_lines=max_lines,
                capacity_profile=capacity_profile,
            ) or not _prose_fits_slot(
                right,
                max_chars=max_chars,
                max_lines=max_lines,
                capacity_profile=capacity_profile,
            ):
                continue
            candidates.append((
                (
                    max(
                        0,
                        minimum_useful_chars - min(len(left), len(right)),
                    ),
                    semantic_rank,
                    abs(
                        _prose_wrapped_line_cost(left)
                        - _prose_wrapped_line_cost(right)
                    ),
                    abs(len(left) - len(right)),
                ),
                left,
                right,
            ))
        if not candidates:
            break
        _, left, right = min(candidates, key=lambda candidate: candidate[0])
        replacement = [left, right]
        if replacement == balanced[pair_start: pair_start + 2]:
            break
        balanced[pair_start: pair_start + 2] = replacement
    return balanced


def _split_text_block_for_slot(
    block: CourseBlock,
    *,
    slot_kind: str,
    max_chars: int,
    max_items: int,
    max_lines: int = 0,
    capacity_profile: str = "",
) -> list[CourseBlock]:
    """Split prose, lists, and procedures only at complete semantic boundaries."""

    source = _prose_source_text(block)
    if slot_kind == "steps":
        items = [
            _complete_ordered_step_item(heading, details)
            for heading, details in _ordered_step_groups(source)
        ]
        if not items:
            raise ValueError("template_slot_capacity_exceeded")
        chunks = _pack_complete_text_items(
            items,
            max_chars=max_chars,
            max_items=max_items,
            max_lines=max_lines,
            items_fit=(
                lambda candidate: capacity_profile_items_fit(
                    capacity_profile,
                    candidate,
                )
            )
            if capacity_profile
            else None,
        )
        return [
            _block_with_source_excerpt(
                block,
                "\n".join(
                    f"{index}. {item}"
                    for index, item in enumerate(chunk, start=1)
                ),
            )
            for chunk in chunks
        ]
    if slot_kind == "items":
        items = [
            _visible_prose_text(re.sub(
                r"^\s*(?:#{1,6}\s+|[-*+] |\d+[.)]\s*)",
                "",
                line,
            )).strip()
            for line in source.splitlines()
            if line.strip()
        ]
        chunks = _pack_complete_text_items(
            items,
            max_chars=max_chars,
            max_items=max_items,
            max_lines=max_lines,
            items_fit=(
                lambda candidate: capacity_profile_items_fit(
                    capacity_profile,
                    candidate,
                )
            )
            if capacity_profile
            else None,
        )
        return [
            _block_with_source_excerpt(
                block,
                "\n".join(f"- {item}" for item in chunk),
            )
            for chunk in chunks
        ]
    if slot_kind == "body":
        chunks: list[list[str]] = []
        pending_groups: list[str] = []

        def flush_pending_groups() -> None:
            nonlocal pending_groups
            if not pending_groups:
                return
            chunks.extend(_pack_complete_prose_groups(
                pending_groups,
                max_chars=max_chars,
                max_lines=max_lines,
                capacity_profile=capacity_profile,
            ))
            pending_groups = []

        for group in _semantic_prose_groups(source):
            if _prose_fits_slot(
                group,
                max_chars=max_chars,
                max_lines=max_lines,
                capacity_profile=capacity_profile,
            ):
                candidate = [*pending_groups, group]
                if pending_groups and not _prose_fits_slot(
                    "\n\n".join(candidate),
                    max_chars=max_chars,
                    max_lines=max_lines,
                    capacity_profile=capacity_profile,
                ):
                    flush_pending_groups()
                pending_groups.append(group)
                continue
            flush_pending_groups()
            chunks.extend(
                [fragment]
                for fragment in _split_oversized_prose_group(
                    group,
                    max_chars=max_chars,
                    max_lines=max_lines,
                    capacity_profile=capacity_profile,
                )
            )
        flush_pending_groups()
        balanced_chunks = _rebalance_prose_continuations(
            ["\n\n".join(chunk) for chunk in chunks],
            max_chars=max_chars,
            max_lines=max_lines,
            capacity_profile=capacity_profile,
        )
        return [
            _block_with_source_excerpt(block, chunk)
            for chunk in balanced_chunks
        ]
    return [block]


def _display_width_units(value: str) -> int:
    return sum(1 if ord(character) < 128 else 2 for character in str(value or ""))


_TITLE_TOKEN_RE = re.compile(r"\s+|[A-Za-z0-9_./:+#@%-]+|[^\x00-\x7f]|[^\s]")


def _title_wrapped_line_cost(value: str, *, line_width_units: int) -> int:
    """Estimate title wrapping without breaking ASCII identifiers or words."""

    clean = " ".join(_visible_prose_text(value).split())
    if not clean:
        return 0
    width = max(1, int(line_width_units))
    lines = 1
    current_width = 0
    pending_space = False
    for match in _TITLE_TOKEN_RE.finditer(clean):
        token = match.group(0)
        if token.isspace():
            pending_space = current_width > 0
            continue
        token_width = _display_width_units(token)
        if token_width > width:
            return 10**9
        separator_width = 1 if pending_space and current_width else 0
        if current_width and current_width + separator_width + token_width > width:
            lines += 1
            current_width = token_width
        else:
            current_width += separator_width + token_width
        pending_space = False
    return lines


def _title_fits_slot(value: str, slot: Any) -> bool:
    """Validate complete title text against the slot's rendered line geometry."""

    clean = " ".join(_visible_prose_text(value).split())
    if not clean:
        return False
    max_chars = int(getattr(slot, "max_chars", 0) or 0)
    max_lines = max(1, int(getattr(slot, "max_lines", 0) or 1))
    if not max_chars:
        return True
    # Template title capacities are declared in full-width character units.
    # Convert that total capacity to display-width units and distribute it
    # across the explicitly allowed lines.  This keeps complete CJK/mixed
    # titles while rejecting an indivisible identifier wider than one line.
    total_width_units = max_chars * 2
    line_width_units = max(1, ceil(total_width_units / max_lines))
    return _title_wrapped_line_cost(
        clean,
        line_width_units=line_width_units,
    ) <= max_lines


def _table_cells(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", str(line or "").strip().strip("|"))
    return [
        _visible_prose_text(cell.replace(r"\|", "|")).replace("\n", " ").strip()
        for cell in cells
    ]


def _is_table_separator(line: str) -> bool:
    stripped = str(line or "").strip()
    return bool(stripped and re.fullmatch(r"[|:\-\s]+", stripped) and "-" in stripped)


def _table_components(value: str) -> tuple[list[str], list[list[str]]]:
    lines = [
        line.strip()
        for line in str(value or "").splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if not lines:
        return [], []
    headers = _table_cells(lines[0])
    data_lines = lines[1:]
    if data_lines and _is_table_separator(data_lines[0]):
        data_lines = data_lines[1:]
    column_count = max(1, len(headers))
    rows: list[list[str]] = []
    for line in data_lines:
        if _is_table_separator(line):
            continue
        cells = _table_cells(line)
        rows.append((cells + [""] * column_count)[:column_count])
    return headers, rows


def _markdown_table_text(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""

    def markdown_cell(value: str) -> str:
        return str(value or "").replace("|", r"\|")

    column_count = len(headers)
    normalized_rows = [
        (list(row) + [""] * column_count)[:column_count]
        for row in rows
    ]
    return "\n".join([
        "| " + " | ".join(markdown_cell(cell) for cell in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *(
            "| " + " | ".join(markdown_cell(cell) for cell in row) + " |"
            for row in normalized_rows
        ),
    ])


def _normalize_markdown_table(
    value: str,
    *,
    cell_display_units: int = 0,
) -> str:
    headers, rows = _table_components(value)
    if not headers:
        return _visible_prose_text(value)
    if cell_display_units:
        headers = [
            _display_excerpt(cell, cell_display_units)
            for cell in headers
        ]
        rows = [
            [_display_excerpt(cell, cell_display_units) for cell in row]
            for row in rows
        ]
    return _markdown_table_text(headers, rows)


def _table_row_wrap_cost(row: str, column_chars: int) -> int:
    cells = _table_cells(row)
    capacity = max(1, int(column_chars or 1))
    return max(
        1,
        max(
            (
                max(1, (_display_width_units(cell) + capacity - 1) // capacity)
                for cell in cells
            ),
            default=1,
        ),
    )


def _table_page_uses_wide_variant(
    slot: Any,
    headers: list[str],
    *,
    split_first_page: bool,
    page_index: int,
) -> bool:
    wide_min_columns = int(getattr(slot, "wide_min_columns", 0) or 0)
    return bool(
        page_index == 0
        and split_first_page
        and wide_min_columns
        and len(headers) >= wide_min_columns
    )


def _table_page_column_capacity(
    slot: Any,
    headers: list[str],
    *,
    split_first_page: bool,
    page_index: int,
) -> int:
    uses_wide_variant = _table_page_uses_wide_variant(
        slot,
        headers,
        split_first_page=split_first_page,
        page_index=page_index,
    )
    if page_index == 0 and split_first_page and not uses_wide_variant:
        declared = int(slot.split_column_chars or slot.full_column_chars or 1)
    else:
        declared = int(slot.full_column_chars or slot.split_column_chars or 1)
    # Slot capacity is declared against a three-column reference table. Wider
    # schemas keep the same template geometry, so each cell's safe display
    # width must shrink instead of forcing a smaller font.
    return max(
        6,
        min(declared, round(declared * 3 / max(3, len(headers)))),
    )


def _table_page_wrapped_budget(
    slot: Any,
    headers: list[str],
    *,
    split_first_page: bool,
    page_index: int,
) -> int:
    uses_wide_variant = _table_page_uses_wide_variant(
        slot,
        headers,
        split_first_page=split_first_page,
        page_index=page_index,
    )
    if page_index == 0 and split_first_page and not uses_wide_variant:
        declared = int(slot.split_wrapped_lines or slot.full_wrapped_lines or 0)
    else:
        declared = int(slot.full_wrapped_lines or slot.split_wrapped_lines or 0)
    if not declared:
        return 0
    # The wrapped-line contract is calibrated against a three-column table.
    # Fewer columns have materially more vertical room per row, so scale the
    # budget without weakening the long-cell safety check for 3+ columns.
    if len(headers) < 3:
        return max(declared, round(declared * 3 / len(headers)))
    return declared


def _table_rows_exceed_layout_slot(
    slot: Any,
    headers: list[str],
    rows: list[list[str]],
    *,
    split_first_page: bool,
    page_index: int,
) -> bool:
    candidate_text = _markdown_table_text(headers, rows)
    column_capacity = _table_page_column_capacity(
        slot,
        headers,
        split_first_page=split_first_page,
        page_index=page_index,
    )
    header_cost = max(
        1,
        max(
            (
                (_display_width_units(cell) + column_capacity - 1)
                // column_capacity
                for cell in headers
            ),
            default=1,
        ),
    )
    wrapped_cost = header_cost + sum(
        max(
            1,
            max(
                (
                    (_display_width_units(cell) + column_capacity - 1)
                    // column_capacity
                    for cell in row
                ),
                default=1,
            ),
        )
        for row in rows
    )
    wrapped_budget = _table_page_wrapped_budget(
        slot,
        headers,
        split_first_page=split_first_page,
        page_index=page_index,
    )
    return bool(
        (slot.max_rows and len(rows) > slot.max_rows)
        or (slot.max_chars and len(candidate_text) > slot.max_chars)
        or (wrapped_budget and wrapped_cost > wrapped_budget)
    )


def _table_fragment_requires_exclusive_page(
    block: CourseBlock,
    *,
    slot: Any,
    split_first_page: bool,
) -> bool:
    """Prove whether a table fragment cannot share its page with support."""

    headers, rows = _table_components(block_source_text(block))
    if not headers or not rows:
        return False
    if _table_page_uses_wide_variant(
        slot,
        headers,
        split_first_page=split_first_page,
        page_index=0,
    ):
        return True
    return bool(
        len(rows) == 1
        and _table_rows_exceed_layout_slot(
            slot,
            headers,
            rows,
            split_first_page=split_first_page,
            page_index=0,
        )
    )


def _split_table_block_for_layout_variants(
    block: CourseBlock,
    *,
    slot: Any,
    split_first_page: bool,
) -> list[CourseBlock]:
    headers, rows = _table_components(block_source_text(block))
    if not headers:
        return _split_artifact_block(
            block,
            slot_kind="table",
            max_chars=slot.max_chars,
            max_lines=slot.max_lines,
            max_rows=slot.max_rows,
        )
    chunks: list[str] = []
    current: list[list[str]] = []
    page_index = 0
    def rendered_text(candidate_rows: list[list[str]]) -> str:
        return _markdown_table_text(headers, candidate_rows)

    def exceeds(candidate_rows: list[list[str]]) -> bool:
        return _table_rows_exceed_layout_slot(
            slot,
            headers,
            candidate_rows,
            split_first_page=split_first_page,
            page_index=page_index,
        )

    for row in rows:
        candidate = [*current, row]
        if current and exceeds(candidate):
            chunks.append(rendered_text(current))
            page_index += 1
            current = [row]
        else:
            current = candidate
        if exceeds(current):
            # A single oversized row has its own declared row-detail adapter.
            # Preserve the complete source row here so Web and PPTX can expand
            # its fields horizontally instead of rejecting or truncating it.
            if len(current) == 1 and len(headers) >= 2:
                chunks.append(rendered_text(current))
                page_index += 1
                current = []
                continue
            raise ValueError("template_slot_capacity_exceeded")
    if current:
        chunks.append(rendered_text(current))
    elif not chunks and len(_markdown_table_text(headers, [])) <= slot.max_chars:
        chunks.append(_markdown_table_text(headers, []))
    return [
        _block_with_source_excerpt(
            block,
            chunk,
            artifact_kind="table",
            payload_metadata={"_v6_artifact_only": True},
        )
        for chunk in chunks
    ]


def _slot_source_blocks(slot: Any, source_blocks: list[CourseBlock]) -> list[CourseBlock]:
    """Mirror template slot assignment closely enough to detect semantic loss."""

    if slot.slot_kind in {"code", "formula", "table", "visual"}:
        return [
            block
            for block in source_blocks
            if _block_matches_slot(block, slot.slot_kind)
        ]
    preferred_roles = set(slot.source_roles)
    all_candidates = [
        block
        for block in source_blocks
        if _prose_source_text(block)
    ]
    preferred = [
        block for block in all_candidates if block.role in preferred_roles
    ]
    candidates = preferred or all_candidates
    if slot.slot_kind == "steps":
        return [
            block
            for block in candidates
            if _ordered_step_groups(_prose_source_text(block))
        ]
    return candidates


def _text_slot_accepts_block(slot: Any, block: CourseBlock) -> bool:
    """Return whether one frozen block can honestly express one text slot."""

    prose = _prose_source_text(block)
    if not prose:
        return False
    if (
        slot.slot_kind == "steps"
        and not _ordered_step_groups(prose)
        and block.role not in {"activity", "checkpoint", "orientation"}
    ):
        return False
    source_roles = set(slot.source_roles)
    if source_roles and block.role not in source_roles:
        return False
    return True


def _layout_source_assignments(
    layout: Any,
    source_blocks: list[CourseBlock],
) -> _LayoutSourceAssignments:
    """Bind source blocks once so Story, Visual, and Template cannot disagree.

    Each required semantic slot receives a distinct source block. A single
    paragraph therefore cannot masquerade as two independent meanings. Extra
    blocks are assigned by declared source role; anything the selected layout
    cannot express remains explicit for a declared safe continuation.
    """

    content_slots = [
        slot
        for slot in layout.slots
        if slot.slot_kind not in {"title", "eyebrow", "notes"}
    ]
    artifact_slots = [
        slot
        for slot in content_slots
        if slot.slot_kind in {"code", "formula", "table", "visual"}
    ]
    artifact_assignments = {
        slot.slot_id: [
            block
            for block in source_blocks
            if _block_matches_slot(block, slot.slot_kind)
        ]
        for slot in artifact_slots
    }

    text_slots = [
        slot
        for slot in content_slots
        if slot.slot_kind in {"body", "items", "steps"}
    ]
    prose_blocks = [block for block in source_blocks if _prose_source_text(block)]
    required_slots = [slot for slot in text_slots if slot.required]
    candidates_by_slot = {
        slot.slot_id: [
            block
            for block in prose_blocks
            if _text_slot_accepts_block(slot, block)
        ]
        for slot in text_slots
    }

    anchored: dict[str, CourseBlock] = {}
    used_block_ids: set[int] = set()
    # Constrained slots go first so a generic body cannot consume the only
    # block capable of satisfying a role-specific required slot.
    required_search_order = sorted(
        required_slots,
        key=lambda slot: (
            len(candidates_by_slot[slot.slot_id]),
            next(index for index, item in enumerate(text_slots) if item is slot),
        ),
    )

    source_indexes = {id(block): index for index, block in enumerate(prose_blocks)}
    best_assignment: dict[str, CourseBlock] | None = None
    best_score: tuple[int, int, tuple[int, ...]] | None = None

    def bind_required(index: int) -> None:
        nonlocal best_assignment, best_score
        if index >= len(required_search_order):
            positions = sorted(source_indexes[id(block)] for block in anchored.values())
            if not positions:
                score = (0, 0, ())
            else:
                selected = {id(block) for block in anchored.values()}
                gaps = sum(
                    1
                    for candidate in prose_blocks[positions[0]:positions[-1] + 1]
                    if id(candidate) not in selected
                )
                score = (
                    gaps,
                    positions[-1] - positions[0],
                    tuple(
                        source_indexes[id(anchored[slot.slot_id])]
                        for slot in required_slots
                    ),
                )
            if best_score is None or score < best_score:
                best_score = score
                best_assignment = dict(anchored)
            return
        slot = required_search_order[index]
        for block in candidates_by_slot[slot.slot_id]:
            identity = id(block)
            if identity in used_block_ids:
                continue
            anchored[slot.slot_id] = block
            used_block_ids.add(identity)
            bind_required(index + 1)
            used_block_ids.remove(identity)
            anchored.pop(slot.slot_id, None)

    bind_required(0)
    required_satisfied = best_assignment is not None
    anchored = best_assignment or {}
    used_block_ids = {id(block) for block in anchored.values()}
    missing_required_slot_ids = (
        []
        if required_satisfied
        else [slot.slot_id for slot in required_slots]
    )
    text_assignments: dict[str, list[CourseBlock]] = {
        slot.slot_id: [anchored[slot.slot_id]]
        for slot in text_slots
        if slot.slot_id in anchored
    }
    remaining = [block for block in prose_blocks if id(block) not in used_block_ids]

    # Preserve semantic role binding for every additional block. Required and
    # optional role-specific slots are considered before generic body slots.
    explicit_slots = [slot for slot in text_slots if slot.source_roles]
    generic_slots = [slot for slot in text_slots if not slot.source_roles]
    for block in list(remaining):
        candidate = next(
            (
                slot
                for slot in explicit_slots
                if _text_slot_accepts_block(slot, block)
            ),
            None,
        )
        if candidate is None and generic_slots:
            candidate = generic_slots[0]
        if candidate is None:
            continue
        text_assignments.setdefault(candidate.slot_id, []).append(block)
        remaining.remove(block)

    covered_by_artifact = {
        id(block)
        for blocks in artifact_assignments.values()
        for block in blocks
    }
    covered_by_text = {
        id(block)
        for blocks in text_assignments.values()
        for block in blocks
    }
    unassigned_blocks = [
        block
        for block in source_blocks
        if id(block) not in covered_by_artifact
        and id(block) not in covered_by_text
    ]
    return _LayoutSourceAssignments(
        artifact_slots=artifact_assignments,
        text_slots=text_assignments,
        unassigned_blocks=unassigned_blocks,
        missing_required_slot_ids=missing_required_slot_ids,
    )


def _assigned_text_slot_blocks(
    layout: Any,
    source_blocks: list[CourseBlock],
) -> dict[str, list[CourseBlock]]:
    """Return the text portion of the centralized layout assignment."""

    return _layout_source_assignments(layout, source_blocks).text_slots


def _complete_slot_content(blocks: list[CourseBlock], slot_kind: str) -> str:
    """Compile the full visible source expression for fidelity comparison."""

    if slot_kind == "code":
        return "\n\n".join(
            str((block.payload or {}).get("_v6_code_chunk_content"))
            if "_v6_code_chunk_content" in (block.payload or {})
            else max(_code_candidates(block_source_text(block)), key=len).strip("\n")
            for block in blocks
            if block_source_text(block)
        )
    if slot_kind == "table":
        return _normalize_markdown_table("\n".join(
            block_source_text(block) for block in blocks
        )).rstrip()
    if slot_kind == "steps":
        return "\n".join(
            _complete_ordered_step_item(heading, details)
            for block in blocks
            for heading, details in _ordered_step_groups(_prose_source_text(block))
        ).rstrip()
    if slot_kind == "items":
        return "\n".join(
            _visible_prose_text(re.sub(
                r"^\s*(?:#{1,6}\s+|[-*+] |\d+[.)]\s*)",
                "",
                line,
            )).strip()
            for block in blocks
            for line in _prose_source_text(block).splitlines()
            if line.strip()
        ).rstrip()
    if slot_kind == "body":
        return "\n\n".join(
            _prose_source_text(block).strip()
            for block in blocks
            if _prose_source_text(block).strip()
        )
    return ""


def _slot_requires_pagination(slot: Any, blocks: list[CourseBlock]) -> bool:
    if not blocks or slot.slot_kind not in {"body", "items", "steps", "code"}:
        return False
    complete = _complete_slot_content(blocks, slot.slot_kind)
    try:
        bounded = _bounded_slot_content(
            blocks,
            slot_kind=slot.slot_kind,
            max_chars=slot.max_chars,
            max_items=slot.max_items,
            max_lines=slot.max_lines,
            max_rows=slot.max_rows,
            capacity_profile=getattr(slot, "capacity_profile", ""),
        )
    except ValueError as error:
        if str(error) != "template_slot_capacity_exceeded":
            raise
        return True
    return bounded != complete


def _split_blocks_for_slot(
    blocks: list[CourseBlock],
    *,
    slot: Any,
) -> list[CourseBlock]:
    fragments: list[CourseBlock] = []
    for block in blocks:
        if slot.slot_kind == "code":
            fragments.extend(_split_artifact_block(
                block,
                slot_kind="code",
                max_chars=slot.max_chars,
                max_lines=slot.max_lines,
                max_rows=slot.max_rows,
            ))
        else:
            fragments.extend(_split_text_block_for_slot(
                block,
                slot_kind=slot.slot_kind,
                max_chars=slot.max_chars,
                max_items=slot.max_items,
                max_lines=slot.max_lines,
                capacity_profile=getattr(slot, "capacity_profile", ""),
            ))
    return fragments


def _declared_continuation_layouts(
    template: TemplateLayoutPackContractV1,
    layout: Any,
) -> list[Any]:
    """Resolve only continuations explicitly published by the template contract."""

    layouts: list[Any] = []
    for slug in layout.safe_continuation_layout_slugs:
        try:
            layout_id = template.layout_id(slug)
        except KeyError:
            continue
        candidate = template.get_layout(layout_id)
        if candidate is not None:
            layouts.append(candidate)
    return layouts


def _layout_accepts_complete_blocks(
    layout: Any,
    source_blocks: list[CourseBlock],
) -> bool:
    """Check a continuation without truncation or bypassing required slots."""

    required_artifacts = {
        kind
        for block in source_blocks
        for kind in block_artifact_kinds(block)
    }
    if required_artifacts and not required_artifacts.issubset(
        set(layout.artifact_kinds)
    ):
        return False
    if not _layout_supports_required_slot_kinds(
        layout,
        source_required_slot_kinds(source_blocks),
    ):
        return False
    try:
        regions = _materialize_template_regions(
            page_id="continuation-contract-probe",
            title="",
            layout=layout,
            source_blocks=source_blocks,
        )
    except V6BuildError:
        return False
    return not _first_incomplete_visible_prose_block(source_blocks, regions)


def _source_can_fill_pending_visual(layout: Any, source_blocks: list[CourseBlock]) -> bool:
    """Prove a future visual decision has a real, compatible source basis."""

    available_artifacts = {
        kind
        for block in source_blocks
        for kind in block_artifact_kinds(block)
    }
    supported = set(layout.artifact_kinds)
    if available_artifacts.intersection(supported):
        return True
    if "image" in supported and any(block.asset_refs for block in source_blocks):
        return True
    if "diagram" in supported and any(
        _prose_source_text(block)
        for block in source_blocks
    ):
        return True
    return False


def _safe_continuation_for_blocks(
    *,
    page_id: str,
    template: TemplateLayoutPackContractV1,
    layout: Any,
    source_blocks: list[CourseBlock],
    purpose: str,
) -> Any:
    """Select a declared continuation that satisfies its own complete contract."""

    candidates = _declared_continuation_layouts(template, layout)
    candidates.sort(key=lambda candidate: (
        _layout_semantic_fallback_cost(candidate, source_blocks),
        candidate.template_layout_id == layout.template_layout_id,
        candidate.template_layout_id,
    ))
    for candidate in candidates:
        if _layout_accepts_complete_blocks(candidate, source_blocks):
            return candidate
    raise V6BuildError(
        stage="template",
        code="template_layout_unavailable",
        message=(
            f"The selected template declares no safe {purpose} continuation "
            "for the complete source content"
        ),
        page_id=page_id,
    )


def _safe_paginated_continuations_for_blocks(
    *,
    page_id: str,
    template: TemplateLayoutPackContractV1,
    layout: Any,
    source_blocks: list[CourseBlock],
    purpose: str,
) -> list[_SafePageMaterialization]:
    """Paginate an unmatched semantic source through a declared continuation."""

    candidates = _declared_continuation_layouts(template, layout)
    candidates.sort(
        key=lambda candidate: (
            _layout_semantic_fallback_cost(candidate, source_blocks),
            candidate.template_layout_id == layout.template_layout_id,
            candidate.template_layout_id,
        )
    )
    for candidate in candidates:
        try:
            materializations = _safe_artifact_page_blocks(
                page_id=f"{page_id}--{purpose}",
                template=template,
                layout=candidate,
                source_blocks=source_blocks,
                story_summary="",
            )
        except V6BuildError:
            continue
        if all(
            _layout_accepts_complete_blocks(
                materialization.layout,
                materialization.source_blocks,
            )
            for materialization in materializations
        ):
            return materializations
    raise V6BuildError(
        stage="template",
        code="template_layout_unavailable",
        message=(
            f"The selected template declares no safe paginated {purpose} "
            "continuation for the complete source content"
        ),
        page_id=page_id,
    )


def _required_support_page_blocks(
    *,
    page_id: str,
    layout: Any,
    support_source_blocks: list[CourseBlock],
) -> list[list[CourseBlock]]:
    """Split one required semantic support slot without duplicating source content."""

    required_slots = [
        slot
        for slot in layout.slots
        if slot.required and slot.slot_kind in {"body", "items", "steps"}
    ]
    if not required_slots:
        return []
    if len(required_slots) != 1:
        raise V6BuildError(
            stage="template",
            code="template_continuation_contract_invalid",
            message=(
                "Lossless multi-slot pagination requires exactly one required "
                "semantic support slot"
            ),
            page_id=page_id,
        )
    slot = required_slots[0]
    matching_blocks = _assigned_text_slot_blocks(
        layout,
        support_source_blocks,
    ).get(slot.slot_id, [])
    if not matching_blocks:
        return []
    try:
        return [
            [fragment]
            for fragment in _split_blocks_for_slot(matching_blocks, slot=slot)
        ]
    except ValueError as error:
        raise V6BuildError(
            stage="template",
            code="template_slot_capacity_exceeded",
            message=f"A complete semantic unit exceeds template slot {slot.slot_id}",
            page_id=page_id,
        ) from error


def _assert_source_driven_pagination_progress(
    *,
    page_id: str,
    source_blocks: list[CourseBlock],
    materializations: list[_SafePageMaterialization],
) -> None:
    """Guard non-progress without imposing a product-level slide-count cap."""

    if not materializations:
        raise V6BuildError(
            stage="template",
            code="slide_safety_limit_exceeded",
            message="Lossless pagination produced no materialized page",
            page_id=page_id,
        )
    source_units = sum(
        max(1, len(block_source_text(block)))
        for block in source_blocks
    )
    if len(materializations) > max(1, source_units):
        raise V6BuildError(
            stage="template",
            code="slide_safety_limit_exceeded",
            message=(
                "Lossless pagination did not make source-driven progress; "
                "the generated page count exceeds the available source units"
            ),
            page_id=page_id,
        )


def _safe_artifact_page_blocks(
    *,
    page_id: str,
    template: TemplateLayoutPackContractV1,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
) -> list[_SafePageMaterialization]:
    """Paginate source losslessly; page count is content-driven, not business-capped."""

    artifact_slot = next(
        (
            slot
            for slot in layout.slots
            if slot.slot_kind in {"code", "formula", "table"}
            and any(_block_matches_slot(block, slot.slot_kind) for block in source_blocks)
        ),
        None,
    )
    if artifact_slot is None:
        assignments = _layout_source_assignments(layout, source_blocks)
        if assignments.missing_required_slot_ids:
            raise V6BuildError(
                stage="template",
                code="template_required_slot_unfilled",
                message=(
                    "Required template slots have no distinct source-backed "
                    "content: "
                    + ", ".join(assignments.missing_required_slot_ids)
                ),
                page_id=page_id,
            )
        text_slots = [
            slot
            for slot in layout.slots
            if slot.slot_kind in {"body", "items", "steps"}
        ]
        # A one-slot continuation is already an order-safe linear container.
        # Keep the compact packing path below; multi-slot pages need an anchor
        # per required meaning and defer overflow through a larger declared
        # continuation rather than pre-splitting every companion at the
        # smaller origin-slot capacity.
        if len(text_slots) > 1:
            main_blocks: list[CourseBlock] = []
            optional_main_blocks: list[CourseBlock] = []
            deferred_blocks: list[CourseBlock] = []
            for slot in text_slots:
                slot_blocks = assignments.text_slots.get(slot.slot_id, [])
                if not slot_blocks:
                    continue
                if not _slot_requires_pagination(slot, slot_blocks):
                    main_blocks.extend(slot_blocks)
                    if not slot.required:
                        optional_main_blocks.extend(slot_blocks)
                    continue
                if not slot.required:
                    deferred_blocks.extend(slot_blocks)
                    continue
                anchor = slot_blocks[0]
                try:
                    anchor_fragments = _split_blocks_for_slot([anchor], slot=slot)
                except ValueError as error:
                    raise V6BuildError(
                        stage="template",
                        code="template_slot_capacity_exceeded",
                        message=(
                            f"A complete semantic unit exceeds template slot {slot.slot_id}"
                        ),
                        page_id=page_id,
                    ) from error
                main_blocks.append(anchor_fragments[0])
                deferred_blocks.extend(slot_blocks[1:])
                deferred_blocks.extend(anchor_fragments[1:])

            main_blocks.extend(
                block
                for slot_blocks in assignments.artifact_slots.values()
                for block in slot_blocks
            )
            deferred_blocks.extend(assignments.unassigned_blocks)
            main_blocks = sorted(
                {id(block): block for block in main_blocks}.values(),
                key=lambda block: (block.position, block.block_id),
            )
            if deferred_blocks and optional_main_blocks:
                first_deferred_position = min(
                    block.position for block in deferred_blocks
                )
                movable_optional_ids = {
                    id(block)
                    for block in optional_main_blocks
                    if block.position > first_deferred_position
                }
                if movable_optional_ids:
                    deferred_blocks.extend(
                        block
                        for block in main_blocks
                        if id(block) in movable_optional_ids
                    )
                    main_blocks = [
                        block
                        for block in main_blocks
                        if id(block) not in movable_optional_ids
                    ]
            main_ids = {id(block) for block in main_blocks}
            main_block_ids = {block.block_id for block in main_blocks}
            deferred_blocks = [
                block
                for block in deferred_blocks
                if id(block) not in main_ids
            ]
            min_main_position = min(block.position for block in main_blocks)
            max_main_position = max(block.position for block in main_blocks)
            before = sorted(
                [
                    block
                    for block in deferred_blocks
                    if block.block_id not in main_block_ids
                    and block.position < min_main_position
                ],
                key=lambda block: (block.position, block.block_id),
            )
            after = sorted(
                [
                    block
                    for block in deferred_blocks
                    if block.block_id in main_block_ids
                    or block.position >= max_main_position
                ],
                key=lambda block: (block.position, block.block_id),
            )
            unsafe_middle = [
                block
                for block in deferred_blocks
                if block.block_id not in main_block_ids
                and min_main_position <= block.position < max_main_position
            ]
            if unsafe_middle:
                raise V6BuildError(
                    stage="template",
                    code="template_layout_unavailable",
                    message=(
                        "The selected multi-slot layout cannot preserve frozen source "
                        "order through its declared continuations"
                    ),
                    page_id=page_id,
                )

            def continuation_groups(blocks: list[CourseBlock]) -> list[list[CourseBlock]]:
                groups: list[list[CourseBlock]] = []
                for block in blocks:
                    if groups and groups[-1][0].block_id == block.block_id:
                        groups[-1].append(block)
                    else:
                        groups.append([block])
                return groups

            before_pages = [
                page
                for group_index, group in enumerate(continuation_groups(before), start=1)
                for page in _safe_paginated_continuations_for_blocks(
                    page_id=f"{page_id}--leading-{group_index}",
                    template=template,
                    layout=layout,
                    source_blocks=group,
                    purpose="leading-semantic",
                )
            ]
            after_pages = [
                page
                for group_index, group in enumerate(continuation_groups(after), start=1)
                for page in _safe_paginated_continuations_for_blocks(
                    page_id=f"{page_id}--trailing-{group_index}",
                    template=template,
                    layout=layout,
                    source_blocks=group,
                    purpose="trailing-semantic",
                )
            ]
            materializations = [
                *before_pages,
                _SafePageMaterialization(layout=layout, source_blocks=main_blocks),
                *after_pages,
            ]
            _assert_source_driven_pagination_progress(
                page_id=page_id,
                source_blocks=source_blocks,
                materializations=materializations,
            )
            return materializations

        chunks_by_slot: dict[str, list[list[CourseBlock]]] = {}
        for slot in text_slots:
            slot_blocks = assignments.text_slots.get(slot.slot_id, [])
            if not slot_blocks:
                chunks_by_slot[slot.slot_id] = []
                continue
            try:
                chunks_by_slot[slot.slot_id] = (
                    [[fragment] for fragment in _split_blocks_for_slot(
                        slot_blocks,
                        slot=slot,
                    )]
                    if _slot_requires_pagination(slot, slot_blocks)
                    else [slot_blocks]
                )
            except ValueError as error:
                if (
                    str(error) == "template_slot_capacity_exceeded"
                    and _declared_continuation_layouts(template, layout)
                ):
                    materializations = _safe_paginated_continuations_for_blocks(
                        page_id=page_id,
                        template=template,
                        layout=layout,
                        source_blocks=source_blocks,
                        purpose="geometry",
                    )
                    _assert_source_driven_pagination_progress(
                        page_id=page_id,
                        source_blocks=source_blocks,
                        materializations=materializations,
                    )
                    return materializations
                raise V6BuildError(
                    stage="template",
                    code="template_slot_capacity_exceeded",
                    message=(
                        f"A complete semantic unit exceeds template slot {slot.slot_id}"
                    ),
                    page_id=page_id,
                ) from error

        first_page_blocks: list[CourseBlock] = []
        text_source_ids: set[str] = set()
        continuation_chunks: list[tuple[int, list[CourseBlock]]] = []
        for slot_index, slot in enumerate(text_slots):
            slot_chunks = chunks_by_slot.get(slot.slot_id, [])
            if slot_chunks:
                first_page_blocks.extend(slot_chunks[0])
                text_source_ids.update(
                    block.block_id
                    for chunk in slot_chunks
                    for block in chunk
                )
                continuation_chunks.extend(
                    (slot_index, chunk)
                    for chunk in slot_chunks[1:]
                )
        first_page_blocks.extend(
            block
            for slot_blocks in assignments.artifact_slots.values()
            for block in slot_blocks
            if block.block_id not in text_source_ids
        )
        first_page_blocks = sorted(
            {id(block): block for block in first_page_blocks}.values(),
            key=lambda block: (block.position, block.block_id),
        )
        materializations = [
            _SafePageMaterialization(
                layout=layout,
                source_blocks=first_page_blocks,
            )
        ]
        continuation_chunks.extend(
            (len(text_slots), [block])
            for block in assignments.unassigned_blocks
        )
        ordered_continuation_chunks = sorted(
            continuation_chunks,
            key=lambda item: (
                min(block.position for block in item[1]),
                item[0],
                min(block.block_id for block in item[1]),
            ),
        )
        if len(text_slots) == 1 and ordered_continuation_chunks:
            remaining_blocks = [
                block
                for _slot_index, blocks in ordered_continuation_chunks
                for block in blocks
            ]
            try:
                materializations.extend(
                    _safe_paginated_continuations_for_blocks(
                        page_id=f"{page_id}--semantic",
                        template=template,
                        layout=layout,
                        source_blocks=remaining_blocks,
                        purpose="semantic",
                    )
                )
            except V6BuildError:
                # Heterogeneous leftovers may need different declared
                # continuations. Preserve the established per-chunk fallback
                # rather than coercing them into one generic layout.
                for _slot_index, blocks in ordered_continuation_chunks:
                    materializations.append(_SafePageMaterialization(
                        layout=_safe_continuation_for_blocks(
                            page_id=page_id,
                            template=template,
                            layout=layout,
                            source_blocks=blocks,
                            purpose="semantic",
                        ),
                        source_blocks=blocks,
                    ))
        else:
            for _slot_index, blocks in ordered_continuation_chunks:
                materializations.append(_SafePageMaterialization(
                    layout=_safe_continuation_for_blocks(
                        page_id=page_id,
                        template=template,
                        layout=layout,
                        source_blocks=blocks,
                        purpose="semantic",
                    ),
                    source_blocks=blocks,
                ))
        _assert_source_driven_pagination_progress(
            page_id=page_id,
            source_blocks=source_blocks,
            materializations=materializations,
        )
        return materializations
    artifact_blocks = [
        block
        for block in source_blocks
        if _block_matches_slot(block, artifact_slot.slot_kind)
    ]
    artifact_ids = {block.block_id for block in artifact_blocks}
    non_artifact_blocks = [
        block for block in source_blocks if block.block_id not in artifact_ids
    ]
    split_artifact_first_page = bool(
        non_artifact_blocks or _visible_prose_text(story_summary)
    )
    adaptive_table = bool(
        artifact_slot.slot_kind == "table"
        and (artifact_slot.split_wrapped_lines or artifact_slot.full_wrapped_lines)
        and artifact_slot.full_column_chars
    )
    adaptive_code = bool(
        artifact_slot.slot_kind == "code"
        and (
            getattr(artifact_slot, "continuation_max_chars", 0)
            or getattr(artifact_slot, "continuation_max_lines", 0)
        )
    )
    artifact_chunks: list[CourseBlock] = []
    try:
        if adaptive_table:
            for block in artifact_blocks:
                artifact_chunks.extend(
                    _split_table_block_for_layout_variants(
                        block,
                        slot=artifact_slot,
                        split_first_page=split_artifact_first_page,
                    )
                )
        elif adaptive_code:
            for block in artifact_blocks:
                artifact_chunks.extend(_split_code_block_for_layout_variants(
                    block,
                    slot=artifact_slot,
                    split_first_page=split_artifact_first_page,
                ))
        else:
            _bounded_slot_content(
                artifact_blocks,
                slot_kind=artifact_slot.slot_kind,
                max_chars=artifact_slot.max_chars,
                max_items=artifact_slot.max_items,
                max_lines=artifact_slot.max_lines,
                max_rows=artifact_slot.max_rows,
                capacity_profile=getattr(artifact_slot, "capacity_profile", ""),
            )
            for block in artifact_blocks:
                artifact_chunks.extend(_split_artifact_block(
                    block,
                    slot_kind=artifact_slot.slot_kind,
                    max_chars=artifact_slot.max_chars,
                    max_lines=artifact_slot.max_lines,
                    max_rows=artifact_slot.max_rows,
                ))
    except ValueError as error:
        if str(error) != "template_slot_capacity_exceeded":
            raise
        if (adaptive_table or adaptive_code) and not artifact_chunks:
            raise V6BuildError(
                stage="template",
                code="template_slot_capacity_exceeded",
                message=(
                    f"A single source line exceeds template slot "
                    f"{artifact_slot.slot_id}"
                ),
                page_id=page_id,
            ) from error
    if layout.layout_slug not in set(layout.safe_continuation_layout_slugs):
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message="The selected template layout declares no safe artifact continuation",
            page_id=page_id,
        )
    if not artifact_chunks:
        try:
            for block in artifact_blocks:
                artifact_chunks.extend(
                    _split_artifact_block(
                        block,
                        slot_kind=artifact_slot.slot_kind,
                        max_chars=artifact_slot.max_chars,
                        max_lines=artifact_slot.max_lines,
                        max_rows=artifact_slot.max_rows,
                    )
                )
        except ValueError as error:
            raise V6BuildError(
                stage="template",
                code="template_slot_capacity_exceeded",
                message=(
                    f"A single source line exceeds template slot "
                    f"{artifact_slot.slot_id}"
                ),
                page_id=page_id,
            ) from error
    lost_artifact_prose_blocks = [
        _block_with_prose_excerpt(block, _artifact_free_prose_text(block))
        for block in artifact_blocks
        if _artifact_free_prose_text(block)
        and not any(
            chunk.block_id == block.block_id
            and _artifact_free_prose_text(chunk) == _artifact_free_prose_text(block)
            for chunk in artifact_chunks
        )
    ]
    support_slots = [
        slot
        for slot in layout.slots
        if slot.slot_kind in {"body", "items", "steps"}
    ]
    required_support = any(slot.required for slot in support_slots)
    first_artifact_requires_exclusive_page = bool(
        adaptive_table
        and artifact_chunks
        and _table_fragment_requires_exclusive_page(
            artifact_chunks[0],
            slot=artifact_slot,
            split_first_page=split_artifact_first_page,
        )
    )
    uncovered_artifact_prose_blocks = list(lost_artifact_prose_blocks)
    if story_summary and not required_support:
        normalized_summary = re.sub(
            r"\s+",
            "",
            _visible_prose_text(story_summary),
        ).casefold()
        uncovered_artifact_prose_blocks = [
            _block_with_prose_excerpt(block, _artifact_free_prose_text(block))
            for block in artifact_blocks
            if _artifact_free_prose_text(block)
            and not (
                (normalized_prose := re.sub(
                    r"\s+",
                    "",
                    _visible_prose_text(_artifact_free_prose_text(block)),
                ).casefold())
                and normalized_prose in normalized_summary
            )
        ]
    pairable_artifact_prose_blocks: list[CourseBlock] = []
    if not required_support and uncovered_artifact_prose_blocks:
        optional_support_slots = [
            slot for slot in support_slots if not slot.required
        ]

        def optional_support_fits(candidates: list[CourseBlock]) -> bool:
            assignments = _layout_source_assignments(layout, candidates)
            assigned_identities = {
                id(block)
                for slot in optional_support_slots
                for block in assignments.text_slots.get(slot.slot_id, [])
            }
            if any(id(block) not in assigned_identities for block in candidates):
                return False
            for slot in optional_support_slots:
                slot_blocks = assignments.text_slots.get(slot.slot_id, [])
                if not slot_blocks:
                    continue
                try:
                    _bounded_slot_content(
                        slot_blocks,
                        slot_kind=slot.slot_kind,
                        max_chars=slot.max_chars,
                        max_items=slot.max_items,
                        max_lines=slot.max_lines,
                        max_rows=slot.max_rows,
                        capacity_profile=getattr(slot, "capacity_profile", ""),
                    )
                except ValueError:
                    return False
            return bool(candidates)

        for candidate in uncovered_artifact_prose_blocks:
            trial = [*pairable_artifact_prose_blocks, candidate]
            if optional_support_fits(trial):
                pairable_artifact_prose_blocks = trial
        pairable_identities = {
            id(block) for block in pairable_artifact_prose_blocks
        }
        uncovered_artifact_prose_blocks = [
            block
            for block in uncovered_artifact_prose_blocks
            if id(block) not in pairable_identities
        ]
    support_source_blocks = [
        *non_artifact_blocks,
        *uncovered_artifact_prose_blocks,
    ]
    support_assignments = _layout_source_assignments(
        layout,
        support_source_blocks,
    )
    overflowing_support_slots = [
        slot
        for slot in support_slots
        if _slot_requires_pagination(
            slot,
            _slot_source_blocks(slot, support_source_blocks),
        )
    ]
    separate_support = bool(
        support_source_blocks
        and not required_support
        and "content-stack" in set(layout.safe_continuation_layout_slugs)
        and (
            bool(story_summary)
            or bool(lost_artifact_prose_blocks)
            or bool(overflowing_support_slots)
            or bool(support_assignments.unassigned_blocks)
        )
    )
    support_materializations: list[_SafePageMaterialization] = []
    artifact_support_blocks = [
        *pairable_artifact_prose_blocks,
        *support_source_blocks,
    ]
    if separate_support:
        support_layout = template.get_layout(template.layout_id("content-stack"))
        if support_layout is None:
            raise V6BuildError(
                stage="template",
                code="template_layout_unavailable",
                message="The template has no source-complete support continuation",
                page_id=page_id,
            )
        support_materializations = _safe_artifact_page_blocks(
            page_id=f"{page_id}--support",
            template=template,
            layout=support_layout,
            source_blocks=support_source_blocks,
            story_summary="",
        )
        artifact_support_blocks = pairable_artifact_prose_blocks

    if required_support and support_source_blocks:
        support_pages = _required_support_page_blocks(
            page_id=page_id,
            layout=layout,
            support_source_blocks=support_source_blocks,
        )
        if not support_pages:
            raise V6BuildError(
                stage="template",
                code="template_required_slot_unfilled",
                message="Required semantic support has no source-backed content",
                page_id=page_id,
            )
        required_support_ids = {
            block.block_id
            for blocks in support_pages
            for block in blocks
        }
        unmatched_support_blocks = [
            block
            for block in support_source_blocks
            if block.block_id not in required_support_ids
        ]
        unmatched_support_continuations = (
            _safe_paginated_continuations_for_blocks(
                page_id=page_id,
                template=template,
                layout=layout,
                source_blocks=unmatched_support_blocks,
                purpose="semantic-support",
            )
            if unmatched_support_blocks
            else []
        )
        if first_artifact_requires_exclusive_page:
            support_continuations = [
                _SafePageMaterialization(
                    layout=_safe_continuation_for_blocks(
                        page_id=page_id,
                        template=template,
                        layout=layout,
                        source_blocks=blocks,
                        purpose="semantic support",
                    ),
                    source_blocks=blocks,
                )
                for blocks in support_pages
            ]
            artifact_continuations = [
                _SafePageMaterialization(
                    layout=_safe_continuation_for_blocks(
                        page_id=page_id,
                        template=template,
                        layout=layout,
                        source_blocks=[chunk],
                        purpose="artifact",
                    ),
                    source_blocks=[chunk],
                )
                for chunk in artifact_chunks
            ]
            source_order = {
                block.block_id: index
                for index, block in enumerate(source_blocks)
            }
            materializations = sorted(
                [
                    *support_continuations,
                    *unmatched_support_continuations,
                    *artifact_continuations,
                ],
                key=lambda materialization: min(
                    source_order.get(block.block_id, len(source_order))
                    for block in materialization.source_blocks
                ),
            )
            _assert_source_driven_pagination_progress(
                page_id=page_id,
                source_blocks=source_blocks,
                materializations=materializations,
            )
            return materializations

        paired_blocks = sorted(
            [*support_pages[0], artifact_chunks[0]],
            key=lambda block: (block.position, block.block_id),
        )
        paired = _SafePageMaterialization(
            layout=layout,
            source_blocks=paired_blocks,
        )
        remaining_support = support_pages[1:]
        remaining_artifacts = artifact_chunks[1:]
        support_continuations = [
            _SafePageMaterialization(
                layout=_safe_continuation_for_blocks(
                    page_id=page_id,
                    template=template,
                    layout=layout,
                    source_blocks=blocks,
                    purpose="semantic support",
                ),
                source_blocks=blocks,
            )
            for blocks in remaining_support
        ]
        artifact_continuations = [
            _SafePageMaterialization(
                layout=_safe_continuation_for_blocks(
                    page_id=page_id,
                    template=template,
                    layout=layout,
                    source_blocks=[chunk],
                    purpose="artifact",
                ),
                source_blocks=[chunk],
            )
            for chunk in remaining_artifacts
        ]
        materializations = [
            paired,
            *support_continuations,
            *unmatched_support_continuations,
            *artifact_continuations,
        ]
        _assert_source_driven_pagination_progress(
            page_id=page_id,
            source_blocks=source_blocks,
            materializations=materializations,
        )
        return materializations

    artifact_materializations = [
        _SafePageMaterialization(
            layout=layout,
            source_blocks=sorted(
                [
                    *(
                        artifact_support_blocks
                        if index == 0 or required_support
                        else []
                    ),
                    chunk,
                ],
                key=lambda block: (block.position, block.block_id),
            ),
        )
        for index, chunk in enumerate(artifact_chunks)
    ]
    source_order = {
        block.block_id: index
        for index, block in enumerate(source_blocks)
    }
    # A page can contain semantic support on both sides of an artifact.  Order
    # each concrete continuation by its first frozen-source block instead of
    # moving the entire support group before or after the artifact group; the
    # latter made a trailing feedback block appear before an earlier table.
    materializations = sorted(
        [*artifact_materializations, *support_materializations],
        key=lambda materialization: min(
            source_order.get(block.block_id, len(source_order))
            for block in materialization.source_blocks
        ),
    )
    _assert_source_driven_pagination_progress(
        page_id=page_id,
        source_blocks=source_blocks,
        materializations=materializations,
    )
    return materializations


_CONTINUATION_FORMULA_RE = re.compile(
    r"\$\$(.+?)\$\$|(?<!\\)\$(?!\$)(.+?)(?<!\\)\$(?!\$)|"
    r"\\\[(.+?)\\\]",
    re.S,
)


def _bounded_source_title_windows(value: str, limit: int) -> list[str]:
    """Extract several complete, source-native title windows from long prose."""

    fragment = " ".join(str(value or "").split()).strip("，,：:、| ")
    fragment = re.sub(r"^\d+[.)、]\s*", "", fragment)
    if len(fragment) < 4:
        return []
    if len(fragment) <= limit:
        return [] if _title_is_incomplete(fragment) else [fragment]

    words = fragment.split()
    candidates: list[str] = []
    if len(words) > 1:
        for start in range(len(words)):
            selected: list[str] = []
            for word in words[start:]:
                candidate = " ".join([*selected, word])
                if len(candidate) > limit:
                    break
                selected.append(word)
            while selected:
                candidate = " ".join(selected).strip("，,：:、| ")
                if 4 <= len(candidate) <= limit and not _title_is_incomplete(candidate):
                    if candidate not in candidates:
                        candidates.append(candidate)
                    break
                selected.pop()
            if len(candidates) >= 8:
                break
    else:
        candidate = fragment[:limit].strip("，,：:、| ")
        while candidate and _title_is_incomplete(candidate):
            candidate = candidate[:-1].rstrip()
        if len(candidate) >= 4:
            candidates.append(candidate)
    return candidates


def _continuation_title_candidates(
    blocks: list[CourseBlock],
    *,
    capacity: int,
) -> list[str]:
    """Extract complete source-backed titles for compiler-created pages."""

    limit = max(4, capacity or 72)
    formula_candidates: list[str] = []
    code_candidates: list[str] = []
    table_candidates: list[str] = []
    prose_candidates: list[str] = []
    for block in blocks:
        source = block_source_text(block)
        presentation = block_presentation_text(block) or source
        table_rows = [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in source.splitlines()
            if line.strip().startswith("|")
            and line.strip().endswith("|")
            and not re.fullmatch(r"[|:\-\s]+", line.strip())
        ]
        for row in table_rows[1:] if len(table_rows) > 1 else []:
            candidate = str(row[0] if row else "").strip()
            if (
                4 <= len(candidate) <= limit
                and candidate not in table_candidates
            ):
                table_candidates.append(candidate)
        for code_match in re.finditer(
            r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n(.*?)```",
            source,
            flags=re.S,
        ):
            for raw_line in code_match.group(1).splitlines():
                candidate = raw_line.strip()
                if (
                    4 <= len(candidate) <= limit
                    and re.search(r"[A-Za-z0-9_]", candidate)
                    and candidate not in code_candidates
                ):
                    code_candidates.append(candidate)
        for match in _CONTINUATION_FORMULA_RE.finditer(source):
            expression = next(
                (group.strip() for group in match.groups() if group and group.strip()),
                "",
            )
            if not expression:
                continue
            relation_parts = re.split(r"\\approx|≈|=", expression)
            if len(relation_parts) >= 3:
                relation = r"\approx" if re.search(r"\\approx|≈", expression) else "="
                compact = (
                    f"${relation_parts[0].strip()} {relation} "
                    f"{relation_parts[-1].strip()}$"
                )
                if (
                    4 <= len(compact) <= limit
                    and compact not in formula_candidates
                ):
                    formula_candidates.append(compact)
            candidate = f"${expression}$"
            if len(candidate) <= limit and candidate not in formula_candidates:
                formula_candidates.append(candidate)
        cleaned = re.sub(r"```.*?```", "", presentation, flags=re.S)
        cleaned = _CONTINUATION_FORMULA_RE.sub(" ", cleaned)
        cleaned = re.sub(r"(?m)^\s*#{1,6}\s+", "", cleaned)
        cleaned = re.sub(r"(?<!\\)(?:\*\*|__|`)", "", cleaned)
        for fragment in re.split(r"[\n。！？!?；;：:，,]", cleaned):
            candidate = " ".join(fragment.split()).strip("，,：:、| ")
            candidate = re.sub(r"^\d+[.)、]\s*", "", candidate)
            if (
                4 <= len(candidate) <= limit
                and not _title_is_incomplete(candidate)
                and candidate not in prose_candidates
            ):
                prose_candidates.append(candidate)
            for window in _bounded_source_title_windows(fragment, limit):
                if window not in prose_candidates:
                    prose_candidates.append(window)
    # A formula page should be named by its strongest equation rather than by
    # a repeated parent-page heading. Equations with relations carry more
    # teaching meaning than isolated symbols.
    formula_candidates.sort(
        key=lambda value: (
            not any(operator in value for operator in ("=", "≤", "≥", "<", ">")),
            -len(value),
        )
    )
    return [
        *formula_candidates,
        *code_candidates,
        *table_candidates,
        *prose_candidates,
    ]


def _continuation_title(
    title: str,
    index: int,
    count: int,
    title_slot: Any,
    blocks: list[CourseBlock],
    used_title_keys: set[str],
    *,
    page_id: str = "",
) -> str:
    """Name each continuation with a distinct, source-backed teaching point."""

    _ = count
    if index == 1:
        selected = title
    else:
        selected = next(
            (
                candidate
                for candidate in _continuation_title_candidates(
                    blocks,
                    capacity=int(getattr(title_slot, "max_chars", 0) or 0),
                )
                if title_slot is None or _title_fits_slot(candidate, title_slot)
                if re.sub(r"\s+", "", candidate).casefold()
                not in used_title_keys
            ),
            "",
        )
        if not selected:
            raise V6BuildError(
                stage="quality",
                code="continuation_title_unavailable",
                message=(
                    "A compiler-created continuation has no distinct "
                    "source-backed teaching title"
                ),
                page_id=page_id,
            )
    used_title_keys.add(re.sub(r"\s+", "", selected).casefold())
    return selected


def _effective_slot_min_chars(slot: Any, blocks: list[CourseBlock]) -> int:
    declared = int(getattr(slot, "min_chars", 0) or 0)
    if declared <= 0:
        return 0
    # Density applies to what this slot can actually render. A rich-text source
    # may contain a short annotation plus a long fenced artifact; counting the
    # artifact toward a body slot's minimum makes a lossless support page fail
    # even after all available prose has been preserved.
    available = len(_visible_prose_text(
        _complete_slot_content(blocks, slot.slot_kind)
    ))
    return min(declared, available)


def _materialize_template_regions(
    *,
    page_id: str,
    title: str,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
    visual_decision: SlideVisualDecisionV2 | None = None,
    enforce_min_chars: bool = True,
    source_backed_visual_pending: bool = False,
) -> list[SlideRegionV6]:
    title_slot = next(
        (slot for slot in layout.slots if slot.slot_kind == "title"),
        None,
    )
    if title_slot and title and not _title_fits_slot(title, title_slot):
        raise V6BuildError(
            stage="template",
            code="template_title_capacity_exceeded",
            message=f"Page title exceeds the {title_slot.slot_id} slot capacity",
            page_id=page_id,
        )
    content_slots = [
        slot
        for slot in layout.slots
        if slot.slot_kind not in {"title", "eyebrow", "notes"}
    ]
    assignments = _layout_source_assignments(layout, source_blocks)
    assigned: dict[str, list[CourseBlock]] = {
        **assignments.artifact_slots,
        **assignments.text_slots,
    }
    text_slots = [
        slot
        for slot in content_slots
        if slot.slot_kind in {"body", "items", "steps"}
    ]

    summary_slot_id = ""
    summary_content = _visible_prose_text(story_summary)
    has_assigned_text_support = any(
        assignments.text_slots.get(slot.slot_id)
        for slot in text_slots
    )
    has_artifact_support = any(
        slot.slot_kind in {"code", "formula", "table", "visual"}
        for slot in content_slots
    )
    if (
        summary_content
        and has_artifact_support
        and len(text_slots) == 1
        and text_slots[0].slot_kind == "body"
    ):
        candidate_slot = text_slots[0]
        assigned_source = _complete_slot_content(
            assignments.text_slots.get(candidate_slot.slot_id, []),
            candidate_slot.slot_kind,
        )
        canonical_source = _canonical_visible_semantic_text(assigned_source)
        canonical_summary = _canonical_visible_semantic_text(summary_content)
        # A Story summary may enrich an artifact-only page, but it must never
        # consume a frozen prose fragment that the learner will not otherwise
        # see.  When prose is assigned to this slot, only a source-complete
        # summary may replace it; otherwise render the assigned source chunk.
        if not canonical_source or canonical_source in canonical_summary:
            summary_slot_id = candidate_slot.slot_id

    regions: list[SlideRegionV6] = []
    for slot in content_slots:
        slot_blocks = assigned.get(slot.slot_id, [])
        visual_decision_fills_slot = bool(
            slot.slot_kind == "visual"
            and (
                (
                    visual_decision is not None
                    and visual_decision.decision in set(layout.artifact_kinds)
                )
                or (
                    source_backed_visual_pending
                    and bool(source_blocks)
                    and bool(layout.artifact_kinds)
                )
            )
        )
        visual_renders_without_text_region = bool(
            slot.slot_kind == "visual"
            and visual_decision is not None
            and visual_decision.decision in {"diagram", "image", "experiment"}
        )
        slot_max_chars = slot.max_chars
        slot_max_lines = slot.max_lines
        if (
            slot.slot_kind == "code"
            and not summary_content
            and not has_assigned_text_support
        ):
            slot_max_chars = int(
                getattr(slot, "continuation_max_chars", 0) or slot.max_chars
            )
            slot_max_lines = int(
                getattr(slot, "continuation_max_lines", 0) or slot.max_lines
            )
        try:
            if visual_renders_without_text_region:
                # Diagram nodes and frozen source images are rendered by the
                # visual adapter itself.  Emitting the same source again as a
                # statement creates duplicate copy and can manufacture a
                # truncation ellipsis that is not present in the source.
                content = ""
            elif slot.slot_id == summary_slot_id:
                if slot.max_chars and len(summary_content) > slot.max_chars:
                    raise ValueError("template_slot_capacity_exceeded")
                content = summary_content
                slot_blocks = list(source_blocks)
                minimum_chars = _effective_slot_min_chars(slot, slot_blocks)
                if (
                    minimum_chars
                    and len(_visible_prose_text(content)) < minimum_chars
                ):
                    content = _bounded_slot_content(
                        slot_blocks,
                        slot_kind=slot.slot_kind,
                        max_chars=slot.max_chars,
                        max_items=slot.max_items,
                        max_lines=slot.max_lines,
                        max_rows=slot.max_rows,
                        capacity_profile=getattr(slot, "capacity_profile", ""),
                    )
            else:
                content = _bounded_slot_content(
                    slot_blocks,
                    slot_kind=slot.slot_kind,
                    max_chars=slot_max_chars,
                    max_items=slot.max_items,
                    max_lines=slot_max_lines,
                    max_rows=slot.max_rows,
                    supports_single_row_detail=bool(
                        slot.slot_kind == "table"
                        and getattr(slot, "split_wrapped_lines", 0)
                        and getattr(slot, "full_wrapped_lines", 0)
                        and getattr(slot, "full_column_chars", 0)
                    ),
                    capacity_profile=getattr(slot, "capacity_profile", ""),
                )
        except ValueError as error:
            if str(error) != "template_slot_capacity_exceeded":
                raise
            raise V6BuildError(
                stage="template",
                code="template_slot_capacity_exceeded",
                message=f"Source-backed content exceeds template slot {slot.slot_id}",
                page_id=page_id,
            ) from error
        if slot.required and not content and not visual_decision_fills_slot:
            raise V6BuildError(
                stage="template",
                code="template_required_slot_unfilled",
                message=f"Required template slot {slot.slot_id} has no source-backed content",
                page_id=page_id,
            )
        minimum_chars = _effective_slot_min_chars(slot, slot_blocks)
        if (
            enforce_min_chars
            and minimum_chars
            and len(_visible_prose_text(content)) < minimum_chars
        ):
            raise V6BuildError(
                stage="template",
                code="template_slot_underfilled",
                message=(
                    f"Source-backed content underfills template slot {slot.slot_id}"
                ),
                page_id=page_id,
            )
        if not content:
            continue
        region_metadata: dict[str, Any] = {}
        if slot.slot_kind == "code" and len(slot_blocks) == 1:
            payload = slot_blocks[0].payload or {}
            if payload.get("_v6_code_language"):
                region_metadata["code_language"] = str(
                    payload["_v6_code_language"]
                )
            if payload.get("_v6_code_start_line") is not None:
                region_metadata["code_start_line"] = int(
                    payload["_v6_code_start_line"]
                )
            if payload.get("_v6_code_end_line") is not None:
                region_metadata["code_end_line"] = int(
                    payload["_v6_code_end_line"]
                )
            if payload.get("_v6_code_chunk_index") is not None:
                region_metadata["code_chunk_index"] = int(
                    payload["_v6_code_chunk_index"]
                )
            if payload.get("_v6_code_chunk_count") is not None:
                region_metadata["code_chunk_count"] = int(
                    payload["_v6_code_chunk_count"]
                )
        regions.append(
            SlideRegionV6(
                region_id=f"{page_id}:{slot.slot_id}",
                slot_id=slot.slot_id,
                content_kind=slot.slot_kind,
                content=content,
                source_block_ids=list(dict.fromkeys(
                    block.block_id for block in slot_blocks
                )),
                source_asset_refs=list(
                    dict.fromkeys(
                        asset_ref
                        for block in slot_blocks
                        for asset_ref in block.asset_refs
                        if asset_ref
                    )
                ),
                metadata=region_metadata,
            )
        )
    visible_blocks = {
        block_id for region in regions for block_id in region.source_block_ids
    }
    if visual_decision is not None and visual_decision.decision == "diagram":
        visible_blocks.update(
            str(block_id)
            for node in visual_decision.visual_payload.get("nodes") or []
            if isinstance(node, dict) and str(node.get("label") or "").strip()
            for block_id in node.get("source_block_ids") or []
        )
    elif (
        visual_decision is not None
        and visual_decision.decision in {"image", "experiment"}
        and visual_decision.source_asset_ids
    ):
        visible_blocks.update(visual_decision.source_block_ids)
    elif source_backed_visual_pending:
        visible_blocks.update(
            block.block_id
            for slot in content_slots
            if slot.slot_kind == "visual"
            for block in assigned.get(slot.slot_id, [])
        )
    missing = [
        block.block_id
        for block in source_blocks
        if block.block_id not in visible_blocks
    ]
    if missing:
        raise V6BuildError(
            stage="template",
            code="template_source_slot_coverage_incomplete",
            message=f"Template slots did not visibly bind source blocks: {', '.join(missing)}",
            page_id=page_id,
        )
    return regions


def validate_layout_source_satisfiability(
    *,
    page_id: str,
    template: TemplateLayoutPackContractV1,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
    enforce_min_chars: bool = True,
) -> list[_SafePageMaterialization]:
    """Prove a layout and every continuation are source-backed and capacity-safe."""

    source_artifacts = {
        kind
        for block in source_blocks
        for kind in block_artifact_kinds(block)
    }
    if source_artifacts and not source_artifacts.issubset(set(layout.artifact_kinds)):
        raise V6BuildError(
            stage="template",
            code="template_layout_artifact_mismatch",
            message="Template layout cannot express every frozen source artifact",
            page_id=page_id,
        )
    if not _layout_supports_required_slot_kinds(
        layout,
        source_required_slot_kinds(source_blocks),
    ):
        raise V6BuildError(
            stage="template",
            code="template_layout_semantic_slot_mismatch",
            message="Template layout cannot express the frozen source structure",
            page_id=page_id,
        )

    assignments = _layout_source_assignments(layout, source_blocks)
    missing_required_artifact_slots = [
        slot.slot_id
        for slot in layout.slots
        if slot.required
        and slot.slot_kind in {"code", "formula", "table"}
        and not assignments.artifact_slots.get(slot.slot_id)
    ]
    if missing_required_artifact_slots:
        raise V6BuildError(
            stage="template",
            code="template_required_slot_unfilled",
            message=(
                "Required template slots have no source-backed artifact: "
                + ", ".join(missing_required_artifact_slots)
            ),
            page_id=page_id,
        )
    if assignments.missing_required_slot_ids:
        raise V6BuildError(
            stage="template",
            code="template_required_slot_unfilled",
            message=(
                "Required template slots have no distinct source-backed content: "
                + ", ".join(assignments.missing_required_slot_ids)
            ),
            page_id=page_id,
        )
    text_slots = [
        slot
        for slot in layout.slots
        if slot.slot_kind in {"body", "items", "steps"}
    ]
    incompatible = [
        block.block_id
        for block in assignments.unassigned_blocks
        if _prose_source_text(block)
    ]
    if (
        incompatible
        and any(slot.required for slot in text_slots)
        and all(slot.source_roles for slot in text_slots)
    ):
        raise V6BuildError(
            stage="template",
            code="template_source_slot_role_mismatch",
            message=(
                "Structured template slots cannot express source roles for blocks: "
                + ", ".join(incompatible)
            ),
            page_id=page_id,
        )
    materializations = _safe_artifact_page_blocks(
        page_id=page_id,
        template=template,
        layout=layout,
        source_blocks=source_blocks,
        story_summary=story_summary,
    )
    materialized_regions: list[SlideRegionV6] = []
    for index, materialization in enumerate(materializations):
        materialized_regions.extend(_materialize_template_regions(
            page_id=(
                page_id
                if index == 0
                else f"{page_id}--continuation-{index + 1}"
            ),
            title="",
            layout=materialization.layout,
            source_blocks=materialization.source_blocks,
            story_summary=(
                story_summary
                if index == 0
                and materialization.layout.template_layout_id
                == layout.template_layout_id
                else ""
            ),
            enforce_min_chars=enforce_min_chars,
            source_backed_visual_pending=_source_can_fill_pending_visual(
                materialization.layout,
                materialization.source_blocks,
            ),
        ))
    incomplete_block_id = _first_incomplete_visible_prose_block(
        source_blocks,
        materialized_regions,
    )
    if incomplete_block_id:
        raise V6BuildError(
            stage="template",
            code="template_source_semantic_fidelity_incomplete",
            message=(
                "Template text regions omit frozen source prose for block "
                f"{incomplete_block_id}"
            ),
            page_id=page_id,
            node_id=incomplete_block_id,
        )
    return materializations


def validate_story_template_text_slots(
    *,
    page_id: str,
    template: TemplateLayoutPackContractV1,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
    enforce_min_chars: bool = True,
) -> None:
    """Compatibility wrapper around the single cross-stage predicate."""

    validate_layout_source_satisfiability(
        page_id=page_id,
        template=template,
        layout=layout,
        source_blocks=source_blocks,
        story_summary=story_summary,
        enforce_min_chars=enforce_min_chars,
    )


def story_safe_page_slices(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
) -> list[dict[str, Any]]:
    """Enumerate contiguous source slices that a published template can render."""

    block_ids = list(unit.primary_block_ids)
    slices: list[dict[str, Any]] = []
    for start_index in range(len(block_ids)):
        for end_index in range(start_index + 1, len(block_ids) + 1):
            source_block_ids = block_ids[start_index:end_index]
            teaching_intent = page_teaching_intent(unit, source_block_ids)
            required_artifacts = page_artifact_kinds(unit, source_block_ids)
            source_blocks = graph_page_source_blocks(unit, source_block_ids)
            required_slot_kinds = source_required_slot_kinds(source_blocks)
            compatible_layout_ids: list[str] = []
            for layout in template.layouts:
                if teaching_intent not in layout.teaching_intents:
                    continue
                if required_artifacts and not required_artifacts.issubset(
                    set(layout.artifact_kinds)
                ):
                    continue
                if not _layout_supports_required_slot_kinds(
                    layout,
                    required_slot_kinds,
                ):
                    continue
                try:
                    validate_story_template_text_slots(
                        page_id="story-safe-slice",
                        template=template,
                        layout=layout,
                        source_blocks=source_blocks,
                        story_summary="",
                    )
                except V6BuildError:
                    continue
                compatible_layout_ids.append(layout.template_layout_id)
            if compatible_layout_ids:
                slices.append({
                    "start_index": start_index,
                    "end_index": end_index,
                    "source_block_ids": source_block_ids,
                    "teaching_intent": teaching_intent,
                    "artifact_kinds": sorted(required_artifacts),
                    "required_slot_kinds": sorted(required_slot_kinds),
                    "template_layout_ids": compatible_layout_ids,
                })
    return slices


def story_page_count_range(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
    *,
    safe_slices: list[dict[str, Any]] | None = None,
) -> list[int]:
    """Derive a compact LLM page budget from template-safe source partitions."""

    if safe_slices is None:
        safe_slices = story_safe_page_slices(unit, template)
    slice_edges = {
        (int(item["start_index"]), int(item["end_index"]))
        for item in safe_slices
    }
    reachable_counts: dict[int, set[int]] = {0: {0}}
    for end_index in range(1, len(unit.primary_block_ids) + 1):
        counts: set[int] = set()
        for start_index in range(end_index):
            if (start_index, end_index) not in slice_edges:
                continue
            counts.update(
                count + 1
                for count in reachable_counts.get(start_index, set())
            )
        if counts:
            reachable_counts[end_index] = counts
    feasible_counts = sorted(
        reachable_counts.get(len(unit.primary_block_ids), set())
    )
    if not feasible_counts:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=(
                "No contiguous template-safe partition covers teaching unit "
                f"{unit.teaching_unit_id}"
            ),
        )
    minimum_pages = feasible_counts[0]
    maximum_pages = feasible_counts[-1]
    return [minimum_pages, maximum_pages]


def story_safe_partition_options(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
    *,
    max_options_per_page_count: int = 12,
    safe_slices: list[dict[str, Any]] | None = None,
    allowed_page_count_range: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Compile safe slices into complete, ordered exact-cover choices for the LLM."""

    if safe_slices is None:
        safe_slices = story_safe_page_slices(unit, template)
    if allowed_page_count_range is None:
        allowed_page_count_range = story_page_count_range(
            unit,
            template,
            safe_slices=safe_slices,
        )
    slices_by_start: dict[int, list[dict[str, Any]]] = {}
    for item in safe_slices:
        slices_by_start.setdefault(int(item["start_index"]), []).append(item)
    for items in slices_by_start.values():
        items.sort(
            key=lambda item: (
                -int(item["end_index"]),
                tuple(item["source_block_ids"]),
            )
        )

    options: list[dict[str, Any]] = []
    source_count = len(unit.primary_block_ids)
    for target_page_count in range(
        allowed_page_count_range[0],
        allowed_page_count_range[1] + 1,
    ):
        matching_paths: list[list[dict[str, Any]]] = []

        def collect(position: int, path: list[dict[str, Any]]) -> None:
            if len(matching_paths) >= max_options_per_page_count:
                return
            remaining_pages = target_page_count - len(path)
            remaining_blocks = source_count - position
            if remaining_pages < 0 or remaining_blocks < remaining_pages:
                return
            if position == source_count:
                if len(path) == target_page_count:
                    matching_paths.append(list(path))
                return
            if len(path) >= target_page_count:
                return
            for item in slices_by_start.get(position, []):
                collect(int(item["end_index"]), [*path, item])

        collect(0, [])
        for path in matching_paths:
            pages = [
                {
                    "source_block_ids": list(item["source_block_ids"]),
                    "teaching_intent": str(item["teaching_intent"]),
                    "artifact_kinds": list(item["artifact_kinds"]),
                    "required_slot_kinds": list(item["required_slot_kinds"]),
                    "template_layout_ids": list(item["template_layout_ids"]),
                }
                for item in path
            ]
            options.append({
                "partition_id": stable_hash(
                    {
                        "teaching_unit_id": unit.teaching_unit_id,
                        "pages": pages,
                    },
                    prefix="safe_partition_",
                ),
                "page_count": len(pages),
                "pages": pages,
            })
    if not options:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=(
                "No complete template-safe partition option covers teaching unit "
                f"{unit.teaching_unit_id}"
            ),
        )
    return options


def _course_agenda_sections(document: CourseDocument) -> list[Any]:
    """Return ordered top-level sections that own formal source content."""

    section_by_id = {section.section_id: section for section in document.sections}
    relevant_ids = {
        block.section_id
        for block in _formal_blocks(document)
        if block.section_id in section_by_id
    }
    pending = list(relevant_ids)
    while pending:
        section = section_by_id.get(pending.pop())
        parent_id = str(section.parent_section_id or "") if section else ""
        if parent_id and parent_id in section_by_id and parent_id not in relevant_ids:
            relevant_ids.add(parent_id)
            pending.append(parent_id)
    ordered = sorted(
        (section_by_id[section_id] for section_id in relevant_ids),
        key=lambda section: (section.position, section.level, section.section_id),
    )
    return [
        section
        for section in ordered
        if not section.parent_section_id or section.parent_section_id not in relevant_ids
    ]


def _agenda_section_description(
    section: Any,
    *,
    per_entry_capacity: int,
) -> str:
    """Choose one complete source-owned descriptor without inventing copy."""

    title = _visible_prose_text(section.title).strip()
    attributes = section.attributes if isinstance(section.attributes, dict) else {}
    candidates = [
        str(section.learning_objective or ""),
        str(attributes.get("path_reason") or ""),
        str(attributes.get("learning_focus") or ""),
    ]
    canonical_title = _canonical_visible_semantic_text(title)
    for candidate in candidates:
        description = _visible_prose_text(candidate).strip()
        if not description:
            continue
        if _canonical_visible_semantic_text(description) == canonical_title:
            continue
        if _display_width_units(description) <= per_entry_capacity:
            return description
    return ""


def _compile_course_agenda_pages(
    document: CourseDocument,
    template: TemplateLayoutPackContractV1,
) -> list[SlidePageV6]:
    sections = _course_agenda_sections(document)
    if len(sections) < 2:
        return []
    layout = template.get_layout(template.layout_id("agenda-path"))
    if layout is None:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message="The published template does not provide a course agenda layout",
        )
    item_slot = next(
        (slot for slot in layout.slots if slot.slot_kind == "items"),
        None,
    )
    if item_slot is None:
        raise V6BuildError(
            stage="template",
            code="template_required_slot_unfilled",
            message="The course agenda layout has no ordered item slot",
        )
    max_items = int(item_slot.max_items or 6)
    max_chars = int(item_slot.max_chars or 180)
    per_entry_capacity = max(1, (max_chars * 2) // max(1, max_items))
    entries = [
        {
            "index": index,
            "title": _visible_prose_text(section.title).strip(),
            "description": _agenda_section_description(
                section,
                per_entry_capacity=per_entry_capacity,
            ),
            "source_section_ids": [section.section_id],
            "section": section,
        }
        for index, section in enumerate(sections, start=1)
    ]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def agenda_text(candidate: list[dict[str, Any]]) -> str:
        return "\n".join(
            "\n".join(
                value
                for value in (
                    str(item["title"]),
                    str(item["description"]),
                )
                if value
            )
            for item in candidate
        )

    for entry in entries:
        section = entry["section"]
        title = str(entry["title"])
        if not title:
            raise V6BuildError(
                stage="source",
                code="course_section_title_missing",
                message="A course section cannot be represented in the agenda",
                chapter_id=section.section_id,
            )
        candidate = [*current, entry]
        candidate_text = agenda_text(candidate)
        if current and (
            len(candidate) > max_items
            or (max_chars and len(candidate_text) > max_chars)
        ):
            chunks.append(current)
            current = [entry]
        else:
            current = candidate
        if max_chars and len(title) > max_chars:
            raise V6BuildError(
                stage="template",
                code="template_slot_capacity_exceeded",
                message="A course section title exceeds the agenda item capacity",
                chapter_id=section.section_id,
            )
    if current:
        chunks.append(current)
    if len(chunks) > 1:
        page_count = len(chunks)
        base_size, larger_pages = divmod(len(entries), page_count)
        sizes = [
            base_size + (1 if index < larger_pages else 0)
            for index in range(page_count)
        ]
        balanced: list[list[dict[str, Any]]] = []
        cursor = 0
        for size in sizes:
            balanced.append(entries[cursor: cursor + size])
            cursor += size
        if all(
            len(chunk) <= max_items
            and (not max_chars or len(agenda_text(chunk)) <= max_chars)
            for chunk in balanced
        ):
            chunks = balanced

    pages: list[SlidePageV6] = []
    for index, chunk in enumerate(chunks, start=1):
        page_id = f"course-agenda-{index}"
        section_ids = [str(entry["section"].section_id) for entry in chunk]
        content = "\n".join(
            str(entry["title"]) for entry in chunk
        )
        pages.append(SlidePageV6(
            page_id=page_id,
            page_ordinal=0,
            teaching_unit_id="course-agenda",
            title="课程目录" if index == 1 else f"课程目录（续 {index}）",
            resolved_layout=layout.template_layout_id,
            web_renderer_adapter=layout.web_renderer_adapter,
            pptx_renderer_adapter=layout.pptx_renderer_adapter,
            regions=[SlideRegionV6(
                region_id=f"{page_id}:{item_slot.slot_id}",
                slot_id=item_slot.slot_id,
                content_kind=item_slot.slot_kind,
                content=content,
                source_section_ids=section_ids,
                metadata={
                    "agenda_entries": [
                        {
                            key: value
                            for key, value in entry.items()
                            if key != "section"
                        }
                        for entry in chunk
                    ],
                },
            )],
            source_section_ids=section_ids,
            visual_decision=SlideVisualDecisionV2(
                page_id=page_id,
                decision="text_native",
                source_section_ids=section_ids,
                resolved_template_layout_id=layout.template_layout_id,
            ),
            speaker_notes=SlideSpeakerNotesV2(
                source_document_revision=document.document_revision,
                teaching_unit_id="course-agenda",
                source_section_ids=section_ids,
            ),
        ))
    return pages


def _compile_course_cover_page(
    document: CourseDocument,
    template: TemplateLayoutPackContractV1,
) -> SlidePageV6:
    """Build the source-bound course cover that owns the agenda entry point."""

    sections = _course_agenda_sections(document)
    if not sections:
        raise V6BuildError(
            stage="source",
            code="course_cover_source_binding_missing",
            message="The course cover requires at least one source section",
        )
    layout = template.get_layout(template.layout_id("cover-minimal"))
    if layout is None:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message="The published template does not provide a course cover layout",
        )
    title_slot = next(
        (slot for slot in layout.slots if slot.slot_kind == "title"),
        None,
    )
    if title_slot is None:
        raise V6BuildError(
            stage="template",
            code="template_required_slot_unfilled",
            message="The course cover layout is missing its title slot",
        )
    course_title = _visible_prose_text(document.title).strip()
    if not course_title:
        raise V6BuildError(
            stage="source",
            code="course_title_missing",
            message="The course cover requires a source course title",
        )
    if not _title_fits_slot(course_title, title_slot):
        raise V6BuildError(
            stage="template",
            code="template_title_capacity_exceeded",
            message="The complete course title exceeds the published cover capacity",
            page_id="course-cover",
        )
    section_ids = [section.section_id for section in sections]
    page_id = "course-cover"
    return SlidePageV6(
        page_id=page_id,
        page_ordinal=0,
        teaching_unit_id="course-cover",
        title=course_title,
        title_max_lines=int(title_slot.max_lines or 3),
        resolved_layout=layout.template_layout_id,
        web_renderer_adapter=layout.web_renderer_adapter,
        pptx_renderer_adapter=layout.pptx_renderer_adapter,
        regions=[SlideRegionV6(
            region_id=f"{page_id}:{title_slot.slot_id}",
            slot_id=title_slot.slot_id,
            content_kind=title_slot.slot_kind,
            content=course_title,
            source_section_ids=section_ids,
        )],
        source_section_ids=section_ids,
        visual_decision=SlideVisualDecisionV2(
            page_id=page_id,
            decision="text_native",
            source_section_ids=section_ids,
            resolved_template_layout_id=layout.template_layout_id,
        ),
        speaker_notes=SlideSpeakerNotesV2(
            source_document_revision=document.document_revision,
            teaching_unit_id="course-cover",
            source_section_ids=section_ids,
        ),
    )


def _complete_story_source_companion(
    unit: CoursePresentationUnitV1,
    source_block_ids: list[str],
    layout: Any,
) -> str:
    """Return the complete bound prose only when one body slot can render it."""

    body_slots = [slot for slot in layout.slots if slot.slot_kind == "body"]
    if len(body_slots) != 1:
        return ""
    source_blocks = graph_page_source_blocks(unit, source_block_ids)
    complete_source = _presentation_summary_text(
        _complete_slot_content(source_blocks, "body")
    ).strip()
    if not complete_source or _looks_like_markdown_table(complete_source):
        return ""
    slot = body_slots[0]
    if slot.max_chars and len(complete_source) > int(slot.max_chars):
        return ""
    if slot.max_lines and _prose_wrapped_line_cost(complete_source) > int(
        slot.max_lines
    ):
        return ""
    if not capacity_profile_text_fits(
        str(getattr(slot, "capacity_profile", "") or ""),
        complete_source,
    ):
        return ""
    return complete_source


def prepare_story_plan_for_final_compilation(
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> SlideStoryPlanV3:
    """Project incompatible optional companions before strict final validation."""

    units = _unit_map(graph)
    used_section_titles: set[str] = set()
    batches: list[SlideStoryBatchV3] = []
    for batch in story.batches:
        pages: list[SlideStoryPageV3] = []
        for page in batch.pages:
            layout = template.get_layout(page.template_layout_id)
            unit = units.get(page.teaching_unit_id)
            if layout is None or unit is None:
                pages.append(page)
                continue
            title_slot = next(
                (slot for slot in layout.slots if slot.slot_kind == "title"),
                None,
            )
            section_title_key = re.sub(
                r"\s+", "", str(unit.section_title or "")
            ).casefold()
            opens_formal_section = any(
                unit.primary_block_roles.get(block_id) == "objective"
                for block_id in page.source_block_ids
            )
            if (
                opens_formal_section
                and unit.section_title
                and section_title_key not in used_section_titles
                and (
                    title_slot is None
                    or _title_fits_slot(unit.section_title, title_slot)
                )
            ):
                page = page.model_copy(update={"title": unit.section_title})
                used_section_titles.add(section_title_key)
            summary = str(page.summary or "")
            body_slots = [
                slot for slot in layout.slots if slot.slot_kind == "body"
            ]
            page_source_text = _unit_source_text_for_blocks(
                unit,
                page.source_block_ids,
            )
            summary_requires_projection = bool(
                summary
                and (
                    _ELLIPSIS_MARKER_RE.search(summary)
                    or _presentation_summary_text(summary) != summary.strip()
                    or _looks_like_markdown_table(summary)
                    or bool(
                        _protected_tokens(summary)
                        - _protected_tokens(page_source_text)
                    )
                    or _semantic_grounding_ratio(summary, page_source_text) < 0.12
                    or (
                        len(body_slots) == 1
                        and body_slots[0].max_chars
                        and len(summary) > int(body_slots[0].max_chars)
                    )
                    or (
                        len(body_slots) == 1
                        and body_slots[0].min_chars
                        and len(_presentation_summary_text(summary))
                        < min(
                            int(body_slots[0].min_chars),
                            len(_presentation_summary_text(page_source_text)),
                        )
                    )
                )
            )
            if summary_requires_projection:
                page = page.model_copy(update={
                    "summary": _complete_story_source_companion(
                        unit,
                        page.source_block_ids,
                        layout,
                    ),
                })
            if not page.summary:
                pages.append(page)
                continue
            pages.append(page)
        batches.append(batch.model_copy(update={"pages": pages}))
    return story.model_copy(update={"batches": batches})


_ELLIPSIS_MARKER_RE = re.compile(r"…|(?<!\.)\.{3}(?!\.)")


def _region_is_audience_visible(page: SlidePageV6, region: SlideRegionV6) -> bool:
    return bool(
        region.content
        and not (
            region.content_kind == "visual"
            and page.visual_decision.decision in {"diagram", "image", "experiment"}
        )
    )


def _audience_visible_source_block_ids(page: SlidePageV6) -> set[str]:
    visible = {
        block_id
        for region in page.regions
        if _region_is_audience_visible(page, region)
        for block_id in region.source_block_ids
    }
    if page.visual_decision.decision == "diagram":
        visible.update(
            str(block_id)
            for node in page.visual_decision.visual_payload.get("nodes") or []
            if isinstance(node, dict) and str(node.get("label") or "").strip()
            for block_id in node.get("source_block_ids") or []
        )
    elif (
        page.visual_decision.decision in {"image", "experiment"}
        and page.visual_decision.source_asset_ids
    ):
        visible.update(page.visual_decision.source_block_ids)
    return visible


def _ellipsis_maps_to_frozen_source(value: str, source: str) -> bool:
    """Prove every visible ellipsis remains in its frozen source context."""

    if not _ELLIPSIS_MARKER_RE.search(str(value or "")):
        return True
    visible = " ".join(_presentation_summary_text(value).split())
    frozen = " ".join(_presentation_summary_text(source).split())
    if not visible or not frozen:
        return False
    if visible in frozen:
        return True

    # A classroom projection may extract several complete source sentences and
    # place them in one slot.  Requiring the entire joined projection to be one
    # contiguous source substring incorrectly rejects a source-authored
    # ellipsis whenever an unrelated delivery sentence was removed in between.
    # Prove each ellipsis-bearing clause independently instead; a renderer- or
    # model-generated truncation marker still fails because that local clause
    # cannot be found in the frozen block.
    ellipsis_clauses = [
        " ".join(_presentation_summary_text(clause).split())
        for clause in re.split(r"[\n。！？；;]+", str(value or ""))
        if _ELLIPSIS_MARKER_RE.search(clause)
    ]
    return bool(ellipsis_clauses) and all(
        clause and clause in frozen for clause in ellipsis_clauses
    )


def _first_generated_ellipsis(
    source_blocks: dict[str, CourseBlock],
    pages: list[SlidePageV6],
) -> tuple[str, str] | None:
    for page in pages:
        page_source = "\n".join(
            block_source_text(source_blocks[block_id])
            for block_id in page.source_block_ids
            if block_id in source_blocks
        )
        if page.source_block_ids and not _ellipsis_maps_to_frozen_source(
            page.title,
            page_source,
        ):
            return page.page_id, "title"
        for region in page.regions:
            if not _region_is_audience_visible(page, region):
                continue
            bound_source = "\n".join(
                block_source_text(source_blocks[block_id])
                for block_id in region.source_block_ids
                if block_id in source_blocks
            )
            if not _ellipsis_maps_to_frozen_source(region.content, bound_source):
                return page.page_id, region.region_id
        if page.visual_decision.decision == "diagram":
            for node in page.visual_decision.visual_payload.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                bound_source = "\n".join(
                    block_source_text(source_blocks[str(block_id)])
                    for block_id in node.get("source_block_ids") or []
                    if str(block_id) in source_blocks
                )
                if not _ellipsis_maps_to_frozen_source(
                    str(node.get("label") or ""),
                    bound_source,
                ):
                    return page.page_id, f"diagram-node:{node.get('node_id') or ''}"
            for index, edge in enumerate(
                page.visual_decision.visual_payload.get("edges") or []
            ):
                if isinstance(edge, dict) and not _ellipsis_maps_to_frozen_source(
                    str(edge.get("label") or ""),
                    page_source,
                ):
                    return page.page_id, f"diagram-edge:{index}"
    return None


def _visible_semantic_fidelity(
    document: CourseDocument,
    pages: list[SlidePageV6],
) -> tuple[float, float, float, bool]:
    """Measure source artifacts, prose, and procedures learners can actually see."""

    source_blocks = {block.block_id: block for block in _formal_blocks(document)}

    def region_contents(block_id: str, content_kind: str) -> list[str]:
        return [
            region.content
            for page in pages
            for region in page.regions
            if region.content_kind == content_kind
            and block_id in region.source_block_ids
        ]

    def semantic_region_contents(block_id: str) -> list[str]:
        return [
            region.content
            for page in pages
            for region in page.regions
            if region.content_kind in {"body", "items", "steps"}
            and block_id in region.source_block_ids
        ]

    artifact_results: list[bool] = []
    prose_results: list[bool] = []
    step_results: list[bool] = []
    for block in source_blocks.values():
        artifacts = set(block_artifact_kinds(block))
        if "code" in artifacts:
            expected = _complete_slot_content([block], "code")
            actual = "\n".join(region_contents(block.block_id, "code"))
            artifact_results.append(actual == expected)
        if "formula" in artifacts:
            expected = _bounded_formula_content([block], max_chars=0)
            actual = "\n\n".join(region_contents(block.block_id, "formula"))
            artifact_results.append(actual == expected)
        if "table" in artifacts:
            expected_headers, expected_rows = _table_components(block_source_text(block))
            table_regions = region_contents(block.block_id, "table")
            if expected_headers:
                actual_rows = [
                    tuple(row)
                    for content in table_regions
                    for row in _table_components(content)[1]
                ]
                artifact_results.append(
                    Counter(actual_rows)
                    == Counter(tuple(row) for row in expected_rows)
                )
            else:
                expected = _complete_slot_content([block], "table")
                artifact_results.append(expected in table_regions)

        presentation_source = block_presentation_text(block)
        expected_step_groups = _ordered_step_groups(presentation_source)
        if len(expected_step_groups) >= 2:
            source_prose = _artifact_free_prose_text(block)
            actual_semantic = "\n".join(
                semantic_region_contents(block.block_id)
            )
            steps_visible = _ordered_step_sequence_visible(
                presentation_source,
                actual_semantic,
            )
            projection_closed = (
                _ordered_step_projection_is_semantically_closed(source_prose)
            )
            complete_prose_visible = (
                _canonical_step_sequence_text(source_prose)
                in _canonical_step_sequence_text(actual_semantic)
            )
            step_results.append(
                steps_visible
                and (projection_closed or complete_prose_visible)
            )
            if not projection_closed:
                prose_results.append(complete_prose_visible)
        else:
            expected_prose = _canonical_visible_semantic_text(
                _artifact_free_prose_text(block)
            )
            if expected_prose:
                actual_prose = _canonical_visible_semantic_text(
                    "\n".join(semantic_region_contents(block.block_id))
                )
                prose_results.append(expected_prose in actual_prose)

    generated_ellipsis_free = _first_generated_ellipsis(
        source_blocks,
        pages,
    ) is None

    artifact_fidelity = (
        sum(artifact_results) / len(artifact_results)
        if artifact_results
        else 1.0
    )
    prose_fidelity = (
        sum(prose_results) / len(prose_results)
        if prose_results
        else 1.0
    )
    step_fidelity = (
        sum(step_results) / len(step_results)
        if step_results
        else 1.0
    )
    return (
        artifact_fidelity,
        prose_fidelity,
        step_fidelity,
        generated_ellipsis_free,
    )


def _source_driven_page_upper_bound(
    document: CourseDocument,
    story_page_count: int,
    template: TemplateLayoutPackContractV1,
) -> int:
    """Return a source-sized final safety bound, never a fixed slide ceiling."""

    slots_by_kind: dict[str, list[Any]] = {
        kind: [
            slot
            for layout in template.layouts
            for slot in layout.slots
            if slot.slot_kind == kind
        ]
        for kind in {"body", "steps", "code", "formula", "table"}
    }

    def text_fragments(block: CourseBlock, prose: str) -> int:
        slot_kind = (
            "steps"
            if "steps" in source_required_slot_kinds([block])
            else "body"
        )
        counts: list[int] = []
        for slot in slots_by_kind[slot_kind]:
            try:
                counts.append(len(_split_text_block_for_slot(
                    _block_with_prose_excerpt(block, prose),
                    slot_kind=slot_kind,
                    max_chars=slot.max_chars,
                    max_items=slot.max_items,
                    max_lines=slot.max_lines,
                    capacity_profile=getattr(slot, "capacity_profile", ""),
                )))
            except ValueError:
                continue
        if counts:
            return min(counts)
        capacity = max(
            (int(slot.max_chars or 0) for slot in slots_by_kind[slot_kind]),
            default=1,
        )
        return max(1, ceil(len(prose) / max(1, capacity)))

    def artifact_fragments(block: CourseBlock, artifact_kind: str) -> int:
        if artifact_kind in {"visual", "diagram", "image", "data", "experiment", "source_excerpt"}:
            return 1
        if artifact_kind == "formula":
            counts: list[int] = []
            for slot in slots_by_kind["formula"]:
                try:
                    counts.append(len(_split_artifact_block(
                        block,
                        slot_kind="formula",
                        max_chars=slot.max_chars,
                        max_lines=slot.max_lines,
                        max_rows=slot.max_rows,
                    )))
                except ValueError:
                    continue
            return min(counts) if counts else max(
                1,
                len(_formula_candidates(block_source_text(block))),
            )
        if artifact_kind == "table":
            _headers, rows = _table_components(block_source_text(block))
            max_rows = max(
                (int(slot.max_rows or 0) for slot in slots_by_kind["table"]),
                default=1,
            )
            return max(1, ceil(max(1, len(rows)) / max(1, max_rows)))
        counts: list[int] = []
        for slot in slots_by_kind["code"]:
            try:
                counts.append(len(_split_code_block_for_layout_variants(
                    block,
                    slot=slot,
                    split_first_page=False,
                )))
            except ValueError:
                continue
        return min(counts) if counts else max(1, len(block_source_text(block).splitlines()))

    source_pages = 0
    for block in _formal_blocks(document):
        block_pages = 0
        prose = _artifact_free_prose_text(block)
        if prose:
            block_pages += text_fragments(block, prose)
        block_pages += sum(
            artifact_fragments(block, artifact_kind)
            for artifact_kind in block_artifact_kinds(block)
        )
        source_pages += max(1, block_pages)
    # Semantic boundary preservation can leave a short tail.  Twenty percent
    # headroom absorbs those legitimate tails while still rejecting runaway
    # recursive or repeated pagination. Cover/agenda receive two explicit pages.
    return ceil(max(story_page_count, source_pages) * 1.2) + 2


def compile_slide_deck_v6(
    document: CourseDocument,
    graph: CoursePresentationGraphV1,
    story: SlideStoryPlanV3,
    visual: SlideVisualPlanV2,
    template: TemplateLayoutPackContractV1,
) -> SlideDeckV6:
    story = prepare_story_plan_for_final_compilation(story, graph, template)
    validate_slide_story_plan_v3(story, graph, template)
    status = validate_slide_visual_plan_v2(visual, story, graph, template)
    blocks = {block.block_id: block for block in _formal_blocks(document)}
    visual_by_page = {decision.page_id: decision for decision in visual.decisions}
    pages: list[SlidePageV6] = []
    used_page_title_keys: set[str] = {
        re.sub(r"\s+", "", page.title).casefold()
        for page in story.pages
        if page.title.strip()
    }
    for story_page in sorted(story.pages, key=lambda item: item.page_ordinal):
        layout = template.get_layout(visual_by_page[story_page.page_id].resolved_template_layout_id)
        if layout is None:
            raise V6BuildError(stage="template", code="template_layout_unavailable", message="Resolved layout disappeared during final compilation", page_id=story_page.page_id)
        source_blocks = [blocks[block_id] for block_id in story_page.source_block_ids]
        materializations = _safe_artifact_page_blocks(
            page_id=story_page.page_id,
            template=template,
            layout=layout,
            source_blocks=source_blocks,
            story_summary=story_page.summary,
        )
        # Story planning keeps semantic ownership; final pagination is driven by
        # complete source units. Progress is guarded per source page rather than
        # by a fixed deck-size product limit.
        continuation_count = len(materializations)
        for continuation_index, materialization in enumerate(materializations, start=1):
            page_layout = materialization.layout
            materialized_blocks = materialization.source_blocks
            title_slot = next(
                (slot for slot in page_layout.slots if slot.slot_kind == "title"),
                None,
            )
            page_id = (
                story_page.page_id
                if continuation_index == 1
                else f"{story_page.page_id}--continuation-{continuation_index}"
            )
            title = _continuation_title(
                story_page.title,
                continuation_index,
                continuation_count,
                title_slot,
                materialized_blocks,
                used_page_title_keys,
                page_id=page_id,
            )
            materialized_source_ids = list(dict.fromkeys(
                block.block_id for block in materialized_blocks
            ))
            uses_story_artifact_layout = (
                page_layout.template_layout_id == layout.template_layout_id
            )
            materialized_artifacts = {
                artifact
                for block in materialized_blocks
                for artifact in block_artifact_kinds(block)
            }
            retains_visual_decision = bool(
                uses_story_artifact_layout
                or (
                    visual_by_page[story_page.page_id].decision
                    in set(page_layout.artifact_kinds)
                    and visual_by_page[story_page.page_id].decision
                    in materialized_artifacts
                )
                or (
                    visual_by_page[story_page.page_id].decision == "data"
                    and "table" in materialized_artifacts
                    and "data" in set(page_layout.artifact_kinds)
                )
            )
            decision = visual_by_page[story_page.page_id].model_copy(
                update={
                    "page_id": page_id,
                    "decision": (
                        visual_by_page[story_page.page_id].decision
                        if retains_visual_decision
                        else "text_native"
                    ),
                    "source_block_ids": materialized_source_ids,
                    "resolved_template_layout_id": page_layout.template_layout_id,
                },
                deep=True,
            )
            has_supporting_artifact = any(
                slot.slot_kind in {"code", "formula", "table", "visual"}
                for slot in page_layout.slots
            )
            regions = _materialize_template_regions(
                page_id=page_id,
                title=title,
                layout=page_layout,
                source_blocks=materialized_blocks,
                story_summary=(
                    story_page.summary
                    if continuation_index == 1
                    and uses_story_artifact_layout
                    and (continuation_count == 1 or has_supporting_artifact)
                    else ""
                ),
                visual_decision=decision,
            )
            pages.append(
                SlidePageV6(
                    page_id=page_id,
                    page_ordinal=len(pages),
                    teaching_unit_id=story_page.teaching_unit_id,
                    title=title,
                    title_max_lines=int(
                        getattr(title_slot, "max_lines", 0) or 1
                    ),
                    resolved_layout=page_layout.template_layout_id,
                    web_renderer_adapter=page_layout.web_renderer_adapter,
                    pptx_renderer_adapter=page_layout.pptx_renderer_adapter,
                    regions=regions,
                    source_block_ids=materialized_source_ids,
                    artifact_kinds=list(dict.fromkeys(
                        artifact
                        for block in materialized_blocks
                        for artifact in block_artifact_kinds(block)
                    )),
                    visual_decision=decision,
                    speaker_notes=SlideSpeakerNotesV2(
                        source_document_revision=document.document_revision,
                        teaching_unit_id=story_page.teaching_unit_id,
                        source_blocks=[
                            SourceNoteBlockV2(
                                block_id=block.block_id,
                                block_revision=block.internal_revision,
                                full_text=block_source_text(block),
                                source_kind=block.kind,
                                source_payload=dict(block.payload or {}),
                                asset_refs=list(block.asset_refs),
                            )
                            for block in source_blocks
                        ],
                    ),
                    continuation_of_page_id=(
                        story_page.page_id if continuation_index > 1 else ""
                    ),
                    continuation_index=continuation_index,
                    continuation_count=continuation_count,
                )
            )
    agenda_pages = _compile_course_agenda_pages(document, template)
    if agenda_pages and not (
        pages and pages[0].resolved_layout.endswith("/cover-minimal")
    ):
        pages.insert(0, _compile_course_cover_page(document, template))
    insertion_index = 0
    while (
        insertion_index < len(pages)
        and pages[insertion_index].resolved_layout.endswith("/cover-minimal")
    ):
        insertion_index += 1
    if agenda_pages:
        pages[insertion_index:insertion_index] = agenda_pages
    for page_ordinal, page in enumerate(pages):
        page.page_ordinal = page_ordinal
    formal_ids = graph.formal_block_ids
    visible = {
        block_id
        for page in pages
        for block_id in _audience_visible_source_block_ids(page)
    }
    exact_noted = {
        item.block_id
        for page in pages
        for item in page.speaker_notes.source_blocks
        if item.block_id in blocks
        and item.block_revision == blocks[item.block_id].internal_revision
        and item.full_text == block_source_text(blocks[item.block_id])
        and item.source_kind == blocks[item.block_id].kind
        and item.source_payload == dict(blocks[item.block_id].payload or {})
        and item.asset_refs == list(blocks[item.block_id].asset_refs)
    }
    observed_first_occurrences: list[str] = []
    observed_set: set[str] = set()
    for page in pages:
        for block_id in page.source_block_ids:
            if block_id not in observed_set:
                observed_first_occurrences.append(block_id)
                observed_set.add(block_id)
    denominator = max(1, len(formal_ids))
    (
        source_artifact_visible_fidelity,
        source_prose_visible_fidelity,
        ordered_step_visible_fidelity,
        generated_ellipsis_free,
    ) = _visible_semantic_fidelity(document, pages)
    story_page_ids = {page.page_id for page in story.pages}
    expansion_by_story_page = Counter(
        page.continuation_of_page_id
        or (page.page_id if page.page_id in story_page_ids else "")
        for page in pages
    )
    expansion_by_story_page.pop("", None)
    story_page_count = len(story.pages)
    final_page_count = len(pages)
    pagination_page_upper_bound = _source_driven_page_upper_bound(
        document,
        story_page_count,
        template,
    )
    visible_char_counts = [
        sum(
            len(_visible_prose_text(region.content))
            for region in page.regions
            if region.content_kind != "notes"
        )
        for page in pages
    ]
    unique_note_chars = sum(
        len(_visible_prose_text(note.full_text))
        for note in {
            (note.block_id, note.block_revision): note
            for page in pages
            for note in page.speaker_notes.source_blocks
        }.values()
    )
    teacher_cue_pattern = re.compile(
        r"【(?:板书|提问|等待回应|演示|巡视|投影|计时)[^】]*】"
    )
    quality = SlideDeckV6Quality(
        formal_block_visible_coverage=len(visible.intersection(formal_ids)) / denominator,
        full_text_note_binding=len(exact_noted.intersection(formal_ids)) / denominator,
        source_artifact_visible_fidelity=source_artifact_visible_fidelity,
        source_prose_visible_fidelity=source_prose_visible_fidelity,
        ordered_step_visible_fidelity=ordered_step_visible_fidelity,
        generated_ellipsis_free=generated_ellipsis_free,
        source_order_preserved=observed_first_occurrences == formal_ids,
        template_contract_passed=True,
        subject_artifacts_passed=True,
        web_pptx_contract_shared=all(page.web_renderer_adapter and page.pptx_renderer_adapter for page in pages),
        story_page_count=story_page_count,
        final_page_count=final_page_count,
        pagination_expansion_ratio=(
            final_page_count / max(1, story_page_count)
        ),
        max_story_page_expansion=max(expansion_by_story_page.values(), default=0),
        pagination_page_upper_bound=pagination_page_upper_bound,
        pagination_within_dynamic_bound=(
            final_page_count <= pagination_page_upper_bound
        ),
        average_visible_chars_per_page=(
            sum(visible_char_counts)
            / max(1, final_page_count)
        ),
        max_visible_chars_per_page=max(visible_char_counts, default=0),
        visible_to_speaker_notes_ratio=(
            sum(visible_char_counts) / max(1, unique_note_chars)
        ),
        teacher_cue_free_page_ratio=(
            sum(
                1
                for page in pages
                if not any(
                    teacher_cue_pattern.search(region.content)
                    for region in page.regions
                )
            )
            / max(1, final_page_count)
        ),
        distinct_page_title_ratio=(
            len({
                re.sub(r"\s+", "", page.title).casefold()
                for page in pages
                if page.title.strip()
            })
            / max(1, final_page_count)
        ),
    )
    if quality.formal_block_visible_coverage != 1.0 or quality.full_text_note_binding != 1.0:
        raise V6BuildError(stage="quality", code="course_block_coverage_incomplete", message="Final deck does not bind every formal block visibly and in notes")
    if quality.source_artifact_visible_fidelity != 1.0:
        raise V6BuildError(
            stage="quality",
            code="source_artifact_visible_fidelity_incomplete",
            message="Visible code, formula, or table content differs from frozen source",
        )
    if quality.source_prose_visible_fidelity != 1.0:
        raise V6BuildError(
            stage="quality",
            code="source_prose_visible_fidelity_incomplete",
            message="Visible prose omits frozen source meaning",
        )
    if quality.ordered_step_visible_fidelity != 1.0:
        raise V6BuildError(
            stage="quality",
            code="ordered_step_visible_fidelity_incomplete",
            message="Visible ordered steps omit or alter frozen source actions",
        )
    if not quality.pagination_within_dynamic_bound:
        raise V6BuildError(
            stage="quality",
            code="pagination_expansion_excessive",
            message=(
                "Final pagination exceeds the source-driven dynamic safety bound "
                f"({quality.final_page_count}/{quality.pagination_page_upper_bound})"
            ),
        )
    if not quality.generated_ellipsis_free:
        offending = _first_generated_ellipsis(blocks, pages)
        raise V6BuildError(
            stage="quality",
            code="generated_ellipsis_detected",
            message=(
                "Visible slide content contains an ellipsis that cannot be mapped "
                "to the same frozen-source context"
                + (f" ({offending[1]})" if offending else "")
            ),
            page_id=offending[0] if offending else "",
        )
    if quality.distinct_page_title_ratio != 1.0:
        raise V6BuildError(
            stage="quality",
            code="duplicate_final_page_title",
            message="Every final classroom page requires a distinct teaching title",
        )
    return SlideDeckV6(
        course_id=document.course_id,
        title=document.title,
        theme=template.theme_id,
        source_document_revision=document.document_revision,
        template_id=template.template_id,
        template_version=template.template_version,
        template_digest=template.template_digest,
        template_theme_overrides=dict(template.render_theme_overrides),
        status=status,
        pages=pages,
        quality=quality,
    )


__all__ = [
    "AIBatchDiagnosticV1",
    "AIProviderAttemptDiagnosticV1",
    "SLIDE_DECK_V6_COMPILER_VERSION",
    "PptManuscriptPageV1",
    "PptManuscriptV1",
    "PptSourceContractV2",
    "SlideDeckV6",
    "SlideStoryBatchV3",
    "SlideStoryPageV3",
    "SlideStoryPlanV3",
    "SlideVisualDecisionV2",
    "SlideVisualPlanV2",
    "V6BuildError",
    "V6Failure",
    "V6_FAILURE_ROOT_CAUSE_BY_CODE",
    "V6_STAGE_CONTRACTS",
    "build_signature_v6",
    "classify_v6_failure",
    "compile_ppt_source_contract_v2",
    "compile_ppt_manuscript_v1",
    "compile_shadow_chapter_document",
    "compile_slide_deck_v6",
    "graph_page_source_blocks",
    "prepare_story_plan_for_final_compilation",
    "validate_layout_source_satisfiability",
    "validate_story_template_text_slots",
    "validate_slide_story_plan_v3",
    "validate_slide_visual_plan_v2",
]
