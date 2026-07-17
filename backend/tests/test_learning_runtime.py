from __future__ import annotations

from copy import deepcopy

import learning_progress
import learning_runtime
from learning_progress import project_learning_objective_bindings
from routers.learning_assets import _project_checklist


def _course() -> dict:
    return {
        "course_id": "c1",
        "current_course_version_id": "cv1",
        "nodes": [
            {"node_id": "ch1", "node_name": "第一章", "node_level": 1, "parent_node_id": "root"},
            {
                "node_id": "n1",
                "node_name": "向量",
                "node_level": 2,
                "parent_node_id": "ch1",
                "node_content": "向量同时具有大小和方向。",
                "learning_objective": "能够解释向量的大小与方向",
            },
        ],
        "learning_assets": {
            "questions": [{
                "asset_id": "q1",
                "revision_id": "qr1",
                "node_id": "n1",
                "practice_level": "mastery_check",
                "mastery_criterion_ids": ["mc1"],
            }],
            "mastery_criteria": [{
                "criterion_id": "mc1",
                "revision_id": "mcr1",
                "node_id": "n1",
                "observable_performance": "解释大小与方向",
                "assessment_bindings": ["qr1"],
            }],
            "checklist": [{
                "asset_id": "cl1",
                "revision_id": "clr1",
                "node_id": "n1",
                "criterion_revision_id": "mcr1",
                "label": "能够解释大小与方向",
                "status": "not_started",
            }],
        },
    }


class _Repository:
    def __init__(self, value):
        self.value = value

    def list(self, *_args):
        return deepcopy(self.value)

    def load(self, *_args):
        return deepcopy(self.value)


def test_runtime_projects_progress_task_and_continuation_from_one_source_batch(monkeypatch):
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    events = [{
        "event_id": "evt1",
        "schema_version": 6,
        "event_type": "node_learning_started",
        "user_id": "u1",
        "course_id": "c1",
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
    }]
    attempts = [{
        "attempt_id": "pa2",
        "revision": 3,
        "status": "in_progress",
        "user_id": "u1",
        "course_id": "c1",
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "task_revision_id": "qr1",
        "question_revision_id": "qr1",
        "criterion_revision_id": "mcr1",
        "task_purpose": "course_practice",
        "answer_payload": {"text": "草稿"},
    }]
    snapshot = {
        "snapshot_id": "ls1",
        "revision": 4,
        "course_version_id": "cv1",
        "node_id": "n1",
        "content_anchor": None,
        "task_state": {"kind": "practice", "object_id": "pa2", "task_revision_id": "qr1"},
    }
    monkeypatch.setattr(learning_runtime, "load_learning_events", lambda **_kwargs: deepcopy(events))
    monkeypatch.setattr(learning_runtime, "practice_attempt_repository", _Repository(attempts))
    monkeypatch.setattr(learning_runtime, "learning_snapshot_repository", _Repository(snapshot))
    monkeypatch.setattr(learning_runtime, "learning_record_repository", _Repository([]))
    monkeypatch.setattr(
        learning_runtime,
        "workflow_view",
        lambda *_args, **_kwargs: {"phase": "practice", "case": None, "session": None, "current_task": None},
    )

    runtime = learning_runtime.build_learning_runtime(course, user_id="u1", node_id="n1")

    assert runtime["progress"]["nodes"][0]["reading_status"] == "in_progress"
    assert runtime["practice"]["active"][0]["attempt_id"] == "pa2"
    assert runtime["continuation"]["primary_action"]["action_type"] == "resume_practice_attempt"
    assert runtime["active_task"]["object_id"] == "pa2"
    assert runtime["active_task"]["task_revision_id"] == "qr1"
    assert runtime["revision_vector"]["snapshot_revision"] == 4
    assert runtime["course_availability"]["mode"] == "standard"
    assert runtime["course_availability"]["capabilities"]["practice"]["status"] == "available"


def test_mastery_checklist_reads_current_practice_attempt(monkeypatch):
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    attempts = [{
        "attempt_id": "pa1",
        "status": "graded",
        "user_id": "u1",
        "course_id": "c1",
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "task_revision_id": "qr1",
        "question_revision_id": "qr1",
        "criterion_revision_id": "mcr1",
        "task_purpose": "course_practice",
        "result": {"score": 100, "passed": True, "mastery_eligible": True},
    }]
    monkeypatch.setattr(learning_progress, "practice_attempt_repository", _Repository(attempts))
    monkeypatch.setattr(learning_progress, "load_learning_events", lambda **_kwargs: [])

    projected = _project_checklist(
        course,
        course["learning_assets"]["checklist"],
        user_id="u1",
    )

    assert projected[0]["status"] == "system_verified"
    assert projected[0]["latest_score"] == 100
    assert projected[0]["evidence_event_id"] == "pa1"


