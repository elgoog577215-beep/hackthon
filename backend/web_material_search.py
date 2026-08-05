"""联网资料检索：从课程需求推导查询，把采纳结果落成资料资产。

关键约束：联网资料**不建立平行真源**。命中的网页会经 `create_text_asset`
成为普通 `MaterialAsset`，再走既有 parse -> evidence -> grounding 链，
与教师导入的资料完全同路。本模块只负责"搜什么、留哪些、怎么标注来源"。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from web_search_config import WebSearchPolicy, normalize_domain
from web_search_provider import (
    RobotsGate,
    SearchCallable,
    WebMaterialSearch,
    content_hash,
    detect_open_license,
    safe_query_term,
    sanitize_untrusted_text,
)

# 搜索结果作为资料的最低正文长度，短于此值不足以支撑教学内容。
MIN_USABLE_TEXT_CHARS = 200
MAX_TITLE_CHARS = 300
MAX_QUERY_CHARS = 300

_STOPWORDS = {
    "课程", "内容", "要求", "希望", "需要", "包括", "以及", "一个", "一门", "这个", "我们",
    "学生", "教学", "讲解", "重点", "基础", "并且", "可以", "能够", "掌握", "了解", "学习",
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "course",
    "students", "should", "would", "please", "need", "want", "learn", "teach",
}


def derive_search_queries(
    *,
    topic: str,
    requirements: str = "",
    target_audience: str = "",
    objectives: list[str] | None = None,
    max_queries: int,
) -> list[str]:
    """从课程主题与需求推导查询词。

    查询完全由输入推导且可展示给教师审阅，不做隐式扩写。
    """
    safe_topic = safe_query_term(topic)
    if not safe_topic:
        return []

    audience = safe_query_term(target_audience)
    phrases = _requirement_phrases(requirements)
    goals = [safe_query_term(item) for item in (objectives or [])]
    goals = [item for item in goals if item][:3]

    candidates: list[str] = []
    for goal in goals:
        candidates.append(f"{safe_topic} {goal} 教学资料")
    for phrase in phrases[:3]:
        candidates.append(f"{safe_topic} {phrase}")
    candidates.append(f"{safe_topic} 教程 开放教育资源")
    candidates.append(f"{safe_topic} lecture notes open educational resource")
    if audience:
        candidates.append(f"{safe_topic} {audience} 课程大纲")

    result: list[str] = []
    for item in candidates:
        query = re.sub(r"\s+", " ", item).strip()[:MAX_QUERY_CHARS]
        if len(query) < 2 or query in result:
            continue
        result.append(query)
        if len(result) >= max(1, int(max_queries)):
            break
    return result


def _requirement_phrases(requirements: str) -> list[str]:
    """从需求文本里取有信息量的短语，去掉套话。"""
    text = str(requirements or "")
    if not text.strip():
        return []
    segments = re.split(r"[，。；！？\n\r,;.!?、]+", text)
    phrases: list[str] = []
    for segment in segments:
        cleaned = safe_query_term(segment)
        if not cleaned or len(cleaned) < 2:
            continue
        lowered = cleaned.lower()
        if lowered in _STOPWORDS:
            continue
        tokens: list[str] = []
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_+-]{1,30}|[㐀-鿿]{2,20}", cleaned):
            if token.lower() in _STOPWORDS:
                continue
            if re.fullmatch(r"[㐀-鿿]+", token):
                # 中文连写会被整段匹配，需要把其中的套话逐个剔除后再判断剩余信息量。
                token = _strip_chinese_stopwords(token)
                if len(token) < 2:
                    continue
            tokens.append(token)
        if not tokens:
            continue
        phrase = " ".join(tokens[:4])[:80]
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _strip_chinese_stopwords(token: str) -> str:
    """从中文连写片段里去掉套话，保留真正的学科词。"""
    chinese_stopwords = sorted(
        (word for word in _STOPWORDS if re.fullmatch(r"[㐀-鿿]+", word)),
        key=len,
        reverse=True,
    )
    for word in chinese_stopwords:
        token = token.replace(word, " ")
    return re.sub(r"\s+", "", token)


def normalize_candidate(
    raw: dict[str, Any],
    *,
    policy: WebSearchPolicy,
    query: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """把 provider 原始结果归一化为带来源标注的候选，正文已清洗。"""
    url = str(raw.get("url") or "").strip()[:2000]
    highlights = raw.get("highlights") or []
    highlight_text = " ".join(str(v) for v in highlights if isinstance(v, str))
    body = str(raw.get("text") or raw.get("content") or highlight_text or raw.get("summary") or "")
    text = sanitize_untrusted_text(body, max_chars=policy.max_source_chars)
    title = sanitize_untrusted_text(str(raw.get("title") or ""), max_chars=MAX_TITLE_CHARS)
    license_name = sanitize_untrusted_text(
        str(raw.get("license") or raw.get("rights") or ""), max_chars=200
    )
    open_license = detect_open_license(license_name)
    return {
        "url": url,
        "domain": normalize_domain(urlparse(url).netloc),
        "title": title,
        "text": text,
        "author": sanitize_untrusted_text(str(raw.get("author") or ""), max_chars=300),
        "published_date": str(raw.get("publishedDate") or raw.get("published_date") or "")[:50],
        "license": license_name,
        "open_license": open_license,
        "credibility": policy.credibility_for(url, open_license=open_license),
        "content_hash": content_hash(text),
        "retrieved_at": retrieved_at,
        "query": query[:MAX_QUERY_CHARS],
    }


async def discover_web_materials(
    *,
    topic: str,
    requirements: str = "",
    target_audience: str = "",
    objectives: list[str] | None = None,
    policy: WebSearchPolicy | None = None,
    search: SearchCallable | None = None,
    robots_gate: RobotsGate | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """执行一次联网资料检索，返回可供教师审阅的候选与完整搜索记录。

    永不抛异常：任何失败都体现为 status 与 degraded 标记，让生成流程继续。
    """
    from web_search_provider import RateLimiter  # 局部导入避免循环依赖顾虑

    active_policy = policy or WebSearchPolicy.from_env()
    retrieved_at = now or _timestamp()
    report: dict[str, Any] = {
        "enabled": bool(active_policy.enabled),
        "status": "disabled",
        "degraded": True,
        "queries": [],
        "candidates": [],
        "rejected": [],
        "query_count": 0,
        "candidate_count": 0,
        "policy": active_policy.to_dict(),
        "retrieved_at": retrieved_at,
        "message_code": "web_search_disabled",
    }
    if not active_policy.enabled:
        return report

    queries = derive_search_queries(
        topic=topic,
        requirements=requirements,
        target_audience=target_audience,
        objectives=objectives,
        max_queries=active_policy.max_queries,
    )
    report["queries"] = list(queries)
    report["query_count"] = len(queries)
    if not queries:
        report.update(status="no_queries", message_code="web_search_no_queries")
        return report

    client = WebMaterialSearch(
        policy=active_policy,
        search=search,
        robots_gate=robots_gate,
        rate_limiter=RateLimiter(active_policy.min_request_interval_seconds),
    )
    if not client.configured:
        report.update(
            status="unavailable_not_configured",
            message_code="web_search_not_configured",
        )
        return report

    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    provider_failures = 0

    for query in queries:
        if len(candidates) >= active_policy.max_sources:
            break
        try:
            results = await client.search(query)
        except Exception:
            results = []
        if not results:
            provider_failures += 1
            continue
        for raw in results:
            if len(candidates) >= active_policy.max_sources:
                break
            candidate = normalize_candidate(
                raw, policy=active_policy, query=query, retrieved_at=retrieved_at
            )
            url = candidate["url"]
            if not url or url in seen_urls:
                continue
            accepted, reason = await client.candidate_verdict(url, candidate["text"])
            if not accepted:
                seen_urls.add(url)
                rejected.append({"url": url, "reason": reason, "query": query})
                continue
            if len(candidate["text"]) < MIN_USABLE_TEXT_CHARS:
                seen_urls.add(url)
                rejected.append({"url": url, "reason": "insufficient_text", "query": query})
                continue
            if candidate["content_hash"] in seen_hashes:
                seen_urls.add(url)
                rejected.append({"url": url, "reason": "duplicate_content", "query": query})
                continue
            seen_urls.add(url)
            seen_hashes.add(candidate["content_hash"])
            candidates.append(candidate)

    report["candidates"] = candidates
    report["candidate_count"] = len(candidates)
    report["rejected"] = rejected
    if candidates:
        report.update(status="ready", degraded=False, message_code="web_search_ready")
    elif provider_failures >= len(queries):
        report.update(status="provider_unavailable", message_code="web_search_provider_failed")
    else:
        report.update(status="no_results", message_code="web_search_no_results")
    return report


def candidate_to_markdown(candidate: dict[str, Any]) -> str:
    """把候选渲染为带出处头的 Markdown，落地后仍能回溯来源。

    正文以引用块呈现，明确这是他人内容而非平台原创产物。
    """
    title = str(candidate.get("title") or candidate.get("url") or "联网资料")
    lines = [
        f"# {title}",
        "",
        "> 本文为联网检索得到的外部参考资料，非平台原创内容。",
        "",
        f"- 来源 URL：{candidate.get('url') or '未知'}",
        f"- 来源域名：{candidate.get('domain') or '未知'}",
        f"- 抓取时间：{candidate.get('retrieved_at') or '未知'}",
        f"- 可信度标记：{candidate.get('credibility') or 'low'}",
        f"- 检索查询：{candidate.get('query') or ''}",
    ]
    if candidate.get("author"):
        lines.append(f"- 作者：{candidate['author']}")
    if candidate.get("published_date"):
        lines.append(f"- 发布时间：{candidate['published_date']}")
    lines.append(f"- 许可信息：{candidate.get('license') or '未标注'}")
    lines.extend(["", "## 摘录正文", ""])
    body = str(candidate.get("text") or "").strip()
    lines.extend(f"> {line}" if line.strip() else ">" for line in body.splitlines() or [""])
    return "\n".join(lines) + "\n"


def candidate_to_binding(candidate: dict[str, Any], asset_id: str) -> dict[str, Any]:
    """联网资料的绑定策略：只做参考、不逐字复用、权利状态明确未知。"""
    credibility = str(candidate.get("credibility") or "low")
    open_license = bool(candidate.get("open_license"))
    return {
        "asset_id": asset_id,
        "purpose": "supplement" if credibility == "high" else "weak_context",
        "priority": "supporting" if credibility == "high" else "weak",
        # 联网资料永不作为 primary 权威，教师导入资料优先级更高。
        "authority": "secondary" if credibility == "high" else "context_only",
        "usage_policy": "prefer" if credibility == "high" else "optional",
        # 未标注开放许可时一律只引用，不允许逐字搬运。
        "reuse_policy": "verbatim_allowed" if open_license else "reference_only",
        "rights_basis": "open_license" if open_license else "license_unknown",
        "source_metadata": {
            "origin": "web_search",
            "url": candidate.get("url") or "",
            "domain": candidate.get("domain") or "",
            "retrieved_at": candidate.get("retrieved_at") or "",
            "credibility": credibility,
            "content_hash": candidate.get("content_hash") or "",
            "query": candidate.get("query") or "",
            "license": candidate.get("license") or "",
            "published_date": candidate.get("published_date") or "",
            "author": candidate.get("author") or "",
        },
        "source_label": str(candidate.get("title") or candidate.get("domain") or "联网资料")[:200],
        "user_description": f"联网检索（{credibility} 可信度）：{candidate.get('url') or ''}"[:2000],
    }


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "MIN_USABLE_TEXT_CHARS",
    "candidate_to_binding",
    "candidate_to_markdown",
    "derive_search_queries",
    "discover_web_materials",
    "normalize_candidate",
]
