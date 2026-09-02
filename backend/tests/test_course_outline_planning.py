from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy

import pytest

from ai_base import AIBase
from course_generation.workflow import (
    _extract_course_shape_constraints,
    build_course_generation_artifacts,
    _resolve_course_shape_constraints,
    build_course_knowledge_scope_contract,
    build_section_knowledge_scope_slice,
)
from course_generation.outline import (
    CourseOutlinePlanningBudget,
    assemble_course_outline,
    course_coverage_verdict,
    build_outline_batch_specs,
    compile_fallback_outline_batch,
    compile_teacher_lecture_outline_batch,
    normalize_outline_skeleton,
    outline_request_fingerprint,
    review_course_outline_document,
    validate_outline_batch,
    validate_outline_skeleton,
)
from course_generation.prompts import CoursePromptComposer
from course_generation.service import CourseService
from course_pedagogy import resolve_pedagogy_profile


def _outline_skeleton_payload(
    *,
    chapter_count: int,
    sections_per_chapter: int,
) -> str:
    return json.dumps({
        "course_title": "大规模并行课程",
        "positioning": "验证结构化分片、恢复与并行生成",
        "learning_objectives": ["完成一门可检查的大规模课程"],
        "prerequisites": [],
        "chapters": [
            {
                "chapter_number": index,
                "title": f"第 {index} 章",
                "learning_focus": f"完成阶段 {index}",
                "section_count": sections_per_chapter,
            }
            for index in range(1, chapter_count + 1)
        ],
    }, ensure_ascii=False)


def _outline_batch_payload(system_prompt: str) -> str:
    match = re.search(
        r"## 当前批次\n(\{.*?\})\n\n## 当前章已完成",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    spec = json.loads(match.group(1))
    return json.dumps({
        "sections": [
            {
                "node_id": node_id,
                "title": f"任务 {node_id}",
                "learning_objective": f"独立完成 {node_id}",
                "prerequisite_node_ids": [],
                "assessment": [f"提交 {node_id} 结果"],
                "scope_boundary": f"只负责 {node_id}",
            }
            for node_id in spec["expected_node_ids"]
        ],
    }, ensure_ascii=False)


def test_plan_conversion_keeps_existing_outline_numbering_idempotent():
    nodes = CourseService._convert_plan_to_nodes(
        None,
        {
            "chapters": [{
                "chapter_number": 1,
                "title": "第1章 开发环境与核心机制",
                "sections": [{
                    "section_number": "1.1",
                    "title": "1.1 初始化项目",
                }],
            }],
        },
        "course-numbering",
    )

    assert [node["node_name"] for node in nodes] == [
        "第1章 开发环境与核心机制",
        "1.1 初始化项目",
    ]


def test_teacher_course_is_generated_as_one_level_lectures_from_the_first_model_call():
    brief = {
        "course_shape_constraints": {
            "teacher_lecture_mode": True,
            "chapter_count": 2,
            "section_count": 2,
        },
        "formal_course_profile": {
            "planned_lecture_count": 2,
            "course_intro": "建立电动力学的经典理论框架。",
        },
        "teacher_course_brief": {"lecture_count": 2},
    }
    prompt = CoursePromptComposer().build_outline_skeleton_v2_prompt(
        subject="电动力学",
        audience="物理学本科生",
        brief=brief,
        profile=resolve_pedagogy_profile(subject="电动力学"),
        difficulty_profile={},
        gap_assessment={},
        adaptation_decision={},
        material_context="教材目录已上传。",
        detail_level="full",
        coverage_verdict={},
    )

    assert '"lectures"' in prompt
    assert '"chapters"' not in prompt
    assert "严格返回 2 讲" in prompt
    assert "第N讲" in prompt
    assert '"assessment"' in prompt
    assert '"scope_boundary"' in prompt
    assert '"outcome_alignment"' in prompt
    assert "学生要提交、解释、判断、设计、实作或迁移出什么具体成果" in prompt
    assert "不得要求学生使用后续讲次才会完成的内容" in prompt

    skeleton = normalize_outline_skeleton(
        {
            "course_title": "电动力学",
            "course_intro_zh": "从经典场论建立统一分析框架。",
            "learning_objectives": ["能解释麦克斯韦方程组的物理意义"],
            "measurable_outcomes": ["能建立并求解典型电磁场问题"],
            "outcome_alignment": [{
                "outcome_number": 1,
                "objective_refs": ["学习目标1"],
                "lecture_numbers": [1, 2, 99],
                "assessment_evidence": ["边值问题求解与磁场计算"],
                "coverage_scope": "静电场与稳恒磁场",
            }, {
                "outcome_number": 1,
                "objective_refs": ["育人目标1"],
                "lecture_numbers": [2],
                "assessment_evidence": ["口头答辩"],
                "coverage_scope": "",
            }],
            "lectures": [
                {
                    "title": "静电场与边值问题",
                    "content_summary": "介绍静电场基本方程、边界条件与典型求解方法。",
                    "learning_objective": "能建立并求解典型静电边值问题",
                    "assessment": ["提交一份边值问题求解，边界条件、推导和物理检验完整"],
                    "scope_boundary": "只处理静电场边值问题，不展开时变场",
                },
                {
                    "title": "稳恒磁场",
                    "content_summary": "讨论稳恒电流产生的磁场及其基本性质。",
                    "learning_objective": "能运用安培定律分析磁场",
                    "assessment": ["绘制对称电流的磁场并完成计算，对称性与环路选择正确"],
                    "scope_boundary": "只分析稳恒电流磁场，不引入电磁感应",
                },
            ],
        },
        topic="电动力学",
        request_fingerprint="outline-request",
    )
    specs = build_outline_batch_specs(skeleton, CourseOutlinePlanningBudget())
    batches = {
        str(spec["batch_id"]): compile_teacher_lecture_outline_batch(
            spec=spec,
            lecture=skeleton["chapters"][index],
            skeleton_revision_id=skeleton["revision_id"],
        )
        for index, spec in enumerate(specs)
    }
    plan = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=specs,
        batches=batches,
    )
    nodes = CourseService._convert_plan_to_nodes(None, plan, "course-electrodynamics")

    assert plan["authoring_structure_version"] == "lecture_v1"
    assert [node["node_name"] for node in nodes if node["node_level"] == 1] == [
        "第1讲 静电场与边值问题",
        "第2讲 稳恒磁场",
    ]
    assert all(
        not re.match(r"^\d+\.\d+", node["node_name"])
        for node in nodes
    )
    assert plan["chapters"][0]["sections"][0]["assessment"] == [
        "提交一份边值问题求解，边界条件、推导和物理检验完整"
    ]
    assert plan["chapters"][1]["sections"][0]["scope_boundary"] == (
        "只分析稳恒电流磁场，不引入电磁感应"
    )
    assert plan["outcome_alignment"] == [{
        "outcome_number": 1,
        "objective_refs": ["学习目标1", "育人目标1"],
        "lecture_numbers": [1, 2],
        "assessment_evidence": ["边值问题求解与磁场计算", "口头答辩"],
        "coverage_scope": "静电场与稳恒磁场",
    }]


