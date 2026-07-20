from __future__ import annotations

from copy import deepcopy

import pytest

from assessment_orchestrator import (
    AssessmentGenerationOrchestrator,
    SemanticPreflightFailure,
)
from assessment_semantics import (
    compile_question_design_brief,
    evaluate_question_semantic_preflight,
)


def _brief(question_type: str) -> dict:
    return compile_question_design_brief(
        objective={
            "objective_id": "obj-1",
            "node_id": "node-1",
            "objective": "Apply Python object semantics",
            "knowledge": ["object identity"],
            "skills": ["trace execution"],
            "misconceptions": ["immutability means every value is copied"],
            "observable_evidence": ["correct final state"],
            "risk_level": "low",
        },
        slot={
            "slot_id": "slot-1",
            "question_type": question_type,
            "input_mode": "choice",
            "validation_mode": "state_trace_validator",
            "risk_level": "low",
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "choice",
            },
        },
        reference_summary={
            "content_covered": True,
            "method_covered": True,
            "content_reference_count": 1,
            "authoring_pattern_count": 1,
        },
        practice_level="concept_check",
        variant_index=0,
    )


def _contract(
    *,
    question_type: str,
    stimulus: str,
    task: str,
    canonical_answer,
    options: list[dict] | None = None,
) -> dict:
    brief = _brief(question_type)
    return {
        "question_type": question_type,
        "design_brief": brief,
        "prompt": f"{stimulus}\n{task}",
        "question_spec": {
            "stimulus": {"rendered_text": stimulus},
            "task": {
                "rendered_text": task,
                "deliverable": "one answer",
            },
            "options": options or [],
            "risk_contract": {
                "risk_level": "low",
                "requires_teacher_review": False,
            },
        },
        "solution_envelope": {
            "canonical_answer": canonical_answer,
            "rubric": ["state the result and verify it"],
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [{
                    "step_id": "trace",
                    "action": "trace the learner-visible material",
                    "check": "compare the final result",
                }],
            },
        },
    }


def test_output_prediction_rejects_concept_question_with_irrelevant_code():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```python\n"
            "items = (1, 2, 3)\n"
            "alias = items\n"
            "```"
        ),
        task=(
            "Which option best reflects the core idea of avoiding side "
            "effects with immutable objects?"
        ),
        canonical_answer="A",
        options=[
            {"id": "A", "text": "Prefer immutable values."},
            {"id": "B", "text": "Always use global variables."},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["passed"] is False
    assert "QUESTION_TYPE_SEMANTIC_MISMATCH" in codes
    assert "MATERIAL_NOT_REQUIRED" in codes


def test_output_prediction_accepts_concrete_observable_result():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```python\n"
            "values = [1, 2]\n"
            "alias = values\n"
            "alias.append(3)\n"
            "print(values)\n"
            "```"
        ),
        task="Predict the exact printed output and explain the alias state.",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "[1, 2, 3]"},
            {"id": "B", "text": "[1, 2]"},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["material_bindings"]


def test_debugging_trace_rejects_false_error_premise():
    contract = _contract(
        question_type="debugging_trace",
        stimulus=(
            "```python\n"
            "values = [1, 2, 3]\n"
            "print(sum(values))\n"
            "```"
        ),
        task="Locate the bug, explain its cause, repair it, and retest.",
        canonical_answer={
            "analysis": "There is no error; the code is correct as written.",
        },
    )

    report = evaluate_question_semantic_preflight(contract)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["passed"] is False
    assert "FALSE_ERROR_PREMISE" in codes


