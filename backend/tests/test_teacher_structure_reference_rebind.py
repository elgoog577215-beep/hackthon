from __future__ import annotations

from copy import deepcopy

import pytest

from course_document import CourseDocument, refresh_document_revision
from course_evolution.core import (
    CourseEvolutionOperation,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
    CourseEvolutionState,
    retry_failed_domain_candidates,
)
from course_evolution.teacher_execution import (
    build_domain_candidate_applier,
    build_domain_candidate_undoer,
)
from question_bank import QuestionBankRepository, refresh_question_bank_bundle
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
)
from teaching_representations import (
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
)


NOW = "2026-09-05T00:00:00+00:00"
COURSE_ID = "course-structure-rebind"
MAPPING_REVISION = "structure-ref-test"


def _migrations() -> list[dict]:
    return [
        {
            "source_section_id": "lesson-primary",
            "target_section_ids": ["lesson-primary"],
            "primary_target_section_id": "lesson-primary",
            "resolution": "merge_primary",
        },
        {
            "source_section_id": "lesson-merged",
            "target_section_ids": ["lesson-primary"],
            "primary_target_section_id": "lesson-primary",
            "resolution": "merged",
        },
    ]


def _operation(domain: str) -> CourseEvolutionOperation:
    return CourseEvolutionOperation(
        operation_id=f"operation-{domain}",
        operation_type="APPLY_DOMAIN_CANDIDATE",
        target_block_id=MAPPING_REVISION,
        target_section_id="",
        reason="迁移结构引用",
        payload={
            "schema_version": "teacher_section_reference_rebind_v1",
            "domain": domain,
            "action": "rebind_section_references",
            "mapping_revision": MAPPING_REVISION,
            "reference_migrations": _migrations(),
            "section_tombstones": [{
                "section_id": "lesson-merged",
                "mapped_to_section_ids": ["lesson-primary"],
                "reason": "merged",
            }],
        },
    )


def _plan() -> CourseEvolutionPlan:
    operations = [
        _operation("authoring_structure_refs"),
        _operation("ppt_structure_refs"),
        _operation("question_bank_structure_refs"),
    ]
    return CourseEvolutionPlan(
        change_set_id="change-structure-rebind",
        user_id="teacher-1",
        course_id=COURSE_ID,
        hypothesis_id="hypothesis-structure-rebind",
        source_kind="manual_request",
        request_text="合并讲次",
        operations=operations,
        allowed_scopes=["current"],
        selected_scope="current",
        selected_operation_ids=[item.operation_id for item in operations],
        expected_effect="引用安全迁移",
        status="accepted",
        generation_status="ready",
        created_at=NOW,
        updated_at=NOW,
    )


def _lesson(lesson_id: str, section_id: str) -> dict:
    return {
        "lesson_unit_id": lesson_id,
        "arrangement": {
            "working_revision_id": "",
            "source_state": "current",
            "revisions": [],
        },
        "working_revision_id": f"plan-{lesson_id}",
        "source_state": "current",
        "revisions": [{
            "revision_id": f"plan-{lesson_id}",
            "plan": {
                "sections": [{
                    "node_id": section_id,
                    "body": f"{lesson_id} plan body",
                }],
            },
        }],
        "ai_candidates": [],
        "working_script_revision_id": f"script-{lesson_id}",
        "script_revisions": [{
            "revision_id": f"script-{lesson_id}",
            "sections": [{
                "section_node_id": section_id,
                "body": f"{lesson_id} script body",
            }],
        }],
        "ppt_manuscript": {},
        "ppt_assets": [],
        "imported_ppt_reviews": [],
        "material_drafts": {},
        "current_material_draft_ids": {},
    }


def _seed_authoring(repository: TeacherLessonAuthoringRepository) -> None:
    value = repository._empty(COURSE_ID)
    primary = _lesson("lesson-primary", "lesson-primary")
    merged = _lesson("lesson-merged", "lesson-merged")
    merged["ppt_assets"] = [{
        "asset_id": "asset-merged",
        "role": "primary",
        "engine": "slide_deck_v6",
        "synthetic_course_id": "ppt-synthetic-merged",
        "source_state": "current",
        "working_v6_revision_id": "binding-merged",
        "v6_revisions": [{
            "revision_id": "binding-merged",
            "section_id": "lesson-merged",
        }],
    }]
    safe = _lesson("lesson-safe", "lesson-safe")
    safe["revisions"].insert(0, {
        "revision_id": "plan-safe-history",
        "plan": {"sections": [{"node_id": "lesson-merged"}]},
    })
    value["lessons"] = {
        "lesson-primary": primary,
        "lesson-merged": merged,
        "lesson-safe": safe,
    }
    repository._save(value)


