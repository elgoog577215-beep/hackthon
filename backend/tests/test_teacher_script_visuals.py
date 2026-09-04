import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from starlette.requests import Request

from slide_asset_repository import SlideAssetRepository
from teacher_script_visuals import (
    TeacherScriptVisualService,
    compile_inclined_plane_scene,
    compile_script_block_diagram,
    compile_script_block_scene,
    plan_script_block_scene,
    recommend_script_visuals,
)
from teaching_representations import RepresentationConflict, TeachingRepresentationRepository


class FakeImageProvider:
    api_base = ""
    model = ""
    configured = False

    def plan_prompt(self, *, source_text: str, style: str) -> str:
        return f"{style}: {source_text[:80]}"


class WorkingImageProvider(FakeImageProvider):
    api_base = "https://images.example.test/v1"
    model = "test-image-model"
    configured = True

    def generate(self, *, prompt: str, output_path: str | Path, **_kwargs) -> Path:
        target = Path(output_path)
        Image.new("RGB", (320, 180), color=(78, 70, 180)).save(target)
        return target


class InspectingImageProvider(WorkingImageProvider):
    def __init__(self, repository: TeachingRepresentationRepository) -> None:
        self.repository = repository

    def generate(self, *, prompt: str, output_path: str | Path, **kwargs) -> Path:
        registry = self.repository.load("course-1")
        candidate = next(
            item
            for item in registry.representations
            if item.representation_type == "image" and item.status == "candidate"
        )
        spec = next(item for item in registry.specs if item.spec_id == candidate.spec_id)
        assert spec.payload["content"]["prompt"] == prompt
        assert spec.payload["content"]["generation_status"] == "pending"
        assert candidate.artifact_ids == []
        return super().generate(prompt=prompt, output_path=output_path, **kwargs)


class FakeAnimationProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    async def _call_llm(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return json.dumps(self.payload, ensure_ascii=False)

    @staticmethod
    def _extract_json(response: str) -> dict:
        return json.loads(response)


def block(content: str = "系统先读取输入，然后建立概念关系，最后输出可检查结果。") -> dict:
    return {
        "block_id": "block-1",
        "role": "reasoning",
        "title": "处理过程",
        "content": content,
        "knowledge_names": ["输入", "关系", "结果"],
    }


def service(tmp_path, provider=None) -> TeacherScriptVisualService:
    return TeacherScriptVisualService(
        TeachingRepresentationRepository(tmp_path / "registry"),
        image_provider=provider or FakeImageProvider(),
        asset_repository=SlideAssetRepository(tmp_path / "assets"),
    )


def create(service: TeacherScriptVisualService, expression_type: str, revision: str = "script-r1"):
    return service.create_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id=revision,
        section_node_id="section-1",
        block=block(),
        expression_type=expression_type,
    )


def test_diagram_and_scene_are_bounded_source_specs():
    diagram = compile_script_block_diagram(
        section_node_id="section-1",
        block_id="block-1",
        title="处理过程",
        content=block()["content"],
    )
    scene = compile_script_block_scene(
        section_node_id="section-1",
        block_id="block-1",
        title="处理过程",
        content=block()["content"],
    )

    assert diagram["schema_version"] == "diagram_spec_v1"
    assert diagram["quality_report"]["passed"] is True
    assert diagram["units"][0]["source_block_ids"] == ["block-1"]
    assert scene["schema_version"] == "scene_spec_v1"
    assert len(scene["checkpoints"]) >= 2
    assert scene["static_fallback"]["type"] == "diagram_spec_unit"
    assert all(action["duration_ms"] >= 120 for action in scene["actions"])


def test_inclined_plane_scene_has_continuous_motion_rotation_and_trace():
    scene = compile_inclined_plane_scene(
        section_node_id="section-1",
        block_id="block-1",
        title="小球滚下斜面",
        content="小球从斜面高处由静止释放，沿斜面加速滚下。",
    )

    assert scene["schema_version"] == "scene_spec_v2"
    assert scene["scene_kind"] == "physical_motion"
    assert {item["kind"] for item in scene["objects"]} >= {"circle", "polygon", "path"}
    actions = {item["action_type"]: item for item in scene["actions"]}
    assert actions["move"]["target_id"] == "ball"
    assert actions["move"]["easing"] == "accelerate"
    assert len(actions["move"]["path"]) >= 3
    assert actions["rotate"]["to_rotation"] >= 360
    assert actions["trace"]["target_id"] == "trajectory"


