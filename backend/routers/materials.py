"""课程资料资产上传与查询接口。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from material_parser import parse_material_asset
from material_storage import MaterialStorageError, material_repository
from teacher_course_space import (
    classify_document_type,
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


def _register_in_course_space(
    owner_id: str,
    asset: Any,
    *,
    course_id: str = "",
) -> dict[str, Any] | None:
    """把上传的资料登记进该教师的文件空间。

    F-3：课程生成里的「添加资料」原本只写 material_storage，与文件空间零交集，
    于是老师传了资料却在文件空间里找不到。这里补上那条引用。

    **登记失败不阻断上传**：文件空间是可见性，上传+解析才是生成链路的命脉。
    宁可这次在文件空间少一条引用（迁移脚本可重跑补上），也不能让上传整个失败。
    """
    if not owner_id:
        return None
    try:
        package = None
        normalized_course_id = str(course_id or "").strip()
        if normalized_course_id:
            matches = teacher_course_space_repository.list_owned(
                owner_id, normalized_course_id
            )
            if not matches:
                raise FileNotFoundError(normalized_course_id)
            package = teacher_course_space_repository.load_owned(
                str(matches[0].get("package_id") or ""), owner_id
            )
        return teacher_course_space_repository.register_material_reference(
            owner_id, asset, package=package
        )
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
    course_id: str = Form(default=""),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        asset = await material_repository.save_upload(
            file,
            upload_batch_id=upload_batch_id,
        )
    except MaterialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    parsed_document = None
    try:
        parsed_document = await parse_material_asset(material_repository, asset)
    except Exception as exc:
        logger.warning("资料 %s 上传成功但解析失败", asset.asset_id, exc_info=True)
        try:
            asset = material_repository.update_status(
                asset.asset_id,
                "failed",
                error=str(exc),
            )
        except MaterialStorageError:
            pass
    asset = material_repository.get_asset(asset.asset_id) or asset
    payload = material_repository.public_asset(asset)
    if parsed_document is not None:
        payload.update({
            "parse_status": parsed_document.parse_status,
            "parse_error": str(parsed_document.error or ""),
            "parse_warnings": list(parsed_document.warnings or []),
        })
    reference = _register_in_course_space(
        _optional_owner(x_user_id),
        asset,
        course_id=course_id if isinstance(course_id, str) else "",
    )
    # 让前端能直接告诉老师"已存入文件空间"，并知道去哪个包找。
    payload["course_space"] = (
        {
            "registered": True,
            "package_id": reference.get("package_id", ""),
            "course_asset_id": reference.get("asset_id", ""),
            "relative_path": reference.get("relative_path", ""),
        }
        if reference
        else {"registered": False}
    )
    return payload


@router.get("")
def list_materials(
    course_id: str | None = None,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """列出该教师在文件空间登记过的资料。

    `material_storage` 本身无归属也无列表接口，所以"我的资料"只能按文件空间的
    引用来答——这也正是统一入口之后应有的语义：文件空间是唯一的资料视图。
    """
    owner_id = _optional_owner(x_user_id)
    if not owner_id:
        return {"assets": [], "owner_scoped": False}
    assets: list[dict[str, Any]] = []
    summaries = teacher_course_space_repository.list_owned(owner_id, course_id)
    generation_source_snapshots: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        package_id = str(summary.get("package_id") or "")
        try:
            package = teacher_course_space_repository.load_owned(package_id, owner_id)
        except (FileNotFoundError, MaterialStorageError):
            continue
        for target_id, snapshot in (package.get("generation_source_snapshots") or {}).items():
            if not isinstance(snapshot, dict):
                continue
            existing = generation_source_snapshots.get(str(target_id))
            if existing and str(existing.get("captured_at") or "") >= str(snapshot.get("captured_at") or ""):
                continue
            generation_source_snapshots[str(target_id)] = {
                **snapshot,
                "package_id": package_id,
            }
        for item in package.get("assets") or []:
            if not item.get("material_asset_id"):
                continue
            material_asset_id = str(item.get("material_asset_id") or "")
            material = material_repository.get_asset(material_asset_id)
            parsed = material_repository.load_parsed_document(material_asset_id)
            document_type = str(item.get("document_type") or "").strip()
            if not document_type:
                document_type, _ = classify_document_type(
                    str(item.get("relative_path") or item.get("filename") or "")
                )
            assets.append({
                "package_id": package_id,
                "asset_id": item.get("asset_id", ""),
                "material_asset_id": material_asset_id,
                "filename": item.get("filename", ""),
                "relative_path": item.get("relative_path", ""),
                "size_bytes": item.get("size_bytes", 0),
                "uploaded_at": item.get("uploaded_at", ""),
                "category": item.get("category", ""),
                "document_type": document_type,
                "processing_status": str(getattr(material, "status", "") or item.get("parse_status") or ""),
                "parse_status": str(getattr(parsed, "parse_status", "") or item.get("parse_status") or ""),
                "parse_error": str(getattr(parsed, "error", "") or item.get("parse_error") or getattr(material, "error", "") or ""),
                "parse_warnings": list(getattr(parsed, "warnings", None) or item.get("parse_warnings") or getattr(material, "warnings", None) or []),
                "usages": teacher_course_space_repository.relationships_for_source(
                    package, str(item.get("asset_id") or "")
                ),
            })
    assets.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    configured_target_ids = sorted({
        str(target_id)
        for summary in summaries
        for target_id in summary.get("configured_source_target_ids", [])
        if target_id
    })
    return {
        "assets": assets,
        "configured_source_target_ids": configured_target_ids,
        "generation_source_snapshots": generation_source_snapshots,
        "owner_scoped": True,
    }


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
