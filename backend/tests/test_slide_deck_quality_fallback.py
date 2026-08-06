from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_ai_v5_quality_failure_rebuilds_with_deterministic_plans(monkeypatch):
    import task_manager

    ai_story = SimpleNamespace(planner="ai")
    deterministic_story = SimpleNamespace(planner="deterministic_fallback")
    ai_allocation = SimpleNamespace(pages=[{"page_id": "ai-page"}])
    deterministic_allocation = SimpleNamespace(
        pages=[{"page_id": "deterministic-page"}],
    )
    ai_visual = SimpleNamespace(pages=[{"page_id": "ai-page"}])
    deterministic_visual = SimpleNamespace(
        pages=[{"page_id": "deterministic-page"}],
    )
    failed_quality = {
        "passed": False,
        "score": 23,
        "blocker_count": 99,
        "blockers": [{"code": "dangling_fragment", "page_id": "ai-page"}],
    }
    calls: list[dict] = []
    progress_events: list[dict] = []
    checkpoints: list[tuple[object, object, object]] = []

    def rebuild(*_args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            kwargs["progress_callback"]({
                "event": "build_blocked",
                "stage": "build_blocked",
                "progress": 100,
                "quality": failed_quality,
            })
            return {
                "status": "failed_using_last_available",
                "quality": failed_quality,
            }
        return {
            "status": "ready",
            "quality": {"passed": True, "score": 98, "blockers": []},
        }

    async def visual_planner(*_args, **_kwargs):
        return deterministic_visual

    async def checkpoint(allocation_plan, visual_plan, story_plan):
        checkpoints.append((allocation_plan, visual_plan, story_plan))

    monkeypatch.setattr(task_manager, "rebuild_slide_deck_variant_safely", rebuild)
    monkeypatch.setattr(task_manager, "fragment_course_document", lambda _document: ["fragment"])
    monkeypatch.setattr(
        task_manager,
        "compile_slide_story_plan_v2",
        lambda *_args, **_kwargs: SimpleNamespace(planner="deterministic_fallback"),
    )
    monkeypatch.setattr(
        task_manager,
        "compact_story_plan_v5",
        lambda *_args, **_kwargs: deterministic_story,
    )
    monkeypatch.setattr(
        task_manager,
        "allocation_from_story_plan_v5",
        lambda *_args, **_kwargs: (deterministic_allocation, []),
    )
    monkeypatch.setattr(task_manager, "plan_slide_visuals", visual_planner)

    result = await task_manager._rebuild_slide_variant_with_quality_fallback(
        document=SimpleNamespace(),
        course_view={},
        repository=SimpleNamespace(),
        mode="teaching",
        theme="qizhi-classroom",
        slide_schema="slide_deck_v5",
        allocation_plan=ai_allocation,
        visual_plan=ai_visual,
        story_plan=ai_story,
        progress_callback=progress_events.append,
        checkpoint_callback=checkpoint,
        resume_slides=[{"unit_id": "ai-slide"}],
    )

    assert len(calls) == 2
    assert calls[0]["story_plan"] is ai_story
    assert calls[1]["story_plan"] is deterministic_story
    assert calls[1]["allocation_plan"] is deterministic_allocation
    assert calls[1]["visual_plan"] is deterministic_visual
    assert calls[1]["resume_slides"] == []
    assert not any(event["event"] == "build_blocked" for event in progress_events)
    fallback_event = next(
        event for event in progress_events if event["event"] == "quality_fallback"
    )
    assert fallback_event["initial_blocker_count"] == 99
    assert fallback_event["initial_score"] == 23
    assert checkpoints == [
        (deterministic_allocation, deterministic_visual, deterministic_story),
    ]
    assert result["used_deterministic_fallback"] is True
    assert result["build"]["quality"]["passed"] is True
    assert result["initial_quality"] == failed_quality


@pytest.mark.asyncio
async def test_deterministic_v5_quality_failure_is_not_retried(monkeypatch):
    import task_manager

    calls: list[dict] = []
    failed = {
        "status": "failed_using_last_available",
        "quality": {"passed": False, "blocker_count": 2, "blockers": []},
    }

    def rebuild(*_args, **kwargs):
        calls.append(kwargs)
        return failed

    monkeypatch.setattr(task_manager, "rebuild_slide_deck_variant_safely", rebuild)

    result = await task_manager._rebuild_slide_variant_with_quality_fallback(
        document=SimpleNamespace(),
        course_view={},
        repository=SimpleNamespace(),
        mode="teaching",
        theme="qizhi-classroom",
        slide_schema="slide_deck_v5",
        allocation_plan=SimpleNamespace(pages=[]),
        visual_plan=SimpleNamespace(pages=[]),
        story_plan=SimpleNamespace(planner="deterministic_fallback"),
        progress_callback=lambda _event: None,
        checkpoint_callback=None,
        resume_slides=[],
    )

    assert len(calls) == 1
    assert result["used_deterministic_fallback"] is False
    assert result["build"] is failed
