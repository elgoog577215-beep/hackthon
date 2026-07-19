"""Generation-time assessment blueprints.

The blueprint is deliberately compiled before any question text is generated.
It converts a course-level subject route into three observable assessment
slots per level-two node and makes response diversity a deterministic
constraint instead of a post-generation statistic.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from assessment_contracts import (
    ASSESSMENT_ARCHETYPES,
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from course_versioning import stable_hash


ASSESSMENT_BLUEPRINT_SCHEMA = "course_assessment_blueprint_v2"
REFERENCE_PACKAGE_SCHEMA = "question_reference_package_v1"
INPUT_CONTRACT_SCHEMA = "input_contract_v2"

PRACTICE_LEVELS = (
    "concept_check",
    "objective_practice",
    "mastery_check",
)

INPUT_MODES = {
    "choice",
    "numeric_unit",
    "code",
    "short_text",
    "rich_text",
    "structured_fields",
}


def _slot(
    archetype_id: str,
    input_mode: str,
    validation_mode: str,
    question_type: str,
) -> dict[str, str]:
    return {
        "archetype_id": archetype_id,
        "input_mode": input_mode,
        "validation_mode": validation_mode,
        "question_type": question_type,
    }


_FAMILY_SLOT_RECIPES: dict[str, tuple[dict[str, str], ...]] = {
    "general": (
        _slot("concept_classification", "choice", "exact_validator", "selected_response"),
        _slot("concept_classification", "structured_fields", "expert_rubric_validator", "structured_application"),
        _slot("constrained_decision", "rich_text", "expert_rubric_validator", "scenario_deliverable"),
    ),
    "math_formal": (
        _slot("concept_classification", "choice", "exact_validator", "selected_response"),
        _slot("numeric_calculation", "numeric_unit", "numeric_unit_validator", "numeric_response"),
        _slot("symbolic_derivation", "structured_fields", "symbolic_validator", "symbolic_derivation"),
    ),
    "programming_engineering": (
        _slot("code_execution", "choice", "state_trace_validator", "output_prediction"),
        _slot("code_execution", "structured_fields", "expert_rubric_validator", "debugging_trace"),
        _slot("code_execution", "code", "code_validator", "implementation_task"),
    ),
    "natural_science": (
        _slot("concept_classification", "choice", "exact_validator", "selected_response"),
        _slot("numeric_calculation", "numeric_unit", "numeric_unit_validator", "numeric_response"),
        _slot("controlled_experiment", "structured_fields", "expert_rubric_validator", "scenario_deliverable"),
    ),
    "life_medical": (
        _slot("concept_classification", "choice", "exact_validator", "selected_response"),
        _slot("evidence_argument", "structured_fields", "evidence_validator", "mechanism_evidence"),
        _slot("constrained_decision", "rich_text", "expert_rubric_validator", "case_analysis"),
    ),
    "humanities_social": (
        _slot("concept_classification", "choice", "exact_validator", "source_identification"),
        _slot("evidence_argument", "structured_fields", "evidence_validator", "source_analysis"),
        _slot("evidence_argument", "rich_text", "expert_rubric_validator", "comparative_argument"),
    ),
    "language_learning": (
        _slot("concept_classification", "choice", "exact_validator", "language_comprehension"),
        _slot("language_production", "structured_fields", "language_rubric_validator", "language_transformation"),
        _slot("language_production", "rich_text", "language_rubric_validator", "contextual_production"),
    ),
    "business_career": (
        _slot("data_interpretation", "choice", "exact_validator", "data_judgement"),
        _slot("constrained_decision", "structured_fields", "expert_rubric_validator", "constrained_decision"),
        _slot("constrained_decision", "rich_text", "expert_rubric_validator", "case_strategy"),
    ),
}


_PROGRAMMING_IMPLEMENTATION_SIGNALS = (
    "实现函数",
    "实现一个",
    "编写函数",
    "编写程序",
    "补全代码",
    "完成代码",
    "算法实现",
    "开发组件",
    "构建接口",
    "数据转换",
    "数据处理",
    "解析器",
    "序列化",
    "排序算法",
    "搜索算法",
    "implement a function",
    "write a function",
    "complete the code",
    "build an api",
)

_PROGRAMMING_CONCEPTUAL_SIGNALS = (
    "原理",
    "机制",
    "模型",
    "生命周期",
    "引用计数",
    "垃圾回收",
    "内存管理",
    "内存可见性",
    "gil",
    "mro",
    "元类",
    "描述符",
    "装饰器",
    "协程",
    "事件循环",
    "线程",
    "进程",
    "并发",
    "底层",
    "性能分析",
    "最佳实践",
    "工作流程",
    "type system",
    "object model",
    "garbage collection",
    "reference count",
    "event loop",
)


def _programming_mastery_recipe(
    objective: dict[str, Any],
    node: dict[str, Any],
    *,
    supported_runner_language: str,
) -> dict[str, str]:
    """Choose hidden-test code only when the objective is implementation-shaped.

    Every programming node already contains output prediction and debugging.
    Conceptual runtime chapters therefore gain more from a state-transfer task
    than from forcing an artificial stdin/stdout implementation into Runner.
    """
    identity_parts = [
        objective.get("objective"),
        *(objective.get("knowledge") or []),
        *(objective.get("skills") or []),
        node.get("node_name"),
        node.get("learning_objective"),
    ]
    identity_text = " ".join(
        str(value)
        for value in identity_parts
        if str(value or "").strip()
    ).casefold()
    implementation_hits = sum(
        signal in identity_text
        for signal in _PROGRAMMING_IMPLEMENTATION_SIGNALS
    )
    conceptual_hits = sum(
        signal in identity_text
        for signal in _PROGRAMMING_CONCEPTUAL_SIGNALS
    )
    if (
        supported_runner_language
        and implementation_hits > conceptual_hits
    ):
        recipe = _slot(
            "code_execution",
            "code",
            "code_validator",
            "implementation_task",
        )
        recipe["language"] = supported_runner_language
        recipe["selection_reason"] = (
            "explicit_implementation_objective"
        )
        return recipe
    recipe = _slot(
        "code_execution",
        "structured_fields",
        "expert_rubric_validator",
        "state_trace_transfer",
    )
    recipe["selection_reason"] = (
        "conceptual_or_non_runner_objective"
    )
    return recipe


def compile_course_assessment_blueprint(
    course_data: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    objectives: list[dict[str, Any]] | None = None,
    teacher_items: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Compile the immutable generation plan consumed by the orchestrator."""
    resolved_profile = profile or compile_course_assessment_profile(course_data)
    resolved_objectives = objectives or compile_assessment_objectives(
        course_data,
        resolved_profile,
    )
    family = str(
        (resolved_profile.get("discipline") or {}).get("family")
        or "general"
    )
    recipes = _FAMILY_SLOT_RECIPES.get(
        family,
        _FAMILY_SLOT_RECIPES["general"],
    )
    programming_languages = [
        str(value).casefold()
        for value in (
            resolved_profile.get("notation_and_language") or {}
        ).get("programming_languages")
        or []
    ]
    supported_runner_language = next(
        (
            language
            for language in ("python", "javascript")
            if language in programming_languages
        ),
        "python" if not programming_languages else "",
    )
    if (
        family == "programming_engineering"
        and not supported_runner_language
    ):
        recipes = (
            recipes[0],
            recipes[1],
            _slot(
                "code_execution",
                "structured_fields",
                "expert_rubric_validator",
                "state_trace_transfer",
            ),
        )
    teacher_distribution = _teacher_distribution(teacher_items)
    node_lookup = {
        str(node.get("node_id") or ""): node
        for node in course_data.get("nodes") or []
    }
    nodes: list[dict[str, Any]] = []
    all_slots: list[dict[str, Any]] = []
    for objective in resolved_objectives:
        node_id = str(objective.get("node_id") or "")
        slots: list[dict[str, Any]] = []
        for index, practice_level in enumerate(PRACTICE_LEVELS):
            recipe = deepcopy(recipes[index])
            if (
                family == "programming_engineering"
                and practice_level == "mastery_check"
            ):
                recipe = _programming_mastery_recipe(
                    objective,
                    node_lookup.get(node_id) or {},
                    supported_runner_language=(
                        supported_runner_language
                    ),
                )
            if (
                recipe.get("input_mode") == "code"
                and supported_runner_language
            ):
                recipe["language"] = supported_runner_language
            archetype = ASSESSMENT_ARCHETYPES[recipe["archetype_id"]]
            slot = {
                "slot_id": stable_hash(
                    {
                        "course_id": course_data.get("course_id"),
                        "node_id": node_id,
                        "practice_level": practice_level,
                        "objective_id": objective.get("objective_id"),
                    },
                    prefix="aslot_",
                ),
                "node_id": node_id,
                "discipline_family": family,
                "objective_id": objective.get("objective_id"),
                "practice_level": practice_level,
                **recipe,
                "response_format": archetype["response_format"],
                "difficulty_contract": deepcopy(
                    objective.get("difficulty_contract") or {}
                ),
                "knowledge": deepcopy(objective.get("knowledge") or []),
                "skills": deepcopy(objective.get("skills") or []),
                "misconceptions": deepcopy(
                    objective.get("misconceptions") or []
                ),
                "source_requirement": (
                    "teacher_or_course_reference"
                    if practice_level != "concept_check"
                    else "course_grounding"
                ),
                "risk_level": objective.get("risk_level") or "teacher_review",
                "input_contract": input_contract_for_slot(
                    recipe,
                    family=family,
                ),
            }
            slots.append(slot)
            all_slots.append(slot)
        nodes.append({
            "node_id": node_id,
            "objective_id": objective.get("objective_id"),
            "slots": slots,
            "diversity_checks": {
                "minimum_input_modes": 2,
                "maximum_rich_text_slots": 1,
                "passed": (
                    len({slot["input_mode"] for slot in slots}) >= 2
                    and sum(
                        slot["input_mode"] == "rich_text"
                        for slot in slots
                    ) <= 1
                ),
            },
        })
    distribution = _distribution(all_slots, "question_type")
    largest_share = (
        max(distribution.values()) / len(all_slots)
        if all_slots
        else 0.0
    )
    blueprint = {
        "schema_version": ASSESSMENT_BLUEPRINT_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "profile_revision_id": resolved_profile.get(
            "profile_revision_id"
        ),
        "discipline_family": family,
        "source_priority": [
            "teacher_question_bank",
            "course_materials",
            "trusted_web_reference",
            "general_model_knowledge",
        ],
        "nodes": nodes,
        "question_type_distribution": distribution,
        "input_mode_distribution": _distribution(
            all_slots,
            "input_mode",
        ),
        "diversity_policy": {
            "minimum_input_modes_per_node": 2,
            "maximum_rich_text_per_node": 1,
            "maximum_single_question_type_share": 0.6,
            "teacher_distribution_locked": bool(
                teacher_distribution.get("locked")
            ),
            "passed": bool(
                all(
                    (node.get("diversity_checks") or {}).get("passed")
                    for node in nodes
                )
                and (
                    largest_share <= 0.6
                    or bool(teacher_distribution.get("locked"))
                )
            ),
        },
        "teacher_distribution": teacher_distribution,
    }
    blueprint["blueprint_revision_id"] = stable_hash(
        blueprint,
        prefix="abp_",
    )
    return blueprint


