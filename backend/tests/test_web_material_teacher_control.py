"""教师可控：搜了什么可见、采用了哪些可见、不想要的能逐条剔除。"""

from __future__ import annotations

import pytest

from web_material_search import discover_web_materials

ENABLED = {"retrieval": {"enabled": True}}
FEATURE = {"provider": "searxng", "enabled_for_user": True}


def _source(source_id: str, url: str, title: str, tier: str = "tier_a") -> dict:
    return {
        "schema_version": "retrieval_source_v1",
        "source_id": source_id,
        "url": url,
        "canonical_url": url,
        "domain": url.split("/")[2],
        "title": title,
        "excerpt": "导数刻画瞬时变化率，是微积分的核心概念。" * 12,
        "published_date": "2024-03-01",
        "retrieved_at": "2026-08-05T00:00:00+00:00",
        "content_hash": f"hash-{source_id}",
        "provider": "searxng",
        "relevance": 0.9,
        "trust_tier": tier,
        "license": None,
        "reuse_policy": "summary_only",
        "accepted_for_generation": tier == "tier_a",
        "rejection_reasons": [],
    }


PAGES = [
    _source("src_open", "https://openstax.org/derivative-intro", "导数的直观引入"),
    _source("src_mit", "https://mit.edu/ocw/limits", "极限与导数"),
]


class FakeGateway:
    def __init__(self, sources):
        self.sources = sources

    async def retrieve(self, request):
        return {
            "schema_version": "retrieval_package_v1",
            "status": "ok",
            "queries": list(request.queries),
            "sources": list(self.sources),
            "rejected_sources": [],
            "errors": [],
            "retrieved_at": "2026-08-05T00:00:00+00:00",
            "package_hash": "pkg",
            "receipt": {"status": "ok"},
        }


async def _run(**kwargs):
    return await discover_web_materials(
        topic="导数",
        requirements="希望学生掌握导数的几何意义",
        generation_request=ENABLED,
        gateway=FakeGateway(PAGES),
        feature=FEATURE,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_report_shows_queries_and_adopted_sources():
    """教师能看到搜了什么、采用了哪些。"""
    report = await _run()

    assert report["status"] == "ready"
    assert report["queries"], "必须回传实际使用的检索词"
    adopted = {item["url"] for item in report["candidates"]}
    assert adopted == {page["url"] for page in PAGES}
    for candidate in report["candidates"]:
        assert candidate["retrieved_at"] == "2026-08-05T00:00:00+00:00"
        assert candidate["credibility"] in {"high", "medium", "low"}


@pytest.mark.asyncio
async def test_teacher_can_exclude_by_source_id():
    """逐条剔除：只去掉一条，不影响其他资料。"""
    report = await _run(ingest_settings={"excluded_source_ids": ["src_mit"]})

    assert {item["url"] for item in report["candidates"]} == {
        "https://openstax.org/derivative-intro"
    }
    reasons = {item["source_id"]: item["reason"] for item in report["rejected"]}
    assert reasons["src_mit"] == "excluded_by_teacher"


@pytest.mark.asyncio
async def test_teacher_can_exclude_by_url():
    report = await _run(ingest_settings={"excluded_urls": ["https://mit.edu/ocw/limits"]})
    assert "https://mit.edu/ocw/limits" not in {
        item["url"] for item in report["candidates"]
    }


@pytest.mark.asyncio
async def test_exclusion_ignores_trailing_slash_and_case():
    """剔除比对要归一化，否则教师点掉的那条会因为末尾斜杠又回来。"""
    report = await _run(ingest_settings={"excluded_urls": ["HTTPS://MIT.EDU/ocw/limits/"]})
    assert "https://mit.edu/ocw/limits" not in {
        item["url"] for item in report["candidates"]
    }


@pytest.mark.asyncio
async def test_excluding_everything_degrades_to_no_results():
    report = await _run(ingest_settings={"excluded_source_ids": ["src_open", "src_mit"]})
    assert report["candidates"] == []
    assert report["status"] == "no_results"
    assert report["degraded"] is True
