import asyncio
import json
import re
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_base import AIProviderRequestError, AIProviderUnavailable
from course_generation_adaptive import (
    compile_fallback_teaching_batch,
    compile_fallback_teaching_skeleton,
)
from course_generation_budget import CourseGenerationDeadlineExceeded
from course_generation_workflow import (
    attach_generation_artifacts_to_plan,
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    build_course_knowledge_scope_contract,
    build_node_generation_context,
    build_section_knowledge_skeleton_evidence_hints,
    merge_course_relation_batches,
    normalize_course_knowledge_skeleton,
    normalize_course_outline_contract,
    normalize_course_plan_contract,
    normalize_course_relation_batch,
    normalize_section_knowledge_package,
    repair_course_relation_batch_decisions,
    validate_course_knowledge_skeleton,
    validate_course_outline_constraints,
    validate_course_plan_constraints,
    validate_course_relation_batch,
    validate_section_knowledge_package,
)
from course_pedagogy import (
    PedagogyMode,
    attach_module_plans_to_plan,
    resolve_pedagogy_profile,
)
from course_planning_budget import build_teaching_plan_batches
from course_service import CourseService
from course_teaching_plan_v3 import normalize_teaching_plan_skeleton_v3


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


def _section_knowledge_package(label):
    structure = _knowledge_structure(label)
    points = structure[0]["knowledge_points"]
    for point in points:
        point.pop("relations", None)
    return {
        "knowledge_structure": structure,
        "reused_knowledge_names": [],
        "knowledge_relations": [{
            "source_name": points[0]["name"],
            "target_name": points[1]["name"],
            "relation_type": "prerequisite",
            "reason": f"只有先核对{label}的成立条件，才能进行应用判断",
        }],
    }


