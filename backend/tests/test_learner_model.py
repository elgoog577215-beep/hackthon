from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import learning_events
from learner_model import build_learner_model, is_model_item_current
from routers import learner_model as learner_model_router


class MemoryStorage:
    def __init__(self):
        self.data: dict[str, object] = {}

    def load_data(self, filename: str):
        return self.data.get(filename)

    def save_data(self, filename: str, data):
        self.data[filename] = data


def _progress(*, reading: str = "not_started", mastery: str = "not_checked") -> dict:
    return {
        "nodes": [{
            "objective_id": "obj-1",
            "objective_revision_id": "objr-1",
            "node_id": "node-1",
            "node_name": "向量",
            "statement": "能够解释向量的大小与方向",
            "reading_status": reading,
            "mastery_status": mastery,
            "evidence_event_ids": [],
            "has_historical_evidence": False,
        }],
    }


def _build(**overrides):
    payload = {
        "course_data": {"course_id": "course-1", "current_course_version_id": "cv1"},
        "user_id": "u1",
        "events": [],
        "snapshot": None,
        "records": [],
        "attempts": [],
        "workflow": {},
        "progress": _progress(),
        "source_revision_vector": {"events_revision": "e0", "attempts_revision": "a0"},
    }
    payload.update(overrides)
    return build_learner_model(**payload)


def test_model_is_deterministic_and_does_not_infer_from_one_page_open():
    event = {
        "event_id": "evt-open",
        "event_type": "node_learning_started",
        "actor": "user",
        "course_id": "course-1",
        "node_id": "node-1",
        "objective_revision_id": "objr-1",
        "created_at": "2026-07-14T08:00:00+00:00",
        "result": {"reading_status": "in_progress"},
    }
    progress = _progress(reading="in_progress")
    progress["nodes"][0]["evidence_event_ids"] = ["evt-open"]

    first = _build(events=[event], progress=progress, source_revision_vector={"events_revision": "e1"})
    second = _build(events=[event], progress=progress, source_revision_vector={"events_revision": "e1"})

    assert first == second
    assert first["model_revision_id"] == second["model_revision_id"]
    assert first["data_sufficiency"]["level"] == "limited"
    assert first["objectives"][0]["support_need"]["status"] == "none"
    assert first["strengths"] == []
    assert first["needs_attention"] == []


def test_model_keeps_formal_mastery_and_support_evidence_explainable():
    attempt = {
        "attempt_id": "attempt-1",
        "course_id": "course-1",
        "course_version_id": "cv1",
        "node_id": "node-1",
        "objective_revision_id": "objr-1",
        "status": "graded",
        "revision": 3,
        "created_at": "2026-07-14T08:00:00+00:00",
        "updated_at": "2026-07-14T08:05:00+00:00",
        "result": {"passed": True, "grading_confidence": 0.95, "support_level": 0},
    }

    model = _build(
        attempts=[attempt],
        progress=_progress(reading="learned", mastery="mastered"),
        source_revision_vector={"attempts_revision": "a1"},
    )

    objective = model["objectives"][0]
    assert objective["mastery_status"] == "mastered"
    assert objective["confidence"] == "high"
    assert objective["evidence_refs"][0]["source_id"] == "attempt-1"
    assert model["strengths"][0]["reason_code"] == "formally_mastered"
    assert model["model_policy"]["ai_writable"] is False


def test_model_projects_objective_evidence_to_formal_knowledge_without_rewriting_library():
    course = {
        "course_id": "course-1",
        "course_name": "线性代数",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": "高斯消元",
            "key_points": ["高斯消元法步骤与行简化阶梯形"],
            "grounding_contract": {},
        }],
    }
    attempt = {
        "attempt_id": "attempt-knowledge",
        "course_id": "course-1",
        "course_version_id": "cv1",
        "node_id": "node-1",
        "objective_revision_id": "objr-1",
        "skill_unit_ids": ["skill.la.system.augmented.elimination"],
        "mistake_point_ids": ["mistake.la.gaussian-zero-pivot"],
        "status": "graded",
        "created_at": "2026-07-14T08:00:00+00:00",
        "updated_at": "2026-07-14T08:05:00+00:00",
        "result": {"passed": True, "grading_confidence": 0.95, "support_level": 0},
    }

    model = _build(
        course_data=course,
        attempts=[attempt],
        progress=_progress(reading="learned", mastery="mastered"),
        source_revision_vector={"attempts_revision": "knowledge-a1"},
    )

    assert "math.la.system.gaussian_elimination.forward" in model["objectives"][0]["knowledge_ids"]
    state = next(
        item for item in model["knowledge_states"]
        if item["knowledge_id"] == "math.la.system.gaussian_elimination.forward"
    )
    assert state["status"] == "mastered"
    assert state["evidence_refs"][0]["source_id"] == "attempt-knowledge"
    skill_state = next(
        item for item in model["skill_states"]
        if item["skill_unit_id"] == "skill.la.system.augmented.elimination"
    )
    assert skill_state["status"] == "mastered"
    assert model["mistake_signals"] == []
    assert model["knowledge_coordinate"]["knowledge_library_id"] == "math.linear_algebra.v1"
    assert model["model_policy"]["personal_state_can_modify_library"] is False


