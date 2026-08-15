"""题型的规范形态（清单 H1d）。

## 为什么要单独一层

上游有一套三层正交的题型体系：输入模式 `INPUT_MODES`（choice / numeric_unit /
short_text / rich_text / structured_fields / code）× 练习层级 × `question_type`
（约 20 个取值，按学科族定义，如 `selected_response` / `structured_application` /
`scenario_deliverable` / `performance_task`）。

问题在于 `question_type` 表达的是**学科教学意图**，不是**作答形态**。实测一门真实
课程的题库：6 道题有 5 种 `question_type`，但作答形态其实只有 3 种（choice /
structured_fields / rich_text）。反过来教师问的是"这门课填空题占比多少"——这个
问题在现有字段上答不了：既不能按 `question_type` 答（它按学科族分裂），也不能按
`input_mode` 答（choice 里混着单选和多选，短文本里混着填空和简答）。

而且教师导入路径 `_imported_item` 还在**仅凭有没有 options** 把题压成
`single_choice` / `short_answer` 两态，把导入题的真实形态直接丢掉。

所以这里补一个**规范作答形态** `question_form`：与学科无关，只回答"学生要怎么
作答、怎么判分"。它是 H1a（多选/判断）与 H1b（填空）能在题库里被看见的前置——
不加这一层，新增的题型落库后仍然只是又一个 `question_type` 字符串，题库统计
里看不出区别。

## 边界

- 不改 `question_type`，不动上游三层体系。这里只是**投影**，不是第二真源。
- 不猜：判定只看 `input_contract.mode`、`options`、`answer_spec` 这些已有的
  结构化事实，取不到就落 `unspecified` 并说明，不按题干文本瞎猜。
"""

from __future__ import annotations

from typing import Any

QUESTION_FORM_SCHEMA = "question_form_v1"

