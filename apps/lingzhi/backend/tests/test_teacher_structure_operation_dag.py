from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from course_commands import CourseCommandService
from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_evolution import (
    CourseEvolutionRepository,
    accept_change_set,
    undo_change_set,
)
from course_evolution.teacher_planning import (
    build_teacher_course_change_context,
    create_teacher_course_change_plan,
    review_teacher_course_change_scope,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository


class MemoryCourseStorage:
    def __init__(self, course: dict):
        self.course = deepcopy(course)
        self.save_count = 0

    def load_course(self, course_id: str):
        if course_id != self.course["course_id"]:
            return None
        return deepcopy(self.course)

    async def save_course(self, course_id: str, course: dict):
        assert course_id == self.course["course_id"]
        self.course = deepcopy(course)
        self.save_count += 1


def _document() -> CourseDocument:
    section_ids = [f"lesson-{index}" for index in range(1, 6)]
    return refresh_document_revision(CourseDocument(
        course_id="course-structure-dag",
        title="跨讲结构课程",
        sections=[
            CourseSection(
                section_id=section_id,
                title=f"第 {index} 讲",
                position=index - 1,
            )
            for index, section_id in enumerate(section_ids, start=1)
        ],
        blocks=[
            CourseBlock(
                block_id=f"block-{section_id}",
                section_id=section_id,
                position=0,
                payload={"markdown": f"{section_id} 正式内容"},
            )
            for section_id in section_ids
        ],
    ))


def _raw_course(document: CourseDocument) -> dict:
    return {
        "course_id": document.course_id,
        "course_name": document.title,
        "course_schema_version": "course_document_v1",
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
        "course_operation_log": [],
    }


def _dag_is_topological(dag: dict) -> bool:
    dependencies = {
        item["operation_id"]: set(item["depends_on_operation_ids"])
        for item in dag["nodes"]
    }
    resolved: set[str] = set()
    for operation_id in dag["topological_order"]:
        if not dependencies[operation_id].issubset(resolved):
            return False
        resolved.add(operation_id)
    return resolved == set(dependencies)


def test_partial_structure_review_rebuilds_dag_and_atomically_migrates_refs(tmp_path):
    document = _document()
    context = build_teacher_course_change_context(
        course_id=document.course_id,
        document=document,
        preview=None,
        authoring={},
        question_bank=None,
        representation_registries=[],
    )
    target_unit = next(
        item
        for item in context.units
        if item.unit_id == "course_content:block-lesson-4"
    )

    async def analyzer(_overview, _candidates, _instruction):
        return {
            "interpreted_goal": "重排课程，合并第三、四讲并新增总结讲",
            "signal_kind": "structural",
            "signal_confidence": 1,
            "affected_units": [{
                "unit_id": target_unit.unit_id,
                "disposition": "reuse_exact",
                "reason": "第四讲内容并入第三讲",
                "confidence": 1,
            }],
            "structure": {
                "required": True,
                "reason": "按教师确认的跨讲结构调整执行",
                "retire_node_ids": ["lesson-2"],
                "proposed_outline": [
                    {
                        "provisional_id": "lesson-5",
                        "title": "第 5 讲",
                        "parent_ref": "root",
                        "source_node_ids": ["lesson-5"],
                    },
                    {
                        "provisional_id": "lesson-1",
                        "title": "第 1 讲",
                        "parent_ref": "root",
                        "source_node_ids": ["lesson-1"],
                    },
                    {
                        "provisional_id": "merge-3-4",
                        "title": "第 3—4 讲",
                        "parent_ref": "root",
                        "source_node_ids": ["lesson-3", "lesson-4"],
                    },
                    {
                        "provisional_id": "new-summary",
                        "title": "课程总结",
                        "parent_ref": "root",
                        "source_node_ids": [],
                    },
                ],
            },
        }

    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    created = asyncio.run(create_teacher_course_change_plan(
        context=context,
        user_id="teacher-1",
        request_id="structure-dag-1",
        instruction="重排课程，合并第三、四讲并新增总结讲",
        repository=evolution_repository,
        analyzer=analyzer,
    ))
    original_plan = created.change_sets[0]
    original_dag = original_plan.impact_summary["structure_operation_dag"]
    assert _dag_is_topological(original_dag)
    assert {
        item["operation_type"] for item in original_dag["nodes"]
    } == {
        "INSERT_OUTLINE_NODE",
        "MERGE_OUTLINE_NODES",
        "REORDER_OUTLINE_NODES",
        "RETIRE_OUTLINE_NODE",
        "REBUILD_OUTLINE",
    }
    original_rebuild = original_plan.operations[0].payload["outline_rebuild"]
    original_summary_id = next(
        item["final_section_id"]
        for item in original_rebuild["identity_mapping"]
        if item["provisional_id"] == "new-summary"
    )
    migration_id = original_plan.teacher_change_planning.unit_migrations[0].migration_id

    blocked_review = review_teacher_course_change_scope(
        repository=evolution_repository,
        user_id="teacher-1",
        course_id=document.course_id,
        change_set_id=original_plan.change_set_id,
        selected_migration_ids=[migration_id],
        proposed_outline=[
            {
                "provisional_id": "lesson-5",
                "title": "第 5 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-5"],
            },
            {
                "provisional_id": "lesson-1",
                "title": "第 1 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-1"],
            },
            {
                "provisional_id": "lesson-2",
                "title": "第 2 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-2"],
            },
            {
                "provisional_id": "lesson-3",
                "title": "第 3 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-3"],
            },
            {
                "provisional_id": "new-summary",
                "title": "总结与迁移",
                "parent_ref": "root",
                "source_node_ids": [],
            },
        ],
        context=context,
    )
    blocked_migration = (
        blocked_review.change_sets[0]
        .teacher_change_planning.unit_migrations[0]
    )
    assert blocked_migration.dependency_ids == []
    assert blocked_migration.disposition == "blocked"
    assert blocked_migration.candidate_status == "failed"
    assert blocked_migration.metadata["pre_structure_dependency_ids"] == [
        "lesson-4"
    ]
    assert blocked_review.change_sets[0].impact_summary[
        "structure_dependency_recalculation"
    ]["blocked_migration_ids"] == [migration_id]

    reviewed = review_teacher_course_change_scope(
        repository=evolution_repository,
        user_id="teacher-1",
        course_id=document.course_id,
        change_set_id=original_plan.change_set_id,
        selected_migration_ids=[migration_id],
        confirm_structure=True,
        proposed_outline=[
            {
                "provisional_id": "lesson-5",
                "title": "第 5 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-5"],
            },
            {
                "provisional_id": "lesson-1",
                "title": "第 1 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-1"],
            },
            {
                "provisional_id": "lesson-2",
                "title": "第 2 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-2"],
            },
            {
                "provisional_id": "merge-3-4",
                "title": "第 3—4 讲",
                "parent_ref": "root",
                "source_node_ids": ["lesson-3", "lesson-4"],
            },
            {
                "provisional_id": "new-summary",
                "title": "总结与迁移",
                "parent_ref": "root",
                "source_node_ids": [],
            },
        ],
        context=context,
    )
    plan = reviewed.change_sets[0]
    structure_reference_operations = [
        item
        for item in plan.operations
        if item.payload.get("action") == "rebind_section_references"
    ]
    assert {
        item.payload["domain"] for item in structure_reference_operations
    } == {
        "authoring_structure_refs",
        "ppt_structure_refs",
        "question_bank_structure_refs",
    }
    assert {
        item.operation_id for item in structure_reference_operations
    }.issubset(plan.selected_operation_ids)
    rebuilt_dag = plan.impact_summary["structure_operation_dag"]
    assert _dag_is_topological(rebuilt_dag)
    assert "RETIRE_OUTLINE_NODE" not in {
        item["operation_type"] for item in rebuilt_dag["nodes"]
    }
    review_history = plan.impact_summary["structure_review_history"]
    rebuilt_operation_ids = {
        item["operation_id"] for item in rebuilt_dag["nodes"]
    }
    retained_types = {
        item["operation_type"]
        for item in original_dag["nodes"]
        if item["operation_id"] in rebuilt_operation_ids
    }
    assert "MERGE_OUTLINE_NODES" in retained_types
    assert any(
        item["operation_type"] == "RETIRE_OUTLINE_NODE"
        and item["operation_id"] in review_history[0]["excluded_operation_ids"]
        for item in original_dag["nodes"]
    )

    migration = plan.teacher_change_planning.unit_migrations[0]
    assert migration.disposition == "reuse_rebind"
    assert migration.dependency_ids == ["lesson-3"]
    dependency_receipt = plan.impact_summary[
        "structure_dependency_recalculation"
    ]["items"][0]
    assert dependency_receipt == {
        "migration_id": migration_id,
        "before_dependency_ids": [],
        "source_dependency_ids": ["lesson-4"],
        "after_dependency_ids": ["lesson-3"],
        "status": "rebound",
    }

    rebuild = plan.operations[0].payload["outline_rebuild"]
    summary_id = next(
        item["final_section_id"]
        for item in rebuild["identity_mapping"]
        if item["provisional_id"] == "new-summary"
    )
    assert summary_id == original_summary_id
    assert rebuild["section_id_map"]["lesson-4"] == "lesson-3"
    assert rebuild["section_tombstones"] == [{
        "section_id": "lesson-4",
        "mapped_to_section_ids": ["lesson-3"],
        "reason": "merged",
    }]

    storage = MemoryCourseStorage(_raw_course(document))
    document_repository = CourseDocumentRepository(storage)
    applied = accept_change_set(
        storage.course,
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=plan.selected_operation_ids,
        repository=evolution_repository,
        document_repository=document_repository,
        domain_candidate_applier=lambda _plan, operation_ids: {
            "status": "applied",
            "items": [
                {
                    "operation_id": operation_id,
                    "status": "applied",
                    "result_revision_id": operation_id,
                }
                for operation_id in operation_ids
            ],
        },
    )
    updated, _ = document_repository.load_document(document.course_id)
    assert storage.save_count == 1
    assert [item.section_id for item in updated.sections] == [
        "lesson-5",
        "lesson-1",
        "lesson-2",
        "lesson-3",
        summary_id,
    ]
    assert next(
        item for item in updated.blocks if item.block_id == "block-lesson-4"
    ).section_id == "lesson-3"
    assert {item.block_id for item in updated.blocks} == {
        f"block-lesson-{index}" for index in range(1, 6)
    }
    receipt = applied.change_sets[0].application_receipt[
        "outline_rebuild_journal"
    ]
    assert receipt["section_tombstones"] == rebuild["section_tombstones"]
    assert receipt["operation_dag"]["revision"] == rebuilt_dag["revision"]

    undo_change_set(
        user_id="teacher-1",
        course_id=document.course_id,
        change_set_id=plan.change_set_id,
        repository=evolution_repository,
        document_repository=document_repository,
        domain_candidate_undoer=lambda _plan: {
            "status": "undone",
            "items": [],
        },
    )
    restored, _ = document_repository.load_document(document.course_id)
    assert storage.save_count == 2
    assert [item.section_id for item in restored.sections] == [
        f"lesson-{index}" for index in range(1, 6)
    ]
    assert next(
        item for item in restored.blocks if item.block_id == "block-lesson-4"
    ).section_id == "lesson-4"
    assert all(item.status == "final" for item in restored.blocks)


