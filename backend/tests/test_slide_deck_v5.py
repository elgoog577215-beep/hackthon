from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pptx import Presentation

from course_document import CourseDocument, CourseSection
from slide_deck import SlideDeckContent, validate_slide_deck
from slide_deck_v3 import (
    ContentFragmentV1,
    PlannedPageV2,
    SlideAllocationPlanV2,
    slide_deck_variant_key,
)
from slide_deck_renderer import (
    _render_editorial_body,
    _render_slide,
    export_structured_slide_deck,
)
from slide_deck_renderer import V5_LAYOUT_RENDERER_NAMES
import slide_deck_renderer
from slide_deck_v4 import allocation_from_story_plan_v2
from slide_deck_v5 import (
    _chapter_recap_slide,
    apply_page_contract_v5,
    compact_story_plan_v5,
    compile_slide_deck_v5,
    compile_deck_outline_v5,
    compile_page_title_v5,
    finalize_v5_quality_report,
    resolve_page_contract_v5,
    summarize_v5_slide_counts,
    v5_contract_issues,
)
from slide_visuals import deterministic_visual_plan, validate_visual_plan
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


def test_v5_rebuilds_visual_plan_when_compaction_changes_page_ids() -> None:
    document = _document(1)
    variant_key = slide_deck_variant_key("teaching", "qizhi-classroom")
    supplied_allocation = SlideAllocationPlanV2(
        title=document.title,
        mode="teaching",
        theme="qizhi-classroom",
        variant_key=variant_key,
        source_document_revision=document.document_revision,
        pages=[
            PlannedPageV2(page_id="slide:title", layout="cover"),
            PlannedPageV2(page_id="slide:roadmap", layout="roadmap"),
            PlannedPageV2(
                page_id="slide:v4:0001",
                layout="editorial-body",
                chapter_id="chapter-1",
            ),
        ],
    )
    compact_allocation = supplied_allocation.model_copy(update={
        "pages": supplied_allocation.pages[:2],
    })
    supplied_visual_plan = deterministic_visual_plan(
        document,
        supplied_allocation,
        [],
    )
    captured: dict[str, object] = {}

    def _compile_v4(*args: object, **kwargs: object) -> dict[str, object]:
        visual_plan = kwargs["visual_plan"]
        allocation_plan = kwargs["allocation_plan"]
        validate_visual_plan(visual_plan, allocation_plan, [])
        captured["visual_plan"] = visual_plan
        captured["allocation_plan"] = allocation_plan
        return {
            "schema_version": "slide_deck_v4",
            "title": document.title,
            "slides": [],
            "quality_report": {"passed": True, "score": 100, "issues": []},
            "quality_summary": {},
        }

    with (
        patch("slide_deck_v5.fragment_course_document", return_value=[]),
        patch("slide_deck_v5.compact_story_plan_v5", return_value=_story(1)),
        patch(
            "slide_deck_v5.allocation_from_story_plan_v2",
            return_value=(compact_allocation, {}),
        ),
        patch("slide_deck_v5.compile_slide_deck_v4", side_effect=_compile_v4),
        patch("slide_deck_v5._materialize_v5_structure", return_value=[]),
        patch(
            "slide_deck_v5.finalize_v5_quality_report",
            return_value={"passed": True, "score": 100, "issues": []},
        ),
    ):
        compile_slide_deck_v5(
            document,
            {},
            story_plan=_story(1),
            allocation_plan=supplied_allocation,
            visual_plan=supplied_visual_plan,
        )

    rebuilt_visual_plan = captured["visual_plan"]
    rebuilt_allocation = captured["allocation_plan"]
    assert [page.page_id for page in rebuilt_visual_plan.pages] == [
        page.page_id for page in rebuilt_allocation.pages
    ]
    assert rebuilt_visual_plan.deck_brief["fallback_reason"] == (
        "v5_compaction_visual_plan_rebuilt"
    )


def test_outline_groups_eight_chapters_into_at_most_six_source_bound_sections() -> None:
    outline = compile_deck_outline_v5(_document(8), _story(8))

    assert 3 <= len(outline.agenda_sections) <= 6
    assert [
        chapter_id
        for section in outline.agenda_sections
        for chapter_id in section.source_chapter_ids
    ] == [f"chapter-{index}" for index in range(1, 9)]
    assert outline.cover.subtitle == "建立一套可迁移的分析框架"
    assert outline.closing.kind == "course_synthesis"


def test_outline_does_not_invent_sections_for_a_single_chapter_course() -> None:
    outline = compile_deck_outline_v5(_document(1), _story(1))

    assert len(outline.agenda_sections) == 1
    assert outline.agenda_sections[0].source_chapter_ids == ["chapter-1"]


