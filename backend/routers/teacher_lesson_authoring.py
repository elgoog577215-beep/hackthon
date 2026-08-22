from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from dependencies import (
    get_teacher_lesson_authoring_repository,
    require_task_manager,
)
from learner_context import resolve_user_id
from material_storage import MaterialStorageError, material_repository
from task_manager import TaskManager
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    extract_uploaded_pptx_evidence,
    lesson_plan_ppt_source,
    lesson_scope,
    teacher_lesson_deck_to_structured_slide_deck,
    teacher_lesson_v6_source,
)
from teacher_course_space import teacher_course_space_repository
from slide_deck_renderer import export_structured_slide_deck
from representation_compiler import export_slide_deck_pptx
from representation_edits import (
    classify_representation_edit,
    representation_edit_impact,
)
from slide_ai_planning_v6 import (
    build_ai_base_visual_planner_v2,
)
from slide_deck_v6_orchestrator import (
    SlideDeckV6CandidateRepository,
    SlideDeckV6Orchestrator,
    V6BuildError,
)
from teaching_representations import (
    TeachingRepresentationSpec,
    teaching_representation_repository,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1
from course_document import stable_hash
from slide_deck_v6 import SlideDeckV6


router = APIRouter(prefix="/teacher", tags=["teacher-lesson-authoring"])
_background_jobs: set[asyncio.Task] = set()


class GenerateLessonPlanRequest(BaseModel):
    request_id: str = Field(default="", max_length=160)
    source_package_id: str = Field(default="", max_length=160)
    source_asset_id: str = Field(default="", max_length=160)
    requirements: str = Field(default="", max_length=4000)
    material_asset_ids: list[str] = Field(default_factory=list, max_length=24)


class SaveLessonPlanDraftRequest(BaseModel):
    plan: dict[str, Any]
    source_outline_revision_id: str = ""


class ConfirmLessonPlanRequest(BaseModel):
    revision_id: str


class CreateLessonPlanCandidateRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    section_node_id: str = ""
    base_revision_id: str


class ResolveLessonPlanCandidateRequest(BaseModel):
    accept: bool


class GenerateLessonPptRequest(BaseModel):
    request_id: str = Field(default="", max_length=160)
    source_revision_id: str


class SaveLessonPptDraftRequest(BaseModel):
    deck: dict[str, Any]
    source_revision_id: str


class CreateLessonPptCandidateRequest(BaseModel):
    asset_id: str
    base_revision_id: str
    instruction: str = Field(min_length=1, max_length=2000)
    slide_indexes: list[int] = Field(default_factory=list)


class ResolveLessonPptCandidateRequest(BaseModel):
    accept: bool


class TeacherLessonV6BuildRequest(BaseModel):
    mode: str = "teaching"
    theme: str = "qizhi-classroom"
    force_rebuild: bool = False


class TeacherLessonRepresentationEditRequest(BaseModel):
    unit_id: str
    field: str
    before: Any = None
    after: Any = None
    semantic_intent: bool = False


class TeacherLessonApplyRepresentationEditRequest(TeacherLessonRepresentationEditRequest):
    decision: str = "representation_only"


def _raise(exc: TeacherLessonAuthoringError) -> None:
    status = 404 if exc.code.endswith("not_found") else 409
    raise HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": str(exc), **exc.details},
    ) from exc


def _source_course(tm: TaskManager, course_id: str) -> dict[str, Any]:
    source = tm.get_generation_workspace_course(course_id)
    if not isinstance(source, dict):
        preview = tm.get_generation_preview(course_id)
        source = preview if isinstance(preview, dict) else None
    if not isinstance(source, dict):
        raw = tm.storage.load_course(course_id) if tm.storage else None
        source = raw if isinstance(raw, dict) else None
    if not isinstance(source, dict):
        raise TeacherLessonAuthoringError("course_not_found", "课程不存在或没有可用大纲。")
    return deepcopy(source)


