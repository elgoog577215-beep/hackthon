from __future__ import annotations

from pptx import Presentation

from slide_deck import SlideSpec
from slide_deck_renderer import (
    _heading,
    _render_practice_feedback,
    _worked_example_labels,
    validate_theme,
)
from slide_deck_v5 import (
    DeckChapterV5,
    _assign_heading_modes_v5,
    _chapter_recap_slide,
    _enrich_practice_feedback_slides_v5,
    apply_page_contract_v5,
    split_mixed_intent_slides_v5,
    v5_contract_issues,
)


def test_mixed_question_and_transition_drops_redundant_navigation_page() -> None:
    slides = split_mixed_intent_slides_v5([{
        "unit_id": "mixed-question-transition",
        "position": 5,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "水壶盖子没有打开，那么这个系统应该归类为什么类型",
        "key_message": "",
        "teaching_job": "用来源问题检查理解",
        "takeaway": "本节内容为后续学习打下基础",
        "narrative_role": "checkpoint",
        "composition": "exercise",
        "blocks": [
            {
                "block_id": "question",
                "type": "exercise",
                "content": "水壶盖子没有打开，这个系统属于哪种类型？",
            },
            {
                "block_id": "transition",
                "type": "statement",
                "content": (
                    "本节介绍了系统分类，并比较了孤立系统、封闭系统和开放系统在"
                    "物质交换、能量交换、边界条件及典型工程情境中的差异。"
                    "这些内容帮助我们建立后续分析所需要的对象边界和状态描述。"
                    "下一节将深入探讨热力学第一定律。"
                ),
            },
        ],
        "quality": {"requested_layout": "two-column"},
    }, {
        "unit_id": "actual-next-page",
        "position": 6,
        "layout": "concept",
        "slide_purpose": "concept",
        "scene_kind": "concept",
        "beat_role": "formal_explanation",
        "title": "1.2 状态变量与过程量",
        "key_message": "",
        "blocks": [{
            "block_id": "definition",
            "type": "rich_text",
            "content": "状态变量只依赖于系统当前状态。",
        }],
    }])

    assert len(slides) == 2
    assert slides[0]["quality"]["requested_layout"] == "question-prompt"
    assert [block["block_id"] for block in slides[0]["blocks"]] == ["question"]
    assert slides[0]["quality"]["removed_redundant_transition"] is True
    assert slides[0]["quality"]["next_topic"] == "状态变量与过程量"
    assert slides[1]["unit_id"] == "actual-next-page"
    assert all(
        slide["quality"].get("requested_layout") != "hero-claim"
        for slide in slides
    )


def test_question_and_transition_inside_one_block_are_split_at_sentence_level() -> None:
    slides = split_mixed_intent_slides_v5([{
        "unit_id": "single-mixed-block",
        "position": 7,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "判断系统类型并衔接下一节",
        "key_message": "",
        "blocks": [{
            "block_id": "mixed",
            "type": "exercise",
            "content": (
                "水壶盖子没有打开，这个系统属于哪种类型？"
                "本节介绍了系统分类。"
                "下一节将深入探讨热力学第一定律。"
            ),
        }],
        "quality": {"requested_layout": "two-column"},
    }])

    assert len(slides) == 1
    assert slides[0]["blocks"][0]["content"] == (
        "水壶盖子没有打开，这个系统属于哪种类型？"
    )
    assert slides[0]["quality"]["removed_redundant_transition"] is True


