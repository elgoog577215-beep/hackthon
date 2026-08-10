from __future__ import annotations

from assessment_generation_policy import (
    ASSESSMENT_GENERATION_POLICY_VERSION,
    requires_deliberation,
    resolve_assessment_generation_policy,
)
from assessment_independent_solvers import IndependentSolverRegistry
from models import CourseGenerationRequest
from question_bank_jobs import QuestionBankRebuildJobRepository
from routers.question_bank import QuestionBankRebuildRequest


def test_generation_profile_defaults_preserve_legacy_behavior() -> None:
    course_request = CourseGenerationRequest(subject="线性代数")
    rebuild_request = QuestionBankRebuildRequest()

    assert course_request.assessment_generation_profile == "deliberate"
    assert rebuild_request.assessment_generation_profile == "deliberate"
    assert QuestionBankRebuildRequest(
        assessment_generation_profile="fast"
    ).assessment_generation_profile == "fast"


def test_fast_policy_has_bounded_repairs_and_provider_budget() -> None:
    policy = resolve_assessment_generation_policy("fast")

    assert policy.version == ASSESSMENT_GENERATION_POLICY_VERSION
    assert policy.profile == "fast"
    assert policy.max_generation_attempts == 2
    assert policy.generation_batch_size == 3
    assert policy.solution_batch_size == 2
    assert policy.max_provider_attempts == 1
    assert policy.compact_candidate is True
    assert policy.stage_timeouts == {
        "generate": 45.0,
        "repair": 35.0,
        "solve": 35.0,
        "review": 30.0,
    }


def test_fast_policy_never_requests_thinking_for_complex_items() -> None:
    policy = resolve_assessment_generation_policy("fast")
    context = {
        "assessment_slot": {
            "input_mode": "code",
            "validation_mode": "expert_rubric_validator",
            "multi_step": True,
        },
        "risk_contract": {
            "risk_level": "high",
            "requires_teacher_review": True,
        },
        "issue_codes": ["semantic_contradiction"],
    }

    for stage in ("generate", "repair", "solve", "review"):
        call_policy = policy.call_policy(stage, context)
        assert call_policy.enable_thinking is False
        assert call_policy.thinking_reason_codes == ()


def test_deliberation_is_selective_and_reasoned() -> None:
    simple = requires_deliberation(
        "generate",
        {
            "assessment_slot": {
                "input_mode": "choice",
                "validation_mode": "exact_validator",
            },
        },
    )
    complex_item = requires_deliberation(
        "solve",
        {
            "input_contract": {"mode": "structured_fields"},
            "validation_mode": "expert_rubric_validator",
        },
    )
    structural_repair = requires_deliberation(
        "repair",
        {"issue_codes": ["MODEL_OUTPUT_SCHEMA_INVALID"]},
    )
    semantic_repair = requires_deliberation(
        "repair",
        {"issue_codes": ["independent_solution_mismatch"]},
    )

    assert simple.required is False
    assert simple.reason_codes == ()
    assert complex_item.required is True
    assert set(complex_item.reason_codes) == {
        "complex_input_mode",
        "complex_validation_mode",
    }
    assert structural_repair.required is False
    assert semantic_repair.required is True
    assert semantic_repair.reason_codes == ("semantic_repair",)


def test_global_thinking_switch_vetoes_provider_request(monkeypatch) -> None:
    monkeypatch.setenv("AI_THINKING_ENABLED", "false")

    policy = resolve_assessment_generation_policy("fast")
    call_policy = policy.call_policy(
        "solve",
        {"input_contract": {"mode": "code"}},
    )

    assert call_policy.enable_thinking is False
    assert call_policy.thinking_reason_codes == ()


def test_rebuild_job_identity_and_receipt_include_profile(tmp_path) -> None:
    repository = QuestionBankRebuildJobRepository(tmp_path)

    fast, fast_created = repository.create_job(
        "course-1",
        request_id="request-fast",
        scope="course",
        node_ids=[],
        mode="full",
        actor_id="teacher-1",
        assessment_generation_profile="fast",
    )
    deliberate, deliberate_created = repository.create_job(
        "course-1",
        request_id="request-deliberate",
        scope="course",
        node_ids=[],
        mode="full",
        actor_id="teacher-1",
        assessment_generation_profile="deliberate",
    )

    assert fast_created is True
    assert deliberate_created is True
    assert fast["job_id"] != deliberate["job_id"]
    assert fast["assessment_generation_profile"] == "fast"
    assert deliberate["assessment_generation_profile"] == "deliberate"
    assert fast["assessment_generation_policy_version"] == (
        ASSESSMENT_GENERATION_POLICY_VERSION
    )


def test_local_numeric_solver_uses_only_public_solver_contract() -> None:
    registry = IndependentSolverRegistry.with_builtin_solvers()

    solution = registry.solve({
        "input_contract": {"mode": "numeric_unit"},
        "solver_contract": {
            "kind": "numeric_expression",
            "expression": "20 - 8",
            "unit": "kJ",
        },
    })

    assert solution is not None
    assert solution["answer"] == {"value": 12, "unit": "kJ"}
    assert solution["work"]
    assert solution["checks"]
    assert solution["solver_attested"] is True


def test_local_solver_rejects_unsafe_or_incomplete_contract() -> None:
    registry = IndependentSolverRegistry.with_builtin_solvers()

    assert registry.solve({
        "input_contract": {"mode": "numeric_unit"},
        "solver_contract": {
            "kind": "numeric_expression",
            "expression": "__import__('os').system('whoami')",
            "unit": "kJ",
        },
    }) is None
    assert registry.solve({
        "input_contract": {"mode": "choice"},
    }) is None
