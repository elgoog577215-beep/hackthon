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
from assessment_semantics import semantics_for_question_type


ASSESSMENT_BLUEPRINT_SCHEMA = "course_assessment_blueprint_v2"
REFERENCE_PACKAGE_SCHEMA = "question_reference_package_v2"
INPUT_CONTRACT_SCHEMA = "input_contract_v2"

PRACTICE_LEVELS = (
    "concept_check",
    "objective_practice",
    "mastery_check",
)

# 唯一真源见 assessment_input_modes。此处仅重导出——`assessment_quality`
# 一直是 `from assessment_blueprint import INPUT_MODES`，保留这个名字不打断它。
from assessment_input_modes import INPUT_MODES  # noqa: F401


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
        _slot("symbolic_derivation", "structured_fields", "expert_rubric_validator", "symbolic_derivation"),
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
            # H2：按知识点类型选作答形态。没有知识库时回落到默认形态，
            # 产出与改动前完全一致。
            recipe["question_form"] = resolve_slot_question_form(
                course_data,
                node_id=node_id,
                input_mode=str(recipe.get("input_mode") or ""),
                practice_level=practice_level,
            )
            if (
                recipe["question_form"] == "fill_blank"
                and recipe.get("input_mode") != "short_text"
            ):
                recipe.update(_FILL_BLANK_SLOT_OVERRIDES)
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
                "difficulty_contract": _slot_difficulty_contract(
                    objective.get("difficulty_contract") or {},
                    practice_level,
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
                "question_type_semantics_id": (
                    semantics_for_question_type(
                        str(recipe.get("question_type") or "")
                    ).get("registry_id")
                ),
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



# 输入模式 -> 该模式能承载的作答形态。H2 只在这个范围内选型：
# 学科族配方决定 input_mode 与验证器（已验收链路），H2 只在它允许的形态里挑。
_FORMS_BY_INPUT_MODE: dict[str, tuple[str, ...]] = {
    # choice 槽位可以被 H2 换成填空：8 个学科族的三个槽位里没有任何 short_text
    # 槽位，不允许换的话填空永远选不上。换的是 input_mode 与验证器，不动三槽位
    # 结构本身（保持每节 3 题，不抬高生成成本）。
    "choice": (
        "single_choice", "multiple_choice", "true_false", "fill_blank",
    ),
    "short_text": ("short_answer", "fill_blank"),
}

# 被 H2 换成填空时，槽位要一起换掉输入模式与验证器——只改形态不改验证器会让
# 填空题拿着选择题的 exact_validator 去比对整段文本。
_FILL_BLANK_SLOT_OVERRIDES = {
    "input_mode": "short_text",
    "validation_mode": "exact_validator",
}
_DEFAULT_FORM_BY_INPUT_MODE: dict[str, str] = {
    "choice": "single_choice",
    "short_text": "short_answer",
    "numeric_unit": "numeric",
    "rich_text": "essay",
    "structured_fields": "structured",
    "code": "coding",
}


def _node_of(
    course_data: dict[str, Any],
    node_id: str,
) -> dict[str, Any] | None:
    for node in (course_data or {}).get("nodes") or []:
        if isinstance(node, dict) and str(node.get("node_id") or "") == str(node_id):
            return node
    return None


def resolve_slot_question_form(
    course_data: dict[str, Any],
    *,
    node_id: str,
    input_mode: str,
    practice_level: str,
) -> str:
    """按知识点类型给这个槽位选一个作答形态（H2）。

    必须是 `(course_data, node_id, input_mode, practice_level)` 的**纯函数**：
    `blueprint_revision_id` 是对整个 blueprint 的 stable_hash，选型只要带一点
    不确定性，blueprint 就不再可复现。

    拿不到课程知识库、拿不到知识点类型、或该输入模式没有可选形态时，一律回落到
    默认形态——**这是既有课程与既有测试行为不变的保证**：绝大多数既有测试不提供
    知识库，走的就是这条回落路径。
    """
    default_form = _DEFAULT_FORM_BY_INPUT_MODE.get(
        str(input_mode or ""), "unspecified",
    )
    candidates = _FORMS_BY_INPUT_MODE.get(str(input_mode or ""))
    if not candidates:
        return default_form

    # 小节可以显式指定作答形态，优先于 H2 推荐。
    #
    # 需要这条是因为 H2 的推荐表里**没有任何知识点类型把 multiple_choice 排在
    # 第一位**（rule 排第三，其余更靠后），于是纯按推荐顺序永远选不出多选。
    # 与其为了凑出多选去改 H2 的教研判断表（那是把工具改成迎合结论），
    # 不如给一个显式入口：教师/教研明确要多选时直接声明。
    requested = str(
        (_node_of(course_data, node_id) or {}).get("preferred_question_form")
        or ""
    )
    if requested in candidates:
        return requested

    # 局部导入：question_knowledge_binding 只读知识库，但 blueprint 是被广泛
    # import 的底层模块，顶层引入会把依赖方向倒过来。
    from question_form_matching import recommended_forms
    from question_knowledge_binding import (
        course_knowledge_base_of,
        resolve_node_knowledge_binding,
    )

    knowledge_base = course_knowledge_base_of(course_data)
    if not knowledge_base:
        return default_form
    binding = resolve_node_knowledge_binding(course_data, node_id)
    if not binding.get("resolved"):
        return default_form
    owned = set(binding.get("knowledge_ids") or [])
    knowledge_types = [
        str(point.get("knowledge_type") or "")
        for point in knowledge_base.get("knowledge_points") or []
        if isinstance(point, dict)
        and str(point.get("knowledge_id") or "") in owned
        and str(point.get("knowledge_type") or "")
    ]
    if not knowledge_types:
        return default_form

    # 同一小节的三个练习层级用不同的知识点做主依据，避免三个槽位塌缩成同一
    # 形态（例如整节都是判断题）。取模而不是随机——必须可复现。
    level_index = (
        PRACTICE_LEVELS.index(practice_level)
        if practice_level in PRACTICE_LEVELS
        else 0
    )
    primary_type = sorted(set(knowledge_types))[
        level_index % len(set(knowledge_types))
    ]
    # 按 H2 的**推荐顺序**挑，而不是按本模块的候选顺序。
    #
    # recommended_forms 是有序的（definition 优先 single_choice，condition 优先
    # true_false，representation 优先 fill_blank）。若按本地候选顺序遍历，
    # single_choice 排在最前且对几乎所有类型都判 match，H2 就永远选不出新题型——
    # 我第一版正是这样，实测五种知识点类型全部得到 single_choice。
    allowed = set(candidates)
    for candidate in recommended_forms(primary_type):
        if candidate in allowed:
            return candidate
    return default_form


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
        # 按槽位声明的作答形态产出 selection。
        #
        # 改动前这里恒写 {"multiple": False}，多选与判断在合同层根本表达不出来
        # （H1a 的现状）。单选分支必须与改动前**逐字节相同**——blueprint_revision_id
        # 是对 blueprint 的 stable_hash，多一个键就会让所有既有课程的修订 ID 漂移。
        question_form = str(slot.get("question_form") or "")
        if question_form == "multiple_choice":
            contract["selection"] = {
                "multiple": True,
                # 部分给分默认关闭，口径见 question_choice_grading。
                "partial_credit": False,
            }
        elif question_form == "true_false":
            contract["selection"] = {"multiple": False, "true_false": True}
        else:
            contract["selection"] = {"multiple": False}
    elif mode == "short_text" and str(
        slot.get("question_form") or ""
    ) == "fill_blank":
        # 填空不新增 INPUT_MODES 成员：全仓有三份 INPUT_MODES 定义与十余处
        # input_mode 分支，新增成员的影响面远大于收益。question_forms 已能从
        # 「short_text + blanks」判出 fill_blank，走这条路。
        contract["blanks"] = []
        # 仍给一个作答字段：填空的空位在题面里，但作答载体要有地方落。
        contract["fields"] = [
            _field("blanks", "structured", "各空作答", True),
        ]
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


def _slot_difficulty_contract(
    course_contract: dict[str, Any],
    practice_level: str,
) -> dict[str, Any]:
    """Translate one course target into a three-step assessment progression."""
    course_target = str(
        course_contract.get("target_level") or "intermediate"
    )
    result = {
        "contract_version": str(
            course_contract.get("contract_version")
            or "course_difficulty_v1"
        ),
        "course_target_level": course_target,
        "anti_patterns": deepcopy(
            course_contract.get("anti_patterns") or []
        ),
    }
    if practice_level == "concept_check":
        result.update({
            "target_level": "foundational",
            "node_role": "concept_discrimination",
            "cognitive_demand": "single_decisive_discrimination",
            "expected_reasoning_steps": [1, 2],
            "learner_action_limit": 1,
            "subject_task": "识别一个决定性特征并排除一个典型误解",
            "required_evidence": [
                "识别一个决定性特征",
                "排除一个典型误解",
            ],
            "exercise_contract": {
                "autonomy": 1,
                "reasoning_steps": [1, 2],
                "transfer_distance": 1,
            },
        })
    elif practice_level == "mastery_check":
        result.update({
            "target_level": course_target,
            "node_role": "bounded_transfer",
            "cognitive_demand": "bounded_transfer_and_check",
            "expected_reasoning_steps": [4, 6],
            "learner_action_limit": 3,
            "subject_task": "在一个有界变式中选择方法、说明条件并检查结果",
            "required_evidence": [
                "完成一个有界变式",
                "说明条件与关键步骤",
                "完成一次结果检查",
            ],
            "exercise_contract": {
                "autonomy": 3,
                "reasoning_steps": [4, 6],
                "transfer_distance": 3,
            },
        })
    else:
        result.update({
            "target_level": course_target,
            "node_role": "bounded_application",
            "cognitive_demand": "single_application_and_check",
            "expected_reasoning_steps": [2, 4],
            "learner_action_limit": 2,
            "subject_task": "在一个自足实例中完成必要应用并检查结果",
            "required_evidence": [
                "完成一个典型应用",
                "写出关键步骤",
                "完成一次结果检查",
            ],
            "exercise_contract": {
                "autonomy": 2,
                "reasoning_steps": [2, 4],
                "transfer_distance": 2,
            },
        })
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
