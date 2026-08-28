"""Stable course-node locations for task progress projections."""

from __future__ import annotations

from typing import Any

def build_node_locations(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """把有序节点表压成 {node_id: 位置}，供进度显示用。

    教师问的是"现在生成到哪了"，答案应该是"第 2 章第 3 节 · 不确定性原理"，
    而不是一个 node_id 或一个孤零零的小节名——课程里重名的小节并不少见，
    只报小节名说不清进度走到了整门课的什么位置。

    章节序号按节点表顺序推导：level 1 递增章号并把节号归零，level 2 在当前章
    下递增节号。位置只依赖顺序与层级，不依赖 node_id 的命名约定。

    正文可能在没有章的课程里生成（早期课程或导入课程只有平铺小节），
    这时 ``chapter_number`` 为 None，标签退化成"第 Y 节 · 名字"，
    调用方不需要为这种课程写分支。
    """
    locations: dict[str, dict[str, Any]] = {}
    chapter_number = 0
    section_number = 0
    chapter_name = ""
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        if not node_id:
            continue
        level = int(node.get("node_level") or 1)
        name = str(node.get("node_name") or "")
        if level <= 1:
            chapter_number += 1
            section_number = 0
            chapter_name = name
            locations[node_id] = {
                "chapter_number": chapter_number,
                "chapter_name": name,
                "section_number": None,
                "node_name": name,
                "label": f"第{chapter_number}章 · {name}" if name else f"第{chapter_number}章",
            }
            continue
        section_number += 1
        if chapter_number:
            prefix = f"第{chapter_number}章第{section_number}节"
        else:
            prefix = f"第{section_number}节"
        locations[node_id] = {
            "chapter_number": chapter_number or None,
            "chapter_name": chapter_name,
            "section_number": section_number,
            "node_name": name,
            "label": f"{prefix} · {name}" if name else prefix,
        }
    return locations

__all__ = ["build_node_locations"]
