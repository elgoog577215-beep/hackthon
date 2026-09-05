#!/usr/bin/env python3
"""Preview or apply deterministic course-block semantic repairs."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from course_repository import CourseDocumentRepository  # noqa: E402
from storage import storage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复正式课程文档中的空块与角色错配")
    parser.add_argument("--course-id", action="append", default=[], help="只处理指定课程，可重复")
    parser.add_argument("--apply", action="store_true", help="提交修复；默认只读预览")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    repository = CourseDocumentRepository(storage)
    requested = set(args.course_id)
    summaries = [
        item
        for item in storage.list_courses()
        if item.get("course_id") and (not requested or item.get("course_id") in requested)
    ]
    skipped_noncanonical = [
        str(item.get("course_id") or "")
        for item in summaries
        if item.get("course_schema_version") != "course_document_v1"
    ]
    course_ids = [
        str(item.get("course_id") or "")
        for item in summaries
        if item.get("course_schema_version") == "course_document_v1"
    ]
    found_ids = {str(item.get("course_id") or "") for item in summaries}
    missing = sorted(requested - found_ids)
    results: list[dict] = []
    failures: list[dict] = []
    for course_id in course_ids:
        try:
            result = await repository.repair_block_semantics(
                course_id,
                dry_run=not args.apply,
            )
            if result.get("changed"):
                results.append(result)
        except Exception as exc:  # CLI must report every course, not stop midway.
            failures.append({"course_id": course_id, "error": str(exc)})

    summary = {
        "mode": "apply" if args.apply else "preview",
        "scanned_courses": len(course_ids),
        "skipped_noncanonical_course_ids": skipped_noncanonical,
        "changed_courses": len(results),
        "removed_empty_blocks": sum(len(item.get("removed_empty_block_ids") or []) for item in results),
        "role_changes": sum(len(item.get("role_changes") or []) for item in results),
        "title_changes": sum(len(item.get("title_changes") or []) for item in results),
        "missing_course_ids": missing,
        "failures": failures,
        "courses": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures or missing else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
