from __future__ import annotations

from copy import deepcopy

import pytest

from canonical_content_repair import persist_generated_node_content
from course_repository import CourseDocumentConflict, CourseDocumentRepository


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)
        self.save_count += 1


def empty_legacy_course() -> dict:
    return {
        "course_id": "course-empty-section",
        "course_name": "线性代数：理论与应用",
        "nodes": [
            {
                "node_id": "chapter-3",
                "parent_node_id": "root",
                "node_name": "第三章 行列式与逆矩阵",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "section-3-1",
                "parent_node_id": "chapter-3",
                "node_name": "第三章 行列式与逆矩阵 - 子节点 1",
                "node_level": 2,
                "learning_objective": "能够解释并应用行列式与逆矩阵",
                "objective_id": "objective-3-1",
                "node_content": "",
            },
        ],
    }


async def canonical_repository() -> tuple[CourseDocumentRepository, MemoryStorage]:
    storage = MemoryStorage(empty_legacy_course())
    repository = CourseDocumentRepository(storage)
    preview = repository.document_envelope("course-empty-section")
    await repository.migrate_legacy_course(
        "course-empty-section",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    return repository, storage


@pytest.mark.asyncio
async def test_generated_content_can_fill_one_empty_canonical_section():
    repository, storage = await canonical_repository()
    before, _ = repository.load_document("course-empty-section")
    markdown = (
        "## 行列式的定义与几何意义\n\n"
        "行列式刻画线性变换对有向面积或体积的缩放。\n\n"
        "## 例题推演\n\n计算二阶行列式并检查符号。"
    )

    receipt = await persist_generated_node_content(
        repository=repository,
        course_id="course-empty-section",
        section_id="section-3-1",
        markdown=markdown,
        actor="teacher-1",
    )

    after, _ = repository.load_document("course-empty-section")
    assert receipt["operation"] == "insert_block"
    assert after.document_revision != before.document_revision
    assert len(after.blocks) == 1
    assert after.blocks[0].section_id == "section-3-1"
    assert after.blocks[0].payload["markdown"] == markdown
    section = next(
        item for item in before.sections if item.section_id == "section-3-1"
    )
    assert after.blocks[0].objective_refs == [section.objective_id]
    assert storage.save_count == 2


@pytest.mark.asyncio
async def test_generated_content_cannot_overwrite_nonempty_canonical_section():
    repository, storage = await canonical_repository()
    await persist_generated_node_content(
        repository=repository,
        course_id="course-empty-section",
        section_id="section-3-1",
        markdown=(
            "## 定义\n\n第一版网站链路生成正文，包含数学定义、"
            "成立条件与一个完整例题，并逐步解释计算依据与结果检查。"
        ),
        actor="teacher-1",
    )
    before = deepcopy(storage.course)

    with pytest.raises(
        CourseDocumentConflict,
        match="block regeneration",
    ):
        await persist_generated_node_content(
            repository=repository,
            course_id="course-empty-section",
            section_id="section-3-1",
            markdown=(
                "## 定义\n\n不应覆盖已有正文；即使新结果足够长，"
                "也必须进入块级重生成审阅流程后才能替换。"
            ),
            actor="teacher-1",
        )

    assert storage.course == before


@pytest.mark.asyncio
async def test_provider_error_text_is_never_persisted():
    repository, storage = await canonical_repository()
    before = deepcopy(storage.course)

    with pytest.raises(CourseDocumentConflict, match="did not produce content"):
        await persist_generated_node_content(
            repository=repository,
            course_id="course-empty-section",
            section_id="section-3-1",
            markdown="[Error: provider timeout]",
            actor="teacher-1",
        )

    assert storage.course == before
