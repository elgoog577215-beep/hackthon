"""遗留键不得关掉名字键关系校验（需求 A3 调查衍生）。

A3 要查的是"已实现未接线的关系规划批次为何被弃用"。查清之后（见 NOTES 3.11：
提交 3eb73c84 主动收敛 AI 主链，openspec 现行条款仍禁止用模型重判确定性结果）
顺带暴露一个真实缺陷，值得单独锁定：

`_knowledge_contract_issues` 里那条为 ID 键关系写的分支是 `if id_relations or
relation_decisions:` → `return issues`。`relation_decisions` 读的是课程信封上
持久化的 `knowledge_relation_decisions`（`task_manager.py` 的透传键名单里就有
这一项），而 2026-07-20 之前生成的课程都带着这个键。

后果不是"多报一条 issue"，而是**整段名字键关系校验被跳过**：六类白名单
（`plan:invalid_knowledge_relation`）、端点检查、缺理由检查，以及 `derives` 缺
`derivation_steps` / `contrasts_with` 缺 `distinction` 这两条——正好是 A1 改
prompt、A2 加软门槛想要守住的东西。一门课只要残留这个空壳键，门就静默关掉，
模型写 `related` 也能过。

判据因此是"同一份计划，加不加遗留键都必须报出同样的关系问题"。
"""

from __future__ import annotations

from typing import Any

from course_generation.workflow import _knowledge_contract_issues

LEGACY_DECISIONS = [{
    "knowledge_id": "ckp_legacy_only_in_old_courses",
    "decision": "course_entry",
    "reason": "2026-07-20 之前生成的课程留下的逐点决定",
}]


def _plan(*, legacy_decisions: bool, relation: dict[str, Any]) -> dict[str, Any]:
    points = [
        {
            "name": "一次函数",
            "statement": "形如 y=kx+b（k≠0）的函数。",
            "entry_reason": "课程入口知识",
            "relations": [relation],
        },
        {
            "name": "斜率",
            "statement": "k 决定直线的倾斜程度。",
            "entry_reason": "课程入口知识",
        },
    ]
    plan: dict[str, Any] = {
        "chapters": [{
            "chapter_number": 1,
            "title": "第一章 线性关系",
            "sections": [{
                "node_id": "L2-1-1",
                "title": "一次函数与斜率",
                "knowledge_structure": [{
                    "concept_group": "函数基础",
                    "knowledge_points": points,
                }],
            }],
        }],
    }
    if legacy_decisions:
        plan["knowledge_relation_decisions"] = LEGACY_DECISIONS
    return plan


def _codes(plan: dict[str, Any]) -> list[str]:
    return [
        str(issue.get("code") or "")
        for issue in _knowledge_contract_issues(plan, plan["chapters"])
    ]


def _relation_codes(plan: dict[str, Any]) -> set[str]:
    return {code for code in _codes(plan) if "relation" in code or "derivation" in code}


# --- 六类白名单不得被遗留键关掉 -------------------------------------------


def test_invalid_relation_type_is_caught_without_the_legacy_key() -> None:
    """基线：没有遗留键时，编造的关系类型会被拦下。"""
    plan = _plan(
        legacy_decisions=False,
        relation={"target_name": "斜率", "relation_type": "related", "reason": "编的类型"},
    )

    assert "plan:invalid_knowledge_relation" in _codes(plan)


def test_invalid_relation_type_is_still_caught_with_the_legacy_key() -> None:
    """真正的判据：残留遗留键不得让白名单静默失效。"""
    plan = _plan(
        legacy_decisions=True,
        relation={"target_name": "斜率", "relation_type": "related", "reason": "编的类型"},
    )

    assert "plan:invalid_knowledge_relation" in _codes(plan)


def test_the_legacy_key_does_not_change_which_relation_issues_are_reported() -> None:
    """同一份计划，加不加遗留键，关系类问题必须一致。"""
    relation = {"target_name": "斜率", "relation_type": "related", "reason": "编的类型"}

    plain = _relation_codes(_plan(legacy_decisions=False, relation=relation))
    legacy = _relation_codes(_plan(legacy_decisions=True, relation=relation))

    assert plain, "基线必须真的报出关系问题，否则这个对比没有意义"
    assert plain <= legacy, f"遗留键关掉了这些检查：{sorted(plain - legacy)}"


# --- A1/A2 守的那两个必填字段同样不得被关掉 -------------------------------


def test_derives_missing_steps_is_caught_with_the_legacy_key() -> None:
    """`derives` 缺 `derivation_steps`：A1 prompt 明写、编译器整条丢弃。"""
    plan = _plan(
        legacy_decisions=True,
        relation={"target_name": "斜率", "relation_type": "derives", "reason": "可由定义推出"},
    )

    assert "plan:derivation_missing_steps" in _codes(plan)


def test_contrast_missing_distinction_is_caught_with_the_legacy_key() -> None:
    """`contrasts_with` 缺 `distinction`：同上，缺了编译期整条丢弃且无提示。"""
    plan = _plan(
        legacy_decisions=True,
        relation={"target_name": "斜率", "relation_type": "contrasts_with", "reason": "学生易混"},
    )

    assert "plan:contrast_missing_distinction" in _codes(plan)


def test_relation_missing_reason_is_caught_with_the_legacy_key() -> None:
    """没有判定理由的关系无法复核，遗留键不得让它蒙混过关。"""
    plan = _plan(
        legacy_decisions=True,
        relation={"target_name": "斜率", "relation_type": "prerequisite", "reason": "  "},
    )

    assert "plan:relation_missing_reason" in _codes(plan)


# --- 遗留键本身的校验必须保留 ---------------------------------------------


def test_legacy_decisions_are_still_validated_on_their_own_terms() -> None:
    """修法不是"忽略遗留键"：指向不存在知识点的遗留决定仍要报出来。"""
    plan = _plan(
        legacy_decisions=True,
        relation={"target_name": "斜率", "relation_type": "prerequisite", "reason": "先学斜率"},
    )

    assert "course_relations:invalid_decision_target" in _codes(plan)