def test_inclined_plane_fallback_does_not_invent_acceleration():
    scene = compile_inclined_plane_scene(
        section_node_id="section-1",
        block_id="block-1",
        title="小球滚下斜面",
        content="小球从斜面高处滚下。",
    )

    actions = {item["action_type"]: item for item in scene["actions"]}
    assert actions["move"]["easing"] == "linear"
    assert "速度变化" not in scene["learning_focus"]
    assert all(item["object_id"] != "speed_label" for item in scene["objects"])


def test_ai_scene_planner_keeps_motion_dsl_and_rejects_executable_code():
    planned = compile_inclined_plane_scene(
        section_node_id="section-1",
        block_id="block-1",
        title="斜面运动",
        content="小球沿斜坡滚下。",
    )
    planned.pop("generation_mode")
    planned.pop("static_fallback")
    provider = FakeAnimationProvider(planned)

    scene = asyncio.run(plan_script_block_scene(
        provider=provider,
        section_node_id="section-1",
        block_id="block-1",
        title="斜面运动",
        content="小球沿斜坡滚下。",
        instruction="突出加速和转动",
    ))

    assert scene["schema_version"] == "scene_spec_v2"
    assert scene["generation_mode"] == "ai_planned"
    assert scene["static_fallback"]["type"] == "diagram_spec_unit"
    assert any(item["action_type"] == "move" for item in scene["actions"])
    assert "JavaScript" in provider.calls[0]["system_prompt"]
    assert "不得擅自假设光滑斜面" in provider.calls[0]["system_prompt"]
    request = json.loads(provider.calls[0]["prompt"])
    assert request["constraints"]["no_unsupported_qualitative_claims"] is True
    assert provider.calls[0]["json_mode"] is True


def test_invalid_generic_ai_scene_fails_instead_of_becoming_a_playing_diagram():
    provider = FakeAnimationProvider({
        "schema_version": "scene_spec_v2",
        "title": "伪动画",
        "scene_kind": "process",
        "learning_focus": "测试",
        "duration_ms": 2000,
        "objects": [],
        "actions": [],
        "checkpoints": [],
    })

    with pytest.raises(RepresentationConflict, match="Animation scene planning failed"):
        asyncio.run(plan_script_block_scene(
            provider=provider,
            section_node_id="section-1",
            block_id="block-1",
            title="信息处理",
            content="系统读取输入并产生输出。",
        ))


def test_ai_animation_candidate_persists_scene_v2(tmp_path):
    planned = compile_inclined_plane_scene(
        section_node_id="section-1",
        block_id="block-1",
        title="斜面运动",
        content="小球沿斜面滚下。",
    )
    planned.pop("generation_mode")
    planned.pop("static_fallback")
    visual_service = service(tmp_path)

    candidate = asyncio.run(visual_service.create_candidate_with_ai_animation(
        provider=FakeAnimationProvider(planned),
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        section_node_id="section-1",
        block=block("小球从斜面高处释放，沿斜面加速滚下。"),
    ))

    assert candidate["content"]["schema_version"] == "scene_spec_v2"
    assert candidate["content"]["generation_mode"] == "ai_planned"
    assert candidate["status"] == "candidate"


def test_recommendation_identifies_process_as_animation_candidate():
    result = recommend_script_visuals([block()])

    assert result[0]["recommended_types"] == ["animation", "diagram"]
    assert "逐步" in result[0]["reason"]


def test_candidate_acceptance_builds_shared_representation_set(tmp_path):
    visual_service = service(tmp_path)
    candidate = create(visual_service, "diagram")

    assert candidate["status"] == "candidate"
    accepted = visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=candidate["representation_id"],
        accept=True,
    )
    registry = visual_service.repository.load("course-1")

    assert accepted["status"] == "accepted"
    assert registry.representation_sets[0].default_representation_id == candidate["representation_id"]
    assert registry.representation_sets[0].selection_policy["consumer_targets"] == [
        "teacher_script", "slide_deck", "learner",
    ]


