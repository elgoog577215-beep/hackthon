"""联网资料落成课程资料资产。

检索本身由团队的 `web_retrieval.RetrievalGateway` 拥有：provider 选择、
信誉分级、PII 脱敏、注入清洗、灰度授权与幂等回执都在那一层。本模块只做
团队没做的一段——把已准入的检索来源变成**普通资料资产**，走 parse →
evidence → grounding 这条既有链，而不是另开一条 Prompt 注入路径。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from web_retrieval import (
    RetrievalRequest,
    admitted_sources,
    configured_retrieval_gateway,
    resolve_retrieval_policy,
)

# 落地为资料资产的最低正文长度。
# SearXNG 返回的是搜索引擎摘要（snippet）而非整页正文，实测（2026-08-06）
# 中文来源摘要常在 100-200 字之间，英文在 250-700 字之间。原先按 Exa 全文
# 场景定的 200 字阈值会把合格的中文 tier_a 来源整批挡掉，故下调到 80。
# 这不降低质量门：相关性与可信度由网关的 tier 判定负责，这里只排除空壳页面。
MIN_USABLE_TEXT_CHARS = 80
MAX_QUERY_CHARS = 300

_STOPWORDS = {
    "课程", "内容", "要求", "希望", "需要", "包括", "以及", "一个", "一门", "这个", "我们",
    "学生", "教学", "讲解", "重点", "基础", "并且", "可以", "能够", "掌握", "了解", "学习",
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "course",
    "students", "should", "would", "please", "need", "want", "learn", "teach",
}


def _contains_cjk(value: str) -> bool:
    """判断查询主题是否为中文，用于选择同语言的兜底资料词。"""
    return bool(re.search(r"[㐀-鿿]", str(value or "")))


def safe_query_term(value: str) -> str:
    """查询词只保留安全字符，避免把用户/模型文本原样拼进外部请求。"""
    text = re.sub(r"[\r\n\t]+", " ", str(value or ""))
    text = re.sub(r"[^\w㐀-鿿 .,+\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


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
    网关还会再做一次 PII 脱敏，这里只负责语义构造。

    刻意保持查询简短：网关的 `_relevance()` 按查询词与标题/摘要的重合度打分，
    低于 0.55 直接判 `low_relevance` 落到 tier_c。实测（2026-08-06，真实
    SearXNG）拼接"教学资料""开放教育资源"这类套话会把所有来源稀释成 tier_c，
    准入数从 8 条掉到 0 条。因此这里只输出主题 + 具体知识点。
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
        candidates.append(f"{safe_topic} {goal}")
    for phrase in phrases[:3]:
        candidates.append(f"{safe_topic} {phrase}")
    # 兜底查询与主题同语言：中文主题配英文资料词（或反之）会让搜索引擎
    # 返回跨语言噪音，进而被网关判 low_relevance。
    candidates.append(
        f"{safe_topic} 讲义" if _contains_cjk(safe_topic) else f"{safe_topic} lecture notes"
    )
    if audience:
        candidates.append(f"{safe_topic} {audience}")

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
        if cleaned.lower() in _STOPWORDS:
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


async def discover_web_materials(
    *,
    topic: str,
    requirements: str = "",
    target_audience: str = "",
    objectives: list[str] | None = None,
    generation_request: dict[str, Any] | None = None,
    ingest_settings: dict[str, Any] | None = None,
    user_id: str | None = None,
    gateway: Any = None,
    feature: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """经团队检索网关取回来源，转成可落地的资料候选。

    永不抛异常：任何失败都体现为 status 与 degraded 标记，让生成流程继续。
    """
    settings = ingest_settings or {}
    policy = resolve_retrieval_policy(generation_request or {})
    report: dict[str, Any] = {
        "enabled": bool(policy.get("enabled")),
        "status": "disabled",
        "degraded": True,
        "queries": [],
        "candidates": [],
        "rejected": [],
        "query_count": 0,
        "candidate_count": 0,
        "policy": {
            "enabled": bool(policy.get("enabled")),
            "scopes": list(policy.get("scopes") or []),
            "source": str(policy.get("source") or "default_off"),
        },
        "retrieved_at": now or "",
        "message_code": "web_search_disabled",
    }
    # 旧的题库联网开关只覆盖 assessment，不放行课程资料检索。
    if not policy.get("enabled") or "course" not in (policy.get("scopes") or []):
        return report
    # 教师可以只用引用、不落资料库。
    if bool(settings.get("skip_ingest")):
        report.update(status="ingest_skipped", message_code="web_search_ingest_skipped")
        return report

    if gateway is None:
        gateway, feature = configured_retrieval_gateway(user_id)
    feature = feature or {}
    report["policy"]["provider"] = str(feature.get("provider") or "")
    if feature and not feature.get("enabled_for_user", True):
        report.update(
            status="unavailable_not_configured",
            message_code="web_search_not_configured",
        )
        return report

    queries = derive_search_queries(
        topic=topic,
        requirements=requirements,
        target_audience=target_audience,
        objectives=objectives,
        # 刻意只发少量查询：网关按 ceil(max_sources / 查询数) 给每条查询分配
        # 取回额度，查询越多每条取回越浅。实测（2026-08-06 真实 SearXNG）
        # 中文查询发 3 条时每条只取前 8 条结果，而中文搜索前 8 名多为
        # 百科/问答/博客聚合站，全部判 low_relevance，准入从 3 条掉到 0 条。
        max_queries=2,
    )
    report["queries"] = list(queries)
    report["query_count"] = len(queries)
    if not queries:
        report.update(status="no_queries", message_code="web_search_no_queries")
        return report

    try:
        package = await gateway.retrieve(RetrievalRequest(
            purpose="course",
            enabled=True,
            queries=queries,
        ))
    except Exception:
        report.update(
            status="provider_unavailable",
            message_code="web_search_provider_failed",
        )
        return report

    report["retrieved_at"] = str(package.get("retrieved_at") or report["retrieved_at"])
    report["package_hash"] = str(package.get("package_hash") or "")
    report["receipt"] = package.get("receipt") or {}
    report["queries"] = [str(item) for item in (package.get("queries") or queries)]
    report["query_count"] = len(report["queries"])

    excluded = _excluded_keys(settings)
    admitted = admitted_sources(
        package,
        accepted_source_ids=settings.get("accepted_source_ids") or [],
    )
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [
        {
            "url": str(item.get("url") or ""),
            "reason": (item.get("rejection_reasons") or ["not_admitted"])[0],
            "source_id": str(item.get("source_id") or ""),
        }
        for item in (package.get("rejected_sources") or [])
    ]
    for source in admitted:
        candidate = candidate_from_source(source)
        if _is_excluded(candidate, excluded):
            rejected.append({
                "url": candidate["url"],
                "reason": "excluded_by_teacher",
                "source_id": candidate["source_id"],
            })
            continue
        if len(candidate["text"]) < MIN_USABLE_TEXT_CHARS:
            rejected.append({
                "url": candidate["url"],
                "reason": "insufficient_text",
                "source_id": candidate["source_id"],
            })
            continue
        candidates.append(candidate)

    report["candidates"] = candidates
    report["candidate_count"] = len(candidates)
    report["rejected"] = rejected
    status = str(package.get("status") or "")
    if candidates:
        report.update(status="ready", degraded=False, message_code="web_search_ready")
    elif status in {"failed", "error"} or package.get("errors"):
        report.update(
            status="provider_unavailable",
            message_code="web_search_provider_failed",
        )
    else:
        report.update(status="no_results", message_code="web_search_no_results")
    return report


def _excluded_keys(settings: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in settings.get("excluded_source_ids") or []:
        text = str(value or "").strip()
        if text:
            keys.add(text)
    for value in settings.get("excluded_urls") or []:
        text = _canonical_url(value)
        if text:
            keys.add(text)
    return keys


def _is_excluded(candidate: dict[str, Any], excluded: set[str]) -> bool:
    if not excluded:
        return False
    return bool(
        candidate.get("source_id") in excluded
        or _canonical_url(candidate.get("url")) in excluded
        or _canonical_url(candidate.get("canonical_url")) in excluded
    )


def _canonical_url(value: Any) -> str:
    """URL 归一化，便于教师逐条剔除时稳定比对（忽略末尾斜杠与大小写）。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme:
        return raw.rstrip("/").lower()
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    canonical = f"{parsed.scheme.lower()}://{host}{path}"
    return f"{canonical}?{parsed.query}" if parsed.query else canonical


