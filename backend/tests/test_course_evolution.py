from __future__ import annotations

from copy import deepcopy

import course_evolution
import pytest
from rate_limiter import _match_rate_limit
from course_document import (
    CourseBlock,
    document_from_legacy_course,
    refresh_document_revision,
)
from course_repository import CourseDocumentRepository
from course_evolution import (
    CourseEvolutionOperation,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
    CourseEvolutionState,
    accept_change_set,
    course_evolution_view,
    create_adjustment_plan,
    personal_course_overlay,
    reject_change_set,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)
from course_revisions import revision_vector_for_document


class _MemoryCourseStorage:
    def __init__(self, *courses: dict) -> None:
        self.courses = {
            str(course["course_id"]): deepcopy(course)
            for course in courses
        }

    def load_course(self, course_id: str) -> dict | None:
        value = self.courses.get(course_id)
        return deepcopy(value) if value else None

    async def save_course(self, course_id: str, course: dict) -> None:
        self.courses[course_id] = deepcopy(course)


def _course() -> dict:
    course = {
        "course_id": "course-growth",
        "course_name": "线性代数",
        "nodes": [
            {
                "node_id": f"section-{index}",
                "parent_node_id": "root",
                "node_name": title,
                "node_level": 2,
                "learning_objective": f"理解{title}",
                "objective_id": f"objective-{index}",
                "node_content": content,
            }
            for index, (title, content) in enumerate([
                ("矩阵复合", "矩阵乘法表示线性变换的复合。"),
                ("结合律", "复合变换满足结合律。"),
                ("逆变换", "可逆矩阵对应可逆线性变换。"),
                ("坐标变换", "同一变换可在不同基底下表示。"),
                ("应用", "使用矩阵复合描述连续操作。"),
            ], start=1)
        ],
    }
    document = document_from_legacy_course(course)
    course["course_document"] = document.model_dump(mode="json")
    course["course_schema_version"] = "course_document_v1"
    course["course_document_revision"] = document.document_revision
    course["course_document_authoritative"] = True
    course["current_course_version_id"] = document.document_revision
    course["course_operation_log"] = []
    return course


def _document_repository(course: dict) -> CourseDocumentRepository:
    return CourseDocumentRepository(_MemoryCourseStorage(course))


def _legacy_overlay_state(course: dict) -> tuple[CourseEvolutionState, object]:
    document = document_from_legacy_course(course)
    target = next(block for block in document.blocks if block.status != "retired")
    vector = revision_vector_for_document(document).revisions
    operation = CourseEvolutionOperation(
        operation_id="legacy-operation-1",
        operation_type="INSERT_PERSONAL_SUPPORT",
        target_block_id=target.block_id,
        target_section_id=target.section_id,
        reason="legacy personalized explanation",
        payload={"body": "legacy support"},
    )
    plan = CourseEvolutionPlan(
        plan_kind="personal_adaptation_plan",
        write_target="personal_overlay",
        change_set_id="legacy-plan-1",
        user_id="student-a",
        course_id=document.course_id,
        hypothesis_id="legacy-hypothesis-1",
        base_revision_vector={
            f"block:{target.block_id}": vector[f"block:{target.block_id}"],
            f"section:{target.section_id}": vector[f"section:{target.section_id}"],
        },
        operations=[operation],
        selected_scope="current",
        selected_operation_ids=[operation.operation_id],
        expected_effect="explain the difficult point",
        status="applied",
        created_at="2026-07-17T00:00:00+00:00",
        updated_at="2026-07-17T00:00:00+00:00",
    )
    state = CourseEvolutionState(
        user_id="student-a",
        course_id=document.course_id,
        change_sets=[plan],
        revision="legacy-state-1",
        updated_at="2026-07-17T00:00:00+00:00",
    )
    return state, document


def test_legacy_personal_overlay_rebases_when_block_anchor_is_unchanged():
    state, document = _legacy_overlay_state(_course())
    target = document.blocks[0]
    document.blocks.append(CourseBlock(
        block_id="new-sibling-block",
        section_id=target.section_id,
        position=target.position + 1,
        kind="callout",
        role="summary",
        payload={"markdown": "new base course content"},
    ))
    updated = refresh_document_revision(document)
    current_vector = revision_vector_for_document(updated).revisions

    overlay = personal_course_overlay(
        state,
        current_revision_vector=current_vector,
    )

    assert overlay.resolution_status == "active"
    assert overlay.active_plan_ids == ["legacy-plan-1"]
    assert [item.operation_id for item in overlay.operations] == ["legacy-operation-1"]
    assert overlay.conflicts == []
    assert overlay.relocations[0]["reason"] == "section_rebased_target_block_unchanged"


def test_legacy_personal_overlay_conflict_is_reported_and_not_projected():
    state, document = _legacy_overlay_state(_course())
    document.blocks[0].payload["markdown"] = "base course changed the semantic target"
    updated = refresh_document_revision(document)
    current_vector = revision_vector_for_document(updated).revisions

    overlay = personal_course_overlay(
        state,
        current_revision_vector=current_vector,
    )

    assert overlay.resolution_status == "conflicted"
    assert overlay.active_plan_ids == []
    assert overlay.operations == []
    assert overlay.conflicts[0]["reason"] == "target_block_revision_changed"
    assert overlay.conflicts[0]["requires_user_resolution"] is True


