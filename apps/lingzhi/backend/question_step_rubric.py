"""大题分步量规（清单 H1c）。

## 与 lz-assess-ux J3 的分工（先读了他们的代码再动手，不重复建模）

J3（`stepwise_answers.py`，dev/lz-assess-ux `87427056`）已经做完**作答侧**：

- `answer_payload.steps` 加法式扩展，旧数据零迁移；
- `extract_steps` / `merged_answer_text` 归一化；
- `normalize_step_judgements` 把模型给的逐步判定绑回学生真实写下的步骤，
  未提交的步骤一律丢弃判定，认不出的降级 `unclear` 而非通过；
- `stepwise_summary` 汇总，给出 `first_flawed_step_index`；
- `stepwise_enabled` 读 `input_contract.stepwise`。

**这些一个都不重做。** 本模块只补他们没有的那一半——**出题侧的分步量规**：

| 谁负责 | 内容 |
| --- | --- |
| J3（已完成） | 学生怎么提交步骤、模型判定怎么绑回步骤、汇总口径 |
| H1c（本模块） | 每步值多少分、哪些步骤是必得分点、按步骤加权算总分 |

J3 的汇总只给出 correct/flawed/unclear 的**计数**，判分仍是整体量规的一个分数。
大题需要的是"第 2 步错了扣多少、第 3 步是不是关键步骤"——那要一份出题期就
定好的量规，学生作答时才能按步给分。

## 口径

- 复用 J3 的 verdict 三态，不新增第四态。
- `unclear` **不给分也不判错**：模型说不清时既不能白送分，也不该当作学生错了。
  它计入 `unresolved_weight`，让"分数偏低是因为判不清"这件事可见。
- 未提交的步骤不给分（J3 已保证不会为它们产生判定）。
- 必得分点（`required`）未判对时，整题不算通过，无论加权分多少——防止靠若干
  边角步骤凑够分数却漏掉关键推导。
"""

from __future__ import annotations

from typing import Any

STEP_RUBRIC_SCHEMA = "stepwise_rubric_v1"
STEP_SCORE_SCHEMA = "stepwise_score_v1"

MAX_RUBRIC_STEPS = 20


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compile_step_rubric(
    solution_spec: dict[str, Any] | None,
    *,
    weights: dict[str, float] | None = None,
    required_step_ids: list[str] | None = None,
) -> dict[str, Any]:
    """从私有解答的步骤编译分步量规。

    步骤来源是 `solution_contracts.project_solution_spec` 的 `step_details`
    （出题期已有的私有解答步骤），不另建一份步骤真源。默认等权——权重是教研
    判断，没有依据时不该由引擎编造差异。
    """
    spec = solution_spec if isinstance(solution_spec, dict) else {}
    details = _as_list(spec.get("step_details"))[:MAX_RUBRIC_STEPS]
    if not details:
        # 只有纯文本步骤时也能编译，但拿不到 step_id，用位置兜底。
        details = [
            {"step_id": f"step_{index}", "explanation": _text(value)}
            for index, value in enumerate(
                _as_list(spec.get("steps"))[:MAX_RUBRIC_STEPS], start=1,
            )
            if _text(value)
        ]

    declared_weights = weights or {}
    required = {_text(value) for value in required_step_ids or [] if _text(value)}
    steps: list[dict[str, Any]] = []
    for position, detail in enumerate(details, start=1):
        if not isinstance(detail, dict):
            continue
        step_id = _text(detail.get("step_id")) or f"step_{position}"
        weight = float(declared_weights.get(step_id, 1.0))
        if weight <= 0:
            continue
        steps.append({
            "step_index": position,
            "step_id": step_id,
            "title": _text(detail.get("title")) or f"步骤 {position}",
            "weight": weight,
            "required": step_id in required,
            # 这一步考什么，用于失分时给出可解释的反馈。
            "criterion": _text(detail.get("explanation"))[:500],
        })
    return {
        "schema_version": STEP_RUBRIC_SCHEMA,
        "step_count": len(steps),
        "total_weight": sum(step["weight"] for step in steps),
        "steps": steps,
    }


def score_steps(
    rubric: dict[str, Any],
    judgements: list[dict[str, Any]],
) -> dict[str, Any]:
    """按分步量规对 J3 的逐步判定加权算分。

    `judgements` 直接吃 `stepwise_answers.normalize_step_judgements` 的输出，
    格式不做二次约定——那会变成第二套判定口径。
    """
    steps = _as_list(rubric.get("steps"))
    by_index = {
        int(item["step_index"]): item
        for item in steps
        if isinstance(item, dict) and item.get("step_index") is not None
    }
    verdicts = {
        int(item["step_index"]): _text(item.get("verdict"))
        for item in _as_list(judgements)
        if isinstance(item, dict) and item.get("step_index") is not None
    }

    total_weight = sum(float(step["weight"]) for step in by_index.values())
    earned = 0.0
    unresolved = 0.0
    missing_required: list[str] = []
    breakdown: list[dict[str, Any]] = []

    for index in sorted(by_index):
        step = by_index[index]
        weight = float(step["weight"])
        verdict = verdicts.get(index, "missing")
        if verdict == "correct":
            earned += weight
        elif verdict == "unclear":
            # 判不清既不给分也不算错——但要让它可见，否则低分会被误读成学生错了。
            unresolved += weight
        if step.get("required") and verdict != "correct":
            missing_required.append(str(step["step_id"]))
        breakdown.append({
            "step_index": index,
            "step_id": step["step_id"],
            "title": step["title"],
            "weight": weight,
            "required": bool(step.get("required")),
            "verdict": verdict,
            "earned": weight if verdict == "correct" else 0.0,
        })

    score = round(100.0 * earned / total_weight, 2) if total_weight else 0.0
    # 通过 = 有量规 + 所有必得分点判对 + 至少拿到一半加权分。
    #
    # 两个条件缺一不可：只看必得分点会让"关键步骤对、其余全错"算通过；只看
    # 分数会让"边角步骤凑够一半、关键推导没做"算通过。分开写而不是塞进一个
    # 表达式——这条口径以后要被人读。
    passed = bool(by_index) and not missing_required and score >= 50.0
    return {
        "schema_version": STEP_SCORE_SCHEMA,
        "step_count": len(by_index),
        "scored_step_count": sum(
            1 for item in breakdown if item["verdict"] == "correct"
        ),
        "score": score,
        "total_weight": total_weight,
        "earned_weight": earned,
        # 因判不清而未计入的权重——分数偏低时先看这个，再看是不是学生错了。
        "unresolved_weight": unresolved,
        "missing_required_step_ids": missing_required,
        "passed": passed,
        "steps": breakdown,
    }


__all__ = [
    "MAX_RUBRIC_STEPS",
    "STEP_RUBRIC_SCHEMA",
    "STEP_SCORE_SCHEMA",
    "compile_step_rubric",
    "score_steps",
]
