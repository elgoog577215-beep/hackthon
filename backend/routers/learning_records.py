"""Unified note, issue, review-task and bookmark API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_events import record_learning_event
from learning_records import (
    InvalidRecordTransition,
    RecordConflict,
    enrich_record_payload,
    learning_record_repository,
    project_record,
)
from storage import storage


router = APIRouter(prefix="/courses/{course_id}/learning-records", tags=["learning_records"])


class RecordCreate(BaseModel):
    record_id: str | None = Field(default=None, max_length=120)
    record_type: Literal["note", "issue", "review_task", "bookmark"]
    status: str | None = Field(default=None, max_length=40)
    node_id: str = Field(min_length=1, max_length=160)
    node_name: str = Field(default="", max_length=300)
    quote: str = Field(default="", max_length=12000)
    title: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=20000)
    origin: str = Field(default="user", max_length=80)
    priority: Literal["low", "medium", "high"] = "medium"
    tags: list[str] = Field(default_factory=list, max_length=50)
    category: str = Field(default="", max_length=120)
    due_at: str | None = None
    anchor: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecordUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, max_length=20000)
    quote: str | None = Field(default=None, max_length=12000)
    priority: Literal["low", "medium", "high"] | None = None
    tags: list[str] | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=120)
    due_at: str | None = None
    status: str | None = Field(default=None, max_length=40)
    anchor: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class RecordArchive(BaseModel):
    expected_revision: int = Field(ge=1)


class LegacyAnnotationMigrationRequest(BaseModel):
    include_unowned: bool = False


@router.get("")
async def list_learning_records(
    course_id: str,
    request: Request,
    record_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    records = await run_in_threadpool(learning_record_repository.list, user_id, course_id)
    projected = [project_record(item, course) for item in records]
    if record_type:
        projected = [item for item in projected if item.get("record_type") == record_type]
    if status:
        projected = [item for item in projected if item.get("status") == status]
    if node_id:
        projected = [item for item in projected if item.get("node_id") == node_id]
    return {"course_id": course_id, "user_id": user_id, "records": projected}


@router.post("")
async def create_learning_record(course_id: str, payload: RecordCreate, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    enriched = enrich_record_payload(course, payload.model_dump(exclude_none=True))
    try:
        record, created = await run_in_threadpool(learning_record_repository.create_once, user_id, course_id, enriched)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        _record_event("learning_record_created", record, user_id=user_id)
    return project_record(record, course)


@router.patch("/{record_id}")
async def update_learning_record(
    course_id: str,
    record_id: str,
    payload: RecordUpdate,
    request: Request,
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    changes = payload.model_dump(exclude_none=True)
    expected_revision = int(changes.pop("expected_revision"))
    try:
        record, change_kind = await run_in_threadpool(
            learning_record_repository.update,
            user_id,
            course_id,
            record_id,
            expected_revision=expected_revision,
            changes=changes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Learning record not found") from exc
    except RecordConflict as exc:
        raise HTTPException(status_code=409, detail={"message": "revision conflict", "current": exc.current}) from exc
    except InvalidRecordTransition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    event_type = "learning_record_status_changed" if change_kind == "status_changed" else "learning_record_updated"
    _record_event(event_type, record, user_id=user_id)
    return project_record(record, course)


@router.post("/{record_id}/archive")
async def archive_learning_record(
    course_id: str,
    record_id: str,
    payload: RecordArchive,
    request: Request,
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        record, _ = await run_in_threadpool(
            learning_record_repository.update,
            user_id,
            course_id,
            record_id,
            expected_revision=payload.expected_revision,
            changes={"status": "archived"},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Learning record not found") from exc
    except RecordConflict as exc:
        raise HTTPException(status_code=409, detail={"message": "revision conflict", "current": exc.current}) from exc
    except InvalidRecordTransition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _record_event("learning_record_archived", record, user_id=user_id)
    return project_record(record, course)


@router.post("/migrate-legacy-annotations")
async def migrate_legacy_annotations(
    course_id: str,
    request: Request,
    payload: LegacyAnnotationMigrationRequest | None = None,
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    include_unowned = bool(payload and payload.include_unowned)
    node_ids = {str(node.get("node_id") or "") for node in course.get("nodes") or []}
    annotations = await run_in_threadpool(storage.load_annotations)
    existing = await run_in_threadpool(learning_record_repository.list, user_id, course_id)
    migrated_ids = {
        str((item.get("metadata") or {}).get("legacy_annotation_id") or "")
        for item in existing
    }
    created = 0
    for annotation in annotations:
        annotation_id = str(annotation.get("anno_id") or "")
        annotation_course = str(annotation.get("course_id") or "")
        node_id = str(annotation.get("node_id") or "")
        if not annotation_id or annotation_id in migrated_ids:
            continue
        if annotation_course and annotation_course != course_id:
            continue
        if not annotation_course and node_id not in node_ids:
            continue
        annotation_owner = str(
            annotation.get("user_id")
            or annotation.get("owner_id")
            or annotation.get("created_by")
            or ""
        )
        if annotation_owner and annotation_owner != user_id:
            continue
        if not annotation_owner and not include_unowned:
            continue
        source_type = str(annotation.get("source_type") or "user")
        if source_type == "format":
            continue
        record_type = "review_task" if source_type == "wrong" else "note"
        origin = {
            "wrong": "legacy_wrong_annotation",
            "ai": "legacy_ai_annotation",
        }.get(source_type, "legacy_annotation")
        payload = enrich_record_payload(course, {
            "record_type": record_type,
            "status": "pending" if record_type == "review_task" else "active",
            "node_id": node_id,
            "quote": str(annotation.get("quote") or ""),
            "title": str(annotation.get("anno_summary") or ""),
            "content": str(annotation.get("answer") or annotation.get("question") or ""),
            "origin": origin,
            "priority": "medium",
            "metadata": {
                "legacy_annotation_id": annotation_id,
                "legacy_source_type": source_type,
                "legacy_owner_id": annotation_owner,
                "claimed_unowned": not annotation_owner,
                "confidence": "low" if source_type in {"wrong", "ai"} else "medium",
                "user_confirmation_unknown": source_type == "ai",
            },
        })
        record, was_created = await run_in_threadpool(learning_record_repository.create_once, user_id, course_id, payload)
        if not was_created:
            continue
        _record_event("legacy_learning_record_imported", record, user_id=user_id)
        migrated_ids.add(annotation_id)
        created += 1
    records = await run_in_threadpool(learning_record_repository.list, user_id, course_id)
    return {
        "status": "migrated",
        "created": created,
        "records": [project_record(item, course) for item in records],
    }


def _record_event(event_type: str, record: dict[str, Any], *, user_id: str) -> None:
    record_learning_event(
        event_type=event_type,
        actor="migration" if event_type == "legacy_learning_record_imported" else "user",
        source=f"learning_records.{record.get('origin') or 'user'}",
        user_id=user_id,
        course_id=record.get("course_id"),
        course_version_id=record.get("course_version_id"),
        node_id=record.get("node_id"),
        node_name=record.get("node_name", ""),
        objective_id=record.get("objective_id"),
        objective_revision_id=record.get("objective_revision_id"),
        record_id=record.get("record_id"),
        record_type=record.get("record_type"),
        operation_id=f"record:{record.get('record_id')}:{record.get('revision')}",
        idempotency_key=f"{event_type}:{record.get('record_id')}:{record.get('revision')}",
        entity_type="learning_record",
        entity_id=record.get("record_id"),
        entity_revision=record.get("revision"),
        evidence={
            "quote": record.get("quote", ""),
            "anchor": record.get("anchor") or {},
            "origin": record.get("origin"),
        },
        result={
            "status": record.get("status"),
            "revision": record.get("revision"),
        },
        metadata=record.get("metadata") or {},
    )


__all__ = ["router"]
