"""Course-logic-first story planning and scene compilation for slide_deck_v4."""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from course_teaching_plan_projection import project_course_teaching_plan
from slide_deck_v3 import (
    ContentFragmentV1,
    SlideDeckMode,
    SlideDeckTheme,
    _paginate_fragments,
)
from slide_layout_registry import (
    LayoutSelectionV2,
    SlideSceneKind,
    registry_summary_v2,
    select_layout_v2,
)

SLIDE_STORY_PLAN_V2_SCHEMA = "slide_story_plan_v2"
SLIDE_STORY_ENGINE_V2_VERSION = "course_logic_story_engine_v2.2"
STORY_BEAT_TEXT_CAPACITY = 230

ClaimSourceKind = Literal[
    "learning_objective",
    "knowledge_statement",
    "teaching_purpose",
    "source_heading",
    "source_sentence",
]


class SlideStoryPlanPrerequisiteError(ValueError):
    """Raised when a course does not have the official inputs required for v4."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StorySourceRevisionsV2(_StrictModel):
    course_document_revision: str
    teaching_plan_revision: str
    knowledge_base_revision: str
    coherence_contract_revision: str


class ClaimSourceV2(_StrictModel):
    kind: ClaimSourceKind
    text: str
    fragment_id: str = ""
    knowledge_id: str = ""
    module_id: str = ""
    objective_id: str = ""


class StoryBeatV2(_StrictModel):
    beat_id: str
    beat_role: str
    teaching_job: str
    primary_claim_source: ClaimSourceV2
    fragment_ids: list[str] = Field(default_factory=list)
    transition_from: str = ""
    reveal_index: int = Field(default=0, ge=0)
    evidence_kinds: list[str] = Field(default_factory=list)
    layout_intent: str
    renderer_layout: str
    layout_family: str
    layout_selection_reason: str
    density: Literal["primary", "alternate", "dense"] = "primary"
    knowledge_refs: list[str] = Field(default_factory=list)
    prerequisite_refs: list[str] = Field(default_factory=list)
    mastery_criterion_refs: list[str] = Field(default_factory=list)


class TeachingEpisodeV2(_StrictModel):
    episode_id: str
    scene_kind: SlideSceneKind
    teaching_job: str
    knowledge_refs: list[str] = Field(default_factory=list)
    capability_refs: list[str] = Field(default_factory=list)
    misconception_refs: list[str] = Field(default_factory=list)
    mastery_criterion_refs: list[str] = Field(default_factory=list)
    beats: list[StoryBeatV2] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reveal_order(self) -> "TeachingEpisodeV2":
        if self.scene_kind not in {"worked_example", "practice_feedback"}:
            return self
        roles = [beat.beat_role for beat in self.beats]
        if not roles or roles[0] != "prompt":
            raise ValueError(f"{self.scene_kind} must start with a prompt beat")
        answer_indexes = [
            index
            for index, role in enumerate(roles)
            if role in {"solution", "answer", "feedback", "validation"}
        ]
        if answer_indexes and min(answer_indexes) == 0:
            raise ValueError(f"{self.scene_kind} cannot reveal an answer on the prompt beat")
        return self


class ChapterStoryV2(_StrictModel):
    chapter_id: str
    title: str
    driving_question: str
    learning_objective: str
    owned_knowledge_ids: list[str] = Field(default_factory=list)
    reused_knowledge_names: list[str] = Field(default_factory=list)
    prerequisite_knowledge_names: list[str] = Field(default_factory=list)
    next_chapter_id: str = ""
    episodes: list[TeachingEpisodeV2] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_entry_and_closure(self) -> "ChapterStoryV2":
        if self.episodes[0].scene_kind != "chapter_entry":
            raise ValueError("Every chapter story must start with chapter_entry")
        if self.episodes[-1].scene_kind != "chapter_recap":
            raise ValueError("Every chapter story must end with chapter_recap")
        return self


class CommunicationBriefV2(_StrictModel):
    audience: str
    course_goal: str
    central_question: str
    expected_learning_results: list[str] = Field(default_factory=list)


class SlideStoryPlanV2(_StrictModel):
    schema_version: Literal["slide_story_plan_v2"] = SLIDE_STORY_PLAN_V2_SCHEMA
    plan_id: str
    mode: SlideDeckMode
    theme: SlideDeckTheme
    communication_brief: CommunicationBriefV2
    source_revisions: StorySourceRevisionsV2
    chapters: list[ChapterStoryV2] = Field(min_length=1)
    planner: Literal["ai", "deterministic_fallback"] = "deterministic_fallback"
    fallback_reason: str = ""


_SCENE_ORDER: tuple[SlideSceneKind, ...] = (
    "chapter_entry",
    "prerequisite_activation",
    "concept",
    "reasoning",
    "method",
    "worked_example",
    "practice_feedback",
    "misconception",
    "application",
    "chapter_recap",
)

_ROLE_TO_SCENE: dict[str, SlideSceneKind] = {
    "orientation": "chapter_entry",
    "objective": "chapter_entry",
    "prerequisite": "prerequisite_activation",
    "concept": "concept",
    "reasoning": "reasoning",
    "method": "method",
    "example": "worked_example",
    "answer": "worked_example",
    "activity": "practice_feedback",
    "checkpoint": "practice_feedback",
    "feedback": "practice_feedback",
    "misconception": "misconception",
    "counterexample": "misconception",
    "remediation": "misconception",
    "application": "application",
    "transfer": "application",
    "summary": "chapter_recap",
}


def _course_logic_inputs(
    course_data: dict[str, Any],
) -> tuple[dict[str, Any], StorySourceRevisionsV2]:
    projection = project_course_teaching_plan(course_data)
    if (
        projection.get("status") != "completed"
        or not projection.get("revision_id")
        or not projection.get("sections")
    ):
        raise SlideStoryPlanPrerequisiteError(
            "slide_deck_v4 requires a completed official course teaching plan"
        )
    knowledge_base = course_data.get("course_knowledge_base") or {}
    if (
        not isinstance(knowledge_base, dict)
        or knowledge_base.get("lifecycle_status") != "active"
        or not knowledge_base.get("revision_id")
    ):
        raise SlideStoryPlanPrerequisiteError(
            "slide_deck_v4 requires an active official course knowledge base"
        )
    coherence_contract = course_data.get("course_coherence_contract") or {}
    if (
        not isinstance(coherence_contract, dict)
        or coherence_contract.get("status") != "active"
        or not coherence_contract.get("revision_id")
        or (coherence_contract.get("quality_report") or {}).get("passed") is False
    ):
        raise SlideStoryPlanPrerequisiteError(
            "slide_deck_v4 requires an active course coherence contract"
        )
    revisions = StorySourceRevisionsV2(
        course_document_revision=str(course_data.get("course_revision") or ""),
        teaching_plan_revision=str(projection["revision_id"]),
        knowledge_base_revision=str(
            knowledge_base.get("revision_id")
            or ""
        ),
        coherence_contract_revision=str(
            coherence_contract.get("revision_id")
            or ""
        ),
    )
    return projection, revisions


def course_supports_slide_deck_v4(course_data: dict[str, Any]) -> bool:
    try:
        _course_logic_inputs(course_data)
    except SlideStoryPlanPrerequisiteError:
        return False
    return True


def slide_deck_v4_prerequisite_issues(
    course_data: dict[str, Any],
) -> list[str]:
    try:
        _course_logic_inputs(course_data)
    except SlideStoryPlanPrerequisiteError as exc:
        return [str(exc)]
    return []


def resolve_slide_deck_schema(
    course_data: dict[str, Any],
    *,
    story_engine_enabled: bool,
    v5_enabled: bool = True,
) -> Literal["slide_deck_v3", "slide_deck_v4", "slide_deck_v5"]:
    """Select the requested engine without silently degrading an enabled V5 build."""
    if not story_engine_enabled:
        return "slide_deck_v3"
    _course_logic_inputs(course_data)
    return "slide_deck_v5" if v5_enabled else "slide_deck_v4"


def _chapter_for_section(
    section: CourseSection,
    sections_by_id: dict[str, CourseSection],
) -> str:
    current = section
    seen: set[str] = set()
    while current.parent_section_id and current.section_id not in seen:
        seen.add(current.section_id)
        parent = sections_by_id.get(current.parent_section_id)
        if parent is None:
            break
        current = parent
    return current.section_id


def _block_module_id(block: CourseBlock) -> str:
    return str(
        block.payload.get("module_id")
        or block.payload.get("module_instance_id")
        or ""
    )


def _module_scene(module: dict[str, Any]) -> SlideSceneKind | None:
    value = " ".join([
        str(module.get("module_id") or ""),
        str(module.get("teaching_purpose") or ""),
        str(module.get("teaching_guidance") or ""),
    ]).lower()
    rules: tuple[tuple[tuple[str, ...], SlideSceneKind], ...] = (
        (("先修", "唤醒", "prerequisite", "recall"), "prerequisite_activation"),
        (("例题", "示例", "worked", "demonstration", "example"), "worked_example"),
        (("练习", "检查", "反馈", "掌握", "practice", "feedback", "mastery"), "practice_feedback"),
        (("误区", "反例", "纠错", "misconception", "counterexample"), "misconception"),
        (("应用", "迁移", "情境", "application", "transfer"), "application"),
        (("证明", "推导", "原理", "reasoning", "derivation"), "reasoning"),
        (("方法", "步骤", "算法", "method", "procedure"), "method"),
        (("总结", "回顾", "recap", "summary"), "chapter_recap"),
        (("定义", "概念", "边界", "concept", "definition"), "concept"),
        (("目标", "导入", "问题", "objective", "orientation"), "chapter_entry"),
    )
    for keywords, scene in rules:
        if any(keyword in value for keyword in keywords):
            return scene
    return None


def _fragment_claim(fragment: ContentFragmentV1) -> ClaimSourceV2:
    return ClaimSourceV2(
        kind="source_heading" if fragment.kind == "heading" else "source_sentence",
        text=fragment.text,
        fragment_id=fragment.fragment_id,
    )


def _knowledge_catalog(section_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        point
        for group in section_plan.get("knowledge_structure") or []
        for point in group.get("knowledge_points") or []
    ]


def _merge_section_plans(
    section_plans: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "node_id": str(section_plans[0].get("node_id") or "") if section_plans else "",
        "knowledge_structure": [
            group
            for section in section_plans
            for group in section.get("knowledge_structure") or []
        ],
        "key_points": list(dict.fromkeys(
            str(item)
            for section in section_plans
            for item in section.get("key_points") or []
            if str(item)
        )),
        "reused_knowledge_names": list(dict.fromkeys(
            str(item)
            for section in section_plans
            for item in section.get("reused_knowledge_names") or []
            if str(item)
        )),
        "knowledge_relations": [
            relation
            for section in section_plans
            for relation in section.get("knowledge_relations") or []
        ],
        "teaching_modules": [
            module
            for section in section_plans
            for module in section.get("teaching_modules") or []
        ],
    }


def _claim_for_scene(
    *,
    scene: SlideSceneKind,
    chapter: CourseSection,
    section_plan: dict[str, Any],
    fragments: list[ContentFragmentV1],
    module: dict[str, Any] | None,
) -> ClaimSourceV2:
    if scene in {"chapter_entry", "chapter_recap"} and chapter.learning_objective:
        return ClaimSourceV2(
            kind="learning_objective",
            text=chapter.learning_objective,
            objective_id=chapter.objective_id,
        )
    if fragments:
        heading = next((item for item in fragments if item.kind == "heading"), fragments[0])
        return _fragment_claim(heading)
    knowledge = _knowledge_catalog(section_plan)
    if knowledge:
        statement = str(knowledge[0].get("statement") or "").strip()
        if statement:
            return ClaimSourceV2(
                kind="knowledge_statement",
                text=statement,
                knowledge_id=str(knowledge[0].get("knowledge_id") or ""),
            )
    if module:
        teaching_purpose = str(module.get("teaching_purpose") or "").strip()
        if teaching_purpose:
            return ClaimSourceV2(
                kind="teaching_purpose",
                text=teaching_purpose,
                module_id=str(module.get("module_id") or ""),
            )
    if chapter.title:
        return ClaimSourceV2(kind="source_heading", text=chapter.title)
    raise ValueError(f"Cannot derive an official claim source for scene {scene}")


def _fragment_evidence(fragments: list[ContentFragmentV1]) -> list[str]:
    kinds = {
        {
            "paragraph": "text",
            "heading": "text",
            "list_item": "list",
        }.get(item.kind, item.kind)
        for item in fragments
    }
    return sorted(kinds or {"text"})


def _split_prompt_and_answer(
    scene: SlideSceneKind,
    blocks: list[CourseBlock],
    fragments_by_block: dict[str, list[ContentFragmentV1]],
) -> list[tuple[str, list[ContentFragmentV1]]]:
    prompt_roles = {"example"} if scene == "worked_example" else {"activity", "checkpoint"}
    answer_roles = {"answer", "feedback", "remediation"}
    prompts: list[ContentFragmentV1] = []
    answers: list[ContentFragmentV1] = []
    rest: list[ContentFragmentV1] = []
    for block in blocks:
        items = fragments_by_block.get(block.block_id, [])
        raw_role = str(block.payload.get("role") or block.role)
        title = str(block.payload.get("title") or "")
        is_answer = raw_role in answer_roles or any(
            marker in title.lower()
            for marker in ("答案", "解答", "反馈", "solution", "answer")
        )
        if is_answer:
            answers.extend(items)
        elif raw_role in prompt_roles:
            prompts.extend(items)
        else:
            rest.extend(items)
    if not prompts and rest:
        prompts = rest[:1]
        rest = rest[1:]
    answers = rest + answers
    result = [("prompt", prompts)]
    if answers:
        result.append(("solution" if scene == "worked_example" else "feedback", answers))
    return result


def _select_fragment_layout(
    *,
    scene: SlideSceneKind,
    fragments: list[ContentFragmentV1],
    theme: SlideDeckTheme,
    recent_layout_families: list[str],
) -> LayoutSelectionV2:
    return select_layout_v2(
        scene_kind=scene,
        evidence_kinds=_fragment_evidence(fragments),
        character_count=sum(len(item.text) for item in fragments),
        item_count=sum(item.kind == "list_item" for item in fragments),
        theme=theme,
        recent_layout_families=recent_layout_families,
    )


def _select_capacity_safe_beat_groups(
    *,
    scene: SlideSceneKind,
    beat_groups: list[tuple[str, list[ContentFragmentV1]]],
    theme: SlideDeckTheme,
    recent_layout_families: list[str],
) -> list[tuple[str, list[ContentFragmentV1], LayoutSelectionV2]]:
    """Split source-ordered beat groups before assigning a capacity-safe layout."""
    selected_groups: list[
        tuple[str, list[ContentFragmentV1], LayoutSelectionV2]
    ] = []
    for role, fragments in beat_groups:
        fragment_groups = (
            _paginate_fragments(fragments, STORY_BEAT_TEXT_CAPACITY)
            if fragments
            else [[]]
        )
        for fragment_group in fragment_groups:
            selection = _select_fragment_layout(
                scene=scene,
                fragments=fragment_group,
                theme=theme,
                recent_layout_families=recent_layout_families,
            )
            selected_groups.append((role, fragment_group, selection))
            recent_layout_families.append(selection.layout_family)
    return selected_groups


def _make_episode(
    *,
    scene: SlideSceneKind,
    chapter: CourseSection,
    section_plan: dict[str, Any],
    blocks: list[CourseBlock],
    fragments: list[ContentFragmentV1],
    fragments_by_block: dict[str, list[ContentFragmentV1]],
    module: dict[str, Any] | None,
    recent_layout_families: list[str],
    theme: SlideDeckTheme,
) -> TeachingEpisodeV2:
    knowledge = _knowledge_catalog(section_plan)
    knowledge_refs = [
        str(item.get("knowledge_id") or "")
        for item in knowledge
        if str(item.get("knowledge_id") or "")
    ]
    capability_refs = [
        str(capability.get("capability_id") or "")
        for item in knowledge
        for capability in item.get("capability_points") or []
        if str(capability.get("capability_id") or "")
    ]
    misconception_refs = [
        str(misconception.get("misconception_id") or "")
        for item in knowledge
        for misconception in item.get("misconceptions") or []
        if str(misconception.get("misconception_id") or "")
    ]
    mastery_refs = [
        str(criterion.get("criterion_id") or "")
        for item in knowledge
        for criterion in item.get("mastery_criteria") or []
        if str(criterion.get("criterion_id") or "")
    ]
    prerequisite_refs = sorted({
        str(name)
        for item in knowledge
        for name in item.get("prerequisite_names") or []
        if str(name)
    })
    episode_id = stable_hash({
        "chapter": chapter.section_id,
        "scene": scene,
        "module": (module or {}).get("module_id"),
        "fragments": [item.fragment_id for item in fragments],
    }, prefix="episode_")
    if scene in {"worked_example", "practice_feedback"}:
        beat_groups = _split_prompt_and_answer(scene, blocks, fragments_by_block)
    else:
        beat_groups = [(
            {
                "chapter_entry": "driving_question",
                "prerequisite_activation": "recall",
                "concept": "formal_explanation",
                "reasoning": "reasoning_step",
                "method": "procedure",
                "misconception": "repair",
                "application": "mapping",
                "chapter_recap": "closure",
            }[scene],
            fragments,
        )]
    selected_beat_groups = _select_capacity_safe_beat_groups(
        scene=scene,
        beat_groups=beat_groups,
        theme=theme,
        recent_layout_families=recent_layout_families,
    )
    beats: list[StoryBeatV2] = []
    transition = ""
    for index, (role, beat_fragments, selection) in enumerate(
        selected_beat_groups
    ):
        claim = _claim_for_scene(
            scene=scene,
            chapter=chapter,
            section_plan=section_plan,
            fragments=beat_fragments or fragments,
            module=module,
        )
        evidence = _fragment_evidence(beat_fragments)
        character_count = sum(len(item.text) for item in beat_fragments)
        beat_id = stable_hash({
            "episode_id": episode_id,
            "role": role,
            "index": index,
            "fragments": [item.fragment_id for item in beat_fragments],
        }, prefix="beat_")
        beats.append(StoryBeatV2(
            beat_id=beat_id,
            beat_role=role,
            teaching_job=_teaching_job(scene, role),
            primary_claim_source=claim,
            fragment_ids=[item.fragment_id for item in beat_fragments],
            transition_from=transition,
            reveal_index=index,
            evidence_kinds=evidence,
            layout_intent=selection.layout_id,
            renderer_layout=selection.renderer_layout,
            layout_family=selection.layout_family,
            layout_selection_reason=selection.reason,
            density="dense" if character_count > 650 else (
                "alternate" if index % 2 else "primary"
            ),
            knowledge_refs=knowledge_refs,
            prerequisite_refs=prerequisite_refs,
            mastery_criterion_refs=mastery_refs,
        ))
        transition = beat_id
    return TeachingEpisodeV2(
        episode_id=episode_id,
        scene_kind=scene,
        teaching_job=_teaching_job(scene, ""),
        knowledge_refs=knowledge_refs,
        capability_refs=capability_refs,
        misconception_refs=misconception_refs,
        mastery_criterion_refs=mastery_refs,
        beats=beats,
    )


def _teaching_job(scene: SlideSceneKind, role: str) -> str:
    jobs = {
        "chapter_entry": "建立本章驱动问题并明确学习目标",
        "prerequisite_activation": "唤醒完成本章任务所需的前置知识",
        "concept": "建立正式概念并说明条件边界",
        "reasoning": "沿来源顺序解释结论如何成立",
        "method": "把知识转化为可执行的方法",
        "worked_example": "用完整例题展示策略、求解与验证",
        "practice_feedback": "检查理解并依据掌握标准反馈",
        "misconception": "定位错误路径并给出来源支持的修复",
        "application": "把知识映射到课程已有的应用情境",
        "chapter_recap": "关闭本章目标并连接后续学习",
    }
    if role == "prompt":
        return "只呈现题目、已知与目标，保留思考空间"
    if role == "solution":
        return "按来源顺序揭示例题求解与验证"
    if role == "feedback":
        return "在练习之后揭示答案、反馈与掌握判断"
    return jobs[scene]


def compile_slide_story_plan_v2(
    document: CourseDocument,
    course_data: dict[str, Any],
    fragments: list[ContentFragmentV1],
    *,
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
) -> SlideStoryPlanV2:
    projection, revisions = _course_logic_inputs(course_data)
    revisions.course_document_revision = document.document_revision
    sections_by_id = {section.section_id: section for section in document.sections}
    blocks_by_chapter: dict[str, list[CourseBlock]] = defaultdict(list)
    for block in sorted(document.blocks, key=lambda item: item.position):
        section = sections_by_id.get(block.section_id)
        if section is None:
            continue
        blocks_by_chapter[_chapter_for_section(section, sections_by_id)].append(block)
    fragments_by_block: dict[str, list[ContentFragmentV1]] = defaultdict(list)
    for fragment in sorted(fragments, key=lambda item: item.ordinal):
        fragments_by_block[fragment.block_id].append(fragment)
    plan_by_section = {
        str(section.get("node_id") or ""): section
        for section in projection.get("sections") or []
    }
    chapters = [
        section
        for section in sorted(document.sections, key=lambda item: item.position)
        if section.parent_section_id is None
    ]
    stories: list[ChapterStoryV2] = []
    for chapter_index, chapter in enumerate(chapters):
        chapter_section_ids = {
            section.section_id
            for section in document.sections
            if _chapter_for_section(section, sections_by_id) == chapter.section_id
        }
        chapter_plan_sections = [
            plan_by_section[section.section_id]
            for section in sorted(document.sections, key=lambda item: item.position)
            if section.section_id in chapter_section_ids
            and section.section_id in plan_by_section
        ]
        if not chapter_plan_sections:
            raise SlideStoryPlanPrerequisiteError(
                f"Teaching plan has no section contract for chapter {chapter.section_id}"
            )
        section_plan = _merge_section_plans(chapter_plan_sections)
        first_objective_section = next(
            (
                section for section in sorted(document.sections, key=lambda item: item.position)
                if section.section_id in chapter_section_ids
                and section.learning_objective
            ),
            None,
        )
        story_chapter = chapter.model_copy(update={
            "learning_objective": (
                chapter.learning_objective
                or (
                    first_objective_section.learning_objective
                    if first_objective_section
                    else ""
                )
            ),
            "objective_id": (
                chapter.objective_id
                or (
                    first_objective_section.objective_id
                    if first_objective_section
                    else ""
                )
            ),
        })
        chapter_blocks = blocks_by_chapter.get(chapter.section_id, [])
        modules = list(section_plan.get("teaching_modules") or [])
        modules_by_id = {
            str(module.get("module_id") or ""): module
            for module in modules
            if str(module.get("module_id") or "")
        }
        scene_blocks: dict[SlideSceneKind, list[CourseBlock]] = defaultdict(list)
        scene_modules: dict[SlideSceneKind, dict[str, Any]] = {}
        for module in modules:
            scene = _module_scene(module)
            if scene:
                scene_modules.setdefault(scene, module)
        for block in chapter_blocks:
            module = modules_by_id.get(_block_module_id(block))
            block_role = str(block.payload.get("role") or block.role)
            role_scene = _ROLE_TO_SCENE.get(block_role)
            scene = (
                role_scene
                if role_scene and block_role != "concept"
                else (_module_scene(module) if module else None) or role_scene or "concept"
            )
            scene_blocks[scene].append(block)
        scene_blocks.setdefault("chapter_entry", [])
        scene_blocks.setdefault("chapter_recap", [])
        knowledge = _knowledge_catalog(section_plan)
        if any(item.get("prerequisite_names") for item in knowledge) or section_plan.get(
            "reused_knowledge_names"
        ):
            scene_blocks.setdefault("prerequisite_activation", [])
        if any(item.get("misconceptions") for item in knowledge):
            scene_blocks.setdefault("misconception", [])
        if any(item.get("mastery_criteria") for item in knowledge):
            scene_blocks.setdefault("practice_feedback", [])
        recent_layout_families: list[str] = []
        episodes: list[TeachingEpisodeV2] = []
        for scene in _SCENE_ORDER:
            if scene not in scene_blocks:
                continue
            blocks = scene_blocks[scene]
            scene_fragments = sorted(
                (
                    fragment
                    for block in blocks
                    for fragment in fragments_by_block.get(block.block_id, [])
                ),
                key=lambda item: item.ordinal,
            )
            if scene not in {"chapter_entry", "chapter_recap", "prerequisite_activation"} and not (
                blocks or scene_modules.get(scene)
            ):
                continue
            episodes.append(_make_episode(
                scene=scene,
                chapter=story_chapter,
                section_plan=section_plan,
                blocks=blocks,
                fragments=scene_fragments,
                fragments_by_block=fragments_by_block,
                module=scene_modules.get(scene),
                recent_layout_families=recent_layout_families,
                theme=theme,
            ))
        if mode == "concise":
            required = {
                "chapter_entry",
                "concept",
                "method",
                "worked_example",
                "practice_feedback",
                "chapter_recap",
            }
            evidence_fallback = next(
                (
                    episode for episode in episodes
                    if episode.scene_kind in {"reasoning", "application"}
                ),
                None,
            )
            concise_episodes = [
                episode for episode in episodes
                if episode.scene_kind in required
            ]
            if not any(
                episode.scene_kind == "worked_example"
                for episode in concise_episodes
            ) and evidence_fallback is not None:
                recap_index = next(
                    (
                        index for index, episode in enumerate(concise_episodes)
                        if episode.scene_kind == "chapter_recap"
                    ),
                    len(concise_episodes),
                )
                concise_episodes.insert(recap_index, evidence_fallback)
            episodes = concise_episodes
        knowledge_ids = [
            str(item.get("knowledge_id") or "")
            for item in knowledge
            if str(item.get("knowledge_id") or "")
        ]
        prerequisite_names = sorted({
            str(name)
            for item in knowledge
            for name in item.get("prerequisite_names") or []
            if str(name)
        })
        objective = story_chapter.learning_objective or (
            str((section_plan.get("key_points") or [""])[0])
        )
        stories.append(ChapterStoryV2(
            chapter_id=chapter.section_id,
            title=chapter.title,
            driving_question=objective or chapter.title,
            learning_objective=objective,
            owned_knowledge_ids=knowledge_ids,
            reused_knowledge_names=[
                str(item)
                for item in section_plan.get("reused_knowledge_names") or []
                if str(item)
            ],
            prerequisite_knowledge_names=prerequisite_names,
            next_chapter_id=(
                chapters[chapter_index + 1].section_id
                if chapter_index + 1 < len(chapters)
                else ""
            ),
            episodes=episodes,
        ))
    brief = CommunicationBriefV2(
        audience=str(course_data.get("target_audience") or "课程学习者"),
        course_goal=str(course_data.get("course_goal") or document.title),
        central_question=stories[0].driving_question,
        expected_learning_results=[
            item.learning_objective for item in stories if item.learning_objective
        ],
    )
    payload = {
        "mode": mode,
        "theme": theme,
        "sources": revisions.model_dump(mode="json"),
        "chapters": [item.model_dump(mode="json") for item in stories],
    }
    return SlideStoryPlanV2(
        plan_id=stable_hash(payload, prefix="story_"),
        mode=mode,
        theme=theme,
        communication_brief=brief,
        source_revisions=revisions,
        chapters=stories,
    )


def validate_ai_story_plan_v2(
    candidate: SlideStoryPlanV2,
    *,
    fallback: SlideStoryPlanV2,
    course_data: dict[str, Any],
    fragments: list[ContentFragmentV1],
) -> None:
    if candidate.mode != fallback.mode or candidate.theme != fallback.theme:
        raise ValueError("AI story plan changed the requested variant")
    if candidate.source_revisions != fallback.source_revisions:
        raise ValueError("AI story plan changed official source revisions")
    if [item.chapter_id for item in candidate.chapters] != [
        item.chapter_id for item in fallback.chapters
    ]:
        raise ValueError("AI story plan changed the official chapter order")
    catalog = {item.fragment_id: item for item in fragments}
    projection = project_course_teaching_plan(course_data)
    official_claims: dict[str, set[str]] = {
        "learning_objective": {
            chapter.learning_objective
            for chapter in fallback.chapters
            if chapter.learning_objective
        },
        "knowledge_statement": {
            str(point.get("statement") or "")
            for section in projection.get("sections") or []
            for group in section.get("knowledge_structure") or []
            for point in group.get("knowledge_points") or []
            if str(point.get("statement") or "")
        },
        "teaching_purpose": {
            str(module.get("teaching_purpose") or "")
            for section in projection.get("sections") or []
            for module in section.get("teaching_modules") or []
            if str(module.get("teaching_purpose") or "")
        },
        "source_heading": {
            item.text for item in fragments if item.kind == "heading"
        },
        "source_sentence": {
            item.text for item in fragments if item.kind != "heading"
        },
    }
    used: list[str] = []
    for chapter in candidate.chapters:
        for episode in chapter.episodes:
            for beat in episode.beats:
                unknown = set(beat.fragment_ids) - set(catalog)
                if unknown:
                    raise ValueError("AI story plan referenced unknown fragment IDs")
                used.extend(beat.fragment_ids)
                source = beat.primary_claim_source
                if source.text not in official_claims.get(source.kind, set()):
                    raise ValueError("AI story plan introduced an unapproved claim")
                if source.fragment_id:
                    fragment = catalog.get(source.fragment_id)
                    if fragment is None or fragment.text != source.text:
                        raise ValueError("AI story plan claim does not match its source fragment")
    if len(used) != len(set(used)):
        raise ValueError("AI story plan duplicated source fragments")


async def plan_slide_story_v2(
    document: CourseDocument,
    course_data: dict[str, Any],
    fragments: list[ContentFragmentV1],
    *,
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
    ai_planner: Callable[
        [dict[str, Any]],
        Awaitable[dict[str, Any]] | dict[str, Any],
    ] | None = None,
    timeout_seconds: float = 45.0,
) -> SlideStoryPlanV2:
    """Use a constrained website planner, falling back to deterministic scenes."""
    fallback = compile_slide_story_plan_v2(
        document,
        course_data,
        fragments,
        mode=mode,
        theme=theme,
    )
    if ai_planner is None:
        fallback.fallback_reason = "no_ai_story_planner"
        return fallback
    request = {
        "schema_version": "slide_story_planning_request_v2",
        "rules": {
            "body_text_forbidden": True,
            "fragment_ids_only": True,
            "claims_must_be_exact_official_source_text": True,
            "structured_headlines_required": True,
            "unknown_ids_forbidden": True,
            "preserve_chapter_order": True,
            "preserve_proof_example_step_order": True,
            "answers_must_follow_prompts": True,
        },
        "mode": mode,
        "theme": theme,
        "course_teaching_plan_projection": project_course_teaching_plan(course_data),
        "course_knowledge_base": course_data.get("course_knowledge_base") or {},
        "course_coherence_contract": course_data.get("course_coherence_contract") or {},
        "allowed_scene_kinds": list(_SCENE_ORDER),
        "layout_registry": registry_summary_v2(),
        "fragments": [
            {
                "fragment_id": item.fragment_id,
                "section_id": item.section_id,
                "block_id": item.block_id,
                "kind": item.kind,
                "role": item.role,
                "ordinal": item.ordinal,
                "source_text": item.text[:400],
            }
            for item in fragments
        ],
        "deterministic_baseline": fallback.model_dump(mode="json"),
    }
    try:
        if inspect.iscoroutinefunction(ai_planner):
            raw = await asyncio.wait_for(
                ai_planner(request),
                timeout=timeout_seconds,
            )
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(ai_planner, request),
                timeout=timeout_seconds,
            )
            raw = await result if inspect.isawaitable(result) else result
        candidate = SlideStoryPlanV2.model_validate(raw)
        validate_ai_story_plan_v2(
            candidate,
            fallback=fallback,
            course_data=course_data,
            fragments=fragments,
        )
        candidate.planner = "ai"
        candidate.fallback_reason = ""
        return candidate
    except Exception:
        fallback.fallback_reason = "invalid_or_failed_ai_story_plan"
        return fallback
