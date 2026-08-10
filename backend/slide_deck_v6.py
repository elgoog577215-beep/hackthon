"""Course-faithful contracts and publication gates for slide-deck V6."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from course_document import CourseBlock, CourseDocument, stable_hash
from course_presentation_graph import (
    CoursePresentationGraphV1,
    CoursePresentationUnitV1,
    block_source_text,
)
from template_layout_contract import TemplateLayoutPackContractV1


V6Status = Literal["v6_ready", "v6_needs_manual_edit", "v6_failed"]


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
    ) -> None:
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
    source_block_ids: list[str] = Field(min_length=1)
    resolved_template_layout_id: str
    provider: str = ""
    model: str = ""
    duration_ms: int = Field(default=0, ge=0)
    attempts: int = Field(default=1, ge=1)
    degraded: bool = False
    degradation_reason: str = ""


class SlideVisualPlanV2(_StrictModel):
    schema_version: Literal["slide_visual_plan_v2"] = "slide_visual_plan_v2"
    source_document_revision: str
    template_digest: str
    decisions: list[SlideVisualDecisionV2] = Field(min_length=1)


class SourceNoteBlockV2(_StrictModel):
    block_id: str
    block_revision: str
    full_text: str


class SlideSpeakerNotesV2(_StrictModel):
    schema_version: Literal["slide_speaker_notes_v2"] = "slide_speaker_notes_v2"
    source_document_revision: str
    teaching_unit_id: str
    source_blocks: list[SourceNoteBlockV2] = Field(min_length=1)


class SlideRegionV6(_StrictModel):
    region_id: str
    slot_id: str
    content_kind: str
    content: str
    source_block_ids: list[str] = Field(default_factory=list)


class SlidePageV6(_StrictModel):
    schema_version: Literal["slide_page_v6"] = "slide_page_v6"
    page_id: str
    page_ordinal: int = Field(ge=0)
    teaching_unit_id: str
    title: str
    resolved_layout: str
    web_renderer_adapter: str
    pptx_renderer_adapter: str
    regions: list[SlideRegionV6] = Field(min_length=1)
    source_block_ids: list[str] = Field(min_length=1)
    artifact_kinds: list[str] = Field(default_factory=list)
    visual_decision: SlideVisualDecisionV2
    speaker_notes: SlideSpeakerNotesV2


class SlideDeckV6Quality(_StrictModel):
    formal_block_visible_coverage: float = Field(ge=0, le=1)
    full_text_note_binding: float = Field(ge=0, le=1)
    source_order_preserved: bool
    template_contract_passed: bool
    subject_artifacts_passed: bool
    web_pptx_contract_shared: bool
    blockers: list[V6Failure] = Field(default_factory=list)


class SlideDeckV6(_StrictModel):
    schema_version: Literal["slide_deck_v6"] = "slide_deck_v6"
    course_id: str
    source_document_revision: str
    template_id: str
    template_version: str
    template_digest: str
    status: V6Status
    pages: list[SlidePageV6] = Field(min_length=1)
    quality: SlideDeckV6Quality


def _formal_blocks(document: CourseDocument) -> list[CourseBlock]:
    section_order = {section.section_id: index for index, section in enumerate(sorted(document.sections, key=lambda item: (item.position, item.level)))}
    return sorted(
        (block for block in document.blocks if block.status == "final"),
        key=lambda block: (section_order.get(block.section_id, len(section_order)), block.position, block.block_id),
    )


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


_PROTECTED_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
_PROTECTED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.]{2,}\b")


def _protected_tokens(text: str) -> set[str]:
    return {
        *(match.group(0).lower() for match in _PROTECTED_NUMBER_RE.finditer(text)),
        *(match.group(0).lower() for match in _PROTECTED_IDENTIFIER_RE.finditer(text)),
    }


def _unit_map(graph: CoursePresentationGraphV1) -> dict[str, CoursePresentationUnitV1]:
    return {unit.teaching_unit_id: unit for unit in graph.units}


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
        if unit.teaching_intent not in layout.teaching_intents:
            raise V6BuildError(stage="template", code="template_layout_intent_mismatch", message="Template layout does not support the teaching intent", page_id=page.page_id)
        if unit.source_ordinal < previous_unit_ordinal:
            raise V6BuildError(stage="story", code="story_dependency_order_invalid", message="Story reverses course teaching-unit order", page_id=page.page_id)
        previous_unit_ordinal = unit.source_ordinal
        page_count_by_unit[unit.teaching_unit_id] += 1
        if page_count_by_unit[unit.teaching_unit_id] > 3:
            raise V6BuildError(stage="story", code="teaching_unit_page_limit_exceeded", message="A teaching unit exceeds the one-to-three page contract", page_id=page.page_id)
        unsupported = _protected_tokens(page.summary) - _protected_tokens(unit.source_text)
        if unsupported:
            raise V6BuildError(stage="story", code="story_unsupported_fact", message=f"Unsupported factual tokens: {', '.join(sorted(unsupported))}", page_id=page.page_id)
        observed_blocks.extend(page.source_block_ids)
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
        layout = template.get_layout(decision.resolved_template_layout_id)
        if layout is None:
            raise V6BuildError(stage="visual", code="template_layout_unavailable", message="Visual plan selected an unknown template layout", page_id=page_id)
        for artifact in unit.artifact_kinds:
            allowed = _REQUIRED_VISUAL_DECISION.get(artifact)
            if allowed and decision.decision not in allowed:
                raise V6BuildError(
                    stage="visual",
                    code="required_subject_representation_missing",
                    message=f"Required {artifact} representation was replaced by {decision.decision}",
                    page_id=page_id,
                )
        if layout.artifact_kinds and decision.decision not in set(layout.artifact_kinds):
            raise V6BuildError(stage="visual", code="visual_layout_artifact_mismatch", message="Visual decision does not match the template artifact contract", page_id=page_id)
        if decision.degraded:
            if not decision.degradation_reason:
                raise V6BuildError(stage="visual", code="visual_degradation_reason_missing", message="A degraded page must explain the degradation", page_id=page_id)
            degraded = True
    return "v6_needs_manual_edit" if degraded else "v6_ready"


def _complete_sentence_excerpt(text: str, capacity: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= capacity:
        return normalized
    sentences = re.split(r"(?<=[。！？.!?])\s*", normalized)
    result = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{result}{sentence}" if not result else f"{result} {sentence}"
        if len(candidate) > capacity:
            break
        result = candidate
    return result or normalized[:capacity].rstrip("，、;；:：") + "…"


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
        body_slot = next((slot for slot in layout.slots if slot.slot_kind in {"body", "items", "code", "formula", "table"} and slot.required), None)
        body_capacity = (body_slot.max_chars if body_slot else 0) or 520
        body = story_page.summary or _complete_sentence_excerpt(
            "\n\n".join(block_source_text(block) for block in source_blocks),
            body_capacity,
        )
        pages.append(
            SlidePageV6(
                page_id=story_page.page_id,
                page_ordinal=story_page.page_ordinal,
                teaching_unit_id=story_page.teaching_unit_id,
                title=story_page.title,
                resolved_layout=layout.template_layout_id,
                web_renderer_adapter=layout.web_renderer_adapter,
                pptx_renderer_adapter=layout.pptx_renderer_adapter,
                regions=[
                    SlideRegionV6(
                        region_id=f"{story_page.page_id}:body",
                        slot_id=body_slot.slot_id if body_slot else "body",
                        content_kind=visual_by_page[story_page.page_id].decision,
                        content=body,
                        source_block_ids=story_page.source_block_ids,
                    )
                ],
                source_block_ids=story_page.source_block_ids,
                artifact_kinds=unit.artifact_kinds,
                visual_decision=visual_by_page[story_page.page_id],
                speaker_notes=SlideSpeakerNotesV2(
                    source_document_revision=document.document_revision,
                    teaching_unit_id=story_page.teaching_unit_id,
                    source_blocks=[
                        SourceNoteBlockV2(
                            block_id=block.block_id,
                            block_revision=block.internal_revision,
                            full_text=block_source_text(block),
                        )
                        for block in source_blocks
                    ],
                ),
            )
        )
    formal_ids = graph.formal_block_ids
    visible = {block_id for page in pages for block_id in page.source_block_ids}
    noted = {item.block_id for page in pages for item in page.speaker_notes.source_blocks if item.full_text}
    denominator = max(1, len(formal_ids))
    quality = SlideDeckV6Quality(
        formal_block_visible_coverage=len(visible.intersection(formal_ids)) / denominator,
        full_text_note_binding=len(noted.intersection(formal_ids)) / denominator,
        source_order_preserved=True,
        template_contract_passed=True,
        subject_artifacts_passed=True,
        web_pptx_contract_shared=all(page.web_renderer_adapter and page.pptx_renderer_adapter for page in pages),
    )
    if quality.formal_block_visible_coverage != 1.0 or quality.full_text_note_binding != 1.0:
        raise V6BuildError(stage="quality", code="course_block_coverage_incomplete", message="Final deck does not bind every formal block visibly and in notes")
    return SlideDeckV6(
        course_id=document.course_id,
        source_document_revision=document.document_revision,
        template_id=template.template_id,
        template_version=template.template_version,
        template_digest=template.template_digest,
        status=status,
        pages=pages,
        quality=quality,
    )


__all__ = [
    "PptSourceContractV2",
    "SlideDeckV6",
    "SlideStoryBatchV3",
    "SlideStoryPageV3",
    "SlideStoryPlanV3",
    "SlideVisualDecisionV2",
    "SlideVisualPlanV2",
    "V6BuildError",
    "V6Failure",
    "compile_ppt_source_contract_v2",
    "compile_slide_deck_v6",
    "validate_slide_story_plan_v3",
    "validate_slide_visual_plan_v2",
]
