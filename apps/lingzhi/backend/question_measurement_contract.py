"""Local checks and inspectable review witnesses, independent of any sample IDs.

Arithmetic checks accept only small literal +, - and * expressions. They never
execute generated code. A review witness is necessary evidence, not a proof of
student diagnostic validity; domain execution checks can strengthen it later.
"""

import ast
import json
import re
from decimal import Decimal, InvalidOperation, localcontext


def _issue(code: str, message: str, evidence: str = "") -> dict:
    return {"code": code, "severity": "critical", "message": message, "evidence": evidence[:400]}


def _plain(value) -> str:
    return re.sub(r"\s+|`", "", str(value or "")).casefold()


def _number(value) -> Decimal | None:
    text = str(value).strip().strip("`").replace("−", "-")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?", text) or len(text) > 50:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _literal_arithmetic(expression: str) -> Decimal | None:
    if len(expression) > 120:
        return None
    try:
        tree = ast.parse(expression.replace("×", "*").replace("−", "-"), mode="eval")
        if len(list(ast.walk(tree))) > 64:
            return None

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                value = Decimal(str(node.value))
                if not value.is_finite() or abs(value) > 10**12:
                    raise ValueError("number outside probe range")
                return value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
                left, right = visit(node.left), visit(node.right)
                return (
                    left + right
                    if isinstance(node.op, ast.Add)
                    else left - right
                    if isinstance(node.op, ast.Sub)
                    else left * right
                )
            raise ValueError("not literal arithmetic")

        with localcontext() as ctx:
            ctx.prec = 60
            return visit(tree.body)
    except (SyntaxError, ValueError, ArithmeticError):
        return None


def _following_conditions(code: str) -> list[str]:
    masked = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', code)
    conditions = []
    for match in re.finditer(r"\belse\s+if\s*\(", masked):
        start = match.end()
        depth = 1
        for pos in range(start, len(masked)):
            depth += (masked[pos] == "(") - (masked[pos] == ")")
            if depth == 0:
                conditions.append(masked[start:pos])
                break
    return conditions


