from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from material_storage import MaterialRepository


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StudyConflict(ValueError):
    pass


class StudyRepository:
    """Private material domain; generic storage supplies atomic locked writes.

    Never writes a course document or the course-owned learning asset bundles.
    Frozen requests and previous revisions survive task cleanup and restarts.
    """

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def sources(self, owner: str) -> MaterialRepository:
        namespace = hashlib.sha256(owner.encode()).hexdigest()
        return MaterialRepository(Path(self.storage._data_dir) / "study_sources" / namespace)

    def source_origin(self, owner: str, asset_id: str) -> dict | None:
        return (self.storage.load_data("study_course_sources.json") or {}).get(owner, {}).get(asset_id)

    def require_origin_access(self, owner: str, origin: dict | None):
        if not origin:
            return
        if origin.get("exchange_origin"):
            from course_exchange import read_remote_course
            read_remote_course(self.storage, owner, origin["course_id"], release_id=origin["exchange_origin"]["release_id"])
            return
        from course_learning_access import CourseLearningAccess
        course = self.storage.load_course(origin["course_id"])
        if not course or (course.get("owner_id") != owner and not CourseLearningAccess(self.storage).active(course, owner)):
            raise KeyError("来源授权已撤销")

    def ledger(self) -> dict:
        # Read under the shared lock: another worker may have committed progress.
        with self.storage._lock_generic_data("study_materials.json"):
            return self.storage._read_generic_data_from_disk(
                self.storage._generic_data_path("study_materials.json")
            ) or {}

    def get(self, owner: str, material_id: str) -> dict:
        value = self.ledger().get(material_id)
        if not value or value["owner_id"] != owner:
            raise KeyError(material_id)
        for section in value.get("request", {}).get("source_sections", []):
            self.require_origin_access(owner, section.get("course_origin"))
        return deepcopy(value)

    def list(self, owner: str) -> list[dict]:
        return sorted(
            [deepcopy(value) for value in self.ledger().values() if value["owner_id"] == owner],
            key=lambda value: value["updated_at"], reverse=True,
        )

    def for_task(self, owner: str, task_id: str) -> dict:
        material = next((value for value in self.list(owner) if value["task_id"] == task_id), None)
        if material is None:
            raise KeyError(task_id)
        return material

    def reserve(self, owner: str, request_key: str, fingerprint: str, material: dict) -> dict:
        def update(current):
            current = current or {}
            for value in current.values():
                if value["owner_id"] == owner and value["request_key"] == request_key:
                    if value["fingerprint"] != fingerprint:
                        raise StudyConflict("这个请求已使用，请重新确认资料和用途后生成")
                    return current
            current[material["id"]] = deepcopy(material)
            return current

        ledger = self.storage.update_data("study_materials.json", update)
        return next(deepcopy(value) for value in ledger.values()
                    if value["owner_id"] == owner and value["request_key"] == request_key)

    def update(self, owner: str, material_id: str, changes: dict) -> dict:
        def update(current):
            current = current or {}
            value = current.get(material_id)
            if not value or value["owner_id"] != owner:
                raise KeyError(material_id)
            value.update(deepcopy(changes))
            value["updated_at"] = now()
            return current

        return self.storage.update_data("study_materials.json", update)[material_id]

    def save_note(self, owner: str, material_id: str, revision_id: str, content: str) -> dict:
        def change(material):
            if not any(revision["id"] == revision_id for revision in material["revisions"]):
                raise StudyConflict("讲义版本已不存在，请重新打开讲义")
            # An old client edits the course note, never a stale copy of the
            # structured entries saved by another tab.
            note = material.setdefault("notes", {}).setdefault(revision_id, {})
            note.update(content=content, updated_at=now())

        saved = self.mutate_notes(owner, material_id, change)
        from learning_events import record_learning_event
        record_learning_event(
            event_type="personal_note_saved", actor="student", source="personal_study", user_id=owner,
            entity_type="personal_material", entity_id=material_id, entity_revision=revision_id,
            task_purpose=saved["purpose"], record_type="personal_note",
            idempotency_key=f"note:{material_id}:{revision_id}:{hashlib.sha256(content.encode()).hexdigest()}",
            result={"saved": True},  # Saving a note never claims understanding or mastery.
        )
        return saved

    def save_reading_position(self, owner: str, material_id: str, revision_id: str,
                              position: dict, expected_version: int, request_id: str) -> dict:
        """A private bookmark, serialized with existing material records; no mastery event."""
        self.get(owner, material_id)  # Includes source authorization, even for cached text.

        def update(current):
            material = (current or {}).get(material_id)
            if not material or material["owner_id"] != owner:
                raise KeyError(material_id)
            revision = next((r for r in material["revisions"] if r["id"] == revision_id), None)
            if not revision:
                raise StudyConflict("讲义版本已不存在，请重新打开讲义")
            section = next((s for s in revision["sections"] if s["id"] == position["sectionId"]), None)
            if not section or (position["blockId"] and not any(
                    b["block_id"] == position["blockId"] for b in section["blocks"])):
                raise StudyConflict("阅读位置已失效，请重新打开讲义")
            answers = {b["block_id"] for s in revision["sections"] for b in s["blocks"]
                       if b.get("answer_to") or b.get("content_type") == "answer"}
            if not set(position.get("expandedAnswers", [])).issubset(answers):
                raise StudyConflict("解答位置已失效，请重新打开讲义")
            positions = material.setdefault("reading_positions", {})
            previous = positions.get(revision_id, {})
            if previous.get("request_id") == request_id:
                if previous["position"] != position:
                    raise StudyConflict("阅读位置请求已使用")
                return current
            if previous.get("version", 0) != expected_version:
                raise StudyConflict("其他窗口已更新阅读位置，请重新打开讲义")
            positions[revision_id] = {"position": deepcopy(position), "version": expected_version + 1,
                                      "request_id": request_id, "updated_at": now()}
            # Reading must not masquerade as a content edit or reorder the material by updated_at.
            return current

        saved = self.storage.update_data("study_materials.json", update)[material_id]
        return deepcopy(saved["reading_positions"][revision_id])

    def mutate_notes(self, owner: str, material_id: str, change) -> dict:
        """Serialize notes with the material's existing authoritative ledger."""
        self.get(owner, material_id)  # Also checks any revoked source access.

        def update(current):
            current = current or {}
            material = current.get(material_id)
            if not material or material["owner_id"] != owner:
                raise KeyError(material_id)
            change(material)
            material["updated_at"] = now()
            return current

        return deepcopy(self.storage.update_data("study_materials.json", update)[material_id])
