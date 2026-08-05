from __future__ import annotations

import os
from urllib.parse import parse_qs

import httpx
import pytest

from web_retrieval import (
    POLICY_VERSION,
    ExaSearchProvider,
    RetrievalGateway,
    RetrievalProviderError,
    RetrievalRequest,
    SearXNGSearchProvider,
    classify_source,
    configured_retrieval_gateway,
    create_search_provider,
    redact_outbound_query,
    resolve_retrieval_policy,
    retrieval_feature_state,
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


def test_live_unity_document_is_admitted_but_unrelated_academic_result_is_rejected():
    query = (
        "Unity 游戏编程 C# 脚本类创建与挂载机制 能够使用 Visual Studio 创建自定义 "
        "MonoBehaviour 子类并将其正确拖拽挂载到 GameObject 上 intermediate "
        "course prerequisite learning objective open education"
    )

    unity_document = classify_source(
        {
            "url": "https://docs.unity.cn/cn/current/Manual/CreatingAndUsingScripts.html",
            "title": "团结引擎 - 手册：创建和使用脚本",
            "content": (
                "在 Unity 中创建 C# 脚本后，可使用 Visual Studio 编辑继承自 "
                "MonoBehaviour 的类，并将脚本组件挂载到 GameObject。"
            ),
        },
        query=query,
    )
    unrelated_paper = classify_source(
        {
            "url": "https://api.crossref.org/works/10.1000/example",
            "title": "Effects of Exercise Self-Efficacy on Public Health",
            "content": "A clinical study of exercise adherence and health outcomes.",
        },
        query=query,
    )

    assert unity_document["relevance"] >= 0.55
    assert unity_document["trust_tier"] == "tier_b"
    assert unrelated_paper["relevance"] < 0.55
    assert unrelated_paper["trust_tier"] == "tier_c"


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
@pytest.mark.parametrize(
    ("query", "expected_language"),
    [
        ("线性代数 特征值", "zh-CN"),
        ("linear algebra eigenvalues", "en"),
    ],
)
async def test_searxng_provider_uses_internal_json_contract_and_language(
    query,
    expected_language,
):
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["form"] = parse_qs(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.edu/reference",
                        "title": "Reference",
                        "content": "Linear algebra eigenvalue course reference.",
                        "publishedDate": "2026-08-01T00:00:00Z",
                        "engines": ["bing", "duckduckgo"],
                        "score": 42.0,
                    },
                    {
                        "url": "https://example.edu/second",
                        "title": "Second",
                        "content": "A second result that must be truncated.",
                    },
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = SearXNGSearchProvider(
            base_url="http://127.0.0.1:8080",
            client=client,
        )
        results = await provider.search(query, limit=1)

    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:8080/search"
    assert captured["form"] == {
        "q": [query],
        "format": ["json"],
        "categories": ["general,science"],
        "safesearch": ["2"],
        "language": [expected_language],
        "pageno": ["1"],
    }
    assert len(results) == 1
    assert results[0]["content"].startswith("Linear algebra")
    assert results[0]["publishedDate"] == "2026-08-01T00:00:00Z"
    assert results[0]["provider_metadata"] == {
        "engines": ["bing", "duckduckgo"],
        "raw_score": 42.0,
    }
    assert "score" not in results[0]


@pytest.mark.asyncio
async def test_searxng_programming_query_retries_broadly_only_after_empty_result():
    captured: list[dict[str, list[str]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(parse_qs(request.content.decode("utf-8")))
        if len(captured) == 1:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://docs.unity.cn/cn/current/Manual/index.html",
                        "title": "Unity Manual",
                        "content": "Unity GameObject and MonoBehaviour documentation.",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SearXNGSearchProvider(
            base_url="http://127.0.0.1:8080",
            client=client,
        )
        results = await provider.search(
            "Unity 游戏 C# MonoBehaviour GameObject 教程",
            limit=2,
        )

    assert len(captured) == 2
    assert captured[0]["categories"] == ["general"]
    assert captured[0]["language"] == ["zh-CN"]
    assert captured[1]["categories"] == ["general,science"]
    assert captured[1]["language"] == ["all"]
    assert results[0]["url"].startswith("https://docs.unity.cn/")


@pytest.mark.asyncio
async def test_searxng_provider_rejects_public_instances_and_invalid_responses():
    assert SearXNGSearchProvider(base_url="https://search.example.com").configured is False

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = SearXNGSearchProvider(
            base_url="http://localhost:8080",
            client=client,
        )
        with pytest.raises(RetrievalProviderError, match="provider_error"):
            await provider.search("linear algebra", limit=2)


def test_searxng_is_default_provider_and_health_state_is_dynamic(monkeypatch):
    monkeypatch.delenv("WEB_RETRIEVAL_PROVIDER", raising=False)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("WEB_RETRIEVAL_V2_MODE", "on")
    monkeypatch.setenv("EXA_API_KEY", "must-not-select-exa")

    provider = create_search_provider()
    state = retrieval_feature_state("teacher-1")

    assert isinstance(provider, SearXNGSearchProvider)
    assert provider.configured is True
    assert state == {
        "mode": "on",
        "enabled": True,
        "enabled_for_user": True,
        "provider": "searxng",
        "provider_configured": True,
    }


@pytest.mark.asyncio
async def test_rollout_denial_uses_disabled_provider_and_makes_no_request(monkeypatch):
    monkeypatch.setenv("WEB_RETRIEVAL_PROVIDER", "searxng")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("WEB_RETRIEVAL_V2_MODE", "allowlist")
    monkeypatch.setenv("WEB_RETRIEVAL_V2_USER_IDS", "allowed-teacher")

    gateway, feature = configured_retrieval_gateway("blocked-teacher")
    package = await gateway.retrieve(
        RetrievalRequest(
            purpose="course",
            enabled=True,
            queries=["linear algebra course"],
        )
    )

    assert feature["enabled_for_user"] is False
    assert gateway.provider.name == "searxng"
    assert gateway.provider.configured is False
    assert package["status"] == "failed_fallback_local"
    assert package["receipt"]["error_codes"] == ["not_configured"]


@pytest.mark.asyncio
async def test_searxng_failure_never_falls_back_to_exa(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "available-but-forbidden-as-fallback")

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = create_search_provider(
            provider_name="searxng",
            endpoint="http://127.0.0.1:8080",
            client=client,
        )
        package = await RetrievalGateway(provider=provider).retrieve(
            RetrievalRequest(
                purpose="ai_teacher",
                enabled=True,
                queries=["linear algebra course"],
            )
        )

    assert provider.name == "searxng"
    assert package["provider"] == "searxng"
    assert package["status"] == "failed_fallback_local"
    assert package["receipt"]["error_codes"] == ["provider_error"]


@pytest.mark.asyncio
async def test_searxng_timeout_and_empty_results_keep_normalized_errors():
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout_handler)
    ) as client:
        timeout_package = await RetrievalGateway(
            provider=SearXNGSearchProvider(
                base_url="http://127.0.0.1:8080",
                client=client,
            ),
            cache_ttl_seconds=0,
        ).retrieve(
            RetrievalRequest(
                purpose="ai_teacher",
                enabled=True,
                queries=["linear algebra course"],
            )
        )

    async def empty_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(empty_handler)
    ) as client:
        empty_package = await RetrievalGateway(
            provider=SearXNGSearchProvider(
                base_url="http://127.0.0.1:8080",
                client=client,
            ),
            cache_ttl_seconds=0,
        ).retrieve(
            RetrievalRequest(
                purpose="ai_teacher",
                enabled=True,
                queries=["linear algebra course"],
            )
        )

    assert timeout_package["receipt"]["error_codes"] == ["timeout"]
    assert empty_package["receipt"]["error_codes"] == ["no_sources"]


