import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from course_generation.outline import normalize_outline_skeleton
from course_repository import CourseDocumentRepository
from course_versioning import build_blueprint_draft
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from guided_generation import step_state as guided_step_state
from jobs.manager import TaskManager, TaskStateConflict, _teacher_outline_result_ready


class MemoryStorage:
    def __init__(self, course=None):
        self.course = deepcopy(course)

    def load_course(self, _course_id):
        return deepcopy(self.course)

    async def save_course(self, _course_id, data):
        self.course = deepcopy(data)


class BlueprintService:
    @staticmethod
    def _attach_teaching(course):
        course["course_composition_profile"] = {
            "style": "example_driven",
            "label": "案例实战",
            "summary": "增加典型案例与真实场景。",
            "rhythm": ["讲解", "补充案例", "真实场景", "学习者行动", "检查反馈"],
        }
        course["course_block_distribution"] = {
            "style": "example_driven",
            "total_blocks": 2,
            "composition_added_blocks": 1,
            "role_counts": {"concept": 1, "example": 1},
        }
        for node in course["nodes"]:
            node["module_plan"] = [{
                "module_id": "core_explanation",
                "module_instance_id": "L2-1-1:core_explanation:1",
                "label": "核心教学",
                "block_role": "concept",
                "composition_source": "subject_required",
                "block_difficulty_contract": {"target_level": "intermediate"},
            }, {
                "module_id": "composition_case_extension",
                "module_instance_id": "L2-1-1:composition_case_extension:1",
                "label": "补充案例",
                "block_role": "example",
                "composition_source": "composition_style",
                "block_difficulty_contract": {"target_level": "intermediate"},
            }]
        course["course_teaching_plan"] = {
            "schema_version": "course_teaching_plan_v2",
            "revision_id": "teaching-plan-1",
            "sections": [
                {
                    "node_id": "L2-1-1",
                    "teaching_modules": [
                        {
                            "module_id": "core_explanation",
                            "teaching_purpose": "解释概念边界",
                            "knowledge_names": ["概念的内涵", "概念的外延"],
                        },
                        {
                            "module_id": "composition_case_extension",
                            "teaching_purpose": "用案例检验概念边界",
                            "knowledge_names": ["概念的外延"],
                        },
                    ],
                }
            ],
        }
        course.setdefault("generation_stage_artifacts", {})["course_teaching_plan"] = {
            "status": "completed",
            "schema_version": "course_teaching_plan_v2",
            "strategy": "single_whole_course_call",
            "model_call_count": 1,
            "knowledge_compilation_model_call_count": 0,
            "graph_compilation_model_call_count": 0,
        }
        return course

    async def build_course_draft(self, **kwargs):
        course = deepcopy(kwargs["existing_course_data"])
        existing_nodes = {
            str(node.get("node_id") or ""): deepcopy(node)
            for node in course.get("nodes") or []
        }
        course.update({
            "course_blueprint": {"nodes": []},
            "subject_pedagogy_profile": {
                "primary_mode": "general",
                "secondary_mode": None,
                "secondary_intensity": None,
                "confidence": "high",
                "evidence": [],
                "rationale": "test",
                "enabled_module_ids": [],
                "user_locked": True,
            },
            "nodes": [{
                "node_id": "L2-1-1",
                "node_level": 2,
                "parent_node_id": "root",
                "node_name": "概念",
                "learning_objective": "能够解释概念",
                "knowledge_structure": [{
                    "concept_group": "概念辨析",
                    "description": "区分概念的内涵与外延",
                    "knowledge_points": [{
                        "name": "概念的内涵",
                        "statement": "概念的内涵由该概念所反映对象的本质属性组成。",
                        "knowledge_type": "definition",
                        "conditions": ["讨论的是同一语境下的概念"],
                        "boundaries": ["内涵不是对象实例的简单罗列"],
                        "capability_points": [{
                            "name": "解释概念内涵",
                            "observable_behavior": "给定一个概念，准确说出构成其内涵的本质属性",
                        }],
                        "mastery_criteria": [{
                            "name": "概念内涵解释达标",
                            "observable_performance": "独立解释一个新概念的内涵并排除偶然属性",
                            "verification_method": "分析三个属性并说明保留或排除理由",
                        }],
                        "entry_reason": "内涵是建立概念边界的课程入口。",
                        "relations": [{
                            "target_name": "概念的外延",
                            "relation_type": "contrasts_with",
                            "reason": "内涵描述本质属性，外延描述符合这些属性的对象范围",
                            "distinction": "属性集合与对象范围",
                        }],
                    }, {
                        "name": "概念的外延",
                        "statement": "概念的外延是所有符合该概念内涵的对象组成的范围。",
                        "knowledge_type": "definition",
                        "conditions": ["对象满足概念的全部本质属性"],
                        "boundaries": ["不满足任一本质属性的对象不属于外延"],
                        "capability_points": [{
                            "name": "判断概念外延",
                            "observable_behavior": "给定对象集合，准确判断哪些对象属于概念外延",
                        }],
                        "mastery_criteria": [{
                            "name": "概念外延判断达标",
                            "observable_performance": "独立判断新对象是否属于概念外延并说明依据",
                            "verification_method": "完成正例、反例和边界例的分类",
                        }],
                    }],
                }],
                "key_points": ["概念的内涵", "概念的外延"],
                "assessment": ["解释概念"],
                "difficulty_contract": {},
                "grounding_contract": {},
                "generation_status": "pending",
            }],
        })
        for node in course["nodes"]:
            existing = existing_nodes.get(str(node.get("node_id") or "")) or {}
            for field in (
                "node_name",
                "learning_objective",
                "scope_boundary",
                "assessment",
                "prerequisite_node_ids",
            ):
                if field in existing:
                    node[field] = deepcopy(existing[field])
        if kwargs.get("stop_after_outline"):
            for node in course["nodes"]:
                node["knowledge_structure"] = []
                node["key_points"] = []
                node["module_plan"] = []
        return course
        return self._attach_teaching(course)

    def compile_teaching_plan(self, course):
        return self._attach_teaching(deepcopy(course))


