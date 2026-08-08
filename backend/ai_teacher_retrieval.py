"""Conversation-scoped retrieval helpers for the AI teacher."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from course_versioning import stable_hash
from web_retrieval import (
    RetrievalGateway,
    RetrievalRequest,
    admitted_sources,
    configured_retrieval_gateway,
)

_SEARCH_COMMAND_PATTERNS = (
    re.compile(
        r"(?:^|[\s,.;:!?，。；：！？、])"
        r"(?:再|请|帮我|麻烦)?(?:联网|上网|网页|网络)?"
        r"(?:搜索|检索|搜|查找|查询|查)(?:一下|下|一搜|一查)?",
        re.I,
    ),
    re.compile(
        r"(?:^|[\s,.;:!?，。；：！？、])(?:找|给|来)(?:点|些|一些|几个)?"
        r"(?=\s*[\w\u3400-\u9fff])",
        re.I,
    ),
    re.compile(
        r"\b(?:please\s+)?(?:search|look\s+up|find|google|web\s+search)"
        r"(?:\s+(?:the\s+web|online|for|me))*\b",
        re.I,
    ),
)
_QUESTION_FILLER_PATTERN = re.compile(
    r"^(?:什么是|什么叫|何为|如何理解|请解释(?:一下)?|解释(?:一下)?|介绍(?:一下)?)"
    r"\s*",
    re.I,
)
_EXAMPLE_QUERY_TERM_PATTERN = re.compile(
    r"(?:例子|示例|案例|\bexamples?\b)",
    re.I,
)


def build_ai_teacher_queries(
    course: dict[str, Any],
    *,
    question: str,
    node_id: str = "",
) -> list[str]:
    """Use only the current question and public course structure."""

    course_name = _safe_term(
        str(course.get("course_name") or course.get("subject") or "course")
    )
    current_question = _safe_term(question)
    node = next(
        (
            item
            for item in course.get("nodes") or []
            if str(item.get("node_id") or "") == str(node_id or "")
        ),
        {},
    )
    node_name = _safe_term(str(node.get("node_name") or ""))
    objective = _safe_term(str(node.get("learning_objective") or ""))
    search_question = _search_intent_term(current_question)
    queries = [search_question] if search_question else []
    tutorial_variant = _tutorial_search_variant(search_question)
    if tutorial_variant and tutorial_variant not in queries:
        queries.append(tutorial_variant)
    primary = _join(course_name, node_name, objective, search_question)
    if primary and primary not in queries:
        queries.append(primary)
    if search_question and objective:
        focused = _join(search_question, objective, "public reference")
        if focused not in queries:
            queries.append(focused)
    return queries[:3]


async def retrieve_ai_teacher_sources(
    course: dict[str, Any],
    *,
    question: str,
    node_id: str,
    user_id: str,
    gateway: RetrievalGateway | None = None,
) -> dict[str, Any]:
    if gateway is None:
        gateway, feature = configured_retrieval_gateway(user_id)
    else:
        feature = {"enabled_for_user": True, "injected_gateway": True}
    queries = build_ai_teacher_queries(
        course,
        question=question,
        node_id=node_id,
    )
    package = await gateway.retrieve(
        RetrievalRequest(
            purpose="ai_teacher",
            enabled=True,
            queries=queries,
            request_fingerprint=stable_hash(
                {
                    "course_id": course.get("course_id"),
                    "course_version_id": course.get(
                        "current_course_version_id"
                    ),
                    "node_id": node_id,
                    "question": stable_hash(
                        _safe_term(question), prefix="query_"
                    ),
                },
                prefix="rrq_",
            ),
        )
    )
    package["feature"] = feature
    return package


def merge_ai_teacher_retrieval(
    context_package: dict[str, Any],
    retrieval_package: dict[str, Any],
) -> dict[str, Any]:
    """Attach admitted web summaries without exposing private model context."""

    merged = deepcopy(context_package)
    web_sources: list[dict[str, Any]] = []
    for index, source in enumerate(_ai_teacher_sources(retrieval_package), start=1):
        citation_id = f"S{index}"
        web_sources.append(
            {
                "source_id": source.get("source_id"),
                "type": "web",
                "citation_id": citation_id,
                "title": source.get("title"),
                "url": source.get("url"),
                "domain": source.get("domain"),
                "content": source.get("excerpt"),
                "excerpt": source.get("excerpt"),
                "published_date": source.get("published_date"),
                "retrieved_at": source.get("retrieved_at"),
                "content_hash": source.get("content_hash"),
                "provider": source.get("provider"),
                "trust_tier": source.get("trust_tier"),
                "license": source.get("license"),
                "reuse_policy": "summary_only",
            }
        )
    merged["sources"] = [
        *deepcopy(merged.get("sources") or []),
        *web_sources,
    ]
    merged["web_retrieval"] = {
        "schema_version": "ai_teacher_web_retrieval_v1",
        "status": retrieval_package.get("status"),
        "receipt": deepcopy(retrieval_package.get("receipt") or {}),
        "package_revision": retrieval_package.get("revision"),
        "package_hash": retrieval_package.get("package_hash"),
        "source_count": len(web_sources),
    }
    return merged


def _ai_teacher_sources(
    retrieval_package: dict[str, Any],
) -> list[dict[str, Any]]:
    tier_a = admitted_sources(retrieval_package)
    if tier_a:
        return tier_a
    # AI-teacher replies can cite a small number of gateway-filtered tier B
    # references when primary sources are unavailable. Tier C sources remain
    # excluded, and the original trust tier stays visible to the caller.
    tier_b = [
        source
        for source in retrieval_package.get("sources") or []
        if source.get("trust_tier") == "tier_b"
    ]
    return sorted(
        tier_b,
        key=lambda source: float(source.get("relevance") or 0),
        reverse=True,
    )[:2]


def should_retrieve_for_message(
    conversation: dict[str, Any] | None,
    *,
    direct_action: str | None,
) -> bool:
    return bool(
        (conversation or {}).get("retrieval_enabled")
        and not direct_action
    )


def _safe_term(value: str) -> str:
    text = " ".join(
        str(value or "").replace("\r", " ").replace("\n", " ").split()
    )
    return text[:1000]


def _search_intent_term(value: str) -> str:
    text = _safe_term(value)
    for pattern in _SEARCH_COMMAND_PATTERNS:
        text = pattern.sub(" ", text)
    text = text.strip()
    text = _QUESTION_FILLER_PATTERN.sub("", text)
    text = re.sub(r"[\s,.;:!?，。；：！？、]+", " ", text).strip()
    return text[:1000] or _safe_term(value)


def _tutorial_search_variant(value: str) -> str:
    if not re.search(r"[\u3400-\u9fff]", value):
        return ""
    text = _EXAMPLE_QUERY_TERM_PATTERN.sub(" ", value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text == value:
        return ""
    return _join(text, "教程")


def _join(*values: str) -> str:
    return " ".join(value for value in values if value).strip()[:1000]


__all__ = [
    "build_ai_teacher_queries",
    "merge_ai_teacher_retrieval",
    "retrieve_ai_teacher_sources",
    "should_retrieve_for_message",
]
