"""Versioned formal-practice attempts stored separately from fact events."""

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


SCHEMA_VERSION = 2
ATTEMPT_STATUSES = {"in_progress", "submitted", "grading", "graded", "abandoned", "invalidated"}
TERMINAL_STATUSES = {"graded", "abandoned", "invalidated"}


class AttemptConflict(Exception):
    def __init__(self, current: dict[str, Any]):
        super().__init__("practice attempt revision conflict")
        self.current = current


class InvalidAttemptTransition(ValueError):
    pass


class PracticeAttemptRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def list(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        key = self._key(user_id, course_id)
        with self._lock(key):
            return deepcopy(self._read(self._path(key)))

    def get(self, user_id: str, course_id: str, attempt_id: str) -> dict[str, Any]:
        attempt = next(
            (item for item in self.list(user_id, course_id) if item.get("attempt_id") == attempt_id),
            None,
        )
        if not attempt:
            raise KeyError(attempt_id)
        return attempt

    def create_once(
        self,
        user_id: str,
        course_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        task_revision_id = str(payload.get("task_revision_id") or payload.get("question_revision_id") or "")
        if not task_revision_id:
            raise ValueError("task_revision_id is required")
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            attempts = self._read(path)
            requested_id = str(payload.get("attempt_id") or "")
            if requested_id:
                existing = next((item for item in attempts if item.get("attempt_id") == requested_id), None)
                if existing:
                    return deepcopy(existing), False
            resume = bool(payload.get("resume", True))
            run_id = str(payload.get("practice_run_id") or "")
            if resume:
                active = next((
                    item for item in reversed(attempts)
                    if str(item.get("task_revision_id") or item.get("question_revision_id") or "") == task_revision_id
                    and item.get("status") == "in_progress"
                    and (not run_id or item.get("practice_run_id") == run_id)
                ), None)
                if active:
                    return deepcopy(active), False

            now = _now()
            attempt_number = 1 + sum(
                str(item.get("task_revision_id") or item.get("question_revision_id") or "") == task_revision_id
                for item in attempts
            )
            attempt = _sanitize_attempt(payload)
            attempt.update({
                "attempt_id": requested_id or f"pa_{uuid.uuid4().hex}",
                "user_id": user_id,
                "course_id": course_id,
                "task_revision_id": task_revision_id,
                "question_revision_id": str(payload.get("question_revision_id") or task_revision_id),
                "status": "in_progress",
                "attempt_number": attempt_number,
                "answer_payload": _sanitize_value(payload.get("answer_payload") or {}),
                "revealed_hint_levels": [],
                "revealed_hints": [],
                "solution_revealed": False,
                "ai_support_level": 0,
                "active_seconds": 0,
                "revision": 1,
                "schema_version": SCHEMA_VERSION,
                "started_at": now,
                "created_at": now,
                "updated_at": now,
            })
            attempts.append(attempt)
            self._write_atomic(path, attempts)
            return deepcopy(attempt), True

    def update_draft(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        answer_payload: dict[str, Any],
        active_seconds: int | None = None,
    ) -> dict[str, Any]:
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress"},
            mutate=lambda current: current.update({
                "answer_payload": _sanitize_value(answer_payload),
                "active_seconds": max(int(current.get("active_seconds") or 0), int(active_seconds or 0)),
            }),
        )

    def reveal_hint(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        level: int,
        hint: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if level not in {1, 2, 3}:
            raise ValueError("hint level must be 1, 2, or 3")
        current = self.get(user_id, course_id, attempt_id)
        hint_snapshot = _sanitize_value(hint) if isinstance(hint, dict) else None
        if level in (current.get("revealed_hint_levels") or []):
            stored_levels = {
                int(item.get("level") or 0)
                for item in current.get("revealed_hints") or []
                if isinstance(item, dict)
            }
            if hint_snapshot and level not in stored_levels:
                return self._update(
                    user_id,
                    course_id,
                    attempt_id,
                    expected_revision=expected_revision,
                    allowed_statuses={"in_progress"},
                    mutate=lambda item: _store_revealed_hint(item, level, hint_snapshot),
                ), False
            return current, False
        if level > 1 and level - 1 not in (current.get("revealed_hint_levels") or []):
            raise InvalidAttemptTransition("hint levels must be revealed in order")

        def mutate(item: dict[str, Any]) -> None:
            item["revealed_hint_levels"] = sorted({*(item.get("revealed_hint_levels") or []), level})
            if hint_snapshot:
                _store_revealed_hint(item, level, hint_snapshot)

        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress"},
            mutate=mutate,
        ), True

    def record_ai_support(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        level: int,
    ) -> dict[str, Any]:
        if level not in {1, 2, 3}:
            raise ValueError("AI support level must be 1, 2, or 3")
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress"},
            mutate=lambda current: current.update({
                "ai_support_level": max(int(current.get("ai_support_level") or 0), level),
            }),
        )

    def reveal_solution(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
    ) -> tuple[dict[str, Any], bool]:
        current = self.get(user_id, course_id, attempt_id)
        if current.get("solution_revealed"):
            return current, False
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress", "submitted", "grading", "graded"},
            mutate=lambda item: item.update({"solution_revealed": True}),
        ), True

    def submit(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        request_id: str,
        answer_payload: dict[str, Any],
        active_seconds: int,
    ) -> tuple[dict[str, Any], bool]:
        current = self.get(user_id, course_id, attempt_id)
        if current.get("submit_request_id") == request_id and current.get("status") in {"submitted", "grading", "graded"}:
            return current, False
        now = _now()

        def mutate(item: dict[str, Any]) -> None:
            item.update({
                "answer_payload": _sanitize_value(answer_payload),
                "submitted_answer_payload": _sanitize_value(answer_payload),
                "active_seconds": max(int(item.get("active_seconds") or 0), int(active_seconds or 0)),
                "submit_request_id": request_id,
                "status": "submitted",
                "submitted_at": now,
            })

        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress"},
            mutate=mutate,
        ), True

    def apply_grade(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        pending = str(result.get("status") or "") in {"pending_review", "submitted_for_review"}
        now = _now()
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"submitted", "grading"},
            mutate=lambda item: item.update({
                "status": "grading" if pending else "graded",
                "result": _sanitize_value(result),
                "graded_at": None if pending else now,
            }),
        )

    def abandon(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=expected_revision,
            allowed_statuses={"in_progress"},
            mutate=lambda item: item.update({"status": "abandoned", "abandoned_at": _now()}),
        )

    def invalidate(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        reason: str,
    ) -> tuple[dict[str, Any], bool]:
        current = self.get(user_id, course_id, attempt_id)
        if current.get("status") in TERMINAL_STATUSES or current.get("status") == "invalidated":
            return current, False
        return self._update(
            user_id,
            course_id,
            attempt_id,
            expected_revision=int(current.get("revision") or 0),
            allowed_statuses={"in_progress", "submitted", "grading"},
            mutate=lambda item: item.update({
                "status": "invalidated",
                "invalidated_at": _now(),
                "invalidation_reason": reason[:500],
            }),
        ), True

    def _update(
        self,
        user_id: str,
        course_id: str,
        attempt_id: str,
        *,
        expected_revision: int,
        allowed_statuses: set[str],
        mutate,
    ) -> dict[str, Any]:
        key = self._key(user_id, course_id)
        path = self._path(key)
        with self._lock(key):
            attempts = self._read(path)
            index = next((i for i, item in enumerate(attempts) if item.get("attempt_id") == attempt_id), -1)
            if index < 0:
                raise KeyError(attempt_id)
            current = attempts[index]
            if int(current.get("revision") or 0) != expected_revision:
                raise AttemptConflict(deepcopy(current))
            if str(current.get("status") or "") not in allowed_statuses:
                raise InvalidAttemptTransition(str(current.get("status") or ""))
            updated = deepcopy(current)
            mutate(updated)
            if updated.get("status") not in ATTEMPT_STATUSES:
                raise InvalidAttemptTransition(str(updated.get("status") or ""))
            updated["revision"] = expected_revision + 1
            updated["updated_at"] = _now()
            attempts[index] = updated
            self._write_atomic(path, attempts)
            return deepcopy(updated)

    def _key(self, user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _lock(self, key: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with path.open(encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            corrupt = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                os.replace(path, corrupt)
            except OSError:
                pass
            return []

    @staticmethod
    def _write_atomic(path: Path, attempts: list[dict[str, Any]]) -> None:
        temp = path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(attempts, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def evidence_strength(attempt: dict[str, Any]) -> str:
    if attempt.get("status") == "invalidated":
        return "invalid"
    if attempt.get("solution_revealed"):
        return "scaffolded"
    highest = max([
        0,
        int(attempt.get("ai_support_level") or 0),
        *[int(item) for item in attempt.get("revealed_hint_levels") or []],
    ])
    return {
        0: "independent",
        1: "lightly_supported",
        2: "supported",
        3: "scaffolded",
    }.get(highest, "scaffolded")


def _store_revealed_hint(attempt: dict[str, Any], level: int, hint: dict[str, Any]) -> None:
    snapshots = [
        item
        for item in attempt.get("revealed_hints") or []
        if isinstance(item, dict) and int(item.get("level") or 0) != level
    ]
    snapshots.append({"level": level, **hint})
    attempt["revealed_hints"] = sorted(
        snapshots,
        key=lambda item: int(item.get("level") or 0),
    )


def _sanitize_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "attempt_id", "practice_run_id", "practice_level", "course_version_id", "node_id", "node_name",
        "objective_id", "objective_revision_id", "criterion_id", "criterion_revision_id",
        "question_revision_id", "task_revision_id", "task_purpose", "task_source",
        "diagnostic_case_id", "remediation_session_id", "question_type", "input_contract", "metadata",
        "concept_ids", "skill_unit_ids", "mistake_point_ids", "improvement_point_ids",
        "origin_attempt_id", "practice_intent",
    }
    return {key: _sanitize_value(value) for key, value in payload.items() if key in allowed and value is not None}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:50000]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value[:200]]
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in list(value.items())[:200]}
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


practice_attempt_repository = PracticeAttemptRepository(Path(storage._data_dir) / "practice_attempts")


__all__ = [
    "ATTEMPT_STATUSES",
    "AttemptConflict",
    "InvalidAttemptTransition",
    "PracticeAttemptRepository",
    "evidence_strength",
    "practice_attempt_repository",
]