def test_debugging_trace_requires_location_repair_and_retest_evidence():
    contract = _contract(
        question_type="debugging_trace",
        stimulus=(
            "```python\n"
            "def average(values):\n"
            "    return sum(values) / (len(values) - 1)\n"
            "print(average([2, 4, 6]))\n"
            "```"
        ),
        task="Locate the defect, explain its cause, repair it, and retest.",
        canonical_answer={
            "location": "line 2 denominator",
            "cause": "subtracting one uses the wrong item count",
            "repair": "replace len(values) - 1 with len(values)",
            "retest": "the expected result is 4.0",
        },
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True


class _ReviewerCountingModel:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate_candidate(self, *args, **kwargs):
        self.calls += 1
        return {
            "passed": True,
            "confidence": 0.95,
            "solution_consistent": True,
            "dimensions": {},
            "evidence": ["independent semantic review"],
            "issues": [],
        }


class _SolverCountingModel(_ReviewerCountingModel):
    def __init__(self) -> None:
        super().__init__()
        self.solve_calls = 0

    async def solve_candidate(self, public_question_spec):
        self.solve_calls += 1
        return {"answer": "A"}


async def test_semantic_failure_is_blocked_before_independent_solver():
    model = _SolverCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    brief = _brief("output_prediction")
    base = {
        "schema_version": "universal_question_contract_v1",
        "question_type": "output_prediction",
        "design_brief": brief,
        "question_spec": {
            "schema_version": "question_spec_v2",
            "course_id": "course-1",
            "node_id": "node-1",
            "practice_level": "concept_check",
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "choice",
            },
            "risk_contract": {
                "risk_level": "low",
                "requires_teacher_review": False,
            },
            "stimulus": {"rendered_text": "placeholder material"},
            "task": {"rendered_text": "placeholder instruction"},
        },
        "solution_envelope": {
            "schema_version": "solution_envelope_v1",
            "validation_mode": "state_trace_validator",
        },
    }
    candidate = {
        "question_spec": {
            "stimulus": {
                "rendered_text": (
                    "```python\n"
                    "items = (1, 2, 3)\n"
                    "alias = items\n"
                    "```"
                ),
            },
            "task": {
                "rendered_text": (
                    "Which option best reflects the core idea of immutable "
                    "objects in this design?"
                ),
                "deliverable": "one option",
            },
            "constraints": [],
            "response_contract": {"format": "choice"},
            "options": [
                {"id": "A", "text": "avoid side effects"},
                {"id": "B", "text": "use global state"},
            ],
        },
        "solution": {
            "validation_mode": "state_trace_validator",
            "canonical_answer": "A",
            "rubric": ["select the correct concept"],
            "validator_config": {},
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [{
                    "step_id": "concept",
                    "action": "identify the concept",
                    "check": "compare the option",
                }],
            },
        },
    }
    audit = {
        "semantic_preflight_calls": 0,
        "independent_solution_calls": 0,
        "call_timings": [],
    }

    with pytest.raises(SemanticPreflightFailure) as captured:
        await orchestrator._solve_and_build(base, candidate, audit)

    assert model.solve_calls == 0
    assert audit["independent_solution_calls"] == 0
    assert {
        issue["code"]
        for issue in captured.value.report["issues"]
    } >= {
        "QUESTION_TYPE_SEMANTIC_MISMATCH",
        "MATERIAL_NOT_REQUIRED",
    }


async def test_clean_low_risk_deterministic_question_skips_llm_review():
    model = _ReviewerCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    contract = _contract(
        question_type="output_prediction",
        stimulus="```python\nprint(1 + 1)\n```",
        task="Predict the exact printed output.",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "2"},
            {"id": "B", "text": "1"},
        ],
    )
    contract["solution_validation"] = {
        "deterministic": True,
        "passed": True,
    }
    contract["semantic_preflight"] = (
        evaluate_question_semantic_preflight(contract)
    )
    audit = {"semantic_evaluation_calls": 0, "call_timings": []}

    report = await orchestrator._semantic_report(
        contract,
        independent={"answer": "A"},
        objective={"objective_id": "obj-1"},
        slot={"slot_id": "slot-1"},
        audit=audit,
    )

    assert report["passed"] is True
    assert report["reviewer_triggered"] is False
    assert model.calls == 0


async def test_open_or_warned_question_invokes_isolated_llm_review():
    model = _ReviewerCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    contract = _contract(
        question_type="case_analysis",
        stimulus="A short case with two constraints.",
        task="Use both constraints to justify a decision.",
        canonical_answer={"rubric": ["uses both constraints"]},
    )
    contract["solution_validation"] = {
        "deterministic": False,
        "passed": True,
    }
    contract["semantic_preflight"] = {
        "schema_version": "question_semantic_preflight_v1",
        "passed": True,
        "requires_llm_review": True,
        "issues": [],
    }
    audit = {"semantic_evaluation_calls": 0, "call_timings": []}

    report = await orchestrator._semantic_report(
        contract,
        independent={"answer": {"text": "decision"}},
        objective={"objective_id": "obj-1"},
        slot={"slot_id": "slot-1"},
        audit=audit,
    )

    assert report["reviewer_triggered"] is True
    assert model.calls == 1
