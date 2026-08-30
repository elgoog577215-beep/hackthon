from copy import deepcopy

from course_generation.prompts import CoursePromptComposer
from course_pedagogy import resolve_pedagogy_profile
from teaching_design import (
    compile_overall_teaching_guidance,
    compile_section_teaching_guidance,
    format_generation_teaching_guidance,
)


def _course():
    node = {
        "node_id": "L2-1-2",
        "parent_node_id": "L1-1",
        "node_level": 2,
        "node_name": "1.2 一次函数的图像与性质",
        "learning_objective": "能够根据图像判断一次函数的变化趋势",
        "scope_boundary": "只处理一次函数图像，不提前展开真实建模",
        "key_points": ["一次函数图像"],
        "knowledge_structure": [],
        "misconceptions": [],
        "assessment": ["完成图像与解析式互译任务"],
        "prerequisite_node_ids": ["L2-1-1"],
        "grounding_contract": {},
        "difficulty_contract": {},
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心教学",
            "block_role": "concept",
            "required": True,
            "output_contract": "解释图像性质",
            "prompt_instruction": "联系斜率解释变化趋势",
        }],
    }
    return {
        "course_id": "course-guidance",
        "course_name": "一次函数",
        "target_audience": "初中二年级学生",
        "generation_request": {
            "target_audience": "已经学习平面直角坐标系的初中二年级学生",
        },
        "subject_pedagogy_profile": {
            "primary_mode": "conceptual",
            "secondary_mode": "worked_examples",
            "rationale": "先用图像建立变化率直觉，再进入代数表达。",
        },
        "course_plan": {
            "course_title": "一次函数",
            "positioning": "把图像、解析式与真实变化关系连接起来",
            "learning_objectives": [
                "理解斜率表示的恒定变化关系",
                "能够在图像与解析式之间转换",
            ],
            "prerequisites": ["平面直角坐标系"],
            "chapters": [{
                "chapter_number": 1,
                "title": "看见恒定的变化",
                "learning_focus": "建立斜率与图像的几何直觉",
                "sections": [{
                    "node_id": "L2-1-1",
                    "title": "从变化率认识斜率",
                    "learning_objective": "能够解释斜率表示的变化关系",
                    "assessment": ["口述斜率的实际意义"],
                }, {
                    "node_id": "L2-1-2",
                    "title": "一次函数的图像与性质",
                    "learning_objective": node["learning_objective"],
                    "scope_boundary": node["scope_boundary"],
                    "assessment": node["assessment"],
                }, {
                    "node_id": "L2-1-3",
                    "title": "一次函数建模",
                    "learning_objective": "能够建立并检验一次函数模型",
                    "assessment": ["完成真实建模作品"],
                }],
            }],
        },
        "course_teaching_plan": {
            "sections": [{
                "node_id": "L2-1-2",
                "knowledge_structure": [{
                    "concept_group": "图像性质",
                    "knowledge_points": [{
                        "name": "一次函数图像",
                        "mastery_criteria": [{
                            "observable_performance": "独立解释图像变化趋势",
                            "verification_method": "出口题",
                        }],
                    }],
                }],
            }],
        },
        "nodes": [node],
    }, node


def test_teacher_view_and_generation_guidance_share_one_macro_contract():
    course, node = _course()

    overall = compile_overall_teaching_guidance(course)
    section = compile_section_teaching_guidance(course, node)
    context = format_generation_teaching_guidance(course, node)

    assert overall["teaching_throughline"] == (
        "先用图像建立变化率直觉，再进入代数表达。"
    )
    assert overall["assessment_methods"] == [
        "口述斜率的实际意义",
        "完成图像与解析式互译任务",
        "完成真实建模作品",
        "出口题",
    ]
    assert section["chapter_learning_focus"] == "建立斜率与图像的几何直觉"
    assert "从变化率认识斜率：能够解释斜率表示的变化关系" in (
        section["handoff_from"]
    )
    assert "一次函数建模：能够建立并检验一次函数模型" in (
        section["handoff_to"]
    )
    assert "教学主线：先用图像建立变化率直觉，再进入代数表达。" in context
    assert "评价证据：完成图像与解析式互译任务" in context