def test_model_only_projects_confirmed_diagnostic_mistake_signal():
    workflow = {
        "case": {
            "diagnostic_case_id": "dc-1",
            "node_id": "node-1",
            "updated_at": "2026-07-14T08:10:00+00:00",
            "hypotheses": [{
                "hypothesis_id": "hyp-1",
                "status": "confirmed",
                "confidence_level": "high",
                "skill_unit_ids": ["skill.la.system.augmented.elimination"],
                "confirmed_mistake_point_ids": ["mistake.la.gaussian-zero-pivot"],
                "evidence_for": [
                    {"attempt_id": "attempt-1", "kind": "formal_failure"},
                    {"attempt_id": "probe-1", "kind": "independent_probe_fail"},
                ],
            }],
        },
    }

    model = _build(workflow=workflow, source_revision_vector={"workflow_revision": "w1"})

    assert model["mistake_signals"][0]["mistake_point_id"] == "mistake.la.gaussian-zero-pivot"
    assert len(model["mistake_signals"][0]["evidence_refs"]) == 2


def test_ungraded_attempt_is_not_counted_as_formal_evidence():
    attempt = {
        "attempt_id": "attempt-pending",
        "course_id": "course-1",
        "course_version_id": "cv1",
        "node_id": "node-1",
        "objective_revision_id": "objr-1",
        "status": "submitted",
        "revision": 1,
        "created_at": "2026-07-14T08:00:00+00:00",
        "updated_at": "2026-07-14T08:00:00+00:00",
        "result": {},
    }

    model = _build(attempts=[attempt], source_revision_vector={"attempts_revision": "a-pending"})

    assert model["data_sufficiency"]["formal_evidence_count"] == 0
    assert model["objectives"][0]["confidence"] == "low"


def test_model_validity_is_consumed_without_rewriting_the_model_revision():
    expired = {"valid_until": "2000-01-01T00:00:00+00:00"}
    current = {"valid_until": "2999-01-01T00:00:00+00:00"}

    assert is_model_item_current(expired) is False
    assert is_model_item_current(current) is True


def test_learning_event_idempotency_links_one_semantic_operation(monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)

    first = learning_events.record_learning_event(
        event_type="learning_record_created",
        source="test.records",
        user_id="u1",
        course_id="course-1",
        idempotency_key="record-1:revision-1",
        operation_id="operation-1",
        entity_type="learning_record",
        entity_id="record-1",
        entity_revision=1,
    )
    second = learning_events.record_learning_event(
        event_type="learning_record_created",
        source="test.records",
        user_id="u1",
        course_id="course-1",
        idempotency_key="record-1:revision-1",
        operation_id="operation-1",
        entity_type="learning_record",
        entity_id="record-1",
        entity_revision=1,
    )

    assert first["event_id"] == second["event_id"]
    assert first["operation_id"] == "operation-1"
    assert len(learning_events.load_learning_events(user_id="u1", course_id="course-1")) == 1


def test_learner_model_api_rejects_shared_default_identity(monkeypatch):
    async def fake_course(_course_id: str):
        return {"course_id": "course-1", "nodes": []}

    monkeypatch.setattr(learner_model_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(learner_model_router, "_build_model", lambda course, user_id: {
        "course_id": course["course_id"],
        "user_id": user_id,
    })
    app = FastAPI()
    app.include_router(learner_model_router.router, prefix="/api")
    client = TestClient(app)

    missing = client.get("/api/courses/course-1/learner-model")
    shared = client.get("/api/courses/course-1/learner-model", headers={"X-User-Id": "default_user"})
    isolated = client.get("/api/courses/course-1/learner-model", headers={"X-User-Id": "u1"})

    assert missing.status_code == 400
    assert shared.status_code == 400
    assert isolated.status_code == 200
    assert isolated.json()["user_id"] == "u1"
