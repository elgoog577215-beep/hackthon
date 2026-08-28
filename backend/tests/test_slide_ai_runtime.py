from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from routers.teaching_representations import get_slide_deck_ai_planner
from slide_ai_runtime import ai_slide_planning_enabled
from jobs.manager import (
    _source_first_slide_visual_ai_worker,
    _source_first_story_ai_worker,
)


def test_ai_slide_planning_auto_enables_when_a_provider_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AI_SLIDE_PLANNER_ENABLED", raising=False)

    assert ai_slide_planning_enabled(provider_available=True) is True
    assert ai_slide_planning_enabled(provider_available=False) is False


def test_ai_slide_planning_respects_an_explicit_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("AI_SLIDE_PLANNER_ENABLED", "false")

    assert ai_slide_planning_enabled(provider_available=True) is False


def test_durable_v5_story_worker_uses_auto_mode_when_provider_exists(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AI_SLIDE_PLANNER_ENABLED", raising=False)

    with patch("jobs.manager.AIBase") as provider_type:
        provider_type.return_value.client = object()
        worker = _source_first_story_ai_worker()

    assert callable(worker)


def test_route_planner_uses_auto_mode_when_provider_exists(monkeypatch) -> None:
    monkeypatch.delenv("AI_SLIDE_PLANNER_ENABLED", raising=False)

    with patch(
        "routers.teaching_representations.AIBase",
    ) as provider_type:
        provider_type.return_value.client = object()
        planner = get_slide_deck_ai_planner()

    assert callable(planner)


@pytest.mark.asyncio
async def test_visual_worker_requires_complete_structured_json(monkeypatch) -> None:
    monkeypatch.delenv("AI_SLIDE_PLANNER_ENABLED", raising=False)

    with patch("jobs.manager.AIBase") as provider_type:
        provider = provider_type.return_value
        provider.client = object()
        provider._call_llm = AsyncMock(return_value='{"pages": []}')
        provider._extract_json.return_value = {"pages": []}
        worker = _source_first_slide_visual_ai_worker()
        assert worker is not None
        await worker({"response_contract": {"root": "slide_visual_plan_v1"}})

    kwargs = provider._call_llm.await_args.kwargs
    assert kwargs["json_mode"] is True
    assert kwargs["reject_truncated"] is True
    assert kwargs["max_tokens"] == 6144
