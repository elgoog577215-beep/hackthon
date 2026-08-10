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
)
from template_layout_contract import TemplateLayoutPackContractV1


V6Status = Literal["v6_ready", "v6_needs_manual_edit", "v6_failed"]
SLIDE_DECK_V6_COMPILER_VERSION = "slide_deck_v6_compiler_v1"


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
    source_asset_ids: list[str] = Field(default_factory=list)
    visual_payload: dict[str, Any] = Field(default_factory=dict)
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
    source_kind: str
    source_payload: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[str] = Field(default_factory=list)


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
    source_asset_refs: list[str] = Field(default_factory=list)


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
    continuation_of_page_id: str = ""
    continuation_index: int = Field(default=1, ge=1, le=3)
    continuation_count: int = Field(default=1, ge=1, le=3)


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
    def derive_passed(self) -> "SlideDeckV6Quality":
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
}


def _protected_tokens(text: str) -> set[str]:
    return {
        *(match.group(0).lower() for match in _PROTECTED_NUMBER_RE.finditer(text)),
        *(match.group(0).lower() for match in _PROTECTED_IDENTIFIER_RE.finditer(text)),
    }


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
            protected.add(token.lower())
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
        if unit.teaching_intent not in layout.teaching_intents:
            raise V6BuildError(stage="template", code="template_layout_intent_mismatch", message="Template layout does not support the teaching intent", page_id=page.page_id)
        if unit.source_ordinal < previous_unit_ordinal:
            raise V6BuildError(stage="story", code="story_dependency_order_invalid", message="Story reverses course teaching-unit order", page_id=page.page_id)
        previous_unit_ordinal = unit.source_ordinal
        page_count_by_unit[unit.teaching_unit_id] += 1
        if page_count_by_unit[unit.teaching_unit_id] > 3:
            raise V6BuildError(stage="story", code="teaching_unit_page_limit_exceeded", message="A teaching unit exceeds the one-to-three page contract", page_id=page.page_id)
        normalized_title = re.sub(r"\s+", "", page.title).casefold()
        if normalized_title in title_owners:
            raise V6BuildError(
                stage="story",
                code="duplicate_slide_title",
                message="Each V6 page must have a distinct teaching title",
                page_id=page.page_id,
            )
        title_owners[normalized_title] = page.page_id
        unsupported_title_tokens = _title_protected_tokens(page.title) - _title_protected_tokens(unit.source_text)
        if unsupported_title_tokens or _semantic_grounding_ratio(page.title, unit.source_text) < 0.12:
            raise V6BuildError(
                stage="story",
                code="story_unsupported_title",
                message="Visible page title is not traceable to its frozen source unit",
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
                if _protected_tokens(label) - _protected_tokens(unit.source_text) or _semantic_grounding_ratio(label, unit.source_text) < 0.12:
                    raise V6BuildError(stage="visual", code="visual_diagram_label_unsupported", message="Diagram node label is not grounded in source text", page_id=page_id)
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
        for artifact in unit.artifact_kinds:
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
    sentences = re.split(r"(?<=[。！？.!?])\s*", normalized)
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
    excerpt = normalized[: capacity - 1].rstrip("，。！？,;: ")
    return f"{excerpt}…"


_SLOT_ROLE_PREFERENCES: dict[str, set[str]] = {
    "driving_question": {"orientation", "objective", "checkpoint", "activity"},
    "task": {"activity", "checkpoint", "orientation"},
    "prompt": {"activity", "checkpoint", "orientation", "example"},
    "criteria": {"feedback", "summary", "objective"},
    "feedback": {"feedback", "answer", "remediation"},
    "annotation": {"concept", "reasoning", "feedback", "remediation"},
    "derivation": {"reasoning", "example"},
    "reasoning": {"reasoning", "example"},
    "interpretation": {"reasoning", "feedback", "summary"},
    "explanation": {"concept", "reasoning", "feedback"},
    "symptom": {"misconception", "counterexample"},
    "cause": {"reasoning", "misconception"},
    "repair": {"remediation", "feedback"},
    "next_action": {"transfer", "application", "activity"},
}


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
    prose = "\n".join(prose_lines).strip()
    if prose == text.strip() and block.kind in {"code", "table"}:
        return ""
    return prose


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
        candidate = max(
            (
                text for text in candidates
                if len(text) <= per_block_chars
                and len(text.splitlines()) <= per_block_lines
            ),
            key=len,
            default=candidates[0],
        )
        selected: list[str] = []
        for line in candidate.splitlines():
            next_text = "\n".join([*selected, line])
            if selected and (
                len(selected) + 1 > per_block_lines
                or len(next_text) > per_block_chars
            ):
                break
            if len(next_text) > per_block_chars:
                continue
            selected.append(line)
        excerpt = "\n".join(selected).strip()
        if excerpt:
            excerpts.append(excerpt)
    content = "\n\n".join(excerpts)
    if len(content) > capacity or len(content.splitlines()) > line_capacity:
        raise ValueError("template_slot_capacity_exceeded")
    return content


def _bounded_slot_content(
    blocks: list[CourseBlock],
    *,
    slot_kind: str,
    max_chars: int,
    max_items: int,
    max_lines: int,
    max_rows: int,
) -> str:
    if slot_kind == "code":
        return _bounded_code_content(
            blocks,
            max_chars=max_chars,
            max_lines=max_lines,
        )
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
        content = "\n".join(texts)
        lines = content.splitlines()
        if (max_rows and len(lines) > max_rows + 2) or len(content) > capacity:
            raise ValueError("template_slot_capacity_exceeded")
        return content.rstrip()
    if slot_kind == "items":
        items: list[str] = []
        for text in texts:
            candidates = [
                re.sub(r"^\s*(?:[-*+] |\d+[.)]\s*)", "", line).strip()
                for line in text.splitlines()
                if line.strip()
            ]
            items.extend(candidates or [text])
        if (max_items and len(items) > max_items) or len("\n".join(items)) > capacity:
            raise ValueError("template_slot_capacity_exceeded")
        return "\n".join(items).rstrip()
    if len(texts) == 1:
        return _complete_sentence_excerpt(texts[0], capacity)
    separator_cost = 2 * (len(texts) - 1)
    per_block_capacity = max(24, (capacity - separator_cost) // len(texts))
    excerpts = [
        _complete_sentence_excerpt(text, per_block_capacity)
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
    return [_block_with_source_excerpt(block, chunk) for chunk in chunks]


def _safe_artifact_page_blocks(
    *,
    page_id: str,
    layout: Any,
    source_blocks: list[CourseBlock],
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
    try:
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
    if layout.layout_slug not in set(layout.safe_continuation_layout_slugs):
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message="The selected template layout declares no safe artifact continuation",
            page_id=page_id,
        )
    artifact_chunks: list[CourseBlock] = []
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
            message=f"A single source line exceeds template slot {artifact_slot.slot_id}",
            page_id=page_id,
        ) from error
    if len(artifact_chunks) > 3:
        raise V6BuildError(
            stage="template",
            code="teaching_unit_page_limit_exceeded",
            message="A source artifact needs more than three template-safe pages",
            page_id=page_id,
        )
    artifact_ids = {block.block_id for block in artifact_blocks}
    non_artifact_blocks = [
        block for block in source_blocks if block.block_id not in artifact_ids
    ]
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


def _materialize_template_regions(
    *,
    page_id: str,
    title: str,
    layout: Any,
    source_blocks: list[CourseBlock],
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
        preferred_roles = _SLOT_ROLE_PREFERENCES.get(slot.slot_id, set())
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

    regions: list[SlideRegionV6] = []
    for slot in content_slots:
        slot_blocks = assigned.get(slot.slot_id, [])
        try:
            content = _bounded_slot_content(
                slot_blocks,
                slot_kind=slot.slot_kind,
                max_chars=slot.max_chars,
                max_items=slot.max_items,
                max_lines=slot.max_lines,
                max_rows=slot.max_rows,
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
    unit_page_counts = Counter(page.teaching_unit_id for page in story.pages)
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
        )
        expanded_unit_count = (
            unit_page_counts[story_page.teaching_unit_id]
            - 1
            + len(materializations)
        )
        if expanded_unit_count > 3:
            raise V6BuildError(
                stage="template",
                code="teaching_unit_page_limit_exceeded",
                message="A teaching unit exceeds three template-safe pages after pagination",
                page_id=story_page.page_id,
            )
        unit_page_counts[story_page.teaching_unit_id] = expanded_unit_count
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
    "validate_slide_story_plan_v3",
    "validate_slide_visual_plan_v2",
]