class SkeletonGateService(BlueprintService):
    stop_after_skeleton = None
    stop_after_outline = None
    detail_input = None

    async def build_course_draft(self, **kwargs):
        self.stop_after_skeleton = kwargs.get("stop_after_skeleton")
        self.stop_after_outline = kwargs.get("stop_after_outline")
        if kwargs.get("stop_after_skeleton"):
            course = deepcopy(kwargs["existing_course_data"])
            request_fingerprint = "outline-request-1"
            lectures = [
                {
                    "lecture_number": number,
                    "title": title,
                    "content_summary": f"讲解{title}的核心内容与应用范围",
                    "learning_objective": objective,
                    "scope_boundary": boundary,
                    "hour_breakdown": {
                        "classroom_lecture": 8,
                        "classroom_practice": 0,
                        "online_instruction": 0,
                    },
                }
                for number, title, objective, boundary in (
                    (1, "基础概念", "能够解释核心概念", "只处理基础概念"),
                    (2, "综合应用", "能够完成综合应用", "使用已学概念解决问题"),
                )
            ]
            skeleton = normalize_outline_skeleton(
                {
                    "authoring_structure_version": "lecture_v1",
                    "course_title": "教师课程方案",
                    "learning_objectives": ["形成课程结构"],
                    "course_modules": [
                        {
                            "module_id": "M1",
                            "title": "课程主线",
                            "lecture_numbers": [1, 2],
                        }
                    ],
                    "total_hours": 16,
                    "lectures": lectures,
                },
                topic="教师课程方案",
                request_fingerprint=request_fingerprint,
            )
            chapters = []
            nodes = []
            for lecture in skeleton["chapters"]:
                number = int(lecture["lecture_number"])
                l1_id = f"L1-{number}"
                l2_id = f"L2-{number}-1"
                section = {
                    "node_id": l2_id,
                    "section_number": f"{number}.1",
                    "title": lecture["title"],
                    "learning_objective": lecture["learning_objective"],
                    "scope_boundary": lecture["scope_boundary"],
                    "hour_breakdown": deepcopy(lecture["hour_breakdown"]),
                    "planned_hours": lecture["planned_hours"],
                    "content_summary": lecture["content_summary"],
                    "key_points": [],
                    "key_difficulties": [],
                    "activities": [],
                    "homework": [],
                    "application_anchors": [],
                    "extension_resources": [],
                    "learning_tasks": [],
                    "education_objective_refs": [],
                    "ideology_implementation": "",
                    "external_mentor": {},
                    "assessment": [],
                }
                chapters.append({
                    **deepcopy(lecture),
                    "sections": [deepcopy(section)],
                })
                nodes.extend([
                    {
                        "node_id": l1_id,
                        "parent_node_id": "root",
                        "node_level": 1,
                        "node_name": lecture["title"],
                        "learning_objective": lecture["learning_objective"],
                        "generation_status": "pending",
                    },
                    {
                        **deepcopy(section),
                        "parent_node_id": l1_id,
                        "node_level": 2,
                        "node_name": lecture["title"],
                        "generation_status": "pending",
                    },
                ])
            plan = {
                "authoring_structure_version": "lecture_v1",
                "course_title": skeleton["course_title"],
                "learning_objectives": deepcopy(skeleton["learning_objectives"]),
                "course_modules": deepcopy(skeleton["course_modules"]),
                "total_hours": 16,
                "chapters": chapters,
            }
            course.update({
                "course_name": skeleton["course_title"],
                "authoring_structure_version": "lecture_v1",
                "generation_status": "outline_framework_ready",
                "outline_framework_only": True,
                "outline_generation_status": "framework_ready",
                "outline_lifecycle_status": "draft",
                "course_plan": deepcopy(plan),
                "course_outline": deepcopy(plan),
                "course_blueprint": {"nodes": deepcopy(nodes)},
                "nodes": nodes,
                "course_outline_quality_report": None,
                "generation_quality_report": None,
                "generation_stage_artifacts": {
                    "outline": {
                        "status": "waiting_for_input",
                        "strategy": "teacher_framework_then_lecture_tasks",
                        "request_fingerprint": request_fingerprint,
                        "skeleton_revision_id": skeleton["revision_id"],
                        "skeleton": skeleton,
                        "detail_batches": {},
                    },
                },
                "course_generation_brief": {
                    "course_shape_constraints": {
                        "teacher_lecture_mode": True,
                        "chapter_count": 2,
                        "section_count": 2,
                        "lecture_count": 2,
                    },
                    "course_type_contract": {},
                },
            })
            return course
        course = deepcopy(kwargs["existing_course_data"])
        self.detail_input = deepcopy(course)
        outline_stage = course["generation_stage_artifacts"]["outline"]
        outline_stage.update({
            "status": "completed",
            "strategy": "teacher_framework_then_lecture_tasks",
            "course_contract_status": "completed",
            "course_contract": {"positioning": "当前课程级合同"},
            "detail_batches": {
                f"OUT-TD-{number:03d}": {
                    "status": "completed",
                    "lesson_id": f"L1-{number}",
                    "lecture_numbers": [number],
                }
                for number in (1, 2)
            },
        })
        course.update({
            "generation_status": "outline_completed",
            "outline_framework_only": False,
            "outline_generation_status": "completed",
            "outline_lifecycle_status": "current",
            "course_outline_quality_report": {"passed": True, "blockers": []},
        })
        return course


class InvalidTeacherOutlineService:
    async def build_course_draft(self, **kwargs):
        course = deepcopy(kwargs["existing_course_data"])
        course.update({"course_outline": {}, "nodes": []})
        return course


