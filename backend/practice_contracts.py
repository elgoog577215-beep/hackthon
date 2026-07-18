"""Formal-practice contracts shared by asset compilation and old-course projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_versioning import stable_hash
from reasoning_paths import compile_reasoning_support


INPUT_MODES = {
    "worked_solution": "rich_text",
    "implementation_task": "code_and_text",
    "evidence_analysis": "structured_text",
    "mechanism_explanation": "structured_text",
    "source_argument": "structured_text",
    "language_production": "language_response",
    "scenario_deliverable": "structured_text",
    "short_answer": "rich_text",
}


def enrich_question_contract(
    question: dict[str, Any],
    *,
    practice_level: str | None = None,
) -> dict[str, Any]:
    item = deepcopy(question)
    question_type = str(item.get("question_type") or "short_answer")
    answer_spec = item.get("answer_spec") or {}
    criteria = [str(value) for value in answer_spec.get("criteria") or [] if str(value).strip()]
    objective = str(item.get("learning_objective") or item.get("prompt") or "当前学习目标")
    level = practice_level or str(item.get("practice_level") or "objective_practice")
    item["practice_level"] = level
    item.setdefault("input_contract", {
        "mode": INPUT_MODES.get(question_type, "rich_text"),
        "required": True,
        "supports_attachments": question_type in {"implementation_task", "source_argument", "scenario_deliverable"},
    })
    if not item.get("hint_contract"):
        support = _legacy_reasoning_support(
            item,
            question_type=question_type,
        )
        item["reasoning_path"] = support["reasoning_path"]
        item["answer_spec"] = support["answer_spec"]
        item["hint_contract"] = support["hint_contract"]
        answer_spec = item["answer_spec"]
        criteria = [
            str(value)
            for value in answer_spec.get("criteria") or []
            if str(value).strip()
        ]
    _complete_hint_policy(item)
    method = "deterministic" if answer_spec.get("correct_answer") is not None or answer_spec.get("correct_option_id") is not None else "rubric_ai"
    item.setdefault("grading_policy", {
        "method": method,
        "pass_score": int(answer_spec.get("pass_score") or 70),
        "confidence_threshold": 0.72,
        "near_threshold_review_margin": 3,
    })
    item.setdefault("validation_policy", {
        "mastery_eligible": level in {"mastery_check", "final_assessment"},
        "max_support_level_for_mastery": 1,
        "requires_unseen_validation_after_solution": True,
    })
    contract_payload = {
        "practice_level": item["practice_level"],
        "input_contract": item["input_contract"],
        "hint_contract": item["hint_contract"],
        "grading_policy": item["grading_policy"],
        "validation_policy": item["validation_policy"],
    }
    item["practice_contract_revision_id"] = stable_hash(contract_payload, prefix="pcr_")
    return item


def _legacy_reasoning_support(
    item: dict[str, Any],
    *,
    question_type: str,
) -> dict[str, Any]:
    prompt = str(item.get("prompt") or "")
    answer_spec = deepcopy(item.get("answer_spec") or {})
    payload = {
        "archetype_id": f"legacy_{question_type}",
        "stimulus": {
            "kind": "legacy_question",
            "data": {
                "question_text": prompt,
                "input_materials": deepcopy(
                    item.get("input_materials") or []
                ),
            },
            "rendered_text": prompt,
        },
        "task": {
            "action": _legacy_task_action(question_type),
            "rendered_text": prompt,
            "deliverable": str(
                item.get("deliverable")
                or "提交题目要求的结果与必要依据"
            ),
        },
        "constraints": deepcopy(item.get("constraints") or []),
        "response_contract": {
            "format": question_type,
            "required_parts": _legacy_required_parts(question_type),
        },
        "answer_spec": answer_spec,
        "result_checks": deepcopy(
            item.get("result_checks")
            or answer_spec.get("criteria")
            or ["结果能够由题目条件复核"]
        ),
    }
    return compile_reasoning_support(payload)


def _complete_hint_policy(item: dict[str, Any]) -> None:
    contract = item["hint_contract"]
    effects = {
        1: ("limited_mastery", 1),
        2: ("not_independent", 2),
        3: ("not_mastery", 3),
    }
    for level in contract.get("levels") or []:
        number = int(level.get("level") or 0)
        effect, support = effects.get(number, ("not_mastery", max(1, number)))
        level.setdefault("evidence_effect", effect)
        level.setdefault("support_level", support)
    contract.setdefault(
        "solution_policy",
        "after_submission_or_repeated_failure",
    )
    contract.setdefault("solution_effect", {
        "invalidate_current_evidence": True,
        "requires_unseen_equivalent_validation": True,
    })
    contract.setdefault("frozen_with_item_revision", True)
    contract.setdefault("leakage_check", {
        "passed": _legacy_hint_does_not_reveal_answer(item),
        "checked_at_compile_time": True,
    })


def _legacy_hint_does_not_reveal_answer(item: dict[str, Any]) -> bool:
    answer = (item.get("answer_spec") or {}).get("canonical_answer")
    if answer is None:
        answer = (item.get("answer_spec") or {}).get("correct_answer")
    if answer is None:
        return True
    normalized_answer = "".join(str(answer).split())
    if len(normalized_answer) < 4:
        return True
    return all(
        normalized_answer not in "".join(str(level.get("content") or "").split())
        for level in (item.get("hint_contract") or {}).get("levels") or []
    )


def _legacy_task_action(question_type: str) -> str:
    return {
        "implementation_task": "implement_transform_and_test",
        "evidence_analysis": "analyze_evidence",
        "mechanism_explanation": "explain_mechanism",
        "source_argument": "construct_evidence_argument",
        "language_production": "produce_contextual_language",
        "scenario_deliverable": "design_and_justify",
    }.get(question_type, "solve_and_verify")


def _legacy_required_parts(question_type: str) -> list[str]:
    return {
        "implementation_task": ["implementation", "tests", "verification"],
        "evidence_analysis": ["evidence", "reasoning", "claim", "limitation"],
        "mechanism_explanation": ["steps", "reasoning", "verification"],
        "source_argument": ["claim", "evidence", "reasoning", "limitation"],
        "language_production": ["response_text", "target_form_highlights"],
        "scenario_deliverable": ["design", "reasoning", "verification"],
    }.get(question_type, ["method", "steps", "answer", "verification"])


def project_practice_contracts(assets: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(assets)
    mastery_bindings = {
        str(revision_id)
        for criterion in result.get("mastery_criteria") or []
        for revision_id in criterion.get("assessment_bindings") or []
    }
    result["questions"] = [
        enrich_question_contract(
            item,
            practice_level="mastery_check" if str(item.get("revision_id") or "") in mastery_bindings else None,
        )
        for item in result.get("questions") or []
    ]
    result["final_assessment"] = [
        enrich_question_contract(item, practice_level="final_assessment")
        for item in result.get("final_assessment") or []
    ]
    return result


__all__ = ["enrich_question_contract", "project_practice_contracts"]