def candidate_from_source(source: dict[str, Any]) -> dict[str, Any]:
    """把网关的 `retrieval_source_v1` 转成落地候选。

    正文已由网关清洗与截断，这里不再重复清洗，只做资料链需要的字段映射。
    """
    trust_tier = str(source.get("trust_tier") or "tier_c")
    return {
        "source_id": str(source.get("source_id") or ""),
        "url": str(source.get("url") or ""),
        "canonical_url": str(source.get("canonical_url") or ""),
        "domain": str(source.get("domain") or ""),
        "title": str(source.get("title") or ""),
        "text": str(source.get("excerpt") or ""),
        "published_date": str(source.get("published_date") or ""),
        "license": str(source.get("license") or ""),
        "reuse_policy": str(source.get("reuse_policy") or "summary_only"),
        "trust_tier": trust_tier,
        # 沿用既有 UI 与绑定语义：tier_a/b/c 映射为 high/medium/low。
        "credibility": {"tier_a": "high", "tier_b": "medium"}.get(trust_tier, "low"),
        "content_hash": str(source.get("content_hash") or ""),
        "retrieved_at": str(source.get("retrieved_at") or ""),
        "provider": str(source.get("provider") or ""),
        "relevance": source.get("relevance"),
    }


def candidate_to_markdown(candidate: dict[str, Any]) -> str:
    """把候选渲染为带出处头的 Markdown，落地后仍能回溯来源。

    正文以引用块呈现，明确这是他人内容而非平台原创产物。
    """
    title = str(candidate.get("title") or candidate.get("url") or "联网资料")
    lines = [
        f"# {title}",
        "",
        "> 本文为联网检索得到的外部参考资料摘录，非平台原创内容。",
        "",
        f"- 来源 URL：{candidate.get('url') or '未知'}",
        f"- 来源域名：{candidate.get('domain') or '未知'}",
        f"- 抓取时间：{candidate.get('retrieved_at') or '未知'}",
        f"- 可信度标记：{candidate.get('credibility') or 'low'}（{candidate.get('trust_tier') or 'tier_c'}）",
        f"- 检索来源标识：{candidate.get('source_id') or ''}",
    ]
    if candidate.get("published_date"):
        lines.append(f"- 发布时间：{candidate['published_date']}")
    lines.append(f"- 许可信息：{candidate.get('license') or '未标注'}")
    lines.append(f"- 复用策略：{candidate.get('reuse_policy') or 'summary_only'}")
    lines.extend(["", "## 摘录正文", ""])
    body = str(candidate.get("text") or "").strip()
    lines.extend(f"> {line}" if line.strip() else ">" for line in body.splitlines() or [""])
    return "\n".join(lines) + "\n"


