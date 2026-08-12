"""Process-wide record of AI provider failover events.

The failover itself lives in ``ai_base`` (primary pool → ModelStore last resort).
It logs one warning when it switches, which is enough for a server operator
tailing logs and invisible to everyone else: the teacher watching a course
generate has no way to know the course was produced by the backup service, and
neither does the task summary.

This module is the seam between the two. ``ai_base`` records a switch; the task
manager reads the record when it projects a task, so the UI can say
"已切换备用模型服务" without ``ai_base`` needing to know tasks exist.

It is deliberately process-wide rather than per-task: a single ``AIBase`` client
is shared by every concurrent job, so a switch is a property of the provider, not
of one course. Consumers therefore compare timestamps rather than assume the
record belongs to them.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any


# Stable codes; the frontend resolves user-facing copy from these.
ROUTE_PRIMARY = "primary"
ROUTE_FALLBACK = "fallback"

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "route": ROUTE_PRIMARY,
    "switched_at": None,
    "reason_code": None,
    "fallback_endpoint": None,
    "switch_count": 0,
}


def record_fallback_switch(
    *,
    endpoint: str,
    reason_code: str | None = None,
    now: str | None = None,
) -> None:
    """Note that calls are now being served by the backup provider.

    ``endpoint`` is stored for operators; it is a base URL, never a key.
    """
    with _LOCK:
        _STATE["route"] = ROUTE_FALLBACK
        _STATE["switched_at"] = now or datetime.now().isoformat()
        _STATE["reason_code"] = reason_code or "primary_pool_exhausted"
        _STATE["fallback_endpoint"] = endpoint
        _STATE["switch_count"] = int(_STATE.get("switch_count") or 0) + 1


def record_primary_recovered(*, now: str | None = None) -> None:
    """Note that the primary provider answered again.

    Recovery is not a separate probe: the next successful primary call is the
    proof. Keeping ``switch_count`` lets an operator see flapping.
    """
    with _LOCK:
        if _STATE["route"] == ROUTE_PRIMARY:
            return
        _STATE["route"] = ROUTE_PRIMARY
        _STATE["switched_at"] = now or datetime.now().isoformat()
        _STATE["reason_code"] = "primary_recovered"
        _STATE["fallback_endpoint"] = None


def provider_route_snapshot() -> dict[str, Any]:
    """Current routing state, safe to embed in a task projection."""
    with _LOCK:
        return dict(_STATE)


def reset_provider_route() -> None:
    """Test seam: restore the initial primary-route state."""
    with _LOCK:
        _STATE.update({
            "route": ROUTE_PRIMARY,
            "switched_at": None,
            "reason_code": None,
            "fallback_endpoint": None,
            "switch_count": 0,
        })


__all__ = [
    "ROUTE_FALLBACK",
    "ROUTE_PRIMARY",
    "provider_route_snapshot",
    "record_fallback_switch",
    "record_primary_recovered",
    "reset_provider_route",
]
