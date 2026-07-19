"""Helpers for structured lesson content blocks."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from course_pedagogy import module_role_from_heading


DEFAULT_BLOCKS: list[tuple[str, str]] = [
    ("intro", "引入问题"),
    ("objective", "本节任务"),
    ("concept", "核心概念"),
    ("reasoning", "推理过程"),
    ("example", "例子讲解"),
    ("application", "应用场景"),
    ("activity", "学习者行动"),
    ("exercise", "自测练习"),
    ("feedback", "检查与反馈"),
    ("summary", "小结"),
]

TYPE_TITLES = dict(DEFAULT_BLOCKS)
TYPE_TITLES.update({
    "orientation": "引入",
    "prerequisite": "前置",
    "counterexample": "辨析",
    "misconception": "易错点",
    "checkpoint": "检查",
    "remediation": "补救",
    "transfer": "迁移",
    "custom": "内容",
})


def block_type_from_title(title: str, order: int = 0, content: str = "") -> str:
    """Resolve a pedagogical role without using block order as hidden meaning.

    ``order`` remains in the signature for compatibility, but deliberately does
    not participate in classification. An unknown heading is honest ``custom``
    content instead of becoming a false introduction, concept, or example.
    """
    del order
    registered = module_role_from_heading(title)
    if registered:
        return registered

    text = _normalize_heading(title)
    explicit_patterns = [
        ("objective", r"^(本节任务|学习目标|学习任务|目标与任务|要解决的问题)$"),
        ("orientation", r"^(引入|引入问题|直觉|直观理解|背景|问题导入|现象与问题)(?:[:：].*)?$"),
        ("prerequisite", r"^(前置|前置知识|前置诊断|准备知识)(?:[:：].*)?$"),
        ("counterexample", r"^(反例|对比|辨析|案例比较|观点比较|材料辨析)(?:[:：].*)?$"),
        ("misconception", r"^(错误分析|常见错误|常见误区|易错点|陷阱)(?:[:：].*)?$"),
        ("remediation", r"^(补救|局部补救|纠错|间隔复习)(?:[:：].*)?$"),
        ("feedback", r"^(检查与反馈|答案与评价标准|评价标准|运行结果|测试与质量)(?:[:：].*)?$"),
        ("activity", r"^(学习者行动|实战任务|修改任务|变式练习|控制练习|真实输出|讨论或写作|角色模拟|实验设计)(?:[:：].*)?$"),
        ("checkpoint", r"^(检查|理解检查|自测|自测练习|随堂练习)(?:[:：].*)?$"),
        ("summary", r"^(小结|总结|本节回顾|回顾)(?:[:：].*)?$"),
        ("example", r"^(例子|案例|示例|例题|例题推演|解释性例子|调试案例|机制案例|案例拆解|最小可运行示例)(?:[:：].*)?$"),
        ("application", r"^(应用|应用场景|实践|预测与应用|工具与模板|数学建模)(?:[:：].*)?$"),
        ("reasoning", r"^(推理|推导|证明|原理|机制|机制拆解|机制过程|观点与论证|数据分析)(?:[:：].*)?$"),
        ("concept", r"^(概念|核心概念|核心教学|概念地图|定义|正式定义|模型与规律|架构设计|方法框架)(?:[:：].*)?$"),
        ("transfer", r"^(迁移|综合迁移|跨情境迁移)(?:[:：].*)?$"),
    ]
    for block_type, pattern in explicit_patterns:
        if re.match(pattern, text, flags=re.IGNORECASE):
            return block_type
    if re.search(r"(?:定义|基本概念|抽象数据类型|渐进记号|结构与性质|核心结构)$", text):
        return "concept"

    evidence = summarize_text(content, 360).lower()
    if re.search(r"(?:要解决的问题|可验证的学习目标|学完本节后).{0,100}(?:能够|应当)", evidence):
        return "objective"
    if re.search(r"(?:答案与评价标准|正确标准|评分标准|典型错误|参考答案)", evidence):
        return "feedback"
    if re.search(r"^(?:任务|请独立|请完成|尝试|动手|练习)[：:]", evidence):
        return "activity"
    if re.search(r"(?:形式定义|定义为|当且仅当|称为|核心关系)", evidence):
        return "concept"
    return "custom"


def heading_matches_section(title: str, section_title: str) -> bool:
    return bool(section_title) and _normalize_heading(title) == _normalize_heading(section_title)


def _normalize_heading(value: str) -> str:
    text = re.sub(r"^[#\s]+", "", str(value or ""))
    text = re.sub(r"[\s　]+", " ", text).strip()
    return text.strip("：:、。 ")


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
    node_title: str = "",
) -> list[dict[str, Any]]:
    if not isinstance(blocks, list) or not blocks:
        return blocks_from_markdown(node_id, fallback_markdown, node_title=node_title)

    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "").strip()
        title = str(raw.get("title") or "").strip()
        block_type = str(raw.get("type") or block_type_from_title(title, idx, content))
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
        return blocks_from_markdown(node_id, fallback_markdown, node_title=node_title)
    return sorted(normalized, key=lambda b: b.get("order", 0))


def blocks_from_markdown(node_id: str, markdown: str, *, node_title: str = "") -> list[dict[str, Any]]:
    text = (markdown or "").strip()
    if not text:
        return []

    # Only level-two headings define peer teaching blocks. Deeper headings stay
    # inside the block body instead of acquiring an unrelated role of their own.
    heading_re = re.compile(r"^(##)\s+(.+?)\s*$", re.MULTILINE)
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

    meaningful_parts: list[tuple[str, str]] = []
    for title, content in parts:
        if heading_matches_section(title, node_title):
            if content:
                meaningful_parts.append(("引入问题", content))
            continue
        if content:
            meaningful_parts.append((title, content))

    blocks: list[dict[str, Any]] = []
    for idx, (title, content) in enumerate(meaningful_parts):
        block_type = block_type_from_title(title, idx, content)
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
        str(node.get("node_name") or ""),
    )
    if not blocks and content:
        blocks = blocks_from_markdown(
            str(node.get("node_id", "")),
            content,
            node_title=str(node.get("node_name") or ""),
        )
    _attach_module_plan_metadata(blocks, node.get("module_plan") or [])
    node["content_blocks"] = blocks
    node["node_content"] = blocks_to_markdown(blocks) if blocks else content
    return blocks


def _attach_module_plan_metadata(
    blocks: list[dict[str, Any]],
    module_plan: list[dict[str, Any]],
) -> None:
    """把已确认模块实例追溯信息挂到生成块，供 CourseDocument 落盘。"""
    candidates = [
        item for item in module_plan
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    for block in blocks:
        title = _normalize_heading(str(block.get("title") or ""))
        matched = next(
            (
                item
                for item in candidates
                if title == _normalize_heading(str(item.get("label") or ""))
                or title.startswith(f"{_normalize_heading(str(item.get('label') or ''))}：")
                or title.startswith(f"{_normalize_heading(str(item.get('label') or ''))}:")
            ),
            None,
        )
        if not matched:
            continue
        metadata = deepcopy(block.get("metadata") or {})
        metadata.update({
            "module_id": matched.get("module_id"),
            "module_instance_id": matched.get("module_instance_id"),
            "composition_source": matched.get("composition_source"),
            "composition_style": matched.get("composition_style"),
            "selection_reasons": deepcopy(
                matched.get("selection_reasons") or []
            ),
            "block_difficulty_contract": deepcopy(
                matched.get("block_difficulty_contract") or {}
            ),
            "role": matched.get("block_role") or block.get("type"),
        })
        block["metadata"] = metadata


def project_course_content_blocks(course_data: dict[str, Any]) -> dict[str, Any]:
    """Return a response-safe course copy with revision metadata for old and new courses."""
    projected = deepcopy(course_data)
    for node in _walk_nodes(projected.get("nodes") or []):
        node["content_blocks"] = normalize_blocks(
            str(node.get("node_id") or ""),
            node.get("content_blocks"),
            str(node.get("node_content") or ""),
            str(node.get("node_name") or ""),
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
