"""A bounded proof-producing solver for one explicitly supported public model.

Only append-only doubling, n0=c0=1 and Phi=2n-c-1 are supported. Other
conditions return None and use the independent model; no generated answer or
generator-supplied solver parameters are treated as evidence.
"""
from __future__ import annotations

import re
from typing import Any


def public_dynamic_array_inputs(spec: dict[str, Any]) -> dict[str, int] | None:
    response = spec.get("input_contract") or {}
    if response.get("mode") != "structured_fields":
        return None
    fields = response.get("fields") or []
    if not all(isinstance(f, dict) for f in fields) or {f.get("field_id") for f in fields} != {"premises", "derivation", "conclusion"}:
        return None
    stimulus = str((spec.get("stimulus") or {}).get("rendered_text") or "")
    task = str((spec.get("task") or {}).get("rendered_text") or "")
    text = re.sub(r"\s+", "", stimulus + "\n" + task).casefold()
    text = text.replace("\\phi", "φ").replace("$", "").replace("{", "").replace("}", "").replace("−", "-")
    if "动态数组" not in text or any(word in text for word in ("删除", "缩容", "弹出", "另一势函数", "ψ", "额外", "附加成本", "不倍增", "不采用倍增")):
        return None
    initial = bool(re.search(r"n_?0=1(?!\d)", text) and re.search(r"c_?0=1(?!\d)", text))
    initial = initial or bool(re.search(r"初始[^。]{0,60}n=c=1(?!\d)", text))
    if not initial:
        return None
    if not re.search(r"(?:φ|phi)\([^)]*\)=2\*?n-c-1(?![0-9nc+\-*/^])", text):
        return None
    if not any(rule in text for rule in ("容量加倍", "容量翻倍", "倍增容量", "c=2c")):
        return None
    if not ("复制" in text and "实际成本" in text and re.search(r"(?:元素数|复制数)加(?:插入)?1|复制原有n个元素.*插入1个元素", text)):
        return None
    if not any(rule in text for rule in ("操作结束", "操作完成后", "追加结束", "追加操作结束")):
        return None
    if "状态" not in text or not all(word in task for word in ("合法", "总实际成本")):
        return None
    match = re.search(r"(?:连续(?:执行|进行)?|执行|进行)(\d+)次(?:追加|append)", text)
    if not match:
        match = re.search(r"(\d+)次连续(?:追加|append)", text)
    if not match or len(match[1]) > 2 or not 1 <= int(match[1]) <= 32:
        return None
    return {"append_count": int(match[1])}


def solve_dynamic_array_potential(contract: dict[str, Any]) -> dict[str, Any] | None:
    count = contract.get("append_count")
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 32:
        return None
    n = capacity = 1
    potential = 0
    states = []
    for step in range(1, count + 1):
        prior = potential
        cost = 1
        if n == capacity:
            cost += n
            capacity *= 2
        n += 1
        potential = 2 * n - capacity - 1
        states.append({"step": step, "size": n, "capacity": capacity,
                       "potential": potential, "delta": potential - prior,
                       "actual_cost": cost, "amortized_cost": cost + potential - prior})
    actual = sum(s["actual_cost"] for s in states)
    amortized = sum(s["amortized_cost"] for s in states)
    assert all(s["size"] <= s["capacity"] and s["potential"] >= 0 for s in states)
    assert actual == amortized - potential and amortized == 3 * count
    table = "|操作|n|c|实际成本|Φ|ΔΦ|摊还成本|\n|---|---|---|---|---|---|---|\n" + "\n".join(
        "|" + "|".join(str(s[key]) for key in ["step", "size", "capacity", "actual_cost", "potential", "delta", "amortized_cost"]) + "|"
        for s in states
    )
    legality = (
        "初始Φ(1,1)=0。只追加不删除时，容量至少为2的可达状态满足c/2<n≤c，"
        "故Φ=2n-c-1≥1；初始状态Φ=0，所以所有可达状态的势能非负。"
        "合法性约束的是Φ，而不是ΔΦ；扩容可以释放此前积累的势能，允许负增量。"
    )
    derivation = (
        "非扩容时ΔΦ=2、实际成本1，摊还成本3。扩容前n=c，完整追加后为(c+1,2c)，"
        "ΔΦ=2-c，实际成本c+1，摊还成本仍为3。"
        f"望远镜求和：Σt=Σ(t+ΔΦ)-Φ末+Φ初={amortized}-{potential}+0={actual}。"
        "对任意k次追加，总实际成本≤3k且至少为k，故总成本为Θ(k)。"
    )
    conclusion = f"候选势函数合法；这{count}次追加的总实际成本为{actual}，总摊还成本为{amortized}，最终势能为{potential}。"
    return {
        "answer": {"premises": table + "\n" + legality, "derivation": derivation, "conclusion": conclusion},
        "summary": conclusion,
        "work": [
            {"title": "核对初始条件", "explanation": "n0=c0=1；Φ0=2×1-1-1=0。", "result": "Φ0=0"},
            {"title": "逐步模拟完整追加", "explanation": "每步先检查是否已满，再扩容复制，最后插入；势能取操作结束状态。", "result": table},
            {"title": "验证可达状态上的合法性", "explanation": legality, "result": "所有可达状态Φ≥0；不要求ΔΦ≥0。"},
            {"title": "独立核对总成本", "explanation": derivation, "result": conclusion},
        ],
        "checks": ["逐行核对n≤c、Φ=2n-c-1及实际成本", f"成本直接求和={actual}；望远镜求和={amortized}-{potential}={actual}"],
        "option_analysis": [], "common_errors": ["把操作前与操作后的容量混用", "误要求每步势能增量非负"],
        "solver_attested": True, "solver_kind": "dynamic_array_potential",
        "solver_evidence": {"states": states, "total_actual": actual, "total_amortized": amortized},
    }
