"""Layered quality scoring for generated assessment contracts."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

from assessment_blueprint import INPUT_CONTRACT_SCHEMA, INPUT_MODES


QUESTION_QUALITY_SCHEMA = "question_quality_report_v2"
QUALITY_WEIGHTS = {
    "correctness_and_verifiability": 25,
    "curriculum_targeting": 20,
    "answerability_and_completeness": 15,
    "answer_and_rubric": 15,
    "difficulty_fit": 10,
    "clarity": 5,
    "diversity": 5,
    "renderability": 5,
}

MINIMUM_TOTAL_SCORE = 85
MINIMUM_CORRECTNESS_SCORE = 22
MINIMUM_TARGETING_SCORE = 16
MAX_REFERENCE_SIMILARITY = 0.65

_REPAIRABLE_HARD_CODES = {
    "MISSING_CONDITION",
    "ANSWER_CONFLICT",
    "ANSWER_OR_RUBRIC_MISSING",
    "INPUT_CONTRACT_MISMATCH",
    "MARKDOWN_INVALID",
    "CODE_MATERIAL_NOT_RENDERABLE",
    "PROMPT_TOO_LONG",
    "TASK_TOO_LONG",
    "SOURCE_DUMP",
    "REFERENCE_SIMILARITY_HIGH",
    "VALIDATION_FAILED",
}


def evaluate_question_contract_quality(
    contract: dict[str, Any],
    *,
    objective: dict[str, Any],
    slot: dict[str, Any] | None,
    references: Iterable[dict[str, Any]] = (),
    existing_prompts: Iterable[str] = (),
    semantic_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed score and a machine-actionable repair decision."""
    spec = contract.get("question_spec") or {}
    solution = contract.get("solution_envelope") or {}
    validation = contract.get("solution_validation") or {}
    prompt = str(contract.get("prompt") or "").strip()
    task_text = str((spec.get("task") or {}).get("rendered_text") or "")
    input_contract = (
        spec.get("input_contract")
        or contract.get("input_contract")
        or {}
    )
    issues: list[dict[str, Any]] = []
    hard_checks = {
        "schema": spec.get("schema_version") == "question_spec_v2",
        "input_contract": _valid_input_contract(input_contract),
        "answer_or_rubric": (
            solution.get("canonical_answer") is not None
            or bool(solution.get("rubric"))
        ),
        "validation": bool(validation.get("passed")),
        "markdown": _markdown_valid(prompt),
        "code_rendering": _code_rendering_valid(spec),
        "prompt_budget": _prompt_within_budget(spec, prompt),
        "task_budget": len(task_text) <= 300,
        "source_isolation": not _looks_like_source_dump(
            prompt,
            str(objective.get("source_excerpt") or ""),
        ),
        "answer_leakage": not _answer_leaked(
            prompt,
            solution.get("canonical_answer"),
        ),
        "choice_options": (
            str(input_contract.get("mode") or "") != "choice"
            or _valid_choice_options(
                spec.get("options"),
                solution.get("canonical_answer"),
            )
        ),
        "runner_attestation": (
            str(solution.get("validation_mode") or "")
            != "code_validator"
            or bool(
                (
                    validation.get("validator_result") or {}
                ).get("runner_attested")
            )
        ),
        "blueprint_contract": not bool(
            contract.get("contract_violations")
        ),
    }
    hard_issue_map = {
        "schema": ("SCHEMA_INVALID", "题目结构不符合question_spec_v2"),
        "input_contract": (
            "INPUT_CONTRACT_MISMATCH",
            "作答组件无法承载当前题目",
        ),
        "answer_or_rubric": (
            "ANSWER_OR_RUBRIC_MISSING",
            "标准答案或评分量规缺失",
        ),
        "validation": ("VALIDATION_FAILED", "独立求解或验证未通过"),
        "markdown": ("MARKDOWN_INVALID", "Markdown或代码围栏不完整"),
        "code_rendering": (
            "CODE_MATERIAL_NOT_RENDERABLE",
            "题面引用了代码，但学生端可见题面中没有完整的 Markdown 代码块",
        ),
        "prompt_budget": ("PROMPT_TOO_LONG", "普通题题面超过长度预算"),
        "task_budget": ("TASK_TOO_LONG", "任务要求超过300字"),
        "source_isolation": ("SOURCE_DUMP", "题面直接复制了大段课程正文"),
        "answer_leakage": ("ANSWER_LEAKAGE", "题面泄漏了标准答案"),
        "choice_options": (
            "CHOICE_OPTIONS_INVALID",
            "选择题缺少至少两个唯一选项",
        ),
        "runner_attestation": (
            "RUNNER_ATTESTATION_MISSING",
            "代码实现题未通过独立Runner隐藏测试",
        ),
        "blueprint_contract": (
            "BLUEPRINT_CONTRACT_CHANGED",
            "候选题擅自修改了蓝图锁定的验证器",
        ),
    }
    for check, passed in hard_checks.items():
        if passed:
            continue
        code, message = hard_issue_map[check]
        issues.append(_issue(code, "critical", message))

    reference_similarity = _maximum_similarity(prompt, references)
    hard_checks["reference_similarity"] = (
        reference_similarity < MAX_REFERENCE_SIMILARITY
    )
    if not hard_checks["reference_similarity"]:
        issues.append(
            _issue(
                "REFERENCE_SIMILARITY_HIGH",
                "critical",
                "题面与参考来源过于相似",
                evidence={"similarity": round(reference_similarity, 4)},
            )
        )

    duplicate_similarity = _maximum_prompt_similarity(
        prompt,
        existing_prompts,
    )
    hard_checks["not_duplicate"] = duplicate_similarity < 0.9
    if not hard_checks["not_duplicate"]:
        issues.append(
            _issue(
                "DUPLICATE_QUESTION",
                "critical",
                "题目与当前题库已有题目高度重复",
                evidence={"similarity": round(duplicate_similarity, 4)},
            )
        )

    semantic = deepcopy(semantic_report or {})
    semantic_issues = [
        deepcopy(issue)
        for issue in semantic.get("issues") or []
        if isinstance(issue, dict) and issue.get("code")
    ]
    issues.extend(semantic_issues)
    dimensions = _dimension_scores(
        contract,
        objective=objective,
        slot=slot,
        semantic_report=semantic,
        duplicate_similarity=duplicate_similarity,
    )
    total_score = sum(dimensions.values())
    hard_gate_passed = all(hard_checks.values())
    minimum_dimension_passed = all(
        dimensions[name] >= int(weight * 0.6)
        for name, weight in QUALITY_WEIGHTS.items()
    )
    score_gate_passed = bool(
        total_score >= MINIMUM_TOTAL_SCORE
        and dimensions["correctness_and_verifiability"]
        >= MINIMUM_CORRECTNESS_SCORE
        and dimensions["curriculum_targeting"]
        >= MINIMUM_TARGETING_SCORE
        and minimum_dimension_passed
    )
    semantic_confidence = float(
        semantic.get("confidence")
        or (
            1.0
            if validation.get("deterministic")
            and validation.get("passed")
            else 0.0
        )
    )
    semantic_passed = bool(
        semantic.get("passed")
        if "passed" in semantic
        else (
            validation.get("deterministic")
            and validation.get("passed")
        )
    )
    eligible = bool(
        hard_gate_passed
        and score_gate_passed
        and (
            (
                validation.get("deterministic")
                and validation.get("passed")
            )
            or (
                semantic_passed
                and semantic_confidence >= 0.85
                and validation.get("independent_solution_present", True)
            )
        )
    )
    critical_issue_codes = {
        str(issue.get("code") or "")
        for issue in issues
        if issue.get("severity") == "critical"
    }
    if eligible:
        decision = "publish"
    elif any(
        code not in _REPAIRABLE_HARD_CODES
        for code in critical_issue_codes
    ):
        decision = "regenerate"
    elif critical_issue_codes:
        # A failed deterministic answer check can drive the score below 75,
        # but it is still a local answer/validator defect. Preserve the
        # blueprint slot and repair that defect instead of paying for a full
        # question regeneration.
        decision = "repair"
    elif total_score < 75:
        decision = "regenerate"
    else:
        decision = "repair"
    return {
        "schema_version": QUESTION_QUALITY_SCHEMA,
        "passed": eligible,
        "status": (
            "passed"
            if eligible
            else (
                "failed"
                if not hard_gate_passed
                else "needs_repair"
            )
        ),
        "score": total_score,
        "threshold": MINIMUM_TOTAL_SCORE,
        "dimensions": dimensions,
        "hard_gates": hard_checks,
        "minimum_dimension_passed": minimum_dimension_passed,
        "semantic": {
            "passed": semantic_passed,
            "confidence": semantic_confidence,
            "evidence": deepcopy(semantic.get("evidence") or []),
        },
        "reference_similarity": round(reference_similarity, 4),
        "duplicate_similarity": round(duplicate_similarity, 4),
        "issues": _deduplicate_issues(issues),
        "decision": decision,
    }


