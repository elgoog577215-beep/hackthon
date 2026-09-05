"""干扰项与易错点的对应关系检查（清单 L2）。

## 这个模块做什么，不做什么

**做**：结构性检查——每个干扰项**能不能说出**它对应哪个易错点，以及那个易错点
是否真的存在于课程知识库里。

**不做**：判断干扰项质量好不好。

这条界限是任务要求，也确实是对的。"这个干扰项是否真的对应学生会犯的错误"、
"三个干扰项是否覆盖了不同的误解而不是同一个误解的三种说法"——这些要教研看题
才能判断，任何自动指标都只能证明"字段填了"，不能证明"填对了"。

所以本模块输出的是**可核查清单**（哪些干扰项没写对应、哪些写了但指向不存在的
易错点），供人工评估使用；它不产出"质量达标"这种结论，调用方也不该把
`declared_ratio == 1.0` 解释成干扰项质量合格——那只说明字段齐全。
"""

from __future__ import annotations

from typing import Any

DISTRACTOR_AUDIT_SCHEMA = "distractor_misconception_audit_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def audit_question_distractors(
    item: dict[str, Any],
    known_misconception_ids: set[str] | None = None,
) -> dict[str, Any]:
    """一道选择题的干扰项对应关系。

    干扰项 = 选项中的非正确项。正确项不需要对应易错点。
    """
    from question_choice_grading import correct_option_ids

    options = [
        option for option in _as_list(item.get("options"))
        if isinstance(option, dict)
    ]
    correct = correct_option_ids(item, item.get("answer_spec") or {})
    known = known_misconception_ids if known_misconception_ids is not None else None

    distractors: list[dict[str, Any]] = []
    for option in options:
        option_id = _text(option.get("id"))
        if not option_id or option_id in correct:
            continue
        declared = [
            _text(value)
            for value in _as_list(option.get("misconception_ids"))
            if _text(value)
        ]
        # 指向知识库里不存在的易错点，与没写一样不可核查——但要分开报，
        # 因为成因不同：一个是漏写，一个是写错。
        dangling = (
            [ref for ref in declared if ref not in known]
            if known is not None
            else []
        )
        distractors.append({
            "option_id": option_id,
            "misconception_ids": declared,
            "declared": bool(declared),
            "dangling_misconception_ids": dangling,
            "resolvable": bool(declared) and not dangling,
        })

    declared_count = sum(1 for item_ in distractors if item_["declared"])
    resolvable_count = sum(1 for item_ in distractors if item_["resolvable"])
    return {
        "schema_version": DISTRACTOR_AUDIT_SCHEMA,
        "revision_id": _text(item.get("revision_id")),
        "distractor_count": len(distractors),
        "declared_count": declared_count,
        "resolvable_count": resolvable_count,
        "undeclared_option_ids": [
            entry["option_id"] for entry in distractors if not entry["declared"]
        ],
        "dangling_option_ids": [
            entry["option_id"]
            for entry in distractors
            if entry["declared"] and entry["dangling_misconception_ids"]
        ],
        "distractors": distractors,
    }


def audit_question_bank_distractors(
    items: list[dict[str, Any]],
    knowledge_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """整个题库的干扰项对应关系清单，供**人工评估**使用。

    刻意不给"质量分"。这里能证明的只有"字段填了、且指向真实存在的易错点"，
    证明不了"这个干扰项真的对应学生会犯的错"——后者要教研看题。
    """
    known = {
        _text(entry.get("misconception_id"))
        for entry in ((knowledge_base or {}).get("misconceptions") or [])
        if isinstance(entry, dict) and _text(entry.get("misconception_id"))
    } if knowledge_base is not None else None

    audits: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _as_list(item.get("options")):
            continue
        audit = audit_question_distractors(item, known)
        if audit["distractor_count"]:
            audits.append(audit)

    total = sum(audit["distractor_count"] for audit in audits)
    declared = sum(audit["declared_count"] for audit in audits)
    resolvable = sum(audit["resolvable_count"] for audit in audits)
    return {
        "schema_version": DISTRACTOR_AUDIT_SCHEMA,
        "question_count": len(audits),
        "distractor_count": total,
        "declared_count": declared,
        "resolvable_count": resolvable,
        # 比例只描述「字段齐全度」，不是质量分。命名刻意避开 score / quality。
        "declared_ratio": round(declared / total, 4) if total else 0.0,
        "resolvable_ratio": round(resolvable / total, 4) if total else 0.0,
        # 供人工评估的待看清单
        "questions_with_undeclared_distractors": [
            audit["revision_id"]
            for audit in audits
            if audit["undeclared_option_ids"]
        ],
        "questions_with_dangling_misconceptions": [
            audit["revision_id"]
            for audit in audits
            if audit["dangling_option_ids"]
        ],
        "audits": audits,
        "assessment_note": (
            "本报告只核查干扰项是否声明了可解析的易错点，"
            "不评价干扰项质量。干扰项是否真的对应学生会犯的错误、"
            "三个干扰项是否覆盖不同误解，需要教研人工评估。"
        ),
    }


__all__ = [
    "DISTRACTOR_AUDIT_SCHEMA",
    "audit_question_bank_distractors",
    "audit_question_distractors",
]
