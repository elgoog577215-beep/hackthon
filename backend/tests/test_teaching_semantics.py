from models import CourseGenerationRequest
from teaching_semantics import (
    compile_course_semantics,
    compile_lesson_semantics,
    compile_teaching_block_contract,
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
    assert semantics["teaching_semantics_version"] == "teaching_semantics_v3"
    assert semantics["teaching_definition"]["teacher_role"].startswith("教师是课程共同设计者")
    assert semantics["subject_type_contract"]["professional_moves"] == [
        "观察现象", "提出假设", "建立模型", "实验或数据检验", "解释边界",
    ]


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
    ) == "experiment_inquiry"


def test_lesson_type_orders_blocks_inside_each_section_only():
    blocks = [
        {"block_id": "a1", "section_node_id": "a", "role": "activity"},
        {"block_id": "a2", "section_node_id": "a", "role": "orientation"},
        {"block_id": "b1", "section_node_id": "b", "role": "feedback"},
        {"block_id": "b2", "section_node_id": "b", "role": "application"},
    ]

    ordered = order_teaching_blocks(blocks, "practice")

    assert [item["block_id"] for item in ordered] == ["a2", "a1", "b2", "b1"]


def test_lesson_compiler_turns_type_and_constraints_into_a_classroom_contract():
    semantics = compile_lesson_semantics(
        learning_purpose="project",
        subject_type="programming_engineering",
        course_teaching_type="project",
        lesson_type="project_workshop",
        phase="development",
        lesson_goal="完成可测试的接口原型",
        classroom_constraints={
            "lesson_duration_minutes": 90,
            "class_size": 36,
            "unknown_field": "ignored",
        },
    )

    assert semantics["lesson_type_label"] == "项目工作坊"
    assert semantics["required_learning_cycle"][-2:] == ["展示评审", "迭代提交"]
    assert semantics["classroom_constraints"] == {
        "lesson_duration_minutes": 90,
        "class_size": 36,
    }
    assert "完成可测试的接口原型" in semantics["lesson_type_recommendation_reason"]


def test_teaching_block_contract_closes_action_evidence_feedback_and_adaptation():
    block = compile_teaching_block_contract(
        {"block_id": "b1", "role": "activity", "purpose": "完成实验"},
        lesson_type="experiment_inquiry",
    )

    assert block["engagement_mode"] == "constructive"
    assert block["student_activity"] == "操作、讨论、制作或协作解决"
    assert block["expected_output"] == "过程记录、作品或协作结论"
    assert len(block["adaptation_options"]) == 3
    assert block["block_contract_version"] == "teaching_semantics_v3"


def test_subject_standard_pack_resolves_discipline_and_drives_block_language():
    semantics = compile_lesson_semantics(
        learning_purpose="systematic",
        subject_type="math_formal",
        discipline_hint="大学微积分",
        course_teaching_type="theory",
        lesson_type="theory_practice",
    )
    pack = semantics["course_semantics"]["subject_standard_pack"]

    assert pack["discipline_profile_id"] == "higher_mathematics"
    assert pack["schema_version"] == "subject_standard_pack_v1"
    assert "直观解释不能代替形式论证" in pack["quality_rules"]

    block = compile_teaching_block_contract(
        {"block_id": "proof", "role": "reasoning"},
        lesson_type="theory_practice",
        subject_standard_pack=pack,
    )
    assert "每一步依据" in block["teacher_activity"]
    assert block["discipline_profile_id"] == "higher_mathematics"


def test_auto_subject_resolution_uses_topic_without_a_parallel_prompt_chain():
    semantics = compile_course_semantics(
        subject_type="auto",
        discipline_hint="临床护理评估",
        course_teaching_type="practice",
    )

    assert semantics["subject_type"] == "life_medical"
    assert semantics["subject_standard_pack"]["discipline_profile_id"] == "nursing"

    discussion = compile_teaching_block_contract(
        {"block_id": "b2", "role": "activity", "purpose": "共同修订判断"},
        lesson_type="case_discussion",
    )
    assert discussion["engagement_mode"] == "interactive"


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
