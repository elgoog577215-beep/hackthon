from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.requests import Request

import course_evolution
import learning_events
from course_versions import CourseVersionRepository
from models import ReviewResult, SubmitReviewRequest
from routers import review


class MemoryDataStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def test_formal_answer_event_keeps_course_and_asset_revisions(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)

    event = learning_events.record_learning_event(
        event_type="formal_question_answered",
        course_id="c1",
        course_version_id="cv3",
        node_id="n1",
        objective_id="lo_1",
        objective_revision_id="lor_1",
        concept_ids=["concept_1"],
        skill_unit_ids=["skill_1"],
        mistake_point_ids=["mistake_1"],
        improvement_point_ids=["improve_1"],
        question_revision_id="qr_1",
        task_revision_id="task_1",
        task_purpose="course_practice",
        criterion_id="mc_1",
        criterion_revision_id="mcr_1",
        diagnostic_case_id="dc_1",
        remediation_session_id="rs_1",
        result={"score": 80, "passed": True},
    )

    assert event["schema_version"] == 8
    assert event["course_version_id"] == "cv3"
    assert event["objective_id"] == "lo_1"
    assert event["objective_revision_id"] == "lor_1"
    assert event["skill_unit_ids"] == ["skill_1"]
    assert event["mistake_point_ids"] == ["mistake_1"]
    assert event["improvement_point_ids"] == ["improve_1"]
    assert event["question_revision_id"] == "qr_1"
    assert event["task_revision_id"] == "task_1"
    assert event["task_purpose"] == "course_practice"
    assert event["criterion_revision_id"] == "mcr_1"
    assert event["diagnostic_case_id"] == "dc_1"
    assert event["remediation_session_id"] == "rs_1"


def test_concurrent_event_appends_do_not_lose_facts(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)

    def append(index):
        return learning_events.record_learning_event(
            event_type="learning_record_created",
            course_id="c1",
            record_id=f"lr_{index}",
            record_type="note",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(40)))

    events = learning_events.load_learning_events(course_id="c1")
    assert len(events) == 40
    assert {event["record_id"] for event in events} == {f"lr_{index}" for index in range(40)}


def test_ai_question_immediately_refreshes_course_evolution_projection(monkeypatch):
    memory = MemoryDataStorage()
    memory.load_course = lambda course_id: {"course_id": course_id, "nodes": []}
    monkeypatch.setattr(learning_events, "storage", memory)
    evaluated = []
    monkeypatch.setattr(
        course_evolution,
        "synchronize_and_evaluate_course_evolution",
        lambda course, *, user_id: evaluated.append((course["course_id"], user_id)),
    )

    learning_events.record_learning_event(
        event_type="assistant_question_submitted",
        course_id="c1",
        user_id="student-a",
        node_id="n1",
        evidence={"question": "为什么是先做右边的变换？"},
    )

    assert evaluated == [("c1", "student-a")]


def test_legacy_course_learning_state_migration_is_idempotent(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)
    course = {
        "course_id": "c1",
        "current_course_version_id": "cv1",
        "nodes": [{"node_id": "n1", "node_name": "节点", "quiz_score": 75}],
        "review_history": {"n1": {"last_reviewed": "2026-01-01", "review_count": 2}},
    }

    assert learning_events.migrate_legacy_learning_state(course) == 2
    assert learning_events.migrate_legacy_learning_state(course) == 0
    assert len(learning_events.load_learning_events(course_id="c1")) == 2


@pytest.mark.asyncio
async def test_review_submission_only_appends_events(monkeypatch):
    memory = MemoryDataStorage()
    monkeypatch.setattr(learning_events, "storage", memory)
    course = {
        "course_id": "c1",
        "current_course_version_id": "cv2",
        "nodes": [{"node_id": "n1", "node_level": 2, "node_name": "节点"}],
    }

    async def fake_course(_course_id):
        return course

    monkeypatch.setattr(review, "get_course_or_404", fake_course)
    response = await review.submit_review_results(
        "c1",
        SubmitReviewRequest(
            course_id="c1",
            results=[ReviewResult(node_id="n1", quality=4, time_spent_seconds=30)],
        ),
        Request({"type": "http", "headers": [(b"x-user-id", b"u1")]}),
    )

    assert response["status"] == "recorded"
    assert "review_history" not in course
    event = learning_events.load_learning_events(course_id="c1")[-1]
    assert event["course_version_id"] == "cv2"
    assert event["event_type"] == "review_result_submitted"


def test_blueprint_revision_is_immutable(tmp_path):
    repository = CourseVersionRepository(tmp_path)
    course = {
        "course_id": "c1",
        "course_name": "课程",
        "nodes": [{"node_id": "n1", "node_level": 2, "node_name": "旧名称"}],
    }
    first = repository.freeze_blueprint("c1", course)
    course["nodes"][0]["node_name"] = "新名称"
    second = repository.freeze_blueprint("c1", course)

    assert first["blueprint_revision_id"] != second["blueprint_revision_id"]
    restored = repository.get_blueprint_revision("c1", first["blueprint_revision_id"])
    assert restored["nodes"][0]["node_name"] == "旧名称"
