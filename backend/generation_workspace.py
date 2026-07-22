"""Isolated persistence for recoverable course-generation drafts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable
import uuid

from storage import DATA_DIR


GENERATION_WORKSPACE_SCHEMA = "generation_workspace_v1"
GENERATION_NODE_DRAFT_SCHEMA = "generation_node_draft_v1"
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
        result = deepcopy(course_data)
        self._overlay_node_drafts(workspace_id, result)
        return result

    def save_node_draft(
        self,
        workspace_id: str,
        node_id: str,
        content: str,
        *,
        generation_runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one streaming node without rewriting the whole course.

        The primary workspace stays the durable course snapshot.  These small
        sidecars are hot-path checkpoints that are overlaid when the course is
        read and removed after the node is finalized.
        """
        self._validate_id(workspace_id)
        self._validate_id(node_id)
        with self._lock(workspace_id):
            if not self._path(workspace_id).exists():
                raise GenerationWorkspaceNotFound(workspace_id)
            now = datetime.now(timezone.utc).isoformat()
            draft = {
                "schema_version": GENERATION_NODE_DRAFT_SCHEMA,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "content": str(content),
                "generation_runtime": deepcopy(generation_runtime or {}),
                "updated_at": now,
            }
            self._atomic_write(self._node_draft_path(workspace_id, node_id), draft)
            return deepcopy(draft)

    def clear_node_draft(self, workspace_id: str, node_id: str) -> bool:
        self._validate_id(workspace_id)
        self._validate_id(node_id)
        with self._lock(workspace_id):
            path = self._node_draft_path(workspace_id, node_id)
            removed = self._unlink_with_temp(path)
            self._remove_empty_draft_dir(workspace_id)
            return removed

    def clear_node_drafts(self, workspace_id: str) -> int:
        self._validate_id(workspace_id)
        with self._lock(workspace_id):
            draft_dir = self._node_draft_dir(workspace_id)
            if not draft_dir.exists():
                return 0
            removed = 0
            for path in draft_dir.iterdir():
                if path.is_file():
                    removed += int(self._unlink_with_temp(path))
            self._remove_empty_draft_dir(workspace_id)
            return removed

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
            if status in {"published", "cancelled", "deleted"}:
                self.clear_node_drafts(workspace_id)
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
            removed = self._unlink_with_temp(path)
            removed_drafts = self.clear_node_drafts(workspace_id)
            return removed or removed_drafts > 0

    def _path(self, workspace_id: str) -> Path:
        return self.root_dir / f"{workspace_id}.json"

    def _node_draft_dir(self, workspace_id: str) -> Path:
        return self.root_dir / ".node-drafts" / workspace_id

    def _node_draft_path(self, workspace_id: str, node_id: str) -> Path:
        return self._node_draft_dir(workspace_id) / f"{node_id}.json"

    def _overlay_node_drafts(
        self,
        workspace_id: str,
        course_data: dict[str, Any],
    ) -> None:
        nodes = {
            str(node.get("node_id") or ""): node
            for node in course_data.get("nodes") or []
            if isinstance(node, dict)
        }
        draft_dir = self._node_draft_dir(workspace_id)
        if not nodes or not draft_dir.exists():
            return
        for path in draft_dir.glob("*.json"):
            try:
                draft = self._read(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if draft.get("schema_version") != GENERATION_NODE_DRAFT_SCHEMA:
                continue
            node = nodes.get(str(draft.get("node_id") or ""))
            if not node:
                continue
            # A finalized node wins even if the process died between the main
            # workspace commit and best-effort sidecar cleanup.
            if (
                node.get("generation_status") == "completed"
                and str(node.get("node_content") or "").strip()
            ):
                continue
            content = str(draft.get("content") or "")
            if content:
                node["node_content_draft"] = content
                node["draft_checkpoint_updated_at"] = draft.get("updated_at")
            runtime = draft.get("generation_runtime")
            if isinstance(runtime, dict) and runtime:
                node["generation_runtime"] = deepcopy(runtime)

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
        temp = path.with_suffix(
            f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(6):
                try:
                    os.replace(temp, path)
                    break
                except OSError as exc:
                    retryable = (
                        isinstance(exc, PermissionError)
                        or getattr(exc, "winerror", None) in {5, 32}
                    )
                    if not retryable or attempt == 5:
                        raise
                    time.sleep(0.05 * (2 ** attempt))
        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _unlink_with_temp(path: Path) -> bool:
        removed = False
        if path.exists():
            path.unlink()
            removed = True
        temp = path.with_suffix(path.suffix + ".tmp")
        if temp.exists():
            temp.unlink()
        return removed

    def _remove_empty_draft_dir(self, workspace_id: str) -> None:
        draft_dir = self._node_draft_dir(workspace_id)
        if draft_dir.exists() and not any(draft_dir.iterdir()):
            draft_dir.rmdir()
        root = draft_dir.parent
        if root.exists() and not any(root.iterdir()):
            root.rmdir()


generation_workspace_repository = GenerationWorkspaceRepository()


__all__ = [
    "GENERATION_NODE_DRAFT_SCHEMA",
    "GENERATION_WORKSPACE_SCHEMA",
    "GenerationWorkspaceConflict",
    "GenerationWorkspaceNotFound",
    "GenerationWorkspaceRepository",
    "generation_workspace_repository",
]
