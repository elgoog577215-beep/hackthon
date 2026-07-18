from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

import course_evolution
from course_document import document_from_legacy_course, refresh_document_revision
from course_evolution import (
    CourseEvolutionRepository,
    accept_change_set,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from course_repository import CourseDocumentRepository
from section_evolution import generate_section_evolution_plan


class _MemoryCourseStorage:
    def __init__(self, course: dict) -> None:
        self.courses = {str(course["course_id"]): deepcopy(course)}

    def load_course(self, course_id: str) -> dict | None:
        value = self.courses.get(course_id)
        return deepcopy(value) if value else None

    async def save_course(self, course_id: str, course: dict) -> None:
        self.courses[course_id] = deepcopy(course)


def _course_with_knowledge() -> dict:
    course = {
        "course_id": "course-section-growth",
        "course_name": "线性代数",
        "nodes": [{
            "node_id": "section-1",
            "parent_node_id": "root",
            "node_name": "矩阵复合",
            "node_level": 2,
            "learning_objective": "解释矩阵复合的顺序并迁移到实际任务",
            "objective_id": "objective-1",
            "node_content": "矩阵乘法表示线性变换的复合。",
            "knowledge_structure": [{
                "concept_group": "矩阵语义",
                "knowledge_points": [{
                    "name": "矩阵复合含义",
                    "statement": "矩阵乘法表达线性变换的复合。",
                    "knowledge_type": "principle",
                    "conditions": ["两个线性变换的定义域和值域可衔接"],
                    "capability_points": [{
                        "name": "解释复合顺序",
                        "observable_behavior": "能够解释矩阵乘法顺序与变换复合的关系",
                    }],
                    "mastery_criteria": [{
                        "name": "复合语义达标",
                        "observable_performance": "不依赖公式解释两个变换的复合顺序",
                        "verification_method": "完成一道变换顺序辨析题",
                    }],
                }],
            }],
        }],
    }
    document = document_from_legacy_course(course)
    course.update({
        "course_document": document.model_dump(mode="json"),
        "course_schema_version": "course_document_v1",
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
    })
    return course


class _SectionGenerator:
    async def generate_course_block_candidate(self, **_kwargs) -> str:
        return (
            "设线性变换先作用于输入，再由第二个变换作用于中间结果。"
            "因此复合顺序必须从最靠近输入的一侧读起，最后再写成矩阵乘积。"
        )

    async def generate_new_course_block_candidate(self, **_kwargs) -> str:
        return (
            "在图形处理流水线中，先缩放再旋转与先旋转再缩放会得到不同结果。"
            "请先判断操作顺序，再用矩阵复合验证，并说明结果为何不同。"
        )


class _FailingSectionGenerator:
    async def generate_course_block_candidate(self, **_kwargs) -> str:
        return "太短"

    async def generate_new_course_block_candidate(self, **_kwargs) -> str:
        return "太短"


def _section_growth_course() -> dict:
    course = _course_with_knowledge()
    document = course_evolution._course_document(course)
    target = next(block for block in document.blocks if block.section_id == "section-1")
    target.role = "reasoning"
    target.payload["title"] = "理论推导"
    refresh_document_revision(document)
    course["course_document"] = document.model_dump(mode="json")
    course["course_document_revision"] = document.document_revision
    course["current_course_version_id"] = document.document_revision
    return course


@pytest.mark.asyncio
async def test_section_request_upgrades_existing_role_and_inserts_missing_role_atomically(tmp_path):
    course = _section_growth_course()
    storage = _MemoryCourseStorage(course)
    document_repository = CourseDocumentRepository(storage)
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    before, _canonical = document_repository.load_document(course["course_id"])
    reasoning_before = next(
        block for block in before.blocks
        if block.section_id == "section-1" and block.role == "reasoning"
    )

    state = await generate_section_evolution_plan(
        course,
        user_id="student-growth",
        section_id="section-1",
        instruction="太简单了，强化理论推导与实战讲解",
        request_id="request-growth-1",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_SectionGenerator(),
    )

    plan = state.change_sets[0]
    assert plan.generation_status == "ready"
    assert plan.growth_direction == "challenge"
    assert plan.requested_roles == ["reasoning", "application"]
    operations = {
        item.operation_type: item
        for item in plan.operations
        if item.operation_type != "ADJUST_COURSE_DIFFICULTY"
    }
    assert set(operations) == {"REPLACE_COURSE_BLOCK", "INSERT_COURSE_BLOCK"}
    assert operations["REPLACE_COURSE_BLOCK"].target_block_id == reasoning_before.block_id
    assert operations["REPLACE_COURSE_BLOCK"].payload["candidate_status"] == "ready"
    assert operations["INSERT_COURSE_BLOCK"].payload["candidate_status"] == "ready"
    assert plan.impact_summary["quality_report"]["passed"] is True
    # Candidate generation is a checkpointed workspace; the formal document is
    # untouched until the learner confirms the whole group.
    unchanged, _canonical = document_repository.load_document(course["course_id"])
    assert unchanged.document_revision == before.document_revision

    applied = await asyncio.to_thread(
        accept_change_set,
        course,
        user_id="student-growth",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        repository=evolution_repository,
        document_repository=document_repository,
    )
    after, _canonical = document_repository.load_document(course["course_id"])
    reasoning_after = next(
        block for block in after.blocks if block.block_id == reasoning_before.block_id
    )
    application = next(
        block for block in after.blocks
        if block.section_id == "section-1" and block.role == "application"
    )
    assert reasoning_after.block_id == reasoning_before.block_id
    assert reasoning_after.payload["markdown"] != reasoning_before.payload["markdown"]
    assert application.concept_refs
    assert set(reasoning_after.concept_refs) == set(application.concept_refs)
    assert len(after.blocks) == len(before.blocks) + 1
    assert len(after.model_dump()["blocks"]) == len({
        block["block_id"] for block in after.model_dump()["blocks"]
    })
    assert applied.change_sets[0].application_receipt["inserted_block_ids"] == [application.block_id]

    undone = await asyncio.to_thread(
        undo_change_set,
        user_id="student-growth",
        course_id=course["course_id"],
        change_set_id=plan.change_set_id,
        repository=evolution_repository,
        document_repository=document_repository,
    )
    restored, _canonical = document_repository.load_document(course["course_id"])
    reasoning_restored = next(
        block for block in restored.blocks if block.block_id == reasoning_before.block_id
    )
    inserted_restored = next(
        block for block in restored.blocks if block.block_id == application.block_id
    )
    assert reasoning_restored.payload == reasoning_before.payload
    assert inserted_restored.status == "retired"
    assert undone.change_sets[0].status == "undone"


@pytest.mark.asyncio
async def test_failed_section_candidate_keeps_formal_course_unchanged_and_checkpoint(tmp_path):
    course = _section_growth_course()
    document_repository = CourseDocumentRepository(_MemoryCourseStorage(course))
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    before, _canonical = document_repository.load_document(course["course_id"])

    with pytest.raises(ValueError, match="候选未通过质量检查"):
        await generate_section_evolution_plan(
            course,
            user_id="student-growth",
            section_id="section-1",
            instruction="强化理论推导与实战讲解",
            request_id="request-growth-failed",
            repository=evolution_repository,
            document_repository=document_repository,
            generator=_FailingSectionGenerator(),
        )

    state = evolution_repository.load("student-growth", course["course_id"])
    plan = state.change_sets[0]
    assert plan.generation_status == "failed"
    failed_operation = next(
        item for item in plan.operations
        if item.operation_type == "REPLACE_COURSE_BLOCK"
    )
    assert failed_operation.payload["candidate_status"] == "quality_failed"
    assert len(failed_operation.payload["quality_report"]["issues"]) >= 1
    after, _canonical = document_repository.load_document(course["course_id"])
    assert after.document_revision == before.document_revision


def test_repeated_formal_success_creates_challenge_suggestion_without_deficit(tmp_path, monkeypatch):
    course = _section_growth_course()
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [
        {
            "attempt_id": "success-1",
            "status": "graded",
            "node_id": "section-1",
            "result": {"passed": True, "grading_confidence": 0.92},
            "graded_at": "2026-07-18T09:00:00+00:00",
        },
        {
            "attempt_id": "success-2",
            "status": "graded",
            "node_id": "section-1",
            "result": {"passed": True, "grading_confidence": 0.95},
            "graded_at": "2026-07-18T09:10:00+00:00",
        },
    ])
    monkeypatch.setattr(
        course_evolution.learning_asset_repository,
        "load_bundle",
        lambda _course_id: None,
    )

    state = synchronize_and_evaluate_course_evolution(
        deepcopy(course),
        user_id="student-ready",
        repository=CourseEvolutionRepository(tmp_path / "evolution"),
    )

    assert all(item.is_counterevidence for item in state.evidence_items)
    assert not any(item.problem_type == "conceptual_gap" for item in state.hypotheses)
    readiness = next(
        item for item in state.hypotheses
        if item.problem_type == "challenge_readiness"
    )
    suggestion = next(
        item for item in state.change_sets
        if item.hypothesis_id == readiness.hypothesis_id
    )
    assert suggestion.generation_status == "suggested"
    assert suggestion.growth_direction == "challenge"
    assert suggestion.requested_roles == ["reasoning", "application"]
    assert suggestion.impact_summary["mastery_transition"] == {
        "previous_status": "mastered_at_base_difficulty",
        "current_status": "ready_for_higher_challenge",
    }