def test_all_consumers_receive_the_same_accepted_representation_and_spec(tmp_path):
    visual_service = service(tmp_path)
    candidate = create(visual_service, "diagram")
    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=candidate["representation_id"],
        accept=True,
    )

    projections = [
        visual_service.repository.accepted_sets_for_consumer(
            "course-1",
            consumer=consumer,
            lesson_unit_id="lesson-1",
        )
        for consumer in ("teacher_script", "slide_deck", "learner")
    ]
    representation_ids = {
        projection["items"][0]["representation"]["representation_id"]
        for projection in projections
    }
    spec_ids = {
        projection["items"][0]["spec"]["spec_id"]
        for projection in projections
    }

    assert representation_ids == {candidate["representation_id"]}
    assert len(spec_ids) == 1
    assert all(
        projection["representation_sets"][0]["default_representation_id"]
        == candidate["representation_id"]
        for projection in projections
    )


def test_shared_consumer_api_returns_only_accepted_lesson_scope(tmp_path, monkeypatch):
    from routers import teaching_representations as representation_router

    visual_service = service(tmp_path)
    accepted = create(visual_service, "diagram")
    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=accepted["representation_id"],
        accept=True,
    )
    create(visual_service, "animation")

    async def existing_course(_course_id: str):
        return {"course_id": "course-1"}

    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: visual_service.repository,
    )
    monkeypatch.setattr(representation_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(representation_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "teacher-1"})

    response = client.get(
        "/api/courses/course-1/teaching-representations/accepted",
        params={"consumer": "slide_deck", "lesson_unit_id": "lesson-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["consumer"] == "slide_deck"
    assert [
        item["representation"]["representation_id"] for item in payload["items"]
    ] == [accepted["representation_id"]]


def test_visual_route_preserves_scoped_script_not_ready_error(monkeypatch):
    from dependencies import (
        get_teacher_lesson_authoring_repository,
        require_task_manager,
    )
    from routers import teacher_lesson_authoring as authoring_router
    from teacher_lesson_authoring import TeacherLessonAuthoringError

    def unavailable_context(*_args, **_kwargs):
        raise TeacherLessonAuthoringError(
            "lesson_script_source_incomplete",
            "当前讲义内容不完整，暂时不能添加视觉表达。",
        )

    monkeypatch.setattr(
        authoring_router,
        "_current_script_visual_context",
        unavailable_context,
    )
    app = FastAPI()
    app.include_router(authoring_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: object()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: object()
    client = TestClient(app, headers={"X-User-Id": "teacher-1"})

    response = client.get(
        "/api/teacher/courses/course-1/lessons/lesson-1/script/visuals"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_script_source_incomplete"


def test_shared_consumer_projection_excludes_candidates_and_stale_members(tmp_path):
    visual_service = service(tmp_path)
    candidate = create(visual_service, "animation")

    before_acceptance = visual_service.repository.accepted_sets_for_consumer(
        "course-1", consumer="learner", lesson_unit_id="lesson-1"
    )
    assert before_acceptance["items"] == []
    assert before_acceptance["representation_sets"] == []

    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=candidate["representation_id"],
        accept=True,
    )
    visual_service.list_for_lesson(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r2",
        blocks=[block("讲义已经变化。")],
    )
    after_revision_change = visual_service.repository.accepted_sets_for_consumer(
        "course-1", consumer="learner", lesson_unit_id="lesson-1"
    )

    assert after_revision_change["items"] == []
    assert after_revision_change["representation_sets"] == []


def test_regeneration_archives_old_candidate_and_replacement_archives_old_acceptance(tmp_path):
    visual_service = service(tmp_path)
    first = create(visual_service, "diagram")
    second = create(visual_service, "diagram")
    registry = visual_service.repository.load("course-1")
    states = {item.representation_id: item.status for item in registry.representations}

    assert states[first["representation_id"]] == "archived"
    assert states[second["representation_id"]] == "candidate"
    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=second["representation_id"],
        accept=True,
    )
    third = create(visual_service, "diagram")
    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=third["representation_id"],
        accept=True,
    )
    registry = visual_service.repository.load("course-1")
    states = {item.representation_id: item.status for item in registry.representations}

    assert states[second["representation_id"]] == "archived"
    assert states[third["representation_id"]] == "accepted"
    assert registry.representation_sets[0].default_representation_id == third["representation_id"]


def test_script_revision_change_marks_existing_visual_stale(tmp_path):
    visual_service = service(tmp_path)
    candidate = create(visual_service, "animation")
    visual_service.resolve_candidate(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r1",
        representation_id=candidate["representation_id"],
        accept=True,
    )

    view = visual_service.list_for_lesson(
        course_id="course-1",
        lesson_unit_id="lesson-1",
        script_revision_id="script-r2",
        blocks=[block("讲义已经变化。")],
    )

    assert view["items"][0]["status"] == "stale"
    assert "source_revision_changed:teacher_script:lesson-1" in view["items"][0]["stale_reasons"]

    with pytest.raises(RepresentationConflict, match="Stale teaching representation"):
        visual_service.resolve_candidate(
            course_id="course-1",
            lesson_unit_id="lesson-1",
            script_revision_id="script-r2",
            representation_id=candidate["representation_id"],
            accept=True,
        )


def test_candidate_cannot_be_resolved_from_another_course(tmp_path):
    visual_service = service(tmp_path)
    candidate = create(visual_service, "diagram")

    with pytest.raises(RepresentationConflict, match="does not exist"):
        visual_service.resolve_candidate(
            course_id="course-2",
            lesson_unit_id="lesson-1",
            script_revision_id="script-r1",
            representation_id=candidate["representation_id"],
            accept=True,
        )

    assert visual_service.repository.load("course-2").representations == []


def test_unconfigured_image_provider_keeps_prompt_without_fake_asset(tmp_path):
    visual_service = service(tmp_path, FakeImageProvider())
    candidate = create(visual_service, "image")

    assert candidate["content"]["generation_status"] == "provider_unavailable"
    assert candidate["content"]["prompt"]
    assert candidate["artifact_ids"] == []
    with pytest.raises(RepresentationConflict, match="no verified asset"):
        visual_service.resolve_candidate(
            course_id="course-1",
            lesson_unit_id="lesson-1",
            script_revision_id="script-r1",
            representation_id=candidate["representation_id"],
            accept=True,
        )


def test_configured_image_provider_persists_verified_immutable_asset(tmp_path):
    visual_service = service(tmp_path, WorkingImageProvider())
    candidate = create(visual_service, "image")
    asset_id = candidate["artifact_ids"][0]
    asset = visual_service.asset_repository.get(asset_id)

    assert candidate["content"]["generation_status"] == "ready"
    assert asset is not None
    assert asset.course_id == "course-1"
    assert visual_service.asset_repository.resolve(asset_id).is_file()


def test_image_prompt_is_persisted_before_provider_execution(tmp_path):
    repository = TeachingRepresentationRepository(tmp_path / "registry")
    visual_service = TeacherScriptVisualService(
        repository,
        image_provider=InspectingImageProvider(repository),
        asset_repository=SlideAssetRepository(tmp_path / "assets"),
    )

    candidate = create(visual_service, "image")

    assert candidate["content"]["generation_status"] == "ready"
    assert candidate["content"]["prompt"]


def test_image_asset_route_rejects_manifest_hash_mismatch(tmp_path, monkeypatch):
    from routers import teaching_representations as representation_router

    visual_service = service(tmp_path, WorkingImageProvider())
    candidate = create(visual_service, "image")
    asset_id = candidate["artifact_ids"][0]
    registry = visual_service.repository.load("course-1")
    representation = next(
        item
        for item in registry.representations
        if item.representation_id == candidate["representation_id"]
    )
    spec = next(
        item for item in registry.specs if item.spec_id == representation.spec_id
    )
    spec.payload["content"]["visual_asset_manifest"][0]["sha256"] = "0" * 64
    visual_service.repository.save(registry)
    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: visual_service.repository,
    )
    monkeypatch.setattr(
        representation_router,
        "slide_asset_repository",
        visual_service.asset_repository,
    )
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-user-id", b"teacher-1")],
    })

    with pytest.raises(HTTPException) as caught:
        asyncio.run(representation_router.get_teaching_slide_asset(
            "course-1",
            candidate["representation_id"],
            asset_id,
            request,
        ))

    assert caught.value.status_code == 409
    assert caught.value.detail == "Teaching visual asset manifest mismatch"
