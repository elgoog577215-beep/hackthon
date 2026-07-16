from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException

from content_blocks import project_course_content_blocks
from course_commands import CourseCommandService
from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseBlock,
    CourseDocument,
    CourseSection,
    document_from_generation_draft,
    document_from_legacy_course,
    refresh_document_revision,
    repair_document_block_semantics,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from storage_utils import save_course_compat


class MemoryStorage:
    def __init__(self, course: dict | None) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict | None:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


def legacy_course() -> dict:
    return {
        "course_id": "course-1",
        "course_name": "线性代数",
        "current_course_version_id": "cv2",
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "第一章",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "objective-1",
                "parent_node_id": "chapter-1",
                "node_name": "向量",
                "node_level": 2,
                "learning_objective": "理解向量",
                "objective_id": "lo-1",
                "node_content": "## 定义\n\n向量有大小和方向。\n\n## 例题推演\n\n求两个向量之和。",
                "content_blocks": [],
                "difficulty_contract": {"level": "beginner"},
            },
        ],
    }


def test_legacy_course_projects_to_ordered_blocks_with_separate_kind_and_role():
    document = document_from_legacy_course(legacy_course())

    assert document.schema_version == COURSE_DOCUMENT_SCHEMA
    assert [section.section_id for section in document.sections] == ["chapter-1", "objective-1"]
    assert [block.kind for block in document.blocks] == ["rich_text", "rich_text"]
    assert [block.role for block in document.blocks] == ["concept", "example"]
    assert document.blocks[0].objective_refs == ["lo-1"]
    assert document.sections[1].attributes["difficulty_contract"] == {"level": "beginner"}
    assert document.document_revision.startswith("cdr_")


def test_generation_compiler_preserves_teaching_semantics_and_references():
    draft = legacy_course()
    node = draft["nodes"][1]
    node["content_blocks"] = [{
        "block_id": "formula-1",
        "type": "concept",
        "title": "向量表达",
        "content": "$v=(x,y)$",
        "metadata": {"kind": "formula", "role": "reasoning"},
    }]
    node["grounding_contract"] = {"required_evidence_ids": ["evidence-1"]}
    node["grounding_annotations"] = [{"evidence_id": "evidence-2"}]
    node["asset_refs"] = ["asset-1"]
    node["concept_refs"] = ["concept-1"]

    document = document_from_generation_draft(draft)
    block = document.blocks[0]

    assert block.kind == "formula"
    assert block.role == "reasoning"
    assert block.objective_refs == ["lo-1"]
    assert block.evidence_refs == ["evidence-1", "evidence-2"]
    assert block.asset_refs == ["asset-1"]
    assert block.concept_refs == ["concept-1"]


def semantic_drift_document() -> CourseDocument:
    return refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="算法",
        sections=[CourseSection(
            section_id="L2-1-1",
            title="1.1 渐进记号与复杂度分析",
            position=0,
            level=2,
        )],
        blocks=[
            CourseBlock(
                block_id="empty-heading",
                section_id="L2-1-1",
                position=0,
                role="orientation",
                payload={"title": "1.1 渐进记号与复杂度分析", "markdown": ""},
            ),
            CourseBlock(
                block_id="objective",
                section_id="L2-1-1",
                position=1,
                role="concept",
                payload={"title": "本节任务", "markdown": "给出代码的时间复杂度。"},
            ),
            CourseBlock(
                block_id="action",
                section_id="L2-1-1",
                position=2,
                role="concept",
                payload={"title": "学习者行动", "markdown": "请独立分析两层循环。"},
            ),
            CourseBlock(
                block_id="feedback",
                section_id="L2-1-1",
                position=3,
                role="checkpoint",
                payload={"title": "检查与反馈", "markdown": "对照答案检查推导过程。"},
            ),
        ],
    ))


def test_semantic_repair_removes_empty_heading_and_preserves_substantive_blocks():
    document = semantic_drift_document()
    repaired, report = repair_document_block_semantics(document)

    assert report["changed"] is True
    assert report["removed_empty_block_ids"] == ["empty-heading"]
    assert [block.block_id for block in repaired.blocks] == ["objective", "action", "feedback"]
    assert [block.role for block in repaired.blocks] == ["objective", "activity", "feedback"]
    assert [block.position for block in repaired.blocks] == [0, 1, 2]
    assert repaired.blocks[0].payload["markdown"] == "给出代码的时间复杂度。"


