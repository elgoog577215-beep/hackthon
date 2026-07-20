"""Cross-subject diversity planning, fingerprints, and deterministic gates."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import hashlib
import json
import os
import re
from typing import Any, Iterable


DIVERSITY_PLAN_SCHEMA = "question_diversity_plan_v1"
DIVERSITY_SIGNATURE_SCHEMA = "question_diversity_signature_v1"
DIVERSITY_REPORT_SCHEMA = "question_diversity_report_v1"


_LEVEL_PLANS = {
    "concept_check": {
        "cognitive_action": "recognize_or_discriminate",
        "reasoning_route": "single_decisive_property",
        "instance_role": "minimal_concept_instance",
        "context_style": "direct_or_canonical",
    },
    "objective_practice": {
        "cognitive_action": "apply_and_verify",
        "reasoning_route": "multi_step_application",
        "instance_role": "worked_novel_instance",
        "context_style": "concrete_problem",
    },
    "mastery_check": {
        "cognitive_action": "transfer_design_or_critique",
        "reasoning_route": "constraint_transfer_and_check",
        "instance_role": "unseen_transfer_instance",
        "context_style": "authentic_or_counterfactual",
    },
}


def compile_diversity_plan(
    *,
    discipline_family: str,
    practice_level: str,
    variant_index: int,
    objective: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a deterministic slot-level diversity contract."""
    base = deepcopy(
        _LEVEL_PLANS.get(
            str(practice_level or ""),
            _LEVEL_PLANS["objective_practice"],
        )
    )
    misconceptions = [
        str(value).strip()
        for value in (objective or {}).get("misconceptions") or []
        if str(value).strip()
    ]
    knowledge = [
        str(value).strip()
        for value in (objective or {}).get("knowledge") or []
        if str(value).strip()
    ]
    target_index = int(variant_index) % max(1, len(misconceptions) or 1)
    plan = {
        "schema_version": DIVERSITY_PLAN_SCHEMA,
        "discipline_family": str(discipline_family or "general"),
        "practice_level": str(practice_level or ""),
        "variant_index": int(variant_index),
        **base,
        "target_misconception": (
            misconceptions[target_index] if misconceptions else ""
        ),
        "knowledge_focus": (
            knowledge[int(variant_index) % len(knowledge)]
            if knowledge
            else str((objective or {}).get("objective") or "")
        ),
        "hard_rules": [
            "do_not_reuse_core_material_or_instance",
            "do_not_create_a_new_question_by_format_or_wording_only",
            "differ_on_at_least_two_of_instance_action_reasoning",
        ],
    }
    plan["plan_id"] = _digest(plan, prefix="qdp_")
    return plan


