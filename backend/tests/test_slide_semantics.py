from __future__ import annotations

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection
from slide_deck_v3 import fragment_course_document
from slide_deck_v5 import compact_story_plan_v5
from slide_semantics import (
    compile_ppt_semantic_units,
    resolve_domain_presentation_profile,
)
from slide_story_plan import (
    ChapterStoryV2,
    ClaimSourceV2,
    CommunicationBriefV2,
    SlideStoryPlanV2,
    StoryBeatV2,
    StorySourceRevisionsV2,
    TeachingEpisodeV2,
)


def _document(*blocks: CourseBlock) -> CourseDocument:
    return CourseDocument(
        course_id="semantic-course",
        title="教学语义测试",
        document_revision="doc-semantic-v1",
        sections=[
            CourseSection(
                section_id="chapter-1",
                title="第一章",
                position=0,
                level=1,
                learning_objective="建立可迁移的判断框架",
            ),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="第一节",
                position=1,
                level=2,
                learning_objective="解释并应用核心关系",
                attributes={
                    "lesson_archetype": {
                        "archetype_id": "life_structure_function",
                    },
                },
            ),
        ],
        blocks=list(blocks),
    )


def _block(
    block_id: str,
    *,
    module_id: str,
    role: str,
    content: str,
    position: int,
) -> CourseBlock:
    return CourseBlock(
        block_id=block_id,
        section_id="section-1",
        position=position,
        role=role,
        payload={
            "title": "课程内容",
            "markdown": content,
            "module_id": module_id,
            "module_instance_id": f"instance-{block_id}",
            "composition_source": "subject_required",
            "composition_style": "balanced",
            "block_difficulty_contract": {"scaffold_level": "guided"},
            "knowledge_binding_status": "bound",
        },
        objective_refs=["objective-1"],
        concept_refs=["knowledge-1"],
        evidence_refs=["evidence-1"],
    )


def _terminal_beat(scene: str) -> StoryBeatV2:
    return StoryBeatV2(
        beat_id=f"beat-{scene}",
        beat_role="driving_question" if scene == "chapter_entry" else "closure",
        teaching_job="建立问题" if scene == "chapter_entry" else "完成回顾",
        primary_claim_source=ClaimSourceV2(
            kind="learning_objective",
            text="解释并应用核心关系",
            objective_id="objective-1",
        ),
        layout_intent="hero-statement",
        renderer_layout="hero-statement",
        layout_family="statement",
        layout_selection_reason="test fixture",
    )


def _story() -> SlideStoryPlanV2:
    return SlideStoryPlanV2(
        plan_id="story-semantic-v2",
        mode="teaching",
        theme="qizhi-classroom",
        communication_brief=CommunicationBriefV2(
            audience="本科生",
            course_goal="建立判断框架",
            central_question="如何形成可靠判断？",
        ),
        source_revisions=StorySourceRevisionsV2(
            course_document_revision="doc-semantic-v1",
            teaching_plan_revision="plan-v1",
            knowledge_base_revision="kb-v1",
            coherence_contract_revision="coherence-v1",
        ),
        chapters=[ChapterStoryV2(
            chapter_id="chapter-1",
            title="第一章",
            driving_question="如何形成可靠判断？",
            learning_objective="建立可迁移的判断框架",
            episodes=[
                TeachingEpisodeV2(
                    episode_id="entry",
                    scene_kind="chapter_entry",
                    teaching_job="建立问题",
                    beats=[_terminal_beat("chapter_entry")],
                ),
                TeachingEpisodeV2(
                    episode_id="recap",
                    scene_kind="chapter_recap",
                    teaching_job="完成回顾",
                    beats=[_terminal_beat("chapter_recap")],
                ),
            ],
        )],
    )


def test_v16_metadata_survives_fragment_and_semantic_projection() -> None:
    document = _document(_block(
        "structure",
        module_id="life_location_structure",
        role="concept",
        content="浅层结构与深层结构构成稳定的空间层次。",
        position=0,
    ))

    fragments = fragment_course_document(document)
    units = compile_ppt_semantic_units(document, fragments)

    assert fragments[0].module_id == "life_location_structure"
    assert fragments[0].composition_style == "balanced"
    assert fragments[0].evidence_refs == ["evidence-1"]
    assert units[0].adapter_type == "v16_structured"
    assert units[0].lesson_archetype_id == "life_structure_function"
    assert units[0].presentation_intent == "hierarchy"
    assert units[0].concept_refs == ["knowledge-1"]
    assert units[0].classification_confidence == 1.0