def test_v5_story_compaction_selects_complete_semantic_groups_per_section() -> None:
    document = CourseDocument(
        course_id="course-v5-compaction",
        title="课程压缩测试",
        document_revision="doc-rev-1",
        sections=[
            CourseSection(
                section_id="chapter-1",
                title="第一章",
                position=0,
                level=1,
            ),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="1.1 核心主题",
                position=1,
                level=2,
            ),
        ],
    )
    raw = [
        ("title", "heading", "1.1 核心主题"),
        ("core-heading", "heading", "核心概念与背景"),
        ("core-body", "paragraph", "核心概念通过已有正文建立。"),
        ("method-heading", "heading", "技术实现与方法"),
        ("method-body", "paragraph", "先识别条件，再选择步骤。"),
        ("case-heading", "heading", "实战案例"),
        ("case-body", "paragraph", "案例用于检验抽象判断。"),
        ("practice-heading", "heading", "思考与挑战"),
        ("practice-body", "list_item", "请说明结论成立的边界。"),
    ]
    fragments = [
        ContentFragmentV1(
            fragment_id=fragment_id,
            section_id="section-1",
            block_id="section-1-body",
            kind=kind,  # type: ignore[arg-type]
            text=text,
            ordinal=index,
            source_hash=f"hash-{index}",
            role="concept",
            source_kind="course_block",
        )
        for index, (fragment_id, kind, text) in enumerate(raw)
    ]

    compact = compact_story_plan_v5(document, _story(1), fragments)
    chapter = compact.chapters[0]

    assert [episode.scene_kind for episode in chapter.episodes] == [
        "chapter_entry",
        "concept",
        "worked_example",
        "practice_feedback",
        "chapter_recap",
    ]
    selected_ids = {
        fragment_id
        for episode in chapter.episodes
        for beat in episode.beats
        for fragment_id in beat.fragment_ids
    }
    assert {"core-body", "case-body", "practice-body"} <= selected_ids
    assert "method-body" not in selected_ids
    allocation, _ = allocation_from_story_plan_v2(
        document,
        fragments,
        compact,
    )
    teaching_pages = [
        page
        for page in allocation.pages
        if page.fragment_ids
    ]
    assert len(teaching_pages) == 3
    assert all(
        exclusion.reason == "v5_semantic_core"
        for exclusion in allocation.exclusions
    )
    assert {
        exclusion.fragment_id for exclusion in allocation.exclusions
    } >= {"method-heading", "method-body"}
    refined = compact.model_copy(update={
        "planner": "ai",
        "chapters": [
            compact.chapters[0].model_copy(update={
                "episodes": [
                    episode.model_copy(update={
                        "beats": [
                            beat.model_copy(update={
                                "layout_selection_reason": (
                                    "ai_source_bound_directive"
                                ),
                            })
                            for beat in episode.beats
                        ],
                    })
                    for episode in compact.chapters[0].episodes
                ],
            }),
        ],
    })

    recompacted = compact_story_plan_v5(document, refined, fragments)

    assert all(
        beat.layout_selection_reason == "ai_source_bound_directive"
        for chapter in recompacted.chapters
        for episode in chapter.episodes[1:-1]
        for beat in episode.beats
    )
    refined_allocation, _ = allocation_from_story_plan_v2(
        document,
        fragments,
        recompacted,
    )

    assert not any(page.appendix for page in refined_allocation.pages)
    assert {
        exclusion.fragment_id for exclusion in refined_allocation.exclusions
    } >= {"method-heading", "method-body"}
    assert all(
        exclusion.reason == "v5_semantic_core"
        for exclusion in refined_allocation.exclusions
    )


def test_v5_compaction_excludes_formula_without_source_explanation() -> None:
    document = CourseDocument(
        course_id="course-v5-formula-compaction",
        title="公式压缩测试",
        document_revision="doc-rev-1",
        sections=[
            CourseSection(
                section_id="chapter-1",
                title="第一章",
                position=0,
                level=1,
            ),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="1.1 核心主题",
                position=1,
                level=2,
            ),
        ],
    )
    fragments = [
        ContentFragmentV1(
            fragment_id=fragment_id,
            section_id="section-1",
            block_id="section-1-body",
            kind=kind,  # type: ignore[arg-type]
            text=text,
            ordinal=index,
            source_hash=f"hash-{index}",
            role="concept",
            source_kind="course_block",
        )
        for index, (fragment_id, kind, text) in enumerate([
            ("core-heading", "heading", "核心概念"),
            ("core-body", "paragraph", "正文解释用于建立概念。"),
            ("formula-heading", "heading", "热力学第一定律"),
            ("formula-only", "formula", r"$$ \Delta U = Q - W $$"),
        ])
    ]

    compact = compact_story_plan_v5(document, _story(1), fragments)
    allocation, _ = allocation_from_story_plan_v2(
        document,
        fragments,
        compact,
    )

    allocated_ids = {
        fragment_id
        for page in allocation.pages
        for fragment_id in page.fragment_ids
    }
    excluded_ids = {
        exclusion.fragment_id for exclusion in allocation.exclusions
    }
    assert "core-body" in allocated_ids
    assert {"formula-heading", "formula-only"} <= excluded_ids
    assert not any(page.appendix for page in allocation.pages)


