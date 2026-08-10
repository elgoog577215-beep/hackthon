"""多选与判断题（清单 H1a）。

## 现状与缺口

`INPUT_MODES` 里有 `choice`，`input_contract.selection.multiple` 这个开关也早
就存在（`assessment_blueprint.py:438` 恒写 `{"multiple": False}`），作答侧
`selected_option_ids`、判分侧的列表比较也都在。**缺的是：**

1. 出题侧从不产出多选与判断——`selection.multiple` 永远是 False；
2. 多选只有"全对才给分"，无法区分"差一个"与"完全不会"；
3. 判断题没有独立形态，两个选项的题与四选一走同一条路。

## 部分给分口径（已确认，不是我自己定的）

**默认保持全对才给分**，与现状一致，零行为变更；题目可以显式开启部分给分。
开启后按"每漏选按比例扣、错选一个即 0"计：

    正确 {A,C} 选 {A}     -> 50（漏 1/2）
    正确 {A,C} 选 {A,C}   -> 100
    正确 {A,C} 选 {A,B}   -> 0（错选 B）
    正确 {A,C} 选 {A,B,C} -> 0（错选 B）

错选归零的理由：选了错误选项说明概念判断错了，与"漏选"性质不同。把两者
同权（例如按选项逐个记分）会让"多选一个错的"看起来比"少选一个对的"损失更小，
与教学判断相反。

## 边界

判分只做确定性比较，不调模型。选项 ID 归一化后按集合比较，不看顺序。
"""

from __future__ import annotations

from typing import Any

CHOICE_GRADING_SCHEMA = "choice_grading_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _id_set(values: Any) -> set[str]:
    return {_text(item) for item in _as_list(values) if _text(item)}


def is_multiple_choice(question: dict[str, Any]) -> bool:
    contract = question.get("input_contract") or {}
    selection = contract.get("selection") or {}
    return bool(selection.get("multiple"))


def partial_credit_enabled(question: dict[str, Any]) -> bool:
    """题目是否显式开启了多选部分给分。

    默认关闭——开启与否是教学判断，不该由引擎替所有题决定。
    """
    contract = question.get("input_contract") or {}
    selection = contract.get("selection") or {}
    return bool(selection.get("partial_credit"))


def is_choice_question(question: dict[str, Any], answer_spec: dict[str, Any]) -> bool:
    """这道题是否按选项判定。

    判据必须是**选项结构**，不能只看"有没有标准答案"：填空、简答题也有
    `correct_answer`，误判成选择题会让它们的文本答案被当成选项 ID 比较，
    从而全部判错。所以要求要么声明了 choice 输入模式，要么真的带选项列表，
    要么显式给了 option 形态的答案字段。
    """
    contract = question.get("input_contract") or {}
    if _text(contract.get("mode")) == "choice":
        return True
    if is_multiple_choice(question):
        return True
    if _as_list(question.get("options")):
        return True
    spec = answer_spec if isinstance(answer_spec, dict) else {}
    if _id_set(spec.get("correct_option_ids")):
        return True
    return bool(_text(spec.get("correct_option_id")))


def canonical_option_ids(canonical_answer: Any) -> set[str]:
    """把 `solution.canonical_answer` 归一成正确选项 id 集合。

    生成链路上有四处各自解读这个值（质量门、编译器、题库对齐、独立求解比较），
    改动前各写各的，且都只认标量——列表答案在四处分别表现为「硬门不过」
    「correct_option_id 变空」「题目被静默改写成单选」「求解比较失败」。
    统一到这里，四处共用同一条规则。

    支持三种形状，都是链路里真实出现过的：
    - 标量 `"A"`；
    - 列表 `["A", "C"]`（多选）；
    - 对象 `{"selected_option_id": "A"}`。
    """
    if isinstance(canonical_answer, dict):
        single = _text(
            canonical_answer.get("selected_option_id")
            or canonical_answer.get("option_id")
        )
        return {single} if single else set()
    if isinstance(canonical_answer, (list, tuple, set)):
        return _id_set(list(canonical_answer))
    single = _text(canonical_answer)
    return {single} if single else set()


