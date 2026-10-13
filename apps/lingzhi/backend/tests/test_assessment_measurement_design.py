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
    course["assessment_variant_count"] = 1
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
    assert measurement_strategy({"knowledge": ["if后分号是空语句，后续语句独立"]})["kind"] == "uncontrolled_statement"
    assert measurement_strategy({"knowledge": ["封闭系统能量守恒"]})["kind"] == "direct_value"


def test_one_line_c_statement_is_real_visible_code_not_a_placeholder():
    from assessment_quality import _code_rendering_valid

    c = {
        "question_spec": {
            "stimulus": {"rendered_text": "```c\ndouble d = 5 / 2;\n```"},
            "task": {"rendered_text": "执行上述代码后，d是多少？"},
        }
    }
    assert _code_rendering_valid(c)
    for text in ("```c\n\n```", "```c\n待补全\n```", "double d = 5 / 2;"):
        c["question_spec"]["stimulus"]["rendered_text"] = text
        assert not _code_rendering_valid(c)


@pytest.mark.parametrize("predicate", ["flag == 0", "flag <= 0", "flag >= 0", "flag", "flag != 1"])
def test_empty_statement_design_synthesizes_a_discriminating_input(predicate):
    from assessment_measurement_design import synthesize_contrast_input

    p = {
        **plan(),
        "public_material": f"```c\nint flag = 0;\nif ({predicate});\nflag = 5;\n```",
        "options": ["0", "5"],
        "correct_option_index": 1,
    }
    result = synthesize_contrast_input(p, {"kind": "uncontrolled_statement"})
    assert result["correct_prediction"] == "5"
    assert result["incorrect_prediction"] != "5"
    assert result["options"][1] == "5"
    assert result["design_normalization"]["condition_value"] is False
    assert result["design_normalization"]["original_material"] == p["public_material"]
    assert p["public_material"].startswith("```c\nint flag = 0;")
    import re

    value = int(re.search(r"int flag = (-?\d+);", result["public_material"])[1])
    actual = {
        "flag == 0": value == 0,
        "flag <= 0": value <= 0,
        "flag >= 0": value >= 0,
        "flag": value != 0,
        "flag != 1": value != 1,
    }[predicate]
    assert actual is False
    assert int(result["incorrect_prediction"]) == value


def test_contrast_synthesis_does_not_guess_complex_c_or_nondecimal_literals():
    from assessment_measurement_design import synthesize_contrast_input

    for code in [
        "int flag=0; if (f(flag)); flag=5;",
        "int flag=010; if(flag); flag=5;",
        "int flag=0; if(flag!=0); flag=0;",
    ]:
        p = {**plan(), "public_material": f"```c\n{code}\n```"}
        assert synthesize_contrast_input(p, {"kind": "uncontrolled_statement"}) == p


def test_contrast_synthesis_handles_separate_condition_and_observed_variables():
    from assessment_measurement_design import synthesize_contrast_input

    p = {**plan(), "public_material": "```c\nint c = 0;\nint out = 5;\nif(c>=0);\nout=5;\n```", "options": ["5", "0"]}
    fixed = synthesize_contrast_input(p, {"kind": "uncontrolled_statement"})
    assert "int c = -1;" in fixed["public_material"]
    assert "int out = 6;" in fixed["public_material"]
    assert fixed["correct_prediction"] == "5"
    assert fixed["incorrect_prediction"] == "6"


def test_exit_observation_keeps_for_local_counter_alive_after_the_loop():
    from assessment_measurement_design import normalize_exit_observation

    p = {
        **plan(),
        "public_material": "```c\nint main(void) { for (int k = 0; k < 10; k += 3) { if(k==3) break; } return 0; }\n```",
        "ask": "程序结束时k是多少？",
    }
    fixed = normalize_exit_observation(p, {"kind": "exit_state"})
    assert "int k = 0;" in fixed["public_material"]
    assert "for (; k < 10; k += 3)" in fixed["public_material"]
    assert "变量 k" in fixed["ask"] and "所在语句块内" in fixed["ask"]
    assert fixed["design_normalization"]["original_material"] == p["public_material"]
    for code in [
        "int k=8; for(int k=0;k<2;k++){break;}",
        "for(int k=f();k<2;k++){break;}",
        "int flag=1;if(flag) for(int k=0;k<2;k++){break;}",
    ]:
        unsupported = {**p, "public_material": "```c\n" + code + "\n```"}
        assert normalize_exit_observation(unsupported, {"kind": "exit_state"}) == unsupported


def test_continue_observation_is_derived_from_actual_for_header():
    from assessment_measurement_design import normalize_control_action

    p = {**plan(), "public_material": "```c\nfor(int k=0;k<8;k+=2){if(k==2)continue;}\n```"}
    fixed = normalize_control_action(p, {"kind": "next_control_action"})
    assert fixed["public_material"] == "```c\nfor(int k=0;k<8;k+=2){continue;}\n```"
    assert fixed["design_normalization"]["original_material"] == p["public_material"]
    assert "k+=2" in fixed["correct_prediction"] and "k<8" in fixed["correct_prediction"]
    assert "不执行" in fixed["incorrect_prediction"]
    assert "控制流顺序" in fixed["ask"]
    nested = {**p, "public_material": "```c\nfor(int k=0;k<8;k++){while(x){continue;}}\n```"}
    assert normalize_control_action(nested, {"kind": "next_control_action"}) == nested


def test_generated_empty_statement_material_defines_its_observed_variable():
    from assessment_measurement_design import synthesize_contrast_input

    p = {**plan(), "public_material": "```c\nint n=5;\nif(n>10);\ny=0;\n```", "options": ["0", "1"]}
    fixed = synthesize_contrast_input(p, {"kind": "uncontrolled_statement"})
    assert "int y = 1;" in fixed["public_material"]
    assert fixed["correct_prediction"] == "0" and fixed["incorrect_prediction"] == "1"


def test_conversion_question_observes_scope_instead_of_a_lossy_destination():
    from assessment_measurement_design import normalize_conversion_observation

    for expr, timing in [("(double)a / b", "之前"), ("(double)(a / b)", "之后")]:
        p = {**plan(), "public_material": f"```c\nint a=7,b=2; int result={expr};\n```"}
        fixed = normalize_conversion_observation(p, {"kind": "conversion_scope"})
        assert expr in fixed["ask"]
        assert timing in fixed["correct_prediction"]
        assert "result" not in fixed["ask"]


def test_assignment_question_isolates_the_literal_initialization():
    from assessment_measurement_design import normalize_assignment_observation

    p = {**plan(), "public_material": "```c\nint i=1; int r=(int)(i/2.0); double q=7/2;\n```"}
    fixed = normalize_assignment_observation(p, {"kind": "assignment_sequence"})
    assert fixed["public_material"] == "```c\ndouble q=7/2;\n```"
    assert "整数" in fixed["correct_prediction"]
    assert "q" in fixed["ask"]
