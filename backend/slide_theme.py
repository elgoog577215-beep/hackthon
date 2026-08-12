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
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def slide_theme_asset_path(
    theme: dict[str, Any],
    asset_name: str,
) -> Path | None:
    """Resolve a bundled theme asset without allowing paths outside the repo."""
    assets = theme.get("visual_assets") or {}
    asset = assets.get(asset_name) or {}
    source_path = str(asset.get("source_path") or "").strip()
    if not source_path:
        return None
    candidate = (REPOSITORY_ROOT / source_path).resolve()
    try:
        candidate.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


__all__ = [
    "THEME_PACK_PATH",
    "load_slide_theme_pack",
    "slide_theme",
    "slide_theme_asset_path",
    "slide_theme_version",
]
