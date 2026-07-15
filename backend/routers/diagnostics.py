"""Diagnostic and remediation workflow projections and user controls."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from dependencies import get_course_or_404
from diagnostic_service import invalidate_stale_workflows, workflow_view
from diagnostic_workflows import (
    WorkflowConflict,
    diagnostic_workflow_repository,
)
from learner_context import require_user_id
from learning_progress import project_learning_objective_bindings


router = APIRouter(prefix="/courses/{course_id}/diagnostics", tags=["diagnostics"])


class WorkflowAction(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)


@router.get("/active")
async def get_active_workflow(course_id: str, request: Request, node_id: str | None = None):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    await run_in_threadpool(invalidate_stale_workflows, course, user_id=user_id)
    return {
        "schema_version": "diagnostic_remediation_api_v1",
        "course_id": course_id,
        "course_version_id": course.get("current_course_version_id"),
        **workflow_view(user_id, course_id, node_id=node_id),
    }


@router.get("/history")
async def get_workflow_history(course_id: str, request: Request):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    await run_in_threadpool(invalidate_stale_workflows, course, user_id=user_id)
    data = await run_in_threadpool(diagnostic_workflow_repository.load, user_id, course_id)
    return {
        "schema_version": "diagnostic_remediation_api_v1",
        "course_id": course_id,
        "cases": list(reversed(data.get("cases") or [])),
        "sessions": list(reversed(data.get("sessions") or [])),
    }


@router.post("/cases/{case_id}/disagree")
async def disagree_with_case(
    course_id: str,
    case_id: str,
    payload: WorkflowAction,
    request: Request,
):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        case = await run_in_threadpool(
            diagnostic_workflow_repository.update_case,
            user_id, course_id, case_id,
            expected_revision=payload.expected_revision,
            mutate=lambda current: current.update({
                "status": "disputed",
                "current_task_revision_id": None,
                "learner_disagreement": payload.reason,
            }),
        )
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "workflow_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Diagnostic case not found") from exc
    return {"status": "disputed", "case": case}


@router.post("/sessions/{session_id}/abandon")
async def abandon_session(
    course_id: str,
    session_id: str,
    payload: WorkflowAction,
    request: Request,
):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        session = await run_in_threadpool(
            diagnostic_workflow_repository.update_session,
            user_id, course_id, session_id,
            expected_revision=payload.expected_revision,
            mutate=lambda current: current.update({
                "status": "abandoned",
                "current_task_revision_id": None,
                "abandon_reason": payload.reason,
            }),
        )
        case = diagnostic_workflow_repository.get_case(
            user_id, course_id, str(session.get("diagnostic_case_id") or ""),
        )
        case = await run_in_threadpool(
            diagnostic_workflow_repository.update_case,
            user_id, course_id, str(case.get("diagnostic_case_id") or ""),
            expected_revision=int(case.get("revision") or 0),
            mutate=lambda current: current.update({"status": "unresolved", "current_task_revision_id": None}),
        )
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "workflow_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Remediation session not found") from exc
    return {"status": "abandoned", "session": session, "case": case}


__all__ = ["router"]
