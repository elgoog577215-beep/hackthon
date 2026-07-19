"""Universal archetype-driven question contract generation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from assessment_contracts import (
    ASSESSMENT_ARCHETYPES,
    QUESTION_SPEC_V2_SCHEMA,
    SOLUTION_ENVELOPE_SCHEMA,
    compile_assessment_objectives,
    compile_course_assessment_profile,
    select_assessment_archetype,
)
from assessment_blueprint import input_contract_for_slot
from assessment_validators import validate_solution_envelope
from course_versioning import stable_hash


def generate_universal_question_contract(
    course_data: dict[str, Any],
    node: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    objective: dict[str, Any] | None = None,
    practice_level: str,
    variant_index: int,
    independent_solution: Any = None,
    slot: dict[str, Any] | None = None,
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a grounded candidate through a domain-neutral archetype."""
    resolved_profile = profile or compile_course_assessment_profile(
        course_data
    )
    resolved_objective = objective or next(
        (
            item
            for item in compile_assessment_objectives(
                course_data,
                resolved_profile,
            )
            if item.get("node_id") == node.get("node_id")
        ),
        None,
    )
    if not resolved_objective:
        raise ValueError("assessment objective is required")
    if (
        slot
        and str(slot.get("archetype_id") or "")
        in ASSESSMENT_ARCHETYPES
    ):
        archetype = deepcopy(
            ASSESSMENT_ARCHETYPES[str(slot["archetype_id"])]
        )
        archetype.update({
            "archetype_id": str(slot["archetype_id"]),
            "selection_method": "course_assessment_blueprint_v2",
            "selection_confidence": 1.0,
            "objective_id": resolved_objective.get("objective_id"),
        })
    else:
        archetype = select_assessment_archetype(
            resolved_objective,
            resolved_profile,
        )
    content = _question_content(
        resolved_objective,
        archetype,
        practice_level,
        variant_index,
        slot=slot,
        references=references or [],
    )
    solution_body = _solution_body(
        resolved_objective,
        archetype,
        content,
        validation_mode=(
            str((slot or {}).get("validation_mode") or "")
            or None
        ),
    )
    solution_revision_id = stable_hash(
        {
            "course_id": course_data.get("course_id"),
            "node_id": node.get("node_id"),
            "practice_level": practice_level,
            "variant_index": variant_index,
            **solution_body,
        },
        prefix="sol_",
    )
    solution_envelope = {
        "schema_version": SOLUTION_ENVELOPE_SCHEMA,
        "solution_revision_id": solution_revision_id,
        **solution_body,
    }
    risk_level = str(
        resolved_objective.get("risk_level") or "teacher_review"
    )
    question_spec = {
        "schema_version": QUESTION_SPEC_V2_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "node_id": str(node.get("node_id") or ""),
        "objective_id": resolved_objective.get("objective_id"),
        "profile_revision_id": resolved_profile.get(
            "profile_revision_id"
        ),
        "archetype_id": archetype["archetype_id"],
        "target": {
            "objective": resolved_objective.get("objective"),
            "knowledge": deepcopy(
                resolved_objective.get("knowledge") or []
            ),
            "skills": deepcopy(
                resolved_objective.get("skills") or []
            ),
            "misconceptions": deepcopy(
                resolved_objective.get("misconceptions") or []
            ),
            "observable_evidence": deepcopy(
                resolved_objective.get("observable_evidence") or []
            ),
        },
        "stimulus": deepcopy(content["stimulus"]),
        "task": deepcopy(content["task"]),
        "constraints": deepcopy(content["constraints"]),
        "response_contract": deepcopy(content["response_contract"]),
        "input_contract": deepcopy(content["input_contract"]),
        "provenance": {
            "course_id": str(course_data.get("course_id") or ""),
            "source_priority": (
                "course_materials"
                if resolved_objective.get("source_refs")
                else "general_model_knowledge"
            ),
            "source_refs": deepcopy(
                resolved_objective.get("source_refs") or []
            ),
        },
        "difficulty_contract": deepcopy(
            resolved_objective.get("difficulty_contract") or {}
        ),
        "risk_contract": {
            "risk_level": risk_level,
            "requires_teacher_review": risk_level != "low",
            "source_sufficiency": resolved_objective.get(
                "source_sufficiency"
            ),
        },
        "practice_level": practice_level,
        "solution_revision_id": solution_revision_id,
    }
    validation = validate_solution_envelope(
        question_spec,
        solution_envelope,
        independent_solution=independent_solution,
    )
    prompt = "\n".join([
        str(content["stimulus"]["rendered_text"]),
        str(content["task"]["rendered_text"]),
    ]).strip()
    result = {
        "schema_version": "universal_question_contract_v1",
        "prompt": prompt,
        "deliverable": content["task"]["deliverable"],
        "input_materials": [
            str(content["stimulus"]["rendered_text"])
        ],
        "constraints": deepcopy(content["constraints"]),
        "result_checks": deepcopy(content["result_checks"]),
        "question_type": _question_type(archetype["archetype_id"]),
        "input_contract": deepcopy(content["input_contract"]),
        "estimated_minutes": _estimated_minutes(practice_level),
        "question_spec": question_spec,
        "solution_envelope": solution_envelope,
        "solution_validation": validation,
        "risk_flags": [
            issue["code"]
            for issue in validation.get("issues") or []
        ],
        "review_required": not validation.get(
            "auto_publish_eligible",
            False,
        ),
    }
    if slot and slot.get("question_type"):
        result["question_type"] = str(slot["question_type"])
    return result


