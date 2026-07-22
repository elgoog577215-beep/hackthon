#!/usr/bin/env python3
"""Prepare the deterministic Recordly environment for both demo videos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from video2_demo_preset import (  # noqa: E402
    COURSE_ID,
    DEMO_USER_ID,
    FIXED_PROMPT,
    TARGET_SECTION_ID,
    prepare_video2_demo,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the two-video Recordly demo.")
    parser.add_argument("--data-dir", type=Path, default=BACKEND / "data")
    parser.add_argument("--frontend-origin", default="http://127.0.0.1:5174")
    args = parser.parse_args()

    result = prepare_video2_demo(args.data_dir)
    origin = args.frontend_origin.rstrip("/")
    result["recordly_demo"] = {
        "course_id": COURSE_ID,
        "learner_user_id": DEMO_USER_ID,
        "viewport": {"width": 1440, "height": 810, "aspect_ratio": "16:9"},
        "environment": {
            "EVOLUTION_DEMO_MODE": "1",
            "VITE_RECORDLY_DEMO_MODE": "1",
            "VITE_LEARNER_USER_ID": DEMO_USER_ID,
        },
        "preload_routes": {
            "video_1_ppt": f"{origin}/course/{COURSE_ID}/ppt",
            "video_2_learning": f"{origin}/course/{COURSE_ID}/learn/{TARGET_SECTION_ID}",
        },
        "fixed_prompt": FIXED_PROMPT,
        "recording_gate": [
            "两条页面均已完成首次加载，录制中不出现加载页",
            "PPT 停在矩阵乘法目标编辑位置",
            "学习页停在 1.2，AI 老师面板关闭",
            "浏览器缩放 100%，视口固定 1440x810",
            "Recordly 只捕获浏览器窗口",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
