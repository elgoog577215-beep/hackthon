"""课程资料资产上传与查询接口。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from material_storage import MaterialStorageError, material_repository
from teacher_course_space import (
    MATERIAL_REFERENCE_KIND,
    teacher_course_space_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/materials", tags=["materials"])


def _optional_owner(raw: str | None) -> str:
    """取教师身份，取不到就返回空串。

    这里刻意**不用** `require_user_id`：它在缺身份时抛 400，而本接口是课程生成的
    资料上传口，历史上不要求身份。改成强制会直接打断生成链路。没有身份时只是
    不登记到文件空间，上传本身照常。
    """
    owner_id = str(raw or "").strip()
    return "" if owner_id in {"", "default_user"} or len(owner_id) > 160 else owner_id


def _register_in_course_space(owner_id: str, asset: Any) -> dict[str, Any] | None:
    """把上传的资料登记进该教师的文件空间。

    F-3：课程生成里的「添加资料」原本只写 material_storage，与文件空间零交集，
    于是老师传了资料却在文件空间里找不到。这里补上那条引用。

    **登记失败不阻断上传**：文件空间是可见性，上传+解析才是生成链路的命脉。
    宁可这次在文件空间少一条引用（迁移脚本可重跑补上），也不能让上传整个失败。
    """
    if not owner_id:
        return None
    try:
        return teacher_course_space_repository.register_material_reference(owner_id, asset)
    except Exception:
        logger.warning(
            "资料 %s 已上传但未能登记到文件空间（owner=%s），可用 "
            "scripts/backfill_material_references.py 补登记",
            getattr(asset, "asset_id", "?"), owner_id, exc_info=True,
        )
        return None


@router.post("", status_code=201)
async def upload_material(
    file: UploadFile = File(...),
    upload_batch_id: str = Form(default=""),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        asset = await material_repository.save_upload(
            file,
            upload_batch_id=upload_batch_id,
        )
    except MaterialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = material_repository.public_asset(asset)
    reference = _register_in_course_space(_optional_owner(x_user_id), asset)
    # 让前端能直接告诉老师"已存入文件空间"，并知道去哪个包找。
    payload["course_space"] = (
        {
            "registered": True,
            "package_id": reference.get("package_id", ""),
            "relative_path": reference.get("relative_path", ""),
        }
        if reference
        else {"registered": False}
    )
    return payload


@router.get("")
def list_materials(x_user_id: str | None = Header(default=None)) -> dict[str, Any]:
    """列出该教师在文件空间登记过的资料。

    `material_storage` 本身无归属也无列表接口，所以"我的资料"只能按文件空间的
    引用来答——这也正是统一入口之后应有的语义：文件空间是唯一的资料视图。
    """
    owner_id = _optional_owner(x_user_id)
    if not owner_id:
        return {"assets": [], "owner_scoped": False}
    assets: list[dict[str, Any]] = []
    for summary in teacher_course_space_repository.list_owned(owner_id):
        package_id = str(summary.get("package_id") or "")
        try:
            package = teacher_course_space_repository.load_owned(package_id, owner_id)
        except (FileNotFoundError, MaterialStorageError):
            continue
        for item in package.get("assets") or []:
            if item.get("source_kind") != MATERIAL_REFERENCE_KIND:
                continue
            assets.append({
                "package_id": package_id,
                "asset_id": item.get("asset_id", ""),
                "material_asset_id": item.get("material_asset_id", ""),
                "filename": item.get("filename", ""),
                "relative_path": item.get("relative_path", ""),
                "size_bytes": item.get("size_bytes", 0),
                "uploaded_at": item.get("uploaded_at", ""),
            })
    assets.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    return {"assets": assets, "owner_scoped": True}


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
