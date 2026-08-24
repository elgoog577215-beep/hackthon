"""Teacher-owned PDF/DOCX import flow for the canonical question bank."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from dependencies import get_course_or_404, get_task_manager_optional
from learner_context import require_actor_id
from material_parser import parse_material_asset
from material_storage import MaterialStorageError, material_repository
from question_bank import merge_teacher_imported_questions
from question_bank_imports import (
    extract_question_drafts,
    question_bank_import_repository,
)
from teacher_course_space import (
    MaterialStorageError as CourseSpaceError,
    teacher_course_space_repository,
)

router = APIRouter(
    prefix="/courses/{course_id}/question-bank/imports",
    tags=["question_bank_imports"],
)


class ImportedQuestionPatch(BaseModel):
    prompt: str | None = Field(default=None, max_length=12000)
    question_type: str | None = Field(default=None, max_length=80)
    options: list[dict[str, str]] | None = Field(default=None, max_length=8)
    answer: str | None = Field(default=None, max_length=2000)
    explanation: str | None = Field(default=None, max_length=8000)
    score: int | None = Field(default=None, ge=1, le=1000)
    node_id: str | None = Field(default=None, max_length=200)
    confirmed: bool | None = None


async def _course_for_import(course_id: str) -> dict[str, Any]:
    canonical = await get_course_or_404(course_id)
    if any(isinstance(item, dict) for item in canonical.get("nodes") or []):
        return canonical
    task_manager = get_task_manager_optional()
    workspace = (
        task_manager.get_generation_workspace_course(course_id)
        if task_manager is not None
        else None
    )
    if not isinstance(workspace, dict):
        return canonical
    projected = deepcopy(workspace)
    projected.update(deepcopy(canonical))
    projected["nodes"] = deepcopy(workspace.get("nodes") or [])
    return projected


def _owned_session(course_id: str, import_id: str, actor_id: str) -> dict[str, Any]:
    try:
        session = question_bank_import_repository.load(course_id, import_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="导入会话标识不合法") from exc
    if not session or session.get("actor_id") != actor_id:
        raise HTTPException(status_code=404, detail="导入会话不存在")
    return session


def _register_source(actor_id: str, course_id: str, asset: Any) -> dict[str, str]:
    matches = teacher_course_space_repository.list_owned(actor_id, course_id)
    package = (
        teacher_course_space_repository.load_owned(
            str(matches[0].get("package_id") or ""), actor_id
        )
        if matches
        else teacher_course_space_repository.default_material_package(actor_id)
    )
    reference = teacher_course_space_repository.register_material_reference(
        actor_id,
        asset,
        package=package,
    )
    return {
        "package_id": str(reference.get("package_id") or package.get("package_id") or ""),
        "course_asset_id": str(reference.get("asset_id") or ""),
    }


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(session.get(key))
        for key in (
            "import_id",
            "course_id",
            "filename",
            "extension",
            "size_bytes",
            "parse_status",
            "status",
            "step",
            "question_count",
            "pending_count",
            "result_bundle_revision_id",
            "created_at",
            "updated_at",
        )
    }


@router.post("", status_code=201)
async def create_question_import(
    course_id: str,
    file: UploadFile = File(...),
    node_ids: list[str] | None = Form(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    await _course_for_import(course_id)
    extension = Path(str(file.filename or "")).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(status_code=422, detail="题目导入仅支持 PDF 和 Word（.docx）")
    try:
        asset = await material_repository.save_upload(
            file,
            upload_batch_id=f"question-import-{uuid4().hex}",
        )
        material_repository.bind_asset(asset.asset_id, course_id)
        reference = _register_source(actor_id, course_id, asset)
        document = await parse_material_asset(material_repository, asset)
    except (MaterialStorageError, CourseSpaceError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if document.parse_status == "failed":
        raise HTTPException(
            status_code=422,
            detail=f"文件解析失败：{document.error or '没有可用的解析器'}",
        )
    questions, source_pages = extract_question_drafts(
        document,
        node_ids=node_ids or [],
    )
    if not questions:
        raise HTTPException(
            status_code=422,
            detail="已读取文件，但未识别到编号题目。请检查题号或扫描质量。",
        )
    session = question_bank_import_repository.create(
        course_id=course_id,
        actor_id=actor_id,
        asset=asset,
        document=document,
        questions=questions,
        source_pages=source_pages,
        course_asset_id=reference["course_asset_id"],
        package_id=reference["package_id"],
    )
    return session


@router.get("")
def list_question_imports(
    course_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    sessions = question_bank_import_repository.list(course_id, actor_id=actor_id)
    return {"imports": [_session_summary(session) for session in sessions[:20]]}


@router.get("/active")
def get_active_question_import(
    course_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    session = next(
        (
            item
            for item in question_bank_import_repository.list(course_id, actor_id=actor_id)
            if item.get("status") != "committed"
        ),
        None,
    )
    return {"session": session}


@router.get("/{import_id}")
def get_question_import(
    course_id: str,
    import_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    return _owned_session(course_id, import_id, actor_id)


@router.patch("/{import_id}/items/{draft_id}")
def update_imported_question(
    course_id: str,
    import_id: str,
    draft_id: str,
    request: ImportedQuestionPatch,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    _owned_session(course_id, import_id, actor_id)
    try:
        return question_bank_import_repository.update_question(
            course_id,
            import_id,
            draft_id,
            request.model_dump(exclude_unset=True),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="待校对题目不存在") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{import_id}/commit")
async def commit_question_import(
    course_id: str,
    import_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    actor_id = require_actor_id(x_user_id)
    session = _owned_session(course_id, import_id, actor_id)
    if session.get("status") == "committed":
        return {
            "session": session,
            "bundle_revision_id": session.get("result_bundle_revision_id", ""),
            "question_count": session.get("question_count", 0),
        }
    if int(session.get("pending_count") or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail=f"还有 {session['pending_count']} 道题未确认",
        )
    course = await _course_for_import(course_id)
    try:
        bundle = merge_teacher_imported_questions(
            course,
            session.get("questions") or [],
            asset_id=str(session.get("asset_id") or ""),
            document_id=str(session.get("document_id") or ""),
            source_label=str(session.get("filename") or ""),
        )
        package_id = str(session.get("package_id") or "")
        course_asset_id = str(session.get("course_asset_id") or "")
        if package_id and course_asset_id:
            package = teacher_course_space_repository.load_owned(package_id, actor_id)
            existing_sources = [
                {
                    "source_asset_id": str(item.get("source_asset_id") or ""),
                    "role": str(item.get("role") or "reference"),
                }
                for item in teacher_course_space_repository.relationships_for_target(
                    package, "managed:question-bank"
                )
                if item.get("source_asset_id")
            ]
            teacher_course_space_repository.replace_formal_relationships(
                package,
                target_id="managed:question-bank",
                target_type="question_bank",
                target_label="课程题库",
                target_revision=str(bundle.get("bundle_revision_id") or ""),
                sources=[
                    *existing_sources,
                    {"source_asset_id": course_asset_id, "role": "reference"},
                ],
            )
    except (CourseSpaceError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    committed = question_bank_import_repository.mark_committed(
        course_id,
        import_id,
        str(bundle.get("bundle_revision_id") or ""),
    )
    return {
        "session": committed,
        "bundle_revision_id": bundle.get("bundle_revision_id", ""),
        "question_count": committed.get("question_count", 0),
    }
