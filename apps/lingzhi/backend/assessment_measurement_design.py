"""Private measurement design before wording; independent checks never see it."""

from copy import deepcopy
import json
import re
import operator

from ai_base import AIProviderRequestError
from assessment_variants import ChoicePositionAllocator, variant_instruction


def measurement_strategy(slot: dict) -> dict:
    """Choose an observation from the rule's semantics, never its identity."""
    target = " ".join(slot.get("knowledge") or [])
    if re.search(r"目标类型.*反向|反向.*运算类型", target):
        return {
            "kind": "assignment_sequence",
            "instruction": "用一条double或float变量初始化、右侧为两个整数常量相除的语句，直接考查先计算右侧再转换存储的阶段顺序，不添加其他运算。",
        }
    if re.search(r"后续.*求值|求值.*后续", target):
        return {
            "kind": "condition_evaluation_trace",
            "instruction": "本槽位必须直接问哪些条件表达式被实际求值。选项列出被求值的条件集合/顺序。"
            "只用纯条件的简短if/else-if链，首个条件成立。分支体只用空块或普通赋值；"
            "禁止在分支中使用return、break、goto或其他提前退出，以免其他控制流掩盖本目标。"
            "不得问输出、最终变量、分支体赋值或打印内容。",
        }
    if "if" in target and "空语句" in target and "分号" in target:
        return {
            "kind": "uncontrolled_statement",
            "instruction": "本槽位给出if(cond);及随后改变一个变量的语句。必须选择让cond明确为假的输入，"
            "问随后赋值后该变量的值：正确规则仍执行赋值，错误地认为受if控制时会跳过赋值，二者不同。"
            "不能使用条件为真的例子，因为那时正确和错误理解都执行赋值；题干不要解释分号规则。"
            "代码只用整数变量声明、一个简单比较条件的if、分号和一条常量赋值，提供两个整数数值选项，"
            "不添加main、库或其他语句。",
        }
    if "else" in target and re.search(r"结合|归属|匹配|绑定", target):
        return {
            "kind": "syntactic_binding",
            "instruction": "本槽位直接询问指定else在语法上属于哪一个if。给一个简短的嵌套if示例，"
            "选项明确指向源代码里的条件表达式，不能只写内层/外层而不标识。不要改问最终变量或输出。",
        }
    if "continue" in target and re.search(r"更新|迭代|第三部分", target):
        return {
            "kind": "next_control_action",
            "instruction": "本槽位直接询问执行continue之后的动作顺序。使用非空for更新表达式，"
            "选项给出跳过余下循环体、更新、判断条件等顺序。不要计算多轮累加或用终止/死循环作为主要问题。",
        }
    if "break" in target and re.search(r"更新|迭代|第三部分", target):
        return {
            "kind": "exit_state",
            "instruction": "本槽位必须询问for头第三部分直接修改的那个变量本身在break退出后的值。"
            "例如第三部分是i++就只能问退出后的i，不能问循环体里复制i的c、sum、缓存值或计数器。"
            "变量在循环外声明，循环体在已知值触发break；正确值与错误地先更新一次再退出的值不同，"
            "不额外改变退出行为。",
        }
    if re.search(r"显式转换|强制转换", target) and re.search(r"作用|位置|操作数", target):
        return {
            "kind": "conversion_scope",
            "instruction": "本槽位直接询问显式转换作用于哪个子表达式，以及在除法前还是后。"
            "用含cast与除法的简短表达式，选项明确写作用范围和先后次序，不引入printf舍入。",
        }
    return {"kind": "direct_value", "instruction": "选择最小、直接且可区分完整目标的观测，不额外包装结果。"}


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
                "measurement_strategy": measurement_strategy(slot),
                "variant_role": slot.get("variant_role", "direct"),
                "variant_instruction": variant_instruction(slot, measurement_strategy(slot)["kind"]),
                "sources": context.get("content_evidence"),
                "previous_failure": context.get("previous_failure") or context.get("quality_report"),
                "diversity_constraints": context.get("diversity_constraints"),
            }
        )
    return (
        "输出最终定稿的测量设计JSON。每个输入槽位只保留一个小型、条件自足的实例。"
        "不要写讨论、犹豫、自我纠错或换例子的过程；先确定实例，所有字段对应同一份代码。"
        "每个槽位的measurement_strategy限定目标观测，variant_instruction指定本次变式结构，冲突时以后者为准。"
        "同一点的各变式不能仅换数字、变量名、选项顺序或同义问法；需改变代码结构、规则应用位置或需辨别的情形。"
        "trace只写不超过160字的可复核计算/执行摘要，再填写与该摘要一致的预测和选项。"
        "使用最少运算，直接询问目标决定的值或动作；不要额外加乘法、转型、计数器、打印格式或多变量组合。"
        "若目标不是输出格式，优先问变量的数学数值，避免引入浮点打印舍入这一额外考点。"
        "先选一个典型错误规则，只改变主考规则的一方面，保留所有其他语义与同一输入。"
        "用该输入分别算出正确和错误规则下的具体结果；相同就主动换输入或观测量，直到不同。"
        "比较整数除法和浮点除法时必须选不能整除的整数，不能把9/3虚构成3.333。"
        "完整目标中的限定也必须能被区分：例如向零截断与向下取整在正商时相同，须选负的非整数商。"
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
        '"target_rule":"完整规则", "incorrect_rule":"单一错误规则，最多60字",'
        '"public_material":"最小材料", "ask":"具体问题", "trace":"简短计算或执行摘要，最多160字",'
        '"correct_prediction":"具体结果", "incorrect_prediction":"同输入不同结果",'
        '"options":["结果1","结果2"], "correct_option_index":0}}]}\n' + json.dumps(items, ensure_ascii=False)
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
    bound = []
    for context in contexts:
        strategy = measurement_strategy(context["assessment_slot"])
        if context["assessment_slot"].get("variant_role", "direct") != "direct":
            bound.append({**deepcopy(context), "private_measurement_design": deepcopy(plans[str(context["assessment_slot"]["slot_id"])])})
            continue
        plan = synthesize_contrast_input(plans[str(context["assessment_slot"]["slot_id"])], strategy)
        plan = normalize_exit_observation(plan, strategy)
        plan = normalize_control_action(plan, strategy)
        plan = normalize_conversion_observation(plan, strategy)
        plan = normalize_assignment_observation(plan, strategy)
        bound.append({**deepcopy(context), "private_measurement_design": plan})
    return bound


def synthesize_contrast_input(plan: dict, strategy: dict) -> dict:
    """Construct a falsy witness for a bounded C fragment, not arbitrary code.

    Supports only small decimal int initializers, one scalar comparison and one
    literal assignment after if(...);. Unknown syntax is left to model design.
    No eval, compilation or execution occurs here. The original draft is retained.
    """
    result = deepcopy(plan)
    if strategy.get("kind") != "uncontrolled_statement":
        return result
    material = str(plan.get("public_material") or "")
    fenced = re.fullmatch(r"\s*```[cC]\s*\n(?P<code>[\s\S]*?)```\s*", material)
    if not fenced or len(material) > 2000:
        return result
    ident = r"[A-Za-z_][A-Za-z0-9_]*"
    number = r"-?(?:0|[1-9][0-9]*)"
    declaration = rf"\s*int\s+({ident})\s*=\s*({number})\s*;\s*"
    parsed = re.fullmatch(
        rf"(?P<decls>(?:{declaration})+)if\s*\(\s*(?P<var>{ident})\s*"
        rf"(?:(?P<op>==|!=|<=|>=|<|>)\s*(?P<bound>{number}))?\s*\)\s*;\s*"
        rf"(?P<target>{ident})\s*=\s*(?P<output>{number})\s*;\s*",
        fenced["code"],
    )
    if not parsed:
        return result
    pairs = re.findall(declaration, parsed["decls"])
    initial = {name: int(value) for name, value in pairs}
    var, target = parsed["var"], parsed["target"]
    bound, output = int(parsed["bound"] or 0), int(parsed["output"])
    options, index = plan.get("options"), plan.get("correct_option_index")
    if (
        len(initial) != len(pairs)
        or var not in initial
        or any(abs(v) > 1000 for v in [*initial.values(), bound, output])
        or not isinstance(options, list)
        or len(options) != 2
        or type(index) is not int
        or index not in (0, 1)
        or not all(isinstance(v, str) and re.fullmatch(number, v.strip()) for v in options)
    ):
        return result
    added_target = target not in initial
    if added_target:
        initial[target] = output + 1
    compare = {
        "==": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }.get(parsed["op"], operator.ne)
    candidates = [initial[var], 0, 1, -1, bound, bound + 1, bound - 1, bound + 2, bound - 2]
    selected = next((v for v in candidates if not compare(v, bound) and (var != target or v != output)), None)
    if selected is None:
        return result
    chosen = {**initial, var: selected}
    if chosen[target] == output:
        chosen[target] = output + 1

    def replace_initializer(match):
        return (
            match[0][: match.start(2) - match.start()]
            + str(chosen[match[1]])
            + match[0][match.end(2) - match.start() :]
        )

    declarations = re.sub(declaration, replace_initializer, parsed["decls"])
    if added_target:
        declarations += f"int {target} = {chosen[target]};\n"
    code = declarations + fenced["code"][parsed.end("decls") :]
    alternatives = ["", ""]
    alternatives[index], alternatives[1 - index] = str(output), str(chosen[target])
    result.update(
        public_material=material[: fenced.start("code")] + code + material[fenced.end("code") :],
        ask=f"执行上述代码后，变量 {target} 的值是多少？",
        correct_prediction=str(output),
        incorrect_prediction=str(chosen[target]),
        options=alternatives,
        incorrect_rule="错误地把分号后的赋值视为受该if条件控制，其余语义不变",
        trace=f"初值{chosen}使条件为假。if的分支体为空语句，随后{target}={output}仍执行；错误规则会跳过赋值，保留{chosen[target]}。",
        design_normalization={
            "kind": "synthesized_falsy_contrast",
            "original_material": material,
            "initial_values": chosen,
            "condition_value": False,
        },
    )
    return result


def normalize_exit_observation(plan: dict, strategy: dict) -> dict:
    """Expose a single C for-counter in its enclosing block for exit questions.

    Only literal int initializers and simple scalar updates are supported. A
    shadowed name, multiple loops or unknown initializer is never rewritten.
    """
    result = deepcopy(plan)
    if strategy.get("kind") != "exit_state":
        return result
    material = str(plan.get("public_material") or "")
    fenced = re.fullmatch(r"\s*```[cC]\s*\n(?P<code>[\s\S]*?)```\s*", material)
    if not fenced or len(material) > 2000:
        return result
    code = fenced["code"]
    if len(re.findall(r"\bfor\s*\(", code)) != 1 or re.search(r"\bgoto\b", code):
        return result
    loop = re.search(r"\bfor\s*\((?P<init>[^;]*);[^;]*;(?P<update>[^()]*)\)", code)
    if not loop or not re.search(r"\bbreak\s*;", code):
        return result
    ident, number = r"[A-Za-z_][A-Za-z0-9_]*", r"-?(?:0|[1-9][0-9]*)"
    update = re.fullmatch(
        rf"\s*(?:(?:\+\+|--)\s*({ident})|({ident})\s*(?:\+\+|--|[+-]=\s*{number}))\s*", loop["update"]
    )
    if not update:
        return result
    var = update[1] or update[2]
    initializer = re.fullmatch(rf"\s*int\s+{re.escape(var)}\s*=\s*({number})\s*", loop["init"])
    if initializer:
        prefix = code[: loop.start()].rstrip()
        if prefix and prefix[-1] not in "{;}":
            return result
        if abs(int(initializer[1])) > 1000 or re.search(rf"\b{re.escape(var)}\b", code[: loop.start()]):
            return result
        # Reject another declaration of the same name, including after the loop.
        if len(re.findall(rf"\bint\s+{re.escape(var)}\b", code)) != 1:
            return result
        code = code[: loop.start()] + f"int {var} = {initializer[1]};\nfor (" + code[loop.end("init") :]
    elif not (
        re.fullmatch(rf"\s*(?:{re.escape(var)}\s*=\s*{number})?\s*", loop["init"])
        and re.search(rf"\bint\s+{re.escape(var)}\s*=\s*{number}\s*;", code[: loop.start()])
    ):
        return result
    result.update(
        public_material=material[: fenced.start("code")] + code + material[fenced.end("code") :],
        ask=f"退出上述 for 循环后（仍在其所在语句块内），变量 {var} 的值是多少？",
        design_normalization={
            "kind": "visible_loop_exit_counter",
            "original_material": material,
            "original_ask": plan.get("ask"),
            "observed_variable": var,
        },
    )
    return result


def normalize_control_action(plan: dict, strategy: dict) -> dict:
    """Render the C for/continue mechanism from the actual public header."""
    result = deepcopy(plan)
    if strategy.get("kind") != "next_control_action":
        return result
    material = str(plan.get("public_material") or "")
    fenced = re.fullmatch(r"\s*```[cC]\s*\n(?P<code>[\s\S]*?)```\s*", material)
    if not fenced or len(material) > 2000:
        return result
    code = fenced["code"]
    if len(re.findall(r"\b(?:for|while|do)\b", code)) != 1 or re.search(r"\bgoto\b", code):
        return result
    loop = re.search(r"\bfor\s*\([^;]*;(?P<condition>[^;]*);(?P<update>[^()]*)\)", code)
    if not loop or not re.search(r"\bcontinue\s*;", code):
        return result
    condition, update = loop["condition"].strip(), loop["update"].strip()
    if not condition or not update:
        return result
    # Isolate the target action when its only guard is the first body statement.
    # This avoids an incidental later mutation making the chosen continue path
    # unreachable. Unknown/nested guards remain unchanged for normal review.
    guard = re.search(r"\bif\s*\([^()]*\)\s*(?:\{\s*continue\s*;\s*\}|continue\s*;)", code)
    if (
        guard
        and len(re.findall(r"\bif\b", code)) == 1
        and not re.search(r"\belse\b", code)
        and re.fullmatch(r"\s*\{\s*", code[loop.end() : guard.start()])
    ):
        code = code[: guard.start()] + "continue;" + code[guard.end() :]
        material = material[: fenced.start("code")] + code + material[fenced.end("code") :]
    correct = f"跳过本轮剩余循环体，执行 `{update}`，然后判断 `{condition}`"
    incorrect = f"跳过本轮剩余循环体，直接判断 `{condition}`，不执行 `{update}`"
    index = plan.get("correct_option_index")
    index = index if type(index) is int and index in (0, 1) else 0
    options = ["", ""]
    options[index], options[1 - index] = correct, incorrect
    result.update(
        public_material=material,
        ask="在上述 for 循环中执行到 continue 时，接下来正确的控制流顺序是哪一项？",
        correct_prediction=correct,
        incorrect_prediction=incorrect,
        options=options,
        correct_option_index=index,
        incorrect_rule="continue跳过本轮剩余循环体，但跳过for头的更新部分，直接检查条件",
        trace=f"本题for的更新部分为{update}，条件为{condition}。C17中continue先跳到更新部分，随后检查条件。错误规则直接检查条件，两种控制流顺序不同。",
        design_normalization={
            "kind": "for_continue_action",
            "original_material": plan.get("public_material"),
            "original_ask": plan.get("ask"),
            "original_options": plan.get("options"),
        },
    )
    return result


def _concept_alternatives(plan: dict, *, ask: str, correct: str, incorrect: str, kind: str) -> dict:
    result = deepcopy(plan)
    index = plan.get("correct_option_index")
    index = index if type(index) is int and index in (0, 1) else 0
    options = ["", ""]
    options[index], options[1 - index] = correct, incorrect
    result.update(
        ask=ask,
        correct_prediction=correct,
        incorrect_prediction=incorrect,
        options=options,
        correct_option_index=index,
        trace=correct,
        incorrect_rule=incorrect,
        design_normalization={
            "kind": kind,
            "original_material": plan.get("public_material"),
            "original_ask": plan.get("ask"),
            "original_options": plan.get("options"),
        },
    )
    return result


def normalize_conversion_observation(plan: dict, strategy: dict) -> dict:
    """Ask about the parsed cast, not a later destination that erases its effect."""
    if strategy.get("kind") != "conversion_scope":
        return deepcopy(plan)
    material = str(plan.get("public_material") or "")
    fenced = re.fullmatch(r"\s*```[cC]\s*\n(?P<code>[\s\S]*?)```\s*", material)
    if not fenced or len(material) > 2000:
        return deepcopy(plan)
    atom = r"(?:[A-Za-z_][A-Za-z0-9_]*|-?(?:0|[1-9][0-9]*))"
    code = fenced["code"]
    whole = re.search(rf"\((?:double|float|int)\)\s*\(\s*({atom})\s*/\s*({atom})\s*\)", code)
    before = re.search(rf"\((?:double|float|int)\)\s*({atom})\s*/\s*({atom})", code)
    match = whole or before
    if match is None:
        return deepcopy(plan)
    before_text = f"转换作用于左操作数 `{match[1]}`，发生在除法之前"
    after_text = f"转换作用于整个 `{match[1]} / {match[2]}` 的结果，发生在除法之后"
    return _concept_alternatives(
        plan,
        ask=f"表达式 `{match[0]}` 中，显式转换的作用范围及其相对于除法的顺序，哪项描述正确？",
        correct=after_text if whole else before_text,
        incorrect=before_text if whole else after_text,
        kind="cast_scope_observation",
    )


def normalize_assignment_observation(plan: dict, strategy: dict) -> dict:
    """Keep one self-contained scalar initializer and observe its type sequence."""
    if strategy.get("kind") != "assignment_sequence":
        return deepcopy(plan)
    material = str(plan.get("public_material") or "")
    fenced = re.fullmatch(r"\s*```[cC]\s*\n(?P<code>[\s\S]*?)```\s*", material)
    if not fenced or len(material) > 2000:
        return deepcopy(plan)
    number = r"-?(?:0|[1-9][0-9]*)"
    match = re.search(
        rf"\b(double|float)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*({number})\s*/\s*({number})\s*;", fenced["code"]
    )
    if not match or int(match[4]) == 0 or max(abs(int(match[3])), abs(int(match[4]))) > 1000:
        return deepcopy(plan)
    datatype, name, left, right = match.groups()
    result = _concept_alternatives(
        plan,
        ask=f"初始化 `{name}` 时，右侧表达式求值和存储转换的顺序是哪一项？",
        correct=f"先对 `{left} / {right}` 执行整数除法，再将结果转换为 `{datatype}` 存入 `{name}`",
        incorrect=f"先因目标类型 `{datatype}` 将右侧两个操作数转为浮点数，再执行浮点除法存入 `{name}`",
        kind="assignment_sequence_observation",
    )
    result["public_material"] = "```c\n" + match[0] + "\n```"
    return result


def evidence_recovery_action(codes: list[str], *, validation_passed: bool) -> str:
    """Retry the responsible artifact, never a specific point or answer."""
    failures = set(codes) - {"INDEPENDENT_EVIDENCE_UNVERIFIED", "SEMANTIC_REVIEW_FAILED", "QUALITY_DIMENSION_BELOW_MINIMUM", "FINAL_SOLUTION_REVIEW_MISSING", "VALIDATION_FAILED"}
    if not validation_passed or not failures:
        return "author"
    if failures == {"RUBRIC_ANSWER_MISMATCH"}:
        return "rubric"
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


def candidate_from_measurement_design(context: dict, *, position_allocator: ChoicePositionAllocator | None = None) -> dict | None:
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
    plan = deepcopy(plan)
    if position_allocator is not None:
        target = position_allocator.allocate(str(slot.get("slot_id") or ""), len(options))
        order = list(range(len(options)))
        order[index], order[target] = order[target], order[index]
        options = [options[i] for i in order]
        plan["option_position_receipt"] = {"original_options": plan["options"], "original_correct_index": index, "permutation": order}
        index = target
        plan.update(options=options, correct_option_index=index)
    ask = plan["ask"]
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
