"""Knowledge-library rebuild, review, migration, and knowledge-command APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from course_knowledge_commands import (
    KNOWLEDGE_COMMANDS,
    CourseKnowledgeCommandService,
    KnowledgeCommandRejected,
    build_knowledge_candidate,
)
from course_knowledge_impact import knowledge_coverage_check
from course_knowledge_point_edits import (
    POINT_EDIT_OPERATIONS,
    build_point_edit_candidate,
)
from course_knowledge_rebuild import (
    CourseKnowledgeRebuildError,
    CourseKnowledgeRebuildService,
)
from course_knowledge_relocation import relocate_point_edit_candidate
from course_repository import (
    CourseDocumentConflict,
    CourseDocumentNotFound,
    CourseDocumentRepository,
)
from dependencies import get_course_document_repository
from learner_context import resolve_user_id

router = APIRouter(tags=["knowledge_libraries"])
logger = logging.getLogger(__name__)

# Rejections that mean "someone else moved first", not "your request is wrong".
# The teacher's correct response is to refresh and recompute, so these must not
# be reported as 400 — the client cannot fix them by editing the payload.
_CONFLICT_CODES = {
    "knowledge_base_revision_changed",
    "course_document_revision_changed",
    "course_revision_conflict",
}


class RebuildRequest(BaseModel):
    force: bool = False


class ReviewRequest(BaseModel):
    revision_id: str
    decision: Literal["accept", "reject"]
    note: str = ""


class KnowledgeCandidateRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    proposed_knowledge_base: dict[str, Any]
    identity_map: dict[str, Any] = Field(default_factory=dict)


class KnowledgeConfirmRequest(BaseModel):
    command_id: str = Field(min_length=1, max_length=200)
    candidate: dict[str, Any]
    proposed_knowledge_base: dict[str, Any]


class KnowledgeCoverageRequest(BaseModel):
    changed_block_ids: list[str] = Field(min_length=1, max_length=200)


class PointEditRequest(BaseModel):
    """A targeted edit to one knowledge point, described rather than uploaded."""

    knowledge_id: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)


class PointEditConfirmRequest(PointEditRequest):
    command_id: str = Field(min_length=1, max_length=200)


class PointEditRelocateRequest(PointEditRequest):
    """A pending candidate asking to be re-anchored onto the current base."""

    base_knowledge_revision_id: str = Field(min_length=1, max_length=200)


def get_course_knowledge_rebuild_service(
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> CourseKnowledgeRebuildService:
    return CourseKnowledgeRebuildService(course_repository)


def get_course_knowledge_command_service(
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> CourseKnowledgeCommandService:
    return CourseKnowledgeCommandService(course_repository)


def _actor(request: Request) -> str:
    return resolve_user_id(request.headers.get("X-User-Id"))


def _command_error(exc: KnowledgeCommandRejected) -> HTTPException:
    status_code = 409 if exc.code in _CONFLICT_CODES else 400
    detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.detail is not None:
        detail["detail"] = exc.detail
    return HTTPException(status_code=status_code, detail=detail)


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


@router.post("/courses/{course_id}/knowledge-library/candidates")
async def preview_knowledge_candidate(
    course_id: str,
    body: KnowledgeCandidateRequest,
    request: Request,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> dict:
    """Validate a proposed knowledge change and return it as a candidate.

    Read-only on purpose: the teacher sees the quality report, the identity
    check and the full downstream impact *before* deciding. The active
    knowledge base is not touched until `/confirm`.
    """
    try:
        course = course_repository.load_course_view(course_id)
        candidate = build_knowledge_candidate(
            course,
            operation=body.operation,
            proposed_knowledge_base=body.proposed_knowledge_base,
            reason=body.reason,
            identity_map=body.identity_map,
            actor=_actor(request),
        )
    except KnowledgeCommandRejected as exc:
        raise _command_error(exc) from exc
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "candidate": candidate}


@router.post("/courses/{course_id}/knowledge-library/candidates/confirm")
async def confirm_knowledge_candidate(
    course_id: str,
    body: KnowledgeConfirmRequest,
    request: Request,
    service: CourseKnowledgeCommandService = Depends(get_course_knowledge_command_service),
) -> dict:
    """Apply a confirmed candidate atomically with the course revision.

    `command_id` is the idempotency key: replaying it returns the original
    receipt instead of applying twice, so a retry after a lost response is safe.
    """
    try:
        receipt = await service.confirm_knowledge_candidate(
            course_id,
            command_id=body.command_id,
            candidate=body.candidate,
            proposed_knowledge_base=body.proposed_knowledge_base,
            actor=_actor(request),
        )
    except KnowledgeCommandRejected as exc:
        raise _command_error(exc) from exc
    except CourseDocumentConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_document_conflict", "message": str(exc),
        }) from exc
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "receipt": receipt}


@router.get("/courses/{course_id}/knowledge-library/revisions")
async def list_knowledge_revisions(
    course_id: str,
    service: CourseKnowledgeCommandService = Depends(get_course_knowledge_command_service),
) -> dict:
    """Confirmed knowledge revisions for this course, oldest first."""
    try:
        entries = service.knowledge_revision_log(course_id)
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "success",
        "course_id": course_id,
        "whitelisted_operations": sorted(KNOWLEDGE_COMMANDS),
        "revisions": entries,
    }


@router.post("/courses/{course_id}/knowledge-library/coverage-check")
async def check_knowledge_coverage(
    course_id: str,
    body: KnowledgeCoverageRequest,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> dict:
    """Reverse direction: do changed body blocks still have knowledge coverage?

    Reports gaps so a knowledge maintenance candidate can be raised. It never
    writes knowledge — that path stays behind the whitelist commands.
    """
    try:
        course = course_repository.load_course_view(course_id)
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "success",
        "coverage": knowledge_coverage_check(
            course, changed_block_ids=body.changed_block_ids,
        ),
    }


@router.post("/courses/{course_id}/knowledge-library/points/preview-edit")
async def preview_point_edit(
    course_id: str,
    body: PointEditRequest,
    request: Request,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> dict:
    """Preview a targeted single-point edit without writing anything.

    The client describes the edit instead of uploading a knowledge base: real
    course envelopes are megabytes, and a description cannot smuggle changes to
    stable IDs, relations or bindings the way a full payload could.
    """
    try:
        course = course_repository.load_course_view(course_id)
        candidate, _ = build_point_edit_candidate(
            course,
            knowledge_id=body.knowledge_id,
            operation=body.operation,
            value=body.value,
            reason=body.reason,
            actor=_actor(request),
        )
    except KnowledgeCommandRejected as exc:
        raise _command_error(exc) from exc
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "success",
        "candidate": candidate,
        "supported_operations": sorted(POINT_EDIT_OPERATIONS),
    }


@router.post("/courses/{course_id}/knowledge-library/points/confirm-edit")
async def confirm_point_edit(
    course_id: str,
    body: PointEditConfirmRequest,
    request: Request,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
    service: CourseKnowledgeCommandService = Depends(get_course_knowledge_command_service),
) -> dict:
    """Recompute the edit against the current base, then commit it atomically.

    The candidate is rebuilt here rather than accepted from the request. A
    client-supplied candidate would be a second, unverified source of truth for
    what is about to be written; recomputing means the quality gate, identity
    check and impact analysis all run against the base actually on disk. If the
    knowledge base moved since the teacher previewed, the recomputed candidate
    carries the new base revision and the command service rejects it as stale.
    """
    try:
        # Idempotency is resolved before recomputing. A replay of an applied
        # command would otherwise rebuild the proposal against a base that
        # already contains the edit and be rejected as a no-op — turning a safe
        # retry into a spurious 400.
        replayed = course_repository.receipt_for_command(course_id, body.command_id)
        if replayed:
            return {"status": "success", "receipt": replayed, "candidate": None}

        course = course_repository.load_course_view(course_id)
        candidate, proposed = build_point_edit_candidate(
            course,
            knowledge_id=body.knowledge_id,
            operation=body.operation,
            value=body.value,
            reason=body.reason,
            actor=_actor(request),
        )
        receipt = await service.confirm_knowledge_candidate(
            course_id,
            command_id=body.command_id,
            candidate=candidate,
            proposed_knowledge_base=proposed,
            actor=_actor(request),
        )
    except KnowledgeCommandRejected as exc:
        raise _command_error(exc) from exc
    except CourseDocumentConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_document_conflict", "message": str(exc),
        }) from exc
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "receipt": receipt, "candidate": candidate}


@router.post("/courses/{course_id}/knowledge-library/points/relocate-edit")
async def relocate_point_edit(
    course_id: str,
    body: PointEditRelocateRequest,
    request: Request,
    course_repository: CourseDocumentRepository = Depends(get_course_document_repository),
) -> dict:
    """Re-anchor a pending candidate whose base revision moved.

    Returns 200 for every outcome, including `conflict`. A conflict here is a
    normal review state the teacher must read and act on — not a failed
    request — and folding it into 409 would make the client discard the
    explanation of *why* it could not be relocated.
    """
    try:
        course = course_repository.load_course_view(course_id)
        result = relocate_point_edit_candidate(
            course,
            knowledge_id=body.knowledge_id,
            operation=body.operation,
            value=body.value,
            reason=body.reason,
            base_knowledge_revision_id=body.base_knowledge_revision_id,
            actor=_actor(request),
        )
    except KnowledgeCommandRejected as exc:
        raise _command_error(exc) from exc
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "relocation": result}
