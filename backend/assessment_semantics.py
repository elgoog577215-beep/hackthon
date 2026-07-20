"""Executable question semantics and answer-first design briefs.

This module deliberately contains no model calls.  It converts a blueprint
slot into an immutable authoring contract and performs the cheap, fail-closed
checks that must run before an independent solver is invoked.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from course_versioning import stable_hash


QUESTION_DESIGN_BRIEF_SCHEMA = "question_design_brief_v1"
SEMANTIC_PREFLIGHT_SCHEMA = "question_semantic_preflight_v1"

SEMANTIC_HARD_CODES = {
    "QUESTION_TYPE_SEMANTIC_MISMATCH",
    "MATERIAL_NOT_REQUIRED",
    "FALSE_ERROR_PREMISE",
    "PROMPT_SOLUTION_CONTRADICTION",
    "OBSERVABLE_RESULT_MISSING",
    "DISTRACTOR_NOT_SAME_QUESTION",
    "MATERIAL_BINDING_INVALID",
}

_CODE_FENCE_RE = re.compile(
    r"```(?:python|py|javascript|js|typescript|ts|java|cpp|c\+\+|c)\s*\n"
    r"(?P<body>[\s\S]*?)```",
    re.IGNORECASE,
)
_OUTPUT_ACTION_RE = re.compile(
    r"(输出|打印|返回值|异常|变量状态|对象身份|调用顺序|执行顺序|"
    r"最终值|运行结果|状态变化|predict\s+(?:the\s+)?output|"
    r"print(?:ed)?\s+output|what\s+(?:is|will be)\s+"
    r"(?:printed|returned)|trace)",
    re.IGNORECASE,
)
_CONCEPT_ONLY_RE = re.compile(
    r"(核心思想|主要作用|最佳体现|最能体现|概念|原则|优势|目的|"
    r"which\s+(?:statement|option).*(?:best|correct)|main\s+(?:idea|purpose))",
    re.IGNORECASE,
)
_ERROR_PREMISE_RE = re.compile(
    r"(找出|指出|定位|诊断|修复|问题所在|错误|缺陷|bug|debug|"
    r"locate\s+(?:the\s+)?(?:error|bug|defect)|"
    r"identify\s+(?:the\s+)?(?:error|bug|defect)|"
    r"fix\s+(?:the\s+)?(?:code|bug|defect)|repair)",
    re.IGNORECASE,
)
_NO_ERROR_RE = re.compile(
    r"(没有(?:明显|实际|真正)?(?:错误|缺陷|问题)|不存在(?:错误|缺陷|问题)|"
    r"代码(?:是|运行)?正确|轨迹正确|无需修复|no\s+(?:error|bug|defect)|"
    r"works?\s+as\s+intended|correct\s+as\s+written)",
    re.IGNORECASE,
)
_DEBUG_EVIDENCE_RE = re.compile(
    r"(第\s*\d+\s*行|line\s*\d+|位置|原因|根因|修复|改为|替换|"
    r"复验|重新运行|测试|预期结果|actual|expected)",
    re.IGNORECASE,
)
_IMPLEMENTATION_IO_RE = re.compile(
    r"(输入|输出|stdin|stdout|参数|返回|input|output|return)",
    re.IGNORECASE,
)


QUESTION_TYPE_SEMANTICS: dict[str, dict[str, Any]] = {
    "output_prediction": {
        "registry_id": "programming.output_prediction.v1",
        "semantic_obligations": [
            "Provide deterministic learner-visible code and inputs.",
            "Ask for an observable output, exception, state, identity, or call order.",
            "Derive the canonical answer by execution or explicit state tracing.",
        ],
        "required_material": "executable_or_traceable_code",
        "answer_derivation": "execution_or_state_trace",
        "max_effective_code_lines": 20,
    },
    "debugging_trace": {
        "registry_id": "programming.debugging_trace.v1",
        "semantic_obligations": [
            "Plant at least one reproducible defect.",
            "Require location, cause, repair, and verification evidence.",
            "Never claim that a correct trace contains an error.",
        ],
        "required_material": "defective_code_or_trace",
        "answer_derivation": "reproduce_localize_repair_retest",
        "max_effective_code_lines": 20,
    },
    "trace_verification": {
        "registry_id": "programming.trace_verification.v1",
        "semantic_obligations": [
            "Provide a trace and ask the learner to verify or falsify it.",
            "Do not presuppose that an error exists.",
        ],
        "required_material": "code_and_claimed_trace",
        "answer_derivation": "independent_trace_comparison",
        "max_effective_code_lines": 20,
    },
    "state_trace_transfer": {
        "registry_id": "programming.state_trace_transfer.v1",
        "semantic_obligations": [
            "Provide a new situation with observable state changes.",
            "Require concrete state evidence rather than a generic explanation.",
        ],
        "required_material": "new_scenario_code_or_state_table",
        "answer_derivation": "state_transition_trace",
        "max_effective_code_lines": 20,
    },
    "implementation_task": {
        "registry_id": "programming.implementation_task.v1",
        "semantic_obligations": [
            "Lock input/output before wording the task.",
            "Register hidden tests and verify canonical code in Runner.",
        ],
        "required_material": "io_contract",
        "answer_derivation": "runner_hidden_tests",
        "max_effective_code_lines": 20,
    },
    "selected_response": {
        "registry_id": "general.selected_response.v1",
        "semantic_obligations": [
            "All options answer the same question.",
            "Exactly one option satisfies the locked answer fact.",
        ],
        "answer_derivation": "single_fact_discrimination",
    },
    "numeric_response": {
        "registry_id": "math.numeric_response.v1",
        "semantic_obligations": [
            "Provide all numerical conditions and units.",
            "Derive the answer using the configured tolerance and unit rules.",
        ],
        "answer_derivation": "deterministic_calculation",
    },
    "symbolic_derivation": {
        "registry_id": "math.symbolic_derivation.v1",
        "semantic_obligations": [
            "State premises and the requested symbolic conclusion.",
            "Make each derivation step checkable.",
        ],
        "answer_derivation": "formal_derivation",
    },
    "scenario_deliverable": {
        "registry_id": "general.scenario_deliverable.v1",
        "semantic_obligations": [
            "Bind the response to scenario constraints and observable evidence.",
        ],
        "answer_derivation": "constraint_satisfaction",
    },
    "mechanism_evidence": {
        "registry_id": "life_science.mechanism_evidence.v1",
        "semantic_obligations": [
            "Require a mechanism claim and evidence that supports each causal step.",
        ],
        "answer_derivation": "mechanism_evidence_chain",
    },
    "case_analysis": {
        "registry_id": "life_science.case_analysis.v1",
        "semantic_obligations": [
            "Require case facts to be used in the conclusion and boundary analysis.",
        ],
        "answer_derivation": "case_evidence_reasoning",
    },
    "source_identification": {
        "registry_id": "humanities.source_identification.v1",
        "semantic_obligations": [
            "Require an identification grounded in a cited feature of the material.",
        ],
        "answer_derivation": "source_feature_matching",
    },
    "source_analysis": {
        "registry_id": "humanities.source_analysis.v1",
        "semantic_obligations": [
            "Bind each claim to material evidence and explain the relationship.",
        ],
        "answer_derivation": "claim_evidence_reasoning",
    },
    "comparative_argument": {
        "registry_id": "humanities.comparative_argument.v1",
        "semantic_obligations": [
            "Use a common comparison dimension and evidence for both sides.",
        ],
        "answer_derivation": "comparative_evidence_argument",
    },
    "language_comprehension": {
        "registry_id": "language.comprehension.v1",
        "semantic_obligations": [
            "Make the correct response derivable from the supplied language material.",
        ],
        "answer_derivation": "textual_comprehension",
    },
    "language_transformation": {
        "registry_id": "language.transformation.v1",
        "semantic_obligations": [
            "Lock meaning, audience, register, and transformation constraints.",
        ],
        "answer_derivation": "constrained_transformation",
    },
    "contextual_production": {
        "registry_id": "language.contextual_production.v1",
        "semantic_obligations": [
            "Specify audience, purpose, situation, and observable rubric criteria.",
        ],
        "answer_derivation": "rubric_constrained_production",
    },
    "data_judgement": {
        "registry_id": "business.data_judgement.v1",
        "semantic_obligations": [
            "Make the decision derivable from supplied data and one decision rule.",
        ],
        "answer_derivation": "data_rule_application",
    },
    "constrained_decision": {
        "registry_id": "business.constrained_decision.v1",
        "semantic_obligations": [
            "State the constraints, alternatives, decision rule, and trade-offs.",
        ],
        "answer_derivation": "constraint_optimization",
    },
    "case_strategy": {
        "registry_id": "business.case_strategy.v1",
        "semantic_obligations": [
            "Require the strategy to use case data, constraints, and risk controls.",
        ],
        "answer_derivation": "case_constrained_strategy",
    },
}

_DEFAULT_SEMANTICS = {
    "registry_id": "general.structured_application.v1",
    "semantic_obligations": [
        "Ask one primary question aligned to the locked objective.",
        "Make every required answer part observable and scorable.",
    ],
    "answer_derivation": "objective_evidence_alignment",
}


def semantics_for_question_type(question_type: str) -> dict[str, Any]:
    return deepcopy(
        QUESTION_TYPE_SEMANTICS.get(
            str(question_type or ""),
            _DEFAULT_SEMANTICS,
        )
    )


def compile_question_design_brief(
    *,
    objective: dict[str, Any],
    slot: dict[str, Any],
    reference_summary: dict[str, Any] | None = None,
    practice_level: str,
    variant_index: int,
) -> dict[str, Any]:
    """Freeze what the question must prove before any wording is generated."""
    question_type = str(slot.get("question_type") or "")
    semantics = semantics_for_question_type(question_type)
    references = deepcopy(reference_summary or {})
    knowledge = [
        str(value).strip()
        for value in objective.get("knowledge") or []
        if str(value).strip()
    ]
    skills = [
        str(value).strip()
        for value in objective.get("skills") or []
        if str(value).strip()
    ]
    misconceptions = [
        str(value).strip()
        for value in objective.get("misconceptions") or []
        if str(value).strip()
    ]
    observable = [
        str(value).strip()
        for value in objective.get("observable_evidence") or []
        if str(value).strip()
    ]
    brief = {
        "schema_version": QUESTION_DESIGN_BRIEF_SCHEMA,
        "objective_id": objective.get("objective_id"),
        "node_id": objective.get("node_id"),
        "slot_id": slot.get("slot_id"),
        "practice_level": practice_level,
        "variant_index": int(variant_index),
        "primary_knowledge": knowledge[0] if knowledge else str(
            objective.get("objective") or ""
        ),
        "primary_skill": skills[0] if skills else str(
            objective.get("objective") or ""
        ),
        "primary_misconception": (
            misconceptions[0] if misconceptions else ""
        ),
        "question_type": question_type,
        "question_type_semantics": semantics,
        "required_observable_evidence": (
            observable[:3]
            or semantics.get("semantic_obligations", [])[:2]
        ),
        "answer_fact_contract": {
            "source": "content_evidence_then_course_objective",
            "fact_basis": (
                references.get("content_fact_basis")
                or knowledge[:3]
                or [str(objective.get("objective") or "")]
            ),
            "derivation_mode": semantics.get("answer_derivation"),
            "locked_before_question_wording": True,
        },
        "validation_contract": {
            "validation_mode": slot.get("validation_mode"),
            "input_mode": slot.get("input_mode"),
            "input_contract": deepcopy(slot.get("input_contract") or {}),
        },
        "material_contract": {
            "required_material": semantics.get("required_material", "minimal"),
            "maximum_effective_code_lines": int(
                semantics.get("max_effective_code_lines") or 20
            ),
            "every_material_must_bind_to_answer_step": True,
            "remove_irrelevant_imports_functions_and_background": True,
        },
        "distractor_contract": {
            "basis": misconceptions[:4],
            "same_question_required": True,
        },
        "retrieval_contract": {
            "content_coverage": bool(references.get("content_covered")),
            "method_coverage": bool(references.get("method_covered")),
            "content_reference_count": int(
                references.get("content_reference_count") or 0
            ),
            "authoring_pattern_count": int(
                references.get("authoring_pattern_count") or 0
            ),
            "source_priority": deepcopy(
                references.get("source_priority") or []
            ),
        },
        "risk_level": slot.get("risk_level") or objective.get("risk_level"),
        "generation_sequence": [
            "lock_answer_fact",
            "lock_canonical_answer_and_validator",
            "select_minimum_material",
            "derive_distractors_from_misconceptions",
            "write_public_question_last",
        ],
    }
    brief["design_brief_revision_id"] = stable_hash(
        brief,
        prefix="qdbr_",
    )
    return brief


def evaluate_question_semantic_preflight(
    contract: dict[str, Any],
    *,
    design_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run inexpensive semantic gates before independent solving."""
    brief = deepcopy(design_brief or contract.get("design_brief") or {})
    spec = contract.get("question_spec") or {}
    solution = contract.get("solution_envelope") or {}
    question_type = str(
        brief.get("question_type")
        or contract.get("question_type")
        or ""
    )
    stimulus = str(
        (spec.get("stimulus") or {}).get("rendered_text") or ""
    ).strip()
    task = str((spec.get("task") or {}).get("rendered_text") or "").strip()
    prompt = "\n".join(value for value in (stimulus, task) if value)
    solution_text = _flatten_text({
        "canonical_answer": solution.get("canonical_answer"),
        "rubric": solution.get("rubric"),
        "solution_graph": solution.get("solution_graph"),
    })
    code_blocks = [
        match.group("body").strip()
        for match in _CODE_FENCE_RE.finditer(stimulus)
        if match.group("body").strip()
    ]
    effective_code_lines = sum(
        1
        for block in code_blocks
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    issues: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}

    if question_type == "output_prediction":
        has_observable = bool(_OUTPUT_ACTION_RE.search(task))
        has_code = bool(code_blocks)
        concept_only = bool(_CONCEPT_ONLY_RE.search(task)) and not has_observable
        checks.update({
            "learner_visible_code": has_code,
            "observable_result_requested": has_observable,
            "material_required_by_task": not concept_only,
        })
        if not has_code:
            issues.append(_issue(
                "OBSERVABLE_RESULT_MISSING",
                "critical",
                "输出预测题缺少可执行或可追踪的学习者可见代码。",
            ))
        if not has_observable:
            issues.append(_issue(
                "QUESTION_TYPE_SEMANTIC_MISMATCH",
                "critical",
                "题型标记为输出预测，但任务没有要求输出、异常、状态或调用顺序。",
            ))
        if concept_only:
            issues.append(_issue(
                "MATERIAL_NOT_REQUIRED",
                "critical",
                "任务只问概念，给出的代码不参与答案推导。",
            ))
    elif question_type == "debugging_trace":
        has_code = bool(code_blocks)
        asks_for_error = bool(_ERROR_PREMISE_RE.search(task))
        denies_error = bool(_NO_ERROR_RE.search(solution_text))
        debug_evidence_count = len(_DEBUG_EVIDENCE_RE.findall(solution_text))
        checks.update({
            "learner_visible_code": has_code,
            "error_localization_requested": asks_for_error,
            "solution_confirms_real_defect": not denies_error,
            "repair_evidence_present": debug_evidence_count >= 2,
        })
        if not has_code:
            issues.append(_issue(
                "MATERIAL_BINDING_INVALID",
                "critical",
                "调试题缺少可复现缺陷所对应的学习者可见代码。",
            ))
        if not asks_for_error:
            issues.append(_issue(
                "QUESTION_TYPE_SEMANTIC_MISMATCH",
                "critical",
                "题型标记为调试追踪，但任务没有要求定位、解释或修复缺陷。",
            ))
        if asks_for_error and denies_error:
            issues.append(_issue(
                "FALSE_ERROR_PREMISE",
                "critical",
                "题面预设存在错误，但标准答案说明代码或轨迹没有错误。",
            ))
        if not denies_error and debug_evidence_count < 2:
            issues.append(_issue(
                "MATERIAL_BINDING_INVALID",
                "critical",
                "调试题标准答案没有形成位置、原因、修复和复验的可检查闭环。",
            ))
    elif question_type == "trace_verification":
        checks["trace_claim_present"] = bool(
            code_blocks and _OUTPUT_ACTION_RE.search(prompt)
        )
        if not checks["trace_claim_present"]:
            issues.append(_issue(
                "OBSERVABLE_RESULT_MISSING",
                "critical",
                "轨迹核验题缺少可核验的代码、状态或执行结论。",
            ))
    elif question_type == "state_trace_transfer":
        has_observable = bool(_OUTPUT_ACTION_RE.search(prompt))
        checks["observable_state_transfer"] = has_observable
        if not has_observable:
            issues.append(_issue(
                "QUESTION_TYPE_SEMANTIC_MISMATCH",
                "critical",
                "状态迁移题没有要求可观察的状态变化或执行轨迹。",
            ))
    elif question_type == "implementation_task":
        has_io = bool(_IMPLEMENTATION_IO_RE.search(prompt))
        hidden_tests = solution.get("hidden_tests")
        checks.update({
            "io_contract_present": has_io,
            "hidden_tests_present": isinstance(hidden_tests, list)
            and bool(hidden_tests),
        })
        if not all(checks.values()):
            issues.append(_issue(
                "MATERIAL_BINDING_INVALID",
                "critical",
                "代码实现题必须先确定输入输出契约和隐藏测试。",
            ))

    options = spec.get("options") or []
    if isinstance(options, list) and len(options) >= 2:
        option_texts = [
            _flatten_text(option)
            for option in options
            if isinstance(option, dict)
        ]
        malformed = (
            len(option_texts) != len(options)
            or any(not text.strip() for text in option_texts)
        )
        checks["options_answer_same_question"] = not malformed
        if malformed:
            issues.append(_issue(
                "DISTRACTOR_NOT_SAME_QUESTION",
                "critical",
                "选择题存在空选项或无法回答同一设问的干扰项。",
            ))

    max_lines = int(
        (
            brief.get("material_contract") or {}
        ).get("maximum_effective_code_lines")
        or 20
    )
    checks["material_within_budget"] = (
        effective_code_lines <= max_lines
        if code_blocks
        else True
    )
    if code_blocks and effective_code_lines > max_lines:
        issues.append(_issue(
            "MATERIAL_BINDING_INVALID",
            "critical",
            "普通代码材料超过最小材料预算，需裁剪无关代码。",
            evidence={
                "effective_code_lines": effective_code_lines,
                "maximum_effective_code_lines": max_lines,
            },
        ))

    bindings = _material_bindings(
        stimulus=stimulus,
        solution=solution,
        code_blocks=code_blocks,
    )
    material_required = question_type in {
        "output_prediction",
        "debugging_trace",
        "trace_verification",
        "state_trace_transfer",
    }
    binding_valid = bool(bindings) if material_required else True
    checks["material_binding_valid"] = binding_valid
    if material_required and not binding_valid:
        issues.append(_issue(
            "MATERIAL_BINDING_INVALID",
            "critical",
            "题目材料没有绑定到任何标准答案步骤。",
        ))

    issues = _deduplicate_issues(issues)
    warnings = [
        issue for issue in issues
        if issue.get("severity") != "critical"
    ]
    passed = not any(
        issue.get("severity") == "critical"
        for issue in issues
    )
    report = {
        "schema_version": SEMANTIC_PREFLIGHT_SCHEMA,
        "question_type": question_type,
        "semantics_registry_id": (
            brief.get("question_type_semantics") or {}
        ).get("registry_id")
        or semantics_for_question_type(question_type).get("registry_id"),
        "passed": passed,
        "checks": checks,
        "issues": issues,
        "material_bindings": bindings,
        "requires_llm_review": bool(
            warnings
            or str((spec.get("risk_contract") or {}).get("risk_level"))
            not in {"", "low"}
            or not bool(
                (
                    brief.get("retrieval_contract") or {}
                ).get("content_coverage", True)
            )
            or not bool(
                (
                    brief.get("retrieval_contract") or {}
                ).get("method_coverage", True)
            )
        ),
    }
    report["preflight_revision_id"] = stable_hash(
        report,
        prefix="qspf_",
    )
    return report


