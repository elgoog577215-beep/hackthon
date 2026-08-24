from __future__ import annotations

import pytest
from pydantic import ValidationError

from course_change_planning import (
    CourseChangeIntent,
    CourseChangePlan,
    CourseChangeSignal,
    CourseStructureOperation,
    CourseUnitMigration,
    ProposedOutlineNode,
    course_change_scenario_matrix,
    derive_execution_strategies,
    replan_course_change,
    summarize_course_change_plan,
    validate_course_change_plan,
)
from course_evolution import CourseEvolutionPlan

NOW = "2026-08-25T10:00:00+00:00"


def _intent(*, signals: list[CourseChangeSignal] | None = None) -> CourseChangeIntent:
    return CourseChangeIntent(
        intent_id="intent-1",
        course_id="course-1",
        raw_request="我觉得第三章太散了，重新整理一下，但原来的项目案例要保留。",
        interpreted_goal="重整第三章的教学结构，同时保留原项目案例。",
        protected_requirements=["保留原项目案例"],
        signals=signals or [],
    )


def _split_operation() -> CourseStructureOperation:
    return CourseStructureOperation(
        operation_id="operation-split-1",
        operation_type="SPLIT_OUTLINE_NODE",
        base_blueprint_revision_id="blueprint-1",
        idempotency_key="split-chapter-3",
        source_node_ids=["chapter-3"],
        proposed_nodes=[
            ProposedOutlineNode(
                provisional_id="new-chapter-3a",
                title="基础原理",
                source_node_ids=["chapter-3"],
            ),
            ProposedOutlineNode(
                provisional_id="new-chapter-3b",
                title="项目实践",
                source_node_ids=["chapter-3"],
            ),
        ],
        reason="原章节同时承担原理与实践，拆分后教学目标更清楚。",
    )


def _regeneration_migration(**overrides: object) -> CourseUnitMigration:
    payload = {
        "migration_id": "migration-script-1",
        "asset_type": "teacher_script",
        "unit_type": "script_block",
        "source_unit_ids": ["script-old-1"],
        "target_unit_ids": ["script-new-1"],
        "disposition": "regenerate",
        "reason": "拆分后的讲次目标和叙事顺序已经改变。",
        "candidate_status": "not_started",
    }
    payload.update(overrides)
    return CourseUnitMigration(**payload)


def test_scenario_matrix_is_coverage_guidance_not_a_teacher_input_gate() -> None:
    matrix = course_change_scenario_matrix()
    scenario_ids = {item.scenario_id for item in matrix.scenarios}

    assert {
        "exact_reference_update",
        "teaching_goal_or_strategy",
        "rename_move_reorder",
        "insert_or_retire",
        "split_or_merge",
        "whole_course_restructure",
        "ambiguous_or_evolving_request",
    }.issubset(scenario_ids)
    assert all(item.advisory_only for item in matrix.scenarios)
    assert "open-ended" in matrix.routing_principle


def test_raw_language_does_not_force_a_structure_route_without_evidence() -> None:
    # The sentence contains "重新整理", but routing deliberately does not parse
    # keywords.  The interpreter may add a structure signal after inspecting the
    # course; until then the semantic discovery route remains provisional.
    strategies, status = derive_execution_strategies(_intent())

    assert strategies == ["semantic_impact"]
    assert status == "provisional"


def test_structural_evidence_routes_structure_before_semantic_analysis() -> None:
    intent = _intent(signals=[
        CourseChangeSignal(
            signal_id="signal-1",
            kind="mixed",
            evidence="第三章需要拆成原理与项目实践两个教学单元。",
            confidence=0.92,
        ),
    ])

    plan = CourseChangePlan(
        plan_id="plan-1",
        course_id="course-1",
        intent=intent,
        base_revision_vector={"blueprint": "blueprint-1"},
        structural_operations=[_split_operation()],
        created_at=NOW,
        updated_at=NOW,
    )

    assert plan.execution_strategies == ["structural_regeneration", "semantic_impact"]
    assert plan.strategy_status == "resolved"
    assert plan.structure_review_status == "pending"


