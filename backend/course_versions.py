"""Persistent product course versions, drafts, and candidate workspaces."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from course_versioning import (
    blueprint_revision_id,
    build_blueprint_draft,
    build_version_entry,
    compare_course_snapshots,
)
from storage import DATA_DIR


MANIFEST_SCHEMA = "course_version_manifest_v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class CourseVersionConflict(RuntimeError):
    pass


class CourseVersionRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "course_versions")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.RLock()

    def ensure_initial_version(self, course_id: str, course_data: dict[str, Any]) -> dict[str, Any]:
        with self._lock(course_id):
            manifest = self._load_manifest(course_id)
            current = manifest.get("current_version_id")
            if current:
                return self.get_version_entry(course_id, current)
            return self._create_version_locked(
                course_id,
                course_data,
                reason="导入现有课程",
                operation="initial_import",
                base_version_id=None,
                changed_node_ids=[str(node.get("node_id") or "") for node in course_data.get("nodes") or []],
                activate=True,
            )

    def create_version(
        self,
        course_id: str,
        course_data: dict[str, Any],
        *,
        reason: str,
        operation: str,
        base_version_id: str | None = None,
        changed_node_ids: list[str] | None = None,
        activate: bool = True,
    ) -> dict[str, Any]:
        with self._lock(course_id):
            return self._create_version_locked(
                course_id,
                course_data,
                reason=reason,
                operation=operation,
                base_version_id=base_version_id,
                changed_node_ids=changed_node_ids or [],
                activate=activate,
            )

    def list_versions(self, course_id: str) -> list[dict[str, Any]]:
        manifest = self._load_manifest(course_id)
        return [deepcopy(item) for item in reversed(manifest.get("versions") or [])]

    def current_version_id(self, course_id: str) -> str | None:
        return self._load_manifest(course_id).get("current_version_id")

    def get_version_entry(self, course_id: str, version_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(course_id)
        entry = next((item for item in manifest.get("versions") or [] if item.get("version_id") == version_id), None)
        if not entry:
            raise KeyError(f"Unknown course version: {version_id}")
        return deepcopy(entry)

    def get_version_snapshot(self, course_id: str, version_id: str) -> dict[str, Any]:
        self._validate_id(course_id)
        self._validate_id(version_id)
        path = self._course_dir(course_id) / "versions" / f"{version_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown course version: {version_id}")
        return self._read_json(path)

    def compare_versions(self, course_id: str, left_version_id: str, right_version_id: str) -> dict[str, Any]:
        left = self.get_version_snapshot(course_id, left_version_id)
        right = self.get_version_snapshot(course_id, right_version_id)
        report = compare_course_snapshots(left, right)
        report["left_version_id"] = left_version_id
        report["right_version_id"] = right_version_id
        return report

    def restore_version(
        self,
        course_id: str,
        source_version_id: str,
        *,
        reason: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock(course_id):
            snapshot = self.get_version_snapshot(course_id, source_version_id)
            current = self.current_version_id(course_id)
            entry = self._create_version_locked(
                course_id,
                snapshot,
                reason=reason or f"恢复课程版本 {source_version_id}",
                operation="restore",
                base_version_id=current,
                changed_node_ids=[str(node.get("node_id") or "") for node in snapshot.get("nodes") or []],
                activate=True,
            )
            restored = deepcopy(snapshot)
            restored["current_course_version_id"] = entry["version_id"]
            restored["restored_from_version_id"] = source_version_id
            return restored, entry

    def save_draft(self, course_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        with self._lock(course_id):
            path = self._course_dir(course_id) / "draft.json"
            self._atomic_write(path, draft)
            return deepcopy(draft)

    def freeze_blueprint(self, course_id: str, course_data: dict[str, Any]) -> dict[str, Any]:
        """Persist one immutable blueprint revision and return its snapshot."""
        with self._lock(course_id):
            revision_id = blueprint_revision_id(course_data)
            snapshot = build_blueprint_draft(course_data)
            snapshot["blueprint_revision_id"] = revision_id
            snapshot["status"] = "frozen"
            path = self._course_dir(course_id) / "blueprints" / f"{revision_id}.json"
            if not path.exists():
                self._atomic_write(path, snapshot)
            return deepcopy(snapshot)

    def get_blueprint_revision(self, course_id: str, revision_id: str) -> dict[str, Any]:
        self._validate_id(revision_id)
        path = self._course_dir(course_id) / "blueprints" / f"{revision_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown blueprint revision: {revision_id}")
        return self._read_json(path)

    def load_draft(self, course_id: str) -> dict[str, Any] | None:
        path = self._course_dir(course_id) / "draft.json"
        return self._read_json(path) if path.exists() else None

    def delete_draft(self, course_id: str) -> None:
        path = self._course_dir(course_id) / "draft.json"
        if path.exists():
            path.unlink()

    def delete_candidate(self, course_id: str, candidate_id: str) -> bool:
        """Delete one candidate without touching formal course versions."""
        self._validate_id(course_id)
        self._validate_id(candidate_id)
        with self._lock(course_id):
            path = self.root_dir / course_id / "candidates" / f"{candidate_id}.json"
            if not path.exists():
                return False
            path.unlink()
            return True

    def delete_course(self, course_id: str) -> bool:
        """Delete all version-side state after the formal course is deleted."""
        self._validate_id(course_id)
        with self._lock(course_id):
            directory = self.root_dir / course_id
            if not directory.exists():
                return False
            shutil.rmtree(directory)
            return True

    def create_candidate(
        self,
        course_id: str,
        course_data: dict[str, Any],
        *,
        base_version_id: str | None,
        impact_report: dict[str, Any],
        job_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock(course_id):
            candidate_id = f"candidate_{uuid.uuid4().hex[:16]}"
            candidate = {
                "schema_version": "candidate_course_v1",
                "candidate_id": candidate_id,
                "course_id": course_id,
                "base_version_id": base_version_id,
                "job_id": job_id,
                "status": "pending",
                "impact_report": deepcopy(impact_report),
                "course_data": deepcopy(course_data),
            }
            self._atomic_write(self._candidate_path(course_id, candidate_id), candidate)
            return deepcopy(candidate)

    def load_candidate(self, course_id: str, candidate_id: str) -> dict[str, Any]:
        path = self._candidate_path(course_id, candidate_id)
        if not path.exists():
            raise KeyError(f"Unknown candidate: {candidate_id}")
        return self._read_json(path)

    def save_candidate(self, course_id: str, candidate_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        with self._lock(course_id):
            self._atomic_write(self._candidate_path(course_id, candidate_id), candidate)
            return deepcopy(candidate)

    def list_candidates(self, course_id: str) -> list[dict[str, Any]]:
        directory = self._course_dir(course_id) / "candidates"
        if not directory.exists():
            return []
        result = []
        for path in sorted(directory.glob("candidate_*.json")):
            item = self._read_json(path)
            result.append({key: deepcopy(value) for key, value in item.items() if key != "course_data"})
        return result

    def promote_candidate(
        self,
        course_id: str,
        candidate_id: str,
        *,
        reason: str,
        operation: str = "regenerate",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock(course_id):
            candidate = self.load_candidate(course_id, candidate_id)
            current = self.current_version_id(course_id)
            if candidate.get("base_version_id") != current:
                candidate["status"] = "base_version_conflict"
                candidate["current_version_id"] = current
                self.save_candidate(course_id, candidate_id, candidate)
                raise CourseVersionConflict(
                    f"Candidate {candidate_id} is based on {candidate.get('base_version_id')}, current is {current}"
                )
            course_data = candidate.get("course_data") or {}
            impact = candidate.get("impact_report") or {}
            entry = self._create_version_locked(
                course_id,
                course_data,
                reason=reason,
                operation=operation,
                base_version_id=current,
                changed_node_ids=impact.get("affected_node_ids") or [],
                activate=True,
            )
            candidate["status"] = "promoted"
            candidate["promoted_version_id"] = entry["version_id"]
            self.save_candidate(course_id, candidate_id, candidate)
            promoted = deepcopy(course_data)
            promoted["current_course_version_id"] = entry["version_id"]
            return promoted, entry

    def _create_version_locked(
        self,
        course_id: str,
        course_data: dict[str, Any],
        *,
        reason: str,
        operation: str,
        base_version_id: str | None,
        changed_node_ids: list[str],
        activate: bool,
    ) -> dict[str, Any]:
        self._validate_id(course_id)
        manifest = self._load_manifest(course_id)
        sequence = int(manifest.get("next_sequence") or 1)
        version_id = f"cv{sequence}"
        snapshot = deepcopy(course_data)
        snapshot["course_id"] = course_id
        entry = build_version_entry(
            snapshot,
            version_id=version_id,
            sequence=sequence,
            reason=reason,
            operation=operation,
            base_version_id=base_version_id,
            changed_node_ids=changed_node_ids,
            status="current" if activate else "historical",
        )
        if activate:
            for item in manifest.get("versions") or []:
                if item.get("status") == "current":
                    item["status"] = "historical"
            manifest["current_version_id"] = version_id
        manifest.setdefault("versions", []).append(entry)
        manifest["next_sequence"] = sequence + 1
        snapshot["current_course_version_id"] = version_id if activate else manifest.get("current_version_id")
        snapshot["blueprint_revision_id"] = entry["blueprint_revision_id"]
        self._atomic_write(self._course_dir(course_id) / "versions" / f"{version_id}.json", snapshot)
        self._atomic_write(self._manifest_path(course_id), manifest)
        return deepcopy(entry)

    def _load_manifest(self, course_id: str) -> dict[str, Any]:
        path = self._manifest_path(course_id)
        if not path.exists():
            return {
                "schema_version": MANIFEST_SCHEMA,
                "course_id": course_id,
                "current_version_id": None,
                "next_sequence": 1,
                "versions": [],
            }
        return self._read_json(path)

    def _course_dir(self, course_id: str) -> Path:
        self._validate_id(course_id)
        directory = self.root_dir / course_id
        (directory / "versions").mkdir(parents=True, exist_ok=True)
        (directory / "candidates").mkdir(parents=True, exist_ok=True)
        (directory / "blueprints").mkdir(parents=True, exist_ok=True)
        return directory

    def _manifest_path(self, course_id: str) -> Path:
        return self._course_dir(course_id) / "manifest.json"

    def _candidate_path(self, course_id: str, candidate_id: str) -> Path:
        self._validate_id(candidate_id)
        return self._course_dir(course_id) / "candidates" / f"{candidate_id}.json"

    def _lock(self, course_id: str) -> threading.RLock:
        self._validate_id(course_id)
        with self._locks_guard:
            return self._locks.setdefault(course_id, threading.RLock())

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not _SAFE_ID.match(value):
            raise ValueError("Invalid repository identifier")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object in {path}")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


course_version_repository = CourseVersionRepository()


__all__ = [
    "CourseVersionConflict",
    "CourseVersionRepository",
    "course_version_repository",
]
