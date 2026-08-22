from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from course_baseline import merge_ai_baseline_draft
from course_repository import CourseDocumentRepository
from routers import course_baseline
from storage import Storage


def _generation_request(goal: str = "理解人工智能的基本原理") -> dict:
    return {
        "subject": "人工智能通识课",
        "target_audience": "大学生",
        "difficulty": "intermediate",
        "course_type": "systematic",
        "course_intent": {
            "schema_version": "course_intent_v1",
            "type": "systematic",
            "learning_goal": goal,
        },
        "composition_style": "balanced",
        "pedagogy_mode": "general",
        "production_mode": "manual",
        "teacher_course_brief": {
            "schema_version": "teacher_course_brief_v1",
            "target_audience": "大学生",
            "total_class_hours": 16,
            "lesson_duration_minutes": 45,
            "teaching_context": "classroom",
            "section_count": 8,
        },
    }


@pytest.mark.asyncio
async def test_confirmed_baseline_update_changes_metadata_without_regenerating_course(tmp_path):
    storage = Storage(str(tmp_path / "data"))
    repository = CourseDocumentRepository(storage)
    await repository.create_teacher_draft(
        "course-1",
        title="人工智能通识课",
        metadata={
            "owner_id": "teacher-a",
            "generation_request": _generation_request(),
            "generation_request_revision": 0,
        },
    )
    before = repository.load_course_view("course-1")
    updated_request = _generation_request("能解释 AI 的能力边界并完成案例判断")
    updated_request["difficulty"] = "advanced"

    response = await course_baseline.update_course_baseline(
        "course-1",
        course_baseline.CourseBaselineUpdateRequest.model_validate({
            "generation_request": updated_request,
            "expected_revision": 0,
            "expected_document_revision": before["course_document_revision"],
            "idempotency_key": "baseline-command-1",
            "source": "manual",
        }),
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
        repository,
    )

    after = repository.load_course_view("course-1")
    assert response["status"] == "confirmed"
    assert response["revision"] == 1
    assert response["downstream_action"] == "none"
    assert set(response["changed_fields"]) == {"learning_goal", "difficulty"}
    assert after["generation_request"]["course_intent"]["learning_goal"].startswith("能解释")
    assert after["course_document_revision"] == before["course_document_revision"]
    assert after["course_document"] == before["course_document"]
    assert after["generation_job_id"] == ""
    assert after["generation_request_history"][-1]["previous"] == before["generation_request"]
    assert after["course_operation_log"][-1]["operation"] == "update_course_generation_request"

    repeated = await course_baseline.update_course_baseline(
        "course-1",
        course_baseline.CourseBaselineUpdateRequest.model_validate({
            "generation_request": updated_request,
            "expected_revision": 0,
            "expected_document_revision": before["course_document_revision"],
            "idempotency_key": "baseline-command-1",
            "source": "manual",
        }),
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
        repository,
    )
    assert repeated["revision"] == 1
    assert len(repository.load_course_view("course-1")["generation_request_history"]) == 1


def test_ai_draft_only_changes_supported_fields_and_preserves_unmentioned_baseline():
    course = {
        "course_id": "course-1",
        "course_name": "人工智能通识课",
        "generation_request_revision": 3,
        "generation_request": _generation_request(),
    }
    draft = merge_ai_baseline_draft(
        course,
        {
            "updates": {
                "course_type": None,
                "learning_goal": "能比较不同 AI 方法的适用边界",
                "difficulty": "advanced",
                "pedagogy_mode": None,
                "total_class_hours": 24,
                "section_count": None,
                "production_mode": None,
                "unknown_field": "must be ignored",
            },
            "evidence": ["教师明确希望学生能比较方法边界。"],
        },
        conversation_id="conversation-1",
        source_message_ids=["message-1", "message-2"],
    )

    request = draft["generation_request"]
    assert draft["based_on_revision"] == 3
    assert set(draft["changed_fields"]) == {"learning_goal", "difficulty", "course_scale"}
    assert request["course_intent"]["learning_goal"] == "能比较不同 AI 方法的适用边界"
    assert request["teacher_course_brief"]["total_class_hours"] == 24
    assert request["teacher_course_brief"]["section_count"] == 8
    assert request["pedagogy_mode"] == "general"
    assert "unknown_field" not in request


@pytest.mark.asyncio
async def test_ai_draft_endpoint_uses_existing_teacher_conversation_without_saving(monkeypatch):
    course = {
        "course_id": "course-1",
        "course_name": "人工智能通识课",
        "owner_id": "teacher-a",
        "generation_request_revision": 0,
        "generation_request": _generation_request(),
    }
    repository = SimpleNamespace(load_course_view=lambda _course_id: course)
    conversation = {
        "conversation_id": "conversation-1",
        "messages": [
            {"message_id": "message-1", "role": "user", "content": "我希望改成 24 学时的高阶课程。"},
            {"message_id": "message-2", "role": "assistant", "status": "complete", "content": "可以，我会先整理成草稿。"},
        ],
    }
    monkeypatch.setattr(
        course_baseline.ai_teacher_repository,
        "get_conversation",
        lambda *_args: conversation,
    )
    monkeypatch.setattr(
        course_baseline.ai_service,
        "_call_llm",
        AsyncMock(return_value='{"updates":{"difficulty":"advanced","total_class_hours":24},"evidence":[]}'),
    )
    monkeypatch.setattr(
        course_baseline.ai_service,
        "_extract_json",
        lambda _value: {"updates": {"difficulty": "advanced", "total_class_hours": 24}, "evidence": []},
    )

    response = await course_baseline.draft_course_baseline_from_conversation(
        "course-1",
        course_baseline.CourseBaselineDraftRequest(
            conversation_id="conversation-1",
            through_message_id="message-2",
        ),
        SimpleNamespace(headers={"X-User-Id": "teacher-a"}),
        repository,
    )

    assert response["generation_request"]["difficulty"] == "advanced"
    assert response["generation_request"]["teacher_course_brief"]["total_class_hours"] == 24
    assert course["generation_request"]["difficulty"] == "intermediate"
    assert response["source_message_ids"] == ["message-1", "message-2"]
