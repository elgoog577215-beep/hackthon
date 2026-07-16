from __future__ import annotations

from copy import deepcopy

import pytest

from course_acceptance import inspect_course_acceptance, read_version_context
from course_repository import CourseDocumentRepository
from course_versions import CourseVersionRepository
from generation_workspace import GenerationWorkspaceRepository
from learning_asset_storage import LearningAssetRepository
from task_manager import TaskManager


class MemoryStorage:
    def __init__(self, course=None):
        self.course = deepcopy(course)

    def load_course(self, _course_id):
        return deepcopy(self.course)

    async def save_course(self, _course_id, data):
        self.course = deepcopy(data)


def _knowledge_structure(name):
    definition = f"{name}的定义条件"
    boundary = f"{name}的应用边界"
    return [{
        "concept_group": f"{name}的核心结构",
        "description": f"组织{name}的成立条件与应用边界",
        "knowledge_points": [{
            "name": definition,
            "statement": f"{name}必须在对象和成立条件明确时才能用于推理。",
            "knowledge_type": "definition",
            "conditions": [f"已经识别{name}的对象"],
            "boundaries": [f"不满足{name}条件时结论不成立"],
            "capability_points": [{
                "name": f"解释{name}定义",
                "observable_behavior": f"给定案例，准确说明{name}的对象与成立条件",
            }],
            "misconceptions": [{
                "name": f"忽略{name}的适用条件",
                "observable_error_pattern": f"没有检查条件就直接应用{name}",
                "discrimination": f"逐项核对{name}的对象、条件和结论",
                "repair_strategy": f"补写{name}的条件检查后重新完成推理",
            }],
            "mastery_criteria": [{
                "name": f"{name}定义解释达标",
                "observable_performance": f"独立解释{name}的定义、条件与反例",
                "verification_method": "使用正例、反例和边界例进行验收",
            }],
            "entry_reason": f"{definition}是本节学习入口。",
            "relations": [{
                "target_name": boundary,
                "relation_type": "prerequisite",
                "reason": f"先明确{name}的定义条件，才能判断应用边界",
            }],
        }, {
            "name": boundary,
            "statement": f"应用{name}前必须检查条件，超出边界时需要更换方法。",
            "knowledge_type": "rule",
            "conditions": [f"案例满足{name}的成立条件"],
            "boundaries": [f"存在违反{name}条件的边界例"],
            "capability_points": [{
                "name": f"判断{name}边界",
                "observable_behavior": f"判断{name}在新情境中是否适用并说明依据",
            }],
            "mastery_criteria": [{
                "name": f"{name}边界判断达标",
                "observable_performance": f"独立判断{name}的适用性并检查结果",
                "verification_method": "完成一个迁移任务并说明条件检查过程",
            }],
        }],
    }]


def _learning_node(node_id, parent_id, name, *, prerequisites=None):
    return {
        "node_id": node_id,
        "parent_node_id": parent_id,
        "node_level": 2,
        "node_name": name,
        "node_content": (
            f"## {name}的定义条件\n\n{name}用于建立概念、条件和推理过程。\n\n"
            f"## {name}的应用边界\n\n先说明依据，再完成推导过程，最后检查{name}的适用边界。"
        ),
        "learning_objective": f"能够解释并应用{name}",
        "knowledge_structure": _knowledge_structure(name),
        "key_points": [f"{name}的定义条件", f"{name}的应用边界"],
        "assessment": [f"在新情境中应用{name}并说明依据、过程和结果检查"],
        "misconceptions": [f"忽略{name}的适用条件"],
        "prerequisite_node_ids": prerequisites or [],
        "difficulty_contract": {
            "challenge": {"reasoning_depth": 2},
            "support": {"scaffold_intensity": 2},
            "mastery": {"independence": 2},
            "subject_task": "worked_solution",
        },
        "grounding_contract": {},
        "generation_status": "completed",
    }


