from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_commands import CourseCommandService
from course_document import document_from_legacy_course
from course_repository import CourseDocumentRepository
from course_revisions import revision_event_for_documents, revision_vector_for_document
from representation_compiler import (
    CORE_TYPES,
    compile_core_representations,
    export_slide_deck_pptx,
    validate_compiled_representations,
)
from representation_edits import (
    apply_representation_only_edit,
    classify_representation_edit,
    representation_edit_impact,
)
from teaching_representations import (
    RepresentationConflict,
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    source_binding_for_document,
)


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
        "nodes": [
            {
                "node_id": "section-a",
                "parent_node_id": "root",
                "node_name": "向量",
                "node_level": 1,
                "learning_objective": "理解向量",
                "objective_id": "objective-a",
                "node_content": "## 定义\n\n向量有大小和方向。",
            },
            {
                "node_id": "section-b",
                "parent_node_id": "root",
                "node_name": "矩阵",
                "node_level": 1,
                "learning_objective": "理解矩阵",
                "objective_id": "objective-b",
                "node_content": "## 定义\n\n矩阵是数字的矩形阵列。",
            },
        ],
    }


def representation(
    document,
    *,
    representation_id: str,
    block_id: str | None = None,
    representation_type: str = "slide_deck",
) -> TeachingRepresentation:
    now = datetime.now(timezone.utc).isoformat()
    binding = source_binding_for_document(document, block_id=block_id)
    return TeachingRepresentation(
        representation_id=representation_id,
        course_id=document.course_id,
        representation_type=representation_type,
        source_bindings=[binding],
        source_revision_vector=binding.source_revisions,
        spec_id=f"spec-{representation_id}",
        semantic_fingerprint=f"semantic-{representation_id}",
        revision=f"revision-{representation_id}",
        status="ready",
        created_at=now,
        updated_at=now,
    )


def test_revision_vector_changes_only_target_block_and_parent_section():
    before = document_from_legacy_course(legacy_course())
    after = before.model_copy(deep=True)
    after.blocks[0].payload["markdown"] = "向量同时具有大小和方向。"
    from course_document import refresh_document_revision

    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="command-1")

    assert "course_document" in event.changed_source_keys
    assert f"block:{before.blocks[0].block_id}" in event.changed_source_keys
    assert f"section:{before.blocks[0].section_id}" in event.changed_source_keys
    assert f"block:{before.blocks[1].block_id}" not in event.changed_source_keys
    assert f"section:{before.blocks[1].section_id}" not in event.changed_source_keys


def test_registry_marks_only_dependent_representation_stale(tmp_path):
    before = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path)
    first = representation(
        before,
        representation_id="slides-a",
        block_id=before.blocks[0].block_id,
    )
    second = representation(
        before,
        representation_id="slides-b",
        block_id=before.blocks[1].block_id,
    )
    repository.register_representation(first)
    repository.register_representation(second)

    after = before.model_copy(deep=True)
    after.blocks[0].payload["markdown"] = "向量同时具有大小和方向。"
    from course_document import refresh_document_revision

    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="command-1")
    updated = repository.apply_revision_event(before.course_id, event)
    states = {item.representation_id: item for item in updated.representations}

    assert states["slides-a"].status == "stale"
    assert states["slides-b"].status == "ready"
    assert any(reason.startswith("source_revision_changed:block:") for reason in states["slides-a"].stale_reasons)


def test_course_bound_representation_stales_on_any_semantic_change(tmp_path):
    before = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path)
    outline = representation(before, representation_id="outline", representation_type="outline")
    repository.register_representation(outline)

    after = before.model_copy(deep=True)
    after.blocks[1].payload["markdown"] = "矩阵表示线性映射。"
    from course_document import refresh_document_revision

    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="command-2")
    updated = repository.apply_revision_event(before.course_id, event)

    assert updated.representations[0].status == "stale"
    assert "source_revision_changed:course_document" in updated.representations[0].stale_reasons