def correct_option_ids(
    question: dict[str, Any],
    answer_spec: dict[str, Any] | None = None,
) -> set[str]:
    """标准答案选项集合。多选与单选统一成集合处理。"""
    spec = answer_spec if isinstance(answer_spec, dict) else (
        question.get("answer_spec") or {}
    )
    ids = _id_set(spec.get("correct_option_ids"))
    if ids:
        return ids
    canonical = spec.get("canonical_answer")
    if isinstance(canonical, list):
        ids = _id_set(canonical)
        if ids:
            return ids
    single = _text(spec.get("correct_option_id")) or _text(
        spec.get("correct_answer")
    )
    if single:
        return {single}
    if isinstance(canonical, dict):
        single = _text(canonical.get("selected_option_id")) or _text(
            canonical.get("option_id")
        )
        if single:
            return {single}
    # 最后看选项自身的 is_correct 标记
    return {
        _text(option.get("id"))
        for option in _as_list(question.get("options"))
        if isinstance(option, dict)
        and option.get("is_correct")
        and _text(option.get("id"))
    }


def selected_option_ids(answer_payload: dict[str, Any]) -> set[str]:
    payload = answer_payload or {}
    ids = _id_set(payload.get("selected_option_ids"))
    if ids:
        return ids
    single = _text(payload.get("selected_option_id"))
    return {single} if single else set()


def grade_choice(
    question: dict[str, Any],
    answer_spec: dict[str, Any],
    answer_payload: dict[str, Any],
) -> dict[str, Any]:
    """确定性判定选择题，含多选部分给分。

    返回结构与 `PracticeGrader._grade_deterministic` 对齐，便于直接替换而不是
    在判分器里再长出一条平行分支。
    """
    expected = correct_option_ids(question, answer_spec)
    selected = selected_option_ids(answer_payload)

    missed = sorted(expected - selected)
    wrong = sorted(selected - expected)
    all_correct = bool(expected) and not missed and not wrong

    multiple = is_multiple_choice(question)
    partial = multiple and partial_credit_enabled(question)

    if all_correct:
        score = 100
    elif not partial:
        score = 0
    elif wrong:
        # 错选归零：选了错误选项是概念判断错误，与漏选性质不同。
        score = 0
    else:
        hit = len(expected) - len(missed)
        score = int(round(100.0 * hit / len(expected))) if expected else 0

    passed = all_correct
    return {
        "status": "graded",
        "score": score,
        "passed": passed,
        "rubric_results": [{
            "criterion": "答案正确",
            "met": passed,
            "score": score,
            "feedback": _feedback(
                all_correct=all_correct,
                missed=missed,
                wrong=wrong,
                partial=partial,
            ),
        }],
        "feedback": _feedback(
            all_correct=all_correct,
            missed=missed,
            wrong=wrong,
            partial=partial,
        ),
        "grading_confidence": 1.0,
        "grading_method": "deterministic",
        "choice_result": {
            "schema_version": CHOICE_GRADING_SCHEMA,
            "multiple": multiple,
            "partial_credit": partial,
            "expected_count": len(expected),
            "selected_count": len(selected),
            "missed_option_ids": missed,
            "wrong_option_ids": wrong,
            # 错选了哪个干扰项 -> 供 L2 与作答诊断做错因归因
            "misconception_ids": _misconception_ids(question, wrong),
        },
    }


def _feedback(
    *,
    all_correct: bool,
    missed: list[str],
    wrong: list[str],
    partial: bool,
) -> str:
    if all_correct:
        return "已达到本题要求"
    if wrong and missed:
        return "存在错选与漏选，请重新判断每个选项是否成立"
    if wrong:
        return "存在错选，请检查被选中的选项是否都成立"
    if missed:
        return (
            "有漏选，已按选中的正确项给分"
            if partial
            else "有漏选，本题需全部选中才算通过"
        )
    return "答案未达到本题要求"


def _misconception_ids(
    question: dict[str, Any],
    wrong_option_ids: list[str],
) -> list[str]:
    """被错选的干扰项对应的易错点（L2 用）。

    只报选项自己声明的易错点，不去猜。声明不了就返回空——空列表意味着
    "这个干扰项没写明对应哪个易错点"，那正是 L2 要暴露的问题。
    """
    wanted = set(wrong_option_ids)
    result: list[str] = []
    for option in _as_list(question.get("options")):
        if not isinstance(option, dict):
            continue
        if _text(option.get("id")) not in wanted:
            continue
        for value in _as_list(option.get("misconception_ids")):
            if _text(value) and _text(value) not in result:
                result.append(_text(value))
    return result


__all__ = [
    "CHOICE_GRADING_SCHEMA",
    "canonical_option_ids",
    "correct_option_ids",
    "is_choice_question",
    "grade_choice",
    "is_multiple_choice",
    "partial_credit_enabled",
    "selected_option_ids",
]