@pytest.mark.asyncio
async def test_process_task_persists_precise_release_quality_handoff(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "versions"),
        workspace_repository=GenerationWorkspaceRepository(tmp_path / "workspaces"),
        document_repository=CourseDocumentRepository(storage),
    )
    manager.tasks["release-check"] = {
        "id": "release-check",
        "job_id": "release-check",
        "task_id": "release-check",
        "course_id": "course-release-check",
        "type": "course_generation",
        "status": "pending",
        "progress": 94,
        "phase": "content_confirmed",
        "current_phase": "content_confirmed",
        "phase_progress": 100,
        "phase_detail": {},
        "message": "正在处理...",
        "current_nodes": [],
        "logs": [],
        "guided_workflow": {
            "schema_version": "guided_course_generation_v3",
            "current_step": "release",
            "review_step": None,
            "steps": [
                {"number": 1, "key": "requirements", "status": "confirmed"},
                {"number": 2, "key": "outline", "status": "confirmed"},
                {"number": 3, "key": "teaching", "status": "confirmed"},
                {"number": 4, "key": "content", "status": "confirmed"},
                {"number": 5, "key": "release", "status": "pending"},
            ],
        },
    }

    await manager._process_task("release-check")

    task = manager.tasks["release-check"]
    assert task["current_phase"] == "publication_quality_check"
    assert task["message"] == "正在执行发布前质量检查"


@pytest.mark.asyncio
async def test_content_generation_never_starts_a_separate_graph_model_call(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(
        task_manager_module,
        "TASKS_FILE",
        tmp_path / "tasks.json",
    )
    graph_called = {"value": False}

    class NoGraphService:
        async def generate_course_graph_enrichment(
            self,
            *_args,
            **_kwargs,
        ):
            graph_called["value"] = True
            raise AssertionError("正文阶段不得再调用图谱模型")

        @staticmethod
        def register_course_generation_metadata(_course_id, _course):
            return None

    course = {
        "course_id": "parallel-course",
        "course_name": "并行课程",
        "course_blueprint": {"nodes": [{"node_id": "L2-1-1"}]},
        "course_knowledge_base": {
            "lifecycle_status": "active",
            "revision_id": "knowledge-1",
        },
        "course_knowledge_map": {
            "course_knowledge_base_revision_id": "knowledge-1",
        },
        "course_teaching_plan": {
            "schema_version": "course_teaching_plan_v2",
            "revision_id": "teaching-1",
        },
        "learning_asset_plan": {"status": "ready"},
        "generation_stage_artifacts": {
            "course_teaching_plan": {
                "status": "completed",
                "knowledge_compilation_model_call_count": 0,
                "graph_compilation_model_call_count": 0,
            },
        },
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "并行节点",
            "module_plan": [{"module_id": "core_explanation"}],
            "generation_status": "pending",
        }],
    }
    storage = MemoryStorage(course)
    manager = TaskManager(
        storage,
        NoGraphService(),
        None,
        version_repository=CourseVersionRepository(
            tmp_path / "versions"
        ),
        workspace_repository=GenerationWorkspaceRepository(
            tmp_path / "workspaces"
        ),
        document_repository=CourseDocumentRepository(storage),
    )
    manager.tasks["parallel-job"] = {
        "job_id": "parallel-job",
        "task_id": "parallel-job",
        "course_id": "parallel-course",
        "type": "course_generation",
        "status": "pending",
        "progress": 55,
        "request_snapshot": {"generation_mode": "fast"},
        "blueprint_confirmed": True,
        "current_nodes": [],
        "logs": [],
    }

    async def fake_schedule(_task_id, _nodes):
        def finish_content(fresh):
            fresh["nodes"][0].update({
                "node_content": "正文检查点",
                "generated_chars": 5,
                "generation_status": "completed",
            })
            return fresh

        await manager._mutate_task_course(
            "parallel-job",
            finish_content,
        )

    completed = {"value": False}

    async def fake_complete(_task_id, _course):
        completed["value"] = True

    monkeypatch.setattr(manager, "_schedule_nodes", fake_schedule)
    monkeypatch.setattr(manager, "_complete_task", fake_complete)

    await manager._process_task("parallel-job")

    assert graph_called["value"] is False
    assert completed["value"] is True
    assert storage.course["nodes"][0]["node_content"] == "正文检查点"
    assert "course_graph" not in storage.course["generation_stage_artifacts"]


