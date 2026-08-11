"""Strict AI story and visual planning for slide-deck V6.

Story planning has no deterministic publication fallback. Visual planning may
degrade only pages that do not carry a required characteristic artifact.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_base import AIBase
from course_document import stable_hash
from course_presentation_graph import (
    CoursePresentationGraphV1,
    CoursePresentationUnitV1,
    page_artifact_kinds,
    page_teaching_intent,
    teaching_intent_for_roles,
)
from slide_deck_v6 import (
    AIBatchDiagnosticV1,
    AIProviderAttemptDiagnosticV1,
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
)
from template_layout_contract import TemplateLayoutPackContractV1

Planner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]
BatchLifecycleCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_MARKDOWN_TITLE_RE = re.compile(
    r"\*\*([^*\n]{4,72})\*\*|^#{1,6}\s+([^\n]{4,72})",
    re.MULTILINE,
)
_STORY_PAGE_CONTRACT_FIELDS = frozenset({
    "page_id",
    "teaching_unit_id",
    "template_layout_id",
    "title",
    "summary",
    "source_block_ids",
})
_STORY_SEMANTIC_MAX_ATTEMPTS = 3
_VISUAL_SEMANTIC_MAX_ATTEMPTS = 2
_VISUAL_DECISION_CONTRACT_FIELDS = frozenset({
    "page_id",
    "decision",
    "source_block_ids",
    "source_asset_ids",
    "visual_payload",
    "resolved_template_layout_id",
    "provider",
    "model",
    "duration_ms",
    "attempts",
    "degraded",
    "degradation_reason",
})


class AIPlannerInvocationError(RuntimeError):
    """Provider failure with only allow-listed, non-content telemetry attached."""

    def __init__(
        self,
        error: BaseException,
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        self.original_error = error
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]
        super().__init__(str(error) or type(error).__name__)


class _AIPlannerResponse(dict[str, Any]):
    def __init__(
        self,
        value: dict[str, Any],
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(value)
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StoryResponsePage(_StrictModel):
    page_id: str
    teaching_unit_id: str
    template_layout_id: str
    title: str
    summary: str = ""
    source_block_ids: list[str] = Field(min_length=1)


class _StoryBatchResponse(_StrictModel):
    schema_version: str
    chapter_id: str
    provider: str = ""
    model: str = ""
    attempts: int = Field(default=1, ge=1)
    pages: list[_StoryResponsePage] = Field(min_length=1)


class _VisualBatchResponse(_StrictModel):
    schema_version: str
    provider: str = ""
    model: str = ""
    attempts: int = Field(default=1, ge=1)
    decisions: list[SlideVisualDecisionV2] = Field(min_length=1)


def _normalize_versioned_response(
    raw: dict[str, Any],
    *,
    schema_version: str,
    collection_field: str,
    collection_aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Normalize explicit, lossless provider shapes before strict validation."""

    payload = dict(raw)
    wrapped = payload.get(schema_version)
    if isinstance(wrapped, dict):
        allowed_outer = {
            schema_version,
            "schema_version",
            "provider",
            "model",
            "attempts",
        }
        unknown_outer = set(payload).difference(allowed_outer)
        if unknown_outer:
            raise ValueError(
                "Unexpected fields beside versioned AI response wrapper: "
                + ", ".join(sorted(unknown_outer))
            )
        normalized = dict(wrapped)
        normalized.setdefault("schema_version", schema_version)
        for field in ("provider", "model", "attempts"):
            if field in payload and field not in normalized:
                normalized[field] = payload[field]
        payload = normalized

    for alias in collection_aliases:
        if alias not in payload:
            continue
        alias_value = payload.pop(alias)
        canonical_value = payload.get(collection_field)
        if canonical_value in (None, []):
            payload[collection_field] = alias_value
        elif canonical_value != alias_value:
            raise ValueError(
                f"Conflicting AI response fields: {collection_field} and {alias}"
            )
    return payload


