"""Teacher-facing course-local question-bank APIs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from dependencies import get_course_or_404
from material_storage import material_repository
from question_bank import (
    build_question_bank,
    filter_question_bank_items,
    question_bank_repository,
    reconcile_question_bank,
    review_question_bank_item,
    revise_question_bank_item,
)
from question_search import enrich_question_bank_with_web

router = APIRouter(
    prefix="/courses/{course_id}/question-bank",
    tags=["question_bank"],
)


class QuestionBankRebuildRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=8, max_length=200)


class QuestionBankReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2000)
    expected_bundle_revision_id: str | None = Field(default=None, max_length=200)


class QuestionBankRevisionRequest(BaseModel):
    patch: dict[str, Any]
    expected_bundle_revision_id: str | None = Field(default=None, max_length=200)


@router.get("")
async def get_question_bank(
    course_id: str,
    node_id: str | None = Query(default=None, max_length=200),
    source_type: str | None = Query(default=None, max_length=50),
    lifecycle_status: str | None = Query(default=None, max_length=50),
    risk: str | None = Query(default=None, max_length=100),
):
    await get_course_or_404(course_id)
    bundle = question_bank_repository.load_bundle(course_id)
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail={"code": "question_bank_not_built"},
        )
    items = filter_question_bank_items(
        bundle,
        node_id=node_id,
        source_type=source_type,
        lifecycle_status=lifecycle_status,
        risk=risk,
    )
    return {
        "schema_version": "question_bank_api_v1",
        "course_id": course_id,
        "bundle_revision_id": bundle.get("bundle_revision_id"),
        "coverage": bundle.get("coverage") or {},
        "review_queue": bundle.get("review_queue") or {},
        "web_enrichment": bundle.get("web_enrichment") or {},
        "items": items,
        "total": len(items),
    }


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_question_bank(
    course_id: str,
    payload: QuestionBankRebuildRequest,
):
    course = await get_course_or_404(course_id)
    previous = question_bank_repository.load_bundle(course_id)
    course_for_bank = deepcopy(course)
    course_for_bank["evidence_catalog"] = _load_course_evidence(
        course.get("material_bindings") or []
    )
    legacy_tasks = []
    if not previous:
        assets = course.get("learning_assets") or {}
        legacy_tasks = [
            *(assets.get("questions") or []),
            *(assets.get("final_assessment") or []),
        ]
    bundle = build_question_bank(course_for_bank, legacy_tasks=legacy_tasks)
    bundle = await enrich_question_bank_with_web(course, bundle)
    bundle = reconcile_question_bank(previous, bundle)
    stored = question_bank_repository.save_bundle(course_id, bundle)
    deduplicated = bool(
        previous
        and previous.get("bundle_revision_id") == stored.get("bundle_revision_id")
    )
    return {
        "schema_version": "question_bank_rebuild_v1",
        "course_id": course_id,
        "request_id": payload.request_id,
        "status": "completed",
        "deduplicated": deduplicated,
        "bundle_revision_id": stored["bundle_revision_id"],
        "coverage": stored["coverage"],
        "review_queue": stored["review_queue"],
        "web_enrichment": stored["web_enrichment"],
    }


@router.post("/items/{revision_id}/reviews")
async def review_question(
    course_id: str,
    revision_id: str,
    payload: QuestionBankReviewRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    await get_course_or_404(course_id)
    bundle = _require_bundle(course_id)
    _require_expected_revision(bundle, payload.expected_bundle_revision_id)
    try:
        updated = review_question_bank_item(
            bundle,
            revision_id,
            decision=payload.decision,
            reviewer_id=x_user_id or "local-teacher",
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stored = question_bank_repository.save_bundle(course_id, updated)
    return _mutation_response(stored, revision_id)


@router.post("/items/{revision_id}/revisions", status_code=status.HTTP_201_CREATED)
async def revise_question(
    course_id: str,
    revision_id: str,
    payload: QuestionBankRevisionRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    await get_course_or_404(course_id)
    bundle = _require_bundle(course_id)
    _require_expected_revision(bundle, payload.expected_bundle_revision_id)
    try:
        updated = revise_question_bank_item(
            bundle,
            revision_id,
            patch=payload.patch,
            editor_id=x_user_id or "local-teacher",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    stored = question_bank_repository.save_bundle(course_id, updated)
    edited = next(
        (
            item
            for item in stored.get("items") or []
            if item.get("parent_revision_id") == revision_id
        ),
        None,
    )
    return {
        **_mutation_response(stored, str((edited or {}).get("revision_id") or revision_id)),
        "item": edited,
    }


def _require_bundle(course_id: str) -> dict[str, Any]:
    bundle = question_bank_repository.load_bundle(course_id)
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail={"code": "question_bank_not_built"},
        )
    return bundle


def _require_expected_revision(
    bundle: dict[str, Any],
    expected_revision_id: str | None,
) -> None:
    if (
        expected_revision_id
        and expected_revision_id != bundle.get("bundle_revision_id")
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "question_bank_revision_conflict"},
        )


def _load_course_evidence(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in bindings:
        asset_id = str(binding.get("asset_id") or "")
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        try:
            result.extend(material_repository.load_evidence(asset_id))
        except (OSError, ValueError):
            continue
    return result


def _mutation_response(
    bundle: dict[str, Any],
    item_revision_id: str,
) -> dict[str, Any]:
    item = next(
        (
            value
            for value in bundle.get("items") or []
            if value.get("revision_id") == item_revision_id
        ),
        None,
    )
    return {
        "schema_version": "question_bank_mutation_v1",
        "course_id": bundle.get("course_id"),
        "bundle_revision_id": bundle.get("bundle_revision_id"),
        "review_queue": bundle.get("review_queue") or {},
        "item": item,
    }


__all__ = ["router"]
