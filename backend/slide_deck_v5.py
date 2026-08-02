"""Deck-level narrative and final page contracts for slide_deck_v5."""

from __future__ import annotations

import math
import os
import re
from copy import deepcopy
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, stable_hash
from slide_deck import SlideDeckContent
from slide_deck_v4 import (
    SLIDE_DECK_V4_SCHEMA,
    allocation_from_story_plan_v2,
    build_signature_v4,
    compile_slide_deck_v4,
    validate_slide_deck_v4,
)
from slide_deck_v3 import fragment_course_document
from slide_visuals import deterministic_visual_plan
from slide_story_plan import (
    ClaimSourceV2,
    SlideStoryPlanV2,
    StoryBeatV2,
    TeachingEpisodeV2,
    V5_SEMANTIC_CORE_REASONS,
)

SLIDE_DECK_V5_SCHEMA = "slide_deck_v5"
SLIDE_DECK_V5_COMPILER_VERSION = "course_logic_slide_compiler_v5.10"
DECK_OUTLINE_V5_VERSION = "deck_outline_v5.0"
FINAL_PAGE_CONTRACT_V5_VERSION = "final_page_contract_v5.3"

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
    r"\d+(?:\s*[.．]\s*\d+)+\s*|"
    r"[一二三四五六七八九十百\d]+\s*[.、．:：])\s*"
)
_NUMBERED_SECTION_TITLE_PATTERN = re.compile(
    r"^\s*\d+(?:\s*[.．]\s*\d+)+\s+\S+"
)
_ENUMERATION_PROMISE_PATTERN = re.compile(
    r"(?:分为|分成|可分为|包括|包含|共有|共计)"
    r"\s*([一二两三四五六七八九十百\d]+)\s*"
    r"(?:类|种|项|个|步|部分|方面|阶段)"
)
_TITLE_ENUMERATION_PATTERN = re.compile(
    r"([一二两三四五六七八九十百\d]+)\s*"
    r"(?:类|种|项|个|步|部分|方面|阶段)"
)
_RAW_TITLE_PATTERN = re.compile(
    r"(?:^\s*>?\s*(?:ID|graph|flowchart|sequenceDiagram|classDiagram)\s*[:\s]|"
    r"-->|```|^\s*\\(?:begin|frac|Delta|sum|int)\b)",
    re.IGNORECASE,
)
_TEMPLATE_LEAD_PATTERN = re.compile(
    r"^\s*[^\w\u4e00-\u9fff]*\s*"
    r"(?:核心概念与背景|核心概念|背景与意义|关键名词解释|"
    r"实战案例(?:/行业应用)?|思考与挑战|练习与思考|"
    r"深度原理/底层机制|行业应用)\s*[:：]?\s*"
)
_V5_DEFAULT_DENSITY_BUDGET = {"characters": 360, "items": 6, "title": 18}
_V5_DENSITY_BUDGETS = {
    "cover-minimal": {"characters": 90, "items": 0, "title": 22},
    "cover-editorial": {"characters": 120, "items": 0, "title": 22},
    "agenda-linear": {"characters": 240, "items": 6, "title": 18},
    "chapter-entry": {"characters": 120, "items": 0, "title": 22},
    "hero-claim": {"characters": 180, "items": 1, "title": 18},
    "editorial-body": {"characters": 360, "items": 6, "title": 18},
    "balanced-two-column": {"characters": 420, "items": 6, "title": 18},
    "classification-3": {"characters": 270, "items": 3, "title": 18},
    "parallel-examples": {"characters": 320, "items": 4, "title": 18},
    "question-prompt": {"characters": 260, "items": 4, "title": 18},
    "process-sequence": {"characters": 300, "items": 5, "title": 18},
    "formula-explanation": {"characters": 280, "items": 4, "title": 18},
    "figure-text": {"characters": 320, "items": 5, "title": 18},
    "diagram-full": {"characters": 0, "items": 0, "title": 18},
    "worked-example": {"characters": 360, "items": 3, "title": 18},
    "practice-feedback": {"characters": 400, "items": 5, "title": 18},
    "chapter-recap": {"characters": 320, "items": 4, "title": 18},
    "course-synthesis": {"characters": 340, "items": 6, "title": 18},
}
_V5_MINIMUM_BODY_FONT_PT = 16
_V5_MINIMUM_TITLE_FONT_PT = 35
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
    if re.search(r"应用|迁移|行业|情境|application|transfer", headings, re.I):
        return "application"
    if re.search(r"案例|例题|示例|实战|case|example", headings, re.I):
        return "worked"
    if re.search(r"方法|实现|步骤|流程|操作|method|procedure", headings, re.I):
        return "method"
    if re.search(r"原理|机制|推导|证明|why|reason|derivation", headings, re.I):
        return "reasoning"
    return "concept"


def _chinese_count(value: str) -> int | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.isdigit():
        parsed = int(token)
        return parsed if parsed > 0 else None
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if token == "十":
        return 10
    if "十" in token:
        left, right = token.split("十", 1)
        tens = digits.get(left, 1 if not left else 0)
        ones = digits.get(right, 0 if not right else -1)
        parsed = tens * 10 + ones
        return parsed if parsed > 0 else None
    return digits.get(token)


def _enumeration_counts(value: str) -> list[int]:
    return [
        count
        for match in _ENUMERATION_PROMISE_PATTERN.finditer(str(value or ""))
        if (
            (count := _chinese_count(match.group(1))) is not None
            and count >= 2
        )
    ]


def _title_enumeration_counts(value: str) -> list[int]:
    return [
        count
        for match in _TITLE_ENUMERATION_PATTERN.finditer(str(value or ""))
        if (
            (count := _chinese_count(match.group(1))) is not None
            and count >= 2
        )
    ]


def _v5_required_enumeration_fragments(group: list[Any]) -> set[str]:
    """Return source fragments that form an indivisible enumerated claim."""
    for index, fragment in enumerate(group):
        counts = _enumeration_counts(str(fragment.text or ""))
        if not counts:
            continue
        expected = counts[0]
        members: list[Any] = []
        for candidate in group[index + 1 :]:
            if candidate.kind == "heading":
                break
            if candidate.kind == "list_item":
                members.append(candidate)
                if len(members) == expected:
                    break
            elif members:
                break
        if len(members) == expected:
            return {
                fragment.fragment_id,
                *(item.fragment_id for item in members),
            }
    return set()


def _formula_group_has_source_explanation(group: list[Any]) -> bool:
    return (
        not any(fragment.kind == "formula" for fragment in group)
        or any(
            fragment.kind in {"paragraph", "list_item"}
            and _clean_text(fragment.text)
            for fragment in group
        )
    )


