from __future__ import annotations

from pptx import Presentation

from slide_deck import SlideSpec
from slide_deck_renderer import (
    _heading,
    _heading_excerpt,
    _render_practice_feedback,
    _uses_visual_directed_renderer,
    _worked_example_labels,
    validate_theme,
)
from slide_deck_v5 import (
    DeckChapterV5,
    _assign_heading_modes_v5,
    _chapter_recap_slide,
    _enrich_practice_feedback_slides_v5,
    _normalize_concept_definition_slide_v5,
    _structure_long_editorial_prose_v5,
    apply_page_contract_v5,
    compile_page_title_v5,
    split_mixed_intent_slides_v5,
    v5_contract_issues,
)


def test_standalone_micro_transition_is_folded_into_previous_page_metadata() -> None:
    slides = split_mixed_intent_slides_v5([
        {
            "unit_id": "practice",
            "position": 0,
            "scene_kind": "practice_feedback",
            "beat_role": "prompt",
            "title": "判断系统类型",
            "blocks": [{
                "block_id": "question",
                "type": "exercise",
                "content": "水壶盖子关闭时属于哪类系统？",
            }],
            "quality": {},
        },
        {
            "unit_id": "slide:v4:0003:transition",
            "position": 1,
            "scene_kind": "transition",
            "beat_role": "transition",
            "title": "下一节：热力学第一定律",
            "blocks": [{
                "block_id": "transition",
                "type": "statement",
                "content": "下一节将深入探讨热力学第一定律。",
            }],
            "quality": {},
        },
        {
            "unit_id": "next-concept",
            "position": 2,
            "scene_kind": "concept",
            "title": "热力学第一定律描述能量守恒",
            "blocks": [],
            "quality": {},
        },
    ])

    assert [slide["unit_id"] for slide in slides] == [
        "practice",
        "next-concept",
    ]
    assert slides[0]["quality"]["removed_redundant_transition"] is True
    assert slides[0]["quality"]["removed_transition_unit_ids"] == [
        "slide:v4:0003:transition"
    ]
    assert slides[0]["quality"]["next_topic"] == "热力学第一定律描述能量守恒"


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
    assert not {
        "recap_item_incomplete",
        "recap_retrieval_prompt_missing",
    } & {issue["code"] for issue in v5_contract_issues([recap])}


def test_concept_definition_is_promoted_and_generic_label_is_removed() -> None:
    normalized = _normalize_concept_definition_slide_v5({
        "unit_id": "state-variable",
        "scene_kind": "concept",
        "title": "状态变量是指只依赖于系统当前状态的",
        "blocks": [
            {
                "block_id": "context",
                "type": "rich_text",
                "title": "核心概念与背景",
                "content": "在热力学中，宏观性质通常分为两类物理量。",
            },
            {
                "block_id": "definition-source",
                "type": "rich_text",
                "content": "状态变量是指只依赖于系统当前状态的物理量。",
            },
        ],
        "quality": {},
    })
    contracted = apply_page_contract_v5(normalized)

    assert contracted["blocks"][0]["title"] == "定义"
    assert contracted["blocks"][0]["content"] == (
        "状态变量是指只依赖于系统当前状态的物理量。"
    )
    assert contracted["blocks"][0]["metadata"]["semantic_role"] == "definition"
    assert all(
        block.get("title") != "核心概念与背景"
        for block in contracted["blocks"]
    )
    assert contracted["title"] == "状态变量只取决于系统当前状态"
    assert "concept_definition_missing" not in {
        issue["code"] for issue in v5_contract_issues([contracted])
    }


def test_long_foundation_claim_is_compressed_without_mid_word_truncation() -> None:
    title = compile_page_title_v5(
        explicit_title=(
            "热力学第零定律是热力学四大定律中最基础的一条，"
            "它是温度这一物理量的定义基础。"
        ),
        primary_claim="",
        body_text="",
        fallback_context="",
    )

    assert title == "热力学第零定律奠定温度定义基础"
    assert not title.endswith("最基")


