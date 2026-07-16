"""Multi-scope change proposal review endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from block_regeneration import (
    BlockRegenerationConflict,
    BlockRegenerationNotFound,
    BlockRegenerationService,
    block_regeneration_candidate_repository,
)
from change_proposals import (
    ChangeProposalConflict,
    ChangeProposalNotFound,
    ChangeProposalRepository,
    apply_item,
    apply_kg_node_item,
    change_proposal_repository,
    reject_item,
    regenerate_item,
)
from course_commands import CourseCommandService
from course_document import stable_hash
from course_knowledge_map import propose_kb_linkage_from_block_change
from course_repository import CourseDocumentConflict, CourseDocumentNotFound
from dependencies import get_course_document_repository
from learner_context import require_user_id
from subject_library_repository import (
    SubjectLibraryRepository,
    subject_library_repository,
)


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


def get_change_proposal_regeneration_service() -> BlockRegenerationService:
    return BlockRegenerationService(
        get_course_document_repository(),
        block_regeneration_candidate_repository,
    )


def get_subject_library_repository() -> SubjectLibraryRepository:
    return subject_library_repository


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
        proposal = repository.load(proposal_id)
        block_id = None
        target_kind = "course_block"
        for item in proposal.get("items") or []:
            if item.get("item_id") == item_id:
                block_id = item.get("block_id")
                target_kind = item.get("target_kind") or "course_block"
                break
        if block_id is None:
            raise ChangeProposalNotFound(item_id)
        if target_kind != "course_block":
            return apply_kg_node_item(
                repository,
                proposal_id,
                item_id,
                actor=require_user_id(request.headers.get("X-User-Id")),
                course_data=course_repository.load_course_view(course_id),
                library_repository=get_subject_library_repository(),
            )
        document, canonical = course_repository.load_document(course_id)
        if not canonical:
            raise HTTPException(status_code=409, detail="Course must be migrated before applying changes")
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
    request: Request,
    body: RegenerateChangeProposalItemRequest | None = None,
):
    repository = get_change_proposal_repository()
    extra_instruction = body.extra_instruction if body else None
    proposal: dict[str, Any] | None = None
    try:
        proposal = repository.load(proposal_id)
        if proposal.get("course_id") != course_id:
            raise ChangeProposalNotFound(proposal_id)
        item = next(
            (
                candidate
                for candidate in proposal.get("items") or []
                if candidate.get("item_id") == item_id
            ),
            None,
        )
        if item is None:
            raise ChangeProposalNotFound(item_id)
        if item.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be regenerated from status {item.get('status')}",
                proposal=proposal,
            )
        if (item.get("target_kind") or "course_block") != "course_block":
            raise ChangeProposalConflict(
                "Knowledge-base proposal items cannot be regenerated as course blocks",
                proposal=proposal,
            )

        course_repository = get_course_document_repository()
        document, canonical = course_repository.load_document(course_id)
        if not canonical:
            raise ChangeProposalConflict(
                "Course must be migrated before regenerating changes",
                proposal=proposal,
            )
        block_id = str(item.get("block_id") or "")
        target = next(
            (block for block in document.blocks if block.block_id == block_id),
            None,
        )
        if target is None:
            raise ChangeProposalNotFound(block_id)

        instruction = str(extra_instruction or item.get("reason") or "").strip()
        regeneration_service = get_change_proposal_regeneration_service()
        user_id = require_user_id(request.headers.get("X-User-Id"))
        candidate = await regeneration_service.create_candidate(
            course_id,
            block_id,
            request_id=stable_hash(
                {
                    "proposal_id": proposal_id,
                    "item_id": item_id,
                    "instruction": instruction,
                },
                prefix="cpr_",
            ),
            expected_document_revision=document.document_revision,
            expected_block_revision=target.internal_revision,
            instruction=instruction,
            action_type="rewrite",
            user_id=user_id,
        )
        if candidate.get("status") == "generation_failed":
            candidate = await regeneration_service.retry_candidate(
                course_id,
                block_id,
                str(candidate.get("candidate_id") or ""),
                user_id=user_id,
            )
        if candidate.get("status") != "ready":
            status_code = 422 if candidate.get("status") == "quality_failed" else 503
            raise HTTPException(
                status_code=status_code,
                detail={
                    "code": "change_proposal_regeneration_failed",
                    "message": "Regenerated content did not become ready for review",
                    "candidate": candidate,
                },
            )
        proposed_block = candidate.get("proposed_block")
        proposed_payload = (
            proposed_block.get("payload")
            if isinstance(proposed_block, dict)
            else None
        )
        if not isinstance(proposed_payload, dict):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "change_proposal_regeneration_invalid",
                    "message": "Regenerated content payload is missing",
                },
            )
        return regenerate_item(
            repository,
            proposal_id,
            item_id,
            extra_instruction=extra_instruction,
            generated_after={"payload": proposed_payload},
            generation_meta={
                "candidate_id": candidate.get("candidate_id"),
                "quality_report": candidate.get("quality_report"),
            },
        )
    except (
        ChangeProposalNotFound,
        BlockRegenerationNotFound,
        CourseDocumentNotFound,
    ) as exc:
        raise HTTPException(status_code=404, detail="Change proposal or item not found") from exc
    except (
        ChangeProposalConflict,
        BlockRegenerationConflict,
        CourseDocumentConflict,
    ) as exc:
        proposal_detail = (
            exc.proposal if isinstance(exc, ChangeProposalConflict) else proposal
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "change_proposal_conflict",
                "message": str(exc),
                "proposal": proposal_detail,
            },
        ) from exc
