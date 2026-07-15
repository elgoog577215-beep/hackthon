"""Multi-scope change proposal review endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from change_proposals import (
    ChangeProposalConflict,
    ChangeProposalNotFound,
    ChangeProposalRepository,
    apply_item,
    change_proposal_repository,
    reject_item,
    regenerate_item,
)
from course_commands import CourseCommandService
from course_knowledge_map import propose_kb_linkage_from_block_change
from course_repository import CourseDocumentConflict, CourseDocumentNotFound
from dependencies import get_course_document_repository
from learner_context import require_user_id


router = APIRouter(
    prefix="/courses/{course_id}/change_proposals",
    tags=["change-proposals"],
)


class RejectChangeProposalItemRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=3000)


class RegenerateChangeProposalItemRequest(BaseModel):
    extra_instruction: str | None = Field(default=None, max_length=3000)


def get_change_proposal_repository() -> ChangeProposalRepository:
    return change_proposal_repository


@router.get("")
async def list_change_proposals(course_id: str):
    repository = get_change_proposal_repository()
    return repository.list_for_course(course_id, status="pending")


@router.post("/{proposal_id}/items/{item_id}/apply")
async def apply_change_proposal_item(
    course_id: str,
    proposal_id: str,
    item_id: str,
    request: Request,
):
    repository = get_change_proposal_repository()
    course_repository = get_course_document_repository()
    command_service = CourseCommandService(course_repository)
    try:
        document, canonical = course_repository.load_document(course_id)
        if not canonical:
            raise HTTPException(status_code=409, detail="Course must be migrated before applying changes")
        proposal = repository.load(proposal_id)
        block_id = None
        for item in proposal.get("items") or []:
            if item.get("item_id") == item_id:
                block_id = item.get("block_id")
                break
        if block_id is None:
            raise ChangeProposalNotFound(item_id)
        target = next((b for b in document.blocks if b.block_id == block_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Course block not found")
        result = await apply_item(
            repository,
            command_service,
            proposal_id,
            item_id,
            expected_document_revision=document.document_revision,
            expected_block_revision=target.internal_revision,
            actor=require_user_id(request.headers.get("X-User-Id")),
        )
        # Content -> knowledge-base linkage trigger point: a block's content just
        # became canonical via this change-proposal item. Best-effort and
        # non-fatal, same reasoning as in routers/block_regeneration.py.
        try:
            course_view = course_repository.load_course_view(course_id)
            propose_kb_linkage_from_block_change(
                course_view,
                str(block_id),
                repository=repository,
                request_id=f"kb-link-change-proposal-{proposal_id}-{item_id}",
            )
        except Exception:
            pass
        return result
    except (ChangeProposalNotFound, CourseDocumentNotFound) as exc:
        raise HTTPException(status_code=404, detail="Change proposal or item not found") from exc
    except (ChangeProposalConflict, CourseDocumentConflict) as exc:
        detail: dict[str, Any] = {"code": "change_proposal_conflict", "message": str(exc)}
        if isinstance(exc, ChangeProposalConflict):
            detail["proposal"] = exc.proposal
        raise HTTPException(status_code=409, detail=detail) from exc


@router.post("/{proposal_id}/items/{item_id}/reject")
async def reject_change_proposal_item(
    course_id: str,
    proposal_id: str,
    item_id: str,
    body: RejectChangeProposalItemRequest | None = None,
):
    repository = get_change_proposal_repository()
    reason = body.reason if body else None
    try:
        return reject_item(repository, proposal_id, item_id, reason=reason)
    except ChangeProposalNotFound as exc:
        raise HTTPException(status_code=404, detail="Change proposal or item not found") from exc
    except ChangeProposalConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "change_proposal_conflict", "message": str(exc), "proposal": exc.proposal},
        ) from exc


@router.post("/{proposal_id}/items/{item_id}/regenerate")
async def regenerate_change_proposal_item(
    course_id: str,
    proposal_id: str,
    item_id: str,
    body: RegenerateChangeProposalItemRequest | None = None,
):
    repository = get_change_proposal_repository()
    extra_instruction = body.extra_instruction if body else None
    try:
        return regenerate_item(repository, proposal_id, item_id, extra_instruction=extra_instruction)
    except ChangeProposalNotFound as exc:
        raise HTTPException(status_code=404, detail="Change proposal or item not found") from exc
    except ChangeProposalConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "change_proposal_conflict", "message": str(exc), "proposal": exc.proposal},
        ) from exc
