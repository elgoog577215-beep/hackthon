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
        material = self.get(owner, material_id)
        if not any(revision["id"] == revision_id for revision in material["revisions"]):
            raise StudyConflict("讲义版本已不存在，请重新打开讲义")
        notes = deepcopy(material.get("notes") or {})
        notes[revision_id] = {"content": content, "updated_at": now()}
        saved = self.update(owner, material_id, {"notes": notes})
        from learning_events import record_learning_event
        record_learning_event(
            event_type="personal_note_saved", actor="student", source="personal_study", user_id=owner,
            entity_type="personal_material", entity_id=material_id, entity_revision=revision_id,
            task_purpose=material["purpose"], record_type="personal_note",
            idempotency_key=f"note:{material_id}:{revision_id}:{hashlib.sha256(content.encode()).hexdigest()}",
            result={"saved": True},  # Saving a note never claims understanding or mastery.
        )
        return saved
