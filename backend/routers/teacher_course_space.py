"""HTTP API for teacher course work packages."""
from __future__ import annotations
import io, json, mimetypes, urllib.parse, zipfile
from typing import Any, Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from course_material_understanding import (
    CourseMaterialUnderstandingService,
    course_material_understanding_service,
)
from course_material_absorption import compile_material_absorption_plan, material_absorption_bundle
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from learner_context import require_user_id
from material_parser import parse_material_asset
from material_storage import MaterialStorageError, material_repository
from teacher_course_space import CATEGORIES, package_folder_paths, teacher_course_space_repository as repository
from teacher_lesson_authoring import TeacherLessonAuthoringRepository

router = APIRouter(prefix="/teacher-course-spaces", tags=["teacher_course_spaces"])
class PackageCreate(BaseModel): course_name: str; academic_year: str; term: str; template: str = "blank"; course_id: str = ""
class PackageBinding(BaseModel): course_id: str
class PreparationUpdate(BaseModel): status: Literal["completed", "skipped"]
class CategoryUpdate(BaseModel):
    category: str | None = None
    document_type: str | None = None
class FolderCreate(BaseModel): name: str
class AssetLocationUpdate(BaseModel):
    filename: str | None = None
    parent_path: str | None = None
class FolderLocationUpdate(BaseModel):
    path: str
    name: str | None = None
    parent_path: str | None = None
class FolderTrashRequest(BaseModel): path: str
class FileBatchAction(BaseModel):
    action: Literal["move", "trash", "restore", "purge"]
    ids: list[str] = Field(default_factory=list)
    destination_path: str = ""
class RelationshipSource(BaseModel):
    source_asset_id: str
    role: Literal["primary", "reference", "question_source"] = "reference"
class RelationshipUpdate(BaseModel):
    target_id: str
    target_type: str
    target_label: str
    target_revision: str = ""
    sources: list[RelationshipSource] = Field(default_factory=list)
    binding_mode: Literal["auto", "manual"] = "manual"
class AbsorptionDecisionUpdate(BaseModel):
    action: Literal["absorb", "reference_only", "ignore"] | None = None
    role: Literal["primary", "reference"] | None = None
    target_scope_id: str | None = None
    version_role: Literal["current", "older", "reference", "unknown"] | None = None
class AbsorptionExecuteRequest(BaseModel):
    target_ids: list[str] = Field(default_factory=list)
def owner(request: Request) -> str: return require_user_id(request.headers.get("X-User-Id"))
def http_error(exc: Exception):
    if isinstance(exc, FileNotFoundError): raise HTTPException(404, "课程工作包或资料不存在")
    if isinstance(exc, MaterialStorageError): raise HTTPException(422, str(exc))
    raise exc

def _course_view(package: dict[str, Any]) -> dict[str, Any]:
    course_id = str(package.get("course_id") or "")
    if not course_id:
        return {}
    try:
        return get_course_document_repository().load_course_view(course_id)
    except Exception:
        return {}

async def _parsed_package_documents(
    package: dict[str, Any],
    *,
    force_asset_ids: set[str] | None = None,
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    force_asset_ids = force_asset_ids or set()
    for asset in package.get("assets") or []:
        asset_id = str(asset.get("asset_id") or "")
        material_asset_id = str(asset.get("material_asset_id") or "")
        material = material_repository.get_asset(material_asset_id) if material_asset_id else None
        if material is None:
            continue
        try:
            document = material_repository.load_parsed_document(material_asset_id)
            if document is None or asset_id in force_asset_ids:
                document = await parse_material_asset(material_repository, material)
            parsed[asset_id] = document
            asset["parse_status"] = document.parse_status
            asset["parser_name"] = document.parser_name
            asset["parser_version"] = document.parser_version
            asset["parse_quality"] = dict(document.quality or {})
            asset["parse_warnings"] = list(document.warnings or [])
            asset["parse_error"] = str(document.error or "")
        except Exception:
            # The compiler exposes an unresolved parse issue; originals remain usable.
            continue
    return parsed

async def _refresh_absorption_plan(package: dict[str, Any]) -> dict[str, Any]:
    plan = compile_material_absorption_plan(
        package=package,
        documents=await _parsed_package_documents(package),
        course=_course_view(package),
    )
    repository.apply_material_absorption_plan(package, plan)
    return plan

@router.get("")
def list_packages(request: Request, course_id: str | None = None): return repository.list_owned(owner(request), course_id)
@router.post("", status_code=201)
def create_package(body: PackageCreate, request: Request):
    try: return repository.create_package(owner(request), body.course_name, body.academic_year, body.term, body.template, body.course_id)
    except Exception as exc: http_error(exc)
@router.get("/{package_id}")
def get_package(package_id: str, request: Request):
    try: return repository.public(repository.load_owned(package_id, owner(request)))
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}")
def bind_package(package_id: str, body: PackageBinding, request: Request):
    try: return repository.bind_course(repository.load_owned(package_id, owner(request)), body.course_id)
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/preparation")
def update_preparation(package_id: str, body: PreparationUpdate, request: Request):
    try: return repository.update_preparation_status(repository.load_owned(package_id, owner(request)), body.status)
    except Exception as exc: http_error(exc)
