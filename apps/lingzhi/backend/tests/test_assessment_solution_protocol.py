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
