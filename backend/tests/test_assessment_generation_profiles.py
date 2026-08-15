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


def test_local_solver_returns_none_on_unparsable_expression() -> None:
    """表达式解析不了要返回 None，**不能让 SyntaxError 逃出去**。

    来自 lz-web-search 的复核补丁（~/patches-for-w11/0001-fix-SyntaxError.patch）。
    真机取证实测：模型给数值题写的 `expression` 经常带单位（"150 J - 60 J"）
    或写成等式（"ΔU = 20 - 8"）。`ast.parse` 对这些抛 `SyntaxError`，而它
    **不是** `ValueError` 的子类——改动前它会穿透 `solve()` 把整个槽位打死
    （`attempts: []` + `final_decision: discard`，一次生成尝试都没发生），
    在审计里看起来像"模型出不了题"。

    这是我在 M1 打开本地解题器时埋下的：`d2b49905` 的闸门让 choice/blanks
    绕开了它，但 `numeric_unit` 仍会走进去，而带单位正是数值题最自然的写法。
    """
    registry = IndependentSolverRegistry.with_builtin_solvers()

    for expression in ("150 J - 60 J", "ΔU = 20 - 8", "20 kJ", "12 +"):
        assert registry.solve({
            "input_contract": {"mode": "numeric_unit"},
            "solver_contract": {
                "kind": "numeric_expression",
                "expression": expression,
                "unit": "kJ",
            },
        }) is None, f"{expression!r} 应返回 None 而不是抛异常"

    # 修完之后合法表达式仍要照常求解（别把闸门关死了）。
    assert registry.solve({
        "input_contract": {"mode": "numeric_unit"},
        "solver_contract": {
            "kind": "numeric_expression",
            "expression": "150 - 60",
            "unit": "J",
        },
    })["answer"] == {"value": 90, "unit": "J"}


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


# --- G3：按题的模型求解预算 -------------------------------------------------


def test_both_profiles_bound_model_solving_per_question() -> None:
    """独立求解不能删（它承担真实正确性验证），但必须有按题上限。"""
    deliberate = resolve_assessment_generation_policy("deliberate")
    fast = resolve_assessment_generation_policy("fast")

    assert deliberate.max_model_solve_calls_per_question == 3
    assert fast.max_model_solve_calls_per_question == 2
    # 预算必须够健康题走完「首轮 + 一轮修复」，否则会误杀正常题
    assert deliberate.max_model_solve_calls_per_question >= 2


def test_solve_budget_counts_one_per_round_not_per_branch() -> None:
    """合批与直连是同一轮求解的两条实现路径，只能扣一次。

    两个分支各扣一次会把一轮算成两次，健康的题也会被误判超预算——我第一版
    就是这么写的，被 test_orchestrator_uses_bounded_repair_and_isolates_solver
    抓住了。
    """
    from assessment_orchestrator import (
        ModelSolveBudgetExhausted,
        _consume_solve_budget,
    )

    budget = {"used": 0, "limit": 2}
    _consume_solve_budget(budget)
    assert budget["used"] == 1
    _consume_solve_budget(budget)
    assert budget["used"] == 2

    try:
        _consume_solve_budget(budget)
    except ModelSolveBudgetExhausted as exc:
        assert exc.used == 2
        assert exc.limit == 2
    else:
        raise AssertionError("用完预算必须抛出，不能静默继续求解")


def test_solve_budget_is_opt_in() -> None:
    """没传预算（例如诊断链路复用求解）时不设限，行为不变。"""
    from assessment_orchestrator import _consume_solve_budget

    _consume_solve_budget(None)
    unlimited = {"used": 99, "limit": 0}
    _consume_solve_budget(unlimited)
    assert unlimited["used"] == 99
