from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import learning_events
from learning_progress import build_learning_progress, project_learning_objective_bindings
from practice_attempts import AttemptConflict, InvalidAttemptTransition, PracticeAttemptRepository
from practice_grading import PracticeGrader
from routers import practice as practice_router


class MemoryStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def _course():
    question = {
        "asset_id": "q1",
        "revision_id": "qr1",
        "node_id": "n1",
        "objective_id": "lo_placeholder",
        "objective_revision_id": "lor_placeholder",
        "question_type": "short_answer",
        "prompt": "解释向量的两个基本属性。",
        "answer_spec": {
            "type": "exact",
            "correct_answer": "大小和方向",
            "criteria": ["说明大小", "说明方向"],
            "pass_score": 70,
        },
    }
    criterion = {
        "criterion_id": "mc1",
        "revision_id": "mcr1",
        "node_id": "n1",
        "observable_performance": "能够说明向量的大小与方向",
        "assessment_bindings": ["qr1"],
    }
    return {
        "course_id": "c1",
        "course_name": "线性代数",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量",
            "learning_objective": "能够解释向量",
            "node_content": "向量具有大小与方向。",
        }],
        "learning_assets": {
            "questions": [question],
            "mastery_criteria": [criterion],
            "checklist": [],
            "misconceptions": [],
            "final_assessment": [],
        },
    }


def _payload(**extra):
    return {
        "question_revision_id": "qr1",
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": "lo1",
        "objective_revision_id": "lor1",
        "criterion_id": "mc1",
        "criterion_revision_id": "mcr1",
        "practice_level": "mastery_check",
        **extra,
    }


def test_attempt_repository_preserves_retries_and_rejects_stale_drafts(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    first, created = repository.create_once("u1", "c1", _payload(attempt_id="a1"))
    assert created is True
    saved = repository.update_draft(
        "u1", "c1", "a1", expected_revision=1, answer_payload={"text": "草稿"}, active_seconds=4
    )
    assert saved["revision"] == 2
    with pytest.raises(AttemptConflict):
        repository.update_draft(
            "u1", "c1", "a1", expected_revision=1, answer_payload={"text": "旧设备覆盖"}
        )

    submitted, changed = repository.submit(
        "u1",
        "c1",
        "a1",
        expected_revision=2,
        request_id="request-0001",
        answer_payload={"text": "大小和方向"},
        active_seconds=8,
    )
    assert changed is True
    graded = repository.apply_grade(
        "u1", "c1", "a1", expected_revision=submitted["revision"], result={"status": "graded", "passed": True}
    )
    assert graded["status"] == "graded"
    with pytest.raises(InvalidAttemptTransition):
        repository.update_draft(
            "u1", "c1", "a1", expected_revision=graded["revision"], answer_payload={"text": "覆盖历史"}
        )

    retry, retry_created = repository.create_once("u1", "c1", _payload(resume=False))
    assert retry_created is True
    assert retry["attempt_id"] != first["attempt_id"]
    assert retry["attempt_number"] == 2
    assert len(repository.list("u1", "c1")) == 2
    assert repository.list("u2", "c1") == []


def test_hint_levels_are_ordered_and_irreversible(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    attempt, _ = repository.create_once("u1", "c1", _payload())
    with pytest.raises(InvalidAttemptTransition):
        repository.reveal_hint(
            "u1", "c1", attempt["attempt_id"], expected_revision=1, level=2
        )
    first, created = repository.reveal_hint(
        "u1", "c1", attempt["attempt_id"], expected_revision=1, level=1
    )
    assert created is True
    duplicate, duplicate_created = repository.reveal_hint(
        "u1", "c1", attempt["attempt_id"], expected_revision=first["revision"], level=1
    )
    assert duplicate_created is False
    assert duplicate["revealed_hint_levels"] == [1]


def test_abandoned_attempt_is_preserved_and_cannot_be_edited(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    attempt, _ = repository.create_once("u1", "c1", _payload())
    abandoned = repository.abandon(
        "u1", "c1", attempt["attempt_id"], expected_revision=attempt["revision"]
    )
    assert abandoned["status"] == "abandoned"
    assert repository.list("u1", "c1")[0]["attempt_id"] == attempt["attempt_id"]
    with pytest.raises(InvalidAttemptTransition):
        repository.update_draft(
            "u1", "c1", attempt["attempt_id"],
            expected_revision=abandoned["revision"], answer_payload={"text": "覆盖"},
        )


def test_concurrent_attempt_creation_does_not_lose_records(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)

    def create(index: int):
        return repository.create_once(
            "u1",
            "c1",
            _payload(attempt_id=f"attempt-{index}", resume=False),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(40)))

    assert len(repository.list("u1", "c1")) == 40


@pytest.mark.asyncio
async def test_deterministic_grading_tracks_support_strength():
    grader = PracticeGrader()
    question = _course()["learning_assets"]["questions"][0]
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "大小和方向"},
        "revealed_hint_levels": [1],
        "ai_support_level": 0,
        "solution_revealed": False,
    })
    assert result["passed"] is True
    assert result["evidence_strength"] == "lightly_supported"
    assert result["mastery_eligible"] is True


