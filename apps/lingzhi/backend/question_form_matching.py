"""题型与知识点类型的匹配规则（清单 H2）。

## 现状与缺口

已有雏形 `_FAMILY_SLOT_RECIPES`（`assessment_blueprint.py:57`）按 8 个学科族各
硬编码 3 个槽位。但那是**按学科族**分配——同一门数学课里，"导数的定义"与
"求导的步骤"会拿到完全一样的题型配方，尽管前者该考辨析、后者该考执行。

本模块补的是学科族**之上**的一层：按知识点类型（`KNOWLEDGE_TYPES` 的七类）
给出推荐与不推荐的作答形态。

## 定位：建议，不是强制

这层只产出**建议与偏离说明**，不直接改写蓝图槽位。原因有二：

1. 学科族配方是已验收的正式链路，直接覆盖会绕过它的约束；
2. 题型选择最终要教研认可（清单 H2 的验收就是"抽查 20 个知识点，题型选择
   符合规则表且教研认可"）。引擎给建议、人来拍板，比引擎自己改更符合这条。

所以输出里既有 `recommended_forms`，也有 `mismatch_reason`——不匹配时说得出
为什么不匹配，而不是只给一个分数。
"""

from __future__ import annotations

from typing import Any

FORM_MATCH_SCHEMA = "question_form_match_v1"