def _course_with_knowledge() -> dict:
    course = _course()
    structures = [
        [{
            "concept_group": "矩阵语义",
            "knowledge_points": [{
                "name": "矩阵复合含义",
                "statement": "矩阵乘法表达线性变换的复合。",
                "knowledge_type": "principle",
                "capability_points": [{
                    "name": "解释复合顺序",
                    "observable_behavior": "能够解释矩阵乘法顺序与变换复合的关系",
                }],
                "misconceptions": [{
                    "name": "把矩阵乘法只理解为行乘列",
                    "observable_error_pattern": "只能复述计算规则，无法解释复合含义",
                    "discrimination": "区分语义对象与坐标计算",
                    "repair_strategy": "用连续变换过程重新解释乘法顺序",
                }],
                "mastery_criteria": [{
                    "name": "复合语义达标",
                    "observable_performance": "不依赖公式解释两个变换的复合顺序",
                    "verification_method": "完成一道变换顺序辨析题",
                }],
                "relations": [{
                    "target_name": "复合结合律",
                    "relation_type": "derives",
                    "reason": "结合律来自变换复合的结合性",
                    "derivation_steps": ["先组合前两个变换", "再比较组合结果"],
                }],
            }],
        }],
        [{
            "concept_group": "无关插入",
            "knowledge_points": [{
                "name": "坐标记号",
                "statement": "坐标用于表示向量。",
                "knowledge_type": "representation",
                "capability_points": [{"name": "读取坐标", "observable_behavior": "读取给定坐标"}],
                "mastery_criteria": [{
                    "name": "坐标读取达标",
                    "observable_performance": "准确读取坐标",
                    "verification_method": "完成读取题",
                }],
            }],
        }],
        [{
            "concept_group": "复合推导",
            "knowledge_points": [{
                "name": "复合结合律",
                "statement": "线性变换的复合满足结合律。",
                "knowledge_type": "principle",
                "capability_points": [{"name": "应用结合律", "observable_behavior": "重组连续变换"}],
                "mastery_criteria": [{
                    "name": "结合律应用达标",
                    "observable_performance": "正确重组连续变换",
                    "verification_method": "完成重组题",
                }],
            }],
        }],
    ]
    for node, structure in zip(course["nodes"], structures):
        node["knowledge_structure"] = structure
    document = document_from_legacy_course(course)
    course["course_document"] = document.model_dump(mode="json")
    return course


def _install_sources(monkeypatch, document) -> None:
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [
        {
            "event_id": "event-dialogue",
            "event_type": "learner_self_reported",
            "course_id": document.course_id,
            "node_id": "section-1",
            "evidence": {"statement": "我会计算，但不理解为什么要这样乘，还是没懂"},
            "created_at": "2026-07-16T09:00:00+00:00",
        },
        {
            "event_id": "event-record-audit",
            "event_type": "learning_record_created",
            "course_id": document.course_id,
            "node_id": "section-1",
            "evidence": {"record_id": "record-note"},
            "created_at": "2026-07-16T09:02:00+00:00",
        },
        {
            "event_id": "event-practice-audit",
            "event_type": "practice_attempt_graded",
            "course_id": document.course_id,
            "node_id": "section-1",
            "evidence": {"attempt_id": "attempt-failed"},
            "result": {"passed": False, "feedback": "没有解释乘法顺序"},
            "created_at": "2026-07-16T09:04:00+00:00",
        },
    ])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [{
        "record_id": "record-note",
        "record_type": "note",
        "status": "active",
        "node_id": "section-1",
        "content": "行乘列只是坐标计算，我不清楚它和复合有什么关系。",
        "created_at": "2026-07-16T09:02:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [{
        "attempt_id": "attempt-failed",
        "status": "graded",
        "node_id": "section-1",
        "result": {"passed": False, "grading_confidence": 0.94, "feedback": "没有解释乘法顺序"},
        "graded_at": "2026-07-16T09:04:00+00:00",
    }])


def test_three_independent_evidence_sources_create_explainable_multi_scope_candidate(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    monkeypatch.setattr(course_evolution.learning_asset_repository, "load_bundle", lambda _course_id: {
        "assets": {
            "questions": [{
                "asset_id": "question-targeted",
                "revision_id": "question-revision-targeted",
                "node_id": "section-1",
                "status": "active",
                "prompt": "解释矩阵复合顺序，并判断交换顺序是否改变结果。",
            }],
        },
    })
    repository = CourseEvolutionRepository(tmp_path)

    state = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )

    assert {item.source_type for item in state.evidence_items} == {
        "learning_event", "learning_record", "practice_attempt",
    }
    assert len(state.evidence_items) == 3
    assert len(state.hypotheses) == 1
    hypothesis = state.hypotheses[0]
    assert 0.0 <= hypothesis.confidence <= 1.0
    assert hypothesis.status == "candidate_created"
    assert hypothesis.claim == "学习者会执行计算，但尚未理解复合变换的先后顺序。"
    assert hypothesis.recommended_scope == "current_and_next"
    assert len(hypothesis.affected_block_ids) == 4
    change_set = state.change_sets[0]
    assert change_set.status == "pending"
    assert change_set.allowed_scopes == ["current", "current_and_next"]
    assert {item.operation_type for item in change_set.operations} >= {
        "INSERT_COURSE_SUPPORT", "ADD_ANIMATION", "ADD_TARGETED_PRACTICE", "ADD_TRANSITION_SUPPORT",
    }
    animation = next(item for item in change_set.operations if item.operation_type == "ADD_ANIMATION")
    practice = next(item for item in change_set.operations if item.operation_type == "ADD_TARGETED_PRACTICE")
    assert animation.payload["animation_spec"]["schema_version"] == "animation_spec_v1"
    assert animation.payload["animation_spec"]["scene"]["renderer"] == "linear_transform_composition_v1"
    assert animation.payload["animation_spec"]["scene"]["composition"] == "ABv = A(Bv)"
    assert len(animation.payload["animation_spec"]["keyframes"]) == 3
    assert len(animation.payload["animation_spec"]["fallback_frames"]) == 3
    assert practice.payload["practice_task_id"] == "question-revision-targeted"
    assert practice.payload["practice_intent"] == "standard"
    assert practice.payload["requires_confirmation"] is True
    assert "范围外课程内容" in change_set.impact_summary["protected"]


