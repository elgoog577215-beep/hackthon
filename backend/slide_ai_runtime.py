"""Runtime policy for optional AI-assisted slide planning."""

from __future__ import annotations

import os

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def ai_slide_planning_enabled(*, provider_available: bool) -> bool:
    """Use AI automatically when configured, while preserving a kill switch."""
    configured = os.getenv("AI_SLIDE_PLANNER_ENABLED", "auto").strip().lower()
    if configured in _FALSE_VALUES:
        return False
    if configured in _TRUE_VALUES or configured in {"", "auto"}:
        return provider_available
    return False


__all__ = ["ai_slide_planning_enabled"]
