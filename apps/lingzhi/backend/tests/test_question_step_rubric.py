"""H1c：大题分步量规。

与 lz-assess-ux 的 J3 分工（先读了 dev/lz-assess-ux 87427056 再动手）：
  J3 负责作答侧——学生怎么提交步骤、模型判定怎么绑回步骤、汇总口径；
  本条负责出题侧——每步值多少分、哪些是必得分点、按步加权算总分。
J3 的 verdict 三态与 normalize_step_judgements 的输出格式原样复用，不另立口径。
"""
from __future__ import annotations

import importlib.util

import pytest

from question_step_rubric import compile_step_rubric, score_steps

# J3（stepwise_answers）在 dev/lz-assess-ux 上，尚未合入本分支。本模块刻意只
# 依赖它的**输出格式**而不依赖它的代码，所以主体用例不需要它；两条对接用例在
# 它到位后自动生效，不到位就跳过——不为了让测试变绿而在这里造一个假的
# stepwise_answers，那会掩盖真正的对接风险。
_HAS_J3 = importlib.util.find_spec("stepwise_answers") is not None
requires_j3 = pytest.mark.skipif(
    not _HAS_J3,
    reason="stepwise_answers (J3) 尚未合入本分支",
)


def _solution_spec():
    return {
        "schema_version": "solution_spec_v1",
        "steps": ["列出已知量", "代入公式", "核对单位"],
        "step_details": [
            {"step_id": "s1", "title": "列出已知量", "explanation": "写出 Q 与 W 及其符号"},
            {"step_id": "s2", "title": "代入公式", "explanation": "使用 ΔU=Q-W"},
            {"step_id": "s3", "title": "核对单位", "explanation": "确认单位为 kJ"},
        ],
    }


def _judgements(*verdicts):
    """构造 J3 normalize_step_judgements 形状的输出。"""
    return [
        {
            "step_index": index,
            "step_id": f"s{index}",
            "verdict": verdict,
            "comment": "",
            "evidence": "",
        }
        for index, verdict in enumerate(verdicts, start=1)
        if verdict
    ]


# --- 量规编译 ---------------------------------------------------------------


def test_rubric_compiles_from_the_private_solution_steps() -> None:
    """步骤来源是已有的私有解答，不另建一份步骤真源。"""
    rubric = compile_step_rubric(_solution_spec())

    assert rubric["step_count"] == 3
    assert [step["step_id"] for step in rubric["steps"]] == ["s1", "s2", "s3"]
    assert [step["title"] for step in rubric["steps"]] == [
        "列出已知量", "代入公式", "核对单位",
    ]


def test_default_weights_are_equal() -> None:
    """权重是教研判断；没有依据时不该由引擎编造差异。"""
    rubric = compile_step_rubric(_solution_spec())
    assert {step["weight"] for step in rubric["steps"]} == {1.0}
    assert rubric["total_weight"] == 3.0


def test_weights_and_required_steps_are_honoured() -> None:
    rubric = compile_step_rubric(
        _solution_spec(),
        weights={"s2": 3.0},
        required_step_ids=["s2"],
    )
    by_id = {step["step_id"]: step for step in rubric["steps"]}
    assert by_id["s2"]["weight"] == 3.0
    assert by_id["s2"]["required"] is True
    assert by_id["s1"]["required"] is False
    assert rubric["total_weight"] == 5.0


def test_zero_weight_steps_are_dropped() -> None:
    rubric = compile_step_rubric(_solution_spec(), weights={"s3": 0})
    assert [step["step_id"] for step in rubric["steps"]] == ["s1", "s2"]


def test_plain_text_steps_still_compile() -> None:
    rubric = compile_step_rubric({"steps": ["先做甲", "再做乙"]})
    assert rubric["step_count"] == 2
    assert rubric["steps"][0]["step_id"] == "step_1"


def test_missing_solution_yields_an_empty_rubric() -> None:
    for spec in (None, {}, {"steps": []}):
        rubric = compile_step_rubric(spec)
        assert rubric["step_count"] == 0
        assert rubric["steps"] == []


# --- 加权判分 ---------------------------------------------------------------


def test_all_correct_scores_full() -> None:
    rubric = compile_step_rubric(_solution_spec())
    result = score_steps(rubric, _judgements("correct", "correct", "correct"))

    assert result["score"] == 100.0
    assert result["passed"] is True
    assert result["scored_step_count"] == 3


def test_partial_credit_follows_step_weights() -> None:
    rubric = compile_step_rubric(_solution_spec(), weights={"s2": 3.0})
    # 只做对权重 3 的关键步骤，总权重 5
    result = score_steps(rubric, _judgements("flawed", "correct", "flawed"))
    assert result["score"] == 60.0


