"""Single persistence boundary for canonical course documents."""

from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseDocument,
    course_view_from_document,
    document_from_legacy_course,
    legacy_source_checksum,
    repair_document_block_semantics,
    refresh_document_revision,
)
from course_feedback import project_feedback_structures
from course_revisions import revision_event_for_documents, revision_vector_for_document

_GENERATED_METADATA_EXCLUDES = {
    "nodes",
    "course_document",
    "course_schema_version",
    "course_document_revision",
    "course_document_authoritative",
    "course_operation_log",
    "current_course_version_id",
}


class CourseDocumentNotFound(KeyError):
    pass


class CourseDocumentConflict(RuntimeError):
    pass


class CourseMigrationConflict(RuntimeError):
    pass


class CourseDocumentRepository:
    def __init__(self, storage_obj: Any) -> None:
        self.storage = storage_obj

    def load_raw(self, course_id: str) -> dict[str, Any]:
        data = self.storage.load_course(course_id)
        if not data:
            raise CourseDocumentNotFound(course_id)
        return deepcopy(data)

    def is_canonical(self, course_data: dict[str, Any]) -> bool:
        return (
            course_data.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
            and isinstance(course_data.get("course_document"), dict)
        )

    def load_document(self, course_id: str) -> tuple[CourseDocument, bool]:
        raw = self.load_raw(course_id)
        if self.is_canonical(raw):
            return CourseDocument.model_validate(raw["course_document"]), True
        return document_from_legacy_course(raw), False

    def load_course_view(self, course_id: str) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        if not self.is_canonical(raw):
            return raw
        return course_view_from_document(raw, raw["course_document"])

    async def create_generation_shell(
        self,
        course_id: str,
        *,
        title: str,
        job_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.storage.load_course(course_id)
        if existing:
            if self.is_canonical(existing) and existing.get("generation_job_id") == job_id:
                return self.document_envelope(course_id)
            raise CourseDocumentConflict("Course already exists")

        document = refresh_document_revision(CourseDocument(
            course_id=course_id,
            title=title or "未命名课程",
            sections=[],
            blocks=[],
        ))
        raw = self._generated_metadata(metadata or {})
        raw.update({
            "course_id": course_id,
            "course_name": title or "未命名课程",
            "course_schema_version": COURSE_DOCUMENT_SCHEMA,
            "course_document": document.model_dump(mode="json"),
            "course_document_revision": document.document_revision,
            "course_revision_vector": revision_vector_for_document(document).model_dump(mode="json"),
            "course_document_authoritative": True,
            "current_course_version_id": "",
            "generation_job_id": job_id,
            "generation_status": "queued",
            "course_operation_log": [],
        })
        await self._save_raw(course_id, raw)
        return self.document_envelope(course_id)

    async def update_generation_state(
        self,
        course_id: str,
        *,
        job_id: str,
        status: str,
        quality_report: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        self._require_generation_shell(raw, job_id)
        is_published = any(
            item.get("operation") == "publish_generation"
            for item in raw.get("course_operation_log") or []
        )
        publishable_statuses = {"passed", "completed_with_warnings"}
        if is_published and status not in publishable_statuses:
            return raw
        if (
            raw.get("generation_status") in publishable_statuses
            and status not in publishable_statuses
        ):
            return raw
        raw["generation_status"] = status
        if quality_report is not None:
            raw["generation_quality_report"] = deepcopy(quality_report)
        if error:
            raw["generation_error"] = error
        elif status not in {"failed", "completed_with_warnings"}:
            raw.pop("generation_error", None)
        await self._save_raw(course_id, raw)
        return raw

    async def update_metadata(
        self,
        course_id: str,
        updates: dict[str, Any],
        *,
        expected_binding_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Update non-document course metadata without mutating canonical content."""
        raw = self.load_raw(course_id)
        if expected_binding_revision_id is not None:
            current = str((raw.get("knowledge_library_binding") or {}).get("revision_id") or "")
            if current != expected_binding_revision_id:
                raise CourseDocumentConflict("Knowledge-library binding changed")
        for key, value in updates.items():
            if key in _GENERATED_METADATA_EXCLUDES:
                raise CourseDocumentConflict(f"Metadata update cannot replace {key}")
            raw[key] = deepcopy(value)
        await self._save_raw(course_id, raw)
        return raw

    async def publish_generated_course(
        self,
        course_id: str,
        document: CourseDocument,
        *,
        job_id: str,
        command_id: str,
        expected_revision: str,
        metadata: dict[str, Any],
        quality_status: str = "passed",
    ) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        self._require_generation_shell(raw, job_id)
        existing = next(
            (item for item in raw.get("course_operation_log") or [] if item.get("command_id") == command_id),
            None,
        )
        if existing:
            return deepcopy(existing.get("receipt") or {})
        current = CourseDocument.model_validate(raw["course_document"])
        if current.document_revision != expected_revision:
            raise CourseDocumentConflict("Course document revision changed before generation publication")
        if document.course_id != course_id:
            raise CourseDocumentConflict("Generated document belongs to another course")
        if not document.sections or not document.blocks:
            raise CourseDocumentConflict("Generated document is empty")

        updated = refresh_document_revision(document)
        published = {
            key: deepcopy(value)
            for key, value in raw.items()
            if key not in _GENERATED_METADATA_EXCLUDES
        }
        published.update(self._generated_metadata(metadata))
        published.update({
            "course_id": course_id,
            "course_name": updated.title,
            "course_schema_version": COURSE_DOCUMENT_SCHEMA,
            "course_document": updated.model_dump(mode="json"),
            "course_document_revision": updated.document_revision,
            "course_document_authoritative": True,
            "current_course_version_id": updated.document_revision,
            "generation_job_id": job_id,
            "generation_status": quality_status,
        })
        receipt = {
            "command_id": command_id,
            "operation": "publish_generation",
            "previous_revision": current.document_revision,
            "document_revision": updated.document_revision,
            "affected_block_ids": [block.block_id for block in updated.blocks],
            "committed_at": datetime.now(timezone.utc).isoformat(),
        }
        revision_change = revision_event_for_documents(
            current,
            updated,
            command_id=command_id,
            operation="publish_generation",
            affected_block_ids=[block.block_id for block in updated.blocks],
            created_at=receipt["committed_at"],
        )
        receipt["revision_change"] = revision_change.model_dump(mode="json")
        operation_log = list(raw.get("course_operation_log") or [])
        operation_log.append({
            "command_id": command_id,
            "operation": "publish_generation",
            "reason": "首次课程生成通过可发布性质量门",
            "actor": "course_generation",
            "receipt": receipt,
        })
        published["course_operation_log"] = operation_log[-200:]
        published["course_revision_vector"] = revision_change.current.model_dump(mode="json")
        published["course_document_publication"] = {
            "source_format": "generation_workspace_v1",
            "job_id": job_id,
            "section_count": len(updated.sections),
            "block_count": len(updated.blocks),
            "published_at": receipt["committed_at"],
        }
        published.pop("nodes", None)
        await self._save_raw(course_id, published)
        return receipt

    def receipt_for_command(self, course_id: str, command_id: str) -> dict[str, Any] | None:
        if not command_id:
            return None
        raw = self.load_raw(course_id)
        entry = next(
            (item for item in raw.get("course_operation_log") or [] if item.get("command_id") == command_id),
            None,
        )
        return deepcopy(entry.get("receipt") or {}) if entry else None

    def document_envelope(
        self,
        course_id: str,
        *,
        prepared_legacy_course: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        canonical = self.is_canonical(raw)
        if canonical:
            document = CourseDocument.model_validate(raw["course_document"])
        else:
            document = document_from_legacy_course(prepared_legacy_course or raw)
        presentation_document = project_feedback_structures(document)
        return {
            "course_id": str(raw.get("course_id") or course_id),
            "course_name": str(raw.get("course_name") or document.title),
            "current_course_version_id": str(raw.get("current_course_version_id") or ""),
            "subject_pedagogy_profile": deepcopy(raw.get("subject_pedagogy_profile")),
            "generation_quality_report": deepcopy(raw.get("generation_quality_report")),
            "source_format": "canonical" if canonical else "legacy_projection",
            "migration": {
                "required": not canonical,
                "source_checksum": None if canonical else legacy_source_checksum(raw),
                "migrated_at": (raw.get("course_document_migration") or {}).get("migrated_at"),
            },
            "document": presentation_document.model_dump(mode="json"),
            "revision_vector": revision_vector_for_document(document).model_dump(mode="json"),
        }

    async def migrate_legacy_course(
        self,
        course_id: str,
        *,
        expected_source_checksum: str,
    ) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        if self.is_canonical(raw):
            return self.document_envelope(course_id)
        actual_checksum = legacy_source_checksum(raw)
        if actual_checksum != expected_source_checksum:
            raise CourseMigrationConflict("Legacy course changed after migration preview")

        from learning_progress import project_learning_objective_bindings

        prepared = project_learning_objective_bindings(deepcopy(raw))
        document = document_from_legacy_course(prepared)
        canonical = {
            key: deepcopy(value)
            for key, value in raw.items()
            if key != "nodes"
        }
        canonical["course_schema_version"] = COURSE_DOCUMENT_SCHEMA
        canonical["course_document"] = document.model_dump(mode="json")
        canonical["course_document_revision"] = document.document_revision
        canonical["current_course_version_id"] = document.document_revision
        canonical["course_revision_vector"] = revision_vector_for_document(document).model_dump(mode="json")
        canonical["course_document_migration"] = {
            "source_format": "legacy_nodes_markdown",
            "source_checksum": actual_checksum,
            "section_count": len(document.sections),
            "block_count": len(document.blocks),
            "migrated_at": datetime.now(timezone.utc).isoformat(),
        }
        canonical.setdefault("course_operation_log", [])
        await self._save_raw(course_id, canonical)
        return self.document_envelope(course_id)

    async def commit_document(
        self,
        course_id: str,
        document: CourseDocument,
        *,
        expected_revision: str,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        raw = self.load_raw(course_id)
        if not self.is_canonical(raw):
            raise CourseDocumentConflict("Course must be migrated before canonical writes")
        current = CourseDocument.model_validate(raw["course_document"])
        if current.document_revision != expected_revision:
            raise CourseDocumentConflict("Course document revision changed")

        command_id = str(operation.get("command_id") or "")
        existing = next(
            (item for item in raw.get("course_operation_log") or [] if item.get("command_id") == command_id),
            None,
        )
        if command_id and existing:
            return deepcopy(existing.get("receipt") or {})

        updated = refresh_document_revision(document)
        receipt = {
            "command_id": command_id,
            "operation": str(operation.get("operation") or "update_document"),
            "previous_revision": current.document_revision,
            "document_revision": updated.document_revision,
            "affected_block_ids": sorted({str(item) for item in operation.get("affected_block_ids") or [] if item}),
            "committed_at": datetime.now(timezone.utc).isoformat(),
        }
        revision_change = revision_event_for_documents(
            current,
            updated,
            command_id=command_id,
            operation=receipt["operation"],
            affected_block_ids=receipt["affected_block_ids"],
            created_at=receipt["committed_at"],
        )
        receipt["revision_change"] = revision_change.model_dump(mode="json")
        entry = {
            "command_id": command_id,
            "operation": receipt["operation"],
            "reason": str(operation.get("reason") or ""),
            "actor": str(operation.get("actor") or "system"),
            "receipt": receipt,
        }
        operation_log = list(raw.get("course_operation_log") or [])
        operation_log.append(entry)
        raw["course_operation_log"] = operation_log[-200:]
        raw["course_document"] = updated.model_dump(mode="json")
        raw["course_document_revision"] = updated.document_revision
        raw["course_revision_vector"] = revision_change.current.model_dump(mode="json")
        raw["current_course_version_id"] = updated.document_revision
        raw.pop("nodes", None)
        await self._save_raw(course_id, raw)
        return receipt

    async def repair_block_semantics(
        self,
        course_id: str,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        document, canonical = self.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before semantic repair")
        repaired, report = repair_document_block_semantics(document)
        result = {
            "course_id": course_id,
            "document_revision": document.document_revision,
            **report,
        }
        if dry_run or not report["changed"]:
            return result

        command_id = f"repair-block-semantics-v1:{course_id}:{document.document_revision}"
        receipt = await self.commit_document(
            course_id,
            repaired,
            expected_revision=document.document_revision,
            operation={
                "command_id": command_id,
                "operation": "repair_block_semantics",
                "reason": "移除空课程块，并依据教学模块契约修复课程块角色",
                "actor": "course_semantic_repair",
                "affected_block_ids": report["affected_block_ids"],
            },
        )
        result["receipt"] = receipt
        result["document_revision"] = receipt["document_revision"]
        return result

    async def _save_raw(self, course_id: str, data: dict[str, Any]) -> None:
        result = self.storage.save_course(course_id, data)
        if inspect.isawaitable(result):
            await result

    def _require_generation_shell(self, raw: dict[str, Any], job_id: str) -> None:
        if not self.is_canonical(raw):
            raise CourseDocumentConflict("Generation publication requires a canonical course shell")
        if raw.get("generation_job_id") != job_id:
            raise CourseDocumentConflict("Generation job does not own the course shell")

    @staticmethod
    def _generated_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in metadata.items()
            if key not in _GENERATED_METADATA_EXCLUDES
        }