def _v5_fit_group(group: list[Any], *, limit: int = 230) -> list[Any]:
    if not _formula_group_has_source_explanation(group):
        return []
    required_ids = _v5_required_enumeration_fragments(group)
    if required_ids:
        required = [
            fragment for fragment in group
            if fragment.fragment_id in required_ids
        ]
        selected_ids = set(required_ids)
        visible = sum(len(str(fragment.text or "")) for fragment in required)

        # Preserve one source heading for traceability when it fits.  Additional
        # headings and prose are optional; they must never displace members
        # required to close a visible enumerated claim.
        first_heading = next(
            (fragment for fragment in group if fragment.kind == "heading"),
            None,
        )
        if first_heading is not None:
            heading_size = len(str(first_heading.text or ""))
            if visible + heading_size <= limit:
                selected_ids.add(first_heading.fragment_id)
                visible += heading_size

        for fragment in group:
            if fragment.fragment_id in selected_ids:
                continue
            size = len(str(fragment.text or ""))
            if len(selected_ids) >= 8 or (size and visible + size > limit):
                continue
            selected_ids.add(fragment.fragment_id)
            visible += size
        fitted = [
            fragment for fragment in group
            if fragment.fragment_id in selected_ids
        ]
        return fitted if _formula_group_has_source_explanation(fitted) else []

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
    return selected if _formula_group_has_source_explanation(selected) else []


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
        beat.layout_selection_reason in V5_SEMANTIC_CORE_REASONS
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
                    for kind in ("worked", "application", "method", "reasoning")
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
                    "application": "application",
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
                    else "mapping"
                    if scene == "application"
                    else "formal_explanation"
                )
                claim_fragment = next(
                    (item for item in group if item.kind == "heading"),
                    group[0],
                )
                selection = {
                    "worked_example": ("worked-example", "question", "example"),
                    "application": (
                        "parallel-examples",
                        "case-study",
                        "case",
                    ),
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
                        "application": "比较来源中的实际应用情境",
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
    planning_diagnostics: dict[str, Any] = Field(default_factory=dict)


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


def _split_course_cover_title(value: str) -> tuple[str, str]:
    cleaned = _clean_text(value).strip("《》〈〉")
    for separator in ("：", ":", "—", "–"):
        if separator not in cleaned:
            continue
        title, subtitle = (part.strip() for part in cleaned.split(separator, 1))
        if title and subtitle:
            return _bounded_title(title, limit=22), _bounded_title(subtitle, limit=24)
    return _bounded_title(cleaned, limit=22), ""


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
    cover_title, cover_subtitle = _split_course_cover_title(document.title)
    cover = DeckCoverV5(
        eyebrow="课程课件",
        title=cover_title,
        subtitle=cover_subtitle or course_goal,
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
        planning_diagnostics=deepcopy(story.planning_diagnostics),
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


def _is_numbered_section_title(value: str) -> bool:
    return bool(_NUMBERED_SECTION_TITLE_PATTERN.match(_clean_text(value)))


def _strip_numbered_section_prefix(value: str) -> str:
    cleaned = _clean_text(value)
    if not _is_numbered_section_title(cleaned):
        return cleaned
    return re.sub(
        r"^\s*\d+(?:\s*[.．]\s*\d+)+\s*",
        "",
        cleaned,
        count=1,
    ).strip()


def _strip_template_lead(value: str) -> str:
    return _TEMPLATE_LEAD_PATTERN.sub("", str(value or ""), count=1)


def _body_title_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    for segment in re.split(
        r"[\r\n]+|(?<=[。！？!?])\s*",
        str(value or ""),
    ):
        candidate = _title_candidate(_strip_template_lead(segment))
        if (
            candidate
            and not _is_numbered_section_title(candidate)
            and candidate not in candidates
        ):
            candidates.append(candidate)
    return candidates


def _best_body_title_claim(value: str) -> str:
    candidates = _body_title_candidates(value)
    enumerated = next(
        (
            candidate for candidate in candidates
            if _enumeration_counts(candidate)
        ),
        "",
    )
    if enumerated:
        return enumerated
    definition = next(
        (
            candidate for candidate in candidates
            if (
                "是否" not in candidate
                and not candidate.startswith(
                    ("为什么", "为何", "如何", "是否", "哪", "谁")
                )
                and re.match(r"^.{1,12}?(?:是指|是|为)", candidate)
            )
        ),
        "",
    )
    if definition:
        return definition
    relational = next(
        (
            candidate for candidate in candidates
            if any(
                marker in candidate
                for marker in (
                    "是指",
                    "意味着",
                    "决定",
                    "导致",
                    "构成",
                    "属于",
                    "取决于",
                    "因此",
                )
            )
        ),
        "",
    )
    return relational or (candidates[0] if candidates else "")


def _is_takeaway_title(value: str) -> bool:
    title = _clean_text(value)
    return bool(
        _enumeration_counts(title)
        or title.endswith(("？", "?"))
        or any(
            marker in title
            for marker in (
                "是指",
                "意味着",
                "决定",
                "导致",
                "构成",
                "属于",
                "取决于",
                "表明",
                "说明",
                "等于",
                "形成",
                "支持",
            )
        )
    )


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
    claim = _clean_text(value).strip("“”\"'。！？!?：:")
    if "，" in claim and claim.startswith(("根据", "通过", "基于", "当", "如果")):
        claim = claim.split("，", 1)[1].strip()
    if claim.startswith("在") and "，" in claim[:20]:
        claim = claim.split("，", 1)[1].strip()
    classification = re.fullmatch(
        r"(.{1,12}?)将(.{1,12}?)分为([一二三四五六七八九十\d]+)类",
        claim,
    )
    if classification:
        subject, topic, count = classification.groups()
        return f"{subject}{topic}的{count}种类型"
    definition = re.match(
        r"^(.{1,10}?)(?:是指|是)(只(?:依赖于|取决于).{2,18}?)(?:的)?"
        r"(?:物理量|变量|量)(?:[，。；]|$)",
        claim,
    )
    if definition:
        subject, predicate = definition.groups()
        predicate = predicate.replace("依赖于", "取决于")
        return _bounded_title(f"{subject}{predicate}")
    foundation = re.match(
        r"^(.{2,12}?)(?:是|作为).{0,20}?(?:最基础|基础)(?:的)?(?:一条|定律|规律)",
        claim,
    )
    if foundation:
        subject = foundation.group(1)
        return (
            f"{subject}奠定温度定义基础"
            if "温度" in claim
            else f"{subject}是基础定律"
        )
    return _bounded_title(claim)


def _is_incomplete_visible_claim(value: str) -> bool:
    clean = _clean_text(value).rstrip("：:，,。！？!?；;、•· ")
    if not clean:
        return True
    if not _has_balanced_text_brackets(clean):
        return True
    # A question may be grammatically complete without terminal punctuation.
    # Do not mistake the final attributive particle in “由什么驱动的” for a
    # clipped declarative title.
    if re.search(
        r"(?:为什么|是什么|什么类型|什么驱动|什么后果|有哪些|如何|"
        r"是否|能否|哪(?:一)?类|怎么)",
        clean,
    ):
        return False
    return clean.endswith((
        "的", "是指", "包括", "分为", "属于", "依赖于", "取决于",
        "表达式为", "如果", "那么",
    ))


def _is_usable_compiled_title(value: str) -> bool:
    clean = _clean_text(value)
    if (
        not clean
        or clean == "本页核心判断"
        or _is_incomplete_visible_claim(clean)
    ):
        return False
    if not re.search(r"[\u4e00-\u9fff]{2,}", clean):
        return False
    return not bool(
        re.fullmatch(r"(?:在|当|从).{0,18}(?:中|下|时|方面)", clean)
    )


_QUESTION_CLAIM_PATTERN = re.compile(
    r"(?:为什么|是什么|什么类型|哪(?:一)?类|如何|是否|能否|"
    r"应该归类为什么|吗|呢)$"
)
_QUESTION_LEAD_PATTERN = re.compile(
    r"^(?:在.{0,18}?[，,])?(?:有哪些|什么|如何|为什么|是否|能否|"
    r"哪(?:一)?类|你能|请问)"
)
_INSTRUCTIONAL_CLAIM_PATTERN = re.compile(
    r"^(?:考虑|思考|请|判断|说明|举出|解释|分析|比较|讨论)"
)


def _is_complete_declarative_claim(value: str) -> bool:
    clean = _clean_text(value).rstrip("。！？!?；;，,：:、 ")
    return bool(
        clean
        and not _is_incomplete_visible_claim(clean)
        and not _QUESTION_CLAIM_PATTERN.search(clean)
        and not _QUESTION_LEAD_PATTERN.search(clean)
        and not _INSTRUCTIONAL_CLAIM_PATTERN.search(clean)
        and not _TRANSITION_TEXT_PATTERN.search(clean)
    )


def _has_balanced_text_brackets(value: str) -> bool:
    pairs = {")": "(", "）": "（", "]": "[", "】": "【"}
    stack: list[str] = []
    openings = set(pairs.values())
    for character in str(value or ""):
        if character in openings:
            stack.append(character)
        elif character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return False
    return not stack


def _bounded_title(value: str, limit: int = 18) -> str:
    cleaned = _clean_text(value).strip("：:，,。！？!?；;、•·")
    if len(cleaned) <= limit:
        return cleaned
    question = re.fullmatch(
        r"(.{2,12}?)(?:，|,)?(?:那么)?(?:这个系统)?应该归类为什么类型",
        cleaned,
    )
    if question:
        subject = question.group(1).rstrip("，,")
        return _bounded_title(f"判断{subject}属于哪类系统", limit=limit)
    application = re.fullmatch(
        r"(.{2,14}?)(?:在工业和日常生活中|在日常生活中)有广泛应用",
        cleaned,
    )
    if application:
        return _bounded_title(f"{application.group(1)}的实际应用", limit=limit)
    for separator in ("：", ":", "；", ";"):
        if separator not in cleaned:
            continue
        lead = cleaned.split(separator, 1)[0].strip()
        if 6 <= len(lead) <= limit:
            return lead
    excerpt = cleaned[:limit]
    boundary = max(
        excerpt.rfind("，"),
        excerpt.rfind("；"),
        excerpt.rfind("："),
        excerpt.rfind("、"),
        excerpt.rfind(" "),
    )
    if boundary >= max(8, limit // 2):
        return excerpt[:boundary].strip("：:，,。！？!?；;、•·")
    subject = re.split(
        r"(?:是指|是|将|通过|能够|可以|需要|决定|描述|包含|包括|分为|用于|具有)",
        cleaned,
        maxsplit=1,
    )[0].strip("：:，,。！？!?；;、•·")
    if (
        4 <= len(subject) <= limit
        and not subject.startswith(("如果", "那么", "无论", "当", "在"))
    ):
        return subject
    # Fail closed to a complete topic label rather than leaking a mid-word
    # character slice into the published heading.
    topic = _clean_text(
        re.split(r"[，,；;：:。！？!?]", cleaned, maxsplit=1)[0]
    )
    return topic if len(topic) <= limit else "本页核心判断"


def _bounded_body_claim(
    value: str,
    limit: int = 64,
    *,
    require_complete: bool = False,
) -> str:
    """Keep a derived claim readable without silently overflowing its layout."""
    cleaned = _clean_text(value)
    if len(cleaned) <= limit:
        return cleaned
    excerpt = cleaned[:limit]
    terminal_boundary = max(
        excerpt.rfind("。"),
        excerpt.rfind("！"),
        excerpt.rfind("？"),
        excerpt.rfind("；"),
        excerpt.rfind("!"),
        excerpt.rfind("?"),
        excerpt.rfind(";"),
    )
    if terminal_boundary >= max(20, limit // 2):
        return excerpt[: terminal_boundary + 1].rstrip("：:、•· ")
    if require_complete:
        return ""
    boundary = max(
        excerpt.rfind("，"),
        excerpt.rfind(","),
        excerpt.rfind(" "),
    )
    if boundary >= max(20, limit // 2):
        excerpt = excerpt[: boundary + 1]
    return excerpt.rstrip("：:、•· ")


def _supporting_title_detail(original: str, compiled: str) -> str:
    source = _clean_text(original).strip("。！？!?")
    title = _clean_text(compiled)
    if not source or not title or source == title:
        return ""
    if source.startswith(title):
        detail = source[len(title):].lstrip("：:，,；;、—- ")
        if detail:
            return detail
    return source


def compile_page_title_v5(
    *,
    explicit_title: str,
    primary_claim: str = "",
    body_text: str = "",
    fallback_context: str = "",
    prefer_body_claim: bool = False,
) -> str:
    """Compile one audience-facing title without promoting takeaway at render time."""
    explicit = _title_candidate(explicit_title)
    claim = _title_candidate(primary_claim)
    explicit_was_numbered = _is_numbered_section_title(explicit)
    claim_was_numbered = _is_numbered_section_title(claim)
    if explicit_was_numbered:
        explicit = _title_candidate(_strip_numbered_section_prefix(explicit))
    if _is_incomplete_visible_claim(explicit):
        explicit = ""
    if claim_was_numbered:
        claim = _title_candidate(_strip_numbered_section_prefix(claim))
    if _is_incomplete_visible_claim(claim):
        claim = ""
    body_claim = _best_body_title_claim(body_text)
    fallback = _title_candidate(fallback_context)
    if (
        (prefer_body_claim or explicit_was_numbered or claim_was_numbered)
        and body_claim
        and explicit
        and explicit == claim
        and not _is_takeaway_title(explicit)
    ):
        body_title = _structured_claim_title(body_claim)
        if _is_usable_compiled_title(body_title):
            return body_title
    for candidate in (explicit, claim, body_claim, fallback):
        if not candidate:
            continue
        compiled = _structured_claim_title(candidate)
        if _is_usable_compiled_title(compiled):
            return compiled
    return "本页核心判断"


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


_VISIBLE_BULLET_LINE = re.compile(
    r"^\s*(?:[•●▪◦*\-]|\d+[.)、])\s*(\S.*)$"
)


def _structure_visible_enumerations(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updated = deepcopy(blocks)
    for block in updated:
        if any(_clean_text(item) for item in block.get("items") or []):
            continue
        content = str(block.get("content") or "")
        lines = content.splitlines()
        items = [
            _clean_text(match.group(1))
            for line in lines
            if (match := _VISIBLE_BULLET_LINE.match(line)) is not None
        ]
        if len(items) < 2:
            continue
        block["items"] = items
        block["content"] = "\n".join(
            line for line in lines
            if _VISIBLE_BULLET_LINE.match(line) is None
        ).strip()
        if str(block.get("type") or "") == "statement":
            block["type"] = "bullets"
    return updated


_DEFINITION_RELATION_PATTERN = re.compile(
    r"^.{1,16}?(?:是指|定义为|指的是|称为).{3,}"
)


def _normalize_concept_definition_slide_v5(
    source: dict[str, Any],
) -> dict[str, Any]:
    slide = deepcopy(source)
    if str(slide.get("scene_kind") or "") != "concept":
        return slide
    normalized_blocks: list[dict[str, Any]] = []
    definition: tuple[str, dict[str, Any]] | None = None
    definition_expected = False
    for block_index, source_block in enumerate(slide.get("blocks") or []):
        block = deepcopy(source_block)
        title = _clean_text(block.get("title"))
        if _normalize_title_match(title) in _GENERIC_TITLES:
            block["title"] = ""
        content = _strip_template_lead(str(block.get("content") or "")).strip()
        items = [
            _strip_template_lead(str(item or "")).strip()
            for item in block.get("items") or []
            if _strip_template_lead(str(item or "")).strip()
        ]
        values = [value for value in [content, *items] if value]
        remaining: list[str] = []
        for value in values:
            if _DEFINITION_RELATION_PATTERN.search(_clean_text(value)):
                definition_expected = True
                if definition is None:
                    definition = (value, block)
                    continue
            remaining.append(value)
        if not remaining:
            continue
        block["content"] = remaining[0] if not items else ""
        block["items"] = remaining if items else []
        block["metadata"] = dict(block.get("metadata") or {})
        block["block_id"] = str(
            block.get("block_id") or f"concept-context-{block_index + 1}"
        )
        normalized_blocks.append(block)
    if definition is not None:
        value, original = definition
        definition_block = {
            "block_id": f"{slide.get('unit_id') or 'concept'}:definition",
            "type": "statement",
            "title": "定义",
            "content": value,
            "items": [],
            "metadata": {
                **(original.get("metadata") or {}),
                "semantic_role": "definition",
            },
        }
        normalized_blocks.insert(0, definition_block)
    slide["blocks"] = normalized_blocks
    slide["quality"] = {
        **(slide.get("quality") or {}),
        "concept_definition_expected": definition_expected,
        "concept_definition_normalized": definition is not None,
        "preferred_title_claim": definition[0] if definition else "",
    }
    return slide


def _semantic_bindings(slide: dict[str, Any]) -> list[SlotBindingV5]:
    bindings: list[SlotBindingV5] = []
    for block_index, block in enumerate(slide.get("blocks") or []):
        block_id = str(block.get("block_id") or f"block-{block_index + 1}")
        block_type = str(block.get("type") or "rich_text")
        declared_role = str(
            (block.get("metadata") or {}).get("semantic_role") or ""
        )
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
                semantic_role=declared_role or "text",
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
    scene_kind = str(slide.get("scene_kind") or "")
    beat_role = str(slide.get("beat_role") or "")
    bindings = _semantic_bindings(slide)
    non_visual = [item for item in bindings if item.semantic_role != "visual"]
    has_visual = any(item.semantic_role == "visual" for item in bindings)
    visual_decision: Literal["accepted", "none"] = "accepted" if has_visual else "none"
    classification = [
        item for item in non_visual
        if item.semantic_role == "classification_item"
    ]
    fallback_reason = ""

    explicit_worked_labels = [
        _clean_text(item)
        for item in quality.get("worked_step_labels") or []
        if _clean_text(item)
    ]
    has_worked_steps = (
        any(item.semantic_role == "process_step" for item in non_visual)
        or len(explicit_worked_labels) >= 2
    )

    if requested_layout in {"cover", "cover-minimal", "cover-editorial"}:
        resolved_layout = "cover-editorial"
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
    elif (
        requested_layout == "parallel-examples"
        or scene_kind == "application"
    ) and 2 <= len(non_visual) <= 4:
        resolved_layout = "parallel-examples"
        resolved_composition = "parallel"
        major_regions = len(non_visual)
        if requested_layout != resolved_layout:
            fallback_reason = "application_items_are_parallel"
    elif requested_layout == "question-prompt" or (
        requested_layout == "worked-example" and beat_role == "prompt"
    ):
        resolved_layout = "question-prompt"
        resolved_composition = "exercise"
        major_regions = 1
        if requested_layout != resolved_layout:
            fallback_reason = "worked_example_prompt_is_not_a_reasoning_chain"
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
        elif not has_worked_steps:
            resolved_layout = "editorial-body"
            resolved_composition = "statement"
            major_regions = 1
            fallback_reason = "worked_example_semantics_missing"
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
    elif requested_layout == "hero-claim":
        resolved_layout = "hero-claim"
        resolved_composition = "statement"
        major_regions = 1
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

    semantic_region_count = len(non_visual) + (1 if has_visual else 0)
    if resolved_layout == "hero-claim" and _clean_text(
        slide.get("key_message") or slide.get("takeaway") or slide.get("title")
    ):
        semantic_region_count = max(1, semantic_region_count)
    occupied = min(major_regions, semantic_region_count)
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
    updated["blocks"] = _structure_visible_enumerations(
        list(updated.get("blocks") or [])
    )
    contract = resolve_page_contract_v5(updated)
    quality = deepcopy(updated.get("quality") or {})
    removed_superseded_issue = False
    for key in ("issues", "blockers"):
        original = [
            item
            for item in quality.get(key) or []
            if isinstance(item, dict)
        ]
        filtered = [
            item
            for item in original
            if str(item.get("code") or "")
            not in _V5_REPLACED_V4_QUALITY_CODES
        ]
        removed_superseded_issue = (
            removed_superseded_issue
            or len(filtered) != len(original)
        )
        quality[key] = filtered
    if removed_superseded_issue:
        remaining = [
            *(quality.get("issues") or []),
            *(quality.get("blockers") or []),
        ]
        quality["passed"] = not any(
            str(item.get("severity") or "") == "critical"
            for item in remaining
        )
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
        original_title = str(updated.get("title") or "")
        body_text = _body_text_from_blocks(
            list(updated.get("blocks") or [])
        )
        updated["title"] = compile_page_title_v5(
            explicit_title=str(updated.get("title") or ""),
            primary_claim=str(
                quality.get("preferred_title_claim")
                or (updated.get("primary_claim_source") or {}).get("text")
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
            prefer_body_claim=(
                str(
                    (updated.get("primary_claim_source") or {}).get("kind")
                    or ""
                )
                == "source_heading"
            ),
        )
        supporting_detail = _supporting_title_detail(
            original_title,
            updated["title"],
        )
        if supporting_detail and not _clean_text(updated.get("key_message")):
            updated["key_message"] = supporting_detail
            quality["title_detail_promoted"] = True
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
        slide_title = _clean_text(slide.get("title"))
        candidates = [
            slide_title if _is_takeaway_title(slide_title) else "",
            _clean_text(slide.get("takeaway")),
            _clean_text(slide.get("key_message")),
            _clean_text((slide.get("primary_claim_source") or {}).get("text")),
        ]
        for block in slide.get("blocks") or []:
            candidates.extend([
                _first_body_sentence(str(block.get("content") or "")),
                *[
                    _first_body_sentence(str(item))
                    for item in block.get("items") or []
                ],
            ])
        for candidate in candidates:
            candidate = _strip_template_lead(candidate).strip()
            if (
                not candidate
                or _is_numbered_section_title(candidate)
                or _normalize_title_match(candidate) in _GENERIC_TITLES
                or "？" in candidate
                or "?" in candidate
            ):
                continue
            compact_candidate = _bounded_body_claim(
                candidate,
                limit=64,
                require_complete=True,
            )
            normalized_candidate = _normalize_title_match(compact_candidate)
            if (
                compact_candidate
                and _is_complete_declarative_claim(compact_candidate)
                and normalized_candidate not in {
                    _normalize_title_match(point) for point in points
                }
            ):
                points.append(compact_candidate)
                break
        if len(points) == 4:
            break
    if not points:
        fallback = _bounded_body_claim(
            chapter.learning_objective or chapter.title,
            limit=64,
            require_complete=True,
        )
        points = [fallback or _bounded_title(chapter.title, limit=18)]
    return {
        "unit_id": f"slide:v5:chapter-recap:{chapter.chapter_id}",
        "position": 0,
        "layout": "recap",
        "slide_purpose": "chapter_recap",
        "eyebrow": "章节回顾",
        "title": "本章必须带走的关键判断",
        "subtitle": "",
        "key_message": "不看前文，你能否用自己的话解释这些判断？",
        "teaching_job": "用回忆问题检验本章关键判断是否真正形成",
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
        "beat_role": "closure",
        "primary_claim_source": {},
        "prerequisite_refs": [],
        "mastery_criterion_refs": [],
        "layout_selection_reason": "required_v5_chapter_recap",
        "quality": {
            "requested_layout": "chapter-recap",
            "navigation_only": False,
            "retrieval_recap": True,
            "derived_density_compaction": True,
        },
    }


def _recap_is_retrieval_ready(slide: dict[str, Any] | None) -> bool:
    if not slide:
        return False
    quality = slide.get("quality") or {}
    if quality.get("navigation_only"):
        return False
    items = [
        _clean_text(item)
        for block in slide.get("blocks") or []
        for item in block.get("items") or []
        if _clean_text(item)
    ]
    prompt = _clean_text(slide.get("key_message"))
    return (
        bool(quality.get("retrieval_recap"))
        and len(items) >= 2
        and ("？" in prompt or "?" in prompt)
        and _page_density_metrics(slide)["density_band"] != "overflow"
    )


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


_TRANSITION_TEXT_PATTERN = re.compile(
    r"(?:本节|本章|下一节|下一章|后续|为.+打下基础|将(?:深入)?(?:探讨|学习|介绍))"
)


def _block_visible_text(block: dict[str, Any]) -> str:
    return _clean_text(" ".join([
        str(block.get("title") or ""),
        str(block.get("content") or ""),
        *[str(item) for item in block.get("items") or []],
    ]))


def _text_sentences(value: str) -> list[str]:
    return [
        _clean_text(match.group(0))
        for match in re.finditer(r"[^。！？!?；;]+[。！？!?；;]?", str(value or ""))
        if _clean_text(match.group(0))
    ]


def _split_block_narrative_jobs(
    block: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    content = str(block.get("content") or "")
    sentences = _text_sentences(content)
    transition_sentences = [
        sentence for sentence in sentences
        if _TRANSITION_TEXT_PATTERN.search(sentence)
    ]
    question_sentences = [
        sentence for sentence in sentences
        if sentence not in transition_sentences
    ]
    has_question = (
        str(block.get("type") or "") == "exercise"
        or any("？" in sentence or "?" in sentence for sentence in question_sentences)
    )
    if not transition_sentences or not question_sentences or not has_question:
        return [(deepcopy(block), _block_narrative_intent(block))]

    question = deepcopy(block)
    question["content"] = "".join(question_sentences)
    transition = deepcopy(block)
    transition["block_id"] = f"{block.get('block_id') or 'block'}:transition"
    transition["type"] = "statement"
    transition["title"] = ""
    transition["content"] = "".join(transition_sentences)
    transition["items"] = []
    return [(question, "question"), (transition, "transition")]


def _block_narrative_intent(block: dict[str, Any]) -> str:
    text = _block_visible_text(block)
    if _TRANSITION_TEXT_PATTERN.search(text):
        return "transition"
    if str(block.get("type") or "") == "exercise" or "？" in text or "?" in text:
        return "question"
    return "content"


def _section_label_from_slide(slide: dict[str, Any]) -> str:
    quality = slide.get("quality") or {}
    candidates = [
        quality.get("section_label"),
        slide.get("key_message"),
        slide.get("title"),
        *(
            block.get("title")
            for block in slide.get("blocks") or []
        ),
    ]
    return next(
        (
            _clean_text(candidate)
            for candidate in candidates
            if _is_numbered_section_title(_clean_text(candidate))
        ),
        "",
    )


def _next_source_topic(
    slides: list[dict[str, Any]],
    source_index: int,
) -> str:
    if source_index + 1 >= len(slides):
        return ""
    next_slide = slides[source_index + 1]
    label = _section_label_from_slide(next_slide)
    if label:
        return re.sub(
            r"^\s*\d+(?:\s*[.．]\s*\d+)+\s+",
            "",
            label,
        ).strip()
    return _bounded_title(
        _clean_text(next_slide.get("title")),
        limit=18,
    )


def _is_standalone_micro_transition(slide: dict[str, Any]) -> bool:
    if str(slide.get("scene_kind") or "") in {
        "chapter_entry",
        "course_synthesis",
    }:
        return False
    unit_id = _clean_text(slide.get("unit_id"))
    transition_identity = bool(
        str(slide.get("scene_kind") or "") == "transition"
        or str(slide.get("beat_role") or "") == "transition"
        or unit_id.endswith(":transition")
    )
    visible_values = [
        _clean_text(slide.get("title")),
        _clean_text(slide.get("key_message")),
        *[
            _block_visible_text(block)
            for block in slide.get("blocks") or []
        ],
    ]
    visible_values = [value for value in visible_values if value]
    return bool(
        transition_identity
        and visible_values
        and all(_TRANSITION_TEXT_PATTERN.search(value) for value in visible_values)
    )


def split_mixed_intent_slides_v5(
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the question and discard a redundant source-navigation page.

    A source sentence such as ``下一节将……`` is not a presentation-worthy
    page on its own.  The actual following slide is the navigation source of
    truth, so the stale sentence is removed and retained only as audit
    metadata on the checkpoint page.
    """
    result: list[dict[str, Any]] = []
    source_slides = list(slides)
    for source_index, source in enumerate(source_slides):
        slide = deepcopy(source)
        slide["quality"] = dict(slide.get("quality") or {})
        expanded = [
            item
            for block in slide.get("blocks") or []
            for item in _split_block_narrative_jobs(block)
        ]
        blocks = [block for block, _intent in expanded]
        intents = [intent for _block, intent in expanded]
        if "question" not in intents or "transition" not in intents:
            result.append(slide)
            continue
        question_blocks = [
            block for block, intent in zip(blocks, intents)
            if intent != "transition"
        ]
        # narrative_role belongs to the upstream story-planning model, not the
        # strict persisted SlideSpec contract. Keep the supported semantic
        # fields below as the single source of truth for the split pages.
        slide.pop("narrative_role", None)
        slide["blocks"] = question_blocks
        if _TRANSITION_TEXT_PATTERN.search(_clean_text(slide.get("key_message"))):
            slide["key_message"] = ""
        slide["quality"] = {
            **(slide.get("quality") or {}),
            "requested_layout": "question-prompt",
            "split_mixed_narrative_jobs": True,
            "removed_redundant_transition": True,
            "next_topic": _next_source_topic(source_slides, source_index),
        }
        result.append(slide)
    filtered: list[dict[str, Any]] = []
    for source_index, slide in enumerate(result):
        if not _is_standalone_micro_transition(slide):
            filtered.append(slide)
            continue
        next_topic = _next_source_topic(result, source_index)
        if filtered:
            previous = filtered[-1]
            previous["quality"] = {
                **(previous.get("quality") or {}),
                "removed_redundant_transition": True,
                "removed_transition_unit_ids": [
                    *(
                        (previous.get("quality") or {}).get(
                            "removed_transition_unit_ids"
                        ) or []
                    ),
                    _clean_text(slide.get("unit_id")),
                ],
                "next_topic": next_topic,
            }
    result = filtered
    for position, slide in enumerate(result):
        slide["position"] = position
    return result


def _assign_heading_modes_v5(
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Separate metadata titles from visible headings across one episode."""
    result: list[dict[str, Any]] = []
    seen_explanation_episodes: set[str] = set()
    labels_by_episode: dict[str, str] = {}
    labels_by_section: dict[str, str] = {}
    for source in slides:
        slide = deepcopy(source)
        quality = dict(slide.get("quality") or {})
        episode_id = _clean_text(slide.get("episode_id"))
        section_id = _clean_text(slide.get("section_id"))
        label = _section_label_from_slide(slide)
        if label:
            if episode_id:
                labels_by_episode[episode_id] = label
            if section_id:
                labels_by_section[section_id] = label
        else:
            label = (
                labels_by_episode.get(episode_id, "")
                or labels_by_section.get(section_id, "")
            )

        is_explanation = (
            str(slide.get("layout") or "") == "concept"
            and str(slide.get("scene_kind") or "")
            not in {"practice_feedback", "transition"}
        )
        is_continuation = bool(
            is_explanation
            and episode_id
            and episode_id in seen_explanation_episodes
        )
        quality["heading_mode"] = "hidden" if is_continuation else "full"
        if label:
            quality["section_label"] = label
        slide["quality"] = quality
        result.append(slide)
        if is_explanation and episode_id:
            seen_explanation_episodes.add(episode_id)
    return result


def _slide_knowledge_refs(slide: dict[str, Any]) -> set[str]:
    return {
        _clean_text(ref)
        for ref in slide.get("knowledge_refs") or []
        if _clean_text(ref)
    }


def _grounded_feedback_evidence(
    practice: dict[str, Any],
    preceding: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Collect concise, source-visible evidence without inventing an answer."""
    target_refs = _slide_knowledge_refs(practice)
    if not target_refs:
        return [], []
    chapter_id = _clean_text(practice.get("chapter_id"))
    evidence: list[str] = []
    source_ids: list[str] = []
    for candidate in reversed(preceding):
        if chapter_id and _clean_text(candidate.get("chapter_id")) != chapter_id:
            continue
        if not target_refs.intersection(_slide_knowledge_refs(candidate)):
            continue
        if str(candidate.get("scene_kind") or "") in {
            "practice_feedback",
            "transition",
        }:
            continue
        candidate_values = [
            value
            for block in candidate.get("blocks") or []
            if str(block.get("type") or "") not in {
                "exercise",
                "question",
                "prompt",
            }
            for value in [
                *(block.get("items") or []),
                block.get("content"),
            ]
            if _clean_text(value)
        ]
        added_from_candidate = False
        for value in candidate_values:
            for sentence in _text_sentences(str(value)):
                clean = _bounded_body_claim(sentence, limit=64)
                if (
                    len(clean) < 6
                    or "？" in clean
                    or "?" in clean
                    or _TRANSITION_TEXT_PATTERN.search(clean)
                    or clean in evidence
                ):
                    continue
                evidence.append(clean)
                added_from_candidate = True
                if len(evidence) >= 3:
                    break
            if len(evidence) >= 3:
                break
        if added_from_candidate:
            source_id = _clean_text(candidate.get("unit_id"))
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        if len(evidence) >= 3:
            break
    return evidence, list(reversed(source_ids))


def _practice_has_feedback(slide: dict[str, Any]) -> bool:
    if str(slide.get("beat_role") or "") in {
        "answer",
        "feedback",
        "solution",
        "validation",
    }:
        return True
    return any(
        str(block.get("type") or "") in {
            "answer",
            "feedback",
            "solution",
            "validation",
        }
        or str((block.get("metadata") or {}).get("semantic_role") or "")
        in {"answer", "feedback", "solution", "validation"}
        for block in slide.get("blocks") or []
    )


def _practice_block_values(block: dict[str, Any]) -> list[str]:
    return [
        _clean_text(value)
        for value in (block.get("items") or [block.get("content")])
        if _clean_text(value)
    ]


def _practice_question_ids(slide: dict[str, Any], count: int) -> list[str]:
    unit_id = _clean_text(slide.get("unit_id")) or "practice"
    return [
        stable_hash(
            {"unit_id": unit_id, "question_index": index},
            prefix="question_",
        )
        for index in range(count)
    ]


def _feedback_blocks(slide: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for block in slide.get("blocks") or []
        if (
            str(block.get("type") or "")
            in {"answer", "feedback", "solution", "validation"}
            or str((block.get("metadata") or {}).get("semantic_role") or "")
            in {"answer", "feedback", "solution", "validation"}
        )
    ]


def _enrich_practice_feedback_slides_v5(
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Publish identity-bound answers or clearly labelled shared evidence."""
    result: list[dict[str, Any]] = []
    skipped_units: set[str] = set()
    for source_index, source in enumerate(slides):
        if _clean_text(source.get("unit_id")) in skipped_units:
            continue
        slide = deepcopy(source)
        is_prompt = (
            str(slide.get("scene_kind") or "") == "practice_feedback"
            and str(slide.get("beat_role") or "") == "prompt"
        )
        if not is_prompt:
            result.append(slide)
            continue

        blocks = [deepcopy(block) for block in slide.get("blocks") or []]
        prompt_index = next((
            index
            for index, block in enumerate(blocks)
            if (
                str(block.get("type") or "")
                in {"exercise", "question", "prompt"}
                or str((block.get("metadata") or {}).get("semantic_role") or "")
                == "prompt"
            )
        ), 0 if blocks else -1)
        if prompt_index < 0:
            result.append(slide)
            continue
        prompt = deepcopy(blocks[prompt_index])
        prompt_values = _practice_block_values(prompt)
        question_ids = _practice_question_ids(slide, len(prompt_values))
        prompt["metadata"] = {
            **(prompt.get("metadata") or {}),
            "semantic_role": "prompt",
            "question_ids": question_ids,
        }
        blocks[prompt_index] = prompt

        direct_blocks = _feedback_blocks({"blocks": blocks})
        if not direct_blocks and source_index + 1 < len(slides):
            candidate = slides[source_index + 1]
            same_episode = bool(
                _clean_text(candidate.get("episode_id"))
                and _clean_text(candidate.get("episode_id"))
                == _clean_text(slide.get("episode_id"))
            )
            is_answer_beat = (
                str(candidate.get("scene_kind") or "") == "practice_feedback"
                and str(candidate.get("beat_role") or "")
                in {"answer", "feedback", "solution", "validation"}
            )
            if same_episode and is_answer_beat:
                direct_blocks = [
                    deepcopy(block)
                    for block in candidate.get("blocks") or []
                    if _practice_block_values(block)
                ]
                skipped_units.add(_clean_text(candidate.get("unit_id")))

        direct_answers = [
            value
            for block in direct_blocks
            for value in _practice_block_values(block)
        ]
        generated_answers = [
            item
            for item in (slide.get("quality") or {}).get(
                "generated_practice_answers"
            ) or []
            if isinstance(item, dict)
        ]
        if len(generated_answers) == len(prompt_values) and all(
            int(item.get("question_index") or 0) == index
            and _clean_text(item.get("answer_text"))
            for index, item in enumerate(generated_answers)
        ):
            direct_answers = [
                _clean_text(item.get("answer_text"))
                for item in generated_answers
            ]
            source_fragment_ids = list(dict.fromkeys(
                fragment_id
                for item in generated_answers
                for fragment_id in item.get("supporting_fragment_ids") or []
                if _clean_text(fragment_id)
            ))
            answer_mode = "llm_generated"
        else:
            source_fragment_ids = list(dict.fromkeys(
                fragment_id
                for block in direct_blocks
                for fragment_id in (
                    (block.get("metadata") or {}).get("source_fragment_ids")
                    or []
                )
                if _clean_text(fragment_id)
            ))
            answer_mode = "source_extracted"

        non_feedback_blocks = [
            block for block in blocks if block not in direct_blocks
        ]
        if len(direct_answers) == len(prompt_values) and prompt_values:
            non_feedback_blocks.append({
                "block_id": f"{slide.get('unit_id') or 'practice'}:answers",
                "type": "callout",
                "title": "参考答案与判断依据",
                "content": "",
                "items": direct_answers,
                "metadata": {
                    "semantic_role": "answer",
                    "direct_answer": True,
                    "generation_mode": answer_mode,
                    "answer_for_question_ids": question_ids,
                    "source_fragment_ids": source_fragment_ids,
                },
            })
            slide["blocks"] = non_feedback_blocks
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "requested_layout": "practice-feedback",
                "feedback_mode": "paired",
                "feedback_pair_count": len(prompt_values),
                "feedback_evidence_count": 0,
                "answer_generation_mode": answer_mode,
            }
            result.append(slide)
            continue

        evidence, source_ids = _grounded_feedback_evidence(slide, result)
        if evidence:
            paired_evidence = evidence[:len(prompt_values)] if prompt_values else evidence[:1]
            non_feedback_blocks.append({
                "block_id": f"{slide.get('unit_id') or 'practice'}:feedback",
                "type": "callout",
                "title": "判断依据",
                "content": "",
                "items": paired_evidence,
                "metadata": {
                    "semantic_role": "feedback",
                    "grounded": True,
                    "direct_answer": False,
                    "source_slide_ids": source_ids,
                },
            })
            slide["blocks"] = non_feedback_blocks
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "requested_layout": "practice-feedback",
                "grounded_feedback": True,
                "grounded_feedback_source_ids": source_ids,
                "feedback_mode": "shared_evidence",
                "feedback_pair_count": 0,
                "feedback_evidence_count": len(paired_evidence),
            }
        result.append(slide)
    return result


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
            "subtitle": outline.cover.subtitle,
            "key_message": "",
            "blocks": [],
            "quality": {
                **(cover.get("quality") or {}),
                "requested_layout": "cover-editorial",
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
        recap = (
            existing_recap
            if _recap_is_retrieval_ready(existing_recap)
            else _chapter_recap_slide(chapter, body_slides)
        )
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
        narrative_intents = {
            _block_narrative_intent(block)
            for block in slide.get("blocks") or []
        }
        if _is_standalone_micro_transition(slide):
            issues.append({
                "severity": "critical",
                "code": "standalone_transition_page",
                "page_id": slide.get("unit_id"),
            })
        if {"question", "transition"} <= narrative_intents:
            issues.append({
                "severity": "critical",
                "code": "mixed_narrative_jobs",
                "page_id": slide.get("unit_id"),
            })
        if resolved == "worked-example":
            binding_roles = {
                str(binding.get("semantic_role") or "")
                for binding in quality.get("slot_bindings") or []
                if isinstance(binding, dict)
            }
            explicit_labels = [
                _clean_text(item)
                for item in quality.get("worked_step_labels") or []
                if _clean_text(item)
            ]
            if "process_step" not in binding_roles and len(explicit_labels) < 2:
                issues.append({
                    "severity": "critical",
                    "code": "worked_example_semantics_missing",
                    "page_id": slide.get("unit_id"),
                })
        if (
            str(slide.get("scene_kind") or "") == "practice_feedback"
            and str(slide.get("beat_role") or "") == "prompt"
            and not _practice_has_feedback(slide)
        ):
            issues.append({
                "severity": "critical",
                "code": "practice_feedback_missing_answer",
                "page_id": slide.get("unit_id"),
            })
        if (
            str(slide.get("scene_kind") or "") == "practice_feedback"
            and str(slide.get("beat_role") or "") == "prompt"
            and str(quality.get("feedback_mode") or "") == "paired"
        ):
            prompt_block = next((
                block
                for block in slide.get("blocks") or []
                if str((block.get("metadata") or {}).get("semantic_role") or "")
                == "prompt"
            ), None)
            question_values = _practice_block_values(prompt_block or {})
            question_ids = list(
                ((prompt_block or {}).get("metadata") or {}).get("question_ids")
                or []
            )
            answer_blocks = [
                block
                for block in slide.get("blocks") or []
                if bool((block.get("metadata") or {}).get("direct_answer"))
            ]
            answer_values = [
                value
                for block in answer_blocks
                for value in _practice_block_values(block)
            ]
            answer_for_ids = [
                question_id
                for block in answer_blocks
                for question_id in (
                    (block.get("metadata") or {}).get(
                        "answer_for_question_ids"
                    ) or []
                )
            ]
            if (
                not question_ids
                or len(answer_for_ids) != len(question_ids)
                or set(answer_for_ids) != set(question_ids)
            ):
                issues.append({
                    "severity": "critical",
                    "code": "practice_direct_answer_unbound",
                    "page_id": slide.get("unit_id"),
                })
            if len(answer_values) != len(question_values):
                issues.append({
                    "severity": "critical",
                    "code": "practice_direct_answer_count_mismatch",
                    "page_id": slide.get("unit_id"),
                    "question_count": len(question_values),
                    "answer_count": len(answer_values),
                })
        if resolved == "chapter-recap":
            if quality.get("navigation_only"):
                issues.append({
                    "severity": "critical",
                    "code": "recap_is_navigation_only",
                    "page_id": slide.get("unit_id"),
                })
            recap_items = [
                _clean_text(item)
                for block in slide.get("blocks") or []
                for item in block.get("items") or []
                if _clean_text(item)
            ]
            if any(
                not _is_complete_declarative_claim(item)
                for item in recap_items
            ):
                issues.append({
                    "severity": "critical",
                    "code": "recap_item_incomplete",
                    "page_id": slide.get("unit_id"),
                })
            recall_prompt = _clean_text(slide.get("key_message"))
            if "？" not in recall_prompt and "?" not in recall_prompt:
                issues.append({
                    "severity": "critical",
                    "code": "recap_retrieval_prompt_missing",
                    "page_id": slide.get("unit_id"),
                })
        if quality.get("concept_definition_expected"):
            has_definition = any(
                str((block.get("metadata") or {}).get("semantic_role") or "")
                == "definition"
                and bool(_clean_text(block.get("content")))
                for block in slide.get("blocks") or []
            )
            if not has_definition:
                issues.append({
                    "severity": "critical",
                    "code": "concept_definition_missing",
                    "page_id": slide.get("unit_id"),
                })
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
        if _is_incomplete_visible_claim(title):
            issues.append({
                "severity": "critical",
                "code": "incomplete_title_claim",
                "page_id": slide.get("unit_id"),
            })
        if _RAW_TITLE_PATTERN.search(title):
            issues.append({
                "severity": "critical",
                "code": "raw_source_sentence_as_title",
                "page_id": slide.get("unit_id"),
            })
        if (
            _is_numbered_section_title(title)
            and resolved not in {
                "cover-minimal",
                "agenda-linear",
                "chapter-entry",
                "chapter-recap",
                "course-synthesis",
            }
        ):
            issues.append({
                "severity": "critical",
                "code": "source_section_heading_as_title",
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
        visible_items = [
            _clean_text(item)
            for block in slide.get("blocks") or []
            for item in block.get("items") or []
            if _clean_text(item)
        ]
        visible_items.extend(
            _clean_text(match.group(1))
            for block in slide.get("blocks") or []
            for line in str(block.get("content") or "").splitlines()
            if (match := _VISIBLE_BULLET_LINE.match(line)) is not None
        )
        expected_counts = [
            *_title_enumeration_counts(title),
            *_enumeration_counts(body_text),
        ]
        expected_count = max(expected_counts, default=0)
        if expected_count and len(visible_items) < expected_count:
            issues.append({
                "severity": "critical",
                "code": "enumeration_cardinality_mismatch",
                "page_id": slide.get("unit_id"),
                "expected_count": expected_count,
                "visible_item_count": len(visible_items),
            })
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
            "concept_definition_missing",
            "incomplete_title_claim",
            "mixed_narrative_jobs",
            "official_source_revision_mismatch",
            "practice_direct_answer_count_mismatch",
            "practice_direct_answer_unbound",
            "practice_feedback_missing_answer",
            "recap_is_navigation_only",
            "recap_item_incomplete",
            "recap_retrieval_prompt_missing",
            "raw_source_sentence_as_title",
            "standalone_transition_page",
            "title_body_duplication",
            "worked_example_semantics_missing",
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
    planning_diagnostics: dict[str, Any] | None = None,
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
            "severity": "major",
            "code": "ai_story_planner_fallback",
            "target": "deck",
            "message": (
                "AI story planning was unavailable; the deck used the "
                "source-grounded deterministic V5 story instead."
            ),
            "suggestion": (
                "Review the recorded chapter diagnostics and retry AI planning "
                "without blocking a render-safe deterministic deck."
            ),
        })
    elif fallback_reason == "partial_ai_story_plan":
        planning_issues.append({
            "severity": "major",
            "code": "ai_story_planner_partial_fallback",
            "target": "deck",
            "message": (
                "Some chapters used the deterministic V5 story because their "
                "AI planning request failed."
            ),
            "suggestion": "Retry only the failed chapters when the AI planner recovers.",
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

    final_slide_issues: list[dict[str, Any]] = []
    for slide in slides:
        quality = slide.get("quality") or {}
        slide_issues = [
            deepcopy(issue)
            for issue in [
                *(quality.get("blockers") or []),
                *(quality.get("issues") or []),
            ]
            if isinstance(issue, dict)
        ]
        for issue in slide_issues:
            issue.setdefault("target", str(slide.get("unit_id") or "slide"))
            issue.setdefault("slide_id", str(slide.get("unit_id") or ""))
        if quality.get("passed") is False and not any(
            str(issue.get("severity") or "") == "critical"
            for issue in slide_issues
        ):
            slide_issues.append({
                "severity": "critical",
                "code": "final_slide_quality_failed",
                "target": str(slide.get("unit_id") or "slide"),
                "slide_id": str(slide.get("unit_id") or ""),
                "message": "A final slide failed its page-level quality contract.",
                "suggestion": "Repair or reflow the final slide before publication.",
            })
        final_slide_issues.extend(slide_issues)

    combined = [
        *retained,
        *v5_contract_issues(slides),
        *final_slide_issues,
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
            "diagnostics": deepcopy(planning_diagnostics or {}),
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
    compaction_applied = False
    if len(compact_allocation.pages) < provided_page_count:
        story = compact_story
        allocation_plan = compact_allocation
        compaction_applied = True
    if compaction_applied and visual_plan is not None:
        # Page IDs and their source bindings are regenerated by compaction.
        # Reusing the pre-compaction visual plan can either fail validation or,
        # worse, attach a visual decision to a different semantic page.
        visual_plan = deterministic_visual_plan(
            document,
            compact_allocation,
            source_fragments,
        )
        visual_plan.deck_brief["fallback_reason"] = (
            "v5_compaction_visual_plan_rebuilt"
        )
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
    slides = split_mixed_intent_slides_v5(slides)
    for slide in slides:
        scene_kind = str(slide.get("scene_kind") or "")
        beat_role = str(slide.get("beat_role") or "")
        scene_layout = (
            "parallel-examples"
            if scene_kind == "application"
            else "question-prompt"
            if scene_kind == "worked_example" and beat_role == "prompt"
            else "worked-example"
            if scene_kind == "worked_example"
            else "practice-feedback"
            if (
                scene_kind == "practice_feedback"
                and beat_role in {"feedback", "answer", "validation"}
            )
            else "question-prompt"
            if scene_kind == "practice_feedback" and beat_role == "prompt"
            else "editorial-body"
            if scene_kind == "practice_feedback"
            else None
        )
        if scene_layout:
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "requested_layout": scene_layout,
            }
    slides = _enrich_practice_feedback_slides_v5(slides)
    slides = [
        _normalize_concept_definition_slide_v5(slide)
        for slide in slides
    ]
    slides = [apply_page_contract_v5(slide) for slide in slides]
    slides = _assign_heading_modes_v5(slides)
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
        planning_diagnostics=outline.planning_diagnostics,
    )
    content["quality_summary"] = {
        **(content.get("quality_summary") or {}),
        "passed": content["quality_report"]["passed"],
        "score": content["quality_report"]["score"],
        **summarize_v5_slide_counts(slides),
    }
    # Fail at the V5 compiler boundary, before rendering or publication, if a
    # future semantic transform leaks planner-only fields into SlideSpec.
    SlideDeckContent.model_validate(content)
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
        planning_diagnostics=dict(
            outline.get("planning_diagnostics") or {}
        ),
    )