def test_teacher_lecture_missing_evidence_is_reported_instead_of_fabricated():
    skeleton = normalize_outline_skeleton(
        {
            "authoring_structure_version": "lecture_v1",
            "course_title": "UI设计",
            "positioning": "面向初学者建立界面设计能力",
            "learning_objectives": ["能完成可评审的界面原型"],
            "lectures": [{
                "title": "信息层级",
                "learning_objective": "能根据用户任务排列页面信息",
            }],
        },
        topic="UI设计",
        request_fingerprint="ui-outline-request",
    )
    spec = build_outline_batch_specs(
        skeleton,
        CourseOutlinePlanningBudget(),
    )[0]
    batch = compile_teacher_lecture_outline_batch(
        spec=spec,
        lecture=skeleton["chapters"][0],
        skeleton_revision_id=skeleton["revision_id"],
    )
    plan = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=[spec],
        batches={str(spec["batch_id"]): batch},
    )

    section = plan["chapters"][0]["sections"][0]
    assert section["assessment"] == []
    assert section["scope_boundary"] == ""
    report = review_course_outline_document(plan)
    codes = {issue["code"] for issue in report["issues"]}
    assert "outline_editorial:missing_assessments" in codes
    assert "outline_editorial:missing_scope_boundaries" in codes
    assert "outline_editorial:repeated_assessment_template" not in codes
    assert report["passed"] is False
    assert report["non_blocking"] is False
    assert "outline_editorial:missing_application_anchors" in codes
    assert "outline_editorial:missing_extension_resources" in codes
    assert "outline_editorial:missing_learning_tasks" in codes
    assert report["summary"].startswith("大纲草稿已生成")


def test_extension_resource_cannot_be_verified_without_an_exact_confirmed_source():
    skeleton = normalize_outline_skeleton(
        {
            "authoring_structure_version": "lecture_v1",
            "course_title": "UI设计",
            "course_intro_zh": "从用户任务出发建立可验证的界面设计方法。",
            "course_intro_en": "Build verifiable interface-design methods from user tasks.",
            "positioning": "面向初学者建立可验证的界面设计方法",
            "learning_objectives": ["掌握信息层级设计方法"],
            "education_objectives": ["具备根据用户证据承担设计责任的意识"],
            "measurable_outcomes": ["能完成可评审的页面信息层级图"],
            "outcome_alignment": [{
                "outcome_number": 1,
                "objective_refs": ["学习目标1", "育人目标1"],
                "lecture_numbers": [1],
                "assessment_evidence": ["信息层级图"],
                "coverage_scope": "页面信息层级",
            }],
            "assessment_plan": [
                {"item": "过程草图", "category": "formative", "weight_percent": 40, "criteria": "层级与用户任务一致", "outcome_numbers": [1]},
                {"item": "完整方案", "category": "summative", "weight_percent": 60, "criteria": "关键信息可定位", "outcome_numbers": [1]},
            ],
            "course_modules": [{"module_id": "M1", "title": "信息组织", "lecture_numbers": [1]}],
            "reference_books": ["《界面设计方法》第2版"],
            "lectures": [{
                "title": "信息层级",
                "content_summary": "根据用户任务组织页面信息。",
                "learning_objective": "能排列页面信息的主次关系",
                "assessment": ["提交信息层级图，关键任务可定位"],
                "scope_boundary": "只负责信息主次，不展开视觉风格",
                "application_anchors": ["课程首页信息层级图"],
                "extension_resources": [{
                    "resource_type": "book",
                    "title": "界面设计方法",
                    "edition": "第2版",
                    "locator": "第3章，45–60页",
                    "source_ref": "《界面设计方法》第1版",
                    "verification_status": "verified",
                }],
                "learning_tasks": [{
                    "mode": "offline",
                    "stage": "after_class",
                    "task": "修订信息层级图",
                    "evidence": "修订前后对比",
                    "estimated_hours": 1,
                }],
                "hour_breakdown": {"classroom_lecture": 1, "classroom_practice": 0, "online_instruction": 0},
            }],
        },
        topic="UI设计",
        request_fingerprint="ui-resource-check",
    )
    spec = build_outline_batch_specs(skeleton, CourseOutlinePlanningBudget())[0]
    batch = compile_teacher_lecture_outline_batch(
        spec=spec,
        lecture=skeleton["chapters"][0],
        skeleton_revision_id=skeleton["revision_id"],
    )
    plan = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=[spec],
        batches={str(spec["batch_id"]): batch},
    )

    resource = plan["chapters"][0]["sections"][0]["extension_resources"][0]
    assert resource["verification_status"] == "pending"
    codes = {item["code"] for item in review_course_outline_document(plan)["blocking_issues"]}
    assert "outline_editorial:unverified_extension_resources" in codes


