"""Domain-neutral assessment contracts used by question generation.

The module deliberately models *observable assessment work* instead of
individual course topics.  Topic-specific deterministic solvers can plug into
the resulting archetype and validation contracts without owning routing.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable

from course_pedagogy import coerce_persisted_profile
from course_versioning import stable_hash


COURSE_ASSESSMENT_PROFILE_SCHEMA = "course_assessment_profile_v1"
ASSESSMENT_OBJECTIVE_SCHEMA = "assessment_objective_v1"
QUESTION_SPEC_V2_SCHEMA = "question_spec_v2"
SOLUTION_ENVELOPE_SCHEMA = "solution_envelope_v1"


ASSESSMENT_ARCHETYPES: dict[str, dict[str, Any]] = {
    "concept_classification": {
        "title": "概念辨析与分类",
        "required_stimulus_fields": ["concepts", "cases"],
        "task_actions": ["classify", "distinguish", "explain_boundary"],
        "response_format": "classification_with_reasons",
        "eligible_validation_modes": [
            "exact_validator",
            "expert_rubric_validator",
        ],
        "hint_strategy": "boundary_and_counterexample",
    },
    "numeric_calculation": {
        "title": "数值计算与单位换算",
        "required_stimulus_fields": ["givens", "units", "conditions"],
        "task_actions": ["calculate", "convert", "check_units"],
        "response_format": "numeric_with_unit",
        "eligible_validation_modes": ["numeric_unit_validator"],
        "hint_strategy": "knowns_formula_units",
    },
    "symbolic_derivation": {
        "title": "符号推导、证明与形式化表达",
        "required_stimulus_fields": ["definitions", "conditions", "target"],
        "task_actions": ["derive", "prove", "formalize"],
        "response_format": "symbolic_reasoning",
        "eligible_validation_modes": [
            "symbolic_validator",
            "expert_rubric_validator",
        ],
        "hint_strategy": "premise_transform_check",
    },
    "data_interpretation": {
        "title": "数据、图表与模型解释",
        "required_stimulus_fields": ["dataset", "representation", "question"],
        "task_actions": ["interpret", "compare", "model"],
        "response_format": "claim_evidence_interpretation",
        "eligible_validation_modes": [
            "numeric_unit_validator",
            "evidence_validator",
        ],
        "hint_strategy": "read_axes_compare_explain",
    },
    "controlled_experiment": {
        "title": "实验设计、变量控制与误差分析",
        "required_stimulus_fields": ["research_question", "materials", "limits"],
        "task_actions": ["design", "control_variables", "analyze_error"],
        "response_format": "experiment_plan",
        "eligible_validation_modes": ["expert_rubric_validator"],
        "hint_strategy": "hypothesis_variables_measurement",
    },
    "code_execution": {
        "title": "代码跟踪、实现、测试与调试",
        "required_stimulus_fields": ["language", "code_or_contract", "tests"],
        "task_actions": ["trace", "implement", "test", "debug"],
        "response_format": "code_and_evidence",
        "eligible_validation_modes": [
            "code_validator",
            "state_trace_validator",
        ],
        "hint_strategy": "input_state_operation_check",
    },
    "evidence_argument": {
        "title": "材料阅读、证据提取与论证",
        "required_stimulus_fields": ["source_set", "question"],
        "task_actions": ["extract_evidence", "argue", "qualify"],
        "response_format": "claim_evidence_reasoning",
        "eligible_validation_modes": ["evidence_validator"],
        "hint_strategy": "claim_evidence_link",
    },
    "language_production": {
        "title": "语言理解、转换与情境表达",
        "required_stimulus_fields": ["language_context", "audience", "purpose"],
        "task_actions": ["comprehend", "transform", "produce"],
        "response_format": "contextual_language_response",
        "eligible_validation_modes": ["language_rubric_validator"],
        "hint_strategy": "purpose_register_structure",
    },
    "constrained_decision": {
        "title": "案例诊断、约束决策与方案比较",
        "required_stimulus_fields": ["case", "alternatives", "constraints"],
        "task_actions": ["diagnose", "compare", "decide"],
        "response_format": "decision_with_tradeoffs",
        "eligible_validation_modes": ["expert_rubric_validator"],
        "hint_strategy": "constraints_options_tradeoffs",
    },
    "integrated_performance": {
        "title": "跨章节设计、创作与综合任务",
        "required_stimulus_fields": ["multi_source_input", "requirements"],
        "task_actions": ["integrate", "design", "create", "validate"],
        "response_format": "integrated_deliverable",
        "eligible_validation_modes": ["expert_rubric_validator"],
        "hint_strategy": "decompose_connect_validate",
    },
}


PUBLIC_QUESTION_FIELDS = (
    "revision_id",
    "task_revision_id",
    "question_id",
    "node_id",
    "node_ids",
    "learning_objective",
    "objective_id",
    "concept_ids",
    "skill_unit_ids",
    "mistake_point_ids",
    "question_type",
    "difficulty_contract",
    "prompt",
    "subquestions",
    "options",
    "practice_level",
    "input_contract",
    "validation_policy",
    "assessment_role",
    "deliverable",
    "input_materials",
    "constraints",
    "result_checks",
    "source_status",
    "quality_status",
    "review_status",
)


def compile_course_assessment_profile(
    course_data: dict[str, Any],
) -> dict[str, Any]:
    """Compile a stable, course-local assessment capability profile."""
    pedagogy = coerce_persisted_profile(course_data)
    persisted = course_data.get("subject_pedagogy_profile") or {}
    family = pedagogy.primary_mode.value
    locked = bool(persisted.get("user_locked"))
    course_text = _course_text(course_data)
    high_stakes = _is_high_stakes_course(course_data, family)
    classification_confidence = (
        0.95
        if locked
        else (0.86 if persisted.get("primary_mode") else 0.72)
    )
    profile = {
        "schema_version": COURSE_ASSESSMENT_PROFILE_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "discipline": {
            "family": family,
            "label": pedagogy.primary_mode.value,
            "high_stakes": high_stakes,
        },
        "classification": {
            "method": (
                "teacher_locked"
                if locked
                else "structured_course_evidence"
            ),
            "confidence": classification_confidence,
            "signals": _discipline_signals(course_text, family),
        },
        "audience": str(
            course_data.get("target_audience")
            or (course_data.get("generation_request") or {}).get(
                "target_audience"
            )
            or "大学生"
        ),
        "course_purpose": str(
            course_data.get("course_purpose")
            or (course_data.get("generation_request") or {}).get(
                "course_purpose"
            )
            or "systematic"
        ),
        "notation_and_language": _notation_contract(course_text, family),
        "allowed_archetype_ids": list(ASSESSMENT_ARCHETYPES),
        "allowed_validation_modes": _validation_modes_for_family(family),
        "source_policy": {
            "priority": [
                "teacher_question_bank",
                "course_materials",
                "trusted_web_reference",
                "general_model_knowledge",
            ],
            "course_scope_only": True,
            "web_enabled": _web_enrichment_enabled(
                course_data
            ),
        },
        "review_policy": {
            "schema_version": "exception_driven_question_quality_v1",
            "high_stakes_requires_teacher": high_stakes,
            "low_confidence_requires_teacher": True,
            "comprehensive_requires_teacher": True,
            "deterministic_pass_auto_publish": True,
            "default_publish_after_validation": True,
            "post_publication_rework": True,
            "family_sample_rate": 0,
        },
    }
    profile["profile_revision_id"] = stable_hash(
        profile,
        prefix="cap_",
    )
    return profile


def _is_high_stakes_course(
    course_data: dict[str, Any],
    family: str,
) -> bool:
    """Classify course-level safety risk from identity, not incidental lesson words.

    Terms such as “诊断” are common in programming and engineering courses.
    Scanning every lesson body therefore creates broad false positives (for
    example, “内存泄漏诊断”).  High-stakes review is reserved for an explicitly
    medical family or a clearly medical/legal course identity.
    """
    if family == "life_medical":
        return True

    request = course_data.get("generation_request") or {}
    identity_text = " ".join(
        str(value or "")
        for value in (
            course_data.get("course_name"),
            course_data.get("course_purpose"),
            course_data.get("description"),
            request.get("course_name"),
            request.get("topic"),
            request.get("description"),
            request.get("requirements"),
        )
    ).lower()
    explicit_high_stakes_markers = (
        "临床",
        "患者",
        "处方",
        "用药",
        "手术",
        "诊疗",
        "治疗方案",
        "刑法",
        "诉讼",
        "法律实务",
        "司法考试",
    )
    if any(
        marker in identity_text
        for marker in explicit_high_stakes_markers
    ):
        return True

    medical_context = any(
        marker in identity_text
        for marker in ("医学", "疾病", "病理", "药理", "护理")
    )
    legal_context = family == "humanities_social" and any(
        marker in identity_text
        for marker in ("法律", "法学", "司法", "合规")
    )
    return bool(
        (medical_context and "诊断" in identity_text)
        or legal_context
    )


def compile_assessment_objectives(
    course_data: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compile observable assessment objectives for every level-two node."""
    resolved_profile = profile or compile_course_assessment_profile(
        course_data
    )
    result: list[dict[str, Any]] = []
    for node in course_data.get("nodes") or []:
        if int(node.get("node_level") or 1) != 2:
            continue
        node_id = str(node.get("node_id") or "")
        node_name = _strip_number(str(node.get("node_name") or ""))
        objective_text = str(
            node.get("learning_objective")
            or f"解释并应用{node_name}"
        ).strip()
        knowledge = _unique(
            [
                *[
                    str(value)
                    for value in node.get("key_points") or []
                ],
                node_name,
            ]
        )
        skills = _unique(
            [
                str(value)
                for value in node.get("assessment") or []
                if str(value).strip()
            ]
            or [objective_text]
        )
        source_refs, source_text = _objective_sources(
            course_data,
            node,
        )
        node_content = str(node.get("node_content") or "").strip()
        grounded_text = " ".join(
            value
            for value in (node_content, source_text)
            if value
        )
        sufficient = len(grounded_text) >= 40
        confidence = "high" if len(grounded_text) >= 120 else (
            "medium" if sufficient else "low"
        )
        risk_level = (
            "teacher_review"
            if (
                not sufficient
                or (
                    resolved_profile.get("discipline") or {}
                ).get("high_stakes")
            )
            else "low"
        )
        modalities = _answer_modalities(
            resolved_profile,
            objective_text,
            skills,
        )
        preferred_archetypes = _preferred_archetypes(
            resolved_profile,
            objective_text,
            skills,
            modalities,
        )
        item = {
            "schema_version": ASSESSMENT_OBJECTIVE_SCHEMA,
            "course_id": str(course_data.get("course_id") or ""),
            "node_id": node_id,
            "objective_id": stable_hash(
                {
                    "course_id": course_data.get("course_id"),
                    "node_id": node_id,
                    "objective": objective_text,
                },
                prefix="aobj_",
            ),
            "objective": objective_text,
            "knowledge": knowledge,
            "skills": skills,
            "misconceptions": _misconceptions(
                objective_text,
                knowledge,
            ),
            "observable_evidence": _observable_evidence(
                skills,
                modalities,
            ),
            "source_refs": source_refs,
            "source_excerpt": grounded_text[:2400],
            "source_sufficiency": (
                "sufficient" if sufficient else "insufficient"
            ),
            "answer_modalities": modalities,
            "preferred_archetype_ids": preferred_archetypes,
            "difficulty_contract": deepcopy(
                node.get("difficulty_contract")
                or {
                    "target_level": course_data.get(
                        "difficulty",
                        "intermediate",
                    )
                }
            ),
            "confidence": confidence,
            "risk_level": risk_level,
            "generation_status": (
                "ready" if sufficient else "candidate_only"
            ),
        }
        result.append(item)
    return result


