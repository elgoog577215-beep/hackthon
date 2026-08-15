from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

import pytest

from course_document import CourseDocument
from course_presentation_graph import CoursePresentationGraphV1
from slide_ai_planning_v6 import plan_slide_story_v3
from slide_deck_v6 import (
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    compile_slide_deck_v6,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1

_LOCAL_REPLAY = (
    Path(__file__).parent
    / "fixtures"
    / "slide_deck_v6"
    / "v13-production-replay.local"
    / "v6-template-replay.json"
)


def _load_replay():
    if not _LOCAL_REPLAY.exists():
        pytest.skip("local sanitized production-shape replay is not installed")
    payload = json.loads(_LOCAL_REPLAY.read_text(encoding="utf-8"))
    template = compile_builtin_template_layout_contract_v1(payload["theme_id"])
    story_payload = dict(payload["story_plan"])
    story_payload.pop("pages", None)
    story_payload["template_digest"] = template.template_digest
    for batch in story_payload["batches"]:
        for page in batch["pages"]:
            page["template_layout_id"] = template.layout_id(
                page["template_layout_id"].rsplit("/", 1)[-1]
            )
    visual_payload = dict(payload["visual_plan"])
    visual_payload["template_digest"] = template.template_digest
    for decision in visual_payload["decisions"]:
        decision["resolved_template_layout_id"] = template.layout_id(
            decision["resolved_template_layout_id"].rsplit("/", 1)[-1]
        )
    return (
        CourseDocument.model_validate(payload["document"]),
        CoursePresentationGraphV1.model_validate(
            payload["course_presentation_graph"]
        ),
        SlideStoryPlanV3.model_validate(story_payload),
        SlideVisualPlanV2.model_validate(visual_payload),
        template,
    )


def _deck_signature(deck) -> list[tuple]:
    return [
        (
            page.page_id,
            page.resolved_layout,
            tuple(page.source_block_ids),
            tuple(
                (
                    region.region_id,
                    region.content_kind,
                    region.content,
                    tuple(region.source_block_ids),
                )
                for region in page.regions
            ),
        )
        for page in deck.pages
    ]


async def _normalize_replayed_story(
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template,
) -> SlideStoryPlanV3:
    """Replay a stale production Story through the current AI boundary."""

    batches = {batch.chapter_id: batch for batch in story.batches}

    async def planner(request):
        batch = batches[request["chapter_id"]]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "sanitized-production-replay",
            "model": "frozen-response",
            "attempts": 1,
            "pages": [
                {
                    "page_id": page.page_id,
                    "teaching_unit_id": page.teaching_unit_id,
                    "template_layout_id": page.template_layout_id,
                    "title": page.title,
                    "summary": page.summary,
                    "source_block_ids": page.source_block_ids,
                }
                for page in batch.pages
            ],
        }

    return await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )


def test_full_production_shape_replay_is_deterministic_complete_and_bounded() -> None:
    document, graph, stale_story, stale_visual, template = _load_replay()

    with pytest.raises(V6BuildError) as stale_error:
        compile_slide_deck_v6(
            document,
            graph,
            stale_story,
            stale_visual,
            template,
        )
    assert (
        stale_error.value.failure.code
        == "template_source_semantic_fidelity_incomplete"
    )

    story = asyncio.run(_normalize_replayed_story(
        stale_story,
        graph,
        template,
    ))
    old_decisions = {
        decision.page_id: decision for decision in stale_visual.decisions
    }
    visual = stale_visual.model_copy(update={
        "decisions": [
            old_decisions[page.page_id].model_copy(update={
                "resolved_template_layout_id": page.template_layout_id,
            })
            if page.page_id in old_decisions
            else SlideVisualDecisionV2(
                page_id=page.page_id,
                decision="text_native",
                source_block_ids=page.source_block_ids,
                resolved_template_layout_id=page.template_layout_id,
            )
            for page in story.pages
        ],
    })

    first = compile_slide_deck_v6(document, graph, story, visual, template)
    second = compile_slide_deck_v6(document, graph, story, visual, template)

    assert first.quality.passed
    assert _deck_signature(first) == _deck_signature(second)
    assert len(first.pages) == len({page.page_id for page in first.pages})
    assert first.quality.story_page_count == len(story.pages)
    assert first.quality.final_page_count == len(first.pages)
    assert first.quality.pagination_within_dynamic_bound
    assert len(first.pages) <= first.quality.pagination_page_upper_bound

    story_ids = {page.page_id for page in story.pages}
    expansion = Counter(
        page.continuation_of_page_id
        or (page.page_id if page.page_id in story_ids else "generated")
        for page in first.pages
    )
    assert max(expansion[page_id] for page_id in story_ids) == (
        first.quality.max_story_page_expansion
    )

    visible_fingerprints: Counter[tuple[str, str, str]] = Counter()
    for page in first.pages:
        assert len(page.source_block_ids) == len(set(page.source_block_ids))
        assert set(page.visual_decision.source_block_ids).issubset(
            set(page.source_block_ids)
        )
        for region in page.regions:
            assert len(region.source_block_ids) == len(set(region.source_block_ids))
            assert set(region.source_block_ids).issubset(set(page.source_block_ids))
            if region.content_kind in {"title", "eyebrow", "notes"}:
                continue
            for block_id in region.source_block_ids:
                visible_fingerprints[(
                    block_id,
                    region.content_kind,
                    region.content,
                )] += 1
    assert all(count == 1 for count in visible_fingerprints.values())
