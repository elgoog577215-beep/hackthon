"""Formal-practice contracts shared by asset compilation and old-course projection."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from course_versioning import stable_hash
from reasoning_paths import compile_reasoning_support
from solution_presentation import present_solution_value


DEFAULT_PRACTICE_BATCH_SIZE = 3
DEFAULT_PRACTICE_QUESTION_TYPE = "single_choice"


INPUT_MODES = {
    "single_choice": "choice",
    "worked_solution": "rich_text",
    "implementation_task": "code_and_text",
    "evidence_analysis": "structured_text",
    "mechanism_explanation": "structured_text",
    "source_argument": "structured_text",
    "language_production": "language_response",
    "scenario_deliverable": "structured_text",
    "short_answer": "rich_text",
}


def project_default_single_choice(
    question_contract: dict[str, Any],
    *,
    misconception_labels: list[str] | None = None,
    variant_index: int = 0,
) -> dict[str, Any]:
    """Project one generated practice contract into the default choice UI.

    The original public task and private solution remain the semantic source.
    This projection only freezes four student-visible options and a private
    correct-option mapping, so historical/imported questions are untouched.
    """

    result = deepcopy(question_contract)
    solution = result.get("solution_envelope")
    question_spec = result.get("question_spec")
    if not isinstance(solution, dict) or not isinstance(question_spec, dict):
        raise ValueError(
            "single-choice projection requires question_spec and solution_envelope"
        )
    legacy_answer = deepcopy(
        solution.get("legacy_answer_spec") or {}
    )
    task = question_spec.setdefault("task", {})
    original_task = str(
        task.get("rendered_text")
        or result.get("prompt")
        or "完成当前题目"
    ).strip()
    canonical = solution.get("canonical_answer")
    acceptable_answers = solution.get("acceptable_answers") or []
    if canonical is None and acceptable_answers:
        canonical = deepcopy(acceptable_answers[0])
    if canonical is None:
        (
            options,
            correct_option_id,
            diagnostics,
            choice_canonical,
        ) = _compile_rubric_choice_options(
            deliverable=str(
                result.get("deliverable")
                or task.get("deliverable")
                or "题目要求的完整作答"
            ),
            criteria=[
                str(value).strip()
                for value in (
                    legacy_answer.get("criteria")
                    or solution.get("rubric")
                    or []
                )
                if str(value).strip()
            ],
            variant_index=variant_index,
        )
        canonical = choice_canonical
        choice_instruction = (
            f"{original_task.rstrip('。')}。"
            "比较下列四份作答方案，选择唯一一份同时满足题目材料、"
            "限制条件和全部交付要求的方案。"
        )
    else:
        options, correct_option_id, diagnostics = _compile_choice_options(
            canonical,
            misconception_labels=misconception_labels or [],
            variant_index=variant_index,
        )
        choice_instruction = (
            f"{original_task.rstrip('。')}。"
            "请先完成必要判断，再从下列选项中选择唯一正确答案。"
        )
    task["rendered_text"] = choice_instruction
    task["deliverable"] = "一个唯一选项"
    question_spec["response_contract"] = {
        "format": DEFAULT_PRACTICE_QUESTION_TYPE,
        "required_parts": ["selected_option_id"],
        "option_count": len(options),
        "selection_limit": 1,
    }
    question_spec["presentation_contract"] = {
        "mode": DEFAULT_PRACTICE_QUESTION_TYPE,
        "option_count": len(options),
        "selection_limit": 1,
    }

    solution_spec = deepcopy(
        legacy_answer.get("solution_spec") or {}
    )
    if not solution_spec:
        solution_spec = {
            "schema_version": "solution_spec_v1",
            "final_answer": deepcopy(canonical),
            "steps": deepcopy(
                (solution.get("solution_graph") or {}).get("steps") or []
            ),
            "checks": deepcopy(result.get("result_checks") or []),
        }
    elif solution_spec.get("final_answer") is None:
        solution_spec["final_answer"] = deepcopy(canonical)
    choice_answer_spec = {
        "type": "choice",
        "correct_option_id": correct_option_id,
        "canonical_answer": deepcopy(canonical),
        "criteria": deepcopy(
            legacy_answer.get("criteria")
            or solution.get("rubric")
            or ["选择唯一正确答案"]
        ),
        "expected_keywords": deepcopy(
            legacy_answer.get("expected_keywords") or []
        ),
        "pass_score": int(
            legacy_answer.get("pass_score")
            or (solution.get("validator_config") or {}).get("pass_score")
            or 70
        ),
        "solution_spec": solution_spec,
        "options": deepcopy(options),
        "choice_diagnostics": diagnostics,
    }
    solution["choice_answer_spec"] = choice_answer_spec
    old_solution_revision_id = str(
        solution.get("solution_revision_id") or ""
    )
    solution_revision_id = stable_hash(
        {
            "base_solution_revision_id": old_solution_revision_id,
            "question_type": DEFAULT_PRACTICE_QUESTION_TYPE,
            "options": options,
            "choice_answer_spec": choice_answer_spec,
        },
        prefix="sol_",
    )
    solution["solution_revision_id"] = solution_revision_id
    question_spec["solution_revision_id"] = solution_revision_id

    stimulus_text = str(
        (question_spec.get("stimulus") or {}).get("rendered_text") or ""
    ).strip()
    result["prompt"] = "\n".join(
        value
        for value in (stimulus_text, choice_instruction)
        if value
    )
    result["deliverable"] = "一个唯一选项"
    result["question_type"] = DEFAULT_PRACTICE_QUESTION_TYPE
    result["options"] = options
    result["estimated_minutes"] = min(
        5,
        max(1, int(result.get("estimated_minutes") or 3)),
    )
    return result


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


def _compile_choice_options(
    canonical: Any,
    *,
    misconception_labels: list[str],
    variant_index: int,
) -> tuple[list[dict[str, str]], str, dict[str, dict[str, str]]]:
    correct_text = _choice_text(canonical)
    distractor_values = _mutated_values(canonical)
    distractor_texts: list[str] = []
    for value in distractor_values:
        text = _choice_text(value)
        if text != correct_text and text not in distractor_texts:
            distractor_texts.append(text)
        if len(distractor_texts) == 3:
            break
    fallback_labels = [
        str(value).strip()
        for value in misconception_labels
        if str(value).strip()
    ]
    fallback_texts = [
        *[
            f"按“{label}”处理，并忽略题目中的其他限制条件。"
            for label in fallback_labels
        ],
        "只复述题意，不执行题目要求的判断或计算。",
        "直接套用一个相近结论，不检查它是否满足当前条件。",
        "得到局部结果后停止，不再核对边界、单位或证据。",
    ]
    for text in fallback_texts:
        if text != correct_text and text not in distractor_texts:
            distractor_texts.append(text)
        if len(distractor_texts) == 3:
            break

    correct_slot = _choice_slot(canonical, variant_index)
    ordered = list(distractor_texts[:3])
    ordered.insert(correct_slot, correct_text)
    option_ids = ("A", "B", "C", "D")
    options = [
        {
            "option_id": option_id,
            "text": text,
        }
        for option_id, text in zip(option_ids, ordered, strict=True)
    ]
    correct_option_id = option_ids[correct_slot]
    diagnostics = {
        option_id: (
            {"kind": "correct", "feedback": "该选项满足题目全部条件。"}
            if option_id == correct_option_id
            else {
                "kind": "distractor",
                "feedback": (
                    fallback_labels[index % len(fallback_labels)]
                    if fallback_labels
                    else "该选项遗漏或改变了题目中的关键条件。"
                ),
            }
        )
        for index, option_id in enumerate(option_ids)
    }
    return options, correct_option_id, diagnostics


def _compile_rubric_choice_options(
    *,
    deliverable: str,
    criteria: list[str],
    variant_index: int,
) -> tuple[
    list[dict[str, str]],
    str,
    dict[str, dict[str, str]],
    dict[str, Any],
]:
    requirements = list(dict.fromkeys(criteria)) or [
        f"完整交付“{deliverable}”",
        "每个主要判断都有题面依据",
        "满足全部限制条件",
        "完成结果检查",
    ]
    canonical = {
        "selection_basis": "rubric_complete_response",
        "deliverable": deliverable,
        "required_criteria": requirements,
    }
    requirement_text = "；".join(requirements)
    correct_text = (
        f"作答方案：完整交付“{deliverable}”，并逐项做到："
        f"{requirement_text}。"
    )
    first = requirements[0]
    last = requirements[-1]
    middle = requirements[1] if len(requirements) > 1 else "其他限制条件"
    distractors = [
        f"作答方案：只做到“{first}”，其余要求不再处理。",
        (
            f"作答方案：完成“{first}”和“{middle}”，"
            f"但明确省略“{last}”。"
        ),
        (
            f"作答方案：只复述题面或材料，不形成“{deliverable}”，"
            "也不逐项核对限制条件。"
        ),
    ]
    correct_slot = _choice_slot(canonical, variant_index)
    ordered = list(distractors)
    ordered.insert(correct_slot, correct_text)
    option_ids = ("A", "B", "C", "D")
    options = [
        {"option_id": option_id, "text": text}
        for option_id, text in zip(option_ids, ordered, strict=True)
    ]
    correct_option_id = option_ids[correct_slot]
    diagnostics = {
        option_id: (
            {
                "kind": "correct",
                "feedback": "该方案覆盖了全部可观察要求。",
            }
            if option_id == correct_option_id
            else {
                "kind": "distractor",
                "feedback": "该方案明确遗漏了至少一项必要要求。",
            }
        )
        for option_id in option_ids
    }
    return options, correct_option_id, diagnostics, canonical


def _mutated_values(value: Any) -> list[Any]:
    candidates: list[Any] = []
    scalar_paths = _scalar_paths(value)
    for position, path in enumerate(scalar_paths[:8]):
        original = _value_at_path(value, path)
        replacements = _scalar_replacements(original, position)
        for replacement in replacements:
            mutated = deepcopy(value)
            mutated = _replace_at_path(mutated, path, replacement)
            candidates.append(mutated)
    if isinstance(value, dict) and len(value) >= 2:
        keys = list(value)
        swapped = deepcopy(value)
        swapped[keys[0]], swapped[keys[1]] = (
            deepcopy(swapped[keys[1]]),
            deepcopy(swapped[keys[0]]),
        )
        candidates.append(swapped)
        shortened = deepcopy(value)
        shortened.pop(keys[-1], None)
        candidates.append(shortened)
    elif isinstance(value, list) and len(value) >= 2:
        candidates.append(list(reversed(deepcopy(value))))
        candidates.append(deepcopy(value[:-1]))
    return candidates


def _scalar_paths(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(value, dict):
        return [
            child
            for key, item in value.items()
            for child in _scalar_paths(item, (*path, key))
        ]
    if isinstance(value, (list, tuple)):
        return [
            child
            for index, item in enumerate(value)
            for child in _scalar_paths(item, (*path, index))
        ]
    return [path]


def _value_at_path(value: Any, path: tuple[Any, ...]) -> Any:
    current = value
    for key in path:
        current = current[key]
    return current


def _replace_at_path(
    value: Any,
    path: tuple[Any, ...],
    replacement: Any,
) -> Any:
    if not path:
        return replacement
    current = value
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement
    return value


def _scalar_replacements(value: Any, position: int) -> list[Any]:
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, (int, float)):
        offset = max(1, abs(value) * 0.1)
        if isinstance(value, int):
            offset = max(1, int(round(offset)))
        return [
            value + offset,
            value - offset,
            -value if value != 0 else 2,
        ]
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            number = float(match.group(0))
            replacement = number + max(1, abs(number) * 0.1)
            rendered = (
                str(int(replacement))
                if replacement.is_integer()
                else str(round(replacement, 4))
            )
            return [
                f"{value[:match.start()]}{rendered}{value[match.end():]}"
            ]
        return [f"{value}（条件不完整）"] if position == 0 else []
    return []


def _choice_text(value: Any) -> str:
    text = present_solution_value(value).strip()
    if len(text) <= 800:
        return text
    return f"{text[:797].rstrip()}…"


def _choice_slot(canonical: Any, variant_index: int) -> int:
    return int(
        stable_hash(
            {
                "canonical": canonical,
                "variant_index": variant_index,
            },
            prefix="choice_",
        )[-8:],
        16,
    ) % 4


def _legacy_reasoning_support(
    item: dict[str, Any],
    *,
    question_type: str,
) -> dict[str, Any]:
    prompt = str(
        item.get("prompt")
        or item.get("learning_objective")
        or item.get("deliverable")
        or item.get("title")
        or "当前冻结任务"
    )
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
