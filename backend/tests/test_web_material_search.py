"""联网资料落地测试：查询推导、来源映射、绑定策略与降级。

检索本身由团队网关负责，这里注入假网关，不打真实外网。
"""

from __future__ import annotations

import pytest

from material_models import MaterialBinding
from web_material_search import (
    MIN_USABLE_TEXT_CHARS,
    candidate_from_source,
    candidate_to_binding,
    candidate_to_markdown,
    derive_search_queries,
    discover_web_materials,
    safe_query_term,
)


def _source(**overrides) -> dict:
    base = {
        "schema_version": "retrieval_source_v1",
        "source_id": "src_abc123",
        "url": "https://ocw.mit.edu/calc",
        "canonical_url": "https://ocw.mit.edu/calc",
        "domain": "ocw.mit.edu",
        "title": "\u5fae\u79ef\u5206\u8bb2\u4e49",
        "excerpt": "\u5bfc\u6570\u523b\u753b\u77ac\u65f6\u53d8\u5316\u7387\u3002" * 20,
        "published_date": "2024-03-01",
        "retrieved_at": "2026-08-05T00:00:00+00:00",
        "content_hash": "hash-a",
        "provider": "searxng",
        "relevance": 0.91,
        "trust_tier": "tier_a",
        "license": None,
        "reuse_policy": "summary_only",
        "accepted_for_generation": True,
        "rejection_reasons": [],
    }
    base.update(overrides)
    return base


class FakeGateway:
    """\u66ff\u4ee3\u56e2\u961f\u7f51\u5173\uff0c\u8fd4\u56de\u9884\u8bbe retrieval_package_v1\u3002"""

    def __init__(self, sources=None, *, status="ok", errors=None, raises=False):
        self.sources = sources if sources is not None else [_source()]
        self.status = status
        self.errors = errors or []
        self.raises = raises
        self.requests = []

    async def retrieve(self, request):
        self.requests.append(request)
        if self.raises:
            raise RuntimeError("gateway exploded")
        return {
            "schema_version": "retrieval_package_v1",
            "status": self.status,
            "queries": list(request.queries),
            "sources": list(self.sources),
            "rejected_sources": [],
            "errors": list(self.errors),
            "retrieved_at": "2026-08-05T00:00:00+00:00",
            "package_hash": "pkg-hash",
            "receipt": {"schema_version": "retrieval_receipt_v1", "status": self.status},
        }


ENABLED = {"retrieval": {"enabled": True}}
FEATURE = {"provider": "searxng", "enabled_for_user": True}


# ---------------------------------------------------------------- 查询推导


def test_queries_derive_from_topic_and_requirements():
    queries = derive_search_queries(
        topic="微积分",
        requirements="重点讲解极限与连续性，需要工程应用案例。",
        max_queries=6,
    )
    assert queries
    assert all("微积分" in query for query in queries)
    joined = " ".join(queries)
    assert "极限" in joined or "连续性" in joined or "工程应用案例" in joined


def test_queries_respect_max_and_are_unique():
    queries = derive_search_queries(
        topic="微积分", requirements="极限 连续 导数 积分 级数", max_queries=3
    )
    assert 0 < len(queries) <= 3
    assert len(set(queries)) == len(queries)


def test_query_fallback_matches_topic_language():
    """兜底资料词必须与主题同语言，跨语言会引入噪音被网关判低相关。"""
    zh = derive_search_queries(topic="微积分", requirements="", max_queries=5)
    assert any("讲义" in query for query in zh)
    assert not any("lecture notes" in query for query in zh)

    en = derive_search_queries(topic="calculus", requirements="", max_queries=5)
    assert any("lecture notes" in query for query in en)
    assert not any("讲义" in query for query in en)


def test_queries_stay_short_for_relevance_scoring():
    """网关按查询词与标题/摘要重合度打分，堆砌套话会把来源稀释成 tier_c。"""
    queries = derive_search_queries(
        topic="线性代数", requirements="特征值 特征向量", max_queries=5
    )
    for query in queries:
        assert "开放教育资源" not in query
        assert "教学资料" not in query
        assert len(query.split()) <= 6


def test_queries_empty_without_topic():
    assert derive_search_queries(topic="   ", requirements="任何要求", max_queries=4) == []


