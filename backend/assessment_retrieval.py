"""Pre-generation retrieval of question exemplars.

References are converted into compact pattern records before they reach the
generator.  The package never contains learner data and web text is treated as
untrusted reference-only material.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Awaitable, Callable

from assessment_blueprint import REFERENCE_PACKAGE_SCHEMA
from course_versioning import stable_hash
from question_search import ExaQuestionSearch, sanitize_web_reference


MAX_REFERENCE_EXCERPT = 1200
MAX_REFERENCE_PATTERNS = 24
MAX_WEB_QUERIES = 12

SearchCallable = Callable[..., Awaitable[list[dict[str, Any]]]]


def compile_local_reference_package(
    course_data: dict[str, Any],
    *,
    objectives: list[dict[str, Any]],
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    evidence = [
        deepcopy(item)
        for item in (
            course_data.get("evidence_catalog")
            or course_data.get("_question_evidence_catalog")
            or []
        )
        if (
            item.get("kind") == "question"
            or item.get("purpose") == "question_source"
        )
    ]
    references: list[dict[str, Any]] = []
    for source in evidence[:MAX_REFERENCE_PATTERNS]:
        text = _source_text(source)
        if not text:
            continue
        objective = _best_objective(text, objectives)
        references.append(
            _reference_record(
                text=text,
                source_type="teacher_question_bank",
                objective=objective,
                source_record=source,
                rights_basis=str(
                    source.get("rights_basis")
                    or "teacher_asserted"
                ),
                reuse_policy=str(
                    source.get("reuse_policy")
                    or "reference_only"
                ),
            )
        )
    package = {
        "schema_version": REFERENCE_PACKAGE_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "blueprint_revision_id": blueprint.get(
            "blueprint_revision_id"
        ),
        "source_priority": [
            "teacher_question_bank",
            "course_materials",
            "trusted_web_reference",
            "general_model_knowledge",
        ],
        "retrieval_mode": _retrieval_mode(course_data),
        "retrieval_requests": [
            {
                "objective_id": node.get("objective_id"),
                "node_id": node.get("node_id"),
                "question_types": [
                    slot.get("question_type")
                    for slot in node.get("slots") or []
                ],
                "input_modes": [
                    slot.get("input_mode")
                    for slot in node.get("slots") or []
                ],
            }
            for node in blueprint.get("nodes") or []
        ],
        "references": references,
        "objective_coverage": _objective_coverage(
            objectives,
            references,
        ),
        "web": {
            "status": "not_started",
            "query_count": 0,
            "source_count": 0,
        },
    }
    package["package_revision_id"] = stable_hash(
        package,
        prefix="qrp_",
    )
    return package


async def enrich_reference_package_with_web(
    course_data: dict[str, Any],
    package: dict[str, Any],
    *,
    objectives: list[dict[str, Any]],
    search: SearchCallable | None = None,
) -> dict[str, Any]:
    """Fill uncovered objective references before question generation."""
    result = deepcopy(package)
    mode = str(result.get("retrieval_mode") or "auto_on_gap")
    if mode == "off":
        result["web"] = {
            "status": "disabled",
            "query_count": 0,
            "source_count": 0,
        }
        return _finalize(result, objectives)
    gaps = [
        item
        for item in result.get("objective_coverage") or []
        if not item.get("covered")
    ]
    if mode != "always" and not gaps:
        result["web"] = {
            "status": "not_needed",
            "query_count": 0,
            "source_count": 0,
        }
        return _finalize(result, objectives)

    provider = ExaQuestionSearch()
    if search is None and not provider.configured:
        result["web"] = {
            "status": "unavailable_fallback_local",
            "query_count": 0,
            "source_count": 0,
            "error_code": "exa_not_configured",
        }
        return _finalize(result, objectives)
    search_fn = search or provider.search
    targets = (
        objectives
        if mode == "always"
        else [
            objective
            for objective in objectives
            if any(
                gap.get("objective_id") == objective.get("objective_id")
                for gap in gaps
            )
        ]
    )
    queries = _build_queries(
        course_data,
        targets,
        package=result,
    )[:MAX_WEB_QUERIES]
    seen_urls: set[str] = set()
    errors = 0
    source_count = 0
    for query, objective in queries:
        if len(result.get("references") or []) >= MAX_REFERENCE_PATTERNS:
            break
        try:
            raw_results = await search_fn(query, num_results=2)
        except Exception:
            errors += 1
            continue
        for raw in raw_results or []:
            sanitized = sanitize_web_reference(raw)
            url = str(sanitized.get("url") or "")
            text = str(sanitized.get("reference_text") or "")
            if not url or not text or url in seen_urls:
                continue
            seen_urls.add(url)
            result.setdefault("references", []).append(
                _reference_record(
                    text=text,
                    source_type="trusted_web_reference",
                    objective=objective,
                    source_record=sanitized,
                    rights_basis=(
                        "open_license"
                        if sanitized.get("open_license")
                        else "license_unknown"
                    ),
                    reuse_policy="reference_only",
                )
            )
            source_count += 1
            if len(result["references"]) >= MAX_REFERENCE_PATTERNS:
                break
    result["web"] = {
        "status": (
            "completed"
            if source_count
            else ("failed_fallback_local" if errors else "no_sources")
        ),
        "query_count": len(queries),
        "source_count": source_count,
        "error_count": errors,
    }
    return _finalize(result, objectives)


def references_for_objective(
    package: dict[str, Any],
    objective_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    matched = [
        deepcopy(item)
        for item in package.get("references") or []
        if str(item.get("objective_id") or "") == str(objective_id)
    ]
    priority = {
        "teacher_question_bank": 0,
        "course_materials": 1,
        "trusted_web_reference": 2,
        "general_model_knowledge": 3,
    }
    matched.sort(
        key=lambda item: priority.get(
            str(item.get("source_type") or ""),
            9,
        )
    )
    return matched[: max(0, limit)]


def _finalize(
    package: dict[str, Any],
    objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(package)
    result["objective_coverage"] = _objective_coverage(
        objectives,
        result.get("references") or [],
    )
    result.pop("package_revision_id", None)
    result["package_revision_id"] = stable_hash(
        result,
        prefix="qrp_",
    )
    return result


def _retrieval_mode(course_data: dict[str, Any]) -> str:
    config = (
        (course_data.get("generation_request") or {}).get(
            "web_question_enrichment"
        )
        or course_data.get("web_question_enrichment")
        or {}
    )
    mode = str(config.get("mode") or "").strip()
    if mode in {"auto_on_gap", "off", "always"}:
        return mode
    if config.get("enabled") is True:
        return "auto_on_gap"
    if config.get("enabled") is False:
        return "off"
    # The v2 product default is automatic gap filling.  Teachers can opt out
    # explicitly with mode=off.
    return "auto_on_gap"


def _objective_coverage(
    objectives: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "objective_id": objective.get("objective_id"),
            "node_id": objective.get("node_id"),
            "covered": any(
                reference.get("objective_id")
                == objective.get("objective_id")
                for reference in references
            ),
            "reference_count": sum(
                reference.get("objective_id")
                == objective.get("objective_id")
                for reference in references
            ),
        }
        for objective in objectives
    ]


def _reference_record(
    *,
    text: str,
    source_type: str,
    objective: dict[str, Any] | None,
    source_record: dict[str, Any],
    rights_basis: str,
    reuse_policy: str,
) -> dict[str, Any]:
    excerpt = " ".join(text.split())[:MAX_REFERENCE_EXCERPT]
    pattern = _extract_pattern(excerpt)
    public_source = {
        key: deepcopy(source_record.get(key))
        for key in (
            "evidence_id",
            "asset_id",
            "title",
            "url",
            "content_hash",
            "license",
            "published_date",
        )
        if source_record.get(key) is not None
    }
    record = {
        "reference_id": stable_hash(
            {
                "source_type": source_type,
                "source": public_source,
                "excerpt": excerpt,
            },
            prefix="qref_",
        ),
        "objective_id": (
            (objective or {}).get("objective_id")
        ),
        "node_id": (objective or {}).get("node_id"),
        "source_type": source_type,
        "source_record": public_source,
        "rights_basis": rights_basis,
        "reuse_policy": reuse_policy,
        "pattern": pattern,
        "reference_excerpt": excerpt,
        "untrusted_source_isolated": source_type
        == "trusted_web_reference",
    }
    return record


def _extract_pattern(text: str) -> dict[str, Any]:
    lowered = text.lower()
    return {
        "stimulus_shape": (
            "code"
            if "```" in text or any(
                marker in lowered
                for marker in ("python", "javascript", "class ", "def ")
            )
            else (
                "data"
                if re.search(r"\d+(?:\.\d+)?", text)
                else "narrative"
            )
        ),
        "question_shape": (
            "selected_response"
            if len(re.findall(r"(?:^|\s)[A-DＡ-Ｄ][.、)]", text)) >= 2
            else "constructed_response"
        ),
        "has_constraints": any(
            marker in text
            for marker in ("要求", "限制", "必须", "不得", "至少")
        ),
        "has_scoring": any(
            marker in text
            for marker in ("分", "评分", "得分", "rubric")
        ),
        "estimated_complexity": (
            "high"
            if len(text) > 800
            else ("medium" if len(text) > 300 else "low")
        ),
    }


def _best_objective(
    text: str,
    objectives: list[dict[str, Any]],
) -> dict[str, Any] | None:
    tokens = set(_tokens(text))
    scored = [
        (
            len(
                tokens.intersection(
                    _tokens(
                        " ".join([
                            str(objective.get("objective") or ""),
                            *[
                                str(value)
                                for value in objective.get("knowledge") or []
                            ],
                        ])
                    )
                )
            ),
            objective,
        )
        for objective in objectives
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] else None


def _build_queries(
    course_data: dict[str, Any],
    objectives: list[dict[str, Any]],
    *,
    package: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    course_name = _safe_term(
        str(
            course_data.get("course_name")
            or course_data.get("subject")
            or "课程"
        )
    )
    result: list[tuple[str, dict[str, Any]]] = []
    for objective in objectives:
        knowledge = " ".join(
            _safe_term(str(value))
            for value in (objective.get("knowledge") or [])[:4]
        )
        target = _safe_term(str(objective.get("objective") or ""))
        difficulty = _safe_term(
            str(
                (
                    objective.get("difficulty_contract")
                    or {}
                ).get("target_level")
                or course_data.get("difficulty")
                or "intermediate"
            )
        )
        request = next(
            (
                item
                for item in package.get(
                    "retrieval_requests"
                )
                or []
                if item.get("objective_id")
                == objective.get("objective_id")
            ),
            {},
        )
        question_types = " ".join(
            _safe_term(str(value))
            for value in request.get("question_types") or []
        )
        result.append((
            " ".join(
                value
                for value in (
                    course_name,
                    knowledge,
                    target,
                    difficulty,
                    question_types,
                    "assessment example open education",
                )
                if value
            )[:1000],
            objective,
        ))
    return result


def _source_text(source: dict[str, Any]) -> str:
    for key in (
        "source_text",
        "reference_text",
        "content",
        "text",
        "raw_text",
    ):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def _safe_term(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^\w\u3400-\u9fff .,+\-]", " ", value),
    ).strip()[:300]


def _tokens(value: str) -> list[str]:
    english = re.findall(r"[a-z][a-z0-9_+#-]{1,30}", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,12}", value)
    grams = [
        group[index:index + width]
        for group in chinese
        for width in (2, 3, 4)
        for index in range(max(0, len(group) - width + 1))
    ]
    return list(dict.fromkeys([*english, *chinese, *grams]))


__all__ = [
    "MAX_REFERENCE_PATTERNS",
    "compile_local_reference_package",
    "enrich_reference_package_with_web",
    "references_for_objective",
]
