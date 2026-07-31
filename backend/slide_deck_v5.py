"""Deck-level narrative and final page contracts for slide_deck_v5."""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from course_document import CourseDocument, stable_hash
from slide_deck_v4 import (
    SLIDE_DECK_V4_SCHEMA,
    build_signature_v4,
    compile_slide_deck_v4,
    validate_slide_deck_v4,
)
from slide_story_plan import SlideStoryPlanV2

SLIDE_DECK_V5_SCHEMA = "slide_deck_v5"
SLIDE_DECK_V5_COMPILER_VERSION = "course_logic_slide_compiler_v5.0"
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
_T = TypeVar("_T")


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
    normalized = re.sub(r"[\s:：/\\_.-]+", "", _clean_text(value)).lower()
    return normalized not in _GENERIC_TITLES and bool(normalized)


def _first_body_sentence(value: str) -> str:
    return re.split(r"[。！？!?\n]", _clean_text(value), maxsplit=1)[0].strip()


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
) -> str:
    """Compile one audience-facing title without promoting takeaway at render time."""
    explicit = _clean_text(explicit_title)
    claim = _clean_text(primary_claim)
    first_body = _first_body_sentence(body_text)
    if _meaningful_title(explicit):
        if explicit not in {claim, first_body} or len(explicit) <= 24:
            return _bounded_title(explicit)
        return _structured_claim_title(explicit)
    if claim:
        return _structured_claim_title(claim)
    if first_body:
        return _structured_claim_title(first_body)
    return "课程内容"


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
        body_text = "\n".join(
            [
                _clean_text(block.get("content"))
                for block in updated.get("blocks") or []
                if _clean_text(block.get("content"))
            ]
        )
        updated["title"] = compile_page_title_v5(
            explicit_title=str(updated.get("title") or ""),
            primary_claim=str(
                (updated.get("primary_claim_source") or {}).get("text")
                or updated.get("takeaway")
                or ""
            ),
            body_text=body_text,
        )
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
        entry = _chapter_entry_slide(chapter)
        if entry["unit_id"] not in used_units:
            result.append(entry)
            used_units.add(entry["unit_id"])
        result.extend(chapter_slides)
        used_units.update(str(slide.get("unit_id") or "") for slide in chapter_slides)
        if not any(
            str(slide.get("scene_kind") or "") == "chapter_recap"
            for slide in chapter_slides
        ):
            recap = _chapter_recap_slide(chapter, chapter_slides)
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


def _v5_contract_issues(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if requested in {"two-column", "positive-negative"} and resolved == "editorial-body":
            continue
    return issues


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
    slides = [apply_page_contract_v5(slide) for slide in slides]
    issues = _v5_contract_issues(slides)
    previous_quality = deepcopy(content.get("quality_report") or {})
    previous_blockers = list(previous_quality.get("blockers") or [])
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
    content["quality_report"] = {
        **previous_quality,
        "passed": bool(previous_quality.get("passed")) and not issues,
        "blockers": [*previous_blockers, *issues],
        "v5_composition": {
            "passed": not issues,
            "issues": issues,
        },
    }
    content["quality_summary"] = {
        **(content.get("quality_summary") or {}),
        "passed": content["quality_report"]["passed"],
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
    issues = _v5_contract_issues(list(content.get("slides") or []))
    blockers = [*(base.get("blockers") or []), *issues]
    return {
        **base,
        "passed": bool(base.get("passed")) and not issues,
        "blockers": blockers,
        "v5_composition": {
            "passed": not issues,
            "issues": issues,
        },
    }
