"""填空判等的逐空取证记录：分类规则与 sink 行为。

这套东西**只做归因，不参与判定**。用户 2026-08-13 的要求是「拿到分布再判断
病因归属，不要在拿到分布前先改判等规则」——所以这里的任何函数都不得被
`question_fill_blank` 的判等路径引用。
"""
from __future__ import annotations

from assessment_fill_blank_diagnostics import (
    CAUSE_BUCKETS,
    classify_blank_mismatch,
    clear_sink,
    install_sink,
    normalize_text,
    record_comparison,
    sink_enabled,
    split_number_unit,
    summarize,
)


def test_sink_is_off_by_default_so_production_records_nothing() -> None:
    """默认 no-op 是这套记录能存在的前提。

    逐空对照必须存**标准答案原文**才有归因价值，而生成审计会被投影进题库
    payload。默认关掉、只在核查脚本进程内打开，答案就永远不会进任何 payload。
    """
    clear_sink()
    assert sink_enabled() is False
    record_comparison({"outcome": "blank_mismatch"})  # 不抛、不存
    assert sink_enabled() is False


def test_installed_sink_collects_entries() -> None:
    sink = install_sink()
    try:
        assert sink_enabled() is True
        record_comparison({"outcome": "blank_mismatch", "blanks": []})
        assert len(sink) == 1
        assert sink[0]["outcome"] == "blank_mismatch"
    finally:
        clear_sink()


def test_split_number_unit_handles_every_real_shape() -> None:
    """真机里同一个答案至少四种写法，归因前必须放到同一形状上。"""
    assert split_number_unit({"value": -14, "unit": "kJ"}) == (-14.0, "kJ")
    assert split_number_unit("-14 kJ") == (-14.0, "kJ")
    assert split_number_unit("-14") == (-14.0, "")
    assert split_number_unit(-14) == (-14.0, "")
    # 全角数字与千分位
    assert split_number_unit("１２００") == (1200.0, "")
    assert split_number_unit("1,200 J") == (1200.0, "J")
    # 拆不出数值就整段当文本
    assert split_number_unit("减少") == (None, "减少")


def test_unit_mismatch_is_separated_from_value_mismatch() -> None:
    """两类数值不一致必须分开——一类是判等预处理问题，一类是内容错。"""
    # 数值相同、单位丢了 → 归一化问题
    assert classify_blank_mismatch(
        "numeric", {"value": -14, "unit": "kJ"}, "-14", correct=False,
    ) == "unit_mismatch"
    # 数值不同 → 求解器（或标准答案）内容错，与判等无关
    assert classify_blank_mismatch(
        "numeric", {"value": -14, "unit": "kJ"}, "14 kJ", correct=False,
    ) == "numeric_value_mismatch"
    # 数值与单位都一致却仍判错 → 纯写法问题
    assert classify_blank_mismatch(
        "numeric", "-14 kJ", "－１４ kJ", correct=False,
    ) == "numeric_format"


def test_text_divergence_is_reported_but_not_resolved() -> None:
    """「减少」vs「下降」与「减少」vs「增加」在字符串层面没有区别。

    代码判不了同义词与答错的差别，所以只归到 `text_divergent` 并原样导出，
    由人来读。**这里绝不能加同义词表去猜**——那等于把已被否决的语义判等
    从后门放进来。
    """
    assert classify_blank_mismatch(
        "exact", "减少", "下降", correct=False,
    ) == "text_divergent"
    assert classify_blank_mismatch(
        "exact", "减少", "增加", correct=False,
    ) == "text_divergent"
    assert CAUSE_BUCKETS["text_divergent"] == "undecidable"


def test_text_normalization_and_containment_are_separated() -> None:
    # 只差空格标点 → 归一化问题
    assert classify_blank_mismatch(
        "exact", "封闭系统", " 封闭、系统 ", correct=False,
    ) == "text_normalization"
    # 归因里最典型的一对：措辞冗余，互为子串
    assert classify_blank_mismatch(
        "exact", "内能增加", "系统内能增加", correct=False,
    ) == "text_containment"


def test_shape_and_missing_submission_are_their_own_kinds() -> None:
    assert classify_blank_mismatch(
        "numeric", {"value": 12, "unit": "kJ"}, "增加", correct=False,
    ) == "shape_mismatch"
    assert classify_blank_mismatch(
        "exact", "增加", None, correct=False,
    ) == "no_submission"
    assert classify_blank_mismatch(
        "exact", "增加", "", correct=False,
    ) == "no_submission"


def test_classification_never_re_judges_correctness() -> None:
    """判对错只有一把尺子（生产判等）。归因工具重判一遍就会出现两套结论。"""
    assert classify_blank_mismatch(
        "exact", "增加", "完全不同的东西", correct=True,
    ) == "correct"


def test_normalize_text_is_looser_than_grading_on_purpose() -> None:
    assert normalize_text(" Q - W ") == normalize_text("q-w")
    assert normalize_text("１２") == normalize_text("12")


