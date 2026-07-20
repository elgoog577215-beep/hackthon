from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

import course_evolution
from block_regeneration import BlockRegenerationCandidateRepository
from course_document import document_from_legacy_course, refresh_document_revision
from course_evolution import (
    CourseEvolutionRepository,
    accept_change_set,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from course_repository import CourseDocumentRepository
from section_evolution import (
    generate_course_adjustment_plan,
    generate_section_evolution_plan,
)


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


class _CountingBlockGenerator(_SectionGenerator):
    def __init__(self) -> None:
        self.calls = 0

    async def generate_course_block_candidate(self, **_kwargs) -> str:
        self.calls += 1
        return (
            "矩阵乘法可以看成连续执行两个线性变换：输入先经过右侧变换，"
            "再经过左侧变换。沿着数据实际流动的顺序阅读，就能解释乘法顺序，"
            "而不只是记住行乘列的计算步骤。"
        )


class _WholeCourseSectionGenerator(_SectionGenerator):
    async def generate_course_block_candidate(self, **kwargs) -> str:
        section_title = str(kwargs["section"].get("title") or "当前小节")
        return (
            f"在“{section_title}”中，先用一个具体输入展示对象如何变化，"
            "再逐步解释每一步为什么成立，最后增加一个相似情境供学习者自行判断。"
        )


class _FailingSectionGenerator:
    async def generate_course_block_candidate(self, **_kwargs) -> str:
        return "太短"

    async def generate_new_course_block_candidate(self, **_kwargs) -> str:
        return "太短"


class _SemanticSectionGenerator(_SectionGenerator):
    async def analyze_section_growth_scenario(self, **_kwargs) -> dict:
        return {
            "scene_summary": "学习者已经掌握基础，希望把本节升级为能解释原理并处理真实行业决策的版本。",
            "rationale": "要求同时涉及解释决策依据和跨情境应用，因此需要升级理论推导并补充实战应用。",
            "requested_roles": ["reasoning", "application"],
            "growth_direction": "challenge",
            "difficulty_delta": {
                "reasoning_depth": 2,
                "transfer_distance": 2,
                "task_complexity": 1,
                "learner_support": -1,
            },
            "source_requirement": "verified_current_sources",
            "source_reason": "真实行业决策涉及当前事实，必须使用经过核验的时效资料。",
        }


class _BrokenSemanticSectionGenerator(_SectionGenerator):
    async def analyze_section_growth_scenario(self, **_kwargs) -> dict:
        return {
            "scene_summary": "越权选择具体内容块。",
            "requested_roles": ["unknown_role"],
            "growth_direction": "自由发挥",
            "difficulty_delta": {"reasoning_depth": 99},
            "source_requirement": "model_memory",
        }


class _FailingSemanticAnalysisGenerator(_SectionGenerator):
    async def analyze_section_growth_scenario(self, **_kwargs) -> dict:
        raise TimeoutError("scene analyzer timed out")


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


def _whole_course_growth_course() -> dict:
    course = {
        "course_id": "course-whole-growth",
        "course_name": "线性代数例子课",
        "nodes": [
            {
                "node_id": f"section-{index}",
                "parent_node_id": "root",
                "node_name": title,
                "node_level": 2,
                "learning_objective": f"理解{title}",
                "objective_id": f"objective-{index}",
                "node_content": content,
                "knowledge_structure": [{
                    "concept_group": title,
                    "knowledge_points": [{
                        "name": f"{title}知识点",
                        "statement": content,
                        "knowledge_type": "principle",
                        "capability_points": [{
                            "name": f"解释{title}",
                            "observable_behavior": f"能够解释{title}的核心关系",
                        }],
                        "mastery_criteria": [{
                            "name": f"{title}达标",
                            "observable_performance": f"能够独立说明{title}",
                            "verification_method": "完成一道新情境辨析题",
                        }],
                    }],
                }],
            }
            for index, (title, content) in enumerate([
                ("矩阵复合", "用连续变换说明矩阵复合。"),
                ("结合律", "解释复合为什么满足结合律。"),
                ("逆变换", "用撤销操作说明逆变换。"),
            ], start=1)
        ],
    }
    document = document_from_legacy_course(course)
    for block in document.blocks:
        block.role = "concept" if block.section_id == "section-2" else "example"
        block.payload["title"] = "核心概念" if block.role == "concept" else "例子讲解"
    refresh_document_revision(document)
    course.update({
        "course_document": document.model_dump(mode="json"),
        "course_schema_version": "course_document_v1",
        "course_document_revision": document.document_revision,
        "course_document_authoritative": True,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
    })
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
async def test_current_block_request_uses_course_evolution_plan_and_one_atomic_apply(
    tmp_path,
):
    course = _section_growth_course()
    storage = _MemoryCourseStorage(course)
    document_repository = CourseDocumentRepository(storage)
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    candidate_repository = BlockRegenerationCandidateRepository(tmp_path / "candidates")
    generator = _CountingBlockGenerator()
    before, _canonical = document_repository.load_document(course["course_id"])
    target = next(
        block for block in before.blocks
        if block.section_id == "section-1" and block.status != "retired"
    )

    state = await generate_course_adjustment_plan(
        course,
        user_id="student-block-adjustment",
        section_id=target.section_id,
        block_id=target.block_id,
        instruction="我不理解乘法顺序，请把这里讲得更直观",
        request_id="request-block-adjustment-1",
        expected_document_revision=before.document_revision,
        expected_block_revision=target.internal_revision,
        direction="simplify",
        scope_selection="current_block",
        repository=evolution_repository,
        document_repository=document_repository,
        candidate_repository=candidate_repository,
        generator=generator,
    )

    plan = state.change_sets[0]
    assert plan.source_kind == "manual_request"
    assert plan.scope_selection == "current_block"
    assert plan.generation_status == "ready"
    assert len(plan.operations) == 1
    operation = plan.operations[0]
    assert operation.operation_type == "REPLACE_COURSE_BLOCK"
    assert operation.target_block_id == target.block_id
    assert operation.payload["candidate_status"] == "ready"
    assert plan.impact_summary["direct_block_ids"] == [target.block_id]
    unchanged, _canonical = document_repository.load_document(course["course_id"])
    assert unchanged.document_revision == before.document_revision

    duplicate = await generate_course_adjustment_plan(
        course,
        user_id="student-block-adjustment",
        section_id=target.section_id,
        block_id=target.block_id,
        instruction="我不理解乘法顺序，请把这里讲得更直观",
        request_id="request-block-adjustment-1",
        expected_document_revision=before.document_revision,
        expected_block_revision=target.internal_revision,
        direction="simplify",
        scope_selection="current_block",
        repository=evolution_repository,
        document_repository=document_repository,
        candidate_repository=candidate_repository,
        generator=generator,
    )
    assert len(duplicate.change_sets) == 1
    assert generator.calls == 1

    applied = await asyncio.to_thread(
        accept_change_set,
        course,
        user_id="student-block-adjustment",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=[operation.operation_id],
        repository=evolution_repository,
        document_repository=document_repository,
    )
    after, _canonical = document_repository.load_document(course["course_id"])
    adjusted = next(block for block in after.blocks if block.block_id == target.block_id)
    assert adjusted.block_id == target.block_id
    assert adjusted.payload["markdown"] != target.payload["markdown"]
    assert applied.change_sets[0].status == "applied"
    assert applied.change_sets[0].application_receipt["replaced_block_ids"] == [
        target.block_id
    ]


@pytest.mark.asyncio
async def test_whole_course_request_matches_semantic_roles_and_partially_applies_reviewed_nodes(
    tmp_path,
):
    course = _whole_course_growth_course()
    storage = _MemoryCourseStorage(course)
    document_repository = CourseDocumentRepository(storage)
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    before, _canonical = document_repository.load_document(course["course_id"])
    before_by_section = {
        block.section_id: deepcopy(block.payload)
        for block in before.blocks
    }

    state = await generate_section_evolution_plan(
        course,
        user_id="student-whole-growth",
        section_id="section-1",
        instruction="这一节的例子讲得太垃圾了，以后的例子都讲得详细一点",
        request_id="request-whole-growth",
        scope_selection="whole_course",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_WholeCourseSectionGenerator(),
    )

    plan = state.change_sets[0]
    content_operations = [
        operation
        for operation in plan.operations
        if operation.operation_type == "REPLACE_COURSE_BLOCK"
    ]
    assert plan.scope_selection == "whole_course"
    assert plan.requested_roles == ["example"]
    assert [item.target_section_id for item in content_operations] == [
        "section-1",
        "section-3",
    ]
    assert plan.impact_summary["matched_block_count"] == 2
    assert plan.impact_summary["affected_section_ids"] == ["section-1", "section-3"]
    assert plan.impact_summary["target_role_labels"] == ["例子讲解"]
    assert "只升级当前课程中已存在" in plan.impact_summary["matching_policy"]
    unchanged, _canonical = document_repository.load_document(course["course_id"])
    assert unchanged.document_revision == before.document_revision

    with pytest.raises(ValueError, match="unavailable"):
        await asyncio.to_thread(
            accept_change_set,
            course,
            user_id="student-whole-growth",
            change_set_id=plan.change_set_id,
            selected_scope="current",
            selected_operation_ids=["not-a-plan-operation"],
            repository=evolution_repository,
            document_repository=document_repository,
        )

    selected_operation = content_operations[0]
    applied = await asyncio.to_thread(
        accept_change_set,
        course,
        user_id="student-whole-growth",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=[selected_operation.operation_id],
        repository=evolution_repository,
        document_repository=document_repository,
    )
    after, _canonical = document_repository.load_document(course["course_id"])
    after_by_section = {
        block.section_id: block.payload
        for block in after.blocks
    }
    assert after_by_section["section-1"] != before_by_section["section-1"]
    assert after_by_section["section-2"] == before_by_section["section-2"]
    assert after_by_section["section-3"] == before_by_section["section-3"]
    applied_plan = applied.change_sets[0]
    assert applied_plan.selected_operation_ids == [selected_operation.operation_id]
    assert applied_plan.excluded_operation_ids == [content_operations[1].operation_id]
    assert applied_plan.application_receipt["accepted_operation_ids"] == [
        selected_operation.operation_id
    ]
    assert applied_plan.application_receipt["excluded_operation_ids"] == [
        content_operations[1].operation_id
    ]


@pytest.mark.asyncio
async def test_whole_course_block_entry_keeps_current_role_when_feedback_contains_role_like_words(
    tmp_path,
):
    course = _whole_course_growth_course()
    document_repository = CourseDocumentRepository(_MemoryCourseStorage(course))
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")

    state = await generate_section_evolution_plan(
        course,
        user_id="student-block-anchor",
        section_id="section-1",
        instruction=(
            "请把这项优化要求应用到全课程同类内容，并先生成逐项影响预览。\n"
            "你的反馈：请都补充一个直观例子，帮助理解当前内容。"
        ),
        request_id="request-block-anchor",
        scope_selection="whole_course",
        anchor_role="example",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_WholeCourseSectionGenerator(),
    )

    plan = state.change_sets[0]
    content_operations = [
        operation
        for operation in plan.operations
        if operation.operation_type == "REPLACE_COURSE_BLOCK"
    ]
    assert plan.requested_roles == ["example"]
    assert [item.target_section_id for item in content_operations] == [
        "section-1",
        "section-3",
    ]
    assert plan.impact_summary["anchor_role"] == "example"
    assert (
        plan.impact_summary["scene_analysis"]["role_resolution"]
        == "current_block_anchor"
    )


@pytest.mark.asyncio
async def test_current_section_scope_is_a_hard_boundary_even_when_language_says_later(
    tmp_path,
):
    course = _whole_course_growth_course()
    document_repository = CourseDocumentRepository(_MemoryCourseStorage(course))
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")

    state = await generate_section_evolution_plan(
        course,
        user_id="student-local-growth",
        section_id="section-1",
        instruction="这一节的例子讲得太垃圾了，以后的例子都讲得详细一点",
        request_id="request-local-growth",
        scope_selection="current_section",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_WholeCourseSectionGenerator(),
    )

    plan = state.change_sets[0]
    content_operations = [
        operation
        for operation in plan.operations
        if operation.operation_type != "ADJUST_COURSE_DIFFICULTY"
    ]
    assert plan.scope_selection == "current_section"
    assert [item.target_section_id for item in content_operations] == ["section-1"]
    assert plan.impact_summary["affected_section_ids"] == ["section-1"]


@pytest.mark.asyncio
async def test_semantic_scene_analysis_guides_roles_but_system_decides_block_actions(tmp_path):
    course = _section_growth_course()
    document_repository = CourseDocumentRepository(_MemoryCourseStorage(course))
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")

    state = await generate_section_evolution_plan(
        course,
        user_id="student-semantic",
        section_id="section-1",
        instruction="我已经掌握了，想把这节换成更贴近真实行业决策的讲法",
        request_id="request-semantic",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=_SemanticSectionGenerator(),
    )

    plan = state.change_sets[0]
    scene = plan.impact_summary["scene_analysis"]
    assert scene["analysis_source"] == "ai_semantic"
    assert scene["scene_summary"].startswith("学习者已经掌握基础")
    assert scene["source_requirement"] == "verified_current_sources"
    assert scene["source_status"] == "verification_required"
    assert plan.requested_roles == ["reasoning", "application"]
    content_operations = [
        item for item in plan.operations
        if item.operation_type != "ADJUST_COURSE_DIFFICULTY"
    ]
    assert [item.payload["action"] for item in content_operations] == ["REPLACE", "INSERT"]
    assert content_operations[0].payload["desired_role"] == "reasoning"
    assert content_operations[1].payload["desired_role"] == "application"


@pytest.mark.parametrize(
    ("generator", "fallback_reason"),
    [
        (_BrokenSemanticSectionGenerator(), "analyzer_output_failed_contract"),
        (_FailingSemanticAnalysisGenerator(), "analyzer_failed"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_semantic_analysis_falls_back_without_blocking_workflow(
    tmp_path,
    generator,
    fallback_reason,
):
    course = _section_growth_course()
    document_repository = CourseDocumentRepository(_MemoryCourseStorage(course))
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")

    state = await generate_section_evolution_plan(
        course,
        user_id="student-fallback",
        section_id="section-1",
        instruction="太难了，请补充一个例子讲清楚",
        request_id="request-fallback",
        repository=evolution_repository,
        document_repository=document_repository,
        generator=generator,
    )

    plan = state.change_sets[0]
    scene = plan.impact_summary["scene_analysis"]
    assert plan.generation_status == "ready"
    assert scene["analysis_source"] == "deterministic_fallback"
    assert scene["fallback_reason"] == fallback_reason
    assert plan.growth_direction == "remediation"
    assert plan.requested_roles == ["example"]


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
