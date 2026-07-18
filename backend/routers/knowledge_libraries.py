"""Knowledge-library rebuild, review, and migration APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from course_knowledge_rebuild import (
    CourseKnowledgeRebuildError,
    CourseKnowledgeRebuildService,
)
from course_repository import (
    CourseDocumentConflict,
    CourseDocumentRepository,
)
from dependencies import get_course_document_repository

router = APIRouter(tags=["knowledge_libraries"])
logger = logging.getLogger(__name__)


class RebuildRequest(BaseModel):
    force: bool = False


class ReviewRequest(BaseModel):
    revision_id: str
    decision: Literal["accept", "reject"]
    note: str = ""


def get_course_knowledge_rebuild_service(
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> CourseKnowledgeRebuildService:
    return CourseKnowledgeRebuildService(course_repository)


@router.post("/courses/{course_id}/knowledge-library/rebuild")
async def rebuild_course_library(
    course_id: str,
    body: RebuildRequest,
    service: CourseKnowledgeRebuildService = Depends(get_course_knowledge_rebuild_service),
) -> dict:
    try:
        return await service.rebuild_course(course_id, force=body.force)
    except CourseKnowledgeRebuildError as exc:
        logger.warning(
            "Course knowledge rebuild failed for %s: %s (%s)",
            course_id,
            exc.code,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.public_detail()) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/courses/{course_id}/knowledge-library/review")
async def get_course_library_review(
    course_id: str,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    try:
        course = course_repository.load_course_view(course_id)
        knowledge_base = course.get("course_knowledge_base") or {}
        return {
            "course_id": course_id,
            "knowledge_scope": "current_course_only",
            "revision_id": knowledge_base.get("revision_id"),
            "lifecycle_status": knowledge_base.get("lifecycle_status", "degraded"),
            "quality_report": knowledge_base.get("quality_report") or {},
            "governance": course.get("course_knowledge_governance") or {},
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/courses/{course_id}/knowledge-library/review")
async def review_course_library(
    course_id: str,
    body: ReviewRequest,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    try:
        course = course_repository.load_course_view(course_id)
        knowledge_base = course.get("course_knowledge_base") or {}
        current_revision = str(knowledge_base.get("revision_id") or "")
        if not current_revision or current_revision != body.revision_id:
            raise HTTPException(status_code=409, detail="课程知识库版本已变化，请刷新后重试")
        governance = {
            "schema_version": "course_knowledge_governance_v1",
            "knowledge_scope": "current_course_only",
            "revision_id": current_revision,
            "decision": body.decision,
            "note": body.note.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        await course_repository.update_metadata(
            course_id,
            {"course_knowledge_governance": governance},
        )
        return {
            "course_id": course_id,
            "revision_id": current_revision,
            "decision": body.decision,
            "governance": governance,
        }
    except CourseDocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
