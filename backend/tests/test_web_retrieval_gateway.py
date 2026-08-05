from __future__ import annotations

import httpx
import pytest

from web_retrieval import (
    ExaSearchProvider,
    RetrievalGateway,
    RetrievalRequest,
    classify_source,
    redact_outbound_query,
    resolve_retrieval_policy,
)


def test_outbound_query_redacts_pii_and_blocks_heavily_private_queries():
    safe = redact_outbound_query(
        "联系 student@example.com 或 13800138000，查询线性代数公开课程"
    )
    assert "student@example.com" not in safe["query"]
    assert "13800138000" not in safe["query"]
    assert safe["blocked"] is False

    blocked = redact_outbound_query(
        "student@example.com 13800138000 110101199001011234"
    )
    assert blocked["blocked"] is True
    assert blocked["error_code"] == "privacy_blocked"


@pytest.mark.parametrize(
    ("url", "query", "text", "expected"),
    [
        (
            "https://math.example.edu/course",
            "linear algebra eigenvalue course",
            "Linear algebra course material about eigenvalue computation.",
            "tier_a",
        ),
        (
            "https://example.com/linear-algebra",
            "linear algebra eigenvalue course",
            "Linear algebra eigenvalue course practice and computation.",
            "tier_b",
        ),
        (
            "http://127.0.0.1/private",
            "linear algebra eigenvalue course",
            "Linear algebra eigenvalue course practice and computation.",
            "tier_c",
        ),
    ],
)
def test_source_classification_is_tiered(url, query, text, expected):
    source = classify_source(
        {
            "url": url,
            "title": "Linear algebra",
            "text": text,
        },
        query=query,
    )
    assert source["trust_tier"] == expected


@pytest.mark.asyncio
async def test_exa_provider_uses_expected_http_contract():
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.edu/reference",
                        "title": "Reference",
                        "highlights": ["Public course evidence"],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = ExaSearchProvider(api_key="test-key", client=client)
        results = await provider.search("public course", limit=2)

    assert captured["headers"]["x-api-key"] == "test-key"
    assert '"numResults":2' in captured["payload"].replace(" ", "")
    assert results[0]["url"] == "https://example.edu/reference"


@pytest.mark.asyncio
async def test_gateway_classifies_timeout_and_never_silently_succeeds():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = ExaSearchProvider(api_key="test-key", client=client)
        package = await RetrievalGateway(provider=provider).retrieve(
            RetrievalRequest(
                purpose="ai_teacher",
                enabled=True,
                queries=["linear algebra course"],
                max_queries=3,
                max_sources=6,
                timeout_seconds=8,
            )
        )

    assert package["status"] == "failed_fallback_local"
    assert package["receipt"]["error_codes"] == ["timeout"]
    assert package["receipt"]["source_count"] == 0


def test_explicit_retrieval_policy_prefers_v2_and_preserves_legacy_scope():
    assert resolve_retrieval_policy({}) == {
        "enabled": False,
        "scopes": [],
        "source": "default_off",
    }
    assert resolve_retrieval_policy(
        {"web_question_enrichment": {"enabled": True}}
    ) == {
        "enabled": True,
        "scopes": ["assessment"],
        "source": "legacy_web_question_enrichment",
    }
    assert resolve_retrieval_policy(
        {
            "retrieval": {"enabled": False},
            "web_question_enrichment": {"enabled": True},
        }
    ) == {
        "enabled": False,
        "scopes": [],
        "source": "retrieval_v2",
    }
