"""Tool and font identity without any dependency on template construction."""
from __future__ import annotations
import hashlib
import importlib.metadata
import platform
import shutil
import subprocess
from pathlib import Path
from functools import lru_cache
from PIL import features
from ppt_layout_schema import COMPILER_VERSION, RENDERER_VERSION, QUALITY_VERSION, FONT_FAMILY
ASSET_ROOT = Path(__file__).resolve().parents[1] / "frontend/public/presentation-assets"
FONT_PATH = ASSET_ROOT / "fonts/NotoSansCJKsc-Regular.otf"

def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=16)
def _cli_version(path, modified_ns, argument):
    try:
        result = subprocess.run([path, argument], capture_output=True, text=True, check=True, timeout=20)
        return (result.stdout.strip() or result.stderr.strip()).splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unavailable"


def _tool_version(names, argument):
    path = next((p for name in names if (p := shutil.which(name))), None)
    return _cli_version(path, Path(path).stat().st_mtime_ns, argument) if path else "unavailable"


def tool_identity() -> dict:
    if not FONT_PATH.is_file():
        raise ValueError("teaching_font_missing")
    return {
        "compiler": COMPILER_VERSION,
        "renderer": RENDERER_VERSION,
        "quality": QUALITY_VERSION,
        "python": platform.python_version(),
        "font_family": FONT_FAMILY,
        "font_sha256": file_digest(FONT_PATH),
        "python_pptx": importlib.metadata.version("python-pptx"),
        "lxml": importlib.metadata.version("lxml"),
        "pillow": importlib.metadata.version("Pillow"),
        "freetype": features.version_module("freetype2"),
        "pypdf": importlib.metadata.version("pypdf"),
        "libreoffice": _tool_version(("soffice", "libreoffice"), "--version"),
        "poppler": _tool_version(("pdftoppm",), "-v"),
    }