def measurement_findings(contract: dict, brief: dict | None = None) -> list[dict]:
    brief = brief or contract.get("design_brief") or {}
    spec = contract.get("question_spec") or {}
    prompt = str(contract.get("prompt") or "")
    options = spec.get("options") or contract.get("options") or []
    issues = []
    asks_value = bool(re.search(r"数值|值是多少|值为多少|执行了几次|执行次数", prompt))
    literal_output = bool(re.search(r"打印|输出|字符串|文本|格式", prompt))
    if asks_value and (not literal_output or re.search(r"输出(?:什么|的|哪个)?数值|打印(?:出)?的数值", prompt)):
        numbers = {}
        for option in options:
            text = str(option.get("text") or option.get("label") or "").strip().strip("`")
            if re.fullmatch(r"[\d\s.()+*/%−+-]+", text) and re.search(r"\d\s*[/+*%−-]\s*\d", text):
                issues.append(
                    _issue(
                        "AMBIGUOUS_VALUE_OPTION",
                        "题目要求数值，选项却给出未明确解释的算式；请使用直接且不等价的数值。",
                        text,
                    )
                )
            number = _number(text)
            if number is not None:
                if number in numbers:
                    issues.append(
                        _issue(
                            "EQUIVALENT_NUMERIC_OPTIONS",
                            "多个数值选项等价，不能形成唯一正确的单选答案。",
                            f"{numbers[number]} / {text}",
                        )
                    )
                numbers[number] = text
    target = str(brief.get("primary_knowledge") or "")
    code = "\n".join(re.findall(r"```(?:c|cpp)?\s*\n([\s\S]*?)```", prompt, re.I))
    prose = re.sub(r"```[\s\S]*?```", "", prompt)
    local_counter = re.search(r"\bfor\s*\(\s*int\s+([A-Za-z_]\w*)\s*=", code)
    if (local_counter and len(re.findall(r"\bfor\s*\(", code)) == 1
            and len(re.findall(rf"\bint\s+{re.escape(local_counter[1])}\b", code)) == 1
            and re.search(r"程序结束|循环结束|退出.*循环|循环.*之后", prose)
            and re.search(rf"变量\s*`?{re.escape(local_counter[1])}`?\s*(?:的|值)", prose)):
        issues.append(_issue("OBSERVED_VARIABLE_OUT_OF_SCOPE", "for头内声明的变量在循环结束后已离开作用域；应在外围声明并明确观察时点。"))
    asks_condition = bool(
        re.search(r"条件.{0,20}(?:是否|会不会|还会|求值|判断)|(?:是否|会不会|还会).{0,20}(?:求值|判断)", prose)
        or re.search(r"(?:实际被|被实际|实际|被)求值.{0,24}条件", prose)
    )
    conditions = _following_conditions(code)
    if (
        re.search(r"求值.*后续|后续.*求值", target)
        and conditions
        and not asks_condition
        and "volatile" not in code
        and all(not re.search(r"\+\+|--|(?<![=!<>])=(?!=)|\w+\s*\(", c) for c in conditions)
    ):
        issues.append(
            _issue(
                "UNOBSERVABLE_CONDITION_EVALUATION",
                "目标是不求值后续条件，但条件没有可观测副作用，题目也未直接询问求值行为；分支体的赋值不能证明条件未求值。",
                str(conditions),
            )
        )
    solution = contract.get("solution_envelope") or contract.get("answer_spec") or {}
    explanation = json.dumps(solution.get("worked_solution") or {}, ensure_ascii=False)
    if (brief.get("language_contract") or {}).get("language_standard") == "C17" and re.search(
        r"(?:`/`|除法运算符)[^。\n]{0,12}(?:是|为)(?:一个)?(?:后置|后缀|前缀|前置)运算符", explanation
    ):
        issues.append(
            _issue("OPERATOR_FIXITY_CONTRADICTION", "C语言的除法/是二元中缀运算符，不能同时说成前缀或后缀运算符。")
        )
    pattern = r"(?<![A-Za-z0-9_.])([+-]?\d+(?:\.\d+)?(?:\s*[+*×−-]\s*[+-]?\d+(?:\.\d+)?)+)\s*=\s*([+-]?\d+(?:\.\d+)?)(?![\d.])"
    for match in re.finditer(pattern, explanation):
        prefix = explanation[max(0, match.start() - 25) : match.start()]
        suffix = explanation[match.end():]
        # This probe can evaluate only a complete literal equality. A number
        # inside a power, fraction or expression containing variables is not
        # such an equality; leave that expression to the semantic reviewer.
        if re.search(r"[A-Za-z0-9_.^*/+×−\\{}()\[\]-]\s*$", prefix) or re.match(r"\s*[A-Za-z0-9_.^*/+×−\\{}\[\]-]", suffix):
            continue
        if re.search(r"误算|错误地|假设错误", prefix):
            continue
        value = _literal_arithmetic(match[1])
        if value is not None and value != _number(match[2]):
            issues.append(
                _issue("EXPLANATION_ARITHMETIC_ERROR", "解析中的字面加减乘等式不成立，请按实际数值重新核对。", match[0])
            )
    facts = json.dumps((brief.get("answer_fact_contract") or {}).get("fact_basis") or [], ensure_ascii=False)
    for citation in re.findall(r"第\s*\d+(?:\.\d+)*\s*节\s*第\s*\d+\s*段", explanation):
        if _plain(citation) not in _plain(facts):
            issues.append(
                _issue(
                    "UNSUPPORTED_PRECISE_CITATION",
                    "解析引用的精确条款号没有出现在提供的来源中；不得编造，改用可核对的规则说明。",
                    citation,
                )
            )
    for match in re.finditer(r"C(?:11|17|18|23)\s*(?:标准)?\s*(?:第)?\s*(\d+\.\d+(?:\.\d+)*)", explanation):
        if match[1] not in facts:
            issues.append(
                _issue(
                    "UNSUPPORTED_PRECISE_CITATION",
                    "提供的来源没有支持该精确标准条款号；请引用材料中的规则而非补造条款。",
                    match[0],
                )
            )
    return issues


