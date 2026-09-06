"""H1a：多选与判断题，含部分给分口径。

部分给分口径由用户确认，不是我自己定的：
  默认全对才给分（与现状一致，零行为变更）；题目可显式开启部分给分。
  开启后「每漏选按比例扣、错选一个即 0」。

  正确 {A,C} 选 {A}     -> 50（漏 1/2）
  正确 {A,C} 选 {A,C}   -> 100
  正确 {A,C} 选 {A,B}   -> 0（错选 B）
  正确 {A,C} 选 {A,B,C} -> 0（错选 B）
"""
from __future__ import annotations

from question_choice_grading import (
    correct_option_ids,
    grade_choice,
    is_choice_question,
    is_multiple_choice,
    selected_option_ids,
)


def _question(*, multiple=False, partial=False, options=None, **extra):
    question = {
        "input_contract": {
            "mode": "choice",
            "selection": {"multiple": multiple, "partial_credit": partial},
        },
        "options": options if options is not None else [
            {"id": "A", "text": "甲"},
            {"id": "B", "text": "乙"},
            {"id": "C", "text": "丙"},
            {"id": "D", "text": "丁"},
        ],
    }
    question.update(extra)
    return question


# --- 口径表：逐行对应用户确认的四种情形 -------------------------------------


def test_partial_credit_scoring_table() -> None:
    spec = {"correct_option_ids": ["A", "C"]}
    question = _question(multiple=True, partial=True)

    def score(selected):
        return grade_choice(
            question, spec, {"selected_option_ids": selected},
        )["score"]

    assert score(["A"]) == 50           # 漏 1/2
    assert score(["A", "C"]) == 100     # 全对
    assert score(["A", "B"]) == 0       # 错选 B
    assert score(["A", "B", "C"]) == 0  # 错选 B


def test_default_keeps_all_or_nothing() -> None:
    """默认不开部分给分，行为与改动前一致。"""
    spec = {"correct_option_ids": ["A", "C"]}
    question = _question(multiple=True, partial=False)

    assert grade_choice(question, spec, {"selected_option_ids": ["A"]})["score"] == 0
    assert grade_choice(
        question, spec, {"selected_option_ids": ["A", "C"]},
    )["score"] == 100


def test_partial_credit_needs_multiple_choice() -> None:
    """单选题开了 partial_credit 也不生效——单选没有"漏选"可言。"""
    question = _question(multiple=False, partial=True)
    result = grade_choice(
        question, {"correct_option_id": "A"}, {"selected_option_id": "B"},
    )
    assert result["score"] == 0
    assert result["choice_result"]["partial_credit"] is False


def test_passing_still_requires_everything_correct() -> None:
    """部分给分给的是分数，不是通过。50 分不算掌握。"""
    question = _question(multiple=True, partial=True)
    result = grade_choice(
        question, {"correct_option_ids": ["A", "C"]},
        {"selected_option_ids": ["A"]},
    )
    assert result["score"] == 50
    assert result["passed"] is False


def test_three_of_four_missing_one_scores_by_proportion() -> None:
    question = _question(multiple=True, partial=True)
    result = grade_choice(
        question, {"correct_option_ids": ["A", "B", "C"]},
        {"selected_option_ids": ["A", "B"]},
    )
    assert result["score"] == 67


# --- 判定细节 ---------------------------------------------------------------


def test_selection_is_order_independent() -> None:
    question = _question(multiple=True)
    result = grade_choice(
        question, {"correct_option_ids": ["A", "C"]},
        {"selected_option_ids": ["C", "A"]},
    )
    assert result["passed"] is True


def test_missed_and_wrong_are_reported_separately() -> None:
    """漏选与错选要能分开看——它们的教学含义不同。"""
    question = _question(multiple=True, partial=True)
    result = grade_choice(
        question, {"correct_option_ids": ["A", "C"]},
        {"selected_option_ids": ["A", "B"]},
    )
    detail = result["choice_result"]
    assert detail["missed_option_ids"] == ["C"]
    assert detail["wrong_option_ids"] == ["B"]
    assert "错选" in result["feedback"]


def test_empty_submission_scores_zero() -> None:
    question = _question(multiple=True, partial=True)
    for payload in ({}, {"selected_option_ids": []}, {"selected_option_ids": None}):
        result = grade_choice(question, {"correct_option_ids": ["A", "C"]}, payload)
        assert result["score"] == 0
        assert result["passed"] is False


def test_correct_ids_read_from_option_flags_when_spec_is_silent() -> None:
    question = _question(multiple=True, options=[
        {"id": "A", "text": "甲", "is_correct": True},
        {"id": "B", "text": "乙"},
        {"id": "C", "text": "丙", "is_correct": True},
    ])
    assert correct_option_ids(question, {}) == {"A", "C"}


def test_selected_ids_accept_single_and_multi_field() -> None:
    assert selected_option_ids({"selected_option_id": "A"}) == {"A"}
    assert selected_option_ids({"selected_option_ids": ["A", "B"]}) == {"A", "B"}
    assert selected_option_ids({}) == set()


# --- 不误伤非选择题（我第一版就是在这里翻车的） -----------------------------


def test_text_questions_are_not_treated_as_choice() -> None:
    """填空/简答也有 correct_answer，不能因为"有标准答案"就按选项判。

    第一版我用"能否解析出正确选项"当判据，结果简答题的文本答案被当成选项 ID
    比较，全部判错——被既有的 test_practice_grading 用例抓住。
    """
    assert is_choice_question({}, {"correct_answer": "北京"}) is False
    assert is_choice_question(
        {"input_contract": {"mode": "short_text"}},
        {"correct_answer": "false"},
    ) is False


