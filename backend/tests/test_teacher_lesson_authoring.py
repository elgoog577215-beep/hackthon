from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_base import AIProviderUnavailable

from course_document import document_from_generation_draft
from teacher_lesson_authoring import (
    TeacherLessonAuthoringError,
    TeacherLessonAuthoringRepository,
    TeacherLessonAuthoringService,
    extract_uploaded_pptx_evidence,
    lesson_scope,
    normalize_teacher_lesson_plan,
    teacher_lesson_script_revision,
    teacher_lesson_section_content,
    teacher_lesson_v6_source,
    validate_teacher_lesson_plan,
)
from teacher_script import (
    compile_teacher_script_module_contract,
    compile_teacher_script_section,
    normalize_teacher_script_section,
    validate_teacher_script_section,
)
from course_presentation_graph import compile_course_presentation_graph
from course_service import CourseService
from dependencies import get_teacher_lesson_authoring_repository, require_task_manager
from lesson_arrangement import (
    _lesson_type,
    apply_lesson_arrangement_to_plan,
    recommend_lesson_arrangement,
    validate_lesson_arrangement,
)
from routers import teacher_lesson_authoring as teacher_lesson_router
from routers import courses as courses_router


def course_data():
    return {
        "course_id": "course-1",
        "nodes": [
            {"node_id": "L1-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一讲"},
            {"node_id": "L2-1-1", "parent_node_id": "L1-1", "node_level": 2, "node_name": "1.1"},
            {"node_id": "L2-1-2", "parent_node_id": "L1-1", "node_level": 2, "node_name": "1.2"},
            {"node_id": "L1-2", "parent_node_id": "root", "node_level": 1, "node_name": "第二讲"},
            {"node_id": "L2-2-1", "parent_node_id": "L1-2", "node_level": 2, "node_name": "2.1"},
        ],
        "course_plan": {
            "chapters": [
                {"node_id": "L1-1", "title": "第一讲", "sections": [{"node_id": "L2-1-1"}, {"node_id": "L2-1-2"}]},
                {"node_id": "L1-2", "title": "第二讲", "sections": [{"node_id": "L2-2-1"}]},
            ]
        },
    }


def standard_lesson_plan():
    return {
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": "outline-v1",
        "sections": [{
            "node_id": "L2-1-1",
            "learning_objective": "能独立解释核心概念并完成一次迁移应用。",
            "key_points": ["核心概念"],
            "key_difficulties": ["概念的适用边界"],
            "in_class_checks": ["完成一道情境判断并说明依据。"],
            "homework": ["用新场景复述概念并给出反例。"],
            "teaching_notes": ["保留学生产出用于课后复盘。"],
            "knowledge_structure": [{
                "knowledge_points": [{
                    "name": "核心概念",
                    "statement": "核心概念由定义、条件和边界共同构成。",
                }],
            }],
            "teaching_modules": [{
                "module_id": "core_explanation",
                "teaching_purpose": "建立概念框架",
                "knowledge_names": ["核心概念"],
                "planned_minutes": 20,
                "teacher_activity": "用正例与反例对照讲解定义和边界。",
                "student_activity": "归纳判断标准并完成情境判断。",
            }],
        }],
    }


def test_lesson_scope_keeps_all_sections_inside_one_lesson():
    scoped = lesson_scope(course_data(), "L1-1")
    assert scoped["lesson"]["node_name"] == "第一讲"
    assert [item["node_id"] for item in scoped["sections"]] == ["L2-1-1", "L2-1-2"]
    assert scoped["chapter"]["node_id"] == "L1-1"


def test_lesson_arrangement_projects_existing_modules_without_example_exam_collision():
    arrangement = recommend_lesson_arrangement(
        course_data(),
        "L1-2",
        source_outline_revision_id="outline-v1",
    )

    assert arrangement["lesson_type"] == "theory"
    assert arrangement["confirmed"] is False
    assert {item["section_node_id"] for item in arrangement["blocks"]} == {"L2-2-1"}
    assert validate_lesson_arrangement(
        arrangement,
        expected_section_ids=["L2-2-1"],
    ) == []

    applied = apply_lesson_arrangement_to_plan(
        course_data()["course_plan"],
        {**arrangement, "lesson_type": "case_discussion"},
    )
    section = applied["chapters"][1]["sections"][0]
    assert section["lesson_archetype"]["label"] == "案例研讨"
    assert [item["arrangement_block_id"] for item in section["module_plan"]] == [
        item["block_id"] for item in arrangement["blocks"]
    ]

    assert _lesson_type(
        ["engineering_debugging_lab", "engineering_guided_build"],
        ["core_explanation", "engineering_review", "engineering_testing"],
    ) == "theory_practice"


def test_lesson_arrangement_adapts_legacy_node_outline_into_same_recommendation():
    legacy = course_data()
    legacy.pop("course_plan")

    arrangement = recommend_lesson_arrangement(
        legacy,
        "L1-1",
        source_outline_revision_id="legacy-outline-v1",
    )

    assert arrangement["blocks"]
    assert {item["section_node_id"] for item in arrangement["blocks"]} == {
        "L2-1-1",
        "L2-1-2",
    }
    assert validate_lesson_arrangement(
        arrangement,
        expected_section_ids=["L2-1-1", "L2-1-2"],
    ) == []


def test_lesson_arrangement_compacts_large_legacy_chapter_to_one_row_per_section():
    legacy = course_data()
    legacy.pop("course_plan")
    legacy["nodes"] = [legacy["nodes"][0], *[
        {
            "node_id": f"legacy-section-{index}",
            "parent_node_id": "L1-1",
            "node_level": 2,
            "node_name": f"1.{index} 历史小节{index}",
        }
        for index in range(1, 7)
    ]]

    arrangement = recommend_lesson_arrangement(legacy, "L1-1")

    assert len(arrangement["blocks"]) == 6
    assert {item["section_node_id"] for item in arrangement["blocks"]} == {
        f"legacy-section-{index}" for index in range(1, 7)
    }
    assert all(item["module_id"] == "teacher_section_sequence" for item in arrangement["blocks"])
    assert all("→" in item["content_summary"] for item in arrangement["blocks"])


def test_standard_lesson_plan_quality_gate_is_shared_by_draft_and_confirmation():
    report = validate_teacher_lesson_plan(
        standard_lesson_plan(),
        expected_section_ids=["L2-1-1"],
        expected_outline_revision_id="outline-v1",
        source_outline_revision_id="outline-v1",
    )
    assert report["passed"] is True
    assert report["pipeline_version"] == "standard_lesson_plan_v1"
    assert report["metrics"]["planned_minutes"] == 20

    incomplete = standard_lesson_plan()
    incomplete["sections"][0]["in_class_checks"] = []
    incomplete["sections"][0]["teaching_modules"] = []
    blocked = validate_teacher_lesson_plan(
        incomplete,
        expected_section_ids=["L2-1-1"],
    )
    assert blocked["passed"] is False
    assert {item["code"] for item in blocked["blocking_issues"]} >= {
        "lesson_plan:modules",
        "lesson_plan:checks",
    }


