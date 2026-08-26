from models import CourseGenerationRequest
from teaching_semantics import (
    compile_course_semantics,
    order_teaching_blocks,
    recommend_lesson_type,
)


def test_course_semantics_keep_purpose_subject_and_teaching_type_separate():
    semantics = compile_course_semantics(
        learning_purpose="systematic",
        legacy_course_type="systematic",
        subject_type="natural_science",
        course_teaching_type="laboratory",
    )

    assert semantics["learning_purpose_label"] == "系统学习"
    assert semantics["subject_type_label"] == "自然科学"
    assert semantics["course_teaching_type_label"] == "实验课"
    assert semantics["course_lesson_type_distribution"]["experiment_inquiry"] == 65


def test_legacy_inquiry_becomes_a_strategy_inside_systematic_seminar_course():
    semantics = compile_course_semantics(
        legacy_course_type="inquiry",
        subject_type="humanities_social",
        composition_style="inquiry_driven",
    )

    assert semantics["learning_purpose"] == "systematic"
    assert semantics["course_teaching_type"] == "seminar"
    assert semantics["internal_teaching_strategies"] == ["problem_inquiry"]


def test_course_teaching_type_controls_the_session_arc_without_erasing_session_type():
    assert recommend_lesson_type(
        "laboratory",
        phase="opening",
        legacy_candidate="theory",
    ) == "theory"
    assert recommend_lesson_type(
        "laboratory",
        phase="development",
        legacy_candidate="practice",
    ) == "experiment_inquiry"
    assert recommend_lesson_type(
        "laboratory",
        phase="closing",
        legacy_candidate="experiment_inquiry",
    ) == "review_assessment"


def test_lesson_type_orders_blocks_inside_each_section_only():
    blocks = [
        {"block_id": "a1", "section_node_id": "a", "role": "activity"},
        {"block_id": "a2", "section_node_id": "a", "role": "orientation"},
        {"block_id": "b1", "section_node_id": "b", "role": "feedback"},
        {"block_id": "b2", "section_node_id": "b", "role": "application"},
    ]

    ordered = order_teaching_blocks(blocks, "practice")

    assert [item["block_id"] for item in ordered] == ["a2", "a1", "b2", "b1"]


def test_generation_request_persists_new_semantics_and_keeps_legacy_course_type():
    request = CourseGenerationRequest.model_validate({
        "subject": "大学物理实验",
        "learning_purpose": "systematic",
        "course_teaching_type": "laboratory",
        "pedagogy_mode": "natural_science",
        "course_intent": {
            "type": "systematic",
            "learning_goal": "建立实验设计与数据判断能力",
        },
    })

    assert request.course_type == "systematic"
    assert request.learning_purpose == "systematic"
    assert request.course_teaching_type == "laboratory"
    assert request.pedagogy_mode == "natural_science"