@pytest.mark.asyncio
async def test_review_mode_waits_and_confirms_same_job(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "versions"),
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
    )
    job = await manager.create_generation_job({
        "subject": "概念课",
        "generation_mode": "fast",
        "course_purpose": "systematic",
    })
    assert manager.tasks[job["job_id"]]["request_snapshot"]["generation_mode"] == "review_blueprint"
    assert manager.tasks[job["job_id"]]["guided_workflow"]["steps"][0]["status"] == "confirmed"
    assert await manager._task_queue.get() == job["job_id"]
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)

    assert manager.tasks[job["job_id"]]["status"] == "waiting_for_review"
    assert manager.tasks[job["job_id"]]["guided_workflow"]["review_step"] == "outline"
    assert storage.course["course_schema_version"] == "course_document_v1"
    assert storage.course["course_document"]["sections"] == []
    assert "nodes" not in storage.course
    workspace_course = manager.get_generation_workspace_course(job["course_id"])
    assert workspace_course is not None
    assert workspace_course["nodes"][0]["node_name"] == "概念"
    assert workspace_course["nodes"][0].get("module_plan") == []
    assert "course_block_distribution" not in workspace_course
    assert "knowledge_library_binding" not in workspace_course
    assert workspace_course["nodes"][0]["knowledge_structure"] == []
    assert "course_knowledge_base" not in workspace_course
    preview = manager.get_generation_preview(job["course_id"])
    assert preview is not None
    assert preview["projection"] == "generation_workspace"
    assert preview["task"]["status"] == "waiting_for_review"
    assert preview["nodes"][0]["node_name"] == "概念"
    assert preview["nodes"][0]["content_state"] == "pending"
    assert preview["teaching_plan"]["status"] == "pending"
    assert preview["teaching_plan"]["sections"] == []
    assert "request_snapshot" not in preview["task"]

    workspaces.update_course(
        job["job_id"],
        lambda course: {
            **course,
            "nodes": [{
                **course["nodes"][0],
                "node_content_draft": "正在形成的课程正文",
                "generation_status": "generating",
            }],
        },
    )
    draft_preview = manager.get_generation_preview(job["course_id"])
    assert draft_preview is not None
    assert draft_preview["nodes"][0]["node_content"] == "正在形成的课程正文"
    assert draft_preview["nodes"][0]["content_state"] == "draft"
    manager.tasks[job["job_id"]]["current_nodes"] = [{"node_id": draft_preview["nodes"][0]["node_id"]}]
    active_preview = manager.get_generation_preview(job["course_id"])
    assert active_preview is not None
    assert active_preview["nodes"][0]["generation_status"] == "generating"
    workspaces.update_course(
        job["job_id"],
        lambda course: {
            **course,
            "course_teaching_plan": {
                "schema_version": "course_teaching_plan_v2",
                "revision_id": "teaching-preview-1",
                "sections": [{
                    "node_id": course["nodes"][0]["node_id"],
                    "key_points": ["概念边界"],
                    "knowledge_structure": [{
                        "concept_group": "概念组",
                        "knowledge_points": [{
                            "name": "概念边界",
                            "statement": "说明概念边界",
                            "relation_decision_reason": "内部判断不得投影",
                        }],
                    }],
                    "teaching_modules": [{
                        "module_id": "core_explanation",
                        "teaching_purpose": "解释概念边界",
                        "knowledge_names": ["概念边界"],
                        "internal_trace": "不得投影",
                    }],
                }],
            },
            "generation_stage_artifacts": {
                **(course.get("generation_stage_artifacts") or {}),
                "course_teaching_plan": {
                    "status": "completed",
                    "strategy": "single_whole_course_call",
                    "model_call_count": 1,
                    "section_count": 1,
                    "knowledge_point_count": 1,
                    "teaching_module_count": 1,
                },
            },
        },
    )


    plan_preview = manager.get_generation_preview(job["course_id"])
    assert plan_preview["teaching_plan"]["status"] == "completed"
    assert plan_preview["teaching_plan"]["sections"][0]["key_points"] == ["概念边界"]
    assert "model_call_count" not in plan_preview["teaching_plan"]
    serialized_plan = json.dumps(
        plan_preview["teaching_plan"],
        ensure_ascii=False,
    )
    assert "relation_decision_reason" not in serialized_plan
    assert "internal_trace" not in serialized_plan
    from routers import course_versions as course_versions_router

    async def load_formal_shell(_course_id):
        return {"course_id": job["course_id"], "nodes": []}

    monkeypatch.setattr(course_versions_router, "get_course_or_404", load_formal_shell)
    monkeypatch.setattr(course_versions_router, "get_task_manager_optional", lambda: manager)
    blueprint_course = await course_versions_router._course_for_blueprint(job["course_id"])
    assert blueprint_course["nodes"][0]["node_name"] == "概念"
    edited_draft = manager._version_repository.load_draft(job["course_id"])
    edited_draft["nodes"][0]["node_name"] = "用户确认后的概念"
    manager._version_repository.save_draft(job["course_id"], edited_draft)
    with pytest.raises(ValueError, match="not content"):
        await manager.confirm_generation_step(job["course_id"], "content")
    resumed = await manager.confirm_blueprint(job["course_id"])
    assert resumed["job_id"] == job["job_id"]
    assert manager.tasks[job["job_id"]]["status"] == "pending"
    duplicate = await manager.confirm_blueprint(job["course_id"])
    assert duplicate["status"] == "already_confirmed"
    assert manager._task_queue.qsize() == 1
    confirmed_course = manager.get_generation_workspace_course(job["course_id"])
    assert confirmed_course["nodes"][0]["node_name"] == "用户确认后的概念"
    assert "course_knowledge_base" not in confirmed_course
    assert await manager._task_queue.get() == job["job_id"]
    workspaces.set_status(job["job_id"], "published")
    assert manager.get_generation_preview(job["course_id"]) is None


