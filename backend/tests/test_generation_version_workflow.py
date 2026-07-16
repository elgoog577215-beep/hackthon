from copy import deepcopy

import pytest

from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from course_versioning import build_blueprint_draft
from generation_workspace import GenerationWorkspaceRepository
from subject_ontology import build_subject_ontology
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
                "key_points": ["概念"],
                "assessment": ["解释概念"],
                "difficulty_contract": {},
                "grounding_contract": {},
                "generation_status": "pending",
            }],
        })
        return course


class PinnedSubjectLibraryService:
    def __init__(self):
        self.prepare_calls = 0
        self.library = None

    async def prepare_course(self, course, **_kwargs):
        self.prepare_calls += 1
        library = build_subject_ontology(course)
        self.library = library
        return {
            "library": library,
            "binding": {
                "subject_id": library["subject_id"],
                "library_id": library["library_id"],
                "revision_id": library["revision_id"],
                "lifecycle_status": library["lifecycle_status"],
                "binding_status": "pinned",
            },
            "quality_report": {
                "passed": True,
                "issues": [],
                "blocking_issues": [],
            },
        }

    def resolve_course_library(self, _course):
        return self.library


@pytest.mark.asyncio
async def test_review_mode_waits_and_confirms_same_job(tmp_path, monkeypatch):
    import task_manager as task_manager_module
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage()
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    subject_libraries = PinnedSubjectLibraryService()
    manager = TaskManager(
        storage,
        BlueprintService(),
        None,
        version_repository=CourseVersionRepository(tmp_path / "versions"),
        workspace_repository=workspaces,
        document_repository=CourseDocumentRepository(storage),
        subject_library_service=subject_libraries,
    )
    job = await manager.create_generation_job({
        "subject": "概念课",
        "generation_mode": "review_blueprint",
        "course_purpose": "systematic",
    })
    assert await manager._task_queue.get() == job["job_id"]
    await manager._process_task(job["job_id"])

    assert manager.tasks[job["job_id"]]["status"] == "waiting_for_review"
    assert storage.course["course_schema_version"] == "course_document_v1"
    assert storage.course["course_document"]["sections"] == []
    assert "nodes" not in storage.course
    workspace_course = manager.get_generation_workspace_course(job["course_id"])
    assert workspace_course is not None
    assert workspace_course["nodes"][0]["node_name"] == "概念"
    binding = workspace_course["knowledge_library_binding"]
    assert binding["binding_status"] == "pinned"
    assert workspace_course["course_knowledge_map"]["binding_revision_id"] == binding["revision_id"]
    assert workspace_course["course_knowledge_base"]["formal_library_revision_id"] == binding["revision_id"]
    assert subject_libraries.prepare_calls == 1
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
    resumed = await manager.confirm_blueprint(job["course_id"])
    assert resumed["job_id"] == job["job_id"]
    assert manager.tasks[job["job_id"]]["status"] == "pending"
    confirmed_course = manager.get_generation_workspace_course(job["course_id"])
    assert confirmed_course["course_knowledge_base"]["formal_library_revision_id"] == binding["revision_id"]
    assert subject_libraries.prepare_calls == 1
    assert await manager._task_queue.get() == job["job_id"]
    workspaces.set_status(job["job_id"], "published")
    assert manager.get_generation_preview(job["course_id"]) is None


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
