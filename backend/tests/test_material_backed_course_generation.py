import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_base import AIProviderRequestError
from course_generation_workflow import (
    attach_generation_artifacts_to_plan,
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    build_node_generation_context,
    normalize_course_plan_contract,
    validate_course_plan_constraints,
)
from course_pedagogy import (
    PedagogyMode,
    attach_module_plans_to_plan,
    resolve_pedagogy_profile,
)
from course_service import CourseService


def _knowledge_structure(label):
    premise = f"{label}的成立条件"
    application = f"{label}的应用判断"
    return [{
        "concept_group": f"{label}的核心机制",
        "description": f"从成立条件走向{label}的独立应用",
        "knowledge_points": [{
            "name": premise,
            "statement": f"使用{label}前必须先识别对象并核对全部成立条件。",
            "knowledge_type": "rule",
            "conditions": [f"已经明确{label}所处理的对象"],
            "boundaries": [f"任一条件不成立时不能直接使用{label}"],
            "capability_points": [{
                "name": f"核对{label}条件",
                "observable_behavior": f"给定案例，逐项判断{label}的成立条件是否满足",
            }],
            "misconceptions": [{
                "name": f"跳过{label}条件检查",
                "observable_error_pattern": f"没有核对条件就直接套用{label}",
                "discrimination": f"把{label}的对象、条件和结论分别列出",
                "repair_strategy": f"补做{label}条件清单后重新推理",
            }],
            "mastery_criteria": [{
                "name": f"{label}条件判断达标",
                "observable_performance": f"独立判断新案例是否满足{label}的成立条件",
                "verification_method": "完成正例、反例与边界例的分类",
            }],
            "entry_reason": f"{premise}是本节的学习入口。",
            "relations": [{
                "target_name": application,
                "relation_type": "prerequisite",
                "reason": f"只有先核对{label}的成立条件，才能进行应用判断",
            }],
        }, {
            "name": application,
            "statement": f"满足条件后，应选择{label}完成任务并检查结果是否落在适用边界内。",
            "knowledge_type": "procedure",
            "conditions": [f"{label}的全部成立条件已经满足"],
            "boundaries": [f"结果超出{label}适用范围时需要更换方法"],
            "capability_points": [{
                "name": f"应用{label}",
                "observable_behavior": f"在新情境中独立应用{label}并检查结果",
            }],
            "mastery_criteria": [{
                "name": f"{label}应用达标",
                "observable_performance": f"独立完成一个{label}迁移任务并说明检查过程",
                "verification_method": "提交完整过程并使用边界案例复核",
            }],
        }],
    }]


def test_generation_artifacts_keep_legacy_material_as_unverified_metadata():
    artifacts = build_course_generation_artifacts(
        course_id="course-1",
        topic="微积分",
        difficulty="intermediate",
        style="academic",
        requirements="覆盖完整，少废话，讲清底层原理。参考李老师教材，但我还没上传。",
        target_audience="大学生",
        materials=[{
            "filename": "第03讲 导数与微分.md",
            "usage": "content_source",
            "importance": "core",
            "user_description": "老师本学期课件，作为正文依据。",
            "content": "# 导数与微分\n\n定义：导数刻画瞬时变化率。\n\n例题：根据定义求导。\n",
        }],
    )

    assert artifacts["pipeline_version"] == "course_generation_v4"
    assert artifacts["course_generation_brief"]["course_shape_constraints"] == {}
    assert artifacts["material_cards"][0]["usage"] == "content_source"
    assert artifacts["material_cards"][0]["parse_status"] == "metadata_only"
    assert "content" not in artifacts["material_cards"][0]
    assert "material_digests" not in artifacts
    assert "李老师教材" in "".join(
        artifacts["course_generation_brief"]["unprovided_references"]
    )


