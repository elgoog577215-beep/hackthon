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
    authoring_patterns: list[dict[str, Any]] = []
    for source in evidence[:MAX_REFERENCE_PATTERNS]:
        text = _source_text(source)
        if not text:
            continue
        objective = _best_objective(text, objectives)
        authoring_patterns.append(
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
    content_evidence: list[dict[str, Any]] = []
    for objective in objectives:
        source_text = str(objective.get("source_excerpt") or "").strip()
        if not source_text:
            continue
        content_evidence.append(
            _reference_record(
                text=source_text,
                source_type="course_materials",
                objective=objective,
                source_record={
                    "asset_id": next(
                        iter(objective.get("source_refs") or []),
                        None,
                    ),
                    "title": "course objective source",
                },
                rights_basis="course_owned",
                reuse_policy="reference_only",
                evidence_role="content_evidence",
            )
        )
    content_coverage = _objective_coverage(
        objectives,
        content_evidence,
    )
    method_coverage = _method_coverage(
        blueprint,
        authoring_patterns,
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
            "builtin_subject_template",
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
        "content_evidence": content_evidence,
        "authoring_patterns": authoring_patterns,
        # Compatibility alias consumed by older generators and summaries.
        "references": deepcopy(authoring_patterns),
        "content_coverage": content_coverage,
        "method_coverage": method_coverage,
        "objective_coverage": _combined_coverage(
            content_coverage,
            method_coverage,
        ),
        "web": {
            "status": "not_started",
            "query_count": 0,
            "source_count": 0,
        },
    }
    if package["retrieval_mode"] == "off":
        package["web"] = {
            "status": "disabled",
            "query_count": 0,
            "source_count": 0,
        }
        return _finalize(package, objectives)
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
    gaps = _coverage_gaps(result)
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
        if len(result.get("authoring_patterns") or []) >= MAX_REFERENCE_PATTERNS:
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
            reference = _reference_record(
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
                evidence_role="authoring_pattern",
            )
            result.setdefault("authoring_patterns", []).append(
                deepcopy(reference)
            )
            result.setdefault("content_evidence", []).append({
                **deepcopy(reference),
                "evidence_role": "content_evidence",
            })
            source_count += 1
            if len(result["authoring_patterns"]) >= MAX_REFERENCE_PATTERNS:
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
        for item in (
            package.get("authoring_patterns")
            or package.get("references")
            or []
        )
        if str(item.get("objective_id") or "") == str(objective_id)
    ]
    priority = {
        "teacher_question_bank": 0,
        "course_materials": 1,
        "trusted_web_reference": 2,
        "builtin_subject_template": 3,
        "general_model_knowledge": 4,
    }
    matched.sort(
        key=lambda item: priority.get(
            str(item.get("source_type") or ""),
            9,
        )
    )
    return matched[: max(0, limit)]


