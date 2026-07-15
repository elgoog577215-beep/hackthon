"""Persistent AI-teacher interaction coordination without learning-state copies."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any
import uuid

from storage import storage


SCHEMA_VERSION = 1
PROPOSAL_STATUSES = {
    "presented",
    "confirmed",
    "executing",
    "succeeded",
    "failed",
    "rejected",
    "expired",
    "stale",
    "cancelled",
}


class InteractionConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("AI teacher interaction revision conflict")
        self.current = current


class AITeacherRepository:
    """Atomic per-user/course store for conversations and action coordination."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def list_conversations(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        with self._guard(user_id, course_id) as data:
            return deepcopy(data["conversations"])

    def create_conversation(
        self,
        user_id: str,
        course_id: str,
        *,
        title: str = "",
        course_version_id: str = "",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        with self._guard(user_id, course_id, write=True) as data:
            requested_id = str(conversation_id or "")
            if requested_id:
                current = self._conversation(data, requested_id)
                if current:
                    return deepcopy(current)
            now = _now()
            conversation = {
                "conversation_id": requested_id or f"aic_{uuid.uuid4().hex}",
                "user_id": user_id,
                "course_id": course_id,
                "course_version_id": course_version_id,
                "title": _clip(title, 200) or "新对话",
                "revision": 1,
                "messages": [],
                "created_at": now,
                "updated_at": now,
            }
            data["conversations"].insert(0, conversation)
            return deepcopy(conversation)

    def get_conversation(
        self,
        user_id: str,
        course_id: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        with self._guard(user_id, course_id) as data:
            current = self._conversation(data, conversation_id)
            return deepcopy(current) if current else None

    def append_message(
        self,
        user_id: str,
        course_id: str,
        conversation_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._guard(user_id, course_id, write=True) as data:
            conversation = self._conversation(data, conversation_id)
            if not conversation:
                raise KeyError(conversation_id)
            now = _now()
            message = _sanitize_message(payload)
            message.update({
                "message_id": str(payload.get("message_id") or f"aim_{uuid.uuid4().hex}"),
                "conversation_id": conversation_id,
                "created_at": now,
            })
            existing = next((item for item in conversation["messages"] if item["message_id"] == message["message_id"]), None)
            if existing:
                return deepcopy(existing)
            conversation["messages"].append(message)
            conversation["messages"] = conversation["messages"][-200:]
            conversation["revision"] = int(conversation.get("revision") or 0) + 1
            conversation["updated_at"] = now
            if conversation.get("title") == "新对话" and message.get("role") == "user":
                conversation["title"] = _clip(str(message.get("content") or ""), 40) or "新对话"
            return deepcopy(message)

    def delete_conversation(
        self,
        user_id: str,
        course_id: str,
        conversation_id: str,
    ) -> bool:
        with self._guard(user_id, course_id, write=True) as data:
            before = len(data["conversations"])
            data["conversations"] = [
                item for item in data["conversations"]
                if item.get("conversation_id") != conversation_id
            ]
            if len(data["conversations"]) == before:
                return False
            data["proposals"] = [
                item for item in data["proposals"]
                if item.get("conversation_id") != conversation_id
                or item.get("status") in {"succeeded", "failed"}
            ]
            for receipt in data["receipts"]:
                if receipt.get("conversation_id") == conversation_id:
                    receipt["conversation_deleted"] = True
            return True

    def create_proposal(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._guard(user_id, course_id, write=True) as data:
            proposal_id = str(payload.get("proposal_id") or f"aip_{uuid.uuid4().hex}")
            existing = next((item for item in data["proposals"] if item.get("proposal_id") == proposal_id), None)
            if existing:
                return deepcopy(existing)
            dedupe_key = str(payload.get("dedupe_key") or "")
            if dedupe_key:
                active = next((
                    item for item in data["proposals"]
                    if item.get("dedupe_key") == dedupe_key
                    and item.get("status") in {"presented", "confirmed", "executing", "succeeded"}
                ), None)
                if active:
                    return deepcopy(active)
            now = _now()
            proposal = _sanitize_proposal(payload)
            proposal.update({
                "proposal_id": proposal_id,
                "user_id": user_id,
                "course_id": course_id,
                "status": "presented",
                "revision": 1,
                "created_at": now,
                "updated_at": now,
            })
            data["proposals"].append(proposal)
            return deepcopy(proposal)

    def get_proposal(
        self,
        user_id: str,
        course_id: str,
        proposal_id: str,
    ) -> dict[str, Any] | None:
        with self._guard(user_id, course_id) as data:
            current = next((item for item in data["proposals"] if item.get("proposal_id") == proposal_id), None)
            return deepcopy(current) if current else None

    def update_proposal(
        self,
        user_id: str,
        course_id: str,
        proposal_id: str,
        *,
        status: str,
        changes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in PROPOSAL_STATUSES:
            raise ValueError("invalid proposal status")
        with self._guard(user_id, course_id, write=True) as data:
            current = next((item for item in data["proposals"] if item.get("proposal_id") == proposal_id), None)
            if not current:
                raise KeyError(proposal_id)
            current["status"] = status
            for key, value in (changes or {}).items():
                if key in {"confirmed_at", "executed_at", "rejected_at", "failure_reason", "receipt_id"}:
                    current[key] = _sanitize(value)
            current["revision"] = int(current.get("revision") or 0) + 1
            current["updated_at"] = _now()
            return deepcopy(current)

    def receipt_for_key(
        self,
        user_id: str,
        course_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        with self._guard(user_id, course_id) as data:
            current = next((item for item in data["receipts"] if item.get("idempotency_key") == idempotency_key), None)
            return deepcopy(current) if current else None

    def save_receipt(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        idempotency_key = str(payload.get("idempotency_key") or "")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        with self._guard(user_id, course_id, write=True) as data:
            existing = next((item for item in data["receipts"] if item.get("idempotency_key") == idempotency_key), None)
            if existing:
                return deepcopy(existing)
            receipt = _sanitize(payload)
            receipt.update({
                "receipt_id": str(payload.get("receipt_id") or f"air_{uuid.uuid4().hex}"),
                "user_id": user_id,
                "course_id": course_id,
                "created_at": _now(),
            })
            data["receipts"].append(receipt)
            return deepcopy(receipt)

    def get_receipt(
        self,
        user_id: str,
        course_id: str,
        receipt_id: str,
    ) -> dict[str, Any] | None:
        with self._guard(user_id, course_id) as data:
            current = next((item for item in data["receipts"] if item.get("receipt_id") == receipt_id), None)
            return deepcopy(current) if current else None

    def save_suppression(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._guard(user_id, course_id, write=True) as data:
            suppression_key = str(payload.get("suppression_key") or "")
            current = next((item for item in data["suppressions"] if item.get("suppression_key") == suppression_key), None)
            sanitized = _sanitize(payload)
            sanitized.update({
                "suppression_key": suppression_key,
                "user_id": user_id,
                "course_id": course_id,
                "updated_at": _now(),
            })
            if current:
                current.update(sanitized)
                return deepcopy(current)
            sanitized["created_at"] = sanitized["updated_at"]
            data["suppressions"].append(sanitized)
            return deepcopy(sanitized)

    def list_suppressions(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        with self._guard(user_id, course_id) as data:
            return deepcopy(data["suppressions"])

    def _conversation(self, data: dict[str, Any], conversation_id: str) -> dict[str, Any] | None:
        return next((item for item in data["conversations"] if item.get("conversation_id") == conversation_id), None)

    def _guard(self, user_id: str, course_id: str, *, write: bool = False):
        return _RepositoryGuard(self, user_id, course_id, write=write)

    def _key(self, user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _lock(self, key: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return _blank()
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return _blank()
            normalized = _blank()
            for key in {"conversations", "proposals", "receipts", "suppressions"}:
                normalized[key] = data.get(key) if isinstance(data.get(key), list) else []
            return normalized
        except (OSError, json.JSONDecodeError):
            corrupt = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass
            return _blank()

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


class _RepositoryGuard:
    def __init__(self, repository: AITeacherRepository, user_id: str, course_id: str, *, write: bool):
        self.repository = repository
        self.key = repository._key(user_id, course_id)
        self.path = repository._path(self.key)
        self.write = write
        self.lock = repository._lock(self.key)
        self.data: dict[str, Any] | None = None

    def __enter__(self) -> dict[str, Any]:
        self.lock.acquire()
        self.data = self.repository._read(self.path)
        return self.data

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.write and exc_type is None and self.data is not None:
                self.repository._write_atomic(self.path, self.data)
        finally:
            self.lock.release()


def _blank() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "conversations": [],
        "proposals": [],
        "receipts": [],
        "suppressions": [],
    }


def _sanitize_message(payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role") or "user")
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return {
        "role": role,
        "content": _clip(str(payload.get("content") or ""), 50000),
        "context_ref": _sanitize(payload.get("context_ref") or {}),
        "task_ref": _sanitize(payload.get("task_ref") or {}),
        "sources": _sanitize(payload.get("sources") or []),
        "proposal_id": str(payload.get("proposal_id") or ""),
        "receipt_id": str(payload.get("receipt_id") or ""),
        "status": str(payload.get("status") or "complete"),
    }


def _sanitize_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "conversation_id", "message_id", "action_type", "target_ref", "payload_preview",
        "payload", "reason", "evidence_refs", "expected_effect", "confirmation_mode",
        "runtime_revision_id", "expected_revisions", "expires_at", "dedupe_key",
        "undo_capability", "origin",
    }
    return {key: _sanitize(value) for key, value in payload.items() if key in allowed}


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _clip(value, 50000)
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in list(value.items())[:100]}
    return _clip(str(value), 50000)


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ai_teacher_repository = AITeacherRepository(Path(storage._data_dir) / "ai_teacher")


__all__ = [
    "AITeacherRepository",
    "InteractionConflict",
    "PROPOSAL_STATUSES",
    "ai_teacher_repository",
]
