"""Knowledge-library rebuild, review, and migration APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal

from course_repository import CourseDocumentRepository
from dependencies import get_course_document_repository
from knowledge_library_migrations import KnowledgeLibraryMigrationService
from subject_library_service import (
    SubjectLibraryService,
    SubjectLibraryVersionConflict,
    SubjectOntologyGenerationError,
)


router = APIRouter(tags=["knowledge_libraries"])


class RebuildRequest(BaseModel):
    force: bool = False


class ReviewRequest(BaseModel):
    revision_id: str
    decision: Literal["accept", "reject"]
    note: str = ""


def get_subject_library_service(
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> SubjectLibraryService:
    return SubjectLibraryService(course_repository)


def get_subject_library_migration_service(
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
    service: SubjectLibraryService = Depends(get_subject_library_service),
) -> KnowledgeLibraryMigrationService:
    return KnowledgeLibraryMigrationService(course_repository, service)


@router.post("/courses/{course_id}/knowledge-library/rebuild")
async def rebuild_course_library(
    course_id: str,
    body: RebuildRequest,
    service: SubjectLibraryService = Depends(get_subject_library_service),
):
    try:
        return await service.rebuild_course(course_id, force=body.force)
    except SubjectOntologyGenerationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/courses/{course_id}/knowledge-library/review")
async def get_course_library_review(
    course_id: str,
    service: SubjectLibraryService = Depends(get_subject_library_service),
):
    try:
        return service.get_review(course_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/courses/{course_id}/knowledge-library/review")
async def review_course_library(
    course_id: str,
    body: ReviewRequest,
    service: SubjectLibraryService = Depends(get_subject_library_service),
):
    try:
        return await service.review_course_library(
            course_id,
            revision_id=body.revision_id,
            decision=body.decision,
            note=body.note,
        )
    except SubjectLibraryVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge-libraries/migrations", status_code=202)
async def create_migration(
    service: KnowledgeLibraryMigrationService = Depends(get_subject_library_migration_service),
):
    return service.create_job()


@router.get("/knowledge-libraries/migrations/{job_id}")
async def get_migration(
    job_id: str,
    service: KnowledgeLibraryMigrationService = Depends(get_subject_library_migration_service),
):
    try:
        return service.load_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Migration job not found") from exc


@router.post("/knowledge-libraries/migrations/{job_id}/pause")
async def pause_migration(
    job_id: str,
    service: KnowledgeLibraryMigrationService = Depends(get_subject_library_migration_service),
):
    try:
        return service.pause_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Migration job not found") from exc


@router.post("/knowledge-libraries/migrations/{job_id}/resume")
async def resume_migration(
    job_id: str,
    service: KnowledgeLibraryMigrationService = Depends(get_subject_library_migration_service),
):
    try:
        return service.resume_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Migration job not found") from exc
