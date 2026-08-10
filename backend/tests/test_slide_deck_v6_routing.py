import pytest
from fastapi import HTTPException

from routers import teaching_representations as representation_router
from routers.teaching_representations import SlideDeckVariantBuildRequest


def _ready_course() -> dict:
    return {
        "course_id": "generic-v6-routing-fixture",
        "course_revision": "course-rev-1",
        "generation_stage_artifacts": {
            "course_teaching_plan": {"status": "completed", "section_count": 1},
        },
        "course_teaching_plan": {
            "revision_id": "plan-rev-1",
            "sections": [{"node_id": "chapter-1", "teaching_modules": []}],
        },
        "course_knowledge_base": {
            "revision_id": "kb-rev-1",
            "lifecycle_status": "active",
        },
        "course_coherence_contract": {
            "revision_id": "coherence-rev-1",
            "status": "active",
            "quality_report": {"passed": True},
        },
    }


def test_explicit_v6_request_selects_v6_only_when_feature_is_enabled(monkeypatch) -> None:
    request = SlideDeckVariantBuildRequest.model_validate({"engine_version": "v6"})
    monkeypatch.setenv("SLIDE_DECK_V6_ENABLED", "true")

    assert representation_router._resolve_requested_slide_schema(
        _ready_course(),
        request,
    ) == "slide_deck_v6"

    monkeypatch.setenv("SLIDE_DECK_V6_ENABLED", "false")
    with pytest.raises(HTTPException) as caught:
        representation_router._resolve_requested_slide_schema(
            _ready_course(),
            request,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "slide_deck_v6_disabled"


def test_v6_does_not_use_the_inline_deterministic_fallback() -> None:
    with pytest.raises(HTTPException) as caught:
        representation_router._require_durable_v6_orchestrator(
            "slide_deck_v6",
            None,
        )

    assert caught.value.status_code == 503
    assert caught.value.detail == {
        "code": "v6_orchestrator_unavailable",
        "message": "V6 requires the durable AI planning service; the last published deck remains available.",
        "action": "retry_after_service_recovery",
        "retryable": True,
        "stage": "orchestration",
    }


def test_default_build_remains_v5_until_v6_rollout_switch_is_enabled(monkeypatch) -> None:
    request = SlideDeckVariantBuildRequest()
    monkeypatch.setenv("SLIDE_DECK_V6_ENABLED", "true")
    monkeypatch.setenv("SLIDE_DECK_V6_DEFAULT_ENABLED", "false")
    assert representation_router._resolve_requested_slide_schema(
        _ready_course(),
        request,
    ) == "slide_deck_v5"

    monkeypatch.setenv("SLIDE_DECK_V6_DEFAULT_ENABLED", "true")
    assert representation_router._resolve_requested_slide_schema(
        _ready_course(),
        request,
    ) == "slide_deck_v6"
