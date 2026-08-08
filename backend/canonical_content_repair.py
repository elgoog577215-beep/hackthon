"""Safe persistence for website-generated content in empty canonical sections."""

from __future__ import annotations

from course_commands import CourseCommandService
from course_document import CourseBlock, stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository


async def persist_generated_node_content(
    *,
    repository: CourseDocumentRepository,
    course_id: str,
    section_id: str,
    markdown: str,
    actor: str,
) -> dict:
    """Insert model output only when the canonical section has no active block."""
    content = str(markdown or "").strip()
    if (
        len(content) < 40
        or content.startswith("[Error:")
        or content.startswith("[Persistence Error:")
    ):
        raise CourseDocumentConflict(
            "Website generation did not produce content that can be persisted"
        )

    document, _ = repository.load_document(course_id)
    section = next(
        (
            item
            for item in document.sections
            if item.section_id == section_id
        ),
        None,
    )
    if section is None:
        raise CourseDocumentConflict("Course section not found")
    if any(
        block.section_id == section_id and block.status != "retired"
        for block in document.blocks
    ):
        raise CourseDocumentConflict(
            "Canonical section already has content; use block regeneration"
        )

    identity = {
        "course_id": course_id,
        "section_id": section_id,
        "source_revision": document.document_revision,
        "markdown": content,
    }
    block_id = stable_hash(identity, prefix="cbr_")
    command_id = stable_hash(identity, prefix="cmd_")
    block = CourseBlock(
        block_id=block_id,
        section_id=section_id,
        position=0,
        kind="rich_text",
        role="concept",
        payload={
            "title": section.title,
            "markdown": content,
        },
        objective_refs=(
            [section.objective_id]
            if section.objective_id
            else []
        ),
    )
    return await CourseCommandService(repository).insert_block(
        course_id,
        command_id=command_id,
        expected_document_revision=document.document_revision,
        block=block,
        reason="fill_empty_section_from_website_generation",
        actor=actor,
    )


__all__ = ["persist_generated_node_content"]
