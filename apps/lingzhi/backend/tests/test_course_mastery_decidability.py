"""掌握标准必须可判定，两个枚举字段必须真的被选择（需求 C2）。

C2 要求抽样评估实际填充质量。我对仓库里 5 门真实课程的全部 146 条掌握标准做了
统计，结论分两半：

- **自由文本字段基本可判定**。`observable_performance` 与 `verification_method`
  多数确实说清了"用什么题、什么作答表现算达标"，例如"独立计算至少 5 个不同的
  2×2 矩阵的行列式，全部正确"／"随机给出 5 个 2×2 矩阵，要求写出行列式值"。
  只有 25% (37/146) 给出了可数阈值，其余靠自然语言描述，属于可改进但不算失效。
- **两个枚举字段完全失效**：`required_independence` 在 146/146 条上都是
  `independent`，`required_transfer` 在 142/146 条上都是 `variation`。

失效的根因不在编译层，而在 prompt：JSON Schema 示例里这两个字段被写死成
`"independent"` / `"variation"`，模型照抄示例即可，从来没有被要求做选择。编译层
的 `or "independent"` 兜底又让"模型没填"和"模型选了这个值"无法区分。

所以本文件锁的是 prompt 侧的修复：示例不再给单一定值、约束里给出取值范围与语义。
这里不断言真实课程的分布会变——那要重生成课程才能验证，属于验收动作，不是单测
能覆盖的范围。
"""

from __future__ import annotations

import re

from course_generation.prompts import CoursePromptComposer

INDEPENDENCE_VALUES = ("scaffolded", "guided", "independent")
TRANSFER_VALUES = ("recall", "procedure", "variation", "novel")


def _prompt() -> str:
    return CoursePromptComposer().build_teaching_plan_batch_v3_prompt(
        course_title="矩阵与线性变换",
        positioning="能用矩阵刻画并计算线性变换",
        batch_spec={"batch_id": "batch-1", "section_ids": ["L2-1-1"]},
        batch_sections=[{
            "node_id": "L2-1-1",
            "title": "行列式",
            "learning_objective": "能计算二阶行列式并解释其几何意义",
            "allowed_module_ids": ["core_explanation"],
        }],
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "二阶行列式",
            "statement": "二阶行列式等于主对角线之积减副对角线之积。",
            "owner_node_id": "L2-1-1",
        }],
        section_identities=[{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
        module_catalog=[{"module_id": "core_explanation", "label": "核心教学"}],
        skeleton_revision_id="skeleton-1",
    )


def _schema_section(prompt: str) -> str:
    return prompt[prompt.index("## JSON Schema"):]


def _constraints(prompt: str) -> str:
    return prompt[prompt.index("## 约束"): prompt.index("## JSON Schema")]


def test_schema_no_longer_hardcodes_a_single_independence_value() -> None:
    """示例给死一个值，模型就只会照抄——146/146 全是 `independent` 的直接原因。"""
    schema = _schema_section(_prompt())

    assert '"required_independence": "independent"' not in schema


def test_schema_no_longer_hardcodes_a_single_transfer_value() -> None:
    """同上：142/146 全是 `variation`。"""
    schema = _schema_section(_prompt())

    assert '"required_transfer": "variation"' not in schema


def test_constraints_enumerate_the_independence_vocabulary() -> None:
    """要模型做选择，就得先告诉它可选项是什么。"""
    constraints = _constraints(_prompt())

    missing = [name for name in INDEPENDENCE_VALUES if name not in constraints]
    assert missing == [], f"约束里没有给出这些取值：{missing}"


def test_constraints_enumerate_the_transfer_vocabulary() -> None:
    constraints = _constraints(_prompt())

    missing = [name for name in TRANSFER_VALUES if name not in constraints]
    assert missing == [], f"约束里没有给出这些取值：{missing}"


def test_constraints_forbid_filling_every_criterion_with_the_same_value() -> None:
    """光给取值范围不够：必须明说要按知识点差异选，否则模型仍会一律填同一个。"""
    constraints = _constraints(_prompt())

    assert "不要所有标准都填同一个值" in constraints


def test_constraints_demand_a_decidable_performance_and_method() -> None:
    """C2 的验收标准原文：能指出"用什么题、什么作答表现算达标"。

    约束文本是换行排版的，断言前先把空白压掉，否则一次无害的重新折行就会让
    用例转红 —— 那种红是噪音，不是缺陷。
    """
    constraints = re.sub(r"\s+", "", _constraints(_prompt()))

    assert "用什么任务" in constraints
    assert "用什么题" in constraints
    assert "能数的就写数量" in constraints


def test_constraints_name_the_undecidable_phrasings_to_avoid() -> None:
    """给出反例比给出要求更能约束模型 —— "理解××" 是实测中的典型失效写法。"""
    constraints = _constraints(_prompt())

    assert "理解××" in constraints
    assert "无法判定" in constraints


# --- 第二条生成路径 --------------------------------------------------------
#
# 掌握标准不只由教案批次产出。`course_service.generate_sub_nodes` 的小节生成
# prompt 里有同一份 schema 示例，同样把两个枚举写死成 `independent`/`variation`。
# 只修批次 prompt 会留下一条仍然照抄单一定值的路径，而实测的 146/146 分布无法
# 区分是哪条路径写的 —— 两条都得锁。


def _sub_node_prompt_source() -> str:
    """读 `generate_sub_nodes` 的 prompt 源文本。

    这个 prompt 由一个大 async 方法内联构造，依赖真实课程上下文与难度契约；
    为断言两行 schema 而搭起整套依赖不值得，也会让用例变脆。所以这里退一步：
    直接读源码里的 prompt 字面量。判据仍然成立 —— 写死的定值就在字面量里。
    """
    import inspect

    from course_generation.service import CourseService

    return inspect.getsource(CourseService.generate_sub_nodes)


def test_sub_node_prompt_also_stops_hardcoding_the_enum_values() -> None:
    """另一条生成路径不能继续给死单一定值。"""
    source = _sub_node_prompt_source()

    assert '"required_independence": "independent"' not in source
    assert '"required_transfer": "variation"' not in source


def test_sub_node_prompt_enumerates_both_vocabularies() -> None:
    """同样要把可选项交给模型，否则它只能猜。"""
    source = _sub_node_prompt_source()

    missing = [
        name
        for name in (*INDEPENDENCE_VALUES, *TRANSFER_VALUES)
        if name not in source
    ]
    assert missing == [], f"小节生成 prompt 里没有给出这些取值：{missing}"


def test_sub_node_prompt_forbids_one_value_for_every_criterion() -> None:
    source = re.sub(r"\s+", "", _sub_node_prompt_source())

    assert "不要所有标准都填同一个值" in source
