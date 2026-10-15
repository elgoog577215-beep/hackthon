"""Program-owned evidence for complete public problems, never model attestation.

Supported computational plans are bounded, calculated first, then rendered by
this module. Any change outside that rendering loses coverage and goes to fact
review. An expression hidden in solver_contract cannot certify a prose premise.
"""
from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from fractions import Fraction
from functools import lru_cache
from typing import Any

from course_versioning import stable_hash

FACT_SCHEMA = "assessment_fact_evidence_v1"
_PUBLIC_FIELDS = ("stimulus", "task", "constraints", "options", "input_contract", "response_contract")
_DELIVERY_FIELDS = ("canonical_answer", "worked_solution", "rubric", "acceptable_answers", "validator_config", "solution_graph")
PLAN_KINDS = ("arithmetic", "dynamic_array", "range_sum", "treap_depth", "zipf_coverage", "state_operations")


def _integer(value: Any, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("computation parameter outside supported bounds")
    return value


def _arithmetic(text: str) -> Fraction:
    if not isinstance(text, str) or not 1 <= len(text) <= 160:
        raise ValueError("invalid arithmetic expression")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid arithmetic expression") from exc
    if sum(1 for _ in ast.walk(tree)) > 48:
        raise ValueError("expression too large")
    def calculate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = Fraction(str(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = calculate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = calculate(node.left), calculate(node.right)
            if isinstance(node.op, ast.Add): value = left + right
            elif isinstance(node.op, ast.Sub): value = left - right
            elif isinstance(node.op, ast.Mult): value = left * right
            else:
                if right == 0: raise ValueError("division by zero")
                value = left / right
        else:
            raise ValueError("unsupported arithmetic syntax")
        if abs(value) > 10**12 or value.denominator > 10**12:
            raise ValueError("arithmetic value outside supported bounds")
        return value
    return calculate(tree.body)


@lru_cache(maxsize=4096)
def treap_expected_depth(n: int, rank: int) -> Fraction:
    """Exact recurrence over uniformly random roots; no supplied theorem used."""
    _integer(n, 1, 32)
    _integer(rank, 1, n)
    total = Fraction(0)
    for root in range(1, n + 1):
        if rank < root:
            total += 1 + treap_expected_depth(root - 1, rank)
        elif rank > root:
            total += 1 + treap_expected_depth(n - root, rank - root)
    return total / n


def _compute(plan: dict) -> tuple[Any, str, str]:
    if not isinstance(plan, dict) or plan.get("kind") not in PLAN_KINDS:
        raise ValueError("unsupported computation plan")
    kind = plan["kind"]
    if kind == "state_operations":
        if set(plan) != {"kind","initial_state","operations"}: raise ValueError("unknown state parameter")
        if len(json.dumps(plan, ensure_ascii=False)) > 4000: raise ValueError("state plan too large")
        state, trace = deepcopy(plan["initial_state"]), []
        if not isinstance(state, (list,dict)) or not isinstance(plan["operations"], list) or not 1 <= len(plan["operations"]) <= 32:
            raise ValueError("invalid state plan")
        for op in plan["operations"]:
            if not isinstance(op,dict): raise ValueError("invalid operation")
            if op.get("op") == "append" and isinstance(state,list) and set(op) == {"op","value"}: state.append(deepcopy(op["value"]))
            elif op.get("op") == "pop" and isinstance(state,list) and state and set(op) == {"op"}: state.pop()
            elif op.get("op") == "set" and isinstance(state,dict) and isinstance(op.get("key"),str) and set(op) == {"op","key","value"}: state[op["key"]] = deepcopy(op["value"])
            elif op.get("op") == "delete" and isinstance(state,dict) and isinstance(op.get("key"),str) and set(op) == {"op","key"}: state.pop(op["key"], None)
            else: raise ValueError("operation incompatible with state")
            trace.append(deepcopy(state))
        return state, "从initial_state开始按顺序执行operations。append在列表末尾追加，pop删除列表最后一个元素；set设置字典键，delete删除键（不存在则不变）。给出最终状态。", "逐步状态为：" + json.dumps(trace,ensure_ascii=False,sort_keys=True)
    if kind == "arithmetic":
        if set(plan) != {"kind", "expression"}: raise ValueError("unknown arithmetic parameter")
        value = _arithmetic(plan["expression"])
        result = value.numerator if value.denominator == 1 else str(value)
        return result, "计算给定表达式的精确值。", f"使用有理数运算逐步计算 {plan['expression']}，得到 {value}。"
    if kind == "dynamic_array":
        if set(plan) != {"kind", "append_count"}: raise ValueError("unknown dynamic-array parameter")
        count = _integer(plan["append_count"], 1, 32)
        size = capacity = 1
        costs = []
        for _ in range(count):
            cost = 1
            if size == capacity:
                cost += size
                capacity *= 2
            size += 1
            costs.append(cost)
        return sum(costs), "动态数组初始元素数和容量均为1。只追加；满时容量翻倍并复制原有元素，复制每个元素及写入新元素各计成本1。求给定次数追加的总实际成本。", f"逐次成本为 {costs}，相加为 {sum(costs)}；最终元素数 {size}、容量 {capacity}。"
    if kind == "range_sum":
        if set(plan) != {"kind", "values", "start", "end"}: raise ValueError("unknown range parameter")
        values = plan["values"]
        if not isinstance(values, list) or not 1 <= len(values) <= 64: raise ValueError("invalid array")
        for value in values: _integer(value, -10**6, 10**6)
        start = _integer(plan["start"], 0, len(values)-1)
        end = _integer(plan["end"], start, len(values)-1)
        result = sum(values[start:end+1])
        return result, "数组下标从0开始。求闭区间[start,end]的元素和，计入两个端点。", f"区间内元素为 {values[start:end+1]}，精确相加得到 {result}。"
    if kind == "treap_depth":
        if set(plan) != {"kind", "n", "rank"}: raise ValueError("unknown tree parameter")
        n = _integer(plan["n"], 1, 32)
        rank = _integer(plan["rank"], 1, n)
        value = treap_expected_depth(n, rank)
        return str(value), "Treap的键为1到n，优先级相互独立且服从同一连续均匀分布，同时满足BST序与堆序。深度按边数计，根深度为0。求键rank的精确期望深度。", f"枚举根键1到{n}的等概率情况；目标为根时深度0，否则为1加对应随机子树的期望深度。精确递推结果为 {value}。"
    if set(plan) != {"kind", "n", "alpha", "threshold"}: raise ValueError("unknown probability parameter")
    n = _integer(plan["n"], 1, 64)
    alpha = _integer(plan["alpha"], 0, 4)
    if not isinstance(plan["threshold"],str) or len(plan["threshold"]) > 48: raise ValueError("invalid threshold")
    try: threshold = Fraction(plan["threshold"])
    except (TypeError, ValueError, ZeroDivisionError) as exc: raise ValueError("invalid threshold") from exc
    if not 0 < threshold <= 1: raise ValueError("invalid threshold")
    weights = [Fraction(1, k**alpha) for k in range(1, n+1)]
    total, cumulative = sum(weights), Fraction(0)
    for count, weight in enumerate(weights, 1):
        previous = cumulative / total
        cumulative += weight
        if cumulative / total >= threshold:
            return count, "离散Zipf模型定义为p(k)=k^(-alpha)/Σ(j^(-alpha)), j=1..n。按索引1、2、…选取，求累计概率达到或超过threshold的最小样本数。", f"前{count-1}项概率为 {previous}，小于 {threshold}；前{count}项概率为 {cumulative/total}，达到或超过阈值，所以最少取{count}项。"
    raise ValueError("unreachable probability threshold")


def build_computed_candidate(plan: dict) -> dict:
    """Compute first and render the entire fact-bearing problem deterministically."""
    result, task, derivation = _compute(plan)
    public = "计算模型与输入参数：\n```json\n" + json.dumps(plan, ensure_ascii=False, sort_keys=True) + "\n```"
    answer = {"premises": public, "derivation": derivation, "conclusion": str(result)}
    work = {"schema_version":"worked_solution_v1", "summary":f"精确结果为 {result}。",
            "steps":[{"title":"按公开模型计算", "explanation":derivation, "result":str(result)}],
            "final_answer":deepcopy(answer), "checks":["从公开参数重新计算，核对边界与精确结果。"],
            "option_analysis":[], "common_errors":[]}
    return {"question_spec":{
        "stimulus":{"rendered_text":public}, "task":{"rendered_text":task,"deliverable":"填写前提、推导过程和结论"},
        "constraints":[], "options":[], "response_contract":{"format":"structured_fields"},
        "input_contract":{"mode":"structured_fields", "fields":[
            {"field_id":key,"kind":"rich_text","label":label,"required":True}
            for key,label in (("premises","前提与已知条件"),("derivation","推导过程"),("conclusion","结论"))]},
        "computation_plan":deepcopy(plan),
    }, "solution":{
        "validation_mode":"expert_rubric_validator", "canonical_answer":answer,
        "acceptable_answers":[], "rubric":["依据公开模型说明条件、完成计算并得到精确结论。"], "validator_config":{},
        "solution_graph":{"schema_version":"solution_graph_v1","steps":[{"step_id":"step_1","action":derivation,"check":str(result)}]},
        "worked_solution":work,
    }}


def _public_binding(spec: dict) -> dict:
    payload = {key:deepcopy(spec.get(key)) for key in _PUBLIC_FIELDS}
    # Blueprint identity/labels do not alter the mathematical problem, but
    # input shape and field identities do.
    response = spec.get("input_contract") or {}
    payload["input_contract"] = {"mode":response.get("mode"), "fields":[
        {"field_id":f.get("field_id"),"kind":f.get("kind"),"required":f.get("required")}
        for f in response.get("fields") or []]}
    return payload


def _bound_computation(spec: dict) -> dict | None:
    plan = spec.get("computation_plan")
    if plan is None:
        return None
    try: candidate = build_computed_candidate(plan)
    except (ValueError, TypeError, ArithmeticError): return None
    return candidate if _public_binding(spec) == _public_binding(candidate["question_spec"]) else None


def computed_independent_solution(spec: dict) -> dict | None:
    candidate = _bound_computation(spec)
    if candidate is None: return None
    solution = candidate["solution"]
    worked = solution["worked_solution"]
    return {"answer":deepcopy(solution["canonical_answer"]), "summary":worked["summary"],
            "work":deepcopy(worked["steps"]), "checks":deepcopy(worked["checks"]),
            "option_analysis":[], "common_errors":[], "solver_attested":True,
            "solver_kind":"verified_computation_plan"}


def _treap_counterexample(spec: dict) -> dict | None:
    text = " ".join(str((spec.get(key) or {}).get("rendered_text") or "") for key in ("stimulus","task"))
    normalized = re.sub(r"[\s$\\{}]", "", text).replace("−","-")
    if not re.search(r"Treap|随机搜索树|随机二叉搜索树", text, re.I): return None
    if re.search(r"(?:i|rank)=1|(?:i|rank)=n|最小键|最大键|是否|判断.*正确|反驳|错误的", normalized): return None
    if not re.search(r"(?:已知|满足|对于任意).*?(?:E|mathbbE)\[D\(i\)\]=H_?n-1", normalized): return None
    return {"n":3,"rank":2,"expected":str(treap_expected_depth(3,2)), "claimed":str(sum(Fraction(1,k) for k in range(1,4))-1),
            "method":"exact_uniform_root_recurrence"}


def _numeric_counterexample(spec: dict) -> dict | None:
    task = str((spec.get("task") or {}).get("rendered_text") or "")
    if re.search(r"是否|判断|反驳|找出.*错误", task): return None
    text = str((spec.get("stimulus") or {}).get("rendered_text") or "").replace("$", "")
    pattern = r"(?:^|[。；\n])\s*已知\s*([0-9.()+*/\-\s]+?)\s*(>=|<=|==|!=|=|>|<|≥|≤|≠)\s*([0-9.()+*/\-\s]+)(?=[。；\n]|$)"
    for match in re.finditer(pattern, text):
        try: left, right = _arithmetic(match[1].strip()), _arithmetic(match[3].strip())
        except (ValueError, ArithmeticError): continue
        op = match[2]
        valid = {"=":left==right,"==":left==right,"!=":left!=right,"≠":left!=right,
                 ">":left>right,"<":left<right,">=":left>=right,"≥":left>=right,"<=":left<=right,"≤":left<=right}[op]
        if not valid:
            return {"claim":match[0].strip(),"left":str(left),"right":str(right),"operator":op,"method":"exact_rational_comparison"}
    return None


def evaluate_fact_evidence(spec: dict, solution: dict) -> dict:
    evidence = {"schema_version":FACT_SCHEMA, "status":"unverified", "reason":"independent_fact_evidence_missing",
                "question_hash":stable_hash(_public_binding(spec), prefix="factq_")}
    counterexample = _numeric_counterexample(spec) or _treap_counterexample(spec)
    if counterexample:
        return {**evidence,"status":"contradicted","reason":"public_premise_counterexample", "counterexample":counterexample}
    candidate = _bound_computation(spec)
    if candidate is None: return evidence
    expected = candidate["solution"]
    # Check all grading/teaching fields, not only the scalar conclusion.
    same_answer = solution.get("canonical_answer") == expected["canonical_answer"]
    same_work = (solution.get("worked_solution") or {}) == expected["worked_solution"]
    if not same_answer or not same_work:
        return {**evidence,"status":"contradicted","reason":"computed_solution_mismatch"}
    if any(solution.get(key, expected.get(key)) != expected.get(key) for key in ("rubric","acceptable_answers","validator_config","solution_graph")):
        return {**evidence,"status":"contradicted","reason":"computed_grading_mismatch"}
    result, _, _ = _compute(spec["computation_plan"])
    return {**evidence,"status":"verified","reason":"complete_program_owned_problem", "result":result,
            "verifier":spec["computation_plan"]["kind"], "plan_hash":stable_hash(spec["computation_plan"])}


def _artifact_hash(contract: dict) -> str:
    solution = contract.get("solution_envelope") or {}
    return stable_hash({"public":_public_binding(contract.get("question_spec") or {}),
                        "plan":(contract.get("question_spec") or {}).get("computation_plan"),
                        "delivery":{key:solution.get(key) for key in _DELIVERY_FIELDS}}, prefix="facta_")


def apply_fact_evidence(contract: dict) -> dict:
    spec = contract.setdefault("question_spec", {})
    spec["factual_evidence_schema"] = FACT_SCHEMA
    solution = contract.setdefault("solution_envelope", {})
    report = evaluate_fact_evidence(spec, solution)
    report["source_bindings"] = _source_bindings(spec, solution)
    report["artifact_hash"] = _artifact_hash(contract)
    solution["factual_validation"] = deepcopy(report)
    contract.setdefault("solution_validation", {})["factual_validation"] = {
        key:deepcopy(report[key]) for key in ("schema_version","status","reason","question_hash","artifact_hash","verifier") if key in report}
    return report


def _source_bindings(spec: dict, solution: dict) -> list[dict]:
    sources = {str(item.get("reference_id") or ""): item
               for item in solution.get("factual_source_evidence") or [] if isinstance(item,dict)}
    public_text = "\n".join(str((spec.get(key) or {}).get("rendered_text") or "") for key in ("stimulus","task"))
    bindings = []
    for binding in (solution.get("premise_bindings") or [])[:12]:
        if not isinstance(binding,dict): continue
        reference_id = str(binding.get("reference_id") or "")
        claim, quote = str(binding.get("claim") or ""), str(binding.get("quote") or "")
        source = sources.get(reference_id)
        excerpt = str((source or {}).get("reference_excerpt") or "")
        matched = bool(source and quote and claim and quote == claim and quote in excerpt and claim in public_text)
        bindings.append({"reference_id":reference_id, "claim":claim[:1200], "quote":quote[:1200],
                         "status":"matched" if matched else "missing_reference" if source is None else "quote_mismatch",
                         "source_snapshot_hash":stable_hash(source) if source else None,
                         "source_type":(source or {}).get("source_type")})
    return bindings


def fact_publication_state(contract: dict) -> str:
    if (contract.get("question_spec") or {}).get("factual_evidence_schema") != FACT_SCHEMA:
        return "legacy"
    # Recompute at the boundary: a stored/model-written 'verified' flag is not authority.
    return evaluate_fact_evidence(contract.get("question_spec") or {}, contract.get("solution_envelope") or {}).get("status", "unverified")