def test_video_two_evidence_chain_replaces_old_candidate_and_requires_independent_validation(
    tmp_path,
    monkeypatch,
):
    course = _course_with_knowledge()
    document = document_from_legacy_course(course)
    target = next(item for item in document.blocks if item.section_id == "section-1")
    events = [{
        "event_id": "event-question",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": "为什么是先做右边的变换？"},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-18T09:00:00+00:00",
    }]
    records = []
    attempts = []
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: deepcopy(events))
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: deepcopy(records))
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: deepcopy(attempts))
    monkeypatch.setattr(course_evolution.learning_asset_repository, "load_bundle", lambda _course_id: {
        "assets": {
            "questions": [
                {
                    "asset_id": "question-original",
                    "revision_id": "question-original-order",
                    "node_id": "section-1",
                    "status": "active",
                    "prompt": "判断两个变换的执行顺序。",
                },
                {
                    "asset_id": "question-independent",
                    "revision_id": "question-independent-order",
                    "node_id": "section-1",
                    "status": "active",
                    "prompt": "用一个新情境解释矩阵复合顺序。",
                },
                {
                    "asset_id": "question-transfer",
                    "revision_id": "question-transfer-order",
                    "node_id": "section-1",
                    "status": "active",
                    "prompt": "在另一个线性变换情境中独立判断复合顺序。",
                },
            ],
        },
    })
    repository = CourseEvolutionRepository(tmp_path / "evolution")
    document_repository = _document_repository(course)

    question_only = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    assert question_only.change_sets == []

    records.append({
        "record_id": "record-note",
        "record_type": "note",
        "status": "active",
        "node_id": "section-1",
        "content": "计算会做，但顺序总是理解反。",
        "created_at": "2026-07-18T09:02:00+00:00",
    })
    two_sources = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    assert two_sources.change_sets == []
    assert two_sources.hypotheses[0].status == "observing"
    assert two_sources.hypotheses[0].evidence_assessment["gate_reason"] == (
        "尚缺正式证据或重复独立信号，继续观察"
    )

    attempts.append({
        "attempt_id": "attempt-original-failed",
        "status": "graded",
        "node_id": "section-1",
        "task_revision_id": "question-original-order",
        "result": {
            "passed": False,
            "grading_confidence": 0.96,
            "feedback": "概念理解题中选择了错误的变换顺序。",
        },
        "graded_at": "2026-07-18T09:04:00+00:00",
    })
    three_sources = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    pending = [item for item in three_sources.change_sets if item.status == "pending"]
    superseded = [item for item in three_sources.change_sets if item.status == "stale"]
    assert len(pending) == 1
    assert superseded == []
    plan = pending[0]
    assert len(plan.evidence_ids) == 3
    assert plan.impact_summary["diagnosis"] == "学习者会执行计算，但尚未理解复合变换的先后顺序。"
    assert plan.allowed_scopes == ["current", "current_and_next"]
    assert plan.impact_summary["source_practice_task_ids"] == ["question-original-order"]
    assert set(plan.impact_summary["validation_task_ids"]) == {
        "question-independent-order",
        "question-transfer-order",
    }
    assert [item.operation_type for item in plan.operations].count("ADD_TRANSITION_SUPPORT") == 1
    assert [item.operation_type for item in plan.operations].count("ADD_CHECKPOINT") >= 1
    assert next(
        item for item in plan.operations
        if item.operation_type == "ADD_TARGETED_PRACTICE"
    ).payload["practice_task_id"] == "question-independent-order"

    applied = accept_change_set(
        course,
        user_id="student-a",
        change_set_id=plan.change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )
    applied_plan = next(item for item in applied.change_sets if item.change_set_id == plan.change_set_id)
    baseline = applied_plan.impact_summary["effect_baseline"]
    assert baseline["problem_type"] == "conceptual_gap"
    assert baseline["selected_scope"] == "current_and_next"
    assert baseline["practice_attempt_ids"] == ["attempt-original-failed"]
    assert baseline["practice_task_ids"] == ["question-original-order"]
    applied_document, _ = document_repository.load_document(course["course_id"])
    independent_practice = next(
        block for block in applied_document.blocks
        if block.block_id in applied_plan.applied_block_ids
        and block.kind == "practice_ref"
    )
    assert independent_practice.payload["validation_task_ids"] == [
        "question-independent-order",
        "question-transfer-order",
    ]
    assert independent_practice.asset_refs == [
        "question-independent-order",
        "question-transfer-order",
    ]
    untouched_section = next(item for item in document.sections if item.section_id == "section-5")
    assert untouched_section.section_id not in applied_plan.impact_summary["affected_section_ids"]
    assert all(
        block.section_id != untouched_section.section_id
        for block in applied_document.blocks
        if block.block_id in applied_plan.applied_block_ids
    )

    events.append({
        "event_id": "interaction-animation",
        "event_type": "adaptive_block_interaction",
        "course_id": document.course_id,
        "node_id": "section-1",
        "result": {
            "interaction": "animation_answered",
            "answer": "right_then_left",
            "correct": True,
        },
        "metadata": {
            "adaptive_block_id": next(
                item.operation_id
                for item in plan.operations
                if item.operation_type == "ADD_ANIMATION"
            ),
        },
        "created_at": "2099-01-01T00:00:00+00:00",
    })
    attempts.append({
        "attempt_id": "attempt-original-retry",
        "status": "graded",
        "node_id": "section-1",
        "task_revision_id": "question-original-order",
        "result": {"passed": True, "grading_confidence": 0.98},
        "graded_at": "2099-01-02T00:00:00+00:00",
    })
    original_retry = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    result = next(item for item in original_retry.change_sets if item.change_set_id == plan.change_set_id)
    assert result.effect_evaluation["status"] == "insufficient_evidence"
    assert result.effect_evaluation["attempt_ids"] == []

    attempts.append({
        "attempt_id": "attempt-independent-passed",
        "status": "graded",
        "node_id": "section-1",
        "task_revision_id": "question-independent-order",
        "result": {"passed": True, "grading_confidence": 0.98},
        "graded_at": "2099-01-03T00:00:00+00:00",
    })
    independently_validated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    result = next(
        item for item in independently_validated.change_sets
        if item.change_set_id == plan.change_set_id
    )
    assert result.effect_evaluation["status"] == "effective"
    assert result.effect_evaluation["attempt_ids"] == ["attempt-independent-passed"]
    assert result.effect_evaluation["verification_level"] == "initial_support"
    assert result.effect_evaluation["verification_summary"]["baseline"]["passed"] is False
    assert result.effect_evaluation["verification_summary"]["follow_up"]["passed"] is True

    attempts.append({
        "attempt_id": "attempt-transfer-passed",
        "status": "graded",
        "node_id": "section-1",
        "task_revision_id": "question-transfer-order",
        "result": {"passed": True, "grading_confidence": 0.97},
        "graded_at": "2099-01-04T00:00:00+00:00",
    })
    repeatedly_validated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    result = next(
        item for item in repeatedly_validated.change_sets
        if item.change_set_id == plan.change_set_id
    )
    assert result.effect_evaluation["verification_level"] == "confirmed"
    assert result.effect_evaluation["verification_summary"]["follow_up"]["distinct_task_count"] == 2


