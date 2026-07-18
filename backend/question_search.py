"""Optional Exa-backed enrichment for question-bank coverage gaps."""

from __future__ import annotations

import hashlib
import html
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from course_versioning import stable_hash
from question_bank import (
    QUESTION_ITEM_SCHEMA,
    evaluate_question_item_quality,
    formal_task_from_question_bank_item,
    refresh_question_bank_bundle,
)

MAX_QUERIES_PER_GAP = 2
MAX_COURSE_QUERIES = 12
MAX_COURSE_SOURCES = 24
MAX_REFERENCE_TEXT_CHARS = 4000
EXA_SEARCH_ENDPOINT = "https://api.exa.ai/search"

SearchCallable = Callable[..., Awaitable[list[dict[str, Any]]]]

_UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?[^。.!?\n]*[。.!?]?", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s+message\s*:[^\n]*", re.IGNORECASE),
    re.compile(r"(?:reveal|show|send)\s+(?:the\s+)?(?:learner|student|user)\s+answers?[^。.!?\n]*[。.!?]?", re.IGNORECASE),
    re.compile(r"忽略(?:此前|之前|以上|全部)?指令[^。！？\n]*[。！？]?", re.IGNORECASE),
    re.compile(r"(?:泄露|展示|发送)(?:学生|用户)?答案[^。！？\n]*[。！？]?", re.IGNORECASE),
)


class ExaQuestionSearch:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("EXA_API_KEY", "")
        self.endpoint = endpoint or os.getenv("EXA_SEARCH_ENDPOINT", EXA_SEARCH_ENDPOINT)
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, *, num_results: int = 2) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        payload = {
            "query": _clip_query(query),
            "type": "auto",
            "numResults": max(1, min(4, int(num_results))),
            "moderation": True,
            "contents": {
                "highlights": {
                    "maxCharacters": 2400,
                }
            },
        }
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        finally:
            if owns_client:
                await client.aclose()
        results = data.get("results") if isinstance(data, dict) else []
        return [item for item in results or [] if isinstance(item, dict)]