def _generated_course():
    return {
        "course_id": "generated-ready",
        "course_name": "线性代数全链路验收",
        "course_purpose": "systematic",
        "generation_status": "content_generation",
        "subject_pedagogy_profile": {
            "primary_mode": "math_formal",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "generated acceptance course",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "nodes": [
            {"node_id": "L1-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一章"},
            _learning_node("L2-1-1", "L1-1", "向量"),
            _learning_node("L2-1-2", "L1-1", "矩阵", prerequisites=["L2-1-1"]),
            {"node_id": "L1-2", "parent_node_id": "root", "node_level": 1, "node_name": "第二章"},
            _learning_node("L2-2-1", "L1-2", "线性方程组", prerequisites=["L2-1-2"]),
            _learning_node("L2-2-2", "L1-2", "线性空间", prerequisites=["L2-2-1"]),
        ],
    }


async def _manager(tmp_path, monkeypatch, course):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    versions = CourseVersionRepository(tmp_path / "versions")
    assets = LearningAssetRepository(tmp_path / "assets")
    workspaces = GenerationWorkspaceRepository(tmp_path / "workspaces")
    storage = MemoryStorage()
    documents = CourseDocumentRepository(storage)
    shell = await documents.create_generation_shell(
        course["course_id"],
        title=course["course_name"],
        job_id="job-1",
        metadata=course,
    )
    workspaces.create("job-1", course_id=course["course_id"], course_data=course)
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        version_repository=versions,
        asset_repository=assets,
        workspace_repository=workspaces,
        document_repository=documents,
    )
    manager.save_tasks = lambda: None
    manager.tasks["job-1"] = {
        "id": "job-1",
        "course_id": course["course_id"],
        "type": "course_generation",
        "status": "running",
        "progress": 90,
        "completed_nodes": 4,
        "total_nodes": 4,
        "current_nodes": [],
        "request_snapshot": {},
        "operation": "generate",
        "candidate_id": None,
        "course_version_id": None,
        "workspace_id": "job-1",
        "base_document_revision": shell["document"]["document_revision"],
    }
    return manager, storage, versions, assets, workspaces, documents


@pytest.mark.asyncio
async def test_generation_completion_publishes_one_strictly_ready_course(tmp_path, monkeypatch):
    course = _generated_course()
    manager, storage, versions, assets, workspaces, documents = await _manager(
        tmp_path, monkeypatch, course
    )
    monkeypatch.setattr(
        "task_manager.build_final_course_quality_report",
        lambda _course, job_id: {"job_id": job_id, "final_status": "passed"},
    )

    await manager._complete_task("job-1", course)

    published = storage.course
    assert published["generation_status"] == "passed"
    assert published["current_course_version_id"].startswith("cdr_")
    assert published["course_document_revision"] == published["current_course_version_id"]
    assert versions.current_version_id(course["course_id"]) is None
    assert assets.load_bundle(course["course_id"])["bundle_revision_id"] == published["learning_asset_bundle_revision_id"]
    assert "nodes" not in published
    assert published["course_document"]["sections"]
    assert published["course_document"]["blocks"]
    assert workspaces.load("job-1")["status"] == "published"
    assert manager.get_generation_workspace_course(course["course_id"]) is None
    projected = documents.load_course_view(course["course_id"])
    assert all(node.get("content_blocks") for node in projected["nodes"] if node.get("node_level") == 2)

    report = inspect_course_acceptance(
        published,
        requested_profile="standard",
        version_context=read_version_context(versions, course["course_id"]),
    )
    assert report["status"] == "ready"
    assert report["ready_for_full_chain"] is True
    assert manager.tasks["job-1"]["status"] == "completed"


