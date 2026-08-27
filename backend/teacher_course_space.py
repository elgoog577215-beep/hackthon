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
FORMAL_FILE_TYPES = {
    "outline",
    "teaching_calendar",
    "lesson_plan",
    "script",
    "ppt",
    "question_bank",
    "exam_paper",
    "companion_document",
}
PREPARATION_STATUSES = {"pending", "review", "completed", "skipped"}
CATEGORIES = {
    "teaching_design": "教学设计",
    "lesson_materials": "讲次资料",
    "homework_labs": "作业与实验",
    "school_materials": "学校材料",
    "course_archive": "结课归档",
    "uncategorized": "未分类",
}
DOCUMENT_TYPES = {
    "outline": "课程大纲",
    "lesson_plan": "教案",
    "script": "讲稿",
    "ppt": "PPT",
    "question_bank": "题库与试卷",
    "school_material": "教务材料",
    "other": "其他资料",
}
MANAGED_UPLOAD_FOLDERS = {
    "辅助资料",
    "辅助资料/老师题库",
    "辅助资料/试卷",
    "辅助资料/学生作业",
    "辅助资料/其他资料",
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
_DOCUMENT_RULES = (
    ("outline", ("教学大纲", "课程大纲", "大纲", "syllabus", "outline")),
    ("script", ("逐字稿", "讲稿", "授课稿", "speaker note", "script")),
    ("lesson_plan", ("教案", "教学设计", "教学方案", "lesson plan")),
    ("question_bank", ("题库", "试题", "试卷", "考卷", "真题", "question bank", "exam")),
    ("school_material", ("教学日历", "成绩", "考场", "签到", "评阅", "自查", "归档")),
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


def classify_document_type(relative_path: str) -> tuple[str, str]:
    """识别原件在备课链中的用途；结果始终等待教师确认。"""
    normalized = str(relative_path or "").replace("\\", "/")
    haystack = normalized.lower()
    extension = Path(normalized).suffix.lower()
    if extension in {".ppt", ".pptx"}:
        return "ppt", "文件格式为 PowerPoint"
    for document_type, words in _DOCUMENT_RULES:
        for word in words:
            if word.lower() in haystack:
                return document_type, f"文件名或路径包含“{word}”"
    return "other", "未识别出明确的备课文档类型"

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

    def create_package(
        self,
        owner_id: str,
        course_name: str,
        academic_year: str,
        term: str,
        template: str = "blank",
        course_id: str = "",
    ) -> dict[str, Any]:
        name, year = course_name.strip(), academic_year.strip()
        if not name or not year or not term.strip():
            raise MaterialStorageError("课程名称、学年和学期不能为空")
        normalized_course_id = str(course_id or "").strip()
        if len(normalized_course_id) > 160:
            raise MaterialStorageError("课程 ID 不合法")
        if normalized_course_id and self.list_owned(owner_id, normalized_course_id):
            raise MaterialStorageError("当前课程已经有文件库")
        package_id = f"tcs-{uuid.uuid4().hex}"
        if template not in {"blank", "school_course_materials"}: raise MaterialStorageError("课程模板不合法")
        entries = [{**entry, "path": entry["name"]} for entry in SCHOOL_TEMPLATE] if template == "school_course_materials" else []
        package = {"package_id": package_id, "owner_id": owner_id, "course_id": normalized_course_id, "course_name": name, "academic_year": year,
                   "term": term.strip(), "template": template, "status": "active", "created_at": _now(), "updated_at": _now(), "assets": [], "trash": [], "imports": [],
                   "entries": entries, "relationships": [], "asset_relationships": [], "material_understanding": {}, "preparation_status": "pending"}
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

    def list_owned(self, owner_id: str, course_id: str | None = None) -> list[dict[str, Any]]:
        result = []
        normalized_course_id = str(course_id or "").strip()
        for path in self.root.glob("tcs-*/manifest.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("owner_id") != owner_id:
                    continue
                if normalized_course_id and str(item.get("course_id") or "") != normalized_course_id:
                    continue
                result.append(self.public(item))
            except (OSError, json.JSONDecodeError): pass
        return sorted(result, key=lambda item: item.get("updated_at", ""), reverse=True)

    def bind_course(self, package: dict[str, Any], course_id: str) -> dict[str, Any]:
        normalized_course_id = str(course_id or "").strip()
        if not normalized_course_id or len(normalized_course_id) > 160:
            raise MaterialStorageError("课程 ID 不合法")
        current = str(package.get("course_id") or "")
        if current and current != normalized_course_id:
            raise MaterialStorageError("文件库已经绑定其他课程")
        conflicts = [
            item for item in self.list_owned(str(package.get("owner_id") or ""), normalized_course_id)
            if item.get("package_id") != package.get("package_id")
        ]
        if conflicts:
            raise MaterialStorageError("当前课程已经有文件库")
        package["course_id"] = normalized_course_id
        self.save(package)
        return self.public(package)

    def public(self, package: dict[str, Any]) -> dict[str, Any]:
        result = dict(package); result.pop("owner_id", None)
        # 旧工作包创建时没有准备状态。把它们视为已完成，避免升级后把老师
        # 已经在使用的课程重新送回首次导入页。
        result["preparation_status"] = str(result.get("preparation_status") or "completed")
        result["entries"] = [entry for entry in result.get("entries", []) if entry.get("kind") == "folder"]
        result["assets"] = []
        for source in package.get("assets", []):
            asset = dict(source)
            if not asset.get("document_type"):
                document_type, reason = classify_document_type(str(asset.get("relative_path") or asset.get("filename") or ""))
                asset["document_type"] = document_type
                asset["document_type_reason"] = reason
            result["assets"].append(asset)
        configured = set(str(value) for value in package.get("source_binding_targets", {}).keys())
        configured.update(
            str(item.get("target_id") or "")
            for item in package.get("relationships", [])
            if item.get("target_id")
        )
        result["configured_source_target_ids"] = sorted(configured)
        result["asset_count"] = len(result.get("assets") or [])
        result["trash"] = [
            {
                "trash_id": str(item.get("trash_id") or ""),
                "kind": str(item.get("kind") or "asset"),
                "name": str(item.get("name") or ""),
                "original_path": str(item.get("original_path") or ""),
                "deleted_at": str(item.get("deleted_at") or ""),
                "item_count": int(item.get("item_count") or 1),
                "size_bytes": int(item.get("size_bytes") or 0),
            }
            for item in package.get("trash") or []
        ]
        result["trash_count"] = sum(int(item.get("item_count") or 1) for item in result["trash"])
        return result

    def update_preparation_status(self, package: dict[str, Any], status: str) -> dict[str, Any]:
        normalized = str(status or "").strip()
        if normalized not in PREPARATION_STATUSES:
            raise MaterialStorageError("课程资料准备状态不合法")
        package["preparation_status"] = normalized
        self.save(package)
        return self.public(package)

    def apply_material_understanding(
        self,
        package: dict[str, Any],
        understanding: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist four-dimensional analysis without overriding teacher decisions."""
        by_id = {
            str(item.get("asset_id") or ""): item
            for item in understanding.get("assets") or []
            if isinstance(item, dict) and item.get("asset_id")
        }
        for asset in package.get("assets") or []:
            analysis = by_id.get(str(asset.get("asset_id") or ""))
            if analysis is None:
                continue
            teacher_confirmed = (
                asset.get("classification_source") == "teacher"
                or asset.get("document_type_reason") == "教师确认"
            )
            if not teacher_confirmed:
                asset["document_type"] = analysis.get("document_type", asset.get("document_type", "other"))
                asset["document_type_reason"] = analysis.get("reason", asset.get("document_type_reason", ""))
                asset["classification_confidence"] = analysis.get("confidence", 0)
                asset["classification_source"] = analysis.get("analysis_source", "rule")
                asset["classification_version"] = understanding.get("engine_version", "")
            asset["course_alignment"] = analysis.get("course_alignment") or {}
            asset["structure_matches"] = analysis.get("structure_matches") or []
            asset["version_role"] = analysis.get("version_role", "unknown")
            asset["version_reason"] = analysis.get("version_reason", "")
            asset["related_asset_ids"] = analysis.get("related_asset_ids") or []
            asset["understanding_updated_at"] = understanding.get("analyzed_at", _now())
        package["asset_relationships"] = list(understanding.get("relationships") or [])
        package["material_understanding"] = {
            key: value for key, value in understanding.items() if key != "assets"
        }
        self.save(package)
        return self.public(package)

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
        document_type, document_type_reason = classify_document_type(relative_path)
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
                 "category": category, "category_reason": reason, "document_type": document_type,
                 "document_type_reason": document_type_reason, "import_batch_id": batch_id, "uploaded_at": _now()}
        package["assets"].append(asset)
        return {**asset, "outcome": "imported"}

    def save(self, package: dict[str, Any]) -> None:
        package["updated_at"] = _now(); _atomic_write(self._manifest(package["package_id"]), package)

    def update_category(self, package: dict[str, Any], asset_id: str, category: str) -> dict[str, Any]:
        return self.update_asset_classification(package, asset_id, category=category)

    def update_asset_classification(
        self,
        package: dict[str, Any],
        asset_id: str,
        *,
        category: str | None = None,
        document_type: str | None = None,
    ) -> dict[str, Any]:
        if category is None and document_type is None:
            raise MaterialStorageError("请选择要修改的资料分类")
        if category is not None and category not in CATEGORIES:
            raise MaterialStorageError("资料分类不合法")
        if document_type is not None and document_type not in DOCUMENT_TYPES:
            raise MaterialStorageError("备课文档类型不合法")
        asset = next((a for a in package.get("assets", []) if a.get("asset_id") == asset_id), None)
        if not asset: raise FileNotFoundError(asset_id)
        if category is not None:
            asset["category"] = category
        if document_type is not None:
            asset["document_type"] = document_type
            asset["document_type_reason"] = "教师确认"
            asset["classification_confidence"] = 1.0
            asset["classification_source"] = "teacher"
            asset["classification_version"] = "teacher_confirmed_v1"
            understanding = package.get("material_understanding") or {}
            low_confidence = {
                str(value) for value in understanding.get("low_confidence_asset_ids") or []
            }
            low_confidence.discard(str(asset_id))
            understanding["low_confidence_asset_ids"] = sorted(low_confidence)
            available_types = {
                str(item.get("document_type") or "") for item in package.get("assets") or []
            }
            expected = ("outline", "lesson_plan", "script", "ppt", "question_bank")
            understanding["missing_document_types"] = [value for value in expected if value not in available_types]
            package["material_understanding"] = understanding
        self.save(package)
        return asset

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

    def _asset(self, package: dict[str, Any], asset_id: str) -> dict[str, Any]:
        asset = next((item for item in package.get("assets", []) if item.get("asset_id") == asset_id), None)
        if not asset:
            raise FileNotFoundError(asset_id)
        return asset

    def _assert_assets_unreferenced(self, package: dict[str, Any], asset_ids: set[str], *, folder: bool = False) -> None:
        referenced_targets = [
            str(item.get("target_label") or item.get("target_id") or "")
            for item in package.get("relationships", [])
            if item.get("source_asset_id") in asset_ids
        ]
        if not referenced_targets:
            return
        target_summary = "、".join(dict.fromkeys(filter(None, referenced_targets)))
        prefix = "文件夹中有原件" if folder else "该原件"
        raise MaterialStorageError(f"{prefix}仍被正式文件引用（{target_summary}），请先解除引用后再操作")

    def _validate_destination_folder(self, package: dict[str, Any], value: str) -> str:
        raw = str(value or "").replace("\\", "/").strip().strip("/")
        if not raw:
            return ""
        normalized = normalize_relative_path(raw)
        folders = set(package_folder_paths(package)) | MANAGED_UPLOAD_FOLDERS
        if normalized not in folders:
            raise MaterialStorageError("目标文件夹不存在")
        return normalized

    def _validate_filename(self, asset: dict[str, Any], value: str) -> str:
        filename = str(value or "").strip()
        if not filename or len(PurePosixPath(filename).parts) != 1 or filename in {".", ".."}:
            raise MaterialStorageError("文件名不合法")
        extension = Path(filename).suffix.lower()
        if extension != str(asset.get("extension") or "").lower():
            raise MaterialStorageError("重命名不能改变文件类型")
        return filename

    def _assert_paths_available(
        self,
        package: dict[str, Any],
        paths: dict[str, str],
        *,
        ignored_asset_ids: set[str] | None = None,
    ) -> None:
        ignored = ignored_asset_ids or set()
        existing = {
            str(item.get("relative_path") or "")
            for item in package.get("assets", [])
            if item.get("asset_id") not in ignored
        }
        folder_paths = set(package_folder_paths(package))
        values = list(paths.values())
        if len(set(values)) != len(values):
            raise MaterialStorageError("目标文件夹中存在同名文件")
        conflict = next((value for value in values if value in existing or value in folder_paths), None)
        if conflict:
            raise MaterialStorageError(f"目标位置已存在：{PurePosixPath(conflict).name}")

    def _move_materialized_file(self, package: dict[str, Any], asset: dict[str, Any], destination_path: str) -> None:
        source = self._content_path(package["package_id"], str(asset.get("relative_path") or ""))
        destination = self._content_path(package["package_id"], destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            source.replace(destination)

    def relocate_asset(
        self,
        package: dict[str, Any],
        asset_id: str,
        *,
        filename: str | None = None,
        parent_path: str | None = None,
    ) -> dict[str, Any]:
        asset = self._asset(package, asset_id)
        current = PurePosixPath(str(asset.get("relative_path") or asset.get("filename") or ""))
        target_name = self._validate_filename(asset, filename if filename is not None else str(asset.get("filename") or current.name))
        target_parent = self._validate_destination_folder(package, str(current.parent) if parent_path is None and str(current.parent) != "." else str(parent_path or ""))
        target_path = str(PurePosixPath(target_parent, target_name)) if target_parent else target_name
        if target_path == str(asset.get("relative_path") or ""):
            return asset
        self._assert_paths_available(package, {asset_id: target_path}, ignored_asset_ids={asset_id})
        self._move_materialized_file(package, asset, target_path)
        asset.update({"filename": target_name, "relative_path": target_path, "materialized_path": target_path, "updated_at": _now()})
        self.save(package)
        return asset

    def relocate_assets(self, package: dict[str, Any], asset_ids: list[str], parent_path: str) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(str(value or "") for value in asset_ids if value))
        if not ids:
            raise MaterialStorageError("请选择要移动的文件")
        assets = [self._asset(package, asset_id) for asset_id in ids]
        target_parent = self._validate_destination_folder(package, parent_path)
        paths = {
            str(asset["asset_id"]): str(PurePosixPath(target_parent, str(asset["filename"]))) if target_parent else str(asset["filename"])
            for asset in assets
        }
        self._assert_paths_available(package, paths, ignored_asset_ids=set(ids))
        for asset in assets:
            target_path = paths[str(asset["asset_id"])]
            if target_path != str(asset.get("relative_path") or ""):
                self._move_materialized_file(package, asset, target_path)
                asset.update({"relative_path": target_path, "materialized_path": target_path, "updated_at": _now()})
        self.save(package)
        return assets

    def relocate_folder(
        self,
        package: dict[str, Any],
        folder_path: str,
        *,
        name: str | None = None,
        parent_path: str | None = None,
    ) -> dict[str, Any]:
        source_path = normalize_relative_path(folder_path)
        if source_path in MANAGED_UPLOAD_FOLDERS:
            raise MaterialStorageError("系统目录不能重命名或移动")
        entries = package.get("entries", [])
        source_entry = next(
            (item for item in entries if item.get("kind") == "folder" and item.get("custom") and str(item.get("path") or item.get("name") or "") == source_path),
            None,
        )
        if not source_entry:
            raise MaterialStorageError("系统目录不能重命名或移动")
        source = PurePosixPath(source_path)
        target_name = str(name if name is not None else source.name).strip()
        if not target_name or len(PurePosixPath(target_name).parts) != 1 or Path(target_name).suffix:
            raise MaterialStorageError("文件夹名称不合法")
        current_parent = "" if str(source.parent) == "." else str(source.parent)
        target_parent = self._validate_destination_folder(package, current_parent if parent_path is None else parent_path)
        if target_parent == source_path or target_parent.startswith(f"{source_path}/"):
            raise MaterialStorageError("不能把文件夹移动到自身内部")
        destination_path = str(PurePosixPath(target_parent, target_name)) if target_parent else target_name
        if destination_path == source_path:
            return source_entry
        existing_folders = set(package_folder_paths(package))
        if destination_path in existing_folders:
            raise MaterialStorageError("目标位置已有同名文件夹")
        affected_assets = [item for item in package.get("assets", []) if str(item.get("relative_path") or "").startswith(f"{source_path}/")]
        asset_paths = {
            str(item["asset_id"]): f"{destination_path}{str(item['relative_path'])[len(source_path):]}"
            for item in affected_assets
        }
        self._assert_paths_available(package, asset_paths, ignored_asset_ids=set(asset_paths))
        source_directory = self._content_path(package["package_id"], source_path)
        destination_directory = self._content_path(package["package_id"], destination_path)
        destination_directory.parent.mkdir(parents=True, exist_ok=True)
        if source_directory.exists():
            source_directory.replace(destination_directory)
        else:
            destination_directory.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            entry_path = str(entry.get("path") or entry.get("name") or "")
            if entry_path == source_path or entry_path.startswith(f"{source_path}/"):
                entry["path"] = f"{destination_path}{entry_path[len(source_path):]}"
                if entry_path == source_path:
                    entry["name"] = target_name
        for asset in affected_assets:
            target_path = asset_paths[str(asset["asset_id"])]
            asset.update({"relative_path": target_path, "materialized_path": target_path, "updated_at": _now()})
        self.save(package)
        return source_entry

    def trash_assets(self, package: dict[str, Any], asset_ids: list[str]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(str(value or "") for value in asset_ids if value))
        if not ids:
            raise MaterialStorageError("请选择要移入回收站的文件")
        assets = [self._asset(package, asset_id) for asset_id in ids]
        self._assert_assets_unreferenced(package, set(ids))
        records = []
        for asset in assets:
            record = {
                "trash_id": f"trash-{uuid.uuid4().hex}",
                "kind": "asset",
                "name": str(asset.get("filename") or ""),
                "original_path": str(asset.get("relative_path") or ""),
                "deleted_at": _now(),
                "item_count": 1,
                "size_bytes": int(asset.get("size_bytes") or 0),
                "asset": dict(asset),
            }
            records.append(record)
            materialized = self._content_path(package["package_id"], str(asset.get("relative_path") or ""))
            if materialized.is_file():
                materialized.unlink()
        package["assets"] = [item for item in package.get("assets", []) if item.get("asset_id") not in set(ids)]
        package.setdefault("trash", []).extend(records)
        self.save(package)
        return records

    def trash_folder(self, package: dict[str, Any], folder_path: str) -> dict[str, Any]:
        normalized = normalize_relative_path(folder_path)
        if normalized in MANAGED_UPLOAD_FOLDERS:
            raise MaterialStorageError("系统目录不能移入回收站")
        entries = package.get("entries", [])
        source_entry = next(
            (item for item in entries if item.get("kind") == "folder" and item.get("custom") and str(item.get("path") or item.get("name") or "") == normalized),
            None,
        )
        if not source_entry:
            raise MaterialStorageError("系统目录不能移入回收站")
        prefix = f"{normalized}/"
        affected_assets = [item for item in package.get("assets", []) if str(item.get("relative_path") or "").startswith(prefix)]
        affected_entries = [item for item in entries if str(item.get("path") or item.get("name") or "") == normalized or str(item.get("path") or item.get("name") or "").startswith(prefix)]
        asset_ids = {str(item.get("asset_id") or "") for item in affected_assets}
        self._assert_assets_unreferenced(package, asset_ids, folder=True)
        record = {
            "trash_id": f"trash-{uuid.uuid4().hex}",
            "kind": "folder",
            "name": PurePosixPath(normalized).name,
            "original_path": normalized,
            "deleted_at": _now(),
            "item_count": len(affected_assets) + len(affected_entries),
            "size_bytes": sum(int(item.get("size_bytes") or 0) for item in affected_assets),
            "assets": [dict(item) for item in affected_assets],
            "entries": [dict(item) for item in affected_entries],
        }
        destination = self._content_path(package["package_id"], normalized)
        if destination.is_dir():
            shutil.rmtree(destination)
        package["assets"] = [item for item in package.get("assets", []) if str(item.get("asset_id") or "") not in asset_ids]
        package["entries"] = [item for item in entries if item not in affected_entries]
        package.setdefault("trash", []).append(record)
        self.save(package)
        return record

    def restore_trash(self, package: dict[str, Any], trash_ids: list[str]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(str(value or "") for value in trash_ids if value))
        records = [item for item in package.get("trash", []) if item.get("trash_id") in ids]
        if len(records) != len(ids):
            raise FileNotFoundError(next((value for value in ids if not any(item.get("trash_id") == value for item in records)), "trash"))
        active_paths = {str(item.get("relative_path") or "") for item in package.get("assets", [])}
        active_folders = set(package_folder_paths(package))
        restored_assets: list[dict[str, Any]] = []
        restored_entries: list[dict[str, Any]] = []
        for record in records:
            assets = [record.get("asset")] if record.get("kind") == "asset" else list(record.get("assets") or [])
            entries = [] if record.get("kind") == "asset" else list(record.get("entries") or [])
            for asset in assets:
                path = str(asset.get("relative_path") or "")
                if path in active_paths:
                    raise MaterialStorageError(f"原位置已存在同名文件：{PurePosixPath(path).name}")
                active_paths.add(path)
                restored_assets.append(dict(asset))
            for entry in entries:
                path = str(entry.get("path") or entry.get("name") or "")
                if path in active_folders:
                    raise MaterialStorageError(f"原位置已存在同名文件夹：{PurePosixPath(path).name}")
                active_folders.add(path)
                restored_entries.append(dict(entry))
        package.setdefault("assets", []).extend(restored_assets)
        package.setdefault("entries", []).extend(restored_entries)
        for entry in restored_entries:
            self._content_path(package["package_id"], str(entry.get("path") or entry.get("name") or "")).mkdir(parents=True, exist_ok=True)
        for asset in restored_assets:
            if asset.get("source_kind") == MATERIAL_REFERENCE_KIND:
                continue
            source = self._path(package["package_id"]) / "files" / str(asset.get("stored_name") or "")
            destination = self._content_path(package["package_id"], str(asset.get("relative_path") or ""))
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        package["trash"] = [item for item in package.get("trash", []) if item.get("trash_id") not in set(ids)]
        self.save(package)
        return records

    def purge_trash(self, package: dict[str, Any], trash_ids: list[str] | None = None) -> dict[str, int]:
        selected_ids = set(str(value or "") for value in (trash_ids or []) if value)
        records = [item for item in package.get("trash", []) if not selected_ids or item.get("trash_id") in selected_ids]
        if selected_ids and len(records) != len(selected_ids):
            raise FileNotFoundError("trash")
        deleted_assets = 0
        for record in records:
            assets = [record.get("asset")] if record.get("kind") == "asset" else list(record.get("assets") or [])
            for asset in filter(None, assets):
                deleted_assets += 1
                if asset.get("source_kind") == MATERIAL_REFERENCE_KIND:
                    continue
                source = self._path(package["package_id"]) / "files" / str(asset.get("stored_name") or "")
                if source.is_file():
                    source.unlink()
        removed_ids = {str(item.get("trash_id") or "") for item in records}
        package["trash"] = [item for item in package.get("trash", []) if str(item.get("trash_id") or "") not in removed_ids]
        self.save(package)
        return {"deleted_items": len(records), "deleted_assets": deleted_assets}

    def delete_asset(self, package: dict[str, Any], asset_id: str) -> dict[str, Any]:
        asset = next((item for item in package.get("assets", []) if item.get("asset_id") == asset_id), None)
        if not asset:
            raise FileNotFoundError(asset_id)
        referenced_targets = [
            str(item.get("target_label") or item.get("target_id") or "")
            for item in package.get("relationships", [])
            if item.get("source_asset_id") == asset_id
        ]
        if referenced_targets:
            target_summary = "、".join(dict.fromkeys(filter(None, referenced_targets)))
            raise MaterialStorageError(
                f"该原件仍被正式文件引用（{target_summary}），请先解除引用后再删除"
            )
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
        package["relationships"] = [
            item for item in package.get("relationships", [])
            if item.get("source_asset_id") != asset_id
        ]
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
        affected_ids = {item["asset_id"] for item in affected_assets}
        referenced_targets = [
            str(item.get("target_label") or item.get("target_id") or "")
            for item in package.get("relationships", [])
            if item.get("source_asset_id") in affected_ids
        ]
        if referenced_targets:
            target_summary = "、".join(dict.fromkeys(filter(None, referenced_targets)))
            raise MaterialStorageError(
                f"文件夹中有原件仍被正式文件引用（{target_summary}），请先解除引用后再删除"
            )
        for asset in affected_assets:
            # 引用条目没有包内副本，跳过（同 delete_asset：不碰底层 mat-* 资产）。
            if asset.get("source_kind") == MATERIAL_REFERENCE_KIND:
                continue
            source = self._path(package["package_id"]) / "files" / str(asset["stored_name"])
            if source.is_file():
                source.unlink()
        if destination.is_dir():
            shutil.rmtree(destination)
        package["assets"] = [item for item in package.get("assets", []) if item.get("asset_id") not in affected_ids]
        package["relationships"] = [
            item for item in package.get("relationships", [])
            if item.get("source_asset_id") not in affected_ids
        ]
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
        package["preparation_status"] = "skipped"
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

    # --- 正式课程文件与原始资料的双向关系 ---------------------------------

    def replace_formal_relationships(
        self,
        package: dict[str, Any],
        *,
        target_id: str,
        target_type: str,
        target_label: str,
        sources: list[dict[str, str]],
        target_revision: str = "",
        binding_mode: str = "manual",
    ) -> list[dict[str, Any]]:
        """替换一个正式文件的来源集合；来源只能是老师上传的原始资料。"""
        normalized_target_id = str(target_id or "").strip()
        normalized_target_type = str(target_type or "").strip()
        if not normalized_target_id or len(normalized_target_id) > 240:
            raise MaterialStorageError("正式文件标识不合法")
        if normalized_target_type not in FORMAL_FILE_TYPES:
            raise MaterialStorageError("正式文件类型不合法")

        assets = {
            str(item.get("asset_id") or ""): item
            for item in package.get("assets", [])
        }
        normalized_sources: list[tuple[dict[str, Any], str]] = []
        seen: set[str] = set()
        primary_count = 0
        for source in sources:
            source_asset_id = str(source.get("source_asset_id") or "").strip()
            role = str(source.get("role") or "reference").strip()
            if role not in {"primary", "reference", "question_source"}:
                raise MaterialStorageError("引用角色不合法")
            if role == "question_source" and normalized_target_type != "question_bank":
                raise MaterialStorageError("真题资料只能关联课程题库")
            if source_asset_id in seen:
                continue
            asset = assets.get(source_asset_id)
            if asset is None:
                raise FileNotFoundError(source_asset_id)
            if role == "primary":
                primary_count += 1
            seen.add(source_asset_id)
            normalized_sources.append((asset, role))
        if primary_count > 1:
            raise MaterialStorageError("一个正式文件只能有一个主来源")

        now = _now()
        relationships = [
            item for item in package.get("relationships", [])
            if str(item.get("target_id") or "") != normalized_target_id
        ]
        created: list[dict[str, Any]] = []
        for asset, role in normalized_sources:
            relationship = {
                "link_id": f"tcr-{uuid.uuid4().hex}",
                "source_asset_id": str(asset.get("asset_id") or ""),
                "material_asset_id": str(asset.get("material_asset_id") or ""),
                "source_label": str(asset.get("filename") or ""),
                "target_id": normalized_target_id,
                "target_type": normalized_target_type,
                "target_label": str(target_label or normalized_target_id).strip(),
                "target_revision": str(target_revision or "").strip(),
                "role": role,
                "created_at": now,
                "updated_at": now,
            }
            relationships.append(relationship)
            created.append(relationship)
        package["relationships"] = relationships
        package.setdefault("source_binding_targets", {})[normalized_target_id] = {
            "mode": "auto" if binding_mode == "auto" else "manual",
            "updated_at": now,
        }
        self.save(package)
        return created

    def relationships_for_target(
        self, package: dict[str, Any], target_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(item) for item in package.get("relationships", [])
            if str(item.get("target_id") or "") == str(target_id or "")
        ]

    def relationships_for_source(
        self, package: dict[str, Any], source_asset_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(item) for item in package.get("relationships", [])
            if str(item.get("source_asset_id") or "") == str(source_asset_id or "")
        ]

teacher_course_space_repository = TeacherCourseSpaceRepository()
