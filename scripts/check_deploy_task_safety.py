#!/usr/bin/env python3
"""Fail closed when deployment would interrupt a background task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BUSY_EXIT_CODE = 75
MAX_TASK_INDEX_BYTES = 96 * 1024 * 1024
TERMINAL_STATUSES = {
    "cancelled",
    "canceled",
    "completed",
    "completed_with_warnings",
    "error",
    "failed",
}
QUIESCENT_STATUSES = {
    "conflict",
    "paused",
    "waiting_for_input",
    "waiting_for_review",
}


def inspect_task_index(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("generation_job_index_missing")
    if path.stat().st_size > MAX_TASK_INDEX_BYTES:
        raise ValueError("generation_job_index_oversized")
    with path.open(encoding="utf-8") as handle:
        tasks = json.load(handle)
    if not isinstance(tasks, dict):
        raise ValueError("generation_job_index_not_object")

    active_count = 0
    unknown_count = 0
    for task in tasks.values():
        if not isinstance(task, dict):
            unknown_count += 1
            continue
        status = str(task.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES or status in QUIESCENT_STATUSES:
            continue
        if status in {"pending", "queued", "running"}:
            active_count += 1
        else:
            # Unknown states cannot prove that stopping the process is safe.
            unknown_count += 1
    return {
        "safe_to_stop": active_count == 0 and unknown_count == 0,
        "active_count": active_count,
        "unknown_count": unknown_count,
        "task_count": len(tasks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_index", type=Path)
    args = parser.parse_args()
    try:
        result = inspect_task_index(args.task_index)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "safe_to_stop": False,
            "active_count": 0,
            "unknown_count": 1,
            "reason": type(exc).__name__,
        }, separators=(",", ":")))
        return BUSY_EXIT_CODE
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["safe_to_stop"] else BUSY_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
