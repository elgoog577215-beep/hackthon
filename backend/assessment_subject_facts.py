"""学科事实检查插件（清单 N1）。

## 为什么单独一个模块

通用质量门 `assessment_quality` 里原本硬编码了两条 Unity 专用检查
（`UNITY_FIXEDUPDATE_RATE_INVALID` / `UNITY_SPEED_STEP_MISMATCH`）与它们的
正则。问题不是这两条检查错——它们抓的是真实的事实性错误（把 FixedUpdate 默认
频率说成 60 Hz，实际 fixedDeltaTime 默认 0.02 秒即 50 Hz），而是**通用引擎里的
单课程特例会误导后来者也往里加**：下一个学科来一条，质量门就多一段 if。

所以把它们移出来，改成注册表：通用门只负责"跑一遍已注册的学科检查"，具体
学科知识住在自己的检查器里。新增学科检查在这里注册，不再去动通用门。

## 边界

- 检查器只做**高置信度的事实矛盾**判定，靠确定性正则，不调模型。判不准就
  不报——质量门是硬门，误报会挡掉正确的题。
- 每个检查器自己声明触发条件（`applies`），不适用就直接跳过，避免把一个学科的
  正则套到另一个学科的题面上。
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable

SubjectFactChecker = Callable[[str, str], list[dict[str, Any]]]

# 学科事实检查会产出的 issue code。通用门用它做可修复性判定。
SUBJECT_FACT_ISSUE_CODES = frozenset({
    "UNITY_FIXEDUPDATE_RATE_INVALID",
    "UNITY_SPEED_STEP_MISMATCH",
})


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": deepcopy(evidence or {}),
    }


# --- Unity ------------------------------------------------------------------

_UNITY_MARKERS = ("unity", "moveposition", "rigidbody")

_UNITY_INVALID_RATE_PATTERNS = (
    r"fixedupdate[^。；;\n]{0,40}(?:默认|通常|至少)"
    r"[^。；;\n]{0,24}(?:60\s*(?:hz|次)|每秒\s*60)",
    r"(?:默认|通常)[^。；;\n]{0,24}fixedupdate"
    r"[^。；;\n]{0,24}(?:60\s*(?:hz|次)|每秒\s*60)",
    r"fixedupdate[^.;\n]{0,40}(?:default|normally|at least)"
    r"[^.;\n]{0,24}60\s*(?:hz|times)",
)


def _unity_applies(question_text: str, solution_text: str) -> bool:
    combined = f"{question_text}\n{solution_text}".casefold()
    if "fixedupdate" not in combined:
        return False
    return any(marker in combined for marker in _UNITY_MARKERS)


def check_unity_lifecycle_facts(
    question_text: str,
    solution_text: str,
) -> list[dict[str, Any]]:
    """Unity 时序事实矛盾，确定性判定，不调模型。"""
    if not _unity_applies(question_text, solution_text):
        return []

    issues: list[dict[str, Any]] = []
    if any(
        re.search(pattern, solution_text, flags=re.IGNORECASE)
        for pattern in _UNITY_INVALID_RATE_PATTERNS
    ):
        issues.append(_issue(
            "UNITY_FIXEDUPDATE_RATE_INVALID",
            "critical",
            (
                "解答把默认 FixedUpdate 频率描述为 60 Hz；"
                "默认 fixedDeltaTime 通常为 0.02 秒，即 50 Hz。"
            ),
            evidence={
                "expected_default_fixed_delta_time": 0.02,
                "expected_default_rate_hz": 50,
            },
        ))

    csharp_blocks = re.findall(
        r"```(?:csharp|cs)\s*\n([\s\S]*?)```",
        question_text,
        flags=re.IGNORECASE,
    )
    if any(
        _has_unscaled_moveposition_speed_step(block)
        for block in csharp_blocks
    ) and "fixeddeltatime" not in solution_text.casefold():
        issues.append(_issue(
            "UNITY_SPEED_STEP_MISMATCH",
            "critical",
            (
                "题面把 speed 直接作为 MovePosition 的单次位移，"
                "但解答未用 Time.fixedDeltaTime 将每秒速度换算为单步位移。"
            ),
            evidence={"required_term": "Time.fixedDeltaTime"},
        ))
    return issues


def _has_unscaled_moveposition_speed_step(value: str) -> bool:
    if not re.search(
        r"\b(?:public|private|protected|internal)?\s*float\s+speed\b",
        value,
        flags=re.IGNORECASE,
    ):
        return False
    calls = re.findall(
        r"\bMovePosition\s*\(([^;\n]{1,400})\)\s*;",
        value,
        flags=re.IGNORECASE,
    )
    return any(
        ".position" in call.casefold()
        and re.search(r"\bspeed\b", call, flags=re.IGNORECASE)
        and "fixeddeltatime" not in call.casefold()
        for call in calls
    )


# --- 注册表 -----------------------------------------------------------------

# 新增学科检查在这里登记，不要再往通用质量门里塞 if。
SUBJECT_FACT_CHECKERS: tuple[SubjectFactChecker, ...] = (
    check_unity_lifecycle_facts,
)


def subject_fact_issues(
    question_text: str,
    solution_text: str,
    *,
    checkers: tuple[SubjectFactChecker, ...] | None = None,
) -> list[dict[str, Any]]:
    """跑一遍已注册的学科事实检查。

    单个检查器抛异常不该让整道题的质量评估崩掉——那会把"某学科正则写错"升级成
    "所有题都过不了门"。异常按"这条检查没结论"处理，其余检查照跑。
    """
    issues: list[dict[str, Any]] = []
    for checker in checkers if checkers is not None else SUBJECT_FACT_CHECKERS:
        try:
            issues.extend(checker(question_text, solution_text) or [])
        except Exception:  # noqa: BLE001 - 一条检查失效不该阻断全部出题
            continue
    return issues


__all__ = [
    "SUBJECT_FACT_CHECKERS",
    "SUBJECT_FACT_ISSUE_CODES",
    "SubjectFactChecker",
    "check_unity_lifecycle_facts",
    "subject_fact_issues",
]