def _seed_representations(
    repository: TeachingRepresentationRepository,
) -> None:
    registry = repository.load("ppt-synthetic-merged")
    for section_id in ("lesson-merged", "lesson-safe"):
        binding = SourceBinding(
            course_id="ppt-synthetic-merged",
            section_id=section_id,
            source_revisions={f"section:{section_id}": f"revision-{section_id}"},
        )
        spec = TeachingRepresentationSpec(
            spec_id=f"spec-{section_id}",
            course_id="ppt-synthetic-merged",
            representation_type="slide_deck",
            source_bindings=[binding],
            payload={
                "slides": [{
                    "section_id": section_id,
                    "body": f"{section_id} visible body",
                }],
            },
            revision=f"spec-revision-{section_id}",
            created_at=NOW,
            updated_at=NOW,
        )
        representation = TeachingRepresentation(
            representation_id=f"representation-{section_id}",
            course_id="ppt-synthetic-merged",
            representation_type="slide_deck",
            source_bindings=[binding],
            spec_id=spec.spec_id,
            artifact_ids=[f"artifact-{section_id}"],
            revision=f"representation-revision-{section_id}",
            status="ready",
            created_at=NOW,
            updated_at=NOW,
        )
        registry.specs.append(spec)
        registry.representations.append(representation)
        repository._bind_spec(registry.derivation_graph, spec)
        repository._bind_representation(
            registry.derivation_graph,
            representation,
            dependency_kind="semantic_content",
            rebuild_policy="on_demand",
        )
    repository.save(registry)


def _seed_question_bank(repository: QuestionBankRepository) -> dict:
    bundle = refresh_question_bank_bundle({
        "schema_version": "question_bank_bundle_v1",
        "course_id": COURSE_ID,
        "items": [{
            "item_id": "question-merged",
            "revision_id": "question-merged-r1",
            "node_id": "lesson-merged",
            "node_ids": ["lesson-merged"],
            "prompt": "Preserve this prompt exactly",
            "answer_spec": {"value": "Preserve this answer"},
            "formal_task": {
                "lesson_unit_id": "lesson-merged",
                "body": "Preserve formal task body",
            },
        }, {
            "item_id": "question-safe",
            "revision_id": "question-safe-r1",
            "node_id": "lesson-safe",
            "node_ids": ["lesson-safe"],
            "prompt": "Safe prompt",
        }],
        "coverage": {},
        "assessment_blueprint": {},
        "generation_audit": {},
    })
    return repository.save_bundle(COURSE_ID, bundle)


class MemoryDocumentRepository:
    def __init__(self, bundle_revision_id: str) -> None:
        self.document = refresh_document_revision(CourseDocument(
            course_id=COURSE_ID,
            title="结构引用迁移测试",
        ))
        self.raw = {
            "course_id": COURSE_ID,
            "question_bank_bundle_revision_id": bundle_revision_id,
        }

    async def update_metadata(self, _course_id: str, updates: dict) -> dict:
        self.raw.update(deepcopy(updates))
        return deepcopy(self.raw)

    def load_raw(self, _course_id: str) -> dict:
        return deepcopy(self.raw)


def test_authoring_rebind_preserves_bodies_and_ignores_historical_only_refs(
    tmp_path,
):
    repository = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    _seed_authoring(repository)
    before = repository.load(COURSE_ID)

    record = repository.apply_structure_reference_rebind(
        COURSE_ID,
        operation_id="operation-authoring",
        mapping_revision=MAPPING_REVISION,
        reference_migrations=_migrations(),
        section_tombstones=[{
            "section_id": "lesson-merged",
            "mapped_to_section_ids": ["lesson-primary"],
            "reason": "merged",
        }],
    )
    after = repository.load(COURSE_ID)

    assert record["affected_section_ids"] == [
        "lesson-merged",
        "lesson-primary",
    ]
    assert after["lessons"]["lesson-primary"]["source_state"] == "stale"
    assert after["lessons"]["lesson-merged"]["rebuild_required"] is True
    assert after["lessons"]["lesson-safe"]["source_state"] == "current"
    assert after["lessons"]["lesson-safe"].get("rebuild_required") is None
    for lesson_id in before["lessons"]:
        assert after["lessons"][lesson_id]["revisions"] == before["lessons"][lesson_id]["revisions"]
        assert after["lessons"][lesson_id]["script_revisions"] == before["lessons"][lesson_id]["script_revisions"]

    repository.apply_structure_reference_rebind(
        COURSE_ID,
        operation_id="operation-authoring",
        mapping_revision=MAPPING_REVISION,
        reference_migrations=_migrations(),
        section_tombstones=[],
    )
    assert repository.load(COURSE_ID)["revision"] == after["revision"]

    repository.undo_structure_reference_rebind(
        COURSE_ID,
        operation_id="operation-authoring",
        expected_mapping_revision=MAPPING_REVISION,
    )
    restored = repository.load(COURSE_ID)
    assert restored["lessons"]["lesson-primary"]["source_state"] == "current"
    assert restored["lessons"]["lesson-merged"]["source_state"] == "current"
    assert restored["section_reference_tombstones"] == []


