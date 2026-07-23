"""Shared slide theme tokens consumed by browser preview and PPTX export."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


THEME_PACK_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "data"
    / "slide-themes.json"
)


@lru_cache(maxsize=1)
def load_slide_theme_pack() -> dict[str, Any]:
    with THEME_PACK_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != "slide_theme_pack_v1":
        raise ValueError("Unsupported slide theme pack")
    return value


def slide_theme_version() -> str:
    return str(load_slide_theme_pack().get("version") or "")


def slide_theme(theme: str) -> dict[str, Any]:
    aliases = {
        "qingfeng-classroom": "qizhi-classroom",
        "academic-bluegray": "academic-editorial",
    }
    normalized = aliases.get(theme, theme)
    themes = load_slide_theme_pack().get("themes") or {}
    if normalized not in themes:
        raise ValueError(
            f"Unknown slide theme '{theme}'. Expected one of: "
            + ", ".join(sorted(themes))
        )
    return dict(themes[normalized])


__all__ = [
    "THEME_PACK_PATH",
    "load_slide_theme_pack",
    "slide_theme",
    "slide_theme_version",
]