def test_legacy_material_metadata_no_longer_broadcasts_material_refs():
    artifacts = build_course_generation_artifacts(
        course_id="course-question",
        topic="微积分",
        difficulty="intermediate",
        style="academic",
        requirements="根据老师真题设计练习。",
        target_audience="大学生",
        materials=[
            {
                "filename": "老师课件.md",
                "usage": "content_source",
                "importance": "core",
                "user_description": "正文依据。",
                "content": "# 导数定义\n导数是瞬时变化率。",
            },
            {
                "filename": "期末真题.md",
                "usage": "question_source",
                "importance": "core",
                "user_description": "用于例题和练习。",
                "content": "题目：根据定义求 f(x)=x^2 在 x=1 的导数？",
            },
        ],
    )
    profile = resolve_pedagogy_profile(
        subject="微积分",
        requirements="根据老师真题设计练习",
    )
    plan = attach_generation_artifacts_to_plan({
        "course_title": "微积分",
        "chapters": [{
            "chapter_number": 1,
            "title": "导数",
            "sections": [{
                "section_number": "1.1",
                "title": "导数定义",
                "learning_objective": "能用定义求导",
                "assessment": ["完成一道定义求导题"],
            }],
        }],
    }, artifacts)
    plan = attach_module_plans_to_plan(plan, profile)
    blueprint = build_course_blueprint_from_plan(plan, artifacts)
    course_data = {**artifacts, "course_blueprint": blueprint}
    node = blueprint["nodes"][0]

    assert profile.primary_mode == PedagogyMode.MATH_FORMAL
    assert "material_refs" not in node
    assert node["evidence_refs"] == []
    assert any(item["module_id"] == "math_worked_example" for item in node["module_plan"])
    context = build_node_generation_context(course_metadata=course_data, node=node)
    assert "资料增强生成上下文" in context
    assert "不得伪装引用资料" in context
    assert "当前节点模块要求" in context


def test_plan_normalizer_converts_model_dependency_aliases_to_canonical_ids():
    plan = {
        "chapters": [
            {
                "chapter_number": "chapter-one",
                "title": "基础",
                "sections": [
                    {"id": "L1-1", "section_number": "A", "title": "第一节"},
                    {
                        "id": "L1-2",
                        "section_number": "B",
                        "title": "第二节",
                        "prerequisite_node_ids": ["L1-1", "unknown"],
                    },
                ],
            },
        ],
    }

    normalized = normalize_course_plan_contract(plan)
    first, second = normalized["chapters"][0]["sections"]

    assert first["section_number"] == "1.1"
    assert second["section_number"] == "1.2"
    assert second["prerequisite_node_ids"] == ["L2-1-1"]
    assert first["learning_objective"]
    assert first["assessment"]


def test_generation_route_creates_one_persisted_job():
    from routers import courses

    class FakeTaskManager:
        def __init__(self):
            self.request_snapshot = None

        async def create_generation_job(self, request_snapshot):
            self.request_snapshot = request_snapshot
            return {
                "job_id": "job-1",
                "task_id": "job-1",
                "course_id": "course-1",
                "course_name": request_snapshot["subject"],
                "status": "pending",
                "phase": "queued",
            }

    fake_manager = FakeTaskManager()
    app = FastAPI()
    app.include_router(courses.router, prefix="/api")
    app.dependency_overrides[courses.require_task_manager] = lambda: fake_manager
    client = TestClient(app)

    response = client.post("/api/course-generation/generate", json={
        "subject": "微积分",
        "difficulty": "intermediate",
        "style": "academic",
        "requirements": "少废话，适合自学",
        "pedagogy_mode": "math_formal",
        "current_readiness": "beginner",
    })

    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == data["task_id"] == "job-1"
    assert data["course_id"] == "course-1"
    assert fake_manager.request_snapshot["pedagogy_mode"] == "math_formal"
    assert fake_manager.request_snapshot["current_readiness"] == "beginner"
    assert fake_manager.request_snapshot["adaptation_preference"] == "preserve_target_extend"

    old_response = client.post("/api/generate_course", json={"keyword": "微积分"})
    assert old_response.status_code == 404