def test_teacher_script_inherits_confirmed_archetype_and_module_order():
    outline = {
        "node_id": "L2-1-1",
        "node_name": "1.1 核心概念",
        "lesson_archetype": {
            "archetype_id": "general_concept_building",
            "label": "概念建构",
        },
        "module_plan": [
            {"module_id": "lesson_goal", "label": "本节任务", "required": True},
            {"module_id": "general_concept_model", "label": "概念模型", "required": True},
            {"module_id": "feedback_check", "label": "检查与反馈", "required": True},
        ],
    }
    plan = {
        "node_id": "L2-1-1",
        "learning_objective": "能解释概念并划清边界。",
        "teaching_modules": [
            {"module_id": "lesson_goal", "planned_minutes": 3},
            {"module_id": "general_concept_model", "planned_minutes": 20},
            {"module_id": "feedback_check", "planned_minutes": 7},
        ],
    }

    contract = compile_teacher_script_module_contract(outline, plan)
    assert contract["lesson_archetype"]["label"] == "概念建构"
    assert [item["module_id"] for item in contract["modules"]] == [
        "lesson_goal", "general_concept_model", "feedback_check",
    ]
    assert [item["title"] for item in contract["modules"]] == [
        "本节任务", "概念模型", "检查与反馈",
    ]
    assert 350 < contract["modules"][0]["max_characters"] <= 600
    assert contract["modules"][1]["max_characters"] <= 1600

    compiled = compile_teacher_script_section(
        "## 本节任务\n\n今天我们先明确要解决的问题和课后可验证的成果。\n\n"
        "## 概念模型\n\n【板书】从定义、条件与边界三个方面逐步建立概念模型，并用正反例核对。\n\n"
        "## 检查与反馈\n\n【提问】请判断一个新情境并说明依据；随后对照标准定位典型错误。",
        contract,
    )
    assert compiled["quality_report"]["passed"] is True
    assert [item["module_id"] for item in compiled["blocks"]] == [
        "lesson_goal", "general_concept_model", "feedback_check",
    ]
    source = course_data()
    source["nodes"][1].update(outline)
    _document, view, _synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id="L1-1",
        plan_revision={
            "revision_id": "plan-1",
            "plan": {
                "schema_version": "course_teaching_plan_v3",
                "sections": [plan],
            },
        },
        script_revision={
            "revision_id": "script-1",
            "sections": [
                compiled,
                {
                    "section_node_id": "L2-1-2",
                    "blocks": [{
                        "block_id": "second-section-block",
                        "module_id": "legacy_script",
                        "role": "concept",
                        "title": "第二小节讲稿",
                        "content": "这是第二小节已经确认的讲稿内容。",
                    }],
                },
            ],
        },
    )
    projected_blocks = view["nodes"][1]["content_blocks"]
    assert [item["metadata"]["module_id"] for item in projected_blocks] == [
        "lesson_goal", "general_concept_model", "feedback_check",
    ]
    assert all(
        item["metadata"]["source_kind"] == "confirmed_teacher_script_block"
        for item in projected_blocks
    )
    assert all(item["title"] != "讲稿正文" for item in projected_blocks)

    generic = compile_teacher_script_section(
        "## 背景导入\n\n这是一段模型自行增加的通用模板内容。",
        contract,
    )
    report = validate_teacher_script_section(generic, contract)
    assert report["passed"] is False
    assert {item["code"] for item in report["blocking_issues"]} >= {
        "teacher_script:module_contract",
        "teacher_script:module_heading",
    }

    tampered = json.loads(json.dumps(compiled))
    tampered["blocks"][0]["block_id"] = "replacement-block"
    tampered["blocks"][0]["role"] = "example"
    tampered["blocks"][0]["knowledge_names"] = ["教案范围外知识"]
    tampered_report = validate_teacher_script_section(tampered, contract)
    assert {item["code"] for item in tampered_report["blocking_issues"]} >= {
        "teacher_script:block_contract",
        "teacher_script:role_contract",
        "teacher_script:knowledge_scope",
    }


@pytest.mark.parametrize(
    ("module_id", "content", "missing_code"),
    [
        (
            "engineering_minimal_run",
            "```python\nprint('hello')\n```\n\n【演示】运行后输出 hello，并核对环境版本。",
            "teacher_script:required_code_artifact",
        ),
        (
            "math_formalization",
            "【板书】定义 $f(x)=x^2$，逐一说明变量、定义域与适用边界。",
            "teacher_script:required_math_artifact",
        ),
    ],
)
def test_teacher_script_enforces_discipline_artifacts(module_id, content, missing_code):
    outline = {
        "node_id": "L2-1-1",
        "node_name": "学科小节",
        "module_plan": [{"module_id": module_id}],
    }
    plan = {
        "node_id": "L2-1-1",
        "teaching_modules": [{"module_id": module_id}],
    }
    contract = compile_teacher_script_module_contract(outline, plan)
    title = contract["modules"][0]["title"]
    complete = compile_teacher_script_section(f"## {title}\n\n{content}", contract)
    assert complete["quality_report"]["passed"] is True

    missing = compile_teacher_script_section(
        f"## {title}\n\n这里只给出概括性说明，没有提供本模块要求的正式学科产物。",
        contract,
    )
    assert missing["quality_report"]["passed"] is False
    assert missing_code in {
        item["code"] for item in missing["quality_report"]["blocking_issues"]
    }


def test_teacher_script_rejects_unclosed_code_and_math_delimiters():
    outline = {
        "node_id": "L2-1-1",
        "node_name": "完整性检查",
        "module_plan": [{"module_id": "core_explanation"}],
    }
    plan = {
        "node_id": "L2-1-1",
        "teaching_modules": [{"module_id": "core_explanation"}],
    }
    contract = compile_teacher_script_module_contract(outline, plan)
    title = contract["modules"][0]["title"]
    compiled = compile_teacher_script_section(
        f"## {title}\n\n```text\n未闭合代码\n\n同时出现未闭合公式 $$x+y。",
        contract,
    )
    codes = {
        item["code"] for item in compiled["quality_report"]["blocking_issues"]
    }
    assert "teacher_script:unclosed_code_fence" in codes
    assert "teacher_script:unclosed_math_delimiter" in codes

    inline = compile_teacher_script_section(
        f"## {title}\n\n公式在返回前被截断：$F_x=6-3",
        contract,
    )
    inline_codes = {
        item["code"]
        for item in inline["quality_report"]["blocking_issues"]
    }
    assert "teacher_script:unclosed_math_delimiter" in inline_codes


def test_teacher_script_service_uses_teacher_prompt_instead_of_self_study_rewrite(monkeypatch):
    service = CourseService()
    captured = {}

    async def fake_call(user_prompt, system_prompt, **kwargs):
        captured["user_prompt"] = user_prompt
        captured["system_prompt"] = system_prompt
        captured["kwargs"] = kwargs
        return "## 核心教学\n\n【板书】围绕定义、条件和边界展开讲解，并用一个正例与反例组织课堂判断。"

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = asyncio.run(service.generate_teacher_script_section(
        course_id="course-1",
        outline_section={
            "node_id": "L2-1-1",
            "node_name": "1.1 核心概念",
            "lesson_archetype": {
                "archetype_id": "general_concept_building",
                "label": "概念建构",
                "purpose": "建立概念、关系和边界。",
            },
            "module_plan": [{
                "module_id": "core_explanation",
                "label": "核心教学",
                "required": True,
            }],
        },
        confirmed_plan_section={
            "node_id": "L2-1-1",
            "learning_objective": "能解释核心概念并划清边界。",
            "teaching_modules": [{
                "module_id": "core_explanation",
                "knowledge_names": ["核心概念"],
                "planned_minutes": 20,
                "teacher_activity": "用正反例讲解。",
            }],
        },
        lesson_context={"lesson_title": "第一讲"},
        requirements="贴近课堂表达",
    ))

    assert result["quality_report"]["passed"] is True
    assert "教师生成可直接在课堂上使用的讲稿" in captured["system_prompt"]
    assert "本节课型：概念建构" in captured["system_prompt"]
    assert "学科类型与当前教学块策略" in captured["system_prompt"]
    assert "前后小节连贯与课程总编约束" in captured["system_prompt"]
    assert "学生自学教材口吻" in captured["system_prompt"]
    assert "## 核心教学" in captured["system_prompt"]
    assert "轻量的教师讲授支架" in captured["system_prompt"]
    assert "不得超过" in captured["system_prompt"]
    assert "自学课程的完整小节" not in captured["system_prompt"]
    assert captured["kwargs"]["use_fast_model"] is True
    assert captured["kwargs"]["enable_thinking"] is False
    assert captured["kwargs"]["max_attempts"] == 2
    assert captured["kwargs"]["reject_truncated"] is True


