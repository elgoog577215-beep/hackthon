from __future__ import annotations

import json
from copy import deepcopy

from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_revisions import revision_event_for_documents
from representation_compiler import compile_core_representations
from teaching_representations import TeachingRepresentationRepository


def _document(*, second_block: bool = True) -> CourseDocument:
    blocks = [
        CourseBlock(
            block_id="block-definition",
            section_id="section-matrix",
            position=0,
            role="concept",
            payload={"title": "定义", "markdown": "矩阵表示按行列排列的数。"},
            concept_refs=["knowledge.matrix.definition"],
        ),
    ]
    if second_block:
        blocks.append(CourseBlock(
            block_id="block-example",
            section_id="section-matrix",
            position=1,
            role="example",
            payload={"title": "例子", "markdown": "二阶矩阵可以描述平面线性变换。"},
            concept_refs=["knowledge.matrix.example"],
        ))
    return refresh_document_revision(CourseDocument(
        course_id="course-handout-units",
        title="矩阵与线性变换",
        sections=[CourseSection(
            section_id="section-matrix",
            title="矩阵",
            position=0,
            learning_objective="能够解释矩阵的结构与线性变换含义",
            objective_id="objective-matrix",
        )],
        blocks=blocks,
    ))


def _course_data() -> dict:
    return {
        "course_id": "course-handout-units",
        "course_name": "矩阵与线性变换",
        "nodes": [{
            "node_id": "section-matrix",
            "parent_node_id": "root",
            "node_name": "矩阵",
            "node_level": 1,
            "learning_objective": "能够解释矩阵的结构与线性变换含义",
            "objective_id": "objective-matrix",
            "node_content": "矩阵表示按行列排列的数。",
        }],
        "learning_assets": {"questions": [], "misconceptions": []},
    }


def _active_handout(repository: TeachingRepresentationRepository, course_id: str):
    registry = repository.load(course_id)
    representation = next(
        item for item in registry.representations
        if item.representation_type == "handout"
    )
    spec = next(item for item in registry.specs if item.spec_id == representation.spec_id)
    return representation, spec


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_single_block_handout_keeps_legacy_section_unit_id(tmp_path):
    document = _document(second_block=False)
    repository = TeachingRepresentationRepository(tmp_path)

    compile_core_representations(document, _course_data(), repository)
    _, spec = _active_handout(repository, document.course_id)

    assert [unit["unit_id"] for unit in spec.payload["content"]["units"]] == [
        "handout:section-matrix",
    ]
    binding = next(
        item for item in spec.unit_bindings["handout:section-matrix"]
        if item.block_id == "block-definition"
    )
    assert binding.section_id == "section-matrix"
    assert set(binding.source_revisions) == {"block:block-definition"}


def test_handout_rebuild_reuses_unchanged_sibling_block_unit(tmp_path):
    before = _document()
    repository = TeachingRepresentationRepository(tmp_path)
    first_build = compile_core_representations(before, _course_data(), repository)
    assert first_build["representations"]
    _, before_spec = _active_handout(repository, before.course_id)
    before_units = {
        item["unit_id"]: deepcopy(item)
        for item in before_spec.payload["content"]["units"]
    }
    definition_id = "handout:section-matrix:block:block-definition"
    example_id = "handout:section-matrix:block:block-example"
    assert set(before_units) == {definition_id, example_id}

    after = before.model_copy(deep=True)
    target = next(item for item in after.blocks if item.block_id == "block-example")
    target.payload["markdown"] = "二阶矩阵能够表示旋转、缩放与剪切。"
    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="edit-example")
    stale_registry = repository.apply_revision_event(before.course_id, event)
    stale_handout = next(
        item for item in stale_registry.representations
        if item.representation_type == "handout"
    )
    assert stale_handout.stale_unit_ids == [example_id]

    result = compile_core_representations(after, _course_data(), repository)
    handout_build = next(
        item for item in result["representations"]
        if item["representation_type"] == "handout"
    )
    assert handout_build["rebuilt_unit_ids"] == [example_id]
    assert handout_build["reused_unit_ids"] == [definition_id]

    _, after_spec = _active_handout(repository, after.course_id)
    after_units = {
        item["unit_id"]: item
        for item in after_spec.payload["content"]["units"]
    }
    assert _canonical_bytes(after_units[definition_id]) == _canonical_bytes(
        before_units[definition_id],
    )
    assert after_units[definition_id] == before_units[definition_id]
    assert after_units[example_id] != before_units[example_id]
    assert after_units[example_id]["blocks"][0]["markdown"] == (
        "二阶矩阵能够表示旋转、缩放与剪切。"
    )

    changed_binding = next(
        item for item in after_spec.unit_bindings[example_id]
        if item.block_id == "block-example"
    )
    sibling_binding = next(
        item for item in after_spec.unit_bindings[definition_id]
        if item.block_id == "block-definition"
    )
    assert changed_binding.section_id == sibling_binding.section_id == "section-matrix"
    assert set(changed_binding.source_revisions) == {"block:block-example"}
    assert set(sibling_binding.source_revisions) == {"block:block-definition"}
    assert changed_binding.source_revisions["block:block-example"] == target.internal_revision