def test_structure_preview_can_run_before_downstream_generation_checkpoint() -> None:
    plan = CourseChangePlan(
        plan_id="plan-1",
        course_id="course-1",
        intent=_intent(signals=[
            CourseChangeSignal(
                signal_id="signal-structure",
                kind="structural",
                evidence="需要拆分章节。",
                confidence=0.9,
            ),
        ]),
        base_revision_vector={"blueprint": "blueprint-1"},
        structural_operations=[_split_operation()],
        created_at=NOW,
        updated_at=NOW,
    )

    preview = validate_course_change_plan(plan, phase="impact_preview")
    generation = validate_course_change_plan(plan, phase="downstream_generation")

    assert preview.passed is True
    assert generation.passed is False
    assert "teacher confirmation" in " ".join(generation.errors)

    confirmed = plan.model_copy(update={"structure_review_status": "confirmed"})
    assert validate_course_change_plan(
        confirmed,
        phase="downstream_generation",
    ).passed is True


def test_replan_preserves_teacher_language_and_can_expand_to_mixed_execution() -> None:
    original = CourseChangePlan(
        plan_id="plan-1",
        course_id="course-1",
        intent=_intent(),
        base_revision_vector={"blueprint": "blueprint-1"},
        unit_migrations=[CourseUnitMigration(
            migration_id="migration-1",
            asset_type="lesson_plan",
            unit_type="lesson_module",
            source_unit_ids=["module-1"],
            target_unit_ids=["module-1"],
            disposition="rewrite_partial",
            reason="先根据当前理解整理本章表达。",
        )],
        created_at=NOW,
        updated_at=NOW,
    )
    expanded_intent = original.intent.model_copy(update={
        "signals": [
            CourseChangeSignal(
                signal_id="signal-mixed",
                kind="mixed",
                evidence="影响扫描发现目标和章节边界都需要变化。",
                confidence=0.86,
            ),
        ],
        "interpretation_revision": "intent-2",
    })

    replanned = replan_course_change(
        original,
        new_plan_id="plan-2",
        reason="影响扫描发现结构信号，扩大为混合执行。",
        intent=expanded_intent,
        structural_operations=[_split_operation()],
        updated_at="2026-08-25T10:05:00+00:00",
    )

    assert replanned.intent.raw_request == original.intent.raw_request
    assert replanned.supersedes_plan_id == "plan-1"
    assert replanned.execution_strategies == [
        "structural_regeneration",
        "semantic_impact",
    ]
    assert replanned.structure_review_status == "pending"


def test_protected_content_cannot_be_regenerated_silently() -> None:
    plan = CourseChangePlan(
        plan_id="plan-protected",
        course_id="course-1",
        intent=_intent(signals=[
            CourseChangeSignal(
                signal_id="signal-semantic",
                kind="semantic",
                evidence="讲稿需要适配新目标。",
            ),
        ]),
        base_revision_vector={"script": "script-1"},
        unit_migrations=[_regeneration_migration(
            protected_by=["保留原项目案例"],
        )],
        created_at=NOW,
        updated_at=NOW,
    )

    validation = validate_course_change_plan(plan, phase="impact_preview")

    assert validation.passed is False
    assert "protected content" in " ".join(validation.errors)


def test_publish_requires_ready_candidates_and_no_blocked_migrations() -> None:
    plan = CourseChangePlan(
        plan_id="plan-publish",
        course_id="course-1",
        intent=_intent(signals=[
            CourseChangeSignal(
                signal_id="signal-semantic",
                kind="semantic",
                evidence="新目标要求重写讲稿。",
            ),
        ]),
        base_revision_vector={"script": "script-1"},
        unit_migrations=[
            _regeneration_migration(candidate_status="ready"),
            CourseUnitMigration(
                migration_id="migration-question-1",
                asset_type="question_bank",
                unit_type="question",
                source_unit_ids=["question-1"],
                disposition="blocked",
                reason="拆分后题目同时覆盖两个新章节，归属无法自动确定。",
            ),
        ],
        created_at=NOW,
        updated_at=NOW,
    )

    validation = validate_course_change_plan(plan, phase="publish")

    assert validation.passed is False
    assert validation.review_migration_ids == ["migration-question-1"]
    assert "still blocked" in " ".join(validation.errors)


