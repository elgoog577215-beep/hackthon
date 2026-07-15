"""Isolated persistence for recoverable course-generation drafts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable

from storage import DATA_DIR


GENERATION_WORKSPACE_SCHEMA = "generation_workspace_v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class GenerationWorkspaceNotFound(KeyError):
    pass


class GenerationWorkspaceConflict(RuntimeError):
    pass


class GenerationWorkspaceRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "generation_workspaces")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def create(
        self,
        workspace_id: str,
        *,
        course_id: str,
        course_data: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_id(workspace_id)
        self._validate_id(course_id)
        with self._lock(workspace_id):
            path = self._path(workspace_id)
            if path.exists():
                existing = self._read(path)
                if existing.get("course_id") != course_id:
                    raise GenerationWorkspaceConflict("Generation workspace belongs to another course")
                return deepcopy(existing)
            now = datetime.now(timezone.utc).isoformat()
            workspace = {
                "schema_version": GENERATION_WORKSPACE_SCHEMA,
                "workspace_id": workspace_id,
                "course_id": course_id,
                "status": "active",
                "course_data": deepcopy(course_data),
                "created_at": now,
                "updated_at": now,
                "result": {},
            }
            self._atomic_write(path, workspace)
            return deepcopy(workspace)

    def load(self, workspace_id: str) -> dict[str, Any]:
        self._validate_id(workspace_id)
        path = self._path(workspace_id)
        if not path.exists():
            raise GenerationWorkspaceNotFound(workspace_id)
        return self._read(path)

    def load_course(self, workspace_id: str) -> dict[str, Any]:
        workspace = self.load(workspace_id)
        course_data = workspace.get("course_data")
        if not isinstance(course_data, dict):
            raise GenerationWorkspaceConflict("Generation workspace course data is invalid")
        return deepcopy(course_data)

    def save_course(self, workspace_id: str, course_data: dict[str, Any]) -> dict[str, Any]:
        return self.update_course(workspace_id, lambda _current: deepcopy(course_data))

    def update_course(
        self,
        workspace_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any]:
        self._validate_id(workspace_id)
        with self._lock(workspace_id):
            workspace = self.load(workspace_id)
            current = deepcopy(workspace.get("course_data") or {})
            updated = updater(current)
            if updated is not None:
                current = updated
            if not isinstance(current, dict):
                raise GenerationWorkspaceConflict("Generation workspace updater returned invalid data")
            workspace["course_data"] = current
            workspace["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_write(self._path(workspace_id), workspace)
            return deepcopy(current)

    def set_status(
        self,
        workspace_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_id(workspace_id)
        with self._lock(workspace_id):
            workspace = self.load(workspace_id)
            workspace["status"] = status
            workspace["updated_at"] = datetime.now(timezone.utc).isoformat()
            if result is not None:
                workspace["result"] = deepcopy(result)
            self._atomic_write(self._path(workspace_id), workspace)
            return deepcopy(workspace)

    def record_recovery(
        self,
        workspace_id: str,
        *,
        reason: str,
        automatic: bool,
    ) -> dict[str, Any]:
        """Mark a workspace active again without discarding its last failure result."""
        self._validate_id(workspace_id)
        with self._lock(workspace_id):
            workspace = self.load(workspace_id)
            now = datetime.now(timezone.utc).isoformat()
            history = list(workspace.get("recovery_history") or [])
            history.append({
                "reason": reason,
                "automatic": bool(automatic),
                "recovered_at": now,
                "previous_status": workspace.get("status"),
            })
            workspace["status"] = "active"
            workspace["recovery_history"] = history[-50:]
            workspace["updated_at"] = now
            self._atomic_write(self._path(workspace_id), workspace)
            return deepcopy(workspace)

    def delete(self, workspace_id: str) -> bool:
        """Delete one workspace idempotently."""
        self._validate_id(workspace_id)
        with self._lock(workspace_id):
            path = self._path(workspace_id)
            if not path.exists():
                return False
            path.unlink()
            temp = path.with_suffix(path.suffix + ".tmp")
            if temp.exists():
                temp.unlink()
            return True

    def _path(self, workspace_id: str) -> Path:
        return self.root_dir / f"{workspace_id}.json"

    def _lock(self, workspace_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(workspace_id, threading.RLock())

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not _SAFE_ID.match(value):
            raise ValueError("Invalid generation workspace identifier")

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise GenerationWorkspaceConflict("Generation workspace must contain an object")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


generation_workspace_repository = GenerationWorkspaceRepository()


__all__ = [
    "GENERATION_WORKSPACE_SCHEMA",
    "GenerationWorkspaceConflict",
    "GenerationWorkspaceNotFound",
    "GenerationWorkspaceRepository",
    "generation_workspace_repository",
]