def test_representation_rebind_is_selective_and_graph_is_reversible(tmp_path):
    repository = TeachingRepresentationRepository(tmp_path / "representations")
    _seed_representations(repository)
    before = repository.load("ppt-synthetic-merged")
    safe_before = next(
        item for item in before.representations
        if item.representation_id == "representation-lesson-safe"
    ).model_dump(mode="json")

    repository.apply_structure_reference_rebind(
        "ppt-synthetic-merged",
        operation_id="operation-ppt",
        mapping_revision=MAPPING_REVISION,
        reference_migrations=_migrations(),
        section_tombstones=[{
            "section_id": "lesson-merged",
            "mapped_to_section_ids": ["lesson-primary"],
            "reason": "merged",
        }],
        affected_section_ids=["lesson-primary", "lesson-merged"],
    )
    after = repository.load("ppt-synthetic-merged")
    affected = next(
        item for item in after.representations
        if item.representation_id == "representation-lesson-merged"
    )
    safe_after = next(
        item for item in after.representations
        if item.representation_id == "representation-lesson-safe"
    )
    assert affected.status == "stale"
    assert affected.rebuild_required is True
    assert affected.source_bindings[0].section_id == "lesson-primary"
    assert "section:lesson-primary" in affected.source_revision_vector
    assert safe_after.model_dump(mode="json") == safe_before
    graph_node_ids = {item.node_id for item in after.derivation_graph.nodes}
    assert "source::section:lesson-primary" in graph_node_ids
    assert "source::section:lesson-merged" not in graph_node_ids

    repository.undo_structure_reference_rebind(
        "ppt-synthetic-merged",
        operation_id="operation-ppt",
        expected_mapping_revision=MAPPING_REVISION,
    )
    restored = repository.load("ppt-synthetic-merged")
    restored_affected = next(
        item for item in restored.representations
        if item.representation_id == "representation-lesson-merged"
    )
    assert restored_affected.status == "ready"
    assert restored_affected.rebuild_required is False
    assert restored_affected.source_bindings[0].section_id == "lesson-merged"


def test_three_structure_rebinds_reconcile_without_replay_and_undo(tmp_path):
    authoring = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    representations = TeachingRepresentationRepository(tmp_path / "representations")
    questions = QuestionBankRepository(tmp_path / "questions")
    _seed_authoring(authoring)
    _seed_representations(representations)
    original_bundle = _seed_question_bank(questions)
    document_repository = MemoryDocumentRepository(
        original_bundle["bundle_revision_id"]
    )
    evolution = CourseEvolutionRepository(tmp_path / "evolution")
    plan = _plan()
    evolution.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    applier = build_domain_candidate_applier(
        course_data={"course_id": COURSE_ID},
        user_id="teacher-1",
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        document_repository=document_repository,
        evolution_repository=evolution,
    )

    applied = applier(plan, plan.selected_operation_ids)
    assert applied["status"] == "applied"
    assert applied["applied_count"] == 3
    current_bundle = questions.load_bundle(COURSE_ID)
    assert current_bundle is not None
    assert current_bundle["bundle_revision_id"] != original_bundle["bundle_revision_id"]
    assert len(current_bundle["items"]) == len(original_bundle["items"])
    merged = next(item for item in current_bundle["items"] if item["item_id"] == "question-merged")
    assert merged["node_id"] == "lesson-primary"
    assert merged["rebuild_required"] is True
    assert merged["prompt"] == "Preserve this prompt exactly"
    assert merged["answer_spec"] == {"value": "Preserve this answer"}
    assert questions.load_bundle(
        COURSE_ID,
        original_bundle["bundle_revision_id"],
    ) == original_bundle

    authoring_revision = authoring.load(COURSE_ID)["revision"]
    registry_revision = representations.load(
        "ppt-synthetic-merged"
    ).registry_revision
    bundle_revision = current_bundle["bundle_revision_id"]
    for entry in plan.operation_journal:
        entry.status = "applying"
        entry.completed_at = None
    evolution.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    reconciled = applier(plan, plan.selected_operation_ids)
    assert reconciled["status"] == "applied"
    assert all("对账" in item["detail"] for item in reconciled["items"])
    assert authoring.load(COURSE_ID)["revision"] == authoring_revision
    assert representations.load(
        "ppt-synthetic-merged"
    ).registry_revision == registry_revision
    assert questions.load_bundle(COURSE_ID)["bundle_revision_id"] == bundle_revision

    plan.application_receipt = {"domain_candidates": deepcopy(reconciled)}
    undoer = build_domain_candidate_undoer(
        user_id="teacher-1",
        course_id=COURSE_ID,
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        document_repository=document_repository,
    )
    undone = undoer(plan)
    assert undone["status"] == "undone"
    assert questions.load_bundle(COURSE_ID)["bundle_revision_id"] == original_bundle["bundle_revision_id"]
    assert document_repository.raw["question_bank_bundle_revision_id"] == original_bundle["bundle_revision_id"]
    assert authoring.load(COURSE_ID)["lessons"]["lesson-merged"]["source_state"] == "current"
    restored_representation = next(
        item
        for item in representations.load("ppt-synthetic-merged").representations
        if item.representation_id == "representation-lesson-merged"
    )
    assert restored_representation.status == "ready"