def fixed_input_witness_issues(prompt: str, witness: dict) -> list[dict]:
    """Reject changed literal inputs only when the displayed scalar is read-only.

    Unknown expressions, escaped addresses, writes and volatile state are left
    for semantic review; this is deliberately not a C interpreter.
    """
    code = "\n".join(re.findall(r"```(?:c|cpp)?\s*\n([\s\S]*?)```", prompt, re.I))
    code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*', lambda m: " " * len(m[0]), code)
    if "volatile" in code:
        return []
    pattern = (
        r"\b(?:(?:const|signed|unsigned|long|short)\s+)*(?:int|double|float|char|_Bool)\s+(?=[A-Za-z_]\w*\s*=)([^;]+);"
    )
    declarations = list(re.finditer(pattern, code))
    outside = re.sub(pattern, "", code)
    inputs = {}
    duplicates = set()
    for declaration in declarations:
        for part in declaration[1].split(","):
            match = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*", part)
            if not match:
                continue
            name, value = match.groups()
            if name in inputs:
                duplicates.add(name)
            inputs[name] = _number(value)
    observation = witness.get("observation_test") or {}
    text = json.dumps(observation, ensure_ascii=False)
    issues = []
    for name, value in inputs.items():
        escaped = re.escape(name)
        if name in duplicates or re.search(
            rf"\b{escaped}\s*(?:=(?!=)|[+*/%-]=|\+\+|--)|(?:\+\+|--|&)\s*\b{escaped}\b", outside
        ):
            continue
        for match in re.finditer(rf"\b{escaped}\s*=\s*([+-]?\d+(?:\.\d+)?)(?![\d.])", text):
            if _number(match[1]) != value:
                issues.append(
                    _issue(
                        "COUNTERFACTUAL_INPUT_CHANGED",
                        "正确与错误规则必须使用题面相同的固定输入，不能换输入制造观测差异。",
                        match[0],
                    )
                )
    return issues


def _if_binding_signature(code: str) -> tuple[list[str], list[str]] | None:
    """Parse a bounded if/else/block/semicolon subset, or return unknown."""
    code = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', " ", code)
    start = re.search(r"\bif\s*\(", code)
    if not start or len(code) > 12000:
        return None
    tokens = re.findall(r"[A-Za-z_]\w*|\d+|[^\s]", code[start.start() :])
    if len(tokens) > 2000:
        return None
    pos = 0
    conditions = []
    owners = []

    def statement(depth=0):
        nonlocal pos
        if depth > 16 or pos >= len(tokens):
            raise ValueError("unsupported")
        token = tokens[pos]
        pos += 1
        if token == "if":
            if tokens[pos] != "(":
                raise ValueError("unsupported")
            pos += 1
            begin = pos
            level = 1
            while level and pos < len(tokens):
                level += (tokens[pos] == "(") - (tokens[pos] == ")")
                pos += 1
            if level:
                raise ValueError("unclosed")
            condition = "".join(tokens[begin : pos - 1])
            conditions.append(condition)
            statement(depth + 1)
            if pos < len(tokens) and tokens[pos] == "else":
                owners.append(condition)
                pos += 1
                statement(depth + 1)
        elif token == "{":
            while pos < len(tokens) and tokens[pos] != "}":
                statement(depth + 1)
            if pos >= len(tokens):
                raise ValueError("unclosed")
            pos += 1
        elif token == ";":
            return
        else:
            if token in {"for", "while", "switch", "do", "else", "}"}:
                raise ValueError("unsupported")
            while pos < len(tokens) and tokens[pos] != ";":
                if tokens[pos] in {"{", "}"}:
                    raise ValueError("unsupported")
                pos += 1
            if pos >= len(tokens):
                raise ValueError("unclosed")
            pos += 1

    try:
        statement()
        return sorted(conditions), sorted(owners)
    except (ValueError, IndexError):
        return None


def observation_prediction_issues(prompt: str, observation: dict) -> list[dict]:
    public_task = re.sub(r"```[\s\S]*?```", "", prompt)
    numeric_or_output = re.search(
        r"数值|最终值|的值是|的值为|值是多少|值为多少|执行.{0,8}几次|执行次数|完整输出|打印出的|控制台.{0,12}输出|输出.{0,12}什么",
        public_task,
    )
    predictions = (str(observation.get("correct_prediction") or ""), str(observation.get("incorrect_prediction") or ""))
    if numeric_or_output and any(
        re.search(r"若|如果|否则|仅当|取决于|依赖于|(?:为真|为假|成立|不成立)时|\bif\b|\bdepending\b", prediction, re.I)
        for prediction in predictions
    ):
        return [
            _issue(
                "OBSERVATION_PREDICTION_UNEVALUATED",
                "数值/输出任务的两种预测必须在题面相同输入下求值，给出具体结果或不终止，不能用未代入的条件句代替。",
            )
        ]
    return []


