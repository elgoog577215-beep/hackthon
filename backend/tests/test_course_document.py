from __future__ import annotations

import asyncio
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


class YieldingMemoryStorage(MemoryStorage):
    def __init__(self, course: dict | None) -> None:
        super().__init__(course)
        self.yield_writes = False

    async def save_course(self, course_id: str, data: dict) -> None:
        if self.yield_writes:
            await asyncio.sleep(0.02)
        await super().save_course(course_id, data)


class PausingMultiCourseStorage:
    def __init__(self) -> None:
        self.courses: dict[str, dict] = {}
        self.paused_course_id: str | None = None
        self.paused_save_started = asyncio.Event()
        self.release_paused_save = asyncio.Event()
        self.other_course_saved = asyncio.Event()

    def load_course(self, course_id: str) -> dict | None:
        return deepcopy(self.courses.get(course_id))

    async def save_course(self, course_id: str, data: dict) -> None:
        if course_id == self.paused_course_id:
            self.paused_save_started.set()
            await self.release_paused_save.wait()
        self.courses[course_id] = deepcopy(data)
        if self.paused_course_id and course_id != self.paused_course_id:
            self.other_course_saved.set()


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


def test_feedback_blocks_compile_to_review_checkpoint_with_task_structure():
    draft = legacy_course()
    node = draft["nodes"][1]
    node["content_blocks"] = [{
        "block_id": "feedback-1",
        "type": "feedback",
        "title": "检查与反馈",
        "content": "### 任务 1：判断\n\n写出核对标准。\n\n### 任务 2：验证\n\n给出参考结论。",
    }]

    document = document_from_generation_draft(draft)
    block = document.blocks[0]

    assert block.role == "feedback"
    assert block.kind == "review_checkpoint"
    assert block.payload["feedback_structure"]["schema_version"] == "course_feedback_v1"
    assert len(block.payload["feedback_structure"]["sections"]) == 2


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
async def test_repository_creates_imported_course_as_canonical_document():
    storage = MemoryStorage(None)
    repository = CourseDocumentRepository(storage)

    created = await repository.create_imported_course(
        "course-1",
        imported_course=legacy_course(),
    )

    assert created["source_format"] == "canonical"
    assert created["migration"]["required"] is False
    assert storage.save_count == 1
    assert storage.course["course_schema_version"] == COURSE_DOCUMENT_SCHEMA
    assert storage.course["course_document_authoritative"] is True
    assert storage.course["current_course_version_id"].startswith("cdr_")
    assert storage.course["course_operation_log"] == []
    assert "nodes" not in storage.course
    CourseDocument.model_validate(storage.course["course_document"])


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
async def test_patch_block_text_updates_only_the_exact_span_and_checks_anchors():
    storage = MemoryStorage(legacy_course())
    repository = CourseDocumentRepository(storage)
    preview = repository.document_envelope("course-1")
    await repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    document, _ = repository.load_document("course-1")
    target = document.blocks[0]
    markdown = str(target.payload["markdown"])
    before = "大小和方向"
    start = markdown.index(before)

    receipt = await CourseCommandService(repository).patch_block_text(
        "course-1",
        command_id="patch-span-1",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        block_id=target.block_id,
        field="markdown",
        start=start,
        end=start + len(before),
        before=before,
        after="大小、方向和线性组合语义",
        prefix_context=markdown[max(0, start - 12):start],
        suffix_context=markdown[start + len(before):start + len(before) + 12],
    )

    updated, _ = repository.load_document("course-1")
    updated_target = next(item for item in updated.blocks if item.block_id == target.block_id)
    assert updated_target.payload["title"] == target.payload["title"]
    assert "大小、方向和线性组合语义" in updated_target.payload["markdown"]
    assert receipt["operation"] == "patch_course_span"

    with pytest.raises(CourseDocumentConflict, match="revision changed"):
        await CourseCommandService(repository).patch_block_text(
            "course-1",
            command_id="patch-span-stale",
            expected_document_revision=updated.document_revision,
            expected_block_revision=target.internal_revision,
            block_id=target.block_id,
            field="markdown",
            start=start,
            end=start + len(before),
            before=before,
            after="过期内容",
        )


@pytest.mark.asyncio
async def test_concurrent_commands_with_the_same_revision_allow_exactly_one_commit():
    storage = YieldingMemoryStorage(legacy_course())
    first_repository = CourseDocumentRepository(storage)
    preview = first_repository.document_envelope("course-1")
    await first_repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    document, _ = first_repository.load_document("course-1")
    target = document.blocks[0]
    storage.yield_writes = True

    async def replace(repository: CourseDocumentRepository, command_id: str, markdown: str):
        return await CourseCommandService(repository).replace_block(
            "course-1",
            command_id=command_id,
            expected_document_revision=document.document_revision,
            expected_block_revision=target.internal_revision,
            block_id=target.block_id,
            payload={**target.payload, "markdown": markdown},
        )

    results = await asyncio.gather(
        replace(first_repository, "concurrent-1", "并发写入一"),
        replace(CourseDocumentRepository(storage), "concurrent-2", "并发写入二"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, CourseDocumentConflict) for result in results) == 1
    assert len(storage.course["course_operation_log"]) == 1


@pytest.mark.asyncio
async def test_course_command_lock_does_not_serialize_different_courses():
    storage = PausingMultiCourseStorage()
    repository = CourseDocumentRepository(storage)
    for course_id in ("course-a", "course-b"):
        imported = legacy_course()
        imported["course_id"] = course_id
        await repository.create_imported_course(course_id, imported_course=imported)

    document_a, _ = repository.load_document("course-a")
    document_b, _ = repository.load_document("course-b")
    target_a = document_a.blocks[0]
    target_b = document_b.blocks[0]
    storage.paused_course_id = "course-a"

    first = asyncio.create_task(CourseCommandService(repository).replace_block(
        "course-a",
        command_id="course-a-write",
        expected_document_revision=document_a.document_revision,
        expected_block_revision=target_a.internal_revision,
        block_id=target_a.block_id,
        payload={**target_a.payload, "markdown": "课程 A 写入"},
    ))
    await storage.paused_save_started.wait()
    second = asyncio.create_task(CourseCommandService(
        CourseDocumentRepository(storage),
    ).replace_block(
        "course-b",
        command_id="course-b-write",
        expected_document_revision=document_b.document_revision,
        expected_block_revision=target_b.internal_revision,
        block_id=target_b.block_id,
        payload={**target_b.payload, "markdown": "课程 B 写入"},
    ))

    different_course_completed = False
    try:
        await asyncio.wait_for(storage.other_course_saved.wait(), timeout=0.2)
        different_course_completed = True
    finally:
        storage.release_paused_save.set()
        await asyncio.gather(first, second)

    assert different_course_completed is True


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