def test_runtime_projects_one_traceable_adaptive_block_for_confirmed_gap():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    case = {
        "diagnostic_case_id": "dc1",
        "status": "remediating",
        "node_id": "n1",
        "objective_revision_id": objective["objective_revision_id"],
        "trigger_attempt_ids": ["a1", "a2"],
        "confirmed_hypothesis_id": "h1",
        "hypotheses": [{"hypothesis_id": "h1", "status": "confirmed", "claim": "混淆大小与方向"}],
    }
    session = {
        "remediation_session_id": "rs1",
        "objective_revision_id": objective["objective_revision_id"],
        "unit": {
            "revision_id": "ru1",
            "micro_explanation": "分别检查大小和方向。",
            "worked_contrast": "比较同向与反向向量。",
            "content_block_ids": ["b1"],
        },
    }
    blocks = learning_runtime._adaptive_blocks(
        course,
        attempts=[],
        workflow={"phase": "remediation", "case": case, "session": session, "current_task": None},
        events=[],
        requested_node_id="n1",
    )

    assert len(blocks) == 1
    assert blocks[0]["kind"] == "counterexample"
    assert blocks[0]["anchor"] == {"node_id": "n1", "content_block_id": "b1", "placement": "after_block"}
    assert blocks[0]["reason_code"] == "confirmed_gap_under_remediation"
    assert blocks[0]["evidence_refs"] == ["a1", "a2", "dc1", "rs1"]
    assert blocks[0]["status"] == "active"
    assert blocks[0]["expires_at"]


def test_dismissed_adaptive_block_is_not_projected_again():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    workflow = {
        "phase": "needs_support",
        "case": {
            "diagnostic_case_id": "dc1",
            "status": "unresolved",
            "node_id": "n1",
            "objective_revision_id": objective["objective_revision_id"],
            "trigger_attempt_ids": ["a1", "a2"],
        },
        "session": None,
        "current_task": None,
    }
    first = learning_runtime._adaptive_blocks(
        course, attempts=[], workflow=workflow, events=[], requested_node_id="n1",
    )[0]
    events = [{
        "event_type": "adaptive_block_feedback",
        "metadata": {"adaptive_block_id": first["adaptive_block_id"]},
        "result": {"feedback": "dismissed"},
    }]

    assert learning_runtime._adaptive_blocks(
        course, attempts=[], workflow=workflow, events=events, requested_node_id="n1",
    ) == []


def test_adaptive_block_interaction_is_recorded_as_effect_evidence(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import learning_runtime as runtime_router

    recorded = []

    async def existing_course(_course_id: str):
        return {"course_id": "c1", "current_course_version_id": "cv1"}

    monkeypatch.setattr(runtime_router, "get_course_or_404", existing_course)
    monkeypatch.setattr(runtime_router, "build_learning_runtime", lambda *_args, **_kwargs: {
        "runtime_revision_id": "runtime-1",
        "adaptive_blocks": [{
            "adaptive_block_id": "block-1",
            "kind": "animation",
            "reason_code": "accepted_evidence_driven_growth",
            "evidence_refs": ["e1", "e2", "e3"],
        }],
    })

    def record(**payload):
        recorded.append(payload)
        return {"event_id": "event-interaction"}

    monkeypatch.setattr(runtime_router, "record_learning_event", record)
    app = FastAPI()
    app.include_router(runtime_router.router, prefix="/api")
    response = TestClient(app, headers={"X-User-Id": "student-a"}).post(
        "/api/courses/c1/learning-runtime/adaptive-blocks/interactions",
        json={
            "adaptive_block_id": "block-1",
            "node_id": "n1",
            "interaction": "animation_played",
        },
    )

    assert response.status_code == 200
    assert response.json()["interaction"] == "animation_played"
    assert recorded[0]["event_type"] == "adaptive_block_interaction"
    assert recorded[0]["result"] == {"interaction": "animation_played"}
    assert recorded[0]["metadata"]["adaptive_block_id"] == "block-1"


def test_formal_course_evolution_block_interaction_remains_effect_evidence(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import learning_runtime as runtime_router

    recorded = []
    course = {
        "course_id": "c1",
        "current_course_version_id": "cv2",
        "nodes": [{
            "node_id": "n1",
            "course_blocks": [{
                "block_id": "course-growth-1",
                "kind": "diagram",
                "evidence_refs": ["e1", "e2", "e3"],
                "payload": {
                    "course_evolution": {
                        "operation_id": "operation-1",
                        "change_set_id": "plan-1",
                    },
                },
            }],
        }],
    }

    async def existing_course(_course_id: str):
        return deepcopy(course)

    monkeypatch.setattr(runtime_router, "get_course_or_404", existing_course)
    monkeypatch.setattr(runtime_router, "build_learning_runtime", lambda *_args, **_kwargs: {
        "runtime_revision_id": "runtime-2",
        "adaptive_blocks": [],
    })

    def record(**payload):
        recorded.append(payload)
        return {"event_id": "event-formal-interaction"}

    monkeypatch.setattr(runtime_router, "record_learning_event", record)
    app = FastAPI()
    app.include_router(runtime_router.router, prefix="/api")
    response = TestClient(app, headers={"X-User-Id": "student-a"}).post(
        "/api/courses/c1/learning-runtime/adaptive-blocks/interactions",
        json={
            "adaptive_block_id": "operation-1",
            "node_id": "n1",
            "interaction": "animation_played",
        },
    )

    assert response.status_code == 200
    assert recorded[0]["source"] == "learning_runtime.course_evolution_block"
    assert recorded[0]["entity_type"] == "course_evolution_block"
    assert recorded[0]["evidence"] == {"evidence_refs": ["e1", "e2", "e3"]}