def test_split_merge_and_retire_use_explicit_non_destructive_shapes() -> None:
    with pytest.raises(ValidationError, match="Split requires"):
        CourseStructureOperation(
            operation_id="bad-split",
            operation_type="SPLIT_OUTLINE_NODE",
            base_blueprint_revision_id="blueprint-1",
            idempotency_key="bad-split",
            source_node_ids=["chapter-3"],
            proposed_nodes=[ProposedOutlineNode(
                provisional_id="only-one",
                title="Only one",
            )],
            reason="invalid split",
        )

    retire = CourseStructureOperation(
        operation_id="retire-1",
        operation_type="RETIRE_OUTLINE_NODE",
        base_blueprint_revision_id="blueprint-1",
        idempotency_key="retire-chapter-4",
        source_node_ids=["chapter-4"],
        reason="章节已过时，但必须保留墓碑和历史引用。",
    )

    assert retire.operation_type == "RETIRE_OUTLINE_NODE"
    assert "DELETE_OUTLINE_NODE" not in retire.model_dump_json()


def test_blocking_questions_keep_imprecise_request_out_of_execution() -> None:
    intent = CourseChangeIntent(
        intent_id="intent-blocked",
        course_id="course-1",
        raw_request="把后半部分改好一点。",
        interpreted_goal="后半部分需要调整，但目标和保护范围仍不明确。",
        blocking_questions=["后半部分是指哪些章节？"],
        can_proceed_without_clarification=False,
    )
    plan = CourseChangePlan(
        plan_id="plan-blocked",
        course_id="course-1",
        intent=intent,
        base_revision_vector={"blueprint": "blueprint-1"},
        unit_migrations=[CourseUnitMigration(
            migration_id="migration-blocked",
            asset_type="outline",
            unit_type="chapter",
            source_unit_ids=["chapter-4"],
            disposition="blocked",
            reason="老师指代的范围还不能从当前课程可靠确定。",
        )],
        status="needs_clarification",
        created_at=NOW,
        updated_at=NOW,
    )

    validation = validate_course_change_plan(plan, phase="impact_preview")

    assert validation.passed is False
    assert "blocking questions" in " ".join(validation.errors)


def test_teacher_planning_is_embedded_in_existing_course_evolution_plan() -> None:
    teacher_plan = CourseChangePlan(
        plan_id="teacher-plan-1",
        course_id="course-1",
        intent=_intent(signals=[
            CourseChangeSignal(
                signal_id="signal-semantic",
                kind="semantic",
                evidence="需要更新多个正式资产。",
            ),
        ]),
        base_revision_vector={"course": "revision-1"},
        unit_migrations=[CourseUnitMigration(
            migration_id="migration-embedded",
            asset_type="outline",
            unit_type="section",
            source_unit_ids=["section-1"],
            target_unit_ids=["section-1"],
            disposition="rewrite_partial",
            reason="更新目标表述但保持稳定身份。",
        )],
        created_at=NOW,
        updated_at=NOW,
    )
    evolution_plan = CourseEvolutionPlan(
        change_set_id="change-set-1",
        user_id="teacher-1",
        course_id="course-1",
        hypothesis_id="teacher-request-1",
        source_kind="manual_request",
        request_text=teacher_plan.intent.raw_request,
        growth_direction="author_directed",
        base_revision_vector={"course": "revision-1"},
        teacher_change_planning=teacher_plan,
        expected_effect="按老师要求形成全课一致修改候选。",
        created_at=NOW,
        updated_at=NOW,
    )

    payload = evolution_plan.model_dump(mode="json")

    assert payload["teacher_change_planning"]["plan_id"] == "teacher-plan-1"
    assert payload["teacher_change_planning"]["intent"]["raw_request"] == (
        teacher_plan.intent.raw_request
    )


