"""Read and reconcile same-source teaching representation state."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from queue import Queue
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from change_proposals import change_proposal_repository, create_authoring_change
from course_document import stable_hash
from course_revisions import revision_vector_for_document
from dependencies import get_course_document_repository, get_course_or_404
from learner_context import require_user_id
from representation_compiler import (
    export_slide_deck_pptx,
    rebuild_core_representations_safely,
    validate_compiled_representations,
)
from storage import DATA_DIR
from teaching_representations import (
    RepresentationConflict,
    TeachingRepresentationRepository,
    teaching_representation_repository,
)
from representation_edits import (
    apply_representation_only_edit,
    classify_representation_edit,
    representation_edit_impact,
)

router = APIRouter(
    prefix="/courses/{course_id}/teaching-representations",
    tags=["teaching_representations"],
)


def get_teaching_representation_repository() -> TeachingRepresentationRepository:
    return teaching_representation_repository


class RepresentationEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: str
    field: str
    before: object | None = None
    after: object
    semantic_intent: bool | None = None


class ApplyRepresentationEditRequest(RepresentationEditRequest):
    decision: str


def _reconciled_registry(course_id: str) -> dict:
    course_repository = get_course_document_repository()
    raw = course_repository.load_raw(course_id)
    registry = get_teaching_representation_repository().reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    return registry.model_dump(mode="json")


def _compile_registry(
    course_id: str,
    *,
    progress_callback: Any | None = None,
) -> dict:
    course_repository = get_course_document_repository()
    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise RepresentationConflict("Course must be migrated before compiling representations")
    raw = course_repository.load_raw(course_id)
    build = rebuild_core_representations_safely(
        document,
        course_repository.load_course_view(course_id),
        get_teaching_representation_repository(),
        progress_callback=progress_callback,
    )
    registry = get_teaching_representation_repository().reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    current_spec_ids = {item.spec_id for item in registry.representations}
    current_specs = [item for item in registry.specs if item.spec_id in current_spec_ids]
    return {
        "build": build,
        "quality": build.get("quality") or validate_compiled_representations(current_specs),
        "registry": registry.model_dump(mode="json"),
    }


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


@router.post("/build")
async def build_teaching_representations(course_id: str, request: Request) -> dict:
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    try:
        result = await run_in_threadpool(_compile_registry, course_id)
    except RepresentationConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "teaching_representation_conflict",
            "message": str(exc),
        }) from exc
    return {"status": "success", **result}


@router.post("/build/stream")
async def stream_teaching_representation_build(course_id: str, request: Request) -> StreamingResponse:
    """Stream page-level progress while preserving atomic final publication."""
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)

    async def event_stream():
        events: Queue[dict[str, Any] | None] = Queue()

        def publish(payload: dict[str, Any]) -> None:
            events.put(payload)

        def worker() -> None:
            try:
                result = _compile_registry(course_id, progress_callback=publish)
                publish({"event": "build_complete", "progress": 100, **result})
            except Exception as exc:
                publish({
                    "event": "error",
                    "progress": 100,
                    "message": str(exc),
                })
            finally:
                events.put(None)

        task = asyncio.create_task(asyncio.to_thread(worker))
        sequence = 0
        while True:
            payload = await asyncio.to_thread(events.get)
            if payload is None:
                break
            sequence += 1
            event_name = str(payload.get("event") or "message")
            body = {**payload, "sequence": sequence}
            yield f"id: {sequence}\nevent: {event_name}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/quality")
async def get_teaching_representation_quality(course_id: str, request: Request) -> dict:
    payload = await get_teaching_representations(course_id, request)
    registry = payload["registry"]
    current_spec_ids = {item["spec_id"] for item in registry["representations"]}
    current_specs = [
        item for item in registry.get("specs") or []
        if item["spec_id"] in current_spec_ids
    ]
    from teaching_representations import TeachingRepresentationSpec

    report = validate_compiled_representations([
        TeachingRepresentationSpec.model_validate(item) for item in current_specs
    ])
    return {"status": "success", "quality": report}


def _representation_and_spec(course_id: str, representation_id: str):
    registry = get_teaching_representation_repository().load(course_id)
    representation = next((
        item for item in registry.representations
        if item.representation_id == representation_id
    ), None)
    if representation is None:
        raise KeyError(representation_id)
    spec = next((item for item in registry.specs if item.spec_id == representation.spec_id), None)
    if spec is None:
        raise KeyError(representation.spec_id)
    return registry, representation, spec


def _representation_unit(spec: Any, unit_id: str) -> dict[str, Any] | None:
    content = spec.payload.get("content") or {}
    units = (
        content.get("units")
        or content.get("slides")
        or content.get("sections")
        or []
    )
    return next(
        (item for item in units if str(item.get("unit_id") or "") == unit_id),
        None,
    )


@router.post("/{representation_id}/edits/preview")
async def preview_teaching_representation_edit(
    course_id: str,
    representation_id: str,
    body: RepresentationEditRequest,
    request: Request,
) -> dict:
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    try:
        registry, _representation, spec = await run_in_threadpool(
            _representation_and_spec,
            course_id,
            representation_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Teaching representation not found") from exc
    classification = classify_representation_edit(
        field=body.field,
        before=body.before,
        after=body.after,
        semantic_intent=body.semantic_intent,
    )
    impact = representation_edit_impact(registry, spec, unit_id=body.unit_id)
    return {"status": "preview", **classification, "impact": impact}


@router.post("/{representation_id}/edits/apply")
async def apply_teaching_representation_edit(
    course_id: str,
    representation_id: str,
    body: ApplyRepresentationEditRequest,
    request: Request,
) -> dict:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    try:
        registry, representation, spec = await run_in_threadpool(
            _representation_and_spec,
            course_id,
            representation_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Teaching representation not found") from exc
    classification = classify_representation_edit(
        field=body.field,
        before=body.before,
        after=body.after,
        semantic_intent=body.semantic_intent,
    )
    impact = representation_edit_impact(registry, spec, unit_id=body.unit_id)
    if body.decision == "representation_only":
        try:
            updated = await run_in_threadpool(
                apply_representation_only_edit,
                get_teaching_representation_repository(),
                registry,
                representation,
                spec,
                unit_id=body.unit_id,
                field=body.field,
                after=body.after,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={
                "code": "representation_quality_blocked",
                "message": str(exc),
            }) from exc
        return {
            "status": "applied_to_representation",
            "classification": (
                classification["classification"]
                if classification["classification"] != "ambiguous"
                else "equivalent_semantic"
            ),
            "impact": impact,
            "registry": updated.model_dump(mode="json"),
        }
    if body.decision != "course_semantic":
        raise HTTPException(status_code=422, detail="Edit decision must be representation_only or course_semantic")
    course_repository = get_course_document_repository()
    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise HTTPException(status_code=409, detail="Course must be migrated before semantic edits")
    before_text = str(body.before or "").strip()
    after_text = str(body.after or "").strip()
    if not after_text:
        raise HTTPException(status_code=422, detail="Semantic course content cannot be empty")
    unit = _representation_unit(spec, body.unit_id) or {}
    source_keys = set(impact.get("source_keys") or [])
    section_ids = impact.get("section_ids") or []
    unit_section_id = str(unit.get("section_id") or (section_ids[0] if section_ids else ""))
    source_section = next(
        (item for item in document.sections if item.section_id == unit_section_id),
        None,
    )
    is_objective_edit = (
        body.field == "key_message"
        and (
            unit.get("slide_purpose") == "learning_objective"
            or any(key.startswith("objective:") for key in source_keys)
            or (
                source_section is not None
                and before_text == source_section.learning_objective.strip()
            )
        )
    )
    request_id = stable_hash({
        "user_id": user_id,
        "representation_id": representation_id,
        "unit_id": body.unit_id,
        "field": body.field,
        "before": body.before,
        "after": body.after,
        "document_revision": document.document_revision,
    }, prefix="representation-edit-")
    if is_objective_edit:
        section_id = unit_section_id
        section = source_section
        if section is None:
            raise HTTPException(status_code=404, detail="Source course section not found")
        vector = revision_vector_for_document(document).revisions
        objective_revision = (
            vector.get(f"objective:{section.objective_id}")
            if section.objective_id
            else None
        ) or stable_hash(
            {
                "objective_id": section.objective_id,
                "learning_objective": section.learning_objective,
                "section_id": section.section_id,
            },
            prefix="cor_",
        )
        target_ids = [section_id]
        scope = "section"
        items = [{
            "block_id": section_id,
            "target_kind": "course_objective",
            "before": {
                "section_id": section_id,
                "learning_objective": section.learning_objective,
                "objective_id": section.objective_id,
                "objective_revision_id": objective_revision,
            },
            "after": {
                "section_id": section_id,
                "learning_objective": after_text,
                "objective_id": section.objective_id,
            },
            "reason": "PPT 学习目标承载正式教学意图，确认后回写课程目标真源并精准联动相关表达。",
        }]
    else:
        block_ids = impact.get("block_ids") or []
        if not block_ids:
            raise HTTPException(
                status_code=409,
                detail="This representation unit has no editable course block source",
            )
        block_id = str(block_ids[0])
        block = next((item for item in document.blocks if item.block_id == block_id), None)
        if block is None:
            raise HTTPException(status_code=404, detail="Source course block not found")
        content_key = (
            "markdown"
            if "markdown" in block.payload
            else ("text" if "text" in block.payload else "content")
        )
        current_content = str(block.payload.get(content_key) or "")
        next_content = (
            current_content.replace(before_text, after_text, 1)
            if before_text and before_text in current_content
            else f"{current_content}\n\n{after_text}".strip()
        )
        next_payload = deepcopy(block.payload)
        next_payload[content_key] = next_content
        target_ids = [block_id]
        scope = "block"
        items = [{
            "block_id": block_id,
            "before": deepcopy(block.payload),
            "after": {"payload": next_payload},
            "reason": "派生产物中的语义修改需要先回写课程真源，再同步所有相关教学表达。",
        }]
    authoring_change = create_authoring_change(
        change_proposal_repository,
        course_id,
        request_id=request_id,
        scope=scope,
        target_block_ids=target_ids,
        items=items,
        source="representation_semantic",
        generation_meta={
            "origin": "teaching_representation_edit",
            "representation_id": representation_id,
            "unit_id": body.unit_id,
            "classification": "semantic",
            "semantic_change": classification.get("semantic_change"),
            "impact": impact,
        },
    )
    return {
        "status": "course_change_proposed",
        "classification": "semantic",
        "impact": impact,
        "authoring_change": authoring_change,
        # Compatibility field for clients that still use the old name.
        "proposal": authoring_change,
    }


@router.get("/{representation_id}/spec")
async def get_teaching_representation_spec(
    course_id: str,
    representation_id: str,
    request: Request,
) -> dict:
    payload = await get_teaching_representations(course_id, request)
    registry = payload["registry"]
    representation = next((
        item for item in registry["representations"]
        if item["representation_id"] == representation_id
    ), None)
    if representation is None:
        raise HTTPException(status_code=404, detail="Teaching representation not found")
    spec = next((
        item for item in registry.get("specs") or []
        if item["spec_id"] == representation["spec_id"]
    ), None)
    if spec is None:
        raise HTTPException(status_code=404, detail="Teaching representation spec not found")
    return {"status": "success", "representation": representation, "spec": spec}


@router.get("/{representation_id}/export.pptx")
async def export_teaching_slide_deck(
    course_id: str,
    representation_id: str,
    request: Request,
) -> FileResponse:
    payload = await get_teaching_representation_spec(course_id, representation_id, request)
    representation = payload["representation"]
    if representation["representation_type"] != "slide_deck":
        raise HTTPException(status_code=409, detail="Only slide decks can be exported to pptx")
    from teaching_representations import TeachingRepresentationSpec

    spec = TeachingRepresentationSpec.model_validate(payload["spec"])
    output_path = Path(DATA_DIR) / "teaching_exports" / f"{representation_id}-{spec.revision}.pptx"
    try:
        await run_in_threadpool(export_slide_deck_pptx, spec, output_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "slide_export_quality_blocked",
            "message": str(exc),
        }) from exc
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{course_id}-slides.pptx",
    )


__all__ = ["router"]