@pytest.mark.asyncio
async def test_non_blocking_quality_warning_is_published_with_visible_status(
    tmp_path, monkeypatch
):
    course = _generated_course()
    manager, storage, _versions, assets, workspaces, _documents = await _manager(
        tmp_path, monkeypatch, course
    )
    monkeypatch.setattr(
        "task_manager.build_final_course_quality_report",
        lambda _course, job_id: {
            "job_id": job_id,
            "final_status": "completed_with_warnings",
            "publication_allowed": True,
            "blocking_issues": [],
        },
    )

    await manager._complete_task("job-1", course)

    assert storage.course["generation_status"] == "completed_with_warnings"
    assert storage.course["course_document"]["sections"]
    assert storage.course["course_document"]["blocks"]
    assert assets.load_bundle(course["course_id"]) is not None
    assert workspaces.load("job-1")["status"] == "published"
    assert manager.tasks["job-1"]["status"] == "completed_with_warnings"
    assert manager.tasks["job-1"]["phase"] == "completed"
    assert manager.tasks["job-1"]["publication_allowed"] is True


@pytest.mark.asyncio
async def test_restart_rechecks_old_quality_block_without_regenerating_content(
    tmp_path, monkeypatch
):
    course = _generated_course()
    manager, storage, _versions, _assets, workspaces, _documents = await _manager(
        tmp_path, monkeypatch, course
    )
    manager.tasks["job-1"].update({
        "status": "completed_with_warnings",
        "phase": "quality_failed",
        "progress": 100,
    })
    workspaces.set_status("job-1", "quality_failed")
    monkeypatch.setattr(
        "task_manager.build_final_course_quality_report",
        lambda _course, job_id: {
            "job_id": job_id,
            "final_status": "completed_with_warnings",
            "publication_allowed": True,
            "blocking_issues": [],
        },
    )

    should_queue = await manager._reconcile_task_after_restart("job-1")

    assert should_queue is False
    assert storage.course["course_document"]["blocks"]
    assert workspaces.load("job-1")["status"] == "published"
    assert manager.tasks["job-1"]["phase"] == "completed"
    assert manager.tasks["job-1"]["status"] == "completed_with_warnings"


@pytest.mark.asyncio
async def test_failed_asset_quality_keeps_revision_inactive_and_unpublished(tmp_path, monkeypatch):
    course = _generated_course()
    for node in course["nodes"]:
        if node.get("node_level") == 2:
            for group in node.get("knowledge_structure") or []:
                for point in group.get("knowledge_points") or []:
                    point["misconceptions"] = []
    manager, storage, versions, assets, workspaces, _documents = await _manager(
        tmp_path, monkeypatch, course
    )
    monkeypatch.setattr(
        "task_manager.build_final_course_quality_report",
        lambda _course, job_id: {"job_id": job_id, "final_status": "passed"},
    )

    await manager._complete_task("job-1", course)

    assert storage.course["generation_status"] == "completed_with_warnings"
    assert storage.course.get("current_course_version_id") == ""
    assert storage.course["course_document"]["sections"] == []
    assert storage.course["course_document"]["blocks"] == []
    assert "nodes" not in storage.course
    assert versions.current_version_id(course["course_id"]) is None
    assert assets.load_bundle(course["course_id"]) is None
    assert len(list((tmp_path / "assets" / course["course_id"] / "revisions").glob("*.json"))) == 1
    assert workspaces.load("job-1")["status"] == "quality_failed"
    workspace_course = manager.get_generation_workspace_course(course["course_id"])
    assert workspace_course is not None
    assert workspace_course["nodes"]
    assert manager.tasks["job-1"]["status"] == "completed_with_warnings"
    assert manager.tasks["job-1"]["phase"] == "quality_failed"


@pytest.mark.asyncio
async def test_runtime_failure_keeps_draft_isolated_and_marks_shell_failed(tmp_path, monkeypatch):
    course = _generated_course()
    manager, storage, _versions, _assets, workspaces, _documents = await _manager(
        tmp_path, monkeypatch, course
    )

    async def fail(_task_id):
        raise RuntimeError("provider unavailable")

    manager._process_task = fail
    await manager._run_job("job-1")

    assert manager.tasks["job-1"]["status"] == "failed"
    assert storage.course["generation_status"] == "failed"
    assert storage.course["course_document"]["blocks"] == []
    assert "nodes" not in storage.course
    assert workspaces.load("job-1")["status"] == "failed"
    assert workspaces.load_course("job-1")["nodes"]
