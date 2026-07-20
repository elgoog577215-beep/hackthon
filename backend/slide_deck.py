"""Structured, same-source slide planning and deterministic quality gates."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash

SLIDE_DECK_SCHEMA = "slide_deck_v2"
SLIDE_DECK_COMPILER_VERSION = "structured_slide_compiler_v9"
SLIDES_PER_SECTION_MAX = 5
DEMO_PLAN_SECTION_THRESHOLD = 4
DEMO_PLAN_DEFAULT_SLIDES = 15

SlideBlockType = Literal[
    "statement",
    "bullets",
    "code",
    "comparison",
    "process",
    "exercise",
    "misconception",
    "callout",
]
SlideLayout = Literal[
    "cover",
    "roadmap",
    "chapter",
    "objective",
    "concept",
    "comparison",
    "process",
    "code",
    "misconception",
    "practice",
    "recap",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideBlockSpec(_StrictModel):
    block_id: str
    type: SlideBlockType
    title: str = ""
    content: str = ""
    items: list[str] = Field(default_factory=list, max_length=8)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SlideSpec(_StrictModel):
    unit_id: str
    position: int = Field(ge=0)
    layout: SlideLayout
    slide_purpose: str
    eyebrow: str = ""
    title: str
    subtitle: str = ""
    key_message: str = ""
    blocks: list[SlideBlockSpec] = Field(default_factory=list, max_length=6)
    speaker_notes: str = ""
    section_id: str | None = None
    source_section_ids: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    learning_objective_ids: list[str] = Field(default_factory=list)
    practice_task_ids: list[str] = Field(default_factory=list)
    practice_source_revisions: dict[str, str] = Field(default_factory=dict)
    knowledge_refs: list[str] = Field(default_factory=list)
    ability_refs: list[str] = Field(default_factory=list)
    misconception_refs: list[str] = Field(default_factory=list)
    mastery_refs: list[str] = Field(default_factory=list)
    knowledge_labels: list[str] = Field(default_factory=list)
    ability_labels: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)


class PlannedSlideV1(_StrictModel):
    slide_id: str
    layout: Literal["cover", "roadmap", "concept", "practice", "recap"]
    slide_purpose: str
    section_id: str | None = None
    source_section_ids: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)


class SlideDeckPlanV1(_StrictModel):
    schema_version: Literal["slide_deck_plan_v1"] = "slide_deck_plan_v1"
    title: str
    target_slide_count: int = Field(ge=12, le=18)
    slides: list[PlannedSlideV1] = Field(min_length=12, max_length=18)
    planner: Literal["ai", "deterministic_fallback"] = "ai"
    fallback_reason: str = ""

    @model_validator(mode="after")
    def validate_plan(self) -> SlideDeckPlanV1:
        if len(self.slides) != self.target_slide_count:
            raise ValueError("Plan target must match the number of slides")
        slide_ids = [slide.slide_id for slide in self.slides]
        if len(slide_ids) != len(set(slide_ids)):
            raise ValueError("Planned slide IDs must be unique")
        if [slide.layout for slide in self.slides[:2]] != ["cover", "roadmap"]:
            raise ValueError("Plan must start with cover and roadmap slides")
        if self.slides[-1].layout != "recap":
            raise ValueError("Plan must end with a recap slide")
        for slide in self.slides[2:-1]:
            if not slide.section_id or not slide.source_section_ids or not slide.source_block_ids:
                raise ValueError("Every teaching slide must retain section and block sources")
        return self


class SlideDeckContent(_StrictModel):
    schema_version: Literal["slide_deck_v2"] = SLIDE_DECK_SCHEMA
    title: str
    theme: str = "qingfeng-classroom"
    aspect_ratio: Literal["16:9"] = "16:9"
    slides: list[SlideSpec]
    presentation_overrides: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    override_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_slide_order(self) -> SlideDeckContent:
        unit_ids = [slide.unit_id for slide in self.slides]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Slide unit IDs must be unique")
        for index, slide in enumerate(self.slides):
            slide.position = index
        return self


LAYOUT_CAPACITY: dict[str, dict[str, int]] = {
    "cover": {"blocks": 1, "characters": 420, "items": 0},
    "roadmap": {"blocks": 1, "characters": 720, "items": 8},
    "chapter": {"blocks": 1, "characters": 480, "items": 0},
    "objective": {"blocks": 3, "characters": 520, "items": 4},
    "concept": {"blocks": 3, "characters": 620, "items": 9},
    "comparison": {"blocks": 1, "characters": 1100, "items": 0},
    "process": {"blocks": 1, "characters": 520, "items": 5},
    "code": {"blocks": 2, "characters": 1700, "items": 4},
    "misconception": {"blocks": 1, "characters": 620, "items": 4},
    "practice": {"blocks": 2, "characters": 1000, "items": 8},
    "recap": {"blocks": 3, "characters": 720, "items": 8},
}


def compile_slide_deck(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    presentation_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
    deck_plan: SlideDeckPlanV1 | dict[str, Any] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile a course into a teachable page sequence instead of copied prose."""
    sections = sorted(document.sections, key=lambda item: item.position)
    blocks_by_section = _blocks_by_section(document)
    section_by_id = {section.section_id: section for section in sections}
    learning_sections = [
        section for section in sections
        if any(block.status != "retired" for block in blocks_by_section.get(section.section_id, []))
    ]
    chapter_sections = [section for section in sections if section.level == 1]
    knowledge_index = _KnowledgeIndex(course_data)
    resolved_plan = (
        _resolve_demo_plan(document, course_data, deck_plan)
        if len(learning_sections) >= DEMO_PLAN_SECTION_THRESHOLD
        else None
    )
    estimated_slide_count = len(resolved_plan.slides) if resolved_plan else _estimated_slide_count(learning_sections)
    slides: list[SlideSpec] = []
    resumed_by_unit_id: dict[str, SlideSpec] = {}
    for raw_slide in resume_slides or []:
        try:
            saved_slide = SlideSpec.model_validate(raw_slide)
        except (TypeError, ValueError):
            continue
        resumed_by_unit_id[saved_slide.unit_id] = saved_slide

    def append(slide: SlideSpec) -> None:
        resumed = resumed_by_unit_id.get(slide.unit_id)
        if resumed is not None:
            # A page emitted before pause/restart is already a complete compiler
            # unit.  Reuse it without another slide_upsert event so callers can
            # distinguish resumed pages from newly compiled pages.
            resumed.position = len(slides)
            slides.append(resumed)
            return
        slide.position = len(slides)
        slide.quality = slide_quality(slide)
        slides.append(slide)
        if progress_callback:
            progress_callback({
                "event": "slide_upsert",
                "progress": min(94, 6 + round((len(slides) / max(1, estimated_slide_count)) * 88)),
                "slide": slide.model_dump(mode="json"),
            })

    def append_resumed(unit_id: str) -> bool:
        """Append a validated savepoint page without materializing it again."""
        resumed = resumed_by_unit_id.get(unit_id)
        if resumed is None:
            return False
        resumed.position = len(slides)
        slides.append(resumed)
        return True

    def append_or_resume(unit_id: str, factory: Callable[[], SlideSpec]) -> None:
        if not append_resumed(unit_id):
            append(factory())

    if progress_callback:
        progress_callback({
            "event": "deck_plan",
            "progress": 4,
            "title": document.title,
            "section_count": len(learning_sections),
            "estimated_slide_count": estimated_slide_count,
            "strategy": "demo_plan_v1" if resolved_plan else "plan_then_fill",
            "planner": resolved_plan.planner if resolved_plan else None,
            "fallback_reason": resolved_plan.fallback_reason if resolved_plan else "",
        })

    append_or_resume("slide:title", lambda: SlideSpec(
        unit_id="slide:title",
        position=0,
        layout="cover",
        slide_purpose="orientation",
        eyebrow="课程演示",
        title=document.title,
        subtitle=_course_subtitle(learning_sections, chapter_sections),
        key_message="围绕学习目标、知识关系与可验证任务组织课程，而不是复制正文。",
        blocks=[SlideBlockSpec(
            block_id="slide:title:promise",
            type="callout",
            title="学习承诺",
            content=_course_learning_promise(learning_sections),
        )],
        speaker_notes="先说明课程解决什么问题、学习者最终能够完成什么任务。",
        source_keys=_unique([
            "course_title",
            *[f"section_structure:{section.section_id}" for section in sections],
            *[
                f"objective:{section.objective_id}"
                for section in learning_sections
                if section.objective_id
            ],
        ]),
    ))

    append_or_resume("slide:roadmap", lambda: SlideSpec(
        unit_id="slide:roadmap",
        position=0,
        layout="roadmap",
        slide_purpose="course_route",
        eyebrow="全课路线",
        title="先建立全局，再进入每个问题",
        key_message="课程按概念建构、方法推演、应用与检查逐步推进。",
        blocks=[SlideBlockSpec(
            block_id="slide:roadmap:chapters",
            type="process",
            items=[_concise_point(_strip_chapter_prefix(section.title), 42) for section in chapter_sections[:8]],
        )],
        speaker_notes="用章节路线帮助学习者定位当前内容在全课中的作用。",
        source_keys=[f"section_structure:{section.section_id}" for section in chapter_sections[:8]],
    ))

    if resolved_plan:
        for planned_slide in resolved_plan.slides[2:-1]:
            if append_resumed(planned_slide.slide_id):
                continue
            section = section_by_id[planned_slide.section_id or ""]
            blocks = [
                block for block in blocks_by_section.get(section.section_id, [])
                if block.status != "retired" and block.block_id in planned_slide.source_block_ids
            ]
            context = _merge_block_knowledge(
                knowledge_index.for_section(section.section_id, section),
                blocks,
            )
            append(_materialize_planned_slide(planned_slide, section, blocks, context, course_data))
    else:
        last_chapter_id = ""
        for section in learning_sections:
            blocks = [block for block in blocks_by_section.get(section.section_id, []) if block.status != "retired"]
            if not blocks:
                continue
            chapter = section_by_id.get(section.parent_section_id or "")
            if chapter and chapter.section_id != last_chapter_id:
                if not append_resumed(f"slide:chapter:{chapter.section_id}"):
                    append(_chapter_slide(chapter, section))
                last_chapter_id = chapter.section_id

            context = _merge_block_knowledge(
                knowledge_index.for_section(section.section_id, section),
                blocks,
            )
            if not append_resumed(f"slide:{section.section_id}"):
                append(_objective_slide(section, blocks, context))
            if len(blocks) <= 2:
                if not append_resumed(f"slide:{section.section_id}:content:1"):
                    append(_compact_section_slide(section, blocks, context))
            else:
                selected = _select_instructional_blocks(blocks)
                for selected_index, block in enumerate(selected[: SLIDES_PER_SECTION_MAX - 2]):
                    unit_id = f"slide:{section.section_id}:{block.role}:{selected_index + 1}"
                    if not append_resumed(unit_id):
                        append(_slide_for_block(section, block, context, selected_index))

            if not append_resumed(f"slide:{section.section_id}:check"):
                assessment = _assessment_slide(section, blocks, context, course_data)
                if assessment:
                    append(assessment)

    if not append_resumed("slide:recap"):
        append(_recap_slide(document, learning_sections, knowledge_index))

    content = SlideDeckContent(title=document.title, slides=slides)
    if presentation_overrides:
        content = apply_presentation_overrides(content, presentation_overrides)
    quality = validate_slide_deck(content.model_dump(mode="json"), course_data=course_data)
    content.quality_report = deepcopy(quality)
    content.quality_summary = {
        "passed": quality["passed"],
        "score": quality["score"],
        "semantic_issue_count": len(quality["semantic"]["issues"]),
        "visual_issue_count": len(quality["visual"]["issues"]),
    }
    if progress_callback:
        progress_callback({"event": "slide_quality", "progress": 97, "quality": quality})
    return content.model_dump(mode="json")


