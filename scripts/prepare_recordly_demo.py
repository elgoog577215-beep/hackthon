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

from video1_demo_preset import (  # noqa: E402
    COURSE_ID as VIDEO1_COURSE_ID,
    FOLLOWUP_GOAL,
    TARGET_GOAL,
    prepare_video1_demo,
)
from video2_demo_preset import (  # noqa: E402
    COURSE_ID as VIDEO2_COURSE_ID,
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

    video1 = prepare_video1_demo(args.data_dir)
    video2 = prepare_video2_demo(args.data_dir)
    origin = args.frontend_origin.rstrip("/")
    result = {
        "video_1": video1,
        "video_2": video2,
        "recordly_demo": {
            "video_1_course_id": VIDEO1_COURSE_ID,
            "video_2_course_id": VIDEO2_COURSE_ID,
            "learner_user_id": DEMO_USER_ID,
            "viewport": {"width": 1920, "height": 1080, "aspect_ratio": "16:9"},
            "environment": {
                "EVOLUTION_DEMO_MODE": "1",
                "VITE_RECORDLY_DEMO_MODE": "1",
                "VITE_LEARNER_USER_ID": DEMO_USER_ID,
            },
            "preload_routes": {
                "video_1_ppt": f"{origin}/course/{VIDEO1_COURSE_ID}/ppt",
                "video_2_learning": f"{origin}/course/{VIDEO2_COURSE_ID}/learn/{TARGET_SECTION_ID}",
            },
            "fixed_prompt": FIXED_PROMPT,
            "video_1_first_update": TARGET_GOAL,
            "video_1_second_update": FOLLOWUP_GOAL,
            "recording_gate": [
                "两条页面均已完成首次加载，录制中不出现加载页",
                "视频一 PPT 停在第17讲 DeepSeek 目标编辑位置",
                "学习页停在 1.2，AI 老师面板关闭",
                "浏览器缩放 100%，视口固定 1920x1080",
                "Recordly 只捕获浏览器窗口",
            ],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
