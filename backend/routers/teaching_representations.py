"""Read and reconcile same-source teaching representation state."""

from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from change_proposals import change_proposal_repository, create_authoring_change
from ai_base import AIBase
from course_document import stable_hash
from course_logic_upgrade import (
    CourseLogicUpgradeError,
    compile_course_logic_upgrade,
)
from course_repository import CourseDocumentConflict
from course_revisions import revision_vector_for_course, revision_vector_for_document
from dependencies import (
    get_course_document_repository,
    get_course_or_404,
    get_task_manager_optional,
)
from learner_context import require_user_id
from product_runtime_policy import demo_overrides_enabled
from representation_compiler import (
    export_slide_deck_pptx,
    rebuild_core_representations_safely,
    rebuild_slide_deck_variant_safely,
    validate_compiled_representations,
)
from slide_deck import SlideDeckPlanV1, plan_slide_deck
from slide_deck_v3 import (
    SLIDE_DECK_V3_COMPILER_VERSION,
    SlideAllocationPlanV2,
    SlideDeckMode,
    SlideDeckTheme,
    fragment_course_document,
    normalize_slide_deck_theme,
    plan_slide_deck_v3,
    slide_deck_variant_key,
)
from slide_deck_v4 import (
    allocation_from_story_plan_v2,
    build_signature_v4,
)
from slide_deck_v5 import build_signature_v5, compact_story_plan_v5
from slide_story_plan import (
    SlideStoryPlanPrerequisiteError,
    SlideStoryPlanV2,
    compile_slide_story_plan_v2,
    course_supports_slide_deck_v4,
    resolve_slide_deck_schema,
    slide_deck_v4_prerequisite_details,
    slide_deck_v4_prerequisite_issues,
)
from slide_deck_renderer import SlideDeckQualityError, validate_theme
from slide_asset_repository import slide_asset_repository
from slide_ai_runtime import ai_slide_planning_enabled
from slide_theme import slide_theme_version
from slide_visuals import build_signature
from storage import DATA_DIR
from teaching_representations import (
    RepresentationConflict,
    TeachingRepresentationRepository,
    teaching_representation_repository,
)
from representation_edits import (
    apply_course_text_patch_preview,
    apply_representation_only_edit,
    build_course_text_patch,
    classify_representation_edit,
    representation_edit_impact,
)

router = APIRouter(
    prefix="/courses/{course_id}/teaching-representations",
    tags=["teaching_representations"],
)


def get_teaching_representation_repository() -> TeachingRepresentationRepository:
    return teaching_representation_repository


def get_slide_deck_ai_planner() -> Callable[[dict[str, Any]], Any] | None:
    """Return the OpenAI-compatible planner when a provider is configured."""
    provider = AIBase()
    if not ai_slide_planning_enabled(
        provider_available=provider.client is not None,
    ):
        return None

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only a valid slide_deck_plan_v1 JSON object. Preserve every provided "
                "section_id and source_block_id exactly, use 12-18 slides, and include cover, "
                "roadmap, concise teaching slides, at most two practice slides, and recap."
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        return provider._extract_json(response or "") or {}

    return planner


class RepresentationEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: str
    field: str
    before: object | None = None
    after: object
    semantic_intent: bool | None = None


class ApplyRepresentationEditRequest(RepresentationEditRequest):
    decision: str


class SlideDeckVariantBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SlideDeckMode = "teaching"
    theme: SlideDeckTheme = "qizhi-classroom"
    force_rebuild: bool = False


