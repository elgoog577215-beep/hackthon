"""K1: 最深一层提示与私有解答的重合度检查（常驻回归）。

三级提示本身已实现且质量不错，但编译期的泄漏检查此前只做一件事：把私有解答
的最终答案当字符串在提示里找一遍。这漏掉了更常见的失败形态——第三级提示把
整条推导链复述了一遍，只是小心地没写出最后那个数。

本文件锁住两件事：
1. 合法提示不能被误伤——提示本来就与私有解答同源，共享方法词汇是设计使然；
2. 两种明确的泄漏必须被拦下——直接给出最终答案，或复现整条推导。
"""

from hint_leakage import coverage_ratio, measure_deepest_hint_overlap
from practice_contracts import enrich_question_contract
from question_bank import _hint_contract, _solution_graph_hint_contract


def _envelope():
    return {
        "solution_revision_id": "sr-1",
        "solution_graph": {
            "schema_version": "solution_graph_v1",
            "steps": [
                {
                    "step_id": "s1",
                    "action": "把 f(x)=x^2-4x+3 配方为 (x-2)^2-1",
                    "check": "展开后与原式一致",
                },
                {
                    "step_id": "s2",
                    "action": "读出顶点坐标 (2,-1)",
                    "check": "顶点横坐标等于 -b/2a",
                },
                {
                    "step_id": "s3",
                    "action": "由开口向上得最小值为 -1",
                    "check": "代入 x=2 复核",
                },
            ],
        },
        "legacy_answer_spec": {"correct_answer": "最小值为 -1"},
    }


def _item():
    return {
        "prompt": "求函数 f(x)=x^2-4x+3 的最小值。",
        "question_spec": {
            "schema_version": "question_spec_v2",
            "stimulus": {"rendered_text": "f(x)=x^2-4x+3"},
        },
    }


# --- 度量本身 ---------------------------------------------------------------


def test_coverage_ratio_measures_verbatim_containment():
    assert coverage_ratio("读出顶点坐标 (2,-1)", "先读出顶点坐标 (2,-1)，再继续") == 1.0
    assert coverage_ratio("读出顶点坐标 (2,-1)", "这道题需要配方") == 0.0
    # 空片段不制造信号。
    assert coverage_ratio("", "任意内容") == 0.0


def test_overlap_reports_when_there_is_nothing_to_measure():
    result = measure_deepest_hint_overlap([], _envelope())
    assert result["measured"] is False
    assert result["leaked"] is False


def test_overlap_uses_the_deepest_level_not_the_first():
    envelope = _envelope()
    levels = [
        {"level": 1, "content": "先想想这是什么函数。"},
        {"level": 3, "content": "把 f(x)=x^2-4x+3 配方为 (x-2)^2-1。"},
    ]
    result = measure_deepest_hint_overlap(levels, envelope)
    assert result["deepest_level"] == 3
    assert result["reproduced_step_count"] == 1


# --- 合法提示不得被误伤 ------------------------------------------------------


def test_real_solution_graph_generator_output_is_not_flagged():
    """真实生成器产出的三级提示与解答同源，但绝不能因此被判泄漏。"""
    contract = _solution_graph_hint_contract(_item(), _envelope())
    overlap = contract["leakage_check"]["deepest_hint_overlap"]

    assert contract["leakage_check"]["passed"] is True
    assert overlap["leaked"] is False
    # 它确实引用了推导中的一步——这是局部脚手架该做的事，不是泄漏。
    assert overlap["reproduced_step_count"] < overlap["solution_step_count"]


def test_scaffold_that_only_names_the_method_is_not_flagged():
    """只点出方法、不代做推导的提示必须通过。"""
    levels = [{
        "level": 3,
        "content": "先回顾配方法的目的：把二次式写成完全平方加常数。"
                   "你自己动手配一次，再看顶点告诉你什么。",
    }]
    result = measure_deepest_hint_overlap(levels, _envelope())

    assert result["leaked"] is False
    assert result["reproduced_step_count"] == 0