def _lesson_projection(
    source: dict[str, Any],
    repository: TeacherLessonAuthoringRepository,
) -> list[dict[str, Any]]:
    course_id = str(source.get("course_id") or "")
    assets = repository.view(course_id).get("lessons") or {}
    nodes = [item for item in source.get("nodes") or [] if isinstance(item, dict)]
    lessons = [
        item for item in nodes
        if int(item.get("node_level") or 0) == 1
        and str(item.get("parent_node_id") or "").lower() in {"", "root"}
    ]
    result = []
    for index, lesson in enumerate(lessons, start=1):
        lesson_id = str(lesson.get("node_id") or "")
        sections = [
            item for item in nodes
            if str(item.get("parent_node_id") or "") == lesson_id
        ]
        asset = assets.get(lesson_id) if isinstance(assets, dict) else None
        result.append({
            "lesson_unit_id": lesson_id,
            "number": index,
            "title": str(lesson.get("node_name") or f"第{index}讲"),
            "duration_minutes": int(
                lesson.get("duration_minutes")
                or (source.get("teacher_course_brief") or {}).get("lesson_duration_minutes")
                or 45
            ),
            "sections": [
                {
                    "section_node_id": str(section.get("node_id") or ""),
                    "title": str(section.get("node_name") or ""),
                }
                for section in sections
            ],
            "plan": deepcopy(asset) if isinstance(asset, dict) else {
                "lesson_unit_id": lesson_id,
                "working_revision_id": "",
                "confirmed_revision_id": "",
                "source_state": "current",
                "revisions": [],
                "ppt_assets": [],
            },
        })
    return result