@pytest.mark.asyncio
async def test_concept_check_never_becomes_mastery_evidence():
    grader = PracticeGrader()
    question = _course()["learning_assets"]["questions"][0]
    question["practice_level"] = "concept_check"
    question["validation_policy"] = {
        "mastery_eligible": False,
        "max_support_level_for_mastery": 1,
    }
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "大小和方向"},
        "revealed_hint_levels": [],
    })
    assert result["passed"] is True
    assert result["mastery_eligible"] is False


@pytest.mark.asyncio
async def test_open_rubric_without_provider_waits_for_review():
    grader = PracticeGrader()
    grader.client = None
    question = _course()["learning_assets"]["questions"][0]
    question["answer_spec"] = {"type": "rubric", "criteria": ["说明概念"], "pass_score": 70}
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "这是一个开放回答"},
        "revealed_hint_levels": [],
    })
    assert result["status"] == "pending_review"
    assert result["score"] is None
    assert result["mastery_eligible"] is False


def test_practice_api_resumes_submits_idempotently_and_projects_mastery(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    first = client.post("/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"})
    second = client.post("/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"})
    assert first.status_code == 200
    assert second.json()["status"] == "resumed"
    attempt = first.json()["attempt"]

    saved = client.patch(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/draft",
        json={"expected_revision": 1, "answer_payload": {"text": "大小和方向"}, "active_seconds": 12},
    )
    assert saved.status_code == 200
    submission = {
        "expected_revision": 2,
        "answer_payload": {"text": "大小和方向"},
        "active_seconds": 12,
        "request_id": "submit-0001",
    }
    submitted = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )
    repeated = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )
    assert submitted.status_code == 200
    assert submitted.json()["result"]["passed"] is True
    assert repeated.json()["status"] == "already_submitted"

    stored = repository.list("u1", "c1")
    course = project_learning_objective_bindings(_course())
    progress = build_learning_progress(
        course,
        user_id="u1",
        events=[],
        attempts=stored,
    )
    assert progress["nodes"][0]["mastery_status"] == "mastered"
    events = learning_events.load_learning_events(course_id="c1")
    assert [item["event_type"] for item in events] == [
        "practice_attempt_started",
        "practice_attempt_submitted",
        "practice_attempt_graded",
    ]
    assert all(item["attempt_id"] == attempt["attempt_id"] for item in events)


def test_legacy_practice_migration_is_idempotent_and_historical_only(monkeypatch, tmp_path):
    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})
    payload = {
        "wrong_answers": [{"nodeId": "n1", "question": "旧题", "timestamp": 1}],
        "quiz_history": [{"nodeId": "n1", "totalQuestions": 3, "correctCount": 1, "timestamp": 2}],
    }
    first = client.post("/api/courses/c1/practice/migrate-legacy", json=payload)
    second = client.post("/api/courses/c1/practice/migrate-legacy", json=payload)
    assert first.json()["created"] == 2
    assert second.json()["created"] == 0
    events = learning_events.load_learning_events(course_id="c1")
    assert all((item.get("result") or {}).get("mastery_eligible") is False for item in events)


def test_legacy_server_records_are_not_implicitly_imported_for_current_user(monkeypatch, tmp_path):
    storage = MemoryStorage()
    storage.data["learning_records.json"] = {
        "c1": {
            "node_records": {
                "n1": {
                    "node_name": "向量",
                    "quiz_records": [{
                        "question_id": "old-q1",
                        "is_correct": False,
                        "timestamp": "2026-03-01T10:00:00",
                    }],
                },
            },
        },
    }
    repository = PracticeAttemptRepository(tmp_path)
    monkeypatch.setattr(practice_router, "storage", storage)
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    assert client.get("/api/courses/c1/practice", params={"node_id": "n1"}).status_code == 200
    assert client.get("/api/courses/c1/practice", params={"node_id": "n1"}).status_code == 200
    events = learning_events.load_learning_events(course_id="c1")
    imported = [item for item in events if item["event_type"] == "legacy_practice_imported"]
    assert imported == []
