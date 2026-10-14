from copy import deepcopy

import pytest

from assessment_independent_solvers import IndependentSolverRegistry
from assessment_orchestrator import _local_solver_applicable


def public_question(count=4):
    return {
        "input_contract": {"mode": "structured_fields", "fields": [
            {"field_id": name, "required": True} for name in ["premises", "derivation", "conclusion"]
        ]},
        "stimulus": {"rendered_text": (
            "动态数组初始状态 $n_0=1,c_0=1$。候选势函数 $\\Phi(n,c)=2n-c-1$。"
            f"连续执行{count}次追加操作。追加前若n=c，先将容量加倍并复制原有n个元素，再插入1个元素。"
            "实际成本为复制的元素数加插入1个元素，势函数取操作结束后的状态。"
        )},
        "task": {"rendered_text": "给出每一步状态及势函数取值，验证合法性并求总实际成本。"},
        # An answer suggested by the generator is not independent evidence.
        "solver_contract": {"kind": "numeric_expression", "expression": "7"},
    }


def test_complete_potential_solution_comes_from_public_states_not_generator_expression():
    spec = public_question()
    assert _local_solver_applicable(spec)
    result = IndependentSolverRegistry.with_builtin_solvers().solve(spec)
    assert result is not None
    assert result["solver_kind"] == "dynamic_array_potential"
    evidence = result["solver_evidence"]
    assert [row["actual_cost"] for row in evidence["states"]] == [2, 3, 1, 5]
    assert [row["potential"] for row in evidence["states"]] == [1, 1, 3, 1]
    assert [row["delta"] for row in evidence["states"]] == [1, 0, 2, -2]
    assert evidence["total_actual"] == 11
    assert evidence["total_amortized"] == 12
    assert "11" in result["answer"]["conclusion"]
    assert "ΔΦ" in result["answer"]["derivation"]
    assert set(result["answer"]) == {"premises", "derivation", "conclusion"}


def test_equivalent_public_wording_is_recognized_without_changing_the_model():
    spec = public_question()
    spec["stimulus"]["rendered_text"] = (
        "动态数组初始状态s0：元素数n_0=1，容量c_0=1。候选势函数Φ(s)=2n-c-1。"
        "规则：追加时若n≥c，先倍增容量并复制旧n个元素，再插入新元素。实际成本t_i为复制数加1。"
        "执行4次追加，状态取操作结束后。"
    )
    spec["task"]["rendered_text"] = "计算Φ(s0)；验证该势函数在s0至s4上的合法性；计算总实际成本与势能差。"
    result = IndependentSolverRegistry.with_builtin_solvers().solve(spec)
    assert result["solver_kind"] == "dynamic_array_potential"
    assert result["solver_evidence"]["total_actual"] == 11


@pytest.mark.parametrize("count", [1, 2, 3, 5, 10, 32])
def test_bounded_append_sequences_satisfy_capacity_and_telescoping_invariants(count):
    evidence = IndependentSolverRegistry.with_builtin_solvers().solve(public_question(count))["solver_evidence"]
    assert all(row["size"] <= row["capacity"] and row["potential"] >= 0 for row in evidence["states"])
    assert evidence["total_actual"] == evidence["total_amortized"] - evidence["states"][-1]["potential"]
    assert evidence["total_amortized"] == 3 * count


@pytest.mark.parametrize(("old", "new"), [
    ("n_0=1", "n_0=0"), ("2n-c-1", "2n-c-10"), ("容量加倍", "容量增加1"),
    ("连续执行4次追加", "连续执行40次追加"), ("动态数组", "动态数组并允许删除和缩容"),
    ("实际成本为", "每次追加有额外2单位成本，实际成本为"),
])
def test_unsupported_public_conditions_do_not_trust_a_claimed_solver_contract(old, new):
    spec = deepcopy(public_question())
    spec["stimulus"]["rendered_text"] = spec["stimulus"]["rendered_text"].replace(old, new)
    spec["solver_contract"] = {"kind": "dynamic_array_potential", "append_count": 4}
    assert IndependentSolverRegistry.with_builtin_solvers().solve(spec) is None
