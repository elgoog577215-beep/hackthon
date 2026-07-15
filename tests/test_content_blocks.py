import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from content_blocks import blocks_from_markdown, blocks_to_markdown


def test_blocks_from_markdown_uses_teaching_headings():
    markdown = """## 引入问题

为什么要学极限？

## 应用场景

用极限描述瞬时速度。"""

    blocks = blocks_from_markdown("L2-1-1", markdown)

    assert [block["type"] for block in blocks] == ["intro", "application"]
    assert blocks[0]["block_id"] == "L2-1-1-1-intro"
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