def test_invalid_structure_dag_fails_before_the_atomic_course_commit():
    document = _document()
    storage = MemoryCourseStorage(_raw_course(document))
    repository = CourseDocumentRepository(storage)
    service = CourseCommandService(repository)
    outline_rebuild = {
        "sections": [item.model_dump(mode="json") for item in document.sections],
        "section_id_map": {
            item.section_id: item.section_id for item in document.sections
        },
        "section_tombstones": [],
        "reference_migrations": [
            {
                "source_section_id": item.section_id,
                "target_section_ids": [item.section_id],
                "primary_target_section_id": item.section_id,
                "resolution": "unique",
            }
            for item in document.sections
        ],
        "operation_dag": {
            "schema_version": "course_structure_operation_dag_v1",
            "revision": "cycle",
            "nodes": [
                {
                    "operation_id": "first",
                    "depends_on_operation_ids": ["second"],
                },
                {
                    "operation_id": "second",
                    "depends_on_operation_ids": ["first"],
                },
            ],
            "topological_order": ["first", "second"],
        },
    }

    with pytest.raises(
        CourseDocumentConflict,
        match="operation graph is not acyclic",
    ):
        asyncio.run(service.apply_block_operation_group(
            document.course_id,
            command_id="invalid-structure-dag",
            expected_document_revision=document.document_revision,
            insertions=[],
            outline_rebuild=outline_rebuild,
        ))

    stored, _ = repository.load_document(document.course_id)
    assert storage.save_count == 0
    assert stored.document_revision == document.document_revision
    assert stored == document


