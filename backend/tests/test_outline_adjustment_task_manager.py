from __future__ import annotations

from copy import deepcopy
import json

import pytest

from course_outline_adjustments import apply_outline_operations
from course_generation.service import CourseService
from course_versioning import blueprint_draft_revision_id, build_blueprint_draft
from course_versions import CourseVersionRepository
from guided_generation import confirm_waiting_step, create_guided_workflow, mark_waiting
from jobs.manager import TaskManager


class MemoryStorage:
    def __init__(self, course):
        self.course = deepcopy(course)

    def load_course(self, _course_id):
        return deepcopy(self.course)

    async def save_course(self, _course_id, course):
        self.course = deepcopy(course)


class CorrectingOutlineService:
    def __init__(self):
        self.calls = []

    async def propose_outline_adjustment(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if len(self.calls) == 1:
            return {
                "operations": [{"op": "remove_node", "node_ref": "L1-1"}],
                "summary": "错误地删除非空章节",
            }
        return {
            "operations": [{
                "op": "add_node",
                "temp_ref": "tmp-components",
                "node_level": 2,
                "parent_ref": "L1-1",
                "after_ref": "L2-1-1",
                "node_name": "组件组合",
                "learning_objective": "使用组件组合实现角色能力",
                "prerequisite_refs": ["L2-1-1"],
            }],
            "summary": "新增组件组合小节",
        }


def _course() -> dict:
    return {
        "course_id": "course-outline",
        "course_name": "Unity 游戏编程",
        "course_type": "systematic",
        "course_purpose": "systematic",
        "course_generation_brief": {
            "course_type": "systematic",
            "course_shape_constraints": {"chapter_count": 1, "section_count": 1},
        },
        "course_plan": {
            "course_title": "Unity 游戏编程",
            "chapters": [{
                "chapter_number": 1,
                "node_id": "L1-1",
                "title": "基础",
                "sections": [{
                    "section_number": "1.1",
                    "node_id": "L2-1-1",
                    "title": "生命周期",
                    "learning_objective": "选择生命周期入口",
                }],
            }],
        },
        "course_outline": {},
        "course_blueprint": {},
        "blueprint_locks": {},
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_level": 1,
                "node_name": "基础",
                "learning_objective": "建立基础",
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_level": 2,
                "node_name": "生命周期",
                "learning_objective": "选择生命周期入口",
                "prerequisite_node_ids": [],
            },
        ],
    }


def _waiting_task() -> dict:
    workflow = create_guided_workflow({"subject": "Unity 游戏编程"})
    mark_waiting(workflow, "outline", revision="outline-before")
    return {
        "id": "job-outline",
        "job_id": "job-outline",
        "task_id": "job-outline",
        "course_id": "course-outline",
        "type": "course_generation",
        "status": "waiting_for_review",
        "updated_at": "2026-08-04T10:00:00",
        "request_snapshot": {"subject": "Unity 游戏编程"},
        "guided_workflow": workflow,
        "logs": [],
    }


def _completed_teacher_task() -> dict:
    task = _waiting_task()
    task["type"] = "teacher_outline_generation"
    confirm_waiting_step(
        task["guided_workflow"],
        "outline",
        revision="outline-before",
    )
    task["status"] = "completed"
    task["phase"] = "teacher_outline_confirmed"
    task["current_phase"] = "teacher_outline_confirmed"
    return task


def _manager(tmp_path, monkeypatch):
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    storage = MemoryStorage(_course())
    service = CorrectingOutlineService()
    versions = CourseVersionRepository(tmp_path / "versions")
    manager = TaskManager(storage, service, None, version_repository=versions)
    manager.tasks = {"job-outline": _waiting_task()}
    return manager, service, storage, versions


@pytest.mark.asyncio
async def test_preview_corrects_once_and_never_persists_the_candidate(tmp_path, monkeypatch):
    manager, service, _storage, versions = _manager(tmp_path, monkeypatch)
    source = build_blueprint_draft(_course())

    proposal = await manager.preview_outline_adjustment(
        "course-outline",
        {
            "request_id": "request-correction",
            "base_blueprint_revision_id": source["base_blueprint_revision_id"],
            "expected_draft_revision_id": source["draft_revision_id"],
            "instruction": "新增一节组件组合",
        },
    )

    assert proposal["can_apply"] is True
    assert proposal["diff"]["after"] == {"chapter_count": 1, "section_count": 2}
    assert len(service.calls) == 2
    assert service.calls[0]["correction"] is None
    assert service.calls[1]["correction"]["validation_error"]["code"] == "chapter_not_empty"
    assert versions.load_draft("course-outline") is None


