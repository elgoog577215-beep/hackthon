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
from collections import Counter, defaultdict
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
    _complete_sentence_excerpt,
    _protected_tokens,
    _title_is_incomplete,
    _visible_prose_text,
    graph_page_source_blocks,
    source_required_slot_kinds,
    story_page_count_range,
    story_safe_page_slices,
    story_safe_partition_options,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
    validate_story_template_text_slots,
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


def _request_title_candidates_for_blocks(
    unit: dict[str, Any],
    source_block_ids: list[str],
) -> list[str]:
    block_metadata = {
        str(block.get("block_id") or ""): block
        for block in unit.get("primary_blocks") or []
        if isinstance(block, dict)
    }
    candidates = list(dict.fromkeys(
        str(candidate)
        for block_id in source_block_ids
        for candidate in block_metadata.get(block_id, {}).get(
            "title_candidates",
            [],
        )
        if str(candidate).strip()
    ))
    return candidates or [
        str(candidate)
        for candidate in unit.get("title_candidates") or []
        if str(candidate).strip()
    ]


def _project_required_safe_partitions(
    pages: list[Any],
    units: dict[str, dict[str, Any]],
    repair_targets: list[dict[str, Any]],
    *,
    chapter_id: str,
) -> list[Any]:
    """Snap a failed AI retry to its one frozen, source-safe repair partition."""

    targets_by_unit = {
        str(target.get("teaching_unit_id") or ""): target
        for target in repair_targets
        if target.get("repartition_required") is True
        and target.get("source_coverage_verified") is True
        and isinstance(target.get("required_safe_partition"), dict)
    }
    if not targets_by_unit:
        return pages

    pages_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unscoped_pages: list[Any] = []
    for value in pages:
        if not isinstance(value, dict):
            unscoped_pages.append(value)
            continue
        unit_id = str(value.get("teaching_unit_id") or "")
        if unit_id not in units:
            unscoped_pages.append(value)
            continue
        pages_by_unit[unit_id].append(value)

    projected: list[Any] = []
    used_page_ids: set[str] = set()
    for unit_id, unit in units.items():
        target = targets_by_unit.get(unit_id)
        provider_pages = pages_by_unit.get(unit_id, [])
        if target is None:
            projected.extend(provider_pages)
            used_page_ids.update(
                str(page.get("page_id") or "") for page in provider_pages
            )
            continue
        if not provider_pages:
            continue
        provider_source_order = [
            str(block_id)
            for page in provider_pages
            for block_id in page.get("source_block_ids") or []
        ]
        expected_source_order = [
            str(block_id) for block_id in unit.get("primary_block_ids") or []
        ]
        if any(
            block_id not in set(expected_source_order)
            for block_id in provider_source_order
        ):
            projected.extend(provider_pages)
            continue
        provider_partition = [
            [str(block_id) for block_id in page.get("source_block_ids") or []]
            for page in provider_pages
        ]
        safe_partitions = [
            [
                [
                    str(block_id)
                    for block_id in page.get("source_block_ids") or []
                ]
                for page in option.get("pages") or []
                if isinstance(page, dict)
            ]
            for option in unit.get("safe_partition_options") or []
            if isinstance(option, dict)
        ]
        if provider_partition in safe_partitions:
            projected.extend(provider_pages)
            continue
        partition = target["required_safe_partition"]
        partition_pages = partition.get("pages") or []
        if not isinstance(partition_pages, list) or not partition_pages:
            projected.extend(provider_pages)
            continue
        for index, required in enumerate(partition_pages):
            if not isinstance(required, dict):
                continue
            provider_page = (
                provider_pages[index]
                if index < len(provider_pages)
                else {}
            )
            source_block_ids = [
                str(block_id)
                for block_id in required.get("source_block_ids") or []
                if str(block_id)
            ]
            allowed_layout_ids = [
                str(layout_id)
                for layout_id in required.get("template_layout_ids") or []
                if str(layout_id)
            ]
            selected_layout_id = str(
                provider_page.get("template_layout_id") or ""
            )
            if selected_layout_id not in allowed_layout_ids:
                selected_layout_id = allowed_layout_ids[0] if allowed_layout_ids else ""
            title_candidates = _request_title_candidates_for_blocks(
                unit,
                source_block_ids,
            )
            selected_title = str(provider_page.get("title") or "").strip()
            if selected_title not in title_candidates and title_candidates:
                selected_title = title_candidates[0]
            selected_page_id = str(provider_page.get("page_id") or "").strip()
            if not selected_page_id or selected_page_id in used_page_ids:
                selected_page_id = stable_hash(
                    {
                        "chapter_id": chapter_id,
                        "teaching_unit_id": unit_id,
                        "partition_id": partition.get("partition_id"),
                        "page_index": index,
                    },
                    prefix="v6repair_",
                )
            used_page_ids.add(selected_page_id)
            provider_source_ids = [
                str(block_id)
                for block_id in provider_page.get("source_block_ids") or []
            ]
            projected.append({
                "page_id": selected_page_id,
                "teaching_unit_id": unit_id,
                "template_layout_id": selected_layout_id,
                "title": selected_title,
                "summary": (
                    str(provider_page.get("summary") or "")
                    if provider_source_ids == source_block_ids
                    else ""
                ),
                "source_block_ids": source_block_ids,
            })
    projected.extend(unscoped_pages)
    return projected


