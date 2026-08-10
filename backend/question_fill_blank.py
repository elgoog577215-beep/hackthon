"""填空题：题干挖空，按空位逐个判定（清单 H1b）。

## 为什么是真缺口

`INPUT_MODES` 里有 `numeric_unit` 和 `short_text`，但没有"题干中挖空、按空位
逐个判定"这个形态。短文本题只有一个整体答案，无法表达"第 2 空对、第 3 空错"，
也就无法做空位级的部分给分与错因定位。

## 判等不从零写

难点是答案等价判定（数值容差、代数等价、多解、单位换算、大小写与同义词）。
这些 `assessment_validators` 已经有了：

- 数值+单位（含换算与容差）：`answers_equivalent("numeric_unit_validator", …)`
- 代数等价（sympy）：`answers_equivalent("symbolic_validator", …)`
- 归一化文本精确匹配：`answers_equivalent("exact_validator", …)`

本模块**只做空位级的编排**：拆题干、对齐空位、逐空调用上面的判等、汇总部分
给分。一条判等规则都不自己实现——自己再写一套就会与正式判定漂移。

## 与答案披露门禁的关系

`blanks` 里带标准答案，属**私有**内容，只能进 `solution_envelope`，绝不能出现在
公开题面。`public_blank_view()` 给出脱敏后的公开投影，`assert_no_answer_leak()`
是给守卫用的显式检查（G2）。
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from assessment_validators import answers_equivalent

FILL_BLANK_SCHEMA = "fill_blank_contract_v1"
FILL_BLANK_RESULT_SCHEMA = "fill_blank_grading_v1"

# 每空可用的判等方式，直接复用正式 validator，不另立口径。
BLANK_MATCH_MODES = (
    "exact",      # 归一化文本精确匹配（大小写、空白无关）
    "numeric",    # 数值+单位，带容差与单位换算
    "symbolic",   # 代数等价
)

# 题干里的空位占位符：{{1}} / {{blank_2}}
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)\s*\}\}")

MAX_BLANKS = 20


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_blank_ids(prompt: str) -> list[str]:
    """按出现顺序取出题干里的空位 ID，重复只算一次。"""
    seen: list[str] = []
    for match in _PLACEHOLDER.finditer(str(prompt or "")):
        blank_id = match.group(1)
        if blank_id not in seen:
            seen.append(blank_id)
    return seen


def compile_fill_blank_contract(
    *,
    prompt: str,
    blanks: list[dict[str, Any]],
) -> dict[str, Any]:
    """编译填空契约，并把结构性错误当场挡住。

    宁可拒绝也不产出一个判不准的填空题：空位对不上、答案缺失、判等方式不认识，
    都会抛 ValueError。这些是出题期就能确定的结构问题，留到学生作答时才发现
    等于让学生替我们试错。
    """
    prompt_text = str(prompt or "")
    declared = parse_blank_ids(prompt_text)
    if not declared:
        raise ValueError("fill_blank prompt must contain at least one {{blank}}")
    if len(declared) > MAX_BLANKS:
        raise ValueError(f"fill_blank supports at most {MAX_BLANKS} blanks")

    compiled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _as_list(blanks):
        if not isinstance(raw, dict):
            raise ValueError("each blank must be an object")
        blank_id = _text(raw.get("blank_id"))
        if not blank_id:
            raise ValueError("blank_id is required")
        if blank_id in seen:
            raise ValueError(f"duplicate blank_id: {blank_id}")
        seen.add(blank_id)
        if blank_id not in declared:
            raise ValueError(
                f"blank {blank_id} is not present in the prompt"
            )
        mode = _text(raw.get("match_mode")) or "exact"
        if mode not in BLANK_MATCH_MODES:
            raise ValueError(f"unsupported blank match_mode: {mode}")
        # 多解：acceptable_answers 里任一命中即算对。
        accepted = [
            value for value in _as_list(raw.get("acceptable_answers"))
            if value is not None and value != ""
        ]
        answer = raw.get("answer")
        if answer is None or answer == "":
            raise ValueError(f"blank {blank_id} has no answer")
        compiled.append({
            "blank_id": blank_id,
            "match_mode": mode,
            "answer": deepcopy(answer),
            "acceptable_answers": deepcopy(accepted),
            "validator_config": deepcopy(raw.get("validator_config") or {}),
            "score_weight": float(raw.get("score_weight") or 1.0),
            "hint": _text(raw.get("hint")),
            # 这一空考的易错点，供 L2 与作答诊断使用。
            "misconception_ids": [
                _text(value)
                for value in _as_list(raw.get("misconception_ids"))
                if _text(value)
            ],
        })

    missing = [blank_id for blank_id in declared if blank_id not in seen]
    if missing:
        raise ValueError(
            f"prompt declares blanks without answers: {missing}"
        )
    return {
        "schema_version": FILL_BLANK_SCHEMA,
        "prompt": prompt_text,
        "blank_ids": declared,
        "blanks": compiled,
    }


_MATCH_MODE_VALIDATORS = {
    "exact": "exact_validator",
    "numeric": "numeric_unit_validator",
    "symbolic": "symbolic_validator",
}


def _blank_matches(blank: dict[str, Any], submitted: Any) -> bool:
    """一空是否判对。多解任一命中即算对。"""
    if submitted is None or _text(submitted) == "":
        return False
    validation_mode = _MATCH_MODE_VALIDATORS[str(blank["match_mode"])]
    config = blank.get("validator_config") or {}
    candidates = [blank["answer"], *blank.get("acceptable_answers", [])]
    return any(
        answers_equivalent(validation_mode, expected, submitted, config)
        for expected in candidates
    )


def grade_fill_blank(
    contract: dict[str, Any],
    submission: dict[str, Any] | None,
) -> dict[str, Any]:
    """逐空判定并汇总。

    部分给分按 `score_weight` 加权。没作答的空计错但**单独标出来**——"答错"与
    "没答"在诊断上不是一回事，混在一起会把跳过当成误解。
    """
    blanks = contract.get("blanks") or []
    answers = (submission or {}).get("blanks")
    answers = answers if isinstance(answers, dict) else {}

    results: list[dict[str, Any]] = []
    earned = 0.0
    total = 0.0
    for blank in blanks:
        blank_id = str(blank["blank_id"])
        weight = float(blank.get("score_weight") or 1.0)
        total += weight
        submitted = answers.get(blank_id)
        answered = submitted is not None and _text(submitted) != ""
        correct = _blank_matches(blank, submitted) if answered else False
        if correct:
            earned += weight
        results.append({
            "blank_id": blank_id,
            "answered": answered,
            "correct": correct,
            "match_mode": blank["match_mode"],
            "score_weight": weight,
            # 判错时把这一空对应的易错点带出来，供诊断归因；判对不带。
            "misconception_ids": (
                list(blank.get("misconception_ids") or [])
                if answered and not correct
                else []
            ),
        })

    correct_count = sum(1 for item in results if item["correct"])
    return {
        "schema_version": FILL_BLANK_RESULT_SCHEMA,
        "blank_count": len(blanks),
        "answered_count": sum(1 for item in results if item["answered"]),
        "correct_count": correct_count,
        "all_correct": bool(blanks) and correct_count == len(blanks),
        "score": round(100.0 * earned / total, 2) if total else 0.0,
        "results": results,
    }


def public_blank_view(contract: dict[str, Any]) -> dict[str, Any]:
    """公开题面投影：只留题干与空位位置，绝不带标准答案。"""
    return {
        "schema_version": FILL_BLANK_SCHEMA,
        "prompt": str(contract.get("prompt") or ""),
        "blanks": [
            {
                "blank_id": str(blank["blank_id"]),
                "match_mode": str(blank["match_mode"]),
                # hint 是给学生的引导，不是答案；仍然经过泄漏检查。
                "hint": str(blank.get("hint") or ""),
            }
            for blank in contract.get("blanks") or []
        ],
    }


def assert_no_answer_leak(public_view: dict[str, Any]) -> None:
    """守卫用：公开投影里出现答案字段就是 bug，直接抛。"""
    forbidden = {"answer", "acceptable_answers", "validator_config"}
    for blank in public_view.get("blanks") or []:
        leaked = forbidden.intersection(blank)
        if leaked:
            raise AssertionError(
                f"fill_blank public view leaked answer fields: {sorted(leaked)}"
            )


__all__ = [
    "BLANK_MATCH_MODES",
    "FILL_BLANK_RESULT_SCHEMA",
    "FILL_BLANK_SCHEMA",
    "MAX_BLANKS",
    "assert_no_answer_leak",
    "compile_fill_blank_contract",
    "grade_fill_blank",
    "parse_blank_ids",
    "public_blank_view",
]
