import json
from copy import deepcopy

import pytest

from assessment_generation_policy import resolve_assessment_generation_policy
from assessment_orchestrator import UniversalAssessmentModel


def context(slot_id="slot-a"):
    return {
        "assessment_slot": {
            "slot_id": slot_id,
            "assessment_binding_schema": "atomic_assessment_v1",
            "input_mode": "choice",
            "knowledge": ["目标规则"],
        }
    }


def plan():
    return {
        "public_material": "给定输入5",
        "ask": "结果是多少？",
        "target_rule": "目标规则",
        "incorrect_rule": "仅改变目标规则",
        "correct_prediction": "2",
        "incorrect_prediction": "3",
        "trace": "保持输入5，分别得到2和3",
        "options": ["2", "3"],
        "correct_option_index": 0,
    }


@pytest.mark.asyncio
async def test_atomic_generator_designs_before_rendering_without_mutating_context():
    model = object.__new__(UniversalAssessmentModel)
    seen = []

    async def call(policy, prompt, **kwargs):
        seen.append((policy.stage, prompt))
        if policy.stage == "design":
            return json.dumps({"plans": [{"slot_id": "slot-a", "plan": plan()}]})
        return json.dumps({"question_spec": {}, "solution": {}})

    model._assessment_llm_call = call
    ctx = context()
    before = deepcopy(ctx)
    result = await model.generate_candidate(
        ctx, call_policy=resolve_assessment_generation_policy(None).call_policy("generate", ctx)
    )
    assert [s for s, _ in seen] == ["design"]
    assert result["question_spec"]["stimulus"]["rendered_text"] == plan()["public_material"]
    assert result["solution"]["measurement_plan"]["correct_prediction"] == "2"
    assert ctx == before


@pytest.mark.asyncio
async def test_legacy_generator_does_not_add_design_call():
    model = object.__new__(UniversalAssessmentModel)
    stages = []

    async def call(policy, prompt, **kwargs):
        stages.append(policy.stage)
        return '{"question_spec":{},"solution":{}}'

    model._assessment_llm_call = call
    await model.generate_candidate({}, call_policy=resolve_assessment_generation_policy(None).call_policy("generate"))
    assert stages == ["generate"]


def test_design_mapping_rejects_cross_slot_or_duplicate_plans():
    from assessment_measurement_design import attach_measurement_designs
    from ai_base import AIProviderRequestError

    for entries in ([], [{"slot_id": "other", "plan": plan()}], [{"slot_id": "slot-a", "plan": plan()}] * 2):
        with pytest.raises(AIProviderRequestError):
            attach_measurement_designs([context()], {"plans": entries})


def test_recovery_routes_by_failed_artifact_not_by_knowledge_id():
    from assessment_measurement_design import evidence_recovery_action

    assert evidence_recovery_action(["TRACE_CONTROL_STRUCTURE_CHANGED"], validation_passed=True) == "review"
    assert evidence_recovery_action(["OPERATOR_FIXITY_CONTRADICTION"], validation_passed=True) == "solve"
    assert evidence_recovery_action(["ANSWER_RULE_DISCLOSED"], validation_passed=True) == "author"
    assert evidence_recovery_action(["TRACE_CONTROL_STRUCTURE_CHANGED"], validation_passed=False) == "author"
    assert evidence_recovery_action(["OBSERVATION_NOT_DISCRIMINATING"], validation_passed=True) == "author"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_artifact", ["review", "solve", "review_persistent"])
async def test_recovery_keeps_question_and_retries_responsible_artifact(failed_artifact):
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from backend.tests.test_atomic_assessment import atomic_course, _atomic_model
    from backend.tests.test_assessment_generation_orchestrator import _course
    from question_bank import approved_formal_tasks, build_question_bank

    course = _course()
    course["course_knowledge_base"] = deepcopy(atomic_course()["course_knowledge_base"])
    point = course["course_knowledge_base"]["knowledge_points"][0]
    point.update(
        section_refs=["thermo-1"],
        statement="系统吸热时Q取正，对外做功时W取正。",
        meta_question="识别吸热与做功的正负号约定",
        name="热量和功的符号",
    )
    course["course_knowledge_base"]["knowledge_points"] = [point]
    model = _atomic_model()
    generate = model.generate_candidate

    async def generate_with_plan(ctx):
        candidate = await generate(ctx)
        candidate["solution"]["measurement_plan"] = plan()
        return candidate

    model.generate_candidate = generate_with_plan
    solve = model.solve_candidate

    async def solve_with_error(spec):
        result = await solve(spec)
        if failed_artifact == "solve" and model.solve_calls == 1:
            result["summary"] = "计算核对：1+2+3=9。"
        return result

    model.solve_candidate = solve_with_error
    original = model.evaluate_candidate
    reviews = []

    async def evaluate(*args, **kwargs):
        report = await original(*args, **kwargs)
        reviews.append(deepcopy(args))
        if (len(reviews) == 1 and failed_artifact == "review") or failed_artifact == "review_persistent":
            report["review_witness"]["observation_test"]["public_anchor"] = "invented input"
        return report

    model.evaluate_candidate = evaluate
    prepared = await AssessmentGenerationOrchestrator(model=model).prepare_course(course)
    assert len(approved_formal_tasks(build_question_bank(prepared))) == (
        0 if failed_artifact == "review_persistent" else 1
    )
    assert model.generate_calls == 1
    assert model.solve_calls == (2 if failed_artifact == "solve" else 1)
    assert model.repair_calls == 0
    assert len(reviews) == 2
    assert {k: v for k, v in reviews[0][0].items() if k != "solution_revision_id"} == {
        k: v for k, v in reviews[1][0].items() if k != "solution_revision_id"
    }
    if failed_artifact.startswith("review"):
        assert "review_feedback" in reviews[1][3]
    else:
        assert "EXPLANATION_ARITHMETIC_ERROR" in model.solve_payloads[1]["explanation_revision_issues"]
    assert "measurement_plan" not in json.dumps(reviews[0][0])
    bank = build_question_bank(prepared)
    if failed_artifact != "review_persistent":
        assert any(s.get("measurement_plan") == plan() for s in bank["solution_envelopes"].values())