def select_assessment_archetype(
    objective: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Select a typed assessment archetype from observable evidence."""
    allowed = set(
        profile.get("allowed_archetype_ids")
        or ASSESSMENT_ARCHETYPES
    )
    candidates = [
        value
        for value in objective.get("preferred_archetype_ids") or []
        if value in allowed and value in ASSESSMENT_ARCHETYPES
    ]
    selected = candidates[0] if candidates else "concept_classification"
    result = deepcopy(ASSESSMENT_ARCHETYPES[selected])
    result["archetype_id"] = selected
    result["selection_method"] = "structured_objective_contract"
    result["selection_confidence"] = (
        0.92 if candidates else 0.7
    )
    result["objective_id"] = objective.get("objective_id")
    return result


def project_public_question(
    question: dict[str, Any],
) -> dict[str, Any]:
    """Project an internal task through an explicit public allowlist."""
    return {
        field: deepcopy(question[field])
        for field in PUBLIC_QUESTION_FIELDS
        if field in question
    }


def _course_text(course_data: dict[str, Any]) -> str:
    return " ".join(
        [
            str(course_data.get("course_name") or ""),
            str(course_data.get("subject") or ""),
            *[
                " ".join([
                    str(node.get("node_name") or ""),
                    str(node.get("learning_objective") or ""),
                    str(node.get("node_content") or "")[:1000],
                ])
                for node in course_data.get("nodes") or []
            ],
        ]
    )


def _web_enrichment_enabled(
    course_data: dict[str, Any],
) -> bool:
    config = (
        (course_data.get("generation_request") or {}).get(
            "web_question_enrichment"
        )
        or course_data.get("web_question_enrichment")
        or {}
    )
    mode = str(config.get("mode") or "").strip()
    if mode:
        return mode != "off"
    if config.get("enabled") is not None:
        return bool(config.get("enabled"))
    return True


def _discipline_signals(text: str, family: str) -> list[str]:
    signal_map = {
        "math_formal": ("函数", "方程", "证明", "积分", "概率"),
        "programming_engineering": (
            "代码",
            "程序",
            "算法",
            "C++",
            "Java",
        ),
        "natural_science": ("实验", "物理", "化学", "热力学"),
        "life_medical": ("生物", "医学", "临床", "机制"),
        "humanities_social": ("材料", "历史", "社会", "论证"),
        "language_learning": ("阅读", "写作", "翻译", "语法"),
        "business_career": ("预算", "决策", "市场", "管理"),
    }
    lowered = text.lower()
    return [
        marker
        for marker in signal_map.get(family, ())
        if marker.lower() in lowered
    ][:8]


def _notation_contract(text: str, family: str) -> dict[str, Any]:
    languages = [
        marker
        for marker in ("C++", "Java", "Python", "JavaScript", "SQL")
        if marker.lower() in text.lower()
    ]
    return {
        "response_language": "zh-CN",
        "programming_languages": languages,
        "requires_units": family == "natural_science",
        "supports_symbolic_notation": family == "math_formal",
    }


def _validation_modes_for_family(family: str) -> list[str]:
    shared = ["exact_validator", "expert_rubric_validator"]
    extra = {
        "math_formal": ["numeric_unit_validator", "symbolic_validator"],
        "programming_engineering": [
            "code_validator",
            "state_trace_validator",
        ],
        "natural_science": [
            "numeric_unit_validator",
            "expert_rubric_validator",
        ],
        "humanities_social": ["evidence_validator"],
        "language_learning": ["language_rubric_validator"],
        "business_career": ["expert_rubric_validator"],
        "life_medical": ["expert_rubric_validator"],
    }.get(family, [])
    return _unique([*shared, *extra])


def _objective_sources(
    course_data: dict[str, Any],
    node: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    evidence_ids = {
        str(value)
        for value in (
            node.get("grounding_contract") or {}
        ).get("question_evidence_ids") or []
    }
    node_terms = set(
        _tokens(
            " ".join([
                str(node.get("node_name") or ""),
                str(node.get("learning_objective") or ""),
                *[
                    str(value)
                    for value in node.get("key_points") or []
                ],
            ])
        )
    )
    selected: list[dict[str, Any]] = []
    source_parts: list[str] = []
    for evidence in course_data.get("evidence_catalog") or []:
        evidence_id = str(evidence.get("evidence_id") or "")
        source = str(evidence.get("source_text") or "")
        overlaps = node_terms.intersection(_tokens(source))
        if evidence_id not in evidence_ids and not overlaps:
            continue
        selected.append({
            "evidence_id": evidence_id,
            "asset_id": str(evidence.get("asset_id") or ""),
            "content_hash": str(evidence.get("content_hash") or ""),
            "locator": deepcopy(evidence.get("locator") or {}),
            "confidence": str(evidence.get("confidence") or "medium"),
        })
        source_parts.append(source)
    node_id = str(node.get("node_id") or "")
    course_document = course_data.get("course_document") or {}
    for block in course_document.get("blocks") or []:
        if str(block.get("section_id") or "") != node_id:
            continue
        payload = block.get("payload") or {}
        source = " ".join(
            str(payload.get(field) or "").strip()
            for field in ("title", "markdown", "content", "text")
            if str(payload.get(field) or "").strip()
        )
        if not source:
            continue
        selected.append({
            "source_type": "course_document",
            "block_id": str(block.get("block_id") or ""),
            "node_id": node_id,
            "content_hash": stable_hash(source, prefix="src_"),
            "confidence": "high",
        })
        source_parts.append(source)
    node_content = str(node.get("node_content") or "").strip()
    if node_content:
        selected.append({
            "source_type": "course_node",
            "node_id": str(node.get("node_id") or ""),
            "content_hash": stable_hash(node_content, prefix="src_"),
            "confidence": "high",
        })
        source_parts.insert(0, node_content)
    return selected, " ".join(source_parts)


def _answer_modalities(
    profile: dict[str, Any],
    objective: str,
    skills: list[str],
) -> list[str]:
    family = str((profile.get("discipline") or {}).get("family") or "")
    text = " ".join([objective, *skills]).lower()
    if family == "programming_engineering":
        return ["code", "execution_trace", "test_evidence"]
    if family == "language_learning":
        return ["contextual_language_response"]
    if family == "humanities_social":
        return ["claim_evidence_reasoning"]
    if family == "business_career":
        return ["decision_with_tradeoffs"]
    if "实验" in text or "变量" in text:
        return ["experiment_plan"]
    if family == "math_formal":
        if any(marker in text for marker in ("推导", "证明", "形式化")):
            return ["symbolic_reasoning"]
        return ["numeric_with_work", "symbolic_reasoning"]
    if family in {"natural_science", "life_medical"}:
        return ["model_explanation", "numeric_with_unit"]
    return ["structured_response"]


def _preferred_archetypes(
    profile: dict[str, Any],
    objective: str,
    skills: list[str],
    modalities: list[str],
) -> list[str]:
    family = str((profile.get("discipline") or {}).get("family") or "")
    text = " ".join([objective, *skills]).lower()
    if any(
        marker in text
        for marker in ("跨章节", "综合", "设计作品", "综合任务")
    ):
        return ["integrated_performance"]
    if "experiment_plan" in modalities:
        return ["controlled_experiment"]
    if family == "programming_engineering":
        return ["code_execution"]
    if family == "language_learning":
        return ["language_production"]
    if family == "humanities_social":
        return ["evidence_argument"]
    if family == "business_career":
        return ["constrained_decision"]
    if "symbolic_reasoning" in modalities and any(
        marker in text for marker in ("推导", "证明", "形式化", "极限")
    ):
        return ["symbolic_derivation"]
    if "numeric_with_unit" in modalities or "numeric_with_work" in modalities:
        return ["numeric_calculation"]
    if any(marker in text for marker in ("图表", "数据", "趋势", "模型")):
        return ["data_interpretation"]
    return ["concept_classification"]


def _misconceptions(
    objective: str,
    knowledge: list[str],
) -> list[str]:
    focus = "、".join(knowledge[:2]) or objective
    return [
        f"只复述“{focus}”而未满足题目条件",
        "忽略边界条件或把相关关系误判为因果关系",
    ]


def _observable_evidence(
    skills: list[str],
    modalities: list[str],
) -> list[str]:
    return _unique([
        *skills,
        *[
            f"提交可检查的{modality}"
            for modality in modalities
        ],
        "说明所用依据并执行结果检查",
    ])


def _strip_number(value: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", value).strip()


def _tokens(value: str) -> list[str]:
    english = re.findall(r"[a-z][a-z0-9_+#-]{1,30}", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,12}", value)
    grams = [
        group[index:index + width]
        for group in chinese
        for width in (2, 3, 4)
        for index in range(max(0, len(group) - width + 1))
    ]
    return _unique([*english, *chinese, *grams])


def _unique(values: Iterable[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    )


__all__ = [
    "ASSESSMENT_ARCHETYPES",
    "ASSESSMENT_OBJECTIVE_SCHEMA",
    "COURSE_ASSESSMENT_PROFILE_SCHEMA",
    "PUBLIC_QUESTION_FIELDS",
    "QUESTION_SPEC_V2_SCHEMA",
    "SOLUTION_ENVELOPE_SCHEMA",
    "compile_assessment_objectives",
    "compile_course_assessment_profile",
    "project_public_question",
    "select_assessment_archetype",
]