async def plan_slide_deck(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    ai_planner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None,
    timeout_seconds: float = 8.0,
) -> SlideDeckPlanV1:
    """Return a validated AI plan or a network-free deterministic fallback."""
    if ai_planner is None:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="no_ai_planner")

    request = {
        "schema_version": "slide_deck_plan_request_v1",
        "title": document.title,
        "target_slide_count": DEMO_PLAN_DEFAULT_SLIDES,
        "sections": [
            {
                "section_id": section.section_id,
                "title": section.title,
                "learning_objective": section.learning_objective,
                "source_block_ids": [
                    block.block_id for block in document.blocks
                    if block.section_id == section.section_id and block.status != "retired"
                ],
            }
            for section in sorted(document.sections, key=lambda item: item.position)
        ],
    }

    async def invoke() -> Any:
        if inspect.iscoroutinefunction(ai_planner):
            return await ai_planner(request)
        result = await asyncio.to_thread(ai_planner, request)
        return await result if inspect.isawaitable(result) else result

    try:
        raw_plan = await asyncio.wait_for(invoke(), timeout=timeout_seconds)
    except TimeoutError:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="timeout")
    except Exception:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="planner_error")

    try:
        plan = SlideDeckPlanV1.model_validate(raw_plan)
        plan.planner = "ai"
        plan.fallback_reason = ""
        _validate_plan_sources(plan, document)
        return plan
    except Exception:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="invalid_plan")


def _resolve_demo_plan(
    document: CourseDocument,
    course_data: dict[str, Any],
    plan: SlideDeckPlanV1 | dict[str, Any] | None,
) -> SlideDeckPlanV1:
    if plan is None:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="no_ai_planner")
    try:
        validated = SlideDeckPlanV1.model_validate(plan)
        _validate_plan_sources(validated, document)
        return validated
    except Exception:
        return _deterministic_slide_deck_plan(document, course_data, fallback_reason="invalid_plan")


def _deterministic_slide_deck_plan(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    fallback_reason: str,
) -> SlideDeckPlanV1:
    blocks_by_section = _blocks_by_section(document)
    sections = [
        section for section in sorted(document.sections, key=lambda item: item.position)
        if any(block.status != "retired" for block in blocks_by_section.get(section.section_id, []))
    ]
    if not sections:
        raise ValueError("Cannot plan a slide deck without active course sections")

    target_slide_count = DEMO_PLAN_DEFAULT_SLIDES if len(sections) >= 12 else 12
    teaching_count = target_slide_count - 3
    if len(sections) >= teaching_count:
        indices = [
            round(index * (len(sections) - 1) / max(1, teaching_count - 1))
            for index in range(teaching_count)
        ]
    else:
        indices = [index % len(sections) for index in range(teaching_count)]
    selected_sections = [sections[index] for index in indices]

    question_sections = {
        str(item.get("node_id") or "")
        for item in _asset_records(course_data, "questions")
        if item.get("node_id")
    }
    practice_indices = [
        index for index, section in enumerate(selected_sections)
        if section.section_id in question_sections
    ][:2]
    if not practice_indices:
        practice_indices = [teaching_count - 1]

    planned_slides = [
        PlannedSlideV1(
            slide_id="slide:title",
            layout="cover",
            slide_purpose="orientation",
        ),
        PlannedSlideV1(
            slide_id="slide:roadmap",
            layout="roadmap",
            slide_purpose="course_route",
        ),
    ]
    for index, section in enumerate(selected_sections):
        source_blocks = [
            block.block_id for block in blocks_by_section.get(section.section_id, [])
            if block.status != "retired"
        ]
        is_practice = index in practice_indices
        planned_slides.append(PlannedSlideV1(
            slide_id=f"slide:demo:{index + 1}:{section.section_id}",
            layout="practice" if is_practice else "concept",
            slide_purpose="mastery_check" if is_practice else "core_concept",
            section_id=section.section_id,
            source_section_ids=[section.section_id],
            source_block_ids=source_blocks,
        ))
    planned_slides.append(PlannedSlideV1(
        slide_id="slide:recap",
        layout="recap",
        slide_purpose="course_recap",
    ))
    return SlideDeckPlanV1(
        title=document.title,
        target_slide_count=target_slide_count,
        slides=planned_slides,
        planner="deterministic_fallback",
        fallback_reason=fallback_reason,
    )


def _validate_plan_sources(plan: SlideDeckPlanV1, document: CourseDocument) -> None:
    section_ids = {section.section_id for section in document.sections}
    block_sections = {block.block_id: block.section_id for block in document.blocks if block.status != "retired"}
    for slide in plan.slides[2:-1]:
        if slide.section_id not in section_ids or slide.source_section_ids != [slide.section_id]:
            raise ValueError("Plan references an unknown or inconsistent section")
        if any(block_sections.get(block_id) != slide.section_id for block_id in slide.source_block_ids):
            raise ValueError("Plan references an unknown or cross-section block")


def _materialize_planned_slide(
    planned: PlannedSlideV1,
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
    course_data: dict[str, Any],
) -> SlideSpec:
    source_notes = _trim(
        "\n\n".join(
            _plain_text(_block_markdown(block))
            for block in blocks
            if _block_markdown(block).strip()
        ),
        1800,
    )
    if planned.layout == "practice":
        slide = _assessment_slide(section, blocks, context, course_data)
        visible_points = sum(len(block.items) if block.items else bool(block.content.strip()) for block in slide.blocks)
        if visible_points < 3 and len(slide.blocks) < 3:
            slide.blocks.append(SlideBlockSpec(
                block_id=f"{planned.slide_id}:checks",
                type="bullets",
                title="作答检查",
                items=["先独立作答", "说明判断依据", "给出边界或反例"],
            ))
        slide.blocks = _cap_demo_practice_points(_fit_blocks_for_layout("practice", slide.blocks))
        slide.unit_id = planned.slide_id
        slide.source_section_ids = list(planned.source_section_ids)
        slide.source_block_ids = list(planned.source_block_ids)
        slide.speaker_notes = _trim(
            f"{slide.speaker_notes}\n\n"
            f"练习对应目标：{section.learning_objective or section.title}。\n\n{source_notes}\n\n"
            "先让学习者独立作答，再按检查项追问理由；页面不展示完整答案。",
            1800,
        )
        return slide

    points = _demo_section_points(section, blocks, context)
    primary_role = next((block.role for block in blocks if block.role != "objective"), "concept")
    return SlideSpec(
        unit_id=planned.slide_id,
        position=0,
        layout="concept",
        slide_purpose=planned.slide_purpose,
        eyebrow="示例与应用" if primary_role in {"example", "application", "transfer"} else "核心概念",
        title=_concise_point(_strip_section_prefix(section.title), 48),
        key_message=_demo_key_message(section),
        blocks=_fit_blocks_for_layout("concept", [SlideBlockSpec(
            block_id=f"{planned.slide_id}:points",
            type="bullets",
            title="本页要点",
            items=points,
        )]),
        speaker_notes=_trim(
            f"本页服务于：{section.learning_objective or section.title}。\n\n{source_notes}\n\n"
            "讲授时只在页面保留关键判断，定义、条件、推导和补充例子放在讲者备注中展开。",
            1800,
        ),
        section_id=section.section_id,
        source_section_ids=list(planned.source_section_ids),
        source_block_ids=list(planned.source_block_ids),
        learning_objective_ids=[section.objective_id] if section.objective_id else [],
        **_context_refs(context),
    )


def _cap_demo_practice_points(blocks: list[SlideBlockSpec]) -> list[SlideBlockSpec]:
    result: list[SlideBlockSpec] = []
    remaining = 5
    for source in blocks:
        block = source.model_copy(deep=True)
        if block.items:
            block.items = block.items[:remaining]
            used = len(block.items)
        elif block.content.strip():
            used = 1
        else:
            continue
        if used:
            result.append(block)
            remaining -= used
        if remaining == 0:
            break

    visible_points = 5 - remaining
    if visible_points < 3:
        generated = ["先独立作答", "说明判断依据", "给出边界或反例"][:3 - visible_points]
        if result and len(result) >= LAYOUT_CAPACITY["practice"]["blocks"]:
            target = result[-1]
            current = target.items or ([target.content] if target.content.strip() else [])
            target.content = ""
            target.items = _unique([*current, *generated])[:4]
        else:
            result.append(SlideBlockSpec(
                block_id="slide:demo:practice-checks",
                type="bullets",
                title="作答检查",
                items=generated,
            ))
    return result