def test_partial_derivation_is_measured_but_not_auto_failed():
    """复述部分步骤是局部脚手架的正常形态：如实计量，不自动判失败。"""
    levels = [{
        "level": 3,
        "content": "把 f(x)=x^2-4x+3 配方为 (x-2)^2-1，然后读出顶点坐标 (2,-1)。"
                   "最后一步请你自己判断。",
    }]
    result = measure_deepest_hint_overlap(levels, _envelope())

    assert result["reproduced_step_count"] == 2
    assert result["solution_step_count"] == 3
    # 留了最后一步给学生，因此不算泄漏；但重合度如实记录，供人工复核。
    assert result["reproduces_whole_derivation"] is False
    assert result["leaked"] is False
    assert result["reproduced_step_ratio"] > 0.5


# --- 两种明确泄漏必须被拦下 --------------------------------------------------


def test_hint_that_hands_over_the_final_answer_is_flagged():
    levels = [{
        "level": 3,
        "content": "别绕了，这道题最小值为 -1，直接写上即可。",
    }]
    result = measure_deepest_hint_overlap(levels, _envelope())

    assert result["reveals_final_answer"] is True
    assert result["leaked"] is True


def test_hint_that_reproduces_the_whole_derivation_is_flagged():
    """这是旧检查看不见的形态：整条推导都复述了，只是没写出最后那个数。"""
    levels = [{
        "level": 3,
        "content": "把 f(x)=x^2-4x+3 配方为 (x-2)^2-1，读出顶点坐标 (2,-1)，"
                   "由开口向上得最小值为 -1，全部过程就是这样。",
    }]
    result = measure_deepest_hint_overlap(levels, _envelope())

    assert result["reproduces_whole_derivation"] is True
    assert result["leaked"] is True


def test_compile_gate_rejects_a_hint_that_restates_the_private_derivation():
    """编译期门禁必须真的拦下来——这条在改动前是通过的。"""
    item = {
        "prompt": "求函数 f(x)=x^2-4x+3 的最小值。",
        "answer_spec": {
            "correct_answer": "-1",
            "solution_spec": {
                "final_answer": "-1",
                "steps": [
                    "配方得 f(x)=(x-2)^2-1",
                    "顶点在 x=2 处",
                    "最小值为 -1",
                ],
            },
        },
        "question_spec": {"hint_contract": {"levels": [
            {"level": 1, "content": "先看这是什么类型的函数。"},
            {"level": 2, "content": "考虑配方法。"},
            {"level": 3, "content": "配方得 f(x)=(x-2)^2-1，顶点在 x=2 处，"
                                    "最小值为 -1，抄下来即可。"},
        ]}},
    }
    contract = _hint_contract(item)

    assert contract["leakage_check"]["passed"] is False
    assert contract["leakage_check"]["deepest_hint_overlap"]["leaked"] is True


def test_legacy_contract_path_also_carries_the_overlap_measurement():
    """legacy 路径（practice_contracts）也必须带上这条计量，不能有后门。"""
    question = enrich_question_contract({
        "asset_id": "q-legacy",
        "revision_id": "qr-legacy",
        "node_id": "n1",
        "question_type": "short_answer",
        "prompt": "解释向量的两个基本属性。",
        "answer_spec": {
            "type": "exact",
            "correct_answer": "大小和方向",
            "criteria": ["说明大小", "说明方向"],
            "pass_score": 70,
        },
    })
    leakage = (question.get("hint_contract") or {}).get("leakage_check") or {}

    assert "deepest_hint_overlap" in leakage
    assert leakage["passed"] is True


def test_short_final_answers_do_not_create_false_leakage():
    """极短答案（"3"、"B"）与普通行文碰撞太容易，不能当泄漏信号。"""
    envelope = {
        "solution_graph": {"steps": [
            {"step_id": "s1", "action": "统计满足条件的元素个数"},
        ]},
        "legacy_answer_spec": {"correct_answer": "3"},
    }
    levels = [{"level": 3, "content": "把符合条件的元素逐个圈出来，再数一遍。"}]
    result = measure_deepest_hint_overlap(levels, envelope)

    assert result["reveals_final_answer"] is False
    assert result["leaked"] is False