def test_ai_refinement_keeps_formula_and_source_explanation_on_one_page() -> None:
    document = CourseDocument(
        course_id="course-v5-formula-binding",
        title="公式绑定测试",
        document_revision="doc-rev-1",
        sections=[
            CourseSection(
                section_id="chapter-1",
                title="第一章",
                position=0,
                level=1,
            ),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="1.1 能量守恒",
                position=1,
                level=2,
            ),
        ],
    )
    fragments = [
        ContentFragmentV1(
            fragment_id=fragment_id,
            section_id="section-1",
            block_id="section-1-body",
            kind=kind,  # type: ignore[arg-type]
            text=text,
            ordinal=index,
            source_hash=f"hash-{index}",
            role="concept",
            source_kind="course_block",
        )
        for index, (fragment_id, kind, text) in enumerate([
            ("formula-heading", "heading", "热力学第一定律"),
            ("formula", "formula", r"$$ \Delta U = Q - W $$"),
            ("formula-explanation", "paragraph", "其中各符号分别表示内能、热量和功。"),
        ])
    ]
    compact = compact_story_plan_v5(document, _story(1), fragments)
    refined = compact.model_copy(update={
        "planner": "ai",
        "chapters": [
            chapter.model_copy(update={
                "episodes": [
                    episode.model_copy(update={
                        "beats": [
                            beat.model_copy(update={
                                "layout_selection_reason": (
                                    "ai_source_bound_directive"
                                ),
                            })
                            for beat in episode.beats
                        ],
                    })
                    for episode in chapter.episodes
                ],
            })
            for chapter in compact.chapters
        ],
    })

    allocation, _ = allocation_from_story_plan_v2(
        document,
        fragments,
        refined,
    )
    formula_pages = [
        page for page in allocation.pages
        if "formula" in page.fragment_ids
    ]

    assert len(formula_pages) == 1
    assert {
        "formula",
        "formula-explanation",
    } <= set(formula_pages[0].fragment_ids)


def test_v5_compaction_keeps_a_complete_enumeration_over_optional_background() -> None:
    document = CourseDocument(
        course_id="course-enumeration",
        title="热力学",
        document_revision="doc-enumeration",
        sections=[
            CourseSection(
                section_id="chapter-1",
                title="第一章 热力学基础",
                position=0,
                level=1,
            ),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="1.1 热力学系统的分类与描述",
                position=1,
                level=2,
            ),
        ],
    )
    raw = [
        ("title", "heading", "1.1 热力学系统的分类与描述"),
        ("core-heading", "heading", "核心概念与背景"),
        (
            "background",
            "paragraph",
            "在热力学中，系统（System）是指我们研究的物理对象或区域，"
            "而环境（Surroundings）则是系统以外的部分。"
            "系统和环境之间的边界可以是实际存在的（如容器壁），"
            "也可以是想象的（如一个气球内的气体）。"
            "系统与环境之间可能有物质、能量甚至信息的交换。",
        ),
        ("promise", "paragraph", "根据系统与环境之间的交互方式，热力学将系统分为三类："),
        ("isolated", "list_item", "孤立系统：既不交换物质，也不交换能量。"),
        ("closed", "list_item", "封闭系统：不交换物质，但可以交换能量。"),
        ("open", "list_item", "开放系统：既可以交换物质，也可以交换能量。"),
        ("summary", "paragraph", "三种类型为后续建模提供边界条件。"),
    ]
    fragments = [
        ContentFragmentV1(
            fragment_id=fragment_id,
            section_id="section-1",
            block_id="section-1-body",
            kind=kind,  # type: ignore[arg-type]
            text=text,
            ordinal=index,
            source_hash=f"hash-{index}",
            role="concept",
            source_kind="course_block",
        )
        for index, (fragment_id, kind, text) in enumerate(raw)
    ]

    compact = compact_story_plan_v5(document, _story(1), fragments)
    concept_beat = next(
        beat
        for episode in compact.chapters[0].episodes
        if episode.scene_kind == "concept"
        for beat in episode.beats
    )

    assert {"promise", "isolated", "closed", "open"} <= set(
        concept_beat.fragment_ids
    )
    assert "background" not in concept_beat.fragment_ids


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


def test_one_prompt_block_cannot_fabricate_a_practice_feedback_region() -> None:
    contract = resolve_page_contract_v5({
        "layout": "practice",
        "blocks": [{
            "block_id": "prompt-only",
            "type": "exercise",
            "items": ["判断系统类型", "说明判断依据"],
        }],
        "quality": {"requested_layout": "practice-feedback"},
    })

    assert contract.resolved_layout == "editorial-body"
    assert contract.layout_fallback_reason == "practice_without_feedback"
    assert contract.major_region_count == 1


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