def _demo_section_points(
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
) -> list[str]:
    section_title = _normalize_visible(_strip_section_prefix(section.title))
    paragraph_candidates = [
        paragraph
        for block in blocks
        for paragraph in _paragraphs(_block_markdown(block))
        if _normalize_visible(paragraph) != section_title
        and _normalize_visible(paragraph) not in {
            "本节要解决的问题",
            "完成本节后你将能够",
            "完成本节后你将可以",
        }
    ]
    candidates = list(paragraph_candidates)
    candidates.extend(context["knowledge_labels"])
    candidates.extend(context["ability_labels"])
    candidates.extend([
        f"核心问题：{_strip_section_prefix(section.title)}",
        "检查方式：能用自己的话解释并举出一个例子",
        "迁移要求：说明适用条件与边界",
    ])
    return [_concise_point(value, 58) for value in _unique(candidates)[:5]][:5]


def _demo_key_message(section: CourseSection) -> str:
    objective = _plain_text(section.learning_objective).strip()
    if objective and len(objective) <= 58:
        return objective
    title = _concise_point(_strip_section_prefix(section.title), 46)
    return f"本页聚焦：{title}"


def validate_slide_deck(
    content: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run independent semantic and visual gates over the shared slide spec."""
    semantic_issues: list[dict[str, Any]] = []
    visual_issues: list[dict[str, Any]] = []
    try:
        deck = SlideDeckContent.model_validate(content)
    except Exception as exc:
        issue = _issue(
            "critical",
            "invalid_slide_deck_contract",
            str(exc),
            "deck",
            layout="deck",
        )
        return {
            "passed": False,
            "score": 0.0,
            "semantic": {"passed": False, "issues": [issue]},
            "visual": {"passed": False, "issues": []},
            "issues": [issue],
            "blockers": [issue],
            "warnings": [],
            "slide_count": len(content.get("slides") or []) if isinstance(content, dict) else 0,
        }

    if len(deck.slides) < 2:
        semantic_issues.append(_issue("critical", "slide_deck_too_short", "课件缺少可讲授的正文页面。"))
    if not any(slide.layout == "cover" for slide in deck.slides):
        semantic_issues.append(_issue("critical", "slide_cover_missing", "课件缺少封面。"))
    if not any(slide.section_id for slide in deck.slides):
        semantic_issues.append(_issue("critical", "instructional_slide_missing", "课件没有绑定任何课程小节。"))

    unit_ids: set[str] = set()
    for slide in deck.slides:
        if slide.unit_id in unit_ids:
            semantic_issues.append(_issue("critical", "duplicate_slide_unit", "幻灯片单元 ID 重复。", slide.unit_id))
        unit_ids.add(slide.unit_id)
        if not slide.title.strip():
            semantic_issues.append(_issue("critical", "slide_title_missing", "幻灯片缺少标题。", slide.unit_id))
        if slide.section_id and (not slide.source_section_ids or not slide.source_block_ids):
            semantic_issues.append(_issue("critical", "slide_source_missing", "教学页没有课程来源绑定。", slide.unit_id))
        if slide.layout not in LAYOUT_CAPACITY:
            visual_issues.append(_issue("critical", "unknown_slide_layout", "幻灯片使用了未知版式。", slide.unit_id))
            continue
        if slide.layout == "recap" and any(
            not block.content.strip() and not any(item.strip() for item in block.items)
            for block in slide.blocks
        ):
            semantic_issues.append(_issue(
                "critical",
                "recap_evidence_missing",
                "课程收束页存在空卡片，无法帮助教师回扣知识与能力。",
                slide.unit_id,
            ))
        visual_issues.extend(_capacity_issues(slide))
        visual_issues.extend(_layout_content_issues(slide))
        visible_text = _slide_visible_text(slide)
        if _looks_like_raw_markdown(_slide_non_code_visible_text(slide)):
            visual_issues.append(_issue(
                "critical",
                "raw_markdown_leaked",
                "页面仍包含 Markdown 表格或标题符号，说明正文没有被转译为演示结构。",
                slide.unit_id,
            ))
        if _looks_like_raw_latex(_slide_non_code_visible_text(slide)):
            visual_issues.append(_issue(
                "critical",
                "raw_latex_leaked",
                "页面仍包含 LaTeX 源码，应先转换为可直接展示的数学文本。",
                slide.unit_id,
            ))
        if _looks_like_mojibake(visible_text):
            visual_issues.append(_issue(
                "critical",
                "text_encoding_corrupted",
                "页面包含替换字符或常见错误解码片段，不能导出为课堂课件。",
                slide.unit_id,
            ))
        if any(len(block.content) > 360 and block.type != "code" for block in slide.blocks):
            visual_issues.append(_issue(
                "critical",
                "paragraph_copy_detected",
                "页面包含接近正文长度的段落，应拆成视觉要点或讲者备注。",
                slide.unit_id,
            ))

    section_ids = {
        str(item.get("node_id") or "")
        for item in _asset_records(course_data or {}, "questions")
        if item.get("node_id")
    }
    practice_sections = {
        slide.section_id for slide in deck.slides
        if slide.section_id and slide.layout == "practice"
    }
    compressed_practice_sections = sorted(section_ids - practice_sections)
    if compressed_practice_sections:
        issue = _issue(
            "major",
            "formal_practice_not_represented",
            f"Demo 课件压缩了 {len(compressed_practice_sections)} 个小节的正式题目，未逐节安排检查页。",
            "deck",
            layout="practice",
        )
        issue.update({
            "count": len(compressed_practice_sections),
            "section_ids": compressed_practice_sections,
        })
        semantic_issues.append(issue)
    for slide in deck.slides:
        if slide.section_id and not slide.knowledge_refs:
            semantic_issues.append(_issue(
                "minor",
                "knowledge_binding_missing",
                "该页还没有正式知识 ID，当前只能依赖课程块来源。",
                slide.unit_id,
            ))

    slide_layouts = {slide.unit_id: slide.layout for slide in deck.slides}
    semantic_issues = [_attach_issue_layout(item, slide_layouts) for item in semantic_issues]
    visual_issues = [_attach_issue_layout(item, slide_layouts) for item in visual_issues]
    all_issues = [*semantic_issues, *visual_issues]
    blocking = [item for item in all_issues if item["severity"] == "critical"]
    warnings = [item for item in all_issues if item["severity"] != "critical"]
    weighted = sum({"critical": 24, "major": 6, "minor": 1}[item["severity"]] for item in all_issues)
    score = max(0.0, round(1 - (weighted / max(24, len(deck.slides) * 8)), 3))
    return {
        "passed": not blocking,
        "score": score,
        "semantic": {
            "passed": not any(item["severity"] == "critical" for item in semantic_issues),
            "issues": semantic_issues,
        },
        "visual": {
            "passed": not any(item["severity"] == "critical" for item in visual_issues),
            "issues": visual_issues,
        },
        "issues": all_issues,
        "blockers": blocking,
        "warnings": warnings,
        "slide_count": len(deck.slides),
    }


def slide_quality(slide: SlideSpec) -> dict[str, Any]:
    issues = [*_capacity_issues(slide), *_layout_content_issues(slide)]
    issues = [_attach_issue_layout(item, {slide.unit_id: slide.layout}) for item in issues]
    return {
        "passed": not any(item["severity"] == "critical" for item in issues),
        "issues": issues,
        "character_count": len(_slide_visible_text(slide)),
        "block_count": len(slide.blocks),
    }


def apply_presentation_overrides(
    content: SlideDeckContent,
    overrides: dict[str, dict[str, dict[str, Any]]],
) -> SlideDeckContent:
    """Reapply compatible presentation edits after source-driven regeneration."""
    result = content.model_copy(deep=True)
    by_id = {slide.unit_id: slide for slide in result.slides}
    result.presentation_overrides = deepcopy(overrides)
    conflicts: list[dict[str, Any]] = []
    for unit_id, fields in overrides.items():
        slide = by_id.get(unit_id)
        if slide is None:
            conflicts.append({"unit_id": unit_id, "field": "*", "reason": "slide_removed"})
            continue
        for field, override in fields.items():
            if field not in {"title", "subtitle", "key_message", "layout", "speaker_notes"}:
                conflicts.append({"unit_id": unit_id, "field": field, "reason": "unsupported_override"})
                continue
            current = getattr(slide, field)
            base_value = override.get("base_value")
            always_safe = field in {"layout", "speaker_notes"}
            if not always_safe and base_value is not None and current != base_value:
                conflicts.append({"unit_id": unit_id, "field": field, "reason": "source_changed"})
                continue
            try:
                setattr(slide, field, override.get("value"))
            except Exception:
                conflicts.append({"unit_id": unit_id, "field": field, "reason": "invalid_value"})
    result.override_conflicts = conflicts
    for slide in result.slides:
        slide.quality = slide_quality(slide)
    return SlideDeckContent.model_validate(result.model_dump(mode="json"))


def _chapter_slide(chapter: CourseSection, first_section: CourseSection) -> SlideSpec:
    focus = str(chapter.attributes.get("learning_focus") or first_section.learning_objective or "")
    return SlideSpec(
        unit_id=f"slide:chapter:{chapter.section_id}",
        position=0,
        layout="chapter",
        slide_purpose="chapter_transition",
        eyebrow="章节转场",
        title=chapter.title,
        key_message=_trim(focus, 90),
        blocks=[SlideBlockSpec(
            block_id=f"slide:chapter:{chapter.section_id}:focus",
            type="statement",
            title="本章主线",
            content=_trim(focus or f"从“{first_section.title}”开始建立本章能力。", 90),
        )],
        speaker_notes="说明本章要解决的核心问题，以及它与上一章的关系。",
        source_keys=[
            f"section_structure:{chapter.section_id}",
            f"section_structure:{first_section.section_id}",
        ],
    )


def _objective_slide(
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
) -> SlideSpec:
    objective_block = next((block for block in blocks if block.role == "objective"), None)
    problem = _trim(_first_question(_block_markdown(objective_block)), 84) if objective_block else ""
    knowledge_details = context["knowledge_labels"] or [
        _trim(str(block.payload.get("title") or _block_key_message(block)), 42)
        for block in blocks
        if block.role in {"concept", "prerequisite", "reasoning"}
    ]
    ability_details = context["ability_labels"] or (
        [_trim(section.learning_objective, 62)] if section.learning_objective else []
    )
    knowledge = knowledge_details[:4]
    abilities = ability_details[:3]
    slide_blocks = [SlideBlockSpec(
        block_id=f"slide:{section.section_id}:objective",
        type="callout",
        title="要解决的问题",
        content=_trim(problem or section.learning_objective or section.title, 170),
    )]
    if knowledge:
        slide_blocks.append(SlideBlockSpec(
            block_id=f"slide:{section.section_id}:knowledge",
            type="bullets",
            title="知识坐标",
            items=knowledge,
        ))
    if abilities:
        slide_blocks.append(SlideBlockSpec(
            block_id=f"slide:{section.section_id}:ability",
            type="bullets",
            title="完成后能够",
            items=abilities,
        ))
    slide_blocks = _fit_blocks_for_layout("objective", slide_blocks)
    return SlideSpec(
        unit_id=f"slide:{section.section_id}",
        position=0,
        layout="objective",
        slide_purpose="learning_objective",
        eyebrow="本节任务",
        title=section.title,
        key_message=_trim(section.learning_objective or problem or section.title, 150),
        blocks=slide_blocks,
        speaker_notes=_trim(
            "先用一个真实问题唤起学生已有经验，再明确本节结束时需要做到什么。\n"
            f"本节目标是：{section.learning_objective or section.title}。\n"
            f"{'完整知识坐标：' + '、'.join(knowledge_details) + '。' if knowledge_details else ''}\n"
            f"{'完整能力目标：' + '、'.join(ability_details) + '。' if ability_details else ''}\n"
            "不要在目标页提前给出结论；请让学生知道后续每一页如何帮助他们完成这个目标。",
            1800,
        ),
        section_id=section.section_id,
        source_section_ids=[section.section_id],
        source_keys=[
            f"section_structure:{section.section_id}",
            *([f"objective:{section.objective_id}"] if section.objective_id else []),
        ],
        # The objective page also displays the section's knowledge and ability
        # coordinates. Bind the active section blocks so semantic edits can
        # trace the full teaching impact instead of becoming an orphan page.
        source_block_ids=[block.block_id for block in blocks if block.status != "retired"],
        learning_objective_ids=[section.objective_id] if section.objective_id else [],
        **_context_refs(context),
    )


def _compact_section_slide(
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
) -> SlideSpec:
    parsed = [_block_to_slide_blocks(block) for block in blocks]
    layout = _layout_for_blocks(blocks)
    slide_blocks = _fit_blocks_for_layout(
        layout,
        [
            *[item for values in parsed for item in values][:4],
            _objective_alignment_block(section, "concept_and_reasoning"),
        ],
    )
    return SlideSpec(
        unit_id=f"slide:{section.section_id}:content:1",
        position=0,
        layout=layout,
        slide_purpose="concept_and_reasoning",
        eyebrow="核心教学",
        title=section.title,
        key_message=_trim(section.learning_objective or _first_meaningful_line(blocks), 150),
        blocks=slide_blocks,
        speaker_notes=_trim(
            f"围绕本节目标讲清概念并检查理解：{section.learning_objective or section.title}\n\n"
            + "\n\n".join(
                _plain_text(_block_markdown(block))
                for block in blocks
                if _block_markdown(block).strip()
            ),
            1800,
        ),
        section_id=section.section_id,
        source_section_ids=[section.section_id],
        source_block_ids=[block.block_id for block in blocks],
        learning_objective_ids=[section.objective_id] if section.objective_id else [],
        **_context_refs(context),
    )


def _slide_for_block(
    section: CourseSection,
    block: CourseBlock,
    context: dict[str, list[str]],
    index: int,
) -> SlideSpec:
    blocks = _block_to_slide_blocks(block)
    layout = _layout_for_block(block, blocks)
    blocks = _fit_blocks_for_layout(layout, blocks)
    blocks = _enrich_instructional_blocks(block, blocks, context)
    blocks.append(_objective_alignment_block(section, block.role, source_id=block.block_id))
    # Enrichment happens after the first source-content fit. Re-run the layout
    # fitter so the support card shares the page budget instead of pushing a
    # valid source page past the quality gate.
    blocks = _fit_blocks_for_layout(layout, blocks)
    purpose_labels = {
        "concept": "概念建构",
        "reasoning": "推理过程",
        "example": "例子映射",
        "application": "应用迁移",
        "activity": "学习者行动",
        "feedback": "检查反馈",
        "misconception": "误区辨析",
        "summary": "本节小结",
    }
    title = _clean_slide_title(str(block.payload.get("title") or section.title))
    return SlideSpec(
        unit_id=f"slide:{section.section_id}:{block.role}:{index + 1}",
        position=0,
        layout=layout,
        slide_purpose=block.role,
        eyebrow=purpose_labels.get(block.role, "核心教学"),
        title=_trim(title, 48),
        key_message=_trim(
            f"{_objective_focus_label(section.learning_objective)}｜{_block_key_message(block)}",
            150,
        ),
        blocks=blocks,
        speaker_notes=_speaker_notes(block, section),
        section_id=section.section_id,
        source_section_ids=[section.section_id],
        source_block_ids=[block.block_id],
        learning_objective_ids=_unique([
            *block.objective_refs,
            *([section.objective_id] if section.objective_id else []),
        ]),
        **_context_refs(context),
    )


def _assessment_slide(
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
    course_data: dict[str, Any],
) -> SlideSpec:
    questions = [
        item for item in _asset_records(course_data, "questions")
        if str(item.get("node_id") or "") == section.section_id
    ]
    misconceptions = context["misconception_labels"]
    action_block = next((block for block in blocks if block.role in {"activity", "checkpoint"}), None)
    slide_blocks: list[SlideBlockSpec] = []
    practice_ids: list[str] = []
    practice_revisions: dict[str, str] = {}
    source_blocks: list[str] = []
    full_prompt = ""
    action_detail = ""
    if questions:
        question = questions[0]
        prompt = str(question.get("prompt") or question.get("question") or "").strip()
        full_prompt = _plain_text(prompt)
        practice_id = str(question.get("question_id") or question.get("asset_id") or "")
        practice_ids = [practice_id] if practice_id else []
        practice_revision = str(question.get("revision_id") or "")
        if practice_id and practice_revision:
            practice_revisions[practice_id] = practice_revision
        slide_blocks.append(SlideBlockSpec(
            block_id=f"slide:{section.section_id}:formal-practice",
            type="exercise",
            title="先独立作答",
            content=_trim(_plain_text(prompt), 220),
            metadata={"formal": True, "practice_task_id": practice_id},
        ))
        if _objective_dimension(section.learning_objective) != "procedural":
            slide_blocks.append(SlideBlockSpec(
                block_id=f"slide:{section.section_id}:objective-follow-up",
                type="callout",
                title="解释追问",
                content=_trim(
                    _objective_alignment_prompt(section, "mastery_check"),
                    150,
                ),
                metadata={"generated_from_objective": True},
            ))
    elif action_block:
        source_blocks.append(action_block.block_id)
        action_detail = _plain_text(_block_markdown(action_block))
        slide_blocks.extend(_block_to_slide_blocks(action_block)[:1])
    else:
        source_blocks.extend([block.block_id for block in blocks[:2]])
        slide_blocks.extend([
            SlideBlockSpec(
                block_id=f"slide:{section.section_id}:generated-check",
                type="exercise",
                title="先脱离课件解释",
                content=_trim(
                    f"请用不超过三句话解释“{_strip_section_prefix(section.title)}”，"
                    f"并说明它如何帮助你做到：{section.learning_objective or section.title}。",
                    220,
                ),
                metadata={"formal": False, "generated_from_objective": True},
            ),
            SlideBlockSpec(
                block_id=f"slide:{section.section_id}:generated-rubric",
                type="bullets",
                title="自检标准",
                items=["概念使用准确", "说出判断或推理依据", "能举例或辨析一个反例"],
            ),
        ])
    if misconceptions:
        slide_blocks.append(SlideBlockSpec(
            block_id=f"slide:{section.section_id}:misconceptions",
            type="misconception",
            title="作答前检查",
            items=[_concise_point(item, 110) for item in misconceptions[:3]],
        ))
    practice_note_values = _unique([
        full_prompt,
        action_detail,
        *misconceptions,
        *[
            value
            for block in slide_blocks
            for value in (block.items or [block.content])
            if value
        ],
    ])
    slide_blocks = _fit_blocks_for_layout("practice", slide_blocks)
    return SlideSpec(
        unit_id=f"slide:{section.section_id}:check",
        position=0,
        layout="practice",
        slide_purpose="mastery_check",
        eyebrow="理解检查",
        title=f"你能独立完成吗：{_strip_section_prefix(section.title)}",
        key_message=_concise_point(
            section.learning_objective or "用一个可回答的任务验证是否真正理解。",
            96,
        ),
        blocks=slide_blocks,
        speaker_notes=_trim(
            "先让学习者作答，再显示判断标准；不要把答案与题目同时展示。\n\n"
            "完整题目与检查细节：\n"
            + "\n".join(f"- {value}" for value in practice_note_values),
            1800,
        ),
        section_id=section.section_id,
        source_section_ids=[section.section_id],
        source_keys=[f"section_structure:{section.section_id}"] if not source_blocks else [],
        source_block_ids=_unique([*source_blocks, *[block.block_id for block in blocks]]),
        practice_task_ids=practice_ids,
        practice_source_revisions=practice_revisions,
        learning_objective_ids=[section.objective_id] if section.objective_id else [],
        **_context_refs(context),
    )


def _recap_slide(
    document: CourseDocument,
    learning_sections: list[CourseSection],
    knowledge_index: _KnowledgeIndex,
) -> SlideSpec:
    labels: list[str] = []
    abilities: list[str] = []
    refs: list[str] = []
    for section in learning_sections:
        context = knowledge_index.for_section(section.section_id, section)
        labels.extend(context["knowledge_labels"])
        abilities.extend(context["ability_labels"])
        refs.extend(context["knowledge_refs"])
    if not _unique(labels):
        labels.extend(
            _clean_slide_title(str(block.payload.get("title") or ""))
            for block in document.blocks
            if block.status != "retired"
            and block.role in {"concept", "reasoning", "example", "application"}
            and str(block.payload.get("title") or "").strip()
        )
    if not _unique(abilities):
        abilities.extend(
            _concise_point(section.learning_objective, 68)
            for section in learning_sections
            if section.learning_objective.strip()
        )
    if not _unique(labels):
        labels.extend(
            _strip_section_prefix(section.title)
            for section in learning_sections
            if section.title.strip()
        )
    if not _unique(abilities):
        abilities.extend(
            f"能解释并应用{_strip_section_prefix(section.title)}"
            for section in learning_sections
            if section.title.strip()
        )
    return SlideSpec(
        unit_id="slide:recap",
        position=0,
        layout="recap",
        slide_purpose="course_recap",
        eyebrow="课程收束",
        title="把知识变成可迁移的能力",
        key_message="回到学习目标，用独立解释、应用与检查证明掌握。",
        blocks=[
            SlideBlockSpec(
                block_id="slide:recap:knowledge",
                type="bullets",
                title="核心知识",
                items=[_concise_point(value, 64) for value in _unique(labels)[:4]],
            ),
            SlideBlockSpec(
                block_id="slide:recap:ability",
                type="bullets",
                title="可观察能力",
                items=[_concise_point(value, 78) for value in _unique(abilities)[:4]],
            ),
        ],
        speaker_notes="最后不要重复目录，而要让学习者说明自己现在能独立完成什么。",
        source_section_ids=_unique(section.section_id for section in learning_sections),
        learning_objective_ids=_unique(
            section.objective_id
            for section in learning_sections
            if section.objective_id
        ),
        source_keys=["course_title"],
        knowledge_refs=_unique(refs),
    )


class _KnowledgeIndex:
    def __init__(self, course_data: dict[str, Any]) -> None:
        assets = course_data.get("learning_assets") or {}
        raw_base = course_data.get("course_knowledge_base") or _first_mapping(assets.get("course_knowledge_base"))
        self.base = raw_base if isinstance(raw_base, Mapping) else {}
        raw_map = _first_mapping(assets.get("course_knowledge_map"))
        self.map = raw_map if isinstance(raw_map, Mapping) else {}
        self.points = {str(item.get("knowledge_id") or ""): item for item in self.base.get("knowledge_points") or []}
        self.skills = {str(item.get("skill_id") or ""): item for item in self.base.get("skill_units") or []}
        self.mistakes = {str(item.get("misconception_id") or ""): item for item in self.base.get("misconceptions") or []}
        self.criteria = {str(item.get("criterion_id") or ""): item for item in self.base.get("mastery_criteria") or []}

    def for_section(self, section_id: str, section: CourseSection) -> dict[str, list[str]]:
        if self.base:
            bindings = [
                item for item in self.base.get("bindings") or []
                if item.get("target_type") == "section" and str(item.get("target_id") or "") == section_id
            ]
            knowledge_refs = _unique([
                value for item in bindings for value in item.get("knowledge_ids") or []
            ])
            ability_refs = _unique([
                value for item in bindings for value in item.get("skill_ids") or []
            ])
            misconception_refs = _unique([
                key for key, item in self.mistakes.items()
                if str(item.get("primary_knowledge_id") or "") in knowledge_refs
            ])
            mastery_refs = _unique([
                key for key, item in self.criteria.items()
                if set(item.get("knowledge_ids") or []) & set(knowledge_refs)
            ])
            if knowledge_refs:
                return {
                    "knowledge_refs": knowledge_refs,
                    "ability_refs": ability_refs,
                    "misconception_refs": misconception_refs,
                    "mastery_refs": mastery_refs,
                    "knowledge_labels": [_concise_point(str(self.points.get(key, {}).get("name") or key), 42) for key in knowledge_refs],
                    "ability_labels": [
                        _concise_point(str(self.skills.get(key, {}).get("observable_behavior") or self.skills.get(key, {}).get("name") or key), 62)
                        for key in ability_refs
                    ],
                    "misconception_labels": [
                        _concise_point(str(self.mistakes.get(key, {}).get("observable_error_pattern") or self.mistakes.get(key, {}).get("name") or key), 110)
                        for key in misconception_refs
                    ],
                    "mastery_labels": [
                        _trim(str(self.criteria.get(key, {}).get("observable_performance") or self.criteria.get(key, {}).get("name") or key), 72)
                        for key in mastery_refs
                    ],
                }

        mappings = [
            item for item in self.map.get("mappings") or []
            if str(item.get("section_id") or "") == section_id
            and str(item.get("local_kind") or "") == "knowledge_point"
        ]
        knowledge_refs = _unique([
            value
            for item in mappings
            for value in item.get("course_knowledge_node_ids") or []
        ])
        if not knowledge_refs:
            knowledge_refs = _unique([item.get("mapping_id") for item in mappings])
        knowledge_labels = [_concise_point(str(item.get("local_name") or ""), 42) for item in mappings if item.get("local_name")]
        ability_labels = [_concise_point(str(item.get("local_capability") or ""), 62) for item in mappings if item.get("local_capability")]
        if not knowledge_labels:
            for group in section.attributes.get("knowledge_structure") or []:
                for point in group.get("knowledge_points") or []:
                    if point.get("name"):
                        knowledge_labels.append(_concise_point(str(point["name"]), 42))
                    if point.get("capability"):
                        ability_labels.append(_concise_point(str(point["capability"]), 62))
        misconception_labels = [
            _concise_point(str(item), 110)
            for item in section.attributes.get("misconceptions") or []
            if str(item).strip()
        ]
        return {
            "knowledge_refs": knowledge_refs,
            "ability_refs": [],
            "misconception_refs": [],
            "mastery_refs": [],
            "knowledge_labels": _unique(knowledge_labels),
            "ability_labels": _unique(ability_labels),
            "misconception_labels": _unique(misconception_labels),
            "mastery_labels": [],
        }


def _block_to_slide_blocks(block: CourseBlock) -> list[SlideBlockSpec]:
    markdown = _block_markdown(block)
    contains_formula = _looks_like_raw_latex(markdown)
    code_blocks = _code_blocks(markdown)
    table = _markdown_table(markdown)
    bullets = _markdown_bullets(markdown)
    paragraphs = _paragraphs(markdown)
    result: list[SlideBlockSpec] = []
    title = _clean_slide_title(str(block.payload.get("title") or "").strip())

    if table:
        result.append(SlideBlockSpec(
            block_id=f"{block.block_id}:comparison",
            type="comparison",
            title=title,
            metadata={"headers": table[0], "rows": table[1:6]},
        ))
    if code_blocks:
        language, code = code_blocks[0]
        result.append(SlideBlockSpec(
            block_id=f"{block.block_id}:code",
            type="code",
            title="代码观察",
            content=_trim_code(code, 900),
            metadata={"language": language or "text"},
        ))
    if bullets:
        result.append(SlideBlockSpec(
            block_id=f"{block.block_id}:bullets",
            type="process" if block.role == "reasoning" else ("exercise" if block.role in {"activity", "checkpoint"} else "bullets"),
            title=title if not result else "关键步骤",
            items=[_trim(item, 72) for item in bullets[:6]],
        ))
    if paragraphs:
        preferred_type: SlideBlockType = {
            "misconception": "misconception",
            "counterexample": "misconception",
            "activity": "exercise",
            "checkpoint": "exercise",
            "feedback": "callout",
        }.get(block.role, "statement")
        first = _trim(paragraphs[0], 230)
        if first and not any(item.content == first for item in result):
            result.append(SlideBlockSpec(
                block_id=f"{block.block_id}:statement",
                type=preferred_type,
                title=title if not result else "核心判断",
                content=first,
                metadata={"formula": True} if contains_formula else {},
            ))
        supporting = [_trim(item, 90) for item in paragraphs[1:4] if item]
        if supporting and not bullets and len(result) < 3:
            result.append(SlideBlockSpec(
                block_id=f"{block.block_id}:support",
                type="bullets",
                title="解释要点",
                items=supporting,
            ))
    if not result:
        result.append(SlideBlockSpec(
            block_id=f"{block.block_id}:fallback",
            type="statement",
            title=title,
            content=_trim(_plain_text(markdown), 230),
        ))
    return result[:3]


def _select_instructional_blocks(blocks: list[CourseBlock]) -> list[CourseBlock]:
    selected: list[CourseBlock] = []
    groups = [
        {"concept", "reasoning", "prerequisite"},
        {"example", "application", "counterexample"},
        {"activity", "checkpoint", "misconception", "feedback", "summary", "transfer"},
    ]
    for roles in groups:
        candidate = next((block for block in blocks if block.role in roles and block.role != "objective"), None)
        if candidate and candidate not in selected:
            selected.append(candidate)
    for block in blocks:
        if block.role != "objective" and block not in selected:
            selected.append(block)
    return selected


def _enrich_instructional_blocks(
    source: CourseBlock,
    blocks: list[SlideBlockSpec],
    context: dict[str, list[str]],
) -> list[SlideBlockSpec]:
    """Add a compact teaching support card when a source block is visually sparse.

    The source course remains authoritative. The support card is assembled only
    from the same section's knowledge, ability, misconception, or mastery
    bindings, so a slide becomes teachable without inventing new facts.
    """
    if len(blocks) >= 2 or any(block.type == "code" for block in blocks):
        return blocks
    visible = {
        _normalize_visible(value)
        for block in blocks
        for value in [block.title, block.content, *block.items]
        if value
    }
    if source.role in {"example", "application", "transfer"}:
        title = "迁移检查"
        candidates = context["ability_labels"] or context["mastery_labels"]
    elif source.role in {"reasoning", "prerequisite"}:
        title = "推理线索"
        candidates = context["knowledge_labels"] or context["ability_labels"]
    elif source.role in {"misconception", "counterexample"}:
        title = "辨析边界"
        candidates = context["misconception_labels"] or context["knowledge_labels"]
    elif source.role in {"activity", "checkpoint", "feedback"}:
        title = "判断标准"
        candidates = context["mastery_labels"] or context["ability_labels"]
    else:
        title = "概念坐标"
        candidates = context["knowledge_labels"] or context["ability_labels"]
    items = [
        _trim(value, 52)
        for value in candidates
        if _normalize_visible(value) not in visible
    ][:3]
    if not items:
        return blocks
    return [
        *blocks,
        SlideBlockSpec(
            block_id=f"{source.block_id}:teaching-support",
            type="bullets",
            title=title,
            items=items,
        ),
    ]


def _objective_dimension(value: str) -> str:
    normalized = str(value or "").lower()
    if any(marker in normalized for marker in ("理解", "解释", "为什么", "含义", "原理", "关系", "本质", "explain", "why")):
        return "conceptual"
    if any(marker in normalized for marker in ("应用", "迁移", "建模", "新情境", "apply", "transfer", "model")):
        return "transfer"
    if any(marker in normalized for marker in ("评价", "比较方案", "设计", "证明", "创造", "evaluate", "design", "prove")):
        return "evaluation"
    return "procedural"


def _objective_alignment_prompt(section: CourseSection, role: str) -> str:
    dimension = _objective_dimension(section.learning_objective)
    if dimension == "conceptual":
        if role in {"reasoning", "concept_and_reasoning"}:
            return "请说明每一步为什么成立，以及对象之间的关系如何决定运算顺序。"
        if role in {"example", "application", "transfer"}:
            return "完成例题后，再解释这个过程如何体现概念关系，而不只报告结果。"
        if role in {"misconception", "counterexample"}:
            return "指出错误背后的概念混淆，并用成立依据完成纠正。"
        if role in {"mastery_check", "activity", "checkpoint"}:
            return "请脱离计算步骤，用自己的话解释概念含义、关系与运算顺序。"
        return "学习本页时持续追问：它表示什么、为什么成立、与哪些概念相连？"
    if dimension == "transfer":
        return "请判断本页方法的适用条件，并尝试把它迁移到一个新情境。"
    if dimension == "evaluation":
        return "请比较可能的方案，用明确标准说明为什么选择这一种。"
    return "请独立完成关键步骤，并说明怎样检查顺序、规则和结果是否正确。"


def _objective_focus_label(objective: str) -> str:
    return {
        "conceptual": "解释为什么",
        "transfer": "迁移到新情境",
        "evaluation": "比较并论证",
        "procedural": "掌握步骤",
    }[_objective_dimension(objective)]


def _objective_alignment_block(
    section: CourseSection,
    role: str,
    *,
    source_id: str | None = None,
) -> SlideBlockSpec:
    return SlideBlockSpec(
        block_id=f"{source_id or section.section_id}:objective-alignment",
        type="callout",
        title="目标对齐",
        content=_trim(_objective_alignment_prompt(section, role), 150),
        metadata={
            "generated_from_objective": True,
            "objective_id": section.objective_id,
        },
    )


def _layout_for_blocks(blocks: list[CourseBlock]) -> SlideLayout:
    parsed = [item for block in blocks for item in _block_to_slide_blocks(block)]
    if any(item.type == "code" for item in parsed):
        return "code"
    if any(item.type == "comparison" for item in parsed):
        return "comparison"
    if any(block.role in {"activity", "checkpoint"} for block in blocks):
        return "practice"
    return "concept"


def _layout_for_block(block: CourseBlock, parsed: list[SlideBlockSpec]) -> SlideLayout:
    if any(item.type == "code" for item in parsed):
        return "code"
    if any(item.type == "comparison" for item in parsed):
        return "comparison"
    if block.role in {"misconception", "counterexample"}:
        return "misconception"
    if block.role in {"activity", "checkpoint", "feedback"}:
        return "practice"
    if block.role == "reasoning":
        return "process"
    if block.role in {"summary", "transfer"}:
        return "recap"
    return "concept"


def _context_refs(context: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        "knowledge_refs": context["knowledge_refs"],
        "ability_refs": context["ability_refs"],
        "misconception_refs": context["misconception_refs"],
        "mastery_refs": context["mastery_refs"],
        "knowledge_labels": context["knowledge_labels"],
        "ability_labels": context["ability_labels"],
    }


def _merge_block_knowledge(
    context: dict[str, list[str]],
    blocks: list[CourseBlock],
) -> dict[str, list[str]]:
    merged = deepcopy(context)
    block_refs = _unique([
        knowledge_id
        for block in blocks
        for knowledge_id in block.concept_refs
    ])
    merged["knowledge_refs"] = _unique([*merged["knowledge_refs"], *block_refs])
    if not merged["knowledge_labels"] and block_refs:
        merged["knowledge_labels"] = block_refs
    return merged


def _fit_blocks_for_layout(
    layout: SlideLayout,
    blocks: list[SlideBlockSpec],
) -> list[SlideBlockSpec]:
    """Normalize visible content to the actual geometry of each renderer."""
    capacity = LAYOUT_CAPACITY[layout]
    source = [block.model_copy(deep=True) for block in blocks]
    if layout == "code":
        code = next((block for block in source if block.type == "code"), None)
        insights = _unique([
            value
            for block in source if block.type != "code"
            for value in (block.items or [block.content])
            if value
        ])
        fitted = [code] if code else []
        if insights:
            fitted.append(SlideBlockSpec(
                block_id=f"{code.block_id if code else 'slide'}:insights",
                type="bullets",
                title="阅读线索",
                items=[_concise_point(value, 54) for value in insights[:4]],
            ))
        return fitted
    if layout == "comparison":
        comparison = next((block for block in source if block.type == "comparison"), None)
        return [comparison or source[0]] if source else []
    if layout == "process":
        values = _unique([
            value
            for block in source
            for value in (block.items or [block.content])
            if value
        ])
        if not values:
            return []
        return [SlideBlockSpec(
            block_id=f"{source[0].block_id}:steps",
            type="process",
            title=source[0].title,
            items=[_concise_point(value, 48) for value in values[:5]],
        )]
    if layout == "misconception":
        values = _unique([
            value
            for block in source
            for value in (block.items or [block.content])
            if value
        ])
        if not values:
            return []
        return [SlideBlockSpec(
            block_id=f"{source[0].block_id}:mistakes",
            type="misconception",
            title=source[0].title,
            items=[_concise_point(value, 44) for value in values[:4]],
        )]
    if layout == "practice":
        if not source:
            return []
        exercise = next((block for block in source if block.type == "exercise"), source[0])
        exercise = exercise.model_copy(deep=True)
        exercise_limit = 110 if exercise.type == "misconception" else 52
        if exercise.items:
            exercise.items = [_concise_point(value, exercise_limit) for value in exercise.items[:4]]
            exercise.content = ""
        else:
            exercise.content = _concise_point(exercise.content, 180)
        checks: list[str] = []
        for block in source:
            if block.block_id == exercise.block_id:
                continue
            limit = 110 if block.type == "misconception" else 52
            checks.extend(
                _concise_point(value, limit)
                for value in (block.items or [block.content])
                if value
            )
        fitted = [exercise]
        if checks:
            fitted.append(SlideBlockSpec(
                block_id=f"{exercise.block_id}:checks",
                type="bullets",
                title="检查标准",
                items=_unique(checks)[:4],
            ))
        return fitted
    if layout == "objective":
        if not source:
            return []
        question = next((block for block in source if block.type == "callout"), source[0])
        result = [question, *[block for block in source if block is not question][:2]]
        for block in result:
            block.title = _concise_point(block.title, 24)
            if block is question:
                block.content = _concise_point(
                    block.content or (block.items[0] if block.items else ""),
                    84,
                )
                block.items = []
            elif block.items:
                block.items = [_concise_point(value, 58) for value in block.items[:2]]
                block.content = ""
            else:
                block.content = _concise_point(block.content, 58)
        return result
    if layout == "concept":
        result = source[:3]
        for block in result:
            block.title = _concise_point(block.title, 24)
            if block.items:
                block.items = [_concise_point(value, 32) for value in block.items[:3]]
                block.content = ""
            else:
                block.content = _concise_point(block.content, 96)
        overflow = source[3:]
        if overflow and result:
            overflow_points = _unique([
                f"{block.title}：{value}" if block.title else value
                for block in overflow
                for value in (block.items or [block.content])[:1]
                if value
            ])
            if overflow_points:
                last = result[-1]
                current = last.items or ([last.content] if last.content else [])
                overflow_summary = _concise_point("；".join(overflow_points), 32)
                last.content = ""
                last.items = [
                    _concise_point(value, 32)
                    for value in _unique(current)[:2]
                ]
                if overflow_summary:
                    last.items.append(overflow_summary)
        return result

    result = source[:capacity["blocks"]]
    for block in result:
        if block.items:
            block.content = ""
    remaining_items = capacity["items"]
    for block in result:
        block.items = block.items[:remaining_items]
        remaining_items -= len(block.items)
    return result


def _capacity_issues(slide: SlideSpec) -> list[dict[str, Any]]:
    capacity = LAYOUT_CAPACITY.get(slide.layout)
    if not capacity:
        return [_issue("critical", "unknown_slide_layout", "幻灯片版式未注册。", slide.unit_id)]
    issues: list[dict[str, Any]] = []
    text = _slide_visible_text(slide)
    item_count = sum(len(block.items) for block in slide.blocks)
    if len(slide.blocks) > capacity["blocks"]:
        issues.append(_issue("critical", "slide_block_overflow", "页面内容块超过版式容量。", slide.unit_id))
    if len(text) > capacity["characters"]:
        issues.append(_issue("critical", "slide_text_overflow", "页面文字超过版式容量。", slide.unit_id))
    if item_count > capacity["items"]:
        issues.append(_issue("critical", "slide_item_overflow", "页面要点数量超过版式容量。", slide.unit_id))
    if len(slide.title) > 54:
        issues.append(_issue("major", "slide_title_too_long", "页面标题过长，投影时难以扫读。", slide.unit_id))
    if len(slide.key_message) > 170:
        issues.append(_issue("major", "slide_key_message_too_long", "页面核心信息不够聚焦。", slide.unit_id))
    return issues


def _layout_content_issues(slide: SlideSpec) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    visible_blocks = [block for block in slide.blocks if block.type != "code"]
    if slide.layout == "chapter" and len(slide.key_message) > 90:
        issues.append(_issue("critical", "chapter_message_overflow", "章节转场主线超过实际显示容量。", slide.unit_id))
    if slide.layout == "code":
        insight_values = [
            value for block in visible_blocks
            for value in (block.items or [block.content]) if value
        ]
        if len(insight_values) > 4 or any(len(value) > 54 for value in insight_values):
            issues.append(_issue("critical", "code_insight_overflow", "代码页阅读线索超过侧栏容量。", slide.unit_id))
    if slide.layout == "objective" and any(
        len(block.content) > (84 if block.type == "callout" else 58)
        or len(block.items) > (0 if block.type == "callout" else 2)
        or any(len(item) > 58 for item in block.items)
        for block in visible_blocks
    ):
        issues.append(_issue("critical", "objective_content_overflow", "目标页内容超过左右栏容量。", slide.unit_id))
    if slide.layout == "concept" and any(
        len(block.content) > 96
        or len(block.items) > 3
        or any(len(item) > 32 for item in block.items)
        or bool(block.content.strip() and block.items)
        for block in visible_blocks
    ):
        issues.append(_issue("critical", "concept_card_overflow", "概念页卡片内容超过实际容量。", slide.unit_id))
    if slide.layout == "process" and any(
        len(item) > 48 for block in visible_blocks for item in block.items
    ):
        issues.append(_issue("critical", "process_step_overflow", "过程页步骤超过单卡容量。", slide.unit_id))
    if slide.layout == "practice" and any(
        (block.type == "exercise" and (
            len(block.content) > 220 or any(len(item) > 52 for item in block.items)
        ))
        or (block.type == "misconception" and (
            len(block.content) > 90 or any(len(item) > 110 for item in block.items)
        ))
        for block in visible_blocks
    ):
        issues.append(_issue("critical", "practice_content_overflow", "练习页题目或检查项超过实际容量。", slide.unit_id))
    if slide.layout == "practice":
        exercise = next(
            (block for block in slide.blocks if block.type == "exercise"),
            slide.blocks[0] if slide.blocks else None,
        )
        check_values = [
            value
            for block in slide.blocks if block is not exercise
            for value in (block.items or [block.content])
            if value
        ]
        if len(check_values) > 4:
            issues.append(_issue(
                "critical",
                "practice_check_overflow",
                "练习页检查区超过四项，PPTX 将无法完整显示。",
                slide.unit_id,
            ))
    return issues


def _slide_visible_text(slide: SlideSpec) -> str:
    values = [slide.eyebrow, slide.title, slide.subtitle, slide.key_message]
    for block in slide.blocks:
        values.extend([block.title, block.content, *block.items])
        if block.type == "comparison":
            values.extend(str(value) for row in block.metadata.get("rows") or [] for value in row)
    return "\n".join(str(value) for value in values if str(value).strip())


def _slide_non_code_visible_text(slide: SlideSpec) -> str:
    values = [slide.eyebrow, slide.title, slide.subtitle, slide.key_message]
    for block in slide.blocks:
        values.append(block.title)
        if block.type != "code":
            values.extend([block.content, *block.items])
        if block.type == "comparison":
            values.extend(str(value) for row in block.metadata.get("rows") or [] for value in row)
    return "\n".join(str(value) for value in values if str(value).strip())


def _looks_like_raw_markdown(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    return len(table_lines) >= 2 or any(re.match(r"^#{1,6}\s+", line) for line in lines)


def _looks_like_raw_latex(text: str) -> bool:
    return bool(
        "$" in text
        or re.search(
            r"\\(?:begin|end|mathbf|mathrm|mathbb|mathcal|text|operatorname|"
            r"frac|sqrt|times|cdot|left|right|to|in|notin|neq|leq|geq|"
            r"approx|equiv|sum|prod|int|lim|alpha|beta|gamma|delta|theta|"
            r"lambda|mu|pi|rho|sigma|phi|omega)\b",
            text,
        )
        or re.search(r"\b(?:begin|end)\s*\{(?:bmatrix|pmatrix|matrix|cases)\}", text)
        or re.search(r"\b(?:begin|end)(?:bmatrix|pmatrix|matrix|cases)\b", text)
    )


def _looks_like_mojibake(text: str) -> bool:
    return bool(
        "\ufffd" in text
        or re.search(r"(?:Ã.|Â.|â[\u0080-\u00bf]|ï¿½)", text)
    )


def _block_key_message(block: CourseBlock) -> str:
    raw_summary = str(block.payload.get("summary") or "")
    summary = _plain_text(
        _block_markdown(block)
        if _looks_like_raw_latex(raw_summary)
        else raw_summary
    )
    if summary and not summary.startswith("|"):
        return _first_sentence(summary)
    paragraphs = _paragraphs(_block_markdown(block))
    return _first_sentence(paragraphs[0]) if paragraphs else str(block.payload.get("title") or "")


def _speaker_notes(block: CourseBlock, section: CourseSection) -> str:
    details = _paragraphs(_block_markdown(block))
    notes = "\n\n".join(details[:4])
    return _trim(
        f"本页服务于“{section.learning_objective or section.title}”。\n\n{notes}\n\n"
        "讲授时先说核心判断，再用页面结构展开；完整细节保留在课程正文。",
        1800,
    )


def _blocks_by_section(document: CourseDocument) -> dict[str, list[CourseBlock]]:
    result: dict[str, list[CourseBlock]] = {}
    for block in sorted(document.blocks, key=lambda item: (item.section_id, item.position)):
        result.setdefault(block.section_id, []).append(block)
    return result


def _estimated_slide_count(sections: list[CourseSection]) -> int:
    return max(4, 3 + len(sections) * 4)


def _course_subtitle(learning_sections: list[CourseSection], chapters: list[CourseSection]) -> str:
    return f"{len(chapters)} 个主题章节 · {len(learning_sections)} 个可学习单元"


def _course_learning_promise(sections: list[CourseSection]) -> str:
    objectives = [section.learning_objective for section in sections if section.learning_objective]
    return _trim(objectives[-1] if objectives else "完成核心概念理解、方法应用与独立检查。", 180)


def _block_markdown(block: CourseBlock | None) -> str:
    if block is None:
        return ""
    return str(block.payload.get("markdown") or block.payload.get("text") or block.payload.get("content") or "")


def _code_blocks(markdown: str) -> list[tuple[str, str]]:
    return [
        (str(match.group(1) or "").strip(), str(match.group(2) or "").strip())
        for match in re.finditer(r"```([\w+.-]*)\s*\n(.*?)```", markdown, flags=re.S)
    ]


def _markdown_table(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            if rows:
                break
            continue
        cells = [_plain_text(cell) for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append([_trim(cell, 54) for cell in cells])
    return rows if len(rows) >= 2 else []


def _markdown_bullets(markdown: str) -> list[str]:
    without_code = re.sub(r"```.*?```", "", markdown, flags=re.S)
    items: list[str] = []
    for line in without_code.splitlines():
        match = re.match(r"^\s*(?:[-*+] |\d+[.)]\s+)(.+)$", line)
        if match:
            value = _plain_text(match.group(1))
            if value:
                items.append(value)
    return _unique(items)


def _paragraphs(markdown: str) -> list[str]:
    text = re.sub(r"```.*?```", "", markdown, flags=re.S)
    text = re.sub(r"(?:^|\n)\s*\|.*?\|\s*(?=\n|$)", "\n", text)
    text = re.sub(r"(?:^|\n)\s*(?:[-*+] |\d+[.)]\s+).*$", "\n", text, flags=re.M)
    chunks = re.split(r"\n\s*\n", text)
    result: list[str] = []
    for chunk in chunks:
        value = _plain_text(chunk)
        if len(value) >= 6 and value not in result:
            result.append(value)
    return result


def _plain_text(markdown: str) -> str:
    text = re.sub(r"!\[[^]]*]\([^)]*\)", "", markdown)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _plain_math_text(text)
    text = re.sub(r"[`*_#>]", "", text)
    text = re.sub(r"\s*---+\s*", " ", text)
    return " ".join(text.split()).strip()


def _plain_math_text(value: str) -> str:
    text = str(value or "")
    replacements = {
        "\\times": "×",
        "\\cdot": "·",
        "\\rightarrow": "→",
        "\\leftarrow": "←",
        "\\to": "→",
        "\\in": "∈",
        "\\neq": "≠",
        "\\leq": "≤",
        "\\geq": "≥",
        "\\ldots": "…",
        "\\dots": "…",
        "\\pm": "±",
        "\\notin": "∉",
        "\\approx": "≈",
        "\\equiv": "≡",
        "\\propto": "∝",
        "\\infty": "∞",
        "\\partial": "∂",
        "\\nabla": "∇",
        "\\forall": "∀",
        "\\exists": "∃",
        "\\subset": "⊂",
        "\\subseteq": "⊆",
        "\\supset": "⊃",
        "\\supseteq": "⊇",
        "\\cap": "∩",
        "\\cup": "∪",
        "\\perp": "⟂",
        "\\angle": "∠",
        "\\sum": "∑",
        "\\prod": "∏",
        "\\int": "∫",
        "\\alpha": "α",
        "\\beta": "β",
        "\\gamma": "γ",
        "\\delta": "δ",
        "\\epsilon": "ε",
        "\\theta": "θ",
        "\\lambda": "λ",
        "\\mu": "μ",
        "\\pi": "π",
        "\\rho": "ρ",
        "\\sigma": "σ",
        "\\phi": "φ",
        "\\omega": "ω",
        "\\Delta": "Δ",
        "\\Theta": "Θ",
        "\\Lambda": "Λ",
        "\\Pi": "Π",
        "\\Sigma": "Σ",
        "\\Phi": "Φ",
        "\\Omega": "Ω",
    }
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(source, target)
    subscript_map = str.maketrans("0123456789nijk", "₀₁₂₃₄₅₆₇₈₉ₙᵢⱼₖ")
    superscript_map = str.maketrans("0123456789nT+-", "⁰¹²³⁴⁵⁶⁷⁸⁹ⁿᵀ⁺⁻")
    text = re.sub(
        r"_\{?([0-9nijk]+)\}?",
        lambda match: match.group(1).translate(subscript_map),
        text,
    )
    text = re.sub(
        r"\^\{?([0-9nT+-]+)\}?",
        lambda match: match.group(1).translate(superscript_map),
        text,
    )
    text = re.sub(r"\\mathbb\s*\{R\}", "ℝ", text)
    text = re.sub(r"\\mathbb\s*\{([A-Za-z])\}", r"\1", text)
    text = re.sub(
        r"\\(?:mathbf|mathrm|text|operatorname)\s*\{([^{}]*)\}",
        r"\1",
        text,
    )
    text = re.sub(
        r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r"\1/\2",
        text,
    )
    text = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"√(\1)", text)
    text = re.sub(
        r"\\(?:overline|underline|vec|hat|bar)\s*\{([^{}]*)\}",
        r"\1",
        text,
    )
    text = re.sub(r"(?:\\)?begin\s*\{(?:bmatrix|pmatrix|matrix|cases)\}", "[", text)
    text = re.sub(r"(?:\\)?end\s*\{(?:bmatrix|pmatrix|matrix|cases)\}", "]", text)
    text = text.replace("\\\\", "；").replace("&", ", ")
    text = text.replace("\\left", "").replace("\\right", "")
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    return (
        text.replace("\\[", "")
        .replace("\\]", "")
        .replace("\\(", "")
        .replace("\\)", "")
        .replace("$", "")
        .replace("{", "")
        .replace("}", "")
    )


def _clean_slide_title(value: str) -> str:
    return _plain_text(
        str(value or "")
        .replace("\\times", "×")
        .replace("\\cdot", "·")
        .replace("\\to", "→")
        .replace("$", "")
        .replace("{", "")
        .replace("}", "")
    )


def _first_question(markdown: str) -> str:
    plain = _plain_text(markdown)
    match = re.search(r"([^。！？!?]{6,}[？?])", plain)
    return _trim(match.group(1), 170) if match else ""


def _first_sentence(text: str) -> str:
    value = _plain_text(text)
    parts = re.split(r"(?<=[。！？!?])\s*", value, maxsplit=1)
    return _trim(parts[0] if parts else value, 150)


def _first_meaningful_line(blocks: list[CourseBlock]) -> str:
    for block in blocks:
        value = _block_key_message(block)
        if value:
            return value
    return ""


def _strip_chapter_prefix(title: str) -> str:
    return re.sub(r"^第?\s*\d+\s*[章节]\s*", "", title).strip()


def _strip_section_prefix(title: str) -> str:
    return re.sub(r"^\d+(?:\.\d+)*\s*", "", title).strip()


def _asset_records(course_data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = (course_data.get("learning_assets") or {}).get(key) or []
    if isinstance(value, Mapping):
        value = value.get("items") or []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _first_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, Mapping)), None)
    return None


_ISSUE_SUGGESTIONS = {
    "invalid_slide_deck_contract": "修复缺失或非法字段后重新生成结构化计划。",
    "slide_deck_too_short": "补充至少一个绑定课程来源的正文页。",
    "slide_cover_missing": "在第一页加入 cover 版式封面。",
    "instructional_slide_missing": "加入至少一个带 section_id 和来源绑定的教学页。",
    "duplicate_slide_unit": "为重复页面生成唯一且稳定的 slide_id。",
    "slide_title_missing": "补充能概括本页教学任务的短标题。",
    "slide_source_missing": "补齐 source_section_ids 和 source_block_ids 后重新发布。",
    "unknown_slide_layout": "改用已注册版式或为该版式补充渲染器。",
    "recap_evidence_missing": "为总结卡片补充来自课程的核心知识或能力要点。",
    "raw_markdown_leaked": "把 Markdown 标记转成卡片、要点或表格结构。",
    "raw_latex_leaked": "把 LaTeX 转为可直接显示的数学文本或原生公式文本。",
    "text_encoding_corrupted": "用 UTF-8 重新读取来源并替换乱码后再导出。",
    "paragraph_copy_detected": "把长段落压缩为 3–5 个要点，细节移入 speaker notes。",
    "formal_practice_not_represented": "如需逐节覆盖正式题，请拆分课件；Demo 版保留少量代表性练习即可。",
    "knowledge_binding_missing": "为该页补充正式知识 ID；现有课程块来源可暂时保留。",
    "slide_block_overflow": "减少卡片数量或拆分页面，直到符合版式块容量。",
    "slide_text_overflow": "精简可见文字并把解释细节移入 speaker notes。",
    "slide_item_overflow": "将可见要点压缩到版式允许的数量。",
    "slide_title_too_long": "将标题压缩为一个核心判断，背景信息移入 speaker notes。",
    "slide_key_message_too_long": "只保留一句结论，其余解释移入 speaker notes。",
    "chapter_message_overflow": "把章节主线压缩为一句短判断。",
    "code_insight_overflow": "侧栏最多保留四条短阅读线索。",
    "objective_content_overflow": "缩短目标页问题和能力描述，细节移入备注。",
    "concept_card_overflow": "每张概念卡只保留一个短判断或少量要点。",
    "process_step_overflow": "缩短步骤文字，必要时拆分为两页。",
    "practice_content_overflow": "缩短题干和检查项，答案与讲解移入备注。",
    "practice_check_overflow": "检查区最多保留四项，其余细节移入备注。",
}


def _issue(
    severity: str,
    code: str,
    message: str,
    target: str = "",
    *,
    layout: str = "",
) -> dict[str, Any]:
    slide_id = target or "deck"
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "target": target,
        "slide_id": slide_id,
        "layout": layout,
        "suggestion": _ISSUE_SUGGESTIONS.get(code, "根据问题描述精简或补全该页后重新检查。"),
    }


def _attach_issue_layout(
    issue: dict[str, Any],
    slide_layouts: dict[str, SlideLayout],
) -> dict[str, Any]:
    result = dict(issue)
    slide_id = str(result.get("slide_id") or result.get("target") or "deck")
    result["slide_id"] = slide_id
    if not result.get("layout"):
        result["layout"] = slide_layouts.get(slide_id) or (
            "practice" if result.get("code") == "formal_practice_not_represented" else "deck"
        )
    return result


def _concise_point(value: str, limit: int) -> str:
    """Shorten projected copy at a semantic boundary; details stay in notes."""
    text = " ".join(str(value).split()).strip().strip("\"'“”")
    if len(text) <= limit:
        return text.rstrip("…").rstrip()

    sentence_breaks = ("。", "！", "？", ". ", "! ", "? ")
    clause_breaks = ("；", "; ", "：", ": ", "，", ", ")
    for token in (*sentence_breaks, *clause_breaks):
        index = text.find(token)
        if index < 11 or index >= limit:
            continue
        include_punctuation = token in sentence_breaks
        end = index + (1 if include_punctuation else 0)
        return text[:end].rstrip(" ,，;；:：").strip()

    shortened = text[:limit].rstrip()
    word_boundary = shortened.rfind(" ")
    if word_boundary >= 11:
        shortened = shortened[:word_boundary]
    shortened = shortened.rstrip(" ,，;；:：…").strip()
    dangling_words = {
        "a", "an", "the", "and", "or", "to", "of", "for", "with", "that",
        "which", "in", "on", "at", "by", "from", "as",
    }
    while len(shortened.split()) > 3 and shortened.rsplit(" ", 1)[-1].lower() in dangling_words:
        shortened = shortened.rsplit(" ", 1)[0].rstrip(" ,，;；:：…").strip()
    return shortened


def _trim(value: str, limit: int) -> str:
    text = " ".join(str(value).split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip("，,；;：:。.") + "…"


def _trim_code(value: str, limit: int) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 2)].rstrip() + "\n…"


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _normalize_visible(value: Any) -> str:
    return re.sub(r"\s+", "", _plain_text(str(value or ""))).lower()


__all__ = [
    "LAYOUT_CAPACITY",
    "SLIDE_DECK_COMPILER_VERSION",
    "SLIDE_DECK_SCHEMA",
    "PlannedSlideV1",
    "SlideBlockSpec",
    "SlideDeckContent",
    "SlideDeckPlanV1",
    "SlideSpec",
    "apply_presentation_overrides",
    "compile_slide_deck",
    "plan_slide_deck",
    "slide_quality",
    "validate_slide_deck",
]
