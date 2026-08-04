"""教师课程文件空间：按教师和学年工作包保存原始课程资料。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from material_storage import ALLOWED_EXTENSIONS, DEFAULT_MAX_FILE_BYTES, MaterialStorageError

COURSE_SPACE_DIR = Path(__file__).resolve().parent / "data" / "teacher_course_spaces"
CATEGORIES = {
    "teaching_design": "教学设计",
    "lesson_materials": "讲次资料",
    "homework_labs": "作业与实验",
    "school_materials": "学校材料",
    "course_archive": "结课归档",
    "uncategorized": "未分类",
}
SCHOOL_TEMPLATE = [
    {"name": "0、教学大纲", "kind": "folder"}, {"name": "1、教案", "kind": "folder"},
    {"name": "2、PPT", "kind": "folder"},
    {"name": "3、大作业或实验报告", "kind": "folder"}, {"name": "4、考场记录单、学生签到单", "kind": "folder"},
    {"name": "5、实际考卷", "kind": "folder"},
]
TEMPLATE_FOLDER_RENUMBER = {
    "12、大作业或实验报告": "3、大作业或实验报告",
    "13、考场记录单、学生签到单": "4、考场记录单、学生签到单",
    "14、实际考卷": "5、实际考卷",
}
_RULES = (
    ("teaching_design", ("教学大纲", "教学设计", "教案")),
    ("lesson_materials", ("ppt", "课件", "讲义", "讲次")),
    ("homework_labs", ("作业", "实验", "报告")),
    ("school_materials", ("教学日历", "成绩", "试卷", "考场", "签到", "评阅", "自查")),
    ("course_archive", ("归档", "结课", "总结")),
)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def normalize_relative_path(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise MaterialStorageError("文件相对路径不合法")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts) or len(path.parts) > 30:
        raise MaterialStorageError("文件相对路径不合法")
    if len(raw) > 600:
        raise MaterialStorageError("文件相对路径过长")
    return str(path)

def classify_path(relative_path: str) -> tuple[str, str]:
    haystack = relative_path.lower()
    for category, words in _RULES:
        for word in words:
            if word.lower() in haystack:
                return category, f"文件名或路径包含“{word}”"
    return "uncategorized", "未命中预设分类规则"

def package_folder_paths(package: dict[str, Any]) -> list[str]:
    folders: set[str] = set()
    for entry in package.get("entries", []):
        if entry.get("kind") == "folder":
            folders.add(normalize_relative_path(str(entry.get("path") or entry.get("name") or "")))
    for asset in package.get("assets", []):
        parts = PurePosixPath(normalize_relative_path(str(asset.get("relative_path", "")))).parts[:-1]
        for index in range(1, len(parts) + 1):
            folders.add(str(PurePosixPath(*parts[:index])))
    return sorted(folders, key=lambda value: (len(PurePosixPath(value).parts), value))

class TeacherCourseSpaceRepository:
    def __init__(self, root: Path | str = COURSE_SPACE_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, package_id: str) -> Path:
        if not re.fullmatch(r"tcs-[a-z0-9-]{8,80}", package_id or ""):
            raise MaterialStorageError("课程工作包 ID 不合法")
        return self.root / package_id

    def _manifest(self, package_id: str) -> Path:
        return self._path(package_id) / "manifest.json"

    def _content_path(self, package_id: str, relative_path: str) -> Path:
        normalized = normalize_relative_path(relative_path)
        content_root = (self._path(package_id) / "content").resolve()
        destination = (content_root / Path(*PurePosixPath(normalized).parts)).resolve()
        try:
            destination.relative_to(content_root)
        except ValueError as exc:
            raise MaterialStorageError("文件相对路径不合法") from exc
        return destination

    def create_package(self, owner_id: str, course_name: str, academic_year: str, term: str, template: str = "blank") -> dict[str, Any]:
        name, year = course_name.strip(), academic_year.strip()
        if not name or not year or not term.strip():
            raise MaterialStorageError("课程名称、学年和学期不能为空")
        package_id = f"tcs-{uuid.uuid4().hex}"
        if template not in {"blank", "school_course_materials"}: raise MaterialStorageError("课程模板不合法")
        entries = [{**entry, "path": entry["name"]} for entry in SCHOOL_TEMPLATE] if template == "school_course_materials" else []
        package = {"package_id": package_id, "owner_id": owner_id, "course_name": name, "academic_year": year,
                   "term": term.strip(), "template": template, "status": "active", "created_at": _now(), "updated_at": _now(), "assets": [], "imports": [],
                   "entries": entries}
        package_path = self._path(package_id)
        package_path.mkdir(parents=True, exist_ok=False)
        (package_path / "files").mkdir(exist_ok=True)  # immutable source copies for download/history
        (package_path / "content").mkdir(exist_ok=True)  # teacher-visible folder tree
        for entry in entries:
            if entry["kind"] == "folder":
                (package_path / "content" / entry["path"]).mkdir(parents=True, exist_ok=False)
        _atomic_write(self._manifest(package_id), package)
        return self.public(package)

    def load_owned(self, package_id: str, owner_id: str) -> dict[str, Any]:
        path = self._manifest(package_id)
        if not path.is_file(): raise FileNotFoundError(package_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("owner_id") != owner_id: raise FileNotFoundError(package_id)
        if self._migrate_template_folder_numbering(data):
            self.save(data)
        return data

    def _migrate_template_folder_numbering(self, package: dict[str, Any]) -> bool:
        if package.get("template") != "school_course_materials":
            return False
        applied: dict[str, str] = {}
        changed = False
        for old_path, new_path in TEMPLATE_FOLDER_RENUMBER.items():
            source = self._content_path(package["package_id"], old_path)
            destination = self._content_path(package["package_id"], new_path)
            if source.exists() and destination.exists():
                continue
            if source.exists():
                source.replace(destination)
                changed = True
            elif any(item.get("kind") == "folder" and item.get("path", item.get("name")) == old_path for item in package.get("entries", [])):
                destination.mkdir(parents=True, exist_ok=True)
                changed = True
            applied[old_path] = new_path
        if not applied:
            return changed
        for entry in package.get("entries", []):
            entry_path = str(entry.get("path", entry.get("name", "")))
            for old_path, new_path in applied.items():
                if entry_path == old_path or entry_path.startswith(f"{old_path}/"):
                    updated = f"{new_path}{entry_path[len(old_path):]}"
                    entry["path"] = updated
                    if entry_path == old_path:
                        entry["name"] = PurePosixPath(new_path).name
                    changed = True
                    break
        for asset in package.get("assets", []):
            relative_path = str(asset.get("relative_path", ""))
            for old_path, new_path in applied.items():
                if relative_path.startswith(f"{old_path}/"):
                    updated = f"{new_path}{relative_path[len(old_path):]}"
                    asset["relative_path"] = updated
                    asset["materialized_path"] = updated
                    changed = True
                    break
        return changed

    def list_owned(self, owner_id: str) -> list[dict[str, Any]]:
        result = []
        for path in self.root.glob("tcs-*/manifest.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("owner_id") == owner_id: result.append(self.public(item))
            except (OSError, json.JSONDecodeError): pass
        return sorted(result, key=lambda item: item.get("updated_at", ""), reverse=True)

    def public(self, package: dict[str, Any]) -> dict[str, Any]:
        result = dict(package); result.pop("owner_id", None)
        result["entries"] = [entry for entry in result.get("entries", []) if entry.get("kind") == "folder"]
        result["asset_count"] = len(result.get("assets") or [])
        return result

    async def import_file(self, package: dict[str, Any], upload: Any, relative_path: str, batch_id: str) -> dict[str, Any]:
        relative_path = normalize_relative_path(relative_path)
        extension = Path(relative_path).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS: raise MaterialStorageError(f"不支持的文件类型：{extension or '无扩展名'}")
        content = await upload.read()
        if not content: raise MaterialStorageError("上传文件为空")
        if len(content) > DEFAULT_MAX_FILE_BYTES: raise MaterialStorageError("文件过大，单个文件最大支持 50 MB")
        digest = hashlib.sha256(content).hexdigest()
        existing = next((a for a in package["assets"] if a["relative_path"] == relative_path and a["sha256"] == digest), None)
        if existing: return {**existing, "outcome": "duplicate"}
        category, reason = classify_path(relative_path)
        asset_id = f"tca-{uuid.uuid4().hex}"
        safe_name = f"{asset_id}{extension}"
        package_path = self._path(package["package_id"])
        destination = package_path / "files" / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        materialized = self._content_path(package["package_id"], relative_path)
        materialized.parent.mkdir(parents=True, exist_ok=True)
        materialized.write_bytes(content)
        asset = {"asset_id": asset_id, "filename": Path(relative_path).name, "relative_path": relative_path, "stored_name": safe_name,
                 "materialized_path": relative_path, "extension": extension, "size_bytes": len(content), "sha256": digest, "suggested_category": category,
                 "category": category, "category_reason": reason, "import_batch_id": batch_id, "uploaded_at": _now()}
        package["assets"].append(asset)
        return {**asset, "outcome": "imported"}

    def save(self, package: dict[str, Any]) -> None:
        package["updated_at"] = _now(); _atomic_write(self._manifest(package["package_id"]), package)

    def update_category(self, package: dict[str, Any], asset_id: str, category: str) -> dict[str, Any]:
        if category not in CATEGORIES: raise MaterialStorageError("资料分类不合法")
        asset = next((a for a in package.get("assets", []) if a.get("asset_id") == asset_id), None)
        if not asset: raise FileNotFoundError(asset_id)
        asset["category"] = category; self.save(package); return asset

    def add_folder(self, package: dict[str, Any], name: str) -> dict[str, Any]:
        relative_path = normalize_relative_path(name)
        if len(relative_path) > 240 or Path(relative_path).suffix: raise MaterialStorageError("文件夹名称不合法")
        entries = package.setdefault("entries", [])
        if any(item.get("path", item.get("name")) == relative_path for item in entries): raise MaterialStorageError("已有同名文件夹")
        destination = self._content_path(package["package_id"], relative_path)
        destination.mkdir(parents=True, exist_ok=False)
        entry = {"name": PurePosixPath(relative_path).name, "path": relative_path, "kind": "folder", "custom": True}
        entries.append(entry); self.save(package); return entry

    def import_folders(self, package: dict[str, Any], folder_paths: list[str]) -> list[dict[str, Any]]:
        entries = package.setdefault("entries", [])
        existing = {item.get("path", item.get("name")) for item in entries if item.get("kind") == "folder"}
        normalized_paths: set[str] = set()
        for value in folder_paths:
            normalized = normalize_relative_path(value)
            parts = PurePosixPath(normalized).parts
            for index in range(1, len(parts) + 1):
                normalized_paths.add(str(PurePosixPath(*parts[:index])))
        created = []
        for relative_path in sorted(normalized_paths, key=lambda value: (len(PurePosixPath(value).parts), value)):
            self._content_path(package["package_id"], relative_path).mkdir(parents=True, exist_ok=True)
            if relative_path not in existing:
                entry = {"name": PurePosixPath(relative_path).name, "path": relative_path, "kind": "folder", "custom": True, "imported": True}
                entries.append(entry); existing.add(relative_path); created.append(entry)
        return created

    def delete_asset(self, package: dict[str, Any], asset_id: str) -> dict[str, Any]:
        asset = next((item for item in package.get("assets", []) if item.get("asset_id") == asset_id), None)
        if not asset:
            raise FileNotFoundError(asset_id)
        source = self._path(package["package_id"]) / "files" / str(asset["stored_name"])
        materialized = self._content_path(package["package_id"], str(asset["relative_path"]))
        if source.is_file():
            source.unlink()
        if materialized.is_file():
            materialized.unlink()
        package["assets"] = [item for item in package.get("assets", []) if item.get("asset_id") != asset_id]
        self.save(package)
        return asset

    def delete_folder(self, package: dict[str, Any], folder_path: str) -> dict[str, int | str]:
        normalized = normalize_relative_path(folder_path)
        destination = self._content_path(package["package_id"], normalized)
        prefix = f"{normalized}/"
        affected_assets = [item for item in package.get("assets", []) if str(item.get("relative_path", "")).startswith(prefix)]
        entries = package.get("entries", [])
        affected_entries = [item for item in entries if item.get("path", item.get("name")) == normalized or str(item.get("path", item.get("name", ""))).startswith(prefix)]
        if not destination.is_dir() and not affected_assets and not affected_entries:
            raise FileNotFoundError(normalized)
        for asset in affected_assets:
            source = self._path(package["package_id"]) / "files" / str(asset["stored_name"])
            if source.is_file():
                source.unlink()
        if destination.is_dir():
            shutil.rmtree(destination)
        affected_ids = {item["asset_id"] for item in affected_assets}
        package["assets"] = [item for item in package.get("assets", []) if item.get("asset_id") not in affected_ids]
        package["entries"] = [item for item in entries if item not in affected_entries]
        self.save(package)
        return {"path": normalized, "deleted_assets": len(affected_assets), "deleted_folders": len(affected_entries)}

    def source_file(self, package: dict[str, Any], asset_id: str) -> tuple[dict[str, Any], Path]:
        asset = next((a for a in package.get("assets", []) if a.get("asset_id") == asset_id), None)
        if not asset: raise FileNotFoundError(asset_id)
        path = self._path(package["package_id"]) / "files" / str(asset["stored_name"])
        if not path.is_file(): raise FileNotFoundError(asset_id)
        return asset, path

teacher_course_space_repository = TeacherCourseSpaceRepository()