# 规范作答形态。与学科无关，只描述"怎么作答、怎么判分"。
QUESTION_FORMS = (
    "single_choice",      # 单选：一个正确选项
    "multiple_choice",    # 多选：多个正确选项（H1a）
    "true_false",         # 判断（H1a）
    "fill_blank",         # 填空：题干挖空、按空位逐个判定（H1b）
    "numeric",            # 数值（可带单位）
    "short_answer",       # 简答：自由短文本
    "essay",              # 大题/长文本，走量规
    "structured",         # 结构化多字段作答
    "coding",             # 代码实现，走 runner
    "unspecified",        # 判定不了，如实标记
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def classify_question_form(item: dict[str, Any]) -> str:
    """按已有的结构化事实判定规范作答形态。

    判定顺序是从"最确定"到"最含糊"：显式声明 > 输入模式 + 答案结构 > 选项形状。
    任何一步都不看题干文本——按文本猜形态会在题干里出现"选择"二字时误判。
    """
    explicit = _text(item.get("question_form"))
    if explicit in QUESTION_FORMS:
        return explicit

    spec = item.get("question_spec") if isinstance(item.get("question_spec"), dict) else {}
    input_contract = spec.get("input_contract") or item.get("input_contract") or {}
    mode = _text(input_contract.get("mode") if isinstance(input_contract, dict) else "")
    answer_spec = item.get("answer_spec") if isinstance(item.get("answer_spec"), dict) else {}
    answer_type = _text(answer_spec.get("type"))
    options = _as_list(item.get("options") or spec.get("options"))

    if mode == "code" or answer_type == "code":
        return "coding"
    if mode == "structured_fields":
        return "structured"
    if mode == "numeric_unit":
        return "numeric"

    # 填空要在选择之前判，因为填空题也可能给候选词表。
    if _is_fill_blank(item, spec, input_contract, answer_type):
        return "fill_blank"

    if mode == "choice" or options:
        # 先认合同声明的 selection。
        #
        # V2 题的 answer_spec 在落库时被显式置空（私有答案存在
        # solution_envelopes 里），只看答案就永远判不出多选——真机实测一道
        # 合同已声明 multiple=True 的题被分类成 single_choice。
        selection = input_contract.get("selection") if isinstance(
            input_contract, dict
        ) else None
        if isinstance(selection, dict):
            if selection.get("multiple"):
                return "multiple_choice"
            if selection.get("true_false"):
                return "true_false"
        return _choice_form(options, answer_spec)

    if mode == "rich_text":
        return "essay"
    if mode == "short_text":
        return "short_answer"
    if answer_type in {"exact", "numeric"}:
        return "numeric" if answer_type == "numeric" else "short_answer"
    if answer_type == "rubric":
        return "essay"
    return "unspecified"


def _is_fill_blank(
    item: dict[str, Any],
    spec: dict[str, Any],
    input_contract: Any,
    answer_type: str,
) -> bool:
    """填空：题干有编号空位，且答案按空位给出。

    只认结构化信号——`blanks` 字段，或按空位组织的答案列表。不靠在题干里数
    下划线：正文里的下划线可能只是排版。
    """
    if answer_type == "fill_blank":
        return True
    for holder in (item, spec):
        if isinstance(holder, dict) and _as_list(holder.get("blanks")):
            return True
    if isinstance(input_contract, dict):
        if _text(input_contract.get("mode")) == "fill_blank":
            return True
        # 认「有没有这个键」而不是「列表空不空」。
        #
        # 填空槽位的公开合同里 blanks 是个占位空列表——真正的空位答案是私有的，
        # 存在 solution_envelope 里。按空列表判会把一道真填空题分类成 short_answer，
        # 真机实测就是这样：契约编译通过、判分五条用例全对，分类却说不是填空。
        if "blanks" in input_contract:
            return True
    answer_spec = item.get("answer_spec")
    if isinstance(answer_spec, dict) and _as_list(answer_spec.get("blank_answers")):
        return True
    return False


def _choice_form(options: list[Any], answer_spec: dict[str, Any]) -> str:
    """单选 / 多选 / 判断。

    判断题按"两个选项且是一对是非表述"识别，而不是靠 question_type 里有没有
    true_false —— 上游根本不产出那个标识符（H1a 的现状）。
    """
    correct_ids = {
        _text(value)
        for value in _as_list(answer_spec.get("correct_option_ids"))
        if _text(value)
    }
    if not correct_ids:
        single = _text(answer_spec.get("correct_option_id"))
        if single:
            correct_ids = {single}
    if not correct_ids:
        correct_ids = {
            _text(option.get("id"))
            for option in options
            if isinstance(option, dict)
            and option.get("is_correct")
            and _text(option.get("id"))
        }
    if len(correct_ids) > 1:
        return "multiple_choice"
    if len(options) == 2 and _looks_like_true_false(options):
        return "true_false"
    return "single_choice"


_TRUE_FALSE_TOKENS = (
    {"正确", "错误"},
    {"对", "错"},
    {"是", "否"},
    {"true", "false"},
    {"t", "f"},
)


def _looks_like_true_false(options: list[Any]) -> bool:
    texts = {
        _text(option.get("text") if isinstance(option, dict) else option).lower()
        for option in options
    }
    texts = {value for value in texts if value}
    if len(texts) != 2:
        return False
    return any(texts == {token.lower() for token in pair} for pair in _TRUE_FALSE_TOKENS)


def question_form_distribution(items: list[dict[str, Any]]) -> dict[str, int]:
    """题库按规范作答形态的分布。

    教师问的"这门课填空题占比多少"由这里回答。只统计出现过的形态，不给一堆
    恒为 0 的键。
    """
    result: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        form = classify_question_form(item)
        result[form] = result.get(form, 0) + 1
    return dict(sorted(result.items()))


__all__ = [
    "QUESTION_FORMS",
    "QUESTION_FORM_SCHEMA",
    "classify_question_form",
    "question_form_distribution",
]