def content_evidence_for_objective(
    package: dict[str, Any],
    objective_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    matched = [
        deepcopy(item)
        for item in package.get("content_evidence") or []
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


def reference_summary_for_slot(
    package: dict[str, Any],
    *,
    objective_id: str,
    question_type: str,
) -> dict[str, Any]:
    content_coverage = next(
        (
            item
            for item in package.get("content_coverage") or []
            if str(item.get("objective_id") or "")
            == str(objective_id)
        ),
        {},
    )
    method_coverage = next(
        (
            item
            for item in package.get("method_coverage") or []
            if (
                str(item.get("objective_id") or "")
                == str(objective_id)
                and str(item.get("question_type") or "")
                == str(question_type)
            )
        ),
        {},
    )
    content = content_evidence_for_objective(
        package,
        objective_id,
        limit=3,
    )
    patterns = references_for_objective(
        package,
        objective_id,
        limit=5,
    )
    return {
        "content_covered": bool(content_coverage.get("covered")),
        "method_covered": bool(method_coverage.get("covered")),
        "content_reference_count": int(
            content_coverage.get("reference_count") or len(content)
        ),
        "authoring_pattern_count": int(
            method_coverage.get("reference_count") or len(patterns)
        ),
        "content_fact_basis": [
            str(item.get("reference_excerpt") or "")[:300]
            for item in content[:3]
        ],
        "source_priority": deepcopy(
            package.get("source_priority") or []
        ),
    }


def _finalize(
    package: dict[str, Any],
    objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(package)
    result.setdefault(
        "authoring_patterns",
        deepcopy(result.get("references") or []),
    )
    _add_builtin_authoring_fallbacks(result, objectives)
    result["references"] = deepcopy(
        result.get("authoring_patterns") or []
    )
    result["content_coverage"] = _objective_coverage(
        objectives,
        result.get("content_evidence") or [],
    )
    result["method_coverage"] = _method_coverage_from_requests(
        result.get("retrieval_requests") or [],
        result.get("authoring_patterns") or [],
    )
    result["objective_coverage"] = _combined_coverage(
        result["content_coverage"],
        result["method_coverage"],
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


def _method_coverage(
    blueprint: dict[str, Any],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requests = [
        {
            "objective_id": node.get("objective_id"),
            "node_id": node.get("node_id"),
            "question_types": [
                slot.get("question_type")
                for slot in node.get("slots") or []
            ],
        }
        for node in blueprint.get("nodes") or []
    ]
    return _method_coverage_from_requests(requests, references)


def _method_coverage_from_requests(
    requests: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for request in requests:
        objective_id = request.get("objective_id")
        objective_references = [
            reference
            for reference in references
            if reference.get("objective_id") == objective_id
        ]
        for question_type in request.get("question_types") or []:
            matched = [
                reference
                for reference in objective_references
                if _pattern_matches_question_type(
                    reference.get("pattern") or {},
                    str(question_type or ""),
                )
            ]
            result.append({
                "objective_id": objective_id,
                "node_id": request.get("node_id"),
                "question_type": question_type,
                "covered": bool(matched),
                "reference_count": len(matched),
            })
    return result


def _combined_coverage(
    content_coverage: list[dict[str, Any]],
    method_coverage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for content in content_coverage:
        objective_id = content.get("objective_id")
        methods = [
            item
            for item in method_coverage
            if item.get("objective_id") == objective_id
        ]
        result.append({
            "objective_id": objective_id,
            "node_id": content.get("node_id"),
            "covered": bool(
                content.get("covered")
                and methods
                and all(item.get("covered") for item in methods)
            ),
            "content_covered": bool(content.get("covered")),
            "method_covered": bool(
                methods and all(item.get("covered") for item in methods)
            ),
            "content_reference_count": int(
                content.get("reference_count") or 0
            ),
            "authoring_pattern_count": sum(
                int(item.get("reference_count") or 0)
                for item in methods
            ),
        })
    return result


def _coverage_gaps(
    package: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps = [
        {
            **deepcopy(item),
            "coverage_kind": "content",
        }
        for item in package.get("content_coverage") or []
        if not item.get("covered")
    ]
    gaps.extend([
        {
            **deepcopy(item),
            "coverage_kind": "method",
        }
        for item in package.get("method_coverage") or []
        if not item.get("covered")
    ])
    return gaps


def _add_builtin_authoring_fallbacks(
    package: dict[str, Any],
    objectives: list[dict[str, Any]],
) -> None:
    patterns = package.setdefault("authoring_patterns", [])
    requests = package.get("retrieval_requests") or []
    existing = {
        (
            str(item.get("objective_id") or ""),
            str((item.get("pattern") or {}).get("question_type") or ""),
        )
        for item in patterns
    }
    objective_lookup = {
        str(item.get("objective_id") or ""): item
        for item in objectives
    }
    for request in requests:
        objective_id = str(request.get("objective_id") or "")
        objective = objective_lookup.get(objective_id)
        for question_type in request.get("question_types") or []:
            key = (objective_id, str(question_type or ""))
            if key in existing:
                continue
            template_text = (
                f"Built-in authoring template for {question_type}: "
                "lock the answer fact and validator first; select only "
                "material used by an answer step; write one observable task; "
                "derive distractors from a named misconception."
            )
            record = _reference_record(
                text=template_text,
                source_type="builtin_subject_template",
                objective=objective,
                source_record={
                    "title": f"builtin:{question_type}",
                },
                rights_basis="system_template",
                reuse_policy="structure_only",
                evidence_role="authoring_pattern",
            )
            record["pattern"]["question_type"] = question_type
            patterns.append(record)
            existing.add(key)


def _pattern_matches_question_type(
    pattern: dict[str, Any],
    question_type: str,
) -> bool:
    explicit = str(pattern.get("question_type") or "")
    if explicit:
        return explicit == question_type
    shape = str(pattern.get("question_shape") or "")
    selected_types = {
        "selected_response",
        "output_prediction",
        "source_identification",
        "language_comprehension",
        "data_judgement",
    }
    return (
        shape == "selected_response"
        if question_type in selected_types
        else shape == "constructed_response"
    )


def _reference_record(
    *,
    text: str,
    source_type: str,
    objective: dict[str, Any] | None,
    source_record: dict[str, Any],
    rights_basis: str,
    reuse_policy: str,
    evidence_role: str = "authoring_pattern",
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
        "evidence_role": evidence_role,
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
    "content_evidence_for_objective",
    "enrich_reference_package_with_web",
    "reference_summary_for_slot",
    "references_for_objective",
]
