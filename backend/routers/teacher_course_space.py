"""HTTP API for teacher course work packages."""
from __future__ import annotations
import io, json, mimetypes, urllib.parse, zipfile
from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from learner_context import require_user_id
from material_storage import MaterialStorageError
from teacher_course_space import CATEGORIES, package_folder_paths, teacher_course_space_repository as repository

router = APIRouter(prefix="/teacher-course-spaces", tags=["teacher_course_spaces"])
class PackageCreate(BaseModel): course_name: str; academic_year: str; term: str; template: str = "blank"
class CategoryUpdate(BaseModel): category: str
class FolderCreate(BaseModel): name: str
def owner(request: Request) -> str: return require_user_id(request.headers.get("X-User-Id"))
def http_error(exc: Exception):
    if isinstance(exc, FileNotFoundError): raise HTTPException(404, "课程工作包或资料不存在")
    if isinstance(exc, MaterialStorageError): raise HTTPException(422, str(exc))
    raise exc

@router.get("")
def list_packages(request: Request): return repository.list_owned(owner(request))
@router.post("", status_code=201)
def create_package(body: PackageCreate, request: Request):
    try: return repository.create_package(owner(request), body.course_name, body.academic_year, body.term, body.template)
    except Exception as exc: http_error(exc)
@router.get("/{package_id}")
def get_package(package_id: str, request: Request):
    try: return repository.public(repository.load_owned(package_id, owner(request)))
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
        for file, path in zip(files, relative_paths):
            try: outcomes.append(await repository.import_file(package, file, path, batch_id))
            except MaterialStorageError as exc: outcomes.append({"relative_path": path, "outcome": "rejected", "error": str(exc)})
        package["imports"].append({"batch_id": batch_id, "imported_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), "outcomes": outcomes})
        repository.save(package); return {"batch_id": batch_id, "outcomes": outcomes, "package": repository.public(package)}
    except Exception as exc: http_error(exc)
@router.patch("/{package_id}/assets/{asset_id}")
def update_asset(package_id: str, asset_id: str, body: CategoryUpdate, request: Request):
    try: return repository.update_category(repository.load_owned(package_id, owner(request)), asset_id, body.category)
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
