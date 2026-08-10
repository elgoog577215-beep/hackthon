"""Execution policies for fast and deliberate assessment generation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

AssessmentGenerationProfile = Literal["fast", "deliberate"]
AssessmentGenerationScope = Literal[
    "full_generation",
    "scoped_repair",
]

ASSESSMENT_GENERATION_POLICY_VERSION = (
    "assessment_generation_policy_v2"
)

_COMPLEX_INPUT_MODES = {
    "code",
    "structured_fields",
    "rich_text",
}
_COMPLEX_VALIDATION_MODES = {
    "symbolic_validator",
    "expert_rubric_validator",
    "language_rubric_validator",
}
_SEMANTIC_REPAIR_CODES = {
    "independent_solution_mismatch",
    "answer_conflict",
    "semantic_contradiction",
    "TASK_CONDITION_MISSING",
    "OBJECTIVE_MISMATCH",
    "DIFFICULTY_MISMATCH",
    "SOURCE_CONFLICT",
}
_STRUCTURAL_REPAIR_CODES = {
    "MODEL_OUTPUT_SCHEMA_INVALID",
    "invalid_candidate_question_and_solution_objects",
    "invalid_candidate_stimulus_or_task_object",
    "invalid_candidate_constraints_list",
    "invalid_candidate_response_contract_object",
    "invalid_candidate_options_list",
}


@dataclass(frozen=True)
class DeliberationDecision:
    required: bool
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssessmentModelCallPolicy:
    stage: str
    enable_thinking: bool
    thinking_reason_codes: tuple[str, ...]
    timeout_seconds: float | None
    max_provider_attempts: int | None
    compact_candidate: bool
    physical_call_telemetry: list[dict[str, Any]] = field(
        default_factory=list,
        compare=False,
        repr=False,
    )


@dataclass(frozen=True)
class AssessmentGenerationPolicy:
    profile: AssessmentGenerationProfile
    version: str
    max_generation_attempts: int
    generation_batch_size: int
    solution_batch_size: int
    max_provider_attempts: int | None
    compact_candidate: bool
    prefer_local_solver: bool
    stage_timeouts: dict[str, float | None]

    @property
    def max_repairs(self) -> int:
        return self.max_generation_attempts - 1

    def call_policy(
        self,
        stage: str,
        context: dict[str, Any] | None = None,
    ) -> AssessmentModelCallPolicy:
        resolved_context = context or {}
        decision = requires_deliberation(stage, resolved_context)
        if self.profile == "fast":
            decision = DeliberationDecision(False)
        else:
            if stage == "review":
                decision = DeliberationDecision(False)
            elif stage == "generate" and resolved_context.get(
                "batch_generation"
            ):
                decision = DeliberationDecision(
                    True,
                    ("deliberate_batch_generation",),
                )
        if not _global_thinking_enabled():
            decision = DeliberationDecision(False)
        return AssessmentModelCallPolicy(
            stage=stage,
            enable_thinking=decision.required,
            thinking_reason_codes=decision.reason_codes,
            timeout_seconds=self.stage_timeouts.get(stage),
            max_provider_attempts=self.max_provider_attempts,
            compact_candidate=self.compact_candidate,
        )


def normalize_assessment_generation_profile(
    value: str | None,
) -> AssessmentGenerationProfile:
    normalized = str(value or "deliberate").strip().lower()
    if normalized not in {"fast", "deliberate"}:
        raise ValueError(
            "assessment_generation_profile must be fast or deliberate"
        )
    return normalized  # type: ignore[return-value]


def resolve_assessment_generation_policy(
    profile: str | None,
) -> AssessmentGenerationPolicy:
    normalized = normalize_assessment_generation_profile(profile)
    if normalized == "fast":
        return AssessmentGenerationPolicy(
            profile="fast",
            version=ASSESSMENT_GENERATION_POLICY_VERSION,
            max_generation_attempts=2,
            generation_batch_size=3,
            solution_batch_size=2,
            max_provider_attempts=1,
            compact_candidate=True,
            prefer_local_solver=True,
            stage_timeouts={
                "generate": 45.0,
                "repair": 35.0,
                "solve": 35.0,
                "review": 30.0,
            },
        )
    return AssessmentGenerationPolicy(
        profile="deliberate",
        version=ASSESSMENT_GENERATION_POLICY_VERSION,
        max_generation_attempts=4,
        generation_batch_size=2,
        solution_batch_size=1,
        max_provider_attempts=None,
        compact_candidate=False,
        # 本地确定性解题器在 deliberate 档也开。
        #
        # 它不是"快但不准"的近似：`IndependentSolverRegistry.solve` 只在题目
        # 自带 `solver_contract.kind` 且命中已注册的确定性解法时才返回结果，
        # 解不出、算不动、结果不完整都返回 None 并原样落回模型求解
        # （`assessment_orchestrator._solve_and_build`）。所以打开它只会把
        # "本来就能被确定性算清的题"从模型手里接走，不会降低任何题的验证强度。
        #
        # 反过来说，deliberate 档关掉它并不换来更强的正确性——只是让模型把
        # 同一道算术题再算一遍，这正是"6 道题 42 次请求"里最没有信息量的那部分。
        prefer_local_solver=True,
        stage_timeouts={
            "generate": None,
            "repair": None,
            "solve": None,
            "review": None,
        },
    )


def requires_deliberation(
    stage: str,
    context: dict[str, Any],
) -> DeliberationDecision:
    """Return whether a call needs reasoning and auditable reason codes."""

    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage in {"semantic_preflight", "local_solver"}:
        return DeliberationDecision(False)

    issue_codes = {
        str(value)
        for value in (
            context.get("issue_codes")
            or _issue_codes(context.get("quality_report"))
        )
        if str(value)
    }
    if normalized_stage == "repair":
        if issue_codes and issue_codes <= _STRUCTURAL_REPAIR_CODES:
            return DeliberationDecision(False)
        if issue_codes & _SEMANTIC_REPAIR_CODES:
            return DeliberationDecision(True, ("semantic_repair",))

    input_mode = _first_non_empty(
        ((context.get("assessment_slot") or {}).get("input_mode")),
        ((context.get("input_contract") or {}).get("mode")),
        (
            ((context.get("question_spec") or {}).get("input_contract") or {})
            .get("mode")
        ),
    )
    validation_mode = _first_non_empty(
        ((context.get("assessment_slot") or {}).get("validation_mode")),
        context.get("validation_mode"),
        (
            (context.get("solution_envelope") or {}).get(
                "validation_mode"
            )
        ),
    )
    reasons: list[str] = []
    if input_mode in _COMPLEX_INPUT_MODES:
        reasons.append("complex_input_mode")
    if validation_mode in _COMPLEX_VALIDATION_MODES:
        reasons.append("complex_validation_mode")

    slot = context.get("assessment_slot") or context.get("slot") or {}
    design = context.get("design_brief") or {}
    risk = (
        context.get("risk_contract")
        or (context.get("question_spec") or {}).get("risk_contract")
        or {}
    )
    archetype = str(
        slot.get("archetype_id")
        or design.get("archetype_id")
        or (context.get("question_spec") or {}).get("archetype_id")
        or ""
    )
    if (
        archetype == "integrated_performance"
        or bool(slot.get("multi_step"))
        or bool(design.get("multi_step"))
    ):
        reasons.append("complex_task")
    if (
        str(risk.get("risk_level") or "low") not in {"", "low"}
        or bool(risk.get("requires_teacher_review"))
    ):
        reasons.append("high_risk")

    reference = context.get("reference_summary") or {}
    if (
        bool(reference.get("has_conflicts"))
        or str(reference.get("source_confidence") or "").lower()
        in {"low", "conflicted"}
    ):
        reasons.append("source_uncertainty")

    return DeliberationDecision(
        bool(reasons),
        tuple(dict.fromkeys(reasons)),
    )


def _first_non_empty(*values: Any) -> str:
    return next(
        (str(value).strip() for value in values if str(value or "").strip()),
        "",
    )


def _issue_codes(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [
        str(item.get("code") or "")
        for item in value.get("issues") or []
        if isinstance(item, dict) and item.get("code")
    ]


def _global_thinking_enabled() -> bool:
    return str(
        os.getenv("AI_THINKING_ENABLED", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "ASSESSMENT_GENERATION_POLICY_VERSION",
    "AssessmentGenerationPolicy",
    "AssessmentGenerationProfile",
    "AssessmentGenerationScope",
    "AssessmentModelCallPolicy",
    "DeliberationDecision",
    "normalize_assessment_generation_profile",
    "requires_deliberation",
    "resolve_assessment_generation_policy",
]
