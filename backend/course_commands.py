"""Canonical course document commands."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_document import CourseBlock, CourseSection, refresh_block_revision, stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository


class CourseCommandService:
    def __init__(self, repository: CourseDocumentRepository) -> None:
        self.repository = repository

    async def replace_block(
        self,
        course_id: str,
        *,
        command_id: str,
        expected_document_revision: str,
        expected_block_revision: str,
        block_id: str,
        payload: dict[str, Any],
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing
        document, canonical = self.repository.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before block replacement")
        target = next((block for block in document.blocks if block.block_id == block_id), None)
        if not target:
            raise CourseDocumentConflict("Course block not found")
        if target.internal_revision != expected_block_revision:
            raise CourseDocumentConflict("Course block revision changed")
        target.payload = deepcopy(payload)
        refresh_block_revision(target)
        return await self.repository.commit_document(
            course_id,
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "replace_block",
                "affected_block_ids": [block_id],
                "reason": reason,
                "actor": actor,
            },
        )

    async def insert_block(
        self,
        course_id: str,
        *,
        command_id: str,
        expected_document_revision: str,
        block: CourseBlock,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing
        document, canonical = self.repository.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before block insertion")
        if any(item.block_id == block.block_id for item in document.blocks):
            raise CourseDocumentConflict("Course block ID already exists")
        if not any(section.section_id == block.section_id for section in document.sections):
            raise CourseDocumentConflict("Course section not found")
        for item in document.blocks:
            if item.section_id == block.section_id and item.position >= block.position:
                item.position += 1
        document.blocks.append(refresh_block_revision(block))
        return await self.repository.commit_document(
            course_id,
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "insert_block",
                "affected_block_ids": [block.block_id],
                "reason": reason,
                "actor": actor,
            },
        )

    async def delete_block(
        self,
        course_id: str,
        *,
        command_id: str,
        expected_document_revision: str,
        expected_block_revision: str,
        block_id: str,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing
        document, canonical = self.repository.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before block deletion")
        target = next((block for block in document.blocks if block.block_id == block_id), None)
        if not target:
            raise CourseDocumentConflict("Course block not found")
        if target.internal_revision != expected_block_revision:
            raise CourseDocumentConflict("Course block revision changed")
        target.status = "retired"
        refresh_block_revision(target)
        return await self.repository.commit_document(
            course_id,
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "delete_block",
                "affected_block_ids": [block_id],
                "reason": reason,
                "actor": actor,
            },
        )

    async def update_section_objective(
        self,
        course_id: str,
        *,
        command_id: str,
        expected_document_revision: str,
        expected_objective_revision: str,
        section_id: str,
        learning_objective: str,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing
        document, canonical = self.repository.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before objective updates")
        section = next(
            (item for item in document.sections if item.section_id == section_id),
            None,
        )
        if section is None:
            raise CourseDocumentConflict("Course section not found")
        if _objective_revision(section) != expected_objective_revision:
            raise CourseDocumentConflict("Course learning objective revision changed")

        next_objective = learning_objective.strip()
        if not next_objective:
            raise CourseDocumentConflict("Course learning objective cannot be empty")
        if not section.objective_id:
            section.objective_id = stable_hash(
                {"course_id": course_id, "section_id": section_id},
                prefix="obj_",
            )
        section.learning_objective = next_objective
        section.objective_revision_id = stable_hash(
            {
                "objective_id": section.objective_id,
                "learning_objective": section.learning_objective,
                "section_id": section.section_id,
            },
            prefix="cor_",
        )
        affected_block_ids = [
            block.block_id
            for block in document.blocks
            if block.section_id == section_id and block.status != "retired"
        ]
        return await self.repository.commit_document(
            course_id,
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "update_section_objective",
                "affected_block_ids": affected_block_ids,
                "reason": reason,
                "actor": actor,
            },
        )


def _objective_revision(section: CourseSection) -> str:
    return section.objective_revision_id or stable_hash(
        {
            "objective_id": section.objective_id,
            "learning_objective": section.learning_objective,
            "section_id": section.section_id,
        },
        prefix="cor_",
    )