def _normalize_story_batch_response(
    raw: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    payload = _normalize_versioned_response(
        raw,
        schema_version="slide_story_batch_response_v3",
        collection_field="pages",
        collection_aliases=("slides",),
    )
    units = {
        str(unit.get("teaching_unit_id") or ""): unit
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict)
    }
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return payload
    used_titles = {
        re.sub(r"\s+", "", str(title)).casefold()
        for title in request.get("constraints", {}).get("forbidden_titles") or []
        if str(title).strip()
    }
    repair_targets = [
        target
        for target in (request.get("repair_feedback") or {}).get("repair_targets") or []
        if isinstance(target, dict)
    ]
    repair_targets_by_page = {
        str(target.get("page_id") or ""): target
        for target in repair_targets
        if str(target.get("page_id") or "")
    }

    def repair_target_for(page: dict[str, Any]) -> dict[str, Any] | None:
        exact = repair_targets_by_page.get(str(page.get("page_id") or ""))
        if exact is not None:
            return exact
        unit_id = str(page.get("teaching_unit_id") or "")
        source_ids = {
            str(block_id) for block_id in page.get("source_block_ids") or []
        }
        matching = [
            target
            for target in repair_targets
            if str(target.get("teaching_unit_id") or "") == unit_id
            and {
                str(block_id)
                for block_id in target.get("current_source_block_ids") or []
            }
            == source_ids
        ]
        return matching[0] if len(matching) == 1 else None

    def allowed_layout_ids_for_page(
        unit: dict[str, Any],
        page: dict[str, Any],
    ) -> list[str]:
        block_metadata = {
            str(block.get("block_id") or ""): block
            for block in unit.get("primary_blocks") or []
            if isinstance(block, dict)
        }
        source_ids = [
            str(block_id) for block_id in page.get("source_block_ids") or []
        ]
        roles = [
            str(block_metadata.get(block_id, {}).get("role") or "")
            for block_id in source_ids
            if str(block_metadata.get(block_id, {}).get("role") or "")
        ]
        artifacts = {
            str(artifact)
            for block_id in source_ids
            for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
            if str(artifact)
        }
        page_intent = (
            teaching_intent_for_roles(roles, artifacts)
            if roles or artifacts
            else str(unit.get("teaching_intent") or "")
        )
        result: list[str] = []
        for layout in unit.get("allowed_template_layouts") or []:
            if not isinstance(layout, dict):
                continue
            layout_id = str(layout.get("template_layout_id") or "")
            if not layout_id or page_intent not in (layout.get("teaching_intents") or []):
                continue
            if artifacts and not artifacts.intersection(layout.get("artifact_kinds") or []):
                continue
            if roles and not artifacts:
                remaining_roles = list(roles)
                required_text_slots = [
                    slot
                    for slot in layout.get("slots") or []
                    if isinstance(slot, dict)
                    and bool(slot.get("required"))
                    and slot.get("slot_kind") in {"body", "items"}
                ]
                satisfiable = True
                for slot in required_text_slots:
                    source_roles = set(slot.get("source_roles") or [])
                    matching_index = next(
                        (
                            index
                            for index, role in enumerate(remaining_roles)
                            if not source_roles or role in source_roles
                        ),
                        None,
                    )
                    if matching_index is None:
                        satisfiable = False
                        break
                    remaining_roles.pop(matching_index)
                if not satisfiable:
                    continue
            result.append(layout_id)
        return result
    normalized_pages: list[Any] = []
    for ordinal, value in enumerate(pages):
        if not isinstance(value, dict):
            normalized_pages.append(value)
            continue
        page = dict(value)
        content = page.pop("content", None)
        if isinstance(content, dict):
            if not str(page.get("title") or "").strip():
                page["title"] = str(
                    content.get("title") or content.get("eyebrow") or ""
                ).strip()
            if "summary" not in page:
                summary = content.get("summary") or content.get("lead") or ""
                page["summary"] = summary if isinstance(summary, str) else ""
        unit_id = str(page.get("teaching_unit_id") or "")
        unit = units.get(unit_id)
        if unit is not None and not page.get("source_block_ids"):
            page["source_block_ids"] = list(unit.get("primary_block_ids") or [])
        if not str(page.get("page_id") or "").strip():
            page["page_id"] = stable_hash(
                {
                    "chapter_id": request.get("chapter_id"),
                    "ordinal": ordinal,
                    "teaching_unit_id": unit_id,
                    "template_layout_id": page.get("template_layout_id"),
                },
                prefix="v6page_",
            )
        if unit is not None:
            selected_layout_id = str(page.get("template_layout_id") or "")
            unit_layout_ids = set(unit.get("allowed_template_layout_ids") or [])
            page_layout_ids = allowed_layout_ids_for_page(unit, page)
            if (
                selected_layout_id in unit_layout_ids
                and selected_layout_id not in page_layout_ids
                and page_layout_ids
            ):
                page["template_layout_id"] = page_layout_ids[0]
        repair_target = repair_target_for(page)
        if repair_target is not None:
            required_title = str(repair_target.get("required_title") or "").strip()
            required_layout_id = str(
                repair_target.get("required_template_layout_id") or ""
            ).strip()
            if required_title:
                page["title"] = required_title
            if required_layout_id:
                page["template_layout_id"] = required_layout_id
        normalized_title = re.sub(
            r"\s+",
            "",
            str(page.get("title") or ""),
        ).casefold()
        if unit is not None and normalized_title in used_titles:
            replacement = next(
                (
                    str(candidate)
                    for candidate in unit.get("title_candidates") or []
                    if re.sub(r"\s+", "", str(candidate)).casefold()
                    not in used_titles
                ),
                "",
            )
            if replacement:
                page["title"] = replacement
                normalized_title = re.sub(r"\s+", "", replacement).casefold()
        if normalized_title:
            used_titles.add(normalized_title)
        # Providers sometimes over-answer the story request with draft code,
        # annotations, or visual instructions. Those fields are not part of the
        # story contract and must never leak into the compiled deck. Project the
        # response onto the declared contract, then let the strict source/layout
        # validators below decide whether the usable story fields are valid.
        normalized_pages.append({
            field: page[field]
            for field in _STORY_PAGE_CONTRACT_FIELDS
            if field in page
        })
    payload["pages"] = normalized_pages
    return payload