def _question_content(
    objective: dict[str, Any],
    archetype: dict[str, Any],
    practice_level: str,
    variant_index: int,
    *,
    slot: dict[str, Any] | None = None,
    references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    objective_text = str(objective.get("objective") or "")
    source = str(objective.get("source_excerpt") or "").strip()
    if not source:
        source = (
            f"当前课程目标为“{objective_text}”。"
            "课程尚未提供足够正文，以下内容只能作为待教师完善的候选。"
        )
    source_limit = (
        2400
        if archetype["archetype_id"] in {
            "evidence_argument",
            "data_interpretation",
        }
        else 800
    )
    source = source[:source_limit]
    source_label = (
        "给定课程材料"
        if objective.get("source_sufficiency") == "sufficient"
        else "低置信课程背景"
    )
    action, deliverable = _task_for_archetype(
        archetype["archetype_id"],
        objective,
        practice_level,
        variant_index,
    )
    family = str((slot or {}).get("discipline_family") or "")
    input_contract = deepcopy(
        (slot or {}).get("input_contract")
        or input_contract_for_slot(
            {
                "input_mode": (
                    (slot or {}).get("input_mode")
                    or "rich_text"
                )
            },
            family=family or "general",
        )
    )
    return {
        "stimulus": {
            "kind": archetype["archetype_id"],
            "data": {
                "source_label": source_label,
                "source_excerpt": source,
            },
            "rendered_text": f"{source_label}：\n{source}",
        },
        "task": {
            "action": archetype["task_actions"][0],
            "rendered_text": action,
            "deliverable": deliverable,
        },
        "constraints": [
            "只能使用题目材料和当前课程已声明的概念",
            "每个结论必须给出可检查的依据",
            "必须完成结果或边界检查",
        ],
        "response_contract": {
            "format": archetype["response_format"],
            "required_parts": _required_parts(
                archetype["archetype_id"]
            ),
        },
        "input_contract": input_contract,
        "reference_patterns": [
            deepcopy(reference.get("pattern") or {})
            for reference in (references or [])[:3]
        ],
        "result_checks": [
            "最终产物回应全部任务要求",
            "关键判断能够定位到材料、规则或计算步骤",
            "结论没有超出给定条件",
        ],
    }


def _solution_body(
    objective: dict[str, Any],
    archetype: dict[str, Any],
    content: dict[str, Any],
    *,
    validation_mode: str | None = None,
) -> dict[str, Any]:
    archetype_id = archetype["archetype_id"]
    resolved_validation_mode = (
        validation_mode
        or archetype["eligible_validation_modes"][0]
    )
    rubric = _rubric(archetype_id, objective)
    canonical = {
        "objective": objective.get("objective"),
        "required_evidence": deepcopy(
            objective.get("observable_evidence") or []
        ),
        "required_parts": deepcopy(
            content["response_contract"]["required_parts"]
        ),
    }
    return {
        "validation_mode": resolved_validation_mode,
        "canonical_answer": canonical,
        "acceptable_answers": [],
        "rubric": rubric,
        "validator_config": {
            "pass_score": 70,
            "confidence_threshold": 0.85,
        },
        "misconception_rules": deepcopy(
            objective.get("misconceptions") or []
        ),
        "solution_graph": {
            "schema_version": "solution_graph_v1",
            "steps": [
                {
                    "step_id": "orient",
                    "action": "定位任务目标、材料和限制条件",
                    "check": "所有输入均能在题面中定位",
                },
                {
                    "step_id": "execute",
                    "action": (
                        f"按“{archetype['title']}”原型形成规定产物"
                    ),
                    "check": rubric[0],
                },
                {
                    "step_id": "verify",
                    "action": "逐项执行结果、边界和依据检查",
                    "check": rubric[-1],
                },
            ],
        },
    }


def _task_for_archetype(
    archetype_id: str,
    objective: dict[str, Any],
    practice_level: str,
    variant_index: int,
) -> tuple[str, str]:
    objective_text = str(objective.get("objective") or "")
    level_instruction = {
        "concept_check": "先完成核心概念或条件辨析",
        "objective_practice": "在给定材料中完成完整应用",
        "mastery_check": "独立完成并提供自检证据",
    }.get(practice_level, "完成并检查")
    tasks = {
        "concept_classification": (
            f"{level_instruction}：围绕“{objective_text}”区分适用与不适用条件，并解释边界。",
            "分类结果、判断依据和反例",
        ),
        "numeric_calculation": (
            f"{level_instruction}：围绕“{objective_text}”整理已知量、计算并核对单位。",
            "计算过程、结果和单位检查",
        ),
        "symbolic_derivation": (
            f"{level_instruction}：围绕“{objective_text}”写出前提、推导步骤和结论检查。",
            "形式化推导及条件检查",
        ),
        "data_interpretation": (
            f"{level_instruction}：围绕“{objective_text}”读取数据、比较关系并解释限制。",
            "数据结论、证据和解释",
        ),
        "controlled_experiment": (
            f"{level_instruction}：围绕“{objective_text}”设计可执行实验并分析误差。",
            "假设、变量、步骤、记录表和误差分析",
        ),
        "code_execution": (
            f"{level_instruction}：围绕“{objective_text}”提交实现或跟踪结果、测试和调试依据。",
            "代码或执行轨迹、测试结果和检查说明",
        ),
        "evidence_argument": (
            f"{level_instruction}：围绕“{objective_text}”提出明确论点，至少引用两处材料并解释证据关系。",
            "论点、两处材料证据、推理链和边界说明",
        ),
        "language_production": (
            f"{level_instruction}：围绕“{objective_text}”根据受众、目的和语域完成表达。",
            "情境化语言产物和表达选择说明",
        ),
        "constrained_decision": (
            f"{level_instruction}：围绕“{objective_text}”比较方案，在约束下决策并说明风险。",
            "方案比较、最终决策、权衡和风险",
        ),
        "integrated_performance": (
            f"{level_instruction}：围绕“{objective_text}”整合多个知识点形成完整产物并验证。",
            "综合产物、知识连接和验证记录",
        ),
    }
    task, deliverable = tasks[archetype_id]
    return (
        f"{task} 本题为第 {variant_index + 1} 个冻结变式。",
        deliverable,
    )


def _required_parts(archetype_id: str) -> list[str]:
    return {
        "concept_classification": [
            "classification",
            "criteria",
            "counterexample",
        ],
        "numeric_calculation": ["givens", "work", "answer", "unit_check"],
        "symbolic_derivation": [
            "premises",
            "derivation",
            "conclusion",
            "condition_check",
        ],
        "data_interpretation": ["claim", "data_evidence", "interpretation"],
        "controlled_experiment": [
            "hypothesis",
            "variables",
            "procedure",
            "measurement",
            "error_analysis",
        ],
        "code_execution": ["artifact", "tests", "trace", "result_check"],
        "evidence_argument": [
            "claim",
            "evidence",
            "reasoning",
            "qualification",
        ],
        "language_production": [
            "response",
            "audience_fit",
            "language_check",
        ],
        "constrained_decision": [
            "constraints",
            "comparison",
            "decision",
            "risk",
        ],
        "integrated_performance": [
            "deliverable",
            "knowledge_connections",
            "validation",
        ],
    }[archetype_id]


def _rubric(
    archetype_id: str,
    objective: dict[str, Any],
) -> list[str]:
    focus = str(objective.get("objective") or "")
    return [
        f"最终产物准确回应“{focus}”",
        "使用题面中可定位的材料、条件或数据",
        "关键过程完整且不存在跳步替代结论",
        "结果检查能够发现边界、单位或证据问题",
    ]


def _question_type(archetype_id: str) -> str:
    return {
        "code_execution": "implementation_task",
        "controlled_experiment": "scenario_deliverable",
        "integrated_performance": "performance_task",
        "language_production": "contextual_production",
        "evidence_argument": "source_analysis",
    }.get(archetype_id, "structured_response")


def _estimated_minutes(practice_level: str) -> int:
    return {
        "concept_check": 8,
        "objective_practice": 15,
        "mastery_check": 25,
    }.get(practice_level, 15)


__all__ = ["generate_universal_question_contract"]
