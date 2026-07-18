"""Validation plugins for public assessment specs and private solutions."""

from __future__ import annotations

import math
import re
from typing import Any

try:
    import sympy
except ImportError:  # pragma: no cover - deployment guard
    sympy = None


VALIDATION_REPORT_SCHEMA = "solution_validation_report_v1"
VALIDATOR_RESULT_SCHEMA = "assessment_validator_result_v1"

_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "j": ("energy", 1.0),
    "kj": ("energy", 1000.0),
    "mj": ("energy", 1_000_000.0),
    "pa": ("pressure", 1.0),
    "kpa": ("pressure", 1000.0),
    "mpa": ("pressure", 1_000_000.0),
    "m": ("length", 1.0),
    "cm": ("length", 0.01),
    "mm": ("length", 0.001),
    "km": ("length", 1000.0),
    "s": ("time", 1.0),
    "ms": ("time", 0.001),
    "min": ("time", 60.0),
    "h": ("time", 3600.0),
    "kg": ("mass", 1.0),
    "g": ("mass", 0.001),
}


def validate_solution_envelope(
    question_spec: dict[str, Any],
    solution_envelope: dict[str, Any],
    *,
    independent_solution: Any = None,
) -> dict[str, Any]:
    """Validate a private solution without copying it into the public spec."""
    issues: list[dict[str, str]] = []
    if question_spec.get("schema_version") != "question_spec_v2":
        issues.append(_issue("question_spec_schema_invalid", "critical"))
    if solution_envelope.get("schema_version") != "solution_envelope_v1":
        issues.append(_issue("solution_schema_invalid", "critical"))
    if question_spec.get("solution_revision_id") != solution_envelope.get(
        "solution_revision_id"
    ):
        issues.append(_issue("solution_revision_mismatch", "critical"))
    mode = str(solution_envelope.get("validation_mode") or "")
    canonical = solution_envelope.get("canonical_answer")
    if not mode:
        issues.append(_issue("validation_mode_missing", "critical"))
    if canonical is None and not solution_envelope.get("rubric"):
        issues.append(_issue("solution_not_executable", "critical"))
    if not (solution_envelope.get("solution_graph") or {}).get("steps"):
        issues.append(_issue("solution_graph_missing", "critical"))

    deterministic_modes = {
        "exact_validator",
        "numeric_unit_validator",
        "symbolic_validator",
        "code_validator",
        "state_trace_validator",
    }
    if (
        independent_solution is not None
        and canonical is not None
        and not answers_equivalent(
            mode,
            canonical,
            independent_solution,
            solution_envelope.get("validator_config") or {},
        )
    ):
        issues.append(
            _issue("independent_solution_mismatch", "critical")
        )
    elif (
        independent_solution is None
        and mode not in deterministic_modes
    ):
        issues.append(
            _issue("independent_solution_required", "major")
        )

    critical = any(
        issue["severity"] == "critical" for issue in issues
    )
    major = any(issue["severity"] == "major" for issue in issues)
    risk_level = str(
        (question_spec.get("risk_contract") or {}).get(
            "risk_level",
            "teacher_review",
        )
    )
    auto_publish_eligible = (
        not critical
        and not major
        and risk_level == "low"
        and not (
            question_spec.get("risk_contract") or {}
        ).get("requires_teacher_review")
    )
    return {
        "schema_version": VALIDATION_REPORT_SCHEMA,
        "passed": not critical,
        "status": (
            "failed"
            if critical and not issues
            else (
                "needs_review"
                if critical or major or not auto_publish_eligible
                else "passed"
            )
        ),
        "validation_mode": mode,
        "deterministic": mode in deterministic_modes,
        "auto_publish_eligible": auto_publish_eligible,
        "issues": issues,
        "checks": {
            "schema": not any(
                issue["code"].endswith("schema_invalid")
                for issue in issues
            ),
            "solution_revision": not any(
                issue["code"] == "solution_revision_mismatch"
                for issue in issues
            ),
            "answer_executable": not any(
                issue["code"] == "solution_not_executable"
                for issue in issues
            ),
            "independent_agreement": not any(
                issue["code"] == "independent_solution_mismatch"
                for issue in issues
            ),
        },
    }


