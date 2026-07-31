from __future__ import annotations

from slide_ai_runtime import ai_slide_planning_enabled


def test_ai_slide_planning_auto_enables_when_a_provider_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AI_SLIDE_PLANNER_ENABLED", raising=False)

    assert ai_slide_planning_enabled(provider_available=True) is True
    assert ai_slide_planning_enabled(provider_available=False) is False


def test_ai_slide_planning_respects_an_explicit_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("AI_SLIDE_PLANNER_ENABLED", "false")

    assert ai_slide_planning_enabled(provider_available=True) is False