def candidate_to_binding(candidate: dict[str, Any], asset_id: str) -> dict[str, Any]:
    """联网资料的绑定策略：只做参考、不逐字复用、权利状态明确。"""
    credibility = str(candidate.get("credibility") or "low")
    # 网关只在明确开放许可时给 verbatim_allowed，其余一律 summary_only。
    open_license = str(candidate.get("reuse_policy") or "") == "verbatim_allowed"
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
            "source_id": candidate.get("source_id") or "",
            "url": candidate.get("url") or "",
            "domain": candidate.get("domain") or "",
            "retrieved_at": candidate.get("retrieved_at") or "",
            "credibility": credibility,
            "trust_tier": candidate.get("trust_tier") or "",
            "content_hash": candidate.get("content_hash") or "",
            "license": candidate.get("license") or "",
            "published_date": candidate.get("published_date") or "",
            "provider": candidate.get("provider") or "",
        },
        "source_label": str(candidate.get("title") or candidate.get("domain") or "联网资料")[:200],
        "user_description": f"联网检索（{credibility} 可信度）：{candidate.get('url') or ''}"[:2000],
    }


__all__ = [
    "MIN_USABLE_TEXT_CHARS",
    "candidate_from_source",
    "candidate_to_binding",
    "candidate_to_markdown",
    "derive_search_queries",
    "discover_web_materials",
    "safe_query_term",
]
