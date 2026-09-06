"""公开/私有合同边界的常驻守卫（清单 G2）。

## 现状与缺口

边界本身已实现：`PUBLIC_QUESTION_FIELDS`（`assessment_contracts.py:120`）定义
公开字段白名单，答案泄漏检查有三处（质量门 `_answer_leaked`、题目检索正则过滤、
提示泄漏检查）。缺的是**一条常驻的自动化守卫**：

1. 没有一处统一断言"发给学生的题目对象里不得出现答案类字段"。三处检查各查
   各的，新增一个投影函数就可能绕过全部三处；
2. 教师题面修订接口只在 V2 题上拒绝 `answer_spec`
   （`question_bank.revise_question_bank_item`），**旧题仍可经该接口改标准答案**。
   题面修订就该只改题面；改答案要走私有解答合同。

## 这个模块做什么

给出一个可被测试、路由、发布门共同调用的检查，而不是再写第四处正则。
"""

from __future__ import annotations

from typing import Any

# 只要出现在面向学生的对象里就算泄漏的字段名。
#
# 覆盖正式契约（answer_spec / canonical_answer / solution_envelope）与历史
# 别名（correct_answer / hidden_tests）。这里宁可多列——公开对象里出现
# 一个叫 answer 的字段，本身就该被人看一眼。
FORBIDDEN_PUBLIC_FIELDS = frozenset({
    "answer_spec",
    "canonical_answer",
    "acceptable_answers",
    "correct_answer",
    "correct_option_id",
    "correct_option_ids",
    "solution_envelope",
    "solution_spec",
    "solution_graph",
    "worked_solution",
    "solution_trace",
    "hidden_tests",
    "rubric",
    "validator_config",
    "misconception_rules",
    "blank_answers",
})

# 教师「题面修订」接口一律不接受的字段。改答案要走私有解答合同，不是改题面。
TEACHER_PATCH_FORBIDDEN_FIELDS = frozenset({
    "answer_spec",
    "canonical_answer",
    "acceptable_answers",
    "correct_answer",
    "correct_option_id",
    "correct_option_ids",
    "solution_envelope",
    "hidden_tests",
})

MAX_SCAN_DEPTH = 12


def find_answer_leaks(
    value: Any,
    *,
    path: str = "",
    depth: int = 0,
) -> list[str]:
    """递归找出公开对象里的答案类字段，返回它们的路径。

    递归而不是只看顶层：泄漏往往发生在嵌套投影里（例如把整个 item 塞进
    `formal_task.source_item`），只查顶层等于没查。
    """
    if depth > MAX_SCAN_DEPTH:
        return []
    leaks: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_PUBLIC_FIELDS:
                # 只有真的带内容才算泄漏。`_stored_formal_task_from_item` 会把 V2
                # 题的 answer_spec 显式置空（`task["answer_spec"] = {}`）以保持
                # 键的形状稳定；把这种空壳报成泄漏会让守卫天天喊狼来了，真泄漏
                # 反而没人看。
                if _has_content(nested):
                    leaks.append(child_path)
                continue
            leaks.extend(
                find_answer_leaks(nested, path=child_path, depth=depth + 1)
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            leaks.extend(
                find_answer_leaks(
                    nested,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                )
            )
    return leaks


def _has_content(value: Any) -> bool:
    """空字符串、空容器、None 都不算带内容。0 与 False 算。"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def assert_no_answer_leak(value: Any, *, context: str = "public question") -> None:
    """守卫入口：发现泄漏就抛，不返回布尔值。

    返回布尔会让调用方有机会忽略它；答案泄漏不该有"忽略"这个选项。
    """
    leaks = find_answer_leaks(value)
    if leaks:
        raise AssertionError(
            f"{context} leaked private answer fields: {sorted(leaks)}"
        )


def rejected_teacher_patch_fields(patch: dict[str, Any]) -> list[str]:
    """教师题面修订里出现的、不允许经该接口修改的字段。"""
    if not isinstance(patch, dict):
        return []
    return sorted(
        field for field in patch if field in TEACHER_PATCH_FORBIDDEN_FIELDS
    )


__all__ = [
    "FORBIDDEN_PUBLIC_FIELDS",
    "MAX_SCAN_DEPTH",
    "TEACHER_PATCH_FORBIDDEN_FIELDS",
    "assert_no_answer_leak",
    "find_answer_leaks",
    "rejected_teacher_patch_fields",
]
