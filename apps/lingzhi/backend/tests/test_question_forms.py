"""H1d：落库层保留完整题型标识，题库可按题型统计与配比。

改动前题库只有 `question_type`，而它表达的是**学科教学意图**——同一种作答形态
在不同学科族下叫不同名字（selected_response / structured_application /
scenario_deliverable / performance_task …）。教师问"这门课填空题占比多少"，
在这个字段上答不了。教师导入路径更是仅凭有没有 options 压成两态。

`question_form` 与学科无关，只回答"怎么作答、怎么判分"，是 H1a（多选/判断）与
H1b（填空）能在题库里被看见的前置。
"""
from __future__ import annotations

from question_forms import (
    QUESTION_FORMS,
    classify_question_form,
    question_form_distribution,
)


def _item(**overrides) -> dict:
    item = {
        "item_id": "qbi_1",
        "revision_id": "qbr_1",
        "prompt": "题干",
        "question_type": "selected_response",
    }
    item.update(overrides)
    return item


def _spec(mode: str, **extra) -> dict:
    spec = {"input_contract": {"mode": mode}}
    spec.update(extra)
    return spec


# --- 按输入模式判定 ---------------------------------------------------------


def test_choice_mode_defaults_to_single_choice() -> None:
    assert classify_question_form(_item(
        question_spec=_spec("choice"),
        options=[{"id": "A", "text": "甲"}, {"id": "B", "text": "乙"}, {"id": "C", "text": "丙"}],
        answer_spec={"correct_option_id": "A"},
    )) == "single_choice"


def test_multiple_correct_options_make_it_multiple_choice() -> None:
    """H1a：多选此前全库没有标识符，只能被当成单选。"""
    assert classify_question_form(_item(
        question_spec=_spec("choice"),
        options=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
        answer_spec={"correct_option_ids": ["A", "C"]},
    )) == "multiple_choice"


def test_multiple_correct_options_detected_from_option_flags() -> None:
    assert classify_question_form(_item(
        question_spec=_spec("choice"),
        options=[
            {"id": "A", "is_correct": True},
            {"id": "B", "is_correct": True},
            {"id": "C"},
        ],
        answer_spec={},
    )) == "multiple_choice"


def test_two_polar_options_are_true_false() -> None:
    """H1a：判断题按选项是不是一对是非表述识别。

    不靠 question_type 里有没有 true_false —— 上游根本不产出那个标识符。
    """
    for pair in (("正确", "错误"), ("对", "错"), ("是", "否"), ("True", "False")):
        assert classify_question_form(_item(
            question_spec=_spec("choice"),
            options=[{"id": "A", "text": pair[0]}, {"id": "B", "text": pair[1]}],
            answer_spec={"correct_option_id": "A"},
        )) == "true_false", pair


def test_two_ordinary_options_are_not_true_false() -> None:
    """只有两个选项不等于判断题，内容必须真的是一对是非表述。"""
    assert classify_question_form(_item(
        question_spec=_spec("choice"),
        options=[{"id": "A", "text": "熵增"}, {"id": "B", "text": "熵减"}],
        answer_spec={"correct_option_id": "A"},
    )) == "single_choice"


def test_code_structured_numeric_and_text_modes() -> None:
    assert classify_question_form(_item(question_spec=_spec("code"))) == "coding"
    assert classify_question_form(
        _item(question_spec=_spec("structured_fields")),
    ) == "structured"
    assert classify_question_form(
        _item(question_spec=_spec("numeric_unit")),
    ) == "numeric"
    assert classify_question_form(_item(question_spec=_spec("rich_text"))) == "essay"
    assert classify_question_form(
        _item(question_spec=_spec("short_text")),
    ) == "short_answer"


# --- 填空（H1b 前置） -------------------------------------------------------


def test_fill_blank_detected_from_structured_blanks() -> None:
    assert classify_question_form(_item(
        question_spec=_spec("short_text", blanks=[{"blank_id": "b1"}]),
    )) == "fill_blank"


