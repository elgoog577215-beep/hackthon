#!/usr/bin/env python3
"""一键重置视频二“个体化生长”的本地录制环境。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from video2_demo_preset import prepare_video2_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="重置《矩阵与线性变换》录屏专用课程和个人学习状态。",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=BACKEND / "data",
        help="后端数据目录，默认使用 backend/data。",
    )
    args = parser.parse_args()
    result = prepare_video2_demo(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
