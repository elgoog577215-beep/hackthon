"""Strict AI story and visual planning for slide-deck V6.

Story planning has no deterministic publication fallback. Visual planning may
degrade only pages that do not carry a required characteristic artifact.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_base import AIBase
from course_presentation_graph import CoursePresentationGraphV1, CoursePresentationUnitV1
from slide_deck_v6 import (
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


def _failure_category(error: BaseException, *, prefix: str) -> tuple[str, bool]:
    message = str(error).lower()
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)) or "timeout" in message:
        return f"{prefix}_timeout", True
    if any(token in message for token in ("401", "403", "authentication", "api key")):
        return f"{prefix}_authentication", False
    if any(token in message for token in ("429", "rate limit", "too many requests")):
        return f"{prefix}_rate_limited", True
    if any(token in message for token in ("balance", "quota", "credit")):
        return f"{prefix}_balance_unavailable", False
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


def _allowed_layout_ids(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
) -> list[str]:
    required_artifacts = set(unit.artifact_kinds)
    result = []
    for layout in template.layouts:
        if unit.teaching_intent not in layout.teaching_intents:
            continue
        if required_artifacts and not required_artifacts.intersection(layout.artifact_kinds):
            continue
        result.append(layout.template_layout_id)
    if not result:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=f"No template layout supports teaching unit {unit.teaching_unit_id}",
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
                "pages_per_unit": [1, 3],
                "allow_new_facts": False,
                "allow_unknown_ids": False,
            },
            "teaching_units": [
                {
                    "teaching_unit_id": unit.teaching_unit_id,
                    "source_ordinal": unit.source_ordinal,
                    "primary_block_ids": unit.primary_block_ids,
                    "teaching_intent": unit.teaching_intent,
                    "artifact_kinds": unit.artifact_kinds,
                    "source_asset_ids": unit.source_asset_refs,
                    "teaching_plan_context": unit.teaching_plan_context,
                    "prerequisite_unit_ids": unit.prerequisite_unit_ids,
                    "source_text": unit.source_text,
                    "allowed_template_layout_ids": (
                        allowed_layout_ids := _allowed_layout_ids(unit, template)
                    ),
                    "allowed_template_layouts": [
                        _layout_prompt_contract(layout_id, template)
                        for layout_id in allowed_layout_ids
                    ],
                }
                for unit in by_section[section_id]
            ],
        }
        for section_id in section_order
    ]


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
        try:
            raw = await _invoke(ai_planner, request, timeout_seconds)
            response = _StoryBatchResponse.model_validate(
                _normalize_versioned_response(
                    raw,
                    schema_version="slide_story_batch_response_v3",
                    collection_field="pages",
                    collection_aliases=("slides",),
                )
            )
            if response.schema_version != "slide_story_batch_response_v3":
                raise ValueError("Unexpected story response schema")
            if response.chapter_id != request["chapter_id"]:
                raise ValueError("Story response chapter does not match its request")
            pages: list[SlideStoryPageV3] = []
            for item in response.pages:
                pages.append(
                    SlideStoryPageV3(
                        **item.model_dump(mode="json"),
                        page_ordinal=page_ordinal,
                    )
                )
                page_ordinal += 1
            batch = SlideStoryBatchV3(
                    batch_id=batch_id,
                    chapter_id=response.chapter_id,
                    provider=response.provider or "shared-ai-pool",
                    model=response.model or "provider-selected",
                    duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
                    attempts=response.attempts,
                    validation_status="passed",
                    pages=pages,
            )
            batches.append(batch)
        except Exception as error:
            code, retryable = _failure_category(error, prefix="story_ai_batch")
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
        "pages": [
            {
                "page_id": page.page_id,
                "teaching_unit_id": page.teaching_unit_id,
                "template_layout_id": page.template_layout_id,
                "source_block_ids": page.source_block_ids,
                "source_text": units[page.teaching_unit_id].source_text,
                "artifact_kinds": units[page.teaching_unit_id].artifact_kinds,
                "source_asset_ids": units[page.teaching_unit_id].source_asset_refs,
            }
            for page in batch.pages
        ],
    }


_HARD_VISUAL_ARTIFACTS = {"code", "formula", "table", "data", "experiment", "source_excerpt"}


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
        try:
            async with semaphore:
                raw = await _invoke(ai_planner, request, timeout_seconds)
            response = _VisualBatchResponse.model_validate(
                _normalize_versioned_response(
                    raw,
                    schema_version="slide_visual_batch_response_v2",
                    collection_field="decisions",
                )
            )
            if response.schema_version != "slide_visual_batch_response_v2":
                raise ValueError("Unexpected visual response schema")
            duration_ms = max(0, round((time.perf_counter() - started) * 1000))
            decisions = [
                decision.model_copy(
                    update={
                        "provider": decision.provider or response.provider or "shared-ai-pool",
                        "model": decision.model or response.model or "provider-selected",
                        "attempts": max(decision.attempts, response.attempts),
                        "duration_ms": max(decision.duration_ms, duration_ms),
                    }
                )
                for decision in response.decisions
            ]
        except Exception as error:
            required_pages = [
                page
                for page in batch.pages
                if set(units[page.teaching_unit_id].artifact_kinds).intersection(_HARD_VISUAL_ARTIFACTS)
            ]
            if required_pages:
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
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only slide_story_batch_response_v3 JSON. You are a course-faithful "
                "presentation planner. Use every supplied primary_block_id exactly once, keep "
                "teaching units and prerequisites in order, and use only supplied teaching_unit_id "
                "and allowed_template_layout_ids. Create one to three pages per unit. Titles, "
                "summaries, transitions, facts, numbers, formulas and identifiers must be supported "
                "by that unit's source_text. Never invent teaching content."
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
        value = provider._extract_json(response or "") or {}
        if telemetry:
            value.setdefault("provider", str(telemetry[-1].get("provider") or "shared-ai-pool"))
            value.setdefault("model", str(telemetry[-1].get("model") or telemetry[-1].get("model_id") or "provider-selected"))
            value.setdefault("attempts", len(telemetry))
        return value

    return planner


def build_ai_base_visual_planner_v2() -> Planner:
    provider = AIBase()

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        telemetry: list[dict[str, Any]] = []
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only slide_visual_batch_response_v2 JSON with exactly one decision per "
                "page_id. Use only supplied source_block_ids and template_layout_id values. Preserve "
                "required code, formula, table, data, experiment and source evidence. Choose "
                "text_native when no meaningful visual is source-supported. Do not write slide copy "
                "or invent labels, facts or data. For diagram decisions include visual_payload with "
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
        value = provider._extract_json(response or "") or {}
        if telemetry:
            value.setdefault("provider", str(telemetry[-1].get("provider") or "shared-ai-pool"))
            value.setdefault("model", str(telemetry[-1].get("model") or telemetry[-1].get("model_id") or "provider-selected"))
            value.setdefault("attempts", len(telemetry))
        return value

    return planner


__all__ = [
    "build_ai_base_story_planner_v6",
    "build_ai_base_visual_planner_v2",
    "plan_slide_story_v3",
    "plan_slide_visuals_v2",
]