def _normalize_visual_batch_response(
    raw: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Project provider output onto source-bound visual decisions."""

    payload = _normalize_versioned_response(
        raw,
        schema_version="slide_visual_batch_response_v2",
        collection_field="decisions",
    )
    pages = {
        str(page.get("page_id") or ""): page
        for page in request.get("pages") or []
        if isinstance(page, dict)
    }
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return payload
    normalized: list[Any] = []
    for value in decisions:
        if not isinstance(value, dict):
            normalized.append(value)
            continue
        decision = dict(value)
        if "decision" not in decision and "decision_type" in decision:
            decision["decision"] = decision.pop("decision_type")
        else:
            decision.pop("decision_type", None)
        page = pages.get(str(decision.get("page_id") or ""))
        if page is not None:
            if not decision.get("source_block_ids"):
                decision["source_block_ids"] = list(
                    page.get("source_block_ids") or []
                )
            if not str(decision.get("resolved_template_layout_id") or "").strip():
                decision["resolved_template_layout_id"] = str(
                    page.get("template_layout_id") or ""
                )
        normalized.append({
            field: decision[field]
            for field in _VISUAL_DECISION_CONTRACT_FIELDS
            if field in decision
        })
    payload["decisions"] = normalized
    return payload


def _sanitize_provider_attempts(
    telemetry: list[dict[str, Any]],
) -> list[AIProviderAttemptDiagnosticV1]:
    """Keep operational routing data while dropping prompts, keys, and responses."""

    records: list[AIProviderAttemptDiagnosticV1] = []
    for ordinal, raw in enumerate(telemetry, start=1):
        if not isinstance(raw, dict):
            continue
        provider = str(
            raw.get("provider")
            or raw.get("provider_route")
            or "shared-ai-pool"
        )
        model = str(
            raw.get("model")
            or raw.get("model_id")
            or "provider-selected"
        )
        try:
            attempt = max(1, int(raw.get("provider_attempt") or raw.get("attempt") or ordinal))
        except (TypeError, ValueError):
            attempt = ordinal
        try:
            duration_ms = max(0, int(raw.get("duration_ms") or 0))
        except (TypeError, ValueError):
            duration_ms = 0
        try:
            queue_wait_ms = max(0, int(raw.get("queue_wait_ms") or 0))
        except (TypeError, ValueError):
            queue_wait_ms = 0
        records.append(AIProviderAttemptDiagnosticV1(
            provider=provider,
            model=model,
            attempt=attempt,
            status=str(raw.get("status") or "unknown"),
            duration_ms=duration_ms,
            queue_wait_ms=queue_wait_ms,
            error_code=str(raw.get("error_code") or ""),
        ))
    return records


def _provider_attempts_from(value: Any) -> list[AIProviderAttemptDiagnosticV1]:
    telemetry = getattr(value, "telemetry", [])
    return _sanitize_provider_attempts(telemetry if isinstance(telemetry, list) else [])


def _batch_diagnostic(
    *,
    kind: str,
    batch_id: str,
    chapter_id: str,
    duration_ms: int,
    validation_status: str,
    failure_category: str = "",
    provider: str = "",
    model: str = "",
    attempts: int = 1,
    attempt_records: list[AIProviderAttemptDiagnosticV1] | None = None,
) -> AIBatchDiagnosticV1:
    records = list(attempt_records or [])
    last = records[-1] if records else None
    actual_attempts = max(1, attempts, len(records))
    return AIBatchDiagnosticV1(
        kind=kind,
        batch_id=batch_id,
        chapter_id=chapter_id,
        provider=provider or (last.provider if last else "shared-ai-pool"),
        model=model or (last.model if last else "provider-selected"),
        duration_ms=max(0, duration_ms),
        attempts=actual_attempts,
        retry_count=max(0, actual_attempts - 1),
        validation_status=validation_status,
        failure_category=failure_category,
        attempt_records=records,
    )


def _failure_category(error: BaseException, *, prefix: str) -> tuple[str, bool]:
    original = (
        error.original_error
        if isinstance(error, AIPlannerInvocationError)
        else error
    )
    message = str(original).lower()
    if isinstance(original, (TimeoutError, asyncio.TimeoutError)) or "timeout" in message:
        return f"{prefix}_timeout", True
    if any(token in message for token in ("401", "403", "authentication", "api key")):
        return f"{prefix}_authentication", False
    if any(token in message for token in ("balance", "quota", "credit")):
        return f"{prefix}_balance_unavailable", False
    if any(token in message for token in ("429", "rate limit", "too many requests")):
        return f"{prefix}_rate_limited", True
    return f"{prefix}_failed", True


async def _invoke(planner: Planner, request: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if inspect.iscoroutinefunction(planner):
        result = planner(request)
    else:
        result = await asyncio.to_thread(planner, request)
    if inspect.isawaitable(result):
        result = await asyncio.wait_for(result, timeout=timeout_seconds)
    if not isinstance(result, dict):
        raise TypeError("AI planner response must be a JSON object")
    return result


async def _notify_batch(
    callback: BatchLifecycleCallback | None,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    result = callback(payload)
    if inspect.isawaitable(result):
        await result


def _allowed_layout_ids_for(
    teaching_intent: str,
    required_artifacts: set[str],
    template: TemplateLayoutPackContractV1,
    *,
    teaching_unit_id: str,
) -> list[str]:
    result = []
    for layout in template.layouts:
        if teaching_intent not in layout.teaching_intents:
            continue
        if required_artifacts and not required_artifacts.intersection(layout.artifact_kinds):
            continue
        result.append(layout.template_layout_id)
    if not result:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=f"No template layout supports teaching unit {teaching_unit_id}",
        )
    return result


def _layout_prompt_contract(
    layout_id: str,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    layout = template.get_layout(layout_id)
    if layout is None:  # pragma: no cover - guarded by the closed registry
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=f"Unknown template layout: {layout_id}",
        )
    return {
        "template_layout_id": layout.template_layout_id,
        "layout_slug": layout.layout_slug,
        "teaching_intents": layout.teaching_intents,
        "artifact_kinds": layout.artifact_kinds,
        "slots": [slot.model_dump(mode="json") for slot in layout.slots],
        "safe_continuation_layout_slugs": layout.safe_continuation_layout_slugs,
    }


def _grounded_title_candidates(
    source_text: str,
    *,
    max_chars: int = 72,
) -> list[str]:
    capacity = max(4, max_chars)
    candidates: list[str] = []
    for match in _MARKDOWN_TITLE_RE.finditer(source_text):
        full_title = str(match.group(1) or match.group(2) or "").strip()
        if len(full_title) <= capacity:
            continue
        for fragment in re.split(
            r"(?:[：:；;｜|]|\s+[—–-]\s+|与|及|和|\s+(?:and|or|versus|vs\.?)\s+)",
            full_title,
            flags=re.IGNORECASE,
        ):
            candidate = fragment.strip().strip("#*` ")
            if (
                4 <= len(candidate) <= capacity
                and candidate in source_text
                and candidate not in candidates
            ):
                candidates.append(candidate)
    for match in _MARKDOWN_TITLE_RE.finditer(source_text):
        candidate = str(match.group(1) or match.group(2) or "").strip()
        if len(candidate) > capacity:
            candidate = candidate[:capacity].rstrip("，。！？,;: ")
        if candidate and candidate in source_text and candidate not in candidates:
            candidates.append(candidate)
    for segment in re.split(r"[\n。！？!?；;]", source_text):
        candidate = segment.strip().strip("#*` ")[:capacity].strip()
        if (
            len(candidate) >= 4
            and candidate in source_text
            and candidate not in candidates
        ):
            candidates.append(candidate)
        if len(candidates) >= 6:
            break
    return candidates[:6]


def _story_unit_request(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    page_intents = {
        page_teaching_intent(unit, [block_id])
        for block_id in unit.primary_block_ids
    }
    page_intents.add(unit.teaching_intent)
    ordered_page_intents = [
        unit.teaching_intent,
        *sorted(page_intents - {unit.teaching_intent}),
    ]
    allowed_layout_ids_by_page_intent = {
        page_intent: _allowed_layout_ids_for(
            page_intent,
            (
                set(unit.artifact_kinds)
                if page_intent == "artifact_explanation"
                else set()
            ),
            template,
            teaching_unit_id=unit.teaching_unit_id,
        )
        for page_intent in ordered_page_intents
    }
    allowed_layout_ids = list(dict.fromkeys(
        layout_id
        for page_intent in ordered_page_intents
        for layout_id in allowed_layout_ids_by_page_intent[page_intent]
    ))
    allowed_layouts = [
        _layout_prompt_contract(layout_id, template)
        for layout_id in allowed_layout_ids
    ]
    title_capacities = [
        int(slot.get("max_chars") or 0)
        for layout in allowed_layouts
        for slot in layout["slots"]
        if slot.get("slot_kind") == "title" and int(slot.get("max_chars") or 0) > 0
    ]
    title_max_chars = min(title_capacities) if title_capacities else 72
    return {
        "teaching_unit_id": unit.teaching_unit_id,
        "source_ordinal": unit.source_ordinal,
        "primary_block_ids": unit.primary_block_ids,
        "primary_blocks": [
            {
                "block_id": block_id,
                "role": unit.primary_block_roles.get(block_id, ""),
                "artifact_kinds": unit.primary_block_artifacts.get(block_id, []),
                "page_intent": page_teaching_intent(unit, [block_id]),
            }
            for block_id in unit.primary_block_ids
        ],
        "teaching_intent": unit.teaching_intent,
        "artifact_kinds": unit.artifact_kinds,
        "source_asset_ids": unit.source_asset_refs,
        "teaching_plan_context": unit.teaching_plan_context,
        "prerequisite_unit_ids": unit.prerequisite_unit_ids,
        "source_text": unit.source_text,
        "title_max_chars": title_max_chars,
        "title_policy": "copy_verbatim_from_title_candidates",
        "title_candidates": _grounded_title_candidates(
            unit.source_text,
            max_chars=title_max_chars,
        ),
        "allowed_template_layout_ids": allowed_layout_ids,
        "allowed_template_layout_ids_by_page_intent": (
            allowed_layout_ids_by_page_intent
        ),
        "allowed_template_layouts": allowed_layouts,
    }


def _story_requests(
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> list[dict[str, Any]]:
    by_section: dict[str, list[CoursePresentationUnitV1]] = defaultdict(list)
    section_order: list[str] = []
    for unit in graph.units:
        if unit.section_id not in by_section:
            section_order.append(unit.section_id)
        by_section[unit.section_id].append(unit)
    return [
        {
            "schema_version": "slide_story_batch_request_v3",
            "chapter_id": section_id,
            "source_document_revision": graph.source_document_revision,
            "template_digest": template.template_digest,
            "constraints": {
                "preserve_unit_order": True,
                "cover_every_primary_block": True,
                "primary_block_page_ownership": "exactly_once",
                "allow_multiple_primary_blocks_per_page": True,
                "canvas_expression": "semantic_closure_with_full_source_in_notes",
                "pages_per_unit": [1, 3],
                "allow_new_facts": False,
                "allow_unknown_ids": False,
            },
            "response_contract": {
                "schema_version": "slide_story_batch_response_v3",
                "required_top_level_fields": [
                    "schema_version",
                    "chapter_id",
                    "pages",
                ],
                "required_page_fields": [
                    "page_id",
                    "teaching_unit_id",
                    "template_layout_id",
                    "title",
                    "source_block_ids",
                ],
                "optional_page_fields": ["summary"],
                "forbidden_page_fields": ["content"],
            },
            "teaching_units": [
                _story_unit_request(unit, template)
                for unit in by_section[section_id]
            ],
        }
        for section_id in section_order
    ]


def _validate_story_batch_candidate(
    *,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    request: dict[str, Any],
    batch: SlideStoryBatchV3,
) -> None:
    reserved_titles = {
        re.sub(r"\s+", "", str(title)).casefold()
        for title in request.get("constraints", {}).get("forbidden_titles") or []
        if str(title).strip()
    }
    reused = next(
        (
            page for page in batch.pages
            if re.sub(r"\s+", "", page.title).casefold() in reserved_titles
        ),
        None,
    )
    if reused is not None:
        raise V6BuildError(
            stage="story",
            code="duplicate_slide_title",
            message="Each V6 page must have a distinct teaching title",
            page_id=reused.page_id,
        )
    requested_unit_ids = {
        str(unit.get("teaching_unit_id") or "")
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict)
    }
    units = [
        unit for unit in graph.units
        if unit.teaching_unit_id in requested_unit_ids
    ]
    scoped_graph = graph.model_copy(update={
        "units": units,
        "formal_block_ids": [
            block_id
            for unit in units
            for block_id in unit.primary_block_ids
        ],
        "primary_block_coverage": 1.0,
        "diagnostics": [],
    })
    validate_slide_story_plan_v3(
        SlideStoryPlanV3(
            source_document_revision=graph.source_document_revision,
            template_digest=template.template_digest,
            batches=[batch],
        ),
        scoped_graph,
        template,
    )


def _story_repair_targets(
    request: dict[str, Any],
    response_payload: dict[str, Any] | None,
    error: Exception | None,
) -> list[dict[str, Any]]:
    """Describe a rejected page using only its frozen request constraints."""

    if response_payload is None or not isinstance(error, V6BuildError):
        return []
    pages = response_payload.get("pages")
    if not isinstance(pages, list):
        return []
    units = {
        str(item.get("teaching_unit_id") or ""): item
        for item in request.get("teaching_units") or []
        if isinstance(item, dict)
    }

    def target_for(
        unit: dict[str, Any],
        *,
        page_id: str = "",
        missing_source_block_ids: list[str] | None = None,
        duplicate_source_block_ids: list[str] | None = None,
        duplicate_page_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        unit_id = str(unit.get("teaching_unit_id") or "")
        current_page = next(
            (
                page for page in pages
                if isinstance(page, dict)
                and str(page.get("page_id") or "") == page_id
            ),
            None,
        )
        current_title = str((current_page or {}).get("title") or "")
        current_summary = str((current_page or {}).get("summary") or "")
        normalized_current_title = re.sub(r"\s+", "", current_title).casefold()
        conflicting_page_ids = [
            str(page.get("page_id") or "")
            for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") != page_id
            and re.sub(r"\s+", "", str(page.get("title") or "")).casefold()
            == normalized_current_title
        ] if normalized_current_title else []
        forbidden_titles = list(dict.fromkeys([
            *(
                str(title)
                for title in request.get("constraints", {}).get("forbidden_titles") or []
                if str(title).strip()
            ),
            *(
                str(page.get("title") or "")
                for page in pages
                if isinstance(page, dict)
                and str(page.get("page_id") or "") != page_id
                and str(page.get("title") or "").strip()
            ),
        ]))
        normalized_forbidden_titles = {
            re.sub(r"\s+", "", title).casefold()
            for title in forbidden_titles
        }
        allowed_title_candidates = list(unit.get("title_candidates") or [])
        title_max_chars = int(unit.get("title_max_chars") or 0)
        current_source_block_ids = [
            str(block_id)
            for block_id in (current_page or {}).get("source_block_ids") or []
        ]
        block_metadata = {
            str(block.get("block_id") or ""): block
            for block in unit.get("primary_blocks") or []
            if isinstance(block, dict)
        }
        current_roles = [
            str(block_metadata.get(block_id, {}).get("role") or "")
            for block_id in current_source_block_ids
            if str(block_metadata.get(block_id, {}).get("role") or "")
        ]
        current_artifacts = {
            str(artifact)
            for block_id in current_source_block_ids
            for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
            if str(artifact)
        }
        page_intent = (
            teaching_intent_for_roles(current_roles, current_artifacts)
            if current_roles or current_artifacts
            else str(unit.get("teaching_intent") or "")
        )
        page_allowed_layout_ids = list(
            (unit.get("allowed_template_layout_ids_by_page_intent") or {}).get(
                page_intent,
                unit.get("allowed_template_layout_ids") or [],
            )
        )
        available_title_candidates = [
            title
            for title in allowed_title_candidates
            if (not title_max_chars or len(str(title)) <= title_max_chars)
            and re.sub(r"\s+", "", str(title)).casefold()
            not in normalized_forbidden_titles
        ]
        title_repair_required = error.failure.code in {
            "duplicate_slide_title",
            "story_title_capacity_exceeded",
            "story_unsupported_title",
        }
        layout_repair_required = error.failure.code in {
            "template_layout_artifact_mismatch",
            "template_layout_intent_mismatch",
        }
        return {
            "page_id": page_id,
            "teaching_unit_id": unit_id,
            "allowed_page_count_range": [1, 3],
            "observed_unit_page_ids": [
                str(page.get("page_id") or "")
                for page in pages
                if isinstance(page, dict)
                and str(page.get("teaching_unit_id") or "") == unit_id
                and str(page.get("page_id") or "")
            ],
            "page_intent": page_intent,
            "allowed_template_layout_ids": page_allowed_layout_ids,
            "required_template_layout_id": (
                str(page_allowed_layout_ids[0])
                if layout_repair_required and page_allowed_layout_ids
                else ""
            ),
            "required_source_block_ids": list(unit.get("primary_block_ids") or []),
            "current_source_block_ids": current_source_block_ids,
            "missing_source_block_ids": list(missing_source_block_ids or []),
            "duplicate_source_block_ids": list(duplicate_source_block_ids or []),
            "duplicate_page_ids": list(duplicate_page_ids or []),
            "allowed_title_candidates": allowed_title_candidates,
            "available_title_candidates": available_title_candidates,
            "required_title": (
                str(available_title_candidates[0])
                if title_repair_required and available_title_candidates
                else ""
            ),
            "title_max_chars": title_max_chars,
            "current_title": current_title,
            "duplicate_title": current_title if conflicting_page_ids else "",
            "conflicting_page_ids": conflicting_page_ids,
            "forbidden_titles": forbidden_titles,
            "current_summary": current_summary,
            "summary_policy": "exact_source_excerpt_or_empty",
        }

    failed_page_id = str(error.failure.page_id or "")
    if not failed_page_id:
        block_page_ids: dict[str, list[str]] = defaultdict(list)
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            for block_id in page.get("source_block_ids") or []:
                block_page_ids[str(block_id)].append(page_id)
        covered = set(block_page_ids)
        missing_targets = []
        for unit in units.values():
            primary_ids = [
                str(block_id)
                for block_id in unit.get("primary_block_ids") or []
            ]
            missing = [block_id for block_id in primary_ids if block_id not in covered]
            duplicates = [
                block_id
                for block_id in primary_ids
                if len(block_page_ids.get(block_id) or []) > 1
            ]
            if missing or duplicates:
                duplicate_pages = list(dict.fromkeys(
                    page_id
                    for block_id in duplicates
                    for page_id in block_page_ids.get(block_id) or []
                    if page_id
                ))
                missing_targets.append(target_for(
                    unit,
                    missing_source_block_ids=missing,
                    duplicate_source_block_ids=duplicates,
                    duplicate_page_ids=duplicate_pages,
                ))
        return missing_targets
    failed_page = next(
        (
            page for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") == failed_page_id
        ),
        None,
    )
    if failed_page is None:
        return []
    unit_id = str(failed_page.get("teaching_unit_id") or "")
    unit = units.get(unit_id)
    if unit is None:
        return []
    return [target_for(unit, page_id=failed_page_id)]


async def plan_slide_story_v3(
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    *,
    ai_planner: Planner | None,
    timeout_seconds: float = 180.0,
    batch_callback: BatchLifecycleCallback | None = None,
    resume_batches: list[SlideStoryBatchV3] | None = None,
) -> SlideStoryPlanV3:
    if ai_planner is None:
        raise V6BuildError(
            stage="story",
            code="story_ai_required",
            message="V6 requires the shared AI story planner",
            retryable=True,
        )
    batches: list[SlideStoryBatchV3] = []
    resumed_by_chapter = {
        batch.chapter_id: batch
        for batch in (resume_batches or [])
        if batch.validation_status == "passed"
    }
    page_ordinal = 0
    for batch_index, request in enumerate(_story_requests(graph, template)):
        request = {
            **request,
            "constraints": {
                **request["constraints"],
                "forbidden_titles": [
                    page.title
                    for accepted_batch in batches
                    for page in accepted_batch.pages
                ],
            },
        }
        batch_id = f"story-{batch_index + 1}"
        resumed = resumed_by_chapter.get(str(request["chapter_id"]))
        if resumed is not None:
            pages = [
                page.model_copy(update={"page_ordinal": page_ordinal + index})
                for index, page in enumerate(resumed.pages)
            ]
            page_ordinal += len(pages)
            batch = resumed.model_copy(update={"batch_id": batch_id, "pages": pages})
            batches.append(batch)
            await _notify_batch(batch_callback, {
                "phase": "completed",
                "kind": "story",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": batch.chapter_id,
                "resumed": True,
                "batch": batch,
            })
            continue
        await _notify_batch(batch_callback, {
            "phase": "started",
            "kind": "story",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": str(request["chapter_id"]),
            "resumed": False,
        })
        started = time.perf_counter()
        attempt_records: list[AIProviderAttemptDiagnosticV1] = []
        reported_provider = ""
        reported_model = ""
        reported_attempts = 1
        planner_invocations = 0
        try:
            contract_error: Exception | None = None
            previous_response_payload: dict[str, Any] | None = None
            for validation_attempt in range(_STORY_SEMANTIC_MAX_ATTEMPTS):
                attempt_request = request
                if validation_attempt:
                    attempt_request = {
                        **request,
                        "repair_feedback": {
                            "attempt": validation_attempt + 1,
                            "code": (
                                contract_error.failure.code
                                if isinstance(contract_error, V6BuildError)
                                else "story_response_contract_invalid"
                            ),
                            "message": str(contract_error or ""),
                            "repair_targets": _story_repair_targets(
                                request,
                                previous_response_payload,
                                contract_error,
                            ),
                            "instruction": (
                                "Return a fresh response that exactly follows response_contract, "
                                "derives each page's intent from its bound primary_blocks and uses "
                                "only that intent's allowed_template_layout_ids_by_page_intent, and "
                                "contains only source IDs supplied for that unit. Partition every "
                                "unit's primary_block_ids across one to three pages: bind multiple "
                                "related block IDs to the same page instead of creating one page per "
                                "block. Full source remains available in speaker notes downstream. "
                                "Copy each title verbatim from that unit's title_candidates and keep "
                                "it within that unit's title_max_chars. Set "
                                "a repair target's title exactly to required_title when provided. Set "
                                "its template_layout_id exactly to required_template_layout_id when "
                                "provided. Set "
                                "summary to empty unless its complete wording is directly supported "
                                "by that unit's source_text; never add identifiers or facts."
                            ),
                        },
                    }
                    await _notify_batch(batch_callback, {
                        "phase": "started",
                        "kind": "story",
                        "batch_index": batch_index,
                        "batch_id": batch_id,
                        "chapter_id": str(request["chapter_id"]),
                        "resumed": False,
                        "retry_attempt": validation_attempt,
                    })
                try:
                    planner_invocations += 1
                    raw = await _invoke(ai_planner, attempt_request, timeout_seconds)
                    attempt_records.extend(_provider_attempts_from(raw))
                    previous_response_payload = _normalize_story_batch_response(
                        raw,
                        attempt_request,
                    )
                    response = _StoryBatchResponse.model_validate(
                        previous_response_payload
                    )
                    reported_provider = response.provider or reported_provider
                    reported_model = response.model or reported_model
                    reported_attempts = max(
                        reported_attempts,
                        response.attempts + validation_attempt,
                        len(attempt_records),
                        planner_invocations,
                    )
                    if response.schema_version != "slide_story_batch_response_v3":
                        raise ValueError("Unexpected story response schema")
                    if response.chapter_id != request["chapter_id"]:
                        raise ValueError("Story response chapter does not match its request")
                    local_pages = [
                        SlideStoryPageV3(
                            **item.model_dump(mode="json"),
                            page_ordinal=index,
                        )
                        for index, item in enumerate(response.pages)
                    ]
                    candidate_batch = SlideStoryBatchV3(
                        batch_id=batch_id,
                        chapter_id=response.chapter_id,
                        provider=response.provider or "shared-ai-pool",
                        model=response.model or "provider-selected",
                        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
                        attempts=reported_attempts,
                        validation_status="passed",
                        pages=local_pages,
                    )
                    _validate_story_batch_candidate(
                        graph=graph,
                        template=template,
                        request=request,
                        batch=candidate_batch,
                    )
                    pages = [
                        page.model_copy(update={"page_ordinal": page_ordinal + index})
                        for index, page in enumerate(local_pages)
                    ]
                    page_ordinal += len(pages)
                    batch = candidate_batch.model_copy(update={"pages": pages})
                    break
                except (ValidationError, ValueError, V6BuildError) as error:
                    contract_error = error
                    if validation_attempt < _STORY_SEMANTIC_MAX_ATTEMPTS - 1:
                        continue
                    if isinstance(error, V6BuildError):
                        raise V6BuildError(
                            stage=error.failure.stage,
                            code=error.failure.code,
                            message=error.failure.message,
                            retryable=True,
                            chapter_id=str(request["chapter_id"]),
                            page_id=error.failure.page_id,
                            batch_id=batch_id,
                        ) from error
                    raise
                else:  # pragma: no cover - the bounded loop either succeeds or raises
                    raise RuntimeError("Story response repair loop exited unexpectedly")
            batch = SlideStoryBatchV3(
                    batch_id=batch_id,
                    chapter_id=batch.chapter_id,
                    provider=batch.provider,
                    model=batch.model,
                    duration_ms=max(batch.duration_ms, round((time.perf_counter() - started) * 1000)),
                    attempts=batch.attempts,
                    validation_status="passed",
                    pages=batch.pages,
            )
            batches.append(batch)
        except V6BuildError as error:
            await _notify_batch(batch_callback, {
                "phase": "failed",
                "kind": "story",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": str(request["chapter_id"]),
                "resumed": False,
                "diagnostic": _batch_diagnostic(
                    kind="story",
                    batch_id=batch_id,
                    chapter_id=str(request["chapter_id"]),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    validation_status="failed",
                    failure_category=error.failure.code,
                    provider=reported_provider,
                    model=reported_model,
                    attempts=max(reported_attempts, planner_invocations),
                    attempt_records=attempt_records,
                ),
            })
            raise
        except Exception as error:
            attempt_records.extend(_provider_attempts_from(error))
            code, retryable = _failure_category(error, prefix="story_ai_batch")
            await _notify_batch(batch_callback, {
                "phase": "failed",
                "kind": "story",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": str(request["chapter_id"]),
                "resumed": False,
                "diagnostic": _batch_diagnostic(
                    kind="story",
                    batch_id=batch_id,
                    chapter_id=str(request["chapter_id"]),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    validation_status="failed",
                    failure_category=code,
                    provider=reported_provider,
                    model=reported_model,
                    attempts=max(reported_attempts, planner_invocations),
                    attempt_records=attempt_records,
                ),
            })
            raise V6BuildError(
                stage="story",
                code=code,
                message=str(error) or "Story AI batch failed",
                retryable=retryable,
                chapter_id=str(request["chapter_id"]),
                batch_id=batch_id,
            ) from error
        await _notify_batch(batch_callback, {
            "phase": "completed",
            "kind": "story",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
            "batch": batch,
            "diagnostic": _batch_diagnostic(
                kind="story",
                batch_id=batch_id,
                chapter_id=batch.chapter_id,
                duration_ms=batch.duration_ms,
                validation_status="passed",
                provider=batch.provider,
                model=batch.model,
                attempts=batch.attempts,
                attempt_records=attempt_records,
            ),
        })
    plan = SlideStoryPlanV3(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        batches=batches,
    )
    validate_slide_story_plan_v3(plan, graph, template)
    return plan


def _visual_request(
    batch: SlideStoryBatchV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    units = {unit.teaching_unit_id: unit for unit in graph.units}
    return {
        "schema_version": "slide_visual_batch_request_v2",
        "chapter_id": batch.chapter_id,
        "source_document_revision": graph.source_document_revision,
        "template_digest": template.template_digest,
        "constraints": {
            "source_bound_only": True,
            "prefer_text_native_when_visual_is_not_meaningful": True,
            "preserve_required_artifacts": True,
        },
        "response_contract": {
            "schema_version": "slide_visual_batch_response_v2",
            "required_top_level_fields": ["schema_version", "decisions"],
            "required_decision_fields": [
                "page_id",
                "decision",
                "source_block_ids",
                "resolved_template_layout_id",
            ],
            "optional_decision_fields": ["source_asset_ids", "visual_payload"],
            "forbidden_decision_fields": ["decision_type", "code_payload"],
        },
        "pages": [
            {
                "page_id": page.page_id,
                "teaching_unit_id": page.teaching_unit_id,
                "template_layout_id": page.template_layout_id,
                "source_block_ids": page.source_block_ids,
                "source_text": units[page.teaching_unit_id].source_text,
                "artifact_kinds": sorted(page_artifact_kinds(
                    units[page.teaching_unit_id],
                    page.source_block_ids,
                )),
                "allowed_decisions": _allowed_visual_decisions(
                    page_artifact_kinds(
                        units[page.teaching_unit_id],
                        page.source_block_ids,
                    ),
                    units[page.teaching_unit_id].source_asset_refs,
                ),
                "source_asset_ids": units[page.teaching_unit_id].source_asset_refs,
            }
            for page in batch.pages
        ],
    }


_HARD_VISUAL_ARTIFACTS = {"code", "formula", "table", "data", "experiment", "source_excerpt"}
_VISUAL_DECISIONS_BY_ARTIFACT: dict[str, set[str]] = {
    "code": {"code"},
    "formula": {"formula"},
    "table": {"table", "data"},
    "data": {"data", "table"},
    "experiment": {"experiment", "image", "data"},
    "source_excerpt": {"source_excerpt", "image"},
}


def _allowed_visual_decisions(
    artifact_kinds: set[str],
    source_asset_ids: list[str],
) -> list[str]:
    required_artifacts = artifact_kinds.intersection(_HARD_VISUAL_ARTIFACTS)
    if required_artifacts:
        decisions = {
            decision
            for artifact in required_artifacts
            for decision in _VISUAL_DECISIONS_BY_ARTIFACT.get(artifact, set())
        }
        if not source_asset_ids:
            decisions.difference_update({"image", "experiment"})
        return sorted(decisions)
    decisions = {"diagram", "text_native"}
    if source_asset_ids:
        decisions.add("image")
    return sorted(decisions)


def _validate_visual_batch_candidate(
    *,
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    batch: SlideStoryBatchV3,
    decisions: list[SlideVisualDecisionV2],
) -> None:
    unit_ids = {page.teaching_unit_id for page in batch.pages}
    scoped_story = story.model_copy(update={"batches": [batch]})
    scoped_graph = graph.model_copy(update={
        "units": [unit for unit in graph.units if unit.teaching_unit_id in unit_ids],
        "formal_block_ids": [
            block_id
            for page in batch.pages
            for block_id in page.source_block_ids
        ],
        "primary_block_coverage": 1.0,
        "diagnostics": [],
    })
    validate_slide_visual_plan_v2(
        SlideVisualPlanV2(
            source_document_revision=graph.source_document_revision,
            template_digest=template.template_digest,
            decisions=decisions,
        ),
        scoped_story,
        scoped_graph,
        template,
    )


def _visual_repair_targets(
    request: dict[str, Any],
    error: Exception | None,
) -> list[dict[str, Any]]:
    failed_page_id = (
        str(error.failure.page_id or "")
        if isinstance(error, V6BuildError)
        else ""
    )
    pages = [
        page
        for page in request.get("pages") or []
        if isinstance(page, dict)
        and (not failed_page_id or str(page.get("page_id") or "") == failed_page_id)
    ]
    return [
        {
            "page_id": str(page.get("page_id") or ""),
            "required_artifact_kinds": list(page.get("artifact_kinds") or []),
            "allowed_decisions": list(page.get("allowed_decisions") or []),
            "required_source_block_ids": list(page.get("source_block_ids") or []),
            "required_template_layout_id": str(page.get("template_layout_id") or ""),
            "allowed_source_asset_ids": list(page.get("source_asset_ids") or []),
        }
        for page in pages
    ]


async def plan_slide_visuals_v2(
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    *,
    ai_planner: Planner | None,
    concurrency: int = 3,
    timeout_seconds: float = 180.0,
    batch_callback: BatchLifecycleCallback | None = None,
    resume_decisions: list[SlideVisualDecisionV2] | None = None,
) -> SlideVisualPlanV2:
    if ai_planner is None:
        raise V6BuildError(
            stage="visual",
            code="visual_ai_required",
            message="V6 requires a visual planning attempt",
            retryable=True,
        )
    limit = max(2, min(4, concurrency))
    semaphore = asyncio.Semaphore(limit)
    units = {unit.teaching_unit_id: unit for unit in graph.units}
    resumed_by_page = {
        decision.page_id: decision for decision in (resume_decisions or [])
    }

    async def plan_batch(
        batch_index: int,
        batch: SlideStoryBatchV3,
    ) -> list[SlideVisualDecisionV2]:
        batch_id = f"visual-{batch_index + 1}"
        resumed = [
            resumed_by_page[page.page_id]
            for page in batch.pages
            if page.page_id in resumed_by_page
        ]
        if len(resumed) == len(batch.pages):
            await _notify_batch(batch_callback, {
                "phase": "completed",
                "kind": "visual",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": batch.chapter_id,
                "resumed": True,
                "decisions": resumed,
            })
            return resumed
        await _notify_batch(batch_callback, {
            "phase": "started",
            "kind": "visual",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
        })
        request = _visual_request(batch, graph, template)
        started = time.perf_counter()
        attempt_records: list[AIProviderAttemptDiagnosticV1] = []
        reported_provider = ""
        reported_model = ""
        reported_attempts = 1
        planner_invocations = 0
        batch_validation_status = "passed"
        batch_failure_category = ""
        try:
            contract_error: Exception | None = None
            for validation_attempt in range(_VISUAL_SEMANTIC_MAX_ATTEMPTS):
                attempt_request = request
                if validation_attempt:
                    attempt_request = {
                        **request,
                        "repair_feedback": {
                            "attempt": validation_attempt + 1,
                            "code": (
                                contract_error.failure.code
                                if isinstance(contract_error, V6BuildError)
                                else "visual_response_contract_invalid"
                            ),
                            "message": str(contract_error or ""),
                            "repair_targets": _visual_repair_targets(
                                request,
                                contract_error,
                            ),
                            "instruction": (
                                "Return a fresh response that follows response_contract exactly. "
                                "For each repair target choose only an allowed_decision, preserve "
                                "its exact source block and template layout bindings, and never "
                                "invent artifact payloads."
                            ),
                        },
                    }
                    await _notify_batch(batch_callback, {
                        "phase": "started",
                        "kind": "visual",
                        "batch_index": batch_index,
                        "batch_id": batch_id,
                        "chapter_id": batch.chapter_id,
                        "resumed": False,
                        "retry_attempt": validation_attempt,
                    })
                try:
                    async with semaphore:
                        planner_invocations += 1
                        raw = await _invoke(ai_planner, attempt_request, timeout_seconds)
                    attempt_records.extend(_provider_attempts_from(raw))
                    response = _VisualBatchResponse.model_validate(
                        _normalize_visual_batch_response(raw, request)
                    )
                    reported_provider = response.provider or reported_provider
                    reported_model = response.model or reported_model
                    reported_attempts = max(
                        reported_attempts,
                        response.attempts + validation_attempt,
                        len(attempt_records),
                        planner_invocations,
                    )
                    if response.schema_version != "slide_visual_batch_response_v2":
                        raise ValueError("Unexpected visual response schema")
                    duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    decisions = [
                        decision.model_copy(
                            update={
                                "provider": decision.provider or response.provider or "shared-ai-pool",
                                "model": decision.model or response.model or "provider-selected",
                                "attempts": max(
                                    decision.attempts,
                                    reported_attempts,
                                ),
                                "duration_ms": max(decision.duration_ms, duration_ms),
                            }
                        )
                        for decision in response.decisions
                    ]
                    _validate_visual_batch_candidate(
                        story=story,
                        graph=graph,
                        template=template,
                        batch=batch,
                        decisions=decisions,
                    )
                    break
                except (ValidationError, ValueError, V6BuildError) as error:
                    contract_error = error
                    if validation_attempt < _VISUAL_SEMANTIC_MAX_ATTEMPTS - 1:
                        continue
                    raise
            else:  # pragma: no cover - the bounded loop either succeeds or raises
                raise RuntimeError("Visual response repair loop exited unexpectedly")
        except Exception as error:
            attempt_records.extend(_provider_attempts_from(error))
            required_pages = [
                page
                for page in batch.pages
                if page_artifact_kinds(
                    units[page.teaching_unit_id],
                    page.source_block_ids,
                ).intersection(_HARD_VISUAL_ARTIFACTS)
            ]
            if required_pages:
                failure_category = (
                    error.failure.code
                    if isinstance(error, V6BuildError)
                    else "visual_ai_required_artifact_failed"
                )
                await _notify_batch(batch_callback, {
                    "phase": "failed",
                    "kind": "visual",
                    "batch_index": batch_index,
                    "batch_id": batch_id,
                    "chapter_id": batch.chapter_id,
                    "resumed": False,
                    "diagnostic": _batch_diagnostic(
                        kind="visual",
                        batch_id=batch_id,
                        chapter_id=batch.chapter_id,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                        validation_status="failed",
                        failure_category=failure_category,
                        provider=reported_provider,
                        model=reported_model,
                        attempts=max(reported_attempts, planner_invocations),
                        attempt_records=attempt_records,
                    ),
                })
                if isinstance(error, V6BuildError):
                    raise V6BuildError(
                        stage=error.failure.stage,
                        code=error.failure.code,
                        message=error.failure.message,
                        retryable=True,
                        chapter_id=batch.chapter_id,
                        page_id=error.failure.page_id or required_pages[0].page_id,
                        batch_id=batch_id,
                    ) from error
                raise V6BuildError(
                    stage="visual",
                    code="visual_ai_required_artifact_failed",
                    message=str(error) or "Visual AI failed for a required artifact page",
                    retryable=True,
                    chapter_id=batch.chapter_id,
                    page_id=required_pages[0].page_id,
                    batch_id=batch_id,
                ) from error
            category, _ = _failure_category(error, prefix="visual_ai_batch")
            batch_validation_status = "degraded"
            batch_failure_category = category
            decisions = [
                SlideVisualDecisionV2(
                    page_id=page.page_id,
                    decision="text_native",
                    source_block_ids=page.source_block_ids,
                    resolved_template_layout_id=page.template_layout_id,
                    degraded=True,
                    degradation_reason=category,
                    duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
                )
                for page in batch.pages
            ]
        await _notify_batch(batch_callback, {
            "phase": "completed",
            "kind": "visual",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
            "decisions": decisions,
            "diagnostic": _batch_diagnostic(
                kind="visual",
                batch_id=batch_id,
                chapter_id=batch.chapter_id,
                duration_ms=round((time.perf_counter() - started) * 1000),
                validation_status=batch_validation_status,
                failure_category=batch_failure_category,
                provider=reported_provider,
                model=reported_model,
                attempts=max(reported_attempts, planner_invocations),
                attempt_records=attempt_records,
            ),
        })
        return decisions

    nested = await asyncio.gather(*(
        plan_batch(index, batch) for index, batch in enumerate(story.batches)
    ))
    plan = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[decision for group in nested for decision in group],
    )
    validate_slide_visual_plan_v2(plan, story, graph, template)
    return plan


def build_ai_base_story_planner_v6() -> Planner:
    provider = AIBase()

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        telemetry: list[dict[str, Any]] = []
        try:
            response = await provider._call_llm(
                json.dumps(request, ensure_ascii=False),
                system_prompt=(
                "Return only slide_story_batch_response_v3 JSON. You are a course-faithful "
                "presentation planner. Use every supplied primary_block_id exactly once, keep "
                "teaching units and prerequisites in order, and use only supplied teaching_unit_id. "
                "Derive each page intent from the roles and artifacts of its bound primary_blocks, "
                "then select a layout from allowed_template_layout_ids_by_page_intent for that intent. "
                "Create one to three pages per unit. Do not create "
                "one page per primary block: partition the unit's block IDs across its pages and "
                "bind multiple related blocks to one page when needed. The downstream compiler "
                "keeps complete source text in speaker notes, so canvas pages should express a "
                "semantically closed teaching step rather than repeat all source prose. Titles, "
                "summaries, transitions, facts, numbers, formulas and identifiers must be supported "
                "by that unit's source_text. Every page must contain exactly page_id, "
                "teaching_unit_id, template_layout_id, title, summary and source_block_ids at the "
                "page level; never emit a nested content object. Copy titles verbatim from the "
                "selected teaching unit's title_candidates and keep each title within the supplied "
                "title_max_chars. Never invent teaching content."
                ),
                use_fast_model=False,
                retry_count=1,
                max_attempts=3,
                max_tokens=6144,
                reject_truncated=True,
                raise_on_failure=True,
                json_mode=True,
                model_role="ppt_story",
                telemetry_sink=telemetry.append,
            )
        except Exception as error:
            raise AIPlannerInvocationError(error, telemetry=telemetry) from error
        value = provider._extract_json(response or "") or {}
        records = _sanitize_provider_attempts(telemetry)
        if records:
            value.setdefault("provider", records[-1].provider)
            value.setdefault("model", records[-1].model)
            value.setdefault("attempts", len(records))
        return _AIPlannerResponse(value, telemetry=telemetry)

    return planner


def build_ai_base_visual_planner_v2() -> Planner:
    provider = AIBase()

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        telemetry: list[dict[str, Any]] = []
        try:
            response = await provider._call_llm(
                json.dumps(request, ensure_ascii=False),
                system_prompt=(
                "Return only slide_visual_batch_response_v2 JSON with exactly one decision per "
                "page_id and follow response_contract exactly. Use decision, never decision_type. "
                "Use only supplied source_block_ids and template_layout_id values. Preserve "
                "required code, formula, table, data, experiment and source evidence. Choose "
                "each page's decision only from its allowed_decisions. Choose text_native when no "
                "meaningful visual is source-supported. Do not write slide copy "
                "or invent labels, facts, data, code_payload, or other artifact payloads. The compiler "
                "reads code, formulas and tables from frozen source blocks. For diagram decisions "
                "include visual_payload with "
                "two to six source-grounded nodes, source_block_ids per node, and valid edges. For "
                "image or experiment decisions choose only supplied source_asset_ids."
                ),
                use_fast_model=True,
                retry_count=1,
                max_attempts=3,
                max_tokens=4096,
                reject_truncated=True,
                raise_on_failure=True,
                json_mode=True,
                model_role="ppt_visual",
                telemetry_sink=telemetry.append,
            )
        except Exception as error:
            raise AIPlannerInvocationError(error, telemetry=telemetry) from error
        value = provider._extract_json(response or "") or {}
        records = _sanitize_provider_attempts(telemetry)
        if records:
            value.setdefault("provider", records[-1].provider)
            value.setdefault("model", records[-1].model)
            value.setdefault("attempts", len(records))
        return _AIPlannerResponse(value, telemetry=telemetry)

    return planner


__all__ = [
    "AIPlannerInvocationError",
    "build_ai_base_story_planner_v6",
    "build_ai_base_visual_planner_v2",
    "plan_slide_story_v3",
    "plan_slide_visuals_v2",
]
