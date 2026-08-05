from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_teacher_state import AITeacherRepository, InteractionConflict
from models import CourseGenerationRequest
from question_bank_jobs import QuestionBankRebuildJobRepository
from routers import ai_teacher as ai_teacher_router
from routers.question_bank import QuestionBankRebuildRequest


def test_course_and_question_bank_retrieval_are_explicit_default_off():
    course_request = CourseGenerationRequest(subject="linear algebra")
    assert course_request.retrieval.enabled is False

    explicit = CourseGenerationRequest.model_validate(
        {
            "subject": "linear algebra",
            "retrieval": {"enabled": True},
            "web_question_enrichment": {"enabled": False},
        }
    )
    assert explicit.retrieval.enabled is True

    rebuild = QuestionBankRebuildRequest()
    assert rebuild.retrieval_enabled is False


def test_rebuild_job_freezes_retrieval_authorization(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    job, created = repository.create_job(
        "course-1",
        request_id="request-with-retrieval",
        scope="course",
        node_ids=[],
        mode="full",
        actor_id="teacher-1",
        retrieval_enabled=True,
    )

    assert created is True
    assert job["retrieval_enabled"] is True


def test_old_ai_teacher_conversation_defaults_retrieval_off(tmp_path):
    repository = AITeacherRepository(tmp_path / "ai-teacher")
    path = repository._path(repository._key("u1", "course-1"))
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "conversations": [
                    {
                        "conversation_id": "legacy-c1",
                        "course_id": "course-1",
                        "user_id": "u1",
                        "revision": 1,
                        "messages": [],
                    }
                ],
                "proposals": [],
                "receipts": [],
                "suppressions": [],
            }
        ),
        encoding="utf-8",
    )

    conversation = repository.get_conversation("u1", "course-1", "legacy-c1")
    assert conversation["retrieval_enabled"] is False


def test_ai_teacher_setting_is_revision_checked_and_conversation_scoped(tmp_path):
    repository = AITeacherRepository(tmp_path / "ai-teacher")
    first = repository.create_conversation("u1", "course-1")
    second = repository.create_conversation("u1", "course-1")

    updated = repository.update_conversation_settings(
        "u1",
        "course-1",
        first["conversation_id"],
        retrieval_enabled=True,
        expected_revision=first["revision"],
    )
    assert updated["retrieval_enabled"] is True
    assert updated["revision"] == first["revision"] + 1
    assert repository.get_conversation(
        "u1", "course-1", second["conversation_id"]
    )["retrieval_enabled"] is False

    with pytest.raises(InteractionConflict) as conflict:
        repository.update_conversation_settings(
            "u1",
            "course-1",
            first["conversation_id"],
            retrieval_enabled=False,
            expected_revision=first["revision"],
        )
    assert conflict.value.current["revision"] == updated["revision"]


def test_ai_teacher_public_settings_endpoint_returns_409_on_conflict(
    monkeypatch, tmp_path
):
    repository = AITeacherRepository(tmp_path / "ai-teacher")

    async def get_course(course_id: str):
        return {"course_id": course_id, "current_course_version_id": "cv-1"}

    monkeypatch.setattr(ai_teacher_router, "ai_teacher_repository", repository)
    monkeypatch.setattr(ai_teacher_router, "get_course_or_404", get_course)
    app = FastAPI()
    app.include_router(ai_teacher_router.router)
    client = TestClient(app)

    created = client.post(
        "/api/ai-teacher/conversations",
        headers={"X-User-Id": "u1"},
        json={"course_id": "course-1", "retrieval_enabled": True},
    )
    assert created.status_code == 200
    conversation = created.json()
    assert conversation["retrieval_enabled"] is True

    changed = client.patch(
        f"/api/ai-teacher/conversations/{conversation['conversation_id']}/settings",
        headers={"X-User-Id": "u1"},
        json={
            "course_id": "course-1",
            "retrieval_enabled": False,
            "expected_revision": conversation["revision"],
        },
    )
    assert changed.status_code == 200
    assert changed.json()["retrieval_enabled"] is False

    conflict = client.patch(
        f"/api/ai-teacher/conversations/{conversation['conversation_id']}/settings",
        headers={"X-User-Id": "u1"},
        json={
            "course_id": "course-1",
            "retrieval_enabled": True,
            "expected_revision": conversation["revision"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "conversation_revision_conflict"