@pytest.mark.parametrize(
    ("module_id", "role", "profile_id", "intent"),
    [
        ("life_location_structure", "concept", "life_medical", "hierarchy"),
        ("math_proof", "reasoning", "math_formal", "mechanism"),
        ("science_experiment_design", "activity", "natural_science", "process"),
        ("engineering_architecture", "concept", "engineering_programming", "hierarchy"),
        ("humanities_timeline", "orientation", "humanities_social", "process"),
        ("business_decision", "reasoning", "business_career", "comparison"),
        ("unknown_module", "concept", "generic", "definition"),
    ],
)
def test_subject_profiles_extend_one_generic_intent_protocol(
    module_id: str,
    role: str,
    profile_id: str,
    intent: str,
) -> None:
    profile = resolve_domain_presentation_profile([module_id])
    document = _document(_block(
        "subject-block",
        module_id=module_id,
        role=role,
        content="来源内容保持不变。",
        position=0,
    ))

    unit = compile_ppt_semantic_units(document, fragment_course_document(document))[0]

    assert profile.profile_id == profile_id
    assert unit.domain_profile_id == profile_id
    assert unit.presentation_intent == intent


def test_feedback_binds_to_the_preceding_learner_action() -> None:
    document = _document(
        _block(
            "question",
            module_id="learner_action",
            role="activity",
            content="请判断该结构属于哪一层，并说明依据。",
            position=0,
        ),
        _block(
            "answer",
            module_id="feedback_check",
            role="feedback",
            content="应依据位置关系和相邻结构完成判断。",
            position=1,
        ),
    )

    units = compile_ppt_semantic_units(document, fragment_course_document(document))
    prompt = next(unit for unit in units if unit.primary_role == "activity")
    feedback = next(unit for unit in units if unit.primary_role == "feedback")

    assert prompt.question_ids
    assert feedback.answer_for_question_ids == prompt.question_ids
    assert feedback.answer_source == "source"


def test_each_visible_prompt_receives_a_distinct_question_id() -> None:
    document = _document(_block(
        "question-list",
        module_id="learner_action",
        role="activity",
        content="- Which layer is superficial?\n- Which layer is deep?",
        position=0,
    ))

    unit = compile_ppt_semantic_units(
        document,
        fragment_course_document(document),
    )[0]

    assert len(unit.question_ids) == 2
    assert len(set(unit.question_ids)) == 2


def test_legacy_course_uses_low_confidence_heading_fallback() -> None:
    document = CourseDocument(
        course_id="legacy-course",
        title="旧课程",
        document_revision="legacy-v1",
        sections=[CourseSection(
            section_id="legacy-section",
            title="基本概念",
            position=0,
            level=1,
        )],
        blocks=[CourseBlock(
            block_id="legacy-block",
            section_id="legacy-section",
            position=0,
            role="concept",
            payload={"markdown": "这是旧课程的概念说明。"},
        )],
    )

    unit = compile_ppt_semantic_units(
        document,
        fragment_course_document(document),
    )[0]

    assert unit.adapter_type == "legacy_compatible"
    assert unit.classification_source == "legacy_heading_fallback"
    assert unit.classification_confidence == 0.45


def test_v5_compaction_uses_roles_and_pairs_practice_with_feedback() -> None:
    document = _document(
        _block(
            "concept",
            module_id="core_explanation",
            role="concept",
            content="结构层次决定观察和操作顺序。",
            position=0,
        ),
        _block(
            "example",
            module_id="life_case",
            role="example",
            content="病例中先识别浅层标志，再核对深层边界。",
            position=1,
        ),
        _block(
            "question",
            module_id="learner_action",
            role="activity",
            content="请给出观察顺序。",
            position=2,
        ),
        _block(
            "answer",
            module_id="feedback_check",
            role="feedback",
            content="先浅后深，并逐层核对边界。",
            position=3,
        ),
    )
    fragments = fragment_course_document(document)

    compacted = compact_story_plan_v5(document, _story(), fragments)

    episodes = compacted.chapters[0].episodes[1:-1]
    assert [episode.scene_kind for episode in episodes] == [
        "concept",
        "worked_example",
        "practice_feedback",
    ]
    fragment_by_id = {fragment.fragment_id: fragment for fragment in fragments}
    practice_blocks = {
        fragment_by_id[fragment_id].block_id
        for fragment_id in episodes[-1].beats[0].fragment_ids
    }
    assert practice_blocks == {"question", "answer"}
    assert episodes[-1].beats[0].question_ids
    assert episodes[-1].beats[0].answer_for_question_ids == (
        episodes[-1].beats[0].question_ids
    )
    diagnostics = compacted.planning_diagnostics
    assert diagnostics["semantic_role_counts"] == {
        "activity": 1,
        "concept": 1,
        "example": 1,
        "feedback": 1,
    }
    assert diagnostics["balanced_composition_unit_count"] == 4
    assert diagnostics["knowledge_binding_unmapped_count"] == 0
    assert diagnostics["question_answer_binding_coverage"] == 1.0
    assert [
        contract["presentation_intent"]
        for contract in diagnostics["teaching_episode_contracts"]
    ] == ["definition", "worked_example", "practice_feedback"]
