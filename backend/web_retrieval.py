"""Shared, policy-enforcing web retrieval for course AI workflows.

Business modules depend on :class:`RetrievalGateway`, never on a concrete
search provider. The gateway deliberately returns a receipt for every outcome
so callers cannot silently replace failed retrieval with model knowledge.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import json
import os
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from urllib.parse import urlparse, urlunparse

import httpx

EXA_SEARCH_ENDPOINT = "https://api.exa.ai/search"
POLICY_VERSION = "web_retrieval_v2.1"
ERROR_CODES = {
    "not_configured",
    "timeout",
    "provider_error",
    "no_sources",
    "privacy_blocked",
}
_QUERY_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

PURPOSE_LIMITS: dict[str, dict[str, int | float]] = {
    "course": {
        "max_queries": 12,
        "max_sources": 24,
        "concurrency": 2,
        "timeout_seconds": 20,
    },
    "assessment": {
        "max_queries": 12,
        "max_sources": 24,
        "concurrency": 3,
        "timeout_seconds": 20,
    },
    "ai_teacher": {
        "max_queries": 3,
        "max_sources": 6,
        "concurrency": 3,
        "timeout_seconds": 8,
    },
    "ppt_image": {
        "max_queries": 2,
        "max_sources": 24,
        "concurrency": 1,
        "timeout_seconds": 20,
    },
}

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email",
        re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE),
    ),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("national_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?[^.!?\n]*[.!?]?", re.I),
    re.compile(r"(?:system|developer)\s+message\s*:[^\n]*", re.I),
    re.compile(r"(?:reveal|show|send)\s+(?:the\s+)?(?:student|user|learner)\s+(?:data|answers?)[^.!?\n]*", re.I),
    re.compile(r"忽略(?:此前|之前|以上|全部)?指令[^。！？\n]*[。！？]?", re.I),
    re.compile(r"(?:泄露|展示|发送)(?:学生|用户)?(?:数据|答案)[^。！？\n]*[。！？]?", re.I),
)
_CURRENT_TERMS = re.compile(
    r"\b(?:latest|current|today|newest|recent)\b|最新|当前|目前|今天|近期",
    re.I,
)
_OPEN_LICENSE = re.compile(
    r"\b(?:cc[- ]?by(?:[- ]?sa)?|creative commons|public domain|oer|open educational)\b",
    re.I,
)
_ACADEMIC_QUERY_TERMS = re.compile(
    r"\b(?:research|papers?|academic|literature|journal|arxiv|pubmed|clinical|"
    r"mathematics|physics|chemistry|biology|medicine|linear\s+algebra|eigenvalues?)\b|"
    r"研究|论文|学术|文献|期刊|临床|数学|物理|化学|生物|医学|线性代数|特征值",
    re.I,
)
_RELEVANCE_NOISE_TOKENS = {
    "course",
    "curriculum",
    "education",
    "learning",
    "objective",
    "open",
    "prerequisite",
    "tutorial",
    "university",
    "beginner",
    "intermediate",
    "advanced",
    "课程",
    "学习",
    "目标",
    "先修",
    "教程",
    "官方",
    "文档",
}
_DEFAULT_TIER_A_DOMAINS = (
    ".gov",
    ".gov.cn",
    ".edu",
    ".edu.cn",
    "arxiv.org",
    "doi.org",
    "openstax.org",
    "pubmed.ncbi.nlm.nih.gov",
)


class SearchProvider(Protocol):
    """Replaceable provider interface consumed by the retrieval gateway."""

    name: str

    @property
    def configured(self) -> bool: ...

    async def search(
        self,
        query: str,
        *,
        limit: int,
        category: Literal["general", "images"] = "general",
    ) -> list[dict[str, Any]]: ...


class ExaSearchProvider:
    """Thin Exa HTTP adapter; policy remains in :class:`RetrievalGateway`."""

    name = "exa"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("EXA_API_KEY", "")
        self.endpoint = endpoint or os.getenv("EXA_SEARCH_ENDPOINT", EXA_SEARCH_ENDPOINT)
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    async def search(
        self,
        query: str,
        *,
        limit: int,
        category: Literal["general", "images"] = "general",
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RetrievalProviderError("not_configured")
        if category != "general":
            raise RetrievalProviderError("not_configured")
        payload = {
            "query": _clip(query, 1000),
            "type": "auto",
            "numResults": max(1, min(24, int(limit))),
            "moderation": True,
            "contents": {"highlights": {"maxCharacters": 2400}},
        }
        headers = {"x-api-key": self.api_key, "content-type": "application/json"}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise RetrievalProviderError("provider_error")
        return [item for item in results if isinstance(item, dict)]


class SearXNGSearchProvider:
    """Loopback-only SearXNG adapter returning provider-neutral snippets."""

    name = "searxng"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        configured_url = (
            base_url
            if base_url is not None
            else os.getenv("SEARXNG_BASE_URL", "")
        )
        self.base_url = _loopback_base_url(str(configured_url or ""))
        configured_timeout = timeout_seconds
        if configured_timeout is None:
            try:
                configured_timeout = float(
                    os.getenv("SEARXNG_REQUEST_TIMEOUT_SECONDS", "6")
                )
            except ValueError:
                configured_timeout = 6.0
        self.timeout_seconds = max(0.5, min(20.0, float(configured_timeout)))
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    async def search(
        self,
        query: str,
        *,
        limit: int,
        category: Literal["general", "images"] = "general",
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RetrievalProviderError("not_configured")
        search_categories = (
            "images" if category == "images" else _search_categories(query)
        )
        form = {
            "q": _clip(query, 1000),
            "format": "json",
            "categories": search_categories,
            "safesearch": "2",
            "language": "zh-CN" if _contains_cjk(query) else "en",
            "pageno": "1",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            trust_env=False,
        )
        try:
            try:
                response = await client.post(
                    f"{self.base_url}/search",
                    data=form,
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results") if isinstance(data, dict) else None
                if not isinstance(results, list):
                    raise RetrievalProviderError("provider_error")
                fallback_categories = (
                    "images" if category == "images" else "general,science"
                )
                if not results and (
                    form["language"] != "all"
                    or form["categories"] != fallback_categories
                ):
                    fallback_form = {
                        **form,
                        "categories": fallback_categories,
                        "language": "all",
                    }
                    response = await client.post(
                        f"{self.base_url}/search",
                        data=fallback_form,
                    )
                    response.raise_for_status()
                    data = response.json()
                    results = data.get("results") if isinstance(data, dict) else None
                    if not isinstance(results, list):
                        raise RetrievalProviderError("provider_error")
            except httpx.TimeoutException:
                raise
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise RetrievalProviderError("provider_error") from exc
        finally:
            if owns_client:
                await client.aclose()

        normalized: list[dict[str, Any]] = []
        for raw in results:
            if not isinstance(raw, dict):
                continue
            engines = raw.get("engines")
            if isinstance(engines, str):
                engines = [engines]
            normalized_engines = [
                str(value).strip()
                for value in (engines or [])
                if str(value).strip()
            ] if isinstance(engines, list) else []
            metadata: dict[str, Any] = {}
            if normalized_engines:
                metadata["engines"] = normalized_engines
            raw_score = raw.get("score")
            if isinstance(raw_score, (int, float)):
                metadata["raw_score"] = raw_score
            if category == "images":
                image_url = str(raw.get("img_src") or "").strip()
                thumbnail_url = str(raw.get("thumbnail_src") or "").strip()
                resolution = str(raw.get("resolution") or "").strip()
                mime_type = str(raw.get("img_format") or "").strip()
                if image_url:
                    metadata["image_url"] = image_url
                if thumbnail_url:
                    metadata["thumbnail_url"] = thumbnail_url
                if resolution:
                    metadata["resolution"] = resolution[:100]
                if mime_type:
                    metadata["mime_type"] = mime_type[:100]
            item = {
                "url": raw.get("url"),
                "title": raw.get("title"),
                "content": (
                    raw.get("content")
                    or raw.get("text")
                    or (raw.get("title") if category == "images" else None)
                ),
                "publishedDate": (
                    raw.get("publishedDate")
                    or raw.get("published_date")
                    or raw.get("pubdate")
                ),
            }
            if metadata:
                item["provider_metadata"] = metadata
            normalized.append(item)
            if len(normalized) >= max(1, min(24, int(limit))):
                break
        return normalized


class DisabledSearchProvider:
    """Non-networking provider used when rollout authorization denies access."""

    def __init__(self, name: str) -> None:
        self.name = str(name or "searxng")

    @property
    def configured(self) -> bool:
        return False

    async def search(
        self,
        query: str,
        *,
        limit: int,
        category: Literal["general", "images"] = "general",
    ) -> list[dict[str, Any]]:
        del query, limit, category
        raise RetrievalProviderError("not_configured")


class RetrievalProviderError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code if error_code in ERROR_CODES else "provider_error"


@dataclass(slots=True)
class RetrievalRequest:
    purpose: str
    enabled: bool
    queries: list[str]
    category: Literal["general", "images"] = "general"
    max_queries: int | None = None
    max_sources: int | None = None
    timeout_seconds: float | None = None
    concurrency: int | None = None
    request_fingerprint: str = ""
    revision: int = 1
    accepted_source_ids: list[str] = field(default_factory=list)


class RetrievalGateway:
    def __init__(
        self,
        *,
        provider: SearchProvider | None = None,
        tier_a_domains: list[str] | tuple[str, ...] | None = None,
        cache_namespace: str | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        self.provider = provider or create_search_provider()
        configured_domains = [
            value.strip().lower()
            for value in os.getenv("WEB_RETRIEVAL_TIER_A_DOMAINS", "").split(",")
            if value.strip()
        ]
        self.tier_a_domains = tuple(
            tier_a_domains or configured_domains or _DEFAULT_TIER_A_DOMAINS
        )
        self.cache_namespace = cache_namespace or (
            f"{POLICY_VERSION}:{self.provider.name}"
        )
        configured_ttl = cache_ttl_seconds
        if configured_ttl is None:
            try:
                configured_ttl = float(
                    os.getenv("WEB_RETRIEVAL_CACHE_TTL_SECONDS", "900")
                )
            except ValueError:
                configured_ttl = 900.0
        self.cache_ttl_seconds = max(0.0, min(86400.0, configured_ttl))

    async def retrieve(self, request: RetrievalRequest) -> dict[str, Any]:
        started = time.monotonic()
        now = _now()
        limits = PURPOSE_LIMITS.get(request.purpose, PURPOSE_LIMITS["course"])
        max_queries = min(
            max(0, request.max_queries or int(limits["max_queries"])),
            int(limits["max_queries"]),
        )
        max_sources = min(
            max(0, request.max_sources or int(limits["max_sources"])),
            int(limits["max_sources"]),
        )
        timeout_seconds = min(
            max(0.1, request.timeout_seconds or float(limits["timeout_seconds"])),
            float(limits["timeout_seconds"]),
        )
        concurrency = min(
            max(1, request.concurrency or int(limits["concurrency"])),
            int(limits["concurrency"]),
        )
        safe_queries: list[str] = []
        error_codes: list[str] = []
        for raw_query in request.queries[:max_queries]:
            redacted = redact_outbound_query(raw_query)
            if redacted["blocked"]:
                error_codes.append("privacy_blocked")
                continue
            query = str(redacted["query"]).strip()
            if query and query not in safe_queries:
                safe_queries.append(query)

        if not request.enabled:
            return self._package(
                request=request,
                status="disabled",
                queries=[],
                sources=[],
                rejected_sources=[],
                errors=[],
                started=started,
                retrieved_at=now,
            )
        if not safe_queries:
            error_codes.append("privacy_blocked" if request.queries else "no_sources")
            return self._failed_package(request, safe_queries, error_codes, started, now)
        if not self.provider.configured:
            return self._failed_package(
                request, safe_queries, [*error_codes, "not_configured"], started, now
            )

        semaphore = asyncio.Semaphore(concurrency)
        per_query = max(1, min(max_sources, (max_sources + len(safe_queries) - 1) // len(safe_queries)))
        candidate_limit = min(24, max(12, max_sources * 4, per_query * 8))

        async def run(
            query: str,
        ) -> tuple[str, list[dict[str, Any]], str | None, bool]:
            async with semaphore:
                cache_key = _digest({
                    "namespace": self.cache_namespace,
                    "query": query,
                    "limit": candidate_limit,
                    "category": request.category,
                })
                cached = _QUERY_CACHE.get(cache_key)
                if cached and cached[0] > time.monotonic():
                    return query, deepcopy(cached[1]), None, True
                if cached:
                    _QUERY_CACHE.pop(cache_key, None)
                try:
                    if request.category == "general":
                        results = await self.provider.search(query, limit=candidate_limit)
                    else:
                        results = await self.provider.search(
                            query,
                            limit=candidate_limit,
                            category=request.category,
                        )
                    if self.cache_ttl_seconds > 0:
                        _QUERY_CACHE[cache_key] = (
                            time.monotonic() + self.cache_ttl_seconds,
                            deepcopy(results),
                        )
                    return query, results, None, False
                except RetrievalProviderError as exc:
                    return query, [], exc.error_code, False
                except httpx.TimeoutException:
                    return query, [], "timeout", False
                except (httpx.HTTPError, ValueError, TypeError):
                    return query, [], "provider_error", False
                except Exception:
                    return query, [], "provider_error", False

        try:
            batches = await asyncio.wait_for(
                asyncio.gather(*(run(query) for query in safe_queries)),
                timeout=timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return self._failed_package(
                request, safe_queries, [*error_codes, "timeout"], started, now
            )

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        cache_hit_count = 0
        for query, results, error_code, cache_hit in batches:
            cache_hit_count += int(cache_hit)
            if error_code:
                error_codes.append(error_code)
            for raw in results:
                source = classify_source(
                    raw,
                    query=query,
                    provider=self.provider.name,
                    tier_a_domains=self.tier_a_domains,
                    retrieved_at=now,
                    category=request.category,
                )
                source["matched_query"] = query
                key = str(source.get("canonical_url") or source.get("url") or source.get("content_hash"))
                if key in seen:
                    continue
                seen.add(key)
                if source["trust_tier"] == "tier_c":
                    rejected.append(source)
                elif len(accepted) < max_sources:
                    accepted.append(source)

        if not accepted:
            if not error_codes:
                error_codes.append("no_sources")
            return self._package(
                request=request,
                status="failed_fallback_local",
                queries=safe_queries,
                sources=[],
                rejected_sources=rejected,
                errors=_unique_error_codes(error_codes),
                started=started,
                retrieved_at=now,
                cache_hit_count=cache_hit_count,
            )
        return self._package(
            request=request,
            status="completed",
            queries=safe_queries,
            sources=accepted,
            rejected_sources=rejected,
            errors=_unique_error_codes(error_codes),
            started=started,
            retrieved_at=now,
            cache_hit_count=cache_hit_count,
        )

    def _failed_package(
        self,
        request: RetrievalRequest,
        queries: list[str],
        errors: list[str],
        started: float,
        retrieved_at: str,
        cache_hit_count: int = 0,
    ) -> dict[str, Any]:
        return self._package(
            request=request,
            status="failed_fallback_local",
            queries=queries,
            sources=[],
            rejected_sources=[],
            errors=_unique_error_codes(errors),
            started=started,
            retrieved_at=retrieved_at,
            cache_hit_count=cache_hit_count,
        )

    def _package(
        self,
        *,
        request: RetrievalRequest,
        status: str,
        queries: list[str],
        sources: list[dict[str, Any]],
        rejected_sources: list[dict[str, Any]],
        errors: list[str],
        started: float,
        retrieved_at: str,
        cache_hit_count: int = 0,
    ) -> dict[str, Any]:
        tier_counts = {"tier_a": 0, "tier_b": 0, "tier_c": 0}
        for source in [*sources, *rejected_sources]:
            tier = str(source.get("trust_tier") or "tier_c")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        fingerprint = request.request_fingerprint or _digest(
            {
                "purpose": request.purpose,
                "category": request.category,
                "queries": queries,
            }
        )
        package_revision = max(1, int(request.revision))
        receipt = {
            "schema_version": "retrieval_receipt_v1",
            "status": status,
            "query_count": len(queries),
            "source_count": len(sources),
            "admitted_count": len(sources),
            "tier_distribution": tier_counts,
            "error_codes": errors,
            "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
            "package_revision": package_revision,
            "cache_hit_count": max(0, int(cache_hit_count)),
        }
        package = {
            "schema_version": "retrieval_package_v1",
            "request_fingerprint": fingerprint,
            "policy_version": POLICY_VERSION,
            "provider": self.provider.name,
            "purpose": request.purpose,
            "category": request.category,
            "status": status,
            "queries": queries,
            "sources": sources,
            "rejected_sources": rejected_sources,
            "coverage": {
                "requested_queries": min(len(request.queries), receipt["query_count"]),
                "completed_queries": receipt["query_count"],
                "has_admitted_sources": bool(sources),
            },
            "errors": [{"code": code} for code in errors],
            "retrieved_at": retrieved_at,
            "revision": package_revision,
            "receipt": receipt,
        }
        package["package_hash"] = _digest(package)
        return package


def resolve_retrieval_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve explicit V2 authorization while preserving legacy assessment scope."""

    payload = payload or {}
    if "retrieval" in payload:
        retrieval = payload.get("retrieval")
        enabled = bool(retrieval.get("enabled")) if isinstance(retrieval, dict) else False
        return {
            "enabled": enabled,
            "scopes": ["course", "assessment"] if enabled else [],
            "source": "retrieval_v2",
        }
    legacy = payload.get("web_question_enrichment")
    if isinstance(legacy, dict) and bool(legacy.get("enabled")):
        return {
            "enabled": True,
            "scopes": ["assessment"],
            "source": "legacy_web_question_enrichment",
        }
    return {"enabled": False, "scopes": [], "source": "default_off"}


