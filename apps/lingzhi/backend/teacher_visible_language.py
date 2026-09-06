"""教师可见文本的通用语言检查。

这里只识别把系统设计话语误写进教学文本的明确组合，
不禁止“闭合运算”“冻结切片”等学科本身的正常用词。
"""

from __future__ import annotations

import re


UNNATURAL_SYSTEM_LANGUAGE_PATTERN = re.compile(
    r"冻结(?:(?:知识)?边界|成果标准|知识职责|课程范围|任务范围|课程结构)|"
    r"(?:证据|职责|任务|流程)闭环|"
    r"(?:证据|职责|任务|流程)闭合|"
    r"结构性阻力|"
    r"形成(?:价值|能力|教学)抓手|"
    r"拉通(?:教学)?(?:链路|流程)|"
    r"收口(?:问题|任务)"
)


def has_unnatural_system_language(value: object) -> bool:
    return bool(UNNATURAL_SYSTEM_LANGUAGE_PATTERN.search(str(value or "")))


__all__ = [
    "UNNATURAL_SYSTEM_LANGUAGE_PATTERN",
    "has_unnatural_system_language",
]