def _knowledge_skeleton_response(system_prompt, labels_by_title=None):
    match = re.search(
        r"- 按教学顺序排列的小节：(\[.*?\])\n\n"
        r"## 已完成小节的锁定知识名称",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    sections = json.loads(match.group(1))
    locked_match = re.search(
        r"## 已完成小节的锁定知识名称\n(\{.*?\})\n\n"
        r"## 规划要求",
        system_prompt,
        re.S,
    )
    locked = (
        json.loads(locked_match.group(1))
        if locked_match
        else {}
    )
    labels = labels_by_title or {}
    payload = []
    for section in sections:
        section_id = section["node_id"]
        label = labels.get(section["title"], section["title"])
        owned = locked.get(section_id)
        if not owned:
            owned = [
                point["name"]
                for group in _knowledge_structure(label)
                for point in group["knowledge_points"]
            ]
        payload.append({
            "node_id": section_id,
            "owned_knowledge_names": owned,
            "reused_knowledge_names": [],
        })
    return json.dumps({"sections": payload}, ensure_ascii=False)


def _teaching_plan_response(system_prompt, labels_by_title=None):
    match = re.search(
        r"- 按教学顺序排列的小节与模板：(\[.*?\])\n\n"
        r"## 教案原则",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    sections = json.loads(match.group(1))
    labels = labels_by_title or {}
    planned_sections = []
    for section in sections:
        label = labels.get(section["title"], section["title"])
        package = _section_knowledge_package(label)
        points = [
            point
            for group in package["knowledge_structure"]
            for point in group["knowledge_points"]
        ]
        for index, point in enumerate(points):
            if index == 0:
                point["entry_reason"] = (
                    point.get("entry_reason")
                    or f"{point['name']}是本节的学习入口。"
                )
                point["prerequisite_names"] = []
            else:
                point["entry_reason"] = ""
                point["prerequisite_names"] = [points[index - 1]["name"]]

        knowledge_names = [point["name"] for point in points]
        modules = []
        for module in section.get("allowed_teaching_modules") or []:
            if not module.get("required"):
                continue
            modules.append({
                "module_id": module["module_id"],
                "teaching_purpose": (
                    f"用{module.get('label') or module['module_id']}"
                    f"完成{label}的教学责任"
                ),
                "knowledge_names": knowledge_names,
                "teaching_guidance": (
                    f"围绕{label}先解释成立条件，再安排应用与边界检查。"
                ),
            })
        planned_sections.append({
            "node_id": section["node_id"],
            **package,
            "teaching_modules": modules,
        })
    return json.dumps({"sections": planned_sections}, ensure_ascii=False)


def _teaching_skeleton_v3_response(system_prompt, labels_by_title=None):
    match = re.search(
        r"## 已去重的规划上下文\n(\{.*?\})\n\n"
        r"(?:## 分片边界\n.*?\n\n)?## 约束",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    context = json.loads(match.group(1))
    labels = labels_by_title or {}
    module_sets = context.get("module_sets") or {}
    registry = []
    identities = []
    key_index = 1
    for section in context["sections"]:
        label = labels.get(section["title"], section["title"])
        points = [
            point
            for group in _knowledge_structure(label)
            for point in group["knowledge_points"]
        ]
        owned_keys = []
        previous_key = ""
        for point in points:
            key = f"K{key_index:03d}"
            key_index += 1
            owned_keys.append(key)
            registry.append({
                "knowledge_key": key,
                "name": point["name"],
                "statement": point["statement"],
                "owner_node_id": section["node_id"],
                "reused_in_node_ids": [],
                "prerequisite_keys": [previous_key] if previous_key else [],
                "module_ids": list(
                    section.get("allowed_module_ids")
                    or module_sets.get(section.get("module_set_id"))
                    or []
                )[:1],
            })
            previous_key = key
        identities.append({
            "node_id": section["node_id"],
            "owned_knowledge_keys": owned_keys,
            "reused_knowledge_keys": [],
        })
    return json.dumps({
        "knowledge_registry": registry,
        "sections": identities,
    }, ensure_ascii=False)


def _teaching_batch_v3_response(system_prompt, labels_by_title=None):
    section_match = re.search(
        r"## 当前小节（已去重）\n(\[.*?\])\n\n"
        r"## 当前批次知识与直接依赖闭包",
        system_prompt,
        re.S,
    )
    registry_match = re.search(
        r"## 当前批次知识与直接依赖闭包（只读）\n"
        r"(\[.*?\])\n\n## 当前批次知识职责",
        system_prompt,
        re.S,
    )
    identity_match = re.search(
        r"## 当前批次知识职责（只读）\n(\[.*?\])\n\n## 共享课程块目录",
        system_prompt,
        re.S,
    )
    assert section_match and registry_match and identity_match, system_prompt
    sections = json.loads(section_match.group(1))
    registry = json.loads(registry_match.group(1))
    identities = json.loads(identity_match.group(1))
    registry_by_key = {item["knowledge_key"]: item for item in registry}
    identity_by_id = {item["node_id"]: item for item in identities}
    labels = labels_by_title or {}
    payload = []
    for section in sections:
        label = labels.get(section["title"], section["title"])
        source_points = [
            point
            for group in _knowledge_structure(label)
            for point in group["knowledge_points"]
        ]
        keys = identity_by_id[section["node_id"]]["owned_knowledge_keys"]
        details = []
        for key, point in zip(keys, source_points, strict=True):
            details.append({
                "knowledge_key": key,
                "concept_group": f"{label}的核心机制",
                "group_description": f"从条件走向{label}的独立应用",
                "knowledge_type": point["knowledge_type"],
                "conditions": point.get("conditions") or [],
                "boundaries": point.get("boundaries") or [],
                "counterexamples": point.get("counterexamples") or [],
                "capability_points": point["capability_points"],
                "misconceptions": point.get("misconceptions") or [{
                    "name": f"{label}的典型误判",
                    "observable_error_pattern": f"忽略{label}成立所需的关键条件",
                    "discrimination": "检查作答是否明确验证了全部成立条件",
                    "repair_strategy": "先列条件清单，再逐项核对并修正推理",
                }],
                "mastery_criteria": point["mastery_criteria"],
                "aliases": [],
            })
        relations = []
        if len(keys) > 1:
            relations.append({
                "source_key": keys[0],
                "target_key": keys[1],
                "relation_type": "prerequisite",
                "reason": f"先掌握{registry_by_key[keys[0]]['name']}才能继续应用",
            })
        payload.append({
            "node_id": section["node_id"],
            "knowledge_details": details,
            "knowledge_relations": relations,
            "teaching_modules": [],
        })
    return json.dumps({"sections": payload}, ensure_ascii=False)


def _multi_section_outline(labels):
    return normalize_course_outline_contract({
        "course_title": "并行生成验证课程",
        "positioning": "验证质量约束不变时的结构性提速",
        "chapters": [{
            "title": "第一章",
            "sections": [
                {
                    "title": f"第{index}小节",
                    "learning_objective": f"能独立完成{label}",
                    "assessment": [f"提交{label}任务"],
                    "scope_boundary": f"只负责{label}",
                    "prerequisite_node_ids": (
                        [f"L2-1-{index - 1}"]
                        if index > 1
                        else []
                    ),
                }
                for index, label in enumerate(labels, start=1)
            ],
        }],
    })


def _outline_skeleton_v2_response(plan):
    return json.dumps({
        "course_title": plan["course_title"],
        "positioning": plan.get("positioning") or "完成全部课程成果",
        "learning_objectives": (
            plan.get("learning_objectives") or ["完成全部课程成果"]
        ),
        "prerequisites": plan.get("prerequisites") or [],
        "chapters": [
            {
                "chapter_number": index,
                "title": chapter["title"],
                "learning_focus": (
                    chapter.get("learning_focus")
                    or f"完成第 {index} 阶段学习任务"
                ),
                "section_count": len(chapter.get("sections") or []),
            }
            for index, chapter in enumerate(
                plan.get("chapters") or [],
                start=1,
            )
        ],
    }, ensure_ascii=False)


def _outline_batch_v2_response(system_prompt, plan):
    match = re.search(
        r"## 当前批次\n(\{.*?\})\n\n## 当前章已完成",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    spec = json.loads(match.group(1))
    sections_by_id = {
        section["node_id"]: section
        for chapter in plan.get("chapters") or []
        for section in chapter.get("sections") or []
    }
    return json.dumps({
        "sections": [
            sections_by_id[node_id]
            for node_id in spec["expected_node_ids"]
        ],
    }, ensure_ascii=False)


def _knowledge_skeleton_for_plan(plan, labels):
    sections = [
        section
        for chapter in plan["chapters"]
        for section in chapter["sections"]
    ]
    scope_contract = build_course_knowledge_scope_contract(plan)
    return normalize_course_knowledge_skeleton({
        "source_scope_revision_id": scope_contract["revision_id"],
        "sections": [
            {
                "node_id": section["node_id"],
                "owned_knowledge_names": [
                    point["name"]
                    for group in _knowledge_structure(label)
                    for point in group["knowledge_points"]
                ],
                "reused_knowledge_names": [],
            }
            for section, label in zip(sections, labels, strict=True)
        ],
    })


def _relation_batch_response(system_prompt):
    match = re.search(
        r"## 本批次必须逐一处理的目标知识点\n(\[.*?\])\n\n"
        r"## 本批次允许引用的关系上下文",
        system_prompt,
        re.S,
    )
    assert match, system_prompt
    targets = json.loads(match.group(1))
    context_match = re.search(
        r"## 本批次允许引用的关系上下文\n(\[.*?\])\n\n"
        r"## 建网规则",
        system_prompt,
        re.S,
    )
    assert context_match, system_prompt
    context = json.loads(context_match.group(1))
    target_ids = [item["knowledge_id"] for item in targets]
    prior_ids = [
        item["knowledge_id"]
        for item in context
        if item["knowledge_id"] not in target_ids
    ]
    decisions = []
    relations = []
    for index, knowledge_id in enumerate(target_ids):
        if index == 0 and prior_ids:
            source_id = prior_ids[0]
            decisions.append({
                "knowledge_id": knowledge_id,
                "decision": "connected",
                "reason": "承接前序小节的直接知识前置",
            })
            relations.append({
                "source_knowledge_id": source_id,
                "target_knowledge_id": knowledge_id,
                "relation_type": "prerequisite",
                "reason": "前序知识是当前知识独立学习所需的直接前置",
            })
        elif index == 0:
            decisions.append({
                "knowledge_id": knowledge_id,
                "decision": "course_entry",
                "reason": "这是当前课程关系网的真实起始知识",
            })
        else:
            decisions.append({
                "knowledge_id": knowledge_id,
                "decision": "connected",
                "reason": "承接本节首个知识点后才能独立应用",
            })
            relations.append({
                "source_knowledge_id": target_ids[0],
                "target_knowledge_id": knowledge_id,
                "relation_type": "prerequisite",
                "reason": "先理解本节首个知识点，才能独立应用当前知识",
            })
    return json.dumps({
        "node_decisions": decisions,
        "relations": relations,
    }, ensure_ascii=False)


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

    assert artifacts["pipeline_version"] == "course_generation_v16"
    assert artifacts["course_generation_brief"]["course_shape_constraints"] == {
        "minimum_chapter_count": 6,
        "minimum_section_count": 18,
    }
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
    assert "当前节点模块要求" not in context


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
async def test_course_service_builds_v12_blueprint_without_profile_model_call(
    monkeypatch,
    tmp_path,
):
    from material_storage import MaterialRepository

    service = CourseService(materials=MaterialRepository(tmp_path / "materials"))
    calls: list[str] = []
    plan = normalize_course_outline_contract({
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
                "complexity": "medium",
                "learning_objective": "能用定义解释导数",
                "prerequisite_node_ids": [],
                "misconceptions": ["连续不一定可导"],
                "assessment": ["能判断分段函数可导性"],
                "scope_boundary": "不展开高阶导数",
            }],
        }],
    })

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        calls.append(prompt)
        labels = {"导数的定义": "导数定义"}
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_v2_response(plan)
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_v2_response(system_prompt, plan)
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt, labels,
            )
        if prompt.startswith("生成详细小节教案批次"):
            return _teaching_batch_v3_response(
                system_prompt, labels,
            )
        raise AssertionError((prompt, system_prompt))

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)

    data = await service.build_course_draft(
        course_id="course-v2",
        topic="微积分",
        depth="intermediate",
        style="academic",
        generation_mode="fast",
        course_purpose="exam_sprint",
        asset_preferences={"questions": True, "final_assessment": True},
        web_question_enrichment={"enabled": True},
        requirements=(
            "生成 1 章，共 1 个小节；"
            "少废话，适合自学，讲清数学底层逻辑。"
        ),
        materials=[{
            "filename": "期末真题.md",
            "usage": "question_source",
            "importance": "core",
            "user_description": "真题用于例题和练习。",
            "content": "题目：根据导数定义求 f(x)=x^2 在 x=1 的导数？",
        }],
    )

    assert data["generation_pipeline_version"] == "course_generation_v16"
    assert data["generation_schema_version"] == "course_generation_v16"
    assert data["prompt_contract_version"] == "course_prompt_v23"
    assert len(calls) == 4
    assert not any("判断课程教学结构" in prompt for prompt in calls)
    assert data["course_purpose"] == "exam_sprint"
    assert data["generation_mode"] == "fast"
    assert data["asset_preferences"] == {"questions": True, "final_assessment": True}
    assert data["web_question_enrichment"]["enabled"] is True
    assert data["generation_request"]["course_purpose"] == "exam_sprint"
    assert data["generation_request"]["generation_mode"] == "fast"
    assert data["generation_request"]["asset_preferences"]["final_assessment"] is True
    assert data["generation_request"]["web_question_enrichment"]["enabled"] is True
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
    teaching_stage = data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert teaching_stage["status"] == "completed"
    assert teaching_stage["strategy"] == "adaptive_skeleton_batches"
    assert teaching_stage["model_call_count"] == 2
    assert teaching_stage["knowledge_compilation_model_call_count"] == 0
    assert teaching_stage["graph_compilation_model_call_count"] == 0
    assert data["course_teaching_plan"]["sections"]
    assert "course_knowledge_index" not in data
    assert data["course_knowledge_base"]["lifecycle_status"] == "active"
    assert data["knowledge_relations"]