def test_title_compiler_rejects_markdown_internal_production_labels() -> None:
    title = compile_page_title_v5(
        explicit_title="本节知识规范名称",
        primary_claim=(
            "**知识规范名称：MonoBehaviour 脚本命名规范与生命周期回调执行顺序**"
        ),
        body_text=(
            "MonoBehaviour 脚本命名规范与生命周期回调执行顺序。"
            "本节通过创建符合规范的脚本验证初始化时序。"
        ),
        fallback_context="脚本生命周期",
    )

    assert title
    assert "知识规范名称" not in title
    assert "生命周期" in title or "MonoBehaviour" in title


def test_title_compiler_prefers_source_heading_over_generic_teaching_job() -> None:
    title = compile_page_title_v5(
        explicit_title="说明结论如何从条件推出",
        primary_claim="1. Inspector 参数实时热更机制",
        body_text=(
            "Unity 的 Inspector 面板不仅是属性查看器，"
            "也是运行时参数控制台。"
        ),
        fallback_context="说明结论如何从条件推出",
    )

    assert title == "Inspector 参数实时热更机制"


def test_page_contract_preserves_visible_sequence_for_continuation_titles() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "slide:v5:continuation:002",
        "layout": "concept",
        "title": "Collider Is Trigger 属性与碰撞事件路由机制",
        "takeaway": "Collider Is Trigger 属性与碰撞事件路由机制",
        "blocks": [{
            "block_id": "conditions",
            "type": "statement",
            "title": "",
            "content": "至少有一个物体必须挂载非运动学的 Rigidbody 组件。",
            "items": [],
        }],
        "quality": {
            "requested_layout": "editorial-body",
            "continuation_of": "slide:v5:continuation:001",
            "continuation_index": 2,
            "continuation_total": 4,
            "title_character_budget": 18,
        },
    })

    assert slide["title"].startswith("属性与碰撞事件路由机制")
    assert slide["title"].endswith("（续2/4）")


def test_page_contract_keeps_the_only_source_claim_for_hero_quality_audit() -> None:
    slide = apply_page_contract_v5({
        "unit_id": "slide:v5:source-hero",
        "layout": "concept",
        "title": "建立本节核心概念与边界",
        "key_message": "第 1 章概念",
        "takeaway": "",
        "blocks": [{
            "block_id": "source-claim",
            "type": "statement",
            "title": "",
            "content": "这是第 1 章的课程正文与方法说明。",
            "items": [],
            "metadata": {"source_fragment_ids": ["fragment-1"]},
        }],
        "visuals": [],
        "quality": {"requested_layout": "editorial-body"},
    })

    assert slide["title"] == "这是第 1 章的课程正文与方法说明"
    assert slide["blocks"][0]["content"].startswith("这是第 1 章")
    assert slide["quality"]["resolved_layout"] == "hero-claim"
    assert slide["quality"]["suppress_redundant_body"] is True


def test_numbered_semantic_heading_recovers_an_incomplete_body_excerpt() -> None:
    title = compile_page_title_v5(
        explicit_title="卡诺循环（Carnot",
        primary_claim="3.2 卡诺定理与最大效率",
        body_text=(
            "在热力学中，卡诺循环（Carnot Cycle）是最早提出的一个"
            "理想化热机模型。"
        ),
        fallback_context="热力学第二定律",
        prefer_body_claim=True,
    )

    assert title == "卡诺定理与最大效率"


def test_incomplete_body_claim_does_not_replace_a_complete_semantic_title() -> None:
    title = compile_page_title_v5(
        explicit_title="内能的本质",
        primary_claim="内能的本质",
        body_text="从微观角度来看，内能 U 包括：",
        fallback_context="热力学第一定律",
        prefer_body_claim=True,
    )

    assert title == "内能的本质"


def test_complete_question_without_terminal_punctuation_is_not_blocked() -> None:
    title = compile_page_title_v5(
        explicit_title="从热力学角度看，这是由什么驱动的",
        primary_claim="思考与挑战",
        body_text="",
        fallback_context="溶液热力学",
    )
    issues = v5_contract_issues([{
        "unit_id": "practice-question",
        "title": title,
        "blocks": [],
        "quality": {},
    }])

    assert title == "从热力学角度看，这是由什么驱动的"
    assert "incomplete_title_claim" not in {
        issue["code"] for issue in issues
    }


def test_title_ending_in_a_dependent_conjunction_is_blocked() -> None:
    issues = v5_contract_issues([{
        "unit_id": "dependent-title",
        "title": "碰撞回调事件的封装与分层处理模式以及",
        "blocks": [],
        "quality": {},
    }])

    assert "incomplete_title_claim" in {
        issue["code"] for issue in issues
    }


