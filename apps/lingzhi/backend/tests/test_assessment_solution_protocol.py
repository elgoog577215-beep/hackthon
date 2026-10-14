from copy import deepcopy

from assessment_orchestrator import AssessmentGenerationOrchestrator, _apply_independent_validation
from assessment_independent_solvers import IndependentSolverRegistry


def example():
    contract = {
        "question_type": "structured_application", "semantic_preflight": {"passed": True},
        "question_spec": {"input_contract": {"mode": "structured_fields"},
            "stimulus": {"rendered_text": "四项成本为2、3、1、5。"},
            "task": {"rendered_text": "求总成本。"},
            "risk_contract": {"risk_level": "low", "requires_teacher_review": False}},
        "solution_envelope": {"canonical_answer": {"conclusion": 8}, "validation_mode": "expert_rubric_validator"},
    }
    independent = {"answer": {"conclusion": 11}, "summary": "逐项计算四次成本，结果为11。",
        "work": [{"title": "加总", "explanation": "公开成本逐项相加：2+3+1+5=11。", "result": "11"}],
        "checks": ["重新求和仍为11"], "option_analysis": [], "common_errors": []}
    validation = {"passed": True, "status": "pending_semantic_review", "validation_mode": "expert_rubric_validator",
                  "deterministic": False, "confidence": 1.0, "requires_teacher_review": True}
    return contract, independent, validation


def test_open_answer_stays_pending_and_does_not_mix_two_solutions():
    contract, independent, validation = example()
    _apply_independent_validation(contract, validation, independent)
    solution = contract["solution_envelope"]
    assert solution["canonical_answer"] == independent["answer"]
    assert solution["worked_solution"]["final_answer"] == independent["answer"]
    assert solution["author_answer_proposal"] == {"conclusion": 8}
    assert solution["independent_solution_record"]["answer"] == independent["answer"]
    assert contract["solution_validation"]["passed"] is False
    assert contract["solution_validation"]["checks"]["independent_agreement"] is None


def test_open_solution_graph_uses_the_same_independent_derivation():
    contract, independent, validation = example()
    author_graph = {"schema_version": "solution_graph_v1", "steps": [
        {"step_id": "step_1", "action": "2+3+1+5=8", "check": "8"}]}
    contract["solution_envelope"]["solution_graph"] = deepcopy(author_graph)
    _apply_independent_validation(contract, validation, independent)
    solution = contract["solution_envelope"]
    assert solution["author_solution_graph_proposal"] == author_graph
    assert solution["solution_graph"]["steps"][0]["action"] == independent["work"][0]["explanation"]
    assert solution["solution_graph"]["steps"][0]["check"] == "11"


def test_public_preflight_defers_answer_evidence_until_the_solution_exists():
    from assessment_semantics import evaluate_question_semantic_preflight
    contract = {"question_type": "debugging_trace", "question_spec": {
        "stimulus": {"rendered_text": "```c\nint f(int x) { return x - 1; }\n```"},
        "task": {"rendered_text": "f应返回x加1，定位错误并修复、复验。"}},
        "solution_envelope": {"validation_mode": "expert_rubric_validator", "canonical_answer": "待独立求解"}}
    public = evaluate_question_semantic_preflight(contract, require_solution_evidence=False)
    assert public["passed"]
    complete = evaluate_question_semantic_preflight(contract)
    assert not complete["passed"], "deferral must not bypass the final evidence check"
    contract["solution_envelope"]["canonical_answer"] = "错误位置为return：原因是减法。修复为return x + 1；复验x=2得到3。"
    contract["solution_envelope"]["solution_graph"] = {"steps": [{"step_id": "s1", "action": "修复并复验", "check": "3"}]}
    assert evaluate_question_semantic_preflight(contract)["passed"]


async def test_review_sees_exact_deliverable_and_its_attestation_expires_after_mutation():
    from assessment_solution_protocol import final_solution_review_valid
    contract, independent, validation = example()
    _apply_independent_validation(contract, validation, independent)
    seen = {}
    class Reviewer:
        async def evaluate_candidate(self, spec, payload, objective, slot):
            seen.update(deepcopy(payload))
            return {"passed": True, "solution_consistent": True, "confidence": 0.95, "issues": [],
                    "evidence": ["最终答案11与逐项计算及公开条件一致"], "dimensions": {}}
    report = await AssessmentGenerationOrchestrator(model=Reviewer())._semantic_report(
        contract, independent=independent, objective={}, slot={}, audit={"semantic_evaluation_calls": 0})
    assert seen["delivery_solution"]["canonical_answer"] == {"conclusion": 11}
    assert seen["author_answer_proposal"] == {"conclusion": 8}
    assert report["passed"] is True and final_solution_review_valid(contract)
    assert contract["solution_validation"]["passed"] is True
    contract["solution_envelope"]["worked_solution"]["summary"] = "总成本为8。"
    assert not final_solution_review_valid(contract)


