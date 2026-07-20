"""Canonical compilation and fail-closed validation for formal practice tasks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_versioning import stable_hash


INPUT_MODES = {
    "choice",
    "numeric_unit",
    "code",
    "short_text",
    "rich_text",
    "structured_fields",
    "structured_text",
    "code_and_text",
    "language_response",
}

_TYPED_VALIDATORS = {
    "exact_validator",
    "numeric_unit_validator",
    "symbolic_validator",
    "state_trace_validator",
}

_VALIDATORS_BY_INPUT_MODE = {
    "choice": {
        "exact_validator",
        "choice_validator",
        "state_trace_validator",
    },
    "numeric_unit": {
        "exact_validator",
        "numeric_unit_validator",
    },
    "code": {"code_validator"},
    "short_text": {
        "exact_validator",
        "expert_rubric_validator",
        "semantic_validator",
    },
    "rich_text": {
        "expert_rubric_validator",
        "semantic_validator",
        "evidence_validator",
        "language_rubric_validator",
    },
    "structured_fields": {
        "exact_validator",
        "numeric_unit_validator",
        "symbolic_validator",
        "state_trace_validator",
        "expert_rubric_validator",
        "semantic_validator",
        "evidence_validator",
        "language_rubric_validator",
    },
    "structured_text": {
        "expert_rubric_validator",
        "semantic_validator",
    },
    "code_and_text": {
        "code_validator",
        "expert_rubric_validator",
    },
    "language_response": {
        "expert_rubric_validator",
        "semantic_validator",
    },
}


def normalize_public_options(value: Any) -> list[dict[str, Any]]:
    """Normalize new and legacy option shapes to one public schema."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for option in value:
        if not isinstance(option, dict):
            continue
        option_id = str(
            option.get("id")
            or option.get("option_id")
            or option.get("value")
            or ""
        ).strip()
        text = str(
            option.get("text")
            or option.get("label")
            or option.get("value")
            or ""
        ).strip()
        result.append({
            "id": option_id,
            "text": text,
        })
    return result