@pytest.mark.asyncio
async def test_course_service_resumes_from_persisted_pedagogy_checkpoint(monkeypatch, tmp_path):
    from material_storage import MaterialRepository

    service = CourseService(materials=MaterialRepository(tmp_path / "materials"))
    calls = []
    plan = normalize_course_outline_contract({
        "course_title": "Python 工程实战",
        "learning_objectives": ["完成可运行项目"],
        "prerequisites": [],
        "chapters": [{
            "chapter_number": 1,
            "title": "最小项目",
            "sections": [{
                "section_number": "1.1",
                "title": "启动项目",
                "learning_objective": "能运行并验证输出",
                "assessment": ["命令返回预期结果"],
                "scope_boundary": "只覆盖启动与输出验证",
            }],
        }],
    })

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        calls.append(prompt)
        labels = {"启动项目": "项目启动"}
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_v2_response(plan)
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_v2_response(system_prompt, plan)
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt, labels,
            )
        if prompt.startswith("生成详细小节教案批次"):
            return _teaching_batch_v3_response(
                system_prompt, labels,
            )
        raise AssertionError((prompt, system_prompt))

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    profile = resolve_pedagogy_profile(
        subject="Python 工程实战",
        requirements="生成 1 章，共 1 个小节；完成可运行项目",
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
        requirements="生成 1 章，共 1 个小节；完成可运行项目",
        existing_course_data=existing,
    )

    assert len(calls) == 4
    assert calls[0].startswith("为「Python 工程实战」规划全课章节骨架")
    assert calls[2].startswith("规划全课知识职责骨架 V3")
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
    with pytest.raises(AIProviderRequestError, match="完整课程目录未通过结构验收"):
        await service.build_course_draft(
            course_id="course-invalid-outline",
            topic="全新主题代号",
            materials=[],
            pedagogy_mode="general",
        )

    # The complete chapter-skeleton path gets one bounded correction. Invalid
    # semantics still never become a fake placeholder course.
    assert len(calls) == 2
    assert not (tmp_path / "debug_failed_json.txt").exists()


@pytest.mark.asyncio
async def test_outline_provider_failure_is_not_reported_as_structure_error():
    service = CourseService()
    service.api_key = None

    with pytest.raises(AIProviderUnavailable, match="not_configured"):
        await service._call_llm_with_heartbeat(
            "生成课程目录",
            "只输出 JSON",
            enable_thinking=False,
            on_phase=None,
            phase="outline_generation",
            base_progress=32,
        )


@pytest.mark.asyncio
async def test_outline_phase_is_persisted_before_immediate_provider_failure(
    monkeypatch,
):
    service = CourseService()
    phases: list[tuple[str, str]] = []

    async def fail_immediately(*_args, **_kwargs):
        raise AIProviderRequestError("provider rejected immediately")

    async def capture_phase(
        phase,
        _progress,
        message,
        _phase_progress,
        _phase_detail,
    ):
        phases.append((phase, message))

    monkeypatch.setattr(service, "_call_llm", fail_immediately)
    with pytest.raises(
        AIProviderRequestError,
        match="provider rejected immediately",
    ):
        await service.build_course_draft(
            course_id="course-outline-phase",
            topic="量子力学",
            pedagogy_mode="auto",
            on_phase=capture_phase,
        )

    assert phases[-1] == (
        "outline_generation",
        "正在生成轻量章节骨架",
    )


def test_lightweight_outline_validation_does_not_require_knowledge_packages():
    outline = normalize_course_outline_contract({
        "course_title": "轻量目录测试",
        "chapters": [{
            "title": "第一章",
            "sections": [{
                "title": "明确学习责任",
                "learning_objective": "能说明本节负责解决的问题",
                "assessment": ["写出一条可观察结果"],
                "scope_boundary": "只确认责任和边界，不生成知识点",
            }],
        }],
    })

    report = validate_course_outline_constraints(outline, {"course_shape_constraints": {}})

    assert report["passed"] is True
    assert outline["chapters"][0]["sections"][0]["knowledge_structure"] == []


def test_outline_validation_leaves_fillable_quality_fields_for_review():
    outline = {
        "course_title": "允许审阅的轻量目录",
        "chapters": [{
            "sections": [
                {"title": "重复措辞"},
                {"title": "重复措辞"},
            ],
        }],
    }

    report = validate_course_outline_constraints(
        outline,
        {"course_shape_constraints": {}},
    )
    normalized = normalize_course_outline_contract(outline)

    assert report["passed"] is True
    assert report["issues"] == []
    assert all(
        section["learning_objective"] and section["scope_boundary"]
        for section in normalized["chapters"][0]["sections"]
    )


@pytest.mark.parametrize(
    ("requirements", "expected"),
    [
        ("生成 4 章、每章 3 节，共 12 个小节", {"chapter_count": 4, "section_count": 12}),
        ("安排四章，每章三节", {"chapter_count": 4, "section_count": 12}),
        ("课程需要 12 个递进小节", {"section_count": 12}),
    ],
)
def test_course_shape_constraints_distinguish_per_chapter_from_total(requirements, expected):
    from course_generation_workflow import _extract_course_shape_constraints

    assert _extract_course_shape_constraints(requirements) == expected


