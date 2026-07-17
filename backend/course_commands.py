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

    async def apply_block_operation_group(
        self,
        course_id: str,
        *,
        command_id: str,
        expected_document_revision: str,
        insertions: list[dict[str, Any]],
        retire_block_ids: list[str] | None = None,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        """Apply a reviewed multi-block course change in one document commit."""
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing

        document, canonical = self.repository.load_document(course_id)
        if not canonical:
            raise CourseDocumentConflict("Course must be migrated before grouped course changes")
        if document.document_revision != expected_document_revision:
            raise CourseDocumentConflict("Course document revision changed")

        blocks_by_id = {block.block_id: block for block in document.blocks}
        normalized_insertions: list[tuple[CourseBlock, str]] = []
        new_ids: set[str] = set()
        for item in insertions:
            block = item.get("block")
            block = block if isinstance(block, CourseBlock) else CourseBlock.model_validate(block)
            after_block_id = str(item.get("after_block_id") or "")
            anchor = blocks_by_id.get(after_block_id)
            if anchor is None or anchor.status == "retired":
                raise CourseDocumentConflict("Course insertion anchor not found")
            if block.section_id != anchor.section_id:
                raise CourseDocumentConflict("Inserted block must stay in its anchor section")
            if block.block_id in blocks_by_id or block.block_id in new_ids:
                raise CourseDocumentConflict("Course block ID already exists")
            if not any(section.section_id == block.section_id for section in document.sections):
                raise CourseDocumentConflict("Course section not found")
            new_ids.add(block.block_id)
            normalized_insertions.append((deepcopy(block), after_block_id))

        retired_ids = {
            str(block_id)
            for block_id in retire_block_ids or []
            if str(block_id)
        }
        for block_id in retired_ids:
            target = blocks_by_id.get(block_id)
            if target is None:
                raise CourseDocumentConflict("Course block to retire not found")
            if target.status != "retired":
                target.status = "retired"

        additions_by_anchor: dict[str, list[CourseBlock]] = {}
        for block, anchor_id in normalized_insertions:
            additions_by_anchor.setdefault(anchor_id, []).append(block)

        reordered: list[CourseBlock] = []
        for section in sorted(document.sections, key=lambda item: (item.position, item.section_id)):
            section_blocks = sorted(
                (block for block in document.blocks if block.section_id == section.section_id),
                key=lambda item: (item.position, item.block_id),
            )
            next_position = 0
            for block in section_blocks:
                block.position = next_position
                reordered.append(refresh_block_revision(block))
                next_position += 1
                for insertion in additions_by_anchor.get(block.block_id, []):
                    insertion.position = next_position
                    reordered.append(refresh_block_revision(insertion))
                    next_position += 1

        if len(reordered) != len(document.blocks) + len(normalized_insertions):
            raise CourseDocumentConflict("Grouped course change contains an unresolved insertion")
        document.blocks = reordered
        affected_block_ids = sorted(new_ids | retired_ids)
        return await self.repository.commit_document(
            course_id,
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "apply_course_evolution_plan",
                "affected_block_ids": affected_block_ids,
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
