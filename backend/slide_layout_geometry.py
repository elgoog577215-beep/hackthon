"""Shared deterministic text geometry for planning and slide rendering."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

HORIZONTAL_PROCESS_CARDS_V1 = "horizontal-process-cards-v1"
_PROCESS_TOTAL_WIDTH_IN = 11.7
_PROCESS_GAP_IN = 0.24
_PROCESS_CARD_HORIZONTAL_PADDING_IN = 0.46
_PROCESS_TEXT_HEIGHT_IN = 1.95
_PROCESS_FONT_SIZE_PT = 16.0
_PROCESS_LINE_HEIGHT = 1.22
_PROCESS_MAX_ITEMS = 5


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
    font = font_loader(max(8, round(font_size_pt * dpi_scale)))
    maximum_width = max(1.0, width_pt * dpi_scale)
    measured_lines = 0
    for logical_line in str(text).splitlines() or [""]:
        if not logical_line:
            measured_lines += 1
            continue
        current_width = 0.0
        measured_lines += 1
        for character in logical_line:
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


def capacity_profile_items_fit(profile: str, items: list[str]) -> bool:
    if not profile:
        return True
    if profile == HORIZONTAL_PROCESS_CARDS_V1:
        return bool(horizontal_process_card_metrics(items)["fits"])
    raise ValueError(f"unknown_template_capacity_profile:{profile}")


__all__ = [
    "HORIZONTAL_PROCESS_CARDS_V1",
    "capacity_profile_items_fit",
    "horizontal_process_card_metrics",
    "wrapped_line_count",
]