def test_measurable_outcomes_without_alignment_are_reported_for_review():
    report = review_course_outline_document({
        "authoring_structure_version": "lecture_v1",
        "positioning": "从真实设计任务建立可验证的方法。",
        "learning_objectives": ["能完成可评审的设计方案"],
        "measurable_outcomes": ["能提交原型与测试记录"],
        "chapters": [],
    })

    issue = next(
        item for item in report["issues"]
        if item["code"] == "outline_editorial:missing_outcome_alignment"
    )
    assert issue["rule_version"] == "course_outline_editorial_v6"
    assert issue["evidence"]["outcome_numbers"] == [1]


def test_sixteen_lecture_ui_design_outline_keeps_distinct_evidence_and_is_ready():
    lecture_contracts = [
        ("用户任务", "从访谈记录提取主要任务", "用户任务清单", "任务包含对象、目标和场景"),
        ("信息架构", "组织内容并建立导航层级", "信息架构图", "分类无重复且关键内容可定位"),
        ("页面流程", "绘制覆盖核心任务的页面流程", "页面流程图", "入口、决策点和结果完整"),
        ("线框图", "把内容层级转化为页面布局", "首页线框图", "主任务突出且信息层级清楚"),
        ("布局与网格", "使用网格建立稳定的布局秩序", "响应式布局稿", "对齐、间距和缩放规则一致"),
        ("字体层级", "根据阅读任务建立字体层级", "字体样式表", "标题、正文和辅助信息可辨"),
        ("色彩系统", "在品牌与可读性约束下配置色彩", "色彩规范", "功能色语义稳定且对比度达标"),
        ("图标与图形", "选择并绘制语义一致的图标", "图标集与使用说明", "图标含义可识别且线性风格一致"),
        ("组件状态", "设计组件的完整交互状态", "按钮与输入框状态表", "默认、悬停、焦点、禁用和失败齐全"),
        ("表单设计", "组织输入、校验与错误恢复", "注册表单原型", "标签清楚、错误可定位且不丢失输入"),
        ("导航设计", "为多层内容选择合适的导航方式", "可点击导航原型", "用户始终知道位置与可去方向"),
        ("空与错误状态", "为无数据和操作失败设计恢复方式", "空状态与错误页", "原因、下一步和恢复操作均可见"),
        ("响应式适配", "根据内容与任务调整不同视口的布局", "三种视口的界面稿", "内容优先级不变且操作可完成"),
        ("可访问性", "识别并修复关键界面的使用障碍", "可访问性检查清单", "键盘路径、焦点与语义均通过检查"),
        ("可用性测试", "观察用户执行指定任务并定位问题", "可用性测试报告", "记录包含任务、行为证据、问题与严重度"),
        ("综合迭代", "依据评审与测试证据修订界面", "高保真原型与变更说明", "关键问题已修复且每项修改有依据"),
    ]
    skeleton = normalize_outline_skeleton(
        {
            "authoring_structure_version": "lecture_v1",
            "course_title": "UI设计",
            "course_intro_zh": "本课程面向初学者，从用户任务出发，完成可测试的界面原型。",
            "course_intro_en": "This course guides beginners from user tasks to a testable interface prototype.",
            "positioning": "面向初学者从用户任务推进到可测试的界面原型",
            "learning_objectives": ["能设计、评审并迭代一套完整界面方案"],
            "education_objectives": ["具备尊重用户、依据证据承担设计责任的意识"],
            "measurable_outcomes": ["能提交界面原型、测试记录与修改说明"],
            "outcome_alignment": [{
                "outcome_number": 1,
                "objective_refs": ["学习目标1", "育人目标1"],
                "lecture_numbers": list(range(1, 17)),
                "assessment_evidence": ["原型、测试记录和修改说明"],
                "coverage_scope": "从用户任务到综合迭代的完整设计过程",
            }],
            "teaching_methods": ["线下讲授与设计实践"],
            "assessment_plan": [
                {"item": "讲次作品", "category": "formative", "weight_percent": 60, "criteria": "按每讲产出和评审标准评分", "outcome_numbers": [1]},
                {"item": "综合原型", "category": "summative", "weight_percent": 40, "criteria": "按可用性证据、问题修复和说明完整度评分", "outcome_numbers": [1]},
            ],
            "course_modules": [{"module_id": "M1", "title": "界面设计全流程", "lecture_numbers": list(range(1, 17))}],
            "reference_books": ["已确认教材：界面设计方法"],
            "lectures": [
                {
                    "title": title,
                    "learning_objective": f"能{action}",
                    "assessment": [f"提交{artifact}；教师检查{criterion}"],
                    "scope_boundary": f"本讲只负责{title}的核心方法，不提前替代后续综合迭代",
                    "application_anchors": [artifact],
                    "extension_resources": [{
                        "resource_type": "book",
                        "title": "已确认教材：界面设计方法",
                        "edition": "第1版",
                        "locator": f"第{index}章",
                        "source_ref": "已确认教材：界面设计方法",
                        "verification_status": "verified",
                    }],
                    "learning_tasks": [{
                        "mode": "offline",
                        "stage": "after_class",
                        "task": f"完成{artifact}",
                        "evidence": artifact,
                        "estimated_hours": 1,
                    }],
                    "hour_breakdown": {"classroom_lecture": 1, "classroom_practice": 0, "online_instruction": 0},
                }
                for index, (title, action, artifact, criterion) in enumerate(lecture_contracts, start=1)
            ],
        },
        topic="UI设计",
        request_fingerprint="ui-16-outline-request",
    )
    specs = build_outline_batch_specs(skeleton, CourseOutlinePlanningBudget())
    batches = {
        str(spec["batch_id"]): compile_teacher_lecture_outline_batch(
            spec=spec,
            lecture=skeleton["chapters"][index],
            skeleton_revision_id=skeleton["revision_id"],
        )
        for index, spec in enumerate(specs)
    }
    plan = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=specs,
        batches=batches,
    )

    report = review_course_outline_document(plan)
    sections = [chapter["sections"][0] for chapter in plan["chapters"]]
    assert len(sections) == 16
    assert len({section["assessment"][0] for section in sections}) == 16
    assert report["status"] == "ready", report
    assert report["issues"] == [], report