@pytest.mark.asyncio
async def test_searxng_raw_score_cannot_bypass_local_relevance_threshold():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{
                    "url": "https://example.edu/unrelated",
                    "title": "Unrelated reference",
                    "content": "A recipe for baking sourdough bread.",
                    "score": 999.0,
                    "engines": ["bing"],
                }]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        package = await RetrievalGateway(
            provider=SearXNGSearchProvider(
                base_url="http://127.0.0.1:8080",
                client=client,
            ),
            cache_ttl_seconds=0,
        ).retrieve(
            RetrievalRequest(
                purpose="course",
                enabled=True,
                queries=["linear algebra eigenvalue course"],
            )
        )

    assert package["receipt"]["error_codes"] == ["no_sources"]
    assert package["rejected_sources"][0]["relevance"] < 0.55
    assert package["rejected_sources"][0]["provider_metadata"]["raw_score"] == 999.0


def test_retrieval_policy_version_records_provider_upgrade():
    assert POLICY_VERSION == "web_retrieval_v2.1"


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


@pytest.mark.asyncio
async def test_gateway_reuses_sanitized_query_cache_across_requests():
    class CountingProvider:
        name = "counting"
        configured = True

        def __init__(self):
            self.calls = 0

        async def search(self, query: str, *, limit: int):
            self.calls += 1
            return [{
                "url": "https://example.edu/linear-algebra",
                "title": "Linear algebra course",
                "text": "Linear algebra eigenvalue course reference.",
                "score": 0.95,
            }]

    provider = CountingProvider()
    request = RetrievalRequest(
        purpose="ai_teacher",
        enabled=True,
        queries=["linear algebra eigenvalue course"],
    )
    first = await RetrievalGateway(
        provider=provider,
        cache_namespace="cache-contract",
    ).retrieve(request)
    second = await RetrievalGateway(
        provider=provider,
        cache_namespace="cache-contract",
    ).retrieve(request)

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert second["receipt"]["cache_hit_count"] == 1
    assert provider.calls == 1