@pytest.mark.parametrize(
    ("requested_layout", "expected_regions"),
    [
        ("worked-example", 3),
        ("practice-feedback", 2),
    ],
)
def test_instructional_layouts_survive_final_contract_resolution(
    requested_layout: str,
    expected_regions: int,
) -> None:
    blocks = (
        [
            {
                "block_id": "practice-prompt",
                "type": "exercise",
                "content": "先判断系统类型。",
            },
            {
                "block_id": "practice-feedback",
                "type": "bullets",
                "items": ["边界条件一致", "排除其他类型"],
            },
        ]
        if requested_layout == "practice-feedback"
        else [
            {
                "block_id": "instructional-sequence",
                "type": "process",
                "items": ["识别条件", "选择方法", "检查结论"],
            },
        ]
    )
    contract = resolve_page_contract_v5({
        "layout": "concept",
        "blocks": blocks,
        "quality": {"requested_layout": requested_layout},
    })

    assert contract.resolved_layout == requested_layout
    assert contract.major_region_count == expected_regions


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


def test_shared_v5_layout_catalog_matches_pptx_renderer_contract() -> None:
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "shared"
            / "slide-layout-contract-v5.json"
        ).read_text(encoding="utf-8")
    )
    expected = {
        item["layout"]: item["pptx_renderer"]
        for item in catalog["layouts"]
    }

    assert expected == V5_LAYOUT_RENDERER_NAMES
    assert catalog["minimum_title_font_pt"] >= 35
    assert catalog["minimum_body_font_pt"] >= 16
    assert all(
        callable(getattr(slide_deck_renderer, renderer_name))
        for renderer_name in expected.values()
    )


def test_v5_render_review_fixture_exports_all_semantic_compositions(
    tmp_path,
) -> None:
    fixture = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "slide_deck_v5_render_review.json"
        ).read_text(encoding="utf-8")
    )
    output = export_structured_slide_deck(
        fixture,
        tmp_path / "slide-deck-v5-review.pptx",
        require_quality=False,
    )
    presentation = Presentation(output)
    visible_text = "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )

    assert len(presentation.slides) == 5
    visible_lines = {line.strip() for line in visible_text.splitlines()}
    assert {"步骤 1", "步骤 2", "步骤 3", "回答与判断依据", "课程主线"} <= visible_lines
    assert {"已知", "推理", "结论"}.isdisjoint(visible_lines)


def test_pptx_export_uses_v5_quality_contract_for_v5_content(tmp_path) -> None:
    content = {
        "schema_version": "slide_deck_v5",
        "title": "V5 quality routing",
        "slides": [],
    }

    with (
        patch(
            "slide_deck_v5.validate_slide_deck_v5",
            return_value={"passed": True, "blockers": []},
        ) as validate_v5,
        patch("slide_deck_renderer.validate_slide_deck") as validate_legacy,
    ):
        export_structured_slide_deck(
            content,
            tmp_path / "v5-quality-routing.pptx",
            require_quality=True,
            course_data={},
        )

    validate_v5.assert_called_once()
    validate_legacy.assert_not_called()


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


@pytest.mark.parametrize(
    ("resolved_layout", "renderer_name"),
    [
        ("worked-example", "_render_worked_example"),
        ("practice-feedback", "_render_practice_feedback"),
        ("chapter-recap", "_render_chapter_recap"),
        ("course-synthesis", "_render_course_synthesis"),
    ],
)
def test_v5_semantic_layouts_use_dedicated_pptx_renderers(
    resolved_layout: str,
    renderer_name: str,
) -> None:
    unit = SimpleNamespace(
        visuals=[],
        layout="concept",
        quality={"resolved_layout": resolved_layout},
    )
    renderer = Mock()

    with (
        patch("slide_deck_renderer._fill_background"),
        patch("slide_deck_renderer._footer"),
        patch(f"slide_deck_renderer.{renderer_name}", renderer),
    ):
        _render_slide(
            Mock(),
            unit,
            1,
            1,
            {"surface": "FFFFFF"},
            Mock(),
        )

    renderer.assert_called_once()


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


def test_title_compiler_replaces_numbered_section_heading_with_visible_claim() -> None:
    title = compile_page_title_v5(
        explicit_title="1.1 热力学系统的分类与描述",
        primary_claim="1.1 热力学系统的分类与描述",
        body_text=(
            "核心概念与背景\n"
            "在热力学中，系统是我们研究的对象，环境是系统以外的部分。\n"
            "根据系统与环境之间的交互方式，热力学将系统分为三类：\n"
            "孤立系统\n封闭系统\n开放系统"
        ),
    )

    assert title == "热力学系统的三种类型"


def test_title_compiler_prefers_supported_claim_over_source_topic_heading() -> None:
    title = compile_page_title_v5(
        explicit_title="内能的本质",
        primary_claim="内能的本质",
        body_text="内能是系统内所有微观粒子能量的总和。",
        prefer_body_claim=True,
    )

    assert title == "内能是系统内所有微观粒子能量的总和"


def test_title_compiler_prefers_the_lead_definition_over_later_detail() -> None:
    title = compile_page_title_v5(
        explicit_title="内能的本质",
        primary_claim="内能的本质",
        body_text=(
            "内能是系统内所有微观粒子能量的总和。"
            "它由分子平动、转动、振动以及相互作用势能共同构成。"
        ),
        prefer_body_claim=True,
    )

    assert title == "内能是系统内所有微观粒子能量的总和"


