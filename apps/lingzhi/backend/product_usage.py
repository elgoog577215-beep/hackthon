"""Privacy-bounded product usage event ledger.

``UsageEvent`` answers how the product is used. It is deliberately separate
from ``LearningEvent`` (learning facts), task state (workflow truth), and model
telemetry (performance/cost). Nothing in this module is allowed to change a
course, a learner projection, a permission, or a task result.
"""

from __future__ import annotations

import os
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from storage import storage

USAGE_EVENTS_FILE = "usage_events.json"
SCHEMA_VERSION = 1

EVENT_NAMES = {
    "session_started",
    "page_viewed",
    "api_action_completed",
    "api_action_failed",
    "client_error",
}
SURFACES = {"teacher", "learner", "shared", "unknown"}
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_PROPERTY_KEYS = {
    "session_started": {"entry_kind"},
    "page_viewed": {"navigation_kind"},
    "api_action_completed": {
        "method", "route_template", "status_code", "duration_ms",
    },
    "api_action_failed": {
        "method", "route_template", "status_code", "duration_ms",
    },
    "client_error": {"error_kind"},
}
_ENTRY_KINDS = {"direct", "reload", "restore", "unknown"}
_NAVIGATION_KINDS = {"initial", "route"}
_ERROR_KINDS = {"window_error", "unhandled_rejection", "router_error"}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_SAFE_ROUTE_TEMPLATE = re.compile(r"^/api/[A-Za-z0-9_{}:./-]{1,235}$")
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def retention_days() -> int:
    return _bounded_int_env("LINGZHI_USAGE_RETENTION_DAYS", 180, 1, 730)


def usage_tracking_enabled() -> bool:
    return os.getenv("LINGZHI_USAGE_TRACKING_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on",
    }


def maximum_records() -> int:
    return _bounded_int_env("LINGZHI_USAGE_MAX_RECORDS", 200_000, 1_000, 1_000_000)


