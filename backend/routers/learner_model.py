"""Read-only learner model API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from dependencies import get_course_or_404
from learner_context import require_user_id
from learner_model_service import build_current_learner_model
from learning_progress import project_learning_objective_bindings


router = APIRouter(prefix="/courses/{course_id}/learner-model", tags=["learner_model"])


@router.get("")
async def get_learner_model(course_id: str, request: Request) -> dict[str, Any]:
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    return await run_in_threadpool(_build_model, course, user_id)


def _build_model(course: dict[str, Any], user_id: str) -> dict[str, Any]:
    return build_current_learner_model(course, user_id=user_id)


__all__ = ["router"]
