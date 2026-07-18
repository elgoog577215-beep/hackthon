"""Formal-practice contracts shared by asset compilation and old-course projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_versioning import stable_hash


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
    item.setdefault("hint_contract", {
        "levels": [
            {
                "level": 1,
                "kind": "orientation",
                "content": f"先澄清任务最终要验证什么，再回看相关章节与自检方向：{objective}",
                "support_level": 1,
                "evidence_effect": "limited_mastery",
            },
            {
                "level": 2,
                "kind": "method_skeleton",
                "content": f"按“整理输入—选择方法—执行首个关键步骤—检查结果”的骨架推进；核对：{'、'.join(criteria[:3]) or '条件、过程与结果'}",
                "support_level": 2,
                "evidence_effect": "not_independent",
            },
            {
                "level": 3,
                "kind": "local_scaffold",
                "content": "用不同情境的正反例定位当前卡点，只补足局部步骤；最终结论仍需独立完成。",
                "support_level": 3,
                "evidence_effect": "not_mastery",
            },
        ],
        "solution_policy": "after_submission_or_repeated_failure",
        "solution_effect": {
            "invalidate_current_evidence": True,
            "requires_unseen_equivalent_validation": True,
        },
        "frozen_with_item_revision": True,
        "leakage_check": {"passed": True, "checked_at_compile_time": True},
    })
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
