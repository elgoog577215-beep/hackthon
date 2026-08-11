"""Independent local solvers that operate on public question contracts only."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
import math
import operator
from typing import Any, Callable


LocalSolver = Callable[[dict[str, Any]], dict[str, Any] | None]

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


@dataclass
class IndependentSolverRegistry:
    _solvers: dict[str, LocalSolver]

    def __init__(self) -> None:
        self._solvers = {}

    @classmethod
    def with_builtin_solvers(cls) -> "IndependentSolverRegistry":
        registry = cls()
        registry.register("numeric_expression", _solve_numeric_expression)
        registry.register("state_operations", _solve_state_operations)
        return registry

    def register(self, kind: str, solver: LocalSolver) -> None:
        normalized = str(kind or "").strip()
        if not normalized:
            raise ValueError("local solver kind is required")
        self._solvers[normalized] = solver

    def solve(
        self,
        public_question_spec: dict[str, Any],
    ) -> dict[str, Any] | None:
        contract = public_question_spec.get("solver_contract") or {}
        if not isinstance(contract, dict):
            return None
        solver = self._solvers.get(str(contract.get("kind") or ""))
        if solver is None:
            return None
        try:
            result = solver(deepcopy(contract))
        except (ArithmeticError, TypeError, ValueError, SyntaxError):
            # SyntaxError 必须单列：它**不是** ValueError 的子类，而
            # `_solve_numeric_expression` 用 `ast.parse` 解析模型给的表达式，
            # 模型只要写成带单位（"150 J - 60 J"）或等式（"ΔU = 20 - 8"）就抛它。
            #
            # 漏掉它的后果不是"这道题不用本地解题器"，而是异常穿透整个
            # `solve()` 把**整个槽位打死**——真机取证里表现为
            # `attempts: []` + `final_decision: discard`，一次生成尝试都没发生。
            # 求解器解不出来的正常语义是返回 None 让题目落回模型求解，
            # 解析失败也该走这条路。
            return None
        if not _complete_solution(result):
            return None
        return deepcopy(result)


def _solve_numeric_expression(
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    expression = str(contract.get("expression") or "").strip()
    if not expression or len(expression) > 200:
        return None
    parsed = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(parsed)) > 64:
        return None
    value = _evaluate_numeric_node(parsed.body)
    if not math.isfinite(value) or abs(value) > 1e15:
        return None
    normalized_value: int | float = (
        int(round(value)) if math.isclose(value, round(value)) else value
    )
    unit = str(contract.get("unit") or "").strip()
    answer: Any = (
        {"value": normalized_value, "unit": unit}
        if unit
        else normalized_value
    )
    return {
        "answer": answer,
        "summary": "根据公开题面中的数值关系完成计算并核对结果。",
        "work": [{
            "title": "代入并计算",
            "explanation": "使用题面公开的数值表达式进行确定性计算。",
            "calculation": expression,
            "result": str(normalized_value),
        }],
        "checks": ["重新计算公开表达式并核对单位"],
        "option_analysis": [],
        "common_errors": [],
        "solver_attested": True,
        "solver_kind": "numeric_expression",
    }


def _evaluate_numeric_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(
            node.value,
            (int, float),
        ):
            raise ValueError("numeric constants only")
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](
            _evaluate_numeric_node(node.operand)
        )
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_numeric_node(node.left)
        right = _evaluate_numeric_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("exponent outside local solver budget")
        return float(_BINARY_OPERATORS[type(node.op)](left, right))
    raise ValueError("unsupported numeric expression")


def _solve_state_operations(
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    state = deepcopy(contract.get("initial_state"))
    operations = contract.get("operations")
    if not isinstance(operations, list) or len(operations) > 50:
        return None
    trace: list[dict[str, Any]] = []
    for index, operation_spec in enumerate(operations):
        if not isinstance(operation_spec, dict):
            return None
        operation_name = str(operation_spec.get("op") or "")
        if operation_name == "append" and isinstance(state, list):
            state.append(deepcopy(operation_spec.get("value")))
        elif operation_name == "pop" and isinstance(state, list) and state:
            state.pop()
        elif operation_name == "set" and isinstance(state, dict):
            key = str(operation_spec.get("key") or "")
            if not key:
                return None
            state[key] = deepcopy(operation_spec.get("value"))
        elif operation_name == "delete" and isinstance(state, dict):
            state.pop(str(operation_spec.get("key") or ""), None)
        else:
            return None
        trace.append({
            "title": f"执行步骤 {index + 1}",
            "explanation": f"执行公开操作 {operation_name}",
            "result": repr(state),
        })
    return {
        "answer": state,
        "summary": "依次执行题面公开的状态操作并记录状态变化。",
        "work": trace,
        "checks": ["从初始状态重新执行全部公开操作"],
        "option_analysis": [],
        "common_errors": [],
        "solver_attested": True,
        "solver_kind": "state_operations",
    }


def _complete_solution(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("answer") is not None
        and str(value.get("summary") or "").strip()
        and isinstance(value.get("work"), list)
        and value.get("work")
        and isinstance(value.get("checks"), list)
        and value.get("checks")
        and value.get("solver_attested") is True
    )


__all__ = ["IndependentSolverRegistry"]
