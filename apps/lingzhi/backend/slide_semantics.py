"""Subject-neutral teaching semantics for slide-deck compilation.

Course generation V16 already emits pedagogy modules and composition metadata.
This module preserves that contract and normalizes legacy courses into the same
internal protocol before V5 story compaction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, stable_hash

PPT_SEMANTIC_COMPILER_VERSION = "ppt_teaching_semantics_v2.1"
DOMAIN_PRESENTATION_PROFILE_VERSION = "domain_presentation_profiles_v1.1"

PresentationIntent = Literal[
    "definition",
    "relation",
    "hierarchy",
    "comparison",
    "process",
    "mechanism",
    "worked_example",
    "practice_feedback",
    "misconception_repair",
    "recap",
]

SubjectRepresentationKind = Literal[
    "code",
    "formula",
    "table",
    "diagram",
    "image",
    "output",
    "debugging",
    "testing",
    "architecture",
    "experiment",
    "data",
    "source_excerpt",
    "timeline",
    "case",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DomainPresentationProfileV1(_StrictModel):
    profile_id: str
    module_prefixes: list[str] = Field(default_factory=list)
    module_intents: dict[str, PresentationIntent] = Field(default_factory=dict)
    preferred_visual_kinds: dict[PresentationIntent, list[str]] = Field(
        default_factory=dict,
    )


class PresentationGrammarV1(_StrictModel):
    schema_version: Literal["presentation_grammar_v1"] = "presentation_grammar_v1"
    presentation_intent: PresentationIntent
    copy_voice: str
    information_structure: str
    visual_grammar: str
    allowed_layouts: list[str] = Field(default_factory=list, min_length=1)
    forbidden_fallbacks: list[str] = Field(default_factory=list)


class SubjectChapterRequirementV1(_StrictModel):
    chapter_id: str
    required_representation_kinds: list[SubjectRepresentationKind] = Field(
        default_factory=list,
    )
    minimum_artifact_count: int = Field(default=1, ge=1)


class SubjectPresentationContractV1(_StrictModel):
    schema_version: Literal["subject_presentation_contract_v1"] = (
        "subject_presentation_contract_v1"
    )
    profile_id: str
    primary_mode: str
    required_representation_kinds: list[SubjectRepresentationKind] = Field(
        default_factory=list,
    )
    optional_representation_kinds: list[SubjectRepresentationKind] = Field(
        default_factory=list,
    )
    characteristic_fragment_ids: dict[SubjectRepresentationKind, list[str]] = (
        Field(default_factory=dict)
    )
    chapter_requirements: list[SubjectChapterRequirementV1] = Field(
        default_factory=list,
    )
    classification_confidence: float = Field(ge=0, le=1)
    classification_source: str
    evidence_conflicts: list[str] = Field(default_factory=list)
    missing_recommended_representation_kinds: list[
        SubjectRepresentationKind
    ] = Field(default_factory=list)


class PptSemanticUnitV2(_StrictModel):
    schema_version: Literal["ppt_semantic_unit_v2"] = "ppt_semantic_unit_v2"
    semantic_unit_id: str
    source_document_revision: str
    section_id: str
    block_ids: list[str] = Field(default_factory=list, min_length=1)
    fragment_ids: list[str] = Field(default_factory=list, min_length=1)
    source_ordinal: int = Field(ge=0)
    primary_role: str
    supporting_roles: list[str] = Field(default_factory=list)
    teaching_intent: str
    presentation_intent: PresentationIntent
    presentation_grammar: PresentationGrammarV1
    domain_profile_id: str = "generic"
    module_id: str = ""
    module_instance_id: str = ""
    lesson_archetype_id: str = ""
    composition_source: str = ""
    composition_style: str = ""
    difficulty_contract: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[str] = Field(default_factory=list)
    objective_refs: list[str] = Field(default_factory=list)
    concept_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    knowledge_binding_status: str = ""
    question_ids: list[str] = Field(default_factory=list)
    answer_for_question_ids: list[str] = Field(default_factory=list)
    answer_source: Literal["", "source", "llm_generated"] = ""
    adapter_type: Literal["v16_structured", "legacy_compatible"]
    classification_confidence: float = Field(ge=0, le=1)
    classification_source: str
    fallback_reason: str = ""


class TeachingEpisodeContractV2(_StrictModel):
    schema_version: Literal["teaching_episode_contract_v2"] = (
        "teaching_episode_contract_v2"
    )
    episode_id: str
    section_id: str
    presentation_intent: PresentationIntent
    presentation_grammar: PresentationGrammarV1
    semantic_unit_ids: list[str] = Field(default_factory=list, min_length=1)
    question_ids: list[str] = Field(default_factory=list)
    answer_for_question_ids: list[str] = Field(default_factory=list)
    source_fragment_ids: list[str] = Field(default_factory=list, min_length=1)


class FinalPageContractV2(_StrictModel):
    schema_version: Literal["final_page_contract_v2"] = "final_page_contract_v2"
    page_id: str
    teaching_intent: str
    requested_layout: str
    resolved_layout: str
    occupied_slot_ids: list[str] = Field(default_factory=list)
    source_fragment_ids: list[str] = Field(default_factory=list)
    repair_passes: int = Field(default=0, ge=0, le=2)
    passed: bool = True


_ROLE_INTENTS: dict[str, PresentationIntent] = {
    "orientation": "definition",
    "prerequisite": "definition",
    "objective": "definition",
    "concept": "definition",
    "reasoning": "mechanism",
    "example": "worked_example",
    "counterexample": "misconception_repair",
    "application": "worked_example",
    "activity": "practice_feedback",
    "feedback": "practice_feedback",
    "misconception": "misconception_repair",
    "checkpoint": "practice_feedback",
    "remediation": "misconception_repair",
    "summary": "recap",
    "transfer": "worked_example",
}

_COMMON_MODULE_INTENTS: dict[str, PresentationIntent] = {
    "lesson_goal": "definition",
    "core_explanation": "definition",
    "learner_action": "practice_feedback",
    "feedback_check": "practice_feedback",
    "composition_deep_reasoning": "mechanism",
    "composition_case_extension": "worked_example",
    "composition_real_application": "worked_example",
    "composition_project_task": "practice_feedback",
    "composition_inquiry": "mechanism",
    "composition_boundary": "misconception_repair",
}


def _profile(
    profile_id: str,
    prefix: str,
    intents: dict[str, PresentationIntent],
    *,
    preferred_visual_kinds: dict[PresentationIntent, list[str]] | None = None,
) -> DomainPresentationProfileV1:
    visual_kinds: dict[PresentationIntent, list[str]] = {
        "definition": ["none", "formula"],
        "relation": ["relational_diagram", "rule_diagram"],
        "hierarchy": ["relational_diagram", "rule_diagram"],
        "comparison": ["table", "relational_diagram"],
        "process": ["rule_diagram", "relational_diagram"],
        "mechanism": ["relational_diagram", "rule_diagram"],
        "worked_example": ["source_image", "relational_diagram"],
        "practice_feedback": ["none"],
        "misconception_repair": ["table", "relational_diagram"],
        "recap": ["none"],
    }
    visual_kinds.update(preferred_visual_kinds or {})
    return DomainPresentationProfileV1(
        profile_id=profile_id,
        module_prefixes=[prefix] if prefix else [],
        module_intents=intents,
        preferred_visual_kinds=visual_kinds,
    )


DOMAIN_PRESENTATION_PROFILES: tuple[DomainPresentationProfileV1, ...] = (
    _profile("math_formal", "math_", {
        "math_formalization": "definition",
        "math_proof": "mechanism",
        "math_worked_example": "worked_example",
        "math_variation": "practice_feedback",
        "math_error_analysis": "misconception_repair",
        "math_modeling": "relation",
        "math_representation": "relation",
        "math_problem_strategy": "process",
    }),
    _profile("natural_science", "science_", {
        "science_phenomenon": "relation",
        "science_model": "definition",
        "science_evidence": "relation",
        "science_boundary": "comparison",
        "science_prediction": "worked_example",
        "science_experiment_design": "process",
        "science_data_analysis": "process",
        "science_argument": "mechanism",
    }),
    _profile("life_medical", "life_", {
        "life_system_levels": "hierarchy",
        "life_location_structure": "hierarchy",
        "life_function": "relation",
        "life_mechanism": "mechanism",
        "life_regulation": "process",
        "life_case": "worked_example",
        "life_normal_abnormal": "comparison",
        "life_evidence": "relation",
        "life_scale_connection": "hierarchy",
        "life_quantitative": "mechanism",
    }),
    _profile(
        "engineering_programming",
        "engineering_",
        {
            "engineering_artifact_path": "process",
            "engineering_minimal_run": "worked_example",
            "engineering_output": "practice_feedback",
            "engineering_mechanism": "mechanism",
            "engineering_modification": "practice_feedback",
            "engineering_debugging": "misconception_repair",
            "engineering_testing": "practice_feedback",
            "engineering_architecture": "hierarchy",
            "engineering_design": "process",
            "engineering_refactoring": "process",
            "engineering_review": "practice_feedback",
        },
        preferred_visual_kinds={
            "worked_example": ["code"],
            "process": ["code", "rule_diagram"],
            "mechanism": ["code", "relational_diagram"],
            "practice_feedback": ["code", "none"],
            "misconception_repair": ["code", "table"],
        },
    ),
    _profile("humanities_social", "humanities_", {
        "humanities_context": "relation",
        "humanities_source": "worked_example",
        "humanities_claim": "mechanism",
        "humanities_comparison": "comparison",
        "humanities_response": "practice_feedback",
        "humanities_source_criticism": "practice_feedback",
        "humanities_timeline": "process",
        "humanities_interpretation": "mechanism",
        "humanities_causation": "mechanism",
        "humanities_synthesis": "relation",
    }),
    _profile("business_career", "business_", {
        "business_scenario": "worked_example",
        "business_framework": "hierarchy",
        "business_case": "worked_example",
        "business_tool": "process",
        "business_task": "practice_feedback",
        "business_metric": "practice_feedback",
        "business_roleplay": "practice_feedback",
        "business_data": "relation",
        "business_problem_diagnosis": "mechanism",
        "business_decision": "comparison",
        "business_reflection": "recap",
        "business_ethics": "comparison",
    }),
)

GENERIC_PRESENTATION_PROFILE = _profile("generic", "", {})


def resolve_domain_presentation_profile(
    module_ids: list[str],
) -> DomainPresentationProfileV1:
    normalized = [str(value or "") for value in module_ids if str(value or "")]
    best = GENERIC_PRESENTATION_PROFILE
    best_score = 0
    for profile in DOMAIN_PRESENTATION_PROFILES:
        score = sum(
            2 if module_id in profile.module_intents else 1
            for module_id in normalized
            if (
                module_id in profile.module_intents
                or any(
                    module_id.startswith(prefix)
                    for prefix in profile.module_prefixes
                )
            )
        )
        if score > best_score:
            best = profile
            best_score = score
    return best


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _lesson_archetype_id(section: Any, payload: dict[str, Any]) -> str:
    candidate = payload.get("lesson_archetype")
    if not isinstance(candidate, dict):
        candidate = (getattr(section, "attributes", {}) or {}).get(
            "lesson_archetype",
        )
    if not isinstance(candidate, dict):
        return str(payload.get("lesson_archetype_id") or "")
    return str(candidate.get("archetype_id") or candidate.get("id") or "")


def _presentation_intent(
    *,
    profile: DomainPresentationProfileV1,
    module_id: str,
    role: str,
) -> PresentationIntent:
    return (
        profile.module_intents.get(module_id)
        or _COMMON_MODULE_INTENTS.get(module_id)
        or _ROLE_INTENTS.get(role)
        or "definition"
    )


def presentation_intent_for_module(
    module_id: str,
    role: str,
) -> PresentationIntent:
    profile = resolve_domain_presentation_profile([module_id])
    return _presentation_intent(
        profile=profile,
        module_id=str(module_id or ""),
        role=str(role or "concept"),
    )


_PRESENTATION_GRAMMARS: dict[
    PresentationIntent,
    tuple[str, str, str, list[str], list[str]],
] = {
    "definition": (
        "concise_explanatory_judgment",
        "claim_boundary_example",
        "concept_hierarchy_or_relation",
        [
            "hero-claim",
            "editorial-body",
            "balanced-two-column",
            "classification-3",
            "parallel-examples",
            "figure-text",
        ],
        [],
    ),
    "relation": (
        "relational_explanatory",
        "entities_and_relations",
        "relationship_map",
        [
            "balanced-two-column",
            "classification-3",
            "parallel-examples",
            "figure-text",
            "diagram-full",
        ],
        ["editorial-body"],
    ),
    "hierarchy": (
        "structural_explanatory",
        "levels_and_containment",
        "hierarchy",
        ["classification-3", "figure-text", "diagram-full"],
        ["editorial-body"],
    ),
    "comparison": (
        "parallel_judgment",
        "shared_axes_and_differences",
        "paired_or_matrix",
        [
            "balanced-two-column",
            "classification-3",
            "parallel-examples",
            "figure-text",
        ],
        ["editorial-body"],
    ),
    "process": (
        "ordered_instructional",
        "ordered_steps_or_state_changes",
        "control_flow",
        ["process-sequence", "figure-text", "diagram-full", "code"],
        ["editorial-body", "balanced-two-column"],
    ),
    "mechanism": (
        "causal_explanatory",
        "condition_cause_effect",
        "causal_or_data_flow",
        ["process-sequence", "figure-text", "diagram-full", "code"],
        ["editorial-body", "parallel-examples"],
    ),
    "worked_example": (
        "worked_evidence",
        "artifact_annotation_result",
        "artifact_first",
        [
            "worked-example",
            "question-prompt",
            "formula-explanation",
            "figure-text",
            "parallel-examples",
            "code",
        ],
        ["editorial-body"],
    ),
    "practice_feedback": (
        "action_then_diagnosis",
        "prompt_criteria_feedback",
        "exercise_and_feedback",
        ["question-prompt", "practice-feedback", "figure-text", "code"],
        ["editorial-body", "hero-claim"],
    ),
    "misconception_repair": (
        "diagnostic_corrective",
        "symptom_cause_fix_verification",
        "before_after_or_diagnostic",
        ["balanced-two-column", "classification-3", "figure-text", "code"],
        ["editorial-body"],
    ),
    "recap": (
        "retrieval_orienting",
        "thread_and_retrieval_cues",
        "recap",
        ["chapter-recap", "course-synthesis", "hero-claim"],
        ["editorial-body"],
    ),
}


def presentation_grammar_for_intent(
    intent: PresentationIntent,
    *,
    artifact_kind: SubjectRepresentationKind | str = "",
) -> PresentationGrammarV1:
    copy_voice, structure, visual, allowed, forbidden = (
        _PRESENTATION_GRAMMARS[intent]
    )
    if artifact_kind == "code":
        return PresentationGrammarV1(
            presentation_intent=intent,
            copy_voice="source_code_with_concise_annotation",
            information_structure="code_annotation_result",
            visual_grammar="artifact_first_code",
            allowed_layouts=list(dict.fromkeys([
                "code",
                "figure-text",
                *allowed,
            ])),
            forbidden_fallbacks=list(dict.fromkeys([
                "editorial-body",
                *forbidden,
            ])),
        )
    if artifact_kind == "formula":
        return PresentationGrammarV1(
            presentation_intent=intent,
            copy_voice="formal_expression_with_interpretation",
            information_structure="formula_conditions_interpretation",
            visual_grammar="artifact_first_formula",
            allowed_layouts=list(dict.fromkeys([
                "formula-explanation",
                "figure-text",
                *allowed,
            ])),
            forbidden_fallbacks=list(dict.fromkeys([
                "editorial-body",
                *forbidden,
            ])),
        )
    return PresentationGrammarV1(
        presentation_intent=intent,
        copy_voice=copy_voice,
        information_structure=structure,
        visual_grammar=visual,
        allowed_layouts=list(allowed),
        forbidden_fallbacks=list(forbidden),
    )


_PRIMARY_MODE_PROFILE_IDS = {
    "programming_engineering": "engineering_programming",
    "engineering_programming": "engineering_programming",
    "math_formal": "math_formal",
    "natural_science": "natural_science",
    "life_medical": "life_medical",
    "humanities_social": "humanities_social",
    "business_career": "business_career",
}

_MODULE_ARTIFACT_KINDS: dict[str, SubjectRepresentationKind] = {
    "engineering_output": "output",
    "engineering_debugging": "debugging",
    "engineering_testing": "testing",
    "engineering_architecture": "architecture",
    "science_experiment_design": "experiment",
    "science_data_analysis": "data",
    "humanities_source": "source_excerpt",
    "humanities_timeline": "timeline",
    "business_scenario": "case",
    "business_case": "case",
}

_PROFILE_OPTIONAL_KINDS: dict[str, list[SubjectRepresentationKind]] = {
    "engineering_programming": [
        "output",
        "debugging",
        "testing",
        "architecture",
    ],
    "math_formal": ["diagram", "table"],
    "natural_science": ["experiment", "data", "table", "diagram", "image"],
    "life_medical": ["diagram", "table", "image", "data"],
    "humanities_social": ["source_excerpt", "timeline", "table", "image"],
    "business_career": ["case", "table", "data", "diagram"],
    "generic": ["table", "diagram", "image"],
}

_PROFILE_EXPECTED_SOURCE_KINDS: dict[str, list[SubjectRepresentationKind]] = {
    "engineering_programming": ["code"],
    "math_formal": ["formula"],
}

_PROFILE_REQUIRED_MODULE_KINDS: dict[str, list[SubjectRepresentationKind]] = {
    "natural_science": ["experiment", "data"],
    "humanities_social": ["source_excerpt", "timeline"],
    "business_career": ["case", "data"],
}


def _profile_confidence(profile: dict[str, Any]) -> float:
    raw = profile.get("classification_confidence", profile.get("confidence"))
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    return {
        "high": 0.95,
        "medium": 0.75,
        "low": 0.45,
    }.get(str(raw or "").strip().lower(), 0.86 if profile.get("primary_mode") else 0.45)


def _chapter_id_for_section(
    section_id: str,
    sections_by_id: dict[str, Any],
) -> str:
    current = sections_by_id.get(section_id)
    visited: set[str] = set()
    while current is not None and current.section_id not in visited:
        visited.add(current.section_id)
        if current.parent_section_id is None:
            return str(current.section_id)
        current = sections_by_id.get(current.parent_section_id)
    return str(section_id)


def compile_subject_presentation_contract_v1(
    document: CourseDocument,
    course_data: dict[str, Any],
    semantic_units: list[PptSemanticUnitV2],
    fragments: list[Any],
) -> SubjectPresentationContractV1:
    """Compile subject-native representation requirements before compaction."""

    persisted = course_data.get("subject_pedagogy_profile") or {}
    if not isinstance(persisted, dict):
        persisted = {}
    primary_mode = str(persisted.get("primary_mode") or "general")
    module_ids = [unit.module_id for unit in semantic_units if unit.module_id]
    module_profile = resolve_domain_presentation_profile(module_ids)
    profile_id = _PRIMARY_MODE_PROFILE_IDS.get(primary_mode, "")
    if not profile_id or profile_id == "generic":
        profile_id = module_profile.profile_id
    fragment_catalog = {
        str(fragment.fragment_id): fragment for fragment in fragments
    }
    characteristic: dict[SubjectRepresentationKind, list[str]] = defaultdict(list)
    unit_by_fragment = semantic_unit_index(semantic_units)
    for fragment in fragments:
        fragment_id = str(fragment.fragment_id)
        kind: SubjectRepresentationKind | None = None
        if fragment.kind in {"code", "formula", "table", "diagram"}:
            kind = fragment.kind
        elif getattr(fragment, "source_kind", "") == "image":
            kind = "image"
        unit = unit_by_fragment.get(fragment_id)
        if kind is None and unit is not None:
            kind = _MODULE_ARTIFACT_KINDS.get(unit.module_id)
        if kind is not None:
            characteristic[kind].append(fragment_id)

    if profile_id == "generic":
        if characteristic.get("code"):
            profile_id = "engineering_programming"
        elif characteristic.get("formula"):
            profile_id = "math_formal"

    required: list[SubjectRepresentationKind] = []
    for kind in characteristic:
        if kind in {"code", "formula", "table", "diagram"}:
            required.append(kind)
        elif kind in _PROFILE_REQUIRED_MODULE_KINDS.get(profile_id, []):
            required.append(kind)
    required = list(dict.fromkeys(required))
    optional = [
        kind
        for kind in _PROFILE_OPTIONAL_KINDS.get(profile_id, [])
        if kind not in required
    ]
    missing_recommended = [
        kind
        for kind in _PROFILE_EXPECTED_SOURCE_KINDS.get(profile_id, [])
        if not characteristic.get(kind)
    ]
    conflicts: list[str] = []
    persisted_profile_id = _PRIMARY_MODE_PROFILE_IDS.get(primary_mode, "generic")
    if (
        persisted_profile_id != "generic"
        and module_profile.profile_id != "generic"
        and persisted_profile_id != module_profile.profile_id
    ):
        conflicts.append("subject_profile_evidence_conflict")
    if primary_mode not in {"general", "", "programming_engineering"}:
        if characteristic.get("code") and profile_id != "engineering_programming":
            conflicts.append("subject_profile_evidence_conflict")
    conflicts = list(dict.fromkeys(conflicts))

    sections_by_id = {section.section_id: section for section in document.sections}
    chapter_kinds: dict[str, set[SubjectRepresentationKind]] = defaultdict(set)
    for kind, fragment_ids in characteristic.items():
        for fragment_id in fragment_ids:
            fragment = fragment_catalog.get(fragment_id)
            if fragment is None:
                continue
            chapter_kinds[_chapter_id_for_section(
                str(fragment.section_id),
                sections_by_id,
            )].add(kind)
    chapter_requirements = [
        SubjectChapterRequirementV1(
            chapter_id=chapter_id,
            required_representation_kinds=[
                kind for kind in required if kind in kinds
            ],
            minimum_artifact_count=1,
        )
        for chapter_id, kinds in sorted(chapter_kinds.items())
        if any(kind in kinds for kind in required)
    ]
    return SubjectPresentationContractV1(
        profile_id=profile_id,
        primary_mode=primary_mode,
        required_representation_kinds=required,
        optional_representation_kinds=optional,
        characteristic_fragment_ids={
            kind: list(dict.fromkeys(fragment_ids))
            for kind, fragment_ids in characteristic.items()
        },
        chapter_requirements=chapter_requirements,
        classification_confidence=_profile_confidence(persisted),
        classification_source=str(
            persisted.get("classification_source")
            or "persisted_pedagogy_and_source_evidence"
        ),
        evidence_conflicts=conflicts,
        missing_recommended_representation_kinds=missing_recommended,
    )


def compile_ppt_semantic_units(
    document: CourseDocument,
    fragments: list[Any],
) -> list[PptSemanticUnitV2]:
    """Normalize structured and legacy course blocks into one semantic protocol."""
    fragments_by_block: dict[str, list[Any]] = defaultdict(list)
    for fragment in sorted(fragments, key=lambda item: item.ordinal):
        fragments_by_block[str(fragment.block_id)].append(fragment)
    blocks_by_id = {block.block_id: block for block in document.blocks}
    sections_by_id = {section.section_id: section for section in document.sections}
    module_ids = [
        str((block.payload or {}).get("module_id") or "")
        for block in document.blocks
    ]
    course_profile = resolve_domain_presentation_profile(module_ids)
    units: list[PptSemanticUnitV2] = []
    for block_id, block_fragments in fragments_by_block.items():
        block = blocks_by_id.get(block_id)
        if block is None or not block_fragments:
            continue
        payload = block.payload or {}
        section = sections_by_id.get(block.section_id)
        module_id = str(payload.get("module_id") or "")
        profile = resolve_domain_presentation_profile([module_id])
        if profile.profile_id == "generic" and not module_id:
            profile = course_profile
        module_instance_id = str(payload.get("module_instance_id") or "")
        composition_source = str(payload.get("composition_source") or "")
        composition_style = str(payload.get("composition_style") or "")
        difficulty = payload.get("block_difficulty_contract") or {}
        structured = bool(
            module_id
            or module_instance_id
            or composition_source
            or composition_style
            or difficulty
        )
        role = str(block.role or "concept")
        intent = _presentation_intent(
            profile=profile,
            module_id=module_id,
            role=role,
        )
        fragment_kinds = {str(item.kind or "") for item in block_fragments}
        artifact_kind: SubjectRepresentationKind | str = ""
        for candidate in ("code", "formula", "table", "diagram"):
            if candidate in fragment_kinds:
                artifact_kind = candidate
                break
        if not artifact_kind and any(
            getattr(item, "source_kind", "") == "image"
            for item in block_fragments
        ):
            artifact_kind = "image"
        if not artifact_kind:
            artifact_kind = _MODULE_ARTIFACT_KINDS.get(module_id, "")
        if artifact_kind == "code":
            intent = (
                "process"
                if role == "method"
                else "mechanism"
                if role == "reasoning"
                else "misconception_repair"
                if role in {"misconception", "counterexample", "remediation"}
                else "practice_feedback"
                if role in {"activity", "checkpoint", "feedback"}
                else "worked_example"
            )
        elif artifact_kind == "formula" and role in {"reasoning", "method"}:
            intent = "mechanism"
        unit_id = stable_hash({
            "document_revision": document.document_revision,
            "section_id": block.section_id,
            "block_id": block_id,
            "fragment_ids": [item.fragment_id for item in block_fragments],
        }, prefix="pptsem_")
        units.append(PptSemanticUnitV2(
            semantic_unit_id=unit_id,
            source_document_revision=str(document.document_revision or ""),
            section_id=block.section_id,
            block_ids=[block_id],
            fragment_ids=[item.fragment_id for item in block_fragments],
            source_ordinal=min(item.ordinal for item in block_fragments),
            primary_role=role,
            supporting_roles=[],
            teaching_intent={
                "definition": "建立概念、定义与边界",
                "relation": "说明要素之间的关系",
                "hierarchy": "建立层级与空间结构",
                "comparison": "对齐比较并形成判断",
                "process": "说明过程与操作顺序",
                "mechanism": "解释因果与作用机制",
                "worked_example": "用来源案例验证理解",
                "practice_feedback": "通过行动与反馈检查理解",
                "misconception_repair": "识别误区并完成修正",
                "recap": "回顾完整关键判断",
            }[intent],
            presentation_intent=intent,
            presentation_grammar=presentation_grammar_for_intent(
                intent,
                artifact_kind=artifact_kind,
            ),
            domain_profile_id=profile.profile_id,
            module_id=module_id,
            module_instance_id=module_instance_id,
            lesson_archetype_id=_lesson_archetype_id(section, payload),
            composition_source=composition_source,
            composition_style=composition_style,
            difficulty_contract=(
                dict(difficulty) if isinstance(difficulty, dict) else {}
            ),
            asset_refs=_unique([
                *block.asset_refs,
                *[
                    ref
                    for fragment in block_fragments
                    for ref in getattr(fragment, "asset_refs", [])
                ],
            ]),
            objective_refs=_unique([
                *block.objective_refs,
                *[
                    ref
                    for fragment in block_fragments
                    for ref in getattr(fragment, "objective_refs", [])
                ],
            ]),
            concept_refs=_unique([
                *block.concept_refs,
                *[
                    ref
                    for fragment in block_fragments
                    for ref in getattr(fragment, "concept_refs", [])
                ],
            ]),
            evidence_refs=_unique([
                *block.evidence_refs,
                *[
                    ref
                    for fragment in block_fragments
                    for ref in getattr(fragment, "evidence_refs", [])
                ],
            ]),
            knowledge_binding_status=str(
                payload.get("knowledge_binding_status") or ""
            ),
            adapter_type=(
                "v16_structured" if structured else "legacy_compatible"
            ),
            classification_confidence=(
                1.0
                if structured
                else 0.75
                if role != "concept"
                else 0.45
            ),
            classification_source=(
                "module_and_block_role"
                if structured
                else "legacy_block_role"
                if role != "concept"
                else "legacy_heading_fallback"
            ),
            fallback_reason=("" if structured else "v16_metadata_absent"),
        ))

    fragments_by_id = {
        fragment.fragment_id: fragment
        for fragment in fragments
    }
    by_section: dict[str, list[PptSemanticUnitV2]] = defaultdict(list)
    for unit in units:
        by_section[unit.section_id].append(unit)
    bound_units: list[PptSemanticUnitV2] = []
    for section_units in by_section.values():
        last_question_ids: list[str] = []
        for unit in sorted(section_units, key=lambda item: item.source_ordinal):
            if unit.primary_role in {"activity", "checkpoint"}:
                question_fragment_ids = [
                    fragment_id
                    for fragment_id in unit.fragment_ids
                    if (
                        fragment_id in fragments_by_id
                        and fragments_by_id[fragment_id].kind != "heading"
                        and (
                            "?" in str(fragments_by_id[fragment_id].text or "")
                            or "？" in str(
                                fragments_by_id[fragment_id].text or ""
                            )
                        )
                    )
                ]
                if not question_fragment_ids:
                    question_fragment_ids = [
                        fragment_id
                        for fragment_id in unit.fragment_ids
                        if (
                            fragment_id in fragments_by_id
                            and fragments_by_id[fragment_id].kind == "list_item"
                        )
                    ]
                if not question_fragment_ids:
                    question_fragment_ids = next((
                        [fragment_id]
                        for fragment_id in unit.fragment_ids
                        if (
                            fragment_id in fragments_by_id
                            and fragments_by_id[fragment_id].kind != "heading"
                        )
                    ), [unit.fragment_ids[0]])
                last_question_ids = [
                    stable_hash(
                        {
                            "semantic_unit_id": unit.semantic_unit_id,
                            "fragment_id": fragment_id,
                            "role": "question",
                        },
                        prefix="pptq_",
                    )
                    for fragment_id in question_fragment_ids
                ]
                unit = unit.model_copy(update={"question_ids": last_question_ids})
            elif unit.primary_role == "feedback" and last_question_ids:
                unit = unit.model_copy(update={
                    "answer_for_question_ids": list(last_question_ids),
                    "answer_source": "source",
                })
            bound_units.append(unit)
    return sorted(bound_units, key=lambda item: item.source_ordinal)


def semantic_unit_index(
    units: list[PptSemanticUnitV2],
) -> dict[str, PptSemanticUnitV2]:
    return {
        fragment_id: unit
        for unit in units
        for fragment_id in unit.fragment_ids
    }


def semantic_group_kind(unit: PptSemanticUnitV2) -> str:
    if unit.primary_role in {"orientation", "objective", "prerequisite"}:
        return "navigation"
    if unit.primary_role == "summary" or unit.presentation_intent == "recap":
        return "recap"
    if unit.primary_role == "feedback":
        return "feedback"
    if unit.primary_role in {"activity", "checkpoint"}:
        return "practice"
    if unit.primary_role == "example":
        return "worked"
    if unit.primary_role in {"application", "transfer"}:
        return "application"
    if unit.primary_role in {
        "counterexample",
        "misconception",
        "remediation",
    }:
        return "misconception"
    if unit.presentation_intent == "process":
        return "method"
    if unit.primary_role == "reasoning" or unit.presentation_intent == "mechanism":
        return "reasoning"
    return "concept"
