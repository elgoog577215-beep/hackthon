from __future__ import annotations

import pytest

from assessment_validators import validate_candidate_answer


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (
            {"value": 12.5, "unit": "kJ"},
            {"value": 12500, "unit": "J"},
        ),
        (
            {"value": 101.3, "unit": "kPa"},
            {"value": 101300, "unit": "Pa"},
        ),
        (
            {"value": 2.0, "unit": "m"},
            {"value": 200, "unit": "cm"},
        ),
    ],
)
def test_numeric_unit_validator_converts_compatible_units(
    expected,
    actual,
):
    result = validate_candidate_answer(
        "numeric_unit_validator",
        expected,
        actual,
        {
            "absolute_tolerance": 1e-6,
            "relative_tolerance": 1e-6,
        },
    )

    assert result["passed"] is True
    assert result["deterministic"] is True
    assert result["confidence"] == 1.0


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("(x + 1)^2", "x^2 + 2*x + 1"),
        ("sin(x)^2 + cos(x)^2", "1"),
        ("2*x + 2*y", "2*(x+y)"),
    ],
)
def test_symbolic_validator_checks_mathematical_equivalence(
    expected: str,
    actual: str,
):
    result = validate_candidate_answer(
        "symbolic_validator",
        expected,
        actual,
        {},
    )

    assert result["passed"] is True
    assert result["deterministic"] is True


def test_code_validator_uses_hidden_test_results_without_executing_text():
    expected = {
        "required_hidden_tests": ["empty", "boundary", "normal"],
    }
    passing = validate_candidate_answer(
        "code_validator",
        expected,
        {
            "test_results": {
                "empty": "passed",
                "boundary": "passed",
                "normal": "passed",
            },
            "complexity": "O(n)",
        },
        {"required_complexity": "O(n)"},
    )
    unexecuted = validate_candidate_answer(
        "code_validator",
        expected,
        "def solve(): pass",
        {},
    )

    assert passing["passed"] is True
    assert passing["deterministic"] is True
    assert unexecuted["passed"] is False
    assert unexecuted["status"] == "needs_review"
    assert unexecuted["issue_code"] == "code_execution_evidence_missing"


def test_evidence_and_expert_validators_never_guess_low_confidence_passes():
    evidence = validate_candidate_answer(
        "evidence_validator",
        {"required_source_refs": ["材料一", "材料二"]},
        "材料一说明现象发生，但没有解释材料二。",
        {},
    )
    expert = validate_candidate_answer(
        "expert_rubric_validator",
        {"rubric": ["变量完整", "误差分析"]},
        {
            "rubric_scores": {
                "变量完整": 0.9,
                "误差分析": 0.62,
            },
            "confidence": 0.68,
        },
        {"pass_score": 0.7, "confidence_threshold": 0.85},
    )

    assert evidence["passed"] is False
    assert evidence["status"] == "needs_review"
    assert evidence["confidence"] < 0.85
    assert expert["passed"] is False
    assert expert["status"] == "needs_review"
    assert expert["requires_teacher_review"] is True


def test_unknown_validator_fails_closed():
    result = validate_candidate_answer(
        "future_magic_validator",
        "answer",
        "answer",
        {},
    )

    assert result["passed"] is False
    assert result["status"] == "needs_review"
    assert result["issue_code"] == "validator_unavailable"