def redact_outbound_query(query: str) -> dict[str, Any]:
    """Redact common identifiers and block queries mostly made of private data."""

    original = _clip(str(query or ""), 1000)
    redacted = original
    pii_types: list[str] = []
    redacted_characters = 0
    for kind, pattern in _PII_PATTERNS:
        matches = list(pattern.finditer(redacted))
        if not matches:
            continue
        pii_types.append(kind)
        redacted_characters += sum(len(match.group(0)) for match in matches)
        redacted = pattern.sub(f"[REDACTED_{kind.upper()}]", redacted)
    meaningful_length = max(1, len(re.sub(r"\s+", "", original)))
    redaction_ratio = min(1.0, redacted_characters / meaningful_length)
    blocked = redaction_ratio >= 0.8
    return {
        "query": re.sub(r"\s+", " ", redacted).strip(),
        "blocked": blocked,
        "error_code": "privacy_blocked" if blocked else None,
        "pii_types": pii_types,
        "redaction_ratio": round(redaction_ratio, 4),
    }


def classify_source(
    raw: dict[str, Any],
    *,
    query: str,
    provider: str = "unknown",
    tier_a_domains: tuple[str, ...] | list[str] | None = None,
    retrieved_at: str | None = None,
    category: Literal["general", "images"] = "general",
) -> dict[str, Any]:
    """Normalize a provider result into the public RetrievalSourceV1 contract."""

    raw_url = str(raw.get("url") or "").strip()[:2000]
    canonical_url, domain, safe_url = _canonical_public_https_url(raw_url)
    title = _sanitize_untrusted(str(raw.get("title") or ""), limit=500)
    highlights = raw.get("highlights") or []
    highlight_text = " ".join(value for value in highlights if isinstance(value, str))
    excerpt = _sanitize_untrusted(
        str(raw.get("text") or raw.get("content") or highlight_text or raw.get("summary") or ""),
        limit=4000,
    )
    published_date = str(raw.get("publishedDate") or raw.get("published_date") or "").strip()[:64]
    license_name = _sanitize_untrusted(
        str(raw.get("license") or raw.get("rights") or ""), limit=200
    )
    provider_score = raw.get("score")
    computed_relevance = _relevance(query, f"{title} {excerpt}")
    relevance = (
        max(computed_relevance, min(1.0, max(0.0, float(provider_score))))
        if isinstance(provider_score, (int, float))
        else computed_relevance
    )
    has_injection = _contains_injection(str(raw.get("text") or raw.get("content") or highlight_text or ""))
    allowed_domains = tuple(tier_a_domains or _DEFAULT_TIER_A_DOMAINS)
    is_tier_a_domain = any(
        domain == suffix.lstrip(".") or domain.endswith(suffix)
        for suffix in allowed_domains
    )
    rejection_reasons: list[str] = []
    if not safe_url:
        rejection_reasons.append("unsafe_url")
    if not excerpt:
        rejection_reasons.append("missing_excerpt")
    minimum_relevance = 0.25 if category == "images" else 0.55
    if relevance < minimum_relevance:
        rejection_reasons.append("low_relevance")
    if has_injection:
        rejection_reasons.append("prompt_injection")

    if rejection_reasons:
        trust_tier = "tier_c"
    elif is_tier_a_domain:
        trust_tier = "tier_a"
    else:
        trust_tier = "tier_b"
    if trust_tier == "tier_a" and _CURRENT_TERMS.search(query) and not published_date:
        trust_tier = "tier_b"
        rejection_reasons.append("missing_date_for_current_query")

    content_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    raw_provider_metadata = raw.get("provider_metadata")
    provider_metadata: dict[str, Any] = {}
    if isinstance(raw_provider_metadata, dict):
        engines = raw_provider_metadata.get("engines")
        if isinstance(engines, list):
            provider_metadata["engines"] = [
                str(value).strip()[:100]
                for value in engines
                if str(value).strip()
            ][:12]
        raw_score = raw_provider_metadata.get("raw_score")
        if isinstance(raw_score, (int, float)):
            provider_metadata["raw_score"] = float(raw_score)
        for field_name in ("image_url", "thumbnail_url"):
            raw_media_url = str(raw_provider_metadata.get(field_name) or "").strip()[:2000]
            canonical_media_url, _, safe_media_url = _canonical_public_https_url(
                raw_media_url
            )
            if safe_media_url:
                provider_metadata[field_name] = canonical_media_url
        resolution = _sanitize_untrusted(
            str(raw_provider_metadata.get("resolution") or ""),
            limit=100,
        )
        if resolution:
            provider_metadata["resolution"] = resolution
        mime_type = _sanitize_untrusted(
            str(raw_provider_metadata.get("mime_type") or ""),
            limit=100,
        )
        if mime_type:
            provider_metadata["mime_type"] = mime_type
    if category == "images" and not provider_metadata.get("image_url"):
        rejection_reasons.append("missing_image_url")
        trust_tier = "tier_c"
    source_id = "src_" + hashlib.sha256(
        f"{canonical_url}\n{content_hash}".encode()
    ).hexdigest()[:24]
    return {
        "schema_version": "retrieval_source_v1",
        "source_id": source_id,
        "url": canonical_url or raw_url,
        "canonical_url": canonical_url,
        "title": title,
        "domain": domain,
        "excerpt": excerpt,
        "published_date": published_date or None,
        "retrieved_at": retrieved_at or _now(),
        "content_hash": content_hash,
        "provider": provider,
        "provider_metadata": provider_metadata,
        "media_type": "image" if category == "images" else "document",
        "relevance": round(relevance, 4),
        "trust_tier": trust_tier,
        "license": license_name or None,
        "reuse_policy": "verbatim_allowed" if _OPEN_LICENSE.search(license_name) else "summary_only",
        "accepted_for_generation": trust_tier == "tier_a",
        "rejection_reasons": rejection_reasons,
    }


