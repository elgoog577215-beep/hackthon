"""Course-logic-first allocation, compilation, and quality gates."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Callable

from course_document import CourseDocument, stable_hash
from slide_deck_v3 import (
    ContentFragmentV1,
    DerivedTextV1,
    FragmentExclusionV1,
    PlannedPageV2,
    SlideAllocationPlanV2,
    SlideDeckMode,
    SlideDeckTheme,
    _paginate_fragments,
    compile_slide_deck_v3,
    fragment_course_document,
    slide_deck_variant_key,
    validate_allocation_plan,
)
from slide_layout_registry import SLIDE_LAYOUT_REGISTRY_V2, SlideSceneKind
from slide_story_plan import (
    SLIDE_STORY_ENGINE_V2_VERSION,
    STORY_BEAT_TEXT_CAPACITY,
    ChapterStoryV2,
    SlideStoryPlanV2,
    StoryBeatV2,
)
from slide_theme import slide_theme_version

SLIDE_DECK_V4_SCHEMA = "slide_deck_v4"
SLIDE_DECK_V4_COMPILER_VERSION = "course_logic_slide_compiler_v4.2"
SLIDE_LAYOUT_REGISTRY_V2_VERSION = "slide_layout_registry_v2.2"
SLIDE_RENDER_REVIEW_VERSION = "slide_render_review_v1"

_SCENE_TO_NARRATIVE_ROLE = {
    "chapter_entry": "orientation",
    "prerequisite_activation": "orientation",
    "concept": "concept",
    "reasoning": "reasoning",
    "method": "method",
    "worked_example": "example",
    "practice_feedback": "checkpoint",
    "misconception": "misconception",
    "application": "example",
    "chapter_recap": "recap",
}


def build_signature_v4(
    *,
    document: CourseDocument,
    course_data: dict[str, Any],
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
) -> dict[str, str]:
    plan = course_data.get("course_teaching_plan") or {}
    knowledge = course_data.get("course_knowledge_base") or {}
    coherence = course_data.get("course_coherence_contract") or {}
    fields = {
        "course_document_revision": str(document.document_revision or ""),
        "teaching_plan_revision": str(
            plan.get("revision_id")
            or course_data.get("teaching_plan_revision")
            or ""
        ),
        "knowledge_base_revision": str(
            knowledge.get("revision_id")
            or course_data.get("knowledge_base_revision")
            or ""
        ),
        "coherence_contract_revision": str(
            coherence.get("revision_id")
            or course_data.get("coherence_contract_revision")
            or ""
        ),
        "mode": str(mode),
        "theme": str(theme),
        "compiler_version": SLIDE_DECK_V4_COMPILER_VERSION,
        "story_engine_version": SLIDE_STORY_ENGINE_V2_VERSION,
        "layout_registry_version": SLIDE_LAYOUT_REGISTRY_V2_VERSION,
        "layout_registry_fingerprint": stable_hash(
            [item.model_dump(mode="json") for item in SLIDE_LAYOUT_REGISTRY_V2],
            prefix="layouts_",
        ),
        "render_review_version": SLIDE_RENDER_REVIEW_VERSION,
        "theme_version": slide_theme_version(),
    }
    return {
        **fields,
        "signature": stable_hash(fields, prefix="slidebuildv4_"),
    }


def _title_text(value: str) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= 76:
        return normalized
    for marker in ("。", "；", "：", "，", ";", ":"):
        index = normalized.find(marker, 24, 76)
        if index >= 0:
            return normalized[: index + 1]
    return normalized[:75].rstrip() + "…"


def _beat_pages(
    beat: StoryBeatV2,
    *,
    chapter_id: str,
    scene_kind: str,
    catalog: dict[str, ContentFragmentV1],
    page_counter: int,
) -> list[PlannedPageV2]:
    fragments = [catalog[item] for item in beat.fragment_ids if item in catalog]
    # A scene may exist in the teaching contract without source prose. Keep it
    # in the story manifest, but do not fabricate a body page for it.
    if not fragments:
        return []
    text_capacity = (
        360
        if beat.layout_selection_reason == "v5_semantic_grouping"
        else STORY_BEAT_TEXT_CAPACITY
    )
    chunks = (
        [fragments]
        if beat.layout_selection_reason == "v5_semantic_grouping"
        else _paginate_fragments(fragments, text_capacity)
    )
    pages: list[PlannedPageV2] = []
    for chunk_index, chunk in enumerate(chunks):
        derived = [DerivedTextV1(
            text=_title_text(beat.primary_claim_source.text),
            purpose="page_title",
            derived_from=[item.fragment_id for item in chunk],
        )]
        if chunk_index:
            derived.append(DerivedTextV1(
                text="继续按来源顺序展开",
                purpose="continuation",
                derived_from=[item.fragment_id for item in chunk],
            ))
        pages.append(PlannedPageV2(
            page_id=f"slide:v4:{page_counter + chunk_index:04d}",
            layout=beat.renderer_layout,
            fragment_ids=[item.fragment_id for item in chunk],
            appendix=False,
            derived_text=derived,
            narrative_role=_SCENE_TO_NARRATIVE_ROLE.get(
                scene_kind,
                "concept",
            ),
            section_id=chunk[0].section_id if chunk else chapter_id,
            chapter_id=chapter_id,
        ))
    return pages


def _source_ordered_beat_runs(
    chapter: ChapterStoryV2,
    catalog: dict[str, ContentFragmentV1],
) -> list[tuple[StoryBeatV2, SlideSceneKind]]:
    assignments: dict[str, tuple[StoryBeatV2, SlideSceneKind]] = {}
    for episode in chapter.episodes:
        for beat in episode.beats:
            for fragment_id in beat.fragment_ids:
                if fragment_id not in catalog:
                    raise ValueError(
                        f"Story beat {beat.beat_id} references an unknown source fragment"
                    )
                if fragment_id in assignments:
                    raise ValueError(
                        f"Story beat {beat.beat_id} duplicates an allocated source fragment"
                    )
                assignments[fragment_id] = (beat, episode.scene_kind)

    ordered_ids = sorted(
        assignments,
        key=lambda fragment_id: catalog[fragment_id].ordinal,
    )
    runs: list[tuple[StoryBeatV2, SlideSceneKind]] = []
    for fragment_id in ordered_ids:
        beat, scene_kind = assignments[fragment_id]
        if runs and runs[-1][0].beat_id == beat.beat_id:
            previous, previous_scene = runs[-1]
            runs[-1] = (
                previous.model_copy(update={
                    "fragment_ids": [*previous.fragment_ids, fragment_id],
                }),
                previous_scene,
            )
            continue
        runs.append((
            beat.model_copy(update={"fragment_ids": [fragment_id]}),
            scene_kind,
        ))
    return runs


def allocation_from_story_plan_v2(
    document: CourseDocument,
    fragments: list[ContentFragmentV1],
    story_plan: SlideStoryPlanV2,
) -> tuple[SlideAllocationPlanV2, dict[str, StoryBeatV2]]:
    """Compile story beats into an ID-only allocation understood by both renderers."""
    catalog = {item.fragment_id: item for item in fragments}
    pages: list[PlannedPageV2] = [
        PlannedPageV2(
            page_id="slide:title",
            layout="cover",
            narrative_role="orientation",
            derived_text=[DerivedTextV1(
                text=document.title,
                purpose="navigation",
            )],
        ),
        PlannedPageV2(
            page_id="slide:roadmap",
            layout="roadmap",
            narrative_role="orientation",
            derived_text=[
                DerivedTextV1(
                    text=chapter.title,
                    purpose="navigation",
                )
                for chapter in story_plan.chapters[:8]
            ],
        ),
    ]
    page_beats: dict[str, StoryBeatV2] = {}
    allocated: set[str] = set()
    counter = 1
    for chapter in story_plan.chapters:
        for beat, scene_kind in _source_ordered_beat_runs(chapter, catalog):
            if any(fragment_id in allocated for fragment_id in beat.fragment_ids):
                raise ValueError(
                    f"Story beat {beat.beat_id} duplicates an allocated source fragment"
                )
            beat_pages = _beat_pages(
                beat,
                chapter_id=chapter.chapter_id,
                scene_kind=scene_kind,
                catalog=catalog,
                page_counter=counter,
            )
            for page in beat_pages:
                page_beats[page.page_id] = beat
            pages.extend(beat_pages)
            allocated.update(beat.fragment_ids)
            counter += len(beat_pages)
    leftovers = [item for item in fragments if item.fragment_id not in allocated]
    exclusions: list[FragmentExclusionV1] = []
    v5_semantic_core = any(
        beat.layout_selection_reason == "v5_semantic_grouping"
        for chapter in story_plan.chapters
        for episode in chapter.episodes
        for beat in episode.beats
    )
    if story_plan.mode == "concise" or v5_semantic_core:
        exclusions = [
            FragmentExclusionV1(
                fragment_id=item.fragment_id,
                reason=(
                    "v5_semantic_core"
                    if v5_semantic_core
                    else "mode_concise"
                ),
            )
            for item in leftovers
        ]
    elif leftovers:
        appendix = story_plan.mode == "teaching"
        if appendix:
            pages.append(PlannedPageV2(
                page_id="slide:appendix-divider",
                layout="section-divider",
                appendix=True,
                narrative_role="appendix",
                derived_text=[DerivedTextV1(
                    text="补充原文",
                    purpose="appendix_label",
                    derived_from=[item.fragment_id for item in leftovers],
                )],
            ))
        for chunk_index, chunk in enumerate(
            _paginate_fragments(leftovers, 820 if appendix else 230, appendix=appendix)
        ):
            pages.append(PlannedPageV2(
                page_id=f"slide:v4:leftover:{chunk_index + 1:04d}",
                layout="appendix" if appendix else "editorial-body",
                fragment_ids=[item.fragment_id for item in chunk],
                appendix=appendix,
                narrative_role="appendix" if appendix else "concept",
                section_id=chunk[0].section_id,
                chapter_id=chunk[0].section_id,
            ))
    allocation = SlideAllocationPlanV2(
        title=document.title,
        mode=story_plan.mode,
        theme=story_plan.theme,
        variant_key=slide_deck_variant_key(story_plan.mode, story_plan.theme),
        source_document_revision=document.document_revision,
        pages=pages,
        exclusions=exclusions,
        planner=story_plan.planner,
        fallback_reason=story_plan.fallback_reason,
        review={"story_plan_id": story_plan.plan_id},
    )
    validate_allocation_plan(allocation, fragments)
    return allocation, page_beats


def _pedagogical_quality(story_plan: SlideStoryPlanV2) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for chapter in story_plan.chapters:
        scene_kinds = [episode.scene_kind for episode in chapter.episodes]
        if not chapter.driving_question:
            issues.append({
                "severity": "critical",
                "code": "chapter_driving_question_missing",
                "chapter_id": chapter.chapter_id,
            })
        if not scene_kinds or scene_kinds[0] != "chapter_entry":
            issues.append({
                "severity": "critical",
                "code": "chapter_entry_missing",
                "chapter_id": chapter.chapter_id,
            })
        if not scene_kinds or scene_kinds[-1] != "chapter_recap":
            issues.append({
                "severity": "critical",
                "code": "chapter_recap_missing",
                "chapter_id": chapter.chapter_id,
            })
        formal_refs = {
            ref
            for episode in chapter.episodes
            if episode.scene_kind in {"concept", "reasoning", "method"}
            for ref in episode.knowledge_refs
        }
        checked_refs = {
            ref
            for episode in chapter.episodes
            if episode.scene_kind == "practice_feedback"
            for ref in episode.knowledge_refs
        }
        for knowledge_id in chapter.owned_knowledge_ids:
            if knowledge_id not in formal_refs:
                issues.append({
                    "severity": "critical",
                    "code": "owned_knowledge_not_formally_explained",
                    "chapter_id": chapter.chapter_id,
                    "knowledge_id": knowledge_id,
                })
            if knowledge_id not in checked_refs:
                issues.append({
                    "severity": "critical",
                    "code": "owned_knowledge_not_checked",
                    "chapter_id": chapter.chapter_id,
                    "knowledge_id": knowledge_id,
                })
        for episode in chapter.episodes:
            if episode.scene_kind not in {"worked_example", "practice_feedback"}:
                continue
            roles = [beat.beat_role for beat in episode.beats]
            if not roles or roles[0] != "prompt":
                issues.append({
                    "severity": "critical",
                    "code": "answer_precedes_prompt",
                    "chapter_id": chapter.chapter_id,
                    "episode_id": episode.episode_id,
                })
            if episode.scene_kind == "worked_example" and not any(
                role in {"solution", "validation"} for role in roles[1:]
            ):
                issues.append({
                    "severity": "warning",
                    "code": "worked_example_solution_missing",
                    "chapter_id": chapter.chapter_id,
                    "episode_id": episode.episode_id,
                })
    blockers = [item for item in issues if item["severity"] == "critical"]
    return {
        "passed": not blockers,
        "score": max(0, 100 - len(blockers) * 20 - (len(issues) - len(blockers)) * 5),
        "issues": issues,
        "blockers": blockers,
    }


def _presentation_quality(
    story_plan: SlideStoryPlanV2,
    page_beats: dict[str, StoryBeatV2],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    chapter_by_beat_id = {
        beat.beat_id: chapter.chapter_id
        for chapter in story_plan.chapters
        for episode in chapter.episodes
        for beat in episode.beats
    }
    consecutive = 0
    previous = ""
    previous_chapter = ""
    for beat in page_beats.values():
        chapter_id = chapter_by_beat_id.get(beat.beat_id, "")
        if chapter_id != previous_chapter:
            consecutive = 0
            previous = ""
        family = beat.layout_family
        consecutive = consecutive + 1 if family == previous else 1
        if consecutive > 2:
            issues.append({
                "severity": "critical",
                "code": "layout_family_repeated_more_than_twice",
                "layout_family": family,
            })
            break
        previous = family
        previous_chapter = chapter_id
    for chapter in story_plan.chapters:
        chapter_families = [
            beat.layout_family
            for episode in chapter.episodes
            for beat in episode.beats
        ]
        counts = Counter(chapter_families)
        if len(chapter_families) >= 6:
            for family, count in counts.items():
                if count / len(chapter_families) > 0.35:
                    issues.append({
                        "severity": "warning",
                        "code": "chapter_layout_family_overrepresented",
                        "chapter_id": chapter.chapter_id,
                        "layout_family": family,
                        "ratio": round(count / len(chapter_families), 6),
                    })
    blockers = [item for item in issues if item["severity"] == "critical"]
    return {
        "passed": not blockers,
        "score": max(0, 100 - len(blockers) * 20 - (len(issues) - len(blockers)) * 5),
        "issues": issues,
        "blockers": blockers,
    }


def compile_slide_deck_v4(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    story_plan: SlideStoryPlanV2 | dict[str, Any],
    allocation_plan: SlideAllocationPlanV2 | dict[str, Any] | None = None,
    visual_plan: Any | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
    asset_repository: Any | None = None,
) -> dict[str, Any]:
    resolved_story = (
        story_plan
        if isinstance(story_plan, SlideStoryPlanV2)
        else SlideStoryPlanV2.model_validate(story_plan)
    )
    fragments = fragment_course_document(document)
    if allocation_plan is None:
        resolved_allocation, page_beats = allocation_from_story_plan_v2(
            document,
            fragments,
            resolved_story,
        )
    else:
        resolved_allocation = (
            allocation_plan
            if isinstance(allocation_plan, SlideAllocationPlanV2)
            else SlideAllocationPlanV2.model_validate(allocation_plan)
        )
        beats = {
            beat.beat_id: beat
            for chapter in resolved_story.chapters
            for episode in chapter.episodes
            for beat in episode.beats
        }
        page_beats = {}
        for page in resolved_allocation.pages:
            beat = next(
                (
                    item for item in beats.values()
                    if set(page.fragment_ids) <= set(item.fragment_ids)
                    and page.fragment_ids
                ),
                None,
            )
            if beat:
                page_beats[page.page_id] = beat
    if progress_callback:
        progress_callback({
            "event": "story_plan",
            "progress": 8,
            "stage": "story_plan",
            "story_plan": resolved_story.model_dump(mode="json"),
        })
        for index, chapter in enumerate(resolved_story.chapters):
            progress_callback({
                "event": "chapter_plan",
                "progress": min(18, 10 + index),
                "stage": "chapter_plan",
                "chapter_id": chapter.chapter_id,
                "chapter": chapter.model_dump(mode="json"),
            })
        progress_callback({
            "event": "layout_plan",
            "progress": 20,
            "stage": "layout_plan",
            "allocation_plan": resolved_allocation.model_dump(mode="json"),
        })
    content = compile_slide_deck_v3(
        document,
        course_data,
        mode=resolved_story.mode,
        theme=resolved_story.theme,
        allocation_plan=resolved_allocation,
        visual_plan=visual_plan,
        progress_callback=progress_callback,
        resume_slides=resume_slides,
        asset_repository=asset_repository,
    )
    episode_by_beat: dict[str, tuple[str, str, Any]] = {}
    for chapter in resolved_story.chapters:
        for episode in chapter.episodes:
            for beat in episode.beats:
                episode_by_beat[beat.beat_id] = (
                    chapter.chapter_id,
                    episode.episode_id,
                    episode,
                )
    for slide in content.get("slides") or []:
        beat = page_beats.get(str(slide.get("unit_id") or ""))
        if not beat:
            continue
        chapter_id, episode_id, episode = episode_by_beat[beat.beat_id]
        slide.update({
            "chapter_id": chapter_id,
            "episode_id": episode_id,
            "scene_kind": episode.scene_kind,
            "beat_role": beat.beat_role,
            "teaching_job": beat.teaching_job,
            "takeaway": beat.primary_claim_source.text,
            "primary_claim_source": beat.primary_claim_source.model_dump(mode="json"),
            "transition_from": beat.transition_from,
            "knowledge_refs": beat.knowledge_refs,
            "prerequisite_refs": beat.prerequisite_refs,
            "mastery_criterion_refs": beat.mastery_criterion_refs,
            "layout_selection_reason": beat.layout_selection_reason,
        })
    pedagogical = _pedagogical_quality(resolved_story)
    presentation = _presentation_quality(resolved_story, page_beats)
    previous_quality = deepcopy(content.get("quality_report") or {})
    v4_blockers = [
        *(pedagogical.get("blockers") or []),
        *(presentation.get("blockers") or []),
    ]
    combined_passed = bool(previous_quality.get("passed")) and not v4_blockers
    render_review = {
        "schema_version": "slide_render_review_v1",
        "reviewer": "deterministic_object_audit",
        "passed": combined_passed,
        "page_count": len(content.get("slides") or []),
        "issues": deepcopy(v4_blockers),
        "repair_attempts": 0,
    }
    content.update({
        "schema_version": SLIDE_DECK_V4_SCHEMA,
        "story_plan": resolved_story.model_dump(mode="json"),
        "scene_manifest": [
            {
                "chapter_id": chapter.chapter_id,
                "episode_id": episode.episode_id,
                "scene_kind": episode.scene_kind,
                "teaching_job": episode.teaching_job,
                "beat_ids": [beat.beat_id for beat in episode.beats],
            }
            for chapter in resolved_story.chapters
            for episode in chapter.episodes
        ],
        "layout_plan": {
            "schema_version": "slide_layout_plan_v2",
            "registry_version": SLIDE_LAYOUT_REGISTRY_V2_VERSION,
            "pages": [
                {
                    "page_id": page_id,
                    "beat_id": beat.beat_id,
                    "layout_intent": beat.layout_intent,
                    "renderer_layout": beat.renderer_layout,
                    "layout_family": beat.layout_family,
                    "reason": beat.layout_selection_reason,
                }
                for page_id, beat in page_beats.items()
            ],
        },
        "build_signature": build_signature_v4(
            document=document,
            course_data=course_data,
            mode=resolved_story.mode,
            theme=resolved_story.theme,
        ),
        "render_review": render_review,
        "pedagogical_quality_report": pedagogical,
        "presentation_quality_report": presentation,
    })
    content["quality_report"] = {
        **previous_quality,
        "passed": combined_passed,
        "pedagogical": pedagogical,
        "presentation": presentation,
        "blockers": [
            *(previous_quality.get("blockers") or []),
            *v4_blockers,
        ],
    }
    content["quality_summary"] = {
        **(content.get("quality_summary") or {}),
        "passed": combined_passed,
        "pedagogical_score": pedagogical["score"],
        "presentation_score": presentation["score"],
    }
    return content


def validate_slide_deck_v4(
    content: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del course_data
    if content.get("schema_version") != SLIDE_DECK_V4_SCHEMA:
        raise ValueError("Expected slide_deck_v4 content")
    story = SlideStoryPlanV2.model_validate(content.get("story_plan") or {})
    pedagogical = _pedagogical_quality(story)
    presentation = deepcopy(content.get("presentation_quality_report") or {})
    base = deepcopy(content.get("quality_report") or {})
    blockers = [
        *(base.get("blockers") or []),
        *(pedagogical.get("blockers") or []),
        *(presentation.get("blockers") or []),
    ]
    return {
        **base,
        "passed": bool(base.get("passed")) and not blockers,
        "pedagogical": pedagogical,
        "presentation": presentation,
        "blockers": blockers,
        "score": min(
            int(base.get("score") or 100),
            int(pedagogical.get("score") or 0),
            int(presentation.get("score") or 100),
        ),
    }