def test_structure_rebind_partial_retry_only_runs_failed_repository(
    tmp_path,
    monkeypatch,
):
    authoring = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    representations = TeachingRepresentationRepository(tmp_path / "representations")
    questions = QuestionBankRepository(tmp_path / "questions")
    _seed_authoring(authoring)
    _seed_representations(representations)
    original_bundle = _seed_question_bank(questions)
    document_repository = MemoryDocumentRepository(
        original_bundle["bundle_revision_id"]
    )
    evolution = CourseEvolutionRepository(tmp_path / "evolution")
    plan = _plan()
    evolution.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    applier = build_domain_candidate_applier(
        course_data={"course_id": COURSE_ID},
        user_id="teacher-1",
        authoring_repository=authoring,
        representation_repository=representations,
        question_bank_repository=questions,
        document_repository=document_repository,
        evolution_repository=evolution,
    )
    original_apply = representations.apply_structure_reference_rebind
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected representation failure")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(
        representations,
        "apply_structure_reference_rebind",
        fail_once,
    )
    first = applier(plan, plan.selected_operation_ids)
    assert first["status"] == "partial"
    assert [item["domain"] for item in first["items"] if item["status"] == "failed"] == [
        "ppt_structure_refs"
    ]
    authoring_revision = authoring.load(COURSE_ID)["revision"]
    question_bank_revision = questions.load_bundle(COURSE_ID)["bundle_revision_id"]

    ppt_operation_id = next(
        item.operation_id
        for item in plan.operations
        if item.payload["domain"] == "ppt_structure_refs"
    )
    plan.status = "applied"
    plan.application_receipt = {"domain_candidates": deepcopy(first)}
    evolution.save(CourseEvolutionState(
        user_id=plan.user_id,
        course_id=plan.course_id,
        change_sets=[plan],
        updated_at=NOW,
    ))
    retried_state = retry_failed_domain_candidates(
        {"course_id": COURSE_ID},
        user_id=plan.user_id,
        change_set_id=plan.change_set_id,
        domain_candidate_applier=applier,
        selected_operation_ids=[ppt_operation_id],
        repository=evolution,
    )
    retried = retried_state.change_sets[0].application_receipt[
        "domain_candidates"
    ]

    assert retried["status"] == "applied", retried
    assert retried["applied_count"] == 3
    assert retried["last_retried_operation_ids"] == [ppt_operation_id]
    assert authoring.load(COURSE_ID)["revision"] == authoring_revision
    assert questions.load_bundle(COURSE_ID)["bundle_revision_id"] == question_bank_revision
    assert calls == 2


def test_authoring_structure_rebind_undo_cas_does_not_overwrite_later_change(
    tmp_path,
):
    repository = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    _seed_authoring(repository)
    repository.apply_structure_reference_rebind(
        COURSE_ID,
        operation_id="operation-authoring",
        mapping_revision=MAPPING_REVISION,
        reference_migrations=_migrations(),
        section_tombstones=[{
            "section_id": "lesson-merged",
            "mapped_to_section_ids": ["lesson-primary"],
            "reason": "merged",
        }],
    )
    changed = repository.load(COURSE_ID)
    changed["lessons"]["lesson-merged"]["source_state_reason"] = "later_teacher_change"
    repository._save(changed)

    with pytest.raises(
        TeacherLessonAuthoringError,
        match="已在结构迁移后变化",
    ):
        repository.undo_structure_reference_rebind(
            COURSE_ID,
            operation_id="operation-authoring",
            expected_mapping_revision=MAPPING_REVISION,
        )

    assert (
        repository.load(COURSE_ID)["lessons"]["lesson-merged"][
            "source_state_reason"
        ]
        == "later_teacher_change"
    )