def test_confirmed_outline_snapshot_is_not_replaced_by_downstream_normalization():
    confirmed = {
        "course_title": "Unity 实战",
        "chapters": [{
            "chapter_number": 1,
            "title": "第1章 开发环境",
            "learning_focus": "",
            "sections": [{
                "section_number": "1.1",
                "title": "1.1 初始化项目",
            }],
        }],
    }
    normalized = deepcopy(confirmed)
    normalized["chapters"][0]["learning_focus"] = "第1章 开发环境"
    normalized["chapters"][0]["sections"][0]["title"] = "初始化项目"

    selected = CourseService._select_output_course_outline(
        {
            "course_outline_revision_id": "bp-confirmed",
            "course_outline": confirmed,
        },
        normalized,
    )

    assert selected == confirmed


def test_total_course_size_is_not_an_outline_budget_dimension():
    budget = CourseOutlinePlanningBudget()

    assert not hasattr(budget, "choose_mode")
    assert not hasattr(budget, "compact_max_sections")
    assert not hasattr(budget, "max_sections")
    assert _extract_course_shape_constraints(
        "生成 20 章，共 120 个小节",
    ) == {
        "chapter_count": 20,
        "section_count": 120,
    }
    assert _resolve_course_shape_constraints("") == {
        "minimum_chapter_count": 6,
        "minimum_section_count": 18,
    }


def test_whole_outline_review_locates_repeated_assessment_templates_without_blocking():
    sections = []
    for index, title in enumerate(("极限", "导数", "积分", "级数"), start=1):
        sections.append({
            "node_id": f"L2-1-{index}",
            "title": title,
            "learning_objective": f"能应用{title}解决典型问题",
            "assessment": f"能独立完成“{title}”的标准计算、条件判定与结果核验",
            "scope_boundary": f"只处理{title}的基本问题",
        })
    report = review_course_outline_document({
        "positioning": "面向本科生建立微积分分析与应用能力",
        "learning_objectives": ["能选择并应用微积分方法解决问题"],
        "chapters": [{"chapter_number": 1, "title": "核心方法", "sections": sections}],
    })

    assert report["passed"] is True
    assert report["non_blocking"] is True
    repeated = next(
        issue for issue in report["issues"]
        if issue["code"] == "outline_editorial:repeated_assessment_template"
    )
    assert repeated["node_ids"] == ["L2-1-1", "L2-1-2", "L2-1-3", "L2-1-4"]
    assert repeated["rule_version"] == "course_outline_editorial_v6"
    assert "范围说明" in repeated["repair_instruction"]
    assert report["metrics"]["located_section_count"] == 4


def test_whole_outline_review_reports_ready_for_distinct_professional_evidence():
    report = review_course_outline_document({
        "positioning": "面向工程学习者完成数据分析方案设计",
        "learning_objectives": ["能解释、比较并设计完整的数据分析方案"],
        "chapters": [{
            "chapter_number": 1,
            "title": "分析方法",
            "sections": [
                {
                    "node_id": "L2-1-1",
                    "title": "变量关系解释",
                    "learning_objective": "能用图表与统计量解释两个变量的关系",
                    "assessment": ["提交一页解释报告，结论须同时引用图表形态与统计量"],
                    "scope_boundary": "只处理两个变量的探索性关系，不推断因果",
                },
                {
                    "node_id": "L2-1-2",
                    "title": "模型方案比较",
                    "learning_objective": "能依据误差与可解释性比较两种模型",
                    "assessment": ["完成模型对照表，并为目标场景给出有依据的选择"],
                    "scope_boundary": "只比较已给模型，不展开新模型训练",
                },
            ],
        }],
    })

    assert report["status"] == "ready"
    assert report["issues"] == []


def test_whole_outline_review_allows_single_section_chapters_but_flags_system_register():
    chapters = []
    for index in range(1, 7):
        chapters.append({
            "node_id": f"L1-{index}",
            "chapter_number": index,
            "title": f"第{index}章",
            "learning_focus": (
                "通过前置检查建立全课知识地图并完成先修链定位"
                if index == 1 else f"理解第{index}章核心内容"
            ),
            "sections": [{
                "node_id": f"L2-{index}-1",
                "title": f"第{index}章基础",
                "learning_objective": "能解释本章概念并完成基础计算",
                "assessment": ["完成两道基础题并说明步骤"],
            }],
        })

    report = review_course_outline_document({
        "positioning": "面向本科生学习微积分基础",
        "learning_objectives": ["能计算并解释基础微积分问题"],
        "chapters": chapters,
    })

    codes = {issue["code"] for issue in report["issues"]}
    assert "outline_editorial:flat_chapter_structure" not in codes
    assert "outline_editorial:system_register" in codes
    assert report["schema_version"] == "course_outline_editorial_review_v5"
    assert report["status"] == "review_suggested"


def test_whole_outline_review_flags_overlong_public_objective():
    report = review_course_outline_document({
        "positioning": "面向本科生学习微积分基础",
        "learning_objectives": ["能计算并解释基础微积分问题"],
        "chapters": [{
            "chapter_number": 1,
            "title": "极限",
            "learning_focus": "理解极限的含义与基本计算方法",
            "sections": [{
                "node_id": "L2-1-1",
                "title": "极限的概念",
                "learning_objective": (
                    "能解释极限的直观含义；能比较图像与数值表；能判断左右极限；"
                    "能检查定义域；能说明计算依据；能核验结果是否合理"
                ),
                "assessment": ["根据图像判断两个极限并说明理由"],
            }],
        }],
    })

    issue = next(
        item for item in report["issues"]
        if item["code"] == "outline_editorial:overlong_objectives"
    )
    assert issue["node_ids"] == ["L2-1-1"]