def should_run_semantic_review(
    contract: dict[str, Any],
    preflight: dict[str, Any],
) -> bool:
    validation = contract.get("solution_validation") or {}
    spec = contract.get("question_spec") or {}
    if not preflight.get("passed"):
        return False
    if not validation.get("deterministic"):
        return True
    if preflight.get("requires_llm_review"):
        return True
    risk = spec.get("risk_contract") or {}
    return bool(
        str(risk.get("risk_level") or "low") != "low"
        or risk.get("requires_teacher_review")
    )


def _material_bindings(
    *,
    stimulus: str,
    solution: dict[str, Any],
    code_blocks: list[str],
) -> list[dict[str, Any]]:
    if not stimulus.strip():
        return []
    graph = solution.get("solution_graph") or {}
    steps = graph.get("steps") if isinstance(graph, dict) else graph
    step_ids = [
        str(step.get("step_id") or f"step_{index + 1}")
        for index, step in enumerate(steps or [])
        if isinstance(step, dict)
    ]
    if not step_ids:
        canonical = solution.get("canonical_answer")
        if canonical is None or canonical == "" or canonical == {}:
            return []
        step_ids = ["canonical_answer"]
    return [{
        "material_id": stable_hash(
            {
                "stimulus": stimulus,
                "code_blocks": len(code_blocks),
            },
            prefix="qmat_",
        ),
        "material_kind": "code" if code_blocks else "text",
        "answer_step_ids": step_ids[:6],
        "purpose": "answer_derivation",
    }]


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(
            f"{key} {_flatten_text(item)}"
            for key, item in value.items()
        )
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value or "")


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if evidence:
        result["evidence"] = deepcopy(evidence)
    return result


def _deduplicate_issues(
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for issue in issues:
        code = str(issue.get("code") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(issue)
    return result


__all__ = [
    "QUESTION_DESIGN_BRIEF_SCHEMA",
    "QUESTION_TYPE_SEMANTICS",
    "SEMANTIC_HARD_CODES",
    "SEMANTIC_PREFLIGHT_SCHEMA",
    "compile_question_design_brief",
    "evaluate_question_semantic_preflight",
    "semantics_for_question_type",
    "should_run_semantic_review",
]