def test_added_block_migrates_legacy_section_unit_id_to_block_scoped_ids(tmp_path):
    """Single-block section grows to two blocks: unit ids migrate, text survives."""
    before = _document(second_block=False)
    repository = TeachingRepresentationRepository(tmp_path)
    compile_core_representations(before, _course_data(), repository)
    _, before_spec = _active_handout(repository, before.course_id)
    legacy_id = "handout:section-matrix"
    definition_id = "handout:section-matrix:block:block-definition"
    example_id = "handout:section-matrix:block:block-example"
    assert [item["unit_id"] for item in before_spec.payload["content"]["units"]] == [legacy_id]
    legacy_unit = deepcopy(before_spec.payload["content"]["units"][0])

    after = before.model_copy(deep=True)
    after.blocks.append(CourseBlock(
        block_id="block-example",
        section_id="section-matrix",
        position=1,
        role="example",
        payload={"title": "例子", "markdown": "二阶矩阵可以描述平面线性变换。"},
        concept_refs=["knowledge.matrix.example"],
    ))
    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="add-example")
    repository.apply_revision_event(before.course_id, event)

    result = compile_core_representations(after, _course_data(), repository)
    handout_build = next(
        item for item in result["representations"]
        if item["representation_type"] == "handout"
    )
    _, after_spec = _active_handout(repository, after.course_id)
    after_units = {
        item["unit_id"]: item
        for item in after_spec.payload["content"]["units"]
    }

    assert set(after_units) == {definition_id, example_id}
    assert legacy_id not in after_units
    assert legacy_id not in after_spec.unit_bindings
    # A brand-new block has no prior binding, so the revision event marks
    # nothing stale and the section takes the full-rebuild path. The retired
    # legacy identifier must not leak into either incremental report.
    assert handout_build["unit_count"] == 2
    assert legacy_id not in handout_build["rebuilt_unit_ids"]
    assert legacy_id not in handout_build["reused_unit_ids"]
    # The unchanged paragraph text survives the identifier migration.
    assert after_units[definition_id]["blocks"] == legacy_unit["blocks"]
    assert set(after_spec.unit_bindings[definition_id][0].source_revisions) == {
        "block:block-definition",
    }


def test_retired_block_collapses_section_back_to_legacy_unit_id(tmp_path):
    """Retiring one of two blocks drops its unit and restores the legacy id."""
    before = _document()
    repository = TeachingRepresentationRepository(tmp_path)
    compile_core_representations(before, _course_data(), repository)
    _, before_spec = _active_handout(repository, before.course_id)
    definition_id = "handout:section-matrix:block:block-definition"
    example_id = "handout:section-matrix:block:block-example"
    assert set(before_spec.unit_bindings) >= {definition_id, example_id}
    before_definition = deepcopy(next(
        item for item in before_spec.payload["content"]["units"]
        if item["unit_id"] == definition_id
    ))

    after = before.model_copy(deep=True)
    retired = next(item for item in after.blocks if item.block_id == "block-example")
    retired.status = "retired"
    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="retire-example")
    repository.apply_revision_event(before.course_id, event)

    compile_core_representations(after, _course_data(), repository)
    _, after_spec = _active_handout(repository, after.course_id)
    after_units = {
        item["unit_id"]: item
        for item in after_spec.payload["content"]["units"]
    }

    assert set(after_units) == {"handout:section-matrix"}
    assert example_id not in after_units
    assert example_id not in after_spec.unit_bindings
    assert definition_id not in after_spec.unit_bindings
    assert after_units["handout:section-matrix"]["blocks"] == before_definition["blocks"]
    assert after_units["handout:section-matrix"]["block_id"] == "block-definition"


def test_reordered_blocks_keep_stable_unit_ids_and_content(tmp_path):
    """Reordering must move units, not rewrite their identity or text."""
    before = _document()
    repository = TeachingRepresentationRepository(tmp_path)
    compile_core_representations(before, _course_data(), repository)
    _, before_spec = _active_handout(repository, before.course_id)
    definition_id = "handout:section-matrix:block:block-definition"
    example_id = "handout:section-matrix:block:block-example"
    before_units = {
        item["unit_id"]: deepcopy(item)
        for item in before_spec.payload["content"]["units"]
    }
    assert [item["unit_id"] for item in before_spec.payload["content"]["units"]] == [
        definition_id,
        example_id,
    ]

    after = before.model_copy(deep=True)
    for block in after.blocks:
        block.position = 0 if block.block_id == "block-example" else 1
    refresh_document_revision(after)
    event = revision_event_for_documents(before, after, command_id="reorder-blocks")
    repository.apply_revision_event(before.course_id, event)

    compile_core_representations(after, _course_data(), repository)
    _, after_spec = _active_handout(repository, after.course_id)

    assert [item["unit_id"] for item in after_spec.payload["content"]["units"]] == [
        example_id,
        definition_id,
    ]
    after_units = {
        item["unit_id"]: item
        for item in after_spec.payload["content"]["units"]
    }
    # Identity is block-derived, so reordering never rewrites unit text.
    for unit_id in (definition_id, example_id):
        assert after_units[unit_id]["blocks"] == before_units[unit_id]["blocks"]
        assert _canonical_bytes(after_units[unit_id]["blocks"]) == _canonical_bytes(
            before_units[unit_id]["blocks"],
        )