def test_teacher_script_rejects_textbook_length_block():
    outline = {
        "node_id": "L2-1-1",
        "node_name": "轻量讲稿",
        "module_plan": [{"module_id": "core_explanation"}],
    }
    plan = {
        "node_id": "L2-1-1",
        "teaching_modules": [{
            "module_id": "core_explanation",
            "planned_minutes": 10,
        }],
    }
    contract = compile_teacher_script_module_contract(outline, plan)
    module = contract["modules"][0]
    oversized = "这是重复展开的教材式讲解。" * (module["max_characters"] // 10 + 20)
    compiled = compile_teacher_script_section(
        f"## {module['title']}\n\n{oversized}",
        contract,
    )
    assert compiled["quality_report"]["passed"] is False
    assert "teacher_script:block_too_long" in {
        item["code"]
        for item in compiled["quality_report"]["blocking_issues"]
    }


def test_teacher_script_service_compacts_length_only_failure(monkeypatch):
    service = CourseService()
    calls = []

    async def fake_call(user_prompt, _system_prompt, **_kwargs):
        calls.append(user_prompt)
        if len(calls) < 3:
            return "## 核心教学\n\n" + "重复讲解。" * 400
        return (
            "## 核心教学\n\n"
            "【板书】简明说明定义、成立条件与适用边界，"
            "再用一个正例检查学生是否能独立判断。"
        )

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = asyncio.run(service.generate_teacher_script_section(
        course_id="course-compact",
        outline_section={
            "node_id": "L2-1-1",
            "node_name": "轻量讲解",
            "module_plan": [{
                "module_id": "core_explanation",
                "label": "核心教学",
            }],
        },
        confirmed_plan_section={
            "node_id": "L2-1-1",
            "teaching_modules": [{
                "module_id": "core_explanation",
                "planned_minutes": 10,
            }],
        },
    ))

    assert len(calls) == 3
    assert "请压缩下面的教师讲稿" in calls[-1]
    assert result["quality_report"]["passed"] is True


def test_teacher_script_service_uses_smart_pool_after_fast_pool_failure(monkeypatch):
    service = CourseService()
    routes = []

    async def fake_call(_user_prompt, _system_prompt, **kwargs):
        routes.append(kwargs["use_fast_model"])
        if kwargs["use_fast_model"]:
            raise AIProviderUnavailable("fast_pool_exhausted")
        return (
            "## 核心教学\n\n"
            "【板书】简明说明定义、条件和边界，并用一个新情境核对。"
        )

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = asyncio.run(service.generate_teacher_script_section(
        course_id="course-smart-fallback",
        outline_section={
            "node_id": "L2-1-1",
            "node_name": "轻量讲解",
            "module_plan": [{
                "module_id": "core_explanation",
                "label": "核心教学",
            }],
        },
        confirmed_plan_section={
            "node_id": "L2-1-1",
            "teaching_modules": [{"module_id": "core_explanation"}],
        },
    ))

    assert routes == [True, False]
    assert result["quality_report"]["passed"] is True


def test_script_job_keeps_completed_blocks_and_resumes_only_missing_work(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = TeacherLessonAuthoringService(repository)
    plan = standard_lesson_plan()
    plan["sections"][0]["teaching_modules"].append({
        "module_id": "feedback_check",
        "teaching_purpose": "检查学生是否掌握判断标准",
        "knowledge_names": ["核心概念"],
        "planned_minutes": 8,
        "teacher_activity": "给出新情境并追问判断依据。",
        "student_activity": "独立判断并说明理由。",
    })
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        plan,
        source_outline_revision_id="outline-v1",
        quality_report=validate_teacher_lesson_plan(plan),
    )
    plan_revision = lesson["working_revision_id"]
    repository.confirm_plan_revision("course-1", "L1-1", plan_revision)
    outline_section = {
        "node_id": "L2-1-1",
        "node_name": "1.1 核心概念",
        "module_plan": [
            {"module_id": "core_explanation", "label": "核心教学"},
            {"module_id": "feedback_check", "label": "检查与反馈"},
        ],
    }

    first_job = repository.create_job(
        "course-1",
        "L1-1",
        job_type="teacher_lesson_script_generation",
        request_id="script-fail-on-second-block",
    )

    async def first_generator(_outline, _plan, module, _completed):
        if module["module_id"] == "feedback_check":
            raise RuntimeError("provider interrupted")
        return "【板书】从定义、条件与边界讲清核心概念，并用正反例形成判断标准。"

    failed = asyncio.run(service.run_script_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=first_job["id"],
        source_plan_revision_id=plan_revision,
        outline_sections=[outline_section],
        plan_sections={"L2-1-1": plan["sections"][0]},
        generator=first_generator,
    ))

    assert failed["status"] == "failed"
    assert failed["completed_blocks"] == 1
    assert failed["total_blocks"] == 2
    assert failed["result_sections"][0]["blocks"][0]["module_id"] == "core_explanation"
    assert repository.lesson("course-1", "L1-1")["working_script_revision_id"] == ""

    second_job = repository.create_job(
        "course-1",
        "L1-1",
        job_type="teacher_lesson_script_generation",
        request_id="script-resume",
    )
    resumed_modules = []

    async def resume_generator(_outline, _plan, module, completed):
        resumed_modules.append(module["module_id"])
        assert [item["module_id"] for item in completed] == ["core_explanation"]
        return "【提问】请判断一个新情境并说明依据，再对照标准纠正常见错误。"

    completed = asyncio.run(service.run_script_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=second_job["id"],
        source_plan_revision_id=plan_revision,
        outline_sections=[outline_section],
        plan_sections={"L2-1-1": plan["sections"][0]},
        generator=resume_generator,
        seed_sections=failed["result_sections"],
    ))

    assert completed["status"] == "completed"
    assert resumed_modules == ["feedback_check"]
    revision = repository.lesson("course-1", "L1-1")["script_revisions"][0]
    assert [item["module_id"] for item in revision["sections"][0]["blocks"]] == [
        "core_explanation",
        "feedback_check",
    ]


def test_script_resume_discards_only_invalid_checkpoint_block(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = TeacherLessonAuthoringService(repository)
    plan = standard_lesson_plan()
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        plan,
        source_outline_revision_id="outline-v1",
        quality_report=validate_teacher_lesson_plan(plan),
    )
    plan_revision = lesson["working_revision_id"]
    repository.confirm_plan_revision("course-1", "L1-1", plan_revision)
    outline_section = {
        "node_id": "L2-1-1",
        "node_name": "1.1 核心概念",
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心教学",
        }],
    }
    job = repository.create_job(
        "course-1",
        "L1-1",
        job_type="teacher_lesson_script_generation",
        request_id="script-invalid-checkpoint",
    )
    generated = []

    async def generator(_outline, _plan, module, _completed):
        generated.append(module["module_id"])
        return "【板书】完整公式 $F_x=6-3=3$\uff0c并核对方向。"

    completed = asyncio.run(service.run_script_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        source_plan_revision_id=plan_revision,
        outline_sections=[outline_section],
        plan_sections={"L2-1-1": plan["sections"][0]},
        generator=generator,
        seed_sections=[{
            "section_node_id": "L2-1-1",
            "blocks": [{
                "block_id": compile_teacher_script_module_contract(
                    outline_section,
                    plan["sections"][0],
                )["modules"][0]["block_id"],
                "module_id": "core_explanation",
                "title": "核心教学",
                "content": "被截断的公式 $F_x=6-3",
            }],
        }],
    ))

    assert completed["status"] == "completed", completed.get("error")
    assert generated == ["core_explanation"]


def test_legacy_script_adapter_keeps_the_original_body_as_one_compatibility_block():
    original = "## 老师原有标题\n\n老师原本的一整篇课堂讲稿。"
    migrated = normalize_teacher_script_section({
        "section_node_id": "L2-1-1",
        "title": "1.1 核心概念",
        "content": original,
    })

    assert len(migrated["blocks"]) == 1
    assert migrated["blocks"][0]["module_id"] == "legacy_script"
    assert migrated["blocks"][0]["content"] == original


def test_teacher_lesson_v6_source_accepts_confirmed_legacy_script_sections():
    source = course_data()
    source["blueprint_revision_id"] = "outline-v1"
    document, view, _synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id="L1-1",
        plan_revision={
            "revision_id": "plan-1",
            "plan": standard_lesson_plan(),
        },
        script_revision={
            "revision_id": "script-legacy",
            "sections": [
                {
                    "section_node_id": "L2-1-1",
                    "title": "1.1 核心概念",
                    "content": "这是老版已确认讲稿的正文。",
                },
                {
                    "section_node_id": "L2-1-2",
                    "title": "1.2 能力迁移",
                    "content": "这是第二小节的已确认讲稿。",
                },
            ],
        },
    )

    assert document.blocks
    assert view["nodes"][1]["content_blocks"][0]["metadata"]["module_id"] == "legacy_script"
    assert view["nodes"][1]["content_blocks"][0]["content"] == "这是老版已确认讲稿的正文。"


def test_canonical_outline_revision_recovers_current_state_and_blocks_weak_plan(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    repository.set_outline("course-1", "blueprint-v1")
    quality = validate_teacher_lesson_plan(
        standard_lesson_plan(),
        expected_section_ids=["L2-1-1"],
        expected_outline_revision_id="knowledge-scope-v1",
        source_outline_revision_id="knowledge-scope-v1",
    )
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        standard_lesson_plan(),
        source_outline_revision_id="knowledge-scope-v1",
        quality_report=quality,
    )
    assert lesson["source_state"] == "stale"

    repository.set_outline("course-1", "knowledge-scope-v1")
    recovered = repository.lesson("course-1", "L1-1")
    assert recovered["source_state"] == "current"
    confirmed = repository.confirm_plan_revision(
        "course-1",
        "L1-1",
        recovered["working_revision_id"],
    )
    assert confirmed["confirmed_revision_id"] == recovered["working_revision_id"]

    weak = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"schema_version": "course_teaching_plan_v3", "sections": [{"node_id": "L2-1-1"}]},
        source_outline_revision_id="knowledge-scope-v1",
    )
    try:
        repository.confirm_plan_revision(
            "course-1",
            "L1-1",
            weak["working_revision_id"],
        )
    except Exception as exc:
        assert getattr(exc, "code", "") == "lesson_plan_quality_blocked"
    else:
        raise AssertionError("不完整教案不应该被确认")


