"""Incrementally migrate a course question bank to the v2 assessment chain.

The script deliberately rebuilds small node batches. A failed batch is split
until the failing node can be retried without discarding unrelated successful
work. The server remains responsible for atomic bundle publication.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


TERMINAL_STATUSES = {"completed", "waiting_review", "failed"}
SUCCESS_STATUSES = {"completed", "waiting_review"}


def _load_node_ids(course_path: Path) -> list[str]:
    course = json.loads(course_path.read_text(encoding="utf-8"))
    return [
        str(node["node_id"])
        for node in course.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
        and node.get("node_id")
    ]


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _run_batch(
    client: httpx.Client,
    *,
    base_url: str,
    course_id: str,
    headers: dict[str, str],
    node_ids: list[str],
    poll_seconds: float,
    mode: str,
) -> dict[str, Any]:
    request_id = f"v2-migration-{uuid4().hex}"
    created = client.post(
        f"{base_url}/api/courses/{course_id}/question-bank/rebuild",
        headers=headers,
        json={
            "request_id": request_id,
            "scope": "nodes",
            "node_ids": node_ids,
            "mode": mode,
        },
    )
    created.raise_for_status()
    job = created.json()
    status_url = str(job["status_url"])
    if status_url.startswith("/"):
        status_url = f"{base_url}{status_url}"
    while True:
        current = client.get(status_url, headers=headers)
        current.raise_for_status()
        payload = current.json()
        status = str(payload.get("status") or "")
        if status in TERMINAL_STATUSES:
            return payload
        time.sleep(poll_seconds)


def _migrate_batch(
    client: httpx.Client,
    *,
    base_url: str,
    course_id: str,
    headers: dict[str, str],
    node_ids: list[str],
    poll_seconds: float,
    individual_retries: int,
    mode: str,
    completed: list[str],
) -> None:
    attempts = individual_retries + 1 if len(node_ids) == 1 else 1
    last: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        print(
            f"START nodes={','.join(node_ids)} attempt={attempt}/{attempts}",
            flush=True,
        )
        last = _run_batch(
            client,
            base_url=base_url,
            course_id=course_id,
            headers=headers,
            node_ids=node_ids,
            poll_seconds=poll_seconds,
            mode=mode,
        )
        if str(last.get("status") or "") in SUCCESS_STATUSES:
            completed.extend(node_ids)
            result = last.get("result") or {}
            print(
                "DONE "
                f"nodes={','.join(node_ids)} "
                f"bundle={result.get('bundle_revision_id')} "
                f"completed={len(completed)}",
                flush=True,
            )
            return
        print(
            f"FAILED nodes={','.join(node_ids)} error={last.get('error')}",
            flush=True,
        )
    if len(node_ids) > 1:
        midpoint = len(node_ids) // 2
        for subset in (node_ids[:midpoint], node_ids[midpoint:]):
            _migrate_batch(
                client,
                base_url=base_url,
                course_id=course_id,
                headers=headers,
                node_ids=subset,
                poll_seconds=poll_seconds,
                individual_retries=individual_retries,
                mode=mode,
                completed=completed,
            )
        return
    raise RuntimeError(
        f"node migration failed after retries: {node_ids[0]}: {last.get('error')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--course-path", type=Path, required=True)
    parser.add_argument("--user-id", default="teacher-codex")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--individual-retries", type=int, default=2)
    parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help="Use full to replace legacy approved items in the selected nodes.",
    )
    parser.add_argument(
        "--skip-node-id",
        action="append",
        default=[],
        help="Already migrated node id; may be supplied more than once.",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    skipped = set(args.skip_node_id)
    node_ids = [
        node_id
        for node_id in _load_node_ids(args.course_path)
        if node_id not in skipped
    ]
    completed: list[str] = []
    headers = {"X-User-Id": args.user_id}
    with httpx.Client(timeout=30.0) as client:
        for batch in _chunks(node_ids, args.batch_size):
            _migrate_batch(
                client,
                base_url=args.base_url.rstrip("/"),
                course_id=args.course_id,
                headers=headers,
                node_ids=batch,
                poll_seconds=args.poll_seconds,
                individual_retries=args.individual_retries,
                mode=args.mode,
                completed=completed,
            )
    print(f"MIGRATION_COMPLETE nodes={len(completed)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MIGRATION_ABORTED {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