@pytest.mark.asyncio
async def test_batch_design_preserves_slot_mapping():
    model = object.__new__(UniversalAssessmentModel)

    async def call(policy, prompt, **kwargs):
        if policy.stage == "design":
            return json.dumps({"plans": [{"slot_id": s, "plan": {**plan(), "ask": s}} for s in ["b", "a"]]})
        return json.dumps(
            {"candidates": [{"slot_id": s, "candidate": {"question_spec": {}, "solution": {}}} for s in ["a", "b"]]}
        )

    model._assessment_llm_call = call
    result = await model.generate_candidate_batch(
        [context("a"), context("b")], call_policy=resolve_assessment_generation_policy(None).call_policy("generate")
    )
    assert result["a"]["solution"]["measurement_plan"]["ask"] == "a"
    assert result["b"]["solution"]["measurement_plan"]["ask"] == "b"


@pytest.mark.parametrize("response", [{"plans": [None]}, {"plans": [{"slot_id": "slot-a", "plan": {}}]}])
def test_malformed_design_is_not_silently_used(response):
    from assessment_measurement_design import attach_measurement_designs
    from ai_base import AIProviderRequestError

    with pytest.raises(AIProviderRequestError):
        attach_measurement_designs([context()], response)


def test_renderer_never_guesses_unsupported_answer_shape():
    from assessment_measurement_design import candidate_from_measurement_design

    c = {**context(), "private_measurement_design": plan()}
    assert candidate_from_measurement_design(c)["solution"]["canonical_answer"] == "A"
    c["private_measurement_design"]["correct_option_index"] = True
    assert candidate_from_measurement_design(c) is None
    c["assessment_slot"]["input_mode"] = "code"
    assert candidate_from_measurement_design(c) is None


def test_optional_null_solver_contract_does_not_waste_generation_attempt():
    from assessment_orchestrator import _normalize_candidate_layout

    candidate, receipt = _normalize_candidate_layout({"question_spec": {"solver_contract": None}})
    assert candidate["question_spec"]["solver_contract"] == {}
    assert receipt


def test_short_complete_task_does_not_require_padding_or_regeneration():
    from assessment_measurement_design import candidate_from_measurement_design
    from assessment_orchestrator import _contract_from_candidate

    design = {**plan(), "public_material": "```c\nint x = -7 / 2;\n```", "ask": "x的值是多少？"}
    candidate = candidate_from_measurement_design({**context(), "private_measurement_design": design})
    assert candidate["question_spec"]["task"]["rendered_text"] == design["ask"]
    base = {"question_spec": {}, "solution_envelope": {"validation_mode": "exact_validator"}}
    assert _contract_from_candidate(base, candidate)["question_spec"]["task"]["rendered_text"] == design["ask"]
    candidate["question_spec"]["task"]["rendered_text"] = "  "
    from ai_base import AIProviderRequestError

    with pytest.raises(AIProviderRequestError, match="not_concrete"):
        _contract_from_candidate(base, candidate)


def test_observation_strategy_follows_rule_not_point_id():
    from assessment_measurement_design import measurement_strategy

    a = {"primary_knowledge_ids": ["unseen-id"], "knowledge": ["首个分支命中后，不再对后续条件求值。"]}
    b = {"primary_knowledge_ids": ["another-id"], "knowledge": list(a["knowledge"])}
    assert measurement_strategy(a) == measurement_strategy(b)
    assert measurement_strategy(a)["kind"] == "condition_evaluation_trace"
    assert measurement_strategy({"knowledge": ["else归属到语法允许的最近if"]})["kind"] == "syntactic_binding"
    assert measurement_strategy({"knowledge": ["continue之后执行for更新部分"]})["kind"] == "next_control_action"
    assert measurement_strategy({"knowledge": ["break退出时不做迭代部分"]})["kind"] == "exit_state"
    assert measurement_strategy({"knowledge": ["显式转换的位置决定操作数"]})["kind"] == "conversion_scope"
    assert measurement_strategy({"knowledge": ["封闭系统能量守恒"]})["kind"] == "direct_value"


def test_one_line_c_statement_is_real_visible_code_not_a_placeholder():
    from assessment_quality import _code_rendering_valid

    c = {"question_spec": {"stimulus": {"rendered_text": "```c\ndouble d = 5 / 2;\n```"},
                           "task": {"rendered_text": "执行上述代码后，d是多少？"}}}
    assert _code_rendering_valid(c)
    for text in ("```c\n\n```", "```c\n待补全\n```", "double d = 5 / 2;"):
        c["question_spec"]["stimulus"]["rendered_text"] = text
        assert not _code_rendering_valid(c)