def test_acceptance_commits_current_course_revision_and_can_be_undone(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    monkeypatch.setattr(course_evolution.learning_asset_repository, "load_bundle", lambda _course_id: {
        "assets": {
            "questions": [{
                "asset_id": "question-targeted",
                "revision_id": "question-revision-targeted",
                "node_id": "section-1",
                "status": "active",
                "prompt": "解释矩阵复合顺序。",
            }],
        },
    })
    repository = CourseEvolutionRepository(tmp_path)
    document_repository = _document_repository(course)
    before_document, _ = document_repository.load_document(course["course_id"])
    student_a = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    change_set_id = student_a.change_sets[0].change_set_id

    applied = accept_change_set(
        course,
        user_id="student-a",
        change_set_id=change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )
    applied_document, _ = document_repository.load_document(course["course_id"])
    overlay = personal_course_overlay(applied)
    view = course_evolution_view(applied)
    plan = applied.change_sets[0]

    assert applied_document.document_revision != before_document.document_revision
    assert len(applied_document.blocks) > len(before_document.blocks)
    assert plan.plan_kind == "course_evolution_plan"
    assert plan.write_target == "course_document"
    assert plan.applied_block_ids
    assert plan.application_receipt["document_revision"] == applied_document.document_revision
    assert {
        block.block_id
        for block in applied_document.blocks
        if block.status != "retired"
    } >= set(plan.applied_block_ids)
    independent_practice = next(
        block for block in applied_document.blocks
        if block.payload.get("practice_intent") == "standard"
    )
    assert independent_practice.kind == "practice_ref"
    assert independent_practice.asset_refs == ["question-revision-targeted"]
    assert independent_practice.payload["validation_task_ids"] == [
        "question-revision-targeted",
    ]
    assert overlay.active_plan_ids == []
    assert overlay.operations == []
    assert view["course_evolution_plans"][0]["plan_kind"] == "course_evolution_plan"
    assert view["permissions"] == {
        "write_target": "course_document",
        "can_modify_current_course": True,
        "can_modify_other_courses": False,
        "can_modify_course_knowledge_base": False,
    }

    undone = undo_change_set(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=change_set_id,
        repository=repository,
        document_repository=document_repository,
    )
    undone_document, _ = document_repository.load_document(course["course_id"])
    assert undone_document.document_revision != applied_document.document_revision
    assert all(
        block.status == "retired"
        for block in undone_document.blocks
        if block.block_id in plan.applied_block_ids
    )


def test_demo_mode_relaxes_strong_contract(monkeypatch):
    weak = "不理解为什么复合变换要先右后左，请用动画解释一下。"
    contract = course_evolution._strong_self_report_contract(weak)
    assert contract["is_strong"] is False

    monkeypatch.setenv("EVOLUTION_DEMO_MODE", "1")
    relaxed = course_evolution._strong_self_report_contract(weak)
    assert relaxed["is_strong"] is True
    assert relaxed["is_complete_contract"] is True
    assert relaxed["scope"] == "current"


def test_block_text_excludes_embedded_diagram_and_html_syntax():
    excerpt = course_evolution._block_text({
        "markdown": """
先解释输入对象，再追踪每一步的变化。

```mermaid
flowchart LR
    A --> B
```

<div style="display:grid"><strong>静态流程卡</strong></div>
最后回到原结论。
        """,
    })

    assert excerpt == "先解释输入对象，再追踪每一步的变化。 静态流程卡 最后回到原结论。"
    assert "mermaid" not in excerpt
    assert "flowchart" not in excerpt
    assert "style=" not in excerpt


def test_current_and_next_fallback_reaches_later_sections_with_dense_current_section():
    document = document_from_legacy_course(_course())
    source = next(item for item in document.blocks if item.section_id == "section-1")
    document.blocks.extend([
        source.model_copy(update={
            "block_id": f"{source.block_id}-local-{index}",
            "position": source.position + index,
        })
        for index in range(1, 5)
    ])

    affected = course_evolution._affected_blocks(
        document,
        source.block_id,
        scope="current_and_next",
        knowledge_base=None,
    )
    block_sections = {
        item.block_id: item.section_id
        for item in document.blocks
    }

    assert affected[0] == source.block_id
    assert len(affected) == 4
    assert any(
        block_sections[block_id] != source.section_id
        for block_id in affected[1:]
    )


def test_strong_scoped_ai_self_report_immediately_creates_related_course_plan(
    tmp_path,
    monkeypatch,
):
    course = _course_with_knowledge()
    document = document_from_legacy_course(course)
    target = next(item for item in document.blocks if item.section_id == "section-1")
    question = (
        "矩阵乘法计算我会，但我一直不理解为什么复合变换要先右后左。"
        "请在本节和后面相关内容中，先用几何动画解释，再让我进行计算。"
    )
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [{
        "event_id": "event-strong-scoped-request",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": question},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-19T09:00:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [])

    state = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=CourseEvolutionRepository(tmp_path),
    )

    assert len(state.evidence_items) == 1
    assert state.evidence_items[0].evidence_kind == "explicit_comprehension_gap"
    hypothesis = state.hypotheses[0]
    assessment = hypothesis.evidence_assessment
    assert hypothesis.status == "candidate_created"
    assert hypothesis.claim == "学习者会执行计算，但尚未理解复合变换的先后顺序。"
    assert hypothesis.recommended_scope == "current_and_next"
    assert assessment["maturity"] == "explicit_scoped_request"
    assert assessment["has_strong_self_report"] is True
    assert assessment["has_explicit_scope"] is True
    assert assessment["explicit_scope"] == "current_and_next"
    assert assessment["explicit_request_contract"] == {
        "is_strong": True,
        "is_complete_contract": True,
        "has_capability_boundary": True,
        "has_explicit_gap": True,
        "has_persistence": True,
        "has_teaching_request": True,
        "requested_supports": ["explanation", "animation", "practice"],
        "capability_text": "矩阵乘法计算",
        "gap_text": "不理解复合变换顺序",
        "scope": "current_and_next",
    }
    synonym_contract = course_evolution._strong_self_report_contract(
        "基本运算我能做，但总是搞不清矩阵复合的顺序。"
        "请把这一节以及后续相关小节用图形演示讲清楚，最后让我练习。"
    )
    assert synonym_contract["is_strong"] is True
    assert synonym_contract["scope"] == "current_and_next"
    assert synonym_contract["requested_supports"] == [
        "explanation",
        "animation",
        "practice",
    ]
    assert course_evolution._strong_self_report_contract(
        "这道题怎么算？"
    )["is_strong"] is False
    assert "后续范围" in assessment["gate_reason"]

    plan = state.change_sets[0]
    assert plan.status == "pending"
    assert plan.request_text == question
    assert plan.allowed_scopes == ["current", "current_and_next"]
    assert plan.requested_roles == ["explanation", "animation", "practice"]
    assert len(plan.impact_summary["dependent_block_ids"]) == 3
    assert plan.impact_summary["trigger_contract"]["scope"] == "current_and_next"
    assert [item.operation_type for item in plan.operations].count("ADD_ANIMATION") == 1
    assert [item.operation_type for item in plan.operations].count("ADD_TRANSITION_SUPPORT") == 1
    assert [item.operation_type for item in plan.operations].count("ADD_CHECKPOINT") == 2
    assert {item.scope for item in plan.operations} == {"current", "next"}
    assert len(plan.impact_summary["affected_section_ids"]) > 1


def test_resolved_strong_request_requires_new_strong_evidence_before_reproposal(
    tmp_path,
    monkeypatch,
):
    course = _course_with_knowledge()
    document = document_from_legacy_course(course)
    target = next(item for item in document.blocks if item.section_id == "section-1")
    question = (
        "矩阵乘法计算我会，但我一直不理解为什么复合变换要先右后左。"
        "请在本节和后面相关内容中，先用几何动画解释，再让我进行计算。"
    )
    events = [{
        "event_id": "event-strong-scoped-request-1",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": question},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-19T09:00:00+00:00",
    }]
    monkeypatch.setattr(
        course_evolution,
        "load_learning_events",
        lambda **_kwargs: deepcopy(events),
    )
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [])
    repository = CourseEvolutionRepository(tmp_path)

    initial = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    first_plan = initial.change_sets[0]
    rejected = reject_change_set(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=first_plan.change_set_id,
        repository=repository,
    )
    assert rejected.change_sets[0].status == "rejected"

    unchanged = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    assert len(unchanged.change_sets) == 1
    assert unchanged.change_sets[0].status == "rejected"
    assert unchanged.hypotheses[0].evidence_assessment[
        "blocked_by_previous_resolution"
    ] is True

    events.append({
        "event_id": "event-strong-scoped-request-2",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": question},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-19T09:05:00+00:00",
    })
    refreshed = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    assert len(refreshed.change_sets) == 2
    assert refreshed.change_sets[-1].status == "pending"
    assert refreshed.change_sets[-1].evidence_ids != first_plan.evidence_ids


def test_undo_does_not_recreate_plan_from_the_same_strong_request(
    tmp_path,
    monkeypatch,
):
    course = _course_with_knowledge()
    document = document_from_legacy_course(course)
    target = next(item for item in document.blocks if item.section_id == "section-1")
    question = (
        "矩阵乘法计算我会，但我一直不理解为什么复合变换要先右后左。"
        "请在本节和后面相关内容中，先用几何动画解释，再让我进行计算。"
    )
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [{
        "event_id": "event-strong-scoped-request",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": question},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-19T09:00:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [])
    repository = CourseEvolutionRepository(tmp_path)
    document_repository = _document_repository(course)

    initial = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    plan = initial.change_sets[0]
    accept_change_set(
        course,
        user_id="student-a",
        change_set_id=plan.change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )
    undo_change_set(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=plan.change_set_id,
        repository=repository,
        document_repository=document_repository,
    )

    reevaluated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    assert len(reevaluated.change_sets) == 1
    assert reevaluated.change_sets[0].status == "undone"
    assert reevaluated.hypotheses[0].status == "observing"


def test_single_explicit_evidence_stays_local_instead_of_expanding_by_count(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [{
        "event_id": "event-explicit",
        "event_type": "learner_self_reported",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"statement": "这段完全看不懂，推导跳步太多"},
        "created_at": "2026-07-16T09:00:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [])

    state = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=CourseEvolutionRepository(tmp_path),
    )

    assert state.hypotheses[0].recommended_scope == "current"
    assert state.change_sets[0].allowed_scopes == ["current"]
    assert all(operation.scope == "current" for operation in state.change_sets[0].operations)


def test_ai_question_is_anchored_to_course_knowledge_and_relations_drive_scope(
    tmp_path,
    monkeypatch,
):
    course = _course_with_knowledge()
    document = document_from_legacy_course(course)
    target = next(item for item in document.blocks if item.section_id == "section-1")
    related = next(item for item in document.blocks if item.section_id == "section-3")
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [{
        "event_id": "event-question",
        "event_type": "assistant_question_submitted",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"question": "我会计算，但不理解为什么要这样乘"},
        "metadata": {"context_ref": {"content_anchor": {"block_id": target.block_id}}},
        "created_at": "2026-07-16T09:00:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [{
        "record_id": "record-1",
        "record_type": "note",
        "status": "active",
        "node_id": "section-1",
        "content": "行乘列和复合的关系不清楚",
        "created_at": "2026-07-16T09:01:00+00:00",
    }])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [{
        "attempt_id": "attempt-1",
        "status": "graded",
        "node_id": "section-1",
        "result": {"passed": False, "grading_confidence": 0.95, "feedback": "没有解释复合顺序"},
        "graded_at": "2026-07-16T09:02:00+00:00",
    }])

    state = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=CourseEvolutionRepository(tmp_path),
    )

    question = next(item for item in state.evidence_items if item.evidence_kind == "learner_question")
    hypothesis = state.hypotheses[0]
    plan = state.change_sets[0]
    assert question.anchor.knowledge_node_ids
    assert question.anchor.ability_point_ids
    assert question.anchor.misconception_point_ids
    assert plan.impact_summary["knowledge_labels"] == ["矩阵复合含义"]
    assert "解释复合顺序" in plan.impact_summary["ability_labels"]
    assert "把矩阵乘法只理解为行乘列" in plan.impact_summary["misconception_labels"]
    assert hypothesis.claim == "学习者会执行计算，但尚未理解复合变换的先后顺序。"
    assert plan.impact_summary["diagnosis"] == hypothesis.claim
    assert plan.impact_summary["validation_plan"] == hypothesis.validation_plan
    assert plan.impact_summary["evidence_source_types"] == [
        "learning_event", "learning_record", "practice_attempt",
    ]
    assert related.block_id in plan.impact_summary["dependent_block_ids"]
    assert any(
        operation.operation_type in {"ADD_TRANSITION_SUPPORT", "ADD_CHECKPOINT"}
        and operation.target_block_id == related.block_id
        for operation in plan.operations
    )
    animation = next(item for item in plan.operations if item.operation_type == "ADD_ANIMATION")
    checkpoint = next(item for item in plan.operations if item.operation_type == "ADD_TARGETED_PRACTICE")
    assert animation.payload["animation_spec"]["knowledge_refs"] == plan.impact_summary["knowledge_node_ids"]
    assert checkpoint.payload["ability_refs"] == plan.impact_summary["ability_point_ids"]
    assert checkpoint.payload["expected_effect"]


