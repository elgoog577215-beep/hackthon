from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_teacher_retrieval import (
    build_ai_teacher_queries,
    merge_ai_teacher_retrieval,
    should_retrieve_for_message,
)
from ai_teacher_context import context_public_summary, format_ai_teacher_context_prompt
from ai_teacher_state import AITeacherRepository
from routers import assistant as assistant_router


def _course() -> dict:
    return {
        "course_id": "course-1",
        "course_name": "Linear algebra",
        "learner_starting_profile": {
            "summary": "PRIVATE_PROFILE_SENTINEL student@example.com",
        },
        "nodes": [
            {
                "node_id": "node-1",
                "node_level": 2,
                "node_name": "Eigenvalues",
                "learning_objective": "Compute eigenvalues",
            }
        ],
    }


def _context() -> dict:
    return {
        "schema_version": "ai_teacher_context_v3",
        "request": {"question": "What is current practice?"},
        "scene": {"course_id": "course-1", "node_id": "node-1"},
        "runtime": {},
        "learner_model": {},
        "knowledge_context": {},
        "task": {},
        "sources": [
            {
                "source_id": "course-source",
                "type": "course_content",
                "title": "Course section",
                "content": "Local material",
            }
        ],
        "learner_evidence": [],
        "conversation": {
            "recent_messages": [
                {"role": "user", "content": "PRIVATE_HISTORY_SENTINEL"}
            ]
        },
        "permissions": {},
    }


def _package(status: str = "completed") -> dict:
    return {
        "schema_version": "retrieval_package_v1",
        "status": status,
        "revision": 1,
        "receipt": {
            "schema_version": "retrieval_receipt_v1",
            "status": status,
            "error_codes": [] if status == "completed" else ["timeout"],
        },
        "sources": (
            [
                {
                    "source_id": "src_web",
                    "type": "web",
                    "title": "Current reference",
                    "url": "https://example.edu/current",
                    "domain": "example.edu",
                    "excerpt": "Current public evidence.",
                    "published_date": "2026-08-01",
                    "retrieved_at": "2026-08-05T00:00:00+00:00",
                    "content_hash": "hash",
                    "provider": "exa",
                    "trust_tier": "tier_a",
                    "license": "CC BY",
                    "reuse_policy": "summary_only",
                }
            ]
            if status == "completed"
            else []
        ),
    }


def test_ai_teacher_queries_exclude_profile_and_conversation_history():
    queries = build_ai_teacher_queries(
        _course(),
        question="What is the current definition of an eigenvalue?",
        node_id="node-1",
    )
    joined = " ".join(queries)
    assert 1 <= len(queries) <= 3
    assert "Linear algebra" in joined
    assert "current definition" in joined
    assert "Compute eigenvalues" in joined
    assert "PRIVATE_PROFILE_SENTINEL" not in joined
    assert "PRIVATE_HISTORY_SENTINEL" not in joined
    assert "student@example.com" not in joined


def test_web_sources_are_numbered_and_visible_without_private_context():
    merged = merge_ai_teacher_retrieval(_context(), _package())
    public = context_public_summary(merged)
    prompt = format_ai_teacher_context_prompt(merged)

    web = next(item for item in public["sources"] if item["type"] == "web")
    assert web["citation_id"] == "S1"
    assert web["url"] == "https://example.edu/current"
    assert "[S1]" in prompt
    assert "Current public evidence" in prompt
    assert "PRIVATE_HISTORY_SENTINEL" in prompt
    assert "student@example.com" not in prompt


def test_failed_retrieval_keeps_local_context_and_explicit_receipt():
    local = _context()
    merged = merge_ai_teacher_retrieval(local, _package("failed_fallback_local"))
    assert merged["sources"] == local["sources"]
    assert merged["web_retrieval"]["status"] == "failed_fallback_local"
    assert merged["web_retrieval"]["receipt"]["error_codes"] == ["timeout"]


def test_retrieval_only_runs_for_enabled_ordinary_answers():
    assert should_retrieve_for_message(
        {"retrieval_enabled": True}, direct_action=None
    )
    assert not should_retrieve_for_message(
        {"retrieval_enabled": False}, direct_action=None
    )
    assert not should_retrieve_for_message(
        {"retrieval_enabled": True}, direct_action="create_note"
    )


class _AnswerService:
    async def answer_question_events(self, **_kwargs):
        yield (
            "event: answer\ndata: "
            + json.dumps({"chunk": "Web-backed answer [S1]."})
            + "\n\n"
        )
        yield (
            "event: final_answer\ndata: "
            + json.dumps({"answer": "Web-backed answer [S1]."})
            + "\n\n"
        )
        yield "event: metadata\ndata: {}\n\n"


def test_ask_events_emits_retrieval_lifecycle_and_persists_receipt(
    monkeypatch, tmp_path
):
    repository = AITeacherRepository(tmp_path / "ai-teacher")
    conversation = repository.create_conversation(
        "u1", "course-1", retrieval_enabled=True
    )

    async def get_course(_course_id: str):
        return {
            **_course(),
            "current_course_version_id": "cv-1",
        }

    async def retrieve(*_args, **_kwargs):
        return _package()

    monkeypatch.setattr(assistant_router, "ai_teacher_repository", repository)
    monkeypatch.setattr(assistant_router, "get_course_or_404", get_course)
    monkeypatch.setattr(
        assistant_router,
        "build_ai_teacher_context",
        lambda *_args, **_kwargs: _context(),
    )
    monkeypatch.setattr(
        assistant_router,
        "retrieve_ai_teacher_sources",
        retrieve,
        raising=False,
    )
    monkeypatch.setattr(
        assistant_router,
        "record_course_evolution_request",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        assistant_router,
        "record_learning_event",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(assistant_router, "ai_service", _AnswerService())
    monkeypatch.setattr(
        assistant_router, "_assistant_demo_mode", lambda _course_id: False
    )
    app = FastAPI()
    app.include_router(assistant_router.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/ask_events",
        headers={"X-User-Id": "u1"},
        json={
            "course_id": "course-1",
            "conversation_id": conversation["conversation_id"],
            "node_id": "node-1",
            "question": "What is current?",
        },
    )

    assert response.status_code == 200
    assert 'event: retrieval\ndata: {"status": "started"}' in response.text
    assert 'event: retrieval\ndata: {"status": "completed"' in response.text
    assert "https://example.edu/current" in response.text
    persisted = repository.get_conversation(
        "u1", "course-1", conversation["conversation_id"]
    )
    message = next(
        item for item in persisted["messages"] if item["role"] == "assistant"
    )
    assert message["retrieval_receipt"]["status"] == "completed"
    assert any(item.get("source_id") == "src_web" for item in message["sources"])