def test_whole_restructure_can_mix_reuse_rewrite_regeneration_and_retirement() -> None:
    operation = CourseStructureOperation(
        operation_id="rebuild-outline-1",
        operation_type="REBUILD_OUTLINE",
        base_blueprint_revision_id="blueprint-1",
        idempotency_key="rebuild-by-projects",
        source_node_ids=["chapter-1", "chapter-2", "chapter-3"],
        proposed_nodes=[
            ProposedOutlineNode(
                provisional_id="project-1",
                title="项目一：模型选型",
                source_node_ids=["chapter-1", "chapter-2"],
            ),
            ProposedOutlineNode(
                provisional_id="project-2",
                title="项目二：应用交付",
                source_node_ids=["chapter-2", "chapter-3"],
            ),
        ],
        reason="课程从知识章节改为项目任务组织。",
    )
    migrations = [
        CourseUnitMigration(
            migration_id="reuse-case",
            asset_type="lesson_plan",
            unit_type="case",
            source_unit_ids=["case-1"],
            target_unit_ids=["case-1"],
            disposition="reuse_rebind",
            reason="原项目案例仍符合新项目一目标，只需重新归属。",
        ),
        CourseUnitMigration(
            migration_id="rewrite-transition",
            asset_type="teacher_script",
            unit_type="transition",
            source_unit_ids=["transition-1"],
            target_unit_ids=["transition-new-1"],
            disposition="rewrite_partial",
            reason="新项目顺序需要新的课堂转场。",
            candidate_status="ready",
        ),
        CourseUnitMigration(
            migration_id="regenerate-slide",
            asset_type="slide_deck",
            unit_type="slide",
            source_unit_ids=["slide-9"],
            target_unit_ids=["slide-new-9"],
            disposition="regenerate",
            reason="页面教学职责和来源讲稿均已变化。",
            candidate_status="ready",
        ),
        CourseUnitMigration(
            migration_id="retire-question",
            asset_type="question_bank",
            unit_type="question",
            source_unit_ids=["question-legacy"],
            disposition="retire",
            reason="题目只考查已经退出新课程目标的记忆性知识。",
        ),
    ]
    plan = CourseChangePlan(
        plan_id="plan-restructure",
        course_id="course-1",
        intent=_intent(signals=[
            CourseChangeSignal(
                signal_id="signal-restructure",
                kind="mixed",
                evidence="新目标需要按项目任务重新组织整门课程。",
                confidence=0.95,
            ),
        ]),
        base_revision_vector={"blueprint": "blueprint-1"},
        structural_operations=[operation],
        unit_migrations=migrations,
        structure_review_status="confirmed",
        created_at=NOW,
        updated_at=NOW,
    )

    summary = summarize_course_change_plan(plan)

    assert summary.total_migrations == 4
    assert summary.by_disposition == {
        "reuse_rebind": 1,
        "rewrite_partial": 1,
        "regenerate": 1,
        "retire": 1,
    }
    assert summary.by_asset_type["slide_deck"] == {"regenerate": 1}
    assert validate_course_change_plan(plan, phase="publish").passed is True


def test_merge_requires_many_to_one_identity_mapping() -> None:
    merge = CourseStructureOperation(
        operation_id="merge-1",
        operation_type="MERGE_OUTLINE_NODES",
        base_blueprint_revision_id="blueprint-1",
        idempotency_key="merge-duplicate-chapters",
        source_node_ids=["chapter-2", "chapter-3"],
        proposed_nodes=[ProposedOutlineNode(
            provisional_id="merged-chapter",
            title="统一应用实践",
            source_node_ids=["chapter-2", "chapter-3"],
        )],
        reason="两个章节目标重复，需要合并并重新组织教学叙事。",
    )

    assert merge.source_node_ids == ["chapter-2", "chapter-3"]
    assert merge.proposed_nodes[0].source_node_ids == ["chapter-2", "chapter-3"]