def test_flawed_step_earns_nothing() -> None:
    rubric = compile_step_rubric(_solution_spec())
    result = score_steps(rubric, _judgements("correct", "flawed", "correct"))
    assert result["score"] == round(200 / 3, 2)
    assert result["steps"][1]["earned"] == 0.0


def test_unclear_is_neither_credited_nor_counted_as_wrong() -> None:
    """模型说不清时不能白送分，也不该当成学生错了——但必须可见。"""
    rubric = compile_step_rubric(_solution_spec())
    result = score_steps(rubric, _judgements("correct", "unclear", "correct"))

    assert result["earned_weight"] == 2.0
    assert result["unresolved_weight"] == 1.0
    assert result["steps"][1]["earned"] == 0.0
    assert result["steps"][1]["verdict"] == "unclear"


def test_unjudged_steps_are_marked_missing_not_wrong() -> None:
    """学生没写的步骤 J3 不会产生判定；这里要记为 missing 而不是判错。"""
    rubric = compile_step_rubric(_solution_spec())
    result = score_steps(rubric, _judgements("correct"))

    verdicts = [step["verdict"] for step in result["steps"]]
    assert verdicts == ["correct", "missing", "missing"]
    assert result["score"] == round(100 / 3, 2)


# --- 必得分点 ---------------------------------------------------------------


def test_missing_a_required_step_blocks_passing() -> None:
    """靠边角步骤凑够分数但漏掉关键推导，不算通过。"""
    rubric = compile_step_rubric(
        _solution_spec(),
        weights={"s1": 4.0},
        required_step_ids=["s2"],
    )
    result = score_steps(rubric, _judgements("correct", "flawed", "correct"))

    assert result["score"] >= 50.0
    assert result["missing_required_step_ids"] == ["s2"]
    assert result["passed"] is False


def test_required_step_alone_is_not_enough_to_pass() -> None:
    """只做对关键步骤、其余全错，也不算通过。"""
    rubric = compile_step_rubric(
        _solution_spec(),
        required_step_ids=["s2"],
    )
    result = score_steps(rubric, _judgements("flawed", "correct", "flawed"))

    assert result["missing_required_step_ids"] == []
    assert result["score"] < 50.0
    assert result["passed"] is False


def test_unclear_required_step_does_not_silently_pass() -> None:
    """必得分点判不清时不能算拿到——那等于用"说不清"换通过。"""
    rubric = compile_step_rubric(_solution_spec(), required_step_ids=["s2"])
    result = score_steps(rubric, _judgements("correct", "unclear", "correct"))

    assert result["missing_required_step_ids"] == ["s2"]
    assert result["passed"] is False


def test_empty_rubric_does_not_pass_by_default() -> None:
    result = score_steps({"steps": []}, _judgements("correct"))
    assert result["passed"] is False
    assert result["score"] == 0.0


# --- 与 J3 的接口对齐 -------------------------------------------------------


@requires_j3
def test_consumes_j3_normalized_judgements_directly() -> None:
    """直接吃 stepwise_answers.normalize_step_judgements 的输出，不做二次约定。

    J3 已保证：未提交的步骤不产生判定、认不出的 verdict 降级 unclear。
    这里复用那份结果，不重新解析学生原始提交。
    """
    from stepwise_answers import extract_steps, normalize_step_judgements

    submitted = extract_steps({"steps": [
        {"step_index": 1, "step_id": "s1", "text": "写出 Q=20kJ, W=8kJ"},
        {"step_index": 2, "step_id": "s2", "text": "ΔU=Q-W=12kJ"},
    ]})
    judgements = normalize_step_judgements(
        [
            {"step_index": 1, "verdict": "correct"},
            {"step_index": 2, "verdict": "correct"},
            # 学生没写第 3 步，J3 会丢弃这条判定
            {"step_index": 3, "verdict": "correct"},
        ],
        submitted,
    )
    assert len(judgements) == 2, "J3 应丢弃未提交步骤的判定"

    rubric = compile_step_rubric(_solution_spec())
    result = score_steps(rubric, judgements)
    assert result["steps"][2]["verdict"] == "missing"
    assert result["score"] == round(200 / 3, 2)


@requires_j3
def test_verdict_vocabulary_matches_j3() -> None:
    """不新增第四种 verdict。"""
    from stepwise_answers import normalize_step_judgements

    submitted = [{"step_index": 1, "step_id": "s1", "text": "x"}]
    judgements = normalize_step_judgements(
        [{"step_index": 1, "verdict": "brilliant"}], submitted,
    )
    assert judgements[0]["verdict"] == "unclear"

    rubric = compile_step_rubric({"steps": ["一"]})
    result = score_steps(rubric, judgements)
    assert result["unresolved_weight"] == 1.0
    assert result["score"] == 0.0