def test_title_compiler_strips_template_label_before_selecting_body_claim() -> None:
    title = compile_page_title_v5(
        explicit_title="内能的本质",
        primary_claim="内能的本质",
        body_text=(
            "💡 核心概念与背景 "
            "内能是系统内所有微观粒子能量的总和。"
            "它由分子平动、转动和振动能共同构成。"
        ),
        prefer_body_claim=True,
    )

    assert title == "内能是系统内所有微观粒子能量的总和"


def test_title_compiler_keeps_an_existing_takeaway_title() -> None:
    title = compile_page_title_v5(
        explicit_title="系统边界决定可发生的交换",
        primary_claim="系统边界决定可发生的交换",
        body_text="系统和环境之间存在边界。",
        prefer_body_claim=True,
    )

    assert title == "系统边界决定可发生的交换"


@pytest.mark.parametrize(
    ("template_title", "body"),
    [
        (
            "🏭 实战案例/行业应用",
            "在航天器设计中，速度分布用于检验喷嘴方案。",
        ),
        (
            "✅ 思考与挑战",
            "为什么封闭系统仍然可以和环境交换能量？",
        ),
    ],
)
def test_title_compiler_demotes_template_labels_to_eyebrow(
    template_title: str,
    body: str,
) -> None:
    title = compile_page_title_v5(
        explicit_title=template_title,
        primary_claim=template_title,
        body_text=body,
    )

    assert title not in {template_title, "实战案例/行业应用", "思考与挑战"}
    assert title


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


def test_v5_enumeration_gate_counts_visible_bullet_lines_and_ignores_singular_phrases() -> None:
    slides = [
        {
            "unit_id": "classification",
            "title": "热力学将系统分为三类",
            "blocks": [{
                "type": "statement",
                "content": (
                    "热力学将系统分为三类：\n"
                    "• 孤立系统\n"
                    "• 封闭系统\n"
                    "• 开放系统"
                ),
                "items": [],
            }],
            "visuals": [],
            "quality": {
                "resolved_layout": "editorial-body",
                "occupied_major_region_count": 1,
                "major_region_count": 1,
            },
        },
        {
            "unit_id": "singular-example",
            "title": "一个系统的宏观状态",
            "blocks": [{
                "type": "statement",
                "content": "这里解释一个系统如何由状态变量描述。",
                "items": [],
            }],
            "visuals": [],
            "quality": {
                "resolved_layout": "editorial-body",
                "occupied_major_region_count": 1,
                "major_region_count": 1,
            },
        },
    ]

    issues = v5_contract_issues(slides)

    assert not any(
        issue["code"] == "enumeration_cardinality_mismatch"
        for issue in issues
    )


def test_v5_quality_gate_rejects_incomplete_enumeration_and_section_title() -> None:
    issues = v5_contract_issues([
        {
            "unit_id": "incomplete-classification",
            "title": "1.1 热力学系统的分类与描述",
            "visuals": [],
            "blocks": [
                {
                    "block_id": "promise",
                    "type": "statement",
                    "content": "根据交换方式，热力学系统分为三类：",
                    "items": [],
                },
                {
                    "block_id": "classification",
                    "type": "bullets",
                    "content": "",
                    "items": ["孤立系统"],
                },
            ],
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
        "enumeration_cardinality_mismatch",
        "source_section_heading_as_title",
    }


def test_v5_quality_gate_does_not_treat_quantities_as_visible_list_contracts() -> None:
    slides = [
        {
            "unit_id": "two-vector-spaces",
            "title": "我们从两个向量空间 V 和 W 开始",
            "blocks": [{
                "type": "process",
                "content": "",
                "items": ["可加性"],
            }],
        },
        {
            "unit_id": "three-input-vectors",
            "title": "假设我们有三个线性无关的向量",
            "blocks": [{
                "type": "process",
                "content": "",
                "items": ["初始化", "第二步"],
            }],
        },
        {
            "unit_id": "inline-two-classes",
            "title": "为什么需要 QR 分解",
            "blocks": [{
                "type": "statement",
                "content": (
                    "把食材分成两类：一类是整齐摆放的原料（Q），"
                    "另一类是精确用量的调味料（R）。"
                ),
                "items": [],
            }],
        },
        {
            "unit_id": "pixel-count",
            "title": "应用场景：人脸识别",
            "blocks": [{
                "type": "statement",
                "content": "一张 64x64 像素的灰度图像共有 4096 个像素点。",
                "items": [],
            }],
        },
    ]
    for slide in slides:
        slide["visuals"] = []
        slide["quality"] = {
            "resolved_layout": "editorial-body",
            "major_region_count": 1,
            "occupied_major_region_count": 1,
        }

    issues = v5_contract_issues(slides)

    assert not any(
        issue["code"] == "enumeration_cardinality_mismatch"
        for issue in issues
    )


def test_v5_quality_gate_keeps_explicit_title_enumerations_strict() -> None:
    issues = v5_contract_issues([{
        "unit_id": "incomplete-three-types",
        "title": "热力学系统的三类交换方式",
        "blocks": [{
            "type": "bullets",
            "content": "",
            "items": ["孤立系统", "封闭系统"],
        }],
        "visuals": [],
        "quality": {
            "resolved_layout": "editorial-body",
            "major_region_count": 1,
            "occupied_major_region_count": 1,
        },
    }])

    assert any(
        issue["code"] == "enumeration_cardinality_mismatch"
        and issue["expected_count"] == 3
        and issue["visible_item_count"] == 2
        for issue in issues
    )


def test_v5_compiler_removes_repeated_lead_claim_but_keeps_supporting_items() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "deduplicated-claim",
        "layout": "concept",
        "title": "系统按交换方式分为三类",
        "blocks": [
            {
                "block_id": "lead",
                "type": "rich_text",
                "content": "系统按交换方式分为三类。",
                "items": [],
            },
            {
                "block_id": "classification",
                "type": "bullets",
                "items": ["孤立系统", "封闭系统", "开放系统"],
            },
        ],
        "quality": {"requested_layout": "editorial-body"},
    })

    assert [block["block_id"] for block in slide["blocks"]] == [
        "classification"
    ]
    assert slide["quality"]["resolved_layout"] == "classification-3"
    assert "title_body_duplication" not in {
        issue["code"] for issue in v5_contract_issues([slide])
    }


