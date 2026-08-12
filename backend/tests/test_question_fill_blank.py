"""H1b：填空题。题干挖空、按空位逐个判定。

验收口径来自清单：能正确处理"等价但写法不同"的答案（数值容差、单位换算、
代数等价、多解、大小写与空白）。判等全部复用 assessment_validators，不另立口径。
"""
from __future__ import annotations

import pytest

from question_fill_blank import (
    MAX_BLANKS,
    assert_no_answer_leak,
    compile_fill_blank_contract,
    grade_fill_blank,
    parse_blank_ids,
    public_blank_view,
)


def _contract(**overrides):
    payload = {
        "prompt": "封闭系统吸热 Q=20 kJ、对外做功 W=8 kJ，则 ΔU={{1}}，判据是{{2}}。",
        "blanks": [
            {
                "blank_id": "1",
                "match_mode": "numeric",
                "answer": {"value": 12, "unit": "kJ"},
            },
            {
                "blank_id": "2",
                "match_mode": "exact",
                "answer": "热力学第一定律",
                "acceptable_answers": ["能量守恒定律"],
            },
        ],
    }
    payload.update(overrides)
    return compile_fill_blank_contract(**payload)


# --- 题干与空位 -------------------------------------------------------------


def test_parses_blanks_in_order_without_duplicates() -> None:
    assert parse_blank_ids("a{{1}}b{{2}}c{{1}}") == ["1", "2"]
    assert parse_blank_ids("没有空位") == []


def test_compiles_a_contract_with_blank_ids() -> None:
    contract = _contract()
    assert contract["blank_ids"] == ["1", "2"]
    assert [blank["blank_id"] for blank in contract["blanks"]] == ["1", "2"]


# --- 结构性错误在出题期就挡住 -----------------------------------------------


def test_prompt_without_blanks_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        compile_fill_blank_contract(prompt="没有空位", blanks=[])


def test_blank_missing_from_prompt_is_rejected() -> None:
    with pytest.raises(ValueError, match="not present in the prompt"):
        compile_fill_blank_contract(
            prompt="只有一个空 {{1}}",
            blanks=[
                {"blank_id": "1", "answer": "甲"},
                {"blank_id": "9", "answer": "乙"},
            ],
        )


def test_prompt_blank_without_an_answer_is_rejected() -> None:
    """题干挖了空却没给答案，学生作答时无从判定——出题期就要拦住。"""
    with pytest.raises(ValueError, match="without answers"):
        compile_fill_blank_contract(
            prompt="{{1}} 与 {{2}}",
            blanks=[{"blank_id": "1", "answer": "甲"}],
        )


def test_empty_answer_is_rejected() -> None:
    with pytest.raises(ValueError, match="no answer"):
        compile_fill_blank_contract(
            prompt="{{1}}",
            blanks=[{"blank_id": "1", "answer": ""}],
        )


def test_duplicate_blank_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        compile_fill_blank_contract(
            prompt="{{1}} 和 {{1}} 再来 {{2}}",
            blanks=[
                {"blank_id": "1", "answer": "甲"},
                {"blank_id": "1", "answer": "乙"},
                {"blank_id": "2", "answer": "丙"},
            ],
        )


def test_unknown_match_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="match_mode"):
        compile_fill_blank_contract(
            prompt="{{1}}",
            blanks=[{"blank_id": "1", "answer": "甲", "match_mode": "vibes"}],
        )


def test_too_many_blanks_is_rejected() -> None:
    count = MAX_BLANKS + 1
    with pytest.raises(ValueError, match="at most"):
        compile_fill_blank_contract(
            prompt="".join(f"{{{{{index}}}}}" for index in range(count)),
            blanks=[
                {"blank_id": str(index), "answer": "x"}
                for index in range(count)
            ],
        )


# --- 判等：等价但写法不同（清单验收重点） -----------------------------------


def test_numeric_blank_accepts_equivalent_units() -> None:
    """12 kJ 与 12000 J 是同一个答案，不能因为写法不同就判错。"""
    contract = _contract()
    graded = grade_fill_blank(contract, {"blanks": {
        "1": {"value": 12000, "unit": "J"},
        "2": "热力学第一定律",
    }})
    assert graded["all_correct"] is True
    assert graded["score"] == 100.0


def test_exact_blank_ignores_case_and_whitespace() -> None:
    contract = compile_fill_blank_contract(
        prompt="{{1}}",
        blanks=[{
            "blank_id": "1",
            "match_mode": "exact",
            "answer": "Gibbs Free Energy",
            # 文本空现在必须自带同义写法（见 _requires_synonyms）
            "acceptable_answers": ["gibbs free energy", "Gibbs free energy"],
        }],
    )
    graded = grade_fill_blank(contract, {"blanks": {"1": "  gibbs   free energy "}})
    assert graded["all_correct"] is True


def test_acceptable_answers_cover_multiple_valid_wordings() -> None:
    contract = _contract()
    graded = grade_fill_blank(contract, {"blanks": {
        "1": {"value": 12, "unit": "kJ"},
        "2": "能量守恒定律",
    }})
    assert graded["all_correct"] is True


