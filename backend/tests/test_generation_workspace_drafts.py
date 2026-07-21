from __future__ import annotations

import json

import pytest

from generation_workspace import GenerationWorkspaceRepository
from task_manager import TaskManager


def _course() -> dict:
    return {
        "course_id": "course-draft",
        "course_name": "草稿检查点课程",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "1.1 流式正文",
            "node_content": "",
            "generation_status": "generating",
        }],
    }


def test_node_draft_checkpoint_does_not_rewrite_main_workspace(tmp_path):
    root = tmp_path / "workspaces"
    repository = GenerationWorkspaceRepository(root)
    repository.create(
        "job-draft",
        course_id="course-draft",
        course_data=_course(),
    )
    workspace_path = root / "job-draft.json"
    before = workspace_path.read_bytes()
    before_mtime = workspace_path.stat().st_mtime_ns

    repository.save_node_draft(
        "job-draft",
        "L2-1-1",
        "已经流式生成的正文",
        generation_runtime={"output_chars": 10},
    )

    assert workspace_path.read_bytes() == before
    assert workspace_path.stat().st_mtime_ns == before_mtime
    sidecar = root / ".node-drafts" / "job-draft" / "L2-1-1.json"
    assert sidecar.stat().st_size < workspace_path.stat().st_size
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["content"] == "已经流式生成的正文"


def test_node_draft_is_overlaid_after_repository_restart(tmp_path):
    root = tmp_path / "workspaces"
    repository = GenerationWorkspaceRepository(root)
    repository.create(
        "job-draft",
        course_id="course-draft",
        course_data=_course(),
    )
    repository.save_node_draft(
        "job-draft",
        "L2-1-1",
        "进程退出前的草稿",
        generation_runtime={"output_chars": 9},
    )

    restored = GenerationWorkspaceRepository(root)
    node = restored.load_course("job-draft")["nodes"][0]

    assert node["node_content_draft"] == "进程退出前的草稿"
    assert node["generation_runtime"]["output_chars"] == 9


def test_finalized_main_content_wins_over_stale_sidecar(tmp_path):
    repository = GenerationWorkspaceRepository(tmp_path / "workspaces")
    repository.create(
        "job-draft",
        course_id="course-draft",
        course_data=_course(),
    )
    repository.save_node_draft(
        "job-draft",
        "L2-1-1",
        "旧草稿",
    )

    def finalize(course: dict) -> dict:
        course["nodes"][0].update({
            "node_content": "最终正文",
            "generation_status": "completed",
        })
        return course

    repository.update_course("job-draft", finalize)

    node = repository.load_course("job-draft")["nodes"][0]
    assert node["node_content"] == "最终正文"
    assert "node_content_draft" not in node


@pytest.mark.asyncio
async def test_task_manager_clears_sidecar_after_final_commit(tmp_path, monkeypatch):
    import task_manager as task_manager_module

    monkeypatch.setattr(
        task_manager_module,
        "TASKS_FILE",
        tmp_path / "generation_jobs.json",
    )
    root = tmp_path / "workspaces"
    repository = GenerationWorkspaceRepository(root)
    repository.create(
        "job-draft",
        course_id="course-draft",
        course_data=_course(),
    )
    repository.save_node_draft(
        "job-draft",
        "L2-1-1",
        "即将定稿的草稿",
    )
    manager = TaskManager(
        storage=None,
        course_service=None,
        ws_service=None,
        workspace_repository=repository,
    )
    manager.tasks["job-draft"] = {
        "id": "job-draft",
        "course_id": "course-draft",
        "workspace_id": "job-draft",
        "status": "running",
    }

    saved = await manager._save_generated_node_content(
        "job-draft",
        "course-draft",
        "L2-1-1",
        "最终正文",
        4,
    )

    assert saved["nodes"][0]["generation_status"] == "completed"
    assert not (
        root / ".node-drafts" / "job-draft" / "L2-1-1.json"
    ).exists()
    assert repository.load_course("job-draft")["nodes"][0][
        "node_content"
    ].endswith("最终正文")


def test_workspace_delete_removes_node_draft_directory(tmp_path):
    root = tmp_path / "workspaces"
    repository = GenerationWorkspaceRepository(root)
    repository.create(
        "job-draft",
        course_id="course-draft",
        course_data=_course(),
    )
    repository.save_node_draft(
        "job-draft",
        "L2-1-1",
        "待删除草稿",
    )

    assert repository.delete("job-draft") is True
    assert not (root / "job-draft.json").exists()
    assert not (root / ".node-drafts" / "job-draft").exists()