def test_v5_compiler_removes_only_the_repeated_question_clause() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "question-clause",
        "layout": "practice",
        "title": "✅ 思考与挑战",
        "blocks": [{
            "block_id": "questions",
            "type": "bullets",
            "items": [
                "为什么沙漠地区昼夜温差大？这是否与沙子的比热容有关？",
                "水和油在相同条件下谁需要更多热量？",
            ],
        }],
        "quality": {"requested_layout": "editorial-body"},
    })

    assert slide["title"] == "为什么沙漠地区昼夜温差大"
    assert slide["blocks"][0]["items"] == [
        "这是否与沙子的比热容有关？",
        "水和油在相同条件下谁需要更多热量？",
    ]
    assert not v5_contract_issues([slide])


def test_v5_density_contract_rejects_overflow_without_reducing_font_floor() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "dense-page",
        "layout": "concept",
        "title": "热力学系统的分类",
        "key_message": "",
        "blocks": [{
            "block_id": "dense-body",
            "type": "rich_text",
            "content": "正文" * 220,
            "items": [],
        }],
        "quality": {"requested_layout": "editorial-body"},
    })

    assert slide["quality"]["density_band"] == "overflow"
    assert slide["quality"]["minimum_body_font_pt"] >= 16
    assert slide["quality"]["minimum_title_font_pt"] >= 35
    assert {
        issue["code"] for issue in v5_contract_issues([slide])
    } >= {"body_density_overflow"}


def test_worked_example_with_more_than_three_regions_reflows_without_dropping_items() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "application-list",
        "layout": "case-study",
        "title": "分子速度分布支持多类工程判断",
        "blocks": [
            {
                "block_id": "context",
                "type": "statement",
                "content": "同一统计模型可以服务不同工程场景。",
            },
            {
                "block_id": "applications",
                "type": "bullets",
                "items": ["航天推进", "真空系统", "材料扩散", "稀薄气体流动"],
            },
        ],
        "quality": {"requested_layout": "worked-example"},
    })

    assert slide["quality"]["resolved_layout"] == "editorial-body"
    assert slide["quality"]["layout_fallback_reason"] == (
        "worked_example_item_overflow"
    )
    assert slide["blocks"][1]["items"] == [
        "航天推进",
        "真空系统",
        "材料扩散",
        "稀薄气体流动",
    ]
    assert not v5_contract_issues([slide])


def test_v5_quality_cannot_publish_when_a_retained_nested_gate_is_critical() -> None:
    report = finalize_v5_quality_report(
        previous_quality={
            "passed": True,
            "score": 92,
            "semantic": {
                "passed": False,
                "issues": [{
                    "severity": "critical",
                    "code": "official_source_revision_mismatch",
                    "target": "deck",
                }],
            },
            "visual": {"passed": True, "issues": []},
            "blockers": [],
        },
        slides=[],
        planner="ai",
        fallback_reason="",
    )

    assert report["passed"] is False
    assert report["semantic"]["passed"] is False
    assert report["visual"]["passed"] is True
    assert {
        issue["code"] for issue in report["blockers"]
    } == {"official_source_revision_mismatch"}


def test_v5_quality_cannot_publish_when_any_final_slide_is_critical() -> None:
    report = finalize_v5_quality_report(
        previous_quality={
            "passed": True,
            "score": 100,
            "semantic": {"passed": True, "issues": []},
            "visual": {"passed": True, "issues": []},
            "blockers": [],
        },
        slides=[{
            "unit_id": "slide:v4:0001",
            "quality": {
                "passed": False,
                "issues": [{
                    "severity": "critical",
                    "code": "slide_block_overflow",
                    "slide_id": "slide:v4:0001",
                    "message": "The final slide still exceeds its resolved layout.",
                }],
            },
        }],
        planner="ai",
        fallback_reason="",
    )

    assert report["passed"] is False
    assert "slide_block_overflow" in {
        issue["code"] for issue in report["blockers"]
    }