@pytest.mark.asyncio
async def test_teacher_outline_waits_through_restart_and_explicit_continue_reuses_job(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(
        task_manager_module,
        "TASKS_FILE",
        tmp_path / "teacher-shape-tasks.json",
    )
    storage = MemoryStorage()
    service = SkeletonGateService()
    versions = CourseVersionRepository(tmp_path / "teacher-shape-versions")
    workspaces = GenerationWorkspaceRepository(tmp_path / "teacher-shape-workspaces")
    manager = TaskManager(
        storage,
        service,
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
    )
    job = await manager.create_generation_job({
        "subject": "教师章节骨架",
        "teacher_authoring_mode": "lesson_assets_v1",
        "teacher_course_brief": {"total_class_hours": 16},
        "generation_mode": "review_blueprint",
        "course_purpose": "systematic",
    })

    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_input"
    assert task["phase"] == "outline_framework_ready"
    assert "guided_workflow" not in task
    assert service.stop_after_skeleton is True
    assert service.stop_after_outline is True
    checkpoint = manager.get_generation_workspace_course(job["course_id"])
    assert checkpoint["generation_status"] == "outline_framework_ready"
    assert checkpoint["outline_framework_only"] is True
    assert checkpoint["outline_generation_status"] == "framework_ready"
    assert checkpoint["outline_lifecycle_status"] == "draft"
    assert checkpoint["course_outline_quality_report"] is None
    assert checkpoint["generation_quality_report"] is None
    assert checkpoint["course_plan"]["total_hours"] == 16
    assert len(checkpoint["course_plan"]["chapters"]) == 2
    assert all(not node.get("node_content") for node in checkpoint["nodes"])
    assert "course_teaching_plan" not in checkpoint
    framework_draft = manager._version_repository.load_draft(job["course_id"])
    assert framework_draft["outline_framework_only"] is True

    # A service restart must preserve the visible framework instead of
    # interpreting it as unfinished background work and silently continuing.
    restored_service = SkeletonGateService()
    restored = TaskManager(
        storage,
        restored_service,
        None,
        version_repository=CourseVersionRepository(
            tmp_path / "teacher-shape-versions"
        ),
        workspace_repository=GenerationWorkspaceRepository(
            tmp_path / "teacher-shape-workspaces"
        ),
        document_repository=CourseDocumentRepository(storage),
    )
    should_enqueue = await restored._reconcile_task_after_restart(job["job_id"])
    assert should_enqueue is False
    assert restored.tasks[job["job_id"]]["status"] == "waiting_for_input"
    assert restored.tasks[job["job_id"]]["phase"] == "outline_framework_ready"
    assert restored._task_queue.empty()

    # The explicit command reads the current editor draft, not the stale model
    # framework that existed before the teacher made changes.
    stale_course = restored.get_generation_workspace_course(job["course_id"])
    stale_stage = stale_course["generation_stage_artifacts"]["outline"]
    stale_stage.update({
        "course_contract_status": "completed",
        "course_contract": {"positioning": "旧课程级合同"},
        "course_contract_validation_report": {"passed": True},
        "course_contract_duration_ms": 100,
        "course_contract_failure_reason": None,
        "detail_batches": {"OUT-TD-001": {"status": "completed"}},
    })
    await restored._save_task_course(job["job_id"], stale_course)
    edited = restored._version_repository.load_draft(job["course_id"])
    edited["nodes"][0]["node_name"] = "教师修改后的第一讲"
    restored._version_repository.save_draft(job["course_id"], edited)
    restored.tasks["newer-unrelated-outline-job"] = {
        "id": "newer-unrelated-outline-job",
        "course_id": job["course_id"],
        "type": "teacher_outline_generation",
        "status": "running",
        "updated_at": "2999-01-01T00:00:00",
    }
    restored.tasks["other-course-outline-job"] = {
        "id": "other-course-outline-job",
        "course_id": "another-course",
        "type": "teacher_outline_generation",
        "status": "waiting_for_input",
    }
    with pytest.raises(TaskStateConflict):
        await restored.continue_teacher_outline_details(
            job["course_id"], "other-course-outline-job"
        )
    started = await restored.continue_teacher_outline_details(
        job["course_id"], job["job_id"]
    )
    assert started["status"] == "started"
    assert started["job_id"] == job["job_id"]
    assert started["outline_detail_requested"] is True
    assert restored.tasks[job["job_id"]]["status"] == "pending"
    assert restored.tasks[job["job_id"]]["outline_detail_requested"] is True
    progress_update = AsyncMock()
    restored.ws_service = SimpleNamespace(push_progress_update=progress_update)
    await restored._update_phase(
        job["job_id"], "outline_course_contract_generation", 32,
        "正在形成课程目标、知识模块与考核方案",
        phase_detail={"artifact_type": "course_outline_course_contract"},
    )
    assert restored.get_task_summary(job["job_id"])["outline_detail_requested"] is True
    assert progress_update.await_args.args[1]["outline_detail_requested"] is True
    restored.ws_service = None
    compiled = restored.get_generation_workspace_course(job["course_id"])
    assert compiled["generation_status"] == "outline_detail_generation"
    assert compiled["generation_stage_artifacts"]["outline"]["skeleton"][
        "chapters"
    ][0]["title"] == "教师修改后的第一讲"
    compiled_stage = compiled["generation_stage_artifacts"]["outline"]
    assert compiled_stage["detail_batches"] == {}
    assert "course_contract_status" not in compiled_stage
    assert "course_contract" not in compiled_stage
    assert "course_contract_validation_report" not in compiled_stage

    duplicate = await restored.continue_teacher_outline_details(
        job["course_id"], job["job_id"]
    )
    assert duplicate["status"] == "already_running"
    assert duplicate["outline_detail_requested"] is True
    assert restored._task_queue.qsize() == 1
    assert await restored._task_queue.get() == job["job_id"]
    await restored._process_task(job["job_id"])

    completed = restored.tasks[job["job_id"]]
    assert completed["status"] == "completed"
    assert completed["phase"] == "teacher_outline_ready"
    assert restored_service.stop_after_skeleton is False
    assert restored_service.stop_after_outline is True
    assert restored_service.detail_input["generation_stage_artifacts"]["outline"][
        "skeleton"
    ]["chapters"][0]["title"] == "教师修改后的第一讲"
    completed_course = restored.get_generation_workspace_course(job["course_id"])
    assert completed_course["generation_status"] == "teacher_outline_ready"
    assert completed_course["outline_framework_only"] is False
    assert completed_course["outline_lifecycle_status"] == "current"
    assert "course_teaching_plan" not in completed_course
    assert restored._version_repository.load_draft(job["course_id"]) is None

    unchanged = await restored.continue_teacher_outline_details(
        job["course_id"], job["job_id"]
    )
    assert unchanged["status"] == "already_completed"

    regenerated_draft = build_blueprint_draft(completed_course)
    regenerated_draft["nodes"][0]["node_name"] = "教师再次修改后的第一讲"
    restored._version_repository.save_draft(job["course_id"], regenerated_draft)
    regenerated = await restored.continue_teacher_outline_details(
        job["course_id"], job["job_id"]
    )

    assert regenerated["status"] == "started"
    assert regenerated["job_id"] == job["job_id"]
    assert restored.tasks[job["job_id"]]["status"] == "pending"
    working_course = restored.get_generation_workspace_course(job["course_id"])
    assert working_course["generation_stage_artifacts"]["outline"]["skeleton"][
        "chapters"
    ][0]["title"] == "教师再次修改后的第一讲"
    last_good = restored.get_generation_workspace_course_for_task(
        job["course_id"],
        task_type="teacher_outline_generation",
        require_usable_outline=True,
    )
    assert last_good["nodes"][0]["node_name"] == completed_course["nodes"][0][
        "node_name"
    ]
    assert last_good["generation_status"] == "teacher_outline_ready"
    restored.tasks[job["job_id"]]["status"] = "failed"
    failed_last_good = restored.get_generation_workspace_course_for_task(
        job["course_id"],
        task_type="teacher_outline_generation",
        require_usable_outline=True,
    )
    assert failed_last_good == last_good


def test_teacher_outline_result_requires_completed_course_contract():
    course = {
        "outline_framework_only": False,
        "generation_stage_artifacts": {
            "outline": {
                "strategy": "teacher_framework_then_lecture_tasks",
                "status": "completed",
                "course_contract_status": "retry_required",
                "detail_batches": {
                    "OUT-TD-001": {"status": "completed"},
                },
            },
        },
        "nodes": [{"node_id": "L1-1", "node_name": "第1讲"}],
    }

    assert _teacher_outline_result_ready(course) is False

    course["generation_stage_artifacts"]["outline"][
        "course_contract_status"
    ] = "completed"
    assert _teacher_outline_result_ready(course) is True


@pytest.mark.asyncio
async def test_teacher_outline_framework_is_editable_and_has_no_review_report(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "teacher-tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "teacher-workspaces")
    manager = TaskManager(
        storage,
        SkeletonGateService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "teacher-versions"),
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
    )
    job = await manager.create_generation_job({
        "subject": "教师十讲课程",
        "teacher_authoring_mode": "lesson_assets_v1",
        "teacher_course_brief": {"chapter_count": 10, "lesson_duration_minutes": 90},
        "generation_mode": "review_blueprint",
        "course_purpose": "systematic",
    })
    task = manager.tasks[job["job_id"]]
    assert task["type"] == "teacher_outline_generation"
    assert "guided_workflow" not in task
    assert storage.course["authoring_surface"] == "teacher"
    assert manager.get_generation_preview(
        job["course_id"],
        task_types={"course_generation", "course_import"},
    ) is None
    assert manager.get_generation_preview(
        job["course_id"],
        task_types={"teacher_outline_generation"},
    ) is not None

    assert await manager._task_queue.get() == job["job_id"]
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    waiting = manager.tasks[job["job_id"]]
    assert waiting["status"] == "waiting_for_input"
    assert waiting["phase"] == "outline_framework_ready"
    assert "轻量讲次方案已生成" in waiting["message"]
    teacher_course = manager.get_generation_workspace_course(job["course_id"])
    assert teacher_course["generation_status"] == "outline_framework_ready"
    assert teacher_course["outline_framework_only"] is True
    assert teacher_course["course_outline_quality_report"] is None
    assert teacher_course["generation_quality_report"] is None
    assert teacher_course["course_plan"]
    assert teacher_course["course_outline"]
    assert teacher_course["course_blueprint"]
    assert teacher_course["nodes"]
    assert "course_teaching_plan" not in teacher_course
    assert all(not node.get("node_content") for node in teacher_course["nodes"])
    scoped_teacher_course = manager.get_generation_workspace_course_for_task(
        job["course_id"],
        task_type="teacher_outline_generation",
        require_confirmed_outline=False,
    )
    assert scoped_teacher_course == teacher_course


@pytest.mark.asyncio
async def test_teacher_outline_empty_result_fails_instead_of_unlocking_lessons(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(
        task_manager_module,
        "TASKS_FILE",
        tmp_path / "teacher-empty-outline-tasks.json",
    )
    manager = TaskManager(
        MemoryStorage(),
        InvalidTeacherOutlineService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "teacher-empty-outline-versions"),
        workspace_repository=GenerationWorkspaceRepository(tmp_path / "teacher-empty-outline-workspaces"),
        document_repository=CourseDocumentRepository(MemoryStorage()),
    )
    job = await manager.create_generation_job({
        "subject": "空大纲失败样例",
        "teacher_authoring_mode": "lesson_assets_v1",
        "teacher_course_brief": {"lecture_count": 2},
        "generation_mode": "review_blueprint",
    })

    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])

    failed = manager.tasks[job["job_id"]]
    assert failed["status"] == "failed"
    assert failed["phase"] == "teacher_outline_failed"
    assert failed["error_detail"]["code"] == "teacher_outline_generation_invalid"


