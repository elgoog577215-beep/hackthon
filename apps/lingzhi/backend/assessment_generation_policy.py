"""The single complete execution policy for assessment generation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

AssessmentGenerationProfile = Literal["complete"]
AssessmentGenerationScope = Literal[
    "full_generation",
    "scoped_repair",
]

ASSESSMENT_GENERATION_POLICY_VERSION = (
    "assessment_generation_policy_v8"
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
    # 每题累计模型求解调用数，包含格式重试和修正后再次求解。
    # 本地确定性求解不占预算；预算耗尽不能跳过校验或继续重写。
    max_model_solve_calls_per_question: int
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
        if stage == "review":
            decision = DeliberationDecision(False)
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
    normalized = str(value or "complete").strip().lower()
    if normalized not in {"complete", "fast", "deliberate"}:
        raise ValueError(
            "assessment_generation_profile must be complete"
        )
    # `fast` and `deliberate` are accepted only as historical wire values.
    # Every new or resumed job receives the same complete quality policy.
    return "complete"


def resolve_assessment_generation_policy(
    profile: str | None,
) -> AssessmentGenerationPolicy:
    normalize_assessment_generation_profile(profile)
    return AssessmentGenerationPolicy(
        profile="complete",
        version=ASSESSMENT_GENERATION_POLICY_VERSION,
        max_generation_attempts=2,
        generation_batch_size=2,
        solution_batch_size=1,
        # The orchestrator owns the one targeted correction. Transport retries
        # must not multiply each generation, solution and review stage.
        max_provider_attempts=1,
        # 候选生成器只负责锁定题面、答案和验证器；完整教学解析由看不到
        # 生成器答案的独立求解器补全。这样既缩短结构化 JSON，避免 reasoning
        # 吃光正文预算，也让解析天然成为一次独立正确性复核。
        compact_candidate=True,
        max_model_solve_calls_per_question=2,
        # 已注册的确定性解法优先；无法完整求解时才使用模型。
        prefer_local_solver=True,
        stage_timeouts={
            "generate": 150.0,
            "repair": 120.0,
            "solve": 120.0,
            "review": 90.0,
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
