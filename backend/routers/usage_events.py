"""Product usage ingestion, governance, and aggregate analytics API."""

from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from learner_context import require_user_id
from product_usage import (
    append_usage_events,
    delete_usage_events,
    export_usage_events,
    load_usage_events,
    summarize_usage_events,
)

router = APIRouter(prefix="/usage-events", tags=["usage_events"])


class UsageEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_event_id: str = Field(..., min_length=1, max_length=160)
    event_name: str = Field(..., min_length=1, max_length=80)
    session_id: str = Field(..., min_length=1, max_length=160)
    surface: str = Field(default="unknown", max_length=40)
    route_name: str | None = Field(default=None, max_length=160)
    course_id: str | None = Field(default=None, max_length=160)
    properties: dict[str, Any] = Field(default_factory=dict)
    client_occurred_at: str | None = Field(default=None, max_length=64)


class UsageBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[UsageEventInput] = Field(..., min_length=1, max_length=50)


class UsageDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["delete_my_usage_events"]


@router.post("/batch")
async def ingest_usage_events(payload: UsageBatchInput, request: Request) -> dict[str, Any]:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        return await run_in_threadpool(
            append_usage_events,
            user_id=user_id,
            events=[item.model_dump() for item in payload.events],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary")
async def summarize_own_usage(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(
        summarize_usage_events,
        user_id=user_id,
        days=days,
    )


@router.get("/export")
async def export_own_usage(request: Request) -> dict[str, Any]:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(export_usage_events, user_id=user_id)


@router.post("/delete")
async def delete_own_usage(
    payload: UsageDeleteInput,
    request: Request,
) -> dict[str, Any]:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(delete_usage_events, user_id=user_id)


@router.get("/admin/summary")
async def summarize_global_usage(
    days: int = Query(default=30, ge=1, le=365),
    admin_token: str | None = Header(default=None, alias="X-Analytics-Admin-Token"),
) -> dict[str, Any]:
    configured = os.getenv("LINGZHI_ANALYTICS_ADMIN_TOKEN", "").strip()
    if not configured:
        raise HTTPException(status_code=404, detail="Usage analytics admin endpoint is disabled")
    if not admin_token or not secrets.compare_digest(configured, admin_token):
        raise HTTPException(status_code=403, detail="Invalid analytics admin token")
    events = await run_in_threadpool(load_usage_events)
    return await run_in_threadpool(summarize_usage_events, events=events, days=days)


__all__ = ["router"]
