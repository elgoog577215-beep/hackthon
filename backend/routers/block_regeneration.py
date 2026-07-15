"""Canonical course-block regeneration candidates."""

from __future__ import annotations

from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from block_regeneration import (
    BlockRegenerationConflict,
    BlockRegenerationNotFound,
    BlockRegenerationService,
    block_regeneration_candidate_repository,
)
from change_proposals import change_proposal_repository
from course_knowledge_map import propose_kb_linkage_from_block_change
from dependencies import get_course_document_repository
from learner_context import require_user_id
from course_repository import CourseDocumentNotFound


router = APIRouter(
    prefix="/courses/{course_id}/blocks/{block_id}/regeneration-candidates",
    tags=["block-regeneration"],
)


class CreateBlockRegenerationCandidateRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=160)
    expected_document_revision: str = Field(..., min_length=1, max_length=160)
    expected_block_revision: str = Field(..., min_length=1, max_length=160)
    instruction: str = Field(default="", max_length=3000)
    action_type: Literal["rewrite", "simplify", "example", "expand"] = "rewrite"


def get_block_regeneration_service() -> BlockRegenerationService:
    return BlockRegenerationService(
        get_course_document_repository(),
        block_regeneration_candidate_repository,
    )


@router.post("")
async def create_block_regeneration_candidate(
    course_id: str,
    block_id: str,
    body: CreateBlockRegenerationCandidateRequest,
    request: Request,
):
    service = get_block_regeneration_service()
    try:
        return await service.create_candidate(
            course_id,
            block_id,
            request_id=body.request_id,
            expected_document_revision=body.expected_document_revision,
            expected_block_revision=body.expected_block_revision,
            instruction=body.instruction,
            action_type=body.action_type,
            user_id=require_user_id(request.headers.get("X-User-Id")),
        )
    except CourseDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Course not found") from exc
    except BlockRegenerationNotFound as exc:
        raise HTTPException(status_code=404, detail="Course block not found") from exc
    except BlockRegenerationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "block_regeneration_conflict", "message": str(exc), "candidate": exc.candidate},
        ) from exc


@router.get("/latest")
async def get_latest_block_regeneration_candidate(
    course_id: str,
    block_id: str,
    expected_document_revision: str | None = None,
    expected_block_revision: str | None = None,
):
    try:
        return get_block_regeneration_service().get_latest_candidate(
            course_id,
            block_id,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
        )
    except BlockRegenerationNotFound as exc:
        raise HTTPException(status_code=404, detail="Block regeneration candidate not found") from exc


@router.get("/{candidate_id}")
async def get_block_regeneration_candidate(course_id: str, block_id: str, candidate_id: str):
    try:
        return get_block_regeneration_service().get_candidate(course_id, block_id, candidate_id)
    except BlockRegenerationNotFound as exc:
        raise HTTPException(status_code=404, detail="Block regeneration candidate not found") from exc


@router.post("/{candidate_id}/retry")
async def retry_block_regeneration_candidate(
    course_id: str,
    block_id: str,
    candidate_id: str,
    request: Request,
):
    try:
        return await get_block_regeneration_service().retry_candidate(
            course_id,
            block_id,
            candidate_id,
            user_id=require_user_id(request.headers.get("X-User-Id")),
        )
    except (BlockRegenerationNotFound, CourseDocumentNotFound) as exc:
        raise HTTPException(status_code=404, detail="Block regeneration candidate not found") from exc
    except BlockRegenerationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "block_regeneration_conflict", "message": str(exc), "candidate": exc.candidate},
        ) from exc


@router.post("/{candidate_id}/apply")
async def apply_block_regeneration_candidate(
    course_id: str,
    block_id: str,
    candidate_id: str,
    request: Request,
):
    try:
        result = await get_block_regeneration_service().apply_candidate(
            course_id,
            block_id,
            candidate_id,
            actor=require_user_id(request.headers.get("X-User-Id")),
        )
        # Content -> knowledge-base linkage trigger point: a block's content just
        # became canonical. Best-effort and non-fatal - never let a linkage
        # proposal failure block the (already-durable) content change response.
        try:
            course_view = get_course_document_repository().load_course_view(course_id)
            propose_kb_linkage_from_block_change(
                course_view,
                block_id,
                repository=change_proposal_repository,
                request_id=f"kb-link-block-regen-{candidate_id}",
            )
        except Exception:
            pass
        return result
    except (BlockRegenerationNotFound, CourseDocumentNotFound) as exc:
        raise HTTPException(status_code=404, detail="Block regeneration candidate not found") from exc
    except BlockRegenerationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "block_regeneration_conflict", "message": str(exc), "candidate": exc.candidate},
        ) from exc


@router.post("/{candidate_id}/reject")
async def reject_block_regeneration_candidate(course_id: str, block_id: str, candidate_id: str):
    try:
        return get_block_regeneration_service().reject_candidate(course_id, block_id, candidate_id)
    except BlockRegenerationNotFound as exc:
        raise HTTPException(status_code=404, detail="Block regeneration candidate not found") from exc
    except BlockRegenerationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "block_regeneration_conflict", "message": str(exc), "candidate": exc.candidate},
        ) from exc
