import json
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalyticsEventName(str, Enum):
    PAGE_VIEW = "page_view"
    PAGE_ENGAGEMENT = "page_engagement"
    SCROLL_DEPTH_REACHED = "scroll_depth_reached"
    TASK_STARTED = "task_started"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    FEATURE_USED = "feature_used"


_ALLOWED_PROPERTY_KEYS = {
    "feature",
    "task_type",
    "source",
    "mode",
    "error_code",
    "result_category",
    "trigger",
}
_MAX_PROPERTIES_BYTES = 4096


def sanitize_properties(value: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only small, explicitly approved analytics dimensions."""
    if not value:
        return {}
    clean: dict[str, Any] = {}
    for key in _ALLOWED_PROPERTY_KEYS:
        item = value.get(key)
        if isinstance(item, (str, int, float, bool)) and len(str(item)) <= 200:
            clean[key] = item
    while clean and len(json.dumps(clean, ensure_ascii=False).encode("utf-8")) > _MAX_PROPERTIES_BYTES:
        clean.pop(next(reversed(clean)))
    return clean


class AnalyticsEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    event_name: AnalyticsEventName
    anonymous_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    page_instance_id: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    workflow_id: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    page_path: str | None = Field(None, max_length=512)
    outcome: Literal["success", "failed", "cancelled"] | None = None
    duration_ms: int | None = Field(None, ge=0, le=3_600_000)
    scroll_depth: int | None = Field(None, ge=0, le=100)
    properties: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = Field(default=1, ge=1, le=10)
    source: Literal["web", "mobile"] = "web"
    client_version: str | None = Field(None, max_length=64)

    @field_validator("page_path")
    @classmethod
    def normalize_page_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = urlsplit(value).path[:512]
        if not path.startswith("/"):
            return "/"
        segments = []
        for segment in path.split("/"):
            if (
                re.fullmatch(r"\d{6,}", segment)
                or re.fullmatch(r"[0-9a-fA-F-]{32,36}", segment)
                or (len(segment) >= 24 and re.fullmatch(r"[A-Za-z0-9_-]+", segment))
            ):
                segments.append(":id")
            else:
                segments.append(segment)
        return "/".join(segments)

    @field_validator("properties", mode="before")
    @classmethod
    def filter_properties(cls, value: Any) -> dict[str, Any]:
        return sanitize_properties(value if isinstance(value, dict) else {})

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if normalized < now - timedelta(days=7) or normalized > now + timedelta(minutes=5):
            raise ValueError("occurred_at is outside the accepted clock window")
        return normalized

    @model_validator(mode="after")
    def forbid_client_task_outcomes(self):
        if self.event_name in {
            AnalyticsEventName.TASK_STARTED,
            AnalyticsEventName.TASK_SUCCEEDED,
            AnalyticsEventName.TASK_FAILED,
            AnalyticsEventName.TASK_CANCELLED,
        }:
            raise ValueError("task lifecycle events are server-authoritative")
        return self


class AnalyticsBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[AnalyticsEventIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_one_visitor(self):
        if len({event.anonymous_id for event in self.events}) != 1:
            raise ValueError("one batch must belong to one anonymous visitor")
        return self


class AnalyticsIngestResult(BaseModel):
    accepted: int
    duplicates: int
