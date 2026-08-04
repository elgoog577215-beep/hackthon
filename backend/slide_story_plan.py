"""Course-logic-first story planning and scene compilation for slide_deck_v4."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from course_teaching_plan_projection import project_course_teaching_plan
from slide_deck_v3 import (
    V3_LAYOUTS,
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
from slide_semantics import (
    compile_ppt_semantic_units,
    semantic_unit_index,
)

SLIDE_STORY_PLAN_V2_SCHEMA = "slide_story_plan_v2"
V5_SEMANTIC_CORE_REASONS = frozenset({
    "v5_semantic_grouping",
    "ai_source_bound_directive",
})
SLIDE_STORY_CHAPTER_DIRECTIVES_V2_SCHEMA = (
    "slide_story_chapter_directives_v2"
)
SLIDE_STORY_ENGINE_V2_VERSION = "course_logic_story_engine_v2.5"
STORY_BEAT_TEXT_CAPACITY = 230

ClaimSourceKind = Literal[
    "learning_objective",
    "knowledge_statement",
    "teaching_purpose",
    "source_heading",
    "source_sentence",
]
StoryCopyModeV2 = Literal[
    "source_exact",
    "source_faithful_rewrite",
    "instructional_scaffold",
]


class SlideStoryPlanPrerequisiteError(ValueError):
    """Typed failure for a missing official course-logic prerequisite."""

    def __init__(
        self,
        technical_message: str,
        *,
        code: str,
        user_message: str,
        action: str = "upgrade_course_logic",
        retryable: bool = False,
    ) -> None:
        super().__init__(technical_message)
        self.code = code
        self.user_message = user_message
        self.action = action
        self.retryable = retryable

    def public_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.user_message,
            "action": self.action,
            "retryable": self.retryable,
        }


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


class GeneratedPracticeAnswerV2(_StrictModel):
    question_index: int = Field(ge=0)
    question_id: str = ""
    answer_source: Literal["llm_generated"] = "llm_generated"
    answer_text: str = Field(min_length=2, max_length=140)
    supporting_fragment_ids: list[str] = Field(min_length=1, max_length=8)


class StoryBeatV2(_StrictModel):
    beat_id: str
    beat_role: str
    teaching_job: str
    primary_claim_source: ClaimSourceV2
    fragment_ids: list[str] = Field(default_factory=list)
    semantic_unit_ids: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list)
    answer_for_question_ids: list[str] = Field(default_factory=list)
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
    audience_facing_title: str = Field(default="", max_length=44)
    audience_facing_summary: str = Field(default="", max_length=180)
    copy_mode: StoryCopyModeV2 = "source_exact"
    copy_source_fragment_ids: list[str] = Field(default_factory=list, max_length=8)
    generated_practice_answers: list[GeneratedPracticeAnswerV2] = Field(
        default_factory=list,
        max_length=4,
    )


class StoryBeatDirectiveV2(_StrictModel):
    beat_id: str
    headline_fragment_id: str = ""
    layout_id: str = ""
    audience_facing_title: str = Field(default="", max_length=44)
    audience_facing_summary: str = Field(default="", max_length=180)
    copy_mode: StoryCopyModeV2 = "source_exact"
    supporting_fragment_ids: list[str] = Field(default_factory=list, max_length=8)
    generated_practice_answers: list[GeneratedPracticeAnswerV2] = Field(
        default_factory=list,
        max_length=8,
    )

    @model_validator(mode="after")
    def validate_copy_contract(self) -> StoryBeatDirectiveV2:
        has_copy = bool(
            self.audience_facing_title or self.audience_facing_summary
        )
        if self.copy_mode == "source_exact" and has_copy:
            raise ValueError("Audience-facing copy must declare a rewrite mode")
        if self.copy_mode != "source_exact" and not has_copy:
            raise ValueError("A rewrite mode requires audience-facing copy")
        if has_copy and not self.supporting_fragment_ids:
            raise ValueError("Audience-facing copy requires supporting fragments")
        return self


class StoryEpisodeDirectivesV2(_StrictModel):
    episode_id: str
    beat_directives: list[StoryBeatDirectiveV2] = Field(min_length=1)


class StoryChapterDirectivesV2(_StrictModel):
    schema_version: Literal["slide_story_chapter_directives_v2"] = (
        SLIDE_STORY_CHAPTER_DIRECTIVES_V2_SCHEMA
    )
    chapter_id: str
    beat_directives: list[StoryBeatDirectiveV2] = Field(default_factory=list)
    episode_directives: list[StoryEpisodeDirectivesV2] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_has_directives(self) -> StoryChapterDirectivesV2:
        if not self.beat_directives and not self.episode_directives:
            raise ValueError("AI story directives must contain at least one beat")
        return self


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
    def validate_reveal_order(self) -> TeachingEpisodeV2:
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
    def validate_entry_and_closure(self) -> ChapterStoryV2:
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
    planning_diagnostics: dict[str, Any] = Field(default_factory=dict)


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
            "slide_deck_v4 requires a completed official course teaching plan",
            code="course_teaching_plan_not_ready",
            user_message="当前课程尚未完成正式教学计划，请先补全课程逻辑。",
        )
    knowledge_base = course_data.get("course_knowledge_base") or {}
    if (
        not isinstance(knowledge_base, dict)
        or knowledge_base.get("lifecycle_status") != "active"
        or not knowledge_base.get("revision_id")
    ):
        raise SlideStoryPlanPrerequisiteError(
            "slide_deck_v4 requires an active official course knowledge base",
            code="course_knowledge_base_not_ready",
            user_message="当前课程尚未建立可用的正式知识库，请先补全课程逻辑。",
        )
    coherence_contract = course_data.get("course_coherence_contract") or {}
    if (
        not isinstance(coherence_contract, dict)
        or coherence_contract.get("status") != "active"
        or not coherence_contract.get("revision_id")
        or (coherence_contract.get("quality_report") or {}).get("passed") is False
    ):
        raise SlideStoryPlanPrerequisiteError(
            "slide_deck_v4 requires an active course coherence contract",
            code="course_coherence_contract_not_ready",
            user_message="当前课程尚未通过课程连贯性检查，请先补全课程逻辑。",
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


def slide_deck_v4_prerequisite_details(
    course_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the public, actionable blocker without exposing internal text."""
    try:
        _course_logic_inputs(course_data)
    except SlideStoryPlanPrerequisiteError as exc:
        return [exc.public_detail()]
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
    semantic_by_fragment: dict[str, Any],
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
        semantic_units = list({
            semantic_by_fragment[fragment.fragment_id].semantic_unit_id:
                semantic_by_fragment[fragment.fragment_id]
            for fragment in beat_fragments
            if fragment.fragment_id in semantic_by_fragment
        }.values())
        beats.append(StoryBeatV2(
            beat_id=beat_id,
            beat_role=role,
            teaching_job=_teaching_job(scene, role),
            primary_claim_source=claim,
            fragment_ids=[item.fragment_id for item in beat_fragments],
            semantic_unit_ids=[
                unit.semantic_unit_id for unit in semantic_units
            ],
            question_ids=list(dict.fromkeys(
                question_id
                for unit in semantic_units
                for question_id in unit.question_ids
            )),
            answer_for_question_ids=list(dict.fromkeys(
                question_id
                for unit in semantic_units
                for question_id in unit.answer_for_question_ids
            )),
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
    semantic_by_fragment = semantic_unit_index(
        compile_ppt_semantic_units(document, fragments)
    )
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
                f"Teaching plan has no section contract for chapter {chapter.section_id}",
                code="course_teaching_plan_incomplete",
                user_message="正式教学计划缺少部分章节的教学契约，请重新补全课程逻辑。",
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
            module_scene = _module_scene(module) if module else None
            scene = (
                module_scene
                if role_scene == "worked_example" and module_scene == "application"
                else role_scene
                if role_scene and block_role != "concept"
                else module_scene or role_scene or "concept"
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
                semantic_by_fragment=semantic_by_fragment,
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
                if beat.renderer_layout not in V3_LAYOUTS:
                    raise ValueError(
                        "AI story plan selected an unsupported renderer layout"
                    )
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


def _practice_questions_for_beat(
    beat: StoryBeatV2,
    fragment_catalog: dict[str, ContentFragmentV1],
) -> list[str]:
    questions: list[str] = []
    fallback_values: list[str] = []
    for fragment_id in beat.fragment_ids:
        fragment = fragment_catalog.get(fragment_id)
        if fragment is None or fragment.kind == "heading":
            continue
        value = " ".join(str(fragment.text or "").split())
        if not value:
            continue
        fallback_values.append(value)
        # Preserve the same granularity as the visible prompt block: one
        # source fragment/item maps to one stable question ID and one answer.
        # Splitting a compound item at every question mark produced four AI
        # answers for two rendered rows, so the identity contract correctly
        # rejected all of them and fell back to unrelated shared evidence.
        if ("？" in value or "?" in value) and value not in questions:
            questions.append(value)
    if questions:
        return questions[:4]
    return fallback_values[:1]


def _validate_generated_practice_answer_v2(
    *,
    answer: GeneratedPracticeAnswerV2,
    question: str,
    source_text: str,
) -> None:
    normalized_answer = " ".join(answer.answer_text.split())
    normalized_question = " ".join(question.split()).rstrip("？?")
    if normalized_answer.rstrip("。！？!?") == normalized_question:
        raise ValueError("Generated practice answer merely repeats its question")
    if normalized_answer.endswith(("？", "?")):
        raise ValueError("Generated practice answer must be declarative")
    _validate_grounded_audience_copy_v2(
        title="",
        summary=normalized_answer,
        source_text=source_text,
    )


def _compatible_layout_options_v2(
    *,
    scene_kind: SlideSceneKind,
    beat: StoryBeatV2,
    fragment_catalog: dict[str, ContentFragmentV1],
) -> list[dict[str, str]]:
    fragments = [
        fragment_catalog[fragment_id]
        for fragment_id in beat.fragment_ids
        if fragment_id in fragment_catalog
    ]
    character_count = sum(len(item.text) for item in fragments)
    item_count = sum(item.kind == "list_item" for item in fragments)
    evidence = set(_fragment_evidence(fragments))
    options: list[dict[str, str]] = []
    for layout in registry_summary_v2():
        if scene_kind not in layout["scene_kinds"]:
            continue
        if str(layout["renderer_layout"]) not in V3_LAYOUTS:
            continue
        if (
            character_count > int(layout["density_budget"])
            or item_count > int(layout["item_budget"])
        ):
            continue
        required_evidence = {
            accepted
            for slot in layout["slots"]
            if slot["required"]
            and not ({"text", "list"} & set(slot["accepts"]))
            for accepted in slot["accepts"]
        }
        if required_evidence and not (required_evidence & evidence):
            continue
        options.append({
            "layout_id": str(layout["layout_id"]),
            "renderer_layout": str(layout["renderer_layout"]),
            "layout_family": str(layout["layout_family"]),
        })
    if beat.layout_intent and all(
        item["layout_id"] != beat.layout_intent
        for item in options
    ):
        options.append({
            "layout_id": beat.layout_intent,
            "renderer_layout": beat.renderer_layout,
            "layout_family": beat.layout_family,
        })
    return options


def _apply_chapter_directives_v2(
    *,
    chapter: ChapterStoryV2,
    raw: dict[str, Any],
    fragment_catalog: dict[str, ContentFragmentV1],
    semantic_by_fragment: dict[str, Any],
) -> ChapterStoryV2:
    directives = StoryChapterDirectivesV2.model_validate(raw)
    if directives.chapter_id != chapter.chapter_id:
        raise ValueError("AI story directives changed the official chapter")
    beat_ids = {
        beat.beat_id
        for episode in chapter.episodes
        for beat in episode.beats
    }
    episode_ids = {
        episode.episode_id: {
            beat.beat_id for beat in episode.beats
        }
        for episode in chapter.episodes
    }
    grouped_directives: list[StoryBeatDirectiveV2] = []
    for episode_directive in directives.episode_directives:
        allowed_beat_ids = episode_ids.get(episode_directive.episode_id)
        if allowed_beat_ids is None:
            raise ValueError(
                "AI story directives referenced an unknown episode"
            )
        if any(
            item.beat_id not in allowed_beat_ids
            for item in episode_directive.beat_directives
        ):
            raise ValueError(
                "AI story directives moved a beat between episodes"
            )
        grouped_directives.extend(episode_directive.beat_directives)
    all_directives = directives.beat_directives + grouped_directives
    directive_ids = [item.beat_id for item in all_directives]
    if len(directive_ids) != len(set(directive_ids)):
        raise ValueError("AI story directives duplicated a beat")
    if set(directive_ids) - beat_ids:
        raise ValueError("AI story directives referenced an unknown beat")
    directive_by_id = {
        item.beat_id: item
        for item in all_directives
    }
    chapter_fragment_ids = {
        fragment_id
        for episode in chapter.episodes
        for beat in episode.beats
        for fragment_id in beat.fragment_ids
    }
    episodes: list[TeachingEpisodeV2] = []
    for episode in chapter.episodes:
        has_source_answer = any(
            beat.beat_role in {"solution", "answer", "feedback", "validation"}
            and bool(beat.fragment_ids)
            for beat in episode.beats
        )
        beats: list[StoryBeatV2] = []
        for beat in episode.beats:
            directive = directive_by_id.get(beat.beat_id)
            if directive is None:
                beats.append(beat)
                continue
            updates: dict[str, Any] = {}
            if directive.headline_fragment_id:
                fragment = fragment_catalog.get(
                    directive.headline_fragment_id,
                )
                if (
                    directive.headline_fragment_id in beat.fragment_ids
                    and fragment is not None
                ):
                    updates["primary_claim_source"] = ClaimSourceV2(
                        kind=(
                            "source_heading"
                            if fragment.kind == "heading"
                            else "source_sentence"
                        ),
                        text=fragment.text,
                        fragment_id=fragment.fragment_id,
                    )
            if directive.layout_id:
                options = _compatible_layout_options_v2(
                    scene_kind=episode.scene_kind,
                    beat=beat,
                    fragment_catalog=fragment_catalog,
                )
                selected = next(
                    (
                        item for item in options
                        if item["layout_id"] == directive.layout_id
                    ),
                    None,
                )
                if selected is not None:
                    updates.update({
                        "layout_intent": selected["layout_id"],
                        "renderer_layout": selected["renderer_layout"],
                        "layout_family": selected["layout_family"],
                    })
            if directive.copy_mode != "source_exact":
                supporting_ids = list(dict.fromkeys(
                    directive.supporting_fragment_ids
                ))
                supporting_fragments = [
                    fragment_catalog[fragment_id]
                    for fragment_id in supporting_ids
                    if fragment_id in fragment_catalog
                ]
                copy_is_bound = bool(
                    set(supporting_ids) <= set(beat.fragment_ids)
                    and len(supporting_fragments) == len(supporting_ids)
                )
                if copy_is_bound:
                    try:
                        _validate_grounded_audience_copy_v2(
                            title=directive.audience_facing_title,
                            summary=directive.audience_facing_summary,
                            source_text=" ".join(
                                fragment.text
                                for fragment in supporting_fragments
                            ),
                        )
                    except ValueError:
                        # Audience copy is an optional enhancement. Reject only
                        # the unsafe rewrite and retain the source-exact baseline;
                        # do not discard valid layouts or generated answers from
                        # the rest of the chapter.
                        pass
                    else:
                        updates.update({
                            "audience_facing_title": (
                                directive.audience_facing_title.strip()
                            ),
                            "audience_facing_summary": (
                                directive.audience_facing_summary.strip()
                            ),
                            "copy_mode": directive.copy_mode,
                            "copy_source_fragment_ids": supporting_ids,
                        })
            if directive.generated_practice_answers:
                answers_are_ineligible = bool(
                    episode.scene_kind != "practice_feedback"
                    or beat.beat_role != "prompt"
                    or has_source_answer
                )
                if not answers_are_ineligible:
                    questions = _practice_questions_for_beat(
                        beat,
                        fragment_catalog,
                    )
                    expected_question_ids = list(beat.question_ids)
                    if not expected_question_ids:
                        expected_question_ids = list(dict.fromkeys(
                            question_id
                            for fragment_id in beat.fragment_ids
                            if fragment_id in semantic_by_fragment
                            for question_id in semantic_by_fragment[
                                fragment_id
                            ].question_ids
                        ))
                    if len(expected_question_ids) != len(questions):
                        expected_question_ids = [
                            stable_hash(
                                {
                                    "beat_id": beat.beat_id,
                                    "question_index": index,
                                },
                                prefix="pptq_",
                            )
                            for index in range(len(questions))
                        ]
                    answer_indexes = [
                        item.question_index
                        for item in directive.generated_practice_answers
                    ]
                    if answer_indexes == list(range(len(questions))):
                        generated_answers: list[GeneratedPracticeAnswerV2] = []
                        for answer in directive.generated_practice_answers:
                            expected_question_id = expected_question_ids[
                                answer.question_index
                            ]
                            if (
                                answer.question_id
                                and answer.question_id != expected_question_id
                            ):
                                generated_answers = []
                                break
                            supporting_ids = list(dict.fromkeys(
                                answer.supporting_fragment_ids
                            ))
                            supporting_fragments = [
                                fragment_catalog[fragment_id]
                                for fragment_id in supporting_ids
                                if fragment_id in fragment_catalog
                            ]
                            answer_is_bound = bool(
                                set(supporting_ids) <= chapter_fragment_ids
                                and len(supporting_fragments)
                                == len(supporting_ids)
                            )
                            if not answer_is_bound:
                                generated_answers = []
                                break
                            try:
                                _validate_generated_practice_answer_v2(
                                    answer=answer,
                                    question=questions[answer.question_index],
                                    # Question premises and generic case labels
                                    # may be repeated without becoming new facts.
                                    source_text=" ".join([
                                        questions[answer.question_index],
                                        *(
                                            fragment.text
                                            for fragment in supporting_fragments
                                        ),
                                        "A B C D 1 2 3 4",
                                    ]),
                                )
                            except (IndexError, ValueError):
                                generated_answers = []
                                break
                            generated_answers.append(answer.model_copy(update={
                                "question_id": expected_question_id,
                                "answer_text": " ".join(
                                    answer.answer_text.split()
                                ),
                                "supporting_fragment_ids": supporting_ids,
                            }))
                        if len(generated_answers) == len(questions):
                            updates["generated_practice_answers"] = (
                                generated_answers
                            )
            if updates:
                updates["layout_selection_reason"] = (
                    "ai_source_bound_directive"
                )
            beats.append(beat.model_copy(update=updates))
        episodes.append(episode.model_copy(update={"beats": beats}))
    return chapter.model_copy(update={"episodes": episodes})


_COPY_INTERNAL_LANGUAGE = re.compile(
    r"(?:system prompt|prompt|planner|model|"
    r"layout[_\s-]*id|fragment[_\s-]*id|beat[_\s-]*id)",
    re.IGNORECASE,
)
_COPY_PROTECTED_TOKEN = re.compile(
    r"(?:\d+(?:\.\d+)?%?|[A-Za-z][A-Za-z0-9_+./-]*|"
    r"[一二两三四五六七八九十百]+(?=\s*(?:类|种|项|个|步|部分|方面|阶段))|"
    r"[Δ∑∏√∞≈≠≤≥±×÷])"
)


def _validate_grounded_audience_copy_v2(
    *,
    title: str,
    summary: str,
    source_text: str,
) -> None:
    generated = " ".join(f"{title} {summary}".split())
    if not generated:
        raise ValueError("Audience-facing copy cannot be empty")
    if _COPY_INTERNAL_LANGUAGE.search(generated):
        raise ValueError("Audience-facing copy exposed internal planning language")
    if any(marker in generated for marker in ("```", "graph TD", "graph LR")):
        raise ValueError("Audience-facing copy exposed code or diagram syntax")
    source_lower = source_text.lower()
    unsupported_tokens = {
        token
        for token in _COPY_PROTECTED_TOKEN.findall(generated)
        if token.lower() not in source_lower
    }
    if unsupported_tokens:
        raise ValueError(
            "Audience-facing copy introduced unsupported factual tokens: "
            + ", ".join(sorted(unsupported_tokens))
        )


def _normalize_chapter_directives_v2(
    raw: Any,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload = raw.get(SLIDE_STORY_CHAPTER_DIRECTIVES_V2_SCHEMA, raw)
    if not isinstance(payload, dict) or not payload.get("chapter_id"):
        return None
    normalized = dict(payload)
    if "episodes" in normalized and "episode_directives" not in normalized:
        normalized["episode_directives"] = [
            {
                "episode_id": item.get("episode_id"),
                "beat_directives": item.get("beat_directives")
                or item.get("beats")
                or [],
            }
            for item in normalized.pop("episodes") or []
            if isinstance(item, dict)
        ]

    def normalize_copy_contract(item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        directive = dict(item)
        normalized_answers = []
        for answer in directive.get("generated_practice_answers") or []:
            if not isinstance(answer, dict):
                normalized_answers.append(answer)
                continue
            normalized_answer = dict(answer)
            answer_text = " ".join(
                str(normalized_answer.get("answer_text") or "").split()
            )
            answer_text = re.sub(
                r"(?:依据|来源|支持片段)?\s*[:：]?\s*"
                r"(?:sfg_[A-Za-z0-9_-]+(?:\s*[,，、]\s*)?)+[。.]?",
                "",
                answer_text,
                flags=re.IGNORECASE,
            ).strip()
            if len(answer_text) > 140:
                clipped = answer_text[:140]
                sentence_end = max(
                    clipped.rfind(mark)
                    for mark in ("。", "！", "!", "；", ";")
                )
                if sentence_end >= 56:
                    answer_text = clipped[:sentence_end + 1]
                else:
                    answer_text = clipped[:139].rstrip(
                        "，,；;：:、 "
                    ) + "。"
            normalized_answer["answer_text"] = answer_text
            normalized_answers.append(normalized_answer)
        if normalized_answers:
            directive["generated_practice_answers"] = normalized_answers
        has_copy = bool(
            str(directive.get("audience_facing_title") or "").strip()
            or str(directive.get("audience_facing_summary") or "").strip()
        )
        if not has_copy:
            # Some providers echo the requested rewrite mode even when they
            # correctly omit optional copy. Canonicalize that harmless shape
            # instead of invalidating every other directive in the chapter.
            directive["copy_mode"] = "source_exact"
            return directive
        supporting_ids = list(dict.fromkeys(
            str(value).strip()
            for value in directive.get("supporting_fragment_ids") or []
            if str(value).strip()
        ))
        headline_id = str(
            directive.get("headline_fragment_id") or ""
        ).strip()
        if not supporting_ids and headline_id:
            supporting_ids = [headline_id]
        if not supporting_ids:
            # Audience copy is optional. Drop an ungrounded rewrite while
            # preserving layout and generated-answer directives for the beat.
            directive["audience_facing_title"] = ""
            directive["audience_facing_summary"] = ""
            directive["copy_mode"] = "source_exact"
            return directive
        directive["supporting_fragment_ids"] = supporting_ids
        if directive.get("copy_mode") in {None, "", "source_exact"}:
            directive["copy_mode"] = "source_faithful_rewrite"
        return directive

    normalized["beat_directives"] = [
        normalize_copy_contract(item)
        for item in normalized.get("beat_directives") or []
    ]
    normalized["episode_directives"] = [
        {
            **item,
            "beat_directives": [
                normalize_copy_contract(directive)
                for directive in item.get("beat_directives") or []
            ],
        }
        for item in normalized.get("episode_directives") or []
        if isinstance(item, dict)
    ]
    if not (
        normalized.get("beat_directives")
        or normalized.get("episode_directives")
    ):
        return None
    normalized["schema_version"] = (
        SLIDE_STORY_CHAPTER_DIRECTIVES_V2_SCHEMA
    )
    return normalized


async def plan_slide_story_v2(
    document: CourseDocument,
    course_data: dict[str, Any],
    fragments: list[ContentFragmentV1],
    *,
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
    baseline: SlideStoryPlanV2 | None = None,
    ai_planner: Callable[
        [dict[str, Any]],
        Awaitable[dict[str, Any]] | dict[str, Any],
    ] | None = None,
    timeout_seconds: float = 180.0,
) -> SlideStoryPlanV2:
    """Use a constrained chapter-batched planner, falling back to deterministic scenes."""
    fallback = baseline or compile_slide_story_plan_v2(
        document,
        course_data,
        fragments,
        mode=mode,
        theme=theme,
    )
    if fallback.mode != mode or fallback.theme != theme:
        raise ValueError("Story planning baseline does not match the requested variant")
    if ai_planner is None:
        fallback.fallback_reason = "no_ai_story_planner"
        return fallback
    fragment_catalog = {item.fragment_id: item for item in fragments}
    semantic_by_fragment = semantic_unit_index(
        compile_ppt_semantic_units(document, fragments)
    )
    projection = project_course_teaching_plan(course_data)
    chapter_count = len(fallback.chapters)

    async def invoke_planner(request: dict[str, Any]) -> dict[str, Any]:
        if inspect.iscoroutinefunction(ai_planner):
            return await asyncio.wait_for(
                ai_planner(request),
                timeout=timeout_seconds,
            )
        result = await asyncio.wait_for(
            asyncio.to_thread(ai_planner, request),
            timeout=timeout_seconds,
        )
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, timeout=timeout_seconds)
        return result

    try:
        planning_units: list[
            tuple[
                ChapterStoryV2,
                SlideStoryPlanV2,
                list[ContentFragmentV1],
                dict[str, Any],
            ]
        ] = []
        for chapter_index, chapter in enumerate(fallback.chapters):
            referenced_ids = {
                fragment_id
                for episode in chapter.episodes
                for beat in episode.beats
                for fragment_id in beat.fragment_ids
            }
            referenced_ids.update({
                beat.primary_claim_source.fragment_id
                for episode in chapter.episodes
                for beat in episode.beats
                if beat.primary_claim_source.fragment_id
            })
            chapter_fragments = [
                item for item in fragments
                if item.fragment_id in referenced_ids
            ]
            section_ids = {
                item.section_id for item in chapter_fragments
            } | {chapter.chapter_id}
            chapter_projection = {
                key: value
                for key, value in projection.items()
                if key != "sections"
            }
            chapter_projection["sections"] = [
                item
                for item in projection.get("sections") or []
                if str(item.get("node_id") or "") in section_ids
            ]
            chapter_baseline = fallback.model_copy(
                update={"chapters": [chapter]},
            )
            beat_catalog = [
                {
                    "beat_id": beat.beat_id,
                    "scene_kind": episode.scene_kind,
                    "beat_role": beat.beat_role,
                    "current_layout_id": beat.layout_intent,
                    "allowed_layouts": _compatible_layout_options_v2(
                        scene_kind=episode.scene_kind,
                        beat=beat,
                        fragment_catalog=fragment_catalog,
                    ),
                    "headline_candidates": [
                        {
                            "fragment_id": fragment_id,
                            "kind": fragment_catalog[fragment_id].kind,
                            "source_text": fragment_catalog[
                                fragment_id
                            ].text[:200],
                        }
                        for fragment_id in beat.fragment_ids
                        if fragment_id in fragment_catalog
                    ],
                    "prompt_questions": (
                        _practice_questions_for_beat(beat, fragment_catalog)
                        if (
                            episode.scene_kind == "practice_feedback"
                            and beat.beat_role == "prompt"
                        )
                        else []
                    ),
                    "needs_generated_answers": bool(
                        episode.scene_kind == "practice_feedback"
                        and beat.beat_role == "prompt"
                        and not any(
                            candidate.beat_role
                            in {"solution", "answer", "feedback", "validation"}
                            and candidate.fragment_ids
                            for candidate in episode.beats
                        )
                    ),
                    "semantic_unit_ids": list(dict.fromkeys(
                        semantic_by_fragment[fragment_id].semantic_unit_id
                        for fragment_id in beat.fragment_ids
                        if fragment_id in semantic_by_fragment
                    )),
                    "question_ids": list(dict.fromkeys(
                        question_id
                        for fragment_id in beat.fragment_ids
                        if fragment_id in semantic_by_fragment
                        for question_id in semantic_by_fragment[
                            fragment_id
                        ].question_ids
                    )),
                    "answer_for_question_ids": list(dict.fromkeys(
                        question_id
                        for fragment_id in beat.fragment_ids
                        if fragment_id in semantic_by_fragment
                        for question_id in semantic_by_fragment[
                            fragment_id
                        ].answer_for_question_ids
                    )),
                }
                for episode in chapter.episodes
                for beat in episode.beats
            ]
            request = {
                "schema_version": "slide_story_planning_request_v2",
                "scope": {
                    "chapter_id": chapter.chapter_id,
                    "chapter_index": chapter_index,
                    "chapter_count": chapter_count,
                },
                "rules": {
                    "body_text_forbidden": False,
                    "fragment_ids_only": False,
                    "claims_must_be_exact_official_source_text": False,
                    "copy_policy": "source_faithful_rewrite",
                    "unsupported_new_facts_forbidden": True,
                    "supporting_fragment_ids_required_for_rewrite": True,
                    "instructional_scaffolds_may_frame_but_not_add_facts": True,
                    "structured_headlines_required": True,
                    "unknown_ids_forbidden": True,
                    "preserve_chapter_order": True,
                    "preserve_proof_example_step_order": True,
                    "answers_must_follow_prompts": True,
                    "missing_answers_may_be_synthesized_from_chapter_fragments": True,
                    "generated_answers_must_cover_every_prompt_question": True,
                    "generated_answers_require_supporting_fragment_ids": True,
                    "return_exactly_one_chapter": True,
                    "return_compact_directives_only": True,
                },
                "mode": mode,
                "theme": theme,
                "course_teaching_plan_projection": chapter_projection,
                "source_revisions": fallback.source_revisions.model_dump(
                    mode="json",
                ),
                "allowed_scene_kinds": list(_SCENE_ORDER),
                "layout_registry": registry_summary_v2(),
                "beat_catalog": beat_catalog,
                "chapter_contract": {
                    "chapter_id": chapter.chapter_id,
                    "title": chapter.title,
                    "driving_question": chapter.driving_question,
                    "learning_objective": chapter.learning_objective,
                    "episode_order": [
                        {
                            "episode_id": episode.episode_id,
                            "scene_kind": episode.scene_kind,
                            "beat_ids": [
                                beat.beat_id for beat in episode.beats
                            ],
                        }
                        for episode in chapter.episodes
                    ],
                },
                "fragments": [
                    {
                        "fragment_id": item.fragment_id,
                        "section_id": item.section_id,
                        "block_id": item.block_id,
                        "kind": item.kind,
                        "role": item.role,
                        "ordinal": item.ordinal,
                        "source_text": item.text[:400],
                        "semantic_unit_id": (
                            semantic_by_fragment[item.fragment_id].semantic_unit_id
                            if item.fragment_id in semantic_by_fragment
                            else ""
                        ),
                        "presentation_intent": (
                            semantic_by_fragment[
                                item.fragment_id
                            ].presentation_intent
                            if item.fragment_id in semantic_by_fragment
                            else "definition"
                        ),
                        "module_id": item.module_id,
                        "module_instance_id": item.module_instance_id,
                        "lesson_archetype_id": item.lesson_archetype_id,
                        "composition_style": item.composition_style,
                        "difficulty_contract": (
                            item.block_difficulty_contract
                        ),
                        "objective_refs": item.objective_refs,
                        "concept_refs": item.concept_refs,
                        "evidence_refs": item.evidence_refs,
                    }
                    for item in chapter_fragments
                ],
            }
            planning_units.append((
                chapter,
                chapter_baseline,
                chapter_fragments,
                request,
            ))

        semaphore = asyncio.Semaphore(3)

        async def plan_chapter(
            unit: tuple[
                ChapterStoryV2,
                SlideStoryPlanV2,
                list[ContentFragmentV1],
                dict[str, Any],
            ],
        ) -> tuple[ChapterStoryV2, dict[str, str] | None]:
            chapter, chapter_baseline, chapter_fragments, request = unit
            try:
                async with semaphore:
                    raw = await invoke_planner(request)
                normalized_directives = _normalize_chapter_directives_v2(raw)
                if normalized_directives is not None:
                    planned = _apply_chapter_directives_v2(
                        chapter=chapter,
                        raw=normalized_directives,
                        fragment_catalog=fragment_catalog,
                        semantic_by_fragment=semantic_by_fragment,
                    )
                else:
                    chapter_candidate = SlideStoryPlanV2.model_validate(raw)
                    validate_ai_story_plan_v2(
                        chapter_candidate,
                        fallback=chapter_baseline,
                        course_data=course_data,
                        fragments=chapter_fragments,
                    )
                    planned = chapter_candidate.chapters[0]
                return planned, None
            except Exception as exc:
                code = (
                    "timeout"
                    if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                    else "invalid_response"
                )
                failure: dict[str, Any] = {
                    "chapter_id": chapter.chapter_id,
                    "code": code,
                    "error_type": type(exc).__name__,
                }
                if isinstance(exc, ValidationError):
                    failure["validation_errors"] = [
                        {
                            "location": ".".join(
                                str(part) for part in item.get("loc") or []
                            ),
                            "type": str(item.get("type") or ""),
                            "message": str(item.get("msg") or "")[:240],
                        }
                        for item in exc.errors(include_url=False)[:8]
                    ]
                elif str(exc).strip():
                    failure["message"] = str(exc).strip()[:300]
                return chapter, failure

        chapter_results = list(await asyncio.gather(*(
            plan_chapter(unit) for unit in planning_units
        )))
        planned_chapters = [item[0] for item in chapter_results]
        chapter_failures = [
            item[1]
            for item in chapter_results
            if item[1] is not None
        ]
        diagnostics = {
            "chapter_count": chapter_count,
            "successful_chapter_count": chapter_count - len(chapter_failures),
            "failed_chapter_count": len(chapter_failures),
            "chapter_failures": chapter_failures,
        }
        if len(chapter_failures) == chapter_count:
            fallback.fallback_reason = "invalid_or_failed_ai_story_plan"
            fallback.planning_diagnostics = diagnostics
            return fallback
        candidate = fallback.model_copy(update={
            "plan_id": stable_hash({
                "mode": mode,
                "theme": theme,
                "sources": fallback.source_revisions.model_dump(mode="json"),
                "chapters": [
                    item.model_dump(mode="json")
                    for item in planned_chapters
                ],
            }, prefix="story_"),
            "chapters": planned_chapters,
            "planner": "ai",
            "fallback_reason": (
                "partial_ai_story_plan"
                if chapter_failures
                else ""
            ),
            "planning_diagnostics": diagnostics,
        })
        validate_ai_story_plan_v2(
            candidate,
            fallback=fallback,
            course_data=course_data,
            fragments=fragments,
        )
        return candidate
    except Exception as exc:
        fallback.fallback_reason = "invalid_or_failed_ai_story_plan"
        fallback.planning_diagnostics = {
            "chapter_count": len(fallback.chapters),
            "successful_chapter_count": 0,
            "failed_chapter_count": len(fallback.chapters),
            "chapter_failures": [],
            "deck_failure": {
                "code": (
                    "timeout"
                    if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                    else "invalid_response"
                ),
                "error_type": type(exc).__name__,
            },
        }
        return fallback
