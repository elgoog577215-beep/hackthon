"""Teacher-scoped teaching calendar persistence.

The calendar is deliberately kept separate from the canonical course document in
V1.  It references course lesson units, but saving a schedule never mutates the
course outline.  Files are written atomically and protected by an optimistic
revision so two browser tabs cannot silently overwrite each other.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


TEACHING_CALENDAR_DIR = Path(__file__).resolve().parent / "data" / "teaching_calendars"
_SAFE_COURSE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")


class TeachingCalendarError(RuntimeError):
    """Base error for calendar persistence."""


class TeachingCalendarValidationError(TeachingCalendarError):
    """Raised when a storage identifier is unsafe or malformed."""


class TeachingCalendarConflict(TeachingCalendarError):
    """Raised when the submitted base revision is stale."""

    def __init__(self, current_revision: int):
        super().__init__("教学日历已在其他位置更新，请刷新后重试")
        self.current_revision = current_revision


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _owner_key(owner_id: str) -> str:
    value = str(owner_id or "").strip()
    if not value:
        raise TeachingCalendarValidationError("教师身份不能为空")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _course_key(course_id: str) -> str:
    value = str(course_id or "").strip()
    if not _SAFE_COURSE_ID.fullmatch(value):
        raise TeachingCalendarValidationError("课程标识格式无效")
    return value


def _public_calendar(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop("owner_id", None)
    return result


class TeachingCalendarRepository:
    def __init__(self, root: Path | str = TEACHING_CALENDAR_DIR):
        self.root = Path(root)

    def _path(self, owner_id: str, course_id: str) -> Path:
        return self.root / _owner_key(owner_id) / f"{_course_key(course_id)}.json"

    def empty(self, course_id: str, course_title: str = "") -> dict[str, Any]:
        return {
            "schema_version": "teaching_calendar_v1",
            "course_id": _course_key(course_id),
            "course_title": str(course_title or "").strip(),
            "academic_year": "",
            "term": "",
            "timezone": "Asia/Shanghai",
            "status": "draft",
            "source_outline_revision": "",
            "revision": 0,
            "sessions": [],
            "created_at": "",
            "updated_at": "",
        }

    def load(self, owner_id: str, course_id: str, course_title: str = "") -> dict[str, Any]:
        path = self._path(owner_id, course_id)
        if not path.exists():
            return self.empty(course_id, course_title)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TeachingCalendarError("教学日历文件读取失败") from exc
        if not isinstance(value, dict):
            raise TeachingCalendarError("教学日历文件格式无效")
        if course_title and not str(value.get("course_title") or "").strip():
            value["course_title"] = course_title
        return _public_calendar(value)

    def save(
        self,
        owner_id: str,
        course_id: str,
        payload: dict[str, Any],
        base_revision: int,
    ) -> dict[str, Any]:
        path = self._path(owner_id, course_id)
        current = self.load(owner_id, course_id)
        current_revision = int(current.get("revision") or 0)
        if int(base_revision) != current_revision:
            raise TeachingCalendarConflict(current_revision)

        now = _utc_now()
        sessions: list[dict[str, Any]] = []
        for index, raw in enumerate(payload.get("sessions") or []):
            item = deepcopy(raw)
            item["session_id"] = str(item.get("session_id") or f"tcsess-{uuid4().hex}")
            item["sequence"] = index + 1
            item["updated_at"] = now
            item.setdefault("created_at", now)
            sessions.append(item)

        value = {
            "schema_version": "teaching_calendar_v1",
            "owner_id": str(owner_id).strip(),
            "course_id": _course_key(course_id),
            "course_title": str(payload.get("course_title") or current.get("course_title") or "").strip(),
            "academic_year": str(payload.get("academic_year") or "").strip(),
            "term": str(payload.get("term") or "").strip(),
            "timezone": str(payload.get("timezone") or "Asia/Shanghai").strip(),
            "status": str(payload.get("status") or "draft").strip(),
            "source_outline_revision": str(payload.get("source_outline_revision") or "").strip(),
            "revision": current_revision + 1,
            "sessions": sessions,
            "created_at": str(current.get("created_at") or now),
            "updated_at": now,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".tmp",
                prefix=f"{path.stem}-",
                dir=path.parent,
                delete=False,
            ) as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
            raise TeachingCalendarError("教学日历保存失败") from exc
        return _public_calendar(value)

    def list_sessions(
        self,
        owner_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        owner_root = self.root / _owner_key(owner_id)
        if not owner_root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(owner_root.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            course_id = str(value.get("course_id") or path.stem)
            course_title = str(value.get("course_title") or "未命名课程")
            for raw in value.get("sessions") or []:
                session_date = str(raw.get("date") or "")
                if not session_date or str(raw.get("status") or "scheduled") == "cancelled":
                    continue
                try:
                    parsed = date.fromisoformat(session_date)
                except ValueError:
                    continue
                if date_from and parsed < date_from:
                    continue
                if date_to and parsed > date_to:
                    continue
                item = deepcopy(raw)
                item.update({
                    "course_id": course_id,
                    "course_title": course_title,
                    "calendar_revision": int(value.get("revision") or 0),
                    "course_color_key": int(hashlib.sha256(course_id.encode("utf-8")).hexdigest()[:4], 16) % 8,
                })
                rows.append(item)
        rows.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("start_time") or ""), str(item.get("course_title") or "")))
        return rows


teaching_calendar_repository = TeachingCalendarRepository()


__all__ = [
    "TEACHING_CALENDAR_DIR",
    "TeachingCalendarConflict",
    "TeachingCalendarError",
    "TeachingCalendarRepository",
    "TeachingCalendarValidationError",
    "teaching_calendar_repository",
]
