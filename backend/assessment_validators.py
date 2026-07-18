"""Validation plugins for public assessment specs and private solutions."""

from __future__ import annotations

import math
import re
from typing import Any


VALIDATION_REPORT_SCHEMA = "solution_validation_report_v1"


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


def _numeric_equivalent(
    expected: Any,
    actual: Any,
    config: dict[str, Any],
) -> bool:
    expected_value, expected_unit = _number_and_unit(expected)
    actual_value, actual_unit = _number_and_unit(actual)
    if expected_value is None or actual_value is None:
        return False
    if expected_unit and expected_unit.lower() != actual_unit.lower():
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
    "VALIDATION_REPORT_SCHEMA",
    "answers_equivalent",
    "validate_solution_envelope",
]
