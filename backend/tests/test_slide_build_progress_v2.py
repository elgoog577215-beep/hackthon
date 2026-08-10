from datetime import datetime, timedelta, timezone
from pathlib import Path

from slide_build_progress_v2 import (
    SlideBuildProgressRepositoryV2,
    SlideBuildProgressTrackerV2,
    SlideWorkItemV2,
)


def _now(offset: int = 0) -> datetime:
    return datetime(2026, 8, 10, 8, 0, offset, tzinfo=timezone.utc)


def test_weighted_progress_is_monotonic_when_work_is_discovered() -> None:
    tracker = SlideBuildProgressTrackerV2.create("task-v6", now=_now())
    tracker.add_work(
        [
            SlideWorkItemV2(item_id="validate", kind="local", stage="source", label="校验课程块"),
            SlideWorkItemV2(item_id="story-a", kind="ai_batch", stage="story", label="故事批次"),
        ],
        now=_now(1),
    )
    tracker.snapshot(now=_now(1))
    tracker.complete("validate", now=_now(2))
    before_discovery = tracker.manifest.display_percent

    tracker.add_work(
        [
            SlideWorkItemV2(item_id="page-1", kind="render_page", stage="render", label="渲染第1页"),
            SlideWorkItemV2(item_id="asset-1", kind="asset", stage="assets", label="准备素材"),
        ],
        now=_now(3),
    )

    assert tracker.manifest.total_weight == 19
    assert tracker.manifest.display_percent == before_discovery
    event = tracker.snapshot(now=_now(3))
    assert event["newly_discovered_work"] == 2
    assert event["completed_weight"] == 1
    assert event["total_weight"] == 19


def test_progress_caps_at_99_until_atomic_publish() -> None:
    tracker = SlideBuildProgressTrackerV2.create("task-v6", now=_now())
    tracker.add_work(
        [SlideWorkItemV2(item_id="quality", kind="local", stage="quality", label="质量门")],
        now=_now(1),
    )
    tracker.complete("quality", now=_now(2))

    assert tracker.manifest.display_percent == 99
    assert tracker.snapshot(now=_now(2))["published"] is False

    tracker.mark_published(now=_now(3))
    assert tracker.manifest.display_percent == 100
    assert tracker.manifest.status == "completed"


def test_progress_manifest_resumes_after_repository_reload(tmp_path: Path) -> None:
    repository = SlideBuildProgressRepositoryV2(tmp_path)
    tracker = SlideBuildProgressTrackerV2.create("task-v6", repository=repository, now=_now())
    tracker.add_work(
        [
            SlideWorkItemV2(item_id="story", kind="ai_batch", stage="story", label="故事规划"),
            SlideWorkItemV2(item_id="visual", kind="ai_batch", stage="visual", label="视觉规划"),
        ],
        now=_now(1),
    )
    tracker.start(
        "story",
        now=_now(2),
        chapter_id="chapter-1",
        batch_id="story-1",
        provider_wait=True,
        retry_attempt=2,
    )
    tracker.complete("story", now=_now(3))

    restored = SlideBuildProgressTrackerV2.load("task-v6", repository=repository)

    assert restored.manifest.completed_weight == 10
    assert restored.manifest.display_percent == tracker.manifest.display_percent
    assert restored.manifest.items[0].status == "completed"
    assert restored.manifest.current_context.chapter_id == "chapter-1"
    assert restored.manifest.current_context.retry_attempt == 2


def test_active_restart_requeues_only_interrupted_work_without_progress_rollback(
    tmp_path: Path,
) -> None:
    repository = SlideBuildProgressRepositoryV2(tmp_path)
    tracker = SlideBuildProgressTrackerV2.create("task-restart", repository=repository, now=_now())
    tracker.add_work([
        SlideWorkItemV2(item_id="story-1", kind="ai_batch", stage="story", label="故事 1"),
        SlideWorkItemV2(item_id="story-2", kind="ai_batch", stage="story", label="故事 2"),
    ], now=_now(1))
    tracker.start("story-1", now=_now(2))
    tracker.complete("story-1", now=_now(3))
    tracker.start("story-2", now=_now(4), provider_wait=True)
    before = tracker.manifest.display_percent

    restored = SlideBuildProgressTrackerV2.load("task-restart", repository=repository)
    restored.resume_active(now=_now(5))

    assert restored.manifest.items[0].status == "completed"
    assert restored.manifest.items[1].status == "pending"
    assert restored.manifest.current_context.provider_wait is False
    assert restored.manifest.display_percent == before


def test_heartbeat_is_due_every_five_seconds_and_reports_provider_wait() -> None:
    tracker = SlideBuildProgressTrackerV2.create("task-v6", now=_now())
    tracker.add_work(
        [SlideWorkItemV2(item_id="story", kind="ai_batch", stage="story", label="故事规划")],
        now=_now(1),
    )
    tracker.start(
        "story",
        now=_now(2),
        chapter_id="chapter-1",
        batch_id="story-1",
        provider_wait=True,
        retry_attempt=1,
    )

    assert tracker.heartbeat_due(now=_now(6)) is False
    assert tracker.heartbeat_due(now=_now(7)) is True
    heartbeat = tracker.heartbeat(now=_now(7))
    assert heartbeat["event_type"] == "heartbeat"
    assert heartbeat["provider_wait"] is True
    assert heartbeat["retry_attempt"] == 1
    assert heartbeat["current_batch_id"] == "story-1"


def test_terminal_failure_keeps_structured_scope() -> None:
    tracker = SlideBuildProgressTrackerV2.create("task-v6", now=_now())
    tracker.add_work(
        [SlideWorkItemV2(item_id="story", kind="ai_batch", stage="story", label="故事规划")],
        now=_now(1),
    )
    tracker.fail(
        "story",
        stage="story",
        code="story_ai_batch_timeout",
        message="provider timed out",
        retryable=True,
        chapter_id="chapter-1",
        batch_id="story-1",
        now=_now(2),
    )

    event = tracker.snapshot(now=_now(2))
    assert event["status"] == "failed"
    assert event["failure"] == {
        "stage": "story",
        "code": "story_ai_batch_timeout",
        "message": "provider timed out",
        "retryable": True,
        "chapter_id": "chapter-1",
        "page_id": "",
        "batch_id": "story-1",
    }
