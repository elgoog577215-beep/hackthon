"""`/ask_events` must report which kind of model failure the learner hit.

The handler previously answered every provider failure with one hard-coded
`model_unavailable` code and discarded whatever text had already streamed. That
is the "silent failure or half an action" case: a rate limit that clears in a
minute, a missing key that never clears, and a truncated answer all looked
identical, and a partially-read answer vanished on failure.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_base import AIProviderRequestError, AIProviderUnavailable
from ai_qa_service import AIQAService
from ai_teacher_state import AITeacherRepository
from routers import assistant as assistant_router


def _sse_events(text: str) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name = ""
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if not name or not data_lines:
            continue
        try:
            parsed.append((name, json.loads("\n".join(data_lines))))
        except json.JSONDecodeError:
            continue
    return parsed


class _FailingAIService(AIQAService):
    """Real classification path, with the provider call replaced by a failure."""

    def __init__(self, error: Exception, prefix: str = ""):
        super().__init__()
        self._error = error
        self._prefix = prefix

    async def _stream_llm(self, *_args, **_kwargs):
        if self._prefix:
            yield self._prefix
        raise self._error


def _client(monkeypatch, tmp_path, service):
    repository = AITeacherRepository(tmp_path / "ai-teacher")

    async def get_course(course_id: str):
        return {
            "course_id": course_id,
            "course_name": "线性代数",
            "current_course_version_id": "cv-1",
        }

    monkeypatch.delenv("EVOLUTION_DEMO_MODE", raising=False)
    monkeypatch.setattr(assistant_router, "ai_teacher_repository", repository)
    monkeypatch.setattr(assistant_router, "get_course_or_404", get_course)
    monkeypatch.setattr(
        assistant_router,
        "build_ai_teacher_context",
        lambda *_a, **_k: {"conversation": {"recent_messages": []}},
    )
    monkeypatch.setattr(
        assistant_router,
        "context_public_summary",
        lambda _p: {"scene": {"node_id": "node-1"}, "sources": []},
    )
    monkeypatch.setattr(assistant_router, "record_learning_event", lambda **_p: None)
    monkeypatch.setattr(assistant_router, "record_course_evolution_request", lambda *_a, **_k: None)
    monkeypatch.setattr(assistant_router, "ai_service", service)

    app = FastAPI()
    app.include_router(assistant_router.router, prefix="/api")
    return TestClient(app), repository


def _ask(client) -> list[tuple[str, dict]]:
    response = client.post(
        "/api/ask_events",
        headers={"X-User-Id": "u1"},
        json={
            "course_id": "course-1",
            "node_id": "node-1",
            "node_name": "向量",
            "question": "什么是线性相关？",
            "context_ref": {"course_id": "course-1", "node_id": "node-1"},
        },
    )
    assert response.status_code == 200
    return _sse_events(response.text)


def test_rate_limited_answer_reports_a_retryable_code(monkeypatch, tmp_path):
    service = _FailingAIService(AIProviderRequestError("Error code: 429 rate limit"))
    client, repository = _client(monkeypatch, tmp_path, service)

    events = _ask(client)

    errors = [payload for name, payload in events if name == "error"]
    assert len(errors) == 1
    assert errors[0]["code"] == "model_rate_limited"
    assert errors[0]["retryable"] is True
    # The stream still closes cleanly so the client leaves its loading state.
    assert [name for name, _ in events][-1] == "done"

    conversation = repository.list_conversations("u1", "course-1")[0]
    assistant = [m for m in conversation["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["status"] == "failed"


def test_missing_api_key_is_reported_as_a_non_retryable_code(monkeypatch, tmp_path):
    service = _FailingAIService(AIProviderUnavailable("not_configured"))
    client, _repository = _client(monkeypatch, tmp_path, service)

    events = _ask(client)

    errors = [payload for name, payload in events if name == "error"]
    assert errors[0]["code"] == "model_not_configured"
    assert errors[0]["retryable"] is False


def test_authentication_failure_is_distinguished_from_a_generic_outage(monkeypatch, tmp_path):
    service = _FailingAIService(AIProviderUnavailable("authentication_failed"))
    client, _repository = _client(monkeypatch, tmp_path, service)

    events = _ask(client)

    errors = [payload for name, payload in events if name == "error"]
    assert errors[0]["code"] == "model_auth_failed"
    assert errors[0]["retryable"] is False


def test_partial_answer_survives_a_mid_stream_failure(monkeypatch, tmp_path):
    service = _FailingAIService(
        AIProviderRequestError("Request timed out."),
        prefix="线性相关的意思是",
    )
    client, repository = _client(monkeypatch, tmp_path, service)

    events = _ask(client)

    streamed = "".join(
        payload.get("chunk", "")
        for name, payload in events
        if name == "answer"
    )
    assert "线性相关的意思是" in streamed
    errors = [payload for name, payload in events if name == "error"]
    assert errors[0]["code"] == "model_timeout"

    # The partial text is persisted with the failure so a reload does not show
    # a blank assistant turn where the learner had already read something.
    conversation = repository.list_conversations("u1", "course-1")[0]
    assistant = [m for m in conversation["messages"] if m["role"] == "assistant"][0]
    assert assistant["status"] == "failed"
    assert "线性相关的意思是" in assistant["content"]
    assert assistant["failure_code"] == "model_timeout"


def test_successful_answer_still_emits_no_error_event(monkeypatch, tmp_path):
    class _OkService(AIQAService):
        async def _stream_llm(self, *_args, **_kwargs):
            yield "线性相关表示存在非零系数组合。"

    client, repository = _client(monkeypatch, tmp_path, _OkService())

    events = _ask(client)

    assert not [name for name, _ in events if name == "error"]
    final = [payload for name, payload in events if name == "final_answer"]
    assert final and "线性相关" in final[0]["answer"]
    conversation = repository.list_conversations("u1", "course-1")[0]
    assistant = [m for m in conversation["messages"] if m["role"] == "assistant"][0]
    assert assistant["status"] == "complete"