def _dimension_scores(
    contract: dict[str, Any],
    *,
    objective: dict[str, Any],
    slot: dict[str, Any] | None,
    semantic_report: dict[str, Any],
    duplicate_similarity: float,
) -> dict[str, int]:
    spec = contract.get("question_spec") or {}
    solution = contract.get("solution_envelope") or {}
    validation = contract.get("solution_validation") or {}
    prompt = str(contract.get("prompt") or "")
    target_text = " ".join([
        str(objective.get("objective") or ""),
        *[str(value) for value in objective.get("knowledge") or []],
        *[str(value) for value in objective.get("skills") or []],
    ])
    overlap = _token_overlap(prompt, target_text)
    semantic_dimensions = semantic_report.get("dimensions") or {}

    correctness = (
        25
        if validation.get("passed")
        else (
            22
            if semantic_report.get("solution_consistent")
            and float(semantic_report.get("confidence") or 0) >= 0.85
            else 0
        )
    )
    targeting = _bounded_dimension(
        semantic_dimensions.get("curriculum_targeting"),
        fallback=20 if overlap >= 0.15 else (16 if overlap > 0 else 8),
        maximum=20,
    )
    complete = all([
        str((spec.get("stimulus") or {}).get("rendered_text") or "").strip(),
        str((spec.get("task") or {}).get("rendered_text") or "").strip(),
        spec.get("constraints") is not None,
        spec.get("response_contract") is not None,
    ])
    answerability = _bounded_dimension(
        semantic_dimensions.get("answerability_and_completeness"),
        fallback=15 if complete else 7,
        maximum=15,
    )
    answer_score = 15 if (
        solution.get("canonical_answer") is not None
        or solution.get("rubric")
    ) else 0
    difficulty = _bounded_dimension(
        semantic_dimensions.get("difficulty_fit"),
        fallback=10 if (
            spec.get("difficulty_contract")
            or (slot or {}).get("difficulty_contract")
        ) else 6,
        maximum=10,
    )
    clarity = _bounded_dimension(
        semantic_dimensions.get("clarity"),
        fallback=5 if 24 <= len(prompt) <= 1200 else 3,
        maximum=5,
    )
    diversity = 5 if duplicate_similarity < 0.75 else 3
    renderability = 5 if _valid_input_contract(
        spec.get("input_contract")
        or contract.get("input_contract")
        or {}
    ) else 0
    return {
        "correctness_and_verifiability": correctness,
        "curriculum_targeting": targeting,
        "answerability_and_completeness": answerability,
        "answer_and_rubric": answer_score,
        "difficulty_fit": difficulty,
        "clarity": clarity,
        "diversity": diversity,
        "renderability": renderability,
    }


