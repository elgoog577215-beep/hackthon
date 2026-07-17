"""Structured, same-source slide planning and deterministic quality gates."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash

SLIDE_DECK_SCHEMA = "slide_deck_v2"
SLIDE_DECK_COMPILER_VERSION = "structured_slide_compiler_v2"
SLIDES_PER_SECTION_MAX = 4

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


class SlideDeckContent(_StrictModel):
    schema_version: Literal["slide_deck_v2"] = SLIDE_DECK_SCHEMA
    title: str
    theme: str = "lingzhi-classroom-v2"
    aspect_ratio: Literal["16:9"] = "16:9"
    slides: list[SlideSpec]
    presentation_overrides: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    override_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    quality_summary: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_slide_order(self) -> SlideDeckContent:
        unit_ids = [slide.unit_id for slide in self.slides]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Slide unit IDs must be unique")
        for index, slide in enumerate(self.slides):
            slide.position = index
        return self


LAYOUT_CAPACITY: dict[str, dict[str, int]] = {
    "cover": {"blocks": 2, "characters": 420, "items": 4},
    "roadmap": {"blocks": 2, "characters": 720, "items": 8},
    "chapter": {"blocks": 2, "characters": 480, "items": 4},
    "objective": {"blocks": 3, "characters": 780, "items": 8},
    "concept": {"blocks": 4, "characters": 900, "items": 10},
    "comparison": {"blocks": 3, "characters": 1100, "items": 12},
    "process": {"blocks": 3, "characters": 950, "items": 8},
    "code": {"blocks": 3, "characters": 1700, "items": 6},
    "misconception": {"blocks": 3, "characters": 850, "items": 8},
    "practice": {"blocks": 3, "characters": 1000, "items": 8},
    "recap": {"blocks": 3, "characters": 720, "items": 8},
}


def compile_slide_deck(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    presentation_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
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
    slides: list[SlideSpec] = []

    def append(slide: SlideSpec) -> None:
        slide.position = len(slides)
        slide.quality = slide_quality(slide)
        slides.append(slide)
        if progress_callback:
            progress_callback({
                "event": "slide_upsert",
                "progress": min(94, 6 + round((len(slides) / max(1, _estimated_slide_count(learning_sections))) * 88)),
                "slide": slide.model_dump(mode="json"),
            })

    if progress_callback:
        progress_callback({"event": "deck_plan", "progress": 4, "title": document.title})

    append(SlideSpec(
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
        source_keys=["course_title"],
    ))

    append(SlideSpec(
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
            items=[_trim(_strip_chapter_prefix(section.title), 42) for section in chapter_sections[:8]],
        )],
        speaker_notes="用章节路线帮助学习者定位当前内容在全课中的作用。",
        source_keys=[f"section_structure:{section.section_id}" for section in chapter_sections[:8]],
    ))

    last_chapter_id = ""
    for section in learning_sections:
        blocks = [block for block in blocks_by_section.get(section.section_id, []) if block.status != "retired"]
        if not blocks:
            continue
        chapter = section_by_id.get(section.parent_section_id or "")
        if chapter and chapter.section_id != last_chapter_id:
            append(_chapter_slide(chapter, section))
            last_chapter_id = chapter.section_id

        context = _merge_block_knowledge(
            knowledge_index.for_section(section.section_id, section),
            blocks,
        )
        if len(blocks) <= 2:
            append(_compact_section_slide(section, blocks, context))
            assessment = _assessment_slide(section, blocks, context, course_data)
            if assessment:
                append(assessment)
            continue

        append(_objective_slide(section, blocks, context))
        selected = _select_instructional_blocks(blocks)
        for selected_index, block in enumerate(selected[:2]):
            append(_slide_for_block(section, block, context, selected_index))

        assessment = _assessment_slide(section, blocks, context, course_data)
        if assessment:
            append(assessment)

    append(_recap_slide(document, learning_sections, knowledge_index))

    content = SlideDeckContent(title=document.title, slides=slides)
    if presentation_overrides:
        content = apply_presentation_overrides(content, presentation_overrides)
    quality = validate_slide_deck(content.model_dump(mode="json"), course_data=course_data)
    content.quality_summary = {
        "passed": quality["passed"],
        "score": quality["score"],
        "semantic_issue_count": len(quality["semantic"]["issues"]),
        "visual_issue_count": len(quality["visual"]["issues"]),
    }
    if progress_callback:
        progress_callback({"event": "slide_quality", "progress": 97, "quality": quality})
    return content.model_dump(mode="json")


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
        return {
            "passed": False,
            "score": 0.0,
            "semantic": {"passed": False, "issues": [{
                "severity": "critical",
                "code": "invalid_slide_deck_contract",
                "message": str(exc),
            }]},
            "visual": {"passed": False, "issues": []},
            "issues": [{"severity": "critical", "code": "invalid_slide_deck_contract", "message": str(exc)}],
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
        if slide.section_id and not (
            slide.source_block_ids
            or slide.source_section_ids
            or slide.source_keys
            or slide.practice_source_revisions
        ):
            semantic_issues.append(_issue("critical", "slide_source_missing", "教学页没有课程来源绑定。", slide.unit_id))
        if slide.layout not in LAYOUT_CAPACITY:
            visual_issues.append(_issue("critical", "unknown_slide_layout", "幻灯片使用了未知版式。", slide.unit_id))
            continue
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
    for section_id in sorted(section_ids - practice_sections):
        semantic_issues.append(_issue(
            "major",
            "formal_practice_not_represented",
            "本节已有正式题目，但课件没有安排对应检查页。",
            section_id,
        ))
    for slide in deck.slides:
        if slide.section_id and not slide.knowledge_refs:
            semantic_issues.append(_issue(
                "minor",
                "knowledge_binding_missing",
                "该页还没有正式知识 ID，当前只能依赖课程块来源。",
                slide.unit_id,
            ))

    all_issues = [*semantic_issues, *visual_issues]
    blocking = [item for item in all_issues if item["severity"] == "critical"]
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
        "slide_count": len(deck.slides),
    }


def slide_quality(slide: SlideSpec) -> dict[str, Any]:
    issues = [*_capacity_issues(slide), *_layout_content_issues(slide)]
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
    knowledge = context["knowledge_labels"][:4]
    abilities = context["ability_labels"][:3]
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
    return SlideSpec(
        unit_id=f"slide:{section.section_id}",
        position=0,
        layout="objective",
        slide_purpose="learning_objective",
        eyebrow="本节任务",
        title=section.title,
        key_message=_trim(section.learning_objective or problem or section.title, 150),
        blocks=slide_blocks,
        speaker_notes=f"本页只用于建立问题与验收标准，不在此展开正文。目标：{section.learning_objective}",
        section_id=section.section_id,
        source_keys=[
            f"section_structure:{section.section_id}",
            *([f"objective:{section.objective_id}"] if section.objective_id else []),
        ],
        source_block_ids=[objective_block.block_id] if objective_block else [],
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
        [item for values in parsed for item in values][:4],
    )
    return SlideSpec(
        unit_id=f"slide:{section.section_id}",
        position=0,
        layout=layout,
        slide_purpose="concept_and_reasoning",
        eyebrow="核心教学",
        title=section.title,
        key_message=_trim(section.learning_objective or _first_meaningful_line(blocks), 150),
        blocks=slide_blocks,
        speaker_notes=f"围绕本节目标讲清概念并检查理解：{section.learning_objective or section.title}",
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
    title = str(block.payload.get("title") or section.title).strip()
    return SlideSpec(
        unit_id=f"slide:{section.section_id}:{block.role}:{index + 1}",
        position=0,
        layout=layout,
        slide_purpose=block.role,
        eyebrow=purpose_labels.get(block.role, "核心教学"),
        title=_trim(title, 48),
        key_message=_trim(_block_key_message(block), 150),
        blocks=blocks,
        speaker_notes=_speaker_notes(block, section),
        section_id=section.section_id,
        source_block_ids=[block.block_id],
        learning_objective_ids=list(block.objective_refs),
        **_context_refs(context),
    )


def _assessment_slide(
    section: CourseSection,
    blocks: list[CourseBlock],
    context: dict[str, list[str]],
    course_data: dict[str, Any],
) -> SlideSpec | None:
    questions = [
        item for item in _asset_records(course_data, "questions")
        if str(item.get("node_id") or "") == section.section_id
    ]
    misconceptions = context["misconception_labels"]
    action_block = next((block for block in blocks if block.role in {"activity", "checkpoint"}), None)
    if not (questions or misconceptions or action_block):
        return None
    slide_blocks: list[SlideBlockSpec] = []
    practice_ids: list[str] = []
    practice_revisions: dict[str, str] = {}
    source_blocks: list[str] = []
    if questions:
        question = questions[0]
        prompt = str(question.get("prompt") or question.get("question") or "").strip()
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
    elif action_block:
        source_blocks.append(action_block.block_id)
        slide_blocks.extend(_block_to_slide_blocks(action_block)[:1])
    if misconceptions:
        slide_blocks.append(SlideBlockSpec(
            block_id=f"slide:{section.section_id}:misconceptions",
            type="misconception",
            title="作答前检查",
            items=[_trim(item, 38) for item in misconceptions[:3]],
        ))
    return SlideSpec(
        unit_id=f"slide:{section.section_id}:check",
        position=0,
        layout="practice",
        slide_purpose="mastery_check",
        eyebrow="理解检查",
        title=f"你能独立完成吗：{_strip_section_prefix(section.title)}",
        key_message=_trim(section.learning_objective or "用一个可回答的任务验证是否真正理解。", 150),
        blocks=slide_blocks,
        speaker_notes="先让学习者作答，再显示判断标准；不要把答案与题目同时展示。",
        section_id=section.section_id,
        source_keys=[f"section_structure:{section.section_id}"] if not source_blocks else [],
        source_block_ids=source_blocks,
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
                items=_unique(labels)[:4],
            ),
            SlideBlockSpec(
                block_id="slide:recap:ability",
                type="bullets",
                title="可观察能力",
                items=_unique(abilities)[:4],
            ),
        ],
        speaker_notes="最后不要重复目录，而要让学习者说明自己现在能独立完成什么。",
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
                    "knowledge_labels": [_trim(str(self.points.get(key, {}).get("name") or key), 42) for key in knowledge_refs],
                    "ability_labels": [
                        _trim(str(self.skills.get(key, {}).get("observable_behavior") or self.skills.get(key, {}).get("name") or key), 62)
                        for key in ability_refs
                    ],
                    "misconception_labels": [
                        _trim(str(self.mistakes.get(key, {}).get("observable_error_pattern") or self.mistakes.get(key, {}).get("name") or key), 72)
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
        knowledge_labels = [_trim(str(item.get("local_name") or ""), 42) for item in mappings if item.get("local_name")]
        ability_labels = [_trim(str(item.get("local_capability") or ""), 62) for item in mappings if item.get("local_capability")]
        if not knowledge_labels:
            for group in section.attributes.get("knowledge_structure") or []:
                for point in group.get("knowledge_points") or []:
                    if point.get("name"):
                        knowledge_labels.append(_trim(str(point["name"]), 42))
                    if point.get("capability"):
                        ability_labels.append(_trim(str(point["capability"]), 62))
        misconception_labels = [
            _trim(str(item), 72) for item in section.attributes.get("misconceptions") or [] if str(item).strip()
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
    code_blocks = _code_blocks(markdown)
    table = _markdown_table(markdown)
    bullets = _markdown_bullets(markdown)
    paragraphs = _paragraphs(markdown)
    result: list[SlideBlockSpec] = []
    title = str(block.payload.get("title") or "").strip()

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
    result = [block.model_copy(deep=True) for block in blocks]
    if layout == "code":
        code = next((block for block in result if block.type == "code"), None)
        insights = _unique([
            value
            for block in result if block.type != "code"
            for value in (block.items or [block.content])
            if value
        ])
        fitted = [code] if code else []
        if insights:
            fitted.append(SlideBlockSpec(
                block_id=f"{code.block_id if code else 'slide'}:insights",
                type="bullets",
                title="阅读线索",
                items=[_trim(value, 54) for value in insights[:4]],
            ))
        return fitted
    for block in result:
        if layout == "process" and block.items:
            block.items = [_trim(value, 48) for value in block.items[:5]]
        elif layout == "concept":
            block.content = _trim(block.content, 150)
            block.items = [_trim(value, 58) for value in block.items[:5]]
        elif layout == "practice":
            if block.type == "exercise":
                block.content = _trim(block.content, 220)
                block.items = [_trim(value, 52) for value in block.items[:4]]
            elif block.type == "misconception":
                block.content = _trim(block.content, 90)
                block.items = [_trim(value, 38) for value in block.items[:3]]
        elif layout == "objective":
            block.content = _trim(block.content, 110 if block.type != "callout" else 84)
            block.items = [_trim(value, 58) for value in block.items[:4]]
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
        len(block.content) > (84 if block.type == "callout" else 110)
        or any(len(item) > 58 for item in block.items)
        for block in visible_blocks
    ):
        issues.append(_issue("critical", "objective_content_overflow", "目标页内容超过左右栏容量。", slide.unit_id))
    if slide.layout == "concept" and any(
        len(block.content) > 150 or any(len(item) > 58 for item in block.items)
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
            len(block.content) > 90 or any(len(item) > 38 for item in block.items)
        ))
        for block in visible_blocks
    ):
        issues.append(_issue("critical", "practice_content_overflow", "练习页题目或检查项超过实际容量。", slide.unit_id))
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


def _block_key_message(block: CourseBlock) -> str:
    summary = _plain_text(str(block.payload.get("summary") or ""))
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
    return max(4, 3 + len(sections) * 3)


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
    text = re.sub(r"[`*_#>]", "", text)
    text = re.sub(r"\s*---+\s*", " ", text)
    return " ".join(text.split()).strip()


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


def _issue(severity: str, code: str, message: str, target: str = "") -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "target": target}


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


__all__ = [
    "LAYOUT_CAPACITY",
    "SLIDE_DECK_COMPILER_VERSION",
    "SLIDE_DECK_SCHEMA",
    "SlideBlockSpec",
    "SlideDeckContent",
    "SlideSpec",
    "apply_presentation_overrides",
    "compile_slide_deck",
    "slide_quality",
    "validate_slide_deck",
]
