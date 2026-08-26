"""HTTP API for teacher course work packages."""
from __future__ import annotations
import io, json, mimetypes, urllib.parse, zipfile
from typing import Any, Literal
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from learner_context import require_user_id
from material_storage import MaterialStorageError, material_repository
from teacher_course_space import CATEGORIES, package_folder_paths, teacher_course_space_repository as repository

router = APIRouter(prefix="/teacher-course-spaces", tags=["teacher_course_spaces"])
class PackageCreate(BaseModel): course_name: str; academic_year: str; term: str; template: str = "blank"; course_id: str = ""
class PackageBinding(BaseModel): course_id: str
class PreparationUpdate(BaseModel): status: Literal["completed", "skipped"]
class CategoryUpdate(BaseModel):
    category: str | None = None
    document_type: str | None = None
class FolderCreate(BaseModel): name: str
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
def owner(request: Request) -> str: return require_user_id(request.headers.get("X-User-Id"))
def http_error(exc: Exception):
    if isinstance(exc, FileNotFoundError): raise HTTPException(404, "课程工作包或资料不存在")
    if isinstance(exc, MaterialStorageError): raise HTTPException(422, str(exc))
    raise exc

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
        package["imports"].append({"batch_id": batch_id, "imported_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), "outcomes": outcomes})
        if str(package.get("preparation_status") or "completed") in {"pending", "review"}:
            package["preparation_status"] = "review"
        repository.save(package); return {"batch_id": batch_id, "outcomes": outcomes, "package": repository.public(package)}
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
@router.post("/{package_id}/folders", status_code=201)
def create_folder(package_id: str, body: FolderCreate, request: Request):
    try: return repository.add_folder(repository.load_owned(package_id, owner(request)), body.name)
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