@pytest.mark.asyncio
async def test_course_service_builds_v4_blueprint_without_legacy_quality_report(monkeypatch, tmp_path):
    from material_storage import MaterialRepository

    service = CourseService(materials=MaterialRepository(tmp_path / "materials"))

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        if "判断课程教学结构" in prompt:
            return json.dumps({
                "primary_mode": "math_formal",
                "secondary_mode": None,
                "evidence": ["微积分", "定义"],
                "rationale": "需要形式推理",
            }, ensure_ascii=False)
        return json.dumps({
            "course_title": "微积分电子课程资料",
            "learning_objectives": ["理解极限与导数"],
            "prerequisites": ["函数基础"],
            "chapters": [{
                "chapter_number": 1,
                "title": "导数基础",
                "learning_focus": "从变化率理解导数",
                "sections": [{
                    "section_number": "1.1",
                    "title": "导数的定义",
                    "key_points": ["差商极限", "瞬时变化率"],
                    "knowledge_structure": _knowledge_structure("导数定义"),
                    "complexity": "medium",
                    "learning_objective": "能用定义解释导数",
                    "prerequisite_node_ids": [],
                    "misconceptions": ["连续不一定可导"],
                    "assessment": ["能判断分段函数可导性"],
                    "scope_boundary": "不展开高阶导数",
                }],
            }],
        }, ensure_ascii=False)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)

    data = await service.build_course_draft(
        course_id="course-v2",
        topic="微积分",
        depth="intermediate",
        style="academic",
        requirements="少废话，适合自学，讲清数学底层逻辑。",
        materials=[{
            "filename": "期末真题.md",
            "usage": "question_source",
            "importance": "core",
            "user_description": "真题用于例题和练习。",
            "content": "题目：根据导数定义求 f(x)=x^2 在 x=1 的导数？",
        }],
    )

    assert data["generation_pipeline_version"] == "course_generation_v4"
    assert data["generation_schema_version"] == "course_generation_v4"
    assert data["generation_quality_report"] is None
    assert data["subject_pedagogy_profile"]["primary_mode"] == "math_formal"
    assert data["difficulty_profile"]["target_level"] == "intermediate"
    assert data["difficulty_gap_assessment"]["readiness_status"] == "unknown"
    assert data["adaptation_decision"]["strategy"] == "diagnostic_required"
    assert data["course_difficulty_curve"]["shape"] == "sawtooth"
    assert data["blueprint_validation_report"]["stage"] == "blueprint"
    assert data["blueprint_validation_report"]["difficulty_check"]["passed"] is True
    assert data["evidence_index"]
    assert "evidence_catalog" not in data
    assert all("source_text" not in item for item in data["evidence_index"])
    assert service._course_generation_artifacts["course-v2"]["evidence_catalog"][0]["source_text"]

    restored_service = CourseService(materials=service._material_repository)
    restored_service.register_course_generation_metadata("course-v2", data)
    restored_catalog = restored_service._course_generation_artifacts["course-v2"]["evidence_catalog"]
    assert restored_catalog[0]["source_text"]

    l2_node = next(node for node in data["nodes"] if node["node_level"] == 2)
    assert l2_node["evidence_refs"]
    assert l2_node["grounding_contract"]["required_evidence_ids"]
    assert l2_node["module_plan"]
    assert l2_node["difficulty_contract"]["target_level"] == "intermediate"
    assert "complexity" not in l2_node


@pytest.mark.asyncio
async def test_course_service_resumes_from_persisted_pedagogy_checkpoint(monkeypatch, tmp_path):
    from material_storage import MaterialRepository

    service = CourseService(materials=MaterialRepository(tmp_path / "materials"))
    calls = []

    async def fake_call_llm(prompt, _system_prompt, **_kwargs):
        calls.append(prompt)
        return json.dumps({
            "course_title": "Python 工程实战",
            "learning_objectives": ["完成可运行项目"],
            "prerequisites": [],
            "chapters": [{
                "chapter_number": 1,
                "title": "最小项目",
                "sections": [{
                    "section_number": "1.1",
                    "title": "启动项目",
                    "knowledge_structure": _knowledge_structure("项目启动"),
                    "learning_objective": "能运行并验证输出",
                    "assessment": ["命令返回预期结果"],
                }],
            }],
        }, ensure_ascii=False)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    profile = resolve_pedagogy_profile(
        subject="Python 工程实战",
        requirements="完成可运行项目",
        requested_mode="programming_engineering",
    )
    existing = {
        "course_id": "course-resume",
        "course_name": "Python 工程实战",
        "generation_pipeline_version": "course_generation_v2",
        "material_cards": [],
        "course_generation_brief": {"subject": "Python 工程实战"},
        "subject_pedagogy_profile": profile.to_dict(),
    }

    data = await service.build_course_draft(
        course_id="course-resume",
        topic="Python 工程实战",
        requirements="完成可运行项目",
        existing_course_data=existing,
    )

    assert len(calls) == 1
    assert calls[0].startswith("为「Python 工程实战」生成课程蓝图")
    assert data["subject_pedagogy_profile"]["primary_mode"] == "programming_engineering"
    assert data["nodes"]