def test_outline_only_lesson_scope_reuses_existing_pedagogy_compiler(monkeypatch):
    service = CourseService()
    captured = {}

    async def fake_prepare(*, course_data, plan, **_kwargs):
        planned_sections = plan["chapters"][0]["sections"]
        captured["module_ids"] = [
            [item["module_id"] for item in section.get("module_plan") or []]
            for section in planned_sections
        ]
        course_data["course_teaching_plan"] = {
            "schema_version": "course_teaching_plan_v3",
            "sections": [
                {"node_id": section["node_id"], "teaching_modules": []}
                for section in planned_sections
            ],
        }
        course_data.setdefault("generation_stage_artifacts", {})["course_teaching_plan"] = {
            "source_outline_revision_id": "outline-v1",
            "fallback_units": [],
        }
        return plan

    monkeypatch.setattr(service, "_prepare_course_teaching_plan", fake_prepare)

    result = asyncio.run(service.prepare_teacher_lesson_plan(
        course_data={**course_data(), "blueprint_revision_id": "outline-v1"},
        lesson_unit_id="L1-1",
    ))

    assert all("core_explanation" in module_ids for module_ids in captured["module_ids"])
    assert [item["node_id"] for item in result["plan"]["sections"]] == ["L2-1-1", "L2-1-2"]


def test_teacher_lesson_plan_resume_reuses_planner_checkpoint(monkeypatch):
    service = CourseService()
    emitted = []

    async def fake_prepare(*, course_data, plan, on_checkpoint, **_kwargs):
        stage = course_data["generation_stage_artifacts"]["course_teaching_plan"]
        assert stage["batches"]["TP-B01"]["status"] == "completed"
        course_data["course_teaching_plan"] = {
            "schema_version": "course_teaching_plan_v3",
            "sections": [
                {"node_id": section["node_id"], "teaching_modules": []}
                for section in plan["chapters"][0]["sections"]
            ],
        }
        stage["source_outline_revision_id"] = "outline-v1"
        stage["fallback_units"] = []
        await on_checkpoint(course_data)
        return plan

    monkeypatch.setattr(service, "_prepare_course_teaching_plan", fake_prepare)
    result = asyncio.run(service.prepare_teacher_lesson_plan(
        course_data={**course_data(), "blueprint_revision_id": "outline-v1"},
        lesson_unit_id="L1-1",
        resume_checkpoint={
            "planner_course_data": {
                "generation_stage_artifacts": {
                    "course_teaching_plan": {
                        "batches": {"TP-B01": {"status": "completed"}},
                    },
                },
            },
        },
        on_checkpoint=lambda checkpoint: emitted.append(checkpoint),
    ))

    assert result["plan"]["sections"]
    assert emitted[0]["schema_version"] == "teacher_lesson_plan_checkpoint_v1"
    assert emitted[0]["planner_course_data"]["generation_stage_artifacts"]["course_teaching_plan"]["batches"]["TP-B01"]["status"] == "completed"


def test_uploaded_pptx_is_extracted_as_immutable_lesson_evidence(tmp_path):
    from pptx import Presentation

    source = tmp_path / "旧课件.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "DeepSeek 4"
    slide.placeholders[1].text = "从模型能力变化到课堂案例"
    presentation.save(source)

    evidence = extract_uploaded_pptx_evidence(source, asset_id="asset-1")

    assert len(evidence) == 1
    assert evidence[0]["evidence_id"] == "uploaded-ppt-asset-1-slide-1"
    assert "DeepSeek 4" in evidence[0]["source_text"]
    assert source.is_file()


def test_repository_keeps_sibling_lesson_assets_independent(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    repository.set_outline("course-1", "outline-v1")
    first = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"sections": [{"node_id": "L2-1-1"}]},
        source_outline_revision_id="outline-v1",
    )
    second = repository.save_plan_revision(
        "course-1",
        "L1-2",
        {"sections": [{"node_id": "L2-2-1"}]},
        source_outline_revision_id="outline-v1",
    )

    assert first["working_revision_id"] != second["working_revision_id"]
    view = repository.view("course-1")
    assert set(view["lessons"]) == {"L1-1", "L1-2"}
    assert len(view["lessons"]["L1-1"]["revisions"]) == 1


def test_valid_fallback_finishes_with_warning_and_remains_editable(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = TeacherLessonAuthoringService(repository)
    job = repository.create_job(
        "course-1",
        "L1-1",
        request_id="request-1",
        source_outline_revision_id="outline-v1",
    )

    async def planner(_course, _lesson_id, on_progress):
        await on_progress("lesson_plan_validation", 70, "正在校验")
        return {
            "plan": {"sections": [{"node_id": "L2-1-1", "teaching_modules": []}]},
            "warnings": [{"code": "model_output_failed_validation"}],
            "generation_source": "deterministic_local_fallback",
            "source_refs": [{"source_kind": "uploaded_ppt", "asset_id": "asset-1", "slide": 1}],
            "source_outline_revision_id": "outline-v1",
        }

    completed = asyncio.run(service.run_plan_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        course_data=course_data(),
        planner=planner,
    ))

    assert completed["status"] == "completed_with_warnings"
    lesson = repository.view("course-1")["lessons"]["L1-1"]
    assert lesson["revisions"][0]["status"] == "needs_ai_review"
    assert lesson["revisions"][0]["plan"]["sections"][0]["node_id"] == "L2-1-1"
    assert lesson["revisions"][0]["source_refs"][0]["asset_id"] == "asset-1"
    assert "模型内容校验未通过" in completed["message"]


