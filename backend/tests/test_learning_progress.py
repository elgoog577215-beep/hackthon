from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

import learning_events
from learning_progress import (
    build_learning_progress,
    project_learning_objective_bindings,
)
from routers import learning_progress as progress_router
from routers import learning_assets as assets_router


class MemoryDataStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def _course(objective="能够解释向量"):
    return {
        "course_id": "c1",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量",
            "learning_objective": objective,
            "node_content": "# 向量\n\n## 定义\n\n向量具有大小与方向。",
        }],
        "learning_assets": {
            "questions": [{
                "node_id": "n1",
                "revision_id": "qr_1",
                "prompt": "解释向量",
            }],
            "mastery_criteria": [{
                "node_id": "n1",
                "criterion_id": "mc_1",
                "revision_id": "mcr_1",
                "observable_performance": "能解释向量",
                "assessment_bindings": ["qr_1"],
            }],
            "misconceptions": [{
                "node_id": "n1",
                "revision_id": "misr_1",
                "error_pattern": "把向量当标量",
            }],
            "checklist": [{
                "node_id": "n1",
                "criterion_revision_id": "mcr_1",
                "revision_id": "checkr_1",
                "label": "能解释向量",
            }],
        },
    }


def _event(event_type, objective, *, user_id="u1", result=None, criterion_revision_id=None):
    return {
        "event_id": f"evt_{event_type}_{user_id}",
        "event_type": event_type,
        "user_id": user_id,
        "course_id": "c1",
        "node_id": "n1",
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "criterion_revision_id": criterion_revision_id,
        "result": result or {},
    }


def test_objective_identity_is_stable_and_revision_changes_with_statement():
    first = project_learning_objective_bindings(_course())
    second = project_learning_objective_bindings(_course("能够推导并解释向量"))
    first_objective = first["learning_objectives"][0]
    second_objective = second["learning_objectives"][0]

    assert first_objective["objective_id"] == second_objective["objective_id"]
    assert first_objective["objective_revision_id"] != second_objective["objective_revision_id"]
    assert first_objective["content_block_ids"]
    assert first_objective["question_revision_ids"] == ["qr_1"]
    assert first_objective["criterion_revision_ids"] == ["mcr_1"]
    assert first["learning_assets"]["questions"][0]["objective_id"] == first_objective["objective_id"]


def test_legacy_level_one_content_nodes_receive_objectives_without_double_counting():
    legacy = _course()
    legacy["nodes"][0]["node_level"] = 1
    projected = project_learning_objective_bindings(legacy)
    assert [item["node_id"] for item in projected["learning_objectives"]] == ["n1"]

    mixed = _course()
    mixed["nodes"].insert(0, {
        "node_id": "chapter",
        "node_level": 1,
        "node_name": "章节容器",
        "node_content": "章节导语",
    })
    projected_mixed = project_learning_objective_bindings(mixed)
    assert [item["node_id"] for item in projected_mixed["learning_objectives"]] == ["n1"]


def test_reading_and_mastery_states_are_independent_and_user_scoped():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]

    initial = build_learning_progress(course, user_id="u1", events=[])["nodes"][0]
    assert initial["reading_status"] == "not_started"
    assert initial["mastery_status"] == "not_checked"

    started = build_learning_progress(
        course,
        user_id="u1",
        events=[
            _event("node_learning_started", objective),
            _event("formal_question_answered", objective, user_id="u2", result={"passed": True}, criterion_revision_id="mcr_1"),
        ],
    )["nodes"][0]
    assert started["reading_status"] == "in_progress"
    assert started["mastery_status"] == "not_checked"

    learned = build_learning_progress(
        course,
        user_id="u1",
        events=[_event("node_learning_completed", objective)],
    )["nodes"][0]
    assert learned["reading_status"] == "learned"
    assert learned["mastery_status"] == "evidence_insufficient"


def test_self_confirmation_never_becomes_system_mastery():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    projected = build_learning_progress(
        course,
        user_id="u1",
        events=[_event(
            "mastery_self_confirmed",
            objective,
            result={"status": "self_confirmed"},
            criterion_revision_id="mcr_1",
        )],
    )["nodes"][0]

    assert projected["reading_status"] == "in_progress"
    assert projected["mastery_status"] == "evidence_insufficient"


def test_latest_formal_result_controls_mastery_and_review():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    passed = _event(
        "formal_question_answered",
        objective,
        result={"score": 85, "passed": True},
        criterion_revision_id="mcr_1",
    )
    mastered = build_learning_progress(course, user_id="u1", events=[passed])["nodes"][0]
    assert mastered["mastery_status"] == "mastered"

    failed = {**passed, "event_id": "evt_failed", "result": {"score": 40, "passed": False}}
    needs_review = build_learning_progress(course, user_id="u1", events=[passed, failed])["nodes"][0]
    assert needs_review["mastery_status"] == "needs_review"


