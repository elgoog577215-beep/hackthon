"""Deck-level narrative and final page contracts for slide_deck_v5."""

from __future__ import annotations

import math
import os
import re
from copy import deepcopy
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, stable_hash
from slide_asset_repository import slide_asset_repository
from slide_deck import SlideDeckContent
from slide_deck_v3 import (
    ContentFragmentV1,
    DerivedTextV1,
    FragmentExclusionV1,
    PlannedPageV2,
    SlideAllocationPlanV2,
    compile_slide_deck_v3,
    fragment_course_document,
    slide_deck_variant_key,
    validate_allocation_plan,
)
from slide_quality_v5 import (
    build_slide_deck_quality_v5,
    repair_semantic_slides_v5,
)
from slide_semantics import (
    DOMAIN_PRESENTATION_PROFILE_VERSION,
    PPT_SEMANTIC_COMPILER_VERSION,
    FinalPageContractV2,
    TeachingEpisodeContractV2,
    compile_ppt_semantic_units,
    semantic_group_kind,
    semantic_unit_index,
)
from slide_story_plan import (
    V5_SEMANTIC_CORE_REASONS,
    ClaimSourceV2,
    SlideStoryPlanV2,
    StoryBeatV2,
    TeachingEpisodeV2,
)
from slide_visuals import deterministic_visual_plan
from slide_web_images import (
    VisualSearchRequestV5,
    WebImageRetrievalConfig,
    compute_image_target_v5,
    enrich_slides_with_generated_images_v5,
    enrich_slides_with_web_images_v5,
    web_image_retrieval_enabled,
)

SLIDE_DECK_V5_SCHEMA = "slide_deck_v5"
SLIDE_DECK_V5_COMPILER_VERSION = "course_logic_slide_compiler_v5.20"
DECK_OUTLINE_V5_VERSION = "deck_outline_v5.1"
FINAL_PAGE_CONTRACT_V5_VERSION = "final_page_contract_v5.12"
VISUAL_PLANNING_BATCH_VERSION = "chapter_visual_batches_v2.1"

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
    "实践案例行业应用",
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
    r"(?P<verb>分为|分成|可分为|包括|包含|共有|共计)"
    r"\s*(?P<count>[一二两三四五六七八九十百\d]+)\s*"
    r"(?P<unit>类|种|项|个|步|部分|方面|阶段|分支|层|区域|结构|边界|要点|平面)"
)
_TITLE_ENUMERATION_PATTERN = re.compile(
    r"(?P<count>[一二两三四五六七八九十百\d]+)\s*"
    r"(?:(?:类|种|项|步|部分|方面|阶段|分支|层|区域|结构|边界|要点|平面)|"
    r"个\s*(?:要点|重点|性质|特征|条件|步骤|原因|方法|结论|"
    r"原则|问题|维度|类别|类型|规则|标准|目标))"
)
_GENERIC_ENUMERATION_NOUN_PATTERN = re.compile(
    r"^\s*(?:要点|重点|性质|特征|条件|步骤|原因|方法|结论|"
    r"原则|问题|维度|类别|类型|规则|标准|目标)"
)
_INLINE_ENUMERATION_MEMBER_PATTERN = re.compile(
    r"(?:第\s*)?(?:[一二三四五六七八九十\d]+|"
    r"另\s*(?:一|二|三|四|五|六|七|八|九|十)?)"
    r"(?:类|种|项|步|部分|方面|阶段|分支|层|区域|结构|边界|要点|平面)"
    r"(?=\s*(?:是|为|指|：|:))"
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
_V5_DEFAULT_DENSITY_BUDGET = {"characters": 230, "items": 5, "title": 18}
_V5_DENSITY_BUDGETS = {
    "cover-minimal": {"characters": 90, "items": 0, "title": 22},
    "cover-editorial": {"characters": 120, "items": 0, "title": 22},
    "agenda-linear": {"characters": 240, "items": 6, "title": 18},
    "chapter-entry": {"characters": 120, "items": 0, "title": 22},
    "hero-claim": {"characters": 180, "items": 1, "title": 18},
    "editorial-body": {"characters": 230, "items": 5, "title": 18},
    "balanced-two-column": {"characters": 320, "items": 6, "title": 18},
    "classification-3": {"characters": 270, "items": 3, "title": 18},
    "parallel-examples": {"characters": 320, "items": 4, "title": 18},
    "question-prompt": {"characters": 220, "items": 4, "title": 18},
    "process-sequence": {"characters": 240, "items": 5, "title": 18},
    "formula-explanation": {"characters": 280, "items": 4, "title": 18},
    "figure-text": {"characters": 320, "items": 5, "title": 18},
    "diagram-full": {"characters": 0, "items": 0, "title": 18},
    "worked-example": {"characters": 230, "items": 3, "title": 18},
    "practice-feedback": {"characters": 260, "items": 6, "title": 18},
    "chapter-recap": {"characters": 220, "items": 4, "title": 18},
    "course-synthesis": {"characters": 240, "items": 6, "title": 18},
}
_V5_MINIMUM_BODY_FONT_PT = 16
_V5_MINIMUM_TITLE_FONT_PT = 35
_V5_SCENE_NARRATIVE_ROLE = {
    "chapter_entry": "orientation",
    "prerequisite_activation": "orientation",
    "concept": "concept",
    "reasoning": "reasoning",
    "method": "method",
    "process": "method",
    "worked_example": "example",
    "practice_feedback": "checkpoint",
    "misconception": "misconception",
    "application": "example",
    "comparison": "reasoning",
    "evidence": "reasoning",
    "chapter_recap": "recap",
}
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
    "slide_title_too_long",
    "visible_item_overflow",
    "enumeration_cardinality_mismatch",
}
_T = TypeVar("_T")


def _v5_fragment_groups(fragments: list[Any]) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current: list[Any] = []
    for fragment in sorted(fragments, key=lambda item: item.ordinal):
        if current and fragment.block_id != current[-1].block_id:
            groups.append(current)
            current = []
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


def _v5_fragment_groups_for_profile(
    fragments: list[Any],
    *,
    profile: str,
) -> list[list[Any]]:
    if profile == "semantic":
        return _v5_fragment_groups(fragments)
    if profile != "quality_fallback":
        raise ValueError(f"Unsupported V5 compaction profile: {profile}")

    # Legacy material often stores every paragraph or list item in its own
    # block. Splitting at those storage boundaries promoted each fragment to a
    # standalone teaching episode (78 beats / 120 pages for the anatomy deck).
    # Explicit source headings are the stable narrative boundary for fallback.
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


def _v5_group_kind(
    group: list[Any],
    semantic_by_fragment: dict[str, Any] | None = None,
) -> str:
    semantic_units = list(dict.fromkeys(
        semantic_by_fragment[item.fragment_id].semantic_unit_id
        for item in group
        if (
            semantic_by_fragment is not None
            and item.fragment_id in semantic_by_fragment
        )
    ))
    unit_by_id = {
        semantic_by_fragment[item.fragment_id].semantic_unit_id:
        semantic_by_fragment[item.fragment_id]
        for item in group
        if (
            semantic_by_fragment is not None
            and item.fragment_id in semantic_by_fragment
        )
    }
    explicit_kinds = [
        semantic_group_kind(unit_by_id[unit_id])
        for unit_id in semantic_units
        if (
            unit_by_id[unit_id].adapter_type == "v16_structured"
            or unit_by_id[unit_id].primary_role != "concept"
        )
    ]
    if explicit_kinds:
        return next(
            (
                kind
                for kind in (
                    "practice",
                    "feedback",
                    "worked",
                    "application",
                    "misconception",
                    "method",
                    "reasoning",
                    "concept",
                    "navigation",
                    "recap",
                )
                if kind in explicit_kinds
            ),
            explicit_kinds[0],
        )
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
    if semantic_units:
        return semantic_group_kind(unit_by_id[semantic_units[0]])
    return "concept"


