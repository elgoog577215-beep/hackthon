"""Shared V6 records; compilation and planning are separate consumers."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_serializer, model_validator
from ppt_teaching_content import PageTeachingV2, PptPacingV1
from ppt_page_scene import ResolvedPageScene
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

    def public_detail(self) -> dict[str, Any]:
        """Return the stable, user-safe failure contract used by task recovery."""

        return {
            **self.failure.model_dump(
                mode="json",
                exclude={"chapter_id", "page_id", "batch_id"},
            ),
            **(
                {"chapter_id": self.failure.chapter_id}
                if self.failure.chapter_id else {}
            ),
            **({"page_id": self.failure.page_id} if self.failure.page_id else {}),
            **({"batch_id": self.failure.batch_id} if self.failure.batch_id else {}),
            **({"node_id": self.node_id} if self.node_id else {}),
        }


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
    visible_copy: list[str] = Field(default_factory=list, max_length=12)
    page_goal: str = Field(default="", max_length=240)
    primary_claim: str = Field(default="", max_length=320)
    audience_question: str = Field(default="", max_length=320)
    audience_action: str = Field(default="", max_length=320)
    expected_response: str = Field(default="", max_length=500)
    observable_evidence: str = Field(default="", max_length=500)
    transition: str = Field(default="", max_length=320)
    reveal_steps: list[str] = Field(default_factory=list, max_length=12)
    composition_notes: str = Field(default="", max_length=500)
    question_bank_item_ids: list[str] = Field(default_factory=list, max_length=12)
    shared_visual_expression_ids: list[str] = Field(default_factory=list, max_length=12)
    source_block_ids: list[str] = Field(min_length=1)
    page_ordinal: int = Field(ge=0)


class SlideNarrativeBriefV1(_StrictModel):
    schema_version: Literal["slide_narrative_brief_v1"] = "slide_narrative_brief_v1"
    central_question: str = Field(default="", max_length=320)
    learning_path: list[str] = Field(default_factory=list, max_length=16)
    observable_checkpoints: list[str] = Field(default_factory=list, max_length=16)
    time_budget_minutes: int = Field(default=0, ge=0, le=6000)
    must_include_source_block_ids: list[str] = Field(default_factory=list, max_length=5000)


class SlideStoryBatchV3(_StrictModel):
    batch_id: str
    chapter_id: str
    provider: str
    model: str
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    validation_status: Literal["passed", "failed"]
    failure_category: str = ""
    narrative_brief: SlideNarrativeBriefV1 = Field(
        default_factory=SlideNarrativeBriefV1
    )
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

    teaching_notes: list[str] | None = None

    @model_serializer(mode="wrap")
    def serialize_compatible(self, handler):
        payload = handler(self)
        if self.teaching_notes is None:
            payload.pop("teaching_notes", None)
        return payload

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
    resolved_scene: ResolvedPageScene | None = None

    @model_serializer(mode="wrap")
    def serialize_compatible(self, handler):
        payload = handler(self)
        if self.resolved_scene is None:
            payload.pop("resolved_scene", None)
        return payload

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
    """一页可审阅的 页面内容稿：拥有台上可见内容，不拥有新知识。"""

    page_id: str
    page_number: int = Field(ge=1)
    teaching_unit_id: str
    course_block_types: list[str] = Field(default_factory=list)
    page_type: PptManuscriptPageType
    page_goal: str = ""
    primary_claim: str = ""
    audience_question: str = ""
    audience_action: str = ""
    expected_response: str = ""
    observable_evidence: str = ""
    transition: str = ""
    reveal_steps: list[str] = Field(default_factory=list)
    title: str
    visible_copy: list[str] = Field(default_factory=list)
    layout_id: str
    composition_notes: str
    visual_kind: VisualDecisionKind
    source_script_block_ids: list[str] = Field(default_factory=list)
    source_section_ids: list[str] = Field(default_factory=list)
    speaker_note_source_block_ids: list[str] = Field(default_factory=list)
    source_material_evidence_ids: list[str] = Field(default_factory=list)
    question_bank_item_ids: list[str] = Field(default_factory=list)
    shared_visual_expression_ids: list[str] = Field(default_factory=list)
    teacher_locked: bool = False
    lock_source_document_revision: str = ""
    title_max_lines: int = Field(default=1, ge=1, le=3)
    web_renderer_adapter: str = ""
    pptx_renderer_adapter: str = ""
    regions: list[SlideRegionV6] = Field(default_factory=list)
    artifact_kinds: list[str] = Field(default_factory=list)
    visual_decision: SlideVisualDecisionV2 | None = None
    speaker_notes: SlideSpeakerNotesV2 | None = None
    continuation_of_page_id: str = ""
    continuation_index: int = Field(default=1, ge=1)
    continuation_count: int = Field(default=1, ge=1)
    teaching: PageTeachingV2 | None = None
    resolved_scenes: list[ResolvedPageScene] | None = None
    split_reason: str = ""

    @model_serializer(mode="wrap")
    def serialize_compatible(self, handler):
        payload = handler(self)
        if not self.split_reason:
            payload.pop("split_reason", None)
        if self.teaching is None:
            payload.pop("teaching", None)
        if self.resolved_scenes is None:
            payload.pop("resolved_scenes", None)
        return payload

    @model_validator(mode="after")
    def require_source_binding(self) -> PptManuscriptPageV1:
        if not self.source_script_block_ids and not self.source_section_ids:
            raise ValueError("ppt_manuscript_source_binding_missing")
        return self


class PptManuscriptMaterialBindingV1(_StrictModel):
    material_asset_id: str
    source_asset_id: str = ""
    source_label: str
    role: Literal["primary", "reference"] = "reference"


class PptManuscriptV1(_StrictModel):
    """讲义与模板渲染之间的唯一逐页内容合同。"""

    schema_version: Literal["ppt_manuscript_v1"] = "ppt_manuscript_v1"
    teaching_content_contract_version: Literal[
        "legacy", "page_teaching_v1", "page_teaching_v2"
    ] = "legacy"
    manuscript_revision: str
    source_document_revision: str
    source_lesson_plan_revision_id: str = ""
    source_script_revision_id: str = ""
    material_bindings: list[PptManuscriptMaterialBindingV1] = Field(
        default_factory=list
    )
    narrative_brief: SlideNarrativeBriefV1 = Field(
        default_factory=SlideNarrativeBriefV1
    )
    template_id: str
    template_version: str
    template_digest: str
    page_count: int = Field(ge=1)
    pages: list[PptManuscriptPageV1] = Field(min_length=1)
    story_page_count: int = Field(default=0, ge=0)
    render_status: V6Status = "v6_ready"
    quality_status: Literal["passed", "blocked"] = "passed"
    quality_issues: list[V6Failure] = Field(default_factory=list)
    pacing: PptPacingV1 | None = None

    @model_serializer(mode="wrap")
    def serialize_compatible(self, handler):
        payload = handler(self)
        if self.pacing is None:
            payload.pop("pacing", None)
        return payload
