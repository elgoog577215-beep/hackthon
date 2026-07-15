"""Version-aware current learning records stored separately from fact events."""

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

from content_blocks import project_course_content_blocks, resolve_content_anchor
from learning_progress import objective_for_node
from storage import storage


SCHEMA_VERSION = 1
RECORD_TYPES = {"note", "issue", "review_task", "bookmark"}
STATUSES = {
    "note": {"active", "archived"},
    "issue": {"open", "explaining", "awaiting_verification", "resolved", "reopened", "archived"},
    "review_task": {"pending", "due", "completed", "dismissed", "archived"},
    "bookmark": {"active", "archived"},
}
DEFAULT_STATUS = {
    "note": "active",
    "issue": "open",
    "review_task": "pending",
    "bookmark": "active",
}
ALLOWED_TRANSITIONS = {
    "note": {"active": {"archived"}, "archived": {"active"}},
    "issue": {
        "open": {"explaining", "awaiting_verification", "resolved", "archived"},
        "explaining": {"open", "awaiting_verification", "resolved", "archived"},
        "awaiting_verification": {"open", "resolved", "archived"},
        "resolved": {"reopened", "archived"},
        "reopened": {"explaining", "awaiting_verification", "resolved", "archived"},
        "archived": {"open", "reopened"},
    },
    "review_task": {
        "pending": {"due", "completed", "dismissed", "archived"},
        "due": {"pending", "completed", "dismissed", "archived"},
        "completed": {"pending", "archived"},
        "dismissed": {"pending", "archived"},
        "archived": {"pending"},
    },
    "bookmark": {"active": {"archived"}, "archived": {"active"}},
}


class RecordConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("learning record revision conflict")
        self.current = current


class InvalidRecordTransition(ValueError):
    pass


class LearningRecordRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def list(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        key = self._key(user_id, course_id)
        with self._lock(key):
            return deepcopy(self._read(self._path(key)))

    def create(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record, _ = self.create_once(user_id, course_id, payload)
        return record

    def create_once(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        record_type = str(payload.get("record_type") or "")
        if record_type not in RECORD_TYPES:
            raise ValueError("unsupported learning record type")
        status = str(payload.get("status") or DEFAULT_STATUS[record_type])
        if status not in STATUSES[record_type]:
            raise ValueError("invalid learning record status")

        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            records = self._read(path)
            requested_id = str(payload.get("record_id") or "")
            if requested_id:
                existing = next((item for item in records if item.get("record_id") == requested_id), None)
                if existing:
                    return deepcopy(existing), False
            now = _now()
            record = _sanitize_record(payload)
            record.update({
                "record_id": requested_id or f"lr_{uuid.uuid4().hex}",
                "record_type": record_type,
                "status": status,
                "user_id": user_id,
                "course_id": course_id,
                "revision": 1,
                "schema_version": SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
            })
            records.append(record)
            self._write_atomic(path, records)
            return deepcopy(record), True

    def update(
        self,
        user_id: str,
        course_id: str,
        record_id: str,
        *,
        expected_revision: int,
        changes: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            records = self._read(path)
            index = next((i for i, item in enumerate(records) if item.get("record_id") == record_id), -1)
            if index < 0:
                raise KeyError(record_id)
            current = records[index]
            if int(current.get("revision") or 0) != expected_revision:
                raise RecordConflict(deepcopy(current))

            record_type = str(current.get("record_type") or "")
            old_status = str(current.get("status") or "")
            next_status = str(changes.get("status") or old_status)
            if next_status != old_status and next_status not in ALLOWED_TRANSITIONS[record_type].get(old_status, set()):
                raise InvalidRecordTransition(f"{old_status} -> {next_status}")

            allowed = {"title", "content", "quote", "tags", "category", "priority", "status", "due_at", "anchor", "metadata"}
            updated = deepcopy(current)
            for field in allowed:
                if field in changes:
                    updated[field] = _sanitize_value(changes[field])
            updated["revision"] = expected_revision + 1
            updated["updated_at"] = _now()
            if next_status == "resolved":
                updated["resolved_at"] = updated["updated_at"]
            if old_status == "resolved" and next_status != "resolved":
                updated["resolved_at"] = None
            records[index] = updated
            self._write_atomic(path, records)
            change_kind = "status_changed" if next_status != old_status else "updated"
            return deepcopy(updated), change_kind

    def _key(self, user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _lock(self, key: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    def _read(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            corrupt = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass
            return []

    def _write_atomic(self, path: Path, records: list[dict[str, Any]]) -> None:
        temp = path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def enrich_record_payload(course: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(payload)
    node_id = str(payload.get("node_id") or "")
    objective = objective_for_node(course, node_id) if node_id else None
    if objective:
        enriched.setdefault("objective_id", objective.get("objective_id"))
        enriched.setdefault("objective_revision_id", objective.get("objective_revision_id"))
    enriched.setdefault("course_version_id", course.get("current_course_version_id"))
    enriched["anchor"] = _best_anchor(course, node_id=node_id, quote=str(payload.get("quote") or ""), anchor=payload.get("anchor"))
    return enriched


def project_record(record: dict[str, Any], course: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(record)
    resolution = resolve_content_anchor(
        course,
        node_id=str(record.get("node_id") or ""),
        anchor=record.get("anchor") or {},
    )
    text_resolution = _resolve_text_anchor(course, record=record, block_resolution=resolution)
    resolution["text"] = text_resolution
    if text_resolution.get("resolved_position") and resolution.get("resolved_anchor"):
        resolution["resolved_anchor"] = {
            **resolution["resolved_anchor"],
            "text_quote": text_resolution.get("text_quote") or "",
            "text_position": text_resolution["resolved_position"],
        }
    projected["anchor_resolution"] = resolution
    projected["migration_status"] = _migration_status(resolution)
    return projected


def _best_anchor(
    course: dict[str, Any],
    *,
    node_id: str,
    quote: str,
    anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    text_anchor = _text_anchor_payload(anchor, quote)
    if anchor and (anchor.get("block_id") or anchor.get("block_revision_id")):
        resolution = resolve_content_anchor(course, node_id=node_id, anchor=anchor)
        return {**dict(resolution.get("resolved_anchor") or anchor), **text_anchor}
    projected = project_course_content_blocks(course)
    node = next((item for item in projected.get("nodes") or [] if str(item.get("node_id") or "") == node_id), None)
    normalized_quote = " ".join(quote.split())
    if node and normalized_quote:
        for block in node.get("content_blocks") or []:
            if normalized_quote in " ".join(str(block.get("content") or "").split()):
                return {
                    "node_id": node_id,
                    "node_name": str(node.get("node_name") or ""),
                    "block_id": str(block.get("block_id") or ""),
                    "block_revision_id": str(block.get("block_revision_id") or ""),
                    "content_fingerprint": str(block.get("content_fingerprint") or ""),
                    "block_type": str(block.get("type") or ""),
                    "title": str(block.get("title") or ""),
                    "progress": 0.0,
                    **_text_anchor_payload(anchor, quote, str(block.get("content") or "")),
                }
    resolution = resolve_content_anchor(course, node_id=node_id, anchor={})
    return {**dict(resolution.get("resolved_anchor") or {"node_id": node_id}), **text_anchor}


def _migration_status(resolution: dict[str, Any]) -> str:
    status = str(resolution.get("status") or "unavailable")
    text_status = str((resolution.get("text") or {}).get("status") or "unavailable")
    if text_status == "ambiguous":
        return "needs_confirmation"
    if text_status == "missing":
        return "needs_confirmation" if status != "unavailable" else "orphaned"
    if text_status == "quote_remap":
        return "content_updated"
    if status == "exact":
        return "current"
    if status in {"updated_block", "fingerprint_remap"}:
        return "content_updated"
    if status in {"node_fallback", "course_fallback"}:
        return "needs_confirmation"
    return "orphaned"


def _text_anchor_payload(
    anchor: dict[str, Any] | None,
    quote: str,
    content: str = "",
) -> dict[str, Any]:
    source = dict(anchor or {})
    text_quote = str(source.get("text_quote") or quote or "")
    raw_position = source.get("text_position")
    if isinstance(raw_position, dict):
        return {
            "text_quote": text_quote,
            "text_position": {
                "start": max(0, int(raw_position.get("start") or 0)),
                "end": max(0, int(raw_position.get("end") or 0)),
                "prefix": str(raw_position.get("prefix") or "")[-80:],
                "suffix": str(raw_position.get("suffix") or "")[:80],
                "occurrence": max(0, int(raw_position.get("occurrence") or 0)),
            },
        }
    if content and text_quote:
        start = content.find(text_quote)
        if start >= 0:
            return {
                "text_quote": text_quote,
                "text_position": _position_payload(content, start, start + len(text_quote), text_quote),
            }
    return {"text_quote": text_quote} if text_quote else {}


def _resolve_text_anchor(
    course: dict[str, Any],
    *,
    record: dict[str, Any],
    block_resolution: dict[str, Any],
) -> dict[str, Any]:
    anchor = dict(record.get("anchor") or {})
    text_quote = str(anchor.get("text_quote") or record.get("quote") or "")
    if not text_quote:
        return {"status": "unavailable", "text_quote": "", "resolved_position": None}

    projected = project_course_content_blocks(course)
    resolved_anchor = block_resolution.get("resolved_anchor") or {}
    resolved_node_id = str(resolved_anchor.get("node_id") or record.get("node_id") or "")
    resolved_block_id = str(resolved_anchor.get("block_id") or "")
    node = next((item for item in _walk_course_nodes(projected.get("nodes") or []) if str(item.get("node_id") or "") == resolved_node_id), None)
    block = next((item for item in (node or {}).get("content_blocks") or [] if str(item.get("block_id") or "") == resolved_block_id), None)
    content = str((block or {}).get("content") or (node or {}).get("node_content") or "")
    if not content:
        return {"status": "missing", "text_quote": text_quote, "resolved_position": None}

    positions = _quote_positions(content, text_quote)
    if not positions:
        return {"status": "missing", "text_quote": text_quote, "resolved_position": None}

    original = anchor.get("text_position") if isinstance(anchor.get("text_position"), dict) else {}
    requested_start = max(0, int((original or {}).get("start") or 0))
    requested_end = max(requested_start, int((original or {}).get("end") or 0))
    if requested_end > requested_start and content[requested_start:requested_end] == text_quote:
        return {
            "status": "exact",
            "text_quote": text_quote,
            "resolved_position": _position_payload(content, requested_start, requested_end, text_quote),
        }

    prefix = str((original or {}).get("prefix") or "")[-80:]
    suffix = str((original or {}).get("suffix") or "")[:80]
    occurrence = max(0, int((original or {}).get("occurrence") or 0))
    candidates: list[tuple[int, int, int]] = []
    for index, start in enumerate(positions):
        end = start + len(text_quote)
        score = 0
        if prefix and content[max(0, start - len(prefix)):start] == prefix:
            score += 4
        if suffix and content[end:end + len(suffix)] == suffix:
            score += 4
        if index == occurrence:
            score += 1
        candidates.append((score, -abs(start - requested_start), start))
    candidates.sort(reverse=True)
    best = candidates[0]
    tied = len(candidates) > 1 and candidates[1][:2] == best[:2]
    if tied and not prefix and not suffix:
        return {
            "status": "ambiguous",
            "text_quote": text_quote,
            "resolved_position": None,
            "candidate_count": len(candidates),
        }
    start = best[2]
    return {
        "status": "quote_remap",
        "text_quote": text_quote,
        "resolved_position": _position_payload(content, start, start + len(text_quote), text_quote),
        "candidate_count": len(candidates),
    }


def _quote_positions(content: str, quote: str) -> list[int]:
    positions: list[int] = []
    cursor = 0
    while quote and cursor <= len(content):
        index = content.find(quote, cursor)
        if index < 0:
            break
        positions.append(index)
        cursor = index + max(1, len(quote))
    return positions


def _walk_course_nodes(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        children = node.get("children") or []
        if isinstance(children, list):
            yield from _walk_course_nodes(children)


def _position_payload(content: str, start: int, end: int, quote: str) -> dict[str, Any]:
    occurrence = sum(1 for position in _quote_positions(content, quote) if position < start)
    return {
        "start": start,
        "end": end,
        "prefix": content[max(0, start - 80):start],
        "suffix": content[end:end + 80],
        "occurrence": occurrence,
    }


def _sanitize_record(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "record_id", "record_type", "status", "course_version_id", "node_id", "node_name",
        "objective_id", "objective_revision_id", "anchor", "quote", "title", "content",
        "origin", "priority", "tags", "category", "due_at", "resolved_at", "metadata",
    }
    return {key: _sanitize_value(value) for key, value in payload.items() if key in allowed and value is not None}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:20000]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in list(value.items())[:50]}
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


learning_record_repository = LearningRecordRepository(Path(storage._data_dir) / "learning_records")


__all__ = [
    "ALLOWED_TRANSITIONS",
    "DEFAULT_STATUS",
    "InvalidRecordTransition",
    "LearningRecordRepository",
    "RECORD_TYPES",
    "RecordConflict",
    "enrich_record_payload",
    "learning_record_repository",
    "project_record",
]
