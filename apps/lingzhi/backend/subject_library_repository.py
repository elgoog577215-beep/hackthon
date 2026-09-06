"""Immutable, versioned persistence for subject-level knowledge libraries."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from storage import DATA_DIR


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SubjectLibraryNotFound(KeyError):
    pass


class SubjectLibraryConflict(RuntimeError):
    pass


class SubjectLibraryRepository:
    """Store immutable ontology revisions and mutable lifecycle decisions separately."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "subject_libraries")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_revision(self, library: dict[str, Any]) -> dict[str, Any]:
        library_id = self._safe(str(library.get("library_id") or ""))
        revision_id = self._safe(str(library.get("revision_id") or ""))
        if not library_id or not revision_id:
            raise ValueError("library_id and revision_id are required")
        stored = deepcopy(library)
        stored.setdefault("lifecycle_status", "candidate")
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        path = self._revision_path(library_id, revision_id)
        if path.exists():
            existing = self._read(path)
            comparable_existing = {key: value for key, value in existing.items() if key != "created_at"}
            comparable_stored = {key: value for key, value in stored.items() if key != "created_at"}
            if comparable_existing != comparable_stored:
                raise SubjectLibraryConflict("Knowledge-library revision is immutable")
            return self._with_review(existing)
        self._atomic_write(path, stored)
        if stored.get("lifecycle_status") == "accepted":
            self._write_accepted_pointer(stored)
        return deepcopy(stored)

    def load_revision(self, library_id: str, revision_id: str) -> dict[str, Any]:
        path = self._revision_path(self._safe(library_id), self._safe(revision_id))
        if not path.exists():
            raise SubjectLibraryNotFound(f"{library_id}@{revision_id}")
        return self._with_review(self._read(path))

    def list_revisions(self, library_id: str) -> list[dict[str, Any]]:
        directory = self.root_dir / self._safe(library_id) / "revisions"
        values = [self._with_review(self._read(path)) for path in directory.glob("*.json")]
        return sorted(values, key=lambda item: str(item.get("created_at") or ""))

    def review_revision(
        self,
        library_id: str,
        revision_id: str,
        *,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise ValueError("decision must be accept or reject")
        library = self.load_revision(library_id, revision_id)
        current = str(library.get("lifecycle_status") or "candidate")
        target = "accepted" if decision == "accept" else "rejected"
        if current == target:
            return library
        if current in {"accepted", "rejected"}:
            raise SubjectLibraryConflict(f"Revision already reviewed as {current}")
        review = {
            "revision_id": revision_id,
            "lifecycle_status": target,
            "decision": decision,
            "note": note.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(self._review_path(library_id, revision_id), review)
        if target == "accepted":
            self._write_accepted_pointer({**library, "accepted_at": review["reviewed_at"]})
        return self.load_revision(library_id, revision_id)

    def load_accepted(self, subject_id: str) -> dict[str, Any] | None:
        pointer = self.root_dir / "accepted" / f"{self._safe(subject_id)}.json"
        if not pointer.exists():
            return None
        value = self._read(pointer)
        return self.load_revision(str(value["library_id"]), str(value["revision_id"]))

    def binding_for(self, library: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject_id": library.get("subject_id"),
            "library_id": library.get("library_id"),
            "revision_id": library.get("revision_id"),
            "lifecycle_status": library.get("lifecycle_status", "candidate"),
            "binding_status": "pinned",
        }

    def resolve_for_course(self, course: dict[str, Any]) -> dict[str, Any] | None:
        binding = course.get("knowledge_library_binding") or {}
        library_id = str(binding.get("library_id") or "")
        revision_id = str(binding.get("revision_id") or "")
        if not library_id or not revision_id:
            return None
        library = self.load_revision(library_id, revision_id)
        source_courses = {str(item) for item in library.get("source_course_ids") or []}
        course_id = str(course.get("course_id") or "")
        if library.get("lifecycle_status") == "candidate" and course_id not in source_courses:
            return None
        return library

    def review_summary(self, library_id: str, revision_id: str) -> dict[str, Any]:
        current = self.load_revision(library_id, revision_id)
        previous = None
        supersedes = str(current.get("supersedes_revision_id") or "")
        if supersedes:
            try:
                previous = self.load_revision(library_id, supersedes)
            except SubjectLibraryNotFound:
                previous = None
        current_nodes = {str(item.get("knowledge_id")): item for item in current.get("nodes") or []}
        previous_nodes = {str(item.get("knowledge_id")): item for item in (previous or {}).get("nodes") or []}
        return {
            "library": current,
            "previous_revision_id": supersedes or None,
            "diff": {
                "added": len(current_nodes.keys() - previous_nodes.keys()),
                "removed": len(previous_nodes.keys() - current_nodes.keys()),
                "modified": sum(
                    current_nodes[key] != previous_nodes[key]
                    for key in current_nodes.keys() & previous_nodes.keys()
                ),
            },
        }

    def record_node_review(
        self,
        library_id: str,
        revision_id: str,
        knowledge_id: str,
        *,
        note: str,
        source_block_id: str,
        proposal_id: str,
        item_id: str,
        reviewed_by: str,
    ) -> dict[str, Any]:
        """Record an audit receipt without mutating the immutable revision."""
        library = self.load_revision(library_id, revision_id)
        known_ids = {
            str(node.get("knowledge_id") or "")
            for node in library.get("nodes") or []
        }
        if knowledge_id not in known_ids:
            raise SubjectLibraryNotFound(
                f"Unknown knowledge node: {knowledge_id}"
            )
        review_id = "knr_" + hashlib.sha256(
            f"{library_id}:{revision_id}:{knowledge_id}:{proposal_id}:{item_id}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        path = self._node_review_path(
            library_id,
            revision_id,
            knowledge_id,
            review_id,
        )
        if path.exists():
            return self._read(path)
        entry = {
            "review_id": review_id,
            "library_id": library_id,
            "revision_id": revision_id,
            "knowledge_id": knowledge_id,
            "note": note.strip(),
            "source_block_id": source_block_id,
            "proposal_id": proposal_id,
            "item_id": item_id,
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(path, entry)
        return deepcopy(entry)

    def list_node_reviews(
        self,
        library_id: str,
        revision_id: str,
        knowledge_id: str,
    ) -> list[dict[str, Any]]:
        directory = (
            self.root_dir
            / self._safe(library_id)
            / "node_reviews"
            / self._safe(revision_id)
            / self._safe(knowledge_id)
        )
        values = [self._read(path) for path in directory.glob("*.json")]
        return sorted(values, key=lambda item: str(item.get("reviewed_at") or ""))

    def _with_review(self, library: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(library)
        path = self._review_path(str(value["library_id"]), str(value["revision_id"]))
        if path.exists():
            review = self._read(path)
            value["lifecycle_status"] = review["lifecycle_status"]
            value["review"] = review
        return value

    def _revision_path(self, library_id: str, revision_id: str) -> Path:
        return self.root_dir / library_id / "revisions" / f"{revision_id}.json"

    def _write_accepted_pointer(self, library: dict[str, Any]) -> None:
        self._atomic_write(
            self.root_dir / "accepted" / f"{self._safe(str(library['subject_id']))}.json",
            {
                "subject_id": library["subject_id"],
                "library_id": library["library_id"],
                "revision_id": library["revision_id"],
                "accepted_at": library.get("accepted_at") or datetime.now(timezone.utc).isoformat(),
            },
        )

    def _review_path(self, library_id: str, revision_id: str) -> Path:
        return self.root_dir / self._safe(library_id) / "reviews" / f"{self._safe(revision_id)}.json"

    def _node_review_path(
        self,
        library_id: str,
        revision_id: str,
        knowledge_id: str,
        review_id: str,
    ) -> Path:
        return (
            self.root_dir
            / self._safe(library_id)
            / "node_reviews"
            / self._safe(revision_id)
            / self._safe(knowledge_id)
            / f"{self._safe(review_id)}.json"
        )

    @staticmethod
    def _safe(value: str) -> str:
        if not value or not _SAFE_ID.fullmatch(value):
            raise ValueError("Unsafe knowledge-library identifier")
        return value

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Knowledge-library repository expected an object")
        return value

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


subject_library_repository = SubjectLibraryRepository()


__all__ = [
    "SubjectLibraryConflict",
    "SubjectLibraryNotFound",
    "SubjectLibraryRepository",
    "subject_library_repository",
]
