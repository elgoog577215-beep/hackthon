"""判分扰动矩阵：预先声明的作答变形与预期分。

## 这份东西是什么，不是什么

它是**我（AI）事先写下的判分意图**：给定一道题，构造若干组作答，并声明每组
应该得多少分。跑完之后拿判分器的实际输出与这些预期比对，得到的指标叫
**预期一致率（expected-agreement）**。

**它不是人工判分。** 预期分由我编写、未经教研复核，所以：

- 不得把这个指标称为「人工一致率」或「人工判分一致率」；
- 清单 H1a/H1b 要求的「判分器与人工判分一致率 > 90%」**不能**用它顶替，
  那一条的状态是「待教研复核」；
- 它能证明的是「判分器行为与预先声明的口径一致」，证明不了「这个口径符合
  教师的判断」。后者只有人看题才能定。

这份矩阵同时被 `scripts/question_form_generation_audit.py` 与
`backend/tests/test_question_form_grading_matrix.py` 引用，**共用一份定义**，
避免脚本与测试各写一套后悄悄漂移。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PERTURBATION_SCHEMA = "grading_perturbation_v1"


def _option_ids(question: dict[str, Any]) -> list[str]:
    return [
        str(option.get("id") or "")
        for option in question.get("options") or []
        if isinstance(option, dict) and str(option.get("id") or "")
    ]


def choice_cases(
    question: dict[str, Any],
    correct_ids: list[str],
) -> list[dict[str, Any]]:
    """选择题（单选 / 多选 / 判断）的作答用例与预期分。

    预期分口径与已确认的部分给分方案一致：默认全对才给分；错选一律 0；
    部分给分只在题目显式开启时按漏选比例给。
    """
    ids = _option_ids(question)
    correct = [value for value in correct_ids if value in ids]
    wrong = [value for value in ids if value not in correct]
    selection = (question.get("input_contract") or {}).get("selection") or {}
    partial = bool(selection.get("partial_credit"))
    cases: list[dict[str, Any]] = []

    if not correct:
        return cases

    cases.append({
        "case_id": "all_correct",
        "description": "选中全部正确项",
        "payload": {"selected_option_ids": list(correct)},
        "expected_score": 100,
        "expected_passed": True,
        "rationale": "完全符合标准答案",
    })

    if wrong:
        cases.append({
            "case_id": "wrong_only",
            "description": "只选一个错误项",
            "payload": {"selected_option_ids": [wrong[0]]},
            "expected_score": 0,
            "expected_passed": False,
            "rationale": "错选即 0（已确认口径）",
        })
        cases.append({
            "case_id": "correct_plus_wrong",
            "description": "正确项全选但多选了一个错误项",
            "payload": {
                "selected_option_ids": [*correct, wrong[0]],
            },
            "expected_score": 0,
            "expected_passed": False,
            "rationale": "错选一个即 0，与漏选性质不同",
        })

    if len(correct) > 1:
        missing_one = correct[:-1]
        expected_partial = (
            int(round(100.0 * len(missing_one) / len(correct)))
            if partial
            else 0
        )
        cases.append({
            "case_id": "missing_one_correct",
            "description": "漏选一个正确项",
            "payload": {"selected_option_ids": list(missing_one)},
            "expected_score": expected_partial,
            "expected_passed": False,
            "rationale": (
                "开启部分给分后按漏选比例给"
                if partial
                else "默认档全对才给分，漏选即 0"
            ),
        })

    cases.append({
        "case_id": "empty",
        "description": "空作答",
        "payload": {"selected_option_ids": []},
        "expected_score": 0,
        "expected_passed": False,
        "rationale": "没有作答不得分",
    })
    return cases


def fill_blank_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """填空题的作答用例与预期分。

    含「等价但写法不同」一组——那正是 H1b 验收关心的点（单位换算、代数等价、
    大小写与空白差异不应判错）。
    """
    blanks = contract.get("blanks") or []
    if not blanks:
        return []
    total_weight = sum(float(blank.get("score_weight") or 1.0) for blank in blanks)
    all_correct = {
        str(blank["blank_id"]): deepcopy(blank["answer"])
        for blank in blanks
    }
    cases: list[dict[str, Any]] = [{
        "case_id": "all_correct",
        "description": "每空都填标准答案",
        "payload": {"blanks": all_correct},
        "expected_score": 100.0,
        "expected_passed": True,
        "rationale": "完全符合标准答案",
    }]

    first = blanks[0]
    first_id = str(first["blank_id"])
    first_weight = float(first.get("score_weight") or 1.0)
    remaining = round(
        100.0 * (total_weight - first_weight) / total_weight, 2,
    ) if total_weight else 0.0

    wrong_first = dict(all_correct)
    wrong_first[first_id] = "__明显错误的答案__"
    cases.append({
        "case_id": "first_blank_wrong",
        "description": "第一空填错，其余正确",
        "payload": {"blanks": wrong_first},
        "expected_score": remaining,
        "expected_passed": False,
        "rationale": "按空位权重扣掉第一空",
    })

    skipped_first = {
        key: value for key, value in all_correct.items() if key != first_id
    }
    cases.append({
        "case_id": "first_blank_unanswered",
        "description": "第一空不作答，其余正确",
        "payload": {"blanks": skipped_first},
        "expected_score": remaining,
        "expected_passed": False,
        "rationale": "未作答与答错同样不得分，但要能区分 answered=False",
    })

    # 等价写法：只有该空声明了可接受写法时才构造，不自己编等价答案
    equivalent_blank = next(
        (
            blank for blank in blanks
            if blank.get("acceptable_answers")
        ),
        None,
    )
    if equivalent_blank is not None:
        equivalent = dict(all_correct)
        equivalent[str(equivalent_blank["blank_id"])] = deepcopy(
            equivalent_blank["acceptable_answers"][0]
        )
        cases.append({
            "case_id": "equivalent_wording",
            "description": "某空使用题目自己声明的等价写法",
            "payload": {"blanks": equivalent},
            "expected_score": 100.0,
            "expected_passed": True,
            "rationale": "等价但写法不同不应判错（H1b 验收重点）",
        })

    cases.append({
        "case_id": "empty",
        "description": "全部不作答",
        "payload": {"blanks": {}},
        "expected_score": 0.0,
        "expected_passed": False,
        "rationale": "没有作答不得分",
    })
    return cases


__all__ = [
    "PERTURBATION_SCHEMA",
    "choice_cases",
    "fill_blank_cases",
]