def test_summarize_reports_distribution_and_exports_undecidable_pairs() -> None:
    """汇总只给分布，不下结论；判不了的那一类原样导出供人读。"""
    entries = [
        {
            "outcome": "blank_mismatch",
            "blanks": [
                {
                    "blank_id": "1",
                    "blank_kind": "numeric",
                    "match_mode": "numeric",
                    "expected": {"value": -14, "unit": "kJ"},
                    "submitted": "-14",
                    "mismatch_kind": "unit_mismatch",
                },
                {
                    "blank_id": "2",
                    "blank_kind": "short_term",
                    "match_mode": "exact",
                    "expected": "减少",
                    "acceptable_answers": [],
                    "submitted": "下降",
                    "mismatch_kind": "text_divergent",
                },
            ],
        },
        {
            "outcome": "passed",
            "blanks": [{
                "blank_id": "1",
                "blank_kind": "numeric",
                "mismatch_kind": "correct",
            }],
        },
    ]
    summary = summarize(entries)
    assert summary["validation_count"] == 2
    assert summary["blank_total"] == 3
    assert summary["mismatch_total"] == 2
    assert summary["by_cause"] == {"normalization": 1, "undecidable": 1}
    assert summary["outcomes"]["blank_mismatch"] == 1
    assert summary["mismatch_by_blank_kind"] == {
        "numeric": 1,
        "short_term": 1,
    }
    # 判不了的那一对必须原样出现，否则人无从复核
    assert summary["undecidable_pairs"] == [{
        "blank_id": "2",
        "blank_kind": "short_term",
        "match_mode": "exact",
        "expected": "减少",
        "acceptable_answers": [],
        "submitted": "下降",
    }]


# --- 接进生产判等路径（_validate_fill_blank_solution）-----------------------


def _fill_blank_contract(answer, prompt: str = "该系统内能变化 ΔU 为 {{1}}。"):
    return {
        "prompt": prompt,
        "question_spec": {"solution_revision_id": "sol_probe"},
        "solution_envelope": {
            "blanks": [{
                "blank_id": "1",
                "answer": answer,
                "match_mode": "numeric",
            }],
        },
    }


def test_validation_records_the_actual_expected_versus_submitted_pair() -> None:
    """取证要的就是这一对：标准答案原文 + 求解器原始答案。

    存哈希看不出 `-14 kJ` vs `-14`，所以必须存原文——也正因为存原文，
    这条通道默认是关的（见 sink 默认 no-op 那条用例）。
    """
    from assessment_orchestrator import _validate_fill_blank_solution

    sink = install_sink()
    try:
        result = _validate_fill_blank_solution(
            _fill_blank_contract({"value": -14, "unit": "kJ"}),
            "-14",
            independent={"solver_kind": "", "solver_attested": False},
        )
    finally:
        clear_sink()

    assert result["passed"] is False
    assert len(sink) == 1
    entry = sink[0]
    assert entry["outcome"] == "blank_mismatch"
    assert entry["raw_solved"] == "-14"
    blank = entry["blanks"][0]
    assert blank["expected"] == {"value": -14, "unit": "kJ"}
    assert blank["submitted"] == "-14"
    assert blank["correct"] is False
    assert blank["blank_kind"] == "numeric"
    assert blank["mismatch_kind"] == "unit_mismatch"


def test_validation_records_passing_blanks_as_the_denominator() -> None:
    """只记失败会让分布没有分母，说不清「多少空里有多少不一致」。"""
    from assessment_orchestrator import _validate_fill_blank_solution

    sink = install_sink()
    try:
        result = _validate_fill_blank_solution(
            _fill_blank_contract({"value": -14, "unit": "kJ"}),
            {"blanks": {"1": {"value": -14, "unit": "kJ"}}},
            independent={},
        )
    finally:
        clear_sink()

    assert result["passed"] is True
    assert sink[0]["outcome"] == "passed"
    assert sink[0]["blanks"][0]["mismatch_kind"] == "correct"


def test_validation_records_structural_rejections_too() -> None:
    """契约拒收与「答案不在题面」也要进分布，否则失败构成会缺一块。"""
    from assessment_orchestrator import _validate_fill_blank_solution

    sink = install_sink()
    try:
        _validate_fill_blank_solution(
            {
                "prompt": "该过程中系统的变化情况如何。",
                "question_spec": {},
                "solution_envelope": {
                    "blanks": [{
                        "blank_id": "1",
                        "answer": "内能增加并对外做功",
                        "match_mode": "exact",
                    }],
                },
            },
            "内能增加并对外做功",
            independent={},
        )
    finally:
        clear_sink()

    assert sink[0]["outcome"] == "answer_not_in_stem"
    assert sink[0]["detail"]["unresolved_blank_ids"] == ["1"]


def test_validation_records_nothing_when_sink_is_off() -> None:
    """生产路径不能因为加了取证就多存一份标准答案。"""
    from assessment_orchestrator import _validate_fill_blank_solution

    clear_sink()
    result = _validate_fill_blank_solution(
        _fill_blank_contract({"value": -14, "unit": "kJ"}),
        "-14",
        independent={},
    )
    # 判定结果与装 sink 时完全一致——记录是旁路，不参与判定
    assert result["passed"] is False
    assert sink_enabled() is False