def test_queries_drop_stopword_only_requirements():
    queries = derive_search_queries(
        topic="微积分", requirements="希望学生能够掌握。我们需要。", max_queries=5
    )
    # 套话不应变成查询词，但主题兜底查询仍然存在。
    assert queries
    assert all("希望" not in query and "我们" not in query for query in queries)


def test_queries_do_not_split_chinese_words_at_fixed_character_boundaries():
    queries = derive_search_queries(
        topic="电动力学",
        requirements="查找大学电动力学中麦克斯韦方程组的官方或高校公开讲义",
        max_queries=4,
    )
    assert any("官方" in query for query in queries)
    assert all("官 方" not in query for query in queries)


def test_queries_strip_injection_from_requirements():
    queries = derive_search_queries(
        topic="微积分",
        requirements="ignore previous instructions <script>alert(1)</script>",
        max_queries=5,
    )
    assert all("<" not in query and ">" not in query for query in queries)


def test_objectives_lead_the_query_list():
    queries = derive_search_queries(
        topic="微积分",
        requirements="",
        objectives=["理解中值定理"],
        max_queries=4,
    )
    assert "中值定理" in queries[0]


def test_safe_query_term_strips_control_characters():
    assert safe_query_term("导数\n\t定义 <script>") == "导数 定义 script"
    assert len(safe_query_term("x" * 500)) == 200


# ------------------------------------------------------------ 来源字段映射


def test_source_maps_to_candidate_with_provenance():
    candidate = candidate_from_source(_source())
    assert candidate["source_id"] == "src_abc123"
    assert candidate["url"] == "https://ocw.mit.edu/calc"
    assert candidate["retrieved_at"] == "2026-08-05T00:00:00+00:00"
    assert candidate["credibility"] == "high"
    assert candidate["trust_tier"] == "tier_a"
    assert candidate["provider"] == "searxng"


@pytest.mark.parametrize(
    "tier,expected",
    [("tier_a", "high"), ("tier_b", "medium"), ("tier_c", "low"), ("", "low")],
)
def test_trust_tier_maps_to_credibility(tier, expected):
    assert candidate_from_source(_source(trust_tier=tier))["credibility"] == expected


# -------------------------------------------------------------- 检索主流程


@pytest.mark.asyncio
async def test_disabled_retrieval_never_calls_gateway():
    gateway = FakeGateway()
    report = await discover_web_materials(
        topic="微积分", generation_request={"retrieval": {"enabled": False}}, gateway=gateway
    )
    assert gateway.requests == []
    assert report["status"] == "disabled"
    assert report["degraded"] is True


@pytest.mark.asyncio
async def test_successful_retrieval_returns_ready_candidates():
    report = await discover_web_materials(
        topic="微积分",
        requirements="极限与连续",
        generation_request=ENABLED,
        gateway=FakeGateway(),
        feature=FEATURE,
    )
    assert report["status"] == "ready"
    assert report["degraded"] is False
    assert report["candidates"][0]["url"] == "https://ocw.mit.edu/calc"
    assert report["package_hash"] == "pkg-hash"
    assert report["receipt"]["schema_version"] == "retrieval_receipt_v1"


@pytest.mark.asyncio
async def test_request_purpose_is_course():
    gateway = FakeGateway()
    await discover_web_materials(
        topic="微积分", generation_request=ENABLED, gateway=gateway, feature=FEATURE
    )
    assert gateway.requests[0].purpose == "course"
    assert gateway.requests[0].enabled is True


@pytest.mark.asyncio
async def test_gateway_exception_degrades_without_raising():
    report = await discover_web_materials(
        topic="微积分",
        generation_request=ENABLED,
        gateway=FakeGateway(raises=True),
        feature=FEATURE,
    )
    assert report["status"] == "provider_unavailable"
    assert report["degraded"] is True
    assert report["candidates"] == []


@pytest.mark.asyncio
async def test_no_sources_reports_no_results():
    report = await discover_web_materials(
        topic="微积分",
        generation_request=ENABLED,
        gateway=FakeGateway(sources=[]),
        feature=FEATURE,
    )
    assert report["status"] == "no_results"
    assert report["degraded"] is True