def test_section_knowledge_validation_keeps_relation_defects_as_advisories():
    valid = normalize_section_knowledge_package(_section_knowledge_package("局部校验"))
    valid["knowledge_structure"][0]["knowledge_points"][1]["entry_reason"] = "用于隔离关系端点校验"
    invalid = {
        **valid,
        "knowledge_relations": [{
            "source_name": "不存在的知识",
            "target_name": valid["key_points"][0],
            "relation_type": "prerequisite",
            "reason": "非法端点",
        }],
    }

    invalid_report = validate_section_knowledge_package(
        invalid,
        section_title="当前小节",
        available_knowledge_names=[],
    )
    valid_report = validate_section_knowledge_package(
        valid,
        section_title="当前小节",
        available_knowledge_names=[],
    )

    assert valid_report["passed"] is True
    assert invalid_report["passed"] is True
    assert invalid_report["strict_passed"] is False
    assert invalid_report["status"] == "passed_with_advisories"
    assert invalid_report["blocking_issues"] == []
    assert {
        item["code"] for item in invalid_report["advisory_issues"]
    } == {"section_knowledge:invalid_relation_endpoint"}


def test_course_relation_batch_requires_an_explicit_decision_for_every_node():
    payload = normalize_course_relation_batch({
        "node_decisions": [{
            "knowledge_id": "kp-a",
            "decision": "course_entry",
            "reason": "课程真实入口",
        }],
        "relations": [],
    })

    report = validate_course_relation_batch(
        payload,
        target_knowledge_ids=["kp-a", "kp-b"],
        allowed_knowledge_ids=["kp-a", "kp-b"],
    )

    assert report["passed"] is False
    assert {
        item["code"] for item in report["issues"]
    } == {"course_relations:missing_decision"}


def test_connected_node_without_inbound_is_repaired_to_course_entry():
    payload = {
        "node_decisions": [
            {
                "knowledge_id": "kp-a",
                "decision": "course_entry",
                "reason": "课程真实入口",
            },
            {
                "knowledge_id": "kp-b",
                "decision": "connected",
                "reason": "依赖 kp-a",
            },
            {
                "knowledge_id": "kp-c",
                "decision": "connected",
                "reason": "模型声称已连接，但没给关系",
            },
        ],
        "relations": [{
            "source_knowledge_id": "kp-a",
            "target_knowledge_id": "kp-b",
            "relation_type": "prerequisite",
            "reason": "kp-a 是 kp-b 的前置",
        }],
    }
    ids = ["kp-a", "kp-b", "kp-c"]
    report = validate_course_relation_batch(
        payload, target_knowledge_ids=ids, allowed_knowledge_ids=ids,
    )
    assert report["passed"] is False
    assert {item["code"] for item in report["issues"]} == {
        "course_relations:connected_without_relation"
    }

    repaired = repair_course_relation_batch_decisions(
        payload, issues=report["issues"],
    )
    assert repaired is not None
    decisions = {
        item["knowledge_id"]: item["decision"]
        for item in repaired["node_decisions"]
    }
    # Only the orphaned node is downgraded; the genuinely connected one stays.
    assert decisions == {
        "kp-a": "course_entry",
        "kp-b": "connected",
        "kp-c": "course_entry",
    }
    repaired_report = validate_course_relation_batch(
        repaired, target_knowledge_ids=ids, allowed_knowledge_ids=ids,
    )
    assert repaired_report["passed"] is True


def test_repair_refuses_batches_with_other_structural_issues():
    payload = {
        "node_decisions": [{
            "knowledge_id": "kp-a",
            "decision": "connected",
            "reason": "没入边",
        }],
        "relations": [{
            "source_knowledge_id": "kp-a",
            "target_knowledge_id": "kp-missing",
            "relation_type": "prerequisite",
            "reason": "非法端点",
        }],
    }
    report = validate_course_relation_batch(
        payload, target_knowledge_ids=["kp-a"], allowed_knowledge_ids=["kp-a"],
    )
    assert report["passed"] is False
    assert repair_course_relation_batch_decisions(
        payload, issues=report["issues"],
    ) is None


def test_course_relation_batches_merge_by_stable_ids():
    decisions, relations = merge_course_relation_batches([
        {
            "node_decisions": [{
                "knowledge_id": "kp-a",
                "decision": "course_entry",
                "reason": "课程真实入口",
            }],
            "relations": [],
        },
        {
            "node_decisions": [{
                "knowledge_id": "kp-b",
                "decision": "connected",
                "reason": "依赖入口知识",
            }],
            "relations": [{
                "source_knowledge_id": "kp-a",
                "target_knowledge_id": "kp-b",
                "relation_type": "prerequisite",
                "reason": "先掌握 A 才能学习 B",
            }],
        },
    ])

    report = validate_course_relation_batch(
        {
            "node_decisions": decisions,
            "relations": relations,
        },
        target_knowledge_ids=["kp-a", "kp-b"],
        allowed_knowledge_ids=["kp-a", "kp-b"],
    )

    assert report["passed"] is True
    assert [item["knowledge_id"] for item in decisions] == ["kp-a", "kp-b"]
    assert relations == [{
        "source_knowledge_id": "kp-a",
        "target_knowledge_id": "kp-b",
        "relation_type": "prerequisite",
        "reason": "先掌握 A 才能学习 B",
        "conditions": [],
        "derivation_steps": [],
    }]




def test_section_knowledge_validation_still_blocks_unusable_core_content():
    package = normalize_section_knowledge_package(
        _section_knowledge_package("核心缺失")
    )
    for point in package["knowledge_structure"][0]["knowledge_points"]:
        point["statement"] = ""
        point["description"] = ""

    report = validate_section_knowledge_package(
        package,
        section_title="核心缺失",
        available_knowledge_names=[],
    )

    assert report["passed"] is False
    assert report["status"] == "blocked"
    assert "section_knowledge:no_usable_points" in {
        item["code"] for item in report["blocking_issues"]
    }


def test_probability_style_quality_defects_no_longer_fail_the_course_plan():
    point = _knowledge_structure("古典概型")[0]["knowledge_points"][0]
    point["name"] = "等可能样本空间上的概率计算"
    point["entry_reason"] = ""
    plan = normalize_course_plan_contract({
        "course_title": "概率论",
        "chapters": [{
            "title": "古典概型",
            "sections": [{
                "title": "等可能样本空间上的概率计算",
                "knowledge_structure": [{
                    "concept_group": "等可能样本空间上的概率计算",
                    "knowledge_points": [point],
                }],
                "reused_knowledge_names": ["伯努利分布"],
                "knowledge_relations": [{
                    "source_name": "不存在的知识",
                    "target_name": point["name"],
                    "relation_type": "prerequisite",
                    "reason": "模型给出的悬空关系",
                }],
            }],
        }],
    })

    report = validate_course_plan_constraints(
        plan,
        {"course_shape_constraints": {}},
    )

    assert report["passed"] is True
    assert report["strict_passed"] is False
    assert report["blocking_issues"] == []
    assert {
        "plan:concept_group_mirrors_section",
        "plan:concept_group_too_small",
        "plan:knowledge_point_mirrors_section",
        "plan:invalid_reused_knowledge",
        "plan:invalid_relation_endpoint",
        "plan:knowledge_entry_reason_missing",
    } <= {item["code"] for item in report["advisory_issues"]}