@router.put("/{package_id}/relationships")
def replace_relationships(package_id: str, body: RelationshipUpdate, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        relationships = repository.replace_formal_relationships(
            package,
            target_id=body.target_id,
            target_type=body.target_type,
            target_label=body.target_label,
            target_revision=body.target_revision,
            sources=[item.model_dump() for item in body.sources],
            binding_mode=body.binding_mode,
        )
        return {"relationships": relationships, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/imports")
async def import_folder(package_id: str, request: Request, files: list[UploadFile] | None = File(default=None), relative_paths: list[str] | None = Form(default=None), folder_paths: list[str] | None = Form(default=None)):
    try:
        package = repository.load_owned(package_id, owner(request))
        files, relative_paths = files or [], relative_paths or []
        if not files and not folder_paths: raise MaterialStorageError("请选择要导入的文件或文件夹")
        if len(files) != len(relative_paths): raise MaterialStorageError("文件与相对路径数量不一致")
        repository.import_folders(package, folder_paths or [])
        batch_id = f"import-{__import__('uuid').uuid4().hex}"; outcomes=[]
        for index, (file, path) in enumerate(zip(files, relative_paths)):
            try:
                outcome = await repository.import_file(package, file, path, batch_id)
                asset = next((item for item in package.get("assets", []) if item.get("asset_id") == outcome.get("asset_id")), None)
                if asset is not None and not asset.get("material_asset_id"):
                    try:
                        await file.seek(0)
                        material = await material_repository.save_upload(
                            file,
                            upload_batch_id=f"{batch_id}-{index + 1}",
                        )
                        asset["material_asset_id"] = material.asset_id
                        outcome["material_asset_id"] = material.asset_id
                    except MaterialStorageError as analysis_error:
                        outcome["analysis_error"] = str(analysis_error)
                outcomes.append(outcome)
            except MaterialStorageError as exc: outcomes.append({"relative_path": path, "outcome": "rejected", "error": str(exc)})
        imported_asset_ids = {
            str(item.get("asset_id") or "")
            for item in outcomes
            if item.get("outcome") in {"imported", "duplicate"} and item.get("asset_id")
        }
        # Re-run package understanding over the complete original set so a
        # later incremental batch can relate to files imported earlier.
        analyzed_assets = list(package.get("assets", []))
        parsed_documents = {}
        for asset in analyzed_assets:
            material_asset_id = str(asset.get("material_asset_id") or "")
            material = material_repository.get_asset(material_asset_id) if material_asset_id else None
            if material is None:
                continue
            try:
                document = material_repository.load_parsed_document(material_asset_id)
                if document is None or str(asset.get("asset_id") or "") in imported_asset_ids:
                    document = await parse_material_asset(material_repository, material)
                parsed_documents[str(asset.get("asset_id") or "")] = document
                asset["parse_status"] = document.parse_status
                asset["parser_name"] = document.parser_name
                asset["parser_version"] = document.parser_version
                asset["parse_quality"] = dict(document.quality or {})
                asset["parse_warnings"] = list(document.warnings or [])
                asset["parse_error"] = str(document.error or "")
            except Exception:
                outcome = next((item for item in outcomes if item.get("asset_id") == asset.get("asset_id")), None)
                if outcome is not None:
                    outcome["analysis_error"] = "文件正文解析失败，已保留原文件并使用基础识别"
        course = _course_view(package)
        try:
            understanding = await course_material_understanding_service.analyze_batch(
                package=package,
                assets=analyzed_assets,
                documents=parsed_documents,
                course=course,
                batch_id=batch_id,
            )
        except Exception:
            understanding = await CourseMaterialUnderstandingService(use_model=False).analyze_batch(
                package=package,
                assets=analyzed_assets,
                documents=parsed_documents,
                course=course,
                batch_id=batch_id,
            )
            understanding["failure_code"] = "analysis_internal_error"
        repository.apply_material_understanding(package, understanding)
        absorption = compile_material_absorption_plan(
            package=package,
            documents=parsed_documents,
            course=course,
        )
        repository.apply_material_absorption_plan(package, absorption)
        package["imports"].append({"batch_id": batch_id, "imported_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), "outcomes": outcomes})
        if str(package.get("preparation_status") or "completed") in {"pending", "review"}:
            package["preparation_status"] = "review"
        repository.save(package); return {"batch_id": batch_id, "outcomes": outcomes, "understanding": understanding, "absorption": absorption, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/assets/{asset_id}")
def update_asset(package_id: str, asset_id: str, body: CategoryUpdate, request: Request):
    try:
        return repository.update_asset_classification(
            repository.load_owned(package_id, owner(request)),
            asset_id,
            category=body.category,
            document_type=body.document_type,
        )
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/material-absorption/refresh")
async def refresh_material_absorption(package_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        plan = await _refresh_absorption_plan(package)
        return {"plan": plan, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/assets/{asset_id}/absorption")
async def update_asset_absorption(
    package_id: str,
    asset_id: str,
    body: AbsorptionDecisionUpdate,
    request: Request,
):
    try:
        package = repository.load_owned(package_id, owner(request))
        asset = repository.update_asset_absorption_decision(
            package,
            asset_id,
            action=body.action,
            role=body.role,
            target_scope_id=body.target_scope_id,
            version_role=body.version_role,
        )
        plan = await _refresh_absorption_plan(package)
        return {"asset": asset, "plan": plan, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/material-absorption/execute")
async def execute_material_absorption(
    package_id: str,
    request: Request,
    body: AbsorptionExecuteRequest | None = None,
    authoring_repository: TeacherLessonAuthoringRepository = Depends(get_teacher_lesson_authoring_repository),
):
    try:
        package = repository.load_owned(package_id, owner(request))
        if not str(package.get("course_id") or ""):
            raise HTTPException(409, {"code": "course_binding_required", "message": "请先把资料包关联到当前课程。"})
        plan = await _refresh_absorption_plan(package)
        requested_target_ids = {
            str(item or "").strip() for item in ((body.target_ids if body else []) or [])
            if str(item or "").strip()
        }
        available_target_ids = {
            str(item.get("target_id") or "") for item in plan.get("targets") or []
        }
        unknown_target_ids = sorted(requested_target_ids - available_target_ids)
        if unknown_target_ids:
            raise HTTPException(404, {
                "code": "material_absorption_target_not_found",
                "message": "当前备课页面没有可执行的材料审计结果。",
                "target_ids": unknown_target_ids,
            })
        selected_targets = [
            item for item in plan.get("targets") or []
            if not requested_target_ids or str(item.get("target_id") or "") in requested_target_ids
        ]
        selected_ids = {str(item.get("target_id") or "") for item in selected_targets}
        selected_unresolved = [
            item for item in plan.get("unresolved_items") or []
            if not requested_target_ids or str(item.get("target_id") or "") in selected_ids
        ]
        selected_plan = {
            **plan,
            "targets": selected_targets,
            "unresolved_items": selected_unresolved,
            "status": "ready" if selected_targets and not selected_unresolved else "needs_decision",
        }
        if str(selected_plan.get("status") or "") != "ready":
            raise HTTPException(409, {
                "code": "material_absorption_needs_decision",
                "message": "请先处理材料审计中的冲突和缺失项。",
                "unresolved_items": selected_unresolved,
            })
        bundle = material_absorption_bundle(selected_plan)
        authoring_receipt = authoring_repository.apply_material_absorption(
            str(package.get("course_id") or ""),
            bundle,
        )
        package_receipt = repository.execute_material_absorption(package, bundle)
        return {
            "bundle": bundle,
            "authoring_receipt": authoring_receipt,
            "receipt": package_receipt,
            "package": repository.public(package),
        }
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/assets/{asset_id}/location")
def update_asset_location(package_id: str, asset_id: str, body: AssetLocationUpdate, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        repository.relocate_asset(package, asset_id, filename=body.filename, parent_path=body.parent_path)
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/folders", status_code=201)
def create_folder(package_id: str, body: FolderCreate, request: Request):
    try: return repository.add_folder(repository.load_owned(package_id, owner(request)), body.name)
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/folders/location")
def update_folder_location(package_id: str, body: FolderLocationUpdate, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        repository.relocate_folder(package, body.path, name=body.name, parent_path=body.parent_path)
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/assets/{asset_id}/trash")
def trash_asset(package_id: str, asset_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        repository.trash_assets(package, [asset_id])
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/folders/trash")
def trash_folder(package_id: str, body: FolderTrashRequest, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        repository.trash_folder(package, body.path)
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/batch")
def batch_file_action(package_id: str, body: FileBatchAction, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        if body.action == "move":
            repository.relocate_assets(package, body.ids, body.destination_path)
        elif body.action == "trash":
            repository.trash_assets(package, body.ids)
        elif body.action == "restore":
            repository.restore_trash(package, body.ids)
        else:
            repository.purge_trash(package, body.ids)
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.post("/{package_id}/trash/{trash_id}/restore")
def restore_trash_item(package_id: str, trash_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        repository.restore_trash(package, [trash_id])
        return repository.public(package)
    except Exception as exc: http_error(exc)
@router.delete("/{package_id}/trash/{trash_id}")
def delete_trash_item(package_id: str, trash_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        result = repository.purge_trash(package, [trash_id])
        return {**result, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.delete("/{package_id}/trash")
def empty_trash(package_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        result = repository.purge_trash(package)
        return {**result, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.delete("/{package_id}/assets/{asset_id}")
def delete_asset(package_id: str, asset_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request))
        deleted = repository.delete_asset(package, asset_id)
        return {"deleted": True, "asset_id": deleted["asset_id"], "relative_path": deleted["relative_path"]}
    except Exception as exc: http_error(exc)
@router.delete("/{package_id}/folders")
def delete_folder(package_id: str, path: str, request: Request):
    try: return {"deleted": True, **repository.delete_folder(repository.load_owned(package_id, owner(request)), path)}
    except Exception as exc: http_error(exc)
@router.get("/{package_id}/assets/{asset_id}/download")
def download_asset(package_id: str, asset_id: str, request: Request):
    try:
        asset, path = repository.source_file(repository.load_owned(package_id, owner(request)), asset_id)
        return FileResponse(path, filename=asset["filename"], media_type="application/octet-stream")
    except Exception as exc: http_error(exc)
@router.get("/{package_id}/assets/{asset_id}/preview")
def preview_asset(package_id: str, asset_id: str, request: Request):
    try:
        asset, path = repository.source_file(repository.load_owned(package_id, owner(request)), asset_id)
        media_type = mimetypes.guess_type(asset["filename"])[0] or "application/octet-stream"
        safe_name = urllib.parse.quote(asset["filename"])
        return FileResponse(path, media_type=media_type, headers={"Content-Disposition": f"inline; filename*=UTF-8''{safe_name}"})
    except Exception as exc: http_error(exc)
@router.get("/{package_id}/export")
def export_package(package_id: str, request: Request):
    try:
        package = repository.load_owned(package_id, owner(request)); buffer=io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest=[]
            for folder_path in package_folder_paths(package):
                directory = zipfile.ZipInfo(f"{folder_path.rstrip('/')}/")
                directory.external_attr = (0o40775 << 16) | 0x10
                archive.writestr(directory, b"")
            for asset in package.get("assets", []):
                _, path = repository.source_file(package, asset["asset_id"])
                archive.write(path, asset['relative_path']); manifest.append({k:v for k,v in asset.items() if k != 'stored_name'})
            archive.writestr("课程资料清单.json", json.dumps({"package": repository.public(package), "categories": CATEGORIES, "assets": manifest}, ensure_ascii=False, indent=2))
        buffer.seek(0); name=f"{package['course_name']}-{package['academic_year']}-{package['term']}-课程资料包.zip"
        return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').parse.quote(name)}"})
    except Exception as exc: http_error(exc)