def test_revision_event_replay_is_idempotent_and_course_isolated(tmp_path):
    before = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path)
    repository.register_representation(representation(
        before,
        representation_id="slides-a",
        block_id=before.blocks[0].block_id,
    ))
    after = before.model_copy(deep=True)
    after.blocks[0].payload["markdown"] = "变化后的内容"
    from course_document import refresh_document_revision

    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="command-3")

    first = repository.apply_revision_event(before.course_id, event)
    second = repository.apply_revision_event(before.course_id, event)
    assert second.registry_revision == first.registry_revision
    assert second.representations[0].stale_reasons == first.representations[0].stale_reasons

    with pytest.raises(RepresentationConflict):
        repository.apply_revision_event("course-2", event)


@pytest.mark.asyncio
async def test_course_command_persists_replayable_revision_event(tmp_path):
    storage = MemoryStorage(legacy_course())
    course_repository = CourseDocumentRepository(storage)
    preview = course_repository.document_envelope("course-1")
    await course_repository.migrate_legacy_course(
        "course-1",
        expected_source_checksum=preview["migration"]["source_checksum"],
    )
    document, _ = course_repository.load_document("course-1")
    target = document.blocks[0]
    representation_repository = TeachingRepresentationRepository(tmp_path)
    representation_repository.register_representation(representation(
        document,
        representation_id="slides-a",
        block_id=target.block_id,
    ))

    receipt = await CourseCommandService(course_repository).replace_block(
        "course-1",
        command_id="replace-a",
        expected_document_revision=document.document_revision,
        expected_block_revision=target.internal_revision,
        block_id=target.block_id,
        payload={"title": "定义", "markdown": "向量同时具有大小和方向。"},
    )

    assert receipt["revision_change"]["event_id"].startswith("cre_")
    assert storage.course["course_revision_vector"] == receipt["revision_change"]["current"]
    reconciled = representation_repository.reconcile_course_operation_log(
        "course-1",
        storage.course["course_operation_log"],
    )
    assert reconciled.representations[0].status == "stale"


def test_source_binding_rejects_missing_block():
    document = document_from_legacy_course(legacy_course())
    with pytest.raises(RepresentationConflict):
        source_binding_for_document(document, block_id="missing-block")


def test_representation_rejects_revision_vector_that_disagrees_with_bindings():
    now = datetime.now(timezone.utc).isoformat()
    binding = SourceBinding(course_id="course-1", source_revisions={"block:a": "revision-a"})
    with pytest.raises(ValueError):
        TeachingRepresentation(
            representation_id="slides-a",
            course_id="course-1",
            representation_type="slide_deck",
            source_bindings=[binding],
            source_revision_vector={"block:a": "different-revision"},
            spec_id="spec-a",
            revision="representation-revision-a",
            created_at=now,
            updated_at=now,
        )


def test_revision_vector_contains_document_sections_blocks_and_objectives():
    document = document_from_legacy_course(legacy_course())
    vector = revision_vector_for_document(document)

    assert vector.revisions["course_document"] == document.document_revision
    assert f"section:{document.sections[0].section_id}" in vector.revisions
    assert f"block:{document.blocks[0].block_id}" in vector.revisions
    assert "objective:objective-a" in vector.revisions