def test_parent_cycle_fails_before_the_atomic_course_commit():
    document = _document()
    storage = MemoryCourseStorage(_raw_course(document))
    repository = CourseDocumentRepository(storage)
    service = CourseCommandService(repository)
    sections = [item.model_copy(deep=True) for item in document.sections]
    sections[0].parent_section_id = sections[1].section_id
    sections[1].parent_section_id = sections[0].section_id
    outline_rebuild = {
        "sections": [item.model_dump(mode="json") for item in sections],
        "section_id_map": {
            item.section_id: item.section_id for item in document.sections
        },
        "section_tombstones": [],
        "reference_migrations": [
            {
                "source_section_id": item.section_id,
                "target_section_ids": [item.section_id],
                "primary_target_section_id": item.section_id,
                "resolution": "unique",
            }
            for item in document.sections
        ],
        "operation_dag": {
            "schema_version": "course_structure_operation_dag_v1",
            "revision": "valid-empty-dag",
            "nodes": [],
            "topological_order": [],
        },
    }

    with pytest.raises(CourseDocumentConflict, match="parent cycle"):
        asyncio.run(service.apply_block_operation_group(
            document.course_id,
            command_id="invalid-parent-cycle",
            expected_document_revision=document.document_revision,
            insertions=[],
            outline_rebuild=outline_rebuild,
        ))

    stored, _ = repository.load_document(document.course_id)
    assert storage.save_count == 0
    assert stored == document


