#!/usr/bin/env python3
"""Reset the shared matrix course for the Video 1 same-source recording."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from video1_demo_preset import prepare_video1_demo  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the shared Video 1 demo course.")
    parser.add_argument("--data-dir", type=Path, default=BACKEND / "data")
    args = parser.parse_args()
    print(json.dumps(prepare_video1_demo(args.data_dir), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
