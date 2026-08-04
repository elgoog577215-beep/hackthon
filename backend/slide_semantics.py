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

PPT_SEMANTIC_COMPILER_VERSION = "ppt_teaching_semantics_v2.0"
DOMAIN_PRESENTATION_PROFILE_VERSION = "domain_presentation_profiles_v1.0"

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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DomainPresentationProfileV1(_StrictModel):
    profile_id: str
    module_prefixes: list[str] = Field(default_factory=list)
    module_intents: dict[str, PresentationIntent] = Field(default_factory=dict)
    preferred_visual_kinds: dict[PresentationIntent, list[str]] = Field(
        default_factory=dict,
    )


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
) -> DomainPresentationProfileV1:
    return DomainPresentationProfileV1(
        profile_id=profile_id,
        module_prefixes=[prefix] if prefix else [],
        module_intents=intents,
        preferred_visual_kinds={
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
        },
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
    _profile("engineering_programming", "engineering_", {
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
    }),
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