@pytest.mark.asyncio
async def test_invalid_model_json_never_falls_back_to_placeholder_course(monkeypatch, tmp_path):
    service = CourseService()
    monkeypatch.chdir(tmp_path)
    calls = []

    async def invalid_json(*_args, **_kwargs):
        calls.append(_args)
        return "这不是 JSON"

    monkeypatch.setattr(service, "_call_llm", invalid_json)
    with pytest.raises(AIProviderRequestError, match="两次未通过结构验收"):
        await service.build_course_draft(
            course_id="course-invalid-outline",
            topic="全新主题代号",
            materials=[],
            pedagogy_mode="general",
        )

    assert len(calls) == 2
    assert not (tmp_path / "debug_failed_json.txt").exists()


def test_explicit_course_shape_is_compiled_as_a_hard_constraint():
    artifacts = build_course_generation_artifacts(
        course_id="course-shape",
        topic="一元二次方程",
        difficulty="intermediate",
        style="academic",
        requirements="严格生成1章2个递进小节，第一节判别式，第二节建模。",
    )
    brief = artifacts["course_generation_brief"]

    assert brief["course_shape_constraints"] == {
        "chapter_count": 1,
        "section_count": 2,
    }
    invalid = validate_course_plan_constraints({
        "chapters": [
            {"sections": [{}, {}]},
            {"sections": [{}, {}]},
        ],
    }, brief)
    assert invalid["passed"] is False
    assert {item["code"] for item in invalid["issues"]} == {
        "plan:chapter_count_mismatch",
        "plan:section_count_mismatch",
        "plan:missing_knowledge_structure",
    }

    malformed = validate_course_plan_constraints({"chapters": ["不是章节对象"]}, brief)
    assert malformed["passed"] is False
    assert "plan:malformed_chapters" in {
        item["code"] for item in malformed["issues"]
    }

    alternate_wording = build_course_generation_artifacts(
        course_id="course-shape-wording",
        topic="概率论",
        difficulty="advanced",
        style="academic",
        requirements="生成两个章节，共六节；不要把第1节的定义重复到第2节。",
    )
    assert alternate_wording["course_generation_brief"]["course_shape_constraints"] == {
        "chapter_count": 2,
        "section_count": 6,
    }


@pytest.mark.asyncio
async def test_course_service_corrects_outline_once_and_keeps_exact_shape(monkeypatch):
    service = CourseService()
    responses = [
        "这不是 JSON",
        json.dumps({
            "course_title": "一元二次方程",
            "learning_objectives": ["能判断根的情况并完成基础建模"],
            "prerequisites": ["整式运算"],
            "chapters": [{
                "chapter_number": 1,
                "title": "从判别到建模",
                "learning_focus": "先判断解的结构，再把情境转化为方程",
                "sections": [
                    {
                        "node_id": "L2-1-1",
                        "section_number": "1.1",
                        "title": "判别式与根的情况",
                        "knowledge_structure": _knowledge_structure("判别式判断"),
                        "learning_objective": "能使用判别式判断实数根的个数",
                        "prerequisite_node_ids": [],
                        "assessment": ["判断三个方程的根的情况"],
                    },
                    {
                        "node_id": "L2-1-2",
                        "section_number": "1.2",
                        "title": "实际问题建模",
                        "knowledge_structure": _knowledge_structure("面积问题建模"),
                        "learning_objective": "能把面积问题转化为一元二次方程并验根",
                        "prerequisite_node_ids": ["L2-1-1"],
                        "assessment": ["完成一个面积建模任务"],
                    },
                ],
            }],
        }, ensure_ascii=False),
    ]
    prompts = []

    async def fake_call_llm(prompt, _system_prompt, **_kwargs):
        prompts.append(prompt)
        return responses.pop(0)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    data = await service.build_course_draft(
        course_id="course-corrected-outline",
        topic="一元二次方程",
        requirements="严格生成1章2个递进小节，第一节判别式，第二节建模。",
        pedagogy_mode="math_formal",
    )

    assert len(prompts) == 2
    assert prompts[1].startswith("重新生成")
    assert data["course_plan_constraint_report"]["passed"] is True
    assert data["course_plan_constraint_report"]["actual"] == {
        "chapter_count": 1,
        "section_count": 2,
    }
    assert len([node for node in data["nodes"] if node["node_level"] == 1]) == 1
    assert len([node for node in data["nodes"] if node["node_level"] == 2]) == 2