def _normalize_story_batch_response(
    raw: dict[str, Any],
    request: dict[str, Any],
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
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
    graph_units = {
        unit.teaching_unit_id: unit
        for unit in graph.units
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
    pages = _project_required_safe_partitions(
        pages,
        units,
        repair_targets,
        chapter_id=str(request.get("chapter_id") or ""),
    )

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
            if artifacts and not artifacts.issubset(
                set(layout.get("artifact_kinds") or [])
            ):
                continue
            source_decisions = set(_allowed_visual_decisions(
                artifacts,
                list(unit.get("source_asset_ids") or []),
            ))
            if (
                _layout_requires_artifact_decision(layout)
                and not source_decisions.intersection(
                    set(layout.get("artifact_kinds") or [])
                )
            ):
                continue
            if roles and not artifacts:
                remaining_roles = list(roles)
                required_text_slots = [
                    slot
                    for slot in layout.get("slots") or []
                    if isinstance(slot, dict)
                    and bool(slot.get("required"))
                    and slot.get("slot_kind") in {"body", "items", "steps"}
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
            graph_unit = graph_units.get(
                str(unit.get("teaching_unit_id") or "")
            )
            layout_contract = template.get_layout(layout_id)
            if graph_unit is None or layout_contract is None:
                continue
            try:
                validate_story_template_text_slots(
                    page_id=str(page.get("page_id") or "story-preflight"),
                    layout=layout_contract,
                    source_blocks=graph_page_source_blocks(
                        graph_unit,
                        source_ids,
                    ),
                    story_summary=str(page.get("summary") or ""),
                    enforce_min_chars=False,
                )
            except V6BuildError:
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
            page_layout_ids = allowed_layout_ids_for_page(unit, page)
            if (
                template.get_layout(selected_layout_id) is not None
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
            required_summary = str(
                repair_target.get("required_summary") or ""
            ).strip()
            if required_title:
                page["title"] = required_title
            if required_layout_id:
                page["template_layout_id"] = required_layout_id
            if required_summary:
                page["summary"] = required_summary
        normalized_title = re.sub(
            r"\s+",
            "",
            str(page.get("title") or ""),
        ).casefold()
        if unit is not None and normalized_title in used_titles:
            replacement = next(
                (
                    str(candidate)
                    for candidate in _request_title_candidates_for_blocks(
                        unit,
                        [
                            str(block_id)
                            for block_id in page.get("source_block_ids") or []
                        ],
                    )
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
            decision["source_block_ids"] = list(
                page.get("source_block_ids") or []
            )
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
    source_asset_ids: list[str],
    template: TemplateLayoutPackContractV1,
    *,
    teaching_unit_id: str,
) -> list[str]:
    result = []
    source_decisions = set(_allowed_visual_decisions(
        required_artifacts,
        source_asset_ids,
    ))
    for layout in template.layouts:
        if teaching_intent not in layout.teaching_intents:
            continue
        if required_artifacts and not required_artifacts.intersection(layout.artifact_kinds):
            continue
        if (
            _layout_requires_artifact_decision(layout)
            and not source_decisions.intersection(set(layout.artifact_kinds))
        ):
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

    def add_candidate(value: str) -> None:
        candidate = " ".join(str(value or "").split()).strip("#*` ，。！？,;:|")
        if (
            4 <= len(candidate) <= capacity
            and candidate in source_text
            and not _title_is_incomplete(candidate)
            and candidate not in candidates
        ):
            candidates.append(candidate)

    def add_complete_fragments(value: str) -> None:
        clean = " ".join(str(value or "").split()).strip("#*` ")
        if not clean:
            return
        if len(clean) <= capacity:
            add_candidate(clean)
            return
        fragments = re.split(
            r"(?:[，。！？；;：:｜|]|\s+[—–-]\s+|与|及|和|"
            r"\s+(?:and|or|versus|vs\.?)\s+)",
            clean,
            flags=re.IGNORECASE,
        )
        for fragment in fragments:
            stripped = fragment.strip()
            if len(stripped) <= capacity:
                add_candidate(stripped)
                continue
            if re.search(r"\s", stripped):
                words: list[str] = []
                for word in stripped.split():
                    candidate = " ".join([*words, word])
                    if len(candidate) > capacity:
                        break
                    words.append(word)
                add_candidate(" ".join(words))

    for match in _MARKDOWN_TITLE_RE.finditer(source_text):
        full_title = str(match.group(1) or match.group(2) or "").strip()
        specific_title = re.split(r"[：:]", full_title, maxsplit=1)[-1].strip()
        add_complete_fragments(specific_title)
    heading_lines = {
        match.group(0).strip()
        for match in _MARKDOWN_TITLE_RE.finditer(source_text)
    }
    for raw_segment in re.split(r"[\n。！？!?；;]", source_text):
        if raw_segment.strip() in heading_lines:
            continue
        add_complete_fragments(raw_segment)
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
            unit.source_asset_refs,
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
    summary_max_chars_by_layout_id = {}
    summary_min_chars_by_layout_id = {}
    for layout in allowed_layouts:
        body_slots = [
            slot
            for slot in layout["slots"]
            if slot.get("slot_kind") == "body"
        ]
        summary_max_chars_by_layout_id[layout["template_layout_id"]] = (
            int(body_slots[0].get("max_chars") or 0)
            if len(body_slots) == 1
            else 0
        )
        summary_min_chars_by_layout_id[layout["template_layout_id"]] = (
            int(body_slots[0].get("min_chars") or 0)
            if len(body_slots) == 1
            else 0
        )
    safe_page_slices = story_safe_page_slices(unit, template)
    allowed_page_count_range = story_page_count_range(unit, template)
    safe_partition_options = story_safe_partition_options(unit, template)

    def block_compatible_layout_ids(block_id: str) -> list[str]:
        block_intent = page_teaching_intent(unit, [block_id])
        block_artifacts = set(
            unit.primary_block_artifacts.get(block_id, [])
        )
        required_slot_kinds = source_required_slot_kinds(
            graph_page_source_blocks(unit, [block_id])
        )
        candidates = allowed_layout_ids_by_page_intent.get(block_intent, [])
        return [
            layout_id
            for layout_id in candidates
            if (
                (layout := template.get_layout(layout_id)) is not None
                and (
                    not block_artifacts
                    or block_artifacts.issubset(set(layout.artifact_kinds))
                )
                and required_slot_kinds.issubset(
                    {slot.slot_kind for slot in layout.slots}
                )
            )
        ]

    return {
        "teaching_unit_id": unit.teaching_unit_id,
        "source_ordinal": unit.source_ordinal,
        "primary_block_ids": unit.primary_block_ids,
        "primary_blocks": [
            {
                "block_id": block_id,
                "role": unit.primary_block_roles.get(block_id, ""),
                "artifact_kinds": unit.primary_block_artifacts.get(block_id, []),
                "required_slot_kinds": sorted(source_required_slot_kinds(
                    graph_page_source_blocks(unit, [block_id])
                )),
                "page_intent": page_teaching_intent(unit, [block_id]),
                "source_text": unit.primary_block_texts.get(block_id, ""),
                "allowed_protected_tokens": sorted(_protected_tokens(
                    unit.primary_block_texts.get(block_id, "")
                )),
                "title_candidates": _grounded_title_candidates(
                    unit.primary_block_texts.get(block_id, ""),
                    max_chars=title_max_chars,
                ),
                "compatible_template_layout_ids": (
                    block_compatible_layout_ids(block_id)
                ),
            }
            for block_id in unit.primary_block_ids
        ],
        "teaching_intent": unit.teaching_intent,
        "artifact_kinds": unit.artifact_kinds,
        "source_asset_ids": unit.source_asset_refs,
        "teaching_plan_context": unit.teaching_plan_context,
        "prerequisite_unit_ids": unit.prerequisite_unit_ids,
        "source_text": unit.source_text,
        "allowed_protected_tokens": sorted(_protected_tokens(unit.source_text)),
        "title_max_chars": title_max_chars,
        "title_policy": (
            "copy_a_complete_specific_candidate_grounded_in_bound_blocks"
        ),
        "title_candidates": _grounded_title_candidates(
            unit.source_text,
            max_chars=title_max_chars,
        ),
        "summary_max_chars_by_layout_id": summary_max_chars_by_layout_id,
        "summary_min_chars_by_layout_id": summary_min_chars_by_layout_id,
        "allowed_page_count_range": allowed_page_count_range,
        "safe_page_slices": safe_page_slices,
        "safe_partition_options": safe_partition_options,
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
                "summary_policy": (
                    "source_grounded_semantic_closure_for_all_bound_blocks_"
                    "complete_sentence_no_markdown"
                ),
                "page_count_policy": (
                    "use_each_teaching_unit_allowed_page_count_range"
                ),
                "allow_new_facts": False,
                "allow_unknown_ids": False,
                "protected_token_policy": (
                    "copy_identifiers_and_numbers_exactly_from_each_unit_or_"
                    "bound_block_allowed_protected_tokens"
                ),
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
        repartition_required = error.failure.code in {
            "template_layout_artifact_mismatch",
            "template_layout_intent_mismatch",
            "template_layout_semantic_slot_mismatch",
        }
        observed_unit_pages = [
            page
            for page in pages
            if isinstance(page, dict)
            and str(page.get("teaching_unit_id") or "") == unit_id
        ]
        replaced_page_ids = {
            str(page.get("page_id") or "")
            for page in observed_unit_pages
            if str(page.get("page_id") or "")
        } if repartition_required else set()
        current_title = str((current_page or {}).get("title") or "")
        current_summary = str((current_page or {}).get("summary") or "")
        normalized_current_title = re.sub(r"\s+", "", current_title).casefold()
        conflicting_page_ids = [
            str(page.get("page_id") or "")
            for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") != page_id
            and str(page.get("page_id") or "") not in replaced_page_ids
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
                and str(page.get("page_id") or "") not in replaced_page_ids
                and str(page.get("title") or "").strip()
            ),
        ]))
        normalized_forbidden_titles = {
            re.sub(r"\s+", "", title).casefold()
            for title in forbidden_titles
        }
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
        allowed_title_candidates = _request_title_candidates_for_blocks(
            unit,
            current_source_block_ids,
        )
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
        layout_artifact_kinds_by_id = {
            str(layout.get("template_layout_id") or ""): {
                str(artifact)
                for artifact in layout.get("artifact_kinds") or []
                if str(artifact)
            }
            for layout in unit.get("allowed_template_layouts") or []
            if isinstance(layout, dict)
            and str(layout.get("template_layout_id") or "")
        }
        current_layout_id = str(
            (current_page or {}).get("template_layout_id") or ""
        )
        current_layout_artifacts = layout_artifact_kinds_by_id.get(
            current_layout_id,
            set(),
        )
        artifact_source_block_ids_by_kind = {
            artifact: [
                block_id
                for block_id in current_source_block_ids
                if artifact in set(
                    block_metadata.get(block_id, {}).get("artifact_kinds") or []
                )
            ]
            for artifact in sorted(current_artifacts)
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
        artifact_layout_ids_by_kind: dict[str, list[str]] = defaultdict(list)
        for layout in unit.get("allowed_template_layouts") or []:
            if not isinstance(layout, dict):
                continue
            layout_id = str(layout.get("template_layout_id") or "")
            if not layout_id:
                continue
            for artifact_kind in layout.get("artifact_kinds") or []:
                artifact = str(artifact_kind or "")
                if artifact and layout_id not in artifact_layout_ids_by_kind[artifact]:
                    artifact_layout_ids_by_kind[artifact].append(layout_id)
        title_repair_required = error.failure.code in {
            "duplicate_slide_title",
            "story_title_capacity_exceeded",
            "story_unsupported_title",
            "story_title_incomplete",
            "story_title_lacks_specificity",
        }
        summary_min_chars = int(
            (unit.get("summary_min_chars_by_layout_id") or {}).get(
                current_layout_id,
                0,
            )
            or 0
        )
        summary_max_chars = int(
            (unit.get("summary_max_chars_by_layout_id") or {}).get(
                current_layout_id,
                0,
            )
            or 0
        )
        summary_repair_required = error.failure.code in {
            "story_page_underfilled",
            "story_summary_capacity_exceeded",
            "story_summary_markdown_invalid",
            "story_unsupported_fact",
            "story_unsupported_semantic_claim",
        }
        allowed_protected_tokens = sorted({
            str(token)
            for block_id in current_source_block_ids
            for token in block_metadata.get(block_id, {}).get(
                "allowed_protected_tokens",
                [],
            )
            if str(token)
        })
        unsupported_protected_tokens = sorted(
            _protected_tokens(current_summary) - set(allowed_protected_tokens)
        )
        required_summary = ""
        if summary_repair_required and (summary_min_chars or summary_max_chars):
            grounded_source = _visible_prose_text("\n\n".join(
                str(block_metadata.get(block_id, {}).get("source_text") or "")
                for block_id in current_source_block_ids
            ))
            effective_max = summary_max_chars or len(grounded_source)
            preferred_max = min(
                effective_max,
                max(summary_min_chars, summary_min_chars + 80),
            )
            required_summary = (
                grounded_source
                if len(grounded_source) <= preferred_max
                else _complete_sentence_excerpt(grounded_source, preferred_max)
            )
            if len(required_summary) < min(summary_min_chars, len(grounded_source)):
                expanded = _complete_sentence_excerpt(grounded_source, effective_max)
                required_summary = expanded
                if required_summary and required_summary[-1] not in "。！？.!?":
                    if len(required_summary) < preferred_max:
                        required_summary += "。"
        safe_partition_options = [
            option
            for option in unit.get("safe_partition_options") or []
            if isinstance(option, dict)
            and isinstance(option.get("pages"), list)
            and option.get("pages")
        ]
        observed_page_count = len(observed_unit_pages)
        observed_source_ids = [
            str(block_id)
            for page in observed_unit_pages
            for block_id in page.get("source_block_ids") or []
        ]
        expected_source_ids = [
            str(block_id) for block_id in unit.get("primary_block_ids") or []
        ]
        source_coverage_verified = (
            Counter(observed_source_ids) == Counter(expected_source_ids)
        )
        required_safe_partition = (
            min(
                enumerate(safe_partition_options),
                key=lambda indexed_option: (
                    abs(
                        int(indexed_option[1].get("page_count") or 0)
                        - observed_page_count
                    ),
                    int(indexed_option[1].get("page_count") or 0),
                    indexed_option[0],
                ),
            )[1]
            if (
                repartition_required
                and source_coverage_verified
                and safe_partition_options
            )
            else {}
        )
        return {
            "page_id": page_id,
            "teaching_unit_id": unit_id,
            "allowed_page_count_range": list(
                unit.get("allowed_page_count_range") or [1, 3]
            ),
            "safe_page_slices": list(unit.get("safe_page_slices") or []),
            "safe_partition_options": list(
                unit.get("safe_partition_options") or []
            ),
            "required_safe_partition": required_safe_partition,
            "source_coverage_verified": source_coverage_verified,
            "observed_unit_page_ids": [
                str(page.get("page_id") or "")
                for page in observed_unit_pages
                if str(page.get("page_id") or "")
            ],
            "repartition_required": repartition_required,
            "repartition_scope": (
                "teaching_unit" if repartition_required else "page"
            ),
            "source_block_order": list(unit.get("primary_block_ids") or []),
            "replace_page_ids": [
                str(page.get("page_id") or "")
                for page in observed_unit_pages
                if str(page.get("page_id") or "")
            ] if repartition_required else [],
            "current_partition": [
                {
                    "page_id": str(page.get("page_id") or ""),
                    "template_layout_id": str(
                        page.get("template_layout_id") or ""
                    ),
                    "source_block_ids": [
                        str(block_id)
                        for block_id in page.get("source_block_ids") or []
                    ],
                }
                for page in observed_unit_pages
            ],
            "allowed_template_layout_ids_by_page_intent": dict(
                unit.get("allowed_template_layout_ids_by_page_intent") or {}
            ),
            "artifact_layout_ids_by_kind": dict(artifact_layout_ids_by_kind),
            "primary_blocks": list(unit.get("primary_blocks") or []),
            "page_intent": page_intent,
            "allowed_template_layout_ids": page_allowed_layout_ids,
            "required_template_layout_id": (
                current_layout_id if summary_repair_required else ""
            ),
            "required_artifact_kinds": sorted(current_artifacts),
            "current_layout_artifact_kinds": sorted(current_layout_artifacts),
            "missing_artifact_kinds": sorted(
                current_artifacts - current_layout_artifacts
            ),
            "artifact_source_block_ids_by_kind": (
                artifact_source_block_ids_by_kind
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
            "allowed_protected_tokens": allowed_protected_tokens,
            "unsupported_protected_tokens": unsupported_protected_tokens,
            "summary_min_chars": summary_min_chars,
            "summary_max_chars": summary_max_chars,
            "required_summary": required_summary,
            "summary_policy": (
                "source_grounded_semantic_closure_for_all_bound_blocks_"
                "complete_sentence_no_markdown"
            ),
        }

    if error.failure.code == "story_page_underfilled":
        underfilled_targets: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            unit = units.get(str(page.get("teaching_unit_id") or ""))
            if not page_id or unit is None:
                continue
            target = target_for(unit, page_id=page_id)
            minimum = int(target.get("summary_min_chars") or 0)
            current = _visible_prose_text(str(page.get("summary") or ""))
            if minimum and len(current) < minimum and target.get("required_summary"):
                underfilled_targets.append(target)
        if underfilled_targets:
            return underfilled_targets

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


def _story_request_page_intent(
    unit: dict[str, Any],
    source_block_ids: list[str],
) -> str:
    block_metadata = {
        str(block.get("block_id") or ""): block
        for block in unit.get("primary_blocks") or []
        if isinstance(block, dict)
    }
    roles = [
        str(block_metadata.get(block_id, {}).get("role") or "")
        for block_id in source_block_ids
        if str(block_metadata.get(block_id, {}).get("role") or "")
    ]
    artifacts = {
        str(artifact)
        for block_id in source_block_ids
        for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
        if str(artifact)
    }
    return (
        teaching_intent_for_roles(roles, artifacts)
        if roles or artifacts
        else str(unit.get("teaching_intent") or "")
    )


def _coalesce_oversplit_story_unit(
    response_payload: dict[str, Any],
    request: dict[str, Any],
    error: V6BuildError,
) -> dict[str, Any]:
    """Deterministically cap one coherent unit without rewriting its batch."""

    if error.failure.code != "teaching_unit_page_limit_exceeded":
        return response_payload
    pages = response_payload.get("pages")
    if not isinstance(pages, list):
        return response_payload
    failed_page = next(
        (
            page for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") == str(error.failure.page_id or "")
        ),
        None,
    )
    if failed_page is None:
        return response_payload
    unit_id = str(failed_page.get("teaching_unit_id") or "")
    unit = next(
        (
            item for item in request.get("teaching_units") or []
            if isinstance(item, dict)
            and str(item.get("teaching_unit_id") or "") == unit_id
        ),
        None,
    )
    unit_pages = [
        page for page in pages
        if isinstance(page, dict)
        and str(page.get("teaching_unit_id") or "") == unit_id
    ]
    page_count_range = (
        list(unit.get("allowed_page_count_range") or [1, 3])
        if unit is not None
        else [1, 3]
    )
    maximum_pages = int(page_count_range[-1])
    if unit is None or len(unit_pages) <= maximum_pages:
        return response_payload

    primary_ids = [
        str(block_id) for block_id in unit.get("primary_block_ids") or []
    ]
    seen: set[str] = set()
    owner_pages: list[dict[str, Any]] = []
    for page in unit_pages:
        page_ids = {
            str(block_id) for block_id in page.get("source_block_ids") or []
        }
        fresh_ids = [
            block_id for block_id in primary_ids
            if block_id in page_ids and block_id not in seen
        ]
        if fresh_ids:
            owner_pages.append(page)
            seen.update(fresh_ids)
    observed_ids = [block_id for block_id in primary_ids if block_id in seen]
    if not observed_ids or not owner_pages:
        return response_payload

    target_count = min(maximum_pages, len(owner_pages), len(observed_ids))
    base_size, remainder = divmod(len(observed_ids), target_count)
    chunks: list[list[str]] = []
    cursor = 0
    for index in range(target_count):
        size = base_size + (1 if index < remainder else 0)
        chunks.append(observed_ids[cursor:cursor + size])
        cursor += size

    replacements: list[dict[str, Any]] = []
    used_titles = {
        re.sub(r"\s+", "", str(page.get("title") or "")).casefold()
        for page in pages
        if isinstance(page, dict)
        and str(page.get("teaching_unit_id") or "") != unit_id
        and str(page.get("title") or "").strip()
    }
    for index, source_ids in enumerate(chunks):
        page = dict(owner_pages[index])
        page["source_block_ids"] = source_ids
        page["summary"] = ""
        replacement_title = next(
            (
                candidate
                for candidate in _request_title_candidates_for_blocks(
                    unit,
                    source_ids,
                )
                if re.sub(r"\s+", "", candidate).casefold() not in used_titles
            ),
            "",
        )
        if replacement_title:
            page["title"] = replacement_title
            used_titles.add(
                re.sub(r"\s+", "", replacement_title).casefold()
            )
        page_intent = _story_request_page_intent(unit, source_ids)
        allowed_layout_ids = list(
            (unit.get("allowed_template_layout_ids_by_page_intent") or {}).get(
                page_intent,
                unit.get("allowed_template_layout_ids") or [],
            )
        )
        if (
            allowed_layout_ids
            and str(page.get("template_layout_id") or "") not in allowed_layout_ids
        ):
            page["template_layout_id"] = str(allowed_layout_ids[0])
        replacements.append(page)

    rebuilt_pages: list[Any] = []
    emitted = False
    for page in pages:
        if (
            isinstance(page, dict)
            and str(page.get("teaching_unit_id") or "") == unit_id
        ):
            if not emitted:
                rebuilt_pages.extend(replacements)
                emitted = True
            continue
        rebuilt_pages.append(page)
    return {**response_payload, "pages": rebuilt_pages}


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
                                "unit's primary_block_ids by choosing exactly one complete entry from "
                                "that unit's safe_partition_options. Copy every option page's "
                                "source_block_ids exactly and choose one of its template_layout_ids: bind multiple "
                                "related block IDs to the same page instead of creating one page per "
                                "block. Full source remains available in speaker notes downstream. "
                                "Copy each title verbatim from that unit's title_candidates and keep "
                                "it within that unit's title_max_chars. Titles must name the bound "
                                "page's specific teaching subject and must not end with a connector, "
                                "delimiter, or incomplete phrase. Prefer candidates supplied on the "
                                "bound primary_blocks. Set "
                                "a repair target's title exactly to required_title when provided. Set "
                                "its template_layout_id exactly to required_template_layout_id when "
                                "provided. When a repair target has repartition_required=true, "
                                "replace every page listed in replace_page_ids with a fresh LLM-authored "
                                "partition of source_block_order by choosing exactly one complete entry from "
                                "safe_partition_options. Copy its page source_block_ids exactly and select one "
                                "listed template_layout_id per page. Do not retain "
                                "the failed source grouping. Each new page must bind a non-empty contiguous "
                                "slice of source_block_order, preserve the complete order exactly once, and "
                                "select its layout from allowed_template_layout_ids_by_page_intent. If a "
                                "repair target supplies required_safe_partition, copy that partition's pages "
                                "exactly, including every source_block_ids list, and choose each layout only "
                                "from that page's template_layout_ids. "
                                "If a "
                                "page contains any primary block with artifact_kinds, its layout must also "
                                "appear in that block's compatible_template_layout_ids. The union of "
                                "artifact_kinds for all blocks bound to a page must be a subset of the "
                                "selected layout's artifact kinds. Use required_artifact_kinds, "
                                "current_layout_artifact_kinds, missing_artifact_kinds, and "
                                "artifact_source_block_ids_by_kind to repair the failed grouping. If no "
                                "single layout appears in artifact_layout_ids_by_kind for every required "
                                "artifact, split those source blocks across separate pages. Never assign "
                                "an artifact-bearing page to a text-only layout. The "
                                "validator will reject the result instead of generating replacement story "
                                "pages. Set "
                                    "summary to one complete, Markdown-free, source-grounded sentence "
                                "that expresses the semantic closure of every bound source_block_id "
                                "whose length remains between summary_min_chars_by_layout_id and "
                                "summary_max_chars_by_layout_id for the selected layout when the frozen "
                                    "source is long enough. Use an empty summary only when the maximum is zero or "
                                    "no faithful synthesis is possible; never add identifiers or facts. Copy "
                                    "identifiers and numbers only from allowed_protected_tokens and preserve "
                                    "their exact spelling; remove every unsupported_protected_token rather "
                                    "than abbreviating or autocorrecting it. Set a "
                                    "repair target's summary exactly to required_summary when provided."
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
                        graph,
                        template,
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
                    try:
                        _validate_story_batch_candidate(
                            graph=graph,
                            template=template,
                            request=request,
                            batch=candidate_batch,
                        )
                    except V6BuildError as validation_error:
                        repaired_payload = _coalesce_oversplit_story_unit(
                            previous_response_payload,
                            request,
                            validation_error,
                        )
                        if repaired_payload is previous_response_payload:
                            raise
                        previous_response_payload = repaired_payload
                        response = _StoryBatchResponse.model_validate(
                            previous_response_payload
                        )
                        local_pages = [
                            SlideStoryPageV3(
                                **item.model_dump(mode="json"),
                                page_ordinal=index,
                            )
                            for index, item in enumerate(response.pages)
                        ]
                        candidate_batch = candidate_batch.model_copy(
                            update={"pages": local_pages}
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
    def page_source_blocks(page: SlideStoryPageV3) -> list[dict[str, str]]:
        unit = units[page.teaching_unit_id]
        blocks = [
            {
                "block_id": block_id,
                "source_text": str(unit.primary_block_texts.get(block_id) or "").strip(),
            }
            for block_id in page.source_block_ids
        ]
        if len(blocks) == 1 and not blocks[0]["source_text"]:
            blocks[0]["source_text"] = unit.source_text
        return blocks

    def page_request(page: SlideStoryPageV3) -> dict[str, Any]:
        unit = units[page.teaching_unit_id]
        layout = template.get_layout(page.template_layout_id)
        if layout is None:
            raise V6BuildError(
                stage="template",
                code="template_layout_unavailable",
                message="Visual planning requires a published template layout",
                page_id=page.page_id,
            )
        source_blocks = page_source_blocks(page)
        artifact_kinds = page_artifact_kinds(unit, page.source_block_ids)
        source_decisions = _allowed_visual_decisions(
            artifact_kinds,
            unit.source_asset_refs,
        )
        layout_requires_artifact = _layout_requires_artifact_decision(layout)
        allowed_decisions = _decisions_allowed_by_layout(
            source_decisions,
            layout_artifact_kinds=set(layout.artifact_kinds),
            layout_requires_artifact=layout_requires_artifact,
        )
        if not allowed_decisions:
            raise V6BuildError(
                stage="template",
                code="template_layout_unavailable",
                message="Template layout has no source-supported visual decision",
                page_id=page.page_id,
            )
        return {
            "page_id": page.page_id,
            "teaching_unit_id": page.teaching_unit_id,
            "template_layout_id": page.template_layout_id,
            "source_block_ids": page.source_block_ids,
            "source_text": "\n\n".join(
                block["source_text"] for block in source_blocks
                if block["source_text"]
            ) or unit.source_text,
            "source_blocks": source_blocks,
            "artifact_kinds": sorted(artifact_kinds),
            "layout_artifact_kinds": list(layout.artifact_kinds),
            "layout_requires_artifact": layout_requires_artifact,
            "allowed_decisions": allowed_decisions,
            "source_asset_ids": unit.source_asset_refs,
        }

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
            "diagram_node_fields": ["node_id", "label", "source_block_ids"],
        },
        "pages": [page_request(page) for page in batch.pages],
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


def _layout_requires_artifact_decision(layout: Any) -> bool:
    slots = layout.slots if hasattr(layout, "slots") else layout.get("slots") or []
    return any(
        (slot.required if hasattr(slot, "required") else bool(slot.get("required")))
        and (
            slot.slot_kind if hasattr(slot, "slot_kind") else str(slot.get("slot_kind") or "")
        ) in {"code", "formula", "table", "visual"}
        for slot in slots
    )


def _decisions_allowed_by_layout(
    source_decisions: list[str],
    *,
    layout_artifact_kinds: set[str],
    layout_requires_artifact: bool,
) -> list[str]:
    if not layout_requires_artifact:
        return list(source_decisions)
    return [
        decision for decision in source_decisions
        if decision in layout_artifact_kinds
    ]


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
    decisions: list[SlideVisualDecisionV2] | None = None,
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
    decisions_by_page = {
        decision.page_id: decision for decision in (decisions or [])
    }
    targets: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page.get("page_id") or "")
        decision = decisions_by_page.get(page_id)
        failed_node_id = (
            str(getattr(error, "node_id", "") or "")
            if isinstance(error, V6BuildError)
            else ""
        )
        nodes = (
            decision.visual_payload.get("nodes") or []
            if decision is not None
            else []
        )
        targets.append({
            "page_id": page_id,
            "required_artifact_kinds": list(page.get("artifact_kinds") or []),
            "allowed_decisions": list(page.get("allowed_decisions") or []),
            "required_source_block_ids": list(page.get("source_block_ids") or []),
            "required_template_layout_id": str(page.get("template_layout_id") or ""),
            "allowed_source_asset_ids": list(page.get("source_asset_ids") or []),
            "source_blocks": list(page.get("source_blocks") or []),
            "failed_node_ids": [failed_node_id] if failed_node_id else [],
            "locked_nodes": [
                node for node in nodes
                if isinstance(node, dict)
                and str(node.get("node_id") or "") != failed_node_id
            ] if failed_node_id else [],
        })
    return targets


def _merge_visual_repair_decisions(
    previous: list[SlideVisualDecisionV2],
    repaired: list[SlideVisualDecisionV2],
    error: Exception | None,
) -> list[SlideVisualDecisionV2]:
    repaired_by_page = {decision.page_id: decision for decision in repaired}
    failed_page_id = (
        str(error.failure.page_id or "")
        if isinstance(error, V6BuildError)
        else ""
    )
    failed_node_id = (
        str(getattr(error, "node_id", "") or "")
        if isinstance(error, V6BuildError)
        else ""
    )
    merged: list[SlideVisualDecisionV2] = []
    for prior in previous:
        replacement = repaired_by_page.get(prior.page_id)
        if replacement is None:
            merged.append(prior)
            continue
        if (
            prior.page_id == failed_page_id
            and failed_node_id
            and prior.decision == "diagram"
            and replacement.decision == "diagram"
        ):
            replacement_nodes = {
                str(node.get("node_id") or ""): node
                for node in replacement.visual_payload.get("nodes") or []
                if isinstance(node, dict)
            }
            prior_payload = dict(prior.visual_payload)
            prior_payload["nodes"] = [
                replacement_nodes[failed_node_id]
                if isinstance(node, dict)
                and str(node.get("node_id") or "") == failed_node_id
                and failed_node_id in replacement_nodes
                else node
                for node in prior.visual_payload.get("nodes") or []
            ]
            merged.append(prior.model_copy(update={
                "visual_payload": prior_payload,
                "provider": replacement.provider or prior.provider,
                "model": replacement.model or prior.model,
                "duration_ms": max(prior.duration_ms, replacement.duration_ms),
                "attempts": max(prior.attempts, replacement.attempts),
            }))
            continue
        merged.append(replacement)
    return merged


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
            previous_decisions: list[SlideVisualDecisionV2] = []
            for validation_attempt in range(_VISUAL_SEMANTIC_MAX_ATTEMPTS):
                attempt_request = request
                if validation_attempt:
                    repair_targets = _visual_repair_targets(
                        request,
                        contract_error,
                        previous_decisions,
                    )
                    repair_page_ids = {
                        str(target.get("page_id") or "") for target in repair_targets
                    }
                    attempt_request = {
                        **request,
                        "pages": [
                            page for page in request.get("pages") or []
                            if str(page.get("page_id") or "") in repair_page_ids
                        ] or list(request.get("pages") or []),
                        "repair_feedback": {
                            "attempt": validation_attempt + 1,
                            "code": (
                                contract_error.failure.code
                                if isinstance(contract_error, V6BuildError)
                                else "visual_response_contract_invalid"
                            ),
                            "message": str(contract_error or ""),
                            "repair_targets": repair_targets,
                            "instruction": (
                                "Return decisions only for the pages in this repair request. For a "
                                "failed diagram node, keep its node_id, bind it only to supplied "
                                "source_blocks, prefer an extractive short label, preserve every "
                                "locked_node unchanged, and keep exact numbers and code identifiers. "
                                "Choose only an allowed_decision and never invent artifact payloads."
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
                    if validation_attempt and previous_decisions:
                        decisions = _merge_visual_repair_decisions(
                            previous_decisions,
                            decisions,
                            contract_error,
                        )
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
                    if "decisions" in locals():
                        previous_decisions = decisions
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
            required_page_ids = {page.page_id for page in required_pages}
            degraded_soft_failure = False
            first_failure_category = (
                error.failure.code
                if isinstance(error, V6BuildError)
                else "visual_ai_batch_failed"
            )
            if isinstance(error, V6BuildError) and previous_decisions:
                fallback_by_page = {
                    decision.page_id: decision
                    for decision in previous_decisions
                }
                fallback_error: V6BuildError = error
                for _ in range(len(batch.pages)):
                    failed_page_id = str(fallback_error.failure.page_id or "")
                    if (
                        not failed_page_id
                        or failed_page_id in required_page_ids
                        or failed_page_id not in fallback_by_page
                    ):
                        break
                    failed_page = next(
                        (
                            page for page in batch.pages
                            if page.page_id == failed_page_id
                        ),
                        None,
                    )
                    if failed_page is None:
                        break
                    fallback_by_page[failed_page_id] = SlideVisualDecisionV2(
                        page_id=failed_page.page_id,
                        decision="text_native",
                        source_block_ids=failed_page.source_block_ids,
                        resolved_template_layout_id=failed_page.template_layout_id,
                        degraded=True,
                        degradation_reason=fallback_error.failure.code,
                        duration_ms=max(
                            0,
                            round((time.perf_counter() - started) * 1000),
                        ),
                    )
                    fallback_decisions = [
                        fallback_by_page[page.page_id]
                        for page in batch.pages
                        if page.page_id in fallback_by_page
                    ]
                    try:
                        _validate_visual_batch_candidate(
                            story=story,
                            graph=graph,
                            template=template,
                            batch=batch,
                            decisions=fallback_decisions,
                        )
                    except V6BuildError as next_error:
                        fallback_error = next_error
                        continue
                    decisions = fallback_decisions
                    batch_validation_status = "degraded"
                    batch_failure_category = first_failure_category
                    degraded_soft_failure = True
                    break
                if not degraded_soft_failure:
                    error = fallback_error
            if required_pages and not degraded_soft_failure:
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
            if not degraded_soft_failure:
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
                "For each teaching unit, choose exactly one complete safe_partition_options entry. "
                "Copy each option page's source_block_ids exactly and choose one of that page's listed "
                "template_layout_ids. Do not create "
                "one page per primary block: partition the unit's block IDs across its pages and "
                "bind multiple related blocks to one page when needed. The downstream compiler "
                "keeps complete source text in speaker notes, so canvas pages should express a "
                "semantically closed teaching step rather than repeat all source prose. Titles, "
                "summaries, transitions, facts, numbers, formulas and identifiers must be supported "
                "by that unit's source_text. Copy every identifier and number exactly from the "
                "allowed_protected_tokens of its bound primary_blocks; never shorten, approximate, "
                "autocorrect or synthesize a protected token. Every page must contain exactly page_id, "
                "teaching_unit_id, template_layout_id, title, summary and source_block_ids at the "
                 "page level; never emit a nested content object. Copy a complete title from candidates "
                 "supplied by the primary_blocks bound to that page, keep it within title_max_chars, "
                 "and never end it with a connector or delimiter. A non-empty summary must express the semantic closure of every "
                 "source_block_id bound to that page. Never invent teaching content."
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
                "two to six source-grounded nodes, source_block_ids per node, and valid edges. Bind "
                "each node only to page source_blocks that support it. Prefer short labels extracted "
                "from those blocks; faithful paraphrases must retain a source term, while numbers and "
                "code identifiers must remain exact. During repair, change only failed_node_ids and "
                "preserve locked_nodes. For "
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