# 知识点类型 -> 推荐 / 不推荐的作答形态。
#
# 表里的判断都能说出理由，不是凭感觉排的：
# - definition（定义）：要考"能不能把它和相邻概念分开"，辨析型题最直接；
#   让学生写一大段论述反而考不出边界感。
# - principle（原理）：要考"能不能用它解释/推出结论"，需要展开过程。
# - rule（规则）：判定题最直接——给一个情形，问规则成不成立。
# - method / procedure（方法/步骤）：必须真的做一遍，选择题只能考"认得出"，
#   考不出"做得对"。
# - condition（成立条件）：本质是判断题——条件满足与否。
# - representation（表示法）：考"能不能正确读写这种表示"，填空与结构化最贴。
_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "definition": {
        "recommended": ("single_choice", "true_false", "fill_blank"),
        "discouraged": ("coding", "essay"),
        "reason": "定义考的是与相邻概念的边界，辨析型题最直接；长文写作考不出边界感。",
    },
    "principle": {
        "recommended": ("essay", "structured", "numeric"),
        "discouraged": ("true_false",),
        "reason": "原理要考能否用它解释或推出结论，需要展开过程；判断题只能考记忆。",
    },
    "rule": {
        "recommended": ("true_false", "single_choice", "multiple_choice"),
        "discouraged": ("essay",),
        "reason": "规则考的是「这个情形下成不成立」，判定型题最直接。",
    },
    "method": {
        "recommended": ("numeric", "structured", "coding", "essay"),
        "discouraged": ("true_false", "single_choice"),
        "reason": "方法必须真的执行一遍；选择题只能考「认得出」，考不出「做得对」。",
    },
    "procedure": {
        "recommended": ("structured", "coding", "numeric"),
        "discouraged": ("true_false", "single_choice"),
        "reason": "步骤要考能否按顺序正确执行，需要逐步产出而不是选一个答案。",
    },
    "condition": {
        "recommended": ("true_false", "single_choice", "fill_blank"),
        "discouraged": ("coding",),
        "reason": "成立条件本质是判断：条件满足与否。",
    },
    "representation": {
        "recommended": ("fill_blank", "structured", "single_choice"),
        "discouraged": ("essay",),
        "reason": "表示法考的是能否正确读写该表示，填空与结构化作答最贴。",
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def recommended_forms(knowledge_type: str) -> tuple[str, ...]:
    rule = _RULES.get(_text(knowledge_type))
    return tuple(rule["recommended"]) if rule else ()


def discouraged_forms(knowledge_type: str) -> tuple[str, ...]:
    rule = _RULES.get(_text(knowledge_type))
    return tuple(rule["discouraged"]) if rule else ()


def evaluate_form_match(
    *,
    knowledge_type: str,
    question_form: str,
) -> dict[str, Any]:
    """判断某个知识点类型配某种作答形态是否合适。

    三档而不是两档：`match` / `acceptable` / `mismatch`。中间那档很重要——
    规则表只列了明确推荐与明确不推荐，**其余一律算可接受**，不能把"没列进
    推荐表"直接当成"不合适"。表本身不完备，把未知当错误会制造大量假警报。
    """
    normalized_type = _text(knowledge_type)
    normalized_form = _text(question_form)
    rule = _RULES.get(normalized_type)
    if not rule or not normalized_form:
        return _result(
            "unknown",
            knowledge_type=normalized_type,
            question_form=normalized_form,
            reason=(
                "未知知识点类型，不做匹配判断"
                if not rule
                else "缺少作答形态，不做匹配判断"
            ),
        )
    if normalized_form in rule["recommended"]:
        return _result(
            "match",
            knowledge_type=normalized_type,
            question_form=normalized_form,
            reason=str(rule["reason"]),
        )
    if normalized_form in rule["discouraged"]:
        return _result(
            "mismatch",
            knowledge_type=normalized_type,
            question_form=normalized_form,
            reason=str(rule["reason"]),
        )
    return _result(
        "acceptable",
        knowledge_type=normalized_type,
        question_form=normalized_form,
        reason="不在明确推荐或不推荐之列，按可接受处理。",
    )


def _result(
    verdict: str,
    *,
    knowledge_type: str,
    question_form: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": FORM_MATCH_SCHEMA,
        "verdict": verdict,
        "knowledge_type": knowledge_type,
        "question_form": question_form,
        "recommended_forms": list(recommended_forms(knowledge_type)),
        "reason": reason,
    }


def review_question_form_matches(
    items: list[dict[str, Any]],
    knowledge_base: dict[str, Any] | None,
) -> dict[str, Any]:
    """对一批题做匹配复核，给出建议而不是直接改写。

    只看题目已绑定的知识点（G4 之后那些是知识库里真实存在的 ID）。绑定不到
    知识点、或知识点没写 knowledge_type 时如实记为 unknown，不猜类型。
    """
    points = {
        _text(point.get("knowledge_id")): point
        for point in ((knowledge_base or {}).get("knowledge_points") or [])
        if isinstance(point, dict) and _text(point.get("knowledge_id"))
    }
    reviews: list[dict[str, Any]] = []
    counts = {"match": 0, "acceptable": 0, "mismatch": 0, "unknown": 0}

    for item in items:
        if not isinstance(item, dict):
            continue
        form = _text(item.get("question_form"))
        refs = [
            _text(value)
            for value in (
                item.get("course_knowledge_refs")
                or item.get("concept_ids")
                or []
            )
            if _text(value)
        ]
        types = [
            _text(points[ref].get("knowledge_type"))
            for ref in refs
            if ref in points and _text(points[ref].get("knowledge_type"))
        ]
        if not types:
            counts["unknown"] += 1
            reviews.append({
                "revision_id": _text(item.get("revision_id")),
                "question_form": form,
                "verdict": "unknown",
                "reason": "题目未绑定带类型的知识点，无法判断匹配",
            })
            continue
        # 一道题可能绑多个知识点：只要与其中之一匹配就算匹配，全部不推荐才算
        # 不匹配——按最宽松的那个知识点判，避免因为附带绑定而误报。
        verdicts = [
            evaluate_form_match(knowledge_type=item_type, question_form=form)
            for item_type in types
        ]
        best = _best_verdict(verdicts)
        counts[best["verdict"]] = counts.get(best["verdict"], 0) + 1
        reviews.append({
            "revision_id": _text(item.get("revision_id")),
            "question_form": form,
            "knowledge_type": best["knowledge_type"],
            "verdict": best["verdict"],
            "recommended_forms": best["recommended_forms"],
            "reason": best["reason"],
        })

    return {
        "schema_version": FORM_MATCH_SCHEMA,
        "reviewed_count": len(reviews),
        "counts": counts,
        "mismatches": [
            review for review in reviews if review["verdict"] == "mismatch"
        ],
        "reviews": reviews,
    }


_VERDICT_ORDER = {"match": 0, "acceptable": 1, "unknown": 2, "mismatch": 3}


def _best_verdict(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    return min(verdicts, key=lambda item: _VERDICT_ORDER[item["verdict"]])


__all__ = [
    "FORM_MATCH_SCHEMA",
    "discouraged_forms",
    "evaluate_form_match",
    "recommended_forms",
    "review_question_form_matches",
]
