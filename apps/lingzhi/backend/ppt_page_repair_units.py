"""Stable, contiguous source units for bounded PPT page repair calls."""
from __future__ import annotations

import hashlib
import re
from typing import Any

PAGE_REPAIR_SPLIT_TRIGGER_CHARS = 4000
PAGE_REPAIR_SPLIT_TRIGGER_LINES = 80
PAGE_REPAIR_UNIT_MAX_CHARS = 2000
PAGE_REPAIR_UNIT_MIN_CHARS = 900
PAGE_REPAIR_RETRY_UNIT_MAX_CHARS = 900
_FENCE_RE = re.compile(r"(?:```|~~~)")


def _source_kind(content: str, start: int, end: int) -> str:
    before = len(_FENCE_RE.findall(content[:start]))
    inside_code = before % 2 == 1
    return "code" if inside_code or _FENCE_RE.search(content[start:end]) else "prose"


def _unit(block_id: str, content: str, start: int, end: int) -> dict[str, Any]:
    excerpt = content[start:end]
    digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    return {
        "repair_unit_id": f"{block_id}:source:{start}-{end}:{digest[:12]}",
        "source_start": start,
        "source_end": end,
        "source_chars": len(excerpt),
        "source_sha256": digest,
        "source_kind": _source_kind(content, start, end),
    }


def full_page_repair_unit(block_id: str, content: str) -> dict[str, Any]:
    return _unit(block_id, content, 0, len(content))


def page_repair_source_units(block_id: str, content: str) -> list[dict[str, Any]]:
    """Split only complex inputs; every returned range is exact and contiguous."""
    text = str(content or "")
    if not text:
        return [full_page_repair_unit(block_id, text)]
    if (
        len(text) <= PAGE_REPAIR_SPLIT_TRIGGER_CHARS
        and len(text.splitlines()) <= PAGE_REPAIR_SPLIT_TRIGGER_LINES
    ):
        return [full_page_repair_unit(block_id, text)]

    line_boundaries = [match.end() for match in re.finditer(r"\n", text)]
    paragraph_boundaries = [match.end() for match in re.finditer(r"\n\s*\n", text)]
    units: list[dict[str, Any]] = []
    start = 0
    while start < len(text):
        limit = min(len(text), start + PAGE_REPAIR_UNIT_MAX_CHARS)
        if limit == len(text):
            end = limit
        else:
            minimum = min(limit, start + PAGE_REPAIR_UNIT_MIN_CHARS)
            preferred = [point for point in paragraph_boundaries if minimum <= point <= limit]
            fallback = [point for point in line_boundaries if minimum <= point <= limit]
            end = (preferred or fallback or [limit])[-1]
        if end <= start:
            raise ValueError("script_ppt_repair_unit_invalid_range")
        units.append(_unit(block_id, text, start, end))
        start = end
    if "".join(text[item["source_start"]:item["source_end"]] for item in units) != text:
        raise ValueError("script_ppt_repair_unit_source_mismatch")
    return units


def subdivide_page_repair_unit(
    block_id: str,
    content: str,
    unit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Split one provider-rejected unit once without changing its source span."""
    start = int(unit["source_start"])
    end = int(unit["source_end"])
    if start < 0 or end <= start or end > len(content):
        raise ValueError("script_ppt_repair_unit_checkpoint_invalid")
    children = []
    cursor = start
    while cursor < end:
        limit = min(end, cursor + PAGE_REPAIR_RETRY_UNIT_MAX_CHARS)
        if limit < end:
            boundaries = [match.end() for match in re.finditer(r"\n", content[cursor:limit])]
            child_end = cursor + (boundaries[-1] if boundaries else limit - cursor)
        else:
            child_end = end
        if child_end <= cursor:
            child_end = limit
        child = _unit(block_id, content, cursor, child_end)
        child["split_depth"] = int(unit.get("split_depth") or 0) + 1
        child["parent_repair_unit_id"] = unit["repair_unit_id"]
        children.append(child)
        cursor = child_end
    if len(children) < 2:
        return [unit]
    if children[0]["source_start"] != start or children[-1]["source_end"] != end:
        raise ValueError("script_ppt_repair_unit_source_mismatch")
    return children


def page_repair_unit_block(block: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    content = str(block.get("content") or "")
    try:
        start = int(unit["source_start"])
        end = int(unit["source_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("script_ppt_repair_unit_checkpoint_invalid") from exc
    if start < 0 or end <= start or end > len(content):
        raise ValueError("script_ppt_repair_unit_checkpoint_invalid")
    excerpt = content[start:end]
    if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != unit.get("source_sha256"):
        raise ValueError("script_ppt_repair_unit_source_changed")
    return {**block, "content": excerpt}
