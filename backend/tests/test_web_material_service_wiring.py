"""验证联网检索在 CourseService 与产物层的接线是真实生效的。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_service import CourseService
from course_generation_workflow import build_course_generation_artifacts
from models import CourseGenerationRequest, WebMaterialIngestInput


@pytest.mark.asyncio
async def test_disabled_retrieval_skips_search_and_never_notifies():
    service = CourseService()
    phases: list[tuple] = []

    async def on_phase(*args, **kwargs):
        phases.append((args, kwargs))

    report = await service._run_web_material_search(
        topic="导数",
        requirements="需要真实案例",
        target_audience="高中生",
        generation_request={"retrieval": {"enabled": False}},
        on_phase=on_phase,
    )

    assert report["enabled"] is False
    assert report["status"] == "disabled"
    assert report["candidates"] == []
    # 关闭时不应产生联网阶段通知
    assert phases == []


@pytest.mark.asyncio
async def test_missing_retrieval_authorization_defaults_to_disabled():
    """没有显式 retrieval 授权时默认不联网。"""
    service = CourseService()
    report = await service._run_web_material_search(
        topic="导数",
        requirements="",
        target_audience="",
        generation_request={},
        on_phase=None,
    )
    assert report["status"] == "disabled"
    assert report["candidates"] == []


@pytest.mark.asyncio
async def test_legacy_question_enrichment_does_not_grant_course_scope():
    """旧的题库联网开关只覆盖 assessment，不应放行课程资料检索。"""
    service = CourseService()
    report = await service._run_web_material_search(
        topic="导数",
        requirements="",
        target_audience="",
        generation_request={"web_question_enrichment": {"enabled": True}},
        on_phase=None,
    )
    assert report["status"] == "disabled"


@pytest.mark.asyncio
async def test_provider_failure_degrades_instead_of_breaking_generation(monkeypatch):
    service = CourseService()
    phases: list[dict] = []

    async def on_phase(*args, **kwargs):
        phases.append(kwargs)

    async def boom(**_kwargs):
        raise RuntimeError("provider down")

    import web_material_search

    monkeypatch.setattr(web_material_search, "discover_web_materials", boom)

    report = await service._run_web_material_search(
        topic="导数",
        requirements="需要真实案例",
        target_audience="高中生",
        generation_request={"retrieval": {"enabled": True}},
        on_phase=on_phase,
    )

    assert report["status"] == "degraded"
    assert report["degraded"] is True
    assert report["message_code"] == "web_search_unavailable"
    assert report["candidates"] == []


def test_artifacts_expose_web_search_summary():
    artifacts = build_course_generation_artifacts(
        course_id="c1",
        topic="导数",
        difficulty="intermediate",
        style="academic",
        composition_style="balanced",
        requirements="",
        target_audience="高中生",
        materials=[],
        learner_profile_summary="",
        prepared_materials={
            "web_search": {
                "enabled": True,
                "status": "ready",
                "queries": ["导数 定义"],
                "candidates": [{"url": "https://example.edu/a"}],
            }
        },
    )
    summary = artifacts["web_material_search"]
    assert summary["enabled"] is True
    assert summary["queries"] == ["导数 定义"]


def test_artifacts_default_web_summary_when_absent():
    artifacts = build_course_generation_artifacts(
        course_id="c1",
        topic="导数",
        difficulty="intermediate",
        style="academic",
        composition_style="balanced",
        requirements="",
        target_audience="高中生",
        materials=[],
        learner_profile_summary="",
    )
    assert artifacts["web_material_search"] == {"enabled": False}


def test_request_model_defaults_to_no_retrieval_and_no_exclusions():
    request = CourseGenerationRequest(topic="导数", subject="数学")
    assert request.retrieval.enabled is False
    assert request.web_material_ingest.skip_ingest is False
    assert request.web_material_ingest.excluded_source_ids == []


def test_ingest_model_normalizes_comma_separated_exclusions():
    payload = WebMaterialIngestInput(
        excluded_source_ids="src_a, src_b",
        excluded_urls="",
    )
    assert payload.excluded_source_ids == ["src_a", "src_b"]
    assert payload.excluded_urls == []
