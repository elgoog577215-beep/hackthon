"""验证联网检索在 CourseService 与产物层的接线是真实生效的。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_generation.service import CourseService
from course_generation.workflow import build_course_generation_artifacts
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
async def test_explicit_retrieval_request_cannot_bypass_product_freeze(monkeypatch):
    service = CourseService()
    phases: list[dict] = []

    async def on_phase(*args, **kwargs):
        phases.append(kwargs)

    called = False

    async def boom(**_kwargs):
        nonlocal called
        called = True
        raise RuntimeError("provider must not be called")

    import web_material_search

    monkeypatch.setattr(web_material_search, "discover_web_materials", boom)

    report = await service._run_web_material_search(
        topic="导数",
        requirements="需要真实案例",
        target_audience="高中生",
        generation_request={"retrieval": {"enabled": True}},
        on_phase=on_phase,
    )

    assert report["status"] == "disabled"
    assert report["degraded"] is False
    assert report["message_code"] == "course_web_research_frozen"
    assert report["candidates"] == []
    assert called is False
    assert phases == []


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


def test_persisted_course_carries_web_summary_for_teacher_panel():
    """真实生成后教师端面板要能拿到联网汇总。

    产物层设了 web_material_search，但落库的 course_data 曾漏掉这一键，
    导致真实生成完成后审阅面板无数据（2026-08-08 真实跑通时发现）。
    """
    import inspect

    import course_generation.service as course_service
    source = inspect.getsource(course_service.CourseService.build_course_draft)
    # 历史字段继续保留，保证代码与旧数据可兼容恢复。
    assert source.count('"web_material_search": artifacts.get(') >= 2


@pytest.mark.asyncio
async def test_frozen_search_emits_no_teacher_review_phase(monkeypatch):
    """采纳来源必须出现在 phase_detail.web_search.sources。

    前端复核面板读的就是这个键。改动前 phase_detail 只做了
    `k != "candidates"` 的过滤，既没有 candidates 也没有 sources，
    于是教师只看得到关键词和被拒项，采纳列表永远是空的——
    "能看到采用了哪些来源、并逐条剔除"这一整段因此形同虚设。
    """
    service = CourseService()
    details: list[dict] = []

    async def on_phase(*args, **kwargs):
        # _notify_phase 是**位置传参**：(phase, progress, message,
        # phase_progress, phase_detail)，phase_detail 不是关键字参数。
        detail = args[4] if len(args) > 4 else kwargs.get("phase_detail")
        if detail:
            details.append(detail)

    async def fake_discover(**_kwargs):
        return {
            "enabled": True,
            "status": "ready",
            "degraded": False,
            "message_code": "web_search_ready",
            "queries": ["导数 定义"],
            "rejected": [],
            "candidates": [{
                "source_id": "src_open",
                "url": "https://openstax.org/derivative-intro",
                "domain": "openstax.org",
                "title": "导数的直观引入",
                "credibility": "high",
                "retrieved_at": "2026-08-05T00:00:00+00:00",
                "license": "",
                "reuse_policy": "summary_only",
                "sensitivity": {},
                "accepted_for_generation": True,
                "text": "正文不应出现在给前端的摘要里" * 20,
            }],
        }

    import web_material_search

    monkeypatch.setattr(
        web_material_search, "discover_web_materials", fake_discover
    )

    report = await service._run_web_material_search(
        topic="导数",
        requirements="需要真实案例",
        target_audience="高中生",
        generation_request={"retrieval": {"enabled": True}},
        on_phase=on_phase,
    )

    assert report["status"] == "disabled"
    assert details == []


@pytest.mark.asyncio
async def test_frozen_search_neither_calls_provider_nor_notifies(monkeypatch):
    service = CourseService()
    details: list[dict] = []

    async def on_phase(*args, **kwargs):
        # _notify_phase 是**位置传参**：(phase, progress, message,
        # phase_progress, phase_detail)，phase_detail 不是关键字参数。
        detail = args[4] if len(args) > 4 else kwargs.get("phase_detail")
        if detail:
            details.append(detail)

    called = False

    async def boom(**_kwargs):
        nonlocal called
        called = True
        raise RuntimeError("provider must not be called")

    import web_material_search

    monkeypatch.setattr(web_material_search, "discover_web_materials", boom)

    report = await service._run_web_material_search(
        topic="导数",
        requirements="需要真实案例",
        target_audience="高中生",
        generation_request={"retrieval": {"enabled": True}},
        on_phase=on_phase,
    )

    assert report["status"] == "disabled"
    assert report["message_code"] == "course_web_research_frozen"
    assert called is False
    assert details == []