def slot_for(
    blueprint: dict[str, Any],
    node_id: str,
    practice_level: str,
) -> dict[str, Any] | None:
    for node in blueprint.get("nodes") or []:
        if str(node.get("node_id") or "") != str(node_id):
            continue
        return next(
            (
                deepcopy(slot)
                for slot in node.get("slots") or []
                if str(slot.get("practice_level") or "")
                == str(practice_level)
            ),
            None,
        )
    return None


def input_contract_for_slot(
    slot: dict[str, Any],
    *,
    family: str,
) -> dict[str, Any]:
    mode = str(slot.get("input_mode") or "rich_text")
    if mode not in INPUT_MODES:
        mode = "rich_text"
    contract: dict[str, Any] = {
        "schema_version": INPUT_CONTRACT_SCHEMA,
        "mode": mode,
        "required": True,
        "fields": [],
        "supports_attachments": False,
    }
    if mode == "choice":
        contract["selection"] = {"multiple": False}
    elif mode == "numeric_unit":
        contract["fields"] = [
            _field("value", "number", "数值", True),
            _field("unit", "short_text", "单位", True),
            _field("work", "rich_text", "计算过程", True),
        ]
    elif mode == "code":
        contract.update({
            "language": (
                str(slot.get("language") or "")
                or (
                    "python"
                    if family == "programming_engineering"
                    else ""
                )
            ),
            "allowed_languages": ["python", "javascript"],
            "fields": [
                _field("code", "code", "代码", True),
                _field("test_evidence", "rich_text", "测试说明", True),
            ],
        })
    elif mode == "short_text":
        contract["fields"] = [
            _field("text", "short_text", "答案", True),
        ]
    elif mode == "rich_text":
        contract["fields"] = [
            _field("text", "rich_text", "完整作答", True),
        ]
    else:
        contract["fields"] = _structured_fields_for_family(family)
    return contract


