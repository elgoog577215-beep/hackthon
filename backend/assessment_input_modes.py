"""作答输入模式的**唯一真源**（Gap E2）。

## 为什么要单独一个模块

`INPUT_MODES` 此前在三个文件各有一份，且内容不同：

- `assessment_blueprint`：6 项集合（蓝图侧「合法输入模式」）
- `assessment_compiler`：9 项集合（编译侧「合法输入模式」，多三项历史模式）
- `practice_contracts`：`question_type -> 输入模式` 的**映射**（dict，同名不同义）

前两个是同一个概念的两份副本，**内容却不一致**，于是各自把关的门认的模式不同。
实测后果：`practice_contracts` 为 6 种 question_type 产出的
`structured_text` / `code_and_text` / `language_response` 三种模式，
**只在编译侧集合里存在**，而质量门 `_valid_input_contract` 校验的是蓝图侧那 6 项
——于是这 6 种题的输入合同被质量门判为不合法（`INPUT_CONTRACT_MISMATCH`）。

这不是"重复定义"这种整洁性问题，是**两份不一致的白名单导致同一道题在不同门
得到相反结论**。所以合并成一份。

## 边界

第三处（`practice_contracts` 的 dict）**不是同一个概念**，不能合并进来——它是
「题型 → 用哪种作答模式」的映射，值域才是本模块这个集合。它已改名为
`INPUT_MODE_BY_QUESTION_TYPE` 以消除同名歧义，并由测试守卫其值域 ⊆ 本集合。
"""

from __future__ import annotations

# 全系统合法的作答输入模式。
#
# 取并集而非交集：那三项历史模式（structured_text / code_and_text /
# language_response）是 `practice_contracts` 真实产出的值，收窄会让 6 种题型
# 的合同当场变成非法。
INPUT_MODES = {
    "choice",
    "numeric_unit",
    "code",
    "short_text",
    "rich_text",
    "structured_fields",
    # 以下三项仅由 question_type 映射产出，蓝图侧配方不会排它们，
    # 但它们是合法的作答模式，各道门都必须认。
    "structured_text",
    "code_and_text",
    "language_response",
}

__all__ = ["INPUT_MODES"]
