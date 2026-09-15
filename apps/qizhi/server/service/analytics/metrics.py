from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def summarize_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    page_views = [row for row in rows if row.get("event_name") == "page_view"]
    visitors = {row.get("visitor_id") for row in rows if row.get("visitor_id")}
    sessions = {row.get("session_id") for row in rows if row.get("session_id")}
    engaged_duration_ms = sum(
        int(row.get("duration_ms") or 0)
        for row in rows
        if row.get("event_name") == "page_engagement"
    )

    session_pages: dict[str, set[str]] = defaultdict(set)
    session_duration: dict[str, int] = defaultdict(int)
    successful_sessions: set[str] = set()
    for row in rows:
        session = row.get("session_id")
        if not session:
            continue
        if row.get("event_name") == "page_view" and row.get("page_instance_id"):
            session_pages[session].add(str(row["page_instance_id"]))
        if row.get("event_name") == "page_engagement":
            session_duration[session] += int(row.get("duration_ms") or 0)
        if row.get("event_name") == "task_succeeded":
            successful_sessions.add(session)
    bounce_count = sum(
        1
        for session in sessions
        if len(session_pages[session]) <= 1
        and session_duration[session] < 10_000
        and session not in successful_sessions
    )

    started = {row.get("workflow_id") for row in rows if row.get("event_name") == "task_started" and row.get("workflow_id")}
    succeeded = {row.get("workflow_id") for row in rows if row.get("event_name") == "task_succeeded" and row.get("workflow_id")}
    failed = {row.get("workflow_id") for row in rows if row.get("event_name") == "task_failed" and row.get("workflow_id")}
    cancelled = {row.get("workflow_id") for row in rows if row.get("event_name") == "task_cancelled" and row.get("workflow_id")}

    page_max_scroll: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("event_name") == "scroll_depth_reached" and row.get("page_instance_id"):
            page = str(row["page_instance_id"])
            page_max_scroll[page] = max(page_max_scroll[page], int(row.get("scroll_depth") or 0))

    return {
        "page_views": len(page_views),
        "unique_visitors": len(visitors),
        "sessions": len(sessions),
        "engaged_duration_ms": engaged_duration_ms,
        "average_engaged_seconds": round(engaged_duration_ms / max(1, len(sessions)) / 1000, 1),
        "bounce_count": bounce_count,
        "bounce_rate": _rate(bounce_count, len(sessions)),
        "task_started": len(started),
        "task_succeeded": len(succeeded),
        "task_failed": len(failed),
        "task_cancelled": len(cancelled),
        "task_completion_rate": _rate(len(succeeded), len(started)),
        "task_failure_rate": _rate(len(failed), len(started)),
        "task_cancellation_rate": _rate(len(cancelled), len(started)),
        "unfinished_tasks": max(0, len(started - succeeded - failed - cancelled)),
        "scroll_reach": {
            str(depth): sum(1 for value in page_max_scroll.values() if value >= depth)
            for depth in (25, 50, 75, 100)
        },
    }