def test_symbolic_blank_accepts_algebraically_equal_forms() -> None:
    contract = compile_fill_blank_contract(
        prompt="ΔU = {{1}}",
        blanks=[{"blank_id": "1", "match_mode": "symbolic", "answer": "Q - W"}],
    )
    assert grade_fill_blank(contract, {"blanks": {"1": "-W + Q"}})["all_correct"] is True


def test_wrong_answer_is_still_wrong() -> None:
    """判等放宽不等于放水。"""
    contract = _contract()
    graded = grade_fill_blank(contract, {"blanks": {
        "1": {"value": 28, "unit": "kJ"},
        "2": "热力学第二定律",
    }})
    assert graded["correct_count"] == 0
    assert graded["score"] == 0.0


# --- 空位级部分给分与错因 ---------------------------------------------------


def test_partial_credit_is_per_blank() -> None:
    contract = _contract()
    graded = grade_fill_blank(contract, {"blanks": {
        "1": {"value": 12, "unit": "kJ"},
        "2": "热力学第二定律",
    }})
    assert graded["correct_count"] == 1
    assert graded["all_correct"] is False
    assert graded["score"] == 50.0
    by_id = {item["blank_id"]: item for item in graded["results"]}
    assert by_id["1"]["correct"] is True
    assert by_id["2"]["correct"] is False


def test_score_weight_is_respected() -> None:
    contract = compile_fill_blank_contract(
        prompt="{{1}}{{2}}",
        blanks=[
            {"blank_id": "1", "answer": "甲", "score_weight": 3},
            {"blank_id": "2", "answer": "乙", "score_weight": 1},
        ],
    )
    graded = grade_fill_blank(contract, {"blanks": {"1": "甲", "2": "错"}})
    assert graded["score"] == 75.0


def test_unanswered_blank_is_distinguished_from_wrong() -> None:
    """"没答"与"答错"在诊断上不是一回事，不能混成一个 correct=False。"""
    contract = _contract()
    graded = grade_fill_blank(contract, {"blanks": {"1": {"value": 12, "unit": "kJ"}}})
    by_id = {item["blank_id"]: item for item in graded["results"]}
    assert by_id["2"]["answered"] is False
    assert by_id["2"]["correct"] is False
    assert graded["answered_count"] == 1


def test_missing_submission_scores_zero_without_crashing() -> None:
    contract = _contract()
    for submission in (None, {}, {"blanks": {}}, {"blanks": "not-a-dict"}):
        graded = grade_fill_blank(contract, submission)
        assert graded["score"] == 0.0
        assert graded["answered_count"] == 0


def test_wrong_blank_reports_its_misconception_for_diagnosis() -> None:
    contract = compile_fill_blank_contract(
        prompt="{{1}}",
        blanks=[{
            "blank_id": "1",
            "answer": "12",
            "misconception_ids": ["ckm_sign_flip"],
        }],
    )
    wrong = grade_fill_blank(contract, {"blanks": {"1": "28"}})
    assert wrong["results"][0]["misconception_ids"] == ["ckm_sign_flip"]
    # 判对不带易错点，否则会把正确作答也归因成误解
    right = grade_fill_blank(contract, {"blanks": {"1": "12"}})
    assert right["results"][0]["misconception_ids"] == []
    # 没答也不归因——那是跳过，不是误解
    skipped = grade_fill_blank(contract, {"blanks": {}})
    assert skipped["results"][0]["misconception_ids"] == []


# --- 答案披露门禁 -----------------------------------------------------------


def test_public_view_never_carries_answers() -> None:
    contract = _contract()
    view = public_blank_view(contract)

    assert_no_answer_leak(view)
    serialized = repr(view)
    assert "热力学第一定律" not in serialized
    assert "能量守恒定律" not in serialized
    assert "12" not in serialized
    assert [blank["blank_id"] for blank in view["blanks"]] == ["1", "2"]


def test_leak_guard_actually_fires() -> None:
    """守卫本身要有效，否则它只是装饰。"""
    bad_view = {"blanks": [{"blank_id": "1", "answer": "12"}]}
    with pytest.raises(AssertionError, match="leaked answer fields"):
        assert_no_answer_leak(bad_view)


# --- 与题库形态分类对接（H1d） ----------------------------------------------


def test_fill_blank_is_recognised_by_the_bank_classifier() -> None:
    from question_forms import classify_question_form

    contract = _contract()
    assert classify_question_form({
        "prompt": contract["prompt"],
        "question_spec": {
            "input_contract": {"mode": "short_text"},
            "blanks": contract["blank_ids"],
        },
    }) == "fill_blank"


# --- 确定性挖空（H1b 成品率）------------------------------------------------


def test_derives_placeholders_from_a_declarative_stem() -> None:
    """模型写一句含答案的陈述句，由代码挖空。

    比让模型自己写 {{1}} 可靠得多——真机实测它对模板语法的服从度只有 3/10。
    """
    from question_fill_blank import derive_blank_placeholders

    text, unresolved = derive_blank_placeholders(
        "封闭系统吸热 35 kJ、对外做功 12 kJ，内能变化 ΔU = 23 kJ。",
        [{"blank_id": "1", "answer": {"value": 23, "unit": "kJ"}}],
    )
    assert text == "封闭系统吸热 35 kJ、对外做功 12 kJ，内能变化 ΔU = {{1}}。"
    assert unresolved == []