def _reconciled_registry(course_id: str) -> dict:
    course_repository = get_course_document_repository()
    raw = course_repository.load_raw(course_id)
    document, _canonical = course_repository.load_document(course_id)
    course_view = course_repository.load_course_view(course_id)
    repository = get_teaching_representation_repository()
    repository.reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    registry = repository.reconcile_source_revision_vector(
        course_id,
        revision_vector_for_course(document, course_view),
    )
    payload = registry.model_dump(mode="json")
    story_engine_enabled = _story_engine_enabled()
    v4_eligible = course_supports_slide_deck_v4(course_view)
    payload["slide_deck_v4_eligible"] = v4_eligible
    payload["slide_deck_v4_upgrade_required"] = not v4_eligible
    payload["slide_deck_story_engine_enabled"] = story_engine_enabled
    payload["slide_deck_target_schema"] = (
        "slide_deck_v3"
        if not story_engine_enabled
        else "slide_deck_v5"
        if v4_eligible and _v5_enabled()
        else "slide_deck_v4"
        if v4_eligible
        else "blocked"
    )
    payload["slide_deck_v4_blockers"] = (
        [] if v4_eligible else slide_deck_v4_prerequisite_issues(course_view)
    )
    payload["slide_deck_v4_blocker_details"] = (
        [] if v4_eligible else slide_deck_v4_prerequisite_details(course_view)
    )
    specs = {
        item["spec_id"]: item
        for item in payload.get("specs") or []
    }
    for representation in payload.get("representations") or []:
        if representation.get("representation_type") != "slide_deck":
            continue
        spec = specs.get(representation.get("spec_id")) or {}
        content = (spec.get("payload") or {}).get("content") or {}
        schema_version = content.get("schema_version")
        if schema_version not in {
            "slide_deck_v3",
            "slide_deck_v4",
            "slide_deck_v5",
        }:
            continue
        if schema_version == "slide_deck_v3" and story_engine_enabled:
            representation["course_logic_upgrade_required"] = True
            representation["course_logic_upgrade_reason"] = (
                "新版课程逻辑 V4 已可用，请重新生成当前 PPT"
                if v4_eligible
                else "当前课程逻辑产物未就绪，请先完成课程升级后再生成 PPT"
            )
        expected = _expected_slide_signature(
            document,
            course_view,
            mode=str(content.get("mode") or "teaching"),
            theme=normalize_slide_deck_theme(
                str(content.get("theme") or "qizhi-classroom")
            ),
            force_schema=str(schema_version),
        )
        actual = str((content.get("build_signature") or {}).get("signature") or "")
        if actual != expected["signature"]:
            representation["visual_engine_update_available"] = True
            representation["visual_engine_update_reason"] = "视觉引擎已更新"
    return payload


