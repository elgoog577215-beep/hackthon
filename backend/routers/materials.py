"""课程资料资产上传与查询接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from material_storage import MaterialStorageError, material_repository

router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("", status_code=201)
async def upload_material(
    file: UploadFile = File(...),
    upload_batch_id: str = Form(default=""),
) -> dict[str, Any]:
    try:
        asset = await material_repository.save_upload(
            file,
            upload_batch_id=upload_batch_id,
        )
    except MaterialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return material_repository.public_asset(asset)


@router.get("/{asset_id}")
def get_material(asset_id: str) -> dict[str, Any]:
    try:
        asset = material_repository.get_asset(asset_id)
    except MaterialStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not asset:
        raise HTTPException(status_code=404, detail="资料不存在")
    return material_repository.public_asset(asset)


@router.delete("/{asset_id}")
def delete_material(asset_id: str) -> dict[str, str]:
    try:
        deleted = material_repository.delete_unbound(asset_id)
    except MaterialStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="资料不存在")
    return {"status": "deleted", "asset_id": asset_id}