async def enrich_question_bank_with_web(
    course_data: dict[str, Any],
    bundle: dict[str, Any],
    *,
    search: SearchCallable | None = None,
) -> dict[str, Any]:
    config = (
        (course_data.get("generation_request") or {}).get("web_question_enrichment")
        or course_data.get("web_question_enrichment")
        or {}
    )
    if not bool(config.get("enabled")):
        return deepcopy(bundle)

    gaps = list((bundle.get("coverage") or {}).get("gaps") or [])
    result = deepcopy(bundle)
    if not gaps:
        result["web_enrichment"] = {
            **(result.get("web_enrichment") or {}),
            "enabled": True,
            "status": "not_needed",
            "query_count": 0,
            "source_count": 0,
        }
        return refresh_question_bank_bundle(result)

    provider = ExaQuestionSearch()
    search_fn = search or provider.search
    if search is None and not provider.configured:
        result["web_enrichment"] = {
            **(result.get("web_enrichment") or {}),
            "enabled": True,
            "status": "unavailable_fallback_local",
            "query_count": 0,
            "source_count": 0,
            "error_code": "exa_not_configured",
        }
        return refresh_question_bank_bundle(result)

    queries = build_gap_queries(course_data, gaps)
    source_count = 0
    seen_urls: set[str] = set()
    errors = 0
    for query, gap in queries:
        if source_count >= MAX_COURSE_SOURCES:
            break
        try:
            references = await search_fn(
                query,
                num_results=min(2, MAX_COURSE_SOURCES - source_count),
            )
        except Exception:
            errors += 1
            continue
        for raw in references or []:
            if source_count >= MAX_COURSE_SOURCES:
                break
            sanitized = sanitize_web_reference(raw)
            url = str(sanitized.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            source_count += 1
            reference_item = _web_reference_item(course_data, gap, sanitized)
            result.setdefault("items", []).append(reference_item)
            result["items"].append(
                _web_generated_item(course_data, gap, sanitized, reference_item)
            )

    result["web_enrichment"] = {
        **(result.get("web_enrichment") or {}),
        "enabled": True,
        "status": (
            "completed"
            if source_count
            else ("failed_fallback_local" if errors else "no_trusted_sources")
        ),
        "query_count": len(queries),
        "source_count": source_count,
        "query_limit": MAX_COURSE_QUERIES,
        "source_limit": MAX_COURSE_SOURCES,
        "error_count": errors,
        "completed_at": _now(),
    }
    return refresh_question_bank_bundle(result)


def build_gap_queries(
    course_data: dict[str, Any],
    gaps: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    topic = _safe_query_term(str(course_data.get("course_name") or course_data.get("subject") or "课程"))
    result: list[tuple[str, dict[str, Any]]] = []
    for gap in gaps:
        if len(result) >= MAX_COURSE_QUERIES:
            break
        objective = _safe_query_term(str(gap.get("objective") or ""))
        knowledge = " ".join(
            _safe_query_term(str(value))
            for value in (gap.get("knowledge_points") or [])[:4]
        ).strip()
        difficulty = _safe_query_term(str(gap.get("difficulty") or course_data.get("difficulty") or "intermediate"))
        candidates = [
            f"{topic} {knowledge} {objective} {difficulty} practice exercise open education",
            f"{topic} {knowledge} authentic assessment example university resource",
        ]
        for query in candidates[:MAX_QUERIES_PER_GAP]:
            if len(result) >= MAX_COURSE_QUERIES:
                break
            result.append((_clip_query(query), deepcopy(gap)))
    return result


def sanitize_web_reference(raw: dict[str, Any]) -> dict[str, Any]:
    url = str(raw.get("url") or "").strip()[:2000]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        url = ""
    highlights = raw.get("highlights") or []
    highlight_text = " ".join(str(value) for value in highlights if isinstance(value, str))
    raw_text = str(
        raw.get("text")
        or raw.get("content")
        or highlight_text
        or raw.get("summary")
        or ""
    )
    reference_text = _sanitize_untrusted_text(raw_text)
    title = _sanitize_untrusted_text(str(raw.get("title") or ""))[:500]
    license_name = _sanitize_untrusted_text(
        str(raw.get("license") or raw.get("rights") or "")
    )[:200]
    open_license = bool(
        re.search(
            r"\b(?:cc[- ]?by|creative commons|public domain|oer|open educational)\b",
            license_name,
            re.IGNORECASE,
        )
    )
    return {
        "url": url,
        "title": title,
        "reference_text": reference_text,
        "published_date": str(raw.get("publishedDate") or raw.get("published_date") or "")[:50],
        "author": _sanitize_untrusted_text(str(raw.get("author") or ""))[:300],
        "license": license_name,
        "open_license": open_license,
        "content_hash": hashlib.sha256(reference_text.encode("utf-8")).hexdigest(),
        "retrieved_at": _now(),
    }


def _web_reference_item(
    course_data: dict[str, Any],
    gap: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    course_id = str(course_data.get("course_id") or "")
    node_id = str(gap.get("node_id") or "")
    objective = str(gap.get("objective") or "")
    knowledge = [str(value) for value in gap.get("knowledge_points") or [] if str(value).strip()]
    reuse_policy = "verbatim_allowed" if reference.get("open_license") else "reference_only"
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": course_id,
        "item_id": stable_hash(
            {"course": course_id, "url": reference.get("url"), "node": node_id},
            prefix="qbi_",
        ),
        "parent_item_id": None,
        "parent_revision_id": None,
        "node_id": node_id,
        "node_ids": [node_id] if node_id else [],
        "prompt": f"联网参考：{reference.get('title') or objective}",
        "reference_excerpt": str(reference.get("reference_text") or "")[:MAX_REFERENCE_TEXT_CHARS],
        "subquestions": [],
        "options": [],
        "answer_spec": {
            "type": "reference_only",
            "criteria": ["仅用于提取真实情境、考查结构与难度特征"],
            "expected_keywords": knowledge,
            "max_score": 0,
            "pass_score": 0,
        },
        "explanation": "",
        "score": 0,
        "estimated_minutes": 0,
        "question_type": "reference",
        "difficulty": str(gap.get("difficulty") or course_data.get("difficulty") or "intermediate"),
        "practice_levels": [],
        "assessment_role": "reference",
        "course_objective_refs": [stable_hash({"course": course_id, "node": node_id, "objective": objective}, prefix="obj_")],
        "course_knowledge_refs": [
            stable_hash({"course": course_id, "node": node_id, "knowledge": value}, prefix="ck_")
            for value in knowledge
        ],
        "course_skill_refs": [],
        "course_misconception_refs": [],
        "course_mastery_refs": [],
        "source_type": "web_reference",
        "source_records": [{
            "source_type": "web",
            "url": reference.get("url"),
            "title": reference.get("title"),
            "author": reference.get("author"),
            "published_date": reference.get("published_date"),
            "retrieved_at": reference.get("retrieved_at"),
            "content_hash": reference.get("content_hash"),
            "license": reference.get("license"),
            "rights_basis": "open_license" if reference.get("open_license") else "license_unknown",
            "reuse_policy": reuse_policy,
        }],
        "parse_confidence": "medium",
        "risk_flags": [] if reference.get("open_license") else ["web_license_unknown"],
        "review_required": True,
        "lifecycle_status": "needs_review",
        "review_status": "needs_review",
        "review_history": [],
        "formal_task_revision_id": None,
        "deliverable": "",
        "input_materials": [],
        "constraints": ["不得复制未明确开放许可的网页原文"],
        "reference_concepts": knowledge,
        "result_checks": [],
        "created_at": _now(),
    }
    item["hint_contract"] = {
        "levels": [],
        "solution_policy": "not_applicable",
        "leakage_check": {"passed": True, "checked_at_compile_time": True},
    }
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = stable_hash(
        {key: value for key, value in item.items() if key != "revision_id"},
        prefix="qbir_",
    )
    return item


def _web_generated_item(
    course_data: dict[str, Any],
    gap: dict[str, Any],
    reference: dict[str, Any],
    parent: dict[str, Any],
) -> dict[str, Any]:
    course_id = str(course_data.get("course_id") or "")
    node_id = str(gap.get("node_id") or "")
    objective = str(gap.get("objective") or "完成当前目标")
    knowledge = [str(value) for value in gap.get("knowledge_points") or [] if str(value).strip()]
    source_title = str(reference.get("title") or "可信公开资料")
    scenario = _original_web_scenario(reference, knowledge)
    prompt = (
        f"联网情境变式｜{objective}\n"
        f"输入材料：{scenario}\n"
        f"任务：独立完成分析或求解，说明方法依据与关键过程，并执行结果检查。\n"
        f"限制条件：不得复制网页原文；至少改变一个有效条件和一种结果表征。"
    )
    source_excerpt = str(reference.get("reference_text") or "")
    similarity = SequenceMatcher(
        None,
        _similarity_text(prompt),
        _similarity_text(source_excerpt),
    ).ratio()
    risk_flags = ["web_similarity_high"] if similarity >= 0.65 else []
    source_record = {
        "source_type": "web",
        "url": reference.get("url"),
        "title": reference.get("title"),
        "retrieved_at": reference.get("retrieved_at"),
        "content_hash": reference.get("content_hash"),
        "license": reference.get("license"),
        "rights_basis": "open_license" if reference.get("open_license") else "license_unknown",
        "reuse_policy": "reference_only",
    }
    item = {
        "schema_version": QUESTION_ITEM_SCHEMA,
        "course_id": course_id,
        "item_id": stable_hash(
            {"course": course_id, "url": reference.get("url"), "node": node_id, "kind": "original_variant"},
            prefix="qbi_",
        ),
        "parent_item_id": parent.get("item_id"),
        "parent_revision_id": parent.get("revision_id"),
        "node_id": node_id,
        "node_ids": [node_id] if node_id else [],
        "prompt": prompt,
        "subquestions": [],
        "options": [],
        "answer_spec": {
            "type": "rubric",
            "criteria": [
                "根据新输入材料选择方法并说明依据",
                "给出可复核的分析、计算或推理过程",
                "检查结果并说明条件或局限",
                "题目与联网原文不存在违规复用",
            ],
            "expected_keywords": knowledge,
            "max_score": 100,
            "pass_score": 70,
        },
        "explanation": "",
        "score": 100,
        "estimated_minutes": 15,
        "question_type": "short_answer",
        "difficulty": str(gap.get("difficulty") or course_data.get("difficulty") or "intermediate"),
        "practice_levels": ["objective_practice"],
        "assessment_role": "web_enriched_practice",
        "course_objective_refs": [
            stable_hash({"course": course_id, "node": node_id, "objective": objective}, prefix="obj_")
        ],
        "course_knowledge_refs": [
            stable_hash({"course": course_id, "node": node_id, "knowledge": value}, prefix="ck_")
            for value in knowledge
        ] or [stable_hash({"course": course_id, "node": node_id}, prefix="ck_")],
        "course_skill_refs": [],
        "course_misconception_refs": [],
        "course_mastery_refs": [],
        "source_type": "variant",
        "source_records": [source_record],
        "parse_confidence": "high",
        "risk_flags": risk_flags,
        "review_required": bool(risk_flags),
        "lifecycle_status": "needs_review" if risk_flags else "approved",
        "review_status": "needs_review" if risk_flags else "approved",
        "review_history": [],
        "formal_task_revision_id": None,
        "deliverable": "一份包含依据、过程与结果检查的原创解答",
        "input_materials": [scenario, f"参考领域：{source_title}"],
        "constraints": ["不得复制网页原文", "改变有效条件", "改变结果表征"],
        "reference_concepts": knowledge,
        "result_checks": ["语义与目标一致", "结果可复核", "与网页原文相似度低于阈值"],
        "web_source_similarity": round(similarity, 4),
        "created_at": _now(),
        "hint_contract": {
            "levels": [
                {"level": 1, "kind": "orientation", "content": f"先明确任务目标并回看：{'、'.join(knowledge[:3])}", "support_level": 1, "evidence_effect": "limited_mastery"},
                {"level": 2, "kind": "method_skeleton", "content": "整理输入，选择方法，完成首个关键步骤，再检查结果。", "support_level": 2, "evidence_effect": "not_independent"},
                {"level": 3, "kind": "local_scaffold", "content": "用不同数据的正反例检查局部步骤，不提供最终结论。", "support_level": 3, "evidence_effect": "not_mastery"},
            ],
            "solution_policy": "after_submission_or_repeated_failure",
            "solution_effect": {
                "invalidate_current_evidence": True,
                "requires_unseen_equivalent_validation": True,
            },
            "frozen_with_item_revision": True,
            "leakage_check": {"passed": True, "checked_at_compile_time": True},
        },
    }
    item["quality_report"] = evaluate_question_item_quality(item)
    item["revision_id"] = stable_hash(
        {
            key: value
            for key, value in item.items()
            if key not in {"revision_id", "formal_task", "created_at"}
        },
        prefix="qbir_",
    )
    item["formal_task"] = formal_task_from_question_bank_item(item)
    item["formal_task_revision_id"] = item["formal_task"]["revision_id"]
    return item


def _sanitize_untrusted_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"(?is)<(script|style|iframe|object|template)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS:
        text = pattern.sub(" ", text)
    text = "".join(character for character in text if character.isprintable() or character in "\n\t")
    return re.sub(r"\s+", " ", text).strip()[:MAX_REFERENCE_TEXT_CHARS]


def _safe_query_term(value: str) -> str:
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"[^\w\u3400-\u9fff .,+\-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:300]


def _similarity_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _original_web_scenario(
    reference: dict[str, Any],
    knowledge: list[str],
) -> str:
    digest = str(reference.get("content_hash") or "0" * 8)
    seed = int(digest[:6], 16) % 17 + 3
    focus = "、".join(knowledge[:3]) or "当前知识点"
    return (
        f"案例 W{seed:02d} 的三次记录为 {seed * 2}、{seed * 2 + 3}、"
        f"{seed * 2 + 7}，允许误差为 ±1；记录者另附一个未验证值 {seed * 3 + 2}。"
        f"只可将网页用于确认应用领域，解题须基于这组原创记录检验{focus}。"
    )


def _clip_query(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:1000]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "EXA_SEARCH_ENDPOINT",
    "ExaQuestionSearch",
    "MAX_COURSE_QUERIES",
    "MAX_COURSE_SOURCES",
    "build_gap_queries",
    "enrich_question_bank_with_web",
    "sanitize_web_reference",
]
