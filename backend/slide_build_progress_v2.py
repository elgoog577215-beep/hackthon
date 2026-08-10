"""Persisted weighted progress protocol for slide-deck V6."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from slide_deck_v6 import V6Failure


WorkKind = Literal["local", "render_page", "asset", "ai_batch"]
WorkStatus = Literal["pending", "running", "completed", "failed"]
ManifestStatus = Literal["active", "failed", "completed"]

DEFAULT_WORK_WEIGHTS: dict[WorkKind, int] = {
    "local": 1,
    "render_page": 3,
    "asset": 5,
    "ai_batch": 10,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideWorkItemV2(_StrictModel):
    item_id: str
    kind: WorkKind
    stage: str
    label: str
    weight: int = Field(default=0, ge=0)
    status: WorkStatus = "pending"
    chapter_id: str = ""
    batch_id: str = ""
    page_id: str = ""
    discovered_at: str = ""
    started_at: str = ""
    completed_at: str = ""

    @model_validator(mode="after")
    def apply_default_weight(self) -> "SlideWorkItemV2":
        if self.weight == 0:
            self.weight = DEFAULT_WORK_WEIGHTS[self.kind]
        return self


class SlideProgressContextV2(_StrictModel):
    stage: str = "source"
    step_index: int = Field(default=0, ge=0)
    step_count: int = Field(default=0, ge=0)
    chapter_id: str = ""
    batch_id: str = ""
    page_id: str = ""
    provider_wait: bool = False
    retry_attempt: int = Field(default=0, ge=0)


class SlideBuildProgressManifestV2(_StrictModel):
    schema_version: Literal["slide_build_progress_v2"] = "slide_build_progress_v2"
    task_id: str
    status: ManifestStatus = "active"
    items: list[SlideWorkItemV2] = Field(default_factory=list)
    current_context: SlideProgressContextV2 = Field(default_factory=SlideProgressContextV2)
    completed_weight: int = Field(default=0, ge=0)
    total_weight: int = Field(default=0, ge=0)
    display_percent: int = Field(default=0, ge=0, le=100)
    published: bool = False
    failure: V6Failure | None = None
    started_at: str
    updated_at: str
    last_event_at: str
    newly_discovered_since_event: int = Field(default=0, ge=0)


class SlideBuildProgressRepositoryV2:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        safe = "".join(character for character in task_id if character.isalnum() or character in "-_")
        if safe != task_id or not safe:
            raise ValueError("Invalid slide progress task ID")
        path = (self.root / f"{safe}.json").resolve()
        path.relative_to(self.root)
        return path

    def save(self, manifest: SlideBuildProgressManifestV2) -> None:
        path = self._path(manifest.task_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def load(self, task_id: str) -> SlideBuildProgressManifestV2:
        path = self._path(task_id)
        if not path.is_file():
            raise FileNotFoundError(task_id)
        return SlideBuildProgressManifestV2.model_validate_json(path.read_text(encoding="utf-8"))


class SlideBuildProgressTrackerV2:
    def __init__(
        self,
        manifest: SlideBuildProgressManifestV2,
        *,
        repository: SlideBuildProgressRepositoryV2 | None = None,
    ) -> None:
        self.manifest = manifest
        self.repository = repository

    @classmethod
    def create(
        cls,
        task_id: str,
        *,
        repository: SlideBuildProgressRepositoryV2 | None = None,
        now: datetime | None = None,
    ) -> "SlideBuildProgressTrackerV2":
        current = now or _utc_now()
        manifest = SlideBuildProgressManifestV2(
            task_id=task_id,
            started_at=_iso(current),
            updated_at=_iso(current),
            last_event_at=_iso(current),
        )
        tracker = cls(manifest, repository=repository)
        tracker._persist()
        return tracker

    @classmethod
    def load(
        cls,
        task_id: str,
        *,
        repository: SlideBuildProgressRepositoryV2,
    ) -> "SlideBuildProgressTrackerV2":
        return cls(repository.load(task_id), repository=repository)

    def _persist(self) -> None:
        if self.repository:
            self.repository.save(self.manifest)

    def _item(self, item_id: str) -> SlideWorkItemV2:
        item = next((candidate for candidate in self.manifest.items if candidate.item_id == item_id), None)
        if item is None:
            raise KeyError(item_id)
        return item

    def _touch(self, now: datetime) -> None:
        self.manifest.updated_at = _iso(now)

    def _recalculate(self) -> None:
        self.manifest.total_weight = sum(item.weight for item in self.manifest.items)
        self.manifest.completed_weight = sum(
            item.weight for item in self.manifest.items if item.status == "completed"
        )
        if self.manifest.published:
            target = 100
        elif self.manifest.total_weight and self.manifest.completed_weight == self.manifest.total_weight:
            target = 99
        elif self.manifest.total_weight:
            target = min(99, int(self.manifest.completed_weight * 100 / self.manifest.total_weight))
        else:
            target = 0
        self.manifest.display_percent = max(self.manifest.display_percent, target)

    def _set_current_item_context(self, item: SlideWorkItemV2) -> None:
        index = self.manifest.items.index(item)
        self.manifest.current_context.stage = item.stage
        self.manifest.current_context.step_index = index + 1
        self.manifest.current_context.step_count = len(self.manifest.items)
        self.manifest.current_context.chapter_id = item.chapter_id or self.manifest.current_context.chapter_id
        self.manifest.current_context.batch_id = item.batch_id or self.manifest.current_context.batch_id
        self.manifest.current_context.page_id = item.page_id or self.manifest.current_context.page_id

    def add_work(self, items: list[SlideWorkItemV2], *, now: datetime | None = None) -> None:
        current = now or _utc_now()
        known = {item.item_id for item in self.manifest.items}
        added = 0
        for item in items:
            if item.item_id in known:
                continue
            item.discovered_at = item.discovered_at or _iso(current)
            self.manifest.items.append(item)
            known.add(item.item_id)
            added += 1
        self.manifest.newly_discovered_since_event += added
        self.manifest.current_context.step_count = len(self.manifest.items)
        self._touch(current)
        self._recalculate()
        self._persist()

    def start(
        self,
        item_id: str,
        *,
        now: datetime | None = None,
        chapter_id: str = "",
        batch_id: str = "",
        page_id: str = "",
        provider_wait: bool = False,
        retry_attempt: int = 0,
    ) -> None:
        current = now or _utc_now()
        item = self._item(item_id)
        item.status = "running"
        item.started_at = item.started_at or _iso(current)
        item.chapter_id = chapter_id or item.chapter_id
        item.batch_id = batch_id or item.batch_id
        item.page_id = page_id or item.page_id
        self._set_current_item_context(item)
        self.manifest.current_context.provider_wait = provider_wait
        self.manifest.current_context.retry_attempt = retry_attempt
        self.manifest.last_event_at = _iso(current)
        self._touch(current)
        self._persist()

    def complete(self, item_id: str, *, now: datetime | None = None) -> None:
        current = now or _utc_now()
        item = self._item(item_id)
        item.status = "completed"
        item.started_at = item.started_at or _iso(current)
        item.completed_at = _iso(current)
        self._set_current_item_context(item)
        self.manifest.current_context.provider_wait = False
        self._touch(current)
        self._recalculate()
        self._persist()

    def fail(
        self,
        item_id: str,
        *,
        stage: str,
        code: str,
        message: str,
        retryable: bool,
        chapter_id: str = "",
        page_id: str = "",
        batch_id: str = "",
        now: datetime | None = None,
    ) -> None:
        current = now or _utc_now()
        item = self._item(item_id)
        item.status = "failed"
        item.completed_at = _iso(current)
        self.manifest.status = "failed"
        self.manifest.failure = V6Failure(
            stage=stage,
            code=code,
            message=message,
            retryable=retryable,
            chapter_id=chapter_id,
            page_id=page_id,
            batch_id=batch_id,
        )
        self.manifest.current_context = SlideProgressContextV2(
            stage=stage,
            step_index=self.manifest.items.index(item) + 1,
            step_count=len(self.manifest.items),
            chapter_id=chapter_id,
            batch_id=batch_id,
            page_id=page_id,
        )
        self._touch(current)
        self._recalculate()
        self._persist()

    def mark_published(self, *, now: datetime | None = None) -> None:
        current = now or _utc_now()
        if any(item.status != "completed" for item in self.manifest.items):
            raise ValueError("Cannot publish before every work item completes")
        self.manifest.published = True
        self.manifest.status = "completed"
        self.manifest.failure = None
        self._touch(current)
        self._recalculate()
        self._persist()

    def heartbeat_due(self, *, now: datetime | None = None) -> bool:
        current = now or _utc_now()
        return (current - _parse(self.manifest.last_event_at)).total_seconds() >= 5

    def _event(self, *, now: datetime, event_type: str) -> dict[str, object]:
        completed_items = sum(item.status == "completed" for item in self.manifest.items)
        elapsed = max(0.0, (now - _parse(self.manifest.started_at)).total_seconds())
        remaining_weight = max(0, self.manifest.total_weight - self.manifest.completed_weight)
        seconds_per_weight = elapsed / self.manifest.completed_weight if self.manifest.completed_weight else 0
        context = self.manifest.current_context
        event = {
            "schema_version": self.manifest.schema_version,
            "event_type": event_type,
            "task_id": self.manifest.task_id,
            "status": self.manifest.status,
            "percent": self.manifest.display_percent,
            "published": self.manifest.published,
            "stage": context.stage,
            "step_index": context.step_index,
            "step_count": context.step_count,
            "current_chapter_id": context.chapter_id,
            "current_batch_id": context.batch_id,
            "current_page_id": context.page_id,
            "completed_items": completed_items,
            "total_items": len(self.manifest.items),
            "completed_weight": self.manifest.completed_weight,
            "total_weight": self.manifest.total_weight,
            "elapsed_seconds": round(elapsed, 3),
            "provider_wait": context.provider_wait,
            "retry_attempt": context.retry_attempt,
            "newly_discovered_work": self.manifest.newly_discovered_since_event,
            "estimated_remaining_seconds": round(remaining_weight * seconds_per_weight, 3) if seconds_per_weight else None,
            "failure": self.manifest.failure.model_dump(mode="json") if self.manifest.failure else None,
            "items": [item.model_dump(mode="json") for item in self.manifest.items],
        }
        self.manifest.newly_discovered_since_event = 0
        self.manifest.last_event_at = _iso(now)
        self._touch(now)
        self._persist()
        return event

    def snapshot(self, *, now: datetime | None = None) -> dict[str, object]:
        return self._event(now=now or _utc_now(), event_type="progress")

    def heartbeat(self, *, now: datetime | None = None) -> dict[str, object]:
        return self._event(now=now or _utc_now(), event_type="heartbeat")


__all__ = [
    "DEFAULT_WORK_WEIGHTS",
    "SlideBuildProgressManifestV2",
    "SlideBuildProgressRepositoryV2",
    "SlideBuildProgressTrackerV2",
    "SlideWorkItemV2",
]
