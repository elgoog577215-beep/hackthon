from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_teacher_state import AITeacherRepository
from routers import ai_teacher as ai_teacher_router


def _client(monkeypatch, tmp_path):
    repository = AITeacherRepository(tmp_path / "ai-teacher")
    conversation = repository.create_conversation("u1", "course-1", title="向量")
    message = repository.append_message(
        "u1",
        "course-1",
        conversation["conversation_id"],
        {
            "message_id": "assistant-1",
            "role": "assistant",
            "content": "向量同时具有大小和方向。",
            "status": "complete",
            "context_ref": {"node_id": "node-1", "node_name": "向量"},
        },
    )
    recorded = []

    async def get_course(course_id: str):
        assert course_id == "course-1"
        return {"course_id": course_id, "current_course_version_id": "cv-1"}

    monkeypatch.setattr(ai_teacher_router, "ai_teacher_repository", repository)
    monkeypatch.setattr(ai_teacher_router, "get_course_or_404", get_course)
    monkeypatch.setattr(ai_teacher_router, "load_learning_events", lambda **_kwargs: recorded)

    def record_event(**payload):
        event = {"event_id": "evt-1", **payload}
        recorded.append(event)
        return event

    monkeypatch.setattr(ai_teacher_router, "record_learning_event", record_event)
    app = FastAPI()
    app.include_router(ai_teacher_router.router)
    return TestClient(app), conversation, message, recorded


def test_completed_assistant_feedback_records_one_learning_event(monkeypatch, tmp_path):
    client, conversation, message, recorded = _client(monkeypatch, tmp_path)
    payload = {
        "course_id": "course-1",
        "feedback": "unclear",
        "node_id": "node-1",
        "node_name": "向量",
        "action": "explain",
        "content_anchor": {"block_id": "block-1", "block_revision_id": "rev-1"},
    }

    first = client.post(
        f"/api/ai-teacher/conversations/{conversation['conversation_id']}/messages/{message['message_id']}/feedback",
        json=payload,
        headers={"X-User-Id": "u1"},
    )
    second = client.post(
        f"/api/ai-teacher/conversations/{conversation['conversation_id']}/messages/{message['message_id']}/feedback",
        json=payload,
        headers={"X-User-Id": "u1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"status": "recorded", "event_id": "evt-1", "feedback": "unclear"}
    feedback_events = [e for e in recorded if e["event_type"] == "assistant_answer_feedback_submitted"]
    assert len(feedback_events) == 1
    assert feedback_events[0]["result"] == {"feedback": "unclear"}
    assert feedback_events[0]["metadata"]["content_anchor"]["block_id"] == "block-1"

    # "unclear" feedback is a comprehension-gap signal in its own right, so it
    # should also feed the same evidence-trigger pipeline `learner_self_reported`
    # events drive (see `learner_model_service.evaluate_and_propose_change`) —
    # but only once, even across the duplicate/idempotent second POST.
    self_reported_events = [e for e in recorded if e["event_type"] == "learner_self_reported"]
    assert len(self_reported_events) == 1
    assert self_reported_events[0]["node_id"] == "node-1"
    assert self_reported_events[0]["evidence"]["statement"]


def test_feedback_rejects_message_that_is_not_owned_by_current_user(monkeypatch, tmp_path):
    client, conversation, message, recorded = _client(monkeypatch, tmp_path)

    response = client.post(
        f"/api/ai-teacher/conversations/{conversation['conversation_id']}/messages/{message['message_id']}/feedback",
        json={
            "course_id": "course-1",
            "feedback": "resolved",
            "action": "explain",
            "content_anchor": {"block_id": "block-1"},
        },
        headers={"X-User-Id": "other-user"},
    )

    assert response.status_code == 404
    assert recorded == []