@pytest.mark.asyncio
async def test_guided_job_requires_teaching_confirmation_before_content(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "versions"),
        workspace_repository=GenerationWorkspaceRepository(tmp_path / "workspaces"),
        document_repository=CourseDocumentRepository(storage),
    )
    job = await manager.create_generation_job({"subject": "概念课"})
    assert await manager._task_queue.get() == job["job_id"]
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    await manager.confirm_generation_step(job["course_id"], "outline")
    assert await manager._task_queue.get() == job["job_id"]

    async def finish_content(_task_id, _nodes):
        manager._generation_workspace_repository.update_course(
            job["job_id"],
            lambda course: {
                **course,
                "nodes": [
                    {
                        **node,
                        "node_content": "完整课程内容。" * 120,
                        "generation_status": "completed",
                    }
                    for node in course["nodes"]
                ],
            },
        )

    monkeypatch.setattr(manager, "_schedule_nodes", finish_content)

    async def keep_compiled_practice_assets(
        _task_id,
        _course,
        question_bank_bundle,
        asset_bundle,
    ):
        return (
            question_bank_bundle,
            asset_bundle,
            {
                "target_node_count": 0,
                "generation_audit": {"model_call_count": 0},
            },
        )

    monkeypatch.setattr(
        manager,
        "_repair_failed_practice_nodes",
        keep_compiled_practice_assets,
    )
    # This workflow test uses deliberately repetitive placeholder content; the
    # quality contract is covered separately. Keep this case on the publishable
    # branch so it tests review-gate sequencing instead of relying on the old
    # impossible state (quality blocked + waiting for release confirmation).
    monkeypatch.setattr(
        manager,
        "_quality_allows_publication",
        lambda _course, _report: True,
    )
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "teaching"
    teaching_review = manager.get_generation_review(job["course_id"])
    assert teaching_review["step"] == "teaching"
    assert teaching_review["can_confirm"] is True

    await manager.confirm_generation_step(job["course_id"], "teaching")
    assert await manager._task_queue.get() == job["job_id"]
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "release"
    assert next(
        step for step in task["guided_workflow"]["steps"]
        if step["key"] == "content"
    )["status"] == "confirmed"
    review = manager.get_generation_review(job["course_id"])
    assert review["step"] == "release"
    generated_course = manager.get_generation_workspace_course(job["course_id"])
    assert generated_course["course_teaching_plan"]["schema_version"] == (
        "course_teaching_plan_v2"
    )
    assert generated_course["course_knowledge_base"]["lifecycle_status"] == "active"
    plan_stage = generated_course["generation_stage_artifacts"][
        "course_teaching_plan"
    ]
    assert plan_stage["knowledge_compilation_model_call_count"] == 0
    assert plan_stage["graph_compilation_model_call_count"] == 0

    manager._generation_workspace_repository.save_node_draft(
        job["job_id"],
        generated_course["nodes"][0]["node_id"],
        "目录变更后不得恢复的旧草稿",
    )
    stale_sidecar = (
        tmp_path
        / "workspaces"
        / ".node-drafts"
        / job["job_id"]
        / f"{generated_course['nodes'][0]['node_id']}.json"
    )
    assert stale_sidecar.exists()
    reopened = await manager.reopen_generation_step(job["course_id"], "outline")
    assert reopened["invalidated_steps"] == ["teaching", "content", "release"]
    assert task["guided_workflow"]["review_step"] == "outline"
    edited_draft = manager._version_repository.load_draft(job["course_id"])
    edited_draft["nodes"][0]["learning_objective"] = "能够比较概念的内涵与外延"
    manager._version_repository.save_draft(job["course_id"], edited_draft)
    await manager.confirm_generation_step(job["course_id"], "outline")
    assert await manager._task_queue.get() == job["job_id"]
    invalidated_course = manager.get_generation_workspace_course(job["course_id"])
    assert "course_knowledge_base" not in invalidated_course
    assert invalidated_course["nodes"][0].get("module_plan") is None
    assert invalidated_course["nodes"][0]["generation_status"] == "pending"
    assert not stale_sidecar.exists()

    monkeypatch.setattr(
        manager,
        "_quality_allows_publication",
        lambda _course, _report: True,
    )
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "teaching"
    await manager.confirm_generation_step(job["course_id"], "teaching")
    assert await manager._task_queue.get() == job["job_id"]
    await asyncio.wait_for(manager._process_task(job["job_id"]), timeout=20)
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "release"

    async def reject_confirmed_content_recompile(*_args, **_kwargs):
        raise AssertionError("已确认的内容候选不得再次编译")

    monkeypatch.setattr(
        manager,
        "_prepare_content_candidate",
        reject_confirmed_content_recompile,
    )
    asset_blocker = {
        "code": "questions:input_contract_missing",
        "severity": "critical",
        "message": "题目缺少正式练习契约",
        "blocking": True,
    }
    manager._generation_workspace_repository.update_course(
        job["job_id"],
        lambda course: {
            **course,
            "asset_quality_report": {
                **(course.get("asset_quality_report") or {}),
                "passed": False,
                "blocking_issues": [asset_blocker],
            },
        },
    )
    release_review = manager.get_generation_review(job["course_id"])
    assert release_review["step"] == "release"
    assert release_review["artifact"]["source_chain"]["can_publish"] is True
    assert asset_blocker in release_review["artifact"]["blocking_issues"]
    assert release_review["artifact"]["asset_blocking_issues"] == [
        asset_blocker
    ]
    manager._generation_workspace_repository.update_course(
        job["job_id"],
        lambda course: {
            **course,
            "asset_quality_report": {
                **(course.get("asset_quality_report") or {}),
                "passed": True,
                "blocking_issues": [],
            },
        },
    )

    await manager.confirm_generation_step(job["course_id"], "release")
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])
    assert manager.tasks[job["job_id"]]["status"] in {"completed", "completed_with_warnings"}
    assert manager._publication_receipt(manager.tasks[job["job_id"]]) is not None


