"""填空判等的逐空取证记录：把独立求解器的原始答案与标准答案对照下来。

## 为什么单独一个模块，而不是塞进 `_assessment_generation_audit`

逐空对照必须记下**标准答案原文**才有归因价值——`-14 kJ` vs `-14` 这种差别，
存成哈希就什么也看不出来。而 `_assessment_generation_audit` 会被
`build_question_bank` 原样投影进题库 payload（`question_bank.py` 的
`generation_audit` 字段），把标准答案塞进去等于给答案披露门禁开一个后门。

所以走**进程内 sink**：默认没有 sink，`record_comparison` 是 no-op，
生产路径不产生任何数据、不落盘、不进任何 payload；只有核查脚本显式
`install_sink()` 时才收集，进程结束即消失。

## 分类只做能确定的那部分

`classify_blank_mismatch` 把不一致分成若干**可由代码确定**的类：数值相同但单位
或写法不同、数值本身不同、文本归一化后相同、文本互为子串。

**剩下的一类 `text_divergent` 代码判不了**——「减少」vs「下降」是同义词，
「减少」vs「增加」是求解器答错，两者在字符串层面没有任何区别。这一类只做
如实记录并原样导出，由人来读。**不要在这里加同义词表去猜**：那等于把语义
判等从后门放进来，而语义判等已被明确否决。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


DIAGNOSTICS_SCHEMA = "fill_blank_blank_comparison_v1"

# 不一致的类别。`correct` 也记，它是分母。
MISMATCH_KINDS = (
    "correct",
    "no_submission",
    "unit_mismatch",
    "numeric_format",
    "numeric_value_mismatch",
    "shape_mismatch",
    "text_normalization",
    "text_containment",
    "text_divergent",
)

# 归并到用户给的三档病因归属。
#
# - `normalization`：判等预处理问题，修它不动确定性判分口径；
# - `solver_content`：求解器（或标准答案）内容不同，与判等无关；
# - `undecidable`：同义词还是答错，**代码判不了，必须人读**。
CAUSE_BUCKETS = {
    "unit_mismatch": "normalization",
    "numeric_format": "normalization",
    "text_normalization": "normalization",
    "text_containment": "normalization",
    "numeric_value_mismatch": "solver_content",
    "shape_mismatch": "solver_content",
    "no_submission": "solver_content",
    "text_divergent": "undecidable",
}

_NUMBER_HEAD = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*)$",
    re.DOTALL,
)
# 归一化文本时要去掉的标点（中英文都要）。
_PUNCTUATION = str.maketrans(
    "",
    "",
    " \t\r\n,，、。.;；:：!！?？'\"“”‘’()（）[]【】{}《》-_/\\",
)

# sink 为 None 时全模块 no-op。生产路径永远走这条。
_SINK: list[dict[str, Any]] | None = None


def install_sink() -> list[dict[str, Any]]:
    """装上收集器并返回它。核查脚本用；生产路径不调用。"""
    global _SINK
    _SINK = []
    return _SINK


def clear_sink() -> None:
    global _SINK
    _SINK = None


def sink_enabled() -> bool:
    return _SINK is not None


def record_comparison(entry: dict[str, Any]) -> None:
    """记一条逐空对照。没装 sink 就什么也不做。"""
    if _SINK is None:
        return
    _SINK.append(dict(entry))


def _normalize_digits(text: str) -> str:
    """全角数字/符号转半角，并去掉千分位逗号。"""
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace(",", "").replace("，", "")


def split_number_unit(value: Any) -> tuple[float | None, str]:
    """把一个答案拆成（数值, 单位）。拆不出数值就返回 (None, 原文)。

    真机里同一个答案至少有四种写法：`{"value": -14, "unit": "kJ"}`、
    `"-14 kJ"`、`"-14"`、`-14`。归因要能看出「数值相同只差单位」，
    就必须先把它们放到同一个形状上。
    """
    if isinstance(value, bool):
        return None, str(value)
    if isinstance(value, (int, float)):
        return float(value), ""
    if isinstance(value, dict):
        raw_value = value.get("value")
        unit = str(value.get("unit") or "").strip()
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            return float(raw_value), unit
        number, tail = split_number_unit(raw_value)
        return number, (unit or tail)
    if value is None:
        return None, ""
    text = _normalize_digits(str(value)).strip()
    match = _NUMBER_HEAD.match(text)
    if not match:
        return None, text
    try:
        number = float(match.group(1))
    except ValueError:  # pragma: no cover - 正则已保证可解析
        return None, text
    return number, match.group(2).strip()


def normalize_text(value: Any) -> str:
    """判等口径之外的**归因用**归一：去空格标点、全角转半角、大小写折叠。

    比生产判等更宽松是故意的——它要回答的是「这对答案的差别是不是纯写法」，
    不是「这道题算不算对」。**不要把它接进 `question_fill_blank` 的判等**。
    """
    if isinstance(value, dict):
        number, unit = split_number_unit(value)
        value = f"{number}{unit}" if number is not None else str(value)
    text = _normalize_digits(str(value if value is not None else ""))
    return text.translate(_PUNCTUATION).casefold()


def _numbers_close(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= 1e-9 * scale


def classify_blank_mismatch(
    match_mode: str,
    expected: Any,
    submitted: Any,
    *,
    correct: bool,
) -> str:
    """判定这一空的不一致属于哪一类。纯函数，不看上下文，可测。

    `correct` 由生产判等给出，本函数**不重新判对错**——归因工具重判一遍等于
    引入第二把尺子，两把尺子不一致时报告就不可信了。
    """
    if correct:
        return "correct"
    if submitted is None or (
        not isinstance(submitted, (int, float, dict))
        and str(submitted).strip() == ""
    ):
        return "no_submission"

    expected_number, expected_unit = split_number_unit(expected)
    submitted_number, submitted_unit = split_number_unit(submitted)

    if expected_number is not None and submitted_number is not None:
        if not _numbers_close(expected_number, submitted_number):
            return "numeric_value_mismatch"
        if normalize_text(expected_unit) != normalize_text(submitted_unit):
            return "unit_mismatch"
        return "numeric_format"
    if (expected_number is None) != (submitted_number is None):
        return "shape_mismatch"

    expected_text = normalize_text(expected)
    submitted_text = normalize_text(submitted)
    if expected_text == submitted_text:
        return "text_normalization"
    if expected_text and submitted_text and (
        expected_text in submitted_text or submitted_text in expected_text
    ):
        return "text_containment"
    return "text_divergent"


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """把逐空记录汇成分布。**只汇总，不下结论。**"""
    by_kind: dict[str, int] = {}
    by_cause: dict[str, int] = {}
    by_blank_kind: dict[str, int] = {}
    undecidable: list[dict[str, Any]] = []
    outcomes: dict[str, int] = {}
    for entry in entries:
        outcome = str(entry.get("outcome") or "")
        if outcome:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        for blank in entry.get("blanks") or []:
            kind = str(blank.get("mismatch_kind") or "")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if kind == "correct":
                continue
            cause = CAUSE_BUCKETS.get(kind, "unknown")
            by_cause[cause] = by_cause.get(cause, 0) + 1
            declared = str(blank.get("blank_kind") or "")
            by_blank_kind[declared] = by_blank_kind.get(declared, 0) + 1
            if cause == "undecidable":
                undecidable.append({
                    "blank_id": blank.get("blank_id"),
                    "blank_kind": declared,
                    "match_mode": blank.get("match_mode"),
                    "expected": blank.get("expected"),
                    "acceptable_answers": blank.get("acceptable_answers"),
                    "submitted": blank.get("submitted"),
                })
    mismatch_total = sum(by_cause.values())
    return {
        "schema_version": DIAGNOSTICS_SCHEMA,
        "validation_count": len(entries),
        "outcomes": dict(sorted(outcomes.items(), key=lambda kv: -kv[1])),
        "blank_total": sum(by_kind.values()),
        "mismatch_total": mismatch_total,
        "by_mismatch_kind": dict(
            sorted(by_kind.items(), key=lambda kv: -kv[1])
        ),
        "by_cause": dict(sorted(by_cause.items(), key=lambda kv: -kv[1])),
        "mismatch_by_blank_kind": dict(
            sorted(by_blank_kind.items(), key=lambda kv: -kv[1])
        ),
        # 代码判不了的那一类原样导出，供人逐条读。
        "undecidable_pairs": undecidable,
        "undecidable_note": (
            "text_divergent 无法由代码区分「同义词」与「求解器答错」，"
            "必须人工逐条判读；不得据此自动放宽判等。"
        ),
    }


__all__ = [
    "CAUSE_BUCKETS",
    "DIAGNOSTICS_SCHEMA",
    "MISMATCH_KINDS",
    "classify_blank_mismatch",
    "clear_sink",
    "install_sink",
    "normalize_text",
    "record_comparison",
    "sink_enabled",
    "split_number_unit",
    "summarize",
]
