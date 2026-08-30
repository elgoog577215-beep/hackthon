"""Teacher-confirmed course baseline editing and AI-assisted drafts."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from generation_streaming import structured_generation_stream
from pydantic import BaseModel, Field

from ai_service import ai_service
from ai_teacher_state import ai_teacher_repository
from course_baseline import (
    baseline_changed_fields,
    baseline_revision,
    build_ai_baseline_prompt,
    build_baseline_mutation,
    build_course_information_mutation,
    confirmed_generation_request,
    course_information_changed_fields,
    course_information_revision,
    course_information_snapshot,
    course_information_versions,
    merge_ai_baseline_draft,
    normalize_course_information,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from dependencies import get_course_document_repository
from learner_context import resolve_user_id
from models import CourseGenerationRequest


router = APIRouter(prefix="/courses", tags=["course_baseline"])


class CourseBaselineUpdateRequest(BaseModel):
    generation_request: CourseGenerationRequest
    expected_revision: int = Field(ge=0)
    expected_document_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)
    source: Literal["manual", "ai_draft"] = "manual"
    draft_id: str = Field(default="", max_length=200)


class CourseBaselineDraftRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=160)
    through_message_id: str = Field(default="", max_length=160)


class CourseProfileInput(BaseModel):
    english_name: str = Field(default="", max_length=200)
    course_code: str = Field(default="", max_length=64)
    course_goal: str = Field(default="", max_length=5000)
    default_location: str = Field(default="", max_length=200)
    target_grade: str = Field(default="", max_length=500)
    course_category: str = Field(default="", max_length=100)
    target_major: str = Field(default="", max_length=200)
    credits: float | None = Field(default=None, ge=0, le=100)
    weekly_hours: float | None = Field(default=None, ge=0, le=100)
    total_hours: int | None = Field(default=None, ge=1, le=1000)
    prerequisite_courses: str = Field(default="", max_length=1000)
    weekday: str = Field(default="", max_length=100)
    periods: str = Field(default="", max_length=500)
    course_period_minutes: Literal[45] = 45
    active_week_start: int = Field(default=1, ge=1, le=30)
    active_week_end: int = Field(default=16, ge=1, le=30)
    schedule_slots: list[dict[str, int]] = Field(default_factory=list, max_length=91)
    planned_lecture_count: int | None = Field(default=None, ge=1, le=1000)
    assessment_method: str = Field(default="", max_length=500)
    course_intro: str = Field(default="", max_length=3000)
    teaching_goals: str = Field(default="", max_length=5000)


class CourseInformationInput(BaseModel):
    course_name: str = Field(min_length=1, max_length=200)
    academic_year: str = Field(default="", max_length=30)
    term: str = Field(default="", max_length=30)
    course_profile: CourseProfileInput
    generation_request: CourseGenerationRequest


class CourseInformationUpdateRequest(BaseModel):
    information: CourseInformationInput
    expected_revision: int = Field(ge=0)
    expected_document_revision: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)
    source: Literal["manual", "restore"] = "manual"
    restore_revision: int | None = Field(default=None, ge=0)


def _assert_teacher_owner(course: dict[str, Any], actor_id: str) -> None:
    owner_id = str(course.get("owner_id") or "").strip()
    if owner_id and owner_id != actor_id:
        raise HTTPException(status_code=404, detail="Course not found")


@router.get("/{course_id}/course-information")
async def get_course_information(
    course_id: str,
    request: Request,
    repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    course = repository.load_course_view(course_id)
    actor_id = resolve_user_id(request.headers.get("X-User-Id"))
    _assert_teacher_owner(course, actor_id)
    return {
        "course_id": course_id,
        "revision": course_information_revision(course),
        "document_revision": str(course.get("course_document_revision") or ""),
        "information": course_information_snapshot(course),
        "versions": course_information_versions(course),
    }


@router.put("/{course_id}/course-information")
async def update_course_information(
    course_id: str,
    body: CourseInformationUpdateRequest,
    request: Request,
    repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    course = repository.load_course_view(course_id)
    actor_id = resolve_user_id(request.headers.get("X-User-Id"))
    _assert_teacher_owner(course, actor_id)
    if body.information.course_name.strip() != str(course.get("course_name") or "").strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "course_name_read_only"},
        )
    submitted = body.information.model_dump(mode="json")
    submitted["generation_request"] = confirmed_generation_request(
        body.information.generation_request,
    )
    information = normalize_course_information(course, submitted)
    changed_fields = course_information_changed_fields(
        course_information_snapshot(course),
        information,
    )
    if not changed_fields:
        return {
            "status": "unchanged",
            "course_id": course_id,
            "revision": course_information_revision(course),
            "document_revision": str(course.get("course_document_revision") or ""),
            "information": course_information_snapshot(course),
            "versions": course_information_versions(course),
            "changed_fields": [],
            "downstream_action": "none",
        }
    try:
        receipt = await repository.apply_metadata_command(
            course_id,
            expected_document_revision=body.expected_document_revision,
            operation={
                "command_id": body.idempotency_key,
                "operation": "update_course_information",
                "reason": "teacher_confirmed_course_information",
                "actor": actor_id,
            },
            mutation=build_course_information_mutation(
                expected_revision=body.expected_revision,
                information=information,
                source=body.source,
                restore_revision=body.restore_revision,
            ),
        )
    except ValueError as exc:
        if str(exc) == "course_information_revision_changed":
            current = repository.load_course_view(course_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "course_information_revision_changed",
                    "current_revision": course_information_revision(current),
                    "information": course_information_snapshot(current),
                    "versions": course_information_versions(current),
                },
            ) from exc
        raise
    except CourseDocumentConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "course_document_revision_changed", "message": str(exc)},
        ) from exc

    updated = repository.load_course_view(course_id)
    return {
        "status": "confirmed",
        "course_id": course_id,
        "revision": course_information_revision(updated),
        "document_revision": str(updated.get("course_document_revision") or ""),
        "information": course_information_snapshot(updated),
        "versions": course_information_versions(updated),
        "changed_fields": changed_fields,
        "downstream_action": "none",
        "receipt": receipt,
    }


@router.put("/{course_id}/generation-request")
async def update_course_baseline(
    course_id: str,
    body: CourseBaselineUpdateRequest,
    request: Request,
    repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    course = repository.load_course_view(course_id)
    actor_id = resolve_user_id(request.headers.get("X-User-Id"))
    _assert_teacher_owner(course, actor_id)
    generation_request = confirmed_generation_request(body.generation_request)
    before = course.get("generation_request") or {}
    changed_fields = baseline_changed_fields(before, generation_request)
    try:
        receipt = await repository.apply_metadata_command(
            course_id,
            expected_document_revision=body.expected_document_revision,
            operation={
                "command_id": body.idempotency_key,
                "operation": "update_course_generation_request",
                "reason": "teacher_confirmed_course_baseline",
                "actor": actor_id,
            },
            mutation=build_baseline_mutation(
                expected_revision=body.expected_revision,
                generation_request=generation_request,
                source=body.source,
                draft_id=body.draft_id,
            ),
        )
    except ValueError as exc:
        if str(exc) == "course_baseline_revision_changed":
            current = repository.load_course_view(course_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "course_baseline_revision_changed",
                    "current_revision": baseline_revision(current),
                    "generation_request": current.get("generation_request") or {},
                },
            ) from exc
        raise
    except CourseDocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    updated = repository.load_course_view(course_id)
    return {
        "status": "confirmed",
        "course_id": course_id,
        "revision": baseline_revision(updated),
        "generation_request": updated.get("generation_request") or {},
        "changed_fields": changed_fields,
        "downstream_action": "none",
        "receipt": receipt,
    }


@router.post("/{course_id}/generation-request/draft")
@structured_generation_stream(
    stage="course_baseline_draft",
    started_message="已开始整理对话中的课程设定。",
    waiting_message="AI 正在生成可确认的课程信息草案。",
)
async def draft_course_baseline_from_conversation(
    course_id: str,
    body: CourseBaselineDraftRequest,
    request: Request,
    repository: CourseDocumentRepository = Depends(get_course_document_repository),
):
    course = repository.load_course_view(course_id)
    actor_id = resolve_user_id(request.headers.get("X-User-Id"))
    _assert_teacher_owner(course, actor_id)
    conversation = await run_in_threadpool(
        ai_teacher_repository.get_conversation,
        actor_id,
        course_id,
        body.conversation_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    prompt = build_ai_baseline_prompt(
        course,
        conversation,
        through_message_id=body.through_message_id,
    )
    try:
        response = await ai_service._call_llm(
            prompt,
            system_prompt=(
                "你是课程定调信息提取器。严格依据对话，只返回符合给定结构的 JSON。"
            ),
            use_fast_model=True,
            enable_thinking=False,
            raise_on_failure=True,
        )
        extracted = ai_service._extract_json(str(response or "")) or {}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "course_baseline_draft_unavailable"},
        ) from exc
    if not isinstance(extracted, dict) or not isinstance(extracted.get("updates"), dict):
        raise HTTPException(
            status_code=502,
            detail={"code": "course_baseline_draft_invalid"},
        )
    source_message_ids = [
        str(item.get("message_id") or "")
        for item in conversation.get("messages") or []
        if item.get("role") in {"user", "assistant"}
    ]
    if body.through_message_id and body.through_message_id in source_message_ids:
        source_message_ids = source_message_ids[:source_message_ids.index(body.through_message_id) + 1]
    return merge_ai_baseline_draft(
        course,
        extracted,
        conversation_id=body.conversation_id,
        source_message_ids=[item for item in source_message_ids if item],
    )


__all__ = ["router"]
