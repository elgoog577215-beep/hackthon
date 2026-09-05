from __future__ import annotations

import asyncio

import httpx
import pytest

from web_document_reader import (
    SafeWebDocumentReader,
    build_research_summary,
    diversify_retrieval_sources,
    enrich_web_candidates,
)


async def _public_resolver(_host: str, _port: int) -> bool:
    return True


@pytest.mark.asyncio
async def test_reader_extracts_article_structure_and_metadata():
    html = """
    <html><head><title>微积分公开课</title>
    <meta name="author" content="示例大学">
    <meta property="article:published_time" content="2026-08-01">
    </head><body><nav>无关导航</nav><article>
    <h1>导数</h1>
    <p>导数刻画函数在某一点的瞬时变化率，是微积分中的核心概念。</p>
    <h2>几何意义</h2>
    <p>从几何上看，导数对应曲线在该点切线的斜率。</p>
    <p>这一解释可以连接极限、局部线性近似以及后续的优化问题。</p>
    <p>为了达到正文提取的最低长度，本段继续说明导数可用于速度、边际量和误差分析。</p>
    <p>课程讲解时应区分平均变化率与瞬时变化率，并通过割线趋近切线建立直观。</p>
    """ + "".join(
        f"<p>补充说明第{index}部分：导数与极限、连续、微分和实际变化率问题之间存在紧密关系。</p>"
        for index in range(8)
    ) + """
    </article><footer>版权和菜单</footer></body></html>
    """

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SafeWebDocumentReader(
            client=client,
            resolver=_public_resolver,
        ).read("https://example.edu/calculus")

    assert result["status"] == "full_text"
    assert result["title"] == "微积分公开课"
    assert result["author"] == "示例大学"
    assert result["published_date"] == "2026-08-01"
    assert "# 导数" in result["text"]
    assert "无关导航" not in result["text"]
    assert result["headings"] == ["导数", "几何意义"]


@pytest.mark.asyncio
async def test_reader_rejects_private_and_unsafe_redirects():
    private = await SafeWebDocumentReader(resolver=_public_resolver).read(
        "https://127.0.0.1/private"
    )
    assert private["reason"] == "unsafe_url"

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://localhost/admin"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        redirected = await SafeWebDocumentReader(
            client=client,
            resolver=_public_resolver,
        ).read("https://example.edu/start")
    assert redirected["status"] == "excerpt_fallback"
    assert redirected["reason"] == "unsafe_redirect"


@pytest.mark.asyncio
async def test_enrichment_keeps_excerpt_when_full_text_fails():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    candidates = [{
        "source_id": "s1",
        "url": "https://example.edu/a",
        "domain": "example.edu",
        "title": "资料",
        "text": "搜索摘要仍然保留",
        "credibility": "high",
        "matched_query": "导数 官方",
    }]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        enriched = await enrich_web_candidates(
            candidates,
            reader=SafeWebDocumentReader(client=client, resolver=_public_resolver),
        )

    assert enriched[0]["text"] == "搜索摘要仍然保留"
    assert enriched[0]["content_status"] == "excerpt_fallback"
    assert "document_text" not in enriched[0]


@pytest.mark.asyncio
async def test_enrichment_has_one_total_time_budget(monkeypatch):
    import web_document_reader

    class SlowReader:
        async def read(self, _url: str) -> dict:
            await asyncio.sleep(1)
            return {"status": "full_text", "text": "不会返回"}

    monkeypatch.setattr(web_document_reader, "MAX_DEEP_READ_SECONDS", 0.01)
    enriched = await enrich_web_candidates(
        [{
            "source_id": "s1",
            "url": "https://example.edu/a",
            "domain": "example.edu",
            "title": "资料",
            "text": "摘要",
        }],
        reader=SlowReader(),
    )
    assert enriched[0]["content_status"] == "excerpt_fallback"
    assert enriched[0]["content_reason"] == "depth_timeout"


def test_diversity_and_summary_cover_queries_domains_and_depth():
    sources = [
        {
            "source_id": "s1",
            "domain": "a.edu",
            "matched_query": "定义",
            "trust_tier": "tier_a",
            "relevance": 0.9,
        },
        {
            "source_id": "s2",
            "domain": "a.edu",
            "matched_query": "案例",
            "trust_tier": "tier_a",
            "relevance": 0.8,
        },
        {
            "source_id": "s3",
            "domain": "b.gov.cn",
            "matched_query": "案例",
            "trust_tier": "tier_b",
            "relevance": 0.7,
        },
    ]
    selected = diversify_retrieval_sources(sources, limit=2)
    assert {item["domain"] for item in selected} == {"a.edu", "b.gov.cn"}
    candidates = [
        {
            **selected[0],
            "credibility": "high",
            "content_status": "full_text",
            "source_type": "academic",
        },
        {
            **selected[1],
            "credibility": "medium",
            "content_status": "excerpt_fallback",
            "source_type": "official",
        },
    ]
    summary = build_research_summary(
        queries=["定义", "案例", "争议"],
        candidates=candidates,
    )
    assert summary["domain_count"] == 2
    assert summary["full_text_count"] == 1
    assert summary["source_types"] == {"academic": 1, "official": 1}
    assert summary["gaps"] == ["争议"]