def _story_engine_enabled() -> bool:
    return os.getenv(
        "SLIDE_STORY_ENGINE_V2_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _v5_enabled() -> bool:
    return os.getenv(
        "SLIDE_DECK_V5_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _expected_slide_signature(
    document: Any,
    course_view: dict[str, Any],
    *,
    mode: str,
    theme: str,
    force_schema: str = "",
) -> dict[str, Any]:
    if force_schema == "slide_deck_v4":
        return build_signature_v4(
            document=document,
            course_data=course_view,
            mode=mode,  # type: ignore[arg-type]
            theme=theme,  # type: ignore[arg-type]
        )
    use_v5 = (
        force_schema == "slide_deck_v5"
        or (
            force_schema != "slide_deck_v3"
            and force_schema != "slide_deck_v4"
            and _story_engine_enabled()
            and _v5_enabled()
            and course_supports_slide_deck_v4(course_view)
        )
    )
    if use_v5:
        return build_signature_v5(
            document=document,
            course_data=course_view,
            mode=mode,
            theme=theme,
        )
    return build_signature(
        source_document_revision=str(document.document_revision or ""),
        mode=mode,
        theme=theme,
        compiler_version=SLIDE_DECK_V3_COMPILER_VERSION,
        theme_version=slide_theme_version(),
    )


def _compile_registry(
    course_id: str,
    *,
    progress_callback: Any | None = None,
    deck_plan: SlideDeckPlanV1 | dict[str, Any] | None = None,
) -> dict:
    course_repository = get_course_document_repository()
    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise RepresentationConflict("Course must be migrated before compiling representations")
    raw = course_repository.load_raw(course_id)
    representation_repository = get_teaching_representation_repository()
    representation_repository.reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    build = rebuild_core_representations_safely(
        document,
        course_repository.load_course_view(course_id),
        representation_repository,
        progress_callback=progress_callback,
        deck_plan=deck_plan,
    )
    registry = representation_repository.reconcile_course_operation_log(
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


def _load_registry_slide_source(course_id: str) -> tuple[Any, dict[str, Any]]:
    course_repository = get_course_document_repository()
    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise RepresentationConflict("Course must be migrated before compiling representations")
    return document, course_repository.load_course_view(course_id)


async def _plan_registry_slide_deck(course_id: str) -> SlideDeckPlanV1:
    document, course_view = await run_in_threadpool(_load_registry_slide_source, course_id)
    return await plan_slide_deck(
        document,
        course_view,
        ai_planner=get_slide_deck_ai_planner(),
    )


def _compile_slide_variant_registry(
    course_id: str,
    *,
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
    allocation_plan: SlideAllocationPlanV2 | dict[str, Any],
    story_plan: SlideStoryPlanV2 | dict[str, Any] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    course_repository = get_course_document_repository()
    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise RepresentationConflict("Course must be migrated before compiling slide variants")
    raw = course_repository.load_raw(course_id)
    repository = get_teaching_representation_repository()
    repository.reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    build = rebuild_slide_deck_variant_safely(
        document,
        course_repository.load_course_view(course_id),
        repository,
        mode=mode,
        theme=theme,
        allocation_plan=allocation_plan,
        story_plan=story_plan,
        progress_callback=progress_callback,
    )
    registry = repository.reconcile_course_operation_log(
        course_id,
        list(raw.get("course_operation_log") or []),
    )
    return {
        "build": build,
        "quality": build.get("quality") or {},
        "registry": registry.model_dump(mode="json"),
        "variant_key": slide_deck_variant_key(mode, theme),
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


@router.post("/course-logic/upgrade")
async def upgrade_course_logic(course_id: str, request: Request) -> dict:
    """Promote migrated node semantics into the official V4 course contracts."""
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    course_repository = get_course_document_repository()
    raw = course_repository.load_raw(course_id)
    if not course_repository.is_canonical(raw):
        raise HTTPException(status_code=409, detail={
            "code": "course_migration_required",
            "message": "Course must be migrated before upgrading course logic",
        })
    course_view = course_repository.load_course_view(course_id)
    try:
        upgrade = await run_in_threadpool(
            compile_course_logic_upgrade,
            course_view,
        )
        if not upgrade["already_ready"]:
            await course_repository.update_metadata(
                course_id,
                upgrade["updates"],
                expected_document_revision=str(
                    raw.get("course_document_revision") or ""
                ),
            )
        registry = await run_in_threadpool(_reconciled_registry, course_id)
    except (CourseLogicUpgradeError, CourseDocumentConflict) as exc:
        raise HTTPException(status_code=409, detail={
            "code": "course_logic_upgrade_blocked",
            "message": str(exc),
        }) from exc
    return {
        "status": "success",
        "course_id": course_id,
        "already_ready": bool(upgrade["already_ready"]),
        "summary": upgrade["summary"],
        "registry": registry,
    }


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
        deck_plan = await _plan_registry_slide_deck(course_id)
        result = await run_in_threadpool(_compile_registry, course_id, deck_plan=deck_plan)
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

    task_manager = get_task_manager_optional()
    if task_manager is not None:
        task_id = await task_manager.create_task(
            course_id,
            "teaching_representation_build",
            request_snapshot={"operation": "build_teaching_representations"},
        )

        async def durable_event_stream():
            cursor = 0
            started = {
                "event": "planner_started", "progress": 1,
                "sequence": 0, "task_id": task_id,
            }
            yield f"id: 0\nevent: planner_started\ndata: {json.dumps(started, ensure_ascii=False)}\n\n"
            while True:
                task = task_manager.get_task(task_id)
                if not task:
                    payload = {"event": "error", "message": "Build task was removed", "task_id": task_id}
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                history = task.get("event_history") or []
                for payload in history:
                    sequence = int(payload.get("sequence") or 0)
                    if sequence <= cursor:
                        continue
                    cursor = sequence
                    body = {**payload, "task_id": task_id}
                    name = str(payload.get("event") or "message")
                    yield f"id: {sequence}\nevent: {name}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
                status = str(task.get("status") or "")
                if status in {"completed", "failed", "cancelled", "paused"}:
                    if status != "completed" and not any(
                        str(item.get("event") or "") == "error" for item in history
                    ):
                        failure_detail = task.get("error_detail") or {}
                        payload = {
                            "event": "error" if status == "failed" else status,
                            "progress": int(task.get("progress") or 0),
                            "code": str(failure_detail.get("code") or ""),
                            "message": str(
                                failure_detail.get("message")
                                or task.get("error")
                                or task.get("message")
                                or status
                            ),
                            "action": str(failure_detail.get("action") or ""),
                            "retryable": failure_detail.get("retryable"),
                            "task_id": task_id,
                        }
                        yield f"event: {payload['event']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                await asyncio.sleep(0.12)

        return StreamingResponse(
            durable_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        sequence = 1
        planning = {
            "event": "planner_started",
            "progress": 1,
            "sequence": sequence,
        }
        yield f"id: {sequence}\nevent: planner_started\ndata: {json.dumps(planning, ensure_ascii=False)}\n\n"
        try:
            deck_plan = await _plan_registry_slide_deck(course_id)
        except RepresentationConflict as exc:
            sequence += 1
            payload = {
                "event": "error",
                "progress": 100,
                "code": "teaching_representation_conflict",
                "message": str(exc),
                "sequence": sequence,
            }
            yield f"id: {sequence}\nevent: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            return

        events: Queue[dict[str, Any] | None] = Queue()

        def publish(payload: dict[str, Any]) -> None:
            events.put(payload)

        def worker() -> None:
            try:
                result = _compile_registry(
                    course_id,
                    progress_callback=publish,
                    deck_plan=deck_plan,
                )
                # A blocked quality gate leaves the previous registry in place.
                # Reporting build_complete would tell the caller a new build was
                # published when nothing changed, so surface build_blocked.
                blocked = (
                    str((result.get("build") or {}).get("status") or "") != "synchronized"
                    or not (result.get("quality") or {}).get("passed", False)
                )
                publish({
                    "event": "build_blocked" if blocked else "build_complete",
                    "progress": 100,
                    **result,
                })
            except Exception as exc:
                publish({
                    "event": "error",
                    "progress": 100,
                    "message": str(exc),
                })
            finally:
                events.put(None)

        task = asyncio.create_task(asyncio.to_thread(worker))
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


@router.post("/slide-decks/build/stream")
async def stream_slide_deck_variant_build(
    course_id: str,
    body: SlideDeckVariantBuildRequest,
    request: Request,
) -> StreamingResponse:
    """Build one mode/theme PPT variant and stream page-level progress."""
    require_user_id(request.headers.get("X-User-Id"))
    await get_course_or_404(course_id)
    theme = normalize_slide_deck_theme(body.theme)
    variant_key = slide_deck_variant_key(body.mode, theme)
    document, course_view = await run_in_threadpool(_load_registry_slide_source, course_id)
    try:
        resolve_slide_deck_schema(
            course_view,
            story_engine_enabled=_story_engine_enabled(),
            v5_enabled=_v5_enabled(),
        )
    except SlideStoryPlanPrerequisiteError as exc:
        raise HTTPException(status_code=409, detail=exc.public_detail()) from exc
    registry = get_teaching_representation_repository().load(course_id)
    cached = next((
        item for item in registry.representations
        if item.representation_type == "slide_deck"
        and item.variant_key == variant_key
        and item.status == "ready"
    ), None)
    cached_parts = sorted(
        [
            item for item in registry.representations
            if (
                item.representation_type == "slide_deck"
                and item.variant_key.startswith(f"{variant_key}:part:")
                and item.status == "ready"
            )
        ],
        key=lambda item: item.variant_key,
    )
    if cached is None and cached_parts:
        cached = cached_parts[0]
    cached_spec = next((
        item for item in registry.specs
        if cached is not None and item.spec_id == cached.spec_id
    ), None)
    cached_content = cached_spec.payload.get("content") if cached_spec else {}
    cached_bundle_part = (cached_content or {}).get("bundle_part") or {}
    cached_source_revision = str(
        cached_bundle_part.get("source_document_revision")
        or (cached_content or {}).get("source_document_revision")
        or ""
    )
    cached_signature = (
        cached_bundle_part.get("build_signature")
        or (cached_content or {}).get("build_signature")
        or {}
    )
    expected_signature = (
        (
            build_signature_v5(
                document=document,
                course_data=course_view,
                mode=body.mode,
                theme=theme,
            )
            if cached_bundle_part.get("slide_schema_version") == "slide_deck_v5"
            else build_signature_v4(
                document=document,
                course_data=course_view,
                mode=body.mode,
                theme=theme,
            )
            if cached_bundle_part.get("slide_schema_version") == "slide_deck_v4"
            else build_signature(
                source_document_revision=str(document.document_revision or ""),
                mode=body.mode,
                theme=theme,
                compiler_version=SLIDE_DECK_V3_COMPILER_VERSION,
                theme_version=slide_theme_version(),
            )
        )["signature"]
        if cached_bundle_part
        else _expected_slide_signature(
            document,
            course_view,
            mode=body.mode,
            theme=theme,
        )["signature"]
    )
    cached_bundle_complete = (
        not cached_bundle_part
        or (
            len(cached_parts) == int(cached_bundle_part.get("part_count") or 0)
            and all(
                item.variant_key
                == f"{variant_key}:part:{index:02d}"
                for index, item in enumerate(cached_parts, start=1)
            )
        )
    )
    cached_current = bool(
        cached_spec
        and cached_source_revision == str(document.document_revision or "")
        and str(
            cached_signature.get("signature")
            or ""
        )
        == expected_signature
        and cached_bundle_complete
    )
    if cached_current and not body.force_rebuild:
        async def cached_event_stream():
            payload = {
                "event": "build_complete",
                "progress": 100,
                "stage": "complete",
                "cached": True,
                "variant_key": variant_key,
                "quality": (cached_spec.payload.get("content") or {}).get("quality_report") or {},
                "registry": registry.model_dump(mode="json"),
            }
            yield f"id: 1\nevent: build_complete\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            cached_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    task_manager = get_task_manager_optional()
    if task_manager is not None:
        task_id = await task_manager.create_task(
            course_id,
            "slide_deck_variant_build",
            request_snapshot={
                "operation": "build_slide_deck_variant",
                "mode": body.mode,
                "theme": theme,
                "variant_key": variant_key,
                "force_rebuild": body.force_rebuild,
            },
            base_document_revision=str(document.document_revision or ""),
        )

        async def durable_event_stream():
            cursor = 0
            started = {
                "event": "planner_started",
                "progress": 1,
                "sequence": 0,
                "task_id": task_id,
                "variant_key": variant_key,
            }
            yield f"id: 0\nevent: planner_started\ndata: {json.dumps(started, ensure_ascii=False)}\n\n"
            while True:
                task = task_manager.get_task(task_id)
                if not task:
                    payload = {
                        "event": "error",
                        "message": "Build task was removed",
                        "task_id": task_id,
                    }
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                history = task.get("event_history") or []
                for payload in history:
                    sequence = int(payload.get("sequence") or 0)
                    if sequence <= cursor:
                        continue
                    cursor = sequence
                    event_name = str(payload.get("event") or "message")
                    event_body = {**payload, "task_id": task_id}
                    yield (
                        f"id: {sequence}\nevent: {event_name}\n"
                        f"data: {json.dumps(event_body, ensure_ascii=False)}\n\n"
                    )
                status = str(task.get("status") or "")
                if status in {"completed", "failed", "cancelled", "paused"}:
                    if status != "completed" and not any(
                        str(item.get("event") or "") == "error" for item in history
                    ):
                        failure_detail = task.get("error_detail") or {}
                        payload = {
                            "event": "error" if status == "failed" else status,
                            "progress": int(task.get("progress") or 0),
                            "code": str(failure_detail.get("code") or ""),
                            "message": str(
                                failure_detail.get("message")
                                or task.get("error")
                                or task.get("message")
                                or status
                            ),
                            "action": str(failure_detail.get("action") or ""),
                            "retryable": failure_detail.get("retryable"),
                            "task_id": task_id,
                        }
                        yield f"event: {payload['event']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                await asyncio.sleep(0.12)

        return StreamingResponse(
            durable_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        sequence = 1
        started = {
            "event": "planner_started",
            "progress": 1,
            "sequence": sequence,
            "variant_key": variant_key,
        }
        yield f"id: {sequence}\nevent: planner_started\ndata: {json.dumps(started, ensure_ascii=False)}\n\n"
        story_plan: SlideStoryPlanV2 | None = None
        if _story_engine_enabled() and course_supports_slide_deck_v4(course_view):
            source_fragments = fragment_course_document(document)
            story_plan = compile_slide_story_plan_v2(
                document,
                course_view,
                source_fragments,
                mode=body.mode,
                theme=theme,  # type: ignore[arg-type]
            )
            if _v5_enabled():
                story_plan = compact_story_plan_v5(
                    document,
                    story_plan,
                    source_fragments,
                )
            allocation_plan, _ = allocation_from_story_plan_v2(
                document,
                source_fragments,
                story_plan,
            )
        else:
            allocation_plan = await plan_slide_deck_v3(
                document,
                course_view,
                mode=body.mode,
                theme=theme,  # type: ignore[arg-type]
            )
        events: Queue[dict[str, Any] | None] = Queue()

        def publish(payload: dict[str, Any]) -> None:
            events.put(payload)

        def worker() -> None:
            try:
                result = _compile_slide_variant_registry(
                    course_id,
                    mode=body.mode,
                    theme=theme,  # type: ignore[arg-type]
                    allocation_plan=allocation_plan,
                    story_plan=story_plan,
                    progress_callback=publish,
                )
                blocked = (
                    str((result.get("build") or {}).get("status") or "") != "synchronized"
                    or not (result.get("quality") or {}).get("passed", False)
                )
                publish({
                    "event": "build_blocked" if blocked else "build_complete",
                    "progress": 100,
                    **result,
                })
            except Exception as exc:
                publish({"event": "error", "progress": 100, "message": str(exc)})
            finally:
                events.put(None)

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        while True:
            payload = await asyncio.to_thread(events.get)
            if payload is None:
                break
            sequence += 1
            event_name = str(payload.get("event") or "message")
            event_body = {**payload, "sequence": sequence}
            yield f"id: {sequence}\nevent: {event_name}\ndata: {json.dumps(event_body, ensure_ascii=False)}\n\n"
        await worker_task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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


def _representation_and_spec_reconciled(course_id: str, representation_id: str):
    try:
        return _representation_and_spec(course_id, representation_id)
    except KeyError:
        # A representation request can race with an atomic registry publish.
        # Reconcile once from the canonical operation log before treating a
        # previously visible representation as missing.
        _reconciled_registry(course_id)
        return _representation_and_spec(course_id, representation_id)


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
    if not demo_overrides_enabled(course_id):
        await get_course_or_404(course_id)
    try:
        registry, _representation, spec = await run_in_threadpool(
            _representation_and_spec_reconciled,
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
    impact = representation_edit_impact(
        registry,
        spec,
        unit_id=body.unit_id,
        field=body.field,
        semantic_change=classification.get("semantic_change"),
    )
    return {"status": "preview", **classification, "impact": impact}


@router.post("/{representation_id}/edits/apply")
async def apply_teaching_representation_edit(
    course_id: str,
    representation_id: str,
    body: ApplyRepresentationEditRequest,
    request: Request,
) -> dict:
    user_id = require_user_id(request.headers.get("X-User-Id"))
    if not demo_overrides_enabled(course_id):
        await get_course_or_404(course_id)
    try:
        registry, representation, spec = await run_in_threadpool(
            _representation_and_spec_reconciled,
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
    impact = representation_edit_impact(
        registry,
        spec,
        unit_id=body.unit_id,
        field=body.field,
        semantic_change=classification.get("semantic_change"),
    )
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
        body.field in {"key_message", "learning_objective"}
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
            "reason": "当前教学材料承载正式教学意图，确认后回写课程目标真源并精准联动相关表达。",
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
        try:
            text_patch = build_course_text_patch(
                block.payload,
                before=before_text,
                after=after_text,
            )
            next_payload = apply_course_text_patch_preview(block.payload, text_patch)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={
                "code": "course_source_span_conflict",
                "message": str(exc),
            }) from exc
        target_ids = [block_id]
        scope = "block"
        items = [{
            "block_id": block_id,
            "before": {
                "block_id": block_id,
                "payload": deepcopy(block.payload),
                "block_revision": block.internal_revision,
            },
            "after": {
                "payload": next_payload,
                "patch": text_patch,
            },
            "expected_block_revision": block.internal_revision,
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
            "source_document_revision": document.document_revision,
            "base_revision_vector": {
                key: value
                for key, value in revision_vector_for_document(document).revisions.items()
                if key in source_keys
            },
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


@router.get("/{representation_id}/assets/{asset_id}")
async def get_teaching_slide_asset(
    course_id: str,
    representation_id: str,
    asset_id: str,
    request: Request,
) -> FileResponse:
    """Serve only immutable assets referenced by the requested slide version."""
    payload = await get_teaching_representation_spec(course_id, representation_id, request)
    representation = payload["representation"]
    if representation["representation_type"] != "slide_deck":
        raise HTTPException(status_code=409, detail="Only slide decks have visual assets")
    content = (payload["spec"].get("payload") or {}).get("content") or {}
    asset_manifest = {
        str(item.get("asset_id") or ""): item
        for item in content.get("visual_asset_manifest") or []
    }
    asset = asset_manifest.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Slide visual asset not found")
    try:
        stored = slide_asset_repository.get(asset_id)
        path = slide_asset_repository.resolve(asset_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Slide visual asset is unavailable") from exc
    if stored is None or stored.course_id != course_id or stored.sha256 != str(asset.get("sha256") or ""):
        raise HTTPException(status_code=409, detail="Slide visual asset manifest mismatch")
    return FileResponse(
        path,
        media_type=stored.mime_type,
        filename=stored.filename,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": f'"{stored.sha256}"',
        },
    )


@router.get("/{representation_id}/export.pptx")
async def export_teaching_slide_deck(
    course_id: str,
    representation_id: str,
    request: Request,
    theme: str | None = None,
) -> FileResponse:
    payload = await get_teaching_representation_spec(course_id, representation_id, request)
    representation = payload["representation"]
    if representation["representation_type"] != "slide_deck":
        raise HTTPException(status_code=409, detail="Only slide decks can be exported to pptx")
    from teaching_representations import TeachingRepresentationSpec

    spec = TeachingRepresentationSpec.model_validate(payload["spec"])
    content = spec.payload.get("content") or {}
    resolved_theme = (
        str(content.get("theme") or "qizhi-classroom")
        if content.get("schema_version") in {
            "slide_deck_v3",
            "slide_deck_v4",
            "slide_deck_v5",
        }
        else str(theme or content.get("theme") or "qingfeng-classroom")
    )
    try:
        validate_theme(resolved_theme)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_slide_theme",
            "message": str(exc),
        }) from exc
    output_path = Path(DATA_DIR) / "teaching_exports" / f"{representation_id}-{spec.revision}-{resolved_theme}.pptx"
    try:
        await run_in_threadpool(export_slide_deck_pptx, spec, output_path, theme=resolved_theme)
    except SlideDeckQualityError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "slide_export_quality_blocked",
            "message": str(exc),
            "blockers": exc.report["blockers"],
            "warnings": exc.report["warnings"],
        }) from exc
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
