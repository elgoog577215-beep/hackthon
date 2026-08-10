"""Authenticated API for built-in and personal PPT template packs."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from learner_context import require_user_id
from ppt_template_packs import (
    MAX_REFERENCE_BYTES,
    TemplatePackError,
    ppt_template_pack_repository,
)


router = APIRouter(prefix="/ppt-template-packs", tags=["ppt-template-packs"])
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_LOGO_TYPES = {"image/png", "image/svg+xml", "image/jpeg", "image/webp"}


def _enabled() -> bool:
    return os.getenv("PPT_TEMPLATE_PACKS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _owner(request: Request) -> str:
    return require_user_id(request.headers.get("X-User-Id"))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail="Template pack not found")


def _ensure_write_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Personal PPT templates are not enabled")


async def _read_upload(upload: UploadFile | None, *, maximum: int) -> bytes | None:
    if upload is None or not upload.filename:
        return None
    payload = await upload.read(maximum + 1)
    if len(payload) > maximum:
        raise HTTPException(status_code=413, detail="Uploaded template asset is too large")
    return payload


@router.get("")
def list_template_packs(request: Request) -> dict[str, Any]:
    owner_id = _owner(request)
    return {
        "built_in": ppt_template_pack_repository.list_builtin(),
        "personal": ppt_template_pack_repository.list_for_owner(owner_id),
        "personal_templates_enabled": _enabled(),
    }


@router.post("/import", status_code=201)
async def import_template_pack(
    request: Request,
    name: str = Form(...),
    base_theme: str = Form(default="qizhi-classroom"),
    brand_json: str = Form(default="{}"),
    reference_pptx: UploadFile | None = File(default=None),
    logo: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    _ensure_write_enabled()
    owner_id = _owner(request)
    try:
        brand = json.loads(brand_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="brand_json must be valid JSON") from exc
    if not isinstance(brand, dict):
        raise HTTPException(status_code=422, detail="brand_json must be an object")

    reference_payload = await _read_upload(reference_pptx, maximum=MAX_REFERENCE_BYTES)
    logo_payload = await _read_upload(logo, maximum=MAX_IMAGE_BYTES)
    assets: list[dict[str, Any]] = []
    if logo_payload is not None and logo is not None:
        media_type = str(logo.content_type or "").lower()
        if media_type not in ALLOWED_LOGO_TYPES:
            raise HTTPException(status_code=415, detail="Logo must be PNG, SVG, JPEG, or WebP")
        assets.append(
            {
                "role": "logo",
                "filename": logo.filename or "logo",
                "mime_type": media_type,
                "payload": logo_payload,
            }
        )
    try:
        return ppt_template_pack_repository.create_draft(
            owner_id=owner_id,
            name=name,
            base_theme=base_theme,
            reference_pptx=reference_payload,
            reference_filename=(reference_pptx.filename if reference_pptx else "") or "",
            brand=brand,
            extra_assets=assets,
        )
    except TemplatePackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{pack_id}/compile-status")
def get_compile_status(pack_id: str, request: Request) -> dict[str, Any]:
    try:
        return ppt_template_pack_repository.compile_status(pack_id, _owner(request))
    except (FileNotFoundError, TemplatePackError) as exc:
        raise _not_found(exc) from exc


@router.patch("/{pack_id}/draft")
def update_template_draft(
    pack_id: str,
    request: Request,
    changes: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ensure_write_enabled()
    try:
        return ppt_template_pack_repository.update_draft(pack_id, _owner(request), changes)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except TemplatePackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{pack_id}/publish")
def publish_template_pack(pack_id: str, request: Request) -> dict[str, Any]:
    _ensure_write_enabled()
    try:
        return ppt_template_pack_repository.publish(pack_id, _owner(request))
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except TemplatePackError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{pack_id}/assets/{asset_id}")
def get_template_asset(
    pack_id: str,
    asset_id: str,
    request: Request,
    version: int | None = None,
) -> FileResponse:
    try:
        path, asset = ppt_template_pack_repository.asset_path(
            pack_id,
            asset_id,
            _owner(request),
            version=version,
        )
    except (FileNotFoundError, TemplatePackError, ValueError) as exc:
        raise _not_found(exc) from exc
    return FileResponse(
        path,
        media_type=asset.get("mime_type") or "application/octet-stream",
        filename=asset.get("filename") or path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{pack_id}")
def hide_template_pack(pack_id: str, request: Request) -> dict[str, str]:
    _ensure_write_enabled()
    try:
        ppt_template_pack_repository.soft_delete(pack_id, _owner(request))
    except (FileNotFoundError, TemplatePackError) as exc:
        raise _not_found(exc) from exc
    return {"status": "hidden", "pack_id": pack_id}


__all__ = ["router", "ppt_template_pack_repository"]
