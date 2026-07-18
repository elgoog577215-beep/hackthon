from copy import deepcopy

import pytest

from course_repository import CourseDocumentRepository
from course_versioning import build_blueprint_draft
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from task_manager import TaskManager


class MemoryStorage:
    def __init__(self, course=None):
        self.course = deepcopy(course)

    def load_course(self, _course_id):
        return deepcopy(self.course)

    async def save_course(self, _course_id, data):
        self.course = deepcopy(data)


class BlueprintService:
    async def build_course_draft(self, **kwargs):
        course = deepcopy(kwargs["existing_course_data"])
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
        if kwargs.get("stop_after_outline"):
            for node in course["nodes"]:
                node["knowledge_structure"] = []
                node["key_points"] = []
        return course


@pytest.mark.asyncio
async def test_review_mode_waits_and_confirms_same_job(tmp_path, monkeypatch):
    import task_manager as task_manager_module
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
    await manager._process_task(job["job_id"])

    assert manager.tasks[job["job_id"]]["status"] == "waiting_for_review"
    assert manager.tasks[job["job_id"]]["guided_workflow"]["review_step"] == "outline"
    assert storage.course["course_schema_version"] == "course_document_v1"
    assert storage.course["course_document"]["sections"] == []
    assert "nodes" not in storage.course
    workspace_course = manager.get_generation_workspace_course(job["course_id"])
    assert workspace_course is not None
    assert workspace_course["nodes"][0]["node_name"] == "概念"
    assert "knowledge_library_binding" not in workspace_course
    assert workspace_course["nodes"][0]["knowledge_structure"] == []
    assert "course_knowledge_base" not in workspace_course
    preview = manager.get_generation_preview(job["course_id"])
    assert preview is not None
    assert preview["projection"] == "generation_workspace"
    assert preview["task"]["status"] == "waiting_for_review"
    assert preview["nodes"][0]["node_name"] == "概念"
    assert preview["nodes"][0]["content_state"] == "pending"
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
async def test_guided_job_waits_for_knowledge_then_teaching_confirmation(tmp_path, monkeypatch):
    import task_manager as task_manager_module

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
    await manager._process_task(job["job_id"])
    await manager.confirm_generation_step(job["course_id"], "outline")
    assert await manager._task_queue.get() == job["job_id"]

    await manager._process_task(job["job_id"])
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "knowledge"
    review = manager.get_generation_review(job["course_id"])
    assert review["step"] == "knowledge"
    assert review["can_confirm"] is True

    await manager.confirm_generation_step(job["course_id"], "knowledge")
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "teaching"
    assert manager.get_generation_review(job["course_id"])["step"] == "teaching"

    await manager.confirm_generation_step(job["course_id"], "teaching")
    assert await manager._task_queue.get() == job["job_id"]
    manager._generation_workspace_repository.update_course(
        job["job_id"],
        lambda course: {
            **course,
            "nodes": [{
                **course["nodes"][0],
                "node_content": "完整课程内容。" * 120,
                "generation_status": "completed",
            }],
        },
    )
    await manager._process_task(job["job_id"])
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "content"
    await manager.confirm_generation_step(job["course_id"], "content")
    assert await manager._task_queue.get() == job["job_id"]
    monkeypatch.setattr(
        manager,
        "_quality_allows_publication",
        lambda _course, _report: True,
    )
    await manager._process_task(job["job_id"])
    task = manager.tasks[job["job_id"]]
    assert task["status"] == "waiting_for_review"
    assert task["guided_workflow"]["review_step"] == "release"
    release_review = manager.get_generation_review(job["course_id"])
    assert release_review["step"] == "release"
    assert release_review["artifact"]["source_chain"]["can_publish"] is True

    await manager.confirm_generation_step(job["course_id"], "release")
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])
    assert manager.tasks[job["job_id"]]["status"] in {"completed", "completed_with_warnings"}
    assert manager._publication_receipt(manager.tasks[job["job_id"]]) is not None


@pytest.mark.asyncio
async def test_generation_workspace_survives_manager_restart(tmp_path, monkeypatch):
    import task_manager as task_manager_module

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
async def test_waiting_confirmation_survives_restart_without_skipping_gate(tmp_path, monkeypatch):
    import task_manager as task_manager_module

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
    import task_manager as task_manager_module
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