@pytest.mark.asyncio
async def test_course_service_can_stop_after_outline_without_generating_knowledge(monkeypatch):
    service = CourseService()
    calls = []
    plan = normalize_course_outline_contract({
        "course_title": "目录确认课程",
        "learning_objectives": ["能完成目录确认"],
        "prerequisites": [],
        "chapters": [{
            "title": "确认结构",
            "sections": [{
                "title": "确认小节责任",
                "learning_objective": "能确认当前小节的责任与边界",
                "assessment": ["确认目录"],
                "scope_boundary": "不生成知识点和正文",
            }],
        }],
    })

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        calls.append(prompt)
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_v2_response(plan)
        return _outline_batch_v2_response(system_prompt, plan)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    data = await service.build_course_draft(
        course_id="course-outline-only",
        topic="目录确认课程",
        pedagogy_mode="general",
        requirements="生成 1 章，共 1 个小节",
        stop_after_outline=True,
    )

    assert len(calls) == 2
    assert calls[0].startswith("为「目录确认课程」规划全课章节骨架")
    assert data["generation_status"] == "outline_ready"
    assert data["course_outline"]["chapters"][0]["sections"][0]["knowledge_structure"] == []
    assert "course_knowledge_base" not in data


@pytest.mark.asyncio
async def test_stage_timeout_becomes_a_resumable_provider_error(monkeypatch):
    service = CourseService()

    async def time_out(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(service, "_call_llm", time_out)
    with pytest.raises(
        AIProviderRequestError,
        match="已停止当前最小生成单元，可从最近检查点继续",
    ):
        await service._call_llm_with_heartbeat(
            "生成当前小节",
            "只输出 JSON",
            enable_thinking=False,
            on_phase=None,
            phase="section_knowledge_generation",
            base_progress=35,
        )


@pytest.mark.asyncio
async def test_structured_call_can_outlive_wall_clock_while_stream_is_active(
    monkeypatch,
):
    service = CourseService()

    async def productive_stream(*_args, on_stream_activity=None, **_kwargs):
        for _ in range(3):
            await asyncio.sleep(0.4)
            on_stream_activity()
        return '{"status":"ok"}'

    monkeypatch.setattr(service, "_call_llm", productive_stream)
    started = time.monotonic()
    result = await service._call_llm_with_heartbeat(
        "生成结构化结果",
        "只输出 JSON",
        enable_thinking=False,
        on_phase=None,
        phase="structured_generation",
        base_progress=35,
        stage_timeout_seconds=1,
    )

    assert result == '{"status":"ok"}'
    assert time.monotonic() - started >= 1.15


@pytest.mark.asyncio
async def test_structured_call_stops_after_real_stream_inactivity(monkeypatch):
    service = CourseService()

    async def stalled_stream(*_args, **_kwargs):
        await asyncio.sleep(2)
        return "late"

    monkeypatch.setattr(service, "_call_llm", stalled_stream)
    with pytest.raises(
        CourseGenerationDeadlineExceeded,
        match="没有新内容",
    ):
        await service._call_llm_with_heartbeat(
            "生成结构化结果",
            "只输出 JSON",
            enable_thinking=False,
            on_phase=None,
            phase="structured_generation",
            base_progress=35,
            stage_timeout_seconds=1,
        )






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
    plan = normalize_course_outline_contract({
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
                    "learning_objective": "能使用判别式判断实数根的个数",
                    "prerequisite_node_ids": [],
                    "assessment": ["判断三个方程的根的情况"],
                },
                {
                    "node_id": "L2-1-2",
                    "section_number": "1.2",
                    "title": "实际问题建模",
                    "learning_objective": "能把面积问题转化为一元二次方程并验根",
                    "prerequisite_node_ids": ["L2-1-1"],
                    "assessment": ["完成一个面积建模任务"],
                },
            ],
        }],
    })
    responses = ["这不是 JSON", _outline_skeleton_v2_response(plan)]
    prompts = []

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        prompts.append(prompt)
        title_to_label = {
            "判别式与根的情况": "判别式判断",
            "实际问题建模": "面积问题建模",
        }
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt,
                title_to_label,
            )
        if prompt.startswith("生成详细小节教案批次"):
            return _teaching_batch_v3_response(
                system_prompt,
                title_to_label,
            )
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_v2_response(system_prompt, plan)
        return responses.pop(0)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    data = await service.build_course_draft(
        course_id="course-corrected-outline",
        topic="一元二次方程",
        requirements="严格生成1章2个递进小节，第一节判别式，第二节建模。",
        pedagogy_mode="math_formal",
    )

    assert len(prompts) == 6
    assert prompts[1].startswith("只修复全课章节骨架")
    assert prompts[3].startswith("规划全课知识职责骨架 V3")
    assert prompts[4].startswith("生成详细小节教案批次")
    assert prompts[5].startswith("生成详细小节教案批次")
    assert data["course_plan_constraint_report"]["passed"] is True
    assert data["course_plan_constraint_report"]["actual"] == {
        "chapter_count": 1,
        "section_count": 2,
    }
    assert len([node for node in data["nodes"] if node["node_level"] == 1]) == 1
    assert len([node for node in data["nodes"] if node["node_level"] == 2]) == 2