def test_derived_chapter_recap_compacts_long_claims_before_quality_gate() -> None:
    chapter = DeckChapterV5(
        chapter_id="chapter-density",
        agenda_id="agenda-density",
        position=0,
        eyebrow="第一章",
        title="系统与边界",
        driving_question="系统边界如何决定分析方式？",
        learning_objective="能够依据交换关系判断系统类型",
    )
    source_slides = [
        {
            "unit_id": f"source-{index}",
            "title": f"来源页 {index}",
            "takeaway": (
                f"判断{index}：当研究对象与环境发生物质和能量交换时，"
                "必须同时识别边界条件、交换方向、状态变量及过程约束，"
                "才能选择合适的热力学模型并解释实际现象，同时还要验证"
                "所选假设是否适用于稳态、瞬态和不可逆过程。"
            ),
            "blocks": [],
        }
        for index in range(1, 5)
    ]

    recap = apply_page_contract_v5(_chapter_recap_slide(chapter, source_slides))

    assert "body_density_overflow" not in {
        issue["code"] for issue in v5_contract_issues([recap])
    }
    assert all(len(item) <= 64 for item in recap["blocks"][0]["items"])


def test_worked_example_labels_must_be_explicit_or_neutral() -> None:
    assert _worked_example_labels({}, 3) == ("步骤 1", "步骤 2", "步骤 3")
    assert _worked_example_labels(
        {"worked_step_labels": ["条件", "推演", "验证"]},
        3,
    ) == ("条件", "推演", "验证")


def test_prompt_only_practice_is_enriched_with_grounded_answer_evidence() -> None:
    slides = [
        {
            "unit_id": "concept-system-types",
            "position": 0,
            "chapter_id": "chapter-1",
            "knowledge_refs": ["system-types"],
            "layout": "concept",
            "scene_kind": "explanation",
            "title": "三类热力学系统",
            "blocks": [{
                "block_id": "definitions",
                "type": "bullets",
                "items": [
                    "孤立系统：不交换物质，也不交换能量。",
                    "封闭系统：不交换物质，但可以交换能量。",
                    "开放系统：既可以交换物质，也可以交换能量。",
                ],
            }],
            "quality": {"requested_layout": "classification-3"},
        },
        {
            "unit_id": "practice-system-types",
            "position": 1,
            "chapter_id": "chapter-1",
            "knowledge_refs": ["system-types"],
            "layout": "practice",
            "scene_kind": "practice_feedback",
            "beat_role": "prompt",
            "title": "判断水壶属于哪类系统",
            "blocks": [{
                "block_id": "question",
                "type": "exercise",
                "items": [
                    "水壶盖子没有打开时属于哪类系统？",
                    "盖子打开并有蒸汽逸出时呢？",
                ],
            }],
            "quality": {"requested_layout": "question-prompt"},
        },
    ]

    enriched = _enrich_practice_feedback_slides_v5(slides)
    practice = apply_page_contract_v5(enriched[1])

    assert practice["quality"]["requested_layout"] == "practice-feedback"
    assert practice["quality"]["resolved_layout"] == "practice-feedback"
    assert practice["quality"]["grounded_feedback_source_ids"] == [
        "concept-system-types"
    ]
    assert practice["blocks"][0]["items"] == [
        "水壶盖子没有打开时属于哪类系统？",
        "盖子打开并有蒸汽逸出时呢？",
    ]
    assert practice["blocks"][1]["title"] == "判断依据"
    assert practice["blocks"][1]["items"] == [
        "孤立系统：不交换物质，也不交换能量。",
        "封闭系统：不交换物质，但可以交换能量。",
    ]
    assert practice["blocks"][1]["metadata"]["direct_answer"] is False
    assert practice["quality"]["feedback_mode"] == "shared_evidence"
    assert practice["quality"]["feedback_pair_count"] == 0
    assert practice["quality"]["feedback_evidence_count"] == 2
    assert "practice_feedback_missing_answer" not in {
        issue["code"] for issue in v5_contract_issues([practice])
    }


def test_prompt_only_practice_fails_the_v5_contract_without_feedback() -> None:
    practice = apply_page_contract_v5({
        "unit_id": "prompt-only",
        "position": 0,
        "layout": "practice",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "先判断再说明",
        "blocks": [{
            "block_id": "question",
            "type": "exercise",
            "content": "这个系统属于哪一类？",
        }],
        "quality": {"requested_layout": "question-prompt"},
    })

    assert "practice_feedback_missing_answer" in {
        issue["code"] for issue in v5_contract_issues([practice])
    }


