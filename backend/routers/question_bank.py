"""Teacher-facing course-local question-bank APIs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from course_document import COURSE_DOCUMENT_SCHEMA
from course_repository import CourseDocumentRepository
from course_versioning import stable_hash
from course_versions import course_version_repository
from dependencies import get_course_or_404
from learning_asset_storage import learning_asset_repository
from learning_assets import compile_learning_assets
from material_storage import material_repository
from question_bank import (
    filter_question_bank_items,
    question_bank_repository,
    reconcile_question_bank,
    review_question_bank_item,
    revise_question_bank_item,
)
from question_search import enrich_question_bank_with_web
from storage import storage
from storage_utils import save_course_compat

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
    previous_assets = learning_asset_repository.load_bundle(course_id)
    if (
        payload.request_id
        and previous
        and previous_assets
        and course.get("question_bank_last_rebuild_request_id")
        == payload.request_id
    ):
        return _rebuild_response(
            course_id,
            payload.request_id,
            previous,
            previous_assets,
            course,
            deduplicated=True,
        )
    course_for_bank = deepcopy(course)
    course_for_bank["evidence_catalog"] = _load_course_evidence(
        course.get("material_bindings") or []
    )
    legacy_tasks = []
    if not previous:
        assets = (
            (previous_assets or {}).get("assets")
            or course.get("learning_assets")
            or {}
        )
        legacy_tasks = [
            *(assets.get("questions") or []),
            *(assets.get("final_assessment") or []),
        ]
    initial_assets = compile_learning_assets(
        course_for_bank,
        legacy_tasks=legacy_tasks,
    )
    bundle = initial_assets.pop("question_bank_bundle")
    compiled_knowledge_base = next(
        iter(
            initial_assets["assets"].get("course_knowledge_base")
            or []
        ),
        None,
    )
    if compiled_knowledge_base:
        course_for_bank["course_knowledge_base"] = deepcopy(
            compiled_knowledge_base
        )
    compiled_knowledge_map = next(
        iter(
            initial_assets["assets"].get("course_knowledge_map")
            or []
        ),
        None,
    )
    if compiled_knowledge_map:
        course_for_bank["course_knowledge_map"] = deepcopy(
            compiled_knowledge_map
        )
    bundle = await enrich_question_bank_with_web(course_for_bank, bundle)
    bundle = reconcile_question_bank(previous, bundle)
    compiled_assets = compile_learning_assets(
        course_for_bank,
        question_bank_bundle=bundle,
    )
    compiled_assets.pop("question_bank_bundle", None)
    compiled_assets = _select_publishable_asset_bundle(
        previous_assets,
        compiled_assets,
        bundle,
    )
    stored = question_bank_repository.save_bundle(
        course_id,
        bundle,
        activate=False,
    )
    stored_assets = learning_asset_repository.save_bundle(
        course_id,
        compiled_assets,
        activate=False,
    )
    deduplicated = bool(
        previous
        and previous.get("bundle_revision_id") == stored.get("bundle_revision_id")
        and previous_assets
        and previous_assets.get("bundle_revision_id")
        == stored_assets.get("bundle_revision_id")
        and course.get("question_bank_bundle_revision_id")
        == stored.get("bundle_revision_id")
        and course.get("learning_asset_bundle_revision_id")
        == stored_assets.get("bundle_revision_id")
    )
    published_course = course
    if not deduplicated:
        published_course = await _publish_rebuilt_course(
            course_id,
            course,
            stored,
            stored_assets,
            request_id=payload.request_id,
            previous_question_bank_revision_id=(
                str(previous.get("bundle_revision_id") or "")
                if previous
                else None
            ),
            previous_asset_revision_id=(
                str(previous_assets.get("bundle_revision_id") or "")
                if previous_assets
                else None
            ),
        )
    return _rebuild_response(
        course_id,
        payload.request_id,
        stored,
        stored_assets,
        published_course,
        deduplicated=deduplicated,
    )


def _rebuild_response(
    course_id: str,
    request_id: str | None,
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
    course: dict[str, Any],
    *,
    deduplicated: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "question_bank_rebuild_v1",
        "course_id": course_id,
        "request_id": request_id,
        "status": "completed",
        "deduplicated": deduplicated,
        "bundle_revision_id": question_bank_bundle["bundle_revision_id"],
        "learning_asset_bundle_revision_id": asset_bundle[
            "bundle_revision_id"
        ],
        "course_version_id": course.get(
            "current_course_version_id"
        ),
        "publication_mode": asset_bundle.get(
            "publication_mode",
            "full_recompile",
        ),
        "coverage": question_bank_bundle["coverage"],
        "review_queue": question_bank_bundle["review_queue"],
        "web_enrichment": question_bank_bundle["web_enrichment"],
    }


def _select_publishable_asset_bundle(
    previous_assets: dict[str, Any] | None,
    compiled_assets: dict[str, Any],
    question_bank_bundle: dict[str, Any],
) -> dict[str, Any]:
    if (compiled_assets.get("quality_report") or {}).get("passed"):
        selected = deepcopy(compiled_assets)
        selected["publication_mode"] = "full_recompile"
        return selected
    if not (
        previous_assets
        and (previous_assets.get("quality_report") or {}).get("passed")
    ):
        selected = deepcopy(compiled_assets)
        selected["publication_mode"] = "full_recompile"
        return selected

    approved_items = [
        item
        for item in question_bank_bundle.get("items") or []
        if item.get("lifecycle_status") == "approved"
        and item.get("assessment_role") in {
            "practice",
            "imported_practice",
            "web_enriched_practice",
        }
    ]
    publication_quality = {
        "schema_version": "question_bank_publication_quality_v1",
        "passed": bool(approved_items)
        and all(
            (item.get("quality_report") or {}).get("passed")
            for item in approved_items
        )
        and float(
            (question_bank_bundle.get("coverage") or {}).get(
                "coverage_ratio"
            )
            or 0
        )
        == 1,
        "approved_task_count": len(approved_items),
        "coverage_ratio": (
            question_bank_bundle.get("coverage") or {}
        ).get("coverage_ratio"),
    }
    if not publication_quality["passed"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "question_bank_publication_quality_failed",
                "quality_report": publication_quality,
            },
        )

    binding = {
        "schema_version": "question_bank_publication_v1",
        "course_id": question_bank_bundle.get("course_id"),
        "question_bank_bundle_revision_id": question_bank_bundle.get(
            "bundle_revision_id"
        ),
        "formal_task_revision_ids": [
            item.get("formal_task_revision_id")
            for item in approved_items
            if item.get("formal_task_revision_id")
        ],
        "quality_report": publication_quality,
        "compatibility_policy": (
            "preserve_passing_legacy_assets_and_overlay_approved_bank_tasks"
        ),
    }
    binding["revision_id"] = stable_hash(
        binding,
        prefix="qbpr_",
    )
    selected = deepcopy(previous_assets)
    selected.pop("bundle_revision_id", None)
    selected["assets"] = deepcopy(selected.get("assets") or {})
    selected["assets"]["question_bank_publications"] = [binding]
    selected["publication_mode"] = "question_bank_overlay"
    selected["question_bank_publication_quality"] = publication_quality
    return selected


async def _publish_rebuilt_course(
    course_id: str,
    course: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
    *,
    request_id: str | None,
    previous_question_bank_revision_id: str | None,
    previous_asset_revision_id: str | None,
) -> dict[str, Any]:
    updated = _course_with_rebuilt_assets(
        course,
        question_bank_bundle,
        asset_bundle,
    )
    if request_id:
        updated["question_bank_last_rebuild_request_id"] = request_id
    is_canonical = (
        course.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        or course.get("course_document_authoritative") is True
    )
    version_id: str | None = None
    if not is_canonical:
        base_version_id = course_version_repository.current_version_id(
            course_id
        )
        if not base_version_id:
            initial = course_version_repository.ensure_initial_version(
                course_id,
                course,
            )
            base_version_id = str(initial["version_id"])
        version = course_version_repository.create_version(
            course_id,
            updated,
            reason="重建课程题库并发布具体练习题",
            operation="question_bank_rebuild",
            base_version_id=base_version_id,
            changed_node_ids=[
                str(node.get("node_id") or "")
                for node in course.get("nodes") or []
                if node.get("node_id")
            ],
            activate=False,
        )
        version_id = str(version["version_id"])
        updated["current_course_version_id"] = version_id
        updated["blueprint_revision_id"] = version.get(
            "blueprint_revision_id"
        )

    persisted = False
    bank_activated = False
    assets_activated = False
    try:
        await _persist_rebuilt_course(course_id, course, updated)
        persisted = True
        question_bank_repository.activate_bundle(
            course_id,
            str(question_bank_bundle["bundle_revision_id"]),
        )
        bank_activated = True
        learning_asset_repository.activate_bundle(
            course_id,
            str(asset_bundle["bundle_revision_id"]),
        )
        assets_activated = True
        if version_id:
            course_version_repository.activate_version(
                course_id,
                version_id,
            )
        return updated
    except Exception:
        if assets_activated:
            _restore_bundle_pointer(
                learning_asset_repository,
                course_id,
                previous_asset_revision_id,
            )
        if bank_activated:
            _restore_bundle_pointer(
                question_bank_repository,
                course_id,
                previous_question_bank_revision_id,
            )
        if persisted:
            await _persist_rebuilt_course(course_id, updated, course)
        raise


def _course_with_rebuilt_assets(
    course: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(course)
    updated["learning_asset_plan"] = deepcopy(asset_bundle["plan"])
    updated["learning_assets"] = deepcopy(asset_bundle["assets"])
    updated["learning_asset_bundle_revision_id"] = asset_bundle[
        "bundle_revision_id"
    ]
    updated["asset_quality_report"] = deepcopy(
        asset_bundle["quality_report"]
    )
    updated["question_bank_bundle_revision_id"] = question_bank_bundle[
        "bundle_revision_id"
    ]
    updated["question_bank_coverage"] = deepcopy(
        question_bank_bundle["coverage"]
    )
    updated["question_bank_review_queue"] = deepcopy(
        question_bank_bundle["review_queue"]
    )
    updated["web_question_enrichment"] = deepcopy(
        question_bank_bundle["web_enrichment"]
    )
    knowledge_base = next(
        iter(updated["learning_assets"].get("course_knowledge_base") or []),
        None,
    )
    if knowledge_base:
        updated["course_knowledge_base"] = deepcopy(knowledge_base)
        updated["course_knowledge_quality_report"] = deepcopy(
            knowledge_base.get("quality_report")
        )
    knowledge_map = next(
        iter(updated["learning_assets"].get("course_knowledge_map") or []),
        None,
    )
    if knowledge_map:
        updated["course_knowledge_map"] = deepcopy(knowledge_map)
    return updated


async def _persist_rebuilt_course(
    course_id: str,
    previous: dict[str, Any],
    updated: dict[str, Any],
) -> None:
    is_canonical = (
        previous.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        or previous.get("course_document_authoritative") is True
    )
    if not is_canonical:
        await save_course_compat(storage, course_id, updated)
        return
    keys = {
        "learning_asset_plan",
        "learning_assets",
        "learning_asset_bundle_revision_id",
        "asset_quality_report",
        "question_bank_bundle_revision_id",
        "question_bank_coverage",
        "question_bank_review_queue",
        "web_question_enrichment",
        "question_bank_last_rebuild_request_id",
        "course_knowledge_base",
        "course_knowledge_quality_report",
        "course_knowledge_map",
    }
    updates = {
        key: deepcopy(updated[key])
        for key in keys
        if key in updated
    }
    repository = CourseDocumentRepository(storage)
    await repository.update_metadata(course_id, updates)


def _restore_bundle_pointer(
    repository: Any,
    course_id: str,
    previous_revision_id: str | None,
) -> None:
    if previous_revision_id:
        repository.activate_bundle(course_id, previous_revision_id)
        return
    pointer = repository.root_dir / course_id / "current.json"
    if pointer.exists():
        pointer.unlink()


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