def test_course_evolution_api_commits_the_reviewed_course_revision(
    tmp_path,
    monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import course_evolution as evolution_router

    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
    document_repository = _document_repository(course)
    monkeypatch.setattr(course_evolution, "course_evolution_repository", repository)
    monkeypatch.setattr(
        evolution_router,
        "get_course_document_repository",
        lambda: document_repository,
    )

    async def existing_course(_course_id: str):
        return document_repository.load_course_view(_course_id)

    monkeypatch.setattr(evolution_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(evolution_router.router, prefix="/api")
    client = TestClient(app)
    before, _ = document_repository.load_document(course["course_id"])

    loaded = client.get(
        "/api/courses/course-growth/evolution",
        headers={"X-User-Id": "student-a"},
    )
    assert loaded.status_code == 200
    plan_id = loaded.json()["course_evolution_plans"][0]["plan_id"]

    accepted = client.post(
        f"/api/courses/course-growth/evolution/change-sets/{plan_id}/accept",
        headers={"X-User-Id": "student-a"},
        json={"selected_scope": "current_and_next"},
    )

    assert accepted.status_code == 200
    payload = accepted.json()
    after, _ = document_repository.load_document(course["course_id"])
    assert after.document_revision != before.document_revision
    assert payload["course_evolution_plans"][0]["write_target"] == "course_document"
    assert payload["permissions"]["can_modify_current_course"] is True
    assert payload["permissions"]["can_modify_other_courses"] is False


def test_course_evolution_progress_returns_generation_checkpoint_without_re_evaluation(
    tmp_path,
    monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import course_evolution as evolution_router

    repository = CourseEvolutionRepository(tmp_path)
    state = repository.load("student-a", "course-growth")
    state.change_sets.append(CourseEvolutionPlan(
        change_set_id="plan-live",
        user_id="student-a",
        course_id="course-growth",
        hypothesis_id="hypothesis-live",
        source_kind="manual_section_request",
        target_section_id="section-1",
        request_text="全课程例子都讲详细一点",
        generation_status="generating",
        scope_selection="whole_course",
        impact_summary={"matched_block_count": 3},
        expected_effect="让全课程例子更完整",
        created_at="2026-07-19T09:00:00+00:00",
        updated_at="2026-07-19T09:00:00+00:00",
    ))
    repository.save(state)
    monkeypatch.setattr(evolution_router, "course_evolution_repository", repository)

    async def existing_course(_course_id: str):
        return _course()

    monkeypatch.setattr(evolution_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(evolution_router.router, prefix="/api")
    client = TestClient(app)

    response = client.get(
        "/api/courses/course-growth/evolution/progress",
        headers={"X-User-Id": "student-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["course_evolution_plans"][0]["generation_status"] == "generating"
    assert payload["course_evolution_plans"][0]["impact_summary"]["matched_block_count"] == 3


def test_course_evolution_progress_has_read_only_polling_rate_limit():
    assert _match_rate_limit(
        "/api/courses/course-growth/evolution/progress"
    ) == (120, 60)
    assert _match_rate_limit(
        "/api/courses/course-growth/evolution"
    ) == (30, 60)


def test_ineffective_adaptation_creates_reviewable_replacement_and_replaces_atomically(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
    document_repository = _document_repository(course)
    initial = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    source_id = initial.change_sets[0].change_set_id
    accept_change_set(
        course,
        user_id="student-a",
        change_set_id=source_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )

    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [
        {
            "event_id": "event-dialogue",
            "event_type": "learner_self_reported",
            "course_id": document.course_id,
            "node_id": "section-1",
            "evidence": {"statement": "我会计算，但不理解为什么要这样乘，还是没懂"},
            "created_at": "2026-07-16T09:00:00+00:00",
        },
        {
            "event_id": "feedback-not-helpful",
            "event_type": "adaptive_block_feedback",
            "course_id": document.course_id,
            "node_id": "section-1",
            "result": {"feedback": "not_helpful"},
            "metadata": {
                "adaptive_block_id": initial.change_sets[0].operations[0].operation_id,
            },
            "created_at": "2099-01-01T00:00:00+00:00",
        },
    ])
    evaluated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    source = next(item for item in evaluated.change_sets if item.change_set_id == source_id)
    assert source.effect_evaluation["status"] == "ineffective"
    assert source.effect_evaluation["follow_up_candidate"]["candidate_type"] == "adjust_course_evolution"

    adjusted = create_adjustment_plan(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=source_id,
        repository=repository,
        document_repository=document_repository,
    )
    replacement = next(item for item in adjusted.change_sets if item.replaces_change_set_id == source_id)
    assert replacement.status == "pending"
    assert "状态对照" in replacement.expected_effect

    applied = accept_change_set(
        course,
        user_id="student-a",
        change_set_id=replacement.change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )
    assert next(item for item in applied.change_sets if item.change_set_id == source_id).status == "undone"
    assert next(item for item in applied.change_sets if item.change_set_id == replacement.change_set_id).status == "applied"
    assert personal_course_overlay(applied).active_plan_ids == []
    source_plan = next(item for item in applied.change_sets if item.change_set_id == source_id)
    replacement_plan = next(item for item in applied.change_sets if item.change_set_id == replacement.change_set_id)
    updated_document, _ = document_repository.load_document(course["course_id"])
    assert all(
        block.status == "retired"
        for block in updated_document.blocks
        if block.block_id in source_plan.applied_block_ids
    )
    assert set(replacement_plan.applied_block_ids) <= {
        block.block_id
        for block in updated_document.blocks
        if block.status != "retired"
    }


@pytest.mark.parametrize(("feedback", "later_results", "interaction", "expected", "action"), [
    ("helpful", [True], "", "effective", "keep"),
    ("", [True], "animation_answered", "effective", "keep"),
    ("", [True], "animation_played", "insufficient_evidence", "collect_more_evidence"),
    ("not_helpful", [False, False], "", "harmful", "rollback"),
    ("", [], "", "insufficient_evidence", "collect_more_evidence"),
])
def test_effect_evaluation_uses_later_learning_evidence_not_acceptance(
    tmp_path,
    monkeypatch,
    feedback,
    later_results,
    interaction,
    expected,
    action,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path / expected)
    document_repository = _document_repository(course)
    initial = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    plan = initial.change_sets[0]
    accept_change_set(
        course,
        user_id="student-a",
        change_set_id=plan.change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )

    events = [{
        "event_id": "event-dialogue",
        "event_type": "learner_self_reported",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"statement": "我会计算，但不理解为什么要这样乘，还是没懂"},
        "created_at": "2026-07-16T09:00:00+00:00",
    }]
    if feedback:
        events.append({
            "event_id": f"feedback-{feedback}",
            "event_type": "adaptive_block_feedback",
            "course_id": document.course_id,
            "node_id": "section-1",
            "result": {"feedback": feedback},
            "metadata": {"adaptive_block_id": plan.operations[0].operation_id},
            "created_at": "2099-01-01T00:00:00+00:00",
        })
    if interaction:
        interaction_result = {"interaction": interaction}
        if interaction == "animation_answered":
            interaction_result.update({
                "answer": "right_then_left",
                "correct": True,
            })
        events.append({
            "event_id": "interaction-animation",
            "event_type": "adaptive_block_interaction",
            "course_id": document.course_id,
            "node_id": "section-1",
            "result": interaction_result,
            "metadata": {"adaptive_block_id": plan.operations[1].operation_id},
            "created_at": "2099-01-01T00:00:00+00:00",
        })
    attempts = [{
        "attempt_id": "attempt-before",
        "status": "graded",
        "node_id": "section-1",
        "result": {"passed": False, "grading_confidence": 0.94},
        "graded_at": "2026-07-16T09:04:00+00:00",
    }]
    attempts.extend({
        "attempt_id": f"attempt-after-{index}",
        "status": "graded",
        "node_id": "section-1",
        "result": {"passed": passed, "grading_confidence": 0.94},
        "graded_at": f"2099-01-0{index + 2}T00:00:00+00:00",
    } for index, passed in enumerate(later_results))
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: events)
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: attempts)

    evaluated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    result = next(item for item in evaluated.change_sets if item.change_set_id == plan.change_set_id)
    assert result.effect_evaluation["status"] == expected
    assert result.effect_evaluation["recommended_action"] == action
    if interaction:
        assert result.effect_evaluation["interaction_event_ids"] == ["interaction-animation"]
    if expected == "harmful":
        assert result.effect_evaluation["follow_up_candidate"]["candidate_type"] == "rollback_course_evolution"


def test_unrelated_later_success_cannot_prove_personal_adaptation_effective(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
    document_repository = _document_repository(course)
    initial = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    plan = initial.change_sets[0]
    accept_change_set(
        course,
        user_id="student-a",
        change_set_id=plan.change_set_id,
        selected_scope="current_and_next",
        repository=repository,
        document_repository=document_repository,
    )
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [
        {
            "event_id": "event-dialogue",
            "event_type": "learner_self_reported",
            "course_id": document.course_id,
            "node_id": "section-1",
            "evidence": {"statement": "我会计算，但不理解为什么要这样乘，还是没懂"},
            "created_at": "2026-07-16T09:00:00+00:00",
        },
        {
            "event_id": "feedback-helpful",
            "event_type": "adaptive_block_feedback",
            "course_id": document.course_id,
            "node_id": "section-1",
            "result": {"feedback": "helpful"},
            "metadata": {"adaptive_block_id": plan.operations[0].operation_id},
            "created_at": "2099-01-01T00:00:00+00:00",
        },
    ])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [{
        "attempt_id": "unrelated-success",
        "status": "graded",
        "node_id": "section-5",
        "result": {"passed": True, "grading_confidence": 0.98},
        "graded_at": "2099-01-02T00:00:00+00:00",
    }])

    evaluated = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )
    result = next(item for item in evaluated.change_sets if item.change_set_id == plan.change_set_id)
    assert result.effect_evaluation["status"] == "insufficient_evidence"
    assert result.effect_evaluation["attempt_ids"] == []


# --- OpenSpec 5.7 / 5.5 acceptance: legacy overlay is a migration reader only ---


def test_course_evolution_view_exposes_only_legacy_overlay_migration_summary():
    state, document = _legacy_overlay_state(_course())
    current_vector = revision_vector_for_document(document).revisions

    view = course_evolution_view(state, current_revision_vector=current_vector)

    assert "personal_course_overlay" not in view
    assert view["legacy_overlay_migration"] == {
        "schema_version": "legacy_overlay_migration_v1",
        "resolution_status": "active",
        "requires_migration": True,
        "conflicts": [],
    }
    # The deprecated overlay MUST NOT ship a second durable content projection.
    assert "operations" not in view["legacy_overlay_migration"]
    assert "relocations" not in view["legacy_overlay_migration"]


def test_course_evolution_view_requires_migration_when_overlay_conflicts():
    state, document = _legacy_overlay_state(_course())
    document.blocks[0].payload["markdown"] = "base course changed the semantic target"
    updated = refresh_document_revision(document)
    current_vector = revision_vector_for_document(updated).revisions

    view = course_evolution_view(state, current_revision_vector=current_vector)
    migration = view["legacy_overlay_migration"]

    assert migration["requires_migration"] is True
    assert migration["resolution_status"] == "conflicted"
    assert [item["reason"] for item in migration["conflicts"]] == [
        "target_block_revision_changed",
    ]
    assert migration["conflicts"][0]["requires_user_resolution"] is True
    assert migration["conflicts"][0]["operation_id"] == "legacy-operation-1"


def test_course_evolution_view_without_overlay_does_not_require_migration():
    state, document = _legacy_overlay_state(_course())
    state.change_sets = []
    current_vector = revision_vector_for_document(document).revisions

    view = course_evolution_view(state, current_revision_vector=current_vector)

    assert view["legacy_overlay_migration"] == {
        "schema_version": "legacy_overlay_migration_v1",
        "resolution_status": "empty",
        "requires_migration": False,
        "conflicts": [],
    }


def test_legacy_overlay_entry_is_never_silently_dropped_when_block_disappears():
    """OpenSpec 5.5: a relocated-away anchor MUST surface as a conflict."""
    state, document = _legacy_overlay_state(_course())
    target_block_id = document.blocks[0].block_id
    document.blocks = [
        block for block in document.blocks
        if block.block_id != target_block_id
    ]
    updated = refresh_document_revision(document)
    current_vector = revision_vector_for_document(updated).revisions

    overlay = personal_course_overlay(state, current_revision_vector=current_vector)

    assert overlay.resolution_status == "conflicted"
    assert overlay.operations == []
    # Not silently lost: the entry is still accounted for, as a conflict.
    assert len(overlay.conflicts) == 1
    assert overlay.conflicts[0]["reason"] == "target_block_removed"
    assert overlay.conflicts[0]["requires_user_resolution"] is True
    assert overlay.conflicts[0]["operation_id"] == "legacy-operation-1"


def test_legacy_overlay_partially_active_keeps_both_relocated_and_conflicted_entries():
    """A revised base course MUST NOT silently overwrite either outcome."""
    state, document = _legacy_overlay_state(_course())
    intact = document.blocks[0]
    vector = revision_vector_for_document(document).revisions
    plan = state.change_sets[0]
    broken_target = document.blocks[1]
    plan.operations.append(CourseEvolutionOperation(
        operation_id="legacy-operation-2",
        operation_type="INSERT_PERSONAL_SUPPORT",
        scope="current",
        target_section_id=broken_target.section_id,
        target_block_id=broken_target.block_id,
        reason="second legacy personalized explanation",
        payload={"body": "second legacy support"},
    ))
    plan.selected_operation_ids.append("legacy-operation-2")
    plan.base_revision_vector[f"block:{broken_target.block_id}"] = (
        vector[f"block:{broken_target.block_id}"]
    )
    plan.base_revision_vector[f"section:{broken_target.section_id}"] = (
        vector[f"section:{broken_target.section_id}"]
    )

    # Base course revision: sibling insert (relocates op-1) + edit of op-2 target.
    document.blocks.append(CourseBlock(
        block_id="new-sibling-block",
        section_id=intact.section_id,
        position=intact.position + 1,
        kind="callout",
        role="summary",
        payload={"markdown": "new base course content"},
    ))
    broken_target.payload["markdown"] = "rewritten by the teacher"
    updated = refresh_document_revision(document)
    current_vector = revision_vector_for_document(updated).revisions

    overlay = personal_course_overlay(state, current_revision_vector=current_vector)

    assert overlay.resolution_status == "partially_active"
    # op-1 relocated and kept; op-2 conflicted and surfaced. Neither vanished.
    assert [item.operation_id for item in overlay.operations] == ["legacy-operation-1"]
    assert [item["operation_id"] for item in overlay.relocations] == ["legacy-operation-1"]
    assert [item["operation_id"] for item in overlay.conflicts] == ["legacy-operation-2"]
    assert overlay.conflicts[0]["reason"] == "target_block_revision_changed"
