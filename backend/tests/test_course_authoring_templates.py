from copy import deepcopy

from course_authoring_templates import (
    attach_formal_course_profile,
    compile_formal_course_context,
)
from course_generation.outline import outline_request_fingerprint


def test_formal_profile_is_a_bounded_generation_snapshot():
    brief = {"subject": "线性代数"}
    attach_formal_course_profile(brief, {
        "course_code": "MATH-202",
        "credits": 4,
        "course_intro": "  建立向量空间与线性变换的结构观  ",
        "course_goal": "能使用线性变换解决典型问题",
        "default_location": "东二-101",
    })

    assert brief["formal_course_profile"] == {
        "course_code": "MATH-202",
        "credits": 4,
        "course_intro": "建立向量空间与线性变换的结构观",
        "default_location": "东二-101",
        "teaching_goals": "能使用线性变换解决典型问题",
    }


def test_formal_profile_change_invalidates_the_outline_input_fingerprint():
    before = {"subject": "线性代数"}
    after = deepcopy(before)
    attach_formal_course_profile(before, {"credits": 2})
    attach_formal_course_profile(after, {"credits": 4})

    first = outline_request_fingerprint(
        topic="线性代数",
        audience="大学生",
        brief=before,
        difficulty_profile={},
    )
    second = outline_request_fingerprint(
        topic="线性代数",
        audience="大学生",
        brief=after,
        difficulty_profile={},
    )

    assert first != second


def test_formal_context_keeps_sources_empty_instead_of_inventing_references():
    context = compile_formal_course_context({
        "course_name": "数字逻辑",
        "course_profile": {
            "target_grade": "大学一年级",
            "assessment_method": "实验与期末设计",
        },
        "teacher_course_brief": {
            "lesson_duration_minutes": 45,
            "course_period_minutes": 45,
            "lecture_count": 16,
            "class_size": 48,
            "class_profile": "学生已修完电路基础，但工程验证经验不足。",
            "additional_requirements": "实验与期末设计",
        },
        "course_plan": {
            "positioning": "从布尔代数进入数字系统设计",
            "learning_objectives": ["能设计并验证基本组合逻辑电路"],
            "measurable_outcomes": ["能完成组合逻辑电路设计并提交验证记录"],
            "outcome_alignment": [{
                "outcome_number": 1,
                "objective_refs": ["学习目标1"],
                "lecture_numbers": [1, 2],
                "assessment_evidence": ["电路作品与验证记录"],
                "coverage_scope": "基本组合逻辑电路",
            }],
            "chapters": [],
        },
    })

    assert context["course_information"]["教学对象"] == "大学一年级"
    assert context["schema_version"] == "formal_course_authoring_v5"
    assert "课程名称" not in context["course_information"]
    assert context["course_information"]["每课时时长"] == "45 分钟"
    assert context["course_information"]["班级规模"] == "48 人"
    assert context["student_profile"] == "学生已修完电路基础，但工程验证经验不足。"
    assert context["assessment_methods"] == ["实验与期末设计"]
    assert context["outcome_alignment"][0]["lecture_numbers"] == [1, 2]
    assert context["teaching_requirements"] == []
    assert context["references"] == []
    assert "不编造" in context["reference_policy"]
    assert [item["label"] for item in context["outline_objective_dimensions"]] == [
        "学习目标", "育人目标", "可测量结果",
    ]
    assert context["lesson_flow_contract"]["required_roles"][-1] == "教学活动照片（教师课后补充）"