def test_v5_publishable_ai_fallback_is_a_warning_not_a_blocker() -> None:
    report = finalize_v5_quality_report(
        previous_quality={
            "passed": True,
            "score": 100,
            "semantic": {"passed": True, "issues": []},
            "visual": {"passed": True, "issues": []},
            "blockers": [],
        },
        slides=[],
        planner="deterministic_fallback",
        fallback_reason="invalid_or_failed_ai_story_plan",
    )

    assert report["passed"] is True
    assert report["blockers"] == []
    assert {
        issue["code"] for issue in report["warnings"]
    } == {"ai_story_planner_fallback"}


def test_v5_contract_discards_superseded_v4_capacity_blockers() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "slide:v4:long-course",
        "layout": "concept",
        "composition": "statement",
        "title": "状态变量只取决于系统当前状态",
        "blocks": [{
            "block_id": "definition",
            "type": "rich_text",
            "content": "状态变量与过程路径无关。",
            "items": [],
        }],
        "visuals": [],
        "quality": {
            "passed": False,
            "issues": [{
                "severity": "critical",
                "code": "concept_card_overflow",
                "slide_id": "slide:v4:long-course",
            }],
            "blockers": [{
                "severity": "critical",
                "code": "slide_block_overflow",
                "slide_id": "slide:v4:long-course",
            }],
        },
    })

    assert slide["quality"]["passed"] is True
    assert slide["quality"]["issues"] == []
    assert slide["quality"]["blockers"] == []
    report = finalize_v5_quality_report(
        previous_quality={
            "passed": False,
            "score": 0,
            "semantic": {"passed": True, "issues": []},
            "visual": {"passed": True, "issues": []},
            "blockers": [{
                "severity": "critical",
                "code": "slide_block_overflow",
                "slide_id": "slide:v4:long-course",
            }],
        },
        slides=[slide],
        planner="deterministic_fallback",
        fallback_reason="invalid_or_failed_ai_story_plan",
    )
    assert report["passed"] is True
    assert report["blockers"] == []


def test_v5_slide_counts_include_inserted_navigation_and_chapter_pages() -> None:
    summary = summarize_v5_slide_counts([
        {"unit_id": "slide:title", "quality": {}},
        {"unit_id": "slide:roadmap", "quality": {}},
        {"unit_id": "slide:v5:chapter:1", "quality": {}},
        {"unit_id": "slide:v4:0001", "quality": {}},
        {"unit_id": "slide:v4:leftover:0001", "quality": {"appendix": True}},
    ])

    assert summary == {
        "main_slide_count": 4,
        "appendix_slide_count": 1,
        "total_slide_count": 5,
    }


def test_v5_title_and_item_budgets_are_hard_quality_gates() -> None:
    issues = v5_contract_issues([{
        "unit_id": "over-budget",
        "layout": "recap",
        "title": "这是一个明显超出投影扫读容量且没有进行结构化压缩的页面标题" * 2,
        "blocks": [{
            "block_id": "too-many",
            "type": "bullets",
            "items": [f"结论 {index}" for index in range(8)],
        }],
        "quality": {
            "requested_layout": "chapter-recap",
            "resolved_layout": "chapter-recap",
            "resolved_composition": "statement",
            "major_region_count": 1,
            "occupied_major_region_count": 1,
        },
    }])

    assert {issue["code"] for issue in issues} >= {
        "slide_title_overflow",
        "visible_item_overflow",
    }


@pytest.mark.parametrize(
    ("course_type", "requested_layout", "blocks", "expected_layout"),
    [
        (
            "quantitative",
            "formula-explanation",
            [{
                "block_id": "energy-balance",
                "type": "formula",
                "content": "ΔU = Q + W 表示封闭系统的能量收支。",
                "metadata": {"formula": r"\Delta U = Q + W"},
            }],
            "formula-explanation",
        ),
        (
            "programming",
            "balanced-two-column",
            [
                {
                    "block_id": "source-code",
                    "type": "code",
                    "content": "def total(values):\n    return sum(values)",
                },
                {
                    "block_id": "reading",
                    "type": "rich_text",
                    "content": "先确认输入，再检查返回值和空列表边界。",
                },
            ],
            "balanced-two-column",
        ),
        (
            "humanities",
            "editorial-body",
            [{
                "block_id": "argument",
                "type": "rich_text",
                "content": "史料的作者、语境和受众共同决定证据能够支持的解释范围。",
            }],
            "editorial-body",
        ),
        (
            "business",
            "editorial-body",
            [{
                "block_id": "segments",
                "type": "bullets",
                "items": ["成本领先", "差异化", "聚焦细分市场"],
            }],
            "classification-3",
        ),
        (
            "medical-structural",
            "process-sequence",
            [{
                "block_id": "clinical-path",
                "type": "process",
                "items": ["采集症状", "识别危险信号", "形成鉴别诊断", "安排检查"],
            }],
            "process-sequence",
        ),
    ],
)
def test_v5_structural_evaluation_across_course_types(
    course_type: str,
    requested_layout: str,
    blocks: list[dict[str, object]],
    expected_layout: str,
) -> None:
    slide = apply_page_contract_v5({
        "unit_id": f"evaluation-{course_type}",
        "layout": "concept",
        "title": {
            "quantitative": "能量守恒连接热、功与内能",
            "programming": "函数契约决定边界行为",
            "humanities": "证据必须放回历史语境",
            "business": "竞争战略有三种基本选择",
            "medical-structural": "临床判断沿证据路径推进",
        }[course_type],
        "blocks": blocks,
        "quality": {"requested_layout": requested_layout},
    })

    assert slide["quality"]["resolved_layout"] == expected_layout
    assert slide["quality"]["density_band"] != "overflow"
    assert not v5_contract_issues([slide])