def test_plan_job_keeps_formal_outline_and_planner_scope_revisions_separate(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    repository.set_outline("course-1", "outline-v1")
    service = TeacherLessonAuthoringService(repository)
    job = repository.create_job(
        "course-1",
        "L1-2",
        request_id="request-scope-revision",
        source_outline_revision_id="outline-v1",
    )
    plan = standard_lesson_plan()
    plan["sections"][0]["node_id"] = "L2-2-1"

    async def planner(_course, _lesson_id, _on_progress):
        return {
            "plan": plan,
            "warnings": [],
            "generation_source": "model",
            "source_outline_revision_id": "knowledge-scope-v2",
        }

    completed = asyncio.run(service.run_plan_job(
        course_id="course-1",
        lesson_unit_id="L1-2",
        job_id=job["id"],
        course_data=course_data(),
        planner=planner,
    ))

    assert completed["status"] == "completed"
    revision = repository.lesson("course-1", "L1-2")["revisions"][0]
    assert revision["source_outline_revision_id"] == "outline-v1"
    assert revision["source_knowledge_scope_revision_id"] == "knowledge-scope-v2"
    assert revision["quality_report"]["passed"] is True


def test_failed_plan_job_keeps_streamed_working_copy(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = TeacherLessonAuthoringService(repository)
    job = repository.create_job(
        "course-1",
        "L1-1",
        request_id="request-stream-failure",
        source_outline_revision_id="outline-v1",
    )

    async def planner(_course, _lesson_id, on_progress):
        await asyncio.gather(
            on_progress(
                "course_teaching_plan_batch", 45, "生成第一批", 45,
                {
                    "stream_event": "delta",
                    "stream_batch_id": "TP-B01",
                    "stream_delta": '{"title":"第一批已生成"',
                },
            ),
            on_progress(
                "course_teaching_plan_batch", 45, "生成第二批", 45,
                {
                    "stream_event": "delta",
                    "stream_batch_id": "TP-B02",
                    "stream_delta": '{"title":"第二批已生成"',
                },
            ),
        )
        raise RuntimeError("模型连接中断")

    failed = asyncio.run(service.run_plan_job(
        course_id="course-1",
        lesson_unit_id="L1-1",
        job_id=job["id"],
        course_data=course_data(),
        planner=planner,
    ))

    assert failed["status"] == "failed"
    assert failed["stream_complete"] is True
    assert set(failed["stream_batches"]) == {"TP-B01", "TP-B02"}
    assert "第一批已生成" in failed["stream_batches"]["TP-B01"]
    assert "第二批已生成" in failed["stream_batches"]["TP-B02"]


def test_orphaned_lesson_job_expires_and_keeps_partial_stream(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    job = repository.create_job(
        "course-1",
        "L1-1",
        request_id="request-orphaned",
        source_outline_revision_id="outline-v1",
    )
    repository.update_job_stream(
        "course-1",
        job["id"],
        phase="course_teaching_plan_batch",
        progress=42,
        message="正在生成",
        batch_id="TP-B01",
        event="delta",
        delta='{"learning_objective":"已生成部分目标"',
    )
    path = tmp_path / "course-1.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["jobs"][job["id"]]["updated_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    expired = repository.expire_stale_job("course-1", job["id"])

    assert expired["status"] == "failed"
    assert expired["phase"] == "lesson_plan_interrupted"
    assert expired["error"]["retryable"] is True
    assert "已生成部分目标" in expired["stream_batches"]["TP-B01"]


def test_plan_v3_projection_is_editable_and_never_serializes_module_json():
    section = {
        "node_id": "L2-1-1",
        "key_points": ["二进制转换"],
        "knowledge_structure": [{
            "knowledge_points": [{
                "name": "二进制转换",
                "statement": "完成二进制与十进制之间的相互转换。",
                "boundaries": ["仅处理无符号整数"],
                "capability_points": [{"observable_behavior": "能够独立完成一次进制转换并核对结果。"}],
            }],
        }],
        "teaching_modules": [
            {
                "module_id": "core_explanation",
                "teaching_purpose": "按模板完成「核心讲解」",
                "teaching_guidance": "使用位权展开演示转换过程",
                "knowledge_names": ["二进制转换"],
            },
            {
                "module_id": "learner_action",
                "teaching_guidance": "学生独立完成一道转换题",
                "knowledge_names": ["二进制转换"],
            },
        ],
    }

    view = teacher_lesson_section_content(section)
    assert view["learning_objective"] == "能够独立完成一次进制转换并核对结果。"
    assert "仅处理无符号整数" in view["key_difficulties"]
    assert view["teacher_activities"] == ["核心讲解：围绕二进制转换；使用位权展开演示转换过程"]
    assert view["student_activities"] == ["学习者行动：围绕二进制转换；学生独立完成一道转换题"]

    normalized = normalize_teacher_lesson_plan({"sections": [section]})
    projected = normalized["sections"][0]
    assert projected["learning_objective"] == view["learning_objective"]
    assert projected["teacher_activities"] == view["teacher_activities"]
    assert "{" not in "\n".join(projected["teacher_activities"])


def test_v6_source_rejects_plan_only_fallback_without_confirmed_script():
    source = course_data()
    revision = {
        "revision_id": "fallback-v1",
        "plan": {
            "sections": [{
                "node_id": "L2-1-1",
                "knowledge_structure": [{
                    "knowledge_points": [{
                        "name": "位权展开",
                        "statement": "二进制数可按位权展开并转换为十进制。",
                    }],
                }],
                "teaching_modules": [{
                    "module_id": "core_explanation",
                    "teaching_purpose": "按模板完成「正式定义」",
                    "teaching_guidance": "逐位演示位权展开",
                    "knowledge_names": ["位权展开"],
                }],
            }],
        },
    }
    with pytest.raises(TeacherLessonAuthoringError) as exc_info:
        teacher_lesson_v6_source(
            source,
            lesson_unit_id="L1-1",
            plan_revision=revision,
            script_revision={"revision_id": "", "sections": []},
        )
    assert exc_info.value.code == "lesson_script_source_missing"


def test_request_id_is_idempotent(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    first = repository.create_job("course-1", "L1-1", request_id="same")
    second = repository.create_job("course-1", "L1-1", request_id="same")
    assert first["id"] == second["id"]


def test_teacher_job_contract_preserves_checkpoint_when_cancelled(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    job = repository.create_job(
        "course-1",
        "L1-1",
        job_type="teacher_lesson_script_generation",
        request_id="cancel-me",
    )
    repository.update_job(
        "course-1",
        job["id"],
        status="running",
        completed_blocks=1,
        current_block_id="block-2",
        result_sections=[{
            "section_node_id": "L2-1-1",
            "content": "已完成内容",
        }],
    )

    cancelled = repository.cancel_job("course-1", job["id"])

    assert cancelled["schema_version"] == "teacher_asset_job_v1"
    assert cancelled["asset_type"] == "script"
    assert cancelled["status"] == "cancelled"
    assert cancelled["stream_complete"] is True
    assert cancelled["checkpoint"]["completed_blocks"] == 1
    assert cancelled["checkpoint"]["result_sections"][0]["content"] == "已完成内容"
    assert cancelled["error"]["retryable"] is True


def test_teacher_only_course_is_hidden_from_student_list(monkeypatch):
    courses = [
        {"course_id": "student-course", "is_published": True},
        {
            "course_id": "teacher-course",
            "generation_job_id": "teacher-job",
        },
    ]
    monkeypatch.setattr(courses_router.storage, "list_courses", lambda: courses)
    monkeypatch.setattr(courses_router.learning_snapshot_repository, "load", lambda *_args: None)
    student = courses_router._list_courses_with_resume(
        "learner",
        {"teacher-job"},
        {"teacher-course"},
    )
    teacher = courses_router._list_teacher_courses({"teacher-job"})
    assert [item["course_id"] for item in student] == ["student-course"]
    assert [item["course_id"] for item in teacher] == ["student-course", "teacher-course"]


def test_ai_candidate_acceptance_creates_new_working_revision(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"sections": [{"node_id": "L2-1-1", "learning_objective": "before"}]},
        source_outline_revision_id="outline-v1",
    )
    candidate = repository.save_ai_candidate(
        "course-1",
        "L1-1",
        base_revision_id=lesson["working_revision_id"],
        instruction="优化目标",
        section_node_id="L2-1-1",
        plan={"sections": [{"node_id": "L2-1-1", "learning_objective": "after"}]},
    )
    accepted = repository.resolve_ai_candidate(
        "course-1",
        "L1-1",
        candidate["candidate_id"],
        accept=True,
    )

    assert len(accepted["revisions"]) == 2
    assert accepted["working_revision_id"] != lesson["working_revision_id"]
    assert accepted["revisions"][-1]["plan"]["sections"][0]["learning_objective"] == "after"
    assert accepted["ai_candidates"][0]["status"] == "accepted"


def test_ai_optimizer_uses_compact_editable_contract_and_merges_one_section():
    plan = {
        "schema_version": "course_teaching_plan_v3",
        "sections": [
            {
                "node_id": "L2-1-1",
                "learning_objective": "原目标",
                "key_points": ["进制转换"],
                "key_difficulties": ["原难点"],
                "in_class_checks": ["完成一道转换题"],
                "homework": ["原作业"],
                "teaching_notes": ["原备注"],
                "teaching_modules": [{
                    "module_id": "core_explanation",
                    "teaching_purpose": "讲清位权展开",
                    "planned_minutes": 15,
                    "teacher_activity": "原教师活动",
                    "student_activity": "原学生活动",
                    "knowledge_names": ["进制转换"],
                }],
                "knowledge_structure": [{"knowledge_points": [{"statement": "不可改写的事实"}]}],
            },
            {"node_id": "L2-1-2", "learning_objective": "兄弟小节"},
        ],
    }

    class FakeOptimizer:
        captured_prompt = ""

        async def _call_llm(self, prompt, **_kwargs):
            self.captured_prompt = prompt
            return json.dumps({
                "sections": [{
                    "node_id": "L2-1-1",
                    "learning_objective": "学生能够独立完成一次进制转换并解释步骤。",
                    "key_points": ["进制转换", "位权展开"],
                    "key_difficulties": ["位权展开"],
                    "in_class_checks": ["独立完成一道转换题并说明每一步。"],
                    "homework": ["完成两道相邻进制转换题。"],
                    "teaching_notes": ["先检查位权表，再处理转换步骤。"],
                    "teaching_modules": [{
                        "module_id": "core_explanation",
                        "teaching_purpose": "用演示和练习建立位权展开方法",
                        "planned_minutes": 18,
                        "teacher_activity": "演示十进制转二进制并逐步核对余数。",
                        "student_activity": "独立完成一道转换题并说明每一步。",
                    }],
                }],
            }, ensure_ascii=False)

        @staticmethod
        def _extract_json(value):
            return json.loads(value)

    fake = FakeOptimizer()
    result = asyncio.run(CourseService.optimize_teacher_lesson_plan(
        fake,
        plan=plan,
        instruction="增加可观察目标和课堂练习",
        section_node_id="L2-1-1",
    ))

    optimized = result["plan"]["sections"]
    assert optimized[0]["learning_objective"].startswith("学生能够独立")
    assert optimized[0]["teaching_modules"][0]["teacher_activity"].startswith("演示十进制")
    assert optimized[0]["teacher_activities"] == ["演示十进制转二进制并逐步核对余数。"]
    assert optimized[0]["knowledge_structure"] == plan["sections"][0]["knowledge_structure"]
    assert optimized[1]["node_id"] == plan["sections"][1]["node_id"]
    assert optimized[1]["learning_objective"] == plan["sections"][1]["learning_objective"]
    assert '"schema_version"' not in fake.captured_prompt
    assert '"knowledge_context"' in fake.captured_prompt
    assert "只修改实现要求所必需的字段" in fake.captured_prompt
    assert "保持原有总时长" in fake.captured_prompt


def test_v6_ppt_binds_exact_plan_and_script_revisions_and_becomes_stale(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        standard_lesson_plan(),
        source_outline_revision_id="outline-v1",
    )
    source_revision = lesson["working_revision_id"]
    repository.confirm_plan_revision("course-1", "L1-1", source_revision)
    lesson = repository.save_script_revision(
        "course-1",
        "L1-1",
        [{
            "section_node_id": "L2-1-1",
            "title": "1.1",
            "content": "这是已经确认的讲稿正文。",
        }],
        source_lesson_plan_revision_id=source_revision,
        generation_source="legacy_course_content",
    )
    script_revision = lesson["working_script_revision_id"]
    repository.confirm_script_revision(
        "course-1", "L1-1", script_revision
    )
    asset = repository.bind_v6_ppt_revision(
        "course-1",
        "L1-1",
        source_lesson_plan_revision_id=source_revision,
        source_script_revision_id=script_revision,
        synthetic_course_id="teacher-lesson-1",
        representation_id="rep-1",
        spec_id="spec-1",
        candidate_status="ready",
    )
    assert asset["source_state"] == "current"
    assert asset["v6_revisions"][0]["source_lesson_plan_revision_id"] == source_revision
    assert asset["v6_revisions"][0]["source_script_revision_id"] == script_revision

    repository.save_plan_revision(
        "course-1",
        "L1-1",
        {"lesson_title": "第一讲 v2", "sections": [{"node_id": "L2-1-1", "title": "1.1"}]},
        source_outline_revision_id="outline-v1",
        actor="teacher",
    )
    stale = repository.lesson("course-1", "L1-1")["ppt_assets"][0]
    assert stale["source_state"] == "stale"
    assert stale["v6_revisions"][0]["representation_id"] == "rep-1"


def test_teacher_lesson_v6_source_is_synthetic_and_covers_only_one_lesson():
    source = course_data()
    source["nodes"][1]["node_content"] = "这是一段已确认的一手讲稿正文。"
    source["nodes"][2]["node_content"] = "这是第二小节已确认的一手讲稿正文。"
    source_before = str(source)
    revision = {
        "revision_id": "plan-v1",
        "plan": {
            "revision_id": "plan-v1",
            "sections": [
                {
                    "node_id": "L2-1-1",
                    "learning_objective": "理解第一节",
                    "key_points": ["概念一"],
                    "teaching_modules": [{
                        "module_id": "core_explanation",
                        "teaching_purpose": "讲清概念一",
                        "knowledge_names": ["概念一"],
                    }],
                },
                {
                    "node_id": "L2-1-2",
                    "learning_objective": "理解第二节",
                    "key_points": ["概念二"],
                    "teaching_modules": [{
                        "module_id": "learner_action",
                        "teaching_purpose": "完成概念二练习",
                        "knowledge_names": ["概念二"],
                    }],
                },
            ],
        },
    }
    document, view, synthetic_id = teacher_lesson_v6_source(
        source,
        lesson_unit_id="L1-1",
        plan_revision=revision,
        script_revision={
            "revision_id": "legacy-script-v1",
            "sections": [
                {
                    "section_node_id": "L2-1-1",
                    "blocks": [{
                        "block_id": "legacy-1",
                        "module_id": "legacy_script",
                        "role": "concept",
                        "title": "讲稿正文",
                        "content": "这是一段已确认的一手讲稿正文。",
                    }],
                },
                {
                    "section_node_id": "L2-1-2",
                    "blocks": [{
                        "block_id": "legacy-2",
                        "module_id": "legacy_script",
                        "role": "concept",
                        "title": "讲稿正文",
                        "content": "这是第二小节已确认的一手讲稿正文。",
                    }],
                },
            ],
        },
    )
    graph = compile_course_presentation_graph(
        document,
        teaching_plan=view["course_teaching_plan"],
    )
    assert synthetic_id.startswith("teacher-lesson-")
    assert synthetic_id != source["course_id"]
    assert {section.section_id for section in document.sections} == {"L1-1", "L2-1-1", "L2-1-2"}
    assert {block.section_id for block in document.blocks} == {"L2-1-1", "L2-1-2"}
    assert graph.primary_block_coverage == 1.0
    assert graph.diagnostics == []
    assert view["teacher_lesson_source"]["script_revision_id"] == "legacy-script-v1"
    assert view["nodes"][1]["content_blocks"][0]["content"] == "这是一段已确认的一手讲稿正文。"
    assert str(source) == source_before


def test_script_confirmation_versions_the_body_and_stales_bound_v6_ppt(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    quality = validate_teacher_lesson_plan(standard_lesson_plan())
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        standard_lesson_plan(),
        source_outline_revision_id="outline-v1",
        quality_report=quality,
    )
    plan_revision = lesson["working_revision_id"]
    repository.confirm_plan_revision("course-1", "L1-1", plan_revision)

    source = course_data()
    source["nodes"][1]["node_content"] = "第一节正式讲稿"
    source["nodes"][2]["node_content"] = "第二节正式讲稿"
    first_script_revision = teacher_lesson_script_revision(source, "L1-1")
    repository.save_script_revision(
        "course-1",
        "L1-1",
        [
            {"section_node_id": "L2-1-1", "title": "1.1", "content": "第一节正式讲稿"},
            {"section_node_id": "L2-1-2", "title": "1.2", "content": "第二节正式讲稿"},
        ],
        source_lesson_plan_revision_id=plan_revision,
    )
    repository.confirm_script_revision("course-1", "L1-1", first_script_revision)
    asset = repository.bind_v6_ppt_revision(
        "course-1",
        "L1-1",
        source_lesson_plan_revision_id=plan_revision,
        source_script_revision_id=first_script_revision,
        synthetic_course_id="teacher-lesson-1",
        representation_id="representation-1",
        spec_id="spec-1",
        candidate_status="v6_ready",
    )
    assert asset["source_state"] == "current"
    assert asset["source_script_revision_id"] == first_script_revision

    source["nodes"][1]["node_content"] = "第一节修改后的正式讲稿"
    second_script_revision = teacher_lesson_script_revision(source, "L1-1")
    assert second_script_revision != first_script_revision
    repository.save_script_revision(
        "course-1",
        "L1-1",
        [
            {"section_node_id": "L2-1-1", "title": "1.1", "content": "第一节修改后的正式讲稿"},
            {"section_node_id": "L2-1-2", "title": "1.2", "content": "第二节正式讲稿"},
        ],
        source_lesson_plan_revision_id=plan_revision,
        generation_source="teacher_edit",
    )
    repository.confirm_script_revision("course-1", "L1-1", second_script_revision)
    stale = repository.lesson("course-1", "L1-1")["ppt_assets"][0]
    assert stale["source_state"] == "stale"


def test_script_confirmation_is_required_by_the_only_v6_ppt_api(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = course_data()
    source["blueprint_revision_id"] = "outline-v1"
    source["nodes"][1]["node_content"] = "第一节正式讲稿"
    source["nodes"][2]["node_content"] = "第二节正式讲稿"
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        standard_lesson_plan(),
        source_outline_revision_id="outline-v1",
        quality_report=validate_teacher_lesson_plan(standard_lesson_plan()),
    )
    repository.confirm_plan_revision(
        "course-1",
        "L1-1",
        lesson["working_revision_id"],
    )

    class FakeStorage:
        @staticmethod
        def load_course(course_id):
            assert course_id == "course-1"
            return source

    class FakeTaskManager:
        storage = FakeStorage()

        @staticmethod
        def get_generation_workspace_course(_course_id):
            return None

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository
    script_revision = teacher_lesson_script_revision(source, "L1-1")

    with TestClient(app) as client:
        blocked = client.get("/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/source")
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "lesson_script_not_confirmed"

        confirmed = client.post(
            "/api/teacher/courses/course-1/lessons/L1-1/script/confirm",
            json={"revision_id": script_revision},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["lesson"]["script"]["confirmed"] is True

        source_response = client.get(
            "/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/source"
        )
        assert source_response.status_code == 200
        assert source_response.json()["document"]["document_revision"]

        legacy_generation = client.post(
            "/api/teacher/courses/course-1/lessons/L1-1/ppt/generate",
            json={"source_revision_id": lesson["working_revision_id"]},
        )
        assert legacy_generation.status_code == 404


def test_script_generation_edit_candidate_and_confirmation_share_one_asset_chain(tmp_path, monkeypatch):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = {**course_data(), "blueprint_revision_id": "outline-v1"}
    for section in (source["nodes"][1], source["nodes"][2]):
        section["module_plan"] = [{
            "module_id": "core_explanation",
            "label": "核心教学",
            "block_role": "concept",
            "required": True,
            "lesson_archetype_id": "general_concept_building",
            "lesson_archetype_label": "概念建构",
        }]
    lesson_plan = standard_lesson_plan()
    second_section = json.loads(json.dumps(lesson_plan["sections"][0]))
    second_section["node_id"] = "L2-1-2"
    lesson_plan["sections"].append(second_section)
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        lesson_plan,
        source_outline_revision_id="outline-v1",
        quality_report=validate_teacher_lesson_plan(
            lesson_plan,
            expected_section_ids=["L2-1-1", "L2-1-2"],
        ),
    )
    plan_revision = lesson["working_revision_id"]
    repository.confirm_plan_revision("course-1", "L1-1", plan_revision)

    class FakeCourseService:
        registered = False
        script_calls = []
        rewrite_calls = []

        @classmethod
        def register_course_generation_metadata(cls, course_id, course):
            assert course_id == "course-1"
            assert course["nodes"]
            cls.registered = True

        @staticmethod
        async def generate_teacher_script_section(**kwargs):
            FakeCourseService.script_calls.append(kwargs)
            contract = compile_teacher_script_module_contract(
                kwargs["outline_section"], kwargs["confirmed_plan_section"]
            )
            return compile_teacher_script_section(
                "## 核心教学\n\n这是一段严格遵循已确认教案、可直接用于课堂讲授的正式讲稿。",
                contract,
            )

        @staticmethod
        async def rewrite_selection(**kwargs):
            FakeCourseService.rewrite_calls.append(kwargs)
            assert "增加一个真实案例" in kwargs["user_requirement"]
            return {"replacement_text": "## 核心教学\n\nAI 候选讲稿，已增加真实案例并保持原教学模块。"}

    class FakeStorage:
        @staticmethod
        def load_course(course_id):
            assert course_id == "course-1"
            return source

    class FakeTaskManager:
        storage = FakeStorage()
        course_service = FakeCourseService()

        @staticmethod
        def get_generation_workspace_course(_course_id):
            return None

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository
    monkeypatch.setattr(
        teacher_lesson_router,
        "_course_material_evidence",
        lambda _course_id, _actor, material_ids: (
            material_ids,
            [{"asset_id": "material-1", "unit_id": "evidence-1", "text": "资料中的可靠案例"}],
        ),
    )

    with TestClient(app) as client:
        generated = client.post(
            "/api/teacher/courses/course-1/lessons/L1-1/script/generate",
            json={
                "request_id": "script-first",
                "requirements": "增加案例",
                "material_asset_ids": ["material-1"],
            },
            headers={"X-User-Id": "teacher-1"},
        )
        assert generated.status_code == 202
        job_id = generated.json()["job"]["id"]
        for _ in range(100):
            job = client.get(
                f"/api/teacher/courses/course-1/lesson-jobs/{job_id}"
            ).json()["job"]
            if job["status"] in {"completed", "completed_with_warnings", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed"
        assert job["completed_blocks"] == job["total_blocks"] == 2
        view = client.get(
            "/api/teacher/courses/course-1/lesson-authoring"
        ).json()
        first_script = next(
            item for item in view["lessons"]
            if item["lesson_unit_id"] == "L1-1"
        )["script"]
        assert first_script["ready"] is True
        assert len(first_script["sections"]) == 2
        first_revision = first_script["current_revision_id"]

        candidate = client.post(
            "/api/teacher/courses/course-1/lessons/L1-1/script/rewrite-candidate",
            json={
                "base_revision_id": first_revision,
                "section_node_id": "L2-1-1",
                "instruction": "增加一个真实案例",
            },
            headers={"X-User-Id": "teacher-1"},
        )
        assert candidate.status_code == 200
        assert repository.lesson("course-1", "L1-1")["working_script_revision_id"] == first_revision

        edited_sections = first_script["sections"]
        edited_sections[0]["content"] = candidate.json()["candidate"]["replacement_text"]
        edited_sections[0].pop("blocks", None)
        saved = client.put(
            "/api/teacher/courses/course-1/lessons/L1-1/script/draft",
            json={"base_revision_id": first_revision, "sections": edited_sections},
            headers={"X-User-Id": "teacher-1"},
        )
        assert saved.status_code == 200
        second_revision = saved.json()["lesson"]["script"]["current_revision_id"]
        assert second_revision != first_revision
        stored_second_revision = next(
            item for item in repository.lesson("course-1", "L1-1")["script_revisions"]
            if item["revision_id"] == second_revision
        )
        assert stored_second_revision["requirements"] == "增加案例"
        assert stored_second_revision["material_asset_ids"] == ["material-1"]

        confirmed = client.post(
            "/api/teacher/courses/course-1/lessons/L1-1/script/confirm",
            json={"revision_id": second_revision},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["lesson"]["script"]["confirmed"] is True

        ppt_source = client.get(
            "/api/teacher/courses/course-1/lessons/L1-1/ppt-v6/source"
        )
        assert ppt_source.status_code == 200
        payload = json.dumps(ppt_source.json(), ensure_ascii=False)
        assert "AI 候选讲稿" in payload

    assert FakeCourseService.registered is True
    assert len(FakeCourseService.script_calls) == 2
    assert all(call["requirements"] == "增加案例" for call in FakeCourseService.script_calls)
    generation_context = FakeCourseService.script_calls[0]["lesson_context"]
    assert generation_context["selected_material_evidence"][0]["text"] == "资料中的可靠案例"
    rewrite_context = json.loads(FakeCourseService.rewrite_calls[0]["course_context"])
    assert rewrite_context["confirmed_lesson_plan"]["node_id"] == "L2-1-1"
    assert rewrite_context["teacher_requirements"] == "增加案例"


def test_teacher_can_save_first_script_draft_without_model_revision(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = {**course_data(), "blueprint_revision_id": "outline-v1"}
    lesson_plan = standard_lesson_plan()
    second_section = json.loads(json.dumps(lesson_plan["sections"][0]))
    second_section["node_id"] = "L2-1-2"
    lesson_plan["sections"].append(second_section)
    for section in (source["nodes"][1], source["nodes"][2]):
        section["module_plan"] = [{
            "module_id": "core_explanation",
            "label": "核心教学",
            "block_role": "concept",
            "required": True,
        }]
    lesson = repository.save_plan_revision(
        "course-1",
        "L1-1",
        lesson_plan,
        source_outline_revision_id="outline-v1",
        quality_report=validate_teacher_lesson_plan(
            lesson_plan,
            expected_section_ids=["L2-1-1", "L2-1-2"],
        ),
    )
    repository.confirm_plan_revision(
        "course-1", "L1-1", lesson["working_revision_id"]
    )

    class FakeStorage:
        @staticmethod
        def load_course(_course_id):
            return source

    class FakeTaskManager:
        storage = FakeStorage()

        @staticmethod
        def get_generation_workspace_course(_course_id):
            return None

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    sections = []
    for outline_section, plan_section in zip(
        (source["nodes"][1], source["nodes"][2]),
        lesson_plan["sections"],
    ):
        contract = compile_teacher_script_module_contract(
            outline_section, plan_section
        )
        sections.append(compile_teacher_script_section(
            "## 核心教学\n\n教师手工补全的可编辑讲稿，包含概念、例子与核对结论。",
            contract,
        ))

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository
    with TestClient(app) as client:
        saved = client.put(
            "/api/teacher/courses/course-1/lessons/L1-1/script/draft",
            json={"base_revision_id": "", "sections": sections},
            headers={"X-User-Id": "teacher-1"},
        )

    assert saved.status_code == 200
    stored = repository.lesson("course-1", "L1-1")
    assert stored["working_script_revision_id"]
    assert stored["script_revisions"][-1]["generation_source"] == "teacher_edit"


def test_teacher_v6_visual_planner_keeps_base_ppt_available_without_ai():
    result = asyncio.run(teacher_lesson_router._teacher_v6_visual_planner({
        "pages": [
            {
                "page_id": "page-prose",
                "template_layout_id": "layout-content",
                "source_block_ids": ["block-1"],
                "allowed_decisions": ["diagram", "text_native"],
                "layout_requires_artifact": False,
            },
            {
                "page_id": "page-table",
                "template_layout_id": "layout-table",
                "source_block_ids": ["block-2"],
                "allowed_decisions": ["data", "table"],
                "layout_requires_artifact": True,
            },
            {
                "page_id": "page-diagram",
                "template_layout_id": "layout-diagram",
                "source_block_ids": ["block-3"],
                "source_blocks": [{
                    "block_id": "block-3",
                    "source_text": "观察现象。建立模型。验证结论。",
                }],
                "allowed_decisions": ["diagram"],
                "layout_requires_artifact": True,
            },
        ],
    }))

    assert result["model"] == "source-native-deterministic"
    assert [item["decision"] for item in result["decisions"]] == [
        "text_native", "table", "diagram",
    ]
    assert result["decisions"][1]["source_block_ids"] == ["block-2"]
    diagram = result["decisions"][2]["visual_payload"]
    assert len(diagram["nodes"]) == 3
    assert len(diagram["edges"]) == 2


def test_legacy_lightweight_ppt_write_chain_is_retired(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    service = CourseService()
    assert not hasattr(repository, "save_ppt_revision")
    assert not hasattr(repository, "save_ppt_ai_candidate")
    assert not hasattr(repository, "resolve_ppt_ai_candidate")
    assert not hasattr(service, "generate_teacher_lesson_ppt")
    assert not hasattr(service, "optimize_teacher_lesson_ppt")


def test_teacher_lesson_api_projects_sessions_from_canonical_course_document(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = {**course_data(), "course_name": "数据结构"}
    document = document_from_generation_draft(source)
    canonical = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_schema_version": "course_document_v1",
        "blueprint_revision_id": "outline-v2",
        "course_document": document.model_dump(mode="json"),
    }

    class FakeStorage:
        @staticmethod
        def load_course(course_id):
            assert course_id == "course-1"
            return canonical

    class FakeTaskManager:
        storage = FakeStorage()

        @staticmethod
        def get_generation_workspace_course(_course_id):
            return None

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository

    with TestClient(app) as client:
        view = client.get("/api/teacher/courses/course-1/lesson-authoring")

    assert view.status_code == 200
    assert view.json()["outline_revision_id"] == "outline-v2"
    assert [item["lesson_unit_id"] for item in view.json()["lessons"]] == ["L1-1", "L1-2"]
    assert [item["section_node_id"] for item in view.json()["lessons"][0]["sections"]] == ["L2-1-1", "L2-1-2"]


def test_teacher_lesson_view_expires_orphaned_jobs_before_frontend_recovery(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    job = repository.create_job(
        "course-1",
        "L1-1",
        request_id="request-orphaned-view",
        source_outline_revision_id="outline-v1",
        job_type="teacher_lesson_script_generation",
    )
    stored_path = tmp_path / "course-1.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["jobs"][job["id"]]["status"] = "running"
    stored["jobs"][job["id"]]["updated_at"] = "2020-01-01T00:00:00+00:00"
    stored_path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    class FakeStorage:
        @staticmethod
        def load_course(_course_id):
            return course_data()

    class FakeTaskManager:
        storage = FakeStorage()

        @staticmethod
        def get_generation_workspace_course(_course_id):
            return None

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository

    with TestClient(app) as client:
        response = client.get("/api/teacher/courses/course-1/lesson-authoring")

    returned = next(item for item in response.json()["jobs"] if item["id"] == job["id"])
    assert returned["status"] == "failed"
    assert returned["error"]["code"] == "lesson_script_generation_interrupted"


def test_teacher_lesson_api_ignores_empty_persisted_shell_and_uses_workspace(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    empty_shell = {
        "course_id": "course-1",
        "nodes": [],
        "course_document": {
            "schema_version": "course_document_v1",
            "sections": [],
            "blocks": [],
        },
    }
    workspace = {**course_data(), "blueprint_revision_id": "outline-workspace-v1"}

    class FakeStorage:
        @staticmethod
        def load_course(course_id):
            assert course_id == "course-1"
            return empty_shell

    class FakeTaskManager:
        storage = FakeStorage()

        @staticmethod
        def get_generation_workspace_course(course_id):
            assert course_id == "course-1"
            return workspace

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository

    with TestClient(app) as client:
        view = client.get("/api/teacher/courses/course-1/lesson-authoring")

    assert view.status_code == 200
    assert view.json()["outline_revision_id"] == "outline-workspace-v1"
    assert [item["lesson_unit_id"] for item in view.json()["lessons"]] == ["L1-1", "L1-2"]


def test_teacher_lesson_api_generates_only_requested_lesson(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)

    class FakeCourseService:
        calls = []

        async def prepare_teacher_lesson_plan(
            self,
            *,
            course_data,
            lesson_unit_id,
            on_phase,
            source_evidence=None,
            lesson_arrangement=None,
            resume_checkpoint=None,
            on_checkpoint=None,
        ):
            self.calls.append(lesson_unit_id)
            assert source_evidence == []
            assert resume_checkpoint == {}
            assert callable(on_checkpoint)
            assert lesson_arrangement["lesson_type"] == "theory"
            assert lesson_arrangement["status"] == "confirmed"
            assert {item["section_node_id"] for item in lesson_arrangement["blocks"]} == {"L2-2-1"}
            assert course_data["requirements"] == "突出课堂讨论与案例分析"
            selected = next(
                item
                for item in course_data["course_plan"]["chapters"]
                if item["node_id"] == lesson_unit_id
            )
            assert selected["teacher_requirements"] == "突出课堂讨论与案例分析"
            await on_phase(
                "course_teaching_plan_batch", 60, "生成中", 60,
                {"stream_event": "reset", "stream_batch_id": "TP-B01", "stream_delta": ""},
            )
            await on_phase(
                "course_teaching_plan_batch", 60, "生成中", 60,
                {
                    "stream_event": "delta",
                    "stream_batch_id": "TP-B01",
                    "stream_delta": '{"sections":[{"learning_objective":"正在生成',
                },
            )
            await on_phase(
                "course_teaching_plan_batch", 60, "生成中", 60,
                {
                    "stream_event": "delta",
                    "stream_batch_id": "TP-B01",
                    "stream_delta": '专业教学目标"}]}',
                },
            )
            scope = lesson_scope(course_data, lesson_unit_id)
            return {
                "plan": {
                    "sections": [
                        {"node_id": item["node_id"], "teaching_modules": []}
                        for item in scope["sections"]
                    ]
                },
                "warnings": [],
                "source_outline_revision_id": "outline-v1",
                "generation_source": "model",
            }

    class FakeTaskManager:
        storage = None
        course_service = FakeCourseService()

        @staticmethod
        def get_generation_workspace_course(course_id):
            assert course_id == "course-1"
            return {**course_data(), "blueprint_revision_id": "outline-v1"}

        @staticmethod
        def get_generation_preview(_course_id):
            return None

    app = FastAPI()
    app.include_router(teacher_lesson_router.router, prefix="/api")
    app.dependency_overrides[require_task_manager] = lambda: FakeTaskManager()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository

    with TestClient(app) as client:
        view = client.get("/api/teacher/courses/course-1/lesson-authoring")
        assert view.status_code == 200
        assert [item["lesson_unit_id"] for item in view.json()["lessons"]] == ["L1-1", "L1-2"]

        blocked = client.post(
            "/api/teacher/courses/course-1/lessons/L1-2/plan/generate",
            json={"request_id": "before-arrangement"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "lesson_arrangement_not_confirmed"

        lesson_two = next(
            item for item in view.json()["lessons"]
            if item["lesson_unit_id"] == "L1-2"
        )
        arrangement_response = client.put(
            "/api/teacher/courses/course-1/lessons/L1-2/arrangement/confirm",
            json={
                "lesson_type": lesson_two["arrangement"]["lesson_type"],
                "blocks": lesson_two["arrangement"]["blocks"],
            },
        )
        assert arrangement_response.status_code == 200
        assert arrangement_response.json()["lesson"]["arrangement"]["confirmed"] is True

        response = client.post(
            "/api/teacher/courses/course-1/lessons/L1-2/plan/generate",
            json={
                "request_id": "lesson-two",
                "requirements": "突出课堂讨论与案例分析",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job"]["id"]
        for _ in range(50):
            job = client.get(f"/api/teacher/courses/course-1/lesson-jobs/{job_id}").json()["job"]
            if job["status"] in {"completed", "completed_with_warnings", "failed"}:
                break
            time.sleep(0.01)
        with client.stream(
            "GET",
            f"/api/teacher/courses/course-1/lesson-jobs/{job_id}/stream",
        ) as stream_response:
            stream_payload = "".join(stream_response.iter_text())

    assert job["status"] == "completed_with_warnings"
    assert job["stream_complete"] is True
    assert job["stream_batches"]["TP-B01"] == (
        '{"sections":[{"learning_objective":"正在生成专业教学目标"}]}'
    )
    assert "lesson_plan_complete" in stream_payload
    assert "正在生成专业教学目标" in stream_payload
    assert FakeTaskManager.course_service.calls == ["L1-2"]
    assets = repository.view("course-1")["lessons"]
    assert set(assets) == {"L1-2"}
    generated_section = assets["L1-2"]["revisions"][0]["plan"]["sections"][0]
    assert generated_section["node_id"] == "L2-2-1"
    assert generated_section["teaching_modules"] == []
    assert generated_section["teacher_activities"] == []
    generated_revision = assets["L1-2"]["revisions"][0]
    assert generated_revision["status"] == "needs_ai_review"
    assert generated_revision["quality_report"]["passed"] is False