def test_repeated_episode_pages_do_not_force_a_new_visible_heading() -> None:
    slides = _assign_heading_modes_v5([
        {
            "unit_id": "concept-1",
            "position": 0,
            "layout": "concept",
            "slide_purpose": "concept",
            "episode_id": "episode-state",
            "section_id": "section-state",
            "eyebrow": "核心概念",
            "title": "状态变量只由当前状态决定",
            "key_message": "1.2 状态变量与过程量",
            "blocks": [{"block_id": "a", "type": "rich_text", "content": "定义。"}],
            "quality": {},
        },
        {
            "unit_id": "concept-2",
            "position": 1,
            "layout": "concept",
            "slide_purpose": "concept",
            "episode_id": "episode-state",
            "section_id": "section-state",
            "eyebrow": "核心概念",
            "title": "温度和压力都是状态变量",
            "key_message": "",
            "blocks": [{"block_id": "b", "type": "rich_text", "content": "举例。"}],
            "quality": {},
        },
    ])

    assert slides[0]["quality"]["heading_mode"] == "full"
    assert slides[0]["quality"]["section_label"] == "1.2 状态变量与过程量"
    assert slides[1]["quality"]["heading_mode"] == "hidden"
    assert slides[1]["quality"]["section_label"] == "1.2 状态变量与过程量"
    assert slides[1]["title"] == "温度和压力都是状态变量"


def test_export_keeps_hidden_heading_as_metadata_only() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    unit = SlideSpec.model_validate({
        "unit_id": "continuation",
        "position": 0,
        "layout": "concept",
        "slide_purpose": "concept",
        "eyebrow": "核心概念",
        "title": "温度和压力都是状态变量",
        "blocks": [],
        "quality": {
            "heading_mode": "hidden",
            "section_label": "1.2 状态变量与过程量",
        },
    })

    _heading(slide, unit, validate_theme("qizhi-classroom"))

    visible_text = "\n".join(
        shape.text
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )
    assert "1.2 状态变量与过程量" in visible_text
    assert "温度和压力都是状态变量" not in visible_text


def test_export_pairs_each_practice_question_with_its_answer() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    unit = SlideSpec.model_validate({
        "unit_id": "paired-practice",
        "position": 0,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "eyebrow": "理解检查",
        "title": "判断系统类型",
        "blocks": [
            {
                "block_id": "questions",
                "type": "exercise",
                "items": ["盖子关闭时属于哪类系统？", "盖子打开时呢？"],
            },
            {
                "block_id": "answers",
                "type": "callout",
                "items": ["封闭系统。", "开放系统。"],
            },
        ],
        "quality": {"resolved_layout": "practice-feedback"},
    })

    _render_practice_feedback(slide, unit, validate_theme("qizhi-classroom"))

    text_shapes = {
        shape.text: shape
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False) and shape.text
    }
    assert text_shapes["盖子关闭时属于哪类系统？"].top == text_shapes["封闭系统。"].top
    assert text_shapes["盖子打开时呢？"].top == text_shapes["开放系统。"].top


def test_export_does_not_present_related_evidence_as_direct_answers() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    unit = SlideSpec.model_validate({
        "unit_id": "shared-evidence",
        "position": 0,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "eyebrow": "理解检查",
        "title": "判断系统类型",
        "blocks": [
            {
                "block_id": "questions",
                "type": "exercise",
                "items": ["盖子关闭时属于哪类系统？", "盖子打开时呢？"],
            },
            {
                "block_id": "evidence",
                "type": "callout",
                "items": ["封闭系统不交换物质。", "开放系统可以交换物质。"],
                "metadata": {"direct_answer": False},
            },
        ],
        "quality": {
            "resolved_layout": "practice-feedback",
            "feedback_mode": "shared_evidence",
        },
    })

    _render_practice_feedback(slide, unit, validate_theme("qizhi-classroom"))

    labels = [
        shape.text
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False) and shape.text
    ]
    assert labels.count("判断依据") == 1
    assert not any("回答与判断依据" in label for label in labels)
