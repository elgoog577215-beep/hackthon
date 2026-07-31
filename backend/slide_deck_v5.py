"""Deck-level narrative and final page contracts for slide_deck_v5."""

from __future__ import annotations

import math
import os
import re
from copy import deepcopy
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, stable_hash
from slide_deck_v4 import (
    SLIDE_DECK_V4_SCHEMA,
    allocation_from_story_plan_v2,
    build_signature_v4,
    compile_slide_deck_v4,
    validate_slide_deck_v4,
)
from slide_deck_v3 import fragment_course_document
from slide_story_plan import (
    ClaimSourceV2,
    SlideStoryPlanV2,
    StoryBeatV2,
    TeachingEpisodeV2,
)

SLIDE_DECK_V5_SCHEMA = "slide_deck_v5"
SLIDE_DECK_V5_COMPILER_VERSION = "course_logic_slide_compiler_v5.2"
DECK_OUTLINE_V5_VERSION = "deck_outline_v5.0"
FINAL_PAGE_CONTRACT_V5_VERSION = "final_page_contract_v5.0"

_VISUAL_REQUIRED_LAYOUTS = {
    "figure-text",
    "image-split",
    "split-visual",
    "diagram-full",
    "figure-first",
}
_VISUAL_COMPOSITIONS = {
    "split-visual",
    "figure-first",
    "diagram-full",
}
_GENERIC_TITLES = {
    "",
    "背景与意义",
    "核心概念",
    "核心概念与背景",
    "关键名词解释",
    "练习与思考",
    "实战案例",
    "实战案例行业应用",
    "思考与挑战",
    "深度原理底层机制",
    "行业应用",
    "课程内容",
    "课程正文",
    "正文",
    "内容",
    "未命名",
    "body",
    "content",
}
_CHAPTER_PREFIX = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十百\d]+\s*[章节篇部]|"
    r"[一二三四五六七八九十百\d]+\s*[.、．:：])\s*"
)
_RAW_TITLE_PATTERN = re.compile(
    r"(?:^\s*>?\s*(?:ID|graph|flowchart|sequenceDiagram|classDiagram)\s*[:\s]|"
    r"-->|```|^\s*\\(?:begin|frac|Delta|sum|int)\b)",
    re.IGNORECASE,
)
_V5_DEFAULT_DENSITY_BUDGET = {"characters": 360, "items": 6, "title": 28}
_V5_DENSITY_BUDGETS = {
    "cover-minimal": {"characters": 90, "items": 0, "title": 44},
    "agenda-linear": {"characters": 240, "items": 6, "title": 28},
    "chapter-entry": {"characters": 120, "items": 0, "title": 36},
    "hero-claim": {"characters": 0, "items": 0, "title": 32},
    "editorial-body": {"characters": 360, "items": 6, "title": 28},
    "balanced-two-column": {"characters": 420, "items": 6, "title": 28},
    "classification-3": {"characters": 270, "items": 3, "title": 28},
    "process-sequence": {"characters": 300, "items": 5, "title": 28},
    "formula-explanation": {"characters": 280, "items": 4, "title": 28},
    "figure-text": {"characters": 320, "items": 5, "title": 28},
    "diagram-full": {"characters": 0, "items": 0, "title": 28},
    "worked-example": {"characters": 360, "items": 3, "title": 28},
    "practice-feedback": {"characters": 400, "items": 5, "title": 28},
    "chapter-recap": {"characters": 320, "items": 5, "title": 28},
    "course-synthesis": {"characters": 340, "items": 6, "title": 28},
}
_V5_MINIMUM_BODY_FONT_PT = 14
_V5_MINIMUM_TITLE_FONT_PT = 24
_V5_REPLACED_V4_QUALITY_CODES = {
    "appendix_content_overflow",
    "chapter_message_overflow",
    "code_insight_overflow",
    "concept_card_overflow",
    "layout_family_repeated_more_than_twice",
    "objective_content_overflow",
    "owned_knowledge_not_checked",
    "practice_check_overflow",
    "practice_content_overflow",
    "process_step_overflow",
    "slide_block_overflow",
    "slide_item_overflow",
    "slide_text_overflow",
    "source_coverage_incomplete",
    "visual_coverage_below_threshold",
    "raw_source_sentence_as_title",
    "title_body_duplication",
}
_T = TypeVar("_T")


def _v5_fragment_groups(fragments: list[Any]) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current: list[Any] = []
    for fragment in sorted(fragments, key=lambda item: item.ordinal):
        if (
            fragment.kind == "heading"
            and current
            and any(item.kind != "heading" for item in current)
        ):
            groups.append(current)
            current = []
        current.append(fragment)
    if current:
        groups.append(current)
    return groups


def _v5_group_kind(group: list[Any]) -> str:
    headings = " ".join(
        str(item.text or "")
        for item in group
        if item.kind == "heading"
    )
    if re.search(r"思考|挑战|练习|测验|检查|question|practice", headings, re.I):
        return "practice"
    if re.search(r"案例|应用|例题|示例|实战|case|example|application", headings, re.I):
        return "worked"
    if re.search(r"方法|实现|步骤|流程|操作|method|procedure", headings, re.I):
        return "method"
    if re.search(r"原理|机制|推导|证明|why|reason|derivation", headings, re.I):
        return "reasoning"
    return "concept"


def _v5_fit_group(group: list[Any], *, limit: int = 230) -> list[Any]:
    selected: list[Any] = []
    visible = 0
    for fragment in group:
        size = len(str(fragment.text or ""))
        if not selected and size > limit:
            return []
        if selected and size and visible + size > limit:
            break
        selected.append(fragment)
        visible += size
        if len(selected) == 8:
            break
    return selected


def _compact_existing_episodes_v5(
    episodes: list[TeachingEpisodeV2],
    fragment_catalog: dict[str, Any],
) -> list[TeachingEpisodeV2]:
    """Preserve the existing teaching loop when legacy prose has no headings."""
    priorities = (
        ("concept", "reasoning"),
        ("worked_example", "method"),
        ("practice_feedback",),
    )
    selected: list[TeachingEpisodeV2] = []
    used_episode_ids: set[str] = set()
    for scene_kinds in priorities:
        candidate = next(
            (
                episode
                for episode in episodes
                if (
                    episode.episode_id not in used_episode_ids
                    and episode.scene_kind in scene_kinds
                )
            ),
            None,
        )
        if candidate is None:
            continue
        fragment_ids = list(dict.fromkeys(
            fragment_id
            for beat in candidate.beats
            for fragment_id in beat.fragment_ids
            if fragment_id in fragment_catalog
        ))
        source_group = sorted(
            [fragment_catalog[fragment_id] for fragment_id in fragment_ids],
            key=lambda item: item.ordinal,
        )
        fitted = _v5_fit_group(source_group)
        if (
            not fitted
            or [item.fragment_id for item in fitted]
            != [item.fragment_id for item in source_group]
        ):
            continue
        selected.append(candidate.model_copy(update={
            "beats": [
                beat.model_copy(update={
                    "layout_selection_reason": "v5_semantic_grouping",
                })
                for beat in candidate.beats
            ],
        }))
        used_episode_ids.add(candidate.episode_id)
    return selected