def test_fill_blank_wins_over_choice_when_it_offers_a_word_bank() -> None:
    """填空题可以给候选词表，不能因为有 options 就判成选择题。"""
    assert classify_question_form(_item(
        question_spec=_spec("choice", blanks=[{"blank_id": "b1"}]),
        options=[{"id": "A", "text": "守恒"}, {"id": "B", "text": "耗散"}],
    )) == "fill_blank"


def test_underscores_in_prompt_alone_do_not_make_it_fill_blank() -> None:
    """不靠数题干里的下划线——正文里的下划线可能只是排版。"""
    assert classify_question_form(_item(
        prompt="请回答：能量守恒定律 ______ 适用于开放系统吗？",
        question_spec=_spec("short_text"),
    )) == "short_answer"


# --- 兜底与诚实 -------------------------------------------------------------


def test_unknown_shape_is_unspecified_not_guessed() -> None:
    assert classify_question_form({"prompt": "无任何结构信息"}) == "unspecified"


def test_explicit_form_is_respected() -> None:
    assert classify_question_form(_item(
        question_form="fill_blank",
        question_spec=_spec("rich_text"),
    )) == "fill_blank"


def test_bogus_explicit_form_falls_back_to_inference() -> None:
    """显式值不在白名单里就不采信，回到按结构判定。"""
    assert classify_question_form(_item(
        question_form="not_a_real_form",
        question_spec=_spec("code"),
    )) == "coding"


def test_every_produced_form_is_in_the_whitelist() -> None:
    samples = [
        _item(question_spec=_spec(mode))
        for mode in ("choice", "code", "numeric_unit", "rich_text",
                     "short_text", "structured_fields")
    ]
    samples.append({"prompt": "空"})
    for sample in samples:
        assert classify_question_form(sample) in QUESTION_FORMS


# --- 分布统计（H1d 验收物） -------------------------------------------------


def test_distribution_answers_the_question_type_ratio() -> None:
    items = [
        _item(question_spec=_spec("choice"), options=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
              answer_spec={"correct_option_id": "A"}),
        _item(question_spec=_spec("short_text", blanks=[{"blank_id": "b1"}])),
        _item(question_spec=_spec("short_text", blanks=[{"blank_id": "b2"}])),
        _item(question_spec=_spec("rich_text")),
    ]
    distribution = question_form_distribution(items)

    assert distribution == {"essay": 1, "fill_blank": 2, "single_choice": 1}
    assert distribution["fill_blank"] / sum(distribution.values()) == 0.5


def test_distribution_ignores_non_dict_entries() -> None:
    assert question_form_distribution([None, "x", _item(question_spec=_spec("code"))]) == {
        "coding": 1,
    }


# --- 接进题库落库层 ---------------------------------------------------------


def test_question_bank_stamps_and_reports_forms() -> None:
    """题库每道题都带 question_form，coverage 能出分布。"""
    from question_bank import _stamp_question_forms, build_question_bank

    items = [
        _item(question_spec=_spec("choice"), options=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
              answer_spec={"correct_option_id": "A"}),
        _item(question_spec=_spec("rich_text")),
    ]
    _stamp_question_forms(items)
    assert [item["question_form"] for item in items] == ["single_choice", "essay"]

    course = {
        "course_id": "c1",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "热力学第一定律",
            "node_content": (
                "封闭系统吸热 Q=20 kJ，对外做功 W=8 kJ，"
                "采用 ΔU=Q-W 计算内能变化并核对单位。"
            ),
            "learning_objective": "使用热力学第一定律计算内能变化",
            "key_points": ["能量守恒"],
            "assessment": ["列式计算内能变化"],
            "difficulty_contract": {"target_level": "intermediate"},
            "grounding_contract": {"question_evidence_ids": []},
        }],
    }
    bundle = build_question_bank(course)

    assert all("question_form" in item for item in bundle["items"])
    distribution = bundle["coverage"]["question_form_distribution"]
    assert distribution
    assert sum(distribution.values()) == len(bundle["items"])
    # 未通过合同的题不进入可发布口径（与 L1 同一口径）
    assert "publishable_question_form_distribution" in bundle["coverage"]
