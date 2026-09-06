"""Course-owned companion-document templates, versions and exports."""

from __future__ import annotations

from typing import Any, Literal, NoReturn
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from course_companion_documents import (
    CompanionDocumentError,
    companion_document_repository,
    compile_document,
    export_document,
    list_templates,
)
from dependencies import get_course_or_404
from learner_context import require_user_id

router = APIRouter(
    prefix="/courses/{course_id}/companion-documents",
    tags=["companion_documents"],
)


class CompanionDocumentGenerateRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


def _actor(request: Request) -> str:
    return require_user_id(request.headers.get("X-User-Id"))


def _raise(error: Exception) -> NoReturn:
    if isinstance(error, CompanionDocumentError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


@router.get("")
async def get_companion_documents(course_id: str, request: Request) -> dict[str, Any]:
    _actor(request)
    course = await get_course_or_404(course_id)
    return {
        "templates": list_templates(course),
        "documents": companion_document_repository.list_course(course_id),
    }


@router.post("/{template_id}/generate")
async def generate_companion_document(
    course_id: str,
    template_id: str,
    body: CompanionDocumentGenerateRequest,
    request: Request,
) -> dict[str, Any]:
    actor_id = _actor(request)
    course = await get_course_or_404(course_id)
    try:
        compiled = compile_document(template_id, body.inputs, course)
        return companion_document_repository.save_revision(
            course_id=course_id,
            actor_id=actor_id,
            compiled=compiled,
        )
    except Exception as error:
        _raise(error)


@router.get("/{document_id}")
async def get_companion_document(course_id: str, document_id: str, request: Request) -> dict[str, Any]:
    _actor(request)
    await get_course_or_404(course_id)
    try:
        document = companion_document_repository.load(course_id, document_id)
    except Exception as error:
        _raise(error)
    if document is None:
        raise HTTPException(status_code=404, detail="配套文档不存在")
    return document


@router.get("/{document_id}/export")
async def export_companion_document(
    course_id: str,
    document_id: str,
    request: Request,
    format: Literal["docx", "md"] = Query(default="docx"),
) -> Response:
    _actor(request)
    await get_course_or_404(course_id)
    try:
        document = companion_document_repository.load(course_id, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="配套文档不存在")
        content, media_type, filename = export_document(document, format)
    except HTTPException:
        raise
    except Exception as error:
        _raise(error)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