def test_existing_placeholders_are_left_alone() -> None:
    """题面已经挖好空的原样返回，不重复加工。"""
    from question_fill_blank import derive_blank_placeholders

    original = "内能变化 ΔU = {{1}} kJ。"
    text, unresolved = derive_blank_placeholders(
        original, [{"blank_id": "1", "answer": "23"}],
    )
    assert text == original
    assert unresolved == []


def test_answer_absent_from_the_stem_is_reported_not_invented() -> None:
    """凭空造一个空位会做出题面与答案对不上的题，比生成失败更糟。"""
    from question_fill_blank import derive_blank_placeholders

    text, unresolved = derive_blank_placeholders(
        "请计算该系统的内能变化。",
        [{"blank_id": "1", "answer": "23"}],
    )
    assert "{{" not in text
    assert unresolved == ["1"]


def test_only_the_first_occurrence_is_blanked() -> None:
    """正文里出现同样的数值时不能一起挖掉。"""
    from question_fill_blank import derive_blank_placeholders

    text, _ = derive_blank_placeholders(
        "已知 12 kJ 为参考值，本题答案为 12 kJ。",
        [{"blank_id": "1", "answer": "12 kJ"}],
    )
    assert text.count("{{1}}") == 1
    assert text.startswith("已知 {{1}} 为参考值")


def test_multiple_blanks_are_derived_in_order() -> None:
    from question_fill_blank import (
        compile_fill_blank_contract,
        derive_blank_placeholders,
    )

    blanks = [
        {"blank_id": "1", "answer": "23", "match_mode": "exact"},
        {
            "blank_id": "2",
            "answer": "热力学第一定律",
            "match_mode": "exact",
            "acceptable_answers": ["热力学第1定律", "能量守恒定律"],
        },
    ]
    text, unresolved = derive_blank_placeholders(
        "ΔU 为 23，判据是热力学第一定律。", blanks,
    )
    assert unresolved == []
    # 挖出来的题面必须能直接编译成契约
    contract = compile_fill_blank_contract(prompt=text, blanks=blanks)
    assert contract["blank_ids"] == ["1", "2"]


# --- 文本空必须自带同义写法（H1b 归因结论的落地） -------------------------


def test_free_text_blank_without_synonyms_is_rejected() -> None:
    """文本空的判等是「归一化后字符串相等」，措辞一变就判错。

    归因实测：填空失败几乎全是求解器写「系统内能增加」而标准答案是
    「内能增加」这类同义不同形。要么题目把同义写法穷举出来，要么这道题
    本来就判不准——所以出题期就要求给齐，而不是留到学生作答时误判。

    **这是收紧不是放宽**：判等规则一个字没动，只是要求把判等所需信息给全。
    """
    with pytest.raises(ValueError, match="acceptable_answers"):
        compile_fill_blank_contract(
            prompt="该过程中系统{{1}}。",
            blanks=[{
                "blank_id": "1",
                "answer": "内能增加",
                "match_mode": "exact",
            }],
        )


def test_free_text_blank_with_synonyms_compiles() -> None:
    contract = compile_fill_blank_contract(
        prompt="该过程中系统{{1}}。",
        blanks=[{
            "blank_id": "1",
            "answer": "内能增加",
            "match_mode": "exact",
            "acceptable_answers": ["系统内能增加", "内能增大"],
        }],
    )
    assert contract["blanks"][0]["acceptable_answers"] == [
        "系统内能增加", "内能增大",
    ]
    # 同义写法要真的能判对，否则等于白填
    graded = grade_fill_blank(contract, {"blanks": {"1": "系统内能增加"}})
    assert graded["all_correct"] is True


def test_numeric_and_symbolic_blanks_are_not_forced_to_list_synonyms() -> None:
    """数值/代数的判等本身就吃得下写法差异，不必穷举。"""
    numeric = compile_fill_blank_contract(
        prompt="ΔU = {{1}}。",
        blanks=[{
            "blank_id": "1",
            "answer": {"value": 23, "unit": "kJ"},
            "match_mode": "numeric",
        }],
    )
    assert numeric["blanks"][0]["acceptable_answers"] == []

    symbolic = compile_fill_blank_contract(
        prompt="ΔU = {{1}}。",
        blanks=[{"blank_id": "1", "answer": "Q - W", "match_mode": "symbolic"}],
    )
    assert symbolic["blanks"][0]["acceptable_answers"] == []


def test_pure_number_and_very_short_exact_blanks_are_exempt() -> None:
    """纯数字与一两字的答案判等歧义小，不强制穷举——否则会误伤正常题。"""
    for answer in ("23", "-15", "1.5", "是"):
        contract = compile_fill_blank_contract(
            prompt="答案是{{1}}。",
            blanks=[{
                "blank_id": "1",
                "answer": answer,
                "match_mode": "exact",
            }],
        )
        assert contract["blank_ids"] == ["1"], answer