def review_witness_issues(contract: dict, witness: dict) -> list[dict]:
    if not isinstance(witness, dict):
        witness = {}
    spec = contract.get("question_spec") or {}
    options = spec.get("options") or contract.get("options") or []
    ids = {str(o.get("id")) for o in options}
    audit = witness.get("option_audit")
    issues = []
    if (
        not isinstance(audit, list)
        or len(audit) != len(ids)
        or any(not isinstance(row, dict) for row in audit)
        or {str(row.get("option_id")) for row in audit} != ids
        or any(
            not row.get("meaning") or not row.get("reason") or type(row.get("is_correct")) is not bool for row in audit
        )
    ):
        issues.append(
            _issue("OPTION_AUDIT_INCOMPLETE", "独立评审必须逐项给出实际选项的解释、判断和依据，不能只列通过标记。")
        )
    elif ids:
        canonical = (contract.get("solution_envelope") or contract.get("answer_spec") or {}).get("canonical_answer")
        correct = {str(v) for v in canonical} if isinstance(canonical, list) else {str(canonical)}
        if {str(row["option_id"]) for row in audit if row["is_correct"]} != correct:
            issues.append(_issue("OPTION_REASONING_CONTRADICTION", "独立逐项评审的正确选项集合与参考答案不一致。"))
    obs = witness.get("observation_test") or {}
    required = (
        "target_statement",
        "observed_quantity",
        "public_anchor",
        "incorrect_rule",
        "correct_prediction",
        "incorrect_prediction",
        "trace",
    )
    if not isinstance(obs, dict) or any(not isinstance(obs.get(k), str) or not obs[k].strip() for k in required):
        issues.append(
            _issue("OBSERVATION_WITNESS_MISSING", "必须给出目标、实际观测位置、错误规则、两种预测与可复核执行摘要。")
        )
    else:
        target = (contract.get("design_brief") or {}).get("primary_knowledge")
        if target and _plain(obs["target_statement"]) != _plain(target):
            issues.append(
                _issue("OBSERVATION_TARGET_CHANGED", "观测证明必须针对完整的主考规则，不得换成更弱的邻近知识。")
            )
        # Math delimiters are presentation, not part of the observation.
        # Preserve expression characters so a different variable still fails.
        def anchor_text(value):
            return _plain(re.sub(r"(?<!\\)\$|\\[\[\]() ]", "", str(value or "")))
        if len(anchor_text(obs["public_anchor"])) < 2 or anchor_text(obs["public_anchor"]) not in anchor_text(contract.get("prompt")):
            issues.append(
                _issue("OBSERVATION_ANCHOR_MISSING", "声明的观测位置不存在于实际公开题目中。", obs["public_anchor"])
            )
        left, right = obs["correct_prediction"], obs["incorrect_prediction"]
        issues.extend(observation_prediction_issues(str(contract.get("prompt") or ""), obs))
        if _plain(left) == _plain(right) or (_number(left) is not None and _number(left) == _number(right)):
            issues.append(
                _issue("OBSERVATION_NOT_DISCRIMINATING", "正确规则与目标错误规则产生相同观测，本题不能区分该错误。")
            )
    assumptions = witness.get("unsupported_assumptions")
    if not isinstance(assumptions, list) or assumptions:
        issues.append(
            _issue(
                "UNSUPPORTED_REASONING_ASSUMPTION",
                "评审须核对未给定初值、隐含前置或额外事实；尚有无依据假设时不得通过。",
                str(assumptions),
            )
        )
    review_contract = {
        "solution_envelope": {"worked_solution": witness},
        "design_brief": contract.get("design_brief") or {},
    }
    issues.extend(measurement_findings(review_contract))
    issues.extend(fixed_input_witness_issues(str(contract.get("prompt") or ""), witness))
    trace = str(obs.get("trace") or "") if isinstance(obs, dict) else ""
    source_code = "\n".join(re.findall(r"```(?:c|cpp)?\s*\n([\s\S]*?)```", str(contract.get("prompt") or ""), re.I))
    first_if = re.search(r"\bif\s*\(", trace)
    if first_if and not re.search(
        r"错误|incorrect|counterfactual", trace[max(0, first_if.start() - 25) : first_if.start()], re.I
    ):
        original, expanded = _if_binding_signature(source_code), _if_binding_signature(trace)
        if original and expanded and original[0] == expanded[0] and original[1] != expanded[1]:
            issues.append(
                _issue(
                    "TRACE_CONTROL_STRUCTURE_CHANGED", "核验摘要改写了if/else的语法归属，不能用修改后的结构证明原题。"
                )
            )
    return issues
