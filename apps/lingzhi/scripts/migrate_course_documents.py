#!/usr/bin/env python3
"""Preview or apply one deterministic legacy course-document migration."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from course_repository import CourseDocumentRepository  # noqa: E402
from storage import Storage  # noqa: E402


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("--data-dir", default=str(BACKEND_DIR / "data"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--source-checksum", default="")
    args = parser.parse_args()

    storage = Storage(data_dir=args.data_dir)
    storage.running = False
    repository = CourseDocumentRepository(storage)
    envelope = repository.document_envelope(args.course_id)
    if args.apply:
        checksum = args.source_checksum or str(envelope.get("migration", {}).get("source_checksum") or "")
        envelope = await repository.migrate_legacy_course(
            args.course_id,
            expected_source_checksum=checksum,
        )
    print(json.dumps({
        "course_id": envelope["course_id"],
        "source_format": envelope["source_format"],
        "migration": envelope["migration"],
        "document_revision": envelope["document"]["document_revision"],
        "section_count": len(envelope["document"]["sections"]),
        "block_count": len(envelope["document"]["blocks"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
