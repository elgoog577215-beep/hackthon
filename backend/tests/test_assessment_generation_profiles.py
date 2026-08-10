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


# --- M1：本地确定性解题器在 deliberate 档也生效 -----------------------------


def test_deliberate_profile_prefers_the_local_solver() -> None:
    """生产用的 deliberate 档此前把本地解题器关着，每道题都要模型再解一遍。

    打开它不降低验证强度：解题器只在题目自带可确定性求解的 solver_contract
    时才接手，解不出就落回模型求解。
    """
    deliberate = resolve_assessment_generation_policy("deliberate")
    fast = resolve_assessment_generation_policy("fast")

    assert deliberate.prefer_local_solver is True
    assert fast.prefer_local_solver is True


def test_local_solver_still_declines_anything_it_cannot_prove() -> None:
    """开关打开不等于放宽判定：解不了的一律返回 None，交回模型求解。"""
    registry = IndependentSolverRegistry.with_builtin_solvers()

    # 没有 solver_contract
    assert registry.solve({"input_contract": {"mode": "short_text"}}) is None
    # kind 不认识
    assert registry.solve({
        "solver_contract": {"kind": "essay_judgement", "expression": "1 + 1"},
    }) is None
    # kind 认识但表达式不可确定性求值
    assert registry.solve({
        "solver_contract": {"kind": "numeric_expression", "expression": "x + 1"},
    }) is None
    # 结果非有限
    assert registry.solve({
        "solver_contract": {"kind": "numeric_expression", "expression": "1 / 0"},
    }) is None


def test_registry_exposes_its_registered_kinds() -> None:
    registry = IndependentSolverRegistry.with_builtin_solvers()
    assert registry.kinds() == ("numeric_expression", "state_operations")


def test_generation_prompt_names_exactly_the_registered_solver_kinds() -> None:
    """防漂移：prompt 里写的 kind 必须与注册表一致。

    模型只会照 schema 填值。如果 prompt 不说有哪些合法 kind（改动前就是
    "Optional public deterministic solver kind" 这种空话），模型会自造一个
    名字，`solve()` 一路返回 None——本地解题器看着是开着的，却永远不生效，
    M1 的收益为零且没人会发现。
    """
    from assessment_orchestrator import _solver_contract_kind_hint

    hint = _solver_contract_kind_hint()
    registered = IndependentSolverRegistry.with_builtin_solvers().kinds()
    for kind in registered:
        assert kind in hint, f"prompt 未告知模型合法 kind：{kind}"
    # 反向：prompt 不得宣传注册表里没有的解法
    for token in ("symbolic_algebra", "code_execution", "essay_judgement"):
        assert token not in hint


def test_generation_schema_carries_the_solver_kind_hint() -> None:
    """两份 schema（中/英）都要带上 kind 提示，不能只改一份。"""
    from assessment_orchestrator import (
        _batch_generation_prompt,
        _generation_prompt_v2,
        _solver_contract_kind_hint,
    )

    hint = _solver_contract_kind_hint()
    context = {
        "assessment_slot": {
            "input_mode": "numeric_unit",
            "validation_mode": "exact_validator",
        },
    }
    single = _generation_prompt_v2(context)
    assert "numeric_expression" in single, "英文 schema 未带合法 kind"

    batch = _batch_generation_prompt([context])
    assert "numeric_expression" in batch, "批量中文 schema 未带合法 kind"
    del hint
