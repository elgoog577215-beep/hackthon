"""Helpers for structured lesson content blocks."""

from __future__ import annotations

import re
from typing import Any


DEFAULT_BLOCKS: list[tuple[str, str]] = [
    ("intro", "引入问题"),
    ("concept", "核心概念"),
    ("reasoning", "推理过程"),
    ("example", "例子讲解"),
    ("application", "应用场景"),
    ("exercise", "自测练习"),
    ("summary", "小结"),
]

TYPE_TITLES = dict(DEFAULT_BLOCKS)


def block_type_from_title(title: str, order: int = 0) -> str:
    text = title.lower()
    pairs = [
        ("intro", ("引入", "问题", "直观", "why", "背景")),
        ("concept", ("概念", "定义", "核心", "是什么", "基础")),
        ("reasoning", ("推理", "证明", "原理", "过程", "为什么")),
        ("example", ("例子", "案例", "示例", "讲解")),
        ("application", ("应用", "场景", "实践", "怎么用")),
        ("exercise", ("练习", "自测", "题", "检查")),
        ("summary", ("小结", "总结", "回顾")),
    ]
    for block_type, keywords in pairs:
        if any(keyword in text for keyword in keywords):
            return block_type
    if 0 <= order < len(DEFAULT_BLOCKS):
        return DEFAULT_BLOCKS[order][0]
    return "concept"


def block_title(block: dict[str, Any]) -> str:
    return str(block.get("title") or TYPE_TITLES.get(block.get("type"), "正文")).strip()


def summarize_text(text: str, limit: int = 120) -> str:
    plain = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    plain = re.sub(r"[#>*_`$\\-]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit]


def make_block_id(node_id: str, order: int, block_type: str) -> str:
    safe_type = re.sub(r"[^a-z0-9_-]+", "-", block_type.lower()).strip("-") or "block"
    return f"{node_id}-{order + 1}-{safe_type}"


def normalize_blocks(
    node_id: str,
    blocks: Any,
    fallback_markdown: str = "",
) -> list[dict[str, Any]]:
    if not isinstance(blocks, list) or not blocks:
        return blocks_from_markdown(node_id, fallback_markdown)

    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "").strip()
        title = str(raw.get("title") or "").strip()
        block_type = str(raw.get("type") or block_type_from_title(title, idx))
        block = {
            "block_id": str(raw.get("block_id") or make_block_id(node_id, idx, block_type)),
            "parent_block_id": raw.get("parent_block_id"),
            "type": block_type,
            "title": title or TYPE_TITLES.get(block_type, "正文"),
            "content": content,
            "summary": str(raw.get("summary") or summarize_text(content)),
            "order": int(raw.get("order", idx)),
            "status": str(raw.get("status") or "final"),
        }
        normalized.append(block)

    if not normalized:
        return blocks_from_markdown(node_id, fallback_markdown)
    return sorted(normalized, key=lambda b: b.get("order", 0))


def blocks_from_markdown(node_id: str, markdown: str) -> list[dict[str, Any]]:
    text = (markdown or "").strip()
    if not text:
        return []

    heading_re = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    parts: list[tuple[str, str]] = []

    if not matches:
        parts.append(("正文", text))
    else:
        first = matches[0]
        preface = text[: first.start()].strip()
        if preface:
            parts.append(("引入问题", preface))
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            parts.append((match.group(2).strip(), text[start:end].strip()))

    blocks: list[dict[str, Any]] = []
    for idx, (title, content) in enumerate(parts):
        block_type = block_type_from_title(title, idx)
        blocks.append({
            "block_id": make_block_id(node_id, idx, block_type),
            "parent_block_id": None,
            "type": block_type,
            "title": title or TYPE_TITLES.get(block_type, "正文"),
            "content": content,
            "summary": summarize_text(content),
            "order": idx,
            "status": "final",
        })
    return blocks


def strip_leading_heading(content: str, title: str = "") -> str:
    text = (content or "").strip()
    if not text:
        return ""
    pattern = r"^#{1,4}\s+(.+?)\s*\n+"
    match = re.match(pattern, text)
    if not match:
        return text
    heading = match.group(1).strip()
    if not title or heading == title or title in heading or heading in title:
        return text[match.end():].strip()
    return text


def blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for block in sorted(blocks, key=lambda b: b.get("order", 0)):
        title = block_title(block)
        content = strip_leading_heading(str(block.get("content") or ""), title)
        if content:
            chunks.append(f"## {title}\n\n{content}")
        else:
            chunks.append(f"## {title}")
    return "\n\n".join(chunks).strip()


def set_node_content_blocks(node: dict[str, Any], content: str) -> list[dict[str, Any]]:
    blocks = normalize_blocks(
        str(node.get("node_id", "")),
        node.get("content_blocks"),
        content,
    )
    if not blocks and content:
        blocks = blocks_from_markdown(str(node.get("node_id", "")), content)
    node["content_blocks"] = blocks
    node["node_content"] = blocks_to_markdown(blocks) if blocks else content
    return blocks
