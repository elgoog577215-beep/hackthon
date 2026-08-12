"""Course-faithful contracts and publication gates for slide-deck V6."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from course_document import CourseBlock, CourseDocument, refresh_document_revision, stable_hash
from course_presentation_graph import (
    CoursePresentationGraphV1,
    CoursePresentationUnitV1,
    block_artifact_kinds,
    block_source_text,
    page_artifact_kinds,
    page_teaching_intent,
)
from template_layout_contract import TemplateLayoutPackContractV1

V6Status = Literal["v6_ready", "v6_needs_manual_edit", "v6_failed"]
SLIDE_DECK_V6_COMPILER_VERSION = "slide_deck_v6_compiler_v2"


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
    continuation_index: int = Field(default=1, ge=1, le=3)
    continuation_count: int = Field(default=1, ge=1, le=3)

    @model_validator(mode="after")
    def require_source_binding(self) -> SlidePageV6:
        if not self.source_block_ids and not self.source_section_ids:
            raise ValueError("page_source_binding_missing")
        return self


class SlideDeckV6Quality(_StrictModel):
    formal_block_visible_coverage: float = Field(ge=0, le=1)
    full_text_note_binding: float = Field(ge=0, le=1)
    source_order_preserved: bool
    template_contract_passed: bool
    subject_artifacts_passed: bool
    web_pptx_contract_shared: bool
    render_review: dict[str, Any] = Field(default_factory=dict)
    blockers: list[V6Failure] = Field(default_factory=list)
    passed: bool = True

    @model_validator(mode="after")
    def derive_passed(self) -> SlideDeckV6Quality:
        self.passed = bool(
            self.formal_block_visible_coverage == 1.0
            and self.full_text_note_binding == 1.0
            and self.source_order_preserved
            and self.template_contract_passed
            and self.subject_artifacts_passed
            and self.web_pptx_contract_shared
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
    texts = [
        str(unit.primary_block_texts.get(block_id) or "").strip()
        for block_id in block_ids
        if str(unit.primary_block_texts.get(block_id) or "").strip()
    ]
    return "\n\n".join(texts) or unit.source_text


def _unit_map(graph: CoursePresentationGraphV1) -> dict[str, CoursePresentationUnitV1]:
    return {unit.teaching_unit_id: unit for unit in graph.units}


def graph_page_source_blocks(
    unit: CoursePresentationUnitV1,
    source_block_ids: list[str],
) -> list[CourseBlock]:
    """Rehydrate the frozen block facts needed by the template allocator."""

    return [
        CourseBlock(
            block_id=block_id,
            section_id=unit.section_id,
            position=index,
            kind=unit.primary_block_kinds.get(block_id, "rich_text"),
            role=unit.primary_block_roles.get(block_id, "concept"),
            payload={"text": unit.primary_block_texts.get(block_id, "")},
            asset_refs=list(unit.primary_block_asset_refs.get(block_id, [])),
        )
        for index, block_id in enumerate(source_block_ids)
    ]


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
    for page in sorted(plan.pages, key=lambda item: item.page_ordinal):
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
        layout_slot_kinds = {slot.slot_kind for slot in layout.slots}
        if not required_slot_kinds.issubset(layout_slot_kinds):
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
        if title_slot and title_slot.max_chars and len(page.title) > title_slot.max_chars:
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
        if page.summary and _visible_prose_text(page.summary) != page.summary.strip():
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
            source_length = len(_visible_prose_text(
                _unit_source_text_for_blocks(unit, page.source_block_ids)
            ))
            summary_min_chars = min(
                int(getattr(summary_slot, "min_chars", 0) or 0),
                source_length,
            )
            if summary_min_chars and len(_visible_prose_text(page.summary)) < summary_min_chars:
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
    decisions = {decision.page_id: decision for decision in plan.decisions}
    if set(decisions) != set(story_pages):
        raise V6BuildError(stage="visual", code="visual_page_coverage_incomplete", message="Visual plan must contain exactly one decision per story page")
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
        if decision.resolved_template_layout_id != page.template_layout_id:
            raise V6BuildError(
                stage="visual",
                code="visual_layout_binding_mismatch",
                message="Visual decision must retain the story page template layout",
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
        for sentence in re.split(r"(?<=[。！？.!?])\s*", protected)
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

    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[([^]]*)]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?<!\\)(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\\)(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(
        r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*)?/?>",
        "",
        text,
    )
    return text.replace(r"\*", "*").replace(r"\_", "_").strip()


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
    fenced = [
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:[A-Za-z0-9_+.#-]+)?\s*\n(.*?)```",
            text,
            re.DOTALL,
        )
        if match.group(1).strip()
    ]
    return fenced or [text.strip()]


def _prose_source_text(block: CourseBlock) -> str:
    text = block_source_text(block)
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
    if prose == text.strip() and block.kind in {"code", "table"}:
        return ""
    return prose


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
    """Select source-only code excerpts; full code remains in speaker notes."""

    if not blocks:
        return ""
    capacity = max_chars or 1600
    line_capacity = max_lines or 24
    per_block_chars = max(48, capacity // len(blocks))
    per_block_lines = max(1, line_capacity // len(blocks))
    excerpts: list[str] = []
    for block in blocks:
        candidates = _code_candidates(block_source_text(block))
        candidate = max(candidates, key=len)
        excerpt = _safe_code_excerpt(
            candidate,
            max_chars=per_block_chars,
            max_lines=per_block_lines,
        )
        if excerpt:
            excerpts.append(excerpt)
    content = "\n\n".join(excerpts)
    if len(content) > capacity or len(content.splitlines()) > line_capacity:
        raise ValueError("template_slot_capacity_exceeded")
    return content


def _formula_candidates(text: str) -> list[str]:
    displayed = [
        match.group(0).strip()
        for match in re.finditer(r"\$\$.+?\$\$|\\\[.+?\\\]", text, re.DOTALL)
        if match.group(0).strip()
    ]
    return displayed or [text.strip()]


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


def _bounded_ordered_step_item(
    heading: str,
    details: list[str],
    capacity: int,
) -> str:
    """Select complete source details instead of clipping a step mid-thought."""

    clean_heading = heading.rstrip(" :：")
    if not details or capacity <= len(clean_heading):
        return _display_excerpt(clean_heading, capacity).rstrip(" :：;；")
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
        candidate = (
            f"{clean_heading}{relation_separator}"
            f"{detail_separator.join([*selected, normalized_detail])}"
            f"{candidate_terminal}"
        )
        if len(candidate) > capacity:
            break
        selected.append(normalized_detail)
        selected_terminal = candidate_terminal
    if selected:
        return (
            f"{clean_heading}{relation_separator}"
            f"{detail_separator.join(selected)}"
            f"{selected_terminal}"
        ).rstrip(" ;；:：")
    return _display_excerpt(clean_heading, capacity)


def source_required_slot_kinds(source_blocks: list[CourseBlock]) -> set[str]:
    """Return semantic template slots required to keep source structure visible."""

    sequence_roles = {"activity", "checkpoint", "orientation"}
    if any(
        block.role in sequence_roles
        and len(_ordered_step_items(block_source_text(block))) >= 2
        for block in source_blocks
    ):
        return {"steps"}
    return set()


def _bounded_slot_content(
    blocks: list[CourseBlock],
    *,
    slot_kind: str,
    max_chars: int,
    max_items: int,
    max_lines: int,
    max_rows: int,
    supports_single_row_detail: bool = False,
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
        separator_cost = max(0, step_count - 1)
        per_step_capacity = max(1, (capacity - separator_cost) // step_count)
        excerpts = (
            [
                _bounded_ordered_step_item(heading, details, per_step_capacity)
                for heading, details in ordered_groups
            ]
            if ordered_groups
            else [
                _complete_sentence_excerpt(step, per_step_capacity)
                for step in fallback_steps
            ]
        )
        content = "\n".join(excerpts).rstrip()
        if len(content) > capacity:
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
        item_limit = max_items or sum(len(items) for items in items_by_block)
        if len(items_by_block) > item_limit:
            raise ValueError("template_slot_capacity_exceeded")
        selected = [items[0] for items in items_by_block]
        next_indexes = [1 for _items in items_by_block]
        while len(selected) < item_limit:
            added = False
            for block_index, items in enumerate(items_by_block):
                next_index = next_indexes[block_index]
                if next_index >= len(items):
                    continue
                selected.append(items[next_index])
                next_indexes[block_index] += 1
                added = True
                if len(selected) >= item_limit:
                    break
            if not added:
                break
        separator_cost = max(0, len(selected) - 1)
        per_item_capacity = max(1, (capacity - separator_cost) // len(selected))
        excerpts = [
            _complete_sentence_excerpt(item, per_item_capacity)
            for item in selected
        ]
        content = "\n".join(excerpts).rstrip()
        if len(content) > capacity or (max_items and len(excerpts) > max_items):
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


def _block_with_source_excerpt(block: CourseBlock, content: str) -> CourseBlock:
    payload = dict(block.payload or {})
    key = next(
        (candidate for candidate in ("markdown", "text", "content", "summary") if candidate in payload),
        "text",
    )
    payload[key] = content
    return block.model_copy(update={"payload": payload}, deep=True)


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


def _split_artifact_block(
    block: CourseBlock,
    *,
    slot_kind: str,
    max_chars: int,
    max_lines: int,
    max_rows: int,
) -> list[CourseBlock]:
    content = block_source_text(block)
    lines = content.splitlines()
    if slot_kind == "code":
        chunks = _pack_lines(
            lines,
            max_lines=max_lines,
            max_chars=max_chars,
        )
    elif slot_kind == "table":
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
    else:
        return [block]
    prose = _prose_source_text(block)
    return [
        _block_with_source_excerpt(
            block,
            f"{prose}\n\n{chunk}" if prose else chunk,
        )
        for chunk in chunks
    ]


def _display_width_units(value: str) -> int:
    return sum(1 if ord(character) < 128 else 2 for character in str(value or ""))


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
    wide_first_page = bool(
        split_first_page
        and int(getattr(slot, "wide_min_columns", 0) or 0)
        and len(headers) >= int(slot.wide_min_columns)
    )

    def page_column_capacity() -> int:
        if page_index == 0 and split_first_page and not wide_first_page:
            declared = int(slot.split_column_chars or slot.full_column_chars or 1)
        else:
            declared = int(slot.full_column_chars or slot.split_column_chars or 1)
        # Slot capacity is declared against a three-column reference table.
        # Wider schemas keep the same template geometry, so each cell's safe
        # display width must shrink instead of forcing a smaller font.
        return max(
            6,
            min(declared, round(declared * 3 / max(3, len(headers)))),
        )

    def rendered_text(candidate_rows: list[list[str]]) -> str:
        return _markdown_table_text(headers, candidate_rows)

    def wrapped_cost(candidate_rows: list[list[str]]) -> int:
        capacity = page_column_capacity()
        header_cost = max(
            1,
            max(
                (
                    (_display_width_units(cell) + capacity - 1) // capacity
                    for cell in headers
                ),
                default=1,
            ),
        )
        return header_cost + sum(
            max(
                1,
                max(
                    (
                        (_display_width_units(cell) + capacity - 1) // capacity
                        for cell in row
                    ),
                    default=1,
                ),
            )
            for row in candidate_rows
        )

    def wrapped_budget() -> int:
        if page_index == 0 and split_first_page and not wide_first_page:
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

    def exceeds(candidate_rows: list[list[str]]) -> bool:
        candidate_text = rendered_text(candidate_rows)
        return bool(
            (slot.max_rows and len(candidate_rows) > slot.max_rows)
            or (slot.max_chars and len(candidate_text) > slot.max_chars)
            or (
                wrapped_budget()
                and wrapped_cost(candidate_rows) > wrapped_budget()
            )
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
    prose = _prose_source_text(block)
    return [
        _block_with_source_excerpt(
            block,
            f"{prose}\n\n{chunk}" if prose else chunk,
        )
        for chunk in chunks
    ]


def _safe_artifact_page_blocks(
    *,
    page_id: str,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
) -> list[list[CourseBlock]]:
    artifact_slot = next(
        (
            slot
            for slot in layout.slots
            if slot.slot_kind in {"code", "table"}
            and any(_block_matches_slot(block, slot.slot_kind) for block in source_blocks)
        ),
        None,
    )
    if artifact_slot is None:
        return [source_blocks]
    artifact_blocks = [
        block
        for block in source_blocks
        if _block_matches_slot(block, artifact_slot.slot_kind)
    ]
    artifact_ids = {block.block_id for block in artifact_blocks}
    non_artifact_blocks = [
        block for block in source_blocks if block.block_id not in artifact_ids
    ]
    adaptive_table = bool(
        artifact_slot.slot_kind == "table"
        and (artifact_slot.split_wrapped_lines or artifact_slot.full_wrapped_lines)
        and artifact_slot.full_column_chars
    )
    artifact_chunks: list[CourseBlock] = []
    try:
        if adaptive_table:
            for block in artifact_blocks:
                artifact_chunks.extend(
                    _split_table_block_for_layout_variants(
                        block,
                        slot=artifact_slot,
                        split_first_page=bool(
                            non_artifact_blocks or _visible_prose_text(story_summary)
                        ),
                    )
                )
            if len(artifact_blocks) == 1 and len(artifact_chunks) == 1:
                return [source_blocks]
        else:
            _bounded_slot_content(
                artifact_blocks,
                slot_kind=artifact_slot.slot_kind,
                max_chars=artifact_slot.max_chars,
                max_items=artifact_slot.max_items,
                max_lines=artifact_slot.max_lines,
                max_rows=artifact_slot.max_rows,
            )
            return [source_blocks]
    except ValueError as error:
        if str(error) != "template_slot_capacity_exceeded":
            raise
        if adaptive_table and not artifact_chunks:
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
    if len(artifact_chunks) > 3:
        raise V6BuildError(
            stage="template",
            code="teaching_unit_page_limit_exceeded",
            message="A source artifact needs more than three template-safe pages",
            page_id=page_id,
        )
    materializations: list[list[CourseBlock]] = []
    for chunk in artifact_chunks:
        by_position = [*non_artifact_blocks, chunk]
        materializations.append(
            sorted(by_position, key=lambda block: (block.position, block.block_id))
        )
    return materializations


def _continuation_title(title: str, index: int, count: int, capacity: int) -> str:
    if count == 1:
        return title
    suffix = f" ({index}/{count})"
    if capacity and len(title) + len(suffix) > capacity:
        title = title[: max(1, capacity - len(suffix))].rstrip()
    return f"{title}{suffix}"


def _effective_slot_min_chars(slot: Any, blocks: list[CourseBlock]) -> int:
    declared = int(getattr(slot, "min_chars", 0) or 0)
    if declared <= 0:
        return 0
    available = len(_visible_prose_text("\n\n".join(
        block_source_text(block)
        for block in blocks
        if block_source_text(block)
    )))
    return min(declared, available)


def _materialize_template_regions(
    *,
    page_id: str,
    title: str,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
) -> list[SlideRegionV6]:
    title_slot = next(
        (slot for slot in layout.slots if slot.slot_kind == "title"),
        None,
    )
    if title_slot and title_slot.max_chars and len(title) > title_slot.max_chars:
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
    remaining = list(source_blocks)
    assigned: dict[str, list[CourseBlock]] = {}
    for slot in content_slots:
        if slot.slot_kind not in {"code", "formula", "table", "visual"}:
            continue
        matches = [
            block for block in remaining if _block_matches_slot(block, slot.slot_kind)
        ]
        if matches:
            assigned[slot.slot_id] = matches
            remaining = [block for block in remaining if block not in matches]

    text_slots = [slot for slot in content_slots if slot.slot_id not in assigned]
    reusable_artifact_blocks = [
        block
        for slot_blocks in assigned.values()
        for block in slot_blocks
        if block not in remaining and _prose_source_text(block)
    ]
    remaining.extend(
        block
        for block in reusable_artifact_blocks
        if block not in remaining
    )
    for index, slot in enumerate(text_slots):
        if not remaining:
            break
        preferred_roles = set(slot.source_roles)
        preferred = [block for block in remaining if block.role in preferred_roles]
        is_last_text_slot = index == len(text_slots) - 1
        if preferred:
            selected = preferred if is_last_text_slot else [preferred[0]]
        elif is_last_text_slot:
            selected = list(remaining)
        else:
            selected = [remaining[0]]
        assigned[slot.slot_id] = selected
        remaining = [block for block in remaining if block not in selected]
    if remaining and text_slots:
        assigned.setdefault(text_slots[-1].slot_id, []).extend(remaining)
        remaining = []

    summary_slot_id = ""
    summary_content = _visible_prose_text(story_summary)
    if (
        summary_content
        and len(text_slots) == 1
        and text_slots[0].slot_kind == "body"
    ):
        summary_slot_id = text_slots[0].slot_id

    regions: list[SlideRegionV6] = []
    for slot in content_slots:
        slot_blocks = assigned.get(slot.slot_id, [])
        try:
            if slot.slot_id == summary_slot_id:
                if slot.max_chars and len(summary_content) > slot.max_chars:
                    raise ValueError("template_slot_capacity_exceeded")
                content = summary_content
                slot_blocks = list(source_blocks)
            else:
                content = _bounded_slot_content(
                    slot_blocks,
                    slot_kind=slot.slot_kind,
                    max_chars=slot.max_chars,
                    max_items=slot.max_items,
                    max_lines=slot.max_lines,
                    max_rows=slot.max_rows,
                    supports_single_row_detail=bool(
                        slot.slot_kind == "table"
                        and getattr(slot, "split_wrapped_lines", 0)
                        and getattr(slot, "full_wrapped_lines", 0)
                        and getattr(slot, "full_column_chars", 0)
                    ),
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
        if slot.required and not content:
            raise V6BuildError(
                stage="template",
                code="template_required_slot_unfilled",
                message=f"Required template slot {slot.slot_id} has no source-backed content",
                page_id=page_id,
            )
        minimum_chars = _effective_slot_min_chars(slot, slot_blocks)
        if minimum_chars and len(_visible_prose_text(content)) < minimum_chars:
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
        regions.append(
            SlideRegionV6(
                region_id=f"{page_id}:{slot.slot_id}",
                slot_id=slot.slot_id,
                content_kind=slot.slot_kind,
                content=content,
                source_block_ids=[block.block_id for block in slot_blocks],
                source_asset_refs=list(
                    dict.fromkeys(
                        asset_ref
                        for block in slot_blocks
                        for asset_ref in block.asset_refs
                        if asset_ref
                    )
                ),
            )
        )
    visible_blocks = {
        block_id for region in regions for block_id in region.source_block_ids
    }
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


def validate_story_template_text_slots(
    *,
    page_id: str,
    layout: Any,
    source_blocks: list[CourseBlock],
    story_summary: str = "",
    enforce_min_chars: bool = True,
) -> None:
    """Reject story layouts whose required prose slots cannot bind source."""

    content_slots = [
        slot
        for slot in layout.slots
        if slot.slot_kind not in {"title", "eyebrow", "notes"}
    ]
    remaining = list(source_blocks)
    assigned_artifact_blocks: list[CourseBlock] = []
    for slot in content_slots:
        if slot.slot_kind not in {"code", "formula", "table", "visual"}:
            continue
        matches = [
            block
            for block in remaining
            if _block_matches_slot(block, slot.slot_kind)
        ]
        if matches:
            assigned_artifact_blocks.extend(matches)
            remaining = [block for block in remaining if block not in matches]
    remaining.extend(
        block
        for block in assigned_artifact_blocks
        if _prose_source_text(block) and block not in remaining
    )

    text_slots = [
        slot
        for slot in content_slots
        if slot.slot_kind in {"body", "items", "steps"}
    ]
    if any(slot.slot_kind == "steps" for slot in text_slots) and all(
        slot.source_roles for slot in text_slots
    ):
        expressible_roles = {
            role for slot in text_slots for role in slot.source_roles
        }
        incompatible = [
            block.block_id
            for block in source_blocks
            if block.role not in expressible_roles
        ]
        if incompatible:
            raise V6BuildError(
                stage="template",
                code="template_source_slot_role_mismatch",
                message=(
                    "Structured template slots cannot express source roles for blocks: "
                    + ", ".join(incompatible)
                ),
                page_id=page_id,
            )
    assigned: dict[str, list[CourseBlock]] = {}
    for index, slot in enumerate(text_slots):
        if not remaining:
            break
        preferred_roles = set(slot.source_roles)
        preferred = [block for block in remaining if block.role in preferred_roles]
        is_last_text_slot = index == len(text_slots) - 1
        if preferred:
            selected = preferred if is_last_text_slot else [preferred[0]]
        elif is_last_text_slot:
            selected = list(remaining)
        else:
            selected = [remaining[0]]
        assigned[slot.slot_id] = selected
        remaining = [block for block in remaining if block not in selected]
    if remaining and text_slots:
        assigned.setdefault(text_slots[-1].slot_id, []).extend(remaining)

    summary_slot_id = ""
    summary_content = _visible_prose_text(story_summary)
    if (
        summary_content
        and len(text_slots) == 1
        and text_slots[0].slot_kind == "body"
    ):
        summary_slot_id = text_slots[0].slot_id

    for slot in text_slots:
        try:
            if slot.slot_id == summary_slot_id:
                if slot.max_chars and len(summary_content) > slot.max_chars:
                    raise ValueError("template_slot_capacity_exceeded")
                content = summary_content
            else:
                content = _bounded_slot_content(
                    assigned.get(slot.slot_id, []),
                    slot_kind=slot.slot_kind,
                    max_chars=slot.max_chars,
                    max_items=slot.max_items,
                    max_lines=slot.max_lines,
                    max_rows=slot.max_rows,
                )
        except ValueError as error:
            raise V6BuildError(
                stage="template",
                code="template_slot_capacity_exceeded",
                message=f"Source-backed content exceeds template slot {slot.slot_id}",
                page_id=page_id,
            ) from error
        if slot.required and not content:
            raise V6BuildError(
                stage="template",
                code="template_required_slot_unfilled",
                message=(
                    f"Required template slot {slot.slot_id} "
                    "has no source-backed content"
                ),
                page_id=page_id,
            )
        if enforce_min_chars:
            minimum_chars = _effective_slot_min_chars(
                slot,
                assigned.get(slot.slot_id, []),
            )
            if minimum_chars and len(_visible_prose_text(content)) < minimum_chars:
                raise V6BuildError(
                    stage="template",
                    code="template_slot_underfilled",
                    message=(
                        f"Source-backed content underfills template slot {slot.slot_id}"
                    ),
                    page_id=page_id,
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
                if not required_slot_kinds.issubset(
                    {slot.slot_kind for slot in layout.slots}
                ):
                    continue
                try:
                    validate_story_template_text_slots(
                        page_id="story-safe-slice",
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
) -> list[int]:
    """Derive a compact LLM page budget from template-safe source partitions."""

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
    maximum_pages = min(
        feasible_counts[-1],
        max(3, minimum_pages + 1),
    )
    return [minimum_pages, maximum_pages]


def story_safe_partition_options(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
    *,
    max_options_per_page_count: int = 12,
) -> list[dict[str, Any]]:
    """Compile safe slices into complete, ordered exact-cover choices for the LLM."""

    safe_slices = story_safe_page_slices(unit, template)
    allowed_page_count_range = story_page_count_range(unit, template)
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
    chunks: list[list[Any]] = []
    current: list[Any] = []
    for section in sections:
        title = _visible_prose_text(section.title).strip()
        if not title:
            raise V6BuildError(
                stage="source",
                code="course_section_title_missing",
                message="A course section cannot be represented in the agenda",
                chapter_id=section.section_id,
            )
        candidate = [*current, section]
        candidate_text = "\n".join(
            _visible_prose_text(item.title).strip() for item in candidate
        )
        if current and (
            len(candidate) > max_items
            or (max_chars and len(candidate_text) > max_chars)
        ):
            chunks.append(current)
            current = [section]
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

    pages: list[SlidePageV6] = []
    for index, chunk in enumerate(chunks, start=1):
        page_id = f"course-agenda-{index}"
        section_ids = [section.section_id for section in chunk]
        content = "\n".join(
            _visible_prose_text(section.title).strip() for section in chunk
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


def compile_slide_deck_v6(
    document: CourseDocument,
    graph: CoursePresentationGraphV1,
    story: SlideStoryPlanV3,
    visual: SlideVisualPlanV2,
    template: TemplateLayoutPackContractV1,
) -> SlideDeckV6:
    validate_slide_story_plan_v3(story, graph, template)
    status = validate_slide_visual_plan_v2(visual, story, graph, template)
    blocks = {block.block_id: block for block in _formal_blocks(document)}
    units = _unit_map(graph)
    visual_by_page = {decision.page_id: decision for decision in visual.decisions}
    pages: list[SlidePageV6] = []
    for story_page in sorted(story.pages, key=lambda item: item.page_ordinal):
        layout = template.get_layout(visual_by_page[story_page.page_id].resolved_template_layout_id)
        if layout is None:
            raise V6BuildError(stage="template", code="template_layout_unavailable", message="Resolved layout disappeared during final compilation", page_id=story_page.page_id)
        unit = units[story_page.teaching_unit_id]
        source_blocks = [blocks[block_id] for block_id in story_page.source_block_ids]
        materializations = _safe_artifact_page_blocks(
            page_id=story_page.page_id,
            layout=layout,
            source_blocks=source_blocks,
            story_summary=story_page.summary,
        )
        # Story planning already enforces the teaching-unit semantic page
        # budget. Template pagination is a separate, bounded render concern:
        # one planned artifact page may become at most three safe pages so
        # source rows are not truncated merely to preserve the story count.
        if len(materializations) > 3:
            raise V6BuildError(
                stage="template",
                code="template_artifact_continuation_limit_exceeded",
                message=(
                    "A planned artifact page requires more than three "
                    "template-safe materializations"
                ),
                page_id=story_page.page_id,
            )
        title_slot = next(
            (slot for slot in layout.slots if slot.slot_kind == "title"),
            None,
        )
        continuation_count = len(materializations)
        for continuation_index, materialized_blocks in enumerate(materializations, start=1):
            page_id = (
                story_page.page_id
                if continuation_index == 1
                else f"{story_page.page_id}--continuation-{continuation_index}"
            )
            title = _continuation_title(
                story_page.title,
                continuation_index,
                continuation_count,
                int(getattr(title_slot, "max_chars", 0) or 0),
            )
            regions = _materialize_template_regions(
                page_id=page_id,
                title=title,
                layout=layout,
                source_blocks=materialized_blocks,
                story_summary=story_page.summary,
            )
            decision = visual_by_page[story_page.page_id].model_copy(
                update={"page_id": page_id},
                deep=True,
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
                    resolved_layout=layout.template_layout_id,
                    web_renderer_adapter=layout.web_renderer_adapter,
                    pptx_renderer_adapter=layout.pptx_renderer_adapter,
                    regions=regions,
                    source_block_ids=story_page.source_block_ids,
                    artifact_kinds=unit.artifact_kinds,
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
        for region in page.regions
        for block_id in region.source_block_ids
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
    quality = SlideDeckV6Quality(
        formal_block_visible_coverage=len(visible.intersection(formal_ids)) / denominator,
        full_text_note_binding=len(exact_noted.intersection(formal_ids)) / denominator,
        source_order_preserved=observed_first_occurrences == formal_ids,
        template_contract_passed=True,
        subject_artifacts_passed=True,
        web_pptx_contract_shared=all(page.web_renderer_adapter and page.pptx_renderer_adapter for page in pages),
    )
    if quality.formal_block_visible_coverage != 1.0 or quality.full_text_note_binding != 1.0:
        raise V6BuildError(stage="quality", code="course_block_coverage_incomplete", message="Final deck does not bind every formal block visibly and in notes")
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
    "PptSourceContractV2",
    "SlideDeckV6",
    "SlideStoryBatchV3",
    "SlideStoryPageV3",
    "SlideStoryPlanV3",
    "SlideVisualDecisionV2",
    "SlideVisualPlanV2",
    "V6BuildError",
    "V6Failure",
    "build_signature_v6",
    "compile_ppt_source_contract_v2",
    "compile_shadow_chapter_document",
    "compile_slide_deck_v6",
    "graph_page_source_blocks",
    "validate_story_template_text_slots",
    "validate_slide_story_plan_v3",
    "validate_slide_visual_plan_v2",
]
