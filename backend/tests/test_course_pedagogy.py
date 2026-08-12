from course_difficulty import (
    assess_readiness,
    attach_difficulty_contracts_to_plan,
    compile_difficulty_profile,
    decide_adaptation,
)
from course_pedagogy import (
    PedagogyMode,
    SecondaryIntensity,
    attach_module_plans_to_plan,
    coerce_persisted_profile,
    compile_subject_generation_template,
    resolve_pedagogy_profile,
    validate_module_registry,
)
from course_quality import evaluate_node_content, validate_blueprint


def test_module_registry_is_complete():
    assert validate_module_registry() == []


def test_same_subject_uses_learning_outcome_to_choose_primary_mode():
    project = resolve_pedagogy_profile(
        subject="机器学习",
        requirements="使用 Python 完成可运行项目，训练、调试并部署模型。",
    )
    theory = resolve_pedagogy_profile(
        subject="机器学习",
        requirements="重点推导公式、证明算法性质并分析收敛条件。",
    )

    assert project.primary_mode == PedagogyMode.PROGRAMMING_ENGINEERING
    assert theory.primary_mode == PedagogyMode.MATH_FORMAL


def test_explicit_mode_is_locked_and_not_overridden():
    profile = resolve_pedagogy_profile(
        subject="机器学习",
        requirements="完成 Python 项目",
        requested_mode="humanities_social",
    )

    assert profile.primary_mode == PedagogyMode.HUMANITIES_SOCIAL
    assert profile.user_locked is True
    assert profile.confidence == "high"


def test_hybrid_course_has_one_secondary_mode_and_intensity():
    profile = resolve_pedagogy_profile(
        subject="商务英语谈判",
        requirements="使用英语完成客户谈判、报价分析和沟通表达。",
    )

    assert profile.primary_mode == PedagogyMode.LANGUAGE_LEARNING
    assert profile.secondary_mode == PedagogyMode.BUSINESS_CAREER
    assert profile.secondary_intensity in {
        SecondaryIntensity.COLLABORATIVE,
        SecondaryIntensity.DUAL_CORE,
    }


def test_unknown_subject_falls_back_to_general_not_natural_science():
    profile = resolve_pedagogy_profile(subject="一个全新的主题代号")
    assert profile.primary_mode == PedagogyMode.GENERAL
    assert profile.confidence == "low"


def test_subject_template_freezes_one_contract_for_all_downstream_stages():
    profile = resolve_pedagogy_profile(
        subject="微积分",
        requirements="完整推导、变式练习和错因分析",
    )

    template = compile_subject_generation_template(profile)

    assert template["schema_version"] == "subject_generation_template_v3"
    assert template["template_id"].startswith("subject/math_formal/")
    assert template["subject_variant"]["id"]
    assert "derives" in template["knowledge_contract"]["relation_priorities"]
    assert "math_formalization" in template["lesson_plan_contract"][
        "available_subject_module_ids"
    ]
    assert template["lesson_plan_contract"]["preferred_archetype_ids"]
    assert template["assessment_contract"]["final_performance"]
    assert template["downstream_order"] == [
        "course_outline",
        "course_knowledge_identity",
        "course_knowledge_enrichment",
        "course_knowledge_freeze",
        "course_teaching_plan",
        "course_content",
        "course_assessment",
    ]


def test_static_routing_distinguishes_computing_physical_engineering_and_history():
    data_structures = resolve_pedagogy_profile(subject="数据结构")
    mechanical_design = resolve_pedagogy_profile(subject="机械设计")
    modern_history = resolve_pedagogy_profile(subject="中国近现代史")

    assert data_structures.primary_mode is PedagogyMode.PROGRAMMING_ENGINEERING
    assert data_structures.subject_variant_id == "engineering_computing_foundations"
    assert "复杂度分析" in data_structures.final_assessment
    assert mechanical_design.primary_mode is PedagogyMode.NATURAL_SCIENCE
    assert mechanical_design.subject_variant_id == "science_physical_engineering_design"
    assert "工程设计" in mechanical_design.final_assessment
    assert modern_history.primary_mode is PedagogyMode.HUMANITIES_SOCIAL
    assert modern_history.subject_variant_id == "humanities_historical"