def test_outline_rebuild_with_inserted_block_can_be_atomically_undone():
    document = _document()
    storage = MemoryCourseStorage(_raw_course(document))
    repository = CourseDocumentRepository(storage)
    service = CourseCommandService(repository)
    original_sections = [
        item.model_dump(mode="json") for item in document.sections
    ]
    original_block_states = [
        {
            "block_id": item.block_id,
            "section_id": item.section_id,
            "position": item.position,
            "status": item.status,
        }
        for item in document.blocks
    ]
    outline_rebuild = {
        "sections": original_sections,
        "section_id_map": {
            item.section_id: item.section_id for item in document.sections
        },
        "section_tombstones": [],
        "reference_migrations": [
            {
                "source_section_id": item.section_id,
                "target_section_ids": [item.section_id],
                "primary_target_section_id": item.section_id,
                "resolution": "unique",
            }
            for item in document.sections
        ],
        "operation_dag": {
            "schema_version": "course_structure_operation_dag_v1",
            "revision": "identity",
            "nodes": [],
            "topological_order": [],
        },
    }
    inserted = CourseBlock(
        block_id="inserted-during-structure-change",
        section_id="lesson-1",
        position=1,
        payload={"markdown": "新增内容"},
    )

    asyncio.run(service.apply_block_operation_group(
        document.course_id,
        command_id="outline-and-insert",
        expected_document_revision=document.document_revision,
        insertions=[{
            "block": inserted,
            "after_block_id": "block-lesson-1",
        }],
        outline_rebuild=outline_rebuild,
    ))
    applied, _ = repository.load_document(document.course_id)

    asyncio.run(service.apply_block_operation_group(
        document.course_id,
        command_id="undo-outline-and-insert",
        expected_document_revision=applied.document_revision,
        insertions=[],
        retire_block_ids=[inserted.block_id],
        outline_rebuild={
            "sections": original_sections,
            "block_states": original_block_states,
        },
    ))

    restored, _ = repository.load_document(document.course_id)
    assert storage.save_count == 2
    assert restored.sections == document.sections
    assert next(
        item for item in restored.blocks if item.block_id == inserted.block_id
    ).status == "retired"
    assert {
        item.block_id: (item.section_id, item.position, item.status)
        for item in restored.blocks
        if item.block_id != inserted.block_id
    } == {
        item.block_id: (item.section_id, item.position, item.status)
        for item in document.blocks
    }