def test_overall_guidance_carries_subject_language_into_existing_lesson_plan_chain():
    course, _node = _course()
    course["generation_request"].update({
        "subject": "微积分",
        "pedagogy_mode": "math_formal",
    })

    overall = compile_overall_teaching_guidance(course)

    assert overall["subject_guidance"]["subject_type"] == "math_formal"
    assert "表征转换" in overall["subject_guidance"]["lesson_plan_language"]
    assert overall["subject_guidance"]["professional_actions"]
    assert overall["subject_guidance"]["quality_rules"]


def test_macro_teaching_design_changes_content_prompt_without_changing_modules():
    course, node = _course()
    composer = CoursePromptComposer()

    _baseline_user, _baseline_system = composer.build_content_prompt(
        course_data=course,
        node=node,
        context="无额外资料",
    )
    changed = deepcopy(course)
    changed["subject_pedagogy_profile"]["rationale"] = (
        "先用真实收费情境提出问题，再从图像归纳变化规律。"
    )
    _guided_user, _guided_system = composer.build_content_prompt(
        course_data=changed,
        node=node,
        context="无额外资料",
    )

    # 节点专属内容现在在 user 消息里，模型收到的是两段拼接。
    baseline = _baseline_system + _baseline_user
    guided = _guided_system + _guided_user

    assert "## 总体教案对本节的引领" in baseline
    assert "先用图像建立变化率直觉，再进入代数表达" in baseline
    assert "先用真实收费情境提出问题，再从图像归纳变化规律" in guided
    assert baseline != guided
    assert "必需模块 `## 核心教学` [角色=concept]" in baseline
    assert "必需模块 `## 核心教学` [角色=concept]" in guided


def test_detailed_lesson_plan_batch_must_translate_overall_guidance():
    course, _node = _course()
    overall = compile_overall_teaching_guidance(course)
    prompt = CoursePromptComposer().build_teaching_plan_batch_v3_prompt(
        course_title="一次函数",
        positioning=overall["positioning"],
        batch_spec={
            "batch_id": "batch-1",
            "section_ids": ["L2-1-2"],
        },
        batch_sections=[{
            "node_id": "L2-1-2",
            "title": "一次函数的图像与性质",
            "learning_objective": "能够根据图像判断一次函数的变化趋势",
            "allowed_module_ids": ["core_explanation"],
        }],
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "一次函数图像",
            "statement": "一次函数图像是一条直线。",
            "owner_node_id": "L2-1-2",
        }],
        section_identities=[{
            "node_id": "L2-1-2",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
        module_catalog=[{
            "module_id": "core_explanation",
            "label": "核心教学",
        }],
        skeleton_revision_id="skeleton-1",
        overall_guidance=overall,
    )

    assert "## 总体教案引领（与教师视图同源，只读）" in prompt
    assert "先用图像建立变化率直觉，再进入代数表达" in prompt
    assert "必须把总体教案的课程成果、教学主线和" in prompt
    assert "不得改变已确认的目录、知识身份或模块集合" in prompt
    assert "知识目标" in prompt
    assert "能力目标" in prompt
    assert "育人目标" in prompt
    assert "育人目标必须由本讲真实内容支撑" in prompt
    assert "不得用创新、迁移或一般课堂活动冒充" in prompt
    assert "不得把所有课程强套成" in prompt


def test_formal_course_baseline_guides_outline_without_becoming_a_second_plan():
    profile = resolve_pedagogy_profile(
        subject="数据结构",
        requirements="理解并实现核心数据结构",
        materials=[],
    )
    prompt = CoursePromptComposer().build_outline_skeleton_v2_prompt(
        subject="数据结构",
        audience="大学二年级",
        brief={
            "course_type": "systematic",
            "course_shape_constraints": {"chapter_count": 4, "section_count": 12},
            "formal_course_profile": {
                "course_code": "CS-201",
                "course_category": "专业基础课",
                "credits": 3,
                "course_intro": "以抽象数据类型与复杂度为主线。",
                "assessment_method": "过程任务与综合项目",
            },
            "teacher_course_brief": {
                "target_audience": "大学二年级",
                "total_class_hours": 48,
                "teaching_context": "blended",
            },
        },
        profile=profile,
        difficulty_profile={},
        gap_assessment={},
        adaptation_decision={},
        material_context="",
    )

    assert "## 正式教学大纲模板契约" in prompt
    assert "其余生成约束" in prompt
    assert '"formal_course_profile"' not in prompt
    assert '"teacher_course_brief"' not in prompt
    assert "CS-201" in prompt
    assert "过程任务与综合项目" in prompt
    assert "当前模型只规划课程定位、目标和目录" in prompt
    assert '"course_title": "课程名"' in prompt
