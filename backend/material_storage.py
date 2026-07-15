"""课程资料资产的文件系统仓库。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from material_models import MaterialAsset, ParsedDocument

MATERIALS_DIR = Path(__file__).resolve().parent / "data" / "materials"
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
}
TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}


class MaterialStorageError(ValueError):
    """资料上传或存储不符合约束。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


class MaterialRepository:
    def __init__(self, root: Path | str = MATERIALS_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._upload_lock = asyncio.Lock()

    def _asset_dir(self, asset_id: str) -> Path:
        if not asset_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in asset_id):
            raise MaterialStorageError("资料 ID 不合法")
        return self.root / asset_id

    def _manifest_path(self, asset_id: str) -> Path:
        return self._asset_dir(asset_id) / "manifest.json"

    def get_asset(self, asset_id: str) -> MaterialAsset | None:
        path = self._manifest_path(asset_id)
        if not path.exists():
            return None
        try:
            return MaterialAsset.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def public_asset(self, asset: MaterialAsset) -> dict[str, Any]:
        data = asset.model_dump(mode="json")
        data.pop("source_name", None)
        return data

    def source_path(self, asset: MaterialAsset) -> Path:
        path = self._asset_dir(asset.asset_id) / asset.source_name
        if not path.is_file():
            raise MaterialStorageError("资料原文件不存在")
        return path

    def save_asset(self, asset: MaterialAsset) -> None:
        asset.updated_at = _now()
        _atomic_json(self._manifest_path(asset.asset_id), asset.model_dump(mode="json"))

    async def save_upload(
        self,
        upload: Any,
        *,
        upload_batch_id: str = "",
        max_bytes: int | None = None,
    ) -> MaterialAsset:
        filename = str(getattr(upload, "filename", "") or "").strip()
        if not filename or filename != Path(filename).name or "/" in filename or "\\" in filename or "\x00" in filename:
            raise MaterialStorageError("文件名不安全")
        if len(filename) > 300:
            raise MaterialStorageError("文件名过长")
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise MaterialStorageError(f"不支持的文件类型：{extension or '无扩展名'}")

        limit = max_bytes or int(os.getenv("MATERIAL_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES))
        temp_dir = self.root / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid.uuid4().hex}.upload"
        digest = hashlib.sha256()
        size = 0
        prefix = b""
        try:
            with temp_path.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise MaterialStorageError(f"文件过大，单文件最大支持 {limit // (1024 * 1024)} MB")
                    if len(prefix) < 16:
                        prefix += chunk[: 16 - len(prefix)]
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if size == 0:
                raise MaterialStorageError("上传文件为空")
            detected_mime = self._detect_mime(extension, prefix, temp_path)
            sha256 = digest.hexdigest()

            async with self._upload_lock:
                existing = self._find_by_hash(sha256)
                if existing:
                    temp_path.unlink(missing_ok=True)
                    return existing

                asset_id = f"mat-{uuid.uuid4().hex}"
                asset_dir = self._asset_dir(asset_id)
                asset_dir.mkdir(parents=True, exist_ok=False)
                source_name = f"source{extension}"
                os.replace(temp_path, asset_dir / source_name)
                now = _now()
                asset = MaterialAsset(
                    asset_id=asset_id,
                    filename=filename,
                    extension=extension,
                    mime_type=str(getattr(upload, "content_type", "") or "application/octet-stream"),
                    detected_mime=detected_mime,
                    size_bytes=size,
                    sha256=sha256,
                    source_name=source_name,
                    upload_batch_id=upload_batch_id,
                    uploaded_at=now,
                    updated_at=now,
                )
                self.save_asset(asset)
                return asset
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    async def create_text_asset(
        self,
        *,
        filename: str,
        content: str,
        upload_batch_id: str = "legacy",
    ) -> MaterialAsset:
        class _TextUpload:
            def __init__(self, name: str, value: str) -> None:
                self.filename = Path(name).name or "legacy-material.md"
                if Path(self.filename).suffix.lower() not in TEXT_EXTENSIONS:
                    self.filename += ".md"
                self.content_type = "text/markdown"
                self._content = value.encode("utf-8")
                self._read = False

            async def read(self, _size: int) -> bytes:
                if self._read:
                    return b""
                self._read = True
                return self._content

        return await self.save_upload(
            _TextUpload(filename, content),
            upload_batch_id=upload_batch_id,
        )

    def bind_asset(self, asset_id: str, course_id: str) -> MaterialAsset:
        asset = self.get_asset(asset_id)
        if not asset:
            raise MaterialStorageError(f"资料不存在：{asset_id}")
        if course_id not in asset.bound_course_ids:
            asset.bound_course_ids.append(course_id)
            self.save_asset(asset)
        return asset

    def update_status(
        self,
        asset_id: str,
        status: str,
        *,
        error: str = "",
        warnings: list[str] | None = None,
        parser_name: str = "",
        parser_version: str = "",
        parse_options_hash: str = "",
        parse_quality: dict[str, Any] | None = None,
    ) -> MaterialAsset:
        asset = self.get_asset(asset_id)
        if not asset:
            raise MaterialStorageError(f"资料不存在：{asset_id}")
        asset.status = status  # type: ignore[assignment]
        asset.error = error
        asset.warnings = warnings or []
        asset.parser_name = parser_name
        asset.parser_version = parser_version
        asset.parse_options_hash = parse_options_hash
        asset.parse_quality = parse_quality or {}
        self.save_asset(asset)
        return asset

    def save_parsed_document(self, document: ParsedDocument) -> None:
        _atomic_json(
            self._asset_dir(document.asset_id) / "parsed_document.json",
            document.model_dump(mode="json"),
        )

    def load_parsed_document(self, asset_id: str) -> ParsedDocument | None:
        path = self._asset_dir(asset_id) / "parsed_document.json"
        if not path.exists():
            return None
        try:
            return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def save_evidence(self, asset_id: str, evidence: list[dict[str, Any]]) -> None:
        _atomic_json(self._asset_dir(asset_id) / "evidence.json", evidence)

    def load_evidence(self, asset_id: str) -> list[dict[str, Any]]:
        path = self._asset_dir(asset_id) / "evidence.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def delete_unbound(self, asset_id: str) -> bool:
        asset = self.get_asset(asset_id)
        if not asset:
            return False
        if asset.bound_course_ids:
            raise MaterialStorageError("资料已被课程使用，不能直接删除")
        shutil.rmtree(self._asset_dir(asset_id))
        return True

    def _find_by_hash(self, sha256: str) -> MaterialAsset | None:
        for path in self.root.glob("mat-*/manifest.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("sha256") == sha256:
                    asset = MaterialAsset.model_validate(data)
                    if (path.parent / asset.source_name).exists():
                        return asset
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return None

    @staticmethod
    def _detect_mime(extension: str, prefix: bytes, path: Path) -> str:
        if extension == ".pdf":
            if not prefix.startswith(b"%PDF-"):
                raise MaterialStorageError("文件内容不是有效 PDF")
            return "application/pdf"
        if extension in OFFICE_EXTENSIONS:
            if not prefix.startswith(b"PK"):
                raise MaterialStorageError("Office 文件结构无效")
            return {
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }[extension]
        if extension in TEXT_EXTENSIONS:
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise MaterialStorageError("文本资料必须使用 UTF-8 编码") from exc
            return mimetypes.guess_type(f"file{extension}")[0] or "text/plain"
        raise MaterialStorageError("不支持的文件类型")


material_repository = MaterialRepository()


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_FILE_BYTES",
    "MATERIALS_DIR",
    "MaterialRepository",
    "MaterialStorageError",
    "TEXT_EXTENSIONS",
    "material_repository",
]
