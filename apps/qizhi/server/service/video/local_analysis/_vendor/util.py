"""共享工具：时间换算、原子写 JSON、日志、视频探测。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def get_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("vanalyze")
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# 时间换算
# ---------------------------------------------------------------------------

def hms_to_sec(value: Any) -> float:
    """把 'HH:MM:SS' / 'MM:SS' / 'SS' / 数字 转成秒。无法解析返回 0.0。"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    # 纯数字（可能带小数）
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return 0.0
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def sec_to_hms(seconds: float) -> str:
    """秒 -> 'HH:MM:SS'。"""
    seconds = max(0, int(round(float(seconds))))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# JSON I/O（原子写）
# ---------------------------------------------------------------------------

def atomic_write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ffprobe
# ---------------------------------------------------------------------------

def probe_duration(video_path: str) -> float:
    """用 ffprobe 取视频时长（秒）。"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)