def _valid_input_contract(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != INPUT_CONTRACT_SCHEMA:
        return False
    mode = str(value.get("mode") or "")
    if mode not in INPUT_MODES:
        return False
    if mode == "choice":
        return True
    fields = value.get("fields")
    return isinstance(fields, list) and bool(fields)


def _valid_choice_options(
    value: Any,
    canonical_answer: Any,
) -> bool:
    if not isinstance(value, list) or len(value) < 2:
        return False
    identifiers = [
        str(
            option.get("id")
            or option.get("value")
            or ""
        ).strip()
        for option in value
        if isinstance(option, dict)
    ]
    correct_id = (
        canonical_answer.get("selected_option_id")
        if isinstance(canonical_answer, dict)
        else canonical_answer
    )
    return bool(
        len(identifiers) == len(value)
        and all(identifiers)
        and len(set(identifiers)) == len(identifiers)
        and str(correct_id or "") in identifiers
    )


def _prompt_within_budget(
    spec: dict[str, Any],
    prompt: str,
) -> bool:
    archetype = str(spec.get("archetype_id") or "")
    limit = (
        3000
        if archetype in {"evidence_argument", "data_interpretation"}
        else 1200
    )
    return len(prompt) <= limit


def _markdown_valid(value: str) -> bool:
    if value.count("```") % 2:
        return False
    return not any(
        marker in value
        for marker in (
            "<!-- BODY_START -->",
            "<!-- BODY_END -->",
        )
    )


def _code_rendering_valid(spec: dict[str, Any]) -> bool:
    stimulus = str(
        (spec.get("stimulus") or {}).get("rendered_text") or ""
    )
    task = str((spec.get("task") or {}).get("rendered_text") or "")
    combined = f"{stimulus}\n{task}"
    has_fenced_code = bool(
        re.search(
            r"```(?:python|javascript|js|typescript|ts|java|cpp|c)\s*\n",
            combined,
            flags=re.IGNORECASE,
        )
    )
    references_visible_code = any(
        marker in task.casefold()
        for marker in (
            "上述代码",
            "以上代码",
            "下列代码",
            "following code",
            "code above",
        )
    )
    raw_code_lines = sum(
        1
        for line in stimulus.splitlines()
        if re.match(
            r"^\s*(?:class|def|async\s+def|from|import|const|let|var|"
            r"function|return|del)\b",
            line,
        )
        or re.match(r"^\s*[A-Za-z_]\w*\s*=(?!=)", line)
    )
    if references_visible_code or raw_code_lines >= 2:
        return has_fenced_code
    return True


def _looks_like_source_dump(
    prompt: str,
    source: str,
) -> bool:
    normalized_prompt = _similarity_text(prompt)
    normalized_source = _similarity_text(source)
    if len(normalized_source) < 300 or len(normalized_prompt) < 200:
        return False
    if (
        len(normalized_source) >= 300
        and normalized_source in normalized_prompt
    ):
        return True
    ratio = SequenceMatcher(
        None,
        normalized_prompt[:5000],
        normalized_source[:5000],
    ).ratio()
    return ratio >= 0.72


def _answer_leaked(prompt: str, canonical: Any) -> bool:
    if not isinstance(canonical, (str, int, float)):
        return False
    answer = str(canonical).strip()
    if len(answer) < 4:
        return False
    return _similarity_text(answer) in _similarity_text(prompt)


def _maximum_similarity(
    prompt: str,
    references: Iterable[dict[str, Any]],
) -> float:
    prompt_text = _similarity_text(prompt)
    if not prompt_text:
        return 0.0
    return max(
        [
            SequenceMatcher(
                None,
                prompt_text,
                _similarity_text(
                    str(reference.get("reference_excerpt") or "")
                ),
            ).ratio()
            for reference in references
            if reference.get("reference_excerpt")
        ]
        or [0.0]
    )


def _maximum_prompt_similarity(
    prompt: str,
    existing_prompts: Iterable[str],
) -> float:
    normalized = _similarity_text(prompt)
    if not normalized:
        return 0.0
    return max(
        [
            SequenceMatcher(
                None,
                normalized,
                _similarity_text(str(value)),
            ).ratio()
            for value in existing_prompts
            if str(value).strip()
        ]
        or [0.0]
    )


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not right_tokens:
        return 0.0
    return len(left_tokens.intersection(right_tokens)) / len(
        right_tokens
    )


def _tokens(value: str) -> list[str]:
    english = re.findall(r"[a-z][a-z0-9_+#-]{1,30}", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,12}", value)
    grams = [
        group[index:index + width]
        for group in chinese
        for width in (2, 3, 4)
        for index in range(max(0, len(group) - width + 1))
    ]
    return list(dict.fromkeys([*english, *chinese, *grams]))


def _similarity_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _bounded_dimension(
    value: Any,
    *,
    fallback: int,
    maximum: int,
) -> int:
    try:
        resolved = int(round(float(value)))
    except (TypeError, ValueError):
        resolved = fallback
    return max(0, min(maximum, resolved))


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": deepcopy(evidence or {}),
    }


def _deduplicate_issues(
    issues: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        code = str(issue.get("code") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(deepcopy(issue))
    return result


__all__ = [
    "MAX_REFERENCE_SIMILARITY",
    "MINIMUM_TOTAL_SCORE",
    "QUALITY_WEIGHTS",
    "QUESTION_QUALITY_SCHEMA",
    "evaluate_question_contract_quality",
]
