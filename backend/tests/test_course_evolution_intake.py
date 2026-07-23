from __future__ import annotations

import pytest

from course_evolution_intake import (
    COURSE_EVOLUTION_REQUEST_SCHEMA,
    CourseEvolutionRequest,
    record_course_evolution_request,
)
from learning_contracts import LearnerCourseScope
from product_runtime_policy import ProductRuntimePolicy


def _scope(course_id: str = "course-1") -> LearnerCourseScope:
    return LearnerCourseScope.from_course(
        {
            "course_id": course_id,
            "current_course_version_id": "version-3",
        },
        user_id="learner-1",
        expected_course_id=course_id,
    )


def test_learner_course_scope_rejects_cross_course_write():
    with pytest.raises(ValueError, match="does not match"):
        LearnerCourseScope.from_course(
            {"course_id": "course-2"},
            user_id="learner-1",
            expected_course_id="course-1",
        )


def test_ai_teacher_request_emits_versioned_course_evolution_protocol():
    request = CourseEvolutionRequest(
        scope=_scope(),
        request_id="message-1",
        instruction="我不理解这里为什么要交换顺序，请详细解释。",
        entrypoint="ai_teacher",
        surface_entrypoint="selection",
        requested_scope="current_section",
        section_id="section-1",
        conversation_id="conversation-1",
        selection="交换顺序",
        context_ref={"node_id": "section-1"},
    )

    payload = request.learning_event_payload()

    assert payload["user_id"] == "learner-1"
    assert payload["course_id"] == "course-1"
    assert payload["course_version_id"] == "version-3"
    assert payload["idempotency_key"] == "ai-teacher-request:message-1"
    assert payload["evidence"]["entrypoint"] == "selection"
    protocol = payload["metadata"]["course_evolution_request"]
    assert protocol["schema_version"] == COURSE_EVOLUTION_REQUEST_SCHEMA
    assert protocol["scope"] == {
        "user_id": "learner-1",
        "course_id": "course-1",
        "course_version_id": "version-3",
    }


def test_adjustment_request_uses_evidence_flow_only_when_scope_can_honor_contract():
    instruction = (
        "矩阵乘法计算我会，但我一直不理解为什么复合变换要先右后左。"
        "请在本节和后面相关内容中，先用几何动画解释，再让我进行计算。"
    )
    current_section = CourseEvolutionRequest(
        scope=_scope(),
        request_id="request-1",
        instruction=instruction,
        entrypoint="course_adjustment",
        requested_scope="current_section",
        section_id="section-1",
        expected_document_revision="version-3",
        expected_block_revision="block-version-2",
    )
    whole_course = CourseEvolutionRequest(
        scope=_scope(),
        request_id="request-2",
        instruction=instruction,
        entrypoint="course_adjustment",
        requested_scope="whole_course",
        section_id="section-1",
    )

    assert current_section.can_use_evidence_flow() is False
    assert whole_course.can_use_evidence_flow() is True

    stale_request = CourseEvolutionRequest(
        scope=_scope(),
        request_id="request-stale",
        instruction=instruction,
        entrypoint="course_adjustment",
        requested_scope="whole_course",
        section_id="section-1",
        expected_document_revision="version-2",
    )
    assert stale_request.can_use_evidence_flow() is False


def test_course_evolution_request_uses_injected_recorder():
    recorded: list[dict] = []
    request = CourseEvolutionRequest(
        scope=_scope(),
        request_id="request-3",
        instruction="请详细解释本节这个概念。",
        entrypoint="course_adjustment",
        requested_scope="current_section",
        section_id="section-1",
        expected_document_revision="version-3",
        expected_block_revision="block-version-2",
    )

    result = record_course_evolution_request(
        request,
        recorder=lambda **payload: recorded.append(payload) or {"event_id": "event-1"},
    )

    assert result == {"event_id": "event-1"}
    assert recorded[0]["source"] == "course_adjustment.learner_request"
    assert recorded[0]["idempotency_key"] == "course-adjustment:request-3"
    protocol = recorded[0]["metadata"]["course_evolution_request"]
    assert protocol["expected_document_revision"] == "version-3"
    assert protocol["expected_block_revision"] == "block-version-2"


def test_demo_runtime_policy_is_disabled_for_non_whitelisted_courses():
    policy = ProductRuntimePolicy.from_environment({
        "EVOLUTION_DEMO_MODE": "1",
        "EVOLUTION_DEMO_COURSE_IDS": "demo-a,demo-b",
    })

    assert policy.allows_demo_overrides("demo-a") is True
    assert policy.allows_demo_overrides("course-1") is False
    assert policy.allows_demo_overrides("") is False
