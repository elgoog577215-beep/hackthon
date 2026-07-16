from __future__ import annotations

from copy import deepcopy

import course_evolution
from course_document import document_from_legacy_course
from course_evolution import (
    CourseEvolutionRepository,
    accept_change_set,
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
    student_b = repository.load("student-b", course["course_id"])

    assert len(student_a_blocks) > 3
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