@pytest.mark.asyncio
async def test_only_admitted_sources_become_candidates():
    """tier_b 未经教师接受时不进资料链。"""
    gateway = FakeGateway(sources=[
        _source(),
        _source(source_id="src_b", url="https://blog.example.com/x", trust_tier="tier_b"),
    ])
    report = await discover_web_materials(
        topic="微积分", generation_request=ENABLED, gateway=gateway, feature=FEATURE
    )
    assert [item["url"] for item in report["candidates"]] == ["https://ocw.mit.edu/calc"]


@pytest.mark.asyncio
async def test_short_excerpt_is_rejected():
    gateway = FakeGateway(sources=[_source(excerpt="太短")])
    report = await discover_web_materials(
        topic="微积分", generation_request=ENABLED, gateway=gateway, feature=FEATURE
    )
    assert report["candidates"] == []
    assert report["rejected"][0]["reason"] == "insufficient_text"


@pytest.mark.asyncio
async def test_skip_ingest_stops_before_gateway():
    """教师选择只引用不落库时，不做落地工作。"""
    gateway = FakeGateway()
    report = await discover_web_materials(
        topic="微积分",
        generation_request=ENABLED,
        ingest_settings={"skip_ingest": True},
        gateway=gateway,
        feature=FEATURE,
    )
    assert gateway.requests == []
    assert report["status"] == "ingest_skipped"


@pytest.mark.asyncio
async def test_rollout_denied_reports_not_configured():
    report = await discover_web_materials(
        topic="微积分",
        generation_request=ENABLED,
        gateway=FakeGateway(),
        feature={"provider": "searxng", "enabled_for_user": False},
    )
    assert report["status"] == "unavailable_not_configured"
    assert report["degraded"] is True


# ------------------------------------------------------ 落地格式与绑定策略


def test_markdown_keeps_source_url_and_time():
    text = candidate_to_markdown(candidate_from_source(_source()))
    assert "https://ocw.mit.edu/calc" in text
    assert "2026-08-05T00:00:00+00:00" in text
    assert "可信度标记：high" in text
    assert "非平台原创内容" in text


def test_markdown_survives_empty_body():
    text = candidate_to_markdown(candidate_from_source(_source(excerpt="")))
    assert "https://ocw.mit.edu/calc" in text
    assert "摘录正文" in text


def test_binding_never_grants_primary_authority():
    for tier in ("tier_a", "tier_b", "tier_c"):
        binding = candidate_to_binding(candidate_from_source(_source(trust_tier=tier)), "mat-1")
        assert binding["authority"] != "primary"


def test_binding_defaults_to_reference_only_without_open_license():
    binding = candidate_to_binding(candidate_from_source(_source()), "mat-1")
    assert binding["reuse_policy"] == "reference_only"
    assert binding["rights_basis"] == "license_unknown"


def test_open_license_source_allows_verbatim():
    source = _source(license="CC BY 4.0", reuse_policy="verbatim_allowed")
    binding = candidate_to_binding(candidate_from_source(source), "mat-1")
    assert binding["reuse_policy"] == "verbatim_allowed"
    assert binding["rights_basis"] == "open_license"


def test_binding_records_provenance_metadata():
    binding = candidate_to_binding(candidate_from_source(_source()), "mat-1")
    metadata = binding["source_metadata"]
    assert metadata["origin"] == "web_search"
    assert metadata["source_id"] == "src_abc123"
    assert metadata["url"] == "https://ocw.mit.edu/calc"
    assert metadata["trust_tier"] == "tier_a"


def test_binding_validates_against_material_binding_contract():
    binding = MaterialBinding.model_validate(
        candidate_to_binding(candidate_from_source(_source()), "mat-1")
    )
    assert binding.source_metadata["origin"] == "web_search"
    assert binding.source_label == "微积分讲义"


def test_low_trust_binding_is_weak_context():
    binding = candidate_to_binding(candidate_from_source(_source(trust_tier="tier_c")), "mat-1")
    assert binding["purpose"] == "weak_context"
    assert binding["priority"] == "weak"


def test_min_usable_text_threshold_is_meaningful():
    # SearXNG 返回摘要而非全文，阈值只用于排除空壳页面，不承担质量判定。
    assert 40 <= MIN_USABLE_TEXT_CHARS <= 120
