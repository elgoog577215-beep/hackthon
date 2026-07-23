import pytest

from course_pedagogy import (
    LESSON_ARCHETYPES,
    PedagogyMode,
    SUBJECT_VARIANTS,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    resolve_pedagogy_profile,
)
from course_prompt_composer import CoursePromptComposer
from course_teaching_plan_projection import project_course_teaching_plan


CASES = [
    (
        "general",
        "摄影入门",
        "理解概念并掌握方法",
        [
            ("认识曝光", "理解曝光概念"),
            ("曝光操作步骤", "掌握操作流程"),
            ("参数比较", "比较不同参数"),
            ("场景应用", "解决具体案例"),
            ("综合作品", "完成迁移成果"),
        ],
        [
            "general_concept_building",
            "general_method_workshop",
            "general_comparison_decision",
            "general_case_application",
            "general_transfer_synthesis",
        ],
    ),
    (
        "math_formal",
        "高等数学",
        "推导证明并完成数学建模",
        [
            ("函数的图像直觉", "连接图像与符号表示"),
            ("导数计算例题", "选择方法求解"),
            ("中值定理证明", "构造完整证明"),
            ("常见求导错误", "诊断错误"),
            ("最优化建模", "建立现实模型"),
        ],
        [
            "math_intuition_representation",
            "math_worked_strategy",
            "math_proof_reasoning",
            "math_error_diagnosis",
            "math_modeling_inquiry",
        ],
    ),
    (
        "programming_engineering",
        "Python 软件工程",
        "构建可运行系统并完成测试",
        [
            ("第一个可运行程序", "运行基础代码"),
            ("实现接口功能", "构建模块"),
            ("定位异常", "调试故障"),
            ("测试与重构", "用测试保护重构"),
            ("系统架构项目", "交付综合系统"),
        ],
        [
            "engineering_runnable_intro",
            "engineering_guided_build",
            "engineering_debugging_lab",
            "engineering_test_refactor",
            "engineering_project_architecture",
        ],
    ),
    (
        "natural_science",
        "物理实验",
        "解释现象并设计实验",
        [
            ("观察摆动现象", "提出问题和假设"),
            ("建立摆模型", "用模型解释规律"),
            ("设计测量实验", "分析实验数据"),
            ("证据支持什么", "形成证据论证"),
            ("工程减震设计", "设计解决方案"),
        ],
        [
            "science_phenomenon_inquiry",
            "science_model_explanation",
            "science_investigation",
            "science_evidence_argument",
            "science_design_application",
        ],
    ),
    (
        "life_medical",
        "人体生理学",
        "解释生命机制并分析医学基础案例",
        [
            ("心脏结构与功能", "解释结构功能"),
            ("循环调节机制", "解释反馈机制"),
            ("实验数据与证据", "分析研究数据"),
            ("正常与异常比较", "比较状态差异"),
            ("综合病例机制", "基于证据解释案例"),
        ],
        [
            "life_structure_function",
            "life_mechanism_system",
            "life_evidence_quantitative",
            "life_comparative_variation",
            "life_case_reasoning",
        ],
    ),
    (
        "humanities_social",
        "中国近代史",
        "分析史料并形成论证",
        [
            ("为什么发生变化", "提出历史问题和背景"),
            ("原始史料辨析", "解释材料来源"),
            ("制度演变原因", "分析因果变化"),
            ("不同观点争议", "比较观点并论证"),
            ("综合史料写作", "形成综合回应"),
        ],
        [
            "humanities_inquiry_context",
            "humanities_source_interpretation",
            "humanities_causal_change",
            "humanities_argument_debate",
            "humanities_synthesis_response",
        ],
    ),
    (
        "language_learning",
        "商务英语",
        "完成真实沟通",
        [
            ("听懂客户对话", "理解输入和语块"),
            ("报价句型语法", "准确使用形式"),
            ("客户会话互动", "协商意义"),
            ("转述会议内容", "调解转述"),
            ("综合汇报与反馈", "修正后再次表达"),
        ],
        [
            "language_input_comprehension",
            "language_form_accuracy",
            "language_interaction_task",
            "language_mediation_task",
            "language_performance_feedback",
        ],
    ),
    (
        "business_career",
        "产品管理",
        "完成业务决策和交付",
        [
            ("用户问题诊断", "界定目标约束"),
            ("案例方案决策", "比较取舍"),
            ("分析工具工作坊", "用模板完成分析"),
            ("利益相关者沟通", "角色模拟谈判"),
            ("交付方案与复盘", "评审并修订成果"),
        ],
        [
            "business_scenario_diagnosis",
            "business_case_decision",
            "business_tool_workshop",
            "business_role_simulation",
            "business_deliverable_review",
        ],
    ),
]


def _plan(sections):
    return {
        "course_title": "课型测试",
        "chapters": [{
            "chapter_number": 1,
            "title": "主线",
            "sections": [
                {
                    "node_id": f"L2-1-{index}",
                    "section_number": f"1.{index}",
                    "title": title,
                    "learning_objective": objective,
                    "key_points": [title],
                    "assessment": ["完成可检查任务"],
                }
                for index, (title, objective) in enumerate(
                    sections,
                    start=1,
                )
            ],
        }],
    }


