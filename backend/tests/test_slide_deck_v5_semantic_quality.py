from __future__ import annotations

from slide_deck_v5 import split_mixed_intent_slides_v5
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
                "content": "本节介绍了系统分类。下一节将深入探讨热力学第一定律。",
            },
        ],
        "quality": {"requested_layout": "two-column"},
    }])

    assert len(slides) == 2
    assert slides[0]["quality"]["requested_layout"] == "question-prompt"
    assert [block["block_id"] for block in slides[0]["blocks"]] == ["question"]
    assert slides[1]["quality"]["requested_layout"] == "hero-claim"
    assert slides[1]["title"] == "下一节：热力学第一定律"
    assert [block["block_id"] for block in slides[1]["blocks"]] == ["transition"]


def test_worked_example_labels_must_be_explicit_or_neutral() -> None:
    assert _worked_example_labels({}, 3) == ("步骤 1", "步骤 2", "步骤 3")
    assert _worked_example_labels(
        {"worked_step_labels": ["条件", "推演", "验证"]},
        3,
    ) == ("条件", "推演", "验证")