def test_outline_prompts_keep_internal_planning_terms_out_of_public_copy():
    composer = CoursePromptComposer()
    prompt = composer.build_outline_batch_v2_prompt(
        course_title="微积分",
        positioning="面向本科生学习微积分基础",
        learning_objectives=["能计算并解释基础微积分问题"],
        chapter={"chapter_number": 1, "title": "极限", "section_count": 3},
        neighbor_chapters=[],
        batch_spec={
            "start_section_index": 1,
            "end_section_index": 1,
            "expected_node_ids": ["L2-1-1"],
        },
        previous_sections=[],
        evidence_hints=[],
        skeleton_revision_id="outline-skeleton-1",
    )

    assert "教师和学生直接阅读" in prompt
    assert "全课知识地图、先修链定位" in prompt
    assert "目标控制在一至两句" in prompt


def test_single_section_outline_prompt_preserves_teacher_shape_without_duplicate_title():
    composer = CoursePromptComposer()
    prompt = composer.build_outline_batch_v2_prompt(
        course_title="微积分",
        positioning="面向本科生学习微积分基础",
        learning_objectives=["能计算并解释基础微积分问题"],
        chapter={"chapter_number": 1, "title": "极限", "section_count": 1},
        neighbor_chapters=[],
        batch_spec={
            "start_section_index": 1,
            "end_section_index": 1,
            "expected_node_ids": ["L2-1-1"],
        },
        previous_sections=[],
        evidence_hints=[],
        skeleton_revision_id="outline-skeleton-1",
    )

    assert "当前章只有一个小节" in prompt
    assert "不得机械复述章标题" in prompt


def test_unspecified_course_rejects_six_section_skeleton():
    shape = _resolve_course_shape_constraints("")
    fingerprint = outline_request_fingerprint(
        topic="深度神经网络",
        audience="undergraduate",
        brief={"course_shape_constraints": shape},
        difficulty_profile={"level": "intermediate"},
    )
    skeleton = normalize_outline_skeleton(
        json.loads(_outline_skeleton_payload(
            chapter_count=3,
            sections_per_chapter=2,
        )),
        topic="深度神经网络",
        request_fingerprint=fingerprint,
    )
    report = validate_outline_skeleton(
        skeleton,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
    )

    assert report["passed"] is False
    assert {
        issue["code"] for issue in report["issues"]
    } >= {
        "outline_skeleton:below_complete_chapter_minimum",
        "outline_skeleton:below_complete_section_minimum",
    }


def test_dedicated_course_planner_requires_complete_ordered_stages():
    shape = {"chapter_count": 5, "section_count": 15}
    contract = {
        "required_planning_stages": [
            {"id": "define_question"},
            {"id": "decompose_questions"},
            {"id": "gather_evidence"},
            {"id": "test_explanations"},
            {"id": "form_conclusion"},
        ],
    }
    fingerprint = outline_request_fingerprint(
        topic="生成式 AI 会如何改变大学评价",
        audience="undergraduate",
        brief={"course_shape_constraints": shape, "course_type_contract": contract},
        difficulty_profile={"level": "intermediate"},
    )
    skeleton = normalize_outline_skeleton(
        {
            "course_title": "生成式 AI 与大学评价",
            "chapters": [
                {
                    "title": f"探究阶段 {index}",
                    "planning_stages": [stage["id"]],
                    "section_count": 3,
                }
                for index, stage in enumerate(
                    contract["required_planning_stages"],
                    start=1,
                )
            ],
        },
        topic="生成式 AI 会如何改变大学评价",
        request_fingerprint=fingerprint,
    )

    passed = validate_outline_skeleton(
        skeleton,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
        course_type_contract=contract,
    )
    assert passed["passed"] is True

    skeleton["chapters"][2]["planning_stages"] = ["form_conclusion"]
    failed = validate_outline_skeleton(
        skeleton,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
        course_type_contract=contract,
    )
    assert failed["passed"] is False
    assert {
        issue["code"] for issue in failed["issues"]
    } >= {
        "outline_skeleton:incomplete_planning_stages",
        "outline_skeleton:planning_stage_order_mismatch",
    }

    compact = normalize_outline_skeleton(
        {
            "course_title": "一章完成探究闭环",
            "chapters": [{
                "title": "完整探究",
                "planning_stages": [
                    item["id"] for item in contract["required_planning_stages"]
                ],
                "section_count": 1,
            }],
        },
        topic="生成式 AI 会如何改变大学评价",
        request_fingerprint=fingerprint,
    )
    compact_report = validate_outline_skeleton(
        compact,
        shape_constraints={"chapter_count": 1, "section_count": 1},
        request_fingerprint=fingerprint,
        course_type_contract=contract,
    )
    assert compact_report["passed"] is True


@pytest.mark.asyncio
async def test_teacher_outline_can_stop_after_named_chapter_skeleton(monkeypatch):
    service = CourseService()
    calls: list[str] = []

    async def fake_call(prompt, system_prompt="", **_kwargs):
        calls.append(system_prompt)
        assert "全课章节骨架 V2" in system_prompt
        return _outline_skeleton_payload(
            chapter_count=6,
            sections_per_chapter=3,
        )

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-shape-review",
        topic="并行系统",
        requirements="形成完整课程",
        stop_after_skeleton=True,
        stop_after_outline=True,
    )

    assert len(calls) == 1
    assert result["generation_status"] == "outline_shape_ready"
    assert "course_outline" not in result
    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["status"] == "waiting_for_shape_review"
    assert [
        chapter["title"] for chapter in stage["skeleton"]["chapters"]
    ] == [f"第 {index} 章" for index in range(1, 7)]
    assert stage["section_count"] == 18


