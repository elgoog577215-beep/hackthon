from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from course_document import document_from_generation_draft
from course_repository import CourseDocumentConflict
from dependencies import get_course_document_repository, require_task_manager
from learner_context import resolve_user_id
from task_manager import TaskManager
from teaching_plan_workbench import TeachingPlanWorkbenchError, TeachingPlanWorkbenchService


router = APIRouter(prefix="/teacher", tags=["teacher-authoring"])


class TeacherAuthoringConfirmRequest(BaseModel):
    confirm: bool = False
    source_task_id: str = ""


@router.post("/courses/{course_id}/authoring/confirm-generation-preview")
async def confirm_generation_preview_for_teacher_authoring(
    course_id: str,
    body: TeacherAuthoringConfirmRequest,
    request: Request,
    tm: TaskManager = Depends(require_task_manager),
    repository=Depends(get_course_document_repository),
):
    """Promote a terminal generation preview into a teacher working source.

    The shared generation task and canonical course document remain the source
    of truth. This command creates a teacher authoring baseline without
    publishing anything to the learner surface.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail={"code": "teacher_authoring_confirmation_required", "message": "请确认采用当前生成结果后再建立教师工作稿。"},
        )
    preview = tm.get_generation_preview(course_id)
    if not isinstance(preview, dict):
        raise HTTPException(
            status_code=404,
            detail={"code": "generation_preview_unavailable", "message": "当前课程没有可采用的生成结果。"},
        )
    task = preview.get("task") if isinstance(preview.get("task"), dict) else {}
    task_id = str(task.get("id") or "")
    if body.source_task_id and body.source_task_id != task_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "generation_preview_changed", "message": "生成结果已经变化，请重新载入后确认。"},
        )
    task_status = str(task.get("status") or "")
    if task_status not in {"completed", "completed_with_warnings", "error", "conflict"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "generation_preview_not_terminal",
                "message": "课程生成仍在运行或等待审阅，请先完成当前生成步骤。",
                "status": task_status,
            },
        )

    workspace_course = tm.get_generation_workspace_course(course_id) or preview
    document = document_from_generation_draft(workspace_course)
    if not document.sections or not document.blocks:
        raise HTTPException(
            status_code=422,
            detail={"code": "teacher_authoring_source_empty", "message": "当前生成结果没有可建立教案的章节正文。"},
        )

    current, canonical = repository.load_document(course_id)
    if not canonical:
        raise HTTPException(
            status_code=409,
            detail={"code": "teacher_authoring_requires_canonical_shell", "message": "课程结构需要先迁移后才能建立教师工作稿。"},
        )

    raw = repository.load_raw(course_id)
    command_id = f"confirm-teacher-authoring-source-v2:{course_id}:{task_id}"
    try:
        receipt = await repository.confirm_generated_teacher_source(
            course_id,
            document,
            job_id=task_id,
            command_id=command_id,
            expected_revision=current.document_revision,
            metadata=workspace_course,
        )
    except CourseDocumentConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "teacher_authoring_revision_conflict", "message": str(exc)},
        ) from exc

    actor = resolve_user_id(request.headers.get("X-User-Id"))
    service = TeachingPlanWorkbenchService(repository)
    try:
        baseline = await service.initialize_baseline(
            course_id,
            actor=actor,
            idempotency_key=f"teacher-source:{task_id}",
            base_course_document_revision=str(receipt.get("document_revision") or ""),
        )
    except TeachingPlanWorkbenchError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc), **exc.details},
        ) from exc

    receipt["source_task_id"] = task_id
    receipt["student_published"] = bool(raw.get("course_document_publication"))
    return {
        "status": "confirmed",
        "receipt": receipt,
        "document": repository.document_envelope(course_id),
        "workbench": baseline.get("workbench") or service.view(course_id, actor=actor),
    }
