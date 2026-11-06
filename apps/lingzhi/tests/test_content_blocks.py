import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from content_blocks import blocks_from_markdown, blocks_to_markdown, normalize_blocks


def test_blocks_from_markdown_uses_teaching_headings():
    markdown = """## 引入问题

为什么要学极限？

## 应用场景

用极限描述瞬时速度。"""

    blocks = blocks_from_markdown("L2-1-1", markdown)

    assert [block["type"] for block in blocks] == ["orientation", "application"]
    assert blocks[0]["block_id"] == "L2-1-1-1-orientation"
    assert blocks[1]["title"] == "应用场景"


def test_blocks_to_markdown_rebuilds_compatible_content():
    blocks = [
        {"block_id": "b1", "type": "intro", "title": "引入问题", "content": "先看问题。", "order": 0},
        {"block_id": "b2", "type": "summary", "title": "小结", "content": "记住核心结论。", "order": 1},
    ]

    markdown = blocks_to_markdown(blocks)

    assert "## 引入问题" in markdown
    assert "先看问题。" in markdown
    assert "## 小结" in markdown


def test_blocks_from_markdown_drops_duplicate_section_heading_and_uses_semantic_roles():
    markdown = """## 1.1 渐进记号与复杂度分析

## 本节任务

给出一段代码的时间复杂度。

## 学习者行动

请独立分析两层循环。

## 检查与反馈

对照答案检查推导过程。"""

    blocks = blocks_from_markdown(
        "L2-1-1",
        markdown,
        node_title="1.1 渐进记号与复杂度分析",
    )

    assert [block["title"] for block in blocks] == ["本节任务", "学习者行动", "检查与反馈"]
    assert [block["type"] for block in blocks] == ["objective", "activity", "feedback"]


def test_deeper_headings_stay_inside_their_parent_teaching_block():
    markdown = """## 核心教学

先建立核心概念。

### 正式定义

这里是定义。

## 解释性例子

这里是例子。"""

    blocks = blocks_from_markdown("L2-1-1", markdown)

    assert [block["type"] for block in blocks] == ["concept", "example"]
    assert "### 正式定义" in blocks[0]["content"]


def test_unknown_heading_does_not_inherit_meaning_from_its_position():
    blocks = blocks_from_markdown("L2-1-1", "## 五个观察\n\n这里记录观察结果。")

    assert blocks[0]["type"] == "custom"


def test_knowledge_markers_index_explicit_types_and_display_formulas_without_gating():
    blocks = blocks_from_markdown("L2-1-1", """## 定理：秩—零度定理

若线性映射满足条件，则：

$$\\dim V = \\dim \\ker(T) + \\dim \\operatorname{im}(T)$$

内联变量 $x$ 不单独进入速览。""")

    markers = blocks[0]["metadata"]["knowledge_markers"]
    assert [marker["kind"] for marker in markers] == ["theorem", "formula"]
    assert markers[1]["source"] == "display_math"
    assert "operatorname{im}" in markers[1]["expression"]
    assert blocks[0]["content"].startswith("若线性映射")


def test_knowledge_markers_recompute_from_saved_blocks_and_absence_stays_valid():
    marked = normalize_blocks("n", [{"block_id": "b", "title": "定义：极限", "content": "称……"}])[0]
    plain = normalize_blocks("n", [{"block_id": "b2", "title": "引入问题", "content": "为什么？"}])[0]

    assert marked["metadata"]["knowledge_markers"][0]["kind"] == "definition"
    assert "knowledge_markers" not in plain["metadata"]