def test_course_knowledge_skeleton_freezes_unique_owner_and_earlier_reuse():
    labels = ["基础判断", "迁移应用"]
    plan = _multi_section_outline(labels)
    sections = [
        section
        for chapter in plan["chapters"]
        for section in chapter["sections"]
    ]
    skeleton = _knowledge_skeleton_for_plan(plan, labels)
    skeleton["sections"][1]["reused_knowledge_names"] = [
        skeleton["sections"][0]["owned_knowledge_names"][0]
    ]

    valid = validate_course_knowledge_skeleton(
        skeleton,
        sections=sections,
    )
    assert valid["passed"] is True

    duplicate = json.loads(json.dumps(skeleton, ensure_ascii=False))
    duplicate["sections"][1]["owned_knowledge_names"][0] = (
        duplicate["sections"][0]["owned_knowledge_names"][0]
    )
    invalid = validate_course_knowledge_skeleton(
        duplicate,
        sections=sections,
    )
    assert invalid["passed"] is False
    assert "knowledge_skeleton:duplicate_owner" in {
        issue["code"] for issue in invalid["blocking_issues"]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("section_count", [2, 3, 12, 21])
async def test_course_teaching_plan_always_uses_bounded_complete_pipeline(
    monkeypatch,
    section_count,
):
    labels = [f"能力{index}" for index in range(1, section_count + 1)]
    plan = _multi_section_outline(labels)
    title_to_label = {
        section["title"]: label
        for chapter in plan["chapters"]
        for section, label in zip(
            chapter["sections"],
            labels,
            strict=True,
        )
    }
    service = CourseService()
    calls: list[str] = []
    active_batches = 0
    max_active_batches = 0

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        nonlocal active_batches, max_active_batches
        calls.append(prompt)
        if "全课章节骨架 V2" in system_prompt:
                return json.dumps({
                    "course_title": plan["course_title"],
                    "positioning": plan["positioning"],
                    "learning_objectives": (
                        plan.get("learning_objectives")
                        or ["完成全部递进能力"]
                    ),
                    "prerequisites": plan.get("prerequisites") or [],
                "chapters": [{
                    "chapter_number": 1,
                    "title": plan["chapters"][0]["title"],
                    "learning_focus": "完成全部递进能力",
                    "section_count": section_count,
                }],
            }, ensure_ascii=False)
        if "章节小节目录批次 V2" in system_prompt:
            match = re.search(
                r"## 当前批次\n(\{.*?\})\n\n## 当前章已完成",
                system_prompt,
                re.S,
            )
            assert match, system_prompt
            spec = json.loads(match.group(1))
            section_by_id = {
                item["node_id"]: item
                for item in plan["chapters"][0]["sections"]
            }
            return json.dumps({
                "sections": [
                    section_by_id[node_id]
                    for node_id in spec["expected_node_ids"]
                ],
            }, ensure_ascii=False)
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt, title_to_label,
            )
        if prompt.startswith("生成详细小节教案批次"):
            active_batches += 1
            max_active_batches = max(max_active_batches, active_batches)
            await asyncio.sleep(0.003)
            response = _teaching_batch_v3_response(
                system_prompt, title_to_label,
            )
            active_batches -= 1
            return response
        return json.dumps(plan, ensure_ascii=False)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    course_data = await service.build_course_draft(
        course_id=f"course-{section_count}",
        topic="结构性提速课程",
        target_audience="大学生",
        depth="intermediate",
        style="academic",
        pedagogy_mode="general",
        requirements=f"生成 1 章，共 {section_count} 个小节",
    )

    stage = course_data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert stage["schema_version"] == "course_teaching_plan_v3"
    assert course_data["course_teaching_plan"]["schema_version"] == (
        "course_teaching_plan_v3"
    )
    assert course_data["course_teaching_plan"]["skeleton_revision_id"]
    assert course_data["generation_stage_artifacts"]["teaching"][
        "schema_version"
    ] == "course_teaching_plan_v3"
    expected_outline_calls = 1 + (
        section_count
        + service._outline_budget.batch_max_sections
        - 1
    ) // service._outline_budget.batch_max_sections
    expected_batches = (
        section_count
        + service._teaching_plan_budget.batch_max_sections
        - 1
    ) // service._teaching_plan_budget.batch_max_sections
    expected_skeleton_chunks = (
        section_count
        + service._teaching_plan_budget.skeleton_max_sections
        - 1
    ) // service._teaching_plan_budget.skeleton_max_sections
    assert stage["strategy"] == "adaptive_skeleton_batches"
    assert stage["schema_version"] == "course_teaching_plan_v3"
    assert stage["batch_count"] == expected_batches
    assert stage["skeleton_chunk_count"] == expected_skeleton_chunks
    assert stage["model_call_count"] == (
        expected_skeleton_chunks + expected_batches
    )
    assert len(calls) == (
        expected_outline_calls
        + expected_skeleton_chunks
        + expected_batches
    )
    assert max_active_batches == min(4, expected_batches)
    assert stage["knowledge_compilation_model_call_count"] == 0
    assert stage["graph_compilation_model_call_count"] == 0
    assert stage["section_count"] == section_count
    assert stage["knowledge_point_count"] == section_count * 2
    planned_sections = [
        section
        for chapter in course_data["course_plan"]["chapters"]
        for section in chapter["sections"]
    ]
    assert all(
        section["module_plan"]
        and all(
            module["teaching_purpose"]
            and module["teaching_guidance"]
            and module["knowledge_names"]
            for module in section["module_plan"]
        )
        for section in planned_sections
    )
    assert (
        course_data["course_knowledge_base"]["lifecycle_status"]
        == "active"
    )
    assert course_data["knowledge_relations"]
    assert "course_graph" not in course_data["generation_stage_artifacts"]


@pytest.mark.asyncio
async def test_single_section_course_never_uses_course_level_compact_path(
    monkeypatch,
):
    labels = ["完整入口"]
    plan = _multi_section_outline(labels)
    title_to_label = {
        section["title"]: label
        for chapter in plan["chapters"]
        for section, label in zip(
            chapter["sections"],
            labels,
            strict=True,
        )
    }
    service = CourseService()
    calls: list[str] = []

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        calls.append(prompt)
        if "全课章节骨架 V2" in system_prompt:
            return _outline_skeleton_v2_response(plan)
        if "章节小节目录批次 V2" in system_prompt:
            return _outline_batch_v2_response(system_prompt, plan)
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt,
                title_to_label,
            )
        if prompt.startswith("生成详细小节教案批次"):
            return _teaching_batch_v3_response(
                system_prompt,
                title_to_label,
            )
        raise AssertionError((prompt, system_prompt))

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)

    course_data = await service.build_course_draft(
        course_id="course-complete-single-section",
        topic="完整链路验证",
        target_audience="大学生",
        depth="intermediate",
        style="academic",
        pedagogy_mode="general",
        requirements="生成 1 章，共 1 个小节",
    )

    stage = course_data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert stage["status"] == "completed"
    assert stage["semantic_status"] == "ai_complete"
    assert stage["strategy"] == "adaptive_skeleton_batches"
    assert "compact_fallback_reason" not in stage
    assert stage["model_call_count"] == 2
    assert stage["degraded"] is False
    assert len(calls) == 4
    assert not any(
        prompt.startswith("生成整门课所有小节教案")
        for prompt in calls
    )


