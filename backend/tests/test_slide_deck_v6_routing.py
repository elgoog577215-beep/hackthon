import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from routers import teaching_representations as representation_router
from routers.teaching_representations import SlideDeckVariantBuildRequest
from slide_deck_v6_orchestrator import SlideDeckV6CandidateRepository
from teaching_representations import TeachingRepresentationRepository
from template_layout_contract import compile_builtin_template_layout_contract_v1


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


def test_deployed_shadow_is_explicitly_available_while_default_stays_v5(monkeypatch) -> None:
    monkeypatch.delenv("SLIDE_DECK_V6_ENABLED", raising=False)
    monkeypatch.delenv("SLIDE_DECK_V6_DEFAULT_ENABLED", raising=False)

    assert representation_router._resolve_requested_slide_schema(
        _ready_course(),
        SlideDeckVariantBuildRequest(engine_version="v6"),
    ) == "slide_deck_v6"
    assert representation_router._resolve_requested_slide_schema(
        _ready_course(),
        SlideDeckVariantBuildRequest(),
    ) == "slide_deck_v5"


def test_v6_freezes_an_explicit_published_template_version(monkeypatch) -> None:
    expected = compile_builtin_template_layout_contract_v1("qizhi-classroom").model_copy(
        update={
            "template_id": "pptp-generic",
            "template_version": "7",
            "template_digest": "tmpl_personal_v7",
        }
    )
    captured: dict[str, object] = {}

    def resolve(pack_id: str, version: int | None, owner_id: str):
        captured.update(pack_id=pack_id, version=version, owner_id=owner_id)
        return expected

    monkeypatch.setattr(
        representation_router.ppt_template_pack_repository,
        "resolve_v6_layout_contract",
        resolve,
    )
    request = SlideDeckVariantBuildRequest.model_validate({
        "engine_version": "v6",
        "template_pack_id": "pptp-generic",
        "template_version": 7,
    })

    resolved = representation_router._resolve_v6_template_contract(
        request,
        owner_id="owner-generic",
        theme="qizhi-classroom",
    )

    assert resolved.template_digest == "tmpl_personal_v7"
    assert captured == {
        "pack_id": "pptp-generic",
        "version": 7,
        "owner_id": "owner-generic",
    }


def test_shadow_chapter_request_is_explicitly_v6_and_read_only() -> None:
    request = SlideDeckVariantBuildRequest.model_validate({
        "engine_version": "v6",
        "shadow_only": True,
        "chapter_id": "chapter-1",
    })

    assert request.shadow_only is True
    assert request.chapter_id == "chapter-1"

    with pytest.raises(ValidationError):
        SlideDeckVariantBuildRequest.model_validate({
            "engine_version": "v5",
            "shadow_only": True,
            "chapter_id": "chapter-1",
        })
    with pytest.raises(ValidationError):
        SlideDeckVariantBuildRequest.model_validate({
            "engine_version": "v6",
            "shadow_only": True,
        })
    with pytest.raises(ValidationError):
        SlideDeckVariantBuildRequest.model_validate({
            "engine_version": "v6",
            "chapter_id": "chapter-1",
        })


def test_shadow_candidate_reader_rejects_public_or_cross_course_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(representation_router, "DATA_DIR", tmp_path)
    repository = SlideDeckV6CandidateRepository(tmp_path / "slide_deck_v6_candidates")
    repository.save("shadow-task", {
        "schema_version": "slide_deck_v6_candidate_v1",
        "task_id": "shadow-task",
        "course_id": "course-a",
        "status": "v6_ready",
        "published": False,
        "shadow_context": {"chapter_id": "chapter-a"},
        "deck": {"schema_version": "slide_deck_v6"},
    })
    repository.save("public-task", {
        "schema_version": "slide_deck_v6_candidate_v1",
        "task_id": "public-task",
        "course_id": "course-a",
        "status": "v6_ready",
        "published": True,
        "shadow_context": {},
    })

    assert representation_router._load_v6_shadow_candidate(
        "course-a",
        "shadow-task",
    )["shadow_context"]["chapter_id"] == "chapter-a"
    with pytest.raises(HTTPException) as public_error:
        representation_router._load_v6_shadow_candidate("course-a", "public-task")
    with pytest.raises(HTTPException) as cross_course_error:
        representation_router._load_v6_shadow_candidate("course-b", "shadow-task")

    assert public_error.value.status_code == 404
    assert cross_course_error.value.status_code == 404


def test_official_stream_enqueues_the_frozen_read_only_shadow_contract(tmp_path, monkeypatch) -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-route-shadow",
        title="Generic observations",
        sections=[CourseSection(section_id="chapter-1", title="Observe", position=0)],
        blocks=[CourseBlock(
            block_id="observation",
            section_id="chapter-1",
            position=0,
            role="concept",
            payload={"markdown": "Record the object, time, and context."},
        )],
    ))
    course_view = {**_ready_course(), "course_id": document.course_id}
    captured: dict[str, object] = {}

    class Repository:
        def load_document(self, _course_id):
            return document, True

        def load_course_view(self, _course_id):
            return course_view

    class TaskManager:
        async def create_task(self, course_id, task_type, **kwargs):
            captured.update(course_id=course_id, task_type=task_type, **kwargs)
            return "shadow-task"

        def get_task(self, _task_id):
            return {
                "status": "completed",
                "event_history": [{
                    "sequence": 1,
                    "event": "build_complete",
                    "build": {"candidate_status": "v6_ready", "published": False},
                }],
            }

    async def existing_course(_course_id):
        return course_view

    monkeypatch.setattr(representation_router, "get_course_document_repository", lambda: Repository())
    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: TeachingRepresentationRepository(tmp_path / "registry"),
    )
    monkeypatch.setattr(representation_router, "get_task_manager_optional", lambda: TaskManager())
    monkeypatch.setattr(representation_router, "get_course_or_404", existing_course)
    monkeypatch.setenv("SLIDE_DECK_V6_ENABLED", "true")
    app = FastAPI()
    app.include_router(representation_router.router, prefix="/api")
    client = TestClient(app)

    with client.stream(
        "POST",
        f"/api/courses/{document.course_id}/teaching-representations/slide-decks/build/stream",
        headers={"X-User-Id": "teacher-shadow"},
        json={
            "engine_version": "v6",
            "shadow_only": True,
            "chapter_id": "chapter-1",
        },
    ) as response:
        stream = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: build_complete" in stream
    snapshot = captured["request_snapshot"]
    assert snapshot["target_schema"] == "slide_deck_v6"
    assert snapshot["shadow_only"] is True
    assert snapshot["chapter_id"] == "chapter-1"
    assert snapshot["source_course_document_revision"] == document.document_revision
