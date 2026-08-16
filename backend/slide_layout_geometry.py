"""Shared deterministic text geometry for planning and slide rendering."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

HORIZONTAL_PROCESS_CARDS_V1 = "horizontal-process-cards-v1"
CLASSIFICATION_THREE_CARDS_V1 = "classification-three-cards-v1"
BALANCED_TWO_COLUMN_BODY_V1 = "balanced-two-column-body-v1"
FORMULA_SOURCE_PANEL_V1 = "formula-source-panel-v1"
FIGURE_SOURCE_PANEL_V1 = "figure-source-panel-v1"
DIAGRAM_SOURCE_PANEL_V1 = "diagram-source-panel-v1"
_PROCESS_TOTAL_WIDTH_IN = 11.7
_PROCESS_GAP_IN = 0.24
_PROCESS_CARD_HORIZONTAL_PADDING_IN = 0.46
_PROCESS_TEXT_HEIGHT_IN = 1.95
_PROCESS_FONT_SIZE_PT = 16.0
_PROCESS_LINE_HEIGHT = 1.22
_PROCESS_MAX_ITEMS = 5

_CLASSIFICATION_CARD_TEXT_WIDTH_PT = (3.38 - 0.02) * 72
_CLASSIFICATION_CARD_TEXT_HEIGHT_PT = (2.35 - 0.02) * 72
_CLASSIFICATION_CARD_LINE_HEIGHT = 1.22
_CLASSIFICATION_MAX_ITEMS = 3

_EDITORIAL_BODY_WIDTH_PT = 10.75 * 72
_EDITORIAL_BODY_HEIGHT_PT = 3.55 * 72
_TWO_COLUMN_BODY_WIDTH_PT = 5.32 * 72
_TWO_COLUMN_BODY_HEIGHT_PT = 4.42 * 72
_TWO_COLUMN_BODY_FONT_SIZE_PT = 16.0
_BODY_LINE_HEIGHT = 1.22
# PowerPoint's font metrics and the portable audit font are not pixel-identical.
# Reserve one complete rendered line so a frame that is mathematically just under
# its boundary cannot touch or cross the card edge after Office lays it out.
_BODY_BOTTOM_SAFETY_LINES = 1

_SOURCE_PANEL_GEOMETRY = {
    FORMULA_SOURCE_PANEL_V1: {"width_pt": 3.80 * 72, "height_pt": 3.57 * 72},
    FIGURE_SOURCE_PANEL_V1: {"width_pt": 3.72 * 72, "height_pt": 3.57 * 72},
    DIAGRAM_SOURCE_PANEL_V1: {"width_pt": 4.76 * 72, "height_pt": 3.57 * 72},
}
_SOURCE_PANEL_LINE_HEIGHT = 1.22

_DIAGRAM_PANEL_WIDTH_IN = 5.95
_DIAGRAM_CONTENT_Y_IN = 0.70
_DIAGRAM_CONTENT_HEIGHT_IN = 3.62
_DIAGRAM_LABEL_FONT_SIZE_PT = 16.0
_DIAGRAM_LABEL_LINE_HEIGHT = 1.22


@lru_cache(maxsize=32)
def _audit_font(font_size_px: int) -> Any:
    from PIL import ImageFont

    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("C:/Windows/Fonts/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), font_size_px)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=8192)
def _audit_character_width(font_size_px: int, character: str) -> float:
    font = _audit_font(font_size_px)
    try:
        return float(font.getlength(character))
    except AttributeError:
        return float(font.getbbox(character)[2])


def wrapped_line_count(
    text: str,
    *,
    width_pt: float,
    font_size_pt: float,
    font_loader: Callable[[int], Any] = _audit_font,
) -> int:
    """Measure wrapping with the active font and a portable Unicode floor."""

    if not text:
        return 1
    dpi_scale = 96 / 72
    font_size_px = max(8, round(font_size_pt * dpi_scale))
    font = font_loader(font_size_px)
    maximum_width = max(1.0, width_pt * dpi_scale)
    measured_lines = 0
    for logical_line in str(text).splitlines() or [""]:
        if not logical_line:
            measured_lines += 1
            continue
        current_width = 0.0
        measured_lines += 1
        for character in logical_line:
            if font_loader is _audit_font:
                character_width = _audit_character_width(
                    font_size_px,
                    character,
                )
            else:
                try:
                    character_width = float(font.getlength(character))
                except AttributeError:
                    character_width = float(font.getbbox(character)[2])
            if current_width and current_width + character_width > maximum_width:
                measured_lines += 1
                current_width = 0.0
            current_width += character_width

    portable_lines = 0
    maximum_width_em = max(1.0, width_pt / max(1.0, font_size_pt))
    for logical_line in str(text).splitlines() or [""]:
        if not logical_line:
            portable_lines += 1
            continue
        current_width_em = 0.0
        portable_lines += 1
        for character in logical_line:
            east_asian_width = unicodedata.east_asian_width(character)
            category = unicodedata.category(character)
            if east_asian_width in {"W", "F"}:
                character_width_em = 1.0
            elif character.isspace():
                character_width_em = 0.34
            elif category.startswith("P"):
                character_width_em = 0.52
            elif character.isupper():
                character_width_em = 0.66
            elif character.islower():
                character_width_em = 0.56
            elif character.isdigit():
                character_width_em = 0.58
            else:
                character_width_em = 0.62
            if (
                current_width_em
                and current_width_em + character_width_em > maximum_width_em
            ):
                portable_lines += 1
                current_width_em = 0.0
            current_width_em += character_width_em
    return max(measured_lines, portable_lines)


def horizontal_process_card_metrics(items: list[str]) -> dict[str, Any]:
    """Return the exact horizontal-card capacity used by the PPTX renderer."""

    item_count = len(items)
    if not 1 <= item_count <= _PROCESS_MAX_ITEMS:
        return {
            "fits": False,
            "item_count": item_count,
            "maximum_item_lines": 0,
            "available_height_pt": _PROCESS_TEXT_HEIGHT_IN * 72,
        }
    card_width_in = (
        _PROCESS_TOTAL_WIDTH_IN
        - max(0, item_count - 1) * _PROCESS_GAP_IN
    ) / item_count
    text_width_pt = max(
        1.0,
        (card_width_in - _PROCESS_CARD_HORIZONTAL_PADDING_IN) * 72,
    )
    available_height_pt = _PROCESS_TEXT_HEIGHT_IN * 72
    wrapped_lines = [
        wrapped_line_count(
            item,
            width_pt=text_width_pt,
            font_size_pt=_PROCESS_FONT_SIZE_PT,
        )
        for item in items
    ]
    required_heights = [
        line_count * _PROCESS_FONT_SIZE_PT * _PROCESS_LINE_HEIGHT
        for line_count in wrapped_lines
    ]
    return {
        "fits": all(
            required <= max(
                available_height_pt * 1.02,
                available_height_pt + 2.0,
            )
            for required in required_heights
        ),
        "item_count": item_count,
        "maximum_item_lines": max(wrapped_lines, default=0),
        "available_height_pt": available_height_pt,
        "text_width_pt": text_width_pt,
        "required_heights_pt": required_heights,
    }


def classification_three_card_metrics(items: list[str]) -> dict[str, Any]:
    """Measure each peer item against the renderer's fixed three-card frame."""

    item_count = len(items)
    if not 1 <= item_count <= _CLASSIFICATION_MAX_ITEMS:
        return {
            "fits": False,
            "item_count": item_count,
            "wrapped_lines": [],
            "required_heights_pt": [],
            "available_height_pt": _CLASSIFICATION_CARD_TEXT_HEIGHT_PT,
            "text_width_pt": _CLASSIFICATION_CARD_TEXT_WIDTH_PT,
        }
    font_sizes_pt = [18.0 if len(item) <= 48 else 16.0 for item in items]
    wrapped_lines = [
        wrapped_line_count(
            item,
            width_pt=_CLASSIFICATION_CARD_TEXT_WIDTH_PT,
            font_size_pt=font_size_pt,
        )
        for item, font_size_pt in zip(items, font_sizes_pt)
    ]
    required_heights_pt = [
        line_count * font_size_pt * _CLASSIFICATION_CARD_LINE_HEIGHT
        for line_count, font_size_pt in zip(wrapped_lines, font_sizes_pt)
    ]
    return {
        "fits": all(
            required <= max(
                _CLASSIFICATION_CARD_TEXT_HEIGHT_PT * 1.02,
                _CLASSIFICATION_CARD_TEXT_HEIGHT_PT + 2.0,
            )
            for required in required_heights_pt
        ),
        "item_count": item_count,
        "wrapped_lines": wrapped_lines,
        "font_sizes_pt": font_sizes_pt,
        "required_heights_pt": required_heights_pt,
        "available_height_pt": _CLASSIFICATION_CARD_TEXT_HEIGHT_PT,
        "text_width_pt": _CLASSIFICATION_CARD_TEXT_WIDTH_PT,
    }