def test_recap_excludes_question_morphology_and_instructional_prompts() -> None:
    chapter = DeckChapterV5(
        chapter_id="chapter-declarative",
        agenda_id="agenda-declarative",
        position=0,
        eyebrow="第一章",
        title="系统分类",
        driving_question="如何判断系统类型？",
        learning_objective="能够根据交换关系判断系统类型。",
    )
    recap = _chapter_recap_slide(chapter, [
        {
            "unit_id": "question-source",
            "title": "判断系统类型",
            "takeaway": "水壶盖子关闭时应该归类为什么类型",
            "blocks": [],
        },
        {
            "unit_id": "instruction-source",
            "title": "理解检查",
            "takeaway": "考虑空调制冷的过程",
            "blocks": [],
        },
        {
            "unit_id": "declarative-source",
            "title": "封闭系统不交换物质",
            "takeaway": "封闭系统不与外界交换物质，但可以交换能量。",
            "blocks": [],
        },
    ])

    assert recap["blocks"][0]["items"] == [
        "封闭系统不与外界交换物质，但可以交换能量。"
    ]


def test_optional_visual_does_not_override_v5_practice_composition() -> None:
    unit = SlideSpec.model_validate({
        "unit_id": "practice-with-visual",
        "position": 0,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "title": "判断系统类型",
        "blocks": [],
        "visuals": [{
            "visual_id": "optional-relation",
            "kind": "relational_diagram",
            "purpose": "structure",
            "alt_text": "可选关系图",
        }],
        "quality": {"resolved_layout": "practice-feedback"},
    })

    assert _uses_visual_directed_renderer(unit, "practice-feedback") is False
    assert _uses_visual_directed_renderer(unit, "figure-text") is True


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


def test_generated_practice_answers_are_bound_to_stable_question_ids() -> None:
    enriched = _enrich_practice_feedback_slides_v5([{
        "unit_id": "generated-practice",
        "position": 0,
        "chapter_id": "chapter-1",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "判断系统类型",
        "blocks": [{
            "block_id": "questions",
            "type": "exercise",
            "items": [
                "水壶盖子关闭时属于哪类系统？",
                "水壶盖子打开并有蒸汽逸出时呢？",
            ],
        }],
        "quality": {
            "question_ids": ["pptq_closed", "pptq_open"],
            "generated_practice_answers": [
                {
                    "question_index": 0,
                    "question_id": "pptq_closed",
                    "answer_source": "llm_generated",
                    "answer_text": "属于封闭系统，因为没有物质穿过边界。",
                    "supporting_fragment_ids": ["definition-closed"],
                },
                {
                    "question_index": 1,
                    "question_id": "pptq_open",
                    "answer_source": "llm_generated",
                    "answer_text": "属于开放系统，因为蒸汽会穿过边界。",
                    "supporting_fragment_ids": ["definition-open"],
                },
            ],
        },
    }])
    practice = apply_page_contract_v5(enriched[0])
    prompt = practice["blocks"][0]
    answer = practice["blocks"][1]

    assert practice["quality"]["answer_generation_mode"] == "llm_generated"
    assert answer["metadata"]["answer_for_question_ids"] == (
        prompt["metadata"]["question_ids"]
    )
    assert answer["metadata"]["source_fragment_ids"] == [
        "definition-closed",
        "definition-open",
    ]
    assert not {
        "practice_direct_answer_unbound",
        "practice_direct_answer_count_mismatch",
    } & {issue["code"] for issue in v5_contract_issues([practice])}


