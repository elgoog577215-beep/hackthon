"""Bounded full-text reading and deterministic restructuring for web research.

This module is an internal stage behind the existing course web-research API.
It never creates a second retrieval endpoint or source of truth: admitted
search results are enriched in place, then selected results continue through
the ordinary material/evidence pipeline.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
import tempfile
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from web_retrieval import sanitize_untrusted_web_text

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_TEXT_CHARS = 12_000
MAX_DEEP_DOCUMENTS = 8
MAX_DEEP_READ_SECONDS = 18.0
MIN_USEFUL_DOCUMENT_CHARS = 320
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "td", "th"}
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "template",
    "form",
    "nav",
    "header",
    "footer",
    "aside",
}
_SOURCE_TYPE_DOMAINS = {
    "academic": ("arxiv.org", "doi.org", "openalex.org", "crossref.org", "pubmed.ncbi.nlm.nih.gov"),
    "reference": ("wikipedia.org", "britannica.com"),
}

HostResolver = Callable[[str, int], Awaitable[bool]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_public_https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return address.is_global
    except (ValueError, UnicodeError):
        return False


async def _resolve_public_host(host: str, port: int) -> bool:
    loop = asyncio.get_running_loop()
    try:
        # The runtime client is bound to IPv4 below, so validate the exact
        # address family it can dial. This avoids rejecting a safe public A
        # record because the local resolver also injects an unusable/private
        # IPv6 compatibility address.
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        addresses = {ipaddress.ip_address(record[4][0]) for record in records}
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(address.is_global for address in addresses)


def _clip(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


class _ArticleHTMLParser(HTMLParser):
    """Extract headings and article-like blocks without adding a parser dependency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.author = ""
        self.published_date = ""
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._skip_depth = 0
        self._primary_depth = 0
        self._block_tag = ""
        self._block_primary = False
        self._block_parts: list[str] = []
        self.blocks: list[tuple[str, str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in {"main", "article"}:
            self._primary_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag == "meta":
            key = (data.get("name") or data.get("property") or data.get("itemprop") or "").lower()
            content = _clip(data.get("content"), 500)
            if key in {"author", "article:author", "byl"} and content and not self.author:
                self.author = content
            if key in {
                "article:published_time",
                "datepublished",
                "date",
                "publishdate",
                "publish-date",
                "dc.date",
            } and content and not self.published_date:
                self.published_date = content
        if tag in _BLOCK_TAGS and not self._block_tag:
            self._block_tag = tag
            self._block_primary = self._primary_depth > 0
            self._block_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == self._block_tag:
            text = sanitize_untrusted_web_text(" ".join(self._block_parts), limit=4_000)
            if len(text) >= 2:
                self.blocks.append((tag, text, self._block_primary))
            self._block_tag = ""
            self._block_primary = False
            self._block_parts = []
        if tag == "title":
            self._title_depth = max(0, self._title_depth - 1)
            if not self._title_depth and not self.title:
                self.title = sanitize_untrusted_web_text(" ".join(self._title_parts), limit=500)
        if tag in {"main", "article"}:
            self._primary_depth = max(0, self._primary_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._title_depth:
            self._title_parts.append(data)
        if self._block_tag:
            self._block_parts.append(data)

    def structured_text(self) -> tuple[str, list[str]]:
        primary = [block for block in self.blocks if block[2]]
        chosen = primary if sum(len(block[1]) for block in primary) >= MIN_USEFUL_DOCUMENT_CHARS else self.blocks
        lines: list[str] = []
        headings: list[str] = []
        seen: set[str] = set()
        for tag, text, _is_primary in chosen:
            compact = re.sub(r"\s+", "", text).lower()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            if tag.startswith("h") and tag[1:].isdigit():
                level = min(6, max(1, int(tag[1:])))
                headings.append(text[:200])
                lines.extend([f"{'#' * level} {text}", ""])
            elif tag == "li":
                lines.append(f"- {text}")
            elif tag in {"td", "th"}:
                lines.append(f"| {text} |")
            else:
                lines.extend([text, ""])
        return "\n".join(lines).strip(), headings[:40]


def _extract_html(content: bytes, encoding: str) -> dict[str, Any]:
    parser = _ArticleHTMLParser()
    parser.feed(content.decode(encoding or "utf-8", errors="replace"))
    text, headings = parser.structured_text()
    return {
        "text": text[:MAX_DOCUMENT_TEXT_CHARS],
        "title": parser.title,
        "author": parser.author,
        "published_date": parser.published_date,
        "headings": headings,
        "extractor": "builtin_article_html",
        "warnings": [],
    }


def _extract_pdf(content: bytes) -> dict[str, Any]:
    try:
        from markitdown import MarkItDown

        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            temporary.write(content)
            temporary.flush()
            converted = MarkItDown().convert(temporary.name)
        text = str(getattr(converted, "text_content", "") or "").strip()
        return {
            "text": text[:MAX_DOCUMENT_TEXT_CHARS],
            "title": "",
            "author": "",
            "published_date": "",
            "headings": [
                line.lstrip("# ").strip()[:200]
                for line in text.splitlines()
                if re.match(r"^#{1,6}\s+\S", line)
            ][:40],
            "extractor": "markitdown_pdf",
            "warnings": ["PDF页码与版面定位将在课程资料解析阶段补充"],
        }
    except Exception:
        return {
            "text": "",
            "title": "",
            "author": "",
            "published_date": "",
            "headings": [],
            "extractor": "pdf_unavailable",
            "warnings": ["PDF正文提取失败，已保留搜索摘要"],
        }


def _extract_plain_text(content: bytes, encoding: str) -> dict[str, Any]:
    raw = content.decode(encoding or "utf-8", errors="replace")
    lines = [
        sanitize_untrusted_web_text(line, limit=4_000)
        for line in raw.splitlines()
    ]
    text = "\n".join(line for line in lines if line).strip()[:MAX_DOCUMENT_TEXT_CHARS]
    return {
        "text": text,
        "title": "",
        "author": "",
        "published_date": "",
        "headings": [
            line.lstrip("# ").strip()[:200]
            for line in text.splitlines()
            if re.match(r"^#{1,6}\s+\S", line)
        ][:40],
        "extractor": "builtin_plain_text",
        "warnings": [],
    }


def _source_type(candidate: dict[str, Any]) -> str:
    host = str(candidate.get("domain") or urlparse(str(candidate.get("url") or "")).hostname or "").lower()
    if host.endswith((".gov", ".gov.cn")):
        return "official"
    if host.endswith((".edu", ".edu.cn")):
        return "academic"
    for source_type, domains in _SOURCE_TYPE_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return source_type
    return "general"


def _terms(value: str) -> set[str]:
    latin = set(re.findall(r"[a-z0-9]{2,}", str(value or "").lower()))
    cjk_groups = re.findall(r"[\u3400-\u9fff]{2,}", str(value or ""))
    cjk = {
        group[index : index + 2]
        for group in cjk_groups
        for index in range(max(1, len(group) - 1))
    }
    return latin | cjk


def _extract_key_points(candidate: dict[str, Any], document_text: str) -> list[dict[str, Any]]:
    """Select bounded, traceable passages instead of producing an AI-written summary."""

    query_terms = _terms(
        f"{candidate.get('matched_query') or ''} {candidate.get('title') or ''}"
    )
    section = ""
    paragraph_index = 0
    ranked: list[tuple[float, dict[str, Any]]] = []
    seen: set[str] = set()
    for raw in document_text.splitlines():
        line = raw.strip()
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            section = heading.group(1).strip()[:200]
            continue
        if not line or line.startswith("|"):
            continue
        paragraph_index += 1
        value = line[2:].strip() if line.startswith("- ") else line
        for sentence in re.split(r"(?<=[。！？!?])\s*", value):
            point = sanitize_untrusted_web_text(sentence, limit=500)
            compact = re.sub(r"\s+", "", point).lower()
            if len(point) < 28 or compact in seen:
                continue
            seen.add(compact)
            point_terms = _terms(point)
            overlap = len(query_terms & point_terms)
            score = overlap / max(1, min(12, len(query_terms)))
            if section and _terms(section) & query_terms:
                score += 0.1
            ranked.append((score, {
                "text": point,
                "section": section,
                "paragraph": paragraph_index,
            }))
    ranked.sort(key=lambda pair: (pair[0], -pair[1]["paragraph"]), reverse=True)
    relevant = [item for score, item in ranked if score > 0]
    selected = relevant[:6] if relevant else [item for _score, item in ranked[:4]]
    return selected


class SafeWebDocumentReader:
    """Read one public HTTPS document with DNS, redirect, size and MIME gates."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: HostResolver | None = None,
        timeout_seconds: float = 12.0,
        max_bytes: int = MAX_DOCUMENT_BYTES,
    ) -> None:
        self._client = client
        self._resolver = resolver or _resolve_public_host
        self.timeout_seconds = max(1.0, min(20.0, float(timeout_seconds)))
        self.max_bytes = max(1_024, min(MAX_DOCUMENT_BYTES, int(max_bytes)))

    async def read(self, url: str) -> dict[str, Any]:
        current = str(url or "").strip()
        if not _safe_public_https_url(current):
            return self._failure("unsafe_url")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            trust_env=False,
            headers={"User-Agent": "LingzhiCourseResearch/1.0"},
            transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=0),
        )
        try:
            for _redirect in range(4):
                parsed = urlparse(current)
                if not await self._resolver(parsed.hostname or "", parsed.port or 443):
                    return self._failure("unsafe_host")
                try:
                    async with client.stream("GET", current, follow_redirects=False) as response:
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location", "")
                            redirected = urljoin(current, location)
                            if not location or not _safe_public_https_url(redirected):
                                return self._failure("unsafe_redirect")
                            current = redirected
                            continue
                        if response.status_code < 200 or response.status_code >= 300:
                            return self._failure(f"http_{response.status_code}")
                        declared_length = int(response.headers.get("content-length", "0") or 0)
                        if declared_length > self.max_bytes:
                            return self._failure("document_too_large")
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > self.max_bytes:
                                return self._failure("document_too_large")
                        mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        raw = bytes(content)
                        if mime == "application/pdf" or raw.startswith(b"%PDF"):
                            extracted = await asyncio.to_thread(_extract_pdf, raw)
                            content_type = "application/pdf"
                        elif mime in {"", "text/html", "application/xhtml+xml"} or b"<html" in raw[:2_000].lower():
                            extracted = _extract_html(raw, response.encoding or "utf-8")
                            content_type = mime or "text/html"
                        elif mime in {"text/plain", "text/markdown"}:
                            extracted = _extract_plain_text(raw, response.encoding or "utf-8")
                            content_type = mime
                        else:
                            return self._failure("unsupported_content_type", content_type=mime)
                        text = str(extracted.get("text") or "").strip()
                        if len(text) < MIN_USEFUL_DOCUMENT_CHARS:
                            return self._failure("insufficient_full_text", content_type=content_type)
                        return {
                            "status": "full_text",
                            "url": current,
                            "content_type": content_type,
                            "text": text,
                            "title": str(extracted.get("title") or ""),
                            "author": str(extracted.get("author") or ""),
                            "published_date": str(extracted.get("published_date") or ""),
                            "headings": list(extracted.get("headings") or []),
                            "extractor": str(extracted.get("extractor") or ""),
                            "warnings": list(extracted.get("warnings") or []),
                            "fetched_at": _now(),
                            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                            "text_length": len(text),
                        }
                except httpx.TimeoutException:
                    return self._failure("timeout")
                except (httpx.HTTPError, ValueError, UnicodeError):
                    return self._failure("fetch_failed")
            return self._failure("too_many_redirects")
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _failure(reason: str, *, content_type: str = "") -> dict[str, Any]:
        return {
            "status": "excerpt_fallback",
            "reason": reason,
            "content_type": content_type,
            "text": "",
            "headings": [],
            "warnings": [reason],
        }


def diversify_retrieval_sources(sources: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Round-robin queries and domains before filling by score."""

    indexed = [dict(source) for source in sources if isinstance(source, dict)]
    indexed.sort(
        key=lambda source: (
            {"tier_a": 2, "tier_b": 1}.get(str(source.get("trust_tier") or ""), 0),
            float(source.get("relevance") or 0),
        ),
        reverse=True,
    )
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in indexed:
        by_query[str(source.get("matched_query") or "未分类")].append(source)
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    selected_domains: set[str] = set()

    def take(source: dict[str, Any], *, require_new_domain: bool) -> bool:
        key = str(source.get("source_id") or source.get("canonical_url") or source.get("url") or "")
        domain = str(source.get("domain") or "")
        if not key or key in selected_keys or (require_new_domain and domain in selected_domains):
            return False
        selected.append(source)
        selected_keys.add(key)
        if domain:
            selected_domains.add(domain)
        return True

    for require_new_domain in (True, False):
        pending = True
        while pending and len(selected) < max(0, int(limit)):
            pending = False
            for query_sources in by_query.values():
                for source in query_sources:
                    if take(source, require_new_domain=require_new_domain):
                        pending = True
                        break
                if len(selected) >= limit:
                    break
    return selected[: max(0, int(limit))]


async def enrich_web_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_documents: int = MAX_DEEP_DOCUMENTS,
    reader: SafeWebDocumentReader | None = None,
    concurrency: int = 3,
) -> list[dict[str, Any]]:
    """Deep-read top candidates in place while keeping excerpt fallback."""

    enriched = [dict(candidate) for candidate in candidates]
    target_count = min(len(enriched), max(0, int(max_documents)), MAX_DEEP_DOCUMENTS)
    if target_count <= 0:
        return enriched
    document_reader = reader or SafeWebDocumentReader()
    semaphore = asyncio.Semaphore(max(1, min(4, int(concurrency))))

    async def read_one(index: int) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            try:
                document = await document_reader.read(str(enriched[index].get("url") or ""))
            except Exception:
                document = SafeWebDocumentReader._failure("reader_failed")
            return index, document

    tasks = {
        asyncio.create_task(read_one(index)): index
        for index in range(target_count)
    }
    done, pending = await asyncio.wait(tasks, timeout=MAX_DEEP_READ_SECONDS)
    results: list[tuple[int, dict[str, Any]]] = []
    for task in done:
        try:
            results.append(task.result())
        except Exception:
            results.append((tasks[task], SafeWebDocumentReader._failure("reader_failed")))
    for task in pending:
        task.cancel()
        results.append((tasks[task], SafeWebDocumentReader._failure("depth_timeout")))
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    for index, document in results:
        candidate = enriched[index]
        candidate["source_type"] = _source_type(candidate)
        candidate["content_status"] = str(document.get("status") or "excerpt_fallback")
        candidate["content_reason"] = str(document.get("reason") or "")
        candidate["content_type"] = str(document.get("content_type") or "")
        if candidate["content_status"] != "full_text":
            continue
        candidate["document_text"] = str(document.get("text") or "")[:MAX_DOCUMENT_TEXT_CHARS]
        candidate["document"] = {
            "schema_version": "web_document_v1",
            "url": str(document.get("url") or candidate.get("url") or "")[:2_000],
            "title": str(document.get("title") or candidate.get("title") or "")[:500],
            "author": str(document.get("author") or "")[:500],
            "published_date": str(document.get("published_date") or candidate.get("published_date") or "")[:100],
            "headings": [str(item)[:200] for item in document.get("headings") or []][:40],
            "content_type": candidate["content_type"][:100],
            "extractor": str(document.get("extractor") or "")[:100],
            "fetched_at": str(document.get("fetched_at") or "")[:100],
            "content_hash": str(document.get("content_hash") or "")[:100],
            "text_length": int(document.get("text_length") or 0),
            "warnings": [str(item)[:300] for item in document.get("warnings") or []][:8],
            "key_points": _extract_key_points(candidate, candidate["document_text"]),
        }
        if document.get("published_date") and not candidate.get("published_date"):
            candidate["published_date"] = str(document["published_date"])
    for candidate in enriched[target_count:]:
        candidate["source_type"] = _source_type(candidate)
        candidate["content_status"] = "not_read"
        candidate["content_reason"] = "depth_budget"
    return enriched


def build_research_summary(
    *,
    queries: list[str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a compact coverage matrix for teacher review and later synthesis."""

    query_groups: list[dict[str, Any]] = []
    for query in queries:
        matched = [item for item in candidates if str(item.get("matched_query") or "") == query]
        evidence_points: list[dict[str, Any]] = []
        for item in matched:
            document = item.get("document") if isinstance(item.get("document"), dict) else {}
            for point in document.get("key_points") or []:
                if not isinstance(point, dict):
                    continue
                evidence_points.append({
                    "source_id": str(item.get("source_id") or ""),
                    "title": str(item.get("title") or "")[:500],
                    "text": str(point.get("text") or "")[:500],
                    "section": str(point.get("section") or "")[:200],
                    "paragraph": max(0, int(point.get("paragraph") or 0)),
                })
        query_groups.append({
            "query": query,
            "source_ids": [str(item.get("source_id") or "") for item in matched if item.get("source_id")],
            "source_count": len(matched),
            "full_text_count": sum(item.get("content_status") == "full_text" for item in matched),
            "high_trust_count": sum(item.get("credibility") == "high" for item in matched),
            "evidence_points": evidence_points[:8],
            "status": "covered" if matched else "gap",
        })
    source_types: dict[str, int] = defaultdict(int)
    domains: set[str] = set()
    for candidate in candidates:
        source_types[str(candidate.get("source_type") or _source_type(candidate))] += 1
        if candidate.get("domain"):
            domains.add(str(candidate["domain"]))
    return {
        "schema_version": "web_research_summary_v1",
        "source_count": len(candidates),
        "domain_count": len(domains),
        "full_text_count": sum(item.get("content_status") == "full_text" for item in candidates),
        "excerpt_fallback_count": sum(item.get("content_status") == "excerpt_fallback" for item in candidates),
        "source_types": dict(sorted(source_types.items())),
        "query_coverage": query_groups,
        "gaps": [group["query"] for group in query_groups if group["status"] == "gap"],
    }


__all__ = [
    "MAX_DEEP_DOCUMENTS",
    "MAX_DOCUMENT_TEXT_CHARS",
    "SafeWebDocumentReader",
    "build_research_summary",
    "diversify_retrieval_sources",
    "enrich_web_candidates",
]