def solution_answer_spec(
    solution_envelope: dict[str, Any] | None,
    *,
    input_mode: str,
    options: list[dict[str, Any]],
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile the private solution into the grader-facing answer contract."""
    solution = solution_envelope or {}
    legacy_choice = deepcopy(solution.get("choice_answer_spec") or {})
    legacy = deepcopy(solution.get("legacy_answer_spec") or {})
    fallback_answer = deepcopy(fallback or {})
    canonical = deepcopy(solution.get("canonical_answer"))
    rubric = deepcopy(solution.get("rubric") or [])
    validator_config = deepcopy(solution.get("validator_config") or {})

    if input_mode == "choice":
        option_ids = {
            str(option.get("id") or "")
            for option in options
            if str(option.get("id") or "")
        }
        correct_option_id = str(
            legacy_choice.get("correct_option_id")
            or legacy.get("correct_option_id")
            or fallback_answer.get("correct_option_id")
            or _selected_option_id(canonical)
            or ""
        ).strip()
        if not correct_option_id and isinstance(canonical, str):
            candidate = canonical.strip()
            if candidate in option_ids:
                correct_option_id = candidate
        return {
            "type": "choice",
            "correct_option_id": correct_option_id,
            "canonical_answer": canonical,
            "criteria": deepcopy(
                legacy_choice.get("criteria")
                or legacy.get("criteria")
                or rubric
            ),
            "expected_keywords": deepcopy(
                legacy_choice.get("expected_keywords")
                or legacy.get("expected_keywords")
                or []
            ),
            "pass_score": int(
                legacy_choice.get("pass_score")
                or legacy.get("pass_score")
                or fallback_answer.get("pass_score")
                or validator_config.get("pass_score")
                or 70
            ),
            "validator_config": validator_config,
        }

    if legacy:
        return legacy
    if fallback_answer:
        return fallback_answer
    return {
        "type": "rubric",
        "validation_mode": solution.get("validation_mode"),
        "canonical_answer": canonical,
        "criteria": rubric,
        "pass_score": int(
            validator_config.get("pass_score") or 70
        ),
        "validator_config": validator_config,
    }


def compile_formal_task_contract(
    item: dict[str, Any],
    solution_envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one immutable item into the exact student/grader contract."""
    question_spec = item.get("question_spec") or {}
    is_v2 = question_spec.get("schema_version") == "question_spec_v2"
    input_contract = deepcopy(
        item.get("input_contract")
        or question_spec.get("input_contract")
        or {}
    )
    if not input_contract:
        input_contract = _legacy_input_contract(item)
    legacy_text_compat = bool(
        not (item.get("input_contract") or {})
        and not (question_spec.get("input_contract") or {})
    )
    input_mode = str(input_contract.get("mode") or "")
    options = normalize_public_options(
        question_spec.get("options")
        if isinstance(question_spec.get("options"), list)
        else item.get("options")
    )
    if not options:
        options = normalize_public_options(item.get("options"))
    if input_mode != "choice":
        options = []

    answer_spec = solution_answer_spec(
        solution_envelope,
        input_mode=input_mode,
        options=options,
        fallback=item.get("answer_spec") or {},
    )
    validation_mode = str(
        (solution_envelope or {}).get("validation_mode")
        or item.get("validation_mode")
        or answer_spec.get("validation_mode")
        or ""
    )
    if legacy_text_compat:
        grading_method = str(
            (
                (item.get("formal_task") or {}).get(
                    "grading_policy"
                )
                or {}
            ).get("method")
            or "rubric_ai"
        )
    else:
        grading_method = _grading_method(
            input_mode=input_mode,
            validation_mode=validation_mode,
            answer_spec=answer_spec,
        )
    practice_level = str(
        next(
            iter(item.get("practice_levels") or []),
            item.get("practice_level") or "objective_practice",
        )
    )
    contract_hash = stable_hash(
        {
            "question_type": item.get("question_type"),
            "input_contract": input_contract,
            "options": options,
            "answer_spec": answer_spec,
            "validation_mode": validation_mode,
            "practice_level": practice_level,
            "assessment_slot": item.get("assessment_slot") or {},
            "solution_revision_id": item.get("solution_revision_id"),
        },
        prefix="qcc_",
    )
    result = {
        "schema_version": (
            "compiled_formal_task_v2"
            if is_v2
            else "compiled_formal_task_v1"
        ),
        "question_type": item.get("question_type"),
        "input_contract": input_contract,
        "options": options,
        "answer_spec": answer_spec,
        "validation_mode": validation_mode,
        "grading_policy": {
            "method": grading_method,
            "pass_score": int(answer_spec.get("pass_score") or 70),
            "confidence_threshold": 0.72,
            "near_threshold_review_margin": 3,
        },
        "practice_level": practice_level,
        "compiled_contract_hash": contract_hash,
        "compatibility_mode": (
            "legacy_text"
            if legacy_text_compat
            else None
        ),
    }
    validation = validate_compiled_question_contract(
        item,
        solution_envelope=solution_envelope,
        compiled=result,
    )
    result["contract_validation"] = validation
    result["validation_policy"] = {
        "mastery_eligible": bool(
            practice_level in {"mastery_check", "final_assessment"}
            and validation.get("passed")
            and not legacy_text_compat
        ),
        "max_support_level_for_mastery": 1,
        "requires_unseen_validation_after_solution": True,
        "compiled_contract_hash": contract_hash,
    }
    return result


def validate_compiled_question_contract(
    item: dict[str, Any],
    *,
    solution_envelope: dict[str, Any] | None = None,
    compiled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the final student-visible contract, not the precompile draft."""
    contract = compiled or compile_formal_task_contract(
        item,
        solution_envelope,
    )
    question_spec = item.get("question_spec") or {}
    is_v2 = question_spec.get("schema_version") == "question_spec_v2"
    input_contract = contract.get("input_contract") or {}
    input_mode = str(input_contract.get("mode") or "")
    options = contract.get("options") or []
    answer_spec = contract.get("answer_spec") or {}
    validation_mode = str(contract.get("validation_mode") or "")
    assessment_slot = item.get("assessment_slot") or {}
    legacy_text_compat = (
        contract.get("compatibility_mode")
        == "legacy_text"
    )
    issues: list[dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        issues.append({
            "code": code,
            "severity": "critical",
            "detail": detail,
        })

    if input_mode not in INPUT_MODES:
        add("FINAL_INPUT_MODE_INVALID", input_mode or "missing")
    if is_v2:
        spec_input = question_spec.get("input_contract") or {}
        item_input = item.get("input_contract") or {}
        if item_input and spec_input != item_input:
            add(
                "PUBLIC_INPUT_CONTRACT_SPLIT",
                "question_spec.input_contract differs from item.input_contract",
            )
        expected_mode = str(assessment_slot.get("input_mode") or "")
        if expected_mode and input_mode != expected_mode:
            add(
                "BLUEPRINT_INPUT_MODE_MISMATCH",
                f"expected {expected_mode}, got {input_mode}",
            )
        expected_type = str(assessment_slot.get("question_type") or "")
        if expected_type and str(item.get("question_type") or "") != expected_type:
            add(
                "BLUEPRINT_QUESTION_TYPE_MISMATCH",
                f"expected {expected_type}, got {item.get('question_type')}",
            )
        if (
            str(item.get("question_type") or "")
            == "single_choice"
            and input_mode != "choice"
        ):
            add(
                "QUESTION_TYPE_INPUT_MODE_MISMATCH",
                "single_choice requires choice input",
            )

    option_ids = [
        str(option.get("id") or "").strip()
        for option in options
        if isinstance(option, dict)
    ]
    option_texts = [
        str(option.get("text") or "").strip()
        for option in options
        if isinstance(option, dict)
    ]
    if input_mode == "choice":
        if len(options) < 2:
            add("CHOICE_OPTIONS_MISSING", "choice requires at least two options")
        if (
            len(option_ids) != len(options)
            or any(not value for value in option_ids)
            or len(set(option_ids)) != len(option_ids)
        ):
            add("CHOICE_OPTION_IDS_INVALID", "option ids must be non-empty and unique")
        if (
            len(option_texts) != len(options)
            or any(not value for value in option_texts)
        ):
            add("CHOICE_OPTION_TEXT_EMPTY", "option text must be non-empty")
        correct_id = str(answer_spec.get("correct_option_id") or "")
        if not correct_id or correct_id not in set(option_ids):
            add(
                "CHOICE_CORRECT_OPTION_NOT_VISIBLE",
                f"correct option {correct_id or 'missing'} is not public",
            )
        private_options = normalize_public_options(
            (solution_envelope or {}).get(
                "choice_answer_spec",
                {},
            ).get("options")
        )
        if private_options and private_options != options:
            add(
                "PUBLIC_PRIVATE_OPTIONS_MISMATCH",
                "private choice options differ from public options",
            )
    elif options:
        add(
            "NON_CHOICE_OPTIONS_PRESENT",
            f"{input_mode} tasks must not expose choice options",
        )

    if not legacy_text_compat:
        allowed_validators = _VALIDATORS_BY_INPUT_MODE.get(
            input_mode,
            set(),
        )
        if (
            validation_mode
            and validation_mode not in allowed_validators
        ):
            add(
                "VALIDATOR_INPUT_MODE_MISMATCH",
                f"{validation_mode} cannot grade {input_mode}",
            )
        if (
            input_mode == "code"
            and validation_mode != "code_validator"
        ):
            add(
                "CODE_RUNNER_REQUIRED",
                "code input requires code_validator",
            )
        if (
            input_mode != "code"
            and validation_mode == "code_validator"
        ):
            add(
                "RUNNER_WITHOUT_CODE_INPUT",
                "code_validator requires code input",
            )
    return {
        "schema_version": "compiled_question_validation_v1",
        "passed": not issues,
        "status": "passed" if not issues else "failed",
        "compiled_contract_hash": contract.get(
            "compiled_contract_hash"
        ),
        "issues": issues,
    }


def _legacy_input_contract(item: dict[str, Any]) -> dict[str, Any]:
    is_choice = bool(
        item.get("question_type")
        in {"single_choice", "multiple_choice"}
        or (item.get("answer_spec") or {}).get(
            "correct_option_id"
        )
    )
    return {
        "schema_version": "input_contract_v1",
        "mode": "choice" if is_choice else "structured_text",
        "required": True,
        "supports_attachments": item.get("question_type")
        in {"implementation_task", "scenario_deliverable"},
    }


def _selected_option_id(canonical: Any) -> str:
    if not isinstance(canonical, dict):
        return ""
    return str(
        canonical.get("selected_option_id")
        or canonical.get("option_id")
        or ""
    ).strip()


def _grading_method(
    *,
    input_mode: str,
    validation_mode: str,
    answer_spec: dict[str, Any],
) -> str:
    if input_mode == "choice":
        return "deterministic"
    if input_mode == "code":
        return "runner"
    if validation_mode in _TYPED_VALIDATORS:
        return "typed_validator"
    if answer_spec.get("canonical_answer") is not None:
        return "rubric_ai_with_reference"
    return "rubric_ai"


__all__ = [
    "compile_formal_task_contract",
    "normalize_public_options",
    "solution_answer_spec",
    "validate_compiled_question_contract",
]