def _plan_revision(
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    revision_id: str,
) -> dict[str, Any]:
    lesson = repository.lesson(course_id, lesson_unit_id)
    revision = next(
        (
            item for item in lesson.get("revisions") or []
            if isinstance(item, dict) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if not isinstance(revision, dict):
        raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案修订不存在。")
    return revision


def _ppt_asset_revision(
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
    asset_id: str,
    revision_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lesson = repository.lesson(course_id, lesson_unit_id)
    asset = next(
        (
            item for item in lesson.get("ppt_assets") or []
            if isinstance(item, dict) and item.get("asset_id") == asset_id
        ),
        None,
    )
    if not isinstance(asset, dict):
        raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 PPT 不存在。")
    revision = next(
        (
            item for item in asset.get("revisions") or []
            if isinstance(item, dict) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if not isinstance(revision, dict):
        raise TeacherLessonAuthoringError("lesson_ppt_revision_not_found", "PPT 修订不存在。")
    return asset, revision


def _teacher_v6_source(
    tm: TaskManager,
    repository: TeacherLessonAuthoringRepository,
    course_id: str,
    lesson_unit_id: str,
):
    source = _source_course(tm, course_id)
    lesson = repository.lesson(course_id, lesson_unit_id)
    revision_id = str(lesson.get("working_revision_id") or "")
    revision = _plan_revision(repository, course_id, lesson_unit_id, revision_id)
    document, course_view, synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id=lesson_unit_id,
        plan_revision=revision,
    )
    return document, course_view, synthetic_id, lesson, revision


def _teacher_v6_registry_payload(synthetic_id: str) -> dict[str, Any]:
    registry = teaching_representation_repository.load(synthetic_id)
    payload = registry.model_dump(mode="json")
    slide_representations = [
        item for item in registry.representations
        if item.representation_type == "slide_deck" and item.status != "archived"
    ]
    selected = slide_representations[0] if slide_representations else None
    spec = next(
        (item for item in registry.specs if selected and item.spec_id == selected.spec_id),
        None,
    )
    content = (spec.payload.get("content") if spec else None) or {}
    payload.update({
        "slide_deck_target_schema": "slide_deck_v6",
        "slide_deck_candidate_schema": str(content.get("schema_version") or ""),
        "slide_deck_published_schema": str(content.get("schema_version") or ""),
        "slide_deck_candidate_status": str(content.get("candidate_status") or content.get("status") or ""),
    })
    return payload


async def _teacher_v6_story_planner(request: dict[str, Any]) -> dict[str, Any]:
    """Produce a source-faithful V6 story batch for teacher lesson plans.

    The shared V6 validator still owns every layout/capacity/fidelity gate. This
    adapter only avoids asking the provider to invent audience copy for content
    that already exists as a structured teacher plan.
    """
    pages: list[dict[str, Any]] = []
    for index, unit in enumerate(request.get("teaching_units") or [], start=1):
        allowed = [str(item) for item in unit.get("allowed_template_layout_ids") or []]
        preferred_suffixes = (
            ["/practice-feedback", "/content-stack"]
            if str(unit.get("teaching_intent") or "") == "practice_feedback"
            else ["/content-stack", "/practice-feedback", "/chapter-entry"]
        )
        layout = next(
            (
                item for suffix in preferred_suffixes for item in allowed
                if item.endswith(suffix)
            ),
            allowed[0] if allowed else "",
        )
        source_text = " ".join(str(unit.get("source_text") or "").split())
        purposes = (unit.get("teaching_plan_context") or {}).get("teaching_purposes") or []
        title_source = str(
            (purposes[0] if purposes else "") or source_text or f"教学环节 {index}"
        )
        title = title_source[:34]
        pages.append({
            "page_id": f"{request.get('chapter_id')}-teacher-{index}",
            "teaching_unit_id": str(unit.get("teaching_unit_id") or ""),
            "template_layout_id": layout,
            "title": title,
            # Empty means "materialize the complete bound source blocks" in
            # the V6 compiler; it is not an empty page or a quality bypass.
            "summary": "",
            "source_block_ids": list(unit.get("primary_block_ids") or []),
        })
    return {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": str(request.get("chapter_id") or ""),
        "provider": "teacher-plan-adapter",
        "model": "source-faithful-deterministic",
        "attempts": 1,
        "pages": pages,
    }


@router.get("/courses/{course_id}/lesson-authoring")
async def get_lesson_authoring_view(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        outline_revision = str(
            source.get("blueprint_revision_id")
            or (source.get("course_knowledge_scope_contract") or {}).get("revision_id")
            or ""
        )
        if outline_revision:
            repository.set_outline(course_id, outline_revision)
        return {
            "schema_version": "teacher_lesson_authoring_view_v1",
            "course_id": course_id,
            "outline_revision_id": outline_revision,
            "lessons": _lesson_projection(source, repository),
            "jobs": list((repository.view(course_id).get("jobs") or {}).values()),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/source")
async def get_teacher_lesson_v6_source(
    course_id: str,
    lesson_unit_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        document, _course_view, _synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        return {
            "schema_version": "course_document_envelope_v1",
            "course_id": course_id,
            "course_name": document.title,
            "source_format": "canonical",
            "document": document.model_dump(mode="json"),
            "migration": {"required": False},
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6")
async def get_teacher_lesson_v6_registry(
    course_id: str,
    lesson_unit_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        return {"registry": _teacher_v6_registry_payload(synthetic_id)}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/spec")
async def get_teacher_lesson_v6_spec(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        if representation is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        spec = next((item for item in registry.specs if item.spec_id == representation.spec_id), None)
        if spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_revision_not_found", "本讲 V6 PPT 规格不存在。")
        return {
            "representation": representation.model_dump(mode="json"),
            "spec": spec.model_dump(mode="json"),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/build/stream")
async def build_teacher_lesson_v6(
    course_id: str,
    lesson_unit_id: str,
    body: TeacherLessonV6BuildRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        document, course_view, synthetic_id, lesson, revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
    source_plan_revision = str(revision.get("revision_id") or lesson.get("working_revision_id") or "")
    task_id = f"teacher-v6-{uuid.uuid4().hex}"
    template = compile_builtin_template_layout_contract_v1(body.theme)
    orchestrator = SlideDeckV6Orchestrator(
        representation_repository=teaching_representation_repository,
        candidate_repository=SlideDeckV6CandidateRepository(repository.root / "v6_candidates"),
        progress_root=repository.root / "v6_progress",
    )

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        sequence = 0

        async def progress(payload: dict[str, object]) -> None:
            await queue.put({
                "event": "slide_build_progress_v2",
                "progress": int(payload.get("percent") or 0),
                "stage": str(payload.get("stage") or "building"),
                "message": "正在使用原 V6 引擎生成本讲 PPT",
                "slide_build_progress_v2": deepcopy(payload),
                "target_schema": "slide_deck_v6",
            })

        def source_revision_provider() -> str:
            current = repository.lesson(course_id, lesson_unit_id)
            return (
                str(document.document_revision or "")
                if current.get("working_revision_id") == source_plan_revision
                else ""
            )

        async def run() -> None:
            try:
                result = await orchestrator.build(
                    task_id=task_id,
                    document=document,
                    course_data=course_view,
                    mode=body.mode,
                    theme=body.theme,
                    story_planner=_teacher_v6_story_planner,
                    visual_planner=build_ai_base_visual_planner_v2(),
                    source_revision_provider=source_revision_provider,
                    template_contract=template,
                    template_digest_provider=lambda: template.template_digest,
                    publish_result=True,
                    progress_callback=progress,
                )
                repository.bind_v6_ppt_revision(
                    course_id,
                    lesson_unit_id,
                    source_lesson_plan_revision_id=source_plan_revision,
                    synthetic_course_id=synthetic_id,
                    representation_id=str(result.get("representation_id") or ""),
                    spec_id=str(result.get("spec_id") or ""),
                    candidate_status=str(result.get("candidate_status") or result.get("status") or ""),
                )
                await queue.put({
                    "event": "build_complete",
                    "progress": 100,
                    "stage": "complete",
                    "target_schema": "slide_deck_v6",
                    "quality": result.get("quality") or {},
                    "build": result,
                    "registry": _teacher_v6_registry_payload(synthetic_id),
                })
            except V6BuildError as exc:
                failure = exc.failure.model_dump(mode="json")
                await queue.put({
                    "event": "build_failed",
                    "progress": 100,
                    "stage": failure.get("stage") or "failed",
                    **failure,
                })
            except Exception as exc:
                await queue.put({
                    "event": "build_failed",
                    "progress": 100,
                    "stage": "failed",
                    "code": "teacher_lesson_v6_failed",
                    "message": str(exc),
                    "retryable": True,
                })
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run())
        while True:
            payload = await queue.get()
            if payload is None:
                break
            sequence += 1
            name = str(payload.get("event") or "message")
            yield f"id: {sequence}\nevent: {name}\ndata: {json.dumps({**payload, 'sequence': sequence}, ensure_ascii=False)}\n\n"
        await worker

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/export.pptx")
async def export_teacher_lesson_v6(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next(
            (item for item in registry.representations if item.representation_id == representation_id),
            None,
        )
        spec = next(
            (item for item in registry.specs if representation and item.spec_id == representation.spec_id),
            None,
        )
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        output = repository.root / "exports" / f"{synthetic_id}-{representation_id}-{spec.revision}.pptx"
        output.parent.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(export_slide_deck_pptx, spec, output, theme="qizhi-classroom")
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{lesson_unit_id}-V6课堂课件.pptx",
        )
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/edits/preview")
async def preview_teacher_lesson_v6_edit(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: TeacherLessonRepresentationEditRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next((item for item in registry.representations if item.representation_id == representation_id), None)
        spec = next((item for item in registry.specs if representation and item.spec_id == representation.spec_id), None)
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
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
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt-v6/{representation_id}/edits/apply")
async def apply_teacher_lesson_v6_edit(
    course_id: str,
    lesson_unit_id: str,
    representation_id: str,
    body: TeacherLessonApplyRepresentationEditRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    if body.decision != "representation_only":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "teacher_semantic_edit_requires_lesson_plan",
                "message": "语义修改请回到本讲教案；PPT 工作台只保存表达层修改。",
            },
        )
    try:
        _document, _course_view, synthetic_id, _lesson, _revision = _teacher_v6_source(
            tm, repository, course_id, lesson_unit_id
        )
        registry = teaching_representation_repository.load(synthetic_id)
        representation = next((item for item in registry.representations if item.representation_id == representation_id), None)
        spec = next((item for item in registry.specs if representation and item.spec_id == representation.spec_id), None)
        if representation is None or spec is None:
            raise TeacherLessonAuthoringError("lesson_ppt_not_found", "本讲 V6 PPT 不存在。")
        payload = deepcopy(spec.payload)
        content = payload.get("content") or {}
        pages = content.get("pages") if isinstance(content.get("pages"), list) else None
        if pages is None or content.get("schema_version") != "slide_deck_v6":
            raise HTTPException(
                status_code=422,
                detail={"code": "teacher_v6_edit_unsupported", "message": "当前 V6 规格不支持页面编辑。"},
            )
        page = next(
            (item for item in pages if str(item.get("page_id") or "") == body.unit_id),
            None,
        )
        if page is None:
            raise HTTPException(status_code=404, detail="V6 page not found")
        if body.field not in {"title", "subtitle", "key_message"}:
            raise HTTPException(
                status_code=422,
                detail={"code": "teacher_v6_edit_field_unsupported", "message": "当前字段请通过原 V6 专用编辑器处理。"},
            )
        page[body.field] = deepcopy(body.after)
        SlideDeckV6.model_validate({
            key: content[key]
            for key in SlideDeckV6.model_fields
            if key in content
        })
        now = datetime.now(timezone.utc).isoformat()
        spec_revision = stable_hash(payload, prefix="tsr_")
        edited_spec = TeachingRepresentationSpec(
            spec_id=stable_hash({
                "course_id": spec.course_id,
                "representation_type": spec.representation_type,
                "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
                "payload": payload,
            }, prefix="trs_"),
            course_id=spec.course_id,
            representation_type=spec.representation_type,
            source_bindings=spec.source_bindings,
            unit_bindings=spec.unit_bindings,
            payload=payload,
            revision=spec_revision,
            created_at=now,
            updated_at=now,
        )
        teaching_representation_repository.register_spec(edited_spec)
        edited_representation = representation.model_copy(deep=True)
        edited_representation.spec_id = edited_spec.spec_id
        edited_representation.semantic_fingerprint = stable_hash(content, prefix="sem_")
        edited_representation.render_fingerprint = stable_hash({
            "spec_revision": spec_revision,
            "renderer": "slide_deck_v6",
        }, prefix="rnd_")
        edited_representation.revision = stable_hash({
            "spec_revision": spec_revision,
            "source_revision_vector": edited_representation.source_revision_vector,
        }, prefix="rpr_")
        edited_representation.updated_at = now
        updated = teaching_representation_repository.register_representation(edited_representation)
        repository.bind_v6_ppt_revision(
            course_id,
            lesson_unit_id,
            source_lesson_plan_revision_id=str(_revision.get("revision_id") or ""),
            synthetic_course_id=synthetic_id,
            representation_id=edited_representation.representation_id,
            spec_id=edited_spec.spec_id,
            candidate_status=str(content.get("status") or content.get("candidate_status") or "v6_ready"),
        )
        return {"status": "applied_to_representation", "registry": updated.model_dump(mode="json")}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "teacher_v6_edit_quality_blocked", "message": str(exc)},
        ) from exc


@router.get("/courses/{course_id}/knowledge-evidence")
async def get_lesson_knowledge_evidence(
    course_id: str,
    lesson_unit_id: str = "",
    tm: TaskManager = Depends(require_task_manager),
):
    try:
        source = _source_course(tm, course_id)
        nodes = [item for item in source.get("nodes") or [] if isinstance(item, dict)]
        if lesson_unit_id:
            scope = lesson_scope(source, lesson_unit_id)
            section_ids = {str(item.get("node_id") or "") for item in scope["sections"]}
            nodes = [item for item in nodes if str(item.get("node_id") or "") in section_ids]
        points: list[dict[str, Any]] = []
        for node in nodes:
            for group in node.get("knowledge_structure") or []:
                if not isinstance(group, dict):
                    continue
                for point in group.get("knowledge_points") or []:
                    if not isinstance(point, dict):
                        continue
                    sources = point.get("source_refs") or point.get("evidence_refs") or []
                    if isinstance(sources, str):
                        sources = [sources]
                    points.append({
                        "section_node_id": str(node.get("node_id") or ""),
                        "section_title": str(node.get("node_name") or ""),
                        "name": str(point.get("name") or ""),
                        "statement": str(point.get("statement") or point.get("description") or ""),
                        "sources": [str(item) for item in sources if str(item).strip()],
                        "conflict": bool(point.get("conflict") or point.get("needs_manual_review")),
                    })
        return {
            "schema_version": "teacher_lesson_knowledge_evidence_v1",
            "course_id": course_id,
            "lesson_unit_id": lesson_unit_id,
            "points": points,
            "conflict_count": sum(1 for item in points if item["conflict"]),
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/generate", status_code=202)
async def generate_lesson_plan(
    course_id: str,
    lesson_unit_id: str,
    body: GenerateLessonPlanRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        source = _source_course(tm, course_id)
        lesson_scope(source, lesson_unit_id)
        source_evidence: list[dict[str, Any]] = []
        source_filename = ""
        actor = resolve_user_id(request.headers.get("X-User-Id"))
        if bool(body.source_package_id) != bool(body.source_asset_id):
            raise TeacherLessonAuthoringError(
                "uploaded_ppt_source_incomplete",
                "旧课件来源信息不完整。",
            )
        if body.source_package_id and body.source_asset_id:
            try:
                package = teacher_course_space_repository.load_owned(
                    body.source_package_id,
                    actor,
                )
                source_asset, source_path = teacher_course_space_repository.source_file(
                    package,
                    body.source_asset_id,
                )
            except (FileNotFoundError, MaterialStorageError) as exc:
                raise TeacherLessonAuthoringError(
                    "uploaded_ppt_source_not_found",
                    "旧课件来源不存在或无权访问。",
                ) from exc
            if str(package.get("course_id") or "") != course_id:
                raise TeacherLessonAuthoringError(
                    "uploaded_ppt_course_mismatch",
                    "旧课件不属于当前课程。",
                )
            source_filename = str(source_asset.get("filename") or "")
            source_evidence = await run_in_threadpool(
                extract_uploaded_pptx_evidence,
                source_path,
                asset_id=body.source_asset_id,
            )
        selected_material_ids = list(dict.fromkeys(
            str(value or "").strip()
            for value in body.material_asset_ids
            if str(value or "").strip()
        ))
        if selected_material_ids:
            allowed_material_ids: set[str] = set()
            for summary in teacher_course_space_repository.list_owned(actor, course_id):
                try:
                    owned_package = teacher_course_space_repository.load_owned(
                        str(summary.get("package_id") or ""), actor
                    )
                except (FileNotFoundError, MaterialStorageError):
                    continue
                allowed_material_ids.update(
                    str(item.get("material_asset_id") or "")
                    for item in owned_package.get("assets") or []
                    if str(item.get("material_asset_id") or "")
                )
            unknown_material_ids = sorted(set(selected_material_ids) - allowed_material_ids)
            if unknown_material_ids:
                raise TeacherLessonAuthoringError(
                    "lesson_material_source_not_found",
                    "部分已选资料不属于当前课程。",
                )
            for material_asset_id in selected_material_ids:
                for evidence in material_repository.load_evidence(material_asset_id):
                    if not isinstance(evidence, dict):
                        continue
                    source_evidence.append({
                        **evidence,
                        "asset_id": material_asset_id,
                        "source_kind": "course_material",
                    })
        outline_revision = str(
            source.get("blueprint_revision_id")
            or (source.get("course_knowledge_scope_contract") or {}).get("revision_id")
            or ""
        )
        repository.set_outline(course_id, outline_revision)
        job = repository.create_job(
            course_id,
            lesson_unit_id,
            request_id=body.request_id,
            source_outline_revision_id=outline_revision,
        )
        if source_evidence:
            job_source_kind = (
                "mixed_course_sources"
                if body.source_asset_id and selected_material_ids
                else "uploaded_ppt"
                if body.source_asset_id
                else "course_materials"
            )
            job = repository.update_job(
                course_id,
                str(job["id"]),
                source_asset_id=(body.source_asset_id or selected_material_ids[0]),
                source_package_id=body.source_package_id,
                source_filename=(
                    source_filename
                    or f"{len(selected_material_ids)} 份课程资料"
                ),
                source_kind=job_source_kind,
            )
        if job.get("status") in {"running", "completed", "completed_with_warnings"}:
            return {"job": job}

        service = TeacherLessonAuthoringService(repository)

        async def planner(
            course: dict[str, Any],
            lesson_id: str,
            on_progress,
        ) -> dict[str, Any]:
            scoped_course = deepcopy(course)
            normalized_requirements = body.requirements.strip()
            if normalized_requirements:
                scoped_course["requirements"] = normalized_requirements
                scoped_course.setdefault("metadata", {}).setdefault(
                    "teacher_lesson_requirements", {}
                )[lesson_id] = normalized_requirements
                for plan_key in ("course_plan", "course_outline"):
                    scoped_plan = scoped_course.get(plan_key)
                    if not isinstance(scoped_plan, dict):
                        continue
                    for chapter in scoped_plan.get("chapters") or []:
                        if not isinstance(chapter, dict):
                            continue
                        chapter_id = str(
                            chapter.get("node_id")
                            or chapter.get("chapter_id")
                            or ""
                        )
                        if chapter_id != lesson_id:
                            continue
                        chapter["teacher_requirements"] = normalized_requirements
                        for section in chapter.get("sections") or []:
                            if isinstance(section, dict):
                                section["teacher_requirements"] = normalized_requirements
            return await tm.course_service.prepare_teacher_lesson_plan(
                course_data=scoped_course,
                lesson_unit_id=lesson_id,
                on_phase=on_progress,
                source_evidence=source_evidence,
            )

        async def run() -> None:
            await service.run_plan_job(
                course_id=course_id,
                lesson_unit_id=lesson_unit_id,
                job_id=str(job["id"]),
                course_data=source,
                planner=planner,
            )

        task = asyncio.create_task(run())
        _background_jobs.add(task)
        task.add_done_callback(_background_jobs.discard)
        return {"job": {**job, "actor": actor}}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lesson-jobs/{job_id}")
async def get_lesson_job(
    course_id: str,
    job_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        return {"job": repository.get_job(course_id, job_id)}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.patch("/courses/{course_id}/lessons/{lesson_unit_id}/plan/draft")
async def save_lesson_plan_draft(
    course_id: str,
    lesson_unit_id: str,
    body: SaveLessonPlanDraftRequest,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        lesson = repository.save_plan_revision(
            course_id,
            lesson_unit_id,
            body.plan,
            source_outline_revision_id=body.source_outline_revision_id,
            generation_source="teacher_edit",
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"lesson": lesson}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/confirm")
async def confirm_lesson_plan(
    course_id: str,
    lesson_unit_id: str,
    body: ConfirmLessonPlanRequest,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        return {
            "lesson": repository.confirm_plan_revision(
                course_id,
                lesson_unit_id,
                body.revision_id,
            )
        }
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/ai-candidates")
async def create_lesson_plan_candidate(
    course_id: str,
    lesson_unit_id: str,
    body: CreateLessonPlanCandidateRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        lesson = repository.lesson(course_id, lesson_unit_id)
        if lesson.get("working_revision_id") != body.base_revision_id:
            raise TeacherLessonAuthoringError("lesson_plan_revision_conflict", "教案草稿已经变化，请重新打开后再优化。")
        revision = next(
            (
                item for item in lesson.get("revisions") or []
                if item.get("revision_id") == body.base_revision_id
            ),
            None,
        )
        if not isinstance(revision, dict):
            raise TeacherLessonAuthoringError("lesson_plan_revision_not_found", "教案草稿不存在。")
        optimized = await tm.course_service.optimize_teacher_lesson_plan(
            plan=deepcopy(revision.get("plan") or {}),
            instruction=body.instruction,
            section_node_id=body.section_node_id,
        )
        candidate = repository.save_ai_candidate(
            course_id,
            lesson_unit_id,
            base_revision_id=body.base_revision_id,
            instruction=body.instruction,
            section_node_id=body.section_node_id,
            plan=optimized["plan"],
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/plan/ai-candidates/{candidate_id}/resolve")
async def resolve_lesson_plan_candidate(
    course_id: str,
    lesson_unit_id: str,
    candidate_id: str,
    body: ResolveLessonPlanCandidateRequest,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        lesson = repository.resolve_ai_candidate(
            course_id,
            lesson_unit_id,
            candidate_id,
            accept=body.accept,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"lesson": lesson}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/generate", status_code=202)
async def generate_lesson_ppt(
    course_id: str,
    lesson_unit_id: str,
    body: GenerateLessonPptRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        revision = _plan_revision(
            repository,
            course_id,
            lesson_unit_id,
            body.source_revision_id,
        )
        lesson = repository.lesson(course_id, lesson_unit_id)
        if lesson.get("working_revision_id") != body.source_revision_id:
            raise TeacherLessonAuthoringError(
                "lesson_plan_revision_conflict",
                "教案草稿已经变化，请基于最新版本生成 PPT。",
            )
        source = lesson_plan_ppt_source(
            deepcopy(revision.get("plan") or {}),
            lesson_unit_id=lesson_unit_id,
            source_revision_id=body.source_revision_id,
        )
        job = repository.create_job(
            course_id,
            lesson_unit_id,
            job_type="teacher_lesson_ppt_generation",
            request_id=body.request_id,
            source_outline_revision_id=str(repository.view(course_id).get("outline_revision_id") or ""),
        )
        if job.get("status") in {"running", "completed", "completed_with_warnings"}:
            return {"job": job}
        service = TeacherLessonAuthoringService(repository)

        async def generator(ppt_source: dict[str, Any], on_progress) -> dict[str, Any]:
            return await tm.course_service.generate_teacher_lesson_ppt(
                source=ppt_source,
                on_phase=on_progress,
            )

        async def run() -> None:
            await service.run_ppt_job(
                course_id=course_id,
                lesson_unit_id=lesson_unit_id,
                job_id=str(job["id"]),
                source_revision_id=body.source_revision_id,
                source=source,
                generator=generator,
            )

        task = asyncio.create_task(run())
        _background_jobs.add(task)
        task.add_done_callback(_background_jobs.discard)
        return {"job": job}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.patch("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/draft")
async def save_lesson_ppt_draft(
    course_id: str,
    lesson_unit_id: str,
    body: SaveLessonPptDraftRequest,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        asset = repository.save_ppt_revision(
            course_id,
            lesson_unit_id,
            body.deck,
            source_lesson_plan_revision_id=body.source_revision_id,
            generation_source="teacher_edit",
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"asset": asset}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/ai-candidates")
async def create_lesson_ppt_candidate(
    course_id: str,
    lesson_unit_id: str,
    body: CreateLessonPptCandidateRequest,
    tm: TaskManager = Depends(require_task_manager),
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        asset, revision = _ppt_asset_revision(
            repository,
            course_id,
            lesson_unit_id,
            body.asset_id,
            body.base_revision_id,
        )
        if asset.get("working_revision_id") != body.base_revision_id:
            raise TeacherLessonAuthoringError("lesson_ppt_revision_conflict", "PPT 草稿已经变化，请重新打开后再优化。")
        optimized = await tm.course_service.optimize_teacher_lesson_ppt(
            deck=deepcopy(revision.get("deck") or {}),
            instruction=body.instruction,
            slide_indexes=body.slide_indexes,
        )
        candidate = repository.save_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            asset_id=body.asset_id,
            base_revision_id=body.base_revision_id,
            instruction=body.instruction,
            slide_indexes=optimized.get("slide_indexes") or [],
            deck=optimized["deck"],
        )
        return {"candidate": candidate}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.post("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/ai-candidates/{candidate_id}/resolve")
async def resolve_lesson_ppt_candidate(
    course_id: str,
    lesson_unit_id: str,
    candidate_id: str,
    body: ResolveLessonPptCandidateRequest,
    request: Request,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        asset = repository.resolve_ppt_ai_candidate(
            course_id,
            lesson_unit_id,
            candidate_id,
            accept=body.accept,
            actor=resolve_user_id(request.headers.get("X-User-Id")),
        )
        return {"asset": asset}
    except TeacherLessonAuthoringError as exc:
        _raise(exc)


@router.get("/courses/{course_id}/lessons/{lesson_unit_id}/ppt/export.pptx")
async def export_lesson_ppt(
    course_id: str,
    lesson_unit_id: str,
    asset_id: str,
    revision_id: str,
    repository: TeacherLessonAuthoringRepository = Depends(
        get_teacher_lesson_authoring_repository
    ),
):
    try:
        _asset, revision = _ppt_asset_revision(
            repository,
            course_id,
            lesson_unit_id,
            asset_id,
            revision_id,
        )
        structured = teacher_lesson_deck_to_structured_slide_deck(
            deepcopy(revision.get("deck") or {}),
            source_revision_id=str(revision.get("source_lesson_plan_revision_id") or ""),
        )
        export_dir = repository.root / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output = export_dir / f"{course_id}-{lesson_unit_id}-{revision_id}.pptx"
        await run_in_threadpool(
            export_structured_slide_deck,
            structured,
            output,
            require_quality=False,
            theme="qingfeng-classroom",
        )
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{lesson_unit_id}-课堂课件.pptx",
        )
    except TeacherLessonAuthoringError as exc:
        _raise(exc)
