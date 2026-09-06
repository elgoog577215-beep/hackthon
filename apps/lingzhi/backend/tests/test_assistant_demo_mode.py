from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_teacher_state import AITeacherRepository
from routers import assistant as assistant_router
from video2_demo_preset import COURSE_ID, FIXED_PROMPT, TARGET_SECTION_ID


class _ForbiddenAIService:
    def answer_question_events(self, **_kwargs):
        raise AssertionError("演示模式不得调用外部 AI 服务")


def test_demo_mode_returns_curated_local_answer_without_external_model(
    monkeypatch,
    tmp_path,
):
    repository = AITeacherRepository(tmp_path / "ai-teacher")
    recorded: list[dict] = []

    async def get_course(course_id: str):
        assert course_id == COURSE_ID
        return {
            "course_id": COURSE_ID,
            "course_name": "矩阵与线性变换",
            "current_course_version_id": "course-revision-1",
        }

    monkeypatch.setenv("EVOLUTION_DEMO_MODE", "1")
    monkeypatch.setattr(
        assistant_router,
        "ai_teacher_repository",
        repository,
    )
    monkeypatch.setattr(
        assistant_router,
        "get_course_or_404",
        get_course,
    )
    monkeypatch.setattr(
        assistant_router,
        "build_ai_teacher_context",
        lambda *_args, **_kwargs: {"context": "local"},
    )
    monkeypatch.setattr(
        assistant_router,
        "context_public_summary",
        lambda _package: {
            "scene": {"node_id": TARGET_SECTION_ID},
            "sources": [],
        },
    )
    monkeypatch.setattr(
        assistant_router,
        "record_learning_event",
        lambda **payload: recorded.append(payload),
    )
    monkeypatch.setattr(
        assistant_router,
        "ai_service",
        _ForbiddenAIService(),
    )

    app = FastAPI()
    app.include_router(assistant_router.router, prefix="/api")
    client = TestClient(app)
    response = client.post(
        "/api/ask_events",
        headers={"X-User-Id": "video2-demo-student"},
        json={
            "course_id": COURSE_ID,
            "node_id": TARGET_SECTION_ID,
            "node_name": "1.2 矩阵：线性映射与矩阵运算",
            "question": FIXED_PROMPT,
            "context_ref": {
                "course_id": COURSE_ID,
                "node_id": TARGET_SECTION_ID,
            },
        },
    )

    assert response.status_code == 200
    assert "event: final_answer" in response.text
    assert "矩阵乘法计算已经掌握" in response.text
    assert "确认前不会修改正式课程" in response.text
    submitted = next(
        event
        for event in recorded
        if event.get("event_type") == "assistant_question_submitted"
    )
    assert submitted["idempotency_key"].startswith("ai-teacher-request:aim_")
    assert submitted["metadata"]["course_evolution_request"]["scope"] == {
        "user_id": "video2-demo-student",
        "course_id": COURSE_ID,
        "course_version_id": "course-revision-1",
    }
    assert any(
        event.get("result", {}).get("response_mode") == "local_demo"
        for event in recorded
        if event.get("event_type") == "assistant_answer_completed"
    )
    conversations = repository.list_conversations(
        "video2-demo-student",
        COURSE_ID,
    )
    assert len(conversations) == 1
    assistant_messages = [
        message
        for message in conversations[0]["messages"]
        if message["role"] == "assistant"
    ]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["status"] == "complete"


def test_demo_mode_is_scoped_to_the_recording_course(monkeypatch):
    monkeypatch.setenv("EVOLUTION_DEMO_MODE", "1")

    assert assistant_router._assistant_demo_mode(COURSE_ID)
    assert not assistant_router._assistant_demo_mode("another-course")