def retrieval_feature_state(user_id: str | None = None) -> dict[str, Any]:
    """Return non-secret runtime rollout state for authorization and health."""

    mode = os.getenv("WEB_RETRIEVAL_V2_MODE", "off").strip().lower()
    if mode not in {"off", "allowlist", "on"}:
        mode = "off"
    allowlist = {
        value.strip()
        for value in os.getenv("WEB_RETRIEVAL_V2_USER_IDS", "").split(",")
        if value.strip()
    }
    enabled_for_user = mode == "on" or (
        mode == "allowlist" and bool(user_id) and str(user_id) in allowlist
    )
    selected_provider = str(
        os.getenv("WEB_RETRIEVAL_PROVIDER", "searxng")
    ).strip().lower() or "searxng"
    try:
        provider_configured = create_search_provider(
            provider_name=selected_provider
        ).configured
    except RetrievalProviderError:
        provider_configured = False
    return {
        "mode": mode,
        "enabled": mode != "off",
        "enabled_for_user": enabled_for_user,
        "provider": selected_provider,
        "provider_configured": provider_configured,
    }


def create_search_provider(
    *,
    provider_name: str | None = None,
    api_key: str | None = None,
    endpoint: str | None = None,
    timeout_seconds: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> SearchProvider:
    """Create the configured provider behind the replaceable domain interface."""

    selected = str(
        provider_name or os.getenv("WEB_RETRIEVAL_PROVIDER", "searxng")
    ).strip().lower()
    if selected == "searxng":
        return SearXNGSearchProvider(
            base_url=endpoint,
            timeout_seconds=timeout_seconds,
            client=client,
        )
    if selected == "exa":
        return ExaSearchProvider(
            api_key=api_key,
            endpoint=endpoint,
            timeout_seconds=(
                12.0 if timeout_seconds is None else timeout_seconds
            ),
            client=client,
        )
    raise RetrievalProviderError("not_configured")


def configured_retrieval_gateway(
    user_id: str | None = None,
) -> tuple[RetrievalGateway, dict[str, Any]]:
    """Return a rollout-aware gateway without leaking provider choice to callers."""

    feature = retrieval_feature_state(user_id)
    provider = (
        create_search_provider(provider_name=str(feature["provider"]))
        if feature.get("enabled_for_user")
        else DisabledSearchProvider(str(feature["provider"]))
    )
    return RetrievalGateway(provider=provider), feature


def admitted_sources(
    package: dict[str, Any] | None,
    *,
    accepted_source_ids: list[str] | set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return tier A plus explicitly accepted tier B sources."""

    accepted = set(accepted_source_ids or [])
    return [
        source
        for source in (package or {}).get("sources", [])
        if source.get("trust_tier") == "tier_a"
        or (
            source.get("trust_tier") == "tier_b"
            and source.get("source_id") in accepted
        )
    ]


def _loopback_base_url(value: str) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            return ""
        if host not in {"localhost", "localhost.localdomain"}:
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    return ""
            except ValueError:
                return ""
        port = parsed.port
        rendered_host = f"[{host}]" if ":" in host else host
        netloc = rendered_host if port is None else f"{rendered_host}:{port}"
        return urlunparse((parsed.scheme.lower(), netloc, "", "", "", ""))
    except (ValueError, UnicodeError):
        return ""


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


def _search_categories(query: str) -> str:
    """Route explicit academic intent to science engines; keep product docs general."""

    return "general,science" if _ACADEMIC_QUERY_TERMS.search(query) else "general"


def _canonical_public_https_url(url: str) -> tuple[str, str, bool]:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return "", host, False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            return "", host, False
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return "", host, False
        port = parsed.port
        netloc = host if port in {None, 443} else f"{host}:{port}"
        canonical = urlunparse(("https", netloc, parsed.path or "/", "", parsed.query, ""))
        return canonical, host, True
    except (ValueError, UnicodeError):
        return "", "", False


def _sanitize_untrusted(value: str, *, limit: int) -> str:
    text = html.unescape(value)
    text = re.sub(r"(?is)<(script|style|iframe|object|template)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub(" ", text)
    text = "".join(character for character in text if character.isprintable() or character in "\n\t")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _contains_injection(value: str) -> bool:
    return any(pattern.search(value) for pattern in _INJECTION_PATTERNS)


def _relevance(query: str, text: str) -> float:
    query_tokens = {
        token
        for token in _tokens(query)
        if token not in _RELEVANCE_NOISE_TOKENS
    }
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokens(text))
    # Search queries contain context that snippets rarely repeat verbatim. A
    # bounded denominator still requires several independent concept matches,
    # while preventing verbose objectives from making a relevant source score
    # worse solely because more context was supplied.
    evidence_target = min(len(query_tokens), 12)
    return min(1.0, len(query_tokens & text_tokens) / evidence_target)


def _tokens(value: str) -> list[str]:
    latin = re.findall(r"[a-z0-9]{2,}", value.lower())
    cjk_chunks = re.findall(r"[\u3400-\u9fff]{2,}", value)
    cjk = [
        chunk[index : index + 2]
        for chunk in cjk_chunks
        for index in range(max(1, len(chunk) - 1))
    ]
    return latin + cjk


def _unique_error_codes(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value if value in ERROR_CODES else "provider_error" for value in values))


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clip(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ERROR_CODES",
    "EXA_SEARCH_ENDPOINT",
    "DisabledSearchProvider",
    "ExaSearchProvider",
    "POLICY_VERSION",
    "PURPOSE_LIMITS",
    "RetrievalGateway",
    "RetrievalProviderError",
    "RetrievalRequest",
    "SearchProvider",
    "SearXNGSearchProvider",
    "admitted_sources",
    "classify_source",
    "configured_retrieval_gateway",
    "create_search_provider",
    "redact_outbound_query",
    "resolve_retrieval_policy",
    "retrieval_feature_state",
]
