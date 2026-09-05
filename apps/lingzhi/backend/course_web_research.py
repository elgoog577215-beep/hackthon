"""课程工作台的联网调研状态。

检索还是由 ``web_retrieval`` 统一网关完成；这里只保存教师可复核的
查询、来源候选和已选课程资料引用。状态挂在课程元数据上，不建立
第二份课程内容真源。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


WEB_RESEARCH_METADATA_KEY = "course_web_research_v1"
WEB_RESEARCH_SCHEMA = "course_web_research_v1"
MAX_RESEARCH_SESSIONS = 12
MAX_RESULTS_PER_SESSION = 16
MAX_CANDIDATE_TEXT_CHARS = 12_000
MAX_DOCUMENT_HEADINGS = 40


def normalize_scope(stage: Any, lesson_id: Any = "") -> tuple[str, str]:
    normalized_stage = str(stage or "foundation").strip()[:50] or "foundation"
    normalized_lesson_id = str(lesson_id or "").strip()[:160]
    return normalized_stage, normalized_lesson_id


def normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """只保存网关已清洗的展示与入库字段，并限制单条大小。"""
    document = candidate.get("document") if isinstance(candidate.get("document"), dict) else {}
    return {
        "source_id": str(candidate.get("source_id") or "")[:240],
        "url": str(candidate.get("url") or "")[:2_000],
        "canonical_url": str(candidate.get("canonical_url") or "")[:2_000],
        "domain": str(candidate.get("domain") or "")[:240],
        "title": str(candidate.get("title") or "")[:500],
        "text": str(candidate.get("text") or "")[:MAX_CANDIDATE_TEXT_CHARS],
        "document_text": str(candidate.get("document_text") or "")[:MAX_CANDIDATE_TEXT_CHARS],
        "published_date": str(candidate.get("published_date") or "")[:80],
        "license": str(candidate.get("license") or "")[:240],
        "reuse_policy": str(candidate.get("reuse_policy") or "summary_only")[:80],
        "trust_tier": str(candidate.get("trust_tier") or "tier_c")[:40],
        "credibility": str(candidate.get("credibility") or "low")[:40],
        "content_hash": str(candidate.get("content_hash") or "")[:240],
        "retrieved_at": str(candidate.get("retrieved_at") or "")[:80],
        "provider": str(candidate.get("provider") or "")[:80],
        "matched_query": str(candidate.get("matched_query") or "")[:300],
        "source_type": str(candidate.get("source_type") or "general")[:40],
        "content_status": str(candidate.get("content_status") or "excerpt_fallback")[:40],
        "content_reason": str(candidate.get("content_reason") or "")[:120],
        "content_type": str(candidate.get("content_type") or "")[:120],
        "document": {
            "schema_version": "web_document_v1",
            "url": str(document.get("url") or candidate.get("url") or "")[:2_000],
            "title": str(document.get("title") or candidate.get("title") or "")[:500],
            "author": str(document.get("author") or "")[:500],
            "published_date": str(document.get("published_date") or "")[:100],
            "headings": [
                str(value)[:200] for value in document.get("headings") or []
            ][:MAX_DOCUMENT_HEADINGS],
            "content_type": str(document.get("content_type") or "")[:120],
            "extractor": str(document.get("extractor") or "")[:120],
            "fetched_at": str(document.get("fetched_at") or "")[:100],
            "content_hash": str(document.get("content_hash") or "")[:100],
            "text_length": max(0, int(document.get("text_length") or 0)),
            "warnings": [str(value)[:300] for value in document.get("warnings") or []][:8],
            "key_points": [
                {
                    "text": str(point.get("text") or "")[:500],
                    "section": str(point.get("section") or "")[:200],
                    "paragraph": max(0, int(point.get("paragraph") or 0)),
                }
                for point in document.get("key_points") or []
                if isinstance(point, dict)
            ][:6],
        } if document else {},
        "relevance": candidate.get("relevance"),
        "sensitivity": deepcopy(candidate.get("sensitivity") or {}),
        "accepted_for_generation": bool(candidate.get("accepted_for_generation")),
    }


def load_research_state(course: dict[str, Any] | None) -> dict[str, Any]:
    raw = (course or {}).get(WEB_RESEARCH_METADATA_KEY)
    if not isinstance(raw, dict):
        return {"schema_version": WEB_RESEARCH_SCHEMA, "sessions": []}
    sessions = [
        deepcopy(item)
        for item in raw.get("sessions") or []
        if isinstance(item, dict) and str(item.get("session_id") or "").strip()
    ]
    return {
        "schema_version": WEB_RESEARCH_SCHEMA,
        "sessions": sessions[-MAX_RESEARCH_SESSIONS:],
    }


def upsert_research_session(
    course: dict[str, Any] | None,
    session: dict[str, Any],
) -> dict[str, Any]:
    state = load_research_state(course)
    session_id = str(session.get("session_id") or "").strip()
    sessions = [
        item for item in state["sessions"]
        if str(item.get("session_id") or "") != session_id
    ]
    sessions.append(deepcopy(session))
    state["sessions"] = sessions[-MAX_RESEARCH_SESSIONS:]
    return state


def research_session(
    course: dict[str, Any] | None,
    session_id: str,
) -> dict[str, Any] | None:
    target = str(session_id or "").strip()
    for item in reversed(load_research_state(course)["sessions"]):
        if str(item.get("session_id") or "") == target:
            return deepcopy(item)
    return None


def scoped_research_projection(
    course: dict[str, Any] | None,
    *,
    stage: Any,
    lesson_id: Any = "",
) -> dict[str, Any]:
    normalized_stage, normalized_lesson_id = normalize_scope(stage, lesson_id)
    sessions = [
        item
        for item in load_research_state(course)["sessions"]
        if str(item.get("stage") or "foundation") == normalized_stage
        and str(item.get("lesson_id") or "") == normalized_lesson_id
    ]
    accepted: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for session in sessions:
        for item in session.get("accepted_references") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("asset_id") or item.get("material_asset_id") or "")
            if not key or key in seen_assets:
                continue
            seen_assets.add(key)
            accepted.append(deepcopy(item))
    return {
        "schema_version": WEB_RESEARCH_SCHEMA,
        "stage": normalized_stage,
        "lesson_id": normalized_lesson_id,
        "latest_session": deepcopy(sessions[-1]) if sessions else None,
        "accepted_references": accepted,
        "session_count": len(sessions),
    }


__all__ = [
    "MAX_RESULTS_PER_SESSION",
    "WEB_RESEARCH_METADATA_KEY",
    "load_research_state",
    "normalize_candidate",
    "normalize_scope",
    "research_session",
    "scoped_research_projection",
    "upsert_research_session",
]
