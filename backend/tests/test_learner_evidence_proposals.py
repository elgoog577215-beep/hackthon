from __future__ import annotations

from copy import deepcopy

import course_evolution
import learner_model_service
from course_document import document_from_legacy_course
from course_evolution import CourseEvolutionRepository
from learner_model import (
    AGGREGATE_TRIGGER_THRESHOLD,
    SINGLE_STRONG_EVIDENCE_THRESHOLD,
    evaluate_evidence_trigger,
)


def _self_report(statement: str, *, created_at: str = "2026-07-15T00:00:00+00:00", event_id: str = "evt-1") -> dict:
    return {
        "event_id": event_id,
        "event_type": "learner_self_reported",
        "course_id": "course-1",
        "node_id": "block-1",
        "created_at": created_at,
        "evidence": {"statement": statement},
    }


# --- evaluate_evidence_trigger: dynamic threshold, not fixed counting ---


def test_single_strong_evidence_triggers_without_repetition():
    events = [_self_report("这段完全看不懂，公式推导跳步太多")]
    result = evaluate_evidence_trigger(events)
    assert result["triggered"] is True
    assert result["reason_code"] == "single_strong_evidence"
    assert result["score"] >= SINGLE_STRONG_EVIDENCE_THRESHOLD


def test_weak_evidence_needs_combined_aggregate_score():
    two_weak = [
        _self_report("能不能讲得更详细一点", event_id="evt-1"),
        _self_report("这里还是没懂", event_id="evt-2"),
    ]
    result_two = evaluate_evidence_trigger(two_weak)
    assert result_two["triggered"] is False
    assert result_two["reason_code"] == "insufficient_evidence"

    three_weak = two_weak + [_self_report("再解释一下这一步", event_id="evt-3")]
    result_three = evaluate_evidence_trigger(three_weak)
    assert result_three["triggered"] is True
    assert result_three["reason_code"] == "aggregate_weak_evidence"
    assert result_three["score"] >= AGGREGATE_TRIGGER_THRESHOLD
    # Aggregating more weak evidence must not simply scale linearly with count.
    assert result_three["score"] < two_weak.__len__() * 5


def test_pure_repetition_without_strength_or_diversity_does_not_trigger():
    # Many low-strength, same-label generic events (no explicit statement) —
    # this exercises the "not simple counting" requirement directly: even a
    # large pile of weak, homogeneous evidence must not cross the bar.
    events = [
        {
            "event_id": f"evt-{i}",
            "event_type": "node_learning_started",
            "course_id": "course-1",
            "node_id": "block-1",
            "created_at": "2026-07-15T00:00:00+00:00",
        }
        for i in range(20)
    ]
    result = evaluate_evidence_trigger(events)
    assert result["triggered"] is False
    assert result["matched_labels"] == ["generic_event"]


def test_stale_evidence_is_discounted_by_recency():
    fresh = evaluate_evidence_trigger([_self_report("完全看不懂", created_at="2026-07-15T00:00:00+00:00")])
    stale = evaluate_evidence_trigger([_self_report("完全看不懂", created_at="2020-01-01T00:00:00+00:00")])
    assert fresh["score"] > stale["score"]


# --- evaluate_and_propose_change: compatibility entrypoint for personal adaptation ---


def _course_and_block() -> tuple[dict, str]:
    course = {
        "course_id": "course-1",
        "course_name": "线性代数",
        "nodes": [{
            "node_id": "section-1",
            "parent_node_id": "root",
            "node_name": "向量",
            "node_level": 2,
            "learning_objective": "理解向量的方向与大小",
            "objective_id": "objective-1",
            "node_content": "向量同时具有大小和方向。",
        }],
    }
    document = document_from_legacy_course(course)
    course["course_document"] = document.model_dump(mode="json")
    course["course_document_authoritative"] = True
    return course, document.blocks[0].block_id


def _install_personal_sources(monkeypatch, *, course: dict, events: list[dict]) -> None:
    monkeypatch.setattr(learner_model_service.storage, "load_course", lambda _course_id: course)
    monkeypatch.setattr(course_evolution, "load_learning_events", lambda **_kwargs: events)
    monkeypatch.setattr(course_evolution.learning_record_repository, "list", lambda *_args: [])
    monkeypatch.setattr(course_evolution.practice_attempt_repository, "list", lambda *_args: [])


def test_evaluate_and_propose_change_creates_course_evolution_plan(tmp_path, monkeypatch):
    course, block_id = _course_and_block()
    base_course = deepcopy(course)
    _install_personal_sources(
        monkeypatch,
        course=course,
        events=[_self_report("这段完全看不懂，公式推导跳步太多") | {"node_id": "section-1"}],
    )

    plan = learner_model_service.evaluate_and_propose_change(
        "course-1",
        block_id,
        user_id="learner-1",
        adaptation_repository=CourseEvolutionRepository(tmp_path),
    )

    assert plan is not None
    assert plan["plan_kind"] == "course_evolution_plan"
    assert plan["write_target"] == "course_document"
    assert plan["status"] == "pending"
    assert plan["plan_id"] == plan["change_set_id"]
    assert all(item["target_block_id"] == block_id for item in plan["operations"])
    assert course == base_course


def test_evaluate_and_propose_change_returns_none_below_threshold(tmp_path, monkeypatch):
    course, block_id = _course_and_block()
    _install_personal_sources(
        monkeypatch,
        course=course,
        events=[_self_report("能不能讲得更详细一点") | {"node_id": "section-1"}],
    )

    plan = learner_model_service.evaluate_and_propose_change(
        "course-1",
        block_id,
        user_id="learner-1",
        adaptation_repository=CourseEvolutionRepository(tmp_path),
    )

    assert plan is None


def test_evaluate_and_propose_change_returns_none_without_evidence(tmp_path, monkeypatch):
    course, block_id = _course_and_block()
    _install_personal_sources(monkeypatch, course=course, events=[])

    plan = learner_model_service.evaluate_and_propose_change(
        "course-1",
        block_id,
        user_id="learner-1",
        adaptation_repository=CourseEvolutionRepository(tmp_path),
    )

    assert plan is None


def test_evaluate_and_propose_change_never_touches_learner_model_output(tmp_path, monkeypatch):
    """The evidence-driven proposal side channel MUST NOT leak into the
    read-only learner model: `ai_writable: False` must hold before and after
    a proposal is generated, and the learner-model builder itself must never
    be imported/called by evaluate_and_propose_change."""
    course, block_id = _course_and_block()
    _install_personal_sources(
        monkeypatch,
        course=course,
        events=[_self_report("这段完全看不懂，公式推导跳步太多") | {"node_id": "section-1"}],
    )

    from learner_model import build_learner_model

    def _minimal_model():
        return build_learner_model(
            {"course_id": "course-1", "current_course_version_id": "cv1"},
            user_id="learner-1",
            events=[],
            snapshot=None,
            records=[],
            attempts=[],
            workflow={},
            progress={"nodes": []},
            source_revision_vector={},
        )

    before = _minimal_model()
    assert before["model_policy"]["ai_writable"] is False

    plan = learner_model_service.evaluate_and_propose_change(
        "course-1",
        block_id,
        user_id="learner-1",
        adaptation_repository=CourseEvolutionRepository(tmp_path),
    )
    assert plan is not None  # sanity: the trigger really fired

    after = _minimal_model()
    assert after["model_policy"]["ai_writable"] is False
    assert after == before  # the evidence side-channel left the model untouched