def capacity_profile_items_fit(profile: str, items: list[str]) -> bool:
    if not profile:
        return True
    if profile == HORIZONTAL_PROCESS_CARDS_V1:
        return bool(horizontal_process_card_metrics(items)["fits"])
    if profile == CLASSIFICATION_THREE_CARDS_V1:
        return bool(classification_three_card_metrics(items)["fits"])
    raise ValueError(f"unknown_template_capacity_profile:{profile}")


def balanced_two_column_body_metrics(text: str) -> dict[str, Any]:
    """Measure and split the editable body using the renderer's exact geometry."""

    source = str(text or "").strip()
    if not source:
        return {
            "fits": False,
            "mode": "empty",
            "segments": [],
            "wrapped_lines": [],
            "required_heights_pt": [],
            "available_height_pt": _TWO_COLUMN_BODY_HEIGHT_PT,
            "maximum_safe_lines": 0,
        }

    single_font_size_pt = (
        26.0 if len(source) <= 90 else 22.0 if len(source) <= 180 else 16.0
    )
    single_lines = wrapped_line_count(
        source,
        width_pt=_EDITORIAL_BODY_WIDTH_PT,
        font_size_pt=single_font_size_pt,
    )
    single_maximum_safe_lines = max(
        1,
        int(
            _EDITORIAL_BODY_HEIGHT_PT
            // (single_font_size_pt * _BODY_LINE_HEIGHT)
        )
        - _BODY_BOTTOM_SAFETY_LINES,
    )
    if single_lines <= single_maximum_safe_lines:
        return {
            "fits": True,
            "mode": "single-column",
            "segments": [source],
            "wrapped_lines": [single_lines],
            "font_size_pt": single_font_size_pt,
            "required_heights_pt": [
                single_lines * single_font_size_pt * _BODY_LINE_HEIGHT
            ],
            "available_height_pt": _EDITORIAL_BODY_HEIGHT_PT,
            "text_width_pt": _EDITORIAL_BODY_WIDTH_PT,
            "maximum_safe_lines": single_maximum_safe_lines,
        }

    candidates = {
        match.end()
        for match in re.finditer(
            r"\n\s*\n|[。！？；]|[.!?;](?:\s+|$)|\s+",
            source,
        )
        if len(source) // 5 <= match.end() <= len(source) * 4 // 5
    }
    if not candidates:
        candidates = {len(source) // 2}

    def split_cost(position: int) -> tuple[int, int, int]:
        left = source[:position].strip()
        right = source[position:].strip()
        left_lines = wrapped_line_count(
            left,
            width_pt=_TWO_COLUMN_BODY_WIDTH_PT,
            font_size_pt=_TWO_COLUMN_BODY_FONT_SIZE_PT,
        )
        right_lines = wrapped_line_count(
            right,
            width_pt=_TWO_COLUMN_BODY_WIDTH_PT,
            font_size_pt=_TWO_COLUMN_BODY_FONT_SIZE_PT,
        )
        return (
            max(left_lines, right_lines),
            abs(left_lines - right_lines),
            abs(position - len(source) // 2),
        )

    split_at = min(candidates, key=split_cost)
    segments = [source[:split_at].strip(), source[split_at:].strip()]
    wrapped_lines = [
        wrapped_line_count(
            segment,
            width_pt=_TWO_COLUMN_BODY_WIDTH_PT,
            font_size_pt=_TWO_COLUMN_BODY_FONT_SIZE_PT,
        )
        for segment in segments
    ]
    maximum_safe_lines = max(
        1,
        int(
            _TWO_COLUMN_BODY_HEIGHT_PT
            // (_TWO_COLUMN_BODY_FONT_SIZE_PT * _BODY_LINE_HEIGHT)
        )
        - _BODY_BOTTOM_SAFETY_LINES,
    )
    required_heights_pt = [
        line_count * _TWO_COLUMN_BODY_FONT_SIZE_PT * _BODY_LINE_HEIGHT
        for line_count in wrapped_lines
    ]
    return {
        "fits": all(
            segment and line_count <= maximum_safe_lines
            for segment, line_count in zip(segments, wrapped_lines)
        ),
        "mode": "two-column",
        "segments": segments,
        "wrapped_lines": wrapped_lines,
        "font_size_pt": _TWO_COLUMN_BODY_FONT_SIZE_PT,
        "required_heights_pt": required_heights_pt,
        "available_height_pt": _TWO_COLUMN_BODY_HEIGHT_PT,
        "text_width_pt": _TWO_COLUMN_BODY_WIDTH_PT,
        "maximum_safe_lines": maximum_safe_lines,
    }


def source_panel_text_metrics(profile: str, text: str) -> dict[str, Any]:
    """Return the exact body geometry used by one visual source panel."""

    geometry = _SOURCE_PANEL_GEOMETRY.get(profile)
    if geometry is None:
        raise ValueError(f"unknown_template_capacity_profile:{profile}")
    font_size_pt = 18.0 if len(str(text or "")) <= 170 else 16.0
    wrapped_lines = wrapped_line_count(
        text,
        width_pt=geometry["width_pt"],
        font_size_pt=font_size_pt,
    )
    required_height_pt = wrapped_lines * font_size_pt * _SOURCE_PANEL_LINE_HEIGHT
    available_height_pt = geometry["height_pt"]
    return {
        "fits": required_height_pt <= max(
            available_height_pt * 1.02,
            available_height_pt + 2.0,
        ),
        "wrapped_lines": wrapped_lines,
        "font_size_pt": font_size_pt,
        "required_height_pt": required_height_pt,
        "available_height_pt": available_height_pt,
        "text_width_pt": geometry["width_pt"],
    }


def capacity_profile_text_fits(profile: str, text: str) -> bool:
    if not profile:
        return True
    if profile == BALANCED_TWO_COLUMN_BODY_V1:
        return bool(balanced_two_column_body_metrics(text)["fits"])
    return bool(source_panel_text_metrics(profile, text)["fits"])


def diagram_node_layout_metrics(
    labels: list[str],
    *,
    direction: str,
) -> dict[str, Any]:
    """Measure complete diagram labels against the renderer's node geometry."""

    node_count = len(labels)
    if not 2 <= node_count <= 6:
        return {"fits": False, "node_boxes": [], "node_count": node_count}
    boxes: list[dict[str, float]] = []
    vertical = str(direction or "").strip().lower() == "vertical"
    if vertical:
        gap = 0.04
        usable_height = _DIAGRAM_CONTENT_HEIGHT_IN - gap * (node_count - 1)
        required_heights = []
        for label in labels:
            wrapped_lines = wrapped_line_count(
                label,
                width_pt=(4.85 - 0.30) * 72,
                font_size_pt=_DIAGRAM_LABEL_FONT_SIZE_PT,
            )
            required_heights.append(max(
                0.58,
                wrapped_lines
                * _DIAGRAM_LABEL_FONT_SIZE_PT
                * _DIAGRAM_LABEL_LINE_HEIGHT
                / 72
                + 0.16,
            ))
        if sum(required_heights) <= usable_height:
            extra = (usable_height - sum(required_heights)) / node_count
            cursor = _DIAGRAM_CONTENT_Y_IN
            for height in (value + extra for value in required_heights):
                boxes.append({
                    "x": 0.55,
                    "y": cursor,
                    "width": 4.85,
                    "height": height,
                })
                cursor += height + gap
        else:
            # A complete technical identifier must never be shortened to keep
            # the requested direction. Fall back deterministically to the same
            # measured two-column geometry used by horizontal diagrams.
            vertical = False
    if not vertical:
        if node_count <= 3:
            gap = 0.18
            width = (
                _DIAGRAM_PANEL_WIDTH_IN - 1.10 - gap * (node_count - 1)
            ) / node_count
            boxes = [
                {
                    "x": 0.55 + index * (width + gap),
                    "y": 1.33,
                    "width": width,
                    "height": 1.28,
                }
                for index in range(node_count)
            ]
        else:
            columns = 2
            rows = (node_count + columns - 1) // columns
            column_gap = 0.22
            row_gap = 0.14
            width = (_DIAGRAM_PANEL_WIDTH_IN - 1.28) / columns
            height = (
                _DIAGRAM_CONTENT_HEIGHT_IN - row_gap * (rows - 1)
            ) / rows
            boxes = [
                {
                    "x": 0.46 + (index % columns) * (width + column_gap),
                    "y": _DIAGRAM_CONTENT_Y_IN
                    + (index // columns) * (height + row_gap),
                    "width": width,
                    "height": height,
                }
                for index in range(node_count)
            ]
    label_fits = [
        wrapped_line_count(
            label,
            width_pt=max(1.0, (box["width"] - 0.30) * 72),
            font_size_pt=_DIAGRAM_LABEL_FONT_SIZE_PT,
        )
        * _DIAGRAM_LABEL_FONT_SIZE_PT
        * _DIAGRAM_LABEL_LINE_HEIGHT
        <= max(
            (box["height"] - 0.16) * 72 * 1.02,
            (box["height"] - 0.16) * 72 + 2.0,
        )
        for label, box in zip(labels, boxes)
    ]
    return {
        "fits": all(label_fits),
        "node_boxes": boxes,
        "node_count": node_count,
        "label_fits": label_fits,
    }


__all__ = [
    "BALANCED_TWO_COLUMN_BODY_V1",
    "CLASSIFICATION_THREE_CARDS_V1",
    "DIAGRAM_SOURCE_PANEL_V1",
    "FIGURE_SOURCE_PANEL_V1",
    "FORMULA_SOURCE_PANEL_V1",
    "HORIZONTAL_PROCESS_CARDS_V1",
    "balanced_two_column_body_metrics",
    "classification_three_card_metrics",
    "capacity_profile_items_fit",
    "capacity_profile_text_fits",
    "diagram_node_layout_metrics",
    "horizontal_process_card_metrics",
    "source_panel_text_metrics",
    "wrapped_line_count",
]
