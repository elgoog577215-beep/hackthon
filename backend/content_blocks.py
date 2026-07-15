"""Helpers for structured lesson content blocks."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
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


def content_fingerprint(content: str) -> str:
    """Return a stable fingerprint after normalizing insignificant whitespace."""
    normalized = re.sub(r"[ \t]+", " ", str(content or "").replace("\r\n", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"cbf_{digest}"


def block_revision_id(block: dict[str, Any]) -> str:
    """Build an immutable revision ID while preserving the logical block ID."""
    payload = {
        "block_id": str(block.get("block_id") or ""),
        "parent_block_id": block.get("parent_block_id"),
        "type": str(block.get("type") or ""),
        "title": str(block.get("title") or "").strip(),
        "content_fingerprint": content_fingerprint(str(block.get("content") or "")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"cbr_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def with_block_revision_metadata(block: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(block)
    enriched["content_fingerprint"] = content_fingerprint(str(enriched.get("content") or ""))
    enriched["block_revision_id"] = block_revision_id(enriched)
    return enriched


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
            "metadata": deepcopy(raw.get("metadata") or {}),
        }
        enriched = with_block_revision_metadata(block)
        supplied_fingerprint = str(raw.get("content_fingerprint") or "")
        supplied_revision = str(raw.get("block_revision_id") or "")
        if supplied_revision and supplied_fingerprint == enriched["content_fingerprint"]:
            enriched["block_revision_id"] = supplied_revision
        normalized.append(enriched)

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
        blocks.append(with_block_revision_metadata({
            "block_id": make_block_id(node_id, idx, block_type),
            "parent_block_id": None,
            "type": block_type,
            "title": title or TYPE_TITLES.get(block_type, "正文"),
            "content": content,
            "summary": summarize_text(content),
            "order": idx,
            "status": "final",
        }))
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


def project_course_content_blocks(course_data: dict[str, Any]) -> dict[str, Any]:
    """Return a response-safe course copy with revision metadata for old and new courses."""
    projected = deepcopy(course_data)
    for node in _walk_nodes(projected.get("nodes") or []):
        node["content_blocks"] = normalize_blocks(
            str(node.get("node_id") or ""),
            node.get("content_blocks"),
            str(node.get("node_content") or ""),
        )
    return projected


def resolve_content_anchor(
    course_data: dict[str, Any],
    *,
    node_id: str | None,
    anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve a historical semantic anchor against the current course content."""
    projected = project_course_content_blocks(course_data)
    nodes = list(_walk_nodes(projected.get("nodes") or []))
    by_node = {str(node.get("node_id") or ""): node for node in nodes}
    current_version_id = projected.get("current_course_version_id")
    original = dict(anchor or {})
    progress = _clamp_progress(original.get("progress"))
    requested_node = by_node.get(str(node_id or ""))

    blocks: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for node in nodes:
        for block in node.get("content_blocks") or []:
            blocks.append((node, block))

    block_id = str(original.get("block_id") or "")
    revision_id = str(original.get("block_revision_id") or "")
    fingerprint = str(original.get("content_fingerprint") or "")

    if block_id and revision_id:
        exact = next((item for item in blocks if item[1].get("block_id") == block_id and item[1].get("block_revision_id") == revision_id), None)
        if exact:
            return _resolution("exact", exact[0], exact[1], progress, current_version_id, False)

    if block_id:
        same_block = next((item for item in blocks if item[1].get("block_id") == block_id), None)
        if same_block:
            return _resolution("updated_block", same_block[0], same_block[1], progress, current_version_id, True)

    if fingerprint:
        same_node_matches = [item for item in blocks if item[0] is requested_node and item[1].get("content_fingerprint") == fingerprint]
        all_matches = [item for item in blocks if item[1].get("content_fingerprint") == fingerprint]
        matches = same_node_matches or all_matches
        if len(matches) == 1:
            return _resolution("fingerprint_remap", matches[0][0], matches[0][1], progress, current_version_id, True)

    if requested_node:
        first_block = next(iter(requested_node.get("content_blocks") or []), None)
        return _resolution("node_fallback", requested_node, first_block, 0.0, current_version_id, True)

    fallback_node = next((node for node in nodes if node.get("node_content") or node.get("content_blocks")), nodes[0] if nodes else None)
    if fallback_node:
        first_block = next(iter(fallback_node.get("content_blocks") or []), None)
        return _resolution("course_fallback", fallback_node, first_block, 0.0, current_version_id, True)

    return {
        "status": "unavailable",
        "resolved_anchor": None,
        "content_changed": True,
        "current_course_version_id": current_version_id,
    }


def _resolution(
    status: str,
    node: dict[str, Any],
    block: dict[str, Any] | None,
    progress: float,
    current_version_id: str | None,
    content_changed: bool,
) -> dict[str, Any]:
    resolved = {
        "node_id": str(node.get("node_id") or ""),
        "node_name": str(node.get("node_name") or ""),
        "block_id": str((block or {}).get("block_id") or ""),
        "block_revision_id": str((block or {}).get("block_revision_id") or ""),
        "content_fingerprint": str((block or {}).get("content_fingerprint") or ""),
        "block_type": str((block or {}).get("type") or ""),
        "title": str((block or {}).get("title") or ""),
        "progress": progress,
    }
    return {
        "status": status,
        "resolved_anchor": resolved,
        "content_changed": content_changed,
        "current_course_version_id": current_version_id,
    }


def _walk_nodes(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        children = node.get("children") or []
        if isinstance(children, list):
            yield from _walk_nodes(children)


def _clamp_progress(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0