@pytest.mark.asyncio
async def test_total_timeout_fallback_preserves_completed_skeleton_and_batch():
    labels = [f"超时恢复{index}" for index in range(1, 7)]
    plan = attach_module_plans_to_plan(
        _multi_section_outline(labels),
        resolve_pedagogy_profile(subject="超时恢复课程", requirements=""),
    )
    sections = [
        section
        for chapter in plan["chapters"]
        for section in chapter["sections"]
    ]
    outline_revision_id = str(
        build_course_knowledge_scope_contract(plan)["revision_id"]
    )
    partial_skeleton = compile_fallback_teaching_skeleton(
        sections[:3],
        outline_revision_id=outline_revision_id,
    )
    first_spec = build_teaching_plan_batches(
        sections[:3],
        partial_skeleton,
        CourseService()._teaching_plan_budget,
    )[0]
    completed_batch = compile_fallback_teaching_batch(
        batch_spec=first_spec,
        skeleton=partial_skeleton,
        sections=sections,
    )
    completed_batch["sections"][0]["knowledge_details"][0][
        "group_description"
    ] = "MODEL_BATCH_MUST_SURVIVE_TIMEOUT"
    course_data = {
        "course_id": "course-timeout-preserve",
        "course_name": "超时恢复课程",
        "nodes": [],
        "generation_stage_artifacts": {
            "course_teaching_plan": {
                "status": "in_progress",
                "skeleton": partial_skeleton,
                "fallback_units": [],
                "batches": {
                    "TP-B01": {
                        "status": "completed",
                        "section_ids": list(first_spec["section_ids"]),
                        "skeleton_revision_id": partial_skeleton["revision_id"],
                        "payload": completed_batch,
                        "generation_source": "model",
                    },
                },
            },
        },
    }
    service = CourseService()

    await service._compile_fallback_course_teaching_plan(
        course_data=course_data,
        plan=plan,
        sections=sections,
        outline_revision_id=outline_revision_id,
        on_checkpoint=None,
        reason="teaching_plan_total_timeout",
        existing_skeleton=partial_skeleton,
    )

    stage = course_data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert stage["status"] == "retry_required"
    assert stage["semantic_status"] == "retry_required"
    assert stage["degraded"] is True
    assert stage["strategy"] == "adaptive_timeout_completion"
    assert stage["preserved_skeleton_section_count"] == 3
    assert stage["preserved_batch_count"] == 1
    assert stage["batches"]["TP-B01"]["generation_source"] == "model"
    assert (
        stage["batches"]["TP-B01"]["payload"]["sections"][0][
            "knowledge_details"
        ][0]["group_description"]
        == "MODEL_BATCH_MUST_SURVIVE_TIMEOUT"
    )
    assert stage["batches"]["TP-B02"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    assert [item["unit"] for item in stage["fallback_units"]] == [
        "TP-B02",
        "TP-B03",
        "TP-B04",
        "TP-B05",
        "TP-B06",
    ]


@pytest.mark.asyncio
async def test_teaching_skeleton_restart_resumes_after_completed_chunk(
    monkeypatch,
):
    labels = [f"骨架续跑{index}" for index in range(1, 13)]
    plan = attach_module_plans_to_plan(
        _multi_section_outline(labels),
        resolve_pedagogy_profile(subject="骨架续跑课程", requirements=""),
    )
    sections = [
        section
        for chapter in plan["chapters"]
        for section in chapter["sections"]
    ]
    title_to_label = {
        section["title"]: label
        for section, label in zip(sections, labels, strict=True)
    }
    outline_revision_id = str(
        build_course_knowledge_scope_contract(plan)["revision_id"]
    )
    service = CourseService()
    first_chunk_size = service._teaching_plan_budget.skeleton_max_sections
    partial_registry = []
    partial_identities = []
    knowledge_index = 1
    for section, label in zip(
        sections[:first_chunk_size],
        labels[:first_chunk_size],
        strict=True,
    ):
        owned_keys = []
        previous_key = ""
        module_id = str(
            (section.get("module_plan") or [{}])[0].get("module_id")
            or "core_explanation"
        )
        for point in [
            item
            for group in _knowledge_structure(label)
            for item in group["knowledge_points"]
        ]:
            key = f"K{knowledge_index:03d}"
            knowledge_index += 1
            owned_keys.append(key)
            partial_registry.append({
                "knowledge_key": key,
                "name": point["name"],
                "statement": point["statement"],
                "owner_node_id": section["node_id"],
                "reused_in_node_ids": [],
                "prerequisite_keys": [previous_key] if previous_key else [],
                "module_ids": [module_id],
            })
            previous_key = key
        partial_identities.append({
            "node_id": section["node_id"],
            "owned_knowledge_keys": owned_keys,
            "reused_knowledge_keys": [],
        })
    partial_skeleton = normalize_teaching_plan_skeleton_v3(
        {
            "knowledge_registry": partial_registry,
            "sections": partial_identities,
        },
        outline_revision_id=outline_revision_id,
    )
    course_data = {
        "course_id": "course-skeleton-resume",
        "course_name": "骨架续跑课程",
        "nodes": [],
        "generation_stage_artifacts": {
            "course_teaching_plan": {
                "status": "in_progress",
                "source_outline_revision_id": outline_revision_id,
                "skeleton": partial_skeleton,
                "completed_skeleton_chunk_count": 1,
                "completed_skeleton_section_count": first_chunk_size,
                "batches": {},
            },
        },
    }
    skeleton_calls: list[str] = []

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        if prompt.startswith("规划全课知识职责骨架 V3"):
            skeleton_calls.append(prompt)
            return _teaching_skeleton_v3_response(
                system_prompt,
                title_to_label,
            )
        if prompt.startswith("生成详细小节教案批次"):
            return _teaching_batch_v3_response(
                system_prompt,
                title_to_label,
            )
        raise AssertionError(prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    await service._prepare_course_teaching_plan(
        course_data=course_data,
        plan=plan,
        artifacts=None,
        on_phase=None,
        on_checkpoint=None,
    )

    stage = course_data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    chunk_count = len(sections) // first_chunk_size
    assert skeleton_calls == [
        f"规划全课知识职责骨架 V3 分片 {index}/{chunk_count}，只输出 JSON。"
        for index in range(2, chunk_count + 1)
    ]
    assert stage["resumed_skeleton_chunk_count"] == 1
    assert stage["completed_skeleton_chunk_count"] == chunk_count
    assert stage["status"] == "completed"


@pytest.mark.asyncio
async def test_teaching_plan_local_fallback_preserves_successful_batches(monkeypatch):
    labels = [f"恢复能力{index}" for index in range(1, 7)]
    plan = _multi_section_outline(labels)
    plan = attach_module_plans_to_plan(
        plan,
        resolve_pedagogy_profile(subject="恢复课程", requirements=""),
    )
    title_to_label = {
        section["title"]: label
        for chapter in plan["chapters"]
        for section, label in zip(chapter["sections"], labels, strict=True)
    }
    course_data = {
        "course_id": "course-batch-resume",
        "course_name": "批次恢复课程",
        "generation_stage_artifacts": {},
        "nodes": [],
    }
    service = CourseService()
    fail_second_batch = True
    calls = []

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        calls.append(prompt)
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(system_prompt, title_to_label)
        if "TP-B02" in prompt and fail_second_batch:
            return "{}"
        if (
            prompt.startswith("生成详细小节教案批次")
            or prompt.startswith("只修复详细教案批次")
        ):
            return _teaching_batch_v3_response(system_prompt, title_to_label)
        raise AssertionError(prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    with pytest.raises(AIProviderRequestError, match="停止在正文之前"):
        await service._prepare_course_teaching_plan(
            course_data=course_data,
            plan=plan,
            artifacts=None,
            on_phase=None,
            on_checkpoint=None,
        )

    stage = course_data["generation_stage_artifacts"]["course_teaching_plan"]
    assert stage["status"] == "retry_required"
    assert stage["semantic_status"] == "retry_required"
    assert stage["degraded"] is True
    assert stage["completed_batch_count"] == 6
    assert stage["completed_section_count"] == 6
    assert stage["batches"]["TP-B01"]["status"] == "completed"
    assert stage["batches"]["TP-B01"]["generation_source"] == "model"
    assert stage["batches"]["TP-B02"]["status"] == "completed"
    assert stage["batches"]["TP-B02"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    first_batch_revision = stage["batches"]["TP-B01"]["revision_id"]
    fail_second_batch = False
    calls_before_resume = len(calls)
    resumed = await service._prepare_course_teaching_plan(
        course_data=course_data,
        plan=plan,
        artifacts=None,
        on_phase=None,
        on_checkpoint=None,
    )

    resumed_calls = calls[calls_before_resume:]
    assert resumed_calls == [
        "生成详细小节教案批次 TP-B02，只输出 JSON。"
    ]
    assert stage["batches"]["TP-B01"]["revision_id"] == first_batch_revision
    assert stage["status"] == "completed"
    assert stage["semantic_status"] == "ai_complete"
    assert stage["completed_batch_count"] == 6
    assert course_data["course_teaching_plan"]["schema_version"] == "course_teaching_plan_v3"
    assert len([
        section for chapter in resumed["chapters"] for section in chapter["sections"]
    ]) == 6


@pytest.mark.asyncio
async def test_teaching_plan_automatically_retries_only_local_unit_once(
    monkeypatch,
):
    labels = [f"自动恢复能力{index}" for index in range(1, 7)]
    plan = attach_module_plans_to_plan(
        _multi_section_outline(labels),
        resolve_pedagogy_profile(subject="自动恢复课程", requirements=""),
    )
    title_to_label = {
        section["title"]: label
        for chapter in plan["chapters"]
        for section, label in zip(chapter["sections"], labels, strict=True)
    }
    course_data = {
        "course_id": "course-auto-semantic-retry",
        "course_name": "教案最小单元自动恢复",
        "generation_stage_artifacts": {},
        "nodes": [],
    }
    service = CourseService()
    batch_calls: dict[str, int] = {}

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(
                system_prompt,
                title_to_label,
            )
        if (
            prompt.startswith("生成详细小节教案批次")
            or prompt.startswith("只修复详细教案批次")
        ):
            match = re.search(r"TP-B\d{2}", prompt)
            assert match
            batch_id = match.group(0)
            batch_calls[batch_id] = batch_calls.get(batch_id, 0) + 1
            if batch_id == "TP-B02" and batch_calls[batch_id] <= 2:
                return "{}"
            return _teaching_batch_v3_response(
                system_prompt,
                title_to_label,
            )
        raise AssertionError(prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    result = await service._prepare_course_teaching_plan(
        course_data=course_data,
        plan=plan,
        artifacts=None,
        on_phase=None,
        on_checkpoint=None,
    )

    stage = course_data["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert stage["status"] == "completed"
    assert stage["semantic_status"] == "ai_complete"
    assert stage["semantic_retry_count"] == 1
    assert stage["fallback_units"] == []
    assert batch_calls["TP-B02"] == 3
    assert all(
        count == 1
        for batch_id, count in batch_calls.items()
        if batch_id != "TP-B02"
    )
    assert len([
        section
        for chapter in result["chapters"]
        for section in chapter["sections"]
    ]) == 6


def test_section_package_must_keep_skeleton_names_verbatim():
    package = _section_knowledge_package("知识任务")
    package["knowledge_structure"][0]["knowledge_points"][0][
        "name"
    ] = "知识任务 的成立条件"
    package["reused_knowledge_names"] = ["前置 知识"]

    report = validate_section_knowledge_package(
        package,
        section_title="知识任务小节",
        available_knowledge_names=["前置知识"],
        required_knowledge_names=[
            "知识任务的成立条件",
            "知识任务的应用判断",
        ],
        required_reused_knowledge_names=["前置知识"],
        validate_relations=False,
    )

    assert report["passed"] is False
    assert {
        "section_knowledge:renamed_skeleton_identity",
        "section_knowledge:reuse_contract_mismatch",
    } <= {
        issue["code"] for issue in report["blocking_issues"]
    }


def test_knowledge_skeleton_receives_bounded_section_evidence_hints():
    section = {
        "grounding_contract": {
            "required_evidence_ids": [
                f"evidence-{index}" for index in range(1, 7)
            ],
        },
    }
    artifacts = {
        "evidence_catalog": [
            {
                "evidence_id": f"evidence-{index}",
                "kind": "definition",
                "source_text": f"资料概念{index}" * 100,
            }
            for index in range(1, 7)
        ],
    }

    hints = build_section_knowledge_skeleton_evidence_hints(
        artifacts,
        section,
    )

    assert len(hints) == 4
    assert [item["evidence_id"] for item in hints] == [
        "evidence-1",
        "evidence-2",
        "evidence-3",
        "evidence-4",
    ]
    assert all(len(item["summary"]) <= 240 for item in hints)


def test_course_planning_concurrency_has_a_production_hard_cap(monkeypatch):
    monkeypatch.setenv("COURSE_GENERATION_PLANNING_CONCURRENCY", "99")
    assert CourseService()._planning_concurrency == 8

    monkeypatch.setenv("COURSE_GENERATION_PLANNING_CONCURRENCY", "invalid")
    assert CourseService()._planning_concurrency == 4












@pytest.mark.asyncio
async def test_concurrent_batch_failures_degrade_only_failed_batches(monkeypatch):
    """Independent bad batches must not turn the whole plan into a failure."""
    labels = [f"并发失败能力{index}" for index in range(1, 13)]
    plan = _multi_section_outline(labels)
    plan = attach_module_plans_to_plan(
        plan,
        resolve_pedagogy_profile(subject="并发失败课程", requirements=""),
    )
    title_to_label = {
        section["title"]: label
        for chapter in plan["chapters"]
        for section, label in zip(chapter["sections"], labels, strict=True)
    }
    course_data = {
        "course_id": "course-batch-failure-id",
        "course_name": "并发失败课程",
        "generation_stage_artifacts": {},
        "nodes": [],
    }
    service = CourseService()

    async def fake_call_llm(prompt, system_prompt, **_kwargs):
        if prompt.startswith("规划全课知识职责骨架 V3"):
            return _teaching_skeleton_v3_response(system_prompt, title_to_label)
        # Fail a later batch as well as an earlier one so the two race.
        if any(batch_id in prompt for batch_id in ("TP-B02", "TP-B04")):
            return "{}"
        if (
            prompt.startswith("生成详细小节教案批次")
            or prompt.startswith("只修复详细教案批次")
        ):
            return _teaching_batch_v3_response(system_prompt, title_to_label)
        raise AssertionError(prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    with pytest.raises(AIProviderRequestError, match="停止在正文之前"):
        await service._prepare_course_teaching_plan(
            course_data=course_data,
            plan=plan,
            artifacts=None,
            on_phase=None,
            on_checkpoint=None,
        )

    stage = course_data["generation_stage_artifacts"]["course_teaching_plan"]
    assert stage["status"] == "retry_required"
    assert stage["semantic_status"] == "retry_required"
    assert stage["degraded"] is True
    assert {item["unit"] for item in stage["fallback_units"]} == {
        "TP-B02",
        "TP-B04",
    }
    assert stage["batches"]["TP-B02"]["status"] == "completed"
    assert stage["batches"]["TP-B04"]["status"] == "completed"
    assert stage["batches"]["TP-B02"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    assert stage["batches"]["TP-B04"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    assert stage["batches"]["TP-B01"]["status"] == "completed"
    assert stage["batches"]["TP-B03"]["status"] == "completed"
