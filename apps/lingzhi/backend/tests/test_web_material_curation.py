"""教师剔除名单的**持久化**：跨生成轮次仍然生效。

原实现只把剔除放在前端组件的 ref 里，刷新即失效、也从未随请求发出。
这里覆盖持久层本身：规整、读回、与请求级剔除合并。
过滤执行仍由 `web_material_search` 负责（见 test_web_material_teacher_control）。
"""

from __future__ import annotations

import pytest

from web_material_curation import (
    CURATION_METADATA_KEY,
    load_course_exclusions,
    merge_ingest_exclusions,
    normalize_exclusions,
)
from web_material_search import discover_web_materials

ENABLED = {"retrieval": {"enabled": True}}
FEATURE = {"provider": "searxng", "enabled_for_user": True}


def _source(source_id: str, url: str) -> dict:
    return {
        "schema_version": "retrieval_source_v1",
        "source_id": source_id,
        "url": url,
        "canonical_url": url,
        "domain": url.split("/")[2],
        "title": f"标题 {source_id}",
        "excerpt": "导数刻画瞬时变化率，是微积分的核心概念。" * 12,
        "published_date": "2024-03-01",
        "retrieved_at": "2026-08-05T00:00:00+00:00",
        "content_hash": f"hash-{source_id}",
        "provider": "searxng",
        "relevance": 0.9,
        "trust_tier": "tier_a",
        "license": None,
        "reuse_policy": "summary_only",
        "accepted_for_generation": True,
        "rejection_reasons": [],
    }


PAGES = [
    _source("src_open", "https://openstax.org/derivative-intro"),
    _source("src_mit", "https://mit.edu/ocw/limits"),
]


class FakeGateway:
    async def retrieve(self, request):
        return {
            "schema_version": "retrieval_package_v1",
            "status": "ok",
            "queries": list(request.queries),
            "sources": list(PAGES),
            "rejected_sources": [],
            "errors": [],
            "retrieved_at": "2026-08-05T00:00:00+00:00",
            "package_hash": "pkg",
            "receipt": {"status": "ok"},
        }


def test_normalize_dedupes_and_canonicalizes():
    result = normalize_exclusions({
        "excluded_source_ids": [" src_a ", "", "src_a", None],
        "excluded_urls": ["HTTPS://WWW.Example.com/Path/", "https://example.com/Path"],
    })
    assert result["excluded_source_ids"] == ["src_a"]
    # 大小写、www.、末尾斜杠都要归一，否则同一条会被存成两份、比对不上。
    assert result["excluded_urls"] == ["https://example.com/Path"]


def test_load_returns_empty_list_when_never_curated():
    """没有记录时给空名单而不是 None，调用方不必到处判空。"""
    assert load_course_exclusions({}) == {
        "excluded_source_ids": [],
        "excluded_urls": [],
    }
    assert load_course_exclusions(None)["excluded_urls"] == []


def test_load_reads_persisted_metadata_key():
    course = {CURATION_METADATA_KEY: {"excluded_source_ids": ["src_mit"]}}
    assert load_course_exclusions(course)["excluded_source_ids"] == ["src_mit"]


def test_load_ignores_malformed_metadata():
    assert load_course_exclusions({CURATION_METADATA_KEY: "nonsense"})[
        "excluded_source_ids"
    ] == []


def test_merge_is_union_of_request_and_persisted():
    merged = merge_ingest_exclusions(
        {"excluded_source_ids": ["req_only"], "skip_ingest": False},
        {"excluded_source_ids": ["stored_only"], "excluded_urls": ["https://x.test/a"]},
    )
    assert set(merged["excluded_source_ids"]) == {"req_only", "stored_only"}
    assert merged["excluded_urls"] == ["https://x.test/a"]
    # 合并不能丢掉 ingest_settings 里的其他键。
    assert merged["skip_ingest"] is False


def test_merge_tolerates_missing_inputs():
    assert merge_ingest_exclusions(None, None) == {
        "excluded_source_ids": [],
        "excluded_urls": [],
    }


@pytest.mark.asyncio
async def test_persisted_exclusion_removes_source_from_next_generation():
    """端到端：只有持久名单（请求里没写），下一轮生成也不能再出现该来源。"""
    stored = {CURATION_METADATA_KEY: {"excluded_source_ids": ["src_mit"]}}
    report = await discover_web_materials(
        topic="导数",
        requirements="希望学生掌握导数的几何意义",
        generation_request=ENABLED,
        gateway=FakeGateway(),
        feature=FEATURE,
        ingest_settings=merge_ingest_exclusions(
            {}, load_course_exclusions(stored)
        ),
    )
    urls = {item["url"] for item in report["candidates"]}
    assert "https://mit.edu/ocw/limits" not in urls
    assert "https://openstax.org/derivative-intro" in urls
    reasons = {item["source_id"]: item["reason"] for item in report["rejected"]}
    assert reasons["src_mit"] == "excluded_by_teacher"