def _v5_group_kind_for_profile(
    group: list[Any],
    semantic_by_fragment: dict[str, Any],
    *,
    profile: str,
) -> str:
    """Choose source-explicit grouping for the quality fallback profile.

    The semantic adapter intentionally infers checkpoints from legacy prose.
    That inference is useful for the normal planner, but using it again after
    an AI candidate has already failed can turn every instructional hint into
    a separate practice episode.  The fallback therefore trusts explicit
    source headings and roles, producing the smaller source-bound plan.
    """
    if profile == "quality_fallback":
        return _v5_group_kind(group)
    if profile != "semantic":
        raise ValueError(f"Unsupported V5 compaction profile: {profile}")
    return _v5_group_kind(group, semantic_by_fragment)


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
    text = str(value or "")
    counts: list[int] = []
    for match in _ENUMERATION_PROMISE_PATTERN.finditer(text):
        count = _chinese_count(match.group("count"))
        if count is None or count < 2:
            continue
        if (
            match.group("verb") in {"共有", "共计"}
            and match.group("unit") == "个"
            and not _GENERIC_ENUMERATION_NOUN_PATTERN.match(
                text[match.end():match.end() + 12]
            )
        ):
            continue
        counts.append(count)
    english_numbers = {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    for match in re.finditer(
        r"\b(?:divided|classified|grouped|organized)\s+into\s+"
        r"(?P<count>\d+|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:regions|types|groups|categories|parts|steps|stages)\b",
        text,
        flags=re.IGNORECASE,
    ):
        token = match.group("count").lower()
        count = int(token) if token.isdigit() else english_numbers[token]
        if count >= 2:
            counts.append(count)
    return counts


def _title_enumeration_counts(value: str) -> list[int]:
    return [
        count
        for match in _TITLE_ENUMERATION_PATTERN.finditer(str(value or ""))
        if (
            (count := _chinese_count(match.group("count"))) is not None
            and count >= 2
        )
    ]


def _inline_enumeration_member_count(value: str) -> int:
    """Count members written inline after an explicit enumeration promise."""
    text = str(value or "")
    member_count = 0
    for promise in _ENUMERATION_PROMISE_PATTERN.finditer(text):
        sentence_tail = re.split(
            r"[。！？!?\n]",
            text[promise.end():],
            maxsplit=1,
        )[0]
        member_count = max(
            member_count,
            len(_INLINE_ENUMERATION_MEMBER_PATTERN.findall(sentence_tail)),
        )
    return member_count


def _v5_required_enumeration_fragments(group: list[Any]) -> set[str]:
    """Return source fragments that form an indivisible enumerated claim."""
    for index, fragment in enumerate(group):
        counts = _enumeration_counts(str(fragment.text or ""))
        if not counts:
            continue
        expected = counts[0]
        member_runs: list[list[Any]] = []
        current_run: list[Any] = []
        for candidate in group[index + 1 :]:
            if candidate.kind == "heading":
                if current_run:
                    member_runs.append(current_run)
                    current_run = []
                continue
            if candidate.kind == "list_item":
                current_run.append(candidate)
                continue
            if current_run:
                member_runs.append(current_run)
                current_run = []
        if current_run:
            member_runs.append(current_run)
        members = next(
            (run for run in member_runs if len(run) == expected),
            [],
        )
        if members:
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


def _v5_fit_group(
    group: list[Any],
    *,
    limit: int = 230,
    preserve_all: bool = False,
) -> list[Any]:
    if not _formula_group_has_source_explanation(group):
        return []
    if preserve_all:
        visible = sum(len(str(fragment.text or "")) for fragment in group)
        return list(group) if len(group) <= 8 and visible <= limit else []
    required_ids = _v5_required_enumeration_fragments(group)
    if not required_ids:
        unresolved_promise_ids = {
            fragment.fragment_id
            for fragment in group
            if (
                (counts := _enumeration_counts(str(fragment.text or "")))
                and _inline_enumeration_member_count(
                    str(fragment.text or "")
                ) < max(counts)
            )
        }
        if unresolved_promise_ids:
            resolved_detail = [
                fragment
                for fragment in group
                if fragment.fragment_id not in unresolved_promise_ids
            ]
            if not resolved_detail:
                return []
            group = resolved_detail
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
            # Optional sibling list items would change the visible cardinality
            # of the source promise. Keep only the exact member run selected
            # above; surrounding prose may still be retained when it fits.
            if fragment.kind == "list_item":
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


def _v5_fit_practice_group(
    group: list[Any],
    semantic_by_fragment: dict[str, Any],
    *,
    limit: int = 400,
) -> list[Any]:
    """Keep a compact, identity-safe question/feedback slice from rich blocks."""
    if not group:
        return []

    def role(fragment: Any) -> str:
        unit = semantic_by_fragment.get(fragment.fragment_id)
        return str(getattr(unit, "primary_role", "") or fragment.role or "")

    prompts = [
        fragment
        for fragment in group
        if (
            fragment.kind != "heading"
            and role(fragment) in {"activity", "checkpoint"}
        )
    ]
    if not prompts:
        return _v5_fit_group(group, limit=limit)
    explicit_prompts = [
        fragment
        for fragment in prompts
        if any(mark in str(fragment.text or "") for mark in ("?", "\uff1f"))
    ]
    list_prompts = [
        fragment for fragment in prompts if fragment.kind == "list_item"
    ]
    prompt_candidates = (explicit_prompts or list_prompts or prompts[:1])[:3]

    feedback = [
        fragment
        for fragment in group
        if fragment.kind != "heading" and role(fragment) == "feedback"
    ]
    list_feedback = [
        fragment for fragment in feedback if fragment.kind == "list_item"
    ]
    feedback_candidates = list_feedback or feedback
    if feedback_candidates:
        pair_count = min(len(prompt_candidates), len(feedback_candidates), 3)
        prompt_candidates = prompt_candidates[:pair_count]
        feedback_candidates = feedback_candidates[:pair_count]
    else:
        feedback_candidates = []

    selected: list[Any] = []
    visible = 0
    for index, prompt in enumerate(prompt_candidates):
        pair = [prompt]
        if index < len(feedback_candidates):
            pair.append(feedback_candidates[index])
        pair_size = sum(len(str(fragment.text or "")) for fragment in pair)
        if selected and visible + pair_size > limit:
            break
        if not selected and pair_size > limit:
            continue
        selected.extend(pair)
        visible += pair_size
    return sorted(
        {fragment.fragment_id: fragment for fragment in selected}.values(),
        key=lambda item: item.ordinal,
    )


def _v5_bound_question_ids(
    group: list[Any],
    semantic_by_fragment: dict[str, Any],
    fragment_catalog: dict[str, Any],
) -> tuple[list[str], list[str]]:
    selected_ids = {fragment.fragment_id for fragment in group}
    units = list({
        semantic_by_fragment[fragment.fragment_id].semantic_unit_id:
            semantic_by_fragment[fragment.fragment_id]
        for fragment in group
        if fragment.fragment_id in semantic_by_fragment
    }.values())
    question_ids: list[str] = []
    has_feedback = False
    for unit in units:
        if unit.primary_role in {"activity", "checkpoint"}:
            candidates = [
                fragment_catalog[fragment_id]
                for fragment_id in unit.fragment_ids
                if (
                    fragment_id in fragment_catalog
                    and fragment_catalog[fragment_id].kind != "heading"
                )
            ]
            explicit = [
                fragment
                for fragment in candidates
                if any(
                    mark in str(fragment.text or "")
                    for mark in ("?", "\uff1f")
                )
            ]
            listed = [
                fragment for fragment in candidates
                if fragment.kind == "list_item"
            ]
            question_fragments = explicit or listed or candidates[:1]
            question_by_fragment = dict(zip(
                [fragment.fragment_id for fragment in question_fragments],
                unit.question_ids,
            ))
            question_ids.extend(
                question_by_fragment[fragment.fragment_id]
                for fragment in question_fragments
                if (
                    fragment.fragment_id in selected_ids
                    and fragment.fragment_id in question_by_fragment
                )
            )
        elif unit.primary_role == "feedback":
            has_feedback = True
    question_ids = list(dict.fromkeys(question_ids))
    return question_ids, list(question_ids) if has_feedback else []


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
    *,
    profile: str = "semantic",
) -> SlideStoryPlanV2:
    """Select three complete, source-bound teaching groups per source section.

    Detailed source fragments remain available as explicit coverage decisions
    instead of being copied into dense appendix slides.
    """
    if profile not in {"semantic", "quality_fallback"}:
        raise ValueError(f"Unsupported V5 compaction profile: {profile}")
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
    semantic_units = compile_ppt_semantic_units(document, source_fragments)
    semantic_by_fragment = semantic_unit_index(semantic_units)
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
            groups = _v5_fragment_groups_for_profile(
                fragments_by_section.get(section_id, []),
                profile=profile,
            )
            by_kind: dict[str, list[list[Any]]] = {}
            for group in groups:
                by_kind.setdefault(
                    _v5_group_kind_for_profile(
                        group,
                        semantic_by_fragment,
                        profile=profile,
                    ),
                    [],
                ).append(group)
            selected_groups: list[tuple[str, list[Any]]] = []
            if by_kind.get("concept"):
                concept_group = list(by_kind["concept"][0])
                if (
                    profile == "semantic"
                    and any(
                        _enumeration_counts(str(item.text or ""))
                        for item in concept_group
                    )
                    and not _v5_required_enumeration_fragments(concept_group)
                ):
                    for sibling_group in by_kind["concept"][1:]:
                        merged = sorted(
                            {
                                item.fragment_id: item
                                for item in [*concept_group, *sibling_group]
                            }.values(),
                            key=lambda item: item.ordinal,
                        )
                        if _v5_required_enumeration_fragments(merged):
                            concept_group = merged
                            break
                selected_groups.append(("concept", concept_group))
            second = next(
                (
                    (kind, by_kind[kind][0])
                    for kind in (
                        (
                            "worked",
                            "application",
                            "method",
                            "reasoning",
                        )
                        if profile == "quality_fallback"
                        else (
                            "worked",
                            "application",
                            "method",
                            "reasoning",
                            "misconception",
                        )
                    )
                    if by_kind.get(kind)
                ),
                None,
            )
            if second:
                selected_groups.append(second)
            if by_kind.get("practice"):
                practice_group = list(by_kind["practice"][0])
                if profile == "semantic" and by_kind.get("feedback"):
                    practice_group.extend(by_kind["feedback"][0])
                    practice_group = sorted(
                        {
                            item.fragment_id: item
                            for item in practice_group
                        }.values(),
                        key=lambda item: item.ordinal,
                    )
                selected_groups.append(("practice", practice_group))
            if len(selected_groups) < 3:
                used_fragment_ids = {
                    item.fragment_id
                    for _kind, group in selected_groups
                    for item in group
                }
                for group in groups:
                    if (
                        not group
                        or any(
                            item.fragment_id in used_fragment_ids
                            for item in group
                        )
                    ):
                        continue
                    fallback_kind = _v5_group_kind_for_profile(
                        group,
                        semantic_by_fragment,
                        profile=profile,
                    )
                    if (
                        profile == "semantic"
                        and fallback_kind in {"navigation", "feedback", "recap"}
                    ):
                        continue
                    selected_groups.append((fallback_kind, group))
                    if len(selected_groups) == 3:
                        break
            for group_index, (kind, raw_group) in enumerate(selected_groups[:3]):
                group = (
                    _v5_fit_practice_group(
                        raw_group,
                        semantic_by_fragment,
                        limit=400,
                    )
                    if kind == "practice" and profile == "semantic"
                    else _v5_fit_group(raw_group, limit=230)
                )
                if not group:
                    continue
                scene = {
                    "worked": "worked_example",
                    "application": "application",
                    "practice": "practice_feedback",
                    "method": "method",
                    "reasoning": "reasoning",
                    "misconception": "misconception",
                }.get(kind, "concept")
                role = (
                    "prompt"
                    if scene in {"worked_example", "practice_feedback"}
                    else "procedure"
                    if scene == "method"
                    else "reasoning_step"
                    if scene == "reasoning"
                    else "misconception"
                    if scene == "misconception"
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
                    "misconception": (
                        "balanced-two-column",
                        "misconception",
                        "misconception",
                    ),
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
                group_semantic_units = list({
                    semantic_by_fragment[item.fragment_id].semantic_unit_id:
                        semantic_by_fragment[item.fragment_id]
                    for item in group
                    if item.fragment_id in semantic_by_fragment
                }.values())
                bound_question_ids, bound_answer_ids = (
                    _v5_bound_question_ids(
                        group,
                        semantic_by_fragment,
                        fragment_catalog,
                    )
                    if scene == "practice_feedback"
                    else ([], [])
                )
                beat = StoryBeatV2(
                    beat_id=beat_id,
                    beat_role=role,
                    teaching_job={
                        "worked_example": "用来源案例展示判断与验证",
                        "application": "比较来源中的实际应用情境",
                        "practice_feedback": "用来源问题检查理解",
                        "method": "把本节知识转化为可执行步骤",
                        "reasoning": "说明结论如何从条件推出",
                        "misconception": "识别常见误区并说明修正依据",
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
                    semantic_unit_ids=[
                        unit.semantic_unit_id for unit in group_semantic_units
                    ],
                    question_ids=(
                        bound_question_ids
                        if scene == "practice_feedback"
                        else list(dict.fromkeys(
                            question_id
                            for unit in group_semantic_units
                            for question_id in unit.question_ids
                        ))
                    ),
                    answer_for_question_ids=(
                        bound_answer_ids
                        if scene == "practice_feedback"
                        else list(dict.fromkeys(
                            question_id
                            for unit in group_semantic_units
                            for question_id in unit.answer_for_question_ids
                        ))
                    ),
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
    structured_count = sum(
        unit.adapter_type == "v16_structured"
        for unit in semantic_units
    )
    role_counts = {
        role: sum(unit.primary_role == role for unit in semantic_units)
        for role in sorted({unit.primary_role for unit in semantic_units})
    }
    intent_counts = {
        intent: sum(
            unit.presentation_intent == intent for unit in semantic_units
        )
        for intent in sorted({
            unit.presentation_intent for unit in semantic_units
        })
    }
    question_ids = {
        question_id
        for unit in semantic_units
        for question_id in unit.question_ids
    }
    answered_question_ids = {
        question_id
        for unit in semantic_units
        for question_id in unit.answer_for_question_ids
    }
    episode_contracts: list[TeachingEpisodeContractV2] = []
    for compact_chapter in compact_chapters:
        for episode in compact_chapter.episodes[1:-1]:
            episode_fragment_ids = list(dict.fromkeys(
                fragment_id
                for beat in episode.beats
                for fragment_id in beat.fragment_ids
                if fragment_id in semantic_by_fragment
            ))
            episode_units = sorted(
                {
                    semantic_by_fragment[fragment_id].semantic_unit_id:
                    semantic_by_fragment[fragment_id]
                    for fragment_id in episode_fragment_ids
                }.values(),
                key=lambda item: item.source_ordinal,
            )
            if not episode_units:
                continue
            presentation_intent = (
                "practice_feedback"
                if episode.scene_kind == "practice_feedback"
                else episode_units[0].presentation_intent
            )
            episode_contracts.append(TeachingEpisodeContractV2(
                episode_id=episode.episode_id,
                section_id=episode_units[0].section_id,
                presentation_intent=presentation_intent,
                semantic_unit_ids=[
                    unit.semantic_unit_id for unit in episode_units
                ],
                question_ids=list(dict.fromkeys(
                    question_id
                    for unit in episode_units
                    for question_id in unit.question_ids
                )),
                answer_for_question_ids=list(dict.fromkeys(
                    question_id
                    for unit in episode_units
                    for question_id in unit.answer_for_question_ids
                )),
                source_fragment_ids=episode_fragment_ids,
            ))
    return story.model_copy(update={
        "chapters": compact_chapters,
        "planning_diagnostics": {
            **(story.planning_diagnostics or {}),
            "semantic_compiler_version": PPT_SEMANTIC_COMPILER_VERSION,
            "compaction_profile": profile,
            "semantic_unit_count": len(semantic_units),
            "structured_semantic_unit_count": structured_count,
            "legacy_semantic_unit_count": len(semantic_units) - structured_count,
            "domain_profile_ids": sorted({
                unit.domain_profile_id for unit in semantic_units
            }),
            "semantic_role_counts": role_counts,
            "presentation_intent_counts": intent_counts,
            "balanced_composition_unit_count": sum(
                unit.composition_style == "balanced"
                for unit in semantic_units
            ),
            "knowledge_binding_unmapped_count": sum(
                unit.adapter_type == "v16_structured"
                and unit.knowledge_binding_status not in {"bound", "mapped"}
                for unit in semantic_units
            ),
            "question_answer_binding_coverage": (
                len(question_ids & answered_question_ids) / len(question_ids)
                if question_ids
                else 1.0
            ),
            "teaching_episode_contracts": [
                contract.model_dump(mode="json")
                for contract in episode_contracts
            ],
        },
    })


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
    result: list[list[_T]] = []
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
            metadata = block.get("metadata") or {}
            comparison_rows = (
                metadata.get("rows")
                if str(block.get("type") or "") == "comparison"
                else None
            )
            body_values.extend([
                _clean_text(block.get("title")),
                _clean_text(block.get("content")),
            ])
            if isinstance(comparison_rows, list) and comparison_rows:
                body_values.extend(
                    _clean_text(cell)
                    for row in comparison_rows
                    if isinstance(row, list)
                    for cell in row
                )
            else:
                body_values.extend(
                    _clean_text(item)
                    for item in block.get("items") or []
                )
    body_character_count = sum(
        len(value)
        for value in body_values
        if value
    )
    item_count = 0
    paired_prompt_items = 0
    paired_feedback_items = 0
    paired_other_items = 0
    count_paired_rows = bool(
        resolved_layout == "practice-feedback"
        and str(quality.get("feedback_mode") or "") == "paired"
    )
    for block in slide.get("blocks") or []:
        metadata = block.get("metadata") or {}
        comparison_rows = (
            metadata.get("rows")
            if str(block.get("type") or "") == "comparison"
            else None
        )
        if isinstance(comparison_rows, list) and comparison_rows:
            block_item_count = len([
                row for row in comparison_rows
                if isinstance(row, list) and any(_clean_text(cell) for cell in row)
            ])
        else:
            block_item_count = len([
                item
                for item in block.get("items") or []
                if _clean_text(item)
            ])
        if not count_paired_rows:
            item_count += block_item_count
            continue
        semantic_role = str(metadata.get("semantic_role") or "")
        if semantic_role == "prompt":
            paired_prompt_items += block_item_count
        elif semantic_role in {"answer", "feedback", "solution", "validation"}:
            paired_feedback_items += block_item_count
        else:
            paired_other_items += block_item_count
    if count_paired_rows:
        # Prompt and answer columns share one vertical row per bound question.
        # Counting both columns independently rejects a three-row page as six
        # visible items even though the renderer lays them out side by side.
        item_count = (
            max(paired_prompt_items, paired_feedback_items)
            + paired_other_items
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
    visible = _clean_text(value)
    if re.search(r"(?:[：:，,、；;]|以及|并且|包括|如下)\s*$", visible):
        return False
    clean = visible.rstrip("。！？!? ")
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
_ITEM_GROUP_LABEL = re.compile(
    r"^\s*\*\*(?P<label>[^*\n]{1,40}?)\*\*\s*[:：]?\s*$"
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


def _promote_item_group_labels(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn markdown-only list labels into real semantic block headings."""
    promoted: list[dict[str, Any]] = []
    for source_block in blocks:
        items = list(source_block.get("items") or [])
        labels = [
            (index, _clean_text(match.group("label")))
            for index, item in enumerate(items)
            if (match := _ITEM_GROUP_LABEL.match(str(item or ""))) is not None
        ]
        if not labels:
            promoted.append(source_block)
            continue

        first_label_index = labels[0][0]
        prefix_items = items[:first_label_index]
        if prefix_items:
            prefix = deepcopy(source_block)
            prefix["items"] = prefix_items
            promoted.append(prefix)

        for label_index, (item_index, label) in enumerate(labels):
            next_index = (
                labels[label_index + 1][0]
                if label_index + 1 < len(labels)
                else len(items)
            )
            group_items = [
                item for item in items[item_index + 1 : next_index]
                if _clean_text(item)
            ]
            if not group_items:
                continue
            group = deepcopy(source_block)
            group["block_id"] = (
                f"{source_block.get('block_id') or 'block'}:group:{label_index + 1}"
            )
            group["title"] = label
            group["content"] = (
                source_block.get("content")
                if label_index == 0 and not prefix_items
                else ""
            )
            group["items"] = group_items
            group["metadata"] = {
                **(source_block.get("metadata") or {}),
                "source_group_label": label,
            }
            promoted.append(group)
    return promoted


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
    elif (
        len(classification) == 3
        and sum(
            len([item for item in block.get("items") or [] if _clean_text(item)])
            for block in slide.get("blocks") or []
        ) <= 3
    ):
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
        if (
            requested_layout == "diagram-full"
            or requested_composition == "diagram-full"
        ):
            resolved_layout = "figure-text"
            resolved_composition = "split-visual"
            fallback_reason = "diagram_full_with_source_text"
        else:
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
    updated["blocks"] = _promote_item_group_labels(
        _structure_visible_enumerations(
            list(updated.get("blocks") or [])
        )
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


def repair_final_page_contracts_v5(
    slides: list[dict[str, Any]],
    *,
    max_passes: int = 2,
) -> list[dict[str, Any]]:
    """Re-resolve final visible contracts after deterministic normalization."""
    current = [deepcopy(slide) for slide in slides]
    pass_limit = max(1, min(2, int(max_passes)))
    completed_passes = 0
    for pass_index in range(pass_limit):
        before = stable_hash(current, prefix="repair_before_")
        current = [apply_page_contract_v5(slide) for slide in current]
        completed_passes = pass_index + 1
        after = stable_hash(current, prefix="repair_before_")
        if after == before:
            break
    for slide in current:
        quality = slide.get("quality") or {}
        source_fragment_ids = list(dict.fromkeys([
            str((slide.get("primary_claim_source") or {}).get("fragment_id") or ""),
            *[
                str(fragment_id or "")
                for block in slide.get("blocks") or []
                for fragment_id in (
                    (block.get("metadata") or {}).get("source_fragment_ids")
                    or []
                )
            ],
        ]))
        source_fragment_ids = [
            fragment_id for fragment_id in source_fragment_ids if fragment_id
        ]
        final_contract = FinalPageContractV2(
            page_id=str(slide.get("unit_id") or ""),
            teaching_intent=str(
                slide.get("teaching_job")
                or slide.get("scene_kind")
                or slide.get("slide_purpose")
                or "teaching"
            ),
            requested_layout=str(quality.get("requested_layout") or ""),
            resolved_layout=str(quality.get("resolved_layout") or ""),
            occupied_slot_ids=[
                str(binding.get("slot_id") or "")
                for binding in quality.get("slot_bindings") or []
                if str(binding.get("slot_id") or "")
            ],
            source_fragment_ids=source_fragment_ids,
            repair_passes=completed_passes,
            passed=not v5_contract_issues([slide]),
        )
        slide["quality"] = {
            **quality,
            "repair_passes": completed_passes,
            "final_page_contract_version": FINAL_PAGE_CONTRACT_V5_VERSION,
            "final_page_contract_v2": final_contract.model_dump(mode="json"),
        }
    return current


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
                limit=52,
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
        "title": f"回顾：{_clean_text(chapter.title)[:14]}",
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
    quality = slide.get("quality") or {}
    declared_ids = [
        _clean_text(question_id)
        for question_id in quality.get("question_ids") or []
        if _clean_text(question_id)
    ]
    generated_ids = [
        _clean_text(answer.get("question_id"))
        for answer in quality.get("generated_practice_answers") or []
        if (
            isinstance(answer, dict)
            and _clean_text(answer.get("question_id"))
        )
    ]
    for candidates in (declared_ids, generated_ids):
        if len(candidates) == count and len(set(candidates)) == count:
            return candidates
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
        direct_answer_for_ids = list(dict.fromkeys(
            _clean_text(question_id)
            for block in direct_blocks
            for question_id in (
                (block.get("metadata") or {}).get(
                    "answer_for_question_ids"
                )
                or []
            )
            if _clean_text(question_id)
        ))
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
                direct_answer_for_ids = [
                    _clean_text(question_id)
                    for question_id in (
                        (candidate.get("quality") or {}).get(
                            "answer_for_question_ids"
                        )
                        or []
                    )
                    if _clean_text(question_id)
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
        if (
            len(prompt_values) == 1
            and len(generated_answers) > 1
            and all(_clean_text(item.get("answer_text")) for item in generated_answers)
        ):
            # The renderer may collapse several paragraph fragments into one
            # compound visible prompt. Preserve the one-row identity contract
            # by publishing one compound direct answer instead of rejecting
            # otherwise valid LLM answers because their source granularity is
            # finer than the rendered block granularity.
            generated_answers = [{
                "question_index": 0,
                "question_id": question_ids[0],
                "answer_source": "llm_generated",
                "answer_text": "；".join(
                    _clean_text(item.get("answer_text")).rstrip("。；; ")
                    for item in generated_answers
                ) + "。",
                "supporting_fragment_ids": list(dict.fromkeys(
                    fragment_id
                    for item in generated_answers
                    for fragment_id in item.get("supporting_fragment_ids") or []
                    if _clean_text(fragment_id)
                )),
            }]
        generated_answer_by_id = {
            _clean_text(item.get("question_id")): item
            for item in generated_answers
            if (
                _clean_text(item.get("question_id"))
                and _clean_text(item.get("answer_text"))
            )
        }
        if (
            len(generated_answer_by_id) == len(prompt_values)
            and set(generated_answer_by_id) == set(question_ids)
        ):
            direct_answers = [
                _clean_text(
                    generated_answer_by_id[question_id].get("answer_text")
                )
                for question_id in question_ids
            ]
            source_fragment_ids = list(dict.fromkeys(
                fragment_id
                for item in generated_answers
                for fragment_id in item.get("supporting_fragment_ids") or []
                if _clean_text(fragment_id)
            ))
            answer_mode = "llm_generated"
        else:
            if len(direct_answers) == len(prompt_values) == 1:
                direct_answer_for_ids = list(question_ids)
            if (
                len(direct_answers) == len(prompt_values)
                and len(direct_answer_for_ids) == len(direct_answers)
                and set(direct_answer_for_ids) == set(question_ids)
            ):
                source_answer_by_id = dict(zip(
                    direct_answer_for_ids,
                    direct_answers,
                    strict=True,
                ))
                direct_answers = [
                    source_answer_by_id[question_id]
                    for question_id in question_ids
                ]
            else:
                direct_answers = []
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

        if len(direct_answers) == len(prompt_values) and prompt_values:
            answer_block = {
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
            }
            # The renderer exposes one prompt column and one answer column.
            # Any source checklist used to derive those answers is evidence,
            # not a third visible column. Keeping it here makes the quality
            # gate count content that the renderer does not display.
            slide["blocks"] = [prompt, answer_block]
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
            feedback_block = {
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
            }
            # Shared evidence is the second visible region. Supporting source
            # checklists remain provenance only and must not become a hidden
            # third region that disagrees with the renderer's 3+3 contract.
            slide["blocks"] = [prompt, feedback_block]
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


def _split_practice_feedback_capacity_v5(
    slides: list[dict[str, Any]],
    *,
    maximum_questions: int = 3,
) -> list[dict[str, Any]]:
    """Paginate practice rows to the exact capacity used by the renderer."""
    limit = max(1, int(maximum_questions))
    result: list[dict[str, Any]] = []
    for source in slides:
        quality = source.get("quality") or {}
        if str(quality.get("requested_layout") or "") != "practice-feedback":
            result.append(source)
            continue
        blocks = list(source.get("blocks") or [])
        prompt_index = next((
            index
            for index, block in enumerate(blocks)
            if str((block.get("metadata") or {}).get("semantic_role") or "")
            == "prompt"
        ), -1)
        if prompt_index < 0:
            result.append(source)
            continue
        prompt_values = _practice_block_values(blocks[prompt_index])
        if len(prompt_values) <= limit:
            result.append(source)
            continue
        prompt_ids = [
            _clean_text(value)
            for value in (
                (blocks[prompt_index].get("metadata") or {}).get("question_ids")
                or []
            )
            if _clean_text(value)
        ]
        if len(prompt_ids) != len(prompt_values):
            prompt_ids = _practice_question_ids(source, len(prompt_values))
        feedback_mode = str(quality.get("feedback_mode") or "")
        page_count = (len(prompt_values) + limit - 1) // limit
        for page_index, start in enumerate(range(0, len(prompt_values), limit)):
            end = min(start + limit, len(prompt_values))
            page = deepcopy(source)
            if page_index:
                page["unit_id"] = (
                    f"{source.get('unit_id') or 'practice'}:practice:{page_index + 1}"
                )
            page_blocks = list(page.get("blocks") or [])
            prompt_block = page_blocks[prompt_index]
            prompt_block["content"] = ""
            prompt_block["items"] = prompt_values[start:end]
            prompt_block["metadata"] = {
                **(prompt_block.get("metadata") or {}),
                "question_ids": prompt_ids[start:end],
            }
            for block_index, block in enumerate(page_blocks):
                if block_index == prompt_index:
                    continue
                metadata = block.get("metadata") or {}
                role = str(metadata.get("semantic_role") or "")
                if role not in {"answer", "feedback", "solution", "validation"}:
                    continue
                values = _practice_block_values(block)
                if feedback_mode == "paired" and len(values) == len(prompt_values):
                    block["content"] = ""
                    block["items"] = values[start:end]
                    block["metadata"] = {
                        **metadata,
                        "answer_for_question_ids": prompt_ids[start:end],
                    }
                elif feedback_mode == "shared_evidence":
                    block["content"] = ""
                    block["items"] = values[:limit]
            page["quality"] = {
                **quality,
                "question_ids": prompt_ids[start:end],
                "feedback_pair_count": (
                    end - start if feedback_mode == "paired" else 0
                ),
                "practice_page_index": page_index + 1,
                "practice_page_count": page_count,
                "practice_capacity_split": True,
            }
            result.append(page)
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


def _v5_title_text(value: str) -> str:
    normalized = _clean_text(value)
    if len(normalized) <= 72:
        return normalized
    for marker in ("。", "；", "：", ";", ":"):
        index = normalized.find(marker, 20, 72)
        if index >= 0:
            return normalized[: index + 1]
    return normalized[:71].rstrip() + "…"


def _stable_v5_page_id(
    *,
    chapter_id: str,
    episode_id: str,
    beat_id: str,
    fragment_ids: list[str],
    part_index: int,
) -> str:
    digest = stable_hash({
        "chapter_id": chapter_id,
        "episode_id": episode_id,
        "beat_id": beat_id,
        "fragment_ids": fragment_ids,
        "part_index": part_index,
    }, prefix="v5p_")
    return f"slide:v5:{digest.removeprefix('v5p_')}"


def _semantic_atom_groups_v5(
    fragments: list[ContentFragmentV1],
) -> list[list[ContentFragmentV1]]:
    """Keep headings, questions/options/answers, processes, and tables intact."""
    ordered = sorted(fragments, key=lambda item: item.ordinal)
    if not ordered:
        return []
    groups = _v5_fragment_groups(ordered)
    result: list[list[ContentFragmentV1]] = []
    for group in groups:
        current: list[ContentFragmentV1] = []
        for fragment in group:
            starts_new = bool(
                current
                and fragment.kind == "heading"
                and any(item.kind != "heading" for item in current)
            )
            if starts_new:
                result.append(current)
                current = []
            current.append(fragment)
        if current:
            result.append(current)
    return result


def _complete_source_semantics_v5(
    selected: list[ContentFragmentV1],
    *,
    all_fragments: list[ContentFragmentV1],
    reserved_ids: set[str],
) -> list[ContentFragmentV1]:
    """Include omitted source members required to close a selected list lead."""
    if not selected:
        return []
    ordered = sorted(all_fragments, key=lambda item: item.ordinal)
    ordinal_index = {item.ordinal: index for index, item in enumerate(ordered)}
    completed = {item.fragment_id: item for item in selected}

    # A compact story beat may retain two list labels while skipping the source
    # member between them. Fill only gaps from the same source block.
    selected_ordered = sorted(selected, key=lambda item: item.ordinal)
    for left, right in zip(selected_ordered, selected_ordered[1:]):
        if not left.block_id or left.block_id != right.block_id:
            continue
        for candidate in ordered[
            ordinal_index[left.ordinal] + 1 : ordinal_index[right.ordinal]
        ]:
            if candidate.block_id != left.block_id or candidate.kind == "heading":
                break
            if candidate.fragment_id not in reserved_ids:
                completed[candidate.fragment_id] = candidate

    # A colon-ended source fragment promises members that must remain visible.
    # Continue within the same source block, stopping at the stated cardinality
    # or the next semantic boundary.
    for lead in sorted(completed.values(), key=lambda item: item.ordinal):
        lead_text = _clean_text(lead.text)
        if not re.search(r"[：:]\s*$", lead_text):
            continue
        expected_counts = [
            *_enumeration_counts(lead_text),
            *_title_enumeration_counts(lead_text),
        ]
        expected = max(expected_counts, default=0)
        appended = 0
        for candidate in ordered[ordinal_index[lead.ordinal] + 1 :]:
            if candidate.block_id != lead.block_id or candidate.kind == "heading":
                break
            if candidate.fragment_id in completed:
                if candidate.kind == "list_item":
                    appended += 1
                continue
            if candidate.fragment_id in reserved_ids or candidate.kind != "list_item":
                break
            completed[candidate.fragment_id] = candidate
            appended += 1
            if expected and appended >= expected:
                break
    return sorted(completed.values(), key=lambda item: item.ordinal)


def _split_oversized_atom_v5(
    atom: list[ContentFragmentV1],
    *,
    capacity: int,
    item_capacity: int,
) -> list[list[ContentFragmentV1]]:
    visible_items = sum(item.kind == "list_item" for item in atom)
    if (
        len(atom) <= 8
        and visible_items <= item_capacity
        and sum(len(item.text) for item in atom) <= capacity
    ):
        return [atom]
    chunks: list[list[ContentFragmentV1]] = []
    current: list[ContentFragmentV1] = []
    current_size = 0
    current_items = 0
    for fragment in atom:
        fragment_size = len(fragment.text)
        fragment_items = int(fragment.kind == "list_item")
        if current and (
            len(current) >= 8
            or current_size + fragment_size > capacity
            or current_items + fragment_items > item_capacity
        ):
            if re.search(r"[：:]\s*$", _clean_text(current[-1].text)):
                lead = current.pop()
                if current:
                    chunks.append(current)
                current = [lead]
                current_size = len(lead.text)
                current_items = int(lead.kind == "list_item")
            else:
                chunks.append(current)
                current = []
                current_size = 0
                current_items = 0
        current.append(fragment)
        current_size += fragment_size
        current_items += fragment_items
    if current:
        chunks.append(current)
    return chunks


def _packed_semantic_pages_v5(
    fragments: list[ContentFragmentV1],
    *,
    capacity: int,
    item_capacity: int,
) -> list[tuple[list[ContentFragmentV1], list[str], str, int]]:
    atoms = _semantic_atom_groups_v5(fragments)
    packed: list[tuple[list[ContentFragmentV1], list[str], str, int]] = []
    current: list[ContentFragmentV1] = []
    current_atom_ids: list[str] = []
    current_size = 0
    for atom in atoms:
        atom_id = stable_hash(
            [fragment.fragment_id for fragment in atom],
            prefix="atomv5_",
        )
        chunks = _split_oversized_atom_v5(
            atom,
            capacity=capacity,
            item_capacity=item_capacity,
        )
        if len(chunks) > 1:
            if current:
                packed.append((current, current_atom_ids, "", 0))
                current = []
                current_atom_ids = []
                current_size = 0
            for chunk_index, chunk in enumerate(chunks, start=1):
                packed.append((
                    chunk,
                    [f"{atom_id}:part:{chunk_index}"],
                    atom_id,
                    chunk_index,
                ))
            continue
        atom_size = sum(len(item.text) for item in atom)
        if current and (
            len(current) + len(atom) > 8
            or current_size + atom_size > capacity
            or (
                sum(item.kind == "list_item" for item in current)
                + sum(item.kind == "list_item" for item in atom)
                > item_capacity
            )
        ):
            packed.append((current, current_atom_ids, "", 0))
            current = []
            current_atom_ids = []
            current_size = 0
        current.extend(atom)
        current_atom_ids.append(atom_id)
        current_size += atom_size
    if current:
        packed.append((current, current_atom_ids, "", 0))
    return packed


def allocation_from_story_plan_v5(
    document: CourseDocument,
    fragments: list[ContentFragmentV1],
    story_plan: SlideStoryPlanV2,
) -> tuple[SlideAllocationPlanV2, dict[str, StoryBeatV2]]:
    """Compile source-bound teaching beats directly into final V5 pages."""
    catalog = {item.fragment_id: item for item in fragments}
    pages = [
        PlannedPageV2(
            page_id="slide:v5:cover",
            layout="cover",
            narrative_role="orientation",
            derived_text=[DerivedTextV1(text=document.title, purpose="navigation")],
        ),
        PlannedPageV2(
            page_id="slide:v5:agenda",
            layout="roadmap",
            narrative_role="orientation",
            derived_text=[
                DerivedTextV1(text=chapter.title, purpose="navigation")
                for chapter in story_plan.chapters[:8]
            ],
        ),
    ]
    page_beats: dict[str, StoryBeatV2] = {}
    allocated: set[str] = set()
    beat_units: list[
        tuple[
            int,
            int,
            int,
            int,
            Any,
            Any,
            StoryBeatV2,
            list[ContentFragmentV1],
        ]
    ] = []
    for chapter_index, chapter in enumerate(story_plan.chapters):
        for episode_index, episode in enumerate(chapter.episodes):
            for beat_index, beat in enumerate(episode.beats):
                beat_fragments = sorted(
                    [
                        catalog[fragment_id]
                        for fragment_id in beat.fragment_ids
                        if fragment_id in catalog and fragment_id not in allocated
                    ],
                    key=lambda item: item.ordinal,
                )
                if beat_fragments:
                    beat_units.append((
                        beat_fragments[0].ordinal,
                        chapter_index,
                        episode_index,
                        beat_index,
                        chapter,
                        episode,
                        beat,
                        beat_fragments,
                    ))
                    allocated.update(item.fragment_id for item in beat_fragments)

    completed_units: list[tuple[Any, ...]] = []
    for unit in sorted(beat_units, key=lambda item: item[:4]):
        beat_fragments = _complete_source_semantics_v5(
            unit[-1],
            all_fragments=fragments,
            reserved_ids=allocated,
        )
        allocated.update(item.fragment_id for item in beat_fragments)
        completed_units.append((*unit[:-1], beat_fragments))

    for (
        _source_ordinal,
        _chapter_index,
        _episode_index,
        _beat_index,
        chapter,
        episode,
        beat,
        beat_fragments,
    ) in completed_units:
        budget_layout = {
            "question": "question-prompt",
            "practice": "question-prompt",
            "answer": "practice-feedback",
            "process": "process-sequence",
            "formula": "formula-explanation",
            "comparison": "balanced-two-column",
        }.get(beat.renderer_layout, beat.renderer_layout)
        budget = _V5_DENSITY_BUDGETS.get(
            budget_layout,
            _V5_DEFAULT_DENSITY_BUDGET,
        )
        capacity = int(
            budget["characters"] or _V5_DEFAULT_DENSITY_BUDGET["characters"]
        )
        item_capacity = int(
            budget["items"] or _V5_DEFAULT_DENSITY_BUDGET["items"]
        )
        packed = _packed_semantic_pages_v5(
            beat_fragments,
            capacity=capacity,
            item_capacity=item_capacity,
        )
        continuation_totals = {
            token: sum(
                1
                for _chunk, _atoms, candidate, _index in packed
                if candidate == token
            )
            for _chunk, _atoms, token, _index in packed
            if token
        }
        continuation_root = ""
        for part_index, (
            chunk,
            atom_ids,
            continuation_of,
            continuation_index,
        ) in enumerate(packed, start=1):
            page_id = _stable_v5_page_id(
                chapter_id=chapter.chapter_id,
                episode_id=episode.episode_id,
                beat_id=beat.beat_id,
                fragment_ids=[item.fragment_id for item in chunk],
                part_index=part_index,
            )
            if continuation_of and not continuation_root:
                continuation_root = page_id
            derived = [DerivedTextV1(
                text=_v5_title_text(
                    beat.audience_facing_title
                    or beat.primary_claim_source.text
                ),
                purpose="page_title",
                derived_from=[item.fragment_id for item in chunk],
            )]
            if continuation_of and continuation_index > 1:
                derived.append(DerivedTextV1(
                    text=(
                        f"续页 {continuation_index}/"
                        f"{continuation_totals.get(continuation_of, continuation_index)}"
                    ),
                    purpose="continuation",
                    derived_from=[item.fragment_id for item in chunk],
                ))
            page = PlannedPageV2(
                page_id=page_id,
                layout=beat.renderer_layout,
                fragment_ids=[item.fragment_id for item in chunk],
                narrative_role=_V5_SCENE_NARRATIVE_ROLE.get(
                    episode.scene_kind,
                    "concept",
                ),
                section_id=chunk[0].section_id,
                chapter_id=chapter.chapter_id,
                episode_id=episode.episode_id,
                beat_id=beat.beat_id,
                semantic_atom_ids=atom_ids,
                continuation_of=(
                    continuation_root if continuation_index > 1 else ""
                ),
                continuation_index=continuation_index,
                derived_text=derived,
            )
            pages.append(page)
            page_beats[page_id] = beat
    leftovers = [item for item in fragments if item.fragment_id not in allocated]
    exclusions = [
        FragmentExclusionV1(
            fragment_id=item.fragment_id,
            reason=(
                "mode_concise"
                if story_plan.mode == "concise"
                else "v5_semantic_core"
            ),
        )
        for item in leftovers
    ]
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
        review={
            "story_plan_id": story_plan.plan_id,
            "compiler": "direct_v5_semantic_atoms",
        },
    )
    validate_allocation_plan(allocation, fragments)
    return allocation, page_beats


def _map_resume_slides_v5(
    resume_slides: list[dict[str, Any]] | None,
    allocation: SlideAllocationPlanV2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page_by_sources: dict[tuple[str, ...], list[PlannedPageV2]] = {}
    for page in allocation.pages:
        if page.fragment_ids:
            page_by_sources.setdefault(tuple(sorted(page.fragment_ids)), []).append(page)
    mapped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for raw in resume_slides or []:
        source_ids = tuple(sorted(
            str(item)
            for item in (raw.get("quality") or {}).get("fragment_ids") or []
        ))
        candidates = page_by_sources.get(source_ids, []) if source_ids else []
        if len(candidates) != 1:
            if source_ids:
                conflicts.append({
                    "legacy_page_id": str(raw.get("unit_id") or ""),
                    "source_fragment_ids": list(source_ids),
                    "reason": "ambiguous_source_episode_beat_mapping",
                })
            continue
        updated = deepcopy(raw)
        updated["unit_id"] = candidates[0].page_id
        updated["chapter_id"] = candidates[0].chapter_id
        updated["episode_id"] = candidates[0].episode_id
        mapped.append(updated)
    return mapped, conflicts


def _bind_question_feedback_v5(
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bind source-backed prompt/answer pages before semantic repair."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for slide in slides:
        episode_id = _clean_text(slide.get("episode_id"))
        if episode_id:
            grouped.setdefault(episode_id, []).append(slide)
    for episode_id, episode_slides in grouped.items():
        scene = _clean_text(episode_slides[0].get("scene_kind"))
        if scene not in {"practice_feedback", "worked_example"}:
            continue
        prompts = [
            slide for slide in episode_slides
            if _clean_text(slide.get("beat_role")) in {"prompt", "question"}
        ]
        answers = [
            slide for slide in episode_slides
            if _clean_text(slide.get("beat_role")) in {
                "answer",
                "feedback",
                "solution",
                "validation",
            }
        ]
        if not prompts:
            continue
        question_id = stable_hash(episode_id, prefix="question_v5_")
        answer_text = " ".join(
            _block_visible_text(block)
            for answer_slide in answers
            for block in answer_slide.get("blocks") or []
            if _block_visible_text(block)
        )
        for prompt in prompts:
            blocks = prompt.get("blocks") or []
            if not blocks:
                continue
            question = blocks[0]
            question["type"] = "exercise"
            question["metadata"] = {
                **(question.get("metadata") or {}),
                "question_id": question_id,
                "question_mode": "closed",
                "source_answer": answer_text,
            }
            prompt["quality"] = {
                **(prompt.get("quality") or {}),
                "question_mode": "closed",
                "answer_page_ids": [
                    str(answer.get("unit_id") or "") for answer in answers
                ],
            }
        for answer in answers:
            blocks = answer.get("blocks") or []
            if not blocks:
                continue
            feedback = blocks[-1]
            feedback["type"] = "callout"
            feedback["metadata"] = {
                **(feedback.get("metadata") or {}),
                "answer_for": question_id,
                "source_fragment_ids": list(
                    (answer.get("quality") or {}).get("fragment_ids") or []
                ),
            }
            if scene == "worked_example":
                answer["quality"] = {
                    **(answer.get("quality") or {}),
                    "worked_example_conclusion": _first_body_sentence(
                        _block_visible_text(feedback)
                    ),
                }
    return slides


def build_signature_v5(
    *,
    document: CourseDocument,
    course_data: dict[str, Any],
    mode: str,
    theme: str,
) -> dict[str, Any]:
    teaching_plan = course_data.get("course_teaching_plan") or {}
    knowledge = course_data.get("course_knowledge_base") or {}
    coherence = course_data.get("course_coherence_contract") or {}
    web_image_retrieval = WebImageRetrievalConfig.model_validate(
        (course_data.get("generation_request") or {}).get("web_image_retrieval")
        or {}
    )
    web_image_retrieval_signature = web_image_retrieval.model_dump(mode="json")
    web_image_retrieval_signature["enabled"] = (
        web_image_retrieval.enabled or web_image_retrieval_enabled()
    )
    fields = {
        "course_document_revision": str(document.document_revision or ""),
        "teaching_plan_revision": str(
            teaching_plan.get("revision_id")
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
        "mode": mode,
        "theme": theme,
        "compiler_version": SLIDE_DECK_V5_COMPILER_VERSION,
        "deck_outline_version": DECK_OUTLINE_V5_VERSION,
        "final_page_contract_version": FINAL_PAGE_CONTRACT_V5_VERSION,
        "semantic_compiler_version": PPT_SEMANTIC_COMPILER_VERSION,
        "domain_presentation_profile_version": (
            DOMAIN_PRESENTATION_PROFILE_VERSION
        ),
        "visual_planning_batch_version": VISUAL_PLANNING_BATCH_VERSION,
        "web_image_retrieval": web_image_retrieval_signature,
    }
    return {
        **fields,
        "signature": stable_hash(fields, prefix="slidebuildv5_"),
    }


def v5_contract_issues(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    slide_by_id = {
        str(slide.get("unit_id") or ""): slide for slide in slides
    }
    continuation_children: dict[str, list[dict[str, Any]]] = {}
    episode_slides: dict[str, list[dict[str, Any]]] = {}
    for candidate in slides:
        parent = str((candidate.get("quality") or {}).get("continuation_of") or "")
        if parent:
            continuation_children.setdefault(parent, []).append(candidate)
        episode_id = str(candidate.get("episode_id") or "")
        if episode_id:
            episode_slides.setdefault(episode_id, []).append(candidate)
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
        continuation_root = str(quality.get("continuation_of") or slide.get("unit_id") or "")
        family_slides = [
            slide_by_id.get(continuation_root, slide),
            *continuation_children.get(continuation_root, []),
        ]
        episode_id = str(slide.get("episode_id") or "")
        if episode_id:
            family_slides = list({
                str(candidate.get("unit_id") or ""): candidate
                for candidate in [
                    *family_slides,
                    *episode_slides.get(episode_id, []),
                ]
            }.values())
        body_text = " ".join(
            _clean_text(value)
            for family_slide in family_slides
            for block in family_slide.get("blocks") or []
            for value in [
                block.get("content"),
                *(block.get("items") or []),
            ]
            if _clean_text(value)
        )
        visible_items = [
            _clean_text(item)
            for family_slide in family_slides
            for block in family_slide.get("blocks") or []
            for item in block.get("items") or []
            if _clean_text(item)
        ]
        visible_items.extend(
            _clean_text(match.group(1))
            for family_slide in family_slides
            for block in family_slide.get("blocks") or []
            for line in str(block.get("content") or "").splitlines()
            if (match := _VISIBLE_BULLET_LINE.match(line)) is not None
        )
        expected_counts = [
            *_title_enumeration_counts(title),
            *_enumeration_counts(title),
        ]
        visible_items.extend(
            content
            for family_slide in family_slides
            for block in family_slide.get("blocks") or []
            if (content := _clean_text(block.get("content")))
            and not re.search(r"[：:]\s*$", content)
            and not _enumeration_counts(content)
        )
        for family_slide in family_slides:
            for block in family_slide.get("blocks") or []:
                content = _clean_text(block.get("content"))
                if not re.search(r"[：:]\s*$", content):
                    continue
                block_counts = [
                    *_enumeration_counts(content),
                    *_title_enumeration_counts(content),
                ]
                if block_counts:
                    expected_counts.append(block_counts[-1])
        expected_count = max(expected_counts, default=0)
        visible_enumeration_count = max(
            len(visible_items),
            _inline_enumeration_member_count(body_text),
        )
        if (
            not quality.get("continuation_of")
            and expected_count
            and visible_enumeration_count < expected_count
        ):
            issues.append({
                "severity": "critical",
                "code": "enumeration_cardinality_mismatch",
                "page_id": slide.get("unit_id"),
                "expected_count": expected_count,
                "visible_item_count": visible_enumeration_count,
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
    visual_planning: dict[str, Any] | None = None,
    visual_asset_manifest: list[dict[str, Any]] | None = None,
    repair_history: list[dict[str, Any]] | None = None,
    image_target: int = 0,
    render_review: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace stale V3/V4 gates with one internally consistent V5 report."""
    previous_presentation = previous_quality.get("presentation") or {}
    previous_presentation_candidates = [
        *(previous_presentation.get("blockers") or []),
        *(previous_presentation.get("issues") or []),
    ]
    previous_candidates = [
        *(previous_quality.get("blockers") or []),
        *((previous_quality.get("semantic") or {}).get("issues") or []),
        *((previous_quality.get("visual") or {}).get("issues") or []),
        *previous_presentation_candidates,
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
    diagnostics = planning_diagnostics or {}
    role_counts = diagnostics.get("semantic_role_counts") or {}
    if (
        int(diagnostics.get("balanced_composition_unit_count") or 0) > 0
        and not any(
            int(role_counts.get(role) or 0) > 0
            for role in ("example", "application", "transfer")
        )
    ):
        planning_issues.append({
            "severity": "major",
            "code": "course_input_example_missing",
            "target": "deck",
            "responsibility": "course_generation",
            "message": "均衡型课程输入中缺少有来源依据的示例或应用单元。",
            "suggestion": "请补生成对应课程小节的示例或应用模块；PPT不会编造专业案例。",
        })
    unmapped_count = int(
        diagnostics.get("knowledge_binding_unmapped_count") or 0
    )
    if unmapped_count:
        planning_issues.append({
            "severity": "major",
            "code": "course_input_knowledge_unmapped",
            "target": "deck",
            "responsibility": "course_generation",
            "count": unmapped_count,
            "message": f"{unmapped_count} 个结构化教学单元尚未绑定正式知识 ID。",
            "suggestion": "请在下次重建前修复课程块知识绑定；当前版式安全页面仍可发布。",
        })
    binding_coverage = float(
        diagnostics.get("question_answer_binding_coverage", 1.0)
    )
    if binding_coverage < 1.0:
        planning_issues.append({
            "severity": "major",
            "code": "course_input_question_answer_gap",
            "target": "deck",
            "responsibility": "course_generation",
            "coverage": binding_coverage,
            "message": "部分来源问题尚未绑定对应反馈单元。",
            "suggestion": "请调用受约束的答案生成器补全缺失答案，或修复课程反馈模块。",
        })

    visual_planning_details = deepcopy(visual_planning or {})
    visual_fallback_reason = str(
        visual_planning_details.get("fallback_reason") or ""
    )
    visual_planning_issues: list[dict[str, Any]] = []
    if visual_fallback_reason == "partial_ai_visual_plan":
        visual_planning_issues.append({
            "severity": "major",
            "code": "ai_visual_planner_partial_fallback",
            "target": "deck",
            "message": "部分页面的 AI 视觉规划失败，已使用确定性视觉方案。",
            "suggestion": "可重试失败的视觉批次；当前页面仍保持来源绑定。",
        })
    elif visual_fallback_reason in {
        "invalid_or_failed_ai_visual_plan",
        "no_ai_visual_planner",
    }:
        visual_planning_issues.append({
            "severity": "major",
            "code": "ai_visual_planner_fallback",
            "target": "deck",
            "message": "AI 视觉规划不可用，整套课件使用了确定性视觉方案。",
            "suggestion": "检查视觉规划模型后重试生成。",
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

    presentation_identities = {
        _v5_issue_identity(issue)
        for issue in previous_presentation_candidates
        if str(issue.get("code") or "") not in _V5_REPLACED_V4_QUALITY_CODES
    }
    for issue in retained:
        if _v5_issue_identity(issue) in presentation_identities:
            issue.setdefault("dimension", "layout_export")
    for issue in planning_issues:
        issue.setdefault("dimension", "source_integrity")
    for issue in visual_planning_issues:
        issue.setdefault("dimension", "visual_effectiveness")

    report = build_slide_deck_quality_v5(
        slides,
        planner=planner,
        fallback_reason=fallback_reason,
        planning_diagnostics=planning_diagnostics,
        render_review=render_review,
        visual_asset_manifest=visual_asset_manifest,
        repair_history=repair_history,
        image_target=image_target,
        legacy_quality=previous_quality,
        extra_issues=[
            *retained,
            *final_slide_issues,
            *v5_contract_issues(slides),
            *planning_issues,
            *visual_planning_issues,
        ],
        coverage_report=coverage_report,
    )
    semantic_issues = [
        issue for issue in report["issues"]
        if str(issue.get("dimension") or "") in {
            "source_integrity",
            "teaching_closure",
            "pagination_narrative",
        }
    ]
    presentation_issues = [
        issue for issue in report["issues"]
        if str(issue.get("dimension") or "") == "layout_export"
    ]
    visual_issues = [
        issue for issue in report["issues"]
        if str(issue.get("dimension") or "") in {
            "visual_effectiveness",
            "attribution_accessibility",
        }
    ]
    report["semantic"] = {
        "passed": not any(item.get("severity") == "critical" for item in semantic_issues),
        "issues": semantic_issues,
    }
    report["visual"] = {
        "passed": not any(item.get("severity") == "critical" for item in visual_issues),
        "issues": visual_issues,
    }
    presentation_blockers = [
        issue for issue in presentation_issues
        if issue.get("severity") == "critical"
    ]
    report["presentation"] = {
        "passed": not presentation_blockers,
        "issues": presentation_issues,
        "blockers": presentation_blockers,
    }
    report["planning"] = {
        **report.get("planning", {}),
        "passed": not any(
            issue.get("severity") == "critical" for issue in planning_issues
        ),
        "issues": planning_issues,
    }
    report["visual_planning"] = {
        **visual_planning_details,
        "degraded": bool(visual_planning_issues),
        "passed": not any(
            issue.get("severity") == "critical" for issue in visual_planning_issues
        ),
        "issues": visual_planning_issues,
    }
    report["v5_composition"] = {
        "passed": not v5_contract_issues(slides),
        "issues": v5_contract_issues(slides),
    }
    return report


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
    configured_retrieval = WebImageRetrievalConfig.model_validate(
        (course_data.get("generation_request") or {}).get("web_image_retrieval") or {}
    )
    retrieval_enabled = configured_retrieval.enabled or web_image_retrieval_enabled()
    has_source_bound_beats = any(
        beat.fragment_ids
        for chapter in story.chapters
        for episode in chapter.episodes
        for beat in episode.beats
    )
    resolved_story = (
        story
        if has_source_bound_beats
        else compact_story_plan_v5(document, story, source_fragments)
    )
    resolved_allocation, page_beats = allocation_from_story_plan_v5(
        document,
        source_fragments,
        resolved_story,
    )
    resolved_page_ids = [page.page_id for page in resolved_allocation.pages]
    supplied_visual_page_ids = [
        str(page.page_id)
        for page in getattr(visual_plan, "pages", [])
    ] if visual_plan is not None else []
    if visual_plan is None or supplied_visual_page_ids != resolved_page_ids:
        visual_plan = deterministic_visual_plan(
            document,
            resolved_allocation,
            source_fragments,
        )
        visual_plan.deck_brief["fallback_reason"] = (
            "v5_final_page_ids_visual_plan_rebuilt"
        )
    planned_visual_search_requests: dict[str, dict[str, Any]] = {}
    raw_visual_search_requests = (
        (getattr(visual_plan, "deck_brief", {}) or {}).get(
            "visual_search_requests"
        )
        or {}
    )
    if not isinstance(raw_visual_search_requests, dict):
        raw_visual_search_requests = {}
    for page_id, raw_request in raw_visual_search_requests.items():
        try:
            request = VisualSearchRequestV5.model_validate(raw_request)
        except ValueError:
            continue
        if request.page_id == str(page_id) and request.page_id in resolved_page_ids:
            planned_visual_search_requests[request.page_id] = request.model_dump(
                mode="json"
            )
    mapped_resume, override_conflicts = _map_resume_slides_v5(
        resume_slides,
        resolved_allocation,
    )
    if progress_callback:
        progress_callback({
            "event": "story_plan",
            "progress": 8,
            "stage": "story_plan",
            "story_plan": resolved_story.model_dump(mode="json"),
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
        resume_slides=mapped_resume,
        asset_repository=asset_repository,
        allow_generated_illustrations=False if retrieval_enabled else None,
    )
    continuation_totals = {
        page.page_id: max(
            [
                int(candidate.continuation_index or 0)
                for candidate in resolved_allocation.pages
                if candidate.continuation_of == page.page_id
            ]
            or [0]
        )
        for page in resolved_allocation.pages
    }
    episode_by_beat = {
        beat.beat_id: (chapter.chapter_id, episode.episode_id, episode)
        for chapter in resolved_story.chapters
        for episode in chapter.episodes
        for beat in episode.beats
    }
    page_catalog = {page.page_id: page for page in resolved_allocation.pages}
    for slide in content.get("slides") or []:
        page_id = str(slide.get("unit_id") or "")
        beat = page_beats.get(page_id)
        page = page_catalog.get(page_id)
        if page is not None:
            continuation_total = (
                continuation_totals.get(page.continuation_of, 0)
                if page.continuation_of
                else continuation_totals.get(page.page_id, 0)
            )
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "semantic_atom_ids": list(page.semantic_atom_ids),
                "continuation_of": page.continuation_of,
                "continuation_index": page.continuation_index,
                "continuation_total": continuation_total,
                "fragment_ids": list(page.fragment_ids),
            }
        if beat is None:
            continue
        chapter_id, episode_id, episode = episode_by_beat[beat.beat_id]
        audience_title = _clean_text(beat.audience_facing_title)
        audience_summary = _clean_text(beat.audience_facing_summary)
        title = audience_title or slide.get("title") or beat.primary_claim_source.text
        if page is not None and page.continuation_of:
            total = max(
                int(page.continuation_index or 0),
                int(continuation_totals.get(page.continuation_of, 0) or 0),
            )
            suffix = f"（续{page.continuation_index}/{total}）"
            base_title = re.sub(
                r"\s*[（(]+\s*续(?:页)?(?:\s*\d+/\d+)?\s*[）)]+\s*$",
                "",
                _clean_text(title),
            )
            concise_base = base_title[:max(8, 18 - len(suffix))].rstrip("（(")
            title = f"{concise_base}{suffix}"
        slide.update({
            "chapter_id": chapter_id,
            "episode_id": episode_id,
            "scene_kind": episode.scene_kind,
            "beat_role": beat.beat_role,
            "teaching_job": beat.teaching_job,
            "title": title,
            "key_message": audience_summary or slide.get("key_message") or "",
            "takeaway": audience_summary or beat.primary_claim_source.text,
            "primary_claim_source": beat.primary_claim_source.model_dump(mode="json"),
            "transition_from": beat.transition_from,
            "knowledge_refs": beat.knowledge_refs,
            "prerequisite_refs": beat.prerequisite_refs,
            "mastery_criterion_refs": beat.mastery_criterion_refs,
            "layout_selection_reason": beat.layout_selection_reason,
        })
    outline = compile_deck_outline_v5(document, resolved_story)
    slides = _materialize_v5_structure(
        list(content.get("slides") or []),
        outline,
    )
    slides = _bind_question_feedback_v5(slides)
    slides = split_mixed_intent_slides_v5(slides)
    for slide in slides:
        page_id = str(slide.get("unit_id") or "")
        if page_id in planned_visual_search_requests:
            slide["quality"] = {
                **(slide.get("quality") or {}),
                "visual_search_request": deepcopy(
                    planned_visual_search_requests[page_id]
                ),
            }
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
    slides = _split_practice_feedback_capacity_v5(slides)
    slides = [
        _normalize_concept_definition_slide_v5(slide)
        for slide in slides
    ]
    slides = repair_final_page_contracts_v5(slides)
    slides = _assign_heading_modes_v5(slides)
    previous_quality = deepcopy(content.get("quality_report") or {})
    slides = [apply_page_contract_v5(slide) for slide in slides]
    slides, repair_history = repair_semantic_slides_v5(slides, max_rounds=2)
    slides = [apply_page_contract_v5(slide) for slide in slides]
    slides = _assign_heading_modes_v5(slides)
    if progress_callback:
        progress_callback({
            "event": "semantic_repair",
            "progress": 97,
            "stage": "semantic_repair",
            "repair_attempts": max(
                (int(item.get("round") or 0) for item in repair_history),
                default=0,
            ),
            "repair_history": deepcopy(repair_history),
        })
    visually_eligible = [
        slide for slide in slides
        if str(slide.get("scene_kind") or "") in {
            "concept",
            "reasoning",
            "method",
            "process",
            "comparison",
            "worked_example",
            "application",
            "evidence",
        }
    ]
    image_target = (
        min(configured_retrieval.target_count, len(visually_eligible))
        if configured_retrieval.target_count is not None
        else compute_image_target_v5(
            chapter_count=len(resolved_story.chapters),
            main_slide_count=sum(
                1 for slide in slides
                if slide.get("layout") != "appendix"
            ),
            visually_eligible_page_count=len(visually_eligible),
        )
    ) if retrieval_enabled else 0
    retrieved_manifest: list[dict[str, Any]] = []
    generated_fallback_manifest: list[dict[str, Any]] = []
    if retrieval_enabled and image_target:
        slides, retrieved_manifest = enrich_slides_with_web_images_v5(
            slides,
            repository=asset_repository or slide_asset_repository,
            course_id=document.course_id,
            target_count=int(image_target),
            progress_callback=progress_callback,
        )
        slides = [apply_page_contract_v5(slide) for slide in slides]
        existing_image_count = sum(
            1
            for asset in [
                *list(content.get("visual_asset_manifest") or []),
                *retrieved_manifest,
            ]
            if asset.get("kind") in {
                "source_image",
                "retrieved_image",
                "generated_illustration",
            }
        )
        slides, generated_fallback_manifest = enrich_slides_with_generated_images_v5(
            slides,
            repository=asset_repository or slide_asset_repository,
            course_id=document.course_id,
            maximum_count=min(6, max(0, int(image_target) - existing_image_count)),
            progress_callback=progress_callback,
        )
        slides = [apply_page_contract_v5(slide) for slide in slides]
    visual_asset_manifest = [
        *list(content.get("visual_asset_manifest") or []),
        *retrieved_manifest,
        *generated_fallback_manifest,
    ]
    content.update({
        "schema_version": SLIDE_DECK_V5_SCHEMA,
        "slides": slides,
        "visual_asset_manifest": visual_asset_manifest,
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
        "deck_outline": outline.model_dump(mode="json"),
        "override_conflicts": override_conflicts,
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
    visual_plan_payload = (
        visual_plan.model_dump(mode="json")
        if hasattr(visual_plan, "model_dump")
        else deepcopy(visual_plan)
        if isinstance(visual_plan, dict)
        else deepcopy(content.get("visual_plan") or {})
    )
    visual_brief = dict((visual_plan_payload or {}).get("deck_brief") or {})
    visual_policy_version = str(
        (visual_plan_payload or {}).get("policy_version") or ""
    )
    content["generation_provenance"] = {
        "schema_version": "slide_generation_provenance_v1",
        "compiler_version": SLIDE_DECK_V5_COMPILER_VERSION,
        "story": {
            "planner": str(story.planner or "deterministic_fallback"),
            "fallback_reason": str(story.fallback_reason or ""),
            "prompt_contract_version": "slide_story_chapter_directives_v2",
        },
        "visual": {
            "planner": str(visual_brief.get("planner") or "deterministic_fallback"),
            "fallback_reason": str(visual_brief.get("fallback_reason") or ""),
            "prompt_contract_version": "slide_visual_plan_v1",
            "policy_version": visual_policy_version,
        },
    }
    content["quality_report"] = finalize_v5_quality_report(
        previous_quality=previous_quality,
        slides=slides,
        planner=outline.planner,
        fallback_reason=outline.fallback_reason,
        planning_diagnostics=outline.planning_diagnostics,
        visual_planning=visual_brief,
        visual_asset_manifest=visual_asset_manifest,
        repair_history=repair_history,
        image_target=int(image_target or 0),
        coverage_report=dict(content.get("coverage_report") or {}),
    )
    content["quality_summary"] = {
        "passed": content["quality_report"]["passed"],
        "score": content["quality_report"]["score"],
        **summarize_v5_slide_counts(slides),
        "image_target_met": content["quality_report"]["image_target_met"],
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
    del course_data
    outline = content.get("deck_outline") or {}
    visual_brief = dict(
        (content.get("visual_plan") or {}).get("deck_brief") or {}
    )
    slides = list(content.get("slides") or [])
    previous = content.get("quality_report") or {}
    return finalize_v5_quality_report(
        previous_quality=previous,
        slides=slides,
        planner=str(outline.get("planner") or ""),
        fallback_reason=str(outline.get("fallback_reason") or ""),
        planning_diagnostics=dict(
            outline.get("planning_diagnostics") or {}
        ),
        visual_planning=visual_brief,
        render_review=dict(content.get("render_review") or {}),
        visual_asset_manifest=list(content.get("visual_asset_manifest") or []),
        repair_history=list(previous.get("repair_history") or []),
        image_target=int((previous.get("metrics") or {}).get("image_target") or 0),
        coverage_report=dict(content.get("coverage_report") or {}),
    )