def answers_equivalent(
    validation_mode: str,
    expected: Any,
    actual: Any,
    config: dict[str, Any] | None = None,
) -> bool:
    """Compare answers using the selected validator contract."""
    validator_config = config or {}
    if validation_mode == "numeric_unit_validator":
        return _numeric_equivalent(
            expected,
            actual,
            validator_config,
        )
    if validation_mode == "symbolic_validator":
        return _symbolic(expected) == _symbolic(actual)
    if validation_mode in {
        "exact_validator",
        "code_validator",
        "state_trace_validator",
    }:
        return _normalized(expected) == _normalized(actual)
    return _normalized(expected) == _normalized(actual)


def validate_candidate_answer(
    validation_mode: str,
    expected: Any,
    actual: Any,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one typed validator and fail closed when it cannot decide."""
    validator_config = config or {}
    deterministic_modes = {
        "exact_validator",
        "numeric_unit_validator",
        "symbolic_validator",
        "code_validator",
        "state_trace_validator",
    }
    if validation_mode == "exact_validator":
        passed = _normalized(expected) == _normalized(actual)
        return _deterministic_result(
            validation_mode,
            passed,
            issue_code=None if passed else "exact_answer_mismatch",
        )
    if validation_mode == "numeric_unit_validator":
        passed = _numeric_equivalent(
            expected,
            actual,
            validator_config,
        )
        return _deterministic_result(
            validation_mode,
            passed,
            issue_code=None if passed else "numeric_or_unit_mismatch",
        )
    if validation_mode == "symbolic_validator":
        equivalent = _symbolic_equivalent(expected, actual)
        if equivalent is None:
            return _review_result(
                validation_mode,
                issue_code="symbolic_expression_unverifiable",
                confidence=0.0,
            )
        return _deterministic_result(
            validation_mode,
            equivalent,
            issue_code=None if equivalent else "symbolic_answer_mismatch",
        )
    if validation_mode == "state_trace_validator":
        passed = _normalized(expected) == _normalized(actual)
        return _deterministic_result(
            validation_mode,
            passed,
            issue_code=None if passed else "state_trace_mismatch",
        )
    if validation_mode == "code_validator":
        return _validate_code_evidence(expected, actual, validator_config)
    if validation_mode == "evidence_validator":
        return _validate_evidence_answer(expected, actual, validator_config)
    if validation_mode in {
        "language_rubric_validator",
        "expert_rubric_validator",
    }:
        return _validate_rubric_answer(
            validation_mode,
            expected,
            actual,
            validator_config,
        )
    return {
        "schema_version": VALIDATOR_RESULT_SCHEMA,
        "validation_mode": validation_mode,
        "passed": False,
        "status": "needs_review",
        "deterministic": validation_mode in deterministic_modes,
        "confidence": 0.0,
        "requires_teacher_review": True,
        "issue_code": "validator_unavailable",
        "details": {},
    }


def _numeric_equivalent(
    expected: Any,
    actual: Any,
    config: dict[str, Any],
) -> bool:
    expected_value, expected_unit = _number_and_unit(expected)
    actual_value, actual_unit = _number_and_unit(actual)
    if expected_value is None or actual_value is None:
        return False
    expected_value, actual_value, units_compatible = _normalize_units(
        expected_value,
        expected_unit,
        actual_value,
        actual_unit,
    )
    if not units_compatible:
        return False
    absolute_tolerance = float(
        config.get("absolute_tolerance", 1e-9)
    )
    relative_tolerance = float(
        config.get("relative_tolerance", 1e-9)
    )
    return math.isclose(
        expected_value,
        actual_value,
        abs_tol=max(0.0, absolute_tolerance),
        rel_tol=max(0.0, relative_tolerance),
    )


def _normalize_units(
    expected_value: float,
    expected_unit: str,
    actual_value: float,
    actual_unit: str,
) -> tuple[float, float, bool]:
    expected_key = _normalize_unit(expected_unit)
    actual_key = _normalize_unit(actual_unit)
    if not expected_key and not actual_key:
        return expected_value, actual_value, True
    if not expected_key or not actual_key:
        return expected_value, actual_value, False
    if expected_key == actual_key:
        return expected_value, actual_value, True
    expected_contract = _UNIT_FACTORS.get(expected_key)
    actual_contract = _UNIT_FACTORS.get(actual_key)
    if (
        not expected_contract
        or not actual_contract
        or expected_contract[0] != actual_contract[0]
    ):
        return expected_value, actual_value, False
    return (
        expected_value * expected_contract[1],
        actual_value * actual_contract[1],
        True,
    )


def _normalize_unit(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _number_and_unit(value: Any) -> tuple[float | None, str]:
    if isinstance(value, dict):
        raw_value = value.get("value")
        unit = str(value.get("unit") or "").strip()
    else:
        match = re.fullmatch(
            r"\s*(-?\d+(?:\.\d+)?)\s*([^\d\s].*)?\s*",
            str(value),
        )
        if not match:
            return None, ""
        raw_value = match.group(1)
        unit = str(match.group(2) or "").strip()
    try:
        return float(raw_value), unit
    except (TypeError, ValueError):
        return None, unit


def _symbolic(value: Any) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value).replace("−", "-").replace("×", "*"),
    ).lower()


def _symbolic_equivalent(expected: Any, actual: Any) -> bool | None:
    if sympy is None:
        return _symbolic(expected) == _symbolic(actual)
    expected_text = str(expected or "").strip()
    actual_text = str(actual or "").strip()
    if not expected_text or not actual_text:
        return False
    if len(expected_text) > 1000 or len(actual_text) > 1000:
        return None
    allowed = re.compile(r"^[A-Za-z0-9+\-*/^().,=\s]+$")
    if not allowed.fullmatch(expected_text) or not allowed.fullmatch(
        actual_text
    ):
        return None
    allowed_functions = {
        "sin",
        "cos",
        "tan",
        "exp",
        "log",
        "sqrt",
        "Abs",
    }
    for text in (expected_text, actual_text):
        calls = set(re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*\(", text))
        if calls - allowed_functions:
            return None
    try:
        expected_expression = _parse_symbolic_expression(expected_text)
        actual_expression = _parse_symbolic_expression(actual_text)
        return bool(
            sympy.simplify(
                expected_expression - actual_expression
            ) == 0
        )
    except Exception:
        return None


def _parse_symbolic_expression(value: str):
    text = value.replace("^", "**")
    if "=" in text:
        left, right = text.split("=", 1)
        return sympy.sympify(left) - sympy.sympify(right)
    return sympy.sympify(text)


def _validate_code_evidence(
    expected: Any,
    actual: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(actual, dict):
        return _review_result(
            "code_validator",
            issue_code="code_execution_evidence_missing",
            confidence=0.0,
            deterministic=True,
        )
    expected_contract = expected if isinstance(expected, dict) else {}
    required_tests = [
        str(value)
        for value in expected_contract.get(
            "required_hidden_tests",
            config.get("required_hidden_tests", []),
        )
    ]
    test_results = actual.get("test_results") or {}
    if not isinstance(test_results, dict) or not required_tests:
        return _review_result(
            "code_validator",
            issue_code="code_execution_evidence_missing",
            confidence=0.0,
            deterministic=True,
        )
    tests_passed = all(
        str(test_results.get(test_id) or "").casefold()
        in {"passed", "pass", "ok", "true"}
        for test_id in required_tests
    )
    required_complexity = str(
        config.get("required_complexity") or ""
    ).strip()
    complexity_passed = (
        not required_complexity
        or str(actual.get("complexity") or "").strip()
        == required_complexity
    )
    passed = tests_passed and complexity_passed
    result = _deterministic_result(
        "code_validator",
        passed,
        issue_code=None if passed else "code_hidden_test_failure",
    )
    result["details"] = {
        "required_test_count": len(required_tests),
        "passed_test_count": sum(
            1
            for test_id in required_tests
            if str(test_results.get(test_id) or "").casefold()
            in {"passed", "pass", "ok", "true"}
        ),
        "complexity_passed": complexity_passed,
    }
    return result


def _validate_evidence_answer(
    expected: Any,
    actual: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected_contract = expected if isinstance(expected, dict) else {}
    source_refs = [
        str(value).strip()
        for value in expected_contract.get(
            "required_source_refs",
            config.get("required_source_refs", []),
        )
        if str(value).strip()
    ]
    text = (
        str(actual.get("text") or "")
        if isinstance(actual, dict)
        else str(actual or "")
    ).strip()
    matched = [
        source_ref
        for source_ref in source_refs
        if source_ref in text
    ]
    coverage = (
        len(matched) / len(source_refs)
        if source_refs
        else 0.0
    )
    sufficient_argument = len(text) >= max(
        80,
        len(source_refs) * 40,
    )
    confidence = min(
        0.95,
        coverage * (0.95 if sufficient_argument else 0.6),
    )
    threshold = float(config.get("confidence_threshold", 0.85))
    passed = bool(
        source_refs
        and coverage == 1.0
        and sufficient_argument
        and confidence >= threshold
    )
    return {
        "schema_version": VALIDATOR_RESULT_SCHEMA,
        "validation_mode": "evidence_validator",
        "passed": passed,
        "status": "passed" if passed else "needs_review",
        "deterministic": False,
        "confidence": confidence,
        "requires_teacher_review": not passed,
        "issue_code": None if passed else "evidence_support_insufficient",
        "details": {
            "required_source_count": len(source_refs),
            "matched_source_count": len(matched),
            "argument_length": len(text),
        },
    }


def _validate_rubric_answer(
    validation_mode: str,
    expected: Any,
    actual: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected_contract = expected if isinstance(expected, dict) else {}
    rubric = [
        str(value)
        for value in expected_contract.get(
            "rubric",
            config.get("rubric", []),
        )
        if str(value).strip()
    ]
    actual_contract = actual if isinstance(actual, dict) else {}
    scores = actual_contract.get("rubric_scores") or {}
    confidence = float(actual_contract.get("confidence") or 0.0)
    if not rubric or not isinstance(scores, dict):
        return _review_result(
            validation_mode,
            issue_code="rubric_evidence_missing",
            confidence=confidence,
        )
    normalized_scores = [
        max(0.0, min(1.0, float(scores.get(item) or 0.0)))
        for item in rubric
    ]
    aggregate = sum(normalized_scores) / len(normalized_scores)
    pass_score = float(config.get("pass_score", 0.7))
    confidence_threshold = float(
        config.get("confidence_threshold", 0.85)
    )
    passed = (
        aggregate >= pass_score
        and confidence >= confidence_threshold
    )
    return {
        "schema_version": VALIDATOR_RESULT_SCHEMA,
        "validation_mode": validation_mode,
        "passed": passed,
        "status": "passed" if passed else "needs_review",
        "deterministic": False,
        "confidence": confidence,
        "requires_teacher_review": not passed,
        "issue_code": None if passed else "rubric_confidence_insufficient",
        "details": {
            "aggregate_score": aggregate,
            "criterion_scores": dict(zip(rubric, normalized_scores)),
        },
    }


def _deterministic_result(
    validation_mode: str,
    passed: bool,
    *,
    issue_code: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": VALIDATOR_RESULT_SCHEMA,
        "validation_mode": validation_mode,
        "passed": bool(passed),
        "status": "passed" if passed else "failed",
        "deterministic": True,
        "confidence": 1.0,
        "requires_teacher_review": False,
        "issue_code": issue_code,
        "details": {},
    }


def _review_result(
    validation_mode: str,
    *,
    issue_code: str,
    confidence: float,
    deterministic: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": VALIDATOR_RESULT_SCHEMA,
        "validation_mode": validation_mode,
        "passed": False,
        "status": "needs_review",
        "deterministic": deterministic,
        "confidence": max(0.0, min(1.0, confidence)),
        "requires_teacher_review": True,
        "issue_code": issue_code,
        "details": {},
    }


def _normalized(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalized(nested)
            for key, nested in sorted(value.items())
        }
    if isinstance(value, list):
        return [_normalized(nested) for nested in value]
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().lower()
    return value


def _issue(code: str, severity: str) -> dict[str, str]:
    return {"code": code, "severity": severity}


__all__ = [
    "VALIDATOR_RESULT_SCHEMA",
    "VALIDATION_REPORT_SCHEMA",
    "answers_equivalent",
    "validate_candidate_answer",
    "validate_solution_envelope",
]