def test_large_outline_is_split_per_chapter_and_locally_assembled():
    shape = {"chapter_count": 8, "section_count": 48}
    fingerprint = outline_request_fingerprint(
        topic="并行系统",
        audience="undergraduate",
        brief={"course_shape_constraints": shape},
        difficulty_profile={"level": "intermediate"},
    )
    skeleton = normalize_outline_skeleton(
        {
            "course_title": "并行系统",
            "positioning": "验证大课目录分片",
            "learning_objectives": ["完成 48 节递进任务"],
            "prerequisites": [],
            "chapters": [
                {
                    "title": f"并行系统阶段 {index}",
                    "learning_focus": f"完成第 {index} 阶段任务",
                    "section_count": 6,
                }
                for index in range(1, 9)
            ],
        },
        topic="并行系统",
        request_fingerprint=fingerprint,
    )
    report = validate_outline_skeleton(
        skeleton,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
    )
    assert report["passed"]

    specs = build_outline_batch_specs(
        skeleton,
        CourseOutlinePlanningBudget(batch_max_sections=6),
    )
    assert len(specs) == 8
    assert all(spec["section_count"] <= 6 for spec in specs)

    chapter_by_number = {
        item["chapter_number"]: item
        for item in skeleton["chapters"]
    }
    batches = {
        spec["batch_id"]: compile_fallback_outline_batch(
            spec=spec,
            chapter=chapter_by_number[spec["chapter_number"]],
            skeleton_revision_id=skeleton["revision_id"],
        )
        for spec in specs
    }
    assert all(
        validate_outline_batch(
            batches[spec["batch_id"]],
            spec=spec,
            skeleton_revision_id=skeleton["revision_id"],
        )["passed"]
        for spec in specs
    )

    outline = assemble_course_outline(
        skeleton=skeleton,
        batch_specs=specs,
        batches=batches,
    )
    assert len(outline["chapters"]) == 8
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 48


@pytest.mark.asyncio
async def test_forty_eight_section_outline_uses_parallel_bounded_batches(
    monkeypatch,
):
    service = CourseService(planning_concurrency=4)
    active = 0
    max_active = 0
    payloads: list[tuple[str, str, dict]] = []
    growth_snapshots: list[dict] = []

    async def capture_phase(
        _phase,
        _progress,
        _message,
        _phase_progress,
        phase_detail,
    ):
        growth = phase_detail.get("outline_growth") or {}
        if growth:
            growth_snapshots.append(deepcopy(growth))

    async def fake_call(prompt, system_prompt="", **kwargs):
        nonlocal active, max_active
        payloads.append((prompt, system_prompt, kwargs))
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=8,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-outline-48",
        topic="并行系统",
        requirements="生成 8 章，共 48 个小节",
        stop_after_outline=True,
        on_phase=capture_phase,
    )

    outline = result["course_outline"]
    assert len(outline["chapters"]) == 8
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 48
    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["strategy"] == "hierarchical_chapter_batches"
    assert stage["batch_count"] == 8
    assert stage["completed_batch_count"] == 8
    assert stage["fallback_units"] == []
    assert max_active >= 2
    assert max_active <= 4
    assert len(payloads) == 9
    assert growth_snapshots[0]["state"] == "skeleton_ready"
    assert growth_snapshots[0]["total_sections"] == 48
    assert growth_snapshots[-1]["state"] == "completed"
    assert growth_snapshots[-1]["completed_sections"] == 48
    assert growth_snapshots[-1]["chapters"][0]["sections"][0] == {
        "node_id": "L2-1-1",
        "section_number": "1.1",
        "title": "任务 L2-1-1",
        "learning_objective": "独立完成 L2-1-1",
    }
    for user_prompt, system_prompt, kwargs in payloads:
        assert len(user_prompt) + len(system_prompt) <= 32_000
        assert AIBase.estimate_request_tokens(
            user_prompt,
            system_prompt,
        ) <= 16_000
        assert kwargs["max_input_chars"] == 32_000
        assert kwargs["max_input_tokens"] == 16_000


@pytest.mark.asyncio
async def test_outline_waits_for_productive_batches_without_whole_course_deadline(
    monkeypatch,
):
    service = CourseService(planning_concurrency=2)
    service._outline_budget = CourseOutlinePlanningBudget(
        batch_max_sections=6,
        batch_timeout_seconds=1,
        total_timeout_seconds=0.02,
    )

    async def fake_call(prompt, system_prompt="", **kwargs):
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=4,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            await asyncio.sleep(0.2)
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-outline-timeout",
        topic="并行系统",
        requirements="生成 4 章，共 24 个小节",
        stop_after_outline=True,
    )

    outline = result["course_outline"]
    assert sum(
        len(chapter["sections"])
        for chapter in outline["chapters"]
    ) == 24
    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["timed_out"] is False
    assert stage["status"] == "completed"
    assert stage["needs_manual_review"] is False
    assert stage["fallback_units"] == []


@pytest.mark.asyncio
async def test_outline_resume_only_requests_missing_chapter_batch(monkeypatch):
    first_service = CourseService(planning_concurrency=3)

    async def first_call(prompt, system_prompt="", **kwargs):
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_payload(
                chapter_count=3,
                sections_per_chapter=6,
            )
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(first_service, "_call_llm", first_call)
    completed = await first_service.build_course_draft(
        course_id="course-outline-resume",
        topic="并行系统",
        requirements="生成 3 章，共 18 个小节",
        stop_after_outline=True,
    )
    checkpoint = deepcopy(completed)
    checkpoint.pop("course_outline", None)
    checkpoint.pop("course_plan", None)
    outline_stage = checkpoint["generation_stage_artifacts"]["outline"]
    outline_stage["batches"].pop("OUT-C002-B001")
    outline_stage["status"] = "in_progress"
    outline_stage["completed_batch_count"] = 2
    outline_stage["completed_section_count"] = 12

    resumed_calls: list[str] = []
    resumed_service = CourseService(planning_concurrency=3)

    async def resumed_call(prompt, system_prompt="", **kwargs):
        resumed_calls.append(system_prompt)
        assert "章节小节目录批次 V2" in system_prompt
        return _outline_batch_payload(system_prompt)

    monkeypatch.setattr(resumed_service, "_call_llm", resumed_call)
    resumed = await resumed_service.build_course_draft(
        course_id="course-outline-resume",
        topic="并行系统",
        requirements="生成 3 章，共 18 个小节",
        existing_course_data=checkpoint,
        stop_after_outline=True,
    )

    assert len(resumed_calls) == 1
    assert "OUT-C002-B001" in resumed_calls[0]
    assert sum(
        len(chapter["sections"])
        for chapter in resumed["course_outline"]["chapters"]
    ) == 18
    assert (
        resumed["generation_stage_artifacts"]["outline"]["status"]
        == "completed"
    )