def _required_safe_name(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_NAME.fullmatch(normalized):
        raise ValueError(f"{field} must be a bounded stable identifier")
    return normalized


def _optional_safe_name(value: Any, field: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return _required_safe_name(normalized, field)


def _validate_properties(event_name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("properties must be an object")
    unknown = set(value) - _PROPERTY_KEYS[event_name]
    if unknown:
        raise ValueError(f"properties contain unregistered keys: {sorted(unknown)}")
    if any(isinstance(item, (dict, list, tuple, set)) for item in value.values()):
        raise ValueError("properties only accept scalar values")

    properties: dict[str, Any] = {}
    if event_name == "session_started":
        entry_kind = str(value.get("entry_kind") or "unknown").strip()
        if entry_kind not in _ENTRY_KINDS:
            raise ValueError("entry_kind is not registered")
        properties["entry_kind"] = entry_kind
    elif event_name == "page_viewed":
        navigation_kind = str(value.get("navigation_kind") or "route").strip()
        if navigation_kind not in _NAVIGATION_KINDS:
            raise ValueError("navigation_kind is not registered")
        properties["navigation_kind"] = navigation_kind
    elif event_name in {"api_action_completed", "api_action_failed"}:
        method = str(value.get("method") or "").strip().upper()
        if method not in MUTATION_METHODS:
            raise ValueError("method must be a mutation method")
        route_template = str(value.get("route_template") or "").strip()
        if "?" in route_template or "#" in route_template:
            raise ValueError("route_template must not include query or fragment")
        if not _SAFE_ROUTE_TEMPLATE.fullmatch(route_template):
            raise ValueError("route_template is not a safe API template")
        status_code = value.get("status_code", 0)
        duration_ms = value.get("duration_ms", 0)
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            raise ValueError("status_code must be an integer")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)):
            raise ValueError("duration_ms must be numeric")
        status_code = max(0, min(599, int(status_code)))
        duration_ms = max(0, min(3_600_000, int(round(duration_ms))))
        if event_name == "api_action_completed" and not 200 <= status_code < 400:
            raise ValueError("completed actions require a successful status_code")
        if event_name == "api_action_failed" and 200 <= status_code < 400:
            raise ValueError("failed actions cannot use a successful status_code")
        properties.update({
            "method": method,
            "route_template": route_template,
            "status_code": status_code,
            "duration_ms": duration_ms,
        })
    else:
        error_kind = str(value.get("error_kind") or "").strip()
        if error_kind not in _ERROR_KINDS:
            raise ValueError("error_kind is not registered")
        properties["error_kind"] = error_kind
    return properties


def validate_usage_event(value: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized event payload or reject it before persistence."""
    event_name = str(value.get("event_name") or "").strip()
    if event_name not in EVENT_NAMES:
        raise ValueError("event_name is not registered")
    client_event_id = _required_safe_name(value.get("client_event_id"), "client_event_id")
    session_id = _required_safe_name(value.get("session_id"), "session_id")
    surface = str(value.get("surface") or "unknown").strip()
    if surface not in SURFACES:
        raise ValueError("surface is not registered")
    route_name = _optional_safe_name(value.get("route_name"), "route_name")
    course_id = _optional_safe_name(value.get("course_id"), "course_id")
    client_occurred_at = _parse_timestamp(value.get("client_occurred_at"))
    if value.get("client_occurred_at") and client_occurred_at is None:
        raise ValueError("client_occurred_at must be an ISO timestamp")
    return {
        "client_event_id": client_event_id,
        "event_name": event_name,
        "session_id": session_id,
        "surface": surface,
        "route_name": route_name,
        "course_id": course_id,
        "properties": _validate_properties(event_name, value.get("properties") or {}),
        "client_occurred_at": _iso(client_occurred_at) if client_occurred_at else None,
    }


def _load_all() -> list[dict[str, Any]]:
    stored = storage.load_data(USAGE_EVENTS_FILE) or []
    return [dict(item) for item in stored] if isinstance(stored, list) else []


def _within_retention(event: dict[str, Any], cutoff: datetime) -> bool:
    received = _parse_timestamp(event.get("received_at"))
    return received is not None and received >= cutoff


def append_usage_events(
    *,
    user_id: str,
    events: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and append one client batch atomically under the process lock."""
    if not usage_tracking_enabled():
        return {
            "status": "disabled",
            "accepted": 0,
            "duplicates": 0,
            "dropped": len(events),
            "items": [],
            "retention_days": retention_days(),
        }
    normalized = [validate_usage_event(item) for item in events]
    received_at = (now or _now()).astimezone(timezone.utc)
    cutoff = received_at - timedelta(days=retention_days())

    outcome: dict[str, Any] = {}

    def update_ledger(current: Any) -> list[dict[str, Any]]:
        stored = [
            dict(item)
            for item in (current if isinstance(current, list) else [])
            if _within_retention(item, cutoff)
        ]
        existing = {
            (str(item.get("user_id") or ""), str(item.get("client_event_id") or "")): item
            for item in stored
        }
        results: list[dict[str, Any]] = []
        accepted = 0
        duplicates = 0
        for item in normalized:
            key = (user_id, item["client_event_id"])
            prior = existing.get(key)
            if prior is not None:
                duplicates += 1
                results.append({
                    "client_event_id": item["client_event_id"],
                    "event_id": prior.get("event_id"),
                    "status": "duplicate",
                })
                continue
            event = {
                "event_id": f"uev_{uuid.uuid4().hex}",
                **item,
                "user_id": user_id,
                "received_at": _iso(received_at),
                "schema_version": SCHEMA_VERSION,
            }
            stored.append(event)
            existing[key] = event
            accepted += 1
            results.append({
                "client_event_id": item["client_event_id"],
                "event_id": event["event_id"],
                "status": "accepted",
            })

        capacity = maximum_records()
        if len(stored) > capacity:
            stored = stored[-capacity:]
        outcome.update({
            "accepted": accepted,
            "duplicates": duplicates,
            "items": results,
            "retention_days": retention_days(),
        })
        return stored

    storage.update_data(USAGE_EVENTS_FILE, update_ledger)
    return outcome


def load_usage_events(
    *,
    user_id: str | None = None,
    now: datetime | None = None,
    days: int | None = None,
) -> list[dict[str, Any]]:
    events = _load_all()
    if user_id is not None:
        events = [item for item in events if item.get("user_id") == user_id]
    if days is not None:
        cutoff = (now or _now()).astimezone(timezone.utc) - timedelta(days=days)
        events = [item for item in events if _within_retention(item, cutoff)]
    return [deepcopy(item) for item in events]


def delete_usage_events(*, user_id: str) -> dict[str, Any]:
    outcome = {"status": "deleted", "deleted_event_count": 0}

    def update_ledger(current: Any) -> list[dict[str, Any]]:
        events = [dict(item) for item in current] if isinstance(current, list) else []
        remaining = [item for item in events if item.get("user_id") != user_id]
        outcome["deleted_event_count"] = len(events) - len(remaining)
        return remaining

    storage.update_data(USAGE_EVENTS_FILE, update_ledger)
    return outcome


def export_usage_events(*, user_id: str) -> dict[str, Any]:
    events = load_usage_events(user_id=user_id)
    return {
        "schema_version": "usage_export_v1",
        "user_id": user_id,
        "exported_at": _iso(_now()),
        "manifest": {
            "event_count": len(events),
            "event_names": sorted({str(item.get("event_name") or "") for item in events}),
            "fact_source": "UsageEvent",
            "non_authoritative": True,
        },
        "events": events,
    }


def _top(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def summarize_usage_events(
    *,
    events: Iterable[dict[str, Any]] | None = None,
    user_id: str | None = None,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build action-oriented aggregate metrics from server receipt timestamps."""
    current = (now or _now()).astimezone(timezone.utc)
    selected = list(events) if events is not None else load_usage_events(user_id=user_id)
    cutoff = current - timedelta(days=days)
    selected = [item for item in selected if _within_retention(item, cutoff)]

    meaningful_names = {"page_viewed", "api_action_completed", "api_action_failed"}
    meaningful = [item for item in selected if item.get("event_name") in meaningful_names]
    successful = [item for item in selected if item.get("event_name") == "api_action_completed"]
    failed = [item for item in selected if item.get("event_name") == "api_action_failed"]
    action_total = len(successful) + len(failed)

    pages = Counter(
        str(item.get("route_name") or "unknown")
        for item in selected if item.get("event_name") == "page_viewed"
    )
    actions = Counter(
        str((item.get("properties") or {}).get("route_template") or "unknown")
        for item in selected
        if item.get("event_name") in {"api_action_completed", "api_action_failed"}
    )
    event_counts = Counter(str(item.get("event_name") or "unknown") for item in selected)

    daily: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "users": set(), "sessions": set(), "page_views": 0,
        "successful_actions": 0, "failed_actions": 0,
    })
    for item in selected:
        received = _parse_timestamp(item.get("received_at"))
        if received is None:
            continue
        bucket = daily[received.date().isoformat()]
        if item.get("event_name") in meaningful_names:
            bucket["users"].add(str(item.get("user_id") or ""))
            bucket["sessions"].add(str(item.get("session_id") or ""))
        if item.get("event_name") == "page_viewed":
            bucket["page_views"] += 1
        elif item.get("event_name") == "api_action_completed":
            bucket["successful_actions"] += 1
        elif item.get("event_name") == "api_action_failed":
            bucket["failed_actions"] += 1

    return {
        "schema_version": "usage_summary_v1",
        "window_days": days,
        "window_end": _iso(current),
        "metrics": {
            "meaningful_active_users": len({str(item.get("user_id") or "") for item in meaningful}),
            "meaningful_active_sessions": len({str(item.get("session_id") or "") for item in meaningful}),
            "page_views": event_counts["page_viewed"],
            "successful_actions": len(successful),
            "failed_actions": len(failed),
            "action_success_rate": round(len(successful) / action_total, 4) if action_total else None,
            "client_errors": event_counts["client_error"],
            "total_events": len(selected),
        },
        "top_pages": _top(pages),
        "top_actions": _top(actions),
        "event_counts": _top(event_counts, limit=len(event_counts)),
        "daily": [
            {
                "date": date,
                "active_users": len(values["users"]),
                "active_sessions": len(values["sessions"]),
                "page_views": values["page_views"],
                "successful_actions": values["successful_actions"],
                "failed_actions": values["failed_actions"],
            }
            for date, values in sorted(daily.items())
        ],
    }


__all__ = [
    "EVENT_NAMES",
    "SCHEMA_VERSION",
    "USAGE_EVENTS_FILE",
    "append_usage_events",
    "delete_usage_events",
    "export_usage_events",
    "load_usage_events",
    "maximum_records",
    "retention_days",
    "summarize_usage_events",
    "usage_tracking_enabled",
    "validate_usage_event",
]