def compact_story_plan_v5(
    document: CourseDocument,
    story_plan: SlideStoryPlanV2 | dict[str, Any],
    fragments: list[Any] | None = None,
) -> SlideStoryPlanV2:
    """Select three complete, source-bound teaching groups per source section.

    Detailed source fragments remain available as explicit coverage decisions
    instead of being copied into dense appendix slides.
    """
    story = (
        story_plan
        if isinstance(story_plan, SlideStoryPlanV2)
        else SlideStoryPlanV2.model_validate(story_plan)
    )
    interior_beats = [
        beat
        for chapter in story.chapters
        for episode in chapter.episodes[1:-1]
        for beat in episode.beats
    ]
    if interior_beats and all(
        beat.layout_selection_reason
        in {"v5_semantic_grouping", "ai_source_bound_directive"}
        for beat in interior_beats
    ):
        return story
    source_fragments = fragments or fragment_course_document(document)
    fragments_by_section: dict[str, list[Any]] = {}
    for fragment in source_fragments:
        fragments_by_section.setdefault(fragment.section_id, []).append(fragment)
    fragment_catalog = {
        fragment.fragment_id: fragment
        for fragment in source_fragments
    }
    compact_chapters = []
    for chapter in story.chapters:
        original_episodes = chapter.episodes
        entry = original_episodes[0].model_copy(update={
            "beats": [
                beat.model_copy(update={"fragment_ids": []})
                for beat in original_episodes[0].beats
            ],
        })
        recap = original_episodes[-1].model_copy(update={
            "beats": [
                beat.model_copy(update={"fragment_ids": []})
                for beat in original_episodes[-1].beats
            ],
        })
        knowledge_refs = list(dict.fromkeys(
            ref
            for episode in original_episodes
            for ref in episode.knowledge_refs
        ))
        capability_refs = list(dict.fromkeys(
            ref
            for episode in original_episodes
            for ref in episode.capability_refs
        ))
        misconception_refs = list(dict.fromkeys(
            ref
            for episode in original_episodes
            for ref in episode.misconception_refs
        ))
        mastery_refs = list(dict.fromkeys(
            ref
            for episode in original_episodes
            for ref in episode.mastery_criterion_refs
        ))
        section_ids = [
            section.section_id
            for section in sorted(document.sections, key=lambda item: item.position)
            if section.parent_section_id == chapter.chapter_id
            and section.level == 2
        ]
        chapter_level_fallback = (
            not section_ids
            and fragments_by_section.get(chapter.chapter_id)
        )
        if chapter_level_fallback:
            section_ids = [chapter.chapter_id]
        teaching_episodes: list[TeachingEpisodeV2] = []
        transition = entry.beats[-1].beat_id if entry.beats else ""
        if (
            chapter_level_fallback
            and not any(
                fragment.kind == "heading"
                for fragment in fragments_by_section.get(
                    chapter.chapter_id,
                    [],
                )
            )
        ):
            teaching_episodes = _compact_existing_episodes_v5(
                original_episodes,
                fragment_catalog,
            )
            section_ids = []
        for section_id in section_ids:
            groups = _v5_fragment_groups(
                fragments_by_section.get(section_id, [])
            )
            by_kind: dict[str, list[list[Any]]] = {}
            for group in groups:
                by_kind.setdefault(_v5_group_kind(group), []).append(group)
            selected_groups: list[tuple[str, list[Any]]] = []
            if by_kind.get("concept"):
                selected_groups.append(("concept", by_kind["concept"][0]))
            second = next(
                (
                    (kind, by_kind[kind][0])
                    for kind in ("worked", "method", "reasoning")
                    if by_kind.get(kind)
                ),
                None,
            )
            if second:
                selected_groups.append(second)
            if by_kind.get("practice"):
                selected_groups.append(("practice", by_kind["practice"][0]))
            if len(selected_groups) < 3:
                used_first_ids = {
                    group[0].fragment_id
                    for _kind, group in selected_groups
                    if group
                }
                for group in groups:
                    if not group or group[0].fragment_id in used_first_ids:
                        continue
                    selected_groups.append((_v5_group_kind(group), group))
                    if len(selected_groups) == 3:
                        break
            for group_index, (kind, raw_group) in enumerate(selected_groups[:3]):
                group = _v5_fit_group(raw_group)
                if not group:
                    continue
                scene = {
                    "worked": "worked_example",
                    "practice": "practice_feedback",
                    "method": "method",
                    "reasoning": "reasoning",
                }.get(kind, "concept")
                role = (
                    "prompt"
                    if scene in {"worked_example", "practice_feedback"}
                    else "procedure"
                    if scene == "method"
                    else "reasoning_step"
                    if scene == "reasoning"
                    else "formal_explanation"
                )
                claim_fragment = next(
                    (item for item in group if item.kind == "heading"),
                    group[0],
                )
                selection = {
                    "worked_example": ("worked-example", "question", "example"),
                    "practice_feedback": (
                        "practice-feedback",
                        "question",
                        "question",
                    ),
                    "method": ("process-sequence", "process", "process"),
                    "reasoning": ("process-sequence", "process", "process"),
                    "concept": (
                        "editorial-body",
                        "editorial-body",
                        "statement",
                    ),
                }[scene]
                episode_id = stable_hash({
                    "chapter_id": chapter.chapter_id,
                    "section_id": section_id,
                    "scene": scene,
                    "group": group_index,
                    "fragments": [item.fragment_id for item in group],
                }, prefix="episodev5_")
                beat_id = stable_hash({
                    "episode_id": episode_id,
                    "fragments": [item.fragment_id for item in group],
                }, prefix="beatv5_")
                beat = StoryBeatV2(
                    beat_id=beat_id,
                    beat_role=role,
                    teaching_job={
                        "worked_example": "用来源案例展示判断与验证",
                        "practice_feedback": "用来源问题检查理解",
                        "method": "把本节知识转化为可执行步骤",
                        "reasoning": "说明结论如何从条件推出",
                        "concept": "建立本节核心概念与边界",
                    }[scene],
                    primary_claim_source=ClaimSourceV2(
                        kind=(
                            "source_heading"
                            if claim_fragment.kind == "heading"
                            else "source_sentence"
                        ),
                        text=str(claim_fragment.text or ""),
                        fragment_id=claim_fragment.fragment_id,
                    ),
                    fragment_ids=[item.fragment_id for item in group],
                    transition_from=transition,
                    evidence_kinds=sorted({
                        "text"
                        if item.kind in {"heading", "paragraph", "list_item"}
                        else item.kind
                        for item in group
                    }),
                    layout_intent=selection[0],
                    renderer_layout=selection[1],
                    layout_family=selection[2],
                    layout_selection_reason="v5_semantic_grouping",
                    density="primary",
                    knowledge_refs=knowledge_refs,
                    prerequisite_refs=chapter.prerequisite_knowledge_names,
                    mastery_criterion_refs=mastery_refs,
                )
                teaching_episodes.append(TeachingEpisodeV2(
                    episode_id=episode_id,
                    scene_kind=scene,
                    teaching_job=beat.teaching_job,
                    knowledge_refs=knowledge_refs,
                    capability_refs=capability_refs,
                    misconception_refs=misconception_refs,
                    mastery_criterion_refs=mastery_refs,
                    beats=[beat],
                ))
                transition = beat_id
        if not any(
            episode.scene_kind == "practice_feedback"
            for episode in teaching_episodes
        ):
            original_practice = next(
                (
                    episode
                    for episode in original_episodes
                    if episode.scene_kind == "practice_feedback"
                ),
                None,
            )
            if original_practice:
                practice_fragment_ids = list(dict.fromkeys(
                    fragment_id
                    for beat in original_practice.beats
                    for fragment_id in beat.fragment_ids
                    if fragment_id in fragment_catalog
                ))
                practice_group = sorted(
                    [
                        fragment_catalog[fragment_id]
                        for fragment_id in practice_fragment_ids
                    ],
                    key=lambda item: item.ordinal,
                )
                fitted_practice = _v5_fit_group(practice_group)
                if (
                    fitted_practice
                    and [item.fragment_id for item in fitted_practice]
                    == [item.fragment_id for item in practice_group]
                ):
                    reserved_ids = set(practice_fragment_ids)
                    cleaned_episodes: list[TeachingEpisodeV2] = []
                    for episode in teaching_episodes:
                        cleaned_beats = [
                            beat.model_copy(update={
                                "fragment_ids": [
                                    fragment_id
                                    for fragment_id in beat.fragment_ids
                                    if fragment_id not in reserved_ids
                                ],
                            })
                            for beat in episode.beats
                        ]
                        cleaned_beats = [
                            beat for beat in cleaned_beats if beat.fragment_ids
                        ]
                        if cleaned_beats:
                            cleaned_episodes.append(
                                episode.model_copy(update={
                                    "beats": cleaned_beats,
                                })
                            )
                    teaching_episodes = cleaned_episodes
                    teaching_episodes.append(
                        original_practice.model_copy(update={
                            "beats": [
                                beat.model_copy(update={
                                    "layout_selection_reason": (
                                        "v5_semantic_grouping"
                                    ),
                                })
                                for beat in original_practice.beats
                            ],
                        })
                    )
        compact_chapters.append(chapter.model_copy(update={
            "episodes": [entry, *teaching_episodes, recap],
        }))
    return story.model_copy(update={"chapters": compact_chapters})