def build_diversity_signature(
    question: dict[str, Any],
    *,
    discipline_family: str | None = None,
) -> dict[str, Any]:
    """Extract a compact, explainable cross-subject semantic fingerprint."""
    spec = question.get("question_spec") or {}
    stimulus = spec.get("stimulus") or {}
    task = spec.get("task") or {}
    material = str(stimulus.get("rendered_text") or "").strip()
    if not material:
        material = "\n".join(
            str(value).strip()
            for value in question.get("input_materials") or []
            if str(value).strip()
        )
    if not material:
        material = str(question.get("prompt") or "").strip()
    task_text = str(task.get("rendered_text") or "").strip()
    if not task_text:
        task_text = str(question.get("deliverable") or "").strip()
    solution = (
        question.get("solution_envelope")
        or question.get("solution")
        or {}
    )
    answer_text = _stable_text(solution.get("canonical_answer"))
    reasoning_text = _stable_text(solution.get("solution_graph"))
    family = str(
        discipline_family
        or (question.get("assessment_slot") or {}).get("discipline_family")
        or (question.get("design_brief") or {}).get(
            "discipline_family"
        )
        or "general"
    )
    plugin_id = _plugin_id(family, content=f"{material}\n{task_text}")
    anchors = _plugin_anchors(
        plugin_id,
        material=material,
        task=task_text,
    )
    normalized_material = _normalize(material)
    material_tokens = _semantic_tokens(material, plugin_id=plugin_id)
    task_tokens = _semantic_tokens(task_text, plugin_id=plugin_id)
    answer_tokens = _semantic_tokens(answer_text, plugin_id=plugin_id)
    reasoning_tokens = _semantic_tokens(
        reasoning_text,
        plugin_id=plugin_id,
    )
    cognitive_action, reasoning_route = _task_semantics(
        task_text,
        question_type=str(
            question.get("question_type")
            or spec.get("question_type")
            or ""
        ),
        practice_level=str(
            question.get("practice_level")
            or spec.get("practice_level")
            or (
                (question.get("practice_levels") or [""])[0]
                if question.get("practice_levels")
                else ""
            )
        ),
    )
    diversity_plan = (
        (question.get("design_brief") or {}).get(
            "diversity_plan"
        )
        or {}
    )
    payload = {
        "schema_version": DIVERSITY_SIGNATURE_SCHEMA,
        "plugin_id": plugin_id,
        "discipline_family": family,
        "node_id": str(
            question.get("node_id")
            or spec.get("node_id")
            or ""
        ),
        "objective_id": str(
            question.get("objective_id")
            or spec.get("objective_id")
            or ""
        ),
        "practice_level": str(
            question.get("practice_level")
            or spec.get("practice_level")
            or (
                (question.get("practice_levels") or [""])[0]
                if question.get("practice_levels")
                else ""
            )
        ),
        "question_type": str(
            question.get("question_type")
            or spec.get("question_type")
            or ""
        ),
        "material_digest": _digest(
            normalized_material,
            prefix="mat_",
        ),
        "material_length": len(normalized_material),
        "material_preview": _collapse(material)[:180],
        "material_tokens": material_tokens[:120],
        "task_preview": _collapse(task_text)[:180],
        "task_tokens": task_tokens[:100],
        "anchors": anchors[:60],
        "answer_tokens": answer_tokens[:80],
        "reasoning_tokens": reasoning_tokens[:120],
        "cognitive_action": str(
            diversity_plan.get("cognitive_action")
            or cognitive_action
        ),
        "reasoning_route": str(
            diversity_plan.get("reasoning_route")
            or reasoning_route
        ),
    }
    payload["signature_id"] = _digest(payload, prefix="qds_")
    return payload