@pytest.mark.asyncio
async def test_generation_shell_publishes_canonical_document_once():
    storage = MemoryStorage(None)
    repository = CourseDocumentRepository(storage)
    shell = await repository.create_generation_shell(
        "course-1",
        title="线性代数",
        job_id="job-1",
        metadata={"nodes": [{"node_id": "draft-only"}]},
    )

    assert shell["document"]["sections"] == []
    assert storage.course["generation_status"] == "queued"
    assert "nodes" not in storage.course

    document = document_from_generation_draft(legacy_course())
    receipt = await repository.publish_generated_course(
        "course-1",
        document,
        job_id="job-1",
        command_id="publish-job-1",
        expected_revision=shell["document"]["document_revision"],
        metadata={
            "nodes": [{"node_id": "must-not-persist"}],
            "generation_quality_report": {"final_status": "passed"},
        },
    )
    repeated = await repository.publish_generated_course(
        "course-1",
        document,
        job_id="job-1",
        command_id="publish-job-1",
        expected_revision="stale-revision",
        metadata={},
    )

    assert repeated == receipt
    assert storage.save_count == 2
    assert storage.course["generation_status"] == "passed"
    assert storage.course["current_course_version_id"] == receipt["document_revision"]
    assert storage.course["course_document_revision"] == receipt["document_revision"]
    assert "nodes" not in storage.course
    assert len(storage.course["course_document"]["blocks"]) == 2

    with pytest.raises(CourseDocumentConflict):
        await repository.publish_generated_course(
            "course-1",
            document,
            job_id="job-1",
            command_id="publish-job-1-again",
            expected_revision=shell["document"]["document_revision"],
            metadata={},
        )


@pytest.mark.asyncio
async def test_repository_commits_semantic_repair_as_a_canonical_operation():
    document = semantic_drift_document()
    storage = MemoryStorage({
        "course_id": "course-1",
        "course_name": "算法",
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
        "course_operation_log": [],
    })
    repository = CourseDocumentRepository(storage)

    preview = await repository.repair_block_semantics("course-1")
    applied = await repository.repair_block_semantics("course-1", dry_run=False)

    assert preview["changed"] is True
    assert storage.save_count == 1
    assert applied["receipt"]["operation"] == "repair_block_semantics"
    assert storage.course["course_operation_log"][-1]["actor"] == "course_semantic_repair"
    assert [block["role"] for block in storage.course["course_document"]["blocks"]] == [
        "objective", "activity", "feedback",
    ]


def test_legacy_projection_is_read_only_until_explicit_migration():
    storage = MemoryStorage(legacy_course())
    repository = CourseDocumentRepository(storage)

    envelope = repository.document_envelope("course-1")

    assert envelope["source_format"] == "legacy_projection"
    assert envelope["migration"]["required"] is True
    assert storage.save_count == 0
    assert "course_document" not in storage.course


@pytest.mark.asyncio
async def test_migration_removes_persisted_nodes_and_remains_idempotent():
    storage = MemoryStorage(legacy_course())
    repository = CourseDocumentRepository(storage)
    preview = repository.document_envelope("course-1")

    migrated = await repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    repeated = await repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )

    assert migrated["source_format"] == "canonical"
    assert repeated["document"]["document_revision"] == migrated["document"]["document_revision"]
    assert storage.save_count == 1
    assert storage.course["course_schema_version"] == COURSE_DOCUMENT_SCHEMA
    assert "nodes" not in storage.course
    assert repository.load_course_view("course-1")["nodes"][1]["node_content"].startswith("## 定义")
    view = repository.load_course_view("course-1")
    document, _ = repository.load_document("course-1")
    assert view["nodes"][1]["content_blocks"][0]["block_revision_id"] == document.blocks[0].internal_revision
    projected = project_course_content_blocks(view)
    assert projected["nodes"][1]["content_blocks"][0]["block_revision_id"] == document.blocks[0].internal_revision


@pytest.mark.asyncio
async def test_replace_block_checks_revisions_and_returns_same_receipt_on_retry():
    storage = MemoryStorage(legacy_course())
    repository = CourseDocumentRepository(storage)
    preview = repository.document_envelope("course-1")
    await repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    document, _ = repository.load_document("course-1")
    target = document.blocks[0]
    service = CourseCommandService(repository)

    receipt = await service.replace_block(
        "course-1",
        command_id="command-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        block_id=target.block_id,
        payload={"title": "定义", "markdown": "向量同时具有大小和方向。"},
    )
    repeated = await service.replace_block(
        "course-1",
        command_id="command-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        block_id=target.block_id,
        payload={"title": "不会再次写入", "markdown": "重复请求"},
    )

    assert repeated == receipt
    assert storage.save_count == 2
    updated, _ = repository.load_document("course-1")
    assert updated.blocks[0].payload["markdown"] == "向量同时具有大小和方向。"
    with pytest.raises(CourseDocumentConflict):
        await service.replace_block(
            "course-1",
            command_id="command-2",
            expected_document_revision=document.document_revision,
            expected_block_revision=target.internal_revision,
            block_id=target.block_id,
            payload={"title": "过期修改", "markdown": "不应写入"},
        )


@pytest.mark.asyncio
async def test_legacy_save_helper_rejects_authoritative_course_documents():
    storage = MemoryStorage(legacy_course())
    canonical_view = {
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document_authoritative": True,
    }

    with pytest.raises(HTTPException) as exc:
        await save_course_compat(storage, "course-1", canonical_view)

    assert exc.value.status_code == 409
    assert storage.save_count == 0
