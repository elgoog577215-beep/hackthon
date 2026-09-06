"""Version-aware current learning state stored separately from learning events."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage import storage

SCHEMA_VERSION = 2


class SnapshotConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("learning snapshot revision conflict")
        self.current = current


class LearningSnapshotRepository:
    """Atomic per-user/course current snapshot repository."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def load(self, user_id: str, course_id: str) -> dict[str, Any] | None:
        key = self._key(user_id, course_id)
        with self._lock(key):
            return self._read(self._path(key))

    def save(
        self,
        user_id: str,
        course_id: str,
        *,
        expected_revision: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            current = self._read(path)
            current_revision = int((current or {}).get("revision") or 0)
            if current_revision != expected_revision:
                raise SnapshotConflict(deepcopy(current or {}))

            now = _now()
            saved = deepcopy(payload)
            saved.update({
                "snapshot_id": (current or {}).get("snapshot_id") or f"ls_{key[:24]}",
                "user_id": user_id,
                "course_id": course_id,
                "revision": current_revision + 1,
                "schema_version": SCHEMA_VERSION,
                "created_at": (current or {}).get("created_at") or now,
                "updated_at": now,
            })
            self._write_atomic(path, saved)
            return deepcopy(saved)

    def delete(self, user_id: str, course_id: str) -> bool:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            if not path.exists():
                return False
            path.unlink()
            return True

    def _key(self, user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _lock(self, key: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    def _read(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return _normalize_snapshot(data) if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            corrupt = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass
            return None

    def _write_atomic(self, path: Path, data: dict[str, Any]) -> None:
        temp = path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(data)
    task = snapshot.get("task_state") if isinstance(snapshot.get("task_state"), dict) else {}
    snapshot["task_state"] = {
        "kind": str(task.get("kind") or "reading"),
        "object_id": str(task.get("object_id") or ""),
        "task_revision_id": str(
            task.get("task_revision_id")
            or (task.get("metadata") or {}).get("task_revision_id")
            or ""
        ),
        "status": str(task.get("status") or "active"),
        "context": deepcopy(task.get("context") or {}),
        "return_node_id": str(task.get("return_node_id") or snapshot.get("node_id") or ""),
        "draft_revision": int(task.get("draft_revision") or 0),
        "metadata": deepcopy(task.get("metadata") or {}),
    }
    return snapshot


learning_snapshot_repository = LearningSnapshotRepository(
    Path(storage._data_dir) / "learning_snapshots"
)


__all__ = [
    "LearningSnapshotRepository",
    "SCHEMA_VERSION",
    "SnapshotConflict",
    "learning_snapshot_repository",
]