async def test_reviewer_cannot_approve_a_deliverable_changed_during_review():
    from assessment_solution_protocol import final_solution_review_valid
    contract, independent, validation = example()
    _apply_independent_validation(contract, validation, independent)
    class MutatingReviewer:
        async def evaluate_candidate(self, *args):
            contract["solution_envelope"]["canonical_answer"] = {"conclusion": 9}
            return {"passed": True, "solution_consistent": True, "confidence": 1.0, "issues": [], "dimensions": {}}
    report = await AssessmentGenerationOrchestrator(model=MutatingReviewer())._semantic_report(
        contract, independent=independent, objective={}, slot={}, audit={"semantic_evaluation_calls": 0})
    assert not report["passed"]
    assert not final_solution_review_valid(contract)
    assert not contract["solution_validation"]["passed"]


def test_calculator_does_not_attest_an_unbound_generator_expression():
    registry = IndependentSolverRegistry.with_builtin_solvers()
    assert registry.solve({"input_contract": {"mode": "numeric_unit"},
        "stimulus": {"rendered_text": "原有100件，取走40件。"}, "task": {"rendered_text": "剩余多少件？"},
        "solver_contract": {"kind": "numeric_expression", "expression": "100+40"}}) is None


def test_calculator_only_accepts_the_expression_asked_in_the_public_task():
    registry = IndependentSolverRegistry.with_builtin_solvers()
    spec = {"input_contract": {"mode": "numeric_unit"}, "task": {"rendered_text": "计算 20-8，单位 kJ。"},
            "solver_contract": {"kind": "numeric_expression", "expression": "20-8", "unit": "kJ"}}
    assert registry.solve(spec)["answer"] == {"value": 12, "unit": "kJ"}
    spec["solver_contract"]["expression"] = "20+8"
    assert registry.solve(spec) is None


def test_incomplete_independent_work_is_not_filled_from_the_authors_explanation():
    from assessment_solution_protocol import final_solution_review_valid
    contract, independent, validation = example()
    contract["solution_envelope"]["worked_solution"] = {
        "summary": "原作者声称结果为8且提供了完整但错误的过程。", "steps": ["把2+3+1+5错误地相加成8。"],
        "final_answer": {"conclusion": 8}, "checks": ["作者自查"]}
    independent["work"] = []
    _apply_independent_validation(contract, validation, independent)
    assert contract["solution_envelope"]["worked_solution"]["steps"] == []
    assert not final_solution_review_valid(contract)


async def test_batch_review_uses_the_same_complete_delivery_payload():
    from assessment_orchestrator import _SemanticEvaluationBatcher
    from assessment_solution_protocol import final_solution_review_valid
    contract, independent, validation = example()
    _apply_independent_validation(contract, validation, independent)
    captured = []
    class BatchReviewer:
        async def evaluate_candidate_batch(self, items):
            captured.extend(deepcopy(items))
            return {item["slot_id"]: {"passed": True, "solution_consistent": True, "confidence": 1.,
                                      "issues": [], "dimensions": {}} for item in items}
    audit = {"semantic_evaluation_calls": 0, "batch_semantic_evaluation_calls": 0}
    model = BatchReviewer()
    batcher = _SemanticEvaluationBatcher(model=model, audit=audit, max_batch_size=1)
    await AssessmentGenerationOrchestrator(model=model)._semantic_report(
        contract, independent=independent, objective={}, slot={"slot_id": "s1"}, audit=audit, semantic_batcher=batcher)
    assert captured[0]["independent_solution"]["delivery_solution"]["worked_solution"]["final_answer"] == {"conclusion": 11}
    assert final_solution_review_valid(contract)


async def test_publication_rejects_a_reviewed_question_mutated_after_acceptance():
    import pytest
    from assessment_solution_protocol import attest_final_solution_review, delivery_hash
    from routers.question_bank import _require_complete_generation
    contract, independent, validation = example()
    _apply_independent_validation(contract, validation, independent)
    attest_final_solution_review(contract, {"passed": True, "solution_consistent": True, "confidence": 1.}, delivery_hash(contract))
    contract["question_spec"]["task"]["rendered_text"] = "Changed question after review"
    with pytest.raises(RuntimeError, match="final_solution_review"):
        _require_complete_generation({"_assessment_generated_contracts": {"node": {"practice": contract}}})
