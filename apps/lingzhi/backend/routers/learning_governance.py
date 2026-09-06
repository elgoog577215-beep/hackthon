"""学习事实的导出与删除 API。

事实层治理入口。`LearnerModel` 等解释层没有对应的删除接口——它们不拥有事实，
删除事实后自然重算。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from learner_context import require_user_id
from learning_governance import delete_learning_facts, export_learning_facts
from learning_scope_corrections import (
    CORRECTABLE_FIELDS,
    ScopeCorrectionError,
    record_scope_correction,
)
from learning_source_links import build_source_links_for_learner

router = APIRouter(prefix="/learning-facts", tags=["learning_governance"])


class FactDeletionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["event", "course", "learner"]
    course_id: str | None = Field(default=None, max_length=160)
    event_id: str | None = Field(default=None, max_length=160)
    reason_code: str = Field(default="learner_requested", max_length=80)


@router.get("/export")
async def export_own_learning_facts(
    request: Request,
    course_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """导出调用者自己的学习事实。只读，不触发任何写入。"""
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(
        export_learning_facts,
        user_id=user_id,
        course_id=course_id,
    )


@router.get("/source-links")
async def list_own_source_links(
    request: Request,
    course_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
) -> dict[str, Any]:
    """解析自己学习事实的回跳坐标。

    课程修订前移时不会失败：来源变更由每条结果的 ``status`` / ``source_changed``
    表达，由调用方决定怎样提示。
    """
    user_id = require_user_id(request.headers.get("X-User-Id"))
    links = await run_in_threadpool(
        build_source_links_for_learner,
        user_id=user_id,
        course_id=course_id,
        limit=limit,
    )
    return {
        "user_id": user_id,
        "course_id": course_id,
        "source_links": links,
    }


class ScopeCorrectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, max_length=160)
    corrections: dict[str, Any] = Field(..., min_length=1)
    reason_code: str = Field(default="misattributed_scope", max_length=80)


@router.post("/scope-corrections")
async def correct_own_fact_scope(
    payload: ScopeCorrectionPayload,
    request: Request,
) -> dict[str, Any]:
    """纠正一条学习事实被记错的范围。

    追加一条纠正事实，**不改写原事实**：原始坐标与纠正痕迹都留在账本里。
    只能纠正范围坐标（课程/节点/目标/知识点），不能改内容。
    """
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        correction = await run_in_threadpool(
            record_scope_correction,
            user_id=user_id,
            event_id=payload.event_id,
            corrections=payload.corrections,
            reason_code=payload.reason_code,
        )
    except ScopeCorrectionError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "correctable_fields": sorted(CORRECTABLE_FIELDS),
            },
        ) from exc
    return correction


@router.post("/delete")
async def delete_own_learning_facts(
    payload: FactDeletionPayload,
    request: Request,
) -> dict[str, Any]:
    """删除调用者自己的学习事实，并让派生投影一致失效。

    身份来自请求头而不是请求体：学习者只能删自己的事实，删除范围不可由调用方
    指定他人。
    """
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        receipt = await run_in_threadpool(
            delete_learning_facts,
            user_id=user_id,
            scope=payload.scope,
            course_id=payload.course_id,
            event_id=payload.event_id,
            reason_code=payload.reason_code,
            requested_by="learner",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return receipt


__all__ = ["router"]
