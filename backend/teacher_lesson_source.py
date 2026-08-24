"""教师原教案到单讲生成证据的单向适配器。

这里只保存原文件的顺序、分块、定位和与讲内小节的映射，不生成第二份教案。
正式教案仍由 ``TeacherLessonAuthoringRepository`` 的修订负责。
"""

from __future__ import annotations

import re
from typing import Any

from material_models import DocumentBlock, ParsedDocument


LESSON_PLAN_SOURCE_SCHEMA_VERSION = "teacher_lesson_plan_source_v1"
LESSON_PLAN_FIDELITY_CONTRACT = "preserve_structure_fill_missing_only"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", _text(value)).lower()


def _title_matches(block: DocumentBlock, section_title: str) -> bool:
    if block.kind not in {"title", "heading"}:
        return False
    left = _normalized(block.text)
    right = _normalized(section_title)
    if not left or not right:
        return False
    if len(left) >= 4 and left in right:
        return True
    if len(right) >= 4 and right in left:
        return True
    tokens = [
        _normalized(item)
        for item in re.split(r"[、，,:：；;（）()\s]+", section_title)
        if len(_normalized(item)) >= 2
    ]
    return bool(tokens) and sum(token in left for token in tokens) >= min(2, len(tokens))


def _block_payload(block: DocumentBlock) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "kind": block.kind,
        "text": block.text,
        "order": block.order,
        "parent_block_id": block.parent_block_id,
        "locator": block.locator.model_dump(mode="json"),
        "metadata": block.metadata,
    }


def _partition_blocks(
    blocks: list[DocumentBlock],
    sections: list[dict[str, Any]],
) -> list[list[DocumentBlock]]:
    if not sections:
        return [blocks]
    groups: list[list[DocumentBlock]] = [[] for _ in sections]
    heading_targets: dict[int, int] = {}
    for block_index, block in enumerate(blocks):
        for section_index, section in enumerate(sections):
            if _title_matches(block, _text(section.get("node_name") or section.get("title"))):
                heading_targets[block_index] = section_index
                break
    if heading_targets:
        current = min(heading_targets.values(), default=0)
        for block_index, block in enumerate(blocks):
            current = heading_targets.get(block_index, current)
            groups[current].append(block)
        return groups
    # 标题无法可靠匹配时，保持原顺序并做连续切分；绝不轮询打散原教案。
    for index, block in enumerate(blocks):
        target = min(len(sections) - 1, index * len(sections) // max(1, len(blocks)))
        groups[target].append(block)
    return groups


def compile_original_lesson_plan_evidence(
    document: ParsedDocument,
    *,
    asset_id: str,
    filename: str,
    sections: list[dict[str, Any]],
    max_chars_per_section: int = 12000,
) -> list[dict[str, Any]]:
    """Preserve one original lesson plan as ordered, locatable section evidence."""
    blocks = sorted(document.blocks, key=lambda item: (item.order, item.block_id))
    if not blocks:
        return []
    normalized_sections = [item for item in sections if isinstance(item, dict)]
    groups = _partition_blocks(blocks, normalized_sections)
    evidence: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        if not group:
            continue
        section = normalized_sections[index] if index < len(normalized_sections) else {}
        section_id = _text(section.get("node_id"))
        section_title = _text(section.get("node_name") or section.get("title"))
        source_text = "\n\n".join(
            f"[{block.kind} | 原顺序 {block.order}] {block.text.strip()}"
            for block in group
            if block.text.strip()
        )[:max_chars_per_section]
        locator = group[0].locator.model_dump(mode="json")
        evidence.append({
            "schema_version": LESSON_PLAN_SOURCE_SCHEMA_VERSION,
            "evidence_id": f"lesson-plan-source:{asset_id}:{section_id or index + 1}",
            "asset_id": asset_id,
            "document_id": document.document_id,
            "source_kind": "uploaded_lesson_plan",
            "kind": "original_lesson_plan",
            "section_node_id": section_id,
            "section_title": section_title,
            "filename": filename,
            "summary": source_text,
            "source_text": source_text,
            "source_blocks": [_block_payload(block) for block in group],
            "block_ids": [block.block_id for block in group],
            "source_order_start": group[0].order,
            "source_order_end": group[-1].order,
            "locator": locator,
            "fidelity_contract": LESSON_PLAN_FIDELITY_CONTRACT,
            "parse_status": document.parse_status,
            "parse_warnings": list(document.warnings),
        })
    return evidence