def compare_diversity_signatures(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Compare two signatures and return deterministic duplicate evidence."""
    resolved_threshold = _resolved_threshold(
        left,
        right,
        explicit=threshold,
    )
    left_material = _normalize(
        str(left.get("material_preview") or "")
    )
    right_material = _normalize(
        str(right.get("material_preview") or "")
    )
    sequence_similarity = (
        SequenceMatcher(None, left_material, right_material).ratio()
        if left_material and right_material
        else 0.0
    )
    token_similarity = _jaccard(
        left.get("material_tokens") or [],
        right.get("material_tokens") or [],
    )
    task_sequence_similarity = _sequence_similarity(
        left.get("task_preview"),
        right.get("task_preview"),
    )
    task_token_similarity = _jaccard(
        left.get("task_tokens") or [],
        right.get("task_tokens") or [],
    )
    task_similarity = max(
        task_sequence_similarity,
        task_token_similarity,
    )
    same_cognitive_action = bool(
        left.get("cognitive_action")
        and left.get("cognitive_action")
        == right.get("cognitive_action")
    )
    same_reasoning_route = bool(
        left.get("reasoning_route")
        and left.get("reasoning_route")
        == right.get("reasoning_route")
    )
    anchor_similarity, shared_anchors = _jaccard_with_count(
        left.get("anchors") or [],
        right.get("anchors") or [],
    )
    shared_anchor_values = sorted(
        set(str(value) for value in left.get("anchors") or [])
        .intersection(
            str(value) for value in right.get("anchors") or []
        )
    )
    left_subject_anchors = [
        str(value)
        for value in left.get("anchors") or []
        if _informative_subject_anchor(str(value))
    ]
    right_subject_anchors = [
        str(value)
        for value in right.get("anchors") or []
        if _informative_subject_anchor(str(value))
    ]
    subject_anchor_similarity, shared_subject_anchors = (
        _jaccard_with_count(
            left_subject_anchors,
            right_subject_anchors,
        )
    )
    answer_similarity = _jaccard(
        left.get("answer_tokens") or [],
        right.get("answer_tokens") or [],
    )
    reasoning_similarity = _jaccard(
        left.get("reasoning_tokens") or [],
        right.get("reasoning_tokens") or [],
    )
    exact_material = bool(
        int(left.get("material_length") or 0) >= 12
        and left.get("material_digest")
        and left.get("material_digest") == right.get("material_digest")
    )
    exact_material_duplicate = bool(
        exact_material
        and (
            task_similarity >= 0.9
            or (
                task_similarity >= 0.45
                and (
                    same_cognitive_action
                    or same_reasoning_route
                )
            )
        )
    )
    decisive_symbolic_anchor = any(
        value.startswith("tuple:")
        and len(value.removeprefix("tuple:")) >= 3
        and re.search(r"[a-z]", value, re.IGNORECASE)
        and re.search(r"\d", value)
        for value in shared_anchor_values
    )
    structural_match = bool(
        (
            shared_anchors >= 1
            and anchor_similarity >= 0.8
            and any(
                len(value) >= 12
                and not value.startswith("number:")
                for value in shared_anchor_values
            )
        )
        or (
            decisive_symbolic_anchor
            and (
                task_similarity >= 0.2
                or same_cognitive_action
            )
        )
        or (
            shared_subject_anchors >= 2
            and subject_anchor_similarity >= 0.5
        )
        or shared_subject_anchors >= 3
    )
    solution_match = bool(
        answer_similarity >= 0.82
        and reasoning_similarity >= 0.72
        and max(sequence_similarity, token_similarity) >= 0.5
    )
    material_similarity = max(
        sequence_similarity,
        token_similarity,
    )
    material_task_similarity = material_similarity * (
        (
            0.4 + 0.3 * task_similarity
        )
        if (
            not same_cognitive_action
            and not same_reasoning_route
        )
        else (
            0.55 + 0.45 * task_similarity
        )
    )
    overall = max(
        material_task_similarity,
        (
            anchor_similarity * (0.6 + 0.4 * task_similarity)
            if shared_anchors >= 2
            else 0.0
        ),
        (
            subject_anchor_similarity
            if shared_subject_anchors >= 2
            else 0.0
        ),
        (
            (answer_similarity + reasoning_similarity) / 2
            if solution_match
            else 0.0
        ),
    )
    duplicate = bool(
        exact_material_duplicate
        or structural_match
        or solution_match
        or overall >= resolved_threshold
    )
    reasons: list[str] = []
    if exact_material_duplicate:
        reasons.append("exact_material")
    if structural_match:
        reasons.append("shared_subject_anchors")
    if solution_match:
        reasons.append("same_answer_and_reasoning")
    if overall >= resolved_threshold:
        reasons.append("semantic_threshold")
    return {
        "duplicate": duplicate,
        "overall_similarity": round(overall, 4),
        "threshold": resolved_threshold,
        "signals": {
            "material_sequence": round(sequence_similarity, 4),
            "material_tokens": round(token_similarity, 4),
            "task_sequence": round(task_sequence_similarity, 4),
            "task_tokens": round(task_token_similarity, 4),
            "task_similarity": round(task_similarity, 4),
            "same_cognitive_action": same_cognitive_action,
            "same_reasoning_route": same_reasoning_route,
            "subject_anchors": round(anchor_similarity, 4),
            "shared_anchor_count": shared_anchors,
            "subject_anchor_similarity": round(
                subject_anchor_similarity,
                4,
            ),
            "shared_subject_anchor_count": shared_subject_anchors,
            "shared_anchors": shared_anchor_values[:12],
            "answer_facts": round(answer_similarity, 4),
            "reasoning_path": round(reasoning_similarity, 4),
        },
        "reasons": reasons,
    }


def evaluate_question_diversity(
    question: dict[str, Any],
    *,
    existing_questions: Iterable[dict[str, Any]] = (),
    discipline_family: str | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Evaluate a question against accepted and historical questions."""
    signature = build_diversity_signature(
        question,
        discipline_family=discipline_family,
    )
    comparisons: list[dict[str, Any]] = []
    for index, existing in enumerate(existing_questions):
        if not isinstance(existing, dict):
            continue
        other_signature = (
            existing
            if existing.get("schema_version")
            == DIVERSITY_SIGNATURE_SCHEMA
            else build_diversity_signature(
                existing,
                discipline_family=discipline_family,
            )
        )
        comparison = compare_diversity_signatures(
            signature,
            other_signature,
            threshold=threshold,
        )
        comparison["other_signature_id"] = other_signature.get(
            "signature_id"
        )
        comparison["other_question_id"] = str(
            existing.get("item_id")
            or existing.get("task_revision_id")
            or existing.get("revision_id")
            or existing.get("question_id")
            or f"accepted_{index + 1}"
        )
        comparisons.append(comparison)
    strongest = max(
        comparisons,
        key=lambda value: float(
            value.get("overall_similarity") or 0
        ),
        default={
            "duplicate": False,
            "overall_similarity": 0.0,
            "signals": {},
            "reasons": [],
            "other_question_id": "",
            "other_signature_id": "",
        },
    )
    duplicate_matches = [
        comparison
        for comparison in comparisons
        if comparison.get("duplicate")
    ]
    return {
        "schema_version": DIVERSITY_REPORT_SCHEMA,
        "passed": not duplicate_matches,
        "signature": signature,
        "comparison_count": len(comparisons),
        "duplicate_match_count": len(duplicate_matches),
        "max_similarity": float(
            strongest.get("overall_similarity") or 0
        ),
        "closest_question_id": strongest.get("other_question_id"),
        "closest_signature_id": strongest.get("other_signature_id"),
        "signals": deepcopy(strongest.get("signals") or {}),
        "reasons": list(strongest.get("reasons") or []),
        "threshold": (
            strongest.get("threshold")
            if comparisons
            else _resolved_threshold(
                signature,
                signature,
                explicit=threshold,
            )
        ),
    }


def forbidden_diversity_context(
    questions: Iterable[dict[str, Any]],
    *,
    discipline_family: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    signatures = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        signature = (
            question
            if question.get("schema_version")
            == DIVERSITY_SIGNATURE_SCHEMA
            else build_diversity_signature(
                question,
                discipline_family=discipline_family,
            )
        )
        signatures.append({
            "signature_id": signature.get("signature_id"),
            "practice_level": signature.get("practice_level"),
            "question_type": signature.get("question_type"),
            "material_preview": signature.get("material_preview"),
            "anchors": list(signature.get("anchors") or [])[:20],
            "cognitive_action": signature.get("cognitive_action"),
            "reasoning_route": signature.get("reasoning_route"),
        })
        if len(signatures) >= limit:
            break
    return {
        "schema_version": "question_diversity_constraints_v1",
        "forbidden_signatures": signatures,
        "rules": [
            "Do not reuse a forbidden core instance, source passage, data set, code sample, formula set, or scenario.",
            "Changing only response format, wording, labels, or numbers is not a new question.",
            "Differ from accepted questions on at least two of instance, cognitive action, and reasoning route.",
        ],
    }


def historical_questions_for_node(
    course_data: dict[str, Any],
    *,
    node_id: str,
) -> list[dict[str, Any]]:
    """Collect prior frozen questions for one node without crossing objectives."""
    pools: list[Any] = [
        (course_data.get("learning_assets") or {}).get("questions"),
        (course_data.get("question_bank") or {}).get("items"),
        (course_data.get("question_bank_bundle") or {}).get("items"),
        (course_data.get("_question_bank_bundle") or {}).get("items"),
    ]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pool in pools:
        for item in pool or []:
            if (
                not isinstance(item, dict)
                or str(item.get("node_id") or "") != str(node_id)
            ):
                continue
            identity = str(
                item.get("task_revision_id")
                or item.get("revision_id")
                or item.get("item_id")
                or _digest(item.get("prompt") or "", prefix="hist_")
            )
            if identity in seen:
                continue
            seen.add(identity)
            result.append(deepcopy(item))
    return result


def _plugin_id(family: str, *, content: str = "") -> str:
    normalized = str(family or "").casefold()
    if normalized in {
        "math_formal",
        "natural_science",
        "life_medical",
    }:
        return "stem_v1"
    if normalized == "programming_engineering":
        return "programming_v1"
    if normalized == "language_learning":
        return "language_v1"
    if normalized in {
        "humanities_social",
        "business_career",
    }:
        return "humanities_v1"
    sample = str(content or "")
    if (
        "```" in sample
        or re.search(
            r"\b(?:def|class|function|return|raise|throw)\b",
            sample,
        )
    ):
        return "programming_v1"
    if (
        re.search(r"[=≤≥∈→]|\\(?:mathbb|frac|dim|text)", sample)
        or any(
            marker in sample
            for marker in (
                "向量",
                "矩阵",
                "方程",
                "函数",
                "定理",
                "公理",
                "物理量",
            )
        )
    ):
        return "stem_v1"
    if any(
        marker in sample.casefold()
        for marker in (
            "语法",
            "翻译",
            "改写",
            "grammar",
            "translate",
            "rewrite",
        )
    ):
        return "language_v1"
    if any(
        marker in sample
        for marker in ("史料", "历史", "观点", "论证", "政策")
    ):
        return "humanities_v1"
    return "general_v1"


def _plugin_anchors(
    plugin_id: str,
    *,
    material: str,
    task: str,
) -> list[str]:
    combined = f"{material}\n{task}"
    anchors: list[str] = []
    if plugin_id == "stem_v1":
        anchors.extend(
            f"tuple:{_normalize(value)}"
            for value in re.findall(
                r"\([^()\n]{1,80}\)",
                combined,
            )
        )
        anchors.extend(
            f"relation:{_normalize(value)}"
            for value in re.findall(
                r"[^。；;\n]{0,70}(?:=|≤|≥|→|∈)[^。；;\n]{1,70}",
                combined,
            )
        )
        anchors.extend(
            f"number:{value}"
            for value in re.findall(r"(?<![\w])[-+]?\d+(?:\.\d+)?", combined)
        )
    elif plugin_id == "programming_v1":
        anchors.extend(
            f"code:{_normalize(value)}"
            for value in re.findall(
                r"```[\w+-]*\n([\s\S]*?)```",
                combined,
            )
        )
        anchors.extend(
            f"identifier:{value.casefold()}"
            for value in re.findall(
                r"\b(?:class|def|function|return|raise|throw|"
                r"if|for|while)\s+([A-Za-z_]\w*)",
                combined,
            )
        )
        anchors.extend(
            f"error:{value.casefold()}"
            for value in re.findall(
                r"\b[A-Za-z_]*(?:Error|Exception)\b",
                combined,
            )
        )
    elif plugin_id == "language_v1":
        anchors.extend(
            f"quote:{_normalize(value)}"
            for value in re.findall(
                r"[“\"]([^”\"\n]{4,160})[”\"]",
                combined,
            )
        )
        anchors.extend(
            f"language_task:{value.casefold()}"
            for value in re.findall(
                r"\b(?:translate|rewrite|summarize|compare|"
                r"grammar|tense|voice|register)\b",
                combined,
                flags=re.IGNORECASE,
            )
        )
    elif plugin_id == "humanities_v1":
        anchors.extend(
            f"date:{value}"
            for value in re.findall(
                r"\b(?:1[0-9]{3}|20[0-9]{2})\b",
                combined,
            )
        )
        anchors.extend(
            f"quote:{_normalize(value)}"
            for value in re.findall(
                r"[“\"]([^”\"\n]{4,200})[”\"]",
                combined,
            )
        )
        anchors.extend(
            f"source:{_normalize(value)}"
            for value in re.findall(
                r"(?:材料|史料|观点|source)\s*[一二三A-C1-3]?",
                combined,
                flags=re.IGNORECASE,
            )
        )
    else:
        anchors.extend(
            f"quote:{_normalize(value)}"
            for value in re.findall(
                r"[“\"]([^”\"\n]{4,160})[”\"]",
                combined,
            )
        )
        anchors.extend(
            f"number:{value}"
            for value in re.findall(r"(?<![\w])[-+]?\d+(?:\.\d+)?", combined)
        )
    return sorted({
        value
        for value in anchors
        if value and len(value) >= 3
    })


def _semantic_tokens(value: str, *, plugin_id: str) -> list[str]:
    collapsed = _collapse(value).casefold()
    english = re.findall(r"[a-z][a-z0-9_+#.-]{1,40}", collapsed)
    numbers = [
        f"n:{number}"
        for number in re.findall(r"(?<![\w])[-+]?\d+(?:\.\d+)?", collapsed)
    ]
    chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,24}", collapsed)
    chinese_grams = [
        f"c:{group[index:index + width]}"
        for group in chinese_groups
        for width in (2, 3)
        for index in range(max(0, len(group) - width + 1))
    ]
    plugin_terms: list[str] = []
    if plugin_id == "programming_v1":
        plugin_terms = [
            f"p:{term.casefold()}"
            for term in re.findall(
                r"\b(?:class|def|function|return|raise|throw|"
                r"error|exception|input|output|test)\b",
                collapsed,
                flags=re.IGNORECASE,
            )
        ]
    return list(dict.fromkeys([
        *english,
        *numbers,
        *chinese_grams,
        *plugin_terms,
    ]))


def _task_semantics(
    task: str,
    *,
    question_type: str,
    practice_level: str,
) -> tuple[str, str]:
    normalized_type = str(question_type or "").casefold()
    text = str(task or "").casefold()
    type_semantics = {
        "selected_response": ("discriminate", "option_elimination"),
        "single_choice": ("discriminate", "option_elimination"),
        "multiple_choice": ("discriminate", "option_elimination"),
        "output_prediction": ("predict", "state_or_output_trace"),
        "debugging_trace": ("diagnose", "fault_localization"),
        "state_trace_transfer": ("transfer", "state_trace"),
        "implementation_task": ("construct", "implementation_and_test"),
        "worked_solution": ("apply", "multi_step_derivation"),
        "evidence_analysis": ("analyze", "evidence_to_claim"),
        "source_argument": ("argue", "source_corroboration"),
        "language_production": ("produce", "constraint_satisfaction"),
        "scenario_deliverable": ("design", "constraint_tradeoff"),
    }
    if normalized_type in type_semantics:
        return type_semantics[normalized_type]
    if any(marker in text for marker in (
        "诊断", "纠错", "修复", "审查", "debug", "fix",
    )):
        return "diagnose", "fault_localization"
    if any(marker in text for marker in (
        "设计", "实现", "构造", "提交", "design", "implement",
    )):
        return "construct", "construction_and_test"
    if any(marker in text for marker in (
        "判断", "辨析", "选择", "identify", "classify", "choose",
    )):
        return "discriminate", "decisive_property"
    if any(marker in text for marker in (
        "证明", "论证", "解释", "prove", "argue", "explain",
    )):
        return "justify", "evidence_or_derivation"
    if any(marker in text for marker in (
        "计算", "求解", "应用", "compute", "solve", "apply",
    )):
        return "apply", "multi_step_application"
    fallback = _LEVEL_PLANS.get(
        str(practice_level or ""),
        _LEVEL_PLANS["objective_practice"],
    )
    return (
        str(fallback["cognitive_action"]),
        str(fallback["reasoning_route"]),
    )


def _sequence_similarity(left: Any, right: Any) -> float:
    left_text = _normalize(str(left or ""))
    right_text = _normalize(str(right or ""))
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _jaccard(left: Iterable[Any], right: Iterable[Any]) -> float:
    score, _ = _jaccard_with_count(left, right)
    return score


def _informative_subject_anchor(value: str) -> bool:
    if value.startswith("number:"):
        return False
    if value.startswith("tuple:"):
        payload = value.removeprefix("tuple:")
        return any(character.isdigit() for character in payload) or (
            len(payload) >= 10
        )
    return len(value) >= 12


def _jaccard_with_count(
    left: Iterable[Any],
    right: Iterable[Any],
) -> tuple[float, int]:
    left_set = {str(value) for value in left if str(value)}
    right_set = {str(value) for value in right if str(value)}
    if not left_set or not right_set:
        return 0.0, 0
    shared = len(left_set.intersection(right_set))
    return shared / len(left_set.union(right_set)), shared


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or ""), flags=re.UNICODE).casefold()