@pytest.mark.parametrize(
    (
        "mode",
        "subject",
        "requirements",
        "sections",
        "expected_archetypes",
    ),
    CASES,
)
def test_every_subject_mode_uses_distinct_goal_and_stage_aware_archetypes(
    mode,
    subject,
    requirements,
    sections,
    expected_archetypes,
):
    profile = resolve_pedagogy_profile(
        subject=subject,
        requirements=requirements,
        requested_mode=mode,
    )
    plan = _plan(sections)

    attach_module_plans_to_plan(plan, profile)

    actual_sections = plan["chapters"][0]["sections"]
    assert [
        item["lesson_archetype"]["archetype_id"]
        for item in actual_sections
    ] == expected_archetypes
    assert all(
        item["lesson_archetype"]["evidence_contract"]
        and item["lesson_archetype"]["guardrails"]
        for item in actual_sections
    )
    for item in actual_sections:
        module_ids = {
            module["module_id"]
            for module in item["module_plan"]
        }
        assert set(item["lesson_archetype"]["module_ids"]) <= module_ids
        assert {
            "lesson_goal",
            "core_explanation",
            "learner_action",
            "feedback_check",
        } <= module_ids


def test_broad_modes_resolve_useful_subject_variants_without_new_model_call():
    variants = {
        "软件架构与微服务": (
            PedagogyMode.PROGRAMMING_ENGINEERING,
            "engineering_software_systems",
        ),
        "机器学习模型训练工程": (
            PedagogyMode.PROGRAMMING_ENGINEERING,
            "engineering_data_ai",
        ),
        "中国古代史": (
            PedagogyMode.HUMANITIES_SOCIAL,
            "humanities_historical",
        ),
        "文学文本与文化": (
            PedagogyMode.HUMANITIES_SOCIAL,
            "humanities_textual_cultural",
        ),
        "医学免疫学": (
            PedagogyMode.LIFE_MEDICAL,
            "life_medical_foundations",
        ),
        "商业财务分析": (
            PedagogyMode.BUSINESS_CAREER,
            "business_analytics_finance",
        ),
    }

    for subject, (mode, expected_variant) in variants.items():
        profile = resolve_pedagogy_profile(
            subject=subject,
            requested_mode=mode.value,
        )
        assert profile.subject_variant_id == expected_variant
        assert profile.subject_variant_label
        assert profile.quality_guardrails
        assert profile.final_assessment


def test_archetype_contract_reaches_content_prompt_and_teacher_plan():
    profile = resolve_pedagogy_profile(
        subject="Python 软件工程",
        requirements="完成测试与重构",
        requested_mode="programming_engineering",
    )
    plan = _plan([
        ("测试与重构", "用测试保护重构"),
    ])
    attach_module_plans_to_plan(plan, profile)
    section = plan["chapters"][0]["sections"][0]
    node = {
        **section,
        "node_name": "1.1 测试与重构",
        "node_level": 2,
        "module_plan": section["module_plan"],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    course = {
        "course_name": "Python 软件工程",
        "subject_pedagogy_profile": profile.to_dict(),
        "course_plan": plan,
        "nodes": [node],
        "course_teaching_plan": {
            "revision_id": "plan-v2",
            "sections": [{
                "node_id": "L2-1-1",
                "knowledge_structure": [],
                "teaching_modules": [],
            }],
        },
    }

    _user, prompt = CoursePromptComposer().build_content_prompt(
        course_data=course,
        node=node,
        context="无额外资料",
    )

    assert "## 本节学科课型" in prompt
    assert "测试与重构" in prompt
    assert "在保持外部行为不变的前提下" in prompt
    assert "不能机械复用同一学科的固定段落套路" in prompt

    projection = project_course_teaching_plan(course)
    assert (
        projection["sections"][0]["lesson_archetype"]["archetype_id"]
        == "engineering_test_refactor"
    )
    assert projection["overall"]["pedagogy_quality_contract"][
        "final_assessment"
    ]


def test_v1_persisted_profile_remains_readable_without_course_migration():
    restored = coerce_persisted_profile({
        "course_name": "旧版数学课程",
        "subject_pedagogy_profile": {
            "primary_mode": "math_formal",
            "profile_version": "subject_pedagogy_v1",
            "enabled_module_ids": ["math_formalization"],
        },
    })

    assert restored.profile_version == "subject_pedagogy_v1"
    assert restored.primary_mode is PedagogyMode.MATH_FORMAL
    assert restored.subject_variant_id
    assert restored.quality_guardrails
    assert restored.final_assessment


def test_registry_covers_all_modes_and_all_archetypes_have_real_evidence():
    assert len(LESSON_ARCHETYPES) == 40
    assert len(SUBJECT_VARIANTS) == 21
    assert {
        item.mode
        for item in LESSON_ARCHETYPES.values()
    } == {
        mode.value
        for mode in PedagogyMode
    }
    assert {
        item.mode
        for item in SUBJECT_VARIANTS.values()
    } == {
        mode.value
        for mode in PedagogyMode
    }
    assert all(
        item.module_ids
        and item.evidence_contract
        and item.guardrails
        for item in LESSON_ARCHETYPES.values()
    )