def _structured_fields_for_family(
    family: str,
) -> list[dict[str, Any]]:
    fields = {
        "programming_engineering": [
            _field("trace", "rich_text", "状态或执行轨迹", True),
            _field("diagnosis", "rich_text", "问题定位", True),
            _field("result_check", "rich_text", "结果检查", True),
        ],
        "math_formal": [
            _field("premises", "rich_text", "前提与已知条件", True),
            _field("derivation", "rich_text", "推导过程", True),
            _field("conclusion", "short_text", "结论", True),
        ],
        "natural_science": [
            _field("hypothesis", "short_text", "假设", True),
            _field("variables", "rich_text", "变量与控制", True),
            _field("procedure", "rich_text", "步骤与测量", True),
            _field("error_analysis", "rich_text", "误差分析", True),
        ],
        "humanities_social": [
            _field("claim", "short_text", "观点", True),
            _field("evidence", "rich_text", "材料证据", True),
            _field("reasoning", "rich_text", "论证", True),
        ],
        "language_learning": [
            _field("response", "rich_text", "情境表达", True),
            _field("audience_fit", "short_text", "语域说明", True),
            _field("language_check", "rich_text", "语言检查", True),
        ],
        "business_career": [
            _field("constraints", "rich_text", "约束", True),
            _field("comparison", "rich_text", "方案比较", True),
            _field("decision", "short_text", "决策", True),
            _field("risk", "rich_text", "风险与权衡", True),
        ],
    }.get(family)
    return fields or [
        _field("answer", "rich_text", "作答", True),
        _field("evidence", "rich_text", "依据", True),
        _field("result_check", "rich_text", "结果检查", True),
    ]


def _field(
    field_id: str,
    kind: str,
    label: str,
    required: bool,
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "kind": kind,
        "label": label,
        "required": required,
    }


def _teacher_distribution(
    items: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    values = [
        str(item.get("question_type") or "")
        for item in items
        if str(item.get("question_type") or "")
    ]
    return {
        "locked": False,
        "question_type_distribution": _distribution(
            [{"question_type": value} for value in values],
            "question_type",
        ),
        "sample_count": len(values),
    }


def _distribution(
    items: Iterable[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = str(item.get(field) or "")
        if value:
            result[value] = result.get(value, 0) + 1
    return result


__all__ = [
    "ASSESSMENT_BLUEPRINT_SCHEMA",
    "INPUT_CONTRACT_SCHEMA",
    "INPUT_MODES",
    "PRACTICE_LEVELS",
    "REFERENCE_PACKAGE_SCHEMA",
    "compile_course_assessment_blueprint",
    "input_contract_for_slot",
    "slot_for",
]
