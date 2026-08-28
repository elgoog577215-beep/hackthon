"""Slide planning workers and quality-preserving rebuild fallback."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from ai_base import AIBase
from representation_compiler import rebuild_slide_deck_variant_safely
from slide_ai_runtime import ai_slide_planning_enabled
from slide_deck_v3 import SlideAllocationPlanV2, fragment_course_document
from slide_deck_v5 import allocation_from_story_plan_v5, compact_story_plan_v5
from slide_story_plan import SlideStoryPlanV2, compile_slide_story_plan_v2
from slide_visuals import SlideVisualPlanV1, plan_slide_visuals
from slide_web_images import VISUAL_RETRIEVAL_PLANNER_PROMPT

def _source_first_slide_ai_workers() -> tuple[
    Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None,
    Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None,
]:
    """Create source-bound planner and reviewer functions when AI is available."""
    provider = AIBase()
    if not ai_slide_planning_enabled(
        provider_available=provider.client is not None,
    ):
        return None, None

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only a slide_allocation_plan_v2 JSON object. You are a page "
                "director, not a course author. Never write, summarize, translate, or "
                "replace teaching body text. Allocate only the supplied fragment_id "
                "values, preserve their order, use only allowed layouts, and explicitly "
                "exclude every omitted fragment in concise mode."
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        return provider._extract_json(response or "") or {}

    async def reviewer(request: dict[str, Any]) -> dict[str, Any]:
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only JSON with action keep or replan and an issues array. "
                "Issues may contain only code, page_id, and suggested_action. Never "
                "write replacement slide text or teaching content."
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            raise_on_failure=True,
        )
        return provider._extract_json(response or "") or {}

    return planner, reviewer


def _source_first_story_ai_worker() -> (
    Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None
):
    """Return the source-bound story planner when AI is available."""
    provider = AIBase()
    if not ai_slide_planning_enabled(
        provider_available=provider.client is not None,
    ):
        return None

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only one valid slide_story_chapter_directives_v2 JSON "
                "object for the requested chapter. Do not echo the deterministic "
                "baseline. For each useful beat, select one "
                "headline_fragment_id from that beat's headline_candidates and "
                "one layout_id from that beat's allowed_layouts. Prefer a concise "
                "source heading for the headline; otherwise choose the shortest "
                "source sentence that states the beat's teaching point. You may "
                "also provide audience_facing_title and audience_facing_summary "
                "as a concise source-faithful rewrite, or as an instructional "
                "scaffold that frames a question or transition without adding a "
                "new fact. Every rewrite must declare copy_mode and exact "
                "supporting_fragment_ids owned by the beat. Never invent or alter "
                "facts, numbers, formulas, units, named entities, or conclusions. "
                "When a beat has needs_generated_answers=true, return exactly one "
                "generated_practice_answers entry for every supplied prompt question, "
                "in question_index order and bind it to the exact supplied question_id. "
                "Keep each answer within 140 Chinese characters. "
                "Start with a direct conclusion, then give one concise teaching reason. "
                "Bind every answer to exact chapter "
                "fragment IDs that support the conclusion. Omit generated answers for "
                "all other beats. Put fragment IDs only in supporting_fragment_ids; "
                "never expose them inside answer_text. "
                "Use only supplied beat_id, fragment_id, and layout_id values. "
                "Omit a rewrite instead of making an uncertain claim. Preserve "
                "proof, example, "
                "prompt, answer, and chapter order. The root object must contain "
                "exactly schema_version, chapter_id, and beat_directives. Use this "
                "shape: {\"schema_version\":\"slide_story_chapter_directives_v2\","
                "\"chapter_id\":\"<exact supplied chapter_id>\","
                "\"beat_directives\":[{\"beat_id\":\"<exact beat_id>\","
                "\"headline_fragment_id\":\"<exact fragment_id or empty>\","
                "\"layout_id\":\"<exact layout_id or empty>\","
                "\"copy_mode\":\"source_exact|source_faithful_rewrite|instructional_scaffold\","
                "\"audience_facing_title\":\"<optional>\","
                "\"audience_facing_summary\":\"<optional>\","
                "\"supporting_fragment_ids\":[\"<exact fragment_id>\"],"
                "\"generated_practice_answers\":[{\"question_index\":0,"
                "\"question_id\":\"<exact supplied question_id>\","
                "\"answer_text\":\"<direct answer and concise reason>\","
                "\"supporting_fragment_ids\":[\"<exact chapter fragment_id>\"]}]}]}. "
                "Never wrap this "
                "object and never return episodes or the baseline."
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            max_tokens=6144,
            reject_truncated=True,
            raise_on_failure=True,
            json_mode=True,
        )
        return provider._extract_json(response or "") or {}

    return planner


def _source_first_slide_visual_ai_worker() -> (
    Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None
):
    provider = AIBase()
    if not ai_slide_planning_enabled(
        provider_available=provider.client is not None,
    ):
        return None

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        response = await provider._call_llm(
            json.dumps(request, ensure_ascii=False),
            system_prompt=(
                "Return only one slide_visual_plan_v1 JSON object. "
                "Follow response_contract exactly and return every requested "
                "page_id once. Never return the compact fragment_id/visual_kind "
                "shape. The compiler owns page copy; only choose composition, "
                "role_layout_variant, and visual_anchor. "
                "Use only the provided page_id and fragment_id values. "
                "Takeaways and diagram labels must be short excerpts of their bound source text. "
                "Do not emit slide body copy or add facts, numbers, claims, or chart data. "
                "Prefer kind=none whenever a useful visual cannot be guaranteed. "
                "For kind=rule_diagram, use only an allowed_rule_diagram_templates value "
                "and source-bound nodes, edges, and relation_evidence. Never emit Mermaid, "
                "SVG, HTML, coordinates, executable drawing code, or invented labels. "
                "Do not request generated_illustration when it is absent from "
                "allowed_visual_kinds. When a real image materially improves a page, "
                "put its strict search request under "
                "deck_brief.visual_search_requests keyed by the exact page_id. "
                "Otherwise omit that key.\n\n"
                + VISUAL_RETRIEVAL_PLANNER_PROMPT
                + "\nThe root JSON object must still be slide_visual_plan_v1; "
                "never return a standalone search request."
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            max_tokens=6144,
            reject_truncated=True,
            raise_on_failure=True,
            json_mode=True,
        )
        return provider._extract_json(response or "") or {}

    return planner

async def _rebuild_slide_variant_with_quality_fallback(
    *,
    document: Any,
    course_view: dict[str, Any],
    repository: Any,
    mode: str,
    theme: str,
    slide_schema: str,
    allocation_plan: SlideAllocationPlanV2,
    visual_plan: SlideVisualPlanV1,
    story_plan: SlideStoryPlanV2 | Any | None,
    progress_callback: Callable[[dict[str, Any]], None],
    checkpoint_callback: (
        Callable[
            [SlideAllocationPlanV2, SlideVisualPlanV1, SlideStoryPlanV2],
            Awaitable[None],
        ]
        | None
    ),
    resume_slides: list[dict[str, Any]],
    source_revision_provider: Callable[[], str] | None = None,
    variant_key_override: str | None = None,
) -> dict[str, Any]:
    """Retry a rejected V5 draft with the strict source-only plan.

    The first candidate still runs through the normal shadow repository. Its
    terminal ``build_blocked`` event is converted into a non-terminal fallback
    event so clients do not settle the build before the deterministic candidate
    has been evaluated. This also covers deterministic semantic plans: a new
    course must still reach the stricter ``quality_fallback`` profile when the
    ordinary deterministic plan cannot satisfy the final page contract.
    """

    fallback_enabled = os.getenv(
        "SLIDE_DECK_V5_QUALITY_FALLBACK_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    story_diagnostics = (
        story_plan.get("planning_diagnostics")
        if isinstance(story_plan, dict)
        else getattr(story_plan, "planning_diagnostics", None)
    )
    compaction_profile = str(
        (story_diagnostics or {}).get("compaction_profile") or ""
    ) if isinstance(story_diagnostics, dict) else ""
    fallback_allowed = bool(
        fallback_enabled
        and slide_schema == "slide_deck_v5"
        and story_plan is not None
        and compaction_profile != "quality_fallback"
    )
    fallback_event_emitted = False

    def primary_progress(payload: dict[str, Any]) -> None:
        nonlocal fallback_event_emitted
        if (
            fallback_allowed
            and payload.get("event") in {"build_blocked", "build_failed"}
        ):
            quality = payload.get("quality") or {}
            blockers = list(quality.get("blockers") or [])
            progress_callback({
                "event": "quality_fallback",
                "stage": "quality_fallback",
                "progress": 85,
                "message": "首轮候选稿未通过质量检查，正在切换严格生成方案",
                "initial_score": int(quality.get("score") or 0),
                "initial_blocker_count": int(
                    quality.get("blocker_count") or len(blockers)
                ),
            })
            fallback_event_emitted = True
            return
        progress_callback(payload)

    build = await asyncio.to_thread(
        rebuild_slide_deck_variant_safely,
        document,
        course_view,
        repository,
        mode=mode,
        theme=theme,
        allocation_plan=allocation_plan,
        visual_plan=visual_plan,
        story_plan=story_plan,
        progress_callback=primary_progress,
        resume_slides=resume_slides,
        requested_schema=slide_schema,
        source_revision_provider=source_revision_provider,
        variant_key_override=variant_key_override,
    )
    initial_quality = build.get("quality") or {}
    if initial_quality.get("passed") or not fallback_allowed:
        return {
            "build": build,
            "allocation_plan": allocation_plan,
            "visual_plan": visual_plan,
            "story_plan": story_plan,
            "used_deterministic_fallback": False,
            "initial_quality": None,
        }

    if not fallback_event_emitted:
        blockers = list(initial_quality.get("blockers") or [])
        progress_callback({
            "event": "quality_fallback",
            "stage": "quality_fallback",
            "progress": 85,
            "message": "首轮候选稿未通过质量检查，正在切换严格生成方案",
            "initial_score": int(initial_quality.get("score") or 0),
            "initial_blocker_count": int(
                initial_quality.get("blocker_count") or len(blockers)
            ),
        })

    source_fragments = fragment_course_document(document)
    deterministic_story = compact_story_plan_v5(
        document,
        compile_slide_story_plan_v2(
            document,
            course_view,
            source_fragments,
            mode=mode,
            theme=theme,
        ),
        source_fragments,
        profile="quality_fallback",
    )
    deterministic_allocation, _ = allocation_from_story_plan_v5(
        document,
        source_fragments,
        deterministic_story,
    )
    deterministic_visual = await plan_slide_visuals(
        document,
        deterministic_allocation,
        source_fragments,
        ai_planner=None,
    )
    if checkpoint_callback is not None:
        await checkpoint_callback(
            deterministic_allocation,
            deterministic_visual,
            deterministic_story,
        )
    fallback_build = await asyncio.to_thread(
        rebuild_slide_deck_variant_safely,
        document,
        course_view,
        repository,
        mode=mode,
        theme=theme,
        allocation_plan=deterministic_allocation,
        visual_plan=deterministic_visual,
        story_plan=deterministic_story,
        progress_callback=progress_callback,
        resume_slides=[],
        requested_schema=slide_schema,
        source_revision_provider=source_revision_provider,
        variant_key_override=variant_key_override,
    )
    return {
        "build": fallback_build,
        "allocation_plan": deterministic_allocation,
        "visual_plan": deterministic_visual,
        "story_plan": deterministic_story,
        "used_deterministic_fallback": True,
        "initial_quality": initial_quality,
    }

__all__: list[str] = []