@pytest.mark.asyncio
async def test_generation_workspace_survives_manager_restart(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    documents = CourseDocumentRepository(storage)
    versions = CourseVersionRepository(tmp_path / "versions")
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    job = await manager.create_generation_job({"subject": "断点续跑课程"})
    workspaces.update_course(
        job["job_id"],
        lambda course: {**course, "checkpoint_marker": "saved-before-restart"},
    )
    manager.tasks[job["job_id"]]["status"] = "paused"
    manager.save_tasks()

    restored = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )

    assert restored.tasks[job["job_id"]]["workspace_id"] == job["job_id"]
    assert restored._load_task_course(job["job_id"])["checkpoint_marker"] == "saved-before-restart"
    await restored.resume_task(job["job_id"])
    assert await restored._task_queue.get() == job["job_id"]


@pytest.mark.asyncio
async def test_failed_teacher_outline_resume_hydrates_request_from_workspace(
    tmp_path,
    monkeypatch,
):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    documents = CourseDocumentRepository(storage)
    versions = CourseVersionRepository(tmp_path / "versions")
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    job = await manager.create_generation_job({
        "subject": "线性代数",
        "requirements": "完整学期课",
        "teacher_authoring_mode": "lesson_assets_v1",
        "teacher_course_brief": {
            "chapter_count": 7,
            "lesson_duration_minutes": 45,
        },
    })
    assert await manager._task_queue.get() == job["job_id"]
    manager.tasks[job["job_id"]].update({
        "status": "failed",
        "phase": "outline_generation",
        "error": "provider unavailable",
    })
    manager.save_tasks(strict=True)

    persisted = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
    assert "request_snapshot" not in persisted[job["job_id"]]

    restored = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    assert restored.tasks[job["job_id"]].get("request_snapshot") == {}
    assert restored.tasks[job["job_id"]].get("legacy_read_only") is not True

    resumed = await restored.resume_task(job["job_id"])

    assert resumed["status"] == "resumed"
    restored_request = restored.tasks[job["job_id"]]["request_snapshot"]
    assert restored_request["subject"] == "线性代数"
    assert restored_request["requirements"] == "完整学期课"
    assert restored_request["teacher_course_brief"]["chapter_count"] == 7
    assert await restored._task_queue.get() == job["job_id"]


