from __future__ import annotations

from slide_deck_v5 import (
    DeckChapterV5,
    _chapter_recap_slide,
    apply_page_contract_v5,
    split_mixed_intent_slides_v5,
    v5_contract_issues,
)
from slide_deck_renderer import _worked_example_labels


def test_mixed_question_and_transition_are_split_into_separate_narrative_jobs() -> None:
    slides = split_mixed_intent_slides_v5([{
        "unit_id": "mixed-question-transition",
        "position": 5,
        "layout": "practice",
        "slide_purpose": "practice_feedback",
        "scene_kind": "practice_feedback",
        "beat_role": "prompt",
        "title": "水壶盖子没有打开，那么这个系统应该归类为什么类型",
        "key_message": "",
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
    }])

    assert len(slides) == 2
    assert slides[0]["quality"]["requested_layout"] == "question-prompt"
    assert [block["block_id"] for block in slides[0]["blocks"]] == ["question"]
    assert slides[1]["quality"]["requested_layout"] == "hero-claim"
    assert slides[1]["title"] == "下一节：热力学第一定律"
    assert slides[1]["key_message"] == "下一节将深入探讨热力学第一定律。"
    assert slides[1]["blocks"] == []
    transition = apply_page_contract_v5(slides[1])
    assert "body_density_overflow" not in {
        issue["code"] for issue in v5_contract_issues([transition])
    }


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

    assert len(slides) == 2
    assert slides[0]["blocks"][0]["content"] == (
        "水壶盖子没有打开，这个系统属于哪种类型？"
    )
    assert slides[1]["title"] == "下一节：热力学第一定律"
    assert slides[1]["key_message"] == "下一节将深入探讨热力学第一定律。"


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