def test_independent_remediation_validation_can_restore_mastery():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    attempts = [
        {
            "attempt_id": "formal-fail",
            "user_id": "u1",
            "course_id": "c1",
            "objective_id": objective["objective_id"],
            "objective_revision_id": objective["objective_revision_id"],
            "criterion_revision_id": "mcr_1",
            "question_revision_id": "qr_1",
            "task_purpose": "course_practice",
            "status": "graded",
            "result": {"passed": False, "score": 0, "mastery_eligible": False},
        },
        {
            "attempt_id": "validation-pass",
            "user_id": "u1",
            "course_id": "c1",
            "objective_id": objective["objective_id"],
            "objective_revision_id": objective["objective_revision_id"],
            "criterion_revision_id": "mcr_1",
            "question_revision_id": "validation-revision",
            "task_purpose": "remediation_validation",
            "status": "graded",
            "result": {"passed": True, "score": 100, "mastery_eligible": True, "support_level": 0},
        },
    ]

    node = build_learning_progress(course, user_id="u1", events=[], attempts=attempts)["nodes"][0]

    assert node["mastery_status"] == "mastered"
    assert node["criterion_states"][0]["evidence_event_id"] == "validation-pass"


def test_old_task_and_criterion_revisions_are_historical_not_current_mastery():
    course = project_learning_objective_bindings(_course())
    course["current_course_version_id"] = "cv2"
    objective = course["learning_objectives"][0]
    course["learning_assets"]["questions"][0]["revision_id"] = "qr_2"
    course["learning_assets"]["mastery_criteria"][0]["revision_id"] = "mcr_2"
    course["learning_assets"]["mastery_criteria"][0]["assessment_bindings"] = ["qr_2"]
    course = project_learning_objective_bindings(course)
    old_attempt = {
        "attempt_id": "old-pass",
        "user_id": "u1",
        "course_id": "c1",
        "course_version_id": "cv1",
        "objective_id": objective["objective_id"],
        "objective_revision_id": objective["objective_revision_id"],
        "question_revision_id": "qr_1",
        "criterion_revision_id": "mcr_1",
        "task_purpose": "course_practice",
        "status": "graded",
        "result": {"passed": True, "score": 100, "mastery_eligible": True},
    }

    node = build_learning_progress(course, user_id="u1", events=[], attempts=[old_attempt])["nodes"][0]

    assert node["mastery_status"] == "not_checked"
    assert node["practice_attempt_ids"] == []
    assert node["has_historical_evidence"] is True
    assert node["historical_evidence_count"] == 1


def test_old_objective_revision_is_retained_but_not_counted():
    old_course = project_learning_objective_bindings(_course())
    old_objective = old_course["learning_objectives"][0]
    current_course = project_learning_objective_bindings(_course("能够推导并解释向量"))
    projected = build_learning_progress(
        current_course,
        user_id="u1",
        events=[_event(
            "formal_question_answered",
            old_objective,
            result={"passed": True},
            criterion_revision_id=None,
        )],
    )["nodes"][0]

    assert projected["mastery_status"] == "not_checked"
    assert projected["has_historical_evidence"] is True


def test_legacy_completion_only_migrates_to_in_progress():
    course = project_learning_objective_bindings(_course())
    objective = course["learning_objectives"][0]
    projected = build_learning_progress(
        course,
        user_id="u1",
        events=[_event("legacy_node_completion_imported", objective)],
    )["nodes"][0]

    assert projected["reading_status"] == "in_progress"
    assert projected["mastery_status"] == "not_checked"


def test_progress_api_actions_and_legacy_migration_are_idempotent(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(progress_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(progress_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    start = client.post("/api/courses/c1/learning-progress/nodes/n1", json={"action": "start"})
    repeat = client.post("/api/courses/c1/learning-progress/nodes/n1", json={"action": "start"})
    assert start.status_code == 200
    assert start.json()["projection"]["nodes"][0]["reading_status"] == "in_progress"
    assert repeat.json()["status"] == "existing"

    complete = client.post("/api/courses/c1/learning-progress/nodes/n1", json={"action": "complete_reading"})
    assert complete.json()["projection"]["nodes"][0]["reading_status"] == "learned"

    migrate = client.post("/api/courses/c1/learning-progress/migrate-legacy", json={"node_ids": ["n1", "n1"]})
    migrate_again = client.post("/api/courses/c1/learning-progress/migrate-legacy", json={"node_ids": ["n1"]})
    assert migrate.json()["created"] == 1
    assert migrate_again.json()["created"] == 0


def test_mastery_confirmation_records_current_objective_revision(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(assets_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(assets_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    response = client.post(
        "/api/courses/c1/learning-assets/criteria/mcr_1/confirm",
        json={"confirmed": True},
    )

    assert response.status_code == 200
    event = learning_events.load_learning_events(course_id="c1")[-1]
    objective = project_learning_objective_bindings(_course())["learning_objectives"][0]
    assert event["objective_id"] == objective["objective_id"]
    assert event["objective_revision_id"] == objective["objective_revision_id"]