def test_compound_visible_prompt_coalesces_fragment_level_generated_answers() -> None:
    enriched = _enrich_practice_feedback_slides_v5([{
        "unit_id": "compound-generated-practice",
        "position": 0,
        "chapter_id": "chapter-1",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "判断并说明理由",
        "blocks": [{
            "block_id": "compound-question",
            "type": "exercise",
            "content": "盖子关闭时属于哪类系统？盖子打开时呢？",
        }],
        "quality": {
            "generated_practice_answers": [
                {
                    "question_index": 0,
                    "answer_text": "盖子关闭时属于封闭系统。",
                    "supporting_fragment_ids": ["definition-closed"],
                },
                {
                    "question_index": 1,
                    "answer_text": "盖子打开时属于开放系统。",
                    "supporting_fragment_ids": ["definition-open"],
                },
            ],
        },
    }])
    practice = apply_page_contract_v5(enriched[0])
    prompt = practice["blocks"][0]
    answer = practice["blocks"][1]

    assert practice["quality"]["answer_generation_mode"] == "llm_generated"
    assert len(answer["items"]) == 1
    assert "封闭系统" in answer["items"][0]
    assert "开放系统" in answer["items"][0]
    assert answer["metadata"]["answer_for_question_ids"] == (
        prompt["metadata"]["question_ids"]
    )
    assert not {
        "practice_direct_answer_unbound",
        "practice_direct_answer_count_mismatch",
    } & {issue["code"] for issue in v5_contract_issues([practice])}


def test_direct_answers_with_missing_question_identity_fail_the_contract() -> None:
    practice = apply_page_contract_v5({
        "unit_id": "unbound-practice",
        "position": 0,
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "判断系统类型",
        "blocks": [
            {
                "block_id": "questions",
                "type": "exercise",
                "items": ["问题一？", "问题二？"],
                "metadata": {
                    "semantic_role": "prompt",
                    "question_ids": ["question-1", "question-2"],
                },
            },
            {
                "block_id": "answers",
                "type": "callout",
                "items": ["答案一。", "答案二。"],
                "metadata": {
                    "semantic_role": "answer",
                    "direct_answer": True,
                    "answer_for_question_ids": ["question-1"],
                },
            },
        ],
        "quality": {
            "requested_layout": "practice-feedback",
            "feedback_mode": "paired",
        },
    })

    assert "practice_direct_answer_unbound" in {
        issue["code"] for issue in v5_contract_issues([practice])
    }


def test_repeated_episode_pages_keep_their_distinct_visible_heading() -> None:
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
    assert slides[1]["quality"]["heading_mode"] == "full"
    assert slides[1]["quality"]["section_label"] == "1.2 状态变量与过程量"
    assert slides[1]["title"] == "温度和压力都是状态变量"


def test_export_keeps_the_page_claim_visible_even_if_legacy_metadata_hides_it() -> None:
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
    assert "温度和压力都是状态变量" in visible_text


def test_renderer_does_not_hard_cut_a_complete_compiled_heading() -> None:
    title = "碰撞回调事件的封装与分层处理模式以及性能裁剪策略"

    assert _heading_excerpt(title) == title


def test_long_editorial_objective_is_structured_into_three_visible_points() -> None:
    slide = {
        "unit_id": "slide:v5:long-objective",
        "layout": "concept",
        "slide_purpose": "concept",
        "scene_kind": "concept",
        "title": "Input System connects actions to movement",
        "blocks": [{
            "block_id": "objective",
            "type": "statement",
            "title": "",
            "content": (
                "This lesson configures the Input System and defines an Action Map. "
                "Learners create Move and Jump actions with explicit bindings. "
                "The final script reads action data and drives movement in the scene."
            ),
            "items": [],
            "metadata": {"fragment_ids": ["fragment-objective"]},
        }],
        "visuals": [],
        "quality": {
            "requested_layout": "editorial-body",
            "resolved_layout": "editorial-body",
        },
    }

    structured = _structure_long_editorial_prose_v5(slide)

    assert structured["quality"]["requested_layout"] == "classification-3"
    assert structured["blocks"][0]["type"] == "bullets"
    assert len(structured["blocks"][0]["items"]) == 3
    assert structured["blocks"][0]["metadata"]["fragment_ids"] == [
        "fragment-objective"
    ]


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


def test_export_pairs_answers_by_identity_even_when_answer_order_differs() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    unit = SlideSpec.model_validate({
        "unit_id": "identity-paired-practice",
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
                "metadata": {
                    "question_ids": ["closed", "open"],
                },
            },
            {
                "block_id": "answers",
                "type": "callout",
                "items": ["开放系统。", "封闭系统。"],
                "metadata": {
                    "semantic_role": "answer",
                    "answer_for_question_ids": ["open", "closed"],
                },
            },
        ],
        "quality": {
            "resolved_layout": "practice-feedback",
            "feedback_mode": "paired",
        },
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
