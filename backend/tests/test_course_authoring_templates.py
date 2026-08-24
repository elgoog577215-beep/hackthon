from copy import deepcopy

from course_authoring_templates import (
    attach_formal_course_profile,
    compile_formal_course_context,
)
from course_outline_planning import outline_request_fingerprint


def test_formal_profile_is_a_bounded_generation_snapshot():
    brief = {"subject": "线性代数"}
    attach_formal_course_profile(brief, {
        "course_code": "MATH-202",
        "credits": 4,
        "course_intro": "  建立向量空间与线性变换的结构观  ",
        "default_location": "不进入生成模板的排课字段",
    })

    assert brief["formal_course_profile"] == {
        "course_code": "MATH-202",
        "credits": 4,
        "course_intro": "建立向量空间与线性变换的结构观",
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
        "course_plan": {
            "positioning": "从布尔代数进入数字系统设计",
            "learning_objectives": ["能设计并验证基本组合逻辑电路"],
            "chapters": [],
        },
    })

    assert context["course_information"]["教学对象"] == "大学一年级"
    assert context["assessment_methods"] == ["实验与期末设计"]
    assert context["references"] == []
    assert "不编造" in context["reference_policy"]