@pytest.mark.skipif(
    os.getenv("RUN_EXA_STAGING_SMOKE") != "1"
    or not os.getenv("EXA_API_KEY", "").strip(),
    reason="requires an explicit staging opt-in and Exa test key",
)
@pytest.mark.asyncio
async def test_exa_staging_smoke_returns_public_sources():
    package = await RetrievalGateway(
        provider=ExaSearchProvider(),
        cache_namespace="exa-staging-smoke",
        cache_ttl_seconds=0,
    ).retrieve(
        RetrievalRequest(
            purpose="ai_teacher",
            enabled=True,
            queries=["OpenStax linear algebra matrices course material"],
            request_fingerprint="exa_staging_smoke_v1",
        )
    )

    assert package["status"] == "completed"
    assert package["sources"]
    assert package["receipt"]["admitted_source_count"] > 0
    assert all(
        source["provider"] == "exa"
        and source["url"].startswith("https://")
        for source in package["sources"]
    )


@pytest.mark.skipif(
    os.getenv("RUN_SEARXNG_STAGING_SMOKE") != "1"
    or not os.getenv("SEARXNG_BASE_URL", "").strip(),
    reason="requires an explicit staging opt-in and self-hosted SearXNG",
)
@pytest.mark.asyncio
async def test_searxng_staging_smoke_returns_public_sources():
    package = await RetrievalGateway(
        provider=SearXNGSearchProvider(),
        cache_namespace="searxng-staging-smoke",
        cache_ttl_seconds=0,
    ).retrieve(
        RetrievalRequest(
            purpose="ai_teacher",
            enabled=True,
            queries=["OpenStax linear algebra matrices course material"],
            request_fingerprint="searxng_staging_smoke_v1",
        )
    )

    assert package["status"] == "completed"
    assert package["sources"]
    assert package["receipt"]["admitted_source_count"] > 0
    assert all(
        source["provider"] == "searxng"
        and source["url"].startswith("https://")
        for source in package["sources"]
    )
