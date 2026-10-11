"""Private measurement design before wording; independent checks never see it."""

from copy import deepcopy
import json

from ai_base import AIProviderRequestError


def measurement_design_prompt(contexts: list[dict]) -> str:
    items = []
    for context in contexts:
        slot = context.get("assessment_slot") or {}
        items.append(
            {
                "slot_id": slot.get("slot_id"),
                "target": slot.get("knowledge")
                or (context.get("question_design_brief") or {}).get("primary_knowledge"),
                "slot": {
                    key: deepcopy(slot.get(key))
                    for key in (
                        "input_mode",
                        "question_form",
                        "validation_mode",
                        "language_contract",
                        "learning_scope",
                        "conditions",
                        "difficulty_contract",
                    )
                },
                "sources": context.get("content_evidence"),
                "previous_failure": context.get("previous_failure") or context.get("quality_report"),
                "diversity_constraints": context.get("diversity_constraints"),
            }
        )
    return (
        "先设计测量实验，不写教学题干。每个输入槽位只设计一个小型、条件自足的实例。"
        "先选一个典型错误规则，只改变主考规则的一方面，保留所有其他语义与同一输入。"
        "用该输入分别算出正确和错误规则下的具体结果；相同就主动换输入或观测量，直到不同。"
        "比较整数除法和浮点除法时必须选不能整除的整数，不能把9/3虚构成3.333。"
        "例如数值运算选能区分运算顺序的数据；控制流考执行顺序可直接询问下一动作；"
        "考条件求值可直接询问哪些条件实际被求值，不要用分支体输出代替条件是否求值。"
        "考跳转前后状态可在循环外声明变量并问退出时的值，错误规则仍须保留跳转退出行为。"
        "语法归属使用原始无花括号结构，不给它补花括号。仅使用本槽位语言版本和已学前置。"
        "所有代码运算都应有定义，避免使用除零等未定义行为来制造区别。"
        "public_material只含数据或代码，禁止含目标规则、答案提示、知识点标题、讲解。"
        "ask仅问一个明确观察结果，不告诉学生如何推理。options给互斥的实际结果，不用算式冒充数值，"
        "不使用同值不同写法，不编造错误数值的由来。correct_option_index是正确选项的从0开始的下标，"
        "正确选项文字必须与correct_prediction完全相同，随机安排其位置。"
        "trace提供简短可复核推导，留在私有计划中。"
        "代码必须是完整的带语言标记Markdown围栏；任务不再重复代码。只输出JSON："
        '{"plans":[{"slot_id":"原样复制", "plan":{'
        '"target_rule":"完整规则", "public_material":"最小材料", "ask":"具体问题",'
        '"incorrect_rule":"单一错误规则", "correct_prediction":"具体结果",'
        '"incorrect_prediction":"同输入不同结果", "trace":"简短推导", "options":["结果1","结果2"], "correct_option_index":0}}]}\n'
        + json.dumps(items, ensure_ascii=False)
    )


def attach_measurement_designs(contexts: list[dict], response: dict) -> list[dict]:
    entries = response.get("plans") if isinstance(response, dict) else None
    expected = {str(c["assessment_slot"]["slot_id"]) for c in contexts}
    plans = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            raise AIProviderRequestError("invalid_measurement_design_entry")
        key, plan = str(entry.get("slot_id") or ""), entry.get("plan")
        if key not in expected or key in plans or not isinstance(plan, dict):
            raise AIProviderRequestError("invalid_measurement_design_slot")
        required = (
            "target_rule",
            "public_material",
            "ask",
            "incorrect_rule",
            "correct_prediction",
            "incorrect_prediction",
            "trace",
        )
        if not all(isinstance(plan.get(k), str) and plan[k].strip() for k in required):
            raise AIProviderRequestError("invalid_measurement_design_fields")
        plans[key] = plan
    if plans.keys() != expected:
        raise AIProviderRequestError("invalid_measurement_design_missing_slot")
    return [
        {**deepcopy(c), "private_measurement_design": deepcopy(plans[str(c["assessment_slot"]["slot_id"])])}
        for c in contexts
    ]


def evidence_recovery_action(codes: list[str], *, validation_passed: bool) -> str:
    """Retry the responsible artifact, never a specific point or answer."""
    failures = set(codes) - {"INDEPENDENT_EVIDENCE_UNVERIFIED", "SEMANTIC_REVIEW_FAILED"}
    if not validation_passed or not failures:
        return "author"
    if failures <= {
        "TRACE_CONTROL_STRUCTURE_CHANGED",
        "COUNTERFACTUAL_INPUT_CHANGED",
        "OBSERVATION_PREDICTION_UNEVALUATED",
        "OBSERVATION_ANCHOR_MISSING",
        "OPTION_AUDIT_INCOMPLETE",
        "OBSERVATION_TARGET_CHANGED",
    }:
        return "review"
    if failures <= {
        "OPERATOR_FIXITY_CONTRADICTION",
        "EXPLANATION_ARITHMETIC_ERROR",
        "EXPLANATION_CONTRADICTION",
        "WORKED_SOLUTION_INCOMPLETE",
    }:
        return "solve"
    return "author"


def candidate_from_measurement_design(context: dict) -> dict | None:
    """Render supported plans losslessly; never infer an answer from prose."""
    slot = context.get("assessment_slot") or {}
    plan = context.get("private_measurement_design") or {}
    if slot.get("input_mode") != "choice" or slot.get("question_form", "single_choice") != "single_choice":
        return None
    options, index = plan.get("options"), plan.get("correct_option_index")
    if not (
        isinstance(options, list)
        and 2 <= len(options) <= 8
        and all(isinstance(v, str) and v.strip() for v in options)
        and len(set(options)) == len(options)
        and type(index) is int
        and 0 <= index < len(options)
        and options[index] == plan.get("correct_prediction")
    ):
        return None
    ask = plan["ask"]
    if len(ask.strip()) < 12:
        ask += "请选择唯一正确的一项。"
    return {
        "question_spec": {
            "stimulus": {"rendered_text": plan["public_material"]},
            "task": {"rendered_text": ask, "deliverable": "选项ID"},
            "constraints": [],
            "response_contract": {"format": "choice"},
            "options": [{"id": chr(65 + i), "text": text} for i, text in enumerate(options)],
            "solver_contract": {},
        },
        "solution": {
            "validation_mode": slot.get("validation_mode", "exact_validator"),
            "canonical_answer": chr(65 + index),
            "acceptable_answers": [],
            "rubric": [],
            "validator_config": {},
            "misconception_rules": [],
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [
                    {
                        "step_id": "step_1",
                        "action": plan["trace"],
                        "check": plan["correct_prediction"],
                    }
                ],
            },
            "measurement_plan": deepcopy(plan),
        },
    }