@pytest.mark.asyncio
async def test_waiting_confirmation_survives_restart_without_skipping_gate(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    documents = CourseDocumentRepository(storage)
    versions = CourseVersionRepository(tmp_path / "versions")
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    job = await manager.create_generation_job({"subject": "等待确认恢复课程"})
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])
    assert manager.tasks[job["job_id"]]["status"] == "waiting_for_review"
    assert manager.tasks[job["job_id"]]["guided_workflow"]["review_step"] == "outline"

    restored = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )

    should_enqueue = await restored._reconcile_task_after_restart(job["job_id"])
    assert should_enqueue is False
    assert restored.tasks[job["job_id"]]["status"] == "waiting_for_review"
    assert restored.tasks[job["job_id"]]["guided_workflow"]["review_step"] == "outline"
    assert restored._task_queue.empty()


@pytest.mark.parametrize("review_step", ["outline", "release"])
@pytest.mark.asyncio
async def test_legacy_compact_review_rebuilds_on_restart(tmp_path, monkeypatch, review_step):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    documents = CourseDocumentRepository(storage)
    versions = CourseVersionRepository(tmp_path / "versions")
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    job = await manager.create_generation_job({"subject": "旧版三章六节课程"})
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])

    legacy = manager._load_task_course(job["job_id"])
    legacy.update({
        "generation_pipeline_version": "course_generation_v15",
        "generation_schema_version": "course_generation_v15",
        "course_outline": {
            "chapters": [
                {
                    "chapter_number": index,
                    "title": f"第{index}章",
                    "sections": [{"node_id": f"L2-{index}-1"}, {"node_id": f"L2-{index}-2"}],
                }
                for index in range(1, 4)
            ],
        },
        "course_plan": {"chapters": [{"chapter_number": 1}]},
        "generation_stage_artifacts": {
            "outline": {
                "status": "completed",
                "strategy": "compact_single_call",
                "actual": {"chapter_count": 3, "section_count": 6},
            },
        },
    })
    await manager._save_task_course(job["job_id"], legacy)
    if review_step == "release":
        workflow = manager.tasks[job["job_id"]]["guided_workflow"]
        workflow["current_step"] = "release"
        workflow["review_step"] = "release"
        guided_step_state(workflow, "outline")["status"] = "confirmed"
        guided_step_state(workflow, "content")["status"] = "confirmed"
        guided_step_state(workflow, "release")["status"] = "waiting_for_confirmation"
    manager.save_tasks()

    restored = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=versions,
        workspace_repository=workspaces,
        document_repository=documents,
    )

    should_enqueue = await restored._reconcile_task_after_restart(job["job_id"])

    assert should_enqueue is True
    task = restored.tasks[job["job_id"]]
    assert task["status"] == "pending"
    assert task["phase"] == "outline_rebuild_required"
    assert task["guided_workflow"]["review_step"] is None
    assert guided_step_state(task["guided_workflow"], "outline")["status"] == "pending"
    rebuilt = restored._load_task_course(job["job_id"])
    assert "course_outline" not in rebuilt
    assert "course_plan" not in rebuilt
    assert rebuilt["nodes"] == []
    assert rebuilt["generation_stage_artifacts"] == {}


@pytest.mark.asyncio
async def test_candidate_workspace_write_does_not_mutate_current_course(tmp_path):
    current = {"course_id": "c1", "course_name": "current", "nodes": []}
    storage = MemoryStorage(current)
    versions = CourseVersionRepository(tmp_path / "versions")
    entry = versions.ensure_initial_version("c1", current)
    candidate = versions.create_candidate(
        "c1",
        {"course_id": "c1", "course_name": "candidate", "nodes": []},
        base_version_id=entry["version_id"],
        impact_report={"affected_node_ids": []},
    )
    manager = TaskManager(storage, None, None, version_repository=versions)
    manager.tasks["t1"] = {
        "id": "t1",
        "course_id": "c1",
        "candidate_id": candidate["candidate_id"],
        "status": "running",
    }
    workspace = manager._load_task_course("t1")
    workspace["course_name"] = "changed candidate"
    await manager._save_task_course("t1", workspace)

    assert storage.load_course("c1")["course_name"] == "current"
    assert versions.load_candidate("c1", candidate["candidate_id"])["course_data"]["course_name"] == "changed candidate"


@pytest.mark.asyncio
async def test_metadata_only_blueprint_change_promotes_without_generation_job(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    current = {
        "course_id": "c1",
        "course_name": "旧名称",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "概念",
            "node_content": "完整正文",
            "generation_status": "completed",
        }],
    }
    storage = MemoryStorage(current)
    versions = CourseVersionRepository(tmp_path / "versions")
    versions.ensure_initial_version("c1", current)
    draft = build_blueprint_draft(current)
    draft["course_name"] = "新名称"
    versions.save_draft("c1", draft)
    manager = TaskManager(storage, None, None, version_repository=versions)

    result = await manager.create_regeneration_job("c1", reason="修改课程名称")

    assert result["status"] == "completed"
    assert result["course_version_id"] == "cv2"
    assert storage.load_course("c1")["course_name"] == "新名称"
    assert manager.tasks == {}
    assert versions.load_draft("c1") is None