@pytest.mark.asyncio
async def test_outline_resume_keeps_teacher_confirmed_shape_when_brief_drifts(
    monkeypatch,
):
    first_service = CourseService(planning_concurrency=3)

    async def first_call(prompt, system_prompt="", **kwargs):
        assert "全课章节骨架 V2" in system_prompt
        return _outline_skeleton_payload(
            chapter_count=6,
            sections_per_chapter=4,
        )

    monkeypatch.setattr(first_service, "_call_llm", first_call)
    checkpoint = await first_service.build_course_draft(
        course_id="course-confirmed-shape-resume",
        topic="并行系统",
        requirements="先生成全课程骨架",
        stop_after_skeleton=True,
    )
    stage = checkpoint["generation_stage_artifacts"]["outline"]
    chapters = deepcopy(stage["skeleton"]["chapters"])
    confirmed_counts = [4, 5, 6, 4, 5, 6]
    for chapter, count in zip(chapters, confirmed_counts, strict=True):
        chapter["section_count"] = count
    confirmed = normalize_outline_skeleton(
        {**deepcopy(stage["skeleton"]), "chapters": chapters},
        topic="并行系统",
        request_fingerprint=stage["request_fingerprint"],
    )
    stage.update({
        "shape_confirmed": True,
        "confirmed_shape_constraints": {
            "chapter_count": 6,
            "section_count": 30,
        },
        "skeleton": confirmed,
        "skeleton_revision_id": confirmed["revision_id"],
        "batches": {},
    })

    resumed_calls: list[str] = []
    resumed_service = CourseService(planning_concurrency=3)

    async def resumed_call(prompt, system_prompt="", **kwargs):
        resumed_calls.append(system_prompt)
        assert "章节小节目录批次 V2" in system_prompt
        return _outline_batch_payload(system_prompt)

    monkeypatch.setattr(resumed_service, "_call_llm", resumed_call)
    resumed = await resumed_service.build_course_draft(
        course_id="course-confirmed-shape-resume",
        topic="并行系统",
        # Simulate a reconstructed brief whose derived fingerprint differs
        # after restart.  The confirmed skeleton remains authoritative.
        requirements="恢复后的派生需求文本已变化",
        existing_course_data=checkpoint,
        stop_after_outline=True,
    )

    assert resumed_calls
    assert all("全课章节骨架 V2" not in item for item in resumed_calls)
    assert [
        len(chapter["sections"])
        for chapter in resumed["course_outline"]["chapters"]
    ] == confirmed_counts
    resumed_stage = resumed["generation_stage_artifacts"]["outline"]
    assert resumed_stage["shape_confirmed"] is True
    assert resumed_stage["confirmed_shape_constraints"]["section_count"] == 30


def test_outline_fingerprint_ignores_ephemeral_brief_id():
    from course_generation.outline import outline_request_fingerprint

    common = {
        "topic": "并行系统",
        "audience": "大学生",
        "difficulty_profile": {"level": "intermediate"},
    }
    first = outline_request_fingerprint(
        **common,
        brief={"brief_id": "brief-first", "goal": "学会并行系统"},
    )
    second = outline_request_fingerprint(
        **common,
        brief={"brief_id": "brief-second", "goal": "学会并行系统"},
    )

    assert first == second


def test_section_scope_payload_stays_linear_and_each_slice_is_bounded():
    def make_plan(section_count: int) -> dict:
        return {
            "course_title": "线性上下文验证",
            "positioning": "验证大课不会重复广播全部前后小节",
            "learning_objectives": ["完成全部递进任务"],
            "prerequisites": [],
            "chapters": [{
                "chapter_number": 1,
                "title": "主线",
                "sections": [
                    {
                        "node_id": f"L2-1-{index}",
                        "section_number": f"1.{index}",
                        "title": f"任务 {index}",
                        "learning_objective": f"完成任务 {index}",
                        "scope_boundary": f"只负责任务 {index}",
                        "prerequisite_node_ids": (
                            [f"L2-1-{index - 1}"] if index > 1 else []
                        ),
                    }
                    for index in range(1, section_count + 1)
                ],
            }],
        }

    contract_50 = build_course_knowledge_scope_contract(make_plan(50))
    contract_100 = build_course_knowledge_scope_contract(make_plan(100))
    size_50 = len(json.dumps(contract_50, ensure_ascii=False))
    size_100 = len(json.dumps(contract_100, ensure_ascii=False))
    assert size_100 < size_50 * 2.2
    assert all(
        "earlier_section_ids" not in item
        and "later_reserved_sections" not in item
        for item in contract_100["section_responsibilities"]
    )

    middle = build_section_knowledge_scope_slice(
        contract_100,
        "L2-1-50",
    )
    assert middle["schema_version"] == (
        "section_knowledge_scope_slice_v2"
    )
    assert len(middle["local_course_path"]) <= 3


# --- D-1 课程规格判定 -------------------------------------------------------


def _calculus_brief(total_class_hours: int) -> dict:
    """Build the brief a 微积分 request with N class hours actually produces."""
    return build_course_generation_artifacts(
        course_id="course-calculus-test",
        topic="微积分",
        difficulty="intermediate",
        style="standard",
        target_audience="大一本科生",
        teacher_course_brief={
            "schema_version": "teacher_course_brief_v1",
            "target_audience": "大一本科生",
            "total_class_hours": total_class_hours,
            "lesson_duration_minutes": 45,
            "teaching_context": "classroom",
        },
    )["course_generation_brief"]