def test_choice_questions_are_recognised_by_structure() -> None:
    assert is_choice_question({"input_contract": {"mode": "choice"}}, {}) is True
    assert is_choice_question({"options": [{"id": "A"}]}, {}) is True
    assert is_choice_question({}, {"correct_option_ids": ["A", "B"]}) is True
    assert is_choice_question({}, {"correct_option_id": "A"}) is True


# --- 合同层：多选与判断能被表达出来 -----------------------------------------


def test_compiler_declares_multiple_when_the_answer_has_several_options() -> None:
    """改动前 selection 恒为 {"multiple": False}，多选在合同层表达不出来。"""
    from assessment_compiler import _apply_choice_selection

    contract = _apply_choice_selection(
        {"mode": "choice"},
        answer_spec={"correct_option_ids": ["A", "C"]},
        options=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
    )
    assert contract["selection"]["multiple"] is True
    # 部分给分默认关闭，由题目显式开启
    assert contract["selection"]["partial_credit"] is False


def test_compiler_keeps_single_choice_single() -> None:
    """把单选声明成多选会让学生以为可以多选，是另一种误导。"""
    from assessment_compiler import _apply_choice_selection

    contract = _apply_choice_selection(
        {"mode": "choice"},
        answer_spec={"correct_option_id": "A"},
        options=[{"id": "A"}, {"id": "B"}],
    )
    assert contract["selection"]["multiple"] is False


def test_compiler_marks_true_false_questions() -> None:
    from assessment_compiler import _apply_choice_selection

    contract = _apply_choice_selection(
        {"mode": "choice"},
        answer_spec={"correct_option_id": "A"},
        options=[{"id": "A", "text": "正确"}, {"id": "B", "text": "错误"}],
    )
    assert contract["selection"]["true_false"] is True
    assert contract["selection"]["multiple"] is False


def test_two_ordinary_options_are_not_marked_true_false() -> None:
    from assessment_compiler import _apply_choice_selection

    contract = _apply_choice_selection(
        {"mode": "choice"},
        answer_spec={"correct_option_id": "A"},
        options=[{"id": "A", "text": "熵增"}, {"id": "B", "text": "熵减"}],
    )
    assert "true_false" not in contract["selection"]


# --- 与 L2 的接口：错选了哪个干扰项 -----------------------------------------


def test_wrong_option_reports_its_misconception() -> None:
    question = _question(multiple=False, options=[
        {"id": "A", "text": "甲"},
        {"id": "B", "text": "乙", "misconception_ids": ["ckm_sign_flip"]},
    ])
    result = grade_choice(
        question, {"correct_option_id": "A"}, {"selected_option_id": "B"},
    )
    assert result["choice_result"]["misconception_ids"] == ["ckm_sign_flip"]


def test_undeclared_distractor_reports_nothing_rather_than_guessing() -> None:
    """干扰项没写明对应哪个易错点时返回空——那正是 L2 要暴露的问题，不能编。"""
    question = _question(multiple=False)
    result = grade_choice(
        question, {"correct_option_id": "A"}, {"selected_option_id": "B"},
    )
    assert result["choice_result"]["misconception_ids"] == []


def test_correct_answer_reports_no_misconception() -> None:
    question = _question(multiple=False, options=[
        {"id": "A", "text": "甲"},
        {"id": "B", "text": "乙", "misconception_ids": ["ckm_sign_flip"]},
    ])
    result = grade_choice(
        question, {"correct_option_id": "A"}, {"selected_option_id": "A"},
    )
    assert result["choice_result"]["misconception_ids"] == []


def test_is_multiple_choice_reads_the_contract() -> None:
    assert is_multiple_choice(_question(multiple=True)) is True
    assert is_multiple_choice(_question(multiple=False)) is False
    assert is_multiple_choice({}) is False


# --- 自查发现的回归：串形拆分不得打碎单值答案 -----------------------------


def test_string_split_does_not_shred_single_valued_answers() -> None:
    """按空白拆会把合法单值答案打碎，进而破坏「选项原文 -> id」映射。

    自查实测：`12 kJ` 曾被拆成 {12, kJ}，于是选项文本含空格时永远对不上。
    多选写成「A C」这种纯空格形式很少见，误拆单值答案的代价更大，
    所以只按显式列表分隔符拆。
    """
    from question_choice_grading import canonical_option_ids

    # 显式分隔符：拆
    assert canonical_option_ids("A、C") == {"A", "C"}
    assert canonical_option_ids("A,C") == {"A", "C"}
    assert canonical_option_ids("A;C") == {"A", "C"}

    # 含空格的单值：不拆
    assert canonical_option_ids("12 kJ") == {"12 kJ"}
    assert canonical_option_ids("选项 A") == {"选项 A"}
    assert canonical_option_ids("ΔU = Q - W") == {"ΔU = Q - W"}


def test_option_text_with_spaces_still_maps_to_its_id() -> None:
    """求解器按选项原文作答时，含空格的选项文本必须仍能映射回 id。"""
    from assessment_orchestrator import _resolve_option_ids

    options = [{"id": "A", "text": "12 kJ"}, {"id": "B", "text": "28 kJ"}]
    assert _resolve_option_ids("12 kJ", options) == {"A"}
    assert _resolve_option_ids("28 kJ", options) == {"B"}
