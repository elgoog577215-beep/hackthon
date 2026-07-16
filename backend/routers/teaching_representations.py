"""Read and reconcile same-source teaching representation state."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from dependencies import get_course_document_repository, get_course_or_404
from learner_context import require_user_id
from teaching_representations import (
    RepresentationConflict,
    TeachingRepresentationRepository,
    teaching_representation_repository,
)

router = APIRouter(
    prefix="/courses/{course_id}/teaching-representations",
    tags=["teaching_representations"],
)


def get_teaching_representation_repository() -> TeachingRepresentationRepository:
    return teaching_representation_repository


def _reconciled_registry(course_id: str) -> dict:
    course_repository = get_course_document_repository()
    raw = course_repository.load_raw(course_id)
    registry = get_teaching_representation_repository().reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    return registry.model_dump(mode="json")


@router.get("")
async def get_teaching_representations(course_id: str, request: Request) -> dict:
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    try:
        registry = await run_in_threadpool(_reconciled_registry, course_id)
    except RepresentationConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "teaching_representation_conflict",
            "message": str(exc),
        }) from exc
    return {"status": "success", "registry": registry}


@router.get("/derivation-graph")
async def get_teaching_representation_graph(course_id: str, request: Request) -> dict:
    payload = await get_teaching_representations(course_id, request)
    registry = payload["registry"]
    return {
        "status": "success",
        "course_id": course_id,
        "registry_revision": registry["registry_revision"],
        "derivation_graph": registry["derivation_graph"],
    }


@router.post("/reconcile")
async def reconcile_teaching_representations(course_id: str, request: Request) -> dict:
    payload = await get_teaching_representations(course_id, request)
    registry = payload["registry"]
    return {
        "status": "reconciled",
        "course_id": course_id,
        "registry_revision": registry["registry_revision"],
        "applied_revision_event_ids": registry["applied_revision_event_ids"],
        "stale_representation_ids": [
            item["representation_id"]
            for item in registry["representations"]
            if item["status"] == "stale"
        ],
    }


__all__ = ["router"]
