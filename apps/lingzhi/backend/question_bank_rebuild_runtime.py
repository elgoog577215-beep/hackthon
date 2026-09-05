"""Runtime port for submitting durable question-bank rebuild jobs.

Business modules may register rebuild jobs, but the HTTP router owns the
process-local executor that runs them.  This small port keeps that dependency
one-way: the router installs its adapter during startup and business code reads
the adapter without importing a router module.
"""

from __future__ import annotations

from threading import RLock
from typing import Any, Callable


_runtime_lock = RLock()
_executor: Any = None
_payload_factory: Callable[..., Any] | None = None


def configure_question_bank_rebuild_runtime(
    *,
    executor: Any,
    payload_factory: Callable[..., Any],
) -> None:
    """Install the router-owned executor behind the business-layer port."""
    if executor is None or not callable(payload_factory):
        raise ValueError("question-bank rebuild runtime is incomplete")
    with _runtime_lock:
        global _executor, _payload_factory
        _executor = executor
        _payload_factory = payload_factory


def current_question_bank_rebuild_runtime(
) -> tuple[Any, Callable[..., Any] | None]:
    """Return the configured adapter without importing or starting the router."""
    with _runtime_lock:
        return _executor, _payload_factory


__all__ = [
    "configure_question_bank_rebuild_runtime",
    "current_question_bank_rebuild_runtime",
]
