from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ai_teacher_state import AITeacherRepository
from routers import companion_learning as routes
from study.auth import study_identity


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = AITeacherRepository(tmp_path / "state")
    monkeypatch.setattr(routes, "ai_teacher_repository", repo)
    course = {
        "course_id": "c",
        "current_course_version_id": "cv",
        "nodes": [{"node_id": "n", "node_name": "导数", "node_content": "正文"}],
    }
    monkeypatch.setattr(routes, "read_learning_course", AsyncMock(return_value=course))
    monkeypatch.setattr(
        routes, "build_current_learner_model", lambda *a, **k: {"model_revision_id": "m", "objectives": []}
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[study_identity] = lambda: {"id": "u", "role": "student"}
    return TestClient(app), repo, app


def test_goal_plan_and_preferences_api(client):
    c, repo, _ = client
    assert c.get("/api/study/companion/preferences").json()["mode"] == "gentle"
    assert (
        c.patch(
            "/api/study/companion/preferences",
            json={"mode": "on_request", "expected_revision": 1, "request_id": "pref-request"},
        ).json()["mode"]
        == "on_request"
    )
    state = c.get("/api/courses/c/learning-records/companion").json()
    assert state["revision"] == 1
    result = c.post(
        "/api/courses/c/learning-records/companion",
        json={
            "action": "save_goal",
            "expected_revision": 1,
            "request_id": "goal-request",
            "value": {"text": "考前复习", "purpose": "exam"},
        },
    )
    assert result.status_code == 200 and result.json()["goal"]["text"] == "考前复习"
    assert repo.companion_state("v", "c") == {}


def test_rejects_untrusted_identity_and_unknown_fields(client):
    c, repo, app = client
    app.dependency_overrides.clear()
    assert c.get("/api/study/companion/preferences", headers={"X-User-Id": "u"}).status_code in {401, 403}
    app.dependency_overrides[study_identity] = lambda: {"id": "u", "role": "student"}
    assert (
        c.patch(
            "/api/study/companion/preferences",
            json={"mode": "gentle", "expected_revision": 1, "request_id": "pref-request", "user_id": "v"},
        ).status_code
        == 422
    )
    assert not list(repo.root.glob("*.json"))


def test_conflicts_and_invalid_input_never_overwrite(client):
    c, _, _ = client
    url = "/api/courses/c/learning-records/companion"
    body = {
        "action": "save_goal",
        "expected_revision": 1,
        "request_id": "goal-request",
        "value": {"text": "理解课程", "purpose": "systematic"},
    }
    assert c.post(url, json=body).status_code == 200
    assert c.post(url, json=body).status_code == 200
    body["value"]["text"] = "变更"
    assert c.post(url, json=body).status_code == 409
    body.update(request_id="another-request", expected_revision=2, value={"text": "x", "minutes_per_week": -1})
    assert c.post(url, json=body).status_code == 422


def test_context_has_official_progress_without_faking_completion(client):
    c, _, _ = client
    result = c.get("/api/courses/c/learning-records/companion").json()
    assert result["source_revision"] == "cv"
    assert result["catalog"] == [{"id": "n", "title": "导数"}]
    assert result["progress"] == []


def test_suppression_is_source_scoped_durable_and_explicitly_restorable(client):
    c, repo, _ = client
    url = "/api/courses/c/learning-records/companion/suppressions"
    assert c.post(url, json={"key": "note:n", "mode": "never"}).status_code == 200
    assert c.get(url).json()[0]["mode"] == "never"
    assert c.post(url, json={"key": "note:n", "mode": "restore"}).status_code == 200
    assert c.get(url).json()[0]["mode"] == "restore"


def test_independent_target_is_exact_private_and_linked_to_the_help(client, monkeypatch):
    c, repo, _ = client
    from routers import practice, study_dialogues

    monkeypatch.setattr(study_dialogues, "_knowledge", lambda *a: [{"knowledge_id": "k", "revision_id": "kr"}])
    monkeypatch.setattr(
        practice,
        "_questions",
        lambda *a, **k: [
            {
                "task_revision_id": "q",
                "quality_status": "passed",
                "node_id": "n",
                "concept_ids": ["k"],
                "knowledge_revision_refs": {"k": "kr"},
                "answer_spec": {"secret": "answer"},
            }
        ],
    )
    monkeypatch.setattr(practice.practice_attempt_repository, "list", lambda *a: [])
    repo.open_study_conversation(
        "u",
        "c",
        conversation_id="conversation",
        title="Help",
        greeting="Hello",
        workspace={"course_version_id": "cv", "node_id": "n", "anchor": {"block_id": "b"}},
    )
    response = c.post(
        "/api/courses/c/learning-records/companion/check-target",
        json={"conversation_id": "conversation", "knowledge_id": "k", "knowledge_revision": "kr"},
    )
    assert response.status_code == 200 and response.json() == {
        "status": "available",
        "node_id": "n",
        "task_revision_id": "q",
    }
    assert "secret" not in response.text
    assert repo.companion_state("u", "c")["check_links"]["q"]["conversation_id"] == "conversation"
    assert (
        c.post(
            "/api/courses/c/learning-records/companion/check-target",
            json={"conversation_id": "conversation", "knowledge_id": "k", "knowledge_revision": "old"},
        ).status_code
        == 409
    )
