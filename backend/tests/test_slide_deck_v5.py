from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from course_document import CourseDocument, CourseSection
from slide_deck import SlideDeckContent, validate_slide_deck
from slide_deck_renderer import _render_editorial_body, _render_slide
from slide_deck_v5 import (
    compile_deck_outline_v5,
    compile_page_title_v5,
    resolve_page_contract_v5,
    v5_contract_issues,
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


def _beat(chapter_index: int, scene: str) -> StoryBeatV2:
    return StoryBeatV2(
        beat_id=f"beat-{chapter_index}-{scene}",
        beat_role="driving_question" if scene == "chapter_entry" else "closure",
        teaching_job="建立学习问题" if scene == "chapter_entry" else "完成章节回顾",
        primary_claim_source=ClaimSourceV2(
            kind="learning_objective",
            text=f"理解第{chapter_index}章的核心关系",
            objective_id=f"objective-{chapter_index}",
        ),
        layout_intent="hero-statement",
        renderer_layout="hero-statement",
        layout_family="statement",
        layout_selection_reason="test fixture",
    )


def _chapter(index: int) -> ChapterStoryV2:
    return ChapterStoryV2(
        chapter_id=f"chapter-{index}",
        title=f"第{index}章 主题{index}",
        driving_question=f"主题{index}解决什么问题？",
        learning_objective=f"理解主题{index}的核心关系",
        episodes=[
            TeachingEpisodeV2(
                episode_id=f"episode-{index}-entry",
                scene_kind="chapter_entry",
                teaching_job="建立学习问题",
                beats=[_beat(index, "chapter_entry")],
            ),
            TeachingEpisodeV2(
                episode_id=f"episode-{index}-recap",
                scene_kind="chapter_recap",
                teaching_job="完成章节回顾",
                beats=[_beat(index, "chapter_recap")],
            ),
        ],
    )


def _story(chapter_count: int) -> SlideStoryPlanV2:
    return SlideStoryPlanV2(
        plan_id="story-v5-test",
        mode="teaching",
        theme="qizhi-classroom",
        communication_brief=CommunicationBriefV2(
            audience="本科生",
            course_goal="建立一套可迁移的分析框架",
            central_question="如何从基本概念走向完整分析？",
            expected_learning_results=["解释概念", "应用方法"],
        ),
        source_revisions=StorySourceRevisionsV2(
            course_document_revision="doc-rev-1",
            teaching_plan_revision="plan-rev-1",
            knowledge_base_revision="kb-rev-1",
            coherence_contract_revision="coherence-rev-1",
        ),
        chapters=[_chapter(index) for index in range(1, chapter_count + 1)],
    )


def _document(chapter_count: int) -> CourseDocument:
    return CourseDocument(
        course_id="course-v5-test",
        title="课程 V5 测试",
        document_revision="doc-rev-1",
        sections=[
            CourseSection(
                section_id=f"chapter-{index}",
                title=f"第{index}章 主题{index}",
                position=index - 1,
                level=1,
                learning_objective=f"理解主题{index}的核心关系",
            )
            for index in range(1, chapter_count + 1)
        ],
    )


def test_outline_groups_eight_chapters_into_at_most_six_source_bound_sections() -> None:
    outline = compile_deck_outline_v5(_document(8), _story(8))

    assert 3 <= len(outline.agenda_sections) <= 6
    assert [
        chapter_id
        for section in outline.agenda_sections
        for chapter_id in section.source_chapter_ids
    ] == [f"chapter-{index}" for index in range(1, 9)]
    assert outline.cover.subtitle == ""
    assert outline.closing.kind == "course_synthesis"


def test_outline_does_not_invent_sections_for_a_single_chapter_course() -> None:
    outline = compile_deck_outline_v5(_document(1), _story(1))

    assert len(outline.agenda_sections) == 1
    assert outline.agenda_sections[0].source_chapter_ids == ["chapter-1"]


def test_one_text_group_cannot_keep_a_two_column_layout() -> None:
    contract = resolve_page_contract_v5({
        "layout": "concept",
        "composition": "split-visual",
        "visuals": [],
        "blocks": [
            {
                "block_id": "body",
                "type": "rich_text",
                "content": "只有一个完整的语义段落。",
                "items": [],
            },
        ],
        "quality": {"requested_layout": "two-column"},
    })

    assert contract.resolved_layout == "editorial-body"
    assert contract.resolved_composition == "statement"
    assert contract.occupied_major_region_count == 1
    assert contract.layout_fallback_reason == "single_group_two_column"


def test_three_sibling_items_select_a_classification_layout() -> None:
    contract = resolve_page_contract_v5({
        "layout": "concept",
        "composition": "statement",
        "visuals": [],
        "blocks": [
            {
                "block_id": "classification",
                "type": "bullets",
                "content": "",
                "items": ["孤立系统", "封闭系统", "开放系统"],
            },
        ],
        "quality": {"requested_layout": "two-column"},
    })

    assert contract.resolved_layout == "classification-3"
    assert [binding.semantic_role for binding in contract.slot_bindings] == [
        "classification_item",
        "classification_item",
        "classification_item",
    ]
    assert contract.occupied_major_region_count == 3


def test_rejected_visual_reflows_to_a_text_native_composition() -> None:
    contract = resolve_page_contract_v5({
        "layout": "concept",
        "composition": "split-visual",
        "visuals": [],
        "blocks": [
            {
                "block_id": "definition",
                "type": "rich_text",
                "content": "系统边界决定可发生的交换。",
                "items": [],
            },
        ],
        "quality": {"requested_layout": "figure-text"},
    })

    assert contract.visual_decision == "none"
    assert contract.resolved_layout == "editorial-body"
    assert contract.resolved_composition == "statement"
    assert contract.layout_fallback_reason == "visual_layout_without_visual"


def test_shared_slide_model_accepts_v5_outline_contract() -> None:
    deck = SlideDeckContent.model_validate({
        "schema_version": "slide_deck_v5",
        "title": "V5",
        "slides": [],
        "deck_outline": {
            "schema_version": "deck_outline_v5",
            "outline_id": "outline-1",
        },
    })

    assert deck.schema_version == "slide_deck_v5"
    assert deck.deck_outline["schema_version"] == "deck_outline_v5"


def test_v5_navigation_slide_can_bind_a_chapter_without_inventing_body_sources() -> None:
    report = validate_slide_deck({
        "schema_version": "slide_deck_v5",
        "title": "V5",
        "slides": [
            {
                "unit_id": "cover",
                "position": 0,
                "layout": "cover",
                "slide_purpose": "orientation",
                "title": "V5",
                "blocks": [],
            },
            {
                "unit_id": "chapter-entry",
                "position": 1,
                "layout": "chapter",
                "slide_purpose": "chapter_open",
                "title": "第一章",
                "section_id": "chapter-1",
                "source_section_ids": ["chapter-1"],
                "source_block_ids": [],
                "blocks": [],
                "quality": {"navigation_only": True},
            },
            {
                "unit_id": "recap",
                "position": 2,
                "layout": "recap",
                "slide_purpose": "course_recap",
                "title": "课程总结",
                "blocks": [{
                    "block_id": "summary",
                    "type": "bullets",
                    "items": ["关键结论"],
                }],
            },
        ],
    })

    assert "slide_source_missing" not in {
        issue["code"] for issue in report["blockers"]
    }


def test_pptx_renderer_uses_resolved_layout_instead_of_requested_layout() -> None:
    unit = SimpleNamespace(
        visuals=[],
        layout="concept",
        quality={
            "requested_layout": "two-column",
            "resolved_layout": "editorial-body",
        },
    )
    editorial_renderer = Mock()
    two_column_renderer = Mock()

    with (
        patch("slide_deck_renderer._fill_background"),
        patch("slide_deck_renderer._footer"),
        patch("slide_deck_renderer._render_editorial_body", editorial_renderer),
        patch("slide_deck_renderer._render_two_column", two_column_renderer),
    ):
        _render_slide(
            Mock(),
            unit,
            1,
            1,
            {"surface": "FFFFFF"},
            Mock(),
        )

    editorial_renderer.assert_called_once()
    two_column_renderer.assert_not_called()


def test_v5_editorial_body_does_not_reserve_a_fake_right_sidebar() -> None:
    unit = SimpleNamespace(
        blocks=[
            SimpleNamespace(
                items=[],
                content="系统边界决定系统与环境之间可以发生的交换。",
                title="",
            ),
        ],
        key_message="",
        eyebrow="核心概念",
        title="系统边界决定交换方式",
    )
    shape = Mock()
    text = Mock()

    with (
        patch("slide_deck_renderer._heading"),
        patch("slide_deck_renderer._shape", shape),
        patch("slide_deck_renderer._text", text),
    ):
        _render_editorial_body(
            Mock(),
            unit,
            {
                "accent": "00F",
                "accent_soft": "DDF",
                "canvas": "FFF",
                "chart_bg": "DDD",
                "ink": "000",
            },
        )

    assert all(float(call.args[1]) < 9.5 for call in shape.call_args_list)
    body_call = next(
        call for call in text.call_args_list
        if call.args[1].startswith("系统边界")
    )
    assert float(body_call.args[4]) >= 10
    assert int(body_call.args[6]) >= 24


def test_title_compiler_rejects_raw_diagram_identifiers() -> None:
    title = compile_page_title_v5(
        explicit_title='> ID: "ThermodynamicSystemClassification"',
        primary_claim="热力学系统按交换方式分为三类",
        body_text="孤立、封闭和开放系统的边界条件不同。",
    )

    assert title == "热力学系统按交换方式分为三类"
    assert "ID:" not in title


def test_v5_quality_gate_rejects_orphan_formula_and_title_duplication() -> None:
    issues = v5_contract_issues([
        {
            "unit_id": "formula-only",
            "title": "内能变化",
            "visuals": [{"kind": "formula", "latex": r"\Delta U=U_2-U_1"}],
            "blocks": [],
            "quality": {
                "requested_layout": "formula-explanation",
                "resolved_layout": "figure-text",
                "resolved_composition": "split-visual",
                "major_region_count": 2,
                "occupied_major_region_count": 1,
            },
        },
        {
            "unit_id": "duplicate-title",
            "title": "系统边界决定可发生的交换",
            "visuals": [],
            "blocks": [{
                "block_id": "body",
                "type": "rich_text",
                "content": "系统边界决定可发生的交换。",
                "items": [],
            }],
            "quality": {
                "requested_layout": "editorial-body",
                "resolved_layout": "editorial-body",
                "resolved_composition": "statement",
                "major_region_count": 1,
                "occupied_major_region_count": 1,
            },
        },
    ])

    assert {issue["code"] for issue in issues} >= {
        "orphan_formula",
        "title_body_duplication",
    }


def test_title_compiler_keeps_explicit_title_and_never_promotes_takeaway() -> None:
    title = compile_page_title_v5(
        explicit_title="热力学系统的三种类型",
        primary_claim="根据系统与环境之间的交互方式，热力学将系统分为三类。",
        body_text="根据系统与环境之间的交互方式，热力学将系统分为三类。",
    )

    assert title == "热力学系统的三种类型"