@pytest.mark.asyncio
async def test_preview_allows_a_reopened_outline(tmp_path, monkeypatch):
    manager, service, _storage, _versions = _manager(tmp_path, monkeypatch)
    manager.tasks["job-outline"]["guided_workflow"]["steps"][1][
        "previous_confirmed_revision"
    ] = "outline-confirmed"
    source = build_blueprint_draft(_course())

    proposal = await manager.preview_outline_adjustment(
        "course-outline",
        {
            "request_id": "request-reopened",
            "base_blueprint_revision_id": source["base_blueprint_revision_id"],
            "expected_draft_revision_id": source["draft_revision_id"],
            "instruction": "重构目录",
        },
    )

    assert proposal["can_apply"] is True
    assert proposal["lifecycle_reopened"] is False
    assert len(service.calls) == 2


@pytest.mark.asyncio
async def test_preview_reopens_a_confirmed_teacher_outline(tmp_path, monkeypatch):
    manager, service, _storage, versions = _manager(tmp_path, monkeypatch)
    manager.tasks["job-outline"] = _completed_teacher_task()
    source = build_blueprint_draft(_course())

    proposal = await manager.preview_outline_adjustment(
        "course-outline",
        {
            "request_id": "request-confirmed-teacher-outline",
            "base_blueprint_revision_id": source["base_blueprint_revision_id"],
            "expected_draft_revision_id": source["draft_revision_id"],
            "instruction": "新增一节组件组合",
        },
    )

    task = manager.tasks["job-outline"]
    outline_state = task["guided_workflow"]["steps"][1]
    assert proposal["can_apply"] is True
    assert proposal["lifecycle_reopened"] is True
    assert task["status"] == "waiting_for_review"
    assert task["phase"] == "outline_reopened"
    assert task["guided_workflow"]["review_step"] == "outline"
    assert outline_state["status"] == "waiting_for_confirmation"
    assert outline_state["previous_confirmed_revision"] == "outline-before"
    assert versions.load_draft("course-outline") is not None
    assert len(service.calls) == 2


@pytest.mark.asyncio
async def test_confirmed_adjustment_is_the_plan_read_by_followup_generation(tmp_path, monkeypatch):
    manager, _service, storage, versions = _manager(tmp_path, monkeypatch)
    source = build_blueprint_draft(_course())
    adjusted = apply_outline_operations(
        source,
        [{
            "op": "add_node",
            "temp_ref": "tmp-components",
            "node_level": 2,
            "parent_ref": "L1-1",
            "after_ref": "L2-1-1",
            "node_name": "组件组合",
            "learning_objective": "使用组件组合实现角色能力",
            "prerequisite_refs": ["L2-1-1"],
        }],
    )["draft"]
    adjusted["draft_revision_id"] = blueprint_draft_revision_id(adjusted)
    versions.save_draft("course-outline", adjusted)

    await manager.confirm_generation_step("course-outline", "outline")

    assert [node["node_name"] for node in storage.course["nodes"]] == [
        "第1章 基础",
        "1.1 生命周期",
        "1.2 组件组合",
    ]
    sections = storage.course["course_plan"]["chapters"][0]["sections"]
    assert [section["title"] for section in sections] == ["1.1 生命周期", "1.2 组件组合"]
    assert [section["node_id"] for section in sections] == ["L2-1-1", "L2-1-2"]
    assert versions.load_draft("course-outline") is None


@pytest.mark.asyncio
async def test_course_service_serializes_the_real_outline_adjustment_request(monkeypatch):
    service = CourseService.__new__(CourseService)
    captured = {}

    async def fake_call(prompt, system_prompt, **kwargs):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        captured["kwargs"] = kwargs
        return '{"operations": [], "summary": "无需调整"}'

    monkeypatch.setattr(service, "_call_llm", fake_call)

    result = await service.propose_outline_adjustment(
        draft=build_blueprint_draft(_course()),
        instruction="给第六章增加一个经典案例",
    )

    request = json.loads(captured["prompt"])
    assert request["instruction"] == "给第六章增加一个经典案例"
    assert request["outline"][0]["node_id"] == "L1-1"
    assert result == {"operations": [], "summary": "无需调整"}