def test_eight_class_hour_calculus_is_judged_before_generation():
    """8 课时的微积分必须在生成前被判为微型课，且不得自称完整课程。"""
    verdict = course_coverage_verdict(
        subject="微积分",
        brief=_calculus_brief(8),
    )

    assert verdict["scale"] == "micro"
    assert verdict["may_claim_complete_subject"] is False
    assert verdict["status"] == "partial"
    # 必须给出两条出路，而不是静默降级。
    advisories = " ".join(verdict["advisories"])
    assert "压缩为核心课" in advisories
    assert "增加课时" in advisories


def test_eight_class_hour_calculus_names_every_uncovered_topic():
    """任务书点名的缺失知识点，要么覆盖，要么被明确列为本次不覆盖。"""
    typical_eight_section_plan = {
        "course_title": "微积分核心概览课",
        "positioning": "在 8 课时内掌握微积分的核心推理链条",
        "learning_objectives": ["能够计算导数与定积分"],
        "chapters": [
            {"chapter_number": 1, "title": "函数与极限", "learning_focus": "理解极限与连续性", "section_count": 2},
            {"chapter_number": 2, "title": "导数", "learning_focus": "掌握导数的定义与基本求导法则", "section_count": 3},
            {"chapter_number": 3, "title": "积分", "learning_focus": "掌握不定积分与定积分及微积分基本定理", "section_count": 3},
        ],
    }
    verdict = course_coverage_verdict(
        subject="微积分",
        brief=_calculus_brief(8),
        skeleton=typical_eight_section_plan,
    )

    uncovered = set(verdict["uncovered_topics"])
    covered = set(verdict["covered_topics"])

    # 任务书点名的六项：每一项要么覆盖，要么明确列为不覆盖，不允许无声消失。
    for topic in (
        "隐函数求导与相关变化率",
        "中值定理",
        "洛必达法则与未定式",
        "微分方程入门",
        "积分技巧：换元与分部积分",
        "反常积分",
    ):
        assert topic in uncovered, f"{topic} 既未覆盖也未被列为不覆盖"
    # 计划里真的讲了的，必须判为已覆盖，否则提示会变成噪音。
    assert "函数、极限与连续" in covered
    assert "导数定义与求导法则" in covered
    assert "定积分与微积分基本定理" in covered


def test_short_course_may_not_call_itself_complete():
    """自称完整课程的短课骨架必须被拦下。"""
    brief = _calculus_brief(8)
    shape = brief.get("course_shape_constraints") or {}
    fingerprint = outline_request_fingerprint(
        topic="微积分",
        audience="大一本科生",
        brief=brief,
        difficulty_profile={"level": "intermediate"},
    )
    dishonest = normalize_outline_skeleton(
        {
            "course_title": "微积分完整课程",
            "positioning": "完整覆盖微积分的全部核心内容",
            "chapters": [
                {"chapter_number": 1, "title": "极限", "section_count": 4},
                {"chapter_number": 2, "title": "导数", "section_count": 4},
            ],
        },
        topic="微积分",
        request_fingerprint=fingerprint,
    )
    verdict = course_coverage_verdict(
        subject="微积分",
        brief=brief,
        skeleton=dishonest,
    )

    report = validate_outline_skeleton(
        dishonest,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
        coverage_verdict=verdict,
    )

    assert report["passed"] is False
    assert "outline_skeleton:unsupported_completeness_claim" in {
        issue["code"] for issue in report["issues"]
    }


def test_short_course_may_state_that_it_does_not_cover_everything():
    """否定式范围说明是诚实边界，不应被关键词门禁误判。"""
    brief = _calculus_brief(8)
    shape = brief.get("course_shape_constraints") or {}
    fingerprint = outline_request_fingerprint(
        topic="微积分",
        audience="大一本科生",
        brief=brief,
        difficulty_profile={"level": "intermediate"},
    )
    honest = normalize_outline_skeleton(
        {
            "course_title": "微积分核心概览课",
            "positioning": "本课不追求学科完整覆盖，只训练极限与导数的核心推理。",
            "chapters": [
                {"chapter_number": 1, "title": "极限", "section_count": 4},
                {"chapter_number": 2, "title": "导数", "section_count": 4},
            ],
        },
        topic="微积分",
        request_fingerprint=fingerprint,
    )
    verdict = course_coverage_verdict(
        subject="微积分",
        brief=brief,
        skeleton=honest,
    )

    report = validate_outline_skeleton(
        honest,
        shape_constraints=shape,
        request_fingerprint=fingerprint,
        coverage_verdict=verdict,
    )

    assert "outline_skeleton:unsupported_completeness_claim" not in {
        issue["code"] for issue in report["issues"]
    }


def test_full_term_course_may_still_claim_completeness():
    """完整学期课不应被这道诚实性门误伤。"""
    brief = _calculus_brief(64)
    fingerprint = outline_request_fingerprint(
        topic="微积分",
        audience="大一本科生",
        brief=brief,
        difficulty_profile={"level": "intermediate"},
    )
    skeleton = normalize_outline_skeleton(
        {
            "course_title": "微积分完整课程",
            "positioning": "完整覆盖微积分主干知识结构",
            "chapters": [
                {"chapter_number": index, "title": f"第 {index} 章", "section_count": 4}
                for index in range(1, 9)
            ],
        },
        topic="微积分",
        request_fingerprint=fingerprint,
    )
    verdict = course_coverage_verdict(subject="微积分", brief=brief)

    assert verdict["scale"] == "full_term"
    assert verdict["may_claim_complete_subject"] is True

    report = validate_outline_skeleton(
        skeleton,
        shape_constraints=brief.get("course_shape_constraints") or {},
        request_fingerprint=fingerprint,
        coverage_verdict=verdict,
    )

    assert "outline_skeleton:unsupported_completeness_claim" not in {
        issue["code"] for issue in report["issues"]
    }
