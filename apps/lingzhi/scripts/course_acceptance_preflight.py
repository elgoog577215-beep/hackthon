#!/usr/bin/env python3
"""Emit a read-only JSON preflight report for persisted courses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from course_acceptance import scan_course_directory  # noqa: E402
from course_versions import course_version_repository  # noqa: E402
from storage import COURSES_DIR  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读检查课程是否满足全链路课程使用契约")
    parser.add_argument("--courses-dir", default=COURSES_DIR, help="课程主文件目录")
    parser.add_argument("--course-id", help="只检查指定课程")
    parser.add_argument(
        "--profile",
        choices=("standard", "reading_only", "compatibility", "auto"),
        default="standard",
        help="验收口径，默认使用严格 standard",
    )
    parser.add_argument("--output", help="同时写入指定 JSON 文件")
    parser.add_argument("--compact", action="store_true", help="输出紧凑 JSON")
    parser.add_argument("--fail-on-blocked", action="store_true", help="存在阻断课程时返回退出码 2")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = scan_course_directory(
        args.courses_dir,
        requested_profile=args.profile,
        course_id=args.course_id,
        version_reader=course_version_repository,
    )
    payload = json.dumps(
        report,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        separators=(",", ":") if args.compact else None,
    )
    print(payload)
    if args.output:
        Path(args.output).write_text(f"{payload}\n", encoding="utf-8")
    if args.fail_on_blocked and report["summary"]["blocked"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
