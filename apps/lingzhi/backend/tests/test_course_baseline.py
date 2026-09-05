from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from course_baseline import (
    build_ai_baseline_prompt,
    confirmed_generation_request,
    course_information_snapshot,
    merge_ai_baseline_draft,
)
from models import CourseGenerationRequest
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


def test_confirmed_baseline_converts_legacy_inquiry_to_current_classifications():
    request = CourseGenerationRequest.model_validate({
        "subject": "城市暴雨与内涝",
        "course_type": "inquiry",
        "course_intent": {
            "type": "inquiry",
            "core_question": "为什么短时强降雨会导致内涝？",
            "desired_output": "形成有资料依据的解释",
        },
    })

    persisted = confirmed_generation_request(request)

    assert persisted["learning_purpose"] == "systematic"
    assert persisted["course_teaching_type"] == "seminar"
    assert persisted["course_intent"]["type"] == "systematic"
    assert "为什么短时强降雨" in persisted["course_intent"]["learning_goal"]
    assert "course_type" not in persisted
    assert "composition_style" not in persisted


def test_legacy_short_term_default_range_is_normalized_to_the_zju_calendar():
    snapshot = course_information_snapshot({
        "course_name": "C 语言程序设计",
        "term": "秋季",
        "course_profile": {
            "active_week_start": 1,
            "active_week_end": 16,
            "planned_lecture_count": 16,
        },
        "generation_request": _generation_request(),
    })

    assert snapshot["course_profile"]["active_week_start"] == 1
    assert snapshot["course_profile"]["active_week_end"] == 8
    assert snapshot["course_profile"]["week_range_mode"] == "academic_calendar"
    assert snapshot["generation_request"]["teacher_course_brief"]["academic_term"] == "秋季"


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
    assert after["generation_request"]["learning_purpose"] == "systematic"
    assert after["generation_request"]["course_teaching_type"] == "comprehensive"
    assert "course_type" not in after["generation_request"]
    assert "composition_style" not in after["generation_request"]
    assert after["course_document_revision"] == before["course_document_revision"]
    assert after["course_document"] == before["course_document"]
    assert after["generation_job_id"] == ""
    previous = after["generation_request_history"][-1]["previous"]
    assert previous["learning_purpose"] == "systematic"
    assert previous["course_teaching_type"] == "comprehensive"
    assert "course_type" not in previous
    assert "course_purpose" not in previous
    assert "composition_style" not in previous
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


@pytest.mark.asyncio
async def test_course_information_update_syncs_profile_and_supports_restore(tmp_path):
    storage = Storage(str(tmp_path / "data"))
    repository = CourseDocumentRepository(storage)
    await repository.create_teacher_draft(
        "course-1",
        title="人工智能通识课",
        metadata={
            "owner_id": "teacher-a",
            "academic_year": "2026-2027",
            "term": "秋冬",
            "course_profile": {
                "course_code": "AI101",
                "target_grade": "大学生",
                "course_category": "通识必修课",
                "target_major": "",
                "credits": 2,
                "total_hours": 16,
                "assessment_method": "过程考核",
                "course_intro": "理解 AI 的基本原理。",
                "teaching_goals": "理解人工智能的基本原理",
            },
            "generation_request": _generation_request(),
            "generation_request_revision": 0,
        },
    )
    request = SimpleNamespace(headers={"X-User-Id": "teacher-a"})
    before = await course_baseline.get_course_information(
        "course-1",
        request,
        repository,
    )
    edited = before["information"]
    edited["term"] = "春夏"
    edited["generation_request"]["teacher_course_brief"]["total_class_hours"] = 64
    edited["generation_request"]["teacher_course_brief"]["teaching_context"] = "blended"
    edited["generation_request"]["pedagogy_mode"] = "natural_science"

    response = await course_baseline.update_course_information(
        "course-1",
        course_baseline.CourseInformationUpdateRequest.model_validate({
            "information": edited,
            "expected_revision": before["revision"],
            "expected_document_revision": before["document_revision"],
            "idempotency_key": "course-information-command-1",
            "source": "manual",
        }),
        request,
        repository,
    )

    after = repository.load_course_view("course-1")
    assert response["revision"] == 1
    assert response["downstream_action"] == "none"
    assert after["course_profile"]["total_hours"] == 64
    assert after["generation_request"]["teacher_course_brief"]["total_class_hours"] == 64
    assert after["generation_request"]["teacher_course_brief"]["academic_term"] == "2026-2027 春夏"
    assert after["generation_request"]["pedagogy_mode"] == "natural_science"
    assert after["course_document_revision"] == before["document_revision"]
    assert response["versions"][1]["revision"] == 0

    restore_information = response["versions"][1]["information"]
    restored = await course_baseline.update_course_information(
        "course-1",
        course_baseline.CourseInformationUpdateRequest.model_validate({
            "information": restore_information,
            "expected_revision": response["revision"],
            "expected_document_revision": response["document_revision"],
            "idempotency_key": "course-information-command-2",
            "source": "restore",
            "restore_revision": 0,
        }),
        request,
        repository,
    )

    current = repository.load_course_view("course-1")
    assert restored["revision"] == 2
    assert current["course_profile"]["total_hours"] == 16
    assert current["generation_request"]["teacher_course_brief"]["total_class_hours"] == 16
    assert current["course_information_history"][-1]["restore_revision"] == 0
    assert len(restored["versions"]) == 3


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
    assert "course_type" not in request
    assert "composition_style" not in request
    assert "unknown_field" not in request


def test_ai_draft_uses_current_purpose_and_teaching_type_fields():
    course = {
        "course_id": "course-1",
        "course_name": "人工智能通识课",
        "generation_request_revision": 3,
        "generation_request": _generation_request(),
    }
    prompt = build_ai_baseline_prompt(
        course,
        {"messages": [{"role": "user", "content": "改成项目实战，整课用项目课组织。"}]},
    )

    assert '"learning_purpose"' in prompt
    assert '"course_teaching_type"' in prompt
    assert '"course_type"' not in prompt

    draft = merge_ai_baseline_draft(
        course,
        {
            "updates": {
                "learning_purpose": "project",
                "course_teaching_type": "project",
                "learning_goal": "完成一个可演示的 AI 应用",
            },
            "evidence": ["教师明确要求项目实战和项目课。"],
        },
        conversation_id="conversation-2",
        source_message_ids=["message-3"],
    )

    request = draft["generation_request"]
    assert request["learning_purpose"] == "project"
    assert request["course_teaching_type"] == "project"
    assert request["course_intent"]["type"] == "project"
    assert set(draft["changed_fields"]) == {
        "learning_purpose",
        "course_teaching_type",
        "learning_goal",
    }
    assert "course_type" not in request


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