def _collapse(value: str) -> str:
    return " ".join(str(value or "").split())


def _stable_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _digest(value: Any, *, prefix: str) -> str:
    encoded = (
        value
        if isinstance(value, str)
        else json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return prefix + hashlib.sha256(
        str(encoded).encode("utf-8")
    ).hexdigest()[:16]


def _bounded_float(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(maximum, resolved))


def _resolved_threshold(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    explicit: float | None,
) -> float:
    if explicit is not None:
        raw: Any = explicit
    else:
        plugin = str(left.get("plugin_id") or "")
        same_plugin = plugin and plugin == str(
            right.get("plugin_id") or ""
        )
        plugin_key = {
            "stem_v1": "STEM",
            "programming_v1": "PROGRAMMING",
            "language_v1": "LANGUAGE",
            "humanities_v1": "HUMANITIES",
            "general_v1": "GENERAL",
        }.get(plugin if same_plugin else "")
        raw = (
            os.getenv(
                f"ASSESSMENT_DIVERSITY_THRESHOLD_{plugin_key}",
            )
            if plugin_key
            else None
        ) or os.getenv("ASSESSMENT_DIVERSITY_THRESHOLD", "0.72")
    return _bounded_float(
        raw,
        default=0.72,
        minimum=0.5,
        maximum=0.95,
    )


__all__ = [
    "DIVERSITY_PLAN_SCHEMA",
    "DIVERSITY_REPORT_SCHEMA",
    "DIVERSITY_SIGNATURE_SCHEMA",
    "build_diversity_signature",
    "compare_diversity_signatures",
    "compile_diversity_plan",
    "evaluate_question_diversity",
    "forbidden_diversity_context",
    "historical_questions_for_node",
]
