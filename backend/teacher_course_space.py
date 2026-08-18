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
# 生成侧资料在文件空间里的登记形态。引用条目**不在包内存字节**，
# 只指向 material_storage 的 `mat-*`，下载/预览由 source_file 转发过去。
MATERIAL_REFERENCE_KIND = "material_reference"
MATERIAL_INBOX_NAME = "课程资料"
MATERIAL_INBOX_YEAR = "通用"
MATERIAL_INBOX_TERM = "全部"
MATERIAL_INBOX_FOLDER = "生成资料"
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
        # 引用条目只删引用，**绝不碰底层 mat-* 资产**：那份资料可能已经绑定课程、
        # 带着解析产物在生成链路里用着。底层删除仍走 material_storage.delete_unbound
        # 的绑定保护，不从这里绕过去。
        if asset.get("source_kind") != MATERIAL_REFERENCE_KIND:
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
            # 引用条目没有包内副本，跳过（同 delete_asset：不碰底层 mat-* 资产）。
            if asset.get("source_kind") == MATERIAL_REFERENCE_KIND:
                continue
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
        # 引用条目不在包内存字节，转发到底层 material_storage 取原文件。
        if asset.get("source_kind") == MATERIAL_REFERENCE_KIND:
            from material_storage import material_repository
            material = material_repository.get_asset(str(asset.get("material_asset_id") or ""))
            if material is None:
                raise FileNotFoundError(asset_id)
            return asset, material_repository.source_path(material)
        path = self._path(package["package_id"]) / "files" / str(asset["stored_name"])
        if not path.is_file(): raise FileNotFoundError(asset_id)
        return asset, path

    # --- 生成侧资料的引用登记 ---------------------------------------------
    #
    # 课程生成里的「添加资料」原本直接写 material_storage，与文件空间零交集，
    # 于是老师传了资料却在文件空间里找不到（F-3 要解决的就是这个）。
    #
    # 这里**不搬存储**：解析产物（parsed_document / evidence）与生成链路都依赖
    # `mat-*`，搬过来会切断那条链路。改为在教师自己的包下登记一条**引用条目**，
    # 不复制字节，下载/预览转发到底层。教师因此在文件空间看得见、管得着。

    def locate_material_reference(
        self,
        material_asset_id: str,
        *,
        owner_id: str = "",
    ) -> list[dict[str, Any]]:
        """反查一份 `mat-*` 资料被登记在哪个包、哪个文件夹下。

        引用是**双向可查**的：正向靠条目上的 `material_asset_id` 取解析产物，
        反向靠这里从资料回到"教师在文件空间的哪个位置能看到它"。少了反向，
        资料出问题时只能全量翻包才能定位。

        返回列表而不是单个：全局去重会让同一份底层资料被多位教师各自引用
        （见 `register_material_reference` 的说明），所以反查天然是一对多。
        `owner_id` 给定时只看该教师的包——这也是接口层该用的调用方式，
        避免把别人的位置暴露出去。
        """
        target = str(material_asset_id or "").strip()
        if not target:
            return []
        found: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("tcs-*/manifest.json")):
            try:
                package = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if owner_id and package.get("owner_id") != owner_id:
                continue
            for asset in package.get("assets") or []:
                if asset.get("source_kind") != MATERIAL_REFERENCE_KIND:
                    continue
                if str(asset.get("material_asset_id") or "") != target:
                    continue
                relative_path = str(asset.get("relative_path") or "")
                folder = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
                found.append({
                    "package_id": str(package.get("package_id") or ""),
                    "course_name": str(package.get("course_name") or ""),
                    "owner_id": str(package.get("owner_id") or ""),
                    "asset_id": str(asset.get("asset_id") or ""),
                    "relative_path": relative_path,
                    "folder": folder,
                    "filename": str(asset.get("filename") or ""),
                })
        return found

    def default_material_package(self, owner_id: str) -> dict[str, Any]:
        """取该教师承接生成侧资料的包，没有就建一个。

        找不到时新建而不是报错：上传是教师的主动作，不该因为"还没建过课程包"
        而失败。
        """
        for path in sorted(self.root.glob("tcs-*/manifest.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if item.get("owner_id") == owner_id and item.get("is_material_inbox"):
                return item
        created = self.create_package(
            owner_id, MATERIAL_INBOX_NAME, MATERIAL_INBOX_YEAR, MATERIAL_INBOX_TERM,
        )
        package = self.load_owned(created["package_id"], owner_id)
        package["is_material_inbox"] = True
        self.save(package)
        return package

    def register_material_reference(
        self,
        owner_id: str,
        material: Any,
        *,
        package: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把一份 `mat-*` 资料登记进该教师的文件空间。

        幂等键是 `(owner_id, material_asset_id)`——同一份资料重复上传只有一条引用。

        **跨教师不串包**：`material_storage` 按 sha256 全局去重，teacher A 传一个与
        teacher B 相同的文件会拿到 B 的 `mat-*` id。今天无害（资料无归属也无列表），
        但登记进按 owner 分包的文件空间后就会变成跨教师可见。所以引用记在**各自
        owner 的包**下——同一个底层资产可以被多个 owner 各自引用，互不可见。
        """
        target = package if package is not None else self.default_material_package(owner_id)
        material_asset_id = str(getattr(material, "asset_id", "") or "")
        if not material_asset_id:
            raise MaterialStorageError("资料标识缺失，无法登记到文件空间")
        existing = next(
            (
                item for item in target.get("assets", [])
                if item.get("source_kind") == MATERIAL_REFERENCE_KIND
                and item.get("material_asset_id") == material_asset_id
            ),
            None,
        )
        if existing:
            return {**existing, "package_id": target["package_id"], "outcome": "duplicate"}

        filename = str(getattr(material, "filename", "") or material_asset_id)
        relative_path = normalize_relative_path(
            f"{MATERIAL_INBOX_FOLDER}/{Path(filename).name}"
        )
        # 同名不同资料时加后缀，避免树里两条同路径条目。
        taken = {str(item.get("relative_path") or "") for item in target.get("assets", [])}
        if relative_path in taken:
            stem, suffix = Path(relative_path).stem, Path(relative_path).suffix
            relative_path = f"{MATERIAL_INBOX_FOLDER}/{stem}-{material_asset_id[-6:]}{suffix}"
        category, reason = classify_path(relative_path)
        asset = {
            "asset_id": f"tca-{uuid.uuid4().hex}",
            "filename": Path(relative_path).name,
            "relative_path": relative_path,
            # 引用条目没有包内副本，这两个字段留空以示区别（source_file 会走转发）。
            "stored_name": "",
            "materialized_path": "",
            "extension": str(getattr(material, "extension", "") or Path(filename).suffix.lower()),
            "size_bytes": int(getattr(material, "size_bytes", 0) or 0),
            "sha256": str(getattr(material, "sha256", "") or ""),
            "suggested_category": category,
            "category": category,
            "category_reason": reason,
            "import_batch_id": str(getattr(material, "upload_batch_id", "") or ""),
            "uploaded_at": _now(),
            "source_kind": MATERIAL_REFERENCE_KIND,
            "material_asset_id": material_asset_id,
        }
        target.setdefault("assets", []).append(asset)
        self.save(target)
        return {**asset, "package_id": target["package_id"], "outcome": "registered"}

teacher_course_space_repository = TeacherCourseSpaceRepository()
