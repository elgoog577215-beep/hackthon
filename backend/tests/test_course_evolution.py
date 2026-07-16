from __future__ import annotations

from copy import deepcopy

import course_evolution
import pytest
from course_document import document_from_legacy_course
from course_evolution import (
    CourseEvolutionRepository,
    accept_change_set,
    course_evolution_view,
    create_adjustment_plan,
    personal_course_overlay,
    project_applied_adaptive_blocks,
    synchronize_and_evaluate_course_evolution,
    undo_change_set,
)


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
    course["course_document_authoritative"] = True
    return course


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
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: [{
        "event_id": "event-dialogue",
        "event_type": "learner_self_reported",
        "course_id": document.course_id,
        "node_id": "section-1",
        "evidence": {"statement": "我会计算，但不理解为什么要这样乘，还是没懂"},
        "created_at": "2026-07-16T09:00:00+00:00",
    }])
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
    repository = CourseEvolutionRepository(tmp_path)

    state = synchronize_and_evaluate_course_evolution(
        course,
        user_id="student-a",
        repository=repository,
    )

    assert {item.source_type for item in state.evidence_items} == {
        "learning_event", "learning_record", "practice_attempt",
    }
    assert len(state.hypotheses) == 1
    hypothesis = state.hypotheses[0]
    assert hypothesis.status == "candidate_created"
    assert hypothesis.recommended_scope == "current_and_next"
    assert len(hypothesis.affected_block_ids) == 4
    change_set = state.change_sets[0]
    assert change_set.status == "pending"
    assert change_set.allowed_scopes == ["current", "current_and_next"]
    assert {item.operation_type for item in change_set.operations} >= {
        "INSERT_PERSONAL_SUPPORT", "ADD_ANIMATION", "ADD_CHECKPOINT", "ADD_TRANSITION_SUPPORT",
    }
    animation = next(item for item in change_set.operations if item.operation_type == "ADD_ANIMATION")
    assert animation.payload["animation_spec"]["schema_version"] == "animation_spec_v1"
    assert len(animation.payload["animation_spec"]["keyframes"]) == 3
    assert len(animation.payload["animation_spec"]["fallback_frames"]) == 3
    assert "基础课程" in change_set.impact_summary["protected"]


def test_acceptance_grows_only_the_selected_learner_course_and_can_be_undone(
    tmp_path,
    monkeypatch,
):
    course = _course()
    base_course = deepcopy(course)
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
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
    )
    student_a_blocks = project_applied_adaptive_blocks(applied)
    overlay = personal_course_overlay(applied)
    view = course_evolution_view(applied)
    student_b = repository.load("student-b", course["course_id"])

    assert len(student_a_blocks) > 3
    assert overlay.active_plan_ids == [change_set_id]
    assert overlay.operations
    assert view["adaptation_plans"][0]["plan_kind"] == "personal_adaptation_plan"
    assert view["personal_course_overlay"]["overlay_id"] == overlay.overlay_id
    assert view["permissions"] == {
        "write_target": "personal_overlay",
        "can_modify_base_course": False,
        "can_modify_other_learners": False,
        "can_modify_course_knowledge_base": False,
    }
    assert project_applied_adaptive_blocks(student_b) == []
    assert course == base_course

    undone = undo_change_set(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=change_set_id,
        repository=repository,
    )
    assert project_applied_adaptive_blocks(undone) == []


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
    plan = state.change_sets[0]
    assert question.anchor.knowledge_node_ids
    assert question.anchor.ability_point_ids
    assert question.anchor.misconception_point_ids
    assert plan.impact_summary["knowledge_labels"] == ["矩阵复合含义"]
    assert "解释复合顺序" in plan.impact_summary["ability_labels"]
    assert "把矩阵乘法只理解为行乘列" in plan.impact_summary["misconception_labels"]
    assert related.block_id in plan.impact_summary["dependent_block_ids"]
    assert plan.operations[3].target_block_id == related.block_id
    animation = next(item for item in plan.operations if item.operation_type == "ADD_ANIMATION")
    checkpoint = next(item for item in plan.operations if item.operation_type == "ADD_CHECKPOINT")
    assert animation.payload["animation_spec"]["knowledge_refs"] == plan.impact_summary["knowledge_node_ids"]
    assert checkpoint.payload["ability_refs"] == plan.impact_summary["ability_point_ids"]
    assert checkpoint.payload["expected_effect"]


def test_personal_adaptation_api_uses_overlay_without_mutating_base_course(
    tmp_path,
    monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import course_evolution as evolution_router

    course = _course()
    base_course = deepcopy(course)
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
    monkeypatch.setattr(course_evolution, "course_evolution_repository", repository)

    async def existing_course(_course_id: str):
        return course

    monkeypatch.setattr(evolution_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(evolution_router.personal_router, prefix="/api")
    client = TestClient(app)

    loaded = client.get(
        "/api/courses/course-growth/personal-adaptation",
        headers={"X-User-Id": "student-a"},
    )
    assert loaded.status_code == 200
    plan_id = loaded.json()["adaptation_plans"][0]["plan_id"]

    accepted = client.post(
        f"/api/courses/course-growth/personal-adaptation/plans/{plan_id}/accept",
        headers={"X-User-Id": "student-a"},
        json={"selected_scope": "current_and_next"},
    )

    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["personal_course_overlay"]["active_plan_ids"] == [plan_id]
    assert payload["permissions"]["can_modify_base_course"] is False
    assert course == base_course


def test_ineffective_adaptation_creates_reviewable_replacement_and_replaces_atomically(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
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
    assert source.effect_evaluation["follow_up_candidate"]["candidate_type"] == "adjust_personal_adaptation"

    adjusted = create_adjustment_plan(
        user_id="student-a",
        course_id=course["course_id"],
        change_set_id=source_id,
        repository=repository,
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
    )
    assert next(item for item in applied.change_sets if item.change_set_id == source_id).status == "undone"
    assert next(item for item in applied.change_sets if item.change_set_id == replacement.change_set_id).status == "applied"
    assert personal_course_overlay(applied).active_plan_ids == [replacement.change_set_id]


@pytest.mark.parametrize(("feedback", "later_results", "expected", "action"), [
    ("helpful", [True], "effective", "keep"),
    ("not_helpful", [False, False], "harmful", "rollback"),
    ("", [], "insufficient_evidence", "collect_more_evidence"),
])
def test_effect_evaluation_uses_later_learning_evidence_not_acceptance(
    tmp_path,
    monkeypatch,
    feedback,
    later_results,
    expected,
    action,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path / expected)
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
    if expected == "harmful":
        assert result.effect_evaluation["follow_up_candidate"]["candidate_type"] == "rollback_personal_adaptation"


def test_unrelated_later_success_cannot_prove_personal_adaptation_effective(
    tmp_path,
    monkeypatch,
):
    course = _course()
    document = document_from_legacy_course(course)
    _install_sources(monkeypatch, document)
    repository = CourseEvolutionRepository(tmp_path)
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