def slide_deck_v5_enabled() -> bool:
    return os.getenv(
        "SLIDE_DECK_V5_ENABLED",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeckCoverV5(_StrictModel):
    eyebrow: str = "课程课件"
    title: str
    subtitle: str = ""
    metadata_line: str = ""


class AgendaSectionV5(_StrictModel):
    agenda_id: str
    position: int = Field(ge=0)
    label: str
    learning_outcome: str = ""
    source_chapter_ids: list[str] = Field(min_length=1)


class DeckChapterV5(_StrictModel):
    chapter_id: str
    agenda_id: str
    position: int = Field(ge=0)
    eyebrow: str
    title: str
    driving_question: str
    learning_objective: str


class DeckClosingV5(_StrictModel):
    kind: Literal["course_synthesis"] = "course_synthesis"
    eyebrow: str = "课程总结"
    title: str
    source_chapter_ids: list[str] = Field(default_factory=list)


class DeckOutlineV5(_StrictModel):
    schema_version: Literal["deck_outline_v5"] = "deck_outline_v5"
    outline_version: str = DECK_OUTLINE_V5_VERSION
    outline_id: str
    source_document_revision: str
    communication_job: str
    cover: DeckCoverV5
    agenda_sections: list[AgendaSectionV5] = Field(min_length=1, max_length=6)
    chapters: list[DeckChapterV5] = Field(min_length=1)
    closing: DeckClosingV5
    planner: Literal["ai", "deterministic_fallback"] = "deterministic_fallback"
    fallback_reason: str = ""


class SlotBindingV5(_StrictModel):
    slot_id: str
    semantic_role: str
    source_block_id: str = ""
    item_index: int | None = None


class FinalPageContractV5(_StrictModel):
    schema_version: Literal["final_page_contract_v5"] = "final_page_contract_v5"
    contract_version: str = FINAL_PAGE_CONTRACT_V5_VERSION
    requested_layout: str
    resolved_layout: str
    requested_composition: str
    resolved_composition: str
    slot_bindings: list[SlotBindingV5] = Field(default_factory=list)
    visual_decision: Literal["accepted", "none"]
    layout_fallback_reason: str = ""
    major_region_count: int = Field(ge=1)
    occupied_major_region_count: int = Field(ge=0)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_chapter_title(value: str) -> str:
    cleaned = _CHAPTER_PREFIX.sub("", _clean_text(value))
    return cleaned.strip(" ：:、.-") or _clean_text(value)


def _balanced_groups(values: list[_T], group_count: int) -> list[list[_T]]:
    if not values:
        return []
    group_count = max(1, min(group_count, len(values)))
    base, remainder = divmod(len(values), group_count)
    result: list[list[T]] = []
    cursor = 0
    for index in range(group_count):
        size = base + (1 if index < remainder else 0)
        result.append(values[cursor : cursor + size])
        cursor += size
    return result


def _agenda_group_count(chapter_count: int) -> int:
    if chapter_count <= 6:
        return max(1, chapter_count)
    return min(6, max(3, math.ceil(chapter_count / 2)))


def _agenda_label(chapters: list[Any]) -> str:
    topics = [_clean_chapter_title(item.title) for item in chapters]
    if len(topics) == 1:
        return topics[0]
    if len(topics) == 2:
        return f"{topics[0]}与{topics[1]}"
    return f"{topics[0]}等{len(topics)}章"


def compile_deck_outline_v5(
    document: CourseDocument,
    story_plan: SlideStoryPlanV2 | dict[str, Any],
) -> DeckOutlineV5:
    """Compile the presentation-level opening, agenda, chapter, and closing plan."""
    story = (
        story_plan
        if isinstance(story_plan, SlideStoryPlanV2)
        else SlideStoryPlanV2.model_validate(story_plan)
    )
    grouped = _balanced_groups(
        story.chapters,
        _agenda_group_count(len(story.chapters)),
    )
    agenda_sections: list[AgendaSectionV5] = []
    agenda_for_chapter: dict[str, str] = {}
    for position, chapters in enumerate(grouped):
        chapter_ids = [chapter.chapter_id for chapter in chapters]
        agenda_id = stable_hash(
            {
                "position": position,
                "chapter_ids": chapter_ids,
                "revision": document.document_revision,
            },
            prefix="agenda_",
        )
        for chapter_id in chapter_ids:
            agenda_for_chapter[chapter_id] = agenda_id
        agenda_sections.append(AgendaSectionV5(
            agenda_id=agenda_id,
            position=position,
            label=_agenda_label(chapters),
            learning_outcome=_clean_text(chapters[-1].learning_objective),
            source_chapter_ids=chapter_ids,
        ))

    audience = _clean_text(story.communication_brief.audience) or "学习者"
    course_goal = _clean_text(story.communication_brief.course_goal) or document.title
    communication_job = f"帮助{audience}完成“{course_goal}”"
    cover = DeckCoverV5(
        eyebrow="课程课件",
        title=_clean_text(document.title),
        subtitle="",
        metadata_line=audience,
    )
    chapters = [
        DeckChapterV5(
            chapter_id=chapter.chapter_id,
            agenda_id=agenda_for_chapter[chapter.chapter_id],
            position=position,
            eyebrow=f"第{position + 1:02d}章",
            title=_clean_chapter_title(chapter.title),
            driving_question=_clean_text(chapter.driving_question),
            learning_objective=_clean_text(chapter.learning_objective),
        )
        for position, chapter in enumerate(story.chapters)
    ]
    closing = DeckClosingV5(
        title="把核心概念、方法与应用连成完整框架",
        source_chapter_ids=[chapter.chapter_id for chapter in story.chapters],
    )
    identity = {
        "course_id": document.course_id,
        "revision": document.document_revision,
        "plan_id": story.plan_id,
        "agenda": [item.model_dump(mode="json") for item in agenda_sections],
    }
    return DeckOutlineV5(
        outline_id=stable_hash(identity, prefix="outlinev5_"),
        source_document_revision=document.document_revision,
        communication_job=communication_job,
        cover=cover,
        agenda_sections=agenda_sections,
        chapters=chapters,
        closing=closing,
        planner=story.planner,
        fallback_reason=story.fallback_reason,
    )


def _meaningful_title(value: str) -> bool:
    cleaned = _clean_text(value)
    if _RAW_TITLE_PATTERN.search(cleaned):
        return False
    normalized = re.sub(
        r"[^\w\u4e00-\u9fff]+",
        "",
        cleaned,
        flags=re.UNICODE,
    ).lower()
    return normalized not in _GENERIC_TITLES and bool(normalized)


def _title_candidate(value: str) -> str:
    cleaned = _clean_text(value).strip("“”\"'")
    cleaned = re.sub(
        r"^\s*(?:文本|标题|图示|图解|caption)\s*[:：]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip("“”\"'")
    return cleaned if _meaningful_title(cleaned) else ""


def _first_body_sentence(value: str) -> str:
    return re.split(r"[。！？!?\n]", _clean_text(value), maxsplit=1)[0].strip()


def _body_text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(
        value
        for block in blocks
        for value in [
            _clean_text(block.get("content")),
            *[
                _clean_text(item)
                for item in block.get("items") or []
            ],
        ]
        if value
    )


def _normalize_title_match(value: Any) -> str:
    return re.sub(
        r"[\s，,；;：:。！？!?、]+$",
        "",
        _clean_text(value),
    )


def _page_density_metrics(slide: dict[str, Any]) -> dict[str, Any]:
    quality = slide.get("quality") or {}
    resolved_layout = str(
        quality.get("resolved_layout")
        or quality.get("requested_layout")
        or slide.get("layout")
        or "editorial-body"
    )
    budget = _V5_DENSITY_BUDGETS.get(
        resolved_layout,
        _V5_DEFAULT_DENSITY_BUDGET,
    )
    suppress_body = bool(quality.get("suppress_redundant_body"))
    body_values = []
    if not suppress_body:
        body_values.append(_clean_text(slide.get("key_message")))
        for block in slide.get("blocks") or []:
            body_values.extend([
                _clean_text(block.get("title")),
                _clean_text(block.get("content")),
                *[
                    _clean_text(item)
                    for item in block.get("items") or []
                ],
            ])
    body_character_count = sum(
        len(value)
        for value in body_values
        if value
    )
    item_count = sum(
        len([
            item
            for item in block.get("items") or []
            if _clean_text(item)
        ])
        for block in slide.get("blocks") or []
    )
    character_budget = int(budget["characters"])
    ratio = (
        body_character_count / character_budget
        if character_budget
        else (0.0 if body_character_count == 0 else float("inf"))
    )
    density_band = (
        "light"
        if ratio <= 0.45
        else "balanced"
        if ratio <= 0.8
        else "dense"
        if ratio <= 1
        else "overflow"
    )
    return {
        "title_character_count": len(_clean_text(slide.get("title"))),
        "title_character_budget": int(budget["title"]),
        "body_character_count": body_character_count,
        "body_character_budget": character_budget,
        "visible_item_count": item_count,
        "visible_item_budget": int(budget["items"]),
        "density_band": density_band,
        "minimum_body_font_pt": _V5_MINIMUM_BODY_FONT_PT,
        "minimum_title_font_pt": _V5_MINIMUM_TITLE_FONT_PT,
    }


def _structured_claim_title(value: str) -> str:
    claim = _clean_text(value).strip("“”\"'。！？!?")
    if "，" in claim and claim.startswith(("根据", "通过", "基于", "当", "如果")):
        claim = claim.split("，", 1)[1].strip()
    classification = re.fullmatch(
        r"(.{1,12}?)将(.{1,12}?)分为([一二三四五六七八九十\d]+)类",
        claim,
    )
    if classification:
        subject, topic, count = classification.groups()
        return f"{subject}{topic}的{count}种类型"
    return _bounded_title(claim)


def _bounded_title(value: str, limit: int = 24) -> str:
    cleaned = _clean_text(value).strip("：:，,。！？!?；;、")
    if len(cleaned) <= limit:
        return cleaned
    excerpt = cleaned[:limit]
    boundary = max(
        excerpt.rfind("，"),
        excerpt.rfind("；"),
        excerpt.rfind("："),
        excerpt.rfind("、"),
        excerpt.rfind(" "),
    )
    if boundary >= max(8, limit // 2):
        excerpt = excerpt[:boundary]
    return excerpt.strip("：:，,。！？!?；;、")


def compile_page_title_v5(
    *,
    explicit_title: str,
    primary_claim: str = "",
    body_text: str = "",
    fallback_context: str = "",
) -> str:
    """Compile one audience-facing title without promoting takeaway at render time."""
    explicit = _title_candidate(explicit_title)
    claim = _title_candidate(primary_claim)
    first_body = _title_candidate(_first_body_sentence(body_text))
    fallback = _title_candidate(fallback_context)
    if explicit:
        if explicit not in {claim, first_body} or len(explicit) <= 24:
            return _bounded_title(explicit)
        return _structured_claim_title(explicit)
    if claim:
        return _structured_claim_title(claim)
    if first_body:
        return _structured_claim_title(first_body)
    if fallback:
        return _structured_claim_title(fallback)
    return "课程内容"


def _remove_repeated_lead_sentence(
    blocks: list[dict[str, Any]],
    title: str,
) -> tuple[list[dict[str, Any]], bool]:
    target = _normalize_title_match(title)
    updated = deepcopy(blocks)
    changed = False
    for block in updated:
        content = str(block.get("content") or "")
        first = _first_body_sentence(content)
        if first and _normalize_title_match(first) == target:
            remainder = content[len(first):].lstrip("。！？!?；;：:，, \n")
            block["content"] = remainder
            changed = True
            break
        items = list(block.get("items") or [])
        if (
            items
            and _normalize_title_match(
                _first_body_sentence(items[0])
            ) == target
        ):
            first_item_sentence = _first_body_sentence(items[0])
            remainder = str(items[0])[len(first_item_sentence):].lstrip(
                "。！？!?；;：:，, "
            )
            block["items"] = (
                [remainder, *items[1:]]
                if remainder
                else items[1:]
            )
            changed = True
            break
    if changed:
        updated = [
            block
            for block in updated
            if (
                _clean_text(block.get("title"))
                or _clean_text(block.get("content"))
                or any(_clean_text(item) for item in block.get("items") or [])
            )
        ]
    return updated, changed


def _semantic_bindings(slide: dict[str, Any]) -> list[SlotBindingV5]:
    bindings: list[SlotBindingV5] = []
    for block_index, block in enumerate(slide.get("blocks") or []):
        block_id = str(block.get("block_id") or f"block-{block_index + 1}")
        block_type = str(block.get("type") or "rich_text")
        items = [_clean_text(item) for item in block.get("items") or [] if _clean_text(item)]
        if block_type == "process":
            for item_index, _item in enumerate(items):
                bindings.append(SlotBindingV5(
                    slot_id=f"step-{item_index + 1}",
                    semantic_role="process_step",
                    source_block_id=block_id,
                    item_index=item_index,
                ))
            continue
        if block_type == "formula" or (block.get("metadata") or {}).get("formula"):
            bindings.append(SlotBindingV5(
                slot_id="formula",
                semantic_role="formula",
                source_block_id=block_id,
            ))
            if _clean_text(block.get("content")):
                bindings.append(SlotBindingV5(
                    slot_id="formula-interpretation",
                    semantic_role="formula_interpretation",
                    source_block_id=block_id,
                ))
            continue
        if items:
            semantic_role = (
                "classification_item"
                if len(items) == 3
                else "comparison_side"
                if len(items) == 2
                else "list_item"
            )
            for item_index, _item in enumerate(items):
                bindings.append(SlotBindingV5(
                    slot_id=f"item-{block_index + 1}-{item_index + 1}",
                    semantic_role=semantic_role,
                    source_block_id=block_id,
                    item_index=item_index,
                ))
            continue
        if _clean_text(block.get("content")) or _clean_text(block.get("title")):
            bindings.append(SlotBindingV5(
                slot_id=f"text-{block_index + 1}",
                semantic_role="text",
                source_block_id=block_id,
            ))
    if slide.get("visuals"):
        bindings.append(SlotBindingV5(
            slot_id="visual",
            semantic_role="visual",
        ))
    return bindings


def resolve_page_contract_v5(slide: dict[str, Any]) -> FinalPageContractV5:
    """Resolve a render-safe layout after visual assets are known."""
    quality = slide.get("quality") or {}
    requested_layout = str(
        quality.get("requested_layout")
        or slide.get("layout")
        or "editorial-body"
    )
    requested_composition = str(
        quality.get("requested_composition")
        or slide.get("composition")
        or "statement"
    )
    bindings = _semantic_bindings(slide)
    non_visual = [item for item in bindings if item.semantic_role != "visual"]
    has_visual = any(item.semantic_role == "visual" for item in bindings)
    visual_decision: Literal["accepted", "none"] = "accepted" if has_visual else "none"
    classification = [
        item for item in non_visual
        if item.semantic_role == "classification_item"
    ]
    fallback_reason = ""

    if requested_layout in {"cover", "cover-minimal"}:
        resolved_layout = "cover-minimal"
        resolved_composition = "statement"
        major_regions = 1
    elif requested_layout in {"roadmap", "agenda-linear"}:
        resolved_layout = "agenda-linear"
        resolved_composition = "sequence"
        major_regions = 1
    elif requested_layout in {"chapter", "chapter-entry", "section-divider"}:
        resolved_layout = "chapter-entry"
        resolved_composition = "statement"
        major_regions = 1
    elif requested_layout == "worked-example":
        if len(non_visual) < 2:
            resolved_layout = "editorial-body"
            resolved_composition = "statement"
            major_regions = 1
            fallback_reason = "worked_example_without_reasoning_steps"
        elif len(non_visual) > 3:
            resolved_layout = "editorial-body"
            resolved_composition = "statement"
            major_regions = 1
            fallback_reason = "worked_example_item_overflow"
        else:
            resolved_layout = "worked-example"
            resolved_composition = "sequence"
            major_regions = min(3, len(non_visual))
    elif requested_layout == "practice-feedback":
        distinct_source_blocks = {
            item.source_block_id
            for item in non_visual
            if item.source_block_id
        }
        if len(distinct_source_blocks) < 2:
            resolved_layout = "editorial-body"
            resolved_composition = "statement"
            major_regions = 1
            fallback_reason = "practice_without_feedback"
        else:
            resolved_layout = "practice-feedback"
            resolved_composition = "exercise"
            major_regions = 2
    elif requested_layout in {"recap", "chapter-recap", "summary", "course-synthesis"}:
        resolved_layout = (
            "course-synthesis"
            if requested_layout == "course-synthesis"
            else "chapter-recap"
        )
        resolved_composition = "statement"
        major_regions = 1
    elif len(classification) == 3:
        resolved_layout = "classification-3"
        resolved_composition = "statement"
        major_regions = 3
        if requested_layout != resolved_layout:
            fallback_reason = "classification_requires_three_regions"
    elif requested_layout in {"editorial-body", "hero-statement"}:
        resolved_layout = "editorial-body"
        resolved_composition = "statement"
        major_regions = 1
    elif requested_layout in {"two-column", "positive-negative", "balanced-two-column"}:
        if len(non_visual) < 2:
            resolved_layout = "editorial-body"
            resolved_composition = "statement"
            major_regions = 1
            fallback_reason = "single_group_two_column"
        else:
            resolved_layout = "balanced-two-column"
            resolved_composition = "statement"
            major_regions = 2
    elif not has_visual and (
        requested_layout in _VISUAL_REQUIRED_LAYOUTS
        or requested_composition in _VISUAL_COMPOSITIONS
    ):
        resolved_layout = (
            "balanced-two-column"
            if len(non_visual) == 2
            else "editorial-body"
        )
        resolved_composition = "statement"
        major_regions = 2 if resolved_layout == "balanced-two-column" else 1
        fallback_reason = "visual_layout_without_visual"
    elif has_visual and not non_visual:
        resolved_layout = "diagram-full"
        resolved_composition = "diagram-full"
        major_regions = 1
    elif has_visual:
        resolved_layout = (
            requested_layout
            if requested_layout in _VISUAL_REQUIRED_LAYOUTS
            else "figure-text"
        )
        resolved_composition = (
            requested_composition
            if requested_composition in _VISUAL_COMPOSITIONS
            else "split-visual"
        )
        major_regions = 2
    elif any(item.semantic_role == "process_step" for item in non_visual):
        resolved_layout = "process-sequence"
        resolved_composition = "sequence"
        major_regions = 1
    elif any(item.semantic_role == "formula" for item in non_visual):
        resolved_layout = "formula-explanation"
        resolved_composition = "statement"
        major_regions = 1
    elif len(non_visual) == 2:
        resolved_layout = "balanced-two-column"
        resolved_composition = "statement"
        major_regions = 2
    else:
        resolved_layout = "editorial-body"
        resolved_composition = "statement"
        major_regions = 1

    occupied = min(major_regions, len(non_visual) + (1 if has_visual else 0))
    return FinalPageContractV5(
        requested_layout=requested_layout,
        resolved_layout=resolved_layout,
        requested_composition=requested_composition,
        resolved_composition=resolved_composition,
        slot_bindings=bindings,
        visual_decision=visual_decision,
        layout_fallback_reason=fallback_reason,
        major_region_count=major_regions,
        occupied_major_region_count=occupied,
    )


def apply_page_contract_v5(slide: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(slide)
    contract = resolve_page_contract_v5(updated)
    quality = deepcopy(updated.get("quality") or {})
    quality.update({
        "requested_layout": contract.requested_layout,
        "resolved_layout": contract.resolved_layout,
        "requested_composition": contract.requested_composition,
        "resolved_composition": contract.resolved_composition,
        "slot_bindings": [
            item.model_dump(mode="json") for item in contract.slot_bindings
        ],
        "visual_decision": contract.visual_decision,
        "layout_fallback_reason": contract.layout_fallback_reason,
        "major_region_count": contract.major_region_count,
        "occupied_major_region_count": contract.occupied_major_region_count,
    })
    updated["quality"] = quality
    updated["composition"] = contract.resolved_composition
    if str(updated.get("layout") or "") not in {"cover", "roadmap", "chapter", "recap"}:
        body_text = _body_text_from_blocks(
            list(updated.get("blocks") or [])
        )
        updated["title"] = compile_page_title_v5(
            explicit_title=str(updated.get("title") or ""),
            primary_claim=str(
                (updated.get("primary_claim_source") or {}).get("text")
                or updated.get("takeaway")
                or ""
            ),
            body_text=body_text,
            fallback_context=str(
                next(
                    (
                        block.get("title")
                        for block in updated.get("blocks") or []
                        if _title_candidate(block.get("title"))
                    ),
                    "",
                )
                or updated.get("teaching_job")
                or updated.get("eyebrow")
                or ""
            ),
        )
        deduplicated_blocks, removed_lead = _remove_repeated_lead_sentence(
            list(updated.get("blocks") or []),
            updated["title"],
        )
        if removed_lead:
            updated["blocks"] = deduplicated_blocks
            contract = resolve_page_contract_v5(updated)
            quality.update({
                "resolved_layout": contract.resolved_layout,
                "resolved_composition": contract.resolved_composition,
                "slot_bindings": [
                    item.model_dump(mode="json")
                    for item in contract.slot_bindings
                ],
                "visual_decision": contract.visual_decision,
                "layout_fallback_reason": contract.layout_fallback_reason,
                "major_region_count": contract.major_region_count,
                "occupied_major_region_count": (
                    contract.occupied_major_region_count
                ),
            })
            updated["composition"] = contract.resolved_composition
            body_text = _body_text_from_blocks(
                list(updated.get("blocks") or [])
            )
        blocks = list(updated.get("blocks") or [])
        single_claim_block = (
            len(blocks) == 1
            and bool(_clean_text(blocks[0].get("content")))
            and not any(
                _clean_text(item)
                for item in blocks[0].get("items") or []
            )
            and not updated.get("visuals")
        )
        if (
            single_claim_block
            and _normalize_title_match(updated["title"])
            == _normalize_title_match(_first_body_sentence(body_text))
        ):
            quality.update({
                "resolved_layout": "hero-claim",
                "resolved_composition": "statement",
                "suppress_redundant_body": True,
                "major_region_count": 1,
                "occupied_major_region_count": 1,
            })
            updated["composition"] = "statement"
    quality.update(_page_density_metrics(updated))
    return updated


def _chapter_entry_slide(chapter: DeckChapterV5) -> dict[str, Any]:
    return {
        "unit_id": f"slide:v5:chapter:{chapter.chapter_id}",
        "position": 0,
        "layout": "chapter",
        "slide_purpose": "chapter_open",
        "eyebrow": chapter.eyebrow,
        "title": chapter.title,
        "subtitle": "",
        "key_message": chapter.driving_question or chapter.learning_objective,
        "teaching_job": "",
        "takeaway": "",
        "transition_from": "",
        "composition": "statement",
        "visuals": [],
        "blocks": [],
        "speaker_notes": "",
        "section_id": chapter.chapter_id,
        "source_section_ids": [chapter.chapter_id],
        "source_block_ids": [],
        "source_keys": [f"section:{chapter.chapter_id}"],
        "learning_objective_ids": [],
        "practice_task_ids": [],
        "practice_source_revisions": {},
        "knowledge_refs": [],
        "ability_refs": [],
        "misconception_refs": [],
        "mastery_refs": [],
        "knowledge_labels": [],
        "ability_labels": [],
        "chapter_id": chapter.chapter_id,
        "episode_id": "",
        "scene_kind": "chapter_entry",
        "beat_role": "navigation",
        "primary_claim_source": {},
        "prerequisite_refs": [],
        "mastery_criterion_refs": [],
        "layout_selection_reason": "required_v5_chapter_entry",
        "quality": {
            "requested_layout": "chapter-entry",
            "navigation_only": True,
        },
    }


def _chapter_recap_slide(
    chapter: DeckChapterV5,
    source_slides: list[dict[str, Any]],
) -> dict[str, Any]:
    points: list[str] = []
    for slide in source_slides:
        candidate = _clean_text(slide.get("title"))
        if candidate and candidate not in points:
            points.append(candidate)
        if len(points) == 4:
            break
    if not points:
        points = [chapter.learning_objective or chapter.title]
    return {
        "unit_id": f"slide:v5:chapter-recap:{chapter.chapter_id}",
        "position": 0,
        "layout": "recap",
        "slide_purpose": "chapter_recap",
        "eyebrow": "章节回顾",
        "title": "回看本章形成的关键判断",
        "subtitle": "",
        "key_message": "",
        "teaching_job": "",
        "takeaway": "",
        "transition_from": "",
        "composition": "statement",
        "visuals": [],
        "blocks": [{
            "block_id": f"slide:v5:chapter-recap:{chapter.chapter_id}:points",
            "type": "bullets",
            "title": "",
            "content": "",
            "items": points,
            "metadata": {
                "derived_text": True,
                "source_slide_ids": [
                    str(slide.get("unit_id") or "") for slide in source_slides
                ],
            },
        }],
        "speaker_notes": "",
        "section_id": chapter.chapter_id,
        "source_section_ids": [chapter.chapter_id],
        "source_block_ids": [],
        "source_keys": [f"section:{chapter.chapter_id}"],
        "learning_objective_ids": [],
        "practice_task_ids": [],
        "practice_source_revisions": {},
        "knowledge_refs": [],
        "ability_refs": [],
        "misconception_refs": [],
        "mastery_refs": [],
        "knowledge_labels": [],
        "ability_labels": [],
        "chapter_id": chapter.chapter_id,
        "episode_id": "",
        "scene_kind": "chapter_recap",
        "beat_role": "navigation",
        "primary_claim_source": {},
        "prerequisite_refs": [],
        "mastery_criterion_refs": [],
        "layout_selection_reason": "required_v5_chapter_recap",
        "quality": {
            "requested_layout": "chapter-recap",
            "navigation_only": True,
        },
    }


def _course_synthesis_slide(outline: DeckOutlineV5) -> dict[str, Any]:
    return {
        "unit_id": "slide:v5:course-synthesis",
        "position": 0,
        "layout": "recap",
        "slide_purpose": "course_recap",
        "eyebrow": outline.closing.eyebrow,
        "title": outline.closing.title,
        "subtitle": "",
        "key_message": "",
        "teaching_job": "",
        "takeaway": "",
        "transition_from": "",
        "composition": "statement",
        "visuals": [],
        "blocks": [{
            "block_id": "slide:v5:course-synthesis:route",
            "type": "process",
            "title": "",
            "content": "",
            "items": [item.label for item in outline.agenda_sections],
            "metadata": {
                "derived_text": True,
                "source_chapter_ids": outline.closing.source_chapter_ids,
            },
        }],
        "speaker_notes": "",
        "section_id": None,
        "source_section_ids": outline.closing.source_chapter_ids,
        "source_block_ids": [],
        "source_keys": [
            f"section:{chapter_id}"
            for chapter_id in outline.closing.source_chapter_ids
        ],
        "learning_objective_ids": [],
        "practice_task_ids": [],
        "practice_source_revisions": {},
        "knowledge_refs": [],
        "ability_refs": [],
        "misconception_refs": [],
        "mastery_refs": [],
        "knowledge_labels": [],
        "ability_labels": [],
        "chapter_id": "",
        "episode_id": "",
        "scene_kind": "course_synthesis",
        "beat_role": "closure",
        "primary_claim_source": {},
        "prerequisite_refs": [],
        "mastery_criterion_refs": [],
        "layout_selection_reason": "required_v5_course_synthesis",
        "quality": {
            "requested_layout": "course-synthesis",
            "navigation_only": True,
        },
    }


def _materialize_v5_structure(
    slides: list[dict[str, Any]],
    outline: DeckOutlineV5,
) -> list[dict[str, Any]]:
    existing = [deepcopy(slide) for slide in slides]
    cover = next(
        (slide for slide in existing if slide.get("layout") == "cover"),
        None,
    )
    roadmap = next(
        (slide for slide in existing if slide.get("layout") == "roadmap"),
        None,
    )
    teaching = [
        slide for slide in existing
        if slide is not cover and slide is not roadmap
        and str(slide.get("unit_id") or "") != "slide:summary"
    ]
    result: list[dict[str, Any]] = []
    if cover:
        cover.update({
            "eyebrow": outline.cover.eyebrow,
            "title": outline.cover.title,
            "subtitle": "",
            "key_message": "",
            "blocks": [],
            "quality": {
                **(cover.get("quality") or {}),
                "requested_layout": "cover-minimal",
            },
        })
        result.append(cover)
    if roadmap:
        roadmap.update({
            "eyebrow": "学习导览",
            "title": "课程路线",
            "subtitle": "",
            "key_message": "",
            "blocks": [{
                "block_id": "slide:roadmap:agenda",
                "type": "process",
                "title": "",
                "content": "",
                "items": [item.label for item in outline.agenda_sections],
                "metadata": {
                    "derived_text": True,
                    "agenda_sections": [
                        item.model_dump(mode="json")
                        for item in outline.agenda_sections
                    ],
                },
            }],
            "source_section_ids": [
                chapter_id
                for item in outline.agenda_sections
                for chapter_id in item.source_chapter_ids
            ],
            "quality": {
                **(roadmap.get("quality") or {}),
                "requested_layout": "agenda-linear",
            },
        })
        result.append(roadmap)

    used_units = {str(slide.get("unit_id") or "") for slide in result}
    chapter_ids = {chapter.chapter_id for chapter in outline.chapters}
    for chapter in outline.chapters:
        chapter_slides = [
            slide for slide in teaching
            if str(slide.get("chapter_id") or "") == chapter.chapter_id
        ]
        existing_entry = next((
            slide for slide in chapter_slides
            if (
                str(slide.get("scene_kind") or "") == "chapter_entry"
                or str(slide.get("layout") or "") == "chapter"
            )
        ), None)
        entry = existing_entry or _chapter_entry_slide(chapter)
        if entry["unit_id"] not in used_units:
            result.append(entry)
            used_units.add(entry["unit_id"])
        existing_recap = next((
            slide for slide in chapter_slides
            if str(slide.get("scene_kind") or "") == "chapter_recap"
        ), None)
        body_slides = [
            slide for slide in chapter_slides
            if slide is not existing_entry and slide is not existing_recap
        ]
        result.extend(body_slides)
        used_units.update(str(slide.get("unit_id") or "") for slide in body_slides)
        recap = existing_recap or _chapter_recap_slide(chapter, body_slides)
        if recap["unit_id"] not in used_units:
            result.append(recap)
            used_units.add(recap["unit_id"])

    result.extend([
        slide for slide in teaching
        if str(slide.get("unit_id") or "") not in used_units
        and str(slide.get("chapter_id") or "") not in chapter_ids
    ])
    result.append(_course_synthesis_slide(outline))
    for position, slide in enumerate(result):
        slide["position"] = position
    return result


def build_signature_v5(
    *,
    document: CourseDocument,
    course_data: dict[str, Any],
    mode: str,
    theme: str,
) -> dict[str, Any]:
    base = build_signature_v4(
        document=document,
        course_data=course_data,
        mode=mode,  # type: ignore[arg-type]
        theme=theme,  # type: ignore[arg-type]
    )
    fields = {
        **{key: value for key, value in base.items() if key != "signature"},
        "compiler_version": SLIDE_DECK_V5_COMPILER_VERSION,
        "deck_outline_version": DECK_OUTLINE_V5_VERSION,
        "final_page_contract_version": FINAL_PAGE_CONTRACT_V5_VERSION,
    }
    return {
        **fields,
        "signature": stable_hash(fields, prefix="slidebuildv5_"),
    }


def v5_contract_issues(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for slide in slides:
        quality = slide.get("quality") or {}
        requested = str(quality.get("requested_layout") or "")
        resolved = str(quality.get("resolved_layout") or "")
        visuals = slide.get("visuals") or []
        occupied = int(quality.get("occupied_major_region_count") or 0)
        regions = int(quality.get("major_region_count") or 1)
        if resolved in {"balanced-two-column", "figure-text"} and occupied < 2:
            issues.append({
                "severity": "critical",
                "code": "required_slot_unfilled",
                "page_id": slide.get("unit_id"),
            })
        if not visuals and (
            resolved in _VISUAL_REQUIRED_LAYOUTS
            or str(quality.get("resolved_composition") or "") in _VISUAL_COMPOSITIONS
        ):
            issues.append({
                "severity": "critical",
                "code": "visual_layout_without_visual",
                "page_id": slide.get("unit_id"),
            })
        if regions > 1 and occupied < regions:
            issues.append({
                "severity": "critical",
                "code": "empty_major_region",
                "page_id": slide.get("unit_id"),
            })
        title = _clean_text(slide.get("title"))
        if _RAW_TITLE_PATTERN.search(title):
            issues.append({
                "severity": "critical",
                "code": "raw_source_sentence_as_title",
                "page_id": slide.get("unit_id"),
            })
        density = _page_density_metrics(slide)
        if (
            density["title_character_count"]
            > density["title_character_budget"]
        ):
            issues.append({
                "severity": "critical",
                "code": "slide_title_overflow",
                "page_id": slide.get("unit_id"),
            })
        if (
            density["body_character_count"]
            > density["body_character_budget"]
        ):
            issues.append({
                "severity": "critical",
                "code": "body_density_overflow",
                "page_id": slide.get("unit_id"),
            })
        if (
            density["visible_item_count"]
            > density["visible_item_budget"]
        ):
            issues.append({
                "severity": "critical",
                "code": "visible_item_overflow",
                "page_id": slide.get("unit_id"),
            })
        body_text = " ".join(
            _clean_text(value)
            for block in slide.get("blocks") or []
            for value in [
                block.get("content"),
                *((block.get("items") or [])),
            ]
            if _clean_text(value)
        )
        first_body = _first_body_sentence(body_text)
        if (
            title
            and first_body
            and _normalize_title_match(title) == _normalize_title_match(first_body)
            and not bool(quality.get("suppress_redundant_body"))
        ):
            issues.append({
                "severity": "critical",
                "code": "title_body_duplication",
                "page_id": slide.get("unit_id"),
            })
        formula_visual = any(
            str(visual.get("kind") or "") == "formula"
            for visual in visuals
        )
        formula_interpretation = any(
            str(binding.get("semantic_role") or "") == "formula_interpretation"
            for binding in quality.get("slot_bindings") or []
            if isinstance(binding, dict)
        )
        if formula_visual and not formula_interpretation and not body_text:
            issues.append({
                "severity": "critical",
                "code": "orphan_formula",
                "page_id": slide.get("unit_id"),
            })
        if requested in {"two-column", "positive-negative"} and resolved == "editorial-body":
            continue
    return issues


def summarize_v5_slide_counts(
    slides: list[dict[str, Any]],
) -> dict[str, int]:
    appendix = sum(
        1
        for slide in slides
        if (
            bool((slide.get("quality") or {}).get("appendix"))
            or str(slide.get("layout") or "") == "appendix"
            or str(slide.get("narrative_role") or "") == "appendix"
        )
    )
    return {
        "main_slide_count": len(slides) - appendix,
        "appendix_slide_count": appendix,
        "total_slide_count": len(slides),
    }


def _v5_issue_identity(issue: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(issue.get("severity") or ""),
        str(issue.get("code") or ""),
        str(
            issue.get("page_id")
            or issue.get("slide_id")
            or issue.get("target")
            or ""
        ),
    )


def _v5_semantic_issue(issue: dict[str, Any]) -> bool:
    code = str(issue.get("code") or "")
    return (
        code in {
            "ai_story_planner_failed",
            "ai_story_planner_unavailable",
            "knowledge_binding_missing",
            "official_source_revision_mismatch",
            "raw_source_sentence_as_title",
            "title_body_duplication",
        }
        or code.startswith(
            (
                "ai_story_",
                "concise_",
                "fragment_",
                "knowledge_",
                "official_",
                "source_",
            )
        )
    )


def finalize_v5_quality_report(
    *,
    previous_quality: dict[str, Any],
    slides: list[dict[str, Any]],
    planner: str,
    fallback_reason: str,
) -> dict[str, Any]:
    """Replace stale V3/V4 gates with one internally consistent V5 report."""
    previous_candidates = [
        *(previous_quality.get("blockers") or []),
        *((previous_quality.get("semantic") or {}).get("issues") or []),
        *((previous_quality.get("visual") or {}).get("issues") or []),
    ]
    retained = [
        deepcopy(issue)
        for issue in previous_candidates
        if str(issue.get("code") or "") not in _V5_REPLACED_V4_QUALITY_CODES
    ]
    planning_issues: list[dict[str, Any]] = []
    if fallback_reason == "invalid_or_failed_ai_story_plan":
        planning_issues.append({
            "severity": "critical",
            "code": "ai_story_planner_failed",
            "target": "deck",
            "message": (
                "AI story planning failed validation; the deterministic fallback "
                "was not published as a quality-equivalent V5 deck."
            ),
            "suggestion": "Retry the build after the AI planner is available.",
        })
    elif planner != "ai":
        planning_issues.append({
            "severity": "major",
            "code": "ai_story_planner_unavailable",
            "target": "deck",
            "message": (
                "The deck used deterministic story planning because no AI planner "
                "was available."
            ),
            "suggestion": "Configure the AI provider to enable semantic planning.",
        })

    combined = [
        *retained,
        *v5_contract_issues(slides),
        *planning_issues,
    ]
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for issue in combined:
        identity = _v5_issue_identity(issue)
        if identity in seen:
            continue
        seen.add(identity)
        issues.append(issue)

    blockers = [
        issue for issue in issues
        if str(issue.get("severity") or "") == "critical"
    ]
    warnings = [
        issue for issue in issues
        if str(issue.get("severity") or "") != "critical"
    ]
    semantic_issues = [
        issue for issue in issues
        if _v5_semantic_issue(issue)
    ]
    visual_issues = [
        issue for issue in issues
        if issue not in semantic_issues
    ]
    score = max(
        0,
        100 - sum(
            {
                "critical": 20,
                "major": 6,
                "minor": 1,
            }.get(str(issue.get("severity") or ""), 1)
            for issue in issues
        ),
    )
    passthrough = {
        key: deepcopy(value)
        for key, value in previous_quality.items()
        if key not in {
            "passed",
            "score",
            "issues",
            "blockers",
            "warnings",
            "semantic",
            "visual",
            "v5_composition",
        }
    }
    contract_issues = v5_contract_issues(slides)
    return {
        **passthrough,
        "passed": not blockers,
        "score": score,
        "issues": issues,
        "blockers": blockers,
        "warnings": warnings,
        "semantic": {
            "passed": not any(
                str(issue.get("severity") or "") == "critical"
                for issue in semantic_issues
            ),
            "issues": semantic_issues,
        },
        "visual": {
            "passed": not any(
                str(issue.get("severity") or "") == "critical"
                for issue in visual_issues
            ),
            "issues": visual_issues,
        },
        "planning": {
            "planner": planner,
            "fallback_reason": fallback_reason,
            "passed": not any(
                str(issue.get("severity") or "") == "critical"
                for issue in planning_issues
            ),
            "issues": planning_issues,
        },
        "v5_composition": {
            "passed": not contract_issues,
            "issues": contract_issues,
        },
    }


def compile_slide_deck_v5(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    story_plan: SlideStoryPlanV2 | dict[str, Any],
    allocation_plan: Any | None = None,
    visual_plan: Any | None = None,
    progress_callback: Any | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
    asset_repository: Any | None = None,
) -> dict[str, Any]:
    story = (
        story_plan
        if isinstance(story_plan, SlideStoryPlanV2)
        else SlideStoryPlanV2.model_validate(story_plan)
    )
    source_fragments = fragment_course_document(document)
    compact_story = compact_story_plan_v5(
        document,
        story,
        source_fragments,
    )
    compact_allocation, _ = allocation_from_story_plan_v2(
        document,
        source_fragments,
        compact_story,
    )
    provided_page_count = (
        len(allocation_plan.pages)
        if hasattr(allocation_plan, "pages")
        else len((allocation_plan or {}).get("pages") or [])
        if isinstance(allocation_plan, dict)
        else 10**9
    )
    if len(compact_allocation.pages) < provided_page_count:
        story = compact_story
        allocation_plan = compact_allocation
    content = compile_slide_deck_v4(
        document,
        course_data,
        story_plan=story,
        allocation_plan=allocation_plan,
        visual_plan=visual_plan,
        progress_callback=progress_callback,
        resume_slides=resume_slides,
        asset_repository=asset_repository,
    )
    outline = compile_deck_outline_v5(document, story)
    slides = _materialize_v5_structure(
        list(content.get("slides") or []),
        outline,
    )
    for slide in slides:
        scene_kind = str(slide.get("scene_kind") or "")
        beat_role = str(slide.get("beat_role") or "")
        scene_layout = (
            "worked-example"
            if scene_kind == "worked_example"
            else "practice-feedback"
            if (
                scene_kind == "practice_feedback"
                and beat_role in {"feedback", "answer", "validation"}
            )
            else "editorial-body"
            if scene_kind == "practice_feedback"
            else None
        )
        if scene_layout:
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "requested_layout": scene_layout,
            }
    slides = [apply_page_contract_v5(slide) for slide in slides]
    previous_quality = deepcopy(content.get("quality_report") or {})
    content.update({
        "schema_version": SLIDE_DECK_V5_SCHEMA,
        "slides": slides,
        "deck_outline": outline.model_dump(mode="json"),
        "build_signature": build_signature_v5(
            document=document,
            course_data=course_data,
            mode=story.mode,
            theme=story.theme,
        ),
        "layout_plan": {
            "schema_version": "slide_layout_plan_v5",
            "contract_version": FINAL_PAGE_CONTRACT_V5_VERSION,
            "pages": [
                {
                    "page_id": slide.get("unit_id"),
                    "requested_layout": (slide.get("quality") or {}).get(
                        "requested_layout"
                    ),
                    "resolved_layout": (slide.get("quality") or {}).get(
                        "resolved_layout"
                    ),
                    "resolved_composition": (slide.get("quality") or {}).get(
                        "resolved_composition"
                    ),
                    "slot_bindings": (slide.get("quality") or {}).get(
                        "slot_bindings"
                    ) or [],
                }
                for slide in slides
            ],
        },
    })
    content["quality_report"] = finalize_v5_quality_report(
        previous_quality=previous_quality,
        slides=slides,
        planner=outline.planner,
        fallback_reason=outline.fallback_reason,
    )
    content["quality_summary"] = {
        **(content.get("quality_summary") or {}),
        "passed": content["quality_report"]["passed"],
        "score": content["quality_report"]["score"],
        **summarize_v5_slide_counts(slides),
    }
    return content


def validate_slide_deck_v5(
    content: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if content.get("schema_version") != SLIDE_DECK_V5_SCHEMA:
        raise ValueError("Expected slide_deck_v5 content")
    DeckOutlineV5.model_validate(content.get("deck_outline") or {})
    compatibility = deepcopy(content)
    compatibility["schema_version"] = SLIDE_DECK_V4_SCHEMA
    base = validate_slide_deck_v4(compatibility, course_data=course_data)
    outline = content.get("deck_outline") or {}
    return finalize_v5_quality_report(
        previous_quality=base,
        slides=list(content.get("slides") or []),
        planner=str(outline.get("planner") or ""),
        fallback_reason=str(outline.get("fallback_reason") or ""),
    )
