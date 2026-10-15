import json

import pytest

from assessment_independent_solvers import IndependentSolverRegistry


@pytest.mark.parametrize(("expression", "answer"), [
    ("-(4)+6", 2), ("+4", 4), ("3.5*2", 7), ("9//2", 4), ("9%4", 1), ("2**3", 8), ("1/2", .5),
])
def test_public_arithmetic_is_computed_with_bounded_operators(expression, answer):
    result = IndependentSolverRegistry.with_builtin_solvers().solve({
        "task": {"rendered_text": "计算 " + expression},
        "solver_contract": {"kind": "numeric_expression", "expression": expression},
    })
    assert result["answer"] == answer


@pytest.mark.parametrize("expression", ["1/0", "2**11", "10**10*10**10", "1+" * 35 + "1", "1+" * 101 + "1"])
def test_arithmetic_outside_safe_budget_declines_without_executing_code(expression):
    assert IndependentSolverRegistry.with_builtin_solvers().solve({
        "task": {"rendered_text": "计算 " + expression},
        "solver_contract": {"kind": "numeric_expression", "expression": expression},
    }) is None


@pytest.mark.parametrize(("initial", "operations", "expected"), [
    ([1], [{"op": "append", "value": 2}, {"op": "pop"}], [1]),
    ({"a": 1}, [{"op": "set", "key": "b", "value": 2}, {"op": "delete", "key": "a"}], {"b": 2}),
])
def test_state_solver_uses_only_an_exact_public_operation_contract(initial, operations, expected):
    public = {"initial_state": initial, "operations": operations}
    spec = {"stimulus": {"rendered_text": "```json\n" + json.dumps(public) + "\n```"},
            "solver_contract": {"kind": "state_operations", **public}}
    registry = IndependentSolverRegistry.with_builtin_solvers()
    assert registry.solve(spec)["answer"] == expected
    spec["solver_contract"]["initial_state"] = {"injected": "not public"}
    assert registry.solve(spec) is None


@pytest.mark.parametrize("public", [
    {"initial_state": [], "operations": [{"op": "pop"}]},
    {"initial_state": {}, "operations": [{"op": "set", "key": ""}]},
    {"initial_state": [], "operations": []},
    {"initial_state": [], "operations": [None]},
    {"initial_state": [], "operations": [{"op": "exec", "value": "not executed"}]},
    {"initial_state": [], "operations": [{"op": "append", "value": 1}] * 51},
])
def test_invalid_public_state_programs_are_not_attested(public):
    assert IndependentSolverRegistry.with_builtin_solvers().solve({
        "stimulus": {"rendered_text": "```json\n" + json.dumps(public) + "\n```"},
        "solver_contract": {"kind": "state_operations", **public},
    }) is None