def test_representation_router_reconciles_and_returns_graph(tmp_path, monkeypatch):
    from routers import teaching_representations as representation_router

    course = legacy_course()
    storage = MemoryStorage(course)
    course_repository = CourseDocumentRepository(storage)
    document = document_from_legacy_course(course)
    representation_repository = TeachingRepresentationRepository(tmp_path)
    representation_repository.register_representation(representation(
        document,
        representation_id="slides-a",
        block_id=document.blocks[0].block_id,
    ))

    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: representation_repository,
    )
    monkeypatch.setattr(
        representation_router,
        "get_course_document_repository",
        lambda: course_repository,
    )

    async def existing_course(_course_id: str):
        return course

    monkeypatch.setattr(representation_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(representation_router.router, prefix="/api")
    client = TestClient(app)

    missing_identity = client.get("/api/courses/course-1/teaching-representations")
    assert missing_identity.status_code == 400

    response = client.get(
        "/api/courses/course-1/teaching-representations/derivation-graph",
        headers={"X-User-Id": "user-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == "course-1"
    assert payload["derivation_graph"]["nodes"]


def test_compiler_builds_five_bound_representations_and_exports_pptx(tmp_path):
    document = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path / "registry")
    course_data = legacy_course()
    course_data["learning_assets"] = {
        "questions": [{
            "question_id": "question-a",
            "revision_id": "question-revision-a",
            "node_id": "section-a",
            "prompt": "向量有哪些基本属性？",
            "practice_level": "understanding",
        }],
        "misconceptions": [{
            "node_id": "section-a",
            "error_pattern": "把方向相反的向量当成相同向量",
        }],
    }

    result = compile_core_representations(document, course_data, repository)
    registry = repository.load(document.course_id)
    current_spec_ids = {item.spec_id for item in registry.representations}
    specs = [item for item in registry.specs if item.spec_id in current_spec_ids]

    assert {item.representation_type for item in registry.representations} == set(CORE_TYPES)
    assert len(result["representations"]) == 5
    assert all(spec.unit_bindings for spec in specs)
    assert validate_compiled_representations(specs)["passed"] is True
    practice = next(spec for spec in specs if spec.representation_type == "practice_sheet")
    assert practice.payload["content"]["units"][0]["practice_task_id"] == "question-a"

    slides = next(spec for spec in specs if spec.representation_type == "slide_deck")
    output = export_slide_deck_pptx(slides, tmp_path / "course.pptx")
    assert output.exists()
    assert output.stat().st_size > 0


def test_compiled_representations_track_stale_units_instead_of_whole_course(tmp_path):
    before = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path)
    course_data = legacy_course()
    course_data["learning_assets"] = {"questions": [], "misconceptions": []}
    compile_core_representations(before, course_data, repository)

    after = before.model_copy(deep=True)
    changed_block = after.blocks[0]
    changed_block.payload["markdown"] = "向量同时具有大小、方向和线性组合语义。"
    from course_document import refresh_document_revision

    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="unit-change")
    updated = repository.apply_revision_event(before.course_id, event)
    by_type = {item.representation_type: item for item in updated.representations}

    assert by_type["slide_deck"].status == "stale"
    assert by_type["slide_deck"].stale_unit_ids == ["slide:section-a"]
    assert "slide:title" not in by_type["slide_deck"].stale_unit_ids
    assert by_type["handout"].stale_unit_ids == ["handout:section-a"]


def test_representation_edits_classify_semantic_boundary_and_preserve_course_source(tmp_path):
    document = document_from_legacy_course(legacy_course())
    repository = TeachingRepresentationRepository(tmp_path)
    compile_core_representations(
        document,
        {**legacy_course(), "learning_assets": {"questions": [], "misconceptions": []}},
        repository,
    )
    registry = repository.load(document.course_id)
    original_block_payload = deepcopy(document.blocks[0].payload)
    slides = next(item for item in registry.representations if item.representation_type == "slide_deck")
    spec = next(item for item in registry.specs if item.spec_id == slides.spec_id)

    assert classify_representation_edit(
        field="layout", before="left", after="right",
    )["classification"] == "presentation"
    assert classify_representation_edit(
        field="example", before="旧例子", after="具有不同数学含义的新例子",
    )["classification"] == "ambiguous"
    assert classify_representation_edit(
        field="example", before="旧例子", after="新例子", semantic_intent=True,
    )["classification"] == "semantic"

    impact = representation_edit_impact(registry, spec, unit_id="slide:section-a")
    assert document.blocks[0].block_id in impact["block_ids"]
    assert {item["representation_type"] for item in impact["affected_representations"]} >= {
        "outline", "lesson_plan", "handout", "slide_deck",
    }

    updated = apply_representation_only_edit(
        repository,
        registry,
        slides,
        spec,
        unit_id="slide:section-a",
        field="title",
        after="向量意味着什么",
    )
    updated_slides = next(item for item in updated.representations if item.representation_type == "slide_deck")
    updated_spec = next(item for item in updated.specs if item.spec_id == updated_slides.spec_id)
    unit = next(item for item in updated_spec.payload["content"]["slides"] if item["unit_id"] == "slide:section-a")
    assert unit["title"] == "向量意味着什么"
    assert document.blocks[0].payload == original_block_payload
