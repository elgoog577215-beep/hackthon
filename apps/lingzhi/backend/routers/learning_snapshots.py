"""Current learning snapshot API with semantic anchor resolution."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from content_blocks import resolve_content_anchor
from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_snapshots import SnapshotConflict, learning_snapshot_repository

router = APIRouter(prefix="/courses/{course_id}/learning-snapshot", tags=["learning_snapshots"])


class ContentAnchorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(default="", max_length=240)
    block_revision_id: str = Field(default="", max_length=120)
    content_fingerprint: str = Field(default="", max_length=120)
    block_type: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=500)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    text_quote: str = Field(default="", max_length=1000)


class SessionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=160)
    device_id: str = Field(..., min_length=1, max_length=160)
    started_at: str = Field(default="", max_length=80)


class TaskStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="reading", max_length=80)
    object_id: str = Field(default="", max_length=240)
    task_revision_id: str = Field(default="", max_length=240)
    status: str = Field(default="active", max_length=40)
    context: dict[str, Any] = Field(default_factory=dict)
    return_node_id: str = Field(default="", max_length=240)
    draft_revision: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(default="", max_length=240)
    issue_id: str = Field(default="", max_length=240)
    remediation_session_id: str = Field(default="", max_length=240)


class SnapshotUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(default=0, ge=0)
    course_version_id: str = Field(default="", max_length=160)
    node_id: str = Field(..., min_length=1, max_length=240)
    node_name: str = Field(default="", max_length=500)
    content_anchor: ContentAnchorPayload | None = None
    session: SessionPayload
    task_state: TaskStatePayload = Field(default_factory=TaskStatePayload)
    interaction_state: InteractionStatePayload = Field(default_factory=InteractionStatePayload)
    fallback_scroll_top: int = Field(default=0, ge=0, le=100_000_000)
    activity_at: str = Field(..., min_length=1, max_length=80)
    source: Literal["live", "legacy_migration", "offline_recovery"] = "live"


@router.get("")
async def get_learning_snapshot(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    snapshot = learning_snapshot_repository.load(user_id, course_id)
    return _response(course, snapshot)


@router.put("")
async def put_learning_snapshot(course_id: str, payload: SnapshotUpdate, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    data = payload.model_dump(exclude={"expected_revision"})
    data["course_version_id"] = data.get("course_version_id") or course.get("current_course_version_id") or ""
    data["task_state"]["context"] = _bounded_metadata(data["task_state"].get("context") or {})
    data["task_state"]["metadata"] = _bounded_metadata(data["task_state"].get("metadata") or {})
    try:
        snapshot = learning_snapshot_repository.save(
            user_id,
            course_id,
            expected_revision=payload.expected_revision,
            payload=data,
        )
    except SnapshotConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"code": "snapshot_revision_conflict", "current_snapshot": conflict.current},
        ) from conflict
    return _response(course, snapshot)


@router.delete("")
async def delete_learning_snapshot(course_id: str, request: Request):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    deleted = learning_snapshot_repository.delete(user_id, course_id)
    return {"status": "deleted" if deleted else "not_found"}


def _response(course: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    resolution = None
    if snapshot:
        resolution = resolve_content_anchor(
            course,
            node_id=snapshot.get("node_id"),
            anchor=snapshot.get("content_anchor"),
        )
    return {
        "schema_version": "learning_snapshot_api_v1",
        "course_id": course.get("course_id"),
        "current_course_version_id": course.get("current_course_version_id"),
        "snapshot": snapshot,
        "resolution": resolution,
    }


def _bounded_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in list(metadata.items())[:20]:
        if isinstance(value, str):
            result[str(key)[:80]] = value[:1000]
        elif isinstance(value, (int, float, bool)) or value is None:
            result[str(key)[:80]] = value
    return result


__all__ = ["router"]