def test_title_compiler_keeps_explicit_title_and_never_promotes_takeaway() -> None:
    title = compile_page_title_v5(
        explicit_title="热力学系统的三种类型",
        primary_claim="根据系统与环境之间的交互方式，热力学将系统分为三类。",
        body_text="根据系统与环境之间的交互方式，热力学将系统分为三类。",
    )

    assert title == "热力学系统的三种类型"


def test_v5_cover_splits_a_long_course_name_into_title_and_subtitle() -> None:
    document = _document(1).model_copy(update={
        "title": "《热力学与统计物理：原理、方法与应用》",
    })

    outline = compile_deck_outline_v5(document, _story(1))
    cover_contract = resolve_page_contract_v5({
        "layout": "cover",
        "title": outline.cover.title,
        "subtitle": outline.cover.subtitle,
        "blocks": [],
        "quality": {"requested_layout": "cover"},
    })

    assert outline.cover.title == "热力学与统计物理"
    assert outline.cover.subtitle == "原理、方法与应用"
    assert cover_contract.resolved_layout == "cover-editorial"


def test_v5_promotes_long_title_detail_into_supporting_copy() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "classification-title",
        "layout": "concept",
        "title": "热力学将系统分为三类：这些分类帮助我们理解不同",
        "key_message": "",
        "blocks": [{
            "block_id": "classification",
            "type": "bullets",
            "items": ["孤立系统", "封闭系统", "开放系统"],
        }],
        "quality": {"requested_layout": "classification-3"},
    })

    assert slide["title"] == "热力学将系统分为三类"
    assert slide["key_message"] == "这些分类帮助我们理解不同"
    assert len(slide["title"]) <= 18


def test_parallel_application_items_never_become_a_worked_reasoning_chain() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "three-parallel-applications",
        "layout": "case-study",
        "scene_kind": "application",
        "beat_role": "mapping",
        "title": "第零定律的实际应用",
        "blocks": [{
            "block_id": "applications",
            "type": "bullets",
            "items": ["空调温控", "冷链运输", "体温测量"],
        }],
        "quality": {"requested_layout": "worked-example"},
    })

    assert slide["quality"]["resolved_layout"] == "parallel-examples"
    assert slide["quality"]["resolved_composition"] == "parallel"
    assert not v5_contract_issues([slide])


def test_chapter_recap_uses_claims_and_a_retrieval_prompt_not_slide_titles() -> None:
    outline = compile_deck_outline_v5(_document(1), _story(1))
    source_slides = [
        {
            "unit_id": "classification",
            "title": "1.1 热力学系统的分类与描述",
            "takeaway": "系统类型取决于它与环境交换物质和能量的方式。",
            "blocks": [],
        },
        {
            "unit_id": "application",
            "title": "实践案例/行业应用",
            "key_message": "第零定律支撑温度测量和温度控制。",
            "blocks": [],
        },
    ]

    recap = _chapter_recap_slide(outline.chapters[0], source_slides)

    assert recap["title"] == "本章必须带走的关键判断"
    assert recap["blocks"][0]["items"] == [
        "系统类型取决于它与环境交换物质和能量的方式。",
        "第零定律支撑温度测量和温度控制。",
    ]
    assert "不看前文" in recap["key_message"]
    assert recap["quality"]["navigation_only"] is False
    assert recap["quality"]["retrieval_recap"] is True


def test_quality_gate_blocks_mixed_question_and_chapter_transition() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "mixed-question-transition",
        "layout": "practice",
        "title": "判断水壶属于哪类系统",
        "blocks": [
            {
                "block_id": "question",
                "type": "exercise",
                "content": "水壶盖子没有打开，这个系统属于哪种类型？",
            },
            {
                "block_id": "transition",
                "type": "statement",
                "content": "本节介绍了系统分类。下一节将深入探讨热力学第一定律。",
            },
        ],
        "quality": {"requested_layout": "two-column"},
    })

    assert "mixed_narrative_jobs" in {
        issue["code"] for issue in v5_contract_issues([slide])
    }