@pytest.mark.asyncio
async def test_challenge_growth_uses_harder_task_results_without_erasing_base_mastery(
    tmp_path,
    monkeypatch,
):
    course = _section_growth_course()
    storage = _MemoryCourseStorage(course)
    document_repository = CourseDocumentRepository(storage)
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    state = await generate_section_evolution_plan(
        course,
        user_id="student-challenge-effect",
        section_id="section-1",
        instruction="太简单了，强化理论推导与实战讲解",
        request_id="request-challenge-effect",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_SectionGenerator(),
    )
    plan = state.change_sets[0]
    await asyncio.to_thread(
        accept_change_set,
        course,
        user_id="student-challenge-effect",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        repository=evolution_repository,
        document_repository=document_repository,
    )

    attempts = [{
        "attempt_id": "harder-task-passed",
        "status": "graded",
        "node_id": "section-1",
        "task_revision_id": "challenge-task-1",
        "result": {"passed": True, "score": 92, "grading_confidence": 0.96},
        "graded_at": "2099-01-01T00:00:00+00:00",
    }]
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(
        course_evolution.practice_attempt_repository,
        "list",
        lambda *_args: deepcopy(attempts),
    )
    monkeypatch.setattr(
        course_evolution.learning_asset_repository,
        "load_bundle",
        lambda _course_id: None,
    )

    evaluated = synchronize_and_evaluate_course_evolution(
        storage.load_course(course["course_id"]),
        user_id="student-challenge-effect",
        repository=evolution_repository,
    )
    applied = next(
        item for item in evaluated.change_sets
        if item.change_set_id == plan.change_set_id
    )
    assert applied.effect_evaluation["status"] == "effective"
    assert applied.effect_evaluation["verification_level"] == "initial_support"
    assert applied.effect_evaluation["mastery_transition"] == {
        "base_difficulty": "mastered_preserved",
        "higher_challenge": "validated",
    }
    assert applied.effect_evaluation["interaction_event_ids"] == []
    assert "旧难度掌握继续保留" in (
        applied.effect_evaluation["verification_summary"]["interpretation"]
    )