def test_specific_subject_variant_outweighs_generic_requirement_activities():
    mechanical_design = resolve_pedagogy_profile(
        subject="机械设计：轴系结构的需求、载荷、失效与验证",
        requirements=(
            "建立物理模型，完成力学分析、测量、实验、计算与仿真，"
            "并比较方案和设计验证。"
        ),
    )

    assert mechanical_design.primary_mode is PedagogyMode.NATURAL_SCIENCE
    assert (
        mechanical_design.subject_variant_id
        == "science_physical_engineering_design"
    )


def test_subject_title_outweighs_generic_application_wording():
    profile = resolve_pedagogy_profile(subject="线性代数：理论与应用")

    assert profile.primary_mode == PedagogyMode.MATH_FORMAL


def test_legacy_natural_science_math_course_is_read_as_math():
    profile = coerce_persisted_profile({
        "course_name": "线性代数入门",
        "discipline": "natural_science",
    })
    assert profile.primary_mode == PedagogyMode.MATH_FORMAL


def test_persisted_profile_keeps_evidence_and_rationale():
    profile = resolve_pedagogy_profile(
        subject="Python 工程",
        requirements="完成可运行项目",
        requested_mode="programming_engineering",
    )
    raw = profile.to_dict()
    raw["evidence"] = ["用户要求可运行产物"]
    raw["rationale"] = "课程以工程交付为主线"

    restored = coerce_persisted_profile({
        "course_name": "Python 工程",
        "subject_pedagogy_profile": raw,
    })

    assert restored.evidence == ("用户要求可运行产物",)
    assert restored.rationale == "课程以工程交付为主线"


def test_module_plan_deduplicates_and_injects_secondary_modules():
    profile = resolve_pedagogy_profile(
        subject="商务英语谈判",
        requirements="用英语完成谈判并形成报价方案",
    )
    plan = {
        "chapters": [{
            "chapter_number": 1,
            "title": "客户沟通",
            "sections": [
                {
                    "section_number": "1.1",
                    "title": "建立谈判场景",
                    "key_points": ["客户目标", "英文表达"],
                    "learning_objective": "能用英语完成开场",
                    "assessment": ["完成角色对话"],
                },
                {
                    "section_number": "1.2",
                    "title": "报价与异议处理",
                    "key_points": ["报价", "异议"],
                    "learning_objective": "能回应价格异议",
                    "assessment": ["提交谈判脚本"],
                },
            ],
        }],
    }

    attach_module_plans_to_plan(plan, profile)
    module_ids = [
        item["module_id"]
        for section in plan["chapters"][0]["sections"]
        for item in section["module_plan"]
    ]
    assert len(module_ids) >= len(set(module_ids))
    assert any(module_id.startswith("business_") for module_id in module_ids)


def test_blueprint_and_node_quality_use_module_contracts():
    profile = resolve_pedagogy_profile(
        subject="Python 编程",
        requested_mode="programming_engineering",
    )
    plan = {
        "chapters": [{
            "chapter_number": 1,
            "title": "运行程序",
            "sections": [{
                "section_number": "1.1",
                "title": "第一个程序",
                "key_points": ["print"],
                "learning_objective": "能运行 print 程序",
                "assessment": ["输出 Hello"],
                "prerequisite_node_ids": [],
            }],
        }],
    }
    attach_module_plans_to_plan(plan, profile)
    difficulty_profile = compile_difficulty_profile(
        "intermediate",
        primary_mode=profile.primary_mode,
    )
    attach_difficulty_contracts_to_plan(
        plan,
        profile=difficulty_profile,
        adaptation=decide_adaptation(assess_readiness(difficulty_profile)),
    )
    section = plan["chapters"][0]["sections"][0]
    node = {
        "node_id": "L2-1-1",
        "node_name": "1.1 第一个程序",
        **section,
    }
    blueprint = {
        "subject_pedagogy_profile": profile.to_dict(),
        "difficulty_profile": plan["difficulty_profile"],
        "course_difficulty_curve": plan["course_difficulty_curve"],
        "nodes": [node],
    }

    assert validate_blueprint(blueprint)["passed"] is True
    weak = evaluate_node_content("## 第一个程序\n\n这里只讲概念。", node)
    assert weak["passed"] is False
    assert any(item["code"] == "module:engineering_minimal_run" for item in weak["issues"])
